"""Independent raw-array audit of a pinned single-domain native surface package."""

import argparse
from collections import deque
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.rainfall_runoff import _strict_json
from tools.audit_td_candidate_coupling import read_record

ACCEPTANCE_SHA256 = "c7da55e59be8d9d91fc81c45f17a0c6421848b06fafe215fc268608b1b00a24f"
STATES = ("depth_m", "soil_mm", "fast_mm", "slow_mm")
FLUX = ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s",
        "routed_volume_m3", "wet_duration_s")
MAX_BYTES = 1024 ** 3


def read_json(record):
    path = Path(record["path"]).resolve(strict=True)
    if path.stat().st_size > 8 * 1024 ** 2 or file_sha256(path) != record["expected_sha256"]:
        raise ValueError("independent JSON external pin/budget mismatch")
    value = _strict_json(path.read_text(encoding="utf-8"))
    if file_sha256(path) != record["expected_sha256"]:
        raise ValueError("JSON changed during audit")
    return value


def near(actual, expected, *, absolute=1e-7, relative=1e-10):
    actual, expected = np.asarray(actual), np.asarray(expected)
    if (actual.shape != expected.shape or not np.isfinite(actual).all()
            or not np.isfinite(expected).all()
            or np.any(abs(actual - expected) > absolute + relative * abs(expected))):
        raise ValueError("independent numeric mismatch")


