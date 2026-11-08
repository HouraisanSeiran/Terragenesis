"""Replayable fine-grid preparation gate for a smoothed channel graph."""

from collections import deque
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np
from numpy.lib import format as npy_format

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest
from terrain_pipeline.channel_centerline import SmoothingRecipe, build_centerline, validate_centerline_for_plan
from terrain_pipeline.channel_inundation import InundationRecipe, evaluate_inundation
from terrain_pipeline.channel_joint import assess_joint
from terrain_pipeline.channel_stage import StageRecipe, solve_stage
from terrain_pipeline.local_channel_sections import SectionRecipe, evaluate_sections
from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel
from terrain_pipeline.surface_network_prepare import SurfaceNetworkBudget


VERSION = "surface-centerline-prepare-v1"
MAX_FINE_NODES = 2_000_000
MAX_PACKAGE_BYTES = 1_000_000_000
MAX_ARCHIVE_MEMBERS = 100
MAX_GRAPH_NODES = 4096
MAX_EDGE_SAMPLES = 2_000_000
MAX_MANIFEST_BYTES = 1_000_000


def _readonly(value):
    return np.frombuffer(value.tobytes(order="C"), dtype=value.dtype).reshape(value.shape)


def _same(left, right):
    if {key: value for key, value in left.items() if key != "arrays"} != {
            key: value for key, value in right.items() if key != "arrays"}:
        return False
    return set(left["arrays"]) == set(right["arrays"]) and all(
        left["arrays"][name].dtype == right["arrays"][name].dtype and
        np.array_equal(left["arrays"][name], right["arrays"][name], equal_nan=True)
        for name in left["arrays"])


def _replay_plan(plan):
    if plan.get("status") != "diagnostic_not_publishable":
        raise ValueError("diagnostic plan required")
    params = plan["identity"]["parameters"]
    recipe = ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__})
    arrays = plan["arrays"]
    rebuilt = plan_channel(arrays["source_height_m"], arrays["receiver"], arrays["order"],
                           arrays["outlet_mask"], arrays["discharge_m3_s"],
                           params["spacing_x_m"], params["spacing_z_m"], params["origin_x_m"],
                           params["origin_z_m"], params["sea_level_elevation_m"],
                           params["source_identity"], recipe)
    if not _same(plan, rebuilt):
        raise ValueError("plan replay differs from supplied geometry")
    discharge = arrays["discharge_m3_s"].ravel()
    incoming = np.zeros(discharge.size)
    receiver = arrays["receiver"]
    routed = receiver >= 0
    np.add.at(incoming, receiver[routed], discharge[routed])
    donor_count = np.bincount(receiver[routed], minlength=discharge.size)
    roundoff = np.finfo(float).eps * np.maximum(discharge, incoming) * (donor_count + 1)
    if not np.isfinite(incoming).all() or np.any(incoming - discharge > roundoff):
        raise ValueError("discharge conservation requires nonnegative local inflow at every node")


def _replay_centerline(centerline, plan):
    validate_centerline_for_plan(centerline, plan)
    params = centerline["identity"]["parameters"]
    recipe = SmoothingRecipe(params["strength"], params["max_offset_m"], params["min_separation_m"])
    if not _same(centerline, build_centerline(plan, recipe)):
        raise ValueError("centerline replay differs from supplied geometry")


def _sample(field, x, z, origin_x, origin_z, spacing_x, spacing_z, masks=(),
            diagnostics=None, mask_names=()):
    fx = (x - origin_x) / spacing_x
    fz = (z - origin_z) / spacing_z
    if not (-1e-9 <= fx <= field.shape[1] - 1 + 1e-9 and
            -1e-9 <= fz <= field.shape[0] - 1 + 1e-9):
        if diagnostics is not None:
            diagnostics["outside_grid"] += 1
        return None, False
    fx = min(max(fx, 0.), field.shape[1] - 1)
    fz = min(max(fz, 0.), field.shape[0] - 1)
    x0, z0 = math.floor(fx), math.floor(fz)
    x1, z1 = min(x0 + 1, field.shape[1] - 1), min(z0 + 1, field.shape[0] - 1)
    tx, tz = fx - x0, fz - z0
    corners = ((z0, x0, (1 - tx) * (1 - tz)), (z0, x1, tx * (1 - tz)),
               (z1, x0, (1 - tx) * tz), (z1, x1, tx * tz))
    corners = [(row, col, weight) for row, col, weight in corners if weight > 0.]
    invalid = set()
    for row, col, weight in corners:
        if not math.isfinite(float(field[row, col])):
            invalid.add("unknown")
        for index, mask in enumerate(masks):
            if not mask[row, col]:
                invalid.add(mask_names[index] if mask_names else "mask")
    if invalid:
        if diagnostics is not None:
            for reason in invalid:
                diagnostics[reason] += 1
        return None, False
    return sum(float(field[row, col]) * weight for row, col, weight in corners), True


