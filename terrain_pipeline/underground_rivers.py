"""Consolidated underground_rivers implementations; numeric expressions preserved."""
from __future__ import annotations

from dataclasses import asdict as _i41_asdict
from dataclasses import dataclass as _i41_dataclass
import json as _i41_json
import math as _i41_math
import os as _i41_os
from pathlib import Path as _i41_Path
import tempfile as _i41_tempfile
import numpy as _i41_np
from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i41_ArtifactIdentity
from terrain_pipeline.artifacts.contracts import array_hash as _i41_array_hash
from copy import deepcopy as _i42_deepcopy
from dataclasses import asdict as _i42_asdict
from dataclasses import dataclass as _i42_dataclass
from importlib.metadata import version as _i42_version
import math as _i42_math
import time as _i42_time
import numpy as _i42_np
import numpy as _i43_np
from terrain_pipeline.artifacts.contracts import array_hash as _i43_array_hash
from terrain_pipeline.artifacts.contracts import canonical_json as _i43_canonical_json
from terrain_pipeline.artifacts.contracts import digest as _i43_digest
from terrain_pipeline.artifacts.contracts import finite_number as _i43_finite_number
from terrain_pipeline.drainage import validate_flat_routing as _i43_validate_flat_routing
from terrain_pipeline.drainage import arrays_from_candidate as _i43__arrays
from terrain_pipeline.drainage import require_positive_integer as _i43__positive_integer
from terrain_pipeline.hybrid_geometry import closed_rock_section as _x56_closed_rock_section
from terrain_pipeline.hybrid_geometry import hybrid_cave_geometry_guard as _x57_hybrid_cave_geometry_guard
from terrain_pipeline.hybrid_geometry import manifold_from_record as _x58_manifold_from_record
from terrain_pipeline.hybrid_geometry import mesh_record as _x59_mesh_record
from terrain_pipeline.hybrid_geometry import ray_hits as _x60_ray_hits
from terrain_pipeline.hybrid_geometry import save_manifold as _x61_save_manifold
from terrain_pipeline.hybrid_geometry import seal as _x62_hybrid_cave_geometry_seal
from terrain_pipeline.hybrid_geometry import sweep_triangles as _x63_sweep_triangles
from terrain_pipeline.hybrid_geometry import void_witnesses as _x64_void_witnesses

CATEGORY = 'C'

# Source: terrain_pipeline.underground_channel
VERSION = 'underground-channel-v2'

# Source: terrain_pipeline.underground_channel
@_i41_dataclass(frozen=True)
class UndergroundRecipe:
    min_cover_m: float = 8.0
    # Retained for v1 caller/identity compatibility; v2 scores rank, never reject.
    min_entry_score: float = 0.5
    grayscale_weight: float = 0.45
    lithology_weight: float = 0.35
    cover_weight: float = 0.2

    def __post_init__(self):
        if any((isinstance(v, bool) or not _i41_math.isfinite(v) or v < 0 for v in (self.min_cover_m, self.min_entry_score, self.grayscale_weight, self.lithology_weight, self.cover_weight))):
            raise ValueError('recipe values must be finite and nonnegative')
        if self.grayscale_weight + self.lithology_weight + self.cover_weight <= 0:
            raise ValueError('at least one score weight is required')

