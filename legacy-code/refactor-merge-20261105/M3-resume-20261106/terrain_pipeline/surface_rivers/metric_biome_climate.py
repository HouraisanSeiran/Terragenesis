"""Python single source of truth for the Minecraft biome-selection rules (P5.2).

A **read-only migration** of three Java rules into Python: the climate variant,
the landform ordinal and the palette index. It touches no Java file, no
`src/main/**` and no biome json, and it neither reads nor modifies
`metric_climate_refinement.py` (v2, P4 delivered) or `metric_noise_forcing.py`
(v1, frozen): those own `BIO1_4_12_15` and are consumed by the caller, never
copied here.

Migrated Java facts (frozen verbatim, contract `biome-climate-spec.md` §1):

- §1.1 the climate bands, and the only occurrence of the three thresholds —
  `src/main/java/com/remotemountains/core/Landscape.java:7-9`:

      public int variant(){return temperature<.28?0:rain<.34?1:rain>.64?3:2;}

  Expanded (the order is the semantics and is never reordered):

      if temperature < .28: return 0        # cold
      elif rain < .34:      return 1        # dry
      elif rain > .64:      return 3        # wet
      else:                 return 2        # temperate

  The three boundary behaviours the migration must keep verbatim: (1) the
  temperature band has the veto — `temperature < .28` is 0 whatever `rain` is,
  so `(.1, .9)` is 0 and never 3; (2) `rain < .34` is tested before
  `rain > .64`, so `.34 <= rain <= .64` is 2, and both comparisons are **strict**,
  i.e. `rain == .34` and `rain == .64` are both 2; (3) `temperature == .28` is
  **not** 0.

  **资料出处：无**。三个阈值（`.28` / `.34` / `.64`）全仓只此一处，无 Köppen / Holdridge 之类引用 = **纯工程假设**，与 P4 已声明的同类义务一致。

  That sentence is deliberately kept on one unwrapped line, because
  §1.1 / §4 item 5 require it verbatim rather than re-flowed.

- §1.2 the landform ordinals —
  `src/main/java/com/remotemountains/core/Landform.java:3-9`: the declaration
  order is the ordinal, i.e. 0 INSELBERG / 1 RIFT / 2 KARST / 3 PILLARS.
  The Python side needs no extra mapping table: `terrain_pipeline/metric_region.py:128-129`
  stacks the four region weights as plain / hill / plateau / mountain and
  `:140` takes `np.argmax` over them, so `dominant_type` 0/1/2/3 is numerically
  the same as Java's `Landform.ordinal` 0/1/2/3 — `docs/metric-minecraft-consumer.md:34`
  states the correspondence verbatim (`plain->inselberg, hill->rift,
  plateau->karst, mountain->pillars`). That correspondence is the ordinal source
  a distribution run must use, and no translation table is introduced here.

- §1.3 the palette index —
  `src/main/java/com/remotemountains/world/TerrainBiomeSource.java:29-35`:
  `index = landform_ordinal * 4 + variant`, `index` in `[0, 15]`, landform as
  the outer and climate as the inner axis. The 16-name table below is that same
  table, with the resource names taken verbatim from
  `tools/create_resources.py:19` (`types=['inselberg','rift','karst','pillars']`,
  `climates=['snowy','arid','temperate','humid']`), and the size 16 mirrors the
  Java assertions (`TerrainBiomeSource.java:20` "Expected 16 climate/landform
  biomes", `RemoteGenerator.java:56` "Expected four climates for each of four
  landforms").

- §2.1 the normalization, verbatim from the live Java adapters —
  `src/main/java/com/remotemountains/diffusion/DiffusionTerrainSource.java:18`,
  identical at `BakedTerrainSource.java:43`:

      temperature = clamp((BIO1_c + 12) / 45, 0, 1)
      rain        = clamp( BIO12_mm     / 2200, 0, 1)

  The three constants are the numbers those adapters already use, not a new
  choice here and not a fit to any distribution (§2.2, §3.2). `Noise.clamp(v,a,b)`
  is `Math.max(a, Math.min(b, v))` (`Noise.java:16`), which is what `np.clip`
  computes here.

The normalized result is a **"normalized biome-selection coordinate, not a physical climate quantity"** (quoted and kept on one unwrapped line because §3.1 / §4 item 5 require it verbatim).
Neither returned number is a temperature, a
precipitation amount, or a member of a real climate classification (Köppen and
Holdridge are unused). The names `temperature` / `rain` are kept because the
migration renames nothing, but the values only ever select one of the 16
existing palette entries; §3.1 of the contract states this verbatim.

Argument conventions (P4's scalar/array single-path style; no window, no cache,
no per-call state): scalars and numpy arrays are both accepted, and the two
`(temperature, rain)` arguments broadcast onto one common grid. The integer
functions return an `int64` scalar (`np.int64`) for a 0-d query and an `int64`
array for an array query, so the declared `int64` holds on both paths;
`climate_coordinates` returns Python floats for a 0-d query and `float64` arrays
otherwise, matching P4's `float(value)` convention. No finiteness guard is added
to `variant` / `climate_coordinates`: the mapping must stay literally equal to
the Java expressions, and both then give the same answer as Java for non-finite
input (`NaN` comparisons are all false, so `variant` is 2, and `clamp` passes
`NaN` through).

Declared interface seam (§3.3, registered rather than hidden): the normalization
upper bound is 2200 mm while v2 annual precipitation may reach 3200 mm
(`metric_climate_refinement.py:64-66`), so the whole `[2200, 3200]` mm stretch
maps to `rain == 1.`. Banding therefore has resolution only below 2200 mm, and
`rain == 1.` guarantees only `> .64` (the wet band), never "exactly 2200 mm".
`temperature == 1.` likewise means `BIO1 >= 33 C`.

Out of scope here (§9 of the contract): the Java/Mod wiring
(`MetricProcessedTerrainSource.java:22` `ADAPTER_CLIMATE`), the 16 biome json
files, what a band looks like (vegetation, ore, mobs), and any connection of
these coordinates to the river network or runoff.
"""

