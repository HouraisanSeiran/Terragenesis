"""Explicit frozen complex-network adapter to finite physical river/marine events.

The unchanged terrain array is a regular model frame X=v,Z=u. World coordinates
are a saved affine transform, never an origin attached to a rotated array.
"""
from dataclasses import asdict
import copy
import hashlib
import json
import math
from pathlib import Path

import networkx as nx
import numpy as np

from .coastal_marine_sediment import make_state
from .coastal_delta_routes import build_route_geometry, world_to_cell
from .coastal_delta_evolution import initialize
from .coastal_delta_branching import _record, mouth_exterior_faces
from .coastal_delta_hydraulics import solve
from .coastal_delta_node_inventory import ChannelInventory


def _simplify(points, tolerance):
    if len(points) < 3:
        return points
    vector = points[-1] - points[0]
    length2 = float(vector @ vector)
    t = np.clip((points-points[0]) @ vector / length2, 0., 1.) if length2 else np.zeros(len(points))
    distances = np.linalg.norm(points-(points[0]+t[:, None]*vector), axis=1)
    index = int(np.argmax(distances))
    if distances[index] <= tolerance:
        return points[[0, -1]]
    return np.concatenate((_simplify(points[:index+1], tolerance)[:-1],
                           _simplify(points[index:], tolerance)))


def _sample(points, interval, tolerance):
    points = _simplify(points, tolerance)
    sampled = []
    for a, b in zip(points, points[1:]):
        count = max(1, int(math.ceil(np.linalg.norm(b-a)/interval)))
        sampled.extend(a+(b-a)*i/count for i in range(count))
    return np.asarray([*sampled, points[-1]])


def _control_alternatives(raw, before, point, after, search_m, tolerance_m):
    """Shift only an interior account along its own immutable source polyline.

    Endpoints and topology never move. Accept a candidate only when the source
    vertices between its neighbours remain within the declared geometric error.
    This resolves sampling coincidences, not unrepresentable coincident reaches.
    """
    raw=raw[np.r_[True,np.linalg.norm(np.diff(raw,axis=0),axis=1)>1e-9]]
    vectors = np.diff(raw,axis=0)
    lengths = np.linalg.norm(vectors,axis=1)
    if np.any(lengths<=0):
        return []
    cumulative = np.r_[0.,np.cumsum(lengths)]
    def parameter(value):
        t = np.clip(np.sum((value-raw[:-1])*vectors,axis=1)/lengths**2,0.,1.)
        distances = np.linalg.norm(raw[:-1]+t[:,None]*vectors-value,axis=1)
        index = int(np.argmin(distances))
        return cumulative[index]+t[index]*lengths[index]
    lo,current,hi = map(parameter,(before,point,after))
    candidates=[]
    for amount in (.25,.5,.75,1.):
        for sign in (-1,1):
            distance=current+sign*search_m*amount
            if not lo+1e-6<distance<hi-1e-6:
                continue
            index=min(int(np.searchsorted(cumulative,distance,side='right')-1),len(lengths)-1)
            candidate=raw[index]+vectors[index]*(distance-cumulative[index])/lengths[index]
            vertices=np.vstack((before,raw[(cumulative>lo)&(cumulative<hi)],after))
            errors=[]
            for a,b in ((before,candidate),(candidate,after)):
                vector=b-a
                t=np.clip((vertices-a)@vector/(vector@vector),0.,1.)
                errors.append(np.linalg.norm(vertices-a-t[:,None]*vector,axis=1))
            error=float(np.minimum(*errors).max())
            if error<=tolerance_m+1e-7:
                candidates.append((float(np.linalg.norm(candidate-point)),error,candidate))
    return sorted(candidates,key=lambda value:(value[0],value[1],*value[2]))


