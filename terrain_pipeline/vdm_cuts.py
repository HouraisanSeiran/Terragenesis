"""Consolidated vdm_cuts implementations; numeric expressions preserved."""
from __future__ import annotations

from dataclasses import asdict as _i36_asdict
from dataclasses import dataclass as _i36_dataclass
import math as _i36_math
import numpy as _i36_np
from terrain_pipeline.common_infra import SOURCE_MAX_CELLS as _i36_MAX_CELLS
from terrain_pipeline.common_infra import MAX_METADATA as _i36_MAX_METADATA
from terrain_pipeline.common_infra import identity as _i36_identity
from terrain_pipeline.common_infra import load_bundle as _i36_load_bundle
from terrain_pipeline.common_infra import readonly as _i36_readonly
from terrain_pipeline.common_infra import save_bundle as _i36_save_bundle
from dataclasses import asdict as _i37_asdict
from dataclasses import dataclass as _i37_dataclass
from dataclasses import replace as _i37_replace
import math as _i37_math
import numpy as _i37_np
from terrain_pipeline.common_infra import identity as _i37_identity
from terrain_pipeline.common_infra import load_bundle as _i37_load_bundle
from terrain_pipeline.common_infra import readonly as _i37_readonly
from terrain_pipeline.common_infra import save_bundle as _i37_save_bundle
from dataclasses import dataclass as _i38_dataclass
import math as _i38_math
import numpy as _i38_np
from dataclasses import asdict as _i39_asdict
import math as _i39_math
import numpy as _i39_np
from terrain_pipeline.common_infra import identity as _i39_identity
from terrain_pipeline.common_infra import load_bundle as _i39_load_bundle
from terrain_pipeline.common_infra import readonly as _i39_readonly
from terrain_pipeline.common_infra import save_bundle as _i39_save_bundle
import numpy as _i40_np
from terrain_pipeline.common_infra import identity as _i40_identity
from terrain_pipeline.common_infra import readonly as _i40_readonly
from terrain_pipeline.basin_topology import validate_basin_hierarchy as _i40_validate_basin_hierarchy
from terrain_pipeline.td_native_channel_surface import validate_channel_surface as _i40_validate_channel_surface

CATEGORY = 'C'

# Source: terrain_pipeline.metric_vdm
SCHEMA = 'metric-vdm-v1'

# Source: terrain_pipeline.metric_vdm
ALGORITHM = 'cliff-skeleton-v1'

# Source: terrain_pipeline.metric_vdm
ARRAY_KEYS = {'reference_xyz_m', 'displacement_xyz_m', 'vertices_xyz_m', 'triangles', 'protected_mask'}

# Source: terrain_pipeline.metric_vdm
def _finite_number(value, name, *, positive=False):
    if type(value) not in (int, float) or not _i36_math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f'invalid {name}')

# Source: terrain_pipeline.metric_vdm
@_i36_dataclass(frozen=True)
class CliffRecipe:
    center_xz_m: tuple
    outward_xz: tuple
    height_m: float
    half_length_m: float
    half_depth_m: float
    wall_half_width_m: float
    end_fade_m: float
    angle_degrees: float
    lean: int

    def __post_init__(self):
        for name in ('center_xz_m', 'outward_xz'):
            pair = getattr(self, name)
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError(f'invalid {name}')
            for value in pair:
                _finite_number(value, name)
        if _i36_math.hypot(*self.outward_xz) == 0:
            raise ValueError('outward direction must be nonzero')
        for name in ('height_m', 'half_length_m', 'half_depth_m', 'wall_half_width_m', 'end_fade_m'):
            _finite_number(getattr(self, name), name, positive=True)
        if self.wall_half_width_m >= self.half_depth_m:
            raise ValueError('wall must fit inside depth collar')
        _finite_number(self.angle_degrees, 'angle_degrees')
        if not 60 <= self.angle_degrees <= 90 or type(self.lean) is not int or self.lean not in (-1, 1):
            raise ValueError('invalid cliff angle or lean')

# Source: terrain_pipeline.metric_vdm
def _smooth(value):
    fraction = _i36_np.clip(value, 0, 1)
    return fraction * fraction * (3 - 2 * fraction)

# Source: terrain_pipeline.metric_vdm
def _triangles(rows, cols):
    cell_rows, cell_cols = _i36_np.indices((rows - 1, cols - 1))
    upper_left = (cell_rows * cols + cell_cols).ravel()
    upper_right = upper_left + 1
    lower_left = upper_left + cols
    lower_right = lower_left + 1
    triangles = _i36_np.empty((2 * upper_left.size, 3), dtype=_i36_np.int64)
    triangles[0::2] = _i36_np.stack((upper_left, lower_left, lower_right), axis=-1)
    triangles[1::2] = _i36_np.stack((upper_left, lower_right, upper_right), axis=-1)
    return triangles

# Source: terrain_pipeline.metric_vdm
def _check_mesh(vertices, triangles):
    points = vertices[triangles]
    first = points[:, 1] - points[:, 0]
    second = points[:, 2] - points[:, 0]
    cross = _i36_np.cross(first, second)
    scale = _i36_np.linalg.norm(first, axis=1) * _i36_np.linalg.norm(second, axis=1)
    if not _i36_np.isfinite(points).all() or not _i36_np.isfinite(cross).all() or _i36_np.any(scale == 0) or _i36_np.any(_i36_np.linalg.norm(cross, axis=1) <= 1e-12 * scale):
        raise ValueError('nonfinite or degenerate VDM triangle')