import numpy as np


# §2.1 normalization constants — verbatim from the live Java adapters, the numbers
# in use at `DiffusionTerrainSource.java:18` / `BakedTerrainSource.java:43`.
TEMPERATURE_OFFSET_C = 12.
TEMPERATURE_SPAN_C = 45.
PRECIPITATION_SPAN_MM = 2200.

# §1.1 band thresholds — verbatim from `Landscape.java:8` (`<.28`, `<.34`, `>.64`),
# all three strict. This band rule is defined in exactly one Python place (here);
# the Java original is the one other place (see the module docstring). The bare
# numbers do occur elsewhere in the repository for unrelated quantities (widths,
# colours, byte values), which is why the rule, not the literal, is the frozen unit.
TEMPERATURE_LOW = .28
RAIN_DRY = .34
RAIN_WET = .64

# The band indices themselves, in the order the Java expression returns them.
VARIANT_COLD = 0
VARIANT_DRY = 1
VARIANT_TEMPERATE = 2
VARIANT_WET = 3
VARIANT_COUNT = 4

# §1.2 landform ordinals — `Landform.java:3-9` declaration order. Do not reorder:
# `dominant_type` from `terrain_pipeline/metric_region.py:140` and the Minecraft
# palette rows are numerically the same 0/1/2/3.
INSELBERG = 0
RIFT = 1
KARST = 2
PILLARS = 3
LANDFORM_COUNT = 4
LANDFORM_ORDINALS = {"inselberg": INSELBERG, "rift": RIFT, "karst": KARST, "pillars": PILLARS}
LANDFORM_NAMES = ("inselberg", "rift", "karst", "pillars")

# §1.3 variant names — `tools/create_resources.py:19` `climates` order, i.e. the
# inner axis of the palette. Variant 0 snowy / 1 arid / 2 temperate / 3 humid.
VARIANT_NAMES = ("snowy", "arid", "temperate", "humid")

# §1.3 the 16-name table, landform outer and climate inner, written out as the
# §1.3 table itself; `BIOME_PALETTE[palette_index(o, v)]` is the name of the pair.
BIOME_PALETTE = (
    "inselberg_snowy", "inselberg_arid", "inselberg_temperate", "inselberg_humid",
    "rift_snowy", "rift_arid", "rift_temperate", "rift_humid",
    "karst_snowy", "karst_arid", "karst_temperate", "karst_humid",
    "pillars_snowy", "pillars_arid", "pillars_temperate", "pillars_humid",
)
PALETTE_SIZE = 16


assert LANDFORM_COUNT * VARIANT_COUNT == PALETTE_SIZE, "four climates for each of four landforms"
assert len(BIOME_PALETTE) == PALETTE_SIZE, "Expected 16 climate/landform biomes"


def _broadcast_pair(first, second):
    """Put two climate arguments on one common float64 grid (single code path)."""
    try:
        return np.broadcast_arrays(np.asarray(first, np.float64), np.asarray(second, np.float64))
    except ValueError:
        raise ValueError("the two climate arguments must broadcast to a common shape")


