"""Explicit terrain/hydrology delivery and generation-free read-only consumers."""

from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import tempfile
from types import MappingProxyType
import zipfile

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, TerrainArtifact, array_hash, canonical_json, digest
from terrain_pipeline.artifacts.storage import load_artifact, save_artifact
from terrain_pipeline.surface_network_recovery import _fingerprint, _tree, validate_surface_network_recovery


VERSION = "surface-network-consumer-v1"
MAX_BYTES = 256 * 1024 * 1024
GEOMETRY = {"source_surface_m", "valley_surface_m", "final_surface_m", "valley_cut_m",
    "bed_cut_m", "total_cut_m", "water_surface_m", "wet_mask", "domain_mask",
    "protected_mask", "legal_outlet_mask"}
GRAPH = {"world_xz_m", "receiver", "order", "discharge_m3_s", "active_mask", "outlet_mask",
    "local_discharge_m3_s", "node_stage_m"}
HYDROLOGY = {"geometry_unit": "m", "discharge_unit": "m3/s",
    "Q_semantics": "coarse_node_reach_discharge_not_additive_across_nodes",
    "dry_stage_placeholder_m": 0., "natural_outlets_certified": False, "lake_water_published": False}


def _immutable(value):
    array = np.ascontiguousarray(value)
    return np.frombuffer(array.tobytes(), dtype=array.dtype).reshape(array.shape)


def _freeze(value):
    if isinstance(value, np.ndarray):
        return _immutable(value)
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate delivery JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("nonfinite delivery JSON constant: " + value)


def _read_json(path):
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("delivery manifest exceeds bound")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)


def _file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _array_record(arrays):
    return {name: {"sha256": array_hash(array), "shape": list(array.shape), "dtype": array.dtype.str}
            for name, array in sorted(arrays.items())}


def _named(value, name):
    if (not isinstance(value, str) or not value.strip() or len(value) > 2048 or value != value.strip() or
            any(ord(char) < 32 for char in value) or
            value.lower() in {"unknown", "none", "null", "nan", "unspecified", "?"}):
        raise ValueError("explicit " + name + " required")
    return value


