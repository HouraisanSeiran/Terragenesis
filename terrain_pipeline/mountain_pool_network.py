"""Finite all-event single-pool cascades; exact engineering weir, no backwater."""

import math
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np
from scipy import ndimage

from terrain_pipeline.mountain_lake_experiment import first_lake_ownership
from terrain_pipeline.mountain_depression_geometry import _hash, _json


MAX_STEPS = 1344
MAX_POOLS = 32
MAX_WORK = 4000000
WEIR_COEFFICIENT = 1.7
ABS_VOLUME_TOLERANCE_M3 = 1e-6
REL_VOLUME_TOLERANCE = 1e-10
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
POOL_ARRAY_KEYS = frozenset(("lake_ids", "pool_downstream", "pool_order", "allocation_counts", "owned_mask",
                            "first_lake_id",
                            "stage_m", "storage_m3", "lateral_volume_m3", "upstream_volume_m3",
                            "outflow_volume_m3", "pool_residual_m3", "external_outflow_volume_m3", "joint_residual_m3"))


def screen_complete_pool_groups(result, screening):
    """Complete contribution groups, every discrete pool event independently gated."""
    arrays = result["arrays"]
    owners = arrays["outlet_owner"].ravel()
    pool_groups = owners[arrays["spill_inside"]]
    decisions = {item["lake_id"]: item for item in screening["decisions"]}
    first = first_lake_ownership(result)
    proposed = []
    bbox = ndimage.find_objects(arrays["lake_id"])
    for group in np.argsort(-arrays["outlet_area_m2"], kind="stable"):
        lakes = np.flatnonzero(pool_groups == group) + 1
        if not lakes.size or lakes.size > MAX_POOLS:
            continue
        flags = []
        paths = {}
        headrooms = {}
        for lake in lakes:
            event = decisions[int(lake)]
            if "disconnected_events" not in event or event["disconnected_events"] > 0:
                flags.append("multiple_initial_pools_or_unverified_events")
                continue
            path = [int(arrays["spill_outside"][lake - 1])]
            while arrays["receiver"][path[-1]] >= 0 and arrays["lake_id"].flat[path[-1]] == 0:
                target = int(arrays["receiver"][path[-1]])
                if target in path:
                    flags.append("cascade_cycle")
                    break
                path.append(target)
            if np.any(np.diff(arrays["H0_m"].ravel()[path]) > 1e-9):
                flags.append("downstream_original_bed_uphill")
            slices = bbox[lake - 1]
            expanded = tuple(slice(max(0, item.start - 1), min(arrays["H0_m"].shape[index], item.stop + 1)) for index, item in enumerate(slices))
            basin = arrays["lake_id"][expanded] == lake
            shore = ndimage.binary_dilation(basin, structure=ndimage.generate_binary_structure(2, 1)) & ~basin
            spill_row, spill_column = divmod(int(arrays["spill_outside"][lake - 1]), arrays["H0_m"].shape[1])
            shore[spill_row - expanded[0].start, spill_column - expanded[1].start] = False
            head = float(arrays["H0_m"][expanded][shore].min() - arrays["lake_stage_m"][lake - 1])
            if head <= 1e-9:
                flags.append("multiple_equal_or_lower_spills")
            paths[str(int(lake))] = path
            headrooms[str(int(lake))] = max(0., min(1., head * .5))
        proposed.append({"group": int(group), "outlet_cell": int(arrays["outlet_cells"][group]),
                         "area_m2": float(arrays["outlet_area_m2"][group]),
                         "lake_ids": lakes.tolist(), "reason_flags": sorted(set(flags)),
                         "status": "static_complete_pool_candidate" if not flags else "refused",
                         "paths": paths, "max_head_m": headrooms,
                         "pool_resolution": "30m_discrete_storage_cells_not_resolved_natural_lakes"})
    return {"groups": proposed, "first_lake_id": first,
            "selection_rule": "descending_complete_window_area_all_event_single_pools_no_unmodeled_shore",
            "max_pools": MAX_POOLS}


