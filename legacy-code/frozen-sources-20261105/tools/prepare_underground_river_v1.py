"""Append an atomic preview package from fixed geometry03 and its passed audit."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".scratch/hybrid-river-network/python-deps"))

from terrain_pipeline.hybrid_cave_geometry import MAX_BYTES, guard, seal
from terrain_pipeline.hybrid_river_graph import FilePin
from terrain_pipeline.underground_river_v1 import CAPABILITIES, Parameters, build_preview
from tools.prepare_hybrid_cave_geometry import checked_identity, file_sha, load_inputs, read, save

SOURCE = ROOT / "verification/natural-river-network/hybrid-cave-geometry-20261006-03"
INDEX_SHA = "d7b971d28f07ff457776e0ce65ff8d583a4d1f70e50cbb3bdaad8e4909679fd6"
AUDIT_SHA = "703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364"
DEFAULT_OUTPUT = ROOT / "verification/natural-river-network/underground-river-v1-20261006-01"
CODE_FILES = ("terrain_pipeline/underground_river_v1.py", "tools/prepare_underground_river_v1.py",
              "tests/test_underground_river_v1.py")


def load_source():
    pins = {"geometry03_index": {"path": str(SOURCE / "index.json"), "sha256": INDEX_SHA},
            "geometry03_audit": {"path": str(SOURCE / "independent-audit-v2.json"), "sha256": AUDIT_SHA}}
    index, audit = read(pins["geometry03_index"]), read(pins["geometry03_audit"])
    checked_identity(index)
    checked_identity(audit)
    if audit["status"] != "passed" or audit.get("errors") or audit["geometry_sha256"] != index["geometry"]["sha256"]:
        raise ValueError("fixed geometry03 passed audit linkage required")
    for name, expected in index["code_sha256"].items():
        if file_sha(ROOT / name) != expected:
            raise ValueError("frozen geometry03 code changed:" + name)
    geometry = read(index["geometry"])
    checked_identity(geometry)
    for name, expected in geometry["readonly_dependency_code_sha256"].items():
        if file_sha(ROOT / name) != expected:
            raise ValueError("frozen source dependency changed:" + name)
    for key in ("rock_before", "vdm"):
        pins[key] = index["artifacts"][key]
    pins["geometry03"] = index["geometry"]
    pins["graph"] = index["graph"]
    rock, vdm = read(pins["rock_before"]), read(pins["vdm"])
    checked_identity(rock)
    checked_identity(vdm)
    _, sampler = load_inputs(FilePin(**index["graph"]))
    return rock, vdm, sampler, pins


def prepare(output, parameters=Parameters()):
    output = Path(output).resolve()
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists() or not output.is_relative_to(ROOT / "verification/natural-river-network"):
        raise ValueError("new natural-river-network output directory required; never overwrite")
    started = time.perf_counter()
    parents = {}
    preview = None
    try:
        rock, vdm, sampler, parents = load_source()
        preview = build_preview(rock, vdm, sampler, parents, parameters, started=started)
        if time.perf_counter() - started > 60.:
            raise ValueError("60s generation budget exceeded")
        index = {"schema": "td-underground-river-preparation-v1", "status": "geometry_checked", "rejection_reasons": []}
    except (ValueError, MemoryError, OSError) as error:
        preview = None
        index = {"schema": "td-underground-river-preparation-v1", "status": "refused", "rejection_reasons": [str(error)]}
    index.update(parameters=asdict(parameters), parents=parents, capabilities=dict(CAPABILITIES),
                 code_sha256={name: file_sha(ROOT / name) for name in CODE_FILES},
                 resource={"elapsed_s": time.perf_counter() - started, "max_rss_bytes": 1024**3,
                           "max_payload_bytes": MAX_BYTES, "max_elapsed_s": 60.,
                           "actual_peak_rss_bytes": guard(), "solver_calls": 0})
    partial.mkdir(parents=True)
    try:
        if preview is not None:
            pin = save(partial / "preview.json", preview)
            pin["path"] = str(output / "preview.json")
            index["preview"] = pin
            index["metrics"] = preview["metrics"]
        seal(index)
        save(partial / "index.json", index)
        if sum(path.stat().st_size for path in partial.iterdir()) > MAX_BYTES:
            raise ValueError("total payload exceeds 64MiB")
        if preview is not None and time.perf_counter() - started > 60.:
            raise ValueError("60s publication budget exceeded")
        partial.rename(output)
    except BaseException:
        shutil.rmtree(partial)
        raise
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    for name, default in asdict(Parameters()).items():
        parser.add_argument("--" + name.replace("_", "-"), type=int if name == "seed" else float, default=default)
    args = parser.parse_args()
    try:
        parameters = Parameters(**{name: getattr(args, name) for name in asdict(Parameters())})
        index = prepare(args.output, parameters)
        summary = {"status": index["status"], "metrics": index.get("metrics"),
                   "rejection_reasons": index["rejection_reasons"], "output": str(args.output.resolve())}
    except (ValueError, MemoryError, OSError) as error:
        summary = {"status": "refused", "metrics": None, "rejection_reasons": [str(error)]}
    print(json.dumps(summary, allow_nan=False))
    return 0 if summary["status"] == "geometry_checked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
