import numpy as np
from terrain_pipeline.large_delta_forward import forward_network,attach_source_reach
from terrain_pipeline.large_delta_evolution import evolve
from terrain_pipeline.large_delta_state import save_state,load_state,classify_ocean,map_to_hydro_nodes


def make_case():
 b=np.zeros((31,31)); v=np.ones_like(b,bool);o=np.zeros_like(v);o[:,24:]=True
 n=forward_network(b,b,~o,v,o,(0,0),100.,(15,2),(1,0),20.)
 return attach_source_reach(n,[(15,0),(15,1),(15,2)],b,(0,0),100.,20.)


def test_checkpoint_resume_matches_uninterrupted(tmp_path):
 n=make_case(); full=evolve(n,intervals=3,interval_seconds=100.,inlet_solid_m3_s=.002)
 part=evolve(n,intervals=1,interval_seconds=100.,inlet_solid_m3_s=.002)
 path=tmp_path/'state.npz';save_state(path,part['state'],source_identity='a'*64,geometry_identity='b'*64)
 state=load_state(path,source_identity='a'*64,geometry_identity='b'*64)
 resumed=evolve(part['network'],intervals=2,interval_seconds=100.,inlet_solid_m3_s=.002,state=state)
 for key in ('loose_solid_m3','mobile_solid_m3','reach_bed_m','width_m'):
  np.testing.assert_allclose(resumed['state'][key],full['state'][key],rtol=1e-12,atol=1e-12)
 assert resumed['state']['time_seconds']==300.
 np.testing.assert_allclose(resumed['network']['bed_m'],full['network']['bed_m'],atol=1e-12)


def test_repeated_section_does_not_duplicate_pixel_projection():
 n=make_case(); clone={**n,'sections':np.insert(n['sections'],1,n['sections'][1],axis=0)}
 a=evolve(n,intervals=1,interval_seconds=100.,inlet_solid_m3_s=.002)
 b=evolve(clone,intervals=1,interval_seconds=100.,inlet_solid_m3_s=.002)
 np.testing.assert_allclose(a['network']['bed_m'],b['network']['bed_m'],atol=1e-12)


def test_ocean_reclassification_keeps_isolated_water_unknown():
 b=np.ones((5,5));v=np.ones((5,5),bool);o=np.zeros((5,5),bool);o[0,0]=o[2,2]=True;b[o]=-1
 sea,unknown=classify_ocean(b,v,o)
 assert sea[0,0] and unknown[2,2]
 b[0,0]=1;sea,unknown=classify_ocean(b,v,o)
 assert not sea.any() and unknown[2,2]


def test_hydro_mapping_partitions_shared_pixel_stock():
 p={'n':1,'node_rows':[{'branch':0,'width':2.,'length':3.}], 'lo':np.array([0,0]),'hi':np.array([2,2]),'local_valid':np.ones((2,2),bool),'fraction':np.array([[.25,0],[0,0]]),'owner':np.array([[0,-1],[-1,-1]]),'block':2,'nz':1,'nx':1}
 state={'time_seconds':4.,'loose_solid_m3':np.array([3.]),'mobile_solid_m3':np.array([2.])}
 mapped=map_to_hydro_nodes(p,state,np.array([[8.,0],[0,0]]))
 np.testing.assert_allclose(mapped['active_solid_m3'],[6.,5.]);np.testing.assert_allclose(mapped['mobile_solid_m3'],[0.,2.])


def test_mouth_history_replay_appends_without_double_charging(tmp_path):
 from terrain_pipeline.large_delta_state import save_mouth_checkpoint,replay_mouth_checkpoint
 from terrain_pipeline.common_infra import TerrainGrid
 from terrain_pipeline.surface_rivers.metric_fluvial_delta import FluvialDeltaBoundary,FluvialDeltaInterval
 bed=np.array([[.1,-.5,-.5,-.5]],dtype=float);valid=np.ones_like(bed,bool);ocean=bed<0;exports=np.array([[False,False,False,True]])
 terrain=TerrainGrid(bed,valid,0,0,2,3,'diagnostic_dem_proxy','fixture','c'*64)
 boundary=FluvialDeltaBoundary(ocean,exports,0,10,'sea')
 forcing=[FluvialDeltaInterval((0,0),10.,10.)]
 path=tmp_path/'mouth.npz';save_mouth_checkpoint(path,{'terrain':terrain,'boundary':boundary,'forcing':forcing})
 result=replay_mouth_checkpoint(path,append_cells=[(0,0)],append_water=[100.],append_solid=[2.])
 assert np.isclose(result['solid_ledger']['input_solid_m3'],12.)
 assert abs(result['solid_ledger']['residual_solid_m3'])<1e-10


