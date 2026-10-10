"""Versioned diagnostic native-grid runoff and topology products; no hydraulics."""

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.rainfall_runoff import ARRAY_KEYS, MAX_CELLS as RUNOFF_MAX_CELLS, MAX_ENTRIES as RUNOFF_MAX_ENTRIES, validate_rainfall_runoff_result
from .metric_contracts import BoundaryGrid, RainfallForcing, RoutingGraph, TerrainGrid
from .metric_drainage import accumulate_local_discharge, route_diagnostic
from .metric_runoff import runoff_from_forcing
from .metric_large_runoff import runoff_from_forcing_large, validate_large_rainfall_runoff_result

SCHEMA = "terragenesis-river-diagnostic-v1"
MAX_PRODUCT_BYTES = 1024 * 1024 * 1024
GRAPH_ARRAYS = ("receiver", "order_downstream_first", "valid_mask", "edge_length_m", "edge_slope", "outlet_kind", "lake_id")
TERMINAL_TOTALS = {"open_outflow": "open_outflow_m3_s", "lake_retained": "lake_retained_m3_s",
                   "unknown_pending": "unknown_pending_m3_s",
                   "prescribed_boundary_candidate": "prescribed_boundary_candidate_m3_s"}
LIMITATIONS = ("no channel travel time or channel storage", "no stage or lake spill dynamics",
               "no sediment erosion or bed change", "open perimeter is engineering boundary, not natural outlet",
               "original-bed D8 is a new diagnostic, not the pinned TD D4 hierarchy",
               "no AMR or uniform resolution certification")


def _time_semantics(forcing, native):
    return {"time_seconds": "T+1 forcing interval endpoints and hydrology states",
            "dt_solver_seconds": float(native["metadata"]["dt_s"]),
            "solver_role": "independent_cell_hydrology_no_channel_hydraulics",
            "dt_output_seconds": np.diff(forcing.time_seconds).tolist(),
            "local_q_m3_s": "interval_average_local_release_not_river_routed",
            "routed_q_m3_s": "interval_average_instantaneous_topological_accumulation_no_travel_time",
            "volume_interval_m3": "forcing_interval_integral"}


def build_diagnostic_product(terrain, boundary, forcing, *, parameters=None):
    cells = int(terrain.valid_mask.sum())
    steps = forcing.interval_seconds.size
    large = cells > RUNOFF_MAX_CELLS or cells * steps > RUNOFF_MAX_ENTRIES
    if large and steps > 3:
        raise ValueError("large diagnostic products support at most three intervals")
    estimated_bytes = terrain.valid_mask.size * (256 + 32 * steps) + cells * (8 * (16 * steps + 4))
    if estimated_bytes > MAX_PRODUCT_BYTES:
        raise ValueError("diagnostic product allocation budget exceeded")
    graph = route_diagnostic(terrain, boundary)
    if large:
        runoff = runoff_from_forcing_large(terrain, forcing, parameters=parameters, output_indices=[steps])
    else:
        runoff = runoff_from_forcing(terrain, forcing, parameters=parameters)
    native = runoff["native_result"]
    steps = forcing.interval_seconds.size
    local = np.zeros((steps,) + terrain.valid_mask.shape, np.float64)
    local.reshape(steps, -1)[:, runoff["valid_cell_ids"]] = native["local_q_m3_s"]
    routed = np.empty_like(local)
    terminals = np.empty_like(local)
    totals = {key: np.zeros(steps, np.float64) for key in TERMINAL_TOTALS}
    residual = np.zeros(steps, np.float64)
    for step in range(steps):
        result = accumulate_local_discharge(graph, local[step])
        routed[step] = result["routed_q_m3_s"]
        terminals[step] = result["terminal_q_m3_s"]
        residual[step] = result["residual_m3_s"] * forcing.interval_seconds[step]
        for key, field in TERMINAL_TOTALS.items():
            totals[key][step] = result[field] * forcing.interval_seconds[step]
    arrays = {"elevation_m": terrain.elevation_m, "boundary_kind": boundary.kind,
              "boundary_allow_inflow": boundary.allow_inflow, "rain_mm_h": forcing.rain_mm_h,
              "time_seconds": forcing.time_seconds, "valid_cell_ids": runoff["valid_cell_ids"],
              "local_q_m3_s": local, "routed_q_m3_s": routed, "terminal_q_m3_s": terminals,
              "routing_residual_m3": residual}
    arrays.update({"graph_" + key: getattr(graph, key) for key in GRAPH_ARRAYS})
    arrays.update({"runoff_" + key: native[key] for key in ARRAY_KEYS})
    arrays.update({key + "_volume_interval_m3": value for key, value in totals.items()})
    for key in ("stage_m", "discharge_m3_s"):
        if getattr(boundary, key) is not None:
            arrays["boundary_" + key] = getattr(boundary, key)
    ledger = runoff["ledger"]["totals_m3"]
    budget = {"rain_input": ledger["rain_volume_m3"], "evapotranspiration": ledger["et_volume_m3"],
              "hydrology_storage_change": ledger["storage_change_m3"],
              "local_release": ledger["outflow_volume_m3"],
              **{name: float(values.sum()) for name, values in totals.items()}}
    budget["combined_residual"] = budget["rain_input"] - budget["evapotranspiration"] - budget["hydrology_storage_change"] - sum(budget[key] for key in TERMINAL_TOTALS)
    metadata = {"schema": SCHEMA, "status": "diagnostic_runoff", "terrain": terrain.metadata(),
                "terrain_identity_sha256": terrain.identity_sha256,
                "boundary": {"source_id": boundary.source_id, "source_sha256": boundary.source_sha256},
                "boundary_identity_sha256": boundary.identity_sha256,
                "forcing": {name: getattr(forcing, name) for name in forcing.__dataclass_fields__ if name not in ("time_seconds", "rain_mm_h")},
                "forcing_identity_sha256": forcing.identity_sha256, "runoff_metadata": native["metadata"],
                "routing_policy": graph.policy, "routing_identity_sha256": graph.identity_sha256,
                "time_semantics": _time_semantics(forcing, native),
                "water_budget_m3": budget, "native_grid_is_volume_basis": True,
                "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
                "amr_role": "local_high_resolution_diagnostic_not_executed",
                "uniform_role": "failure_control_not_executed",
                "lake_id_semantics": "closed_terminal_contribution_catchment_not_wet_footprint",
                "lake_terminal_count": int(np.count_nonzero(graph.outlet_kind == "lake_preserved")),
                "unknown_terminal_count": int(np.count_nonzero(graph.outlet_kind == "unknown_boundary")),
                "limitations": list(LIMITATIONS)}
    arrays = {name: readonly(value) for name, value in arrays.items()}
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    del native, runoff
    validate_diagnostic_product(result)
    return result


