"""Lumped three-store runoff feeding independent Radau surface inventories.

This is not native-grid v10 hydrology: no surface reinfiltration, tailwater,
erosion, or natural-outlet certification is provided.
"""

from dataclasses import asdict, dataclass
import math

import numpy as np
from scipy.integrate import Radau

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.rainfall_runoff import (
    ARRAY_KEYS as RUNOFF_ARRAY_KEYS, RunoffParameters, simulate_rainfall_runoff,
    validate_rainfall_runoff_result,
)
from terrain_pipeline.td_basin_overflow import SCHEMA as TOPOLOGY_SCHEMA, _topology_identity
from terrain_pipeline.td_basin_overflow_radau import _IntegratedExchange

SCHEMA = "td-basin-runoff-exchange-v1"
ALGORITHM = "lumped-three-store-runoff-radau-surface-exchange-v1"
MAX_STEPS = 100_000
MAX_ENTRIES = 1_000_000
MAX_ARRAY_BYTES = 128 * 1024 * 1024
SURFACE_KEYS = {
    "surface_volume_m3", "stage_m", "soil_volume_m3", "fast_volume_m3", "slow_volume_m3",
    "surface_input_volume_m3", "face_forward_m3", "face_reverse_m3", "face_net_m3",
    "basin_net_internal_m3", "engineering_boundary_outflow_m3", "basin_boundary_outflow_m3",
    "surface_balance_residual_m3", "total_water_m3", "total_balance_residual_m3",
}
ARRAY_KEYS = set(RUNOFF_ARRAY_KEYS) | SURFACE_KEYS
FLAGS = ("hydraulic_ready", "transient_converged", "natural_outlet_verified", "publishable")
METADATA_KEYS = {"schema", "algorithm", "parameters", "runoff_metadata", "topology_identity_sha256",
                 "hierarchy_identity_sha256", "source_identity_sha256", "steps", "timestep_s", "duration_s",
                 "max_step_s", "rtol", "atol_stage_m", "flux_atol_m3", "work", "leaf_order",
                 "supply_semantics", "integration", "boundary_semantics", "balance_semantics", "limitations"} | set(FLAGS)
WORK_KEYS = {"accepted_steps", "rhs_evaluations", "jacobian_evaluations", "lu_factorizations",
             "maximum_scaled_collocation_defect", "maximum_inventory_correction_m3"}


def _positive(value, name, allow_zero=False):
    if (type(value) not in (int, float) or not math.isfinite(value) or
            value < 0 or (not allow_zero and value == 0)):
        raise ValueError("invalid finite positive parameter: " + name)


@dataclass(frozen=True)
class RunoffExchangeParameters:
    timestep_s: float = 300.
    duration_s: float = 3600.
    face_conductance_m_s: float = .6
    boundary_conductance_m_s: float = .6

    def __post_init__(self):
        for name, value in asdict(self).items():
            _positive(value, name, allow_zero=name.endswith("conductance_m_s"))
        ratio = self.duration_s / self.timestep_s
        if not math.isfinite(ratio) or ratio != int(ratio) or not 1 <= ratio <= MAX_STEPS:
            raise ValueError("duration must contain a bounded integer number of timesteps")


class _RunoffExchange(_IntegratedExchange):
    def set_runoff_volume(self, outflow_volume_m3, dt_s):
        if (outflow_volume_m3.shape != (self.count,) or not np.isfinite(outflow_volume_m3).all()
                or np.any(outflow_volume_m3 < 0)):
            raise ValueError("invalid runoff supply volume")
        self.supply_rate = outflow_volume_m3 / dt_s


def _exchange(topology, parameters):
    if (not isinstance(topology, dict) or topology.get("metadata", {}).get("schema") != TOPOLOGY_SCHEMA or
            topology.get("identity_sha256") != _topology_identity(topology)):
        raise ValueError("runoff exchange requires pinned original-bed topology")
    return _RunoffExchange(topology, parameters)


