"""Select the 40 km @30 m bounded-acceptance area on the fixed seed, by declared rule.

Why this exists
---------------
The spec (`.scratch/river-infinite-world/fine-terrain-40km-spec.md` §4) forbids
"pick a nice-looking spot": the world is deterministic in `(world_seed, x, z)`, so
which area is accepted must be deterministic too. This tool implements the declared
rule and nothing else:

1. scan one declared scan page of the fixed seed's real TD terrain for closed
   depressions (`depression_hierarchy` + `depression_component`);
2. keep only candidates whose basin does **not** touch the window border and whose
   measurement **converges** on at least three window sizes
   (`sampled_window_basin`, tolerance 1e-3 relative, unchanged);
3. keep only candidates that fit inside a 1337-node window with a declared margin;
4. rank by **largest basin area**, ties broken by the lexicographically smallest
   native origin -- both stated before any result was seen;
5. reverse the 1337 window origin so the basin is centred in it.

Scan domain and measurement support are two different things
------------------------------------------------------------
The **scan domain** -- which candidates exist, and therefore the ranking -- is
exactly one declared saved page (`--page`). Extra terrain on disk must not change
which area wins, or the "declared rule" would depend on what happened to be
generated.

The **convergence gate** is different: it measures a candidate in 513/1025/1537-node
windows centred on the basin, and for a basin near the scan page's rim the largest of
those leaves that page. That is a coverage question, not a reason to prefer a small
basin that happens to sit mid-page. That exact failure happened: 23 basins of 43.4 /
26.3 / 14.1 / 9.6 / 8.8 ... km2 were all refused with "the 1537-cell window needed for
the convergence gate leaves the 2049x2049 scanned page", and a 1.68 km2 basin in the
page centre was accepted instead. `--support-page` therefore accepts further saved TD
pages, and `PageMosaic` serves any window from **absolute native coordinates**,
assembling it from whichever pages cover it.

Why assembling from several pages is the same source, and when it is refused
---------------------------------------------------------------------------
Terrain Diffusion is a pure function of `(seed, absolute coordinates)`. Measured on
this workstation with `world_seed=20261020`: a 1537-node window generated at native
origin (42082, 42660) agrees with the archived 2049-node page at (42309, 41976)
**bitwise** over their whole 1365x1310 overlap (`max |delta| = 0.0`); the two
archived 2049-node pages agree to 0.031 m of 6-decimal noise on a terrain whose
standard deviation is 490 m. A window assembled from pages of the same source is
therefore the same terrain, not a blend. So `PageMosaic` never averages and never
resamples: values are copied by integer index arithmetic, and where two pages overlap
they must agree **exactly** -- one differing cell raises `SourceDisagreement` rather
than quietly mixing two sources.

What is deliberately *not* used to fill a gap: the analytic 30 m field
(`metric_fine_terrain.analytic_fine_field`, `diffusion.geography_physical
.sample_physical`). Its 30 m base is the conditioning field with TD contributing only
a high-frequency band (spec §1), so it is a different terrain; filling a TD window
from it would mix two definitions of "the terrain".

Refusals are results
--------------------
Every refusal carries a stable `reason_code` in exactly one of four declared
categories (`REASON_LABELS`), and the report counts them by category. If one
category takes every large candidate, that means a criterion is wrong, not that the
terrain has no large closed basin, and the report says so. If the convergence windows
are simply not covered by the pages at hand, the tool writes the exact absolute
rectangles it needs plus the 1337-node tiles that would cover them and reports
`status="needs_more_td_coverage"`; it never relaxes a tolerance, never clips a window,
never wraps around a page edge and never substitutes a non-closed basin.

Run (CPU only, no GPU):
    runtime/venv/Scripts/python.exe -B tools/scan_40km_area.py \
        --output .scratch/fine-terrain-40km/selection-v8 \
        --support-page .scratch/fine-terrain-40km/td-pages/*.npz
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.lake import CONVERGENCE_AREA_TOLERANCE as CONVERGENCE_AREA_TOLERANCE
from terrain_pipeline.lake import CONVERGENCE_LEVEL_TOLERANCE as CONVERGENCE_LEVEL_TOLERANCE
from terrain_pipeline.lake import depression_hierarchy as depression_hierarchy
from terrain_pipeline.lake import sampled_window_basin as sampled_window_basin

WORLD_SEED = 20261020
SPACING_M = 30.0
WINDOW_NODES = 1337                 # 1336 intervals = 40.08 km, per the spec
MARGIN_CELLS = 40                   # declared edge reserve so the basin is interior

# Declared before any scan output was inspected (spec §4.3).
RANKING_RULE = ("largest convergent closed-basin area first; ties broken by the "
                "lexicographically smallest native origin [row, column]")
CONVERGENCE_SIZES = (513, 1025, 1537)

# Refusal taxonomy (spec §4 step 5: a refusal is a result and carries a reason).
# Exactly one of these four goes on every refusal; the report counts them.
REASON_FOOTPRINT = "basin_exceeds_acceptance_window"
REASON_UNMEASURABLE = "convergence_window_outside_source"
REASON_NOT_CONVERGED = "not_converged"
REASON_TOUCHES_EDGE = "touches_measurement_window_edge"
REASON_LABELS = {
    REASON_FOOTPRINT: "the basin's own footprint cannot fit a 1337-node window "
                      "with the declared margin (盆地装不下验收窗口)",
    REASON_UNMEASURABLE: "the convergence window is not covered by any saved TD page "
                         "of the same source (无法复测收敛)",
    REASON_NOT_CONVERGED: "measured on every declared size but the two largest windows "
                          "still disagree beyond the declared tolerance (不收敛)",
    REASON_TOUCHES_EDGE: "the measured depression reaches the measurement window edge, "
                         "so its rim is outside the window and its spill level is not a "
                         "saddle (触边)",
}


# Terrain Diffusion is **window-size dependent on the outer rings** of each window it
# generates, and identical inside them. Measured on this workstation with
# `world_seed=20261020`, comparing at **absolute** native coordinates (four
# independent pairs, `pipeline.get` at each size):
#
#   pair                        overlap      differing cells   where they differ
#   w00 vs w01 (archived 2049)  2049x1024    2042 / 2098176    within 3 cells of a page
#                                                             edge; interior 0
#   w00 vs fresh 1537           1365x1310      0 / 1788150    identical, bitwise
#   w00 vs 1337 @(41631,41368)   729x659     5530 /  480411    within 4 cells; interior 0
#   w00 vs 1337 @(42731,42468)  1337x1337    2670 / 1787569    within 4 cells; interior 0
#
# So a value is reproducible only when the cell sits at least `SAFE_INSET_CELLS` from
# the border of the window that produced it; the outermost rings are an artifact of
# how much terrain the decoder could see, not a property of the coordinate. A window
# is therefore served from pages' **safe interiors only**. This is not a tolerance:
# a cell either comes from a region measured to be window-independent, or the window
# is refused -- no averaging, no clipping, no shrinking toward the page.
SAFE_INSET_CELLS = 4

# The one terrain family a window may be assembled from: Terrain Diffusion's own
# native 30 m elevation. Archived pages spell it in `artifact_kind` or not at all;
# `PhysicalTerrainDiffusionBackend.generate` spells it `terrain_diffusion_output`.
TD_NATIVE_FAMILY = "td-native"
TD_BACKEND_FAMILY = "terrain_diffusion_output"


class WindowNotCovered(ValueError):
    """No saved page has the requested window inside its window-independent interior."""


class SourceDisagreement(ValueError):
    """Two saved pages disagree on a shared cell: refusing to blend two sources."""


# --------------------------------------------------------------------------- #
# absolute-coordinate terrain access
# --------------------------------------------------------------------------- #
def load_page(path):
    """Read a saved TD window: elevation plus the native origin it was cut at.

    **Units.** `elevation_native[row, column]` is indexed from a *native grid index*
    pair, and the world position of one cell is

        x_metres = native_column * spacing_m
        z_metres = native_row    * spacing_m

    i.e. a **multiplication** of an index, never `origin + spacing * i` treating the
    index as a metre value. Getting this wrong is not a rounding error: it moves a
    window by `origin_native * (spacing - 1)` cells. The archived page's origin
    (42309, 41976) read as metres put every previous measurement ~1.4e6 cells away
    from the basin it claimed to describe, which is why `selection-v4/v6/v7/v8`
    reached wrong conclusions rather than merely wrong numbers. Both forms are kept
    on `NativePage` and asserted consistent below.
    """
    with np.load(Path(path), allow_pickle=False) as archive:
        elevation = np.asarray(archive["elevation_native"], np.float64)
        metadata = json.loads(str(archive["metadata_json"]))
    origin = (metadata.get("native_origin") or metadata.get("native_origin_xz")
              or metadata.get("origin_xz"))
    spacing = float(metadata.get("spacing_m", SPACING_M))
    if origin is None:
        raise ValueError("saved page must declare its native origin")
    declared_native = metadata.get("native_origin") or metadata.get("native_origin_xz")
    if declared_native is not None:
        column, row = (int(round(float(value))) for value in declared_native)
        origin_m = (float(declared_native[0]) * spacing, float(declared_native[1]) * spacing)
    else:
        column = int(round(float(origin[0]) / spacing))
        row = int(round(float(origin[1]) / spacing))
        origin_m = (float(origin[0]), float(origin[1]))
    if (abs(origin_m[0] - column * spacing) > 1e-6
            or abs(origin_m[1] - row * spacing) > 1e-6):
        raise ValueError("saved page origin is not on the native lattice")
    if elevation.ndim != 2 or not np.isfinite(elevation).all():
        raise ValueError("finite 2D native elevation required")
    # The unit contract, asserted rather than assumed: metres are `index * spacing`.
    if (origin_m[0] != column * spacing or origin_m[1] != row * spacing):
        raise ValueError(
            "native origin is not on the lattice: metres %s vs indices %s * %.6g m"
            % (origin_m, (column, row), spacing))
    if not (isinstance(column, int) and isinstance(row, int)):
        raise ValueError("native origin indices must be integers")
    return NativePage(elevation=elevation, origin_m=origin_m, spacing_m=spacing,
                      metadata=metadata, origin_native=(column, row))


@dataclass(frozen=True)
class NativePage:
    """One saved TD window, addressed by absolute native indices."""

    elevation: np.ndarray
    origin_m: tuple
    spacing_m: float
    metadata: dict
    origin_native: tuple

    @property
    def shape(self):
        return self.elevation.shape

    def source_key(self):
        """Identity of the terrain definition this page was cut from.

        Pages may only be combined when this matches: same seed, same lattice spacing,
        same artifact family. `world_seed` (archive-written pages) and `seed`
        (backend-written pages) are the same number in two spellings, and a backend
        window is the same TD-native elevation as an archived one, so both map to the
        one family `td-native`. Anything else -- an analytic 30 m field, a stitched
        source package -- keeps its own name and is refused.
        """
        seed = self.metadata.get("world_seed", self.metadata.get("seed"))
        if seed is None:
            raise ValueError("saved page must declare its world seed")
        declared = self.metadata.get("artifact_kind") or self.metadata.get("kind")
        family = TD_NATIVE_FAMILY if declared in (None, TD_NATIVE_FAMILY,
                                                 TD_BACKEND_FAMILY) else str(declared)
        return (int(seed), round(float(self.spacing_m), 6), family)


class PageMosaic:
    """Absolute-coordinate access to one or more saved pages of the same source.

    `block(column, row, rows, columns)` takes native indices counted from the world
    origin (not from any page) and returns that window exactly. Pages are combined by
    index arithmetic only; where they overlap they must agree bitwise.
    """

    def __init__(self, pages, *, label="mosaic", inset=SAFE_INSET_CELLS):
        pages = list(pages)
        if not pages:
            raise ValueError("at least one saved page required")
        if type(inset) is not int or inset < 0:
            raise ValueError("non-negative integer inset required")
        key = pages[0].source_key()
        spacing = pages[0].spacing_m
        for index, page in enumerate(pages):
            if abs(page.spacing_m - spacing) > 1e-9:
                raise SourceDisagreement(
                    "page %d has spacing %.6g m, page 0 has %.6g m; different lattices "
                    "cannot be combined" % (index, page.spacing_m, spacing))
            if page.source_key() != key:
                raise SourceDisagreement(
                    "page %d was cut from %s, page 0 from %s; different terrain sources "
                    "cannot be combined" % (index, page.source_key(), key))
            if min(page.shape) <= 2 * inset:
                raise ValueError("page %d is too small to have an interior with an inset "
                                 "of %d cells" % (index, inset))
        self.pages = pages
        self.label = label
        self.spacing_m = spacing
        self.source_key_value = key
        self.inset = inset

    def safe_extent(self, page):
        """Absolute native rectangle of a page's window-independent interior.

        Everything outside it was produced while the decoder could see less terrain
        than the cell really has, so it is not a property of the coordinate (see
        `SAFE_INSET_CELLS`). Those rings are excluded from every served window rather
        than used and hoped for.
        """
        page_column, page_row = page.origin_native
        page_rows, page_columns = page.shape
        return (page_column + self.inset, page_row + self.inset,
                page_rows - 2 * self.inset, page_columns - 2 * self.inset)

    def _intersections(self, column0, row0, rows, columns):
        for index, page in enumerate(self.pages):
            safe_column, safe_row, safe_rows, safe_columns = self.safe_extent(page)
            column_lo = max(column0, safe_column)
            column_hi = min(column0 + columns, safe_column + safe_columns)
            row_lo = max(row0, safe_row)
            row_hi = min(row0 + rows, safe_row + safe_rows)
            if column_lo >= column_hi or row_lo >= row_hi:
                continue
            target = (slice(row_lo - row0, row_hi - row0),
                      slice(column_lo - column0, column_hi - column0))
            # `source` indexes the page's own array, so it must be offset by the page
            # origin -- not by the safe interior's origin. Mixing the two shifts every
            # served value by `inset` cells, which a 0.0-difference assertion catches.
            page_column, page_row = page.origin_native
            source = (slice(row_lo - page_row, row_hi - page_row),
                      slice(column_lo - page_column, column_hi - page_column))
            yield index, page, target, source

    @staticmethod
    def _validate(column0, row0, rows, columns):
        for name, value in (("column", column0), ("row", row0),
                            ("rows", rows), ("columns", columns)):
            if type(value) is not int:
                raise ValueError("integer native %s required, got %s"
                                 % (name, type(value).__name__))
        if rows < 1 or columns < 1:
            raise ValueError("positive window shape required")

    def coverage(self, column0, row0, rows, columns):
        """Boolean mask of which cells of the window the saved pages can supply."""
        self._validate(column0, row0, rows, columns)
        filled = np.zeros((rows, columns), bool)
        for _, _, target, _ in self._intersections(column0, row0, rows, columns):
            filled[target] = True
        return filled

    def covers(self, column0, row0, rows, columns):
        return bool(self.coverage(column0, row0, rows, columns).all())

    def uncovered(self, column0, row0, rows, columns):
        """The parts of the window no page covers, as absolute native rectangles."""
        filled = self.coverage(column0, row0, rows, columns)
        if filled.all():
            return []
        missing_rows = np.flatnonzero(~filled.all(axis=1))
        missing_columns = np.flatnonzero(~filled.all(axis=0))
        return [{"native_column_range": [column0 + int(missing_columns.min()),
                                         column0 + int(missing_columns.max())],
                 "native_row_range": [row0 + int(missing_rows.min()),
                                      row0 + int(missing_rows.max())],
                 "missing_cells": int((~filled).sum()), "window_cells": int(filled.size)}]

    def block(self, column0, row0, rows, columns):
        """Assemble one window from absolute native coordinates; never clip, never wrap."""
        self._validate(column0, row0, rows, columns)
        out = np.empty((rows, columns), np.float64)
        filled = np.zeros((rows, columns), bool)
        used = []
        for index, page, target, source in self._intersections(column0, row0, rows, columns):
            region = out[target]
            region_filled = filled[target]
            values = page.elevation[source]
            if region_filled.any():
                difference = np.abs(region[region_filled] - values[region_filled])
                if difference.size and float(difference.max()) != 0.:
                    raise SourceDisagreement(
                        "pages disagree on %d of %d assembled cells (max |delta| %.6g m) "
                        "inside native window column %d..%d, row %d..%d; refusing to blend "
                        "two sources" % (int(difference.size), int(region.size),
                                         float(difference.max()), column0, column0 + columns - 1,
                                         row0, row0 + rows - 1))
            np.copyto(region, values, where=~region_filled)
            region_filled[...] = True
            if index not in used:
                used.append(index)
        if not filled.all():
            missing = self.uncovered(column0, row0, rows, columns)
            raise WindowNotCovered(
                "no saved page has the %dx%d native window at column %d, row %d inside "
                "its window-independent interior (%d-cell inset); uncovered: %s. A "
                "clipped window would invent a rim and the outermost rings of a page are "
                "window-size dependent, so the window is refused instead."
                % (rows, columns, column0, row0, self.inset, json.dumps(missing)))
        return out

    def sampler(self):
        """`sampled_window_basin` sampler: metres in, elevation out, no page offsets.

        `sampled_window_basin` places windows by absolute coordinates
        (`centre = round(lake_metres / spacing)`), so the conversion below is pure
        integer arithmetic on absolute indices. Deriving it from a page-relative
        offset instead is how the earlier version produced negative slice indices,
        which numpy silently wraps around to the far edge of the array.
        """
        spacing = self.spacing_m

        def sample(window_origin_m, shape):
            column = int(round(float(window_origin_m[0]) / spacing))
            row = int(round(float(window_origin_m[1]) / spacing))
            return self.block(column, row, int(shape[0]), int(shape[1]))

        return sample


# --------------------------------------------------------------------------- #
# candidate labelling on the scan page
# --------------------------------------------------------------------------- #
def candidate_basins(elevation, *, min_cells=64, spacing_m=SPACING_M):
    """Every 4-connected depression that does not touch the border, with its bed.

    How the depressions are labelled without a per-cell flood
    --------------------------------------------------------
    The obvious version -- loop over cells, call `depression_component` on each cell
    not yet `seen` -- floods a whole basin per depression. On a 2049 x 2049 page
    with 224 286 positive fill cells that is quadratic and did not finish inside the
    time budget (measured: `depression_hierarchy` alone already needs 45 s here).

    Depressions of a filled surface are the 4-connected components of
    `fill_depth > 0`, so they can be labelled with a bounded number of vectorised
    passes: start from a unique label per wet cell and iteratively adopt the smallest
    label among a cell's wet neighbours until no label changes. Each pass is pure
    numpy, and the number of passes is the label-propagation diameter, which is small
    for compact depressions.

    The answer is unchanged: a basin is still a connected component of positive fill
    depth, and the border test is the same inner-ring test used by
    `metric_lake_hypsometry._touches_border` (checked on the ring at `2:-2`, because
    border cells are flood seeds and can never carry fill depth).
    """
    filled, depth = depression_hierarchy(elevation)
    wet = depth > 0.
    rows, columns = elevation.shape
    if not wet.any():
        return []

    labels = np.where(wet, np.arange(wet.size, dtype=np.int64).reshape(wet.shape), np.int64(wet.size))
    big = np.int64(wet.size)
    passes = 0
    while True:
        passes += 1
        current = labels.copy()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            shifted = np.full_like(labels, big)
            source_rows = slice(max(0, dr), rows + min(0, dr))
            target_rows = slice(max(0, -dr), rows + min(0, -dr))
            source_columns = slice(max(0, dc), columns + min(0, dc))
            target_columns = slice(max(0, -dc), columns + min(0, -dc))
            shifted[target_rows, target_columns] = labels[source_rows, source_columns]
            # Only wet cells may take a label. Applying `np.minimum` everywhere let a
            # label flow through dry cells, so two bowls separated by plateau became
            # one component of 24000 cells while only 2514 cells were actually wet.
            np.minimum(current, shifted, out=current, where=wet)
        if np.array_equal(current, labels):
            break
        labels = current
        if passes > 4096:                      # a bound, not a tuning knob
            raise ValueError("label propagation did not settle in %d passes" % passes)
    labels = np.where(wet, labels, -1)

    inner = np.zeros((rows, columns), bool)
    inner[2:-2, 2:-2] = True
    flat_labels = labels.ravel()
    wet_cells = np.flatnonzero(wet.ravel())
    root_of_cell = flat_labels[wet_cells]
    order = np.argsort(root_of_cell, kind="stable")
    sorted_cells = wet_cells[order]
    sorted_roots = root_of_cell[order]
    boundaries = np.flatnonzero(np.diff(sorted_roots)) + 1
    groups = np.split(sorted_cells, boundaries)

    inner_flat = inner.ravel()
    elevation_flat = elevation.ravel()
    filled_flat = filled.ravel()
    cell_area = float(spacing_m) * float(spacing_m)
    found = []
    for cells in groups:
        if cells.size < min_cells:
            continue
        if not inner_flat[cells].all():
            continue          # rim outside the page: not a closed basin
        beds = elevation_flat[cells]
        bed = float(beds.min())
        spill = float(filled_flat[cells].max())
        if not spill > bed:
            continue
        index = int(cells[int(np.argmin(beds))])
        cell_rows = cells // columns
        cell_columns = cells % columns
        found.append(dict(mask=None, cells=int(cells.size), bed_m=bed, spill_m=spill,
                          relief_m=spill - bed,
                          centre_rc=(index // columns, index % columns),
                          extent_rc=(int(cell_rows.min()), int(cell_rows.max()),
                                     int(cell_columns.min()), int(cell_columns.max())),
                          area_m2=int(cells.size) * cell_area))
    return found


# --------------------------------------------------------------------------- #
# absolute-coordinate measurement
# --------------------------------------------------------------------------- #
def lake_position_m(centre_rc, page):
    """Absolute `(x, z)` metres of a candidate's bed cell."""
    spacing = page.spacing_m
    return (page.origin_m[0] + centre_rc[1] * spacing,
            page.origin_m[1] + centre_rc[0] * spacing)


