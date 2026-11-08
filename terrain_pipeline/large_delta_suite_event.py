"""Short, finite reduced-graph tidal event on suite network reaches.

The graph has analytic channel plan areas and separate offshore buffers. It
has no floodplain cells; results must not be rendered as regional hydraulics.
"""
import numpy as np
from terrain_pipeline.large_delta_tidal_dynamics import Geometry, State, step, tide_stage, bed_elevation


def run_event(network, discharge_m3_s, sediment_m3_s, *, duration_s=43200., dt_s=10.):
    sections=network['sections']; parent=network['parent']; lengths=network['length_m']
    n=len(parent)
    if duration_s <= 0 or dt_s <= 0 or discharge_m3_s <= 0 or sediment_m3_s < 0:
        raise ValueError('invalid event forcing')
    if abs(duration_s/dt_s-round(duration_s/dt_s)) > 1e-9:
        raise ValueError('duration must be an integral number of steps')
    branches=[sections[sections[:,0]==i] for i in range(n)]
    leaves=[i for i in range(n) if i not in set(parent)]
    widths=np.array([b[0,6] for b in branches]); flow=np.array([b[0,8] for b in branches])
    area=widths*lengths
    stage=np.array([b[:,5].mean() for b in branches]); depth=np.array([b[0,7] for b in branches])
    bed=np.array([b[:,9].mean() for b in branches])
    # One physically separate offshore storage per outlet; sea forcing acts on
    # the outer face of that buffer, never directly on the river mouth.
    offshore_area=np.maximum(widths[leaves]*2000.,1.e5)
    area=np.r_[area,offshore_area]; bed=np.r_[bed,np.full(len(leaves),-4.)]
    floor=bed-0.5
    left=[];right=[];cond=[]
    for i,p in enumerate(parent):
        if p>=0:
            distance=.5*(lengths[i]+lengths[p]); q=flow[i]
            left.append(p);right.append(i);cond.append(q/max(.00005*distance,.1))
    for j,i in enumerate(leaves):
        left.append(i);right.append(n+j);cond.append(flow[i]/max(.00005*(lengths[i]/2+1000),.1))
    geom=Geometry(area,floor,np.array(left,int),np.array(right,int),np.array(cond,float),
                  np.arange(n,n+len(leaves)),np.maximum(flow[leaves]*10,100.))
    initial_stage=np.r_[stage,np.zeros(len(leaves))]
    state=State(0.,np.maximum(initial_stage-bed,0)*area,.5*.6*area,np.zeros(len(area)))
    initial_water=state.water_m3.sum(); initial_solid=state.bed_solid_m3.sum()
    water_min=state.water_m3.copy(); water_max=state.water_m3.copy(); stages=[]
    for k in range(round(duration_s/dt_s)):
        step(geom,state,dt_s,tide_stage(state.time_s+dt_s),0,discharge_m3_s,sediment_m3_s,storage_area=area)
        water_min=np.minimum(water_min,state.water_m3); water_max=np.maximum(water_max,state.water_m3)
        if k % max(1,round(3600/dt_s))==0:
            stages.append((state.time_s,*(bed_elevation(geom,state)+state.water_m3/area)))
    final_bed=bed_elevation(geom,state)
    return {'time_stage_m':np.array(stages), 'area_m2':area, 'initial_bed_m':bed,
            'final_bed_m':final_bed, 'final_water_m3':state.water_m3,
            'low_water_m3':water_min, 'high_water_m3':water_max, 'river_node_count':n,
            'water_residual_m3':float(initial_water+state.source_water_m3+state.sea_water_in_m3-state.sea_water_out_m3-state.water_m3.sum()),
            'solid_residual_m3':float(initial_solid+state.source_solid_m3-state.sea_solid_out_m3-state.bed_solid_m3.sum()-state.mobile_solid_m3.sum()),
            'source_water_m3':state.source_water_m3,'sea_water_in_m3':state.sea_water_in_m3,
            'sea_water_out_m3':state.sea_water_out_m3,'source_solid_m3':state.source_solid_m3,
            'sea_solid_out_m3':state.sea_solid_out_m3}


