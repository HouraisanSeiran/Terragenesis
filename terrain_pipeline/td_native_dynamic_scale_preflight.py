"""Pinned, read-only v10 native-grid sizing and window preparation."""

import json
import math
from pathlib import Path

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_source import PRIMARY_PATH, PRIMARY_SHA256, load_td_source_bundle


ROOT = Path(__file__).resolve().parents[1]
SIZES = (256, 512, 1024, 2048)
STEPS = (2.5, 1.25)
SOURCE_SHA256 = "d09d2df4df86423547f5aa8e04efa14e98a285b0873124dd82982040434f7697"
SOURCE_IDENTITY = "8600fde239cc5b8d83a0f66c0eaa7974e2f68badc14dee341a9656d6911f199c"
DRIVER = "tools/verify_td_native_weather_storage_v10.py"
KERNEL = "terrain_pipeline/td_basin_storage_v10.py"
PAGE_IO = "terrain_pipeline/td_basin_storage_v10_io.py"
RUN_INPUTS_SHA256 = "d6601d27315281ca38e6f50f2c0d83f34552c3499bd4608572bc65a277f633fc"
RUN_INPUTS = ROOT / "verification/td-basin-generation/A-native-weather-v10-20261002T165104790989Z/run-inputs.json"
MAX_BYTES = 1073741824
WINDOW_INTERIOR = 256
HALO = 1