def test_hydro_stock_round_trip_preserves_reach_and_coast():
 from types import SimpleNamespace
 from terrain_pipeline.large_delta_state import unpack_hydro_state
 p={'n':1,'node_rows':[{'branch':0,'width':2.,'length':3.}], 'lo':np.array([0,0]),'hi':np.array([2,2]),'local_valid':np.ones((2,2),bool),'fraction':np.array([[.25,0],[0,0]]),'owner':np.array([[0,-1],[-1,-1]]),'block':2,'nz':1,'nx':1,'coast_area':np.array([[.75,1],[1,1]])}
 s={'time_seconds':4.,'loose_solid_m3':np.array([3.]),'mobile_solid_m3':np.array([2.])}
 mapped=map_to_hydro_nodes(p,s,np.array([[8.,0],[0,0]]))
 result={'state':SimpleNamespace(bed_solid_m3=mapped['active_solid_m3'],mobile_solid_m3=mapped['mobile_solid_m3'],time_s=5.),'node_bed_m':np.array([0.,-1.])}
 state=unpack_hydro_state(p,result,1,(2,2))
 assert np.isclose(state['loose_solid_m3'].sum()+state['coastal_active_solid_m3'].sum(),11.)
 assert np.isclose(state['mobile_solid_m3'].sum()+state['coastal_mobile_solid_m3'].sum(),2.)


def test_native_water_mapping_preserves_total():
 from terrain_pipeline.large_delta_state import water_to_hydro_nodes
 p={'n':1,'node_rows':[{'branch':0}],'lo':np.array([0,0]),'hi':np.array([2,2]),'local_valid':np.ones((2,2),bool),'fraction':np.array([[.25,0],[0,0]]),'owner':np.array([[0,-1],[-1,-1]]),'block':2,'nz':1,'nx':1}
 water=np.array([[8.,1.],[2.,3.]])
 np.testing.assert_allclose(water_to_hydro_nodes(p,water),[12.,2.])


def test_owned_transfer_retains_component_on_unchanged_and_changed_width():
 from terrain_pipeline.large_delta_state import transfer_owned_nodes
 old={'lo':np.array([0,0]),'hi':np.array([2,2]),'owner':np.array([[0,0],[-1,-1]]),'river_area':np.array([[.25,.5],[0,0]]),'coast_area':np.array([[.75,.5],[1,1]]),'block':2,'nz':1,'nx':1,'n':1,'branches':np.array([0])}
 water=np.array([100.,17.]);np.testing.assert_array_equal(transfer_owned_nodes(old,old,water),water)
 changed={**old,'river_area':np.array([[.4,.7],[0,0]]),'coast_area':np.array([[.6,.3],[1,1]])}
 np.testing.assert_allclose(transfer_owned_nodes(old,changed,water),water)


def test_river_bed_change_does_not_raise_coastal_bed():
 from types import SimpleNamespace
 from terrain_pipeline.large_delta_state import project_hydro_to_native
 p={'n':1,'block':1,'nz':1,'nx':1,'lo':np.array([0,0]),'hi':np.array([1,1]),'coast_area':np.array([[.8]]),'river_area':np.array([[.2]]),'owner':np.array([[0]]),'cell_area':1.,'local_bed':np.array([[5.]]),'base':np.array([5.,2.]),'node_rows':[{}]}
 result={'node_bed_m':np.array([5.,3.]),'state':SimpleNamespace(water_m3=np.array([10.,2.]))}
 bed,water=project_hydro_to_native(p,result,(1,1))
 assert bed[0,0]==5.
 assert water.sum()==12.