def _shapes(steps, count, faces, boundaries):
    if steps * max(count, faces, boundaries, 1) > MAX_ENTRIES:
        raise ValueError("runoff exchange entry budget exceeded")
    shapes = {key: (steps, count) for key in RUNOFF_ARRAY_KEYS}
    shapes["area_m2"] = (count,)
    for key in ("soil_mm", "fast_mm", "slow_mm", "surface_volume_m3", "stage_m",
                "soil_volume_m3", "fast_volume_m3", "slow_volume_m3", "total_water_m3"):
        shapes[key] = (steps + 1, count)
    for key in ("surface_input_volume_m3", "basin_net_internal_m3", "basin_boundary_outflow_m3",
                "surface_balance_residual_m3", "total_balance_residual_m3"):
        shapes[key] = (steps, count)
    for key in ("face_forward_m3", "face_reverse_m3", "face_net_m3"):
        shapes[key] = (steps, faces)
    shapes["engineering_boundary_outflow_m3"] = (steps, boundaries)
    if sum(math.prod(shape) * 8 for shape in shapes.values()) > MAX_ARRAY_BYTES:
        raise ValueError("runoff exchange saved array budget exceeded")
    return shapes


def _internal_ledgers(arrays, exchange):
    steps = len(arrays["rain_mm_h"])
    net = np.zeros((steps, exchange.count))
    boundary = np.zeros_like(net)
    signed = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    for face, (first, second) in enumerate(zip(exchange.system.first, exchange.system.second)):
        net[:, first] -= signed[:, face]
        net[:, second] += signed[:, face]
    for face, leaf in enumerate(exchange.system.boundary_leaf):
        boundary[:, leaf] += arrays["engineering_boundary_outflow_m3"][:, face]
    return signed, net, boundary