# Source: terrain_pipeline.underground_channel
def plan_underground(surface_plan, grayscale_reference, lithology_reference, domain_mask, protected_mask, entries, exits, recipe=UndergroundRecipe(), cover_reference=None):
    """Rank explicit candidate entrances and connect only accepted entry/exit pairs."""
    if not isinstance(recipe, UndergroundRecipe) or surface_plan.get('status') != 'diagnostic_not_publishable':
        raise ValueError('validated surface plan and recipe required')
    identity = _i41_ArtifactIdentity(**surface_plan['identity'])
    if identity.sha256 != surface_plan.get('identity_sha256') or identity.algorithm != 'metric-channel-plan':
        raise ValueError('invalid surface plan identity')
    height = _i41_np.asarray(surface_plan['arrays']['source_height_m'])
    if height.dtype != _i41_np.float64 or height.ndim != 2 or (not _i41_np.isfinite(height).all()):
        raise ValueError('surface height must be a finite float64 grid')
    source_hash = identity.record()['parameters'].get('source_height_sha256')
    if source_hash and _i41_array_hash(height) != source_hash:
        raise ValueError('surface height differs from identity')
    shape = height.shape
    gray = _i41_np.asarray(grayscale_reference, dtype=_i41_np.float64)
    lithology = _i41_np.asarray(lithology_reference, dtype=_i41_np.float64)
    domain = _i41_np.asarray(domain_mask)
    protected = _i41_np.asarray(protected_mask)
    if gray.shape != shape or lithology.shape != shape or domain.shape != shape or (protected.shape != shape) or (not _i41_np.isfinite(gray).all()) or (not _i41_np.isfinite(lithology).all()) or (domain.dtype != bool) or (protected.dtype != bool):
        raise ValueError('references and masks must be finite arrays matching the surface plan')
    if cover_reference is None:
        raise ValueError('an explicit underground cover reference is required')
    cover = _i41_np.asarray(cover_reference, dtype=_i41_np.float64)
    if cover.shape != shape or not _i41_np.isfinite(cover).all() or _i41_np.any(cover < 0):
        raise ValueError('cover reference must be a finite nonnegative grid')
    entry_array = _i41_np.asarray(entries, dtype=_i41_np.int64)
    if entry_array.ndim != 2 or entry_array.shape[1] != 2:
        raise ValueError('entries must be z,x pairs')
    exit_records = []
    for item in exits:
        if isinstance(item, dict):
            point, kind = (item.get('grid_zx'), item.get('type'))
        else:
            if len(item) != 3:
                raise ValueError('exits require grid_zx and explicit type')
            point, kind = (item[:2], item[2])
        if kind not in {'surface_low', 'spring', 'coast', 'subsea'}:
            raise ValueError('unknown exit type')
        if point is None or len(point) != 2:
            raise ValueError('exit coordinates must be z,x')
        exit_records.append((int(point[0]), int(point[1]), kind))
    scores = _i41_np.zeros(shape, dtype=_i41_np.float64)
    gray_range = _i41_np.ptp(gray)
    gray_norm = (_i41_np.clip(gray, 0.0, 1.0) if gray_range == 0
                 else (gray - gray.min()) / max(gray_range, 1e-12))
    lith_norm = (lithology - lithology.min()) / max(_i41_np.ptp(lithology), 1e-12)
    total_weight = recipe.grayscale_weight + recipe.lithology_weight + recipe.cover_weight
    scores = (recipe.grayscale_weight * (1 - gray_norm) + recipe.lithology_weight * lith_norm + recipe.cover_weight * _i41_np.clip(cover / max(recipe.min_cover_m, 1.0), 0.0, 1.0)) / total_weight
    accepted = []
    rejected = []
    for z, x in entry_array:
        reasons = []
        valid = 0 <= z < shape[0] and 0 <= x < shape[1]
        if not valid:
            reasons.append('outside_grid')
        else:
            if protected[z, x]:
                reasons.append('protected')
            if not domain[z, x]:
                reasons.append('outside_hydrologic_domain')
            if cover[z, x] < recipe.min_cover_m:
                reasons.append('insufficient_cover')
        item = {'grid_zx': [int(z), int(x)], 'score': float(scores[z, x]) if valid else None, 'accepted': not reasons, 'reasons': reasons}
        (accepted if not reasons else rejected).append(item)
    # Python's stable sort preserves caller order when scores tie.
    accepted.sort(key=lambda item: item['score'], reverse=True)
    accepted_exits = []
    for z, x, exit_type in exit_records:
        valid = 0 <= z < shape[0] and 0 <= x < shape[1]
        reasons = [] if valid and domain[z, x] and (not protected[z, x]) else ['invalid_or_protected_exit']
        item = {'grid_zx': [int(z), int(x)], 'accepted': not reasons, 'reasons': reasons, 'type': exit_type}
        if exit_type == 'subsea':
            item['diagnostic_only'] = True
        (accepted_exits if not reasons else rejected).append(item)
    edges = []
    blocked = protected | ~domain | (cover < recipe.min_cover_m)
    if accepted and accepted_exits:
        for source in accepted:
            target = min(accepted_exits, key=lambda item: abs(item['grid_zx'][0] - source['grid_zx'][0]) + abs(item['grid_zx'][1] - source['grid_zx'][1]))
            start, goal = (tuple(source['grid_zx']), tuple(target['grid_zx']))
            queue, previous = ([start], {start: None})
            for cell in queue:
                if cell == goal:
                    break
                for dz, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nxt = (cell[0] + dz, cell[1] + dx)
                    if 0 <= nxt[0] < shape[0] and 0 <= nxt[1] < shape[1] and (nxt == goal or not blocked[nxt]) and (nxt not in previous):
                        previous[nxt] = cell
                        queue.append(nxt)
            if goal not in previous:
                continue
            path = []
            cell = goal
            while cell is not None:
                path.append(list(cell))
                cell = previous[cell]
            path.reverse()
            edges.append({'entry_grid_zx': source['grid_zx'], 'exit_grid_zx': target['grid_zx'], 'path_grid_zx': path, 'status': 'candidate_only'})
    identity = _i41_ArtifactIdentity('Terragenesis', 'underground-channel', VERSION, 0, {**_i41_asdict(recipe), 'surface_plan_sha256': surface_plan['identity_sha256'], 'height_sha256': _i41_array_hash(height), 'grayscale_sha256': _i41_array_hash(gray), 'lithology_sha256': _i41_array_hash(lithology), 'domain_sha256': _i41_array_hash(domain), 'protected_sha256': _i41_array_hash(protected), 'cover_sha256': _i41_array_hash(cover)})
    outputs = {'score_m': scores, 'accepted_entry_mask': _i41_np.zeros(shape, bool), 'domain_mask': domain.copy(), 'protected_mask': protected.copy()}
    for item in accepted:
        outputs['accepted_entry_mask'][tuple(item['grid_zx'])] = True
    for value in outputs.values():
        value.flags.writeable = False
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': 'diagnostic_not_publishable', 'arrays': outputs, 'entries': accepted + rejected, 'exits': accepted_exits, 'edges': edges, 'preview_modes': ['surface_only', 'underground_only', 'overlay'], 'summary': {'accepted_entries': len(accepted), 'rejected_candidates': len(rejected), 'accepted_exits': len(accepted_exits), 'candidate_edges': len(edges), 'grayscale_is_ranking_only': True, 'cover_is_explicit_reference': True}}

