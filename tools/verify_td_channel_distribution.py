"""Freeze real spatial-block channel distributions, then evaluate untouched TD."""

import argparse
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_distribution_calibration import calibrate_distribution, evaluate_distribution
from terrain_pipeline.surface_rivers.metric_cohort_calibration import calibrate_cohorts, evaluate_cohort
from terrain_pipeline.climate_forcing import audit_noise_climate, physical_bio_context
from terrain_pipeline.climate_forcing import NoiseClimateParameters, sample_climate
from tools.verify_td_natural_river_baseline import boundary_for, diagnose


ROOT = Path(__file__).resolve().parents[1]
DEM = ROOT / "verification/dem-domain/run-20261001T135530750135Z/dem-candidate.npz"
SIDE = 48
ALPHA = .2
METRICS = ("longitudinal_slope", "curvature_rad_per_m", "signed_slope_jump_knickpoint_candidate")


def implementation_pins():
    paths = [Path(__file__), ROOT / "tools/verify_td_natural_river_baseline.py"]
    paths.extend(ROOT / relative for relative in (
        "terrain_pipeline/common_infra.py",
        'terrain_pipeline/drainage.py',
        "terrain_pipeline/surface_rivers/metric_naturalness_audit.py",
        "terrain_pipeline/surface_rivers/metric_distribution_calibration.py",
        "terrain_pipeline/surface_rivers/metric_cohort_calibration.py",
        "terrain_pipeline/climate_forcing.py",
        "terrain_pipeline/climate_forcing.py",
        "diffusion/geographic_noise.py",
        'terrain_pipeline/drainage.py'))
    return {str(path.relative_to(ROOT)): file_sha256(path) for path in paths}


def validate_reference(reference_path):
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    payload = {key: value for key, value in reference.items() if key != "identity_sha256"}
    if reference.get("identity_sha256") != identity({}, payload):
        raise ValueError("reference identity mismatch")
    plan_path = reference_path.parent / "plan.json"
    if file_sha256(plan_path) != reference["plan_sha256"]:
        raise ValueError("reference plan pin mismatch")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan["implementation_pins"] != implementation_pins():
        raise ValueError("frozen implementation pins mismatch")
    if "inventory_path" in plan and file_sha256(Path(plan["inventory_path"])) != plan["inventory_sha256"]:
        raise ValueError("real source inventory pin mismatch")
    return reference, plan


def relief_condition(height, valid):
    relief = float(np.ptp(height[valid]))
    return ("low_relief" if relief < 50. else "moderate_relief" if relief < 250. else "high_relief"), relief


def climate_bin(values, design):
    values = np.asarray(values, np.float64)
    if values.shape != (4,) or not np.isfinite(values).all():
        raise ValueError("four finite BIO conditions required")
    edges = design["bin_edges"]
    if isinstance(edges, dict):
        edges = [edges[name] for name in design["channel_order"]]
    if len(edges) != 4 or any(np.asarray(edge).ndim != 1 or not np.all(np.diff(edge) > 0.) for edge in edges):
        raise ValueError("four increasing climate bin edge arrays required")
    return [int(np.searchsorted(edge, value, side="right")) for edge, value in zip(edges, values)]


def condition_key(relief, bins):
    return relief + ":" + ":".join(str(value) for value in bins)


def holdout_summary(records):
    counts = {status: sum(record["evaluation"]["status"] == status for record in records)
              for status in ("pass", "fail", "not_assessed")}
    assessed = counts["pass"] + counts["fail"]
    return {"counts": counts, "assessed_count": assessed,
            "empirical_acceptance_fraction": counts["pass"] / assessed if assessed else None,
            "interpretation": "nonoverlapping_same_tile_holdout_not_independent_basin_or_universal_coverage"}


def measure(height, valid, *, spacing, source_kind, source_sha, source_id, origin=(0., 0.),
            flat_distance_strategy="hop_count", curvature_method="legacy_acos"):
    height = np.rint(np.asarray(height, dtype=np.float64))
    terrain = TerrainGrid(height.astype(np.float64), valid.astype(bool), *origin, spacing, spacing,
                          source_kind, source_id, source_sha)
    _, statistics = diagnose(terrain, boundary_for(terrain, "unknown_boundary"),
                             flat_distance_strategy=flat_distance_strategy, curvature_method=curvature_method)
    channels = statistics["channel_geometry_observations"]
    if channels.get("status") == "insufficient_channel_support":
        return None, channels
    samples = {name: channels[name]["samples"] for name in METRICS}
    if any(len(values) < 2 for values in samples.values()):
        return None, channels
    return samples, channels