def convergence_window(centre_rc, page, size):
    """Absolute native rectangle the gate will ask for, mirroring the module's own math.

    `sampled_window_basin` computes `centre = round(lake_metres / spacing)` then
    `origin = centre - size // 2`. Reproduced here exactly, so the coverage check
    below cannot drift from what is actually requested.
    """
    spacing = page.spacing_m
    lake_x, lake_z = lake_position_m(centre_rc, page)
    centre_column = int(round(lake_x / spacing))
    centre_row = int(round(lake_z / spacing))
    column = centre_column - int(size) // 2
    row = centre_row - int(size) // 2
    return (column, row, int(size), int(size))       # (column, row, columns, rows)


def basin_converges(centre_rc, page, mosaic, sizes=CONVERGENCE_SIZES):
    """Re-measure one basin in growing centred windows using the module's own gate.

    The window is served from **absolute** coordinates by `mosaic`, so a basin near
    the scan page's rim is measured on real terrain beyond that page instead of being
    refused. A window the saved pages cannot supply raises `WindowNotCovered`; it is
    never clipped or wrapped, because either would invent a rim.
    """
    return sampled_window_basin(lake_position_m(centre_rc, page), sizes,
                                page.spacing_m, mosaic.sampler())


def classify_measurement(convergence):
    """Which refusal category a non-converged measurement belongs to.

    A depression reaching the measurement window's edge has its rim outside the
    window, so its spill level is the window edge, not a saddle -- that is a coverage
    problem (`REASON_TOUCHES_EDGE`), not a tolerance problem. Only when every window
    is closed and the two largest still disagree is it `REASON_NOT_CONVERGED`.
    """
    records = convergence["records"]
    for record in records:
        if not record["closed_basin"] or record["touches_window_border"]:
            return REASON_TOUCHES_EDGE
    return REASON_NOT_CONVERGED


