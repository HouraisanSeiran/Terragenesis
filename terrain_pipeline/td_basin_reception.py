"""Cold-read, event-dependent reception across pinned physical basin faces."""

import hashlib
import json

import numpy as np

from terrain_pipeline.td_basin_overflow import _face_id, _physical_faces
from terrain_pipeline.td_basin_overflow import _topology_identity, validate_overflow_event
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy


SCHEMA = "td-stable-basin-reception-v1"
MIN_FACE_VOLUME_M3 = 1e-6
RELATIVE_TOLERANCE = .01
LEDGER_TOLERANCE_M3 = 1e-7


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def _event_ledger(topology, event, leaf_lookup):
    arrays = event["arrays"]
    water = arrays["volume_m3"]
    steps, count = arrays["input_volume_m3"].shape
    incoming = np.zeros((steps, count))
    outgoing = np.zeros_like(incoming)
    exports = np.zeros_like(incoming)
    for face_index, face in enumerate(topology["faces"]):
        first, second = (leaf_lookup[int(leaf)] for leaf in face["leaf_ids"])
        incoming[:, first] += arrays["face_reverse_m3"][:, face_index]
        outgoing[:, first] += arrays["face_forward_m3"][:, face_index]
        incoming[:, second] += arrays["face_forward_m3"][:, face_index]
        outgoing[:, second] += arrays["face_reverse_m3"][:, face_index]
    for boundary_index, boundary in enumerate(topology["engineering_boundaries"]):
        exports[:, leaf_lookup[int(boundary["leaf_id"])]] += arrays["engineering_boundary_outflow_m3"][:, boundary_index]
    residual = arrays["input_volume_m3"] + incoming - outgoing - exports - np.diff(water, axis=0)
    if not np.isfinite(residual).all() or np.any(np.abs(residual) > LEDGER_TOLERANCE_M3):
        raise ValueError("independent per-interval basin inventory closure failed")
    if not np.allclose(arrays["face_net_m3"], arrays["face_forward_m3"] - arrays["face_reverse_m3"], rtol=0, atol=1e-9):
        raise ValueError("saved face net disagrees with directional volumes")
    if not np.allclose(arrays["input_volume_m3"],
                       (arrays["rain_mm_h"][:, None] * event["metadata"]["parameters"]["runoff_coefficient"] / 3_600_000.
                        + event["metadata"]["parameters"]["baseflow_mm_per_day"] / 86_400_000.)
                       * topology["arrays"]["leaf_area_m2"][None, :] * event["metadata"]["timestep_s"],
                       rtol=0, atol=LEDGER_TOLERANCE_M3):
        raise ValueError("saved rain input mismatch")
    return incoming, outgoing, exports, residual