def _outlet_connected(wet, legal):
    visited = np.zeros(wet.shape, bool)
    queue = deque(map(tuple, np.argwhere(wet & legal)))
    for cell in queue:
        visited[cell] = True
    while queue:
        row, col = queue.popleft()
        for next_row, next_col in ((row - 1, col), (row + 1, col),
                                   (row, col - 1), (row, col + 1)):
            if (0 <= next_row < wet.shape[0] and 0 <= next_col < wet.shape[1] and
                    wet[next_row, next_col] and not visited[next_row, next_col]):
                visited[next_row, next_col] = True
                queue.append((next_row, next_col))
    return np.array_equal(visited, wet) and bool(np.any(wet & legal))


def _geometry_gate(plan, centerline, section, stage, flood, budget, stage_recipe):
    params = section["identity"]["parameters"]
    origin_x, origin_z = params["origin_x_m"], params["origin_z_m"]
    spacing_x, spacing_z = params["spacing_x_m"], params["spacing_z_m"]
    source = section["arrays"]["source_surface_m"]
    final = section["arrays"]["bounded_surface_m"]
    cut = source - final
    changed = cut > 1e-9
    weights = np.ones(final.shape)
    weights[[0, -1], :] *= .5
    weights[:, [0, -1]] *= .5
    area = float(np.sum(changed * weights) * spacing_x * spacing_z)
    volume = float(np.sum(cut * weights) * spacing_x * spacing_z)
    domain = flood["arrays"]["domain_mask"]
    protected = flood["arrays"]["protected_mask"]
    wet = flood["arrays"]["wet_mask"]
    water = flood["arrays"]["water_surface_m"]
    support_failures = {name: 0 for name in ("outside_grid", "domain", "protected", "unknown", "dry")}
    nodes = centerline["arrays"]["node_flat_index"]
    positions = centerline["arrays"]["node_world_xz_m"]
    lookup = {int(cell): index for index, cell in enumerate(nodes)}
    bed = plan["arrays"]["bounded_bed_m"].ravel()
    stages = stage["arrays"]["stage_m"].ravel()
    failures = {"bed_depth": bool(np.any(cut > budget.max_bed_cut_m + 1e-9)),
                "area": area > budget.max_area_m2 + 1e-9,
                "volume": volume > budget.max_cut_volume_m3 + 1e-9,
                "protected": bool(np.any(changed & protected)) or section["summary"]["protected_conflict_nodes"] > 0,
                "outside_domain_cut": bool(np.any(changed & ~domain)),
                "section": bool(section["summary"]["blocked_by_plan"] or
                                section["summary"]["blocked_by_centerline"] or
                                section["summary"]["local_budget_conflict_nodes"]),
                "stage_bed_mismatch": False, "edge_support": False,
                "edge_clearance": False, "edge_max_depth": False,
                "wet_outlet_connectivity": not _outlet_connected(wet, flood["arrays"]["legal_outlet_mask"])}
    max_bed_error = 0.
    max_edge_bed_error = 0.
    max_reconstruction_error = 0.
    edge_reverse_bed_observed = False
    sample_count = 0
    for index, cell in enumerate(nodes):
        x, z = positions[index]
        sampled, valid = _sample(final, x, z, origin_x, origin_z, spacing_x, spacing_z,
                                 (domain, ~protected), support_failures, ("domain", "protected"))
        if not valid:
            failures["edge_support"] = True
            continue
        max_bed_error = max(max_bed_error, abs(sampled - bed[cell]))
    failures["stage_bed_mismatch"] = bool(max_bed_error > budget.bed_match_tolerance_m)
    for donor, target in zip(centerline["arrays"]["edge_donor_flat_index"],
                             centerline["arrays"]["edge_target_flat_index"]):
        start, end = positions[lookup[int(donor)]], positions[lookup[int(target)]]
        steps = max(1, int(math.ceil(2 * max(abs(end[0] - start[0]) / spacing_x,
                                           abs(end[1] - start[1]) / spacing_z))))
        previous_bed = None
        for step in range(steps + 1):
            fraction = step / steps
            x, z = start + fraction * (end - start)
            stage_here = (1 - fraction) * stages[donor] + fraction * stages[target]
            actual_bed, bed_valid = _sample(final, x, z, origin_x, origin_z, spacing_x, spacing_z,
                                            (domain, ~protected), support_failures, ("domain", "protected"))
            actual_water, water_valid = _sample(water, x, z, origin_x, origin_z, spacing_x, spacing_z,
                                                (domain, ~protected, wet), support_failures,
                                                ("domain", "protected", "dry"))
            sample_count += 1
            if not bed_valid or not water_valid:
                failures["edge_support"] = True
                continue
            max_reconstruction_error = max(max_reconstruction_error, abs(actual_water - stage_here))
            ideal_bed = (1 - fraction) * bed[donor] + fraction * bed[target]
            max_edge_bed_error = max(max_edge_bed_error, abs(actual_bed - ideal_bed))
            if min(stage_here, actual_water) - actual_bed < stage_recipe.min_clearance_m - 1e-9:
                failures["edge_clearance"] = True
            if max(stage_here, actual_water) - actual_bed > stage_recipe.max_depth_m + 1e-9:
                failures["edge_max_depth"] = True
            if previous_bed is not None and actual_bed > previous_bed + 1e-9:
                edge_reverse_bed_observed = True
            previous_bed = actual_bed
    return failures, {"area_m2": area, "cut_volume_m3": volume,
                      "max_stage_bed_error_m": float(max_bed_error),
                      "max_edge_bed_error_m": float(max_edge_bed_error),
                      "support_failures": support_failures,
                      "max_water_reconstruction_error_m": float(max_reconstruction_error),
                      "edge_reverse_bed_observed": edge_reverse_bed_observed,
                      "edge_samples": sample_count}


