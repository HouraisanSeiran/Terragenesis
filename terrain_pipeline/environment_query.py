"""Consolidated environment_query implementations; numeric expressions preserved."""
from __future__ import annotations
import hashlib as _i50_hashlib
import importlib as _i50_importlib
import os as _i50_os
import time as _i50_time
from dataclasses import asdict as _i50_asdict
import numpy as _i50_np
CATEGORY = 'D'
SCHEMA = 'metric-environment-query-v1'
GRID_SPACING_M = 30.0
MAX_POINTS = 8192
MAX_MATERIAL_CELLS = 262144
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_SECONDS = 60.0
AVAILABLE_WATER_SEMANTICS = 'relative_proxy_not_dynamic_et'
POLICIES = ('pending', 'coarse_condition', 'require_dem')
GRID_ALIGN_ATOL = 1e-06
MATERIAL_PURPOSE = 'geography-stage2-material'
SOIL_PURPOSE = 'geography-stage2-soil'
DECLARED_UNCALIBRATED = 'soil drainage thresholds, available_water span and the material/lithology attribute values are declared engineering assumptions, not calibrated measurements; the 10000 m SoilParameters default is not used by this path'
UNITS = {'x_m': 'm', 'z_m': 'm', 'elevation_m': 'm', 'monthly_temperature_c': 'degC_monthly_mean', 'monthly_precipitation_mm': 'mm_per_month', 'BIO1_c': 'degC_annual_mean', 'BIO12_mm': 'mm_per_year', 'precipitation_multiplier': '1', 'material_erodible_thickness_m': 'm', 'material_erodibility': '1', 'lithology_bed_hardness': '1', 'soil_depth_m': 'm', 'drainage': 'ordinal_0_fast_to_3_waterlogged', 'available_water': '1_relative_proxy'}
NOT_AVAILABLE = 'not_available'
SUPPORTED_SOURCE_KEYS = ('dem',)
_DEPENDENCY_MODULES = ('terrain_pipeline.climate_forcing', 'terrain_pipeline.soil_water', 'terrain_pipeline.geology', 'terrain_pipeline.hydrology_planning')

def _code_identities():
    """返回本层依赖核的模块身份（源文件字节 sha256）。用于组合 identity。

    这是“同参数但改了核就不应同 identity”的可核手段；不是签名/防篡改。
    """
    record = {}
    for name in _DEPENDENCY_MODULES:
        module = _i50_importlib.import_module(name)
        path = getattr(module, '__file__', None)
        if not path or not _i50_os.path.exists(path):
            raise ValueError('cannot locate source file for %s' % name)
        with open(path, 'rb') as handle:
            digest = _i50_hashlib.sha256(handle.read()).hexdigest()
        record[name] = {'source_sha256': digest, 'basename': _i50_os.path.basename(path)}
    return record

def _validate_seed(seed):
    if isinstance(seed, bool) or not isinstance(seed, (int, _i50_np.integer)):
        raise ValueError('seed must be a non-boolean integer')
    value = int(seed)
    if not 0 <= value < 2 ** 64:
        raise ValueError('seed must satisfy 0 <= seed < 2**64')
    return value

def _broadcast_points(x_m, z_m):
    x = _i50_np.asarray(x_m, _i50_np.float64)
    z = _i50_np.asarray(z_m, _i50_np.float64)
    try:
        x, z = _i50_np.broadcast_arrays(x, z)
    except ValueError:
        raise ValueError('x_m and z_m must broadcast to a common shape')
    if x.size < 1 or x.size > MAX_POINTS:
        raise ValueError('point count %d outside 1..%d' % (x.size, MAX_POINTS))
    if not _i50_np.isfinite(x).all() or not _i50_np.isfinite(z).all():
        raise ValueError('finite absolute world coordinates required')
    if max(float(_i50_np.abs(x).max()), float(_i50_np.abs(z).max())) > 1000000000000.0:
        raise ValueError('bounded absolute meter coordinates required')
    return (x, z)

def _require_grid_aligned(values, name):
    """要求落在 30 m 格参考点上；**不吸附、不取整、不插值**，不对齐就拒。"""
    quotient = values / GRID_SPACING_M
    if not _i50_np.allclose(quotient, _i50_np.rint(quotient), rtol=0.0, atol=1e-08):
        raise ValueError('%s must be an integer multiple of %.1f m (30 m grid reference points); this entry point never snaps or interpolates' % (name, GRID_SPACING_M))

def _resolve_soil_parameters(soil_parameters):
    """固定 30 m 坡度采样；显式给 10000 m 默认值就拒，不静默改写。"""
    from terrain_pipeline.soil_water import SoilParameters as _x101_SoilParameters
    if soil_parameters is None:
        return _x101_SoilParameters(slope_spacing_m=GRID_SPACING_M)
    if not isinstance(soil_parameters, _x101_SoilParameters):
        raise ValueError('soil_parameters must be a SoilParameters instance or None')
    if float(soil_parameters.slope_spacing_m) != GRID_SPACING_M:
        raise ValueError('this path is 30 m only: slope_spacing_m must be %.1f, got %r (the 10000 m default is not inherited and no 10 km compatibility mode exists)' % (GRID_SPACING_M, soil_parameters.slope_spacing_m))
    return soil_parameters

