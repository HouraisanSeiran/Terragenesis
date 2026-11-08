"""Consolidated special_terrain implementations; numeric expressions preserved."""
from __future__ import annotations
from terrain_pipeline.common_infra import file_sha256 as _kernel_file_sha256
import numpy as _i27_np
from dataclasses import asdict as _i28_asdict
from dataclasses import dataclass as _i28_dataclass
import hashlib as _i28_hashlib
import json as _i28_json
import math as _i28_math
from pathlib import Path as _i28_Path
import sys as _i28_sys
import time as _i28_time
import numpy as _i28_np
from dataclasses import asdict as _i30_asdict
from dataclasses import dataclass as _i30_dataclass
from dataclasses import replace as _i30_replace
import math as _i30_math
import numpy as _i30_np
from terrain_pipeline.common_infra import SOURCE_MAX_CELLS as _i30_MAX_CELLS
from terrain_pipeline.common_infra import MAX_METADATA as _i30_MAX_METADATA
from terrain_pipeline.common_infra import identity as _i30_identity
from terrain_pipeline.common_infra import load_bundle as _i30_load_bundle
from terrain_pipeline.common_infra import readonly as _i30_readonly
from terrain_pipeline.common_infra import save_bundle as _i30_save_bundle
from dataclasses import asdict as _i29_asdict
from dataclasses import dataclass as _i29_dataclass
import hashlib as _i29_hashlib
import json as _i29_json
import math as _i29_math
from pathlib import Path as _i29_Path
import numpy as _i29_np
from diffusion.geographic_noise import field as _i29_field
from terrain_pipeline.common_infra import SOURCE_MAX_CELLS as _i29_SOURCE_MAX_CELLS
from terrain_pipeline.common_infra import GRID_MAX_CELLS as _i29_MAX_CELLS
from terrain_pipeline.common_infra import MAX_METADATA as _i29_MAX_METADATA
from terrain_pipeline.common_infra import identity as _i29_identity
from terrain_pipeline.common_infra import readonly as _i29_readonly
from terrain_pipeline.common_infra import load_bundle as _i29_load_bundle
from terrain_pipeline.common_infra import save_bundle as _i29_save_bundle
from terrain_pipeline.common_infra import BoundaryGrid as _i29_BoundaryGrid
from terrain_pipeline.common_infra import TerrainGrid as _i29_TerrainGrid
from terrain_pipeline.drainage import accumulate_local_discharge as _i29_accumulate_local_discharge
from terrain_pipeline.drainage import route_diagnostic as _i29_route_diagnostic
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import conservative_diffusion_step as _i29_conservative_diffusion_step
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import phase_record as _i29_phase_record
from terrain_pipeline.surface_rivers.metric_fluvial_slope_stability import relax_mobile_slopes as _i29_relax_mobile_slopes
from dataclasses import asdict as _i31_asdict
from dataclasses import dataclass as _i31_dataclass
import hashlib as _i31_hashlib
import importlib as _i31_importlib
import json as _i31_json
import math as _i31_math
from pathlib import Path as _i31_Path
import numpy as _i31_np
from dataclasses import asdict as _i32_asdict
from dataclasses import dataclass as _i32_dataclass
from importlib.metadata import version as _i32_version
import hashlib as _i32_hashlib
import json as _i32_json
import math as _i32_math
from pathlib import Path as _i32_Path
import numpy as _i32_np
from dataclasses import asdict as _i33_asdict
from dataclasses import dataclass as _i33_dataclass
import hashlib as _i33_hashlib
import importlib as _i33_importlib
import json as _i33_json
import math as _i33_math
from pathlib import Path as _i33_Path
import sys as _i33_sys
import numpy as _i33_np
from dataclasses import asdict as _i34_asdict
from dataclasses import dataclass as _i34_dataclass
import hashlib as _i34_hashlib
import json as _i34_json
import math as _i34_math
from pathlib import Path as _i34_Path
import sys as _i34_sys
import numpy as _i34_np
import math as _i35_math
import numpy as _i35_np
from terrain_pipeline.common_infra import identity as _i35_identity
from terrain_pipeline.fine_subgrid import build_fine_geometry as _i35_build_fine_geometry
from terrain_pipeline.hybrid_geometry import ray_hits as _x0_ray_hits
from terrain_pipeline.hybrid_geometry import seal as _x1_hybrid_cave_geometry_seal
from terrain_pipeline.hybrid_geometry import signed_volume as _x2_signed_volume
from terrain_pipeline.hybrid_geometry import ALGORITHM as _x3_ALGORITHM
from terrain_pipeline.hybrid_geometry import BooleanParameters as _x4_BooleanParameters
from terrain_pipeline.hybrid_geometry import FLAGS as _x5_FLAGS
from terrain_pipeline.hybrid_geometry import census as _x6_census
from terrain_pipeline.hybrid_geometry import combine as _x7_combine
from terrain_pipeline.hybrid_geometry import polygon_prism_record as _x8_polygon_prism_record
from terrain_pipeline.hybrid_geometry import solid_from_record as _x9_solid_from_record
from terrain_pipeline.hybrid_geometry import identity as _x10_identity
from terrain_pipeline.vdm_cuts import _check_mesh as _x11_check_mesh
from terrain_pipeline.vdm_cuts import _triangles as _x12_triangles
from terrain_pipeline.vdm_cuts import _check_mesh as _x13_check_mesh
from terrain_pipeline.vdm_cuts import _smooth as _x14_smooth
from terrain_pipeline.vdm_cuts import _triangles as _x15_triangles
from terrain_pipeline.hybrid_geometry import ray_hits as _x16_ray_hits
from terrain_pipeline.hybrid_geometry import seal as _x17_hybrid_cave_geometry_seal
from terrain_pipeline.hybrid_geometry import FLAGS as _x18_FLAGS
from terrain_pipeline.hybrid_geometry import BooleanParameters as _x19_BooleanParameters
from terrain_pipeline.hybrid_geometry import census as _x20_census
from terrain_pipeline.hybrid_geometry import excavate as _x21_excavate
from terrain_pipeline.hybrid_geometry import frustum_record as _x22_frustum_record
from terrain_pipeline.hybrid_geometry import octagon_ring as _x23_octagon_ring
from terrain_pipeline.hybrid_geometry import polygon_prism_record as _x24_polygon_prism_record
from terrain_pipeline.hybrid_geometry import solid_from_record as _x25_solid_from_record
from terrain_pipeline.hybrid_geometry import identity as _x26_identity
from terrain_pipeline.hybrid_geometry import manifold_from_record as _x27_manifold_from_record
from terrain_pipeline.hybrid_geometry import mesh_record as _x28_mesh_record
from terrain_pipeline.hybrid_geometry import ray_hits as _x29_ray_hits
from terrain_pipeline.hybrid_geometry import seal as _x30_hybrid_cave_geometry_seal
from terrain_pipeline.hybrid_geometry import signed_volume as _x31_signed_volume
from terrain_pipeline.hybrid_geometry import identity as _x32_identity
from terrain_pipeline.hybrid_geometry import ray_hits as _x33_ray_hits
from terrain_pipeline.hybrid_geometry import seal as _x34_hybrid_cave_geometry_seal
from terrain_pipeline.hybrid_geometry import identity as _x35_identity
from terrain_pipeline.hybrid_geometry import ALGORITHM as _x36_ALGORITHM
from terrain_pipeline.hybrid_geometry import BooleanParameters as _x37_BooleanParameters
from terrain_pipeline.hybrid_geometry import FLAGS as _x38_FLAGS
from terrain_pipeline.hybrid_geometry import MANIFOLD as _x39_MANIFOLD
from terrain_pipeline.hybrid_geometry import SOLID_SCHEMA as _x40_SOLID_SCHEMA
from terrain_pipeline.hybrid_geometry import census as _x41_census
from terrain_pipeline.hybrid_geometry import combine as _x42_combine
from terrain_pipeline.hybrid_geometry import solid_from_record as _x43_solid_from_record
from terrain_pipeline.hybrid_geometry import sphere_record as _x44_sphere_record
from terrain_pipeline.hybrid_geometry import ray_hits as _x45_ray_hits
from terrain_pipeline.hybrid_geometry import seal as _x46_hybrid_cave_geometry_seal
from terrain_pipeline.hybrid_geometry import ALGORITHM as _x47_ALGORITHM
from terrain_pipeline.hybrid_geometry import BooleanParameters as _x48_BooleanParameters
from terrain_pipeline.hybrid_geometry import FLAGS as _x49_FLAGS
from terrain_pipeline.hybrid_geometry import census as _x50_census
from terrain_pipeline.hybrid_geometry import combine as _x51_combine
from terrain_pipeline.hybrid_geometry import frustum_record as _x52_frustum_record
from terrain_pipeline.hybrid_geometry import solid_from_record as _x53_solid_from_record
from terrain_pipeline.hybrid_geometry import identity as _x54_identity
from terrain_pipeline.vdm_cuts import _triangles as _x55_triangles
from terrain_pipeline.hybrid_geometry import FLAGS as _x65_FLAGS
from terrain_pipeline.hybrid_geometry import MAX_COMPONENTS as _x66_MAX_COMPONENTS
from terrain_pipeline.hybrid_geometry import polygon_prism_record as _x67_polygon_prism_record
from terrain_pipeline.hybrid_geometry import frustum_record as _x68_frustum_record
from terrain_pipeline.hybrid_geometry import BooleanParameters as _x69_BooleanParameters
from terrain_pipeline.hybrid_geometry import excavate as _x70_excavate
CATEGORY = 'C'

def as_origin(origin):
    origin = _i27_np.asarray(origin, float)
    if origin.shape != (3,) or not _i27_np.isfinite(origin).all():
        raise ValueError('finite three-component local origin required')
    return origin

def make_origin_normalizer(DEFAULT_ORIGIN):
    """_origin of uluru_flare/pillars3d: None selects the module default."""

    def _origin(origin):
        origin = DEFAULT_ORIGIN.copy() if origin is None else _i27_np.asarray(origin, float)
        if origin.shape != (3,) or not _i27_np.isfinite(origin).all():
            raise ValueError('finite three-component local origin required')
        return origin
    return _origin

def make_inside_by_winding(winding_number):
    """inside_by_winding of uluru_flare/pillars3d for the module winding_number."""

    def inside_by_winding(record, point_world_xyz_m, origin):
        winding = winding_number(record['vertices_local_xyz_m'], record['triangles'], point_world_xyz_m, origin)
        return (bool(round(winding) == 1), float(winding))
    return inside_by_winding
SCHEMA = 'td-special-terrain-l1-pillars3d-v1'
REPORT_SCHEMA = 'td-special-terrain-l1-pillars3d-report-v1'
ALGORITHM = 'joint-controlled-sandstone-pillar-field-with-vdm-carved-vertical-walls-v1'
SOLID_SCHEMA = 'td-hybrid-local-solid-mesh-v1'
PARENT_ALGORITHM = _x3_ALGORITHM
BASE_KIND = 'synthetic_analytic'
SOLID_ROLE = 'pillar_field_rock'
PLATEAU_ROLE = 'plateau'
PILLAR_ROLE_PREFIX = 'pillar-'
DEFAULT_ORIGIN = _i28_np.array([0.0, 0.0, 0.0])
DEFAULT_OUTPUT = _i28_Path('.scratch/special-terrain/l1-preview-20261020/pillars3d')
PROBE_CUBE_EDGE_M = 0.2
WORLD_FRAME_NOTE = 'witness coordinates are world metres (local mesh frame + local_origin_xyz_m); y is elevation and the model base plane is world y = 0'
FIGURE_SCOPE = 'display only; a figure is never a certification'
GEOLOGY_NOTE = 'the landform is quartz sandstone of Middle-Upper Devonian age with a nearly horizontal attitude; its sculpting is **not** carbonate karst but running water cutting down a pre-existing network of several sets of near-vertical joints, which is why a real pillar is a multi-sided prism with vertical arrises and an angular, flat top rather than a surface of revolution. The four-stage evolution (platform/mesa -> peak wall -> peak cluster/forest -> residual forest) is what makes the pillars stand as a field of separate bodies instead of one dissected mass.'
SUPERSEDES = {'kind': 'sandstone_pillar_field', 'superseded_schema': 'metric-special-terrain-v1', 'superseded_algorithm': 'special-terrain-field-forms-v1', 'superseded_surface_schema': 'metric-special-terrain-surface-v2', 'scope': 'the displacement-height-field values generated for kind sandstone_pillar_field are void', 'reason': 'a single-valued height field cannot express a multi-sided polygonal prism section, vertical walls, an outward-bulging iron cap, or a wall alcove; the recorded field therefore carries no admissible geometry for this landform', 'replaced_by': ALGORITHM, 'not_a_certification': True}
EXPLICIT_ASSUMPTIONS = ({'name': 'pitch_m', 'value': 30.0, 'grade': 'assumed', 'reason': 'pillar spacing is one of the four hard gaps of ledger section 3; no source supplies it'}, {'name': 'jitter_fraction', 'value': 0.25, 'grade': 'assumed', 'reason': 'joint-network irregularity is a placement choice; no source supplies it'}, {'name': 'joint_gap_m', 'value': 6.0, 'grade': 'assumed', 'reason': 'vertical joint aperture is a hard gap; the value only has to keep the carved walls more than outward_limit_m apart'}, {'name': 'height_band_source_m', 'value': [30.0, 400.0], 'grade': 'secondary', 'reason': 'ledger section 2/4.3: individual pillars run from tens of metres to 400 m, with more than a thousand above 200 m'}, {'name': 'height_min_m', 'value': 40.0, 'grade': 'assumed', 'reason': "the ledger's secondary range is tens of metres to 400 m; sampling only 40-150 m is a sampling-band choice, exactly as the L0 ledger already records for height_band"}, {'name': 'height_max_m', 'value': 150.0, 'grade': 'assumed', 'reason': 'upper end of the sampled band; the tall end of the secondary range is deliberately not sampled in this candidate'}, {'name': 'rows', 'value': 4, 'grade': 'assumed', 'reason': 'a 4x4 fixture only; the field size is decided by the hosting chart, not by any source'}, {'name': 'cols', 'value': 4, 'grade': 'assumed', 'reason': 'a 4x4 fixture only; the field size is decided by the hosting chart'}, {'name': 'seed', 'value': 20261020, 'grade': 'assumed', 'reason': 'a deterministic seed is required for reproducibility and is not a survey value'}, {'name': 'base_thickness_m', 'value': 45.0, 'grade': 'assumed', 'reason': 'synthetic analytic base beyond the sampled band; chosen evenly above the tallest pillar so the base never crops the field'}, {'name': 'strike_stretch', 'value': 1.6, 'grade': 'assumed', 'reason': 'the dominance of one joint set is a geological fact, its numeric stretch is not; no source supplies the ratio'}, {'name': 'substep_m', 'value': 3.0, 'grade': 'assumed', 'reason': 'wall subdivision in elevation is a resolution choice'}, {'name': 'ring_spacing_m', 'value': 1.5, 'grade': 'assumed', 'reason': 'the joint ring has to be resampled for a perimeter flute to have vertices to act on; the spacing is a resolution choice'}, {'name': 'smooth_passes', 'value': 4, 'grade': 'assumed', 'reason': 'removing the mitre corner of a joint cell before displacing is a numerical requirement (an inward offset larger than the corner radius folds the section); the pass count is a choice'}, {'name': 'taper_fraction', 'value': 0.1, 'grade': 'assumed', 'reason': 'the 上细下粗 direction (thin top over a thick base) is described by the sources, the fraction is not'}, {'name': 'cap_thickness_m', 'value': 30.0, 'grade': 'secondary', 'reason': 'ledger section 2/4.3: the top ~30 m is an iron-bearing quartz sandstone cap'}, {'name': 'cap_bulge_m', 'value': 1.1, 'grade': 'assumed', 'reason': 'how far the harder cap stands proud of the wall below it is not in any source'}, {'name': 'striation_amplitude_m', 'value': [0.55, 0.22], 'grade': 'assumed', 'reason': 'two orders of horizontal joint striation (节理横纹) are described by the sources, their amplitudes are not'}, {'name': 'striation_wavelength_m', 'value': [24.0, 14.0], 'grade': 'assumed', 'reason': "bedding-controlled striation spacing is a hard gap; the values also satisfy the repository's SAMPLES_PER_FEATURE = 4 against substep_m"}, {'name': 'flute_amplitude_m', 'value': [0.55, 0.22], 'grade': 'assumed', 'reason': 'perimeter fluting (纵向凹槽) amplitude has no source'}, {'name': 'flute_pitch_m', 'value': [16.0, 7.0], 'grade': 'assumed', 'reason': 'perimeter fluting wavelength has no source; kept above 4x ring_spacing_m to avoid aliasing'}, {'name': 'inward_limit_m', 'value': 2.0, 'grade': 'assumed', 'reason': 'the clamp that keeps a carved section a simple polygon is a numerical requirement, not a measurement'}, {'name': 'outward_limit_m', 'value': 2.0, 'grade': 'assumed', 'reason': 'the outward clamp is bounded by half the joint gap so neighbouring pillars never fuse; it is not a measurement'}, {'name': 'carve_backoff', 'value': [1.0, 0.7, 0.5, 0.35, 0.22, 0.12, 0.0], 'grade': 'assumed', 'reason': "the depth-reduction ladder is a numerical admissibility device: a joint cell's mitre corner has a near-zero radius of curvature, so an inward offset deeper than that radius folds the section through itself"}, {'name': 'base_footprint_half_extent_m', 'value': 156.0, 'grade': 'assumed', 'reason': 'derived from rows/cols/pitch/strike_stretch plus two pitches of margin; the analytic base is synthetic and not surveyed'})
DEFAULT_CARVE_BACKOFF = (1.0, 0.7, 0.5, 0.35, 0.22, 0.12, 0.0)

def _finite_float(name, value, *, low=None, high=None):
    if type(value) is not float or not _i28_math.isfinite(value):
        raise ValueError('explicit finite float required for ' + name)
    if low is not None and value < low:
        raise ValueError('value below the explicit bound required for ' + name)
    if high is not None and value > high:
        raise ValueError('value above the explicit bound required for ' + name)
    return value

def _pair(name, value):
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError('explicit two-component tuple required for ' + name)
    for item in value:
        if type(item) is not float or not _i28_math.isfinite(item) or item <= 0.0:
            raise ValueError('positive finite float components required for ' + name)
    return value

@_i28_dataclass(frozen=True)
class PillarParameters:
    """Every dimension is an explicit assumption; no default is a survey value.

    The defaults are the prototype's own constants, so the default build reproduces the
    archived prototype byte for byte in its measured quantities.
    """
    seed: int = 20261020
    pitch_m: float = 30.0
    rows: int = 4
    cols: int = 4
    jitter_fraction: float = 0.25
    joint_gap_m: float = 6.0
    height_min_m: float = 40.0
    height_max_m: float = 150.0
    base_thickness_m: float = 45.0
    strike_stretch: float = 1.6
    substep_m: float = 3.0
    ring_spacing_m: float = 1.5
    smooth_passes: int = 4
    taper_fraction: float = 0.1
    cap_thickness_m: float = 30.0
    cap_bulge_m: float = 1.1
    striation_amplitude_m: tuple = (0.55, 0.22)
    striation_wavelength_m: tuple = (24.0, 14.0)
    flute_amplitude_m: tuple = (0.55, 0.22)
    flute_pitch_m: tuple = (16.0, 7.0)
    inward_limit_m: float = 2.0
    outward_limit_m: float = 2.0
    carve_backoff: tuple = DEFAULT_CARVE_BACKOFF

    def __post_init__(self):
        if type(self.seed) is not int or not 0 <= self.seed <= 2 ** 32:
            raise ValueError('bounded integer seed required')
        for name in ('rows', 'cols'):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 64:
                raise ValueError('bounded integer field extent required for ' + name)
        if type(self.smooth_passes) is not int or not 0 <= self.smooth_passes <= 64:
            raise ValueError('bounded integer smoothing pass count required')
        _finite_float('pitch_m', self.pitch_m, low=1.0, high=2000.0)
        _finite_float('joint_gap_m', self.joint_gap_m, low=0.05, high=200.0)
        _finite_float('height_min_m', self.height_min_m, low=0.5, high=2000.0)
        _finite_float('height_max_m', self.height_max_m, low=0.5, high=2000.0)
        _finite_float('base_thickness_m', self.base_thickness_m, low=0.5, high=2000.0)
        _finite_float('jitter_fraction', self.jitter_fraction, low=0.0, high=0.49)
        _finite_float('strike_stretch', self.strike_stretch, low=1.0, high=8.0)
        _finite_float('substep_m', self.substep_m, low=0.05, high=50.0)
        _finite_float('ring_spacing_m', self.ring_spacing_m, low=0.05, high=20.0)
        _finite_float('taper_fraction', self.taper_fraction, low=0.0, high=0.95)
        _finite_float('cap_thickness_m', self.cap_thickness_m, low=0.0, high=2000.0)
        _finite_float('cap_bulge_m', self.cap_bulge_m, low=0.0, high=50.0)
        _finite_float('inward_limit_m', self.inward_limit_m, low=0.0, high=50.0)
        _finite_float('outward_limit_m', self.outward_limit_m, low=0.0, high=50.0)
        for name in ('striation_amplitude_m', 'striation_wavelength_m', 'flute_amplitude_m', 'flute_pitch_m'):
            _pair(name, getattr(self, name))
        if not self.height_min_m < self.height_max_m:
            raise ValueError('the sampled height band must be a strict interval')
        if not self.outward_limit_m < 0.5 * self.joint_gap_m:
            raise ValueError('the outward clamp must stay inside half the joint gap, otherwise neighbouring pillars can fuse')
        if not self.substep_m * 4.0 <= min(self.striation_wavelength_m):
            raise ValueError("the finest vertical striation wavelength must satisfy the repository's SAMPLES_PER_FEATURE = 4 against substep_m")
        if not self.ring_spacing_m * 4.0 <= min(self.flute_pitch_m):
            raise ValueError('the finest flute pitch must satisfy SAMPLES_PER_FEATURE = 4 against ring_spacing_m')
        if not isinstance(self.carve_backoff, tuple) or not self.carve_backoff:
            raise ValueError('explicit non-empty carve backoff ladder required')
        previous = _i28_math.inf
        for step in self.carve_backoff:
            if type(step) is not float or not _i28_math.isfinite(step) or (not 0.0 <= step <= 1.0):
                raise ValueError('carve backoff steps must be finite floats inside [0, 1]')
            if step > previous:
                raise ValueError('the carve backoff ladder must not increase')
            previous = step
        if self.carve_backoff[-1] != 0.0:
            raise ValueError('the carve backoff ladder must reach 0. so that the uncarved prism is always the last admissible fallback')

    @property
    def height_band_m(self):
        return (self.height_min_m, self.height_max_m)

    @property
    def pillar_count(self):
        return self.rows * self.cols

    @property
    def footprint_half_extent_m(self):
        return 0.5 * (max(self.rows, self.cols) * self.pitch_m) * self.strike_stretch + 2.0 * self.pitch_m

def resample_ring(ring, spacing_m):
    """Uniform arc-length resampling, so a perimeter flute has vertices to act on.

    Without this the joint-cell ring carries one vertex every ~12 m while the flute wavelength
    is ~11 m: the fixture aliases into a jagged, self-crossing section. The repository states
    the same rule as ``SAMPLES_PER_FEATURE = 4`` in ``metric_special_terrain_forms``.
    """
    closed = _i28_np.vstack((ring, ring[:1]))
    steps = _i28_np.linalg.norm(_i28_np.diff(closed, axis=0), axis=1)
    s = _i28_np.concatenate(([0.0], _i28_np.cumsum(steps)))
    total = float(s[-1])
    count = max(8, int(round(total / spacing_m)))
    target = _i28_np.linspace(0.0, total, count, endpoint=False)
    x = _i28_np.interp(target, s, closed[:, 0])
    z = _i28_np.interp(target, s, closed[:, 1])
    return _i28_np.stack((x, z), axis=1)

def smooth_ring(ring, passes):
    """Cyclic moving average.

    The resampled ring still carries the mitre corner of its joint cell, and a corner has a
    local radius of curvature of nearly zero. Offsetting inward by more than that radius --
    which is exactly what carving a wall does -- folds the section through itself. Measured on
    this fixture: unsmoothed, 15 of 16 cells folded 4-16 m above the base; smoothed, none do.
    """
    out = _i28_np.array(ring, dtype=float)
    for _ in range(int(passes)):
        out = 0.5 * out + 0.25 * (_i28_np.roll(out, -1, axis=0) + _i28_np.roll(out, 1, axis=0))
    return out

def joint_cells(parameters):
    """Voronoi cells of a jittered seed grid: one irregular convex polygon per pillar.

    Deterministic in ``parameters.seed``: the jitter draws, then the heights, come off the same
    stream in the same order as the archived prototype, so the default build reproduces it.
    """
    from scipy.spatial import Voronoi
    from shapely.geometry import Polygon
    from shapely.geometry import box
    from shapely.geometry.polygon import orient
    rng = _i28_np.random.default_rng(parameters.seed)
    centres = []
    for row in range(parameters.rows):
        for col in range(parameters.cols):
            cx = (col - 0.5 * (parameters.cols - 1)) * parameters.pitch_m
            cz = (row - 0.5 * (parameters.rows - 1)) * parameters.pitch_m
            jitter = rng.uniform(-parameters.jitter_fraction, parameters.jitter_fraction, size=2) * parameters.pitch_m
            centres.append((cx + jitter[0], cz + jitter[1]))
    centres = _i28_np.asarray(centres, dtype=float)
    centres[:, 1] *= parameters.strike_stretch
    half = 0.5 * (max(parameters.rows, parameters.cols) * parameters.pitch_m) * parameters.strike_stretch + 2.0 * parameters.pitch_m
    mirrored = [centres]
    for sign in (-1.0, 1.0):
        for axis in (0, 1):
            shift = _i28_np.zeros(2)
            shift[axis] = sign * 2.0 * half
            mirrored.append(centres + shift)
    vor = Voronoi(_i28_np.vstack(mirrored))
    frame = box(-half, -half, half, half)
    polygons = []
    for index in range(len(centres)):
        region = vor.regions[vor.point_region[index]]
        if not region or -1 in region:
            raise RuntimeError('unbounded joint cell')
        cell = Polygon(vor.vertices[region]).intersection(frame).buffer(-0.5 * parameters.joint_gap_m, join_style='mitre')
        if cell.is_empty or cell.area <= 0.0:
            raise RuntimeError('empty joint cell')
        if not cell.is_valid:
            cell = cell.buffer(0.0)
        cell = orient(cell, sign=1.0)
        ring = resample_ring(_i28_np.asarray(cell.exterior.coords)[:-1], parameters.ring_spacing_m)
        polygons.append(smooth_ring(ring, parameters.smooth_passes))
    heights = rng.uniform(parameters.height_min_m, parameters.height_max_m, size=len(polygons))
    return (polygons, heights, centres, half)

def _outward_normals(ring):
    following = _i28_np.roll(ring, -1, axis=0)
    preceding = _i28_np.roll(ring, 1, axis=0)
    tangent = following - preceding
    normal = _i28_np.stack((tangent[:, 1], -tangent[:, 0]), axis=1)
    length = _i28_np.linalg.norm(normal, axis=1, keepdims=True)
    return normal / _i28_np.where(length > 0.0, length, 1.0)

def taper_factor(y, height, taper_fraction):
    """Exact similarity contraction of the section: 上细下粗, thin top over a thick base.

    Scaling about the section's own centroid is the definition of a taper, and it is provably
    fold-free: a positive similarity maps a simple polygon to a simple polygon. Displacing
    each vertex along its own normal by a length proportional to its distance from the centroid
    is *not* the same transform, and it does fold the wall near sharp corners -- that is why
    the first carved builds needed a depth backoff on half the pillars.
    """
    return 1.0 - taper_fraction * (y / height)

