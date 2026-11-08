"""Independent bounded initial-terrain candidates and same-bed event comparison."""

import argparse
from dataclasses import asdict
import gc
import json
from pathlib import Path
import sys
import threading
import time

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes, save_bundle
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.basin_storage import load_td_source as load_td_source
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_storage import save_td_source as save_td_source
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_topology import save_basin_hierarchy as save_basin_hierarchy
from terrain_pipeline.basin_storage import build_overflow_topology as build_overflow_topology
from terrain_pipeline.basin_storage import load_overflow_topology as load_overflow_topology
from terrain_pipeline.basin_storage import save_overflow_topology as save_overflow_topology
from terrain_pipeline.basin_storage import RunoffExchangeParameters as RunoffExchangeParameters
from terrain_pipeline.basin_storage import simulate_runoff_exchange as simulate_runoff_exchange
from terrain_pipeline.basin_storage import save_runoff_exchange as save_runoff_exchange
from terrain_pipeline.td_bounded_conditioning import build_conditioning_candidates, validate_conditioning
from terrain_pipeline.geology import load_material_field

BASELINE = ROOT / "verification/natural-river-network/runoff-exchange-20261005-01"
SPILLS = ROOT / "verification/natural-river-network/stable-spill-paths-20261005-01"
BASELINE_SHA = "cd78c2f2ce9c6a1abbd98ae7ee528079dfb2ee1b5ce2905458e64137aa868e5f"
SPILL_SHA = "f1d6e89b3bb642f6ede52d231fa340bb41a8a03aa479ab4e889c648f361565af"
CASES = (("normal-spatial-recession-24h", 30., 86400.), ("strong-spatial-recession-6h", 120., 21600.))
CODE = ("terrain_pipeline/td_bounded_conditioning.py", 'terrain_pipeline/basin_storage.py',
        'terrain_pipeline/basin_topology.py', 'terrain_pipeline/basin_storage.py',
        'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
        'terrain_pipeline/runoff.py', "tools/prepare_td_conditioning_comparison.py")


def publish(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))


def read_pinned(path, expected_sha256):
    if file_sha256(path) != expected_sha256:
        raise ValueError("pinned input changed: " + str(path))
    return json.loads(Path(path).read_text(encoding="utf-8"))


def artifact(path, root, bundle=None):
    result = {"path": str(Path(path).relative_to(root)), "sha256": file_sha256(path)}
    if bundle is not None:
        result["identity_sha256"] = bundle["identity_sha256"]
    return result


def baseline_cell_factor(hierarchy, topology):
    curves = topology["arrays"]
    levels = curves["curve_level_m"][curves["curve_offsets"][:-1]]
    factor = .7 + .6 * (levels - levels.min()) / max(float(np.ptp(levels)), 1.)
    factor /= float(np.average(factor, weights=curves["leaf_area_m2"]))
    lookup = np.full(len(hierarchy["arrays"]["node_parent"]), np.nan)
    lookup[curves["leaf_ids"]] = factor
    owners = hierarchy["arrays"]["contribution_owner"]
    valid = hierarchy["arrays"]["valid_mask"] & ~hierarchy["arrays"]["protected_mask"]
    result = np.zeros(owners.shape)
    result[valid] = lookup[owners[valid]]
    if not np.isfinite(result).all():
        raise ValueError("original rainfall does not cover active source cells")
    return result


def aggregate_factor(cell_factor, hierarchy, topology):
    arrays = hierarchy["arrays"]
    active = arrays["valid_mask"] & ~arrays["protected_mask"]
    owner = arrays["contribution_owner"][active]
    sums = np.bincount(owner, weights=cell_factor[active], minlength=len(arrays["node_parent"]))
    counts = np.bincount(owner, minlength=len(arrays["node_parent"]))
    leaves = topology["arrays"]["leaf_ids"]
    if np.any(counts[leaves] <= 0):
        raise ValueError("new basin has no rainfall support")
    return sums[leaves] / counts[leaves]


def drainage_summary(hierarchy):
    arrays = hierarchy["arrays"]
    valid = arrays["valid_mask"].ravel()
    owner = arrays["contribution_owner"].ravel()
    area = hierarchy["metadata"]["spacing_m"] ** 2
    terminals = np.flatnonzero(valid & (arrays["receiver"] < 0))
    counts = np.bincount(owner[valid], minlength=len(arrays["node_parent"]))
    boundary_terminals = terminals[arrays["open_boundary_mask"].ravel()[terminals]]
    draining = np.isin(owner[valid], owner[boundary_terminals])
    largest = int(np.argmax(counts))
    return {"basin_count": int(len(terminals)), "largest_static_catchment_area_m2": float(counts[largest] * area),
            "largest_static_catchment_leaf_id": largest,
            "engineering_outlet_terminal_count": int(len(boundary_terminals)),
            "static_boundary_draining_area_m2": float(np.count_nonzero(draining) * area),
            "retained_internal_terminal_count": int(len(terminals) - len(boundary_terminals)),
            "semantics": "bed-receiver connectivity only; no claim of permanent river, wet flow, or natural sea outlet"}


