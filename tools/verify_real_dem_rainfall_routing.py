"""Three fixed illustrative rainfall scenarios with equation-only cold replay.

Engineering boundary discharge is an explicit assumption, never natural outlet
certification. Retained array bytes exclude graph, runoff batches and temporary
allocations and are not peak total memory. No dynamic world state is advanced.
"""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline import real_dem_rainfall_routing as rainfall
from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.real_dem_surface_network import RealDemNetwork
from tools import verify_real_dem_flat_routing as flat_exporter
from tools.verify_real_dem_outlet_classification import (
    DEFAULT_AUDIT, DEFAULT_CANDIDATE, DEFAULT_VECTORS, canonical_bytes,
    check_unchanged, confined_file, file_sha256, read_json, reject_natural_claims,
    source_record, value_hash,
)

DEFAULT_STAGE_A = flat_exporter.DEFAULT_STAGE_A
DEFAULT_STAGE_B = flat_exporter.DEFAULT_STAGE_B
DEFAULT_FLAT = ROOT / "verification/real-dem-flat-routing/run-20261001T154605807741Z"
DEFAULT_OUTPUT_ROOT = ROOT / "verification/real-dem-rainfall-routing"
ALGORITHM = "real-dem-rainfall-routing-export-v1"
SCENARIOS = ("zero_dry", "uniform", "pulse")
STEPS = 24
DT_S = 3600.0
BATCH_CELLS = 100000
SPEED_M_S = 1.0
LEDGER_KEYS = rainfall.RUNOFF_KEYS + rainfall.ROUTING_KEYS
MEMBERS = set(rainfall.ARRAY_KEYS) | {"ledger_" + name for name in LEDGER_KEYS}
MAX_JSON_BYTES = 4 * 1024 * 1024


def scenario_forcing(name):
    rain = np.zeros(STEPS, dtype=np.float64)
    parameters = RunoffParameters()
    if name == "zero_dry":
        parameters = RunoffParameters(initial_soil_mm=0., initial_fast_mm=0., initial_slow_mm=0.,
                                      potential_et_mm_h=0., percolation_mm_h=0.)
    elif name == "uniform":
        rain[:] = 5.
    elif name == "pulse":
        rain[2:4] = 40.
    else:
        raise ValueError("unknown fixed rainfall scenario")
    return rain, parameters


def algorithm_identity():
    return {"version": ALGORITHM, "export_code_sha256": file_sha256(__file__),
            "rainfall_algorithm": rainfall.ALGORITHM,
            "rainfall_code_sha256": file_sha256(rainfall.__file__),
            "runoff_code_sha256": file_sha256(importlib.import_module("terrain_pipeline.rainfall_runoff").__file__),
            "flat_code_sha256": file_sha256(importlib.import_module("terrain_pipeline.real_dem_flat_routing").__file__),
            "flat_export_code_sha256": file_sha256(flat_exporter.__file__)}


def load_inputs(candidate_path, stage_a_path, stage_b_path, flat_path, vectors_path, audit_path):
    options = {"candidate_path": candidate_path, "stage_a_path": stage_a_path,
               "stage_b_path": stage_b_path, "vectors_path": vectors_path, "audit_path": audit_path}
    directory = Path(flat_path).resolve(strict=True)
    records = {"flat_" + name: source_record(confined_file(directory, name))
               for name in ("manifest.json", "report.json", "network.npz")}
    report = flat_exporter.verify_package(directory, **options)
    candidate, unused, inputs, sources = flat_exporter.load_inputs(
        candidate_path, stage_a_path, stage_b_path, vectors_path, audit_path)
    inputs.update(records)
    check_unchanged(list(inputs.values()) + sources)
    with np.load(directory / "network.npz", allow_pickle=False) as archive:
        arrays = {name: archive[name].copy() for name in flat_exporter.ARRAY_NAMES}
    result = {"network": RealDemNetwork(**{name: arrays[name] for name in flat_exporter.stage_b.ARRAY_NAMES}),
              "component_id": arrays["component_id"], "distance_to_exit": arrays["distance_to_exit"],
              "components": report["components"], "summary": report["summary"]}
    engineering = sorted(record["cell_id"] for record in report["terminals"]
                         if record["classification"] == "boundary_clip"
                         and record["component_touches_unknown"] is False)
    actual_risks = flat_exporter.terminal_risks(candidate, result)
    expected = sorted(record["cell_id"] for record in actual_risks["terminals"]
                      if record["classification"] == "boundary_clip"
                      and record["component_touches_unknown"] is False)
    if engineering != expected or len(engineering) != report["terminal_classification_counts"]["boundary_clip"]:
        raise ValueError("engineering terminal component risk mismatch")
    if Path(flat_path).resolve() == DEFAULT_FLAT.resolve() and len(engineering) != 149:
        raise ValueError("fixed real flat package requires exactly 149 engineering boundaries")
    check_unchanged(list(inputs.values()) + sources)
    return candidate, result, engineering, inputs, sources


