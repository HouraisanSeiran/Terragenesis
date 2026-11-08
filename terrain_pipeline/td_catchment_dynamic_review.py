"""Exclusive catchment saved-frame accounts; no simulation or water interpolation."""

import json
import hashlib
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_topology import validate_basin_hierarchy as validate_basin_hierarchy
from terrain_pipeline.basin_storage import dispatch_load_storage as load_storage
from terrain_pipeline.td_surface_reaches import _storage_match, _plain, _freeze, _hash, _checked_surface_reaches
from terrain_pipeline.basin_topology import _read_json as _read_json

SCHEMA = "td-catchment-dynamic-review-v1"
MAX_PAGE_BYTES = 8 * 1024 * 1024
LEDGERS = ("rain_volume_m3", "soil_et_m3", "surface_et_m3", "boundary_outflow_m3", "internal_net_m3",
           "storage_change_m3", "balance_residual_m3", "lake_rain_m3", "land_rain_m3", "local_release_m3")


def _pages(hierarchy, storage, reaches=None):
    validate_basin_hierarchy(hierarchy)
    _storage_match(hierarchy, storage)
    arrays, water = hierarchy["arrays"], storage["arrays"]
    valid = arrays["valid_mask"].ravel()
    owners = arrays["contribution_owner"].ravel()[valid]
    leaf_ids, labels = np.unique(owners, return_inverse=True)
    count = len(leaf_ids)
    area = hierarchy["metadata"]["spacing_m"] ** 2
    bed = arrays["height_m"].ravel()[valid]
    threshold = storage["metadata"]["parameters"]["wet_threshold_m"]
    if reaches is not None:
        expected = _checked_surface_reaches(hierarchy, threshold_area_m2=reaches["threshold_area_m2"],
            expected_hierarchy_identity=hierarchy["identity_sha256"], storage=storage, expected_storage_identity=storage["identity_sha256"])
        if _plain(expected) != _plain(reaches):
            raise ValueError("dynamic reach input semantic mismatch")

    def aggregate(values):
        return np.bincount(labels, weights=values, minlength=count)

    previous = None
    previous_stores = None
    initial_domain = None
    cumulative_rain = 0.
    cumulative_losses = 0.
    for frame in range(len(water["depth_m"])):
        depth = water["depth_m"][frame, valid]
        wet = depth > threshold
        surface = bed + depth
        minima = np.full(count, np.inf)
        maxima = np.full(count, -np.inf)
        np.minimum.at(minima, labels[wet], surface[wet])
        np.maximum.at(maxima, labels[wet], surface[wet])
        fields = {"surface_volume_m3": aggregate(depth * area),
                  **{name.replace("_mm", "_volume_m3"): aggregate(water[name][frame, valid] * area / 1000)
                     for name in ("soil_mm", "fast_mm", "slow_mm")},
                  "wet_count": np.bincount(labels[wet], minlength=count).astype(int)}
        total = sum(fields[name] for name in ("surface_volume_m3", "soil_volume_m3", "fast_volume_m3", "slow_volume_m3"))
        cell_stores = depth + sum(water[name][frame, valid] for name in ("soil_mm", "fast_mm", "slow_mm")) / 1000
        cell_total = area * cell_stores
        interval = None
        if frame:
            interval = {name: aggregate(water[name][frame - 1, valid]) for name in LEDGERS}
            residual = interval["rain_volume_m3"] + interval["internal_net_m3"] - interval["soil_et_m3"] - interval["surface_et_m3"] - interval["boundary_outflow_m3"] - (total - previous)
            leaf_allowed = 1e-6 + 1e-10 * (abs(total) + abs(previous))
        else:
            initial_domain = math.fsum(cell_stores) * area
        records = [{"leaf_id": int(node), **{name: int(values[index]) if name == "wet_count" else float(values[index]) for name, values in fields.items()},
                    "total_water_volume_m3": float(total[index]),
                    "water_surface_min_m": float(minima[index]) if np.isfinite(minima[index]) else None,
                    "water_surface_max_m": float(maxima[index]) if np.isfinite(maxima[index]) else None,
                    "interval_budget": None if interval is None else {"residual_m3": float(residual[index]), "allowed_m3": float(leaf_allowed[index]), "passed": bool(abs(residual[index]) <= leaf_allowed[index])},
                    "interval_ledger_m3": None if interval is None else {name: float(values[index]) for name, values in interval.items()}}
                   for index, node in enumerate(leaf_ids)]
        native_reaches = None if reaches is None else [{"reach_id": reach["reach_id"], "cell_ids": list(reach["cell_ids"]),
            "bed_plus_depth_m": [float(arrays["height_m"].ravel()[cell] + water["depth_m"][frame, cell]) for cell in reach["cell_ids"]],
            "wet": [bool(water["depth_m"][frame, cell] > threshold) for cell in reach["cell_ids"]]} for reach in reaches["reaches"]]
        totals = {name: float(values.sum()) for name, values in fields.items()}
        totals["total_water_volume_m3"] = float(total.sum())
        interval_diagnostic = None
        if interval is not None:
            rain_sum = math.fsum((water["rain_mm_h"][frame - 1, valid] * (storage["metadata"]["dt_s"] / 3600) * area / 1000).tolist())
            loss_sum = math.fsum((water["soil_et_m3"][frame - 1, valid] + water["surface_et_m3"][frame - 1, valid]).tolist())
            boundary_sum = math.fsum(water["boundary_outflow_m3"][frame - 1, valid].tolist())
            change_sum = math.fsum(((cell_stores - previous_stores) * area).tolist())
            interval_residual = rain_sum - loss_sum - boundary_sum - change_sum
            expected_rain = loss_sum + boundary_sum + change_sum
            gate_difference = rain_sum - expected_rain
            interval_allowed = 1e-6 + abs(expected_rain) * 1e-10
            interval_diagnostic = {"residual_m3": interval_residual, "gate_difference_m3": gate_difference, "allowed_m3": interval_allowed, "passed": abs(gate_difference) <= interval_allowed,
                                   "rain_m3": rain_sum, "loss_m3": loss_sum, "external_m3": boundary_sum,
                                   "actual_state_change_m3": change_sum, "change_basis": "diff(depth+(soil+fast+slow)/1000)*area; never saved storage_change"}
            cumulative_rain += rain_sum
            cumulative_losses += loss_sum + boundary_sum
        whole_residual = math.fsum([initial_domain, cumulative_rain, -cumulative_losses, -(math.fsum(cell_stores) * area)])
        budget = 1e-6 + cumulative_rain * 1e-10
        yield {"frame_index": frame, "time_s": frame * storage["metadata"]["dt_s"],
               "interval_s": None if frame == 0 else [(frame - 1) * storage["metadata"]["dt_s"], frame * storage["metadata"]["dt_s"]],
               "leaves": records, "domain_totals": totals,
               "domain_interval_ledger_m3": None if interval is None else {name: float(values.sum()) for name, values in interval.items()},
               "budget_diagnostic": {"audit_budget_passed": abs(whole_residual) <= budget and (interval_diagnostic is None or interval_diagnostic["passed"]),
                    "whole_interval": interval_diagnostic, "cumulative_budget_passed": abs(whole_residual) <= budget,
                    "whole_run_residual_m3": whole_residual, "whole_run_tolerance_m3": budget,
                    "cumulative_rain_m3": cumulative_rain,
                    "max_leaf_interval_residual_m3": 0. if interval is None else float(abs(residual).max(initial=0)),
                    "leaf_interval_rule": "1e-6+1e-10*(abs(current_inventory)+abs(previous_inventory))",
                    "leaf_interval_budget_passed": interval is None or bool(np.all(abs(residual) <= leaf_allowed))},
               "native_reach_vertices": native_reaches}
        previous = total
        previous_stores = cell_stores


