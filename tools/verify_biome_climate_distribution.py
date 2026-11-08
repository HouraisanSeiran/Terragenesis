"""Read-only p5.3 distribution run: are all 16 biome palette slots reachable?

Contract: ``.scratch/river-infinite-world/biome-climate-spec.md``.

Labels used throughout (they are kept apart on purpose):

* **marginal edge** -- a distribution measured on **one grid** for **one axis**: the
  landform ordinals on the published ``literal_metre`` artifact, and the climate
  variants on a grid covering a full latitude period.
* **co-located joint observation** -- on **one and the same grid**, how many of the
  16 ``(ordinal, variant)`` slots actually occur together.  That is what a world
  can show inside a single window; it is reported for the published 15.27 km
  window and for a large grid spanning one latitude period.
* **direct-product reachability** -- ``{(ordinal, variant)}`` of the two measured
  marginal edges, mapped through ``palette_index`` to the 16 frozen palette names.
  This says the 16 slots are *addressable*, **not** that 16 slots were observed on
  one grid.

The acceptance grid is 12 columns x 96 rows over x 0..880 km and z 0..one whole
latitude period (1 920 km), which is §7.1's ">= 1 complete latitude period".  The contract's
§6.1 probe lattice (1 900 km = 0.99 periods, deliberately stopping short of the seam) is
re-run only to reproduce that probe's published share table, and the period-coverage claim
is kept on the 1 920 km grid alone.  A denser 24 x 192 cross-check grid, a five-phase
robustness sweep of the z origin, and a precipitation-saturation lattice sweep are run as
well.

The two axes move on different scales (contract §6.3, measured): the landform
ordinal ``dominant_type`` changes within ~15 km of terrain while the climate
``variant`` needs one full ``LATITUDE_PERIOD_M`` (1 920 km) to walk a period.  On
the published 15.27 km window the ordinal edge shows all four values and the
climate edge shows **one** value.  That is a sample fact about that window and
seed; this script makes **no** universal claim that no window anywhere can hold
all 16 slots, and it never reports the independent direct product as if it were a
co-located observation.

What is read, and what is never touched
---------------------------------------

Read (``verification/`` is opened read-only and stays byte-identical):

* ``verification/metric-region-v1/literal_metre/landforms.npz`` keys ``weights``
  (float64 (509, 509, 4)) and ``dominant_type`` (uint8 (509, 509)) with
  ``np.load(..., allow_pickle=False)``;
* ``verification/metric-region-v1/literal_metre/base/manifest.json`` for the grid
  geometry and seed;
* the 16 biome json **names** under
  ``src/main/resources/data/remotemountains/worldgen/biome`` (existence only).

Consumed, never modified: ``terrain_pipeline/surface_rivers/metric_biome_climate.py``
(the frozen P5.2 rules), ``terrain_pipeline/surface_rivers/metric_climate_refinement.py``
(v2 climate, P4 delivered) and -- for the co-located section only --
``terrain_pipeline/metric_region.py`` with ``terrain_pipeline/hydrology_planning.py``,
through their public entry points.  Nothing is written under ``verification/``.

Where the normalized numbers come from (§2.1, zero new assumptions):
``temperature = clip((BIO1_c + 12) / 45, 0, 1)`` and ``rain = clip(BIO12_mm / 2200, 0, 1)``,
implemented once in ``metric_biome_climate.climate_coordinates``; both are
**normalized biome-selection coordinates, not physical climate quantities**.

Run:

    .\\runtime\\venv\\Scripts\\python.exe tools\\verify_biome_climate_distribution.py
"""

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.climate_forcing import BIOME_PALETTE, LANDFORM_COUNT, LANDFORM_NAMES, PALETTE_SIZE, PRECIPITATION_SPAN_MM, TEMPERATURE_OFFSET_C, TEMPERATURE_SPAN_C, VARIANT_COUNT, VARIANT_NAMES, climate_coordinates, palette_index, variant
from terrain_pipeline.climate_forcing import LATITUDE_PERIOD_M, sample_climate_v2


SCHEMA = "metric-biome-climate-distribution-v1"
DEFAULT_SEED = 20261020
DEFAULT_OUTPUT = Path(".scratch/river-infinite-world/p53-biome-climate-distribution.json")

# Acceptance lattice: 12 columns x 96 rows, x 0..880 km, z 0..one whole latitude
# period, so §7.1's ">= 1 complete latitude period" is met by the acceptance grid.
DEFAULT_COLUMNS = 12
DEFAULT_ROWS = 96
DEFAULT_X_SPAN_M = 880_000.
DEFAULT_Z_SPAN_M = 1_920_000.
# §7.1 cross-check grid: x 0..880 km, z one exact latitude period (12 x 96).
CROSSCHECK_COLUMNS = 12
CROSSCHECK_ROWS = 96
CROSSCHECK_X_SPAN_M = 880_000.
# Denser robustness grid over the same spans.
DENSE_COLUMNS = 24
DENSE_ROWS = 192
DENSE_X_SPAN_M = 880_000.

# The §6.1 probe lattice (x 0..880 km, z 0..1900 km) and its published numbers, kept
# as a reproduction check.  It is 98.96% of a period, so it is not the §7.1 grid.
CONTRACT_PROBE_COLUMNS = 12
CONTRACT_PROBE_ROWS = 96
CONTRACT_PROBE_X_SPAN_M = 880_000.
CONTRACT_PROBE_Z_SPAN_M = 1_900_000.
CONTRACT_PROBE_SHARES = (31.25, 29.34, 29.69, 9.72)
CONTRACT_PROBE_BIO1_C = (-20.16, 36.95)
CONTRACT_PROBE_BIO12_MM = (110.5, 2195.9)

LANDFORMS_RELATIVE = Path("verification/metric-region-v1/literal_metre/landforms.npz")
MANIFEST_RELATIVE = Path("verification/metric-region-v1/literal_metre/base/manifest.json")
BIOME_DIR_RELATIVE = Path("src/main/resources/data/remotemountains/worldgen/biome")
# §6.3 evidence window: the whole published literal_metre region, sub-sampled on a
# 43 x 43 lattice so both edges are read on identical coordinates.
WINDOW_SAMPLES = 43

# Co-located large grid (section 6b): one latitude period along z at a coarse metre
# spacing.  ``coarse_condition_field`` refuses more than 1 048 576 cells per query,
# so 240 m spacing over 30 km x one period (8001 x 126 cells) is the cheapest size
# that still spans a whole period; the run takes about half a minute.
JOINT_SPACING_M = 240.
JOINT_X_SPAN_M = 30_000.
JOINT_CELL_BUDGET = 1_048_576

# §4 item 3 / §1.3: out-of-range and non-integer input must raise, never clamp.
REJECTION_CASES = (
    ("ordinal 4 above the frozen 0..3 range", 4, 0),
    ("ordinal -1 below the frozen 0..3 range", -1, 0),
    ("variant 4 above the frozen 0..3 range", 0, 4),
    ("variant -1 below the frozen 0..3 range", 0, -1),
    ("float ordinal 1.0 would silently truncate", 1.0, 0),
    ("float variant 2.0 would silently truncate", 0, 2.0),
    ("bool ordinal True", True, 0),
)


