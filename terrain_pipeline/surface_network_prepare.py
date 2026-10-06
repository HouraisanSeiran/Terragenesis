"""Explicit fixed-route surface-network preparation and publication gate."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile
from collections import deque

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest
from terrain_pipeline.channel_inundation import evaluate_inundation
from terrain_pipeline.channel_joint import assess_joint
from terrain_pipeline.channel_stage import solve_stage
from terrain_pipeline.local_channel_sections import evaluate_sections


VERSION = "surface-network-prepare-v2"


@dataclass(frozen=True)
class SurfaceNetworkBudget:
    max_bed_cut_m: float
    max_area_m2: float
    max_cut_volume_m3: float
    bed_match_tolerance_m: float = 1e-6

    def __post_init__(self):
        if any(isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in asdict(self).values()):
            raise ValueError("budget values must be finite and nonnegative")


def prepare_surface_network(plan, fine_origin_x_m, fine_origin_z_m, fine_spacing_x_m,
                            fine_spacing_z_m, fine_shape_zx, domain_mask, protected_mask,
                            legal_outlet_mask, outlet_stage_m, section_recipe, stage_recipe,
                            inundation_recipe, budget: SurfaceNetworkBudget):
    """Cut one fixed route and run all joint diagnostics on the resulting surface."""
    if not isinstance(budget, SurfaceNetworkBudget):
        raise ValueError("surface network budget required")
    section = evaluate_sections(plan, fine_origin_x_m, fine_origin_z_m, fine_spacing_x_m,
                                fine_spacing_z_m, fine_shape_zx, protected_mask, section_recipe)
    arrays = section["arrays"]
    source = arrays["source_surface_m"]
    final = arrays["bounded_surface_m"]
    bed_cut = source - final
    changed = bed_cut > 1e-9
    weights = np.ones(final.shape)
    weights[[0, -1], :] *= .5
    weights[:, [0, -1]] *= .5
    area_m2 = float(np.sum(changed * weights) * fine_spacing_x_m * fine_spacing_z_m)
    volume_m3 = float(np.sum(bed_cut * weights) * fine_spacing_x_m * fine_spacing_z_m)
    budget_failures = {
        "bed_depth": bool(np.any(bed_cut > budget.max_bed_cut_m + 1e-9)),
        "area": area_m2 > budget.max_area_m2 + 1e-9,
        "volume": volume_m3 > budget.max_cut_volume_m3 + 1e-9,
        "protected": bool(np.any(changed & protected_mask)) or section["summary"]["protected_conflict_nodes"] > 0,
        "section": bool(section["summary"]["blocked_by_plan"] or section["summary"]["local_budget_conflict_nodes"]),
        "outside_domain_cut": bool(np.any(changed & ~np.asarray(domain_mask))),
    }
    plan_arrays = plan["arrays"]
    params = plan["identity"]["parameters"]
    z, x = np.nonzero(plan_arrays["channel_mask"])
    fx = (params["origin_x_m"] + x * params["spacing_x_m"] - fine_origin_x_m) / fine_spacing_x_m
    fz = (params["origin_z_m"] + z * params["spacing_z_m"] - fine_origin_z_m) / fine_spacing_z_m
    ix, iz = np.rint(fx).astype(int), np.rint(fz).astype(int)
    aligned = (np.allclose(fx, ix, atol=1e-8, rtol=0) and np.allclose(fz, iz, atol=1e-8, rtol=0) and
               np.all((ix >= 0) & (ix < final.shape[1]) & (iz >= 0) & (iz < final.shape[0])))
    bed_error = float(np.max(np.abs(final[iz, ix] - plan_arrays["bounded_bed_m"][z, x]))) if aligned and len(z) else None
    budget_failures["stage_bed_mismatch"] = bed_error is None or bed_error > budget.bed_match_tolerance_m
    stage = solve_stage(plan, outlet_stage_m, stage_recipe)
    edge_failure = False
    edge_depth_failure = False
    edge_slope_failure = False
    if aligned:
        receiver = plan_arrays["receiver"]
        for donor in np.flatnonzero(plan_arrays["channel_mask"].ravel() & (receiver >= 0)):
            target = int(receiver[donor])
            if not plan_arrays["channel_mask"].flat[target]: continue
            a = (int(np.rint((params["origin_z_m"] + (donor // plan_arrays["channel_mask"].shape[1]) * params["spacing_z_m"] - fine_origin_z_m) / fine_spacing_z_m)),
                 int(np.rint((params["origin_x_m"] + (donor % plan_arrays["channel_mask"].shape[1]) * params["spacing_x_m"] - fine_origin_x_m) / fine_spacing_x_m)))
            b = (int(np.rint((params["origin_z_m"] + (target // plan_arrays["channel_mask"].shape[1]) * params["spacing_z_m"] - fine_origin_z_m) / fine_spacing_z_m)),
                 int(np.rint((params["origin_x_m"] + (target % plan_arrays["channel_mask"].shape[1]) * params["spacing_x_m"] - fine_origin_x_m) / fine_spacing_x_m)))
            steps = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
            if steps == 0: edge_failure = True; break
            upstream, downstream = stage["arrays"]["stage_m"].flat[[donor, target]]
            previous_bed = None
            for step in range(steps + 1):
                fraction = step / steps
                cell = (round(a[0] + fraction * (b[0] - a[0])), round(a[1] + fraction * (b[1] - a[1])))
                stage_here = upstream + fraction * (downstream - upstream)
                if (not (0 <= cell[0] < final.shape[0] and 0 <= cell[1] < final.shape[1]) or
                        stage_here - final[cell] < stage_recipe.min_clearance_m - 1e-9):
                    edge_failure = True; break
                if stage_here - final[cell] > stage_recipe.max_depth_m + 1e-9:
                    edge_depth_failure = True
                if previous_bed is not None and final[cell] > previous_bed + 1e-9:
                    edge_slope_failure = True
                previous_bed = final[cell]
            if edge_failure: break
    budget_failures["edge_clearance"] = edge_failure or not aligned
    budget_failures["edge_max_depth"] = edge_depth_failure or not aligned
    flood = evaluate_inundation(plan, section, stage, domain_mask, protected_mask,
                                legal_outlet_mask, inundation_recipe)
    joint = assess_joint(plan, section, stage, flood)
    publishable = not any(budget_failures.values()) and joint["pass"]
    outputs = {"source_surface_m": source.copy(), "final_surface_m": final.copy(),
               "bed_cut_m": bed_cut.copy(), "water_surface_m": flood["arrays"]["water_surface_m"].copy(),
               "wet_mask": flood["arrays"]["wet_mask"].copy(),
               "channel_seed_mask": flood["arrays"]["channel_seed_mask"].copy(),
               "disconnected_seed_mask": flood["arrays"]["disconnected_seed_mask"].copy(),
               "boundary_contact_mask": flood["arrays"]["boundary_contact_mask"].copy(),
               "reach_limited_mask": flood["arrays"]["reach_limited_mask"].copy(),
               "domain_mask": flood["arrays"]["domain_mask"].copy(),
               "protected_mask": flood["arrays"]["protected_mask"].copy(),
               "legal_outlet_mask": flood["arrays"]["legal_outlet_mask"].copy()}
    for value in outputs.values(): value.flags.writeable = False
    summary = {"publishable": publishable, "area_m2": area_m2,
               "cut_volume_m3": volume_m3, "max_stage_bed_error_m": bed_error,
               "valley_cut_m3": 0.0, "budget_failures": budget_failures,
               "joint_blockers": joint["blockers"], "section": section["summary"],
               "stage": stage["summary"], "inundation": flood["summary"],
               "edge_reverse_bed_observed": edge_slope_failure}
    identity = ArtifactIdentity("Terragenesis", "surface-network-prepare", VERSION, 0,
                                {**asdict(budget), "plan_sha256": plan["identity_sha256"],
                                 "section_sha256": section["identity_sha256"],
                                 "stage_sha256": stage["identity_sha256"],
                                 "flood_sha256": flood["identity_sha256"],
                                 "joint_sha256": joint["identity_sha256"],
                                 "fine_origin_x_m": float(fine_origin_x_m), "fine_origin_z_m": float(fine_origin_z_m),
                                 "fine_spacing_x_m": float(fine_spacing_x_m), "fine_spacing_z_m": float(fine_spacing_z_m),
                                 "sea_level_elevation_m": params["sea_level_elevation_m"],
                                 "fine_shape_zx": list(final.shape),
                                 "output_sha256": digest({name: array_hash(value) for name, value in outputs.items()}),
                                 "summary_sha256": digest(summary)})
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": "prepared" if publishable else "diagnostic_not_publishable",
            "arrays": outputs, "summary": summary}


def save_surface_network(result, path):
    if result.get("status") != "prepared":
        raise ValueError("only jointly accepted surface networks may be published")
    destination = Path(path)
    if destination.exists(): raise FileExistsError(destination)
    if not destination.parent.is_dir(): raise FileNotFoundError(destination.parent)
    manifest = {key: result[key] for key in ("identity", "identity_sha256", "status", "summary")}
    manifest["format_version"] = 2
    manifest["array_sha256"] = {name: array_hash(value) for name, value in result["arrays"].items()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, delete=False, suffix=".npz") as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(manifest, sort_keys=True), **result["arrays"])
        load_surface_network(temporary)
        os.link(temporary, destination)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
    return destination


def save_surface_network_diagnostic(result, path):
    """Persist a failed result for inspection, never as a publishable package."""
    if result.get("status") != "diagnostic_not_publishable":
        raise ValueError("diagnostic saver requires a failed result")
    destination = Path(path)
    if destination.exists(): raise FileExistsError(destination)
    if not destination.parent.is_dir(): raise FileNotFoundError(destination.parent)
    record = {"identity": result["identity"], "identity_sha256": result["identity_sha256"],
              "status": result["status"], "summary": result["summary"], "format_version": 2,
              "array_sha256": {name: array_hash(value) for name, value in result["arrays"].items()}}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, delete=False, suffix=".npz") as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(record, sort_keys=True), **result["arrays"])
        load_surface_network(temporary, allow_diagnostic=True)
        os.link(temporary, destination)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
    return destination


def load_surface_network(path, allow_diagnostic=False):
    expected = {"source_surface_m", "final_surface_m", "bed_cut_m", "water_surface_m", "wet_mask",
                "channel_seed_mask", "disconnected_seed_mask", "boundary_contact_mask", "reach_limited_mask",
                "domain_mask", "protected_mask", "legal_outlet_mask"}
    with np.load(path, allow_pickle=False) as archive:
        manifest = json.loads(str(archive["manifest"].item()))
        if set(archive.files) != expected | {"manifest"} or set(manifest["array_sha256"]) != expected:
            raise ValueError("invalid surface network arrays")
        arrays = {name: archive[name].copy() for name in expected}
    return _validate_surface_network_payload(manifest, arrays, allow_diagnostic)


def validate_surface_network(result, allow_diagnostic=False):
    """Apply the load-time geometry, budget and publication gates in memory."""
    try:
        manifest = {name: result[name] for name in ("identity", "identity_sha256", "status", "summary")}
        manifest["format_version"] = 2
        manifest["array_sha256"] = {name: array_hash(value) for name, value in result["arrays"].items()}
        return _validate_surface_network_payload(manifest, result["arrays"], allow_diagnostic)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("invalid surface network result") from error


def _validate_surface_network_payload(manifest, arrays, allow_diagnostic):
    expected = {"source_surface_m", "final_surface_m", "bed_cut_m", "water_surface_m", "wet_mask",
                "channel_seed_mask", "disconnected_seed_mask", "boundary_contact_mask", "reach_limited_mask",
                "domain_mask", "protected_mask", "legal_outlet_mask"}
    if set(arrays) != expected or set(manifest["array_sha256"]) != expected:
        raise ValueError("invalid surface network arrays")
    identity = ArtifactIdentity(**manifest["identity"])
    if (manifest["format_version"] != 2 or identity.algorithm != "surface-network-prepare" or
            identity.algorithm_version != VERSION or identity.sha256 != manifest["identity_sha256"] or
            any(array_hash(arrays[name]) != manifest["array_sha256"][name] for name in expected) or
            digest({name: array_hash(value) for name, value in arrays.items()}) != identity.record()["parameters"]["output_sha256"]):
        raise ValueError("surface network identity mismatch")
    shape = arrays["source_surface_m"].shape
    if (len(shape) != 2 or any(arrays[name].shape != shape for name in expected) or
            any(arrays[name].dtype != np.float64 for name in ("source_surface_m", "final_surface_m", "bed_cut_m", "water_surface_m")) or
            any(arrays[name].dtype != bool for name in expected - {"source_surface_m", "final_surface_m", "bed_cut_m", "water_surface_m"}) or
            any(not np.isfinite(arrays[name]).all() for name in ("source_surface_m", "final_surface_m", "bed_cut_m")) or
            not np.allclose(arrays["source_surface_m"] - arrays["final_surface_m"], arrays["bed_cut_m"], rtol=0, atol=1e-9)):
        raise ValueError("invalid surface network geometry")
    summary = manifest["summary"]
    if digest(summary) != identity.record()["parameters"]["summary_sha256"]:
        raise ValueError("surface network summary mismatch")
    params = identity.record()["parameters"]
    SurfaceNetworkBudget(**{name: params[name] for name in SurfaceNetworkBudget.__dataclass_fields__})
    if (params["fine_shape_zx"] != list(shape) or
            any(not math.isfinite(params[name]) for name in
                ("fine_origin_x_m", "fine_origin_z_m", "fine_spacing_x_m", "fine_spacing_z_m",
                 "sea_level_elevation_m")) or
            params["fine_spacing_x_m"] <= 0 or params["fine_spacing_z_m"] <= 0):
        raise ValueError("invalid surface network grid")
    wet = arrays["wet_mask"]
    water = arrays["water_surface_m"]
    if (not np.isfinite(water[wet]).all() or not np.isnan(water[~wet]).all() or
            np.any(water[wet] <= arrays["final_surface_m"][wet]) or
            np.any(arrays["bed_cut_m"] < -1e-9)):
        raise ValueError("invalid surface network water or cut")
    masks = {"wet_nodes": "wet_mask", "channel_seed_nodes": "channel_seed_mask",
             "disconnected_seed_nodes": "disconnected_seed_mask",
             "boundary_contact_nodes": "boundary_contact_mask",
             "reach_limited_nodes": "reach_limited_mask"}
    if (any(summary["inundation"][count] != int(np.count_nonzero(arrays[name]))
            for count, name in masks.items()) or
            not np.all(~wet | arrays["domain_mask"]) or
            np.any(wet & arrays["protected_mask"]) or
            np.any((arrays["bed_cut_m"] > 1e-9) & arrays["protected_mask"]) or
            not np.all(~arrays["channel_seed_mask"] | wet) or
            not np.all(~arrays["disconnected_seed_mask"] | arrays["channel_seed_mask"]) or
            summary["inundation"]["legal_outlet_wet"] != bool(np.any(wet & arrays["legal_outlet_mask"]))):
        raise ValueError("surface network wet masks disagree")
    visited = np.zeros(shape, bool)
    queue = deque(map(tuple, np.argwhere(wet & arrays["legal_outlet_mask"])))
    for cell in queue: visited[cell] = True
    while queue:
        z, x = queue.popleft()
        for nz, nx in ((z-1,x),(z+1,x),(z,x-1),(z,x+1)):
            if 0 <= nz < shape[0] and 0 <= nx < shape[1] and wet[nz,nx] and not visited[nz,nx]:
                visited[nz,nx] = True; queue.append((nz,nx))
    if manifest["status"] == "prepared" and not np.array_equal(visited, wet):
        raise ValueError("surface network has wet cells disconnected from outlet")
    weights = np.ones(shape)
    weights[[0, -1], :] *= .5
    weights[:, [0, -1]] *= .5
    cell_area = params["fine_spacing_x_m"] * params["fine_spacing_z_m"]
    area = float(np.sum((arrays["bed_cut_m"] > 1e-9) * weights) * cell_area)
    volume = float(np.sum(arrays["bed_cut_m"] * weights) * cell_area)
    if (not math.isclose(area, summary["area_m2"], abs_tol=1e-7) or
            not math.isclose(volume, summary["cut_volume_m3"], abs_tol=1e-7) or
            summary["budget_failures"]["area"] != (area > params["max_area_m2"] + 1e-9) or
            summary["budget_failures"]["volume"] != (volume > params["max_cut_volume_m3"] + 1e-9) or
            summary["budget_failures"]["bed_depth"] != bool(np.any(arrays["bed_cut_m"] > params["max_bed_cut_m"] + 1e-9))):
        raise ValueError("surface network budget summary mismatch")
    if (summary["budget_failures"]["outside_domain_cut"] != bool(np.any(
            (arrays["bed_cut_m"] > 1e-9) & ~arrays["domain_mask"])) or
            summary["publishable"] != (not any(summary["budget_failures"].values()) and
                                       not any(summary["joint_blockers"].values()))):
        raise ValueError("surface network gate mismatch")
    valid_status = (manifest["status"] == "prepared" and summary["publishable"] is True) or (
        allow_diagnostic and manifest["status"] == "diagnostic_not_publishable" and summary["publishable"] is False)
    if not valid_status:
        raise ValueError("surface network status mismatch")
    for value in arrays.values(): value.flags.writeable = False
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": manifest["status"], "arrays": arrays, "summary": summary}


def slice_surface_network(result, z_slice, x_slice):
    """Read a window from one prepared shared grid without rerouting or resampling."""
    if result["status"] != "prepared":
        raise ValueError("only prepared networks support read-only slices")
    shape = result["arrays"]["final_surface_m"].shape
    for item, limit in ((z_slice, shape[0]), (x_slice, shape[1])):
        if (not isinstance(item, slice) or item.step not in (None, 1) or
                item.start is None or item.stop is None or
                not (0 <= item.start < item.stop <= limit)):
            raise ValueError("slice must be a bounded unit-step window")
    params = result["identity"]["parameters"]
    arrays = {name: value[z_slice, x_slice] for name, value in result["arrays"].items()}
    for value in arrays.values(): value.flags.writeable = False
    return {"origin_x_m": params["fine_origin_x_m"] + x_slice.start * params["fine_spacing_x_m"],
            "origin_z_m": params["fine_origin_z_m"] + z_slice.start * params["fine_spacing_z_m"],
            "spacing_x_m": params["fine_spacing_x_m"], "spacing_z_m": params["fine_spacing_z_m"],
            "source_identity_sha256": result["identity_sha256"], "arrays": arrays}
