"""Explicit threshold scan on frozen full 256-square TD topology and water."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_storage import load_basin_storage
from terrain_pipeline.td_surface_reaches import make_surface_reaches, save_surface_reaches, load_surface_reaches, _plain


def independent_audit(result, hierarchy, storage):
    arrays = hierarchy["arrays"]
    receiver = arrays["receiver"]
    usable = arrays["valid_mask"].ravel() & ~arrays["protected_mask"].ravel()
    area = np.zeros(receiver.size)
    spacing = hierarchy["metadata"]["spacing_m"]
    for source in np.flatnonzero(usable):
        cell = int(source)
        visited = set()
        while True:
            if cell in visited:
                raise ValueError("independent receiver cycle")
            visited.add(cell)
            area[cell] += spacing ** 2
            target = int(receiver[cell])
            if target < 0 or not usable[target]:
                break
            cell = target
    selected = set(map(int, np.flatnonzero(usable & (area >= result["threshold_area_m2"]))))
    edges = []
    for reach in result["reaches"]:
        for cell, actual in zip(reach["cell_ids"], reach["contributing_area_m2"]):
            if actual != area[cell]:
                raise ValueError("independent contribution area mismatch")
        for edge in reach["edges"]:
            donor, target = edge["donor_cell_id"], edge["target_cell_id"]
            if receiver[donor] != target or donor not in selected or target not in selected:
                raise ValueError("independent edge topology mismatch")
            edges.append(donor)
            face = edge["face_index"]
            flux = edge["stored_flux"]
            if flux["forward_m3"] != storage["arrays"]["face_forward_m3"][face] or flux["reverse_m3"] != storage["arrays"]["face_reverse_m3"][face]:
                raise ValueError("independent directional volume mismatch")
    expected = {cell for cell in selected if receiver[cell] >= 0 and usable[receiver[cell]]}
    if set(edges) != expected or len(edges) != len(expected):
        raise ValueError("independent edge uniqueness mismatch")
    return {"passed": True, "method": "trace each usable source contribution to terminal; compare every published edge to frozen receiver and directional face volume",
            "selected_cells": len(selected), "unique_edges": len(expected)}


def verify():
    base = ROOT / "verification/td-basin-generation"
    hierarchy_pin = {"path": str(base / "A-20261001T184113155960Z/hierarchy.npz"), "expected_sha256": "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422", "expected_identity": "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"}
    hydro_pin = {"path": str(base / "A-storage-v2-20261001T193000Z/ordinary.npz"), "expected_sha256": "8ec55ed5cf750f93f821e97a0abf5fd74b2fe870f20ce1785a70f84097382dd2", "expected_identity": "3c19fe7ab54b0373051fb25d59733130d3117a105b3d905a68f389687983a49b"}
    hierarchy = load_basin_hierarchy(hierarchy_pin["path"], expected_sha256=hierarchy_pin["expected_sha256"], expected_identity=hierarchy_pin["expected_identity"])
    storage = load_basin_storage(hydro_pin["path"], expected_sha256=hydro_pin["expected_sha256"], expected_identity=hydro_pin["expected_identity"])
    output = ROOT / "verification/td-surface-reaches" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    cases = []
    for threshold in (50000., 100000., 250000.):
        result = make_surface_reaches(hierarchy, threshold_area_m2=threshold, expected_hierarchy_identity=hierarchy_pin["expected_identity"], storage=storage, expected_storage_identity=hydro_pin["expected_identity"])
        path = output / ("area-" + str(int(threshold)) + ".json")
        save_surface_reaches(result, path)
        digest = file_sha256(path)
        load_surface_reaches(path, expected_sha256=digest, expected_identity=result["identity_sha256"], hierarchy=hierarchy, storage=storage)
        cases.append({"threshold_area_m2": threshold, "path": str(path), "expected_sha256": digest,
                      "expected_identity": result["identity_sha256"], "summary": _plain(result["summary"]),
                      "sample_reach_ids": [reach["reach_id"] for reach in result["reaches"][:5]],
                      "independent_audit": independent_audit(result, hierarchy, storage)})
    report = {"schema": "td-surface-reaches-threshold-scan-v1", "inputs": {"hierarchy": hierarchy_pin, "storage": hydro_pin},
              "cases": cases, "threshold_selection": "all caller-declared thresholds retained; no automatic selection",
              "flags": {"full_native_256": True, "readonly": True, "hydraulic_ready": False, "natural_outlet_verified": False, "water_generated": False},
              "limitations": "Static area candidates, not rain Q or observed channels. Whole-run edge volume/activity only; no edge series, width/depth or water mesh.",
              "implementation_sha256": {name: file_sha256(ROOT / name) for name in ("terrain_pipeline/td_surface_reaches.py", "tests/test_td_surface_reaches.py", "tools/verify_td_surface_reaches.py")}}
    publish_bytes(output / "report.json", json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode())
    index = {"schema": "td-surface-reaches-review-index-v1", "cases": cases,
             "consumer": {"polyline": "reaches[].xyz_m", "nodes": "nodes[]", "edge_flux": "reaches[].edges[].stored_flux",
                          "coordinates": "XYZ metres; X east/Z south; unchanged bed heights",
                          "water_mesh": None, "width_depth": None}, "flags": report["flags"]}
    publish_bytes(output / "index.json", json.dumps(index, indent=2, ensure_ascii=False, allow_nan=False).encode())
    publish_bytes(output / "pins.json", json.dumps({name: file_sha256(output / name) for name in ("report.json", "index.json")}, indent=2).encode())
    print(json.dumps({"output": str(output), "cases": cases}, ensure_ascii=False))


if __name__ == "__main__":
    verify()