# Source: terrain_pipeline.underground_channel
def save_underground(result, path):
    destination = _i41_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ('identity', 'identity_sha256', 'status', 'entries', 'exits', 'edges', 'preview_modes', 'summary')}
    record['format_version'] = 1
    record['array_sha256'] = {name: _i41_array_hash(_i41_np.ascontiguousarray(value)) for name, value in result['arrays'].items()}
    temporary = None
    try:
        with _i41_tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent, delete=False, suffix='.npz') as stream:
            temporary = _i41_Path(stream.name)
            _i41_np.savez_compressed(stream, manifest=_i41_json.dumps(record, sort_keys=True), **result['arrays'])
        load_underground(temporary)
        _i41_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

# Source: terrain_pipeline.underground_channel
def load_underground(path):
    expected = {'score_m', 'accepted_entry_mask', 'domain_mask', 'protected_mask'}
    with _i41_np.load(path, allow_pickle=False) as archive:
        record = _i41_json.loads(str(archive['manifest'].item()))
        if set(archive.files) != expected | {'manifest'} or set(record.get('array_sha256', {})) != expected:
            raise ValueError('invalid underground array set')
        arrays = {name: archive[name].copy() for name in expected}
    identity = _i41_ArtifactIdentity(**record['identity'])
    # Load the saved version verbatim; never re-score or re-pin legacy v1 artifacts.
    if record.get('format_version') != 1 or record.get('status') != 'diagnostic_not_publishable' or identity.algorithm != 'underground-channel' or (identity.algorithm_version not in {'underground-channel-v1', VERSION}) or (identity.sha256 != record['identity_sha256']) or any((_i41_array_hash(_i41_np.ascontiguousarray(arrays[name])) != expected for name, expected in record['array_sha256'].items())):
        raise ValueError('underground identity or arrays differ')
    shape = arrays['score_m'].shape
    if len(shape) != 2 or min(shape) < 1 or arrays['score_m'].dtype != _i41_np.float64 or (not _i41_np.isfinite(arrays['score_m']).all()) or any((arrays[name].shape != shape or arrays[name].dtype != bool for name in ('accepted_entry_mask', 'domain_mask', 'protected_mask'))):
        raise ValueError('invalid underground shapes or values')
    if record.get('preview_modes') != ['surface_only', 'underground_only', 'overlay']:
        raise ValueError('invalid preview modes')
    for value in arrays.values():
        value.flags.writeable = False
    return {**{key: record[key] for key in ('identity', 'identity_sha256', 'status', 'entries', 'exits', 'edges', 'preview_modes', 'summary')}, 'arrays': arrays}

# Source: terrain_pipeline.underground_river_v1
SCHEMA = 'td-underground-river-preview-v1'

# Source: terrain_pipeline.underground_river_v1
CAPABILITIES = {'hydraulic_solved': False, 'full_network_verified': False, 'natural_outlet_certified': False}

# Source: terrain_pipeline.underground_river_v1
@_i42_dataclass(frozen=True)
class Parameters:
    seed: int = 17
    lateral_amplitude_m: float = 1.0
    width_scale: float = 1.05
    roof_variation_m: float = 0.2

    def __post_init__(self):
        if type(self.seed) is not int or not 0 <= self.seed <= 2 ** 32 - 1:
            raise ValueError('seed must be an integer in [0, 4294967295]')
        for name, lower, upper in (('lateral_amplitude_m', 0.0, 3.0), ('width_scale', 0.8, 1.2), ('roof_variation_m', 0.0, 0.5)):
            value = getattr(self, name)
            if type(value) not in (int, float):
                raise ValueError(name + ' must be an int or float')
            if not lower <= value <= upper or not _i42_math.isfinite(value):
                raise ValueError(name + ' outside bounded finite range')

