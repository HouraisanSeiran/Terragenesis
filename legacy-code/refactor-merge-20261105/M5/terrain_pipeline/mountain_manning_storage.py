"""Implicit source-bound Manning diffusive storage, not Saint-Venant momentum."""

import math
import io

import numpy as np
from scipy.optimize import least_squares

from terrain_pipeline.mountain_manning_geometry import section_hydraulics, validate_tributary_geometry
from terrain_pipeline.common_infra import checked_archive, identity, publish_bytes, readonly
from terrain_pipeline.runoff import _json as _json
from terrain_pipeline.runoff import _strict_json as _strict_json


ROUGHNESS_S_M_THIRD = .035
MAX_STEPS = 6000
MAX_DURATION_S = 86400.
MAX_EVALUATIONS = 2000000
MAX_STEP_EVALUATIONS = 64
MAX_STEP_RESIDUAL_CALLS = MAX_STEP_EVALUATIONS * 9 + 2
MAX_BYTES = 64 * 1024 * 1024
ABS_VOLUME_TOLERANCE_M3 = 1e-6
REL_VOLUME_TOLERANCE = 1e-10


def support_volume(record, node, stage):
    arrays = record["arrays"]
    selected = arrays["row_owner"] == node
    return float((np.maximum(stage - arrays["H2_m"][selected], 0.) * arrays["support_area_m2"][selected]).sum())


def manning_flux(record, stages, tailwater_stage_m):
    """Signed upwind section conveyance with actual shared dry-interface crest."""
    arrays = record["arrays"]
    heads = np.r_[stages, tailwater_stage_m]
    flux = np.zeros(4, dtype=np.float64)
    for edge in range(4):
        section = arrays["interface_section_bed_m"][edge + 1]
        crest = arrays["interface_crest_m"][edge + 1]
        left = max(float(heads[edge]), crest)
        right = max(float(heads[edge + 1]), crest)
        difference = left - right
        if difference == 0:
            continue
        donor_stage = float(heads[edge] if difference > 0 else heads[edge + 1])
        hydraulics = section_hydraulics(arrays["across_m"], section, donor_stage)
        conveyance = hydraulics["area_m2"] * hydraulics["hydraulic_radius_m"] ** (2 / 3) / ROUGHNESS_S_M_THIRD
        flux[edge] = math.copysign(conveyance * math.sqrt(abs(difference) / arrays["edge_distance_m"][edge + 1]), difference)
    return flux


def preflight(steps, dt_s):
    if type(steps) is not int or not 1 <= steps <= MAX_STEPS or type(dt_s) not in (int, float) or not math.isfinite(dt_s) or dt_s not in (15., 30.):
        raise ValueError("fixed 15/30s step and bounded forcing required")
    if steps * dt_s > MAX_DURATION_S:
        raise ValueError("Manning work/duration ceiling before allocation")
    estimate = (steps + 1) * 4 * 8 * 20 + 65536
    if estimate > MAX_BYTES:
        raise ValueError("Manning byte ceiling")
    return {"steps": steps, "dt_s": dt_s, "estimated_bytes": estimate,
            "worst_case_requested_residual_calls": steps * MAX_STEP_RESIDUAL_CALLS,
            "max_residual_evaluations": min(MAX_EVALUATIONS, steps * MAX_STEP_RESIDUAL_CALLS),
            "per_step_residual_call_limit": MAX_STEP_RESIDUAL_CALLS,
            "budget_policy": "bounded_prefix_refusal_not_guaranteed_full_duration"}


def capacity_bound(record, *, inlet_q_m3_s, lateral_q_m3_s, tailwater_stage_m, dt_s):
    """Necessary dry-start volume bound using the greatest legal outlet conveyance."""
    arrays = record["arrays"]
    capacities = np.array([support_volume(record, node, arrays["max_stage_m"][node]) for node in range(4)])
    upper_stages = arrays["max_stage_m"].copy()
    maximum_q = np.array([max(0., manning_flux(record, upper_stages, float(stage))[-1]) for stage in tailwater_stage_m[1:]])
    volume_in = np.cumsum((inlet_q_m3_s + lateral_q_m3_s.sum(axis=1)) * dt_s)
    maximum_out = np.cumsum(maximum_q * dt_s)
    exceed = volume_in - maximum_out > capacities.sum() + ABS_VOLUME_TOLERANCE_M3
    cumulative_net = np.r_[0., volume_in - maximum_out]
    interval_drawup = cumulative_net[1:] - np.minimum.accumulate(cumulative_net[:-1])
    interval_exceed = interval_drawup > capacities.sum() + ABS_VOLUME_TOLERANCE_M3
    return {"capacity_m3": capacities, "max_outflow_q_m3_s": maximum_q,
            "cumulative_input_m3": volume_in, "cumulative_max_outflow_m3": maximum_out,
            "exceeded_mask": exceed,
            "first_exceed_step": int(np.flatnonzero(exceed)[0]) if exceed.any() else None,
            "any_interval_drawup_m3": interval_drawup,
            "any_interval_first_exceed_step": int(np.flatnonzero(interval_exceed)[0]) if interval_exceed.any() else None,
            "bound_scope": "necessary_only_null_is_inconclusive_no_virtual_early_drainage_credit"}