EVIDENCE = {
    KERNEL: ("full.shape != (24, *shape) or full.size > 4000000",
             "count > 100000 or count*len(faces) > 6000000000",
             "full = full.copy()", "states = np.zeros((4,len(bed)))"),
    PAGE_IO: ("1 <= metadata['cells'] <= 250000",
              "count * metadata['faces'] > 6000000000"),
    DRIVER: ("for hour in range(24)", "monitor = ResourceMonitor(psutil.Process())"),
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _pin_inputs():
    _require(file_sha256(RUN_INPUTS) == RUN_INPUTS_SHA256, "v10 run-inputs pin changed")
    inputs = json.loads(RUN_INPUTS.read_text(encoding="utf-8"))
    _require(inputs.get("schema") == "td-v10-spatial-weather-run-inputs-v1"
             and inputs.get("steps_s") == list(STEPS)
             and inputs.get("primary_sha256") == PRIMARY_SHA256
             and inputs.get("job_max_bytes") == MAX_BYTES
             and inputs.get("chunk_max_face_steps") == 6000000000,
             "v10 run-inputs contract changed")
    for name, snippets in EVIDENCE.items():
        path = ROOT / name
        _require(file_sha256(path) == inputs["code_sha256"].get(name), "actual v10 code pin changed: " + name)
        text = path.read_text(encoding="utf-8")
        _require(all(snippet in text for snippet in snippets), "v10 source limit changed: " + name)
    _require(Path(PRIMARY_PATH).is_file() and file_sha256(PRIMARY_PATH) == PRIMARY_SHA256,
             "original primary source changed")
    source_record = {"path": str(ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/source.npz"),
                     "expected_sha256": SOURCE_SHA256, "expected_identity": SOURCE_IDENTITY}
    source = load_td_source_bundle(**source_record)
    _require(source["metadata"]["source_sha256"] == PRIMARY_SHA256
             and source["arrays"]["height_m"].shape == (256, 256)
             and source["metadata"]["spacing_m"] == 30., "original 256x256/30m source/grid mismatch")
    hierarchy = load_basin_hierarchy(**inputs["hierarchy"])
    _require(hierarchy["metadata"]["source_identity_sha256"] == source["identity_sha256"]
             and hierarchy["arrays"]["height_m"].shape == (256, 256), "original hierarchy/source mismatch")
    return inputs, source_record, source, hierarchy


def estimate_memory(cells, faces, boundary_cells):
    rain_bytes = 24 * cells * 8
    page_bytes = (8 * cells + 13 * cells + cells + cells + cells +
                  2 * faces + 2 * boundary_cells + 4 * faces + 2 * cells) * 8 + cells
    checkpoint_bytes = (8 * cells + 4 * faces + 2 * cells) * 8
    scratch_bytes = (8 * cells + 13 * cells + 8 * cells + 8 * cells +
                     8 * faces + 4 * faces + 8 * boundary_cells) * 8
    array_scratch_estimate = 2 * rain_bytes + page_bytes + checkpoint_bytes + scratch_bytes
    return {"full_24h_rain_bytes": rain_bytes, "driver_rain_copy_bytes": rain_bytes,
            "saved_page_arrays_bytes": page_bytes, "checkpoint_arrays_bytes": checkpoint_bytes,
            "solver_and_ssprk2_scratch_reserve_bytes": scratch_bytes,
            "estimated_resident_arrays_and_scratch_bytes": array_scratch_estimate,
            "page_and_checkpoint_array_capacity_lower_bound_bytes": page_bytes + checkpoint_bytes,
            "estimate_not_measurement": True,
            "exclusions": "Python/Numba runtime, allocator fragmentation, serialization buffers and OS overhead; this is not a whole-process peak bound. Actual peak requires monitored execution."}


def _windows(size, spacing_m):
    windows = []
    for row in range(0, size, WINDOW_INTERIOR):
        for column in range(0, size, WINDOW_INTERIOR):
            row_end = min(size, row + WINDOW_INTERIOR)
            column_end = min(size, column + WINDOW_INTERIOR)
            halo_row_start = max(0, row - HALO)
            halo_column_start = max(0, column - HALO)
            halo_row_end = min(size, row_end + HALO)
            halo_column_end = min(size, column_end + HALO)
            height = halo_row_end - halo_row_start
            width = halo_column_end - halo_column_start
            cells = height * width
            faces = height * (width - 1) + width * (height - 1)
            windows.append({"interior_zx": [row, row_end, column, column_end],
                            "halo_zx": [halo_row_start, halo_row_end, halo_column_start, halo_column_end],
                            "interior_cells": (row_end - row) * (column_end - column),
                            "interior_area_m2": (row_end - row) * (column_end - column) * spacing_m**2,
                            "cells_including_halo": cells, "d4_faces_upper": faces,
                            "rain_values_24h": 24 * cells,
                            "work_face_steps_per_hour": {str(step): int(3600 / step) * faces for step in STEPS}})
    return windows


def _size(size, spacing_m):
    cells = size * size
    faces = 2 * size * (size - 1)
    work = {str(step): {"substeps_per_hour": int(3600 / step),
                         "face_steps_per_hour": int(3600 / step) * faces,
                         "face_steps_24h_per_direction": 24 * int(3600 / step) * faces,
                         "hour_work_limit_passed": int(3600 / step) * faces <= 6000000000} for step in STEPS}
    limits = {"full_rain_values_at_most_4000000": 24 * cells <= 4000000,
              "page_cells_at_most_250000": cells <= 250000,
              "hour_face_steps_at_most_6000000000": all(item["hour_work_limit_passed"] for item in work.values())}
    memory = estimate_memory(cells, faces, 4 * size - 4)
    limits["array_scratch_estimate_at_most_1gib"] = memory["estimated_resident_arrays_and_scratch_bytes"] <= MAX_BYTES
    windows = _windows(size, spacing_m)
    _require(sum((item["interior_zx"][1] - item["interior_zx"][0]) *
                 (item["interior_zx"][3] - item["interior_zx"][2]) for item in windows) == cells,
             "window interior coverage mismatch")
    return {"size_zx": [size, size], "spacing_m": spacing_m,
            "cell_area_footprint_m_xz": [size * spacing_m, size * spacing_m],
            "sample_center_span_m_xz": [(size - 1) * spacing_m, (size - 1) * spacing_m],
            "origin_convention": "origin_m_xz is the center of grid cell (z=0,x=0); each cell has area spacing_m squared",
            "cells_upper": cells,
            "d4_faces_upper_exact_for_full_valid_grid": faces, "full_24h_rain_values": 24 * cells,
            "hour_work": work, "memory": memory, "actual_v10_limits": limits,
            "actual_v10_profile_prepare_ready": all(limits.values()),
            "dynamic_solver_ready": False,
            "window_plan": {"status": "prepare_only_unimplemented", "interior_side_cells": WINDOW_INTERIOR,
                            "halo_cells": HALO, "window_count": len(windows),
                            "max_interior_area_m2": max(item["interior_area_m2"] for item in windows),
                            "max_cells_including_halo": max(item["cells_including_halo"] for item in windows),
                            "max_d4_faces_upper": max(item["d4_faces_upper"] for item in windows),
                            "windows": windows,
                            "all_window_local_limits_passed": all(
                                item["cells_including_halo"] <= 250000 and item["rain_values_24h"] <= 4000000
                                and all(value <= 6000000000 for value in item["work_face_steps_per_hour"].values())
                                for item in windows)}}


def preflight(sizes=SIZES):
    _require(tuple(sizes) == SIZES, "fixed 256/512/1024/2048 scope required")
    inputs, source_record, source, hierarchy = _pin_inputs()
    spacing_m = source["metadata"]["spacing_m"]
    cases = {str(size): _size(size, spacing_m) for size in SIZES}
    actual_faces = len(hierarchy["arrays"]["face_cells"])
    cases["256"]["actual_pinned_hierarchy_faces"] = actual_faces
    cases["256"]["actual_pinned_valid_cells"] = int(hierarchy["arrays"]["valid_mask"].sum())
    _require(actual_faces <= cases["256"]["d4_faces_upper_exact_for_full_valid_grid"],
             "actual 256 hierarchy exceeds D4 upper bound")
    return {"schema": "td-v10-native-dynamic-scale-preflight-v1", "scope": "prepare_only_no_solve",
            "run_inputs": {"path": str(RUN_INPUTS), "expected_sha256": RUN_INPUTS_SHA256},
            "source": source_record, "hierarchy": inputs["hierarchy"], "primary_sha256": PRIMARY_SHA256,
            "origin_m_xz": source["metadata"]["origin_m_xz"],
            "actual_code_sha256": {name: inputs["code_sha256"][name] for name in EVIDENCE},
            "actual_code_evidence": EVIDENCE, "sizes": cases,
            "windowed_execution_requires": ["hourly native rain streaming with stable full-forcing identity",
                "tile halo state synchronization per SSP-RK2 stage", "unique global face owners and deterministic cross-window exchange",
                "native checkpoint/restart and complete resource monitor"],
            "cross_window_ledger_contract_fields": ["hour", "substep", "stage", "owner_window_id",
                "neighbor_window_id", "global_face_id", "first_global_cell_id", "second_global_cell_id",
                "forward_m3", "reverse_m3", "active_forward_s", "active_reverse_s",
                "first_cell_internal_net_m3", "second_cell_internal_net_m3", "boundary_outflow_m3",
                "state_before_sha256", "state_after_sha256"],
            "cross_window_invariants": ["each shared face has exactly one owner per stage",
                "same signed exchange debits/credits both adjacent cells", "global ledger includes all windows once",
                "halo copies are not independent hydraulic domains"],
            "source_or_rain_generated": False, "solver_advanced": False, "hydraulic_ready": False,
            "limitations": "Full-valid D4 upper geometry for expanded sizes; only 256 source exists. "
                           "Window geometry is a design plan, not a runnable or accepted dynamic solution."}