# --------------------------------------------------------------------------- #
# acceptance-window geometry (unchanged rule)
# --------------------------------------------------------------------------- #
def basin_fits_acceptance_window(basin, extent_rc, shape, window=WINDOW_NODES,
                                 margin=MARGIN_CELLS):
    """Can a `window`-node acceptance window contain this basin completely?

    The spec (§4.2) says the basin must fall **entirely inside** a 1337 window with a
    declared edge margin -- it does *not* require the basin to sit mid-page of the
    saved source page. An earlier version tested "is the centre 769 cells from the
    page edge", which is a different (and much stricter) statement: on the saved
    2049 page it rejected the 43.4, 26.3, 14.1 ... km2 basins purely because they are
    near the page border, and accepted a 1.68 km2 basin in the middle. The page is
    only the source used for scanning; the acceptance window is placed afterwards.

    `extent_rc` is `(row_min, row_max, column_min, column_max)` of the basin's own
    cells, so the check is on the basin's real footprint, not on a radius guess.
    """
    row_min, row_max, column_min, column_max = extent_rc
    basin_rows = row_max - row_min + 1
    basin_columns = column_max - column_min + 1
    usable = int(window) - 2 * int(margin)
    if basin_rows > usable or basin_columns > usable:
        return False                     # cannot fit even centred
    return True


