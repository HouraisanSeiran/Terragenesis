"""Bounded generation geometry from monthly discharge; no physical erosion clock."""

from dataclasses import asdict, dataclass
import math

import numpy as np
from scipy.ndimage import distance_transform_edt

from terrain_pipeline.runoff import MONTH_SECONDS as MONTH_SECONDS


ALGORITHM = "monthly_discharge_material_trapezoid_v2"


@dataclass(frozen=True)
class DischargeGeometryConfig:
    generation_exposure: float = 3.
    width_at_unit_q_m: float = 4.
    depth_at_unit_q_m: float = .6
    width_q_exponent: float = .45
    depth_q_exponent: float = .3
    max_width_m: float = 120.
    max_incise_m: float = 4.
    bottom_width_fraction: float = .6

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)) or not math.isfinite(value):
                raise ValueError(name + " must be a finite number")
        if not 0. <= self.generation_exposure <= 100.:
            raise ValueError("generation_exposure must be dimensionless in [0, 100]")
        for name in ("width_at_unit_q_m", "depth_at_unit_q_m", "max_width_m"):
            if not 0. < getattr(self, name) <= 10000.:
                raise ValueError(name + " must be in (0, 10000]")
        if not 0. < self.max_incise_m <= 4.:
            raise ValueError("max_incise_m must be in (0, 4] metres below source TD")
        if not 0. < self.bottom_width_fraction < 1.:
            raise ValueError("bottom_width_fraction must be in (0, 1)")
        if not 0. < self.width_q_exponent <= 1. or not 0. < self.depth_q_exponent <= 1.:
            raise ValueError("discharge exponents must be in (0, 1]")


def channel_section_cut(offset_m, width_m, depth_m, *, bottom_width_fraction=.6):
    """Return incision metres at signed lateral offsets in a parametric section.

    Width is the top incision width; depth is source-relative cutting, never a
    water depth. The flat bottom occupies bottom_width_fraction of top width.
    """
    offset, width, depth = np.broadcast_arrays(np.asarray(offset_m, np.float64),
                                              np.asarray(width_m, np.float64),
                                              np.asarray(depth_m, np.float64))
    if (not np.isfinite(offset).all() or not np.isfinite(width).all()
            or not np.isfinite(depth).all() or np.any(width < 0.) or np.any(depth < 0.)
            or not np.isfinite(bottom_width_fraction) or not 0. < bottom_width_fraction < 1.):
        raise ValueError("finite offsets, nonnegative dimensions and bottom fraction required")
    bank_run = width * (1. - bottom_width_fraction) / 2.
    weight = np.zeros_like(offset)
    np.divide(width / 2. - np.abs(offset), bank_run, out=weight, where=bank_run > 0.)
    return depth * np.clip(weight, 0., 1.)


def _hardness(value, shape, name):
    array = np.asarray(value, np.float64)
    if array.ndim == 0:
        array = np.full(shape, float(array))
    if array.shape != shape or not np.isfinite(array).all() or np.any(array < 0.) or np.any(array > 1.):
        raise ValueError(name + " must be scalar or matching field in [0, 1]")
    return array