def prepare_surface_centerline(plan, centerline, fine_origin_x_m, fine_origin_z_m,
                               fine_spacing_x_m, fine_spacing_z_m, fine_shape_zx,
                               domain_mask, protected_mask, legal_outlet_mask,
                               outlet_stage_m, section_recipe, stage_recipe,
                               inundation_recipe, budget: SurfaceNetworkBudget):
    if not isinstance(budget, SurfaceNetworkBudget):
        raise ValueError("surface network budget required")
    if (len(fine_shape_zx) != 2 or any(type(size) is not int or size < 2 for size in fine_shape_zx)
            or math.prod(fine_shape_zx) > MAX_FINE_NODES):
        raise ValueError("fine grid resource limit exceeded")
    if plan["arrays"]["source_height_m"].size > MAX_FINE_NODES:
        raise ValueError("plan grid resource limit exceeded")
    if np.count_nonzero(plan["arrays"]["channel_mask"]) > MAX_GRAPH_NODES:
        raise ValueError("active graph resource limit exceeded")
    if (any(isinstance(value, bool) or not math.isfinite(value)
            for value in (fine_origin_x_m, fine_origin_z_m, fine_spacing_x_m, fine_spacing_z_m)) or
            min(fine_spacing_x_m, fine_spacing_z_m) <= 0):
        raise ValueError("fine origin and spacing must be finite; spacing positive")
    for mask in (domain_mask, protected_mask, legal_outlet_mask):
        if np.asarray(mask).dtype != bool or np.asarray(mask).shape != tuple(fine_shape_zx):
            raise ValueError("fine masks must be boolean and match fine grid")
    _replay_plan(plan)
    _replay_centerline(centerline, plan)
    positions = centerline["arrays"]["node_world_xz_m"]
    lookup = {int(cell): index for index, cell in enumerate(centerline["arrays"]["node_flat_index"])}
    sample_count = 0
    for donor, target in zip(centerline["arrays"]["edge_donor_flat_index"],
                             centerline["arrays"]["edge_target_flat_index"]):
        delta = np.abs(positions[lookup[int(donor)]] - positions[lookup[int(target)]])
        span = 2 * max(delta[0] / fine_spacing_x_m, delta[1] / fine_spacing_z_m)
        if not math.isfinite(span) or span > MAX_EDGE_SAMPLES:
            raise ValueError("edge sampling resource limit exceeded")
        sample_count += max(1, math.ceil(span)) + 1
    if sample_count > MAX_EDGE_SAMPLES:
        raise ValueError("edge sampling resource limit exceeded")
    section = evaluate_sections(plan, fine_origin_x_m, fine_origin_z_m, fine_spacing_x_m,
                                fine_spacing_z_m, fine_shape_zx, protected_mask, section_recipe, centerline)
    stage = solve_stage(plan, outlet_stage_m, stage_recipe, centerline)
    flood = evaluate_inundation(plan, section, stage, domain_mask, protected_mask,
                                legal_outlet_mask, inundation_recipe, centerline)
    joint = assess_joint(plan, section, stage, flood)
    failures, metrics = _geometry_gate(plan, centerline, section, stage, flood, budget, stage_recipe)
    prepared = not any(failures.values()) and joint["pass"]
    summary = {"publishable": prepared, "budget_failures": failures,
               "joint_blockers": joint["blockers"], "section": section["summary"],
               "stage": stage["summary"], "inundation": flood["summary"], **metrics,
               "moved_nodes": centerline["summary"]["moved_nodes"]}
    summary["needs_finer_grid"] = bool(failures["stage_bed_mismatch"] or joint["blockers"]["resolution"])
    components = {"plan": plan, "centerline": centerline, "section": section,
                  "stage": stage, "flood": flood}
    inputs = {"domain_mask": np.asarray(domain_mask).copy(),
              "protected_mask": np.asarray(protected_mask).copy(),
              "legal_outlet_mask": np.asarray(legal_outlet_mask).copy(),
              "outlet_stage_m": np.asarray(outlet_stage_m, dtype=np.float64).copy()}
    arrays = {f"{group}__{name}": value.copy() for group, component in components.items()
              for name, value in component["arrays"].items()}
    arrays.update(inputs)
    identity = ArtifactIdentity("Terragenesis", "surface-centerline-prepare", VERSION, 0,
                                {"budget": asdict(budget),
                                 "component_sha256": {name: value["identity_sha256"] for name, value in components.items()},
                                 "joint_sha256": joint["identity_sha256"],
                                 "arrays_sha256": digest({name: array_hash(value) for name, value in arrays.items()}),
                                 "summary_sha256": digest(summary)})
    arrays = {name: _readonly(value) for name, value in arrays.items()}
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": "prepared" if prepared else "diagnostic_not_publishable",
            "components": {name: {key: value[key] for key in ("identity", "identity_sha256", "status", "summary") if key in value}
                           for name, value in components.items()},
            "arrays": arrays, "summary": summary}


