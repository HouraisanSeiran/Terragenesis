"""Conservative first adapter for new-world channel geometry and evidence.

This module does not infer a water surface from design incision.  Its raster
audit is evidence, not a full cross-section or hydraulic certification.
"""
from types import SimpleNamespace

import numpy as np

from terrain_pipeline.river_connectivity_audit import audit
from terrain_pipeline.world_irregular_channels import build_irregular_channel_geometry


def prepare_rivers(*, bed_m, receiver, q_m3_s, channel_mask, ocean_mask,
                   lake_mask, unknown_mask, protected_mask, origin_native_xz,
                   spacing_m, source_identity, bed_hardness, bank_hardness,
                   water_surface_m=None, water_source=None, config=None,
                   formative_section_inputs=None):
    """Build bounded shared-node sections and audit actual sampled raster beds.

    Q is a representative rate supplied by stage1, not a new water input.
    Water surfaces, if supplied, must be independently solved and identified.
    Bed changes require routing/classification revalidation by stage1.
    """
    if not isinstance(source_identity, str) or not source_identity.strip():
        raise ValueError("source identity required")
    bed = np.asarray(bed_m, dtype=float)
    if bed.ndim != 2 or not bed.size or not np.isfinite(bed).all():
        raise ValueError("finite nonempty bed required")
    masks = []
    for value in (channel_mask, ocean_mask, lake_mask, unknown_mask, protected_mask):
        a = np.asarray(value)
        if a.shape != bed.shape or a.dtype.kind != "b":
            raise ValueError("matching explicit boolean masks required")
        masks.append(a)
    channel, ocean, lake, unknown, protected = masks
    origin = np.asarray(origin_native_xz)
    if origin.shape != (2,) or origin.dtype.kind not in "iu":
        raise ValueError("integer native origin required")
    if not np.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("positive spacing required")
    rows, cols = np.indices(bed.shape)
    mesh = SimpleNamespace(node_x_m=((cols + origin[0]) * spacing_m).ravel(),
                           node_z_m=((rows + origin[1]) * spacing_m).ravel(),
                           world_seed=20261020)
    product = build_irregular_channel_geometry(
        bed, q_m3_s, channel, mesh, receiver, bed_hardness=bed_hardness,
        bank_hardness=bank_hardness, protected_mask=protected,
        complete_mask=~unknown, lake_mask=lake, ocean_mask=ocean,
        origin_native_xz=tuple(origin), spacing_m=spacing_m, config=config,
        formative_section_inputs=formative_section_inputs)
    final = product["arrays"]["final_bed_m"]
    evidence = audit(product["graph"], bed, final, lake=lake, ocean=ocean,
                     protected=protected, unknown=unknown,
                     water_surface=water_surface_m, water_source=water_source)
    product["evidence"] = evidence
    product["metadata"].update(source_identity=source_identity,
        routing_and_ocean_revalidation_required=bool(np.any(final != bed)),
        wet_connectivity_certified=False,
        resolution_warning="Widths below native spacing are not raster-resolved; sampled centres do not prove full sections.")
    return product


