"""Same morphology kernel on a bounded, fully covered saved TD region (CPU only)."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

import numpy as np
import psutil
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from terrain_pipeline import delta_network_site as site
from terrain_pipeline import delta_network_morphology as morphology
from terrain_pipeline import delta_network_skeleton_v3 as skeleton
import run_delta_network_v1 as common
import run_delta_network_v4 as rendering


def scenario():
    """Declared alongshore case, with space reserved beyond channel growth for mouths."""
    spec = site.SiteSpec(anchor_world_m=(0., 5000.), alpha_deg=90., u0_m=-18000.,
        v0_m=-61000., nu=740, nv=1220, spacing_m=100.)
    params = morphology.parameters('base', window_u_m=(-18000., 56000.),
        window_v_m=(-61000., 61000.), boundary_margin_m=6000., r_young=110000.,
        max_lateral_m=56000., n_lobes=5, spread_deg=38., r_decay=.995, share_ratio=.85,
        spacing_plain_m=8000., spacing_front_m=4000., beta=18., step_m=400.,
        q_total=30000., max_steps=5000, c_goal=1.6, c_coast=.1,
        forward_deg=85., fan_half_deg=85.)
    plain = morphology.PlainParameters(catchment_km2=1200000., denudation_m=1.6,
        delivery_fraction=.3, shelf_depth_bound_m=2000.,
        landward_max_distance_from_coast_m=24000., longshore_transport_m=78000.)
    return spec, params, plain


def connected_extent(mask, spacing):
    """Measure one broad connected body, never a disconnected bounding box."""
    labels, count = ndi.label(mask)
    if not count:
        return dict(area_km2=0., span_u_v_km=[0., 0.], touches_window=False)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    body = labels == sizes.argmax()
    points = np.argwhere(body)
    return dict(area_km2=float(body.sum()*spacing**2/1e6),
        span_u_v_km=(np.ptp(points, axis=0)*spacing/1000.).tolist(),
        touches_window=bool(body[[0,-1],:].any() or body[:,[0,-1]].any()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / '.scratch/delta-completion-20261107/hundred-km-v1')
    parser.add_argument('--figs', type=Path, default=ROOT / '验收图片/百公里复杂三角洲-20261107')
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError('use a new output directory: ' + str(args.out))
    started = time.perf_counter()
    spec, params, plain_params = scenario()
    td_bed, td_ocean, valid = site.sample_td(spec, str(ROOT / site.TD_DIR))
    if not valid.all():
        raise ValueError('scenario exceeds the known saved TD support')
    print('known TD sampled; building morphology', flush=True)
    graph, terrain, terrain_params = morphology.build(spec, td_bed, td_ocean,
        delta_params=params, plain_params=plain_params)
    validation = skeleton.validate_graph(graph)
    if not validation['ok']:
        raise ValueError(validation)
    audit = morphology.geometry_audit(spec, graph, terrain, terrain_params)
    if not audit['ok']:
        raise ValueError(audit)
    if max(m['raster_depth_m'] for m in audit['mouths'])>100.:
        raise ValueError('mouth reaches a deep cliff; reject this geological front')
    mouth_span = float(np.ptp(graph.node_uv[graph.mouth_nodes, 1]))
    plain = terrain['whole_plain']
    footprint = plain['active'] & (plain['bed'] >= .02) & (plain['bed'] <= 8.)
    interior = ndi.distance_transform_edt(np.pad(footprint, 1))[1:-1,1:-1]*spec.spacing_m
    body_extent = connected_extent(footprint, spec.spacing_m)
    core_extent = connected_extent(interior >= 2000., spec.spacing_m)
    if max(core_extent['span_u_v_km']) < 100.:
        raise ValueError(f'connected plain interior does not reach 100 km: {core_extent}')
    base = terrain['whole_plain']['base']
    change = terrain['bed'] - base
    cell_area = spec.spacing_m ** 2
    metrics = dict(validation=validation, geometry_audit=audit,
        skeleton=skeleton.skeleton_metrics_v3(graph),
        whole_plain=morphology.whole_plain_metrics(spec, graph, terrain, td_ocean),
        connected_plain=body_extent, connected_plain_2km_interior=core_extent,
        hundred_km_evidence='connected interior at least 2 km from the plain edge; original and filled lowland surface',
        actual_mouth_alongshore_span_km=mouth_span/1000.,
        graph_world_span_km=np.ptp(np.column_stack(site.local_to_world(spec,
            graph.pts_uv[:, 0], graph.pts_uv[:, 1])), axis=0).tolist(),
        construction_fill_bulk_m3=float(np.maximum(change, 0.).sum()*cell_area),
        construction_cut_bulk_m3=float(np.maximum(-change, 0.).sum()*cell_area),
        event_deposition_solid_m3=0., td_valid_fraction=float(valid.mean()))
    metrics['graph_world_span_km'] = [x/1000. for x in metrics['graph_world_span_km']]
    args.out.mkdir(parents=True)
    arrays = dict(bed_dem_float64=terrain['bed'], water_mask=terrain['water'],
        channel_mask=terrain['chan'], tidal_mask=terrain['tidal'], sand_mask=terrain['sand'],
        island_labels=terrain['island_label'], spit_mask=terrain['spit'], valid_mask=valid,
        td_original_bed_m=td_bed, td_ocean_mask=td_ocean, declared_base_bed_m=base,
        construction_reference_bed_m=base,
        geological_plain_bed_m=terrain['whole_plain']['bed'],
        geological_plain_active=terrain['whole_plain']['active'],
        geological_marine_deposit_m=terrain['whole_plain']['deposit'],
        construction_bed_change_m=change,
        water_surface_m=np.where(terrain['chan'], np.maximum(0., terrain['z_plain']-terrain_params.freeboard_m), 0.))
    for name, values in arrays.items():
        np.save(args.out / (name+'.npy'), values)
    serialized = common.graph_dict(graph, spec)
    serialized['construction_profiles'] = graph.construction_profiles
    serialized['flow_semantics'] = 'Q_m3s is design discharge; physical Q requires the coupled event'
    common.write_json(args.out / 'channel_graph.json', serialized)
    common.write_json(args.out / 'metrics.json', metrics)
    common.write_json(args.out / 'geological-ledger.json', terrain['geological_ledger'])
    files = ['delta_network_site.py', 'delta_network_morphology.py', 'delta_network_skeleton.py',
             'delta_network_skeleton_v3.py', 'delta_network_terrain.py',
             'delta_network_terrain_v3.py', 'delta_network_terrain_v4.py', 'large_delta_landform_regional.py']
    manifest = dict(product='complex-delta-hundred-km-morphology-v1', world_seed=morphology.WORLD_SEED,
        source_world_seed=site.WORLD_SEED, site=spec.to_dict(), td_source=common.td_cache_identity(),
        terrain_basis='saved TD mosaic terrain-v3 land, bathymetry and coast; source-controlled geological fill',
        geological_initial_condition=True, params=dict(delta=params.to_dict(),
            terrain=terrain_params.to_dict(), plain=asdict(plain_params)),
        construction_reference=dict(file='construction_reference_bed_m.npy',
            semantics='saved original TD land and bathymetry before source-controlled geological fill and channel excavation'),
        geological_ledger=terrain['geological_ledger'],
        derived_seeds=graph.seeds, metrics=metrics,
        coverage_status='complete_in_window',
        coordinate_note='arrays[row_u,col_v], model X=v,Z=u; site affine transform gives world X,Z',
        declaration='100 m resampling of saved native 30 m TD; geological cut/fill is not event sediment. '
                    'Finite planning domain; no claim of independent tile generation or natural long-term formation.',
        code_sha256={f'terrain_pipeline/{f}':common.sha256_file(ROOT/'terrain_pipeline'/f) for f in files})
    manifest['code_sha256']['tools/run_delta_network_hundred_km.py'] = common.sha256_file(__file__)
    common.write_json(args.out / 'manifest.json', manifest)
    snapshot=args.out/'algorithm-source'
    snapshot.mkdir()
    for filename in files:
        (snapshot/filename).write_bytes((ROOT/'terrain_pipeline'/filename).read_bytes())
    (snapshot/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    args.figs.mkdir(parents=True, exist_ok=True)
    plt = common._setup_mpl()
    extent = common._extent_km(spec)
    fig, ax = plt.subplots(figsize=(15, 8))
    ax.imshow(rendering.rgb_v4(terrain, spec.spacing_m), extent=extent, origin='upper')
    ax.contour(td_ocean.astype(float),levels=[.5],extent=extent,origin='upper',
        colors=['#e69dc7'],linewidths=.6)
    ax.set(xlabel='Alongshore v / km', ylabel='Seaward u / km',
        title=f'遥感式合成影像（地形配色）｜连续平原腹地跨度 {max(core_extent["span_u_v_km"]):.1f} km｜100 m 构造初态\n粉线为原 TD 岸线；地质初态无物理经过时间')
    fig.tight_layout(); fig.savefig(args.figs/'overview.png', dpi=130); plt.close(fig)
    fig, axs = plt.subplots(1, 3, figsize=(18, 6))
    for ax, values, title, vmin, vmax in zip(axs,
            [td_bed, terrain['whole_plain']['bed'], change],
            ['原 TD 床面（m）', '源约束地质平原（m）', '构造床变（m，非事件沉积）'],
            [-80, -80, -30], [80, 80, 30]):
        im = ax.imshow(values, extent=extent, origin='upper', cmap='terrain' if vmin==-80 else 'RdBu_r', vmin=vmin, vmax=vmax)
        ax.set(title=title, xlabel='v / km', ylabel='u / km'); fig.colorbar(im, ax=ax, shrink=.7)
    fig.tight_layout(); fig.savefig(args.figs/'source-construction.png', dpi=110); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.imshow(rendering.rgb_v4(terrain, spec.spacing_m), extent=extent, origin='upper')
    ax.set(xlim=(-20, 5), ylim=(45, 20), xlabel='v / km', ylabel='u / km', title='同一保存床面局部｜100 m 采样')
    fig.tight_layout(); fig.savefig(args.figs/'detail-100m.png', dpi=130); plt.close(fig)
    resources = dict(elapsed_seconds=time.perf_counter()-started, spacing_m=spec.spacing_m,
        native_td_spacing_m=30., grid_shape=list(td_bed.shape),
        peak_working_set_bytes=psutil.Process().memory_info().peak_wset,
        product_bytes=sum(p.stat().st_size for p in args.out.rglob('*') if p.is_file()))
    common.write_json(args.out/'resources.json', resources)
    common.write_json(args.out/'sha256sums.json', {
        p.relative_to(args.out).as_posix():common.sha256_file(p)
        for p in sorted(args.out.rglob('*')) if p.is_file()})
    common.write_json(args.figs/'manifest.json', dict(terrain_basis=manifest['terrain_basis'],
        source_manifest=str(args.out/'manifest.json'), algorithms=files,
        coverage_status='complete_in_window', physical_event='not yet included in these construction figures',
        figures={p.name:common.sha256_file(p) for p in args.figs.glob('*.png')}))
    print(json.dumps(dict(metrics=metrics, resources=resources)), flush=True)


if __name__ == '__main__':
    main()
