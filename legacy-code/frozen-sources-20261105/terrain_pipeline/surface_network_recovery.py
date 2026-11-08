"""Bounded automatic recovery, actual fine gates and replayable diagnostics."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, digest
from terrain_pipeline.channel_reroute import reroute_channel, RerouteRecipe, _local_discharge
from terrain_pipeline.channel_inundation import InundationRecipe
from terrain_pipeline.channel_stage import StageRecipe
from terrain_pipeline.local_channel_sections import SectionRecipe
from terrain_pipeline.metric_channel_plan import ChannelRecipe
from terrain_pipeline.network_valley import (
    NetworkValleyRecipe, _immutable, _validated_source_plan, prepare_network_valley,
)
from terrain_pipeline.surface_network_prepare import (
    SurfaceNetworkBudget, prepare_surface_network, validate_surface_network,
)
from terrain_pipeline.valley_geometry import ValleyGeometryRecipe, evaluate_fine_valley_ledger


VERSION = "surface-network-recovery-v1"
MAX_BUNDLE_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class FineGrid:
    """Explicit metre coordinates and frozen full-domain fine-grid masks."""

    origin_x_m: float
    origin_z_m: float
    spacing_x_m: float
    spacing_z_m: float
    shape_zx: tuple
    domain_mask: np.ndarray
    protected_mask: np.ndarray
    legal_outlet_mask: np.ndarray

    def __post_init__(self):
        for name in ("origin_x_m", "origin_z_m", "spacing_x_m", "spacing_z_m"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not math.isfinite(value) or
                    (name.startswith("spacing") and value <= 0)):
                raise ValueError("invalid fine grid coordinates")
        if (len(self.shape_zx) != 2 or any(type(size) is not int or size <= 1
                                         for size in self.shape_zx) or
                math.prod(self.shape_zx) > 1000000):
            raise ValueError("invalid or excessive fine grid shape")
        object.__setattr__(self, "shape_zx", tuple(self.shape_zx))
        for name in ("domain_mask", "protected_mask", "legal_outlet_mask"):
            mask = np.asarray(getattr(self, name))
            if mask.dtype != bool or mask.shape != self.shape_zx:
                raise ValueError("fine masks must be matching boolean grids")
            object.__setattr__(self, name, _immutable(mask))
        if np.any(self.legal_outlet_mask & (~self.domain_mask | self.protected_mask)):
            raise ValueError("legal outlets conflict with fine domain or protection")


@dataclass(frozen=True)
class RecoveryRecipe:
    max_attempts: int = 12
    max_sources: int = 8
    anchor_lookahead: int = 8
    max_coarse_cells: int = 250000
    max_fine_cells: int = 1000000
    max_total_fine_cells: int = 4000000
    max_working_bytes: int = 268435456

    def __post_init__(self):
        ceilings = {"max_attempts": 32, "max_sources": 64, "anchor_lookahead": 128,
                    "max_coarse_cells": 250000, "max_fine_cells": 1000000,
                    "max_total_fine_cells": 32000000, "max_working_bytes": 536870912}
        if any(type(value) is not int or not 0 < value <= ceilings[name]
               for name, value in asdict(self).items()):
            raise ValueError("invalid recovery resource bounds")


def _tree(value, arrays):
    if isinstance(value, np.ndarray):
        key = f"array_{len(arrays):05d}"
        arrays[key] = value
        return {"$array": key, "sha256": array_hash(value),
                "shape": list(value.shape), "dtype": value.dtype.str}
    if isinstance(value, dict):
        return {key: _tree(child, arrays) for key, child in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_tree(child, arrays) for child in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _fingerprint(value):
    return digest(_tree(value, {}))


def _freeze(value):
    if isinstance(value, np.ndarray):
        return _immutable(value)
    if isinstance(value, dict):
        return {key: _freeze(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_freeze(child) for child in value]
    return value


def _surface(plan, fine, outlet_stage, section, stage, inundation, budget):
    result = prepare_surface_network(plan, fine.origin_x_m, fine.origin_z_m,
        fine.spacing_x_m, fine.spacing_z_m, fine.shape_zx, fine.domain_mask,
        fine.protected_mask, fine.legal_outlet_mask, outlet_stage,
        section, stage, inundation, budget)
    if result["status"] == "prepared":
        validate_surface_network(result)
    return result


def _coarse_gate(plan, domain, protected):
    active = plan["arrays"]["channel_mask"]
    return {"coarse_domain": bool(np.any(active & ~domain)),
            "coarse_protection": bool(np.any(active & protected))}


def _consistent_masks(plan, domain, protected, fine):
    params = plan["identity"]["parameters"]
    shape = plan["arrays"]["source_height_m"].shape
    axes = []
    for axis, count, origin, spacing in (
            ("z", shape[0], fine.origin_z_m, fine.spacing_z_m),
            ("x", shape[1], fine.origin_x_m, fine.spacing_x_m)):
        positions = (params[f"origin_{axis}_m"] + np.arange(count) *
                     params[f"spacing_{axis}_m"] - origin) / spacing
        indices = np.rint(positions).astype(np.int64)
        limit = fine.shape_zx[len(axes)]
        if (not np.allclose(positions, indices, rtol=0, atol=1e-8) or
                indices[0] != 0 or indices[-1] != limit - 1):
            raise ValueError("fine grid must cover and align the full coarse grid")
        axes.append(indices)
    sample = np.ix_(*axes)
    if (not np.array_equal(domain, fine.domain_mask[sample]) or
            not np.array_equal(protected, fine.protected_mask[sample])):
        raise ValueError("coarse and fine domain/protection disagree")


def _failure_nodes(original, surface, domain, protected, fine):
    arrays = original["arrays"]
    active = arrays["channel_mask"].ravel()
    receiver = arrays["receiver"]
    failed = active & (~domain.ravel() | protected.ravel())
    for name in ("over_budget_mask", "failed_slope_edge_donor_mask"):
        failed |= arrays[name].ravel() & active
    params = original["identity"]["parameters"]
    columns = arrays["source_height_m"].shape[1]
    if surface is not None:
        surface_arrays = surface["arrays"]
        failures = surface["summary"]["budget_failures"]
        fine_failure = np.zeros(fine.shape_zx, bool)
        for name in ("disconnected_seed_mask", "boundary_contact_mask", "reach_limited_mask"):
            fine_failure |= surface_arrays[name]
        fine_failure |= (surface_arrays["bed_cut_m"] > 1e-9) & (
            fine.protected_mask | ~fine.domain_mask)
        if any(failures.values()):
            fine_failure |= surface_arrays["bed_cut_m"] > 1e-9
        for donor in np.flatnonzero(active & (receiver >= 0)):
            target = int(receiver[donor])
            endpoints = []
            for cell in (donor, target):
                endpoints.append((int(round((params["origin_z_m"] + (cell // columns) *
                    params["spacing_z_m"] - fine.origin_z_m) / fine.spacing_z_m)),
                    int(round((params["origin_x_m"] + (cell % columns) *
                    params["spacing_x_m"] - fine.origin_x_m) / fine.spacing_x_m))))
            start, end = endpoints
            steps = max(abs(end[0] - start[0]), abs(end[1] - start[1]), 1)
            for step in range(steps + 1):
                fraction = step / steps
                cell = (int(round(start[0] + fraction * (end[0] - start[0]))),
                        int(round(start[1] + fraction * (end[1] - start[1]))))
                if fine_failure[cell]:
                    failed[donor] = True
                    break
        if any(surface["summary"]["joint_blockers"].values()) and not np.any(failed):
            failed |= active & (receiver >= 0)
    return failed


def _failure_sources(original, failed, domain, protected, recipe):
    arrays = original["arrays"]
    active = arrays["channel_mask"].ravel()
    receiver = arrays["receiver"]
    upstream = [[] for _ in range(receiver.size)]
    for donor in np.flatnonzero(active & (receiver >= 0)):
        upstream[int(receiver[donor])].append(int(donor))
    candidates = []
    seen = set()
    for failure in np.flatnonzero(failed):
        queue = list(upstream[int(failure)])
        if domain.flat[failure] and not protected.flat[failure]:
            queue.append(int(failure))
        position = 0
        while position < len(queue) and len(candidates) < recipe.max_sources:
            cell = queue[position]
            position += 1
            if cell in seen:
                continue
            seen.add(cell)
            queue.extend(upstream[cell])
            if domain.flat[cell] and not protected.flat[cell] and receiver[cell] >= 0:
                candidates.append(cell)
        if len(candidates) >= recipe.max_sources:
            break
    return candidates


def recover_surface_network(plan, coarse_domain, coarse_protected, fine,
                            outlet_stage_m, section_recipe, stage_recipe,
                            inundation_recipe, budget, network_recipe,
                            valley_recipe, reroute_recipe=RerouteRecipe(),
                            recovery_recipe=RecoveryRecipe()):
    """Try original bed, whole-network valley, then failure-driven original-plan routes.

    Legal outlets are caller-supplied boundary conditions, not natural-outlet evidence.
    Failed outcomes diagnose a possible lake requirement; they never publish lake water.
    """
    expected_types = ((fine, FineGrid), (section_recipe, SectionRecipe),
        (stage_recipe, StageRecipe), (inundation_recipe, InundationRecipe),
        (budget, SurfaceNetworkBudget), (network_recipe, NetworkValleyRecipe),
        (valley_recipe, ValleyGeometryRecipe), (reroute_recipe, RerouteRecipe),
        (recovery_recipe, RecoveryRecipe))
    if any(not isinstance(value, expected) for value, expected in expected_types):
        raise ValueError("explicit recovery grids and recipes required")
    shape = np.asarray(plan["arrays"]["source_height_m"]).shape
    if len(shape) != 2 or math.prod(shape) > recovery_recipe.max_coarse_cells:
        raise ValueError("recovery exceeds coarse cell bound")
    if math.prod(fine.shape_zx) > recovery_recipe.max_fine_cells:
        raise ValueError("recovery exceeds fine cell bound")
    if (math.prod(fine.shape_zx) * 512 + math.prod(shape) * 1024 >
            recovery_recipe.max_working_bytes):
        raise ValueError("recovery exceeds working memory bound")
    original = _validated_source_plan(plan)
    _local_discharge(original)
    domain, protected = np.asarray(coarse_domain), np.asarray(coarse_protected)
    if any(mask.shape != shape or mask.dtype != bool for mask in (domain, protected)):
        raise ValueError("coarse masks must be matching boolean grids")
    domain, protected = _immutable(domain), _immutable(protected)
    _consistent_masks(original, domain, protected, fine)
    original_outlets = original["arrays"]["channel_mask"] & original["arrays"]["outlet_mask"]
    params = original["identity"]["parameters"]
    outlet_rows, outlet_columns = np.nonzero(original_outlets)
    fine_rows = np.rint((params["origin_z_m"] + outlet_rows * params["spacing_z_m"] -
                         fine.origin_z_m) / fine.spacing_z_m).astype(int)
    fine_columns = np.rint((params["origin_x_m"] + outlet_columns * params["spacing_x_m"] -
                            fine.origin_x_m) / fine.spacing_x_m).astype(int)
    if not np.all(fine.legal_outlet_mask[fine_rows, fine_columns]):
        raise ValueError("active plan outlets must map to explicit legal fine outlets")
    channel = ChannelRecipe(**{name: original["identity"]["parameters"][name]
                              for name in ChannelRecipe.__dataclass_fields__})
    if reroute_recipe.max_extra_cut_m > min(channel.max_cut_m, budget.max_bed_cut_m,
                                           section_recipe.max_local_cut_m):
        raise ValueError("reroute extra cut exceeds original allowed bed limit")
    outlet_stage = np.asarray(outlet_stage_m)
    count = int(np.count_nonzero(original["arrays"]["channel_mask"] &
                                 original["arrays"]["outlet_mask"]))
    if (outlet_stage.dtype.kind not in "fiu" or outlet_stage.shape != (count,) or
            not np.isfinite(outlet_stage).all()):
        raise ValueError("outlet stages must match original active outlets")
    inputs = {"plan": original, "coarse_domain": domain, "coarse_protected": protected,
        "fine": {"origin_x_m": fine.origin_x_m, "origin_z_m": fine.origin_z_m,
            "spacing_x_m": fine.spacing_x_m, "spacing_z_m": fine.spacing_z_m,
            "shape_zx": list(fine.shape_zx), "domain_mask": fine.domain_mask,
            "protected_mask": fine.protected_mask, "legal_outlet_mask": fine.legal_outlet_mask},
        "outlet_stage_m": _immutable(outlet_stage), "section_recipe": asdict(section_recipe),
        "stage_recipe": asdict(stage_recipe), "inundation_recipe": asdict(inundation_recipe),
        "budget": asdict(budget), "network_recipe": asdict(network_recipe),
        "valley_recipe": asdict(valley_recipe), "reroute_recipe": asdict(reroute_recipe),
        "recovery_recipe": asdict(recovery_recipe)}
    attempts = []
    failed_nodes = _failure_nodes(original, None, domain, protected, fine)
    fine_work = 0
    work_exhausted = False
    last = {"plan": original, "valley": None, "surface": None, "fine_ledger": None}
    selected = None

    def evaluate(candidate, method, valley=False, source=None, anchor=None, reroute=None):
        nonlocal last, selected, fine_work, work_exhausted, failed_nodes
        if len(attempts) >= recovery_recipe.max_attempts:
            return False
        if fine_work + math.prod(fine.shape_zx) > recovery_recipe.max_total_fine_cells:
            work_exhausted = True
            return False
        fine_work += math.prod(fine.shape_zx)
        attempt = {"index": len(attempts), "method": method,
            "source_grid_zx": source, "anchor_grid_zx": anchor,
            "source_plan_sha256": original["identity_sha256"], "accepted": False}
        attempts.append(attempt)
        last = {"plan": candidate, "valley": None, "surface": None, "fine_ledger": None}
        outcome = {"plan": candidate, "valley": None, "surface": None, "fine_ledger": None}
        try:
            coarse_failures = _coarse_gate(candidate, domain, protected)
            coarse_failures["active_outlets_changed"] = not np.array_equal(
                candidate["arrays"]["channel_mask"] & candidate["arrays"]["outlet_mask"], original_outlets)
            if valley:
                outcome["valley"] = prepare_network_valley(candidate, domain, protected,
                    network_recipe, valley_recipe, channel)
                candidate = outcome["valley"]["replanned_plan"]
                outcome["plan"] = candidate
            outcome["surface"] = _surface(candidate, fine, outlet_stage, section_recipe,
                                           stage_recipe, inundation_recipe, budget)
            if valley:
                outcome["fine_ledger"] = evaluate_fine_valley_ledger(
                    outcome["valley"], outcome["surface"])
            surface = outcome["surface"]
            failures = {**coarse_failures, **surface["summary"]["budget_failures"],
                **{f"joint_{name}": value for name, value in surface["summary"]["joint_blockers"].items()}}
            if valley:
                failures.update({f"ledger_{name}": value for name, value in
                                 outcome["fine_ledger"]["summary"]["failures"].items()})
            accepted = surface["status"] == "prepared" and not any(failures.values())
            attempt.update({"accepted": accepted, "failures": failures,
                "plan_sha256": candidate["identity_sha256"], "surface_summary": surface["summary"],
                "fine_ledger_summary": None if not valley else outcome["fine_ledger"]["summary"],
                "reroute_summary": None if reroute is None else reroute["summary"],
                "path_grid_zx": None if reroute is None else reroute["path_grid_zx"]})
            if accepted:
                selected = method
        except ValueError as error:
            attempt["error"] = str(error)
        last = outcome
        failed_nodes |= _failure_nodes(original, outcome["surface"], domain, protected, fine)
        return attempt["accepted"]

    accepted = evaluate(original, "baseline")
    if not accepted:
        accepted = evaluate(original, "network_valley", valley=True)
    exhausted_candidates = True
    if not accepted and not work_exhausted and len(attempts) < recovery_recipe.max_attempts:
        sources = _failure_sources(original, failed_nodes, domain, protected, recovery_recipe)
        columns = shape[1]
        for source_id in sources:
            anchor_id = int(original["arrays"]["receiver"][source_id])
            for _ in range(recovery_recipe.anchor_lookahead):
                if anchor_id < 0 or accepted:
                    break
                source = [source_id // columns, source_id % columns]
                anchor = [anchor_id // columns, anchor_id % columns]
                if (not domain.flat[anchor_id] or protected.flat[anchor_id] or
                        not original["arrays"]["channel_mask"].flat[anchor_id]):
                    anchor_id = int(original["arrays"]["receiver"][anchor_id])
                    continue
                if work_exhausted or len(attempts) >= recovery_recipe.max_attempts:
                    exhausted_candidates = False
                    break
                try:
                    reroute = reroute_channel(original, source, anchor, domain, protected, reroute_recipe)
                except ValueError as error:
                    attempts.append({"index": len(attempts), "method": "reroute_search",
                        "source_grid_zx": source, "anchor_grid_zx": anchor,
                        "source_plan_sha256": original["identity_sha256"], "accepted": False,
                        "error": str(error)})
                else:
                    accepted = evaluate(reroute["plan"], "reroute_bed", source=source,
                                        anchor=anchor, reroute=reroute)
                    if not accepted:
                        accepted = evaluate(reroute["plan"], "reroute_valley", valley=True,
                                            source=source, anchor=anchor, reroute=reroute)
                anchor_id = int(original["arrays"]["receiver"][anchor_id])
            if accepted or work_exhausted or len(attempts) >= recovery_recipe.max_attempts:
                break
    resource_exhausted = not accepted and (work_exhausted or len(attempts) >= recovery_recipe.max_attempts)
    constraint_failure = any(any(value for key, value in attempt.get("failures", {}).items()
        if any(word in key for word in ("protection", "domain", "volume", "area", "depth")))
        for attempt in attempts)
    status = "accepted" if accepted else (
        "failed" if resource_exhausted or constraint_failure else "lake_required")
    result = {"algorithm_version": VERSION, "inputs": inputs, "status": status,
        "accepted": accepted, "selected_method": selected, "attempts": attempts,
        "final_plan": last["plan"], "valley": last["valley"], "surface": last["surface"],
        "fine_ledger": last["fine_ledger"], "summary": {
            "attempt_count": len(attempts), "attempt_limit_reached": resource_exhausted,
            "total_fine_cells_evaluated": fine_work, "fine_work_limit_reached": work_exhausted,
            "candidate_search_exhausted": not accepted and exhausted_candidates and not resource_exhausted,
            "outlet_evidence": "caller_supplied_not_naturally_certified",
            "lake_published": False, "original_height_sha256": array_hash(original["arrays"]["source_height_m"])}}
    result["identity_sha256"] = _fingerprint(result)
    return _freeze(result)


def _replay(inputs):
    return recover_surface_network(inputs["plan"], inputs["coarse_domain"],
        inputs["coarse_protected"], FineGrid(**inputs["fine"]), inputs["outlet_stage_m"],
        SectionRecipe(**inputs["section_recipe"]), StageRecipe(**inputs["stage_recipe"]),
        InundationRecipe(**inputs["inundation_recipe"]), SurfaceNetworkBudget(**inputs["budget"]),
        NetworkValleyRecipe(**inputs["network_recipe"]), ValleyGeometryRecipe(**inputs["valley_recipe"]),
        RerouteRecipe(**inputs["reroute_recipe"]), RecoveryRecipe(**inputs["recovery_recipe"]))


def validate_surface_network_recovery(result):
    """Replay actual fine water and cumulative ledger, not a trusted saved summary."""
    try:
        if result["algorithm_version"] != VERSION:
            raise ValueError("unsupported recovery algorithm")
        replayed = _replay(result["inputs"])
        if _fingerprint(result) != _fingerprint(replayed):
            raise ValueError("recovery differs from semantic replay")
        return replayed
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError("invalid recovery bundle") from error


def save_surface_network_recovery(result, path):
    """Atomically create an immutable diagnostic bundle; never replace any file."""
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    validated = validate_surface_network_recovery(result)
    arrays = {}
    tree = _tree(validated, arrays)
    manifest = {"format_version": 1, "tree": tree, "tree_sha256": digest(tree)}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, suffix=".npz",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(manifest, sort_keys=True), **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        load_surface_network_recovery(temporary)
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_surface_network_recovery(path):
    """Check bounded payload hashes and replay every chosen or failed computation."""
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if (len(entries) > 4096 or sum(item.file_size for item in entries) > MAX_BUNDLE_BYTES or
                    len({item.filename for item in entries}) != len(entries)):
                raise ValueError("recovery bundle exceeds resource bound")
            for entry in entries:
                with archive.open(entry) as stream:
                    version = np.lib.format.read_magic(stream)
                    if version == (1, 0):
                        shape, _, dtype = np.lib.format.read_array_header_1_0(stream)
                    elif version == (2, 0):
                        shape, _, dtype = np.lib.format.read_array_header_2_0(stream)
                    else:
                        raise ValueError("unsupported bundle array format")
                    if (dtype.hasobject or math.prod(shape) * dtype.itemsize > MAX_BUNDLE_BYTES or
                            math.prod(shape) * dtype.itemsize != entry.file_size - stream.tell()):
                        raise ValueError("invalid or excessive bundle array header")
                    if entry.filename == "manifest.npy" and (
                            shape != () or dtype.kind != "U" or dtype.itemsize > 4 * 1024 * 1024):
                        raise ValueError("recovery manifest must be a bounded Unicode scalar")
        with np.load(path, allow_pickle=False) as archive:
            def unique_pairs(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate recovery JSON key")
                    result[key] = value
                return result

            def reject_constant(value):
                raise ValueError("nonfinite recovery JSON constant: " + value)

            manifest = json.loads(str(archive["manifest"].item()), object_pairs_hook=unique_pairs,
                                  parse_constant=reject_constant)
            if manifest["format_version"] != 1 or digest(manifest["tree"]) != manifest["tree_sha256"]:
                raise ValueError("invalid recovery manifest hash")
            used = {"manifest"}

            def decode(value):
                if isinstance(value, dict) and "$array" in value:
                    key = value["$array"]
                    if key in used or set(value) != {"$array", "sha256", "shape", "dtype"}:
                        raise ValueError("invalid recovery array reference")
                    used.add(key)
                    array = archive[key]
                    if (array.dtype.kind not in "bifu" or array.dtype.str != value["dtype"] or
                            list(array.shape) != value["shape"] or array_hash(array) != value["sha256"]):
                        raise ValueError("recovery array hash or shape mismatch")
                    return _immutable(array)
                if isinstance(value, dict):
                    return {key: decode(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [decode(child) for child in value]
                return value

            result = decode(manifest["tree"])
            if used != set(archive.files):
                raise ValueError("unexpected recovery bundle arrays")
        return validate_surface_network_recovery(result)
    except (KeyError, TypeError, OSError, RecursionError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError("invalid recovery bundle") from error


def prepare_with_reroute(plan, source_grid_zx, anchor_grid_zx, coarse_domain,
                         coarse_protected, fine_origin_x_m, fine_origin_z_m,
                         fine_spacing_x_m, fine_spacing_z_m, fine_shape_zx,
                         fine_domain, fine_protected, fine_legal_outlet,
                         outlet_stage_m, section_recipe, stage_recipe,
                         inundation_recipe, budget, reroute_recipe=RerouteRecipe()):
    """Run a changed D8 graph/Q through the same fine geometry and water gate."""
    if reroute_recipe.max_extra_cut_m > min(budget.max_bed_cut_m, section_recipe.max_local_cut_m):
        raise ValueError("reroute extra cut exceeds original allowed bed limit")
    candidate = reroute_channel(plan, source_grid_zx, anchor_grid_zx,
                                coarse_domain, coarse_protected, reroute_recipe)
    result = prepare_surface_network(candidate["plan"], fine_origin_x_m, fine_origin_z_m,
        fine_spacing_x_m, fine_spacing_z_m, fine_shape_zx, fine_domain,
        fine_protected, fine_legal_outlet, outlet_stage_m, section_recipe,
        stage_recipe, inundation_recipe, budget)
    if result["status"] == "prepared":
        validate_surface_network(result)
    return {"status": result["status"], "reroute": candidate, "surface_network": result,
            "accepted": result["status"] == "prepared" and candidate["summary"]["bed_plan_feasible"]}