def _accounts(graph, state, interval, tolerance, *, placements=None, control_cell_search_m=None):
    topology = nx.DiGraph()
    positions = {}
    for node in graph['nodes']:
        key = int(node['id'])
        if key in positions:
            raise ValueError('duplicate source graph node')
        positions[key] = np.array([node['v_m'], node['u_m']], float)
        topology.add_node(key)
    edge_rows, pair_edges = {}, {}
    for ordinal,edge in enumerate(graph['edges']):
        a, b = int(edge['from']), int(edge['to'])
        key=(a,b,int(edge.get('id',ordinal)))
        if a not in positions or b not in positions or key in edge_rows:
            raise ValueError('unknown endpoint or duplicate physical edge')
        topology.add_edge(a, b)
        edge_rows[key] = edge
        pair_edges.setdefault((a,b),[]).append(key)
    if not nx.is_directed_acyclic_graph(topology):
        raise ValueError('source river graph must be a DAG')
    roots = [n for n in topology if topology.in_degree(n) == 0]
    mouths = sorted(n for n in topology if topology.out_degree(n) == 0)
    if len(roots) != 1 or not edge_rows or not mouths:
        raise ValueError('source graph requires one inlet and wet outlets')
    inlet = roots[0]
    if len(nx.descendants(topology, inlet))+1 != len(topology):
        raise ValueError('disconnected source graph')
    cells, coordinates, widths, sampled_edges = {}, {}, {}, {}
    for node, point in positions.items():
        cell = world_to_cell(point, state.origin_xz_m, state.spacing_m, state.base_bed_m.shape)
        if cell in cells and cells[cell] != ('node', node):
            raise ValueError('distinct junctions collapse into one account cell; use finer grid')
        cells[cell] = ('node', node)
    for (a, b, edge_id), edge in sorted(edge_rows.items()):
        raw = np.asarray(edge['path_uv_m'], float)[:, ::-1]
        if (raw.ndim != 2 or raw.shape[1] != 2 or len(raw) < 2 or not np.isfinite(raw).all()
                or not np.allclose(raw[0], positions[a], atol=1e-6, rtol=0)
                or not np.allclose(raw[-1], positions[b], atol=1e-6, rtol=0)):
            raise ValueError('edge polyline must match canonical endpoint coordinates')
        width = float(edge['width_m'])
        if not np.isfinite(width) or width <= 0:
            raise ValueError('invalid source width')
        path = []
        points = _sample(raw, interval, tolerance)
        if len(pair_edges[a,b])>1 and len(points)==2:
            length=float(np.linalg.norm(np.diff(raw,axis=0),axis=1).sum())
            points=_sample(raw,min(interval,length/2.),tolerance)
        # Profiles are sampled by normalized arclength, preserving mouth widening.
        profile = edge.get('width_profile_m')
        for i, point in enumerate(points):
            cell = world_to_cell(point, state.origin_xz_m, state.spacing_m, state.base_bed_m.shape)
            if not state.valid_mask[cell]:
                raise ValueError('river account outside valid terrain')
            tag = ('node', a) if i == 0 else ('node', b) if i == len(points)-1 else ('edge', a, b, edge_id)
            if 0 < i < len(points)-1 and cell in cells and cells[cell] in (('node', a), ('node', b)):
                continue
            if cell in cells and cells[cell] != tag:
                alternatives=[]
                if 0<i<len(points)-1:
                    search=state.spacing_m if control_cell_search_m is None else control_cell_search_m
                    before=np.asarray(coordinates[path[-1]]) if path else points[i-1]
                    alternatives=_control_alternatives(raw,before,point,points[i+1],search,tolerance)
                chosen=None
                for shift,error,candidate in alternatives:
                    candidate_cell=world_to_cell(candidate,state.origin_xz_m,state.spacing_m,state.base_bed_m.shape)
                    if candidate_cell not in cells and state.valid_mask[candidate_cell]:
                        chosen=shift,error,candidate,candidate_cell
                        break
                if chosen is None:
                    raise ValueError(f'nonshared channels collapse into account cell {cell}: {cells[cell]} vs {tag}; use finer grid or declared control-cell placement')
                shift,error,candidate,candidate_cell=chosen
                if placements is not None:
                    placements.append({'source_edge':[a,b],'source_edge_id':edge_id,'old_model_xz_m':point.tolist(),
                        'new_model_xz_m':candidate.tolist(),'shift_m':shift,'local_source_error_m':error})
                point,cell=candidate,candidate_cell
            if path and cell == path[-1]:
                if i == len(points)-1:
                    coordinates[cell] = point.tolist()
                continue
            if cell in path:
                raise ValueError('curved edge revisits an account cell; use finer grid')
            cells[cell] = tag
            if cell in coordinates and not np.allclose(coordinates[cell], point, atol=1e-6, rtol=0):
                raise ValueError('conflicting shared endpoint coordinates')
            coordinates[cell] = point.tolist()
            local_width = width
            if profile is not None:
                values = np.asarray(profile, float)
                if values.shape != (len(raw),) or not np.isfinite(values).all() or np.any(values <= 0):
                    raise ValueError('width profile must match path vertices')
                nearest = np.argmin(np.linalg.norm(raw-point, axis=1))
                local_width = float(values[nearest])
            widths[cell] = max(widths.get(cell, 0.), local_width)
            path.append(cell)
        if len(path) < 2:
            raise ValueError('physical edge collapsed into one cell')
        if len(pair_edges[a,b])>1 and len(path)<3:
            raise ValueError('parallel physical arms need distinct interior account cells; use finer grid')
        sampled_edges[a, b, edge_id] = path
    # A deterministic edge cover. Reconnection count increases routes linearly;
    # prefixes/suffixes use a single topological predecessor/successor per node.
    routes = []
    order = list(nx.lexicographical_topological_sort(topology))
    prefixes, suffixes = {inlet: [inlet]}, {}
    for node in order[1:]:
        parent = min(topology.predecessors(node))
        prefixes[node] = prefixes[parent]+[node]
    for node in reversed(order):
        children = sorted(topology.successors(node))
        suffixes[node] = [node]+suffixes[children[0]] if children else [node]
    covered = set()
    for key in sorted(edge_rows):
        a,b,_=key
        if key in covered:
            continue
        source_path = prefixes[a]+suffixes[b]
        path = []
        for x, y in zip(source_path, source_path[1:]):
            selected=key if (x,y)==(a,b) else min(pair_edges[x,y])
            covered.add(selected)
            segment = sampled_edges[selected]
            path.extend(segment if not path else segment[1:])
        routes.append(path)
    return routes, coordinates, widths


