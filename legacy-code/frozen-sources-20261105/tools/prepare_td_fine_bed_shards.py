"""Retry only byte-budget-refused triangles in the fixed task09 fine package."""

import argparse
import json
from pathlib import Path
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_fine_bed_shards import build_fine_bed_shards, save_fine_bed_shards

BASE = ROOT / "verification/natural-river-network/fine-bed-raster-lake-entry-20261005-01"
INDEX_SHA = "113f3990de828f25f4b766afffa58c948a5d5aea12b9e2de05d383486795f759"
BASE_SHA = "ad414151aa9b2cede4f47b95fc5011f81ebc6ec1666f2ef01d333828e9ad295c"
AUDIT_SHA = "787ed835e848bc7b23158d845db2160495ae0ea01dfccf7813773d046d95b6ed"
MAX_BYTES = 64 * 1024**2
MAX_RSS_BYTES = 1024**3


def _read(path, expected_sha):
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT) or path.stat().st_size > MAX_BYTES or file_sha256(path) != expected_sha:
        raise ValueError("fixed input file location/SHA/budget mismatch")
    return json.loads(path.read_text(encoding="utf-8"))


def _pin(path, record=None):
    pin = {"path": str(path.resolve()), "sha256": file_sha256(path), "bytes": path.stat().st_size}
    if record is not None:
        pin["identity_sha256"] = record["identity_sha256"]
    return pin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cells", type=int, default=2_000_000)
    parser.add_argument("--max-shard-bytes", type=int, default=MAX_BYTES)
    parser.add_argument("--max-transactions-per-shard", type=int, default=4096)
    args = parser.parse_args()
    output = args.output.resolve()
    parent = (ROOT / "verification/natural-river-network").resolve()
    if not output.is_relative_to(parent) or output == parent or output.exists():
        raise ValueError("new verification output directory required")
    started, process, peak_rss = time.perf_counter(), psutil.Process(), 0

    def resource_check():
        nonlocal peak_rss
        memory = process.memory_info()
        peak_rss = max(peak_rss, memory.rss, getattr(memory, "peak_wset", 0))
        if peak_rss > MAX_RSS_BYTES:
            raise MemoryError("hard 1GiB process peak RSS limit exceeded")

    resource_check()
    index = _read(BASE / "index.json", INDEX_SHA)
    audit = _read(BASE / "independent-audit.json", AUDIT_SHA)
    if index["raster"]["sha256"] != BASE_SHA or audit["status"] != "passed" or audit["raster_sha256"] != BASE_SHA:
        raise ValueError("fixed shard0 independent audit/pin mismatch")
    base_path = Path(index["raster"]["path"])
    base = _read(base_path, BASE_SHA)
    if base["identity_sha256"] != index["raster"]["identity_sha256"]:
        raise ValueError("fixed shard0 identity mismatch")
    pins = {"base_index": _pin(BASE / "index.json"), "base_raster": _pin(base_path, base),
            "base_independent_audit": _pin(BASE / "independent-audit.json"), **index["inputs"]}
    for name, pin in index["inputs"].items():
        path = Path(pin["path"]).resolve(strict=True)
        if not path.is_relative_to(ROOT) or file_sha256(path) != pin["sha256"]:
            raise ValueError("immutable source dependency changed: " + name)
    hierarchy_pin = index["inputs"]["hierarchy"]
    hierarchy = load_basin_hierarchy(Path(hierarchy_pin["path"]),
        expected_sha256=hierarchy_pin["sha256"], expected_identity=hierarchy_pin["identity_sha256"])
    resource_check()
    package = build_fine_bed_shards(base, hierarchy, input_pins=pins,
        max_cells=args.max_cells, max_shard_bytes=args.max_shard_bytes,
        max_transactions_per_shard=args.max_transactions_per_shard, resource_check=resource_check)
    save_fine_bed_shards(package, output, resource_check=resource_check)
    raw_pin = _pin(output / "raw.json", package["raw"])
    manifest_pin = _pin(output / "manifest.json", package["manifest"])
    shard_pins = [_pin(output / "shards" / (shard["shard_id"] + ".json"), shard) for shard in package["shards"]]
    resource_check()
    flags = {name: False for name in ("hydraulic_ready", "hydraulic_solved", "natural_outlet_certified",
                                      "publish_ready", "bed_changed", "cross_shard_hydraulics_verified")}
    review = {"schema": "td-fine-bed-shards-review-v1", "summary": package["manifest"]["summary"],
              "coverage": package["raw"]["summary"],
              "material_ledger_merged": package["manifest"]["material_ledger_merged"],
              "original_fill_refusals_not_repaired": True,
              "mesh_expression_changed": False, **flags}
    publish_bytes(output / "review.json", json.dumps(review, sort_keys=True, allow_nan=False).encode())
    result = {"schema": "td-fine-bed-shards-preparation-v1", "status": "candidate_only",
              "inputs": pins, "shard0": pins["base_raster"], "raw": raw_pin,
              "manifest": manifest_pin, "shards": shard_pins, "review": _pin(output / "review.json"),
              "summary": package["manifest"]["summary"], "coverage": package["raw"]["summary"],
              "material_ledger_merged": package["manifest"]["material_ledger_merged"],
              "resource": {"peak_rss_bytes": peak_rss, "max_rss_bytes": MAX_RSS_BYTES,
                           "elapsed_s": time.perf_counter() - started, "water_solves": 0,
                           "forest_rebuilds": 0, "base_rasterizations": 0},
              "code_sha256": {name: file_sha256(ROOT / name) for name in (
                  "terrain_pipeline/td_fine_bed_shards.py", "tools/prepare_td_fine_bed_shards.py",
                  "terrain_pipeline/td_fine_bed_raster.py", "terrain_pipeline/mountain_source_adapter.py",
                  "terrain_pipeline/td_basin_hierarchy.py")}, **flags}
    publish_bytes(output / "index.json", json.dumps(result, sort_keys=True, allow_nan=False, indent=2).encode())
    print(json.dumps({"summary": result["summary"], "coverage": result["coverage"]}, sort_keys=True))


if __name__ == "__main__":
    main()
