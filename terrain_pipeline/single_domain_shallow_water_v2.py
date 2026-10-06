"""MUSCL shallow-water model bound to common conservative execution."""

from terrain_pipeline.single_domain_shallow_water_execution import advance_shallow_water as _advance
from terrain_pipeline.single_domain_shallow_water_support_v2 import MODEL, shallow_water_rhs


def advance_shallow_water(geometry, **kwargs):
    return _advance(geometry, rhs=shallow_water_rhs, model=MODEL,
        scope="independent FV MUSCL HLL with in-cell bed source and SSPRK2; uncalibrated",
        physical_limitation="limited MUSCL face reconstruction; coarse cell-mean bed; no calibrated natural certification",
        **kwargs)
