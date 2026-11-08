"""Finite native TD proposals, material stocks, and saved synthetic refusals."""

import argparse
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, load_bundle, validate_source
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_cutoff import CutoffConfig
from terrain_pipeline.surface_rivers.metric_cutoff_product import (
    CutoffMaterialConfig, _corridor, build_cutoff_material_candidate,
    load_cutoff_material_candidate, save_cutoff_material_candidate,
)
from terrain_pipeline.surface_rivers.metric_morphology_product import (
    KINDS, build_morphology_proposal, load_morphology_proposal, save_morphology_proposal,
)
from terrain_pipeline.td_basin_source import load_td_source, PRIMARY_PATH, PRIMARY_SHA256
from tools.prepare_td_morphology_candidates import _terrain_window, _point


def inputs_for(terrain):
    shape = terrain.elevation_m.shape
    land = np.zeros(shape, bool)
    land[:, :16] = terrain.valid_mask[:, :16]
    water = terrain.valid_mask & ~land
    centerline = np.asarray([_point(terrain, 5, 5), _point(terrain, 5, 14),
        _point(terrain, 10, 20), _point(terrain, 20, 20), _point(terrain, 27, 14), _point(terrain, 27, 5)], np.float64)
    return {"land_mask": land, "water_mask": water, "centerline_xz_m": centerline,
            "path_cells": np.array([(16, c) for c in range(12, 18)], np.int64)}


def parameters_for(kind, terrain):
    configs = {"delta": {"max_radius_cells": 4, "max_deposit_depth_m": .8, "seed": 17},
        "cutoff": {"neck_distance_m": 900., "min_loop_length_m": 60., "max_bed_rise_m": 10000.},
        "bank_pointbar": {"max_erosion_depth_m": .05, "max_deposit_depth_m": .05},
        "braided": {"max_candidates": 3, "branch_fraction": .2},
        "alluvial_fan": {"max_fan_radius_m": 180., "max_deposit_depth_m": .5},
        "floodplain": {"bank_height_m": 30., "max_floodplain_half_width_m": 180.}}
    return {"edge_ids": ["design-edge-%d" % i for i in range(5)], "config": configs[kind],
            "solid_m3": 1200. if kind in ("delta", "alluvial_fan") else 20.,
            "water_m3_s": 8., "water_depth_m": 20., "apex_xz_m": _point(terrain, 16, 16),
            "direction_xz": [1., 0.]}


