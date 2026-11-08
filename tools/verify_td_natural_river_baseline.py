"""Freeze small TD regional diagnostics without claiming natural certification."""

import argparse
from dataclasses import replace
import importlib.metadata
import json
import platform
from pathlib import Path
import tempfile
import time
import tracemalloc

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity, load_bundle, validate_source
from terrain_pipeline.common_infra import BoundaryGrid, RainfallForcing, TerrainGrid
from terrain_pipeline.drainage import accumulate_local_discharge as accumulate_local_discharge
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from terrain_pipeline.surface_rivers.metric_source import (
    load_source_registration, register_source, save_source_registration,
)
from terrain_pipeline.surface_rivers.metric_large_source import stitch_tiles
from terrain_pipeline.surface_rivers.metric_product import build_diagnostic_product
from terrain_pipeline.surface_rivers.metric_naturalness_audit import (
    geometry_metrics, compare_frozen_samples, sample_summary, channel_graph_observations,
)
from terrain_pipeline.basin_storage import PRIMARY_PATH as PRIMARY_PATH
from terrain_pipeline.basin_storage import PRIMARY_SHA256 as PRIMARY_SHA256
from terrain_pipeline.basin_storage import load_td_source as load_td_source


CHANNEL_AREA_M2 = 100_000.
QUANTILES = (0., .25, .5, .75, 1.)
ROOT = Path(__file__).resolve().parents[1]
PROCESS_REPORTS = (
    ("water", "verification/td-river-channel/m3-20261008-02/acceptance.json"),
    ("lake", "verification/td-river-lake-coupling/m3-m4-20261008-02/acceptance.json"),
    ("sediment", "verification/td-river-sediment/m6-20261008-03/acceptance.json"),
    ("morphology", "verification/td-morphology-extension/td1024-20261008-03/acceptance.json"),
)


def audit_process_evidence():
    """Bind historical process results and independently attempt current cold readers."""
    from terrain_pipeline.surface_rivers.metric_channel_product import load_channel_product
    from terrain_pipeline.surface_rivers.metric_coupled_product import load_coupled_product
    from terrain_pipeline.surface_rivers.metric_sediment import load_sediment
    from terrain_pipeline.surface_rivers.metric_morphology_coupling import load_morphology_coupling

    records = []
    for module, relative in PROCESS_REPORTS:
        path = ROOT / relative
        if not path.is_file():
            records.append({"module": module, "path": relative, "status": "missing"})
            continue
        historical = json.loads(path.read_text(encoding="utf-8"))
        record = {"module": module, "path": relative, "sha256": file_sha256(path),
                  "historical_status": historical["status"],
                  "historical_cases_not_rerun": historical.get("cases", {}),
                  "historical_thresholds": historical.get("thresholds", {}),
                  "current_cold_reads": []}
        for name, pin in historical.get("artifacts", {}).items():
            artifact = path.parent / pin["path"]
            read = {**pin, "name": name, "path": str(artifact.relative_to(ROOT))}
            try:
                kwargs = {"expected_sha256": pin["sha256"]}
                if module in ("water", "lake"):
                    kwargs["expected_identity"] = pin["identity_sha256"]
                if module == "lake":
                    bundle = load_coupled_product(artifact, **kwargs)
                else:
                    loader = {"water": load_channel_product, "sediment": load_sediment,
                              "morphology": load_morphology_coupling}[module]
                    bundle = loader(artifact, **kwargs)
                if bundle["identity_sha256"] != pin["identity_sha256"]:
                    raise ValueError("historical external identity differs")
                read["status"] = "cold_read_verified"
            except (OSError, ValueError, KeyError, TypeError) as error:
                read.update(status="rejected", reason=type(error).__name__ + ": " + str(error))
            record["current_cold_reads"].append(read)
        record["status"] = "historical_evidence_bound_not_recomputed"
        records.append(record)
    return records


def boundary_for(terrain, policy):
    kinds = np.full(terrain.valid_mask.shape, "interior", dtype="U24")
    kinds[[0, -1], :] = policy
    kinds[:, [0, -1]] = policy
    kinds[~terrain.valid_mask] = "unknown_boundary"
    return BoundaryGrid(kinds, np.zeros(kinds.shape, bool), policy,
                        identity({"kind": kinds}, {"policy": policy}))


