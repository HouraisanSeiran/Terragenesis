"""Read-only SHA-pinned saved assembly input, not a raw TD page claim."""
import numpy as np
from terrain_pipeline.common_infra import checked_archive, identity
from terrain_pipeline.runoff import _strict_json as _strict_json


def load_saved_assembly(record, parameters):
    def headers(items):
        for shape, dtype in items.values():
            if dtype.hasobject or dtype.fields is not None or np.prod(shape, dtype=object) > 16777216:
                raise ValueError('unsafe_assembly_array_header')
    arrays = checked_archive(record['path'], expected_sha256=record['sha256'],
                             max_bytes=512*1024**2, header_validator=headers)
    required = {'receiver', 'covered_mask', 'elevation_m', 'origin_native_cells', 'metadata_json'}
    if not required.issubset(arrays):
        raise ValueError('assembly_not_recomputable_or_missing_provenance')
    raw_meta = arrays['metadata_json']
    if raw_meta.dtype.kind != 'U' or raw_meta.shape not in ((), (1,)) or raw_meta.nbytes > 1048576:
        raise ValueError('assembly_metadata_json')
    meta = _strict_json(str(raw_meta.reshape(-1)[0]))
    if meta.get('schema') != 'native-30m-saved-assembly-v1':
        raise ValueError('assembly_metadata_schema')
    if type(meta.get('world_seed')) is not int or meta['world_seed'] != 20261020:
        raise ValueError('seed_mismatch')
    if type(meta.get('spacing_m')) not in (int, float) or meta['spacing_m'] != 30.0:
        raise ValueError('spacing_mismatch')
    field = arrays['elevation_m']
    mask = arrays['covered_mask']
    receiver = arrays['receiver']
    origin = arrays['origin_native_cells']
    shape = tuple(parameters['shape_zx'])
    if field.dtype.kind != 'f' or field.shape != shape or np.isinf(field).any():
        raise ValueError('assembly_elevation_shape_dtype')
    if mask.dtype != np.bool_ or mask.shape != shape or not mask.any() or not np.isfinite(field[mask]).all():
        raise ValueError('assembly_coverage_mask')
    if origin.dtype != np.int64 or origin.shape != (2,) or not np.array_equal(origin, parameters['origin_native_xz']):
        raise ValueError('assembly_origin_mismatch')
    if receiver.dtype != np.int64 or receiver.shape != shape:
        raise ValueError('assembly_receiver_shape_dtype')
    field = np.ascontiguousarray(field, np.float64)
    from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology
    topology = build_strict_topology(field, mask, origin_native_xz=tuple(int(v) for v in origin),
                                     world_seed=meta['world_seed'])
    if not np.array_equal(receiver, topology['receiver']):
        raise ValueError('assembly_receiver_not_strict_native_topology')
    metadata = {'schema': meta['schema'], 'world_seed': meta['world_seed'], 'spacing_m': 30.0,
                'source_file_sha256': record['sha256'], 'provenance': meta.get('provenance', 'caller-pinned saved assembly')}
    source_digest = identity({'field': field, 'resolved_mask': mask, 'receiver': receiver,
                              'origin_native_xz': origin}, metadata)
    return {'field': field, 'resolved_mask': mask.copy(), 'origin_native_xz': origin.copy(),
            'assembly_digest': source_digest,
            'source_records': [{'path': record['path'], 'sha256': record['sha256'],
                'page_key': 'saved-assembly', 'schema': 'native-30m-saved-assembly-v1',
                'native_origin_xz': origin.tolist(), 'shape_zx': list(shape),
                'world_seed': 20261020, 'spacing_m': 30.0}],
            'policy': {'source_kind': 'saved_assembly', 'receiver_verified_against_strict_topology': True,
                       'routed_q_reused': False, 'raw_td_page_authenticity_certified': False}}