def _reject_link_chain(path):
    absolute = Path(os.path.abspath(path))
    for item in (absolute, *absolute.parents):
        try:
            record = item.lstat()
        except FileNotFoundError:
            continue
        if (item.is_symlink() or getattr(record, "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)):
            raise ValueError("delivery paths must not contain symlinks or junctions")


def _identity(result):
    identity = ArtifactIdentity(**result["identity"])
    if identity.sha256 != result["identity_sha256"]:
        raise ValueError("proof algorithm identity mismatch")
    return result["identity"]["parameters"]


def _local_q(arrays):
    receiver, order = arrays["receiver"], arrays["order"]
    height = arrays["source_height_m"]
    count = height.size
    if (height.ndim != 2 or count > 250000 or receiver.shape != (count,) or order.shape != (count,) or
            receiver.dtype.kind not in "iu" or order.dtype.kind not in "iu" or
            np.any((receiver < -1) | (receiver >= count)) or
            not np.array_equal(np.sort(order), np.arange(count))):
        raise ValueError("invalid delivered route/order")
    rank = np.empty(count, dtype=np.int64)
    rank[order] = np.arange(count)
    donors = np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    if np.any(rank[targets] >= rank[donors]):
        raise ValueError("delivered route is cyclic or not receiver-first")
    columns = height.shape[1]
    if np.any(np.maximum(np.abs(donors // columns - targets // columns),
                         np.abs(donors % columns - targets % columns)) != 1):
        raise ValueError("delivered graph must use D8 neighbours")
    discharge = arrays["discharge_m3_s"].ravel()
    if (arrays["discharge_m3_s"].shape != height.shape or not np.isfinite(discharge).all() or
            np.any(discharge < 0) or arrays["channel_mask"].dtype != bool or
            arrays["channel_mask"].shape != height.shape or arrays["outlet_mask"].dtype != bool or
            arrays["outlet_mask"].shape != height.shape or
            not np.array_equal(arrays["outlet_mask"].ravel(), receiver == -1)):
        raise ValueError("invalid delivered Q or outlet masks")
    active = arrays["channel_mask"].ravel()
    if np.any(active[donors] & ~active[targets]):
        raise ValueError("active channel terminates before its outlet")
    local = discharge.copy()
    np.subtract.at(local, targets, discharge[donors])
    total = float(discharge[receiver < 0].sum())
    if (np.any(local < -1e-8) or not math.isclose(float(local.sum()), total, rel_tol=1e-10, abs_tol=1e-8)):
        raise ValueError("delivered Q is nonconservative")
    return local, total


def _plan_proof(plan):
    params = _identity(plan)
    arrays = plan["arrays"]
    for name in ("spacing_x_m", "spacing_z_m", "origin_x_m", "origin_z_m", "sea_level_elevation_m"):
        value = params[name]
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or
                (name.startswith("spacing") and value <= 0)):
            raise ValueError("invalid delivered coarse coordinates")
    for name, parameter in (("source_height_m", "source_height_sha256"),
            ("receiver", "source_route_sha256"), ("order", "source_order_sha256"),
            ("outlet_mask", "source_outlet_sha256"), ("discharge_m3_s", "source_discharge_sha256")):
        if array_hash(arrays[name]) != params[parameter]:
            raise ValueError("delivered plan source hash mismatch")
    if not np.isfinite(arrays["source_height_m"]).all():
        raise ValueError("nonfinite delivered coarse source")
    _named(params["source_identity"], "plan source identity")
    return _local_q(arrays)


def _fine_source(height, coarse, fine):
    rows, columns = fine["shape_zx"]
    x = (fine["origin_x_m"] + np.arange(columns) * fine["spacing_x_m"] - coarse["origin_x_m"]) / coarse["spacing_x_m"]
    z = (fine["origin_z_m"] + np.arange(rows) * fine["spacing_z_m"] - coarse["origin_z_m"]) / coarse["spacing_z_m"]
    if x[0] < -1e-8 or z[0] < -1e-8 or x[-1] > height.shape[1] - 1 + 1e-8 or z[-1] > height.shape[0] - 1 + 1e-8:
        raise ValueError("delivered fine grid leaves original source")
    x, z = np.clip(x, 0, height.shape[1] - 1), np.clip(z, 0, height.shape[0] - 1)
    left, top = np.floor(x).astype(int), np.floor(z).astype(int)
    right, bottom = np.minimum(left + 1, height.shape[1] - 1), np.minimum(top + 1, height.shape[0] - 1)
    fraction_x, fraction_z = (x - left)[None, :], (z - top)[:, None]
    return ((1 - fraction_x) * (1 - fraction_z) * height[np.ix_(top, left)] +
            fraction_x * (1 - fraction_z) * height[np.ix_(top, right)] +
            (1 - fraction_x) * fraction_z * height[np.ix_(bottom, left)] +
            fraction_x * fraction_z * height[np.ix_(bottom, right)])


def _grid_indices(plan, fine):
    params = plan["identity"]["parameters"]
    rows, columns = np.indices(plan["arrays"]["source_height_m"].shape)
    world_x = params["origin_x_m"] + columns.ravel() * params["spacing_x_m"]
    world_z = params["origin_z_m"] + rows.ravel() * params["spacing_z_m"]
    fine_x, fine_z = ((world_x - fine["origin_x_m"]) / fine["spacing_x_m"],
                      (world_z - fine["origin_z_m"]) / fine["spacing_z_m"])
    ix, iz = np.rint(fine_x).astype(int), np.rint(fine_z).astype(int)
    if (not np.allclose(fine_x, ix, atol=1e-8, rtol=0) or not np.allclose(fine_z, iz, atol=1e-8, rtol=0) or
            np.any(ix < 0) or np.any(iz < 0) or np.any(ix >= fine["shape_zx"][1]) or np.any(iz >= fine["shape_zx"][0])):
        raise ValueError("delivered graph is not aligned with fine grid")
    return np.column_stack((world_x, world_z)), iz, ix


def _payload(recovery):
    surface, ledger = recovery["surface"], recovery["fine_ledger"]
    source = surface["arrays"]["source_surface_m"] if ledger is None else ledger["arrays"]["source_surface_m"]
    final = surface["arrays"]["final_surface_m"] if ledger is None else ledger["arrays"]["final_surface_m"]
    valley_surface, wet = surface["arrays"]["source_surface_m"], surface["arrays"]["wet_mask"]
    water = np.where(wet, surface["arrays"]["water_surface_m"], 0.)
    arrays = {"source_surface_m": source, "valley_surface_m": valley_surface,
        "final_surface_m": final, "valley_cut_m": source - valley_surface,
        "bed_cut_m": valley_surface - final, "total_cut_m": source - final,
        "water_surface_m": water, "wet_mask": wet,
        **{name: surface["arrays"][name] for name in ("domain_mask", "protected_mask", "legal_outlet_mask")}}
    plan, fine = recovery["final_plan"], recovery["inputs"]["fine"]
    positions, rows, columns = _grid_indices(plan, fine)
    local, _ = _local_q(plan["arrays"])
    active = plan["arrays"]["channel_mask"].ravel()
    arrays.update(world_xz_m=positions, receiver=plan["arrays"]["receiver"], order=plan["arrays"]["order"],
        discharge_m3_s=plan["arrays"]["discharge_m3_s"].ravel(), active_mask=active,
        outlet_mask=plan["arrays"]["outlet_mask"].ravel(), local_discharge_m3_s=local,
        node_stage_m=np.where(active, water[rows, columns], 0.))
    return arrays


def _geometry_gate(arrays, recovery):
    source, valley_surface, final = (arrays[name] for name in ("source_surface_m", "valley_surface_m", "final_surface_m"))
    shape = source.shape
    fine = recovery["inputs"]["fine"]
    for name in ("origin_x_m", "origin_z_m", "spacing_x_m", "spacing_z_m"):
        value = fine[name]
        if isinstance(value, bool) or not math.isfinite(value) or (name.startswith("spacing") and value <= 0):
            raise ValueError("invalid delivered fine coordinates")
    if shape != tuple(fine["shape_zx"]) or source.ndim != 2 or source.size > 1000000:
        raise ValueError("invalid delivered fine shape")
    inputs = recovery["inputs"]
    for recipe_name in ("budget", "valley_recipe", "stage_recipe", "inundation_recipe", "section_recipe"):
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
               not math.isfinite(value) or value < 0 for value in inputs[recipe_name].values()):
            raise ValueError("invalid delivered numeric recipe")
    for name in GEOMETRY:
        array = arrays[name]
        if array.shape != shape or (name.endswith("mask") and array.dtype != bool):
            raise ValueError("invalid delivered geometry/mask shape")
        if not name.endswith("mask") and (array.dtype.kind not in "fiu" or not np.isfinite(array).all()):
            raise ValueError("delivered geometry must be finite")
    for name, expected in (("valley_cut_m", source - valley_surface), ("bed_cut_m", valley_surface - final),
                           ("total_cut_m", source - final)):
        if np.any(arrays[name] < -1e-9) or not np.allclose(arrays[name], expected, atol=1e-9, rtol=0):
            raise ValueError("delivered cut is negative or inconsistent")
    wet, water = arrays["wet_mask"], arrays["water_surface_m"]
    domain, protected, legal = (arrays[name] for name in ("domain_mask", "protected_mask", "legal_outlet_mask"))
    changed = arrays["total_cut_m"] > 1e-9
    if (not wet.any() or np.any(water[~wet] != 0) or np.any(water[wet] <= final[wet]) or
            np.any(wet & (~domain | protected)) or np.any(changed & (~domain | protected)) or
            np.any(legal & (~domain | protected))):
        raise ValueError("delivered wet water, domain or protection is invalid")
    boundary = np.zeros(shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    if np.any(wet & boundary & ~legal):
        raise ValueError("delivered water touches an undeclared boundary")
    threshold = max(.5, inputs["inundation_recipe"]["min_water_depth_m"] * 10)
    for axis in (0, 1):
        first = [slice(None), slice(None)]
        second = [slice(None), slice(None)]
        first[axis], second[axis] = slice(None, -1), slice(1, None)
        before, after = tuple(first), tuple(second)
        adjacent_wet = wet[before] & wet[after]
        if np.any(adjacent_wet & (np.abs(water[before] - water[after]) > threshold + 1e-9)):
            raise ValueError("delivered adjacent wet stage transition exceeds original threshold")
    visited = np.zeros(shape, bool)
    queue = deque(map(tuple, np.argwhere(wet & legal)))
    for cell in queue:
        visited[cell] = True
    while queue:
        row, column = queue.popleft()
        for next_row, next_column in ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1)):
            if (0 <= next_row < shape[0] and 0 <= next_column < shape[1] and
                    wet[next_row, next_column] and not visited[next_row, next_column]):
                visited[next_row, next_column] = True
                queue.append((next_row, next_column))
    if not np.array_equal(visited, wet):
        raise ValueError("delivered wet water is not four-connected to legal outlets")
    original = recovery["inputs"]["plan"]
    if array_hash(original["arrays"]["source_height_m"]) != recovery["summary"]["original_height_sha256"]:
        raise ValueError("original H0 hash disagrees with delivery provenance")
    h0 = _fine_source(original["arrays"]["source_height_m"], original["identity"]["parameters"], fine)
    if not np.allclose(source, h0, atol=1e-8, rtol=0):
        raise ValueError("delivery H0 is not the original source")
    _, rows, columns = _grid_indices(recovery["final_plan"], fine)
    active, outlets = arrays["active_mask"], arrays["outlet_mask"]
    if (np.any(active & (~inputs["coarse_domain"].ravel() | inputs["coarse_protected"].ravel())) or
            not np.array_equal(domain[rows, columns], inputs["coarse_domain"].ravel()) or
            not np.array_equal(protected[rows, columns], inputs["coarse_protected"].ravel()) or
            not np.all(wet[rows[active], columns[active]]) or
            not np.all(legal[rows[active & outlets], columns[active & outlets]])):
        raise ValueError("delivered route, fine masks or active outlets disagree")
    for name in ("domain_mask", "protected_mask", "legal_outlet_mask"):
        if not np.array_equal(arrays[name], fine[name]):
            raise ValueError("delivered fine masks differ from original constraints")
    bounded_bed = recovery["final_plan"]["arrays"]["bounded_bed_m"].ravel()
    if not np.allclose(final[rows[active], columns[active]], bounded_bed[active],
                       atol=inputs["budget"]["bed_match_tolerance_m"], rtol=0):
        raise ValueError("delivered surface does not match actual channel bed")
    plan_arrays = recovery["final_plan"]["arrays"]
    for donor in np.flatnonzero(active & (arrays["receiver"] >= 0)):
        target = int(arrays["receiver"][donor])
        steps = max(abs(rows[target] - rows[donor]), abs(columns[target] - columns[donor]))
        previous_bed = None
        for step in range(steps + 1):
            fraction = step / steps
            row = int(round(rows[donor] + fraction * (rows[target] - rows[donor])))
            column = int(round(columns[donor] + fraction * (columns[target] - columns[donor])))
            stage = arrays["node_stage_m"][donor] * (1 - fraction) + arrays["node_stage_m"][target] * fraction
            depth = stage - final[row, column]
            if (not wet[row, column] or depth < inputs["stage_recipe"]["min_clearance_m"] - 1e-9 or
                    depth > inputs["stage_recipe"]["max_depth_m"] + 1e-9 or
                    (previous_bed is not None and final[row, column] > previous_bed + 1e-9)):
                raise ValueError("delivered fine channel edge is dry, blocked or reverse-sloped")
            previous_bed = final[row, column]
    h1 = _fine_source(plan_arrays["source_height_m"], recovery["final_plan"]["identity"]["parameters"], fine)
    if not np.allclose(valley_surface, h1, atol=1e-8, rtol=0):
        raise ValueError("delivery H1 differs from actual final plan coarse source")
    if recovery["valley"] is None:
        if not np.array_equal(original["arrays"]["source_height_m"], plan_arrays["source_height_m"]):
            raise ValueError("non-valley final plan changed original H0")
    else:
        valley_arrays = recovery["valley"]["arrays"]
        if (not np.array_equal(valley_arrays["source_height_m"], original["arrays"]["source_height_m"]) or
                not np.array_equal(valley_arrays["valley_surface_m"], plan_arrays["source_height_m"])):
            raise ValueError("delivery valley H0/H1 source chain differs")
    weights = np.ones(shape)
    weights[[0, -1], :] *= .5
    weights[:, [0, -1]] *= .5
    cell_area = fine["spacing_x_m"] * fine["spacing_z_m"]
    def area(cut):
        return float(np.sum((cut > 1e-9) * weights) * cell_area)
    def volume(cut):
        return float(np.sum(cut * weights) * cell_area)
    budget = inputs["budget"]
    if any(isinstance(value, bool) or not math.isfinite(value) or value < 0 for value in budget.values()):
        raise ValueError("invalid delivered original budget")
    bed_cut, valley_cut = arrays["bed_cut_m"], arrays["valley_cut_m"]
    if (np.any(bed_cut > budget["max_bed_cut_m"] + 1e-9) or area(bed_cut) > budget["max_area_m2"] + 1e-9 or
            volume(bed_cut) > budget["max_cut_volume_m3"] + 1e-9):
        raise ValueError("delivered actual bed exceeds original budget")
    if recovery["valley"] is not None:
        recipe = inputs["valley_recipe"]
        if any(isinstance(value, bool) or not math.isfinite(value) or value < 0 for value in recipe.values()):
            raise ValueError("invalid delivered valley budget")
        if (np.any(valley_cut > recipe["max_valley_depth_m"] + 1e-9) or
                area(valley_cut) > recipe["max_valley_area_m2"] + 1e-9 or
                volume(valley_cut) > recipe["max_valley_volume_m3"] + 1e-9 or
                area(arrays["total_cut_m"]) > recipe["max_total_cut_area_m2"] + 1e-9 or
                volume(arrays["total_cut_m"]) > recipe["max_total_cut_volume_m3"] + 1e-9):
            raise ValueError("delivered cumulative fine ledger exceeds original budget")