def acceptance_window_origin_rc(extent_rc, window=WINDOW_NODES):
    """Place a `window`-node window so the basin sits centred inside it.

    Returns `(row, column)` of the window's corner in the same (scan page) index
    system as `extent_rc`. The caller converts to absolute coordinates, so the window
    is not restricted to the scanned page's interior.
    """
    row_min, row_max, column_min, column_max = extent_rc
    centre_row = (row_min + row_max) / 2.
    centre_column = (column_min + column_max) / 2.
    half = int(window) // 2
    return (int(round(centre_row)) - half, int(round(centre_column)) - half)


# --------------------------------------------------------------------------- #
# coverage planning: what to generate when the gate cannot be measured
# --------------------------------------------------------------------------- #
def plan_support_tiles(rects, *, tile_nodes=WINDOW_NODES, stride=None,
                      inset=SAFE_INSET_CELLS):
    """Grid of `tile_nodes` squares whose **safe interiors** cover every needed window.

    Only the union has to be covered: `PageMosaic` assembles one window from as many
    pages as it touches, and every tile is the same source, so overlapping tiles are
    redundant data rather than a seam.

    The check is on interiors, not on tile extents. A 1537-node convergence window can
    never fit inside one 1337-node tile (nor inside any tile at all once the inset is
    removed), which is precisely why several tiles are needed; planning on extents
    would report a plan that fails the moment it is followed.
    """
    rects = [tuple(int(value) for value in rect) for rect in rects]
    if not rects:
        return []
    tile = int(tile_nodes)
    step = int(stride) if stride else max(1, int(round(tile * 0.823)))   # 1100 for 1337
    if step < 1 or step > tile - 2 * int(inset):
        raise ValueError("stride must be in 1..%d so consecutive tile interiors overlap"
                         % (tile - 2 * int(inset),))
    column_lo = min(rect[0] for rect in rects)
    row_lo = min(rect[1] for rect in rects)
    column_hi = max(rect[0] + rect[2] for rect in rects) - 1
    row_hi = max(rect[1] + rect[3] for rect in rects) - 1
    # back off by the inset so the first tile's interior already reaches `column_lo`
    columns = list(range(column_lo - int(inset), column_hi + 1, step))
    rows = list(range(row_lo - int(inset), row_hi + 1, step))
    tiles = [{"native_origin": [column, row], "nodes": tile}
             for row in rows for column in columns]
    for rect in rects:
        if not tile_union_covers(tiles, rect, inset=inset):
            raise ValueError("planned tiles leave part of %s uncovered by any tile interior"
                             % (rect,))
    return tiles


