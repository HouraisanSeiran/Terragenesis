"""Independent geometry, flux and ledger validation for coupled channel/lake traces."""

from dataclasses import asdict
import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelNetwork, GEOMETRY_SEMANTICS
from .metric_channel_product import NETWORK_FIELDS, LEGACY_NETWORK_FIELDS
from terrain_pipeline.lake import LakeStorage as LakeStorage
from terrain_pipeline.lake import LakeOutlet as LakeOutlet
from .metric_boundary_coupling import BoundarySeries, CoupledForcing


SCHEMA = "terragenesis-channel-lake-boundary-v2"
ALGORITHM = "manning-lake-boundary-explicit-v1"
MAX_BYTES = 128 * 1024 * 1024
NETWORK = NETWORK_FIELDS
BOUNDARY = ("node_ids", "kinds", "allow_inflow", "time_seconds", "stage_m", "discharge_m3_s", "conductance_m2_s")
TRACE = ("time_seconds", "channel_volume_m3", "lake_volume_m3", "channel_stage_m", "lake_stage_m",
         "channel_q_m3_s", "lake_outlet_q_m3_s", "boundary_q_m3_s", "channel_local_q_m3_s",
         "lake_local_q_m3_s", "channel_donor_q_m3_s", "lake_donor_q_m3_s", "channel_boundary_volume_m3",
         "lake_external_volume_m3", "channel_residual_m3", "lake_residual_m3", "stability_number")
SEMANTICS = {"state": "initial_and_committed_internal_step_endpoints", "Q": "pre_step_interval_average",
             "positive_boundary_Q": "out_of_domain", "exchange": "same_step_equal_volume_debit_and_credit",
             "lake_footprint": "finite_source_support_level_pool_not_contribution_mask",
             "geometry": GEOMETRY_SEMANTICS}
LIMITATIONS = ["rectangular channel and finite fixed-support lake",
               "prescribed stage uses explicit conductance, not backwater",
               "no sediment, bed change, or natural outlet certification"]


def _equal(observed, expected, name):
    if np.shape(observed) != np.shape(expected) or not np.isfinite(expected).all() or not np.allclose(observed, expected, rtol=1e-10, atol=1e-10):
        raise ValueError("coupled saved mismatch: " + name)


def _stage_equal(observed, expected, name):
    tolerance = np.maximum(1e-9, 8. * np.abs(np.spacing(expected)))
    if np.shape(observed) != np.shape(expected) or not np.isfinite(expected).all() or np.any(np.abs(observed - expected) > tolerance):
        raise ValueError("coupled saved stage mismatch: " + name)


