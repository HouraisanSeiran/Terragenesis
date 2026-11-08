from dataclasses import replace

import numpy as np
import pytest

from terrain_pipeline.coastal_delta_branch_attachment import attach_multicell_branch
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from test_coastal_delta_branch_attachment import candidate
from test_coastal_delta_multicell import fixture


def test_intermediate_cut_consumes_only_local_outer_bed():
    state, progress = fixture()
    fork, path, xy = candidate(state, progress)
    cell = tuple(path[-2])
    bed = state.bed_solid_m3.copy()
    area = state.spacing_m**2*(1-state.porosity[cell])
    bed[cell] = 1.0*area
    modified = replace(state, bed_solid_m3=bed)
    out, p, report = attach_multicell_branch(modified, progress, parent_index=0, fork_index=fork,
        path_zx=path, path_xz_m=xy, hydraulic_config=HydraulicConfig(12.))
    assert report['attached'], report
    removed = modified.bed_solid_m3[cell]-out.bed_solid_m3[cell]
    assert removed == pytest.approx(.5*area)
    assert out.mobile_solid_m3[cell]-modified.mobile_solid_m3[cell] == pytest.approx(removed)
    assert np.array_equal(out.base_bed_m, modified.base_bed_m)
    assert p['node_footprints'][:len(progress['node_footprints'])] == progress['node_footprints']


def test_excess_cut_rolls_back_everything():
    state, progress = fixture()
    fork, path, xy = candidate(state, progress)
    cell = tuple(path[-2])
    bed = state.bed_solid_m3.copy()
    area = state.spacing_m**2*(1-state.porosity[cell])
    bed[cell] = (20.-state.base_bed_m[cell])*area
    modified = replace(state, bed_solid_m3=bed)
    out, p, report = attach_multicell_branch(modified, progress, parent_index=0, fork_index=fork,
        path_zx=path, path_xz_m=xy, hydraulic_config=HydraulicConfig(12.))
    assert not report['attached']
    assert out is modified and p is progress
