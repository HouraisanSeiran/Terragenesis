"""Read-only atlas for saved delta checkpoints; no simulation is performed."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, Normalize
from matplotlib.patches import Polygon, Patch
import numpy as np

from terrain_pipeline.coastal_delta_product import load_checkpoint
from terrain_pipeline.coastal_marine_sediment import classify_ocean, load_state
from terrain_pipeline.coastal_delta_routes import load_routes

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'window100-v2'
IDENTITY = '778970b3c367bc5896e86e69b6eb17b30998482da96cd05d9d5ed7be796beb19'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def source():
    path = SOURCE / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    if manifest['source_identity'] != IDENTITY or digest(SOURCE / 'source.npz') != manifest['source_sha256']:
        raise ValueError('official source identity or source.npz hash mismatch')
    if digest(SOURCE / 'state.npz') != manifest['state_sha256']:
        raise ValueError('official source state hash mismatch')
    with np.load(SOURCE / 'source.npz', allow_pickle=False) as data:
        arrays = {key: data[key].copy() for key in data.files}
    state = load_state(SOURCE / 'state.npz')
    if (state.source_identity != IDENTITY or state.bed_m.shape != (450, 450)
            or state.spacing_m != 100 or tuple(state.origin_xz_m) != tuple(manifest['origin_xz_m'])
            or not np.array_equal(state.base_bed_m, arrays['derived_base_bed_m'])
            or not np.array_equal(state.valid_mask, arrays['valid_mask'])):
        raise ValueError('source state and source arrays disagree')
    return manifest, arrays, state


def check_state(state, reference):
    if (state.source_identity != IDENTITY or state.bed_m.shape != reference.bed_m.shape
            or state.origin_xz_m != reference.origin_xz_m or state.spacing_m != reference.spacing_m
            or not np.array_equal(state.base_bed_m, reference.base_bed_m)
            or not np.array_equal(state.valid_mask, reference.valid_mask)
            or not np.array_equal(state.ocean_seed_mask, reference.ocean_seed_mask)):
        raise ValueError('checkpoint does not match official source grid and base')


def coords(state):
    x, z = state.origin_xz_m
    d = state.spacing_m
    return [(x-d/2)/1000, (x+(state.bed_m.shape[1]-.5)*d)/1000,
            (z+(state.bed_m.shape[0]-.5)*d)/1000, (z-d/2)/1000]


def decoration(ax, scale=5, color='white'):
    ax.set_xlabel('X east (km)')
    ax.set_ylabel('Z south (km)')
    ax.annotate('N', xy=(.94, .95), xytext=(.94, .82), xycoords='axes fraction',
                ha='center', arrowprops={'arrowstyle': '->', 'color': color}, color=color, weight='bold')
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    x = x0 + .06*(x1-x0); y = y0 + .08*(y1-y0)
    ax.plot([x, x+scale], [y, y], color=color, lw=3)
    ax.text(x, y, f'{scale} km', color=color, va='bottom', fontsize=8)


def terrain(ax, state, unknown, norm, sea_level):
    bed = state.bed_m
    rgb = LightSource(azdeg=315, altdeg=45).shade(bed, cmap=plt.get_cmap('terrain'),
        norm=norm, blend_mode='soft', vert_exag=1, dx=state.spacing_m, dy=state.spacing_m)
    ocean, _ = classify_ocean(state, sea_level)
    rgb[ocean & ~unknown] = [0.18, 0.42, 0.57, 1]
    rgb[~state.valid_mask | unknown] = [0.72, 0.33, 0.68, 1]
    ax.imshow(rgb, extent=coords(state), origin='upper', interpolation='nearest')
    return ocean


def point(state, cells):
    a = np.asarray(cells, dtype=float)
    if a.ndim != 2 or a.shape[1] != 2 or not np.isfinite(a).all():
        raise ValueError('invalid route cells')
    if np.any(a != np.floor(a)) or np.any(a < 0) or np.any(a[:, 0] >= state.bed_m.shape[0]) or np.any(a[:, 1] >= state.bed_m.shape[1]):
        raise ValueError('route cells outside grid')
    return (state.origin_xz_m[0] + a[:, 1]*state.spacing_m)/1000, (state.origin_xz_m[1] + a[:, 0]*state.spacing_m)/1000


def hydraulics(progress, state):
    h = progress.get('river_hydraulics')
    if not isinstance(h, dict) or 'nodes' not in h:
        return None, []
    sections = {(int(n[0]), int(n[1])): (float(n[2]), float(n[3])) for n in progress.get('hydraulic_sections', {}).get('nodes', [])}
    nodes = []
    for n in h['nodes']:
        if len(n) < 5:
            raise ValueError('invalid hydraulic node')
        r, c, stage = int(n[0]), int(n[1]), float(n[2])
        point(state, [[r, c]])
        if not np.isfinite([stage, float(n[3]), float(n[4])]).all():
            raise ValueError('nonfinite hydraulic node')
        # The solver saves depth against its section bed, including subgrid beds.
        section = sections.get((r, c))
        bed, width = section if section is not None else (stage - float(n[3]), None)
        if width is not None and (not np.isfinite([bed, width]).all() or width <= 0):
            raise ValueError('invalid saved hydraulic section')
        nodes.append((r, c, stage, bed, float(n[4]), width))
    return h, nodes


def routes(progress, h):
    paths = progress.get('routes', [])
    shares = (h or {}).get('actual_shares', progress.get('actual_shares'))
    if shares is None:
        return []
    if len(paths) != len(shares):
        raise ValueError('route and actual share count mismatch')
    return [route for route, share in zip(paths, shares) if float(share) > 0]


def mouth_bounds(state, active):
    cells = [cell for route in active for cell in route]
    if not cells:
        cells = [[state.bed_m.shape[0]//2, state.bed_m.shape[1]//2]]
    x, z = point(state, cells)
    cx, cz = (min(x)+max(x))/2, (min(z)+max(z))/2
    span = max(10., max(x)-min(x)+1., max(z)-min(z)+1.)
    return (cx-span/2, cx+span/2, cz+span/2, cz-span/2)


def freshwater(ax, state, active, nodes):
    # A ribbon joins only adjacent saved wet, positive-flow nodes with saved widths.
    by_cell = {(r, c): (stage, bed, q, width) for r, c, stage, bed, q, width in nodes}
    wet_cells, segments = set(), 0
    for route in active:
        for a, b in zip(route, route[1:]):
            a, b = tuple(a), tuple(b)
            if a not in by_cell or b not in by_cell:
                continue
            sa, sb = by_cell[a], by_cell[b]
            if not all(s[0] > s[1] and s[2] > 0 and s[3] is not None and state.valid_mask[cell]
                       for cell, s in ((a, sa), (b, sb))):
                continue
            if abs(a[0]-b[0])+abs(a[1]-b[1]) != 1:
                continue
            x, z = point(state, [a, b]); direction = np.array([x[1]-x[0], z[1]-z[0]])
            normal = np.array([-direction[1], direction[0]]) / np.linalg.norm(direction)
            # Minimum 100 m visibility, capped at twice the saved subgrid width.
            widths = [min(max(s[3], 100.), 2*s[3])/2000 for s in (sa, sb)]
            p, q = np.array([x[0], z[0]]), np.array([x[1], z[1]])
            ax.add_patch(Polygon([p+normal*widths[0], q+normal*widths[1], q-normal*widths[1], p-normal*widths[0]],
                                 closed=True, facecolor='#25e5f0', edgecolor='none', zorder=4))
            wet_cells.update((a, b)); segments += 1
    return wet_cells, segments


def scenario(p):
    config = p.get('config', {})
    return {'discharge_m3_s': p.get('discharge_m3_s', config.get('discharge_m3_s')),
            'solid_rate_m3_s': p.get('solid_rate_m3_s', config.get('solid_rate_m3_s'))}


def level(p):
    return float(p.get('sea_level_m', p.get('config', {}).get('sea_level_m', 0.0)))


def stamp(state, p):
    return {'physical_time_s': state.time_s, 'equivalent_years': p.get('years', p.get('years_delivered'))}


def save(fig, output, name):
    fig.savefig(output / name, dpi=150, bbox_inches='tight')
    plt.close(fig)
    if (output / name).stat().st_size >= 25_000_000:
        raise ValueError('image exceeds 25 MB')


def render(args):
    manifest, arrays, reference = source()
    loaded = [load_checkpoint(p) for p in (args.initial, args.formed, args.final)]
    for state, _ in loaded:
        check_state(state, reference)
    (initial, pi), (formed, pf), (final, pe) = loaded
    unknown = arrays['unknown_wet'].astype(bool)
    norm = Normalize(vmin=float(min(np.min(initial.bed_m[initial.valid_mask]), np.min(formed.bed_m[formed.valid_mask]))),
                     vmax=float(max(np.max(initial.bed_m[initial.valid_mask]), np.max(formed.bed_m[formed.valid_mask]))))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    fig, axes = plt.subplots(1, 2, figsize=(14, 7), constrained_layout=True)
    for ax, state, p, title in zip(axes, (initial, formed), (pi, pf), ('Initial', 'After equivalent years')):
        terrain(ax, state, unknown, norm, level(p)); decoration(ax)
        ax.set_title(f'{title}\nphysical {state.time_s:g} s; equivalent years {stamp(state, p)["equivalent_years"]}')
    fig.suptitle('01 | 45 km remote-sensing-style terrain colour | 100 m sample; original TD 30 m\nMagenta: unknown wet / invalid; blue: boundary-connected ocean')
    save(fig, output, '01-full-window.png')
    h, nodes = hydraulics(pe, final)
    active = routes(pe, h)
    bounds = mouth_bounds(final, active)
    delta = np.ma.array(formed.bed_m-initial.bed_m, mask=~initial.valid_mask)
    x0, x1, z0, z1 = bounds
    xgrid = (initial.origin_xz_m[0]+np.arange(initial.bed_m.shape[1])*initial.spacing_m)/1000
    zgrid = (initial.origin_xz_m[1]+np.arange(initial.bed_m.shape[0])*initial.spacing_m)/1000
    local = (zgrid[:, None] >= z1) & (zgrid[:, None] <= z0) & (xgrid[None, :] >= x0) & (xgrid[None, :] <= x1) & initial.valid_mask
    local_limit = max(float(np.max(np.abs(delta.data[local]))) if local.any() else 0., 1e-9)
    fig, axes = plt.subplots(1, 3, figsize=(16, 6), constrained_layout=True)
    for ax, state, p, title in zip(axes[:2], (initial, formed), (pi, pf), ('Initial', 'Formed')):
        terrain(ax, state, unknown, norm, level(p))
        ax.set_xlim(x0, x1); ax.set_ylim(z0, z1); decoration(ax, 2); ax.set_title(title)
    im = axes[2].imshow(delta, extent=coords(initial), origin='upper', cmap='RdBu_r', vmin=-local_limit, vmax=local_limit, interpolation='nearest')
    axes[2].set_xlim(x0, x1); axes[2].set_ylim(z0, z1); decoration(axes[2], 2, 'black'); axes[2].set_title('Formed minus initial bed')
    fig.colorbar(im, ax=axes[2], label='Bed change (m)', shrink=.75)
    fig.suptitle('01b | Same-scale local comparison and quantitative bed change | 100 m; TD 30 m\nTerrain light and colour locked to full window; change colour range is local')
    save(fig, output, '01b-local-comparison.png')
    fig, ax = plt.subplots(figsize=(9, 8), constrained_layout=True)
    terrain(ax, final, unknown, norm, level(pe))
    wet, segments = freshwater(ax, final, active, nodes)
    ax.set_xlim(x0, x1); ax.set_ylim(z0, z1)
    decoration(ax, 2)
    ax.set_title('02 | Mouth | final actual raster bed | 100 m; TD 30 m\n' + ('Saved freshwater: original ocean classification unknown; scenario-computed water' if h is not None else 'No saved hydraulics: no actual river wetness evidence'))
    ax.legend(handles=[Patch(color='#b854ae', label='Original unknown water classification'),
                       Patch(color='#2e6b91', label='Boundary-connected ocean'),
                       Patch(color='#25e5f0', label='Computed freshwater; subgrid width enhanced')], loc='lower right', fontsize=8)
    save(fig, output, '02-mouth.png')
    fig = plt.figure(figsize=(15, 8), constrained_layout=True)
    grid = fig.add_gridspec(2, 2)
    ax = fig.add_subplot(grid[:, 0]); profile = fig.add_subplot(grid[0, 1]); history = fig.add_subplot(grid[1, 1])
    vmax = max(float(np.max(np.abs(delta))), 1e-9)
    im = ax.imshow(delta, extent=coords(initial), origin='upper', cmap='RdBu_r', vmin=-vmax, vmax=vmax, interpolation='nearest')
    ax.set_facecolor('#b854ae'); decoration(ax, color='black'); ax.set_title('Formed minus initial bed (m)')
    fig.colorbar(im, ax=ax, label='Bed change (m)', shrink=.75)
    hf, nf = hydraulics(pf, formed)
    active_formed = routes(pf, hf)
    historical_profile = False
    if active_formed:
        route = active_formed[0]; point(formed, route)
        cells = np.asarray(route, int)
        distance = np.r_[0., np.cumsum(np.hypot(np.diff(cells[:, 0]), np.diff(cells[:, 1]))*formed.spacing_m)]/1000
        bed_by_cell = {(r, c): bed for r, c, stage, bed, q, width in nf}
        stage_by_cell = {(r, c): stage for r, c, stage, bed, q, width in nf}
        profile.plot(distance, [bed_by_cell.get(tuple(c), np.nan) for c in cells], label='Saved hydraulic section bed')
        profile.plot(distance, [stage_by_cell.get(tuple(c), np.nan) for c in cells], label='Saved stage')
        route_digest = pf.get('integrated', {}).get('route_data_sha256')
        if route_digest:
            historical, route_meta = load_routes(ROOT/'full-routes-initial')
            if (route_meta['data_sha256'] != route_digest or route_meta['source_identity'] != IDENTITY
                    or route_meta['source_sha256'] != manifest['source_sha256']):
                raise ValueError('historical route source or data mismatch')
            offsets = historical['fine_section_offset_m']
            centre = int(np.argmin(np.abs(offsets)))
            fine_distance = historical['fine_section_distance_m']
            history.plot((fine_distance-fine_distance[-1])/1000,
                         historical['fine_section_bed_m'][:, centre], color='#885522',
                         label='Historical fine centre bed (static)')
            historical_profile = True
        profile.axhline(level(pf), color='steelblue', ls='--', label='Sea level')
        profile.legend(fontsize=8)
    else:
        profile.text(.5, .5, 'No saved effective route / hydraulic profile evidence', ha='center', transform=profile.transAxes, wrap=True)
    if not historical_profile:
        history.text(.5, .5, 'No linked historical fine profile', ha='center', transform=history.transAxes)
    profile.set_title('Mouth: saved section and stage'); profile.set_xlabel('Distance from coarse inlet (km)'); profile.set_ylabel('Elevation (m)'); profile.grid(alpha=.25)
    history.set_title('Historical fine centre bed: static geometry'); history.set_xlabel('Distance upstream of coarse inlet (km)'); history.set_ylabel('Elevation (m)'); history.grid(alpha=.25)
    fig.suptitle('03 | Quantitative change and saved route profile | 100 m sample; original TD 30 m')
    save(fig, output, '03-change-profile.png')
    chain = {'source_manifest': str((SOURCE/'manifest.json').resolve()), 'source_manifest_sha256': digest(SOURCE/'manifest.json'),
             'source_npz': str((SOURCE/'source.npz').resolve()), 'source_sha256': manifest['source_sha256'],
             'source_identity': IDENTITY, 'td_pages': manifest['pages'], 'source_algorithm': manifest['algorithm']}
    inputs = [{'prefix': str(Path(path).resolve()), 'npz_sha256': digest(Path(path).with_suffix('.npz')),
               'json_sha256': digest(Path(path).with_suffix('.json')), 'time': stamp(state, p), 'scenario': scenario(p)}
              for path, (state, p) in zip((args.initial, args.formed, args.final), loaded)]
    common = {'terrain_basis': 'saved marine checkpoint bed, derived from window100-v2 and TD pages; not satellite imagery',
              'source_chain': chain, 'inputs': inputs, 'sampling_m': 100, 'native_td_m': 30,
              'coordinates': 'cell centres [z,x], X east, Z south', 'unknown_wet': 'original unknown ocean classification, not invalid DEM; magenta base, computed freshwater may overlay',
              'algorithms': ['saved marine bed', 'boundary-connected classify_ocean', 'matplotlib LightSource azimuth 315 altitude 45 vertical exaggeration 1'],
              'coverage_status': 'partial'}
    figures = []
    for filename, description, extra in [
        ('01-full-window.png', 'same-source initial and formed 45 km terrain comparison', {'colour_range_m': [norm.vmin, norm.vmax], 'locked_light_and_colour': True}),
        ('01b-local-comparison.png', 'same-scale local comparison and quantitative bed change', {'bounds_xz_km': list(bounds), 'terrain_colour_range_m': [norm.vmin, norm.vmax], 'local_bed_change_range_m': [-local_limit, local_limit]}),
        ('02-mouth.png', 'final mouth raster bed and computed freshwater ribbons on saved effective routes', {'hydraulics_saved': h is not None, 'wet_nodes': len(wet), 'wet_nodes_on_original_unknown': sum(bool(unknown[r, c]) for r, c in wet), 'wet_segments': segments, 'effective_routes': len(active), 'bounds_xz_km': list(bounds), 'display': 'freshwater ribbon joins adjacent saved nodes with stage > section bed and Q > 0; display width max(section width, 100 m), capped at twice section width; subgrid width, not raster river width'}),
        ('03-change-profile.png', 'formed minus initial bed; formed saved route profile', {'bed_change_range_m': [-vmax, vmax], 'profile_route_available': bool(active_formed), 'historical_fine_profile': historical_profile, 'historical_route_data_sha256': pf.get('integrated', {}).get('route_data_sha256') if historical_profile else None, 'profile_limit': 'saved historical fine centre bed and effective route only; no invented upstream extension'})]:
        figures.append({**common, 'file': filename, 'sha256': digest(output/filename), 'description': description, **extra})
    result = {'schema': 'full-publication-atlas-v1', 'status': 'read-only rendering; visual review required', 'figures': figures}
    (output/'manifest.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf8')
    report = (
        '# 三角洲只读重绘\n\n'
        '本图集读取保存检查点，未运行演化、TD 或 GPU。图 1 为同源全域对照，图 1b 为同尺度局部对照及定量床变；地形色阶和光照锁定。\n\n'
        '图 2 紫色为原海洋分类未知，并非 DEM 无效。河水是本情景已算结果，可覆盖紫色底层；仅连接保存有效路线中相邻、正流量且水位高于断面床的节点。水宽属于子格参数，显示宽度至少 100 m 且不超过保存宽度的两倍。海洋采用边界连通分类，未知区域未整体划为海洋。\n\n'
        '图 3 分开显示口门水面与静态历史细床。物理秒、等效年、Q、泥沙及 TD 页摘要见清单。缺失水力数据不构成实际湿区证据；候选分汊未画成水道。\n\n'
        '输入情景及演化阶段以检查点为准；图片核查不代表世界主图或物理机制验收完成。\n'
    )
    (output/'report.md').write_text(report, encoding='utf8')
    if sum(p.stat().st_size for p in output.iterdir()) >= 25_000_000:
        raise ValueError('atlas exceeds 25 MB')
    print(output.resolve())


def smoke(output):
    manifest, arrays, state = source()
    route_path = ROOT/'full-routes-initial'
    routes_data, meta = load_routes(route_path)
    if meta['source_identity'] != IDENTITY or meta['source_sha256'] != manifest['source_sha256'] or meta['state_sha256'] != manifest['state_sha256']:
        raise ValueError('initial route source binding mismatch')
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    fig, ax = plt.subplots(figsize=(5, 5))
    terrain(ax, state, arrays['unknown_wet'].astype(bool), Normalize(vmin=float(state.bed_m.min()), vmax=float(state.bed_m.max())), 0.)
    x, z = point(state, routes_data['main_cells_zx']); ax.plot(x, z, color='yellow', lw=1)
    ax.set_title('Read/plot smoke only: source + initial main route'); decoration(ax)
    save(fig, output, 'smoke.png')
    (output/'report.md').write_text('只读自检：校验正式源、初始实际主路及来源摘要，绘制一张小图；候选分汊未绘制。不是完整案例或验收图集。\n', encoding='utf8')
    print(output.resolve())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initial', help='initial checkpoint prefix')
    parser.add_argument('--formed', help='multi-year checkpoint prefix')
    parser.add_argument('--final', help='post-event checkpoint prefix')
    parser.add_argument('--output', required=True, help='new output directory')
    parser.add_argument('--smoke', action='store_true', help='small official source and initial route read/plot check')
    args = parser.parse_args()
    if args.smoke:
        smoke(args.output)
    else:
        if not all((args.initial, args.formed, args.final)):
            parser.error('--initial, --formed and --final are required unless --smoke is used')
        render(args)