# Source: terrain_pipeline.metric_vdm
def build_vdm(reference_xyz_m, *, recipe: CliffRecipe, protected_mask, source_identity: str, protection_identity: str):
    if not isinstance(recipe, CliffRecipe):
        raise ValueError('CliffRecipe required')
    reference = _i36_np.asarray(reference_xyz_m)
    if reference.ndim != 3 or reference.shape[2] != 3 or min(reference.shape[:2]) < 3 or (reference.shape[0] * reference.shape[1] > _i36_MAX_CELLS) or (reference.dtype.kind not in 'fiu') or (not _i36_np.isfinite(reference).all()):
        raise ValueError('invalid metric reference chart')
    reference = _i36_np.array(reference, dtype=_i36_np.float64, copy=True)
    mask = _i36_np.asarray(protected_mask)
    if mask.shape != reference.shape[:2] or mask.dtype != bool:
        raise ValueError('protected_mask must be a boolean chart')
    for name, value in (('source_identity', source_identity), ('protection_identity', protection_identity)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{name} required')
    outward = _i36_np.array(recipe.outward_xz, dtype=_i36_np.float64)
    outward /= _i36_np.linalg.norm(outward)
    along = _i36_np.array((outward[1], -outward[0]))
    offset = reference[:, :, (0, 2)] - recipe.center_xz_m
    u = offset @ along
    v = offset @ outward
    end = _smooth((recipe.half_length_m - _i36_np.abs(u)) / recipe.end_fade_m)
    collar = _smooth((recipe.half_depth_m - _i36_np.abs(v)) / (recipe.half_depth_m - recipe.wall_half_width_m))
    active = (end > 0) & (collar > 0)
    if active[0].any() or active[-1].any() or active[:, 0].any() or active[:, -1].any():
        raise ValueError('active cliff reaches chart perimeter; provide an outer collar')
    if not active.any():
        raise ValueError('cliff does not intersect chart interior')
    fraction = _i36_np.clip((recipe.wall_half_width_m - v) / (2 * recipe.wall_half_width_m), 0, 1)
    top_offset = recipe.lean * recipe.height_m / _i36_math.tan(_i36_math.radians(recipe.angle_degrees))
    horizontal = ((fraction - 0.5) * top_offset - _i36_np.clip(v, -recipe.wall_half_width_m, recipe.wall_half_width_m)) * end * collar
    vertical = (fraction - 0.5) * recipe.height_m * end * collar
    displacement = _i36_np.zeros_like(reference)
    displacement[:, :, 0] = outward[0] * horizontal
    displacement[:, :, 1] = vertical
    displacement[:, :, 2] = outward[1] * horizontal
    displacement[mask] = 0
    vertices = (reference + displacement).reshape(-1, 3)
    if not _i36_np.isfinite(vertices).all():
        raise ValueError('nonfinite VDM position')
    triangles = _triangles(*mask.shape)
    _check_mesh(vertices, triangles)
    arrays = {'reference_xyz_m': _i36_readonly(reference), 'displacement_xyz_m': _i36_readonly(displacement), 'vertices_xyz_m': _i36_readonly(vertices), 'triangles': _i36_readonly(triangles), 'protected_mask': _i36_readonly(mask)}
    metadata = {'schema': SCHEMA, 'algorithm': ALGORITHM, 'coordinates': 'xyz metres; chart [row,col]', 'recipe': _i36_asdict(recipe), 'source_identity': source_identity, 'protection_identity': protection_identity, 'hydraulic_ready': False, 'natural_outlet_verified': False, 'publishable': False, 'self_intersection_verified': False}
    result = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i36_identity(arrays, metadata)}
    validate_vdm(result)
    return result