# Source: terrain_pipeline.underground_river_v1
def deform_charts(source_vdm, parameters):
    stations = _i42_deepcopy(source_vdm['stations'])
    phases = _i42_np.random.default_rng(parameters.seed).uniform(-_i42_math.pi, _i42_math.pi, 3)
    for ordinal, station in enumerate(stations):
        if ordinal in (0, len(stations) - 1):
            continue
        fraction = station['fraction']
        envelope = _i42_math.sin(_i42_math.pi * fraction) ** 2
        transverse = _i42_np.asarray(station['transverse_unit_xz'], float)
        origin = _i42_np.asarray(station['origin_xyz_m'], float)
        baseline = _i42_np.asarray(station['derived_ring_xyz_m'], float)
        lateral = parameters.lateral_amplitude_m * envelope * _i42_math.sin(2 * _i42_math.pi * fraction + phases[0])
        shift = _i42_np.array([transverse[0] * lateral, 0.0, transverse[1] * lateral])
        derived = baseline + shift
        offsets = (baseline[:, [0, 2]] - origin[[0, 2]]) @ transverse
        scale = 1.0 + (parameters.width_scale - 1.0) * envelope
        derived[:, [0, 2]] += _i42_np.outer(offsets * (scale - 1.0), transverse)
        variation = parameters.roof_variation_m * envelope
        derived[-2:, 1] += variation * _i42_math.sin(4 * _i42_math.pi * fraction + phases[1])
        derived[-2, [0, 2]] += variation * _i42_math.sin(2 * _i42_math.pi * fraction + phases[2]) * transverse
        derived[-1, [0, 2]] -= variation * _i42_math.sin(2 * _i42_math.pi * fraction + phases[2]) * transverse
        station['origin_xyz_m'] = (origin + shift).tolist()
        reference = _i42_np.asarray(station['reference_ring_xyz_m'], float)
        displacement = derived - reference
        station['displacement_ring_xyz_m'] = displacement.tolist()
        station['derived_ring_xyz_m'] = (reference + displacement).tolist()
    for ordinal in (0, -1):
        if stations[ordinal] != source_vdm['stations'][ordinal]:
            raise ValueError('immutable portal station changed')
    rings = [_i42_np.asarray(station['derived_ring_xyz_m']) for station in stations]
    if not all((_i42_np.isfinite(ring).all() for ring in rings)):
        raise ValueError('nonfinite chart')
    bounds = [(_i42_np.vstack((first, second))[:, [0, 2]].min(axis=0), _i42_np.vstack((first, second))[:, [0, 2]].max(axis=0)) for first, second in zip(rings, rings[1:])]
    for ordinal, (low, high) in enumerate(bounds):
        for other_low, other_high in bounds[ordinal + 2:]:
            if _i42_np.all(_i42_np.minimum(high, other_high) - _i42_np.maximum(low, other_low) > 1e-08):
                raise ValueError('nonadjacent sweep projection overlap not certified')
    return {'stations': stations, 'triangles': _x63_sweep_triangles(stations)}

