"""Finite 1600 km fictional-world overview: three continents, islands, mountains, rivers.

What this module produces
-------------------------
One low-resolution **overview / planning map** of a single finite square world frame:
``extent_km`` on a side, ``grid_size`` cell-centre samples per side, node spacing
``extent_km * 1000 / grid_size`` metres (1024 samples over 1600 km is 1562.5 m).
The land is exactly three continents above a declared area gate plus a set of
small islands; nothing touches the frame border.  Elevation, a continuous
mountain belt and a small set of diagnostic mainstem rivers are exported with a
JSON report that records seeds, parameters, method, limitations and checks.

What this module is *not*
-------------------------
* **Not a Terrain Diffusion product.**  Nothing here calls the TD model, the
  native 30 m pages, ``metric_cross_region`` or any stage-one river chain, and no
  array produced here may be fed to those interfaces as terrain.  The grid is a
  ~1.5 km planning grid, not 30 m; the elevation is an analytic construction.
* **Not a hydraulic result.**  No shallow water, no Manning conveyance, no
  sediment, no evapotranspiration.  The rivers are *diagnostic
  contributing-area paths* (one receiver per node, irregular graph, with the filled working
  surface recorded separately from the exported elevation), so "drainage" here
  means "under irregular graph on this exported grid", never "measured discharge".  No outlet
  is certified natural.
* **Not a stage-one acceptance.**  Passing this module's own checks says the
  three-continent layout, the ocean border and the acyclic river paths hold on
  *this* overview grid; it says nothing about the 30 m TD chain.

Determinism
-----------
Every random decision is drawn from ``sha256``-derived sub-seeds of one world
seed and a stable purpose name (:func:`derive_subseed`), and the noise is sampled
at absolute metre coordinates from the declared frame origin.  Python's
``hash()``, wall-clock time, system entropy and load order are never used, so the
same request reproduces byte-identical arrays.

Coordinate convention
---------------------
``x`` is east, ``z`` is south, both in metres from the north-west frame corner.
Node ``(i, j)`` (row ``i``, column ``j``) samples the *centre* of its cell:
``x = (j + 0.5) * spacing_m``, ``z = (i + 0.5) * spacing_m``; the cell area is
``spacing_m ** 2``.  A ``grid_size`` of N means N x N cell-centre samples that
cover the frame ``[0, extent_m)`` *by cell edges* -- N cells of ``spacing`` each.
The sample centres themselves only span ``(N - 1) * spacing``.  Both numbers are
reported separately (:meth:`OverviewRequest.grid_contract`) and must never be
used interchangeably.

Elevation is metres above the declared sea-level datum (``SEA_LEVEL_M = 0``);
**negative values are sea floor** and are both allowed and expected.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import receiver_edges_valid as receiver_edges_valid
from terrain_pipeline.drainage import reverse_donors as reverse_donors

import numpy as np
from scipy import ndimage

from diffusion.geographic_noise import field as absolute_noise_field
from terrain_pipeline.artifacts.contracts import array_hash, canonical_json
from terrain_pipeline.drainage import accumulate as accumulate
from terrain_pipeline.drainage import route as route

# ---------------------------------------------------------------------------
# Declared identity and bounds.  These are contracts, not tunables: the arrays,
# the JSON report and the tests all read them from here.
# ---------------------------------------------------------------------------
SCHEMA_VERSION = "fictional-world-overview-v2-irregular"
ALGORITHM = "analytic-constrained-landmass-overview-v1"
SEED_NAMESPACE = "terragenesis-fictional-world-overview-v1"

DEFAULT_WORLD_SEED = 20261020
DEFAULT_EXTENT_KM = 1600.0
DEFAULT_GRID_SIZE = 1024

MIN_GRID_SIZE = 96
MAX_GRID_SIZE = 2048
MIN_EXTENT_KM = 200.0
MAX_EXTENT_KM = 4000.0

#: The layout contract: exactly this many landmasses above the area gate.
CONTINENT_COUNT = 3
#: Admissible island count, inclusive.  Islands are everything else.
ISLAND_COUNT_RANGE = (6, 15)

#: Declared *before* any generation: a connected component is a continent when its
#: area is at least this fraction of the whole frame (1600 x 1600 km => 2.56e6 km2,
#: so 0.015 is 38 400 km2, a disc of radius ~110 km).  Everything below the gate is
#: a small island.  The gate is applied to the *final* 8-connected components.
CONTINENT_MIN_AREA_FRACTION = 0.015

#: Minimum clear water between any two landmasses, kilometres.
MIN_STRAIT_KM = 80.0

#: Fraction of the frame side kept free of land on all four sides, and its floor in
#: cells.  This is what makes "ocean on all four borders" geometric rather than hoped.
BORDER_BAND_FRACTION = 0.03
MIN_BORDER_BAND_CELLS = 3

#: Complete layout attempts before the request is refused.
LAYOUT_ATTEMPTS = 64
#: Random candidate centres tried per landmass inside one attempt.
PLACEMENT_TRIES = 3000

#: Declared sea-level datum, metres.  Elevation is signed relative to it.
SEA_LEVEL_M = 0.0

#: Design budget of the analytic elevation construction, metres.  The *measured*
#: range of the exported array is reported separately and is the only figure a
#: reader may cite.
LAND_RELIEF_M = 950.0
OCEAN_BASE_DEPTH_M = 2500.0
LAND_RAMP_FRACTION = 0.075
SEA_RAMP_FRACTION = 0.060
INLAND_RAMP_FRACTION = 0.045
MIN_LAND_M = 2.0
MIN_OCEAN_M = 5.0
MAX_ELEVATION_M = 4800.0

#: Mountain belt budget, metres above the ambient land surface.
MAIN_RIDGE_AMPLITUDE_M = 2200.0
BRANCH_RIDGE_AMPLITUDE_M = 1250.0
MAIN_RIDGE_WIDTH_FRACTION = 0.020
BRANCH_RIDGE_WIDTH_FRACTION = 0.013
MAX_MOUNTAIN_ADD_M = 3000.0

#: River export rules, fixed and declared before generation.
RIVER_MAX_PER_CONTINENT = 3
RIVER_MIN_RELATIVE_AREA = 0.25
RIVER_MAX_NODES = 600
#: A mainstem shorter than this is degenerate for a continental-scale overview.
RIVER_MIN_NODES = 8

#: Below this belt value the mountain shading is not drawn at all, so the overlay
#: marks the ridge bands rather than fading the whole continent.
MOUNTAIN_OVERLAY_THRESHOLD = 0.18

_PURPOSE = re.compile(r"[a-z][a-z0-9_]{0,48}\Z")
_EIGHT = np.ones((3, 3), dtype=bool)


class OverviewError(ValueError):
    """Invalid request or invalid intermediate state; nothing is written."""


class LayoutRefused(RuntimeError):
    """The requested frame cannot hold the declared layout; the request is refused.

    A refusal is a *legal, reported* outcome: the caller gets the per-attempt
    reasons and no output files.  The area gate, the strait width and the border
    band are never relaxed to turn a refusal into a success, and no seed is
    promised to succeed.
    """

    def __init__(self, message, attempts=()):
        super().__init__(message)
        self.attempts = tuple(attempts)


class OutputExistsError(FileExistsError):
    """The output destination already exists; overview output is never overwritten."""


# ---------------------------------------------------------------------------
# Seed derivation (CONTRIBUTING: fixed world seed, stable purpose names)
# ---------------------------------------------------------------------------
def derive_subseed(world_seed, purpose, index=0):
    """Stable ``uint64`` sub-seed from the world seed, a purpose name and an index.

    The derivation is ``sha256(NAMESPACE|seed|purpose|index)[:8]`` interpreted
    big-endian; it never uses wall-clock time, system entropy or ``hash()``, so the
    value is reproducible on any machine and is recorded in the report.
    """
    if isinstance(world_seed, (bool, np.bool_)) or not isinstance(world_seed, (int, np.integer)):
        raise OverviewError("world_seed must be an integer")
    if not 0 <= int(world_seed) < 2 ** 64:
        raise OverviewError("world_seed must fit an unsigned 64-bit integer")
    if not isinstance(purpose, str) or not _PURPOSE.match(purpose):
        raise OverviewError("purpose must be a lowercase stable name, got %r" % (purpose,))
    if (isinstance(index, (bool, np.bool_)) or not isinstance(index, (int, np.integer))
            or int(index) < 0):
        raise OverviewError("seed index must be a non-negative integer")
    payload = "%s|%d|%s|%d" % (SEED_NAMESPACE, int(world_seed), purpose, int(index))
    return int.from_bytes(hashlib.sha256(payload.encode("ascii")).digest()[:8], "big")


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OverviewRequest:
    """One overview request.  Everything that changes the arrays is here."""

    seed: int = DEFAULT_WORLD_SEED
    extent_km: float = DEFAULT_EXTENT_KM
    grid_size: int = DEFAULT_GRID_SIZE
    min_strait_km: float = MIN_STRAIT_KM

    def __post_init__(self):
        if isinstance(self.seed, (bool, np.bool_)) or not isinstance(self.seed, (int, np.integer)):
            raise OverviewError("seed must be an integer, got %r" % (self.seed,))
        if not 0 <= int(self.seed) < 2 ** 64:
            raise OverviewError("seed must be an unsigned 64-bit integer")
        extent = _finite("extent_km", self.extent_km)
        if not MIN_EXTENT_KM <= extent <= MAX_EXTENT_KM:
            raise OverviewError("extent_km must lie in [%g, %g], got %g"
                                % (MIN_EXTENT_KM, MAX_EXTENT_KM, extent))
        if (isinstance(self.grid_size, (bool, np.bool_))
                or not isinstance(self.grid_size, (int, np.integer))):
            raise OverviewError("grid_size must be an integer, got %r" % (self.grid_size,))
        if not MIN_GRID_SIZE <= int(self.grid_size) <= MAX_GRID_SIZE:
            raise OverviewError("grid_size must lie in [%d, %d], got %d"
                                % (MIN_GRID_SIZE, MAX_GRID_SIZE, int(self.grid_size)))
        strait = _finite("min_strait_km", self.min_strait_km)
        if strait <= 0.0:
            raise OverviewError("min_strait_km must be positive")

    @property
    def extent_m(self):
        return float(self.extent_km) * 1000.0

    @property
    def spacing_m(self):
        return self.extent_m / float(self.grid_size)

    @property
    def border_band_cells(self):
        return max(MIN_BORDER_BAND_CELLS, int(round(BORDER_BAND_FRACTION * int(self.grid_size))))

    @property
    def cell_area_m2(self):
        return self.spacing_m ** 2

    @property
    def cell_area_km2(self):
        return self.cell_area_m2 / 1.0e6

    @property
    def frame_area_km2(self):
        return float(self.extent_km) ** 2

    @property
    def continent_gate_km2(self):
        return CONTINENT_MIN_AREA_FRACTION * self.frame_area_km2

    def parameters(self):
        return {
            "seed": int(self.seed),
            "extent_km": float(self.extent_km),
            "grid_size": int(self.grid_size),
            "min_strait_km": float(self.min_strait_km),
        }

    def grid_contract(self):
        """The node/cell semantics, stated once so no reader has to guess."""
        spacing = self.spacing_m
        size = int(self.grid_size)
        return {
            "extent_km": float(self.extent_km),
            "grid_size": size,
            "sample_count": size * size,
            "node_spacing_m": spacing,
            "cell_area_m2": self.cell_area_m2,
            "cell_area_km2": self.cell_area_km2,
            "node_semantics": "node (i j) samples the centre of its cell at "
                              "x = (j + 0.5) * node_spacing_m, z = (i + 0.5) * node_spacing_m; "
                              "z increases southward from the north-west frame corner",
            "cell_semantics": "one cell per node, area = node_spacing_m ** 2",
            "frame_edges_m": [0.0, self.extent_m],
            "node_centre_range_m": [0.5 * spacing, self.extent_m - 0.5 * spacing],
            "node_centre_span_m": (size - 1) * spacing,
            "coverage_statement": "N x N cell-centre samples cover [0, extent_m) by cell edges, "
                                  "i.e. N * spacing of frame length; the sample centres themselves "
                                  "span (N - 1) * spacing.  The two are reported separately and are "
                                  "not interchangeable.",
            "frame_area_km2": self.frame_area_km2,
            "border_band_cells": self.border_band_cells,
            "border_band_width_km": self.border_band_cells * spacing / 1000.0,
            "sea_level_m": SEA_LEVEL_M,
            "elevation_sign": "positive above sea level, negative below; negative values are expected",
            "resolution_kind": "low-resolution overview/planning grid, NOT the 30 m TD native grid",
        }


def _finite(name, value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, float, np.floating, np.integer)):
        raise OverviewError("%s must be a number, got %r" % (name, value))
    number = float(value)
    if not math.isfinite(number):
        raise OverviewError("%s must be finite" % name)
    return number


# ---------------------------------------------------------------------------
# Landmass skeleton: lobed outlines with an exact bound on their extent
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Lobe:
    offset_x_m: float
    offset_z_m: float
    semi_x_m: float
    semi_z_m: float
    harmonics: tuple
    extent_m: float


@dataclass(frozen=True)
class LandmassSpec:
    """One intended landmass: a union of lobed ellipse patches around a centre."""

    slot: int
    is_continent: bool
    centre_x_m: float
    centre_z_m: float
    lobes: tuple
    extent_m: float

    def contains(self, x, z):
        grid_x, grid_z = np.broadcast_arrays(np.asarray(x, np.float64), np.asarray(z, np.float64))
        inside = np.zeros(grid_x.shape, dtype=bool)
        for lobe in self.lobes:
            inside |= _inside_lobe(lobe, self.centre_x_m, self.centre_z_m, grid_x, grid_z)
        return inside


@dataclass(frozen=True)
class _Ridge:
    points_m: tuple
    amplitude_m: float
    width_m: float
    is_main: bool


def _lobe(rng, offset_x, offset_z, semi_x, semi_z):
    harmonics = []
    total = 0.0
    for _ in range(2):
        frequency = 2 + int(rng.integers(0, 3))
        amplitude = float(rng.uniform(0.045, 0.10))
        phase = float(rng.uniform(0.0, 2.0 * np.pi))
        harmonics.append((float(frequency), amplitude, phase))
        total += amplitude
    if total > 0.22:
        scale = 0.22 / total
        harmonics = [(f, a * scale, p) for f, a, p in harmonics]
        total = 0.22
    extent = max(semi_x, semi_z) * (1.0 + total)
    return _Lobe(offset_x, offset_z, semi_x, semi_z, tuple(harmonics), extent)


def _inside_lobe(lobe, centre_x, centre_z, x, z):
    u = (x - (centre_x + lobe.offset_x_m)) / lobe.semi_x_m
    v = (z - (centre_z + lobe.offset_z_m)) / lobe.semi_z_m
    rho = np.hypot(u, v)
    theta = np.arctan2(v, u)
    radius = np.ones_like(rho)
    for frequency, amplitude, phase in lobe.harmonics:
        radius = radius + amplitude * np.sin(frequency * theta + phase)
    return rho <= radius


def _draw_continent(rng, extent_m, slot):
    base = extent_m * float(rng.uniform(0.095, 0.135))
    aspect = float(rng.uniform(0.62, 1.00))
    semi_x = base / math.sqrt(aspect)
    semi_z = base * math.sqrt(aspect)
    lobes = [_lobe(rng, 0.0, 0.0, semi_x, semi_z)]
    for _ in range(2 + int(rng.integers(0, 2))):
        angle = float(rng.uniform(0.0, 2.0 * np.pi))
        reach = base * float(rng.uniform(0.55, 0.95))
        semi = base * float(rng.uniform(0.35, 0.62))
        lobes.append(_lobe(rng, reach * math.cos(angle), reach * math.sin(angle),
                           semi / math.sqrt(aspect), semi * math.sqrt(aspect)))
    extent = max(math.hypot(lobe.offset_x_m, lobe.offset_z_m) + lobe.extent_m for lobe in lobes)
    return LandmassSpec(slot, True, 0.0, 0.0, tuple(lobes), extent)


def _draw_island(rng, extent_m, slot):
    base = extent_m * float(rng.uniform(0.013, 0.032))
    aspect = float(rng.uniform(0.70, 1.00))
    lobe = _lobe(rng, 0.0, 0.0, base / math.sqrt(aspect), base * math.sqrt(aspect))
    return LandmassSpec(slot, False, 0.0, 0.0, (lobe,), lobe.extent_m)


def _place(spec, centre_x, centre_z):
    return LandmassSpec(spec.slot, spec.is_continent, float(centre_x), float(centre_z),
                        spec.lobes, spec.extent_m)


def _inner_box(request):
    """Free-of-land inner box in metres, and its centre."""
    spacing = request.spacing_m
    band = request.border_band_cells
    low = band * spacing
    high = (int(request.grid_size) - band) * spacing
    if high <= low:
        raise LayoutRefused("border band %d cells leaves no usable inner box" % band)
    return low, high, 0.5 * (low + high)


def _draw_and_place(request, rng):
    """Draw the skeleton and place every landmass with the declared separations.

    The three continents sit on a jittered equilateral triangle around the frame
    centre; the triangle is sized so that the pairwise water gaps and the border
    band hold *by construction*, not by luck.  Islands are then placed by rejection
    sampling against every already-placed landmass.  Nothing here can produce a
    land bridge: every separation check uses the exact upper bound of the lobed
    outline, so rasterisation only ever pulls land inward.
    """
    extent_m = request.extent_m
    low, high, centre = _inner_box(request)
    half = 0.5 * (high - low)
    strait_m = request.min_strait_km * 1000.0

    continents = [_draw_continent(rng, extent_m, slot) for slot in range(CONTINENT_COUNT)]
    reaches = [spec.extent_m for spec in continents]
    if max(reaches) >= half:
        raise LayoutRefused(
            "continent reach %.1f km does not fit half of the %.1f km inner box"
            % (max(reaches) / 1000.0, (high - low) / 1000.0))
    required = 0.0
    for first in range(CONTINENT_COUNT):
        for second in range(first + 1, CONTINENT_COUNT):
            required = max(required, reaches[first] + reaches[second] + strait_m)
    circum_min = required / math.sqrt(3.0)
    circum_max = half - max(reaches)
    if circum_min > circum_max:
        raise LayoutRefused(
            "three continents of %.0f-%.0f km reach cannot keep %.0f km of water apart inside a "
            "%.0f km inner box" % (min(reaches) / 1000.0, max(reaches) / 1000.0,
                                    strait_m / 1000.0, (high - low) / 1000.0))
    circum = circum_max - float(rng.uniform(0.0, 0.25)) * (circum_max - circum_min)
    rotation = float(rng.uniform(0.0, 2.0 * np.pi / CONTINENT_COUNT))

    placed = []
    for slot in range(CONTINENT_COUNT):
        angle = rotation + 2.0 * np.pi * slot / CONTINENT_COUNT
        placed.append(_place(continents[slot],
                             centre + circum * math.cos(angle),
                             centre + circum * math.sin(angle)))
    _check_separation(placed, low, high, strait_m)

    island_count = int(rng.integers(ISLAND_COUNT_RANGE[0], ISLAND_COUNT_RANGE[1] + 1))
    for island in range(island_count):
        spec = _draw_island(rng, extent_m, CONTINENT_COUNT + island)
        reach = spec.extent_m
        for _ in range(PLACEMENT_TRIES):
            x = float(rng.uniform(low + reach, high - reach))
            z = float(rng.uniform(low + reach, high - reach))
            if all(math.hypot(x - other.centre_x_m, z - other.centre_z_m)
                   >= reach + other.extent_m + strait_m for other in placed):
                placed.append(_place(spec, x, z))
                break
        else:
            raise LayoutRefused(
                "island %d (reach %.1f km) found no water %.1f km clear of the %d landmasses "
                "already placed" % (island, reach / 1000.0, strait_m / 1000.0, len(placed)))
    placed.sort(key=lambda item: item.slot)
    return tuple(placed)


def _check_separation(placed, low, high, strait_m):
    """Assert the geometric contract on the skeleton itself."""
    for index, spec in enumerate(placed):
        if (spec.centre_x_m - spec.extent_m < low - 1e-9 or spec.centre_x_m + spec.extent_m > high + 1e-9
                or spec.centre_z_m - spec.extent_m < low - 1e-9
                or spec.centre_z_m + spec.extent_m > high + 1e-9):
            raise LayoutRefused("landmass %d crosses the border band" % spec.slot)
        for other in placed[index + 1:]:
            gap = math.hypot(spec.centre_x_m - other.centre_x_m, spec.centre_z_m - other.centre_z_m)
            if gap < spec.extent_m + other.extent_m + strait_m - 1e-9:
                raise LayoutRefused(
                    "landmasses %d and %d are %.1f km apart, under the declared %.1f km strait plus "
                    "their %.1f + %.1f km reaches"
                    % (spec.slot, other.slot, gap / 1000.0, strait_m / 1000.0,
                       spec.extent_m / 1000.0, other.extent_m / 1000.0))
    return True


# ---------------------------------------------------------------------------
# Rasterisation and the final component audit
# ---------------------------------------------------------------------------
def _grid_axes(request):
    spacing = request.spacing_m
    return (np.arange(int(request.grid_size), dtype=np.float64) + 0.5) * spacing


def _window(request, reach_m, centre_x_m, centre_z_m):
    spacing = request.spacing_m
    size = int(request.grid_size)
    j0 = max(0, int(math.floor((centre_x_m - reach_m) / spacing)) - 1)
    j1 = min(size, int(math.ceil((centre_x_m + reach_m) / spacing)) + 2)
    i0 = max(0, int(math.floor((centre_z_m - reach_m) / spacing)) - 1)
    i1 = min(size, int(math.ceil((centre_z_m + reach_m) / spacing)) + 2)
    return i0, i1, j0, j1


def _rasterise(request, specs):
    """Rasterise the skeleton into a landmass index; nothing may touch the border."""
    axis = _grid_axes(request)
    size = int(request.grid_size)
    landmass_index = np.full((size, size), -1, dtype=np.int16)
    for spec in specs:
        i0, i1, j0, j1 = _window(request, spec.extent_m, spec.centre_x_m, spec.centre_z_m)
        if i0 >= i1 or j0 >= j1:
            continue
        inside = spec.contains(axis[j0:j1][None, :], axis[i0:i1][:, None])
        window = landmass_index[i0:i1, j0:j1]
        if spec.is_continent:
            window[inside] = spec.slot
        else:
            window[inside & (window < 0)] = spec.slot
    band = request.border_band_cells
    border = np.zeros((size, size), dtype=bool)
    border[:band, :] = True
    border[-band:, :] = True
    border[:, :band] = True
    border[:, -band:] = True
    return landmass_index, border


def _components(land_mask):
    """8-connected components of the land mask, largest first.

    8-connectivity is the conservative choice: two islands touching only at a corner
    are reported as one component, which can only make the "exactly three
    continents" gate harder to pass, never easier.
    """
    labels, count = ndimage.label(land_mask, structure=_EIGHT)
    sizes = (np.asarray(ndimage.sum(land_mask, labels, index=np.arange(1, count + 1)),
                        dtype=np.float64) if count else np.zeros(0))
    order = np.argsort(-sizes, kind="stable")
    remap = np.zeros(count + 1, dtype=np.int32)
    for rank, position in enumerate(order):
        remap[int(position) + 1] = rank
    component_id = remap[labels]
    component_id[~land_mask] = -1
    return component_id, sizes[order]


def _audit_components(request, specs, landmass_index, land_mask, component_id, sizes):
    """The separation contract, checked on the final mask rather than the skeleton."""
    areas = sizes * request.cell_area_km2
    gate = request.continent_gate_km2
    if areas.size != len(specs):
        raise LayoutRefused("%d connected components for %d intended landmasses"
                            % (areas.size, len(specs)))
    above = int(np.sum(areas >= gate))
    if above != CONTINENT_COUNT:
        raise LayoutRefused(
            "%d components exceed the %.1f km2 continent gate (need exactly %d)"
            % (above, gate, CONTINENT_COUNT))
    islands = int(areas.size - above)
    if not ISLAND_COUNT_RANGE[0] <= islands <= ISLAND_COUNT_RANGE[1]:
        raise LayoutRefused("%d islands fall outside the declared range %s"
                            % (islands, list(ISLAND_COUNT_RANGE)))
    pairs = set()
    flat_component = component_id.ravel()
    flat_landmass = landmass_index.ravel()
    for cell in np.flatnonzero(land_mask.ravel()):
        pairs.add((int(flat_component[cell]), int(flat_landmass[cell])))
    if len(pairs) != len(specs):
        raise LayoutRefused(
            "%d (component, landmass) pairs for %d intended landmasses: an accidental land "
            "bridge or a detached lobe" % (len(pairs), len(specs)))
    return areas, pairs


# ---------------------------------------------------------------------------
# Elevation
# ---------------------------------------------------------------------------
def _texture_scales(extent_m):
    return ((0.115 * extent_m, 1.00), (0.052 * extent_m, 0.60),
            (0.021 * extent_m, 0.30), (0.0086 * extent_m, 0.15))


def _uplift_scales(extent_m):
    return ((0.240 * extent_m, 1.00), (0.098 * extent_m, 0.55), (0.041 * extent_m, 0.25))


def _ridge_modulation_scales(extent_m):
    return ((0.070 * extent_m, 1.00), (0.029 * extent_m, 0.45))


def _elevation(request, land_mask, ledger):
    """Signed elevation from the land mask alone, so the sea-level sign cannot drift."""
    spacing = request.spacing_m
    extent_m = request.extent_m
    axis = _grid_axes(request)
    x, z = np.meshgrid(axis, axis)

    seed_terrain = ledger["terrain_texture", 0] = derive_subseed(request.seed, "terrain_texture")
    seed_uplift = ledger["terrain_uplift", 0] = derive_subseed(request.seed, "terrain_uplift")

    distance_in = ndimage.distance_transform_edt(land_mask, sampling=spacing)
    distance_out = ndimage.distance_transform_edt(~land_mask, sampling=spacing)
    texture = absolute_noise_field(x, z, seed_terrain, 0, _texture_scales(extent_m))
    uplift = absolute_noise_field(x, z, seed_uplift, 0, _uplift_scales(extent_m))

    land_ramp = 1.0 - np.exp(-distance_in / (LAND_RAMP_FRACTION * extent_m))
    inland = np.clip(distance_in / (INLAND_RAMP_FRACTION * extent_m), 0.0, 1.0)
    sea_ramp = 1.0 - np.exp(-distance_out / (SEA_RAMP_FRACTION * extent_m))

    land_height = LAND_RELIEF_M * land_ramp * (1.0 + 0.40 * texture)
    land_height = land_height + 0.45 * LAND_RELIEF_M * inland * uplift
    sea_height = -OCEAN_BASE_DEPTH_M * sea_ramp * (0.80 + 0.35 * texture)

    elevation = np.where(land_mask, land_height, sea_height)
    elevation = np.where(land_mask, np.maximum(elevation, MIN_LAND_M),
                         np.minimum(elevation, -MIN_OCEAN_M))
    return elevation, inland


def _draw_ridge(rng, centre, span_m, angle, count=6, wobble=0.16):
    direction = np.array([math.cos(angle), math.sin(angle)])
    perpendicular = np.array([-direction[1], direction[0]])
    phase = float(rng.uniform(0.0, 2.0 * np.pi))
    bends = 1 + int(rng.integers(0, 2))
    points = []
    for step in range(count):
        t = -0.5 + step / float(count - 1)
        lateral = wobble * span_m * math.sin(math.pi * (t + 0.5) * bends + phase)
        point = centre + direction * (t * span_m) + perpendicular * lateral
        points.append((float(point[0]), float(point[1])))
    return tuple(points)


def _distance_to_polyline(points, x, z):
    best = np.full(np.shape(x), np.inf)
    for start, stop in zip(points[:-1], points[1:]):
        delta_x = stop[0] - start[0]
        delta_z = stop[1] - start[1]
        length2 = delta_x * delta_x + delta_z * delta_z
        if length2 <= 0.0:
            continue
        t = np.clip(((x - start[0]) * delta_x + (z - start[1]) * delta_z) / length2, 0.0, 1.0)
        best = np.minimum(best, np.hypot(x - (start[0] + t * delta_x),
                                        z - (start[1] + t * delta_z)))
    return best


def _mountain_belt(request, specs, inland, ledger):
    """Continuous ridge belts (polyline bands), not isolated white-noise peaks."""
    extent_m = request.extent_m
    axis = _grid_axes(request)
    size = int(request.grid_size)
    belt = np.zeros((size, size), dtype=np.float64)
    added = np.zeros_like(belt)
    ridge_records = []
    continents = [spec for spec in specs if spec.is_continent]
    for position, spec in enumerate(continents):
        i0, i1, j0, j1 = _window(request, spec.extent_m, spec.centre_x_m, spec.centre_z_m)
        if i0 >= i1 or j0 >= j1:
            continue
        local_x, local_z = np.meshgrid(axis[j0:j1], axis[i0:i1])
        inside = spec.contains(local_x, local_z)
        centre = np.array([spec.centre_x_m, spec.centre_z_m])
        seed_ridge = ledger["mountain_belt", position] = derive_subseed(
            request.seed, "mountain_belt", position)
        rng = np.random.default_rng(seed_ridge)
        angle = float(rng.uniform(0.0, np.pi))
        span = 1.15 * spec.extent_m
        ridges = [_Ridge(_draw_ridge(rng, centre, span, angle), MAIN_RIDGE_AMPLITUDE_M,
                         MAIN_RIDGE_WIDTH_FRACTION * extent_m, True)]
        for branch in range(2):
            branch_angle = angle + float(rng.uniform(0.6, 1.3)) * (1.0 if branch else -1.0)
            anchor = centre + np.array([math.cos(angle), math.sin(angle)]) * \
                float(rng.uniform(-0.25, 0.25)) * span
            ridges.append(_Ridge(_draw_ridge(rng, anchor, 0.62 * span, branch_angle, count=5),
                                 BRANCH_RIDGE_AMPLITUDE_M,
                                 BRANCH_RIDGE_WIDTH_FRACTION * extent_m, False))
        modulation = 0.55 + 0.45 * absolute_noise_field(local_x, local_z, seed_ridge, 91,
                                                       _ridge_modulation_scales(extent_m))
        modulation = np.clip(modulation, 0.10, 1.0)
        window_belt = np.zeros(np.shape(local_x), dtype=np.float64)
        window_added = np.zeros(np.shape(local_x), dtype=np.float64)
        for ridge in ridges:
            distance = _distance_to_polyline(ridge.points_m, local_x, local_z)
            shape = np.exp(-(distance / ridge.width_m) ** 2)
            window_belt = np.maximum(window_belt, shape)
            window_added = window_added + ridge.amplitude_m * shape * modulation
            ridge_records.append({
                "continent": position,
                "main": bool(ridge.is_main),
                "amplitude_m": float(ridge.amplitude_m),
                "width_km": float(ridge.width_m / 1000.0),
                "vertices_m": [[float(px), float(pz)] for px, pz in ridge.points_m],
            })
        window_added = window_added * inland[i0:i1, j0:j1] * inside
        slice_belt = belt[i0:i1, j0:j1]
        slice_added = added[i0:i1, j0:j1]
        slice_belt[inside] = np.maximum(slice_belt[inside], window_belt[inside])
        slice_added[inside] = np.minimum(MAX_MOUNTAIN_ADD_M,
                                         slice_added[inside] + window_added[inside])
    return belt, added, ridge_records


# ---------------------------------------------------------------------------
# Diagnostic drainage, its audit, and river selection
# ---------------------------------------------------------------------------
def _drainage(request, elevation, land_mask):
    """Priority-flood irregular graph routing with the ocean as the only explicit outlets.

    Reuses ``terrain_pipeline.surface_rivers.drainage.route`` -- a general offline
    diagnostic router with a documented acyclic receiver graph -- instead of
    writing a second router.  Unit runoff is imposed **on land nodes only**, so an
    ocean node never acts as a land runoff source and every contributing area is a
    sum of land cells.  This is not the TD river-network interface: the arrays
    never leave this module.
    """
    outlets = ~land_mask
    if not outlets.any():
        raise OverviewError("the frame contains no ocean; drainage needs at least one outlet")
    first_center_m = .5 * request.spacing_m
    routing = route(elevation, outlets, request.spacing_m, world_seed=int(request.seed),
                    origin_world_xz=(first_center_m, first_center_m))
    runoff = land_mask.astype(np.float64)
    accumulation = accumulate(routing, runoff, request.spacing_m)
    filled_depth = routing.routing_height - elevation
    return routing, accumulation, filled_depth


def _rank(routing):
    rank = np.empty(routing.receiver.size, dtype=np.int64)
    rank[routing.order] = np.arange(routing.receiver.size, dtype=np.int64)
    return rank


def _donors(cell, receiver, rank, rows, cols, donor_index=None):
    """Read all graph donors, including edges beyond the old raster stencil."""
    indptr, indices = reverse_donors(receiver) if donor_index is None else donor_index
    return [int(node) for node in indices[indptr[cell]:indptr[cell + 1]]
            if rank[node] > rank[cell]]


def _receiver_audit(land_mask, routing, world_seed=20261020):
    """Independent checks on the exported receiver graph itself."""
    cols = land_mask.shape[1]
    receiver = routing.receiver
    rank = _rank(routing)
    flat_land = land_mask.ravel()
    non_outlet = np.flatnonzero(receiver >= 0)

    land_outlets = int(np.sum((receiver < 0) & flat_land))
    ocean_outlets = int(np.sum((receiver < 0) & ~flat_land))
    ocean_nodes = int(np.sum(~flat_land))

    mesh = grid_mesh(land_mask.shape, dx_m=routing.spacing_blocks, world_seed=world_seed)
    adjacent_ok = receiver_edges_valid(receiver, mesh)
    rank_ok = bool(np.all(rank[receiver[non_outlet]] < rank[non_outlet]))

    # Acyclicity by explicit following: 0 = unseen, 1 = on the current walk, 2 = settled.
    state = np.zeros(receiver.size, dtype=np.int8)
    acyclic = True
    for start in range(receiver.size):
        if state[start]:
            continue
        walk = []
        cell = start
        while cell >= 0 and state[cell] == 0:
            state[cell] = 1
            walk.append(cell)
            cell = int(receiver[cell])
        if cell >= 0 and state[cell] == 1:
            acyclic = False
        for node in walk:
            state[node] = 2
        if not acyclic:
            break

    return {
        "nodes": int(receiver.size),
        "land_nodes": int(flat_land.sum()),
        "ocean_nodes": ocean_nodes,
        "receiver_entries": int(non_outlet.size),
        "land_outlet_nodes": land_outlets,
        "ocean_outlet_nodes": ocean_outlets,
        "every_ocean_node_is_an_outlet": bool(ocean_outlets == ocean_nodes),
        "no_land_node_acts_as_an_outlet": bool(land_outlets == 0),
        "receivers_are_graph_adjacent": adjacent_ok,
        "receivers_have_larger_rank": rank_ok,
        "receiver_graph_is_acyclic": bool(acyclic),
        "connectivity": "irregular graph (one receiver per native control-cell node)",
    }


def _upstream_census(seed_cells, receiver, rank, rows, cols, flat_land):
    """Land cells draining into ``seed_cells``, counted by explicit traversal.

    This deliberately does not call ``accumulate``: it is the independent second
    opinion that a contributing area is a count of land cells times cell area.
    """
    donor_index = reverse_donors(receiver)
    seen = set(int(cell) for cell in seed_cells)
    stack = list(seen)
    while stack:
        cell = stack.pop()
        for donor in _donors(cell, receiver, rank, rows, cols, donor_index):
            if donor not in seen:
                seen.add(donor)
                stack.append(donor)
    return sum(1 for cell in seen if flat_land[cell])


def _mouths(land_mask, component_id, receiver):
    flat_land = land_mask.ravel()
    flat_component = component_id.ravel()
    mouths = {}
    for cell in np.flatnonzero(flat_land):
        downstream = int(receiver[cell])
        if downstream >= 0 and not flat_land[downstream]:
            mouths.setdefault(int(flat_component[cell]), []).append(int(cell))
    return mouths


def _trace(seed, receiver, rank, flat_area, rows, cols):
    """Upstream mainstem from ``seed`` along the largest contributing donor.

    The path runs to a headwater (a node with no donor inside the frame) or to the
    node budget.  "Mainstem" here means the chain of the largest contributing donor at
    every step: the irregular graph stream of greatest contributing area, not a discharge-
    weighted hydraulic channel.
    """
    donor_index = reverse_donors(receiver)
    nodes = [int(seed)]
    current = int(seed)
    while len(nodes) < RIVER_MAX_NODES:
        donors = _donors(current, receiver, rank, rows, cols, donor_index)
        if not donors:
            break
        upstream = max(donors, key=lambda cell: (float(flat_area[cell]), -cell))
        nodes.append(int(upstream))
        current = int(upstream)
    nodes.reverse()
    return nodes


def _select_rivers(land_mask, component_id, routing, accumulation):
    """Pick a few mainstem paths per continent by a fixed, declared rule."""
    rows, cols = land_mask.shape
    receiver = routing.receiver
    rank = _rank(routing)
    flat_area = accumulation.discharge.ravel()
    mouths_by_component = _mouths(land_mask, component_id, receiver)

    rivers = []
    for continent in range(CONTINENT_COUNT):
        candidates = mouths_by_component.get(continent, [])
        if not candidates:
            raise LayoutRefused("continent %d has no coastal mouth cell" % continent)
        candidates.sort(key=lambda cell: (-float(flat_area[cell]), cell))
        largest = float(flat_area[candidates[0]])
        chosen = []
        for cell in candidates:
            if len(chosen) >= RIVER_MAX_PER_CONTINENT:
                break
            if float(flat_area[cell]) < RIVER_MIN_RELATIVE_AREA * largest:
                break
            nodes = _trace(cell, receiver, rank, flat_area, rows, cols)
            if len(nodes) < RIVER_MIN_NODES:
                continue
            chosen.append((cell, nodes))
        if not chosen:
            raise LayoutRefused(
                "continent %d offers no mainstem of at least %d nodes at the declared "
                "threshold" % (continent, RIVER_MIN_NODES))
        for order_index, (mouth, nodes) in enumerate(chosen):
            rivers.append({
                "continent": continent,
                "order_within_continent": order_index,
                "mouth_cell": int(mouth),
                "nodes": nodes,
            })
    return rivers


def _river_paths(request, rivers):
    """Concatenate the exported river nodes; lengths are kilometres."""
    cols = int(request.grid_size)
    spacing = request.spacing_m
    nodes = []
    offsets = [0]
    lengths = []
    mesh = grid_mesh((cols, cols), dx_m=spacing, world_seed=int(request.seed))
    for river in rivers:
        cells = river["nodes"]
        nodes.extend(cells)
        offsets.append(len(nodes))
        length_m = 0.0
        for first, second in zip(cells[:-1], cells[1:]):
            length_m += math.hypot(mesh.node_x_m[second] - mesh.node_x_m[first],
                                   mesh.node_z_m[second] - mesh.node_z_m[first])
        lengths.append(length_m / 1000.0)
    return (np.asarray(nodes, dtype=np.int64), np.asarray(offsets, dtype=np.int64),
            np.asarray(lengths, dtype=np.float64))


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OverviewResult:
    request: OverviewRequest
    arrays: dict
    report: dict

    def npz_payload(self):
        return dict(self.arrays)


def _attempt_overview(request, rng, ledger):
    """One complete generation attempt; raises ``LayoutRefused`` to try another."""
    specs = _draw_and_place(request, rng)
    landmass_index, border = _rasterise(request, specs)
    land_mask = (landmass_index >= 0) & ~border
    component_id, sizes = _components(land_mask)
    component_areas, pairs = _audit_components(request, specs, landmass_index, land_mask,
                                               component_id, sizes)

    elevation, inland = _elevation(request, land_mask, ledger)
    belt, mountain_add, ridge_records = _mountain_belt(request, specs, inland, ledger)
    elevation = elevation + mountain_add * land_mask
    elevation = np.where(land_mask, np.clip(elevation, MIN_LAND_M, MAX_ELEVATION_M),
                         np.minimum(elevation, -MIN_OCEAN_M))
    # Round-trip through the exported dtype first, so every downstream number and
    # every reported check describes the array a reader will actually load.
    elevation = elevation.astype(np.float32).astype(np.float64)
    mismatch = int(np.sum((elevation > SEA_LEVEL_M) != land_mask))
    if mismatch:
        raise OverviewError("%d nodes disagree between the land mask and the elevation sign"
                            % mismatch)

    routing, accumulation, filled_depth = _drainage(request, elevation, land_mask)
    receiver_checks = _receiver_audit(land_mask, routing, int(request.seed))
    if not receiver_checks["receiver_graph_is_acyclic"]:
        raise LayoutRefused("the exported receiver graph contains a cycle")
    rivers = _select_rivers(land_mask, component_id, routing, accumulation)
    river_nodes, river_offsets, river_lengths = _river_paths(request, rivers)

    continent_id = np.full(land_mask.shape, -1, dtype=np.int8)
    for component in range(CONTINENT_COUNT):
        continent_id[component_id == component] = component
    continent_id[component_id >= CONTINENT_COUNT] = -2

    river_id = np.full(land_mask.shape, -1, dtype=np.int16)
    flat_river = river_id.ravel()
    for index in range(len(rivers)):
        flat_river[river_nodes[river_offsets[index]:river_offsets[index + 1]]] = index

    arrays = {
        "elevation_m": elevation.astype(np.float32),
        "land_mask": land_mask,
        "continent_id": continent_id,
        "landmass_index": landmass_index,
        "component_id": component_id.astype(np.int16),
        "mountain_belt": belt.astype(np.float32),
        "mountain_height_m": (mountain_add * land_mask).astype(np.float32),
        "receiver_index": routing.receiver.astype(np.int64).reshape(land_mask.shape),
        "contributing_area_m2": np.where(land_mask, accumulation.discharge, 0.0).astype(np.float64),
        "routing_surface_m": routing.routing_height.astype(np.float32),
        "filled_depth_m": filled_depth.astype(np.float32),
        "river_id": river_id,
        "river_nodes": river_nodes,
        "river_offsets": river_offsets,
        "river_length_km": river_lengths,
        "x_km": _grid_axes(request) / 1000.0,
        "z_km": _grid_axes(request) / 1000.0,
    }
    extras = {
        "specs": specs,
        "ridge_records": ridge_records,
        "rivers": rivers,
        "component_areas": component_areas,
        "pairs": pairs,
        "routing": routing,
        "accumulation": accumulation,
        "receiver_checks": receiver_checks,
        "mismatch": mismatch,
    }
    return arrays, extras


def generate_overview(request):
    """Build one overview.  Deterministic; writes nothing; refuses impossible layouts."""
    if not isinstance(request, OverviewRequest):
        raise OverviewError("an OverviewRequest is required, got %r" % (type(request).__name__,))
    ledger = {}
    failures = []
    for attempt in range(LAYOUT_ATTEMPTS):
        seed = ledger["layout", attempt] = derive_subseed(request.seed, "layout", attempt)
        local_ledger = {}
        try:
            arrays, extras = _attempt_overview(request, np.random.default_rng(seed), local_ledger)
        except LayoutRefused as refusal:
            failures.append({"attempt": int(attempt), "reason": str(refusal)})
            continue
        ledger.update(local_ledger)
        report = _build_report(request, arrays, extras, ledger, failures)
        return OverviewResult(request, arrays, report)

    raise LayoutRefused(
        "no attempt in %d produced exactly %d continents above the %.1f km2 gate plus "
        "%d-%d non-touching islands with usable mainstems, all inside the border band"
        % (LAYOUT_ATTEMPTS, CONTINENT_COUNT, request.continent_gate_km2,
           ISLAND_COUNT_RANGE[0], ISLAND_COUNT_RANGE[1]), failures)


def _build_report(request, arrays, extras, ledger, failures):
    """Recompute every exported claim from the exported arrays and build the report."""
    specs = extras["specs"]
    ridge_records = extras["ridge_records"]
    rivers = extras["rivers"]
    component_area_km2 = extras["component_areas"]
    pairs = extras["pairs"]
    routing = extras["routing"]
    accumulation = extras["accumulation"]
    receiver_checks = extras["receiver_checks"]
    mismatch = extras["mismatch"]

    land_mask = arrays["land_mask"]
    elevation = arrays["elevation_m"].astype(np.float64)
    filled_depth = arrays["filled_depth_m"].astype(np.float64)
    component_id = arrays["component_id"]
    rows, cols = land_mask.shape
    cell_area_km2 = request.cell_area_km2
    cell_area_m2 = request.cell_area_m2
    band = request.border_band_cells
    flat_land = land_mask.ravel()
    flat_component = component_id.ravel()
    rank = _rank(routing)
    flat_area = arrays["contributing_area_m2"].ravel()

    # --- border ------------------------------------------------------------
    border_mask = np.zeros_like(land_mask, dtype=bool)
    border_mask[:band, :] = True
    border_mask[-band:, :] = True
    border_mask[:, :band] = True
    border_mask[:, -band:] = True
    border_land = int(np.sum(land_mask & border_mask))
    if border_land:
        raise OverviewError("%d land nodes inside the border band" % border_land)
    border_checks = {
        "border_band_cells": band,
        "border_band_width_km": band * request.spacing_m / 1000.0,
        "land_nodes_inside_border_band": border_land,
        "first_row_all_ocean": bool(not land_mask[0].any()),
        "last_row_all_ocean": bool(not land_mask[-1].any()),
        "first_column_all_ocean": bool(not land_mask[:, 0].any()),
        "last_column_all_ocean": bool(not land_mask[:, -1].any()),
        "border_is_all_ocean": border_land == 0,
    }

    # --- components ------------------------------------------------------------
    gate = request.continent_gate_km2
    components = []
    for index in range(int(component_id.max()) + 1):
        mask = component_id == index
        area = float(component_area_km2[index])
        ii, jj = np.nonzero(mask)
        components.append({
            "component": int(index),
            "area_km2": area,
            "frame_fraction": area / request.frame_area_km2,
            "is_continent": bool(area >= gate),
            "above_continent_gate": bool(area >= gate),
            "node_count": int(mask.sum()),
            "centroid_km": [float((jj.mean() + 0.5) * request.spacing_m / 1000.0),
                            float((ii.mean() + 0.5) * request.spacing_m / 1000.0)],
            "bbox_km": [float(jj.min() * request.spacing_m / 1000.0),
                        float(ii.min() * request.spacing_m / 1000.0),
                        float((jj.max() + 1) * request.spacing_m / 1000.0),
                        float((ii.max() + 1) * request.spacing_m / 1000.0)],
            "max_elevation_m": float(elevation[mask].max()),
            "mean_elevation_m": float(elevation[mask].mean()),
        })
    continents = [item for item in components if item["is_continent"]]
    islands = [item for item in components if not item["is_continent"]]

    # --- rivers ----------------------------------------------------------------
    river_records = []
    for index, river in enumerate(rivers):
        nodes = river["nodes"]
        mouth = int(river["mouth_cell"])
        downstream = int(routing.receiver[mouth])
        i, j = divmod(mouth, cols)
        hi, hj = divmod(nodes[0], cols)
        edge_distance = min(i, j, rows - 1 - i, cols - 1 - j)
        monotone = True
        for first, second in zip(nodes[:-1], nodes[1:]):
            if int(routing.receiver[first]) != int(second) or rank[second] >= rank[first]:
                monotone = False
                break
        census_cells = _upstream_census([mouth], routing.receiver, rank, rows, cols, flat_land)
        census_area_m2 = census_cells * cell_area_m2
        river_records.append({
            "river": int(index),
            "continent": int(river["continent"]),
            "order_within_continent": int(river["order_within_continent"]),
            "node_count": int(len(nodes)),
            "length_km": float(arrays["river_length_km"][index]),
            "head_cell_ij": [int(hi), int(hj)],
            "head_cell_km": [float((hj + 0.5) * request.spacing_m / 1000.0),
                             float((hi + 0.5) * request.spacing_m / 1000.0)],
            "mouth_cell_ij": [int(i), int(j)],
            "mouth_km": [float((j + 0.5) * request.spacing_m / 1000.0),
                         float((i + 0.5) * request.spacing_m / 1000.0)],
            "mouth_catchment_km2_accumulated": float(flat_area[mouth]) / 1.0e6,
            "mouth_catchment_km2_independent_census": census_area_m2 / 1.0e6,
            "mouth_catchment_agreement_m2": float(abs(flat_area[mouth] - census_area_m2)),
            "mouth_is_land": bool(flat_land[mouth]),
            "mouth_downstream_cell": downstream,
            "mouth_downstream_is_ocean": bool(downstream >= 0 and not flat_land[downstream]),
            "mouth_downstream_elevation_m": (float(elevation.ravel()[downstream])
                                             if downstream >= 0 else None),
            "mouth_cells_from_frame_edge": int(edge_distance),
            "mouth_owner_component": int(flat_component[mouth]),
            "all_nodes_are_land": bool(all(flat_land[cell] for cell in nodes)),
            "path_follows_receivers_monotonically": bool(monotone),
            "crosses_open_water": bool(any(not flat_land[cell] for cell in nodes)),
        })
    worst_agreement = max((record["mouth_catchment_agreement_m2"] for record in river_records),
                          default=0.0)
    tolerance = 1.0e-3 * cell_area_m2
    river_checks = {
        "count": len(river_records),
        "per_continent": {str(k): sum(1 for r in river_records if r["continent"] == k)
                          for k in range(CONTINENT_COUNT)},
        "every_continent_has_a_river": all(
            any(r["continent"] == k for r in river_records) for k in range(CONTINENT_COUNT)),
        "all_paths_follow_receivers_monotonically": all(
            r["path_follows_receivers_monotonically"] for r in river_records),
        "all_nodes_on_land": all(r["all_nodes_are_land"] for r in river_records),
        "no_path_crosses_open_water": not any(r["crosses_open_water"] for r in river_records),
        "all_mouths_are_land_and_drain_to_ocean": all(
            r["mouth_is_land"] and r["mouth_downstream_is_ocean"] for r in river_records),
        "all_mouths_owned_by_their_continent": all(
            r["mouth_owner_component"] == r["continent"] for r in river_records),
        "min_mouth_cells_from_frame_edge": min(
            (r["mouth_cells_from_frame_edge"] for r in river_records), default=0),
        "min_node_count": min((r["node_count"] for r in river_records), default=0),
        "min_length_km": min((r["length_km"] for r in river_records), default=0.0),
        "no_degenerate_path": all(r["node_count"] >= RIVER_MIN_NODES for r in river_records),
        "catchment_cross_check_max_abs_disagreement_m2": float(worst_agreement),
        "catchment_cross_check_tolerance_m2": float(tolerance),
        "catchment_cross_check_agrees": bool(worst_agreement <= tolerance),
        "catchment_semantics": "contributing area in m2 = (number of land cells draining into the "
                               "mouth, the mouth included) x cell area; ocean cells carry zero "
                               "runoff and are never counted; the mouth itself is charged once and "
                               "the ocean cell downstream of it is never charged",
        "rule": {
            "max_per_continent": RIVER_MAX_PER_CONTINENT,
            "relative_catchment_threshold": RIVER_MIN_RELATIVE_AREA,
            "max_nodes": RIVER_MAX_NODES,
            "min_nodes": RIVER_MIN_NODES,
            "selection": "per continent, order coastal mouths by contributing area; take the "
                         "largest, then further mouths worth at least %.0f%% of it, up to %d; trace "
                         "upstream from each chosen mouth along the largest contributing donor to a "
                         "headwater (no donor left) or the %d-node budget"
                         % (100.0 * RIVER_MIN_RELATIVE_AREA, RIVER_MAX_PER_CONTINENT, RIVER_MAX_NODES),
        },
    }

    # --- filling and drainage budget -------------------------------------------
    land_count = int(land_mask.sum())
    filled_land = filled_depth[land_mask]
    filled = filled_land > 1.0e-6
    filling = {
        "filled_land_nodes": int(filled.sum()),
        "filled_land_fraction": float(filled.sum() / max(1, land_count)),
        "max_filled_depth_m": float(filled_land.max()) if filled_land.size else 0.0,
        "mean_filled_depth_over_filled_nodes_m": (float(filled_land[filled].mean())
                                                  if filled.any() else 0.0),
        "routing_surface_minus_elevation": "filled depth of the priority-flood working surface, "
                                           "reported separately from the exported elevation; it "
                                           "is not lake storage",
        "runoff_input_total_km2": float(accumulation.input_total) / 1.0e6,
        "accumulated_at_outlets_km2": float(accumulation.outlet_total) / 1.0e6,
        "land_area_km2": land_count * cell_area_km2,
        "accumulation_residual_m2": float(accumulation.residual),
    }

    measured = {
        "elevation_min_m": float(elevation.min()),
        "elevation_max_m": float(elevation.max()),
        "land_min_m": float(elevation[land_mask].min()),
        "land_max_m": float(elevation[land_mask].max()),
        "ocean_max_m": float(elevation[~land_mask].max()),
        "ocean_min_m": float(elevation[~land_mask].min()),
        "land_percentiles_m": {
            "p50": float(np.percentile(elevation[land_mask], 50.0)),
            "p90": float(np.percentile(elevation[land_mask], 90.0)),
            "p99": float(np.percentile(elevation[land_mask], 99.0)),
        },
        "nodes_at_upper_clip": int(np.sum(elevation[land_mask] >= MAX_ELEVATION_M - 1.0e-3)),
        "nodes_at_land_floor": int(np.sum(elevation[land_mask] <= MIN_LAND_M + 1.0e-3)),
        "nodes_at_ocean_floor": int(np.sum(elevation[~land_mask] >= -MIN_OCEAN_M - 1.0e-3)),
        "clip_is_active": bool(np.any(elevation[land_mask] >= MAX_ELEVATION_M - 1.0e-3)),
        "design_budget": {
            "land_relief_m": LAND_RELIEF_M,
            "ocean_base_depth_m": OCEAN_BASE_DEPTH_M,
            "max_elevation_clip_m": MAX_ELEVATION_M,
            "max_mountain_add_m": MAX_MOUNTAIN_ADD_M,
            "note": "construction budgets only.  The measured figures above describe the exported "
                    "array; `nodes_at_upper_clip` / `clip_is_active` say whether the analytic "
                    "expression actually reached the clamp, so a clamped maximum is never presented "
                    "as a free-running one.  Nothing here claims a realistic terrestrial elevation "
                    "distribution.",
        },
    }

    land_area = land_count * cell_area_km2
    report = {
        "schema": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "capability": {
            "product": "finite fictional world overview / planning map",
            "terrain_diffusion_product": False,
            "native_30m": False,
            "hydraulic_or_sediment_model": False,
            "natural_outlet_certified": False,
            "stage_one_accepted": False,
            "may_be_fed_to_td_river_interfaces": False,
            "may_replace_default_30m_terrain": False,
            "elevation_source": "analytic: lobed landmass skeleton + distance transforms + "
                                "multi-octave absolute-coordinate value noise + ridged mountain belts",
            "river_meaning": "diagnostic irregular graph contributing-area paths on the exported elevation; not "
                             "discharge, not hydraulics, not a natural-outlet certificate",
            "ocean_definition": "declared analytic land mask with an elevation floor; the sea floor "
                                "is cosmetic",
        },
        "request": request.parameters(),
        "grid_contract": request.grid_contract(),
        "seeds": {
            "world_seed": int(request.seed),
            "derivation": "uint64 big-endian of sha256('%s|<world_seed>|<purpose>|<index>')[:8]"
                          % SEED_NAMESPACE,
            "namespace": SEED_NAMESPACE,
            "forbidden_sources": ["python builtin hash()", "wall-clock time", "system entropy",
                                  "load or evaluation order"],
            "values": {"%s[%d]" % (key[0], key[1]): int(value)
                       for key, value in sorted(ledger.items())},
        },
        "layout": {
            "continent_count": CONTINENT_COUNT,
            "island_count": int(len(specs) - CONTINENT_COUNT),
            "island_count_range": list(ISLAND_COUNT_RANGE),
            "min_strait_km": float(request.min_strait_km),
            "continent_area_gate_km2": float(gate),
            "continent_area_gate_fraction_of_frame": CONTINENT_MIN_AREA_FRACTION,
            "gate_declared_before_generation": True,
            "separation_rule": "centre distance >= extent_i + extent_j + min_strait, where extent is "
                               "the exact upper bound of the lobed outline; plus a border band kept "
                               "land free",
            "connected_component_connectivity": "8-connectivity (diagonal contact counts as connected)",
            "budget_attempts": LAYOUT_ATTEMPTS,
            "attempts_used": len(failures) + 1,
            "failed_attempts": failures,
            "skeleton_component_pairs": len(pairs),
            "landmasses": [{
                "slot": int(spec.slot),
                "is_continent": bool(spec.is_continent),
                "centre_km": [spec.centre_x_m / 1000.0, spec.centre_z_m / 1000.0],
                "extent_bound_km": spec.extent_m / 1000.0,
                "lobe_count": len(spec.lobes),
            } for spec in specs],
        },
        "checks": {
            "exactly_three_continents_above_gate": len(continents) == CONTINENT_COUNT,
            "island_count_within_range": bool(
                ISLAND_COUNT_RANGE[0] <= len(islands) <= ISLAND_COUNT_RANGE[1]),
            "skeleton_matches_final_components": len(pairs) == len(specs),
            "no_island_merged_into_a_continent": all(item["area_km2"] < gate for item in islands),
            "nodes_disagreeing_between_mask_and_elevation_sign": int(mismatch),
            "border": border_checks,
            "components": {
                "count": len(components),
                "continents": len(continents),
                "islands": len(islands),
                "connectivity": "8-connectivity on the exported land_mask",
            },
            "receiver_graph": receiver_checks,
            "rivers": river_checks,
            "filling": filling,
            "elevation": measured,
        },
        "results": {
            "land_area_km2": float(land_area),
            "land_fraction": float(land_area / request.frame_area_km2),
            "ocean_area_km2": float(request.frame_area_km2 - land_area),
            "island_count": len(islands),
            "island_area_total_km2": float(sum(item["area_km2"] for item in islands)),
            "largest_island_area_km2": float(max((item["area_km2"] for item in islands),
                                                 default=0.0)),
            "continent_areas_km2": [item["area_km2"] for item in continents],
            "continent_frame_fractions": [item["frame_fraction"] for item in continents],
            "components": components,
            "rivers": river_records,
            "river_paths": [{"river": index,
                             "continent": int(river["continent"]),
                             "nodes": [int(cell) for cell in river["nodes"]]}
                            for index, river in enumerate(rivers)],
            "mountain_cells_above_500m": int(np.sum((arrays["mountain_height_m"] > 500.0)
                                                    & land_mask)),
            "mountain_cells_above_1000m": int(np.sum((arrays["mountain_height_m"] > 1000.0)
                                                     & land_mask)),
            "ridges": ridge_records,
        },
        "configuration_surface": _configuration_surface(),
        "limitations": [
            "low-resolution overview grid (%.1f m node spacing for this request); it is not the "
            "30 m TD native grid and not a TD inference product" % request.spacing_m,
            "elevation is analytic (lobed skeleton + distance transforms + value noise + ridge "
            "belts); it models no tectonics, erosion, sediment, lithology or climate",
            "rivers are diagnostic irregular graph contributing-area paths on this grid; they are not routed "
            "hydraulics, carry no discharge, and do not certify a natural outlet",
            "depressions are filled by the routing working surface; the filled depth is reported "
            "and must not be read as lake hydrology or storage",
            "the land/ocean split is a declared analytic mask with an elevation floor, not a "
            "sea-level solve, and the sea floor is cosmetic",
            "a LayoutRefused result means the declared layout does not fit the frame under the "
            "declared strait and border constraints within the attempt budget; the gates are never "
            "relaxed and no seed is guaranteed to succeed",
            "no output of this module may substitute for the default 30 m TD terrain or be fed to "
            "the existing TD river-network interfaces",
        ],
        "arrays": {name: {"dtype": str(array.dtype), "shape": list(array.shape),
                          "sha256": array_hash(np.ascontiguousarray(array))}
                   for name, array in sorted(arrays.items())},
    }
    report["report_sha256"] = hashlib.sha256(canonical_json(report).encode("utf-8")).hexdigest()
    return report


# ---------------------------------------------------------------------------
# Declared configuration surface (V1 freeze)
# ---------------------------------------------------------------------------
def _configuration_surface():
    """Exactly what a caller can already change, and what is still hard-coded.

    This is the V1 freeze hand-over: the module's public request is
    :class:`OverviewRequest` and nothing else.  Everything under ``hard_coded`` is
    a declared construction constant, not a knob; changing one changes the
    algorithm identity (:data:`ALGORITHM`) and needs its own review, because the
    topological guarantees are sized against these numbers.
    """
    return {
        "already_parameterised": {
            "seed": {"range": "0 .. 2**64-1",
                     "effect": "a fresh layout, noise phases and ridge geometry; changes every "
                               "array"},
            "extent_km": {"range": [MIN_EXTENT_KM, MAX_EXTENT_KM],
                          "effect": "frame side; resets node spacing and every metre-scaled "
                                    "wavelength, and the area gate follows the frame area"},
            "grid_size": {"range": [MIN_GRID_SIZE, MAX_GRID_SIZE],
                          "effect": "cell-centre samples per side; changes node spacing and hence "
                                    "how many cells a landmass occupies"},
            "min_strait_km": {"range": "> 0",
                              "effect": "minimum open water between landmasses; too large for the "
                                        "frame is a refusal, never a silent relaxation"},
        },
        "hard_coded": {
            "layout": {"continents": CONTINENT_COUNT,
                       "island_count_range": list(ISLAND_COUNT_RANGE),
                       "continent_area_gate_fraction": CONTINENT_MIN_AREA_FRACTION,
                       "border_band_fraction": BORDER_BAND_FRACTION,
                       "min_border_band_cells": MIN_BORDER_BAND_CELLS,
                       "attempts": LAYOUT_ATTEMPTS,
                       "placement_tries": PLACEMENT_TRIES},
            "landmass_shape": {"continent_base_fraction": [0.095, 0.135],
                               "continent_aspect": [0.62, 1.00],
                               "continent_lobe_count": [3, 5],
                               "island_base_fraction": [0.013, 0.032],
                               "angular_harmonic_amplitude_cap": 0.22},
            "elevation": {"land_relief_m": LAND_RELIEF_M,
                          "ocean_base_depth_m": OCEAN_BASE_DEPTH_M,
                          "land_ramp_fraction": LAND_RAMP_FRACTION,
                          "sea_ramp_fraction": SEA_RAMP_FRACTION,
                          "inland_ramp_fraction": INLAND_RAMP_FRACTION,
                          "max_elevation_clip_m": MAX_ELEVATION_M,
                          "min_land_m": MIN_LAND_M,
                          "min_ocean_m": MIN_OCEAN_M},
            "mountains": {"main_amplitude_m": MAIN_RIDGE_AMPLITUDE_M,
                          "branch_amplitude_m": BRANCH_RIDGE_AMPLITUDE_M,
                          "main_width_fraction": MAIN_RIDGE_WIDTH_FRACTION,
                          "branch_width_fraction": BRANCH_RIDGE_WIDTH_FRACTION,
                          "branches_per_continent": 2,
                          "max_added_m": MAX_MOUNTAIN_ADD_M},
            "rivers": {"max_per_continent": RIVER_MAX_PER_CONTINENT,
                       "relative_catchment_threshold": RIVER_MIN_RELATIVE_AREA,
                       "min_nodes": RIVER_MIN_NODES,
                       "max_nodes": RIVER_MAX_NODES},
        },
        "safe_to_expose_later": [
            {"name": "seed",
             "constraint": "integer < 2**64; every seed may legitimately refuse"},
            {"name": "extent_km",
             "constraint": "[%.0f, %.0f]; the area gate and all metre-scaled wavelengths rescale "
                           "with it" % (MIN_EXTENT_KM, MAX_EXTENT_KM)},
            {"name": "grid_size",
             "constraint": "[%d, %d]; below roughly %d cells a 38 400 km2 continent is too few "
                           "cells wide to keep a valid mainstem"
                           % (MIN_GRID_SIZE, MAX_GRID_SIZE, MIN_GRID_SIZE)},
            {"name": "min_strait_km",
             "constraint": "must stay below (frame diagonal - largest continent reach); a request "
                           "that cannot fit is refused"},
            {"name": "island_count_range",
             "constraint": "upper bound must keep strait placement feasible inside the border band"},
            {"name": "continent_area_gate_fraction",
             "constraint": "must sit strictly between the largest island and the smallest continent "
                           "this request produces"},
            {"name": "river_max_per_continent",
             "constraint": "raising it or lowering the catchment threshold can exhaust the "
                           "candidate mouths and trigger a refusal; it can never invent a river"},
        ],
        "unsafe_without_new_validation": [
            "raising CONTINENT_COUNT without resizing the triangle: the required circumradius grows "
            "with the number of pairs and requests start refusing",
            "shrinking BORDER_BAND_FRACTION to zero: the ocean border stops being geometric",
            "lowering MIN_STRAIT_KM below one node spacing: rasterised landmasses could touch at a "
            "corner and merge into one component, breaking the three-continent gate",
            "scaling ridge amplitude or width past MAX_MOUNTAIN_ADD_M / the continent reach: the "
            "ridge band would leave its own landmass",
        ],
        "rule": "a configuration change that breaks the component, border, strait, receiver or "
                "catchment checks is a refusal, never a success; whatever attempt list led there "
                "is reported",
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_overview(result, path):
    """Full-map PNG: hypsometric terrain with mountains and rivers, plus the audit."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap

    from terrain_pipeline import terrain_map_style as style

    request = result.request
    arrays = result.arrays
    land_mask = arrays["land_mask"]
    elevation = arrays["elevation_m"].astype(np.float64)
    extent_km = float(request.extent_km)
    spacing = request.spacing_m

    rgb = style.banded_relief_rgb(elevation, spacing, ocean_mask=~land_mask,
                                  ocean_depth=np.maximum(-elevation, 0.0))
    figure = plt.figure(figsize=(14.0, 7.8), constrained_layout=True)
    axis = figure.add_subplot(121)
    axis.imshow(rgb, extent=(0.0, extent_km, extent_km, 0.0), interpolation="nearest")

    belt = arrays["mountain_belt"].astype(np.float64)
    visible = np.where(belt > MOUNTAIN_OVERLAY_THRESHOLD, belt, np.nan)
    axis.imshow(visible, extent=(0.0, extent_km, extent_km, 0.0), cmap="copper",
                alpha=np.where(np.isnan(visible), 0.0, 0.45), interpolation="nearest")

    nodes = arrays["river_nodes"]
    offsets = arrays["river_offsets"]
    cols = int(request.grid_size)
    for index in range(len(offsets) - 1):
        cells = nodes[offsets[index]:offsets[index + 1]]
        if cells.size < 2:
            continue
        ii, jj = np.divmod(cells, cols)
        river_x = (jj + 0.5) * spacing / 1000.0
        river_z = (ii + 0.5) * spacing / 1000.0
        axis.plot(river_x, river_z, color="#ffffff", linewidth=3.2,
                  solid_capstyle="round", zorder=11)
        axis.plot(river_x, river_z, color="#06365e", linewidth=1.5,
                  solid_capstyle="round", zorder=12)
        axis.plot(river_x[-1], river_z[-1], marker="o", markersize=3.4, color="#06365e",
                  markeredgecolor="#ffffff", markeredgewidth=0.5, zorder=13)

    axis.set_xlim(0.0, extent_km)
    axis.set_ylim(extent_km, 0.0)
    axis.set_aspect("equal")
    axis.set_xlabel("x (km, east)")
    axis.set_ylabel("z (km, south)")
    style.draw_scale_bar(axis, style.nice_scale_length_km(extent_km))
    style.draw_north_arrow(axis)
    style.draw_metre_graticule(axis, step_km=style.nice_graticule_step_km(extent_km))
    islands = result.report["results"]["island_count"]
    axis.set_title("Fictional world overview: %.0f km frame, %.1f m nodes (seed %d)\n"
                   "three continents + %d islands; mountain belts and %d diagnostic mainstems"
                   % (extent_km, spacing, request.seed, islands,
                      len(result.report["results"]["rivers"])), fontsize=10)

    partition = figure.add_subplot(122)
    component_id = arrays["component_id"].astype(np.int64)
    palette = ["#8c6d46", "#a8703f", "#7c8f4e", "#6f8fa8", "#9a7fa8", "#a8a06f",
               "#5f8f77", "#a88c6f", "#7f7fa8", "#8fa86f"]
    colors = palette + ["#dceae9"]
    shown = np.where(component_id >= 0, component_id % len(palette), len(palette))
    partition.imshow(shown, extent=(0.0, extent_km, extent_km, 0.0), interpolation="nearest",
                     cmap=ListedColormap(colors),
                     norm=BoundaryNorm(np.arange(-0.5, len(colors) + 0.5), len(colors)))
    partition.set_xlim(0.0, extent_km)
    partition.set_ylim(extent_km, 0.0)
    partition.set_aspect("equal")
    partition.set_xlabel("x (km, east)")
    partition.set_ylabel("z (km, south)")
    for record in result.report["results"]["components"]:
        if not record["is_continent"]:
            continue
        partition.annotate("continent %d\n%.0f km2 (%.1f%%)"
                           % (record["component"], record["area_km2"],
                              100.0 * record["frame_fraction"]),
                           xy=(record["centroid_km"][0], record["centroid_km"][1]),
                           ha="center", va="center", fontsize=8, color="#ffffff")
    partition.set_title("8-connected components of the exported land_mask\n"
                        "%d continents above a %.0f km2 gate, %d islands"
                        % (CONTINENT_COUNT, request.continent_gate_km2, islands), fontsize=10)
    figure.suptitle("Low-resolution planning overview -- not a Terrain Diffusion product, not 30 m; "
                    "rivers are diagnostic irregular graph contributing-area paths", fontsize=8.5)

    path = Path(path)
    if path.exists():
        raise OutputExistsError("%s already exists; overview images are never overwritten" % path)
    with open(path, "xb") as stream:
        figure.savefig(stream, format="png", dpi=150)
    plt.close(figure)
    return path


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def source_hashes():
    """SHA-256 of the module and its CLI, so a report can name its own code."""
    hashes = {}
    for path in (Path(__file__).resolve(),
                 Path(__file__).resolve().parents[1] / "tools"
                 / "generate_fictional_world_overview.py"):
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    return hashes


