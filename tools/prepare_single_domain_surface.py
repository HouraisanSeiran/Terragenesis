"""Stream the fixed accepted native pages into an explicitly pinned surface archive."""

import argparse
from datetime import datetime, timezone
import gc
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.single_domain_surface_archive import (
    ACCEPTANCE_SHA256, LIMITATIONS, iter_single_domain_hours, load_accepted_single_domain_chain,
)
from terrain_pipeline.single_domain_surface_geometry import build_geometry, build_water_frame, save_geometry, save_water_frame


BUDGETS = dict(max_memory_bytes=1024 ** 3, max_output_bytes=2 * 1024 ** 3,
               max_wall_s=1800, max_artifact_bytes=256 * 1024 ** 2)
CODE_FILES = ("terrain_pipeline/single_domain_surface_geometry.py",
              "terrain_pipeline/single_domain_surface_archive.py", "tools/prepare_single_domain_surface.py")
FLAGS = dict(hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
THREAD_ENVIRONMENT = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS")


def _json(path, record):
    publish_bytes(path, (json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8"))
    return dict(path=str(path.resolve()), expected_sha256=file_sha256(path))


class ResourceMeter:
    def __init__(self):
        self.started = time.monotonic()
        self.peak_rss = 0
        self.peak_private = 0
        self.failure = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()

    def _sample(self):
        process = psutil.Process()
        while not self.stop.is_set():
            info = process.memory_info()
            self.peak_rss = max(self.peak_rss, int(getattr(info, "peak_wset", info.rss)))
            self.peak_private = max(self.peak_private, int(getattr(info, "peak_pagefile", getattr(info, "private", info.vms))))
            if max(self.peak_rss, self.peak_private) > BUDGETS["max_memory_bytes"]:
                self.failure = "memory budget exceeded"
            if time.monotonic() - self.started > BUDGETS["max_wall_s"]:
                self.failure = "wall-clock budget exceeded"
            self.stop.wait(.1)

    def check(self):
        if self.failure:
            raise RuntimeError(self.failure)

    def finish(self):
        self.stop.set()
        self.thread.join()
        self.check()
        return dict(peak_rss_bytes=self.peak_rss, peak_private_bytes=self.peak_private,
                    elapsed_s=time.monotonic() - self.started,
                    runtime=dict(python_executable=sys.executable,
                                 thread_environment={name: os.environ.get(name) for name in THREAD_ENVIRONMENT}))


def _record(path, result):
    if path.stat().st_size > BUDGETS["max_artifact_bytes"]:
        raise RuntimeError("artifact byte budget exceeded")
    return dict(path=str(path.resolve()), expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"])


def _obj(path, arrays, vertex_name, triangle_name):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".surface-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
            stream.write("# native cell support only; no continuous 3D hydraulic certification\n")
            for vertex in arrays[vertex_name]:
                stream.write("v " + " ".join(format(float(value), ".17g") for value in vertex) + "\n")
            for triangle in arrays[triangle_name]:
                stream.write("f " + " ".join(str(int(index) + 1) for index in triangle) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if Path(temporary).stat().st_size > BUDGETS["max_artifact_bytes"]:
            raise RuntimeError("OBJ byte budget exceeded")
        os.link(temporary, path)
    finally:
        os.unlink(temporary)
    return dict(path=str(path.resolve()), expected_sha256=file_sha256(path))


def _chain_audit(direction, hours):
    rain = math.fsum(item["rain_m3"] for item in hours)
    loss = math.fsum(item["loss_m3"] for item in hours)
    export = math.fsum(item["external_m3"] for item in hours)
    residual = math.fsum([hours[0]["initial_water_m3"], rain, -loss, -export, -hours[-1]["final_water_m3"]])
    allowed = 1e-6 + rain * 1e-10
    if abs(residual) > allowed:
        raise ValueError("whole-period water budget mismatch")
    return dict(direction=direction, hours=hours, rain_m3=rain, loss_m3=loss,
                engineering_export_m3=export, whole_period_residual_m3=residual, allowed_m3=allowed,
                checkpoint_chain_verified=True, cell_budgets_verified=True)


def prepare(output, acceptance_record):
    if any(os.environ.get(name) != "1" for name in THREAD_ENVIRONMENT):
        raise ValueError("surface preparation requires OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=NUMBA_NUM_THREADS=1 before starting Python")
    output = Path(output).resolve()
    permitted = (ROOT / "verification/single-domain-surface").resolve()
    if not output.is_relative_to(permitted) or output == permitted:
        raise ValueError("new run output must lie inside verification/single-domain-surface")
    output.mkdir(parents=True, exist_ok=False)
    meter = ResourceMeter()
    artifacts, samples, directions, audits, diagnostics = [], [], {}, {}, {}
    code_sha256 = {name: file_sha256(ROOT / name) for name in CODE_FILES}
    source_records = None
    try:
        for direction in ("eastward", "westward"):
            context = load_accepted_single_domain_chain(acceptance_record, direction)
            source_records = context["source_records"]
            geometry = build_geometry(context["hierarchy"],
                                      source_hierarchy_sha256=source_records["hierarchy"]["expected_sha256"])
            geometry_path = output / direction / "geometry.npz"
            save_geometry(geometry_path, geometry)
            geometry_pin = _record(geometry_path, geometry)
            artifacts.append(geometry_pin)
            if direction == "eastward":
                sample = _obj(output / "samples/native-bed.obj", geometry["arrays"],
                              "bed_vertices_xyz_m", "bed_triangles")
                artifacts.append(sample)
                samples.append(sample)
            frames, hours, frame_audits = [], [], []
            for item in iter_single_domain_hours(context):
                hour, page = item["hour"], item["storage"]
                hours.append(item["budget"])
                for state_index in ((0, 1) if hour == 0 else (1,)):
                    number = hour + state_index
                    frame = build_water_frame(geometry, page, source_page_sha256=item["storage_record"]["expected_sha256"],
                                              state_index=state_index)
                    path = output / direction / f"frame-{number:02d}.npz"
                    save_water_frame(path, frame)
                    pin = _record(path, frame)
                    artifacts.append(pin)
                    frames.append(dict(frame=number, time_s=frame["metadata"]["time_s"], state_index=state_index,
                                       source_page=item["storage_record"], water_frame=pin))
                    meta = frame["metadata"]
                    frame_audits.append({name: meta[name] for name in (
                        "time_s", "wet_cell_count", "represented_wet_cell_count", "omitted_wet_cell_count",
                        "raster_volume_m3", "triangulated_support_volume_m3", "volume_difference_m3",
                        "represented_area_m2", "raster_wet_area_m2", "max_wet_neighbor_surface_jump_m")})
                    if number == 24:
                        for suffix, vertices, triangles in (("water", "water_vertices_xyz_m", "water_triangles"),
                                                            ("support-sides", "support_side_vertices_xyz_m", "support_side_triangles")):
                            sample = _obj(output / f"samples/{direction}-hour24-{suffix}.obj", frame["arrays"], vertices, triangles)
                            artifacts.append(sample)
                            samples.append(sample)
                    del frame
                    meter.check()
                    size = sum(Path(record["path"]).stat().st_size for record in artifacts)
                    if size > BUDGETS["max_output_bytes"]:
                        raise RuntimeError("new output byte budget exceeded")
                print(f"{direction} saved hour {hour + 1:02d}/24", flush=True)
                del page, item
            directions[direction] = dict(geometry=geometry_pin, frames=frames)
            audits[direction] = _chain_audit(direction, hours)
            diagnostics[direction] = frame_audits
            del context, geometry
            gc.collect()
        for name, digest in code_sha256.items():
            if file_sha256(ROOT / name) != digest:
                raise ValueError("implementation changed during archive preparation")
        limitations = list(LIMITATIONS) + [
            "Independent flat native dual-cell water surfaces may jump at shared edges; no continuous fine channel surface.",
            "Wet support side walls are numerical perimeter geometry and do not certify natural banks or sealed union volumes.",
            "Actual saved bidirectional face volumes remain in pinned source pages; static receiver links do not determine actual flow.",
            "Formal frontend integration remains a separate delivery gate; this archive exposes a read-only adapter contract.",
        ]
        shared = dict(acceptance_record=acceptance_record, source_records=source_records, directions=directions,
                      code_sha256=code_sha256, limitations=limitations, **FLAGS)
        report = dict(schema="single-domain-surface-report-v1", **shared, direction_audits=audits,
                      frame_diagnostics=diagnostics, sample_records=samples, solver_advanced=False, frame_count=50,
                      native_bed_changed=False, validation_command="D:/anaconda/python.exe -B -m unittest tests.test_single_domain_surface_geometry tests.test_single_domain_surface_archive")
        report_pin = _json(output / "report.json", report)
        artifacts.append(report_pin)
        output_bytes = sum(Path(record["path"]).stat().st_size for record in artifacts)
        resource = dict(schema="single-domain-surface-resource-v1", complete=True, budgets=BUDGETS,
                        artifact_records=artifacts, output_bytes=output_bytes, **meter.finish())
        if output_bytes > BUDGETS["max_output_bytes"]:
            raise RuntimeError("new output byte budget exceeded")
        resource_pin = _json(output / "resource.json", resource)
        index = dict(schema="single-domain-surface-index-v1", **shared, report=report_pin, resource=resource_pin)
        index_pin = _json(output / "index.json", index)
        print(json.dumps(index_pin), flush=True)
        return index_pin
    except BaseException as error:
        meter.stop.set()
        meter.thread.join()
        _json(output / "failure.json", dict(complete=False, error=type(error).__name__, message=str(error),
                                           elapsed_s=time.monotonic() - meter.started, **FLAGS))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "verification/single-domain-surface" /
                        datetime.now(timezone.utc).strftime("native-same-bed-%Y%m%dT%H%M%S%fZ"))
    parser.add_argument("--acceptance", type=Path, default=ROOT /
                        "verification/td-weather-refinement/independent-final-20261002T232545211593Z/acceptance-index.json")
    parser.add_argument("--acceptance-sha256", default=ACCEPTANCE_SHA256)
    args = parser.parse_args()
    prepare(args.output, dict(path=str(args.acceptance.resolve()), expected_sha256=args.acceptance_sha256))


if __name__ == "__main__":
    main()