def _ownership(state, routes, coordinates, widths, subdivisions):
    """Rasterize unique variable-width segments without changing any bed elevation.

    A subcell belongs to the closest normalized segment, then lexicographic edge.
    Only touched grid cells are stored, avoiding a whole-window supersampled grid.
    """
    dx = state.spacing_m
    origin = np.asarray(state.origin_xz_m)
    edges = sorted({(a, b) for path in routes for a, b in zip(path, path[1:])})
    shape = state.base_bed_m.shape
    tile_size = 32
    tiles = {}
    segments = []
    nodes = sorted(coordinates)
    node_ids = {node: index for index, node in enumerate(nodes)}
    for a, b in edges:
        pa, pb = np.asarray(coordinates[a]), np.asarray(coordinates[b])
        reach = max(widths[a], widths[b])/2
        low = np.floor((np.minimum(pa, pb)-reach-origin)/dx-.5).astype(int)
        high = np.ceil((np.maximum(pa, pb)+reach-origin)/dx+.5).astype(int)
        index = len(segments)
        segments.append((a, b, pa, pb))
        for row in range(max(0, low[1])//tile_size, min(shape[0]-1, high[1])//tile_size+1):
            for col in range(max(0, low[0])//tile_size, min(shape[1]-1, high[0])//tile_size+1):
                tiles.setdefault((row, col), []).append(index)
    counts = {}
    # Bound temporary supersampling by one tile, independent of domain size.
    for (tile_row, tile_col), candidates in sorted(tiles.items()):
        r0, c0 = tile_row*tile_size, tile_col*tile_size
        nr, nc = min(tile_size, shape[0]-r0), min(tile_size, shape[1]-c0)
        xs = origin[0]+(c0-.5+(np.arange(nc*subdivisions)+.5)/subdivisions)*dx
        zs = origin[1]+(r0-.5+(np.arange(nr*subdivisions)+.5)/subdivisions)*dx
        x, z = xs[None, :], zs[:, None]
        best = np.full((len(zs), len(xs)), np.inf)
        winner = np.full(best.shape, -1, np.int32)
        for index in candidates:
            a, b, pa, pb = segments[index]
            vector = pb-pa
            t = np.clip(((x-pa[0])*vector[0]+(z-pa[1])*vector[1])/(vector@vector), 0., 1.)
            ratio = np.hypot(x-pa[0]-t*vector[0], z-pa[1]-t*vector[1])*2/(widths[a]*(1-t)+widths[b]*t)
            take = (ratio <= 1.) & (ratio < best)
            best[take] = ratio[take]
            owner = np.where(t < .5, node_ids[a], node_ids[b])
            winner[take] = owner[take]
        rr, cc = np.nonzero(winner >= 0)
        rows, cols = r0+rr//subdivisions, c0+cc//subdivisions
        good = state.valid_mask[rows, cols]
        packed = winner[rr[good], cc[good]].astype(np.int64)*np.prod(shape)+rows[good]*shape[1]+cols[good]
        keys, values = np.unique(packed, return_counts=True)
        for key, value in zip(keys, values):
            node_id, cell_id = divmod(int(key), int(np.prod(shape)))
            row, col = divmod(cell_id, shape[1])
            counts[nodes[node_id], row, col] = int(value)
    parts = {n: [] for n in coordinates}
    owned = {}
    for (node, row, col), count in sorted(counts.items()):
        fraction = count/subdivisions**2
        stocks = [float(getattr(state, field)[row, col])*fraction for field in
                  ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')]
        parts[node].append([row, col, fraction, *stocks])
        item = owned.setdefault((row, col), [0., 0., 0., 0.])
        item[:] = [x+y for x, y in zip(item, [fraction, *stocks])]
    if any(not entries for entries in parts.values()):
        raise ValueError('narrow channel missed by footprint sampling; increase subdivisions')
    footprints = [[*node, entries] for node, entries in sorted(parts.items())]
    owners = [[*cell, *values, float(state.base_bed_m[cell]), float(state.base_bed_m[cell]), 0.]
              for cell, values in sorted(owned.items())]
    return footprints, owners


def initialize_graph(graph, bed_m, site, valid_mask, ocean_seed_mask, *, source_identity,
                     source_seed, algorithm_seed, hydraulic_config, discharge_m3_s,
                     solid_rate_m3_s=0., erodible_thickness_m=.5, porosity=.4,
                     control_spacing_m=1000., geometry_tolerance_m=10., subdivisions=4,
                     sea_level_m=0., input_id='complex-network-initial', control_cell_search_m=None):
    """Bind frozen terrain unchanged; stock is declared geology, never river supply."""
    bed = np.asarray(bed_m, float)
    valid = np.asarray(valid_mask, bool)
    dx = float(site['spacing_m'])
    thickness = np.broadcast_to(np.asarray(erodible_thickness_m, float), bed.shape)
    por = np.broadcast_to(np.asarray(porosity, float), bed.shape)
    if (valid.shape != bed.shape or np.any(thickness < 0) or not np.isfinite(thickness).all()
            or not np.isfinite([control_spacing_m,geometry_tolerance_m,
                dx if control_cell_search_m is None else control_cell_search_m]).all()
            or (control_cell_search_m is not None and control_cell_search_m<0)
            or control_spacing_m <= 0 or geometry_tolerance_m < 0
            or not isinstance(subdivisions, int) or subdivisions < 1):
        raise ValueError('invalid adapter geometry or initial material')
    state = make_state(base_bed_m=bed-np.where(valid, thickness, 0.),
        bed_solid_m3=np.where(valid, thickness*dx**2*(1-por), 0.), mobile_solid_m3=0.,
        porosity=por, valid_mask=valid, ocean_seed_mask=ocean_seed_mask, spacing_m=dx,
        origin_xz_m=(site['v0_m']+dx/2, site['u0_m']+dx/2), source_identity=source_identity)
    placements=[]
    routes, points, widths = _accounts(graph, state, control_spacing_m, geometry_tolerance_m,
        placements=placements,control_cell_search_m=control_cell_search_m)
    footprints, owners = _ownership(state, routes, points, widths, subdivisions)
    main = routes[0]
    data = {'main_cells_zx': np.asarray(main), 'main_points_xz': np.asarray([points[n] for n in main]),
            'branch_offsets': np.array([0]), 'branch_cells_zx': np.empty((0, 2), int),
            'branch_points_xz': np.empty((0, 2)), 'section_bed_m': np.array([bed[n] for n in main]),
            'section_bank_m': np.array([bed[n] for n in main]),
            'section_width_m': np.array([widths[n] for n in main]),
            'section_stage_m': np.full(len(main), hydraulic_config.upstream_stage_limit_m)}
    metadata = {'source_identity': source_identity, 'route_geometry_algorithm': 'complex-network-model-vu-v1',
                'route_geometry_seed': int(algorithm_seed)}
    state, progress = initialize(state, data, metadata, input_id=input_id,
                                discharge_m3_s=discharge_m3_s, solid_rate_m3_s=solid_rate_m3_s)
    progress['routes'] = [[list(n) for n in route] for route in routes]
    progress['shares'] = [1/len(routes)]*len(routes)
    progress['hydraulics_backend'] = 'physical_edge_graph'
    progress['route_geometry'] = build_route_geometry(state, routes,
        [[points[n] for n in route] for route in routes], metadata['route_geometry_algorithm'], algorithm_seed)
    progress['node_footprints'] = footprints
    progress['integrated']['owner_cells'] = owners
    section_order = main + sorted(set(points)-set(main))
    progress['hydraulic_sections']['nodes'] = [[*n, float(bed[n]), widths[n], float(bed[n]), hydraulic_config.roughness]
                                               for n in section_order]
    # No construction excavation or fill occurs. Geometry is the frozen initial state.
    progress['complex_network'] = {'algorithm': 'frozen-network-physical-adapter-v1',
        'source_seed': int(source_seed), 'algorithm_seed': int(algorithm_seed),
        'model_axes': 'X_model=v, Z_model=u; array[row_u,col_v]', 'site': copy.deepcopy(site),
        'graph_sha256': hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest(),
        'initial_dem_sha256': hashlib.sha256(bed.tobytes()).hexdigest(),
        'control_spacing_m': control_spacing_m, 'geometry_tolerance_m': geometry_tolerance_m,
        'control_cell_policy':'bounded along-source account shifts; immutable source endpoints and physical topology',
        'control_cell_search_m':dx if control_cell_search_m is None else control_cell_search_m,
        'control_cell_adjustments':placements,
        'footprint_subdivisions': subdivisions, 'initial_stock_solid_m3': float(state.bed_solid_m3.sum()),
        'construction_event_supply_solid_m3': 0., 'initial_material': 'declared finite geological layer',
        'design_q_role': 'source morphology only; hydraulic solve uses discharge boundary and actual sections'}
    pool = ChannelInventory(state, progress)
    state, progress = pool.commit(state, progress)
    # Section beds are means of the owned finite inventory, including subcell
    # banks. Establish them before the first solve, so _prepare cannot change
    # an initial section merely by committing its untouched inventory.
    for index, node in enumerate(main):
        progress['integrated']['sections']['section_bed_m'][index] = pool.section_bed(node)
    progress['complex_network']['section_bed_definition'] = 'area-weighted owned footprint bed'
    progress['complex_network']['width_feedback'] = 'fixed initial design widths; finite bed exchange remains active'
    progress['complex_network']['topology'] = 'fixed frozen DAG; no event-end mouth extension or avulsion'
    from .coastal_delta_multicell import _prepare
    state, progress = _prepare(_record(state, progress), progress)
    faces = mouth_exterior_faces(state, progress, sea_level_m=sea_level_m)
    if not all(faces):
        raise ValueError('source graph mouth does not contact connected exterior sea through its footprint')
    progress['river_hydraulics'] = solve(state, progress, sea_level_m, hydraulic_config)
    return _record(state, progress), progress


def model_to_world(site, points_xz):
    """Convert model [v,u] points into absolute world [X,Z] metres."""
    from .delta_network_site import SiteSpec, local_to_world
    points = np.asarray(points_xz, float)
    x, z = local_to_world(SiteSpec(**site), points[..., 1], points[..., 0])
    return np.stack((x, z), axis=-1)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_frozen_product(directory, *, hydraulic_config, discharge_m3_s=None,
                        solid_rate_m3_s=0., erodible_thickness_m=.5, porosity=.4,
                        control_spacing_m=1000., geometry_tolerance_m=10., subdivisions=4,
                        sea_level_m=0.,control_cell_search_m=None):
    """Read a hash-bound morphology product, preserving TD and declared shelf roles.

    The valid mask means known source support. No outside-TD placeholder is
    promoted to bathymetry. Exterior sea seeds require the saved TD-ocean flag.
    """
    directory = Path(directory)
    read_json = lambda name: json.loads((directory/name).read_text(encoding='utf-8'))
    manifest, graph = read_json('manifest.json'), read_json('channel_graph.json')
    reference_name = 'construction_reference_bed_m.npy'
    reference_metadata = manifest.get('construction_reference')
    explicit_reference = (directory/reference_name).exists() or isinstance(reference_metadata,dict)
    if explicit_reference and (not isinstance(reference_metadata,dict)
            or reference_metadata.get('file') != reference_name
            or not isinstance(reference_metadata.get('semantics'),str)
            or not reference_metadata['semantics'].strip()):
        raise ValueError('saved construction reference requires manifest construction_reference {file, semantics}')
    names = ['manifest.json','channel_graph.json','bed_dem_float64.npy',
             'valid_mask.npy','td_ocean_mask.npy','td_original_bed_m.npy']
    if explicit_reference:
        names.append(reference_name)
    hashes = {name: file_sha256(directory/name) for name in names}
    sums_path = directory/'sha256sums.json'
    if sums_path.exists():
        expected = read_json('sha256sums.json')
        if any(name in expected and expected[name] != value for name,value in hashes.items()):
            raise ValueError('frozen product file hash differs from manifest sums')
    identity = hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    bed = np.load(directory/'bed_dem_float64.npy',mmap_mode='r')
    valid = np.load(directory/'valid_mask.npy',mmap_mode='r').astype(bool)
    ocean = np.load(directory/'td_ocean_mask.npy',mmap_mode='r').astype(bool)
    original = np.load(directory/'td_original_bed_m.npy',mmap_mode='r')
    if valid.shape != bed.shape or ocean.shape != bed.shape or original.shape != bed.shape:
        raise ValueError('frozen product masks differ from DEM geometry')
    if explicit_reference:
        reference = np.load(directory/reference_name,mmap_mode='r')
        if reference.shape != bed.shape or not np.isfinite(reference[valid]).all():
            raise ValueError('saved construction reference differs from DEM geometry or has invalid elevations')
        reference_semantics = reference_metadata['semantics']
    else:
        from .delta_network_site import SiteSpec, base_surface
        reference,_ = base_surface(SiteSpec(**manifest['site']),original,ocean)
        reference_semantics = 'TD land plus saved declared shelf parameters'
    boundary = np.zeros(bed.shape,bool)
    boundary[[0,-1],:] = True; boundary[:,[0,-1]] = True
    seeds = boundary & valid & ocean & (bed < sea_level_m)
    site = manifest['site']
    if list(bed.shape) != [site['nu'],site['nv']]:
        raise ValueError('site and frozen DEM geometry differ')
    if discharge_m3_s is None:
        roots = set(n['id'] for n in graph['nodes'])-{e['to'] for e in graph['edges']}
        if len(roots) != 1:
            raise ValueError('morphology product does not have one inlet')
        discharge_m3_s = next(n['Q_m3s'] for n in graph['nodes'] if n['id'] in roots)
    state,p = initialize_graph(graph,bed,site,valid,seeds,source_identity=identity,
        source_seed=manifest['source_world_seed'],algorithm_seed=manifest['world_seed'],
        hydraulic_config=hydraulic_config,discharge_m3_s=discharge_m3_s,
        solid_rate_m3_s=solid_rate_m3_s,erodible_thickness_m=erodible_thickness_m,
        porosity=porosity,control_spacing_m=control_spacing_m,
        geometry_tolerance_m=geometry_tolerance_m,subdivisions=subdivisions,sea_level_m=sea_level_m,
        control_cell_search_m=control_cell_search_m)
    difference = np.where(valid,np.asarray(bed)-reference,0.)
    area = state.spacing_m**2
    p['complex_network']['frozen_product'] = {
        'directory': str(directory.resolve()),'files_sha256':hashes,
        'td_source':manifest.get('td_source'),'valid_source_cells':int(valid.sum()),
        'unknown_cells':int((~valid).sum()),
        'declared_shelf_cells':None if explicit_reference else int((valid&ocean).sum()),
        'declaration':manifest.get('declaration'),
        'construction_reference':reference_semantics,
        'construction_reference_file':reference_name if explicit_reference else None,
        'construction_reference_metadata':copy.deepcopy(reference_metadata) if explicit_reference else None,
        'construction_reference_mode':'explicit saved array' if explicit_reference else 'historical declared-shelf fallback',
        'construction_fill_bulk_m3':float(np.maximum(difference,0.).sum()*area),
        'construction_cut_bulk_m3':float(np.maximum(-difference,0.).sum()*area),
        'construction_fill_solid_m3':float((np.maximum(difference,0.)*(1-porosity)).sum()*area),
        'construction_cut_solid_m3':float((np.maximum(-difference,0.)*(1-porosity)).sum()*area),
        'construction_cut_destination':'historical geological initial condition; not event supply',
        'erodible_layer_m':float(erodible_thickness_m),'porosity':float(porosity),
        'initial_section_bed_m':[[*n[:2],n[2]] for n in p['hydraulic_sections']['nodes']]}
    return _record(state,p),p


def coupled_evidence(state, progress):
    """Report finite budgets, actual mouth delivery and concrete changed cells."""
    info = progress['complex_network']
    initial = info.get('frozen_product',{})
    reports = progress.get('physical_cadence',{}).get('reports',[])
    inventories = {field:float(getattr(state,field).sum()) for field in
                   ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3')}
    inventory = sum(inventories.values())
    total = inventory+state.exported_solid_m3+state.unresolved_solid_m3
    incoming = math.fsum(r['delivered_solid_m3'] for r in reports)
    sections = {tuple(n[:2]):n[2] for n in progress['hydraulic_sections']['nodes']}
    changes = [[*row[:2],sections[tuple(row[:2])]-row[2]] for row in initial.get('initial_section_bed_m',[])]
    changes.sort(key=lambda row:-abs(row[2]))
    channel_exterior = None
    if initial:
        original = np.load(Path(initial['directory'])/'bed_dem_float64.npy',mmap_mode='r')
        owned = np.zeros(state.base_bed_m.shape,bool)
        for row in progress['integrated']['owner_cells']:
            owned[tuple(row[:2])] = True
        rise = state.bed_m-original
        eligible = state.valid_mask & ~owned & (original < 0.)
        candidates = np.where(eligible,rise,-np.inf)
        cell = tuple(int(i) for i in np.unravel_index(np.argmax(candidates),candidates.shape))
        if candidates[cell]>1e-9:
            model = [state.origin_xz_m[0]+cell[1]*state.spacing_m,
                     state.origin_xz_m[1]+cell[0]*state.spacing_m]
            channel_exterior = {'cell_zx':list(cell),'rise_m':float(candidates[cell]),
                'solid_increase_m3':float(candidates[cell]*state.spacing_m**2*(1-state.porosity[cell])),
                'outside_all_channel_footprints':True,
                'receiver_classification':'unclassified; may be bay, estuary or open water',
                'model_xz_m':model,'world_xz_m':model_to_world(info['site'],model).tolist()}
    mouths = {}
    for report in reports:
        for item in report['outlet_water']:
            key=tuple(item['mouth_zx'])
            mouths.setdefault(key,{'water_m3':0.,'gross_solid_m3':0.})['water_m3']+=item['water_m3']
        for item in report['outlet_delivery']:
            key=tuple(item['mouth_zx'])
            mouths.setdefault(key,{'water_m3':0.,'gross_solid_m3':0.})['gross_solid_m3']+=item['gross_solid_m3']
    from .coastal_delta_floodplain_coupling import water_evidence
    floodplain = water_evidence(state, progress)
    return {'physical_seconds':state.time_s,'initial_stock_solid_m3':info['initial_stock_solid_m3'],
        'current_inventory_solid_m3':inventory,'inventory_solid_m3':inventories,
        'exported_solid_m3':state.exported_solid_m3,
        'unresolved_solid_m3':state.unresolved_solid_m3,'delivered_solid_m3':incoming,
        'solid_residual_m3':total-info['initial_stock_solid_m3']-incoming,
        'undelivered_solid_m3':math.fsum(r['undelivered_solid_m3'] for r in reports),
        'undelivered_water_m3':math.fsum(r['undelivered_water_m3'] for r in reports),
        'channel_exterior_deposition':channel_exterior,
        'offshore_deposition':channel_exterior,
        'deposition_semantics':{
            'channel_exterior_deposition':'positive net bed rise in initially wet valid cells outside all channel footprints; receiving water is unclassified',
            'offshore_deposition':'deprecated compatibility alias of channel_exterior_deposition; does not establish an offshore or open-sea location',
            'positive_exterior_deposition_required':False,
            'mouth_delivery':'gross internal channel-to-receiving-water transfer, not whole-domain export'},
        **({'floodplain': floodplain} if floodplain is not None else {}),
        'unconnected_processes':([] if floodplain is not None else ['capacity-event overbank exchange'])
            + ['closed marine receiver water storage', 'bidirectional tidal-channel flow','wet zero-flow channel settling'],
        'largest_section_bed_changes_m':changes[:10],
        'mouth_delivery':[{'mouth_zx':list(k),**v} for k,v in sorted(mouths.items())],
        'hydraulic_nodes':len(progress['hydraulic_sections']['nodes']),
        'physical_edges':len(progress['route_geometry']['edges']),'cover_routes':len(progress['routes']),
        'last_hydraulics':progress['river_hydraulics'],'event_reports':reports}


def advance_cadence(state, progress, ticks, *, cadence_s, run_id, marine_config,
                    hydraulic_config, capacity_rule, inlet_solid_rate_m3_s,
                    active_layer_m=.1, max_velocity_m_s=2., floodplain_config=None):
    """Advance complete fixed event ticks; checkpoints may split only between ticks.

    Identity and tick ordinal are persisted. Calling N ticks at once or saving and
    loading between the same N ticks performs exactly the same physical events.
    """
    from .coastal_delta_hydraulic_event import advance_event_hydraulic
    from .coastal_delta_branching import _validate
    _validate(state, progress)
    if not isinstance(ticks, int) or ticks < 1 or not run_id or cadence_s <= 0 or not math.isfinite(cadence_s):
        raise ValueError('invalid cadence')
    identity = {'cadence_s': cadence_s, 'run_id': run_id, 'marine': asdict(marine_config),
                'hydraulic': asdict(hydraulic_config), 'capacity_rule': capacity_rule.identity(),
                'inlet_solid_rate_m3_s': inlet_solid_rate_m3_s, 'active_layer_m': active_layer_m,
                'max_velocity_m_s': max_velocity_m_s, 'fixed_topology': True}
    if floodplain_config is not None:
        identity['floodplain'] = floodplain_config.identity()
    identity = json.loads(json.dumps(identity))
    saved = progress.get('physical_cadence')
    if saved is not None and saved['identity'] != identity:
        raise ValueError('physical cadence or forcing differs from saved identity')
    p = copy.deepcopy(progress)
    cadence = p.setdefault('physical_cadence', {'identity': identity, 'completed_ticks': 0, 'reports': []})
    reports = []
    for _ in range(ticks):
        ordinal = cadence['completed_ticks']
        # Record cadence before entering the validated kernel.
        state = _record(state, p)
        state, report = advance_event_hydraulic(state, p, cadence_s, marine_config,
            input_id=f'{run_id}:tick:{ordinal}', hydraulic_config=hydraulic_config,
            inlet_solid_rate_m3_s=inlet_solid_rate_m3_s, capacity_rule=capacity_rule,
            active_layer_m=active_layer_m, max_velocity_m_s=max_velocity_m_s, fixed_topology=True,
            floodplain_config=floodplain_config)
        p = report['updated_progress']
        cadence = p['physical_cadence']
        summary = {k: v for k, v in report.items() if k != 'updated_progress'}
        cadence['reports'].append(summary)
        cadence['completed_ticks'] += 1
        reports.append(summary)
        state = _record(state, p)
    return state, p, reports
