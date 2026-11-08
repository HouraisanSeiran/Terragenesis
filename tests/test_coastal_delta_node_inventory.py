from dataclasses import replace
from copy import deepcopy

import numpy as np
import pytest

from terrain_pipeline.coastal_delta_node_inventory import ChannelInventory
from terrain_pipeline.coastal_delta_product import load_checkpoint, save_checkpoint
from terrain_pipeline.coastal_marine_sediment import make_state


def example():
    state = make_state(base_bed_m=np.array([[-4., -3., -2.], [-2., -2., -2.]]),
                       bed_solid_m3=np.array([[100., 200., 60.], [0., 0., 0.]]),
                       mobile_solid_m3=np.array([[20., 30., 0.], [0., 0., 0.]]),
                       porosity=.4, valid_mask=True, ocean_seed_mask=np.zeros((2, 3), bool),
                       spacing_m=10., origin_xz_m=(0., 0.), source_identity='test')
    p = {'node_footprints': [[0, 0, [[0, 0, .3, 50., 5., 0.], [0, 1, .4, 30., 10., 0.]]],
                             [0, 2, [[0, 0, .2, 10., 4., 0.], [0, 2, .5, 20., 0., 0.]]]],
         'integrated': {'owner_cells': [[0, 0, .5, 60., 9., 0., -4., -4., 0.],
                                        [0, 1, .4, 30., 10., 0., -3., -3., 0.],
                                        [0, 2, .5, 20., 0., 0., -2., -2., 0.]]},
         'hydraulic_sections': {'nodes': [[0, 0, 0., 20., 10.], [0, 2, 0., 8., 5.]]}}
    return state, p


def test_multicell_take_add_and_shared_cell():
    state, p = example(); oldp = deepcopy(p)
    inv = ChannelInventory(state, p)
    assert inv.node_keys == ((0, 0), (0, 2))
    assert inv.area((0, 0)) == pytest.approx(70.)
    assert inv.amount((0, 0), 'bed_solid_m3') == 80.
    assert inv.take((0, 0), 'bed_solid_m3', 40.) == 40.
    assert inv.amount((0, 2), 'bed_solid_m3') == 30.
    inv.add((0, 0), 'mobile_solid_m3', 70.)
    out, pp = inv.commit(state, p)
    assert p == oldp and state.bed_solid_m3[0, 0] == 100.
    assert out.bed_solid_m3[0, 0] == pytest.approx(75.)
    assert out.bed_solid_m3[0, 1] == pytest.approx(185.)
    assert out.mobile_solid_m3.sum() == pytest.approx(state.mobile_solid_m3.sum()+70.)
    assert pp['integrated']['owner_cells'][0][3] == pytest.approx(35.)
    assert pp['hydraulic_sections']['nodes'][0][2] == pytest.approx(inv.section_bed((0, 0)))
    assert pp['hydraulic_sections']['nodes'][0][3:] == [20., 10.]
    assert inv.take((0, 0), 'bed_solid_m3', 1e6) == pytest.approx(40.)
    assert inv.amount((0, 0), 'bed_solid_m3') == 0.
    with pytest.raises(ValueError): inv.take((0, 0), 'bed_solid_m3', -1.)


def test_grid_changes_conserve_ownership_and_restart(tmp_path):
    state,p=example(); inv=ChannelInventory(state,p)
    inv.take((0,0),'bed_solid_m3',20.)
    with pytest.raises(ValueError, match='uncommitted'):
        inv.apply_grid_changes(state,state)
    before, bp=inv.commit(state,p)
    bed=before.bed_solid_m3.copy(); bed[0,0] -= 70.; bed[0,1] += 100.; bed[1,1] += 25.
    mobile=before.mobile_solid_m3.copy(); mobile[0,0] = 0.; mobile[0,2] += 10.
    after=replace(before,bed_solid_m3=bed,mobile_solid_m3=mobile,unresolved_solid_m3=17.)
    inv.apply_grid_changes(before,after)
    result,rp=inv.commit(after,bp)
    for field in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'):
        assert np.allclose(getattr(result,field),getattr(after,field),rtol=0,atol=1e-12)
    assert result.unresolved_solid_m3 == 17.
    assert inv.amount((0,0),'mobile_solid_m3') >= 0
    assert inv.amount((0,2),'mobile_solid_m3') >= 0
    save_checkpoint(tmp_path/'checkpoint',result,rp)
    loaded,lp=load_checkpoint(tmp_path/'checkpoint')
    resumed=ChannelInventory(loaded,lp)
    assert resumed.take((0,2),'bed_solid_m3',5.) == inv.take((0,2),'bed_solid_m3',5.)
    resumed.add((0,0),'bed_solid_m3',7.); inv.add((0,0),'bed_solid_m3',7.)
    a,ap=inv.commit(result,rp); b,bp=resumed.commit(loaded,lp)
    assert np.array_equal(a.bed_solid_m3,b.bed_solid_m3)
    assert ap['node_footprints']==bp['node_footprints']


def test_reject_overallocated_footprint():
    state,p=example();p['node_footprints'][1][2][0][2]=.8
    with pytest.raises(ValueError,match='overlapping'):
        ChannelInventory(state,p)


def test_actual_v3_roundtrip():
    state,p=load_checkpoint('.scratch/delta-hundred-km-20261103/network-v3-initial')
    inv=ChannelInventory(state,p);out,updated=inv.commit(state,p)
    for field in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'):
        np.testing.assert_allclose(getattr(out,field),getattr(state,field),rtol=1e-12,atol=1e-7)
    assert out.unresolved_solid_m3==state.unresolved_solid_m3
    assert len(updated['node_footprints'])==len(p['node_footprints'])
