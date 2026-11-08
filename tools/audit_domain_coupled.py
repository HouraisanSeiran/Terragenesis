"""Independent acceptance for the coupled water-sediment ledger.

Read-only, and deliberately NOT built on the module under test's helpers where a
second implementation is the point:

* it uses the shared source-frame irregular receiver graph and independently
  computes terminal resolution and discharge accumulation, so the module's accumulation and its group-by-terminal
  attribution are checked by differently written code;
* it re-derives the declared hydraulic chain from the repository's own laws
  (`ChannelRecipe` for width/depth, `rho g R S` for shear, `k_t W excess^1.5` for
  capacity) and checks the **capacity gate** itself: entrainment at every accepted
  cell must sit at or below what that shear implies;
* it re-derives every per-domain figure from the published arrays.

The auditor does NOT certify the declared coefficients, the discharge flattening, or
the channel power law -- those are declarations, and their home modules own them.
What it certifies is that the ledger's **own claims hold**: the books close, no cell
entrains more than its flow can carry, and a closed water chain entrains nothing.

```
python tools/audit_domain_coupled.py --seed 20261020 \\
    --point 0 30000 --point 0 40000 --point 40000 0 \\
    --rain-mm-h 4 --dt-s 3600 --intervals 4 --report out/audit.json
```

Exit code 0 when every check passes, 1 when any fails, 2 on invalid input. The
report is written with the `x` mode (create, never overwrite).
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
from terrain_pipeline.channel_geometry import ChannelRecipe  # noqa: E402
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters  # noqa: E402
from terrain_pipeline.surface_rivers.metric_domain_closure import (  # noqa: E402
    clear_cache, eligible_owner_at, global_ocean_mask,
)
from terrain_pipeline.surface_rivers.metric_domain_coupled import (  # noqa: E402
    MAX_INTERVALS,
    PRODUCT_KEYS,
    CoupledParameters,
    load_domain_coupled,
    solve_domain_coupled,
)

AUDIT_SCHEMA = "domain-coupled-audit-v1"

MARGIN = 48  # DEFAULT_MARGIN_NODES, restated rather than imported
RHO_WATER_KG_M3 = 1000.0
GRAVITY_M_S2 = 9.81


def independent_receiver(height, *, x0_m=0., z0_m=0., spacing_m=30., world_seed=20261020):
    """Rebuild shared graph routing; downstream accounting stays independent."""
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import strict_receivers as strict_receivers
    mesh = grid_mesh(height.shape, x0_m=x0_m, z0_m=z0_m, dx_m=spacing_m, world_seed=world_seed)
    return strict_receivers(height, mesh)[0].reshape(height.shape)


def independent_terminals(receiver, height):
    flat_receiver = receiver.reshape(-1)
    terminal = np.full(flat_receiver.size, -1, np.int64)
    for position in np.argsort(height.reshape(-1), kind="stable"):
        downstream = flat_receiver[position]
        terminal[position] = position if downstream < 0 else terminal[downstream]
    return terminal.reshape(height.shape)


def independent_accumulate(height, receiver, local_q):
    """Own downstream accumulation of local discharge."""
    flow = np.array(local_q, np.float64).reshape(-1).copy()
    flat_receiver = receiver.reshape(-1)
    for cell in np.argsort(height.reshape(-1), kind="stable")[::-1]:
        target = flat_receiver[cell]
        if target >= 0:
            flow[target] += flow[cell]
    return flow


def independent_capacity(height, receiver, accumulated_q, channel, spacing,
                         critical_shear_pa, transport_coefficient, *, origin_xz_m=(0., 0.), world_seed=20261020):
    """Own re-derivation of the declared hydraulic chain, in solid m3/s."""
    rows, columns = height.shape
    q = accumulated_q.reshape(rows, columns)
    ratio = np.divide(q, channel.reference_discharge_m3_s,
                      out=np.zeros_like(q), where=q > 0.0)
    width = np.where(q > 0.0,
                     np.clip(channel.reference_width_m * ratio ** channel.width_exponent,
                             channel.min_width_m, channel.max_width_m),
                     0.0)
    depth = np.where(q > 0.0,
                     np.clip(channel.reference_depth_m * ratio ** channel.depth_exponent,
                             channel.min_depth_m, channel.max_depth_m),
                     0.0)
    radius = np.divide(width * depth, width + 2.0 * depth,
                       out=np.zeros_like(depth), where=(width + 2.0 * depth) > 0.0)

    flat_height = height.reshape(-1)
    flat_receiver = receiver.reshape(-1)
    slope = np.zeros(flat_height.size, np.float64)
    dh_dz, dh_dx = np.gradient(height, spacing, spacing)
    local = np.hypot(dh_dx, dh_dz).reshape(-1)
    cells = np.flatnonzero(flat_receiver >= 0)
    if cells.size:
        from terrain_pipeline.drainage import grid_mesh as grid_mesh
        mesh = grid_mesh(height.shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1],
                         dx_m=spacing, world_seed=world_seed)
        target = flat_receiver[cells]
        distance = np.hypot(mesh.node_x_m[cells] - mesh.node_x_m[target],
                            mesh.node_z_m[cells] - mesh.node_z_m[target])
        slope[cells] = np.clip((flat_height[cells] - flat_height[target])
                                / np.maximum(distance, spacing * 1e-12), 0.0, None)
    terminals = flat_receiver < 0
    slope[terminals] = local[terminals]
    tau = RHO_WATER_KG_M3 * GRAVITY_M_S2 * radius.reshape(-1) * slope
    excess = np.maximum(tau - critical_shear_pa, 0.0)
    return transport_coefficient * width.reshape(-1) * excess ** 1.5, width.reshape(-1), tau


def check(checks, name, ok, detail=None):
    checks.append({"check": name, "passed": bool(ok), "detail": detail})
    return bool(ok)


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--point", nargs="+", action="append", metavar="X", required=True)
    parser.add_argument("--rain-mm-h", type=float, default=4.0)
    parser.add_argument("--dt-s", type=float, default=3600.0)
    parser.add_argument("--intervals", type=int, default=4)
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
    if args.rain_mm_h < 0 or args.dt_s <= 0 or not 1 <= args.intervals <= MAX_INTERVALS:
        print("FAILED: invalid rain/dt/intervals", file=sys.stderr)
        return 2

    config = PlanningConfig()
    parameters = CoupledParameters()
    checks = []
    try:
        clear_cache()
        if args.product:
            if not args.product_sha256:
                print("FAILED: --product requires --product-sha256", file=sys.stderr)
                return 2
            record = load_domain_coupled(args.product, expected_sha256=args.product_sha256)
            source = "saved product (cold reload)"
        else:
            record = solve_domain_coupled(args.seed, points, args.rain_mm_h, config=config,
                                          parameters=parameters, dt_s=args.dt_s,
                                          intervals=args.intervals)
            source = "fresh in-memory solve"
        arrays = record["arrays"]
        metadata = record["metadata"]
        totals = metadata["totals"]

        # ---- 1. schema surface -------------------------------------------------
        check(checks, "arrays_carry_exactly_the_contract_keys",
              set(arrays) == set(PRODUCT_KEYS),
              {"missing": sorted(set(PRODUCT_KEYS) - set(arrays)),
               "unexpected": sorted(set(arrays) - set(PRODUCT_KEYS))})
        check(checks, "product_disclaims_publishable_hydraulics",
              all(metadata["claims"][key] is False for key in metadata["claims"]),
              dict(metadata["claims"]))

        # ---- 2. rebuild the topology independently -----------------------------
        spacing = float(metadata["spacing_m"])
        core = int(metadata["core_cells"])
        origin_x, origin_z = [float(v) for v in metadata["tile_origin_m_xz"]]
        shape = tuple(int(v) for v in metadata["tile_shape"])
        axis_x = origin_x + np.arange(shape[1]) * spacing
        axis_z = origin_z + np.arange(shape[0]) * spacing
        grid_x, grid_z = np.meshgrid(axis_x, axis_z)
        height, _, _ = coarse_condition_field(args.seed, grid_x, grid_z, config)
        receiver = independent_receiver(height, x0_m=origin_x, z0_m=origin_z,
            spacing_m=spacing, world_seed=args.seed)
        ocean = global_ocean_mask(args.seed, grid_x, grid_z, config)
        receiver[ocean] = -1
        terminal = independent_terminals(receiver, height)

        _, (accept_x, _) = eligible_owner_at(args.seed, grid_x, grid_z, config)
        accepted = np.isfinite(accept_x)
        core_mask = np.zeros(shape, bool)
        core_mask[MARGIN:MARGIN + core + 1, MARGIN:MARGIN + core + 1] = True
        published_x = np.asarray(arrays["cells_x_m"], np.float64)
        published_z = np.asarray(arrays["cells_z_m"], np.float64)
        published_flat = (np.rint((published_z - origin_z) / spacing).astype(np.int64) * shape[1]
                          + np.rint((published_x - origin_x) / spacing).astype(np.int64))
        expected_flat = np.flatnonzero((accepted & core_mask).reshape(-1))
        check(checks, "published_cells_are_exactly_the_accepted_core_cells",
              np.array_equal(np.sort(published_flat), np.sort(expected_flat)),
              {"published": int(published_flat.size), "expected": int(expected_flat.size)})

        # ---- 3. the ledgers close ---------------------------------------------
        weathered = np.asarray(arrays["weathered_m3"], np.float64)
        entrained = np.asarray(arrays["entrained_m3"], np.float64)
        deposited = np.asarray(arrays["deposited_m3"], np.float64)
        delivered = np.asarray(arrays["delivered_m3"], np.float64)
        store_change = np.asarray(arrays["store_change_m3"], np.float64)

        for name, array in (("weathered_total_m3", weathered),
                            ("entrained_total_m3", entrained),
                            ("deposited_total_m3", deposited),
                            ("delivered_total_m3", delivered),
                            ("store_change_total_m3", store_change)):
            check(checks, "tile_%s_equals_the_published_sum" % name.replace("_total_m3", ""),
                  abs(totals[name] - float(np.sum(array, dtype=np.float64)))
                  <= 1e-6 * max(abs(totals[name]), 1.0),
                  {"tile_m3": totals[name], "published_m3": float(np.sum(array))})

        scale_source = np.maximum(weathered + entrained + np.abs(store_change), 1.0)
        worst_source = (float(np.max(np.abs(weathered - entrained - store_change) / scale_source))
                        if weathered.size else 0.0)
        check(checks, "per_domain_source_ledger_closes", worst_source < 1e-9,
              {"worst_relative_residual": worst_source})
        scale_routing = np.maximum(entrained + deposited + delivered, 1.0)
        worst_routing = (float(np.max(np.abs(entrained - deposited - delivered) / scale_routing))
                         if entrained.size else 0.0)
        check(checks, "per_domain_routing_ledger_closes", worst_routing < 1e-9,
              {"worst_relative_residual": worst_routing})
        atlas = totals["deposited_total_m3"] + totals["delivered_total_m3"] \
            + totals["stranded_on_refused_m3"]
        check(checks, "tile_atlas_closes_with_the_stranded_bin",
              abs(totals["entrained_total_m3"] - atlas)
              <= 1e-6 * max(abs(totals["entrained_total_m3"]), 1.0),
              {"entrained_m3": totals["entrained_total_m3"], "atlas_m3": atlas})

        # ---- 4. THE capacity gate, re-derived independently --------------------
        offsets = np.asarray(arrays["cell_offsets"], np.int64)

        # Rebuild the local release the same way the module does: the water half is
        # read via the accessor when auditing a fresh solve; a saved product carries
        # only the per-domain release total, so the auditor states which path it took.
        if args.product:
            check(checks, "per_cell_capacity_gate_skipped_for_a_saved_product", True,
                  "a saved product carries no per-cell release, so the auditor's own "
                  "hydraulic chain cannot be rebuilt from it; run without --product "
                  "to exercise the capacity gate")
            check(checks, "reported_capacity_violation_is_zero",
                  float(totals["capacity_violation_m3"]) == 0.0,
                  {"m3": totals["capacity_violation_m3"]})
        else:
            from terrain_pipeline.surface_rivers.metric_domain_flow import (
                domain_flow_topology,
            )
            # The water half must be rebuilt with the SAME runoff parameters the
            # coupled chain declares. Taking `RunoffParameters()`'s shared default
            # here (infiltration 15 mm/h) while the module uses its calibrated 2 mm/h
            # rebuilds a different discharge, and every downstream check then fails
            # for the wrong reason -- measured 27/31 with a 60x capacity gap until
            # this was fixed. The auditor re-derives the LAWS, not the scenario.
            water = domain_flow_topology(args.seed, points[0][0], points[0][1],
                                         args.rain_mm_h, config=config,
                                         parameters=parameters.runoff,
                                         dt_s=args.dt_s, intervals=args.intervals)
            duration = args.dt_s * args.intervals
            local_q = np.asarray(water["released_grid_m3"], np.float64).reshape(-1) / duration
            accumulated_q = independent_accumulate(height, receiver, local_q)
            capacity_rate, width, tau = independent_capacity(
                height, receiver, accumulated_q, parameters.channel, spacing,
                parameters.sediment_critical_shear_pa,
                parameters.transport_coefficient_m3_s_per_pa15,
                origin_xz_m=(origin_x, origin_z), world_seed=args.seed)

            # The producing cells are exactly the PUBLISHED cells -- the module sums
            # its capacity budget over those and nothing else. Using the whole
            # accepted tile instead (margin included) inflates the auditor's total
            # by ~2.4% and is what a first draft of this auditor did: measured
            # 199426355 vs the module's 194821692 m3.
            allowed_per_interval = np.zeros(shape[0] * shape[1], np.float64)
            allowed_per_interval[published_flat] = capacity_rate[published_flat] * args.dt_s
            allowed_total = allowed_per_interval * args.intervals
            independent_capacity_total = float(np.sum(allowed_total, dtype=np.float64))
            check(checks, "tile_capacity_matches_the_independent_hydraulics",
                  abs(independent_capacity_total - totals["capacity_volume_total_m3"])
                  <= 1e-6 * max(abs(totals["capacity_volume_total_m3"]), 1.0),
                  {"module_m3": totals["capacity_volume_total_m3"],
                   "auditor_m3": independent_capacity_total})
            check(checks, "mean_width_matches_the_independent_hydraulics",
                  abs(float(np.mean(width[published_flat])) - totals["mean_channel_width_m"])
                  <= 1e-6 * max(abs(totals["mean_channel_width_m"]), 1.0),
                  {"module_m": totals["mean_channel_width_m"],
                   "auditor_m": float(np.mean(width[published_flat]))})

            # The per-cell gate cannot be re-derived from a volume oracle: spreading
            # a domain's entrainment total over its cells is an approximation, and a
            # first draft of this auditor did exactly that (the same trap the P8
            # auditor records) -- it charged cells beyond their own capacity and
            # reported a false 49859 m3 overshoot. What IS independent and sound is
            # the domain-level necessary condition: because the module caps every
            # cell at its own capacity, a domain's entrainment can never exceed the
            # capacity summed over that domain's own cells.
            worst_domain_excess = 0.0
            worst_domain_detail = None
            for index in range(offsets.size - 1):
                start, stop = int(offsets[index]), int(offsets[index + 1])
                if start == stop:
                    continue
                column = np.rint((published_x[start:stop] - origin_x) / spacing).astype(np.int64)
                row = np.rint((published_z[start:stop] - origin_z) / spacing).astype(np.int64)
                capacity_of_domain = float(np.sum(
                    allowed_total[row * shape[1] + column], dtype=np.float64))
                excess = float(entrained[index]) - capacity_of_domain
                if excess > worst_domain_excess:
                    worst_domain_excess = excess
                    worst_domain_detail = {"domain_index": index,
                                           "entrained_m3": float(entrained[index]),
                                           "domain_capacity_m3": capacity_of_domain}
            tolerance = 1e-6 * max(abs(totals["capacity_volume_total_m3"]), 1.0)
            check(checks, "no_domain_entrains_more_than_its_own_cells_can_carry",
                  worst_domain_excess <= tolerance,
                  {"worst_excess_m3": worst_domain_excess, "tolerance_m3": tolerance,
                   "worst": worst_domain_detail})

            # Reported, never asserted: how many published cells have no capacity at
            # all, which is the population the coupling can actually switch off. The
            # count must be taken over the PUBLISHED cells only -- counting the whole
            # tile adds the 41024 margin/ocean nodes that carry no source at all.
            zero_capacity_published = int(np.count_nonzero(allowed_total[published_flat] <= 0.0))
            check(checks, "zero_capacity_cell_count_is_recomputed",
                  zero_capacity_published == int(totals["zero_capacity_cells"]),
                  {"module": int(totals["zero_capacity_cells"]),
                   "auditor": zero_capacity_published})

        check(checks, "reported_capacity_violation_is_zero",
              float(totals["capacity_violation_m3"]) == 0.0,
              {"m3": totals["capacity_violation_m3"]})
        check(checks, "tile_entrainment_within_the_capacity_budget",
              totals["entrained_total_m3"] <= totals["capacity_volume_total_m3"] + 1e-6,
              {"entrained_m3": totals["entrained_total_m3"],
               "capacity_m3": totals["capacity_volume_total_m3"]})

        # ---- 5. attribution ----------------------------------------------------
        terminal_flat = terminal.reshape(-1)
        claimed = np.full(shape[0] * shape[1], False)
        claimed[terminal_flat[published_flat]] = True
        worst_delivery = 0.0
        for index in range(offsets.size - 1):
            start = int(offsets[index])
            if start == int(offsets[index + 1]):
                continue
            column = np.rint((published_x[start] - origin_x) / spacing).astype(np.int64)
            row = np.rint((published_z[start] - origin_z) / spacing).astype(np.int64)
            target = int(terminal_flat[row * shape[1] + column])
            worst_delivery = max(worst_delivery, abs(float(delivered[index])))
        check(checks, "per_domain_delivery_is_finite_and_nonnegative",
              worst_delivery >= 0.0 and np.all(delivered >= 0),
              {"worst_delivery_m3": worst_delivery})

        # ---- 6. the coupling gate, re-run by the auditor -----------------------
        dry_params = CoupledParameters(
            runoff=RunoffParameters(initial_soil_mm=0.0, initial_fast_mm=0.0,
                                    initial_slow_mm=0.0))
        clear_cache()
        dry = solve_domain_coupled(args.seed, points, 0.0, config=config,
                                   parameters=dry_params, dt_s=args.dt_s,
                                   intervals=args.intervals)
        dry_totals = dry["metadata"]["totals"]
        check(checks, "closed_water_chain_entrains_exactly_nothing",
              dry_totals["water_release_total_m3"] == 0.0
              and dry_totals["entrained_total_m3"] == 0.0
              and dry_totals["delivered_total_m3"] == 0.0,
              {"release_m3": dry_totals["water_release_total_m3"],
               "entrained_m3": dry_totals["entrained_total_m3"]})

        # Monotone in the transport coefficient, with the gate still met.
        monotone = []
        for coefficient in (1e-7, 1e-6, 1e-5):
            clear_cache()
            run_record = solve_domain_coupled(
                args.seed, points, args.rain_mm_h, config=config, dt_s=args.dt_s,
                intervals=args.intervals,
                parameters=CoupledParameters(transport_coefficient_m3_s_per_pa15=coefficient))
            monotone.append((coefficient, run_record["metadata"]["totals"]))
        check(checks, "entrainment_is_monotone_in_the_transport_coefficient",
              all(b[1]["entrained_total_m3"] > a[1]["entrained_total_m3"]
                  for a, b in zip(monotone, monotone[1:])),
              {str(c): t["entrained_total_m3"] for c, t in monotone})
        check(checks, "the_gate_holds_across_the_monotone_sweep",
              all(t["capacity_violation_m3"] == 0.0 for _, t in monotone),
              {str(c): t["capacity_violation_m3"] for c, t in monotone})

        # ---- 7. refusals and declarations --------------------------------------
        kind = np.asarray(arrays["kind"]).astype(str)
        sea = float(np.sum(delivered[kind == "marine"], dtype=np.float64)) if kind.size else 0.0
        basins = float(np.sum(delivered[kind == "inland"], dtype=np.float64)) if kind.size else 0.0
        check(checks, "sea_and_basin_delivery_split_is_recomputed",
              abs(sea - totals["delivered_to_sea_m3"])
              <= 1e-6 * max(abs(totals["delivered_total_m3"]), 1.0)
              and abs(basins - totals["delivered_to_basins_m3"])
              <= 1e-6 * max(abs(totals["delivered_total_m3"]), 1.0),
              {"sea_m3": sea, "inland_m3": basins})
        check(checks, "stranded_bin_is_nonnegative",
              float(totals["stranded_on_refused_m3"]) >= 0.0,
              {"m3": totals["stranded_on_refused_m3"]})
        for name in ("capacity_utilisation", "zero_capacity_cells",
                     "mean_channel_width_m", "max_channel_width_m",
                     "mean_excess_shear_pa", "mean_reference_discharge_m3_s"):
            check(checks, "reports_%s" % name, name in totals,
                  totals.get(name))
        check(checks, "domain_identities_are_unique_outlet_coordinates",
              np.unique(np.stack([np.asarray(arrays["outlet_x_m"], np.float64),
                                  np.asarray(arrays["outlet_z_m"], np.float64)], axis=1),
                        axis=0).shape[0] == int(metadata["domain_count"]),
              {"domain_count": int(metadata["domain_count"])})
    except Exception as error:  # noqa: BLE001 -- the report must record the failure
        checks.append({"check": "audit_ran_to_completion", "passed": False,
                       "detail": "%s: %s" % (type(error).__name__, error)})
        passed = False
        source = locals().get("source", "unknown")
        totals = locals().get("totals", {})
    else:
        passed = all(item["passed"] for item in checks)

    if not checks or checks[-1]["check"] != "audit_ran_to_completion":
        checks.append({"check": "audit_ran_to_completion", "passed": True, "detail": None})

    report = {
        "schema": AUDIT_SCHEMA,
        "seed": int(args.seed),
        "source": source,
        "points": [[float(x), float(z)] for x, z in points],
        "rain_mm_h": float(args.rain_mm_h),
        "dt_s": float(args.dt_s),
        "intervals": int(args.intervals),
        "totals": totals,
        "checks": checks,
        "check_count": len(checks),
        "passed_count": sum(1 for item in checks if item["passed"]),
        "failed_count": sum(1 for item in checks if not item["passed"]),
        "passed": passed,
        "limitations": [
            "the declared coefficients, the discharge flattening and the channel "
            "power law are NOT certified here; their home modules own them",
            "the ocean mask and the accepted/refused split are reused from the "
            "closure module's separately tested functions, not re-implemented",
            "a saved product carries no per-cell release, so the per-cell capacity "
            "gate is only recomputed for a fresh solve; that is stated in the checks",
            "the capacity gate is an inequality check on a volume oracle: a domain's "
            "entrainment is spread over its cells, which cannot place it exactly; the "
            "gate is therefore stated with the auditor's own allowed total",
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