def decode_diagnostic_product(result):
    arrays, meta = result["arrays"], result["metadata"]
    terrain_meta = {key: value for key, value in meta["terrain"].items() if key in TerrainGrid.__dataclass_fields__}
    terrain = TerrainGrid(arrays["elevation_m"], arrays["graph_valid_mask"], **terrain_meta)
    boundary = BoundaryGrid(arrays["boundary_kind"], arrays["boundary_allow_inflow"], **meta["boundary"],
                            stage_m=arrays.get("boundary_stage_m"), discharge_m3_s=arrays.get("boundary_discharge_m3_s"))
    forcing = RainfallForcing(arrays["time_seconds"], arrays["rain_mm_h"], **meta["forcing"])
    graph = RoutingGraph(**{key: arrays["graph_" + key] for key in GRAPH_ARRAYS},
                         terrain_identity_sha256=meta["terrain_identity_sha256"],
                         boundary_identity_sha256=meta["boundary_identity_sha256"], policy=meta["routing_policy"])
    native = {key: arrays["runoff_" + key] for key in ARRAY_KEYS} | {"metadata": meta["runoff_metadata"]}
    return terrain, boundary, forcing, graph, native


def _equal(observed, expected, label):
    if np.shape(observed) != np.shape(expected) or not np.allclose(observed, expected, rtol=1e-11, atol=1e-10):
        raise ValueError("diagnostic saved mismatch: " + label)