def write_overview(result, output_dir, *, render=True):
    """Write ``overview.npz``, ``overview-report.json`` and ``overview.png``.

    The destination directory must not exist yet and every file is opened with an
    exclusive ``xb`` handle, so an existing overview is never silently replaced by
    a failed or partial run.  ``report_sha256`` in the written JSON is recomputed
    after the source hashes are attached, so it covers the whole written body.
    """
    if not isinstance(result, OverviewResult):
        raise OverviewError("an OverviewResult is required")
    destination = Path(output_dir)
    if destination.exists():
        raise OutputExistsError("output directory %s already exists; refuse to overwrite"
                                % destination)
    destination.mkdir(parents=True, exist_ok=False)

    report = dict(result.report)
    report["sources"] = source_hashes()
    report.pop("report_sha256", None)
    report["report_sha256"] = hashlib.sha256(canonical_json(report).encode("utf-8")).hexdigest()

    written = {}
    npz_path = destination / "overview.npz"
    with open(npz_path, "xb") as stream:
        np.savez_compressed(stream, **result.npz_payload())
    written[npz_path.name] = hashlib.sha256(npz_path.read_bytes()).hexdigest()

    report_path = destination / "overview-report.json"
    with open(report_path, "xb") as stream:
        stream.write((canonical_json(report) + "\n").encode("utf-8"))
    written[report_path.name] = hashlib.sha256(report_path.read_bytes()).hexdigest()

    if render:
        png_path = render_overview(result, destination / "overview.png")
        written[png_path.name] = hashlib.sha256(png_path.read_bytes()).hexdigest()
    return {"output_dir": str(destination), "files": written, "report": report}