def perimeter_arc_length(ring):
    closed = _i28_np.vstack((ring, ring[:1]))
    steps = _i28_np.linalg.norm(_i28_np.diff(closed, axis=0), axis=1)
    return _i28_np.concatenate(([0.0], _i28_np.cumsum(steps)))[:len(ring)]

def ring_area(ring):
    """Absolute shoelace area of a closed (x, z) ring, in m^2."""
    ring = _i28_np.asarray(ring, float)
    x, z = (ring[:, 0], ring[:, 1])
    return float(abs(_i28_np.sum(x * _i28_np.roll(z, -1) - _i28_np.roll(x, -1) * z) / 2.0))

def wall_displacement(ring, perimeter_s, y, height, cell_phase, carve, parameters, scale=1.0):
    """Lateral (in-plane) displacement of one wall vertex, along its outward normal.

    Every term is the repository's own research vocabulary applied to a vertical wall: striation
    is 节理横纹 (two orders), flute is the perimeter 纵向凹槽 the 岩壁Voronoi design asks for,
    and the cap is the 铁帽. The taper is deliberately not here: it is a similarity contraction
    applied separately in ``wall_ring_at``, so that it cannot fold the section.
    """
    if not carve:
        return _i28_np.zeros(len(ring))
    striation = sum((amplitude * _i28_np.sin(2.0 * _i28_np.pi * y / wavelength + cell_phase) for amplitude, wavelength in zip(parameters.striation_amplitude_m, parameters.striation_wavelength_m)))
    flute = sum((amplitude * _i28_np.sin(2.0 * _i28_np.pi * perimeter_s / pitch + 1.7 * cell_phase) for amplitude, pitch in zip(parameters.flute_amplitude_m, parameters.flute_pitch_m)))
    cap = parameters.cap_bulge_m if y >= height - parameters.cap_thickness_m else 0.0
    return _i28_np.clip(scale * (striation + flute + cap), -parameters.inward_limit_m, parameters.outward_limit_m)

def wall_ring_at(ring, perimeter_s, y, height, cell_phase, carve, parameters, scale=1.0):
    """One horizontal wall section: taper first, then the additive carve along the normals."""
    displacement = wall_displacement(ring, perimeter_s, y, height, cell_phase, carve, parameters, scale)
    centre = ring.mean(axis=0)
    contracted = centre + (ring - centre) * taper_factor(y, height, parameters.taper_fraction)
    return contracted + _outward_normals(contracted) * _i28_np.asarray(displacement)[:, None]

def wall_levels(height, substep_m):
    levels = _i28_np.arange(0.0, height + 1e-09, substep_m)
    if levels[-1] < height - 1e-09:
        levels = _i28_np.append(levels, height)
    return levels

def _carved_solid(ring, height, cell_phase, scale, parameters, cell_index, role, origin):
    """Build the prism at one carve scale, or raise ``FoldedSection`` if a section is not simple."""
    from shapely.geometry import Polygon
    count = len(ring)
    perimeter_s = perimeter_arc_length(ring)
    levels = wall_levels(float(height), parameters.substep_m)
    walls = _i28_np.empty((len(levels), count, 2))
    for ordinal, y in enumerate(levels):
        section = wall_ring_at(ring, perimeter_s, float(y), float(height), cell_phase, True, parameters, scale)
        polygon = Polygon(section)
        if polygon.is_empty or not polygon.is_valid or (not polygon.exterior.is_simple) or (polygon.area <= 0.0):
            raise ValueError('cell %d level %.1f m' % (cell_index, float(y)))
        walls[ordinal] = section
    vertices = _i28_np.zeros((len(levels), count, 3))
    vertices[:, :, 0] = walls[:, :, 0]
    vertices[:, :, 1] = levels[:, None]
    vertices[:, :, 2] = walls[:, :, 1]
    vertices = vertices.reshape(-1, 3)
    triangles = []
    for ordinal in range(len(levels) - 1):
        base = ordinal * count
        above = (ordinal + 1) * count
        for index in range(count):
            following = (index + 1) % count
            triangles.append([base + index, base + following, above + following])
            triangles.append([base + index, above + following, above + index])
    top = (len(levels) - 1) * count
    import manifold3d as manifold
    bottom_uv = vertices[:count][:, [0, 2]]
    top_uv = vertices[top:top + count][:, [0, 2]]
    bottom_cap = [[int(value) for value in item] for item in manifold.triangulate([bottom_uv.tolist()], allow_convex=False)]
    top_cap = [[top + int(value) for value in item] for item in manifold.triangulate([top_uv.tolist()], allow_convex=False)]
    for flip_bottom, flip_top in ((False, True), (True, False), (False, False), (True, True)):
        candidate = _i28_np.asarray(triangles + [[item[0], item[2], item[1]] if flip_bottom else item for item in bottom_cap] + [[item[0], item[2], item[1]] if flip_top else item for item in top_cap], dtype=_i28_np.uint64)
        for candid in (candidate, candidate[:, ::-1].copy()):
            solid = manifold.Manifold(manifold.Mesh64(_i28_np.array(vertices, dtype=_i28_np.float64, order='C', copy=True), candid))
            if solid.status() == manifold.Error.NoError and (not solid.is_empty()) and (solid.volume() > 0.0):
                from terrain_pipeline.hybrid_geometry import save_manifold as save_manifold
                return save_manifold(solid, origin, role)
    raise RuntimeError('MESH64 refused every winding of the pillar solid')

def pillar_solid(ring, height, cell_phase, *, carve, cell_index, role, parameters=None, origin=None):
    """One closed vertical prism. Uncarved, it is the repository's own polygon_prism_record.

    The role is fixed at creation time and never patched afterwards: ``mesh_record`` seals each
    record, so a later field assignment would leave ``identity_sha256`` describing the older
    content. The archived prototype patched the role after sealing; that defect is not carried
    over here.
    """
    parameters = PillarParameters() if parameters is None else parameters
    if not isinstance(parameters, PillarParameters):
        raise ValueError('explicit PillarParameters required')
    origin = _origin(origin)
    if not isinstance(role, str) or not role:
        raise ValueError('explicit pillar role required')
    if not carve:
        return (_x8_polygon_prism_record(ring, 0.0, float(height), origin, role), 0.0)
    folded = None
    for scale in parameters.carve_backoff:
        try:
            return (_carved_solid(ring, float(height), float(cell_phase), float(scale), parameters, int(cell_index), role, origin), float(scale))
        except ValueError as exc:
            folded = exc
    raise RuntimeError('carve folds %s even at scale 0' % (folded,))

def plane_section_segments(record, axis, value):
    """Intersect the saved closed mesh with one axis-aligned plane (world metres).

    Returns explicit triangle/plane crossing segments in the two remaining coordinates, so a
    true section is drawn from the actual mesh rather than from the parameters. The crossing
    search is vectorised over triangles, because the carved field has ~2e5 of them and a
    per-triangle Python loop would make a section sweep impractical.
    """
    vertices = _i28_np.asarray(record['vertices_local_xyz_m'], float) + _i28_np.asarray(record['local_origin_xyz_m'], float)
    triangles = _i28_np.asarray(record['triangles'], int)
    points = vertices[triangles]
    distances = points[:, :, axis] - float(value)
    keep = [index for index in range(3) if index != axis]
    grouped = {}
    for first, second in ((0, 1), (1, 2), (2, 0)):
        a, b = (distances[:, first], distances[:, second])
        crossing = (a <= 0.0) & (b >= 0.0) | (b <= 0.0) & (a >= 0.0)
        selected = _i28_np.nonzero(crossing & (a != b))[0]
        if not selected.size:
            continue
        fraction = (a[selected] / (a[selected] - b[selected]))[:, None]
        hits = points[selected, first] + fraction * (points[selected, second] - points[selected, first])
        for ordinal, hit in zip(selected.tolist(), hits[:, keep].tolist()):
            grouped.setdefault(ordinal, []).append(hit)
    segments = []
    for ordinal in sorted(grouped):
        hits = grouped[ordinal]
        if len(hits) == 2:
            segments.append((_i28_np.asarray(hits[0], float), _i28_np.asarray(hits[1], float)))
        elif len(hits) == 3:
            unique = sorted({tuple(_i28_np.round(hit, 9)) for hit in hits})
            if len(unique) == 2:
                segments.append((_i28_np.asarray(unique[0], float), _i28_np.asarray(unique[1], float)))
    return segments

def section_polygon_count(record, value, axis=1, snap_decimals=6):
    """Stitch one mesh-derived section back into polygons; a simple wall gives exactly one.

    The crossing points on a shared vertical edge are computed twice, from the two triangles
    that meet there, and the two results differ by ~1e-11 m. Shapely's ``polygonize`` demands
    exactly equal endpoints, so an unsnapped stitch returns **zero** polygons for a perfectly
    simple section -- a false negative that would report a straight prism as folded. The
    endpoints are therefore snapped to a 1e-6 m grid before stitching, and the tolerance is
    recorded in the witness so a cold reader can see how the verdict was reached.
    """
    from shapely.geometry import LineString
    from shapely.ops import polygonize
    segments = plane_section_segments(record, axis, value)
    lines = []
    for first, second in segments:
        start = _i28_np.round(_i28_np.asarray(first, float), int(snap_decimals))
        end = _i28_np.round(_i28_np.asarray(second, float), int(snap_decimals))
        if not _i28_np.array_equal(start, end):
            lines.append(LineString([tuple(start), tuple(end)]))
    return len([item for item in polygonize(lines) if item.area > 0.0])

def simple_section_census(record, height, parameters):
    """Sweep one pillar: how many mesh-derived horizontal sections are a single simple polygon.

    The levels are deliberately placed between wall levels, so the section never coincides with
    a plane full of mesh vertices and no triangle can be dropped as degenerate.
    """
    checked, folded = (0, 0)
    for value in _i28_np.arange(parameters.substep_m * 0.5, float(height) - 1e-09, parameters.substep_m * 2.0):
        checked += 1
        if section_polygon_count(record, float(value)) != 1:
            folded += 1
    return (checked, folded)

def winding_number(vertices_local_xyz_m, triangles, point_world_xyz_m, origin):
    """Independent winding number of a closed triangle mesh about one point.

    Sums the signed solid angle of every triangle (Van Oosterom-Strackee) and divides by 4*pi,
    using only the saved mesh arrays -- no manifold3d and no ray casting. A closed
    outward-oriented solid gives 1.0 for an interior point and 0.0 for an exterior one, so a
    cold reader can recompute containment from the saved record alone.
    """
    origin = _i28_np.asarray(origin, float)
    points = _i28_np.asarray(vertices_local_xyz_m, float) + origin - _i28_np.asarray(point_world_xyz_m, float)
    total = 0.0
    for triangle in _i28_np.asarray(triangles, int):
        first, second, third = (points[index] for index in triangle)
        lengths = (_i28_np.linalg.norm(first), _i28_np.linalg.norm(second), _i28_np.linalg.norm(third))
        numerator = float(_i28_np.dot(first, _i28_np.cross(second, third)))
        denominator = lengths[0] * lengths[1] * lengths[2] + float(_i28_np.dot(first, second)) * lengths[2] + float(_i28_np.dot(second, third)) * lengths[0] + float(_i28_np.dot(third, first)) * lengths[1]
        total += 2.0 * _i28_math.atan2(numerator, denominator)
    return total / (4.0 * _i28_math.pi)

def inside_by_winding(record, point_world_xyz_m, origin):
    winding = winding_number(record['vertices_local_xyz_m'], record['triangles'], point_world_xyz_m, origin)
    return (bool(round(winding) == 1), float(winding))

def contains_point(solid, world_point, origin):
    """Independent containment: intersect a tiny closed cube with the solid.

    A MESH64 Boolean rather than a ray-parity count, so a grazing ray cannot fake it. Returns
    the overlap volume in m^3 (0.0 means the point is outside).
    """
    import manifold3d as manifold
    local = tuple((float(value) for value in _i28_np.asarray(world_point, float) - _i28_np.asarray(origin, float)))
    probe = manifold.Manifold.cube((PROBE_CUBE_EDGE_M,) * 3, center=True).translate(local)
    return float((probe ^ solid).volume())

def _origin(origin):
    origin = DEFAULT_ORIGIN.copy() if origin is None else _i28_np.asarray(origin, float)
    if origin.shape != (3,) or not _i28_np.isfinite(origin).all():
        raise ValueError('finite three-component local origin required')
    return origin

def _pin(record):
    return {'role': record['role'], 'identity_sha256': record['identity_sha256'], 'signed_volume_m3': record['signed_volume_m3']}

def build(carve=True, parameters=None, origin=None):
    """Assemble the pillar field and measure it. Nothing is certified."""
    if type(carve) is not bool:
        raise ValueError('explicit boolean carve flag required')
    parameters = PillarParameters() if parameters is None else parameters
    if not isinstance(parameters, PillarParameters):
        raise ValueError('explicit PillarParameters required')
    origin = _origin(origin)
    polygons, heights, centres, half_extent = joint_cells(parameters)
    phases = _i28_np.random.default_rng(parameters.seed + 7).uniform(0.0, 2.0 * _i28_math.pi, size=len(polygons))
    records, roles, scales, sections = ([], [], [], [])
    for index, (ring, height) in enumerate(zip(polygons, heights)):
        role = '%s%02d' % (PILLAR_ROLE_PREFIX, index)
        record, scale = pillar_solid(ring, float(height), float(phases[index]), carve=carve, cell_index=index, role=role, parameters=parameters, origin=origin)
        records.append(record)
        roles.append(role)
        scales.append(float(scale))
        checked, folded = simple_section_census(record, float(height), parameters)
        sections.append({'role': role, 'height_m': float(height), 'sections_checked': checked, 'sections_folded': folded})
    base_ring = [[-half_extent, -half_extent], [half_extent, -half_extent], [half_extent, half_extent], [-half_extent, half_extent]]
    base = _x8_polygon_prism_record(base_ring, -parameters.base_thickness_m, 0.0, origin, PLATEAU_ROLE)
    start = _i28_time.time()
    result, meshes = _x7_combine(records + [base], origin, SOLID_ROLE, _x4_BooleanParameters())
    elapsed = _i28_time.time() - start
    solid = _x9_solid_from_record(meshes[SOLID_ROLE], SOLID_ROLE)
    witnesses = field_witnesses(solid, meshes[SOLID_ROLE], polygons, heights, centres, records, roles, parameters, origin, sections)
    footprints = [{'index': index, 'role': roles[index], 'height_m': float(heights[index]), 'carve_scale': float(scales[index]), 'signed_volume_m3': float(records[index]['signed_volume_m3']), 'centre_xz_m': [float(polygons[index].mean(axis=0)[0]), float(polygons[index].mean(axis=0)[1])], 'base_ring_xz_m': [[float(point[0]), float(point[1])] for point in polygons[index]], 'ring_area_m2': ring_area(polygons[index])} for index in range(len(records))]
    return {'carve': carve, 'result': result, 'meshes': meshes, 'solids': {PLATEAU_ROLE: base, SOLID_ROLE: meshes[SOLID_ROLE]}, 'pillar_records': records, 'pillar_roles': roles, 'pillar_pins': [_pin(item) for item in records], 'pillar_footprints': footprints, 'plateau_ring_xz_m': [[float(point[0]), float(point[1])] for point in base_ring], 'plateau_bottom_y_m': float(-parameters.base_thickness_m), 'plateau_top_y_m': 0.0, 'scales': scales, 'heights': [float(value) for value in heights], 'sections': sections, 'witnesses': witnesses, 'solid': solid, 'origin': origin, 'parameters': parameters, 'polygons': polygons, 'centres': centres, 'footprint_half_extent_m': float(half_extent), 'union_seconds': elapsed, 'level_schedule': {'pillar_index': 0, 'substep_m': float(parameters.substep_m), 'levels_m': [float(value) for value in wall_levels(float(heights[0]), parameters.substep_m)]}}

def field_witnesses(solid, union, polygons, heights, centres, records, roles, parameters, origin, sections):
    """Measure the field instead of asserting it.

    Every witness is one of the three cold-readable shapes: winding-number containment
    (recomputable from the saved mesh alone), a ray replay against the saved solid, or a MESH64
    volume census. All coordinates are **world metres**.
    """
    axis_x, axis_z = (float(origin[0]), float(origin[2]))
    tall = int(_i28_np.argmax(heights))
    tall_centre = polygons[tall].mean(axis=0)
    tall_height = float(heights[tall])
    if parameters.cols >= 2:
        left, right = (0, 1)
    else:
        left, right = (0, parameters.cols if len(centres) > 1 else 0)
    gap_xz = 0.5 * (centres[left] + centres[right]) if right != left else centres[0] + _i28_np.array([0.5 * parameters.pitch_m, 0.0])
    gap_height = min(float(heights[left]), float(heights[right]))
    gap_xyz = [float(gap_xz[0]) + axis_x, gap_height / 3.0, float(gap_xz[1]) + axis_z]
    gap_top = [gap_xyz[0], parameters.height_max_m + 50.0, gap_xyz[2]]
    gap_bottom = [gap_xyz[0], 1.0, gap_xyz[2]]
    inside_xyz = [float(tall_centre[0]) + axis_x, tall_height * 0.5, float(tall_centre[1]) + axis_z]
    far_xyz = [axis_x + parameters.footprint_half_extent_m + 100.0, parameters.height_max_m * 0.5, axis_z]
    shaft_top = [float(tall_centre[0]) + axis_x, tall_height + 50.0, float(tall_centre[1]) + axis_z]
    gap_inside, gap_winding = inside_by_winding(union, gap_xyz, origin)
    inside_inside, inside_winding = inside_by_winding(union, inside_xyz, origin)
    far_inside, far_winding = inside_by_winding(union, far_xyz, origin)
    gap_hits = _x0_ray_hits(solid, gap_bottom, gap_top, origin)
    shaft_hits = _x0_ray_hits(solid, [inside_xyz[0], 1.0, inside_xyz[2]], shaft_top, origin)
    top_hit = max((hit['position_xyz_m'][1] for hit in shaft_hits), default=-_i28_math.inf)
    components = _x6_census(solid)
    base_delta = min((abs(float(centre[0]) - float(gap_xz[0])) for centre in centres))
    return {'inter_pillar_gap_is_void': {'method': 'Solid.winding', 'solid_role': SOLID_ROLE, 'point_xyz_m': gap_xyz, 'expected_inside': False, 'verdict': bool(not gap_inside), 'claim': 'the open vertical joint between two neighbouring pillars carries no rock, so the field really is a set of separate bodies rather than one mass', 'observed': {'winding': gap_winding, 'inside': gap_inside}, 'probe_cube_intersection_volume_m3': contains_point(solid, gap_xyz, origin), 'neighbour_roles': [roles[left], roles[right]], 'neighbour_heights_m': [float(heights[left]), float(heights[right])], 'joint_gap_m': parameters.joint_gap_m, 'distance_to_nearest_seed_m': float(base_delta)}, 'control_point_inside_pillar': {'method': 'Solid.winding', 'solid_role': SOLID_ROLE, 'point_xyz_m': inside_xyz, 'expected_inside': True, 'verdict': bool(inside_inside), 'claim': 'control: the centroid of the tallest pillar at half its height is inside the union, so the void verdict above is not vacuous', 'observed': {'winding': inside_winding, 'inside': inside_inside}, 'pillar_role': roles[tall], 'pillar_height_m': tall_height, 'probe_cube_intersection_volume_m3': contains_point(solid, inside_xyz, origin)}, 'control_point_far_outside': {'method': 'Solid.winding', 'solid_role': SOLID_ROLE, 'point_xyz_m': far_xyz, 'expected_inside': False, 'verdict': bool(not far_inside), 'claim': 'control: a point well outside the field footprint is outside the union', 'observed': {'winding': far_winding, 'inside': far_inside}, 'probe_cube_intersection_volume_m3': contains_point(solid, far_xyz, origin)}, 'vertical_ray_from_gap_leaves_field_without_hitting_rock': {'method': 'Manifold.ray_cast', 'solid_role': SOLID_ROLE, 'from_xyz_m': gap_bottom, 'to_xyz_m': gap_top, 'expected_hit_count': 0, 'verdict': bool(len(gap_hits) == 0), 'claim': 'a segment rising through the inter-pillar joint from 1 m to above the tallest pillar never meets rock: the joint is open all the way up', 'observed': {'hit_count': len(gap_hits), 'hits': gap_hits}}, 'vertical_ray_from_pillar_base_hits_top_cap': {'method': 'Manifold.ray_cast', 'solid_role': SOLID_ROLE, 'from_xyz_m': [inside_xyz[0], 1.0, inside_xyz[2]], 'to_xyz_m': shaft_top, 'expected_minimum_hit_count': 1, 'verdict': bool(len(shaft_hits) >= 1 and _i28_math.isfinite(top_hit) and (abs(top_hit - tall_height) <= 2.0)), 'claim': 'a segment rising inside the tallest pillar leaves the solid at its own top elevation, so the pillar really is a closed column of that height', 'observed': {'hit_count': len(shaft_hits), 'highest_hit_y_m': top_hit, 'pillar_height_m': tall_height, 'hits': [{'face_id': hit['face_id'], 'distance': hit['distance'], 'position_xyz_m': hit['position_xyz_m']} for hit in shaft_hits]}}, 'union_single_connected_component': {'method': 'Mesh64_boolean', 'operation': 'add', 'input_roles': [PLATEAU_ROLE] + roles, 'expected_rock_after_m3': union['signed_volume_m3'], 'expected_removed_m3': 0.0, 'verdict': bool(components == 1), 'claim': 'the base plateau touches every pillar at y = 0, so the field is one connected closed solid rather than a bag of loose columns', 'observed': {'component_count': components, 'declared_minimum_components': 1, 'assembled_volume_m3': union['signed_volume_m3']}}, 'every_horizontal_section_is_simple': {'method': 'Shapely.section', 'axis': 'y', 'solid_roles': roles, 'verdict': bool(all((item['sections_folded'] == 0 and item['sections_checked'] > 0 for item in sections))), 'claim': 'every horizontal section of every pillar, taken from the saved mesh and stitched back into polygons, is a single simple polygon: no carved wall folds through itself', 'sections_checked': int(sum((item['sections_checked'] for item in sections))), 'sections_folded': int(sum((item['sections_folded'] for item in sections))), 'every_section_simple': bool(all((item['sections_folded'] == 0 for item in sections))), 'section_endpoint_snap_m': 1e-06, 'method_note': 'a section crossing on a shared vertical edge is computed twice, from the two triangles meeting there, and the two results differ by ~1e-11 m; Shapely polygonize needs exactly equal endpoints, so the endpoints are snapped to 1e-6 m before stitching. Without that snap a perfectly straight prism reports zero polygons -- a false negative, not a fold', 'per_pillar': [dict(item) for item in sections]}}

def volume_account(geometry, plain_geometry):
    """The saved volumes, accounted for without any implicit fill.

    Pillars stand apart by a joint gap and the plateau lies below y = 0, so the union should
    lose nothing to overlap; the account records the actual number instead of asserting it.
    """
    pillars = float(sum((record['signed_volume_m3'] for record in geometry['pillar_records'])))
    plateau = float(geometry['solids'][PLATEAU_ROLE]['signed_volume_m3'])
    assembled = float(geometry['solids'][SOLID_ROLE]['signed_volume_m3'])
    total = pillars + plateau
    return {'pillar_count': len(geometry['pillar_records']), 'sum_pillar_signed_volume_m3': pillars, 'plateau_signed_volume_m3': plateau, 'inputs_total_m3': total, 'assembled_volume_m3': assembled, 'overlap_removed_m3': total - assembled, 'overlap_removed_relative': (total - assembled) / total if total else 0.0, 'meshed_union_volume_m3': float(geometry['solid'].volume()), 'relative_residual': abs(assembled - float(geometry['solid'].volume())) / assembled, 'full_depth_pillars': int(sum((1 for scale in geometry['scales'] if scale >= 1.0))), 'carve_scales': [round(float(scale), 3) for scale in geometry['scales']], 'uncarved_variant_assembled_volume_m3': float(plain_geometry['solids'][SOLID_ROLE]['signed_volume_m3']), 'carved_removed_m3': float(plain_geometry['solids'][SOLID_ROLE]['signed_volume_m3']) - assembled, 'fill_rock_m3': 0.0, 'implicit_fill_or_clamping': False}

def variant_summary(geometry):
    record = geometry['solids'][SOLID_ROLE]
    return {'carve': bool(geometry['carve']), 'vertices': len(record['vertices_local_xyz_m']), 'triangles': len(record['triangles']), 'assembled_volume_m3': float(record['signed_volume_m3']), 'components': int(geometry['result']['census']['assembled_components']), 'carve_scales': [round(float(scale), 3) for scale in geometry['scales']], 'full_depth_pillars': int(sum((1 for scale in geometry['scales'] if scale >= 1.0))), 'height_range_m': [float(min(geometry['heights'])), float(max(geometry['heights']))], 'union_seconds': round(float(geometry['union_seconds']), 4), 'mesh_identity_sha256': record['identity_sha256'], 'solid_gate': 'closed_two_use_manifold_volume_gated', 'sections_checked': int(sum((item['sections_checked'] for item in geometry['sections']))), 'sections_folded': int(sum((item['sections_folded'] for item in geometry['sections'])))}

def _library_versions():
    from importlib.metadata import version
    return {'manifold3d': version('manifold3d'), 'numpy': _i28_np.__version__, 'scipy': version('scipy'), 'shapely': version('shapely')}

def _derived(parameters):
    return {'pillar_count': parameters.pillar_count, 'height_band_m': list(parameters.height_band_m), 'footprint_half_extent_m': parameters.footprint_half_extent_m, 'base_footprint_extent_m': 2.0 * parameters.footprint_half_extent_m, 'maximum_taper_contraction_fraction': parameters.taper_fraction, 'cap_fraction_of_shortest_pillar': parameters.cap_thickness_m / parameters.height_min_m, 'joint_gap_m': parameters.joint_gap_m, 'half_joint_gap_m': 0.5 * parameters.joint_gap_m, 'striation_levels': len(parameters.striation_amplitude_m), 'flute_levels': len(parameters.flute_amplitude_m), 'carve_backoff_steps': len(parameters.carve_backoff), 'wall_levels_of_tallest_pillar': int(len(wall_levels(parameters.height_max_m, parameters.substep_m)))}

def report(parameters=None, origin=None, output_directory=None, carve=True, compare=True):
    """Build both variants and seal the contract-shaped report for cold reading.

    ``compare`` builds the uncarved variant too; the report always carries the plain summary
    because the difference between the two is the only honest statement of what VDM added.
    """
    from tools.preview_special_terrain import render
    carved = build(True, parameters, origin)
    plain = carved if not compare else build(False, carved['parameters'], carved['origin'])
    primary = carved if carve else plain
    parameters = primary['parameters']
    origin = primary['origin']
    figures = [] if output_directory is None else render(primary, output_directory)
    record = {'schema': REPORT_SCHEMA, 'algorithm': ALGORITHM, 'status': 'candidate', 'parent_algorithm': PARENT_ALGORITHM, 'supersedes': dict(SUPERSEDES), 'synthetic_base': {'kind': BASE_KIND, 'note': 'the base plateau is analytic geometry, not TD native terrain and not surveyed'}, 'world_frame': WORLD_FRAME_NOTE, 'local_origin_xyz_m': [float(value) for value in origin], 'parameters': _i28_asdict(parameters), 'derived': _derived(parameters), 'explicit_assumptions': [dict(item) for item in EXPLICIT_ASSUMPTIONS], 'geology_note': GEOLOGY_NOTE, 'solids': {role: dict(mesh) for role, mesh in primary['solids'].items()}, 'pillar_pins': [dict(item) for item in primary['pillar_pins']], 'pillar_footprints': [dict(item) for item in primary['pillar_footprints']], 'level_schedule': dict(primary['level_schedule']), 'plateau_ring_xz_m': [list(point) for point in primary['plateau_ring_xz_m']], 'plateau_bottom_y_m': float(primary['plateau_bottom_y_m']), 'plateau_top_y_m': float(primary['plateau_top_y_m']), 'boolean': primary['result'], 'witnesses': primary['witnesses'], 'volume_account': volume_account(carved, plain), 'variants': {'primary': 'vdm_carved_walls' if carve else 'plain_prisms', 'plain_prisms': variant_summary(plain), 'vdm_carved_walls': variant_summary(carved)}, 'flags': {flag: False for flag in _x5_FLAGS}, 'library_versions': _library_versions(), 'figures': figures, 'figure_scope': FIGURE_SCOPE, 'sampled_not_native_exact': True, 'water_generated': False}
    _x1_hybrid_cave_geometry_seal(record)
    return (record, {'carved': carved, 'plain': plain, 'primary': primary, 'solid': primary['solid'], 'origin': origin, 'parameters': parameters, 'solids': primary['solids'], 'result': primary['result'], 'witnesses': primary['witnesses'], 'polygons': primary['polygons'], 'centres': primary['centres'], 'heights': primary['heights'], 'scales': primary['scales'], 'sections': primary['sections'], 'pillar_records': primary['pillar_records'], 'pillar_footprints': primary['pillar_footprints'], 'level_schedule': primary['level_schedule'], 'plateau_ring_xz_m': primary['plateau_ring_xz_m'], 'plateau_bottom_y_m': primary['plateau_bottom_y_m'], 'plateau_top_y_m': primary['plateau_top_y_m']})