class Report:
    """Collects sections and prints one OK/FAIL line per check as it runs."""

    def __init__(self):
        self.sections = {}
        self.checks = []

    def check(self, name, passed, detail=None):
        passed = bool(passed)
        self.checks.append({"check": name, "passed": passed, "detail": detail})
        print("%-4s %s%s" % ("OK" if passed else "FAIL", name,
                              "" if detail is None else "  [%s]" % (detail,)))
        return passed

    def header(self, name):
        print("\n== %s" % (name,))

    def section(self, name, payload):
        self.sections[name] = payload

    def note(self, text):
        print("     %s" % (text,))

    @property
    def passed(self):
        return all(item["passed"] for item in self.checks)


def _percent(count, total):
    return float(round(float(count) / float(total) * 100., 4))


def _counts(values, size):
    flat = np.asarray(values).reshape(-1)
    return [int(v) for v in np.bincount(flat.astype(np.int64), minlength=size)[:size]]


def _range_or_none(values, mask):
    values = np.asarray(values, np.float64)
    if not bool(np.any(mask)):
        return None
    selected = values[mask]
    return [float(selected.min()), float(selected.max())]


def _json_default(value):
    """Make numpy scalars and arrays JSON-serializable in the written report."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError("not JSON serializable: %r" % (value,))


def _load_landform_artifact(root):
    with np.load(root / LANDFORMS_RELATIVE, allow_pickle=False) as data:
        return sorted(data.files), np.asarray(data["weights"]), np.asarray(data["dominant_type"])


def landform_edge(report, root):
    """§6.3 item 1: the landform marginal edge, read from the published artifact."""
    report.header("1. LANDFORM MARGINAL EDGE (read-only, %s)" % (LANDFORMS_RELATIVE.as_posix(),))
    keys, weights, dominant = _load_landform_artifact(root)
    report.check("npz exposes exactly the keys weights + dominant_type",
                 keys == ["dominant_type", "weights"], keys)
    report.check("weights is float64 with shape (z, x, 4)",
                 weights.dtype == np.float64 and weights.shape == dominant.shape + (LANDFORM_COUNT,),
                 "%s %s" % (weights.dtype, weights.shape))
    report.check("dominant_type is a uint8 (z, x) label grid",
                 dominant.dtype == np.uint8 and dominant.ndim == 2,
                 "%s %s" % (dominant.dtype, dominant.shape))
    # §1.2.1: dominant_type == argmax(weights) is the ordinal source; pin it.
    report.check("dominant_type == argmax(weights) (the spec 1.2.1 ordinal source)",
                 bool(np.array_equal(np.argmax(weights, axis=-1).astype(np.uint8), dominant)))

    total = int(dominant.size)
    counts = _counts(dominant, LANDFORM_COUNT)
    present = sorted(int(v) for v in np.unique(dominant))
    report.check("every landform ordinal lies inside 0..3",
                 all(0 <= value < LANDFORM_COUNT for value in present), present)
    for ordinal in range(LANDFORM_COUNT):
        report.note("ordinal %d %-9s %8d cells  %7.2f%%" % (
            ordinal, LANDFORM_NAMES[ordinal], counts[ordinal], _percent(counts[ordinal], total)))
    report.check("all 4 landform ordinals appear (marginal edge, each nonzero)",
                 present == list(range(LANDFORM_COUNT)), present)

    payload = {"source": LANDFORMS_RELATIVE.as_posix(), "cells": total,
               "weights_shape": list(weights.shape), "dominant_type_shape": list(dominant.shape),
               "counts": {str(o): counts[o] for o in range(LANDFORM_COUNT)},
               "shares_percent": {str(o): _percent(counts[o], total) for o in range(LANDFORM_COUNT)},
               "names": {str(o): LANDFORM_NAMES[o] for o in range(LANDFORM_COUNT)},
               "observed_ordinals": present,
               "observed_on": "the published literal_metre artifact (15.27 x 15.27 km)"}
    report.section("landform_marginal_edge", payload)
    return payload


def _climate_lattice(columns, rows, x_span_m, z_span_m):
    x = np.linspace(0., float(x_span_m), int(columns))
    z = np.linspace(0., float(z_span_m), int(rows))
    return np.meshgrid(x, z, indexing="ij")


def _climate_observations(seed, mesh_x, mesh_z):
    body = sample_climate_v2(seed, mesh_x, mesh_z)
    bio = np.asarray(body["BIO1_4_12_15"], np.float64)
    temperature, rain = climate_coordinates(bio[0], bio[2])
    return body, bio, temperature, rain, np.asarray(variant(temperature, rain), np.int64)


def climate_edge(report, seed, columns, rows, x_span_m, z_span_m):
    """§6.3 item 2 / §7.1: the climate marginal edge, run over >= 1 period."""
    report.header("2. CLIMATE MARGINAL EDGE (sample_climate_v2, v2 defaults, seed %d)" % (seed,))
    mesh_x, mesh_z = _climate_lattice(columns, rows, x_span_m, z_span_m)
    span_x, span_z = float(np.ptp(mesh_x)), float(np.ptp(mesh_z))
    report.note("grid %d columns x %d rows = %d points" % (columns, rows, mesh_x.size))
    report.note("x span %.1f m, z span %.1f m = %.4f latitude periods (period %.1f m)" % (
        span_x, span_z, span_z / LATITUDE_PERIOD_M, LATITUDE_PERIOD_M))
    # This is the spec 7.1 acceptance grid: its z span covers >= one whole latitude period.
    # The spec 6.1 probe lattice (z 0..1900 km = 0.99 periods, which deliberately keeps the
    # last 20 km away from the period seam) is a *different* lattice serving a *different*
    # job -- reproducing that probe's published share table -- and lives in section 3b.  The
    # period-coverage claim belongs to this grid and to section 3c, not to the 1900 km one.
    report.check("acceptance grid covers at least one full latitude period (spec 6.2 / 7.1)",
                 span_z >= LATITUDE_PERIOD_M - 1e-9, "z span %.1f m" % (span_z,))

    body, bio, temperature, rain, bands = _climate_observations(seed, mesh_x, mesh_z)
    report.check("BIO1_4_12_15 has 4 channels on the query grid",
                 bio.shape == (4,) + mesh_x.shape, bio.shape)
    # §2.3: BIO12 == sum(months) is exact, so this is the same single truth.
    report.check("BIO12 == annual_precipitation_mm (single source)",
                 bool(np.array_equal(bio[2], np.asarray(body["annual_precipitation_mm"], np.float64))))
    report.check("the climate output is a pure function of the world point",
                 bool(np.array_equal(bio, _climate_observations(seed, mesh_x, mesh_z)[1])))

    total = int(bands.size)
    counts = _counts(bands, VARIANT_COUNT)
    present = sorted(int(v) for v in np.unique(bands))
    report.check("every variant lies inside 0..3",
                 all(0 <= value < VARIANT_COUNT for value in present), present)
    report.note("BIO1  %.4f .. %.4f C" % (bio[0].min(), bio[0].max()))
    report.note("BIO12 %.4f .. %.4f mm" % (bio[2].min(), bio[2].max()))
    report.note("temperature(normalized) %.6f .. %.6f" % (temperature.min(), temperature.max()))
    report.note("rain(normalized)        %.6f .. %.6f" % (rain.min(), rain.max()))
    per_variant = {}
    for band in range(VARIANT_COUNT):
        mask = bands == band
        entry = {"count": counts[band], "share_percent": _percent(counts[band], total),
                 "BIO1_c": _range_or_none(bio[0], mask), "BIO12_mm": _range_or_none(bio[2], mask)}
        per_variant[str(band)] = entry
        report.note("variant %d %-9s %6d points %7.2f%%   BIO1 %s   BIO12 %s" % (
            band, VARIANT_NAMES[band], counts[band], entry["share_percent"],
            "n/a" if entry["BIO1_c"] is None else "%.3f..%.3f" % tuple(entry["BIO1_c"]),
            "n/a" if entry["BIO12_mm"] is None else "%.1f..%.1f" % tuple(entry["BIO12_mm"])))
    report.check("all 4 climate variants appear (marginal edge, each nonzero)",
                 present == list(range(VARIANT_COUNT)), present)
    comparison = ", ".join("variant %d %.2f%% vs %.2f%%" % (
        int(band), per_variant[band]["share_percent"], CONTRACT_PROBE_SHARES[int(band)])
        for band in sorted(per_variant, key=int))
    report.note("this (%d km) grid vs the spec 6.1 probe (%d km): %s" % (
        int(round(span_z / 1000.)), int(round(CONTRACT_PROBE_Z_SPAN_M / 1000.)), comparison))
    report.note("the two lattices differ only in the final 20 km before the period seam, so the"
                " climate marginal edge is stable across them (spec 6.1 correction note)")

    clip = clip_reachability(report, bio, temperature, rain)
    payload = {
        "seed": seed, "columns": int(columns), "rows": int(rows), "points": int(mesh_x.size),
        "x_span_m": span_x, "z_span_m": span_z, "latitude_period_m": float(LATITUDE_PERIOD_M),
        "periods_covered": span_z / LATITUDE_PERIOD_M,
        "BIO1_c": [float(bio[0].min()), float(bio[0].max())],
        "BIO12_mm": [float(bio[2].min()), float(bio[2].max())],
        "temperature": [float(temperature.min()), float(temperature.max())],
        "rain": [float(rain.min()), float(rain.max())],
        "counts": {str(v): counts[v] for v in range(VARIANT_COUNT)},
        "shares_percent": {str(v): _percent(counts[v], total) for v in range(VARIANT_COUNT)},
        "names": {str(v): VARIANT_NAMES[v] for v in range(VARIANT_COUNT)},
        "per_variant": per_variant, "observed_variants": present, "clip": clip,
    }
    report.section("climate_marginal_edge", payload)
    return payload


def clip_reachability(report, bio, temperature, rain):
    """§3.3 / §7.1: is each end of the clip reachable, and on which input?

    The section's pass condition is the **pure-function** endpoint behaviour only: the
    documented physical inputs map to 0./1., the §3.3 seam holds, and the clip saturates
    outside its bounds.  The counts measured on the acceptance grid are reported as facts
    and are deliberately *not* a pass condition -- the dry end is physically out of reach
    (v2 declares a 100 mm precipitation minimum) and the wet seam depends on the lattice.
    """
    report.header("3. CLIP END-REACHABILITY (spec 2.1 / 3.3 / 7.1)")
    lo_temperature, _ = climate_coordinates(-TEMPERATURE_OFFSET_C, 0.)
    hi_temperature, _ = climate_coordinates(TEMPERATURE_SPAN_C - TEMPERATURE_OFFSET_C, 0.)
    _, lo_rain = climate_coordinates(0., 0.)
    _, hi_rain = climate_coordinates(0., PRECIPITATION_SPAN_MM)
    report.check("function endpoint: BIO1 = -12 C maps to temperature == 0.",
                 lo_temperature == 0., repr(lo_temperature))
    report.check("function endpoint: BIO1 = +33 C maps to temperature == 1.",
                 hi_temperature == 1., repr(hi_temperature))
    report.check("function endpoint: BIO12 = 0 mm maps to rain == 0.", lo_rain == 0., repr(lo_rain))
    report.check("function endpoint: BIO12 = 2200 mm maps to rain == 1.", hi_rain == 1., repr(hi_rain))
    report.check("function endpoint: the spec 3.3 seam holds (BIO12 = 2600 mm still rain == 1.)",
                 climate_coordinates(0., PRECIPITATION_SPAN_MM + 400.)[1] == 1.)
    report.check("function endpoint: the clip saturates outside its bounds (BIO1 = -100 C)",
                 climate_coordinates(-100., -50.)[0] == 0.)
    report.check("function endpoint: the rain clip saturates below its lower bound (BIO12 = -50 mm)",
                 climate_coordinates(0., -50.)[1] == 0., repr(climate_coordinates(0., -50.)[1]))

    observed = {
        "temperature_equals_0": int(np.count_nonzero(temperature == 0.)),
        "temperature_equals_1": int(np.count_nonzero(temperature == 1.)),
        "rain_equals_0": int(np.count_nonzero(rain == 0.)),
        "rain_equals_1": int(np.count_nonzero(rain == 1.)),
        "BIO1_at_or_below_minus_12": int(np.count_nonzero(bio[0] <= -TEMPERATURE_OFFSET_C)),
        "BIO1_at_or_above_plus_33": int(np.count_nonzero(
            bio[0] >= TEMPERATURE_SPAN_C - TEMPERATURE_OFFSET_C)),
        "BIO12_at_or_above_2200": int(np.count_nonzero(bio[2] >= PRECIPITATION_SPAN_MM)),
        "BIO12_at_or_below_0": int(np.count_nonzero(bio[2] <= 0.)),
    }
    temperature_low = observed["temperature_equals_0"] > 0
    temperature_high = observed["temperature_equals_1"] > 0
    rain_low = observed["rain_equals_0"] > 0
    rain_high = observed["rain_equals_1"] > 0
    measured = {"temperature_0": temperature_low, "temperature_1": temperature_high,
                "rain_0": rain_low, "rain_1": rain_high}
    report.note("MEASURED END REACHABILITY on the acceptance grid -- reported as fact, NOT a pass")
    report.note("condition (the dry end is physically out of reach and the wet seam is lattice-")
    report.note("dependent).  Raw counts: " + ", ".join(
        "%s=%d" % item for item in sorted(observed.items())))
    report.note("  temperature == 0.  needs BIO1 <= -12 C: %s  [%d of %d points]" % (
        "reached" if temperature_low else "NOT reached", observed["temperature_equals_0"],
        int(temperature.size)))
    report.note("  temperature == 1.  needs BIO1 >= +33 C: %s  [%d points]" % (
        "reached" if temperature_high else "NOT reached", observed["temperature_equals_1"]))
    report.note("  rain == 0.  needs BIO12 <= 0 mm: %s -- v2 declares a precipitation minimum of"
                " 100 mm (RefinedClimateParameters), so no real point can reach it [%d points]" % (
                    "reached" if rain_low else "NOT REACHABLE", observed["BIO12_at_or_below_0"]))
    report.note("  rain == 1.  needs BIO12 >= 2200 mm (spec 3.3 seam): %s  [%d points; this grid"
                " tops out at %.1f mm]" % (
                    "reached" if rain_high else "NOT reached here", observed["rain_equals_1"],
                    bio[2].max()))
    report.note("  the wet seam on real data is exercised in section 3d, which widens the x lattice"
                " only (orographic lift); the dry end is answered by v2's declared 100 mm floor")
    payload = {"function_endpoints": {
                   "BIO1_c": [-TEMPERATURE_OFFSET_C, TEMPERATURE_SPAN_C - TEMPERATURE_OFFSET_C],
                   "BIO12_mm": [0., PRECIPITATION_SPAN_MM],
                   "temperature": [lo_temperature, hi_temperature], "rain": [lo_rain, hi_rain]},
               "measured": measured, "observed": observed, "BIO12_max_mm": float(bio[2].max()),
               "BIO1_min_c": float(bio[0].min()), "BIO1_max_c": float(bio[0].max()),
               "pass_condition": "pure-function endpoint mapping only (see the section 3 checks); "
                                 "measured end reachability is reported, not asserted",
               "dry_end_note": "rain == 0. requires BIO12 <= 0 mm, so v2's 100 mm precipitation "
                               "minimum makes it physically unreachable on real data",
               "seam_note": "BIO12 in [2200, 3200] mm all maps to rain == 1. (spec 3.3)"}
    report.section("clip", payload)
    return payload


def _period_cross_check(report, seed):
    """§6.2 / §7.1: a grid whose z span is exactly one latitude period.

    The published §6.1 lattice is 1 900 km, i.e. 0.99 of a period (it deliberately
    leaves 20 km so the period seam is avoided); this grid is the one that actually
    spans a whole period, and it is where the period-coverage claim belongs.
    """
    report.header("3c. PERIOD CROSS-CHECK GRID (x 0..880 km, z exactly one period)")
    check_x, check_z = _climate_lattice(CROSSCHECK_COLUMNS, CROSSCHECK_ROWS,
                                        CROSSCHECK_X_SPAN_M, float(LATITUDE_PERIOD_M))
    _, _, _, _, check_bands = _climate_observations(seed, check_x, check_z)
    check_counts = _counts(check_bands, VARIANT_COUNT)
    span_z = float(np.ptp(check_z))
    report.note("points %d, z span %.1f m = %.4f periods, counts %s, shares %s" % (
        check_bands.size, span_z, span_z / LATITUDE_PERIOD_M, check_counts,
        [round(_percent(check_counts[v], check_bands.size), 2) for v in range(VARIANT_COUNT)]))
    report.check("the period cross-check grid covers a whole latitude period",
                 span_z >= LATITUDE_PERIOD_M - 1e-9, "z span %.1f m" % (span_z,))
    report.check("the period cross-check grid shows all 4 climate variants",
                 sorted(int(v) for v in np.unique(check_bands)) == list(range(VARIANT_COUNT)))
    payload = {"columns": CROSSCHECK_COLUMNS, "rows": CROSSCHECK_ROWS,
               "x_span_m": CROSSCHECK_X_SPAN_M, "z_span_m": span_z,
               "periods_covered": span_z / LATITUDE_PERIOD_M, "points": int(check_bands.size),
               "counts": {str(v): check_counts[v] for v in range(VARIANT_COUNT)},
               "shares_percent": {str(v): _percent(check_counts[v], check_bands.size)
                                  for v in range(VARIANT_COUNT)}}
    report.section("period_cross_check", payload)
    return payload


PHASE_OFFSETS_M = (0., 240_000., 480_000., 960_000., 1_440_000.)


def phase_cross_check(report, seed):
    """Robustness: does the 4-variant climate edge survive a phase shift along z?

    The acceptance grid always starts at z = 0; this repeats it at four shifted phases
    (each still one whole period long) to show that the measured edge is a property of the
    v2 climate rather than of where the lattice happens to sample the sine.  Measured at
    five phases: all four variants appear every time; the shares move (snowy 28.56-33.25%,
    arid 27.00-28.91%, temperate 25.00-29.86%, humid 10.42-15.54%), so the *presence* of four
    variants is stable while the exact shares are not a distribution law.
    """
    report.header("3f. PHASE ROBUSTNESS OF THE CLIMATE EDGE (z shifted by %s m each time)" % (
        ", ".join("%.0f" % offset for offset in PHASE_OFFSETS_M),))
    entries = []
    for offset in PHASE_OFFSETS_M:
        mesh_x, mesh_z = _climate_lattice(CROSSCHECK_COLUMNS, CROSSCHECK_ROWS,
                                          CROSSCHECK_X_SPAN_M, float(LATITUDE_PERIOD_M))
        mesh_z = mesh_z + float(offset)
        _, bio, _, _, bands = _climate_observations(seed, mesh_x, mesh_z)
        counts = _counts(bands, VARIANT_COUNT)
        present = sorted(int(v) for v in np.unique(bands))
        entries.append({"z_offset_m": float(offset), "counts": {str(v): counts[v]
                                                                for v in range(VARIANT_COUNT)},
                        "shares_percent": {str(v): _percent(counts[v], bands.size)
                                           for v in range(VARIANT_COUNT)},
                        "observed_variants": present,
                        "BIO1_c": [float(bio[0].min()), float(bio[0].max())],
                        "BIO12_mm": [float(bio[2].min()), float(bio[2].max())]})
        report.note("z offset %8.0f km: variants %s, shares %s, BIO1 %.2f..%.2f C, BIO12 %.1f..%.1f mm" % (
            offset / 1000., present, [round(_percent(counts[v], bands.size), 2)
                                      for v in range(VARIANT_COUNT)],
            bio[0].min(), bio[0].max(), bio[2].min(), bio[2].max()))
    report.check("all 4 climate variants appear at every tested z phase",
                 all(entry["observed_variants"] == list(range(VARIANT_COUNT))
                     for entry in entries))
    report.note("SCOPE: five phases at one seed and one x range; the shares vary, so this shows")
    report.note("the edge is not an artifact of the lattice origin, not a distribution law.")
    payload = {"z_offsets_m": list(PHASE_OFFSETS_M), "entries": entries}
    report.section("phase_cross_check", payload)
    return payload


def saturation_evidence(report, seed):
    """Auxiliary: on which lattice does BIO12 actually reach the 2200 mm seam?

    The acceptance lattice of §6.1 tops out below the normalization span, so
    ``rain == 1.`` never occurs there (contract §3.4 reports the same: the wet band
    is scarce because v2 precipitation barely touches 2200 mm).  Widening the
    x lattice only adds orographically lifted columns, nothing else, and shows
    whether the seam is reachable on real data at all.
    """
    report.header("3d. AUXILIARY: PRECIPITATION SATURATION ON WIDER X LATTICES")
    rows = CONTRACT_PROBE_ROWS
    candidates = ((CONTRACT_PROBE_COLUMNS, CONTRACT_PROBE_X_SPAN_M),
                  (12, 3_520_000.), (24, 7_040_000.))
    results = []
    for columns, span_x in candidates:
        mesh_x, mesh_z = _climate_lattice(columns, rows, span_x, CONTRACT_PROBE_Z_SPAN_M)
        _, bio, _, rain, _ = _climate_observations(seed, mesh_x, mesh_z)
        entry = {"columns": columns, "x_span_m": span_x, "points": int(mesh_x.size),
                 "BIO12_mm": [float(bio[2].min()), float(bio[2].max())],
                 "BIO12_at_or_above_2200": int(np.count_nonzero(bio[2] >= PRECIPITATION_SPAN_MM)),
                 "rain_equals_1": int(np.count_nonzero(rain == 1.))}
        results.append(entry)
        report.note("x span %8.0f km, %2d columns: BIO12 %.1f..%.1f mm, BIO12 >= 2200 mm on %d "
                    "points, rain == 1. on %d points" % (
                        span_x / 1000., columns, entry["BIO12_mm"][0], entry["BIO12_mm"][1],
                        entry["BIO12_at_or_above_2200"], entry["rain_equals_1"]))
    report.check("the rain == 1. seam is reachable on some real lattice (spec 3.3)",
                 any(entry["rain_equals_1"] > 0 for entry in results))
    report.note("SCOPE: auxiliary.  The acceptance lattice of section 2 keeps the contract's")
    report.note("x 0..880 km and reports its own (unreached) rain == 1. count.")
    report.section("saturation_evidence", {"lattices": results})
    return {"lattices": results}


def contract_probe_reproduction(report, seed):
    """Re-run the §6.1 probe lattice and compare with its published table."""
    report.header("3b. CONTRACT 6.1 PROBE REPRODUCTION (12 x 96, x 0..880 km, z 0..1900 km)")
    mesh_x, mesh_z = _climate_lattice(CONTRACT_PROBE_COLUMNS, CONTRACT_PROBE_ROWS,
                                      CONTRACT_PROBE_X_SPAN_M, CONTRACT_PROBE_Z_SPAN_M)
    _, bio, _, _, bands = _climate_observations(seed, mesh_x, mesh_z)
    counts = _counts(bands, VARIANT_COUNT)
    shares = tuple(_percent(counts[v], bands.size) for v in range(VARIANT_COUNT))
    bio1 = (float(bio[0].min()), float(bio[0].max()))
    bio12 = (float(bio[2].min()), float(bio[2].max()))
    report.note("shares %s  (contract 6.1 column A: %s)" % (
        [round(v, 2) for v in shares], list(CONTRACT_PROBE_SHARES)))
    report.note("BIO1 %.2f..%.2f C (contract %.2f..%.2f)  BIO12 %.1f..%.1f mm (contract %.1f..%.1f)" % (
        bio1 + CONTRACT_PROBE_BIO1_C + bio12 + CONTRACT_PROBE_BIO12_MM))
    report.note("raw counts %s, x span %.0f m, z span %.0f m" % (
        counts, float(np.ptp(mesh_x)), float(np.ptp(mesh_z))))
    report.check("reproduces the contract 6.1 shares to 0.01 pp",
                 all(abs(a - b) <= 0.01 for a, b in zip(shares, CONTRACT_PROBE_SHARES)),
                 [round(v, 2) for v in shares])
    report.check("reproduces the contract 6.1 BIO1 range",
                 all(abs(a - b) <= 0.01 for a, b in zip(bio1, CONTRACT_PROBE_BIO1_C)),
                 [round(v, 2) for v in bio1])
    report.check("reproduces the contract 6.1 BIO12 range",
                 all(abs(a - b) <= 0.05 for a, b in zip(bio12, CONTRACT_PROBE_BIO12_MM)),
                 [round(v, 1) for v in bio12])
    payload = {"columns": CONTRACT_PROBE_COLUMNS, "rows": CONTRACT_PROBE_ROWS,
               "x_span_m": CONTRACT_PROBE_X_SPAN_M, "z_span_m": CONTRACT_PROBE_Z_SPAN_M,
               "periods_covered": CONTRACT_PROBE_Z_SPAN_M / LATITUDE_PERIOD_M,
               "counts": {str(v): counts[v] for v in range(VARIANT_COUNT)},
               "shares_percent": {str(v): shares[v] for v in range(VARIANT_COUNT)},
               "contract_shares_percent": list(CONTRACT_PROBE_SHARES),
               "BIO1_c": list(bio1), "BIO12_mm": list(bio12),
               "contract_BIO1_c": list(CONTRACT_PROBE_BIO1_C),
               "contract_BIO12_mm": list(CONTRACT_PROBE_BIO12_MM)}
    report.section("contract_probe_reproduction", payload)
    return payload


def direct_product(report, ordinals, variants):
    """§6.3 item 3: the 16 slots as the direct product of the two marginal edges."""
    report.header("4. DIRECT PRODUCT OF THE TWO MARGINAL EDGES (reachability, not co-location)")
    ordinal_axis = np.asarray(sorted(ordinals), np.int64)
    variant_axis = np.asarray(sorted(variants), np.int64)
    grid_index = palette_index(ordinal_axis[:, None], variant_axis[None, :])
    expected = ordinal_axis[:, None] * VARIANT_COUNT + variant_axis[None, :]
    report.check("palette_index equals ordinal*4 + variant over the whole product grid",
                 bool(np.array_equal(np.asarray(grid_index), expected)))
    slots = []
    for ordinal in [int(v) for v in ordinal_axis]:
        for band in [int(v) for v in variant_axis]:
            index = int(palette_index(np.int64(ordinal), np.int64(band)))
            slots.append({"landform_ordinal": ordinal, "landform": LANDFORM_NAMES[ordinal],
                          "variant": band, "variant_name": VARIANT_NAMES[band],
                          "palette_index": index, "biome": BIOME_PALETTE[index]})
            report.note("ordinal %d %-9s + variant %d %-9s -> index %2d  %s" % (
                ordinal, LANDFORM_NAMES[ordinal], band, VARIANT_NAMES[band], index,
                BIOME_PALETTE[index]))
    indices = [slot["palette_index"] for slot in slots]
    product_size = len(ordinal_axis) * len(variant_axis)
    report.check("|landform edge| x |climate edge| equals the number of slots produced",
                 len(slots) == product_size,
                 "%d x %d = %d" % (len(ordinal_axis), len(variant_axis), product_size))
    report.check("all palette indices are distinct and inside 0..15",
                 len(set(indices)) == len(indices) and all(0 <= i < PALETTE_SIZE for i in indices),
                 "distinct=%d" % (len(set(indices)),))
    report.check("every slot resolves to a distinct frozen palette name",
                 len({slot["biome"] for slot in slots}) == len(slots))
    report.check("the direct product covers exactly the 16 frozen palette slots",
                 product_size == PALETTE_SIZE == len(BIOME_PALETTE), product_size)

    missing = sorted({(o, v) for o in range(LANDFORM_COUNT) for v in range(VARIANT_COUNT)}
                     - {(int(o), int(v)) for o in ordinal_axis for v in variant_axis})
    report.check("no slot of the full 4x4 grid is absent from the direct product", not missing, missing)
    report.note("SCOPE (reachability): this combines two independently measured edges.  It is NOT")
    report.note("a co-located observation of 16 slots -- see sections 6a and 6b for those.")
    payload = {"slots": slots, "slot_count": len(slots),
               "observed_ordinal_axis": [int(v) for v in ordinal_axis],
               "observed_variant_axis": [int(v) for v in variant_axis],
               "full_4x4_slots_absent_from_product": [list(item) for item in missing],
               "kind": "direct product of two independently measured marginal edges",
               "claim": "all 16 palette slots are reachable in the direct-product sense; "
                        "this is not a co-located joint observation"}
    report.section("direct_product", payload)
    return payload


def palette_bounds(report):
    """§1.3 / §4 item 3: out-of-range input raises; it is never silently accepted."""
    report.header("5. PALETTE INDEX BOUNDS (combinations outside the product)")
    report.check("palette table is 16 entries = 4 landforms x 4 variants",
                 PALETTE_SIZE == 16 and len(BIOME_PALETTE) == 16
                 and LANDFORM_COUNT == VARIANT_COUNT == 4)
    cases = []
    for label, ordinal, band in REJECTION_CASES:
        try:
            result = palette_index(ordinal, band)
        except ValueError as error:
            accepted, message = False, str(error)
        else:
            accepted, message = True, "returned %r" % (result,)
        cases.append({"case": label,
                      "ordinal": int(ordinal) if isinstance(ordinal, bool) else ordinal,
                      "variant": int(band) if isinstance(band, bool) else band,
                      "raised": not accepted, "message": message})
        report.check("rejected (raised, not clamped): %s" % (label,), not accepted, message)
    report.check("every out-of-product combination is rejected, none silently accepted",
                 all(case["raised"] for case in cases))
    payload = {"cases": cases, "palette_size": PALETTE_SIZE}
    report.section("palette_bounds", payload)
    return payload


def window_observation(report, root):
    """§6.3 evidence: on the published 15.27 km window, the two edges differ."""
    report.header("6a. CO-LOCATED OBSERVATION, PUBLISHED WINDOW (%s)" % (
        LANDFORMS_RELATIVE.as_posix(),))
    manifest = json.loads((root / MANIFEST_RELATIVE).read_text())
    grid = manifest["grid"]
    artifact_seed = int(manifest["identity"]["seed"])
    shape_z, shape_x = grid["shape_zx"]
    spacing_x, spacing_z = grid["spacing_x_m"], grid["spacing_z_m"]
    origin_x, origin_z = grid["origin_x_m"], grid["origin_z_m"]
    rows = np.linspace(0, shape_z - 1, WINDOW_SAMPLES).astype(np.int64)
    columns = np.linspace(0, shape_x - 1, WINDOW_SAMPLES).astype(np.int64)
    window_x = origin_x + columns * spacing_x
    window_z = origin_z + rows * spacing_z
    mesh_x, mesh_z = np.meshgrid(window_x, window_z, indexing="xy")
    span_x, span_z = float(np.ptp(mesh_x)), float(np.ptp(mesh_z))
    report.note("window %.1f x %.1f m on a %d x %d lattice (%d points), spacing %.0f m" % (
        span_x, span_z, WINDOW_SAMPLES, WINDOW_SAMPLES, mesh_x.size, spacing_x))
    report.note("z span / latitude period = %.4f%%" % (span_z / LATITUDE_PERIOD_M * 100.,))

    _, _, dominant = _load_landform_artifact(root)
    window_dominant = dominant[np.ix_(rows, columns)]
    body, bio, _, _, window_bands = _climate_observations(artifact_seed, mesh_x, mesh_z)
    ordinal_present = sorted(int(v) for v in np.unique(window_dominant))
    variant_present = sorted(int(v) for v in np.unique(window_bands))
    joint = np.bincount((window_dominant.astype(np.int64) * VARIANT_COUNT + window_bands).reshape(-1),
                        minlength=PALETTE_SIZE)
    joint_slots = [{"palette_index": i, "biome": BIOME_PALETTE[i], "count": int(joint[i]),
                    "landform_ordinal": i // VARIANT_COUNT, "variant": i % VARIANT_COUNT}
                   for i in range(PALETTE_SIZE) if joint[i] > 0]
    report.note("landform ordinals co-located here: %s (counts %s)" % (
        ordinal_present, _counts(window_dominant, LANDFORM_COUNT)))
    report.note("climate variants on the SAME grid: %s (counts %s)" % (
        variant_present, _counts(window_bands, VARIANT_COUNT)))
    report.note("BIO1 %.4f..%.4f C, BIO12 %.4f..%.4f mm, latitude_band_norm %.4f..%.4f" % (
        bio[0].min(), bio[0].max(), bio[2].min(), bio[2].max(),
        np.asarray(body["latitude_band_norm"]).min(), np.asarray(body["latitude_band_norm"]).max()))
    report.note("co-located slots present: %d of 16 -> %s" % (
        len(joint_slots), [slot["biome"] for slot in joint_slots]))
    report.check("this window shows all 4 landform ordinals",
                 ordinal_present == list(range(LANDFORM_COUNT)), ordinal_present)
    report.check("this same window shows fewer than 4 climate variants",
                 len(variant_present) < VARIANT_COUNT, variant_present)
    report.note("SCOPE: a sample fact about this 15.27 km window at this seed; not a statement")
    report.note("that no window anywhere can hold all 16 slots.")
    payload = {"artifact": LANDFORMS_RELATIVE.as_posix(), "manifest": MANIFEST_RELATIVE.as_posix(),
               "artifact_seed": artifact_seed,
               "grid": {"shape_zx": [shape_z, shape_x], "spacing_x_m": spacing_x,
                        "spacing_z_m": spacing_z, "origin_x_m": origin_x, "origin_z_m": origin_z},
               "window_span_m": [span_x, span_z],
               "window_span_percent_of_period": span_z / LATITUDE_PERIOD_M * 100.,
               "window_points": int(mesh_x.size),
               "window_landform_counts": {str(o): _counts(window_dominant, LANDFORM_COUNT)[o]
                                          for o in range(LANDFORM_COUNT)},
               "window_variant_counts": {str(v): _counts(window_bands, VARIANT_COUNT)[v]
                                         for v in range(VARIANT_COUNT)},
               "window_observed_ordinals": ordinal_present,
               "window_observed_variants": variant_present,
               "co_located_slots": joint_slots, "co_located_slot_count": len(joint_slots),
               "window_BIO1_c": [float(bio[0].min()), float(bio[0].max())],
               "window_BIO12_mm": [float(bio[2].min()), float(bio[2].max())],
               "scope": "sample fact about this window and seed; no universal claim"}
    report.section("window_observation", payload)
    return payload


def joint_grid_observation(report, seed, spacing_m, x_span_m):
    """Co-located landform + climate on one large grid spanning a latitude period."""
    report.header("6b. CO-LOCATED OBSERVATION, LARGE GRID (low-cost corroboration, optional)")
    from terrain_pipeline.hydrology_planning import coarse_condition_field
    from terrain_pipeline.metric_region import METRIC_30M_RECIPE_V1, process_region

    report.note("OPTIONAL: the acceptance evidence is sections 1 + 2 + 3b/3c/3d + 4 + 5 + 7 (two")
    report.note("marginal edges, their direct product, the rejection behaviour, the resources).")
    report.note("This section only asks what one grid can show *co-located*; --skip-joint-grid")
    report.note("drops it, and a degenerated result is reported as measured, never tuned away.")
    report.note("Size is computed before anything is generated, and an over-budget grid is skipped")
    report.note("rather than silently resized: keeping the published 30 m spacing over one period")
    report.note("times the 15.27 km window would be %d rows x %d columns = %.1fM cells, %.0fx the"
                " %d-cell per-query budget of coarse_condition_field" % (
                    64_001, 510, 64_001 * 510 / 1e6, 64_001 * 510 / JOINT_CELL_BUDGET,
                    JOINT_CELL_BUDGET))

    spacing = float(spacing_m)
    rows = int(round(float(LATITUDE_PERIOD_M) / spacing)) + 1
    columns = int(round(float(x_span_m) / spacing)) + 1
    mesh_x, mesh_z = np.meshgrid(np.arange(columns) * spacing, np.arange(rows) * spacing,
                                 indexing="xy")
    report.note("grid %d columns x %d rows = %d points at %.0f m spacing (%.1f x %.1f km)" % (
        columns, rows, mesh_x.size, spacing,
        float(np.ptp(mesh_x)) / 1000., float(np.ptp(mesh_z)) / 1000.))
    if mesh_x.size > JOINT_CELL_BUDGET:
        report.note("coarse_condition_field accepts at most %d cells per query; this grid is "
                    "%d, so section 6b is SKIPPED (rerun with a larger --joint-spacing-m)" % (
                        JOINT_CELL_BUDGET, mesh_x.size))
        return None
    started = time.time()
    height = np.asarray(coarse_condition_field(seed, mesh_x, mesh_z)[0], np.float64)
    region = process_region(height, 126., spacing, spacing, recipe=METRIC_30M_RECIPE_V1)
    elapsed = time.time() - started
    del height
    # Trim the recipe halo, exactly as the published pipeline crops it before publishing.
    halo = int(METRIC_30M_RECIPE_V1.required_halo_samples(spacing, spacing)[0])
    if rows - 2 * halo < 2 or columns - 2 * halo < 2:
        report.note("grid too small to trim the %d-sample halo; skipping section 6b" % (halo,))
        return None
    inside = (slice(halo, rows - halo), slice(halo, columns - halo))
    dominant = region.dominant_type[inside]
    _, bio, _, _, bands = _climate_observations(seed, mesh_x[inside], mesh_z[inside])
    joint = np.bincount((dominant.astype(np.int64) * VARIANT_COUNT + bands).reshape(-1),
                        minlength=PALETTE_SIZE)
    ordinal_present = sorted(int(v) for v in np.unique(dominant))
    variant_present = sorted(int(v) for v in np.unique(bands))
    slots = [{"palette_index": i, "biome": BIOME_PALETTE[i], "count": int(joint[i]),
              "share_percent": _percent(joint[i], joint.sum()),
              "landform_ordinal": i // VARIANT_COUNT, "variant": i % VARIANT_COUNT}
             for i in range(PALETTE_SIZE) if joint[i] > 0]
    report.note("generated in %.1f s (halo %d samples trimmed on each side)" % (elapsed, halo))
    report.note("ordinals here: %s of 4, variants here: %s of 4" % (
        ordinal_present, variant_present))
    report.note("co-located slots present: %d of 16" % (len(slots),))
    for slot in slots:
        report.note("slot %2d %-18s ordinal %d + variant %d  %9d points %7.2f%%" % (
            slot["palette_index"], slot["biome"], slot["landform_ordinal"], slot["variant"],
            slot["count"], slot["share_percent"]))
    report.note("BIO1 %.2f..%.2f C, BIO12 %.1f..%.1f mm" % (
        bio[0].min(), bio[0].max(), bio[2].min(), bio[2].max()))
    # Corroboration only (the parent brief: 6b is a low-cost extra, not a requirement).
    # No check demands 4 ordinals or 4 variants here -- at a spacing this coarse the
    # published 30 m recipe smooths the terrain, so a degenerate result is reported as
    # measured instead of being asserted away or "fixed" by tuning.
    report.check("the co-located joint accounting is consistent (slots sum to counted points)",
                 int(joint.sum()) == int(dominant.size),
                 "%d == %d" % (int(joint.sum()), int(dominant.size)))
    report.note("VALIDITY: %s (counted %d points at %.0f m spacing)" % (
        "usable" if len(ordinal_present) > 1 else
        "DEGENERATE -- the published 30 m recipe collapses to one ordinal at this coarse "
        "spacing, so this grid is NOT a valid co-located probe", dominant.size, spacing))
    payload = {"seed": seed, "spacing_m": spacing, "columns": columns, "rows": rows,
               "points_counted": int(dominant.size), "halo_trimmed": halo, "seconds": elapsed,
               "observed_ordinals": ordinal_present, "observed_variants": variant_present,
               "co_located_slots": slots, "co_located_slot_count": len(slots),
               "ordinal_counts": {str(o): _counts(dominant, LANDFORM_COUNT)[o]
                                  for o in range(LANDFORM_COUNT)},
               "variant_counts": {str(v): _counts(bands, VARIANT_COUNT)[v]
                                  for v in range(VARIANT_COUNT)},
               "BIO1_c": [float(bio[0].min()), float(bio[0].max())],
               "BIO12_mm": [float(bio[2].min()), float(bio[2].max())],
               "recipe": "METRIC_30M_RECIPE_V1 as published, elevation from "
                         "coarse_condition_field, sea level 126 m",
               "valid_probe": len(ordinal_present) > 1,
               "optional_low_cost_corroboration": True,
               "scope": "one strip %.0f km wide by one latitude period long at one seed; "
                        "reported as observed, no universal claim" % (x_span_m / 1000.,)}
    report.section("joint_grid_observation", payload)
    return payload


def biome_resources(report, root, slots):
    """Read-only existence check that every direct-product slot has a real json."""
    report.header("7. BIOME RESOURCES (%s)" % (BIOME_DIR_RELATIVE.as_posix(),))
    directory = root / BIOME_DIR_RELATIVE
    entries = [{"biome": slot["biome"], "palette_index": slot["palette_index"],
                "exists": (directory / (slot["biome"] + ".json")).is_file()} for slot in slots]
    present = sum(1 for entry in entries if entry["exists"])
    report.check("all 16 palette names have a biome json on disk (read-only check)",
                 present == len(slots), "%d/%d" % (present, len(slots)))
    payload = {"directory": BIOME_DIR_RELATIVE.as_posix(), "present": present,
               "total": len(slots), "entries": entries}
    report.section("biome_resources", payload)
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the p5.3 biome-climate distribution.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help="JSON report path (relative paths resolve against the repo root)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--columns", type=int, default=DEFAULT_COLUMNS)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--x-span-m", type=float, default=DEFAULT_X_SPAN_M)
    parser.add_argument("--z-span-m", type=float, default=DEFAULT_Z_SPAN_M)
    parser.add_argument("--joint-spacing-m", type=float, default=JOINT_SPACING_M,
                        help="spacing of the co-located large grid (section 6b); the run is "
                             "skipped when 30 km / spacing * period / spacing exceeds 2**20 cells")
    parser.add_argument("--joint-x-span-m", type=float, default=JOINT_X_SPAN_M)
    parser.add_argument("--skip-joint-grid", action="store_true",
                        help="skip section 6b, the co-located large-grid generation")
    parser.add_argument("--skip-period-grid", action="store_true",
                        help="skip the extra >= 1 latitude period cross-check grid")
    args = parser.parse_args(argv)

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output

    report = Report()
    print("metric biome/climate distribution (p5.3) -- read-only")
    print("repo root: %s" % (ROOT,))
    print("contract: .scratch/river-infinite-world/biome-climate-spec.md "
          "(spec 6.3 method, spec 7.1 acceptance)")
    print("normalization constants from metric_biome_climate: "
          "TEMPERATURE_OFFSET_C=%.1f TEMPERATURE_SPAN_C=%.1f PRECIPITATION_SPAN_MM=%.1f" % (
              TEMPERATURE_OFFSET_C, TEMPERATURE_SPAN_C, PRECIPITATION_SPAN_MM))

    landform = landform_edge(report, ROOT)
    climate = climate_edge(report, args.seed, args.columns, args.rows,
                           args.x_span_m, args.z_span_m)
    probe = contract_probe_reproduction(report, args.seed)
    saturation = saturation_evidence(report, args.seed)
    period = None
    phase = None
    if not args.skip_period_grid:
        period = _period_cross_check(report, args.seed)
        phase = phase_cross_check(report, args.seed)
        report.header("3e. DENSER ROBUSTNESS GRID (same spans, twice the resolution)")
        dense_x, dense_z = _climate_lattice(DENSE_COLUMNS, DENSE_ROWS, DENSE_X_SPAN_M,
                                            float(LATITUDE_PERIOD_M))
        _, _, _, _, dense_bands = _climate_observations(args.seed, dense_x, dense_z)
        dense_counts = _counts(dense_bands, VARIANT_COUNT)
        report.note("points %d, z span %.1f m = %.4f periods, counts %s, shares %s" % (
            dense_bands.size, float(np.ptp(dense_z)),
            float(np.ptp(dense_z)) / LATITUDE_PERIOD_M, dense_counts,
            [round(_percent(dense_counts[v], dense_bands.size), 2) for v in range(VARIANT_COUNT)]))
        report.check("the denser robustness grid also shows all 4 climate variants",
                     sorted(int(v) for v in np.unique(dense_bands)) == list(range(VARIANT_COUNT)))
        dense = {"columns": DENSE_COLUMNS, "rows": DENSE_ROWS, "x_span_m": DENSE_X_SPAN_M,
                 "z_span_m": float(LATITUDE_PERIOD_M), "points": int(dense_bands.size),
                 "counts": {str(v): dense_counts[v] for v in range(VARIANT_COUNT)},
                 "shares_percent": {str(v): _percent(dense_counts[v], dense_bands.size)
                                    for v in range(VARIANT_COUNT)}}
    else:
        dense = None

    product = direct_product(report, landform["observed_ordinals"], climate["observed_variants"])
    bounds = palette_bounds(report)
    window = window_observation(report, ROOT)
    joint = None
    if not args.skip_joint_grid:
        joint = joint_grid_observation(report, args.seed, args.joint_spacing_m,
                                       args.joint_x_span_m)
    resources = biome_resources(report, ROOT, product["slots"])

    payload = {
        "schema": SCHEMA,
        "method": "contract 6.3: two independent marginal edges plus their direct product, "
                  "with co-located joint observations reported separately",
        "passed": report.passed,
        "checks": report.checks,
        "inputs": {"seed": args.seed, "columns": args.columns, "rows": args.rows,
                   "x_span_m": args.x_span_m, "z_span_m": args.z_span_m,
                   "joint_spacing_m": args.joint_spacing_m,
                   "joint_x_span_m": args.joint_x_span_m},
        "landform_marginal_edge": landform,
        "climate_marginal_edge": climate,
        "clip": climate["clip"],
        "contract_probe_reproduction": probe,
        "saturation_evidence": saturation,
        "period_cross_check": period,
        "phase_cross_check": phase,
        "dense_robustness_grid": dense,
        "direct_product": product,
        "palette_bounds": bounds,
        "window_observation": window,
        "joint_grid_observation": joint,
        "biome_resources": resources,
        "claims": {
            "co_located_joint_observation": "only the grids in sections 6a and 6b were observed "
                                             "co-located; the slot count seen together is "
                                             "reported there",
            "direct_product_reachability": "all 16 palette slots are reachable as a direct "
                                           "product of the two measured marginal edges; this "
                                           "is not a co-located observation of 16 slots",
            "no_universal_claim": "no claim is made that no window anywhere can hold all 16 "
                                   "slots; the 15.27 km window result is a sample fact",
        },
        "normalization_constants": {"TEMPERATURE_OFFSET_C": TEMPERATURE_OFFSET_C,
                                    "TEMPERATURE_SPAN_C": TEMPERATURE_SPAN_C,
                                    "PRECIPITATION_SPAN_MM": PRECIPITATION_SPAN_MM},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
                      encoding="utf-8")

    report.header("result")
    print("JSON report written to %s" % (output,))
    print("landform marginal edge: %s" % (landform["shares_percent"],))
    print("climate  marginal edge: %s" % (climate["shares_percent"],))
    print("direct product:         %d/16 slots reachable" % (product["slot_count"],))
    print("co-located, 15.27 km window: %d/16 slots %s" % (
        window["co_located_slot_count"],
        [slot["biome"] for slot in window["co_located_slots"]]))
    clip_facts = climate["clip"]["measured"]
    print("clip ends measured: temperature==0. %s, temperature==1. %s, rain==0. %s "
          "(physically unreachable: v2 precipitation minimum 100 mm), rain==1. %s "
          "(seam reachable on wider x lattices, section 3d)" % (
              "reached" if clip_facts["temperature_0"] else "not reached",
              "reached" if clip_facts["temperature_1"] else "not reached",
              "reached" if clip_facts["rain_0"] else "NOT reached",
              "reached" if clip_facts["rain_1"] else "not reached here"))
    if joint is not None:
        print("co-located, large grid:      %d/16 slots" % (joint["co_located_slot_count"],))
    if report.passed:
        print("RESULT: PASS -- %d checks passed; 16/16 palette slots reachable in the "
              "direct-product sense" % (len(report.checks),))
        return 0
    failed = [item["check"] for item in report.checks if not item["passed"]]
    print("RESULT: FAIL -- %d check(s) failed: %s" % (len(failed), "; ".join(failed)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
