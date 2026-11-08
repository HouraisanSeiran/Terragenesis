"""Cold-read frozen TD edge export and independently check face provenance."""

import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import load_basin_storage as load_basin_storage
from terrain_pipeline.td_surface_river_edges import build_td_surface_river_edges, write_report


def verify(destination):
    hierarchy_path = ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz"
    storage_path = ROOT / "verification/td-basin-generation/A-storage-v2-20261001T193000Z/ordinary.npz"
    pins = {
        "hierarchy": {"path": str(hierarchy_path), "expected_sha256": "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
                      "expected_identity": "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"},
        "ordinary": {"path": str(storage_path), "expected_sha256": "8ec55ed5cf750f93f821e97a0abf5fd74b2fe870f20ce1785a70f84097382dd2",
                     "expected_identity": "3c19fe7ab54b0373051fb25d59733130d3117a105b3d905a68f389687983a49b"}}
    with patch('terrain_pipeline.basin_topology.build_basin_hierarchy', side_effect=AssertionError("cold build")), patch(
            'terrain_pipeline.basin_storage.simulate_threshold_storage', side_effect=AssertionError("cold solve")):
        hierarchy = load_basin_hierarchy(**pins["hierarchy"])
        storage = load_basin_storage(**pins["ordinary"])
        result = build_td_surface_river_edges(hierarchy, storage=storage)
    records = result["records"]
    internal = [record for record in records if record["kind"] == "d4_internal_face"]
    for record, face in zip(internal, hierarchy["arrays"]["face_cells"]):
        assert record["cell_ids"] == face.tolist()
        first, second = record["cell_ids"]
        columns = hierarchy["arrays"]["height_m"].shape[1]
        assert abs(first // columns - second // columns) + abs(first % columns - second % columns) == 1
        index = record["face_index"]
        assert record["net_volume_m3"] == storage["arrays"]["face_forward_m3"][index] - storage["arrays"]["face_reverse_m3"][index]
        assert record["gross_volume_m3"] == storage["arrays"]["face_forward_m3"][index] + storage["arrays"]["face_reverse_m3"][index]
    assert len(internal) == len(hierarchy["arrays"]["face_cells"])
    assert len({record["edge_id"] for record in records}) == len(records)
    assert not result["diagnostic"]["hydraulic_ready"]
    for role, pin in pins.items():
        assert file_sha256(pin["path"]) == pin["expected_sha256"]
    destination = Path(destination)
    sha = write_report(result, destination / "edges.json")
    report = {"schema": "td-surface-river-edge-audit-v1", "pins": pins, "edges_sha256": sha,
              "internal_faces": len(internal), "receiver_edges": sum(record["receiver_edge"] for record in internal),
              "engineered_exterior_faces": len(records) - len(internal), "independent_face_checks_passed": True,
              "inputs_unchanged": True, "solver_advanced": False, "jit_called": False,
              "hydraulic_ready": False, "publishable": False, "transient_converged": False,
              "code_sha256": {name: file_sha256(ROOT / name) for name in (
                  "terrain_pipeline/td_surface_river_edges.py", "tools/verify_td_surface_river_edges.py")},
              "limitations": "Computational D4 faces and static receiver contribution edges; no observed river channel, natural outlet, or per-exterior-side flux."}
    write_report(report, destination / "independent-report.json")
    print(json.dumps({"output": str(destination), "edges_sha256": sha, "internal_faces": len(internal)}))


if __name__ == "__main__":
    verify(ROOT / "verification/td-basin-generation" / ("A-surface-edges-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")))
