"""Independent fine-chain V(h) conductance prototype; no forest impersonation."""

import math
import json
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np
from scipy import ndimage

from terrain_pipeline.surface_variable_storage import volume, _invert
from terrain_pipeline.lake import _hash as _hash
from terrain_pipeline.lake import depression_json as _json
from terrain_pipeline.mountain_fine_geometry import validate_fine_chain


MAX_STEPS = 4096
MAX_SUPPORT = 250000
MAX_WORK = 2000000
CONDUCTANCE_M2_S = 0.01
MAX_DT_S = 10.0
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024


def fine_storage_support(chain):
    """Partition longitudinal quadrature exactly once across shared fine nodes."""
    arrays = chain["arrays"]
    bed = arrays["H2_m"]
    area = arrays["quadrature_area_m2"]
    if bed.shape != area.shape or bed.size > MAX_SUPPORT or not np.isfinite(bed).all() or (area <= 0).any():
        raise ValueError("invalid fine support/resource")
    nodes = chain["segments"] + 1
    rows = bed.shape[0]
    samples_per_segment = (rows - 1) // chain["segments"]
    owner = np.minimum(np.floor(np.arange(rows) / samples_per_segment + .5).astype(np.int64), nodes - 1)
    beds = []
    weights = []
    offsets = [0]
    min_bed = np.zeros(nodes)
    max_stage = np.zeros(nodes)
    min_bank = np.zeros(nodes)
    event_counts = np.zeros(nodes, dtype=np.int64)
    for node in range(nodes):
        selected = owner == node
        values = bed[selected].ravel()
        support = area[selected].ravel()
        beds.append(values)
        weights.append(support)
        offsets.append(offsets[-1] + values.size)
        min_bed[node] = float(values.min())
        min_bank[node] = float(np.minimum(bed[selected, 0], bed[selected, -1]).min())
        max_stage[node] = min_bank[node] - 1e-6
        levels = np.unique(bed[selected][bed[selected] <= max_stage[node]])
        event_counts[node] = levels.size
        for level in levels:
            if ndimage.label(bed[selected] <= level, ndimage.generate_binary_structure(2, 1))[1] > 1:
                raise ValueError("fine support contains disconnected initial pools below valid banks")
    interfaces = np.flatnonzero(np.diff(owner) != 0)
    sill = np.r_[bed[0].min(), np.maximum(bed[interfaces].min(axis=1), bed[interfaces + 1].min(axis=1)), bed[-1].min()]
    return {"offsets": np.asarray(offsets, dtype=np.int64), "beds_m": np.concatenate(beds),
            "weights_m2": np.concatenate(weights), "row_owner": owner,
            "min_bed_m": min_bed, "max_stage_m": max_stage, "min_bank_m": min_bank,
            "side_margin_m": min_bank - min_bed,
            "interface_before_rows": interfaces.astype(np.int64), "interface_sill_m": sill,
            "single_pool_event_count": event_counts,
            "source_H2_sha256": _hash(bed), "source_area_sha256": _hash(area)}


def map_chain_upstream_runoff(geometry, chain, *, local_q_m3_s, cell_owner, hru_area_m2):
    """Full new-receiver donor subtree, excluding upstream lake storage shortcuts."""
    arrays = geometry["arrays"]
    start = int(chain["arrays"]["chain_cells"][0])
    upstream = np.zeros(arrays["receiver"].size, dtype=bool)
    upstream[start] = True
    for cell in arrays["order"]:
        target = arrays["receiver"][cell]
        if target >= 0 and upstream[target]:
            upstream[cell] = True
    mask = upstream.reshape(arrays["H0_m"].shape)
    upstream_lakes = np.unique(arrays["lake_id"][mask])
    upstream_lakes = upstream_lakes[upstream_lakes > 0]
    counts = np.bincount(cell_owner[mask], minlength=hru_area_m2.size)
    q = local_q_m3_s @ (counts * geometry["metadata"]["spacing_m"] ** 2 / hru_area_m2)
    return {"subtree_mask": mask, "allocation_counts": counts,
            "upstream_lake_ids": upstream_lakes,
            "rainfall_only_instantaneous_local_q_m3_s": q,
            "status": "requires_upstream_lake_outflow_binding" if upstream_lakes.size else "complete_dry_upstream_subtree",
            "area_m2": float(mask.sum() * geometry["metadata"]["spacing_m"] ** 2),
            "limitation": "instantaneous_local_runoff_sum_is_not_a_routed_lake_or_hillslope_hydrograph"}