def _validate(result, allow_diagnostic):
    if (len(result["arrays"]) >= MAX_ARCHIVE_MEMBERS or
            any(not isinstance(value, np.ndarray) or value.dtype.hasobject or
                value.size > MAX_FINE_NODES * 20 or value.nbytes > MAX_PACKAGE_BYTES
                for value in result["arrays"].values()) or
            sum(value.nbytes for value in result["arrays"].values()) > MAX_PACKAGE_BYTES):
        raise ValueError("package resource limit exceeded")
    identity = ArtifactIdentity(**result["identity"])
    if (identity.sha256 != result["identity_sha256"] or identity.algorithm != "surface-centerline-prepare" or
            identity.algorithm_version != VERSION):
        raise ValueError("invalid prepare identity")
    params = identity.record()["parameters"]
    if (digest({name: array_hash(value) for name, value in result["arrays"].items()}) != params["arrays_sha256"] or
            digest(result["summary"]) != params["summary_sha256"]):
        raise ValueError("prepare hashes disagree")
    components = {}
    for group in ("plan", "centerline", "section", "stage", "flood"):
        component = result["components"][group]
        components[group] = {**component, "arrays": {name.split("__", 1)[1]: value for name, value in result["arrays"].items()
                                                      if name.startswith(group + "__")}}
        if component["identity_sha256"] != params["component_sha256"][group]:
            raise ValueError("component identity mismatch")
    section_params = components["section"]["identity"]["parameters"]
    stage_params = components["stage"]["identity"]["parameters"]
    flood_params = components["flood"]["identity"]["parameters"]
    budget = SurfaceNetworkBudget(**params["budget"])
    if components["section"]["arrays"]["bounded_surface_m"].size > MAX_FINE_NODES:
        raise ValueError("fine grid resource limit exceeded")
    replayed = prepare_surface_centerline(
        components["plan"], components["centerline"],
        section_params["origin_x_m"], section_params["origin_z_m"],
        section_params["spacing_x_m"], section_params["spacing_z_m"],
        tuple(components["section"]["arrays"]["bounded_surface_m"].shape),
        result["arrays"]["domain_mask"], result["arrays"]["protected_mask"],
        result["arrays"]["legal_outlet_mask"], result["arrays"]["outlet_stage_m"],
        SectionRecipe(section_params["max_local_cut_m"], section_params["min_cells_across_width"]),
        StageRecipe(**{name: stage_params[name] for name in StageRecipe.__dataclass_fields__}),
        InundationRecipe(flood_params["min_water_depth_m"], flood_params["max_lateral_reach_m"]), budget)
    if (result["status"] != replayed["status"] or result["summary"] != replayed["summary"] or
            result["identity_sha256"] != replayed["identity_sha256"] or
            result["components"] != replayed["components"] or
            not _same(result, replayed)):
        raise ValueError("prepare replay differs from saved result")
    if result["status"] != "prepared" and not allow_diagnostic:
        raise ValueError("diagnostic package requires explicit opt-in")
    return replayed


