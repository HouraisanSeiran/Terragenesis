"""Pure IO catchment saved-frame export; versions remain separate cases."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_catchment_dynamic_review import export_catchment_dynamic_review, load_catchment_dynamic_review, _load_inputs
from tools.verify_td_basin_spill_network import peak_process_memory


def audit(directory, records):
    hierarchy, storage = _load_inputs(records)
    labels = hierarchy["arrays"]["contribution_owner"].ravel()
    valid = hierarchy["arrays"]["valid_mask"].ravel()
    area = hierarchy["metadata"]["spacing_m"] ** 2
    max_error = 0.
    for page_path in sorted(directory.glob("frame-*.json")):
        page = json.loads(page_path.read_bytes())
        frame = page["frame_index"]
        for record in page["leaves"]:
            mask = valid & (labels == record["leaf_id"])
            for field, native, scale in (("surface_volume_m3", "depth_m", area), ("soil_volume_m3", "soil_mm", area / 1000),
                                         ("fast_volume_m3", "fast_mm", area / 1000), ("slow_volume_m3", "slow_mm", area / 1000)):
                expected = float(storage["arrays"][native][frame, mask].sum() * scale)
                max_error = max(max_error, abs(record[field] - expected))
                if not np.isclose(record[field], expected, rtol=1e-12, atol=1e-6):
                    raise ValueError("independent leaf inventory sum mismatch")
    return {"passed": True, "method": "independent per-leaf boolean mask saved-state sums, no bincount aggregation reused", "max_inventory_error_m3": max_error}


def verify():
    base = ROOT / "verification/td-basin-generation"
    hierarchy = {"path": str(base / "A-20261001T184113155960Z/hierarchy.npz"),
                 "expected_sha256": "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
                 "expected_identity": "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"}
    storage_cases = {
        "ordinary-v6-2.5s-diagnostic": {"path": str(base / "A-storage-v6-full-20261002T101625224506Z/ordinary-2.5s/storage.npz"),
            "expected_sha256": "337cbdc6ee5a5a87cc2b1482e7ea739c177e897fd1f991340cc25fcefc2e71ea",
            "expected_identity": "0ae051840ddc0a320d6e635d7981ba546c12cbae4183e8066f72e2dedd0e7f8d"},
        "strong-v6-2.5s": {"path": str(base / "A-storage-v6-full-20261002T101625224506Z/strong-2.5s/storage.npz"),
            "expected_sha256": "92d7f4140a23b0f01128a81a2c6cbe26ad0568ba2762c6be115a716334fac7da",
            "expected_identity": "c530660bac6176c041154c93e575329462b15736d0729c07ebbf80f76a005d06"},
        "ordinary-historical-v2": {"path": str(base / "A-storage-v2-20261001T193000Z/ordinary.npz"),
            "expected_sha256": "8ec55ed5cf750f93f821e97a0abf5fd74b2fe870f20ce1785a70f84097382dd2",
            "expected_identity": "3c19fe7ab54b0373051fb25d59733130d3117a105b3d905a68f389687983a49b"}}
    output = ROOT / "verification/td-catchment-dynamic-review" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    cases = []
    for name, storage in storage_cases.items():
        records = {"hierarchy": hierarchy, "storage": storage}
        directory = output / name
        result = export_catchment_dynamic_review(records, directory)
        index_path = directory / "index.json"
        load_catchment_dynamic_review(index_path, expected_sha256=file_sha256(index_path), expected_identity=result["identity_sha256"], records=records)
        cases.append({"case": name, "path": str(index_path), "expected_sha256": file_sha256(index_path), "expected_identity": result["identity_sha256"],
                      "status": "budget_passed_saved_state_only" if result["budget_acceptance"]["audit_budget_passed"] else "budget_failed_diagnostic",
                      "storage_version": dict(result["storage_version"]), "budget_acceptance": dict(result["budget_acceptance"]), "audit": audit(directory, records)})
    memory = peak_process_memory()
    report = {"schema": "td-dynamic-catchment-verification-v1", "cases": cases,
              "scope": "v6 ordinary/strong same-profile saved-state comparison with explicit budget_failed diagnostics; historical ordinary v2 separate, never direct two-rain algorithm comparison; v6 refinement below 1mm not accepted",
              "resources": {"peak_process_memory": memory, "within_1GiB": max(memory.values()) <= 1024 ** 3},
              "implementation_sha256": {name: file_sha256(ROOT / name) for name in ("terrain_pipeline/td_catchment_dynamic_review.py", "tests/test_td_catchment_dynamic_review.py", "tools/verify_td_catchment_dynamic_review.py")}}
    if not report["resources"]["within_1GiB"]:
        publish_bytes(output / "failed-resource.json", json.dumps(report, indent=2).encode())
        raise RuntimeError("resource budget exceeded; no final index")
    publish_bytes(output / "report.json", json.dumps(report, indent=2).encode())
    payload = json.dumps({"schema": "td-dynamic-catchment-review-navigation-v1", "cases": cases, "scope": report["scope"]}, indent=2).encode()
    import hashlib
    publish_bytes(output / "pins.json", json.dumps({"index.json": hashlib.sha256(payload).hexdigest(), "report.json": file_sha256(output / "report.json")}).encode())
    publish_bytes(output / "index.json", payload)
    print(json.dumps({"output": str(output), "cases": cases, "resources": report["resources"]}))


if __name__ == "__main__":
    verify()