def route_complete_pool_group(result, proposal, *, local_q_m3_s, cell_owner, hru_area_m2, dt_s=900.):
    """Backward Euler V(next)+dt*C*b*head^1.5 = V(before)+incoming."""
    arrays, metadata = result["arrays"], result["metadata"]
    if proposal["status"] != "static_complete_pool_candidate":
        raise ValueError("complete static pool certificate required")
    _validate_forcing(result, local_q_m3_s, cell_owner, hru_area_m2, dt_s)
    if not isinstance(local_q_m3_s, np.ndarray) or local_q_m3_s.ndim != 2:
        raise ValueError("two-dimensional forcing required")
    steps, hrus = local_q_m3_s.shape
    lakes = np.asarray(proposal["lake_ids"], dtype=np.int64)
    cell_counts = np.bincount(arrays["lake_id"].ravel(), minlength=arrays["lake_stage_m"].size + 1)[lakes]
    if not 1 <= steps <= MAX_STEPS or lakes.size > MAX_POOLS or steps * int(cell_counts.sum()) * 64 > MAX_WORK:
        return {"status": "pool_work_limit", "requested_work": int(steps * cell_counts.sum() * 64)}
    if local_q_m3_s.dtype != np.dtype("float64") or not np.isfinite(local_q_m3_s).all() or (local_q_m3_s < 0).any():
        raise ValueError("invalid local forcing")
    group = proposal["group"]
    owned = arrays["outlet_owner"] == group
    first = first_lake_ownership(result)
    counts = np.zeros((lakes.size + 1, hrus), dtype=np.int64)
    counts[0] = np.bincount(cell_owner[owned & (first == 0)], minlength=hrus)
    for index, lake in enumerate(lakes):
        counts[index + 1] = np.bincount(cell_owner[owned & (first == lake)], minlength=hrus)
    if counts.sum() != owned.sum():
        raise ValueError("upstream area lost or duplicated")
    lateral = local_q_m3_s @ (counts * metadata["spacing_m"] ** 2 / hru_area_m2).T * dt_s
    stages = np.zeros((steps + 1, lakes.size), dtype=np.float64)
    storage = np.zeros_like(stages)
    outflow = np.zeros((steps, lakes.size), dtype=np.float64)
    upstream = np.zeros_like(outflow)
    residual = np.zeros_like(outflow)
    terminal = lateral[:, 0].copy()
    pool_index = {int(lake): index for index, lake in enumerate(lakes)}
    downstream = np.full(lakes.size, -1, dtype=np.int64)
    for index, lake in enumerate(lakes):
        target_lake = int(arrays["lake_downstream_id"][lake - 1])
        if target_lake > 0:
            if target_lake not in pool_index:
                raise ValueError("downstream pool omitted from complete group")
            downstream[index] = pool_index[target_lake]
    rank = np.empty(arrays["receiver"].size, dtype=np.int64)
    rank[arrays["order"]] = np.arange(rank.size)
    pool_order = np.argsort(-rank[arrays["spill_inside"][lakes - 1]], kind="stable")
    failures = []
    floors = [arrays["H0_m"][arrays["lake_id"] == lake] for lake in lakes]
    for index, values in enumerate(floors):
        stages[0, index] = float(values.min())
    area = metadata["spacing_m"] ** 2
    width = metadata["spacing_m"]
    completed = 0
    for step in range(steps):
        next_storage = storage[step].copy()
        next_stage = stages[step].copy()
        next_outflow = np.zeros(lakes.size)
        next_upstream = np.zeros(lakes.size)
        next_residual = np.zeros(lakes.size)
        terminal_step = lateral[step, 0]
        failed = False
        for index in pool_order:
            lake = int(lakes[index])
            spill = float(arrays["lake_stage_m"][lake - 1])
            upper = spill + proposal["max_head_m"][str(lake)]
            target = storage[step, index] + lateral[step, index + 1] + next_upstream[index]
            tolerance = ABS_VOLUME_TOLERANCE_M3 + REL_VOLUME_TOLERANCE * max(target, storage[step, index])
            def capacity(stage):
                return float(np.maximum(stage - floors[index], 0).sum() * area)
            def discharge(stage):
                return WEIR_COEFFICIENT * width * max(stage - spill, 0.) ** 1.5
            available = capacity(upper) + dt_s * discharge(upper)
            if target > available + tolerance:
                failures.append({"step": step, "lake_id": lake, "code": "valid_shore_headroom_exceeded",
                                 "incoming_plus_storage_m3": float(target), "available_m3": float(available),
                                 "max_head_m": proposal["max_head_m"][str(lake)]})
                failed = True
                break
            lower = float(floors[index].min())
            stage = lower
            for iteration in range(64):
                stage = (lower + upper) / 2
                volume = capacity(stage)
                release = dt_s * discharge(stage)
                error = volume + release - target
                if abs(error) <= tolerance:
                    break
                if error > 0:
                    upper = stage
                else:
                    lower = stage
            else:
                failures.append({"step": step, "lake_id": lake, "code": "solver_precision_limit"})
                failed = True
                break
            next_stage[index], next_storage[index] = stage, volume
            next_outflow[index], next_residual[index] = release, error
            target_pool = downstream[index]
            if target_pool >= 0:
                next_upstream[target_pool] += release
            else:
                terminal_step += release
        if failed:
            break
        for index, target_pool in enumerate(downstream):
            if target_pool >= 0 and next_stage[target_pool] > arrays["lake_stage_m"][lakes[index] - 1] + 1e-9:
                failures.append({"step": step, "lake_id": int(lakes[index]), "code": "receiving_pool_submerges_free_weir"})
                failed = True
                break
        if failed:
            break
        storage[step + 1], stages[step + 1] = next_storage, next_stage
        outflow[step], upstream[step], residual[step] = next_outflow, next_upstream, next_residual
        terminal[step] = terminal_step
        completed += 1
    incoming = lateral[:completed].sum(axis=1)
    joint_residual = incoming - terminal[:completed] - np.diff(storage[:completed + 1].sum(axis=1))
    returned = {"status": "complete_pool_group_feasible" if completed == steps else "complete_pool_group_refused",
            "scope": "finite_complete_window_contribution_group_one_way_pool_cascade_no_backwater_or_river_storage",
            "proposal": proposal, "completed_steps": completed, "requested_steps": steps,
            "failures": failures, "dt_s": dt_s, "weir_coefficient": WEIR_COEFFICIENT,
            "weir_width_m": width, "abs_volume_tolerance_m3": ABS_VOLUME_TOLERANCE_M3,
            "rel_volume_tolerance": REL_VOLUME_TOLERANCE,
            "arrays": {"lake_ids": lakes, "pool_downstream": downstream, "pool_order": pool_order,
                       "allocation_counts": counts, "owned_mask": owned,
                       "first_lake_id": first,
                       "stage_m": stages[:completed + 1], "storage_m3": storage[:completed + 1],
                       "lateral_volume_m3": lateral[:completed], "upstream_volume_m3": upstream[:completed],
                       "outflow_volume_m3": outflow[:completed], "pool_residual_m3": residual[:completed],
                       "external_outflow_volume_m3": terminal[:completed], "joint_residual_m3": joint_residual}}
    validate_complete_pool_group(returned, result, local_q_m3_s=local_q_m3_s,
                                 cell_owner=cell_owner, hru_area_m2=hru_area_m2)
    return returned


