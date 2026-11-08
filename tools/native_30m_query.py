"""Read-only scoped access to a fully cold-validated finite native river bundle."""
import math
import numpy as np

NOT_IMPLEMENTED = {'lake', 'backwater', 'floodplain_2d', 'natural_outlet', 'infinite_world'}
SPATIAL_SCOPES = {'terrain_surface', 'd8_topology', 'local_runoff', 'diagnostic_discharge',
                  'design_discharge', 'channel_section', 'hydraulics', 'bed_change', 'solid_inventory'}
UNITS = {'terrain_surface': 'm', 'd8_topology': 'flat native cell id; -1 terminal',
         'local_runoff': 'm3/s per active cell; interval x cell',
         'diagnostic_discharge': 'm3/s instantaneous known accumulation',
         'design_discharge': 'm3/s declared routed storm peak; not bankfull',
         'channel_section': 'columns: width_m, normal_depth_m, source_slope, carved_slope',
         'hydraulics': 'm3 water inventory; time edge x node',
         'bed_change': 'm relative to initial nodal bed; time edge x node',
         'solid_inventory': 'solid m3; time edge x node x [mobile,loose,rock_removed]'}


class ScopeRefusal(ValueError):
    def __init__(self, reason):
        self.reason_code = reason
        super().__init__(reason)


def _complete(env):
    from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge
    top = env['arrays']['topology.npz']
    result = accumulate_network_discharge(top['receiver'], top['valid_mask'].astype(np.float64),
        top['valid_mask'], terminal_kind=top['terminal_kind'],
        upstream_unknown_mask=top['upstream_unknown_mask'])
    return result['complete_mask']


def _diagnostic_mask(env, ids):
    shape = env['arrays']['source.npz']['field'].shape
    origin = env['arrays']['source.npz']['origin_native_xz']
    product = env['diagnostic']
    meta = product['metadata']
    rows = ids // shape[1] + origin[1] - meta['origin_native_cells'][1]
    cols = ids % shape[1] + origin[0] - meta['origin_native_cells'][0]
    h, w = meta['shape_zx']
    if np.any((rows < 0) | (rows >= h) | (cols < 0) | (cols >= w)):
        raise ScopeRefusal('stage_absent')
    mask = np.zeros((h, w), bool)
    mask[rows, cols] = True
    return mask, rows, cols


def require_available(env, scope, requested_mask, *, semantics=None, as_natural_outlet=False):
    if scope in NOT_IMPLEMENTED:
        raise ScopeRefusal('stage_not_implemented')
    if scope in ('water_ledger', 'solid_ledger'):
        raise ScopeRefusal('scope_not_spatial_use_audit')
    if scope not in SPATIAL_SCOPES:
        raise ScopeRefusal('stage_absent')
    arrays = env['arrays']
    source = arrays.get('source.npz')
    if source is None:
        raise ScopeRefusal('stage_absent')
    shape = source['field'].shape
    if not isinstance(requested_mask, np.ndarray) or requested_mask.dtype != np.bool_ or requested_mask.shape != shape:
        raise ScopeRefusal('outside_window')
    ids = np.flatnonzero(requested_mask)
    if not ids.size:
        raise ScopeRefusal('empty_request')
    if not source['resolved_mask'].ravel()[ids].all():
        missing = ids[~source['resolved_mask'].ravel()[ids]]
        origin = source['origin_native_xz']
        nx, nz = missing % shape[1] + origin[0], missing // shape[1] + origin[1]
        covered = np.zeros(missing.size, bool)
        for record in env['manifest']['source_records']:
            ox, oz = record['native_origin_xz']
            h, w = record['shape_zx']
            covered |= (nx >= ox) & (nx < ox+w) & (nz >= oz) & (nz < oz+h)
        raise ScopeRefusal('unresolved_border' if covered.any() else 'out_of_tile')
    top = arrays.get('topology.npz')
    if scope != 'terrain_surface':
        if top is None:
            raise ScopeRefusal('stage_absent')
        if not top['valid_mask'].ravel()[ids].all():
            raise ScopeRefusal('inactive_cell')
        if not _complete(env).ravel()[ids].all():
            raise ScopeRefusal('upstream_unknown')
    expected_semantics = {'local_runoff': 'soil_bucket_catchment',
                          'diagnostic_discharge': 'instantaneous_diagnostic',
                          'design_discharge': 'storm_event_routed_peak'}
    if semantics is not None and semantics != expected_semantics.get(scope):
        raise ScopeRefusal('semantics_mismatch')
    if as_natural_outlet:
        if top is not None and np.any(top['terminal_kind'].ravel()[ids] == 'retained'):
            raise ScopeRefusal('gate_refuses_retained_as_outlet')
        raise ScopeRefusal('natural_outlet_not_certified')
    if scope == 'terrain_surface':
        return source['field'].ravel()[ids].copy()
    if scope == 'd8_topology':
        return top['receiver'].ravel()[ids].copy()
    if scope == 'diagnostic_discharge':
        from terrain_pipeline.surface_rivers.metric_network_discharge_product import require_complete_discharge
        if 'diagnostic' not in env:
            raise ScopeRefusal('stage_absent')
        mask, rows, cols = _diagnostic_mask(env, ids)
        if not env['diagnostic']['arrays']['complete_mask'][rows, cols].all():
            raise ScopeRefusal('upstream_unknown')
        require_complete_discharge(env['diagnostic'], mask)
        return env['diagnostic']['arrays']['known_routed_q_m3_s'][rows, cols].copy()
    if scope == 'local_runoff':
        event = arrays.get('event.npz')
        if event is None:
            raise ScopeRefusal('stage_absent')
        r0, r1, c0, c1 = env['json_records']['selection.json']['chosen']['subwindow_rc']
        rows, cols = ids // shape[1], ids % shape[1]
        if np.any((rows < r0) | (rows >= r1) | (cols < c0) | (cols >= c1)):
            raise ScopeRefusal('stage_absent')
        local_ids = (rows-r0)*(c1-c0) + cols-c0
        positions = np.searchsorted(event['active_cells'], local_ids)
        safe = np.minimum(positions, event['active_cells'].size-1)
        if np.any(positions >= event['active_cells'].size) or not np.array_equal(event['active_cells'][safe], local_ids):
            raise ScopeRefusal('stage_absent')
        return event['local_q_m3_s'][:, positions].copy()
    section = arrays.get('section.npz')
    if section is None:
        raise ScopeRefusal('stage_absent')
    lookup = {int(cell): index for index, cell in enumerate(section['node_cell_ids'])}
    if any(int(cell) not in lookup for cell in ids):
        raise ScopeRefusal('stage_absent')
    nodes = np.array([lookup[int(cell)] for cell in ids], np.int64)
    if scope == 'design_discharge':
        return section['design_q_m3_s'][nodes].copy()
    if scope == 'channel_section':
        return np.column_stack([section['width_m'][nodes], section['normal_depth_m'][nodes],
             section['source_slope_per_m'][nodes], arrays['reach_context.npz']['node_slope_per_m'][nodes]]).copy()
    if 'dynamics' not in env:
        raise ScopeRefusal('stage_absent')
    dyn = env['dynamics']['arrays']
    if scope == 'hydraulics':
        return dyn['water_volume_m3'][:, nodes].copy()
    if scope == 'bed_change':
        return (dyn['node_bed_m'][:, nodes] - dyn['node_bed_m'][0, nodes]).copy()
    return np.stack([dyn[k][:, nodes] for k in ('mobile_solid_m3', 'loose_solid_m3', 'rock_removed_m3')], axis=-1).copy()