def freeze(output, inventory_path=None, generation_plan_path=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    primary_path = ROOT / "verification/td-natural-river-stages/reference-baseline-02/reference.json"
    primary = json.loads(primary_path.read_text(encoding="utf-8"))
    if file_sha256(DEM) != primary["dem"]["source"]["sha256"]:
        raise ValueError("real DEM differs from source-replayed pin")
    inventory_path = Path(inventory_path) if inventory_path else ROOT / "verification/td-natural-river-stages/reference-conditions-20261011-01/report.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    generation_plan_path = Path(generation_plan_path) if generation_plan_path else None
    plan = {"schema": "channel-distribution-spatial-plan-v2", "source_sha256": file_sha256(DEM),
            "source_replay_reference_sha256": file_sha256(primary_path), "block_side": SIDE,
            "block_spacing_m": 90., "physical_extent_m": 4320., "alpha": ALPHA,
            "roles": "(block_row+block_col)%3:0 train,1 calibration,2 real_holdout",
            "condition_relief_m_boundaries": [50., 250.], "maximum_unknown_fraction": 0.,
            "channel_upstream_area_threshold_m2": 100000., "metric_names": list(METRICS),
            "flat_distance_strategy": "metric_distance", "curvature_method": "atan2",
            "cohort_policy": "real_calibration_spatial_two_window_pairs_mean_jointCDF_minimum4_pairs_independent_real_validation_not_all_blocks_pass",
            "condition_policy": "relief_grid_geometry_separate_from_noise_climate_physical_evaluation" if generation_plan_path else "legacy_BIO_bin_context",
            "generation_plan_path": str(generation_plan_path.resolve()) if generation_plan_path else None,
            "generation_plan_sha256": file_sha256(generation_plan_path) if generation_plan_path else None,
            "condition_limit": "relief/grid and BIO conditioning bins assessed separately; model BIO is not measured physical forcing",
            "inventory_path": str(inventory_path.resolve()), "inventory_sha256": file_sha256(inventory_path),
            "climate_design": inventory.get("climate_design"),
            "implementation_pins": implementation_pins(),
            "negative_control": "each pooled real metric shifted above its maximum by at least one unit",
            "vertical_observation_projection": {"spacing_m": 1., "rounding": "numpy_rint_ties_to_even",
                "applies_to": "both_real_and_TD_before_channel_graph_and_relief_classification",
                "reason": "SRTM_int16_meter_samples_vs_continuous_TD_not_equal_observation_precision",
                "does_not_modify_source": True},
            "td_windows_native_zx": [[0, 0], [192, 192]],
            "td_generation_report": str(ROOT / "verification/height-budget-v5/run-20260929T103819083596Z/holdout/report.json"),
            "td_generation_report_sha256": file_sha256(ROOT / "verification/height-budget-v5/run-20260929T103819083596Z/holdout/report.json")}
    (output / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    blocks = []
    world_extents = []
    datasets = inventory["datasets"] if "datasets" in inventory else [{"id": "original", "dem": inventory["dem"], "blocks": inventory["blocks"]}]
    for index, dataset in enumerate(datasets):
        if "dem" not in dataset:
            continue
        dem = dataset["dem"]
        dem_path = Path(dem.get("path", str(DEM)))
        expected = dem.get("sha256", plan["source_sha256"])
        if file_sha256(dem_path) != expected:
            raise ValueError("inventory DEM pin mismatch")
        with np.load(dem_path, allow_pickle=False) as archive:
            height, valid = archive["height_m"], archive["valid_mask"]
            manifest = json.loads(str(archive["manifest"].item()))
        grid = manifest["identity"]["grid"]
        crs = manifest["identity"]["recipe"]["target_crs"]
        if grid["spacing_x_m"] != 90. or grid["spacing_z_m"] != 90.:
            raise ValueError("real inventory grid spacing mismatch")
        for declared in dataset["blocks"]:
            r0, r1, c0, c1 = declared["window_zx"]
            window = np.s_[r0:r1, c0:c1]
            h, v = height[window], valid[window]
            role = {"fit": "train", "holdout": "real_holdout"}.get(declared["role"], declared["role"])
            record = {"id": str(dataset.get("id", index)) + ":" + declared["id"], "window_zx": declared["window_zx"], "role": role,
                      "dataset_id": str(dataset.get("id", index)), "crs": crs,
                      "valid_fraction": float(v.mean())}
            if not declared.get("eligible_for_evaluation", True):
                record["status"] = "excluded_inventory_spatial_overlap_or_halo"
            elif h.shape != (SIDE, SIDE) or not v.all():
                record["status"] = "excluded_unknown_support"
            else:
                x0 = grid["origin_x_m"] + (c0 - .5) * 90.
                z0 = grid["origin_z_m"] + (r0 - .5) * 90.
                extent = (x0, z0, x0 + SIDE * 90., z0 + SIDE * 90.)
                if any(crs == old_crs and extent[0] < old[2] and old[0] < extent[2]
                       and extent[1] < old[3] and old[1] < extent[3] for old_crs, old in world_extents):
                    raise ValueError("real training/calibration/holdout blocks share world cells")
                world_extents.append((crs, extent))
                record["world_extent_xz_m"] = list(extent)
                condition, relief = relief_condition(np.rint(h), v)
                samples, channels = measure(h, v, spacing=90., source_kind="observed_dem",
                    source_sha=expected, source_id="real-" + record["id"],
                    origin=(grid["origin_x_m"] + c0 * 90., grid["origin_z_m"] + r0 * 90.),
                    flat_distance_strategy=plan["flat_distance_strategy"], curvature_method=plan["curvature_method"])
                record.update(condition=condition, relief_m=relief,
                              raw_relief_m=float(np.ptp(h[v])),
                              status="measured" if samples is not None else "insufficient_channel_support",
                              metrics=samples, channel_support=channels.get("channel_support"))
                if plan["climate_design"] and declared.get("climate_BIO1_4_12_15") is not None:
                    values = declared["climate_BIO1_4_12_15"]
                    bins = climate_bin(values, plan["climate_design"])
                    record.update(climate_BIO1_4_12_15=values, climate_bin=bins,
                                  full_condition=condition_key(condition, bins))
            blocks.append(record)
    frozen = {}
    holdout = []
    for condition in ("low_relief", "moderate_relief", "high_relief"):
        selected = [block for block in blocks if block["status"] == "measured" and block["condition"] == condition]
        train = [block for block in selected if block["role"] == "train"]
        calibration = [block for block in selected if block["role"] == "calibration"]
        if not train or not calibration:
            continue
        frozen[condition] = calibrate_distribution(train, calibration, alpha=ALPHA,
                                                  conditions={"relief_class": condition, "spacing_m": 90., "extent_m": 4320.})
        for block in selected:
            if block["role"] == "real_holdout":
                holdout.append({"id": block["id"], "condition": condition,
                                "evaluation": evaluate_distribution(block["metrics"], frozen[condition], conditions_match=True)})
    result = {"schema": "real-channel-distribution-reference-v1", "plan_sha256": file_sha256(output / "plan.json"),
              "blocks": blocks, "calibrations": frozen, "nonoverlapping_real_holdout": holdout,
              "negative_controls": {condition: evaluate_distribution({name: (np.asarray(values) + max(1., float(np.ptp(values))) + float(np.max(values)) - float(np.min(values))).tolist() for name, values in calibration["reference_samples"].items()}, calibration, conditions_match=True) for condition, calibration in frozen.items()},
              "spatial_dependence": "same real product geographic blocks; no independent-basin or exchangeability guarantee",
              "condition_coverage": {condition: sum(block.get("condition") == condition and block["status"] == "measured"
                                                     for block in blocks) for condition in frozen},
              "natural_certification": False}
    conditional = {}
    conditional_holdout = []
    for key in sorted({block["full_condition"] for block in blocks if block.get("full_condition") and block["status"] == "measured"}):
        selected = [block for block in blocks if block.get("full_condition") == key and block["status"] == "measured"]
        train = [block for block in selected if block["role"] == "train"]
        calibration = [block for block in selected if block["role"] == "calibration"]
        if not train or not calibration:
            continue
        conditional[key] = calibrate_distribution(train, calibration, alpha=ALPHA,
            conditions={"full_condition": key, "spacing_m": 90., "extent_m": 4320., "climate_semantics": "BIO_condition_values_not_measured_forcing"})
        for block in selected:
            if block["role"] == "real_holdout":
                conditional_holdout.append({"id": block["id"], "condition": key,
                    "evaluation": evaluate_distribution(block["metrics"], conditional[key], conditions_match=True)})
    result.update(conditional_calibrations=conditional, conditional_real_holdout=conditional_holdout,
                  cohort_calibration=calibrate_cohorts(blocks, frozen),
                  real_holdout_by_CRS={crs: holdout_summary([record for record in holdout if next(block for block in blocks if block["id"] == record["id"])["crs"] == crs]) for crs in sorted({block.get("crs") for block in blocks if block.get("crs")})},
                  relief_grid_real_holdout_summary=holdout_summary(holdout),
                  conditional_real_holdout_summary=holdout_summary(conditional_holdout),
                  unsupported_datasets=[{key: dataset.get(key) for key in ("id", "status", "reason")} for dataset in datasets if "dem" not in dataset])
    result["identity_sha256"] = identity({}, result)
    (output / "reference.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result


def evaluate(reference_path, source_path, expected_sha256, output, development_report=None):
    reference_path, source_path, output = Path(reference_path), Path(source_path), Path(output)
    if output.exists():
        raise FileExistsError(output)
    if file_sha256(source_path) != expected_sha256:
        raise ValueError("untouched TD archive differs from frozen generation pin")
    reference, plan = validate_reference(reference_path)
    new_plan_path = Path(plan["generation_plan_path"]) if plan.get("generation_plan_path") else None
    if new_plan_path:
        if file_sha256(new_plan_path) != plan["generation_plan_sha256"]:
            raise ValueError("new noise generation plan pin mismatch")
        source_plan = json.loads(new_plan_path.read_text(encoding="utf-8"))
        report_path = new_plan_path.parent / "report.json"
        if development_report:
            report_path = Path(development_report)
            source_plan = json.loads((report_path.parent / "plan.json").read_text(encoding="utf-8"))
            if source_plan["phase"] != "development":
                raise ValueError("development override cannot consume formal holdout")
    else:
        report_path = Path(plan["td_generation_report"])
        if file_sha256(report_path) != plan["td_generation_report_sha256"]:
            raise ValueError("TD generation report pin mismatch")
    generation = json.loads(report_path.read_text(encoding="utf-8"))
    if new_plan_path and not development_report and (generation["plan_sha256"] != plan["generation_plan_sha256"] or generation["evaluation_plan_sha256"] != file_sha256(reference_path.parent / "plan.json")):
        raise ValueError("noise generation did not bind this frozen evaluation plan")
    if development_report and generation["plan_sha256"] != file_sha256(report_path.parent / "plan.json"):
        raise ValueError("development generation plan differs")
    matching = [entry for entry in generation["samples"] if entry["raw_npz"] == source_path.name and entry["raw_sha256"] == expected_sha256]
    if len(matching) != 1:
        raise ValueError("TD source not bound to frozen report")
    with np.load(source_path, allow_pickle=False) as archive:
        height = archive["elevation"].astype(np.float64)
        metadata = json.loads(str(archive["metadata"].item()))
        config = json.loads(str(archive["generation_config"].item()))
        climate = archive["climate"].astype(np.float64)
    if new_plan_path:
        job = next(job for job in source_plan["jobs"] if job["seed"] == int(metadata["seed"]))
        expected_config, expected_identity = job["generation_config"], job["generation_identity"]
        physical_path = Path(source_plan["physical_reference_path"])
        if file_sha256(physical_path) != source_plan["physical_reference_sha256"]:
            raise ValueError("noise physical real-reference pin differs")
        physical_reference = json.loads(physical_path.read_text(encoding="utf-8"))
        noise_parameters = NoiseClimateParameters(**source_plan["parameters"])
    else:
        expected_config, expected_identity = generation["generation_config"], generation["generation_identity"]
    if (metadata["native_resolution_m"] != 30 or height.shape != (513, 513)
            or metadata["identity"] != expected_identity
            or config != expected_config
            or metadata["native_origin"] != matching[0]["native_origin"]
            or int(metadata["seed"]) != matching[0]["seed"]):
        raise ValueError("TD generation metadata/grid mismatch")
    if climate.ndim != 3 or climate.shape[0] < 4 or climate.shape[1:] != height.shape:
        raise ValueError("TD climate channel grid mismatch")
    cases = []
    for row, column in plan["td_windows_native_zx"]:
        h = height[row:row + SIDE * 3:3, column:column + SIDE * 3:3]
        v = np.isfinite(h)
        condition, relief = relief_condition(np.rint(h), v)
        samples, channels = measure(h, v, spacing=90., source_kind="generated_terrain", source_sha=expected_sha256,
                                   source_id="unseen-TD-" + str(metadata["seed"]),
                                   origin=((metadata["native_origin"][0] + column) * 30., (metadata["native_origin"][1] + row) * 30.),
                                   flat_distance_strategy=plan.get("flat_distance_strategy", "hop_count"),
                                   curvature_method=plan.get("curvature_method", "legacy_acos"))
        frozen = reference["calibrations"].get(condition)
        measured = evaluate_distribution(samples, frozen, conditions_match=True) if samples is not None and frozen else {
            "status": "not_assessed", "reason": "no_real_calibration_for_condition_or_insufficient_channels"}
        climate_values = np.median(climate[:4, row:row + SIDE * 3:3, column:column + SIDE * 3:3], axis=(1, 2)).tolist()
        bins = climate_bin(climate_values, plan["climate_design"]) if plan["climate_design"] else None
        key = condition_key(condition, bins) if bins is not None else None
        conditional = reference["conditional_calibrations"].get(key)
        full = evaluate_distribution(samples, conditional, conditions_match=True) if samples is not None and conditional else {
            "status": "not_assessed", "reason": "no_real_calibration_for_full_relief_climate_condition_or_insufficient_channels"}
        if new_plan_path:
            gx, gz = np.meshgrid((metadata["native_origin"][0] + column + np.arange(SIDE) * 3) * 30.,
                                 (metadata["native_origin"][1] + row + np.arange(SIDE) * 3) * 30.)
            noise_audit = audit_noise_climate(int(metadata["seed"]), gx, gz, h, physical_reference, parameters=noise_parameters)
            noise_climate = sample_climate(int(metadata["seed"]), gx, gz, h, parameters=noise_parameters)
            derived_path = output.parent / (source_path.stem + "-noise-climate-window" + str(row) + "-" + str(column) + ".npz")
            derived_path.parent.mkdir(parents=True, exist_ok=True)
            if derived_path.exists():
                raise FileExistsError(derived_path)
            np.savez_compressed(derived_path, monthly_temperature_c=noise_climate["monthly_temperature_c"],
                monthly_precipitation_mm=noise_climate["monthly_precipitation_mm"], BIO1_4_12_15=noise_climate["BIO1_4_12_15"],
                metadata=np.array(json.dumps({"source_sha256": expected_sha256, "seed": int(metadata["seed"]),
                    "origin_xz_m": [float(gx[0, 0]), float(gz[0, 0])], "spacing_m": 90.,
                    "parameter_identity_sha256": noise_parameters.identity_sha256, "source_model": "metric_noise_climate_v1",
                    "generation_plan_sha256": generation["plan_sha256"], "canonical_derived_climate_not_upstream_auxiliary_BIO": True})))
            noise_audit["derived_product"] = {"path": str(derived_path.resolve()), "sha256": file_sha256(derived_path)}
            upstream_context = physical_bio_context(climate[:4, row:row + SIDE * 3:3, column:column + SIDE * 3:3], physical_reference)
        else:
            noise_audit, upstream_context = None, None
        cases.append({"window_origin_zx": [row, column], "relief_class": condition, "relief_m": relief,
                      "raw_relief_m": float(np.ptp(h[v])), "vertical_observation_projection": plan["vertical_observation_projection"],
                      "distribution_evaluation_relief_grid_only": measured,
                      "climate_condition_values_BIO1_4_12_15": climate_values, "climate_bin": bins,
                      "conditional_geometry_evaluation": full,
                      "noise_climate_physical_evaluation": noise_audit, "upstream_auxiliary_BIO_real_context": upstream_context,
                      "climate_semantics": "model_BIO_conditioning_not_observed_physical_forcing",
                      "naturalness_status": "conditional_BIO_context_only" if new_plan_path else full["status"],
                      "channel_observations": channels})
    result = {"schema": "td-real-calibrated-channel-distribution-evaluation-v1", "source_sha256": expected_sha256,
              "source_metadata": metadata, "generation_config": config, "reference_sha256": file_sha256(reference_path), "cases": cases,
              "real_holdout": reference["nonoverlapping_real_holdout"], "negative_controls": reference["negative_controls"],
              "real_holdout_summary": reference["relief_grid_real_holdout_summary"],
              "conditional_real_holdout_summary": reference["conditional_real_holdout_summary"],
              "cohort_evaluation": evaluate_cohort(cases, reference["cohort_calibration"]),
              "generation_report_sha256": file_sha256(report_path),
              "evaluation_role": "development_only_not_independent_holdout" if development_report else "independent_holdout",
              "natural_certification": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--source-sha256")
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--generation-plan", type=Path)
    parser.add_argument("--development-report", type=Path)
    args = parser.parse_args()
    result = evaluate(args.reference, args.source, args.source_sha256, args.output, args.development_report) if args.reference else freeze(args.output, args.inventory, args.generation_plan)
    print(json.dumps({"schema": result["schema"], "natural_certification": False}))