def _dem_contract(source_identities, elevation_sampler):
    """解析并校验 DEM 来源声明；缺声明就拒（不接受“只记函数名”）。

    同时拒未知声明键：声明了却不参与身份，等于让产物假装已绑定。
    """
    if not isinstance(source_identities, dict):
        raise ValueError('source_identities dict is required')
    unknown = sorted(set(source_identities) - set(SUPPORTED_SOURCE_KEYS))
    if unknown:
        raise ValueError('unsupported source_identities keys %r: this entry point only binds %r into the combined identity, and silently ignoring a declaration would make the product look bound when it is not' % (unknown, list(SUPPORTED_SOURCE_KEYS)))
    dem = source_identities.get('dem', None)
    if elevation_sampler is None:
        if dem is not None:
            raise ValueError('a DEM identity was declared without an elevation_sampler')
        return None
    if dem is None:
        raise ValueError("elevation_sampler is supplied but source_identities['dem'] is missing; a DEM must declare identity_sha256, origin_m_xz, spacing_m and shape_zx")
    if not isinstance(dem, dict):
        raise ValueError("source_identities['dem'] must be a dict")
    required = ('identity_sha256', 'origin_m_xz', 'spacing_m', 'shape_zx')
    missing = [key for key in required if key not in dem]
    if missing:
        raise ValueError('DEM source identity missing %r' % (missing,))
    digest = dem['identity_sha256']
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError('DEM identity_sha256 must be a 64-character hex digest')
    try:
        int(digest, 16)
    except ValueError:
        raise ValueError('DEM identity_sha256 must be hexadecimal')
    origin = _i50_np.asarray(dem['origin_m_xz'], _i50_np.float64)
    if origin.shape != (2,) or not _i50_np.isfinite(origin).all():
        raise ValueError('DEM origin_m_xz must be two finite coordinates')
    if float(dem['spacing_m']) != GRID_SPACING_M:
        raise ValueError('DEM spacing_m must be %.1f' % GRID_SPACING_M)
    shape = tuple((int(v) for v in dem['shape_zx']))
    if len(shape) != 2 or min(shape) < 1:
        raise ValueError('DEM shape_zx must be two positive integers')
    return {'identity_sha256': digest.lower(), 'origin_m_xz': [float(origin[0]), float(origin[1])], 'spacing_m': GRID_SPACING_M, 'shape_zx': [shape[0], shape[1]]}

def _dem_lookup(dem, x, z):
    """DEM 精确格心查表。域外或非格点不可用；**不吸附、不填 0**。

    “是否落在格心”必须**用未取整的原列/行算**：先 `rint` 再与自己的 `int` 相减
    那个差恒为 0，会让 off-grid 请求被误判为对齐。这里对原始商做容差比较。

    返回 `(height, inside, row_index, col_index)`，四个元素形状一致；
    `dem is None` 时 inside 全为 False（调用方据此判定“无 DEM”）。
    """
    arr_x = _i50_np.asarray(x, _i50_np.float64)
    arr_z = _i50_np.asarray(z, _i50_np.float64)
    height = _i50_np.full(arr_x.shape, _i50_np.nan, _i50_np.float64)
    zero_i = _i50_np.zeros(arr_x.shape, _i50_np.int64)
    if dem is None:
        return (height, _i50_np.zeros(arr_x.shape, bool), zero_i, zero_i)
    origin_x, origin_z = dem['origin_m_xz']
    rows, cols = dem['shape_zx']
    raw_col = (arr_x - origin_x) / GRID_SPACING_M
    raw_row = (arr_z - origin_z) / GRID_SPACING_M
    col_i = _i50_np.rint(raw_col).astype(_i50_np.int64)
    row_i = _i50_np.rint(raw_row).astype(_i50_np.int64)
    exact = (_i50_np.abs(raw_col - col_i) <= GRID_ALIGN_ATOL) & (_i50_np.abs(raw_row - row_i) <= GRID_ALIGN_ATOL)
    inside = exact & (col_i >= 0) & (col_i < cols) & (row_i >= 0) & (row_i < rows)
    return (height, inside, row_i, col_i)

def _measure_orographic_request(seed, flat_x, flat_z, parameters, elevation_values, counter):
    """用记录型 sampler 求一遍 v2，同时拿到真实请求包络与**这一遍的气候结果**。

    请求坐标只由 (seed, 查询点, 参数) 决定，与 sampler 返回什么值无关。所以这一遍用
    粗条件场既能把包络测准，又能直接当作背景估计结果复用——避免同一请求重复跑 v2。

    返回 `(climate, requested_x, requested_z)`。
    """
    from terrain_pipeline.hydrology_planning import coarse_condition_field as _i50_coarse_condition_field
    from terrain_pipeline.climate_forcing import sample_climate_v2 as _x98_sample_climate_v2
    requested_x = []
    requested_z = []

    def recorder(x_m, z_m):
        ax = _i50_np.asarray(x_m, _i50_np.float64).reshape(-1)
        az = _i50_np.asarray(z_m, _i50_np.float64).reshape(-1)
        requested_x.append(ax.copy())
        requested_z.append(az.copy())
        counter['coarse_condition_field'] += 1
        return _i50_np.asarray(_i50_coarse_condition_field(seed, x_m, z_m)[0], _i50_np.float64)
    climate = _x98_sample_climate_v2(seed, flat_x, flat_z, elevation_m=elevation_values, parameters=parameters, elevation_sampler=recorder)
    return (climate, _i50_np.concatenate(requested_x), _i50_np.concatenate(requested_z))

