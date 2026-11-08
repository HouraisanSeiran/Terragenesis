"""Read-only maps of completed delta checkpoints; never runs the evolution solver."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
import numpy as np
from scipy.ndimage import distance_transform_edt

from terrain_pipeline.coastal_delta_evolution import load
from terrain_pipeline.coastal_marine_sediment import classify_ocean
from terrain_pipeline.terrain_map_style import physical_hillshade

ROOT = Path('.scratch/delta-large-acceptance-20261103')
HISTORY = Path('.scratch/coast-marine-reorganization-20261102/river-connection-v4-data.npz')
LAND_LEVELS = [-20, 0, 2, 5, 20, 100, 500, 2000, 5000]
LAND_COLORS = ['#c1b99b', '#d5d3aa', '#c9d19f', '#b5c993', '#99b781', '#8da375', '#a99f83', '#d3cabc', '#f4f1e9']
SEA_LEVELS = [-10000, -1000, -100, -20, -5, 0]
SEA_COLORS = ['#284e6a', '#366d88', '#579ab0', '#83bac2', '#aed3cd', '#d0e5d8']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rgb_ramp(values, levels, colors):
    channels = np.array([to_rgb(c) for c in colors])
    return np.stack([np.interp(values, levels, channels[:, i]) for i in range(3)], axis=-1)


def terrain(state, unknown):
    bed = state.bed_m
    ocean, _ = classify_ocean(state, 0.0)
    land = rgb_ramp(bed, LAND_LEVELS, LAND_COLORS)
    sea = rgb_ramp(bed, SEA_LEVELS, SEA_COLORS)
    # Bound bathymetric gradients at depth to prevent abyssal slopes dominating the shelf.
    land_shade = physical_hillshade(bed * 1.5, state.spacing_m)
    sea_shade = physical_hillshade(np.maximum(bed, -1000) * 1.5, state.spacing_m)
    rgb = np.where(ocean[..., None], sea * (0.72 + .40 * sea_shade[..., None]),
                   land * (0.65 + .50 * land_shade[..., None]))
    rgb[unknown] = .50 * rgb[unknown] + .50 * np.array(to_rgb('#b5a0c6'))
    rgb[~state.valid_mask] = (0.92, 0.92, 0.92)
    return np.clip(rgb, 0, 1), ocean


def segments(state, progress):
    sections = {tuple(map(int, n[:2])): n for n in progress.get('hydraulic_sections', {}).get('nodes', [])}
    hydraulic = progress.get('river_hydraulics') or {}
    water = {tuple(map(int, n[:2])): n for n in hydraulic.get('nodes', [])}
    routes = progress.get('routes', [])
    q = hydraulic.get('route_q_m3_s', [])
    widths = progress.get('widths_m', [])
    result = []
    for index, route in enumerate(routes):
        if index >= len(q) or q[index] <= 0:
            continue
        lines = []
        for a, b in zip(route, route[1:]):
            a, b = tuple(a), tuple(b)
            if max(abs(a[0]-b[0]), abs(a[1]-b[1])) != 1:
                continue
            if not all(c in sections and c in water and state.valid_mask[c] and
                       water[c][4] > 0 and water[c][2] > sections[c][2] for c in (a, b)):
                continue
            lines.append([a, b])
        if lines:
            result.append({'index': index + 1, 'q_m3_s': q[index],
                           'width_m': widths[index] if index < len(widths) else None,
                           'segments': lines})
    return result


def coordinates(cells, state):
    cells = np.asarray(cells)
    return (state.origin_xz_m[0] + cells[:, 1] * state.spacing_m) / 1000, (state.origin_xz_m[1] + cells[:, 0] * state.spacing_m) / 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('initial', 'formed', 'final', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    output = Path(args.output)
    # Exclusive creation avoids overwriting existing renders or leaving misleading partial products.
    if output.exists():
        raise FileExistsError(output)
    manifest_path = ROOT / 'case-source/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    source_path = ROOT / 'case-source/source.npz'
    if digest(source_path) != manifest['source_sha256']:
        raise ValueError('source file hash mismatch')
    with np.load(source_path, allow_pickle=False) as source_file:
        source = {k: source_file[k] for k in source_file.files}
    states, progress, hashes = [], [], {}
    for name in ('initial', 'formed', 'final'):
        prefix = Path(getattr(args, name))
        before = {ext: digest(prefix.with_suffix(ext)) for ext in ('.json', '.npz')}
        state, meta = load(prefix)
        if before != {ext: digest(prefix.with_suffix(ext)) for ext in before}:
            raise ValueError('checkpoint changed while reading: ' + str(prefix))
        if state.source_identity != manifest['source_identity'] or not np.array_equal(state.valid_mask, source['valid_mask']) or not np.array_equal(state.origin_xz_m, source['origin_xz_m']) or state.spacing_m != float(source['spacing_m']) or not np.allclose(state.base_bed_m, source['derived_base_bed_m'], rtol=0, atol=1e-5):
            raise ValueError('checkpoint/source binding mismatch: ' + str(prefix))
        states.append(state); progress.append(meta); hashes[name] = {'prefix': str(prefix), 'sha256': before}
    with np.load(HISTORY, allow_pickle=False) as f:
        history = f['path_xz_m'].copy() / 1000
    routes = [segments(s, p) for s, p in zip(states, progress)]
    if not routes[1]:
        raise ValueError('formed checkpoint has no saved positive-flow wet route segments')
    mask = np.zeros(states[0].bed_m.shape, bool)
    for route in routes[1]:
        for line in route['segments']:
            for cell in line:
                mask[tuple(cell)] = True
    near = distance_transform_edt(~mask) * states[0].spacing_m <= 5000
    footprint = source['source_ocean'] & (states[0].bed_m > 0) & near
    rows, cols = np.where(mask | footprint)
    x = (states[0].origin_xz_m[0] + cols * states[0].spacing_m) / 1000
    z = (states[0].origin_xz_m[1] + rows * states[0].spacing_m) / 1000
    bbox = [float(x.min()), float(x.max()), float(z.min()), float(z.max())]
    cx, cz = (bbox[0]+bbox[1])/2, (bbox[2]+bbox[3])/2
    size = min(35., max(20., bbox[1]-bbox[0]+6, bbox[3]-bbox[2]+6))
    window = [cx-size/2, cx+size/2, cz-size/2, cz+size/2]
    extent = [-40, 60, 60, -40]
    plt.rcParams.update({'font.family': 'Microsoft YaHei', 'axes.unicode_minus': False, 'font.size': 10})
    output.mkdir(parents=True)
    legend = [Patch(color='#b5a0c6', label='原未知湿区（非无效 DEM）'), Line2D([0],[0],color='#087bb5',lw=2.5,label='已保存正流量湿河槽（线宽增强）'), Line2D([0],[0],color='#555555',ls='--',lw=1,label='历史河槽几何（本轮未重算沿线水面）')]

    def draw(ax, idx, limits, title):
        image, ocean = terrain(states[idx], source['unknown_wet'])
        ax.imshow(image, extent=extent, origin='upper', interpolation='nearest')
        ax.plot(history[:,0], history[:,1], '--', color='#555555', lw=.8, alpha=.85)
        paths = []
        for route in routes[idx]:
            for line in route['segments']:
                xx, zz = coordinates(line, states[idx]); paths.append(np.column_stack((xx, zz)))
        ax.add_collection(LineCollection(paths, colors='#f0f9f9', linewidths=3.1, capstyle='round'))
        ax.add_collection(LineCollection(paths, colors='#087bb5', linewidths=1.8, capstyle='round'))
        ax.set(xlim=limits[:2], ylim=(limits[3], limits[2]), xlabel='世界 X / km', ylabel='世界 Z / km', title=title)
        ax.text(.04,.94,'N ↑',transform=ax.transAxes,va='top',weight='bold',bbox=dict(facecolor='white',alpha=.7,edgecolor='none'))
        length = 10 if limits[1]-limits[0] > 50 else 5
        ax.plot([.05,.05+length/(limits[1]-limits[0])],[.06,.06],transform=ax.transAxes,color='black',lw=3)
        ax.text(.05,.075,f'{length} km',transform=ax.transAxes,fontsize=9)
        return ocean

    def footer(fig):
        fig.text(.04,.018,'地形色为高程示意，非真实覆盖 | 固定光照：西北、垂直夸张 1.5× | 蓝线显示加宽，非 200 m 整格开挖',fontsize=9)

    def swatches(fig):
        labels = ['陆地高程 m：0', '2', '5', '20', '100', '500', '2000+', '海深 m：0', '5', '20', '100', '1000+']
        colors = [LAND_COLORS[i] for i in [1,2,3,4,5,6,7]] + [SEA_COLORS[i] for i in [5,4,3,2,1]]
        fig.legend(handles=[Patch(color=c,label=l) for c,l in zip(colors,labels)],loc='lower center',bbox_to_anchor=(.5,.045),ncol=6,frameon=False,fontsize=8)

    fig, ax = plt.subplots(figsize=(12,10)); fig.subplots_adjust(bottom=.19); draw(ax,1,[-40,60,-40,60],'100 × 100 km 区域地形与已保存水路'); ax.add_patch(Rectangle((window[0],window[2]),size,size,fill=False,edgecolor='#d05c3f',lw=1.5)); ax.legend(handles=legend,loc='upper right',fontsize=8); swatches(fig); footer(fig); fig.savefig(output/'regional.png',dpi=195,bbox_inches='tight'); plt.close(fig)
    fig, ax = plt.subplots(figsize=(12,10)); fig.subplots_adjust(bottom=.19); draw(ax,1,window,'三角洲主体及邻近地形'); ax.legend(handles=legend,loc='upper right',fontsize=8); swatches(fig); footer(fig); fig.savefig(output/'detail.png',dpi=195,bbox_inches='tight'); plt.close(fig)
    fig, axes = plt.subplots(1,3,figsize=(15,6)); fig.subplots_adjust(bottom=.28,wspace=.25); draw(axes[0],0,window,'初始床面'); draw(axes[1],2,window,'末态床面'); diff=states[2].bed_m-states[0].bed_m; vmax=max(float(np.nanmax(np.abs(diff))), .01); im=axes[2].imshow(np.ma.masked_where(~source['valid_mask'],diff),extent=extent,origin='upper',cmap='RdBu_r',vmin=-vmax,vmax=vmax,interpolation='nearest'); axes[2].set(xlim=window[:2],ylim=(window[3],window[2]),xlabel='世界 X / km',ylabel='世界 Z / km',title='末态 − 初始床变 / m'); fig.colorbar(im,ax=axes[2],shrink=.65,label='床变 / m'); fig.legend(handles=legend,loc='lower center',bbox_to_anchor=(.5,.07),ncol=2,fontsize=8,frameon=False); footer(fig); fig.savefig(output/'comparison.png',dpi=150,bbox_inches='tight'); plt.close(fig)
    common = {'terrain_basis': 'saved checkpoint bed = derived TD base plus saved sediment; no synthetic relief', 'source_manifest_sha256': digest(manifest_path), 'source_identity': manifest['source_identity'], 'source_sha256': digest(source_path), 'source_td_pages': manifest['pages'], 'source_algorithm': manifest['algorithm'], 'checkpoints': hashes, 'origin_xz_m': manifest['origin_xz_m'], 'spacing_m': manifest['spacing_m'], 'native_spacing_m': 30, 'world_seed': manifest['world_seed'], 'times': {n: {'formation_equivalent_years': p.get('years'), 'physical_time_s': s.time_s} for n,s,p in zip(('initial','formed','final'),states,progress)}, 'algorithms': {'ocean': 'classify_ocean at 0 m', 'hillshade': 'terrain_map_style.physical_hillshade, NW light, vertical exaggeration 1.5; seabed shade clipped below -1000 m', 'land_ramp_m': LAND_LEVELS, 'sea_ramp_m': SEA_LEVELS, 'routes': 'saved river_hydraulics nodes intersect hydraulic_sections and valid route adjacent pairs; Q>0 and stage>section bed'}, 'coverage_status': 'unknown_wet shown separately, actual water may overlay; history is geometry only, no recomputed water; historical inventory is not new supply', 'display': {'water_width_points': 1.8, 'water_outline_points': 3.1, 'actual_route_widths_m': {n:[{'route':r['index'],'width_m':r['width_m'],'q_m3_s':r['q_m3_s']} for r in rs] for n,rs in zip(('initial','formed','final'),routes)}, 'body_bbox_xmin_xmax_zmin_zmax_km': bbox, 'body_definition': 'source-ocean initial positive bed within 5 km of formed active route plus active route', 'detail_window_xmin_xmax_zmin_zmax_km': window, 'history_file_sha256':digest(HISTORY)}, 'change_m': {'minimum':float(diff.min()), 'maximum':float(diff.max()), 'colour_limit_abs':vmax}}
    for image in ('regional.png','detail.png','comparison.png'):
        info = dict(common, image=image, image_sha256=digest(output/image))
        (output/(Path(image).stem+'.json')).write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(output),'bbox_km':bbox,'window_km':window,'routes':common['display']['actual_route_widths_m'],'change_m':common['change_m']},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