def tile_union_covers(tiles, rect, inset=SAFE_INSET_CELLS):
    """Do the **safe interiors** of `tiles` contain the whole `rect` (integer math)?"""
    column0, row0, columns, rows = rect
    covered = np.zeros((rows, columns), bool)
    for tile in tiles:
        tile_column, tile_row = tile["native_origin"]
        nodes = int(tile["nodes"])
        column_lo = max(column0, tile_column + int(inset))
        column_hi = min(column0 + columns, tile_column + nodes - int(inset))
        row_lo = max(row0, tile_row + int(inset))
        row_hi = min(row0 + rows, tile_row + nodes - int(inset))
        if column_lo < column_hi and row_lo < row_hi:
            covered[row_lo - row0:row_hi - row0, column_lo - column0:column_hi - column0] = True
    return bool(covered.all())


# --------------------------------------------------------------------------- #
# selection
# --------------------------------------------------------------------------- #
def evaluate_candidates(basins, page, mosaic, *, limit, sizes=CONVERGENCE_SIZES):
    """Apply the declared rules in ranking order and classify every refusal.

    `sizes` is the convergence window family; production always passes the declared
    `CONVERGENCE_SIZES`, while the tests pass small windows so that an assembled
    window's geometry can be compared cell by cell against a directly measured one.
    """
    accepted, rejected = [], []
    plan_rects = []
    for basin in basins[:limit]:
        entry = dict(
            area_km2=basin["area_m2"] / 1e6, cells=basin["cells"],
            bed_m=basin["bed_m"], spill_m=basin["spill_m"], relief_m=basin["relief_m"],
            centre_rc=list(basin["centre_rc"]), extent_rc=list(basin["extent_rc"]),
            centre_xz_m=list(lake_position_m(basin["centre_rc"], page)))

        # Rule 1 (spec §4 step 2): the basin's own footprint must fit inside a 1337
        # window with the declared margin. This is about the basin, not about where
        # the basin happens to sit on the scanned page.
        if not basin_fits_acceptance_window(basin, basin["extent_rc"], page.shape):
            entry["reason_code"] = REASON_FOOTPRINT
            entry["reason"] = (
                "basin footprint %dx%d cells does not fit a %d-node window with a "
                "%d-cell margin (usable %d cells)" % (
                    basin["extent_rc"][1] - basin["extent_rc"][0] + 1,
                    basin["extent_rc"][3] - basin["extent_rc"][2] + 1,
                    WINDOW_NODES, MARGIN_CELLS, WINDOW_NODES - 2 * MARGIN_CELLS))
            rejected.append(entry)
            continue

        # Rule 2: the measurement must converge on three growing windows. Each window
        # is requested at absolute coordinates; whether the saved pages cover it is a
        # separate, reported fact rather than a silent preference for a small basin.
        largest = max(sizes)
        rect = convergence_window(basin["centre_rc"], page, largest)
        plan_rects.append(dict(native_column=rect[0], native_row=rect[1],
                               columns=rect[2], rows=rect[3],
                               area_km2=entry["area_km2"],
                               centre_rc=list(basin["centre_rc"])))
        if not mosaic.covers(*rect):
            entry["reason_code"] = REASON_UNMEASURABLE
            entry["needed_window"] = {"native_column_range": [rect[0], rect[0] + rect[2] - 1],
                                      "native_row_range": [rect[1], rect[1] + rect[3] - 1],
                                      "nodes": largest}
            entry["uncovered"] = mosaic.uncovered(*rect)
            entry["reason"] = (
                "cannot remeasure convergence: the %d-node window needed for the "
                "convergence gate at absolute native column %d, row %d is not covered by "
                "the %d saved page(s) of this source" % (largest, rect[0], rect[1],
                                                        len(mosaic.pages)))
            rejected.append(entry)
            continue
        try:
            convergence = basin_converges(basin["centre_rc"], page, mosaic, sizes=sizes)
        except (WindowNotCovered, SourceDisagreement) as error:
            entry["reason_code"] = REASON_UNMEASURABLE
            entry["reason"] = "convergence measurement refused: " + str(error)
            rejected.append(entry)
            continue
        entry["converged"] = bool(convergence["converged"])
        entry["convergence_records"] = [
            {key: record[key] for key in ("size", "window_km", "origin_xz_m", "closed_basin",
                                          "touches_window_border", "basin_cells",
                                          "basin_area_m2", "bed_min_m", "spill_level_m")}
            for record in convergence["records"]]
        entry["convergence_deltas"] = {
            key: convergence[key] for key in
            ("level_change_m", "level_relative", "area_change_m2", "area_relative")}
        if not convergence["converged"]:
            entry["reason_code"] = classify_measurement(convergence)
            entry["reason"] = (
                "%s: measured %s with spill %.3f -> %.3f m and area %.6g -> %.6g m2 "
                "between the two largest windows (tolerance level %.0e / area %.0e)" % (
                    REASON_LABELS[entry["reason_code"]],
                    [record["size"] for record in convergence["records"]],
                    convergence["records"][-2]["spill_level_m"],
                    convergence["records"][-1]["spill_level_m"],
                    convergence["records"][-2]["basin_area_m2"],
                    convergence["records"][-1]["basin_area_m2"],
                    CONVERGENCE_LEVEL_TOLERANCE, CONVERGENCE_AREA_TOLERANCE))
            rejected.append(entry)
            continue
        accepted.append(entry)
    return accepted, rejected, plan_rects