def build_basin_reception(topology, event, reference_event, hierarchy):
    """Report saved-interval exchange; no solver calls or permanent channel claim."""
    validate_basin_hierarchy(hierarchy)
    if topology["identity_sha256"] != _topology_identity(topology):
        raise ValueError("topology identity mismatch")
    if (topology["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or
            topology["metadata"]["source_identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"]):
        raise ValueError("topology/hierarchy identity mismatch")
    validate_overflow_event(event, topology)
    validate_overflow_event(reference_event, topology)
    metadata, reference = event["metadata"], reference_event["metadata"]
    for key in ("topology_identity_sha256", "hierarchy_identity_sha256", "source_identity_sha256", "parameters", "steps", "timestep_s", "duration_s"):
        if metadata[key] != reference[key]:
            raise ValueError("event/reference physics or time grid mismatch")
    if metadata["topology_identity_sha256"] != topology["identity_sha256"]:
        raise ValueError("event/topology identity mismatch")
    arrays, other = event["arrays"], reference_event["arrays"]
    if not np.array_equal(arrays["rain_mm_h"], other["rain_mm_h"]) or not np.array_equal(arrays["volume_m3"][0], other["volume_m3"][0]):
        raise ValueError("event/reference rain or initial inventory mismatch")
    leaves = [int(leaf) for leaf in topology["arrays"]["leaf_ids"]]
    lookup = {leaf: index for index, leaf in enumerate(leaves)}
    if len(lookup) != len(leaves):
        raise ValueError("duplicate topology leaf")
    ledgers = _event_ledger(topology, event, lookup)
    _event_ledger(topology, reference_event, lookup)
    height = hierarchy["arrays"]["height_m"]
    rows, columns = height.shape
    valid = hierarchy["arrays"]["valid_mask"].ravel()
    protected = hierarchy["arrays"]["protected_mask"].ravel()
    owners = hierarchy["arrays"]["contribution_owner"].ravel()
    face_cells = hierarchy["arrays"]["face_cells"]
    spacing = float(hierarchy["metadata"]["spacing_m"])
    origin = hierarchy["metadata"]["origin_m_xz"]
    if spacing <= 0 or not np.isfinite(spacing):
        raise ValueError("invalid hierarchy spacing")
    faces = []
    seen = set()
    expected_faces = _physical_faces(hierarchy, topology["arrays"]["leaf_ids"], lookup)
    if ({face["face_id"] for face in expected_faces} != {face["face_id"] for face in topology["faces"]} or
            len(expected_faces) != len(topology["faces"])):
        raise ValueError("lowest-sill D4 face coverage mismatch")
    steps = metadata["steps"]
    late_start = int(np.floor(.8 * steps))
    for face_index, face in enumerate(topology["faces"]):
        hierarchy_index = int(face["face_index"])
        if not 0 <= hierarchy_index < len(face_cells) or hierarchy_index in seen:
            raise ValueError("face coverage or duplicate mismatch")
        seen.add(hierarchy_index)
        cells = [int(cell) for cell in face_cells[hierarchy_index]]
        if cells != face["cell_ids"] or any(not 0 <= cell < rows * columns for cell in cells):
            raise ValueError("face cell pairing mismatch")
        first_row, first_col = divmod(cells[0], columns)
        second_row, second_col = divmod(cells[1], columns)
        if (abs(first_row - second_row) + abs(first_col - second_col) != 1 or
                not valid[cells].all() or protected[cells].any()):
            raise ValueError("face D4/valid/protection mismatch")
        cell_owners = [int(owners[cell]) for cell in cells]
        if sorted(cell_owners) != face["leaf_ids"] or face["leaf_ids"][0] == face["leaf_ids"][1]:
            raise ValueError("face owner pairing mismatch")
        if face["face_id"] != _face_id(hierarchy, hierarchy_index) or face["sill_m"] != float(max(height.ravel()[cells])):
            raise ValueError("face identity or original-bed sill mismatch")
        endpoints = [[float(origin[0] + column * spacing), float(height[row, column]),
                      float(origin[1] + row * spacing)] for row, column in ((first_row, first_col), (second_row, second_col))]
        forward = arrays["face_forward_m3"][:, face_index]
        reverse = arrays["face_reverse_m3"][:, face_index]
        net = forward - reverse
        ref_net = other["face_forward_m3"][:, face_index] - other["face_reverse_m3"][:, face_index]
        gross = forward + reverse
        significant = gross >= MIN_FACE_VOLUME_M3
        active = np.flatnonzero(significant)
        signs = np.sign(net[active])
        signs = signs[signs != 0]
        switches = int(np.count_nonzero(signs[1:] != signs[:-1]))
        total_net = float(net.sum())
        direction = int(np.sign(total_net))
        late_net = float(net[late_start:].sum())
        late_ref_net = float(ref_net[late_start:].sum())
        late_abs = float(np.abs(net[late_start:]).sum())
        late_consistency = max(0., direction * late_net / late_abs) if late_abs else 0.
        significant_pair = np.maximum(gross, other["face_forward_m3"][:, face_index] + other["face_reverse_m3"][:, face_index]) >= MIN_FACE_VOLUME_M3
        interval_error = float(np.abs(net[significant_pair] - ref_net[significant_pair]).sum())
        interval_scale = float(np.abs(ref_net[significant_pair]).sum())
        relative_error = interval_error / max(interval_scale, MIN_FACE_VOLUME_M3)
        interval_relative_error = float(np.max(np.abs(net[significant_pair] - ref_net[significant_pair]) /
                                               np.maximum(np.abs(ref_net[significant_pair]), MIN_FACE_VOLUME_M3))) if significant_pair.any() else 0.
        stable = bool(active.size and direction and switches == 0 and
                      float(gross.sum()) >= MIN_FACE_VOLUME_M3 and
                      direction * total_net >= (1 - RELATIVE_TOLERANCE) * float(gross.sum()) and
                      direction * late_net >= MIN_FACE_VOLUME_M3 and
                      direction * late_ref_net >= MIN_FACE_VOLUME_M3 and
                      late_consistency >= 1 - RELATIVE_TOLERANCE and
                      relative_error <= RELATIVE_TOLERANCE and
                      interval_relative_error <= RELATIVE_TOLERANCE and
                      np.all(np.sign(net[significant_pair]) == np.sign(ref_net[significant_pair])))
        faces.append({"face_id": face["face_id"], "face_index": face_index,
                      "hierarchy_face_index": hierarchy_index, "cell_ids": cells,
                      "cell_owner_leaf_ids": cell_owners, "leaf_ids": face["leaf_ids"],
                      "endpoints_xyz_m": endpoints,
                      "face_center_xyz_m": [(first + second) / 2 for first, second in zip(*endpoints)],
                      "width_m": spacing, "spacing_m": spacing,
                      "coverage": "pinned original-bed D4 face; endpoints valid and unprotected",
                      "sill_m": face["sill_m"], "first_active_interval": int(active[0]) if active.size else None,
                      "last_active_interval": int(active[-1]) if active.size else None,
                      "forward_m3": float(forward.sum()), "reverse_m3": float(reverse.sum()),
                      "net_m3": total_net, "gross_m3": float(gross.sum()),
                      "canceled_m3": float(2 * min(forward.sum(), reverse.sum())),
                      "active_interval_sign_switches": switches, "late_start_interval": late_start,
                      "late_net_m3": late_net, "late_direction_consistency": late_consistency,
                      "interval_net_relative_l1_difference": relative_error,
                      "max_interval_net_relative_difference": interval_relative_error,
                      "stable_relationship": stable,
                      "receiver_leaf_id": face["leaf_ids"][1 if direction > 0 else 0] if stable else None,
                      "source_leaf_id": face["leaf_ids"][0 if direction > 0 else 1] if stable else None})
    basins = []
    incoming, outgoing, exports, residual = ledgers
    parameters = metadata["parameters"]
    for index, leaf in enumerate(leaves):
        rain_input = arrays["rain_mm_h"] * parameters["runoff_coefficient"] / 3_600_000. * topology["arrays"]["leaf_area_m2"][index] * metadata["timestep_s"]
        baseflow_input = np.full(steps, parameters["baseflow_mm_per_day"] / 86_400_000. * topology["arrays"]["leaf_area_m2"][index] * metadata["timestep_s"])
        basins.append({"leaf_id": leaf, "rain_input_m3": rain_input.tolist(),
                       "baseflow_input_m3": baseflow_input.tolist(),
                       "face_in_m3": incoming[:, index].tolist(),
                       "face_out_m3": outgoing[:, index].tolist(),
                       "external_export_m3": exports[:, index].tolist(),
                       "inventory_m3": arrays["volume_m3"][:, index].tolist(),
                       "inventory_residual_m3": residual[:, index].tolist()})
    result = {"schema": SCHEMA, "topology_identity_sha256": topology["identity_sha256"],
              "hierarchy_identity_sha256": hierarchy["identity_sha256"],
              "event_identity_sha256": event["identity_sha256"],
              "reference_event_identity_sha256": reference_event["identity_sha256"],
              "thresholds": {"minimum_diagnostic_face_volume_m3": MIN_FACE_VOLUME_M3,
                             "interval_net_relative_l1": RELATIVE_TOLERANCE,
                             "inventory_residual_m3": LEDGER_TOLERANCE_M3},
              "faces": faces, "basins": basins, "saved_interval_count": steps,
              "basin_series_semantics": "each basin column covers saved intervals 0..steps-1; inventory_m3 covers boundaries 0..steps",
              "max_abs_inventory_residual_m3": float(np.max(np.abs(residual))),
              "relationship_semantics": "event-dependent shared-face reception; cycles allowed; no permanent river or backwater certification",
              "publishable": False, "natural_outlet_verified": False, "hydraulic_ready": False,
              "continuous_fine_corridor_ready": False}
    result["identity_sha256"] = _sha(result)
    return result


def load_basin_reception(path, *, expected_sha256, expected_identity):
    from pathlib import Path
    from terrain_pipeline.mountain_source_adapter import file_sha256

    path = Path(path)
    if path.stat().st_size >= 128 * 1024**2 or file_sha256(path) != expected_sha256:
        raise ValueError("reception file budget/hash mismatch")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate reception key")
            result[key] = value
        return result
    record = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite reception JSON")))
    return validate_basin_reception(record, expected_identity=expected_identity)


def validate_basin_reception(record, *, expected_identity):
    record = dict(record)
    digest = record.pop("identity_sha256", None)
    if record.get("schema") != SCHEMA or digest != expected_identity or _sha(record) != digest:
        raise ValueError("reception identity/schema mismatch")
    for flag in ("publishable", "natural_outlet_verified", "hydraulic_ready", "continuous_fine_corridor_ready"):
        if record.get(flag) is not False:
            raise ValueError("reception cannot certify hydraulic or publishing readiness")
    thresholds = record.get("thresholds", {})
    if thresholds != {"minimum_diagnostic_face_volume_m3": MIN_FACE_VOLUME_M3,
                      "interval_net_relative_l1": RELATIVE_TOLERANCE,
                      "inventory_residual_m3": LEDGER_TOLERANCE_M3}:
        raise ValueError("reception thresholds mismatch")
    steps = record.get("saved_interval_count")
    if type(steps) is not int or steps < 1 or not isinstance(record.get("faces"), list) or not isinstance(record.get("basins"), list):
        raise ValueError("reception shape mismatch")
    fields = ("rain_input_m3", "baseflow_input_m3", "face_in_m3", "face_out_m3",
              "external_export_m3", "inventory_residual_m3")
    for basin in record["basins"]:
        if any(not isinstance(basin.get(field), list) or len(basin[field]) != steps for field in fields):
            raise ValueError("reception basin series shape mismatch")
        if not isinstance(basin.get("inventory_m3"), list) or len(basin["inventory_m3"]) != steps + 1:
            raise ValueError("reception inventory series shape mismatch")
        if any(not np.isfinite(basin[field]).all() for field in (*fields, "inventory_m3")):
            raise ValueError("nonfinite reception basin series")
        if any(np.any(np.asarray(basin[field]) < 0.) for field in (*fields[:-1], "inventory_m3")):
            raise ValueError("negative reception inventory or directional series")
        residual = (np.asarray(basin["rain_input_m3"]) + np.asarray(basin["baseflow_input_m3"])
                    + np.asarray(basin["face_in_m3"]) - np.asarray(basin["face_out_m3"])
                    - np.asarray(basin["external_export_m3"]) - np.diff(basin["inventory_m3"]))
        if (np.max(np.abs(residual)) > LEDGER_TOLERANCE_M3 or
                not np.allclose(residual, basin["inventory_residual_m3"], rtol=0, atol=1e-9)):
            raise ValueError("reception reconstructed inventory closure failed")
        if np.max(np.abs(basin["inventory_residual_m3"])) > LEDGER_TOLERANCE_M3:
            raise ValueError("reception inventory residual mismatch")
    if not np.isfinite(record.get("max_abs_inventory_residual_m3", float("nan"))) or record["max_abs_inventory_residual_m3"] > LEDGER_TOLERANCE_M3:
        raise ValueError("reception inventory summary mismatch")
    for face in record["faces"]:
        if (not isinstance(face.get("endpoints_xyz_m"), list) or len(face["endpoints_xyz_m"]) != 2 or
                any(len(point) != 3 or not np.isfinite(point).all() for point in face["endpoints_xyz_m"]) or
                not isinstance(face.get("face_center_xyz_m"), list) or len(face["face_center_xyz_m"]) != 3 or
                not np.isfinite(face["face_center_xyz_m"]).all() or
                not all(np.isfinite(face.get(key, float("nan"))) for key in
                        ("width_m", "spacing_m", "sill_m", "forward_m3", "reverse_m3", "net_m3", "gross_m3",
                         "canceled_m3", "late_net_m3", "late_direction_consistency",
                         "interval_net_relative_l1_difference", "max_interval_net_relative_difference"))):
            raise ValueError("reception face shape or finite mismatch")
        forward, reverse = face["forward_m3"], face["reverse_m3"]
        if (forward < 0. or reverse < 0. or face["width_m"] <= 0. or face["spacing_m"] <= 0. or
                not np.isclose(face["net_m3"], forward - reverse, rtol=0, atol=1e-7) or
                not np.isclose(face["gross_m3"], forward + reverse, rtol=0, atol=1e-7) or
                not np.isclose(face["canceled_m3"], 2 * min(forward, reverse), rtol=0, atol=1e-7)):
            raise ValueError("reception directional totals mismatch")
    record["identity_sha256"] = digest
    return record