def _proof_gate(recovery, arrays):
    if (recovery["accepted"] is not True or recovery["status"] != "accepted" or
            not recovery["attempts"] or recovery["attempts"][-1]["accepted"] is not True or
            recovery["selected_method"] != recovery["attempts"][-1]["method"] or
            any(recovery["attempts"][-1]["failures"].values())):
        raise ValueError("delivery requires genuinely accepted recovery proof")
    shape = recovery["inputs"]["fine"]["shape_zx"]
    if (not isinstance(shape, list) or len(shape) != 2 or
            any(type(size) is not int or size <= 1 for size in shape) or math.prod(shape) > 1000000):
        raise ValueError("invalid delivered proof fine shape")
    record = {key: value for key, value in recovery.items() if key != "identity_sha256"}
    if _fingerprint(record) != recovery["identity_sha256"]:
        raise ValueError("recovery proof payload hash mismatch")
    original, final = recovery["inputs"]["plan"], recovery["final_plan"]
    original_local, original_total = _plan_proof(original)
    final_local, final_total = _plan_proof(final)
    if (not np.allclose(original_local, final_local, rtol=0, atol=1e-8) or
            not math.isclose(original_total, final_total, abs_tol=1e-8, rel_tol=1e-10) or
            not np.array_equal(original["arrays"]["channel_mask"] & original["arrays"]["outlet_mask"],
                               final["arrays"]["channel_mask"] & final["arrays"]["outlet_mask"])):
        raise ValueError("delivered graph changes Q sources or active outlets")
    surface = recovery["surface"]
    for name in ("disconnected_seed_mask", "boundary_contact_mask", "reach_limited_mask"):
        if surface["arrays"][name].dtype != bool or np.any(surface["arrays"][name]):
            raise ValueError("delivered prepared surface retains failure masks")
    if any(surface["summary"]["inundation"][name] != 0 for name in
           ("stage_mismatch_nodes", "reach_limited_nodes", "disconnected_seed_nodes", "boundary_contact_nodes")):
        raise ValueError("delivered prepared surface retains diagnosed failures")
    if (np.any(surface["arrays"]["channel_seed_mask"] & ~surface["arrays"]["wet_mask"]) or
            surface["summary"]["inundation"]["channel_seed_nodes"] !=
            int(surface["arrays"]["channel_seed_mask"].sum())):
        raise ValueError("delivered surface seeds are not actual wet geometry")
    surface_params = _identity(surface)
    if (surface["status"] != "prepared" or surface["summary"]["publishable"] is not True or
            any(surface["summary"]["budget_failures"].values()) or
            any(surface["summary"]["joint_blockers"].values()) or
            surface_params["plan_sha256"] != final["identity_sha256"] or
            surface_params["summary_sha256"] != digest(surface["summary"]) or
            surface_params["output_sha256"] != digest({name: array_hash(value) for name, value in surface["arrays"].items()})):
        raise ValueError("delivered surface acceptance proof is inconsistent")
    if any(surface_params[name] != value for name, value in recovery["inputs"]["budget"].items()):
        raise ValueError("delivered surface budget differs from original recipe")
    valley, ledger = recovery["valley"], recovery["fine_ledger"]
    if (valley is None) != (ledger is None):
        raise ValueError("valley delivery requires cumulative fine ledger")
    if ledger is not None:
        ledger_params, valley_params = _identity(ledger), _identity(valley)
        if (ledger["status"] != "prepared" or any(ledger["summary"]["failures"].values()) or
                valley["summary"]["geometry_feasible"] is not True or any(valley["summary"]["failures"].values()) or
                ledger_params["surface_identity_sha256"] != surface["identity_sha256"] or
                ledger_params["valley_identity_sha256"] != valley["identity_sha256"] or
                ledger_params["summary_sha256"] != digest(ledger["summary"]) or
                ledger_params["arrays_sha256"] != digest({name: array_hash(value) for name, value in ledger["arrays"].items()}) or
                valley_params["replanned_sha256"] != final["identity_sha256"]):
            raise ValueError("delivered cumulative fine ledger proof is inconsistent")
        if (valley_params["arrays_sha256"] != digest(_array_record(valley["arrays"])) or
                valley_params["summary_sha256"] != digest(valley["summary"]) or
                any(valley_params[name] != value or ledger_params[name] != value
                    for name, value in recovery["inputs"]["valley_recipe"].items())):
            raise ValueError("delivered valley arrays or budget proof differs")
        for name in ("source_surface_m", "valley_surface_m", "final_surface_m", "valley_cut_m", "bed_cut_m", "total_cut_m"):
            if not np.allclose(ledger["arrays"][name], arrays[name], atol=1e-8, rtol=0):
                raise ValueError("delivered fine ledger geometry disagrees")
    surface_water, surface_wet = surface["arrays"]["water_surface_m"], surface["arrays"]["wet_mask"]
    if not np.isnan(surface_water[~surface_wet]).all() or not np.isfinite(surface_water[surface_wet]).all():
        raise ValueError("invalid original surface wet/dry geometry")
    expected = _payload(recovery)
    for name in GEOMETRY | GRAPH:
        actual = arrays[name]
        if (actual.dtype != expected[name].dtype or actual.shape != expected[name].shape or
                not np.array_equal(actual, expected[name], equal_nan=True)):
            raise ValueError("delivery payload disagrees with proof: " + name)
    _geometry_gate(arrays, recovery)


