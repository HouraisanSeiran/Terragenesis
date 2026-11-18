"""Fixed-grid, CPU-only qualification of exposed islands for explicit TD work.

Default qualification is exposed area strictly greater than 25 square km.
Width filtering is opt-in; coastal blending never decides area qualification.
All areas/distances are finite raster approximations, not vector measurements.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np
from scipy import ndimage as nd

from .common_infra import canonical_json

LEGACY_ALGORITHM = 'island-mountains-fixed-interior-v1'
LEGACY_POLICY = 'frozen-island-base-coastal-zero-td-land-floor-v1'
AREA_ALGORITHM = 'island-mountains-strict-area-v2'
AREA_POLICY = 'frozen-island-area100-coastal-height-taper-v2'
ALGORITHM = 'island-mountains-area-peaks-v3'
POLICY = 'frozen-island-global-raw-area-peak-v3'
SCHEMA = 'island-mountain-plan-v3'
VERSIONS = {(LEGACY_ALGORITHM, LEGACY_POLICY, 'island-mountain-plan-v1'),
            (AREA_ALGORITHM, AREA_POLICY, 'island-mountain-plan-v2'),
            (ALGORITHM, POLICY, SCHEMA)}
STRUCTURE = nd.generate_binary_structure(2, 1)


def identity(record):
    return hashlib.sha256(canonical_json(record).encode()).hexdigest()


@dataclass(frozen=True)
class IslandMountainConfig:
    analysis_spacing_m: float = 1000.
    min_area_km2: float = 25.
    min_usable_width_m: float = 0.
    coast_buffer_m: float = 0.
    blend_ramp_m: float = 1000.
    coastal_height_ramp_m: float = 50.
    land_floor_m: float = 2.
    max_analysis_cells: int = 4000000
    analysis_bounds_m: tuple[float, float, float, float] | None = None
    peak_min_m: float = 300.
    peak_max_m: float = 3000.
    peak_ripple_fraction: float = .1
    peak_saturation_area_km2: float = 2000.

    def __post_init__(self):
        for name in ('analysis_spacing_m', 'min_area_km2', 'blend_ramp_m', 'coastal_height_ramp_m'):
            value = getattr(self, name)
            if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                raise ValueError('invalid positive mountain parameter: ' + name)
        for name in ('min_usable_width_m', 'coast_buffer_m', 'land_floor_m'):
            value = getattr(self, name)
            if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
                raise ValueError('invalid nonnegative mountain parameter: ' + name)
        if type(self.max_analysis_cells) is not int or not 1 <= self.max_analysis_cells <= 16000000:
            raise ValueError('invalid analysis budget')
        if self.analysis_bounds_m is not None:
            bounds = tuple(self.analysis_bounds_m)
            if (len(bounds) != 4 or any(type(v) not in (float, int) or not math.isfinite(v) for v in bounds)
                    or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]):
                raise ValueError('invalid fixed analysis bounds')
            object.__setattr__(self, 'analysis_bounds_m', bounds)
        peak_height_for_area(self.min_area_km2, self.peak_min_m, self.peak_max_m, 0, 'config-validation',
            saturation_area_km2=self.peak_saturation_area_km2, threshold_area_km2=100.,
            ripple_fraction=self.peak_ripple_fraction)


def peak_height_for_area(area_km2, min_m=300., max_m=3000., seed=20260903, island_key='default', *,
                         saturation_area_km2=2000., threshold_area_km2=100., ripple_fraction=.1):
    """Stable absolute peak altitude: log area saturation and bounded seed ripple."""
    numbers = (area_km2, min_m, max_m, saturation_area_km2, threshold_area_km2, ripple_fraction)
    if (any(type(v) not in (float, int) or not math.isfinite(v) for v in numbers)
            or area_km2 <= 0 or min_m <= 0 or max_m < min_m or threshold_area_km2 <= 0
            or saturation_area_km2 <= threshold_area_km2 or not 0 <= ripple_fraction < 1
            or type(seed) is not int or not 0 <= seed < 2**63 or not isinstance(island_key, str) or not island_key):
        raise ValueError('invalid area peak-height parameters')
    fraction = np.clip(math.log(area_km2/threshold_area_km2)/math.log(saturation_area_km2/threshold_area_km2), 0., 1.)
    unit = int.from_bytes(hashlib.sha256(canonical_json(['island-area-peak-v3', seed, island_key]).encode()).digest()[:8], 'big')/2**64
    return float((min_m+(max_m-min_m)*fraction)*(1+ripple_fraction*(2*unit-1)))


@dataclass(frozen=True, init=False)
class IslandMountainPlan:
    _manifest_json: str
    selected_interior: np.ndarray
    coast_distance_m: np.ndarray
    interior_distance_m: np.ndarray

    def __init__(self, manifest, selected_interior, coast_distance_m, interior_distance_m):
        object.__setattr__(self, '_manifest_json', canonical_json(manifest))
        for name, array in (('selected_interior', selected_interior),
                            ('coast_distance_m', coast_distance_m),
                            ('interior_distance_m', interior_distance_m)):
            array = np.ascontiguousarray(array)
            frozen = np.frombuffer(array.tobytes(), dtype=array.dtype).reshape(array.shape)
            object.__setattr__(self, name, frozen)

    @property
    def manifest(self):
        return json.loads(self._manifest_json)

    @property
    def identity(self):
        return self.manifest['identity']

    @property
    def empty(self):
        return not self.manifest['selected_components']


def _summary(array):
    return dict(shape=list(array.shape), dtype=array.dtype.str,
                sha256=hashlib.sha256(array.tobytes()).hexdigest())


def _distance(mask, spacing):
    # A padded sea border also handles components touching the finite boundary.
    return nd.distance_transform_edt(np.pad(mask, 1))[1:-1, 1:-1] * spacing


def _overlap(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _support_window(feature, source_bounds, spacing, margin_m):
    padding = feature.support_radius_m + margin_m
    raw = (feature.center_x_m-padding, feature.center_z_m-padding,
           feature.center_x_m+padding, feature.center_z_m+padding)
    return [max(source_bounds[0], source_bounds[0]+math.floor((raw[0]-source_bounds[0])/spacing)*spacing),
            max(source_bounds[1], source_bounds[1]+math.floor((raw[1]-source_bounds[1])/spacing)*spacing),
            min(source_bounds[2], source_bounds[0]+math.ceil((raw[2]-source_bounds[0])/spacing)*spacing),
            min(source_bounds[3], source_bounds[1]+math.ceil((raw[3]-source_bounds[1])/spacing)*spacing)]


def _fixed_bounds(source_bounds, bounds, spacing):
    if (bounds[0] < source_bounds[0] or bounds[1] < source_bounds[1]
            or bounds[2] > source_bounds[2] or bounds[3] > source_bounds[3]):
        raise ValueError('analysis window outside finite source')
    for value, origin, edge in zip(bounds,
            (source_bounds[0], source_bounds[1], source_bounds[0], source_bounds[1]), source_bounds):
        coordinate = (value-origin)/spacing
        # A finite source partial final cell is the only unaligned endpoint.
        if value != edge and not math.isclose(coordinate, round(coordinate), abs_tol=1e-8, rel_tol=0):
            raise ValueError('analysis window must align with the fixed source-origin grid')


def _analysis_bounds(product, config):
    source_bounds = product.source.bounds_m
    bounds = config.analysis_bounds_m or source_bounds
    _fixed_bounds(source_bounds, bounds, config.analysis_spacing_m)
    if config.analysis_bounds_m is not None:
        for feature in product.features:
            support = _support_window(feature, source_bounds, config.analysis_spacing_m, config.analysis_spacing_m)
            if _overlap(bounds, support) and not (bounds[0] <= support[0] and bounds[1] <= support[1]
                    and bounds[2] >= support[2] and bounds[3] >= support[3]):
                raise ValueError('analysis window cuts a complete feature-support group/halo')
    return bounds


def mountain_analysis_windows(product, config=None, *, tile_margin_m=0.):
    """Candidate fixed windows without any full-domain raster allocation.

    Support boxes only bound dependencies. Qualification always queries actual
    land in the complete product. Overlapping snapped windows merge, including
    their halo/tile margin. Oversized groups are returned as pending-analysis;
    the caller must report partial coverage rather than silently skip them.
    """
    config = config or IslandMountainConfig()
    if config.analysis_bounds_m is not None:
        raise ValueError('window grouping requires the complete source, not an existing subwindow')
    if type(tile_margin_m) not in (int, float) or not math.isfinite(tile_margin_m) or tile_margin_m < 0:
        raise ValueError('invalid tile margin')
    if len(product.features) > 20000:
        raise ValueError('feature support grouping exceeds inventory budget')
    source_bounds = product.source.bounds_m
    spacing = config.analysis_spacing_m
    groups = [dict(bounds_m=_support_window(f, source_bounds, spacing, spacing+tile_margin_m),
                   feature_ids=[f.feature_id]) for f in product.features]
    # Sweep one bounding rectangle at a time. No all-pairs matrix or full-world
    # masks; intermediate storage is bounded by the frozen feature inventory.
    while True:
        groups.sort(key=lambda g: (g['bounds_m'][0], g['bounds_m'][1], g['feature_ids']))
        merged = []
        changed = False
        for group in groups:
            matching = [i for i,other in enumerate(merged) if _overlap(group['bounds_m'], other['bounds_m'])]
            if not matching:
                merged.append(group)
                continue
            changed = True
            boxes = [group['bounds_m']]+[merged[i]['bounds_m'] for i in matching]
            feature_ids = group['feature_ids']+[key for i in matching for key in merged[i]['feature_ids']]
            group = dict(bounds_m=[min(b[0] for b in boxes), min(b[1] for b in boxes),
                                   max(b[2] for b in boxes), max(b[3] for b in boxes)],
                         feature_ids=sorted(feature_ids))
            for i in reversed(matching):
                merged.pop(i)
            merged.append(group)
        groups = merged
        if not changed:
            break
    for group in groups:
        bounds = group['bounds_m']
        cells = math.ceil((bounds[2]-bounds[0])/spacing)*math.ceil((bounds[3]-bounds[1])/spacing)
        group.update(analysis_cells=cells, status='ready' if cells <= config.max_analysis_cells else 'pending-analysis',
            source_identity=product.source.identity, product_identity=product.identity,
            analysis_spacing_m=spacing, halo_m=spacing, tile_margin_m=float(tile_margin_m))
        if group['status'] == 'pending-analysis':
            group['reason'] = 'complete support group exceeds max_analysis_cells; no coarsening or partial qualification'
    return sorted(groups, key=lambda g:(g['bounds_m'][1],g['bounds_m'][0]))


def analyze_island_mountains(product, config=None):
    config = config or IslandMountainConfig()
    bounds = _analysis_bounds(product, config)
    spacing = config.analysis_spacing_m
    nx = math.ceil((bounds[2]-bounds[0])/spacing)
    nz = math.ceil((bounds[3]-bounds[1])/spacing)
    if nx*nz > config.max_analysis_cells:
        raise ValueError('fixed island analysis exceeds cell budget')
    # Last partial cell is sampled at its own centre and contributes its area.
    xe = np.minimum(bounds[0]+np.arange(nx+1)*spacing, bounds[2])
    ze = np.minimum(bounds[1]+np.arange(nz+1)*spacing, bounds[3])
    x = (xe[:-1]+xe[1:])/2
    z = (ze[:-1]+ze[1:])/2
    land = np.zeros((nz, nx), bool)
    original_land = np.zeros_like(land)
    generated = np.zeros_like(land)
    lagoon = np.zeros_like(land)
    special_volcanic = np.zeros_like(land)
    query_budget = min(16384, getattr(product.config, 'max_query_points', 16384),
                       getattr(product.config, 'max_working_bytes', 16384*224)//224)
    if query_budget < 1:
        raise ValueError('island product has no analysis query budget')
    column_batch = min(nx, query_budget)
    row_batch = max(1, min(64, query_budget//column_batch))
    for start in range(0, nz, row_batch):
        for column in range(0, nx, column_batch):
            window = np.s_[start:start+row_batch, column:column+column_batch]
            q = product.query(x[None, column:column+column_batch], z[start:start+row_batch, None])
            land[window] = q['elevation_m'] >= 0
            original_land[window] = q['base_elevation_m'] >= 0
            generated[window] = (q['elevation_m'] >= 0) & (q['base_elevation_m'] < 0) & q['protected']
            lagoon[window] = q['lagoon']
            special_volcanic[window] = np.asarray(q.get('volcano_weight', 0)) > 0
    labels, _ = nd.label(land & ~lagoon, STRUCTURE)
    # Half a cell diagonal preserves some interior in one-cell-wide islands.
    # Actual sea-level taper below removes weight continuously at the shore.
    margin = math.sqrt(2)*spacing/2
    distance = np.maximum(_distance(land & ~lagoon, spacing)-margin, 0.)
    selected = np.zeros_like(labels, dtype=np.int32)
    records = []
    lagoon_edge = nd.binary_dilation(lagoon, structure=STRUCTURE)
    slices = nd.find_objects(labels)
    for component, window in enumerate(slices, 1):
        mask = labels[window] == component
        if not np.any(generated[window] & mask):
            continue
        zz, xx = window
        area = float(np.sum(mask*np.diff(ze)[zz, None]*np.diff(xe)[None, xx])/1e6)
        reasons = []
        if zz.start == 0 or xx.start == 0 or zz.stop == nz or xx.stop == nx:
            reasons.append('finite-boundary')
        if np.any(original_land[window] & mask):
            reasons.append('connected-to-original-land')
        if np.any(lagoon_edge[window] & mask):
            reasons.append('registered-lagoon-rim')
        if np.any(special_volcanic[window] & mask):
            reasons.append('special-volcanic-morphology')
        if area <= config.min_area_km2:
            reasons.append('area-not-strictly-above-threshold')
        inland = mask & (distance[window] >= config.coast_buffer_m)
        inner_labels, inner_count = nd.label(inland, STRUCTURE)
        inner_distance = np.maximum(_distance(inland, spacing)-margin, 0.)
        widths = nd.maximum(inner_distance, inner_labels, np.arange(1, inner_count+1))*2
        width = float(np.max(widths)) if inner_count else 0.
        if config.min_usable_width_m > 0 and width < config.min_usable_width_m:
            reasons.append('usable-interior-width-below-threshold')
        eligible_inner = np.flatnonzero(widths >= config.min_usable_width_m)+1
        accepted = not reasons
        if accepted:
            target = selected[window]
            # Optional width selects buffered interiors explicitly. The default
            # area-only rule always records the whole exposed component, even
            # when a coast-buffer parameter would leave no blending interior.
            selected_mask = np.isin(inner_labels, eligible_inner) if config.min_usable_width_m > 0 else mask
            target[selected_mask] = component
        first_z, first_x = np.argwhere(mask)[0]
        source_bounds = product.source.bounds_m
        global_cell = [zz.start+int(first_z)+round((bounds[1]-source_bounds[1])/spacing),
                       xx.start+int(first_x)+round((bounds[0]-source_bounds[0])/spacing)]
        island_key = identity(['fixed-island-component-v3', product.identity, global_cell])
        records.append(dict(component_id=component, island_key=island_key, first_source_cell_zx=global_cell,
            peak_height_target_m=peak_height_for_area(area, config.peak_min_m, config.peak_max_m,
                product.config.world_seed, island_key, saturation_area_km2=config.peak_saturation_area_km2,
                threshold_area_km2=100., ripple_fraction=config.peak_ripple_fraction),
            exposed_area_km2=area,
            usable_interior_max_inscribed_diameter_m=width, interior_components=inner_count,
            accepted=accepted, exclusion_reasons=reasons,
            cell_bounds_zx=[zz.start, xx.start, zz.stop, xx.stop],
            bounds_m=[float(xe[xx.start]), float(ze[zz.start]), float(xe[xx.stop]), float(ze[zz.stop])]))
    selected = np.ascontiguousarray(selected)
    distance = np.ascontiguousarray(distance, dtype=np.float32)
    interior_distance = np.ascontiguousarray(np.maximum(_distance(selected > 0, spacing)-margin, 0.), dtype=np.float32)
    manifest = dict(schema=SCHEMA, algorithm=ALGORITHM, blend_policy=POLICY,
        peak_normalization_required=True,
        height_policy='Whole-component native30m raw min/max, then one component scale for protected-coast effective absolute peak; incomplete coverage pending',
        product_identity=product.identity, source_identity=product.source.identity,
        world_seed=product.config.world_seed, config=asdict(config),
        grid=dict(bounds_m=list(bounds), shape_zx=[nz, nx], spacing_m=spacing,
                  origin_xz_m=[bounds[0], bounds[1]], source_bounds_m=list(product.source.bounds_m),
                  source_origin_xz_m=list(product.source.bounds_m[:2]),
                  semantics='source-origin aligned cell centres; final source partial cell centre'),
        components=records, selected_components=[r['component_id'] for r in records if r['accepted']],
        qualification=dict(area_rule='exposed_area_km2 > min_area_km2',
            width_filter_enabled=config.min_usable_width_m > 0,
            coast_buffer_role='Blend protection only; does not disqualify an area-qualified component when width filter is disabled'),
        arrays=dict(selected_interior=_summary(selected), coast_distance_m=_summary(distance),
                    interior_distance_m=_summary(interior_distance)),
        approximation=dict(connectivity='4-neighbour fixed-grid actual exposed land',
            edge_margin_m=margin, width='Maximum inscribed circle in a connected coast-buffered interior; not exact island short axis',
            coast_protection='Smooth distance ramps times positive-height smoothstep from zero to coastal_height_ramp_m; actual sea/lagoon/original land forced zero',
            limits='Raster cell-centre area estimate, no exact-area or conservative-area guarantee near the configured threshold. Subgrid channels/bridges may be missed. Boundary/original-land/registered-lagoon-rim components excluded; no feature underwater-radius qualification.'))
    manifest['identity'] = identity(manifest)
    selected.flags.writeable = False
    distance.flags.writeable = False
    return IslandMountainPlan(manifest, selected, distance, interior_distance)


def _validate(plan, product=None):
    m = plan.manifest
    if m.get('identity') != identity({k:v for k,v in m.items() if k != 'identity'}):
        raise ValueError('mountain plan identity mismatch')
    if (m.get('algorithm'), m.get('blend_policy'), m.get('schema')) not in VERSIONS:
        raise ValueError('unsupported mountain plan algorithm/policy')
    if product is not None and (m['product_identity'] != product.identity or m['source_identity'] != product.source.identity):
        raise ValueError('mountain plan belongs to another island/source')
    config = IslandMountainConfig(**m['config']) if m['algorithm'] == ALGORITHM else IslandMountainConfig(
        **m['config'], **({} if 'peak_saturation_area_km2' in m['config'] else
                         {'peak_saturation_area_km2':max(2000.,m['config']['min_area_km2']*2)}))
    bounds = m['grid']['bounds_m']
    shape = m['grid']['shape_zx']
    if (len(shape) != 2 or any(type(v) is not int or v < 1 for v in shape)
            or math.prod(shape) > config.max_analysis_cells
            or len(bounds) != 4 or not all(math.isfinite(v) for v in bounds)
            or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]
            or m['grid']['spacing_m'] != config.analysis_spacing_m):
        raise ValueError('invalid mountain plan grid')
    expected_shape = [math.ceil((bounds[3]-bounds[1])/config.analysis_spacing_m),
                      math.ceil((bounds[2]-bounds[0])/config.analysis_spacing_m)]
    if shape != expected_shape or m['grid']['origin_xz_m'] != bounds[:2]:
        raise ValueError('mountain plan shape/origin does not match fixed window')
    if m['algorithm'] in (AREA_ALGORITHM, ALGORITHM):
        source_bounds = m['grid']['source_bounds_m']
        _fixed_bounds(source_bounds, bounds, config.analysis_spacing_m)
        if (m['grid']['source_origin_xz_m'] != source_bounds[:2]
                or (config.analysis_bounds_m is None and bounds != source_bounds)
                or (config.analysis_bounds_m is not None and list(config.analysis_bounds_m) != bounds)):
            raise ValueError('mountain plan fixed-window contract mismatch')
        if product is not None and (list(product.source.bounds_m) != source_bounds
                or list(_analysis_bounds(product, config)) != bounds):
            raise ValueError('mountain plan source/window bounds mismatch')
    elif product is not None and list(product.source.bounds_m) != bounds:
        raise ValueError('legacy mountain plan source bounds mismatch')
    for name in ('selected_interior', 'coast_distance_m', 'interior_distance_m'):
        a = getattr(plan, name)
        if _summary(a) != m['arrays'][name] or list(a.shape) != m['grid']['shape_zx'] or not np.isfinite(a).all():
            raise ValueError('mountain plan array integrity: ' + name)
    if (plan.selected_interior.dtype != np.dtype('int32')
            or plan.coast_distance_m.dtype != np.dtype('float32')
            or plan.interior_distance_m.dtype != np.dtype('float32')
            or not np.isin(plan.selected_interior, [0]+m['selected_components']).all()
            or (plan.coast_distance_m < 0).any() or (plan.interior_distance_m < 0).any()):
        raise ValueError('invalid mountain plan array values')


def save_mountain_plan(plan, path):
    _validate(plan)
    if plan.manifest['algorithm'] != ALGORITHM:
        raise ValueError('legacy mountain plan is read-only; prepare a new current plan')
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(handle, 'wb') as stream:
            np.savez_compressed(stream, manifest_json=np.array(canonical_json(plan.manifest)),
                selected_interior=plan.selected_interior, coast_distance_m=plan.coast_distance_m,
                interior_distance_m=plan.interior_distance_m)
        # Exclusive destination creation preserves a concurrently published plan.
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_mountain_plan(path, expected_identity, product):
    import zipfile
    with zipfile.ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist()) > 256*2**20:
            raise ValueError('mountain plan exceeds archive budget')
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != {'manifest_json', 'selected_interior', 'coast_distance_m', 'interior_distance_m'}:
            raise ValueError('mountain plan inventory mismatch')
        plan = IslandMountainPlan(json.loads(str(archive['manifest_json'])),
            archive['selected_interior'], archive['coast_distance_m'], archive['interior_distance_m'])
    _validate(plan, product)
    if not expected_identity or plan.identity != expected_identity:
        raise ValueError('unexpected mountain plan identity')
    plan.selected_interior.flags.writeable = False
    plan.coast_distance_m.flags.writeable = False
    return plan


def _sample_mountain_fields(plan, product, x_m, z_m):
    """Sample a frozen plan under its recorded policy; never requalify a window."""
    manifest = plan.manifest
    if manifest['product_identity'] != product.identity:
        raise ValueError('mountain plan belongs to another island product')
    if (manifest['algorithm'], manifest['blend_policy'], manifest['schema']) not in VERSIONS:
        raise ValueError('unsupported mountain plan algorithm/policy')
    x, z = np.broadcast_arrays(np.asarray(x_m, float), np.asarray(z_m, float))
    bounds = manifest['grid']['bounds_m']
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError('nonfinite mountain coordinates')
    inside = (x >= bounds[0]) & (x < bounds[2]) & (z >= bounds[1]) & (z < bounds[3])
    weights = np.zeros(x.shape, float)
    components = np.zeros(x.shape, np.int32)
    if plan.empty or not inside.any():
        return weights, components
    spacing = manifest['grid']['spacing_m']
    nx, nz = plan.selected_interior.shape[1], plan.selected_interior.shape[0]
    if manifest['algorithm'] in (AREA_ALGORITHM, ALGORITHM):
        # Derive fractions from the source grid even for a local plan, so
        # identical coordinates do not acquire window-dependent roundoff.
        source_bounds = manifest['grid']['source_bounds_m']
        gx = (x[inside]-source_bounds[0])/spacing-.5
        gz = (z[inside]-source_bounds[1])/spacing-.5
        gx = np.clip(gx-round((bounds[0]-source_bounds[0])/spacing), 0, nx-1)
        gz = np.clip(gz-round((bounds[1]-source_bounds[1])/spacing), 0, nz-1)
    else:
        gx = np.clip((x[inside]-bounds[0])/spacing-.5, 0, nx-1)
        gz = np.clip((z[inside]-bounds[1])/spacing-.5, 0, nz-1)
    ix, iz = np.floor(gx).astype(int), np.floor(gz).astype(int)
    jx, jz = np.minimum(ix+1, nx-1), np.minimum(iz+1, nz-1)
    corner_ids = np.array([plan.selected_interior[iz,ix], plan.selected_interior[iz,jx],
                           plan.selected_interior[jz,ix], plan.selected_interior[jz,jx]])
    distance = np.array([plan.coast_distance_m[iz,ix], plan.coast_distance_m[iz,jx],
                         plan.coast_distance_m[jz,ix], plan.coast_distance_m[jz,jx]])
    interior = np.array([plan.interior_distance_m[iz,ix], plan.interior_distance_m[iz,jx],
                         plan.interior_distance_m[jz,ix], plan.interior_distance_m[jz,jx]])
    cfg = manifest['config']
    t = np.clip((distance-cfg['coast_buffer_m'])/cfg['blend_ramp_m'], 0, 1)
    inner_t = np.clip(interior/cfg['blend_ramp_m'], 0, 1)
    nodal = np.where(corner_ids > 0, t*t*(3-2*t)*inner_t*inner_t*(3-2*inner_t), 0.)
    fx, fz = gx-ix, gz-iz
    interpolated = ((1-fz)*((1-fx)*nodal[0]+fx*nodal[1])
                    + fz*((1-fx)*nodal[2]+fx*nodal[3]))
    q = product.query(x[inside], z[inside])
    allowed = (q['elevation_m'] >= 0) & ~q['lagoon'] & (q['base_elevation_m'] < 0)
    allowed &= np.asarray(q.get('volcano_weight', 0)) <= 0
    if manifest['algorithm'] in (AREA_ALGORITHM, ALGORITHM):
        coastal_t = np.clip(q['elevation_m']/cfg['coastal_height_ramp_m'], 0., 1.)
        interpolated *= coastal_t*coastal_t*(3-2*coastal_t)
    weights[inside] = np.where(allowed, interpolated, 0.)
    contribution = nodal*np.array([(1-fx)*(1-fz),fx*(1-fz),(1-fx)*fz,fx*fz])
    best = np.argmax(contribution, axis=0)
    fallback = np.argmax(corner_ids > 0, axis=0)
    best = np.where(np.max(contribution,axis=0)>0,best,fallback)
    ids = corner_ids[best, np.arange(corner_ids.shape[1])]
    components[inside] = np.where(allowed,ids,0)
    return weights, components


def sample_mountain_weights(plan, product, x_m, z_m):
    return _sample_mountain_fields(plan,product,x_m,z_m)[0]


def sample_mountain_components(plan, product, x_m, z_m):
    """Stable frozen component ownership for normalization consumers."""
    return _sample_mountain_fields(plan,product,x_m,z_m)[1]


def blend_mountain_surface(plan, product, x_m, z_m, decoded):
    """Keep analytic frozen base at weight zero; raw decoded input is untouched."""
    if plan.manifest.get('peak_normalization_required'):
        raise ValueError('peak-normalized plan requires complete-component normalization and apply_peak_surface')
    base = product.query(x_m, z_m)['elevation_m']
    decoded = np.broadcast_to(np.asarray(decoded, float), base.shape)
    if not np.isfinite(decoded).all():
        raise ValueError('nonfinite decoded mountain surface')
    weight = sample_mountain_weights(plan, product, x_m, z_m)
    target = np.maximum(decoded, plan.manifest['config']['land_floor_m'])
    return (base+weight*(target-base)).astype(np.float32), weight


def component_native_tiles(plan, component_id, *, tile_native=512, native_m=30):
    """Closed native tiles covering a fixed component and its interpolation halo.

    Bounding boxes deliberately overestimate coverage; requests cannot change
    which raw samples are required for the same component's peak statistics.
    """
    row = next((r for r in plan.manifest['components']
                if r['component_id'] == component_id and r['accepted']), None)
    if row is None:
        raise ValueError('unknown selected island component')
    span = tile_native*native_m
    halo = plan.manifest['grid']['spacing_m']
    x0, z0, x1, z1 = row['bounds_m']
    return [(ix, iz) for iz in range(math.floor((z0-halo)/span), math.floor((z1+halo)/span)+1)
            for ix in range(math.floor((x0-halo)/span), math.floor((x1+halo)/span)+1)]


def _native_fields(plan, product, ix, iz, raw):
    if np.asarray(raw).shape != (513, 513) or not np.isfinite(raw).all():
        raise ValueError('peak normalization requires finite native513 raw tiles')
    x = (ix*512+np.arange(513)[None, :])*30.
    z = (iz*512+np.arange(513)[:, None])*30.
    weight, components = _sample_mountain_fields(plan, product, x, z)
    base = product.query(x, z)['elevation_m']
    return base, weight, components


class PeakNormalizationBuilder:
    """Bounded two-pass statistics; never retains a tile or modifies raw TD.

    Every ready island uses the same raw range and scale in every tile. The
    caller binds immutable raw manifests; both passes verify elevation hashes.
    """

    def __init__(self, plan, product, raw_records):
        _validate(plan, product)
        if not plan.manifest.get('peak_normalization_required'):
            raise ValueError('peak normalization requires a current peak plan')
        self.plan, self.product = plan, product
        self.records = {}
        for record in raw_records:
            key = (record['ix'], record['iz'])
            if any(type(v) is not int for v in key) or key in self.records:
                raise ValueError('invalid or duplicate raw tile')
            if any(not isinstance(record.get(k), str) or len(record[k]) != 64
                   for k in ('identity', 'elevation_sha256')):
                raise ValueError('raw identity and elevation SHA required')
            self.records[key] = dict(record)
        self.raw_seen, self.scale_seen = set(), set()
        self.stats = {}
        for row in plan.manifest['components']:
            if row['accepted']:
                self.stats[row['component_id']] = dict(row=row,
                    required=set(component_native_tiles(plan, row['component_id'])),
                    raw_min=math.inf, raw_max=-math.inf, protected_floor=-math.inf,
                    scale=math.inf, sample_count=0)

    def _verify(self, ix, iz, raw, seen):
        key = (ix, iz)
        if key not in self.records or key in seen:
            raise ValueError('unregistered or repeated normalization tile')
        array = np.asarray(raw)
        expected = self.records[key].get('array_sha256', self.records[key]['elevation_sha256'])
        if hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest() != expected:
            raise ValueError('raw elevation changed during peak normalization')
        fields = _native_fields(self.plan, self.product, ix, iz, array)
        seen.add(key)
        return array, fields

    def observe_raw(self, ix, iz, raw):
        raw, (base, w, ids) = self._verify(ix, iz, raw, self.raw_seen)
        floor = self.plan.manifest['config']['land_floor_m']
        for cid in np.unique(ids):
            if cid not in self.stats:
                continue
            stat = self.stats[cid]
            mask = ids == cid
            stat['protected_floor'] = max(stat['protected_floor'], float(np.max((base*(1-w)+w*floor)[mask])))
            active = mask & (w > 0)
            if active.any():
                stat['raw_min'] = min(stat['raw_min'], float(raw[active].min()))
                stat['raw_max'] = max(stat['raw_max'], float(raw[active].max()))
                stat['sample_count'] += int(active.sum())

    def observe_scale(self, ix, iz, raw):
        if self.raw_seen != set(self.records):
            raise ValueError('raw observation pass is incomplete')
        raw, (base, w, ids) = self._verify(ix, iz, raw, self.scale_seen)
        cfg = self.plan.manifest['config']
        upper = cfg['peak_max_m']*(1+cfg['peak_ripple_fraction'])
        a = base*(1-w)+w*cfg['land_floor_m']
        for cid in np.unique(ids):
            if cid not in self.stats:
                continue
            stat = self.stats[cid]
            if not stat['required'] <= self.raw_seen or not stat['sample_count']:
                continue
            effective = max(stat['row']['peak_height_target_m'], stat['protected_floor']+1e-5)
            if effective > upper:
                continue
            span = stat['raw_max']-stat['raw_min']
            u = np.clip((raw-stat['raw_min'])/span, 0., 1.) if span > 1e-12 else np.ones(raw.shape)
            b = w*u
            active = (ids == cid) & (b > 1e-12)
            if active.any():
                stat['scale'] = min(stat['scale'], float(np.min((effective-a[active])/b[active])))

    def finalize(self):
        if self.raw_seen != set(self.records) or self.scale_seen != set(self.records):
            raise ValueError('both peak normalization observation passes must finish')
        cfg = self.plan.manifest['config']
        upper = cfg['peak_max_m']*(1+cfg['peak_ripple_fraction'])
        rows = []
        for cid, stat in sorted(self.stats.items()):
            requested = stat['row']['peak_height_target_m']
            row = dict(component_id=cid, island_key=stat['row']['island_key'],
                requested_peak_m=requested, required_tiles=[list(k) for k in sorted(stat['required'])],
                missing_tiles=[list(k) for k in sorted(stat['required']-self.raw_seen)])
            if row['missing_tiles']:
                row.update(status='pending', reason='incomplete whole-island raw coverage')
            elif not stat['sample_count']:
                row.update(status='rejected', reason='no positive mountain weights at native samples')
            else:
                effective = max(requested, stat['protected_floor']+1e-5)
                row.update(effective_peak_m=effective, protected_floor_m=stat['protected_floor'],
                    coast_constraint_applied=effective > requested, raw_min_m=stat['raw_min'],
                    raw_max_m=stat['raw_max'], constant_raw=stat['raw_max']-stat['raw_min'] <= 1e-12)
                if effective > upper:
                    row.update(status='rejected', reason='protected coast exceeds configured peak ceiling')
                elif not math.isfinite(stat['scale']) or stat['scale'] < 0:
                    row.update(status='rejected', reason='no finite nonnegative whole-island scale')
                else:
                    row.update(status='ready', scale=stat['scale'])
            rows.append(row)
        record = dict(schema='island-peak-normalization-v3', plan_identity=self.plan.identity,
            product_identity=self.product.identity, blend_policy=POLICY, components=rows,
            raw_tiles=[self.records[k] for k in sorted(self.records)],
            lattice=dict(native_m=30, tile_native=512, tile_samples=513),
            peak_scope='Maximum at the complete component native30m samples, not a continuous extrema guarantee')
        record['identity'] = identity(record)
        return record


def validate_peak_normalization(plan, product, normalization):
    if (normalization.get('schema') != 'island-peak-normalization-v3'
            or normalization.get('identity') != identity({k:v for k,v in normalization.items() if k != 'identity'})
            or normalization.get('plan_identity') != plan.identity
            or normalization.get('product_identity') != product.identity
            or normalization.get('blend_policy') != plan.manifest['blend_policy']):
        raise ValueError('peak normalization identity/plan/policy mismatch')


def apply_peak_surface(plan, product, normalization, x_m, z_m, decoded):
    """Apply common frozen per-island scales; pending islands retain their base."""
    validate_peak_normalization(plan, product, normalization)
    base = product.query(x_m, z_m)['elevation_m']
    raw = np.broadcast_to(np.asarray(decoded, float), base.shape)
    if not np.isfinite(raw).all():
        raise ValueError('nonfinite decoded mountain surface')
    w, ids = _sample_mountain_fields(plan, product, x_m, z_m)
    height = np.array(base, dtype=float, copy=True)
    applied = np.zeros(w.shape)
    floor = plan.manifest['config']['land_floor_m']
    for row in normalization['components']:
        if row['status'] != 'ready':
            continue
        mask = (ids == row['component_id']) & (w > 0)
        span = row['raw_max_m']-row['raw_min_m']
        u = np.clip((raw[mask]-row['raw_min_m'])/span, 0., 1.) if span > 1e-12 else np.ones(int(mask.sum()))
        height[mask] = base[mask]*(1-w[mask])+w[mask]*floor+row['scale']*w[mask]*u
        applied[mask] = w[mask]
    return height.astype(np.float32), applied
