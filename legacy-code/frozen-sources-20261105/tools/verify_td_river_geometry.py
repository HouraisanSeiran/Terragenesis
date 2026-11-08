"""Bounded M5 fixtures and original TD geometry, independent mesh evidence."""

import argparse
import json
from pathlib import Path
import struct

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_channel_geometry import (
    GeometryConfig, build_channel_geometry, load_channel_geometry, save_channel_geometry,
)
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy


ROOT = Path(__file__).resolve().parents[1]
TD_DIRECTORY = ROOT / "verification/td-river-milestones/td1024-20261008-01"
TD_PRODUCT_SHA = "070b121bbe56d0d61caa3552f2b868ddbac28483da389bebb7b9ec36b617030c"
TD_PRODUCT_ID = "365db961a6c21795707e74080216e309732ee450b3c5d80913113d4ed1eeee74"


def mesh_evidence(product):
    """Integrate the actual saved triangles and check incidence, without generation."""
    a = product["arrays"]
    points, faces = a["vertices_xz_m"], a["triangles"]
    v = points[faces]
    signed = ((v[:, 1, 0] - v[:, 0, 0]) * (v[:, 2, 1] - v[:, 0, 1])
              - (v[:, 2, 0] - v[:, 0, 0]) * (v[:, 1, 1] - v[:, 0, 1])) / 2.
    if np.any(signed == 0.) or not (np.all(signed > 0.) or np.all(signed < 0.)):
        raise AssertionError("degenerate or reversed mesh triangles")
    area = np.abs(signed)
    cut = float(np.dot(area, np.mean(a["cut_depth_m"][faces], axis=1)))
    difference = float(np.dot(area, np.mean(
        (a["source_elevation_m"] - a["bed_elevation_m"])[faces], axis=1)))
    np.testing.assert_allclose(cut, difference, rtol=1e-10, atol=1e-8)
    np.testing.assert_allclose(cut, product["metadata"]["cut_volume_m3"], rtol=1e-10, atol=1e-8)
    directed = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    undirected = np.sort(directed, axis=1)
    _, inverse, counts = np.unique(undirected, axis=0, return_inverse=True, return_counts=True)
    if np.any(counts > 2):
        raise AssertionError("nonmanifold triangle edges")
    direction = np.where(directed[:, 0] < directed[:, 1], 1, -1)
    orientation = np.bincount(inverse, weights=direction)
    if np.any(orientation[counts == 2] != 0):
        raise AssertionError("internal mesh edges are not reversed pairs")
    bary = a["canonical_port_barycentric"]
    port_faces = faces[a["canonical_port_triangle_ids"]]
    observed = np.sum(a["cut_depth_m"][port_faces] * bary, axis=-1)
    np.testing.assert_allclose(observed, a["canonical_port_cut_depth_m"], rtol=0., atol=1e-10)
    np.testing.assert_allclose(np.sum(points[port_faces] * bary[..., None], axis=-2),
                               a["canonical_port_profile_xz_m"], rtol=0., atol=1e-8)
    return {"represented_cut_volume_m3": cut, "mesh_volume_difference_m3": difference,
            "triangles": len(faces), "vertices": len(points),
            "canonical_ports": len(bary), "internal_edges_reversed": True,
            "shared_port_observations_verified": True, "deposition_bulk_m3": 0.}


