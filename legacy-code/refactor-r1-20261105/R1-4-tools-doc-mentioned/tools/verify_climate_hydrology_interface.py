"""Read-only acceptance for the climate-to-hydrology interface (P3.2).

Every check recomputes from the source functions; nothing is read back from a saved
product, and no module is imported for its answer. The seven invariants of
`.scratch/infinite-world-geography/climate-hydrology-interface-spec.md` section 4 are
asserted one by one, with the measured values printed next to each verdict so a
reviewer can compare against the contract's numbers.

Deliberate non-claims enforced here:
- the grid-vs-point annual gap is the v1 layer's own property and must NOT be asserted
  to vanish (section 4.1);
- the runoff ledger is a diagnostic independent-cell quantity and must NOT be
  described as having entered a river network (section 4.6);
- `source_sha256` is the digest of the producing metadata (climate parameters AND grid
  geometry), so it is NOT a cross-grid climate identity (section 3).

Usage:
    python tools/verify_climate_hydrology_interface.py [--output PATH]
Report defaults to `.scratch/infinite-world-geography/climate-hydrology-acceptance.json`.
"""

import argparse
import json
import os

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity
from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.surface_rivers.metric_climate_refinement import (
    RefinedClimateParameters, grid_rainfall_v2, sample_climate_v2)
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_noise_forcing import (
    MONTH_EDGES_S, NoiseClimateParameters, grid_rainfall)
from terrain_pipeline.surface_rivers.metric_runoff import runoff_from_forcing


SEED = 20261020
SPACING_M = 10000.0
ORIGIN = (0.0, 0.0)
ULP_TOLERANCE = 8 * np.spacing(1.0)
UNIFORM_STEPS = 12
UNIFORM_INTERVAL_S = 30.0 * 86400.0


class Ledger:
    """Collects verdicts so one failure cannot hide the rest of the run."""

    def __init__(self):
        self.checks = []
        self.values = {}

    def check(self, label, ok, detail=""):
        self.checks.append({"label": label, "ok": bool(ok), "detail": str(detail)})
        print(("OK   " if ok else "FAIL ") + label + ("  [" + str(detail) + "]" if detail else ""))
        return bool(ok)

    def value(self, key, value):
        self.values[key] = value
        return value


def terrain_grid(shape, spacing=SPACING_M, origin=ORIGIN, drop=3.0):
    """A plain descending ramp: routing is not under test here, only the water ledger."""
    heights = 100.0 - np.arange(shape[0] * shape[1], dtype=np.float64).reshape(shape) * drop
    return TerrainGrid(heights, np.ones(shape, bool), float(origin[0]), float(origin[1]),
                       spacing, spacing, "generated_terrain", "p32_acceptance", "a" * 64)


def coordinates(shape, spacing=SPACING_M, origin=ORIGIN):
    rows, columns = np.indices(shape)
    return (float(origin[0]) + columns * spacing, float(origin[1]) + rows * spacing)


def uniform_edges(steps=UNIFORM_STEPS, interval_s=UNIFORM_INTERVAL_S):
    return np.arange(steps + 1, dtype=np.float64) * interval_s


def monthly_rainfall(shape=(3, 3), spacing=SPACING_M, origin=ORIGIN, parameters=None,
                     subsamples=1):
    return grid_rainfall_v2(SEED, origin_xz_m=origin, shape_zx=shape, spacing_m=spacing,
                            time_edges_s=MONTH_EDGES_S.copy(), parameters=parameters,
                            spatial_subsamples=subsamples)


