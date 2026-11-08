"""Explicit frozen-plan, seasonal and genuine TD detail preparation entry point."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from diffusion.physical_config import PhysicalGenerationConfig
from terrain_pipeline.hydrology_detail import (
    DetailBudget, derive_detail, file_sha256, load_raw_td, save_detail, select_key_windows, required_td_nodes,
)
from terrain_pipeline.hydrology_detail_conditioning import (
    ResourcePhysicalTerrainDiffusionBackend, PlannedTerrainDiffusionBackend, RESOURCE_SETTINGS, candidate_change,
)
from terrain_pipeline.td_source import CanonicalTDSource, source_contract, _hydrology_td_digest as source_digest

CANONICAL_CACHE = ROOT / "verification/hydrological-planning-domain/td-canonical-cache"


def _json_new(path, record):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, ensure_ascii=False, allow_nan=False)


def prepare_windows(plan, output, *, generate=False, resource_tier="balanced", budget=None, size=97,
                    window_kind=None, lake_level_m=None, lake_mask=None, divide_taper_width_m=0.0,
                    ridge_index=0, budget_is_frozen=False):
    """Resource tier changes scheduling only; raw/derived identities exclude it.

    The caller owns serialization with other GPU work. Raw caches have pinned
    provenance and survive a refused derivation. No fallback terrain exists.
    """
    budget = DetailBudget() if budget is None else budget
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    windows = select_key_windows(plan, size=size, lake_level_m=lake_level_m, lake_mask=lake_mask, ridge_index=ridge_index)
    if window_kind:
        windows = [window for window in windows if window["kind"] == window_kind]
    if generate and "frozen_td_lowpass_m" not in plan and not plan.get("frozen_td_baseline_nodes") and not window_kind:
        raise ValueError("unmatched low-frequency backbone: generate one explicit calibration window first")
    config = PhysicalGenerationConfig()
    generation_identity, _ = config.generation_identity()
    canonical_identity = source_digest(source_contract(generation_identity))
    declaration = {"schema": "hydrology-detail-execution-v1", "seed": int(plan["seed"]),
                   "plan_identity": plan.get("identity", plan.get("identity_sha256")),
                   "generation_identity": generation_identity, "windows": windows,
                   "budget": asdict(budget), "budget_status": "frozen_after_calibration" if budget_is_frozen else "calibration_candidate_requires_freeze",
                   "physical_config": json.loads(json.dumps(config.record(), allow_nan=False))}
    declaration["raw_source_schema"] = "hydrology-canonical-td-window-v1"
    declaration["canonical_source_identity"] = canonical_identity
    declaration["divide_taper_width_m"] = divide_taper_width_m
    plan_path = output / "detail-plan.json"
    if plan_path.exists():
        if json.loads(plan_path.read_text(encoding="utf-8")) != declaration:
            raise ValueError("immutable detail plan or frozen budgets differ")
    else:
        _json_new(plan_path, declaration)
    if not generate:
        return {"status": "planned_no_inference", "plan": str(plan_path)}
    from diffusion.paths import configure

    configure()
    backend = CanonicalTDSource(ResourcePhysicalTerrainDiffusionBackend(config, resource_tier), CANONICAL_CACHE)
    records = []
    try:
        nodes = dict(plan.get("frozen_td_baseline_nodes", {}))
        node_folder = output / "td-coarse-node-cache"
        node_folder.mkdir(exist_ok=True)
        for window in windows:
            if window["status"] != "planned":
                continue
            for cz, cx in required_td_nodes(plan, window):
                key = str(cz) + ":" + str(cx)
                cache = node_folder / (str(cz) + "-" + str(cx) + ".json")
                world = np.array(plan["origin_xz_m"]) + np.array([cx, cz]) * plan["spacing_m"]
                native = world / config.native_resolution_m
                if cache.exists():
                    record = json.loads(cache.read_text(encoding="utf-8"))
                    if record["generation_identity"] != canonical_identity or record["seed"] != plan["seed"] or record["world_xz_m"] != world.tolist():
                        raise ValueError("coarse TD node cache identity mismatch")
                else:
                    native_floor = np.floor(native).astype(int)
                    elevation, _, metadata = backend.generate(plan["seed"], int(native_floor[0]), int(native_floor[1]), 2)
                    wx, wz = native - native_floor
                    sampled = ((1 - wz) * ((1 - wx) * elevation[0, 0] + wx * elevation[0, 1])
                               + wz * ((1 - wx) * elevation[1, 0] + wx * elevation[1, 1]))
                    record = {"elevation_m": float(sampled), "world_xz_m": world.tolist(),
                              "generation_identity": canonical_identity, "seed": plan["seed"],
                              "generation_metadata": metadata, "native_elevation_m": elevation.tolist(),
                              "sampling": "bilinear fixed globally aligned native 2x2 TD nodes"}
                    _json_new(cache, record)
                nodes[key] = record
        plan = dict(plan, frozen_td_baseline_nodes=nodes)
        for window in windows:
            if window["status"] != "planned":
                records.append(window)
                continue
            raw_path = output / (window["kind"] + "-original-td.npz")
            digest_path = raw_path.with_suffix(".sha256")
            if not raw_path.exists():
                x, z = window["native_origin_xz"]
                elevation, climate, metadata = backend.generate(plan["seed"], x, z, size)
                with raw_path.open("xb") as stream:
                    np.savez_compressed(stream, elevation_m=elevation, climate=climate,
                                        metadata_json=np.array(json.dumps(metadata, allow_nan=False)))
                digest_path.write_text(file_sha256(raw_path), encoding="ascii")
            if not digest_path.exists():
                raise ValueError("unversioned raw TD cache; explicit pin required")
            raw, metadata = load_raw_td(raw_path, digest_path.read_text(encoding="ascii").strip())
            provenance = metadata["provenance"]
            generated = provenance["generation_metadata"]
            if (generated["identity"] != canonical_identity or int(generated["seed"]) != plan["seed"]
                    or generated["native_origin"] != window["native_origin_xz"]
                    or generated["shape"] != window["shape"]):
                raise ValueError("cached original TD coordinates/seed/model identity mismatch")
            result = derive_detail(plan, raw["arrays"]["height_m"], origin_xz_m=window["origin_xz_m"],
                spacing_m=window["spacing_m"], raw_provenance=provenance, budget=budget, window_kind=window["kind"],
                divide_taper_width_m=divide_taper_width_m)
            detail_path = output / (window["kind"] + "-detail.npz")
            if not detail_path.exists():
                save_detail(detail_path, result)
            else:
                with np.load(detail_path, allow_pickle=False) as archive:
                    existing = json.loads(str(archive["metadata_json"].item()))
                if existing["identity"] != result["metadata"]["identity"]:
                    raise ValueError("existing derived detail identity mismatch")
            records.append({**window, "raw_path": raw_path.name, "detail_path": detail_path.name,
                            "status": result["metadata"]["status"], "metadata": result["metadata"]})
    finally:
        backend.close()
    report = {"schema": "hydrology-detail-review-v1", "windows": records,
              "global_hydrology_certified": False, "publishable": False,
              "resource_tier": resource_tier, "scheduling": "serial identical native windows",
              "resource_settings": RESOURCE_SETTINGS[resource_tier]}
    report_path = output / "detail-review.json"
    if not report_path.exists():
        _json_new(report_path, report)
    return report


def prepare_planned_candidate(plan, output, *, window_kind, size, resource_tier, budget,
                              lake_level_m=None, lake_mask=None, ridge_index=0):
    """Explicit second inference, beside the immutable original physical TD."""
    from diffusion.paths import configure

    output = Path(output)
    raw_path = output / (window_kind + "-original-td.npz")
    digest_path = raw_path.with_suffix(".sha256")
    if not raw_path.exists() or not digest_path.exists():
        raise ValueError("planned condition candidate requires a pinned original TD calibration first")
    raw, original_metadata = load_raw_td(raw_path, digest_path.read_text(encoding="ascii").strip())
    windows = select_key_windows(plan, size=size, lake_level_m=lake_level_m, lake_mask=lake_mask, ridge_index=ridge_index)
    window = next(window for window in windows if window["kind"] == window_kind)
    if window["status"] != "planned":
        raise ValueError("no genuine planned location for condition candidate")
    config = PhysicalGenerationConfig()
    planned_backend = PlannedTerrainDiffusionBackend(config, plan, resource_tier)
    backend = CanonicalTDSource(planned_backend, CANONICAL_CACHE)
    path = output / (window_kind + "-planned-conditioned-td.npz")
    pin_path = path.with_suffix(".sha256")
    configure()
    if path.exists():
        if not pin_path.exists() or file_sha256(path) != pin_path.read_text(encoding="ascii").strip():
            raise ValueError("unverified planned TD cache")
        with np.load(path, allow_pickle=False) as archive:
            elevation = archive["elevation_m"].copy()
            metadata = json.loads(str(archive["metadata_json"].item()))
        if metadata["identity"] != backend.identity or metadata["native_origin"] != window["native_origin_xz"] or metadata["shape"] != window["shape"]:
            raise ValueError("planned TD candidate identity/coordinates mismatch")
    else:
        try:
            x, z = window["native_origin_xz"]
            elevation, climate, metadata = backend.generate(plan["seed"], x, z, size)
            with path.open("xb") as stream:
                np.savez_compressed(stream, elevation_m=elevation, climate=climate,
                                    metadata_json=np.array(json.dumps(metadata, allow_nan=False)))
            pin_path.write_text(file_sha256(path), encoding="ascii")
        finally:
            backend.close()
    original = raw["arrays"]["height_m"]
    if (original_metadata["origin_m_xz"] != window["origin_xz_m"]
            or original.shape != elevation.shape or int(metadata["seed"]) != plan["seed"]
            or int(original_metadata["provenance"]["generation_metadata"]["seed"]) != plan["seed"]
            or original_metadata["provenance"]["generation_metadata"].get("base_generation_identity") != planned_backend.metadata["parent_generation_identity"]):
        raise ValueError("original and conditioned candidate are not aligned")
    comparison = candidate_change(original, elevation, config.native_resolution_m)
    provenance = {"artifact_kind": "terrain_diffusion_output", "td_inference_run": True,
                  "archive_sha256": file_sha256(path), "generation_metadata": metadata}
    audit = derive_detail(plan, original, origin_xz_m=window["origin_xz_m"], spacing_m=config.native_resolution_m,
        raw_provenance=original_metadata["provenance"], budget=budget, window_kind=window_kind,
        candidate_height_m=elevation, candidate_provenance=provenance)
    result = {"status": audit["metadata"]["status"], "candidate_generation_identity": backend.identity,
              "original_td_sha256": original_metadata["provenance"]["archive_sha256"],
              "candidate_td_sha256": file_sha256(path), "plan_identity": plan["identity_sha256"],
              "audit": audit["metadata"], "comparison_ledger": comparison["ledger"],
              "semantics": comparison["semantics"], "budget": asdict(budget),
              "global_hydrology_certified": False, "publishable": False,
              "resource_settings": RESOURCE_SETTINGS[resource_tier]}
    report_path = output / (window_kind + "-planned-conditioned-review.json")
    if not report_path.exists():
        _json_new(report_path, result)
        with (output / (window_kind + "-planned-conditioned-comparison.npz")).open("xb") as stream:
            np.savez_compressed(stream, original_td_m=original, planned_conditioned_td_m=elevation,
                total_delta_m=comparison["delta_m"], actual_receiver=audit["arrays"]["actual_receiver"],
                cross_owner_d8_mask=audit["arrays"]["cross_owner_d8_mask"],
                unplanned_sink_mask=audit["arrays"]["unplanned_sink_mask"],
                metadata_json=np.array(json.dumps(result, allow_nan=False)))
    return result


def prepare_fine_components(plan, output, specifications):
    """CPU-only solve for explicitly clipped components of the frozen river graph."""
    from terrain_pipeline.channel_geometry import derive_continuous_bed

    output = Path(output)
    reports = []
    for kind, specification in specifications.items():
        detail_path = output / (kind + "-detail.npz")
        with np.load(detail_path, allow_pickle=False) as archive:
            detail = {"arrays": {key: archive[key].copy() for key in archive.files if key != "metadata_json"},
                      "metadata": json.loads(str(archive["metadata_json"].item()))}
        result = derive_continuous_bed(detail, specification["points_xz_m"], specification["receiver"],
            specification["width_m"], specification["bed_target_m"],
            fine_spacing_m=specification.get("fine_spacing_m", 1.0), frozen_plan=plan,
            node_source_edges=specification["node_source_edges"], node_edge_fractions=specification["node_edge_fractions"])
        report = {key: value for key, value in result.items() if key != "arrays"}
        report["window_kind"] = kind
        report_path = output / (kind + "-continuous-fine-bed-review.json")
        if not report_path.exists():
            _json_new(report_path, report)
            if result["arrays"]:
                with (output / (kind + "-continuous-fine-bed.npz")).open("xb") as stream:
                    np.savez_compressed(stream, **result["arrays"], metadata_json=np.array(json.dumps(report, allow_nan=False)))
        reports.append(report)
    return reports


def prepare_wide_ridge(plan, output, budget, width_m=None, margin_m=1.0):
    from terrain_pipeline.hydrology_detail_ridge import derive_wide_ridge

    output = Path(output)
    with np.load(output / "ridge-detail.npz", allow_pickle=False) as archive:
        detail = {"arrays": {key: archive[key].copy() for key in archive.files if key != "metadata_json"},
                  "metadata": json.loads(str(archive["metadata_json"].item()))}
    if detail["metadata"]["plan_identity"] != plan["identity_sha256"]:
        raise ValueError("wide ridge cannot migrate original detail between frozen plans")
    result = derive_wide_ridge(plan, detail, width_m=width_m, ridge_margin_m=margin_m, budget=budget)
    destination = output / "ridge-wide-proposal-detail.npz"
    if not destination.exists():
        save_detail(destination, result)
    else:
        with np.load(destination, allow_pickle=False) as archive:
            saved = json.loads(str(archive["metadata_json"].item()))
        if saved["identity"] != result["metadata"]["identity"]:
            raise ValueError("immutable wide ridge proposal differs")
    return {"path": str(destination), "status": result["metadata"]["status"],
            "rejection_reasons": result["metadata"]["rejection_reasons"], "ledger": result["metadata"]["ledger"],
            "cross_domain_d8_count": result["metadata"]["cross_domain_d8_count"],
            "unplanned_interior_sink_count": result["metadata"]["unplanned_interior_sink_count"]}


def prepare_global_macro(plan, output, budget, lake_level_m, residual_fraction=0.0):
    from terrain_pipeline.hydrology_detail_ridge import derive_global_macro

    if lake_level_m is None:
        raise ValueError("global macro proposal needs verified seasonal lake stage")
    reports = []
    output = Path(output)
    for kind in ("ridge", "river", "confluence", "mouth", "lake_shore"):
        directory = output / kind if (output / kind).is_dir() else output
        source = directory / (kind + "-detail.npz")
        if not source.exists():
            continue
        with np.load(source, allow_pickle=False) as archive:
            detail = {"arrays": {key: archive[key].copy() for key in archive.files if key != "metadata_json"},
                      "metadata": json.loads(str(archive["metadata_json"].item()))}
        if detail["metadata"]["plan_identity"] != plan["identity_sha256"]:
            raise ValueError("global proposal cannot migrate source between frozen plans")
        result = derive_global_macro(plan, detail, lake_level_m=lake_level_m, budget=budget, residual_fraction=residual_fraction)
        suffix = "global-residual-v4-proposal" if residual_fraction else "global-macro-v4-proposal"
        destination = directory / (kind + "-" + suffix + "-detail.npz")
        if not destination.exists():
            save_detail(destination, result)
        else:
            with np.load(destination, allow_pickle=False) as archive:
                if json.loads(str(archive["metadata_json"].item()))["identity"] != result["metadata"]["identity"]:
                    raise ValueError("immutable global macro proposal differs")
        reports.append({"kind": kind, "path": str(destination), **{key: result["metadata"][key] for key in
            ("status", "ledger", "rejection_reasons", "cross_domain_d8_count", "unplanned_interior_sink_count", "non_downhill_channel_steps")}})
    return reports


def prepare_global_fine_beds(plan, output, *, canonical_projection=False, window_kind=None, projection_version="v3"):
    from terrain_pipeline.channel_geometry import select_frozen_component, derive_continuous_bed

    output = Path(output)
    reports = []
    windows = select_key_windows(plan)
    prefix = "canonical-projection-" + projection_version + "-detail-v3-assessment-v2" if canonical_projection else "global-residual-v4"
    for kind in ("river", "confluence", "mouth"):
        if window_kind is not None and kind != window_kind:
            continue
        directory = output / kind
        source = directory / (kind + "-" + prefix + (".npz" if canonical_projection else "-proposal-detail.npz"))
        if canonical_projection and not source.exists():
            reports.append({"window_kind": kind, "status": "parent_projection_not_available"})
            continue
        with np.load(source, allow_pickle=False) as archive:
            detail = {"arrays": {key: archive[key].copy() for key in archive.files if key != "metadata_json"},
                      "metadata": json.loads(str(archive["metadata_json"].item()))}
        declaration_path = directory / "detail-plan.json"
        if declaration_path.exists():
            declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
            window = next(window for window in declaration["windows"] if window["kind"] == kind)
        else:
            window = next(window for window in windows if window["kind"] == kind)
        specification = select_frozen_component(plan, detail, window)
        request_path = directory / (kind + "-" + prefix + "-fine-component-request.json")
        if not request_path.exists():
            _json_new(request_path, {kind: specification})
        result = derive_continuous_bed(detail, specification["points_xz_m"], specification["receiver"],
            specification["width_m"], specification["bed_target_m"], fine_spacing_m=1.0, frozen_plan=plan,
            node_source_edges=specification["node_source_edges"], node_edge_fractions=specification["node_edge_fractions"])
        report = {key: value for key, value in result.items() if key != "arrays"}
        report["window_kind"] = kind
        if canonical_projection:
            report["parent_detail_identity"] = detail["metadata"]["identity"]
            native_reasons = [reason for reason in detail["metadata"]["rejection_reasons"] if reason != "continuous_fine_bed_not_certified"]
            report["parent_native_rejection_reasons"] = native_reasons
            if result.get("arrays"):
                total_volume = detail["metadata"]["ledger"]["total_absolute_volume_m3"] + report["ledger"]["local_cut_volume_m3"]
                report["combined97_window_total_absolute_volume_upper_bound_m3"] = total_volume
                report["combined97_window_total_volume_budget_m3"] = detail["metadata"]["budget"]["total_absolute_volume_m3"]
                if total_volume > report["combined97_window_total_volume_budget_m3"]:
                    report["status"] = "rejected"
                    report["reason"] = "combined97_window_total_change_volume_budget_exceeded"
                report["local_example_compatible"] = not native_reasons and report["status"] != "rejected"
        report_path = directory / (kind + "-" + prefix + "-continuous-fine-bed-review.json")
        if not report_path.exists():
            _json_new(report_path, report)
            if result.get("arrays"):
                with (directory / (kind + "-" + prefix + "-continuous-fine-bed.npz")).open("xb") as stream:
                    np.savez_compressed(stream, **result["arrays"], metadata_json=np.array(json.dumps(report, allow_nan=False)))
        reports.append(report)
    return reports


def _artifact_identity(metadata, arrays):
    return source_digest({"metadata": {key: value for key, value in metadata.items() if key != "identity"},
                          "arrays": {key: hashlib.sha256(value.tobytes()).hexdigest() for key, value in sorted(arrays.items())}})


def _read_bed_piece(path):
    with np.load(path, allow_pickle=False) as archive:
        record = json.loads(str(archive["metadata_json"].item()))
        arrays = {key: archive[key].copy() for key in archive.files if key != "metadata_json"}
    if record["identity"] != _artifact_identity(record, arrays):
        raise ValueError("immutable full-window bed piece identity mismatch")
    return {**record, "arrays": arrays}


def _projection_algorithm(version, tributary_declaration=None):
    algorithms = {"v2": "canonical-td-full-residual-constrained-projection-v2",
                  "v3": "canonical-td-full-residual-constrained-projection-v3-frozen-river-valleys",
                  "finite-local-v1": "finite99-local-tributary-constrained-projection-v1",
                  "finite-network-v1": "finite99-frozen-network-constrained-projection-v1",
                  "finite-network-v2-target-witness": "finite99-frozen-network-target-macro-rank-projection-v2",
                  "finite-network-v3-channel-feasibility": "finite99-frozen-network-channel-feasibility-projection-v3",
                  "finite-network-v4-harmonic-channel": "finite99-frozen-network-harmonic-channel-projection-v4",
                  "finite-network-v5-harmonic-channel-target-witness": "finite99-frozen-network-harmonic-channel-target-witness-projection-v5",
                  "finite-network-v6-target-gradient": "finite99-frozen-network-harmonic-channel-target-gradient-projection-v6"}
    if version not in algorithms:
        raise ValueError("explicit v2 or v3 projection version required")
    if version == "finite-local-v1" and tributary_declaration is None:
        raise ValueError("finite local projection requires explicit frozen tributary sidecar")
    if tributary_declaration is not None:
        if version == "finite-local-v1":
            return algorithms[version]
        if version != "v3":
            raise ValueError("local tributary geometry requires explicit projection v3")
        return algorithms[version] + "-local-tributary-v1"
    return algorithms[version]


def _projection_tag(version, tributary_declaration=None):
    _projection_algorithm(version, tributary_declaration)
    if tributary_declaration is None:
        return version
    return version + "-local-tributary-" + tributary_declaration["identity_sha256"][:12]


def _owned_full_window_source(plan, output, kind, budget, lake_level_m, projection_version="v3", *, tributary_declaration=None):
    """Assemble only accepted owning pixels, and prove raw99 against pinned TD."""
    if projection_version == "finite-local-v1":
        from terrain_pipeline.hydrology_detail_tributary_finite import prepare_finite_tributary_source
        return prepare_finite_tributary_source(plan, output, budget, lake_level_m, tributary_declaration)
    if projection_version in ("finite-network-v1", "finite-network-v2-target-witness", "finite-network-v3-channel-feasibility", "finite-network-v4-harmonic-channel", "finite-network-v5-harmonic-channel-target-witness", "finite-network-v6-target-gradient"):
        from terrain_pipeline.hydrology_detail_tributary_finite import prepare_finite_tributary_source
        from terrain_pipeline.hydrology_detail_projection import MACRO_WITNESS_POLICY, TARGET_WITNESS_POLICY
        return prepare_finite_tributary_source(plan, output, budget, lake_level_m, None,
            window_kind=kind, frozen_network=True,
            witness_policy=TARGET_WITNESS_POLICY if projection_version in ("finite-network-v2-target-witness", "finite-network-v5-harmonic-channel-target-witness", "finite-network-v6-target-gradient") else MACRO_WITNESS_POLICY,
            channel_feasibility_policy="frozen-channel-feasibility-v1" if projection_version in ("finite-network-v3-channel-feasibility", "finite-network-v4-harmonic-channel", "finite-network-v5-harmonic-channel-target-witness", "finite-network-v6-target-gradient") else None,
            target_policy="harmonic-boundary-residual-v1" if projection_version in ("finite-network-v4-harmonic-channel", "finite-network-v5-harmonic-channel-target-witness", "finite-network-v6-target-gradient") else None,
            gradient_policy="target-neighbor-gradient-l1-v1" if projection_version == "finite-network-v6-target-gradient" else None)
    from terrain_pipeline.hydrology_detail_projection import load_projection, crop_projection, load_cached_support
    from terrain_pipeline.common_infra import checked_archive

    output = Path(output)
    expected_algorithm = _projection_algorithm(projection_version, tributary_declaration)
    projection_tag = _projection_tag(projection_version, tributary_declaration)
    window = projection_source_declaration(plan, output, kind)["windows"][0]
    if tributary_declaration is not None and window.get("local_tributary_sidecar_identity_sha256") != tributary_declaration["identity_sha256"]:
        raise ValueError("selected frozen window differs from its local tributary sidecar")
    declared = json.loads((output / kind / "detail-plan.json").read_text(encoding="utf-8"))
    if declared["budget"] != asdict(budget) or declared["budget_status"] != "frozen_after_calibration":
        raise ValueError("full-window bed requires unchanged frozen97 budgets")
    raw_path = output / kind / (kind + "-original-td.npz")
    raw_pin = raw_path.with_suffix(".sha256")
    if not raw_path.exists() or not raw_pin.exists():
        raise ValueError("selected original97 pinned source is not prepared")
    original, original_metadata = load_raw_td(raw_path, raw_pin.read_text(encoding="ascii").strip())
    generation = original_metadata["provenance"]["generation_metadata"]
    if (generation["native_origin"] != window["native_origin_xz"] or generation["shape"] != [97, 97]
            or generation["identity"] != declared["canonical_source_identity"]):
        raise ValueError("full-window original source differs from its frozen selection")
    x, z = np.asarray(window["native_origin_xz"], int) - 1
    rows, cols = 99, 99
    needed = [(tx, tz) for tz in range(z // 256, (z + rows - 1) // 256 + 1)
              for tx in range(x // 256, (x + cols - 1) // 256 + 1)]
    if len(needed) > 4:
        raise ValueError("full-window owned source exceeds fixed four-core work scope")
    stitched, parents, source_records = {}, [], []
    climate = np.empty((5, rows, cols), np.float32)
    for tx, tz in needed:
        path = output / ("canonical-projections-" + projection_tag) / f"tile-x{tx}-z{tz}.npz"
        if not path.exists():
            raise ValueError("accepted owning core is not prepared: " + str(path))
        result = load_projection(path)
        meta = result["metadata"]
        if (meta["algorithm"] != expected_algorithm or meta["status"] != "accepted_canonical_projection" or meta["plan_identity"] != plan["identity_sha256"]
                or meta["fixed_lake_level_m"] != lake_level_m or meta["config"]["macro_max_abs_m"] != budget.macro_max_abs_m
                or meta["config"]["macro_absolute_volume_m3"] != budget.macro_absolute_volume_m3 * 260 ** 2 / 97 ** 2
                or meta["raw_provenance"]["canonical_source_identity"] != generation["identity"]):
            raise ValueError("owning core is not accepted for the frozen source, plan, stage and budget")
        if tributary_declaration is not None and meta.get("local_tributary_sidecar_identity_sha256") != tributary_declaration["identity_sha256"]:
            raise ValueError("accepted owning core differs from its declared local tributary geometry")
        raw_support, provenance = load_cached_support(generation, tile_x=tx, tile_z=tz)
        if not np.array_equal(raw_support, result["arrays"]["original_td_m"]):
            raise ValueError("accepted core raw pixels differ from its pinned genuine TD components")
        left, right = max(x, tx * 256), min(x + cols, (tx + 1) * 256)
        top, bottom = max(z, tz * 256), min(z + rows, (tz + 1) * 256)
        crop = crop_projection(result, [int(left), int(top)], [int(bottom - top), int(right - left)])
        region = (slice(top - z, bottom - z), slice(left - x, right - x))
        for key in ("original_td_m", "projection_height_m", "owner_domain_id", "ocean_mask", "terminal_mask"):
            if key not in stitched:
                stitched[key] = np.empty((rows, cols), crop["arrays"][key].dtype)
            stitched[key][region] = crop["arrays"][key]
        component = next(record for record in provenance["tile_assembly"] if record["tile_xz"] == [tx, tz])
        tile = checked_archive(component["path"], expected_sha256=component["sha256"])
        tile_meta = json.loads(str(tile["metadata_json"].item()))
        local = (slice(top - tz * 256, bottom - tz * 256), slice(left - tx * 256, right - tx * 256))
        climate[(slice(None),) + region] = tile["climate"][(slice(None),) + local]
        source_records.append({"tile_xz": [tx, tz], "native_origin": [tx * 256, tz * 256],
            "sha256": component["sha256"], "tile_file": Path(component["path"]).name,
            "generation_identity": tile_meta["identity"], "generation_metadata": tile_meta})
        parents.append({"tile_xz": [tx, tz], "path": str(path), "archive_sha256": file_sha256(path), "identity": meta["identity"]})
    if not np.array_equal(stitched["original_td_m"][1:-1, 1:-1], original["arrays"]["height_m"]):
        raise ValueError("owned raw97 differs pixel-for-pixel from its immutable original archive")
    if np.any(stitched["terminal_mask"] & ~stitched["ocean_mask"]):
        raise ValueError("full-window dry river or mouth source contains registered wet lake support")
    raw99_path = output / kind / (kind + "-canonical-projection-" + projection_tag + "-detail-v3-assessment-v2-full-window-raw99.npz")
    raw99_pin = raw99_path.with_suffix(".sha256")
    assembled_metadata = {**generation, "native_origin": [int(x), int(z)], "shape": [99, 99], "tile_assembly": source_records}
    if not raw99_path.exists():
        with raw99_path.open("xb") as stream:
            np.savez_compressed(stream, elevation_m=stitched["original_td_m"], climate=climate,
                                metadata_json=np.array(json.dumps(assembled_metadata, allow_nan=False)))
        with raw99_pin.open("x", encoding="ascii") as stream:
            stream.write(file_sha256(raw99_path))
    if not raw99_pin.exists():
        raise ValueError("raw99 computational source lacks its immutable external SHA pin")
    raw99, raw99_metadata = load_raw_td(raw99_path, raw99_pin.read_text(encoding="ascii").strip())
    if not np.array_equal(raw99["arrays"]["height_m"], stitched["original_td_m"]):
        raise ValueError("immutable raw99 source differs from current accepted owned pixels")
    return window, original_metadata["provenance"], raw99_metadata["provenance"], stitched, parents


def prepare_full_window_beds(plan, output, budget, lake_level_m, window_kind, projection_version="v3", *, tributary_declaration=None, lake_mask=None, bed_version="v3"):
    """Explicit serial fine solves; accepted scope is exactly the frozen97 window."""
    from terrain_pipeline.channel_geometry import select_frozen_window_component, split_frozen_window_component, derive_continuous_bed, audit_frozen_window_seams, frozen_shared_sections
    from terrain_pipeline.hydrology_detail_ridge import transformed_coarse_plan
    from terrain_pipeline.hydrology_detail import _steepest_receivers

    if window_kind not in ("river", "mouth", "confluence") or (lake_level_m is None and projection_version not in ("finite-network-v1", "finite-network-v2-target-witness", "finite-network-v3-channel-feasibility", "finite-network-v4-harmonic-channel", "finite-network-v5-harmonic-channel-target-witness", "finite-network-v6-target-gradient")):
        raise ValueError("full-window beds require explicit river, mouth or confluence and a verified seasonal stage")
    if bed_version not in ("v3", "v4-center-lowest", "v5-continuous-center-lowest", "v6-joint-continuous-center-lowest", "v7-shared-sections", "v8-complete-adjacent-shared-sections"):
        raise ValueError("explicit v3, v4-center-lowest or v5-continuous-center-lowest bed version required")
    if window_kind == "confluence" and tributary_declaration is None:
        raise ValueError("full-window confluence requires its explicit frozen local tributary sidecar")
    if tributary_declaration is not None and window_kind != "confluence":
        raise ValueError("local tributary full-window beds require the declared confluence window")
    if tributary_declaration is not None:
        from terrain_pipeline.hydrology_detail_tributaries import validate_local_tributary_sidecar
        validate_local_tributary_sidecar(plan, tributary_declaration, highest_lake_level_m=lake_level_m, lake_mask=lake_mask)
    output = Path(output)
    window, raw97_provenance, raw99_provenance, arrays, parents = _owned_full_window_source(
        plan, output, window_kind, budget, lake_level_m, projection_version, tributary_declaration=tributary_declaration)
    projection_tag = _projection_tag(projection_version, tributary_declaration)
    prefix = window_kind + "-canonical-projection-" + projection_tag + "-detail-v3-assessment-v2-full-window"
    protection_options = {}
    if projection_version in ("finite-network-v1", "finite-network-v2-target-witness", "finite-network-v3-channel-feasibility", "finite-network-v4-harmonic-channel", "finite-network-v5-harmonic-channel-target-witness", "finite-network-v6-target-gradient"):
        protection_options = {"shared_boundary_protection_m": 60.0}
        projection_tag += "-d4-face-protection60m-v1"
        prefix = window_kind + "-canonical-projection-" + projection_tag + "-detail-v3-assessment-v2-full-window"
    tributary_options = ({"tributary_declaration": tributary_declaration, "highest_lake_level_m": lake_level_m,
                          "lake_mask": lake_mask} if tributary_declaration is not None else {})
    observer_options = {**tributary_options, "tributary_validation_plan": plan} if tributary_options else {}
    candidate, raw = arrays["projection_height_m"], arrays["original_td_m"]
    inner = (slice(1, -1), slice(1, -1))
    transformed = transformed_coarse_plan(plan, lake_level_m) if lake_level_m is not None else plan
    provenance = {"artifact_kind": "derived_terrain_diffusion_macro_geometry", "td_inference_run": False,
                  "parent_archive_sha256": raw97_provenance["archive_sha256"],
                  "canonical_projection_parent_identities": [parent["identity"] for parent in parents]}
    fine_support = {"algorithm": "frozen-ocean-support-continuous-zero-isoline-v1",
                    "owner_domain_id": arrays["owner_domain_id"][inner], "ocean_mask": arrays["ocean_mask"][inner]}
    native = derive_detail(transformed, raw[inner], origin_xz_m=window["origin_xz_m"], spacing_m=30,
        raw_provenance=raw97_provenance, window_kind=window_kind, budget=budget, candidate_height_m=candidate[inner],
        candidate_provenance=provenance, fine_support=fine_support, **observer_options, **protection_options)
    actual = _steepest_receivers(candidate, 30)
    destination = np.maximum(actual, 0)
    owners = arrays["owner_domain_id"]
    crossing = (actual >= 0) & (owners >= 0) & (owners.ravel()[destination] >= 0) & (owners != owners.ravel()[destination])
    sinks = (actual < 0) & ~arrays["terminal_mask"]
    native["metadata"]["cross_domain_d8_count"] = int(crossing[inner].sum())
    native["metadata"]["unplanned_interior_sink_count"] = int(sinks[inner].sum())
    reasons = [reason for reason in native["metadata"]["rejection_reasons"]
               if reason not in ("actual_d8_crosses_frozen_domain", "actual_d8_has_unplanned_interior_sinks")]
    if crossing[inner].any():
        reasons.append("actual_d8_crosses_frozen_domain")
    if sinks[inner].any():
        reasons.append("actual_d8_has_unplanned_interior_sinks")
    native["metadata"].update(rejection_reasons=reasons, native_d8_computational_support=[99, 99],
        native_d8_acceptance_scope=[97, 97], accepted_owning_core_provenance=parents,
        raw97_pixel_equal=True, raw97_array_sha256=hashlib.sha256(raw[inner].copy().tobytes()).hexdigest(),
        raw99_array_sha256=hashlib.sha256(raw.tobytes()).hexdigest())
    native["metadata"]["status"] = "rejected" if reasons else "local_compatible_global_unverified"
    native["arrays"]["local97_clipped_receiver"] = native["arrays"].pop("actual_receiver")
    native["arrays"]["actual_receiver_support99"] = actual
    native["arrays"]["cross_owner_d8_support99_mask"] = crossing
    native["arrays"]["unplanned_sink_support99_mask"] = sinks
    native["arrays"]["cross_owner_d8_mask"] = crossing[inner]
    native["arrays"]["unplanned_sink_mask"] = sinks[inner]
    native["metadata"]["identity"] = _artifact_identity(native["metadata"], native["arrays"])
    native_path = output / window_kind / (prefix + "-native97-detail.npz")
    if not native_path.exists():
        save_detail(native_path, native)
    else:
        with np.load(native_path, allow_pickle=False) as archive:
            if json.loads(str(archive["metadata_json"].item()))["identity"] != native["metadata"]["identity"]:
                raise ValueError("immutable full-window native97 detail differs")
    support_provenance = {**provenance, "parent_archive_sha256": raw99_provenance["archive_sha256"]}
    support = derive_detail(transformed, raw, origin_xz_m=np.asarray(window["origin_xz_m"]) - 30, spacing_m=30,
        raw_provenance=raw99_provenance, window_kind=window_kind, budget=budget, candidate_height_m=candidate,
        candidate_provenance=support_provenance, fine_support={**fine_support,
            "owner_domain_id": owners, "ocean_mask": arrays["ocean_mask"]}, **observer_options, **protection_options)
    support["metadata"].update(computational_support99_ledger=support["metadata"]["ledger"],
        ledger=native["metadata"]["ledger"], rejection_reasons=reasons,
        status=native["metadata"]["status"],
        acceptance_scope="original frozen97 window only; one-native-cell halo is computational support",
        original97_native_detail_identity=native["metadata"]["identity"], accepted_owning_core_provenance=parents)
    support["metadata"]["identity"] = _artifact_identity(support["metadata"], support["arrays"])
    support_path = output / window_kind / (prefix + "-support99-detail.npz")
    if not support_path.exists():
        save_detail(support_path, support)
    else:
        with np.load(support_path, allow_pickle=False) as archive:
            if json.loads(str(archive["metadata_json"].item()))["identity"] != support["metadata"]["identity"]:
                raise ValueError("immutable full-window computational support differs")
    specification = select_frozen_window_component(plan, support, window, width_m=8, maximum_segment_length_m=500, **tributary_options)
    specification = {**specification, "bed_version": bed_version}
    if bed_version == "v6-joint-continuous-center-lowest":
        specification["joint_component_solve"] = True
    pieces = split_frozen_window_component(specification)
    sections = (frozen_shared_sections(support, specification,
                complete_adjacent_pieces=bed_version == "v8-complete-adjacent-shared-sections")
                if bed_version in ("v7-shared-sections", "v8-complete-adjacent-shared-sections") else None)
    if sections is not None:
        specification["shared_sections"] = sections
    directory_name = "canonical-projection-" + projection_tag + "-detail-v3-assessment-v2-full-window-beds"
    if bed_version != "v3":
        directory_name += "-" + bed_version
    directory = output / window_kind / directory_name
    directory.mkdir(exist_ok=True)
    request_path = directory / ("request-" + source_digest(specification)[:12] + ".json")
    if not request_path.exists():
        _json_new(request_path, specification)
    completed, piece_records = [], []
    bounds_min = np.asarray(window["origin_xz_m"])
    bounds_max = bounds_min + np.array(window["shape"])[::-1] * 30 - 30
    for index, piece in enumerate(pieces):
        piece_request = {"piece": piece, "bed_version": bed_version}
        if sections is not None:
            piece_request["shared_sections"] = sections[index]
        request_digest = source_digest(piece if bed_version == "v3" else piece_request)
        piece_path = directory / f"piece-{index:03d}-{request_digest[:12]}.npz"
        failure_path = piece_path.with_suffix(".json")
        if piece_path.exists():
            result = _read_bed_piece(piece_path)
            if result["piece_request_digest"] != request_digest or result["parent_detail_identity"] != support["metadata"]["identity"]:
                raise ValueError("cached full-window piece belongs to a different shared profile")
        elif failure_path.exists():
            result = {**json.loads(failure_path.read_text(encoding="utf-8")), "arrays": {}}
            if result["piece_request_digest"] != request_digest or result["parent_detail_identity"] != support["metadata"]["identity"]:
                raise ValueError("cached full-window failure belongs to a different shared profile")
        else:
            result = derive_continuous_bed(support, piece["points_xz_m"], piece["receiver"], piece["width_m"], piece["bed_target_m"],
                fine_spacing_m=1, frozen_plan=plan, node_source_edges=piece["node_source_edges"],
                node_edge_fractions=piece["node_edge_fractions"], centerline_profile=piece["centerline_profile"], **tributary_options,
                **({"center_lowest": True} if bed_version != "v3" else {}),
                **({"continuous_center_lowest": True} if bed_version in ("v5-continuous-center-lowest", "v6-joint-continuous-center-lowest", "v7-shared-sections", "v8-complete-adjacent-shared-sections") else {}),
                **({"shared_sections": sections[index]} if sections is not None else {}),
                **({"joint_component": True} if bed_version == "v6-joint-continuous-center-lowest" else {}))
            result["bed_version"] = bed_version
            result["piece_request_digest"] = request_digest
            result["parent_detail_identity"] = support["metadata"]["identity"]
            if result.get("arrays"):
                vertices = result["arrays"]["vertices_xz_m"]
                result["arrays"]["export_scope_mask"] = np.all((vertices >= bounds_min) & (vertices <= bounds_max), axis=1)
                record = {key: value for key, value in result.items() if key != "arrays"}
                record["identity"] = _artifact_identity(record, result["arrays"])
                with piece_path.open("xb") as stream:
                    np.savez_compressed(stream, **result["arrays"], metadata_json=np.array(json.dumps(record, allow_nan=False)))
                result = _read_bed_piece(piece_path)
            else:
                _json_new(failure_path, {key: value for key, value in result.items() if key != "arrays"})
        completed.append(result)
        piece_records.append({"piece_index": index, "path": str(piece_path if result.get("arrays") else failure_path),
                              **{key: value for key, value in result.items() if key != "arrays"}})
        if not result.get("arrays"):
            break
    seam_audit = audit_frozen_window_seams(completed, specification)
    if bed_version == "v6-joint-continuous-center-lowest":
        seam_audit = {**seam_audit, "applicable": False,
            "scope": "one joint mesh; no independent internal pieces or seam test",
            "maximum_shared_full_width_bed_difference_m": None}
    local_cut = sum(result.get("ledger", {}).get("local_cut_volume_m3", 0) for result in completed)
    maximum_cut = max((result.get("ledger", {}).get("local_max_cut_m", 0) for result in completed), default=0)
    combined = native["metadata"]["ledger"]["macro_absolute_volume_m3"] + local_cut
    native_reasons = [reason for reason in reasons if reason != "continuous_fine_bed_not_certified"]
    accepted = (seam_audit["accepted"] and not native_reasons and maximum_cut <= budget.channel_max_cut_m
                and combined <= budget.total_absolute_volume_m3
                and all(result["status"] != "rejected" for result in completed))
    report = {"schema": "hydrology-canonical-projection-full-window-bed-v1", "window_kind": window_kind,
        "projection_version": projection_version, "projection_algorithm": _projection_algorithm(projection_version, tributary_declaration),
        "bed_version": bed_version,
        "assembly_algorithm": ("joint-three-arm-single-mesh-v1" if bed_version == "v6-joint-continuous-center-lowest"
                               else "bounded-complete-adjacent-feasible-fan4-section-v3" if bed_version == "v8-complete-adjacent-shared-sections"
                               else "bounded-two-sided-30m-feasible-fan4-section-v2" if sections is not None
                               else "shared-profile-subdivision-v1"),
        "geometry_solver_algorithm": "frozen-continuous-bed-v5-continuous-center-floor" if bed_version in ("v5-continuous-center-lowest", "v6-joint-continuous-center-lowest", "v7-shared-sections", "v8-complete-adjacent-shared-sections") else bed_version,
        "shared_section_algorithm": ("bounded-complete-adjacent-feasible-fan4-section-v3" if bed_version == "v8-complete-adjacent-shared-sections"
                                     else "bounded-two-sided-30m-feasible-fan4-section-v2" if sections is not None else None),
        "internal_piece_seams_applicable": bed_version != "v6-joint-continuous-center-lowest",
        "source_projection_provenance_scope": ("finite local original97 projection; owning canonical cores are not certified"
                                                if projection_version in ("finite-local-v1", "finite-network-v1", "finite-network-v2-target-witness", "finite-network-v3-channel-feasibility", "finite-network-v4-harmonic-channel", "finite-network-v5-harmonic-channel-target-witness", "finite-network-v6-target-gradient")
                                                else "accepted owning canonical projection pixels"),
        "canonical_owning_cores_certified": projection_version not in ("finite-local-v1", "finite-network-v1", "finite-network-v2-target-witness", "finite-network-v3-channel-feasibility", "finite-network-v4-harmonic-channel", "finite-network-v5-harmonic-channel-target-witness", "finite-network-v6-target-gradient"),
        "exterior_fine_continuity_certified": False,
        "local_tributary_sidecar_identity_sha256": tributary_declaration["identity_sha256"] if tributary_declaration is not None else None,
        "status": "local_full_window_geometry_global_unverified" if accepted else "rejected", "local_window_compatible": accepted,
        "plan_identity": plan["identity_sha256"], "budget": asdict(budget), "fixed_lake_level_m": lake_level_m,
        "native97_detail_path": str(native_path), "computational_support99_path": str(support_path),
        "component_request_path": str(request_path),
        "source97_raw_array_sha256": native["metadata"]["raw97_array_sha256"], "raw97_pixel_equal": True,
        "accepted_owning_core_provenance": parents, "declared_window": window,
        "coverage": specification["coverage"], "seam_audit": seam_audit,
        "declared_piece_count": len(pieces), "completed_piece_count": sum(bool(result.get("arrays")) for result in completed),
        "maximum_piece_length_m": max((float(np.linalg.norm(np.asarray(piece["points_xz_m"])[node] -
            np.asarray(piece["points_xz_m"])[destination])) for piece in pieces
            for node, destination in enumerate(piece["receiver"]) if destination >= 0), default=0),
        "fine_spacing_m": 1, "channel_max_cut_m": maximum_cut,
        "original97_native_ledger": native["metadata"]["ledger"], "parent_native_rejection_reasons": native_reasons,
        "combined97_total_absolute_volume_upper_bound_m3": combined,
        "local_cut_volume_upper_bound_m3": local_cut,
        "volume_semantics": "original97 macro plus summed complete piece cuts; overlap and computational halo cuts conservatively counted",
        "scope": "exact frozen97 edge/window intersection; genuine99 halo only supports computation; no full coarse-edge or hydraulic certificate",
        "piece_results": piece_records, "model_inference_run": False, "macro_projection_run": False,
        "global_hydrology_certified": False, "publishable": False}
    report_path = directory / ("review-" + source_digest(report)[:12] + ".json")
    if not report_path.exists():
        _json_new(report_path, report)
    return {**report, "path": str(report_path)}


def prepare_canonical_projection(plan, output, budget, lake_level_m, window_kind=None, projection_version="v3", *, tributary_declaration=None, lake_mask=None):
    """Project complete immutable canonical supports, then audit owned crops."""
    from terrain_pipeline.hydrology_detail_projection import (
        ALGORITHM, LOCAL_TRIBUTARY_ALGORITHM, ProjectionConfig, ProjectionError, prepare_cached_projection, save_projection, load_projection, crop_projection,
    )

    if lake_level_m is None:
        raise ValueError("canonical projection requires verified seasonal lake stage")
    output = Path(output)
    expected_algorithm = _projection_algorithm(projection_version, tributary_declaration)
    projection_tag = _projection_tag(projection_version, tributary_declaration)
    if tributary_declaration is not None and window_kind != "confluence":
        raise ValueError("local tributary projection requires its explicit confluence window")
    if tributary_declaration is not None:
        from terrain_pipeline.hydrology_detail_tributaries import validate_local_tributary_sidecar
        validate_local_tributary_sidecar(plan, tributary_declaration, highest_lake_level_m=lake_level_m, lake_mask=lake_mask)
    directory = output / ("canonical-projections-" + projection_tag)
    directory.mkdir(exist_ok=True)
    originals, anchors = {}, {}
    for kind in ("ridge", "river", "confluence", "mouth", "lake_shore"):
        if window_kind is not None and kind != window_kind:
            continue
        path = output / kind / (kind + "-detail.npz")
        if not path.exists():
            if window_kind == kind:
                raise ValueError("selected " + kind + " original detail is not prepared: " + str(path))
            continue
        with np.load(path, allow_pickle=False) as archive:
            originals[kind] = {"arrays": {key: archive[key].copy() for key in archive.files if key != "metadata_json"},
                               "metadata": json.loads(str(archive["metadata_json"].item()))}
        for key, record in originals[kind]["metadata"].get("baseline_node_provenance", {}).items():
            if key in anchors and source_digest(anchors[key]) != source_digest(record):
                raise ValueError("canonical coarse anchors differ between original windows")
            anchors[key] = record
    for path in sorted((output / "canonical-projection-td-nodes").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        key = record["coarse_node_key"]
        if key in anchors and anchors[key]["elevation_m"] != record["elevation_m"]:
            raise ValueError("prepared canonical projection anchor differs from pinned original")
        anchors.setdefault(key, {field: value for field, value in record.items() if field != "coarse_node_key"})
    original_shapes = {tuple(original["arrays"]["original_td_m"].shape) for original in originals.values()}
    if original_shapes != {(97, 97)}:
        raise ValueError("area-derived projection support budget requires the frozen97 window scope")
    support_volume = budget.macro_absolute_volume_m3 * (260 * 260) / (97 * 97)
    config = ProjectionConfig(macro_max_abs_m=budget.macro_max_abs_m, macro_absolute_volume_m3=support_volume)
    budget_declaration = {"schema": "hydrology-canonical-projection-support-budget-v1",
        "original97_window_budget_unchanged": asdict(budget), "support_shape": [260, 260],
        "support_area_m2": 260 * 260 * 900, "frozen97_area_m2": 97 * 97 * 900,
        "volume_per_area_m": budget.macro_absolute_volume_m3 / (97 * 97 * 900),
        "support_budget": asdict(config), "semantics": "pre-run larger support budget at frozen97 volume-per-area rate; every original97 crop keeps its unchanged budget"}
    budget_path = directory / ("support-budget-" + source_digest(budget_declaration)[:12] + ".json")
    if not budget_path.exists():
        _json_new(budget_path, budget_declaration)
    tiles, failures = {}, {}
    for kind, original in originals.items():
        metadata = original["metadata"]
        generation = metadata["raw_provenance"]["generation_metadata"]
        origin = np.asarray(generation["native_origin"], dtype=int)
        shape = original["arrays"]["original_td_m"].shape
        for tz in range(origin[1] // 256, (origin[1] + shape[0] - 1) // 256 + 1):
            for tx in range(origin[0] // 256, (origin[0] + shape[1] - 1) // 256 + 1):
                key = (tx, tz)
                if key in tiles or key in failures:
                    continue
                path = directory / ("tile-x" + str(tx) + "-z" + str(tz) + ".npz")
                try:
                    if path.exists():
                        result = load_projection(path)
                        saved = result["metadata"]
                        if (saved["algorithm"] != expected_algorithm or saved["plan_identity"] != plan["identity_sha256"] or saved["config"] != asdict(config)
                                or saved["fixed_lake_level_m"] != lake_level_m):
                            raise ValueError("immutable projection plan/configuration/stage differs")
                        if tributary_declaration is not None and saved.get("local_tributary_sidecar_identity_sha256") != tributary_declaration["identity_sha256"]:
                            raise ValueError("immutable projection local tributary sidecar differs")
                    else:
                        if expected_algorithm not in (ALGORITHM, LOCAL_TRIBUTARY_ALGORITHM):
                            raise ValueError("legacy projection version can only consume existing pinned cores")
                        result = prepare_cached_projection(plan, generation, anchors, tile_x=tx, tile_z=tz,
                            lake_level_m=lake_level_m, config=config, **({"tributary_declaration": tributary_declaration,
                            "highest_lake_level_m": lake_level_m, "lake_mask": lake_mask} if tributary_declaration is not None else {}))
                        save_projection(result, path)
                    tiles[key] = result
                except ProjectionError as error:
                    diagnostics = getattr(error, "diagnostics", {})
                    failure = {"tile_xz": [tx, tz], "status": "source_unprepared" if
                               "missing_tiles" in diagnostics or "missing_anchor_keys" in diagnostics else "rejected",
                               "reason": str(error), "diagnostics": diagnostics}
                    failures[key] = failure
                    failure_path = directory / ("tile-x" + str(tx) + "-z" + str(tz) + "-failure-" + source_digest(failure)[:12] + ".json")
                    if not failure_path.exists():
                        _json_new(failure_path, failure)
    crop_reports = []
    for kind, original in originals.items():
        metadata = original["metadata"]
        generation = metadata["raw_provenance"]["generation_metadata"]
        x, z = generation["native_origin"]
        rows, cols = original["arrays"]["original_td_m"].shape
        needed = [(tx, tz) for tz in range(z // 256, (z + rows - 1) // 256 + 1)
                  for tx in range(x // 256, (x + cols - 1) // 256 + 1)]
        if any(key not in tiles for key in needed):
            crop_reports.append({"kind": kind, "status": "source_unprepared" if any(
                failures[key]["status"] == "source_unprepared" for key in needed if key in failures) else "rejected",
                "missing_or_rejected_core_tile_xz": [list(key) for key in needed if key not in tiles]})
            continue
        stitched = {name: np.empty((rows, cols), dtype=tiles[needed[0]]["arrays"][name].dtype) for name in
                    ("original_td_m", "projection_height_m", "target_height_m", "macro_height_m", "owner_domain_id", "ocean_mask", "terminal_mask", "td_residual_retention")}
        for tx, tz in needed:
            left, right = max(x, tx * 256), min(x + cols, (tx + 1) * 256)
            top, bottom = max(z, tz * 256), min(z + rows, (tz + 1) * 256)
            cropped = crop_projection(tiles[(tx, tz)], [left, top], [bottom - top, right - left])
            region = (slice(top - z, bottom - z), slice(left - x, right - x))
            for name in stitched:
                stitched[name][region] = cropped["arrays"][name]
        if not np.array_equal(stitched["original_td_m"], original["arrays"]["original_td_m"]):
            raise ValueError("projection owned crop differs from immutable original TD pixels")
        candidate = stitched["projection_height_m"]
        provenance = {"artifact_kind": "derived_terrain_diffusion_macro_geometry", "td_inference_run": False,
            "parent_archive_sha256": metadata["raw_provenance"]["archive_sha256"],
            "proposal_array_sha256": hashlib.sha256(candidate.tobytes()).hexdigest(),
            "canonical_projection_parent_identities": [tiles[key]["metadata"]["identity"] for key in needed],
            "derivation": "exact globally owned canonical full-residual LP core crops; no window-specific fitting"}
        fine_support = {"algorithm": "frozen-ocean-support-continuous-zero-isoline-v1",
            "owner_domain_id": stitched["owner_domain_id"], "ocean_mask": stitched["ocean_mask"],
            "definition": "projection canonical core immutable continuous coast support; actual ocean constrained below sea0"}
        lake_support = None
        if np.any(stitched["terminal_mask"] & ~stitched["ocean_mask"]):
            from scipy.ndimage import label
            from terrain_pipeline.runoff import LakeGeometry as LakeGeometry
            inland = [domain for domain in plan["domains"] if domain["kind"] == "inland"]
            if len(inland) != 1:
                raise ValueError("one explicitly registered inland lake required")
            basin = LakeGeometry(plan["height_m"], plan["owner_domain_id"], inland[0], plan["spacing_m"] ** 2)
            wet = stitched["terminal_mask"] & ~stitched["ocean_mask"] & (candidate < lake_level_m)
            components, _ = label(wet)
            boundary = np.zeros(wet.shape, bool)
            boundary[[0, -1], :] = True
            boundary[:, [0, -1]] = True
            contacts = np.unique(components[wet & boundary])
            connected = np.isin(components, contacts[contacts > 0])
            lake_support = {"connected_wet_mask": connected, "level_m": lake_level_m,
                "coarse_basin_mask_sha256": hashlib.sha256(basin.mask.tobytes()).hexdigest(),
                "local_connectivity": "D4 local wet component reaches canonical registered wet basin boundary; outside fine capacity unverified",
                "fine_basin_seasonal_revalidated": False}
        from terrain_pipeline.hydrology_detail_ridge import transformed_coarse_plan
        result = derive_detail(transformed_coarse_plan(plan, lake_level_m), stitched["original_td_m"],
            origin_xz_m=metadata["origin_xz_m"], spacing_m=metadata["spacing_m"], raw_provenance=metadata["raw_provenance"],
            window_kind=kind, budget=budget, candidate_height_m=candidate, candidate_provenance=provenance,
            fine_support=fine_support, lake_support=lake_support,
            **({"tributary_declaration": tributary_declaration, "highest_lake_level_m": lake_level_m,
                "lake_mask": lake_mask, "tributary_validation_plan": plan} if tributary_declaration is not None else {}))
        result["arrays"]["td_residual_retention"] = stitched["td_residual_retention"]
        result["arrays"]["projection_target_height_m"] = stitched["target_height_m"]
        result["arrays"]["projection_macro_height_m"] = stitched["macro_height_m"]
        result["metadata"].update({"proposal_algorithm": expected_algorithm,
            "fixed_lake_level_m": lake_level_m, "source_residual_fraction": 1.0,
            "residual_retention_semantics": "target input fraction; LP constrained correction separately reflected in target-to-derived difference",
            "projection_target_correction_max_abs_m": float(np.abs(candidate - stitched["target_height_m"]).max()),
            "hydrologic_naturalness_verified": False, "fine_basin_seasonal_revalidated": False})
        result["metadata"].pop("identity")
        result["metadata"]["identity"] = source_digest({"metadata": result["metadata"], "arrays": {
            name: hashlib.sha256(value.tobytes()).hexdigest() for name, value in sorted(result["arrays"].items())}})
        destination = output / kind / (kind + "-canonical-projection-" + projection_tag + "-detail-v3-assessment-v2.npz")
        if not destination.exists():
            save_detail(destination, result)
        else:
            with np.load(destination, allow_pickle=False) as archive:
                if json.loads(str(archive["metadata_json"].item()))["identity"] != result["metadata"]["identity"]:
                    raise ValueError("immutable projection crop differs")
        crop_reports.append({"kind": kind, "path": str(destination), "status": result["metadata"]["status"],
                             "ledger": result["metadata"]["ledger"], "rejection_reasons": result["metadata"]["rejection_reasons"]})
    report = {"schema": "hydrology-canonical-projection-execution-v1", "plan_identity": plan["identity_sha256"],
              "projection_version": projection_version, "projection_algorithm": expected_algorithm,
              "local_tributary_sidecar_identity_sha256": tributary_declaration["identity_sha256"] if tributary_declaration is not None else None,
              "selected_window_kind": window_kind,
              "configuration": asdict(config), "verified_lake_level_m": lake_level_m,
              "projected_tiles": [result["metadata"] for result in tiles.values()],
              "rejected_tiles": list(failures.values()), "model_inference_run": False,
              "owned_window_crops": crop_reports,
              "continuous_fine_beds": [],
              "fine_bed_execution": "requires explicit separate component or full-window bed action",
              "global_hydrology_certified": False, "publishable": False}
    record_path = directory / ("execution-" + source_digest(report)[:12] + ".json")
    if not record_path.exists():
        _json_new(record_path, report)
    report["path"] = str(record_path)
    return report


def projection_source_declaration(plan, output, window_kind=None):
    """Read frozen window selections and compute the same finite CPU dependencies."""
    from terrain_pipeline.td_source import CORE

    output = Path(output)
    collection_path = output / "collection-plan.json"
    collection = json.loads(collection_path.read_text(encoding="utf-8")) if collection_path.exists() else None
    if collection is not None and collection["source_plan_identity"] != plan["identity_sha256"]:
        raise ValueError("frozen collection planning identity mismatch")
    kinds = (window_kind,) if window_kind else ("ridge", "river", "confluence", "mouth", "lake_shore")
    cores, nodes, generation_identity, contract = set(), set(), None, None
    selected = []
    for kind in kinds:
        frozen = next((record for record in collection["windows"] if record["kind"] == kind), None) if collection else None
        if frozen is not None and frozen["status"] != "planned":
            if window_kind:
                raise ValueError("selected " + kind + " has no frozen planned location")
            continue
        directory = output / kind
        if not directory.exists() and (output / "detail-plan.json").exists() and window_kind:
            directory = output
        detail_path = directory / (kind + "-detail.npz")
        declaration_path = directory / "detail-plan.json"
        declared = json.loads(declaration_path.read_text(encoding="utf-8")) if declaration_path.exists() else None
        if declared is not None:
            if declared["plan_identity"] != plan["identity_sha256"] or declared["seed"] != plan["seed"]:
                raise ValueError("frozen detail planning identity or seed mismatch")
            selection = next((record for record in declared["windows"] if record["kind"] == kind), None)
            if selection is None or selection["status"] != "planned":
                if window_kind:
                    raise ValueError("selected " + kind + " has no frozen planned location")
                continue
            if frozen is not None and selection != frozen:
                raise ValueError("detail window differs from its frozen collection selection")
            frozen = selection
            current_contract = source_contract(declared["generation_identity"])
            if source_digest(current_contract) != declared["canonical_source_identity"]:
                raise ValueError("frozen canonical source contract mismatch")
            identity = declared["canonical_source_identity"]
        elif detail_path.exists():
            with np.load(detail_path, allow_pickle=False) as archive:
                metadata = json.loads(str(archive["metadata_json"].item()))
            generation = metadata["raw_provenance"]["generation_metadata"]
            current_contract = generation["canonical_source_contract"]
            identity = generation["identity"]
            if source_digest(current_contract) != identity:
                raise ValueError("saved canonical source contract mismatch")
            if frozen is None:
                frozen = {"kind": kind, "status": "planned", "native_origin_xz": generation["native_origin"],
                          "shape": metadata["shape"], "spacing_m": generation["native_resolution_m"]}
        else:
            if window_kind:
                raise ValueError("selected " + kind + " frozen source declaration is not prepared")
            continue
        if generation_identity is not None and (identity != generation_identity or current_contract != contract):
            raise ValueError("projection sources do not share one canonical identity")
        generation_identity, contract = identity, current_contract
        if frozen["spacing_m"] != 30.0 or frozen["shape"] != [97, 97]:
            raise ValueError("projection source requires frozen97 native30m window scope")
        if detail_path.exists():
            with np.load(detail_path, allow_pickle=False) as archive:
                metadata = json.loads(str(archive["metadata_json"].item()))
            generation = metadata["raw_provenance"]["generation_metadata"]
            if (generation["identity"] != identity or int(generation["seed"]) != plan["seed"]
                    or generation["native_origin"] != frozen["native_origin_xz"] or metadata["shape"] != frozen["shape"]):
                raise ValueError("saved original differs from its frozen selected source window")
        selected.append(frozen)
        x, z = frozen["native_origin_xz"]
        rows, cols = frozen["shape"]
        cores.update((tx, tz) for tz in range(z // CORE, (z + rows - 1) // CORE + 1)
                     for tx in range(x // CORE, (x + cols - 1) // CORE + 1))
    if not selected:
        raise ValueError("no frozen planned source windows are prepared")
    tiles = {(tx + dx, tz + dz) for tx, tz in cores for dz in (-1, 0, 1) for dx in (-1, 0, 1)}
    for tx, tz in sorted(cores):
        window = {"origin_xz_m": [(tx * CORE - 2) * 30.0, (tz * CORE - 2) * 30.0],
                  "shape": [CORE + 4, CORE + 4], "spacing_m": 30.0}
        nodes.update(required_td_nodes(plan, window))
    for cz, cx in nodes:
        native = (np.asarray(plan["origin_xz_m"]) + np.array([cx, cz]) * plan["spacing_m"]) / 30
        nx, nz = np.floor(native).astype(int)
        tiles.update((tx, tz) for tz in range(nz // CORE, (nz + 1) // CORE + 1)
                     for tx in range(nx // CORE, (nx + 1) // CORE + 1))
    return {"schema": "hydrology-canonical-projection-source-preparation-v2", "plan_identity": plan["identity_sha256"],
        "canonical_source_identity": generation_identity, "canonical_source_contract": contract,
        "seed": plan["seed"], "owned_core_size": CORE, "halo_cells": 2,
        "maximum_component_tiles_per_core": 9, "selected_window_kind": window_kind, "windows": selected,
        "owned_core_tile_xz": [list(map(int, key)) for key in sorted(cores)],
        "required_source_tile_xz": [list(map(int, key)) for key in sorted(tiles)],
        "required_coarse_node_zx": [list(map(int, key)) for key in sorted(nodes)],
        "source_semantics": "fixed257 genuine TD inference; core256 ownership; missing only; frozen260 support plus canonical2x2 coarse anchors"}


def prepare_projection_source(plan, output, resource_tier="light", window_kind=None, *, generate=True):
    """Explicit genuine fixed-tile preparation; never regenerate original TD."""
    from diffusion.paths import configure
    output = Path(output)
    declaration = projection_source_declaration(plan, output, window_kind)
    tiles, nodes = declaration["required_source_tile_xz"], declaration["required_coarse_node_zx"]
    generation_identity = declaration["canonical_source_identity"]
    record_path = output / ("projection-source-preparation-" + source_digest(declaration)[:12] + ".json")
    if record_path.exists():
        if json.loads(record_path.read_text(encoding="utf-8")) != declaration:
            raise ValueError("immutable projection source declaration differs")
    else:
        _json_new(record_path, declaration)
    if not generate:
        return {"status": "declared_no_inference", "source_declaration": str(record_path),
                "selected_window_kind": window_kind, "required_tile_count": len(tiles),
                "required_anchor_count": len(nodes), "model_inference_run": False}
    configure()
    backend = CanonicalTDSource(ResourcePhysicalTerrainDiffusionBackend(PhysicalGenerationConfig(), resource_tier), CANONICAL_CACHE)
    if backend.identity != generation_identity:
        backend.close()
        raise ValueError("projection preparation would change canonical scientific source identity")
    generated = []
    try:
        for tx, tz in tiles:
            path = backend.cache_root / str(plan["seed"] & 0xFFFFFFFFFFFFFFFF) / ("tile-x" + str(tx) + "-z" + str(tz) + ".npz")
            missing = not path.exists()
            backend._tile(plan["seed"], tx, tz)
            if missing:
                generated.append([tx, tz])
                if resource_tier == "light":
                    import torch
                    torch.cuda.empty_cache()
                    time.sleep(5.0)
        node_folder = output / "canonical-projection-td-nodes"
        node_folder.mkdir(exist_ok=True)
        for cz, cx in nodes:
            path = node_folder / (str(cz) + "-" + str(cx) + ".json")
            world = np.asarray(plan["origin_xz_m"]) + np.array([cx, cz]) * plan["spacing_m"]
            native = world / 30
            floor = np.floor(native).astype(int)
            elevation, _, metadata = backend.generate(plan["seed"], int(floor[0]), int(floor[1]), 2)
            wx, wz = native - floor
            value = (1 - wz) * ((1 - wx) * elevation[0, 0] + wx * elevation[0, 1]) + wz * ((1 - wx) * elevation[1, 0] + wx * elevation[1, 1])
            record = {"coarse_node_key": str(cz) + ":" + str(cx), "elevation_m": float(value), "world_xz_m": world.tolist(),
                "generation_identity": backend.identity, "seed": plan["seed"], "generation_metadata": metadata,
                "native_elevation_m": elevation.tolist(), "sampling": "bilinear fixed globally aligned native 2x2 TD nodes"}
            if path.exists():
                if json.loads(path.read_text(encoding="utf-8")) != record:
                    raise ValueError("immutable canonical projection anchor differs")
            else:
                _json_new(path, record)
    finally:
        backend.close()
    return {"source_declaration": str(record_path), "required_tile_count": len(tiles), "generated_tile_xz": generated,
            "prepared_anchor_count": len(nodes), "original_windows_regenerated": False,
            "light_inter_tile_pause_s": 5.0 if resource_tier == "light" else 0.0,
            "selected_window_kind": window_kind, "resource_settings": RESOURCE_SETTINGS[resource_tier],
            "scheduling": "serial; one canonical tile at a time"}


def verify_resource_tiers(output, window_kind="ridge"):
    """Explicit small GPU check; compare actual values, not just config identity."""
    from diffusion.paths import configure

    output = Path(output)
    path = output / (window_kind + "-original-td.npz")
    source, metadata = load_raw_td(path, path.with_suffix(".sha256").read_text(encoding="ascii").strip())
    generation = metadata["provenance"]["generation_metadata"]
    if min(source["arrays"]["height_m"].shape) < 17:
        raise ValueError("saved real TD needs 17x17 available overlap")
    offset = (min(source["arrays"]["height_m"].shape) - 17) // 2
    x, z = generation["native_origin"]
    seed = int(generation["seed"])
    config = PhysicalGenerationConfig.from_record(generation["config"])
    configure()
    reference = None
    records = []
    for tier in ("light", "balanced", "large"):
        backend = CanonicalTDSource(ResourcePhysicalTerrainDiffusionBackend(config, tier), generation["canonical_cache_root"])
        try:
            elevation, climate, fresh_metadata = backend.generate(seed, x + offset, z + offset, 17)
        finally:
            backend.close()
        if backend.identity != generation["identity"]:
            raise ValueError("resource check generation identity differs from pinned source")
        if reference is None:
            reference = (elevation.copy(), climate.copy())
        delta = float(np.abs(elevation.astype(float) - reference[0]).max())
        climate_delta = float(np.abs(climate.astype(float) - reference[1]).max())
        same = np.array_equal(elevation, reference[0]) and np.array_equal(climate, reference[1])
        record = {"tier": tier, "resource_settings": RESOURCE_SETTINGS[tier], "exact_same": bool(same),
                  "maximum_height_difference_m": delta, "maximum_climate_difference": climate_delta}
        records.append(record)
        artifact = output / ("resource-check-" + tier + ".npz")
        if not artifact.exists():
            with artifact.open("xb") as stream:
                np.savez_compressed(stream, elevation_m=elevation, climate=climate,
                                    metadata_json=np.array(json.dumps(fresh_metadata, allow_nan=False)))
    original = source["arrays"]["height_m"][offset:offset + 17, offset:offset + 17]
    overlap_difference = float(np.abs(reference[0] - original).max())
    report = {"status": "verified" if all(record["exact_same"] for record in records) and overlap_difference == 0 else "failed",
              "scope": "canonical fixed 257 TD tiles under three scheduling tiers; exact 17 vs97 pixel ownership",
              "generation_identity": generation["identity"], "tiers": records,
              "saved_97_window_overlap_max_height_difference_m": overlap_difference,
              "inference_policy": "canonical tiles may be cached; resource settings apply to missing-tile real inference"}
    report_path = output / "resource-tier-review.json"
    if not report_path.exists():
        _json_new(report_path, report)
    return report


def audit_canonical_seams(output, window_kind="ridge", *, prepare_neighbors=False, maximum_difference_m=0.25):
    """Report true overlapping tile halos separately from canonical pixel ownership."""
    from terrain_pipeline.common_infra import checked_archive

    output = Path(output)
    original = output / (window_kind + "-original-td.npz")
    _, metadata = load_raw_td(original, original.with_suffix(".sha256").read_text(encoding="ascii").strip())
    generated = metadata["provenance"]["generation_metadata"]
    if generated["schema"] != "hydrology-canonical-td-window-v1":
        raise ValueError("seam audit requires genuine canonical component assembly")
    config = PhysicalGenerationConfig.from_record(generated["config"])
    seed = int(generated["seed"])
    source = CanonicalTDSource(ResourcePhysicalTerrainDiffusionBackend(config), generated["canonical_cache_root"])
    pairs = set()
    for record in generated["tile_assembly"]:
        tx, tz = record["tile_xz"]
        pairs.update(((tx, tz, tx + 1, tz), (tx, tz, tx, tz + 1)))
    folder = Path(generated["canonical_cache_root"]) / generated["identity"] / generated["seed"]
    records = []
    try:
        for ax, az, bx, bz in sorted(pairs):
            paths = [folder / ("tile-x" + str(tx) + "-z" + str(tz) + ".npz") for tx, tz in ((ax, az), (bx, bz))]
            if prepare_neighbors and not paths[1].exists():
                source.generate(seed, bx * 256, bz * 256, 1)
            if not all(path.exists() and path.with_suffix(".sha256").exists() for path in paths):
                records.append({"tile_pair_xz": [[ax, az], [bx, bz]], "status": "missing_adjacent_tile_evidence"})
                continue
            tiles = [checked_archive(path, expected_sha256=path.with_suffix(".sha256").read_text(encoding="ascii").strip()) for path in paths]
            if ax != bx:
                a, b = tiles[0]["elevation_m"][:, 256], tiles[1]["elevation_m"][:, 0]
                ca, cb = tiles[0]["climate"][:, :, 256], tiles[1]["climate"][:, :, 0]
            else:
                a, b = tiles[0]["elevation_m"][256, :], tiles[1]["elevation_m"][0, :]
                ca, cb = tiles[0]["climate"][:, 256, :], tiles[1]["climate"][:, 0, :]
            difference = np.abs(a.astype(float) - b)
            records.append({"tile_pair_xz": [[ax, az], [bx, bz]],
                "status": "diagnostic_within_limit" if difference.max() <= maximum_difference_m else "diagnostic_exceeds_limit",
                "maximum_height_halo_difference_m": float(difference.max()), "mean_height_halo_difference_m": float(difference.mean()),
                "maximum_climate_halo_difference": float(np.abs(ca.astype(float) - cb).max()),
                "exact_halo_same": bool(np.array_equal(a, b) and np.array_equal(ca, cb)),
                "tile_sha256": [file_sha256(path) for path in paths]})
    finally:
        source.close()
    report = {"schema": "hydrology-canonical-adjacent-halo-review-v1", "canonical_source_identity": generated["identity"],
              "diagnostic_maximum_difference_m": maximum_difference_m, "pairs": records,
              "status": "diagnostic_within_limit" if records and all(record["status"] == "diagnostic_within_limit" for record in records) else "unverified_or_exceeds_limit",
              "semantics": "compare duplicate diagnostic halo values from actual fixed 257-square model queries; owned pixels always use one canonical northwest core",
              "hydrologic_seam_certified": False}
    report_path = output / ("canonical-seam-review-neighbors.json" if prepare_neighbors else "canonical-seam-review.json")
    if not report_path.exists():
        _json_new(report_path, report)
    return report


def prepare_hybrid_lake_seasonal(plan, output, source_path, source_sha256, domain_id, parameters):
    """Explicit seasonal recomputation with immutable derived TD lake geometry."""
    from terrain_pipeline.runoff import SeasonalConfig as SeasonalConfig
    from builtins import ValueError as SeasonalBalanceError
    from terrain_pipeline.runoff import WATER_STEP_ALGORITHM as WATER_STEP_ALGORITHM
    from terrain_pipeline.runoff import PERIODIC_SOLVER as PERIODIC_SOLVER
    from terrain_pipeline.runoff import SHORE_EVENT_SCHEMA as SHORE_EVENT_SCHEMA
    from terrain_pipeline.runoff import load_hybrid_lake_detail as load_hybrid_lake_detail
    from terrain_pipeline.runoff import simulate_hybrid_lake_water_balance as simulate_hybrid_lake_water_balance
    from terrain_pipeline.runoff import save_hybrid_lake_bundle as save_hybrid_lake_bundle
    from terrain_pipeline.runoff import load_hybrid_lake_bundle as load_hybrid_lake_bundle

    config = SeasonalConfig(**parameters)
    request = {"source_sha256": source_sha256, "domain_id": domain_id, "parameters": asdict(config),
               "parent_plan_identity_sha256": plan["identity_sha256"],
               "water_step_algorithm": WATER_STEP_ALGORITHM, "periodic_solver_algorithm": PERIODIC_SOLVER,
               "shore_event_schema": SHORE_EVENT_SCHEMA}
    directory = Path(output) / ("hybrid-lake-seasonal-" + source_digest(request)[:12])
    if (directory / "hybrid-bundle.json").exists():
        bundle = load_hybrid_lake_bundle(plan, directory)
        if (bundle["manifest"]["fine_source_sha256"] != source_sha256
                or bundle["audit"]["domain_id"] != domain_id
                or bundle["result"]["metadata"]["parameters"] != asdict(config)):
            raise ValueError("immutable hybrid seasonal request differs")
        return {**bundle["manifest"], "path": str(directory), "seasonal_run": False}
    detail = load_hybrid_lake_detail(source_path, source_sha256)
    try:
        bundle = simulate_hybrid_lake_water_balance(plan, detail, source_sha256=source_sha256,
                                                   domain_id=domain_id, config=config)
    except SeasonalBalanceError as error:
        failure = {"status": "rejected", "request": request, "reason": str(error),
                   "diagnostics": getattr(error, "diagnostics", {}), "global_hydrology_certified": False}
        Path(output).mkdir(parents=True, exist_ok=True)
        failure_path = Path(output) / ("hybrid-lake-seasonal-failure-" + source_digest(failure)[:12] + ".json")
        if not failure_path.exists():
            _json_new(failure_path, failure)
        return {**failure, "path": str(failure_path)}
    save_hybrid_lake_bundle(plan, detail, bundle, directory, source_path=source_path, source_sha256=source_sha256)
    cold = load_hybrid_lake_bundle(plan, directory)
    return {**cold["manifest"], "path": str(directory), "seasonal_run": True,
            "model_inference_run": False, "macro_projection_run": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generate-windows", action="store_true")
    parser.add_argument("--generate-planned-condition", action="store_true", help="Explicit genuine TD re-inference with frozen elevation-only condition; requires original cache")
    parser.add_argument("--fine-components", type=Path, help="JSON keyed by window: actual frozen edge IDs/fractions, clipped nodes, receiver, width, bed targets")
    parser.add_argument("--select-fine-component", action="store_true", help="CPU select exact frozen 120m river/confluence/mouth component; writes request, does not solve")
    parser.add_argument("--fine-component-length-m", type=float, default=120.0)
    parser.add_argument("--fine-component-width-m", type=float, default=8.0)
    parser.add_argument("--wide-ridge-proposal", action="store_true", help="Explicit CPU globally wide ridge macro proposal; uses saved genuine TD detail, preserves budget")
    parser.add_argument("--global-macro-proposal", action="store_true", help="CPU sea/lake-fixed monotone global fan proposal against saved genuine TD")
    parser.add_argument("--global-residual-fraction", type=float, choices=(0.0, 0.05), default=0.0)
    parser.add_argument("--global-fine-beds", action="store_true", help="CPU actual 1m continuous bed audits against saved global residual v4 proposals")
    parser.add_argument("--canonical-projection", action="store_true", help="CPU complete cached canonical native support projection; missing genuine cache explicitly rejects")
    parser.add_argument("--canonical-projection-fine-beds", action="store_true", help="CPU actual 1m independent continuous beds from saved canonical projection crops")
    parser.add_argument("--canonical-projection-full-window-beds", action="store_true", help="CPU serial 1m beds over frozen97 river or mouth using accepted existing owning cores and genuine99 support")
    parser.add_argument("--projection-version", choices=("v2", "v3", "finite-local-v1", "finite-network-v1", "finite-network-v2-target-witness", "finite-network-v3-channel-feasibility", "finite-network-v4-harmonic-channel", "finite-network-v5-harmonic-channel-target-witness", "finite-network-v6-target-gradient"), default="v3", help="Explicit projection identity; finite variants do not certify canonical cores")
    parser.add_argument("--tributary-declaration", type=Path, help="Explicit frozen local tributary confluence sidecar for separate v3 variant projection and full-window mesh")
    parser.add_argument("--prepare-tributary-original", action="store_true", help="CPU cache-only original97 assembly at the frozen local tributary window; all genuine source tiles must already be pinned")
    parser.add_argument("--prepare-hybrid-lake-seasonal", action="store_true", help="CPU periodic lake recomputation using pinned derived TD footprint and retained coarse basin")
    parser.add_argument("--hybrid-lake-detail", type=Path, help="Pinned genuine-TD-derived lake detail NPZ")
    parser.add_argument("--hybrid-lake-detail-sha256", help="Explicit SHA256 of the selected derived lake detail archive")
    parser.add_argument("--hybrid-lake-domain-id", type=int, help="Explicit frozen inland domain for hybrid lake geometry")
    parser.add_argument("--bed-version", choices=("v3", "v4-center-lowest", "v5-continuous-center-lowest", "v6-joint-continuous-center-lowest", "v7-shared-sections", "v8-complete-adjacent-shared-sections"), default="v3", help="Full-window bed constraint variant; center-lowest variants use independent new artifacts")
    parser.add_argument("--prepare-projection-source", action="store_true", help="Explicit serial GPU missing canonical fixed tiles and anchors after immutable support declaration")
    parser.add_argument("--declare-projection-source", action="store_true", help="CPU-only finite source declaration from frozen selected windows; no model or original TD required")
    parser.add_argument("--verify-resource-tiers", action="store_true", help="Explicit GPU three-tier same 17x17 TD window verification")
    parser.add_argument("--audit-canonical-seams", action="store_true", help="CPU cold comparison of true adjacent fixed tile halos")
    parser.add_argument("--prepare-seam-neighbors", action="store_true", help="Explicit GPU generate missing east/south fixed tiles before halo audit")
    parser.add_argument("--ridge-width-m", type=float)
    parser.add_argument("--ridge-margin-m", type=float, default=1.0)
    parser.add_argument("--prepare-plan", action="store_true", help="Explicit CPU macro planning; no model inference")
    parser.add_argument("--prepare-support", action="store_true", help="Explicit CPU general canonical catchment support")
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--cell-x", type=int, default=0)
    parser.add_argument("--cell-z", type=int, default=0)
    parser.add_argument("--planning-config", type=Path)
    parser.add_argument("--prepare-seasonal", action="store_true", help="Explicit CPU seasonal solve; refused states stay failed")
    parser.add_argument("--seasonal", type=Path, help="Load a previously verified fixed-bed seasonal product")
    parser.add_argument("--seasonal-config", type=Path)
    parser.add_argument("--resource-tier", choices=("light", "balanced", "large"), default="light")
    parser.add_argument("--window-size", type=int, default=97)
    parser.add_argument("--ridge-index", type=int, default=0, help="Immutable shared-edge-list index, selected before model inference")
    parser.add_argument("--budget-frozen", action="store_true", help="Declare supplied calibration budget frozen before independent acceptance")
    parser.add_argument("--formal-collection", action="store_true", help="Prepare independent five-window directories and immutable collection declaration")
    parser.add_argument("--window-kind", choices=("ridge", "river", "confluence", "mouth", "lake_shore"),
                        help="single low-cost calibration window before batch inference")
    parser.add_argument("--lake-level-m", type=float, help="explicitly certified seasonal lake level")
    parser.add_argument("--divide-taper-width-m", type=float, default=0.0)
    parser.add_argument("--budget", type=Path, help="JSON record of explicitly frozen DetailBudget fields")
    args = parser.parse_args(argv)
    from terrain_pipeline.hydrology_planning import load_plan, plan_macro_cell, save_plan, PlanningConfig

    if args.prepare_plan or args.prepare_support:
        if args.prepare_plan and args.prepare_support:
            parser.error("select one of --prepare-plan or --prepare-support")
        args.output.mkdir(parents=True, exist_ok=True)
        configuration = PlanningConfig(**json.loads(args.planning_config.read_text(encoding="utf-8"))) if args.planning_config else None
        if args.prepare_support:
            from terrain_pipeline.hydrology_planning import plan_canonical_support
            planned = plan_canonical_support(args.seed, args.cell_x, args.cell_z, config=configuration)
        else:
            planned = plan_macro_cell(args.seed, args.cell_x, args.cell_z, config=configuration)
        plan_path = args.plan or args.output / "plan.npz"
        if plan_path.exists():
            existing = load_plan(plan_path)
            if existing["identity_sha256"] != planned["identity_sha256"]:
                raise ValueError("existing immutable plan differs")
        else:
            save_plan(planned, plan_path)
        plan = planned
    else:
        if args.plan is None:
            parser.error("--plan or explicit --prepare-plan required")
        plan = load_plan(args.plan)
    lake_mask = None
    verified_lake_level = None
    seasonal_status = "not_prepared"
    if args.prepare_seasonal or args.seasonal:
        from terrain_pipeline.runoff import SeasonalConfig as SeasonalConfig
        from builtins import ValueError as SeasonalBalanceError
        from terrain_pipeline.runoff import LakeGeometry as LakeGeometry
        from terrain_pipeline.runoff import simulate_seasonal_water_balance as simulate_seasonal_water_balance
        from terrain_pipeline.runoff import save_seasonal_water_balance as save_seasonal_water_balance
        from terrain_pipeline.runoff import load_seasonal_water_balance as load_seasonal_water_balance
        seasonal_path = args.seasonal or args.output / "seasonal.npz"
        args.output.mkdir(parents=True, exist_ok=True)
        try:
            if args.prepare_seasonal and not seasonal_path.exists():
                seasonal_config = SeasonalConfig(**json.loads(args.seasonal_config.read_text(encoding="utf-8"))) if args.seasonal_config else None
                seasonal = simulate_seasonal_water_balance(plan, config=seasonal_config)
                save_seasonal_water_balance(plan, seasonal, seasonal_path)
            else:
                seasonal = load_seasonal_water_balance(plan, seasonal_path)
            seasonal_status = "verified"
            inland = [domain for domain in plan["domains"] if domain["kind"] == "inland"]
            if inland:
                domain = inland[0]
                column = seasonal["metadata"]["domain_ids"].index(domain["domain_id"])
                lake = LakeGeometry(plan["height_m"], plan["owner_domain_id"], domain, plan["spacing_m"] ** 2)
                volumes = np.r_[seasonal["lake_volume_m3"][0, column], seasonal["lake_volume_m3"][0, column]
                                + np.cumsum(seasonal["steps"]["lake_change_m3"][:, column])]
                levels = np.array([lake.level(float(volume)) for volume in volumes])
                verified_lake_level = float(levels.max()) if args.lake_level_m is None else args.lake_level_m
                if not levels.min() <= verified_lake_level <= levels.max():
                    raise ValueError("requested shoreline level outside verified seasonal range")
                lake_mask = lake.mask
        except SeasonalBalanceError as error:
            seasonal_status = "failed"
            failure = {"status": "failed", "source_plan_identity": plan["identity_sha256"],
                       "reason": str(error), "diagnostics": getattr(error, "diagnostics", {}),
                       "shoreline_selection_permitted": False}
            failure_path = args.output / "seasonal-failure.json"
            if not failure_path.exists():
                _json_new(failure_path, failure)
    elif args.lake_level_m is not None:
        raise ValueError("lake shoreline requires verified --seasonal or --prepare-seasonal, not an arbitrary level")
    budget = DetailBudget(**json.loads(args.budget.read_text(encoding="utf-8"))) if args.budget else DetailBudget()
    tributary_declaration = json.loads(args.tributary_declaration.read_text(encoding="utf-8")) if args.tributary_declaration else None
    if args.projection_version == "finite-local-v1" and (not args.canonical_projection_full_window_beds or args.window_kind != "confluence" or tributary_declaration is None or args.canonical_projection):
        parser.error("finite-local-v1 requires full-window confluence beds and its frozen sidecar")
    if tributary_declaration is not None and not (args.canonical_projection or args.canonical_projection_full_window_beds or args.prepare_tributary_original):
        parser.error("tributary declaration requires explicit canonical projection or full-window bed action")
    if args.prepare_tributary_original and (tributary_declaration is None or not args.budget_frozen or args.budget is None or seasonal_status != "verified"):
        parser.error("tributary original requires frozen sidecar, explicit frozen budget and verified seasonal product")
    if args.bed_version != "v3" and not args.canonical_projection_full_window_beds:
        parser.error("center-lowest bed variant requires explicit full-window bed action")
    if args.prepare_hybrid_lake_seasonal and (args.hybrid_lake_detail is None or args.hybrid_lake_detail_sha256 is None
            or args.hybrid_lake_domain_id is None or seasonal_status != "verified"):
        parser.error("hybrid lake recomputation requires pinned detail, explicit inland domain and verified parent seasonal product")
    if args.formal_collection:
        if not args.budget_frozen or args.budget is None or seasonal_status != "verified":
            parser.error("formal collection requires explicit frozen --budget and verified seasonal product")
        if args.window_kind or args.generate_planned_condition or args.wide_ridge_proposal or args.global_macro_proposal or args.global_fine_beds or args.canonical_projection or args.canonical_projection_fine_beds or args.canonical_projection_full_window_beds or args.prepare_tributary_original or args.prepare_hybrid_lake_seasonal or args.prepare_projection_source or args.declare_projection_source or args.fine_components:
            parser.error("formal collection prepares five window roots; candidate and component actions use individual roots")
        selected = select_key_windows(plan, size=args.window_size, lake_level_m=verified_lake_level,
            lake_mask=lake_mask, ridge_index=args.ridge_index)
        collection = {"schema": "hydrology-formal-five-window-v1", "source_plan_identity": plan["identity_sha256"],
                      "seasonal_source_sha256": file_sha256(args.seasonal or args.output / "seasonal.npz"),
                      "budget": asdict(budget), "budget_status": "frozen_after_calibration",
                      "ridge_selection": "explicit list index fixed before inference", "ridge_index": args.ridge_index,
                      "windows": selected, "global_hydrology_certified": False}
        args.output.mkdir(parents=True, exist_ok=True)
        collection_path = args.output / "collection-plan.json"
        if collection_path.exists():
            if json.loads(collection_path.read_text(encoding="utf-8")) != collection:
                raise ValueError("immutable formal collection differs")
        else:
            _json_new(collection_path, collection)
        records = []
        for window in selected:
            records.append(prepare_windows(plan, args.output / window["kind"], generate=args.generate_windows,
                resource_tier=args.resource_tier, budget=budget, size=args.window_size, window_kind=window["kind"],
                lake_level_m=verified_lake_level, lake_mask=lake_mask, divide_taper_width_m=args.divide_taper_width_m,
                ridge_index=args.ridge_index, budget_is_frozen=True))
        report = {"status": "formal_collection_prepared", "collection_plan": str(collection_path), "windows": records}
    elif args.generate_planned_condition and not args.generate_windows:
        report = {"status": "candidate_only_reusing_pinned_original_td", "output": str(args.output)}
    elif (args.prepare_projection_source or args.declare_projection_source) and not args.generate_windows:
        report = {"status": "source_only_using_frozen_window_declarations", "output": str(args.output)}
    elif (args.fine_components or args.select_fine_component or args.wide_ridge_proposal or args.global_macro_proposal or args.global_fine_beds or args.canonical_projection or args.canonical_projection_fine_beds or args.canonical_projection_full_window_beds or args.prepare_tributary_original or args.prepare_hybrid_lake_seasonal or args.prepare_projection_source or args.declare_projection_source or args.verify_resource_tiers
          or args.audit_canonical_seams or args.prepare_seam_neighbors) and not args.generate_windows:
        report = {"status": "fine_component_only_reusing_saved_detail", "output": str(args.output)}
    else:
        report = prepare_windows(plan, args.output, generate=args.generate_windows,
            resource_tier=args.resource_tier, budget=budget, size=args.window_size,
            window_kind=args.window_kind, lake_level_m=verified_lake_level, lake_mask=lake_mask,
            divide_taper_width_m=args.divide_taper_width_m, ridge_index=args.ridge_index, budget_is_frozen=args.budget_frozen)
    report["seasonal_status"] = seasonal_status
    if args.generate_planned_condition:
        if args.window_kind is None:
            parser.error("planned condition candidate needs one explicit window")
        if args.window_kind == "lake_shore" and lake_mask is None:
            parser.error("planned lake candidate requires verified seasonal wet connected shoreline")
        report["planned_condition_candidate"] = prepare_planned_candidate(plan, args.output,
            window_kind=args.window_kind, size=args.window_size, resource_tier=args.resource_tier, budget=budget,
            lake_level_m=verified_lake_level, lake_mask=lake_mask, ridge_index=args.ridge_index)
    if args.fine_components:
        report["fine_components"] = prepare_fine_components(plan, args.output,
            json.loads(args.fine_components.read_text(encoding="utf-8")))
    if args.select_fine_component:
        from terrain_pipeline.channel_geometry import select_frozen_component
        if args.window_kind not in ("river", "confluence", "mouth"):
            parser.error("fine component requires river, confluence or mouth window")
        window = next(window for window in select_key_windows(plan, size=args.window_size, ridge_index=args.ridge_index) if window["kind"] == args.window_kind)
        with np.load(args.output / (args.window_kind + "-detail.npz"), allow_pickle=False) as archive:
            detail = {"arrays": {key: archive[key].copy() for key in archive.files if key != "metadata_json"},
                      "metadata": json.loads(str(archive["metadata_json"].item()))}
        specification = select_frozen_component(plan, detail, window, length_m=args.fine_component_length_m, width_m=args.fine_component_width_m)
        destination = args.output / (args.window_kind + "-fine-component-request.json")
        if not destination.exists():
            _json_new(destination, {args.window_kind: specification})
        report["fine_component_request"] = str(destination)
    if args.wide_ridge_proposal:
        report["wide_ridge_proposal"] = prepare_wide_ridge(plan, args.output, budget, args.ridge_width_m, args.ridge_margin_m)
    if args.global_macro_proposal:
        report["global_macro_proposal"] = prepare_global_macro(plan, args.output, budget, verified_lake_level, args.global_residual_fraction)
    if args.global_fine_beds:
        report["global_fine_beds"] = prepare_global_fine_beds(plan, args.output)
    if args.prepare_projection_source or args.declare_projection_source:
        report["projection_source_preparation"] = prepare_projection_source(plan, args.output, args.resource_tier,
            args.window_kind, generate=args.prepare_projection_source)
    if args.prepare_tributary_original:
        if args.window_kind != "confluence":
            parser.error("tributary original requires explicit confluence window")
        from terrain_pipeline.hydrology_detail_tributaries import prepare_local_tributary_original
        report["local_tributary_original"] = prepare_local_tributary_original(plan, tributary_declaration, args.output,
            budget=budget, highest_lake_level_m=verified_lake_level, lake_mask=lake_mask, resource_tier=args.resource_tier,
            canonical_cache_root=CANONICAL_CACHE)
    if args.prepare_hybrid_lake_seasonal:
        parameters = (json.loads(args.seasonal_config.read_text(encoding="utf-8")) if args.seasonal_config
                      else seasonal["metadata"]["parameters"])
        report["hybrid_lake_seasonal"] = prepare_hybrid_lake_seasonal(plan, args.output, args.hybrid_lake_detail,
            args.hybrid_lake_detail_sha256, args.hybrid_lake_domain_id, parameters)
    if args.canonical_projection:
        report["canonical_projection"] = prepare_canonical_projection(plan, args.output, budget, verified_lake_level, args.window_kind, args.projection_version,
            tributary_declaration=tributary_declaration, lake_mask=lake_mask)
    elif args.canonical_projection_fine_beds:
        report["canonical_projection_fine_beds"] = prepare_global_fine_beds(plan, args.output, canonical_projection=True, window_kind=args.window_kind, projection_version=args.projection_version)
    if args.canonical_projection_full_window_beds:
        if not args.budget_frozen or args.budget is None:
            parser.error("full-window beds require explicit frozen --budget")
        report["canonical_projection_full_window_beds"] = prepare_full_window_beds(
            plan, args.output, budget, verified_lake_level, args.window_kind, args.projection_version,
            tributary_declaration=tributary_declaration, lake_mask=lake_mask, bed_version=args.bed_version)
    if args.verify_resource_tiers:
        report["resource_tier_verification"] = verify_resource_tiers(args.output, args.window_kind or "ridge")
    if args.audit_canonical_seams or args.prepare_seam_neighbors:
        report["canonical_seam_review"] = audit_canonical_seams(args.output, args.window_kind or "ridge",
                                                              prepare_neighbors=args.prepare_seam_neighbors)
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    return report


if __name__ == "__main__":
    main()