def simulate_runoff_exchange(topology, rain_mm_h, *, parameters=None, runoff_parameters=None,
                             source_id="lumped-basin-rainfall", initial_surface_volume_m3=None,
                             max_step_s=300., rtol=1e-7, atol_stage_m=1e-7, flux_atol_m3=1e-6):
    parameters = RunoffExchangeParameters() if parameters is None else parameters
    if not isinstance(parameters, RunoffExchangeParameters):
        raise ValueError("RunoffExchangeParameters required; legacy coefficient/baseflow are not accepted")
    parameters.__post_init__()
    for name, value in (("max_step_s", max_step_s), ("rtol", rtol),
                        ("atol_stage_m", atol_stage_m), ("flux_atol_m3", flux_atol_m3)):
        _positive(value, name)
    exchange = _exchange(topology, parameters)
    steps = int(parameters.duration_s / parameters.timestep_s)
    count, faces, boundaries = exchange.count, exchange.faces, exchange.boundaries
    shapes = _shapes(steps, count, faces, boundaries)
    if (not isinstance(rain_mm_h, np.ndarray) or rain_mm_h.shape != (steps, count)
            or rain_mm_h.dtype.kind not in "fiu" or not np.isfinite(rain_mm_h).all()
            or np.any(rain_mm_h < 0)):
        raise ValueError("rain_mm_h must be a finite nonnegative numeric [T,leaf] array, not bool")
    initial = np.zeros(count)
    if initial_surface_volume_m3 is not None:
        raw = np.asarray(initial_surface_volume_m3)
        if (raw.shape != (count,) or raw.dtype.kind not in "fiu" or
                not np.isfinite(raw).all() or np.any(raw < 0)):
            raise ValueError("invalid initial surface inventories")
        initial = raw.astype(np.float64, copy=True)
    runoff = simulate_rainfall_runoff(rain_mm_h, topology["arrays"]["leaf_area_m2"],
                                     dt_s=parameters.timestep_s, source_id=source_id,
                                     parameters=runoff_parameters)
    arrays = {key: runoff[key].copy() for key in RUNOFF_ARRAY_KEYS}
    arrays.update({key: np.zeros(shapes[key]) for key in SURFACE_KEYS})
    arrays["surface_volume_m3"][0] = initial
    values = np.concatenate((initial, np.zeros(2 * faces + boundaries)))
    depth, *_ = exchange.fields(values)
    arrays["stage_m"][0] = exchange.system.bottom + depth
    minimum_area = exchange.system.areas[exchange.system.offsets[:-1]]
    atol = np.concatenate((minimum_area * atol_stage_m, np.full(2 * faces + boundaries, flux_atol_m3)))
    work = {"accepted_steps": 0, "rhs_evaluations": 0, "jacobian_evaluations": 0,
            "lu_factorizations": 0, "maximum_scaled_collocation_defect": 0.,
            "maximum_inventory_correction_m3": 0.}
    for step in range(steps):
        exchange.set_runoff_volume(arrays["outflow_volume_m3"][step], parameters.timestep_s)
        arrays["surface_input_volume_m3"][step] = arrays["outflow_volume_m3"][step]
        start = step * parameters.timestep_s
        end = (step + 1) * parameters.timestep_s
        values = np.concatenate((values[:count], np.zeros(2 * faces + boundaries)))
        solver = Radau(exchange.rhs, start, values, end, jac=exchange.jacobian,
                       max_step=min(max_step_s, parameters.timestep_s), rtol=rtol, atol=atol)
        solver.newton_tol = min(solver.newton_tol, 1e-8)
        while solver.status == "running":
            previous = solver.y.copy()
            previous_time = solver.t
            solver.step()
            work["accepted_steps"] += 1
            if solver.status == "failed" or work["accepted_steps"] > MAX_STEPS:
                raise ValueError("runoff exchange Radau integration failed or exceeded step budget")
            defect, correction = exchange.conservative_step(solver, previous, solver.t - previous_time, atol, rtol)
            work["maximum_scaled_collocation_defect"] = max(work["maximum_scaled_collocation_defect"], defect)
            work["maximum_inventory_correction_m3"] = max(work["maximum_inventory_correction_m3"], correction)
        work["rhs_evaluations"] += solver.nfev
        work["jacobian_evaluations"] += solver.njev
        work["lu_factorizations"] += solver.nlu
        values = solver.y.copy()
        arrays["surface_volume_m3"][step + 1] = values[:count]
        depth, *_ = exchange.fields(values)
        arrays["stage_m"][step + 1] = exchange.system.bottom + depth
        arrays["face_forward_m3"][step] = values[count:count + faces]
        arrays["face_reverse_m3"][step] = values[count + faces:count + 2 * faces]
        arrays["engineering_boundary_outflow_m3"][step] = values[count + 2 * faces:]
    signed, net, boundary = _internal_ledgers(arrays, exchange)
    arrays["face_net_m3"], arrays["basin_net_internal_m3"], arrays["basin_boundary_outflow_m3"] = signed, net, boundary
    arrays["surface_balance_residual_m3"] = arrays["outflow_volume_m3"] + net - boundary - np.diff(arrays["surface_volume_m3"], axis=0)
    for store in ("soil", "fast", "slow"):
        arrays[store + "_volume_m3"] = arrays[store + "_mm"] * arrays["area_m2"] / 1000.
    arrays["total_water_m3"] = sum(arrays[store + "_volume_m3"] for store in ("soil", "fast", "slow", "surface"))
    arrays["total_balance_residual_m3"] = arrays["rain_volume_m3"] - arrays["et_volume_m3"] + net - boundary - np.diff(arrays["total_water_m3"], axis=0)
    metadata = {"schema": SCHEMA, "algorithm": ALGORITHM, "parameters": asdict(parameters),
                "runoff_metadata": runoff["metadata"], "topology_identity_sha256": topology["identity_sha256"],
                "hierarchy_identity_sha256": topology["metadata"]["hierarchy_identity_sha256"],
                "source_identity_sha256": topology["metadata"]["source_identity_sha256"],
                "steps": steps, "timestep_s": parameters.timestep_s, "duration_s": parameters.duration_s,
                "max_step_s": max_step_s, "rtol": rtol, "atol_stage_m": atol_stage_m, "flux_atol_m3": flux_atol_m3,
                "work": work, "leaf_order": "topology arrays.leaf_ids order; rainfall columns are not remapped",
                "supply_semantics": "runoff outflow_volume_m3 / timestep_s is the sole piecewise-constant surface supply",
                "integration": "Radau IIA positive stage weights; same conservative_step flux quadrature updates surface and face ledgers",
                "boundary_semantics": "one-way engineering perimeter outflow; no controlled tailwater inflow",
                "balance_semantics": "balance_residual_m3 is the three-store runoff ledger; surface and total ledgers are independent per leaf",
                "limitations": ["lumped independent-leaf runoff; no surface reinfiltration", "not native-grid v10 four-store hydrology", "no natural outlet or calibrated catchment certification"],
                **{flag: False for flag in FLAGS}}
    result = {"arrays": {key: readonly(value) for key, value in arrays.items()}, "metadata": metadata}
    result["identity_sha256"] = identity(result["arrays"], metadata)
    validate_runoff_exchange(result, topology)
    return result