def run(ledger):
    parameters = RefinedClimateParameters(base=NoiseClimateParameters())
    v1_identity = parameters.base_parameter_identity_sha256
    v2_identity = parameters.identity_sha256
    ledger.value("v1_parameter_identity_sha256", v1_identity)
    ledger.value("v2_parameter_identity_sha256", v2_identity)

    print("== 1. unit conservation and independent recomputation")
    edges = uniform_edges()
    shape = (4, 4)
    forcing, forcing_metadata = grid_rainfall_v2(
        SEED, origin_xz_m=ORIGIN, shape_zx=shape, spacing_m=SPACING_M,
        time_edges_s=edges, parameters=parameters, spatial_subsamples=1)
    terrain = terrain_grid(shape)
    result = runoff_from_forcing(terrain, forcing, parameters=RunoffParameters())
    totals = result["ledger"]["totals_m3"]
    native = result["native_result"]

    hours = forcing.interval_seconds / 3600.0
    manual_depth = (forcing.rain_mm_h * hours[:, None, None]).sum(axis=0)
    manual_volume = float((manual_depth * (terrain.cell_area_m2 / 1000.0)).sum())
    ledger_volume = float(totals["rain_volume_m3"])
    relative = abs(manual_volume - ledger_volume) / abs(ledger_volume)
    ledger.value("ledger_rain_volume_m3", ledger_volume)
    ledger.value("manual_rain_volume_m3", manual_volume)
    ledger.value("rain_volume_relative_difference", relative)
    ledger.check("the runoff rain volume is reproducible from the forcing by definition",
                 relative < 1e-12, "relative difference %.3e" % relative)

    per_step_saved = native["rain_volume_m3"]
    cell_ids = result["valid_cell_ids"]
    per_step_manual = (forcing.rain_mm_h.reshape(forcing.rain_mm_h.shape[0], -1)[:, cell_ids]
                       * hours[:, None]) * (terrain.cell_area_m2 / 1000.0)
    ledger.check("the per-interval rain volume is bit-identical to the recomputation",
                 np.array_equal(per_step_saved, per_step_manual),
                 "max absolute difference %.3e" % float(np.abs(per_step_saved - per_step_manual).max()))
    residual = float(np.abs(native["balance_residual_m3"]).max())
    ledger.value("max_abs_balance_residual_m3", residual)
    ledger.check("the solved water balance residual is negligible against the totals",
                 residual < 1e-6 * max(1.0, abs(ledger_volume)), "%.3e m3" % residual)

    # The grid-vs-point gap is the v1 layer's own property; v2 must not enlarge it.
    print("== 1b. the grid/point annual gap belongs to v1 and must not grow in v2")
    point_shape = (3, 3)
    px, pz = coordinates(point_shape)
    v2_forcing, _ = monthly_rainfall(point_shape, parameters=parameters)
    v1_forcing, _ = grid_rainfall(SEED, origin_xz_m=ORIGIN, shape_zx=point_shape,
                                  spacing_m=SPACING_M, time_edges_s=MONTH_EDGES_S.copy(),
                                  parameters=parameters.base, spatial_subsamples=1)
    v2_point = sample_climate_v2(SEED, px, pz, parameters=parameters)
    v1_point = __import__("terrain_pipeline.surface_rivers.metric_noise_forcing",
                          fromlist=["sample_climate"]).sample_climate(
        SEED, px, pz, parameters=parameters.base)
    v2_grid_annual = v2_forcing.rainfall_depth_mm.sum(axis=0)
    v1_grid_annual = v1_forcing.rainfall_depth_mm.sum(axis=0)
    v2_point_annual = v2_point["annual_precipitation_mm"]
    v1_point_annual = np.sum(v1_point["monthly_precipitation_mm"], axis=0)
    v2_gap = float(np.abs(np.abs(v2_grid_annual / v2_point_annual - 1.0)).max())
    v1_gap = float(np.abs(np.abs(v1_grid_annual / v1_point_annual - 1.0)).max())
    ledger.value("v2_grid_point_annual_relative_gap", v2_gap)
    ledger.value("v1_grid_point_annual_relative_gap", v1_gap)
    ledger.check("the grid/point annual gap is a v1 property, not a v2 regression",
                 v2_gap <= v1_gap + 1e-9, "v2 %.6e vs v1 %.6e" % (v2_gap, v1_gap))
    ledger.check("the realized annual precipitation equals the twelve months bit for bit",
                 np.array_equal(v2_point["BIO1_4_12_15"][2],
                                np.sum(v2_point["monthly_precipitation_mm"], axis=0)))

    print("== 2. one single precipitation product in grid and point form")
    grid_ratio = v2_forcing.rain_mm_h.sum(axis=0) / v1_forcing.rain_mm_h.sum(axis=0)
    point_multiplier = v2_point["precipitation_multiplier"]
    difference = float(np.abs(grid_ratio - point_multiplier).max())
    ledger.value("grid_vs_point_multiplier_max_abs_difference", difference)
    ledger.check("the grid rainfall uses the same multiplier product as the point query",
                 difference <= ULP_TOLERANCE, "max absolute difference %.3e" % difference)
    ledger.check("the multiplier never falls to zero or below",
                 bool((point_multiplier > 0.0).all() and (grid_ratio > 0.0).all()))

    print("== 3. identity honesty")
    # Measured rule (probe temp://scratch/p32_probe4.py): the producer digests its own
    # metadata **with the digest field removed**, so the summary is not self-referential.
    #   identity({}, metadata)                          != source_sha256
    #   identity({}, metadata without the digest field) == source_sha256
    without_digest = {key: value for key, value in forcing_metadata.items()
                      if key != "source_identity_sha256"}
    recomputed = identity({}, without_digest)
    self_referential = identity({}, forcing_metadata)
    ledger.value("forcing_source_sha256", forcing.source_sha256)
    ledger.value("recomputed_identity_sha256", recomputed)
    ledger.check("source_sha256 equals a fresh digest of the metadata without its own digest field",
                 forcing.source_sha256 == recomputed,
                 "recomputed %s" % recomputed[:16])
    ledger.check("the digest field is genuinely excluded, so the summary is not self-referential",
                 self_referential != forcing.source_sha256,
                 "digesting the field back in gives %s" % self_referential[:16])
    ledger.check("the metadata publishes the digest it computed for itself",
                 forcing_metadata.get("source_identity_sha256") == forcing.source_sha256)
    ledger.check("source_id distinguishes the terrain-refined producer",
                 forcing.source_id == "synthetic_noise_terrain_climate_v2", forcing.source_id)
    ledger.check("the metadata carries the v2 parameter identity verbatim",
                 forcing_metadata.get("parameter_identity_sha256") == v2_identity)
    ledger.check("the metadata carries the reused v1 identity verbatim",
                 forcing_metadata.get("base_parameter_identity_sha256") == v1_identity)
    ledger.check("the rainfall composition names both layers",
                 forcing_metadata.get("rainfall_composition", "").startswith("v1_interval_mean"))
    v1_forcing_for_id, v1_metadata = grid_rainfall(
        SEED, origin_xz_m=ORIGIN, shape_zx=(2, 2), spacing_m=SPACING_M,
        time_edges_s=uniform_edges(2), parameters=parameters.base, spatial_subsamples=1)
    ledger.check("a v1 field cannot claim the terrain-refined producer",
                 v1_forcing_for_id.source_id == "synthetic_noise_climate" and
                 v1_forcing_for_id.source_sha256 != forcing.source_sha256)
    ledger.check("the v1 metadata still reports the frozen v1 parameter identity",
                 v1_metadata.get("parameter_identity_sha256") == v1_identity)

    print("== 4. window and order independence")
    # A finite, named set rather than an unbounded "any window": three window shapes
    # sharing world-anchored cells, two call orders, and a shuffled batch.
    big_shape = (4, 4)
    inner_origin = (SPACING_M, SPACING_M)
    inner_shape = (3, 3)
    big_forcing, _ = monthly_rainfall(big_shape, parameters=parameters)
    inner_forcing, _ = monthly_rainfall(inner_shape, origin=inner_origin, parameters=parameters)
    shifted_origin = (2.0 * SPACING_M, SPACING_M)
    shifted_forcing, _ = monthly_rainfall(inner_shape, origin=shifted_origin,
                                          parameters=parameters)
    shared_ok = np.array_equal(big_forcing.rain_mm_h[:, 1:, 1:], inner_forcing.rain_mm_h)
    ledger.check("two world-anchored windows agree bit for bit on their shared cells", shared_ok,
                 "shared cells %d" % inner_forcing.rain_mm_h[:, 0, 0].size)
    # The shifted window samples x = 2S, 3S, 4S while the inner one samples x = S, 2S, 3S:
    # two of the three columns are shared, so only those may be compared cell for cell.
    shifted_shared = np.array_equal(shifted_forcing.rain_mm_h[:, :, 0:2],
                                    inner_forcing.rain_mm_h[:, :, 1:3])
    ledger.check("a third window offset along one axis agrees bit for bit on its shared columns",
                 shifted_shared, "2 shared columns of a 3x3 lattice")
    repeat_forcing, _ = monthly_rainfall(big_shape, parameters=parameters)
    ledger.check("an identical query repeated in a separate call agrees bit for bit",
                 np.array_equal(big_forcing.rain_mm_h, repeat_forcing.rain_mm_h))
    batch_x, batch_z = coordinates(big_shape)
    shuffled_x = np.ascontiguousarray(batch_x.ravel()[::-1])
    shuffled_z = np.ascontiguousarray(batch_z.ravel()[::-1])
    shuffled = sample_climate_v2(SEED, shuffled_x, shuffled_z, parameters=parameters)
    straight = sample_climate_v2(SEED, batch_x.ravel(), batch_z.ravel(), parameters=parameters)
    ledger.check("reversing the query order reproduces the same answers bit for bit",
                 np.array_equal(shuffled["monthly_precipitation_mm"][:, ::-1],
                                straight["monthly_precipitation_mm"]))
    single_x, single_z = float(px.ravel()[4]), float(pz.ravel()[4])
    single = sample_climate_v2(SEED, single_x, single_z, parameters=parameters)
    arrayed = sample_climate_v2(SEED, px.ravel()[4:5], pz.ravel()[4:5], parameters=parameters)
    # The scalar query returns shape (12,) and the one-point array query shape (12, 1);
    # only the values are comparable, so both sides are flattened first.
    ledger.check("a lone point answers exactly as it does inside an array query",
                 np.array_equal(np.asarray(single["monthly_precipitation_mm"]).reshape(-1),
                                np.asarray(arrayed["monthly_precipitation_mm"]).reshape(-1)))

    print("== 5. time edge consistency")
    ledger.check("the interval count matches the time edges minus one",
                 forcing.rain_mm_h.shape[0] == forcing.time_seconds.size - 1,
                 "%d intervals, %d edges" % (forcing.rain_mm_h.shape[0], forcing.time_seconds.size))
    ledger.check("the physical time edges strictly increase from zero",
                 bool(forcing.time_seconds[0] >= 0.0) and bool((np.diff(forcing.time_seconds) > 0.0).all()))
    ledger.check("the declared spatial extent of the forcing matches the terrain",
                 forcing.rain_mm_h.shape[1:] == terrain.valid_mask.shape)

    print("== 6. the water ledger must not over-claim")
    metadata = result["metadata"]
    ledger.check("the runoff result declares itself diagnostic rather than publishable",
                 metadata["status"] == "diagnostic_runoff" and metadata["publishable"] is False)
    ledger.check("the runoff result denies channel hydraulics",
                 metadata["hydraulic_ready"] is False and metadata["natural_outlet_verified"] is False)
    ledger.check("the local discharge is declared as not river routed",
                 metadata["q_semantics"] == "interval_average_local_release_not_river_routed",
                 metadata["q_semantics"])
    ledger.check("the ledger reports the forcing identity it actually consumed",
                 metadata["forcing_identity_sha256"] == forcing.identity_sha256)
    ledger.check("the ledger reports the terrain identity it actually consumed",
                 metadata["terrain_identity_sha256"] == terrain.identity_sha256)

    print("== 7. refusal rather than guessing")
    month_intervals = MONTH_EDGES_S.copy()
    ledger.check("the raw monthly climate edges are genuinely non-uniform",
                 not np.all(np.diff(month_intervals) == np.diff(month_intervals)[0]),
                 "%d intervals" % np.diff(month_intervals).size)
    try:
        runoff_from_forcing(terrain, forcing_v1_monthly(parameters), parameters=RunoffParameters())
        ledger.check("a non-uniform forcing is refused by the fixed-step solver", False,
                     "no error raised")
    except ValueError as error:
        ledger.check("a non-uniform forcing is refused by the fixed-step solver",
                     "uniform forcing intervals" in str(error), str(error))
    for label, call in (
        ("non-increasing time edges",
         lambda: grid_rainfall_v2(SEED, origin_xz_m=ORIGIN, shape_zx=(2, 2),
                                  spacing_m=SPACING_M, parameters=parameters,
                                  spatial_subsamples=1,
                                  time_edges_s=np.array([0.0, 100.0, 50.0, 200.0]))),
        ("non-positive grid spacing",
         lambda: grid_rainfall_v2(SEED, origin_xz_m=ORIGIN, shape_zx=(2, 2),
                                  spacing_m=0.0, parameters=parameters,
                                  spatial_subsamples=1, time_edges_s=uniform_edges(2))),
        ("out-of-range subdivision count",
         lambda: grid_rainfall_v2(SEED, origin_xz_m=ORIGIN, shape_zx=(2, 2),
                                  spacing_m=SPACING_M, parameters=parameters,
                                  spatial_subsamples=3, time_edges_s=uniform_edges(2))),
        ("zero-width interval",
         lambda: grid_rainfall_v2(SEED, origin_xz_m=ORIGIN, shape_zx=(2, 2),
                                  spacing_m=SPACING_M, parameters=parameters,
                                  spatial_subsamples=1,
                                  time_edges_s=np.array([0.0, 100.0, 100.0]))),
    ):
        try:
            call()
            ledger.check("refused rather than guessed: " + label, False, "no error raised")
        except ValueError as error:
            ledger.check("refused rather than guessed: " + label, True, str(error))

    print("== 8. the production wiring fact is still true")
    wiring = production_wiring_scan()
    ledger.value("production_wiring", wiring)
    ledger.check("the terrain-aware rainfall is referenced only by verifiers, tests and contracts",
                 wiring["production_files"] == [],
                 ", ".join(wiring["production_files"]) or "none")
    ledger.check("the scan is not vacuous: the known verifier references are present",
                 any("verify_biome_climate_distribution" in name for name in wiring["verifier_files"]),
                 ", ".join(wiring["verifier_files"]) or "none")

    return ledger


