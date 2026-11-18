"""Finite fixed-section sediment replay driven by a freshly solved channel trace."""
import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.surface_rivers.metric_sediment import SedimentDomain, SedimentForcing, solve_sediment


def produce_supply(network, water_forcing, *, terrain_identity, mouth_nodes, rock_floor_m,
                   initial_alluvium_bulk_m3, initial_mobile_solid_m3, is_lake,
                   material, bed_material_provenance, bank_material_provenance,
                   initial_water_m3, hydraulic_config=None, sediment_config=None):
    """Solve a bounded fixed-section scenario; bank erosion is not represented.

    Each packet corresponds to one committed hydraulic step. All initial stocks,
    including water, must be declared; no concentration is inferred.
    """
    for value in (terrain_identity, bed_material_provenance, bank_material_provenance):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('terrain and material provenance required')
    if initial_water_m3 is None or initial_mobile_solid_m3 is None:
        raise ValueError('declared initial water and mobile stocks required')
    if np.any(network.terminal_kind == 'unknown_boundary'):
        raise ValueError('unknown hydraulic boundary')
    if not isinstance(mouth_nodes, dict) or not mouth_nodes:
        raise ValueError('mouth node mapping required')
    nodes = list(mouth_nodes.values())
    if (any(not isinstance(k, str) or not k.strip() for k in mouth_nodes)
            or any(type(n) is not int or n < 0 or n >= network.receiver.size for n in nodes)
            or len(set(nodes)) != len(nodes)
            or any(network.terminal_kind[n] != 'open_outflow' for n in nodes)
            or set(nodes) != set(np.flatnonzero(network.terminal_kind == 'open_outflow'))):
        raise ValueError('mouths must identify every open outlet exactly once')
    hydraulic = solve_channel(network, water_forcing, initial_water_m3, hydraulic_config)
    if hydraulic['metadata']['status'] != 'complete':
        raise ValueError('unsupported hydraulic failed prefix')
    h = hydraulic['arrays']
    hydraulic_id = identity(h, hydraulic['metadata'])
    geometry_id = network.source_identity_sha256
    domain = SedimentDomain(network.receiver, network.length_m * network.width_m, network.width_m,
        network.bed_elevation_m, rock_floor_m, initial_alluvium_bulk_m3, is_lake,
        network.terminal_kind == 'open_outflow', geometry_id, bed_material_provenance)
    forcing = SedimentForcing(h['time_seconds'], h['volume_m3'][:-1], h['depth_m'][:-1],
        h['outflow_q_m3_s'], np.broadcast_to(network.bed_slope, h['outflow_q_m3_s'].shape).copy(),
        np.zeros_like(h['outflow_q_m3_s']), hydraulic_id, geometry_id, 'solved fixed-section hydraulic steps')
    sediment = solve_sediment(domain, forcing, material, initial_mobile_solid_m3, sediment_config)
    if sediment['metadata']['status'] != 'complete':
        raise ValueError('unsupported sediment failed prefix: ' + sediment['metadata']['failure_reason'])
    s = sediment['arrays']
    indices = np.searchsorted(h['time_seconds'], s['trace_time_seconds'][:-1], side='right') - 1
    exports = np.zeros_like(h['outflow_q_m3_s'])
    np.add.at(exports, indices, s['step_exported_solid_m3'])
    packets = []
    for mouth, node in mouth_nodes.items():
        for i, (start, end) in enumerate(zip(h['time_seconds'][:-1], h['time_seconds'][1:])):
            packets.append(dict(mouth_id=mouth, interval_id=str(i), start_s=float(start), end_s=float(end), duration_s=float(end - start),
                water_m3=float(h['boundary_outflow_volume_m3'][i, node]), solid_m3=float(exports[i, node])))
    return dict(terrain_identity=terrain_identity, hydrology_identity=water_forcing.source_identity_sha256,
        hydraulic_identity=hydraulic_id, geometry_identity=geometry_id, sediment_identity=sediment['identity_sha256'],
        bed_material_provenance=bed_material_provenance, bank_material_provenance=bank_material_provenance,
        scope='finite frozen hydraulics, fixed rectangular sections; lakes are zero-dimensional well-mixed stores with settling and advective bypass, without shear entrainment; no bank erosion or construction excavation',
        mouth_nodes=dict(mouth_nodes), packets=packets, hydraulic=hydraulic, sediment=sediment)


SUPPLY_SCHEMA = 'finite-sediment-supply-v1'


def _supply_bundle(supply):
    """Include full solved traces so the consumer can audit each exported packet."""
    arrays = {prefix + key: value for prefix, bundle in
              (('hydraulic__', supply['hydraulic']), ('sediment__', supply['sediment']))
              for key, value in bundle['arrays'].items()}
    metadata = {key: value for key, value in supply.items() if key not in ('hydraulic', 'sediment')}
    metadata.update(schema=SUPPLY_SCHEMA, units={'time': 's', 'water': 'm3', 'solid': 'm3'},
                    hydraulic_metadata=supply['hydraulic']['metadata'],
                    sediment_metadata=supply['sediment']['metadata'])
    return {'arrays': arrays, 'metadata': metadata, 'identity_sha256': identity(arrays, metadata)}