def prepare_manning_storage(record, geometry, *, initial_stage_m, inlet_q_m3_s,
                            lateral_q_m3_s, tailwater_stage_m, dt_s):
    """Bounded four-control-volume implicit stage solve, preserving failed prefix."""
    validate_tributary_geometry(record, geometry)
    if not isinstance(inlet_q_m3_s, np.ndarray) or inlet_q_m3_s.ndim != 1:
        raise ValueError("resource-checkable inlet required")
    steps = inlet_q_m3_s.size
    resources = preflight(steps, dt_s)
    arrays = record["arrays"]
    initial = np.asarray(initial_stage_m)
    if initial.shape != (4,) or lateral_q_m3_s.shape != (steps, 4) or tailwater_stage_m.shape != (steps + 1,):
        raise ValueError("Manning input shapes")
    for values in (initial, inlet_q_m3_s, lateral_q_m3_s, tailwater_stage_m):
        if values.dtype != np.dtype("float64") or not np.isfinite(values).all():
            raise ValueError("finite float64 Manning forcing required")
    if (inlet_q_m3_s < 0).any() or (lateral_q_m3_s < 0).any():
        raise ValueError("negative supplied inflow")
    lower, upper = arrays["min_bed_m"], arrays["max_stage_m"]
    if (initial < lower).any() or (initial > upper).any():
        raise ValueError("initial stage outside source bank support")
    initial_storage = np.array([support_volume(record, node, initial[node]) for node in range(4)])
    stages = [initial.copy()]
    storages = [initial_storage]
    fluxes = []
    residuals = []
    iterations = []
    failure = None
    spent = 0
    for step in range(steps):
        step_start = spent
        before = storages[-1]
        external = lateral_q_m3_s[step].copy()
        external[0] += inlet_q_m3_s[step]
        tolerance = ABS_VOLUME_TOLERANCE_M3 + REL_VOLUME_TOLERANCE * (before + dt_s * external)
        def residual(stage):
            nonlocal spent
            if spent >= MAX_EVALUATIONS or spent - step_start >= MAX_STEP_RESIDUAL_CALLS:
                raise RuntimeError("Manning residual evaluation ceiling")
            spent += 1
            volume = np.array([support_volume(record, node, stage[node]) for node in range(4)])
            flux = manning_flux(record, stage, float(tailwater_stage_m[step + 1]))
            internal = np.r_[0., flux[:-1]] - flux
            return volume - before - dt_s * (external + internal)
        try:
            initial_error = residual(stages[-1])
            if np.max(np.abs(initial_error)) == 0:
                next_stage = stages[-1].copy()
                evaluation_count = 1
            else:
                def depth_residual(depth):
                    return residual(lower + depth)
                solved = least_squares(depth_residual, np.clip(stages[-1] - lower, 1e-10, upper - lower - 1e-10),
                    bounds=(np.zeros(4), upper - lower), max_nfev=MAX_STEP_EVALUATIONS,
                    ftol=1e-12, xtol=1e-12, gtol=1e-12, jac="3-point", x_scale="jac")
                next_stage = lower + solved.x
                evaluation_count = int(solved.nfev)
            error = residual(next_stage)
        except RuntimeError as exc:
            if str(exc) != "Manning residual evaluation ceiling":
                raise
            failure = {"step": step, "reason": "residual_evaluation_budget_exhausted"}
            break
        if (np.abs(error) > tolerance).any():
            failure = {"step": step, "reason": "bank_limited_implicit_residual_or_solver_limit",
                       "max_residual_m3": float(np.abs(error).max()), "nfev": evaluation_count,
                       "near_upper_bank_nodes": np.flatnonzero(upper - next_stage < 1e-7).tolist()}
            break
        flux = manning_flux(record, next_stage, float(tailwater_stage_m[step + 1]))
        volume = np.array([support_volume(record, node, next_stage[node]) for node in range(4)])
        stages.append(next_stage.copy())
        storages.append(volume)
        fluxes.append(flux)
        residuals.append(error)
        iterations.append(evaluation_count)
    committed = len(fluxes)
    saved = {"metadata": {"schema": "mountain-manning-diffusive-storage-v1", "dt_s": float(dt_s),
              "roughness_s_m_third": ROUGHNESS_S_M_THIRD,
              "status": "completed" if failure is None else "refused", "failure": failure,
              "committed_steps": committed, "requested_steps": steps, "resources": resources,
              "residual_evaluations": spent,
              "scope": "independent_local_implicit_Manning_diffusive_no_momentum_not_Saint_Venant",
              "source_binding": record["metadata"]["source_binding"]},
             "arrays": {"initial_stage_m": initial.copy(), "inlet_q_m3_s": inlet_q_m3_s.copy(),
               "lateral_q_m3_s": lateral_q_m3_s.copy(), "tailwater_stage_m": tailwater_stage_m.copy(),
               "stage_m": np.asarray(stages), "storage_m3": np.asarray(storages),
               "qedges_m3_s": np.asarray(fluxes).reshape(-1, 4),
               "node_residual_m3": np.asarray(residuals).reshape(-1, 4),
               "solver_evaluations": np.asarray(iterations, dtype=np.int64)}}
    validate_manning_storage(saved, record, geometry)
    return saved