_TERRAIN_FOR_UNIFORM = None


def forcing_v1_monthly(parameters):
    """A v1 forcing on the real calendar edges, to show the solver refuses it."""
    global _TERRAIN_FOR_UNIFORM
    forcing, _ = grid_rainfall(SEED, origin_xz_m=ORIGIN, shape_zx=(4, 4), spacing_m=SPACING_M,
                               time_edges_s=MONTH_EDGES_S.copy(), parameters=parameters.base,
                               spatial_subsamples=1)
    return forcing


VERIFIER_PREFIXES = ("verify_", "audit_", "diagnose_", "compare_", "inspect_", "plot_",
                     "review_", "benchmark_", "probe_", "check_")
# The module that *defines* the v2 symbols obviously mentions them; it is not a consumer.
DEFINING_MODULES = ("terrain_pipeline/surface_rivers/metric_climate_refinement.py",)


def production_wiring_scan(root=None):
    """Find which files mention a v2 climate symbol; read only, no import side effects.

    A file is treated as a *verifier* rather than a production consumer when its name
    carries one of `VERIFIER_PREFIXES`, and the defining module is skipped outright.
    Both exclusions are listed in the report so a reviewer can audit them.
    """
    root = root or os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    hits = []
    for folder in ("tools", "terrain_pipeline", "diffusion"):
        base = os.path.join(root, folder)
        if not os.path.isdir(base):
            continue
        for current, _dirs, files in os.walk(base):
            if "__pycache__" in current:
                continue
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(current, name)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as handle:
                        text = handle.read()
                except OSError:
                    continue
                if "grid_rainfall_v2" in text or "sample_climate_v2" in text:
                    hits.append(os.path.relpath(path, root).replace("\\", "/"))
    hits = sorted(set(hits))
    definitions = [h for h in hits if h in DEFINING_MODULES]
    verifiers = [h for h in hits
                 if h not in definitions and os.path.basename(h).startswith(VERIFIER_PREFIXES)]
    production = [h for h in hits if h not in definitions and h not in verifiers]
    return {"all_references": hits, "defining_modules": definitions,
            "verifier_files": verifiers, "production_files": production}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=os.path.join(
        ".scratch", "infinite-world-geography", "climate-hydrology-acceptance.json"))
    arguments = parser.parse_args()
    ledger = run(Ledger())
    failures = [check for check in ledger.checks if not check["ok"]]
    passed = len(ledger.checks) - len(failures)
    report = {"checks": ledger.checks, "values": ledger.values, "passed": passed,
              "failed": len(failures), "seed": SEED, "spacing_m": SPACING_M}
    with open(arguments.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, ensure_ascii=False)
    print("== result")
    print("report written to " + os.path.abspath(arguments.output))
    print("RESULT: %s -- %d checks passed, %d failed" %
          ("PASS" if not failures else "FAIL", passed, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
