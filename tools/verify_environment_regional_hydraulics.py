"""Focused real-source regional hydraulic handoff/cold-resume acceptance."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline import environment_product as process
from terrain_pipeline import environment_regional_hydraulics as api
from terrain_pipeline.common_infra import file_sha256, publish_bytes


def _same(left, right):
    return {k: v["identity_sha256"] for k, v in left.items()} == {k: v["identity_sha256"] for k, v in right.items()}


def _water(regions):
    return sum(float(r["arrays"]["water_m3"].sum()) for r in regions.values())


def _solid(regions):
    return sum(float((r["arrays"]["mobile_solid_m3"] + r["arrays"]["loose_solid_m3"] - r["arrays"]["rock_removed_m3"]).sum()) for r in regions.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--process", required=True)
    parser.add_argument("--source-width", type=int, default=1400)
    parser.add_argument("--handoff-time-start", type=float)
    parser.add_argument("--generate-handoff", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    input_path = Path(args.process)
    input_sha = file_sha256(input_path)
    product = process.load_product(input_path, expected_sha256=input_sha)
    sources = product["sources"]
    paths = {input_path, Path(sources["registry_path"])}
    paths.update(Path(p["path"]) for p in sources["source_pages"])
    paths.update(Path(p["file"]) for p in sources["mask_tiles"])
    before = {str(p.resolve()): file_sha256(p) for p in sorted(paths)}
    if args.generate_handoff:
        if args.handoff_time_start is not None:
            raise ValueError("handoff interval is determined from the completed source when generating")
        mask = np.zeros_like(product["context"]["valid_mask"])
        reaches = api.select_reaches(product["context"])
        mask.ravel()[reaches[0][0]] = True
        args.handoff_time_start = product["time_s"]
        product = process.advance(product, dict(
            climate=dict(external_inflow_kg_per_s=10., uplift_gain=.01, wind_speed_m_s=1.),
            groundwater=dict(surface_conductance_m2_s=0.),
            radiation=dict(latitude_deg=30., longitude_deg=180.), hydraulic_handoff_mask=mask), 3600.)
        input_sha = process.save_product(product, out / "environment-export.npz")
    rows, cols = np.indices(product["context"]["height_m"].shape)
    row, col, _ = sources["window_row_col_size"]
    ids = ((rows + row) * args.source_width + cols + col).astype(np.int64)
    if args.handoff_time_start is None:
        regions = api.prepare_from_context(product["context"], sources, ids)
        case = "independent declared stocks on actual unchanged source geometry"
    else:
        regions = api.prepare_process_handoff(product, ids, time_start_s=args.handoff_time_start)
        case = "actual environment debited external ports into initially dry regional hydraulic owners"
    initial = deepcopy(regions)
    initial_sha = api.save_checkpoint(out / "initial.npz", initial)
    owners = {node for r in regions.values() for node in r["metadata"]["source_nodes"]}
    budget = []
    for interval in range(2):
        original = regions
        regions = api.advance(original, 2.)
        reverse = api.advance(original, 2., request_order=list(reversed(original)))
        assert _same(regions, reverse)
        external = [r["metadata"]["exports"][-1] for r in regions.values()
                    if r["metadata"]["exports"][-1]["target_node"] not in owners]
        residual_water = _water(regions) + sum(p["water_m3"] for p in external) - _water(original)
        residual_solid = _solid(regions) + sum(p["solid_m3"] for p in external) - _solid(original)
        assert abs(residual_water) < 1e-9 and abs(residual_solid) < 1e-9
        budget.append(dict(interval=interval, residual_water_m3=residual_water, residual_solid_m3=residual_solid))
        sha = api.save_checkpoint(out / ("step-" + str(interval + 1) + ".npz"), regions)
        cold = api.load_checkpoint(out / ("step-" + str(interval + 1) + ".npz"), expected_sha256=sha)
        assert _same(regions, cold)
        for name, region in cold.items():
            for packet in region["metadata"]["receipts"].values():
                assert api.deliver(region, packet)["identity_sha256"] == region["identity_sha256"]
        regions = cold
    cli = ROOT / "tools/prepare_environment_regional_hydraulics.py"
    result = subprocess.run([sys.executable, "-B", str(cli), "query", "--checkpoint", str(out / "step-2.npz"),
                             "--sha256", sha], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == api.query(regions)
    result = subprocess.run([sys.executable, "-B", str(cli), "advance", "--checkpoint", str(out / "step-2.npz"),
                             "--sha256", sha, "--dt-s", "2", "--output", str(out / "cold-step-3.npz")],
                            check=True, capture_output=True, text=True)
    cold_record = json.loads(result.stdout)
    cold = api.load_checkpoint(cold_record["path"], expected_sha256=cold_record["sha256"])
    assert _same(api.advance(regions, 2.), cold)
    after = {str(p.resolve()): file_sha256(p) for p in sorted(paths)}
    assert before == after
    source_packets = [p for r in initial.values() for p in r["metadata"]["receipts"].values()]
    if args.handoff_time_start is not None:
        assert sum(p["water_m3"] for p in source_packets) > 0.
        assert abs(_water(initial) - sum(p["water_m3"] for p in source_packets)) < 1e-12
        assert abs(_solid(initial) - sum(p["solid_m3"] for p in source_packets)) < 1e-12
    channel_packets = [p for r in regions.values() for p in r["metadata"]["exports"] if p["target_node"] in owners]
    assert any(p["water_m3"] > 0. for p in channel_packets)
    report = dict(status="passed", case=case, source_process_sha256=input_sha,
                  source_world_identity=sources["source_world_identity"],
                  source_nodes=sorted(owners), initial_checkpoint_sha256=initial_sha,
                  final_checkpoint_sha256=sha, source_files_unchanged=before == after,
                  source_files=before, source_handoff_packets=source_packets,
                  water_solid_budgets=budget, query_cold_read_equal=True,
                  resume_third_interval_equal=True, reversed_order_equal=True,
                  repeated_receipts_noop=True, initial=api.query(initial), final=api.query(regions),
                  limitations=list(next(iter(regions.values()))["metadata"]["limitations"]))
    publish_bytes(out / "acceptance.json", (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
    print(json.dumps(dict(status="passed", report=str((out / "acceptance.json").resolve()),
                          source_nodes=report["source_nodes"], water_solid_budgets=budget)))


if __name__ == "__main__":
    main()