def _validate_graph_geometry(terrain, boundary, graph):
    if graph.policy != "original_bed_d8_plateau_bfs_v1":
        raise ValueError("unsupported saved routing policy")
    if not np.array_equal(graph.valid_mask, terrain.valid_mask) or boundary.kind.shape != terrain.valid_mask.shape:
        raise ValueError("saved routing domain differs")
    rows, cols = terrain.valid_mask.shape
    valid = terrain.valid_mask.ravel()
    kind = boundary.kind.ravel()
    cells = np.flatnonzero(valid)
    rr, cc = np.divmod(cells, cols)
    unknown_contact = np.zeros(valid.size, bool)
    perimeter = np.zeros(valid.size, bool)
    perimeter[cells] = (rr == 0) | (rr == rows - 1) | (cc == 0) | (cc == cols - 1)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == dc == 0:
                continue
            inside = (rr + dr >= 0) & (rr + dr < rows) & (cc + dc >= 0) & (cc + dc < cols)
            ids = cells[inside]
            unknown_contact[ids] |= ~valid[(rr[inside] + dr) * cols + cc[inside] + dc]
    fringe = perimeter | unknown_contact
    if (np.any(kind[~valid] != "unknown_boundary") or np.any((kind == "interior") & perimeter)
            or np.any(valid & ~fringe & (kind != "interior"))):
        raise ValueError("saved boundary placement differs from routing domain")
    donors = np.flatnonzero(graph.receiver >= 0)
    targets = graph.receiver[donors]
    dr = targets // cols - donors // cols
    dc = targets % cols - donors % cols
    if np.any((np.abs(dr) > 1) | (np.abs(dc) > 1) | ((dr == 0) & (dc == 0))):
        raise ValueError("saved routing edges must join adjacent cells")
    diagonal = (dr != 0) & (dc != 0)
    if np.any(~valid[donors[diagonal] + dr[diagonal] * cols]) or np.any(~valid[donors[diagonal] + dc[diagonal]]):
        raise ValueError("saved diagonal crosses unknown corner")
    length = np.hypot(dc * terrain.dx_m, dr * terrain.dz_m)
    drop = terrain.elevation_m.ravel()[donors] - terrain.elevation_m.ravel()[targets]
    if np.any(drop < 0.):
        raise ValueError("saved original-bed route climbs uphill")
    _equal(graph.edge_length_m[donors], length, "metric edge length")
    _equal(graph.edge_slope[donors], drop / length, "original-bed slope")
    explicit = valid & np.isin(kind, ("open_outflow", "prescribed_stage", "prescribed_discharge", "unknown_boundary"))
    if np.any(graph.receiver[explicit] != -1) or np.any(graph.outlet_kind[explicit] != kind[explicit]):
        raise ValueError("saved explicit outlet differs from boundary")
    terminals = valid & (graph.receiver < 0)
    for terminal in np.flatnonzero(terminals & ~explicit):
        outlet = graph.outlet_kind[terminal]
        if outlet == "unknown_boundary" and not unknown_contact[terminal]:
            raise ValueError("unknown terminal must contact unknown terrain")
        if outlet not in ("lake_preserved", "unknown_boundary"):
            raise ValueError("implicit domain outlet is forbidden")
    expected_lakes = np.where(graph.outlet_kind == "lake_preserved", np.arange(valid.size), -1)
    if not np.array_equal(graph.lake_id[terminals], expected_lakes[terminals]):
        raise ValueError("saved lake terminal classification differs")
    if not np.array_equal(graph.lake_id[donors], graph.lake_id[targets]):
        raise ValueError("saved lake catchment classification differs")


