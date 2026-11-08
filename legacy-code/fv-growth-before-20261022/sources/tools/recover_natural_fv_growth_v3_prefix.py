"""Reassemble only fully committed v3 chunk/checkpoint evidence, without simulation."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.inspect_natural_fv_growth import audit_chunk, read_arrays
from tools.run_natural_fv_growth_v3 import STATE, finish, identities, load_checkpoint
from terrain_pipeline.mountain_source_adapter import file_sha256


def recover(source, through_checkpoint, parameters_from, output):
    started = time.monotonic()
    template = json.loads(parameters_from.read_text(encoding="utf-8"))
    last_index = int(through_checkpoint.stem.split("-")[-1])
    initial_data, start = load_checkpoint(Path(template["parameters"]["resume"]))
    final_data = read_arrays(through_checkpoint)
    end = json.loads(str(final_data.pop("metadata_json")))
    if end["schema"] != "finite-FV-growth-checkpoint-v3" or end["implementation_hashes"] != identities():
        raise ValueError("exact v3 completed checkpoint signatures required")
    if end["resumed_checkpoint_sha256"] != start["resumed_checkpoint_sha256"]:
        raise ValueError("template and recovered run have different parent checkpoints")
    parameters = deepcopy(template["parameters"])
    config = end["exchange_config"]
    parameters.update(disable_exchange=not config["enabled"], disable_slope=not config["slope_enabled"],
        erosion_velocity=config["erosion_velocity_m_s"], exchange_max_concentration=config["maximum_concentration"],
        critical_slope=config["critical_slope_m_m"], slope_mobility=config["slope_mobility_m2_s"], output=str(output))
    # For a failed branch no summary exists; confirm its supplied physical template against all saved ledgers.
    records = json.loads((source / "interval-ledgers.json").read_text(encoding="utf-8"))
    ledgers = [row for row in records if int(row["global_interval"]) < last_index]
    if [row["global_interval"] for row in ledgers] != list(range(last_index)):
        raise ValueError("complete contiguous prefix ledgers required")
    if any(row["injected_solid_m3"] > 1.e-10 for row in ledgers) and parameters["supply_off"]:
        raise ValueError("source-off template disagrees with committed injection")
    snapshots = {key: [initial_data[key].copy()] for key in STATE}
    times = [start["physical_time_s"]]
    files = []
    count = 0
    for path in sorted(source.glob("chunk-audit-*.npz")):
        index = int(path.stem.split("-")[-1])
        if index > last_index:
            continue
        block = read_arrays(path)
        if "suspended_entrained_solid_m3" not in block or "slope_internal_transfer_solid_m3" not in block:
            raise ValueError("v3 exchange and slope evidence required")
        audit = audit_chunk(block)
        if (audit["maximum_cell_water_mismatch_m3"] > 1.e-7 or audit["maximum_cell_momentum_mismatch_m4_s"] > 1.e-6
                or audit["maximum_cell_suspended_mismatch_solid_m3"] > 1.e-8 or audit["maximum_cell_bed_mismatch_solid_m3"] > 1.e-8):
            raise ValueError("invalid committed chunk ledger: " + str(path))
        count += int(block["aggregated_interval_count"])
        if count != index:
            raise ValueError("chunk naming/count coverage mismatch")
        np.testing.assert_allclose(times[-1], block["absolute_time_start_s"], atol=1.e-10, rtol=0.)
        checkpoint = source / f"checkpoint-{index:07d}.npz"
        saved = read_arrays(checkpoint)
        meta = json.loads(str(saved["metadata_json"]))
        if meta["exchange_config"] != config or meta["implementation_hashes"] != identities():
            raise ValueError("inconsistent committed mechanism parameters/signatures")
        for key in STATE:
            np.testing.assert_array_equal(block["before_" + key], snapshots[key][-1])
            np.testing.assert_array_equal(block["after_" + key], saved[key])
            snapshots[key].append(saved[key].copy())
        times.append(float(block["absolute_time_end_s"]))
        files.extend((path, checkpoint))
    if count != last_index:
        raise ValueError("requested completed checkpoint not reached")
    for key in STATE:
        np.testing.assert_array_equal(snapshots[key][-1], final_data[key])
    np.testing.assert_allclose(ledgers[-1]["physical_time_end_s"], times[-1], atol=1.e-10, rtol=0.)
    output.mkdir(parents=True, exist_ok=False)
    for path in files:
        shutil.copy2(path, output / path.name)
    status = "completed-prefix-after-rejected-step" if not (source / "summary.json").exists() else "completed-prefix-for-matched-comparison"
    report = finish(output, snapshots, times, final_data, start, end, ledgers, argparse.Namespace(**parameters),
        started, status, [{"recovered_prefix_interval_count": count, "rejected_or_later_chunks_included": False}])
    report["recovery_provenance"] = {"source_directory": str(source), "through_checkpoint": str(through_checkpoint),
        "through_checkpoint_sha256": file_sha256(through_checkpoint), "physical_parameter_template": str(parameters_from),
        "physical_parameter_template_sha256": file_sha256(parameters_from),
        "template_policy": "same-parent physical forcing template; checkpoint supplies exact exchange/slope settings; disabled flags replaced from checkpoint",
        "recovered_without_simulation": True, "source_files_unchanged": True}
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {key: report[key] for key in ("status", "actual_duration_s", "planned_duration_s", "injected_solid_m3",
        "exported_solid_m3", "combined_residual_solid_m3", "checkpoint")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--through-checkpoint", type=Path, required=True)
    parser.add_argument("--parameters-from", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(recover(args.source, args.through_checkpoint, args.parameters_from, args.output), indent=2))