def shape_evidence(product):
    a = product["arrays"]
    receiver = a["receiver"]
    donors = [[] for _ in receiver]
    for i, j in enumerate(receiver):
        if j >= 0:
            donors[j].append(i)

    def angles(points):
        values = []
        for i, j in enumerate(receiver):
            if j < 0 or len(donors[i]) != 1:
                continue
            first = points[i] - points[donors[i][0]]
            second = points[j] - points[i]
            cosine = np.dot(first, second) / (np.linalg.norm(first) * np.linalg.norm(second))
            values.append(float(np.degrees(np.arccos(np.clip(cosine, -1., 1.)))))
        return values

    before, after = angles(a["original_node_xz_m"]), angles(a["node_xz_m"])
    def curvatures(points, turns):
        result = []
        for i, j in enumerate(receiver):
            if j < 0 or len(donors[i]) != 1:
                continue
            average_length = (np.linalg.norm(points[i] - points[donors[i][0]])
                               + np.linalg.norm(points[j] - points[i])) / 2.
            result.append(float(2. * np.sin(np.radians(turns[len(result)]) / 2.) / average_length))
        return result
    before_curvature = curvatures(a["original_node_xz_m"], before)
    after_curvature = curvatures(a["node_xz_m"], after)
    height = a["source_height_m"].ravel()[a["source_node_cell_ids"]]
    return {"original_turn_degrees": before, "candidate_turn_degrees": after,
            "original_discrete_curvature_per_m": before_curvature,
            "candidate_discrete_curvature_per_m": after_curvature,
            "max_original_turn_degrees": max(before, default=0.),
            "max_candidate_turn_degrees": max(after, default=0.),
            "max_node_offset_m": float(np.linalg.norm(
                a["node_xz_m"] - a["original_node_xz_m"], axis=1).max()),
            "original_minus_candidate_source_height_m": (height - a["node_source_elevation_m"]).tolist(),
            "source_anchors_unchanged": bool(np.array_equal(
                a["node_xz_m"][a["anchor_mask"]], a["original_node_xz_m"][a["anchor_mask"]]))}


def export_glb(product, path):
    """glTF 2.0 binary export of the exact indexed bed mesh, translated for float32."""
    a = product["arrays"]
    origin = np.array([a["vertices_xz_m"][:, 0].min(), a["bed_elevation_m"].min(),
                       a["vertices_xz_m"][:, 1].min()])
    positions = np.column_stack((a["vertices_xz_m"][:, 0], a["bed_elevation_m"],
                                 a["vertices_xz_m"][:, 1])) - origin
    positions = np.ascontiguousarray(positions, dtype="<f4")
    faces = np.ascontiguousarray(a["triangles"], dtype="<u4")
    binary = positions.tobytes() + faces.tobytes()
    document = {"asset": {"version": "2.0", "generator": "Terragenesis M5 saved indexed mesh"},
                "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
                "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1,
                                               "material": 0}]}],
                "materials": [{"doubleSided": True, "pbrMetallicRoughness": {
                    "baseColorFactor": [.32, .52, .4, 1.], "metallicFactor": 0., "roughnessFactor": 1.}}],
                "buffers": [{"byteLength": len(binary)}],
                "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": positions.nbytes,
                                  "target": 34962},
                                 {"buffer": 0, "byteOffset": positions.nbytes,
                                  "byteLength": faces.nbytes, "target": 34963}],
                "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(positions),
                               "type": "VEC3", "min": positions.min(axis=0).tolist(),
                               "max": positions.max(axis=0).tolist()},
                              {"bufferView": 1, "componentType": 5125, "count": faces.size,
                               "type": "SCALAR"}],
                "extras": {"source_identity_sha256": product["identity_sha256"],
                           "origin_world_xyz_m": origin.tolist(),
                           "display_export_no_hydraulic_certification": True}}
    encoded = json.dumps(document, separators=(",", ":"), allow_nan=False).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    binary += b"\x00" * (-len(binary) % 4)
    payload = (struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(encoded) + 8 + len(binary))
               + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
               + struct.pack("<II", len(binary), 0x004E4942) + binary)
    publish_bytes(path, payload)