def prepare_fine_storage(chain, geometry, *, initial_stage_m, local_q_m3_s, upstream_stage_m,
                         tailwater_stage_m, dt_s, conductance_m2_s=CONDUCTANCE_M2_S):
    """Wet/dry sill gating and signed flux; donor-limited explicit volume update."""
    validate_fine_chain(chain, geometry)
    support = fine_storage_support(chain)
    nodes = support["min_bed_m"].size
    if not isinstance(local_q_m3_s, np.ndarray) or local_q_m3_s.ndim != 2:
        raise ValueError("resource-checkable forcing required")
    steps = local_q_m3_s.shape[0]
    if not 1 <= steps <= MAX_STEPS or local_q_m3_s.shape[1] != nodes or steps * (nodes + support["beds_m"].size) > MAX_WORK:
        raise ValueError("fine dynamic resource ceiling")
    if isinstance(dt_s, bool) or not math.isfinite(dt_s) or not 0 < dt_s <= MAX_DT_S or conductance_m2_s != CONDUCTANCE_M2_S:
        raise ValueError("fixed fine dynamic dt/conductance ceiling")
    initial = np.asarray(initial_stage_m)
    upstream = np.asarray(upstream_stage_m)
    tailwater = np.asarray(tailwater_stage_m)
    if initial.shape != (nodes,) or upstream.shape != (steps + 1,) or tailwater.shape != (steps + 1,):
        raise ValueError("explicit open seam heads required")
    if not all(np.isfinite(values).all() for values in (initial, upstream, tailwater, local_q_m3_s)) or (local_q_m3_s < 0).any():
        raise ValueError("invalid fine forcing")
    offsets, beds, weights = support["offsets"], support["beds_m"], support["weights_m2"]
    stages = [initial.copy()]
    storage = np.array([volume(initial[index], beds[offsets[index]:offsets[index + 1]], weights[offsets[index]:offsets[index + 1]]) for index in range(nodes)])
    storages = [storage]
    fluxes = []
    ledgers = []
    failure = None
    if (initial < support["min_bed_m"] - 1e-9).any() or (initial > support["max_stage_m"] + 1e-9).any():
        failure = {"step": -1, "reason": "initial_outside_bed_or_bank"}
    for step in range(steps):
        if failure is not None:
            break
        current = stages[-1]
        heads = np.r_[upstream[step], current, tailwater[step]]
        sill = support["interface_sill_m"]
        effective = np.maximum(heads[:-1], sill) - np.maximum(heads[1:], sill)
        flux = conductance_m2_s * effective
        for node in range(nodes):
            outgoing = max(0., -flux[node]) + max(0., flux[node + 1])
            available = storage[node] + dt_s * local_q_m3_s[step, node]
            if outgoing * dt_s > available and outgoing > 0:
                factor = available / (outgoing * dt_s)
                if flux[node] < 0:
                    flux[node] *= factor
                if flux[node + 1] > 0:
                    flux[node + 1] *= factor
        after = storage + dt_s * (local_q_m3_s[step] + flux[:-1] - flux[1:])
        if (after < -1e-10).any():
            failure = {"step": step, "reason": "negative_storage"}
            break
        after = np.maximum(after, 0.)
        next_stage = np.array([_invert(float(after[index]), beds[offsets[index]:offsets[index + 1]], weights[offsets[index]:offsets[index + 1]]) for index in range(nodes)])
        if (next_stage > support["max_stage_m"] + 1e-9).any():
            failure = {"step": step, "reason": "resolved_bank_overtopped", "nodes": np.flatnonzero(next_stage > support["max_stage_m"] + 1e-9).tolist()}
            break
        residual = after.sum() - storage.sum() - dt_s * (local_q_m3_s[step].sum() + flux[0] - flux[-1])
        ledgers.append([storage.sum(), dt_s * local_q_m3_s[step].sum(), dt_s * flux[0], dt_s * flux[-1], after.sum(), residual])
        stages.append(next_stage)
        storages.append(after)
        fluxes.append(flux)
        storage = after
    return {"status": "fine_storage_completed" if failure is None else "fine_storage_refused",
            "scope": "fine_local_chain_engineering_storage_conductance_not_Saint_Venant_or_complete_forest",
            "failure": failure, "committed_steps": len(fluxes), "requested_steps": steps,
            "dt_s": float(dt_s), "conductance_m2_s": conductance_m2_s,
            "support": support,
            "arrays": {"initial_stage_m": initial.copy(), "local_q_m3_s": local_q_m3_s.copy(),
                       "upstream_stage_m": upstream.copy(), "tailwater_stage_m": tailwater.copy(),
                       "stage_m": np.asarray(stages), "storage_m3": np.asarray(storages),
                       "qedges_m3_s": np.asarray(fluxes).reshape(-1, nodes + 1),
                       "ledger_m3": np.asarray(ledgers).reshape(-1, 6)}}


