"""Freshwater distributary construction and finite event routing on a supplied bed.

Coordinates are x,z metres, arrays indexed z,x. This is a deterministic,
steady kinematic approximation, not a tidal or backwater solver.
"""
from __future__ import annotations
import argparse
import json
import hashlib
from pathlib import Path
import numpy as np
from scipy.ndimage import binary_dilation, binary_propagation, distance_transform_edt, gaussian_filter1d
from skimage.graph import MCP_Geometric
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters


CORRIDOR_SEED = int.from_bytes(hashlib.sha256(b'20261020:active-network-corridors').digest()[:8], 'little')


def corridor_field(shape, origin, spacing):
    """Stationary deterministic field evaluated at absolute world coordinates."""
    rng = np.random.default_rng(CORRIDOR_SEED)
    x = origin[0] + np.arange(shape[1], dtype=float)*spacing
    z = origin[1] + np.arange(shape[0], dtype=float)*spacing
    field = np.zeros(shape, dtype=float)
    for _ in range(12):
        angle = rng.uniform(0, 2*np.pi)
        wavelength = rng.uniform(1200, 4000)
        phase = rng.uniform(0, 2*np.pi)
        field += np.cos((2*np.pi/wavelength)*(np.sin(angle)*z[:, None] + np.cos(angle)*x[None, :]) + phase)
    return field / np.sqrt(6.)


def curve_edge(points, land, anchors, forbidden, spacing):
    """Bend short pinned windows independently, retaining safe local fallback."""
    original = np.asarray(points, dtype=float)
    output_cells = []
    output_positions = []
    counts = dict(terrain=0, interference=0, duplicate=0, disconnected=0, accepted_windows=0, fallback_windows=0)
    # Each window is pinned to the backbone, including all graph junctions.
    window = max(8, int(1200/spacing))
    for begin in range(0, len(original)-1, window):
        end = min(begin+window, len(original)-1)
        pts = original[begin:end+1]
        outside = {tuple(p.astype(int)) for p in np.concatenate((original[:begin], original[end+1:]))}
        blocked = forbidden | outside | set(output_cells[:-1])
        blocked.discard(tuple(pts[0].astype(int)))
        blocked.discard(tuple(pts[-1].astype(int)))
        accepted = None
        for amplitude in (100/spacing, 50/spacing, 0.):
            if len(pts) < 4:
                break
            sigma = min(8., len(pts)/8)
            base = gaussian_filter1d(pts, sigma, axis=0, mode='nearest')
            t = np.linspace(0, 1, len(pts))
            taper = np.sin(np.pi*t)**2
            base = pts + (base-pts)*taper[:,None]
            tangent = np.gradient(base, axis=0)
            tangent /= np.maximum(np.linalg.norm(tangent, axis=1)[:,None], 1e-9)
            bend = amplitude*np.sin(2*np.pi*t)*taper
            candidate = base + np.column_stack((-tangent[:,1], tangent[:,0]))*bend[:,None]
            distance = np.r_[0., np.cumsum(np.linalg.norm(np.diff(candidate, axis=0), axis=1))]
            samples = np.linspace(0, distance[-1], max(2, int(np.ceil(distance[-1]*4))+1))
            candidate = np.column_stack([np.interp(samples, distance, candidate[:,axis]) for axis in range(2)])
            cells = np.rint(candidate).astype(int)
            keep = np.r_[True, np.any(np.diff(cells, axis=0) != 0, axis=1)]
            cells, candidate = cells[keep], candidate[keep]
            candidate[0] = pts[0]
            candidate[-1] = pts[-1]
            tuples = [tuple(v) for v in cells]
            if any(not (0 <= z < land.shape[0] and 0 <= x < land.shape[1] and (land[z,x] or (z,x) in anchors)) for z,x in tuples):
                counts['terrain'] += 1
            elif any(p in blocked for p in tuples):
                counts['interference'] += 1
            elif len(set(tuples)) != len(tuples):
                counts['duplicate'] += 1
            elif np.any(np.max(np.abs(np.diff(cells,axis=0)),axis=1) > 1):
                counts['disconnected'] += 1
            else:
                accepted = (tuples, candidate)
                counts['accepted_windows'] += 1
                break
        if accepted is None:
            accepted = ([tuple(p.astype(int)) for p in pts], pts)
            counts['fallback_windows'] += 1
        output_cells.extend(accepted[0][1:] if output_cells else accepted[0])
        output_positions.extend(accepted[1][1:] if output_positions else accepted[1])
    return output_cells, np.asarray(output_positions), counts