def configuration(engineering):
    return {"steps": STEPS, "dt_s": DT_S, "batch_cells": BATCH_CELLS, "speed_m_s": SPEED_M_S,
            "engineering_terminal_ids": engineering,
            "scenarios": {name: {"rain_mm_h": scenario_forcing(name)[0].tolist(),
                                  "parameters": asdict(scenario_forcing(name)[1])} for name in SCENARIOS}}


def resource_budget(candidate):
    cells = int(candidate["arrays"]["valid_mask"].sum())
    retained = 8 * ((2 * STEPS + 5) * cells + STEPS + len(LEDGER_KEYS) * STEPS)
    if STEPS > rainfall.MAX_STEPS or STEPS * cells > rainfall.MAX_ENTRIES or retained > rainfall.MAX_BYTES:
        raise ValueError("rainfall retained array/entry budget exceeded")
    return {"valid_cells": cells, "steps": STEPS, "retained_array_bytes_per_scenario": retained,
            "max_retained_array_bytes": rainfall.MAX_BYTES,
            "scope": "retained arrays only, not peak total memory; graph/batches/temporaries excluded",
            "scenario_processing": "write and release one scenario at a time"}


def saved_arrays(result):
    return {**{name: result[name] for name in rainfall.ARRAY_KEYS},
            **{"ledger_" + name: result["ledger"][name] for name in LEDGER_KEYS}}


def scenario_record(name, result):
    return {"metadata": result["metadata"], "summary": result["summary"],
            "ledger": {key: result["ledger"][key].tolist() for key in LEDGER_KEYS},
            "forcing": {"rain_mm_h": scenario_forcing(name)[0].tolist(),
                        "parameters": asdict(scenario_forcing(name)[1])}}


def verify_fixed_forcing(name, result, engineering):
    rain, parameters = scenario_forcing(name)
    metadata = result["metadata"]
    if (not np.array_equal(result["rain_mm_h"], rain)
            or canonical_bytes(metadata["parameters"]) != canonical_bytes(asdict(parameters))
            or metadata["dt_s"] != DT_S or metadata["batch_cells"] != BATCH_CELLS
            or metadata["speed_m_s"] != SPEED_M_S
            or metadata["engineering_terminal_ids"] != engineering):
        raise ValueError("fixed scenario forcing/initial state/engineering binding mismatch")
    reject_natural_claims(metadata)
    reject_natural_claims(result["summary"])


def expected_shapes(cells):
    shapes = {"valid_cell_ids": (cells,), "rain_mm_h": (STEPS,),
              "local_volume": (STEPS, cells), "channel_storage": (STEPS + 1, cells),
              "final_soil_mm": (cells,), "final_fast_mm": (cells,), "final_slow_mm": (cells,)}
    shapes.update({"ledger_" + name: (STEPS,) for name in LEDGER_KEYS})
    return shapes