def validate_fine_storage(saved, chain, geometry):
    """Static source geometry, V(h), signed local flux and per-node continuity."""
    support = saved["support"]
    validate_fine_chain(chain, geometry)
    source = chain["arrays"]
    if support["source_H2_sha256"] != _hash(source["H2_m"]) or support["source_area_sha256"] != _hash(source["quadrature_area_m2"]):
        raise ValueError("fine support source binding")
    owner = support["row_owner"]
    rows = source["H2_m"].shape[0]
    nodes = chain["segments"] + 1
    expected_owner = np.minimum(np.floor(np.arange(rows) / ((rows - 1) // chain["segments"]) + .5).astype(np.int64), nodes - 1)
    if not np.array_equal(owner, expected_owner):
        raise ValueError("fine row partition forged")
    offsets = support["offsets"]
    if offsets.shape != (nodes + 1,) or offsets.dtype != np.dtype("int64") or offsets[0] != 0 or offsets[-1] != support["beds_m"].size or (np.diff(offsets) <= 0).any():
        raise ValueError("fine support offsets")
    for node in range(nodes):
        values = source["H2_m"][owner == node].ravel()
        weights = source["quadrature_area_m2"][owner == node].ravel()
        begin, end = offsets[node:node + 2]
        if not np.array_equal(support["beds_m"][begin:end], values) or not np.array_equal(support["weights_m2"][begin:end], weights):
            raise ValueError("fine saved support local source sampling")
        bank = float(np.minimum(source["H2_m"][owner == node, 0], source["H2_m"][owner == node, -1]).min())
        if support["min_bed_m"][node] != values.min() or support["min_bank_m"][node] != bank or support["max_stage_m"][node] != bank - 1e-6:
            raise ValueError("fine saved bank envelope")
        if support["side_margin_m"][node] != bank - values.min():
            raise ValueError("fine side margin forged")
        local_bed = source["H2_m"][owner == node]
        levels = np.unique(local_bed[local_bed <= bank - 1e-6])
        if support["single_pool_event_count"][node] != levels.size:
            raise ValueError("fine event certificate forged")
        for level in levels:
            if ndimage.label(local_bed <= level, ndimage.generate_binary_structure(2, 1))[1] > 1:
                raise ValueError("fine sub-bank initial pools disconnected")
    interfaces = np.flatnonzero(np.diff(owner) != 0)
    bed = source["H2_m"]
    sill = np.r_[bed[0].min(), np.maximum(bed[interfaces].min(axis=1), bed[interfaces + 1].min(axis=1)), bed[-1].min()]
    if not np.array_equal(support["interface_before_rows"], interfaces) or not np.array_equal(support["interface_sill_m"], sill):
        raise ValueError("real shared-section sill forgery")
    arrays = saved["arrays"]
    requested = saved["requested_steps"]
    committed = saved["committed_steps"]
    if type(requested) is not int or type(committed) is not int or not 0 <= committed <= requested <= MAX_STEPS:
        raise ValueError("fine step metadata")
    if requested * (nodes + support["beds_m"].size) > MAX_WORK or support["beds_m"].size > MAX_SUPPORT:
        raise ValueError("fine static work ceiling")
    if saved["status"] == "fine_storage_completed":
        if committed != requested or saved["failure"] is not None:
            raise ValueError("fine completed status forgery")
    elif saved["status"] == "fine_storage_refused":
        if saved["failure"] is None or committed == requested or saved["failure"]["step"] not in (-1, committed):
            raise ValueError("fine failure status forgery")
    else:
        raise ValueError("fine unknown status")
    specs = {"initial_stage_m": (nodes,), "local_q_m3_s": (requested, nodes),
             "upstream_stage_m": (requested + 1,), "tailwater_stage_m": (requested + 1,),
             "stage_m": (committed + 1, nodes), "storage_m3": (committed + 1, nodes),
             "qedges_m3_s": (committed, nodes + 1), "ledger_m3": (committed, 6)}
    if set(arrays) != set(specs):
        raise ValueError("fine state exact schema")
    for key, shape in specs.items():
        value = arrays[key]
        if not isinstance(value, np.ndarray) or value.dtype != np.dtype("float64") or value.shape != shape or not np.isfinite(value).all():
            raise ValueError("fine state dtype/shape/finite: " + key)
    stages, storage = arrays["stage_m"], arrays["storage_m3"]
    if stages.shape != storage.shape or stages.shape[0] != saved["committed_steps"] + 1:
        raise ValueError("fine state shapes")
    if not np.array_equal(stages[0], arrays["initial_stage_m"]):
        raise ValueError("fine initial stage mismatch")
    offsets, beds, weights = support["offsets"], support["beds_m"], support["weights_m2"]
    for node in range(stages.shape[1]):
        volumes = np.maximum(stages[:, node, None] - beds[None, offsets[node]:offsets[node + 1]], 0) @ weights[offsets[node]:offsets[node + 1]]
        if not np.allclose(storage[:, node], volumes, rtol=1e-12, atol=1e-9):
            raise ValueError("fine V(h) forgery")
    initial_failure = saved["failure"] is not None and saved["failure"]["step"] == -1
    if ((stages > support["max_stage_m"] + 1e-9).any() or (stages < support["min_bed_m"] - 1e-9).any()) and not initial_failure:
        raise ValueError("fine bank/negative water")
    if (storage < 0).any() or (arrays["local_q_m3_s"] < 0).any():
        raise ValueError("fine negative quantity")
    steps = saved["committed_steps"]
    flux = arrays["qedges_m3_s"]
    if saved["conductance_m2_s"] != CONDUCTANCE_M2_S or not 0 < saved["dt_s"] <= MAX_DT_S:
        raise ValueError("fixed dynamic identity")
    heads = np.column_stack((arrays["upstream_stage_m"][:steps], stages[:-1], arrays["tailwater_stage_m"][:steps]))
    expected_flux = CONDUCTANCE_M2_S * (np.maximum(heads[:, :-1], sill) - np.maximum(heads[:, 1:], sill))
    for node in range(nodes):
        outgoing = np.maximum(0., -expected_flux[:, node]) + np.maximum(0., expected_flux[:, node + 1])
        available = storage[:-1, node] + saved["dt_s"] * arrays["local_q_m3_s"][:steps, node]
        limited = outgoing * saved["dt_s"] > available
        factor = np.ones(steps)
        factor[limited] = available[limited] / (outgoing[limited] * saved["dt_s"])
        left_negative = expected_flux[:, node] < 0
        right_positive = expected_flux[:, node + 1] > 0
        expected_flux[left_negative, node] *= factor[left_negative]
        expected_flux[right_positive, node + 1] *= factor[right_positive]
    if not np.allclose(flux, expected_flux, rtol=1e-12, atol=1e-12):
        raise ValueError("signed wet-connected limited flux forged")
    residual = np.diff(storage, axis=0) - saved["dt_s"] * (arrays["local_q_m3_s"][:steps] + flux[:, :-1] - flux[:, 1:])
    if not np.allclose(residual, 0, rtol=0, atol=1e-9):
        raise ValueError("fine local continuity forgery")
    expected_ledger = np.column_stack((storage[:-1].sum(axis=1),
        saved["dt_s"] * arrays["local_q_m3_s"][:steps].sum(axis=1),
        saved["dt_s"] * flux[:, 0], saved["dt_s"] * flux[:, -1], storage[1:].sum(axis=1),
        storage[1:].sum(axis=1) - storage[:-1].sum(axis=1) - saved["dt_s"] * (arrays["local_q_m3_s"][:steps].sum(axis=1) + flux[:, 0] - flux[:, -1])))
    if not np.allclose(arrays["ledger_m3"], expected_ledger, rtol=0., atol=1e-9):
        raise ValueError("fine ledger component forgery")
    return {"max_node_residual_m3": float(np.abs(residual).max(initial=0)),
            "minimum_bank_margin_m": float(np.min(support["side_margin_m"])),
            "final_storage_m3": float(storage[-1].sum())}


def save_fine_storage(path, saved, chain, geometry):
    validate_fine_storage(saved, chain, geometry)
    metadata = {key: value for key, value in saved.items() if key not in ("arrays", "support")}
    support_meta = {key: value for key, value in saved["support"].items() if not isinstance(value, np.ndarray)}
    payload = {"state__" + key: value for key, value in saved["arrays"].items()}
    payload.update({"support__" + key: value for key, value in saved["support"].items() if isinstance(value, np.ndarray)})
    manifest = {"metadata": metadata, "support_metadata": support_meta,
                "geometry_source_binding": geometry["metadata"]["source_binding"],
                "hashes": {key: _hash(value) for key, value in payload.items()}}
    encoded = _json(manifest).encode("ascii")
    if len(encoded) > 65536 or sum(value.nbytes for value in payload.values()) > MAX_ARCHIVE_BYTES:
        raise ValueError("fine storage publication resource ceiling")
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    descriptor, temporary = tempfile.mkstemp(prefix=".mountain-fine-storage-", suffix=".npz", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            np.savez_compressed(stream, manifest=np.frombuffer(encoded, dtype=np.uint8), **payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


def load_fine_storage(path, chain, geometry):
    state_keys = {"initial_stage_m", "local_q_m3_s", "upstream_stage_m", "tailwater_stage_m", "stage_m", "storage_m3", "qedges_m3_s", "ledger_m3"}
    support_keys = {"offsets", "beds_m", "weights_m2", "row_owner", "min_bed_m", "max_stage_m", "min_bank_m", "side_margin_m", "interface_before_rows", "interface_sill_m", "single_pool_event_count"}
    names = {"state__" + key + ".npy" for key in state_keys} | {"support__" + key + ".npy" for key in support_keys} | {"manifest.npy"}
    with open(path, "rb") as stream:
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            if len(members) != len(names) or {member.filename for member in members} != names:
                raise ValueError("strict fine storage archive schema")
            if sum(member.file_size for member in members) > MAX_ARCHIVE_BYTES:
                raise ValueError("fine storage archive resource ceiling")
            headers = {}
            for member in members:
                with archive.open(member) as item:
                    if np.lib.format.read_magic(item) != (1, 0):
                        raise ValueError("fine NPY version")
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(item)
                    key = member.filename[:-4]
                    headers[key] = shape
                    expected_dtype = np.dtype("uint8" if key == "manifest" else "int64" if key in {"support__" + name for name in ("offsets", "row_owner", "interface_before_rows", "single_pool_event_count")} else "float64")
                    if dtype != expected_dtype or fortran or math.prod(shape) * dtype.itemsize + item.tell() != member.file_size:
                        raise ValueError("fine header dtype/size")
                    if len(shape) not in (1, 2) or math.prod(shape) > max(MAX_SUPPORT, MAX_STEPS * 17):
                        raise ValueError("fine header dimensions")
                    if key == "manifest" and shape[0] > 65536:
                        raise ValueError("fine manifest limit")
            nodes = chain["segments"] + 1
            if not 4 <= nodes <= 17:
                raise ValueError("fine node ceiling")
            requested_shape = headers["state__local_q_m3_s"]
            state_shape = headers["state__stage_m"]
            if len(requested_shape) != 2 or len(state_shape) != 2:
                raise ValueError("fine forcing/state header dimensions")
            requested = requested_shape[0]
            committed = state_shape[0] - 1
            if not 1 <= requested <= MAX_STEPS or not 0 <= committed <= requested:
                raise ValueError("fine steps header ceiling")
            rows, columns = chain["arrays"]["H2_m"].shape
            exact_shapes = {"state__initial_stage_m": (nodes,), "state__local_q_m3_s": (requested, nodes),
                "state__upstream_stage_m": (requested + 1,), "state__tailwater_stage_m": (requested + 1,),
                "state__stage_m": (committed + 1, nodes), "state__storage_m3": (committed + 1, nodes),
                "state__qedges_m3_s": (committed, nodes + 1), "state__ledger_m3": (committed, 6),
                "support__offsets": (nodes + 1,), "support__beds_m": (rows * columns,),
                "support__weights_m2": (rows * columns,), "support__row_owner": (rows,),
                "support__interface_before_rows": (nodes - 1,), "support__interface_sill_m": (nodes + 1,)}
            exact_shapes.update({"support__" + key: (nodes,) for key in ("min_bed_m", "max_stage_m", "min_bank_m", "side_margin_m", "single_pool_event_count")})
            for key, shape in exact_shapes.items():
                if headers[key] != shape:
                    raise ValueError("fine exact header shape: " + key)
        stream.seek(0)
        with np.load(stream, allow_pickle=False) as archive:
            manifest = json.loads(archive["manifest"].tobytes().decode("ascii"))
            arrays = {key: archive[key].copy() for key in archive.files if key != "manifest"}
    if manifest["geometry_source_binding"] != geometry["metadata"]["source_binding"] or set(manifest["hashes"]) != set(arrays):
        raise ValueError("fine source external trust mismatch")
    for key, value in arrays.items():
        if manifest["hashes"][key] != _hash(value):
            raise ValueError("fine integrity mismatch")
    saved = dict(manifest["metadata"])
    saved["arrays"] = {key[len("state__"):]: value for key, value in arrays.items() if key.startswith("state__")}
    saved["support"] = dict(manifest["support_metadata"], **{key[len("support__"):]: value for key, value in arrays.items() if key.startswith("support__")})
    validate_fine_storage(saved, chain, geometry)
    for branch in (saved["arrays"], saved["support"]):
        for key, value in branch.items():
            if isinstance(value, np.ndarray):
                branch[key] = np.frombuffer(value.tobytes(), dtype=value.dtype).reshape(value.shape)
    return saved
