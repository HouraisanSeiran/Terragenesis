"""Prepare pinned land-side lake-entry tapers without modifying parents."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.lake import build_lake_entry_tapers as build_lake_entry_tapers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    index_path = (args.geometry / "index.json").resolve(strict=True)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    parents = {}
    records = {}
    for name in ("paths", "sections"):
        pin = index[name]
        path = (args.geometry / pin["path"]).resolve(strict=True)
        if not path.is_relative_to(ROOT) or file_sha256(path) != pin["sha256"]:
            raise ValueError("parent file pin mismatch")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["identity_sha256"] != pin["identity_sha256"]:
            raise ValueError("parent identity mismatch")
        records[name] = record
        parents[name] = {"path": str(path), "sha256": pin["sha256"], "identity_sha256": record["identity_sha256"]}
    hierarchy_pin = index["inputs"]["hierarchy"]
    hierarchy_path = Path(hierarchy_pin["path"]).resolve(strict=True)
    if not hierarchy_path.is_relative_to(ROOT):
        raise ValueError("hierarchy outside workspace")
    hierarchy = load_basin_hierarchy(hierarchy_path, expected_sha256=hierarchy_pin["sha256"],
                                     expected_identity=hierarchy_pin["identity_sha256"])
    result = build_lake_entry_tapers(records["paths"], records["sections"], hierarchy)
    parents["hierarchy"] = hierarchy_pin
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("use a new immutable output directory")
    payload = json.dumps(result, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > 32 * 1024**2:
        raise MemoryError("entry payload exceeds 32MiB")
    publish_bytes(output / "entries.json", payload)
    manifest = {"schema": "td-lake-entry-taper-preparation-v1", "status": "diagnostic_candidates",
                "parent_index": {"path": str(index_path), "sha256": file_sha256(index_path)},
                "inputs": parents, "entries": {"path": "entries.json", "sha256": file_sha256(output / "entries.json"),
                                               "identity_sha256": result["identity_sha256"]},
                "code_sha256": {name: file_sha256(ROOT / name) for name in
                                ('terrain_pipeline/lake.py', "tools/prepare_td_lake_entry_tapers.py")},
                "summary": result["summary"], "solver_advanced": False, "publishable": False}
    publish_bytes(output / "index.json", json.dumps(manifest, allow_nan=False, separators=(",", ":")).encode("utf-8"))
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
