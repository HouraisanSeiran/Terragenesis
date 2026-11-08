"""Current fault fixtures, independent of archived-v1 contract tests."""

import numpy as np

from terrain_pipeline.vdm_cuts import CliffRecipe, build_vdm
from terrain_pipeline.vdm_cuts import FaultRecipe


def chart(angle_degrees=0.0):
    row, col = np.indices((25, 25))
    x = col.astype(float) - 12.0
    z = row.astype(float) - 12.0
    angle = np.deg2rad(angle_degrees)
    reference = np.zeros((25, 25, 3), dtype=float)
    reference[:, :, 0] = x * np.cos(angle) - z * np.sin(angle)
    reference[:, :, 2] = x * np.sin(angle) + z * np.cos(angle)
    reference[:, :, 1] = 30.0 + 0.04 * x + 0.02 * z
    return reference


def source(angle_degrees=0.0, protected=None):
    reference = chart(angle_degrees)
    if protected is None:
        protected = np.zeros(reference.shape[:2], dtype=bool)
    config = CliffRecipe(
        center_xz_m=(0.0, 0.0), outward_xz=(1.0, 0.0), height_m=6.0,
        half_length_m=7.0, half_depth_m=8.0, wall_half_width_m=3.0,
        end_fade_m=2.0, angle_degrees=75.0, lean=1,
    )
    return build_vdm(reference, recipe=config, protected_mask=protected,
                     source_identity="source-vdm-test", protection_identity="protection-test")


def selection():
    mask = np.zeros((25, 25), dtype=bool)
    mask[5:20, 5:20] = True
    return mask


def recipe(slip=2.0, strike=0.0, moving_side="positive", transition=3.0):
    return FaultRecipe(
        plane_origin_xz_m=(0.0, 0.0), strike_degrees=strike, slip_m=slip,
        moving_side=moving_side, transition_width_m=transition,
    )