def check_geometry(arrays, metadata, hierarchy, hierarchy_metadata, hierarchy_record):
    shape = hierarchy["height_m"].shape
    valid = hierarchy["valid_mask"].ravel()
    if metadata.get("schema") != "single-domain-native-surface-geometry-v1":
        raise ValueError("independent geometry schema mismatch")
    if (metadata["hierarchy_identity"] != hierarchy_record["expected_identity"]
            or metadata["source_hierarchy_sha256"] != hierarchy_record["expected_sha256"]
            or metadata["grid_shape"] != list(shape)
            or metadata["source_identity"] != hierarchy_metadata["source_identity_sha256"]):
        raise ValueError("independent geometry lineage mismatch")
    for key in ("spacing_m", "origin_m_xz"):
        if metadata[key] != hierarchy_metadata[key]:
            raise ValueError("independent geometry coordinates mismatch")
    for key in ("height_m", "valid_mask", "receiver", "face_cells", "boundary_cells"):
        np.testing.assert_array_equal(arrays[key], hierarchy[key])
    ids = np.flatnonzero(valid)
    receiver = hierarchy["receiver"]
    sources = ids[receiver[ids] >= 0]
    targets = receiver[sources]
    if (np.any(targets >= valid.size) or not valid[targets].all()
            or np.any(abs(sources // shape[1] - targets // shape[1])
                      + abs(sources % shape[1] - targets % shape[1]) != 1)):
        raise ValueError("independent receiver D4/coverage mismatch")
    incoming = np.bincount(targets, minlength=valid.size)
    queue = deque(ids[incoming[ids] == 0].tolist())
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        target = receiver[node]
        if target >= 0:
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(int(target))
    if visited != len(ids):
        raise ValueError("independent receiver cycle")
    expected_faces = set()
    for cell in ids:
        row, column = divmod(int(cell), shape[1])
        for other in (cell + 1 if column + 1 < shape[1] else -1,
                      cell + shape[1] if row + 1 < shape[0] else -1):
            if other >= 0 and valid[other]:
                expected_faces.add((int(cell), int(other)))
    faces = arrays["face_cells"]
    if len(faces) != len(expected_faces) or set(map(tuple, faces.tolist())) != expected_faces:
        raise ValueError("independent shared faces incomplete/duplicated")
    origin, spacing = metadata["origin_m_xz"], metadata["spacing_m"]
    xyz = np.column_stack((origin[0] + ids % shape[1] * spacing,
                           hierarchy["height_m"].ravel()[ids],
                           origin[1] + ids // shape[1] * spacing))
    np.testing.assert_array_equal(arrays["node_cell_ids"], ids)
    np.testing.assert_array_equal(arrays["node_xyz_m"], xyz)
    np.testing.assert_array_equal(ids[arrays["edge_node_indices"]], np.column_stack((sources, targets)))
    boundary = np.isin(ids, hierarchy["boundary_cells"])
    np.testing.assert_array_equal(arrays["node_engineering_boundary"], boundary)
    np.testing.assert_array_equal(arrays["node_internal_sink"], (receiver[ids] < 0) & ~boundary)
    uphill = np.zeros(len(ids), bool)
    uphill[receiver[ids] >= 0] = hierarchy["height_m"].ravel()[targets] > hierarchy["height_m"].ravel()[sources]
    np.testing.assert_array_equal(arrays["node_receiver_uphill"], uphill)
    corners = arrays["bed_vertices_xyz_m"].reshape(len(ids), 4, 3)
    near(corners[:, :, 1], np.repeat(xyz[:, 1, None], 4, axis=1), absolute=0, relative=0)
    offsets = corners[:, :, (0, 2)] - xyz[:, None, (0, 2)]
    expected_offsets = np.array([[-.5, -.5], [-.5, .5], [.5, .5], [.5, -.5]]) * spacing
    near(offsets, np.broadcast_to(expected_offsets, offsets.shape), absolute=1e-10, relative=0)
    check_quad_triangles(arrays["bed_triangles"], len(ids))
    for flag in ("hydraulic_ready", "natural_outlet_verified", "publishable", "candidate_bed_used", "continuous_surface"):
        if metadata.get(flag) is not False:
            raise ValueError("unsupported independent geometry scope")
    return dict(valid_cells=len(ids), static_edges=len(sources), unique_d4_faces=len(faces),
                shared_junction_xyz_exact=True, nodes_acyclic=True,
                original_bed_uphill_edges=int(np.count_nonzero(xyz[arrays["edge_node_indices"][:, 1], 1]
                                                               > xyz[arrays["edge_node_indices"][:, 0], 1])),
                engineering_boundary_cells=len(arrays["boundary_cells"]))


def check_quad_triangles(triangles, cells):
    corners = np.arange(cells * 4).reshape(-1, 4)
    np.testing.assert_array_equal(triangles[::2], corners[:, (0, 1, 2)])
    np.testing.assert_array_equal(triangles[1::2], corners[:, (0, 2, 3)])
    if triangles.shape != (cells * 2, 3):
        raise ValueError("independent quad triangle count mismatch")


def check_frame(arrays, metadata, geometry, geometry_metadata, declaration, page, page_metadata, geometry_record):
    if metadata.get("schema") != "single-domain-saved-water-frame-v1":
        raise ValueError("independent frame schema mismatch")
    if (metadata["geometry_identity"] != geometry_record["expected_identity"]
            or metadata["geometry_metadata"] != geometry_metadata
            or metadata["source_page_identity"] != declaration["source_page"]["expected_identity"]
            or metadata["source_page_sha256"] != declaration["source_page"]["expected_sha256"]
            or metadata["forcing_identity"] != page_metadata["forcing_identity"]
            or metadata["state_index"] != declaration["state_index"]
            or metadata["time_s"] != declaration["time_s"]):
        raise ValueError("independent frame provenance/time mismatch")
    for key, value in geometry.items():
        np.testing.assert_array_equal(arrays[key], value)
    ids = geometry["node_cell_ids"]
    depths = page["depth_m"][declaration["state_index"], ids]
    np.testing.assert_array_equal(arrays["native_depth_m"], depths)
    wet = ids[depths > 0]
    np.testing.assert_array_equal(arrays["wet_cell_ids"], wet)
    vertices = arrays["water_vertices_xyz_m"].reshape(len(wet), 4, 3)
    bed_corners = geometry["bed_vertices_xyz_m"].reshape(len(ids), 4, 3)[depths > 0]
    np.testing.assert_array_equal(vertices[:, :, (0, 2)], bed_corners[:, :, (0, 2)])
    expected_levels = page["height_m"].ravel()[wet] + depths[depths > 0]
    np.testing.assert_array_equal(vertices[:, :, 1], np.repeat(expected_levels[:, None], 4, axis=1))
    check_quad_triangles(arrays["water_triangles"], len(wet))
    xyz = arrays["water_vertices_xyz_m"][arrays["water_triangles"]]
    normals = np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0])
    if np.any(normals[:, 1] <= 0):
        raise ValueError("independent water triangle winding invalid")
    areas = normals[:, 1] / 2
    triangle_volume = math.fsum((areas * np.repeat(depths[depths > 0], 2)).tolist())
    raster_volume = math.fsum(depths.tolist()) * geometry_metadata["spacing_m"] ** 2
    near(np.asarray(triangle_volume), np.asarray(raster_volume), absolute=1e-7)
    near(np.asarray(metadata["raster_volume_m3"]), np.asarray(raster_volume))
    near(np.asarray(metadata["triangulated_support_volume_m3"]), np.asarray(triangle_volume))
    if (metadata["wet_cell_count"] != len(wet) or metadata["represented_wet_cell_count"] != len(wet)
            or metadata["omitted_wet_cell_count"] != 0 or metadata["omitted_wet_volume_m3"] != 0):
        raise ValueError("independent wet coverage mismatch")
    shape = page["height_m"].shape
    wet_mask = np.zeros(page["height_m"].size, bool)
    wet_mask[wet] = True
    exposed = []
    for number, cell in enumerate(wet):
        row, column = divmod(int(cell), shape[1])
        others = (cell-1 if column else -1, cell+shape[1] if row+1 < shape[0] else -1,
                  cell+1 if column+1 < shape[1] else -1, cell-shape[1] if row else -1)
        for side, other in enumerate(others):
            if other < 0 or not wet_mask[other]:
                exposed.append((number, side))
    walls = arrays["support_side_vertices_xyz_m"].reshape(len(exposed), 4, 3)
    for number, (cell_index, side) in enumerate(exposed):
        a, b = vertices[cell_index, side], vertices[cell_index, (side+1) % 4]
        expected = np.asarray([a, b, b, a]).copy()
        expected[2:, 1] = page["height_m"].ravel()[wet[cell_index]]
        np.testing.assert_array_equal(walls[number], expected)
    check_quad_triangles(arrays["support_side_triangles"], len(exposed))
    for flag in ("hydraulic_ready", "natural_outlet_verified", "publishable", "water_generated",
                 "candidate_bed_used", "continuous_surface"):
        if metadata.get(flag) is not False:
            raise ValueError("unsupported independent frame scope")
    return dict(frame=declaration["frame"], time_s=declaration["time_s"], wet_cells=len(wet),
                omitted_wet_cells=0, raster_volume_m3=raster_volume,
                triangle_volume_m3=triangle_volume, volume_difference_m3=triangle_volume-raster_volume,
                full_native_sample_match=True, support_perimeter_segments=len(exposed))


def check_hour(arrays, metadata, checkpoint, checkpoint_metadata, previous, rain, hierarchy, hierarchy_identity):
    cells = arrays["height_m"].size
    area = metadata["spacing_m"] ** 2
    if (metadata["hierarchy_identity"] != hierarchy_identity or metadata["substep_s"] != .625
            or checkpoint_metadata["hierarchy_identity"] != hierarchy_identity
            or checkpoint_metadata["forcing_identity"] != metadata["forcing_identity"]):
        raise ValueError("independent hour metadata mismatch")
    for key in ("height_m", "valid_mask", "receiver", "face_cells", "boundary_cells"):
        np.testing.assert_array_equal(arrays[key], hierarchy[key])
    np.testing.assert_array_equal(arrays["rain_mm_h"][0], rain.ravel())
    near(arrays["rain_volume_m3"][0], rain.ravel() * area / 1000)
    for key in STATES:
        expected_initial = np.where(arrays["valid_mask"].ravel(), 30. if key == "soil_mm" else 0., 0.) if previous is None else previous[key]
        np.testing.assert_array_equal(arrays[key][0], expected_initial)
        np.testing.assert_array_equal(arrays[key][1], checkpoint[key])
    for key in FLUX:
        total = arrays[key] if previous is None else previous["cumulative_"+key] + arrays[key]
        np.testing.assert_array_equal(checkpoint["cumulative_"+key], total)
    faces = arrays["face_cells"]
    signed = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    divergence = np.zeros(cells)
    np.add.at(divergence, faces[:, 0], -signed)
    np.add.at(divergence, faces[:, 1], signed)
    near(divergence, arrays["internal_net_m3"][0])
    soil_change = np.diff(arrays["soil_mm"], axis=0)[0] * area / 1000
    pool_change = np.diff(arrays["fast_mm"] + arrays["slow_mm"], axis=0)[0] * area / 1000
    surface_change = np.diff(arrays["depth_m"], axis=0)[0] * area
    ledger = lambda key: arrays[key][0]
    near(soil_change, ledger("rain_infiltration_m3") + ledger("surface_infiltration_m3")
         - ledger("soil_et_m3") - ledger("percolation_m3"))
    near(pool_change, ledger("rain_excess_m3") + ledger("percolation_m3") - ledger("local_release_m3"))
    near(surface_change, ledger("local_release_m3") - ledger("surface_infiltration_m3")
         - ledger("surface_et_m3") + divergence - ledger("boundary_outflow_m3"))
    initial = arrays["depth_m"][0] * area + sum(arrays[key][0] for key in STATES[1:]) * area / 1000
    final = arrays["depth_m"][1] * area + sum(arrays[key][1] for key in STATES[1:]) * area / 1000
    residual = ledger("rain_volume_m3") + divergence - ledger("soil_et_m3") - ledger("surface_et_m3") - ledger("boundary_outflow_m3") - (final-initial)
    near(residual, np.zeros(cells), absolute=1e-6)
    routed = np.zeros(cells)
    for first, second, volumes in ((faces[:, 0], faces[:, 1], arrays["face_forward_m3"]),
                                  (faces[:, 1], faces[:, 0], arrays["face_reverse_m3"])):
        follows = arrays["receiver"][first] == second
        np.add.at(routed, first[follows], volumes[follows])
    near(routed, arrays["routed_volume_m3"])
    return dict(initial_m3=math.fsum(initial.tolist()), final_m3=math.fsum(final.tolist()),
                rain_m3=math.fsum(ledger("rain_volume_m3").tolist()),
                loss_m3=math.fsum((ledger("soil_et_m3") + ledger("surface_et_m3")).tolist()),
                export_m3=math.fsum(ledger("boundary_outflow_m3").tolist()),
                max_cell_residual_m3=float(abs(residual).max(initial=0)),
                absolute_cell_residual_sum_m3=math.fsum(abs(residual).tolist()),
                signed_cell_residual_sum_m3=math.fsum(residual.tolist()),
                gross_forward_m3=math.fsum(arrays["face_forward_m3"].tolist()),
                gross_reverse_m3=math.fsum(arrays["face_reverse_m3"].tolist()),
                reverse_active_faces=int(np.count_nonzero(arrays["face_reverse_m3"] > 0)))


def audit(index_record, output):
    started = time.monotonic()
    index = read_json(index_record)
    if index.get("schema") != "single-domain-surface-index-v1" or set(index["directions"]) != {"eastward", "westward"}:
        raise ValueError("independent complete index schema mismatch")
    if index["acceptance_record"]["expected_sha256"] != ACCEPTANCE_SHA256:
        raise ValueError("independent trusted acceptance required")
    accepted = read_json(index["acceptance_record"])
    if not accepted["all_saved_numerical_gates_passed"] or not accepted["io_chain_accepted"]:
        raise ValueError("independent temporal evidence rejected")
    execution = read_json(accepted["run_records"]["index"])
    if index["source_records"] != accepted["source_records"]:
        raise ValueError("independent accepted source records mismatch")
    for flag in ("hydraulic_ready", "natural_outlet_verified", "publishable"):
        if index.get(flag) is not False:
            raise ValueError("independent unsupported index certification")
    report = read_json(index["report"])
    resource = read_json(index["resource"])
    if (report["schema"] != "single-domain-surface-report-v1"
            or resource["schema"] != "single-domain-surface-resource-v1"
            or resource["complete"] is not True):
        raise ValueError("independent report/resource mismatch")
    for key in ("directions", "acceptance_record", "source_records", "code_sha256"):
        if report[key] != index[key]:
            raise ValueError("independent report/index declaration mismatch")
    observed = [index_record, index["acceptance_record"], accepted["run_records"]["index"],
                index["report"], index["resource"]]
    published_root = Path(index_record["path"]).resolve().parent
    expected_artifacts = [index["report"], *report.get("sample_records", [])]
    for group in index["directions"].values():
        expected_artifacts.extend([group["geometry"], *(frame["water_frame"] for frame in group["frames"])])
    if sorted(resource["artifact_records"], key=lambda pin: pin["path"]) != sorted(expected_artifacts, key=lambda pin: pin["path"]):
        raise ValueError("independent artifact inventory mismatch")
    output_bytes = 0
    for pin in resource["artifact_records"]:
        target = Path(pin["path"]).resolve(strict=True)
        if not target.is_relative_to(published_root):
            raise ValueError("independent derived artifact outside published root")
        output_bytes += target.stat().st_size
        observed.append(pin)
    if output_bytes != resource["output_bytes"] or output_bytes > 2*MAX_BYTES:
        raise ValueError("independent output budget mismatch")
    for name, digest in index["code_sha256"].items():
        target = (ROOT / name).resolve(strict=True)
        if not target.is_relative_to(ROOT) or file_sha256(target) != digest:
            raise ValueError("independent pinned implementation changed")
        observed.append(dict(path=str(target), expected_sha256=digest))
    hierarchy_record = accepted["source_records"]["hierarchy"]
    observed.append(hierarchy_record)
    hierarchy, hmeta = read_record(hierarchy_record)
    directions = {}
    snapshots = {}
    for direction in ("eastward", "westward"):
        group = index["directions"][direction]
        geometry, gmeta = read_record(group["geometry"])
        geometry_audit = check_geometry(geometry, gmeta, hierarchy, hmeta, hierarchy_record)
        rain, _ = read_record(accepted["source_records"]["weather_records"][direction])
        observed.append(accepted["source_records"]["weather_records"][direction])
        pages = execution["scenarios"][direction]["pages"]
        if len(pages) != 24 or len(group["frames"]) != 25:
            raise ValueError("independent 24h/25state coverage mismatch")
        previous = None
        hours, frames = [], []
        for hour, source in enumerate(pages):
            page, pmeta = read_record(source["storage"])
            checkpoint, cmeta = read_record(source["checkpoint"])
            observed.extend([source["storage"], source["checkpoint"]])
            if (source["hour"] != hour or pmeta["start_s"] != hour*3600.
                    or pmeta["end_s"] != (hour+1)*3600.
                    or cmeta["last_page_identity"] != source["storage"]["expected_identity"]):
                raise ValueError("independent page/checkpoint sequence mismatch")
            hours.append(check_hour(page, pmeta, checkpoint, cmeta, previous,
                                    rain["rain_mm_h"][hour], hierarchy, hierarchy_record["expected_identity"]))
            for number in ((0, 1) if hour == 0 else (hour+1,)):
                declaration = group["frames"][number]
                if (declaration["frame"] != number or declaration["time_s"] != number*3600.
                        or declaration["source_page"] != source["storage"]
                        or declaration["state_index"] != (0 if number == 0 else 1)):
                    raise ValueError("independent frame selection mismatch")
                frame, fmeta = read_record(declaration["water_frame"])
                frames.append(check_frame(frame, fmeta, geometry, gmeta, declaration,
                                          page, pmeta, group["geometry"]))
                if number in (1, 6, 24):
                    snapshots[(direction, number)] = page["depth_m"][declaration["state_index"]].reshape(page["height_m"].shape).copy()
                del frame
            previous = checkpoint
            del page
            memory = psutil.Process().memory_info()
            if max(getattr(memory, "peak_wset", memory.rss), getattr(memory, "peak_pagefile", 0)) > MAX_BYTES:
                raise MemoryError("independent audit exceeds 1GiB")
        whole = math.fsum([hours[0]["initial_m3"], sum(item["rain_m3"] for item in hours),
                           -sum(item["loss_m3"] for item in hours), -sum(item["export_m3"] for item in hours),
                           -hours[-1]["final_m3"]])
        if abs(whole) > 1e-6 + sum(item["rain_m3"] for item in hours)*1e-10:
            raise ValueError("independent whole-period water budget mismatch")
        directions[direction] = dict(geometry=geometry_audit, hours=hours, frames=frames,
                                     whole_period_residual_m3=whole, full_chain_verified=True)
        del geometry, previous
    output = Path(output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    images = plot_review(hierarchy, hmeta, directions, snapshots, output)
    memory = psutil.Process().memory_info()
    report = dict(schema="single-domain-independent-raw-audit-v1", index_record=index_record,
                  accepted_same_bed_saved_chain=True, directions=directions, images=images,
                  elapsed_s=time.monotonic()-started, peak_rss_bytes=getattr(memory, "peak_wset", memory.rss),
                  peak_private_bytes=getattr(memory, "peak_pagefile", None), solver_advanced=False,
                  hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                  limitations=["Native 30m independent flat cell supports; not continuous fine river banks or water surfaces.",
                               "Reverse shared-face volumes witness local bidirectional exchange, not a controlled tailwater response test.",
                               "Fast/slow releases lack separate saved independent witnesses.",
                               "Official frontend integration and complete stage-1 certification remain open."])
    for record in observed:
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("independent audit source changed")
    publish_bytes(output / "report.json", json.dumps(report, indent=2, allow_nan=False).encode("utf-8"))
    return dict(path=str(output / "report.json"), expected_sha256=file_sha256(output / "report.json"),
                elapsed_s=report["elapsed_s"], peak_rss_bytes=report["peak_rss_bytes"],
                directions={key: dict(frames=len(value["frames"]), residual_m3=value["whole_period_residual_m3"],
                                     omitted_wet_cells=sum(frame["omitted_wet_cells"] for frame in value["frames"]))
                            for key, value in directions.items()}, images=images)


def plot_review(hierarchy, metadata, directions, snapshots, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    height = hierarchy["height_m"]
    spacing = metadata["spacing_m"]
    extent = [-spacing/2000, (height.shape[1]-.5)*spacing/1000,
              (height.shape[0]-.5)*spacing/1000, -spacing/2000]
    figure, axes = plt.subplots(2, 4, figsize=(18, 9), constrained_layout=True)
    for row, direction in enumerate(("eastward", "westward")):
        for column, frame in enumerate((1, 6, 24)):
            depth = snapshots[(direction, frame)]
            image = axes[row, column].imshow(np.ma.masked_where(depth <= 0, depth), extent=extent,
                                             cmap="viridis", interpolation="nearest")
            axes[row, column].set(title=f"{direction}: saved {frame}h depth (m)", xlabel="local X (km)", ylabel="local Z (km)")
            figure.colorbar(image, ax=axes[row, column], shrink=.8)
        frames = directions[direction]["frames"]
        axes[row, 3].plot([frame["time_s"]/3600 for frame in frames],
                         [frame["raster_volume_m3"] for frame in frames], label="all wet cell volume")
        axes[row, 3].set(title=f"{direction}: surface water", xlabel="physical hours", ylabel="m3")
        axes[row, 3].grid(alpha=.25)
    figure.suptitle("Fixed TD 256x256 / 30m | same native bed | no wet-support omissions")
    overview = output / "same-bed-saved-water.png"
    figure.savefig(overview, dpi=130)
    plt.close(figure)

    depth = snapshots[("eastward", 6)]
    center = np.unravel_index(np.argmax(depth), depth.shape)
    lower = (max(0, min(center[0]-24, height.shape[0]-48)), max(0, min(center[1]-24, height.shape[1]-48)))
    rows, columns = np.mgrid[lower[0]:lower[0]+48, lower[1]:lower[1]+48]
    cells = np.column_stack((columns.ravel(), rows.ravel()))
    offsets = np.array([[-.5, -.5], [-.5, .5], [.5, .5], [.5, -.5]])
    xz = (cells[:, None, :] + offsets)*spacing
    bed = height[rows, columns].ravel()
    water_depth = depth[rows, columns].ravel()
    figure = plt.figure(figsize=(11, 8), constrained_layout=True)
    axis = figure.add_subplot(111, projection="3d")
    bed_quads = np.stack((xz[:, :, 0], xz[:, :, 1], np.repeat(bed[:, None], 4, axis=1)), axis=-1)
    axis.add_collection3d(Poly3DCollection(bed_quads, facecolor="#81976b", linewidth=.05, edgecolor="#52644c"))
    wet = water_depth > 0
    water_quads = bed_quads[wet].copy()
    water_quads[:, :, 2] += water_depth[wet, None]
    axis.add_collection3d(Poly3DCollection(water_quads, facecolor="#2bacc1", alpha=.8, linewidth=.05, edgecolor="#146977"))
    axis.set(xlim=(xz[:, :, 0].min(), xz[:, :, 0].max()), ylim=(xz[:, :, 1].min(), xz[:, :, 1].max()),
             zlim=(bed.min(), float((bed+water_depth).max())), xlabel="local X (m)", ylabel="local Z (m)", zlabel="elevation (m)",
             title="Eastward saved 6h | actual 48x48 flat supports | water-level jumps retained")
    axis.set_box_aspect((1, 1, max(.08, float(np.ptp(bed+water_depth))/(48*spacing))))
    axis.view_init(elev=30, azim=-55)
    local = output / "native-support-3d.png"
    figure.savefig(local, dpi=140)
    plt.close(figure)
    return [dict(path=str(path), expected_sha256=file_sha256(path)) for path in (overview, local)]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(dict(path=str(args.index.resolve()), expected_sha256=args.index_sha256), args.output)))
