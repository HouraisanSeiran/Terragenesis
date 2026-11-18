"""Sequential quasi-steady normal-flow / finite-inventory morphodynamics.

Each prescribed interval runs once; transient and backwater flow are not solved.
"""
from __future__ import annotations

from copy import deepcopy
import math
import numpy as np

from terrain_pipeline.common_infra import identity
from .metric_sediment import MaterialParameters
from .metric_upstream_sediment import route_daily_sediment, validate_daily_sediment


def normal_depth(q, width, slope, roughness=.035):
    if not all(math.isfinite(v) for v in (q, width, slope, roughness)) or q < 0. or width <= 0. or roughness <= 0.:
        raise ValueError("finite discharge and positive finite width/roughness required")
    if q == 0.:
        return 0.
    if q < 0. or width <= 0. or slope <= 0. or roughness <= 0.:
        raise ValueError("positive-flow normal depth requires positive slope, width and roughness")
    lo, hi = 0., 1.
    def discharge(h):
        area = width * h
        return area * (area / (width + 2. * h)) ** (2. / 3.) * math.sqrt(slope) / roughness
    while discharge(hi) < q:
        hi *= 2.
        if hi > 10000.:
            raise ValueError("normal depth outside bounded physical range")
    for _ in range(60):
        middle = (lo + hi) * .5
        if discharge(middle) < q:
            lo = middle
        else:
            hi = middle
    return (lo + hi) * .5


def bed_slopes(receiver, bed, node_xz_m, terminal_slope=None):
    """Edge gradients use node distance, never control-volume lengths."""
    xz = np.asarray(node_xz_m, dtype=np.float64)
    if xz.shape != (bed.size, 2) or not np.isfinite(xz).all():
        raise ValueError("finite [node,2] coordinates required")
    slopes = np.zeros(bed.size)
    for i, target in enumerate(receiver):
        if target >= 0:
            distance = float(np.linalg.norm(xz[i] - xz[target]))
            if distance <= 0.:
                raise ValueError("receiver edge distance must be positive")
            slopes[i] = (bed[i] - bed[target]) / distance
            if slopes[i] <= 0.:
                raise ValueError(f"reversed or flat bed slope at node {i}; normal-flow closure rejected")
    for i in np.flatnonzero(receiver == -1):
        donors = np.flatnonzero(receiver == i)
        if donors.size:
            slopes[i] = float(np.mean(slopes[donors]))
        elif terminal_slope is not None and math.isfinite(terminal_slope) and terminal_slope > 0.:
            slopes[i] = terminal_slope
        else:
            raise ValueError("isolated terminal requires explicit positive outlet slope")
    return slopes


