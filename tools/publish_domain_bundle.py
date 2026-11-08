"""Publish the explicitly invoked default consumer bundle with ledgers and derived bed feedback.

This is the user-designated default consumer entry point for explicitly requested bundle
publication. It requires caller-supplied coordinates and `--output-dir`; it is not an
automatic infinite-world scheduler and does not wire Java/Minecraft or background generation.

The index role `production_default_consumer_unvalidated` records entry-point selection only.
It does not certify terrain, hydrology or stage completion. Every ledger retains
`hydraulic_ready` / `natural_outlet_verified` / `publishable` = false. The finite-tile gate,
product limitations and explicit CLI/overwrite refusals remain in force.

Each publish cold-reloads every file and re-derives its identity. Ledgers are per tile, not
per domain; the domain products are per outlet.

Example:

    python tools/publish_domain_bundle.py --seed 20261020 `
        --point 170000 10000 --rain-mm-h 4 --dt-s 3600 --intervals 4 `
        --output-dir out/bundle-20261021

Exit code 0 on successful bundle creation, 1 on cold-read failure, 2 on invalid input, finite-tile
gate refusal or refused overwrite.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from terrain_pipeline.hydrology_planning import PlanningConfig  # noqa: E402
from terrain_pipeline.surface_rivers.metric_domain_closure import (  # noqa: E402
    clear_cache, domain_topology,
)
from terrain_pipeline.surface_rivers.metric_domain_closed_gate import (  # noqa: E402
    check_domain_closed,
)
from terrain_pipeline.surface_rivers.metric_domain_coupled import (  # noqa: E402
    CoupledParameters, load_domain_coupled, save_domain_coupled, solve_domain_coupled,
)
from terrain_pipeline.surface_rivers.metric_domain_bed_feedback import (  # noqa: E402
    load_domain_bed_feedback, save_domain_bed_feedback, solve_domain_bed_feedback,
)
from terrain_pipeline.surface_rivers.metric_domain_flow import (  # noqa: E402
    load_domain_flow, save_domain_flow, solve_domain_flow,
)
from terrain_pipeline.surface_rivers.metric_domain_pipeline import (  # noqa: E402
    config_identity, node_spacing_m, resolve_domain_products,
)
from terrain_pipeline.surface_rivers.metric_domain_sediment import (  # noqa: E402
    load_domain_sediment, save_domain_sediment, solve_domain_sediment,
)

BUNDLE_SCHEMA = "river-domain-bundle-v1"

# Repeated into every bundle index. The bundle index is the first thing a reader
# opens, so it is the right place to say what the bundle does NOT certify.
LIMITATIONS = (
    "candidate bundle contains whole-tile ledgers; only point-selected domains were checked by the finite-tile closure gate",
    "unselected domains included in tile ledgers are auxiliary and are not closure-gate validated; bundle does not certify the entire tile",
    "user-designated production default consumer entry point, invoked explicitly by CLI; "
    "not an automatic infinite-world scheduler or Java/Minecraft connection",
    "role production_default_consumer_unvalidated identifies default entry selection only; "
    "it does not certify terrain or hydrology",
    "every published ledger still declares hydraulic_ready, natural_outlet_verified "
    "and publishable false; this bundle does not upgrade any of them",
    "finite-tile closure gate certifies only point-selected domains, not every domain "
    "in the per-tile ledgers; it does not certify unknown upstream outside the built tile",
    "the ledgers are per TILE, not per domain; the domain products are per outlet",
    "sediment and coupled report volumes only; R8 bed feedback is a derived surface, "
    "not a modification of the immutable RAW base face",
    "R8 placement is uniform-within-domain volume redistribution over published cells, "
    "not a reproduction of deposition along the chain",
    "bed feedback does not rerun hydraulics or apply bed_rejection; geometry and "
    "hydraulics need revalidation and phase completion is not certified",
    "routing is instantaneous and volume conserving; it is not a flood wave",
    "the coefficients are declared engineering assumptions, not calibrated values",
)


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _ledger_record(path, record, schema, totals_keys):
    totals = record["metadata"].get("totals", {})
    return {
        "file": str(Path(path).name),
        "sha256": _file_sha256(path),
        "identity_sha256": record["identity_sha256"],
        "schema": schema,
        "algorithm": record["metadata"].get("algorithm"),
        "domain_count": int(record["metadata"].get("domain_count", 0)),
        "interval_count": int(record["metadata"].get("interval_count", 0)),
        "claims": dict(record["metadata"].get("claims", {})),
        "totals": {key: totals[key] for key in totals_keys if key in totals},
    }


def _bed_feedback_record(path, record):
    result = _ledger_record(path, record, record["metadata"]["schema"],
                            ("deposited_solid_total_m3", "deposited_bulk_total_m3",
                             "conservation_residual_m3", "changed_cells"))
    for key in ("parent_identity_sha256", "parent_schema", "placement_rule", "revalidation"):
        result[key] = record["metadata"][key]
    result["status"] = "derived_bed_candidate_requires_revalidation"
    return result


def _claims_are_safe(kind, record):
    metadata = record["metadata"]
    claims = metadata.get("claims", {})
    if not claims or any(claims.get(key) is not False for key in
                         ("hydraulic_ready", "natural_outlet_verified", "publishable")):
        return False
    if kind != "bed_feedback":
        return all(value is False for value in claims.values())
    revalidation = metadata.get("revalidation", {})
    return (claims.get("terrain_feedback_applied") is True
            and all(value is False for key, value in claims.items()
                    if key != "terrain_feedback_applied")
            and revalidation.get("needs_geometry_and_hydraulic_revalidation") is True
            and revalidation.get("bed_rejection_applied") is False)


def _tile_dir(root, origin_x, origin_z, spacing):
    index_x = int(round(float(origin_x) / spacing))
    index_z = int(round(float(origin_z) / spacing))
    return Path(root) / "tiles" / ("tile_%d_%d" % (index_x, index_z))


# The legacy planning-chain publisher. Its arguments, refusals and publications are unchanged; it
# is now reachable only through the explicit `--legacy-coarse` switch.
def _run_legacy_coarse(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--point", nargs="+", action="append", metavar="X", required=True)
    parser.add_argument("--rain-mm-h", type=float, default=4.0)
    parser.add_argument("--dt-s", type=float, default=3600.0)
    parser.add_argument("--intervals", type=int, default=4)
    parser.add_argument("--output-dir", required=True)
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
    if args.rain_mm_h < 0 or args.dt_s <= 0 or args.intervals < 1:
        print("FAILED: invalid rain/dt/intervals", file=sys.stderr)
        return 2

    # The closure lattice is NOT the terrain grid and carries no scale knob here.
    # `metric_domain_closure` is a 7680 m conditioning lattice (30 m x latent 8 x
    # coarse 32); shrinking its node spacing to 30 m collapses the core span to
    # 7.68 km and the drainage margin to 1.44 km, which was measured to refuse
    # 100% of cells. The native 30 m mechanism lives in `metric_cross_region`.
    # This entry point therefore keeps PlanningConfig's single declared default.
    config = PlanningConfig()
    config.validate()
    # Preserve coupled's calibrated runoff default and share that exact object.
    coupled_parameters = CoupledParameters()
    runoff_parameters = coupled_parameters.runoff
    spacing = node_spacing_m(config)
    root = Path(args.output_dir)
    bundle_path = root / "bundle.json"
    if bundle_path.exists():
        print("FAILED: bundle already exists at %s; refusing to overwrite" % bundle_path,
              file=sys.stderr)
        return 2
    # Refuse boundary-dependent selections before creating any directory or
    # publishing a domain product/ledger. Existing products are never deleted.
    try:
        clear_cache()
        closed_gate = check_domain_closed(args.seed, points, config=config)
    except (ValueError, OverflowError) as error:
        print("FAILED: invalid closure selection: %s" % error, file=sys.stderr)
        return 2
    finally:
        clear_cache()
    if not closed_gate["passed"]:
        print("FAILED: finite-tile closure gate: %s" % json.dumps(
            closed_gate, sort_keys=True), file=sys.stderr)
        return 2
    root.mkdir(parents=True, exist_ok=True)

    checks = []

    def check(name, ok, detail=None):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})
        return bool(ok)

    try:
        clear_cache()
        # ---- domain products (the pipeline's own publication) -----------------
        domain_dir = root / "domains"
        batch = resolve_domain_products(args.seed, points, config=config,
                                        output_dir=domain_dir)
        domain_index = batch.index_record()
        check("domain_products_published",
              int(domain_index["domain_count"]) > 0,
              {"domains": int(domain_index["domain_count"]),
               "refusals": int(domain_index["refused_points"])})

        # ---- group the points by world-anchored tile -------------------------
        # The ledgers are per tile, so the bundle must not silently collapse two
        # tiles into one product: each distinct tile is published separately.
        tiles = {}
        for x_m, z_m in points:
            topology = domain_topology(args.seed, x_m, z_m, config)
            key = (float(topology["origin_x_m"]), float(topology["origin_z_m"]))
            tiles.setdefault(key, []).append((x_m, z_m))
        check("points_group_into_tiles", len(tiles) >= 1, {"tiles": len(tiles)})

        tile_records = []
        published = []
        for (origin_x, origin_z) in sorted(tiles):
            tile_points = tiles[(origin_x, origin_z)]
            directory = _tile_dir(root, origin_x, origin_z, spacing)
            directory.mkdir(parents=True, exist_ok=True)

            flow = solve_domain_flow(args.seed, tile_points, args.rain_mm_h, config=config,
                                     parameters=runoff_parameters,
                                     dt_s=args.dt_s, intervals=args.intervals)
            sediment = solve_domain_sediment(args.seed, tile_points, config=config,
                                             intervals=args.intervals)
            coupled = solve_domain_coupled(args.seed, tile_points, args.rain_mm_h,
                                           parameters=coupled_parameters,
                                           config=config, dt_s=args.dt_s,
                                           intervals=args.intervals)
            bed_feedback = solve_domain_bed_feedback(coupled)

            flow_path = directory / "flow.npz"
            sediment_path = directory / "sediment.npz"
            coupled_path = directory / "coupled.npz"
            bed_feedback_path = directory / "bed_feedback.npz"
            save_domain_flow(flow_path, flow)
            save_domain_sediment(sediment_path, sediment)
            save_domain_coupled(coupled_path, coupled)
            save_domain_bed_feedback(bed_feedback_path, bed_feedback)

            gate_tile = next(item for item in closed_gate.get("tiles", [])
                             if item["origin_x_m"] == origin_x
                             and item["origin_z_m"] == origin_z)
            selected_gate_domains = int(gate_tile["selected_domains"])
            ledger_domain_count = int(flow["metadata"]["domain_count"])
            tile_records.append({
                "origin_x_m": origin_x,
                "origin_z_m": origin_z,
                "directory": str(directory.relative_to(root)).replace("\\", "/"),
                "points": [[float(x), float(z)] for x, z in tile_points],
                "domain_count": ledger_domain_count,
                "closure_gate_coverage": {
                    "scope": "point_selected_domains_only",
                    "selected_domains_checked": selected_gate_domains,
                    "unselected_domains_in_ledgers_unchecked": max(
                        0, ledger_domain_count - selected_gate_domains),
                    "whole_tile_certified": False,
                },
                "ledgers": {
                    "bed_feedback": _bed_feedback_record(bed_feedback_path, bed_feedback),
                    "flow": _ledger_record(flow_path, flow, flow["metadata"]["schema"],
                                           ("requested_rain_m3", "routed_rain_m3",
                                            "released_total_m3", "exported_to_sea_m3",
                                            "retained_in_basins_m3")),
                    "sediment": _ledger_record(sediment_path, sediment,
                                               sediment["metadata"]["schema"],
                                               ("weathered_total_m3", "entrained_total_m3",
                                                "deposited_total_m3", "delivered_total_m3",
                                                "stranded_on_refused_m3")),
                    "coupled": _ledger_record(coupled_path, coupled,
                                              coupled["metadata"]["schema"],
                                              ("water_release_total_m3",
                                               "capacity_volume_total_m3",
                                               "capacity_violation_m3",
                                               "capacity_utilisation",
                                               "entrained_total_m3",
                                               "delivered_total_m3")),
                },
            })
            products = [
                ("flow", flow_path, flow, load_domain_flow),
                ("sediment", sediment_path, sediment, load_domain_sediment),
                ("coupled", coupled_path, coupled, load_domain_coupled),
                ("bed_feedback", bed_feedback_path, bed_feedback, load_domain_bed_feedback),
            ]
            published.extend((kind, path, record, loader,
                              tile_records[-1]["ledgers"][kind]["sha256"])
                             for kind, path, record, loader in products)

        # ---- cold reload: a publish that cannot be read back has failed ------
        identity_mismatches = []
        for kind, path, record, loader, digest in published:
            reloaded = loader(path, expected_sha256=digest,
                              expected_identity=record["identity_sha256"])
            if reloaded["identity_sha256"] != record["identity_sha256"]:
                identity_mismatches.append({"kind": kind, "file": str(path)})
            if kind == "bed_feedback":
                parent = next(item[2] for item in published
                              if item[0] == "coupled" and item[1].parent == path.parent)
                check("bed_feedback_parent_binding", reloaded["metadata"].get(
                    "parent_identity_sha256") == parent["identity_sha256"], str(path))
            check("%s_readiness_contract" % kind, _claims_are_safe(kind, reloaded), str(path))
        check("every_published_ledger_cold_reloads", not identity_mismatches,
              {"files": len(published), "mismatches": identity_mismatches})

        if domain_index.get("index"):
            domain_index_path = Path(domain_index["index"])
            check("domain_index_cold_reloads", domain_index_path.exists(),
                  {"index": str(domain_index_path)})

        claims_safe = all(_claims_are_safe(kind, record)
                          for kind, _, record, _, _ in published)
        check("no_published_ledger_claims_publishability", claims_safe,
              "only derived bed terrain_feedback_applied may be true; all hydraulic "
              "claims remain false and bed feedback requires revalidation")
    except Exception as error:  # noqa: BLE001 -- the index must record the failure
        checks.append({"check": "publish_ran_to_completion", "passed": False,
                       "detail": "%s: %s" % (type(error).__name__, error)})
        tile_records = locals().get("tile_records", [])
        domain_index = locals().get("domain_index", {})
    else:
        checks.append({"check": "publish_ran_to_completion", "passed": True, "detail": None})
    finally:
        clear_cache()

    passed = all(item["passed"] for item in checks)
    index = {
        "schema": BUNDLE_SCHEMA,
        "role": "production_default_consumer_unvalidated",
        "producer": "tools/publish_domain_bundle.py",
        "seed": int(args.seed),
        "config_id": config_identity(config),
        "node_spacing_m": float(spacing),
        "rain_mm_h": float(args.rain_mm_h),
        "dt_s": float(args.dt_s),
        "intervals": int(args.intervals),
        "runoff_parameters": asdict(runoff_parameters),
        "closed_domain_gate": closed_gate,
        "requested_points": len(points),
        "tile_count": len(tile_records),
        "domain_products": {
            "index": str(domain_index.get("index")),
            "schema": domain_index.get("schema"),
            "domain_count": int(domain_index.get("domain_count", 0) or 0),
            "refused_points": int(domain_index.get("refused_points", 0) or 0),
            "product_set_sha256": domain_index.get("product_set_sha256"),
        },
        "tiles": tile_records,
        "checks": checks,
        "check_count": len(checks),
        "passed_count": sum(1 for item in checks if item["passed"]),
        "passed": passed,
        "limitations": list(LIMITATIONS),
    }
    bundle_path.write_text(json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False),
                           encoding="utf-8")

    for item in checks:
        print("%s  %s%s" % ("PASS" if item["passed"] else "FAIL", item["check"],
                             "" if item["detail"] is None else "  %s" % (item["detail"],)))
    print("tiles=%d domains=%d files=%d"
          % (len(tile_records), int(domain_index.get("domain_count", 0) or 0),
             len(tile_records) * 4))
    print("bundle: %s" % bundle_path)
    return 0 if passed else 1


FINITE_ROLE = "production_default_consumer_finite_sample"
FINITE_DESCRIPTION = """Default consumption of the promoted finite-sample product.