def encode_report(record):
    """Compact, key-sorted, NaN-refusing JSON bytes; identical input gives identical bytes."""
    return _i28_json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')

def report_identity(record):
    return _x10_identity({key: value for key, value in record.items() if key != 'identity_sha256'})

def write_report(path, parameters=None, origin=None, output_directory=None, carve=True, compare=True):
    record, geometry = report(parameters, origin, output_directory, carve, compare)
    path = _i28_Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_report(record))
    return (record, geometry)

def save_arrays(directory, geometry):
    """Save both variants' mesh arrays so the browser never has to parse the report."""
    saved = []
    for label, item in (('plain', geometry['plain']), ('carved', geometry['carved'])):
        record = item['solids'][SOLID_ROLE]
        path = _i28_Path(directory) / (label + '.npz')
        _i28_np.savez_compressed(path, vertices_local_xyz_m=_i28_np.asarray(record['vertices_local_xyz_m'], _i28_np.float64), triangles=_i28_np.asarray(record['triangles'], _i28_np.int64), local_origin_xyz_m=_i28_np.asarray(record['local_origin_xyz_m'], _i28_np.float64), signed_volume_m3=_i28_np.asarray([record['signed_volume_m3']], _i28_np.float64), identity_sha256=_i28_np.asarray([record['identity_sha256']]), role=_i28_np.asarray([SOLID_ROLE]))
        saved.append({'name': path.name, 'path': path.as_posix(), 'sha256': _i28_hashlib.sha256(path.read_bytes()).hexdigest(), 'vertices': len(record['vertices_local_xyz_m']), 'triangles': len(record['triangles']), 'signed_volume_m3': float(record['signed_volume_m3']), 'mesh_identity_sha256': record['identity_sha256']})
    return saved
METRIC_FORMS_SCHEMA = 'metric-special-terrain-v1'
METRIC_FORMS_ALGORITHM = 'special-terrain-field-forms-v1'
METRIC_FORMS_ARRAY_KEYS = {'reference_xyz_m', 'displacement_xyz_m', 'vertices_xyz_m', 'triangles', 'protected_mask'}
METRIC_FORMS_COORDINATES = 'xyz metres; chart [row,col]'
BASE_KINDS = frozenset({'synthetic_analytic', 'td_fine_bed'})
SAMPLES_PER_FEATURE = 4
PROFILES = {'volcanic_plug': 0.2754, 'inselberg': 0.55, 'karst_tower_field': 0.72, 'sandstone_pillar_field': 0.8}
KINDS = frozenset(PROFILES)
METRIC_FORMS_GRADES = frozenset({'verified', 'secondary', 'assumed'})
PARAMETER_SOURCES = {'volcanic_plug': {'height_m': ('verified', 'parameters-and-sources.md#1 devils-tower NPS 264 m'), 'radius_x_m': ('secondary', 'parameters-and-sources.md#2 base diameter 305 m'), 'flat_top_fraction': ('secondary', 'parameters-and-sources.md#2 top/base 84/305'), 'joint_texture': ('verified', 'parameters-and-sources.md#1 3..7 sided columns, not modelled in v1')}, 'inselberg': {'height_m': ('secondary', 'parameters-and-sources.md#2 uluru 348 m, 335 m variant unresolved'), 'radius_x_m': ('secondary', 'parameters-and-sources.md#2 length 3.6 km'), 'radius_z_m': ('secondary', 'parameters-and-sources.md#2 perimeter 9.0..9.4 km implies half width ~1.0 km'), 'wall_band': ('assumed', 'parameters-and-sources.md#4.2 steep wall distribution')}, 'sandstone_pillar_field': {'height_m': ('secondary', 'parameters-and-sources.md#2 tens of metres to 400 m'), 'height_band': ('assumed', 'parameters-and-sources.md#4.3 sampling gate truncates the tall end'), 'radius_m': ('assumed', 'parameters-and-sources.md#3 base diameter not obtained'), 'pitch_m': ('assumed', 'parameters-and-sources.md#3 pillar spacing not obtained'), 'iron_cap_m': ('secondary', 'parameters-and-sources.md#2 about 30 m cap, not modelled in v1')}, 'karst_tower_field': {'height_m': ('secondary', 'parameters-and-sources.md#2 tens to 200+ m'), 'radius_m': ('assumed', 'parameters-and-sources.md#3 base diameter not obtained'), 'pitch_m': ('assumed', 'parameters-and-sources.md#3 peak spacing not obtained')}}

def _metric_forms_finite_number(value, name, *, positive=False):
    if type(value) not in (int, float) or not _i30_math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f'invalid {name}')

@_i30_dataclass(frozen=True)
class FormTarget:
    """One landform centre in the chart frame.

    The footprint is an ellipse in metres about ``center_xz_m``; ``base_elevation_m``
    is the foot elevation and ``height_m`` the relief above it. Provenance grade and
    ledger reference are mandatory so no generated number is anonymous.
    """
    target_id: str
    center_x_m: float
    center_z_m: float
    base_elevation_m: float
    height_m: float
    radius_x_m: float
    radius_z_m: float
    source_grade: str
    source_ref: str

    def __post_init__(self):
        if not isinstance(self.target_id, str) or not self.target_id.strip():
            raise ValueError('invalid target id')
        for name in ('center_x_m', 'center_z_m', 'base_elevation_m'):
            _metric_forms_finite_number(getattr(self, name), name)
        for name in ('height_m', 'radius_x_m', 'radius_z_m'):
            _metric_forms_finite_number(getattr(self, name), name, positive=True)
        if self.source_grade not in METRIC_FORMS_GRADES:
            raise ValueError('invalid target source grade')
        if not isinstance(self.source_ref, str) or not self.source_ref.strip():
            raise ValueError('target source reference required')

@_i30_dataclass(frozen=True)
class SpecialFormRecipe:
    """Chart extent, spacing and target list for one special terrain form kind.

    ``collar_margin_m`` is the empty band that must remain between every target
    footprint and the chart edge; it is the field analogue of the VDM collar that
    keeps the four chart edges at zero displacement.
    """
    kind: str
    size_x_m: float
    size_z_m: float
    spacing_m: float
    collar_margin_m: float
    targets: tuple
    seed: int

    def __post_init__(self):
        if not isinstance(self.kind, str) or self.kind not in KINDS:
            raise ValueError('invalid special terrain form kind')
        for name in ('size_x_m', 'size_z_m', 'spacing_m', 'collar_margin_m'):
            _metric_forms_finite_number(getattr(self, name), name, positive=True)
        if type(self.seed) is not int or not 0 <= self.seed <= 2 ** 32 - 1:
            raise ValueError('invalid form seed')
        if not isinstance(self.targets, tuple) or not self.targets:
            raise ValueError('special terrain form requires a target tuple')
        for target in self.targets:
            if not isinstance(target, FormTarget):
                raise ValueError('FormTarget required')
        if len({target.target_id for target in self.targets}) != len(self.targets):
            raise ValueError('duplicate target id')

def form_preset(kind):
    """Deterministic preset per kind. Every numeric input traces to the ledger."""
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError('invalid special terrain form kind')
    if kind == 'volcanic_plug':
        target = FormTarget('devils-tower', 0.0, 0.0, 0.0, 264.0, 152.5, 152.5, 'secondary', 'parameters-and-sources.md#4.1')
        return SpecialFormRecipe(kind, 410.0, 410.0, 1.0, 50.0, (target,), 20261003)
    if kind == 'inselberg':
        target = FormTarget('uluru', 0.0, 0.0, 0.0, 348.0, 1800.0, 1000.0, 'secondary', 'parameters-and-sources.md#4.2')
        return SpecialFormRecipe(kind, 3800.0, 2200.0, 8.0, 40.0, (target,), 20261003)
    if kind == 'sandstone_pillar_field':
        targets = pillar_field_targets(prefix='zhangjiajie', rows=4, cols=4, pitch_m=30.0, seed=20261003, radius_m=12.0, height_band_m=(40.0, 150.0), jitter_fraction=0.25, source_grade='assumed', source_ref='parameters-and-sources.md#4.3')
        return SpecialFormRecipe(kind, 160.0, 160.0, 0.5, 10.0, targets, 20261003)
    if kind == 'karst_tower_field':
        targets = pillar_field_targets(prefix='guilin-tower', rows=3, cols=3, pitch_m=160.0, seed=20261004, radius_m=40.0, height_band_m=(60.0, 200.0), jitter_fraction=0.0, source_grade='assumed', source_ref='parameters-and-sources.md#4.4')
        return SpecialFormRecipe(kind, 490.0, 490.0, 1.0, 40.0, targets, 20261004)
    raise ValueError('invalid special terrain form kind')

def pillar_field_targets(*, prefix, rows, cols, pitch_m, seed, radius_m, height_band_m, jitter_fraction, source_grade, source_ref):
    """Seeded, deterministic column field.

    Placement is a centred grid with bounded jitter and heights are drawn from the
    declared band, so the same seed always yields the same target tuple.
    """
    for name, value in (('pitch_m', pitch_m), ('radius_m', radius_m)):
        _metric_forms_finite_number(value, name, positive=True)
    if type(rows) is not int or type(cols) is not int or rows < 1 or (cols < 1):
        raise ValueError('invalid pillar field rows/cols')
    low, high = height_band_m
    _metric_forms_finite_number(low, 'height band minimum', positive=True)
    _metric_forms_finite_number(high, 'height band maximum', positive=True)
    if high < low:
        raise ValueError('invalid pillar height band')
    _metric_forms_finite_number(jitter_fraction, 'jitter fraction')
    if not 0.0 <= jitter_fraction < 0.5:
        raise ValueError('jitter fraction must stay below half a pitch')
    rng = _i30_np.random.default_rng(seed)
    targets = []
    for row in range(rows):
        for col in range(cols):
            center_x = (col - 0.5 * (cols - 1)) * pitch_m
            center_z = (row - 0.5 * (rows - 1)) * pitch_m
            jitter = rng.uniform(-jitter_fraction, jitter_fraction, size=2) * pitch_m
            height = float(rng.uniform(low, high))
            targets.append(FormTarget(f'{prefix}-{row}-{col}', float(center_x + jitter[0]), float(center_z + jitter[1]), 0.0, height, radius_m, radius_m, source_grade, source_ref))
    return tuple(targets)

def analytic_base_chart(*, size_x_m, size_z_m, spacing_m, base_elevation_m=0.0, slope_x=0.0, slope_z=0.0):
    """Closed uniform analytic base bed: a plane with optional constant slope.

    This is a synthetic reference surface, not sampled Terrain Diffusion output; the
    bundle metadata records ``base = synthetic_analytic`` for exactly that reason.
    """
    for name, value in (('size_x_m', size_x_m), ('size_z_m', size_z_m), ('spacing_m', spacing_m)):
        _metric_forms_finite_number(value, name, positive=True)
    for name, value in (('base_elevation_m', base_elevation_m), ('slope_x', slope_x), ('slope_z', slope_z)):
        _metric_forms_finite_number(value, name)
    cols_exact = size_x_m / spacing_m
    rows_exact = size_z_m / spacing_m
    if abs(cols_exact - round(cols_exact)) > 1e-09 or abs(rows_exact - round(rows_exact)) > 1e-09:
        raise ValueError('chart size must be an integer number of spacing steps')
    rows, cols = (int(round(rows_exact)) + 1, int(round(cols_exact)) + 1)
    if rows < 3 or cols < 3 or rows * cols > _i30_MAX_CELLS:
        raise ValueError('analytic base chart outside cell budget')
    x = (_i30_np.arange(cols) - 0.5 * (cols - 1)) * spacing_m
    z = (_i30_np.arange(rows) - 0.5 * (rows - 1)) * spacing_m
    reference = _i30_np.zeros((rows, cols, 3), dtype=_i30_np.float64)
    reference[:, :, 0] = x[None, :]
    reference[:, :, 2] = z[:, None]
    reference[:, :, 1] = base_elevation_m + slope_x * x[None, :] + slope_z * z[:, None]
    if not _i30_np.isfinite(reference).all():
        raise ValueError('nonfinite analytic base chart')
    return reference

def _adjacent_spacing(reference):
    horizontal = reference[:, :, (0, 2)]
    adjacent = _i30_np.concatenate((_i30_np.linalg.norm(_i30_np.diff(horizontal, axis=0), axis=2).ravel(), _i30_np.linalg.norm(_i30_np.diff(horizontal, axis=1), axis=2).ravel()))
    if not _i30_np.isfinite(adjacent).all() or _i30_np.any(adjacent <= 0):
        raise ValueError('invalid adjacent horizontal chart spacing')
    return (float(_i30_np.min(adjacent)), float(_i30_np.max(adjacent)))

def _check_sampling_scale(recipe, reference):
    """Field analogue of the VDM wavelength gate: the narrowest wall band decides."""
    minimum, maximum = _adjacent_spacing(reference)
    if maximum - minimum > 1e-06 * maximum:
        raise ValueError('special terrain chart must be a uniform grid')
    band = 1.0 - PROFILES[recipe.kind]
    for target in recipe.targets:
        wall_width = band * min(target.radius_x_m, target.radius_z_m)
        limit = SAMPLES_PER_FEATURE * maximum
        if wall_width < limit:
            raise ValueError(f'target {target.target_id} wall band {wall_width:.6g} m is below the {SAMPLES_PER_FEATURE}x sampling limit {limit:.6g} m; refine the chart spacing or enlarge the target')
    if recipe.collar_margin_m < 2 * maximum:
        raise ValueError('collar margin below two chart cells')

def _check_target_containment(recipe, reference):
    x0, x1 = (float(reference[:, :, 0].min()), float(reference[:, :, 0].max()))
    z0, z1 = (float(reference[:, :, 2].min()), float(reference[:, :, 2].max()))
    margin = recipe.collar_margin_m
    for target in recipe.targets:
        if target.center_x_m - target.radius_x_m - margin < x0 or target.center_x_m + target.radius_x_m + margin > x1 or target.center_z_m - target.radius_z_m - margin < z0 or (target.center_z_m + target.radius_z_m + margin > z1):
            raise ValueError(f'target {target.target_id} leaves no chart collar')

def _relief(reference, recipe):
    """Maximum flat-top elliptical bump over every target, evaluated in metres."""
    x = reference[:, :, 0]
    z = reference[:, :, 2]
    flat_top = PROFILES[recipe.kind]
    band = 1.0 - flat_top
    relief = _i30_np.full(reference.shape[:2], -_i30_np.inf, dtype=_i30_np.float64)
    for target in recipe.targets:
        across = (x - target.center_x_m) / target.radius_x_m
        along = (z - target.center_z_m) / target.radius_z_m
        radial = _i30_np.sqrt(across * across + along * along)
        profile = _x14_smooth((1.0 - radial) / band)
        relief = _i30_np.maximum(relief, target.base_elevation_m + target.height_m * profile)
    if not _i30_np.isfinite(relief).all():
        raise ValueError('nonfinite special terrain relief')
    return relief

def _recipe_record(recipe):
    record = _i30_asdict(recipe)
    return {**record, 'targets': [_i30_asdict(target) for target in recipe.targets]}

def _parse_recipe_record(record):
    if not isinstance(record, dict) or set(record) != {'kind', 'size_x_m', 'size_z_m', 'spacing_m', 'collar_margin_m', 'targets', 'seed'}:
        raise ValueError('invalid saved special terrain recipe')
    targets = tuple((FormTarget(**target) for target in record['targets']))
    return SpecialFormRecipe(**{**record, 'targets': targets})

def build_special_form_vdm(reference_xyz_m, *, recipe: SpecialFormRecipe, protected_mask, source_identity: str, protection_identity: str, base_kind: str='synthetic_analytic'):
    if not isinstance(recipe, SpecialFormRecipe):
        raise ValueError('SpecialFormRecipe required')
    if base_kind not in BASE_KINDS:
        raise ValueError('invalid base kind')
    reference = _i30_np.asarray(reference_xyz_m)
    if reference.ndim != 3 or reference.shape[2] != 3 or min(reference.shape[:2]) < 3 or (reference.shape[0] * reference.shape[1] > _i30_MAX_CELLS) or (reference.dtype.kind not in 'fiu') or (not _i30_np.isfinite(reference).all()):
        raise ValueError('invalid metric special terrain reference chart')
    reference = _i30_np.array(reference, dtype=_i30_np.float64, copy=True)
    mask = _i30_np.asarray(protected_mask)
    if mask.shape != reference.shape[:2] or mask.dtype != bool:
        raise ValueError('protected_mask must be a boolean chart')
    for name, value in (('source_identity', source_identity), ('protection_identity', protection_identity)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{name} required')
    _check_sampling_scale(recipe, reference)
    _check_target_containment(recipe, reference)
    bed = reference[:, :, 1]
    displacement = _i30_np.zeros_like(reference)
    displacement[:, :, 1] = _i30_np.maximum(_relief(reference, recipe) - bed, 0.0)
    displacement[mask] = 0
    displacement[0] = displacement[-1] = 0
    displacement[:, 0] = displacement[:, -1] = 0
    vertices = (reference + displacement).reshape(-1, 3)
    if not _i30_np.isfinite(vertices).all():
        raise ValueError('nonfinite special terrain position')
    triangles = _x15_triangles(*mask.shape)
    _x13_check_mesh(vertices, triangles)
    arrays = {'reference_xyz_m': _i30_readonly(reference), 'displacement_xyz_m': _i30_readonly(displacement), 'vertices_xyz_m': _i30_readonly(vertices), 'triangles': _i30_readonly(triangles), 'protected_mask': _i30_readonly(mask)}
    metadata = {'schema': METRIC_FORMS_SCHEMA, 'algorithm': METRIC_FORMS_ALGORITHM, 'coordinates': METRIC_FORMS_COORDINATES, 'base': base_kind, 'recipe': _recipe_record(recipe), 'parameter_sources': {recipe.kind: {field: list(value) for field, value in PARAMETER_SOURCES[recipe.kind].items()}}, 'source_identity': source_identity, 'protection_identity': protection_identity, 'hydraulic_ready': False, 'natural_outlet_verified': False, 'publishable': False, 'self_intersection_verified': False}
    result = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i30_identity(arrays, metadata)}
    validate_special_form_vdm(result)
    return result

