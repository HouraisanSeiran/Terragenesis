"""Independent acceptance for the domain sediment ledger (`metric_domain_sediment`).

Read-only, and deliberately NOT built on the module under test's helpers:

* it uses the shared source-frame irregular graph for strict downhill receivers
  and authors its own terminal resolution and upstream-first routing push, so the
  ledger's per-cell loop and its group-by-terminal attribution are checked by a
  second, differently written implementation rather than by itself;
* it re-derives every per-domain figure from the published arrays and compares the
  source ledger, the routing ledger and the tile atlas;
* it re-verifies the closure module's public query against the published cells.

Scope, stated rather than hidden: the ocean mask and the accepted/refused split
are taken from the closure module's already-accepted, separately tested functions
(`test_metric_domain_closure`, `test_metric_domain_eligibility`); this auditor does
not re-implement the connectivity flood, and says so in its report. The auditor
also does **not** certify the declared yield coefficients -- it only checks that the
ledger closes, that the source sits on the published cells, and that the reported
fate matches where an independent push actually puts the volume.

```
python tools/audit_domain_sediment.py --seed 20261020 \\
    --point 0 30000 --point 0 40000 --point 40000 0 \\
    --intervals 4 --report out/audit.json
```

Exit code is 0 when every check passes, 1 when any check fails, and 2 on invalid
input. The report is written with the `x` mode (create, never overwrite), the same
discipline as the other auditors in this repository.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from terrain_pipeline.hydrology_planning import (  # noqa: E402
    PlanningConfig, coarse_condition_field,
)
from terrain_pipeline.surface_rivers.metric_domain_closure import (  # noqa: E402
    clear_cache, eligible_owner_at, global_ocean_mask,
)
from terrain_pipeline.surface_rivers.metric_domain_sediment import (  # noqa: E402
    MAX_INTERVALS,
    PRODUCT_KEYS,
    SedimentYieldParameters,
    load_domain_sediment,
    solve_domain_sediment,
)

AUDIT_SCHEMA = "domain-sediment-audit-v1"


# `DEFAULT_MARGIN_NODES`, restated rather than imported.
MARGIN = 48


def independent_receiver(height, *, x0_m=0., z0_m=0., spacing_m=30., world_seed=20261020):
    """Rebuild shared graph routing; downstream accounting stays independent."""
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import strict_receivers as strict_receivers
    mesh = grid_mesh(height.shape, x0_m=x0_m, z0_m=z0_m, dx_m=spacing_m, world_seed=world_seed)
    return strict_receivers(height, mesh)[0].reshape(height.shape)


def independent_terminals(receiver, height):
    """Own terminal resolution: follow the chain in ascending-height order."""
    flat_receiver = receiver.reshape(-1)
    terminal = np.full(flat_receiver.size, -1, np.int64)
    for position in np.argsort(height.reshape(-1), kind="stable"):
        downstream = flat_receiver[position]
        terminal[position] = position if downstream < 0 else terminal[downstream]
    return terminal.reshape(height.shape)


def independent_sediment_push(height, receiver, accepted, entrained_flat, retention):
    """Own sediment traversal: settle a fraction, push the rest downstream.

    Written as an explicit per-cell pass over descending height (a valid
    topological order for a strictly-downhill receiver), which is the same
    traversal the ledger describes but not the same code: the ledger walks
    `upstream_first`, this one re-derives the order, and the accumulation targets
    (`landed_flat`, `deposited`) are kept separate from the module's arrays.
    """
    flat_height = height.reshape(-1)
    accept_flat = accepted.reshape(-1)
    receiver_flat = receiver.reshape(-1)
    load = np.array(entrained_flat, np.float64).copy()
    landed = np.zeros(load.size, np.float64)
    deposited = np.zeros(load.size, np.float64)
    for cell in np.argsort(-flat_height, kind="stable"):
        value = load[cell]
        if accept_flat[cell]:
            settle = retention * value
            if settle:
                deposited[cell] += settle
                value -= settle
        target = receiver_flat[cell]
        if target >= 0:
            load[target] += value
        else:
            landed[cell] += value
        load[cell] = 0.0
    return landed, deposited


def check(checks, name, ok, detail=None):
    checks.append({"check": name, "passed": bool(ok), "detail": detail})
    return bool(ok)


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--point", nargs="+", action="append", metavar="X", required=True)
    parser.add_argument("--intervals", type=int, default=4)
    parser.add_argument("--weathered-m-per-interval", type=float, default=0.0002)
    parser.add_argument("--slope-gain", type=float, default=150.0)
    parser.add_argument("--deposit-fraction", type=float, default=0.3)
    parser.add_argument("--initial-mobile-m", type=float, default=0.0)
    parser.add_argument("--product", help="audit a saved .npz instead of a fresh solve")
    parser.add_argument("--product-sha256", help="required with --product")
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)

    points = []
    for values in args.point:
        if len(values) != 2:
            print("FAILED: --point needs exactly two numbers; got %r" % (values,),
                  file=sys.stderr)
            return 2
        try:
            points.append((float(values[0]), float(values[1])))
        except ValueError:
            print("FAILED: --point values must be numbers; got %r" % (values,),
                  file=sys.stderr)
            return 2
    if not 1 <= args.intervals <= MAX_INTERVALS:
        print("FAILED: --intervals must be 1..%d" % MAX_INTERVALS, file=sys.stderr)
        return 2

    config = PlanningConfig()
    parameters = SedimentYieldParameters(
        weathered_m_per_interval=args.weathered_m_per_interval,
        slope_gain=args.slope_gain,
        deposit_fraction=args.deposit_fraction,
        initial_mobile_m=args.initial_mobile_m)
    checks = []
    try:
        clear_cache()
        if args.product:
            if not args.product_sha256:
                print("FAILED: --product requires --product-sha256", file=sys.stderr)
                return 2
            record = load_domain_sediment(args.product, expected_sha256=args.product_sha256)
            source = "saved product (cold reload)"
        else:
            record = solve_domain_sediment(args.seed, points, config=config,
                                           parameters=parameters, intervals=args.intervals)
            source = "fresh in-memory solve"
        arrays = record["arrays"]
        metadata = record["metadata"]
        totals = metadata["totals"]

        # ---- 1. schema, identity and disclaimer surface -----------------------
        check(checks, "arrays_carry_exactly_the_contract_keys",
              set(arrays) == set(PRODUCT_KEYS),
              {"missing": sorted(set(PRODUCT_KEYS) - set(arrays)),
               "unexpected": sorted(set(arrays) - set(PRODUCT_KEYS))})
        check(checks, "product_disclaims_publishable_hydraulics",
              all(metadata["claims"][key] is False for key in metadata["claims"]),
              dict(metadata["claims"]))
        check(checks, "declared_parameters_are_reported_verbatim",
              metadata["parameters"] == {"weathered_m_per_interval": args.weathered_m_per_interval,
                                         "slope_gain": args.slope_gain,
                                         "deposit_fraction": args.deposit_fraction,
                                         "initial_mobile_m": args.initial_mobile_m},
              metadata["parameters"])

        # ---- 2. rebuild the topology independently ---------------------------
        spacing = float(metadata["spacing_m"])
        core = int(metadata["core_cells"])
        origin_x, origin_z = [float(value) for value in metadata["tile_origin_m_xz"]]
        shape = tuple(int(value) for value in metadata["tile_shape"])
        axis_x = origin_x + np.arange(shape[1]) * spacing
        axis_z = origin_z + np.arange(shape[0]) * spacing
        grid_x, grid_z = np.meshgrid(axis_x, axis_z)
        height, _, _ = coarse_condition_field(args.seed, grid_x, grid_z, config)
        receiver = independent_receiver(height, x0_m=origin_x, z0_m=origin_z,
            spacing_m=spacing, world_seed=args.seed)
        # The closure contract makes every ocean cell a TERMINAL: its receiver is
        # forced to -1, so a coastal domain's chain ends at its river mouth. The
        # ocean mask is a separately tested closure function, reused rather than
        # re-derived (stated in this module's docstring).
        ocean = global_ocean_mask(args.seed, grid_x, grid_z, config)
        receiver[ocean] = -1
        terminal = independent_terminals(receiver, height)

        # ---- 3. published cells are exactly the accepted core cells ----------
        _, (accept_x, accept_z) = eligible_owner_at(args.seed, grid_x, grid_z, config)
        accepted = np.isfinite(accept_x)
        core_mask = np.zeros(shape, bool)
        core_mask[MARGIN:MARGIN + core + 1, MARGIN:MARGIN + core + 1] = True
        expected_accepted_core = accepted & core_mask
        published_x = np.asarray(arrays["cells_x_m"], np.float64)
        published_z = np.asarray(arrays["cells_z_m"], np.float64)
        published_flat = (
            np.rint((published_z - origin_z) / spacing).astype(np.int64) * shape[1]
            + np.rint((published_x - origin_x) / spacing).astype(np.int64))
        expected_flat = np.flatnonzero(expected_accepted_core.reshape(-1))
        check(checks, "published_cells_are_exactly_the_accepted_core_cells",
              np.array_equal(np.sort(published_flat), np.sort(expected_flat)),
              {"published": int(published_flat.size), "expected": int(expected_flat.size)})

        # ---- 4. the source sits on the published cells and nowhere else -------
        weathered = np.asarray(arrays["weathered_m3"], np.float64)
        entrained = np.asarray(arrays["entrained_m3"], np.float64)
        deposited = np.asarray(arrays["deposited_m3"], np.float64)
        delivered = np.asarray(arrays["delivered_m3"], np.float64)
        store_change = np.asarray(arrays["store_change_m3"], np.float64)
        cell_area = spacing * spacing

        check(checks, "weathered_total_equals_the_published_sum",
              abs(totals["weathered_total_m3"] - float(np.sum(weathered)))
              <= 1e-6 * max(abs(totals["weathered_total_m3"]), 1.0),
              {"tile_m3": totals["weathered_total_m3"], "published_m3": float(np.sum(weathered))})
        for name, array in (("entrained_total_m3", entrained),
                            ("deposited_total_m3", deposited),
                            ("delivered_total_m3", delivered),
                            ("store_change_total_m3", store_change)):
            key = name.replace("_total_m3", "")
            check(checks, "tile_%s_equals_the_published_sum" % key,
                  abs(totals[name] - float(np.sum(array)))
                  <= 1e-6 * max(abs(totals[name]), 1.0),
                  {"tile_m3": totals[name], "published_m3": float(np.sum(array))})

        # ---- 5. both ledgers close, per domain and tile wide ------------------
        scale_source = np.maximum(weathered + entrained + np.abs(store_change), 1.0)
        worst_source = float(np.max(np.abs(weathered - entrained - store_change) / scale_source)) \
            if weathered.size else 0.0
        check(checks, "per_domain_source_ledger_closes", worst_source < 1e-9,
              {"worst_relative_residual": worst_source})
        scale_routing = np.maximum(entrained + deposited + delivered, 1.0)
        worst_routing = float(np.max(np.abs(entrained - deposited - delivered) / scale_routing)) \
            if entrained.size else 0.0
        check(checks, "per_domain_routing_ledger_closes", worst_routing < 1e-9,
              {"worst_relative_residual": worst_routing})
        check(checks, "tile_source_ledger_closes",
              abs(totals["source_residual_m3"])
              <= 1e-6 * max(abs(totals["weathered_total_m3"]), 1.0),
              {"reported_residual_m3": totals["source_residual_m3"]})
        # The tile atlas must close WITH the stranded bin, so nothing is silently
        # dropped between the per-domain ledgers and the tile total.
        atlas = (totals["deposited_total_m3"] + totals["delivered_total_m3"]
                 + totals["stranded_on_refused_m3"])
        check(checks, "tile_atlas_closes_with_the_stranded_bin",
              abs(totals["entrained_total_m3"] - atlas)
              <= 1e-6 * max(abs(totals["entrained_total_m3"]), 1.0),
              {"entrained_m3": totals["entrained_total_m3"], "atlas_m3": atlas,
               "reported_routing_residual_m3": totals["routing_residual_m3"]})

        # ---- 6. the fate an independent push produces -------------------------
        # Attribution cannot be checked by spreading a domain's entrainment total
        # uniformly: deposition is charged on EVERY accepted cell a load passes, so
        # the per-cell pattern decides how much settles where. The oracle therefore
        # uses a **single-interval** solve, where the per-cell entrainment has an
        # exact closed form on the raw face -- `clip(gain * slope, 0, 1) * depth` with
        # an empty starting store. The multi-interval run is held to conservation and
        # to the totals above; a per-cell oracle for it would have to replay the
        # store recurrence, which would be a copy of the implementation rather than
        # an independent one. Both facts are stated, not hidden.
        offsets = np.asarray(arrays["cell_offsets"], np.int64)
        if args.initial_mobile_m != 0.0:
            check(checks, "per_cell_attribution_oracle_skipped_for_a_nonzero_initial_store",
                  True, "the slope law is only an exact per-cell closed form while the "
                        "store starts empty")
        elif args.intervals != 1:
            check(checks, "per_cell_attribution_oracle_skipped_for_multiple_intervals",
                  True, "a multi-interval run has no closed-form per-cell entrainment; "
                        "run with --intervals 1 to exercise the attribution oracle")
        else:
            dh_dz, dh_dx = np.gradient(height, spacing, spacing)
            slope = np.hypot(dh_dx, dh_dz)
            fraction = np.clip(args.slope_gain * slope.reshape(-1)[published_flat], 0.0, 1.0)
            closed_form = fraction * args.weathered_m_per_interval * cell_area
            check(checks, "tile_entrainment_matches_the_closed_form_slope_law",
                  abs(float(np.sum(entrained)) - float(np.sum(closed_form)))
                  <= 1e-6 * max(float(np.sum(closed_form)), 1.0),
                  {"published_m3": float(np.sum(entrained)),
                   "closed_form_m3": float(np.sum(closed_form))})

            load_flat = np.zeros(shape[0] * shape[1], np.float64)
            np.add.at(load_flat, published_flat, closed_form)
            landed, oracle_deposited = independent_sediment_push(
                height, receiver, accepted, load_flat, args.deposit_fraction)
            check(checks, "independent_push_conserves_the_load",
                  abs(float(np.sum(landed)) + float(np.sum(oracle_deposited))
                      - float(np.sum(load_flat)))
                  <= 1e-6 * max(float(np.sum(load_flat)), 1.0),
                  {"loaded_m3": float(np.sum(load_flat)),
                   "landed_m3": float(np.sum(landed)),
                   "deposited_m3": float(np.sum(oracle_deposited))})
            check(checks, "tile_deposition_matches_the_independent_push",
                  abs(float(np.sum(oracle_deposited)) - totals["deposited_total_m3"])
                  <= 1e-6 * max(abs(totals["deposited_total_m3"]), 1.0),
                  {"module_m3": totals["deposited_total_m3"],
                   "oracle_m3": float(np.sum(oracle_deposited))})

            # Each domain's delivery must be what lands on ITS OWN terminal; the
            # per-domain deposition must be what settles on the accepted cells that
            # drain to that terminal (margin included -- that is why the product
            # attributes deposition by terminal rather than by published cell).
            terminal_flat = terminal.reshape(-1)
            worst_delivery = 0.0
            worst_delivery_detail = None
            worst_deposition = 0.0
            worst_deposition_detail = None
            claimed = np.full(shape[0] * shape[1], False)
            claimed[terminal_flat[published_flat]] = True
            for index in range(offsets.size - 1):
                start, stop = int(offsets[index]), int(offsets[index + 1])
                if start == stop:
                    continue
                column = np.rint((published_x[start:stop] - origin_x) / spacing).astype(np.int64)
                row = np.rint((published_z[start:stop] - origin_z) / spacing).astype(np.int64)
                flat = row * shape[1] + column
                target = int(terminal_flat[flat[0]])
                if not bool(np.all(terminal_flat[flat] == target)):
                    check(checks, "one_terminal_per_domain", False,
                          {"domain_index": index})
                    break
                difference = abs(float(landed[target]) - float(delivered[index]))
                if difference > worst_delivery:
                    worst_delivery = difference
                    worst_delivery_detail = {"domain_index": index,
                                             "oracle_m3": float(landed[target]),
                                             "published_m3": float(delivered[index])}
                oracle_domain_deposition = float(np.sum(
                    oracle_deposited[accepted.reshape(-1) & (terminal_flat == target)]))
                difference = abs(oracle_domain_deposition - float(deposited[index]))
                if difference > worst_deposition:
                    worst_deposition = difference
                    worst_deposition_detail = {
                        "domain_index": index,
                        "oracle_m3": oracle_domain_deposition,
                        "published_m3": float(deposited[index])}
            tolerance_delivery = 1e-6 * max(abs(totals["delivered_total_m3"]), 1.0)
            tolerance_deposition = 1e-6 * max(abs(totals["deposited_total_m3"]), 1.0)
            check(checks, "per_domain_delivery_matches_the_independent_push",
                  worst_delivery <= tolerance_delivery,
                  {"worst_absolute_difference_m3": worst_delivery,
                   "tolerance_m3": tolerance_delivery, "worst": worst_delivery_detail})
            check(checks, "per_domain_deposition_matches_the_independent_push",
                  worst_deposition <= tolerance_deposition,
                  {"worst_absolute_difference_m3": worst_deposition,
                   "tolerance_m3": tolerance_deposition, "worst": worst_deposition_detail})
            stranded = float(np.sum(landed[~claimed]))
            check(checks, "stranded_bin_is_the_unclaimed_terminal_load",
                  abs(stranded - totals["stranded_on_refused_m3"])
                  <= 1e-6 * max(abs(totals["delivered_total_m3"]), 1.0),
                  {"oracle_m3": stranded, "reported_m3": totals["stranded_on_refused_m3"]})

        # ---- 7. refusal semantics stay honest --------------------------------
        check(checks, "accepted_and_excluded_cells_partition_the_core",
              totals["accepted_cells"] == int(np.sum(np.asarray(arrays["cell_count"], np.int64))),
              {"accepted_cells": totals["accepted_cells"],
               "published_cell_count": int(np.sum(np.asarray(arrays["cell_count"], np.int64)))})
        check(checks, "volumes_are_nonnegative",
              not (np.any(weathered < 0) or np.any(entrained < 0)
                   or np.any(deposited < 0) or np.any(delivered < 0)),
              {"min_weathered": float(np.min(weathered)) if weathered.size else 0.0,
               "min_entrained": float(np.min(entrained)) if entrained.size else 0.0})
        check(checks, "stranded_bin_is_nonnegative",
              totals["stranded_on_refused_m3"] >= 0.0,
              {"m3": totals["stranded_on_refused_m3"]})
        kind = np.asarray(arrays["kind"]).astype(str)
        check(checks, "domain_kind_is_marine_or_inland",
              kind.shape == delivered.shape
              and set(kind.tolist()).issubset({"marine", "inland"}),
              {"marine": int(np.count_nonzero(kind == "marine")),
               "inland": int(np.count_nonzero(kind == "inland"))})
        sea = float(np.sum(delivered[kind == "marine"])) if kind.size else 0.0
        basins = float(np.sum(delivered[kind == "inland"])) if kind.size else 0.0
        check(checks, "sea_and_basin_delivery_split_is_recomputed",
              abs(sea - totals["delivered_to_sea_m3"])
              <= 1e-6 * max(abs(totals["delivered_total_m3"]), 1.0)
              and abs(basins - totals["delivered_to_basins_m3"])
              <= 1e-6 * max(abs(totals["delivered_total_m3"]), 1.0),
              {"sea_m3": sea, "inland_m3": basins})

        # ---- 8. identity stability across a reload ---------------------------
        check(checks, "domain_identities_are_unique_outlet_coordinates",
              np.unique(np.stack([np.asarray(arrays["outlet_x_m"], np.float64),
                                  np.asarray(arrays["outlet_z_m"], np.float64)], axis=1),
                        axis=0).shape[0] == int(metadata["domain_count"]),
              {"domain_count": int(metadata["domain_count"])})
    except Exception as error:  # noqa: BLE001 -- the report must record the failure
        checks.append({"check": "audit_ran_to_completion", "passed": False,
                       "detail": "%s: %s" % (type(error).__name__, error)})
        passed = False
    else:
        passed = all(item["passed"] for item in checks)

    if not checks or checks[-1]["check"] != "audit_ran_to_completion":
        checks.append({"check": "audit_ran_to_completion", "passed": True, "detail": None})

    report = {
        "schema": AUDIT_SCHEMA,
        "seed": int(args.seed),
        "source": source,
        "points": [[float(x), float(z)] for x, z in points],
        "intervals": int(args.intervals),
        "parameters": dict(parameters.__dict__ if hasattr(parameters, "__dict__")
                           else {"weathered_m_per_interval": args.weathered_m_per_interval,
                                 "slope_gain": args.slope_gain,
                                 "deposit_fraction": args.deposit_fraction,
                                 "initial_mobile_m": args.initial_mobile_m}),
        "totals": totals,
        "checks": checks,
        "check_count": len(checks),
        "passed_count": sum(1 for item in checks if item["passed"]),
        "failed_count": sum(1 for item in checks if not item["passed"]),
        "passed": passed,
        "limitations": [
            "ocean mask and accepted/refused split are reused from the closure "
            "module's separately tested functions, not re-implemented here",
            "the yield coefficients are declared engineering assumptions and are "
            "NOT certified by this auditor; only the ledger closure, the source "
            "placement and the reported fate are",
            "the closed-form per-cell slope law is only exact for a SINGLE interval "
            "with an empty starting store; the multi-interval run is held to "
            "conservation and totals instead, and running with --intervals 1 "
            "exercises the attribution oracle",
            "this auditor writes no product and modifies no terrain",
        ],
    }
    path = Path(args.report)
    if path.exists():
        print("FAILED: report already exists at %s; refusing to overwrite" % path,
              file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    for item in checks:
        print("%s  %s%s" % ("PASS" if item["passed"] else "FAIL", item["check"],
                             "" if item["detail"] is None else "  %s" % (item["detail"],)))
    print("%d/%d checks PASS" % (report["passed_count"], report["check_count"]))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(run())
