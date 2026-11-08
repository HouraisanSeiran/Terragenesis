"""New spatial-rain and recession events, without re-running frozen overflow."""

import argparse
import json
from pathlib import Path
import sys
import threading
import time

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_overflow import load_overflow_topology
from terrain_pipeline.td_basin_runoff_exchange import RunoffExchangeParameters, simulate_runoff_exchange, save_runoff_exchange

PARENT = ROOT / "verification/natural-river-network/radau-overflow-20261005-03/index.json"
PARENT_SHA = "2bdf20aaee1d3f22d4e22ed94f26c66c761896a613afa1abb6338a658ad36618"
CODE = ("terrain_pipeline/td_basin_runoff_exchange.py", "terrain_pipeline/rainfall_runoff.py",
        "terrain_pipeline/td_basin_overflow_radau.py", "tools/prepare_td_runoff_exchange.py")


def publish(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))


def compare(first, second):
    initial, refined = first["arrays"], second["arrays"]
    if (not np.array_equal(initial["rain_mm_h"], refined["rain_mm_h"])
            or not np.array_equal(initial["outflow_volume_m3"], refined["outflow_volume_m3"])
            or first["metadata"]["parameters"] != second["metadata"]["parameters"]):
        raise ValueError("comparison requires identical runoff forcing and physics")
    numerator = np.abs(np.cumsum(initial["face_net_m3"], axis=0) - np.cumsum(refined["face_net_m3"], axis=0)).sum(axis=1)
    denominator = np.abs(np.cumsum(refined["face_net_m3"], axis=0)).sum(axis=1)
    relative = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0.)
    if np.any((denominator == 0.) & (numerator > 1e-8)):
        raise ValueError("unresolved zero-flux comparison")
    stage = float(np.max(np.abs(initial["stage_m"] - refined["stage_m"])))
    result = {"scope": "surface_integrator_only; fixed 300s lumped runoff forcing; not full four-store timestep refinement",
              "max_stage_error_m": stage, "max_cumulative_net_relative_l1": float(relative.max()),
              "thresholds": {"stage_m": .001, "net_relative_l1": .01}}
    result["passed"] = stage <= .001 and result["max_cumulative_net_relative_l1"] <= .01
    return result


def run(output):
    if file_sha256(PARENT) != PARENT_SHA:
        raise ValueError("parent index pin mismatch")
    parent = json.loads(PARENT.read_text(encoding="utf-8"))
    topology_pin = parent["topology"]
    topology = load_overflow_topology(topology_pin["path"], expected_sha256=topology_pin["sha256"], expected_identity=topology_pin["identity_sha256"])
    code_pins = {name: file_sha256(ROOT / name) for name in CODE}
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    levels = topology["arrays"]["curve_level_m"][topology["arrays"]["curve_offsets"][:-1]]
    factor = .7 + .6 * (levels - levels.min()) / max(float(np.ptp(levels)), 1.)
    area = topology["arrays"]["leaf_area_m2"]
    factor /= float(np.average(factor, weights=area))
    configuration = {"parent_index": {"path": str(PARENT), "sha256": PARENT_SHA}, "topology": topology_pin,
                     "forcing_semantics": "fixed scenario: elevation-linked spatial intensity, area-normalized; half event rain then zero-rain recession; not calibrated weather or Perlin",
                     "output_interval_s": 300., "soil_fast_slow_parameters": "RunoffParameters defaults",
                     "surface_supply": "sole internal runoff release; no additional fixed coefficient or baseflow",
                     "factor_range": [float(factor.min()), float(factor.max())], "code_sha256": code_pins}
    publish(output / "configuration.json", configuration)
    process = psutil.Process()
    stopped = threading.Event()
    resources = {"peak_rss_bytes": process.memory_info().rss, "rss_limit_bytes": 1024**3, "monitor_error": None}

    def monitor():
        while not stopped.wait(.1):
            try:
                resources["peak_rss_bytes"] = max(resources["peak_rss_bytes"], process.memory_info().rss)
            except Exception as error:
                resources["monitor_error"] = str(error)
                return

    observer = threading.Thread(target=monitor, daemon=True)
    observer.start()
    started = time.perf_counter()
    cases, work = [], 0
    try:
        for name, rain_rate, duration in (("normal-spatial-recession-24h", 30., 86400.), ("strong-spatial-recession-6h", 120., 21600.)):
            config = RunoffExchangeParameters(timestep_s=300., duration_s=duration)
            steps = int(duration / config.timestep_s)
            rain = np.zeros((steps, len(area)))
            rain[:steps // 2] = rain_rate * factor
            records, previous = [], None
            for level in (0, 1):
                controls = {"max_step_s": 300. / 2**level, "rtol": 5e-7 / 2**level,
                            "atol_stage_m": 2e-7 / 2**level, "flux_atol_m3": .001 / 2**level}
                print(json.dumps({"state": "solving", "case": name, "level": level}), flush=True)
                event = simulate_runoff_exchange(topology, rain, parameters=config, source_id=name, **controls)
                work += event["metadata"]["work"]["rhs_evaluations"] * (len(area) + len(topology["faces"]))
                if resources["peak_rss_bytes"] > 1024**3 or resources["monitor_error"] or work > 6_000_000_000:
                    raise MemoryError("new coupled event resource/work budget exceeded")
                path = output / f"{name}-level-{level}.npz"
                save_runoff_exchange(event, path, topology)
                record = {"level": level, "event": {"path": path.name, "sha256": file_sha256(path), "identity_sha256": event["identity_sha256"]}, "controls": controls,
                          "work": event["metadata"]["work"], "rain_m3": float(event["arrays"]["rain_volume_m3"].sum()),
                          "et_m3": float(event["arrays"]["et_volume_m3"].sum()), "runoff_m3": float(event["arrays"]["outflow_volume_m3"].sum()),
                          "boundary_outflow_m3": float(event["arrays"]["engineering_boundary_outflow_m3"].sum()),
                          "final_four_store_m3": {store: float(event["arrays"][store + "_volume_m3"][-1].sum()) for store in ("soil", "fast", "slow", "surface")}}
                if previous is not None:
                    record["comparison"] = compare(previous, event)
                records.append(record)
                publish(output / f"{name}-level-{level}.json", record)
                print(json.dumps({"state": "saved", "case": name, "level": level, "comparison": record.get("comparison")}), flush=True)
                previous = event
            cases.append({"name": name, "levels": records, "surface_time_refinement_passed": records[-1]["comparison"]["passed"]})
    finally:
        stopped.set()
        observer.join()
    for name, expected in code_pins.items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("new coupled event code changed during solve")
    resources.update(counted_rhs_work=work, elapsed_s=time.perf_counter() - started)
    index = {"schema": "td-runoff-exchange-refinement-v1", "status": "ready_for_independent_audit", "configuration": configuration,
             "cases": cases, "resources": resources, "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
             "full_coupled_timestep_refinement_passed": False, "tailwater_verified": False}
    publish(output / "index.json", index)
    return {"index": str(output / "index.json"), "sha256": file_sha256(output / "index.json"), "resources": resources}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False))
