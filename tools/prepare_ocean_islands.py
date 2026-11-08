"""Prepare, sample and export a provenance-bound CPU ocean-island experiment."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image

from terrain_pipeline.ocean_islands import OceanIslandConfig, PlateOceanSource, prepare_ocean_islands, save_product, load_product
from terrain_pipeline.ocean_island_consumers import rasterize


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def measured(call):
    import psutil
    process = psutil.Process()
    stop = threading.Event()
    rss = [process.memory_info().rss]
    def sample():
        while not stop.wait(.01):
            rss.append(process.memory_info().rss)
    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    start = time.perf_counter()
    try:
        value = call()
    finally:
        elapsed = time.perf_counter() - start
        rss.append(process.memory_info().rss)
        stop.set()
        thread.join()
    return value, dict(wall_seconds=elapsed, process_rss_peak_bytes=max(rss), rss_sample_interval_ms=10,
                       scope='whole process RSS including prior allocations; peaks between samples may be missed')


def terrain_rgb(height, spacing):
    """Elevation colour and physical hillshade; no land-cover/vegetation claim."""
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list('metric_terrain', [(0, '#091b37'), (.30, '#15517b'), (.499, '#80bec1'),
                                                               (.5, '#b0aa80'), (.55, '#8c926b'), (.7, '#9b8e79'), (1, '#f4f1e9')])
    rgb = cmap(np.clip((height + 8000) / 16000, 0, 1))[..., :3]
    gz = np.gradient(height, spacing, axis=0) if height.shape[0]>1 else np.zeros_like(height)
    gx = np.gradient(height, spacing, axis=1) if height.shape[1]>1 else np.zeros_like(height)
    shade = np.clip((.8 - .4 * gx - .4 * gz) / np.sqrt(1 + gx * gx + gz * gz), .18, 1)
    return np.uint8(np.clip(rgb * (.55 + .45 * shade[..., None]), 0, 1) * 255)


def render_map(directory, prefix, raster, product_identity):
    """Unmarked same-source plan views with metric axes and elevation colour bar."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from matplotlib.cm import ScalarMappable
    cmap = LinearSegmentedColormap.from_list('metric_legend', [(0, '#091b37'), (.30, '#15517b'), (.499, '#80bec1'),
                                                               (.5, '#b0aa80'), (.55, '#8c926b'), (.7, '#9b8e79'), (1, '#f4f1e9')])
    bounds = raster.bounds_m
    extent = [bounds[0]/1000, bounds[2]/1000, bounds[3]/1000, bounds[1]/1000]
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), constrained_layout=True)
    for ax, key, title in zip(axes, ('base_elevation_m', 'elevation_m'), ('Original frozen plate surface / ocean floor', 'With frozen ocean islands')):
        ax.imshow(terrain_rgb(raster.fields[key], raster.spacing_m), extent=extent, origin='upper')
        ax.set(xlabel='Absolute X east (km)', ylabel='Absolute Z south (km)', title=title)
    fig.colorbar(ScalarMappable(norm=Normalize(-8000, 8000), cmap=cmap), ax=axes, label='Elevation / seabed (m), sea = 0', shrink=.65)
    fig.suptitle(f'{prefix}: same frozen source, {raster.spacing_m:g} m cells; {product_identity[:16]}\nElevation pseudocolour + physical shade; no real land-cover claim', fontsize=10)
    fig.savefig(directory / (prefix + '_comparison.png'), dpi=140, metadata={'SourceProduct':product_identity})
    plt.close(fig)


def export_raster(directory, prefix, raster):
    height = raster.fields['elevation_m']
    arrays = dict(raster.fields, x_m=raster.x_m, z_m=raster.z_m, land_fraction=raster.land_fraction,
                  protected_fraction=raster.protected_fraction, lagoon_fraction=raster.lagoon_fraction,
                  cell_area_m2=raster.cell_area_m2)
    if raster.ocean_connected is not None:
        arrays['ocean_connected'] = raster.ocean_connected
    np.savez_compressed(directory / (prefix + '.npz'), **arrays)
    np.save(directory / (prefix + '_elevation_m.npy'), height.astype(np.float32), allow_pickle=False)
    for suffix, value in (('terrain', height), ('base', raster.fields['base_elevation_m'])):
        Image.fromarray(terrain_rgb(value, raster.spacing_m)).save(directory / (prefix + '_' + suffix + '_preview.png'))
    Image.fromarray(np.uint16(np.rint(np.clip((raster.fields['base_elevation_m'] + 8000) / 16000, 0, 1) * 65535))).save(directory / (prefix + '_base16.png'))
    Image.fromarray(np.uint16(np.rint(np.clip((height + 8000) / 16000, 0, 1) * 65535))).save(directory / (prefix + '_elevation16.png'))
    Image.fromarray(np.uint8(np.rint(np.clip((height + 8000) / 16000, 0, 1) * 255))).save(directory / (prefix + '_elevation8.png'))
    return dict(raster.metadata, elevation_png_mapping=dict(zero_code_m=-8000, max_code_m=8000,
                code_to_m='-8000 + code * 16000 / 65535 (16-bit); 255 denominator for 8-bit',
                clipped_below_count=int((height < -8000).sum()), clipped_above_count=int((height > 8000).sum()),
                vertical_unit='metres; sea level 0m; float NPY/NPZ remains authoritative'),
                preview='height colour + physical hillshade; no real vegetation/land cover, no water/river ecology')