def make_coupled_product(network, lakes, outlets, channel_to_lake, forcing, boundaries, result):
    if result["metadata"]["algorithm"] != ALGORITHM:
        raise ValueError("unsupported coupled algorithm")
    arrays = {"network_" + key: getattr(network, key) for key in NETWORK}
    arrays.update({"boundary_" + key: getattr(boundaries, key) for key in BOUNDARY})
    offsets = np.r_[0, np.cumsum([len(lake.cell_ids) for lake in lakes])].astype(np.int64)
    arrays["lake_offsets"] = offsets
    for key, dtype in (("cell_ids", np.int64), ("bed_elevation_m", np.float64), ("cell_area_m2", np.float64)):
        arrays["lake_" + key] = np.concatenate([getattr(lake, key) for lake in lakes]) if lakes else np.empty(0, dtype)
    arrays["channel_to_lake"] = np.asarray(channel_to_lake).copy()
    arrays["forcing_time_seconds"] = forcing.time_seconds
    arrays["forcing_channel_local_q_m3_s"] = forcing.channel_local_q_m3_s
    arrays["forcing_lake_local_q_m3_s"] = forcing.lake_local_q_m3_s
    arrays.update({"trace_" + key: value for key, value in result["arrays"].items()})
    metadata = {"schema": SCHEMA, "result": dict(result["metadata"]), "semantics": dict(SEMANTICS),
                "unfinished_time_seconds": None if result["metadata"]["status"] == "complete" else
                    [float(result["arrays"]["time_seconds"][-1]), float(forcing.time_seconds[-1])],
                "network": {key: getattr(network, key) for key in ("source_identity_sha256", "section_source", "roughness_source")},
                "lakes": [{key: getattr(lake, key) for key in ("seed_cell_id", "max_stage_m", "source_identity_sha256", "footprint_policy")} for lake in lakes],
                "outlets": [asdict(outlet) for outlet in outlets],
                "forcing_source_identity_sha256": forcing.source_identity_sha256,
                "boundary_source_identity_sha256": boundaries.source_identity_sha256,
                "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    arrays = {key: readonly(value) for key, value in arrays.items()}
    product = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_coupled_product(product)
    return product


def decode_coupled_product(product):
    arrays, meta = product["arrays"], product["metadata"]
    fields = LEGACY_NETWORK_FIELDS if meta["schema"] == "terragenesis-channel-lake-boundary-v1" else NETWORK
    network = ChannelNetwork(**{key: arrays["network_" + key] for key in fields}, **meta["network"])
    lakes = []
    for index, record in enumerate(meta["lakes"]):
        start, stop = arrays["lake_offsets"][index:index + 2]
        lakes.append(LakeStorage(**{key: arrays["lake_" + key][start:stop] for key in
                                   ("cell_ids", "bed_elevation_m", "cell_area_m2")}, **record))
    outlets = tuple(LakeOutlet(**record) for record in meta["outlets"])
    forcing = CoupledForcing(arrays["forcing_time_seconds"], arrays["forcing_channel_local_q_m3_s"],
                             arrays["forcing_lake_local_q_m3_s"], meta["forcing_source_identity_sha256"])
    boundaries = BoundarySeries(**{key: arrays["boundary_" + key] for key in BOUNDARY},
                                 source_identity_sha256=meta["boundary_source_identity_sha256"])
    return network, tuple(lakes), outlets, arrays["channel_to_lake"], forcing, boundaries


def independent_flux(network, lakes, outlets, mapping, boundaries, channel_volume, lake_volume, interval):
    """Evaluate equations independently; no routing/solver entry point is called."""
    count, lake_count = len(channel_volume), len(lake_volume)
    area = channel_volume / network.length_m
    depth = area / network.width_m
    stage = network.bed_elevation_m + depth
    perimeter = network.width_m + 2. * depth
    radius = area / perimeter
    active = np.isin(network.terminal_kind, ("interior", "open_outflow"))
    q = np.where(active, area * radius ** (2. / 3.) * np.sqrt(network.bed_slope) / network.roughness, 0.)
    speed = np.where(active, radius ** (2. / 3.) * np.sqrt(network.bed_slope) / network.roughness
                     * (5. / 3. - 4. * depth / (3. * perimeter)), 0.)
    rates = speed / network.length_m
    boundary_q = np.zeros(len(boundaries.node_ids))
    for index, node in enumerate(boundaries.node_ids):
        kind = boundaries.kinds[index]
        if kind in ("closed_wall", "unknown_boundary"):
            q[node] = 0.
            rates[node] = 0.
        elif kind == "prescribed_stage":
            with np.errstate(over="ignore", invalid="ignore"):
                q[node] = boundaries.conductance_m2_s[index] * (stage[node] - boundaries.stage_m[interval, index])
            if not boundaries.allow_inflow[index]:
                q[node] = max(0., q[node])
            if channel_volume[node] == 0. and q[node] > 0.:
                q[node] = 0.
            rates[node] = boundaries.conductance_m2_s[index] / (network.length_m[node] * network.width_m[node])
        elif kind == "prescribed_discharge":
            q[node] = boundaries.discharge_m3_s[interval, index]
            rates[node] = 0.
        boundary_q[index] = q[node]
    lake_stage = np.array([lake.stage_at_volume(float(volume)) for lake, volume in zip(lakes, lake_volume)])
    lake_q = np.zeros(len(outlets))
    lake_out = np.zeros(lake_count)
    lake_rates = np.zeros(lake_count)
    lake_external = np.zeros(lake_count)
    channel_donor = np.zeros(count)
    lake_donor = np.zeros(lake_count)
    channel_external = np.zeros(count)
    for node, target in enumerate(network.receiver):
        if target >= 0:
            channel_donor[target] += q[node]
        elif mapping[node] >= 0:
            lake_donor[mapping[node]] += q[node]
        else:
            channel_external[node] = q[node]
    for index, outlet in enumerate(outlets):
        lake_index = outlet.lake_index
        head = max(0., lake_stage[lake_index] - outlet.crest_stage_m)
        lake_q[index] = outlet.coefficient_m3_s_m15 * head ** 1.5
        lake_out[lake_index] += lake_q[index]
        wet_area = lakes[lake_index].surface_area_at_stage(float(lake_stage[lake_index]))
        if wet_area > 0.:
            lake_rates[lake_index] += 1.5 * outlet.coefficient_m3_s_m15 * np.sqrt(head) / wet_area
        if outlet.receiver < 0:
            lake_external[lake_index] += lake_q[index]
        elif outlet.receiver < count:
            channel_donor[outlet.receiver] += lake_q[index]
        else:
            lake_donor[outlet.receiver - count] += lake_q[index]
    return {"channel_q": q, "lake_outlet_q": lake_q, "boundary_q": boundary_q,
            "channel_donor": channel_donor, "lake_donor": lake_donor, "channel_external": channel_external,
            "lake_external": lake_external, "lake_out": lake_out, "channel_stage": stage,
            "lake_stage": lake_stage, "channel_rate": rates, "lake_rate": lake_rates}


def next_failure_reason(network, lakes, outlets, mapping, forcing, boundaries, cv, lv, now, steps, config):
    """Check the next proposed physical step independently of the coupled solver."""
    nc, nl, no, nb = len(cv), len(lv), len(outlets), len(boundaries.node_ids)
    if steps >= config.max_steps:
        return "maximum step count exceeded"
    if steps >= MAX_BYTES // (8 * (28 * nc + 20 * nl + 4 * no + 4 * nb + 4)):
        return "trace byte budget exceeded"
    interval = int(np.searchsorted(forcing.time_seconds, now, side="right") - 1)
    end = float(forcing.time_seconds[interval + 1])
    try:
        flux = independent_flux(network, lakes, outlets, mapping, boundaries, cv, lv, interval)
    except (ValueError, OverflowError, FloatingPointError):
        return "nonfinite hydraulic flux"
    if any(not np.isfinite(value).all() for value in flux.values()):
        return "nonfinite hydraulic flux"
    dt = min(config.max_dt_seconds, end - now)
    rate = max(float(np.max(flux["channel_rate"], initial=0.)), float(np.max(flux["lake_rate"], initial=0.)))
    if rate > 0.:
        dt = min(dt, config.cfl / rate)
    for volume, outflow in ((cv, flux["channel_q"]), (lv, flux["lake_out"])):
        positive = outflow > 0.
        if positive.any():
            dt = min(dt, float(np.min(config.cfl * volume[positive] / outflow[positive])))
    if not np.isfinite(dt) or dt <= 0. or dt < config.min_dt_seconds and end - now > config.min_dt_seconds:
        return "minimum internal step required or nonfinite time step"
    if now + dt == now:
        return "time resolution exhausted"
    next_time = end if now + dt >= end else now + dt
    dt = next_time - now
    if dt > config.max_dt_seconds * (1. + 1e-12):
        return "maximum internal step exceeded at time resolution"
    cc = network.length_m * network.width_m * network.max_depth_m
    lc = np.array([lake.capacity_m3 for lake in lakes])
    with np.errstate(over="ignore", invalid="ignore"):
        next_cv = cv + dt * (forcing.channel_local_q_m3_s[interval] + flux["channel_donor"] - flux["channel_q"])
        next_lv = lv + dt * (forcing.lake_local_q_m3_s[interval] + flux["lake_donor"] - flux["lake_out"])
    if (not np.isfinite(next_cv).all() or not np.isfinite(next_lv).all()
            or np.any(next_cv < -1e-12 * np.maximum(1., cc)) or np.any(next_lv < -1e-12 * np.maximum(1., lc))):
        return "nonfinite or negative volume"
    if np.any(next_cv > cc):
        return "channel depth limit exceeded"
    if np.any(next_lv > lc):
        return "lake capacity exceeded"
    next_cv, next_lv = np.maximum(next_cv, 0.), np.maximum(next_lv, 0.)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        area = next_cv / network.length_m
        depth = area / network.width_m
        perimeter = network.width_m + 2. * depth
        active = np.isin(network.terminal_kind, ("interior", "open_outflow"))
        next_q = np.where(active, area * (area / perimeter) ** (2. / 3.) * np.sqrt(network.bed_slope) / network.roughness, 0.)
        next_wave = np.where(active, (area / perimeter) ** (2. / 3.) * np.sqrt(network.bed_slope) / network.roughness
                             * (5. / 3. - 4. * depth / (3. * perimeter)), 0.)
        next_stage = network.bed_elevation_m + depth
    try:
        lake_stages = np.array([lake.stage_at_volume(float(v)) for lake, v in zip(lakes, next_lv)])
    except ValueError:
        return "nonfinite hydraulic state"
    if any(not np.isfinite(value).all() for value in (depth, next_q, next_wave, next_stage, lake_stages)):
        return "nonfinite hydraulic state"
    with np.errstate(over="ignore", invalid="ignore"):
        totals = (np.sum(next_cv) + np.sum(next_lv),
                  dt * (np.sum(forcing.channel_local_q_m3_s[interval]) + np.sum(forcing.lake_local_q_m3_s[interval])),
                  np.sum(dt * flux["channel_external"]) + np.sum(dt * flux["lake_external"]),
                  np.sum(flux["channel_donor"]) + np.sum(flux["lake_donor"]))
    if (not np.isfinite(dt * flux["channel_external"]).all() or not np.isfinite(dt * flux["lake_external"]).all()
            or not np.isfinite(totals).all()):
        return "nonfinite water ledger"
    if not np.isfinite(rate * dt) or rate * dt > config.cfl * (1. + 1e-12):
        return "stability bound exceeded at time resolution"
    return None


def validate_coupled_product(product):
    arrays, meta = product["arrays"], product["metadata"]
    legacy = meta.get("schema") == "terragenesis-channel-lake-boundary-v1"
    fields = LEGACY_NETWORK_FIELDS if legacy else NETWORK
    semantics = {key: value for key, value in SEMANTICS.items() if key != "geometry"} if legacy else SEMANTICS
    expected = {"network_" + key for key in fields} | {"boundary_" + key for key in BOUNDARY} | {"trace_" + key for key in TRACE}
    expected |= {"lake_offsets", "lake_cell_ids", "lake_bed_elevation_m", "lake_cell_area_m2", "channel_to_lake",
                 "forcing_time_seconds", "forcing_channel_local_q_m3_s", "forcing_lake_local_q_m3_s"}
    if (set(product) != {"arrays", "metadata", "identity_sha256"} or set(arrays) != expected
            or set(meta) != {"schema", "result", "unfinished_time_seconds", "semantics", "network", "lakes", "outlets", "forcing_source_identity_sha256",
                             "boundary_source_identity_sha256", "hydraulic_ready", "natural_outlet_verified", "publishable"}
            or meta["schema"] != ("terragenesis-channel-lake-boundary-v1" if legacy else SCHEMA) or meta["semantics"] != semantics
            or any(meta[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable"))
            or product["identity_sha256"] != identity(arrays, meta)
            or sum(value.nbytes for value in arrays.values()) > MAX_BYTES):
        raise ValueError("coupled schema/identity/budget mismatch")
    offsets = arrays["lake_offsets"]
    if (offsets.dtype != np.int64 or offsets.shape != (len(meta["lakes"]) + 1,) or offsets[0] != 0
            or np.any(np.diff(offsets) <= 0) or offsets[-1] != arrays["lake_cell_ids"].size
            or any(arrays["lake_" + key].shape != (offsets[-1],) for key in ("bed_elevation_m", "cell_area_m2"))):
        raise ValueError("invalid coupled lake offsets")
    if len(set(arrays["lake_cell_ids"].tolist())) != len(arrays["lake_cell_ids"]):
        raise ValueError("overlapping lake source cells")
    network, lakes, outlets, mapping, forcing, boundaries = decode_coupled_product(product)
    nc, nl, no, nb = len(network.receiver), len(lakes), len(outlets), len(boundaries.node_ids)
    if nl > 256 or no > 4096 or len(arrays["lake_cell_ids"]) > 65536:
        raise ValueError("coupled pool/outlet/support resource limit exceeded")
    if (mapping.dtype != np.int64 or mapping.shape != (nc,) or np.any((mapping < -1) | (mapping >= nl))
            or np.any((mapping >= 0) & ((network.receiver >= 0) | (network.terminal_kind != "open_outflow")))
            or any(node >= nc or mapping[node] >= 0 or network.receiver[node] >= 0 for node in boundaries.node_ids)
            or not np.array_equal(forcing.time_seconds, boundaries.time_seconds)):
        raise ValueError("invalid lake mapping/boundary topology")
    for outlet in outlets:
        if (not 0 <= outlet.lake_index < nl or not -1 <= outlet.receiver < nc + nl
                or outlet.receiver == nc + outlet.lake_index
                or not float(lakes[outlet.lake_index].bed_elevation_m.min()) <= outlet.crest_stage_m <= lakes[outlet.lake_index].max_stage_m):
            raise ValueError("invalid lake outlet topology/crest")
    result = meta["result"]
    if (set(result) != {"algorithm", "status", "failure_reason", "last_time_seconds", "requested_end_time_seconds", "config",
                       "limitations", "hydraulic_ready", "natural_outlet_verified", "publishable"}
            or result["algorithm"] != ALGORITHM or result["status"] not in ("complete", "failed_prefix")
            or result["limitations"] != LIMITATIONS
            or any(result[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable"))):
        raise ValueError("unsupported coupled result")
    config = ChannelConfig(**result["config"])
    times = arrays["trace_time_seconds"]
    if (times.dtype != np.float64 or times.ndim != 1 or not 1 <= len(times) <= config.max_steps + 1
            or not np.isfinite(times).all() or not np.isfinite(np.diff(times)).all() or np.any(np.diff(times) <= 0.)
            or times[0] != forcing.time_seconds[0] or times[-1] > forcing.time_seconds[-1]
            or result["last_time_seconds"] != float(times[-1]) or result["requested_end_time_seconds"] != float(forcing.time_seconds[-1])):
        raise ValueError("invalid coupled chronology")
    k = len(times) - 1
    widths = {"channel_volume_m3": nc, "lake_volume_m3": nl, "channel_stage_m": nc, "lake_stage_m": nl,
              "channel_q_m3_s": nc, "lake_outlet_q_m3_s": no, "boundary_q_m3_s": nb,
              "channel_local_q_m3_s": nc, "lake_local_q_m3_s": nl, "channel_donor_q_m3_s": nc,
              "lake_donor_q_m3_s": nl, "channel_boundary_volume_m3": nc, "lake_external_volume_m3": nl,
              "channel_residual_m3": nc, "lake_residual_m3": nl}
    for key, width in widths.items():
        value = arrays["trace_" + key]
        states = key in ("channel_volume_m3", "lake_volume_m3", "channel_stage_m", "lake_stage_m")
        if value.dtype != np.float64 or value.shape != (k + int(states), width) or not np.isfinite(value).all():
            raise ValueError("invalid coupled trace: " + key)
    cv, lv = arrays["trace_channel_volume_m3"], arrays["trace_lake_volume_m3"]
    if np.any(cv < 0.) or np.any(lv < 0.):
        raise ValueError("negative coupled volume")
    channel_capacity = network.length_m * network.width_m * network.max_depth_m
    if not np.isfinite(channel_capacity).all() or np.any(cv > channel_capacity + 1e-10):
        raise ValueError("coupled channel capacity exceeded")
    if any(np.any(lv[:, i] > lake.capacity_m3 + 1e-10) for i, lake in enumerate(lakes)):
        raise ValueError("coupled lake capacity exceeded")
    _stage_equal(arrays["trace_channel_stage_m"], network.bed_elevation_m + (cv / network.length_m) / network.width_m, "channel stage")
    for index, lake in enumerate(lakes):
        _stage_equal(arrays["trace_lake_stage_m"][:, index], np.array([lake.stage_at_volume(float(v)) for v in lv[:, index]]), "lake stage")
    dt = np.diff(times)
    stability = arrays["trace_stability_number"]
    if stability.dtype != np.float64 or stability.shape != (k,) or not np.isfinite(stability).all():
        raise ValueError("invalid stability trace")
    for step in range(k):
        interval = int(np.searchsorted(forcing.time_seconds, times[step], side="right") - 1)
        if (times[step + 1] > forcing.time_seconds[interval + 1] or dt[step] > config.max_dt_seconds * (1. + 1e-12)
                or dt[step] < config.min_dt_seconds and times[step + 1] != forcing.time_seconds[interval + 1]):
            raise ValueError("coupled step crosses forcing boundary or configured bounds")
        flux = independent_flux(network, lakes, outlets, mapping, boundaries, cv[step], lv[step], interval)
        for saved, computed in (("channel_q_m3_s", "channel_q"), ("lake_outlet_q_m3_s", "lake_outlet_q"),
                                ("boundary_q_m3_s", "boundary_q"), ("channel_donor_q_m3_s", "channel_donor"),
                                ("lake_donor_q_m3_s", "lake_donor")):
            _equal(arrays["trace_" + saved][step], flux[computed], saved)
        cq, lq = forcing.channel_local_q_m3_s[interval], forcing.lake_local_q_m3_s[interval]
        _equal(arrays["trace_channel_local_q_m3_s"][step], cq, "channel local linkage")
        _equal(arrays["trace_lake_local_q_m3_s"][step], lq, "lake local linkage")
        cd = dt[step] * (cq + flux["channel_donor"] - flux["channel_q"])
        ld = dt[step] * (lq + flux["lake_donor"] - flux["lake_out"])
        _equal(cv[step + 1] - cv[step], cd, "channel continuity")
        _equal(lv[step + 1] - lv[step], ld, "lake continuity")
        _equal(arrays["trace_channel_residual_m3"][step], cv[step + 1] - cv[step] - cd, "channel residual")
        _equal(arrays["trace_lake_residual_m3"][step], lv[step + 1] - lv[step] - ld, "lake residual")
        _equal(arrays["trace_channel_boundary_volume_m3"][step], dt[step] * flux["channel_external"], "channel boundary volume")
        _equal(arrays["trace_lake_external_volume_m3"][step], dt[step] * flux["lake_external"], "lake boundary volume")
        rate = max(float(np.max(flux["channel_rate"], initial=0.)), float(np.max(flux["lake_rate"], initial=0.)))
        _equal(stability[step], rate * dt[step], "stability")
        if stability[step] > config.cfl * (1. + 1e-10):
            raise ValueError("coupled stability exceeded")
        for volume, outgoing in ((cv[step], flux["channel_q"]), (lv[step], flux["lake_out"])):
            moving = outgoing > 0.
            if np.any(dt[step] * outgoing[moving] > config.cfl * volume[moving] * (1. + 1e-10)):
                raise ValueError("coupled positivity timestep limit exceeded")
    if result["status"] == "complete":
        if times[-1] != forcing.time_seconds[-1] or result["failure_reason"] is not None or meta["unfinished_time_seconds"] is not None:
            raise ValueError("incomplete coupled result claimed complete")
    else:
        if times[-1] >= forcing.time_seconds[-1] or not isinstance(result["failure_reason"], str) or not result["failure_reason"].strip():
            raise ValueError("invalid coupled failed prefix")
        if (meta["unfinished_time_seconds"] != [float(times[-1]), float(forcing.time_seconds[-1])]
                or result["failure_reason"] != next_failure_reason(network, lakes, outlets, mapping, forcing, boundaries,
                                                                  cv[-1], lv[-1], float(times[-1]), k, config)):
            raise ValueError("coupled prefix does not have the declared next-step failure")
    local = float(np.sum(arrays["trace_channel_local_q_m3_s"] * dt[:, None]) + np.sum(arrays["trace_lake_local_q_m3_s"] * dt[:, None]))
    external = float(np.sum(arrays["trace_channel_boundary_volume_m3"]) + np.sum(arrays["trace_lake_external_volume_m3"]))
    change = float(np.sum(cv[-1] - cv[0]) + np.sum(lv[-1] - lv[0]))
    with np.errstate(over="ignore", invalid="ignore"):
        initial = float(cv[0].sum() + lv[0].sum())
        final = float(cv[-1].sum() + lv[-1].sum())
    residual = local - external - change
    if (not np.isfinite([local, external, change, initial, final, residual]).all()
            or abs(residual) > 1e-8 * max(1., abs(local), abs(external), initial)):
        raise ValueError("coupled global budget mismatch")
    return True


def save_coupled_product(path, product):
    save_bundle(path, product, validator=validate_coupled_product)


def load_coupled_product(path, *, expected_sha256, expected_identity):
    product = load_bundle(path, expected_sha256=expected_sha256, validator=validate_coupled_product, max_bytes=MAX_BYTES)
    if product["identity_sha256"] != expected_identity:
        raise ValueError("external coupled identity mismatch")
    return product


def sample_coupled_output(product, times):
    validate_coupled_product(product)
    times = np.asarray(times)
    source = product["arrays"]
    trace_times = source["trace_time_seconds"]
    if (times.dtype != np.float64 or times.ndim != 1 or not 1 <= len(times) <= 100001 or not np.isfinite(times).all()
            or times[0] != trace_times[0] or times[-1] != trace_times[-1] or np.any(np.diff(times) <= 0.)):
        raise ValueError("sample times require actual first/last committed times")
    if len(times) * (len(source["network_receiver"]) + len(product["metadata"]["lakes"]) + 1) * 128 > MAX_BYTES:
        raise ValueError("coupled sampling allocation budget exceeded")
    arrays = {"time_seconds": times.copy()}
    for key in ("channel_volume_m3", "lake_volume_m3"):
        volume = source["trace_" + key]
        arrays[key] = np.column_stack([np.interp(times, trace_times, volume[:, i]) for i in range(volume.shape[1])]) if volume.shape[1] else np.empty((len(times), 0))
    for key in ("channel_boundary_volume_m3", "lake_external_volume_m3"):
        cumulative = np.r_[0., np.cumsum(source["trace_" + key].sum(axis=1))]
        arrays["cumulative_" + key] = np.interp(times, trace_times, cumulative)
    metadata = {"schema": "terragenesis-coupled-output-v1", "source_identity_sha256": product["identity_sha256"],
                "state_semantics": "linear_interpolation_of_committed_volumes", "boundary_semantics": "complete_overlap_integral"}
    arrays = {key: readonly(value) for key, value in arrays.items()}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