def route_feedback_daily(bundle, node_xz_m, *, roughness=.035, terminal_slope=None):
    """Recompute hydraulics per interval and carry all stores from the last one."""
    validate_daily_sediment(bundle)
    if not math.isfinite(roughness) or roughness <= 0.:
        raise ValueError("positive finite Manning roughness required")
    a, source = bundle["arrays"], bundle["metadata"]
    material = MaterialParameters(**source["material"])
    porosity = material.porosity
    current = a["bed_elevation_m"].copy()
    loose = a["initial_alluvium_bulk_m3"] * (1. - porosity)
    mobile = a["initial_mobile_solid_m3"].copy()
    cumulative_rock = np.zeros_like(current)
    runs = []
    for j in range(a["water_q_m3_s"].shape[0]):
        slope = bed_slopes(a["receiver"], current, node_xz_m, terminal_slope)
        depth = np.array([normal_depth(q, w, s, roughness)
                          for q, w, s in zip(a["water_q_m3_s"][j], a["width_m"], slope)])
        hydraulic_id = identity({"q": a["water_q_m3_s"][j:j+1], "depth": depth, "slope": slope},
                                {"algorithm": "rectangular-Manning-normal-flow-v1", "roughness": roughness})
        run = route_daily_sediment(
            receiver=a["receiver"], length_m=a["length_m"], width_m=a["width_m"],
            bed_elevation_m=current, water_depth_m=depth[None, :],
            water_q_m3_s=a["water_q_m3_s"][j:j+1], friction_slope=slope[None, :],
            time_seconds=a["time_seconds"][j:j+2], rock_floor_m=a["rock_floor_m"],
            initial_alluvium_bulk_m3=loose / (1. - porosity), initial_mobile_solid_m3=mobile,
            hardness=a["hardness_source"], material=material,
            external_solid_m3_s=a["external_solid_m3_s"][j:j+1],
            retention_fraction=a["retention_fraction"],
            geometry_identity_sha256=source["geometry_identity_sha256"],
            hydraulic_identity_sha256=hydraulic_id, material_provenance=source["material_provenance"])
        r = run["arrays"]
        current = r["trace_bed_m"][-1].copy()
        loose = r["trace_loose_solid_m3"][-1].copy()
        mobile = r["trace_mobile_solid_m3"][-1].copy()
        r["trace_rock_removed_m3"] += cumulative_rock
        cumulative_rock = r["trace_rock_removed_m3"][-1].copy()
        runs.append(run)
    arrays = {name: value.copy() for name, value in a.items()}
    for name, value in runs[0]["arrays"].items():
        if value.ndim == 2:
            if name.startswith("trace_"):
                arrays[name] = np.concatenate([runs[0]["arrays"][name][:1]] +
                                               [run["arrays"][name][1:] for run in runs])
            else:
                arrays[name] = np.concatenate([run["arrays"][name] for run in runs])
    arrays["node_xz_m"] = np.asarray(node_xz_m, dtype=np.float64).copy()
    metadata = deepcopy(source)
    metadata.update({"algorithm": "sequential-daily-normal-flow-finite-sediment-v1",
                     "frozen_water": False, "hydraulic_recomputed": True,
                     "hydraulic_ready": False, "publishable": False,
                     "needs_revalidation": True, "manning_roughness": roughness,
                     "feedback_intervals": len(runs), "terminal_slope": terminal_slope,
                     "source_bundle_identity_sha256": bundle["identity_sha256"],
                     "hydraulic_semantics": "daily quasi-steady rectangular Manning normal depth; no transient, backwater or downstream-stage feedback",
                     "terminal_gradient_semantics": "mean current incoming geometric gradients, or explicit isolated outlet slope"})
    metadata["geometry_identity_sha256"] = identity(
        {key: arrays[key] for key in ("node_xz_m", "receiver", "length_m", "width_m", "bed_elevation_m")},
        {"source_geometry": source["geometry_identity_sha256"]})
    metadata["hydraulic_identity_sha256"] = identity(
        {key: arrays[key] for key in ("time_seconds", "water_q_m3_s", "water_depth_m", "friction_slope")},
        {"closure": "daily-Manning", "roughness": roughness})
    initial = float((a["initial_alluvium_bulk_m3"] * (1. - porosity)).sum() + a["initial_mobile_solid_m3"].sum())
    metadata["global_residual"] = float(initial + arrays["external_solid_m3"].sum() + arrays["eroded_rock_m3"].sum()
                                        - loose.sum() - mobile.sum() - arrays["exported_solid_m3"].sum())
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_daily_sediment(result)
    return result


def recouple_daily_bundle(bundle, bed_delta_m=None, *, node_xz_m, roughness=.035):
    """Compatibility wrapper; external edits require a new material source bundle."""
    if bed_delta_m is not None and np.any(np.asarray(bed_delta_m) != 0.):
        raise ValueError("external bed edits require explicit material inventory reconstruction")
    return {"frozen": bundle, "feedback": route_feedback_daily(bundle, node_xz_m, roughness=roughness)}


def deposit_landward_plain(initial_bed_m, land_mask, deposited_solid_m3, *, cell_area_m2, porosity=.35):
    """Area-aware inventory helper; deposition alone does not identify wetland."""
    bed = np.asarray(initial_bed_m, float)
    land = np.asarray(land_mask, bool)
    dep = np.asarray(deposited_solid_m3, float)
    if bed.shape != land.shape or dep.shape != bed.shape or not np.isfinite(bed).all():
        raise ValueError("finite matching plain shapes required")
    if not 0. <= porosity < 1. or np.any(dep < 0.) or not np.isfinite(dep).all() or not math.isfinite(cell_area_m2) or cell_area_m2 <= 0.:
        raise ValueError("invalid deposition, porosity or cell area")
    accepted = np.where(land, dep, 0.)
    return {"initial_bed_m": bed.copy(), "final_bed_m": bed + accepted / ((1. - porosity) * cell_area_m2),
            "deposited_solid_m3": accepted, "land_mask": land.copy(),
            "deposited_land_area_m2": int(np.count_nonzero(accepted)) * cell_area_m2, "island_forced": False}