def fixture(name, spacing=1.):
    rows, cols = np.mgrid[:13, :13]
    height = 100. - .15 * (rows * 10. + cols * 10.)
    if name == "single":
        cells, receiver = [(3, 3), (3, 4), (3, 5), (3, 6)], [1, 2, 3, -1]
    elif name == "turn":
        cells, receiver = [(3, 3), (3, 4), (4, 4), (4, 5), (5, 5), (5, 6)], [1, 2, 3, 4, 5, -1]
    elif name == "acute":
        height = 100. - .15 * rows * 10. - .25 * cols * 10.
        cells, receiver = [(3, 3), (2, 4), (3, 4), (3, 5)], [1, 2, 3, -1]
    elif name == "y":
        cells, receiver = [(3, 4), (4, 3), (4, 4), (5, 5), (6, 6)], [2, 2, 3, 4, -1]
    elif name == "lake":
        cells, receiver = [(4, 3), (4, 4), (4, 5)], [1, 2, -1]
    else:
        raise ValueError(name)
    terrain = TerrainGrid(height.astype(np.float64), np.ones(height.shape, bool), 0., 0., 10., 10.,
                          "generated_terrain", "analytical_plane_" + name, "a" * 64)
    ids = np.array([r * 13 + c for r, c in cells], np.int64)
    lake = np.zeros(height.shape, bool)
    stage = None
    if name == "lake":
        lake[3:7, 5:9] = True
        stage = float(height[cells[-1]]) + .1
    return terrain, ids, np.array(receiver, np.int64), {
        "width_m": np.full(len(ids), 6.), "depth_m": np.full(len(ids), .4),
        "owner_grid": np.ones(height.shape, np.int64), "corridor_mask": np.ones(height.shape, bool),
        "lake_mask": lake, "anchor_mask": np.zeros(len(ids), bool), "lake_stage_m": stage,
        "config": GeometryConfig(fine_spacing_m=spacing)}


def terrain_from_product(source):
    m, a = source["metadata"]["terrain"], source["arrays"]
    fields = {key: m[key] for key in TerrainGrid.__dataclass_fields__
              if key not in ("elevation_m", "valid_mask") and key in m}
    return TerrainGrid(a["elevation_m"].copy(), a["graph_valid_mask"].copy(), **fields)


def real_td_candidates(source):
    a = source["arrays"]
    receiver = a["graph_receiver"]
    owners = np.full(len(receiver), -1, np.int64)
    length = np.zeros(len(receiver), np.int64)
    columns = a["elevation_m"].shape[1]
    rows = len(receiver) // columns
    for cell in a["graph_order_downstream_first"]:
        target = receiver[cell]
        owners[cell] = int(cell) if target < 0 else owners[target]
        r, c = divmod(int(cell), columns)
        if 2 <= r < rows - 2 and 2 <= c < columns - 2 and target >= 0:
            length[cell] = length[target] + 1
    starts = np.argsort(-length, kind="stable")[:200]
    for start in starts:
        selected = [int(start)]
        while len(selected) < 4 and length[selected[-1]] > 1:
            selected.append(int(receiver[selected[-1]]))
        if len(selected) < 4:
            continue
        yield np.asarray(selected, np.int64), owners.reshape(a["elevation_m"].shape)


