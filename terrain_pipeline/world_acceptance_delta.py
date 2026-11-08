"""Bind a local engineered delta simulation to an actual TD world river mouth.

No old scene is loaded. Coordinates are cell centres, rows increase world +z.
Distributary excavation is explicit engineering; subsequent deposition uses the
project's conservative channel-tree solver and actual upstream water discharge.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import label
from terrain_pipeline.surface_rivers.metric_coast_bounded_delta import carve_section, open_marine_mask, path_station, sample_path, truncate_at_first_marine
from terrain_pipeline.channel_geometry import flowing_path, derived_seed
from terrain_pipeline.surface_rivers.metric_tidal_creek_construction import enrich_tidal_coast
from terrain_pipeline.surface_rivers.metric_integrated_delta import build_channel_tree, run_integrated_delta, integrated_solid_ledger


def sha256(path):
    with open(path, 'rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def select_mouth(product):
    """Highest-discharge actual land receiver edge entering the actual ocean."""
    ocean = np.asarray(product['ocean_mask'], bool).ravel()
    receiver = np.asarray(product['receiver'], int).ravel()
    q = np.asarray(product['discharge_m3_s'], float).ravel()
    valid = (receiver >= 0) & (receiver < len(ocean)) & ~ocean
    candidates = np.flatnonzero(valid & ocean[np.clip(receiver, 0, len(ocean)-1)] & (q > 0))
    if not len(candidates):
        raise ValueError('world contains no flowing land-to-ocean receiver edge')
    mouth = int(candidates[np.argmax(q[candidates])])
    reverse = {}
    for source in np.flatnonzero(valid):
        reverse.setdefault(int(receiver[source]), []).append(int(source))
    chain = [mouth]
    while chain[-1] in reverse:
        previous = max(reverse[chain[-1]], key=lambda node: q[node])
        if previous in chain:
            raise ValueError('cyclic upstream receiver graph')
        chain.append(previous)
    xy = np.column_stack((np.asarray(product['node_x_m']).ravel(), np.asarray(product['node_z_m']).ravel()))
    return mouth, np.asarray(chain[::-1], int), xy, float(q[mouth])


def simulate_world_delta(product, native_bed, native_origin_xz_m, *, native_spacing_m=30., patch_radius_m=3300., concentration_kg_m3=.2, months=12):
    if concentration_kg_m3 < 0 or months < 1:
        raise ValueError('nonnegative concentration and positive months required')
    mouth, chain, xy, q = select_mouth(product)
    centre = xy[mouth]
    native_origin = np.asarray(native_origin_xz_m, float)
    spacing = float(native_spacing_m)
    native_bed = np.asarray(native_bed)
    bounds_lo = np.maximum(np.floor((centre-patch_radius_m-native_origin)/spacing).astype(int), 0)
    bounds_hi = np.minimum(np.ceil((centre+patch_radius_m-native_origin)/spacing).astype(int)+1, native_bed.shape[::-1])
    original = np.asarray(native_bed[bounds_lo[1]:bounds_hi[1], bounds_lo[0]:bounds_hi[0]], float).copy()
    origin = native_origin+bounds_lo*spacing
    marine = open_marine_mask(original)
    if not marine.any():
        raise ValueError('native TD mouth patch contains no boundary-connected sea')
    upstream = xy[chain]
    inside = np.all((upstream >= origin+spacing*3) & (upstream <= origin+(np.array(original.shape[::-1])-4)*spacing), axis=1)
    upstream = upstream[inside]
    if len(upstream) < 4:
        raise ValueError('mouth patch requires at least four actual upstream river nodes')
    station = path_station(upstream)
    # Keep the actual receiver path up to a junction 450 m before its mouth.
    chain_q = np.asarray(product['discharge_m3_s']).ravel()[chain]
    upstream_q = chain_q[inside]
    keep = (station >= max(0., station[-1]-2000.)) & (station <= station[-1]-450.) & (upstream_q >= q*.8)
    trunk = upstream[keep]
    if len(trunk) < 4:
        raise ValueError('actual upstream river is too short for local delta junctions')
    trunk = sample_path(trunk, path_station(trunk), np.linspace(0., path_station(trunk)[-1], max(7, len(trunk)*3)))
    inlet_node = int(chain[np.argmin(np.linalg.norm(xy[chain]-trunk[0], axis=1))])
    mouth_q = q
    q = float(np.asarray(product['discharge_m3_s']).ravel()[inlet_node])
    direction = centre-trunk[-1]
    direction /= np.linalg.norm(direction)
    branches = []
    seed = derived_seed(20261020, 'world-acceptance/delta-flowing-path/v1')
    for index, slope in enumerate((-.6, -.28, .6)):
        start = trunk[-1]
        points = flowing_path(start, direction, patch_radius_m*1.5, slope, np.random.default_rng(seed), 1201, bend_amplitude=12., initial_lateral_slope=slope*.25)
        inside = np.all((points >= origin+spacing) & (points <= origin+(np.array(original.shape[::-1])-2)*spacing), axis=1)
        outside = np.flatnonzero(~inside)
        if len(outside):
            points = points[:outside[0]]
        land_path, _ = truncate_at_first_marine(points, marine, origin, spacing, sample_count=401, terminal_inside_cell=True)
        cells = np.rint((points-origin)/spacing).astype(int)
        marine_path = marine[cells[:, 1], cells[:, 0]]
        first = int(np.flatnonzero(marine_path)[0])
        # Pressure outlets need a submerged marine section, rather than the
        # numerically near-dry first coastline cell. Keep the inherited sea bed.
        depths = -original[cells[:, 1], cells[:, 0]]
        ends = np.flatnonzero(marine_path & (depths >= 1.2) & (np.arange(len(points)) >= first))
        if not len(ends):
            raise ValueError('same-world marine patch lacks a submerged pressure outlet')
        last = int(ends[0])
        if not np.all(marine_path[first:last+1]):
            raise ValueError('delta marine pressure path crosses inherited land')
        points = np.vstack((land_path, points[first+1:last+1]))
        branches.append(points)
    # Resolution floor is explicit: narrow natural channels remain unresolved at
    # 30 m, so this engineering scene uses a two-cell minimum wetted section.
    hydraulic_width = 8.*np.sqrt(q)
    width = max(2.*spacing, min(260., hydraulic_width))
    widths = [width]+[max(2.*spacing, width*fraction) for fraction in (.72, .65, .8)]
    bed = original.copy()
    channel = np.zeros_like(marine)
    source_rc = np.rint((trunk[0]-origin)/spacing).astype(int)[::-1]
    source_bed = float(original[tuple(source_rc)])
    trunk_terminal_bed = min(.4, source_bed-.1)
    trunk_profile = np.linspace(source_bed, trunk_terminal_bed, len(trunk))
    for index, (path, channel_width) in enumerate(zip([trunk]+branches, widths)):
        dense_s = np.linspace(0., path_station(path)[-1], max(20, int(path_station(path)[-1]/(spacing/3))))
        dense = sample_path(path, path_station(path), dense_s)
        if index == 0:
            profile = np.interp(dense_s, path_station(trunk), trunk_profile)
        else:
            junction_index = len(trunk)-1
            dense_cells = np.rint((dense-origin)/spacing).astype(int)
            in_marine = marine[dense_cells[:, 1], dense_cells[:, 0]]
            marine_entry = int(np.flatnonzero(in_marine)[0])
            marine_bed = original[dense_cells[:, 1], dense_cells[:, 0]]
            entry_bed = float(marine_bed[marine_entry])
            profile = np.interp(dense_s, [0., dense_s[marine_entry]], [trunk_profile[junction_index], entry_bed])
            profile[in_marine] = marine_bed[in_marine]
        carved = carve_section(bed, origin, spacing, dense, profile, np.zeros(len(dense)), channel_width, marine, irregular=True)
        bed = carved['bed_m']
        channel |= carved['section_mask']
    # Existing reach carving clips at endpoint tangent planes. Irregular graph
    # junctions need the shared cross-section explicitly, or their nearest raster
    # cell can fall outside all incident half-planes and leave a dry join.
    rr, cc = np.indices(bed.shape)
    grid_xy = origin+np.stack((cc, rr), axis=-1)*spacing
    for junction_index in (len(trunk)//2, len(trunk)-1):
        distance = np.linalg.norm(grid_xy-trunk[junction_index], axis=-1)
        weight = np.clip((1.-distance/(width*.5))/.4, 0., 1.)*(~marine)
        weight[(distance <= spacing/np.sqrt(2.)) & ~marine] = 1.
        bed = np.minimum(bed, bed+weight*(trunk_profile[junction_index]-bed))
        channel |= weight > 0.
    edge_m = np.minimum.reduce([rr, cc, bed.shape[0]-1-rr, bed.shape[1]-1-cc])*spacing
    tidal_platform_weight = ((np.linalg.norm(grid_xy-centre, axis=-1) < 1800.) & (edge_m > 1200.)).astype(float)
    tidal = enrich_tidal_coast(dict(bed_m=bed, open_marine_mask=marine, channel_mask=channel, platform_weight=tidal_platform_weight,
        retained_upstream_raster_mask=np.zeros_like(marine), construction_footprint_mask=bed != original, trunk_path_xz_m=trunk),
        dict(origin_xz_m=origin.tolist(), spacing_m=spacing, incoming_width_m=width, river_direction_xz=direction.tolist()), world_seed=20261020)
    bed = tidal['arrays']['bed_m']
    marine = tidal['arrays']['open_marine_mask']
    geometry = build_channel_tree(bed, origin, spacing, centre, trunk[0], trunk, branches, widths, ocean_mask=marine, eligible_band_m=350., protected_band_m=spacing, branch_parent_index=[-1, -1, -1])
    geometry.protected_mask |= marine | ~channel
    geometry.eligible_mask &= ~marine & channel
    # An irregular graph inlet may round to a cell centre just behind the
    # reach's start tangent plane. It remains the unchanged boundary bed, but
    # must receive the solved source head rather than be excluded as upstream.
    geometry.protected_mask[tuple(source_rc)] = False
    geometry.eligible_mask[tuple(source_rc)] = True
    seconds = np.full(months, 365.*86400/12)
    water = q*seconds
    solid = water*concentration_kg_m3/2650.
    result = run_integrated_delta(bed, geometry, water, solid, seconds)
    wet = result['depth_m'] > 0.
    components, _ = label(wet)
    source_cell = np.rint((trunk[0]-origin)/spacing).astype(int)[::-1]
    source_component = int(components[tuple(source_cell)])
    checks = []
    for name, path in [('trunk', trunk)]+[(f'branch{index}', path) for index, path in enumerate(branches)]:
        cells = np.rint((path-origin)/spacing).astype(int)
        connected = source_component != 0 and np.all(components[cells[:, 1], cells[:, 0]] == source_component)
        checks.append(dict(path=name, samples=len(path), all_wet_in_inlet_component=bool(connected)))
    if not all(check['all_wet_in_inlet_component'] for check in checks):
        raise ValueError(f'delta inlet-to-ocean wet connectivity failed: {checks}')
    ledger = integrated_solid_ledger(result, solid)
    ledger['balance_residual_solid_m3'] = ledger['input_solid_m3']-ledger['retained_solid_m3']-ledger['exported_solid_m3']-ledger['escrow_solid_m3']
    ledger['water_input_m3'] = float(water.sum())
    terminal_q = np.asarray([r.terminal_q_m3_s or (r.q_branch0_m3_s, r.q_branch1_m3_s, r.q_branch2_m3_s) for r in result['records']])
    ledger['water_terminal_export_m3'] = float(np.sum(terminal_q*seconds[:, None]))
    delta = bed-original
    metadata = dict(schema='same-world-td-delta-v1', world_seed=20261020, origin_xz_m=origin.tolist(), spacing_m=spacing,
        coordinate_convention='cell centres; row +z; column +x; metres', mouth_node=mouth, mouth_xz_m=centre.tolist(), actual_upstream_q_m3_s=q,
        inlet_node=inlet_node, inlet_xz_m=trunk[0].tolist(), original_inlet_bed_m=source_bed, reference_mouth_q_m3_s=mouth_q, wet_connectivity=checks,
        inlet_unknown_external_inflow=bool(np.asarray(product.get('unknown_external_inflow_mask', np.zeros_like(product['ocean_mask']))).ravel()[inlet_node]),
        flow_boundary='Actual receiver discharge at inlet node; downstream local lateral runoff is not added within this local engineered delta',
        forcing_time='Twelve equal intervals per 365-day year at saved world final-year mean inlet Q; local steady-forcing engineering evaluation, not a synchronous seasonal rerun of the world',
        source_graph_path_nodes=chain.tolist(), construction='Existing seeded monotone downstream flowing_path engineering distributaries on the original same-world TD bed; not emergent avulsion',
        widths_m=widths, hydraulic_width_estimate_m=hydraulic_width, width_resolution_floor_m=2.*spacing, construction_purpose_seed=seed,
        sediment='Declared engineering suspended sediment concentration applied to computed same-world river Q; not upstream erosion output', concentration_kg_m3=concentration_kg_m3,
        duration_seconds=float(seconds.sum()), construction_cut_bulk_m3=float(np.maximum(-delta, 0.).sum()*spacing**2), construction_fill_bulk_m3=float(np.maximum(delta, 0.).sum()*spacing**2),
        tidal_construction_audit=tidal['audit'], tidal_construction_metadata=tidal['metadata'],
        algorithms=['metric_natural_construction.flowing_path', 'metric_coast_bounded_delta.carve_section', 'metric_tidal_creek_construction.enrich_tidal_coast', 'metric_integrated_delta.build_channel_tree', 'metric_integrated_delta.run_integrated_delta'], ledger=ledger,
        records=[asdict(record) for record in result['records']])
    arrays = dict(original_bed_m=original, constructed_bed_m=bed, final_bed_m=result['final_bed_m'], bed_change_m=result['height_delta_m'],
        wet_mask=result['depth_m'] > 0., water_depth_m=result['depth_m'], water_surface_m=result['stage_m'], ocean_mask=marine, channel_mask=channel,
        trunk_path_xz_m=trunk, incoming_path_xz_m=upstream, mouth_xz_m=centre, origin_xz_m=origin, spacing_m=np.array(spacing),
        monthly_water_m3=water, monthly_solid_m3=solid, month_seconds=seconds, stored_solid_m3=result['stored_solid_m3'],
        monthly_terminal_q_m3_s=terminal_q)
    arrays.update({f'branch{index}_path_xz_m': path for index, path in enumerate(branches)})
    arrays.update({key: value for key, value in tidal['arrays'].items() if key.startswith('tidal_')})
    return arrays, metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product', required=True, type=Path)
    parser.add_argument('--native-terrain', required=True, type=Path)
    parser.add_argument('--native-origin-x-m', required=True, type=float)
    parser.add_argument('--native-origin-z-m', required=True, type=float)
    parser.add_argument('--native-spacing-m', default=30., type=float)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--months', default=12, type=int)
    parser.add_argument('--concentration-kg-m3', default=.2, type=float)
    args = parser.parse_args(argv)
    with np.load(args.product, allow_pickle=False) as data:
        product = dict(data)
    arrays, metadata = simulate_world_delta(product, np.load(args.native_terrain, mmap_mode='r'), [args.native_origin_x_m, args.native_origin_z_m], native_spacing_m=args.native_spacing_m, months=args.months, concentration_kg_m3=args.concentration_kg_m3)
    metadata['sources'] = {name: dict(path=str(path.resolve()), sha256=sha256(path)) for name, path in [('world_product', args.product), ('native_td_terrain', args.native_terrain)]}
    if 'metadata_json' in product:
        metadata['world_product_metadata'] = json.loads(product['metadata_json'].item())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, **arrays, metadata_json=np.array(json.dumps(metadata)))
    print(json.dumps(dict(output=str(args.output), inlet_q_m3_s=metadata['actual_upstream_q_m3_s'],
        construction_cut_bulk_m3=metadata['construction_cut_bulk_m3'], tidal_creek_count=metadata['tidal_construction_audit']['creek_count'],
        wet_connectivity=metadata['wet_connectivity'], ledger=metadata['ledger']), indent=2))


if __name__ == '__main__':
    main()