def variant(temperature, rain):
    """§1.1 / §4 item 1: the climate band of one normalized `(temperature, rain)`.

    Literally equivalent to `Landscape.java:8`
    (`temperature<.28?0:rain<.34?1:rain>.64?3:2`), keeping the Java comparison
    order and all three of its boundary behaviours: the temperature band vetoes
    (`(.1, .9)` is 0, never 3), `.34 <= rain <= .64` is 2, and the three
    comparisons are strict, so `temperature == .28` is not 0 while `rain == .34`
    and `rain == .64` are 2.

    The method is the Java ternary chain read as an assignment sequence: start at
    the `else` value 2, let `rain < .34` set 1, let `rain > .64` set 3, and let
    `temperature < .28` overwrite the result with 0 last, which is exactly the
    veto the Java expression performs by testing temperature first.

    Both arguments accept scalars or numpy arrays and broadcast onto a common
    grid; a 0-d query returns an `int64` scalar, an array query an `int64` array.
    Non-finite input is not rejected, so `NaN` lands in band 2 exactly as Java's
    comparisons would (declared in the module docstring).
    """
    t, r = _broadcast_pair(temperature, rain)
    band = np.full(t.shape, VARIANT_TEMPERATE, np.int64)
    band = np.where(r < RAIN_DRY, VARIANT_DRY, band)
    band = np.where(r > RAIN_WET, VARIANT_WET, band)
    band = np.where(t < TEMPERATURE_LOW, VARIANT_COLD, band)
    return band[()] if band.ndim == 0 else band


def climate_coordinates(BIO1_c, BIO12_mm):
    """§2.1 / §4 item 4: normalized `(temperature, rain)` from BIO1 and BIO12.

        temperature = clip((BIO1_c + 12) / 45, 0., 1.)
        rain        = clip( BIO12_mm     / 2200, 0., 1.)

    The three constants are the module-level ones above, which are the live Java
    adapter numbers (`DiffusionTerrainSource.java:18`), and `clip` mirrors
    `Noise.clamp` (`Noise.java:16`). Both ends of the clip are reachable: every
    `BIO1 <= -12 C` gives `0.` and every `BIO1 >= 33 C` gives `1.`, likewise for
    BIO12 at `0.` / `2200 mm` and above.

    Neither returned number is a physical quantity — together they are a
    normalized biome-selection coordinate (module docstring, contract §3.1).
    Scalars or arrays are accepted on one path: a 0-d query returns a pair of
    Python floats, an array query a pair of `float64` arrays. The §3.3 saturation
    seam above 2200 mm is documented, not hidden.
    """
    t, p = _broadcast_pair(BIO1_c, BIO12_mm)
    temperature = np.clip((t + TEMPERATURE_OFFSET_C) / TEMPERATURE_SPAN_C, 0., 1.)
    rain = np.clip(p / PRECIPITATION_SPAN_MM, 0., 1.)
    if temperature.ndim == 0:
        return float(temperature), float(rain)
    return temperature, rain


def _integer_index(value, name, upper):
    """Validate one integer index argument and return it as an `int64` array.

    Integer dtype is required (a float index would silently truncate) and the
    value must already be inside `0..upper`: out of range raises instead of being
    clamped, the same way Java's `palette.get(...)` throws and the 16-item
    assertion at `TerrainBiomeSource.java:20` guards the palette.
    """
    array = np.asarray(value)
    if array.dtype == np.bool_ or not np.issubdtype(array.dtype, np.integer):
        raise ValueError("integer %s required (got dtype %s)" % (name, array.dtype))
    if array.size and (array.min() < 0 or array.max() > upper):
        raise ValueError("%s outside the frozen 0..%d range" % (name, upper))
    return array.astype(np.int64)


def palette_index(landform_ordinal, variant):
    """§1.3 / §4 item 3: the palette index `landform_ordinal * 4 + variant`.

    `index` lies in `[0, 15]` (`PALETTE_SIZE` = 16 = 4 landforms x 4 variants) and
    indexes `BIOME_PALETTE`. Out-of-range input raises `ValueError` and is never
    clamped, matching the Java gate (`palette.get` throws, `TerrainBiomeSource.java:20`
    asserts 16 entries). Integer dtype is required for both arguments; scalars are
    validated directly, arrays elementwise, and the result is `int64` on both
    paths.

    The second parameter carries the contract's name and shadows this module's
    `variant()` function inside the body only, where it is used as a value.
    """
    ordinal = _integer_index(landform_ordinal, "landform ordinal", LANDFORM_COUNT - 1)
    band = _integer_index(variant, "variant", VARIANT_COUNT - 1)
    try:
        index = ordinal * VARIANT_COUNT + band
    except ValueError:
        raise ValueError("landform ordinal and variant must broadcast to a common shape")
    return index[()] if index.ndim == 0 else index