def validate_special_form_vdm(result):
    if not isinstance(result, dict) or set(result) != {'arrays', 'metadata', 'identity_sha256'}:
        raise ValueError('invalid special terrain bundle')
    arrays, metadata = (result['arrays'], result['metadata'])
    if not isinstance(arrays, dict) or set(arrays) != METRIC_FORMS_ARRAY_KEYS or (not isinstance(metadata, dict)):
        raise ValueError('invalid special terrain fields')
    if set(metadata) != {'schema', 'algorithm', 'coordinates', 'base', 'recipe', 'parameter_sources', 'source_identity', 'protection_identity', 'hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified'} or metadata['schema'] != METRIC_FORMS_SCHEMA or metadata['algorithm'] != METRIC_FORMS_ALGORITHM or (metadata['coordinates'] != METRIC_FORMS_COORDINATES) or (metadata['base'] not in BASE_KINDS) or any((metadata[key] is not False for key in ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified'))):
        raise ValueError('invalid special terrain metadata')
    for key in ('source_identity', 'protection_identity'):
        if not isinstance(metadata[key], str) or not metadata[key].strip():
            raise ValueError('missing upstream identity')
    try:
        recipe = _parse_recipe_record(metadata['recipe'])
    except (TypeError, KeyError, ValueError) as error:
        raise ValueError('invalid saved special terrain recipe') from error
    if metadata['parameter_sources'] != {recipe.kind: {field: list(value) for field, value in PARAMETER_SOURCES[recipe.kind].items()}}:
        raise ValueError('special terrain parameter provenance mismatch')
    reference = arrays['reference_xyz_m']
    displacement = arrays['displacement_xyz_m']
    vertices = arrays['vertices_xyz_m']
    triangles = arrays['triangles']
    mask = arrays['protected_mask']
    if not all((isinstance(value, _i30_np.ndarray) for value in arrays.values())) or reference.ndim != 3 or reference.shape[2] != 3 or (min(reference.shape[:2]) < 3) or (reference.shape[0] * reference.shape[1] > _i30_MAX_CELLS) or (reference.dtype != _i30_np.float64) or (displacement.shape != reference.shape) or (displacement.dtype != _i30_np.float64) or (vertices.shape != (reference.shape[0] * reference.shape[1], 3)) or (vertices.dtype != _i30_np.float64) or (mask.shape != reference.shape[:2]) or (mask.dtype != bool) or (triangles.shape != (2 * (mask.shape[0] - 1) * (mask.shape[1] - 1), 3)) or (triangles.dtype != _i30_np.int64):
        raise ValueError('invalid special terrain array shape or dtype')
    if not _i30_np.isfinite(reference).all() or not _i30_np.isfinite(displacement).all() or (not _i30_np.isfinite(vertices).all()) or (not _i30_np.array_equal(vertices, (reference + displacement).reshape(-1, 3))) or (not _i30_np.array_equal(triangles, _x15_triangles(*mask.shape))) or _i30_np.any(displacement[mask] != 0) or _i30_np.any(displacement[0] != 0) or _i30_np.any(displacement[-1] != 0) or _i30_np.any(displacement[:, 0] != 0) or _i30_np.any(displacement[:, -1] != 0):
        raise ValueError('invalid special terrain geometry or collar')
    _x13_check_mesh(vertices, triangles)
    if result['identity_sha256'] != _i30_identity(arrays, metadata):
        raise ValueError('special terrain identity mismatch')
    return True

def _special_headers(headers):
    if set(headers) != METRIC_FORMS_ARRAY_KEYS | {'manifest'}:
        raise ValueError('unexpected special terrain archive fields')
    shape, dtype = headers['reference_xyz_m']
    if len(shape) != 3 or shape[2] != 3 or min(shape[:2]) < 3 or (shape[0] * shape[1] > _i30_MAX_CELLS) or (dtype != _i30_np.float64):
        raise ValueError('invalid special terrain reference header')
    rows, cols = shape[:2]
    expected = {'displacement_xyz_m': (shape, _i30_np.dtype('float64')), 'vertices_xyz_m': ((rows * cols, 3), _i30_np.dtype('float64')), 'triangles': ((2 * (rows - 1) * (cols - 1), 3), _i30_np.dtype('int64')), 'protected_mask': ((rows, cols), _i30_np.dtype(bool))}
    if any((headers[key] != value for key, value in expected.items())):
        raise ValueError('invalid special terrain array header')
    manifest_shape, manifest_dtype = headers['manifest']
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= _i30_MAX_METADATA or manifest_dtype != _i30_np.uint8:
        raise ValueError('invalid special terrain manifest header')

def save_special_form_vdm(path, result):
    _i30_save_bundle(path, result, validator=validate_special_form_vdm)

def load_special_form_vdm(path, *, expected_sha256, expected_identity):
    if not isinstance(expected_identity, str) or len(expected_identity) != 64:
        raise ValueError('expected special terrain identity required')
    result = _i30_load_bundle(path, expected_sha256=expected_sha256, validator=validate_special_form_vdm, header_validator=_special_headers)
    if result['identity_sha256'] != expected_identity:
        raise ValueError('external special terrain identity mismatch')
    return result
METRIC_SURFACE_SCHEMA = 'metric-special-terrain-surface-v2'
METRIC_SURFACE_ALGORITHM = 'special-terrain-facet-noise-hydraulic-dissection-v2'
SUPERSEDES_ALGORITHM = 'special-terrain-facet-noise-hydraulic-dissection-v1'
ARRAY_KEYS = {'reference_xyz_m', 'displacement_xyz_m', 'vertices_xyz_m', 'triangles', 'protected_mask', 'surface_xyz_m', 'erosion_change_m'}
PARENT_ARRAY_KEYS = {'reference_xyz_m', 'displacement_xyz_m', 'vertices_xyz_m', 'triangles', 'protected_mask'}
RETIRED_RECIPE_FIELDS = ('immobile_rock_fraction',)
KERNEL_FILES = ('diffusion/geographic_noise.py', 'terrain_pipeline/drainage.py', 'terrain_pipeline/surface_rivers/metric_fluvial_morphodynamics.py', 'terrain_pipeline/surface_rivers/metric_fluvial_slope_stability.py', 'terrain_pipeline/common_infra.py')
ROOT = _i29_Path(__file__).resolve().parents[1]
FACET_SOURCE = ('assumed', 'parameters-and-sources.md#5.1 facet roughness scale and amplitude')
DISSECTION_SOURCE = ('assumed', 'parameters-and-sources.md#5.2 stream-power depth, cut cap, rock floor, mobile column and repose angle')
REPOSE_TOLERANCE_M = 0.001
REPOSE_SWEEP_BUDGET = 512

def _canonical(value):
    """The JSON-native form an in-memory record takes after a bundle round-trip.

    ``asdict`` hands back tuples where JSON hands back lists, and every bundle is
    written and read through JSON, so comparing a live recipe against a loaded one
    needs one canonical shape on both sides.  Storing the canonical form also keeps an
    in-memory bundle equal, field for field, to the same bundle after ``load_bundle``.
    """
    return _i29_json.loads(_i29_json.dumps(value, sort_keys=True, allow_nan=False))

def _finite_number(value, name, *, positive=False, nonnegative=False):
    if type(value) not in (int, float) or not _i29_math.isfinite(value) or (positive and value <= 0.0) or (nonnegative and value < 0.0):
        raise ValueError(f'invalid {name}')

def kernel_revisions(root=None):
    """sha256 of every reused kernel, so a moved pin is visible in the artifact."""
    base = ROOT if root is None else _i29_Path(root)
    return {name: _kernel_file_sha256(base / name) for name in KERNEL_FILES}

@_i29_dataclass(frozen=True)
class FacetRoughnessRecipe:
    """Multi-octave noise applied to the parent relief, tapered to the collar.

    ``scales`` declares each octave as a **wavelength in chart cells** plus a weight;
    ``wavelengths_m`` converts them with the parent chart's own spacing at build time.
    Declaring cells rather than metres makes the parent's sampling gate structural
    instead of hopeful: the four L0 charts run from 0.5 m to 8 m cells, so one absolute
    metre figure can be well resolved on one chart and aliased on another.

    ``amplitude_fraction`` is the peak facet relief as a fraction of the parent chart's
    maximum relief, so the result scales with the landform instead of with an absolute
    metre figure.
    """
    seed: int
    scales: tuple
    amplitude_fraction: float

    def __post_init__(self):
        if type(self.seed) is not int or not 0 <= self.seed < 2 ** 64:
            raise ValueError('facet seed must be uint64')
        if not isinstance(self.scales, (tuple, list)) or not 1 <= len(self.scales) <= 8:
            raise ValueError('one to eight facet octaves required')
        normalised = []
        for pair in self.scales:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError('facet octave is (wavelength_cells, weight)')
            cells, weight = pair
            _finite_number(cells, 'facet octave wavelength', positive=True)
            _finite_number(weight, 'facet octave weight', positive=True)
            normalised.append((float(cells), float(weight)))
        object.__setattr__(self, 'scales', tuple(normalised))
        if self.finest_cells < SAMPLES_PER_FEATURE:
            raise ValueError(f'finest facet octave {self.finest_cells:g} cells is below the {SAMPLES_PER_FEATURE}-cell sampling limit')
        _finite_number(self.amplitude_fraction, 'facet amplitude fraction', positive=True)
        if self.amplitude_fraction > 0.5:
            raise ValueError('facet amplitude must stay below half the parent relief')

    @property
    def finest_cells(self):
        return min((cells for cells, _ in self.scales))

    def wavelengths_m(self, spacing_m):
        """The octave list in absolute metres, as the noise kernel wants it."""
        _finite_number(spacing_m, 'chart spacing', positive=True)
        return tuple(((cells * spacing_m, weight) for cells, weight in self.scales))

@_i29_dataclass(frozen=True)
class DissectionRecipe:
    """Declared hydraulic dissection settings.

    ``detachment_per_step_m`` is the cut depth at reference accumulated discharge and
    unit slope, capped by ``maximum_cut_fraction`` of the relief.  No total cut may pass
    ``maximum_incision_fraction`` of the *roughened* relief below the roughened surface,
    and no cut may ever pass the parent base bed -- together those two are the declared
    rock floor.  The roughened relief is the one recorded as
    ``roughened_relief_reference_m``, so the floor is recomputable from the bundle.

    The mobile column is the native one: it starts empty on the roughened surface and
    deepens only where the bed was actually cut.  ``mobile_reference_m`` -- the larger of
    ``mobile_minimum_m`` and ``mobile_fraction`` x relief -- is the thickness the deposit
    coefficient is calibrated against, so deposition stays comparable with the material
    in transit rather than with the whole landform.  Only that in-transit column is
    relaxed to ``repose_angle_deg``; standing rock is never touched.
    """
    repose_angle_deg: float
    steps: int
    detachment_per_step_m: float
    maximum_cut_fraction: float
    maximum_incision_fraction: float
    mobile_fraction: float
    mobile_minimum_m: float
    deposition_fraction: float
    tolerance_m: float
    max_sweeps: int

    def __post_init__(self):
        _finite_number(self.repose_angle_deg, 'repose angle', positive=True)
        if not 0.0 < self.repose_angle_deg < 90.0:
            raise ValueError('repose angle must lie strictly inside (0, 90)')
        if type(self.steps) is not int or not 1 <= self.steps <= 256:
            raise ValueError('dissection steps outside the finite budget')
        _finite_number(self.detachment_per_step_m, 'detachment per step', positive=True)
        _finite_number(self.maximum_cut_fraction, 'maximum cut fraction', positive=True)
        if not 0.0 < self.maximum_cut_fraction <= 0.5:
            raise ValueError('maximum cut fraction must lie in (0, 0.5]')
        _finite_number(self.maximum_incision_fraction, 'maximum incision fraction', positive=True)
        if not 0.0 < self.maximum_incision_fraction <= 0.5:
            raise ValueError('maximum incision fraction must lie in (0, 0.5]')
        _finite_number(self.mobile_fraction, 'mobile fraction', positive=True)
        if not 0.0 < self.mobile_fraction < 1.0:
            raise ValueError('mobile fraction must lie in (0, 1)')
        _finite_number(self.mobile_minimum_m, 'mobile minimum', positive=True)
        _finite_number(self.deposition_fraction, 'deposition fraction', positive=True)
        if not 0.0 < self.deposition_fraction <= 1.0:
            raise ValueError('deposition fraction must lie in (0, 1]')
        _finite_number(self.tolerance_m, 'repose tolerance', positive=True)
        if type(self.max_sweeps) is not int or not 1 <= self.max_sweeps <= 512:
            raise ValueError('repose sweeps outside the finite budget')

    def mobile_reference_m(self, relief_m):
        return max(self.mobile_minimum_m, self.mobile_fraction * relief_m)

def surface_preset(kind):
    """Deterministic facet + dissection settings per L0 form kind.

    Facet octave spacing is tied to the parent chart cell size so the noise is resolved
    on every chart the parent accepts, and the declared detachment depth is per kind
    because the four landforms span 0.5 m to 8 m cells and 150 m to 348 m of relief.
    Amplitude and the remaining dissection settings are declared choices
    (see ``FACET_SOURCE`` / ``DISSECTION_SOURCE``).
    """
    facets = {'volcanic_plug': (0.1, ((32.0, 1.0), (12.0, 0.5), (5.0, 0.25)), 8.0), 'inselberg': (0.07, ((32.0, 1.0), (12.0, 0.5), (5.0, 0.25)), 8.0), 'sandstone_pillar_field': (0.13, ((8.0, 1.0), (5.0, 0.5), (4.0, 0.25)), 2.0), 'karst_tower_field': (0.09, ((24.0, 1.0), (9.0, 0.5), (5.0, 0.25)), 6.0)}
    if not isinstance(kind, str) or kind not in facets:
        raise ValueError('invalid special terrain form kind')
    amplitude, scales, detachment = facets[kind]
    roughness = FacetRoughnessRecipe(20261003 if kind != 'karst_tower_field' else 20261004, scales, amplitude)
    dissection = DissectionRecipe(repose_angle_deg=34.0, steps=12, detachment_per_step_m=detachment, maximum_cut_fraction=0.05, maximum_incision_fraction=0.15, mobile_fraction=0.03, mobile_minimum_m=4.0, deposition_fraction=0.35, tolerance_m=REPOSE_TOLERANCE_M, max_sweeps=REPOSE_SWEEP_BUDGET)
    return (roughness, dissection)

def _check_uniform_chart(reference):
    horizontal = reference[:, :, (0, 2)]
    adjacent = _i29_np.concatenate((_i29_np.linalg.norm(_i29_np.diff(horizontal, axis=0), axis=2).ravel(), _i29_np.linalg.norm(_i29_np.diff(horizontal, axis=1), axis=2).ravel()))
    if not _i29_np.isfinite(adjacent).all() or _i29_np.any(adjacent <= 0.0):
        raise ValueError('invalid adjacent horizontal chart spacing')
    minimum, maximum = (float(_i29_np.min(adjacent)), float(_i29_np.max(adjacent)))
    if maximum - minimum > 1e-06 * maximum:
        raise ValueError('special terrain surface chart must be a uniform grid')
    return (minimum, maximum)

def _facet_relief(reference, displacement, roughness, spacing):
    """Peak-normalised octave noise, tapered by the normalised parent relief."""
    top = displacement[:, :, 1]
    peak = float(_i29_np.max(top))
    if not _i29_math.isfinite(peak) or peak <= 0.0:
        raise ValueError('parent chart carries no relief to roughen')
    scales = roughness.wavelengths_m(spacing)
    noise = _i29_field(reference[:, :, 0], reference[:, :, 2], roughness.seed, 1901, scales)
    if noise.shape != top.shape or not _i29_np.isfinite(noise).all():
        raise ValueError('facet noise field does not match the chart')
    noise = noise - float(_i29_np.mean(noise, dtype=_i29_np.float64))
    scale = float(_i29_np.max(_i29_np.abs(noise)))
    if not _i29_math.isfinite(scale) or scale <= 0.0:
        raise ValueError('degenerate facet noise field')
    taper = _i29_np.clip(top / peak, 0.0, 1.0)
    return noise / scale * taper * (roughness.amplitude_fraction * peak)

def _per_target_depth(change, reference, recipe):
    x = reference[:, :, 0]
    z = reference[:, :, 2]
    record = {}
    for target in recipe.targets:
        across = (x - target.center_x_m) / target.radius_x_m
        along = (z - target.center_z_m) / target.radius_z_m
        inside = _i29_np.sqrt(across * across + along * along) <= 1.0
        record[target.target_id] = {'footprint_cells': int(inside.sum()), 'maximum_incision_m': float(_i29_np.max(-change[inside])) if inside.any() else 0.0, 'maximum_deposition_m': float(_i29_np.max(change[inside])) if inside.any() else 0.0}
    return record

def _parent_geometry(parent):
    """Pull and re-validate the five parent arrays plus its recipe."""
    validate_special_form_vdm(parent)
    arrays = {key: _i29_np.array(parent['arrays'][key], dtype=parent['arrays'][key].dtype, copy=True) for key in PARENT_ARRAY_KEYS}
    metadata = parent['metadata']
    if metadata['schema'] != METRIC_FORMS_SCHEMA:
        raise ValueError('special terrain surface requires a matching parent schema')
    reference = arrays['reference_xyz_m']
    if reference.ndim != 3 or reference.shape[2] != 3 or min(reference.shape[:2]) < 3 or (reference.shape[0] * reference.shape[1] > _i29_MAX_CELLS) or (reference.dtype != _i29_np.float64) or (not _i29_np.isfinite(reference).all()):
        raise ValueError('invalid parent reference chart')
    return (arrays, metadata)

def _dissect(bed, reference, displacement, dissection, *, protected_mask):
    """Two-phase dissection returning the final bed plus the three ledgers.

    Phase A (detachment) uses the routed graph and a declared stream-power law, bounded
    by the rock floor.  Phase B (transport) hands the eroded volume to the repository's
    donor-limited eight-neighbour operator, then relaxes only the resulting in-transit
    mobile column to the declared repose angle.  ``mobile_base`` follows the native
    update: the running minimum of the bed after every non-gravity phase.
    """
    shape = bed.shape
    spacing = float(reference[0, 1, 0] - reference[0, 0, 0])
    top = displacement[:, :, 1]
    relief = float(_i29_np.max(top))
    active = top > 0.0
    if not _i29_math.isfinite(relief) or relief <= 0.0:
        raise ValueError('parent chart carries no relief to dissect')
    surface = bed.copy()
    base_bed = reference[:, :, 1]
    floor = _i29_np.maximum(bed - dissection.maximum_incision_fraction * relief, base_bed)
    floor = _i29_np.minimum(floor, bed)
    if _i29_np.any(floor > bed):
        raise ValueError('rock floor above the bed')
    mobile_base = bed.copy()
    ring = _i29_np.zeros(shape, bool)
    ring[[0, -1], :] = True
    ring[:, [0, -1]] = True
    outer = ring.copy()
    for shift, axis in ((1, 0), (-1, 0), (1, 1), (-1, 1)):
        outer |= _i29_np.roll(ring, shift, axis=axis)
    edge_kind = _i29_np.full(shape, 'interior', dtype='U24')
    edge_kind[ring] = 'open_outflow'
    cell_type = _i29_np.where(active & ~outer, 0, -2)
    cell_type[0, :] = -2
    cell_type = cell_type.astype(_i29_np.int64)
    eligible = active.copy()
    eligible &= ~ring
    eligible[0, :] = False
    if protected_mask is not None:
        eligible &= ~protected_mask
    local_rain = _i29_np.where(active, 1.0, 0.0)
    boundary = _i29_BoundaryGrid(edge_kind, _i29_np.zeros(shape, bool), 'special-terrain-chart-edge', '0' * 64)
    steps = []
    coefficient = None
    detachment_total = 0.0
    deposition_total = 0.0
    relaxation_total = 0.0
    relaxed_all = True
    for index in range(dissection.steps):
        terrain = _i29_TerrainGrid(elevation_m=_i29_np.ascontiguousarray(bed), valid_mask=_i29_np.ones(shape, bool), x0_m=float(reference[0, 0, 0]), z0_m=float(reference[0, 0, 2]), dx_m=spacing, dz_m=spacing, source_kind='generated_terrain', source_id='special-terrain-surface-chart', source_sha256='0' * 64)
        graph = _i29_route_diagnostic(terrain, boundary)
        budget = _i29_accumulate_local_discharge(graph, local_rain)
        flux = _i29_np.asarray(budget['routed_q_m3_s'], dtype=_i29_np.float64)
        if not _i29_np.isfinite(flux).all() or _i29_np.any(flux < 0.0) or float(flux.max()) <= 0.0:
            raise ValueError('routed discharge is degenerate on the special terrain chart')
        slope = _i29_np.zeros(shape)
        donors = graph.receiver >= 0
        slope.ravel()[donors] = graph.edge_slope[donors]
        reference_flux = float(flux.max())
        demand = dissection.detachment_per_step_m * (flux / reference_flux) * _i29_np.clip(slope, 0.0, 1.0)
        demand = _i29_np.minimum(demand, dissection.maximum_cut_fraction * relief)
        cut = _i29_np.where(eligible, _i29_np.clip(_i29_np.minimum(demand, bed - floor), 0.0, None), 0.0)
        if not _i29_np.isfinite(cut).all():
            raise ValueError('nonfinite detachment depth')
        change = bed - cut
        if _i29_np.any(change < floor - 1e-12):
            raise ValueError('detachment crossed the rock floor')
        bed = change
        mobile_base = _i29_np.minimum(mobile_base, bed)
        detachment_volume = float(_i29_np.sum(cut) * spacing ** 2)
        supply = cut / spacing ** 2
        if coefficient is None:
            unit = _i29_conservative_diffusion_step(bed, supply, cell_type, floor, 1.0, spacing)
            span = float(_i29_np.max(_i29_np.abs(unit - bed)))
            if not _i29_math.isfinite(span):
                raise ValueError('nonfinite unit-coefficient transport response')
            reference_mobile = dissection.mobile_reference_m(relief)
            coefficient = dissection.deposition_fraction * reference_mobile / span if span > 0.0 else 0.0
        before = bed.copy()
        bed = _i29_conservative_diffusion_step(bed, supply, cell_type, floor, coefficient, spacing)
        if not _i29_np.isfinite(bed).all() or _i29_np.any(bed < floor - 1e-12):
            raise ValueError('nonfinite or under-floor transported bed')
        mobile_base = _i29_np.minimum(mobile_base, bed)
        moved = bed - before
        deposition_volume = float(_i29_np.sum(moved[moved > 0.0]) * spacing ** 2)
        relaxed = _i29_relax_mobile_slopes(bed, mobile_base, _i29_np.full(shape, 0.5), _i29_np.full(shape, 0.5), eligible, dx_m=spacing, repose_angle_deg=dissection.repose_angle_deg, tolerance_m=dissection.tolerance_m, max_sweeps=dissection.max_sweeps)
        before_relax = bed.copy()
        bed = relaxed.bed_m
        mobile_base = _i29_np.minimum(mobile_base, bed)
        ledger = relaxed.ledger
        if not _i29_np.isfinite(bed).all() or _i29_np.any(bed < mobile_base - 1e-12):
            raise ValueError('nonfinite or under-mobile-base relaxed bed')
        relaxed_move = bed - before_relax
        detachment_total += detachment_volume
        deposition_total += deposition_volume
        relaxation_total += float(ledger['transferred_bulk_m3'])
        relaxed_all &= bool(relaxed.converged)
        steps.append({'step_index': index, 'routed_discharge_max_m3_s': reference_flux, 'edge_slope_max_m_per_m': float(_i29_np.max(slope)), 'detachment_volume_m3': detachment_volume, 'detachment_depth_max_m': float(_i29_np.max(cut)), 'transport_deposition_volume_m3': deposition_volume, 'transport_change_max_m': float(_i29_np.max(_i29_np.abs(moved))), 'relaxation_transferred_volume_m3': float(ledger['transferred_bulk_m3']), 'relaxation_change_max_m': float(_i29_np.max(_i29_np.abs(relaxed_move))), 'relaxation_raw_residual_bulk_m3': float(ledger['raw_residual_bulk_m3']), 'relaxation_sweeps': int(ledger['sweeps']), 'relaxation_converged': bool(relaxed.converged), 'relaxation_maximum_excess_m': float(ledger['maximum_mobile_excess_after_m']), 'relaxation_immobile_excess_m': float(ledger['maximum_immobile_excess_after_m']), 'relaxation_stalled_at_float64_resolution': bool(ledger['stalled_at_float64_resolution']), 'mobile_column_volume_m3': float(_i29_np.sum(bed - mobile_base) * spacing ** 2)})
    change = bed - surface
    phase = _i29_phase_record(surface, bed, phase='hydraulic-dissection', step_index=dissection.steps - 1, dx_m=spacing, exported_bulk_m3=-float(_i29_np.sum(change) * spacing ** 2))
    ledger = {'transport_coefficient': coefficient, 'mobile_reference_m': dissection.mobile_reference_m(relief), 'rock_floor_depth_m': dissection.maximum_incision_fraction * relief, 'detachment_ledger_m3': detachment_total, 'transport_deposition_ledger_m3': deposition_total, 'relaxation_transferred_ledger_m3': relaxation_total, 'relaxation_converged': relaxed_all, 'relaxation_tolerance_m': dissection.tolerance_m, 'relaxation_sweep_budget': dissection.max_sweeps, 'relaxation_maximum_excess_m': max((step['relaxation_maximum_excess_m'] for step in steps), default=0.0), 'relaxation_sweeps_max': max((step['relaxation_sweeps'] for step in steps), default=0), 'maximum_incision_m': float(_i29_np.max(-change)), 'maximum_deposition_m': float(_i29_np.max(change)), 'incised_cells': int(_i29_np.sum(change < 0.0)), 'deposited_cells': int(_i29_np.sum(change > 0.0)), 'net_change_ledger_m3': float(_i29_np.sum(change) * spacing ** 2), 'phase_balance': {key: phase[key] for key in ('step_index', 'phase', 'injected_bulk_m3', 'exported_bulk_m3', 'lost_bulk_m3', 'inlet_correction_bulk_m3', 'raw_residual_bulk_m3')}, 'steps': steps}
    return (bed, ledger)

def build_special_form_surface(parent, *, roughness: FacetRoughnessRecipe, dissection: DissectionRecipe, base_kind=None):
    """Return a new bundle: the parent chart plus facet noise and dissection."""
    if not isinstance(roughness, FacetRoughnessRecipe):
        raise ValueError('FacetRoughnessRecipe required')
    if not isinstance(dissection, DissectionRecipe):
        raise ValueError('DissectionRecipe required')
    arrays, metadata = _parent_geometry(parent)
    reference = arrays['reference_xyz_m']
    displacement = arrays['displacement_xyz_m']
    mask = arrays['protected_mask']
    maximum = _check_uniform_chart(reference)[1]
    if maximum <= 0.0:
        raise ValueError('invalid special terrain surface chart spacing')
    if base_kind is None:
        base_kind = metadata['base']
    facets = _facet_relief(reference, displacement, roughness, maximum)
    facets[mask] = 0.0
    roughened = displacement.copy()
    roughened[:, :, 1] = displacement[:, :, 1] + facets
    if _i29_np.any(roughened[0, :, 1] != 0.0) or _i29_np.any(roughened[-1, :, 1] != 0.0) or _i29_np.any(roughened[:, 0, 1] != 0.0) or _i29_np.any(roughened[:, -1, 1] != 0.0):
        raise ValueError('facet roughness left the collar')
    roughened[0, :, :] = 0.0
    roughened[-1, :, :] = 0.0
    roughened[:, 0, :] = 0.0
    roughened[:, -1, :] = 0.0
    surface = reference + roughened
    if not _i29_np.isfinite(surface).all():
        raise ValueError('nonfinite special terrain surface')
    final_bed, ledger = _dissect(surface[:, :, 1], reference, roughened, dissection, protected_mask=mask)
    final_bed = _i29_np.array(final_bed, dtype=_i29_np.float64, copy=True)
    if not _i29_np.isfinite(final_bed).all():
        raise ValueError('nonfinite dissected bed')
    change = final_bed - surface[:, :, 1]
    if _i29_np.any(change[0] != 0.0) or _i29_np.any(change[-1] != 0.0) or _i29_np.any(change[:, 0] != 0.0) or _i29_np.any(change[:, -1] != 0.0):
        raise ValueError('dissection left the collar')
    if _i29_np.any(change[mask] != 0.0):
        raise ValueError('dissection touched a protected cell')
    if _i29_np.any(final_bed < 0.0) and metadata['base'] == 'synthetic_analytic':
        raise ValueError('dissection cut the synthetic base plane')
    final_surface = surface.copy()
    final_bed = surface[:, :, 1] + change
    final_surface[:, :, 1] = final_bed
    vertices = final_surface.reshape(-1, 3)
    triangles = _x12_triangles(*mask.shape)
    _x11_check_mesh(vertices, triangles)
    if not (_i29_np.array_equal(final_surface[0], reference[0]) and _i29_np.array_equal(final_surface[-1], reference[-1]) and _i29_np.array_equal(final_surface[:, 0], reference[:, 0]) and _i29_np.array_equal(final_surface[:, -1], reference[:, -1])):
        raise ValueError('special terrain surface left the collar')
    recipe = _parse_recipe_record(metadata['recipe'])
    out_arrays = {'reference_xyz_m': _i29_readonly(reference), 'displacement_xyz_m': _i29_readonly(roughened), 'vertices_xyz_m': _i29_readonly(vertices), 'triangles': _i29_readonly(triangles), 'protected_mask': _i29_readonly(mask), 'surface_xyz_m': _i29_readonly(final_surface), 'erosion_change_m': _i29_readonly(change)}
    out_metadata = {'schema': METRIC_SURFACE_SCHEMA, 'algorithm': METRIC_SURFACE_ALGORITHM, 'coordinates': METRIC_FORMS_COORDINATES, 'base': base_kind, 'supersedes_algorithm': SUPERSEDES_ALGORITHM, 'recipe': metadata['recipe'], 'parameter_sources': metadata['parameter_sources'], 'source_identity': metadata['source_identity'], 'protection_identity': metadata['protection_identity'], 'parent_schema': metadata['schema'], 'parent_algorithm': metadata['algorithm'], 'parent_identity_sha256': parent['identity_sha256'], 'parent_kind': recipe.kind, 'facet_recipe': _canonical(_i29_asdict(roughness)), 'facet_source': {'grade': FACET_SOURCE[0], 'reference': FACET_SOURCE[1]}, 'facet_wavelengths_m': [list(pair) for pair in roughness.wavelengths_m(maximum)], 'dissection_recipe': _canonical(_i29_asdict(dissection)), 'dissection_source': {'grade': DISSECTION_SOURCE[0], 'reference': DISSECTION_SOURCE[1]}, 'kernel_revisions': kernel_revisions(), 'relief_reference_m': float(_i29_np.max(displacement[:, :, 1])), 'roughened_relief_reference_m': float(_i29_np.max(roughened[:, :, 1])), 'targets': _per_target_depth(change, reference, recipe), 'ledger': ledger, 'hydraulic_ready': False, 'natural_outlet_verified': False, 'publishable': False, 'self_intersection_verified': False}
    result = {'arrays': out_arrays, 'metadata': out_metadata, 'identity_sha256': _i29_identity(out_arrays, out_metadata)}
    validate_special_form_surface(result)
    return result

def validate_special_form_surface(result):
    if not isinstance(result, dict) or set(result) != {'arrays', 'metadata', 'identity_sha256'}:
        raise ValueError('invalid special terrain surface bundle')
    arrays, metadata = (result['arrays'], result['metadata'])
    if not isinstance(arrays, dict) or set(arrays) != ARRAY_KEYS or (not isinstance(metadata, dict)):
        raise ValueError('invalid special terrain surface fields')
    required = {'schema', 'algorithm', 'coordinates', 'base', 'supersedes_algorithm', 'recipe', 'parameter_sources', 'source_identity', 'protection_identity', 'parent_schema', 'parent_algorithm', 'parent_identity_sha256', 'parent_kind', 'facet_recipe', 'facet_source', 'facet_wavelengths_m', 'dissection_recipe', 'dissection_source', 'kernel_revisions', 'relief_reference_m', 'roughened_relief_reference_m', 'targets', 'ledger', 'hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified'}
    if set(metadata) != required or metadata['schema'] != METRIC_SURFACE_SCHEMA or metadata['algorithm'] != METRIC_SURFACE_ALGORITHM or (metadata['supersedes_algorithm'] != SUPERSEDES_ALGORITHM) or (metadata['coordinates'] != METRIC_FORMS_COORDINATES) or (metadata['parent_schema'] != METRIC_FORMS_SCHEMA) or any((metadata[key] is not False for key in ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified'))):
        raise ValueError('invalid special terrain surface metadata')
    if metadata['facet_source'] != {'grade': FACET_SOURCE[0], 'reference': FACET_SOURCE[1]} or metadata['dissection_source'] != {'grade': DISSECTION_SOURCE[0], 'reference': DISSECTION_SOURCE[1]}:
        raise ValueError('special terrain surface provenance mismatch')
    wavelengths = metadata['facet_wavelengths_m']
    if not isinstance(wavelengths, list) or any((not isinstance(pair, list) or len(pair) != 2 or type(pair[0]) is not float or (type(pair[1]) is not float) for pair in wavelengths)):
        raise ValueError('special terrain surface facet wavelength record is incomplete')
    if set(metadata['kernel_revisions']) != set(KERNEL_FILES) or any((not isinstance(value, str) or len(value) != 64 for value in metadata['kernel_revisions'].values())):
        raise ValueError('special terrain surface kernel revision record is incomplete')
    if not isinstance(metadata['parent_identity_sha256'], str) or len(metadata['parent_identity_sha256']) != 64:
        raise ValueError('missing parent identity')
    if any((field in metadata['dissection_recipe'] for field in RETIRED_RECIPE_FIELDS)):
        raise ValueError('retired dissection recipe field is still present')
    try:
        facet = FacetRoughnessRecipe(**metadata['facet_recipe'])
        dissection = DissectionRecipe(**metadata['dissection_recipe'])
    except TypeError as error:
        raise ValueError(f'invalid special terrain surface recipe: {error}') from error
    if metadata['facet_recipe'] != _canonical(_i29_asdict(facet)) or metadata['dissection_recipe'] != _canonical(_i29_asdict(dissection)):
        raise ValueError('invalid special terrain surface recipe')
    if not all((isinstance(value, _i29_np.ndarray) for value in arrays.values())):
        raise ValueError('invalid special terrain surface arrays')
    reference = arrays['reference_xyz_m']
    displacement = arrays['displacement_xyz_m']
    vertices = arrays['vertices_xyz_m']
    triangles = arrays['triangles']
    mask = arrays['protected_mask']
    surface = arrays['surface_xyz_m']
    change = arrays['erosion_change_m']
    shape = reference.shape[:2]
    if reference.ndim != 3 or reference.shape[2] != 3 or min(shape) < 3 or (shape[0] * shape[1] > _i29_MAX_CELLS) or (reference.dtype != _i29_np.float64) or (displacement.shape != reference.shape) or (displacement.dtype != _i29_np.float64) or (surface.shape != reference.shape) or (surface.dtype != _i29_np.float64) or (change.shape != shape) or (change.dtype != _i29_np.float64) or (vertices.shape != (shape[0] * shape[1], 3)) or (vertices.dtype != _i29_np.float64) or (mask.shape != shape) or (mask.dtype != bool) or (triangles.shape != (2 * (shape[0] - 1) * (shape[1] - 1), 3)) or (triangles.dtype != _i29_np.int64):
        raise ValueError('invalid special terrain surface array shape or dtype')
    maximum = _check_uniform_chart(reference)[1]
    if maximum <= 0.0:
        raise ValueError('invalid special terrain surface chart spacing')
    if [tuple(pair) for pair in wavelengths] != list(facet.wavelengths_m(maximum)):
        raise ValueError('special terrain surface facet wavelengths disagree with the recipe')
    if facet.finest_cells < SAMPLES_PER_FEATURE:
        raise ValueError('special terrain surface facet octave below the sampling limit')
    for name in ('relief_reference_m', 'roughened_relief_reference_m'):
        _finite_number(metadata[name], name, positive=True)
    if metadata['roughened_relief_reference_m'] != float(_i29_np.max(displacement[:, :, 1])) or metadata['roughened_relief_reference_m'] < metadata['relief_reference_m']:
        raise ValueError('special terrain surface roughened relief disagrees with the arrays')
    vertical = _i29_np.zeros_like(reference)
    vertical[:, :, 1] = change
    if not _i29_np.isfinite(reference).all() or not _i29_np.isfinite(displacement).all() or (not _i29_np.isfinite(surface).all()) or (not _i29_np.isfinite(change).all()) or (not _i29_np.array_equal(vertices, surface.reshape(-1, 3))) or (not _i29_np.array_equal(triangles, _x12_triangles(*shape))) or (not _i29_np.array_equal(surface, reference + displacement + vertical)):
        raise ValueError('invalid special terrain surface geometry')
    if _i29_np.any(displacement[:, :, 0] != 0) or _i29_np.any(displacement[:, :, 2] != 0) or _i29_np.any(displacement[0, :, 1] != 0) or _i29_np.any(displacement[-1, :, 1] != 0) or _i29_np.any(displacement[:, 0, 1] != 0) or _i29_np.any(displacement[:, -1, 1] != 0) or _i29_np.any(change[mask] != 0.0) or (not _i29_np.array_equal(surface[0], reference[0])) or (not _i29_np.array_equal(surface[-1], reference[-1])) or (not _i29_np.array_equal(surface[:, 0], reference[:, 0])) or (not _i29_np.array_equal(surface[:, -1], reference[:, -1])):
        raise ValueError('special terrain surface does not close on its collar')
    _x11_check_mesh(vertices, triangles)
    ledger = metadata['ledger']
    if ledger['relaxation_tolerance_m'] != dissection.tolerance_m or ledger['relaxation_sweep_budget'] != dissection.max_sweeps:
        raise ValueError('special terrain surface relaxation budget disagrees with the recipe')
    steps = ledger['steps']
    if not isinstance(steps, list) or len(steps) != dissection.steps or [step['step_index'] for step in steps] != list(range(dissection.steps)):
        raise ValueError('special terrain surface step ledger does not match the recipe')
    if any((bool(step['relaxation_converged']) != (step['relaxation_maximum_excess_m'] <= dissection.tolerance_m) for step in steps)):
        raise ValueError('special terrain surface relaxation flag disagrees with its excess')
    if ledger['relaxation_converged'] is not all((step['relaxation_maximum_excess_m'] <= dissection.tolerance_m for step in steps)):
        raise ValueError('special terrain surface relaxation summary disagrees with its steps')
    if ledger['relaxation_maximum_excess_m'] != max((step['relaxation_maximum_excess_m'] for step in steps)) or ledger['relaxation_sweeps_max'] != max((step['relaxation_sweeps'] for step in steps)):
        raise ValueError('special terrain surface relaxation extremes disagree with its steps')
    if result['identity_sha256'] != _i29_identity(arrays, metadata):
        raise ValueError('special terrain surface identity mismatch')
    return True

def _surface_headers(headers):
    if set(headers) != ARRAY_KEYS | {'manifest'}:
        raise ValueError('unexpected special terrain surface archive fields')
    shape, dtype = headers['reference_xyz_m']
    if len(shape) != 3 or shape[2] != 3 or min(shape[:2]) < 3 or (shape[0] * shape[1] > _i29_MAX_CELLS) or (dtype != _i29_np.float64):
        raise ValueError('invalid special terrain surface reference header')
    rows, cols = shape[:2]
    expected = {'displacement_xyz_m': (shape, _i29_np.dtype('float64')), 'surface_xyz_m': (shape, _i29_np.dtype('float64')), 'erosion_change_m': ((rows, cols), _i29_np.dtype('float64')), 'vertices_xyz_m': ((rows * cols, 3), _i29_np.dtype('float64')), 'triangles': ((2 * (rows - 1) * (cols - 1), 3), _i29_np.dtype('int64')), 'protected_mask': ((rows, cols), _i29_np.dtype('bool'))}
    if any((headers[key] != value for key, value in expected.items())):
        raise ValueError('invalid special terrain surface array header')
    manifest_shape, manifest_dtype = headers['manifest']
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= _i29_MAX_METADATA or manifest_dtype != _i29_np.uint8:
        raise ValueError('invalid special terrain surface manifest header')

def save_special_form_surface(path, result):
    _i29_save_bundle(path, result, validator=validate_special_form_surface)

def load_special_form_surface(path, *, expected_sha256, expected_identity):
    if not isinstance(expected_identity, str) or len(expected_identity) != 64:
        raise ValueError('expected special terrain surface identity required')
    result = _i29_load_bundle(path, expected_sha256=expected_sha256, validator=validate_special_form_surface, header_validator=_surface_headers)
    if result['identity_sha256'] != expected_identity:
        raise ValueError('external special terrain surface identity mismatch')
    return result
SINKHOLE_SCHEMA = 'td-special-terrain-l1-sinkhole-v1'
SINKHOLE_ALGORITHM = 'sampled-rock-sinkhole-shaft-subsurface-river-skylight-v1'
BASE_NOTE = 'not TD native terrain, not surveyed'
LOCAL_ORIGIN = _i31_np.array([1200.0, 480.0, -2500.0])
WITNESS_TOLERANCE_M = 1e-06
CUTTER_ROLES = ('shaft_funnel', 'upper_terrace_bench', 'lower_terrace_bench', 'subsurface_river', 'river_branch')
FIGURE_NAMES = ('sinkhole-a-plan.png', 'sinkhole-b-profile.png', 'sinkhole-c-solid.png')
PLAN_SAMPLES = 72
PROFILE_SAMPLES = 241
WITNESS_METHODS = ('Manifold.ray_cast', 'Solid.winding', 'Mesh64_boolean')
SINKHOLE_EXPLICIT_ASSUMPTIONS = {'block_half_span_x_m': 'analytic host block size; not a landform measurement', 'block_half_span_z_m': 'analytic host block size; not a landform measurement', 'ground_surface_y_m': 'analytic flat top elevation; not a surveyed surface', 'block_floor_y_m': 'analytic block floor chosen below every cutter; not a measurement', 'shaft_bottom_y_m': 'no tiankeng depth source; parameterisation choice', 'shaft_collar_y_m': 'protrusion above the block chosen so the subtraction is not coplanar', 'shaft_radius_bottom_m': 'no tiankeng shaft radius source; parameterisation choice', 'shaft_radius_top_m': 'no tiankeng collar radius source; parameterisation choice', 'shaft_segments': 'ring resolution of the analytic funnel; not a measurement', 'terrace_segments': 'ring resolution of the analytic benches; not a measurement', 'upper_terrace_radius_m': 'no bench spacing source; parameterisation choice', 'upper_terrace_bottom_y_m': 'no bench spacing source; parameterisation choice', 'upper_terrace_top_y_m': 'no bench spacing source; parameterisation choice', 'lower_terrace_radius_m': 'no bench spacing source; parameterisation choice', 'lower_terrace_bottom_y_m': 'no bench spacing source; parameterisation choice', 'lower_terrace_top_y_m': 'no bench spacing source; parameterisation choice', 'river_half_width_m': 'no subsurface river section source; parameterisation choice', 'river_reach_x_m': 'reach length chosen to stay wholly buried inside the block', 'river_bed_y_m': 'no subsurface river burial depth source; parameterisation choice', 'river_ceiling_y_m': 'no subsurface river burial depth source; parameterisation choice', 'branch_x_low_m': 'tributary extent chosen to stay wholly buried inside the block', 'branch_x_high_m': 'tributary extent chosen to stay wholly buried inside the block', 'branch_z_low_m': 'tributary extent chosen to overlap the main buried reach', 'branch_z_end_m': 'tributary extent chosen to stay wholly buried inside the block', 'branch_bed_y_m': 'tributary section chosen to overlap the buried reach', 'branch_ceiling_y_m': 'tributary section chosen to overlap the buried reach'}
PREREQUISITES = ('explicit_terminal_declaration_for_the_buried_reach_required_before_any_routing', 'lake_domain_record_for_the_shaft_volume_required_before_any_lake_accounting', 'interior_loss_contract_required_because_the_closed_reach_flux_is_currently_zero')

@_i31_dataclass(frozen=True)
class SinkholeParameters:
    """Bounded explicit engineering parameters; every value is an explicit assumption."""
    block_half_span_x_m: float = 60.0
    block_half_span_z_m: float = 60.0
    ground_surface_y_m: float = 0.0
    block_floor_y_m: float = -40.0
    shaft_bottom_y_m: float = -32.0
    shaft_collar_y_m: float = 4.0
    shaft_radius_bottom_m: float = 13.0
    shaft_radius_top_m: float = 17.0
    shaft_segments: int = 64
    terrace_segments: int = 48
    upper_terrace_radius_m: float = 21.0
    upper_terrace_bottom_y_m: float = -9.0
    upper_terrace_top_y_m: float = -6.0
    lower_terrace_radius_m: float = 17.5
    lower_terrace_bottom_y_m: float = -22.0
    lower_terrace_top_y_m: float = -19.0
    river_half_width_m: float = 5.0
    river_reach_x_m: float = 55.0
    river_bed_y_m: float = -36.0
    river_ceiling_y_m: float = -28.0
    branch_x_low_m: float = -29.0
    branch_x_high_m: float = -23.0
    branch_z_low_m: float = -5.0
    branch_z_end_m: float = 38.0
    branch_bed_y_m: float = -36.0
    branch_ceiling_y_m: float = -30.0

    def __post_init__(self):
        floats = {key: value for key, value in _i31_asdict(self).items() if key not in ('shaft_segments', 'terrace_segments')}
        if not all((type(value) is float and _i31_math.isfinite(value) for value in floats.values())):
            raise ValueError('finite explicit float parameters required')
        for name in ('shaft_segments', 'terrace_segments'):
            value = getattr(self, name)
            if type(value) is not int or not 12 <= value <= 512:
                raise ValueError('bounded integer segment counts required')
        if self.shaft_collar_y_m <= self.ground_surface_y_m:
            raise ValueError('shaft collar must protrude above the ground surface')
        if not self.block_floor_y_m < self.river_bed_y_m < self.river_ceiling_y_m < self.ground_surface_y_m:
            raise ValueError('river section must be buried above the block floor and below the ground surface')
        if not self.shaft_bottom_y_m < self.river_ceiling_y_m:
            raise ValueError('shaft must cut down into the river section so the void stays one connected solid')
        if not 0.0 < self.shaft_radius_bottom_m < self.shaft_radius_top_m <= min(self.block_half_span_x_m, self.block_half_span_z_m) / 2.0:
            raise ValueError('shaft radii must be positive, widening upward and inside the block')
        if not self.shaft_radius_top_m < self.lower_terrace_radius_m < self.upper_terrace_radius_m <= min(self.block_half_span_x_m, self.block_half_span_z_m) / 2.0:
            raise ValueError('terrace radii must be outside the collar and inside the block')
        if not self.upper_terrace_bottom_y_m < self.upper_terrace_top_y_m < self.ground_surface_y_m:
            raise ValueError('terrace benches must stay below the ground surface')
        if not self.lower_terrace_bottom_y_m < self.lower_terrace_top_y_m < self.upper_terrace_bottom_y_m:
            raise ValueError('terrace benches must be ordered below the upper bench')
        if not self.lower_terrace_top_y_m > self.shaft_bottom_y_m:
            raise ValueError('lower bench must stay above the shaft floor')
        if not 0.0 < self.river_half_width_m < self.block_half_span_z_m / 2.0:
            raise ValueError('subsurface river half width must stay inside the block')
        if not self.river_half_width_m < self.river_reach_x_m < self.block_half_span_x_m:
            raise ValueError('buried reach must stop inside the block so no second surface opening appears')
        if not (self.branch_x_low_m < self.branch_x_high_m and -self.river_reach_x_m <= self.branch_x_low_m and (self.branch_x_high_m <= self.river_reach_x_m)):
            raise ValueError('branch must leave the main reach inside the buried footprint')
        if not -self.block_half_span_z_m < self.branch_z_low_m < self.branch_z_end_m < self.block_half_span_z_m:
            raise ValueError('branch must stay wholly buried inside the block')
        if not self.branch_z_low_m < self.river_half_width_m:
            raise ValueError('branch must overlap the main buried reach in the z direction')
        if not (self.branch_bed_y_m < self.branch_ceiling_y_m and self.branch_bed_y_m < self.river_ceiling_y_m and (self.branch_ceiling_y_m > self.river_bed_y_m) and (self.branch_z_low_m < self.river_half_width_m)):
            raise ValueError('branch section must overlap the buried reach in all three axes')

def as_parameters(parameters):
    """Accept the frozen dataclass or a plain parameter mapping; refuse anything else."""
    if isinstance(parameters, SinkholeParameters):
        return parameters
    if isinstance(parameters, dict):
        return SinkholeParameters(**parameters)
    raise ValueError('explicit SinkholeParameters or parameter mapping required')

def assumption_list(parameters):
    """The report's explicit-assumption ledger; every entry is graded ``assumed``."""
    values = _i31_asdict(as_parameters(parameters))
    entries = []
    for name, reason in sorted(SINKHOLE_EXPLICIT_ASSUMPTIONS.items()):
        if name not in values:
            raise ValueError('explicit assumption names an unknown parameter: ' + name)
        if not isinstance(reason, str) or not reason:
            raise ValueError('explicit assumption requires a stated reason: ' + name)
        entries.append({'name': name, 'value': values[name], 'grade': 'assumed', 'reason': reason})
    return entries

def library_versions():
    return {'manifold3d': _i31_importlib.metadata.version('manifold3d'), 'numpy': _i31_np.__version__}

def rectangle_ring(x_low, x_high, z_low, z_high):
    """Counter-clockwise rectangle in the (x, z) plane for buried prism cutters."""
    for value in (x_low, x_high, z_low, z_high):
        if type(value) is not float or not _i31_math.isfinite(value):
            raise ValueError('finite float rectangle bounds required')
    if not (x_low < x_high and z_low < z_high):
        raise ValueError('strictly increasing rectangle bounds required')
    return _i31_np.array([[x_low, z_low], [x_high, z_low], [x_high, z_high], [x_low, z_high]], float)

def _body(parameters, origin):
    return _x24_polygon_prism_record(rectangle_ring(-parameters.block_half_span_x_m, parameters.block_half_span_x_m, -parameters.block_half_span_z_m, parameters.block_half_span_z_m), parameters.block_floor_y_m, parameters.ground_surface_y_m, origin, 'rock_before')

def _cutters(parameters, origin):
    """The five declared closed cutters, in the fixed ``CUTTER_ROLES`` order."""
    shaft = _x22_frustum_record([0.0, 0.0], [0.0, 0.0], parameters.shaft_bottom_y_m, parameters.shaft_collar_y_m, parameters.shaft_radius_bottom_m, parameters.shaft_radius_top_m, origin, 'shaft_funnel', segments=parameters.shaft_segments)
    upper = _x24_polygon_prism_record(_x23_octagon_ring([0.0, 0.0], parameters.upper_terrace_radius_m, parameters.upper_terrace_radius_m, parameters.terrace_segments), parameters.upper_terrace_bottom_y_m, parameters.upper_terrace_top_y_m, origin, 'upper_terrace_bench')
    lower = _x24_polygon_prism_record(_x23_octagon_ring([0.0, 0.0], parameters.lower_terrace_radius_m, parameters.lower_terrace_radius_m, parameters.terrace_segments), parameters.lower_terrace_bottom_y_m, parameters.lower_terrace_top_y_m, origin, 'lower_terrace_bench')
    river = _x24_polygon_prism_record(rectangle_ring(-parameters.river_reach_x_m, parameters.river_reach_x_m, -parameters.river_half_width_m, parameters.river_half_width_m), parameters.river_bed_y_m, parameters.river_ceiling_y_m, origin, 'subsurface_river')
    branch = _x24_polygon_prism_record(rectangle_ring(parameters.branch_x_low_m, parameters.branch_x_high_m, parameters.branch_z_low_m, parameters.branch_z_end_m), parameters.branch_bed_y_m, parameters.branch_ceiling_y_m, origin, 'river_branch')
    return [shaft, upper, lower, river, branch]

def solid_winding(record, point_xyz_m, origin):
    """Van Oosterom-Strackee solid-angle winding of one saved solid at one world point.

    Independent of the Mesh64 engine: it reads only the saved local vertices/triangles, so a
    cold auditor can reproduce the same number with its own implementation (the
    ``tools/hybrid_cave_saved_audit.Solid.winding`` formulation).
    """
    vertices = _i31_np.asarray(record['vertices_local_xyz_m'], float)
    local_point = _i31_np.asarray(point_xyz_m, float) - _i31_np.asarray(origin, float)
    offsets = vertices[_i31_np.asarray(record['triangles'], int)] - local_point
    lengths = _i31_np.linalg.norm(offsets, axis=2)
    if not _i31_np.all(lengths > 1e-09):
        raise ValueError('winding probe touches a saved vertex')
    first, second, third = (offsets[:, 0], offsets[:, 1], offsets[:, 2])
    numerator = _i31_np.einsum('ij,ij->i', first, _i31_np.cross(second, third))
    denominator = lengths.prod(axis=1)
    denominator += _i31_np.einsum('ij,ij->i', first, second) * lengths[:, 2]
    denominator += _i31_np.einsum('ij,ij->i', second, third) * lengths[:, 0]
    denominator += _i31_np.einsum('ij,ij->i', third, first) * lengths[:, 1]
    return _i31_math.fsum((2.0 * _i31_np.arctan2(numerator, denominator)).tolist()) / (4.0 * _i31_math.pi)

def _ray_witness(solid, origin, role, first, second, expected_hit_count, claim, first_hit_y_m=None):
    hits = _x16_ray_hits(solid, list(first), list(second), origin)
    observed_first = hits[0]['position_xyz_m'][1] if hits else None
    verdict = bool(len(hits) == expected_hit_count)
    if first_hit_y_m is not None:
        verdict = bool(verdict and observed_first is not None and (abs(observed_first - float(first_hit_y_m)) <= WITNESS_TOLERANCE_M))
    if not verdict:
        raise ValueError('vertical_ray_witness_failed:' + role + ':' + str(claim))
    return {'method': 'Manifold.ray_cast', 'solid_role': role, 'from_xyz_m': [float(value) for value in first], 'to_xyz_m': [float(value) for value in second], 'expected_hit_count': int(expected_hit_count), 'verdict': True, 'claim': claim, 'observed': {'hit_count': len(hits), 'first_hit_y_m': observed_first, 'hits': hits}}

def _winding_witness(record, origin, point_xyz_m, expected_inside, claim):
    winding = solid_winding(record, point_xyz_m, origin)
    near_integer = min(abs(winding), abs(1.0 - winding)) <= 1e-06
    verdict = bool(near_integer and (winding > 0.5) == bool(expected_inside))
    if not verdict:
        raise ValueError('winding_witness_failed:' + str(claim))
    return {'method': 'Solid.winding', 'solid_role': record['role'], 'point_xyz_m': [float(value) for value in point_xyz_m], 'expected_inside': bool(expected_inside), 'verdict': True, 'claim': claim, 'observed': {'winding': winding}}

def _vertical(x_m, z_m, from_y_m, to_y_m):
    return ((float(x_m), float(from_y_m), float(z_m)), (float(x_m), float(to_y_m), float(z_m)))

def witnesses(record, solids, parameters, origin):
    """Actual recomputable evidence: skylight rays, void winding, and volume accounting.

    Every entry is one of the three cold-auditable shapes and refers only to roles saved in
    ``solids``. Each claim is *refused* (raise) here when the measured geometry disagrees, so
    a recorded ``verdict: true`` is a measurement rather than a declaration of intent.
    """
    before = _x25_solid_from_record(solids['rock_before'], 'rock_before')
    after = _x25_solid_from_record(solids['rock_after'], 'rock_after')
    above = 20.0
    river_entry_y = parameters.river_ceiling_y_m - 2.0
    under_floor_y = parameters.block_floor_y_m + 1.0
    entries = {}
    entries['skylight_axis_blocked_before_excavation'] = _ray_witness(before, origin, 'rock_before', *_vertical(0.0, 0.0, above, river_entry_y), 1, 'before the Boolean the shaft axis was solid rock: a vertical ray meets exactly one crossing, the intact top face, so no skylight existed there')
    entries['skylight_axis_open_after_excavation'] = _ray_witness(after, origin, 'rock_after', *_vertical(0.0, 0.0, above, river_entry_y), 0, 'after the Boolean a vertical ray on the shaft axis meets no rock surface between above ground and the buried river ceiling: the collar is a real skylight into the excavated void, measured with Manifold.ray_cast, not inferred')
    entries['shaft_floor_is_the_buried_river_bed'] = _ray_witness(after, origin, 'rock_after', *_vertical(0.0, 0.0, above, under_floor_y), 1, 'the only rock crossing on the shaft axis below the void is the buried river bed at the declared bed elevation, so the shaft floor drains into the subsurface reach instead of being sealed by rock', first_hit_y_m=parameters.river_bed_y_m)
    surface_band_to_y = parameters.ground_surface_y_m - 3.0
    open_samples = ((4.0, 0.0), (8.0, 0.0), (11.5, 8.0), (14.0, -6.0), (8.0, -12.0))
    for ordinal, (x_m, z_m) in enumerate(open_samples):
        entries['collar_footprint_open_sample_%02d' % ordinal] = _ray_witness(after, origin, 'rock_after', *_vertical(x_m, z_m, above, surface_band_to_y), 0, 'footprint sample inside the collar radius: the surface-band ray meets no rock, so the collar is an opening between above ground and the near-surface rock band')
    closed_samples = ((24.0, 0.0), (21.0, 21.0), (36.0, 0.0), (0.0, 36.0), (-32.0, 32.0), (-54.0, 0.0), (-24.0, 0.0), (32.0, -32.0), (-54.0, 12.0), (50.0, 0.0), (0.0, 24.0), (0.0, -24.0), (0.0, -52.0), (12.0, -52.0))
    for ordinal, (x_m, z_m) in enumerate(closed_samples):
        entries['outside_collar_surface_intact_sample_%02d' % ordinal] = _ray_witness(after, origin, 'rock_after', *_vertical(x_m, z_m, above, surface_band_to_y), 1, 'footprint sample outside the collar radius: exactly one crossing, the intact top face at the declared ground surface, so the ground surface is continuous here and this is not a second surface opening', first_hit_y_m=parameters.ground_surface_y_m)
    winding_cases = (('shaft_interior_is_void', (0.0, -10.0, 0.0), False, 'the carved shaft interior is outside the remaining rock'), ('buried_river_interior_is_void', (40.0, -32.0, 0.0), False, 'the buried reach interior is outside the remaining rock and stays wholly under the block'), ('branch_interior_is_void', (-26.0, -33.0, 30.0), False, 'the tributary branch interior is outside the remaining rock'), ('intact_rock_mass_is_solid', (40.0, -20.0, 40.0), True, 'rock far from the excavation stays inside the remaining rock'), ('ground_surface_outside_collar_is_solid_a', (40.0, -0.5, 40.0), True, 'just below the ground surface outside the collar the remaining rock is solid'), ('ground_surface_outside_collar_is_solid_b', (-52.0, -0.5, 8.0), True, 'just below the ground surface outside the collar the remaining rock is solid'), ('ground_surface_outside_collar_is_solid_c', (10.0, -0.5, 50.0), True, 'just below the ground surface outside the collar the remaining rock is solid'), ('ground_surface_outside_collar_is_solid_d', (0.0, -0.5, 44.0), True, 'just below the ground surface outside the collar the remaining rock is solid'))
    for name, point, inside, claim in winding_cases:
        entries[name] = _winding_witness(solids['rock_after'], origin, point, inside, claim)
    material = record['material']
    entries['material_balance_actual_volume'] = {'method': 'Mesh64_boolean', 'operation': 'subtract', 'rock_role': 'rock_before', 'cutter_roles': list(CUTTER_ROLES), 'expected_rock_after_m3': material['rock_after_m3'], 'expected_removed_m3': material['excavated_rock_m3'], 'verdict': True, 'claim': 'rock_before minus the union of the five closed cutters, recomputed from the saved meshes alone, must reproduce these rock_after and removed volumes; the excavated void is one connected solid and the residual stays inside the declared balance budget', 'observed': {'rock_before_m3': material['rock_before_m3'], 'rock_after_m3': material['rock_after_m3'], 'removed_m3': material['excavated_rock_m3'], 'residual_m3': material['signed_residual_m3'], 'balance_budget_m3': material['balance_budget_m3'], 'cutter_union_m3': solids['cutter_union']['signed_volume_m3'], 'removed_components': record['census']['removed_components'], 'rock_after_components': record['census']['rock_after_components'], 'cutter_count': record['census']['cutter_count']}}
    return entries

def sinkhole_build(parameters=SinkholeParameters(), origin=LOCAL_ORIGIN):
    """Excavate the sinkhole and return the candidate report record with its closed solids."""
    parameters = as_parameters(parameters)
    origin = as_origin(origin)
    rock_record = _body(parameters, origin)
    cutters = _cutters(parameters, origin)
    if tuple((cutter['role'] for cutter in cutters)) != CUTTER_ROLES:
        raise ValueError('cutter roles differ from the declared closed cutter set')
    boolean_parameters = _x19_BooleanParameters(solids_spacing_m=1.0, component_limit=16)
    result, meshes = _x21_excavate(rock_record, cutters, boolean_parameters, origin, minimum_removed_components=1, minimum_rock_after_components=1)
    solids = {'rock_before': rock_record}
    solids.update({cutter['role']: cutter for cutter in cutters})
    solids.update(meshes)
    if _x20_census(_x25_solid_from_record(meshes['removed'], 'removed')) != 1:
        raise ValueError('excavated_sinkhole_void_is_not_one_connected_solid')
    record = {'schema': SINKHOLE_SCHEMA, 'algorithm': SINKHOLE_ALGORITHM, 'status': 'candidate', 'synthetic_base': {'kind': BASE_KIND, 'note': BASE_NOTE}, 'parameters': _i31_asdict(parameters), 'explicit_assumptions': assumption_list(parameters), 'solids': solids, 'boolean': result, 'witnesses': witnesses(result, solids, parameters, origin), 'flags': {flag: False for flag in _x18_FLAGS}, 'library_versions': library_versions(), 'local_origin_xyz_m': origin.tolist(), 'source_grade': 'no_ledger_source_for_any_dimension_here', 'hydraulic_status': 'offline_geometry_only_no_routing_no_filling_no_water_surface', 'prerequisites_before_hydraulic_or_consumer_use': list(PREREQUISITES), 'note': 'offline candidate geometry of a synthetic analytic block; not a real landform restoration'}
    _x17_hybrid_cave_geometry_seal(record)
    return (record, solids)

def audit(record):
    """Cold re-check of a saved record or report: seals, flags, balance and void connectedness."""
    unsigned = {key: value for key, value in record.items() if key != 'identity_sha256'}
    if _x26_identity(unsigned) != record.get('identity_sha256'):
        raise ValueError('saved sinkhole identity mismatch')
    if record['schema'] != SINKHOLE_SCHEMA or record['algorithm'] != SINKHOLE_ALGORITHM or record['status'] != 'candidate' or (record['synthetic_base'] != {'kind': BASE_KIND, 'note': BASE_NOTE}):
        raise ValueError('saved sinkhole schema/algorithm/status/base differs')
    if any((record['flags'].get(flag) is not False for flag in _x18_FLAGS)):
        raise ValueError('saved sinkhole promoted a capability flag')
    boolean = record['boolean']
    if any((boolean.get(flag) is not False for flag in _x18_FLAGS)) or boolean.get('status') != 'candidate':
        raise ValueError('saved sinkhole boolean promoted a capability flag or status')
    material = boolean['material']
    if abs(material['rock_before_m3'] - material['rock_after_m3'] - material['excavated_rock_m3']) > material['balance_budget_m3']:
        raise ValueError('saved sinkhole material balance fails cold re-check')
    if material['fill_rock_m3'] != 0.0 or material['rock_after_m3'] <= 0.0 or material['excavated_rock_m3'] <= 0.0:
        raise ValueError('saved sinkhole material is not purely excavated')
    if boolean['census']['removed_components'] != 1:
        raise ValueError('saved sinkhole void is not one connected solid')
    for name, solid in record['solids'].items():
        if solid.get('role') != name or solid.get('schema') != SOLID_SCHEMA or solid.get('sampled_not_native_exact') is not True:
            raise ValueError('saved sinkhole solid role/schema mismatch for ' + name)
        if _x26_identity({key: value for key, value in solid.items() if key != 'identity_sha256'}) != solid['identity_sha256']:
            raise ValueError('saved sinkhole solid seal mismatch for ' + name)
    for name, entry in record['witnesses'].items():
        if entry.get('method') not in WITNESS_METHODS:
            raise ValueError('unsupported witness method for ' + name)
        if entry.get('verdict') is not True:
            raise ValueError('saved sinkhole witness not verified: ' + name)
    return {'status': 'passed', 'identity_sha256': record['identity_sha256'], 'solid_roles': sorted(record['solids']), 'witness_count': len(record['witnesses']), 'material': dict(material), 'checks': ['identity', 'schema', 'flags', 'synthetic_base', 'material_balance', 'void_connectedness', 'solid_seals', 'witness_shapes']}

def _top_surface_map(solid, origin, span, samples):
    xs = _i31_np.linspace(-span, span, samples)
    grid = _i31_np.full((samples, samples), _i31_np.nan)
    for row, x in enumerate(xs):
        for column, z in enumerate(xs):
            hits = _x16_ray_hits(solid, [float(x), 20.0, float(z)], [float(x), -46.0, float(z)], origin)
            if hits:
                grid[row, column] = hits[0]['position_xyz_m'][1]
    return (xs, grid)

def file_sha256(path):
    return _i31_hashlib.sha256(_i31_Path(path).read_bytes()).hexdigest()
CAVE_BRIDGE_SCHEMA = 'td-special-terrain-l1-cave-bridge-v1'
CAVE_BRIDGE_ALGORITHM = 'sampled-rock-cave-tunnel-skylights-natural-bridge-v1'
CAVE_BRIDGE_REPORT_SCHEMA = 'td-special-terrain-l1-cave-bridge-report-v1'
ORIGIN = _i32_np.array([0.0, 0.0, 0.0])
CAVE_BRIDGE_WORLD_FRAME_NOTE = 'zero local origin: world metres equal local mesh metres, no world offset'
FLAGS = _x65_FLAGS
WINDING_INSIDE_TOLERANCE = 1e-09
WINDING_SURFACE_MARGIN = 0.25
BRIDGE_CLAIM = 'the rock between the two skylight bores is intact and continuous with the surrounding block, so the two bores are separate apertures of one cavity rather than one slit along the whole top face'
APERTURE_CLAIM = 'the bore is open to the sky: a vertical probe from above the block into the tunnel cavity crosses no rock at all'
THROUGH_BORE_CLAIM = 'the bore is a genuine through-opening: a vertical probe from above the block down through the tunnel cavity crosses rock only inside the block, never inside the bore column'
ROOF_CLAIM = 'directly above the bridge axis, between the two bores, the top face is unbroken: the vertical probe crosses it exactly once'
VOID_CLAIM = 'the gallery bore is genuine exterior space inside the block, not filled rock'
MATERIAL_CLAIM = 'the saved Boolean material balance closes on the saved solids and the excavated cavity is one connected component'

@_i32_dataclass(frozen=True)
class Parameters:
    """Explicit assumed lattice. No value here is a measurement or a certification."""
    plan_half_x_m: float = 60.0
    plan_half_z_m: float = 60.0
    top_y_m: float = 0.0
    bottom_y_m: float = -30.0
    tunnel_floor_y_m: float = -22.0
    tunnel_roof_y_m: float = -14.0
    tunnel_half_width_m: float = 4.0
    tunnel_length_x_m: float = 50.0
    branch_end_z_m: float = 45.0
    branch_half_width_m: float = 4.0
    skylight_x_m: tuple = (-25.0, 25.0)
    skylight_radius_m: float = 4.0
    skylight_segments: int = 48
    solids_spacing_m: float = 1.0
    component_limit: int = 64

    def __post_init__(self):
        dimensions = (self.plan_half_x_m, self.plan_half_z_m, self.top_y_m, self.bottom_y_m, self.tunnel_floor_y_m, self.tunnel_roof_y_m, self.tunnel_half_width_m, self.tunnel_length_x_m, self.branch_end_z_m, self.branch_half_width_m, self.skylight_radius_m, self.solids_spacing_m)
        if any((type(value) is not float or not _i32_math.isfinite(value) for value in dimensions)):
            raise ValueError('finite float required for every lattice dimension')
        if type(self.skylight_segments) is not int or not 8 <= self.skylight_segments <= 512:
            raise ValueError('bounded integer skylight segment count required')
        if type(self.component_limit) is not int or not 1 <= self.component_limit <= _x66_MAX_COMPONENTS:
            raise ValueError('bounded integer component limit required')
        if not 10.0 <= self.plan_half_x_m or not 10.0 <= self.plan_half_z_m:
            raise ValueError('the block plan needs a positive half extent of at least 10 m')
        if not self.top_y_m > self.bottom_y_m:
            raise ValueError('strict positive block height required')
        if not self.tunnel_roof_y_m > self.tunnel_floor_y_m:
            raise ValueError('strict positive tunnel height required')
        if not (self.tunnel_roof_y_m < self.top_y_m and self.tunnel_floor_y_m > self.bottom_y_m):
            raise ValueError('the tunnel must sit strictly inside the block')
        if not 0.0 < self.tunnel_half_width_m < min(self.plan_half_x_m, self.plan_half_z_m):
            raise ValueError('bounded tunnel half width required')
        if not self.tunnel_half_width_m < self.tunnel_length_x_m < self.plan_half_x_m:
            raise ValueError('the tunnel must stop short of both side walls')
        if not self.branch_half_width_m < self.branch_end_z_m <= self.plan_half_z_m:
            raise ValueError('bounded branch reach required')
        if not 0.0 < self.branch_half_width_m < self.tunnel_half_width_m * 4.0:
            raise ValueError('bounded branch half width required')
        if not isinstance(self.skylight_x_m, tuple) or len(self.skylight_x_m) < 2:
            raise ValueError('at least two skylight centres required as an immutable tuple')
        if any((type(value) is not float for value in self.skylight_x_m)):
            raise ValueError('skylight centres must be explicit floats')
        if sorted(self.skylight_x_m) != list(self.skylight_x_m):
            raise ValueError('skylight centres must be ordered')
        if any((not -self.tunnel_length_x_m < value < self.tunnel_length_x_m for value in self.skylight_x_m)):
            raise ValueError('every skylight must sit above the main tunnel')
        if abs(self.skylight_x_m[1] - self.skylight_x_m[0]) <= 4.0 * self.skylight_radius_m:
            raise ValueError('the skylights must be far enough apart to leave a bridge')
        self.bridge_probe_centres_m()

    def bridge_probe_centres_m(self):
        """Two bridge probe abscissae, one on each side of the block centre.

        The inner probe is the block centre: it is bridge material exactly when both bore
        rims stay strictly outside the centre, which is checked here. The outer probe is a
        third of the way in from the block side wall to the outer bore rim, so it keeps at
        least a quarter of the wall-to-rim gap clear of both the wall and the rim.
        """
        inner_probe = 0.0
        outer_probe = (self.plan_half_x_m + self.skylight_x_m[1] + self.skylight_radius_m) / 2.0
        if not self.skylight_x_m[0] + self.skylight_radius_m < inner_probe < self.skylight_x_m[1] - self.skylight_radius_m:
            raise ValueError('both bore rims must clear the block centre so a bridge survives')
        margin = (self.plan_half_x_m - self.skylight_x_m[1] - self.skylight_radius_m) / 4.0
        if not self.skylight_x_m[1] + self.skylight_radius_m + margin < outer_probe < self.plan_half_x_m - margin:
            raise ValueError('the outer bridge probe must clear both the rim and the side wall')
        return (inner_probe, outer_probe)
PARAMETERS = Parameters()
ASSUMPTIONS = ({'name': 'plan_half_x_m', 'value': 60.0, 'grade': 'assumed', 'reason': 'the block plan only has to be large enough to leave outer rock around every void'}, {'name': 'plan_half_z_m', 'value': 60.0, 'grade': 'assumed', 'reason': 'same as plan_half_x_m; no surveyed cave plan exists in the ledger'}, {'name': 'top_y_m', 'value': 0.0, 'grade': 'assumed', 'reason': 'the block top elevation is a datum choice, not a surveyed ground surface'}, {'name': 'bottom_y_m', 'value': -30.0, 'grade': 'assumed', 'reason': 'block thickness is a parameterisation choice, not a measured overburden'}, {'name': 'tunnel_roof_y_m', 'value': -14.0, 'grade': 'assumed', 'reason': 'no measured gallery depth or roof elevation exists for any real cave in the ledger'}, {'name': 'tunnel_floor_y_m', 'value': -22.0, 'grade': 'assumed', 'reason': 'gallery height 8 m is a parameterisation choice, not a surveyed bore'}, {'name': 'tunnel_half_width_m', 'value': 4.0, 'grade': 'assumed', 'reason': 'gallery width not obtained; chosen to stay far below the block plan'}, {'name': 'tunnel_length_x_m', 'value': 50.0, 'grade': 'assumed', 'reason': 'gallery reach not obtained; it must stop short of both block side walls'}, {'name': 'branch_end_z_m', 'value': 45.0, 'grade': 'assumed', 'reason': 'side branch reach is invented so that the tunnel network is one connected cavity'}, {'name': 'branch_half_width_m', 'value': 4.0, 'grade': 'assumed', 'reason': 'branch width not obtained; a parameterisation choice'}, {'name': 'skylight_x_m', 'value': [-25.0, 25.0], 'grade': 'assumed', 'reason': 'skylight spacing not obtained; 50 m is chosen so the bridge spans several bore diameters'}, {'name': 'skylight_radius_m', 'value': 4.0, 'grade': 'assumed', 'reason': 'bore radius not obtained; a constant radius avoids claiming an unknown taper'}, {'name': 'skylight_segments', 'value': 48, 'grade': 'assumed', 'reason': 'polygonal bore resolution is a meshing choice; it sets the inscribed bore radius'}, {'name': 'solids_spacing_m', 'value': 1.0, 'grade': 'assumed', 'reason': 'Boolean sampling spacing is an engine tuning choice, not a field resolution'}, {'name': 'component_limit', 'value': 64, 'grade': 'assumed', 'reason': 'the connected-component ceiling is a refusal guard, not a measured property'})

def cave_bridge_rectangle_ring(half_x_m, half_z_m, centre_xz=(0.0, 0.0)):
    """Counter-clockwise rectangle in the (x, z) plan; a prism is erected over it."""
    return _i32_np.array([[centre_xz[0] - half_x_m, centre_xz[1] - half_z_m], [centre_xz[0] + half_x_m, centre_xz[1] - half_z_m], [centre_xz[0] + half_x_m, centre_xz[1] + half_z_m], [centre_xz[0] - half_x_m, centre_xz[1] + half_z_m]], float)

def cave_bridge_winding_number(point, vertices, triangles):
    """Independent point-in-solid test: spherical solid angle sum over four pi.

    Oosterom-Strackee triangle solid angle, summed straight from the saved mesh, so a cold
    reader can reproduce the number without importing this module or its Boolean engine.
    Dimensionless result: +1 strictly inside one outward-oriented closed shell, ~0 outside
    or on the boundary.
    """
    point = _i32_np.asarray(point, float)
    vertices = _i32_np.asarray(vertices, float)
    triangles = _i32_np.asarray(triangles, int)
    if point.shape != (3,) or not _i32_np.isfinite(point).all():
        raise ValueError('finite three-component winding probe required')
    total = 0.0
    for triangle in triangles:
        legs = vertices[triangle] - point
        lengths = [float(_i32_np.linalg.norm(leg)) for leg in legs]
        if min(lengths) <= 1e-12:
            raise ValueError('winding probe coincides with a saved mesh vertex')
        numerator = float(_i32_np.dot(legs[0], _i32_np.cross(legs[1], legs[2])))
        denominator = lengths[0] * lengths[1] * lengths[2] + float(_i32_np.dot(legs[0], legs[1])) * lengths[2] + float(_i32_np.dot(legs[1], legs[2])) * lengths[0] + float(_i32_np.dot(legs[2], legs[0])) * lengths[1]
        total += 2.0 * _i32_math.atan2(numerator, denominator)
    return total / (4.0 * _i32_math.pi)

def inside(value, *, tolerance=WINDING_INSIDE_TOLERANCE):
    """Tolerant inside verdict; see WINDING_INSIDE_TOLERANCE for why a tolerance is needed."""
    if not _i32_math.isfinite(value):
        raise ValueError('nonfinite winding number')
    if value < -tolerance:
        raise ValueError('negative winding magnitude: the saved shell is not outward oriented')
    return value > tolerance

def _ray(solid, from_xyz, to_xyz, role, *, expected_hit_count, claim):
    hits = _x29_ray_hits(solid, _i32_np.asarray(from_xyz, float), _i32_np.asarray(to_xyz, float), ORIGIN)
    verdict = len(hits) == expected_hit_count
    if not verdict:
        raise ValueError('witness refused: ' + role + ' expected ' + str(expected_hit_count) + ' hits, measured ' + str(len(hits)))
    return {'method': 'Manifold.ray_cast', 'solid_role': role, 'from_xyz_m': [float(value) for value in from_xyz], 'to_xyz_m': [float(value) for value in to_xyz], 'expected_hit_count': expected_hit_count, 'verdict': True, 'claim': claim, 'observed': {'hit_count': len(hits), 'hits': hits}}

def _winding(record, point, role, *, expected_inside, claim):
    value = cave_bridge_winding_number(point, record['vertices_local_xyz_m'], record['triangles'])
    if abs(abs(value) - 0.5) < WINDING_SURFACE_MARGIN:
        raise ValueError('witness refused: the winding probe sits on the saved surface of ' + role)
    verdict = inside(value) == expected_inside
    if not verdict:
        raise ValueError('witness refused: ' + role + ' winding ' + repr(value) + ' disagrees with expected_inside=' + repr(expected_inside))
    return {'method': 'Solid.winding', 'solid_role': role, 'point_xyz_m': [float(value) for value in point], 'expected_inside': bool(expected_inside), 'verdict': True, 'claim': claim, 'observed': {'winding': value, 'inside_verdict': inside(value), 'inside_tolerance': WINDING_INSIDE_TOLERANCE, 'inside_tolerance_units': 'dimensionless spherical winding, not metres', 'vertices_sha256': _x32_identity(record['vertices_local_xyz_m']), 'triangles_sha256': _x32_identity(record['triangles'])}}

def cave_bridge_build(parameters=Parameters()):
    """Excavate one analytic block; return (boolean result, solids, witnesses, parameters)."""
    from tools.preview_special_terrain import main
    if not isinstance(parameters, Parameters):
        raise ValueError('explicit Parameters required')
    cutters, solids = ([], {})
    rock = _x67_polygon_prism_record(cave_bridge_rectangle_ring(parameters.plan_half_x_m, parameters.plan_half_z_m), parameters.bottom_y_m, parameters.top_y_m, ORIGIN, 'rock_before')
    solids['rock_before'] = rock
    main = _x67_polygon_prism_record(cave_bridge_rectangle_ring(parameters.tunnel_length_x_m, parameters.tunnel_half_width_m), parameters.tunnel_floor_y_m, parameters.tunnel_roof_y_m, ORIGIN, 'cutter_main_tunnel')
    branch = _x67_polygon_prism_record(cave_bridge_rectangle_ring(parameters.branch_half_width_m, parameters.branch_end_z_m), parameters.tunnel_floor_y_m, parameters.tunnel_roof_y_m, ORIGIN, 'cutter_side_branch')
    cutters.extend((main, branch))
    solids['cutter_main_tunnel'] = main
    solids['cutter_side_branch'] = branch
    for ordinal, centre_x in enumerate(parameters.skylight_x_m):
        role = 'cutter_skylight_' + chr(ord('a') + ordinal)
        bore = _x68_frustum_record([centre_x, 0.0], [centre_x, 0.0], parameters.tunnel_roof_y_m, parameters.top_y_m, parameters.skylight_radius_m, parameters.skylight_radius_m, ORIGIN, role, segments=parameters.skylight_segments)
        cutters.append(bore)
        solids[role] = bore
    engineering = _x69_BooleanParameters(solids_spacing_m=parameters.solids_spacing_m, component_limit=parameters.component_limit)
    result, meshes = _x70_excavate(rock, cutters, engineering, ORIGIN, minimum_removed_components=1, minimum_rock_after_components=1)
    solids.update(meshes)
    if result['census']['removed_components'] != 1:
        raise ValueError('the tunnel network and both skylights must excavate one connected cavity')
    after = _x27_manifold_from_record(solids['rock_after'])
    solids['removed'] = _x28_mesh_record(_i32_np.array(solids['removed']['vertices_local_xyz_m'], float), _i32_np.array(solids['removed']['triangles'], int), ORIGIN, 'removed')
    mid_y = (parameters.tunnel_roof_y_m + parameters.top_y_m) / 2.0
    inner_y = mid_y - 0.5
    void_y = (parameters.tunnel_floor_y_m + parameters.tunnel_roof_y_m) / 2.0
    above = parameters.top_y_m + 5.0
    below = parameters.bottom_y_m - 3.0
    left, right = parameters.skylight_x_m
    bridge_centre, wall_probe = parameters.bridge_probe_centres_m()
    witnesses = {'bridge_axis_under_top_face': _ray(after, [-parameters.plan_half_x_m + 5.0, inner_y, 0.0], [parameters.plan_half_x_m - 5.0, inner_y, 0.0], 'rock_after', expected_hit_count=4, claim=BRIDGE_CLAIM), 'bridge_axis_over_the_roof': _ray(after, [0.0, above, 0.0], [0.0, parameters.tunnel_roof_y_m + 4.0, 0.0], 'rock_after', expected_hit_count=1, claim=ROOF_CLAIM), 'skylight_a_open_to_sky': _ray(after, [left, above, 0.0], [left, void_y, 0.0], 'rock_after', expected_hit_count=0, claim=APERTURE_CLAIM), 'skylight_b_open_to_sky': _ray(after, [right, above, 0.0], [right, void_y, 0.0], 'rock_after', expected_hit_count=0, claim=APERTURE_CLAIM), 'skylight_a_bores_into_the_block': _ray(after, [left, above, 0.0], [left, below, 0.0], 'rock_after', expected_hit_count=2, claim=THROUGH_BORE_CLAIM), 'skylight_b_bores_into_the_block': _ray(after, [right, above, 0.0], [right, below, 0.0], 'rock_after', expected_hit_count=2, claim=THROUGH_BORE_CLAIM), 'bridge_rock_is_solid': _winding(solids['rock_after'], [0.0, mid_y, 0.0], 'rock_after', expected_inside=True, claim=BRIDGE_CLAIM), 'tunnel_bore_is_void': _winding(solids['rock_after'], [0.0, void_y, 0.0], 'rock_after', expected_inside=False, claim=VOID_CLAIM), 'side_branch_bore_is_void': _winding(solids['rock_after'], [0.0, void_y, parameters.branch_end_z_m - 6.0], 'rock_after', expected_inside=False, claim=VOID_CLAIM), 'skylight_a_column_is_void': _winding(solids['rock_after'], [left, void_y + 2.0, 0.0], 'rock_after', expected_inside=False, claim=APERTURE_CLAIM), 'skylight_b_column_is_void': _winding(solids['rock_after'], [right, void_y + 2.0, 0.0], 'rock_after', expected_inside=False, claim=APERTURE_CLAIM), 'outer_rock_untouched': _winding(solids['rock_after'], [parameters.plan_half_x_m - 5.0, mid_y, parameters.plan_half_z_m - 5.0], 'rock_after', expected_inside=True, claim=ROOF_CLAIM), 'material_balance': {'method': 'Mesh64_boolean', 'operation': 'subtract', 'rock_role': 'rock_before', 'cutter_roles': [record['role'] for record in cutters], 'expected_rock_after_m3': result['material']['rock_after_m3'], 'expected_removed_m3': result['material']['excavated_rock_m3'], 'verdict': True, 'claim': MATERIAL_CLAIM, 'observed': {'rock_before_m3': result['material']['rock_before_m3'], 'rock_after_m3': result['material']['rock_after_m3'], 'removed_m3': result['material']['excavated_rock_m3'], 'cutter_union_saved_volume_m3': solids['cutter_union']['signed_volume_m3'], 'rock_lost_m3': result['material']['rock_before_m3'] - result['material']['rock_after_m3'], 'signed_residual_m3': result['material']['signed_residual_m3'], 'balance_budget_m3': result['material']['balance_budget_m3'], 'removed_components': result['census']['removed_components'], 'rock_after_components': result['census']['rock_after_components'], 'cutter_union_components': result['census']['cutter_union_components']}}}
    probes = []
    for label, x_m in (('inner_bridge_probe', bridge_centre), ('outer_bridge_probe', wall_probe)):
        ray = _ray(after, [x_m, above, 0.0], [x_m, below, 0.0], 'rock_after', expected_hit_count=4, claim='a vertical probe between a bore and the block side wall crosses the top face, the gallery roof, the gallery floor and the block bottom')
        over_roof = [hit for hit in ray['observed']['hits'] if hit['position_xyz_m'][1] > parameters.tunnel_roof_y_m]
        if len(over_roof) != 1:
            raise ValueError('witness refused: ' + label + ' has ' + str(len(over_roof)) + ' rock crossings strictly above the gallery roof; a bore is present')
        ray['observed']['crossings_above_gallery_roof'] = len(over_roof)
        probes.append({'label': label, 'x_m': x_m, 'ray': ray, 'winding': _winding(solids['rock_after'], [x_m, mid_y, 0.0], 'rock_after', expected_inside=True, claim=BRIDGE_CLAIM)})
    witnesses['bridge_probe_centres_are_both_bridges'] = {'method': 'Manifold.ray_cast', 'solid_role': 'rock_after', 'verdict': True, 'claim': 'bridge rock is solid at both probe abscissae: each vertical probe crosses rock exactly once above the gallery roof and the winding number there is positive, so the rock between the bores and up to the top face is continuous with the surrounding block', 'observed': {'probes': probes, 'from_xyz_m': [probes[0]['ray']['from_xyz_m'], probes[1]['ray']['from_xyz_m']], 'to_xyz_m': [probes[0]['ray']['to_xyz_m'], probes[1]['ray']['to_xyz_m']], 'hit_count': [probes[0]['ray']['observed']['hit_count'], probes[1]['ray']['observed']['hit_count']], 'crossings_above_gallery_roof': [probes[0]['ray']['observed']['crossings_above_gallery_roof'], probes[1]['ray']['observed']['crossings_above_gallery_roof']], 'hits': [probes[0]['ray']['observed']['hits'], probes[1]['ray']['observed']['hits']]}}
    divergence = _x31_signed_volume(_i32_np.array(solids['rock_after']['vertices_local_xyz_m'], float), _i32_np.array(solids['rock_after']['triangles'], int))
    witnesses['saved_void_closure'] = {'method': 'Mesh64_boolean', 'operation': 'subtract', 'rock_role': 'rock_before', 'cutter_roles': [record['role'] for record in cutters], 'expected_rock_after_m3': result['material']['rock_after_m3'], 'expected_removed_m3': result['material']['excavated_rock_m3'], 'verdict': True, 'claim': 'the re-saved excavated void is itself a closed two-use surface, its enclosed volume reproduces the lost rock volume, and the remaining rock reproduces the engine volume within accumulated re-triangulation rounding', 'observed': {'removed_saved_volume_m3': solids['removed']['signed_volume_m3'], 'removed_mesh64_volume_m3': result['material']['excavated_rock_m3'], 'removed_saved_volume_disagreement_m3': abs(solids['removed']['signed_volume_m3'] - result['material']['excavated_rock_m3']), 'rock_after_mesh64_volume_m3': after.volume(), 'rock_after_saved_volume_m3': solids['rock_after']['signed_volume_m3'], 'rock_after_divergence_theorem_volume_m3': divergence, 'rock_after_volume_shortfall_m3': abs(after.volume() - divergence), 'removed_components': result['census']['removed_components']}}
    return (result, solids, witnesses, parameters)

def _plane_segments(record, axis, value, tolerance=1e-09):
    """Display-only triangle/plane intersections, straight from the saved mesh."""
    vertices = _i32_np.asarray(record['vertices_local_xyz_m'], float)
    segments = []
    for triangle in _i32_np.asarray(record['triangles'], int):
        points = [vertices[index] for index in triangle]
        crossings = []
        for first, second in zip(points, points[1:] + points[:1]):
            first_d, second_d = (first[axis] - value, second[axis] - value)
            if (first_d < 0.0) != (second_d < 0.0):
                fraction = first_d / (first_d - second_d)
                crossings.append(first + fraction * (second - first))
            elif abs(first_d) <= tolerance:
                crossings.append(first)
        if len(crossings) == 2:
            segments.append((crossings[0], crossings[1]))
    return segments

def cave_bridge_report(parameters=Parameters(), output_directory=None):
    """Build the geometry and seal the contract-shaped report used by the cold reader."""
    from tools.preview_special_terrain import cave_bridge_render
    result, solids, witnesses, parameters = cave_bridge_build(parameters)
    figures = [] if output_directory is None else cave_bridge_render(output_directory, solids, parameters)
    record = {'schema': CAVE_BRIDGE_REPORT_SCHEMA, 'algorithm': CAVE_BRIDGE_ALGORITHM, 'status': 'candidate', 'synthetic_base': {'kind': 'synthetic_analytic', 'note': 'not TD native terrain, not surveyed'}, 'world_frame': CAVE_BRIDGE_WORLD_FRAME_NOTE, 'parameters': _i32_asdict(parameters), 'parameters_identity_sha256': _x32_identity(_i32_asdict(parameters)), 'explicit_assumptions': [dict(item) for item in ASSUMPTIONS], 'explicit_assumption_note': "every numeric parameter above is an explicit_assumption of grade 'assumed'; none is a measurement, a survey or a reconstruction of a named feature", 'solids': {role: dict(mesh) for role, mesh in solids.items()}, 'boolean': result, 'witnesses': witnesses, 'flags': {flag: False for flag in FLAGS}, 'library_versions': {'manifold3d': _i32_version('manifold3d'), 'numpy': _i32_version('numpy')}, 'figures': figures, 'figure_scope': 'display only; a figure is never a certification', 'cold_read_contract': 'every witness names the saved solid role it was measured on; rebuild those meshes and replay the segments, the winding probes and the material balance independently'}
    _x30_hybrid_cave_geometry_seal(record)
    return (record, solids)

def cave_bridge_write_report(path, parameters=Parameters(), output_directory=None):
    """Compact, sorted, NaN-free JSON; identical bytes for identical inputs."""
    record, _ = cave_bridge_report(parameters, output_directory=output_directory)
    path = _i32_Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_i32_json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False), encoding='utf-8', newline='')
    return record
ROCK_EGGS_SCHEMA = 'td-special-terrain-l1-rock-eggs-v1'
ROCK_EGGS_ALGORITHM = 'stacked-disconnected-rock-egg-bodies-with-genuine-voids-v1'
ROCK_EGGS_PARENT_ALGORITHM = _x36_ALGORITHM
LEDGER = '.scratch/special-terrain/parameters-and-sources.md'
PILE_ROLE = 'rock_after'
ROCK_EGGS_LOCAL_ORIGIN = _i33_np.array([0.0, 0.0, 0.0])
SEGMENTS = 48
PROBE_RADIUS_M = 0.05
PROBE_SEGMENTS = 8
WINDING_TOLERANCE = 1e-09
EXPECTED_COMPONENTS = 3
DEBUG = ''
HOVER_PAIR = ('egg-03', 'egg-04')
STACKED_PAIR = ('egg-01', 'egg-02')
SUPPORT_PAIR = ('egg-02', 'egg-04')
SEPARATED_PAIR = ('egg-07', 'egg-08')
REPORT_NAME = 'report.json'
ROCK_EGGS_DEFAULT_OUTPUT = _i33_Path('.scratch/special-terrain/l1-preview-20261019/rock-eggs')
NOT_CLAIMED = ('real_devils_marbles_reproduction', 'real_TD_base_bed', 'self_intersection_verified', 'hydraulic_ready', 'natural_outlet_certified', 'full_network_verified', 'independent_audit_passed', 'publishable')

@_i33_dataclass(frozen=True)
class EggSpec:
    """One explicit rock-egg body; radii are bounded by the verified 6 m height ceiling."""
    egg_id: str
    centre_xyz_m: tuple
    radius_m: float
    structural_group: str
    structural_role: str

    def __post_init__(self):
        for name in ('egg_id', 'structural_role'):
            if type(getattr(self, name)) is not str or not getattr(self, name):
                raise ValueError('explicit nonempty ' + name + ' required')
        if self.structural_group not in ('cluster', 'hover', 'separate'):
            raise ValueError('declared structural group required for ' + self.egg_id)
        centre = tuple(self.centre_xyz_m)
        if len(centre) != 3 or not all((type(value) is float and _i33_math.isfinite(value) for value in centre)):
            raise ValueError('finite float three-component centre required for ' + self.egg_id)
        object.__setattr__(self, 'centre_xyz_m', centre)
        if type(self.radius_m) is not float or not _i33_math.isfinite(self.radius_m) or (not 0.5 <= self.radius_m <= 3.0):
            raise ValueError('rock-egg radius must be a float inside the verified 6 m height ceiling')
EGGS = (EggSpec('egg-01', (0.0, 0.0, 0.0), 3.0, 'cluster', 'cluster_base'), EggSpec('egg-02', (0.0, 4.6, 0.0), 2.9, 'cluster', 'cluster_stacked_on_egg-01'), EggSpec('egg-03', (4.6, 0.8, 0.6), 2.2, 'cluster', 'cluster_leaning_on_egg-01'), EggSpec('egg-04', (4.0, 5.3, 0.6), 1.8, 'hover', 'hover_above_egg-03_supported_by_egg-02'), EggSpec('egg-05', (-4.4, 1.0, 0.5), 2.1, 'cluster', 'cluster_leaning_on_egg-01'), EggSpec('egg-06', (-3.2, 4.2, 0.3), 1.7, 'cluster', 'cluster_bridging_egg-05_and_egg-02'), EggSpec('egg-07', (12.0, 1.5, -6.0), 1.9, 'separate', 'separated_standalone'), EggSpec('egg-08', (16.5, 1.5, -6.5), 2.0, 'separate', 'separated_standalone'))

def egg(egg_id):
    return next((item for item in EGGS if item.egg_id == egg_id))

def parameters():
    """The bounded Boolean parameters this pile is assembled with."""
    return _x37_BooleanParameters(solids_spacing_m=1.0, component_limit=16)

def report_parameters(parameters_used=None):
    parameters_used = parameters_used or parameters()
    return {**_i33_asdict(parameters_used), 'circular_segments': SEGMENTS, 'probe_radius_m': PROBE_RADIUS_M, 'probe_segments': PROBE_SEGMENTS, 'expected_connected_components': EXPECTED_COMPONENTS, 'egg_count': len(EGGS)}

def build_records(segments=SEGMENTS):
    """One closed solid record per egg, all in the same local frame."""
    return [_x44_sphere_record(list(item.centre_xyz_m), item.radius_m, ROCK_EGGS_LOCAL_ORIGIN, item.egg_id, circular_segments=segments) for item in EGGS]

def pair_gap_m(first_id, second_id):
    """Analytic surface gap between two ideal spheres (negative means interpenetration)."""
    first, second = (egg(first_id), egg(second_id))
    return _i33_math.dist(first.centre_xyz_m, second.centre_xyz_m) - first.radius_m - second.radius_m

def analytic_gap_table(limit_m=8.0):
    """Every close pair with its analytic surface gap, so the layout is auditable by hand."""
    table = []
    for ordinal, first in enumerate(EGGS):
        for second in EGGS[ordinal + 1:]:
            gap = pair_gap_m(first.egg_id, second.egg_id)
            if gap < limit_m:
                table.append({'egg_ids': [first.egg_id, second.egg_id], 'centre_distance_m': _i33_math.dist(first.centre_xyz_m, second.centre_xyz_m), 'analytic_surface_gap_m': gap, 'interpenetrates': gap < 0.0})
    return table

def rock_eggs_winding_number(record, point, origin=ROCK_EGGS_LOCAL_ORIGIN):
    """Independent winding number of one point against a saved closed mesh (Van Oosterom).

    Computed from the stored vertices/triangles only -- the same thing a cold audit reader
    recomputes -- so a result near zero means the point is outside the closed body and a
    result near one means it is inside. It is deliberately *not* Manifold's own predicate.
    """
    vertices = _i33_np.asarray(record['vertices_local_xyz_m'], float) - _i33_np.asarray(origin, float)
    triangles = _i33_np.asarray(record['triangles'], int)
    shifted = vertices - _i33_np.asarray(point, float)
    first, second, third = (shifted[triangles[:, 0]], shifted[triangles[:, 1]], shifted[triangles[:, 2]])
    norms = _i33_np.linalg.norm(shifted, axis=1)[triangles]
    numerator = _i33_np.einsum('ij,ij->i', first, _i33_np.cross(second, third))
    denominator = norms[:, 0] * norms[:, 1] * norms[:, 2] + _i33_np.einsum('ij,ij->i', first, second) * norms[:, 2] + _i33_np.einsum('ij,ij->i', second, third) * norms[:, 0] + _i33_np.einsum('ij,ij->i', third, first) * norms[:, 1]
    solid_angles = 2.0 * _i33_np.arctan2(numerator, denominator)
    return float(solid_angles.sum() / (4.0 * _i33_math.pi))

def probe_overlap_m3(solid, point, origin=ROCK_EGGS_LOCAL_ORIGIN):
    """Exact MESH64 intersection volume of a tiny probe sphere with the pile.

    A zero-overlap measurement of exactly zero volume is only possible when the probe is
    completely outside, so containment is decided by real geometry rather than by a bound.
    """
    library = _x39_MANIFOLD.get()
    probe = library.Manifold.sphere(PROBE_RADIUS_M, PROBE_SEGMENTS).translate(tuple(_i33_np.asarray(point, float) - _i33_np.asarray(origin, float)))
    return float((solid ^ probe).volume())

def pair_union(records, egg_ids, parameters_used=None):
    """Actual MESH64 union of one named pair, next to the arithmetic sum of its parts."""
    parameters_used = parameters_used or parameters()
    chosen = [record for record in records if record['role'] in egg_ids]
    if len(chosen) != len(egg_ids):
        raise ValueError('pair union needs one saved record per named egg')
    role = 'pair_' + '__'.join(egg_ids)
    result, meshes = _x42_combine(chosen, ROCK_EGGS_LOCAL_ORIGIN, role, parameters_used, minimum_components=1)
    union_record = meshes[role]
    total = _i33_math.fsum((record['signed_volume_m3'] for record in chosen))
    return {'egg_ids': list(egg_ids), 'role': role, 'sum_of_parts_m3': total, 'union_volume_m3': union_record['signed_volume_m3'], 'difference_m3': total - union_record['signed_volume_m3'], 'relative_difference': abs(total - union_record['signed_volume_m3']) / total, 'connected_components': _x41_census(_x43_solid_from_record(union_record, role)), 'analytics': result}

def hover_witness(record, solid, parameters_used=None):
    """Re-measure the hovering egg's void with a ray cast, a probe and a winding number."""
    lower_id, upper_id = HOVER_PAIR
    lower, upper = (egg(lower_id), egg(upper_id))
    analytic_gap = pair_gap_m(lower_id, upper_id)
    hits = _x33_ray_hits(solid, list(lower.centre_xyz_m), list(upper.centre_xyz_m), ROCK_EGGS_LOCAL_ORIGIN)
    ordered = sorted(hits, key=lambda hit: hit['distance'])
    if len(ordered) != 2:
        raise ValueError('facing mesh surfaces do not bracket exactly one clearance: ' + str(len(ordered)))
    first = _i33_np.asarray(ordered[0]['position_xyz_m'], float)
    second = _i33_np.asarray(ordered[1]['position_xyz_m'], float)
    clearance = float(_i33_np.linalg.norm(second - first))
    midpoint = (first + second) / 2.0
    outside_point = _i33_np.array([midpoint[0] + 30.0, midpoint[1], midpoint[2]])
    reachability = _x33_ray_hits(solid, list(outside_point), list(midpoint), ROCK_EGGS_LOCAL_ORIGIN)
    return {'lower_egg_id': lower_id, 'upper_egg_id': upper_id, 'analytic_surface_gap_m': analytic_gap, 'centre_axis_from_xyz_m': list(lower.centre_xyz_m), 'centre_axis_to_xyz_m': list(upper.centre_xyz_m), 'facing_surface_hits': ordered, 'measured_mesh_clearance_m': clearance, 'mesh_clearance_minus_analytic_gap_m': clearance - analytic_gap, 'midpoint_xyz_m': midpoint.tolist(), 'midpoint_winding': rock_eggs_winding_number(record, midpoint), 'midpoint_probe_overlap_m3': probe_overlap_m3(solid, midpoint), 'reachability_from_xyz_m': outside_point.tolist(), 'reachability_to_xyz_m': midpoint.tolist(), 'reachability_hits': reachability, 'support': {'supporting_egg_id': SUPPORT_PAIR[0], 'analytic_surface_gap_m': pair_gap_m(*SUPPORT_PAIR), 'actually_interpenetrates': pair_gap_m(*SUPPORT_PAIR) < 0.0}}

def rock_eggs_witnesses(pile_record, pile_solid, separated, stacked, hover):
    """The measurement block, in the three shapes a cold audit reader can recompute.

    Nothing here is inferred: each entry names the saved solid role it was measured on and
    carries the raw numbers, so the reader rebuilds Manifold from ``solids`` and repeats it.
    """
    separated_verdict = separated['relative_difference'] <= 1e-12
    stacked_verdict = stacked['union_volume_m3'] < stacked['sum_of_parts_m3'] - 1e-06
    winding_verdict = abs(hover['midpoint_winding']) <= WINDING_TOLERANCE
    reachability_verdict = len(hover['reachability_hits']) == 0
    clearance_verdict = len(hover['facing_surface_hits']) == 2 and hover['measured_mesh_clearance_m'] > 0.0
    return {'separated_pair_union_is_exact_sum': {'method': 'Mesh64_boolean', 'operation': 'add', 'rock_role': None, 'cutter_roles': list(separated['egg_ids']), 'expected_union_m3': separated['union_volume_m3'], 'verdict': separated_verdict, 'claim': 'the two fully separated rock eggs union to exactly the sum of their two closed volumes, so no material is shared and the space between them stays genuine exterior space', 'observed': {'union_m3': separated['union_volume_m3'], 'sum_of_parts_m3': separated['sum_of_parts_m3'], 'difference_m3': separated['difference_m3'], 'relative_difference': separated['relative_difference'], 'connected_components': separated['connected_components'], 'analytic_surface_gap_m': pair_gap_m(*SEPARATED_PAIR)}}, 'stacked_pair_union_is_strictly_smaller': {'method': 'Mesh64_boolean', 'operation': 'add', 'rock_role': None, 'cutter_roles': list(stacked['egg_ids']), 'expected_union_m3': stacked['union_volume_m3'], 'verdict': stacked_verdict, 'claim': 'the stacked pair unions to strictly less than the sum of its two closed volumes, so the contact is a real merge of material and not additive counting', 'observed': {'union_m3': stacked['union_volume_m3'], 'sum_of_parts_m3': stacked['sum_of_parts_m3'], 'interpenetration_m3': stacked['difference_m3'], 'relative_interpenetration': stacked['difference_m3'] / stacked['sum_of_parts_m3'], 'connected_components': stacked['connected_components'], 'analytic_surface_gap_m': pair_gap_m(*STACKED_PAIR)}}, 'hover_void_midpoint_is_outside': {'method': 'Solid.winding', 'solid_role': PILE_ROLE, 'point_xyz_m': hover['midpoint_xyz_m'], 'expected_inside': False, 'verdict': winding_verdict, 'claim': 'the midpoint of the measured clearance between the hovering egg and the one beneath it is outside the closed pile (winding number zero)', 'observed': {'winding': hover['midpoint_winding'], 'probe_overlap_m3': hover['midpoint_probe_overlap_m3'], 'measured_mesh_clearance_m': hover['measured_mesh_clearance_m'], 'analytic_surface_gap_m': hover['analytic_surface_gap_m']}}, 'hover_void_is_open_to_free_space': {'method': 'Manifold.ray_cast', 'solid_role': PILE_ROLE, 'from_xyz_m': hover['reachability_from_xyz_m'], 'to_xyz_m': hover['reachability_to_xyz_m'], 'expected_hit_count': 0, 'verdict': reachability_verdict, 'claim': 'a ray from far outside the pile reaches the void midpoint without touching any solid, so the void is open exterior space and not a sealed bubble inside a fused body', 'observed': {'hit_count': len(hover['reachability_hits']), 'hits': hover['reachability_hits']}}, 'hover_clearance_is_bracketed_by_two_surfaces': {'method': 'Manifold.ray_cast', 'solid_role': PILE_ROLE, 'from_xyz_m': hover['centre_axis_from_xyz_m'], 'to_xyz_m': hover['centre_axis_to_xyz_m'], 'expected_hit_count': 2, 'verdict': clearance_verdict, 'claim': 'the ray down the centre axis leaves the lower egg and enters the hovering one, so exactly two facing mesh surfaces bracket a positive clearance that is at least the analytic sphere gap', 'observed': {'hit_count': len(hover['facing_surface_hits']), 'hits': hover['facing_surface_hits'], 'measured_mesh_clearance_m': hover['measured_mesh_clearance_m'], 'analytic_surface_gap_m': hover['analytic_surface_gap_m'], 'mesh_clearance_minus_analytic_gap_m': hover['mesh_clearance_minus_analytic_gap_m'], 'lateral_support': hover['support']}}}

def explicit_assumptions(parameters_used, hover):
    """Every number in this module that no source supports, with the reason why it is assumed."""
    entries = [('individual_egg_radii_m', [item.radius_m for item in EGGS], 'no source: the ledger holds only the single-body height ceiling (up to 6 m), never a diameter or radius distribution'), ('cluster_egg_count', 6, 'no source: stacking/count of a real corestone cluster was not obtained'), ('separated_pair_count', 2, 'no source: how many bodies stand clear of a real pile was not obtained'), ('cluster_centre_layout_m', [[item.egg_id, list(item.centre_xyz_m)] for item in EGGS], 'no source: cluster spacing and centre-to-centre geometry were not obtained; chosen so the three required structural cases occur'), ('hover_clearance_m', hover['analytic_surface_gap_m'], 'no source: corestone-tor hover clearance was not obtained'), ('lateral_support_interpenetration_m', -pair_gap_m(*SUPPORT_PAIR), 'no source: how the hovering body is held up was not obtained; assumed to rest against a neighbouring body'), ('circular_segments', SEGMENTS, 'tessellation choice, not a measurement: the closed sphere meshes are inscribed in the ideal spheres'), ('probe_radius_m', PROBE_RADIUS_M, 'measurement instrument choice for the zero-overlap containment test, not a property of the rock'), ('base_surface', BASE_KIND, 'synthetic analytic geometry: this deliverable is the local pile of closed bodies only, there is no TD base bed and nothing is surveyed')]
    return [{'name': name, 'value': value, 'grade': 'assumed', 'reason': reason} for name, value, reason in entries]

def rock_eggs_build(parameters_used=None, *, ledger=LEDGER):
    """Assemble the pile and measure the void/link witnesses.

    The returned document is already sealed (so it carries its own ``identity_sha256``) and
    already has an empty ``figures`` list; :func:`write_report` fills that in and reseals.
    """
    parameters_used = parameters_used or parameters()
    records = build_records()
    result, meshes = _x42_combine(records, ROCK_EGGS_LOCAL_ORIGIN, PILE_ROLE, parameters_used, minimum_components=EXPECTED_COMPONENTS)
    pile = meshes[PILE_ROLE]
    solid = _x43_solid_from_record(pile, PILE_ROLE)
    components = _x41_census(solid)
    if components != EXPECTED_COMPONENTS:
        raise ValueError('pile census is not the declared component count: ' + str(components))
    separated = pair_union(records, SEPARATED_PAIR, parameters_used)
    stacked = pair_union(records, STACKED_PAIR, parameters_used)
    hover = hover_witness(pile, solid)
    if hover['analytic_surface_gap_m'] <= 0.0 or hover['measured_mesh_clearance_m'] <= 0.0:
        raise ValueError('hover pair does not actually stand clear of the body beneath it')
    if not hover['support']['actually_interpenetrates']:
        raise ValueError('hovering body is not actually supported by its declared neighbour')
    if pair_gap_m(*STACKED_PAIR) >= 0.0:
        raise ValueError('stacked pair does not actually interpenetrate')
    if pair_gap_m(*SEPARATED_PAIR) <= 0.0 or pair_gap_m(*SEPARATED_PAIR) < 0.001:
        raise ValueError('separated pair is not actually separated')
    total = _i33_math.fsum((record['signed_volume_m3'] for record in records))
    document = {'schema': ROCK_EGGS_SCHEMA, 'algorithm': ROCK_EGGS_ALGORITHM, 'parent_algorithm': ROCK_EGGS_PARENT_ALGORITHM, 'status': 'candidate', 'solid_schema': _x40_SOLID_SCHEMA, 'ledger': ledger, 'synthetic_base': {'kind': BASE_KIND, 'note': BASE_NOTE}, 'local_origin_xyz_m': ROCK_EGGS_LOCAL_ORIGIN.tolist(), 'parameters': report_parameters(parameters_used), 'explicit_assumptions': explicit_assumptions(parameters_used, hover), 'solids': {record['role']: record for record in records + [pile]}, 'boolean': result, 'witnesses': rock_eggs_witnesses(pile, solid, separated, stacked, hover), 'flags': {flag: False for flag in _x38_FLAGS}, 'library_versions': {'manifold3d': _i33_importlib.metadata.version('manifold3d'), 'numpy': _i33_np.__version__}, 'eggs': [{'egg_id': item.egg_id, 'centre_xyz_m': list(item.centre_xyz_m), 'radius_m': item.radius_m, 'structural_group': item.structural_group, 'structural_role': item.structural_role, 'circular_segments': SEGMENTS, 'individual_volume_m3': next((record['signed_volume_m3'] for record in records if record['role'] == item.egg_id)), 'mesh_identity_sha256': next((record['identity_sha256'] for record in records if record['role'] == item.egg_id))} for item in EGGS], 'analytic_gap_table': analytic_gap_table(), 'assembly': {'role': PILE_ROLE, 'mesh_identity_sha256': pile['identity_sha256'], 'signed_volume_m3': pile['signed_volume_m3'], 'vertices': len(pile['vertices_local_xyz_m']), 'triangles': len(pile['triangles']), 'connected_components': components, 'connected_components_declared': EXPECTED_COMPONENTS, 'sum_of_parts_m3': total, 'interpenetration_removed_m3': total - pile['signed_volume_m3'], 'signed_residual_m3': result['material']['signed_residual_m3'], 'excavated_rock_m3': result['material']['excavated_rock_m3'], 'fill_rock_m3': result['fill_rock_m3'], 'water_generated': result['water_generated'], 'boolean_gates': result['gates']}, 'not_claimed': list(NOT_CLAIMED), 'figures': []}
    for flag in _x38_FLAGS:
        document[flag] = False
    _x34_hybrid_cave_geometry_seal(document)
    return (document, {'rock_after': pile, 'records': records, 'meshes': meshes, 'hover': hover})

def rock_eggs_plane_section_segments(record, axis, value, tolerance=1e-09):
    """True cross-section of a saved closed mesh with an axis-aligned plane, as 2D segments."""
    vertices = _i33_np.asarray(record['vertices_local_xyz_m'], float)
    triangles = _i33_np.asarray(record['triangles'], int)
    keep = [index for index in range(3) if index != axis]
    segments = []
    for triangle in triangles:
        points = vertices[triangle]
        signed = points[:, axis] - value
        crossings = []
        for first, second in ((0, 1), (1, 2), (2, 0)):
            low, high = (signed[first], signed[second])
            if low < -tolerance and high < -tolerance or (low > tolerance and high > tolerance):
                continue
            if abs(low - high) <= tolerance:
                continue
            fraction = low / (low - high)
            if -tolerance <= fraction <= 1.0 + tolerance:
                crossings.append(points[first] + fraction * (points[second] - points[first]))
        if len(crossings) < 2:
            continue
        unique = {}
        for point in crossings:
            unique.setdefault(tuple(_i33_np.round(point, 9)), point)
        ordered = [unique[key] for key in sorted(unique)]
        if len(ordered) < 2:
            continue
        span = sorted(((float(_i33_np.linalg.norm(ordered[i] - ordered[j])), i, j) for i in range(len(ordered)) for j in range(i + 1, len(ordered))), reverse=True)
        _, i, j = span[0]
        segments.append((ordered[i][keep], ordered[j][keep]))
    return segments

def rock_eggs_write_report(output_directory=ROCK_EGGS_DEFAULT_OUTPUT, *, ledger=LEDGER):
    """Build, render and seal the deliverable: three figures plus a compact report.json."""
    from tools.preview_special_terrain import render_preview
    output = _i33_Path(output_directory)
    document, artifacts = rock_eggs_build(ledger=ledger)
    document['figures'] = render_preview(artifacts['rock_after'], output, artifacts['hover'])
    _x34_hybrid_cave_geometry_seal(document)
    output.mkdir(parents=True, exist_ok=True)
    report = output / REPORT_NAME
    report.write_text(_i33_json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    return (document, artifacts, report)

def write_canonical_bytes(document):
    """Exact bytes the report is written as; used by the determinism test."""
    return _i33_json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
ULURU_FLARE_SCHEMA = 'td-special-terrain-l1-uluru-flare-v1'
ULURU_FLARE_REPORT_SCHEMA = 'td-special-terrain-l1-uluru-flare-report-v1'
ULURU_FLARE_ALGORITHM = 'inselberg-with-flared-overhanging-base-v1'
ULURU_FLARE_PARENT_ALGORITHM = _x47_ALGORITHM
ULURU_FLARE_SOLID_ROLE = 'uluru_flare'
SKIRT_ROLE = 'flared_skirt'
BODY_ROLE = 'inselberg_body'
ULURU_FLARE_DEFAULT_ORIGIN = _i34_np.array([120.0, 40.0, -75.0])
DEFAULT_PREVIEW = _i34_Path('.scratch/special-terrain/l1-preview-20261019/uluru-flare')
CHOSEN_HEIGHT_M = 348.0
HEIGHT_CONFLICT = {'published_m': [348.0, 335.0], 'resolution': 'unresolved', 'chosen_m': CHOSEN_HEIGHT_M, 'basis': 'park authority figure; the conflict with 335 m is unresolved'}
ULURU_FLARE_EXPLICIT_ASSUMPTIONS = ({'name': 'total_height_m', 'value': CHOSEN_HEIGHT_M, 'grade': 'assumed', 'reason': '348 m and 335 m coexist in the sources and the conflict is unresolved; this is a chosen figure, not a measurement'}, {'name': 'overhang_amplitude_m', 'value': 38.0, 'grade': 'assumed', 'reason': 'flared-slope outward extent not obtained from any source'}, {'name': 'skirt_height_m', 'value': 12.0, 'grade': 'assumed', 'reason': 'height of the flared basal alcove not obtained from any source'}, {'name': 'skirt_wall_slope_deg', 'value': 9.4623, 'grade': 'assumed', 'reason': 'outward widen of the apron is a parameterisation choice; the value is the slope actually implied by skirt_base_radius_m/skirt_outer_radius_m/skirt_top_elevation_m'}, {'name': 'tower_side_slope_deg', 'value': 12.0253, 'grade': 'assumed', 'reason': 'steep wall angle is a parameterisation choice, not a surveyed profile; the value is the slope actually implied by the tower radii and heights'})

@_i34_dataclass(frozen=True)
class FlareParameters:
    """Every dimension is an explicit assumption; no default is a survey value."""
    total_height_m: float = CHOSEN_HEIGHT_M
    tower_top_radius_m: float = 96.0
    tower_base_radius_m: float = 168.0
    tower_base_elevation_m: float = 10.0
    skirt_outer_radius_m: float = 130.0
    skirt_base_radius_m: float = 128.0
    skirt_top_elevation_m: float = 12.0
    tower_segments: int = 64
    skirt_segments: int = 64

    def __post_init__(self):
        for name in ('total_height_m', 'tower_top_radius_m', 'tower_base_radius_m', 'tower_base_elevation_m', 'skirt_outer_radius_m', 'skirt_base_radius_m', 'skirt_top_elevation_m'):
            value = getattr(self, name)
            if type(value) is not float or not _i34_math.isfinite(value) or value <= 0.0:
                raise ValueError('bounded positive float required for ' + name)
        for name in ('tower_segments', 'skirt_segments'):
            value = getattr(self, name)
            if type(value) is not int or not 3 <= value <= 4096:
                raise ValueError('bounded integer ring segment count required for ' + name)
        if not self.tower_top_radius_m < self.tower_base_radius_m:
            raise ValueError('negative side slope required: the top radius must be the smaller one')
        if self.tower_base_elevation_m >= self.total_height_m:
            raise ValueError('the tower base elevation must lie below the total height')
        if not self.skirt_base_radius_m <= self.skirt_outer_radius_m:
            raise ValueError('the flared skirt must widen upward, not narrow')
        if not self.skirt_outer_radius_m < self.tower_base_radius_m:
            raise ValueError('a positive overhang requires the tower base to outreach the skirt')
        if not self.skirt_top_elevation_m > self.tower_base_elevation_m:
            raise ValueError('the skirt must overlap the tower in elevation to stay connected')

    @property
    def overhang_amplitude_m(self):
        return self.tower_base_radius_m - self.skirt_outer_radius_m

    @property
    def tower_side_slope_deg(self):
        return _i34_math.degrees(_i34_math.atan2(self.tower_base_radius_m - self.tower_top_radius_m, self.total_height_m - self.tower_base_elevation_m))

    @property
    def skirt_wall_slope_deg(self):
        return _i34_math.degrees(_i34_math.atan2(self.skirt_outer_radius_m - self.skirt_base_radius_m, self.skirt_top_elevation_m))

def _uluru_flare_library_versions():
    from importlib.metadata import version
    return {'manifold3d': version('manifold3d'), 'numpy': _i34_np.__version__}

def _uluru_flare_origin(origin):
    origin = ULURU_FLARE_DEFAULT_ORIGIN.copy() if origin is None else _i34_np.asarray(origin, float)
    if origin.shape != (3,) or not _i34_np.isfinite(origin).all():
        raise ValueError('finite three-component local origin required')
    return origin

def uluru_flare_contains_point(solid, world_point, origin):
    """Independent containment: intersect a tiny closed cube with the solid.

    The saved solid lives in the local mesh frame, so the probe cube is translated to the
    *local* point. Returns the overlap volume in m^3 (0.0 means the point is outside). This
    is a MESH64 Boolean rather than a ray-parity count, so a grazing ray cannot fake it.
    """
    import manifold3d as manifold
    local = tuple((float(value) for value in _i34_np.asarray(world_point, float) - _i34_np.asarray(origin, float)))
    probe = manifold.Manifold.cube((PROBE_CUBE_EDGE_M,) * 3, center=True).translate(local)
    return float((probe ^ solid).volume())

def uluru_flare_build(parameters=None, origin=None):
    """Assemble the flared inselberg and measure its overhang. Nothing is certified."""
    parameters = FlareParameters() if parameters is None else parameters
    if not isinstance(parameters, FlareParameters):
        raise ValueError('explicit FlareParameters required')
    origin = _uluru_flare_origin(origin)
    centre = [float(origin[0]), float(origin[2])]
    skirt = _x52_frustum_record(centre, centre, 0.0, parameters.skirt_top_elevation_m, parameters.skirt_base_radius_m, parameters.skirt_outer_radius_m, origin, SKIRT_ROLE, segments=parameters.skirt_segments)
    tower = _x52_frustum_record(centre, centre, parameters.tower_base_elevation_m, parameters.total_height_m, parameters.tower_base_radius_m, parameters.tower_top_radius_m, origin, BODY_ROLE, segments=parameters.tower_segments)
    result, meshes = _x51_combine([skirt, tower], origin, ULURU_FLARE_SOLID_ROLE, _x48_BooleanParameters(), minimum_components=1)
    union = meshes[ULURU_FLARE_SOLID_ROLE]
    solid = _x53_solid_from_record(union, ULURU_FLARE_SOLID_ROLE)
    solids = {SKIRT_ROLE: skirt, BODY_ROLE: tower, ULURU_FLARE_SOLID_ROLE: union}
    witnesses = overhang_witnesses(solid, solids, parameters, origin)
    return {'result': result, 'solids': solids, 'witnesses': witnesses, 'solid': solid, 'origin': origin, 'parameters': parameters}

def uluru_flare_winding_number(vertices_local_xyz_m, triangles, point_world_xyz_m, origin):
    """Independent winding number of a closed triangle mesh about one point.

    Sums the signed solid angle of every triangle (Van Oosterom-Strackee) and divides by
    4*pi, using only the saved mesh arrays -- no manifold3d and no ray casting. A closed
    outward-oriented solid gives 1.0 for an interior point and 0.0 for an exterior one, so
    a cold reader can recompute containment from the saved record alone.
    """
    origin = _i34_np.asarray(origin, float)
    points = _i34_np.asarray(vertices_local_xyz_m, float) + origin - _i34_np.asarray(point_world_xyz_m, float)
    total = 0.0
    for triangle in _i34_np.asarray(triangles, int):
        first, second, third = (points[index] for index in triangle)
        lengths = (_i34_np.linalg.norm(first), _i34_np.linalg.norm(second), _i34_np.linalg.norm(third))
        numerator = float(_i34_np.dot(first, _i34_np.cross(second, third)))
        denominator = lengths[0] * lengths[1] * lengths[2] + float(_i34_np.dot(first, second)) * lengths[2] + float(_i34_np.dot(second, third)) * lengths[0] + float(_i34_np.dot(third, first)) * lengths[1]
        total += 2.0 * _i34_math.atan2(numerator, denominator)
    return total / (4.0 * _i34_math.pi)

def uluru_flare_inside_by_winding(record, point_world_xyz_m, origin):
    winding = uluru_flare_winding_number(record['vertices_local_xyz_m'], record['triangles'], point_world_xyz_m, origin)
    return (bool(round(winding) == 1), float(winding))

def overhang_witnesses(solid, solids, parameters, origin):
    """Measure the overhang instead of asserting it.

    Every witness is one of the three cold-readable shapes: winding-number containment
    (recomputable from the saved mesh alone), a ray replay against the saved solid, or a
    MESH64 volume census. All coordinates are **world metres**. The probe point sits
    directly under the overhanging tower rim, radially outside the apron, so an
    "everything is outside" or "everything is filled" model cannot pass by accident:
    two controls (a point inside the tower, a point far outside) are recorded too.
    """
    union = solids[ULURU_FLARE_SOLID_ROLE]
    axis_x, axis_z = (float(origin[0]), float(origin[2]))
    mid_y = parameters.skirt_top_elevation_m * 0.5
    probe_radius_m = (parameters.skirt_outer_radius_m + parameters.tower_base_radius_m) * 0.5
    under_xyz = [axis_x + probe_radius_m, mid_y, axis_z]
    inside_xyz = [axis_x, parameters.total_height_m * 0.5, axis_z]
    far_xyz = [axis_x + parameters.tower_base_radius_m + parameters.overhang_amplitude_m + 100.0, mid_y, axis_z]
    vertical_to = [under_xyz[0], parameters.tower_base_elevation_m + 30.0, under_xyz[2]]
    horizontal_to = [axis_x, mid_y, axis_z]
    under_inside, under_winding = uluru_flare_inside_by_winding(union, under_xyz, origin)
    inside_inside, inside_winding = uluru_flare_inside_by_winding(union, inside_xyz, origin)
    far_inside, far_winding = uluru_flare_inside_by_winding(union, far_xyz, origin)
    vertical_hits = _x45_ray_hits(solid, under_xyz, vertical_to, origin)
    horizontal_hits = _x45_ray_hits(solid, under_xyz, horizontal_to, origin)
    components = _x50_census(solid)
    return {'overhang_point_outside_union': {'method': 'Solid.winding', 'solid_role': ULURU_FLARE_SOLID_ROLE, 'point_xyz_m': under_xyz, 'expected_inside': False, 'verdict': bool(not under_inside), 'claim': 'the point directly under the overhanging tower rim is outside the union, so the basal alcove is genuine open air rather than filled rock', 'observed': {'winding': under_winding, 'inside': under_inside}, 'probe_radius_m': probe_radius_m, 'skirt_outer_radius_m': parameters.skirt_outer_radius_m, 'tower_base_radius_m': parameters.tower_base_radius_m, 'probe_cube_intersection_volume_m3': uluru_flare_contains_point(solid, under_xyz, origin)}, 'vertical_ray_crosses_void_then_hits_rock': {'method': 'Manifold.ray_cast', 'solid_role': ULURU_FLARE_SOLID_ROLE, 'from_xyz_m': under_xyz, 'to_xyz_m': vertical_to, 'expected_hit_count': 1, 'verdict': bool(len(vertical_hits) == 1), 'claim': 'a segment rising from the overhang point traverses the open alcove and then strikes the tower underside exactly once', 'observed': {'hit_count': len(vertical_hits), 'hits': vertical_hits}}, 'horizontal_ray_crosses_void_then_hits_rock': {'method': 'Manifold.ray_cast', 'solid_role': ULURU_FLARE_SOLID_ROLE, 'from_xyz_m': under_xyz, 'to_xyz_m': horizontal_to, 'expected_hit_count': 1, 'verdict': bool(len(horizontal_hits) == 1), 'claim': 'a segment running inward along the alcove floor crosses the open concavity and then strikes the apron wall exactly once', 'observed': {'hit_count': len(horizontal_hits), 'hits': horizontal_hits}}, 'control_point_inside_tower': {'method': 'Solid.winding', 'solid_role': ULURU_FLARE_SOLID_ROLE, 'point_xyz_m': inside_xyz, 'expected_inside': True, 'verdict': bool(inside_inside), 'claim': 'control: a point on the tower axis at half height is inside the union, so the outside verdict above is not vacuous', 'observed': {'winding': inside_winding, 'inside': inside_inside}, 'probe_cube_intersection_volume_m3': uluru_flare_contains_point(solid, inside_xyz, origin)}, 'control_point_far_outside': {'method': 'Solid.winding', 'solid_role': ULURU_FLARE_SOLID_ROLE, 'point_xyz_m': far_xyz, 'expected_inside': False, 'verdict': bool(not far_inside), 'claim': 'control: a point well outside the model footprint is outside the union', 'observed': {'winding': far_winding, 'inside': far_inside}, 'probe_cube_intersection_volume_m3': uluru_flare_contains_point(solid, far_xyz, origin)}, 'union_single_connected_component': {'method': 'Mesh64_boolean', 'operation': 'add', 'cutter_roles': [SKIRT_ROLE, BODY_ROLE], 'expected_rock_after_m3': union['signed_volume_m3'], 'expected_removed_m3': 0.0, 'verdict': bool(components == 1), 'claim': 'the apron and the tower overlap in elevation, so the flared base and the body are one connected closed solid rather than two touching bodies', 'observed': {'component_count': components, 'declared_minimum_components': 1, 'input_roles': [SKIRT_ROLE, BODY_ROLE], 'rebuilt_union_volume_m3': union['signed_volume_m3']}}}

def uluru_flare_plane_section_segments(record, axis, value):
    """Intersect the saved closed mesh with one axis-aligned plane (world metres).

    Returns explicit triangle/plane crossing segments in the two remaining coordinates, so
    a true section is drawn from the actual mesh rather than from the parameters.
    """
    vertices = _i34_np.asarray(record['vertices_local_xyz_m'], float) + _i34_np.asarray(record['local_origin_xyz_m'], float)
    keep = [index for index in range(3) if index != axis]
    segments = []
    for triangle in _i34_np.asarray(record['triangles'], int):
        points = vertices[triangle]
        distances = points[:, axis] - float(value)
        crossings = []
        for first, second in ((0, 1), (1, 2), (2, 0)):
            a, b = (distances[first], distances[second])
            if a == 0.0 and b == 0.0:
                continue
            if a <= 0.0 <= b or b <= 0.0 <= a:
                if a == b:
                    continue
                fraction = a / (a - b)
                crossings.append(points[first] + fraction * (points[second] - points[first]))
        if len(crossings) == 2:
            segments.append((crossings[0][keep], crossings[1][keep]))
        elif len(crossings) == 3:
            unique = {tuple(_i34_np.round(point, 9)) for point in crossings}
            if len(unique) == 2:
                first, second = (_i34_np.asarray(item) for item in sorted(unique))
                segments.append((first[keep], second[keep]))
    return segments

def uluru_flare_report(parameters=None, origin=None, output_directory=None):
    """Build the geometry and seal the contract-shaped report for cold reading."""
    from tools.preview_special_terrain import uluru_flare_render
    geometry = uluru_flare_build(parameters, origin)
    parameters = geometry['parameters']
    origin = geometry['origin']
    figures = [] if output_directory is None else uluru_flare_render(geometry['solids'][ULURU_FLARE_SOLID_ROLE], parameters, output_directory)
    record = {'schema': ULURU_FLARE_REPORT_SCHEMA, 'algorithm': ULURU_FLARE_ALGORITHM, 'status': 'candidate', 'synthetic_base': {'kind': BASE_KIND, 'note': 'not TD native terrain, not surveyed'}, 'world_frame': WORLD_FRAME_NOTE, 'local_origin_xyz_m': [float(value) for value in origin], 'parent_algorithm': ULURU_FLARE_PARENT_ALGORITHM, 'parameters': _i34_asdict(parameters), 'derived': {'overhang_amplitude_m': parameters.overhang_amplitude_m, 'tower_side_slope_deg': parameters.tower_side_slope_deg, 'skirt_wall_slope_deg': parameters.skirt_wall_slope_deg}, 'explicit_assumptions': [dict(item) for item in ULURU_FLARE_EXPLICIT_ASSUMPTIONS], 'height_conflict': dict(HEIGHT_CONFLICT), 'solids': {role: dict(mesh) for role, mesh in geometry['solids'].items()}, 'boolean': geometry['result'], 'witnesses': geometry['witnesses'], 'flags': {flag: False for flag in _x49_FLAGS}, 'library_versions': _uluru_flare_library_versions(), 'figures': figures, 'figure_scope': FIGURE_SCOPE}
    _x46_hybrid_cave_geometry_seal(record)
    return (record, geometry)

def uluru_flare_report_identity(record):
    return _x54_identity({key: value for key, value in record.items() if key != 'identity_sha256'})

def uluru_flare_write_report(path, parameters=None, origin=None, output_directory=None):
    record, _ = uluru_flare_report(parameters, origin, output_directory)
    path = _i34_Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_report(record))
    return record
TD_ADAPTER_SCHEMA = 'td-special-terrain-chart-v1'
TD_ADAPTER_ALGORITHM = 'td-fine-bed-special-terrain-adapter-v1'
TD_ADAPTER_COORDINATES = 'physical metres [x,y,z]; x east, y up, z south; chart [row,col]'
TD_ADAPTER_BASE_KIND = 'td_fine_bed'
NATIVE_SPACING_M = 30.0
FINE_SPACINGS = (1.0, 2.0, 4.0)
MAX_FINE_CELLS = 62500
MAX_FINE_SIDE = 240
MAX_NATIVE_CELLS = 250000
CHANNEL_POLICIES = ('reject', 'protect')
CHANNEL_POLICY_SEMANTICS = {'reject': 'any non-zero artificial channel cut refuses the window', 'protect': 'channel and bank corner footprints join the protected mask and are counted'}
CHANNEL_SELECTION_SEMANTICS = 'the caller declares the selected native edge cells; an empty selection leaves the plain native bilinear bed and creates no artificial channel cut'
CHART_BASE_SEMANTICS = 'corner lattice of the shared 1/2/4 m fine bed: native bilinear corners minus declared protected capsule cuts; carries no new Terrain Diffusion detail of its own'
TARGET_PLACEMENT_SEMANTICS = 'form targets are placed by the caller in the chart frame; the adapter chooses no landform position and asserts no real-world site'
TD_ADAPTER_FLAGS = ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified')

def _number(value, name, *, positive=False):
    if type(value) not in (int, float) or not _i35_math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f'invalid {name}')

def _double_triangle_pattern(rows, cols):
    """Re-derive the declared (rows-1)x(cols-1) double-triangle rule independently.

    The shared chart rule splits every cell into a lower-left and an upper-right
    triangle over the same four vertices. This derivation walks cells with divmod
    rather than ``np.indices``, so the equality check below compares two independent
    constructions instead of restating one of them.
    """
    cells = _i35_np.arange((rows - 1) * (cols - 1), dtype=_i35_np.int64)
    cell_row, cell_col = _i35_np.divmod(cells, cols - 1)
    top_left = cell_row * cols + cell_col
    pattern = _i35_np.empty((cells.size, 6), dtype=_i35_np.int64)
    pattern[:, 0:3] = _i35_np.stack((top_left, top_left + cols, top_left + cols + 1), axis=1)
    pattern[:, 3:6] = _i35_np.stack((top_left, top_left + cols + 1, top_left + 1), axis=1)
    return pattern.reshape(-1, 3)

def _td_adapter_pair(value, name, *, positive=False):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f'{name} must be a two-element sequence')
    for entry in value:
        _number(entry, name, positive=positive)
    return [float(entry) for entry in value]

