"""Render a continuous same-world TD relief sheet and physical supporting maps."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
import numpy as np
from scipy.ndimage import distance_transform_edt, map_coordinates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline import terrain_map_style as style
from terrain_pipeline.world_acceptance_delta import sha256

PAPER = '#f6f3e9'
WATER = '#5a9fc1'
SNOW_THRESHOLD_MM = 10.
SEASONAL_SNOW_ALPHA = .35
SEASONAL_SNOW_RGB = np.array([.82, .94, 1.])
plt.rcParams.update({'font.family': ['Microsoft YaHei', 'DejaVu Sans'], 'axes.unicode_minus': False,
    'figure.facecolor': PAPER, 'axes.facecolor': PAPER, 'text.color': '#35423a', 'axes.labelcolor': '#4b554d',
    'xtick.color': '#697267', 'ytick.color': '#697267', 'axes.edgecolor': '#a9afa2', 'font.size': 10})


def extent(origin, shape, spacing):
    x, z = origin
    h, w = shape
    return [(x-spacing/2)/1000, (x+(w-.5)*spacing)/1000,
            (z+(h-.5)*spacing)/1000, (z-spacing/2)/1000]


def terrain_rgb(bed, spacing, vegetation, snow, ocean, lake, *, perennial_mask=None):
    """Declared natural tint driven by physical cover fields, under real hillshade."""
    cover = np.clip(vegetation, 0., 1.)[..., None]
    rock = np.array([.76, .74, .65])
    green = np.array([.46, .60, .39])
    rgb = rock*(1-cover)+green*cover
    shade = style.physical_hillshade(bed, spacing)
    rgb *= (.72+.34*shade)[..., None]
    perennial = np.zeros_like(bed, bool) if perennial_mask is None else np.asarray(perennial_mask, bool)
    seasonal = (np.asarray(snow) >= SNOW_THRESHOLD_MM) & ~perennial
    rgb[seasonal] = rgb[seasonal]*(1.-SEASONAL_SNOW_ALPHA)+SEASONAL_SNOW_RGB*SEASONAL_SNOW_ALPHA
    rgb[perennial] = np.array([.96, .98, .98])*(.72+.34*shade[perennial, None])
    depth = np.maximum(-bed, 0.)
    ocean_cmap = LinearSegmentedColormap.from_list('quiet-sea', ['#9ccbd2', '#629fbd', '#487eaa'])
    rgb[ocean] = ocean_cmap(np.clip(depth[ocean]/300., 0., 1.))[..., :3]
    rgb[lake] = np.array([.38, .66, .76])
    return np.clip(rgb, 0., 1.)


def snow_cartography(monthly_swe, ocean, lake, spacing_m):
    """Single-year persistence is a display category, never permanent snow."""
    monthly = np.asarray(monthly_swe, float)
    if monthly.ndim != 3 or monthly.shape[0] != 12:
        raise ValueError('snow cartography requires 12 saved monthly SWE fields')
    land = ~np.asarray(ocean, bool) & ~np.asarray(lake, bool)
    perennial = np.all(monthly >= SNOW_THRESHOLD_MM, axis=0) & land
    records = []
    for month, field in enumerate(monthly, 1):
        seasonal = (field >= SNOW_THRESHOLD_MM) & ~perennial & land
        records.append(dict(month=month, seasonal_cells=int(seasonal.sum()),
            seasonal_area_km2=float(seasonal.sum()*spacing_m**2/1.e6),
            seasonal_fraction_of_display_land=float(seasonal.sum()/max(1, land.sum()))))
    return perennial, dict(threshold_swe_mm=SNOW_THRESHOLD_MM, seasonal_alpha=SEASONAL_SNOW_ALPHA,
        seasonal_colour_rgb=SEASONAL_SNOW_RGB.tolist(), period='12 saved month-end SWE states of the final modeled year',
        perennial_candidate_rule='All 12 saved months >=10 mm SWE, excluding displayed ocean/lakes; single-year retained snow only',
        perennial_label='全年残留积雪（本模拟年）', permanent_snow_status='Not certified; requires independently verified multi-year persistence field',
        perennial_candidate_cells=int(perennial.sum()), perennial_candidate_area_km2=float(perennial.sum()*spacing_m**2/1.e6),
        display_land_cells=int(land.sum()), months=records, source_spacing_m=float(spacing_m),
        native_detail_sampling='Monthly SWE bilinear interpolation and categorical single-year retention nearest interpolation from 90 m; no 30 m snow simulation')


def atlas_manifest(args, meta, records, snow_report):
    result = dict(schema='same-world-acceptance-render-v2', river_threshold_m3_s=float(args.river_threshold_m3_s), source_product=dict(path=str(args.product.resolve()), sha256=sha256(args.product)), source_metadata=meta, figures=records,
        cartography='Cream paper; actual vegetation/rock tint; seasonal SWE threshold translucent cool-white/cyan mask with alpha 0.35 over physical terrain_map_style hillshade; single-year retained snow white plus outline; vertical exaggeration 1; no generated detail; actual receiver topology with enlarged display width',
        snow_cartography=snow_report,
        coverage_status_definitions=dict(complete_in_window='Named field is fully available in the displayed window; not a validation of physical realism',
            partial='A stated spatial/time/state boundary prevents a complete interpretation', mechanism_only='Local mechanism or planning evidence; not acceptance of final landform or continental TD coverage', not_available='Required saved field or consumer is unavailable'))
    if args.delta:
        result['source_delta'] = dict(path=str(args.delta.resolve()), sha256=sha256(args.delta))
    return result


def decorate(ax, box):
    span = box[1]-box[0]
    ax.set_xlim(box[:2])
    ax.set_ylim(box[2:])
    ax.set_aspect('equal')
    ax.set_xlabel('世界 X / km', labelpad=25)
    ax.set_ylabel('世界 Z / km', labelpad=10)
    style.draw_metre_graticule(ax, step_km=style.nice_graticule_step_km(span), colour='#667361')
    ax.set_xticks([])
    ax.set_yticks([])
    style.draw_scale_bar(ax, style.nice_scale_length_km(span))
    style.draw_north_arrow(ax)


def river_collection(product, threshold, *, omit_nodes=(), affected=None):
    receiver = np.asarray(product['receiver'], int).ravel()
    q = np.asarray(product['discharge_m3_s'], float).ravel()
    ocean = np.asarray(product['ocean_mask'], bool).ravel()
    source = np.flatnonzero((receiver >= 0) & (receiver < len(q)) & (q >= threshold) & ~ocean)
    if len(omit_nodes):
        source = source[~np.isin(source, omit_nodes)]
    target = receiver[source]
    xy = np.column_stack([np.asarray(product['node_x_m']).ravel(), np.asarray(product['node_z_m']).ravel()])/1000.
    segments = np.stack((xy[source], xy[target]), axis=1)
    widths = np.clip(.3+.42*np.log10(1+q[source]), .3, 1.8)
    colours = WATER if affected is None else np.where(np.asarray(affected, bool).ravel()[source], '#b56842', WATER)
    return LineCollection(segments, colors=colours, linewidths=widths, capstyle='round', joinstyle='round', zorder=10)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--delta', type=Path)
    parser.add_argument('--macro-preview', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--span-km', type=float, default=64.)
    parser.add_argument('--pixels', type=int, default=3600)
    parser.add_argument('--river-threshold-m3-s', type=float, default=2.)
    parser.add_argument('--only-delta-detail', action='store_true', help='Update the delta detail and its manifest entry in an existing atlas')
    parser.add_argument('--snow-month', type=int, choices=range(1, 13), default=12)
    parser.add_argument('--snow-overlay-only', action='store_true', help='Render selected month, July, and their geographic snow comparison only')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    with np.load(args.product, allow_pickle=False) as data:
        product = dict(data)
    meta = json.loads(product['metadata_json'].item())
    origin = np.asarray(meta['origin_xz_m'], float)
    spacing = float(meta['spacing_m'])
    bed = np.asarray(product['bed_m'], float)
    shape = bed.shape
    fullbox = extent(origin, shape, spacing)
    centre = np.array([(fullbox[0]+fullbox[1])/2, (fullbox[2]+fullbox[3])/2])
    half = args.span_km/2
    box = [centre[0]-half, centre[0]+half, centre[1]+half, centre[1]-half]
    requested = meta.get('source_terrain', {}).get('requested_view_bounds_m')
    if requested is not None and np.isclose((requested[2]-requested[0])/1000., args.span_km):
        box = [requested[0]/1000., requested[2]/1000., requested[3]/1000., requested[1]/1000.]
    monthly_snow = np.asarray(product['monthly_snow_swe_mm'])
    perennial, snow_report = snow_cartography(monthly_snow, product['ocean_mask'], product['lake_mask'], spacing)
    snow_report['selected_month'] = args.snow_month
    rgb = terrain_rgb(bed, spacing, product['vegetation_fraction'], monthly_snow[args.snow_month-1], product['ocean_mask'], product['lake_mask'], perennial_mask=perennial)
    delta = None
    omit_nodes = []
    if args.delta:
        with np.load(args.delta, allow_pickle=False) as data:
            delta = dict(data)
        dm = json.loads(delta['metadata_json'].item())
        dspacing, dorigin = float(dm['spacing_m']), np.asarray(dm['origin_xz_m'])
        dshape = delta['final_bed_m'].shape
        rr, cc = np.indices(dshape)
        worldx, worldz = dorigin[0]+cc*dspacing, dorigin[1]+rr*dspacing
        coord = np.array([(worldz-origin[1])/spacing, (worldx-origin[0])/spacing])
        vegetation = map_coordinates(np.asarray(product['vegetation_fraction'], float), coord, order=1, mode='nearest')
        snow = map_coordinates(np.asarray(monthly_snow[args.snow_month-1], float), coord, order=1, mode='nearest')
        native_perennial = map_coordinates(perennial.astype(float), coord, order=0, mode='nearest') > .5
        native_lake = map_coordinates(np.asarray(product['lake_mask'], float), coord, order=0, mode='nearest') > .5
        drgb = terrain_rgb(delta['final_bed_m'], dspacing, vegetation, snow, delta['ocean_mask'], native_lake, perennial_mask=native_perennial)
        drgb[delta['wet_mask'] & ~delta['ocean_mask']] = np.array([.36, .63, .74])
        detail_rgb = terrain_rgb(delta['final_bed_m'], dspacing, vegetation, snow, delta['ocean_mask'], np.zeros(dshape, bool), perennial_mask=native_perennial)
        coarse_lake = np.asarray(product['lake_mask'], bool)
        if coarse_lake.any():
            lake_distance, lake_nearest = distance_transform_edt(~coarse_lake, return_indices=True)
            coarse_surface = np.asarray(product['elevation_m'])+np.asarray(product['lake_depth_m'])
            nearest_surface = coarse_surface[lake_nearest[0], lake_nearest[1]]
            projected_surface = map_coordinates(nearest_surface, coord, order=0, mode='nearest')
            projected_support = map_coordinates(lake_distance*spacing, coord, order=0, mode='nearest') <= spacing
            projected_lake = projected_support & (delta['final_bed_m'] < projected_surface) & ~delta['ocean_mask']
        else:
            projected_lake = np.zeros(dshape, bool)
        detail_rgb[projected_lake] = np.array([.42, .68, .77])
        detail_rgb[delta['wet_mask'] & ~delta['ocean_mask']] = np.array([.36, .63, .74])
        # The fine native TD patch replaces its coarse parent in world space.
        # A narrow cartographic edge blend prevents a rectangular shade boundary.
        edge_distance = np.minimum.reduce([rr, cc, dshape[0]-1-rr, dshape[1]-1-cc])
        delta_alpha = np.clip(edge_distance/8., 0., 1.)
        dbox = extent(dorigin, dshape, dspacing)
        chain = dm['source_graph_path_nodes']
        inlet_index = chain.index(dm['inlet_node'])
        omit_nodes = chain[inlet_index:]
    previous_manifest = None
    if args.only_delta_detail:
        previous_manifest = json.loads((args.output/'manifest.json').read_text(encoding='utf-8'))
    records = [] if previous_manifest is None else [record for record in previous_manifest['figures'] if record['file'] != 'same_world_delta_30m.png']

    def save(fig, name, fields, native_spacing, bounds, *, coverage='complete_in_window', basis='same-world Terrain Diffusion native terrain and saved process product', algorithms=None, notes=None):
        if args.only_delta_detail and name != 'same_world_delta_30m':
            plt.close(fig)
            return
        path = args.output / f'{name}.png'
        fig.savefig(path, dpi=args.pixels/12, facecolor=PAPER)
        plt.close(fig)
        records.append(dict(file=path.name, fields=fields, spacing_m=native_spacing, extent_world_km=bounds, sha256=sha256(path), terrain_basis=basis,
            algorithms=algorithms or meta.get('algorithms', []), time=meta.get('time', {}), coverage_status=coverage, coverage_meaning=notes or 'Named saved fields are available throughout this map window; availability is not a calibration claim.'))
        print(path, flush=True)

    snow_handles = [Patch(facecolor='#d1f0ff', edgecolor='#a2c5d1', alpha=SEASONAL_SNOW_ALPHA, label='季节积雪（半透明）'),
                    Patch(facecolor='#f5fafa', edgecolor='#768b93', label='全年残留积雪（本模拟年）')]

    def surface_map(ax, month):
        field = monthly_snow[month-1]
        image = terrain_rgb(bed, spacing, product['vegetation_fraction'], field, product['ocean_mask'], product['lake_mask'], perennial_mask=perennial)
        ax.imshow(image, extent=fullbox, interpolation='bilinear')
        if delta:
            native_snow = map_coordinates(np.asarray(field, float), coord, order=1, mode='nearest')
            native_image = terrain_rgb(delta['final_bed_m'], dspacing, vegetation, native_snow, delta['ocean_mask'], native_lake, perennial_mask=native_perennial)
            native_image[delta['wet_mask'] & ~delta['ocean_mask']] = np.array([.36, .63, .74])
            ax.imshow(np.dstack((native_image, delta_alpha)), extent=dbox, interpolation='nearest', zorder=7)
            ax.add_patch(Rectangle((dbox[0], dbox[3]), dbox[1]-dbox[0], dbox[2]-dbox[3], fill=False, edgecolor='#586b56', linewidth=.75, linestyle='--', zorder=9))
        if perennial.any():
            ax.contour((origin[0]+np.arange(shape[1])*spacing)/1000., (origin[1]+np.arange(shape[0])*spacing)/1000., perennial.astype(float), levels=[.5], colors=['#768b93'], linewidths=.65, zorder=12)
        ax.add_collection(river_collection(product, args.river_threshold_m3_s, omit_nodes=omit_nodes))
        decorate(ax, box)

    def surface_sheet(month, name):
        fig, ax = plt.subplots(figsize=(12, 12))
        fig.subplots_adjust(left=.085, right=.97, top=.92, bottom=.17)
        surface_map(ax, month)
        fig.text(.085, .965, f'山川形意  /  {month} 月积雪图示', fontsize=22)
        fig.text(.085, .935, f'Terrain Diffusion · 世界种子 20261020 · {args.span_km:g} × {args.span_km:g} km · 地形与积雪采样 {spacing:g} m', fontsize=10)
        handles = [Patch(color='#809967', label='实际植被覆盖'), Patch(color='#b9b5a0', label='低植被 / 岩土'), *snow_handles, Patch(color=WATER, label='海洋 / 湖泊'), Line2D([0], [0], color=WATER, label=f'计算河网 Q ≥ {args.river_threshold_m3_s:g} m³/s（线宽放大）')]
        fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.53, .060), ncol=3, frameon=False, fontsize=9)
        fig.text(.5, .034, f'SWE ≥ {SNOW_THRESHOLD_MM:g} mm · 全年残留区 {snow_report["perennial_candidate_area_km2"]:g} km²（仅本模拟年，不据此认定永久积雪）', ha='center', fontsize=8)
        fig.text(.5, .015, '积雪为半透明地理遮罩；30 m 河口积雪由 90 m 保存场插值。模型合成图，非观测。', ha='center', fontsize=8)
        save(fig, name, ['bed_m', 'vegetation_fraction', f'monthly_snow_swe_mm[{month-1}]', 'all_12_months_swe_persistence', 'ocean_mask', 'lake_mask', 'receiver', 'discharge_m3_s', 'same-world-delta'], spacing, box,
             coverage='partial', notes='Terrain and cover fields span the full window; selected month-end SWE is a translucent geographic overlay. Single-year retained snow is not certified permanent snow. Hydrology retains unknown external inflow boundaries; river display widths are enlarged. Delta snow is interpolated from 90 m.')
        if not args.only_delta_detail:
            records[-1]['snow'] = dict(snow_report['months'][month-1], perennial_candidate_cells=snow_report['perennial_candidate_cells'], threshold_swe_mm=SNOW_THRESHOLD_MM, seasonal_alpha=SEASONAL_SNOW_ALPHA)

    surface_sheet(args.snow_month, 'world_surface_64km')
    if args.snow_overlay_only:
        surface_sheet(7, 'world_surface_july')
        fig, axes = plt.subplots(1, 2, figsize=(12, 7))
        fig.subplots_adjust(left=.065, right=.95, top=.86, bottom=.20, wspace=.17)
        for ax, month in zip(axes, (args.snow_month, 7)):
            surface_map(ax, month)
            ax.set_title(f'{month} 月末', pad=15)
        fig.suptitle('同一世界  /  积雪季节地理遮罩', fontsize=19, y=.97)
        fig.legend(handles=snow_handles, loc='lower center', bbox_to_anchor=(.5, .06), ncol=2, frameon=False, fontsize=10)
        fig.text(.5, .027, f'同一地形与覆盖背景，仅对比月末积雪；阈值 {SNOW_THRESHOLD_MM:g} mm SWE，遮罩不透明度 {SEASONAL_SNOW_ALPHA:.0%}。', ha='center', fontsize=9)
        save(fig, 'seasonal_snow_geographic_comparison', [f'monthly_snow_swe_mm[{args.snow_month-1}]', 'monthly_snow_swe_mm[6]', 'all_12_months_swe_persistence'], spacing, box,
             notes='Same terrain, final-year vegetation, hydrology and light; only month-end seasonal SWE overlay changes. Single-year persistence is not permanent snow or a climate-change comparison.')
        manifest = atlas_manifest(args, meta, records, snow_report)
        (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps(snow_report, indent=2, ensure_ascii=False), flush=True)
        return
    if delta:
        fig, ax = plt.subplots(figsize=(12, 12))
        fig.subplots_adjust(left=.085, right=.97, top=.91, bottom=.15)
        ax.imshow(detail_rgb, extent=dbox, interpolation='nearest')
        ax.add_collection(river_collection(product, args.river_threshold_m3_s, omit_nodes=omit_nodes))
        # Receiver edges through a stored lake can have low node Q when pool
        # water is released at its anchor. Draw the saved upstream chain as
        # context, without assigning the lake's discharge to those low-Q nodes.
        context_nodes = np.asarray(dm['source_graph_path_nodes'][:inlet_index+1], int)
        if len(context_nodes) > 1:
            xy = np.column_stack((np.asarray(product['node_x_m']).ravel(), np.asarray(product['node_z_m']).ravel()))/1000.
            context_xy = xy[context_nodes]
            ax.plot(context_xy[:, 0], context_xy[:, 1], color='#4e8da9', linewidth=.8, linestyle=(0, (2, 1)), zorder=11)
        decorate(ax, dbox)
        fig.text(.085, .96, '同一世界的河口  /  30 m 局部求解', fontsize=20)
        fig.text(.085, .928, f'入口年均 Q = {dm["actual_upstream_q_m3_s"]:.2f} m³/s · 声明泥沙浓度 {dm["concentration_kg_m3"]:g} kg/m³ · 恒定入口 {dm["duration_seconds"]/86400:.1f} 天', fontsize=10)
        fig.text(.5, .060, '深蓝面为 30 m 求解湿区；浅蓝湖面为 90 m 保存水位投影到原生地形，并非重算 30 m 蓄水。', ha='center', fontsize=9)
        fig.text(.5, .041, '虚线为穿湖的原始 receiver 路径，不额外赋予流量；湖泊原有体积账本保持不变。', ha='center', fontsize=9)
        fig.text(.5, .022, '潮沟为同源近岸地形上的显式初始施工；本图海面 0 m，未运行周期潮汐。', ha='center', fontsize=9)
        save(fig, 'same_world_delta_30m', ['original_bed_m', 'constructed_bed_m', 'final_bed_m', 'wet_mask', 'world.lake_mask', 'world.elevation_m+lake_depth_m', 'world.receiver'], dspacing, dbox, coverage='mechanism_only', algorithms=dm['algorithms'], notes='Engineering distributary excavation plus conservative local morphodynamics on same-world TD; prescribed sediment concentration is not upstream erosion. Dark water is native solved wet area; light lake water is saved 90 m water-level projection onto native bed, with unchanged 90 m storage. Fine river lines are computed topology and dashed upstream chain assigns no additional Q.')
        records[-1]['field_spacings_m'] = dict(terrain_and_delta=dspacing, vegetation_snow_and_topology=spacing)
        records[-1]['neighbor_lakes'] = dict(method='Saved 90 m lake surface=elevation+lake_depth, nearest lake surface projected onto native final bed; support limited to actual 90 m lake mask plus one 90 m cell',
            projected_visible_area_m2=float(projected_lake.sum()*dspacing**2), storage='Original 90 m storage ledger unchanged; no rerouting or 30 m storage conservation claim',
            upstream_context='Saved receiver chain before inlet, including low-Q lake carry nodes; dashed line assigns no additional discharge')
        records[-1]['tidal_state'] = 'Explicit initial nearshore/tidal creek construction, prescribed constant sea stage 0 m; no periodic tidal hydrodynamics or emergent platform claim'
        records[-1]['time'] = dict(local_duration_seconds=dm['duration_seconds'], forcing=dm.get('forcing_time', 'Saved annual mean Q held constant'))
        fig, ax = plt.subplots(figsize=(12, 12))
        im = ax.imshow(delta['bed_change_m'], extent=dbox, cmap='BrBG', vmin=-max(.1, float(np.abs(delta['bed_change_m']).max())), vmax=max(.1, float(np.abs(delta['bed_change_m']).max())), interpolation='nearest')
        decorate(ax, dbox)
        ax.set_title('河口自然模拟床面变化 / m（不含初始工程开挖）', pad=18)
        fig.colorbar(im, ax=ax, fraction=.035, pad=.03, label='m')
        save(fig, 'delta_bed_change', ['bed_change_m'], dspacing, dbox, coverage='mechanism_only', algorithms=dm['algorithms'], notes='Natural simulation change after separately recorded engineering construction; local inlet Q and declared concentration.')
    for field, title, unit, cmap in [('annual_precipitation_mm', '年降水', 'mm / year', 'YlGnBu'), ('annual_temperature_c', '年平均气温', '°C', 'RdYlBu_r'), ('elevation_m', '实际地表高程', 'm', 'terrain'), ('soil_depth_m', '土壤深度', 'm', 'YlGn')]:
        fig, ax = plt.subplots(figsize=(12, 12))
        fig.subplots_adjust(left=.08, right=.88, top=.92, bottom=.09)
        im = ax.imshow(product[field], extent=fullbox, cmap=cmap, interpolation='nearest')
        decorate(ax, box)
        ax.set_title(f'同源世界  /  {title}', pad=18, fontsize=18)
        fig.colorbar(im, ax=ax, fraction=.035, pad=.035, label=unit)
        fig.text(.5, .027, f'世界种子 20261020 · 采样 {spacing:g} m · 模型场，非观测', ha='center', fontsize=9)
        save(fig, field, [field], spacing, box)
    if 'monthly_snow_swe_mm' in product:
        fig, axes = plt.subplots(1, 2, figsize=(12, 7))
        fig.subplots_adjust(left=.065, right=.9, top=.87, bottom=.16, wspace=.16)
        snow_fields = np.asarray(product['monthly_snow_swe_mm'])[[0, 6]]
        maximum = max(1., float(snow_fields.max()))
        for ax, field, month in zip(axes, snow_fields, ['一月末', '七月末']):
            im = ax.imshow(np.ma.masked_where(product['ocean_mask'], field), extent=fullbox, cmap='Blues', vmin=0., vmax=maximum, interpolation='nearest')
            decorate(ax, box)
            ax.set_title(month, pad=14)
        fig.suptitle('同一年内的积雪季节对比', fontsize=18, y=.97)
        cax = fig.add_axes([.93, .23, .014, .55])
        fig.colorbar(im, cax=cax, label='雪水当量 / mm')
        fig.text(.5, .045, '相同世界、相同年份，月末雪水当量；季节差异不代表长期气候变化。', ha='center', fontsize=9)
        save(fig, 'seasonal_snow_january_july', ['monthly_snow_swe_mm[0]', 'monthly_snow_swe_mm[6]'], spacing, box, notes='Month-end stores for January and July of the same modeled year, using shared colour scale; seasonal contrast, not climate change.')
    if 'unknown_external_inflow_mask' in product:
        fig, ax = plt.subplots(figsize=(12, 12))
        fig.subplots_adjust(left=.08, right=.97, top=.9, bottom=.11)
        pale = rgb*.3+np.array([.94, .94, .9])*.7
        ax.imshow(pale, extent=fullbox, interpolation='bilinear')
        unknown = np.asarray(product['unknown_external_inflow_mask'], bool)
        ax.imshow(np.dstack((np.full(shape, .76), np.full(shape, .45), np.full(shape, .28), unknown*.10)), extent=fullbox, interpolation='nearest')
        ax.add_collection(river_collection(product, args.river_threshold_m3_s, affected=unknown))
        q = np.asarray(product['discharge_m3_s']).ravel()
        river_nodes = np.flatnonzero((q >= args.river_threshold_m3_s) & ~np.asarray(product['ocean_mask']).ravel())
        xy = np.column_stack((np.asarray(product['node_x_m']).ravel(), np.asarray(product['node_z_m']).ravel()))/1000.
        labelled = []
        for node in river_nodes[np.argsort(q[river_nodes])[::-1]]:
            point = xy[node]
            if all(np.linalg.norm(point-previous) > args.span_km*.12 for previous in labelled):
                ax.annotate(f'{q[node]:.1f} m³/s', point, xytext=(5, 5), textcoords='offset points', fontsize=8,
                            color='#8d4a2f' if unknown.ravel()[node] else '#336c87',
                            bbox=dict(facecolor=PAPER, edgecolor='none', alpha=.85, pad=1.5), zorder=15)
                labelled.append(point)
            if len(labelled) >= 8:
                break
        decorate(ax, box)
        ax.set_title('水文边界核查  /  流量与未知外部来水', fontsize=18, pad=20)
        fig.legend(handles=[Line2D([0], [0], color=WATER, label='计算河网'), Line2D([0], [0], color='#b56842', label='受未知边界来水影响的河段'), Patch(facecolor='#d9b59b', alpha=.5, label='边界影响传播范围')], loc='lower center', bbox_to_anchor=(.5, .055), ncol=3, frameon=False, fontsize=9)
        fig.text(.5, .025, f'仅显示 Q ≥ {args.river_threshold_m3_s:g} m³/s；线宽按 log(1+Q) 放大，非实际湿宽。裁剪陆地出口不是海洋。', ha='center', fontsize=9)
        save(fig, 'hydrology_boundary_verification', ['receiver', 'discharge_m3_s', 'unknown_external_inflow_mask'], spacing, box, coverage='partial', notes='Q is computed with local finite-domain runoff only. Orange source nodes and receiver reaches inherit unknown external-inflow influence; blue does not prove an externally complete catchment.')
    if args.macro_preview and not args.only_delta_detail:
        with np.load(args.macro_preview, allow_pickle=False) as data:
            mm = json.loads(data['metadata_json'].item())
        frame = mm['world_frame_bounds_m']
        mbox = [frame[0]/1000, frame[2]/1000, frame[3]/1000, frame[1]/1000]
        from terrain_pipeline.td_source import macro_fields
        mspacing = (frame[2]-frame[0])/512
        mx = frame[0]+(np.arange(512)+.5)*mspacing
        mz = frame[1]+(np.arange(512)+.5)*mspacing
        macro = macro_fields(mx[None, :], mz[:, None], seed=20261020)
        macro_source_path = args.output/'macro_continent_planning_source.npz'
        macro_metadata = dict(algorithm='world_acceptance_terrain.macro_fields', world_seed=20261020, world_frame_bounds_m=frame,
            origin_xz_m=[float(mx[0]), float(mz[0])], spacing_m=mspacing, shape_zx=[512, 512], terrain_basis='Macro conditioning only, not Terrain Diffusion',
            parameter_source_path=str(args.macro_preview.resolve()), parameter_source_sha256=sha256(args.macro_preview))
        np.savez_compressed(macro_source_path, **macro, metadata_json=np.array(json.dumps(macro_metadata)))
        mrgb = terrain_rgb(macro['elevation_m'], mspacing, np.full_like(macro['elevation_m'], .45), np.zeros_like(macro['elevation_m']), macro['ocean_mask'], np.zeros_like(macro['ocean_mask']))
        fig, ax = plt.subplots(figsize=(12, 12))
        fig.subplots_adjust(left=.08, right=.97, top=.89, bottom=.10)
        ax.imshow(mrgb, extent=mbox, interpolation='bilinear')
        ax.add_patch(Rectangle((box[0], box[3]), box[1]-box[0], box[2]-box[3], fill=False, edgecolor='#a84d37', linewidth=2., zorder=10))
        ax.text(box[0]+3, box[3]-6, '64 km TD 验收窗口', color='#8a3e2b', fontsize=11, zorder=11)
        decorate(ax, mbox)
        ax.set_title('大陆布局规划  /  500 km 定位背景', fontsize=20, pad=22)
        fig.text(.5, .037, '本图仅为宏观条件场与窗口定位，不是 500 km Terrain Diffusion 成品，也不计入 TD 算法验收。', ha='center', fontsize=9)
        save(fig, 'continent_planning_context', ['macro.elevation_m', 'macro.ocean_mask', '64km_view_bounds'], mspacing, mbox, coverage='mechanism_only', basis='Macro conditioning layout only; explicitly excluded from Terrain Diffusion acceptance', algorithms=[macro_metadata['algorithm']], notes='Full-frame macro_fields evaluated at absolute world cell centres, saved separately. Planning context only. The red rectangle locates the same 64 km TD sample; the surrounding 500 km has not been generated or accepted as TD.')
    manifest = atlas_manifest(args, meta, records, snow_report)
    if args.macro_preview and not args.only_delta_detail:
        manifest['source_macro_planning_only'] = dict(path=str(macro_source_path.resolve()), sha256=sha256(macro_source_path), metadata=macro_metadata)
    elif previous_manifest is not None and 'source_macro_planning_only' in previous_manifest:
        manifest['source_macro_planning_only'] = previous_manifest['source_macro_planning_only']
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