def validate_diagnostic_product(result):
    arrays, meta = result["arrays"], result["metadata"]
    if sum(value.nbytes for value in arrays.values()) > MAX_PRODUCT_BYTES:
        raise ValueError("saved diagnostic product byte budget exceeded")
    if meta["schema"] != SCHEMA or meta["status"] != "diagnostic_runoff" or any(meta[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("unsupported diagnostic scope or capability promotion")
    if result["identity_sha256"] != identity(arrays, meta):
        raise ValueError("diagnostic identity mismatch")
    terrain, boundary, forcing, graph, native = decode_diagnostic_product(result)
    if meta["terrain"] != terrain.metadata():
        raise ValueError("saved terrain metadata differs from registered contract")
    expected_arrays = {"elevation_m", "boundary_kind", "boundary_allow_inflow", "rain_mm_h", "time_seconds",
                       "valid_cell_ids", "local_q_m3_s", "routed_q_m3_s", "terminal_q_m3_s", "routing_residual_m3"}
    expected_arrays.update("graph_" + key for key in GRAPH_ARRAYS)
    expected_arrays.update("runoff_" + key for key in ARRAY_KEYS)
    expected_arrays.update(key + "_volume_interval_m3" for key in TERMINAL_TOTALS)
    for key in ("stage_m", "discharge_m3_s"):
        if getattr(boundary, key) is not None:
            expected_arrays.add("boundary_" + key)
    if set(arrays) != expected_arrays:
        raise ValueError("unexpected diagnostic array census")
    scope = {"native_grid_is_volume_basis": True, "amr_role": "local_high_resolution_diagnostic_not_executed",
             "uniform_role": "failure_control_not_executed",
             "lake_id_semantics": "closed_terminal_contribution_catchment_not_wet_footprint",
             "lake_terminal_count": int(np.count_nonzero(graph.outlet_kind == "lake_preserved")),
             "unknown_terminal_count": int(np.count_nonzero(graph.outlet_kind == "unknown_boundary")),
             "limitations": list(LIMITATIONS)}
    if any(meta.get(key) != value for key, value in scope.items()):
        raise ValueError("saved diagnostic scope differs")
    for key, contract in (("terrain", terrain), ("boundary", boundary), ("forcing", forcing), ("routing", graph)):
        if contract.identity_sha256 != meta[key + "_identity_sha256"]:
            raise ValueError("contract identity differs: " + key)
    _validate_graph_geometry(terrain, boundary, graph)
    steps, cells = native["rain_mm_h"].shape
    if cells > RUNOFF_MAX_CELLS or cells * steps > RUNOFF_MAX_ENTRIES:
        validate_large_rainfall_runoff_result(native)
    else:
        validate_rainfall_runoff_result(native)
    if meta["time_semantics"] != _time_semantics(forcing, native):
        raise ValueError("saved time semantics differ from diagnostic intervals")
    ids = np.flatnonzero(terrain.valid_mask)
    if not np.array_equal(ids, arrays["valid_cell_ids"]):
        raise ValueError("valid cell census differs")
    _equal(native["area_m2"], np.full(len(ids), terrain.cell_area_m2), "native cell area")
    _equal(native["rain_mm_h"], forcing.rain_mm_h.reshape(len(forcing.interval_seconds), -1)[:, ids], "forcing linkage")
    if np.any(forcing.interval_seconds != native["metadata"]["dt_s"]):
        raise ValueError("saved physical intervals differ from fixed solver dt")
    if np.any(forcing.rain_mm_h[:, ~terrain.valid_mask] != 0.):
        raise ValueError("rain crosses unknown")
    shape = forcing.rain_mm_h.shape
    for key in ("routing_residual_m3",) + tuple(name + "_volume_interval_m3" for name in TERMINAL_TOTALS):
        if arrays[key].shape != (shape[0],) or arrays[key].dtype != np.float64 or not np.isfinite(arrays[key]).all():
            raise ValueError("invalid saved interval budget: " + key)
    for key in ("local_q_m3_s", "routed_q_m3_s", "terminal_q_m3_s"):
        if arrays[key].shape != shape or arrays[key].dtype != np.float64 or not np.isfinite(arrays[key]).all() or np.any(arrays[key] < 0.) or np.any(arrays[key][:, ~terrain.valid_mask] != 0.):
            raise ValueError("invalid saved discharge: " + key)
    _equal(arrays["local_q_m3_s"].reshape(shape[0], -1)[:, ids], native["local_q_m3_s"], "local release linkage")
    for step, dt in enumerate(forcing.interval_seconds):
        expected = accumulate_local_discharge(graph, arrays["local_q_m3_s"][step])
        _equal(arrays["routed_q_m3_s"][step], expected["routed_q_m3_s"], "routed discharge")
        _equal(arrays["terminal_q_m3_s"][step], expected["terminal_q_m3_s"], "terminal discharge")
        _equal(arrays["routing_residual_m3"][step], expected["residual_m3_s"] * dt, "routing residual")
        for name, field in TERMINAL_TOTALS.items():
            volume = expected[field] * dt
            _equal(arrays[name + "_volume_interval_m3"][step], volume, "terminal budget")
    # Keep the interval-then-cell reduction used by the native hydrology ledger.
    # A flat reduction changes roundoff at full TD grid scale.
    def native_total(key):
        return float(np.sum(np.sum(native[key], axis=1, dtype=np.float64), dtype=np.float64))

    volume_totals = {name: float(np.sum(arrays[name + "_volume_interval_m3"], dtype=np.float64))
                     for name in TERMINAL_TOTALS}
    ledger = {"rain_input": native_total("rain_volume_m3"), "evapotranspiration": native_total("et_volume_m3"),
              "hydrology_storage_change": native_total("storage_change_m3"),
              "local_release": native_total("outflow_volume_m3"), **volume_totals}
    ledger["combined_residual"] = ledger["rain_input"] - ledger["evapotranspiration"] - ledger["hydrology_storage_change"] - sum(ledger[key] for key in TERMINAL_TOTALS)
    if set(meta["water_budget_m3"]) != set(ledger) or not all(np.isfinite(value) for value in ledger.values()):
        raise ValueError("invalid global diagnostic ledger")
    for key, value in ledger.items():
        _equal(meta["water_budget_m3"][key], value, "global water budget " + key)
    scale = max(1., ledger["rain_input"], abs(ledger["hydrology_storage_change"]))
    if abs(ledger["combined_residual"]) > 1e-10 * scale:
        raise ValueError("combined water budget failed")
    return True


def save_diagnostic_product(path, result):
    save_bundle(path, result, validator=validate_diagnostic_product)


def load_diagnostic_product(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_diagnostic_product,
                         max_bytes=MAX_PRODUCT_BYTES)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external diagnostic identity mismatch")
    return result
