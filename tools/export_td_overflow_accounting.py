"""Cold-read pinned original-bed events and export new accounting without solving."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_storage import add_saved_overflow_accounting as add_saved_overflow_accounting
from terrain_pipeline.basin_storage import load_overflow_event as load_overflow_event
from terrain_pipeline.basin_storage import load_overflow_topology as load_overflow_topology
from terrain_pipeline.basin_storage import save_overflow_event as save_overflow_event
from terrain_pipeline.basin_storage import save_overflow_topology as save_overflow_topology
from tools.audit_td_original_bed_overflow import audit_saved_arrays


def export(saved_index, *, expected_index_sha256, output):
    saved_index, output = Path(saved_index).resolve(strict=True), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    if file_sha256(saved_index) != expected_index_sha256:
        raise ValueError("saved index external hash mismatch")
    index = json.loads(saved_index.read_text(encoding="utf-8"))
    for pin in index["input_pins"].values():
        if file_sha256(pin["path"]) != pin["sha256"]:
            raise ValueError("source input pin mismatch")
    topology_pin = index["topology"]
    topology = load_overflow_topology(saved_index.parent / Path(topology_pin["path"]).name,
                                      expected_sha256=topology_pin["sha256"],
                                      expected_identity=topology_pin["identity_sha256"])
    topology_path = output / "original-bed-overflow-topology.json"
    save_overflow_topology(topology, topology_path)
    cases = []
    for case in index["cases"]:
        event_path = saved_index.parent / Path(case["event"]["path"]).name
        event = load_overflow_event(event_path, expected_sha256=case["event"]["sha256"],
                                    expected_identity=case["event_identity_sha256"], topology=topology)
        accounted = add_saved_overflow_accounting(event, topology)
        output_path = output / event_path.name
        save_overflow_event(accounted, output_path)
        cases.append(dict(audit_saved_arrays(topology, accounted), name=case["name"],
                          event={"path": str(output_path), "sha256": file_sha256(output_path), "bytes": output_path.stat().st_size},
                          event_identity_sha256=accounted["identity_sha256"],
                          parent_event={"path": str(event_path), "sha256": case["event"]["sha256"], "identity_sha256": event["identity_sha256"]},
                          hydraulic_ready=False, natural_outlet_verified=False, publishable=False))
    if file_sha256(saved_index) != expected_index_sha256:
        raise ValueError("saved index changed during accounting export")
    result = {"schema": "td-original-bed-overflow-diagnostic-v2", "status": "diagnostic_only",
              "parent_index": {"path": str(saved_index), "sha256": expected_index_sha256},
              "input_pins": index["input_pins"], "summary": index["summary"], "cases": cases,
              "topology": {"path": str(topology_path), "sha256": file_sha256(topology_path),
                           "identity_sha256": topology["identity_sha256"]},
              "code_sha256": {"exporter": file_sha256(Path(__file__)),
                              "accounting": file_sha256(ROOT / 'terrain_pipeline/basin_storage.py')},
              "cold_read": True, "solver_advanced": False, "event_model_advanced": False,
              "semantics": "original stages, inventories, rain and directional exchanges copied unchanged; v2 adds derived accounting only",
              "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    publish_bytes(output / "index.json", json.dumps(result, ensure_ascii=False, sort_keys=True,
                  allow_nan=False, indent=2).encode("utf-8"))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--saved-index", type=Path, required=True)
    parser.add_argument("--expected-index-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = export(args.saved_index, expected_index_sha256=args.expected_index_sha256, output=args.output)
    print(json.dumps({"output": str(args.output), "cases": result["cases"], "solver_advanced": False}, ensure_ascii=False))