def build_network(bed, original_bed, deposit, origin, spacing, inlet, ocean_mask, forcing, outlet_count=5, valid_mask=None):
    bed = np.asarray(bed, dtype=float)
    original = np.asarray(original_bed, dtype=float)
    deposit = np.asarray(deposit, dtype=float)
    ocean = np.asarray(ocean_mask, dtype=bool).copy()
    if not isinstance(outlet_count, int) or not 1 <= outlet_count <= 20:
        raise ValueError('invalid outlet count')
    if bed.ndim != 2 or any(a.shape != bed.shape for a in (original, deposit, ocean)) or not all(np.isfinite(a).all() for a in (bed, original, deposit)) or spacing <= 0 or np.any(deposit < 0):
        raise ValueError('invalid terrain arrays or spacing')
    times = np.asarray(forcing['time_seconds'], float)
    qin = np.asarray(forcing['interval_water_q_m3_s'], float)
    water = np.asarray(forcing['interval_water_m3'], float)
    solid = np.asarray(forcing['interval_delivered_solid_m3'], float)
    if len(times) != len(qin)+1 or water.shape != qin.shape or solid.shape != qin.shape or np.any(np.diff(times) <= 0) or np.any(qin <= 0) or np.any(solid < 0) or not np.allclose(water, qin*np.diff(times), rtol=1e-10) or not np.allclose(qin, qin[0], rtol=1e-10):
        raise ValueError('forcing must be finite constant positive water and nonnegative daily solid')
    if not all(np.isfinite(a).all() for a in (times, qin, water, solid)):
        raise ValueError('nonfinite forcing')
    start = (int(round((inlet[1]-origin[1])/spacing)), int(round((inlet[0]-origin[0])/spacing)))
    if not (0 <= start[0] < bed.shape[0] and 0 <= start[1] < bed.shape[1]):
        raise ValueError('inlet outside raster')
    valid = np.ones(bed.shape, bool) if valid_mask is None else np.asarray(valid_mask, bool)
    if valid.shape != bed.shape or not valid[start]:
        raise ValueError('invalid terrain mask or inlet')
    ocean &= valid
    # Only sea connected to the edge is eligible as an outlet.
    boundary = np.zeros(bed.shape, dtype=bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    ocean = binary_propagation(ocean & boundary, mask=ocean)
    # Conservative terrain gate leaves at most 3 m of original excavation.
    land = valid & ~ocean & (bed > 0) & (original < 1.2) & (bed < 3.0)
    land[start] = True
    shallow_sea = ocean & (bed >= -3.0)
    coast = land & binary_dilation(shallow_sea)
    costs = np.full(bed.shape, np.inf)
    coast_distance = distance_transform_edt(~ocean)*spacing
    # Fixed-purpose spatial field bends routes at a scale much larger than a
    # pixel; it affects the actual route and excavation, not just the plot.
    seed = CORRIDOR_SEED
    noise = corridor_field(bed.shape, origin, spacing)
    costs[land] = (2 + .35*np.maximum(bed[land], 0) + .35/(deposit[land]+.5)
                   + 8*np.exp(-coast_distance[land]/180.)
                   + 1.5*np.clip(noise[land]+2, 0, 4))
    costs[start] = 1
    mcp = MCP_Geometric(costs, fully_connected=True)
    dist, _ = mcp.find_costs([start])
    candidates = np.argwhere(coast & np.isfinite(dist))
    if len(candidates) == 0:
        raise ValueError('no reachable coastline from inlet')
    # Limit the active event to accessible lobes rather than spanning the
    # entire geological coastline. The complex can contain inactive lobes.
    distance = np.linalg.norm(candidates-start, axis=1)*spacing
    candidates = candidates[(distance > 1500) & (distance < 10000)]
    if not len(candidates):
        raise ValueError('no coastline sufficiently far from inlet')
    candidates = candidates[::max(1, len(candidates)//500)]
    proposals = []
    for p in candidates:
        path = mcp.traceback(tuple(p))
        if len(path)*spacing < 2500:
            continue
        # A coast-hugging route is not made plausible by a distant outlet.
        near = np.mean([coast_distance[v] < 300 for v in path[:-min(len(path), int(500/spacing))]])
        proposals.append((p, path, near))
    chosen = []
    selected_paths = []
    for _ in range(outlet_count):
        best = None
        existing_splits = set()
        for a in range(len(selected_paths)):
            for b in range(a):
                first = next((i for i, (u,v) in enumerate(zip(selected_paths[a], selected_paths[b])) if u != v), min(len(selected_paths[a]), len(selected_paths[b])))
                existing_splits.add(selected_paths[a][max(0, first-1)])
        for p, path, near in proposals:
            if selected_paths:
                shared = max(next((i for i, (a,b) in enumerate(zip(path, other)) if a != b), min(len(path),len(other))) for other in selected_paths)
                unique = (len(path)-shared)*spacing
                separation = min(np.linalg.norm(p-q)*spacing for q in chosen)
                split = path[max(0, shared-1)]
                if (unique < 900 or separation < 1200 or coast_distance[split] < 180
                    or (0 < shared*spacing < 500)
                    or any(0 < (len(other)-shared)*spacing < 900 for other in selected_paths if shared <= len(other) and path[:shared] == other[:shared])
                    or any(0 < np.linalg.norm(np.subtract(split, old))*spacing < 500 for old in existing_splits)):
                    continue
                score = min(unique, 4000) + min(separation, 4000) - near*6000
            else:
                score = min(len(path)*spacing, 6500) - near*6000
            if best is None or score > best[0]:
                best = (score, p, path)
        if best is None:
            break
        chosen.append(best[1]); selected_paths.append(best[2])
    if not chosen:
        raise ValueError('no suitable coastal outlet')
    paths = []
    anchors = []
    for p in chosen:
        z, x = p
        neighbors = [(z+dz, x+dx) for dz, dx in ((-1,0),(1,0),(0,-1),(0,1))
                     if 0 <= z+dz < bed.shape[0] and 0 <= x+dx < bed.shape[1] and shallow_sea[z+dz,x+dx]]
        anchor = min(neighbors, key=lambda point: abs(bed[point] + 1.0))
        anchors.append(anchor)
        paths.append(mcp.traceback(tuple(p)) + [anchor])
    # MCP paths share a predecessor, giving a rooted, non-crossing cell tree.
    children = {}
    for path in paths:
        for a, b in zip(path, path[1:]):
            children.setdefault(tuple(a), set()).add(tuple(b))
    nodes = {start} | {tuple(p[-1]) for p in paths} | {p for p, c in children.items() if len(c) > 1}
    edges = []
    def walk(node, parent):
        for child in sorted(children.get(node, ())):
            points = [node, child]
            while child not in nodes:
                child = next(iter(children[child]))
                points.append(child)
            index = len(edges)
            edges.append(dict(parent=parent, points=points))
            walk(child, index)
    walk(start, -1)
    if not edges:
        raise ValueError('empty network')
    # Preserve graph nodes and accept each safe local bend independently.
    original_cells = [set(edge['points']) for edge in edges]
    occupied = set()
    for i, edge in enumerate(edges):
        pts = np.asarray(edge['points'], float)
        forbidden = set().union(*(cells for j, cells in enumerate(original_cells) if j != i)) | occupied
        forbidden.discard(tuple(pts[0].astype(int)))
        forbidden.discard(tuple(pts[-1].astype(int)))
        edge['backbone_length'] = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()*spacing)
        v = np.diff(pts, axis=0)
        angles = np.degrees(np.arctan2(v[:,0], v[:,1])) % 45
        weights = np.linalg.norm(v, axis=1)
        edge['backbone_grid_heading_fraction'] = float(weights[np.minimum(angles, 45-angles) < 5].sum()/weights.sum())
        edge['points'], edge['smooth'], edge['curve_diagnostics'] = curve_edge(edge['points'], land, anchors, forbidden, spacing)
        occupied.update(edge['points'][1:-1])
        edge['length'] = float(np.linalg.norm(np.diff(edge['smooth'], axis=0), axis=1).sum()*spacing)
    # Downstream path resistance is length; parallel conductances split flow.
    conductance = np.zeros(len(edges))
    for i in range(len(edges)-1, -1, -1):
        downstream = [j for j,e in enumerate(edges) if e['parent'] == i]
        resistance = edges[i]['length'] + (1/sum(conductance[j] for j in downstream) if downstream else 3000.)
        conductance[i] = 1/max(resistance, 1e-9)
    for i,e in enumerate(edges):
        siblings = [j for j,x in enumerate(edges) if x['parent'] == e['parent']]
        incoming = qin[0] if e['parent'] == -1 else edges[e['parent']]['q']
        e['q'] = float(incoming*conductance[i]/sum(conductance[j] for j in siblings))
        e['width'] = float(max(.5, 8.314*e['q']**.45))
        e['depth'] = float(max(.05, .598*e['q']**.28581553))
        e['velocity'] = e['q']/(e['width']*e['depth'])
        e['storage'] = e['length']*e['width']*e['depth']
    # Assign a single nonincreasing stage at every junction, with sea at 0 m.
    # A declared prefilled inlet head provides depth even at a near-zero TD bed.
    remaining = np.zeros(len(edges))
    for i in range(len(edges)-1, -1, -1):
        downstream = [j for j, edge in enumerate(edges) if edge['parent'] == i]
        remaining[i] = edges[i]['length'] + (min(remaining[j] for j in downstream) if downstream else 0.)
    longest = max(remaining[i] for i, edge in enumerate(edges) if edge['parent'] == -1)
    inlet_stage = max(1.5, .00005*longest)
    carved = bed.copy()
    raster_water = np.full(bed.shape, np.nan)
    line_rows = []
    for i, e in enumerate(edges):
        parent = e['parent']
        start_stage = inlet_stage if parent == -1 else edges[parent]['end_stage']
        downstream = [j for j, child in enumerate(edges) if child['parent'] == i]
        remain_after = min((remaining[j] for j in downstream), default=0.)
        end_stage = start_stage * remain_after / (e['length']+remain_after)
        e['end_stage'] = end_stage
        pts = np.asarray(e['points'], int)
        smooth = e['smooth']
        distances = np.r_[0., np.cumsum(np.linalg.norm(np.diff(smooth, axis=0), axis=1))]
        stages = start_stage + (end_stage-start_stage)*distances/distances[-1]
        for k, ((z,x), position, stage) in enumerate(zip(pts, smooth, stages)):
            target_bed = min(bed[z,x], stage-e['depth'])
            if target_bed < original[z,x]-3.-1e-9:
                raise ValueError('required incision exceeds 3 m original material; reroute required')
            carved[z,x] = min(carved[z,x], target_bed)
            if np.isfinite(raster_water[z,x]) and abs(raster_water[z,x]-stage)>1e-8:
                raise ValueError('routes overlap at incompatible water stages')
            raster_water[z,x] = stage
            line_rows.append((i, k, origin[0]+position[1]*spacing, origin[1]+position[0]*spacing,
                              z, x, stage, e['width'], e['depth']))
    rows = np.array(line_rows, float)
    lines = np.column_stack((rows[:, :4], carved[rows[:,4].astype(int), rows[:,5].astype(int)], rows[:,6:]))
    deposit_cut = np.minimum(bed-carved, deposit)
    original_cut = np.maximum(bed-carved-deposit_cut, 0.)
    deposit_bulk = float(deposit_cut.sum()*spacing**2)
    original_bulk = float(original_cut.sum()*spacing**2)
    for i, e in enumerate(edges):
        section = lines[lines[:,0] == i]
        segment_lengths = np.linalg.norm(np.diff(section[:,2:4], axis=0), axis=1)
        depths = section[:,5]-section[:,4]
        e['storage'] = float(np.sum(segment_lengths*(depths[:-1]+depths[1:])*.5)*e['width'])
        e['actual_depth'] = e['storage']/(e['length']*e['width'])
        e['velocity'] = e['q']/(e['width']*e['actual_depth'])
    n = len(edges); days = len(qin)
    outlet_water = np.zeros((days,n)); outlet_solid = np.zeros((days,n)); daily_inputs = np.zeros((days,n)); deposited = np.zeros((days,n)); stored = np.zeros(n)
    material = MaterialParameters(porosity=.4)
    solid_history = np.zeros((days+1,n))
    for day in range(days):
        inputs = np.zeros(n)
        for i,e in enumerate(edges):
            if e['parent'] == -1:
                inputs[i] = solid[day]*e['q']/qin[0]
            else:
                p = e['parent']; inputs[i] = outlet_solid[day,p]*e['q']/edges[p]['q']
            daily_inputs[day,i] = inputs[i]
            # Well-mixed transport reservoir over an interval; constant input.
            dt = times[day+1]-times[day]
            # Same settling law as metric_upstream_sediment, combined with
            # finite well-mixed advection over this interval (no bed erosion).
            advect = e['velocity']/e['length']
            settle = material.settling_velocity_m_s/e['actual_depth']
            total_rate = advect + settle
            decay = np.exp(-dt*total_rate)
            new = stored[i]*decay + inputs[i]/dt/total_rate*(1-decay)
            removed = stored[i]+inputs[i]-new
            outlet_solid[day,i] = removed*advect/total_rate
            deposited[day,i] = removed*settle/total_rate
            stored[i] = new
            outlet_water[day,i] = e['q']*dt
        solid_history[day+1] = stored
    leaves = [i for i in range(n) if not any(x['parent']==i for x in edges)]
    water_store = sum(e['storage'] for e in edges)
    # Deposit event solids uniformly over each analytic channel bed area.
    bed_delta = np.zeros(n)
    for i, e in enumerate(edges):
        bed_delta[i] = deposited[:,i].sum() / (.6*e['width']*e['length'])
    final_bed = carved.copy()
    # Map the analytic response to raster samples; average at shared junctions.
    delta_sum = np.zeros(bed.shape); delta_count = np.zeros(bed.shape)
    for i, e in enumerate(edges):
        pts = np.asarray(e['points'], int)
        delta_sum[pts[:,0], pts[:,1]] += bed_delta[i]
        delta_count[pts[:,0], pts[:,1]] += 1
    wet = delta_count > 0
    final_bed[wet] += delta_sum[wet]/delta_count[wet]
    final_lines = lines.copy()
    final_lines[:,4] = final_bed[rows[:,4].astype(int), rows[:,5].astype(int)]
    final_storage = np.zeros(n)
    for i, e in enumerate(edges):
        section = final_lines[final_lines[:,0] == i]
        segment_lengths = np.linalg.norm(np.diff(section[:,2:4], axis=0), axis=1)
        depths = section[:,5]-section[:,4]
        if np.any(depths <= 0):
            raise ValueError('event deposition exhausted channel depth')
        final_storage[i] = np.sum(segment_lengths*(depths[:-1]+depths[1:])*.5)*e['width']
    initial_storage = np.array([e['storage'] for e in edges])
    displacement = np.maximum(initial_storage-final_storage, 0.)
    daily_displacement = np.divide(deposited, deposited.sum(axis=0), out=np.zeros_like(deposited), where=deposited.sum(axis=0)>0)*displacement
    # Fixed-stage deposition displaces channel water downstream.
    for day in range(days):
        for i, e in enumerate(edges):
            if e['parent'] == -1:
                incoming_water = water[day]*e['q']/qin[0]
            else:
                parent = e['parent']
                incoming_water = outlet_water[day,parent]*e['q']/edges[parent]['q']
            outlet_water[day,i] = incoming_water + daily_displacement[day,i]
    result = dict(bed_m=final_bed, initial_channel_bed_m=carved, event_bed_change_m=final_bed-carved, water_surface_m=raster_water, water_depth_m=np.where(np.isfinite(raster_water), raster_water-final_bed, 0),
                  centerline_sections=final_lines, initial_centerline_sections=lines, inlet_hook_xz_m=np.asarray(inlet, float), parent=np.array([e['parent'] for e in edges]), branch_q_m3_s=np.array([e['q'] for e in edges]),
                  branch_length_m=np.array([e['length'] for e in edges]), branch_width_m=np.array([e['width'] for e in edges]), branch_depth_m=np.array([e['depth'] for e in edges]),
                  branch_water_storage_m3=initial_storage, final_branch_water_storage_m3=final_storage, daily_branch_water_displacement_m3=daily_displacement, branch_actual_depth_m=np.array([e['actual_depth'] for e in edges]), branch_velocity_m_s=np.array([e['velocity'] for e in edges]), branch_event_bed_change_m=bed_delta, daily_branch_water_out_m3=outlet_water,
                  daily_branch_solid_in_m3=daily_inputs, source_interval_water_m3=water, source_interval_solid_m3=solid, daily_branch_solid_out_m3=outlet_solid, daily_branch_deposited_solid_m3=deposited, solid_storage_m3=solid_history, leaf_indices=np.array(leaves), time_seconds=times)
    interior_cells = [p for e in edges for p in e['points'][:-min(len(e['points']), max(1, int(500/spacing)))]]
    junctions = [e['points'][-1] for i, e in enumerate(edges) if any(c['parent'] == i for c in edges)]
    for edge in edges:
        vectors = np.diff(edge['smooth'], axis=0)
        angle = np.degrees(np.arctan2(vectors[:,0], vectors[:,1])) % 45
        lengths = np.linalg.norm(vectors, axis=1)
        edge['grid_heading_fraction'] = float(lengths[np.minimum(angle, 45-angle) < 5].sum()/lengths.sum())
    metrics = dict(outlet_count=len(leaves), branch_count=n, inlet_world_xz_m=list(inlet), snapped_inlet_zx=list(start), origin_xz_m=list(origin), spacing_m=spacing,
                   geometry_diagnostics=[dict(backbone_length_m=e['backbone_length'], curved_length_m=e['length'], backbone_heading_within_5deg_of_grid_fraction=e['backbone_grid_heading_fraction'], curved_heading_within_5deg_of_grid_fraction=e['grid_heading_fraction'], **e['curve_diagnostics']) for e in edges],
                   nearshore_fraction_excluding_branch_terminal_500m=float(np.mean([coast_distance[p] < 300 for p in interior_cells])) if interior_cells else 0.,
                   shortest_branch_m=float(min(e['length'] for e in edges)), junction_sea_distances_m=[float(coast_distance[p]) for p in junctions],
                   corridor_seed=seed, corridor_seed_derivation='sha256(20261020:active-network-corridors), first 8 bytes little endian',
                   water_input_m3=float(water.sum()), water_outlet_m3=float(outlet_water[:,leaves].sum()), initial_water_storage_m3=water_store, final_water_storage_m3=float(final_storage.sum()),
                   water_residual_m3=float(water.sum()+water_store-outlet_water[:,leaves].sum()-final_storage.sum()), solid_input_m3=float(solid.sum()), solid_outlet_m3=float(outlet_solid[:,leaves].sum()), final_mobile_solid_m3=float(stored.sum()),
                   solid_deposited_m3=float(deposited.sum()), solid_residual_m3=float(solid.sum()-outlet_solid[:,leaves].sum()-stored.sum()-deposited.sum()),
                   deposit_excavation_bulk_m3=deposit_bulk, deposit_excavation_solid_m3=deposit_bulk*.6, original_excavation_bulk_m3=original_bulk, original_excavation_solid_m3=original_bulk*.6,
                   max_original_incision_m=float(original_cut.max()), inlet_stage_m=inlet_stage, max_stage_backstep_m=max(0., max(float(np.max(np.diff(lines[lines[:,0]==i,5]))) for i in range(n))),
                   width_range_m=[float(min(e['width'] for e in edges)),float(max(e['width'] for e in edges))], actual_depth_range_m=[float(np.min(lines[:,5]-lines[:,4])),float(np.max(lines[:,5]-lines[:,4]))],
                   velocity_range_m_s=[float(min(e['velocity'] for e in edges)),float(max(e['velocity'] for e in edges))],
                   section_velocity_range_m_s=[float(min(np.min(e['q']/(e['width']*(lines[lines[:,0]==i,5]-lines[lines[:,0]==i,4]))) for i,e in enumerate(edges))),float(max(np.max(e['q']/(e['width']*(lines[lines[:,0]==i,5]-lines[lines[:,0]==i,4]))) for i,e in enumerate(edges)))],
                   reach_bed_slopes=[float((lines[lines[:,0]==i,4][0]-lines[lines[:,0]==i,4][-1])/e['length']) for i,e in enumerate(edges)],
                   outlet_world_xz_m=[[float(origin[0]+p[1]*spacing),float(origin[1]+p[0]*spacing)] for p in anchors])
    return result, metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--formation', default='.scratch/large-delta-20261101/terrain-product-v1/terrain.npz')
    parser.add_argument('--forcing', default='.scratch/large-delta-20261101/active-source-v1/forcing.npz')
    parser.add_argument('--output', default='.scratch/large-delta-20261101/active-network-v5')
    parser.add_argument('--origin', nargs=2, type=float)
    parser.add_argument('--spacing', type=float)
    parser.add_argument('--inlet', nargs=2, type=float, default=(17430,-29040))
    parser.add_argument('--outlet-count', type=int, default=5)
    args = parser.parse_args()
    with np.load(args.formation) as f, np.load(args.forcing) as source:
        if 'derivedbed' in f:
            bed = f['derivedbed']; original = f['originalbed']; deposit = f['deposit']
            origin = args.origin if args.origin is not None else f['origin_xz_m']
            spacing = args.spacing if args.spacing is not None else float(f['spacing_m'])
            ocean = f['final_sea_connected_ocean']; valid = f['valid']
        else:
            bed = f['local_derived_bed_m']; original = f['local_original_bed_m']
            deposit = np.maximum(bed-original, 0); ocean = bed <= 0; valid = None
            origin = args.origin if args.origin is not None else (17130,-42240)
            spacing = args.spacing if args.spacing is not None else 30.
        result, metrics = build_network(bed, original, deposit, origin, spacing, args.inlet, ocean, source, outlet_count=args.outlet_count, valid_mask=valid)
    metrics['terrain_path'] = str(args.formation)
    metrics['terrain_sha256'] = hashlib.sha256(Path(args.formation).read_bytes()).hexdigest()
    metrics['forcing_path'] = str(args.forcing)
    metrics['forcing_sha256'] = hashlib.sha256(Path(args.forcing).read_bytes()).hexdigest()
    terrain_inventory = Path(args.formation).parent / 'manifest.json'
    if not terrain_inventory.exists():
        terrain_inventory = Path(args.formation).parent / 'inventory.json'
    source_manifest = Path(args.forcing).parent / 'manifest.json'
    terrain_metadata = json.loads(terrain_inventory.read_text(encoding='utf8')) if terrain_inventory.exists() else {}
    source_metadata = json.loads(source_manifest.read_text(encoding='utf8')) if source_manifest.exists() else {}
    if terrain_metadata.get('source_identity') and terrain_metadata['source_identity'] != source_metadata.get('source_identity'):
        raise ValueError('terrain and forcing source identities differ')
    metrics['source_identity'] = source_metadata.get('source_identity')
    metrics['world_seed'] = terrain_metadata.get('world_seed')
    metrics['origin_xz_m'] = [float(x) for x in metrics['origin_xz_m']]
    metrics_json = json.dumps(metrics, indent=2)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(output/'network.npz', **result)
    (output/'metrics.json').write_text(metrics_json, encoding='utf8')
    print(metrics_json)

if __name__ == '__main__':
    main()
