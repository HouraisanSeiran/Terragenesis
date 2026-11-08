"""Independent acceptance for the derived bed-change product.

Read-only. It re-derives every conserved quantity **itself** -- it does not import
the module's arithmetic -- and it cross-checks the bed product against its parent,
which is the check that matters most: the solid volume written into the bed must be
the deposition the coupled ledger actually reported.

What it certifies
-----------------
* the parent's identity recomputes (so neither product was edited after publication);
* `bulk = solid / (1 - porosity)` and `pore = bulk - solid`, recomputed;
* per-domain and tile-wide conservation: `sum(bed_change) * area` equals the bulk
  volume, recomputed from the published depths;
* the **cross-product** conservation: the bed product's solid total equals the
  parent's `deposited_total_m3`;
* accumulation only (no negative change), and the raster marks exactly the published
  cells;
* the declarations: `terrain_feedback_applied` true, every hydraulic claim false,
  revalidation demanded, `bed_rejection` declared not applied.

What it does NOT certify
------------------------
the placement rule (uniform within a domain) is a **declaration**, not a claim about
where material really settled; the auditor checks that the product *says so* and that
the volumes add up, and nothing more.

```
python tools/audit_domain_bed_feedback.py --seed 20261020 \\
    --point 0 30000 --point 0 40000 --rain-mm-h 4 --dt-s 3600 --intervals 4 \\
    --report out/audit.json
```
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

from terrain_pipeline.hydrology_planning import PlanningConfig  # noqa: E402
from terrain_pipeline.mountain_source_adapter import identity  # noqa: E402
from terrain_pipeline.surface_rivers.metric_domain_bed_feedback import (  # noqa: E402
    BED_FEEDBACK_SCHEMA,
    PRODUCT_KEYS,
    load_domain_bed_feedback,
    solve_domain_bed_feedback,
)
from terrain_pipeline.surface_rivers.metric_domain_closure import clear_cache  # noqa: E402
from terrain_pipeline.surface_rivers.metric_domain_coupled import (  # noqa: E402
    COUPLED_SCHEMA,
    CoupledParameters,
    load_domain_coupled,
    solve_domain_coupled,
)

AUDIT_SCHEMA = "domain-bed-feedback-audit-v1"


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
    parser.add_argument("--parent-product", help="saved coupled .npz (parent)")
    parser.add_argument("--parent-sha256", help="required with --parent-product")
    parser.add_argument("--product", help="saved bed feedback .npz")
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
    if (args.product and not args.product_sha256) or \
            (args.parent_product and not args.parent_sha256):
        print("FAILED: a saved product needs its sha256", file=sys.stderr)
        return 2

    config = PlanningConfig()
    checks = []
    try:
        clear_cache()
        if args.parent_product:
            parent = load_domain_coupled(args.parent_product,
                                        expected_sha256=args.parent_sha256)
            parent_source = "saved coupled product (cold reload)"
        else:
            parent = solve_domain_coupled(args.seed, points, args.rain_mm_h,
                                          config=config,
                                          parameters=CoupledParameters(),
                                          dt_s=args.dt_s, intervals=args.intervals)
            parent_source = "fresh coupled solve"

        if args.product:
            record = load_domain_bed_feedback(args.product,
                                             expected_sha256=args.product_sha256)
            source = "saved bed feedback product (cold reload)"
        else:
            record = solve_domain_bed_feedback(parent)
            source = "derived from the coupled parent in memory"
        arrays = record["arrays"]
        metadata = record["metadata"]
        totals = metadata["totals"]

        # ---- 1. schema, parent binding, declarations --------------------------
        check(checks, "arrays_carry_exactly_the_contract_keys",
              set(arrays) == set(PRODUCT_KEYS),
              {"missing": sorted(set(PRODUCT_KEYS) - set(arrays)),
               "unexpected": sorted(set(arrays) - set(PRODUCT_KEYS))})
        check(checks, "schema_and_parent_schema_are_as_contract",
              metadata.get("schema") == BED_FEEDBACK_SCHEMA
              and metadata.get("parent_schema") == COUPLED_SCHEMA,
              {"schema": metadata.get("schema"),
               "parent_schema": metadata.get("parent_schema")})
        # Recompute BOTH identities: neither product may have been edited after
        # publication, and the recorded parent link must point at that identity.
        parent_identity = identity(parent["arrays"], parent["metadata"])
        check(checks, "parent_identity_recomputes",
              parent_identity == parent["identity_sha256"],
              {"recomputed": parent_identity, "carried": parent["identity_sha256"]})
        check(checks, "bed_product_identity_recomputes",
              identity(arrays, metadata) == record["identity_sha256"],
              {"carried": record["identity_sha256"]})
        check(checks, "parent_link_points_at_the_parent_identity",
              metadata.get("parent_identity_sha256") == parent["identity_sha256"],
              {"link": metadata.get("parent_identity_sha256")})
        claims = metadata.get("claims", {})
        check(checks, "declares_terrain_feedback_and_no_hydraulics",
              claims.get("terrain_feedback_applied") is True
              and all(claims.get(key) is False for key in
                      ("hydraulic_ready", "natural_outlet_verified", "publishable")),
              dict(claims))
        revalidation = metadata.get("revalidation", {})
        check(checks, "demands_revalidation_and_declares_bed_rejection_absent",
              revalidation.get("needs_geometry_and_hydraulic_revalidation") is True
              and revalidation.get("bed_rejection_applied") is False,
              dict(revalidation))
        check(checks, "placement_rule_is_declared",
              metadata.get("placement_rule") == "uniform_within_domain_over_published_cells",
              metadata.get("placement_rule"))

        # ---- 2. porosity conversion, recomputed --------------------------------
        porosity = float(metadata["parameters"]["porosity"])
        solid = np.asarray(arrays["deposited_solid_m3"], np.float64)
        bulk = np.asarray(arrays["deposited_bulk_m3"], np.float64)
        pore = np.asarray(arrays["pore_m3"], np.float64)
        expected_bulk = solid / (1.0 - porosity)
        scale = max(float(np.sum(expected_bulk, dtype=np.float64)), 1.0)
        worst_bulk = float(np.max(np.abs(bulk - expected_bulk))) if solid.size else 0.0
        check(checks, "bulk_is_solid_over_one_minus_porosity",
              worst_bulk <= 1e-9 * max(scale, 1.0),
              {"porosity": porosity, "worst_absolute_difference_m3": worst_bulk})
        worst_pore = float(np.max(np.abs((bulk - solid) - pore))) if solid.size else 0.0
        check(checks, "pore_is_bulk_minus_solid",
              worst_pore <= 1e-9 * max(scale, 1.0),
              {"worst_absolute_difference_m3": worst_pore})

        # ---- 3. conservation, recomputed from the published depths -------------
        bed_change = np.asarray(arrays["bed_change_m"], np.float64)
        offsets = np.asarray(arrays["cell_offsets"], np.int64)
        cell_area = float(metadata["cell_area_m2"])
        count = int(metadata["domain_count"])
        worst_domain = 0.0
        worst_domain_index = None
        for index in range(count):
            start, stop = int(offsets[index]), int(offsets[index + 1])
            if start == stop:
                continue
            volume = float(np.sum(bed_change[start:stop], dtype=np.float64)) * cell_area
            difference = abs(volume - float(bulk[index]))
            if difference > worst_domain:
                worst_domain = difference
                worst_domain_index = index
        check(checks, "per_domain_depths_sum_to_the_bulk_volume",
              worst_domain <= 1e-6 * scale,
              {"worst_absolute_difference_m3": worst_domain,
               "worst_domain_index": worst_domain_index})
        tile_volume = float(np.sum(bed_change, dtype=np.float64)) * cell_area
        check(checks, "tile_depths_sum_to_the_tile_bulk",
              abs(tile_volume - float(np.sum(bulk, dtype=np.float64))) <= 1e-6 * scale,
              {"from_depths_m3": tile_volume,
               "from_bulk_m3": float(np.sum(bulk, dtype=np.float64))})

        # ---- 4. the cross-product check ---------------------------------------
        # The solid the bed absorbed must be the deposition the coupled ledger
        # reported. This is the check that a bed product cannot pass on its own.
        parent_deposited = float(parent["metadata"]["totals"]["deposited_total_m3"])
        check(checks, "the_bed_absorbed_exactly_the_parents_deposition",
              abs(float(np.sum(solid, dtype=np.float64)) - parent_deposited)
              <= 1e-6 * max(abs(parent_deposited), 1.0),
              {"bed_solid_m3": float(np.sum(solid, dtype=np.float64)),
               "parent_deposited_m3": parent_deposited})

        # ---- 5. accumulation only and the raster ---------------------------------
        check(checks, "no_cell_loses_material",
              bool(np.all(bed_change >= -1e-12)),
              {"min_bed_change_m": float(np.min(bed_change)) if bed_change.size else 0.0})
        raster = np.asarray(arrays["bed_change_raster_m"], np.float64)
        rows, columns = (int(v) for v in metadata["tile_shape"])
        spacing = float(metadata["spacing_m"])
        origin_x, origin_z = (float(v) for v in metadata["tile_origin_m_xz"])
        cells_x = np.asarray(arrays["cells_x_m"], np.float64)
        cells_z = np.asarray(arrays["cells_z_m"], np.float64)
        column_index = np.rint((cells_x - origin_x) / spacing).astype(np.int64)
        row_index = np.rint((cells_z - origin_z) / spacing).astype(np.int64)
        flat = row_index * columns + column_index
        check(checks, "raster_shape_matches_the_tile_lattice",
              raster.shape == (rows * columns,),
              {"shape": list(raster.shape), "expected": rows * columns})
        check(checks, "raster_carries_the_per_cell_change",
              bool(np.array_equal(raster[flat], bed_change)),
              {"nonzero_raster_cells": int(np.count_nonzero(raster))})
        mask = np.zeros(rows * columns, bool)
        mask[flat] = True
        check(checks, "raster_marks_no_cell_outside_the_published_set",
              bool(np.all(raster[~mask] == 0.0)),
              {"cells_outside_set": int(np.count_nonzero(raster[~mask]))})

        # ---- 6. the reported totals agree with the recomputation -----------------
        for name, expected in (("deposited_solid_total_m3", float(np.sum(solid))),
                               ("deposited_bulk_total_m3", float(np.sum(bulk))),
                               ("pore_total_m3", float(np.sum(pore)))):
            check(checks, "totals_%s_equals_the_recomputation" % name,
                  abs(float(totals[name]) - expected) <= 1e-6 * max(abs(expected), 1.0),
                  {"reported": totals[name], "recomputed": expected})
        check(checks, "reported_max_bed_change_matches_the_array",
              (not bed_change.size)
              or abs(float(totals["max_bed_change_m"]) - float(np.max(bed_change)))
              <= 1e-12 * max(1.0, float(np.max(bed_change))),
              {"reported": totals["max_bed_change_m"]})
        check(checks, "conservation_residual_is_zero",
              abs(float(totals["conservation_residual_m3"])) <= 1e-6 * scale,
              {"reported": totals["conservation_residual_m3"]})

        # ---- 7. alignment with the parent ---------------------------------------
        same_cells = all(
            np.array_equal(np.asarray(arrays[key]), np.asarray(parent["arrays"][key]))
            for key in ("cells_x_m", "cells_z_m", "cell_offsets", "cell_count",
                        "outlet_x_m", "outlet_z_m", "kind"))
        check(checks, "published_cells_are_the_parents_cells_unchanged", same_cells,
              "cell anchors, offsets, counts, outlets and kinds carried verbatim")
    except Exception as error:  # noqa: BLE001 -- the report must record the failure
        checks.append({"check": "audit_ran_to_completion", "passed": False,
                       "detail": "%s: %s" % (type(error).__name__, error)})
        passed = False
        source = locals().get("source", "unknown")
        parent_source = locals().get("parent_source", "unknown")
        metadata = locals().get("metadata", {})
        totals = locals().get("totals", {})
    else:
        passed = all(item["passed"] for item in checks)
        checks.append({"check": "audit_ran_to_completion", "passed": True, "detail": None})
        passed = all(item["passed"] for item in checks)

    report = {
        "schema": AUDIT_SCHEMA,
        "seed": int(args.seed),
        "source": source,
        "parent_source": parent_source,
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
            "the placement rule (uniform within a domain) is a declaration, not a "
            "claim about where material settled; the auditor checks the volumes and "
            "that the product says so",
            "bed_rejection cannot be audited because neither product publishes a "
            "receiver, water depth or rock floor",
            "no hydraulic consequence is certified; a changed bed invalidates the "
            "hydraulics that produced the deposition",
            "this auditor writes no product and modifies no terrain",
        ],
    }
    path = Path(args.report)
    if path.exists():
        print("FAILED: report already exists at %s; refusing to overwrite" % path,
              file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
                    encoding="utf-8")

    for item in checks:
        print("%s  %s%s" % ("PASS" if item["passed"] else "FAIL", item["check"],
                             "" if item["detail"] is None else "  %s" % (item["detail"],)))
    print("%d/%d checks PASS" % (report["passed_count"], report["check_count"]))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(run())