def count_reasons(rejected):
    counts = {code: 0 for code in REASON_LABELS}
    for entry in rejected:
        counts[entry["reason_code"]] = counts.get(entry["reason_code"], 0) + 1
    return counts


def report_accepted_area(accepted):
    """One-line description of the largest accepted basin, for the status message."""
    best = accepted[0]
    return "%.3f km2, bed %.2f m, spill %.2f m" % (
        best["area_km2"], best["bed_m"], best["spill_m"])


def dominant_reason_warning(rejected, counts, evaluated):
    """Flag the case the fix exists for: one category removing every large candidate.

    If the largest evaluated basin was refused and the same category accounts for
    every refusal of the top half, the criterion is suspect and the report has to say
    so instead of presenting a small accepted basin as the answer.
    """
    if not rejected:
        return None
    top_half = max(1, evaluated // 2)
    sample = rejected[:top_half]
    if len(sample) < 2:
        return None
    codes = {entry["reason_code"] for entry in sample}
    if len(codes) != 1:
        return None
    code = codes.pop()
    return ("the same category removed all of the %d largest evaluated basins: %s (%s). "
            "That means a criterion is refusing the terrain, not that the terrain has no "
            "large closed basin; do not present a smaller accepted basin as the answer."
            % (len(sample), code, REASON_LABELS[code]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--page", default=".scratch/fine-terrain-01/td-window-00.npz",
                        help="declared scan domain: the saved real TD page whose depressions "
                             "are the candidate set")
    parser.add_argument("--support-page", action="append", default=[],
                        help="further saved TD page of the same source, usable only to "
                             "serve convergence windows that leave the scan page "
                             "(repeatable)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-basin-cells", type=int, default=64)
    parser.add_argument("--evaluate", type=int, default=24,
                        help="how many of the largest candidates to measure (bounded work)")
    parser.add_argument("--tile-nodes", type=int, default=WINDOW_NODES,
                        help="tile side suggested in the coverage plan")
    parser.add_argument("--tile-stride", type=int, default=None,
                        help="tile stride in the coverage plan (default 0.823 * tile)")
    args = parser.parse_args(argv)

    scan_page = load_page(args.page)
    if abs(scan_page.spacing_m - SPACING_M) > 1e-9:
        raise SystemExit("scan page spacing %.6g m is not the declared %.6g m"
                         % (scan_page.spacing_m, SPACING_M))
    if scan_page.source_key()[0] != WORLD_SEED:
        raise SystemExit("scan page was cut from seed %d, not the declared world_seed %d"
                         % (scan_page.source_key()[0], WORLD_SEED))
    support = [load_page(path) for path in args.support_page]
    mosaic = PageMosaic([scan_page] + support, label="scan+support")

    report = dict(world_seed=WORLD_SEED,
                  page=str(args.page), page_shape=list(scan_page.shape),
                  page_origin_xz_m=list(scan_page.origin_m),
                  page_origin_native_xz=list(scan_page.origin_native),
                  spacing_m=scan_page.spacing_m,
                  window_nodes=WINDOW_NODES,
                  window_km=WINDOW_NODES * scan_page.spacing_m / 1000.,
                  declared_margin_cells=MARGIN_CELLS,
                  ranking_rule=RANKING_RULE,
                  convergence_sizes=list(CONVERGENCE_SIZES),
                  convergence_tolerance=dict(level=CONVERGENCE_LEVEL_TOLERANCE,
                                             area=CONVERGENCE_AREA_TOLERANCE),
                  reason_labels=REASON_LABELS,
                  source_key=list(mosaic.source_key_value),
                  support_pages=[dict(path=str(path), shape=list(page.shape),
                                      origin_native_xz=list(page.origin_native),
                                      origin_xz_m=list(page.origin_m))
                                 for path, page in zip(args.support_page, support)],
                  source_metadata=scan_page.metadata)

    basins = candidate_basins(scan_page.elevation, min_cells=args.min_basin_cells,
                              spacing_m=scan_page.spacing_m)
    basins.sort(key=lambda item: (-item["area_m2"], item["centre_rc"]))
    report["candidate_count"] = len(basins)

    accepted, rejected, plan_rects = evaluate_candidates(
        basins, scan_page, mosaic, limit=max(1, args.evaluate))
    evaluated = len(accepted) + len(rejected)
    counts = count_reasons(rejected)

    report["evaluated_count"] = evaluated
    report["unevaluated_count"] = max(0, len(basins) - evaluated)
    report["evaluation_note"] = (
        "the %d largest candidates were evaluated in ranking order and the remaining %d "
        "were not measured; every one of them is smaller than the %dth largest, so none "
        "can win the declared ranking" % (evaluated, report["unevaluated_count"], evaluated))
    report["rejected"] = rejected
    report["accepted"] = accepted
    report["rejection_counts"] = counts

    needed = [(entry["needed_window"]["native_column_range"][0],
               entry["needed_window"]["native_row_range"][0],
               entry["needed_window"]["nodes"], entry["needed_window"]["nodes"])
              for entry in rejected if entry["reason_code"] == REASON_UNMEASURABLE]
    report["convergence_plan"] = dict(
        needed_window_count=len(plan_rects),
        uncovered_window_count=len(needed),
        needed_windows=plan_rects,
        suggested_support_tiles=plan_support_tiles(needed, tile_nodes=args.tile_nodes,
                                                   stride=args.tile_stride) if needed else [])
    warning = dominant_reason_warning(rejected, counts, evaluated)
    if warning:
        report["criterion_warning"] = warning

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    summary = dict(world_seed=WORLD_SEED, candidates=len(basins), evaluated=evaluated,
                   rejection_counts=counts)

    # A refusal is a result, and so is a suspect criterion. If one category removed
    # every large candidate, no accepted basin can be published as *the* answer: the
    # ranking rule is by area, and the basins that should have won were never measured.
    # The run still reports the accepted list, but its status says what it is.
    if accepted and warning:
        report["status"] = "provisional_accepted_criterion_suspect"
        report["note"] = (
            "the largest accepted basin (%s) is NOT reported as the answer: %s Generate "
            "the pages in convergence_plan.suggested_support_tiles and re-run with them as "
            "--support-page; the tolerances were not relaxed and no non-closed basin was "
            "substituted." % (report_accepted_area(accepted), warning))
        (output / "selection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(dict(summary, status=report["status"],
                              provisional_basin_area_km2=round(accepted[0]["area_km2"], 3),
                              suggestion=report["note"]), indent=2))
        return 2

    if not accepted:
        if needed:
            report["status"] = "needs_more_td_coverage"
            report["note"] = (
                "%d candidate(s) could not be measured because their convergence windows "
                "leave the saved pages. Generate the tiles in convergence_plan."
                "suggested_support_tiles and re-run with them as --support-page; the "
                "convergence gate was not relaxed and no non-closed basin was substituted."
                % len(needed))
            code = 2
        else:
            report["status"] = "no_accepted_area"
            report["note"] = ("no candidate satisfied every rule; tolerances were not "
                              "relaxed and no non-closed basin was substituted")
            code = 1
        (output / "selection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(dict(summary, status=report["status"],
                              rejected=len(rejected)), indent=2))
        return code

    chosen = accepted[0]
    origin_rc = acceptance_window_origin_rc(chosen["extent_rc"])
    window_origin_xz = (scan_page.origin_m[0] + origin_rc[1] * scan_page.spacing_m,
                        scan_page.origin_m[1] + origin_rc[0] * scan_page.spacing_m)
    window_origin_native = (scan_page.origin_native[0] + origin_rc[1],
                            scan_page.origin_native[1] + origin_rc[0])
    acceptance = (window_origin_native[0], window_origin_native[1],
                  WINDOW_NODES, WINDOW_NODES)
    report.update(status="accepted", chosen=chosen,
                  rejected_uncovered_window_count=report["convergence_plan"]["uncovered_window_count"],
                  window_origin_rc=list(origin_rc),
                  window_origin_native_xz=list(window_origin_native),
                  window_origin_xz_m=list(window_origin_xz),
                  window_extent_xz_m=[list(window_origin_xz),
                                      [window_origin_xz[0] + (WINDOW_NODES - 1) * scan_page.spacing_m,
                                       window_origin_xz[1] + (WINDOW_NODES - 1) * scan_page.spacing_m]],
                  coverage_km=(WINDOW_NODES - 1) * scan_page.spacing_m / 1000.,
                  acceptance_window_covered_by_saved_pages=bool(mosaic.covers(*acceptance)),
                  note=("coverage is %.2f km, not exactly 40 km; the spec requires stating "
                        "this rather than rounding it"
                        % ((WINDOW_NODES - 1) * scan_page.spacing_m / 1000.)))
    if not mosaic.covers(*acceptance):
        report["acceptance_window_note"] = (
            "the placed acceptance window is not covered by the saved pages; it must be "
            "generated before the area can be built from TD terrain")
    (output / "selection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(dict(summary, status=report["status"],
                          basin_area_km2=round(chosen["area_km2"], 3),
                          bed_m=round(chosen["bed_m"], 2),
                          spill_m=round(chosen["spill_m"], 2),
                          window_origin_native_xz=list(window_origin_native),
                          window_origin_xz_m=[round(value, 1) for value in window_origin_xz],
                          coverage_km=round(report["coverage_km"], 3)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
