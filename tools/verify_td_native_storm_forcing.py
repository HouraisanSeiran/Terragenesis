"""Light serial native TD weather generation and externally pinned cold reads."""

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import unittest

for variable in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_storage import load_td_source_bundle as load_td_source_bundle
from terrain_pipeline.climate_forcing import SOURCE_RECORD, fixed_storm, generate_native_storm, load_native_storm, save_native_storm
from tests.test_td_native_storm_forcing import NativeStormTests


def memory():
    info = psutil.Process().memory_info()
    return dict(peak_rss_bytes=int(getattr(info, "peak_wset", info.rss)),
                peak_private_bytes=getattr(info, "peak_pagefile", None))


def main():
    tests = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeStormTests))
    if not tests.wasSuccessful():
        raise SystemExit(1)
    directory = ROOT / "verification/td-native-storm-forcing" / ("B-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    record = {**SOURCE_RECORD, "path": str(ROOT / SOURCE_RECORD["path"])}
    source = load_td_source_bundle(**record)
    if source["arrays"]["height_m"].shape != (256, 256):
        raise ValueError("fixed TD full native shape mismatch")
    cases = {}
    for direction in ("eastward", "westward"):
        result = generate_native_storm(record, parameters=fixed_storm(source, direction))
        path = directory / (direction + ".npz")
        save_native_storm(path, result)
        pin = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"])
        loaded = load_native_storm(**pin, source_record=record, expected_plan=result["metadata"]["plan"])
        rain = loaded["arrays"]["rain_mm_h"]
        factor = 30. ** 2 / 1000
        direct = math.fsum(float(value) * factor for value in rain.flat)
        interval = math.fsum(loaded["arrays"]["interval_rain_m3"])
        if abs(direct - interval) > 1e-6 + abs(direct) * 1e-12:
            raise ValueError("independent full rain volume mismatch")
        cases[direction] = dict(record=pin, plan=result["metadata"]["plan"],
            plan_identity=result["metadata"]["plan_identity"], forcing_identity=result["metadata"]["forcing_identity"],
            interval_rain_m3=loaded["arrays"]["interval_rain_m3"].tolist(), total_rain_m3=interval,
            direct_cell_fsum_m3=direct, max_rain_mm_h=float(rain.max()),
            cumulative_depth_min_mm=float(rain.sum(axis=0).min()), cumulative_depth_max_mm=float(rain.sum(axis=0).max()))
        del result, loaded, rain
        current = memory()
        if current["peak_private_bytes"] is None or max(current.values()) > 1073741824:
            publish_bytes(directory / "failed-resource.json", json.dumps(current, indent=2).encode())
            raise MemoryError("native weather job lacks passing RSS/private resource evidence")
    if file_sha256(record["path"]) != record["expected_sha256"]:
        raise ValueError("source changed during weather export")
    names = ("terrain_pipeline/climate_forcing.py", "tests/test_td_native_storm_forcing.py",
             "tools/verify_td_native_storm_forcing.py", ".scratch/terrain-framework/td-native-storm-forcing-spec-v1.md",
             "terrain_pipeline/climate_forcing.py", "terrain_pipeline/mountain_source_adapter.py",
             'terrain_pipeline/basin_storage.py')
    report = dict(schema="td-native-storm-forcing-index-v1", source=record, cases=cases,
        tests=tests.testsRun, tests_passed=True, resource=memory(), within_1GiB=True, numeric_library_threads=1,
        output_bytes=sum(path.stat().st_size for path in directory.glob("*.npz")),
        water_solved=False, hydraulic_ready=False, publishable=False,
        code_sha256={name: file_sha256(ROOT / name) for name in names})
    publish_bytes(directory / "index.json", json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"))
    print(json.dumps(dict(path=str(directory / "index.json"), sha256=file_sha256(directory / "index.json")), ensure_ascii=False))


if __name__ == "__main__":
    main()
