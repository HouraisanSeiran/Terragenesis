"""Cold-read, determinism, and pin checks for TD natural river candidates."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_natural_channel_geometry import (
    load_natural_channel_geometry, load_natural_channel_window,
)
from terrain_pipeline.td_natural_river_network import load_natural_river_network
from tools.audit_td_natural_river_network import audit_saved_network


HIERARCHY = {
    "path": "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz",
    "expected_sha256": "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
    "expected_identity": "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998",
}


def pin(path, result):
    return {"path": str(path), "expected_sha256": file_sha256(path),
            "expected_identity": result["identity_sha256"]}


def main(first, second):
    first, second = Path(first), Path(second)
    records = {}
    for name, root in (("first", first), ("second", second)):
        index = json.loads((root / "index.json").read_text(encoding="utf-8"))
        artifacts = index["artifacts"]
        network = load_natural_river_network(root / "network.npz",
                                             expected_sha256=artifacts["network"]["sha256"],
                                             expected_identity=artifacts["network"]["identity_sha256"])
        geometry = load_natural_channel_geometry(root / "geometry.npz",
                                                 expected_sha256=artifacts["geometry"]["sha256"],
                                                 expected_identity=artifacts["geometry"]["identity_sha256"])
        window = load_natural_channel_window(root / "window.npz",
                                             expected_sha256=artifacts["window"]["sha256"],
                                             expected_identity=artifacts["window"]["identity_sha256"])
        audit = audit_saved_network(network_record={"path": str(root / "network.npz"), "expected_sha256": artifacts["network"]["sha256"], "expected_identity": artifacts["network"]["identity_sha256"]},
                                    hierarchy_record={**HIERARCHY, "path": str(Path(HIERARCHY["path"]))},
                                    geometry_record={"path": str(root / "geometry.npz"), "expected_sha256": artifacts["geometry"]["sha256"], "expected_identity": artifacts["geometry"]["identity_sha256"]},
                                    window_record={"path": str(root / "window.npz"), "expected_sha256": artifacts["window"]["sha256"], "expected_identity": artifacts["window"]["identity_sha256"]})
        records[name] = {"network": network, "geometry": geometry, "window": window, "audit": audit}

    compare = {}
    for artifact in ("network", "geometry", "window"):
        a, b = records["first"][artifact], records["second"][artifact]
        compare[artifact] = {
            "file_sha256_equal": file_sha256(first / (artifact + ".npz")) == file_sha256(second / (artifact + ".npz")),
            "identity_equal": a["identity_sha256"] == b["identity_sha256"],
            "metadata_equal": a["metadata"] == b["metadata"],
            "arrays_equal": sorted(a["arrays"]) == sorted(b["arrays"]) and all(np.array_equal(a["arrays"][k], b["arrays"][k]) for k in a["arrays"]),
        }
    result = {"schema": "td-natural-river-deep-test-v1", "input_pins": HIERARCHY,
              "cold_read_audit": {name: records[name]["audit"] for name in records},
              "determinism": compare,
              "all_cold_read_checks_passed": all(x["audit"]["checks"] and all(x["audit"]["checks"].values()) for x in records.values()),
              "all_loaded_artifacts_deterministic": all(all(x.values()) for x in compare.values())}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("first")
    parser.add_argument("second")
    args = parser.parse_args()
    main(args.first, args.second)
