"""Build a compact event-driven window channel and lake display geometry."""
import json
from pathlib import Path
import numpy as np
from terrain_pipeline.channel_geometry import build_discharge_geometry
from tools.render_world_river_acceptance import crop_slices
from terrain_pipeline.new_world_native_geometry import native_lake_wet
ROOT=Path('.scratch/river-upgrade-20261101')

def main():
    src=ROOT/'terrain-v3';evt=ROOT/'native-event-v1';der=ROOT/'native-final-routing-v1/derived';rt=ROOT/'native-final-routing-v1/routing';out=ROOT/'native-map-v1'; manifest=json.loads((src/'manifest.json').read_text(encoding='utf8'));em=json.loads((evt/'manifest.json').read_text(encoding='utf8'));report=json.loads((out/'manifest.json').read_text(encoding='utf8'))
    if manifest['identity']!=em['source_identity'] or report['source_identity']!=em['source_identity']:raise ValueError('identity mismatch')
    slices,extent=crop_slices(manifest);zs,xs=slices; shape=(zs.stop-zs.start,xs.stop-xs.start)
    bed=np.asarray(np.load(src/'bed_m.npy',mmap_mode='r')[slices],float);ocean=np.asarray(np.load(src/'ocean_mask.npy',mmap_mode='r')[slices],bool);unknown=np.asarray(np.load(src/'unknown_mask.npy',mmap_mode='r')[slices],bool)
    pool=np.asarray(np.load(der/'pool_index.npy',mmap_mode='r').reshape(4096,4096)[slices]);level=np.load(evt/'pool_level_m.npy',mmap_mode='r')[-1];wet=native_lake_wet(bed,pool,level,ocean,unknown)
    channels=np.asarray(np.load(evt/'channel_mask.npy',mmap_mode='r').reshape(4096,4096)[slices],bool);rr,cc=np.nonzero(channels);ids=(rr+zs.start)*4096+(cc+xs.start);rec=np.load(rt/'receiver.npy',mmap_mode='r');receivers=np.asarray(rec[ids]);water=np.load(evt/'node_water_m3.npy',mmap_mode='r');q=np.asarray(water[-1,ids],float)/1296000.
    geom=build_discharge_geometry(np.zeros((1,len(ids))),q[None,:],np.ones((1,len(ids)),bool),30.)['arrays'];width=geom['channel_width_m'][0];depth=geom['channel_depth_m'][0]
    # Independent equivalent local sections; these do not certify along-network water levels.
    sourcebed=bed[rr,cc]; sectionbed=sourcebed-depth;stage=sourcebed
    source_xz=np.column_stack(((cc+xs.start)*30-61440,(rr+zs.start)*30-61440));zr,xr=np.divmod(receivers,4096);dest_xz=np.column_stack((xr*30-61440,zr*30-61440));
    np.savez_compressed(out/'window-geometry.npz',lake_wet_day30=wet,pool_index=pool,channel_node_ids=ids,receiver_ids=receivers,channel_source_xz_m=source_xz,channel_target_xz_m=dest_xz,channel_q_m3_s=q,channel_width_m=width,channel_section_bed_m=sectionbed,channel_section_stage_m=stage,channel_source_bed_m=sourcebed,window_origin_xz_m=np.array([xs.start*30-61440,zs.start*30-61440]),spacing_m=30.)
    print(json.dumps(dict(channel_count=len(ids),lake_wet_cells=int(wet.sum()),extent=extent,source_identity=em['source_identity']),indent=2))
if __name__=='__main__':main()
