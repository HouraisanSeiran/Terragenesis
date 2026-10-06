"""Bind independent coarse subgrid storage and advective HLL evolution."""

from functools import partial

import numpy as np

from terrain_pipeline.single_domain_fine_geometry import storage_stages
from terrain_pipeline.single_domain_shallow_water_execution import advance_shallow_water as _advance
from terrain_pipeline.single_domain_shallow_water_support_v4 import MODEL, shallow_water_rhs


def advance_shallow_water(geometry, **kwargs):
    arrays = geometry["arrays"]
    support = {name: arrays[name] for name in ("subcell_bed_relative_m", "subcell_prefix_relative_m",
        "face_segment_crest_relative_m", "boundary_segment_crest_relative_m")}

    def wave_speed(state, gravity):
        stage = storage_stages(state[:, 0], support["subcell_bed_relative_m"], support["subcell_prefix_relative_m"])
        maximum_depth = np.maximum(stage-support["subcell_bed_relative_m"][:, 0], 0.)
        velocity = np.divide(state[:, 1:], state[:, 0, None], out=np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
        return float(1.5*abs(velocity).sum(axis=1).max(initial=0)+2*np.sqrt(gravity*max(float(stage.max()-support["subcell_bed_relative_m"].min()),0)))

    return _advance(geometry, rhs=partial(shallow_water_rhs, support=support), model=MODEL,
        hydraulic_datum_m=geometry["metadata"]["hydraulic_datum_m"], wave_speed=wave_speed,
        stage_provider=lambda depth: storage_stages(depth, support["subcell_bed_relative_m"], support["subcell_prefix_relative_m"]),
        face_evaluation_multiplier=support["face_segment_crest_relative_m"].shape[1],
        scope="independent FV canonical subgrid storage and MUSCL segmented advective HLL; SSPRK2; uncalibrated",
        physical_limitation="one velocity vector per coarse cell; segmented pressure support; no calibrated natural certification",
        **kwargs)


