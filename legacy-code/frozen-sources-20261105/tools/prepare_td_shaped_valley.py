"""Save anchored real TD centerlines and the actual monotone bed they generate."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_geometry import GeometryConfig
from terrain_pipeline.surface_rivers.metric_network_geometry import load_network_geometry_plan
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from terrain_pipeline.surface_rivers.metric_valley_centerline import (
    CenterlineRecipe, build_valley_centerline, save_valley_centerline,
)
from terrain_pipeline.surface_rivers.metric_monotone_union import (
    build_monotone_union, save_monotone_union, load_monotone_union,
)
from tools.verify_td_river_geometry import TD_DIRECTORY, TD_PRODUCT_ID, TD_PRODUCT_SHA, terrain_from_product

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "verification/td-valley-global-tiled/td1024-20261008-01"
PLAN = ROOT / "verification/td-river-network-expansion/td1024-20261008-01"


def statistics(points, receiver):
    donors = [[] for _ in receiver]
    lengths, angles = [], []
    for i, j in enumerate(receiver):
        if j >= 0:
            donors[j].append(i)
            lengths.append(float(np.linalg.norm(points[j] - points[i])))
    for i, j in enumerate(receiver):
        if j >= 0 and len(donors[i]) == 1:
            a, b = points[i] - points[donors[i][0]], points[j] - points[i]
            angles.append(float(np.degrees(np.arccos(np.clip(a @ b / np.linalg.norm(a) / np.linalg.norm(b), -1, 1)))))
    return dict(length_m=sum(lengths), max_turn_degrees=max(angles, default=0.),
                mean_turn_degrees=float(np.mean(angles)) if angles else 0.,
                turn_degrees=angles)


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    baseline = json.loads((BASE / "failure-prefix.json").read_text(encoding="utf-8"))
    pin = json.loads((PLAN / "acceptance.json").read_text(encoding="utf-8"))["plan"]
    plan = load_network_geometry_plan(PLAN / pin["path"], expected_sha256=pin["sha256"])
    source = load_diagnostic_product(TD_DIRECTORY / "product.npz", expected_sha256=TD_PRODUCT_SHA, expected_identity=TD_PRODUCT_ID)
    terrain = terrain_from_product(source)
    owner = plan["arrays"]["terminal_owner"].reshape(terrain.elevation_m.shape)
    q = plan["arrays"]["contributing_area_m2"] / 1000. / 3600.
    outcomes, cases = [], []
    options = dict(owner_grid=owner, corridor_mask=np.ones(owner.shape, bool), lake_mask=np.zeros(owner.shape, bool),
                   source_plan_identity_sha256=plan["identity_sha256"])
    for index, record in baseline["component_records"].items():
        ids = np.array(record["source_node_ids"], np.int64)
        # Bounded demonstration components; retain the complete declared coverage above.
        if len(ids) < 4 or len(ids) > 14:
            continue
        mapping = {int(cell): i for i, cell in enumerate(ids)}
        rec = np.array([mapping.get(int(plan["arrays"]["graph_receiver"][cell]), -1) for cell in ids], np.int64)
        width, depth = np.maximum(6., 4. * np.sqrt(q[ids])), np.maximum(.25, .2 * np.cbrt(q[ids]))
        row = dict(component=index, edge_count=int(np.sum(rec >= 0)))
        try:
            centerline = build_valley_centerline(terrain, ids, rec, width, depth, **options,
                recipe=CenterlineRecipe(iterations=8), config=GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0))
            if centerline["metadata"]["moved_nodes"] == 0:
                raise ValueError("no legal anchored displacement decreased turn energy")
            before = build_monotone_union(terrain, ids, rec, width, depth, **options,
                config=GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0))
            coarse = build_monotone_union(terrain, ids, rec, width, depth, **options, centerline=centerline,
                config=GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0))
            fine = build_monotone_union(terrain, ids, rec, width, depth, **options, centerline=centerline,
                config=GeometryConfig(fine_spacing_m=.25, smoothing_iterations=0))
            relative = abs(coarse["metadata"]["cut_volume_m3"] - fine["metadata"]["cut_volume_m3"]) / fine["metadata"]["cut_volume_m3"]
            if relative > .02:
                raise ValueError("shaped bed volume fails fixed 2% refinement")
            artifacts = {}
            for label, bundle in (("before", before), ("coarse", coarse), ("fine", fine)):
                path = output / f"component-{index}-{label}.npz"
                save_monotone_union(path, bundle)
                sha = file_sha256(path)
                load_monotone_union(path, expected_sha256=sha, expected_identity=bundle["identity_sha256"])
                artifacts[label] = dict(path=str(path), sha256=sha, identity_sha256=bundle["identity_sha256"])
            center_path = output / f"component-{index}-centerline.npz"
            save_valley_centerline(center_path, centerline)
            artifacts["centerline"] = dict(path=str(center_path), sha256=file_sha256(center_path), identity_sha256=centerline["identity_sha256"])
            ca, fa = centerline["arrays"], fine["arrays"]
            row.update(status="accepted_shaped_component", before=statistics(ca["original_node_xz_m"], rec),
                       after=statistics(ca["node_xz_m"], rec), moved_nodes=centerline["metadata"]["moved_nodes"],
                       max_offset_m=float(np.linalg.norm(ca["node_xz_m"] - ca["original_node_xz_m"], axis=1).max()),
                       max_cut_m=float(fa["cut_depth_m"].max()), original_cut_volume_m3=before["metadata"]["cut_volume_m3"],
                       shaped_cut_volume_m3=coarse["metadata"]["cut_volume_m3"],
                       comparison_spacing_m=.5, shaped_fine_cut_volume_m3=fine["metadata"]["cut_volume_m3"],
                       spatial_refinement_relative=relative,
                       artifacts=artifacts, anchors_unchanged=True, actual_bed_monotone=True)
            cases.append(row)
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            for i, j in enumerate(rec):
                if j >= 0:
                    axes[0].plot(*ca["original_node_xz_m"][[i, j]].T, color="gray", linestyle="--")
                    axes[0].plot(*ca["node_xz_m"][[i, j]].T, color="blue")
            axes[0].set_aspect("equal")
            axes[0].set_title("Original D8 / anchored generated bed route")
            im = axes[1].tripcolor(fa["vertices_xz_m"][:, 0], fa["vertices_xz_m"][:, 1], fa["triangles"], fa["cut_depth_m"], shading="gouraud")
            axes[1].set_aspect("equal")
            axes[1].set_title("Saved actual bed incision (m)")
            fig.colorbar(im, ax=axes[1])
            fig.tight_layout()
            fig.savefig(output / f"component-{index}-comparison.png", dpi=160)
            plt.close(fig)
        except ValueError as error:
            row.update(status="refused_shaped_component", reason=str(error))
        outcomes.append(row)
        print(json.dumps({k: row[k] for k in ("component", "status")}), flush=True)
        if len(cases) >= 3:
            break
    report = dict(schema="td-anchored-shaped-valley-results-v1", status="bounded_shaped_geometry",
        source=dict(path=str(TD_DIRECTORY / "product.npz"), sha256=TD_PRODUCT_SHA, identity_sha256=TD_PRODUCT_ID),
        baseline_report=dict(path=str(BASE / "failure-prefix.json"), sha256=file_sha256(BASE / "failure-prefix.json")),
        declared_edges=673, baseline_accepted_edges=623, current_global_accepted_edges=623, unresolved_edges=50,
        scope="bounded replacement candidates; global replacement ledger and hydraulics pending",
        improved_edges=sum(row["edge_count"] for row in cases), cases=cases, outcomes=outcomes,
        source_preserved=True, hydraulic_ready=False, publishable=False,
        code_sha256={name:file_sha256(ROOT / name) for name in ("terrain_pipeline/surface_rivers/metric_monotone_union.py", "tools/prepare_td_shaped_valley.py")})
    publish_bytes(output / "manifest.json", json.dumps(report, indent=2, allow_nan=False).encode())
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    result = prepare(parser.parse_args().output.resolve())
    print(json.dumps(dict(improved_edges=result["improved_edges"], cases=len(result["cases"]))))