def _validate_forcing(geometry, local, owner, area, dt_s):
    shape = geometry["arrays"]["H0_m"].shape
    if type(dt_s) not in (int, float) or not math.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("positive physical timestep required")
    if not isinstance(area, np.ndarray) or area.dtype != np.dtype("float64") or area.ndim != 1 or not 1 <= area.size <= 256 or not np.isfinite(area).all() or (area <= 0).any():
        raise ValueError("positive finite HRU areas required")
    if not isinstance(owner, np.ndarray) or owner.dtype != np.dtype("int64") or owner.shape != shape or (owner < 0).any() or (owner >= area.size).any():
        raise ValueError("complete valid HRU owner required")
    expected = np.bincount(owner.ravel(), minlength=area.size) * geometry["metadata"]["spacing_m"] ** 2
    if not np.array_equal(area, expected):
        raise ValueError("original complete HRU area mismatch")
    if not isinstance(local, np.ndarray) or local.dtype != np.dtype("float64") or local.ndim != 2 or local.shape[1] != area.size or not 1 <= local.shape[0] <= MAX_STEPS or not np.isfinite(local).all() or (local < 0).any():
        raise ValueError("bounded finite local forcing required")


def validate_complete_pool_group(saved, geometry, *, local_q_m3_s, cell_owner, hru_area_m2):
    """Static saved local balances and weir equations; never rerun pool dynamics."""
    arrays = saved["arrays"]
    _validate_forcing(geometry, local_q_m3_s, cell_owner, hru_area_m2, saved["dt_s"])
    if set(arrays) != POOL_ARRAY_KEYS:
        raise ValueError("fixed pool schema required")
    terrain = geometry["arrays"]
    spacing = geometry["metadata"]["spacing_m"]
    steps = saved["completed_steps"]
    lakes = arrays["lake_ids"]
    count = lakes.size
    group = saved["proposal"]["group"]
    if not 0 <= steps <= saved["requested_steps"] <= MAX_STEPS or count > MAX_POOLS:
        raise ValueError("static pool resource ceiling")
    if saved["requested_steps"] != local_q_m3_s.shape[0]:
        raise ValueError("requested forcing length")
    if saved["status"] == "complete_pool_group_feasible":
        if steps != saved["requested_steps"] or saved["failures"]:
            raise ValueError("pool success status forgery")
    elif saved["status"] == "complete_pool_group_refused":
        if steps == saved["requested_steps"] or not saved["failures"] or saved["failures"][0]["step"] != steps:
            raise ValueError("pool failure status forgery")
    else:
        raise ValueError("unknown pool status")
    if not np.array_equal(np.sort(arrays["pool_order"]), np.arange(count)):
        raise ValueError("pool order permutation")
    pool_rank = np.empty(count, dtype=np.int64)
    pool_rank[arrays["pool_order"]] = np.arange(count)
    for index, target in enumerate(arrays["pool_downstream"]):
        if target >= 0 and (target >= count or pool_rank[target] <= pool_rank[index]):
            raise ValueError("pool order downstream dependency")
    for key, values in arrays.items():
        if not isinstance(values, np.ndarray) or not np.isfinite(values).all():
            raise ValueError("nonfinite saved pool data")
        if key not in ("stage_m", "pool_downstream", "pool_residual_m3", "joint_residual_m3") and values.dtype.kind == "f" and (values < 0).any():
            raise ValueError("negative water")
    owned = terrain["outlet_owner"] == group
    if not np.array_equal(arrays["owned_mask"], owned):
        raise ValueError("partial contribution group")
    counts = arrays["allocation_counts"]
    if not np.array_equal(counts.sum(axis=0), np.bincount(cell_owner[owned], minlength=hru_area_m2.size)):
        raise ValueError("omitted or double-counted upstream HRU area")
    if not np.array_equal(np.sort(lakes), np.flatnonzero(terrain["outlet_owner"].ravel()[terrain["spill_inside"]] == group) + 1):
        raise ValueError("pool omitted from complete group")
    if (saved["weir_coefficient"] != WEIR_COEFFICIENT or saved["weir_width_m"] != spacing
            or saved["abs_volume_tolerance_m3"] != ABS_VOLUME_TOLERANCE_M3
            or saved["rel_volume_tolerance"] != REL_VOLUME_TOLERANCE):
        raise ValueError("weir or tolerance identity forgery")
    first = arrays["first_lake_id"].ravel()
    labels = terrain["lake_id"].ravel()
    donors = np.flatnonzero(terrain["receiver"] >= 0)
    if arrays["first_lake_id"].shape != owned.shape or arrays["first_lake_id"].dtype != np.dtype("int64"):
        raise ValueError("saved first lake schema")
    if not np.array_equal(first[labels > 0], labels[labels > 0]):
        raise ValueError("lake anchor mismatch")
    dry_donors = donors[labels[donors] == 0]
    if not np.array_equal(first[dry_donors], first[terrain["receiver"][dry_donors]]) or (first[terrain["receiver"] < 0] != 0).any():
        raise ValueError("saved local first-lake recurrence")
    expected_counts = np.zeros_like(counts)
    expected_counts[0] = np.bincount(cell_owner[owned & (first.reshape(owned.shape) == 0)], minlength=hru_area_m2.size)
    for index, lake in enumerate(lakes):
        expected_counts[index + 1] = np.bincount(cell_owner[owned & (first.reshape(owned.shape) == lake)], minlength=hru_area_m2.size)
    if not np.array_equal(counts, expected_counts):
        raise ValueError("first-pool allocation forged")
    pool_index = {int(lake): index for index, lake in enumerate(lakes)}
    expected_downstream = np.array([pool_index.get(int(terrain["lake_downstream_id"][lake - 1]), -1) for lake in lakes])
    if not np.array_equal(arrays["pool_downstream"], expected_downstream):
        raise ValueError("cascade connectivity forged")
    lateral = local_q_m3_s[:steps] @ (counts * spacing ** 2 / hru_area_m2).T * saved["dt_s"]
    def equal(actual, expected, name, tolerance=1e-8):
        if actual.shape != expected.shape or not np.allclose(actual, expected, rtol=1e-12, atol=tolerance):
            raise ValueError("static pool mismatch: " + name)
    equal(arrays["lateral_volume_m3"], lateral, "authentic local forcing")
    if arrays["storage_m3"].shape != (steps + 1, count) or arrays["stage_m"].shape != (steps + 1, count):
        raise ValueError("state shape")
    if (arrays["storage_m3"][0] != 0).any():
        raise ValueError("initial water invented")
    releases = arrays["outflow_volume_m3"]
    upstream = np.zeros((steps, count), dtype=np.float64)
    for index, downstream in enumerate(arrays["pool_downstream"]):
        if downstream >= 0:
            if downstream >= count:
                raise ValueError("invalid cascade downstream")
            upstream[:, downstream] += releases[:, index]
    equal(arrays["upstream_volume_m3"], upstream, "each internal release injected once")
    for index, lake in enumerate(lakes):
        stage = arrays["stage_m"][:, index]
        basin = terrain["lake_id"] == lake
        slices = ndimage.find_objects(basin.astype(np.int64))[0]
        cropped = basin[slices]
        local_height = terrain["H0_m"][slices]
        floors = local_height[cropped]
        for level in np.unique(floors):
            if ndimage.label(cropped & (local_height <= level), ndimage.generate_binary_structure(2, 1))[1] > 1:
                raise ValueError("multi-initial-pool caller proposal forged")
        shore = ndimage.binary_dilation(basin, structure=ndimage.generate_binary_structure(2, 1)) & ~basin
        spill_cell = int(terrain["spill_outside"][lake - 1])
        shore.flat[spill_cell] = False
        spill = terrain["lake_stage_m"][lake - 1]
        expected_head = min(1., float(terrain["H0_m"][shore].min() - spill) * .5)
        if expected_head <= 0 or saved["proposal"]["max_head_m"][str(int(lake))] != expected_head:
            raise ValueError("shore headroom forged")
        path = saved["proposal"]["paths"][str(int(lake))]
        if len(path) < 1 or path[0] != spill_cell or any(terrain["receiver"][before] != after for before, after in zip(path[:-1], path[1:])):
            raise ValueError("downstream path identity")
        if np.any(np.diff(terrain["H0_m"].ravel()[path]) > 1e-9):
            raise ValueError("downstream path uphill")
        target_pool = arrays["pool_downstream"][index]
        if target_pool < 0:
            if terrain["receiver"][path[-1]] != -1 or not terrain["boundary_mask"].flat[path[-1]]:
                raise ValueError("unproven external terminal")
        elif terrain["lake_id"].flat[path[-1]] != lakes[target_pool]:
            raise ValueError("receiving pool path mismatch")
        if target_pool >= 0 and (arrays["stage_m"][:, target_pool] > spill + 1e-9).any():
            raise ValueError("submerged free-weir invalid")
        volume = np.maximum(stage[:, None] - floors[None, :], 0).sum(axis=1) * spacing ** 2
        equal(arrays["storage_m3"][:, index], volume, "native capacity equation")
        spill = terrain["lake_stage_m"][lake - 1]
        head = np.maximum(stage[1:] - spill, 0)
        if (head > saved["proposal"]["max_head_m"][str(int(lake))] + 1e-9).any():
            raise ValueError("shore limit forged")
        expected_release = saved["dt_s"] * WEIR_COEFFICIENT * spacing * head ** 1.5
        equal(releases[:, index], expected_release, "exact engineering weir")
    change = np.diff(arrays["storage_m3"], axis=0)
    pool_residual = lateral[:, 1:] + upstream - releases - change
    equal(arrays["pool_residual_m3"], -pool_residual, "per-pool ledger sign")
    tolerance = ABS_VOLUME_TOLERANCE_M3 + REL_VOLUME_TOLERANCE * np.maximum(arrays["storage_m3"][:-1], lateral[:, 1:] + upstream + arrays["storage_m3"][:-1])
    if (np.abs(pool_residual) > tolerance * 1.01).any():
        raise ValueError("local pool volume imbalance")
    terminal = lateral[:, 0] + releases[:, arrays["pool_downstream"] < 0].sum(axis=1)
    equal(arrays["external_outflow_volume_m3"], terminal, "explicit external exit")
    joint = lateral.sum(axis=1) - terminal - change.sum(axis=1)
    equal(arrays["joint_residual_m3"], joint, "complete group ledger")
    if (np.abs(joint) > tolerance.sum(axis=1) * 1.01).any():
        raise ValueError("complete group water budget")
    return {"max_pool_residual_m3": float(np.abs(pool_residual).max(initial=0)),
            "max_joint_residual_m3": float(np.abs(joint).max(initial=0)),
            "input_volume_m3": float(lateral.sum()), "external_outflow_m3": float(terminal.sum()),
            "final_storage_m3": float(arrays["storage_m3"][-1].sum()),
            "total_residual_m3": float(lateral.sum() - terminal.sum() - arrays["storage_m3"][-1].sum())}