def _coverage_report(requested_x, requested_z, dem):
    """把实测请求包络和 DEM 实际可供给范围对比。"""
    origin_x, origin_z = dem['origin_m_xz']
    rows, cols = dem['shape_zx']
    col = (requested_x - origin_x) / GRID_SPACING_M
    row = (requested_z - origin_z) / GRID_SPACING_M
    col_i = _i50_np.rint(col).astype(_i50_np.int64)
    row_i = _i50_np.rint(row).astype(_i50_np.int64)
    exact = (_i50_np.abs(col - col_i) < 1e-09) & (_i50_np.abs(row - row_i) < 1e-09)
    inside = exact & (col_i >= 0) & (col_i < cols) & (row_i >= 0) & (row_i < rows)
    covered = int(inside.sum())
    total = int(inside.size)
    missing_x = int((~inside).sum())
    return {'requested_coordinates_total': total, 'requested_coordinates_covered': covered, 'requested_coordinates_missing': missing_x, 'dem_covered_all': bool(missing_x == 0), 'requested_envelope_m': {'x_min': float(requested_x.min()), 'x_max': float(requested_x.max()), 'z_min': float(requested_z.min()), 'z_max': float(requested_z.max())}, 'dem_extent_m': {'x_min': float(origin_x), 'x_max': float(origin_x + (cols - 1) * GRID_SPACING_M), 'z_min': float(origin_z), 'z_max': float(origin_z + (rows - 1) * GRID_SPACING_M)}, 'dem_shape_zx': [rows, cols], 'coverage_method': 'instrumented sampler: every requested world coordinate is recorded'}

def preflight(n_points, bbox_cells):
    """分配前算清上限；不靠分配后才发现。"""
    if isinstance(n_points, bool) or not isinstance(n_points, int):
        raise ValueError('n_points must be an int')
    if not 1 <= n_points <= MAX_POINTS:
        raise ValueError('point count %d outside 1..%d' % (n_points, MAX_POINTS))
    if isinstance(bbox_cells, bool) or not isinstance(bbox_cells, int):
        raise ValueError('bbox_cells must be an int')
    if not 1 <= bbox_cells <= MAX_MATERIAL_CELLS:
        raise ValueError('material bbox %d cells exceeds %d; this entry point evaluates the material field on one padded rectangle, so scattered points with a large bounding box are refused before allocation' % (bbox_cells, MAX_MATERIAL_CELLS))
    estimated = int(8 * (15 * n_points + 4 * bbox_cells + 8 * n_points + 5 * n_points))
    if estimated > MAX_OUTPUT_BYTES:
        raise ValueError('estimated logical payload %d bytes exceeds %d' % (estimated, MAX_OUTPUT_BYTES))
    return {'n_points': n_points, 'bbox_cells': bbox_cells, 'estimated_logical_payload_bytes': estimated, 'max_points': MAX_POINTS, 'max_material_cells': MAX_MATERIAL_CELLS, 'max_output_bytes': MAX_OUTPUT_BYTES, 'max_seconds': MAX_SECONDS}

def _points_digest(flat_x, flat_z):
    """与顺序、形状、分窗无关的点集摘要（排序后取字节）。"""
    order = _i50_np.lexsort((flat_z, flat_x))
    canonical = _i50_np.stack((flat_x[order], flat_z[order]), axis=1)
    return _i50_hashlib.sha256(_i50_np.ascontiguousarray(canonical).tobytes()).hexdigest()

def _ordinal_digest(flat_x, flat_z, ordinal):
    """把「哪个坐标拿到哪个 ordinal」绑进身份，并保持置换不变。

    仅记 `supplied: true` 是不够的：ordinal 值一变 palette 就变，但组合身份不变。
    这里用与 `points_digest` **同一**排序规范，把 (x, z, ordinal) 三者一起摘要，
    于是同点集不同 ordinal ⇒ 身份变；同点集换顺序 ⇒ 身份不变。
    """
    order = _i50_np.lexsort((flat_z, flat_x))
    canonical = _i50_np.stack((flat_x[order], flat_z[order], _i50_np.asarray(ordinal, _i50_np.float64)[order]), axis=1)
    return _i50_hashlib.sha256(_i50_np.ascontiguousarray(canonical).tobytes()).hexdigest()