def _validate_supply_bundle(bundle):
    from terrain_pipeline.surface_rivers.metric_sediment import validate_sediment
    a, m = bundle['arrays'], bundle['metadata']
    if (m.get('schema') != SUPPLY_SCHEMA or m.get('units') != {'time': 's', 'water': 'm3', 'solid': 'm3'}
            or identity(a, m) != bundle['identity_sha256']):
        raise ValueError('invalid supply schema, units or identity')
    h = {k[11:]: v for k, v in a.items() if k.startswith('hydraulic__')}
    s = {k[10:]: v for k, v in a.items() if k.startswith('sediment__')}
    if len(h) + len(s) != len(a):
        raise ValueError('unexpected supply arrays')
    if identity(h, m['hydraulic_metadata']) != m['hydraulic_identity']:
        raise ValueError('invalid hydraulic identity')
    validate_sediment({'arrays': s, 'metadata': m['sediment_metadata'], 'identity_sha256': m['sediment_identity']})
    if (m['hydraulic_metadata']['status'] != 'complete' or
            m['sediment_metadata']['hydraulic_identity_sha256'] != m['hydraulic_identity'] or
            m['sediment_metadata']['geometry_identity_sha256'] != m['geometry_identity']):
        raise ValueError('inconsistent supply source identities')
    for key in ('terrain_identity', 'hydrology_identity', 'hydraulic_identity', 'geometry_identity',
                'sediment_identity', 'bed_material_provenance', 'bank_material_provenance'):
        if not isinstance(m.get(key), str) or not m[key].strip():
            raise ValueError('missing source or stock provenance')
    mapping = m['mouth_nodes']
    outlets = set(np.flatnonzero(s['domain_open_boundary']).tolist())
    if (not isinstance(mapping, dict) or not mapping or any(not isinstance(k, str) or not k.strip()
            or type(v) is not int for k, v in mapping.items()) or len(set(mapping.values())) != len(mapping)
            or set(mapping.values()) != outlets):
        raise ValueError('invalid mouth binding')
    times = h['time_seconds']
    expected = {(mouth, str(i)) for mouth in mapping for i in range(len(times) - 1)}
    packets = m['packets']
    if not isinstance(packets, list) or len(packets) != len(expected):
        raise ValueError('invalid packet inventory')
    seen = set()
    for packet in packets:
        if not isinstance(packet, dict) or set(packet) != {'mouth_id', 'interval_id', 'start_s', 'end_s', 'duration_s', 'water_m3', 'solid_m3'}:
            raise ValueError('invalid packet schema')
        key = (packet['mouth_id'], packet['interval_id'])
        if key not in expected or key in seen:
            raise ValueError('invalid packet identity')
        seen.add(key)
        values = [packet[k] for k in ('start_s', 'end_s', 'duration_s', 'water_m3', 'solid_m3')]
        if any(type(x) not in (float, int) or not np.isfinite(x) for x in values):
            raise ValueError('invalid packet values')
        i, node = int(key[1]), mapping[key[0]]
        start, end, duration, water, solid = values
        step = (s['trace_time_seconds'][:-1] >= start) & (s['trace_time_seconds'][:-1] < end)
        if (start != times[i] or end != times[i + 1] or duration != end - start or duration <= 0
                or water < 0 or solid < 0 or water != h['boundary_outflow_volume_m3'][i, node]
                or not np.isclose(solid, s['step_exported_solid_m3'][step, node].sum(), rtol=1e-12, atol=1e-12)):
            raise ValueError('packet does not match solved exports and interval')


def save_supply(path, supply):
    """Publish once; return the external SHA-256 required to read the product."""
    from terrain_pipeline.common_infra import save_bundle, file_sha256
    save_bundle(path, _supply_bundle(supply), validator=_validate_supply_bundle)
    return file_sha256(path)


def load_supply(path, *, expected_sha256):
    """Read an externally pinned product, never an unverified snapshot."""
    from terrain_pipeline.common_infra import load_bundle
    bundle = load_bundle(path, expected_sha256=expected_sha256, validator=_validate_supply_bundle)
    m, arrays = dict(bundle['metadata']), bundle['arrays']
    hydraulic_meta = m.pop('hydraulic_metadata')
    sediment_meta = m.pop('sediment_metadata')
    m.pop('schema'); m.pop('units')
    m['hydraulic'] = {'metadata': hydraulic_meta, 'arrays': {k[11:]: v for k, v in arrays.items() if k.startswith('hydraulic__')}}
    m['sediment'] = {'metadata': sediment_meta, 'arrays': {k[10:]: v for k, v in arrays.items() if k.startswith('sediment__')}, 'identity_sha256': m['sediment_identity']}
    return m