def diagnose(terrain, boundary, *, flat_distance_strategy="hop_count", curvature_method="legacy_acos"):
    """Measure the unchanged-bed diagnostic graph; all lengths are in metres."""
    graph = route_diagnostic(terrain, boundary, flat_distance_strategy=flat_distance_strategy)
    valid = terrain.valid_mask.ravel()
    edge = valid & (graph.receiver >= 0)
    cells = np.flatnonzero(edge)
    drops = terrain.elevation_m.ravel()[cells] - terrain.elevation_m.ravel()[graph.receiver[cells]]
    np.testing.assert_allclose(graph.edge_slope[cells], drops / graph.edge_length_m[cells],
                               rtol=0., atol=1e-12)
    area = accumulate_local_discharge(graph, terrain.valid_mask * terrain.cell_area_m2)
    contributing = area["routed_q_m3_s"].ravel()
    terminal = valid & (graph.receiver < 0)
    kinds, counts = np.unique(graph.outlet_kind[terminal], return_counts=True)
    channel = edge & (contributing >= CHANNEL_AREA_M2)
    domain_area = float(valid.sum()) * terrain.cell_area_m2
    statistics = {
        "valid_area_m2": domain_area,
        "terminal_kind_counts": dict(zip(kinds.tolist(), counts.tolist())),
        "terminal_area_residual_m2": float(domain_area - contributing[terminal].sum()),
        "channel_area_threshold_m2": CHANNEL_AREA_M2,
        "diagnostic_drainage_density_m_per_m2": float(graph.edge_length_m[channel].sum() / domain_area),
        "upstream_area_quantiles_m2": np.quantile(contributing[valid], QUANTILES).tolist(),
        "edge_slope_quantiles": np.quantile(graph.edge_slope[edge], QUANTILES).tolist() if edge.any() else [],
        "lake_terminal_count": int(np.count_nonzero(terminal & (graph.outlet_kind == "lake_preserved"))),
    }
    ids = np.flatnonzero(valid)
    lookup = np.full(valid.size, -1, np.int64)
    lookup[ids] = np.arange(ids.size)
    receivers = graph.receiver[ids]
    local_receivers = np.where(receivers >= 0, lookup[np.maximum(receivers, 0)], -1)
    points = np.asarray([terrain.world_xz(int(cell)) for cell in ids])
    tiles = (ids // terrain.valid_mask.shape[1] // 16) * 10000 + (ids % terrain.valid_mask.shape[1] // 16)
    statistics["geometry_observations"] = geometry_metrics(
        points, terrain.elevation_m.ravel()[ids], local_receivers,
        allowed_terminal=np.isin(graph.outlet_kind[ids], ("lake_preserved", "unknown_boundary", "open_outflow",
                                                         "prescribed_stage", "prescribed_discharge")), tile_ids=tiles,
        curvature_method=curvature_method)
    statistics["geometry_observations"]["metric_scope"] = "all_valid_D8_terrain_edges_not_channel_only"
    statistics["channel_geometry_observations"] = channel_graph_observations(
        terrain, graph, contributing, minimum_area_m2=CHANNEL_AREA_M2, curvature_method=curvature_method)
    try:
        from terrain_pipeline.drainage import analyze_td_graph as analyze_td_graph
        reference = analyze_td_graph(terrain, boundary, graph)
        stream = reference.stream_order
        order_ends = valid & (graph.receiver < 0)
        order_ends[cells] = stream[cells] != stream[graph.receiver[cells]]
        orders, counts = np.unique(stream[order_ends], return_counts=True)
        segments = dict(zip(orders.tolist(), counts.tolist()))
        statistics["reference_graph_metrics"] = {
            "status": "observed_diagnostic", "backend": reference.backend,
            "version": reference.version,
            "basin_count": int(np.unique(reference.basin_id[valid]).size),
            "strahler_segment_counts": {str(key): value for key, value in segments.items()},
            "bifurcation_ratios": {str(key): segments[key] / segments[key + 1]
                                   for key in segments if key + 1 in segments},
            "basin_area_quantiles_m2": np.quantile(reference.upstream_area_m2[terminal], QUANTILES).tolist(),
        }
    except ImportError as error:
        statistics["reference_graph_metrics"] = {"status": "dependency_unavailable", "reason": str(error)}
    return graph, statistics


def audit_shared_strips(height):
    """Exercise the established overlap seam auditor on exact native TD samples."""
    tiles = {}
    for row in range(2):
        for col in range(2):
            patch = height[row * 16:row * 16 + 17, col * 16:col * 16 + 17].astype(np.float64)
            tiles[row, col] = (patch, np.zeros((5, 17, 17)))
    _, _, clean = stitch_tiles(tiles, seam_tolerance_m=0.)
    bad = {key: (value[0].copy(), value[1].copy()) for key, value in tiles.items()}
    bad[0, 1][0][:, 0] += 1.
    _, _, shifted = stitch_tiles(bad, seam_tolerance_m=0.)
    if not clean["accepted"] or shifted["accepted"]:
        raise AssertionError("shared strip mismatch was not detected")
    return {"native_shared_strip_sha256": identity({str(key): value[0] for key, value in tiles.items()}, {}),
            "exact_native_overlap": clean, "synthetic_shifted_strip": shifted,
            "hydrologic_seam_certified": False}


def runoff_scenarios(terrain):
    """Domain-size, rainfall and explicit boundary-policy sensitivity, no calibration."""
    records = []
    for side in (16, 32):
        local = replace(terrain, elevation_m=terrain.elevation_m[:side, :side].copy(),
                        valid_mask=terrain.valid_mask[:side, :side].copy())
        for policy in ("closed_wall", "open_outflow"):
            boundary = boundary_for(local, policy)
            for name, intensity in (("dry", 0.), ("rain", 30.), ("storm", 90.)):
                rainfall = np.zeros((3,) + local.valid_mask.shape)
                rainfall[0, local.valid_mask] = intensity
                forcing = RainfallForcing(np.array([0., 300., 600., 900.]), rainfall,
                                          name, identity({"rain": rainfall}, {"scenario": name}))
                started = time.perf_counter()
                product = build_diagnostic_product(local, boundary, forcing)
                records.append({"source_id": terrain.source_id, "domain_shape_zx": [side, side],
                                "native_spacing_m": [local.dx_m, local.dz_m],
                                "scale_semantics": "domain_extent_only_not_resolution_convergence_or_AMR",
                                "terrain_identity_sha256": local.identity_sha256,
                                "terrain_provenance": local.metadata(),
                                "rainfall_scenario": name, "first_interval_rain_mm_h": intensity,
                                "boundary_policy_ablation": policy,
                                "forcing_identity_sha256": forcing.identity_sha256,
                                "product_identity_sha256": product["identity_sha256"],
                                "budget_m3": product["metadata"]["water_budget_m3"],
                                "elapsed_seconds": time.perf_counter() - started,
                                "status": "native_runoff_diagnostic_not_channel_hydraulics"})
    return records


def prepare_stage1_reference(output):
    """Freeze the real DEM empirical samples before opening any new TD comparison."""
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    dem_path = ROOT / "verification/dem-domain/run-20261001T135530750135Z/dem-candidate.npz"
    verified_reference_path = ROOT / "verification/td-natural-river-stages/reference-baseline-02/reference.json"
    verified = json.loads(verified_reference_path.read_text(encoding="utf-8"))
    if file_sha256(dem_path) != verified["dem"]["source"]["sha256"]:
        raise ValueError("DEM differs from source-replayed reference pin")
    with np.load(dem_path, allow_pickle=False) as archive:
        manifest = json.loads(str(archive["manifest"].item()))
        grid = manifest["identity"]["grid"]
        terrain = TerrainGrid(archive["height_m"][:96, :96].astype(np.float64),
                              archive["valid_mask"][:96, :96].copy(),
                              grid["origin_x_m"], grid["origin_z_m"], 90., 90.,
                              "observed_dem", "local-srtm-fixed-window", file_sha256(dem_path),
                              source_path=str(dem_path))
    _, metrics = diagnose(terrain, boundary_for(terrain, "unknown_boundary"))
    observed = metrics["geometry_observations"]
    frozen = {"schema": "metric-naturalness-frozen-reference-v1",
              "source": {"path": str(dem_path), "sha256": file_sha256(dem_path),
                         "manifest_identity_sha256": manifest["identity_sha256"]},
              "source_verification": {"reference_path": str(verified_reference_path),
                                      "reference_sha256": file_sha256(verified_reference_path),
                                      "scope": "reuse_reference_preparation_source_replay_evidence"},
              "selection": {"window_zx": [0, 96, 0, 96], "selection_reason": "fixed northwest window before new TD comparison"},
              "conditions": {"spacing_m": 90., "domain_shape_zx": [96, 96],
                             "sampling": "saved_UTM90m_target_grid_from_angular_SRTM_exact_inverse_center_nearest_source_cell",
                             "boundary": "imposed_unknown", "climate": "unknown",
                             "terrain_class": "SRTM_local_coastal_window_121.25_to_121.65E_29.15_to_29.65N",
                             "comparison_scope": "same_scale_original_bed_diagnostic_geometry_not_hydraulic_naturalness"},
              "metric_definition": {"quantile_probs": [.05, .25, .5, .75, .95],
                                    "channel_area_threshold_m2": CHANNEL_AREA_M2,
                                    "interval_policy": "empirical_q05_q95_review_only_not_universal_acceptance",
                                    "absolute_tolerance": 1e-9},
              "metrics": {name: {"review_interval": [record["quantiles"][0], record["quantiles"][-1]],
                                  "absolute_tolerance": 1e-9, "reference_observation": record}
                          for name, record in observed.items() if isinstance(record, dict) and record.get("count", 0)},
              "diagnostic_graph_statistics": metrics, "publishable": False,
              "code_sha256": file_sha256(__file__)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(frozen, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return frozen


def grid_reference_conditions_match(reference, terrain):
    condition = reference["conditions"]
    return (condition.get("spacing_m") == terrain.dx_m == terrain.dz_m
            and condition.get("domain_shape_zx") == list(terrain.elevation_m.shape)
            and condition.get("boundary") == "imposed_unknown"
            and condition.get("comparison_scope") == "same_scale_original_bed_diagnostic_geometry_not_hydraulic_naturalness"
            and reference["metric_definition"].get("channel_area_threshold_m2") == CHANNEL_AREA_M2)


def evaluate_stage1_reference(reference_path, output):
    """Consume a previously frozen reference and explicitly sampled independent TD seeds."""
    reference_path, output = Path(reference_path), Path(output)
    if output.exists():
        raise FileExistsError(output)
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    inventory_path = ROOT / "verification/td-natural-river-stages/reference-baseline-02/td-source-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    cases = []
    for seed in ("20260930", "20260931"):
        path = ROOT / ("verification/height-budget-v5/run-20260929T103819083596Z/screen-3/seed" + seed + "-x0-z0.npz")
        # The reference preparation verified generation-report archive pins.
        matching = [entry for entry in inventory if Path(entry["path"]).resolve() == path.resolve()]
        if len(matching) != 1 or file_sha256(path) != matching[0]["sha256"]:
            raise ValueError("TD source absent from verified inventory")
        with np.load(path, allow_pickle=False) as archive:
            meta = json.loads(str(archive["metadata"].item()))
            config = json.loads(str(archive["generation_config"].item()))
            height = archive["elevation"][:288:3, :288:3].astype(np.float64)
        terrain = TerrainGrid(height, np.isfinite(height), 0., 0., 90., 90., "generated_terrain",
                              "td-v5-" + seed + "-diagnostic-subsample", file_sha256(path),
                              generation_seed=int(seed), source_path=str(path),
                              condition_summary=identity({}, config))
        _, metrics = diagnose(terrain, boundary_for(terrain, "unknown_boundary"))
        matched = grid_reference_conditions_match(reference, terrain)
        cases.append({"seed": seed, "source": {"path": str(path), "sha256": file_sha256(path),
                                               "generation_metadata": meta, "generation_config": config},
                      "representation": "every_third_native30m_sample_90m_diagnostic_not_volume_basis",
                      "limitations": ["subsampling_aliases_fine_relief", "climate_not_available",
                                      "TD_geographic_v5_not_observed_coastal_class"],
                      "grid_conditioned_comparison": compare_frozen_samples(metrics["geometry_observations"], reference,
                                                                           conditions_match=matched),
                      "grid_conditions_match": matched,
                      "source_verification_inventory_sha256": file_sha256(inventory_path),
                      "naturalness_conditions": {"status": "not_comparable", "reason": "climate_and_terrain_class_not_matched"},
                      "metrics": metrics})
    geometry_path = ROOT / "verification/td-river-geometry/m5-20261008-06/acceptance.json"
    geometry_manifest = json.loads(geometry_path.read_text(encoding="utf-8"))
    geometry_observations = []
    from terrain_pipeline.channel_geometry import load_channel_geometry
    for name in ("td_fine", "td_bend_fine", "td_lake_fine"):
        pin = geometry_manifest["artifacts"][name]
        path = geometry_path.parent / pin["path"]
        bundle = load_channel_geometry(path, expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
        arrays = bundle["arrays"]
        # Node center bed is sampled from the canonical mesh by the existing verifier.
        from tools.verify_td_river_sediment import sample_saved_mesh
        bed = sample_saved_mesh(bundle, arrays["node_xz_m"])
        geometry_observations.append({**pin, "case": name, "path": str(path),
                                      "metrics": geometry_metrics(arrays["node_xz_m"], bed, arrays["receiver"],
                                                                  width_m=arrays["width_m"], depth_m=arrays["depth_m"]),
                                      "section_semantics": "designed_incised_channel_width_cut_depth_not_observed_wet_section",
                                      "USGS_comparison_status": "not_comparable_to_measured_current_flow_mean_depth"})
    report = {"schema": "td-stage1-frozen-reference-comparison-v1",
              "reference": {"path": str(reference_path), "sha256": file_sha256(reference_path)},
              "cases": cases, "saved_channel_geometry": geometry_observations,
              "stage1_audit_status": "completed_with_observed_pass_fail_and_condition_limits",
              "natural_credible": False, "publishable": False}
    primary_path = ROOT / "verification/td-natural-river-stages/reference-baseline-02/reference.json"
    primary = json.loads(primary_path.read_text(encoding="utf-8"))
    curves, orders = [], []
    for reach in primary["hydrorivers"]["reaches"]:
        attributes = reach["attributes"]
        if "ORD_STRA" in attributes:
            orders.append(float(attributes["ORD_STRA"]))
        for part in reach["parts_xz_m"]:
            points = np.asarray(part, np.float64)
            if len(points) < 3:
                continue
            points = points[np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > 0.]]
            downstream = np.arange(1, len(points) + 1, dtype=np.int64)
            downstream[-1] = -1
            measured = geometry_metrics(points, np.zeros(len(points)), downstream)
            curves.extend(measured["curvature_rad_per_m"]["samples"])
    report["primary_reference_context"] = {
        "path": str(primary_path), "sha256": file_sha256(primary_path),
        "usgs_station_groups": primary["usgs"]["groups"],
        "hydrorivers_curvature_rad_per_m": sample_summary(curves),
        "hydrorivers_strahler_order": sample_summary(orders),
        "comparison_status": "not_comparable_different_map_resolution_terrain_climate_and_section_semantics",
        "reference_limitations": "HydroRIVERS DEM-derived mapped centerlines; USGS current-flow mean depth, not bankfull or incision depth"}
    report["primary_reference_context"]["dem_sampling_semantics"] = primary["dem"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def run_case(name, terrain, boundary, conditions, output):
    started = time.perf_counter()
    tracemalloc.start()
    registration = register_source(terrain, boundary)
    path = output / (name + "-source.npz")
    save_source_registration(path, registration)
    cold = load_source_registration(path, expected_sha256=file_sha256(path),
                                    expected_identity=registration["identity_sha256"])
    graph, metrics = diagnose(cold["terrain"], cold["boundary"])
    repeated, repeated_metrics = diagnose(terrain, boundary)
    if graph.identity_sha256 != repeated.identity_sha256 or metrics != repeated_metrics:
        raise AssertionError("same source diagnostic is not repeatable")
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return {"case": name, "conditions": conditions, "metrics": metrics,
            "source_sha256": terrain.source_sha256,
            "terrain_identity_sha256": terrain.identity_sha256,
            "boundary_identity_sha256": boundary.identity_sha256,
            "graph_identity_sha256": graph.identity_sha256,
            "registration_identity_sha256": registration["identity_sha256"],
            "registration_file_sha256": file_sha256(path),
            "elapsed_seconds": time.perf_counter() - started,
            "python_traced_peak_bytes": peak,
            "memory_scope": "tracemalloc Python allocations; not process RSS",
            "cold_read_verified": True, "same_source_repeatable": True,
            "status": "diagnostic", "natural_outlet_verified": False}


def prepare(output, *, include_process_evidence=True):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    source = load_td_source()
    original = load_bundle(PRIMARY_PATH, expected_sha256=PRIMARY_SHA256, validator=validate_source)
    source_metadata = original["metadata"]
    generation = source_metadata["provenance"]["generation_metadata"]
    height, valid = source["arrays"]["height_m"], source["arrays"]["valid_mask"]
    spacing = source["metadata"]["spacing_m"]
    origin = source["metadata"]["origin_m_xz"]
    cases = []
    # Nonoverlapping fixed windows are regions, not independent TD seeds.
    for index, (row, col) in enumerate(((0, 0), (height.shape[0] - 32, height.shape[1] - 32))):
        window = np.s_[row:row + 32, col:col + 32]
        terrain = TerrainGrid(height[window].copy(), valid[window].copy(),
                              origin[0] + col * spacing, origin[1] + row * spacing,
                              spacing, spacing, "generated_terrain", "pinned-td-region-" + str(index),
                              PRIMARY_SHA256, source_path=str(PRIMARY_PATH),
                              vertical_datum=source_metadata["vertical_datum"],
                              model_version=generation["model"]["revision"],
                              generation_seed=int(generation["seed"]),
                              condition_summary=generation["conditioning_identity"])
        for policy in ("unknown_boundary", "closed_wall", "open_outflow"):
            cases.append(("td-region-" + str(index) + "-" + policy, terrain,
                          boundary_for(terrain, policy),
                          {"window_zx": [row, row + 32, col, col + 32],
                           "review_role": "baseline" if index == 0 else "held_out_region_same_seed",
                           "spacing_m": spacing, "climate": "unknown",
                           "terrain_class": "unclassified_td", "boundary": "imposed_" + policy}))
    basin = np.array([[4., 3., 4.], [3., 0., 3.], [4., 3., 4.]])
    terrain = TerrainGrid(basin, np.ones(basin.shape, bool), 0., 0., 100., 100.,
                          "diagnostic_dem_proxy", "synthetic-closed-basin",
                          identity({"height_m": basin}, {}))
    cases.append(("synthetic-no-natural-outflow", terrain, boundary_for(terrain, "closed_wall"),
                  {"spacing_m": 100., "climate": "synthetic", "terrain_class": "closed_basin"}))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        results = [run_case(*case, Path(staging)) for case in cases]
        if results[-1]["metrics"]["terminal_kind_counts"] != {"lake_preserved": 1}:
            raise AssertionError("closed basin was silently drained")
        dependencies = {}
        for name in ("numpy", "pyflwdir"):
            try:
                dependencies[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                dependencies[name] = "unavailable"
        process_evidence = audit_process_evidence() if include_process_evidence else []
        report = {"schema": "td-natural-river-baseline-v1", "status": "diagnostic_baseline",
                  "stage0_status": "reproducible_success_and_explicit_failures",
                  "machine": {"platform": platform.platform(), "python": platform.python_version()},
                  "dependencies": dependencies, "cases": results,
                  "pinned_td_provenance": source_metadata,
                  "process_evidence": process_evidence,
                  "process_evidence_scope": "current_cold_reads" if include_process_evidence else "not_repeated_clean_environment_subset",
                  "native_seam_audit": audit_shared_strips(height),
                  "runoff_sensitivity": [record for case in (cases[0], cases[3])
                                         for record in runoff_scenarios(case[1])],
                  "frozen_metric_definition": {"quantiles": list(QUANTILES),
                                               "channel_area_threshold_m2": CHANNEL_AREA_M2},
                  "code_sha256": file_sha256(__file__),
                  "reference_distribution": None, "publishable": False,
                  "blocker_scope": "natural_certification_of_this_baseline_not_stage0_reproducibility",
                  "blockers": ["No matched climate/terrain-conditioned real basin reference distributions",
                               "No certified natural outlet evidence for imposed region boundaries",
                               "This baseline's two fixed regions share one source; independent seeds audited separately",
                               "This baseline has no channel cross-sections; saved geometry audited separately",
                               "No bounded large-domain RSS budget or cross-scale acceptance intervals"]}
        Path(staging, "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        Path(staging).rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--skip-process-evidence", action="store_true")
    parser.add_argument("--freeze-stage1-reference", action="store_true")
    parser.add_argument("--stage1-reference", type=Path)
    args = parser.parse_args()
    if args.freeze_stage1_reference:
        report = prepare_stage1_reference(args.output)
        print(json.dumps({"status": "reference_frozen", "metric_count": len(report["metrics"])}))
        return
    if args.stage1_reference:
        report = evaluate_stage1_reference(args.stage1_reference, args.output)
        print(json.dumps({"status": report["stage1_audit_status"], "cases": len(report["cases"])}))
        return
    report = prepare(args.output, include_process_evidence=not args.skip_process_evidence)
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]),
                      "blockers": report["blockers"]}))


if __name__ == "__main__":
    main()
