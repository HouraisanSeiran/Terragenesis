"""Produce fixed-window, source-bound ridge breakup comparisons."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_forms import RidgeBreakupConfig, rasterize_ridge_breakup as rasterize
from terrain_pipeline.mountain_forms import VoronoiConfig
from terrain_pipeline.terrain_map_style import physical_hillshade
from tools.prepare_mountain_forms import measured
from tools.prepare_mountain_forms import routing

WINDOWS = {'main': (0., 0.), 'negative': (-24000., -24000.)}
STAGES = ('original', 'gaussian', 'breakup', 'final')
HEIGHTS = ('original_height_m', 'gaussian_height_m', 'breakup_height_m', 'height_m')
DELTAS = ('original_delta_m', 'gaussian_delta_m', 'breakup_delta_m', 'final_delta_m')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(fields, spacing):
    original = fields[DELTAS[0]]
    result = {}
    for name, key in zip(STAGES, DELTAS):
        value = fields[key]
        dz, dx = np.gradient(value, spacing)
        slope = np.hypot(dx, dz)
        lap = np.gradient(dx, spacing, axis=1) + np.gradient(dz, spacing, axis=0)
        result[name] = {'rms_m': float(np.sqrt(np.mean(value ** 2))),
                        'mean_abs_change_from_original_m': float(np.mean(np.abs(value - original))),
                        'slope_p95': float(np.percentile(slope, 95)),
                        'gradient_energy': float(np.mean(slope ** 2)),
                        'laplacian_energy_per_m2': float(np.mean(lap ** 2))}
    gap = fields['gap_field']
    retention = fields['ridge_retention']
    positive = fields['warped_delta_m'] > 0
    result['gap_field'] = {'min': float(gap.min()), 'max': float(gap.max()), 'mean': float(gap.mean()),
                           'fraction_above_0_7': float(np.mean(gap > .7)),
                           'positive_ridge_retention_below_0_2': float(np.mean(retention[positive] < .2)) if positive.any() else None,
                           'positive_ridge_retention_above_0_99': float(np.mean(retention[positive] > .99)) if positive.any() else None,
                           'meaning': 'noise attenuation control, not measured real terrain passes'}
    # Gradient orientation, modulo 180 degrees, weighted toward stronger original gradients.
    oz, ox = np.gradient(original, spacing)
    bz, bx = np.gradient(fields['breakup_delta_m'], spacing)
    valid = np.hypot(ox, oz) > np.percentile(np.hypot(ox, oz), 75)
    angle = np.abs(np.arctan2(oz, ox) - np.arctan2(bz, bx)) % np.pi
    result['gradient_orientation_change'] = {'selection': 'top quartile original gradient magnitude; axial angle, not tracked ridge centerline',
        'median_degrees': float(np.degrees(np.median(np.minimum(angle[valid], np.pi - angle[valid])))) if valid.any() else None}
    return result


def render(path, fields, origin, spacing):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    n = fields['height_m'].shape[0]
    heights = [fields[k] for k in HEIGHTS]
    low = min(float(h.min()) for h in heights); high = max(float(h.max()) for h in heights)
    extent = [origin[0] / 1000, (origin[0] + (n - 1)*spacing)/1000,
              (origin[1] + (n - 1)*spacing)/1000, origin[1]/1000]
    stride = max(1, int(np.ceil(n / 90)))
    x, z = np.meshgrid((origin[0] + np.arange(n)[::stride] * spacing)/1000,
                       (origin[1] + np.arange(n)[::stride] * spacing)/1000)
    fig = plt.figure(figsize=(16, 14), constrained_layout=True)
    lim = max(float(np.max(np.abs(fields[k]))) for k in DELTAS)
    for col, (name, h, key) in enumerate(zip(STAGES, heights, DELTAS)):
        for row, az in enumerate((-60, 120)):
            ax = fig.add_subplot(4, 4, row*4+col+1, projection='3d')
            sample = h[::stride, ::stride]
            shade = physical_hillshade(h, spacing)[::stride, ::stride]
            gray = np.repeat(np.clip(.22+.68*shade, 0, 1)[...,None], 3, axis=2)
            ax.plot_surface(x,z,sample/1000, facecolors=gray, shade=False, linewidth=0, antialiased=False,
                            rcount=sample.shape[0], ccount=sample.shape[1])
            ax.set_zlim(low/1000, high/1000); ax.set_box_aspect((1,1,.35)); ax.view_init(elev=25,azim=az)
            ax.set_title(f'{name} az={az}°'); ax.set_xlabel('X km'); ax.set_ylabel('Z km')
        ax = fig.add_subplot(4,4,9+col)
        im=ax.imshow(fields[key],extent=extent,cmap='coolwarm',vmin=-lim,vmax=lim)
        ax.set_title(name+' structure delta'); ax.set_xlabel('World X km'); ax.set_ylabel('World Z km'); fig.colorbar(im,ax=ax,label='m')
        ax=fig.add_subplot(4,4,13+col)
        ax.imshow(physical_hillshade(h,spacing),extent=extent,cmap='gray',vmin=0,vmax=1)
        ax.set_title(name+' overhead'); ax.set_xlabel('World X km'); ax.set_ylabel('World Z km')
    exaggeration=.35*((n-1)*spacing)/(high-low)
    fig.suptitle(f'World origin {origin} m; shared elevation scale; vertical exaggeration {exaggeration:.2f}×; surface stride {stride}')
    fig.savefig(path,dpi=100); plt.close(fig)
    fig=plt.figure(figsize=(7,5),constrained_layout=True); ax=fig.add_subplot(111,projection='3d')
    h=heights[-1][::stride,::stride]; shade=physical_hillshade(heights[-1],spacing)[::stride,::stride]
    gray=np.repeat(np.clip(.22+.68*shade,0,1)[...,None],3,axis=2)
    ax.plot_surface(x,z,h/1000,facecolors=gray,shade=False,rcount=h.shape[0],ccount=h.shape[1],linewidth=0)
    ax.set_zlim(low/1000,high/1000); ax.set_box_aspect(((n-1)*spacing,(n-1)*spacing,high-low))
    ax.set_title('Full breakup, physical aspect 1:1'); ax.view_init(elev=25,azim=-60)
    physical=path.with_name(path.stem+'_1to1.png'); fig.savefig(physical,dpi=100); plt.close(fig)
    files=[path,physical]
    fig, axes = plt.subplots(2, 3, figsize=(14, 9), constrained_layout=True)
    for ax, key in zip(axes.ravel(), ('original_delta_m', 'gaussian_delta_m', 'warped_delta_m',
                                     'breakup_delta_m', 'final_delta_m', 'cut_delta_m')):
        im = ax.imshow(fields[key], extent=extent, cmap='coolwarm', vmin=-lim, vmax=lim)
        ax.set_title(key); ax.set_xlabel('World X km'); ax.set_ylabel('World Z km')
        fig.colorbar(im, ax=ax, label='m')
    fig.suptitle('Structure stages; cut_delta is nonnegative removed uplift')
    structure = path.with_name(path.stem+'_structure.png')
    fig.savefig(structure, dpi=100); plt.close(fig); files.append(structure)
    if origin == (0.,0.):
        lo,hi=round(9000/spacing),round(15000/spacing)
        fig,axes=plt.subplots(2,4,figsize=(15,7),constrained_layout=True)
        for col,(name,key) in enumerate(zip(STAGES,DELTAS)):
            axes[0,col].imshow(fields[key][lo:hi+1,lo:hi+1],extent=[9,15,15,9],cmap='coolwarm',vmin=-lim,vmax=lim)
            axes[0,col].set_title(name+' structure'); axes[0,col].set_xlabel('World X km'); axes[0,col].set_ylabel('World Z km')
            axes[1,col].plot(np.arange(lo,hi+1)*spacing/1000,fields[key][(lo+hi)//2,lo:hi+1])
            axes[1,col].set_ylim(-lim,lim); axes[1,col].set_xlabel('World X km'); axes[1,col].set_ylabel('Structure delta m')
        fig.suptitle('Fixed 9–15 km structure window; Z=12 km section')
        central=path.with_name(path.stem+'_central.png'); fig.savefig(central,dpi=100); plt.close(fig); files.append(central)
    return {p.name:{'sha256':digest(p)} for p in files}, {'surface_stride':stride,'vertical_exaggeration':exaggeration,'physical_aspect':'1:1'}


def generate(output, size=201, spacing=120., windows=('main',), families=('ridge_network',), benchmark_sizes=()):
    target=Path(output).resolve()
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.'+target.name+'-',dir=target.parent))
    try:
        source_names=('terrain_pipeline/mountain_forms.py','terrain_pipeline/mountain_forms.py',
            'terrain_pipeline/mountain_forms.py','terrain_pipeline/mountain_forms.py',
            'terrain_pipeline/world_seed.py','diffusion/geographic_noise.py','terrain_pipeline/terrain_map_style.py',
            'terrain_pipeline/drainage.py','terrain_pipeline/surface_rivers/metric_contracts.py',
            'terrain_pipeline/drainage.py','terrain_pipeline/mountain_source_adapter.py',
            'tools/prepare_mountain_forms.py','tools/prepare_mountain_forms.py','tools/prepare_ridge_breakup.py')
        hashes={name:digest(ROOT/name) for name in source_names}
        manifest={'world_seed':20260903,'coordinates':'X east, Z south, metres','source_hashes_sha256':hashes,
            'selection':'fixed before inspection','gaussian_sampling':'world anchored auxiliary grid; see physical step in algorithm metadata; output spacing is separate',
            'boundary':'unknown perimeter; diagnostic topology, not proof of preserved river network',
            'runs':{},'benchmark':[],'measurement_scope':'generation and routing: wall time, tracemalloc, sampled whole-process RSS; rendering wall time separately'}
        for window in windows:
            origin=WINDOWS[window]
            for family in families:
                cfg=RidgeBreakupConfig(voronoi=VoronoiConfig(world_seed=20260903,family=family))
                fields,timing=measured(lambda:rasterize(origin,(size,size),spacing,cfg))
                prefix=window+'_'+family
                metadata={'algorithm':fields['metadata'],'origin_m_xz':origin,'spacing_m':spacing,'shape_zx':[size,size], 'source_hashes_sha256':hashes}
                path=stage/(prefix+'.npz')
                np.savez_compressed(path,**{k:v for k,v in fields.items() if k!='metadata'},metadata_json=np.array(json.dumps(metadata,ensure_ascii=False,allow_nan=False)))
                start=time.perf_counter(); images,rendering=render(stage/(prefix+'.png'),fields,origin,spacing); render_time=time.perf_counter()-start
                diag= rasterize(origin,(65,65),375.,cfg)
                adapted={'advanced_base_m':diag['advanced_base_m'],'unprotected_height_m':diag['original_height_m'],
                    'height_m':diag['height_m'],'protection_mask':diag['protection_mask'],'structure_delta_m':diag['final_delta_m']}
                (route,arrays),route_time=measured(lambda:routing(adapted,origin,375.,20260903))
                for suffix in ('receiver', 'terminal', 'routed_q_m3_s'):
                    arrays['original_height_m_' + suffix] = arrays.pop('unprotected_height_m_' + suffix)
                core = diag['protection_mask'].ravel() == 1
                route['original_to_final'] = {
                    'receiver_changed_fraction': float(np.mean(arrays['original_height_m_receiver'] != arrays['height_m_receiver'])),
                    'terminal_changed_fraction': float(np.mean(arrays['original_height_m_terminal'] != arrays['height_m_terminal'])),
                    'core_receiver_changed_fraction': float(np.mean((arrays['original_height_m_receiver'] != arrays['height_m_receiver'])[core])) if core.any() else None,
                    'core_terminal_changed_fraction': float(np.mean((arrays['original_height_m_terminal'] != arrays['height_m_terminal'])[core])) if core.any() else None}
                route['original_height_m'] = route.pop('unprotected_height_m')
                route['protection']['mean_abs_original_to_final_edge_slope_change'] = route['protection'].pop('mean_abs_slope_effect')
                for key in ('unprotected_height_m', 'structure_delta_m'):
                    arrays.pop(key, None)
                arrays.update({k:v for k,v in diag.items() if k!='metadata'})
                routepath=stage/(prefix+'_routing.npz'); np.savez_compressed(routepath,**arrays)
                manifest['runs'][prefix]={'data':path.name,'sha256':digest(path),'metadata':metadata,'metrics':metrics(fields,spacing),
                    'images':images,'rendering':rendering,'generation':timing,'render_seconds':render_time,
                    'routing':{'data':routepath.name,'sha256':digest(routepath),'spacing_m':375.,'results':route,'timing':route_time,
                               'stage_mapping':{'advanced_base_m':'Advanced base', 'original_height_m':'original protected Voronoi',
                                                'height_m':'final protected breakup'}}}
        for n in benchmark_sizes:
            cfg=RidgeBreakupConfig(voronoi=VoronoiConfig(world_seed=20260903,family='ridge_network'))
            for origin in ((0.,0.),(500000000.,-500000000.)):
                _,timing=measured(lambda:rasterize(origin,(n,n),60.,cfg))
                manifest['benchmark'].append({'size':n,'origin_m_xz':origin,'spacing_m':60.,**timing})
        (stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
        os.rename(stage,target)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    return target


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--final',action='store_true')
    a=p.parse_args()
    print(generate(a.output_dir,401 if a.final else 201,60. if a.final else 120.,
        ('main','negative') if a.final else ('main',),('ridge_network','mixed') if a.final else ('ridge_network',),
        (128,256,512) if a.final else ()))


if __name__=='__main__': main()