def detail_exports(directory, product):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    records = {}
    groups = {}
    for feature in product.features:
        groups.setdefault(feature.kind, []).append(feature)
    for kind, features in sorted(groups.items()):
        feature = sorted(features, key=lambda f: (f.chain_id, f.stage, f.feature_id))[0]
        radius = min(feature.support_radius_m * 1.3, 100000)
        xmin, zmin, xmax, zmax = product.source.bounds_m
        bounds = (max(xmin, feature.center_x_m - radius), max(zmin, feature.center_z_m - radius),
                  min(xmax, feature.center_x_m + radius), min(zmax, feature.center_z_m + radius))
        spacing = max(100., max(bounds[2] - bounds[0], bounds[3] - bounds[1]) / 600)
        local = rasterize(product, bounds, spacing, 1, area_refinement=2)
        records[kind] = dict(feature=asdict(feature), export=export_raster(directory, 'detail_' + kind, local))
        render_map(directory, 'detail_' + kind, local, product.identity)
        xx = np.linspace(bounds[0], np.nextafter(bounds[2], bounds[0]), 1201)
        zz = np.full_like(xx, feature.center_z_m)
        sampled = product.query(xx, zz)
        fig, ax = plt.subplots(figsize=(10, 3.5), constrained_layout=True)
        ax.plot(xx / 1000, sampled['base_elevation_m'], label='Original ocean floor')
        ax.plot(xx / 1000, sampled['elevation_m'], label='Frozen island surface')
        ax.axhline(0, color='black', linewidth=.6)
        ax.set(xlabel='Absolute X (km), +east', ylabel='Elevation (m)', title=f'{kind}; Z={feature.center_z_m / 1000:.3f} km; no vertical shape scaling')
        ax.legend()
        fig.savefig(directory / ('detail_' + kind + '_section.png'), dpi=140)
        plt.close(fig)
    hotspot = sorted((f for f in product.features if f.kind == 'hotspot'), key=lambda f: (f.chain_id, f.stage))
    if hotspot:
        chain = [f for f in product.features if f.chain_id == hotspot[0].chain_id]
        xmin, zmin, xmax, zmax = product.source.bounds_m
        bounds = (max(xmin, min(f.center_x_m-f.support_radius_m for f in chain)),
                  max(zmin, min(f.center_z_m-f.support_radius_m for f in chain)),
                  min(xmax, max(f.center_x_m+f.support_radius_m for f in chain)),
                  min(zmax, max(f.center_z_m+f.support_radius_m for f in chain)))
        local = rasterize(product, bounds, 500, 1, area_refinement=2)
        records['representative_chain'] = dict(chain_id=chain[0].chain_id,
                selection='lexicographically first hotspot chain before visual inspection',
                feature_ids=[f.feature_id for f in chain], export=export_raster(directory, 'representative_chain', local))
        render_map(directory, 'representative_chain', local, product.identity)
        first, last = sorted(chain, key=lambda f:f.stage)[0], sorted(chain, key=lambda f:f.stage)[-1]
        t = np.linspace(-.25, 1.35, 1801)
        xs = first.center_x_m + (last.center_x_m-first.center_x_m)*t
        zs = first.center_z_m + (last.center_z_m-first.center_z_m)*t
        valid = (xs>=xmin)&(xs<xmax)&(zs>=zmin)&(zs<zmax)
        xs, zs, t = xs[valid], zs[valid], t[valid]
        q = product.query(xs,zs)
        distance = t*np.hypot(last.center_x_m-first.center_x_m,last.center_z_m-first.center_z_m)/1000
        fig, ax = plt.subplots(figsize=(11,3.5), constrained_layout=True)
        ax.plot(distance,q['base_elevation_m'],label='Original ocean floor')
        ax.plot(distance,q['elevation_m'],label='Young to old chain, +plate velocity')
        ax.axhline(0,color='black',linewidth=.6)
        ax.set(xlabel='Distance along +plate velocity (km); 0 = youngest centre',ylabel='Elevation (m)',title='Representative chain: island slopes and submarine tail')
        ax.legend()
        fig.savefig(directory/'representative_chain_section.png',dpi=140)
        plt.close(fig)
    return records