def sample_environment(seed, x_m, z_m, *, elevation_sampler=None, material_seed=None, soil_parameters=None, source_identities=None, orographic_policy='pending', climate_parameters=None, landform_ordinal=None):
    """在同一批绝对世界坐标上返回环境联合字段，逐字段带 source/status/units。

    参数
    ----
    seed : int
        世界种子；用途子种子由它确定性派生（见返回 `identity.sub_seeds`）。
    x_m, z_m : array_like
        绝对世界坐标米，**必须是 30 m 格参考点**；广播到同一形状。
    elevation_sampler : callable or None
        ``(x_m, z_m) -> height_m``。真实 DEM 就传它，并在 `source_identities['dem']`
        里申报身份与有效范围。``None`` 表示只有粗条件场。
    material_seed, soil_parameters : 可选
        材料用途子种子 / 土壤参数（必须显式 30 m）。
    source_identities : dict
        来源申报。有 DEM 时必须含 ``'dem'``。
    orographic_policy : {'pending','coarse_condition','require_dem'}
        见模块说明。
    climate_parameters, landform_ordinal : 可选
        气候参数对象 / 非高度场地貌序数（不传则 palette 为 not_available）。

    返回
    ----
    dict
        字段值 + 逐字段 `sources`/`status`/`units` + `identity` + `cost`/`cache`。
    """
    from terrain_pipeline.hydrology_planning import coarse_condition_field as _i50_coarse_condition_field
    from terrain_pipeline.surface_rivers.world_channel_graph import derive_noise_seed as _i50_derive_noise_seed
    from terrain_pipeline.common_infra import identity as _i50_identity
    from terrain_pipeline.soil_water import SOIL_ALGORITHM as _x100_SOIL_ALGORITHM
    from terrain_pipeline.soil_water import soil_condition as _x103_soil_condition
    from terrain_pipeline.geology import CLASS_IDS as _x104_CLASS_IDS
    from terrain_pipeline.geology import ROCK_ORDER as _x105_ROCK_ORDER
    from terrain_pipeline.geology import lithology_subseeds as _x106_lithology_subseeds
    from terrain_pipeline.geology import rock_table_identity as _x107_rock_table_identity
    from terrain_pipeline.geology import sample_lithology_points as _x108_sample_lithology_points
    from terrain_pipeline.geology import make_material_field as _x109_make_material_field
    from terrain_pipeline.climate_forcing import PRECIPITATION_SPAN_MM as _x87_PRECIPITATION_SPAN_MM
    from terrain_pipeline.climate_forcing import RAIN_DRY as _x88_RAIN_DRY
    from terrain_pipeline.climate_forcing import RAIN_WET as _x89_RAIN_WET
    from terrain_pipeline.climate_forcing import TEMPERATURE_LOW as _x90_TEMPERATURE_LOW
    from terrain_pipeline.climate_forcing import TEMPERATURE_OFFSET_C as _x91_TEMPERATURE_OFFSET_C
    from terrain_pipeline.climate_forcing import TEMPERATURE_SPAN_C as _x92_TEMPERATURE_SPAN_C
    from terrain_pipeline.climate_forcing import VARIANT_NAMES as _x93_VARIANT_NAMES
    from terrain_pipeline.climate_forcing import climate_coordinates as _x94_climate_coordinates
    from terrain_pipeline.climate_forcing import palette_index as _x95_palette_index
    from terrain_pipeline.climate_forcing import variant as _x96_variant
    from terrain_pipeline.climate_forcing import RefinedClimateParameters as _x97_RefinedClimateParameters
    from terrain_pipeline.climate_forcing import sample_climate_v2 as _x98_sample_climate_v2
    from terrain_pipeline.climate_forcing import NoiseClimateParameters as _x99_NoiseClimateParameters
    started = _i50_time.perf_counter()
    seed = _validate_seed(seed)
    if orographic_policy not in POLICIES:
        raise ValueError('orographic_policy must be one of %r' % (POLICIES,))
    parameters = climate_parameters or _x97_RefinedClimateParameters()
    if not isinstance(parameters, _x97_RefinedClimateParameters):
        raise ValueError('climate_parameters must be a RefinedClimateParameters instance')
    soil_params = _resolve_soil_parameters(soil_parameters)
    dem = _dem_contract(source_identities, elevation_sampler)
    x, z = _broadcast_points(x_m, z_m)
    _require_grid_aligned(x, 'x_m')
    _require_grid_aligned(z, 'z_m')
    shape = x.shape
    flat_x = _i50_np.ascontiguousarray(x.reshape(-1))
    flat_z = _i50_np.ascontiguousarray(z.reshape(-1))
    n = flat_x.size
    origin_x = float(flat_x.min())
    origin_z = float(flat_z.min())
    cols = int(round((float(flat_x.max()) - origin_x) / GRID_SPACING_M)) + 1
    rows = int(round((float(flat_z.max()) - origin_z) / GRID_SPACING_M)) + 1
    budget = preflight(n, rows * cols)
    if material_seed is None:
        material_seed_value = _i50_derive_noise_seed(seed, MATERIAL_PURPOSE)
        material_seed_source = 'derived'
    else:
        material_seed_value = _validate_seed(material_seed)
        material_seed_source = 'caller_supplied'
    soil_seed = _i50_derive_noise_seed(seed, SOIL_PURPOSE)
    counts = {'sample_climate_v2': 0, 'make_material_field': 0, 'sample_lithology_points': 0, 'soil_condition': 0, 'coarse_condition_field': 0}
    cache = {'bio12_exact_lookup_hits': 0, 'bio12_exact_lookup_misses': 0, 'thickness_exact_lookup_hits': 0, 'thickness_exact_lookup_misses': 0, 'climate_batch_passes': 0}

    def elapsed():
        return _i50_time.perf_counter() - started

    def check_time(stage):
        if elapsed() > MAX_SECONDS:
            raise ValueError('single computation exceeded %.0f s budget at stage %s' % (MAX_SECONDS, stage))
    if dem is None:
        elevation_dem = _i50_np.full(n, _i50_np.nan, _i50_np.float64)
        elevation_available = _i50_np.zeros(n, bool)
    else:
        _blank, inside, row_i, col_i = _dem_lookup(dem, flat_x, flat_z)
        sampled = _i50_np.asarray(elevation_sampler(flat_x, flat_z), _i50_np.float64)
        if sampled.shape != (n,):
            raise ValueError('elevation_sampler must return one value per query point')
        elevation_available = inside & _i50_np.isfinite(sampled)
        elevation_dem = _i50_np.where(elevation_available, sampled, _i50_np.nan)
    coarse_height = _i50_np.asarray(_i50_coarse_condition_field(seed, flat_x, flat_z)[0], _i50_np.float64)
    counts['coarse_condition_field'] += 1
    elevation_used = _i50_np.where(elevation_available, elevation_dem, coarse_height)

    def coarse_only_sampler(x_m, z_m):
        return _i50_np.asarray(_i50_coarse_condition_field(seed, x_m, z_m)[0], _i50_np.float64)
    orographic = {'policy': orographic_policy}
    use_dem_orographic = False
    measured_climate = None
    has_dem = not (elevation_sampler is None or dem is None)
    if orographic_policy == 'require_dem' and (not has_dem):
        raise ValueError("orographic_policy='require_dem' requires an elevation_sampler plus a declared source_identities['dem']; neither was supplied. This path refuses rather than silently returning a coarse-condition estimate.")
    if not has_dem:
        orographic.update({'status': 'declared_background_estimate_coarse', 'orographic_elevation_source': 'coarse_condition_field', 'precipitation_status': 'declared_background_estimate', 'note': 'no DEM sampler supplied: the whole climate estimate is the analytic coarse condition field, not terrain-driven orography'})
    elif orographic_policy == 'coarse_condition':
        measured_climate, requested_x, requested_z = _measure_orographic_request(seed, flat_x, flat_z, parameters, elevation_used, counts)
        counts['sample_climate_v2'] += 1
        cache['climate_batch_passes'] += 1
        coverage = _coverage_report(requested_x, requested_z, dem)
        orographic.update({'status': 'declared_background_estimate_coarse', 'orographic_elevation_source': 'coarse_condition_field', 'precipitation_status': 'declared_background_estimate', 'requested_envelope': coverage, 'note': "orographic_policy='coarse_condition' was chosen explicitly, so the coarse-condition estimate is returned even if the DEM could cover the envelope; the source is decided by policy and never switched silently."})
        check_time('orographic')
    else:
        measured_climate, requested_x, requested_z = _measure_orographic_request(seed, flat_x, flat_z, parameters, elevation_used, counts)
        counts['sample_climate_v2'] += 1
        cache['climate_batch_passes'] += 1
        coverage = _coverage_report(requested_x, requested_z, dem)
        orographic['requested_envelope'] = coverage
        if coverage['dem_covered_all']:
            use_dem_orographic = True
            orographic.update({'status': 'dem_verified', 'orographic_elevation_source': 'caller_dem', 'precipitation_status': 'dem_verified'})
        elif orographic_policy == 'require_dem':
            raise ValueError("orographic_policy='require_dem' but the DEM cannot cover the actual requested envelope: %d of %d requested coordinates are missing. Required envelope x %r..%r m, z %r..%r m; DEM extent x %r..%r m, z %r..%r m." % (coverage['requested_coordinates_missing'], coverage['requested_coordinates_total'], coverage['requested_envelope_m']['x_min'], coverage['requested_envelope_m']['x_max'], coverage['requested_envelope_m']['z_min'], coverage['requested_envelope_m']['z_max'], coverage['dem_extent_m']['x_min'], coverage['dem_extent_m']['x_max'], coverage['dem_extent_m']['z_min'], coverage['dem_extent_m']['z_max']))
        else:
            orographic.update({'status': 'pending_dem_halo_insufficient', 'orographic_elevation_source': 'coarse_condition_field', 'precipitation_status': 'declared_background_estimate', 'note': 'real-DEM orographic rainfall is pending: the requested envelope exceeds DEM coverage. The returned precipitation is a coarse-condition background estimate, NOT DEM-driven. Temperature does use the DEM elevation through the lapse rate.'})
        check_time('orographic')
    if use_dem_orographic:

        def dem_only_sampler(x_m, z_m):
            """已验证 DEM 全覆盖：只读 DEM，不接受任何退回粗地形的路径。"""
            _blank, ok, _r, _c = _dem_lookup(dem, x_m, z_m)
            if not ok.all():
                raise ValueError('verified DEM coverage was insufficient at evaluation time')
            real = _i50_np.asarray(elevation_sampler(x_m, z_m), _i50_np.float64)
            if not _i50_np.isfinite(real).all():
                raise ValueError('verified DEM sampler returned non-finite heights')
            return real
        climate = _x98_sample_climate_v2(seed, flat_x, flat_z, elevation_m=elevation_used, parameters=parameters, elevation_sampler=dem_only_sampler)
        counts['sample_climate_v2'] += 1
        cache['climate_batch_passes'] += 1
    elif measured_climate is None:
        climate = _x98_sample_climate_v2(seed, flat_x, flat_z, elevation_m=elevation_used, parameters=parameters, elevation_sampler=coarse_only_sampler)
        counts['sample_climate_v2'] += 1
        cache['climate_batch_passes'] += 1
    else:
        climate = measured_climate
    check_time('climate')
    bio1 = _i50_np.asarray(climate['BIO1_4_12_15'][0], _i50_np.float64).reshape(n)
    bio12 = _i50_np.asarray(climate['annual_precipitation_mm'], _i50_np.float64).reshape(n)
    multiplier = _i50_np.asarray(climate['precipitation_multiplier'], _i50_np.float64).reshape(n)
    monthly_temperature = _i50_np.asarray(climate['monthly_temperature_c'], _i50_np.float64)
    monthly_precipitation = _i50_np.asarray(climate['monthly_precipitation_mm'], _i50_np.float64)
    material = _x109_make_material_field((rows, cols), origin_m_xz=[origin_x, origin_z], spacing_m=GRID_SPACING_M, seed=material_seed_value)
    counts['make_material_field'] += 1
    material_field = material['arrays']
    row_index = _i50_np.rint((flat_z - origin_z) / GRID_SPACING_M).astype(_i50_np.int64)
    col_index = _i50_np.rint((flat_x - origin_x) / GRID_SPACING_M).astype(_i50_np.int64)
    thickness = _i50_np.asarray(material_field['erodible_thickness_m'], _i50_np.float64)[row_index, col_index]
    erodibility = _i50_np.asarray(material_field['erodibility'], _i50_np.float64)[row_index, col_index]
    thickness_cache = {}
    for key, value in zip(zip(flat_x.tolist(), flat_z.tolist()), thickness.tolist()):
        thickness_cache.setdefault(key, value)
    check_time('material')
    lithology = _x108_sample_lithology_points(flat_x, flat_z, world_seed=seed)
    counts['sample_lithology_points'] += 1
    class_index = _i50_np.asarray(lithology['class_index'], _i50_np.int64).reshape(n)
    rock_index = _i50_np.asarray(lithology['rock_index'], _i50_np.int64).reshape(n)
    bed_hardness = _i50_np.asarray(lithology['bed_hardness'], _i50_np.float64).reshape(n)
    s = float(soil_params.slope_spacing_m)
    if elevation_sampler is None or dem is None:
        soil_elevation_ok = _i50_np.ones(n, bool)
        soil_elevation_source = 'coarse_condition_field'
    else:

        def elevation_available_at(xx, zz):
            _v, ok, _r, _c = _dem_lookup(dem, xx, zz)
            return ok
        soil_elevation_ok = elevation_available_at(flat_x + s, flat_z) & elevation_available_at(flat_x - s, flat_z) & elevation_available_at(flat_x, flat_z + s) & elevation_available_at(flat_x, flat_z - s) & elevation_available_at(flat_x, flat_z)
        soil_elevation_source = 'caller_dem'
    bio12_cache = {}
    for key, value in zip(zip(flat_x.tolist(), flat_z.tolist()), bio12.tolist()):
        bio12_cache.setdefault(key, value)

    def bio12_sampler(xx, zz):
        arr_x = _i50_np.asarray(xx, _i50_np.float64)
        arr_z = _i50_np.asarray(zz, _i50_np.float64)
        out = _i50_np.empty(arr_x.shape, _i50_np.float64)
        flat_out = out.reshape(-1)
        fy = arr_x.reshape(-1)
        fz = arr_z.reshape(-1)
        for i in range(fy.size):
            key = (float(fy[i]), float(fz[i]))
            value = bio12_cache.get(key)
            if value is None:
                cache['bio12_exact_lookup_misses'] += 1
                raise ValueError('BIO12 cache miss at %r: exact-coordinate caching is mandatory and no nearest/average fill is permitted' % (key,))
            cache['bio12_exact_lookup_hits'] += 1
            flat_out[i] = value
        return out

    def thickness_sampler(xx, zz):
        arr_x = _i50_np.asarray(xx, _i50_np.float64)
        arr_z = _i50_np.asarray(zz, _i50_np.float64)
        out = _i50_np.empty(arr_x.shape, _i50_np.float64)
        flat_out = out.reshape(-1)
        fy = arr_x.reshape(-1)
        fz = arr_z.reshape(-1)
        for i in range(fy.size):
            key = (float(fy[i]), float(fz[i]))
            value = thickness_cache.get(key)
            if value is None:
                cache['thickness_exact_lookup_misses'] += 1
                raise ValueError('material thickness cache miss at %r: exact-coordinate caching is mandatory and no nearest/average fill is permitted' % (key,))
            cache['thickness_exact_lookup_hits'] += 1
            flat_out[i] = value
        return out
    if elevation_sampler is None or dem is None:

        def soil_elevation_sampler(xx, zz):
            return _i50_np.asarray(_i50_coarse_condition_field(seed, xx, zz)[0], _i50_np.float64)
    else:

        def soil_elevation_sampler(xx, zz):
            values, ok, _r, _c = _dem_lookup(dem, xx, zz)
            real = _i50_np.asarray(elevation_sampler(xx, zz), _i50_np.float64)
            if not (ok & _i50_np.isfinite(real)).all():
                raise ValueError('soil elevation found a DEM gap although the subset was declared servable')
            return real
    soil_depth = _i50_np.full(n, _i50_np.nan, _i50_np.float64)
    drainage = _i50_np.full(n, -1, _i50_np.int64)
    available_water = _i50_np.full(n, _i50_np.nan, _i50_np.float64)
    soil_status = _i50_np.where(soil_elevation_ok, 'computed', NOT_AVAILABLE).astype(object)
    soil_reason = _i50_np.full(n, '', dtype=object)
    soil_reason[~soil_elevation_ok] = 'soil_halo_outside_dem_coverage: the slope stencil needs x+-%.0f m and z+-%.0f m and the DEM cannot supply them; no snapping or zero fill is performed' % (s, s)
    if soil_elevation_ok.any():
        subset = _i50_np.flatnonzero(soil_elevation_ok)
        result = _x103_soil_condition(soil_seed, flat_x[subset], flat_z[subset], elevation=soil_elevation_sampler, bio12_mm=bio12_sampler, thickness_m=thickness_sampler, parameters=soil_params)
        counts['soil_condition'] += 1
        soil_depth[subset] = _i50_np.asarray(result['soil_depth_m'], _i50_np.float64).reshape(-1)
        drainage[subset] = _i50_np.asarray(result['drainage'], _i50_np.int64).reshape(-1)
        available_water[subset] = _i50_np.asarray(result['available_water'], _i50_np.float64).reshape(-1)
    check_time('soil')
    temperature_norm, rain_norm = _x94_climate_coordinates(bio1, bio12)
    climate_band = _i50_np.asarray(_x96_variant(temperature_norm, rain_norm), _i50_np.int64).reshape(n)
    if landform_ordinal is None:
        palette = None
        palette_status = NOT_AVAILABLE
        palette_reason = 'landform_ordinal_not_supplied: the 16-entry palette needs a non-heightfield landform ordinal, which is out of A1 scope; no ordinal is fabricated'
        ordinal_flat = None
    else:
        ordinal = _i50_np.broadcast_to(_i50_np.asarray(landform_ordinal, _i50_np.int64), shape).reshape(-1)
        if ordinal.size != n:
            raise ValueError('landform_ordinal must broadcast to the query shape')
        palette = _i50_np.asarray(_x95_palette_index(ordinal, climate_band), _i50_np.int64).reshape(n)
        palette_status = 'computed'
        palette_reason = None
        ordinal_flat = ordinal
    sub_seeds = {'material': material_seed_value, 'soil': soil_seed, 'material_source': material_seed_source}
    record = {'schema': SCHEMA, 'world_seed': seed, 'grid_spacing_m': GRID_SPACING_M, 'policy': orographic_policy, 'points_digest': _points_digest(flat_x, flat_z), 'point_count': n, 'dem': dem, 'climate': {'v2_parameter_identity_sha256': parameters.identity_sha256, 'v1_base_parameter_identity_sha256': parameters.base_parameter_identity_sha256, 'v1_parameter_identity_sha256': _x99_NoiseClimateParameters().identity_sha256, 'orographic_elevation_source': orographic['orographic_elevation_source'], 'precipitation_status': orographic['precipitation_status']}, 'material': {'algorithm': 'td-continuous-global-value-noise-v1', 'seed': material_seed_value, 'seed_source': material_seed_source, 'seed_derivation': "sha256('terragenesis-world-noise-v1', seed, purpose)[0:4] big-endian" if material_seed_source == 'derived' else 'caller_supplied', 'identity_sha256': material['identity_sha256']}, 'lithology': {'rock_table_identity_sha256': _x107_rock_table_identity(), 'seed_purposes': _x106_lithology_subseeds(seed)}, 'soil': {'algorithm': _x100_SOIL_ALGORITHM, 'seed': soil_seed, 'parameters': _i50_asdict(soil_params), 'seed_derivation': "sha256('terragenesis-world-noise-v1', seed, purpose)[0:4] big-endian", 'declared_uncalibrated': DECLARED_UNCALIBRATED, 'input_sources': {'elevation': soil_elevation_source, 'bio12': 'sample_climate_v2 annual_precipitation_mm (batch cache)', 'thickness': 'td_material_field erodible_thickness_m (batch cache)'}}, 'biome': {'variant_thresholds': {'temperature_low': _x90_TEMPERATURE_LOW, 'rain_dry': _x88_RAIN_DRY, 'rain_wet': _x89_RAIN_WET}, 'climate_coordinates': {'temperature_offset_c': _x91_TEMPERATURE_OFFSET_C, 'temperature_span_c': _x92_TEMPERATURE_SPAN_C, 'precipitation_span_mm': _x87_PRECIPITATION_SPAN_MM}, 'landform_ordinal_supplied': landform_ordinal is not None}, 'code_identities': _code_identities(), 'declared_uncalibrated': DECLARED_UNCALIBRATED}
    if ordinal_flat is None:
        record['biome']['landform_ordinal'] = {'supplied': False}
    else:
        record['biome']['landform_ordinal'] = {'supplied': True, 'values_digest': _ordinal_digest(flat_x, flat_z, ordinal_flat), 'value_histogram': {str(int(k)): int(v) for k, v in zip(*_i50_np.unique(ordinal_flat, return_counts=True))}, 'binding': 'digest over lexsorted (x, z, ordinal) triples, so a different ordinal at the same point changes identity and permutation does not'}
    combined_identity = _i50_identity({}, record)
    sources = {'elevation_m': {'source': 'caller_dem' if dem is not None else 'coarse_condition_field', 'units': UNITS['elevation_m']}, 'monthly_temperature_c': {'source': 'metric_climate_refinement.sample_climate_v2', 'units': UNITS['monthly_temperature_c'], 'elevation_driver': 'dem_lapse_rate' if dem is not None else 'coarse_condition_field', 'status': 'dem_elevation_lapse_estimate' if dem is not None else 'declared_background_estimate'}, 'monthly_precipitation_mm': {'source': 'metric_climate_refinement.sample_climate_v2', 'units': UNITS['monthly_precipitation_mm'], 'status': orographic['precipitation_status'], 'orographic_elevation_source': orographic['orographic_elevation_source'], 'note': 'in v2 the explicit elevation_m never changes precipitation; only the orographic sampler does (measured)'}, 'BIO1_c': {'source': 'sample_climate_v2 months', 'units': UNITS['BIO1_c']}, 'BIO12_mm': {'source': 'sample_climate_v2 annual_precipitation_mm', 'units': UNITS['BIO12_mm'], 'status': orographic['precipitation_status']}, 'material_erodible_thickness_m': {'source': 'td_material_field.make_material_field', 'units': UNITS['material_erodible_thickness_m'], 'note': 'erodible thickness is not soil depth and not storage'}, 'material_erodibility': {'source': 'td_material_field.make_material_field', 'units': UNITS['material_erodibility']}, 'lithology_class_index': {'source': 'td_lithology_field.sample_lithology_points', 'units': 'ordinal_into_%r' % (_x104_CLASS_IDS,)}, 'lithology_rock_index': {'source': 'td_lithology_field.sample_lithology_points', 'units': 'ordinal_into_rock_table', 'note': 'a rock name is not a complete physical property set'}, 'lithology_bed_hardness': {'source': 'td_lithology_field.sample_lithology_points', 'units': UNITS['lithology_bed_hardness'], 'declared_uncalibrated': True}, 'soil_depth_m': {'source': 'metric_soil_condition.soil_condition', 'units': UNITS['soil_depth_m']}, 'drainage': {'source': 'metric_soil_condition.soil_condition', 'units': UNITS['drainage']}, 'available_water': {'source': 'metric_soil_condition.soil_condition', 'units': UNITS['available_water'], 'semantics': AVAILABLE_WATER_SEMANTICS}, 'biome_climate_band': {'source': 'metric_biome_climate.variant', 'units': 'ordinal_0_cold_1_dry_2_temperate_3_wet', 'note': 'a climate band label is not generated vegetation'}, 'biome_palette_index': {'source': 'metric_biome_climate.palette_index', 'status': palette_status}, 'potential_et': {'status': NOT_AVAILABLE, 'reason': 'no PET model is in A1 scope; available_water is a relative proxy, not ET'}, 'actual_et': {'status': NOT_AVAILABLE, 'reason': 'dynamic ET requires the advance_soil bucket chain, which this entry point does not run and does not claim'}, 'land_cover': {'status': NOT_AVAILABLE, 'reason': 'vegetation cover is not implemented in Python'}}
    flat = None
    return {'schema': SCHEMA, 'shape': list(shape), 'x_m': flat_x.reshape(shape), 'z_m': flat_z.reshape(shape), 'elevation_m': elevation_used.reshape(shape), 'elevation_dem_m': _i50_np.where(elevation_available, elevation_dem, _i50_np.nan).reshape(shape) if dem is not None else None, 'elevation_source_per_point': _i50_np.where(elevation_available, 'caller_dem', 'coarse_condition_field').reshape(shape), 'monthly_temperature_c': monthly_temperature.reshape((12,) + shape), 'monthly_precipitation_mm': monthly_precipitation.reshape((12,) + shape), 'BIO1_c': bio1.reshape(shape), 'BIO12_mm': bio12.reshape(shape), 'precipitation_multiplier': multiplier.reshape(shape), 'material_erodible_thickness_m': thickness.reshape(shape), 'material_erodibility': erodibility.reshape(shape), 'lithology_class_index': class_index.reshape(shape), 'lithology_rock_index': rock_index.reshape(shape), 'lithology_bed_hardness': bed_hardness.reshape(shape), 'soil_depth_m': soil_depth.reshape(shape), 'drainage': drainage.reshape(shape), 'available_water': available_water.reshape(shape), 'soil_status': soil_status.reshape(shape), 'soil_reason': soil_reason.reshape(shape), 'available_water_semantics': AVAILABLE_WATER_SEMANTICS, 'biome_climate_band': climate_band.reshape(shape), 'biome_climate_band_name': _i50_np.asarray([_x93_VARIANT_NAMES[int(v)] for v in climate_band]).reshape(shape), 'biome_palette_index': None if palette is None else palette.reshape(shape), 'biome_palette_status': palette_status, 'biome_palette_reason': palette_reason, 'rock_names': _i50_np.asarray([_x105_ROCK_ORDER[int(i)] for i in rock_index]).reshape(shape), 'orographic': orographic, 'sources': sources, 'units': UNITS, 'identity': {'combined_identity_sha256': combined_identity, 'record': record, 'sub_seeds': sub_seeds, 'points_digest': record['points_digest']}, 'budget': budget, 'cost': {'seconds': round(elapsed(), 3), 'source_call_counts': counts, 'cache': cache, 'rss_note': 'do not read tracemalloc as tree RSS; process RSS is measured by the caller/driver'}, 'limitations': ['A1 environment query only: this is not a dynamic hydrology-ecology chain.', 'available_water is a relative proxy, never dynamic ET.', 'material erodible thickness != soil depth != water storage.', 'rock names are engineering reference values, not measured properties.', 'biome climate band is not generated vegetation.', 'no PET/actual ET/land cover are returned; those fields are explicitly not_available.', 'does not feed, modify or claim the M1-M4 finite-river product or the default world.', {'orographic_pending': orographic['status']}]}

def describe():
    """返回本入口的静态声明（供审查与下游引用，不参与数值）。"""
    return {'schema': SCHEMA, 'grid_spacing_m': GRID_SPACING_M, 'policies': list(POLICIES), 'max_points': MAX_POINTS, 'max_material_cells': MAX_MATERIAL_CELLS, 'max_output_bytes': MAX_OUTPUT_BYTES, 'max_seconds': MAX_SECONDS, 'available_water_semantics': AVAILABLE_WATER_SEMANTICS, 'declared_uncalibrated': DECLARED_UNCALIBRATED, 'not_available_fields': ['potential_et', 'actual_et', 'land_cover'], 'never': ['10 km compatibility mode', 'nearest/average fill', 'snapping to grid', 'DEM-fabricated orographic rainfall when pending', 'dynamic ET from available_water']}