def verify(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cases, artifacts, products = {}, {}, {}

    def save(name, product):
        path = output / (name + ".npz")
        save_channel_geometry(path, product)
        pin = {"path": path.name, "sha256": file_sha256(path),
               "identity_sha256": product["identity_sha256"]}
        load_channel_geometry(path, expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
        artifacts[name] = pin
        cases[name] = mesh_evidence(product) | shape_evidence(product)
        products[name] = product

    for name in ("single", "turn", "acute", "y", "lake"):
        for label, spacing in (("coarse", 1.), ("fine", .5)):
            terrain, ids, receiver, keywords = fixture(name, spacing)
            save(name + "_" + label, build_channel_geometry(terrain, ids, receiver, **keywords))
        coarse, fine = cases[name + "_coarse"], cases[name + "_fine"]
        difference = abs(coarse["represented_cut_volume_m3"] - fine["represented_cut_volume_m3"]) / max(
            fine["represented_cut_volume_m3"], 1e-12)
        if difference > .02:
            raise AssertionError((name, "spatial volume refinement", difference))
        coarse["spatial_volume_refinement_relative"] = difference

    terrain, ids, receiver, keywords = fixture("single")
    rejected = {}
    for reason in ("unknown", "owner_divide", "underresolved"):
        trial = dict(keywords)
        if reason == "unknown":
            valid = terrain.valid_mask.copy()
            valid[3, 4] = False
            test_terrain = TerrainGrid(terrain.elevation_m.copy(), valid, 0., 0., 10., 10.,
                                       "generated_terrain", "unknown_fixture", "a" * 64)
        else:
            test_terrain = terrain
        if reason == "owner_divide":
            owner = keywords["owner_grid"].copy()
            owner[:, 5:] = 2
            trial["owner_grid"] = owner
        if reason == "underresolved":
            trial["width_m"] = np.full(len(ids), .1)
        try:
            build_channel_geometry(test_terrain, ids, receiver, **trial)
        except ValueError as error:
            rejected[reason] = str(error)
        else:
            raise AssertionError("missing geometry rejection: " + reason)

    source = load_diagnostic_product(TD_DIRECTORY / "product.npz", expected_sha256=TD_PRODUCT_SHA,
                                     expected_identity=TD_PRODUCT_ID)
    td = terrain_from_product(source)
    failures = []
    for ids, owners in real_td_candidates(source):
        rec = np.r_[np.arange(1, len(ids)), -1].astype(np.int64)
        selected_owner = int(owners.flat[ids[0]])
        args = {"width_m": np.full(len(ids), 6.), "depth_m": np.full(len(ids), .25),
                "owner_grid": owners, "corridor_mask": owners == selected_owner,
                "lake_mask": np.zeros(td.elevation_m.shape, bool),
                "anchor_mask": np.zeros(len(ids), bool)}
        try:
            coarse = build_channel_geometry(td, ids, rec, config=GeometryConfig(fine_spacing_m=.5), **args)
            fine = build_channel_geometry(td, ids, rec, config=GeometryConfig(fine_spacing_m=.25), **args)
        except ValueError as error:
            failures.append({"cell_ids": ids.tolist(), "reason": str(error)})
            continue
        save("td_coarse", coarse)
        save("td_fine", fine)
        break
    else:
        raise AssertionError({"no_accepted_original_TD_reach": failures})
    difference = abs(cases["td_coarse"]["represented_cut_volume_m3"] - cases["td_fine"]["represented_cut_volume_m3"]) / cases["td_fine"]["represented_cut_volume_m3"]
    if difference > .02:
        raise AssertionError(("TD spatial refinement", difference))
    bend_ids = np.array([833902, 834926, 835950, 836973], np.int64)
    bend_receiver = np.array([1, 2, 3, -1], np.int64)
    bend_args = {"width_m": np.full(4, 6.), "depth_m": np.full(4, .25),
                 "owner_grid": owners, "corridor_mask": owners == int(owners.flat[bend_ids[0]]),
                 "lake_mask": np.zeros(td.elevation_m.shape, bool), "anchor_mask": np.zeros(4, bool)}
    for label, spacing in (("coarse", .5), ("fine", .25)):
        save("td_bend_" + label, build_channel_geometry(td, bend_ids, bend_receiver,
             config=GeometryConfig(fine_spacing_m=spacing), **bend_args))
    bend_difference = abs(cases["td_bend_coarse"]["represented_cut_volume_m3"]
                          - cases["td_bend_fine"]["represented_cut_volume_m3"]) / cases["td_bend_fine"]["represented_cut_volume_m3"]
    if bend_difference > .02 or cases["td_bend_fine"]["max_candidate_turn_degrees"] >= cases["td_bend_fine"]["max_original_turn_degrees"]:
        raise AssertionError(("TD bend refinement or turn improvement", bend_difference))
    pool_source_path = ROOT / "verification/td-river-milestones/td256-20261008-01/product.npz"
    pool_source = load_diagnostic_product(pool_source_path,
        expected_sha256="01e7db47838aafe6028f39520895ce8f758ce3d8989e4564822bdee3388677e5",
        expected_identity="d485a50daded18e08db222cd07b4c23435aceb48f7007a3e3782d3367f863d42")
    hierarchy_path = ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz"
    hierarchy = load_basin_hierarchy(hierarchy_path,
        expected_sha256="36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
        expected_identity="cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998")
    pool_terrain = terrain_from_product(pool_source)
    pool_owners = hierarchy["arrays"]["contribution_owner"].astype(np.int64)
    pool_mask = np.zeros(pool_terrain.elevation_m.shape, bool)
    pool_mask.ravel()[[62905, 62906, 63160, 63161, 63162]] = True
    for label, spacing in (("coarse", .25), ("fine", .125)):
        result = build_channel_geometry(pool_terrain, np.array([62648, 62905], np.int64),
            np.array([1, -1], np.int64), np.full(2, 6.), np.full(2, .25),
            owner_grid=pool_owners, corridor_mask=pool_owners == 8, lake_mask=pool_mask,
            anchor_mask=np.zeros(2, bool), config=GeometryConfig(fine_spacing_m=spacing),
            lake_stage_m=1347.1527099609375)
        save("td_lake_" + label, result)
    lake_difference = abs(cases["td_lake_coarse"]["represented_cut_volume_m3"]
                          - cases["td_lake_fine"]["represented_cut_volume_m3"]) / cases["td_lake_fine"]["represented_cut_volume_m3"]
    if lake_difference > .02:
        raise AssertionError(("TD lake spatial refinement", lake_difference))
    export_glb(products["td_fine"], output / "td-river-bed.glb")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    for axis, name in zip(axes, ("turn_fine", "y_fine", "td_bend_fine")):
        a = products[name]["arrays"]
        axis.tripcolor(a["vertices_xz_m"][:, 0], a["vertices_xz_m"][:, 1], a["triangles"],
                       a["cut_depth_m"], cmap="Blues", shading="gouraud")
        for i, j in enumerate(a["receiver"]):
            if j >= 0:
                before, after = a["original_node_xz_m"][[i, j]], a["node_xz_m"][[i, j]]
                axis.plot(before[:, 0], before[:, 1], color="#ad6f30", linestyle="--", linewidth=1.)
                axis.plot(after[:, 0], after[:, 1], color="#237947", linewidth=1.4)
        axis.set_title(name + " | original / constrained centerline")
        axis.set_aspect("equal")
        axis.set_xlabel("X (m)")
        axis.set_ylabel("Z (m)")
        axis.ticklabel_format(useOffset=False, style="plain")
        axis.xaxis.set_major_locator(MaxNLocator(3))
        axis.tick_params(axis="x", labelrotation=25, labelsize=8)
    fig.suptitle("M5 shared bed field; cut depth, not instantaneous water surface")
    fig.tight_layout()
    fig.savefig(output / "geometry-preview.png", dpi=160)
    plt.close(fig)
    report = {"schema": "td-river-m5-verification-v1", "status": "accepted_bounded_geometry",
              "artifacts": artifacts, "cases": cases, "rejections": rejected,
              "td_rejected_candidates": failures, "td_spatial_refinement_relative": difference,
              "td_bend_spatial_refinement_relative": bend_difference,
              "td_lake_spatial_refinement_relative": lake_difference,
              "td_lake_source": {"path": str(pool_source_path),
                  "sha256": "01e7db47838aafe6028f39520895ce8f758ce3d8989e4564822bdee3388677e5",
                  "identity_sha256": pool_source["identity_sha256"], "hierarchy_path": str(hierarchy_path),
                  "hierarchy_sha256": "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
                  "hierarchy_identity_sha256": hierarchy["identity_sha256"], "leaf_node": 8,
                  "lake_support_cell_ids": [62905, 62906, 63160, 63161, 63162],
                  "stage_policy": "first_saddle_stage_original_wet_support_no_natural_merger_claim"},
              "td_source": {"path": str(TD_DIRECTORY / "product.npz"), "sha256": TD_PRODUCT_SHA,
                            "identity_sha256": TD_PRODUCT_ID, "source_identity_sha256": td.identity_sha256,
                            "source_sha256": td.source_sha256},
              "limitations": ["bounded_selected_reach_not_all_1024_centerlines", "uncalibrated_sections",
                              "represented_PL_geometry_not_unsampled_envelope", "no_natural_lake_merging"],
              "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    publish_bytes(output / "acceptance.json", json.dumps(report, indent=2, allow_nan=False).encode("utf-8"))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = verify(arguments.output)
    print(json.dumps({"status": result["status"], "cases": len(result["artifacts"]),
                      "td_spatial_refinement_relative": result["td_spatial_refinement_relative"]}, indent=2))


if __name__ == "__main__":
    main()