# Source: terrain_pipeline.underground_river_v1
def build_preview(rock_record, source_vdm, sampler, source_pins, parameters=Parameters(), *, started=None):
    started = _i42_time.perf_counter() if started is None else started

    def budget_guard():
        _x57_hybrid_cave_geometry_guard()
        if _i42_time.perf_counter() - started > 60.0:
            raise ValueError('60s generation budget exceeded')

    def bounded_sampler(point):
        budget_guard()
        return sampler(point)
    if _i42_version('manifold3d') != '3.5.4':
        raise ValueError('only manifold3d==3.5.4 authorized')
    import manifold3d
    budget_guard()
    origin = _i42_np.asarray(rock_record['local_origin_xyz_m'], float)
    if not _i42_np.array_equal(origin, source_vdm['stations'][0]['origin_xyz_m']):
        raise ValueError('source sink and fixed rock origin differ')
    for station in source_vdm['stations']:
        if not _i42_np.array_equal(_i42_np.asarray(station['reference_ring_xyz_m']) + _i42_np.asarray(station['displacement_ring_xyz_m']), station['derived_ring_xyz_m']):
            raise ValueError('source VDM reference displacement mismatch')
    before = _x58_manifold_from_record(rock_record)
    vdm = deform_charts(source_vdm, parameters)
    stations = vdm['stations']
    rings = _i42_np.asarray([station['derived_ring_xyz_m'] for station in stations])
    local = rings.reshape(-1, 3) - origin
    rock_vertices = _i42_np.asarray(rock_record['vertices_local_xyz_m'])
    if _i42_np.any(local[:, [0, 2]] <= rock_vertices[:, [0, 2]].min(axis=0)) or _i42_np.any(local[:, [0, 2]] >= rock_vertices[:, [0, 2]].max(axis=0)):
        raise ValueError('cutter leaves fixed rock crop')
    if local[:, 1].min() <= rock_vertices[:, 1].min():
        raise ValueError('cutter leaves fixed rock bottom')
    above_y = float(rock_vertices[:, 1].max() + origin[1] + 10.0)
    closed_indices = []
    cover_witnesses = []
    for ordinal, (station, ring) in enumerate(zip(stations, rings)):
        containment = []
        for point in ring:
            source_witness = bounded_sampler(point[[0, 2]])
            hits = _x60_ray_hits(before, [point[0], above_y, point[2]], point, origin)
            cover = min((hit['position_xyz_m'][1] - point[1] for hit in hits), default=None)
            containment.append({'point_xyz_m': point.tolist(), 'vertical_ray_start_xyz_m': [float(point[0]), above_y, float(point[2])], 'rock_before_vertical_hits': hits, 'actual_sampled_top_cover_m': cover, 'source_bed_witness': source_witness})
        closed = _x56_closed_rock_section(containment)
        cover_witnesses.append({'station_id': station['station_id'], 'fraction': station['fraction'], 'actual_ring_containment': containment, 'physical_closed_rock_section': closed})
        if 0.25 <= station['fraction'] <= 0.75 and (not closed):
            raise ValueError('insufficient actual core rock cover:' + station['station_id'])
        if closed:
            closed_indices.append(ordinal)
    if not closed_indices or closed_indices != list(range(closed_indices[0], closed_indices[-1] + 1)):
        raise ValueError('covered core missing or not contiguous')
    cutter_record = _x59_mesh_record(local, vdm['triangles'], origin, 'cutter')
    cutter = _x58_manifold_from_record(cutter_record)
    after, removed = (before - cutter, before ^ cutter)
    budget_guard()
    if any((solid.status() != manifold3d.Error.NoError or solid.is_empty() for solid in (after, removed))):
        raise ValueError('actual rock Boolean failed or empty')
    if len(cutter.decompose()) != 1 or len(removed.decompose()) != 1:
        raise ValueError('cutter or removed not connected')
    residual = before.volume() - after.volume() - removed.volume()
    if abs(residual) > max(1e-07, before.volume() * 1e-10):
        raise ValueError('material balance failed')
    path, segments, openings = _x64_void_witnesses(before, after, removed, vdm, origin, bounded_sampler)
    for segment in segments:
        budget_guard()
        segment['rock_before_hits'] = _x60_ray_hits(before, segment['from_xyz_m'], segment['to_xyz_m'], origin)
        segment['removed_hits'] = _x60_ray_hits(removed, segment['from_xyz_m'], segment['to_xyz_m'], origin)
    records = {'rock_before': rock_record, 'cutter': cutter_record, 'rock_after': _x61_save_manifold(after, origin, 'rock_after'), 'removed': _x61_save_manifold(removed, origin, 'removed')}
    reference = _i42_np.asarray([station['reference_ring_xyz_m'] for station in stations]).reshape(-1, 3) - origin
    displacement = _i42_np.asarray([station['displacement_ring_xyz_m'] for station in stations]).reshape(-1, 3)
    derived = reference + displacement
    if not _i42_np.allclose(derived, local, atol=1e-10, rtol=0.0):
        raise ValueError('VDM reference displacement mismatch')
    budget_guard()
    return _x62_hybrid_cave_geometry_seal({'schema': SCHEMA, 'status': 'geometry_checked', 'origin_xyz_m': origin.tolist(), 'parameters': _i42_asdict(parameters), 'source_pins': source_pins, 'capabilities': dict(CAPABILITIES), 'scope': 'seeded engineered gallery in fixed sampled mountain rock; generator checks only, no independent audit or complete portal certification', 'meshes': {key: {name: record[name] for name in ('vertices_local_xyz_m', 'triangles')} for key, record in records.items()}, 'vdm': {'reference_local_xyz_m': reference.tolist(), 'derived_local_xyz_m': derived.tolist(), 'displacement_xyz_m': displacement.tolist(), 'triangles': cutter_record['triangles']}, 'stations': [{'station_id': station['station_id'], 'origin_local_xyz_m': (_i42_np.asarray(station['origin_xyz_m']) - origin).tolist(), 'ring_local_xyz_m': (ring - origin).tolist()} for station, ring in zip(stations, rings)], 'portals': [{'kind': kind, 'position_local_xyz_m': (_i42_np.asarray(stations[ordinal]['origin_xyz_m']) - origin).tolist()} for kind, ordinal in (('sink', 0), ('spring', -1))], 'metrics': {'length_m': _i42_math.fsum((_i42_math.dist(first['origin_xyz_m'], second['origin_xyz_m']) for first, second in zip(stations, stations[1:]))), 'excavated_rock_m3': removed.volume(), 'material_residual_m3': residual, 'closed_core_count': len(closed_indices)}, 'geometry_checks': {'air_path_local_xyz_m': (_i42_np.asarray(path) - origin).tolist(), 'evidence_coordinates': 'world XYZ metres for *_xyz_m; local only for *_local_xyz_m', 'producer_check_scope': 'new generator geometry checks, not independent audit or complete portal certification', 'independent_audit_passed': False, 'complete_portal_certified': False, 'station_source_cover_witnesses': cover_witnesses, 'air_path_xyz_m': path, 'air_path_segments': segments, 'portal_opening_witnesses': openings, 'air_segment_count': len(segments), 'terrain_opening_kinds': sorted(openings), 'closed_core_station_indices': closed_indices, 'removed_components': 1}, 'water': None})

