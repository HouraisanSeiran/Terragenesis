"""Independent threshold connectivity/capacity checks on a rebuilt derived bed."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_basin_generation import audit_hierarchy
from tools.audit_td_candidate_coupling import read_record


def audit(index_path, expected_sha256, parent_record):
    index_path = Path(index_path).resolve(strict=True)
    if (file_sha256(index_path) != expected_sha256 or
            file_sha256(parent_record["path"]) != parent_record["expected_sha256"]):
        raise ValueError("external topology/parent manifest pin mismatch")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    parent = json.loads(Path(parent_record["path"]).read_text(encoding="utf-8"))
    candidate_id = index["candidate_id"]
    if (index["schema"] != "td-accepted-candidate-topology-review-v1" or
            index["parent_manifest"] != parent_record or parent["identity_sha256"] != parent_record["expected_identity"] or
            parent["stage"] != "geometry_only" or candidate_id not in ("valley_incision", "source_deposition") or
            index["source"] != parent["candidates"][candidate_id]["source"] or
            index["hydrology_solved"] is not False or index["recoupling_required"] is not True or
            index["selection"] != "baseline pending"):
        raise ValueError("derived topology parent/source/recoupling contract mismatch")
    source, source_metadata = read_record(index["source"])
    original, original_metadata = read_record(parent["inputs"]["source_record"])
    topology, metadata = read_record(index["hierarchy"])
    if (metadata["source_identity_sha256"] != index["source"]["expected_identity"] or
            metadata["source_metadata"] != source_metadata or
            source_metadata["source_sha256"] != parent["inputs"]["source_record"]["expected_sha256"]):
        raise ValueError("rebuilt actual bed source provenance differs")
    for name in ("height_m", "valid_mask", "protected_mask", "open_boundary_mask"):
        np.testing.assert_array_equal(topology[name], source[name])
    for name in ("valid_mask", "protected_mask", "open_boundary_mask"):
        np.testing.assert_array_equal(source[name], original[name])
    for name in ("origin_m_xz", "spacing_m"):
        if metadata[name] != source_metadata[name] or source_metadata[name] != original_metadata[name]:
            raise ValueError("derived topology changes original physical grid")
    hierarchy_checks = audit_hierarchy(topology, metadata)
    if any(value is not False for value in index["flags"].values()):
        raise ValueError("topology publication asserts unsupported readiness")
    for record in (index["source"], index["hierarchy"], parent_record, parent["inputs"]["source_record"]):
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("topology audit inputs changed during inspection")
    info = psutil.Process().memory_info()
    resource = dict(peak_rss_bytes=int(getattr(info, "peak_wset", info.rss)),
                    peak_private_bytes=getattr(info, "peak_pagefile", None))
    if resource["peak_private_bytes"] is None or max(resource.values()) > 1073741824:
        raise MemoryError("independent topology audit requires bounded RSS/private evidence")
    return dict(schema="td-independent-accepted-topology-v1", index=str(index_path),
        index_sha256=expected_sha256, parent=parent_record, candidate_id=candidate_id,
        source=index["source"], hierarchy=index["hierarchy"], independent_hierarchy_checks=hierarchy_checks,
        changed_bed_cells=int(np.count_nonzero(source["height_m"] != original["height_m"])),
        resource=resource, solver_advanced=False, hydrology_solved=False,
        recoupling_required=True, hydraulic_ready=False, natural_outlet_verified=False,
        publishable=False, auditor_sha256=file_sha256(__file__))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--parent-sha256", required=True)
    parser.add_argument("--parent-identity", required=True)
    args = parser.parse_args()
    parent = dict(path=str(args.parent.resolve(strict=True)), expected_sha256=args.parent_sha256,
                  expected_identity=args.parent_identity)
    report = audit(args.index, args.index_sha256, parent)
    output = ROOT / "verification/td-accepted-candidate-topology" / ("independent-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(report, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(output), sha256=file_sha256(output)), ensure_ascii=False))
