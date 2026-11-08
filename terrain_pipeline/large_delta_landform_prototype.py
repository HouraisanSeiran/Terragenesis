"""Bounded finite-sediment redistribution experiment; not a delta generator."""
import numpy as np

from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import conservative_diffusion_step


def redistribute(bed_m, allowed, source_cell, solid_m3, spacing_m, *, porosity=0.35, steps=40):
    """Place declared solid at one cell then redistribute mobile cover on the real bed.

    Steps are numerical morphological iterations, without a physical duration.
    Walls and the first row are fixed by the existing diffusion kernel.
    """
    bed = np.asarray(bed_m, dtype=np.float64)
    mask = np.asarray(allowed, dtype=bool)
    if (bed.ndim != 2 or bed.shape != mask.shape or not np.isfinite(bed).all()
            or not np.isfinite([solid_m3, spacing_m, porosity]).all()
            or solid_m3 < 0 or spacing_m <= 0 or not 0 <= porosity < 1
            or not isinstance(steps, int) or not 0 <= steps <= 1000
            or not mask[source_cell] or source_cell[0] == 0):
        raise ValueError("invalid bounded redistribution inputs")
    result = bed.copy()
    result[source_cell] += solid_m3 / ((1 - porosity) * spacing_m**2)
    kinds = np.where(mask, 0, -2)
    for _ in range(steps):
        result = conservative_diffusion_step(result, np.ones_like(bed), kinds, bed, 0.035, spacing_m)
    return result
