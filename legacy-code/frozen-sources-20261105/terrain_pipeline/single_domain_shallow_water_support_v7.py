"""Canonical wet-subcell Manning integral for independent subgrid HLL."""

import numpy as np

from terrain_pipeline.single_domain_fine_geometry import storage_stages
from terrain_pipeline.single_domain_shallow_water_support_v3 import shallow_water_rhs

MODEL = "single-domain-subgrid-storage-segmented-HLL-canonical-Manning-SSPRK2-v7"


def manning_damping(state, dt, gravity, roughness, *, support):
    stage = storage_stages(state[:, 0], support["subcell_bed_relative_m"], support["subcell_prefix_relative_m"])
    depth = np.maximum(stage[:, None]-support["subcell_bed_relative_m"], 0.)
    inverse = np.zeros_like(depth)
    np.power(depth, -1/3, out=inverse, where=depth > 0)
    factor = inverse.mean(axis=1)
    depth_squared = state[:, 0]**2
    magnitude = np.hypot(state[:, 1], state[:, 2])
    denominator = depth_squared+dt*gravity*roughness**2*magnitude*factor
    damping = np.divide(depth_squared, denominator, out=np.zeros_like(depth_squared), where=denominator > 0)
    return damping, factor