# Source: terrain_pipeline.real_dem_river_3d_adapter
ALGORITHM = 'real-dem-shared-bank-illustrative-bed-ribbon-v1'

# Source: terrain_pipeline.real_dem_river_3d_adapter
MAX_BYTES = 512 * 1024 * 1024

# Source: terrain_pipeline.real_dem_river_3d_adapter
ARRAY_NAMES = {'node_ids', 'node_xyz', 'edge_ids', 'edges', 'donor_count', 'heads', 'junctions', 'terminals', 'component_id', 'touches_boundary', 'touches_unknown', 'cross_sections', 'vertices', 'faces', 'degenerate_face_ids'}

# Source: terrain_pipeline.real_dem_river_3d_adapter
def _context(candidate, flat_result, threshold, width, depth, tile_size):
    _i43__positive_integer(tile_size, 'tile_size', 1024)
    threshold = _i43_finite_number(threshold, 'min_contributing_cells', positive=True)
    width = _i43_finite_number(width, 'width_m', positive=True)
    depth = _i43_finite_number(depth, 'depth_m', positive=True)
    if width > 1000000.0 or depth > 1000000.0 or threshold > 500000:
        raise ValueError('geometry parameters exceed resource/range budget')
    height, valid = _i43__arrays(candidate)
    _i43_validate_flat_routing(candidate, flat_result)
    identity = candidate.get('manifest', {}).get('identity', {})
    grid = identity.get('grid', candidate.get('grid'))
    if not isinstance(grid, dict):
        raise ValueError('explicit projected metric grid required')
    if not identity and (grid.get('crs') != 'EPSG:32651' or grid.get('units') != 'metres'):
        raise ValueError('fixture grid must declare EPSG:32651 metres')
    for name in ('origin_x_m', 'origin_z_m', 'spacing_x_m', 'spacing_z_m'):
        _i43_finite_number(grid.get(name), name, positive=name.startswith('spacing'))
    source = {'candidate_content_sha256': candidate.get('manifest', {}).get('content_sha256'), 'height_sha256': _i43_array_hash(height), 'valid_mask_sha256': _i43_array_hash(valid), 'flat_graph_sha256': _i43_digest({name: _i43_array_hash(getattr(flat_result['network'], name)) for name in ('receiver', 'order', 'accumulation_cells', 'boundary_outlet', 'unknown_adjacent_terminal')}), 'flat_components_sha256': _i43_digest(flat_result['components']), 'grid': dict(grid)}
    return (height, valid, grid, threshold, width, depth, source)

# Source: terrain_pipeline.real_dem_river_3d_adapter
def _topology(height, valid, grid, flat, threshold):
    network = flat['network']
    ids = _i43_np.flatnonzero(valid.ravel() & (network.accumulation_cells.ravel() >= threshold))
    receiver = network.receiver.ravel()[ids]
    routed = receiver >= 0
    targets = receiver[routed]
    if not _i43_np.isin(targets, ids).all():
        raise ValueError('selected graph lacks downstream closure')
    edges = _i43_np.column_stack((ids[routed], targets)).astype(_i43_np.int64)
    row, col = _i43_np.divmod(ids, height.shape[1])
    xyz = _i43_np.column_stack((grid['origin_x_m'] + col * grid['spacing_x_m'], height.ravel()[ids], grid['origin_z_m'] + row * grid['spacing_z_m']))
    if not _i43_np.isfinite(xyz).all():
        raise ValueError('nonfinite projected node coordinates')
    donors = _i43_np.bincount(_i43_np.searchsorted(ids, targets), minlength=len(ids)).astype(_i43_np.int64)
    component = flat['component_id'].ravel()[ids]
    records = {item['component_id']: item for item in flat['components']}
    return {'node_ids': ids, 'node_xyz': xyz, 'edge_ids': ids[routed].copy(), 'edges': edges, 'donor_count': donors, 'heads': donors == 0, 'junctions': donors > 1, 'terminals': ~routed, 'component_id': component.copy(), 'touches_boundary': _i43_np.array([records[int(value)]['touches_boundary'] for value in component], bool), 'touches_unknown': _i43_np.array([records[int(value)]['touches_unknown'] for value in component], bool)}