def verify(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "config.json").write_text(json.dumps({"version": "stage3-native-proposals-v1",
        "mass_absolute_tolerance_m3": 1e-8, "capability": "candidate", "revalidation": ["topology", "geometry", "hydraulics", "sediment", "outlet"]}, indent=2), encoding="utf-8")
    source = load_td_source()
    terrain = _terrain_window(source)
    raw = load_bundle(PRIMARY_PATH, expected_sha256=PRIMARY_SHA256, validator=validate_source)
    generation = raw["metadata"]["provenance"]["generation_metadata"]
    terrain = TerrainGrid(terrain.elevation_m, terrain.valid_mask, terrain.x0_m, terrain.z0_m,
        terrain.dx_m, terrain.dz_m, terrain.source_kind, terrain.source_id, terrain.source_sha256,
        vertical_datum=raw["metadata"]["vertical_datum"], model_version=generation["model"]["revision"],
        generation_seed=int(generation["seed"]), condition_summary=generation["conditioning_identity"],
        source_path=str(PRIMARY_PATH))
    inputs = inputs_for(terrain)
    synthetic = TerrainGrid(np.zeros((33,33)), np.ones((33,33), bool), 0., 0., 30., 30.,
        "diagnostic_dem_proxy", "explicit-flat-synthetic-refusal", "a" * 64)
    pins, cases = {}, {}
    for kind in KINDS:
        p = parameters_for(kind, terrain)
        local_inputs = dict(inputs)
        if kind == "braided":
            water = np.zeros(terrain.valid_mask.shape, bool)
            water[15:18, 12:18] = terrain.valid_mask[15:18, 12:18]
            local_inputs["water_mask"] = water
        result = build_morphology_proposal(kind, terrain, local_inputs, p)
        if result["metadata"]["status"] != "candidate":
            raise ValueError("TD " + kind + " did not produce a candidate")
        repeated = build_morphology_proposal(kind, terrain, local_inputs, p)
        if repeated["identity_sha256"] != result["identity_sha256"]:
            raise ValueError("morphology determinism failed")
        path = output / (kind + "-candidate.npz")
        save_morphology_proposal(path, result)
        cold = load_morphology_proposal(path, expected_sha256=file_sha256(path))
        pins[kind] = {"path": path.name, "sha256": file_sha256(path), "identity_sha256": cold["identity_sha256"], "schema": cold["metadata"]["schema"]}
        bad = inputs_for(synthetic)
        bp = parameters_for(kind, synthetic)
        if kind == "delta":
            bad["water_mask"][:] = False
        elif kind == "cutoff":
            bp["config"]["neck_distance_m"] = 1.
        elif kind == "bank_pointbar":
            bad["centerline_xz_m"] = bad["centerline_xz_m"].astype(np.float32)
        elif kind == "braided":
            bad["path_cells"] = np.array([[16,16],[16,18]], np.int64)
        elif kind == "alluvial_fan":
            bp["direction_xz"] = [0., 0.]
        else:
            bad["centerline_xz_m"] = np.repeat(bad["centerline_xz_m"][:1], 2, axis=0)
        refused = build_morphology_proposal(kind, synthetic, bad, bp)
        if refused["metadata"]["status"] != "rejected" or not refused["metadata"]["failure_reason"]:
            raise ValueError(kind + " synthetic counterexample did not refuse")
        rpath = output / (kind + "-rejected.npz")
        save_morphology_proposal(rpath, refused)
        rcold = load_morphology_proposal(rpath, expected_sha256=file_sha256(rpath))
        pins[kind + "_rejected"] = {"path": rpath.name, "sha256": file_sha256(rpath), "identity_sha256": rcold["identity_sha256"], "schema": rcold["metadata"]["schema"]}
        cases[kind] = {"status": "candidate", "deterministic": True, "cold_read": True,
                       "synthetic_failure": rcold["metadata"]["failure_reason"]}
    config = CutoffMaterialConfig()
    old = _corridor(terrain, inputs["centerline_xz_m"], config.corridor_half_width_m)
    material = build_cutoff_material_candidate(terrain, inputs["centerline_xz_m"], tuple(parameters_for("cutoff",terrain)["edge_ids"]),
        old.astype(float)*.02, old.astype(float)*.001, np.full(old.shape,.05), terrain.elevation_m-2.,
        CutoffConfig(**parameters_for("cutoff",terrain)["config"]), config)
    if material["metadata"]["status"] != "candidate":
        raise ValueError("TD cutoff material proposal refused")
    mp = output / "cutoff-material.npz"
    save_cutoff_material_candidate(mp, material)
    cold = load_cutoff_material_candidate(mp, expected_sha256=file_sha256(mp))
    pins["cutoff_material"] = {"path": mp.name, "sha256": file_sha256(mp),
        "identity_sha256": cold["identity_sha256"], "schema": cold["metadata"]["schema"]}
    a = cold["arrays"]
    residual = a["residual_mask"]
    stage = cold["metadata"]["event_record"]["parameters"]["residual_level_pool_stage_m"]
    vh = float(np.maximum(stage-a["after_bed_m"][residual],0.).sum()*terrain.cell_area_m2)
    water = float(a["residual_water_m3"].sum())
    if abs(vh-water)>1e-8:
        raise ValueError("independent native residual lake V(h) mismatch")
    cases["cutoff_material"] = {"native_residual_Vh_m3":vh,"residual_water_m3":water,
        "surviving_water_m3":float(a["surviving_water_m3"].sum()), "material_ledger":cold["metadata"]["material_ledger"],
        "provenance":"explicit old native-cell inventory scenario; no solved water-state migration",
        "residual_connectivity":"unvalidated native support volume, not certified connected oxbow lake"}
    root = Path(__file__).resolve().parents[1]
    delta_report = root / "verification/td-natural-river-stages/delta-sediment-20261011-canonical/report.json"
    delta = json.loads(delta_report.read_text(encoding="utf-8"))
    feedback_report = root / "verification/td-natural-river-stages/water-morphology-20261011-fixed/acceptance.json"
    feedback = json.loads(feedback_report.read_text(encoding="utf-8"))
    linked = {"delta_sediment": {"report_path": str(delta_report), "report_sha256": file_sha256(delta_report),
        "product_path": str(delta_report.parent / "candidate.npz"), "product_sha256": delta["artifact_sha256"],
        "identity_sha256": delta["identity_sha256"], "scope": "independent canonical TD reach window, not this33x33 proposal"},
        "bed_feedback": {"report_path": str(feedback_report), "report_sha256": file_sha256(feedback_report),
            "products": [{"path": str(feedback_report.parent / pin["path"]), "sha256": pin["sha256"],
                          "identity_sha256": pin["identity_sha256"]} for pin in feedback["artifacts"].values()],
            "scope": "independent actual bounded 4node TD PL water/sediment recoupling, not proposal dynamics"}}
    report = {"schema":"td-stage3-native-morphology-evidence-v1","status":"accepted_candidate_contracts",
        "source":{"path":str(PRIMARY_PATH),"sha256":PRIMARY_SHA256,"identity_sha256":source["identity_sha256"]},
        "terrain_identity_sha256":terrain.identity_sha256,"artifacts":pins,"cases":cases,
        "time_semantics":"static candidate scenario, no physical elapsed time",
        "capabilities":{"topology_mutation":False,"hydraulic":False,"natural_outlet":False,"publishable":False},
        "source_metadata": raw["metadata"], "linked_evidence": linked}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    existed = args.output.exists()
    try:
        result = verify(args.output)
    except Exception as error:
        if not existed and args.output.is_dir():
            (args.output / "rejection.json").write_text(json.dumps({"status": "rejected", "reason": str(error)}, indent=2), encoding="utf-8")
        raise
    print(json.dumps({"status": result["status"], "artifacts": len(result["artifacts"])}))
