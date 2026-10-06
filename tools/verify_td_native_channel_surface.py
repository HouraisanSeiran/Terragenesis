"""Explicitly join four pinned candidate bed tiles and export no-water NPZ/OBJ."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_native_channel_geometry import load_channel_geometry
from terrain_pipeline.td_native_channel_surface import build_channel_surface, export_surface_obj, load_channel_surface, load_surface_tiles, save_channel_surface


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tile-report", type=Path, required=True)
    parser.add_argument("--tile-report-sha256", required=True)
    args = parser.parse_args()
    if file_sha256(args.tile_report) != args.tile_report_sha256:
        raise ValueError("tile report external SHA mismatch")
    source = json.loads(args.tile_report.read_text(encoding="utf-8"))
    geometry = load_channel_geometry(**source["geometry"])
    tiles = load_surface_tiles(source["tiles"])
    surface = build_channel_surface(tiles, geometry=geometry)
    reversed_surface = build_channel_surface(tiles[::-1], geometry=geometry)
    if surface["identity_sha256"] != reversed_surface["identity_sha256"]:
        raise ValueError("join order differs")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = ROOT / "verification" / "td-native-channel-surface" / ("A-prototype-" + stamp)
    path = destination / "surface.npz"
    save_channel_surface(path, surface)
    surface_pin = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=surface["identity_sha256"])
    loaded = load_channel_surface(**surface_pin)
    obj_path = destination / "surface.obj"
    export_surface_obj(obj_path, loaded)
    for record in source["tiles"] + [source["geometry"]]:
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("source chain changed during join")
    if file_sha256(args.tile_report) != args.tile_report_sha256:
        raise ValueError("tile report changed during join")
    report = dict(schema="td-native-channel-surface-prototype-v1", source_tile_report=dict(
                      path=str(args.tile_report.resolve()), expected_sha256=args.tile_report_sha256),
                  geometry=source["geometry"], tiles=source["tiles"], surface=surface_pin,
                  obj=dict(path=str(obj_path), expected_sha256=file_sha256(obj_path)),
                  metadata=surface["metadata"], join_order_independent=True, cold_roundtrip_identity_passed=True,
                  cold_load_generates=False, water_generated=False, hydraulic_ready=False,
                  natural_outlet_verified=False, publishable=False,
                  code_sha256={name: file_sha256(ROOT / name) for name in (
                      "terrain_pipeline/td_native_channel_surface.py", "tests/test_td_native_channel_surface.py",
                      "tools/verify_td_native_channel_surface.py")})
    publish_bytes(destination / "report.json", json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