def validate_manning_storage(saved, record, geometry):
    """Static bank, source, V(h), exact signed Manning and volume equations."""
    validate_tributary_geometry(record, geometry)
    meta, state = saved["metadata"], saved["arrays"]
    if meta["schema"] != "mountain-manning-diffusive-storage-v1" or meta["scope"] != "independent_local_implicit_Manning_diffusive_no_momentum_not_Saint_Venant":
        raise ValueError("Manning schema/scope identity")
    requested, committed = meta["requested_steps"], meta["committed_steps"]
    if meta["status"] not in ("completed", "refused") or type(committed) is not int:
        raise ValueError("unknown Manning status or prefix type")
    if type(meta["residual_evaluations"]) is not int or not 0 <= meta["residual_evaluations"] <= MAX_EVALUATIONS:
        raise ValueError("Manning residual work budget")
    if meta["resources"] != preflight(requested, meta["dt_s"]) or not 0 <= committed <= requested:
        raise ValueError("Manning resource metadata")
    if meta["roughness_s_m_third"] != ROUGHNESS_S_M_THIRD or meta["source_binding"] != record["metadata"]["source_binding"]:
        raise ValueError("roughness/source identity mismatch")
    if (meta["status"] == "completed" and (committed != requested or meta["failure"] is not None)) or (meta["status"] == "refused" and (committed == requested or meta["failure"] is None or meta["failure"]["step"] != committed)):
        raise ValueError("Manning status prefix")
    specs = {"initial_stage_m": (4,), "inlet_q_m3_s": (requested,), "lateral_q_m3_s": (requested, 4),
             "tailwater_stage_m": (requested + 1,), "stage_m": (committed + 1, 4),
             "storage_m3": (committed + 1, 4), "qedges_m3_s": (committed, 4),
             "node_residual_m3": (committed, 4), "solver_evaluations": (committed,)}
    if set(state) != set(specs):
        raise ValueError("Manning exact saved schema")
    for key, shape in specs.items():
        values = state[key]
        dtype = np.dtype("int64" if key == "solver_evaluations" else "float64")
        if values.shape != shape or values.dtype != dtype or not np.isfinite(values).all():
            raise ValueError("Manning saved dtype/shape/finite")
    if not np.array_equal(state["stage_m"][0], state["initial_stage_m"]):
        raise ValueError("Manning initial stage identity")
    if (state["inlet_q_m3_s"] < 0).any() or (state["lateral_q_m3_s"] < 0).any():
        raise ValueError("negative external Manning forcing")
    if ((state["solver_evaluations"] < 1) | (state["solver_evaluations"] > MAX_STEP_EVALUATIONS)).any():
        raise ValueError("Manning solver step budget")
    source = record["arrays"]
    if (state["stage_m"] < source["min_bed_m"] - 1e-9).any() or (state["stage_m"] > source["max_stage_m"] + 1e-9).any() or (state["storage_m3"] < 0).any():
        raise ValueError("Manning bank/dry positivity")
    for node in range(4):
        selected = source["row_owner"] == node
        beds = source["H2_m"][selected].ravel()
        weights = source["support_area_m2"][selected].ravel()
        volumes = np.maximum(state["stage_m"][:, node, None] - beds[None, :], 0) @ weights
        if not np.allclose(state["storage_m3"][:, node], volumes, rtol=0, atol=1e-8):
            raise ValueError("Manning storage support forgery")
    expected_flux = np.array([manning_flux(record, stage, float(tail)) for stage, tail in zip(state["stage_m"][1:], state["tailwater_stage_m"][1:committed + 1])]).reshape(-1, 4)
    if not np.allclose(state["qedges_m3_s"], expected_flux, rtol=1e-12, atol=1e-12):
        raise ValueError("Manning signed section flux forged")
    external = state["lateral_q_m3_s"][:committed].copy()
    external[:, 0] += state["inlet_q_m3_s"][:committed]
    net = np.column_stack((np.zeros(committed), expected_flux[:, :-1])) - expected_flux
    residual = np.diff(state["storage_m3"], axis=0) - meta["dt_s"] * (external + net)
    tolerance = ABS_VOLUME_TOLERANCE_M3 + REL_VOLUME_TOLERANCE * (state["storage_m3"][:-1] + external * meta["dt_s"])
    if not np.allclose(state["node_residual_m3"], residual, rtol=0, atol=1e-8) or (np.abs(residual) > tolerance * 1.01).any():
        raise ValueError("Manning per-node balance")
    return {"max_node_residual_m3": float(np.abs(residual).max(initial=0)),
            "final_storage_m3": float(state["storage_m3"][-1].sum()),
            "signed_external_outflow_m3": float(expected_flux[:, -1].sum() * meta["dt_s"])}