def _index(hierarchy, storage, inputs, pages, reaches=None, escape_record=None):
    from terrain_pipeline.basin_topology import _leaf_graph as _leaf_graph
    leaf_nodes = _leaf_graph(hierarchy, None)["leaf_nodes"]
    result = {"schema": SCHEMA, "algorithm": "exclusive-contribution-owner-saved-frame-bincount-v1", "inputs": inputs,
              "storage_version": {name: storage["metadata"].get(name) for name in ("algorithm", "work_profile", "dt_s", "substep_s")},
              "hierarchy_identity_sha256": hierarchy["identity_sha256"], "storage_identity_sha256": storage["identity_sha256"],
              "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
              "grid": {"shape_zx": list(hierarchy["arrays"]["height_m"].shape), "spacing_m": hierarchy["metadata"]["spacing_m"], "origin_m_xz": hierarchy["metadata"]["origin_m_xz"]},
              "pages": pages, "reach_identity_sha256": None if reaches is None else reaches["identity_sha256"], "optional_escape_record": escape_record,
              "leaf_nodes": leaf_nodes,
              "budget_acceptance": {"audit_budget_passed": all(pin["budget_diagnostic"]["audit_budget_passed"] for pin in pages),
                   "leaf_interval_budget_passed": all(pin["budget_diagnostic"]["leaf_interval_budget_passed"] for pin in pages),
                   "scope": "all audit_storage-definition fsum intervals AND cumulative must pass; interval actual change=diff(states)*area, allowed=1e-6+abs(loss+outflow+actual_change)*1e-10; cumulative allowed=1e-6+cumulative_rain*1e-10; no dynamic/refinement certification"},
              "flags": {"readonly": True, "hydraulic_ready": False, "transient_converged": False, "publishable": False,
                        "natural_outlet_verified": False, "water_generated": False, "water_interpolation": False},
              "semantics": "Actual saved-frame exclusive catchment inventories. Surface min/max only over wet cells; no common stage imposed. Frame0 has no preceding interval. Interval ledger volumes use actual dt, not inferred Q. Bed+depth native reach vertices with wet mask are samples, not width, channel or continuous water mesh. No per-hour face volume or spill onset reconstructed from whole-run face totals. Optional escape is external potential threshold/hypothetical capacity, never actual water. Different algorithm versions remain separate cases."}
    result["identity_sha256"] = _hash(result)
    return result


