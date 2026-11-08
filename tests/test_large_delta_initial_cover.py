import numpy as np
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import FluvialDeltaBoundary,FluvialDeltaConfig,FluvialDeltaInterval,simulate_fluvial_delta


def test_existing_cover_is_not_added_twice_and_can_reentrain():
 bed=np.array([[.1,-.5,-.5,-.5]],float);valid=np.ones(bed.shape,bool);exports=np.array([[False,False,False,True]])
 terrain=TerrainGrid(bed,valid,0.,0.,2.,3.,'diagnostic_dem_proxy','cover','c'*64)
 boundary=FluvialDeltaBoundary(bed<0,exports,0.,10.,'sea')
 config=FluvialDeltaConfig(porosity=.25,capacity_solid_per_water=.1,marine_capacity_decay_per_m=0.,max_reentrainment_depth_per_interval_m=.2)
 cover=np.array([[0.,1.,0.,0.]])
 result=simulate_fluvial_delta(terrain,boundary,[FluvialDeltaInterval((0,0),100.,0.)],config,initial_cover_solid_m3=cover)
 assert np.isclose(result['solid_ledger']['initial_stored_solid_m3'],1.)
 assert np.isclose(result['solid_ledger']['residual_solid_m3'],0.)
 assert result['reentrained_solid_m3'].sum()>0
 assert np.all(result['final_bed_m'] <= bed+1e-12)
