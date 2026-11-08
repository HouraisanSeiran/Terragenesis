"""Independent native affine-cut geometry and actual channel port evidence."""
from collections import defaultdict, deque
import math
import numpy as np
from tools.audit_td_source_conforming_banks_v3 import require, assert_close, source_sample, wet_at, clip_patch, area, intervals_complete
from tools.audit_saved_source_conforming_banks import native_edge_polynomial
from tools.td_ported_junction_saved_audit_v2 import audit_mesh, boundary_coverage
from tools.td_ported_network_saved_audit import cross_plan, overlap_area, compare, match_ports, edge_contact, pair_key
from tools.audit_td_fine_bed_shards import digest, check_memory
from tools.audit_td_fine_bed_raster import _source
from tools.audit_td_source_conforming_banks_v3 import audit_function
from tools.audit_saved_source_conforming_banks import verify_incident_fans
from tools.td_ported_junction_saved_audit_v3 import EdgeCandidateIndex
PARAMETERS = dict(max_cut_m=4.0, conflict_tolerance_m=1e-09, bank_slope_h_per_v=2.0)
POLICY = {'schema': 'td-shared-port-channel-v1', 'metrics': 'unchanged_upstream_saved_node_section_width_depth_q', 'offsets': '[-width/2-depth*2,-width/2,width/2,width/2+depth*2]', 'bank_slope_h_per_v': 2.0, 'cuts': '[0,upstream_depth,upstream_depth,0]', 'midpoint': 'one_canonical_actual_arc_midpoint_with_flow_normal_direction', 'source': 'original_native_bilinear_minus_nonnegative_affine_cut_fans', 'center': 'unchanged_saved_node_depth_not_legacy_absolute_floor', 'node_geometry': 'degree1_terminal_strip_degree2_3_4_complete_directional_inner_port_ring_with_zero_cut_exterior_gap_controls', 'turn_controls': 'actual_polar_gap_greater_than_180deg_insert_zero_cut_bank_at_gap_bisector_radius_max_adjacent_radius', 'inset': 'min(0.4*half_arc_length,max(1m,1.5*outer_bank_offset))', 'terminal': 'source_relative_saved_node_metrics_with_original_terminal_and_clipping_evidence', 'wet': 'original_source_gates_and_conservative_whole_native_patch_wet_guard', 'selection': 'largest_original_land_component_then_safety_clipping_longest_directed_chain_and_connected_branches', 'acceptance': 'new_derived_geometry_never_inherit_06_acceptance_or_delete_parent_reasons', 'replacement': 'new_mesh_only_original06_is_separate_context_no_fine_transaction', 'connectivity': 'complete_three_actual_reverse_boundary_edges_and_whole_native_source_depth_coefficients', 'max_cut_m': 4.0, 'slope': 'diagnostic_only_no_hydraulic_acceptance'}
POLICY_SHA256 = digest(POLICY)
FLAGS = ('fine_generated', 'material_budget_verified', 'hydraulic_ready', 'hydraulic_solved', 'full_network_verified', 'natural_outlet_certified', 'bed_changed')

def seal(record):
    return dict(record, identity_sha256=digest(record))

def native_sample(hierarchy, selected, protection, point):
    height, reasons, provenance = _source(hierarchy['arrays'], hierarchy['metadata'], selected, np.asarray(point, float))
    unknown = hierarchy['arrays']['node_unknown_contact']
    if any((leaf < 0 or leaf >= len(unknown) or unknown[leaf] for leaf in provenance['contribution_leaf_ids'])):
        reasons = sorted(set(reasons) | {'unknown_native_owner'})
    wet = False
    if 'outside_native_dem' not in reasons:
        metadata, arrays = (hierarchy['metadata'], hierarchy['arrays'])
        column, row = np.floor((np.asarray(point) - metadata['origin_m_xz']) / metadata['spacing_m'] + 0.5).astype(int)
        stages = {item['leaf_id']: item['stage_m'] for item in protection['stage_by_leaf']}
        wet = row * arrays['height_m'].shape[1] + column in protection['covered_native_cell_ids']
        if height is not None:
            wet = wet or height < stages.get(int(arrays['contribution_owner'][row, column]), -math.inf)
    return dict(height_m=height, rejection_reasons=reasons, wet_source_support=bool(wet), **provenance)

def parent_safety(node, section, hierarchy, selected, protection):
    if section is None:
        return (['missing_saved_node_section'], None)
    reasons = set()
    if section.get('anchor') or any(('lake' in kind or 'anchor' in kind for kind in node.get('kinds', []))):
        reasons.add('original_anchor_or_lake')
    reasons.update(('original_safety:' + reason for reason in section.get('rejection_reasons', []) if any((word in reason for word in ('unknown', 'protected', 'anchor', 'nonfinite')))))
    depth, width = (section.get('depth_m'), section.get('width_m'))
    if not isinstance(depth, (int, float)) or not math.isfinite(depth) or (not 0.0 < depth <= 4.0):
        reasons.add('invalid_saved_node_depth')
    if not isinstance(width, (int, float)) or not math.isfinite(width) or width <= 0.0:
        reasons.add('invalid_saved_node_width')
    sample = native_sample(hierarchy, selected, protection, np.asarray(node['xyz_m'])[[0, 2]])
    reasons.update(sample['rejection_reasons'])
    return (sorted(reasons), sample)