def load_saved(path, record, cells):
    shapes = expected_shapes(cells)
    budget = sum(int(np.prod(shape)) * 8 for shape in shapes.values())
    if budget > rainfall.MAX_BYTES or Path(path).stat().st_size > budget + len(MEMBERS) * 4096:
        raise ValueError("scenario archive exceeds retained byte budget")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != len(MEMBERS) or {item.filename for item in members} != {name + ".npy" for name in MEMBERS}:
            raise ValueError("unexpected scenario archive members")
        if sum(item.file_size for item in members) > budget + len(MEMBERS) * 4096:
            raise ValueError("scenario decompressed budget exceeded")
        for item in members:
            name = item.filename[:-4]
            if item.file_size > int(np.prod(shapes[name])) * 8 + 4096:
                raise ValueError("scenario member exceeds shape byte budget")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name].copy() for name in MEMBERS}
    for name, array in arrays.items():
        dtype = np.dtype(np.int64 if name == "valid_cell_ids" else np.float64)
        if array.dtype != dtype or array.shape != shapes[name] or not np.isfinite(array).all():
            raise ValueError(f"invalid saved scenario dtype/shape/finite: {name}")
    ledger = {key: arrays["ledger_" + key] for key in LEDGER_KEYS}
    if canonical_bytes(record["ledger"]) != canonical_bytes({key: value.tolist() for key, value in ledger.items()}):
        raise ValueError("saved ledger report/archive mismatch")
    return {**{name: arrays[name] for name in rainfall.ARRAY_KEYS},
            "ledger": ledger, "metadata": record["metadata"], "summary": record["summary"]}


def base_report(candidate, engineering):
    return {"schema_version": 1, "algorithm": ALGORITHM, "config": configuration(engineering),
            "resources": resource_budget(candidate), "scenarios": {},
            "risk": {"engineering_terminal_ids": engineering, "engineering_terminal_count": len(engineering),
                     "engineering_assumption": "explicit component boundary_clip without unknown, not observed sea mouth",
                     "unknown_is_barrier": True, "natural_outlet_verified": False,
                     "ocean_outlet_certified": False},
            "source_unchanged": True,
            "notes": ["One-way delayed linear reservoir, not Saint-Venant/backwater or calibrated flood model.",
                      "Unknown/internal retained ledger entries are end-step inventories, not repeated losses.",
                      "Retained array bytes are not peak total memory.",
                      "Cold read validates saved runoff/propagation equations without simulate_dem_rainfall."]}


def make_manifest(directory, report, arrays, inputs, sources, algorithm):
    return {"schema_version": 1, "algorithm": algorithm, "algorithm_sha256": value_hash(algorithm),
            "config": report["config"], "config_sha256": value_hash(report["config"]),
            "inputs": inputs, "source_files": sources, "source_unchanged": True,
            "arrays": arrays,
            "artifacts": {name: {"path": name, "sha256": file_sha256(directory / name),
                                  "bytes": (directory / name).stat().st_size,
                                  "source_files": list(inputs.values()) + sources}
                          for name in ("report.json",) + tuple(name + ".npz" for name in SCENARIOS)}}


def validate_output(output, paths):
    verification = (ROOT.resolve() / "verification").resolve()
    allowed = (verification / "real-dem-rainfall-routing").resolve()
    if (not verification.is_relative_to(ROOT.resolve()) or not allowed.is_relative_to(verification)
            or output != allowed or any(Path(path).resolve().is_relative_to(output) for path in paths)):
        raise ValueError("output-root must be workspace/verification/real-dem-rainfall-routing, separate from sources")


