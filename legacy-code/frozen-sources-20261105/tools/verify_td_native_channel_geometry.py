"""Read pinned single-hour inputs and export diagnostic geometry; no solver."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_native_channel_geometry import (
    build_channel_geometry, load_channel_geometry, load_geometry_inputs, save_channel_geometry,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-records", type=Path, required=True)
    parser.add_argument("--input-records-sha256", required=True)
    args = parser.parse_args()
    if file_sha256(args.input_records) != args.input_records_sha256:
        raise ValueError("external input records SHA mismatch")
    records = json.loads(args.input_records.read_text(encoding="utf-8"))
    hierarchy, page = load_geometry_inputs(records["hierarchy"], records["hour_page"])
    geometry = build_channel_geometry(hierarchy, page)
    arrays = geometry["arrays"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = ROOT / "verification" / "td-native-channel-geometry" / ("A-prototype-" + stamp)
    path = destination / "geometry.npz"
    save_channel_geometry(path, geometry)
    pin = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=geometry["identity_sha256"])
    loaded = load_channel_geometry(**pin)
    if loaded["identity_sha256"] != geometry["identity_sha256"]:
        raise ValueError("roundtrip identity failed")
    if file_sha256(args.input_records) != args.input_records_sha256:
        raise ValueError("input records changed during read")
    report = dict(schema="td-native-channel-geometry-prototype-report-v1", scope="single saved TD hour diagnostic prototype",
                  input_records=dict(path=str(args.input_records.resolve()), expected_sha256=args.input_records_sha256),
                  inputs=records, geometry=pin, nodes=len(arrays["node_cell_ids"]), edges=len(arrays["edge_cell_ids"]),
                  internal_sinks=int(arrays["node_internal_sink"].sum()),
                  active_edges=int(arrays["edge_geometry_active"].sum()), active_nodes=int(arrays["node_geometry_active"].sum()),
                  engineering_boundary_nodes=int(arrays["node_engineering_boundary"].sum()),
                  actual_faces=len(arrays["actual_face_cells"]),
                  bidirectional_faces=int(np.count_nonzero((arrays["actual_face_forward_m3"] > 0) & (arrays["actual_face_reverse_m3"] > 0))),
                  roundtrip_identity_passed=True, solver_advanced=False, source_modified=False,
                  numerical_acceptance="unverified; not accepted or converged", hydraulic_ready=False,
                  natural_outlet_verified=False, publishable=False,
                  code_sha256={name: file_sha256(ROOT / name) for name in (
                      "terrain_pipeline/td_native_channel_geometry.py", "tests/test_td_native_channel_geometry.py",
                      "tools/verify_td_native_channel_geometry.py")})
    (destination / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
