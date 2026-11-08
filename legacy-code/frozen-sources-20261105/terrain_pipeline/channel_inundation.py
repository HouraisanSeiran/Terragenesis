"""Full-grid, level-gated inundation from shared channel stages."""

from collections import deque
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile
import heapq

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash
from terrain_pipeline.artifacts.contracts import digest


VERSION = "channel-inundation-v1"


@dataclass(frozen=True)
class InundationRecipe:
    min_water_depth_m: float = .01
    max_lateral_reach_m: float = 30.

    def __post_init__(self):
        if (not math.isfinite(self.min_water_depth_m) or self.min_water_depth_m <= 0 or
                not math.isfinite(self.max_lateral_reach_m) or self.max_lateral_reach_m <= 0):
            raise ValueError("inundation depth and reach must be finite and positive")


def _shared_stage_fields(plan, section, stage, centerline, reach_m):
    """Nearest shared segment supplies a local stage ceiling and wet channel seeds."""
    params = section["identity"]["parameters"]
    coarse = plan["identity"]["parameters"]
    shape = section["arrays"]["bounded_surface_m"].shape
    gx, gz = np.meshgrid(params["origin_x_m"] + np.arange(shape[1]) * params["spacing_x_m"],
                         params["origin_z_m"] + np.arange(shape[0]) * params["spacing_z_m"])
    node_stage = stage["arrays"]["stage_m"].ravel()
    active = stage["arrays"]["channel_mask"].ravel()
    receiver = plan["arrays"]["receiver"]
    width = plan["arrays"]["nominal_width_m"].ravel()
    cols = plan["arrays"]["source_height_m"].shape[1]
    if centerline is None:
        positions = np.column_stack((coarse["origin_x_m"] + np.arange(receiver.size) % cols * coarse["spacing_x_m"],
                                     coarse["origin_z_m"] + np.arange(receiver.size) // cols * coarse["spacing_z_m"]))
    else:
        from terrain_pipeline.channel_centerline import validate_centerline_for_plan
        validate_centerline_for_plan(centerline, plan)
        positions = np.full((receiver.size, 2), np.nan)
        positions[centerline["arrays"]["node_flat_index"]] = centerline["arrays"]["node_world_xz_m"]
    nearest_distance = np.full(shape, np.inf)
    ceiling = np.full(shape, -np.inf)
    nearest_radius = np.zeros(shape)
    seed = np.zeros(shape, bool)
    for cell in np.flatnonzero(active):
        target = int(receiver[cell])
        if target < 0 or not active[target]:
            continue
        ax, az = positions[cell]
        bx, bz = positions[target]
        radius = max(width[cell], width[target]) / 2
        reach = radius + reach_m
        if (max(ax, bx) + reach < gx[0, 0] or min(ax, bx) - reach > gx[0, -1] or
                max(az, bz) + reach < gz[0, 0] or min(az, bz) - reach > gz[-1, 0]):
            continue
        length2 = (bx - ax) ** 2 + (bz - az) ** 2
        t = np.clip(((gx - ax) * (bx - ax) + (gz - az) * (bz - az)) / length2, 0., 1.)
        distance = np.hypot(gx - (ax + t * (bx - ax)), gz - (az + t * (bz - az)))
        local_stage = (1 - t) * node_stage[cell] + t * node_stage[target]
        nearer = distance < nearest_distance - 1e-9
        nearest_distance[nearer] = distance[nearer]
        ceiling[nearer] = local_stage[nearer]
        local_radius = ((1 - t) * width[cell] + t * width[target]) / 2
        nearest_radius[nearer] = local_radius[nearer]
        seed |= distance <= np.maximum(local_radius / 2, min(params["spacing_x_m"], params["spacing_z_m"]) / 2)
    graph_samples = []
    graph_covered = True
    for cell in np.flatnonzero(active):
        px, pz = positions[cell]
        if (px < gx[0, 0] - 1e-9 or px > gx[0, -1] + 1e-9 or
                pz < gz[0, 0] - 1e-9 or pz > gz[-1, 0] + 1e-9):
            graph_covered = False
            break
    if graph_covered:
        for cell in np.flatnonzero(active):
            target = int(receiver[cell])
            if target < 0 or not active[target]:
                continue
            ax, az = positions[cell]
            bx, bz = positions[target]
            samples = max(2, int(math.ceil(math.hypot(bx - ax, bz - az) /
                                           min(params["spacing_x_m"], params["spacing_z_m"]))))
            for t in np.linspace(0., 1., samples + 1):
                x = int(round((ax + t * (bx - ax) - params["origin_x_m"]) / params["spacing_x_m"]))
                z = int(round((az + t * (bz - az) - params["origin_z_m"]) / params["spacing_z_m"]))
                if not (0 <= x < shape[1] and 0 <= z < shape[0] and seed[z, x]):
                    graph_covered = False
                    break
                graph_samples.append((z, x))
            if not graph_covered:
                break
    return ceiling, seed, nearest_distance, nearest_radius, graph_covered, graph_samples


def evaluate_inundation(plan, section, stage, domain_mask, protected_mask,
                        legal_outlet_mask, recipe: InundationRecipe, centerline=None):
    """Solve full fine-grid flood once, gating lateral water by local river stage."""
    if not isinstance(recipe, InundationRecipe):
        raise ValueError("inundation recipe required")
    section_identity = ArtifactIdentity(**section["identity"])
    stage_identity = ArtifactIdentity(**stage["identity"])
    if (section_identity.sha256 != section["identity_sha256"] or
            stage_identity.sha256 != stage["identity_sha256"]):
        raise ValueError("section or stage identity mismatch")
    surface = section["arrays"]["bounded_surface_m"]
    shape = surface.shape
    domain = np.asarray(domain_mask)
    protected = np.asarray(protected_mask)
    legal_outlet = np.asarray(legal_outlet_mask)
    if (domain.shape != shape or protected.shape != shape or domain.dtype != bool or
            protected.dtype != bool or legal_outlet.shape != shape or legal_outlet.dtype != bool or
            not np.isfinite(surface).all()):
        raise ValueError("domain, protection and bounded surface must match finite full grid")
    if (section["identity"]["parameters"]["plan_identity_sha256"] != plan["identity_sha256"] or
            stage["identity"]["parameters"]["plan_identity_sha256"] != plan["identity_sha256"] or
            (centerline is None) != (section["identity"]["parameters"].get("centerline_identity_sha256") is None) or
            (centerline is not None and
             section["identity"]["parameters"]["centerline_identity_sha256"] != centerline["identity_sha256"]) or
            stage["identity"]["parameters"].get("centerline_identity_sha256") !=
            (centerline["identity_sha256"] if centerline is not None else None)):
        raise ValueError("section, stage and centerline must use the same shared plan")
    if stage["arrays"]["channel_mask"].shape != plan["arrays"]["source_height_m"].shape:
        raise ValueError("stage and plan grid mismatch")
    section_arrays = section["arrays"]
    section_params = section_identity.record()["parameters"]
    section_recipe_cap = section_params["max_local_cut_m"]
    source = section_arrays["source_surface_m"]
    actual = section_arrays["actual_cut_m"]
    required = section_arrays["required_cut_m"]
    if (source.shape != shape or actual.shape != shape or required.shape != shape or
            array_hash(source) != section_params["source_surface_sha256"] or
            not np.isfinite(source).all() or not np.isfinite(actual).all() or
            not np.isfinite(required).all() or np.any(actual < -1e-9) or
            np.any(actual > required + 1e-9) or
            np.any(actual > section_recipe_cap + 1e-9) or
            np.any(actual[section_arrays["protected_mask"]] > 1e-9) or
            not np.allclose(surface, source - actual, atol=1e-9, rtol=0)):
        raise ValueError("section bounded surface differs from validated cut")
    stage_params = stage_identity.record()["parameters"]
    stage_arrays = stage["arrays"]
    if digest({name: array_hash(np.ascontiguousarray(value))
               for name, value in stage_arrays.items()}) != stage_params["stage_output_sha256"]:
        raise ValueError("stage output differs from identity")
    ceiling, seed, distance, radius, whole_graph_covered, graph_samples = _shared_stage_fields(
        plan, section, stage, centerline, recipe.max_lateral_reach_m)
    rows, cols = shape
    potential_seed = seed & (ceiling > surface + recipe.min_water_depth_m)
    seed = potential_seed & domain & ~protected
    water = np.full(shape, np.nan)
    reachable = np.zeros(shape, bool)
    protected_conflict = potential_seed & protected
    boundary_contact = np.zeros(shape, bool)
    queue = deque(map(tuple, np.argwhere(seed)))
    for z, x in queue:
        reachable[z, x] = True
    while queue:
        z, x = queue.popleft()
        for nz, nx in ((z - 1, x), (z + 1, x), (z, x - 1), (z, x + 1)):
            if not (0 <= nz < rows and 0 <= nx < cols):
                if not legal_outlet[z, x]:
                    boundary_contact[z, x] = True
                continue
            if distance[nz, nx] > recipe.max_lateral_reach_m + 1e-9:
                continue
            if ceiling[nz, nx] <= surface[nz, nx] + recipe.min_water_depth_m:
                continue
            if not domain[nz, nx]:
                boundary_contact[nz, nx] = True
                continue
            if protected[nz, nx]:
                protected_conflict[nz, nx] = True
                continue
            if not reachable[nz, nx]:
                reachable[nz, nx] = True
                queue.append((nz, nx))
    water[reachable] = ceiling[reachable]
    boundary = np.zeros(shape, bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    boundary_contact |= reachable & boundary & ~legal_outlet
    reach_limited = np.zeros(shape, bool)
    for z, x in np.argwhere(reachable):
        for nz, nx in ((z - 1, x), (z + 1, x), (z, x - 1), (z, x + 1)):
            if (0 <= nz < rows and 0 <= nx < cols and
                    distance[nz, nx] > recipe.max_lateral_reach_m + 1e-9 and
                    ceiling[nz, nx] > surface[nz, nx] + recipe.min_water_depth_m and
                    domain[nz, nx] and not protected[nz, nx]):
                reach_limited[z, x] = True
    outlet_covered = bool(np.any(reachable & legal_outlet))
    wet_to_outlet = np.zeros(shape, bool)
    queue = deque(map(tuple, np.argwhere(reachable & legal_outlet)))
    for z, x in queue:
        wet_to_outlet[z, x] = True
    while queue:
        z, x = queue.popleft()
        for nz, nx in ((z - 1, x), (z + 1, x), (z, x - 1), (z, x + 1)):
            if 0 <= nz < rows and 0 <= nx < cols and reachable[nz, nx] and not wet_to_outlet[nz, nx]:
                wet_to_outlet[nz, nx] = True
                queue.append((nz, nx))
    disconnected_seed = seed & ~wet_to_outlet
    whole_graph_covered &= all(wet_to_outlet[z, x] for z, x in graph_samples)
    high_to_low_incompatibility = np.zeros(shape, bool)
    for dz, dx in ((1, 0), (0, 1)):
        first = reachable[:rows-dz, :cols-dx]
        second = reachable[dz:, dx:]
        mismatch = first & second & (np.abs(ceiling[:rows-dz, :cols-dx] - ceiling[dz:, dx:]) >
                                     max(.5, recipe.min_water_depth_m * 10))
        high_to_low_incompatibility[:rows-dz, :cols-dx] |= mismatch
    identity = ArtifactIdentity("Terragenesis", "channel-inundation", VERSION, 0,
                                {**asdict(recipe), "section_identity_sha256": section["identity_sha256"],
                                 "stage_identity_sha256": stage["identity_sha256"],
                                 "domain_sha256": array_hash(domain),
                                 "protected_sha256": array_hash(protected),
                                 "legal_outlet_sha256": array_hash(legal_outlet),
                                 "water_sha256": array_hash(water),
                                 "section_arrays_sha256": digest({
                                     name: array_hash(np.ascontiguousarray(value))
                                     for name, value in section_arrays.items()}),
                                 "stage_output_sha256": stage_params["stage_output_sha256"],
                                 "whole_graph_covered": whole_graph_covered})
    overbank = reachable & (distance > radius + 1e-9)
    arrays = {"water_surface_m": water, "wet_mask": reachable,
              "overbank_mask": overbank,
              "protected_conflict_mask": protected_conflict,
              "boundary_contact_mask": boundary_contact,
              "reach_limited_mask": reach_limited,
              "disconnected_seed_mask": disconnected_seed,
              "stage_mismatch_mask": high_to_low_incompatibility,
              "domain_mask": domain.copy(), "protected_mask": protected.copy(),
              "legal_outlet_mask": legal_outlet.copy(), "channel_seed_mask": seed}
    identity_params = identity.record()["parameters"]
    identity_params["all_arrays_sha256"] = digest({name: array_hash(np.ascontiguousarray(value))
                                                    for name, value in arrays.items()})
    identity = ArtifactIdentity("Terragenesis", "channel-inundation", VERSION, 0, identity_params)
    for value in arrays.values():
        value.flags.writeable = False
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": "diagnostic_not_publishable", "arrays": arrays,
            "summary": {"wet_nodes": int(np.count_nonzero(reachable)),
                        "overbank_nodes": int(np.count_nonzero(overbank)),
                        "protected_conflict_nodes": int(np.count_nonzero(protected_conflict)),
                        "boundary_contact_nodes": int(np.count_nonzero(boundary_contact)),
                        "reach_limited_nodes": int(np.count_nonzero(reach_limited)),
                        "stage_mismatch_nodes": int(np.count_nonzero(high_to_low_incompatibility)),
                        "channel_seed_nodes": int(np.count_nonzero(seed)),
                        "disconnected_seed_nodes": int(np.count_nonzero(disconnected_seed)),
                        "whole_graph_covered": whole_graph_covered,
                        "legal_outlet_wet": outlet_covered,
                        "coverage_complete": whole_graph_covered and outlet_covered and
                                             not bool(np.any(disconnected_seed | boundary_contact | reach_limited))}}


def slice_inundation(result, z_slice, x_slice):
    """Read-only storage window from one full-grid inundation result."""
    return {name: value[z_slice, x_slice] for name, value in result["arrays"].items()}


def save_inundation(result, path):
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ("identity", "identity_sha256", "status", "summary")}
    record["format_version"] = 1
    record["array_sha256"] = {name: array_hash(np.ascontiguousarray(value))
                              for name, value in result["arrays"].items()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent,
                                         prefix=f".{destination.name}-", suffix=".npz", delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(record, sort_keys=True), **result["arrays"])
        load_inundation(temporary)
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_inundation(path):
    expected = {"water_surface_m", "wet_mask", "overbank_mask", "protected_conflict_mask",
                "boundary_contact_mask", "reach_limited_mask", "stage_mismatch_mask",
                "disconnected_seed_mask",
                "domain_mask", "protected_mask", "legal_outlet_mask", "channel_seed_mask"}
    with np.load(path, allow_pickle=False) as archive:
        record = json.loads(str(archive["manifest"].item()))
        if set(archive.files) != expected | {"manifest"} or set(record["array_sha256"]) != expected:
            raise ValueError("invalid inundation array set")
        arrays = {name: archive[name].copy() for name in expected}
    identity = ArtifactIdentity(**record["identity"])
    if (identity.sha256 != record["identity_sha256"] or
            identity.algorithm != "channel-inundation" or identity.algorithm_version != VERSION or
            record["format_version"] != 1 or record["status"] != "diagnostic_not_publishable" or
            any(array_hash(np.ascontiguousarray(arrays[name])) != hash_value
                for name, hash_value in record["array_sha256"].items())):
        raise ValueError("invalid inundation identity or hashes")
    shape = arrays["water_surface_m"].shape
    if (len(shape) != 2 or min(shape) < 2 or arrays["water_surface_m"].dtype != np.float64 or
            any(arrays[name].shape != shape or arrays[name].dtype != bool
                for name in expected - {"water_surface_m"}) or
            not np.isfinite(arrays["water_surface_m"][arrays["wet_mask"]]).all()):
        raise ValueError("invalid inundation arrays")
    params = identity.record()["parameters"]
    InundationRecipe(params["min_water_depth_m"], params["max_lateral_reach_m"])
    if (array_hash(arrays["domain_mask"]) != params["domain_sha256"] or
            array_hash(arrays["protected_mask"]) != params["protected_sha256"] or
            array_hash(arrays["legal_outlet_mask"]) != params["legal_outlet_sha256"] or
            array_hash(arrays["water_surface_m"]) != params["water_sha256"]):
        raise ValueError("inundation domain or protection differs from identity")
    if digest({name: array_hash(np.ascontiguousarray(value))
               for name, value in arrays.items()}) != params["all_arrays_sha256"]:
        raise ValueError("inundation arrays differ from identity")
    summary = record["summary"]
    if (summary["wet_nodes"] != int(np.count_nonzero(arrays["wet_mask"])) or
            summary["overbank_nodes"] != int(np.count_nonzero(arrays["overbank_mask"])) or
            summary["protected_conflict_nodes"] != int(np.count_nonzero(arrays["protected_conflict_mask"])) or
            summary["boundary_contact_nodes"] != int(np.count_nonzero(arrays["boundary_contact_mask"])) or
            summary["reach_limited_nodes"] != int(np.count_nonzero(arrays["reach_limited_mask"])) or
            summary["stage_mismatch_nodes"] != int(np.count_nonzero(arrays["stage_mismatch_mask"])) or
            summary["disconnected_seed_nodes"] != int(np.count_nonzero(arrays["disconnected_seed_mask"])) or
            summary["channel_seed_nodes"] != int(np.count_nonzero(arrays["channel_seed_mask"])) or
            summary["legal_outlet_wet"] != bool(np.any(arrays["wet_mask"] & arrays["legal_outlet_mask"]))):
        raise ValueError("inundation summary mismatch")
    expected_complete = (params["whole_graph_covered"] and summary["legal_outlet_wet"] and
                         not bool(np.any(arrays["disconnected_seed_mask"] |
                                         arrays["boundary_contact_mask"] |
                                         arrays["reach_limited_mask"])))
    if summary["whole_graph_covered"] != params["whole_graph_covered"] or summary["coverage_complete"] != expected_complete:
        raise ValueError("inundation coverage summary mismatch")
    for value in arrays.values():
        value.flags.writeable = False
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": record["status"], "arrays": arrays, "summary": summary}