def save_manning_storage(path, saved, record, geometry):
    validate_manning_storage(saved, record, geometry)
    manifest = {"metadata": saved["metadata"], "identity_sha256": identity(saved["arrays"], saved["metadata"]),
                "geometry_identity": identity(record["arrays"], record["metadata"])}
    encoded = _json(manifest).encode("utf-8")
    if len(encoded) > 65536:
        raise ValueError("Manning manifest budget")
    stream = io.BytesIO()
    np.savez_compressed(stream, manifest=np.frombuffer(encoded, dtype=np.uint8), **saved["arrays"])
    if stream.tell() > MAX_BYTES:
        raise ValueError("Manning archive byte ceiling")
    publish_bytes(path, stream.getvalue())


def load_manning_storage(path, record, geometry, *, expected_sha256, trusted_forcing):
    def headers(specs):
        keys = {"initial_stage_m", "inlet_q_m3_s", "lateral_q_m3_s", "tailwater_stage_m", "stage_m",
                "storage_m3", "qedges_m3_s", "node_residual_m3", "solver_evaluations", "manifest"}
        if set(specs) != keys:
            raise ValueError("exact Manning archive keys")
        requested_shape = specs["inlet_q_m3_s"][0]
        state_shape = specs["stage_m"][0]
        if len(requested_shape) != 1 or len(state_shape) != 2:
            raise ValueError("Manning header axes")
        requested, committed = requested_shape[0], state_shape[0] - 1
        if not 1 <= requested <= MAX_STEPS or not 0 <= committed <= requested:
            raise ValueError("Manning header steps")
        shapes = {"initial_stage_m": (4,), "inlet_q_m3_s": (requested,), "lateral_q_m3_s": (requested, 4),
                  "tailwater_stage_m": (requested + 1,), "stage_m": (committed + 1, 4),
                  "storage_m3": (committed + 1, 4), "qedges_m3_s": (committed, 4),
                  "node_residual_m3": (committed, 4), "solver_evaluations": (committed,)}
        for key, shape in shapes.items():
            dtype = np.dtype("int64" if key == "solver_evaluations" else "float64")
            if specs[key] != (shape, dtype):
                raise ValueError("Manning exact header: " + key)
        shape, dtype = specs["manifest"]
        if len(shape) != 1 or not 1 <= shape[0] <= 65536 or dtype != np.dtype("uint8"):
            raise ValueError("Manning manifest header")
    arrays = checked_archive(path, expected_sha256=expected_sha256, max_bytes=MAX_BYTES, header_validator=headers)
    manifest = _strict_json(arrays.pop("manifest").tobytes().decode("utf-8"))
    if set(manifest) != {"metadata", "identity_sha256", "geometry_identity"}:
        raise ValueError("Manning manifest schema")
    if manifest["geometry_identity"] != identity(record["arrays"], record["metadata"]) or manifest["identity_sha256"] != identity(arrays, manifest["metadata"]):
        raise ValueError("Manning geometry/integrity mismatch")
    if set(trusted_forcing) != {"initial_stage_m", "inlet_q_m3_s", "lateral_q_m3_s", "tailwater_stage_m", "dt_s"}:
        raise ValueError("external Manning forcing trust required")
    for key, value in trusted_forcing.items():
        if key == "dt_s":
            if manifest["metadata"][key] != value:
                raise ValueError("external timestep mismatch")
        elif not np.array_equal(arrays[key], value):
            raise ValueError("external forcing mismatch: " + key)
    saved = {"metadata": manifest["metadata"], "arrays": arrays}
    validate_manning_storage(saved, record, geometry)
    saved["arrays"] = {key: readonly(value) for key, value in arrays.items()}
    return saved
