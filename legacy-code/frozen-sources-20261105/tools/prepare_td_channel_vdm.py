"""Derive metric XYZ VDM offline from pinned river-bed geometry, without a game."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.metric_vdm import CliffRecipe, load_vdm, save_vdm
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_channel_vdm import build_channel_vdm
from terrain_pipeline.td_native_channel_surface import load_channel_surface


def prepare(configuration, expected_sha256, output):
    configuration = Path(configuration).resolve(strict=True)
    if file_sha256(configuration) != expected_sha256:
        raise ValueError("VDM configuration pin mismatch")
    config = json.loads(configuration.read_text(encoding="utf-8"))
    if set(config) not in ({"surface", "hierarchy", "recipe"}, {"surface", "hierarchy", "recipe", "form"}):
        raise ValueError("VDM configuration fields mismatch")
    surface = load_channel_surface(**config["surface"])
    hierarchy = load_basin_hierarchy(**config["hierarchy"])
    settings = dict(config["recipe"])
    settings["center_xz_m"] = tuple(settings["center_xz_m"])
    settings["outward_xz"] = tuple(settings["outward_xz"])
    form = None
    save, load = save_vdm, load_vdm
    if "form" in config:
        from terrain_pipeline.metric_vdm_forms import FormRecipe, save_formed_vdm, load_formed_vdm
        form = FormRecipe(**config["form"])
        save, load = save_formed_vdm, load_formed_vdm
    result = build_channel_vdm(surface, hierarchy, recipe=CliffRecipe(**settings), form=form)
    arrays = result["arrays"]
    displaced = arrays["vertices_xyz_m"]
    reference = arrays["reference_xyz_m"].reshape(-1, 3)
    triangles = arrays["triangles"]
    normals = np.cross(displaced[triangles[:, 1]] - displaced[triangles[:, 0]],
                       displaced[triangles[:, 2]] - displaced[triangles[:, 0]])
    changed = np.any(displaced != reference, axis=1)
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    bundle_path = output / "vdm.npz"
    save(bundle_path, result)
    pin = dict(path=str(bundle_path), expected_sha256=file_sha256(bundle_path),
               expected_identity=result["identity_sha256"])
    loaded = load(**pin)
    if not np.array_equal(loaded["arrays"]["vertices_xyz_m"], displaced):
        raise ValueError("VDM saved XYZ changed")
    for name, vertices in (("reference", reference), ("derived", displaced)):
        lines = ["# physical metres XYZ; source parameter topology preserved; not a closed solid"]
        lines.extend("v " + " ".join(format(float(value), ".17g") for value in vertex) for vertex in vertices)
        lines.extend("f " + " ".join(str(int(value) + 1) for value in face) for face in triangles)
        publish_bytes(output / (name + ".obj"), ("\n".join(lines) + "\n").encode("ascii"))
    review = dict(schema="metric-vdm-review-v1", coordinates="physical metres XYZ, y up",
                  form=result["metadata"].get("form"),
                  effective_recipe=result["metadata"]["recipe"],
                  geometry_schema=result["metadata"]["schema"],
                  source_identity=surface["identity_sha256"], vdm_identity=result["identity_sha256"],
                  shape=list(arrays["protected_mask"].shape), reference_xyz_m=reference.tolist(),
                  displacement_xyz_m=arrays["displacement_xyz_m"].reshape(-1, 3).tolist(),
                  triangles=triangles.tolist(), protected_mask=arrays["protected_mask"].ravel().tolist(),
                  hydraulic_ready=False, publishable=False, self_intersection_verified=False)
    publish_bytes(output / "review.json", json.dumps(review, separators=(",", ":"), allow_nan=False).encode())
    for record in (config["surface"], config["hierarchy"]):
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("VDM source changed during export")
    if file_sha256(configuration) != expected_sha256:
        raise ValueError("VDM configuration changed during export")
    report = dict(schema="td-channel-vdm-preparation-v1", inputs=config,
                  configuration=dict(path=str(configuration), expected_sha256=expected_sha256),
                  vdm=pin, vertices=len(displaced), triangles=len(triangles), changed_vertices=int(changed.sum()),
                  downward_facing_triangles=int((normals[:, 1] < 0).sum()),
                  protected_vertices=int(arrays["protected_mask"].sum()),
                  max_displacement_m=float(np.linalg.norm(displaced - reference, axis=1).max()),
                  cold_roundtrip_passed=True, source_unchanged=True, swept_protected_boxes_clear=True,
                  river_protection_scope="saved candidate cut footprint and coarse protected/unknown stencil with collar",
                  geometry_migration="Java CliffGeometry skeleton formula, metric configurable placement",
                  form=result["metadata"].get("form"),
                  effective_recipe=result["metadata"]["recipe"],
                  geometry_schema=result["metadata"]["schema"],
                  water_generated=False, solver_advanced=False, hydraulic_ready=False, publishable=False,
                  natural_outlet_verified=False, self_intersection_verified=False,
                  limitations=["no Voronoi or runoff/erosion solver migration in this batch",
                               "source 1m bed is derived from 30m TD, not measured 1m terrain",
                               "source hour diagnostic identity retained; not new accepted hydraulics",
                               "triangle normals alone do not prove a non-self-intersecting solid"],
                  artifacts={name: file_sha256(output / name) for name in ("reference.obj", "derived.obj", "review.json")},
                  code_sha256={name: file_sha256(ROOT / name) for name in (
                      "terrain_pipeline/metric_vdm.py", "terrain_pipeline/td_channel_vdm.py", "tools/prepare_td_channel_vdm.py")})
    if form is not None:
        report["code_sha256"]["terrain_pipeline/metric_vdm_forms.py"] = file_sha256(ROOT / "terrain_pipeline/metric_vdm_forms.py")
    publish_bytes(output / "report.json", json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--configuration-sha256", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "verification/metric-vdm" / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ"))
    arguments = parser.parse_args()
    result = prepare(arguments.configuration, arguments.configuration_sha256, arguments.output)
    print(json.dumps({key: result[key] for key in ("vdm", "changed_vertices", "downward_facing_triangles", "protected_vertices")}, ensure_ascii=False))