def controls(level):
    return {"max_step_s": 300. / 2**level, "rtol": 5e-7 / 2**level,
            "atol_stage_m": 2e-7 / 2**level, "flux_atol_m3": .001 / 2**level}


def run(output):
    baseline_sha = BASELINE_SHA
    baseline = read_pinned(BASELINE / "index.json", baseline_sha)
    audit_sha = "821309de91dcd634193d622c910e4fe976f2e9e3602aa311cfe73d30ac342ff6"
    baseline_audit = read_pinned(BASELINE / "independent-audit-v2.json", audit_sha)
    if baseline_audit["status"] != "passed" or baseline_audit["index_sha256"] != baseline_sha:
        raise ValueError("baseline independent evidence is not accepted")
    spills = read_pinned(SPILLS / "index.json", SPILL_SHA)
    request_pin = spills["requests"]
    requests = read_pinned(SPILLS / request_pin["path"], request_pin["sha256"])
    hierarchy_pin = next(pin for pin in spills["source_pins"] if pin["path"].endswith("hierarchy.npz"))
    hierarchy = load_basin_hierarchy(hierarchy_pin["path"], expected_sha256=hierarchy_pin["sha256"],
                                     expected_identity=hierarchy_pin["identity_sha256"])
    source = load_td_source()
    pin = baseline["configuration"]["topology"]
    topology = load_overflow_topology(pin["path"], expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
    if topology["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]:
        raise ValueError("baseline rain topology/hierarchy differs")
    material_pin = spills["material"]
    materials = load_material_field(SPILLS / material_pin["path"], expected_sha256=material_pin["sha256"],
                                    expected_identity=material_pin["identity_sha256"])
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    code_pins = {name: file_sha256(ROOT / name) for name in CODE}
    runoff_parameters = RunoffParameters()
    configuration = {"baseline_index": {"path": str(BASELINE / "index.json"), "sha256": baseline_sha},
                     "baseline_audit": {"path": str(BASELINE / "independent-audit-v2.json"), "sha256": audit_sha},
                     "spill_index": {"path": str(SPILLS / "index.json"), "sha256": SPILL_SHA},
                     "hierarchy": hierarchy_pin, "baseline_topology": pin,
                     "forcing_semantics": "original basin rain expanded to immutable cells, area-averaged on each new basin; fixed spatial rain, not re-derived from changed bed",
                     "runoff_limitation": "basin-lumped nonlinear runoff; regrouping cells can change runoff after averaging the same rain",
                     "code_sha256": code_pins, "max_new_solves": 8,
                     "runoff_parameters": asdict(runoff_parameters),
                     "initial_water": "same default soil moisture (30mm), zero fast/slow/surface; initialized on each new bed, not transferred from old events"}
    cell_factor = baseline_cell_factor(hierarchy, topology)
    publish(output / "rainfall-grid.json", {"shape": list(cell_factor.shape), "factor": cell_factor.tolist(),
                                           "source_identity_sha256": source["identity_sha256"]})
    configuration["rainfall_grid"] = artifact(output / "rainfall-grid.json", output)
    publish(output / "configuration.json", configuration)
    bundles = build_conditioning_candidates(source, hierarchy, materials, requests)
    records, candidate_state = [], {}
    baseline_record = {"candidate_id": "baseline", "drainage": drainage_summary(hierarchy),
                       "events_reused": True, "changed_cells": 0,
                       "source_identity_sha256": source["identity_sha256"]}
    records.append(baseline_record)
    process, stop = psutil.Process(), threading.Event()
    resource = {"peak_rss_bytes": process.memory_info().rss, "counted_rhs_work": 0,
                "rss_limit_bytes": 1024**3, "rhs_work_limit": 6_000_000_000, "monitor_error": None,
                "new_solves": 0}

    def monitor():
        while not stop.wait(.1):
            try:
                resource["peak_rss_bytes"] = max(resource["peak_rss_bytes"], process.memory_info().rss)
            except Exception as error:
                resource["monitor_error"] = str(error)
                return

    def solve(candidate_id, candidate_topology, factor, case, level):
        name, rate, duration = case
        rain = np.zeros((int(duration / 300.), len(factor)))
        rain[:len(rain) // 2] = rate * factor
        print(json.dumps({"state": "solving", "candidate": candidate_id, "case": name, "level": level}), flush=True)
        event = simulate_runoff_exchange(candidate_topology, rain,
            parameters=RunoffExchangeParameters(timestep_s=300., duration_s=duration),
            runoff_parameters=runoff_parameters, source_id=name, **controls(level))
        resource["new_solves"] += 1
        resource["counted_rhs_work"] += event["metadata"]["work"]["rhs_evaluations"] * (len(factor) + len(candidate_topology["faces"]))
        if resource["peak_rss_bytes"] > 1024**3 or resource["counted_rhs_work"] > 6_000_000_000 or resource["monitor_error"]:
            raise MemoryError("candidate comparison resource budget exceeded")
        path = output / candidate_id / f"{name}-level-{level}.npz"
        save_runoff_exchange(event, path, candidate_topology)
        summary = {"level": level, "controls": controls(level), "event": artifact(path, output, event),
                   "rain_m3": float(event["arrays"]["rain_volume_m3"].sum()),
                   "boundary_outflow_m3": float(event["arrays"]["engineering_boundary_outflow_m3"].sum()),
                   "final_surface_m3": float(event["arrays"]["surface_volume_m3"][-1].sum()),
                   "work": event["metadata"]["work"]}
        del event
        gc.collect()
        publish(path.with_suffix(".json"), summary)
        return summary

    started = time.perf_counter()
    observer = threading.Thread(target=monitor, daemon=True)
    observer.start()
    try:
        for candidate_id in ("limited_fill", "limited_breach", "mixed"):
            bundle = bundles[candidate_id]
            directory = output / candidate_id
            directory.mkdir()
            save_bundle(directory / "conditioning.npz", bundle, validator=validate_conditioning)
            changed = int(np.count_nonzero(bundle["arrays"]["height_m"] != source["arrays"]["height_m"]))
            record = {"candidate_id": candidate_id, "conditioning": artifact(directory / "conditioning.npz", output, bundle),
                      "changed_cells": changed, "cases": [], "geometry_metadata": bundle["metadata"]}
            records.append(record)
            if not changed:
                record.update(status="unchanged_no_solve", drainage=baseline_record["drainage"])
                continue
            derived = make_td_source(bundle["arrays"]["height_m"], spacing_m=source["metadata"]["spacing_m"],
                origin_m_xz=source["metadata"]["origin_m_xz"], valid_mask=source["arrays"]["valid_mask"],
                protected_mask=source["arrays"]["protected_mask"], open_boundary_mask=source["arrays"]["open_boundary_mask"],
                source_sha256=source["metadata"]["source_sha256"])
            print(json.dumps({"state": "rebuilding", "candidate": candidate_id, "changed_cells": changed}), flush=True)
            derived_hierarchy = build_basin_hierarchy(derived)
            derived_topology = build_overflow_topology(derived_hierarchy)
            save_td_source(directory / "source.npz", derived)
            save_basin_hierarchy(directory / "hierarchy.npz", derived_hierarchy)
            save_overflow_topology(derived_topology, directory / "topology.json")
            factor = aggregate_factor(cell_factor, derived_hierarchy, derived_topology)
            record.update(source=artifact(directory / "source.npz", output, derived),
                          hierarchy=artifact(directory / "hierarchy.npz", output, derived_hierarchy),
                          topology=artifact(directory / "topology.json", output, derived_topology),
                          drainage=drainage_summary(derived_hierarchy), status="same_bed_events_saved")
            for case in CASES:
                record["cases"].append({"name": case[0], "levels": [solve(candidate_id, derived_topology, factor, case, 0)]})
            candidate_state[candidate_id] = (derived_topology, factor)
            publish(directory / "record.json", record)
        changed_records = [record for record in records if record["changed_cells"]]
        improved = [record for record in changed_records
                    if record["drainage"]["basin_count"] < baseline_record["drainage"]["basin_count"]
                    and record["drainage"]["largest_static_catchment_area_m2"] >= baseline_record["drainage"]["largest_static_catchment_area_m2"]]
        nominated = "baseline"
        if improved:
            nominee = min(improved, key=lambda record: (-record["drainage"]["largest_static_catchment_area_m2"],
                record["drainage"]["basin_count"],
                float(np.abs(bundles[record["candidate_id"]]["arrays"]["height_m"] - source["arrays"]["height_m"]).sum()),
                record["candidate_id"]))
            nominated = nominee["candidate_id"]
            derived_topology, factor = candidate_state[nominated]
            for case, case_record in zip(CASES, nominee["cases"]):
                case_record["levels"].append(solve(nominated, derived_topology, factor, case, 1))
    finally:
        stop.set()
        observer.join()
    for name, expected in code_pins.items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("implementation changed during candidate comparison")
    resource["elapsed_s"] = time.perf_counter() - started
    index = {"schema": "td-bounded-conditioning-comparison-v1", "status": "ready_for_independent_audit",
             "configuration": configuration, "candidates": records, "resources": resource,
             "nominated_candidate": nominated, "selected_candidate": "baseline",
             "selection_semantics": "nomination by static connectivity and disturbance; diagnostic recommendation requires independent new-bed ledgers and fixed-forcing surface refinement",
             "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
             "full_coupled_timestep_refinement_passed": False, "permanent_trunk_ready": False}
    publish(output / "index.json", index)
    return {"index": str(output / "index.json"), "sha256": file_sha256(output / "index.json"),
            "nominated_candidate": nominated, "resources": resource}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output), ensure_ascii=False))