def build_discharge_geometry(source_elevation_m, discharge_q_m3_s, channel_mask,
                             spacing_m, *, bed_hardness=.5, bank_hardness=.5,
                             protected_mask=None, config=None):
    """Derive a separate geometry field while preserving the caller's TD/DAG.

    Discharge may be an already averaged 2D Q field or 12 monthly Q fields.
    Raster cuts use the nearest active channel's section in its Voronoi region.
    This is a deterministic coarse heightfield projection, not a hydraulic or
    sediment simulation. Subgrid sections remain available as width/depth fields.
    """
    config = DischargeGeometryConfig() if config is None else config
    if not isinstance(config, DischargeGeometryConfig):
        raise ValueError("DischargeGeometryConfig required")
    source = np.asarray(source_elevation_m, np.float64)
    discharge = np.asarray(discharge_q_m3_s, np.float64)
    channel = np.asarray(channel_mask)
    if (source.ndim != 2 or not 1 <= source.size <= 4_000_000
            or discharge.shape not in (source.shape, (12, *source.shape)) or channel.shape != source.shape
            or channel.dtype.kind != "b" or not np.isfinite(source).all()
            or not np.isfinite(discharge).all() or np.any(discharge < 0.)):
        raise ValueError("finite bounded terrain, representative or 12 monthly Q fields and boolean channel mask required")
    if isinstance(spacing_m, (bool, np.bool_)) or not np.isfinite(spacing_m) or not 0. < spacing_m <= 10000.:
        raise ValueError("spacing_m must be in (0, 10000]")
    protected = np.zeros(source.shape, bool) if protected_mask is None else np.asarray(protected_mask)
    if protected.shape != source.shape or protected.dtype.kind != "b":
        raise ValueError("protected_mask must be a matching boolean field")
    bed = _hardness(bed_hardness, source.shape, "bed_hardness")
    bank = _hardness(bank_hardness, source.shape, "bank_hardness")
    q = (discharge.copy() if discharge.ndim == 2 else
         np.einsum("m,mij->ij", MONTH_SECONDS / MONTH_SECONDS.sum(), discharge))
    if not np.isfinite(q).all():
        raise ValueError("representative monthly discharge overflow")
    active = channel & (q > 0.)
    raster_cut_active = active & ~protected
    width = np.zeros(source.shape, np.float64)
    depth = np.zeros(source.shape, np.float64)
    exposure = -math.expm1(-config.generation_exposure)
    # Hard beds favour lateral work; resistant banks redirect work to incision.
    width[active] = np.minimum(config.max_width_m,
        config.width_at_unit_q_m * q[active] ** config.width_q_exponent
        * (1. + 1.5 * bed[active]) * (.5 + 1.5 * (1. - bank[active]))) * exposure
    depth[active] = np.minimum(config.max_incise_m,
        config.depth_at_unit_q_m * q[active] ** config.depth_q_exponent
        * (.4 + 1.2 * (1. - bed[active])) * (.8 + .4 * bank[active])) * exposure
    cut = np.zeros(source.shape, np.float64)
    if raster_cut_active.any() and exposure > 0.:
        distance, nearest = distance_transform_edt(~raster_cut_active, sampling=float(spacing_m),
                                                  return_indices=True)
        nearest_width = width[nearest[0], nearest[1]]
        nearest_depth = depth[nearest[0], nearest[1]]
        cut = channel_section_cut(distance, nearest_width, nearest_depth,
                                  bottom_width_fraction=config.bottom_width_fraction)
        cut[protected] = 0.
    removed = float(cut.sum(dtype=np.float64) * float(spacing_m) ** 2)
    if not math.isfinite(removed):
        raise ValueError("removed material volume overflow")
    arrays = dict(representative_q_m3_s=q, channel_width_m=width,
                  bottom_width_m=width * config.bottom_width_fraction,
                  channel_depth_m=depth, cut_depth_m=cut,
                  bed_elevation_m=source - cut, bed_hardness=bed.copy(),
                  bank_hardness=bank.copy(), channel_mask=channel.copy())
    metadata = dict(algorithm=ALGORITHM, config=asdict(config), spacing_m=float(spacing_m),
                    representative_discharge=("caller_supplied_mean_m3_s" if discharge.ndim == 2 else
                                              "calendar_duration_weighted_monthly_mean_m3_s"),
                    exposure_units="dimensionless_generation_budget_not_physical_years",
                    width_definition="top_source_relative_incision_width_m",
                    depth_definition="incision_below_immutable_TD_not_water_depth_m",
                    raster_projection="nearest_unprotected_active_channel_Voronoi_trapezoid",
                    protected_water_policy="retain_design_sections_exclude_cut_seeds_zero_raster_cut",
                    volume_measure="coarse_raster_edit_sum_cut_times_cell_area_not_subgrid_channel_volume",
                    subgrid_sections_resolved=False, hydraulic_solution=False,
                    material_budget=dict(coarse_raster_edit_bulk_m3=removed,
                                         removed_terrain_bulk_m3=removed,
                                         unplaced_excavated_bulk_m3=removed,
                                         redeposited_bulk_m3=0.,
                                         sediment_export_solved=False),
                    limitations=["parametric sections may be narrower than the source grid",
                                 "raster edit volume is not the unresolved parametric channel excavation volume",
                                 "nearest-channel projection does not resolve overlapping sections",
                                 "excavation retained as unplaced budget; sediment routing unsolved"])
    return dict(arrays=arrays, metadata=metadata)
