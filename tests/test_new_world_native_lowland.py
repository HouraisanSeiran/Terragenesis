import numpy as np
from terrain_pipeline.drainage import accumulate_inplace as accumulate
from terrain_pipeline.drainage import channels_and_capture as channels_and_capture
from terrain_pipeline.runoff import LowlandRunoffConfig as LowlandRunoffConfig
from terrain_pipeline.runoff import lowland_geometry as lowland_geometry


def test_area_closure_and_pool_flow_gate():
    order=np.array([0,1,2,3,4]); receiver=np.array([-1,0,1,2,3])
    area=np.ones(5,dtype=np.int32); accumulate(order,receiver,area)
    assert area.tolist()==[5,4,3,2,1]
    # Every cell has enough area. The interior is not a river even when its
    # pre-collapse volume is high; the dry anchor breaks downstream closure.
    area[:]=5000
    labels=np.array([-1,-1,0,0,-1]); anchors=np.array([2]); low=np.zeros(5,dtype=bool)
    ocean=np.zeros(5,dtype=bool); unknown=ocean.copy(); valid=np.ones(5,dtype=bool)
    flow=np.full(5,50000.); flow[2]=0
    channel=np.zeros(5,dtype=bool); capture=np.empty(5,dtype=np.int32)
    channels_and_capture(order,receiver,labels,anchors,area,low,ocean,unknown,valid,flow,channel,capture)
    assert channel.tolist()==[True,True,False,False,True]
    assert capture.tolist()==[0,1,1,1,4]


def test_lowland_relief_and_slope():
    bed=np.zeros((25,25)); bed[:,13:]=30
    _,_,low=lowland_geometry(bed,30,LowlandRunoffConfig())
    assert low[12,0] and not low[12,12]
