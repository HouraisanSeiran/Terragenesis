"""Level-pool lake storage and sill overflow wired onto a finite world reach.

No lake hydrology is introduced here. Two existing modules do the physics:

* `metric_lake_storage.LakeStorage` supplies the finite V(h) curve and its inverse
  (`volume_at_stage` / `stage_at_volume`) together with wetted area and depth;
* `metric_lake_storage.LakeOutlet` supplies the reduced broad-crested sill rating
  `Q = C * (stage - crest) ** 1.5`, so several saddles are just several outlets.

What this module adds is only the wiring the repository did not have for a coarse
world reach: the level-pool march itself (explicit, sub-step of the existing
Manning solver), the derivation of the sill/support from the raw D8 tile, and an
exactly closing water ledger. Every cubic metre entering the lake comes from the
reach's own terminal open-outflow volume saved by the existing aqueous solver;
nothing is re-injected as a new boundary source.

`metric_lake_channel_coupling.solve_lake_channel` (the signed two-way weir port) is
deliberately not used for this reach; the concrete interface blockers are recorded
in `.scratch/cross-region-tributary/full-reach-handoff.md`. In short: it caps the
channel at 32 nodes, it requires the channel terminal to sit on the *D4 outer
neighbour* of a lake support cell (in a raw D8 world the inland minimum is the
terminal cell itself), and it replaces the existing channel solver instead of
consuming its saved trace, so it cannot carry this reach's sediment coupling.
"""
from dataclasses import dataclass
import math

import numpy as np

from terrain_pipeline.surface_rivers.metric_lake_storage import LakeOutlet, LakeStorage