def export_package(*, candidate_path=DEFAULT_CANDIDATE, stage_a_path=DEFAULT_STAGE_A,
                   stage_b_path=DEFAULT_STAGE_B, flat_path=DEFAULT_FLAT,
                   vectors_path=DEFAULT_VECTORS, audit_path=DEFAULT_AUDIT,
                   output_root=DEFAULT_OUTPUT_ROOT):
    output = Path(output_root).resolve()
    validate_output(output, (candidate_path, vectors_path, audit_path, Path(flat_path) / "manifest.json"))
    candidate, flat, engineering, inputs, sources = load_inputs(
        candidate_path, stage_a_path, stage_b_path, flat_path, vectors_path, audit_path)
    validate_output(output, [record["path"] for record in list(inputs.values()) + sources])
    report = base_report(candidate, engineering)
    algorithm = algorithm_identity()
    output.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output).free < report["resources"]["retained_array_bytes_per_scenario"] * len(SCENARIOS) + MAX_JSON_BYTES:
        raise ValueError("insufficient output disk space")
    destination = output / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    array_manifest = {}
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=output) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        for name in SCENARIOS:
            rain, parameters = scenario_forcing(name)
            result = rainfall.simulate_dem_rainfall(candidate, flat, rain, dt_s=DT_S, parameters=parameters,
                                                   batch_cells=BATCH_CELLS, speed_m_s=SPEED_M_S,
                                                   engineering_terminal_ids=engineering)
            verify_fixed_forcing(name, result, engineering)
            rainfall.validate_dem_rainfall(candidate, flat, result)
            report["scenarios"][name] = scenario_record(name, result)
            arrays = saved_arrays(result)
            array_manifest[name] = flat_exporter.stage_b.array_records(arrays)
            np.savez_compressed(staging / (name + ".npz"), **arrays)
            del arrays, result
        (staging / "report.json").write_bytes(canonical_bytes(report))
        manifest = make_manifest(staging, report, array_manifest, inputs, sources, algorithm)
        (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
        check_unchanged(list(inputs.values()) + sources)
        if destination.exists():
            raise FileExistsError(destination)
        staging.rename(destination)
    return destination, report


def verify_package(directory, *, candidate_path=DEFAULT_CANDIDATE, stage_a_path=DEFAULT_STAGE_A,
                   stage_b_path=DEFAULT_STAGE_B, flat_path=DEFAULT_FLAT,
                   vectors_path=DEFAULT_VECTORS, audit_path=DEFAULT_AUDIT):
    directory = Path(directory).resolve(strict=True)
    names = {"report.json", "manifest.json"} | {name + ".npz" for name in SCENARIOS}
    if {path.name for path in directory.iterdir()} != names:
        raise ValueError("unexpected rainfall bundle files")
    for name in names:
        confined_file(directory, name)
    for name in ("report.json", "manifest.json"):
        if (directory / name).stat().st_size > MAX_JSON_BYTES:
            raise ValueError("rainfall JSON byte budget exceeded")
    report = read_json(directory / "report.json")
    manifest = read_json(directory / "manifest.json")
    reject_natural_claims(report)
    reject_natural_claims(manifest)
    candidate, flat, engineering, inputs, sources = load_inputs(
        candidate_path, stage_a_path, stage_b_path, flat_path, vectors_path, audit_path)
    expected_report = base_report(candidate, engineering)
    arrays_manifest = {}
    for name in SCENARIOS:
        result = load_saved(directory / (name + ".npz"), report["scenarios"][name],
                            expected_report["resources"]["valid_cells"])
        verify_fixed_forcing(name, result, engineering)
        rainfall.validate_dem_rainfall(candidate, flat, result)
        expected_report["scenarios"][name] = scenario_record(name, result)
        arrays = saved_arrays(result)
        arrays_manifest[name] = flat_exporter.stage_b.array_records(arrays)
        del arrays, result
    if canonical_bytes(report) != canonical_bytes(expected_report):
        raise ValueError("rainfall report forcing/risk/ledger binding mismatch")
    expected_manifest = make_manifest(directory, report, arrays_manifest, inputs, sources, algorithm_identity())
    if canonical_bytes(manifest) != canonical_bytes(expected_manifest):
        raise ValueError("rainfall manifest code/source/input/artifact/array binding mismatch")
    check_unchanged(list(inputs.values()) + sources)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--stage-a-package", type=Path, default=DEFAULT_STAGE_A)
    parser.add_argument("--stage-b-package", type=Path, default=DEFAULT_STAGE_B)
    parser.add_argument("--flat-package", type=Path, default=DEFAULT_FLAT)
    parser.add_argument("--vectors", type=Path, default=DEFAULT_VECTORS)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--verify-package", type=Path)
    args = parser.parse_args(argv)
    options = {"candidate_path": args.candidate, "stage_a_path": args.stage_a_package,
               "stage_b_path": args.stage_b_package, "flat_path": args.flat_package,
               "vectors_path": args.vectors, "audit_path": args.audit}
    try:
        if args.verify_package is None:
            output, report = export_package(output_root=args.output_root, **options)
        else:
            output = args.verify_package.resolve()
            report = verify_package(output, **options)
        print(json.dumps({"output": str(output), "scenarios": {name: value["summary"] for name, value in report["scenarios"].items()},
                          "engineering_terminals": report["risk"]["engineering_terminal_count"],
                          "source_unchanged": True, "verified": args.verify_package is not None}, separators=(",", ":")))
    except (ValueError, OSError, KeyError, TypeError, ImportError, zipfile.BadZipFile) as error:
        parser.exit(1, f"rainfall routing verification failed: {error}\n")


if __name__ == "__main__":
    main()
