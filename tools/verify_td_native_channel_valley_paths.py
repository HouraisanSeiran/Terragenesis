"""Build a pinned, render-only valley path prototype from saved TD evidence."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.td_native_channel_geometry import load_channel_geometry
from terrain_pipeline.td_native_channel_valley_paths import build_valley_paths, load_valley_paths, save_valley_paths


def run(geometry_report_path, expected_report_sha256, output_directory, window):
    if file_sha256(geometry_report_path) != expected_report_sha256:
        raise ValueError("geometry report external SHA mismatch")
    report = json.loads(Path(geometry_report_path).read_text(encoding="utf-8"))
    geometry_pin = report["geometry"]
    hierarchy_pin = report["inputs"]["hierarchy"]
    page_pin = report["inputs"]["hour_page"]
    if file_sha256(geometry_pin["path"]) != geometry_pin["expected_sha256"] or \
            file_sha256(hierarchy_pin["path"]) != hierarchy_pin["expected_sha256"] or \
            file_sha256(page_pin["path"]) != page_pin["expected_sha256"]:
        raise ValueError("source file pin mismatch")
    geometry = load_channel_geometry(**geometry_pin)
    hierarchy = load_basin_hierarchy(**hierarchy_pin)
    if geometry["metadata"]["hour_page_identity"] != page_pin["expected_identity"]:
        raise ValueError("hour page identity mismatch")
    paths = build_valley_paths(geometry, hierarchy, window=window)
    for pin in (geometry_pin, hierarchy_pin, page_pin):
        if file_sha256(pin["path"]) != pin["expected_sha256"]:
            raise ValueError("source changed while building paths")
    if file_sha256(geometry_report_path) != expected_report_sha256:
        raise ValueError("geometry report changed while building paths")
    code_paths = ("terrain_pipeline/td_native_channel_valley_paths.py",
                  "tests/test_td_native_channel_valley_paths.py",
                  "tools/verify_td_native_channel_valley_paths.py")
    code_sha256 = {name: file_sha256(ROOT / name) for name in code_paths}
    output_directory = Path(output_directory)
    if output_directory.exists():
        raise FileExistsError(output_directory)
    output_directory.mkdir(parents=True)
    path = output_directory / "paths.npz"
    save_valley_paths(path, paths)
    pin = dict(path=str(path.resolve()), expected_sha256=file_sha256(path), expected_identity=paths["identity_sha256"])
    cold = load_valley_paths(**pin)
    if cold["identity_sha256"] != paths["identity_sha256"]:
        raise ValueError("cold path identity mismatch")
    output_report = dict(schema="td-native-channel-valley-paths-prototype-v1",
                         source_report=dict(path=str(Path(geometry_report_path).resolve()), expected_sha256=expected_report_sha256),
                         geometry=geometry_pin, hierarchy=hierarchy_pin, hour_page=page_pin, paths=pin,
                         metadata=paths["metadata"], code_sha256=code_sha256,
                         points=int(len(paths["arrays"]["points_xyz_m"])),
                         chains=int(len(paths["arrays"]["chain_accepted"])),
                         included_active_edges=int(len(paths["arrays"]["included_active_edge_indices"])),
                         water_generated=False,
                         hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    if any(file_sha256(ROOT / name) != digest for name, digest in code_sha256.items()):
        raise ValueError("valley path code changed while exporting")
    publish_bytes(output_directory / "report.json", json.dumps(output_report, indent=2, ensure_ascii=False).encode("utf-8"))
    return output_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry_report", type=Path)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--window", nargs=4, type=int, metavar=("X0", "X1", "Z0", "Z1"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = args.output or ROOT / "verification/td-native-channel-valley-paths" / \
        ("prototype-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    result = run(args.geometry_report, args.report_sha256, output, args.window)
    print(json.dumps({"output": str(output), "paths_sha256": result["paths"]["expected_sha256"],
                      "metadata": result["metadata"]}, indent=2))


if __name__ == "__main__":
    main()
