import numpy as np
from terrain_pipeline.large_delta_tidal_dynamics import Geometry, State, step
from terrain_pipeline.large_delta_tidal_product_v4 import volume_stage


def test_subgrid_volume_stage_respects_rugged_bed():
    beds=np.array([[0.,1.,4.]])
    area=np.array([[10.,10.,10.]])
    stage,wet=volume_stage(beds,area,np.array([20.]),np.array([0.]))
    assert np.isclose(stage[0],1.5)
    assert wet[0]==20.
    assert np.isclose(np.sum(np.maximum(stage[0]-beds,0)*area),20.)


def test_accounted_bar_changes_next_flow():
    g=Geometry(np.array([100.,100.,100.]),np.array([0.,0.,0.]),
               np.array([0,1]),np.array([1,2]),np.array([1.,1.]),
               np.array([],int),np.array([]))
    # The displaced bed solid comes from the upstream node, so initial total
    # bed inventory is unchanged; only its distribution changes.
    original=State(0.,np.array([200.,100.,0.]),np.array([60.,0.,0.]),np.zeros(3))
    bar=State(0.,np.array([200.,100.,0.]),np.array([0.,60.,0.]),np.zeros(3))
    a=step(g,original,1.,0.,0,0.,0.)
    b=step(g,bar,1.,0.,0,0.,0.)
    assert original.bed_solid_m3.sum()+original.mobile_solid_m3.sum() == bar.bed_solid_m3.sum()+bar.mobile_solid_m3.sum()
    assert not np.allclose(a['internal_water_m3'],b['internal_water_m3'])
    assert b['internal_water_m3'][0] < a['internal_water_m3'][0]


def test_source_branch_footprints_match_saved_width_and_length():
    from pathlib import Path
    from terrain_pipeline.large_delta_tidal_source import load_source
    from terrain_pipeline.large_delta_tidal_product_v4 import prepare
    path=Path('.scratch/delta-tides-bars-20261102/source-v1/source-manifest.json')
    if not path.exists():
        import pytest
        pytest.skip('source fixture is not present')
    source=load_source(path)
    p=prepare(source)
    area=p['geometry'].area_m2
    for branch,nodes in enumerate(p['branch_nodes']):
        actual=area[p['ncoast']+np.asarray(nodes)].sum()
        expected=source['network']['branch_width_m'][branch]*source['network']['branch_length_m'][branch]
        assert np.isclose(actual,expected,rtol=1e-12)
    np.testing.assert_allclose(p['coast_area']+p['channel_area'],900*source['valid'][p['bounds'][0]:p['bounds'][1],p['bounds'][2]:p['bounds'][3]])