def save_pool_group(path, saved, geometry, *, local_q_m3_s, cell_owner, hru_area_m2):
    validate_complete_pool_group(saved, geometry, local_q_m3_s=local_q_m3_s,
                                 cell_owner=cell_owner, hru_area_m2=hru_area_m2)
    metadata = {key: value for key, value in saved.items() if key != "arrays"}
    binding = {"geometry_H0_sha256": geometry["metadata"]["H0_sha256"],
               "source_binding": geometry["metadata"]["source_binding"],
               "forcing_sha256": _hash(local_q_m3_s), "cell_owner_sha256": _hash(cell_owner),
               "hru_area_sha256": _hash(hru_area_m2)}
    manifest = {"metadata": metadata, "binding": binding,
                "hashes": {key: _hash(value) for key, value in saved["arrays"].items()}}
    payload = _json(manifest).encode("ascii")
    if len(payload) > 65536:
        raise ValueError("pool metadata ceiling")
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    descriptor, temporary = tempfile.mkstemp(prefix=".mountain-pool-", suffix=".npz", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            np.savez_compressed(stream, manifest=np.frombuffer(payload, dtype=np.uint8), **saved["arrays"])
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


def load_pool_group(path, geometry, *, local_q_m3_s, cell_owner, hru_area_m2):
    """Static exact-equation checks, never advance, assemble, or infer terrain."""
    expected_names = {key + ".npy" for key in POOL_ARRAY_KEYS} | {"manifest.npy"}
    with open(path, "rb") as stream:
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            if len(members) != len(expected_names) or {item.filename for item in members} != expected_names:
                raise ValueError("pool archive schema")
            if sum(item.file_size for item in members) > MAX_ARCHIVE_BYTES:
                raise ValueError("pool archive resource ceiling")
            headers = {}
            for member in members:
                with archive.open(member) as item:
                    if np.lib.format.read_magic(item) != (1, 0):
                        raise ValueError("NPY version")
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(item)
                    key = member.filename[:-4]
                    headers[key] = shape
                    expected_dtype = np.dtype("uint8" if key == "manifest" else "bool" if key == "owned_mask" else "int64" if key in ("first_lake_id", "lake_ids", "pool_downstream", "pool_order", "allocation_counts") else "float64")
                    if fortran or dtype != expected_dtype or dtype.hasobject or math.prod(shape) * dtype.itemsize + item.tell() != member.file_size:
                        raise ValueError("pool header schema")
                    if key == "manifest" and (len(shape) != 1 or shape[0] > 65536):
                        raise ValueError("pool metadata ceiling")
                    if key in ("owned_mask", "first_lake_id") and shape != geometry["arrays"]["H0_m"].shape:
                        raise ValueError("pool grid shape")
                    if key not in ("owned_mask", "first_lake_id", "manifest") and (len(shape) not in (1, 2) or any(value > MAX_STEPS + 1 for value in shape)):
                        raise ValueError("pool header dimensions")
            count = headers["lake_ids"][0]
            if headers["lake_ids"] != (count,) or not 1 <= count <= MAX_POOLS:
                raise ValueError("pool lake-axis resource ceiling")
            state_shape = headers["stage_m"]
            if len(state_shape) != 2:
                raise ValueError("pool state header dimensions")
            completed = state_shape[0] - 1
            if not 0 <= completed <= local_q_m3_s.shape[0]:
                raise ValueError("pool completed header range")
            shapes = {"lake_ids": (count,), "pool_downstream": (count,), "pool_order": (count,),
                      "allocation_counts": (count + 1, hru_area_m2.size),
                      "stage_m": (completed + 1, count), "storage_m3": (completed + 1, count),
                      "lateral_volume_m3": (completed, count + 1),
                      "upstream_volume_m3": (completed, count), "outflow_volume_m3": (completed, count),
                      "pool_residual_m3": (completed, count), "external_outflow_volume_m3": (completed,),
                      "joint_residual_m3": (completed,)}
            for key, shape in shapes.items():
                if headers[key] != shape:
                    raise ValueError("exact pool header shape: " + key)
        stream.seek(0)
        with np.load(stream, allow_pickle=False) as archive:
            manifest = json.loads(archive["manifest"].tobytes().decode("ascii"))
            arrays = {key: archive[key].copy() for key in POOL_ARRAY_KEYS}
    expected_binding = {"geometry_H0_sha256": geometry["metadata"]["H0_sha256"],
                        "source_binding": geometry["metadata"]["source_binding"],
                        "forcing_sha256": _hash(local_q_m3_s), "cell_owner_sha256": _hash(cell_owner),
                        "hru_area_sha256": _hash(hru_area_m2)}
    if manifest["binding"] != expected_binding or set(manifest["hashes"]) != POOL_ARRAY_KEYS:
        raise ValueError("external pool trust mismatch")
    for key, values in arrays.items():
        if _hash(values) != manifest["hashes"][key]:
            raise ValueError("pool integrity")
    saved = dict(manifest["metadata"], arrays=arrays)
    validate_complete_pool_group(saved, geometry, local_q_m3_s=local_q_m3_s,
                                 cell_owner=cell_owner, hru_area_m2=hru_area_m2)
    saved["arrays"] = {key: np.frombuffer(value.tobytes(), dtype=value.dtype).reshape(value.shape) for key, value in arrays.items()}
    return saved
