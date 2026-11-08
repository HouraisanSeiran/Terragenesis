"""v4 carrier-bounded bedload using the frozen transactional v3 scheduler.

Only transient interval-runner inputs use its legacy v3 schema protocol;
all published checkpoints and final reports have v4 identity and provenance.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import FunctionType, SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import run_natural_fv_growth_v3 as previous
from tools import run_natural_fv_growth_interval_v3 as interval
from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.surface_rivers.metric_fv_growth_coupling_v4 import advance_growth


SELF = "tools/run_natural_fv_growth_v4.py"
IMPLEMENTATIONS = (*interval.IMPLEMENTATIONS,
    "terrain_pipeline/surface_rivers/metric_fv_incident_wave_vectorized.py",
    "terrain_pipeline/surface_rivers/metric_fv_bedload_v4.py",
    "terrain_pipeline/surface_rivers/metric_fv_growth_coupling_v4.py", SELF)
CONTRACT = {"schema": "same-direction-net-carrier-finite-bedload-v4",
    "solid_capacity_fraction": "1-porosity", "layer_height_bound": "carrier wet section",
    "normal_grain_speed_bound": "same-direction net carrier speed",
    "counterflow": "MPM requests opposite to interval net water transfer rejected and recorded",
    "waves": "vectorized Airy field; frozen 16 phase MPM and exchange formulas",
    "limitation": "no oscillatory gross flux or wave-driven counterflow representation"}
CAPTURE_FIELDS = ("mpm_internal_requested_solid_m3", "carrier_internal_capacity_solid_m3",
    "carrier_internal_accepted_solid_m3", "mpm_boundary_requested_solid_m3",
    "carrier_boundary_capacity_solid_m3", "carrier_boundary_accepted_solid_m3")


def identities():
    return {name: file_sha256(ROOT / name) for name in IMPLEMENTATIONS}


def load_checkpoint(path):
    saved = previous.read_arrays(path)
    meta = json.loads(str(saved.pop("metadata_json")))
    source_schema = meta["schema"]
    if source_schema == "finite-FV-growth-checkpoint-v4":
        if meta["implementation_hashes"] != identities() or meta["bedload_transport_contract"] != CONTRACT:
            raise ValueError("v4 checkpoint implementation or carrier contract mismatch")
    elif source_schema == "finite-FV-growth-checkpoint-v3":
        previous.load_checkpoint(path)
    else:
        raise ValueError("explicit complete v3 or v4 checkpoint required")
    meta.update(schema="finite-FV-growth-checkpoint-v4", implementation_hashes=identities(),
        resumed_checkpoint=str(path), resumed_checkpoint_sha256=file_sha256(path), bedload_transport_contract=deepcopy(CONTRACT))
    meta["checkpoint_migration"] = {"from_schema": source_schema, "source": str(path),
        "source_sha256": file_sha256(path), "to_runner_sha256": identities()[SELF],
        "policy": "verified source implementation; preserve complete bed/floor/h/hu/hv/suspended/source cursor and quota; v4 finite-carrier acceptance and vectorized waves"}
    return saved, meta


def save_checkpoint(path, data, meta):
    meta.update(schema="finite-FV-growth-checkpoint-v4", implementation_hashes=identities(),
        bedload_transport_contract=deepcopy(CONTRACT))
    previous.save_checkpoint(path, data, meta)


def run_interval(args):
    data = previous.read_arrays(args.resume)
    meta = json.loads(str(data.pop("metadata_json")))
    if meta["schema"] != "finite-FV-growth-checkpoint-v4" or meta["implementation_hashes"] != identities():
        raise ValueError("v4 interval requires certified v4 state")
    # The frozen interval executor's schema check is a storage protocol only.
    # Its private advance binding below is explicitly v4, with v4 hashes.
    meta["schema"] = "finite-FV-growth-checkpoint-v3"
    protocol_path = args.output.parent / ".interval-v3-protocol.npz"
    previous.save_checkpoint(protocol_path, data, meta)
    trial_args = deepcopy(args)
    trial_args.resume = protocol_path
    aggregate = {}

    def advance_with_evidence(*positional, **keyword):
        observer = keyword["interval_observer"]

        def observe(packet, bedload, suspended, ledger):
            for key in CAPTURE_FIELDS:
                value = bedload[key]
                if key not in aggregate:
                    aggregate[key] = np.zeros_like(value)
                aggregate[key] += value
            actual = bedload["internal_transfer_solid_m3"]
            boundary_actual = bedload["boundary_export_solid_m3"]
            evidence = {
                "carrier_internal_accepted_abs_solid_m3": abs(actual),
                "carrier_internal_max_capacity_violation_solid_m3": np.asarray(np.maximum(abs(actual) - bedload["carrier_internal_capacity_solid_m3"], 0.).max(initial=0.)),
                "carrier_internal_max_direction_violation_solid_m3": np.asarray(np.where(actual * packet["internal_transfer_m3"] <= 0., abs(actual), 0.).max(initial=0.)),
                "carrier_boundary_accepted_actual_solid_m3": boundary_actual,
                "carrier_boundary_max_capacity_violation_solid_m3": np.asarray(np.maximum(boundary_actual - bedload["carrier_boundary_capacity_solid_m3"], 0.).max(initial=0.))}
            for key, value in evidence.items():
                if key not in aggregate:
                    aggregate[key] = np.zeros_like(value)
                if "_max_" in key:
                    aggregate[key] = np.maximum(aggregate[key], value)
                else:
                    aggregate[key] += value
            number = packet["interval"]
            if number % args.packet_stride == 0:
                np.savez_compressed(args.output / "packets" / f"{number:07d}-carrier.npz",
                    **{key: bedload[key] for key in CAPTURE_FIELDS},
                    accepted_internal_transfer_solid_m3=bedload["internal_transfer_solid_m3"],
                    accepted_boundary_export_solid_m3=bedload["boundary_export_solid_m3"],
                    water_internal_transfer_m3=packet["internal_transfer_m3"],
                    water_boundary_transfer_m3=packet["boundary_transfer_m3"])
            observer(packet, bedload, suspended, ledger)

        keyword["interval_observer"] = observe
        return advance_growth(*positional, **keyword)

    private_run = FunctionType(interval.run.__code__, dict(interval.run.__globals__,
        IMPLEMENTATIONS=IMPLEMENTATIONS, advance_growth=advance_with_evidence), name="run_v4_interval")
    try:
        report = private_run(trial_args)
    finally:
        protocol_path.unlink(missing_ok=True)
    checkpoint = Path(report["checkpoint"])
    final_data = previous.read_arrays(checkpoint)
    final_meta = json.loads(str(final_data.pop("metadata_json")))
    save_checkpoint(checkpoint, final_data, final_meta)
    for path in args.output.glob("chunk-audit-*.npz"):
        arrays = previous.read_arrays(path)
        arrays.update({"bedload_" + key: value for key, value in aggregate.items()})
        np.savez_compressed(path, **arrays)
    return report


def finish(*args, **kwargs):
    private_finish = FunctionType(previous.finish.__code__, dict(previous.finish.__globals__, identities=identities))
    report = private_finish(*args, **kwargs)
    report.update(schema="finite-FV-suspended-growth-v4", bedload_transport_contract=deepcopy(CONTRACT),
        limitations="same-direction interval-net carrier bound on finite MPM bedload; no oscillatory gross/wave-driven counterflow; v3 exchange and slope; no wave radiation stress; adaptive time accuracy not certified")
    (args[0] / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run(args):
    executor = SimpleNamespace(run=run_interval, append_source=interval.append_source)
    private_run = FunctionType(previous.run.__code__, dict(previous.run.__globals__,
        legacy=executor, identities=identities, load_checkpoint=load_checkpoint,
        save_checkpoint=save_checkpoint, finish=finish), name="run_carrier_growth")
    return private_run(args)


def parser():
    result = previous.parser()
    result.description = __doc__
    return result


if __name__ == "__main__":
    interval.resource_limits()
    arguments = parser().parse_args()
    if not arguments.resume:
        raise ValueError("explicit complete checkpoint required")
    print(json.dumps(run(arguments), indent=2))
