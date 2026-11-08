"""Export one pinned saved v10 native water snapshot; never runs a solver."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.td_native_water_surface import (
    build_water_surface, export_water_obj, load_pinned_page, load_water_surface, save_water_surface,
)


def run(page_path, *, page_sha256, page_identity, wet_threshold_m, output_directory):
    output = Path(output_directory)
    if output.exists():
        raise FileExistsError(output)
    page = load_pinned_page(page_path, expected_sha256=page_sha256, expected_identity=page_identity)
    surface = build_water_surface(page, source_sha256=page_sha256, wet_threshold_m=wet_threshold_m)
    if file_sha256(page_path) != page_sha256:
        raise ValueError("v10 page changed while exporting")
    output.mkdir(parents=True)
    mesh_path = output / "surface.npz"
    obj_path = output / "surface.obj"
    save_water_surface(mesh_path, surface)
    export_water_obj(obj_path, surface)
    mesh_pin = dict(path=str(mesh_path.resolve()), expected_sha256=file_sha256(mesh_path),
                    expected_identity=surface["identity_sha256"])
    load_water_surface(**mesh_pin)
    source_files = ("terrain_pipeline/td_native_water_surface.py", "tests/test_td_native_water_surface.py",
                    "tools/verify_td_native_water_surface.py")
    report = dict(schema="td-native-water-surface-prototype-v1",
                  source_page=dict(path=str(Path(page_path).resolve()), expected_sha256=page_sha256,
                                   expected_identity=page_identity), surface=mesh_pin,
                  obj=dict(path=str(obj_path.resolve()), expected_sha256=file_sha256(obj_path)),
                  metadata=surface["metadata"], code_sha256={name: file_sha256(ROOT / name) for name in source_files},
                  vertex_count=int(len(surface["arrays"]["vertex_cell_ids"])),
                  triangle_count=int(len(surface["arrays"]["triangles"])))
    if file_sha256(page_path) != page_sha256:
        raise ValueError("v10 page changed while writing artifact")
    publish_bytes(output / "report.json", json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", type=Path)
    parser.add_argument("--page-sha256", required=True)
    parser.add_argument("--page-identity", required=True)
    parser.add_argument("--wet-threshold-m", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.page, page_sha256=args.page_sha256, page_identity=args.page_identity,
                 wet_threshold_m=args.wet_threshold_m, output_directory=args.output)
    print(json.dumps({"surface": report["surface"], "obj": report["obj"],
                      "vertices": report["vertex_count"], "triangles": report["triangle_count"],
                      "grid_water_volume_m3": report["metadata"]["grid_water_volume_m3"]}, indent=2))


if __name__ == "__main__":
    main()