def graph_components(node_ids, arcs):
    neighbors = {identifier: set() for identifier in node_ids}
    for arc in arcs:
        first, second = arc['node_ids']
        neighbors[first].add(second)
        neighbors[second].add(first)
    components, visited = ([], set())
    for identifier in sorted(node_ids):
        if identifier in visited:
            continue
        pending, members = ([identifier], [])
        visited.add(identifier)
        while pending:
            current = pending.pop()
            members.append(current)
            for neighbor in sorted(neighbors[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        components.append(sorted(members))
    return sorted(components, key=lambda members: (-len(members), members[0]))

def chain_record(node_ids, arcs, nodes):
    graph = geometry_graph(node_ids, [(arc['arc_id'], *arc['node_ids']) for arc in arcs], {identifier: node['xyz_m'] for identifier, node in nodes.items()})
    if graph['cycle_node_ids']:
        return dict(node_ids=[], arc_ids=[], plan_length_m=None, cycle_node_ids=graph['cycle_node_ids'])
    if not node_ids:
        return dict(node_ids=[], arc_ids=[], plan_length_m=0.0, cycle_node_ids=[])
    return dict(node_ids=graph['main_chain_node_ids'], arc_ids=graph['main_chain_arc_ids'], plan_length_m=graph['main_chain_length_m'], cycle_node_ids=[], source_xyz_m=[nodes[identifier]['xyz_m'] for identifier in graph['main_chain_node_ids']])

def independent_selection(hierarchy, paths, sections, protection, max_nodes):
    require(type(max_nodes) is int and 2 <= max_nodes <= 256, 'invalid selection node budget')
    nodes = {node['node_id']: node for node in paths['nodes']}
    arcs = {arc['arc_id']: arc for arc in paths['arcs'] if arc['kind'] == 'land_channel'}
    profiles = {item['node_id']: (number, item) for number, item in enumerate(sections['node_sections'])}
    original_nodes = sorted({identifier for arc in arcs.values() for identifier in arc['node_ids']})
    components = graph_components(original_nodes, arcs.values())
    mother = set(components[0]) if components else set()
    allowed, clipping = (set(), [])
    for identifier in sorted(mother):
        index, section = profiles.get(identifier, (None, None))
        reasons, sample = parent_safety(nodes[identifier], section, hierarchy, set(sections['selected_leaf_ids']), protection)
        if reasons:
            clipping.append(dict(node_id=identifier, rejection_reasons=reasons, parent_section_index=index, parent_rejection_reasons=[] if section is None else section.get('rejection_reasons', []), source_sample=sample, source_xyz_m=nodes[identifier]['xyz_m']))
        else:
            allowed.add(identifier)
    safe_arcs = [arc for arc in arcs.values() if set(arc['node_ids']) <= allowed]
    choices = []
    for component in graph_components(allowed, safe_arcs):
        component_set = set(component)
        members = [arc for arc in safe_arcs if set(arc['node_ids']) <= component_set]
        chain = chain_record(component, members, nodes)
        degree = defaultdict(int)
        for arc in members:
            for identifier in arc['node_ids']:
                degree[identifier] += 1
        choices.append((chain, component, members, degree))
    choices.sort(key=lambda choice: (-(choice[0]['plan_length_m'] or 0.0), -len(choice[1]), choice[1][0]))
    chain, available, members, degree = choices[0] if choices else (dict(node_ids=[], arc_ids=[], plan_length_m=0.0), [], [], {})
    trunk = chain['node_ids']
    budget = max_nodes - min(16, max_nodes // 4) if any((value >= 3 for value in degree.values())) and len(trunk) >= max_nodes else max_nodes
    window = trunk[:budget]
    if len(trunk) > budget:
        windows = [trunk[index:index + budget] for index in range(len(trunk) - budget + 1)]
        window = max(windows, key=lambda entries: (sum((degree.get(identifier, 0) >= 3 for identifier in entries)), math.fsum((profiles[identifier][1].get('representative_q_m3_s', 0.0) for identifier in entries))))
    selected = set(window)
    while len(selected) < max_nodes:
        frontier = []
        for arc in members:
            first, second = arc['node_ids']
            if (first in selected) != (second in selected):
                frontier.append((-float(profiles[first][1].get('representative_q_m3_s', 0.0)), arc['arc_id'], second if first in selected else first))
        if not frontier:
            break
        selected.add(min(frontier)[2])
    selected_arcs = sorted((arc['arc_id'] for arc in members if set(arc['node_ids']) <= selected))
    cut_arcs = [dict(arc_id=arc['arc_id'], node_ids=arc['node_ids'], reason='safety_clip' if not set(arc['node_ids']) <= allowed else 'node_budget_boundary') for arc in arcs.values() if set(arc['node_ids']) & selected and arc['arc_id'] not in selected_arcs]
    graph = seal(dict(schema='td-shared-port-land-graph-v1', parents=dict(paths=paths['identity_sha256'], ordinary=paths['ordinary_identity_sha256']), nodes=[nodes[identifier] for identifier in original_nodes], arcs=list(arcs.values()), original_land_arc_count=len(arcs), components=components, largest_component_node_ids=sorted(mother)))
    selection = seal(dict(schema='td-shared-port-selection-v1', policy_identity_sha256=POLICY_SHA256, graph_identity_sha256=graph['identity_sha256'], mother_component_node_ids=sorted(mother), safety_clipping=clipping, safe_component_node_ids=available, longest_selection_chain=chain, selected_node_ids=sorted(selected), selected_arc_ids=selected_arcs, budget_clipped_node_ids=sorted(set(available) - selected), boundary_arc_clipping=cut_arcs, max_nodes=max_nodes, selection_not_geometry_verified=True, selected_branch_node_ids=sorted((identifier for identifier in selected if sum((identifier in arcs[arc]['node_ids'] for arc in selected_arcs)) >= 3))))
    return (graph, selection)

def native_knots(hierarchy, first, last):
    origin = np.asarray(hierarchy['metadata']['origin_m_xz'], float)
    spacing = float(hierarchy['metadata']['spacing_m'])
    endpoints = (np.asarray([first, last], float) - origin) / spacing
    length = float(np.linalg.norm(np.asarray(last) - first))
    fractions = {0.0, 1.0}
    for axis in range(2):
        delta = endpoints[1, axis] - endpoints[0, axis]
        if abs(delta) <= 1e-14:
            continue
        low, high = sorted(endpoints[:, axis])
        for knot in range(math.floor(low) + 1, math.ceil(high)):
            fraction = float((knot - endpoints[0, axis]) / delta)
            if 1e-08 / length < fraction < 1.0 - 1e-08 / length:
                fractions.add(fraction)
    result = []
    for fraction in sorted(fractions):
        if not result or (fraction - result[-1]) * length > 1e-08:
            result.append(fraction)
    return result

def edge_functions(hierarchy, selected, first, last, cuts):
    first, last = (np.asarray(first, float), np.asarray(last, float))
    require(first.shape == last.shape == (2,) and np.isfinite([first, last, cuts]).all(), 'invalid native edge inputs')
    require(float(np.linalg.norm(last - first)) > 1e-10, 'degenerate affine-cut edge')
    cuts = np.asarray(cuts, float)
    require(cuts.shape == (2,) and cuts.min() >= 0.0 and (cuts.max() <= 4.0), 'edge violates no-fill/maxcut')
    fractions = native_knots(hierarchy, first, last)
    result = []
    for low, high in zip(fractions, fractions[1:]):
        start, end = (first + (last - first) * low, first + (last - first) * high)
        source = native_edge_polynomial(hierarchy, selected, start, end)
        first_depth = float(cuts[0]) if low == 0.0 else float(cuts[0] + (cuts[1] - cuts[0]) * low)
        last_depth = float(cuts[1]) if high == 1.0 else float(cuts[0] + (cuts[1] - cuts[0]) * high)
        depth = [first_depth, last_depth - first_depth, 0.0]
        coefficients = source['source_height_polynomial_m']
        result.append(dict(interval_t01=[low, high], start_xz_m=start.tolist(), end_xz_m=end.tolist(), source_coefficients_m_t012=coefficients, cut_coefficients_m_t012=depth, bed_coefficients_m_t012=(np.asarray(coefficients) - depth).tolist(), native_patch_row_column=source['native_patch_row_column'], native_cell_ids=[item['native_cell_id'] for item in source['provenance']]))
    return result

def audit_vertices(mesh, hierarchy, selected, protection):
    vertices = np.asarray(mesh['vertices_xyz_m'], float)
    depths = np.asarray(mesh['vertex_depths_m'], float)
    require(vertices.ndim == 2 and vertices.shape[1] == 3 and (depths.shape == (len(vertices),)) and np.isfinite(vertices).all() and np.isfinite(depths).all(), 'invalid channel vertices/cut depths')
    require(depths.min(initial=0.0) >= 0.0 and depths.max(initial=0.0) <= 4.0, 'channel vertices violate no-fill/maxcut')
    for point, depth in zip(vertices, depths):
        height, reasons = source_sample(hierarchy, selected, point[[0, 2]])
        require(height is not None and (not reasons), 'channel vertex lacks valid original source support')
        assert_close(height - point[1], depth, 'source-relative saved channel vertex', atol=1e-09)
        require(not wet_at(hierarchy, protection, point[[0, 2]], height) or depth == 0.0, 'channel cuts original wet vertex')
    return (vertices, depths)

def audit_native_triangle(points, cuts, hierarchy, selected, protection):
    points, cuts = (np.asarray(points, float), np.asarray(cuts, float))
    require(points.shape == (3, 2) and cuts.shape == (3,) and np.isfinite([*points.ravel(), *cuts]).all(), 'invalid native face')
    require(cuts.min() >= 0.0 and cuts.max() <= 4.0, 'whole affine face violates no-fill/maxcut')
    signed = cross_plan(points[1] - points[0], points[2] - points[0]) / 2.0
    require(signed > 1e-09, 'reversed/degenerate channel face')
    anchor = points[0]
    gradient = np.linalg.solve(points[1:] - anchor, cuts[1:] - cuts[0])
    coefficients = [float(cuts[0]), *gradient.tolist()]
    origin = np.asarray(hierarchy['metadata']['origin_m_xz'], float)
    spacing = float(hierarchy['metadata']['spacing_m'])
    height = hierarchy['arrays']['height_m']
    low = np.floor((points.min(axis=0) - origin) / spacing).astype(int)
    high = np.floor((points.max(axis=0) - origin) / spacing).astype(int)
    patches, measures = ([], [])
    for row in range(int(low[1]), int(high[1]) + 1):
        for column in range(int(low[0]), int(high[0]) + 1):
            corner = origin + np.array([column, row]) * spacing
            polygon = clip_patch(points, corner, spacing)
            if len(polygon) < 3 or area(polygon) <= 1e-12:
                continue
            require(0 <= row < height.shape[0] - 1 and 0 <= column < height.shape[1] - 1, 'native face outside original source')
            sample, reasons = source_sample(hierarchy, selected, corner + spacing / 2.0)
            require(sample is not None and (not reasons), 'native face touches invalid/protected/unknown support')
            polygon = np.asarray(polygon, float)
            patch_cuts = cuts[0] + (polygon - anchor) @ gradient
            require(patch_cuts.min() >= -1e-09 and patch_cuts.max() <= 4.0 + 1e-09, 'native face cut function out of bounds')
            for point, depth in zip(polygon, patch_cuts):
                value, reasons = source_sample(hierarchy, selected, point)
                require(value is not None and (not reasons), 'native face knot source invalid')
                require(not wet_at(hierarchy, protection, point, value) or depth <= 1e-09, 'native face knot cuts old wet support')
            native_values = [float(height[row, column]), float(height[row, column + 1]), float(height[row + 1, column]), float(height[row + 1, column + 1])]
            for delta in ((0, 0), (1, 0), (0, 1), (1, 1)):
                point = corner + np.asarray(delta) * spacing
                native_height = float(height[row + delta[1], column + delta[0]])
                require(not wet_at(hierarchy, protection, point, native_height) or patch_cuts.max() <= 1e-09, 'native face cuts protected wet patch support')
            measure = area(polygon)
            measures.append(measure)
            patches.append(dict(patch_row_column=[row, column], polygon_xz_m=polygon.tolist(), patch_origin_m_xz=corner.tolist(), native_spacing_m=spacing, native_height_m=native_values, bilinear_coefficients_m=[native_values[0], native_values[1] - native_values[0], native_values[2] - native_values[0], native_values[3] - native_values[2] - native_values[1] + native_values[0]], native_cell_ids=[row * height.shape[1] + column, row * height.shape[1] + column + 1, (row + 1) * height.shape[1] + column, (row + 1) * height.shape[1] + column + 1], projected_area_m2=measure))
    require(patches, 'face lacks any native source patch')
    assert_close(math.fsum(measures), signed, 'complete native patch face coverage', atol=1e-08)
    return dict(depth_origin_xz_m=anchor.tolist(), depth_coefficients_m_1xz=coefficients, native_patches=patches, projected_area_m2=signed)

def face_components(mesh):
    incidence = audit_mesh(mesh['vertices_xyz_m'], mesh['triangles'], check_overlap=False)
    neighbors = [set() for _ in mesh['triangles']]
    for sides in incidence.values():
        if len(sides) == 2:
            first, second = (sides[0]['triangle_index'], sides[1]['triangle_index'])
            neighbors[first].add(second)
            neighbors[second].add(first)
    components, visited = ([], set())
    for first in range(len(neighbors)):
        if first in visited:
            continue
        pending, members = ([first], [])
        visited.add(first)
        while pending:
            current = pending.pop()
            members.append(current)
            for neighbor in sorted(neighbors[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        components.append(sorted(members))
    return components

def port_boundary(mesh, profile, hierarchy, selected):
    require(len(profile) == 4, 'actual port requires complete four-point profile')
    coverage = boundary_coverage(mesh['vertices_xyz_m'], mesh['triangles'], profile)
    vertices = np.asarray(mesh['vertices_xyz_m'], float)
    cuts = np.asarray(mesh['vertex_depths_m'], float)
    incidence = audit_mesh(mesh['vertices_xyz_m'], mesh['triangles'], check_overlap=False)
    segments = []
    for number, (first, last) in enumerate(zip(profile, profile[1:])):
        start, end = np.asarray([first, last])[:, [0, 2]]
        vector = end - start
        denominator = float(vector @ vector)
        sides, intervals = ([], [])
        for entries in incidence.values():
            if len(entries) != 1:
                continue
            side = entries[0]
            indices = mesh['triangles'][side['triangle_index']]
            pair_ids = [indices[side['edge_index']], indices[(side['edge_index'] + 1) % 3]]
            pair = vertices[pair_ids]
            offsets = pair[:, [0, 2]] - start
            distances = np.abs(offsets[:, 0] * vector[1] - offsets[:, 1] * vector[0]) / math.sqrt(denominator)
            parameters = offsets @ vector / denominator
            if distances.max() > 1e-08 or parameters.min() < -1e-08 or parameters.max() > 1.0 + 1e-08:
                continue
            intervals.append(sorted(parameters.tolist()))
            functions = edge_functions(hierarchy, selected, pair[0, [0, 2]], pair[1, [0, 2]], cuts[pair_ids])
            sides.append(dict(triangle_index=side['triangle_index'], edge_index=side['edge_index'], points_xyz_m=pair.tolist(), vertex_indices=pair_ids, interval_t01=sorted(parameters.tolist()), native_pieces=functions))
        intervals_complete(intervals, 'full true boundary profile segment')
        segments.append(dict(profile_segment_index=number, points_xyz_m=[first, last], sides=sides))
    require(coverage, 'no actual channel port boundary')
    return segments

def shared_port(first_mesh, second_mesh, profile, hierarchy, selected):
    first = port_boundary(first_mesh, profile, hierarchy, selected)
    second = port_boundary(second_mesh, profile, hierarchy, selected)
    functions = []
    for number, (first_segment, second_segment) in enumerate(zip(first, second)):
        pair = np.asarray(profile[number:number + 2])[:, [0, 2]]
        vector = pair[1] - pair[0]
        groups = []
        for segment in (first_segment, second_segment):
            pieces = []
            for side in segment['sides']:
                for piece in side['native_pieces']:
                    points = np.asarray([piece['start_xz_m'], piece['end_xz_m']])
                    parameters = ((points - pair[0]) @ vector / (vector @ vector)).tolist()
                    pieces.append((side, piece, parameters))
            groups.append(pieces)
        knots = sorted({0.0, 1.0} | {value for group in groups for side, piece, parameters in group for value in parameters})
        for low, high in zip(knots, knots[1:]):
            if high - low <= 1e-12:
                continue
            midpoint = (low + high) / 2.0
            matches = []
            for group in groups:
                found = [(side, piece, parameters) for side, piece, parameters in group if min(parameters) - 1e-12 <= midpoint <= max(parameters) + 1e-12]
                require(len(found) == 1, 'shared native boundary missing or duplicated')
                matches.append(found[0])
            directions = [np.asarray(side['points_xyz_m'])[1, [0, 2]] - np.asarray(side['points_xyz_m'])[0, [0, 2]] for side, piece, parameters in matches]
            require(float(directions[0] @ directions[1]) < 0.0, 'shared midpoint boundary winding not reverse')
            transformed = []
            for side, piece, parameters in matches:
                offset = (low - parameters[0]) / (parameters[1] - parameters[0])
                scale = (high - low) / (parameters[1] - parameters[0])
                result = {}
                for key in ('source_coefficients_m_t012', 'cut_coefficients_m_t012', 'bed_coefficients_m_t012'):
                    constant, linear, quadratic = piece[key]
                    result[key] = [constant + linear * offset + quadratic * offset ** 2, (linear + 2.0 * quadratic * offset) * scale, quadratic * scale ** 2]
                transformed.append(result)
            for key in transformed[0]:
                assert_close(transformed[0][key], transformed[1][key], 'whole native shared midpoint ' + key, atol=1e-09)
            functions.append(dict(profile_segment_index=number, interval_t01=[low, high], first_side={key: matches[0][0][key] for key in ('triangle_index', 'edge_index')}, second_side={key: matches[1][0][key] for key in ('triangle_index', 'edge_index')}, **transformed[0]))
    return functions

def projected_conflicts(mesh, other_mesh):
    points = np.asarray(mesh['vertices_xyz_m'], float).reshape(-1, 3)
    other_points = np.asarray(other_mesh['vertices_xyz_m'], float).reshape(-1, 3)
    shapes = points[np.asarray(mesh['triangles'], int).reshape(-1, 3)][:, :, [0, 2]]
    others = other_points[np.asarray(other_mesh['triangles'], int).reshape(-1, 3)][:, :, [0, 2]]
    if len(others) == 0:
        return []
    low, high = (others.min(axis=1), others.max(axis=1))
    result = []
    for number, shape in enumerate(shapes):
        candidates = np.flatnonzero(np.all(high > shape.min(axis=0), axis=1) & np.all(low < shape.max(axis=0), axis=1))
        for other in candidates:
            if overlap_area(shape, others[other]) > 1e-08:
                result.append([number, int(other)])
    return result

def geometry_graph(node_ids, connections, positions):
    neighbors = {identifier: set() for identifier in node_ids}
    directed = {identifier: [] for identifier in node_ids}
    for arc_id, first, second in connections:
        require(first in neighbors and second in neighbors and (first != second), 'connection endpoints absent')
        neighbors[first].add(second)
        neighbors[second].add(first)
        directed[first].append((second, arc_id))
    components, visited = ([], set())
    for identifier in sorted(node_ids):
        if identifier in visited:
            continue
        pending, members = ([identifier], [])
        visited.add(identifier)
        while pending:
            current = pending.pop()
            members.append(current)
            for neighbor in sorted(neighbors[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        components.append(sorted(members))
    indegree = dict.fromkeys(node_ids, 0)
    for edges in directed.values():
        for neighbor, arc in edges:
            indegree[neighbor] += 1
    queue = deque(sorted((identifier for identifier in node_ids if indegree[identifier] == 0)))
    distance, predecessor = (dict.fromkeys(node_ids, 0.0), {})
    while queue:
        current = queue.popleft()
        for neighbor, arc in sorted(directed[current], key=lambda edge: edge[1]):
            length = float(np.linalg.norm(np.asarray(positions[neighbor])[[0, 2]] - np.asarray(positions[current])[[0, 2]]))
            proposed = distance[current] + length
            if proposed > distance[neighbor]:
                distance[neighbor] = proposed
                predecessor[neighbor] = (current, arc)
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)
    cycles = sorted((identifier for identifier, degree in indegree.items() if degree))
    chain_nodes, chain_arcs = ([], [])
    if node_ids and (not cycles):
        endpoint = max(sorted(node_ids), key=lambda identifier: distance[identifier])
        chain_nodes = [endpoint]
        while chain_nodes[-1] in predecessor:
            previous, arc = predecessor[chain_nodes[-1]]
            chain_nodes.append(previous)
            chain_arcs.append(arc)
        chain_nodes.reverse()
        chain_arcs.reverse()
    return dict(components=components, directed=directed, cycle_node_ids=cycles, main_chain_node_ids=chain_nodes, main_chain_arc_ids=chain_arcs, main_chain_length_m=distance[chain_nodes[-1]] if chain_nodes else 0.0)

def native_record(hierarchy, selected, first, last):
    native = native_edge_polynomial(hierarchy, selected, first, last)
    row, column = native['native_patch_row_column']
    metadata, height = (hierarchy['metadata'], hierarchy['arrays']['height_m'])
    values = [float(height[row, column]), float(height[row, column + 1]), float(height[row + 1, column]), float(height[row + 1, column + 1])]
    return dict(patch_row_column=[row, column], native_cell_ids=[row * height.shape[1] + column, row * height.shape[1] + column + 1, (row + 1) * height.shape[1] + column, (row + 1) * height.shape[1] + column + 1], native_height_m=values, bilinear_coefficients_m=[values[0], values[1] - values[0], values[2] - values[0], values[3] - values[2] - values[1] + values[0]], patch_origin_m_xz=(np.asarray(metadata['origin_m_xz']) + np.array([column, row]) * metadata['spacing_m']).tolist(), native_spacing_m=metadata['spacing_m'], source_coefficients_m_t012=native['source_height_polynomial_m'])

def patch_wet(hierarchy, protection, native):
    arrays = hierarchy['arrays']
    stages = {item['leaf_id']: item['stage_m'] for item in protection['stage_by_leaf']}
    return bool(set(native['native_cell_ids']) & set(protection['covered_native_cell_ids'])) or any((arrays['height_m'].ravel()[cell] < stages.get(int(arrays['contribution_owner'].ravel()[cell]), -math.inf) for cell in native['native_cell_ids']))

def profile_evidence(center, flow, section, hierarchy, selected, protection):
    width, depth = (float(section['width_m']), float(section['depth_m']))
    require(math.isfinite(width) and width > 0.0 and math.isfinite(depth) and (0.0 < depth <= 4.0), 'invalid_saved_profile_metrics')
    normal = np.array([-flow[1], flow[0]])
    offsets = [-width / 2.0 - 2.0 * depth, -width / 2.0, width / 2.0, width / 2.0 + 2.0 * depth]
    cuts, points, samples, reasons = ([0.0, depth, depth, 0.0], [], [], set())
    for offset, cut in zip(offsets, cuts):
        point = np.asarray(center) + normal * offset
        sample = native_sample(hierarchy, selected, protection, point)
        samples.append(sample)
        reasons.update(sample['rejection_reasons'])
        if sample['height_m'] is None:
            reasons.add('profile_source_unknown')
        if cut > 0.0 and sample['wet_source_support']:
            reasons.add('profile_wet_cut_refused')
        points.append([float(point[0]), None if sample['height_m'] is None else sample['height_m'] - cut, float(point[1])])
    segments = []
    if not reasons:
        for number in range(3):
            start, end = np.asarray(points[number:number + 2])[:, [0, 2]]
            pieces = []
            for piece in edge_functions(hierarchy, selected, start, end, cuts[number:number + 2]):
                native = native_record(hierarchy, selected, piece['start_xz_m'], piece['end_xz_m'])
                gate = native_sample(hierarchy, selected, protection, (np.asarray(piece['start_xz_m']) + piece['end_xz_m']) / 2.0)
                reasons.update(gate['rejection_reasons'])
                depth_coefficients = piece['cut_coefficients_m_t012'][:2]
                if max(depth_coefficients[0], sum(depth_coefficients)) > 0.0 and patch_wet(hierarchy, protection, native):
                    reasons.add('profile_native_patch_wet_cut_refused')
                pieces.append(dict(interval_t01=piece['interval_t01'], start_xz_m=piece['start_xz_m'], end_xz_m=piece['end_xz_m'], source=native, depth_coefficients_m_t01=depth_coefficients))
            segments.append(dict(profile_segment_index=number, points_xyz_m=points[number:number + 2], native_pieces=pieces))
    return dict(profile_xyz_m=points, cut_depths_m=cuts, transverse_offsets_m=offsets, width_m=width, depth_m=depth, bank_run_m=2.0 * depth, bank_slope_h_per_v=2.0, source_samples=samples, profile_segments=segments, status='refused' if reasons else 'candidate', rejection_reasons=sorted(reasons))

def check_identity(record):
    require(record['identity_sha256'] == digest({key: value for key, value in record.items() if key != 'identity_sha256'}), 'shared record content identity differs')

def audit_midpoint(record, paths, sections, hierarchy, protection, pins):
    check_identity(record)
    require(record['schema'] == 'td-shared-midpoint-port-v1' and record['policy_identity_sha256'] == POLICY_SHA256, 'midpoint schema/policy differs')
    nodes = {node['node_id']: node for node in paths['nodes']}
    arcs = {arc['arc_id']: arc for arc in paths['arcs'] if arc['kind'] == 'land_channel'}
    profiles = {item['node_id']: (number, item) for number, item in enumerate(sections['node_sections'])}
    arc = arcs[record['arc_id']]
    require(record['inputs'] == pins and record['node_ids'] == arc['node_ids'], 'midpoint actual arc/source pins differ')
    require(record['parents'] == dict(paths=paths['identity_sha256'], sections=sections['identity_sha256'], hierarchy=hierarchy['identity_sha256'], source=hierarchy['metadata']['source_identity_sha256']), 'midpoint original parent identities differ')
    positions = [nodes[identifier]['xyz_m'] for identifier in arc['node_ids']]
    compare(record['source_arc_xyz_m'], positions, 'original midpoint arc xyz')
    first, last = np.asarray(positions)[:, [0, 2]]
    length = float(np.linalg.norm(last - first))
    require(length > 1e-08, 'zero length original arc')
    center, flow = ((first + last) / 2.0, (last - first) / length)
    index, section = profiles[arc['node_ids'][0]]
    require(record['upstream_section_index'] == index and record['upstream_parent_section'] == section and (record['representative_q_m3_s'] == section.get('representative_q_m3_s')), 'midpoint changed upstream prior/Q')
    compare(record['midpoint_xz_m'], center.tolist(), 'canonical midpoint')
    compare(record['flow_unit_xz'], flow.tolist(), 'canonical flow normal')
    compare(record['length_m'], length, 'original arc length')
    reasons = set()
    flow_value = section.get('representative_q_m3_s')
    if not isinstance(flow_value, (int, float)) or not math.isfinite(flow_value) or flow_value < 0.0:
        reasons.add('invalid_saved_upstream_q')
    for identifier in arc['node_ids']:
        safety, sample = parent_safety(nodes[identifier], profiles.get(identifier, (None, None))[1], hierarchy, set(sections['selected_leaf_ids']), protection)
        reasons.update(safety)
    try:
        expected_profile = profile_evidence(center, flow, section, hierarchy, set(sections['selected_leaf_ids']), protection)
        compare(record['profile'], expected_profile, 'canonical whole source-minus-cut midpoint profile')
        reasons.update(expected_profile['rejection_reasons'])
    except ValueError as error:
        if str(error) == 'invalid_saved_profile_metrics':
            require(record['profile'] == {}, 'invalid metrics exposed a profile')
            reasons.add(str(error))
        else:
            raise
    require(record['status'] == ('refused' if reasons else 'candidate') and record['rejection_reasons'] == sorted(reasons), 'midpoint candidate/refusal differs from independent source evidence')
    require(record['old_absolute_profile_acceptance_inherited'] is False, 'midpoint inherited original absolute floor acceptance')
    for flag in FLAGS:
        require(record[flag] is False, 'midpoint promoted capability')
    return not reasons

def audit_node_edges(record, hierarchy, selected, protection):
    mesh = record['geometry']
    vertices = np.asarray(mesh['vertices_xyz_m'], float)
    depths = np.asarray(mesh['vertex_depths_m'], float)
    index = EdgeCandidateIndex(hierarchy['metadata']['spacing_m'], hierarchy['metadata']['origin_m_xz'])
    boundary_bindings = {}
    for arm in record['arms']:
        for number, pair in enumerate(zip(arm['midpoint_vertex_ids'], arm['midpoint_vertex_ids'][1:])):
            boundary_bindings[tuple(sorted(pair))] = dict(kind='shared_midpoint_open_geometric_port', arc_id=arm['arc_id'], midpoint_port_identity_sha256=arm['midpoint_port_identity_sha256'], profile_segment_index=number, hydraulic_boundary_claimed=False)
    terminal_ids = mesh.get('terminal_vertex_ids', [])
    for number, pair in enumerate(zip(terminal_ids, terminal_ids[1:])):
        boundary_bindings[tuple(sorted(pair))] = dict(kind='source_relative_terminal_open_section', profile_segment_index=number, terminal_evidence=record['terminal_evidence'], hydraulic_boundary_claimed=False)
    faces, coverage = ({}, defaultdict(list))
    for number, indices in enumerate(mesh['triangles']):
        identifier = 'shared:' + record['node_id'] + ':' + str(number)
        faces[identifier] = dict(triangle_id=identifier, vertices_xyz_m=vertices[indices].tolist(), vertex_ids=indices, replacement_role=mesh['triangle_roles'][number])
        for edge in range(3):
            index.add(identifier, edge, vertices[[indices[edge], indices[(edge + 1) % 3]]])
    edges = {}
    for proof in record['edge_proofs']:
        check_identity(proof)
        require(proof['segment_id'] not in edges and proof['status'] == 'candidate' and (not proof['rejection_reasons']), 'duplicate/refused node edge')
        require(proof['policy_identity_sha256'] == POLICY_SHA256, 'node edge policy differs')
        points = np.asarray([proof['start_xz_m'], proof['end_xz_m']])
        actual, values, binding = ([], None, None)
        for identifier, edge_index, pair, fractions in index.matching_sides(*points):
            triangle_index = int(identifier.rsplit(':', 1)[1])
            indices = mesh['triangles'][triangle_index]
            pair_ids = [indices[edge_index], indices[(edge_index + 1) % 3]]
            pair_depths = depths[pair_ids]
            reconstructed = pair_depths[0] + fractions * (pair_depths[1] - pair_depths[0])
            for number, point in enumerate(points):
                for endpoint, depth in zip(pair[:, [0, 2]], pair_depths):
                    if np.array_equal(point, endpoint):
                        reconstructed[number] = depth
            require(reconstructed.min() >= 0.0 and reconstructed.max() <= 4.0, 'strict independently reconstructed node edge cut')
            if values is not None:
                assert_close(values, reconstructed, 'whole actual shared node edge cut', atol=1e-09)
            values = reconstructed
            coverage[identifier, edge_index].append(sorted(fractions.tolist()))
            actual.append(dict(triangle_id=identifier, triangle_index=triangle_index, edge_index=edge_index, points_xyz_m=pair.tolist()))
            local_binding = boundary_bindings.get(tuple(sorted(pair_ids)))
            if local_binding is not None:
                require(binding is None or binding == local_binding, 'conflicting profile boundary bindings')
                binding = local_binding
        actual.sort(key=lambda side: (side['triangle_index'], side['edge_index']))
        require(1 <= len(actual) <= 2, 'missing/nonmanifold node native edge')
        compare(proof['sides'], actual, 'complete actual native edge side census')
        source = native_record(hierarchy, selected, *points)
        compare(proof['source'], source, 'independent complete native edge source')
        expected_depth = [float(values[0]), float(values[1] - values[0])]
        compare(proof['depth_coefficients_m_t01'], expected_depth, 'independent native edge cut coefficients')
        for side, saved in zip(actual, proof['side_depth_knots']):
            require(saved['triangle_id'] == side['triangle_id'] and saved['edge_index'] == side['edge_index'], 'false saved cut side')
            require(min(saved['depth_knots_m']) >= 0.0 and max(saved['depth_knots_m']) <= 4.0, 'saved cut side violates strict gate')
            compare(saved['depth_knots_m'], values.tolist(), 'whole saved side cut knots')
        require(len(proof['side_depth_knots']) == len(actual), 'missing node edge cut side')
        compare(proof['source_samples'], [native_sample(hierarchy, selected, protection, point) for point in points], 'native edge endpoint samples')
        require(not patch_wet(hierarchy, protection, source) or values.max() == 0.0, 'native edge cuts protected wet patch')
        if binding is None:
            if len(actual) == 1:
                require(values.max() == 0.0, 'unbound nonzero node bank cut')
            binding = dict(kind='source_bank_zero_cut' if len(actual) == 1 else 'shared_node_internal_edge')
        compare(proof['boundary_condition'], binding, 'true geometric/open boundary classification')
        require(proof['common_function_identity_sha256'] == digest({key: proof[key] for key in ('start_xz_m', 'end_xz_m', 'source', 'depth_coefficients_m_t01', 'policy_identity_sha256')}), 'node whole function identity differs')
        edges[proof['segment_id']] = proof
    for identifier in faces:
        for edge_index in range(3):
            intervals_complete(coverage[identifier, edge_index], 'entire node triangle native edge coverage')
    require(len(record['source_functions']) == len(faces), 'node full face function census differs')
    fans, seen = ([], set())
    for function in record['source_functions']:
        check_identity(function)
        identifier = function['original_triangle']['triangle_id']
        require(identifier in faces and identifier not in seen and (function['status'] == 'candidate') and (not function['rejection_reasons']) and (function['policy_identity_sha256'] == POLICY_SHA256), 'duplicate/refused/wrong face function')
        seen.add(identifier)
        compact = audit_function(function, faces[identifier], edges, hierarchy, selected, PARAMETERS, protection)
        fans.extend(compact['fans'])
        for fan in function['fans']:
            require(min(fan['depth_at_vertices_m']) >= 0.0 and max(fan['depth_at_vertices_m']) <= 4.0, 'saved fan violates strict no-fill/maxcut')
            for patch in fan['native_patches']:
                require(not patch_wet(hierarchy, protection, patch) or max(fan['depth_at_vertices_m']) == 0.0, 'saved fan cuts wet native patch')
    verify_incident_fans(fans)
    return edges

def port_descriptor(record, arm, edges):
    mesh, segments = (record['geometry'], [])
    ids = arm['midpoint_vertex_ids']
    for number, (first, last) in enumerate(zip(ids, ids[1:])):
        pair = [mesh['vertices_xyz_m'][first], mesh['vertices_xyz_m'][last]]
        pieces = []
        for proof in edges.values():
            boundary = proof['boundary_condition']
            if boundary.get('arc_id') != arm['arc_id'] or boundary.get('profile_segment_index') != number:
                continue
            require(len(proof['sides']) == 1, 'midpoint descriptor not actual boundary')
            side = proof['sides'][0]
            native, cuts = (proof['source']['source_coefficients_m_t012'], proof['depth_coefficients_m_t01'])
            start, end = np.asarray(pair)[:, [0, 2]]
            vector = end - start
            interval = sorted((float((np.asarray(proof[key]) - start) @ vector / (vector @ vector)) for key in ('start_xz_m', 'end_xz_m')))
            pieces.append(dict(interval_t01=interval, start_xz_m=proof['start_xz_m'], end_xz_m=proof['end_xz_m'], source_coefficients_m_t012=native, bed_coefficients_m_t012=[native[0] - cuts[0], native[1] - cuts[1], native[2]], depth_coefficients_m_t01=cuts, segment_id=proof['segment_id'], side=dict(kind='node', node_id=record['node_id'], hub_node_id=record['node_id'], triangle_index=side['triangle_index'], edge_index=side['edge_index'], points_xyz_m=side['points_xyz_m'])))
        intervals_complete([piece['interval_t01'] for piece in pieces], 'entire descriptor native profile function')
        segments.append(dict(points_xyz_m=pair, profile_segment_index=number, pieces=pieces))
    return dict(kind='node', hub_node_id=record['node_id'], node_id=record['node_id'], arc_id=arm['arc_id'], outer_node_id='midpoint:' + arm['arc_id'], midpoint_port_identity_sha256=arm['midpoint_port_identity_sha256'], original_profile_xyz_m=[mesh['vertices_xyz_m'][index] for index in ids], segments=segments, boundary_condition='shared_midpoint_geometry_port_only', hydraulic_boundary_claimed=False)

def audit_node_geometry(record, local_ports, paths, sections, hierarchy, protection, clipping):
    mesh, degree = (record['geometry'], record['degree'])
    require(1 <= degree <= 4 and len(record['arms']) == degree, 'invalid actual node half-arm census')
    require(0 < len(mesh['triangles']) <= 256 and len(mesh['triangles']) == len(mesh['triangle_roles']), 'missing/oversized node geometry')
    vertices, depths = audit_vertices(mesh, hierarchy, set(sections['selected_leaf_ids']), protection)
    audit_mesh(mesh['vertices_xyz_m'], mesh['triangles'])
    require(len(face_components(mesh)) == 1, 'node patch arms lack real face connections')
    require({index for triangle in mesh['triangles'] for index in triangle} == set(range(len(vertices))), 'unused/unsupported node vertex')
    center = np.asarray(record['source_xyz_m'])[[0, 2]]
    section = record['parent_section']
    ports = {port['arc_id']: port for port in local_ports}
    require(len(ports) == degree and {arm['arc_id'] for arm in record['arms']} == set(ports), 'missing/duplicate half arm')
    diagnostics, groups = ([], [])
    for arm in record['arms']:
        port = ports[arm['arc_id']]
        profile, flow = (port['profile'], np.asarray(port['flow_unit_xz']))
        require(arm['node_ids'] == port['node_ids'] and arm['midpoint_port_identity_sha256'] == port['identity_sha256'] and (arm['flow_unit_xz'] == port['flow_unit_xz']) and (arm['profile_xyz_m'] == profile['profile_xyz_m']), 'arm changed canonical midpoint evidence')
        outer_ids, inner_ids = (arm['midpoint_vertex_ids'], arm['inner_vertex_ids'])
        require(len(outer_ids) == len(inner_ids) == 4 and len(set(outer_ids + inner_ids)) == 8, 'arm lost distinct four-point ports')
        compare(vertices[outer_ids].tolist(), profile['profile_xyz_m'], 'actual midpoint vertices')
        compare(depths[outer_ids].tolist(), profile['cut_depths_m'], 'canonical midpoint cuts')
        radial = np.asarray(port['midpoint_xz_m']) - center
        half_length = float(np.linalg.norm(radial))
        radial /= half_length
        bank_extent = max((abs(value) for value in profile['transverse_offsets_m']))
        require(bank_extent < half_length, 'profile width conflicts with half-arm length')
        compare(arm['half_length_m'], half_length, 'actual half arc length')
        normal = np.array([-flow[1], flow[0]])
        if degree == 1:
            terminal = profile_evidence(center, flow, section, hierarchy, set(sections['selected_leaf_ids']), protection)
            require(terminal['status'] == 'candidate', 'terminal profile lacks source evidence')
            compare(record['terminal_evidence'], dict(classification='actual_land_terminal' if record['original_land_degree'] == 1 else 'clipped_fragment_boundary', original_node_section_index=record['node_section_index'], original_profile_xyz_m=section.get('cross_section_xyz_m', []), derived_terminal_profile=terminal, clipping=clipping, unchanged_absolute_floor_claimed=False, hydraulic_boundary_claimed=False), 'whole open terminal evidence')
            require(mesh['terminal_vertex_ids'] == inner_ids, 'terminal not actual four-point inner port')
            compare(vertices[inner_ids].tolist(), terminal['profile_xyz_m'], 'actual terminal geometry')
            compare(depths[inner_ids].tolist(), terminal['cut_depths_m'], 'terminal prior cut depths')
            require(arm['inset_m'] == 0.0, 'terminal replaced by invented inset')
        else:
            inset = min(0.4 * half_length, max(1.0, 1.5 * bank_extent))
            compare(arm['inset_m'], inset, 'actual directional inner inset')
            expected = center + radial * inset + np.asarray(profile['transverse_offsets_m'])[:, None] * normal
            assert_close(vertices[inner_ids][:, [0, 2]], expected, 'actual directional inner profile', atol=1e-09)
            compare(depths[inner_ids].tolist(), profile['cut_depths_m'], 'inner profile unchanged cut depths')
            groups.append((math.atan2(radial[1], radial[0]), inner_ids if cross_plan(radial, normal) > 0.0 else inner_ids[::-1]))
        require(depths[outer_ids[0]] == depths[outer_ids[-1]] == depths[inner_ids[0]] == depths[inner_ids[-1]] == 0.0, 'actual outside bank cut nonzero')
        triangles = [triangle for triangle, role in zip(mesh['triangles'], mesh['triangle_roles']) if role == dict(region='half_arm', arc_id=arm['arc_id'])]
        require(len(triangles) == 6, 'half arm not full three-quad strip')
        expected_faces = []
        for number in range(3):
            for indices in ([outer_ids[number], outer_ids[number + 1], inner_ids[number]], [outer_ids[number + 1], inner_ids[number + 1], inner_ids[number]]):
                points = vertices[indices][:, [0, 2]]
                expected_faces.append(indices if cross_plan(points[1] - points[0], points[2] - points[0]) >= 0.0 else indices[::-1])
        require(triangles == expected_faces, 'half-arm triangles do not cover actual midpoint-to-node profile')
        boundary_coverage(mesh['vertices_xyz_m'], triangles, vertices[outer_ids].tolist())
        boundary_coverage(mesh['vertices_xyz_m'], triangles, vertices[inner_ids].tolist())
        midpoint_bed = (profile['profile_xyz_m'][1][1] + profile['profile_xyz_m'][2][1]) / 2.0
        center_bed = record['center_source_sample']['height_m'] - section['depth_m']
        upstream, downstream = (center_bed, midpoint_bed) if port['node_ids'][0] == record['node_id'] else (midpoint_bed, center_bed)
        diagnostics.append(dict(arc_id=arm['arc_id'], half_length_m=half_length, center_bed_m=center_bed, midpoint_mean_bottom_bed_m=midpoint_bed, flow_downhill_slope_m_per_m=(upstream - downstream) / half_length, adverse_bed_slope=upstream < downstream, diagnostic_only=True, fine_or_hydraulic_profile_claimed=False))
    compare(record['bed_slope_diagnostics'], diagnostics, 'diagnostic prior center-bed slopes')
    if degree >= 2:
        require(record['terminal_evidence'] is None and (not mesh.get('terminal_vertex_ids')), 'multiarms falsely claim terminal')
        center_id = mesh['center_vertex_id']
        assert_close(vertices[center_id, [0, 2]], center, 'actual original center coordinates', atol=1e-09)
        require(depths[center_id] == section['depth_m'], 'changed original node center depth')
        base = [index for angle, ids in sorted(groups) for index in ids]
        expanded, controls = ([], iter(mesh['outer_bank_control_vertex_ids']))
        used_controls = []
        for first, second in zip(base, base[1:] + base[:1]):
            expanded.append(first)
            first_delta, second_delta = vertices[[first, second]][:, [0, 2]] - center
            gap = math.atan2(cross_plan(first_delta, second_delta), float(first_delta @ second_delta)) % (2.0 * math.pi)
            if gap > math.pi + 1e-10:
                control = next(controls, None)
                require(control is not None, 'wide turn lacks actual outside bank control')
                angle = math.atan2(first_delta[1], first_delta[0]) + gap / 2.0
                radius = max(float(np.linalg.norm(first_delta)), float(np.linalg.norm(second_delta)))
                assert_close(vertices[control, [0, 2]], center + radius * np.array([math.cos(angle), math.sin(angle)]), 'actual wide-turn exterior control', atol=1e-09)
                require(depths[control] == 0.0, 'outside control bank cut nonzero')
                expanded.append(control)
                used_controls.append(control)
        require(next(controls, None) is None and mesh['ring_vertex_indices'] == expanded and (len(set(expanded)) == len(expanded)), 'omitted/duplicate/unnecessary ring control')
        core = [triangle for triangle, role in zip(mesh['triangles'], mesh['triangle_roles']) if role == dict(region='node_ring', node_id=record['node_id'])]
        require(len(core) == len(expanded), 'node core incomplete variable-degree port ring')
        for triangle, first, second in zip(core, expanded, expanded[1:] + expanded[:1]):
            require(cross_plan(vertices[first, [0, 2]] - center, vertices[second, [0, 2]] - center) > 1e-10 and triangle == [first, second, center_id], 'core ring not positive actual star fan')
    else:
        require(mesh['ring_vertex_indices'] == mesh['outer_bank_control_vertex_ids'] == [] and len(mesh['triangles']) == 6, 'degree1 substituted hub ring or incomplete terminal strip')
    require(len(mesh['triangles']) == degree * 6 + (len(mesh['ring_vertex_indices']) if degree >= 2 else 0), 'extraneous undeclared node face')
    for indices in mesh['triangles']:
        audit_native_triangle(vertices[indices][:, [0, 2]], depths[indices], hierarchy, set(sections['selected_leaf_ids']), protection)
    edges = audit_node_edges(record, hierarchy, set(sections['selected_leaf_ids']), protection)
    descriptors = [port_descriptor(record, arm, edges) for arm in record['arms']]
    compare(record['port_proofs'], descriptors, 'actual complete midpoint port descriptors')
    require(len(record['inner_port_proofs']) == (degree if degree >= 2 else 0), 'missing/duplicate inner core interfaces')
    for arm, proof in zip(record['arms'], record['inner_port_proofs']):
        check_identity(proof)
        require(proof['arc_id'] == arm['arc_id'] and proof['profile_vertex_ids'] == arm['inner_vertex_ids'] and (proof['kind'] == 'complete_inner_four_point_port') and (proof['status'] == 'candidate') and (proof['policy_identity_sha256'] == POLICY_SHA256), 'inner port provenance differs')
        expected_segments = []
        for number, (first, last) in enumerate(zip(arm['inner_vertex_ids'], arm['inner_vertex_ids'][1:])):
            pair = vertices[[first, last]].tolist()
            pieces = []
            start, end = np.asarray(pair)[:, [0, 2]]
            vector = end - start
            for edge in edges.values():
                sides = [side for side in edge['sides'] if side['points_xyz_m'] in (pair, pair[::-1])]
                if not sides:
                    continue
                require(len(sides) == 2 and sides[0]['points_xyz_m'] == sides[1]['points_xyz_m'][::-1], 'inner port lacks two true reverse sides')
                roles = [mesh['triangle_roles'][side['triangle_index']] for side in sides]
                require(dict(region='half_arm', arc_id=arm['arc_id']) in roles and dict(region='node_ring', node_id=record['node_id']) in roles, 'inner port attaches wrong arm/core')
                interval = sorted((float((np.asarray(edge[key]) - start) @ vector / (vector @ vector)) for key in ('start_xz_m', 'end_xz_m')))
                pieces.append(dict(segment_id=edge['segment_id'], interval_t01=interval, side_refs=[{key: side[key] for key in ('triangle_id', 'triangle_index', 'edge_index')} for side in sides], reverse_seam=True, common_function_identity_sha256=edge['common_function_identity_sha256']))
            intervals_complete([piece['interval_t01'] for piece in pieces], 'entire inner core native function')
            expected_segments.append(dict(profile_segment_index=number, points_xyz_m=pair, native_pieces=pieces))
        compare(proof['profile_segments'], expected_segments, 'complete actual inner port native refs')
    return descriptors

def audit_node(record, local_ports, paths, sections, hierarchy, protection, pins, clipping):
    check_identity(record)
    require(record['schema'] == 'td-shared-port-node-piece-v1' and record['policy_identity_sha256'] == POLICY_SHA256 and (record['parameters'] == PARAMETERS) and (record['inputs'] == pins) and (record['wet_protection'] == protection), 'node schema/parameters/original pins differ')
    nodes = {node['node_id']: node for node in paths['nodes']}
    profiles = {section['node_id']: (number, section) for number, section in enumerate(sections['node_sections'])}
    identifier = record['node_id']
    node, (index, section) = (nodes[identifier], profiles[identifier])
    require(record['parents'] == dict(paths=paths['identity_sha256'], sections=sections['identity_sha256'], hierarchy=hierarchy['identity_sha256'], source=hierarchy['metadata']['source_identity_sha256']) and record['source_xyz_m'] == node['xyz_m'] and (record['node_section_index'] == index) and (record['parent_section'] == section) and (record['center_depth_m'] == section['depth_m']), 'node changed original metrics/provenance')
    for flag in FLAGS:
        require(record[flag] is False, 'node promoted capability')
    safety, sample = parent_safety(node, section, hierarchy, set(sections['selected_leaf_ids']), protection)
    compare(record['center_source_sample'], sample, 'original node center source support')
    original_degree = sum((identifier in arc['node_ids'] for arc in paths['arcs'] if arc['kind'] == 'land_channel'))
    require(record['degree'] == len(local_ports) and record['original_land_degree'] == original_degree and (len({port['arc_id'] for port in local_ports}) == len(local_ports)), 'actual selected/original node degree differs')
    reasons = set(safety)
    if not 1 <= len(local_ports) <= 4:
        reasons.add('requires_one_to_four_actual_half_arms')
    for port in local_ports:
        require(identifier in port['node_ids'], 'foreign midpoint attached to node')
        if port['status'] != 'candidate':
            reasons.add('midpoint_refused:' + port['arc_id'])
    geometry_error, descriptors = (None, [])
    if reasons:
        require(not record['geometry']['triangles'] and (not record['arms']) and (not record['edge_proofs']) and (not record['source_functions']) and (not record['port_proofs']) and (not record['inner_port_proofs']), 'parent-refused node contributes unsupported geometry')
    else:
        try:
            descriptors = audit_node_geometry(record, local_ports, paths, sections, hierarchy, protection, clipping)
        except (ValueError, np.linalg.LinAlgError) as error:
            geometry_error = str(error)
    require(record['status'] in ('candidate', 'refused'), 'unknown node status')
    if record['status'] == 'candidate':
        require(not reasons and geometry_error is None and (not record['rejection_reasons']) and descriptors, 'node candidate lacks independent whole geometry proof: ' + str(geometry_error or sorted(reasons)))
        require(record['construction_checks'] == dict(positive_nonoverlapping_projection=True, center_inside_simple_directional_ring=len(local_ports) >= 2, complete_inner_port_functions=len(local_ports) >= 2, independent_audit_passed=False), 'node construction claims differ from actual geometry')
    else:
        require(record['rejection_reasons'] and (reasons or geometry_error), 'node refusal has no independent evidence')
        require(reasons <= set(record['rejection_reasons']), 'node omitted original parent refusal evidence')
        descriptors = []
    return (dict(node_id=identifier, generation_status=record['status'], source_native_geometry_verified=record['status'] == 'candidate', refusal_evidence_verified=record['status'] == 'refused', parent_refusal_witnesses=sorted(reasons), independent_geometry_refusal=geometry_error), descriptors)

class FragmentAudit:

    def __init__(self):
        self.mesh = dict(schema='td-shared-port-fragment-mesh-v1', vertices_xyz_m=[], triangles=[], face_origins=[], old06_mesh_included=False, parametric_only=True, **{flag: False for flag in FLAGS})
        self.rows, self.ports, self.seams, self.closed = ([], {}, [], set())
        self.face_points = []

    def consider(self, record, pin, descriptors):
        identifier = record['node_id']
        row = dict(node_id=identifier, pin=pin, source_xyz_m=record['source_xyz_m'], generation_status=record['status'], composition_status='refused', generation_rejection_reasons=record['rejection_reasons'], rejection_reasons=[], arc_ids=[arm['arc_id'] for arm in record['arms']], bed_slope_diagnostics=record['bed_slope_diagnostics'])
        if record['terminal_evidence'] is not None:
            row['terminal_port'] = dict(classification=record['terminal_evidence']['classification'], profile_xyz_m=record['terminal_evidence']['derived_terminal_profile']['profile_xyz_m'], hydraulic_boundary_claimed=False)
        self.rows.append(row)
        if record['status'] == 'refused':
            row['rejection_reasons'] = ['node_generation_refused']
            return row
        reasons, seams = (set(), [])
        if len(self.mesh['triangles']) + len(record['geometry']['triangles']) > 20000:
            reasons.add('fragment_face_budget_exceeded')
        for port in descriptors:
            prior = self.ports.get(port['arc_id'])
            if prior is None:
                continue
            if port['arc_id'] in self.closed:
                reasons.add('midpoint_more_than_two_sides')
                continue
            if prior['midpoint_port_identity_sha256'] != port['midpoint_port_identity_sha256']:
                reasons.add('canonical_midpoint_identity_mismatch')
            seam, reason = match_ports(port, prior)
            if reason is not None:
                reasons.add('midpoint_seam:' + reason)
            else:
                seam.update(arc_id=port['arc_id'], first_node_id=port['node_id'], second_node_id=prior['node_id'], midpoint_port_identity_sha256=port['midpoint_port_identity_sha256'])
                seams.append(seam)
        allowed = {pair_key(seam['original_profile_xyz_m'][number:number + 2]) for seam in seams for number in range(3)}
        allowed_points = [np.asarray(point)[[0, 2]] for seam in seams for point in seam['original_profile_xyz_m']]
        mesh = record['geometry']
        vertices = np.asarray(mesh['vertices_xyz_m'])
        projected = vertices[np.asarray(mesh['triangles'], int)][:, :, [0, 2]]
        if self.face_points:
            previous = np.asarray(self.face_points)
            shapes = previous[:, :, [0, 2]]
            low, high = (shapes.min(axis=1), shapes.max(axis=1))
            for number, shape in enumerate(projected):
                nearby = np.flatnonzero(np.all(high + 1e-08 >= shape.min(axis=0), axis=1) & np.all(low - 1e-08 <= shape.max(axis=0), axis=1))
                indices = mesh['triangles'][number]
                for other in nearby:
                    if overlap_area(shape, shapes[other]) > 1e-08:
                        reasons.add('new_node_projected_overlap')
                    for edge in range(3):
                        pair = vertices[[indices[edge], indices[(edge + 1) % 3]]].tolist()
                        for old_edge in range(3):
                            old_pair = previous[other][[old_edge, (old_edge + 1) % 3]].tolist()
                            if edge_contact(pair, old_pair) and (pair_key(pair) not in allowed or pair != old_pair[::-1]):
                                reasons.add('partial_unbound_wrong_direction_or_nonmanifold_contact')
                            for endpoints, segment in ((pair, old_pair), (old_pair, pair)):
                                first, last = np.asarray(segment)[:, [0, 2]]
                                vector = last - first
                                squared_length = float(vector @ vector)
                                for point in np.asarray(endpoints)[:, [0, 2]]:
                                    fraction = float((point - first) @ vector / squared_length)
                                    distance = abs(cross_plan(vector, point - first)) / math.sqrt(squared_length)
                                    if 0.0 <= fraction <= 1.0 and distance <= 1e-08 and (not any((np.max(np.abs(point - allowed_point)) <= 1e-08 for allowed_point in allowed_points))):
                                        reasons.add('unbound_vertex_or_t_junction_contact')
        if reasons:
            row['rejection_reasons'] = sorted(reasons)
            return row
        offset = len(self.mesh['vertices_xyz_m'])
        self.mesh['vertices_xyz_m'].extend(mesh['vertices_xyz_m'])
        self.mesh['triangles'].extend([[index + offset for index in triangle] for triangle in mesh['triangles']])
        for number, (indices, role) in enumerate(zip(mesh['triangles'], mesh['triangle_roles'])):
            self.mesh['face_origins'].append(dict(node_id=identifier, triangle_index=number, role=role))
            self.face_points.append(vertices[indices].tolist())
        for port in descriptors:
            if port['arc_id'] not in self.ports:
                self.ports[port['arc_id']] = port
        self.closed.update((seam['arc_id'] for seam in seams))
        self.seams.extend(seams)
        row['composition_status'] = 'selected'
        check_memory()
        return row

    def finish(self, paths, sections, selection, port_rows, pins):
        nodes = {node['node_id']: node for node in paths['nodes']}
        arcs = {arc['arc_id']: arc for arc in paths['arcs'] if arc['kind'] == 'land_channel'}
        selected = sorted((row['node_id'] for row in self.rows if row['composition_status'] == 'selected'))
        actual_arcs = [arcs[identifier] for identifier in sorted(self.closed)]
        for seam in self.seams:
            require({seam['first_node_id'], seam['second_node_id']} == set(arcs[seam['arc_id']]['node_ids']), 'shared port does not join two original arc endpoints')
        components = graph_components(selected, actual_arcs)
        longest = chain_record(selected, actual_arcs, nodes)
        require(not longest['cycle_node_ids'], 'actual geometric channel graph contains directed cycle')
        main_component = next((component for component in components if longest['node_ids'] and longest['node_ids'][0] in component), [])
        main_arcs = {arc['arc_id'] for arc in actual_arcs if set(arc['node_ids']) <= set(main_component)}
        degree = defaultdict(int)
        for arc in actual_arcs:
            for identifier in arc['node_ids']:
                degree[identifier] += 1
        open_ports = [dict(node_id=port['node_id'], arc_id=arc, midpoint_port_identity_sha256=port['midpoint_port_identity_sha256'], profile_xyz_m=port['original_profile_xyz_m'], reason='other_half_arm_not_composition_selected', boundary_condition='shared_midpoint_geometry_port_only', hydraulic_boundary_claimed=False) for arc, port in sorted(self.ports.items()) if arc not in self.closed]
        terminals = [dict(node_id=row['node_id'], **row['terminal_port'], reason='geometric_terminal_open_section') for row in self.rows if row['composition_status'] == 'selected' and 'terminal_port' in row]
        mesh_points = np.asarray(self.mesh['vertices_xyz_m']).reshape(-1, 3)
        topology = dict(schema='td-shared-port-channel-topology-v1', metrics_status='candidate_unverified', verified=False, components=[dict(component_id=number, node_ids=component, arc_ids=[arc['arc_id'] for arc in actual_arcs if set(arc['node_ids']) <= set(component)], bounds_xyz_m=[np.asarray([nodes[node]['xyz_m'] for node in component]).min(axis=0).tolist(), np.asarray([nodes[node]['xyz_m'] for node in component]).max(axis=0).tolist()]) for number, component in enumerate(components)], component_count=len(components), joined_arc_ids=sorted(self.closed), joined_arc_count=len(self.closed), longest_directed_path=longest, branch_node_ids=sorted((identifier for identifier, count in degree.items() if count >= 3)), branch_arc_ids=sorted(main_arcs - set(longest['arc_ids'])), other_component_arc_ids=sorted(self.closed - main_arcs), open_ports=open_ports, terminal_open_ports=terminals, source_terrain={key: paths.get(key) for key in ('origin_m_xz', 'spacing_m', 'grid_shape')}, geometry_bounds_xyz_m=[mesh_points.min(axis=0).tolist(), mesh_points.max(axis=0).tolist()] if len(mesh_points) else None, source_identity_sha256=paths['source_identity_sha256'], no_node_id_only_connections=True, **{flag: False for flag in FLAGS})
        attempted = set(selection['selected_arc_ids'])
        manifest = dict(schema='td-shared-port-channel-v1', policy=POLICY, policy_identity_sha256=POLICY_SHA256, parameters=PARAMETERS, inputs=pins, selected_node_ids=selected, selected_arc_ids=sorted(self.closed), attempted_arc_ids=selection['selected_arc_ids'], nodes=self.rows, ports=port_rows, shared_midpoint_seams=self.seams, replacement=dict(candidate_replaced_06_triangle_ids=[number for number, arc in enumerate(sections['mesh']['triangle_arc_ids']) if arc in self.closed], independent_old_context_triangle_ids=[number for number, arc in enumerate(sections['mesh']['triangle_arc_ids']) if arc not in attempted], partial_or_refused_selected_arc_ids=sorted(attempted - self.closed), original_06_in_fragment_mesh=False, old_packages_changed=False, fine_replacement_committed=False, material_effects_generated=False), metrics_status='candidate_unverified', independent_audit_passed=False, **{flag: False for flag in FLAGS})
        return (manifest, topology)