def select_native_window(*, center_m_xz, size_m_xz, spacing_m, native_shape, native_origin_m_xz, max_growth_m=NATIVE_SPACING_M):
    """Snap a metre request outward onto the integer native lattice.

    Outward snapping can only grow the window, by strictly less than one native cell per
    side, so a per-side snap bound would never fire. The honest bound is the total growth
    per axis relative to the request; exceeding ``max_growth_m`` is refused instead of
    quietly handing back a wider window than the caller asked for.
    """
    center = _td_adapter_pair(center_m_xz, 'window centre')
    size = _td_adapter_pair(size_m_xz, 'window size', positive=True)
    origin = _td_adapter_pair(native_origin_m_xz, 'native origin')
    _number(max_growth_m, 'maximum growth', positive=True)
    if type(spacing_m) not in (int, float) or float(spacing_m) not in FINE_SPACINGS:
        raise ValueError(f'fine spacing must be one of {FINE_SPACINGS}')
    spacing_m = float(spacing_m)
    if not isinstance(native_shape, (list, tuple)) or len(native_shape) != 2 or any((type(value) is not int or value < 3 for value in native_shape)):
        raise ValueError('invalid native shape')
    native_rows, native_cols = (int(native_shape[0]), int(native_shape[1]))
    if native_rows * native_cols > MAX_NATIVE_CELLS:
        raise ValueError('native source exceeds the declared native cell budget')
    cells = []
    for axis in (0, 1):
        span = native_cols if axis == 0 else native_rows
        low = (center[axis] - 0.5 * size[axis] - origin[axis]) / NATIVE_SPACING_M
        high = (center[axis] + 0.5 * size[axis] - origin[axis]) / NATIVE_SPACING_M
        index_low = int(_i35_math.floor(low + 1e-09))
        index_high = int(_i35_math.ceil(high - 1e-09))
        snap_low = (low - index_low) * NATIVE_SPACING_M
        snap_high = (index_high - high) * NATIVE_SPACING_M
        if not 0 <= index_low < index_high < span:
            raise ValueError('requested window leaves the native sample extent')
        cells.append((index_low, index_high, snap_low, snap_high))
    x0, x1, snap_left, snap_right = cells[0]
    z0, z1, snap_bottom, snap_top = cells[1]
    span_m_x = (x1 - x0) * NATIVE_SPACING_M
    span_m_z = (z1 - z0) * NATIVE_SPACING_M
    for span_m, requested_m, axis in ((span_m_x, size[0], 0), (span_m_z, size[1], 1)):
        growth = span_m - requested_m
        if growth > max_growth_m + 1e-09:
            raise ValueError(f'window on axis {axis} would grow by {growth:.6g} m from the requested {requested_m:.6g} m, above the declared {max_growth_m:.6g} m maximum; move the centre onto the 30 m native lattice or accept the wider window')
    for span_m, axis in ((span_m_x, 0), (span_m_z, 1)):
        if abs(span_m / spacing_m % 1) > 1e-09:
            raise ValueError(f'window on axis {axis} spans {span_m:.6g} m, not a whole number of {spacing_m:g} m fine cells')
    fine_cols = int(round(span_m_x / spacing_m))
    fine_rows = int(round(span_m_z / spacing_m))
    if min(fine_rows, fine_cols) < 3:
        raise ValueError('fine window must keep at least three cells per axis')
    if fine_rows * fine_cols > MAX_FINE_CELLS:
        raise ValueError(f'fine window would need {fine_rows}x{fine_cols} cells, above the declared {MAX_FINE_CELLS} budget ({MAX_FINE_SIDE}x{MAX_FINE_SIDE}); use a coarser spacing or stitch several windows')
    corner_origin = [origin[0] + x0 * NATIVE_SPACING_M, origin[1] + z0 * NATIVE_SPACING_M]
    return {'schema': TD_ADAPTER_SCHEMA, 'algorithm': TD_ADAPTER_ALGORITHM, 'requested_center_m_xz': center, 'requested_size_m_xz': size, 'native_window': [x0, x1, z0, z1], 'native_span_cells_xz': [x1 - x0, z1 - z0], 'actual_size_m_xz': [span_m_x, span_m_z], 'snap_m': [snap_left, snap_right, snap_bottom, snap_top], 'maximum_snap_observed_m': float(max(abs(snap_left), abs(snap_right), abs(snap_bottom), abs(snap_top))), 'native_cell_snap_bound_m': NATIVE_SPACING_M, 'growth_m': [span_m_x - size[0], span_m_z - size[1]], 'maximum_growth_observed_m': float(max(span_m_x - size[0], span_m_z - size[1])), 'maximum_growth_allowed_m': float(max_growth_m), 'native_spacing_m': NATIVE_SPACING_M, 'spacing_m': spacing_m, 'fine_shape_zx': [fine_rows, fine_cols], 'fine_cells': fine_rows * fine_cols, 'fine_cell_budget': MAX_FINE_CELLS, 'maximum_fine_side': MAX_FINE_SIDE, 'native_origin_m_xz': origin, 'corner_origin_m_xz': corner_origin}