# Repository conventions reused rather than invented (see the report for citations):
# * design discharge from contributing area: metric_network_geometry._catalogue
#   (`design_q = area * design_runoff_mm_h / 1000 / 3600`, default 1 mm/h);
# * width power law: metric_channel_plan.ChannelRecipe (W = W_ref*(Q/Q_ref)**b,
#   b = .5, exponents from Leopold & Maddock 1953, USGS PP 252).
DESIGN_RUNOFF_MM_H = 1.
WIDTH_EXPONENT = .5
GRAVITY_M_S2 = 9.80665


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(name + " must be numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0.:
        raise ValueError(name + " must be finite positive")
    return value


def design_discharge_m3_s(contributing_area_m2, *, design_runoff_mm_h=DESIGN_RUNOFF_MM_H):
    """Node design discharge from contributing area (repository runoff convention)."""
    area = np.asarray(contributing_area_m2, np.float64)
    if area.ndim != 1 or not np.isfinite(area).all() or np.any(area <= 0.):
        raise ValueError("finite positive contributing area per node required")
    runoff = _positive(design_runoff_mm_h, "design_runoff_mm_h")
    return area * runoff / 1000. / 3600.


def channel_width_m(contributing_area_m2, *, reference_discharge_m3_s, reference_width_m,
                    min_width_m, max_width_m, design_runoff_mm_h=DESIGN_RUNOFF_MM_H,
                    width_exponent=WIDTH_EXPONENT):
    """`ChannelRecipe` width law applied per node: W = clip(W_ref*(Q/Q_ref)**b).

    Returns (width_m, design_q_m3_s). Areas are the contributing *cell* footprints
    of the selected reach, so width increases monotonically with catchment size.

    This is the flow-only law. `channel_width_from_lithology_m` is the one the
    reach builder uses now: the project's own stated rule is that width comes from
    discharge **and** rock hardness together, developed from erosion, so a
    flow-only width drops half of the original specification.
    """
    q = design_discharge_m3_s(contributing_area_m2, design_runoff_mm_h=design_runoff_mm_h)
    reference_q = _positive(reference_discharge_m3_s, "reference_discharge_m3_s")
    reference_w = _positive(reference_width_m, "reference_width_m")
    low = _positive(min_width_m, "min_width_m")
    high = _positive(max_width_m, "max_width_m")
    if high < low:
        raise ValueError("maximum width must exceed minimum width")
    exponent = float(width_exponent)
    if not math.isfinite(exponent) or exponent < 0.:
        raise ValueError("nonnegative finite width exponent required")
    ratio = q / reference_q
    return np.clip(reference_w * ratio ** exponent, low, high), q


def channel_width_from_lithology_m(contributing_area_m2, bed_hardness, bank_hardness, *,
                                   reference_discharge_m3_s, reference_width_m,
                                   min_width_m, max_width_m,
                                   design_runoff_mm_h=DESIGN_RUNOFF_MM_H,
                                   width_exponent=WIDTH_EXPONENT,
                                   bed_lateral_factor=1.5, bank_lateral_factor=1.5):
    """Width from discharge **and** rock hardness, reusing the repository erosion rule.

    The law is the one already implemented in
    `metric_discharge_geometry.build_discharge_geometry`, copied here rather than
    re-derived so the reach and the older geometry path cannot disagree:

        W = W_ref * (Q/Q_ref)**b * (1 + a_bed * h_bed) * (0.5 + a_bank * (1 - h_bank))

    with `a_bed = a_bank = 1.5`. Its stated intent is that a hard bed directs work
    sideways (wider), while a resistant bank resists widening. Values are the
    geology table's `bed_hardness` / `bank_hardness` in [0, 1], sampled at the
    node's absolute world coordinate, so a granite reach and a shale reach with the
    same discharge are not forced to the same width.

    `min_width_m` / `max_width_m` still clamp, because the 30 m base cannot carry a
    sub-cell channel; the clamp is reported by the caller, not hidden here.
    """
    q = design_discharge_m3_s(contributing_area_m2, design_runoff_mm_h=design_runoff_mm_h)
    reference_q = _positive(reference_discharge_m3_s, "reference_discharge_m3_s")
    reference_w = _positive(reference_width_m, "reference_width_m")
    low = _positive(min_width_m, "min_width_m")
    high = _positive(max_width_m, "max_width_m")
    if high < low:
        raise ValueError("maximum width must exceed minimum width")
    exponent = float(width_exponent)
    if not math.isfinite(exponent) or exponent < 0.:
        raise ValueError("nonnegative finite width exponent required")
    bed = np.asarray(bed_hardness, np.float64)
    bank = np.asarray(bank_hardness, np.float64)
    if bed.shape != q.shape or bank.shape != q.shape:
        raise ValueError("one hardness pair per node required")
    if not (np.isfinite(bed).all() and np.isfinite(bank).all()):
        raise ValueError("finite hardness required")
    if np.any(bed < 0.) or np.any(bed > 1.) or np.any(bank < 0.) or np.any(bank > 1.):
        raise ValueError("hardness must lie in [0, 1]")
    lateral = (1. + float(bed_lateral_factor) * bed) * (
        .5 + float(bank_lateral_factor) * (1. - bank))
    raw = reference_w * (q / reference_q) ** exponent * lateral
    return np.clip(raw, low, high), q


def sill_coefficient_m3_s_m15(sill_width_m, *, discharge_coefficient=.4):
    """Broad-crested weir `Q = Cd*sqrt(2g)*L*h**1.5` lumped into one `LakeOutlet` C.

        `LakeOutlet` documents its coefficient as `m3 s-1 m-1.5`; multiplying the
    per-metre weir law by the sill length keeps that unit and makes the number
    auditable instead of tuned.
    """
    width = _positive(sill_width_m, "sill_width_m")
    cd = _positive(discharge_coefficient, "discharge_coefficient")
    return cd * math.sqrt(2. * GRAVITY_M_S2) * width


@dataclass(frozen=True)
class SillLake:
    storage: LakeStorage
    outlets: tuple
    seed_cell_id: int
    sill_stage_m: float
    secondary_sill: dict | None
    provenance: dict

    @property
    def bed_elevation_m(self):
        return float(self.storage.bed_elevation_m[0])

    @property
    def sill_depth_m(self):
        return self.sill_stage_m - self.bed_elevation_m

    def volume_at_sill_m3(self):
        return self.storage.volume_at_stage(self.sill_stage_m)

    def capacity_m3(self):
        return self.storage.capacity_m3


def build_sill_lake(*, cell_ids, bed_elevation_m, cell_area_m2, seed_cell_id, sill_stage_m,
                    head_allowance_m, sill_width_m, source_identity_sha256, primary_target_xz_m,
                    secondary_sill=None, discharge_coefficient=.4, provenance):
    """Build the level-pool store and its saddle ratings from declared inputs.

    `secondary_sill` is an optional dict with `stage_m`, `width_m`, `target_xz_m` for
    a second, higher saddle; it is represented as a second `LakeOutlet` and reports
    zero outflow whenever the stage stays below its crest.
    """
    ids = np.asarray(cell_ids, np.int64)
    bed = np.asarray(bed_elevation_m, np.float64)
    area = np.asarray(cell_area_m2, np.float64)
    if ids.shape != bed.shape or ids.shape != area.shape:
        raise ValueError("lake support arrays must share one shape")
    allowance = _positive(head_allowance_m, "head_allowance_m")
    sill = float(sill_stage_m)
    if not math.isfinite(sill):
        raise ValueError("finite sill stage required")
    coefficient = sill_coefficient_m3_s_m15(sill_width_m, discharge_coefficient=discharge_coefficient)
    storage = LakeStorage(
        cell_ids=ids, bed_elevation_m=bed, cell_area_m2=area, seed_cell_id=int(seed_cell_id),
        max_stage_m=sill + allowance, source_identity_sha256=source_identity_sha256,
        footprint_policy=("single_coarse_cell_level_pool_tank_at_native_tile_spacing;"
                          "stage above the saddle is the declared weir head, not an expanded wetted footprint"))
    if storage.volume_at_stage(storage.min_stage_m) != 0.:
        raise ValueError("sill lake must start from a dry support")
    outlets = [LakeOutlet(0, -1, sill, coefficient,
                          "broad-crested sill: Cd=%.3f, sqrt(2g), sill width %.1f m; "
                          "spills out of the modelled reach to %s" % (discharge_coefficient,
                                                                     float(sill_width_m),
                                                                     list(primary_target_xz_m)))]
    secondary = None
    if secondary_sill is not None:
        crest = float(secondary_sill["stage_m"])
        width = _positive(secondary_sill["width_m"], "secondary sill width_m")
        outlets.append(LakeOutlet(0, -1, crest, sill_coefficient_m3_s_m15(width, discharge_coefficient=discharge_coefficient),
                                  "declared secondary saddle %s, higher than the primary sill" %
                                  (list(secondary_sill["target_xz_m"]),)))
        secondary = dict(stage_m=crest, width_m=width, target_xz_m=list(secondary_sill["target_xz_m"]),
                         coefficient_m3_s_m15=outlets[-1].coefficient_m3_s_m15)
    return SillLake(storage=storage, outlets=tuple(outlets), seed_cell_id=int(seed_cell_id),
                    sill_stage_m=sill, secondary_sill=secondary,
                    provenance=dict(provenance, discharge_coefficient=float(discharge_coefficient),
                                    head_allowance_m=allowance,
                                    primary_sill_width_m=float(sill_width_m),
                                    primary_target_xz_m=list(primary_target_xz_m)))


def integrate_sill_lake(lake, inflow_volume_m3, dt_seconds, *, initial_volume_m3):
    """March the level-pool lake with an explicit storage/spill split.

    `inflow_volume_m3[k]` is the volume the existing aqueous solver moved out of the
    reach terminal during step `k`; it is never rescaled. Spill is the sum of the
    existing `LakeOutlet` ratings at the resolved stage, capped by the volume that is
    actually there, so no step can spill water it does not hold. The ledger closes to
    floating-point round-off by construction.
    """
    inflow = np.asarray(inflow_volume_m3, np.float64)
    dt = np.asarray(dt_seconds, np.float64)
    if inflow.ndim != 1 or dt.ndim != 1 or inflow.shape != dt.shape or inflow.size == 0:
        raise ValueError("matching nonempty inflow and dt series required")
    if not np.isfinite(inflow).all() or not np.isfinite(dt).all() or np.any(inflow < 0.) or np.any(dt <= 0.):
        raise ValueError("finite nonnegative inflow and positive dt required")
    capacity = lake.storage.capacity_m3
    volume = float(initial_volume_m3)
    if not math.isfinite(volume) or volume < 0. or volume > capacity:
        raise ValueError("initial lake volume outside declared finite support")
    stages = np.empty(inflow.size + 1)
    volumes = np.empty(inflow.size + 1)
    areas = np.empty(inflow.size + 1)
    spills = np.empty((inflow.size, len(lake.outlets)))
    stages[0] = lake.storage.stage_at_volume(volume)
    volumes[0] = volume
    areas[0] = lake.storage.surface_area_at_stage(stages[0])
    for step in range(inflow.size):
        volume += float(inflow[step])
        if volume > capacity + 1e-6:
            raise ValueError("lake exceeds declared finite support: raise the declared weir head allowance")
        stage = lake.storage.stage_at_volume(min(volume, capacity))
        rate = np.array([outlet.discharge_at_stage(stage) for outlet in lake.outlets], np.float64)
        spilled = rate * dt[step]
        total = float(spilled.sum())
        if total > volume:
            spilled = spilled * (volume / total) if total > 0. else np.zeros_like(spilled)
            total = volume
        volume -= total
        spills[step] = spilled
        stages[step + 1] = lake.storage.stage_at_volume(volume)
        volumes[step + 1] = volume
        areas[step + 1] = lake.storage.surface_area_at_stage(stages[step + 1])
    total_spill = float(spills.sum())
    ledger = dict(initial_m3=float(initial_volume_m3), inflow_m3=float(inflow.sum()),
                  spill_m3=total_spill, final_m3=float(volumes[-1]),
                  residual_m3=float(initial_volume_m3 + inflow.sum() - total_spill - volumes[-1]))
    return dict(time_edges_seconds=np.concatenate(([0.], np.cumsum(dt))),
                stage_m=stages, volume_m3=volumes, surface_area_m2=areas,
                inflow_volume_m3=inflow, spill_volume_m3=spills,
                outlet_spill_m3=spills.sum(axis=0), dt_seconds=dt, ledger=ledger)