def _equal(actual, expected, name):
    if not np.allclose(actual, expected, rtol=1e-10, atol=1e-8):
        raise ValueError("runoff exchange ledger mismatch: " + name)


def _balanced(residual, scale, name):
    if np.any(np.abs(residual) > 1e-8 + 1e-10 * scale):
        raise ValueError("runoff exchange nonconservative " + name)


def validate_runoff_exchange(result, topology):
    if not isinstance(result, dict) or set(result) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid runoff exchange bundle")
    arrays, metadata = result["arrays"], result["metadata"]
    if (not isinstance(arrays, dict) or set(arrays) != ARRAY_KEYS or not isinstance(metadata, dict) or
            set(metadata) != METADATA_KEYS or
            metadata.get("schema") != SCHEMA or metadata.get("algorithm") != ALGORITHM):
        raise ValueError("runoff exchange schema/fields mismatch")
    for flag in FLAGS:
        if metadata.get(flag) is not False:
            raise ValueError("runoff exchange certification flags must remain false")
    try:
        parameters = RunoffExchangeParameters(**metadata["parameters"])
    except (KeyError, TypeError) as error:
        raise ValueError("invalid runoff exchange parameters") from error
    exchange = _exchange(topology, parameters)
    steps = int(parameters.duration_s / parameters.timestep_s)
    if (type(metadata.get("steps")) is not int or metadata["steps"] != steps or
            metadata.get("timestep_s") != parameters.timestep_s or metadata.get("duration_s") != parameters.duration_s or
            metadata.get("topology_identity_sha256") != topology["identity_sha256"] or
            metadata.get("hierarchy_identity_sha256") != topology["metadata"]["hierarchy_identity_sha256"] or
            metadata.get("source_identity_sha256") != topology["metadata"]["source_identity_sha256"]):
        raise ValueError("runoff exchange topology/time identity mismatch")
    for name in ("max_step_s", "rtol", "atol_stage_m", "flux_atol_m3"):
        _positive(metadata.get(name), name)
    work = metadata["work"]
    if not isinstance(work, dict) or set(work) != WORK_KEYS:
        raise ValueError("invalid runoff exchange work summary")
    for name in ("accepted_steps", "rhs_evaluations", "jacobian_evaluations", "lu_factorizations"):
        if type(work[name]) is not int or work[name] < 0:
            raise ValueError("invalid runoff exchange work count")
    if not steps <= work["accepted_steps"] <= MAX_STEPS:
        raise ValueError("runoff exchange work step budget exceeded")
    for name in ("maximum_scaled_collocation_defect", "maximum_inventory_correction_m3"):
        _positive(work[name], name, allow_zero=True)
    if work["maximum_scaled_collocation_defect"] > .05:
        raise ValueError("runoff exchange collocation defect exceeds accepted bound")
    shapes = _shapes(steps, exchange.count, exchange.faces, exchange.boundaries)
    for name, shape in shapes.items():
        value = arrays[name]
        if not isinstance(value, np.ndarray) or value.shape != shape or value.dtype != np.float64 or not np.isfinite(value).all():
            raise ValueError("invalid runoff exchange array: " + name)
    runoff = {key: arrays[key] for key in RUNOFF_ARRAY_KEYS}
    runoff["metadata"] = metadata["runoff_metadata"]
    validate_rainfall_runoff_result(runoff)
    if runoff["metadata"]["dt_s"] != parameters.timestep_s:
        raise ValueError("runoff and exchange timestep mismatch")
    _equal(arrays["area_m2"], topology["arrays"]["leaf_area_m2"], "runoff leaf areas")
    for name in ("surface_volume_m3", "surface_input_volume_m3", "face_forward_m3", "face_reverse_m3", "engineering_boundary_outflow_m3"):
        if np.any(arrays[name] < 0):
            raise ValueError("negative runoff exchange inventory/flux: " + name)
    _equal(arrays["surface_input_volume_m3"], arrays["outflow_volume_m3"], "sole surface supply")
    signed, net, boundary = _internal_ledgers(arrays, exchange)
    _equal(arrays["face_net_m3"], signed, "face signed volumes")
    _equal(arrays["basin_net_internal_m3"], net, "paired internal exchange")
    _equal(arrays["basin_boundary_outflow_m3"], boundary, "engineering outflow")
    surface_change = np.diff(arrays["surface_volume_m3"], axis=0)
    surface_residual = arrays["outflow_volume_m3"] + net - boundary - surface_change
    _equal(arrays["surface_balance_residual_m3"], surface_residual, "surface residual")
    _balanced(surface_residual, arrays["outflow_volume_m3"] + np.abs(net) + boundary + np.abs(surface_change), "surface")
    for store in ("soil", "fast", "slow"):
        _equal(arrays[store + "_volume_m3"], arrays[store + "_mm"] * arrays["area_m2"] / 1000., store + " volume")
    total = sum(arrays[store + "_volume_m3"] for store in ("soil", "fast", "slow", "surface"))
    _equal(arrays["total_water_m3"], total, "four-store total water")
    total_change = np.diff(total, axis=0)
    residual = arrays["rain_volume_m3"] - arrays["et_volume_m3"] + net - boundary - total_change
    _equal(arrays["total_balance_residual_m3"], residual, "total residual")
    _balanced(residual, arrays["rain_volume_m3"] + arrays["et_volume_m3"] + np.abs(net) + boundary + np.abs(total_change), "four-store total")
    global_residual = arrays["rain_volume_m3"].sum(axis=1) - arrays["et_volume_m3"].sum(axis=1) - boundary.sum(axis=1) - total_change.sum(axis=1)
    _balanced(global_residual, arrays["rain_volume_m3"].sum(axis=1) + arrays["et_volume_m3"].sum(axis=1) + boundary.sum(axis=1) + np.abs(total_change).sum(axis=1), "global total")
    for step, volumes in enumerate(arrays["surface_volume_m3"]):
        depth, *_ = exchange.fields(np.concatenate((volumes, np.zeros(exchange.size - exchange.count))))
        _equal(arrays["stage_m"][step], exchange.system.bottom + depth, "surface stage/volume")
    if result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("runoff exchange identity mismatch")
    return True


def save_runoff_exchange(result, path, topology):
    save_bundle(path, result, validator=lambda event: validate_runoff_exchange(event, topology))


def load_runoff_exchange(path, *, expected_sha256, expected_identity, topology):
    parameters = RunoffExchangeParameters()
    exchange = _exchange(topology, parameters)

    def headers(values):
        if set(values) != ARRAY_KEYS | {"manifest"}:
            raise ValueError("unexpected runoff exchange archive fields")
        shape, _ = values["rain_mm_h"]
        if len(shape) != 2 or not 1 <= shape[0] <= MAX_STEPS or shape[1] != exchange.count:
            raise ValueError("invalid runoff exchange archive rain shape")
        expected = _shapes(shape[0], exchange.count, exchange.faces, exchange.boundaries)
        if any(values[key] != (wanted, np.dtype("float64")) for key, wanted in expected.items()):
            raise ValueError("runoff exchange archive array shapes/dtypes mismatch")

    result = load_bundle(path, expected_sha256=expected_sha256, max_bytes=MAX_ARRAY_BYTES,
                         header_validator=headers, validator=lambda event: validate_runoff_exchange(event, topology))
    if result["identity_sha256"] != expected_identity:
        raise ValueError("runoff exchange external identity mismatch")
    return result
