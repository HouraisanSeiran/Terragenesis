"""Joint-controlled true-3D sandstone pillar field, with VDM applied to vertical pillar walls.

The L0 ``sandstone_pillar_field`` in ``metric_special_terrain_forms`` is a single-valued
displacement height field: every ``(row, col)`` of the chart carries exactly one elevation.
Two of the landform's defining features are therefore not expressible at all:

* its **section** can only be a closed level curve of that field, so the recorded pillars are
  framed radial discs with circular bases -- while the sources describe 金鞭岩 as "四棱分明"
  and 御笔峰 as "方正如削", i.e. multi-sided prisms whose flat faces meet at straight,
  near-vertical arrises;
* a real pillar wall is a **multi-valued** surface: the wall itself, an outward-bulging iron
  cap and a fluted, striated face cannot be encoded as one elevation per chart cell.

This module therefore builds the field as a real closed MESH64 solid through the general
Boolean algebra in ``terrain_pipeline.hybrid_rock_boolean`` (which is not edited here), using
the same L1 volume route as the other ``special_terrain_l1_*`` forms.

Geometry, in world metres (a local frame plus ``local_origin_xyz_m``); y is elevation and the
model base plane is world y = 0:

* a **joint network** -- the Voronoi diagram of a jittered seed grid, with one joint set
  stretched to give a dominant strike -- supplies one irregular convex polygon per pillar;
  that polygon is the multi-sided prism section the height field cannot express;
* every polygon is shrunk by half a joint gap, so genuine open vertical joints stand between
  the pillars instead of a continuous sheet of rock;
* the wall is subdivided in elevation and every wall vertex is displaced **laterally along its
  own outward normal** -- that is VDM applied to a vertical wall, and it keeps the body a
  closed solid rather than an open surface;
* the shape terms are the repository's own vocabulary for this landform: a taper (上细下粗),
  two orders of horizontal joint striations (节理横纹), a perimeter fluting (纵向凹槽) and the
  harder iron cap (铁帽) that bulges outward over the top ``cap_thickness_m``;
* a base plateau under the field makes the pillars meet a ground plane, and because every body
  is closed the union is a single closed solid.

Every dimension is an **explicit assumption** (``EXPLICIT_ASSUMPTIONS``): the pillar diameter,
the pillar spacing, the vertical joint spacing and the height/width distribution are the four
hard gaps of ledger section 3 and no source supplies them; the sampled height band and the
joint-gap width are parameterisation choices as well. Only the source range of the height band
and the ~30 m iron cap are secondary values. Nothing here is a certification: ``status`` is
``candidate`` and every capability flag stays False.

The values this module replaces are declared in ``SUPERSEDES``: the ``sandstone_pillar_field``
displacement height field of ``metric-special-terrain-v1`` /
``metric-special-terrain-surface-v2`` is void for this kind -- not because it was a wrong field,
but because a single-valued field carries no admissible geometry for a pillar.

One numerical trap is disclosed with the artifact rather than hidden inside it. The section
simplicity gate (``section_polygon_count``) cuts the saved mesh with a horizontal plane and
stitches the crossing segments back into polygons. A crossing point on a shared vertical edge
is produced **twice**, once by each of the two triangles that meet there, and the two results
differ by ~1e-11 m; Shapely's ``polygonize`` requires exactly equal endpoints, so an unsnapped
stitch returns **zero** polygons for a perfectly simple section. That is a false negative, not a
fold: with it, the uncarved straight prisms reported 208 of 256 sections "folded". The endpoints
are therefore snapped to a 1e-6 m grid before stitching, and the tolerance is written into the
witness (``section_endpoint_snap_m`` / ``method_note``) so a cold reader can see how the verdict
was reached instead of taking it on trust. The geometric claim -- that a carved wall whose
taper is a similarity contraction of its own joint cell cannot fold -- is unaffected by the
tolerance, but the check that claims it is only meaningful once the tolerance is declared.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

from terrain_pipeline.hybrid_cave_geometry import ray_hits, seal, signed_volume
from terrain_pipeline.hybrid_rock_boolean import (
    ALGORITHM as BOOLEAN_ALGORITHM, BooleanParameters, FLAGS, census, combine,
    polygon_prism_record, solid_from_record)
from terrain_pipeline.hybrid_river_graph import identity

SCHEMA = "td-special-terrain-l1-pillars3d-v1"
REPORT_SCHEMA = "td-special-terrain-l1-pillars3d-report-v1"
ALGORITHM = "joint-controlled-sandstone-pillar-field-with-vdm-carved-vertical-walls-v1"
SOLID_SCHEMA = "td-hybrid-local-solid-mesh-v1"
PARENT_ALGORITHM = BOOLEAN_ALGORITHM
BASE_KIND = "synthetic_analytic"
SOLID_ROLE = "pillar_field_rock"
PLATEAU_ROLE = "plateau"
PILLAR_ROLE_PREFIX = "pillar-"
DEFAULT_ORIGIN = np.array([0., 0., 0.])
DEFAULT_OUTPUT = Path(".scratch/special-terrain/l1-preview-20261020/pillars3d")
PROBE_CUBE_EDGE_M = .2
WORLD_FRAME_NOTE = ("witness coordinates are world metres (local mesh frame + local_origin_xyz_m); "
                    "y is elevation and the model base plane is world y = 0")
FIGURE_SCOPE = "display only; a figure is never a certification"
GEOLOGY_NOTE = (
    "the landform is quartz sandstone of Middle-Upper Devonian age with a nearly horizontal "
    "attitude; its sculpting is **not** carbonate karst but running water cutting down a "
    "pre-existing network of several sets of near-vertical joints, which is why a real pillar "
    "is a multi-sided prism with vertical arrises and an angular, flat top rather than a "
    "surface of revolution. The four-stage evolution (platform/mesa -> peak wall -> peak "
    "cluster/forest -> residual forest) is what makes the pillars stand as a field of separate "
    "bodies instead of one dissected mass.")
# The values this module replaces. The height-field record stays on disk and stays readable;
# it is the geometry it declares for this kind that is void.
SUPERSEDES = {
    "kind": "sandstone_pillar_field",
    "superseded_schema": "metric-special-terrain-v1",
    "superseded_algorithm": "special-terrain-field-forms-v1",
    "superseded_surface_schema": "metric-special-terrain-surface-v2",
    "scope": "the displacement-height-field values generated for kind sandstone_pillar_field are void",
    "reason": "a single-valued height field cannot express a multi-sided polygonal prism section, "
              "vertical walls, an outward-bulging iron cap, or a wall alcove; the recorded field "
              "therefore carries no admissible geometry for this landform",
    "replaced_by": ALGORITHM,
    "not_a_certification": True,
}

# Numeric inputs and their provenance. Values are grades against
# .scratch/special-terrain/parameters-and-sources.md; "assumed" means the number has no source
# and is only a parameterisation choice, never a measurement.
EXPLICIT_ASSUMPTIONS = (
    {"name": "pitch_m", "value": 30.0, "grade": "assumed",
     "reason": "pillar spacing is one of the four hard gaps of ledger section 3; no source "
               "supplies it"},
    {"name": "jitter_fraction", "value": 0.25, "grade": "assumed",
     "reason": "joint-network irregularity is a placement choice; no source supplies it"},
    {"name": "joint_gap_m", "value": 6.0, "grade": "assumed",
     "reason": "vertical joint aperture is a hard gap; the value only has to keep the carved "
               "walls more than outward_limit_m apart"},
    {"name": "height_band_source_m", "value": [30.0, 400.0], "grade": "secondary",
     "reason": "ledger section 2/4.3: individual pillars run from tens of metres to 400 m, "
               "with more than a thousand above 200 m"},
    {"name": "height_min_m", "value": 40.0, "grade": "assumed",
     "reason": "the ledger's secondary range is tens of metres to 400 m; sampling only "
               "40-150 m is a sampling-band choice, exactly as the L0 ledger already records "
               "for height_band"},
    {"name": "height_max_m", "value": 150.0, "grade": "assumed",
     "reason": "upper end of the sampled band; the tall end of the secondary range is "
               "deliberately not sampled in this candidate"},
    {"name": "rows", "value": 4, "grade": "assumed",
     "reason": "a 4x4 fixture only; the field size is decided by the hosting chart, not by "
               "any source"},
    {"name": "cols", "value": 4, "grade": "assumed",
     "reason": "a 4x4 fixture only; the field size is decided by the hosting chart"},
    {"name": "seed", "value": 20261020, "grade": "assumed",
     "reason": "a deterministic seed is required for reproducibility and is not a survey value"},
    {"name": "base_thickness_m", "value": 45.0, "grade": "assumed",
     "reason": "synthetic analytic base beyond the sampled band; chosen evenly above the "
               "tallest pillar so the base never crops the field"},
    {"name": "strike_stretch", "value": 1.6, "grade": "assumed",
     "reason": "the dominance of one joint set is a geological fact, its numeric stretch is "
               "not; no source supplies the ratio"},
    {"name": "substep_m", "value": 3.0, "grade": "assumed",
     "reason": "wall subdivision in elevation is a resolution choice"},
    {"name": "ring_spacing_m", "value": 1.5, "grade": "assumed",
     "reason": "the joint ring has to be resampled for a perimeter flute to have vertices to "
               "act on; the spacing is a resolution choice"},
    {"name": "smooth_passes", "value": 4, "grade": "assumed",
     "reason": "removing the mitre corner of a joint cell before displacing is a numerical "
               "requirement (an inward offset larger than the corner radius folds the section); "
               "the pass count is a choice"},
    {"name": "taper_fraction", "value": 0.10, "grade": "assumed",
     "reason": "the 上细下粗 direction (thin top over a thick base) is described by the "
               "sources, the fraction is not"},
    {"name": "cap_thickness_m", "value": 30.0, "grade": "secondary",
     "reason": "ledger section 2/4.3: the top ~30 m is an iron-bearing quartz sandstone cap"},
    {"name": "cap_bulge_m", "value": 1.1, "grade": "assumed",
     "reason": "how far the harder cap stands proud of the wall below it is not in any source"},
    {"name": "striation_amplitude_m", "value": [0.55, 0.22], "grade": "assumed",
     "reason": "two orders of horizontal joint striation (节理横纹) are described by the "
               "sources, their amplitudes are not"},
    {"name": "striation_wavelength_m", "value": [24.0, 14.0], "grade": "assumed",
     "reason": "bedding-controlled striation spacing is a hard gap; the values also satisfy "
               "the repository's SAMPLES_PER_FEATURE = 4 against substep_m"},
    {"name": "flute_amplitude_m", "value": [0.55, 0.22], "grade": "assumed",
     "reason": "perimeter fluting (纵向凹槽) amplitude has no source"},
    {"name": "flute_pitch_m", "value": [16.0, 7.0], "grade": "assumed",
     "reason": "perimeter fluting wavelength has no source; kept above 4x ring_spacing_m to "
               "avoid aliasing"},
    {"name": "inward_limit_m", "value": 2.0, "grade": "assumed",
     "reason": "the clamp that keeps a carved section a simple polygon is a numerical "
               "requirement, not a measurement"},
    {"name": "outward_limit_m", "value": 2.0, "grade": "assumed",
     "reason": "the outward clamp is bounded by half the joint gap so neighbouring pillars "
               "never fuse; it is not a measurement"},
    {"name": "carve_backoff", "value": [1.0, 0.7, 0.5, 0.35, 0.22, 0.12, 0.0], "grade": "assumed",
     "reason": "the depth-reduction ladder is a numerical admissibility device: a joint cell's "
               "mitre corner has a near-zero radius of curvature, so an inward offset deeper "
               "than that radius folds the section through itself"},
    {"name": "base_footprint_half_extent_m", "value": 156.0, "grade": "assumed",
     "reason": "derived from rows/cols/pitch/strike_stretch plus two pitches of margin; the "
               "analytic base is synthetic and not surveyed"},
)

# Largest fraction of the full carve that keeps every horizontal section a simple polygon.
# See the carve_backoff ledger entry above for why this ladder exists at all.
DEFAULT_CARVE_BACKOFF = (1.0, 0.7, 0.5, 0.35, 0.22, 0.12, 0.0)


def _finite_float(name, value, *, low=None, high=None):
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("explicit finite float required for " + name)
    if low is not None and value < low:
        raise ValueError("value below the explicit bound required for " + name)
    if high is not None and value > high:
        raise ValueError("value above the explicit bound required for " + name)
    return value


def _pair(name, value):
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError("explicit two-component tuple required for " + name)
    for item in value:
        if type(item) is not float or not math.isfinite(item) or item <= 0.:
            raise ValueError("positive finite float components required for " + name)
    return value


@dataclass(frozen=True)
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
    taper_fraction: float = 0.10
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
            raise ValueError("bounded integer seed required")
        for name in ("rows", "cols"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 64:
                raise ValueError("bounded integer field extent required for " + name)
        if type(self.smooth_passes) is not int or not 0 <= self.smooth_passes <= 64:
            raise ValueError("bounded integer smoothing pass count required")
        _finite_float("pitch_m", self.pitch_m, low=1., high=2000.)
        _finite_float("joint_gap_m", self.joint_gap_m, low=.05, high=200.)
        _finite_float("height_min_m", self.height_min_m, low=.5, high=2000.)
        _finite_float("height_max_m", self.height_max_m, low=.5, high=2000.)
        _finite_float("base_thickness_m", self.base_thickness_m, low=.5, high=2000.)
        _finite_float("jitter_fraction", self.jitter_fraction, low=0., high=.49)
        _finite_float("strike_stretch", self.strike_stretch, low=1., high=8.)
        _finite_float("substep_m", self.substep_m, low=.05, high=50.)
        _finite_float("ring_spacing_m", self.ring_spacing_m, low=.05, high=20.)
        _finite_float("taper_fraction", self.taper_fraction, low=0., high=.95)
        _finite_float("cap_thickness_m", self.cap_thickness_m, low=0., high=2000.)
        _finite_float("cap_bulge_m", self.cap_bulge_m, low=0., high=50.)
        _finite_float("inward_limit_m", self.inward_limit_m, low=0., high=50.)
        _finite_float("outward_limit_m", self.outward_limit_m, low=0., high=50.)
        for name in ("striation_amplitude_m", "striation_wavelength_m", "flute_amplitude_m",
                     "flute_pitch_m"):
            _pair(name, getattr(self, name))
        if not self.height_min_m < self.height_max_m:
            raise ValueError("the sampled height band must be a strict interval")
        if not self.outward_limit_m < .5 * self.joint_gap_m:
            raise ValueError("the outward clamp must stay inside half the joint gap, otherwise "
                             "neighbouring pillars can fuse")
        if not self.substep_m * 4. <= min(self.striation_wavelength_m):
            raise ValueError("the finest vertical striation wavelength must satisfy the "
                             "repository's SAMPLES_PER_FEATURE = 4 against substep_m")
        if not self.ring_spacing_m * 4. <= min(self.flute_pitch_m):
            raise ValueError("the finest flute pitch must satisfy SAMPLES_PER_FEATURE = 4 "
                             "against ring_spacing_m")
        if not isinstance(self.carve_backoff, tuple) or not self.carve_backoff:
            raise ValueError("explicit non-empty carve backoff ladder required")
        previous = math.inf
        for step in self.carve_backoff:
            if type(step) is not float or not math.isfinite(step) or not 0. <= step <= 1.:
                raise ValueError("carve backoff steps must be finite floats inside [0, 1]")
            if step > previous:
                raise ValueError("the carve backoff ladder must not increase")
            previous = step
        if self.carve_backoff[-1] != 0.:
            raise ValueError("the carve backoff ladder must reach 0. so that the uncarved "
                             "prism is always the last admissible fallback")

    @property
    def height_band_m(self):
        return (self.height_min_m, self.height_max_m)

    @property
    def pillar_count(self):
        return self.rows * self.cols

    @property
    def footprint_half_extent_m(self):
        return .5 * (max(self.rows, self.cols) * self.pitch_m) * self.strike_stretch \
            + 2. * self.pitch_m


# ---------------------------------------------------------------- joint network

def resample_ring(ring, spacing_m):
    """Uniform arc-length resampling, so a perimeter flute has vertices to act on.

    Without this the joint-cell ring carries one vertex every ~12 m while the flute wavelength
    is ~11 m: the fixture aliases into a jagged, self-crossing section. The repository states
    the same rule as ``SAMPLES_PER_FEATURE = 4`` in ``metric_special_terrain_forms``.
    """
    closed = np.vstack((ring, ring[:1]))
    steps = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    s = np.concatenate(([0.0], np.cumsum(steps)))
    total = float(s[-1])
    count = max(8, int(round(total / spacing_m)))
    target = np.linspace(0.0, total, count, endpoint=False)
    x = np.interp(target, s, closed[:, 0])
    z = np.interp(target, s, closed[:, 1])
    return np.stack((x, z), axis=1)


def smooth_ring(ring, passes):
    """Cyclic moving average.

    The resampled ring still carries the mitre corner of its joint cell, and a corner has a
    local radius of curvature of nearly zero. Offsetting inward by more than that radius --
    which is exactly what carving a wall does -- folds the section through itself. Measured on
    this fixture: unsmoothed, 15 of 16 cells folded 4-16 m above the base; smoothed, none do.
    """
    out = np.array(ring, dtype=float)
    for _ in range(int(passes)):
        out = 0.5 * out + 0.25 * (np.roll(out, -1, axis=0) + np.roll(out, 1, axis=0))
    return out


def joint_cells(parameters):
    """Voronoi cells of a jittered seed grid: one irregular convex polygon per pillar.

    Deterministic in ``parameters.seed``: the jitter draws, then the heights, come off the same
    stream in the same order as the archived prototype, so the default build reproduces it.
    """
    from scipy.spatial import Voronoi
    from shapely.geometry import Polygon, box
    from shapely.geometry.polygon import orient
    rng = np.random.default_rng(parameters.seed)
    centres = []
    for row in range(parameters.rows):
        for col in range(parameters.cols):
            cx = (col - 0.5 * (parameters.cols - 1)) * parameters.pitch_m
            cz = (row - 0.5 * (parameters.rows - 1)) * parameters.pitch_m
            jitter = rng.uniform(-parameters.jitter_fraction, parameters.jitter_fraction,
                                 size=2) * parameters.pitch_m
            centres.append((cx + jitter[0], cz + jitter[1]))
    centres = np.asarray(centres, dtype=float)
    centres[:, 1] *= parameters.strike_stretch       # one strike direction dominates
    half = .5 * (max(parameters.rows, parameters.cols) * parameters.pitch_m) \
        * parameters.strike_stretch + 2. * parameters.pitch_m
    mirrored = [centres]
    for sign in (-1.0, 1.0):
        for axis in (0, 1):
            shift = np.zeros(2)
            shift[axis] = sign * 2.0 * half
            mirrored.append(centres + shift)
    vor = Voronoi(np.vstack(mirrored))
    frame = box(-half, -half, half, half)
    polygons = []
    for index in range(len(centres)):
        region = vor.regions[vor.point_region[index]]
        if not region or -1 in region:
            raise RuntimeError("unbounded joint cell")
        cell = Polygon(vor.vertices[region]).intersection(frame).buffer(
            -0.5 * parameters.joint_gap_m, join_style="mitre")
        if cell.is_empty or cell.area <= 0.0:
            raise RuntimeError("empty joint cell")
        if not cell.is_valid:
            cell = cell.buffer(0.0)
        cell = orient(cell, sign=1.0)                # counter-clockwise exterior
        ring = resample_ring(np.asarray(cell.exterior.coords)[:-1], parameters.ring_spacing_m)
        polygons.append(smooth_ring(ring, parameters.smooth_passes))
    heights = rng.uniform(parameters.height_min_m, parameters.height_max_m, size=len(polygons))
    return polygons, heights, centres, half


# ------------------------------------------------------- wall VDM displacement

def _outward_normals(ring):
    following = np.roll(ring, -1, axis=0)
    preceding = np.roll(ring, 1, axis=0)
    tangent = following - preceding
    normal = np.stack((tangent[:, 1], -tangent[:, 0]), axis=1)
    length = np.linalg.norm(normal, axis=1, keepdims=True)
    return normal / np.where(length > 0.0, length, 1.0)


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
    closed = np.vstack((ring, ring[:1]))
    steps = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    return np.concatenate(([0.0], np.cumsum(steps)))[:len(ring)]


def ring_area(ring):
    """Absolute shoelace area of a closed (x, z) ring, in m^2."""
    ring = np.asarray(ring, float)
    x, z = ring[:, 0], ring[:, 1]
    return float(abs(np.sum(x * np.roll(z, -1) - np.roll(x, -1) * z) / 2.))


def wall_displacement(ring, perimeter_s, y, height, cell_phase, carve, parameters, scale=1.0):
    """Lateral (in-plane) displacement of one wall vertex, along its outward normal.

    Every term is the repository's own research vocabulary applied to a vertical wall: striation
    is 节理横纹 (two orders), flute is the perimeter 纵向凹槽 the 岩壁Voronoi design asks for,
    and the cap is the 铁帽. The taper is deliberately not here: it is a similarity contraction
    applied separately in ``wall_ring_at``, so that it cannot fold the section.
    """
    if not carve:
        return np.zeros(len(ring))
    striation = sum(amplitude * np.sin(2.0 * np.pi * y / wavelength + cell_phase)
                    for amplitude, wavelength in zip(parameters.striation_amplitude_m,
                                                     parameters.striation_wavelength_m))
    flute = sum(amplitude * np.sin(2.0 * np.pi * perimeter_s / pitch + 1.7 * cell_phase)
                for amplitude, pitch in zip(parameters.flute_amplitude_m, parameters.flute_pitch_m))
    cap = parameters.cap_bulge_m if y >= height - parameters.cap_thickness_m else 0.0
    return np.clip(scale * (striation + flute + cap),
                   -parameters.inward_limit_m, parameters.outward_limit_m)


def wall_ring_at(ring, perimeter_s, y, height, cell_phase, carve, parameters, scale=1.0):
    """One horizontal wall section: taper first, then the additive carve along the normals."""
    displacement = wall_displacement(ring, perimeter_s, y, height, cell_phase, carve, parameters,
                                     scale)
    # taper first (a similarity about the centroid, so it cannot fold), then the additive
    # carving along the normals of that already-contracted section.
    centre = ring.mean(axis=0)
    contracted = centre + (ring - centre) * taper_factor(y, height, parameters.taper_fraction)
    return contracted + _outward_normals(contracted) * np.asarray(displacement)[:, None]


def wall_levels(height, substep_m):
    levels = np.arange(0.0, height + 1e-9, substep_m)
    if levels[-1] < height - 1e-9:
        levels = np.append(levels, height)
    return levels


class FoldedSection(ValueError):
    """The carve drove a horizontal section through itself: that depth is not admissible."""


# ------------------------------------------------------------------- the solid

def _carved_solid(ring, height, cell_phase, scale, parameters, cell_index, role, origin):
    """Build the prism at one carve scale, or raise ``FoldedSection`` if a section is not simple."""
    from shapely.geometry import Polygon
    count = len(ring)
    perimeter_s = perimeter_arc_length(ring)
    levels = wall_levels(float(height), parameters.substep_m)
    walls = np.empty((len(levels), count, 2))
    for ordinal, y in enumerate(levels):
        section = wall_ring_at(ring, perimeter_s, float(y), float(height), cell_phase, True,
                               parameters, scale)
        polygon = Polygon(section)
        if polygon.is_empty or not polygon.is_valid or not polygon.exterior.is_simple \
                or polygon.area <= 0.0:
            raise FoldedSection("cell %d level %.1f m" % (cell_index, float(y)))
        walls[ordinal] = section
    vertices = np.zeros((len(levels), count, 3))   # layout is (x, y, z), not (x, z, y)
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
    # Caps: the carved section is not convex, so a fan will not do. Use the pinned MESH64
    # triangulator the repository's own polygon_prism_record relies on, then let MESH64 itself
    # decide which winding is admissible instead of assuming one.
    import manifold3d as manifold
    bottom_uv = vertices[:count][:, [0, 2]]
    top_uv = vertices[top:top + count][:, [0, 2]]
    bottom_cap = [[int(value) for value in item]
                  for item in manifold.triangulate([bottom_uv.tolist()], allow_convex=False)]
    top_cap = [[top + int(value) for value in item]
               for item in manifold.triangulate([top_uv.tolist()], allow_convex=False)]
    for flip_bottom, flip_top in ((False, True), (True, False), (False, False), (True, True)):
        candidate = np.asarray(
            triangles
            + [[item[0], item[2], item[1]] if flip_bottom else item for item in bottom_cap]
            + [[item[0], item[2], item[1]] if flip_top else item for item in top_cap], dtype=np.uint64)
        # The wall ring runs counter-clockwise, which leaves the wall triangles facing inward:
        # MESH64 accepts both orientations but reports a signed volume, so pair each cap choice
        # with the global reversal as well. Only the outward-facing one has volume > 0.
        for candid in (candidate, candidate[:, ::-1].copy()):
            solid = manifold.Manifold(manifold.Mesh64(
                np.array(vertices, dtype=np.float64, order="C", copy=True), candid))
            if solid.status() == manifold.Error.NoError and not solid.is_empty() \
                    and solid.volume() > 0.0:
                # Export through the repository's own entity -> triangle-mesh route, so the saved
                # signed volume is by construction the one the pinned MESH64 kernel measures. A
                # hand-rolled double-precision volume agrees with MESH64 only to ~1e-6 relative,
                # because MESH64 re-welds near-coincident vertices on the way in: that tolerance
                # mismatch, not the winding, is what made the first attempt report
                # "no consistent winding found".
                from terrain_pipeline.hybrid_cave_geometry import save_manifold
                return save_manifold(solid, origin, role)
    raise RuntimeError("MESH64 refused every winding of the pillar solid")


def pillar_solid(ring, height, cell_phase, *, carve, cell_index, role, parameters=None,
                 origin=None):
    """One closed vertical prism. Uncarved, it is the repository's own polygon_prism_record.

    The role is fixed at creation time and never patched afterwards: ``mesh_record`` seals each
    record, so a later field assignment would leave ``identity_sha256`` describing the older
    content. The archived prototype patched the role after sealing; that defect is not carried
    over here.
    """
    parameters = PillarParameters() if parameters is None else parameters
    if not isinstance(parameters, PillarParameters):
        raise ValueError("explicit PillarParameters required")
    origin = _origin(origin)
    if not isinstance(role, str) or not role:
        raise ValueError("explicit pillar role required")
    if not carve:
        return polygon_prism_record(ring, 0.0, float(height), origin, role), 0.0
    folded = None
    for scale in parameters.carve_backoff:
        try:
            return _carved_solid(ring, float(height), float(cell_phase), float(scale), parameters,
                                 int(cell_index), role, origin), float(scale)
        except FoldedSection as exc:
            folded = exc
    raise RuntimeError("carve folds %s even at scale 0" % (folded,))


# --------------------------------------------------------------- cold reading

def plane_section_segments(record, axis, value):
    """Intersect the saved closed mesh with one axis-aligned plane (world metres).

    Returns explicit triangle/plane crossing segments in the two remaining coordinates, so a
    true section is drawn from the actual mesh rather than from the parameters. The crossing
    search is vectorised over triangles, because the carved field has ~2e5 of them and a
    per-triangle Python loop would make a section sweep impractical.
    """
    vertices = np.asarray(record["vertices_local_xyz_m"], float) \
        + np.asarray(record["local_origin_xyz_m"], float)
    triangles = np.asarray(record["triangles"], int)
    points = vertices[triangles]
    distances = points[:, :, axis] - float(value)
    keep = [index for index in range(3) if index != axis]
    grouped = {}
    for first, second in ((0, 1), (1, 2), (2, 0)):
        a, b = distances[:, first], distances[:, second]
        crossing = ((a <= 0.) & (b >= 0.)) | ((b <= 0.) & (a >= 0.))
        selected = np.nonzero(crossing & (a != b))[0]
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
            segments.append((np.asarray(hits[0], float), np.asarray(hits[1], float)))
        elif len(hits) == 3:
            unique = sorted({tuple(np.round(hit, 9)) for hit in hits})
            if len(unique) == 2:
                segments.append((np.asarray(unique[0], float), np.asarray(unique[1], float)))
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
        start = np.round(np.asarray(first, float), int(snap_decimals))
        end = np.round(np.asarray(second, float), int(snap_decimals))
        if not np.array_equal(start, end):
            lines.append(LineString([tuple(start), tuple(end)]))
    return len([item for item in polygonize(lines) if item.area > 0.])


def simple_section_census(record, height, parameters):
    """Sweep one pillar: how many mesh-derived horizontal sections are a single simple polygon.

    The levels are deliberately placed between wall levels, so the section never coincides with
    a plane full of mesh vertices and no triangle can be dropped as degenerate.
    """
    checked, folded = 0, 0
    for value in np.arange(parameters.substep_m * .5, float(height) - 1e-9,
                           parameters.substep_m * 2.0):
        checked += 1
        if section_polygon_count(record, float(value)) != 1:
            folded += 1
    return checked, folded


def winding_number(vertices_local_xyz_m, triangles, point_world_xyz_m, origin):
    """Independent winding number of a closed triangle mesh about one point.

    Sums the signed solid angle of every triangle (Van Oosterom-Strackee) and divides by 4*pi,
    using only the saved mesh arrays -- no manifold3d and no ray casting. A closed
    outward-oriented solid gives 1.0 for an interior point and 0.0 for an exterior one, so a
    cold reader can recompute containment from the saved record alone.
    """
    origin = np.asarray(origin, float)
    points = np.asarray(vertices_local_xyz_m, float) + origin - np.asarray(point_world_xyz_m, float)
    total = 0.
    for triangle in np.asarray(triangles, int):
        first, second, third = (points[index] for index in triangle)
        lengths = (np.linalg.norm(first), np.linalg.norm(second), np.linalg.norm(third))
        numerator = float(np.dot(first, np.cross(second, third)))
        denominator = (lengths[0] * lengths[1] * lengths[2]
                       + float(np.dot(first, second)) * lengths[2]
                       + float(np.dot(second, third)) * lengths[0]
                       + float(np.dot(third, first)) * lengths[1])
        total += 2. * math.atan2(numerator, denominator)
    return total / (4. * math.pi)


def inside_by_winding(record, point_world_xyz_m, origin):
    winding = winding_number(record["vertices_local_xyz_m"], record["triangles"],
                             point_world_xyz_m, origin)
    return bool(round(winding) == 1), float(winding)


def contains_point(solid, world_point, origin):
    """Independent containment: intersect a tiny closed cube with the solid.

    A MESH64 Boolean rather than a ray-parity count, so a grazing ray cannot fake it. Returns
    the overlap volume in m^3 (0.0 means the point is outside).
    """
    import manifold3d as manifold
    local = tuple(float(value) for value
                  in (np.asarray(world_point, float) - np.asarray(origin, float)))
    probe = manifold.Manifold.cube((PROBE_CUBE_EDGE_M,) * 3, center=True).translate(local)
    return float((probe ^ solid).volume())


def _origin(origin):
    origin = DEFAULT_ORIGIN.copy() if origin is None else np.asarray(origin, float)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("finite three-component local origin required")
    return origin


def _pin(record):
    return {"role": record["role"], "identity_sha256": record["identity_sha256"],
            "signed_volume_m3": record["signed_volume_m3"]}


# ------------------------------------------------------------------- assembly

def build(carve=True, parameters=None, origin=None):
    """Assemble the pillar field and measure it. Nothing is certified."""
    if type(carve) is not bool:
        raise ValueError("explicit boolean carve flag required")
    parameters = PillarParameters() if parameters is None else parameters
    if not isinstance(parameters, PillarParameters):
        raise ValueError("explicit PillarParameters required")
    origin = _origin(origin)
    polygons, heights, centres, half_extent = joint_cells(parameters)
    phases = np.random.default_rng(parameters.seed + 7).uniform(0.0, 2.0 * math.pi,
                                                                size=len(polygons))
    records, roles, scales, sections = [], [], [], []
    for index, (ring, height) in enumerate(zip(polygons, heights)):
        role = "%s%02d" % (PILLAR_ROLE_PREFIX, index)
        record, scale = pillar_solid(ring, float(height), float(phases[index]), carve=carve,
                                     cell_index=index, role=role, parameters=parameters,
                                     origin=origin)
        records.append(record)
        roles.append(role)
        scales.append(float(scale))
        checked, folded = simple_section_census(record, float(height), parameters)
        sections.append({"role": role, "height_m": float(height), "sections_checked": checked,
                         "sections_folded": folded})
    base_ring = [[-half_extent, -half_extent], [half_extent, -half_extent],
                 [half_extent, half_extent], [-half_extent, half_extent]]
    base = polygon_prism_record(base_ring, -parameters.base_thickness_m, 0.0, origin, PLATEAU_ROLE)
    start = time.time()
    result, meshes = combine(records + [base], origin, SOLID_ROLE, BooleanParameters())
    elapsed = time.time() - start
    solid = solid_from_record(meshes[SOLID_ROLE], SOLID_ROLE)
    witnesses = field_witnesses(solid, meshes[SOLID_ROLE], polygons, heights, centres, records,
                                roles, parameters, origin, sections)
    footprints = [{"index": index, "role": roles[index], "height_m": float(heights[index]),
                   "carve_scale": float(scales[index]),
                   "signed_volume_m3": float(records[index]["signed_volume_m3"]),
                   "centre_xz_m": [float(polygons[index].mean(axis=0)[0]),
                                   float(polygons[index].mean(axis=0)[1])],
                   "base_ring_xz_m": [[float(point[0]), float(point[1])]
                                      for point in polygons[index]],
                   "ring_area_m2": ring_area(polygons[index])}
                  for index in range(len(records))]
    return {"carve": carve, "result": result, "meshes": meshes,
            "solids": {PLATEAU_ROLE: base, SOLID_ROLE: meshes[SOLID_ROLE]},
            "pillar_records": records, "pillar_roles": roles, "pillar_pins": [_pin(item) for item in records],
            "pillar_footprints": footprints,
            "plateau_ring_xz_m": [[float(point[0]), float(point[1])] for point in base_ring],
            "plateau_bottom_y_m": float(-parameters.base_thickness_m), "plateau_top_y_m": 0.,
            "scales": scales, "heights": [float(value) for value in heights],
            "sections": sections, "witnesses": witnesses, "solid": solid, "origin": origin,
            "parameters": parameters, "polygons": polygons, "centres": centres,
            "footprint_half_extent_m": float(half_extent), "union_seconds": elapsed,
            "level_schedule": {"pillar_index": 0, "substep_m": float(parameters.substep_m),
                               "levels_m": [float(value) for value in
                                            wall_levels(float(heights[0]), parameters.substep_m)]}}


def field_witnesses(solid, union, polygons, heights, centres, records, roles, parameters, origin,
                    sections):
    """Measure the field instead of asserting it.

    Every witness is one of the three cold-readable shapes: winding-number containment
    (recomputable from the saved mesh alone), a ray replay against the saved solid, or a MESH64
    volume census. All coordinates are **world metres**.
    """
    axis_x, axis_z = float(origin[0]), float(origin[2])
    tall = int(np.argmax(heights))
    tall_centre = polygons[tall].mean(axis=0)
    tall_height = float(heights[tall])
    # A neighbour pair of the seed grid: their shared Voronoi edge is exactly the midpoint of
    # the two seeds, and each cell was shrunk by half a joint gap, so the midpoint is void rock.
    if parameters.cols >= 2:
        left, right = 0, 1
    else:
        left, right = 0, parameters.cols if len(centres) > 1 else 0
    gap_xz = .5 * (centres[left] + centres[right]) if right != left else centres[0] + np.array([.5 * parameters.pitch_m, 0.])
    gap_height = min(float(heights[left]), float(heights[right]))
    gap_xyz = [float(gap_xz[0]) + axis_x, gap_height / 3., float(gap_xz[1]) + axis_z]
    gap_top = [gap_xyz[0], parameters.height_max_m + 50., gap_xyz[2]]
    gap_bottom = [gap_xyz[0], 1., gap_xyz[2]]
    inside_xyz = [float(tall_centre[0]) + axis_x, tall_height * .5, float(tall_centre[1]) + axis_z]
    far_xyz = [axis_x + parameters.footprint_half_extent_m + 100., parameters.height_max_m * .5, axis_z]
    shaft_top = [float(tall_centre[0]) + axis_x, tall_height + 50., float(tall_centre[1]) + axis_z]
    gap_inside, gap_winding = inside_by_winding(union, gap_xyz, origin)
    inside_inside, inside_winding = inside_by_winding(union, inside_xyz, origin)
    far_inside, far_winding = inside_by_winding(union, far_xyz, origin)
    gap_hits = ray_hits(solid, gap_bottom, gap_top, origin)
    shaft_hits = ray_hits(solid, [inside_xyz[0], 1., inside_xyz[2]], shaft_top, origin)
    top_hit = max((hit["position_xyz_m"][1] for hit in shaft_hits), default=-math.inf)
    components = census(solid)
    base_delta = min(abs(float(centre[0]) - float(gap_xz[0])) for centre in centres)
    return {
        "inter_pillar_gap_is_void": {
            "method": "Solid.winding", "solid_role": SOLID_ROLE, "point_xyz_m": gap_xyz,
            "expected_inside": False, "verdict": bool(not gap_inside),
            "claim": "the open vertical joint between two neighbouring pillars carries no rock, "
                     "so the field really is a set of separate bodies rather than one mass",
            "observed": {"winding": gap_winding, "inside": gap_inside},
            "probe_cube_intersection_volume_m3": contains_point(solid, gap_xyz, origin),
            "neighbour_roles": [roles[left], roles[right]],
            "neighbour_heights_m": [float(heights[left]), float(heights[right])],
            "joint_gap_m": parameters.joint_gap_m,
            "distance_to_nearest_seed_m": float(base_delta)},
        "control_point_inside_pillar": {
            "method": "Solid.winding", "solid_role": SOLID_ROLE, "point_xyz_m": inside_xyz,
            "expected_inside": True, "verdict": bool(inside_inside),
            "claim": "control: the centroid of the tallest pillar at half its height is inside "
                     "the union, so the void verdict above is not vacuous",
            "observed": {"winding": inside_winding, "inside": inside_inside},
            "pillar_role": roles[tall], "pillar_height_m": tall_height,
            "probe_cube_intersection_volume_m3": contains_point(solid, inside_xyz, origin)},
        "control_point_far_outside": {
            "method": "Solid.winding", "solid_role": SOLID_ROLE, "point_xyz_m": far_xyz,
            "expected_inside": False, "verdict": bool(not far_inside),
            "claim": "control: a point well outside the field footprint is outside the union",
            "observed": {"winding": far_winding, "inside": far_inside},
            "probe_cube_intersection_volume_m3": contains_point(solid, far_xyz, origin)},
        "vertical_ray_from_gap_leaves_field_without_hitting_rock": {
            "method": "Manifold.ray_cast", "solid_role": SOLID_ROLE,
            "from_xyz_m": gap_bottom, "to_xyz_m": gap_top,
            "expected_hit_count": 0, "verdict": bool(len(gap_hits) == 0),
            "claim": "a segment rising through the inter-pillar joint from 1 m to above the "
                     "tallest pillar never meets rock: the joint is open all the way up",
            "observed": {"hit_count": len(gap_hits), "hits": gap_hits}},
        "vertical_ray_from_pillar_base_hits_top_cap": {
            "method": "Manifold.ray_cast", "solid_role": SOLID_ROLE,
            "from_xyz_m": [inside_xyz[0], 1., inside_xyz[2]], "to_xyz_m": shaft_top,
            "expected_minimum_hit_count": 1,
            "verdict": bool(len(shaft_hits) >= 1 and math.isfinite(top_hit)
                            and abs(top_hit - tall_height) <= 2.),
            "claim": "a segment rising inside the tallest pillar leaves the solid at its own "
                     "top elevation, so the pillar really is a closed column of that height",
            "observed": {"hit_count": len(shaft_hits), "highest_hit_y_m": top_hit,
                         "pillar_height_m": tall_height,
                         "hits": [{"face_id": hit["face_id"], "distance": hit["distance"],
                                   "position_xyz_m": hit["position_xyz_m"]} for hit in shaft_hits]}},
        "union_single_connected_component": {
            "method": "Mesh64_boolean", "operation": "add",
            "input_roles": [PLATEAU_ROLE] + roles,
            "expected_rock_after_m3": union["signed_volume_m3"], "expected_removed_m3": 0.,
            "verdict": bool(components == 1),
            "claim": "the base plateau touches every pillar at y = 0, so the field is one "
                     "connected closed solid rather than a bag of loose columns",
            "observed": {"component_count": components, "declared_minimum_components": 1,
                         "assembled_volume_m3": union["signed_volume_m3"]}},
        "every_horizontal_section_is_simple": {
            "method": "Shapely.section", "axis": "y", "solid_roles": roles,
            "verdict": bool(all(item["sections_folded"] == 0 and item["sections_checked"] > 0
                                 for item in sections)),
            "claim": "every horizontal section of every pillar, taken from the saved mesh and "
                     "stitched back into polygons, is a single simple polygon: no carved wall "
                     "folds through itself",
            "sections_checked": int(sum(item["sections_checked"] for item in sections)),
            "sections_folded": int(sum(item["sections_folded"] for item in sections)),
            "every_section_simple": bool(all(item["sections_folded"] == 0
                                             for item in sections)),
            "section_endpoint_snap_m": 1e-6,
            "method_note": "a section crossing on a shared vertical edge is computed twice, "
                           "from the two triangles meeting there, and the two results differ "
                           "by ~1e-11 m; Shapely polygonize needs exactly equal endpoints, so "
                           "the endpoints are snapped to 1e-6 m before stitching. Without that "
                           "snap a perfectly straight prism reports zero polygons -- a false "
                           "negative, not a fold",
            "per_pillar": [dict(item) for item in sections]},
    }


def volume_account(geometry, plain_geometry):
    """The saved volumes, accounted for without any implicit fill.

    Pillars stand apart by a joint gap and the plateau lies below y = 0, so the union should
    lose nothing to overlap; the account records the actual number instead of asserting it.
    """
    pillars = float(sum(record["signed_volume_m3"] for record in geometry["pillar_records"]))
    plateau = float(geometry["solids"][PLATEAU_ROLE]["signed_volume_m3"])
    assembled = float(geometry["solids"][SOLID_ROLE]["signed_volume_m3"])
    total = pillars + plateau
    return {"pillar_count": len(geometry["pillar_records"]),
            "sum_pillar_signed_volume_m3": pillars,
            "plateau_signed_volume_m3": plateau,
            "inputs_total_m3": total,
            "assembled_volume_m3": assembled,
            "overlap_removed_m3": total - assembled,
            "overlap_removed_relative": (total - assembled) / total if total else 0.,
            "meshed_union_volume_m3": float(geometry["solid"].volume()),
            "relative_residual": abs(assembled - float(geometry["solid"].volume())) / assembled,
            "full_depth_pillars": int(sum(1 for scale in geometry["scales"] if scale >= 1.)),
            "carve_scales": [round(float(scale), 3) for scale in geometry["scales"]],
            "uncarved_variant_assembled_volume_m3":
                float(plain_geometry["solids"][SOLID_ROLE]["signed_volume_m3"]),
            "carved_removed_m3": float(plain_geometry["solids"][SOLID_ROLE]["signed_volume_m3"])
                                 - assembled,
            "fill_rock_m3": 0., "implicit_fill_or_clamping": False}


def variant_summary(geometry):
    record = geometry["solids"][SOLID_ROLE]
    return {"carve": bool(geometry["carve"]),
            "vertices": len(record["vertices_local_xyz_m"]),
            "triangles": len(record["triangles"]),
            "assembled_volume_m3": float(record["signed_volume_m3"]),
            "components": int(geometry["result"]["census"]["assembled_components"]),
            "carve_scales": [round(float(scale), 3) for scale in geometry["scales"]],
            "full_depth_pillars": int(sum(1 for scale in geometry["scales"] if scale >= 1.)),
            "height_range_m": [float(min(geometry["heights"])), float(max(geometry["heights"]))],
            "union_seconds": round(float(geometry["union_seconds"]), 4),
            "mesh_identity_sha256": record["identity_sha256"],
            "solid_gate": "closed_two_use_manifold_volume_gated",
            "sections_checked": int(sum(item["sections_checked"] for item in geometry["sections"])),
            "sections_folded": int(sum(item["sections_folded"] for item in geometry["sections"]))}


def _library_versions():
    from importlib.metadata import version
    return {"manifold3d": version("manifold3d"), "numpy": np.__version__,
            "scipy": version("scipy"), "shapely": version("shapely")}


def _derived(parameters):
    return {"pillar_count": parameters.pillar_count,
            "height_band_m": list(parameters.height_band_m),
            "footprint_half_extent_m": parameters.footprint_half_extent_m,
            "base_footprint_extent_m": 2. * parameters.footprint_half_extent_m,
            "maximum_taper_contraction_fraction": parameters.taper_fraction,
            "cap_fraction_of_shortest_pillar": parameters.cap_thickness_m / parameters.height_min_m,
            "joint_gap_m": parameters.joint_gap_m,
            "half_joint_gap_m": .5 * parameters.joint_gap_m,
            "striation_levels": len(parameters.striation_amplitude_m),
            "flute_levels": len(parameters.flute_amplitude_m),
            "carve_backoff_steps": len(parameters.carve_backoff),
            "wall_levels_of_tallest_pillar":
                int(len(wall_levels(parameters.height_max_m, parameters.substep_m)))}


# ----------------------------------------------------------------- rendering

def _save(figure, output_directory, name):
    path = Path(output_directory) / name
    figure.savefig(path, dpi=120, metadata={"Software": "special_terrain_pillars3d"})
    import matplotlib.pyplot as plt
    plt.close(figure)
    return {"name": name, "path": path.as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def render(geometry, output_directory):
    """Plan, wall profile and 3D views of the saved union. Display only, never evidence."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    matplotlib.rcParams["font.family"] = ["Microsoft YaHei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    parameters = geometry["parameters"]
    polygons = geometry["polygons"]
    heights = geometry["heights"]
    origin = geometry["origin"]
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    union = geometry["solids"][SOLID_ROLE]
    vertices = np.asarray(union["vertices_local_xyz_m"], float) + np.asarray(origin, float)
    triangles = np.asarray(union["triangles"], int)
    phases = np.random.default_rng(parameters.seed + 7).uniform(0.0, 2.0 * math.pi,
                                                                size=len(polygons))
    panel = []

    # (a) plan: the joint cells, and one cell's carved outline at three elevations
    figure, axes = plt.subplots(figsize=(8.4, 8.4))
    for ring in polygons:
        closed = np.vstack((ring, ring[:1]))
        axes.plot(closed[:, 0], closed[:, 1], color="#7b5e2e", linewidth=.9)
    axes.scatter(geometry["centres"][:, 0], geometry["centres"][:, 1], s=8., color="#c62828",
                 zorder=5, label="节理种子点 (joint seeds)")
    ring = polygons[0]
    height = float(heights[0])
    perimeter_s = perimeter_arc_length(ring)
    for y, colour, label in ((0., "#2e7d32", "底 y = 0"),
                             (height * .5, "#1565c0", "中 y = h/2"),
                             (height, "#6a1b9a", "顶 y = h")):
        outline = wall_ring_at(ring, perimeter_s, y, height, float(phases[0]), True, parameters)
        closed = np.vstack((outline, outline[:1]))
        axes.plot(closed[:, 0], closed[:, 1], color=colour, linewidth=1.4, label=label)
    axes.annotate("多边形棱柱截面 (polygonal prism section),\n不是高度场能给出的圆盘",
                  xy=(float(polygons[0][:, 0].min()), float(polygons[0][:, 1].min())),
                  xytext=(-parameters.footprint_half_extent_m * .95,
                          -parameters.footprint_half_extent_m * .78),
                  fontsize=8, arrowprops={"arrowstyle": "->", "lw": .8})
    axes.set_aspect("equal")
    axes.set_xlabel("x (m)")
    axes.set_ylabel("z (m)")
    axes.set_title("%d 个节理胞：不规则多边形平面截面 (plan view, synthetic analytic, not TD)"
                   % len(polygons))
    axes.legend(fontsize=7, loc="upper right")
    axes.grid(alpha=.2)
    figure.tight_layout()
    panel.append(_save(figure, output, "pillars3d-a-plan.png"))

    # (b) one pillar's wall profile along two perimeter rays: taper and the iron cap
    figure, axes = plt.subplots(figsize=(7.6, 7.0))
    centre = ring.mean(axis=0)
    radii = np.linalg.norm(ring - centre, axis=1)
    levels = wall_levels(height, parameters.substep_m)
    for index, colour, label in ((int(np.argmax(radii)), "#1565c0", "最远壁点 (farthest arris)"),
                                 (int(np.argmin(radii)), "#2e7d32", "最近壁点 (nearest face)")):
        profile = [float(np.linalg.norm(
            wall_ring_at(ring, perimeter_s, float(y), height, float(phases[0]), True, parameters)[index]
            - centre)) for y in levels]
        axes.plot(profile, levels, color=colour, linewidth=1.4, label=label)
    axes.axhline(height - parameters.cap_thickness_m, color="#6a1b9a", linestyle="--", linewidth=1.,
                 label="铁帽下界 (iron cap base, %.0f m)" % parameters.cap_thickness_m)
    axes.annotate("上细下粗 (taper %.0f%%)：绕自身质心的相似收缩"
                  % (parameters.taper_fraction * 100.),
                  xy=(float(min(radii)) * .99, height * .55),
                  xytext=(float(min(radii)) * .55, height * .82),
                  fontsize=8, arrowprops={"arrowstyle": "->", "lw": .8})
    axes.annotate("铁帽外凸 (cap bulge %.1f m)" % parameters.cap_bulge_m,
                  xy=(float(max(radii)) * 1.02, height - parameters.cap_thickness_m * .5),
                  xytext=(float(max(radii)) * .8, height * .18),
                  fontsize=8, arrowprops={"arrowstyle": "->", "lw": .8})
    axes.set_xlabel("距柱截面质心的径向距离 (m)")
    axes.set_ylabel("y elevation (m)")
    axes.set_title("单柱壁剖面：每条周边射线的半径随高程变化")
    axes.legend(fontsize=7, loc="upper left")
    axes.grid(alpha=.2)
    figure.tight_layout()
    panel.append(_save(figure, output, "pillars3d-b-wall-profile.png"))

    # (c) the closed union itself
    figure = plt.figure(figsize=(9., 7.4))
    axes = figure.add_subplot(111, projection="3d")
    faces = vertices[triangles][::max(1, len(triangles) // 6000)]
    axes.add_collection3d(Poly3DCollection(faces, facecolor="#c8853f", edgecolor="#6b4f1d",
                                           linewidths=.05, alpha=.95))
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    axes.set_xlim(low[0], high[0])
    axes.set_ylim(low[2], high[2])
    axes.set_zlim(low[1], high[1])
    axes.set_xlabel("x (m)")
    axes.set_ylabel("z (m)")
    axes.set_zlabel("y elevation (m)")
    axes.set_title("石柱群闭合 MESH64 实体：%d 面" % len(triangles))
    figure.tight_layout()
    panel.append(_save(figure, output, "pillars3d-c-solid.png"))
    return panel


# ------------------------------------------------------------------- report

def report(parameters=None, origin=None, output_directory=None, carve=True, compare=True):
    """Build both variants and seal the contract-shaped report for cold reading.

    ``compare`` builds the uncarved variant too; the report always carries the plain summary
    because the difference between the two is the only honest statement of what VDM added.
    """
    carved = build(True, parameters, origin)
    plain = carved if not compare else build(False, carved["parameters"], carved["origin"])
    primary = carved if carve else plain
    parameters = primary["parameters"]
    origin = primary["origin"]
    figures = [] if output_directory is None else render(primary, output_directory)
    record = {"schema": REPORT_SCHEMA, "algorithm": ALGORITHM, "status": "candidate",
              "parent_algorithm": PARENT_ALGORITHM, "supersedes": dict(SUPERSEDES),
              "synthetic_base": {"kind": BASE_KIND,
                                 "note": "the base plateau is analytic geometry, not TD native terrain "
                                         "and not surveyed"},
              "world_frame": WORLD_FRAME_NOTE,
              "local_origin_xyz_m": [float(value) for value in origin],
              "parameters": asdict(parameters), "derived": _derived(parameters),
              "explicit_assumptions": [dict(item) for item in EXPLICIT_ASSUMPTIONS],
              "geology_note": GEOLOGY_NOTE,
              "solids": {role: dict(mesh) for role, mesh in primary["solids"].items()},
              "pillar_pins": [dict(item) for item in primary["pillar_pins"]],
              "pillar_footprints": [dict(item) for item in primary["pillar_footprints"]],
              "level_schedule": dict(primary["level_schedule"]),
              "plateau_ring_xz_m": [list(point) for point in primary["plateau_ring_xz_m"]],
              "plateau_bottom_y_m": float(primary["plateau_bottom_y_m"]),
              "plateau_top_y_m": float(primary["plateau_top_y_m"]),
              "boolean": primary["result"], "witnesses": primary["witnesses"],
              "volume_account": volume_account(carved, plain),
              "variants": {"primary": "vdm_carved_walls" if carve else "plain_prisms",
                           "plain_prisms": variant_summary(plain),
                           "vdm_carved_walls": variant_summary(carved)},
              "flags": {flag: False for flag in FLAGS},
              "library_versions": _library_versions(), "figures": figures,
              "figure_scope": FIGURE_SCOPE,
              "sampled_not_native_exact": True, "water_generated": False}
    seal(record)
    return record, {"carved": carved, "plain": plain, "primary": primary,
                    "solid": primary["solid"], "origin": origin, "parameters": parameters,
                    "solids": primary["solids"], "result": primary["result"],
                    "witnesses": primary["witnesses"], "polygons": primary["polygons"],
                    "centres": primary["centres"], "heights": primary["heights"],
                    "scales": primary["scales"], "sections": primary["sections"],
                    "pillar_records": primary["pillar_records"],
                    "pillar_footprints": primary["pillar_footprints"],
                    "level_schedule": primary["level_schedule"],
                    "plateau_ring_xz_m": primary["plateau_ring_xz_m"],
                    "plateau_bottom_y_m": primary["plateau_bottom_y_m"],
                    "plateau_top_y_m": primary["plateau_top_y_m"]}


def encode_report(record):
    """Compact, key-sorted, NaN-refusing JSON bytes; identical input gives identical bytes."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def report_identity(record):
    return identity({key: value for key, value in record.items() if key != "identity_sha256"})


def write_report(path, parameters=None, origin=None, output_directory=None, carve=True,
                 compare=True):
    record, geometry = report(parameters, origin, output_directory, carve, compare)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_report(record))
    return record, geometry


def save_arrays(directory, geometry):
    """Save both variants' mesh arrays so the browser never has to parse the report."""
    saved = []
    for label, item in (("plain", geometry["plain"]), ("carved", geometry["carved"])):
        record = item["solids"][SOLID_ROLE]
        path = Path(directory) / (label + ".npz")
        np.savez_compressed(path,
                            vertices_local_xyz_m=np.asarray(record["vertices_local_xyz_m"], np.float64),
                            triangles=np.asarray(record["triangles"], np.int64),
                            local_origin_xyz_m=np.asarray(record["local_origin_xyz_m"], np.float64),
                            signed_volume_m3=np.asarray([record["signed_volume_m3"]], np.float64),
                            identity_sha256=np.asarray([record["identity_sha256"]]),
                            role=np.asarray([SOLID_ROLE]))
        saved.append({"name": path.name, "path": path.as_posix(),
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "vertices": len(record["vertices_local_xyz_m"]),
                      "triangles": len(record["triangles"]),
                      "signed_volume_m3": float(record["signed_volume_m3"]),
                      "mesh_identity_sha256": record["identity_sha256"]})
    return saved


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    output = Path(argv[0]) if argv else DEFAULT_OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    record, geometry = write_report(output / "report.json", output_directory=output)
    arrays = save_arrays(output, geometry)
    print(json.dumps({"status": record["status"], "report": (output / "report.json").as_posix(),
                      "union_volume_m3": record["volume_account"]["assembled_volume_m3"],
                      "components": record["boolean"]["census"]["assembled_components"],
                      "pillars": record["volume_account"]["pillar_count"],
                      "full_depth_pillars": record["volume_account"]["full_depth_pillars"],
                      "carve_scales": record["volume_account"]["carve_scales"],
                      "height_range_m": record["variants"]["vdm_carved_walls"]["height_range_m"],
                      "variants": record["variants"],
                      "witness_verdicts": {name: witness["verdict"]
                                           for name, witness in record["witnesses"].items()},
                      "arrays": arrays, "figures": record["figures"],
                      "identity_sha256": record["identity_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