Without `--legacy-coarse` this entry point answers questions about the already published finite
event (3951-cell drainage set, 24 x 900 s, one bounded lake) and never solves, generates terrain or
writes into the product. Points are world metres by default; `--native` reads them as native 30 m
grid indices. Times are physical seconds in the stored event.

    python tools/publish_domain_bundle.py --point 1267800 1292580 --time-s 900 7200

The legacy 7680 m planning chain is available only through `--legacy-coarse`.
"""


def run(argv=None):
    """Default entry point: finite-sample consumption; the planning chain is explicit."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--legacy-coarse" in arguments:
        return _run_legacy_coarse([value for value in arguments if value != "--legacy-coarse"])
    return _run_finite(arguments)


def _product_module():
    from terrain_pipeline.surface_rivers import finite_river_product
    return finite_river_product


def _run_finite(argv):
    """Read-only query (and explicit recovery) over the promoted finite product."""
    parser = argparse.ArgumentParser(description=FINITE_DESCRIPTION,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--point", nargs=2, action="append", metavar=("X", "Z"), required=True)
    parser.add_argument("--time-s", nargs="+", type=float, required=True,
                        help="physical seconds inside the stored event")
    parser.add_argument("--native", action="store_true",
                        help="read --point as native 30 m grid indices instead of metres")
    parser.add_argument("--product-dir", default=None)
    parser.add_argument("--output-dir", default=None,
                        help="optional report directory; an existing report is refused")
    parser.add_argument("--resume-checkpoint", default=None,
                        help="explicit checkpoint key to resume from, e.g. k8")
    parser.add_argument("--resume-output-dir", default=None)
    arguments = parser.parse_args(argv)
    module = _product_module()
    try:
        product = module.load_product(arguments.product_dir)
    except (ValueError, FileNotFoundError, OSError) as error:
        print("FAILED: product unavailable: %s: %s" % (type(error).__name__, error),
              file=sys.stderr)
        return 2
    if arguments.resume_checkpoint:
        if not arguments.resume_output_dir:
            print("FAILED: --resume-checkpoint needs --resume-output-dir", file=sys.stderr)
            return 2
        return _resume_product(arguments, product, module)
    answers = []
    try:
        for x_text, z_text in arguments.point:
            x, z = float(x_text), float(z_text)
            for time_s in arguments.time_s:
                answers.append(product.query(x, z, float(time_s), native=arguments.native))
    except ValueError as error:
        print("FAILED: query refused: %s" % error, file=sys.stderr)
        return 2
    report = {"schema": FINITE_ROLE + "-v1",
              "role": FINITE_ROLE,
              "producer": "tools/publish_domain_bundle.py",
              "product_dir": str(product.directory),
              "product_sha256": module.sha256_file(product.directory / "product.json"),
              "product_schema": product.meta["schema"],
              "capabilities": dict(product.meta["capabilities"]),
              "source_code_identity": dict(product.meta["source_code_identity"]),
              "limitations": list(product.meta["limitations"]),
              "query_count": len(answers),
              "queries": answers}
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    if arguments.output_dir:
        target = Path(arguments.output_dir) / "query.json"
        if target.exists():
            print("FAILED: report already exists at %s; refusing to overwrite" % target,
                  file=sys.stderr)
            return 2
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


def _resume_product(arguments, product, module):
    """Explicit recovery: continue from a stored checkpoint and publish a stitched product."""
    import numpy as np

    from terrain_pipeline.surface_rivers.finite_river_block_schedule import (
        load_checkpoint, run_block_event,
    )
    key = arguments.resume_checkpoint
    record = product.meta["checkpoints"].get(key)
    if record is None:
        print("FAILED: product carries no checkpoint %r; available %s"
              % (key, sorted(product.meta["checkpoints"])), file=sys.stderr)
        return 2
    parameters = module.checkpoint_parameters(product)
    rain = np.asarray(product.meta["forcing"]["rain_mm_h_by_interval"], np.float64)
    dt_s = float(product.meta["time"]["dt_s"])
    try:
        schedule = module.rebuild_schedule(product)
        manifest = json.loads((product.directory / record["manifest_path"])
                              .read_text(encoding="utf-8"))
        loaded = load_checkpoint(product.directory / Path(record["state_path"]).parent,
                                 schedule=schedule,
                                 expected_interval_index=int(record["interval_index"]),
                                 dt_s=dt_s, parameters=parameters, rain_sequence=rain,
                                 protocol_sha256=manifest["identity"]["protocol_sha256"])
        tail = run_block_event(schedule, loaded["state"],
                               rain[int(record["interval_index"]):], dt_s=dt_s,
                               parameters=parameters,
                               start_index=int(record["interval_index"]))
        arrays = _stitched_arrays(product, module, tail, int(record["interval_index"]))
    except (ValueError, FileNotFoundError, KeyError, OSError) as error:
        print("FAILED: recovery refused: %s: %s" % (type(error).__name__, error),
              file=sys.stderr)
        return 2
    meta = dict(product.meta)
    meta["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    meta["role"] = "finite_sample_explicit_recovery"
    meta["provenance"] = dict(product.meta["provenance"])
    meta["provenance"]["resumed_from"] = {
        "product_dir": str(product.directory),
        "checkpoint": key,
        "interval_index": int(record["interval_index"]),
        "elapsed_s": float(record["elapsed_s"]),
        "state_sha256": record["state_sha256"],
        "continuation": "run_block_event on the same schedule and forcing",
    }
    meta["gates"] = dict(product.meta["gates"])
    meta["gates"]["resume_matches_continuous"] = True
    # the resumed product carries no checkpoint of its own: its state is already the end state
    meta["checkpoints"] = {}
    meta["files"] = {}
    try:
        published = module.write_product(arguments.resume_output_dir, meta=meta, arrays=arrays)
    except FileExistsError as error:
        print("FAILED: refusing to overwrite %s" % error, file=sys.stderr)
        return 2
    print(json.dumps({"schema": FINITE_ROLE + "-resume-v1", "role": meta["role"],
                      "product_dir": published["directory"],
                      "checkpoint": key, "resumed_intervals": int(tail["intervals"]),
                      "files": len(published["files"]),
                      "product_sha256": published["product_sha256"]},
                     indent=2, sort_keys=True))
    return 0


def _stitched_arrays(product, module, tail, boundary):
    """Prefix from the delivered product + suffix from the explicit continuation."""
    import numpy as np

    source = product.arrays
    keys = ("local_q_m3_s", "routed_q_m3_s", "delivered_to_lake_m3", "et_mm_land",
            "release_mm_land")
    arrays = {key: np.array(source[key], copy=True) for key in keys}
    arrays["seconds_edges"] = np.array(source["seconds_edges"], copy=True)
    arrays["rain_mm_h"] = np.array(source["rain_mm_h"], copy=True)
    soil = np.array(source["soil_states_mm"], copy=True)
    lake_volume = np.array(source["lake_volume_m3"], copy=True)
    lake_level = np.array(source["lake_level_m"], copy=True)
    lake_wet = np.array(source["lake_wet_cells"], copy=True)
    for offset, step in enumerate(tail["steps"]):
        index = boundary + offset
        arrays["local_q_m3_s"][index] = step["local_q_m3_s"]
        arrays["routed_q_m3_s"][index] = step["routed_q_m3_s"]
        arrays["delivered_to_lake_m3"][index] = step["ledger"]["delivered_to_lake_m3"]
        arrays["et_mm_land"][index] = step["et_mm_land"]
        arrays["release_mm_land"][index] = step["release_mm_land"]
        soil[index + 1] = step["soil_states_mm"]
        lake_volume[index + 1] = step["lake_volume_m3"]
        lake_level[index + 1] = step["lake"]["level_m"]
        lake_wet[index + 1] = step["lake"]["wet_cells"]
    arrays["soil_states_mm"] = soil
    arrays["lake_volume_m3"] = lake_volume
    arrays["lake_level_m"] = lake_level
    arrays["lake_wet_cells"] = lake_wet
    for key in ("active_index", "land_index", "lake_bed_index", "head_path_index"):
        arrays[key] = np.array(source[key], copy=True)
    for key, relative in module.DOMAIN_FILES.items():
        arrays[key] = np.load(product.directory / relative)
    for key, relative in module.LAYOUT_FILES.items():
        arrays[key] = np.load(product.directory / relative)
    for key in ("local_q_m3_s", "routed_q_m3_s", "delivered_to_lake_m3", "soil_states_mm",
                "lake_volume_m3", "lake_level_m", "lake_wet_cells", "et_mm_land",
                "release_mm_land"):
        if not np.array_equal(np.asarray(arrays[key]), np.asarray(source[key])):
            raise ValueError("the continuation disagrees with the delivered product on %s" % key)
    return arrays


def main(argv=None):
    return run(argv)


if __name__ == "__main__":
    sys.exit(run())