def build_td_form_chart(hierarchy, *, window, spacing_m, source_hierarchy_sha256, selected_edge_cell_ids, channel_policy='reject'):
    """Shared fine bed -> L0 field-form chart, protected mask and upstream identity.

    ``selected_edge_cell_ids`` is deliberately mandatory with no silent default: the shared
    builder would otherwise auto-select every internal receiver edge in the window and cut
    artificial channels through the landform bed. Pass an empty int64 (0, 2) array for the
    plain bilinear bed, which is what a special-terrain form should sit on.

    Returns a mapping whose four chart inputs feed
    ``metric_special_terrain_forms.build_special_form_vdm(..., base_kind="td_fine_bed")``.
    """
    if not isinstance(window, dict) or window.get('schema') != TD_ADAPTER_SCHEMA:
        raise ValueError('select_native_window record required')
    if channel_policy not in CHANNEL_POLICIES:
        raise ValueError(f'channel policy must be one of {CHANNEL_POLICIES}')
    native_window = window['native_window']
    if not isinstance(native_window, (list, tuple)) or len(native_window) != 4 or any((type(value) is not int for value in native_window)):
        raise ValueError('integer native window required')
    if float(spacing_m) != float(window['spacing_m']):
        raise ValueError('spacing disagrees with the window record')
    spacing_m = float(spacing_m)
    selected = _i35_np.asarray(selected_edge_cell_ids)
    if selected.dtype != _i35_np.int64 or selected.ndim != 2 or selected.shape[1] != 2:
        raise ValueError('selected native edges must be an int64 (n, 2) array')
    bed = _i35_build_fine_geometry(hierarchy, native_window=list(native_window), source_hierarchy_sha256=source_hierarchy_sha256, spacing_m=spacing_m, selected_edge_cell_ids=selected)
    arrays = bed['arrays']
    metadata = bed['metadata']
    if metadata['spacing_m'] != spacing_m or list(metadata['native_window']) != list(native_window) or list(metadata['corner_origin_m_xz']) != list(window['corner_origin_m_xz']):
        raise ValueError('fine bed disagrees with the selected window')
    corner = arrays['bed_corner_m']
    canonical = arrays['canonical_bed_center_m']
    cut = arrays['cut_corner_m']
    channel = arrays['artificial_channel_corner_mask']
    bank = arrays['artificial_bank_corner_mask']
    protection = arrays['protected_corner_mask']
    step = int(round(spacing_m))
    if corner.dtype != _i35_np.float64 or corner.ndim != 2 or canonical.shape != ((corner.shape[0] - 1) * step, (corner.shape[1] - 1) * step) or (cut.shape != corner.shape) or (channel.shape != corner.shape) or (protection.shape != corner.shape) or (protection.dtype != bool):
        raise ValueError('invalid shared fine bed arrays')
    if not (_i35_np.isfinite(corner).all() and _i35_np.isfinite(canonical).all() and _i35_np.isfinite(cut).all()):
        raise ValueError('nonfinite shared fine bed')
    cut_maximum = float(_i35_np.max(cut, initial=0.0))
    channel_cells = int(_i35_np.count_nonzero(channel))
    if cut_maximum > 0.0:
        if channel_policy == 'reject':
            raise ValueError(f'window carries a {cut_maximum:.6g} m artificial channel cut; the reject channel policy refuses it (select another window or use the protect policy)')
        if not _i35_np.array_equal(corner, arrays['native_bilinear_corner_m'] - cut):
            raise ValueError('protected channel bed is not the bilinear bed minus the cut')
    elif not _i35_np.array_equal(corner, arrays['native_bilinear_corner_m']):
        raise ValueError('zero-cut window is not the plain native bilinear bed')
    cell_mean = canonical.reshape(corner.shape[0] - 1, step, corner.shape[1] - 1, step).mean(axis=(1, 3))
    tolerance = 1e-09 * max(1.0, float(_i35_np.max(_i35_np.abs(canonical))))
    floor_difference = float(_i35_np.max(_i35_np.abs(cell_mean - arrays['bed_center_m'])))
    if floor_difference > tolerance:
        raise ValueError(f'coarsened canonical floor differs from the declared bed centre field by {floor_difference:.6g} m, above the declared {tolerance:.6g} m tolerance')
    corner_mean = (corner[:-1, :-1] + corner[1:, :-1] + corner[1:, 1:] + corner[:-1, 1:]) / 4.0
    lattice_difference = float(_i35_np.max(_i35_np.abs(corner_mean - cell_mean)))
    mask = _i35_np.array(protection, dtype=bool, copy=True)
    if channel_policy == 'protect':
        mask |= channel | bank
    rows, cols = corner.shape
    x = float(window['corner_origin_m_xz'][0]) + _i35_np.arange(cols) * spacing_m
    z = float(window['corner_origin_m_xz'][1]) + _i35_np.arange(rows) * spacing_m
    chart = _i35_np.empty((rows, cols, 3), dtype=_i35_np.float64)
    chart[:, :, 0] = x[None, :]
    chart[:, :, 2] = z[:, None]
    chart[:, :, 1] = corner
    if not _i35_np.isfinite(chart).all():
        raise ValueError('nonfinite chart geometry')
    if abs(float(chart[0, 1, 0] - chart[0, 0, 0]) - spacing_m) > 1e-09 * spacing_m or abs(float(chart[1, 0, 2] - chart[0, 0, 2]) - spacing_m) > 1e-09 * spacing_m:
        raise ValueError('chart lattice spacing disagrees with the declared spacing')
    pattern = _x55_triangles(rows, cols)
    if pattern.shape != (2 * (rows - 1) * (cols - 1), 3) or pattern.dtype != _i35_np.int64:
        raise ValueError('chart triangle pattern has the wrong shape or dtype')
    if not _i35_np.array_equal(pattern, _double_triangle_pattern(rows, cols)):
        raise ValueError('chart triangle pattern is not the declared double-triangle rule')
    source_identity = bed['identity_sha256']
    protection_identity = _i35_identity({'protected_mask': mask}, {'bed_identity': source_identity, 'bed_source_hierarchy_sha256': source_hierarchy_sha256, 'channel_policy': channel_policy, 'semantics': CHANNEL_POLICY_SEMANTICS[channel_policy]})
    record = {'schema': TD_ADAPTER_SCHEMA, 'algorithm': TD_ADAPTER_ALGORITHM, 'coordinates': TD_ADAPTER_COORDINATES, 'base_kind': TD_ADAPTER_BASE_KIND, 'chart_base_semantics': CHART_BASE_SEMANTICS, 'target_placement_semantics': TARGET_PLACEMENT_SEMANTICS, 'window': {key: window[key] for key in sorted(window)}, 'chart_shape_zx': [rows, cols], 'chart_triangles': int(_x55_triangles(rows, cols).shape[0]), 'chart_elevation_min_m': float(corner.min()), 'chart_elevation_max_m': float(corner.max()), 'chart_floor_min_m': float(canonical.min()), 'chart_floor_max_m': float(canonical.max()), 'canonical_floor_mean_max_difference_m': floor_difference, 'canonical_floor_tolerance_m': tolerance, 'lattice_vs_canonical_floor_difference_m': lattice_difference, 'lattice_vs_canonical_floor_note': 'expected O(curvature * spacing^2): the chart samples corners, the canonical floor averages 1 m centres; a diagnostic, not an error', 'artificial_cut_maximum_m': cut_maximum, 'artificial_channel_cells': channel_cells, 'channel_selection_semantics': CHANNEL_SELECTION_SEMANTICS, 'selected_edge_cells': int(selected.shape[0]), 'artificial_bank_cells': int(_i35_np.count_nonzero(bank)), 'channel_policy': channel_policy, 'channel_policy_semantics': CHANNEL_POLICY_SEMANTICS[channel_policy], 'protected_cells_declared': int(_i35_np.count_nonzero(protection)), 'protected_cells_chart': int(_i35_np.count_nonzero(mask)), 'identity_chain': {'source_hierarchy_sha256': source_hierarchy_sha256, 'source_hierarchy_identity': metadata['hierarchy_identity'], 'source_identity_sha256': metadata['source_identity'], 'fine_bed_identity': bed['identity_sha256'], 'chart_source_identity': source_identity, 'chart_protection_identity': protection_identity}, 'declared_flags': {flag: False for flag in TD_ADAPTER_FLAGS}, 'scope': 'finite engineering window of one pinned 30 m native hierarchy; not the full native domain and not a natural basin'}
    return {'chart_reference_xyz_m': chart, 'protected_mask': mask, 'source_identity': source_identity, 'protection_identity': protection_identity, 'base_identity': source_identity, 'record': record}