# Source: terrain_pipeline.metric_vdm
def validate_vdm(result):
    if not isinstance(result, dict) or set(result) != {'arrays', 'metadata', 'identity_sha256'}:
        raise ValueError('invalid VDM bundle')
    arrays, metadata = (result['arrays'], result['metadata'])
    if not isinstance(arrays, dict) or set(arrays) != ARRAY_KEYS or (not isinstance(metadata, dict)):
        raise ValueError('invalid VDM fields')
    if set(metadata) != {'schema', 'algorithm', 'coordinates', 'recipe', 'source_identity', 'protection_identity', 'hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified'} or metadata['schema'] != SCHEMA or metadata['algorithm'] != ALGORITHM or (metadata['coordinates'] != 'xyz metres; chart [row,col]') or any((metadata[key] is not False for key in ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified'))):
        raise ValueError('invalid VDM metadata')
    for key in ('source_identity', 'protection_identity'):
        if not isinstance(metadata[key], str) or not metadata[key].strip():
            raise ValueError('missing upstream identity')
    try:
        recipe_record = metadata['recipe']
        recipe = CliffRecipe(**{**recipe_record, 'center_xz_m': tuple(recipe_record['center_xz_m']), 'outward_xz': tuple(recipe_record['outward_xz'])})
    except (TypeError, KeyError, ValueError) as error:
        raise ValueError('invalid saved cliff recipe') from error
    if set(recipe_record) != set(_i36_asdict(recipe)):
        raise ValueError('unexpected cliff recipe field')
    reference = arrays['reference_xyz_m']
    displacement = arrays['displacement_xyz_m']
    vertices = arrays['vertices_xyz_m']
    triangles = arrays['triangles']
    mask = arrays['protected_mask']
    if not all((isinstance(value, _i36_np.ndarray) for value in arrays.values())) or reference.ndim != 3 or reference.shape[2] != 3 or (min(reference.shape[:2]) < 3) or (reference.shape[0] * reference.shape[1] > _i36_MAX_CELLS) or (reference.dtype != _i36_np.float64) or (displacement.shape != reference.shape) or (displacement.dtype != _i36_np.float64) or (vertices.shape != (reference.shape[0] * reference.shape[1], 3)) or (vertices.dtype != _i36_np.float64) or (mask.shape != reference.shape[:2]) or (mask.dtype != bool) or (triangles.shape != (2 * (mask.shape[0] - 1) * (mask.shape[1] - 1), 3)) or (triangles.dtype != _i36_np.int64):
        raise ValueError('invalid VDM array shape or dtype')
    if not _i36_np.isfinite(reference).all() or not _i36_np.isfinite(displacement).all() or (not _i36_np.isfinite(vertices).all()) or (not _i36_np.array_equal(vertices, (reference + displacement).reshape(-1, 3))) or (not _i36_np.array_equal(triangles, _triangles(*mask.shape))) or _i36_np.any(displacement[mask] != 0) or _i36_np.any(displacement[0] != 0) or _i36_np.any(displacement[-1] != 0) or _i36_np.any(displacement[:, 0] != 0) or _i36_np.any(displacement[:, -1] != 0):
        raise ValueError('invalid VDM geometry or collar')
    _check_mesh(vertices, triangles)
    if result['identity_sha256'] != _i36_identity(arrays, metadata):
        raise ValueError('VDM identity mismatch')
    return True

# Source: terrain_pipeline.metric_vdm
def _vdm_headers(headers):
    if set(headers) != ARRAY_KEYS | {'manifest'}:
        raise ValueError('unexpected VDM archive fields')
    shape, dtype = headers['reference_xyz_m']
    if len(shape) != 3 or shape[2] != 3 or min(shape[:2]) < 3 or (shape[0] * shape[1] > _i36_MAX_CELLS) or (dtype != _i36_np.float64):
        raise ValueError('invalid VDM reference header')
    rows, cols = shape[:2]
    expected = {'displacement_xyz_m': (shape, _i36_np.dtype('float64')), 'vertices_xyz_m': ((rows * cols, 3), _i36_np.dtype('float64')), 'triangles': ((2 * (rows - 1) * (cols - 1), 3), _i36_np.dtype('int64')), 'protected_mask': ((rows, cols), _i36_np.dtype(bool))}
    if any((headers[key] != value for key, value in expected.items())):
        raise ValueError('invalid VDM array header')
    manifest_shape, manifest_dtype = headers['manifest']
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= _i36_MAX_METADATA or manifest_dtype != _i36_np.uint8:
        raise ValueError('invalid VDM manifest header')

# Source: terrain_pipeline.metric_vdm
def save_vdm(path, result):
    _i36_save_bundle(path, result, validator=validate_vdm)

# Source: terrain_pipeline.metric_vdm
def load_vdm(path, *, expected_sha256, expected_identity):
    if not isinstance(expected_identity, str) or len(expected_identity) != 64:
        raise ValueError('expected VDM identity required')
    result = _i36_load_bundle(path, expected_sha256=expected_sha256, validator=validate_vdm, header_validator=_vdm_headers)
    if result['identity_sha256'] != expected_identity:
        raise ValueError('external VDM identity mismatch')
    return result

# Source: terrain_pipeline.metric_vdm_forms
METRIC_VDM_FORMS_SCHEMA = 'metric-vdm-forms-v1'

# Source: terrain_pipeline.metric_vdm_forms
METRIC_VDM_FORMS_ALGORITHM = 'coherent-cliff-forms-v1'

# Source: terrain_pipeline.metric_vdm_forms
SCHEMA_V2 = 'metric-vdm-forms-v2'

# Source: terrain_pipeline.metric_vdm_forms
ALGORITHM_V2 = 'coherent-cliff-forms-v2'

# Source: terrain_pipeline.metric_vdm_forms
KINDS = frozenset({'layered_ledge', 'undercut_alcove', 'fluted_wall', 'stepped_wall', 'curved_escarpment', 'massive_overhang'})

# Source: terrain_pipeline.metric_vdm_forms
@_i37_dataclass(frozen=True)
class FormRecipe:
    """Wavelength is chart structural length, not vertical layer thickness.

    Curvature is outward-positive at the wall center. End difference is the added
    height at the positive inner fade end minus the negative inner fade end, both
    at v=0; the outer collar returns to the reference bed. Direction rotates
    from +X toward +Z in degrees and None inherits the cliff recipe direction.
    """
    kind: str
    amplitude_m: float
    wavelength_m: float
    seed: int
    surface_curvature_m: float = 0.0
    end_elevation_difference_m: float = 0.0
    extension_direction_degrees: float | None = None

    def __post_init__(self):
        if not isinstance(self.kind, str) or self.kind not in KINDS:
            raise ValueError('invalid cliff form kind')
        if type(self.amplitude_m) not in (int, float) or not _i37_math.isfinite(self.amplitude_m) or self.amplitude_m <= 0:
            raise ValueError('invalid form amplitude_m')
        if type(self.wavelength_m) not in (int, float) or not _i37_math.isfinite(self.wavelength_m) or self.wavelength_m <= 0:
            raise ValueError('invalid form wavelength_m')
        if type(self.seed) is not int or not 0 <= self.seed <= 2 ** 32 - 1:
            raise ValueError('invalid form seed')
        for name in ('surface_curvature_m', 'end_elevation_difference_m'):
            value = getattr(self, name)
            if type(value) not in (int, float) or not _i37_math.isfinite(value):
                raise ValueError(f'invalid form {name}')
        if abs(self.surface_curvature_m) > 0.5 * self.wavelength_m:
            raise ValueError('form surface curvature exceeds structural scale')
        if self.extension_direction_degrees is not None and (type(self.extension_direction_degrees) not in (int, float) or not _i37_math.isfinite(self.extension_direction_degrees)):
            raise ValueError('invalid extension direction')

# Source: terrain_pipeline.metric_vdm_forms
def _spacing(reference):
    horizontal = reference[:, :, (0, 2)]
    adjacent = _i37_np.concatenate((_i37_np.linalg.norm(_i37_np.diff(horizontal, axis=0), axis=2).ravel(), _i37_np.linalg.norm(_i37_np.diff(horizontal, axis=1), axis=2).ravel()))
    if not _i37_np.isfinite(adjacent).all() or _i37_np.any(adjacent <= 0):
        raise ValueError('invalid adjacent horizontal reference spacing')
    return (float(_i37_np.min(adjacent)), float(_i37_np.max(adjacent)))

# Source: terrain_pipeline.metric_vdm_forms
def _check_form_scale(form, recipe, reference):
    _, maximum = _spacing(reference)
    if form.wavelength_m < 4 * maximum:
        raise ValueError('form wavelength below chart sampling limit')
    if form.amplitude_m > min(0.25 * recipe.height_m, 0.5 * recipe.wall_half_width_m):
        raise ValueError('form amplitude exceeds conservative cliff scale')
    if abs(form.end_elevation_difference_m) > recipe.height_m:
        raise ValueError('end elevation difference exceeds cliff height')
    if form.end_elevation_difference_m and (not 0 < recipe.end_fade_m < recipe.half_length_m):
        raise ValueError('end elevation difference requires an interior fade')

# Source: terrain_pipeline.metric_vdm_forms
def _shape(form, u, v, recipe):
    phase = _i37_np.random.default_rng(form.seed).uniform(0, 2 * _i37_math.pi, size=3)
    wave = 2 * _i37_math.pi / form.wavelength_m
    across = (recipe.wall_half_width_m - v) / (2 * recipe.wall_half_width_m)
    wall = _smooth((recipe.half_depth_m - _i37_np.abs(v)) / (recipe.half_depth_m - recipe.wall_half_width_m))
    ends = _smooth((recipe.half_length_m - _i37_np.abs(u)) / recipe.end_fade_m)
    envelope = wall * ends
    band = _i37_np.exp(-((v - 0.2 * recipe.wall_half_width_m) / (0.8 * recipe.wall_half_width_m)) ** 2)
    longitudinal = _i37_np.sin(wave * u + phase[0])
    secondary = _i37_np.sin(0.5 * wave * u + phase[1])
    if form.kind == 'layered_ledge':
        layers = _i37_np.sin(wave * v + phase[2])
        shelves = _i37_np.maximum(0, layers) ** 2
        horizontal = (0.75 * shelves - 0.2 * _i37_np.maximum(0, -layers)) * band
        vertical = 0.2 * layers * band
    elif form.kind == 'undercut_alcove':
        recess = _i37_np.exp(-((across - 0.32) / 0.24) ** 2)
        arch = _smooth((secondary + 1) / 2)
        horizontal = -recess * (0.55 + 0.45 * arch)
        vertical = -0.18 * recess * arch
    elif form.kind == 'fluted_wall':
        horizontal = longitudinal * band * (0.75 + 0.25 * secondary)
        vertical = 0.12 * longitudinal * band
    elif form.kind == 'stepped_wall':
        terraces = _i37_np.tanh(3 * _i37_np.sin(wave * v + phase[2]))
        horizontal = terraces * band * (0.85 + 0.15 * secondary)
        vertical = 0.3 * terraces * band
    elif form.kind == 'curved_escarpment':
        bend = _i37_np.sin(0.5 * wave * u + phase[0])
        horizontal = (0.85 * bend + 0.15 * secondary) * _smooth((recipe.half_depth_m - _i37_np.abs(v)) / recipe.half_depth_m)
        vertical = 0.08 * bend * band
    elif form.kind == 'massive_overhang':
        cap = _smooth((across - 0.42) / 0.35)
        horizontal = cap * (0.8 + 0.2 * secondary)
        vertical = 0.15 * cap
    else:
        raise ValueError(f'unknown cliff form kind: {form.kind!r}')
    if form.surface_curvature_m == 0 and form.end_elevation_difference_m == 0:
        return (form.amplitude_m * envelope * horizontal, form.amplitude_m * envelope * vertical)
    surface_curvature = form.surface_curvature_m * _i37_np.maximum(0.0, 1.0 - (v / recipe.wall_half_width_m) ** 2) ** 2 * ends
    inner_end = recipe.half_length_m - recipe.end_fade_m
    end_tilt = 0.5 * form.end_elevation_difference_m * _i37_np.clip(u / inner_end, -1.0, 1.0) * wall * ends if form.end_elevation_difference_m else 0.0
    return (form.amplitude_m * envelope * horizontal + surface_curvature, form.amplitude_m * envelope * vertical + end_tilt)

# Source: terrain_pipeline.metric_vdm_forms
def _oriented_recipe(recipe, form):
    if form.extension_direction_degrees is None:
        return recipe
    angle = _i37_math.radians(form.extension_direction_degrees % 360)
    along = _i37_np.array((_i37_math.cos(angle), _i37_math.sin(angle)))
    outward = (-along[1], along[0])
    return _i37_replace(recipe, outward_xz=(float(outward[0]), float(outward[1])))

# Source: terrain_pipeline.metric_vdm_forms
def build_formed_vdm(reference_xyz_m, *, recipe: CliffRecipe, form: FormRecipe, protected_mask, source_identity, protection_identity):
    if not isinstance(form, FormRecipe):
        raise ValueError('FormRecipe required')
    oriented_recipe = _oriented_recipe(recipe, form)
    base = build_vdm(reference_xyz_m, recipe=oriented_recipe, protected_mask=protected_mask, source_identity=source_identity, protection_identity=protection_identity)
    arrays = base['arrays']
    reference = arrays['reference_xyz_m']
    _check_form_scale(form, recipe, reference)
    outward = _i37_np.asarray(oriented_recipe.outward_xz, dtype=_i37_np.float64)
    outward /= _i37_np.linalg.norm(outward)
    along = _i37_np.array((outward[1], -outward[0]))
    offset = reference[:, :, (0, 2)] - recipe.center_xz_m
    u = offset @ along
    v = offset @ outward
    horizontal, vertical = _shape(form, u, v, recipe)
    displacement = arrays['displacement_xyz_m'].copy()
    displacement[:, :, 0] += outward[0] * horizontal
    displacement[:, :, 1] += vertical
    displacement[:, :, 2] += outward[1] * horizontal
    displacement[arrays['protected_mask']] = 0
    displacement[0] = displacement[-1] = 0
    displacement[:, 0] = displacement[:, -1] = 0
    formed_arrays = {**arrays, 'displacement_xyz_m': _i37_readonly(displacement), 'vertices_xyz_m': _i37_readonly((reference + displacement).reshape(-1, 3))}
    form_record = _i37_asdict(form)
    default_controls = form.surface_curvature_m == 0 and form.end_elevation_difference_m == 0 and (form.extension_direction_degrees is None)
    if default_controls:
        form_record = {key: form_record[key] for key in ('kind', 'amplitude_m', 'wavelength_m', 'seed')}
    metadata = {**base['metadata'], 'schema': METRIC_VDM_FORMS_SCHEMA if default_controls else SCHEMA_V2, 'algorithm': METRIC_VDM_FORMS_ALGORITHM if default_controls else ALGORITHM_V2, 'form': form_record, 'base_identity_sha256': base['identity_sha256']}
    result = {'arrays': formed_arrays, 'metadata': metadata, 'identity_sha256': _i37_identity(formed_arrays, metadata)}
    validate_formed_vdm(result)
    return result

# Source: terrain_pipeline.metric_vdm_forms
def validate_formed_vdm(result):
    if not isinstance(result, dict) or set(result) != {'arrays', 'metadata', 'identity_sha256'}:
        raise ValueError('invalid formed VDM bundle')
    metadata = result['metadata']
    if not isinstance(metadata, dict) or set(metadata) != {'schema', 'algorithm', 'coordinates', 'recipe', 'source_identity', 'protection_identity', 'hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified', 'form', 'base_identity_sha256'}:
        raise ValueError('invalid formed VDM metadata')
    versions = {METRIC_VDM_FORMS_SCHEMA: METRIC_VDM_FORMS_ALGORITHM, SCHEMA_V2: ALGORITHM_V2}
    if metadata['schema'] not in versions or metadata['algorithm'] != versions[metadata['schema']]:
        raise ValueError('invalid formed VDM version')
    base_identity = metadata['base_identity_sha256']
    if not isinstance(base_identity, str) or len(base_identity) != 64 or any((character not in '0123456789abcdef' for character in base_identity)):
        raise ValueError('invalid base VDM identity')
    try:
        form_record = metadata['form']
        form = FormRecipe(**form_record)
        expected_fields = set(_i37_asdict(form))
        if metadata['schema'] == METRIC_VDM_FORMS_SCHEMA:
            expected_fields -= {'surface_curvature_m', 'end_elevation_difference_m', 'extension_direction_degrees'}
        elif form.surface_curvature_m == 0 and form.end_elevation_difference_m == 0 and (form.extension_direction_degrees is None):
            raise ValueError('default controls require v1')
        if set(form_record) != expected_fields:
            raise ValueError('unexpected form field')
        recipe_record = metadata['recipe']
        recipe = CliffRecipe(**{**recipe_record, 'center_xz_m': tuple(recipe_record['center_xz_m']), 'outward_xz': tuple(recipe_record['outward_xz'])})
        if form.extension_direction_degrees is not None:
            angle = _i37_math.radians(form.extension_direction_degrees % 360)
            expected_outward = (-_i37_math.sin(angle), _i37_math.cos(angle))
            actual_outward = _i37_np.asarray(recipe.outward_xz, dtype=float)
            actual_outward /= _i37_np.linalg.norm(actual_outward)
            if not _i37_np.allclose(actual_outward, expected_outward, rtol=0, atol=1e-12):
                raise ValueError('saved extension direction disagrees with recipe')
    except (TypeError, KeyError, ValueError, AttributeError) as error:
        raise ValueError('invalid saved form or recipe') from error
    base_metadata = {key: value for key, value in metadata.items() if key not in ('form', 'base_identity_sha256')}
    base_metadata.update(schema=SCHEMA, algorithm=ALGORITHM)
    projection = {'arrays': result['arrays'], 'metadata': base_metadata, 'identity_sha256': _i37_identity(result['arrays'], base_metadata)}
    validate_vdm(projection)
    _check_form_scale(form, recipe, result['arrays']['reference_xyz_m'])
    if result['identity_sha256'] != _i37_identity(result['arrays'], metadata):
        raise ValueError('formed VDM identity mismatch')
    return True

# Source: terrain_pipeline.metric_vdm_forms
def save_formed_vdm(path, result):
    _i37_save_bundle(path, result, validator=validate_formed_vdm)

# Source: terrain_pipeline.metric_vdm_forms
def load_formed_vdm(path, *, expected_sha256, expected_identity):
    if not isinstance(expected_identity, str) or len(expected_identity) != 64:
        raise ValueError('expected formed VDM identity required')
    result = _i37_load_bundle(path, expected_sha256=expected_sha256, validator=validate_formed_vdm, header_validator=_vdm_headers)
    if result['identity_sha256'] != expected_identity:
        raise ValueError('external formed VDM identity mismatch')
    return result

# Source: terrain_pipeline.metric_vdm_fault_common
def _finite(value, name):
    if type(value) not in (int, float) or not _i38_math.isfinite(value):
        raise ValueError(f'invalid {name}')

# Source: terrain_pipeline.metric_vdm_fault_common
@_i38_dataclass(frozen=True)
class FaultRecipe:
    plane_origin_xz_m: tuple
    strike_degrees: float
    slip_m: float
    moving_side: str
    transition_width_m: float

    def __post_init__(self):
        if not isinstance(self.plane_origin_xz_m, tuple) or len(self.plane_origin_xz_m) != 2:
            raise ValueError('invalid plane origin')
        for value in self.plane_origin_xz_m:
            _finite(value, 'plane origin')
        _finite(self.strike_degrees, 'strike')
        _finite(self.slip_m, 'slip')
        if self.moving_side not in ('positive', 'negative'):
            raise ValueError('moving_side must be positive or negative')
        _finite(self.transition_width_m, 'transition width')
        if self.transition_width_m <= 0:
            raise ValueError('transition width must be positive')

# Source: terrain_pipeline.metric_vdm_fault_common
def _metric_vdm_fault_common_smooth(value):
    value = _i38_np.clip(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)

# Source: terrain_pipeline.metric_vdm_fault_common
def _selection_weights(reference, selection, width):
    """Keep the original metric mask-distance arithmetic unchanged."""
    rows, columns = selection.shape
    distances = _i38_np.full(selection.shape, _i38_np.inf, _i38_np.float64)
    outside = _i38_np.argwhere(~selection)
    if len(outside):
        inside = _i38_np.argwhere(selection)
        for row, column in inside:
            distances[row, column] = _i38_np.min(_i38_np.hypot(outside[:, 0] - row, outside[:, 1] - column))
    spacing = []
    horizontal = reference[:, :, (0, 2)]
    if rows > 1:
        spacing.extend(_i38_np.linalg.norm(_i38_np.diff(horizontal, axis=0), axis=2).ravel().tolist())
    if columns > 1:
        spacing.extend(_i38_np.linalg.norm(_i38_np.diff(horizontal, axis=1), axis=2).ravel().tolist())
    metre_spacing = float(_i38_np.median(spacing)) if spacing else 1.0
    weights = _i38_np.where(selection, _metric_vdm_fault_common_smooth(distances * metre_spacing / width), 0.0)
    return weights.reshape(-1)

# Source: terrain_pipeline.metric_vdm_fault_v2
METRIC_VDM_FAULT_MECHANISM_2_SCHEMA = 'metric-vdm-fault-v2'

# Source: terrain_pipeline.metric_vdm_fault_v2
METRIC_VDM_FAULT_MECHANISM_2_ALGORITHM = 'local-deformed-vdm-edge-cut-strike-slip-v2'

# Source: terrain_pipeline.metric_vdm_fault_v2
METRIC_VDM_FAULT_MECHANISM_2_ARRAY_KEYS = {'reference_xyz_m', 'source_vertices_xyz_m', 'source_triangles', 'vertices_xyz_m', 'triangles', 'vertex_side', 'transition_weight', 'applied_displacement_xyz_m', 'vertex_source_index', 'triangle_source_index', 'seam_edges', 'protected_mask', 'vertex_source_edge', 'vertex_source_fraction'}

# Source: terrain_pipeline.metric_vdm_fault_v2
def apply_fault(source_vdm, *, recipe, selection_mask):
    if not isinstance(recipe, FaultRecipe):
        raise ValueError('FaultRecipe required')
    recipe.__post_init__()
    source = source_vdm['arrays']
    chart = source['reference_xyz_m']
    points = source['vertices_xyz_m']
    triangles = source['triangles']
    protected = source['protected_mask']
    selection = _i39_np.asarray(selection_mask)
    if chart.ndim != 3 or chart.shape[-1] != 3 or points.shape != (chart.shape[0] * chart.shape[1], 3) or (points.dtype != _i39_np.float64) or (not _i39_np.isfinite(points).all()) or (len(points) > 100000) or (selection.dtype != bool) or (selection.shape != chart.shape[:2]) or (not selection.any()) or _i39_np.any(selection & protected) or (source_vdm['identity_sha256'] != _i39_identity(source, source_vdm['metadata'])):
        raise ValueError('invalid deformed VDM source, identity, or selection')
    _check_mesh(points, triangles)
    weights = _selection_weights(chart, selection, recipe.transition_width_m)
    influenced = _i39_np.any(weights[triangles] > 0.0, axis=1)
    if _i39_np.any(protected.ravel()[triangles[influenced]]):
        raise ValueError('fault influence intersects protected VDM area')
    angle = _i39_math.radians(recipe.strike_degrees)
    tangent = _i39_np.array([_i39_math.cos(angle), 0.0, _i39_math.sin(angle)])
    normal = _i39_np.array([-_i39_math.sin(angle), 0.0, _i39_math.cos(angle)])
    signed = (points - _i39_np.array([recipe.plane_origin_xz_m[0], 0.0, recipe.plane_origin_xz_m[1]])) @ normal
    signs = _i39_np.where(signed >= 0.0, 1, -1).astype(_i39_np.int8)
    cut = influenced & (signed[triangles].min(axis=1) <= 0.0) & (signed[triangles].max(axis=1) >= 0.0)
    vertices = points.tolist()
    sides = signs.tolist()
    vertex_weights = weights.tolist()
    edges = [[index, index] for index in range(len(points))]
    fractions = [0.0] * len(points)
    vertex_sources = list(range(len(points)))
    output = triangles[~cut].tolist()
    provenance = _i39_np.flatnonzero(~cut).tolist()
    lookup = {}
    seam = set()

    def vertex(barycentric, source_face, side):
        support = _i39_np.flatnonzero(barycentric > 1e-12)
        if len(support) == 1:
            source_index = int(source_face[support[0]])
            if abs(signed[source_index]) > 1e-10:
                return source_index
            edge = (source_index, source_index)
            fraction = 0.0
        else:
            edge = tuple(sorted((int(source_face[index]) for index in support)))
            if len(edge) != 2:
                raise ValueError('cut vertex must lie on an original edge')
            fraction = float(barycentric[_i39_np.flatnonzero(source_face == edge[1])[0]])
            source_index = -1
        key = (edge, side)
        if key not in lookup:
            lookup[key] = len(vertices)
            vertices.append((barycentric @ points[source_face]).tolist())
            sides.append(side)
            vertex_weights.append(float(barycentric @ weights[source_face]))
            edges.append(list(edge))
            fractions.append(fraction)
            vertex_sources.append(source_index)
        return lookup[key]
    for face_index in _i39_np.flatnonzero(cut):
        source_face = triangles[face_index]
        distances = signed[source_face]
        for side in (1, -1):
            polygon = []
            for index in range(3):
                previous = (index - 1) % 3
                inside = side * distances[index] >= 0.0
                prior_inside = side * distances[previous] >= 0.0
                if inside != prior_inside:
                    fraction = distances[previous] / (distances[previous] - distances[index])
                    barycentric = _i39_np.zeros(3)
                    barycentric[previous] = 1.0 - fraction
                    barycentric[index] = fraction
                    polygon.append(vertex(barycentric, source_face, side))
                if inside:
                    polygon.append(vertex(_i39_np.eye(3)[index], source_face, side))
            polygon = list(dict.fromkeys(polygon))
            for index in range(1, len(polygon) - 1):
                face = [polygon[0], polygon[index], polygon[index + 1]]
                trial = _i39_np.asarray([vertices[value] for value in face])
                if _i39_np.linalg.norm(_i39_np.cross(trial[1] - trial[0], trial[2] - trial[0])) <= 1e-12:
                    continue
                output.append(face)
                provenance.append(int(face_index))
                for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
                    if abs(float(_i39_np.dot(_i39_np.asarray(vertices[first]) - points[source_face[0]], normal)) + distances[0]) < 1e-08 and abs(float(_i39_np.dot(_i39_np.asarray(vertices[second]) - points[source_face[0]], normal)) + distances[0]) < 1e-08:
                        seam.add(tuple(sorted((first, second))))
    output_array = _i39_np.asarray(output, _i39_np.int64)
    used = _i39_np.unique(output_array)
    remap = _i39_np.full(len(vertices), -1, _i39_np.int64)
    remap[used] = _i39_np.arange(len(used))
    before = _i39_np.asarray(vertices, _i39_np.float64)[used]
    side_array = _i39_np.asarray(sides, _i39_np.int8)[used]
    weight_array = _i39_np.asarray(vertex_weights, _i39_np.float64)[used]
    displacement = weight_array[:, None] * tangent * recipe.slip_m
    moving_side = 1 if recipe.moving_side == 'positive' else -1
    displacement[side_array != moving_side] = 0.0
    actual_faces = remap[output_array]
    moving_faces = actual_faces[_i39_np.any(_i39_np.linalg.norm(displacement[actual_faces], axis=2) > 0.0, axis=1)]
    protected_positions = chart[:, :, (0, 2)][protected]
    if len(protected_positions) and len(moving_faces):
        chart_xz = chart[:, :, (0, 2)]
        spacing = _i39_np.median(_i39_np.concatenate((_i39_np.linalg.norm(_i39_np.diff(chart_xz, axis=0), axis=2).ravel(), _i39_np.linalg.norm(_i39_np.diff(chart_xz, axis=1), axis=2).ravel())))
        for face in moving_faces:
            swept = _i39_np.concatenate((before[face][:, (0, 2)], (before + displacement)[face][:, (0, 2)]))
            lower, upper = (swept.min(axis=0) - spacing / 2.0, swept.max(axis=0) + spacing / 2.0)
            if _i39_np.any(_i39_np.all((protected_positions >= lower) & (protected_positions <= upper), axis=1)):
                raise ValueError('conservative swept fault patch intersects protected source cell')
    arrays = {'reference_xyz_m': chart.copy(), 'source_vertices_xyz_m': points.copy(), 'source_triangles': triangles.copy(), 'vertices_xyz_m': before + displacement, 'triangles': remap[output_array], 'vertex_side': side_array, 'transition_weight': weight_array, 'applied_displacement_xyz_m': displacement, 'vertex_source_index': _i39_np.asarray(vertex_sources, _i39_np.int64)[used], 'triangle_source_index': _i39_np.asarray(provenance, _i39_np.int64), 'seam_edges': remap[_i39_np.asarray(sorted(seam), _i39_np.int64).reshape(-1, 2)], 'protected_mask': protected.copy(), 'vertex_source_edge': _i39_np.asarray(edges, _i39_np.int64)[used], 'vertex_source_fraction': _i39_np.asarray(fractions, _i39_np.float64)[used]}
    metadata = {'schema': METRIC_VDM_FAULT_MECHANISM_2_SCHEMA, 'algorithm': METRIC_VDM_FAULT_MECHANISM_2_ALGORITHM, **_i39_asdict(recipe), 'source_identity': source_vdm['identity_sha256'], 'protection_identity': source_vdm['metadata'].get('protection_identity', ''), 'coordinates': 'xyz metres; X east, Y up, Z south', 'slip_axis': 'horizontal_strike', 'reference_semantics': 'original input chart; source_vertices are the already deformed VDM', 'cut_semantics': 'only triangles touching nonzero local selection influence are split', 'protection_semantics': 'source influence exclusion plus conservative swept XZ triangle bounding boxes against protected chart cells', 'cut_source_triangle_count': int(cut.sum()), 'selection_shape_zx': list(selection.shape), 'selection_cell_count': int(selection.sum()), 'source_triangle_count': len(triangles), 'output_triangle_count': len(output), 'seam_edge_count': len(seam), 'closed_surface': False, 'hydraulic_ready': False, 'natural_outlet_verified': False, 'publishable': False, 'self_intersection_verified': False, 'overlap_diagnostic': 'not_verified'}
    result = {'arrays': {key: _i39_readonly(value) for key, value in arrays.items()}, 'metadata': metadata}
    result['identity_sha256'] = _i39_identity(result['arrays'], metadata)
    validate_fault(result)
    return result

# Source: terrain_pipeline.metric_vdm_fault_v2
def validate_fault(result):
    arrays, metadata = (result['arrays'], result['metadata'])
    if set(arrays) != METRIC_VDM_FAULT_MECHANISM_2_ARRAY_KEYS or metadata.get('schema') != METRIC_VDM_FAULT_MECHANISM_2_SCHEMA or metadata.get('algorithm') != METRIC_VDM_FAULT_MECHANISM_2_ALGORITHM:
        raise ValueError('invalid v2 fault fields')
    for flag in ('closed_surface', 'hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified'):
        if metadata.get(flag) is not False:
            raise ValueError('fault certification flags must remain false')
    for value in arrays.values():
        if not _i39_np.isfinite(value).all():
            raise ValueError('nonfinite fault array')
    points, displacement = (arrays['vertices_xyz_m'], arrays['applied_displacement_xyz_m'])
    edges, fractions = (arrays['vertex_source_edge'], arrays['vertex_source_fraction'])
    source = arrays['source_vertices_xyz_m']
    triangles = arrays['triangles']
    weights, sides = (arrays['transition_weight'], arrays['vertex_side'])
    if points.dtype != _i39_np.float64 or points.ndim != 2 or points.shape[1] != 3 or (displacement.shape != points.shape) or (edges.shape != (len(points), 2)) or (edges.dtype != _i39_np.int64) or _i39_np.any(edges < 0) or _i39_np.any(edges >= len(source)) or (fractions.shape != (len(points),)) or _i39_np.any(fractions < 0.0) or _i39_np.any(fractions > 1.0) or (weights.shape != (len(points),)) or _i39_np.any(weights < 0.0) or _i39_np.any(weights > 1.0) or (sides.shape != (len(points),)) or (not _i39_np.isin(sides, (-1, 1)).all()):
        raise ValueError('invalid fault edge provenance or shapes')
    before = source[edges[:, 0]] * (1.0 - fractions[:, None]) + source[edges[:, 1]] * fractions[:, None]
    if not _i39_np.allclose(points - displacement, before, rtol=0.0, atol=1e-08):
        raise ValueError('fault erased source VDM geometry or changed edge interpolation')
    angle = _i39_math.radians(metadata['strike_degrees'])
    expected = weights[:, None] * _i39_np.array([_i39_math.cos(angle), 0.0, _i39_math.sin(angle)]) * metadata['slip_m']
    expected[sides != (1 if metadata['moving_side'] == 'positive' else -1)] = 0.0
    if not _i39_np.allclose(displacement, expected, rtol=0.0, atol=1e-10):
        raise ValueError('fault displacement differs from signed horizontal slip')
    source_index = arrays['vertex_source_index']
    face_source = arrays['triangle_source_index']
    original_faces = arrays['source_triangles']
    seam = arrays['seam_edges']
    if source_index.shape != (len(points),) or source_index.dtype != _i39_np.int64 or _i39_np.any(source_index < -1) or _i39_np.any(source_index >= len(source)) or (face_source.shape != (len(triangles),)) or (face_source.dtype != _i39_np.int64) or _i39_np.any(face_source < 0) or _i39_np.any(face_source >= len(original_faces)) or (seam.dtype != _i39_np.int64) or (seam.ndim != 2) or (seam.shape[1] != 2) or _i39_np.any(seam < 0) or _i39_np.any(seam >= len(points)):
        raise ValueError('invalid source indices or seam edges')
    _check_mesh(source, original_faces)
    exact = source_index >= 0
    if not _i39_np.allclose(before[exact], source[source_index[exact]], rtol=0.0, atol=1e-08):
        raise ValueError('exact source vertex mapping mismatch')
    support = edges[triangles]
    owners = original_faces[face_source]
    if not _i39_np.all(_i39_np.any(support[..., None] == owners[:, None, None, :], axis=-1)):
        raise ValueError('output triangle provenance leaves original triangle')
    if _i39_np.any(arrays['protected_mask'].ravel()[edges[_i39_np.linalg.norm(displacement, axis=1) > 0.0]]):
        raise ValueError('protected source vertices displaced')
    _check_mesh(points, triangles)
    influenced = _i39_np.any(weights[triangles] > 0.0, axis=1)
    if _i39_np.any(_i39_np.ptp(sides[triangles[influenced]], axis=1) != 0):
        raise ValueError('influenced triangle crosses fault seam')
    if result['identity_sha256'] != _i39_identity(arrays, metadata):
        raise ValueError('fault identity mismatch')
    return True

# Source: terrain_pipeline.metric_vdm_fault_v2
def save_fault(path, result):
    _i39_save_bundle(path, result, validator=validate_fault)

# Source: terrain_pipeline.metric_vdm_fault_v2
def load_fault(path, *, expected_sha256, expected_identity):

    def headers(values):
        if set(values) != METRIC_VDM_FAULT_MECHANISM_2_ARRAY_KEYS | {'manifest'}:
            raise ValueError('unexpected v2 fault archive fields')
    result = _i39_load_bundle(path, expected_sha256=expected_sha256, validator=validate_fault, header_validator=headers)
    if result['identity_sha256'] != expected_identity:
        raise ValueError('external fault identity mismatch')
    return result

# Source: terrain_pipeline.td_channel_vdm
def channel_protection(surface, hierarchy):
    _i40_validate_channel_surface(surface)
    _i40_validate_basin_hierarchy(hierarchy)
    metadata = surface['metadata']
    if metadata['hierarchy_identity'] != hierarchy['identity_sha256']:
        raise ValueError('surface/hierarchy identity mismatch')
    first_x, last_x, first_z, last_z = metadata['window']
    shape = (last_z - first_z + 1, last_x - first_x + 1)
    reference = surface['arrays']['vertices_xyz_m'].reshape(*shape, 3)
    topology = hierarchy['arrays']
    origin = hierarchy['metadata']['origin_m_xz']
    spacing = hierarchy['metadata']['spacing_m']
    fractional = (reference[..., [0, 2]] - origin) / spacing
    lower = _i40_np.floor(fractional).astype(_i40_np.int64)
    upper = _i40_np.ceil(fractional).astype(_i40_np.int64)
    if _i40_np.any(lower < 0) or _i40_np.any(upper[..., 0] >= topology['height_m'].shape[1]) or _i40_np.any(upper[..., 1] >= topology['height_m'].shape[0]):
        raise ValueError('surface outside hierarchy sample coverage')
    protected = surface['arrays']['candidate_cut_m'].reshape(shape) > 0
    for column in (lower[..., 0], upper[..., 0]):
        for row in (lower[..., 1], upper[..., 1]):
            protected |= topology['protected_mask'][row, column] | ~topology['valid_mask'][row, column]
    padded = _i40_np.pad(protected, 1)
    expanded = _i40_np.zeros(shape, bool)
    for row in range(3):
        for column in range(3):
            expanded |= padded[row:row + shape[0], column:column + shape[1]]
    return _i40_readonly(expanded)

# Source: terrain_pipeline.td_channel_vdm
def reject_protected_sweep(reference, displaced, triangles, protected):
    """Reject projected swept triangle boxes intersecting protected metre cells."""
    rows, columns = protected.shape
    original = reference.reshape(-1, 3)
    changed = _i40_np.any(displaced != original, axis=1)
    moving_faces = triangles[_i40_np.any(changed[triangles], axis=1)]
    if not len(moving_faces):
        return
    before = original[moving_faces][:, :, [0, 2]]
    after = displaced[moving_faces][:, :, [0, 2]]
    lower = _i40_np.minimum(before.min(axis=1), after.min(axis=1))
    upper = _i40_np.maximum(before.max(axis=1), after.max(axis=1))
    origin = reference[0, 0, [0, 2]]
    if _i40_np.any(lower < origin) or _i40_np.any(upper > reference[-1, -1, [0, 2]]):
        raise ValueError('VDM moved face outside source domain')
    first = _i40_np.maximum(_i40_np.ceil(lower - origin - 0.5).astype(_i40_np.int64), 0)
    last = _i40_np.minimum(_i40_np.floor(upper - origin + 0.5).astype(_i40_np.int64), [columns - 1, rows - 1])
    prefix = _i40_np.pad(protected.astype(_i40_np.int64), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    count = prefix[last[:, 1] + 1, last[:, 0] + 1] - prefix[first[:, 1], last[:, 0] + 1] - prefix[last[:, 1] + 1, first[:, 0]] + prefix[first[:, 1], first[:, 0]]
    if _i40_np.any(count):
        raise ValueError('VDM swept triangle box intersects protected river/domain footprint')

# Source: terrain_pipeline.td_channel_vdm
def build_channel_vdm(surface, hierarchy, *, recipe, form=None):
    protected = channel_protection(surface, hierarchy)
    reference = surface['arrays']['vertices_xyz_m'].reshape(*protected.shape, 3)
    protection_identity = _i40_identity({'protected_mask': protected}, {'surface_identity': surface['identity_sha256'], 'hierarchy_identity': hierarchy['identity_sha256'], 'policy': 'positive_candidate_cut_or_coarse_protected_unknown_stencil_plus_1m_collar'})
    options = dict(recipe=recipe, protected_mask=protected, source_identity=surface['identity_sha256'], protection_identity=protection_identity)
    if form is None:
        result = build_vdm(reference, **options)
    else:
        pass  # Reference the existing consolidated global directly.
        result = build_formed_vdm(reference, form=form, **options)
    if not _i40_np.array_equal(result['arrays']['triangles'], surface['arrays']['triangles']):
        raise ValueError('VDM changed source triangle connectivity')
    reject_protected_sweep(reference, result['arrays']['vertices_xyz_m'], result['arrays']['triangles'], protected)
    return result
