"""Check relocated consumer payloads and HTTP with original-source access denied."""

import argparse
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(name, "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psutil
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.single_domain_surface_consumer import BUDGETS, load_consumer_manifest, readonly_server


def adaptive_frame_validator(context):
    from terrain_pipeline.surface_adaptive_water import load_consumer_adaptive_frame

    def validate():
        count, maximum_error = 0, 0.
        for name, scenario in context["manifest"]["scenarios"].items():
            for entry in scenario["frames"]:
                saved = load_consumer_adaptive_frame(context, scenario=name, frame_index=entry["frame"])
                frame = saved["frame"]
                maximum_error = max(maximum_error, frame["metadata"]["max_cell_volume_difference_m3"])
                count += 1
        return dict(bound_frames_verified=count, max_cell_volume_difference_m3=maximum_error,
                    original_snapshot_and_leaf_geometry_verified=True)
    return validate


def verify(manifest_path, manifest_sha256, output):
    started = time.monotonic()
    original = load_consumer_manifest(manifest_path, expected_sha256=manifest_sha256)
    validate_adaptive = None
    if original["manifest"]["backend"] == "adaptive-saved-canonical-fan":
        # Import pure validators before enforcing package-only filesystem reads.
        validate_adaptive = adaptive_frame_validator(original)
    output = Path(output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    relocated = output/"relocated"
    relocated.mkdir()
    shutil.copy2(original["manifest_path"], relocated/"manifest.json")
    for name, source in original["allowlist"].items():
        target = relocated/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    real_open, real_io_open = builtins.open, io.open
    reads = set()

    def restricted(opener):
        def open_saved(file, *args, **kwargs):
            if not isinstance(file, int):
                path = Path(os.fspath(file)).resolve()
                if not path.is_relative_to(relocated):
                    raise PermissionError("Original source and outside-package file reads forbidden")
                reads.add(str(path))
            return opener(file, *args, **kwargs)
        return open_saved

    http = {}
    adaptive = None
    with patch("builtins.open", restricted(real_open)), patch("io.open", restricted(real_io_open)):
        context = load_consumer_manifest(relocated/"manifest.json", expected_sha256=manifest_sha256)
        if validate_adaptive is not None:
            adaptive = adaptive_frame_validator(context)()
        server = readonly_server(context, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = "http://127.0.0.1:"+str(server.server_address[1])
        try:
            item = context["manifest"]["artifacts"][0]
            requests = [("manifest.json", manifest_sha256, context["manifest_path"].stat().st_size),
                        ("payload/"+item["path"], item["sha256"], item["bytes"])]
            water_frames = [item for item in context["manifest"]["artifacts"] if item.get("role")=="saved-water-frame"]
            if water_frames:
                item = water_frames[-1]
                requests.append(("payload/"+item["path"], item["sha256"], item["bytes"]))
            for name, digest, size in requests:
                with urlopen(base+"/"+name, timeout=30) as response:
                    checksum, observed_bytes = hashlib.sha256(), 0
                    while True:
                        chunk = response.read(1048576)
                        if not chunk:
                            break
                        checksum.update(chunk)
                        observed_bytes += len(chunk)
                    if (checksum.hexdigest() != digest or observed_bytes != size
                            or response.headers["ETag"] != '"'+digest+'"'
                            or int(response.headers["Content-Length"]) != size):
                        raise ValueError("Relocated HTTP payload/SHA/ETag/length mismatch")
                    http[name] = dict(status=response.status, sha256=digest, bytes=observed_bytes)
            for route in ("/payload/../manifest.json", "/payload/%2e%2e/manifest.json",
                          "/payload/C:/Windows/win.ini", "/payload/unknown.npz"):
                try:
                    with urlopen(base+route, timeout=30):
                        raise ValueError("HTTP route outside allowlist accepted")
                except HTTPError as error:
                    if error.code != 404:
                        raise
                    http[route] = dict(status=404)
            try:
                with urlopen(Request(base+"/manifest.json", data=b"forbidden", method="POST"), timeout=30):
                    raise ValueError("HTTP write accepted")
            except HTTPError as error:
                if error.code != 501:
                    raise
                http["POST /manifest.json"] = dict(status=501)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
            if worker.is_alive():
                raise RuntimeError("consumer HTTP worker did not exit")
    if any(name == "numba" or name.startswith("numba.")
            or name == "terrain_pipeline.single_domain_fine_hydraulics"
            or name in ("terrain_pipeline.surface_adaptive_execution", "terrain_pipeline.surface_adaptive_hydraulics",
                        "terrain_pipeline.surface_adaptive_refinement")
            or name.startswith("terrain_pipeline.single_domain_shallow_water") for name in sys.modules):
        raise RuntimeError("consumer portability check imported execution modules")
    memory = psutil.Process().memory_info()
    observed = dict(elapsed_s=time.monotonic()-started,
        peak_rss_bytes=int(getattr(memory, "peak_wset", memory.rss)),
        peak_private_bytes=int(getattr(memory, "peak_pagefile", memory.vms)))
    if max(observed["peak_rss_bytes"], observed["peak_private_bytes"]) > BUDGETS["max_memory_bytes"] or observed["elapsed_s"] > BUDGETS["max_wall_s"]:
        raise RuntimeError("consumer portability resource budget exceeded")
    result = dict(schema="single-domain-consumer-portability-audit-v1",
        source_manifest=dict(path=str(Path(manifest_path).resolve()), expected_sha256=manifest_sha256),
        relocated_manifest=dict(path=str(relocated/"manifest.json"), expected_sha256=manifest_sha256),
        payload_count=len(context["allowlist"]), payload_bytes=context["manifest"]["output_bytes"],
        authenticated_relative_payloads=True, original_source_access_forbidden=True,
        package_only_file_reads=len(reads), execution_modules_absent=True, solver_advanced=False,
        http=http, http_server_stopped=True, resource=observed,
        hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    if adaptive is not None:
        result["adaptive_water_frames"] = adaptive
    path = output/"report.json"
    publish_bytes(path, (json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+"\n").encode("utf-8"))
    print(dict(path=str(path), expected_sha256=file_sha256(path)), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    verify(args.manifest, args.manifest_sha256, args.output)