def prepare(args):
    target = Path(args.out).resolve()
    if target.exists():
        raise FileExistsError(target)
    source_path = Path(args.source).resolve()
    source_file_sha = digest(source_path)
    if args.gallery and (Path(args.gallery).resolve() / target.name).exists():
        raise FileExistsError(Path(args.gallery).resolve() / target.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + target.name + '-', dir=target.parent))
    try:
        source, source_stats = measured(lambda: PlateOceanSource.from_npz(source_path, args.expected_identity))
        config = OceanIslandConfig(world_seed=args.world_seed, world_type=args.world_type, density=args.density,
                                  atolls=args.atolls, warm_water_scenario=args.warm_water_scenario,
                                  hotspot_count=getattr(args,'hotspot_count',None),arcs=not getattr(args,'no_arcs',False),
                                  ridge=not getattr(args,'no_ridge',False),
                                  volcanic_fraction=getattr(args,'volcanic_fraction',OceanIslandConfig().volcanic_fraction),
                                  volcanic_lava_strength=getattr(args,'volcanic_lava_strength',OceanIslandConfig().volcanic_lava_strength))
        product, prepare_stats = measured(lambda: prepare_ocean_islands(source, config))
        save_product(product, stage / 'islands.npz')
        reread = load_product(stage / 'islands.npz', product.identity)
        raster, raster_stats = measured(lambda: rasterize(reread, spacing_m=args.spacing, land_supersamples=args.supersamples))
        def export_all():
            exports = {'world': export_raster(stage, 'world', raster)}
            render_map(stage, 'world', raster, product.identity)
            if not args.no_details:
                exports.update(detail_exports(stage, reread))
            return exports
        exports, export_stats = measured(export_all)
        base_land = raster.fields['base_elevation_m'] >= 0
        area = raster.cell_area_m2
        summary = dict(features_by_kind=dict(Counter(f.kind for f in product.features)),
                       chain_count=len(set(f.chain_id for f in product.features)),
                       fractional_land_km2=float((raster.land_fraction * area).sum() / 1e6),
                       centre_new_land_km2=float((area * (raster.fields['land'] & ~base_land)).sum() / 1e6),
                       original_centre_land_km2=float((area * base_land).sum() / 1e6),
                       final_centre_land_km2=float((area * raster.fields['land']).sum() / 1e6),
                       ocean_fraction=float(raster.ocean_connected.mean()),
                       ocean_comparison=dict(method='same final grid cell centres; negative surface elevation; connectivity separately reported',
                            original_fraction=float((~base_land).mean()),final_fraction=float((~raster.fields['land']).mean()),
                            change_fraction=float((~raster.fields['land']).mean()-(~base_land).mean()),
                            target_fraction=getattr(args,'target_ocean_fraction',None),
                            target_deviation_fraction=None if getattr(args,'target_ocean_fraction',None) is None else float((~raster.fields['land']).mean()-args.target_ocean_fraction),
                            sea_level_adjusted=False),
                       nonnegative_ocean_cells=int((raster.ocean_connected & raster.fields['land']).sum()))
        if max(source_stats['process_rss_peak_bytes'],prepare_stats['process_rss_peak_bytes'],raster_stats['process_rss_peak_bytes'],export_stats['process_rss_peak_bytes']) > 2*1024**3:
            raise ValueError('measured process RSS exceeded 2 GiB')
        if digest(source_path) != source_file_sha:
            raise ValueError('source changed during run')
        manifest = dict(run_utc=datetime.now(timezone.utc).isoformat(), task_date='2026-11-06',
                        source_path=str(source_path), source_file_sha256=source_file_sha,
                        source_identity=source.identity, source_world_seed=source.world_seed,
                        source_array_summaries=product.manifest['arrays'], product_identity=product.identity,
                        config=asdict(config), source_kind=source.source_kind,
                        source_snapshot='islands.npz embeds all consumed original source arrays and original manifest; original NPZ unchanged',
                        coordinates='X east, Z south; absolute metres; origin at extent corner; samples at cell centres',
                        environment=dict(python=sys.version, platform=platform.platform(), numpy=np.__version__, executable=sys.executable),
                        source_hashes={str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__).resolve(), ROOT/'terrain_pipeline/ocean_islands.py', ROOT/'terrain_pipeline/ocean_island_consumers.py', ROOT/'terrain_pipeline/island_volcanoes.py', ROOT/'terrain_pipeline/island_volcanoes_v4.py']},
                        timings=dict(load_source=source_stats, prepare=prepare_stats, raster=raster_stats,export_render=export_stats), statistics=summary,
                        budgets=dict(max_output_cells=1000000,max_generation_sampled_rss_bytes=2*1024**3,prepare_target_seconds=60,raster_target_seconds=60,
                                     timing_targets_met=prepare_stats['wall_seconds']<60 and raster_stats['wall_seconds']<60,
                                     scope='source load, preparation, raster, export/render phases sampled at 10ms; short inter-phase save/load gaps are not monitored'),
                        exports=exports, limitations=['Finite source; clamped base interpolation. Whole raster ocean connectivity uses finite four-neighbour boundary flood.',
                            'No GPU/TD generation; direct vector-aware TD condition and TD model response are separate acceptance items.',
                            'Regular cell-area samples plus inner-support refinement may miss narrower strips; all frozen features and support-cell references are retained.',
                            'Explicit periodic TD condition mapping repeats a finite plan and does not guarantee continuity at its seams.',
                            'Preview colours encode elevation, not real land cover. No fabricated river/lake/ecology layers.'])
        manifest['files'] = {p.name:dict(sha256=digest(p), bytes=p.stat().st_size) for p in stage.iterdir() if p.is_file()}
        write_json(stage / 'delivery_manifest.json', manifest)
        stage.rename(target)
    finally:
        if stage.exists():
            cleanup = stage.resolve()
            if cleanup.parent != target.parent.resolve() or not cleanup.name.startswith('.' + target.name + '-'):
                raise ValueError('refusing to remove a directory outside this run staging prefix')
            shutil.rmtree(cleanup)
    if args.gallery:
        gallery = Path(args.gallery).resolve() / target.name
        if gallery.exists():
            raise FileExistsError(gallery)
        gallery.mkdir(parents=True)
        copied = {}
        for src in sorted(target.glob('*.png')):
            dest = gallery / src.name
            shutil.copy2(src, dest)
            if digest(src) != digest(dest):
                raise ValueError('gallery SHA mismatch')
            copied[src.name] = digest(dest)
        write_json(gallery / 'image_binding.json', dict(product_identity=product.identity, source_identity=source.identity,
                   source_file_sha256=digest(source_path), run_manifest=str(target/'delivery_manifest.json'), images=copied,
                   mapping=manifest['exports'], source_type=source.source_kind, td_generation=False))
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--expected-identity', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--spacing', type=float, default=2000)
    parser.add_argument('--supersamples', type=int, default=2)
    parser.add_argument('--world-seed', type=int, default=20260903)
    parser.add_argument('--world-type', choices=('balanced','archipelago','continental','oceanic','waterworld','islands',
                                               'multi-continent','pangaea','two-continents','inland-sea'), default='balanced')
    parser.add_argument('--density', choices=('none','low','medium','high'), default='medium')
    parser.add_argument('--atolls', action='store_true')
    parser.add_argument('--warm-water-scenario', action='store_true')
    parser.add_argument('--hotspot-count',type=int,default=None)
    parser.add_argument('--no-arcs',action='store_true')
    parser.add_argument('--no-ridge',action='store_true')
    parser.add_argument('--volcanic-fraction',type=float,default=OceanIslandConfig().volcanic_fraction,
                        help='Deterministic special volcano fraction among eligible hotspot/arc features; 0 disables (default:0.2)')
    parser.add_argument('--volcanic-lava-strength',type=float,default=OceanIslandConfig().volcanic_lava_strength,
                        help='Warped smooth Voronoi lava geometry strength in [0,2]; 0 disables (default:1)')
    parser.add_argument('--target-ocean-fraction',type=float,default=None,help='report-only target in [0,1]; never adjusts sea level')
    parser.add_argument('--no-details', action='store_true')
    parser.add_argument('--gallery')
    args = parser.parse_args(argv)
    if args.target_ocean_fraction is not None and not 0<=args.target_ocean_fraction<=1:
        parser.error('--target-ocean-fraction must be finite and in [0,1]')
    print(prepare(args))


if __name__ == '__main__':
    main()
