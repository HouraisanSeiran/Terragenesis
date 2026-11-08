"""Independent acceptance for the domain water ledger (`metric_domain_flow`).

Read-only and deliberately NOT built on the module under test's own helpers:

* it uses the shared source-frame irregular graph for strict downhill receivers
  and authors its **own** upstream-first routing push -- so the ledger's
  group-by-terminal shortcut is checked by a second, differently written
  implementation rather than by itself;
* it re-derives every per-domain figure from the published arrays and compares
  both the per-domain ledger and the tile partition;
* it re-verifies the closure module's public query against the published cells.

Scope, stated rather than hidden: the ocean mask and the accepted/refused split
are taken from the closure module's already-accepted, separately tested
functions (`test_metric_domain_closure`, `test_metric_domain_eligibility`); this
auditor does not re-implement the connectivity flood, and says so in its report.

```
python tools/audit_domain_flow.py --seed 20261020 \\
    --point 0 30000 --point 0 40000 --point 40000 0 \\
    --rain-mm-h 4 --dt-s 3600 --intervals 6 --report out/audit.json
```

Exit code is 0 when every check passes, 1 when any check fails, and 2 on invalid
input. The report is written with the `x` mode (create, never overwrite), the
same discipline as the other auditors in this repository.
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
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters  # noqa: E402
from terrain_pipeline.surface_rivers.metric_domain_closure import (  # noqa: E402
    clear_cache, eligible_owner_at, global_ocean_mask,
)
from terrain_pipeline.surface_rivers.metric_domain_flow import (  # noqa: E402
    PRODUCT_KEYS,
    load_domain_flow,
    solve_domain_flow,
)

AUDIT_SCHEMA = "domain-flow-audit-v1"



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


def independent_push(height, receiver, released_flat):
    """Own upstream-first routing: push each cell's volume into its receiver."""
    flow = np.array(released_flat, np.float64).copy()
    for cell in np.argsort(-height.reshape(-1), kind="stable"):
        target = receiver.reshape(-1)[cell]
        if target >= 0:
            flow[target] += flow[cell]
            flow[cell] = 0.0
    return flow


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
    parser.add_argument("--intervals", type=int, default=6)
    parser.add_argument("--product", help="audit a saved .npz instead of a fresh solve")
    parser.add_argument("--product-sha256", help="required with --product")
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)

    points = []
    for values in args.point:
        if len(values) != 2:
            print("FAILED: --point needs exactly two numbers; got %r" % (values,), file=sys.stderr)
            return 2
        try:
            points.append((float(values[0]), float(values[1])))
        except ValueError:
            print("FAILED: --point values must be numbers; got %r" % (values,), file=sys.stderr)
            return 2
    if args.rain_mm_h < 0 or args.dt_s <= 0 or not 1 <= args.intervals <= 60:
        print("FAILED: invalid rainfall/dt/intervals", file=sys.stderr)
        return 2

    config = PlanningConfig()
    checks = []
    try:
        clear_cache()
        if args.product:
            if not args.product_sha256:
                print("FAILED: --product requires --product-sha256", file=sys.stderr)
                return 2
            record = load_domain_flow(args.product, expected_sha256=args.product_sha256)
            source = "saved product (cold reload)"
        else:
            record = solve_domain_flow(args.seed, points, args.rain_mm_h, config=config,
                                       parameters=RunoffParameters(),
                                       dt_s=args.dt_s, intervals=args.intervals)
            source = "fresh in-memory solve"
        arrays = record["arrays"]
        metadata = record["metadata"]

        # ---- 1. schema and identity surface -----------------------------------
        check(checks, "arrays_carry_exactly_the_contract_keys",
              set(arrays) == set(PRODUCT_KEYS),
              {"missing": sorted(set(PRODUCT_KEYS) - set(arrays)),
               "unexpected": sorted(set(arrays) - set(PRODUCT_KEYS))})
        check(checks, "product_disclaims_publishable_hydraulics",
              all(metadata["claims"][key] is False for key in metadata["claims"]))

        # ---- 2. rebuild the topology independently ---------------------------
        spacing = float(metadata["spacing_m"])
        core = int(metadata["core_cells"])
        margin = 48  # DEFAULT_MARGIN_NODES, restated rather than imported
        origin_x, origin_z = [float(value) for value in metadata["tile_origin_m_xz"]]
        shape = tuple(int(value) for value in metadata["tile_shape"])
        axis_x = origin_x + np.arange(shape[1]) * spacing
        axis_z = origin_z + np.arange(shape[0]) * spacing
        grid_x, grid_z = np.meshgrid(axis_x, axis_z)
        height, _, _ = coarse_condition_field(args.seed, grid_x, grid_z, config)
        receiver = independent_receiver(height, x0_m=origin_x, z0_m=origin_z,
            spacing_m=spacing, world_seed=args.seed)
        # The closure contract makes every ocean cell a TERMINAL: its receiver is
        # forced to -1 (`ClosureRegion.__init__`: `receiver[self.ocean] = -1`), so a
        # coastal domain's chain ends at its river mouth. The ocean mask is a
        # separately tested closure function, reused rather than re-derived, and
        # this is the one contract rule the first draft of this auditor missed --
        # catching it is what the independent rebuild is for.
        ocean = global_ocean_mask(args.seed, grid_x, grid_z, config)
        receiver[ocean] = -1
        terminal = independent_terminals(receiver, height)

        # ---- 3. published cells are exactly the accepted core cells ----------
        _, (accept_x, accept_z) = eligible_owner_at(args.seed, grid_x, grid_z, config)
        accepted = np.isfinite(accept_x)
        core_mask = np.zeros(shape, bool)
        core_mask[margin:margin + core + 1, margin:margin + core + 1] = True
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

        # ---- 4. rebuilt terminals and domain grouping ------------------------
        rebuilt_terminal = terminal.reshape(-1)[published_flat]
        rebuilt_outlet_x = accept_x.reshape(-1)[published_flat]
        rebuilt_outlet_z = accept_z.reshape(-1)[published_flat]
        offsets = np.asarray(arrays["cell_offsets"], np.int64)
        product_outlet_x = np.asarray(arrays["outlet_x_m"], np.float64)
        product_outlet_z = np.asarray(arrays["outlet_z_m"], np.float64)
        rebuilt_keys = set(zip(np.round(rebuilt_outlet_x, 6).tolist(),
                               np.round(rebuilt_outlet_z, 6).tolist()))
        product_keys = set(zip(np.round(product_outlet_x, 6).tolist(),
                               np.round(product_outlet_z, 6).tolist()))
        check(checks, "domain_identity_set_matches_the_independent_rebuild",
              rebuilt_keys == product_keys,
              {"independent": len(rebuilt_keys), "product": len(product_keys)})

        # The closure contract makes the outlet identity the TERMINAL's world
        # coordinate (`outlet_at` returns `world_of_terminal(terminal)`), so the
        # terminal the independent rebuild assigns to a domain must land on the
        # world point the product calls that domain's outlet. This is a real
        # cross-check: the rebuild never reads the product's terminal column.
        flat_columns = shape[1]
        terminal_row, terminal_column = np.divmod(terminal.reshape(-1), flat_columns)
        terminal_world_x = origin_x + terminal_column * spacing
        terminal_world_z = origin_z + terminal_row * spacing
        terminal_mismatch = 0
        for index in range(offsets.size - 1):
            start, stop = int(offsets[index]), int(offsets[index + 1])
            if start == stop:
                continue
            mine = np.unique(terminal.reshape(-1)[published_flat[start:stop]])
            if mine.size != 1:
                terminal_mismatch += 1
                continue
            target = int(mine[0])
            if (abs(terminal_world_x[target] - product_outlet_x[index]) > 1e-6
                    or abs(terminal_world_z[target] - product_outlet_z[index]) > 1e-6):
                terminal_mismatch += 1
        check(checks, "every_domain_lands_on_one_terminal_matching_its_outlet",
              terminal_mismatch == 0, {"mismatched_domains": terminal_mismatch})

        # ---- 5. independent routing of the released volume -------------------
        released_flat = np.zeros(shape[0] * shape[1], np.float64)
        product_release = np.asarray(arrays["terminal_release_m3"], np.float64)
        # Spread each domain's published release over its own cells, then push it
        # downstream with the independent walk; the TOTAL landing on the domain's
        # terminal is what this check compares, so the intra-domain split cannot
        # hide a leak.
        for index in range(offsets.size - 1):
            start, stop = int(offsets[index]), int(offsets[index + 1])
            if start == stop:
                continue
            per_cell = product_release[index] / (stop - start)
            np.add.at(released_flat, published_flat[start:stop], per_cell)
        landed = independent_push(height, receiver, released_flat)
        conserved = abs(float(np.sum(landed)) - float(np.sum(released_flat)))
        check(checks, "independent_routing_conserves_every_cubic_metre",
              conserved <= 1e-6 * max(float(np.sum(released_flat)), 1.0),
              {"difference_m3": conserved})
        # The independent walk leaves volume only on terminal cells. A domain's
        # cells all share one terminal, so the volume the independent walk puts
        # on that terminal must equal the product's release total for the domain.
        worst_leak = 0.0
        for index in range(offsets.size - 1):
            start, stop = int(offsets[index]), int(offsets[index + 1])
            if start == stop:
                continue
            target = int(np.unique(terminal.reshape(-1)[published_flat[start:stop]])[0])
            worst_leak = max(worst_leak, abs(landed[target] - float(product_release[index])))
        check(checks, "each_domain_release_reaches_its_own_terminal",
              worst_leak <= 1e-3 * max(float(np.sum(product_release)), 1.0),
              {"worst_absolute_difference_m3": worst_leak})

        # ---- 6. per-domain and tile ledgers ---------------------------------
        rain = np.asarray(arrays["rain_input_m3"], np.float64)
        et = np.asarray(arrays["actual_et_m3"], np.float64)
        storage = np.asarray(arrays["soil_storage_change_m3"], np.float64)
        residual = rain - et - storage - product_release
        scale = np.maximum(np.abs(rain) + np.abs(et) + np.abs(storage) + np.abs(product_release), 1.0)
        worst_domain = float(np.max(np.abs(residual) / scale)) if rain.size else 0.0
        check(checks, "every_domain_ledger_closes", worst_domain <= 1e-9,
              {"worst_relative_residual": worst_domain})
        totals = metadata["totals"]
        partition = (totals["routed_rain_m3"] + totals["unresolved_rain_m3"]
                     + totals["ocean_direct_rain_m3"] + totals["outside_core_rain_m3"])
        check(checks, "rainfall_partition_closes",
              abs(totals["requested_rain_m3"] - partition)
              <= 1e-6 * max(abs(totals["requested_rain_m3"]), 1.0),
              {"requested_m3": totals["requested_rain_m3"], "partition_m3": partition})
        kind = np.asarray(arrays["kind"]).astype(str)
        check(checks, "reported_sea_and_basin_totals_are_recomputed",
              abs(totals["exported_to_sea_m3"] - float(np.sum(product_release[kind == "marine"]))) <= 1e-3
              and abs(totals["retained_in_basins_m3"] - float(np.sum(product_release[kind == "inland"]))) <= 1e-3)

        # ---- 7. refusals stay refusals --------------------------------------
        check(checks, "refused_rainfall_is_reported_never_routed",
              totals["unresolved_rain_m3"] >= 0.0 and totals["ocean_direct_rain_m3"] >= 0.0
              and abs(totals["routed_rain_m3"] - float(np.sum(rain))) <= 1e-3,
              {"routed_m3": totals["routed_rain_m3"],
               "unresolved_m3": totals["unresolved_rain_m3"],
               "ocean_direct_m3": totals["ocean_direct_rain_m3"]})
    finally:
        clear_cache()

    passed = sum(1 for item in checks if item["passed"])
    failed = len(checks) - passed
    report = {
        "schema": AUDIT_SCHEMA,
        "seed": int(args.seed),
        "points": [{"x_m": float(x), "z_m": float(z)} for x, z in points],
        "source": source,
        "rain_mm_h": float(args.rain_mm_h),
        "dt_s": float(args.dt_s),
        "intervals": int(args.intervals),
        "identity_sha256": record["identity_sha256"],
        "scope": {
            "independent": ["shared irregular-graph receiver", "terminal resolution",
                            "upstream-first routing", "per-domain ledger",
                            "rainfall partition", "published-cell set"],
            "reused_not_reimplemented": [
                "base conditioning face (coarse_condition_field)",
                "accepted/refused split and ocean mask (metric_domain_closure)",
                "soil bucket solver (rainfall_runoff.simulate_rainfall_runoff)"],
            "not_covered": ["channel hydraulics", "sediment", "terrain feedback",
                            "Terrain Diffusion inference", "Minecraft consumer"],
        },
        "checks": checks,
        "summary": {"passed": passed, "failed": failed, "total": len(checks)},
    }
    report_path = Path(args.report)
    if report_path.exists():
        print("FAILED: --report refuses to overwrite: %s" % report_path, file=sys.stderr)
        return 2
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)

    for item in checks:
        print("%s %s%s" % ("PASS" if item["passed"] else "FAIL", item["check"],
                           "" if item["detail"] in (None, True) else " " + json.dumps(item["detail"],
                                                                                     ensure_ascii=False)))
    print("summary: %d/%d passed (report: %s)" % (passed, len(checks), report_path))
    return 0 if failed == 0 else 1


def main(argv=None):
    return run(argv)


if __name__ == "__main__":
    sys.exit(run())