# Source: terrain_pipeline.real_dem_river_3d_adapter
def _banks(topology, width, depth):
    ids, xyz, edges = (topology['node_ids'], topology['node_xyz'], topology['edges'])
    source = _i43_np.searchsorted(ids, edges[:, 0])
    target = _i43_np.searchsorted(ids, edges[:, 1])
    delta = xyz[target][:, [0, 2]] - xyz[source][:, [0, 2]]
    lengths = _i43_np.linalg.norm(delta, axis=1)
    if _i43_np.any(lengths <= 0) or not _i43_np.isfinite(lengths).all():
        raise ValueError('zero/nonfinite horizontal edge length')
    direction = delta / lengths[:, None]
    tangent = _i43_np.zeros((len(ids), 2))
    _i43_np.add.at(tangent, target, direction)
    tangent[source] = direction
    magnitude = _i43_np.linalg.norm(tangent, axis=1)
    fallback = magnitude <= 1e-12
    tangent[fallback] = [1.0, 0.0]
    tangent[~fallback] /= magnitude[~fallback, None]
    normal = _i43_np.column_stack((-tangent[:, 1], tangent[:, 0]))
    vertices = _i43_np.repeat(xyz, 2, axis=0)
    vertices[:, 1] -= depth
    vertices[0::2, 0] += normal[:, 0] * width / 2
    vertices[0::2, 2] += normal[:, 1] * width / 2
    vertices[1::2, 0] -= normal[:, 0] * width / 2
    vertices[1::2, 2] -= normal[:, 1] * width / 2
    if not _i43_np.isfinite(vertices).all():
        raise ValueError('nonfinite bank vertices')
    faces = _i43_np.empty((2 * len(edges), 3), _i43_np.int64)
    faces[0::2] = _i43_np.column_stack((2 * source, 2 * source + 1, 2 * target))
    faces[1::2] = _i43_np.column_stack((2 * source + 1, 2 * target + 1, 2 * target))
    triangles = vertices[faces]
    double_area = _i43_np.linalg.norm(_i43_np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
    bad = _i43_np.flatnonzero(double_area <= 1e-10)
    profile = _i43_np.tile(_i43_np.array([width, depth, width * depth]), (len(ids), 1))
    return (profile, vertices, faces, bad, int(fallback.sum()))

# Source: terrain_pipeline.real_dem_river_3d_adapter
def _metadata(source, threshold, width, depth, topology, bad, fallback):
    return {'algorithm': ALGORITHM, 'source': source, 'parameters': {'min_contributing_cells': threshold, 'width_m': width, 'depth_m': depth}, 'coordinates': 'X=easting_m; Y=raw_DEM_height_m; Z=-northing_m; pixel_centers', 'cross_section_columns': ['illustrative_width_m', 'illustrative_depth_m', 'illustrative_area_m2'], 'bed_elevation': 'raw_DEM_height_minus_explicit_illustrative_depth_not_observed_channel', 'node_id': 'global_cell_id', 'edge_id': 'donor_global_cell_id', 'banks': 'two_shared_vertices_per_node', 'tangent': 'downstream_unit_direction_else_mean_upstream_unit_direction_else_positive_X', 'status': 'topology_sections_only_mesh_degenerate' if len(bad) else 'illustrative_shared_bank_ribbon_prototype', 'mesh_accepted': not bool(len(bad)), 'degenerate_face_count': len(bad), 'tangent_fallback_node_count': fallback, 'junction_count': int(topology['junctions'].sum()), 'junction_mesh': 'shared_banks_but_sharp_overlapping_nonmanifold_junctions_not_hydraulic_ready', 'intersection_check': 'not_performed_crossings_possible', 'limitations': '90m_DEM_does_not_resolve_real_fine_channels; no_water_surface_ocean_or_Minecraft', 'engineering_parameters': True, 'source_height_unchanged': True, 'hydraulic_ready': False, 'continuous_water_body_verified': False, 'natural_outlet_verified': False, 'ocean_outlet_certified': False, 'publishable': False}

# Source: terrain_pipeline.real_dem_river_3d_adapter
def _seal(result):
    result['array_hashes'] = {name: _i43_array_hash(result[name]) for name in sorted(ARRAY_NAMES)}
    result['metadata_sha256'] = _i43_digest(result['metadata'])
    result['content_sha256'] = _i43_digest({'array_hashes': result['array_hashes'], 'metadata_sha256': result['metadata_sha256']})

# Source: terrain_pipeline.real_dem_river_3d_adapter
def build_river_geometry(candidate, flat_result, *, min_contributing_cells=100, width_m=20.0, depth_m=1.0, tile_size=256) -> dict:
    height, valid, grid, threshold, width, depth, source = _context(candidate, flat_result, min_contributing_cells, width_m, depth_m, tile_size)
    result = _topology(height, valid, grid, flat_result, threshold)
    if len(result['node_ids']) * 300 > MAX_BYTES:
        raise ValueError('geometry retained array resource budget exceeded')
    profile, vertices, faces, bad, fallback = _banks(result, width, depth)
    result.update(cross_sections=profile, vertices=vertices, faces=faces, degenerate_face_ids=bad)
    result['metadata'] = _metadata(source, threshold, width, depth, result, bad, fallback)
    if _i43_array_hash(height) != source['height_sha256']:
        raise ValueError('source height changed')
    _seal(result)
    return result

# Source: terrain_pipeline.real_dem_river_3d_adapter
def validate_river_geometry(candidate, flat_result, result) -> dict:
    """Audit source topology, coordinates, shared cross-sections and mesh faces."""
    if not isinstance(result, dict) or set(result) != ARRAY_NAMES | {'metadata', 'array_hashes', 'metadata_sha256', 'content_sha256'}:
        raise ValueError('invalid geometry schema')
    try:
        parameters = result['metadata']['parameters']
        height, valid, grid, threshold, width, depth, source = _context(candidate, flat_result, parameters['min_contributing_cells'], parameters['width_m'], parameters['depth_m'], 256)
    except (KeyError, TypeError) as error:
        raise ValueError('invalid geometry metadata') from error
    topology = _topology(height, valid, grid, flat_result, threshold)
    for name, expected in topology.items():
        actual = result[name]
        if not isinstance(actual, _i43_np.ndarray) or actual.dtype != expected.dtype or actual.shape != expected.shape or (not _i43_np.array_equal(actual, expected)):
            raise ValueError(f'geometry topology/coordinate/class/risk mismatch: {name}')
    ids, xyz, edges = (result['node_ids'], result['node_xyz'], result['edges'])
    if not _i43_np.isfinite(xyz).all():
        raise ValueError('nonfinite node coordinates')
    if len(edges) and _i43_np.any(xyz[_i43_np.searchsorted(ids, edges[:, 1]), 1] > xyz[_i43_np.searchsorted(ids, edges[:, 0]), 1]):
        raise ValueError('reference edge uphill')
    profile, vertices, faces, bad, fallback = _banks(topology, width, depth)
    for name, expected in (('cross_sections', profile), ('vertices', vertices), ('faces', faces), ('degenerate_face_ids', bad)):
        actual = result[name]
        if not isinstance(actual, _i43_np.ndarray) or actual.dtype != expected.dtype or actual.shape != expected.shape or (not _i43_np.isfinite(actual).all()) or (not _i43_np.array_equal(actual, expected)):
            raise ValueError(f'geometry section/shared mesh mismatch: {name}')
    if _i43_np.any(faces < 0) or _i43_np.any(faces >= len(vertices)) or sum((result[name].nbytes for name in ARRAY_NAMES)) > MAX_BYTES:
        raise ValueError('face indices/resource budget mismatch')
    expected_metadata = _metadata(source, threshold, width, depth, topology, bad, fallback)
    if _i43_canonical_json(result['metadata']) != _i43_canonical_json(expected_metadata):
        raise ValueError('geometry metadata source/claims mismatch')
    hashes = {name: _i43_array_hash(result[name]) for name in sorted(ARRAY_NAMES)}
    metadata_hash = _i43_digest(expected_metadata)
    if result['array_hashes'] != hashes or result['metadata_sha256'] != metadata_hash or result['content_sha256'] != _i43_digest({'array_hashes': hashes, 'metadata_sha256': metadata_hash}):
        raise ValueError('geometry hash mismatch')
    return {'verified': True, 'mesh_accepted': not bool(len(bad)), 'node_count': len(ids), 'edge_count': len(edges), 'degenerate_face_count': len(bad), 'hydraulic_ready': False, 'publishable': False, 'natural_outlet_verified': False, 'ocean_outlet_certified': False}