def export_surface_network(recovery, vertical_datum, path, *, source_declaration=None):
    """Replay accepted recovery once; atomically deliver terrain plus node hydrology."""
    datum = _named(vertical_datum, "vertical datum")
    declaration = _named(source_declaration, "source declaration")
    destination = Path(path)
    _reject_link_chain(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    validated = validate_surface_network_recovery(recovery)
    if validated["accepted"] is not True or validated["status"] != "accepted":
        raise ValueError("only actually accepted recovery may be delivered")
    arrays = _payload(validated)
    _proof_gate(validated, arrays)
    fine = validated["inputs"]["fine"]
    grid = {name: fine[name] for name in ("origin_x_m", "origin_z_m", "spacing_x_m", "spacing_z_m")}
    grid.update(vertical_datum=datum,
        sea_level_elevation_m=validated["inputs"]["plan"]["identity"]["parameters"]["sea_level_elevation_m"])
    shared = {"recovery_sha256": validated["identity_sha256"], "source_declaration": declaration,
              "original_height_sha256": validated["summary"]["original_height_sha256"]}
    base = TerrainArtifact("base", ArtifactIdentity("Terragenesis", "surface-network-base-delivery", VERSION,
        0, shared), arrays["source_surface_m"], **grid)
    displacement = np.zeros((3, *fine["shape_zx"]))
    displacement[1] = arrays["final_surface_m"] - arrays["source_surface_m"]
    derived = TerrainArtifact("derived", ArtifactIdentity("Terragenesis", "surface-network-derived-delivery",
        VERSION, 0, {**shared, "base_content_id": base.content_id}), arrays["source_surface_m"], **grid,
        displacement_type="vertical", displacement_m=displacement, source_artifact_id=base.content_id)
    proof_arrays = {}
    proof = _tree(validated, proof_arrays)
    arrays.update(proof_arrays)
    if sum(array.nbytes for array in arrays.values()) > MAX_BYTES:
        raise ValueError("delivery payload exceeds resource bound")
    temporary = Path(tempfile.mkdtemp(prefix="." + destination.name + "-", dir=destination.parent))
    try:
        save_artifact(base, temporary / "base")
        save_artifact(derived, temporary / "derived")
        with (temporary / "hydro.npz").open("xb") as stream:
            np.savez_compressed(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        files = {name: _file_hash(temporary / name) for name in (
            "base/manifest.json", "base/arrays.npz", "derived/manifest.json", "derived/arrays.npz", "hydro.npz")}
        manifest = {"format_version": 1, "algorithm_version": VERSION,
            "base_content_id": base.content_id, "derived_content_id": derived.content_id,
            "grid": base.grid_record(), "source_declaration": declaration,
            "recovery_sha256": validated["identity_sha256"], "proof": proof,
            "arrays": _array_record(arrays), "files": files, "hydrology": HYDROLOGY.copy()}
        manifest["content_id"] = digest(manifest)
        with (temporary / "manifest.json").open("x", encoding="utf-8") as stream:
            stream.write(canonical_json(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        load_surface_network_delivery(temporary)
        if destination.exists():
            raise FileExistsError(destination)
        os.rename(temporary, destination)
    finally:
        if temporary.exists():
            resolved = temporary.resolve()
            if resolved.parent != destination.parent.resolve() or not resolved.name.startswith("." + destination.name + "-"):
                raise ValueError("refusing cleanup outside delivery staging directory")
            shutil.rmtree(resolved)
    return destination


def _bounded_npz(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if (len(entries) > 4096 or len({entry.filename for entry in entries}) != len(entries) or
                sum(entry.file_size for entry in entries) > MAX_BYTES):
            raise ValueError("delivery archive exceeds resource bound")
        for entry in entries:
            with archive.open(entry) as stream:
                version = np.lib.format.read_magic(stream)
                if version == (1, 0):
                    shape, _, dtype = np.lib.format.read_array_header_1_0(stream)
                elif version == (2, 0):
                    shape, _, dtype = np.lib.format.read_array_header_2_0(stream)
                else:
                    raise ValueError("unsupported delivery array format")
                size = math.prod(shape) * dtype.itemsize
                if dtype.kind not in "bifu" or dtype.hasobject or size > MAX_BYTES or size != entry.file_size - stream.tell():
                    raise ValueError("invalid delivery array header")
        return sum(entry.file_size for entry in entries)


def load_surface_network_delivery(path):
    """Validate stored arithmetic/provenance only; never recover, prepare or model."""
    directory = Path(path)
    try:
        _reject_link_chain(directory)
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        if directory.is_symlink() or {entry.name for entry in directory.iterdir()} != {"base", "derived", "manifest.json", "hydro.npz"}:
            raise ValueError("invalid delivery directory layout")
        for name in ("base", "derived", "manifest.json", "hydro.npz"):
            item = directory / name
            _reject_link_chain(item)
            if item.is_symlink() or (not item.is_dir() if name in ("base", "derived") else not item.is_file()):
                raise ValueError("delivery entries must be regular files/directories")
        manifest = _read_json(directory / "manifest.json")
        expected = {"format_version", "algorithm_version", "base_content_id", "derived_content_id", "grid",
            "source_declaration", "recovery_sha256", "proof", "arrays", "files", "hydrology", "content_id"}
        if (set(manifest) != expected or type(manifest["format_version"]) is not int or manifest["format_version"] != 1 or
                manifest["algorithm_version"] != VERSION or
                digest({key: value for key, value in manifest.items() if key != "content_id"}) != manifest["content_id"]):
            raise ValueError("invalid delivery manifest identity")
        _named(manifest["source_declaration"], "source declaration")
        _named(manifest["grid"]["vertical_datum"], "vertical datum")
        file_names = {"base/manifest.json", "base/arrays.npz", "derived/manifest.json", "derived/arrays.npz", "hydro.npz"}
        if set(manifest["files"]) != file_names:
            raise ValueError("invalid delivery file hash fields")
        if sum((directory / name).stat().st_size for name in file_names) > MAX_BYTES:
            raise ValueError("delivery files exceed total resource bound")
        for name in file_names:
            item = directory / name
            _reject_link_chain(item)
            if not item.is_file() or item.is_symlink() or _file_hash(item) != manifest["files"][name]:
                raise ValueError("delivery file hash mismatch")
        total_bytes = sum(_bounded_npz(directory / name) for name in
                          ("hydro.npz", "base/arrays.npz", "derived/arrays.npz"))
        if total_bytes > MAX_BYTES:
            raise ValueError("delivery archives exceed total uncompressed resource bound")
        base, derived = load_artifact(directory / "base"), load_artifact(directory / "derived")
        derived.verify_source(base)
        if (base.kind != "base" or derived.kind != "derived" or base.water is not None or derived.water is not None or
                base.content_id != manifest["base_content_id"] or derived.content_id != manifest["derived_content_id"] or
                base.grid_record() != manifest["grid"] or derived.grid_record() != manifest["grid"] or
                derived.displacement_type != "vertical"):
            raise ValueError("delivery terrain package chain mismatch")
        with np.load(directory / "hydro.npz", allow_pickle=False) as archive:
            if set(archive.files) != set(manifest["arrays"]):
                raise ValueError("delivery array fields mismatch")
            arrays = {name: _immutable(archive[name]) for name in archive.files}
        if _array_record(arrays) != manifest["arrays"]:
            raise ValueError("delivery array hash mismatch")
        used = set(GEOMETRY | GRAPH)
        def unpack(value):
            if isinstance(value, dict) and "$array" in value:
                name = value["$array"]
                if not name.startswith("array_") or set(value) != {"$array", "sha256", "shape", "dtype"}:
                    raise ValueError("invalid delivery proof array reference")
                used.add(name)
                if {key: value[key] for key in ("sha256", "shape", "dtype")} != manifest["arrays"][name]:
                    raise ValueError("delivery proof array hash mismatch")
                return arrays[name]
            if isinstance(value, dict):
                return {key: unpack(child) for key, child in value.items()}
            if isinstance(value, list):
                return [unpack(child) for child in value]
            return value
        recovery = unpack(manifest["proof"])
        if used != set(arrays):
            raise ValueError("unused delivery proof arrays")
        if recovery["identity_sha256"] != manifest["recovery_sha256"]:
            raise ValueError("delivery recovery source identity mismatch")
        fine = recovery["inputs"]["fine"]
        if (any(manifest["grid"][name] != fine[name] for name in
                ("origin_x_m", "origin_z_m", "spacing_x_m", "spacing_z_m", "shape_zx")) or
                manifest["grid"]["sea_level_elevation_m"] !=
                recovery["inputs"]["plan"]["identity"]["parameters"]["sea_level_elevation_m"]):
            raise ValueError("delivery grid differs from actual recovery coordinates")
        for artifact, algorithm in ((base, "surface-network-base-delivery"), (derived, "surface-network-derived-delivery")):
            params = artifact.identity.record()["parameters"]
            if (artifact.identity.algorithm != algorithm or artifact.identity.algorithm_version != VERSION or
                    params["recovery_sha256"] != manifest["recovery_sha256"] or
                    params["source_declaration"] != manifest["source_declaration"] or
                    params["original_height_sha256"] != recovery["summary"]["original_height_sha256"]):
                raise ValueError("delivery artifact provenance mismatch")
        if derived.identity.record()["parameters"]["base_content_id"] != base.content_id:
            raise ValueError("delivery derived base provenance mismatch")
        _proof_gate(recovery, arrays)
        if (not np.array_equal(base.reference_elevation_m, arrays["source_surface_m"]) or
                not np.array_equal(derived.reference_elevation_m, arrays["source_surface_m"]) or
                not np.allclose(derived.reference_elevation_m + derived.displacement_m[1], arrays["final_surface_m"], rtol=0, atol=1e-9)):
            raise ValueError("delivery artifacts do not encode actual H0/H2")
        if manifest["hydrology"] != HYDROLOGY:
            raise ValueError("unsupported delivered hydrology semantics")
        return MappingProxyType({"base": base, "derived": derived, "manifest": _freeze(manifest),
            "geometry": MappingProxyType({name: arrays[name] for name in GEOMETRY}),
            "centerline": MappingProxyType({name: arrays[name] for name in GRAPH})})
    except (KeyError, TypeError, OverflowError, RecursionError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError("invalid surface network delivery") from error


def slice_surface_network_delivery(delivery, z_slice, x_slice):
    """Return immutable overlapping grid windows without interpolation or rerouting."""
    grid = delivery["manifest"]["grid"]
    for item, limit in ((z_slice, grid["shape_zx"][0]), (x_slice, grid["shape_zx"][1])):
        if (not isinstance(item, slice) or item.step not in (None, 1) or type(item.start) is not int or
                type(item.stop) is not int or not 0 <= item.start < item.stop <= limit):
            raise ValueError("delivery slice must be a bounded unit-step window")
    arrays = {name: array[z_slice, x_slice] for name, array in delivery["geometry"].items()}
    arrays["water_depth_m"] = _immutable(np.where(arrays["wet_mask"],
        arrays["water_surface_m"] - arrays["final_surface_m"], 0.))
    return MappingProxyType({"origin_x_m": grid["origin_x_m"] + x_slice.start * grid["spacing_x_m"],
        "origin_z_m": grid["origin_z_m"] + z_slice.start * grid["spacing_z_m"],
        "spacing_x_m": grid["spacing_x_m"], "spacing_z_m": grid["spacing_z_m"],
        "vertical_datum": grid["vertical_datum"], "unit": "m", "content_id": delivery["manifest"]["content_id"],
        "arrays": MappingProxyType(arrays)})


def _world_index(value, origin, spacing, count):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)) or not math.isfinite(value):
        raise ValueError("world coordinate must be finite metres")
    coordinate = (value - origin) / spacing
    index = round(coordinate)
    if not 0 <= index < count or not math.isclose(coordinate, index, rel_tol=0, abs_tol=1e-8):
        raise ValueError("world coordinate must address an existing aligned grid node")
    return index


def sample_surface_network(delivery, world_x_m, world_z_m):
    """Read one exact fine node; stage zero is a placeholder only when wet=False."""
    grid = delivery["manifest"]["grid"]
    column = _world_index(world_x_m, grid["origin_x_m"], grid["spacing_x_m"], grid["shape_zx"][1])
    row = _world_index(world_z_m, grid["origin_z_m"], grid["spacing_z_m"], grid["shape_zx"][0])
    return slice_surface_network_delivery(delivery, slice(row, row + 1), slice(column, column + 1))


def slice_surface_network_world(delivery, bounds_xz_m):
    """Read an inclusive aligned (xmin,zmin,xmax,zmax) world-coordinate window."""
    if not isinstance(bounds_xz_m, (tuple, list)) or len(bounds_xz_m) != 4:
        raise ValueError("world bounds must be xmin,zmin,xmax,zmax")
    grid = delivery["manifest"]["grid"]
    min_x, min_z, max_x, max_z = bounds_xz_m
    start_x = _world_index(min_x, grid["origin_x_m"], grid["spacing_x_m"], grid["shape_zx"][1])
    end_x = _world_index(max_x, grid["origin_x_m"], grid["spacing_x_m"], grid["shape_zx"][1])
    start_z = _world_index(min_z, grid["origin_z_m"], grid["spacing_z_m"], grid["shape_zx"][0])
    end_z = _world_index(max_z, grid["origin_z_m"], grid["spacing_z_m"], grid["shape_zx"][0])
    return slice_surface_network_delivery(delivery, slice(start_z, end_z + 1), slice(start_x, end_x + 1))
