"""Build and audit one bounded subgrid spill-to-ocean reach from saved hydro."""
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.spatial import cKDTree
from terrain_pipeline.common_infra import identity
from terrain_pipeline.new_world_game_delta import bounded_subgrid_channel, route_trace_sediment
from terrain_pipeline.channel_geometry import build_discharge_geometry
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters

ROOT = Path('.scratch/river-upgrade-20261101')
SOURCE_ID = 'c751a09a6f02e8c336b6b9b8fb4b11b5dc67386e9a8470b0b1d90858bf1ffb72'

def main():
    source, hydro, graph = ROOT/'terrain-v3', ROOT/'game-hydro-v1', ROOT/'game-grade-90m'
    if json.loads((hydro/'manifest.json').read_text(encoding='utf8'))['source_identity'] != SOURCE_ID:
        raise ValueError('source identity mismatch')
    mouth = int(np.flatnonzero(np.load(hydro/'derived/mouth_source.npy') == 1112508)[0])
    if str(np.load(hydro/'derived/mouth_id.npy')[mouth]) != '13966664223735675838':
        raise ValueError('mouth mismatch')
    rec = np.load(graph/'routing/receiver.npy', mmap_mode='r')
    area = np.load(graph/'contributing_cells.npy', mmap_mode='r').ravel()
    pools = np.load(hydro/'derived/pool_index.npy', mmap_mode='r')
    chain = [1112508]
    while True:
        parents = np.flatnonzero(rec == chain[-1])
        if not len(parents): raise ValueError('no upstream pool')
        parent = int(parents[np.argmax(area[parents])]); chain.append(parent)
        if pools[parent] >= 0: break
    ids = np.array(chain[::-1]); p = int(pools[ids[0]])
    anchor = int(np.load(hydro/'derived/pool_anchor.npy')[p])
    if ids[0] != anchor: raise ValueError('chain does not begin at pool anchor')
    levels = np.load(hydro/'pool_level_m.npy')[:, p]
    time = np.load(hydro/'time_seconds.npy').astype(float)
    volumes = np.asarray(np.load(hydro/'node_water_m3.npy', mmap_mode='r')[:, ids], float)
    mouth_water = np.load(hydro/'mouth_water_m3.npy')[:, mouth]
    if not np.all(volumes[:, 0] > 0) or not np.allclose(volumes[:, -1], mouth_water):
        raise ValueError('anchor overflow or mouth volume mismatch')
    x = np.load(graph/'graph/node_x_m.npy',mmap_mode='r')[ids]*3-61440
    z = np.load(graph/'graph/node_z_m.npy',mmap_mode='r')[ids]*3-61440
    nodes = np.column_stack((x,z))
    source_bed = np.load(source/'bed_m.npy', mmap_mode='r')
    ocean = np.load(source/'ocean_mask.npy', mmap_mode='r')
    # Nearest shared-ocean cell in a bounded 3 km square about mouth.
    row, col = np.rint((nodes[-1][::-1]+61440)/30).astype(int)
    r0,r1=max(0,row-100),min(ocean.shape[0],row+101)
    c0,c1=max(0,col-100),min(ocean.shape[1],col+101)
    rr,cc=np.nonzero(ocean[r0:r1,c0:c1]); marine=np.column_stack(((cc+c0)*30-61440,(rr+r0)*30-61440))
    _, near=cKDTree(marine).query(nodes[-1]); contact=marine[int(near)]
    poly=np.vstack((nodes,contact)); seg=np.linalg.norm(np.diff(poly,axis=0),axis=1)
    if np.any(seg <= 0): raise ValueError('degenerate reach')
    stations=np.r_[0.,np.cumsum(seg)]; samples=np.linspace(0,stations[-1],int(np.ceil(stations[-1]/10))+1)
    points=np.column_stack([np.interp(samples,stations,poly[:,j]) for j in range(2)])
    # Terminate at the first shared-ocean cell; do not cut inside that cell.
    cells=np.rint((points[:,::-1]+61440)/30).astype(int)
    hits=np.flatnonzero(ocean[cells[:,0],cells[:,1]])
    if not len(hits) or hits[0] == 0: raise ValueError('invalid ocean transition')
    end=int(hits[0]); points=points[:end+1]; samples=samples[:end+1]
    contact=points[-1].copy()
    if np.any(np.load(source/'unknown_mask.npy',mmap_mode='r')[cells[:end+1,0],cells[:end+1,1]]):
        raise ValueError('unknown terrain along reach')
    bed=map_coordinates(source_bed,[(points[:,1]+61440)/30,(points[:,0]+61440)/30],order=1,mode='nearest').astype(float)
    q=volumes/np.diff(time)[:,None]
    # Channel dimensions follow existing discharge/material geometry; no raster widening.
    qmean=np.interp(samples,stations[:-1],q.mean(axis=0)); shape=(1,len(samples))
    design=build_discharge_geometry(np.zeros(shape),qmean[None,:],np.ones(shape,bool),30.)['arrays']
    width=design['channel_width_m'][0]; nominal=design['channel_depth_m'][0]
    stage=np.linspace(float(min(levels[1:])),0.,len(samples))
    # The actual frozen marine bed is the downstream boundary. It is never cut.
    bed[-1]=float(source_bed[cells[end,0],cells[end,1]])
    if bed[-1] >= 0: raise ValueError('ocean boundary bed is not below sea level')
    nominal[-1]=min(nominal[-1],-bed[-1])
    section=bounded_subgrid_channel(bed,stage,width,nominal,samples)
    if section['cut_m'][-1] > 1e-9: raise ValueError('marine bed cut forbidden')
    # Only the final point is the marine boundary; no excavation inside lake floor.
    if not bool(ocean[cells[end,0],cells[end,1]]):
        raise ValueError('terminal is not shared ocean')
    node_bed=np.interp(stations[:-1],samples,section['bed_m'])
    node_stage=np.interp(stations[:-1],samples,stage)
    node_width=np.interp(stations[:-1],samples,width)
    depth=np.broadcast_to(node_stage-node_bed,volumes.shape).copy()
    lengths=np.diff(np.r_[stations[:-1],samples[-1]])
    slope=np.full(len(ids),float(levels[1]/samples[-1]))
    geom_id=identity({'points':points,'bed':section['bed_m'],'width':width}, {'source':SOURCE_ID})
    hydro_id=identity({'time':time,'water':volumes}, {'source':SOURCE_ID,'mouth':mouth})
    sediment=route_trace_sediment(receiver=np.r_[np.arange(1,len(ids)),-1].astype(np.int64),
        length_m=lengths,width_m=node_width,bed_m=node_bed,depth_m=depth,routed_water_m3=volumes,
        slope=slope,time_seconds=time,rock_floor_m=node_bed-1.,alluvium_bulk_m3=node_width*lengths*.25,
        hardness=np.full(len(ids),.5),material=MaterialParameters(provenance='local bounded scenario, uncalibrated'),
        geometry_identity=geom_id,hydraulic_identity=hydro_id,
        provenance='local scenario: 0.25 m alluvium, rock floor 1 m below constructed bed; unknown upstream solids omitted')
    out=ROOT/'game-delta-local-derived'; out.mkdir(exist_ok=True)
    np.savez_compressed(out/'reach.npz',points_xz_m=points,station_m=samples,source_bed_m=bed,
        channel_bed_m=section['bed_m'],channel_stage_m=stage,section_width_m=width,cut_m=section['cut_m'],
        node_ids=ids,node_water_m3=volumes,**sediment['arrays'])
    report=dict(source_identity=SOURCE_ID,mouth_id='13966664223735675838',pool_index=p,anchor=anchor,
        pool_stage_m=levels[1:].tolist(),anchor_overflow_m3=volumes[:,0].tolist(),mouth_water_m3=mouth_water.tolist(),
        marine_contact_xz_m=contact.tolist(),length_m=float(samples[-1]),max_cut_m=float(section['cut_m'].max()),
        construction_bulk_m3=section['construction_bulk_m3'],width_m_range=[float(width.min()),float(width.max())],
        minimum_depth_m=float(section['depth_m'].min()),geometry_identity=geom_id,hydraulic_identity=hydro_id,
        sediment_identity=sediment['identity_sha256'],mouth_solid_m3=sediment['arrays']['exported_solid_m3'][:,-1].tolist(),
        solid_balance_residual_m3=sediment['metadata']['global_residual'],
        limitations=['subgrid, prescribed linearly interpolated stage, no dynamic backwater solve',
        'local finite material scenario only; upstream solid supply unknown',
        'spill-anchor to nearest ocean only; lake interior floor unchanged',
        'constructed bulk is not sediment; terrain and water sources unchanged'])
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()


