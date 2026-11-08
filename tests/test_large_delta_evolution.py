import numpy as np
from terrain_pipeline.large_delta_evolution import evolve
from terrain_pipeline.large_delta_forward import forward_network,attach_source_reach


def test_routed_fork_continuation_updates_width_and_preserves_stock():
    bed=np.zeros((31,31)); valid=np.ones_like(bed,bool); sea=np.zeros_like(valid);sea[:,24:]=True
    n=forward_network(bed,bed,~sea,valid,sea,(0,0),100.,(15,2),(1,0),20.)
    n=attach_source_reach(n,[(15,0),(15,1),(15,2)],bed,(0,0),100.,20.)
    r=evolve(n,intervals=3,interval_seconds=86400.,inlet_solid_m3_s=.002)
    assert abs(r['solid_residual_m3'])<1e-8
    assert np.all(r['stock_history_solid_m3']>=0)
    assert np.any(r['bed_history_m'][-1]!=r['bed_history_m'][0])
    assert np.any(r['width_history_m'][-1]!=r['width_history_m'][0])
    assert np.array_equal(r['network']['sections'][:,6],r['width_history_m'][-1][r['network']['sections'][:,0].astype(int)])
    for i,parent in enumerate(n['parent']):
        if parent>=0:
            q=n['sections'][n['sections'][:,0]==i][0,8]
            pq=n['sections'][n['sections'][:,0]==parent][0,8]
            np.testing.assert_allclose(r['incoming_solid_m3'][:,i],r['outgoing_solid_m3'][:,parent]*q/pq)
