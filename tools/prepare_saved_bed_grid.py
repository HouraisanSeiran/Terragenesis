#!/usr/bin/env python3
"""Prepare the saved bed grid from the accepted shared-section report (20261016-01)."""
import os

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.verify_fluvial_channel_remobilization import resource_limits  # noqa: E402
from tools.prepare_hydrology_domains import _read_bed_piece  # noqa: E402
from terrain_pipeline.channel_geometry import sample_saved_bed_grid  # noqa: E402

REPORT = ROOT / (
    "verification/hydrological-planning-domain/full-edges-v5-20261014-03/"
    "edge-8470-8600-v7-shared-sections-owned-halo2/report.json"
)
OUT_DIR = ROOT / ".scratch/hydrological-planning-domain/saved-bed-grid-20261016-01"
EXPECTED_SOURCE_EDGE = [8470, 8600]


def _sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    resource_limits()
    report = json.loads(REPORT.read_text())
    assert report["accepted"] is True
    assert report["source_edge"] == EXPECTED_SOURCE_EDGE
    assert len(report["piece_paths"]) == 29
    report_sha256 = _sha256_file(REPORT)

    records = []
    source_hashes = {}
    for rel in report["piece_paths"]:
        path = ROOT / rel
        rec = _read_bed_piece(path)
        rec["source_path"] = str(path)
        rec["archive_sha256"] = _sha256_file(path)
        source_hashes[str(path)] = rec["archive_sha256"]
        assert rec["parent_detail_identity"] == report["detail_identity"]
        assert rec["frozen_plan_identity"] == report["plan_identity"]
        records.append(rec)

    center = np.array(records[0]["arrays"]["node_xz_m"][1], dtype=float)
    origin = center - np.array([20.0, 20.0])
    result = sample_saved_bed_grid(
        records,
        origin_xz_m=origin,
        shape_zx=(41, 41),
        spacing_m=1.0,
    )

    for path_str, digest in source_hashes.items():
        assert _sha256_file(Path(path_str)) == digest
    assert _sha256_file(REPORT) == report_sha256

    OUT_DIR.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(
        OUT_DIR / "sample-grid.npz",
        bed_m=result["bed_m"],
        supported_mask=result["supported_mask"],
        owner_piece_index=result["owner_piece_index"],
        metadata_json=np.array(json.dumps(result["provenance"])),
    )

    summary = {
        "passed": True,
        "report_sha256": report_sha256,
        "center_xz_m": center.tolist(),
        "origin_xz_m": origin.tolist(),
        "shape_zx": [41, 41],
        "spacing_m": 1.0,
        "support_count": int(result["supported_mask"].sum()),
        "maximum_shared_section_difference_m": result["provenance"][
            "maximum_shared_section_difference_m"
        ],
        "hydraulics_coupled": False,
        "publishable": False,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