def save_surface_centerline(result, path, allow_diagnostic=False):
    result = _validate(result, allow_diagnostic)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    manifest = {key: result[key] for key in ("identity", "identity_sha256", "status", "components", "summary")}
    manifest["format_version"] = 1
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, delete=False, suffix=".npz") as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(manifest, sort_keys=True), **result["arrays"])
        load_surface_centerline(temporary, allow_diagnostic=allow_diagnostic)
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_surface_centerline(path, allow_diagnostic=False):
    with open(path, "rb") as package:
        return _load_package(package, allow_diagnostic)


def _load_package(package, allow_diagnostic):
    with zipfile.ZipFile(package) as archive:
        members = archive.infolist()
        if (len(members) > MAX_ARCHIVE_MEMBERS or
                len({item.filename for item in members}) != len(members) or
                sum(item.file_size for item in members) > MAX_PACKAGE_BYTES or
                any(item.file_size > MAX_PACKAGE_BYTES or not item.filename.endswith(".npy") or
                    "/" in item.filename or "\\" in item.filename for item in members)):
            raise ValueError("package resource limit exceeded")
        if "manifest.npy" not in {item.filename for item in members}:
            raise ValueError("missing manifest")
        declared_bytes = 0
        for member in members:
            with archive.open(member) as stream:
                version = npy_format.read_magic(stream)
                if version == (1, 0):
                    shape, _, dtype = npy_format.read_array_header_1_0(stream)
                elif version == (2, 0):
                    shape, _, dtype = npy_format.read_array_header_2_0(stream)
                else:
                    raise ValueError("unsupported NPY version")
                elements = math.prod(shape)
                payload_bytes = elements * dtype.itemsize
                if (dtype.hasobject or dtype.itemsize <= 0 or len(shape) > 2 or
                        any(size < 0 for size in shape) or elements > MAX_FINE_NODES * 20 or
                        payload_bytes > MAX_PACKAGE_BYTES):
                    raise ValueError("NPY resource limit exceeded")
                if stream.tell() + payload_bytes != member.file_size:
                    raise ValueError("NPY declared bytes differ from member length")
                if member.filename == "manifest.npy":
                    if shape != () or dtype.kind != "U" or payload_bytes > MAX_MANIFEST_BYTES:
                        raise ValueError("invalid manifest NPY")
                elif dtype.kind not in "bifu":
                    raise ValueError("invalid numeric NPY dtype")
                declared_bytes += payload_bytes
        if declared_bytes > MAX_PACKAGE_BYTES:
            raise ValueError("NPY aggregate resource limit exceeded")
    package.seek(0)
    with np.load(package, allow_pickle=False) as archive:
        if "manifest" not in archive.files:
            raise ValueError("missing manifest")
        manifest = json.loads(str(archive["manifest"].item()))
        if manifest.pop("format_version") != 1:
            raise ValueError("unsupported package format")
        arrays = {name: archive[name].copy() for name in archive.files if name != "manifest"}
    return _validate({**manifest, "arrays": arrays}, allow_diagnostic)


def slice_surface_centerline(result, z_slice, x_slice):
    if result["status"] != "prepared":
        raise ValueError("only prepared surfaces can be sliced")
    shape = result["arrays"]["section__bounded_surface_m"].shape
    for selection, limit in ((z_slice, shape[0]), (x_slice, shape[1])):
        if (not isinstance(selection, slice) or selection.step not in (None, 1) or
                selection.start is None or selection.stop is None or
                not 0 <= selection.start < selection.stop <= limit):
            raise ValueError("bounded unit-step slices required")
    names = ("section__source_surface_m", "section__bounded_surface_m", "section__actual_cut_m",
             "flood__water_surface_m", "flood__wet_mask", "domain_mask", "protected_mask",
             "legal_outlet_mask")
    arrays = {name: result["arrays"][name][z_slice, x_slice] for name in names}
    for value in arrays.values():
        value.flags.writeable = False
    params = result["components"]["section"]["identity"]["parameters"]
    return {"origin_x_m": params["origin_x_m"] + x_slice.start * params["spacing_x_m"],
            "origin_z_m": params["origin_z_m"] + z_slice.start * params["spacing_z_m"],
            "spacing_x_m": params["spacing_x_m"], "spacing_z_m": params["spacing_z_m"],
            "source_identity_sha256": result["identity_sha256"], "arrays": arrays}