def solve_finite_hydraulics(*, bed_m, valid_mask, path_xz_m, width_m, max_depth_m,
                            origin_xz_m, spacing_m, source_identity_sha256,
                            section_source, roughness, roughness_source,
                            time_seconds, local_volume_m3, initial_volume_m3,
                            downstream, config=None):
    """Route a finite, sampled rectangular reach; coordinates and times are physical metres/seconds.

    Volumes are per interval and original path vertex. They are mapped without
    duplication to corresponding sampled stations. No construction is performed.
    The prescribed downstream head must remain below the terminal bed; this
    deliberately excludes backwater and submerged lake connections.
    """
    from terrain_pipeline.lake import _Gate as _Gate
    from terrain_pipeline.lake import _sample as _sample
    from terrain_pipeline.surface_hydraulics import solve_channel
    from terrain_pipeline.channel_geometry import ChannelForcing, ChannelNetwork, MAX_CHANNEL_NODES

    def unresolved(reason, arrays=None):
        return {"metadata": {"status": "unresolved", "reason": reason,
                "source_identity_sha256": source_identity_sha256,
                "wet_connectivity_certified": False}, "arrays": arrays or {}}

    bed = np.asarray(bed_m, dtype=float)
    valid = np.asarray(valid_mask)
    path = np.asarray(path_xz_m, dtype=float)
    widths = np.asarray(width_m, dtype=float)
    depths = np.asarray(max_depth_m, dtype=float)
    times = np.asarray(time_seconds, dtype=float)
    volumes = np.asarray(local_volume_m3, dtype=float) if local_volume_m3 is not None else None
    initial = np.asarray(initial_volume_m3, dtype=float) if initial_volume_m3 is not None else None
    origin = np.asarray(origin_xz_m, dtype=float)
    if (bed.ndim != 2 or min(bed.shape) < 2 or valid.shape != bed.shape or valid.dtype.kind != 'b'
            or path.ndim != 2 or path.shape[1] != 2 or len(path) < 2
            or widths.shape != (len(path),) or depths.shape != widths.shape
            or not np.isfinite(path).all() or not np.isfinite(widths).all() or np.any(widths <= 0)
            or not np.isfinite(depths).all() or np.any(depths <= 0)
            or origin.shape != (2,) or not np.isfinite(origin).all()
            or not np.isfinite(spacing_m) or spacing_m <= 0):
        raise ValueError('invalid sampled source geometry')
    if volumes is None or initial is None:
        return unresolved('unknown water input or initial state')
    if (times.ndim != 1 or len(times) < 2 or not np.isfinite(times).all()
            or np.any(times < 0) or np.any(np.diff(times) <= 0)
            or volumes.shape != (len(times) - 1, len(path)) or initial.shape != (len(path),)
            or not np.isfinite(volumes).all() or np.any(volumes < 0)
            or not np.isfinite(initial).all() or np.any(initial < 0)):
        raise ValueError('invalid physical times or water volumes')
    if not isinstance(downstream, dict) or downstream.get('kind') not in ('open', 'lake'):
        return unresolved('unknown downstream boundary')
    head = downstream.get('stage_m')
    if head is None or not np.isscalar(head) or not np.isfinite(head):
        return unresolved('unknown downstream head')
    if downstream['kind'] == 'lake':
        reservoir = downstream.get('volume_m3')
        if reservoir is None or not np.isscalar(reservoir) or not np.isfinite(reservoir) or reservoir < 0:
            return unresolved('unknown measured lake volume')
    delta = np.diff(path, axis=0)
    distances = np.linalg.norm(delta, axis=1)
    if np.any(distances <= 0):
        raise ValueError('degenerate path')
    counts = np.maximum(1, np.ceil(distances / (spacing_m * .5)).astype(int))
    if int(counts.sum()) + 1 > MAX_CHANNEL_NODES:
        return unresolved('path exceeds finite solver node limit')
    points, ws, ds, original = [], [], [], []
    for i, count in enumerate(counts):
        original.append(len(points))
        for j in range(count):
            f = j / count
            points.append(path[i] * (1-f) + path[i+1] * f)
            ws.append(widths[i] * (1-f) + widths[i+1] * f)
            ds.append(depths[i] * (1-f) + depths[i+1] * f)
    original.append(len(points))
    points.append(path[-1]); ws.append(widths[-1]); ds.append(depths[-1])
    points = np.asarray(points); ws = np.asarray(ws); ds = np.asarray(ds)
    n = len(points)
    tangents = np.empty_like(points)
    tangents[0] = points[1] - points[0]; tangents[-1] = points[-1] - points[-2]
    tangents[1:-1] = points[2:] - points[:-2]
    tangent_length = np.linalg.norm(tangents, axis=1)
    if np.any(tangent_length <= 1e-12):
        return unresolved('path reverses at a section')
    normals = np.column_stack((-tangents[:, 1], tangents[:, 0])) / tangent_length[:, None]
    # Sampling spacing is at most half a native interval across every section.
    lateral_count = max(2, int(np.ceil(float(ws.max()) / (spacing_m * .5))) + 1)
    if n * lateral_count > 1000000:
        return unresolved('cross-section sampling resource limit')
    offsets = np.linspace(-.5, .5, lateral_count)
    samples = points[:, None, :] + normals[:, None, :] * ws[:, None, None] * offsets[None, :, None]
    grid = dict(origin_x_m=origin[0], origin_z_m=origin[1], spacing_x_m=spacing_m, spacing_z_m=spacing_m)
    domain = np.ones(bed.shape, dtype=bool); protected = np.zeros(bed.shape, dtype=bool)
    try:
        section_bed = np.array([[_sample(p, grid, bed, valid, domain, protected) for p in row] for row in samples])
        center = np.array([_sample(p, grid, bed, valid, domain, protected) for p in points])
    except _Gate as error:
        return unresolved('source sampling: ' + error.code)
    arrays = {'source_bed_m': bed.copy(), 'source_valid_mask': valid.copy(),
              'source_origin_xz_m': origin.copy(), 'source_spacing_m': np.asarray(spacing_m),
              'input_path_xz_m': path.copy(), 'input_width_m': widths.copy(),
              'input_max_depth_m': depths.copy(), 'station_xz_m': points, 'section_xz_m': samples, 'section_bed_m': section_bed,
              'bed_elevation_m': center, 'width_m': ws, 'max_depth_m': ds,
              'original_station_index': np.asarray(original, dtype=np.int64),
              'input_time_seconds': times, 'input_volume_m3': volumes, 'input_initial_volume_m3': initial}
    edges = np.linalg.norm(np.diff(points, axis=0), axis=1)
    if not np.allclose(section_bed, center[:, None], rtol=0., atol=1e-8):
        return unresolved('sampled cross section is incompatible with rectangular solver', arrays)
    if np.any(np.diff(center) >= 0):
        return unresolved('unsupported non-downhill bed or obstruction', arrays)
    if head >= center[-1]:
        return unresolved('incompatible downstream head; backwater unsupported', arrays)
    receiver = np.r_[np.arange(1, n, dtype=np.int64), np.int64(-1)]
    length = np.r_[edges, edges[-1]].astype(np.float64)
    slope = np.r_[-np.diff(center) / edges, -np.diff(center)[-1] / edges[-1]].astype(np.float64)
    distance = np.r_[edges, 0.].astype(np.float64)
    kinds = np.full(n, 'interior', dtype='U24'); kinds[-1] = 'open_outflow'
    rough = np.full(n, roughness, dtype=np.float64)
    network = ChannelNetwork(receiver, length, ws.astype(np.float64), center.astype(np.float64), slope,
                             rough, ds.astype(np.float64), kinds, source_identity_sha256,
                             section_source, roughness_source, distance)
    mapped = np.zeros((len(times)-1, n), dtype=np.float64)
    mapped[:, original] = volumes / np.diff(times)[:, None]
    initial_mapped = np.zeros(n, dtype=np.float64); initial_mapped[original] = initial
    forcing = ChannelForcing(times.astype(np.float64), mapped, source_identity_sha256)
    result = solve_channel(network, forcing, initial_mapped, config)
    arrays.update(result['arrays'])
    arrays['section_wet'] = result['arrays']['stage_m'][:, :, None] > section_bed[None, :, :]
    stage = result['arrays']['stage_m']
    if result['metadata']['status'] != 'complete':
        return unresolved('solver failed: ' + result['metadata']['failure_reason'], arrays)
    if np.any(np.diff(stage, axis=1) > 1e-9):
        return unresolved('unsupported water-surface backwater gradient', arrays)
    wet = bool(np.all(arrays['section_wet'][-1]))
    arrays['storage_length_m'] = length
    return {'arrays': arrays, 'metadata': {'status': 'complete', 'reason': None,
        'source_identity_sha256': source_identity_sha256, 'section_source': section_source,
        'roughness_source': roughness_source, 'downstream': dict(downstream),
        'algorithm': result['metadata']['algorithm'], 'roughness': float(roughness), 'solver_config': result['metadata']['config'],
        'wet_connectivity_certified': False, 'sampled_sections_wet_at_end': wet,
        'raster_resolution': 'subgrid_unresolved' if np.any(ws < 2 * spacing_m) else 'sampled',
        'proof_scope': 'sampled cross sections only; no continuous ribbon or raster connectivity proof',
        'water_ledger': {'initial_m3': float(initial.sum()), 'input_m3': float(volumes.sum()),
            'outflow_m3': float(arrays['boundary_outflow_volume_m3'].sum()),
            'final_storage_m3': float(arrays['volume_m3'][-1].sum()),
            'residual_m3': float(arrays['balance_residual_m3'].sum())},
        'construction_bulk_m3': 0.0, 'sediment_input_m3': 0.0}}


def save_finite_hydraulics(result, destination):
    """Save the actual physical trace and source-bound metadata without overwrite."""
    import json
    from pathlib import Path
    destination = Path(destination)
    if destination.suffix != '.npz':
        raise ValueError('hydraulic product must use .npz')
    with destination.open('xb') as handle:
        np.savez_compressed(handle, metadata_json=np.asarray(json.dumps(result['metadata'], allow_nan=False)),
                            **result['arrays'])
