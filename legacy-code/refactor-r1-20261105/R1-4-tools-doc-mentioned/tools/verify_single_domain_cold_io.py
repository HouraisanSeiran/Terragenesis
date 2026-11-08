"""Cold-load both saved surface directions with production construction disabled."""

import argparse
import copy
import gc
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

THREAD_ENVIRONMENT = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS")
for _name in THREAD_ENVIRONMENT:
    os.environ.setdefault(_name, "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline import single_domain_surface_archive as archive
from terrain_pipeline import single_domain_surface_geometry as geometry
from terrain_pipeline import td_basin_hierarchy, td_native_storm_forcing

FORBIDDEN_MODULES = (
    "terrain_pipeline.td_basin_storage_v10", "terrain_pipeline.td_basin_storage_compiled",
    "terrain_pipeline.td_basin_forcing_v10", "terrain_pipeline.td_basin_transport_v6",
    "terrain_pipeline.regional_surface_hydraulics_accelerated", "numba", "torch",
)


def _no_construction(*args, **kwargs):
    raise RuntimeError("production construction forbidden during cold surface IO")


def _no_solver_imports():
    found = sorted(name for name in sys.modules if any(name == prefix or name.startswith(prefix+".")
                                                      for prefix in FORBIDDEN_MODULES))
    if found:
        raise RuntimeError("solver modules imported during cold IO: " + ", ".join(found))


def _save_json(path, value):
    publish_bytes(path, (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n").encode("utf-8"))
    return dict(path=str(path.resolve()), expected_sha256=file_sha256(path))


def semantic_negatives(index_path, index_sha256, context, output):
    """Repin small shadow manifests; original large archives stay read-only."""
    original_reader = archive._json
    cases = []
    for name in ("missing_frame_25", "wrong_frame_source", "fake_resource_claim", "raised_certification", "forged_report"):
        directory = output / name
        directory.mkdir()
        index, report, resource = (copy.deepcopy(context[role]) for role in ("index", "report", "resource"))
        if name == "missing_frame_25":
            index["directions"]["eastward"]["frames"].pop()
            report["directions"] = copy.deepcopy(index["directions"])
        elif name == "wrong_frame_source":
            frames = index["directions"]["eastward"]["frames"]
            frames[3]["source_page"] = copy.deepcopy(frames[4]["source_page"])
            report["directions"] = copy.deepcopy(index["directions"])
        elif name == "fake_resource_claim":
            resource["peak_private_bytes"] = archive.MAX_BYTES + 1
        elif name == "raised_certification":
            index["natural_outlet_verified"] = True
            report["natural_outlet_verified"] = True
        else:
            report["acceptance_record"]["expected_sha256"] = "0"*64
        shadow_records = {role: _save_json(directory / (role+".json"), value)
                          for role, value in (("index", index), ("report", report), ("resource", resource))}
        redirected = {str(Path(index_path).resolve()):shadow_records["index"],
                      str(Path(context["index"]["report"]["path"]).resolve()):shadow_records["report"],
                      str(Path(context["index"]["resource"]["path"]).resolve()):shadow_records["resource"]}

        def read_shadow(record, *args, **kwargs):
            replacement = redirected.get(str(Path(record["path"]).resolve()), record)
            return original_reader(replacement, *args, **kwargs)

        with patch.object(archive, "_json", side_effect=read_shadow):
            try:
                archive.load_single_domain_index(index_path, expected_sha256=index_sha256)
            except ValueError as error:
                cases.append(dict(name=name, rejected=True, reason=str(error), shadow_manifest_records=shadow_records))
            else:
                raise RuntimeError("semantic mutation accepted: " + name)
    return cases


def verify(index_path, index_sha256, output):
    started = time.monotonic()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    _no_solver_imports()
    with (patch.object(geometry, "build_geometry", _no_construction),
          patch.object(geometry, "build_water_frame", _no_construction),
          patch.object(td_basin_hierarchy, "build_basin_hierarchy", _no_construction),
          patch.object(td_native_storm_forcing, "generate_native_storm", _no_construction)):
        context = archive.load_single_domain_index(index_path, expected_sha256=index_sha256)
        summaries = {}
        for direction in ("eastward", "westward"):
            count = 0
            largest_difference = 0.
            minimum_coverage = 1.
            omitted_cells = 0
            omitted_volume = 0.
            time_seconds = []
            for item in archive.iter_single_domain_frames(context, direction):
                metadata = item["frame"]["metadata"]
                count += 1
                time_seconds.append(metadata["time_s"])
                largest_difference = max(largest_difference, abs(metadata["volume_difference_m3"]))
                minimum_coverage = min(minimum_coverage, metadata["wet_count_coverage_fraction"])
                omitted_cells += metadata["omitted_wet_cell_count"]
                omitted_volume += metadata["omitted_wet_volume_m3"]
                del item
            if count != 25 or time_seconds != [hour*3600. for hour in range(25)] or omitted_cells or omitted_volume or minimum_coverage != 1.:
                raise ValueError("cold surface frame/time/cell coverage incomplete")
            summaries[direction] = dict(frames=count, saved_time_s=time_seconds, cell_coverage_fraction=minimum_coverage,
                                        omitted_wet_cells=omitted_cells, omitted_wet_volume_m3=omitted_volume,
                                        maximum_volume_difference_m3=largest_difference,
                                        four_state_checkpoint_chain_verified=True, independent_cell_and_whole_budgets_verified=True)
            print(f"{direction}: complete 25-frame cold read passed", flush=True)
            gc.collect()
        negatives_directory = output / "semantic-negative-fixtures"
        negatives_directory.mkdir()
        negatives = semantic_negatives(index_path, index_sha256, context, negatives_directory)
        _no_solver_imports()
        elapsed = time.monotonic()-started
        if elapsed > archive.BUDGETS["max_wall_s"]:
            raise RuntimeError("cold surface wall budget exceeded")
        report = dict(schema="single-domain-surface-cold-io-verification-v1",
                      index_record=dict(path=str(Path(index_path).resolve()), expected_sha256=index_sha256),
                      directions=summaries, frame_count=sum(value["frames"] for value in summaries.values()),
                      semantic_negatives=negatives, production_construction_disabled=True,
                      forbidden_solver_modules_absent=True, resource=dict(archive._memory(), elapsed_s=elapsed),
                      runtime=dict(python_executable=sys.executable,
                                   thread_environment={name:os.environ.get(name) for name in THREAD_ENVIRONMENT}),
                      solver_advanced=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                      limitations=context["index"]["limitations"])
        if file_sha256(index_path) != index_sha256:
            raise ValueError("source surface index changed during cold verification")
        pin = _save_json(output / "report.json", report)
        print(json.dumps(dict(report=pin, frames=report["frame_count"], resource=report["resource"])), flush=True)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    verify(args.index, args.index_sha256, args.output)


if __name__ == "__main__":
    main()