def query_point(env, x, z, *, native=False, scope='terrain_surface', semantics=None, as_natural_outlet=False):
    if scope in NOT_IMPLEMENTED:
        raise ScopeRefusal('stage_not_implemented')
    if scope in ('water_ledger', 'solid_ledger'):
        raise ScopeRefusal('scope_not_spatial_use_audit')
    if scope not in SPATIAL_SCOPES:
        raise ScopeRefusal('stage_absent')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (x, z)):
        raise ScopeRefusal('outside_window')
    if native:
        if int(x) != x or int(z) != z:
            raise ScopeRefusal('native_coordinates_must_be_integers')
        nx, nz = int(x), int(z)
    else:
        nx, nz = math.floor(x / 30.0), math.floor(z / 30.0)
    source = env['arrays']['source.npz']
    ox, oz = source['origin_native_xz']
    row, col = nz-int(oz), nx-int(ox)
    if not (0 <= row < source['field'].shape[0] and 0 <= col < source['field'].shape[1]):
        raise ScopeRefusal('outside_window')
    mask = np.zeros(source['field'].shape, bool)
    mask[row, col] = True
    value = require_available(env, scope, mask, semantics=semantics, as_natural_outlet=as_natural_outlet)
    answer = {'resolved': True, 'scope': scope, 'units': UNITS[scope], 'values': value.tolist(),
            'requested_xz': [x, z], 'coordinate_units': 'native cells' if native else 'm',
            'sampled_native_xz': [nx, nz], 'sampling': 'native node' if native else 'floor_to_native_30m_node',
            'elevation_m': float(source['field'][row, col]),
            'terminal_kind': str(env['arrays']['topology.npz']['terminal_kind'][row, col]),
            'numerical_identity_sha256': env['manifest'].get('diagnostic_identity_sha256', env['manifest']['identity_sha256'])}
    if scope == 'local_runoff':
        answer['time_edges_seconds'] = env['arrays']['event.npz']['time_edges_s'].tolist()
    elif scope == 'diagnostic_discharge':
        answer['interval_seconds'] = list(env['diagnostic']['metadata']['interval_seconds'])
    elif scope in ('hydraulics', 'bed_change', 'solid_inventory'):
        answer['time_edges_seconds'] = env['dynamics']['arrays']['time_seconds'].tolist()
    elif scope in ('design_discharge', 'channel_section'):
        edges = env['arrays']['event.npz']['time_edges_s']
        answer['design_event_window_seconds'] = [float(edges[0]), float(edges[-1])]
        answer['design_q_is_bankfull'] = False
    return answer


def census(env):
    top = env['arrays']['topology.npz']
    source = env['arrays']['source.npz']
    labels, counts = np.unique(top['terminal_kind'], return_counts=True)
    complete = _complete(env)
    return {'scope': 'entire declared saved window; no clipping',
            'shape_zx': list(source['field'].shape), 'resolved_cells': int(source['resolved_mask'].sum()),
            'unresolved_cells': int((~source['resolved_mask']).sum()),
            'upstream_unknown_seed_cells': int(top['upstream_unknown_mask'].sum()),
            'incomplete_valid_cells': int((top['valid_mask'] & ~complete).sum()),
            'terminal_kind': {str(k): int(v) for k, v in zip(labels, counts)},
            'catchment_cells': (int(env['arrays']['selection.npz']['catchment_mask'].sum())
                                if 'selection.npz' in env['arrays'] else None),
            'channel_nodes': (int(env['arrays']['section.npz']['node_cell_ids'].size)
                              if 'section.npz' in env['arrays'] else None)}