def _load_inputs(records):
    if set(records) != {"hierarchy", "storage"}:
        raise ValueError("explicit hierarchy/storage records required")
    for record in records.values():
        if set(record) != {"path", "expected_sha256", "expected_identity"}:
            raise ValueError("input requires path and both pins")
    hierarchy = load_basin_hierarchy(**records["hierarchy"])
    storage = load_storage(**records["storage"])
    _storage_match(hierarchy, storage)
    return hierarchy, storage


def export_catchment_dynamic_review(records, directory, *, reaches=None, escape_record=None):
    hierarchy, storage = _load_inputs(records)
    directory = Path(directory)
    if directory.exists():
        raise FileExistsError(directory)
    if escape_record is not None:
        from terrain_pipeline.basin_topology import load_basin_escape_plan as load_basin_escape_plan
        from terrain_pipeline.basin_topology import _leaf_graph as _leaf_graph
        load_basin_escape_plan(**escape_record, hierarchy=hierarchy, contribution_leaf_graph=_leaf_graph(hierarchy, None))
    pages = []
    for page in _pages(hierarchy, storage, reaches):
        payload = json.dumps(page, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(payload) > MAX_PAGE_BYTES:
            raise ValueError("dynamic page allocation budget exceeded")
        name = f"frame-{page['frame_index']:04d}.json"
        publish_bytes(directory / name, payload)
        pages.append({"file": name, "expected_sha256": file_sha256(directory / name), "expected_identity": _hash(page),
                      "bytes": len(payload), "frame_index": page["frame_index"], "time_s": page["time_s"], "budget_diagnostic": page["budget_diagnostic"]})
    index = _index(hierarchy, storage, records, pages, reaches, escape_record)
    payload = json.dumps(index, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = hashlib.sha256(payload).hexdigest()
    publish_bytes(directory / "pins.json", json.dumps({"index.json": digest, "expected_identity": index["identity_sha256"]}).encode())
    publish_bytes(directory / "index.json", payload)
    return _freeze(index)


def load_catchment_dynamic_review(path, *, expected_sha256, expected_identity, records, reaches=None, escape_record=None):
    path = Path(path)
    if path.stat().st_size > MAX_PAGE_BYTES or file_sha256(path) != expected_sha256:
        raise ValueError("dynamic index external hash/budget mismatch")
    result = _read_json(path)
    digest = result.pop("identity_sha256")
    if digest != expected_identity or _hash(result) != digest:
        raise ValueError("dynamic external identity mismatch")
    hierarchy, storage = _load_inputs(records)
    if escape_record is not None:
        from terrain_pipeline.basin_topology import load_basin_escape_plan as load_basin_escape_plan
        from terrain_pipeline.basin_topology import _leaf_graph as _leaf_graph
        load_basin_escape_plan(**escape_record, hierarchy=hierarchy, contribution_leaf_graph=_leaf_graph(hierarchy, None))
    pages = result["pages"]
    if len(pages) != len(storage["arrays"]["depth_m"]) or {entry.name for entry in path.parent.glob("frame-*.json")} != {pin["file"] for pin in pages}:
        raise ValueError("dynamic frame coverage mismatch")
    for index, (pin, expected) in enumerate(zip(pages, _pages(hierarchy, storage, reaches))):
        if pin["file"] != f"frame-{index:04d}.json" or pin["frame_index"] != index or pin["time_s"] != expected["time_s"]:
            raise ValueError("unsafe dynamic page/time mismatch")
        page_path = path.parent / pin["file"]
        if page_path.is_symlink() or page_path.resolve().parent != path.parent.resolve() or page_path.stat().st_size != pin["bytes"] or pin["bytes"] > MAX_PAGE_BYTES or file_sha256(page_path) != pin["expected_sha256"]:
            raise ValueError("dynamic page pin/budget/path mismatch")
        actual = _read_json(page_path)
        if actual != expected or _hash(actual) != pin["expected_identity"] or pin["budget_diagnostic"] != expected["budget_diagnostic"]:
            raise ValueError("dynamic page time/coverage/ledger semantics mismatch")
    expected_index = _index(hierarchy, storage, records, pages, reaches, escape_record)
    if expected_index["identity_sha256"] != digest:
        raise ValueError("dynamic index input/version/semantics mismatch")
    result["identity_sha256"] = digest
    return _freeze(result)
