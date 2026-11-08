"""Read-only tributary bed and source-identical weighted wet support points."""

import numpy as np

from terrain_pipeline.mountain_manning_storage import validate_manning_storage
from terrain_pipeline.mountain_source_adapter import identity
from terrain_pipeline.rainfall_runoff import _hash


MAX_DISPLAY_STATES = 100


def export_manning_mesh(record, saved, geometry):
    validate_manning_storage(saved, record, geometry)
    source = record["arrays"]
    state = saved["arrays"]
    count = state["stage_m"].shape[0]
    peak = int(state["storage_m3"].sum(axis=1).argmax())
    indices = np.unique(np.r_[np.linspace(0, count - 1, min(97, count)).astype(np.int64), peak])
    rows, columns = source["H2_m"].shape
    grid = np.arange(rows * columns, dtype=np.int64).reshape(rows, columns)
    lower_left, lower_right = grid[:-1, :-1].ravel(), grid[:-1, 1:].ravel()
    upper_left, upper_right = grid[1:, :-1].ravel(), grid[1:, 1:].ravel()
    triangles = np.concatenate((np.column_stack((lower_left, lower_right, upper_right)),
                                np.column_stack((lower_left, upper_right, upper_left))))
    original = np.column_stack((source["world_x_m"].ravel(), source["H0_m"].ravel(), source["world_z_m"].ravel()))
    bed = original.copy()
    bed[:, 1] = source["H2_m"].ravel()
    origin = np.array([original[0, 0], original[:, 1].min(), original[0, 2]])
    owner = np.repeat(source["row_owner"], columns)
    depth = np.maximum(state["stage_m"][indices][:, owner] - bed[None, :, 1], 0.)
    weights = source["support_area_m2"].ravel()
    volume = depth @ weights
    selected_flux = np.zeros((indices.size, 4))
    positive = indices > 0
    selected_flux[positive] = state["qedges_m3_s"][indices[positive] - 1]
    mesh = {"arrays": {"origin_world_xyz_m": origin,
        "vertices_H0_local_xyz_m": original - origin, "vertices_H2_local_xyz_m": bed - origin,
        "triangles": triangles, "shared_section_vertex_ids": grid[[0, 30, 60, 90]],
        "support_owner": owner, "support_area_m2": weights,
        "saved_state_indices": indices, "time_s": indices.astype(np.float64) * saved["metadata"]["dt_s"],
        "water_depth_m": depth, "wet_mask": depth > 0., "water_volume_m3": volume,
        "solver_volume_m3": state["storage_m3"][indices].sum(axis=1),
        "display_volume_difference_m3": volume - state["storage_m3"][indices].sum(axis=1),
        "qedges_m3_s": selected_flux},
        "metadata": {"schema": "mountain-manning-weighted-wet-support-mesh-v1",
            "geometry_identity": identity(record["arrays"], record["metadata"]),
            "saved_stage_sha256": _hash(state["stage_m"]),
            "source_binding": record["metadata"]["source_binding"],
            "state_count": int(indices.size), "full_committed_state_count": count,
            "peak_saved_state": peak, "failure": saved["metadata"]["failure"],
            "water_representation": "weighted_discrete_wet_support_points_not_interpolated_triangle_water_surface",
            "scope": "offline_A_release_replay_engineering_diffusive_prescribed_tailwater_not_natural_outlet",
            "display_sampling": "at_most_98_saved_states_including_initial_last_storage_peak_no_new_time_interpolation"}}
    validate_manning_mesh(mesh, record, saved, geometry)
    return mesh


def validate_manning_mesh(mesh, record, saved, geometry):
    validate_manning_storage(saved, record, geometry)
    arrays, meta = mesh["arrays"], mesh["metadata"]
    source, state = record["arrays"], saved["arrays"]
    if set(arrays) != {"origin_world_xyz_m", "vertices_H0_local_xyz_m", "vertices_H2_local_xyz_m", "triangles",
        "shared_section_vertex_ids", "support_owner", "support_area_m2", "saved_state_indices", "time_s",
        "water_depth_m", "wet_mask", "water_volume_m3", "solver_volume_m3", "display_volume_difference_m3", "qedges_m3_s"}:
        raise ValueError("exact Manning mesh schema")
    if meta["geometry_identity"] != identity(source, record["metadata"]) or meta["saved_stage_sha256"] != _hash(state["stage_m"]):
        raise ValueError("Manning mesh source identity")
    indices = arrays["saved_state_indices"]
    if indices.dtype != np.int64 or indices.ndim != 1 or not 1 <= indices.size <= MAX_DISPLAY_STATES:
        raise ValueError("Manning mesh display resource budget")
    if indices[0] != 0 or indices[-1] != state["stage_m"].shape[0] - 1 or (np.diff(indices) <= 0).any():
        raise ValueError("Manning mesh saved state selection")
    shapes = {"origin_world_xyz_m": (3,), "vertices_H0_local_xyz_m": (1001, 3), "vertices_H2_local_xyz_m": (1001, 3),
        "triangles": (1800, 3), "shared_section_vertex_ids": (4, 11), "support_owner": (1001,),
        "support_area_m2": (1001,), "saved_state_indices": (indices.size,), "time_s": (indices.size,),
        "water_depth_m": (indices.size, 1001), "wet_mask": (indices.size, 1001),
        "water_volume_m3": (indices.size,), "solver_volume_m3": (indices.size,),
        "display_volume_difference_m3": (indices.size,), "qedges_m3_s": (indices.size, 4)}
    for key, shape in shapes.items():
        value = arrays[key]
        dtype = np.dtype("bool" if key == "wet_mask" else "int64" if key in
            ("triangles", "shared_section_vertex_ids", "support_owner", "saved_state_indices") else "float64")
        if value.shape != shape or value.dtype != dtype or not np.isfinite(value).all():
            raise ValueError("Manning mesh exact shape/dtype/finite: " + key)
    peak = int(state["storage_m3"].sum(axis=1).argmax())
    if (meta["schema"] != "mountain-manning-weighted-wet-support-mesh-v1" or meta["state_count"] != indices.size
            or meta["full_committed_state_count"] != state["stage_m"].shape[0] or meta["peak_saved_state"] != peak
            or peak not in indices or meta["failure"] != saved["metadata"]["failure"]):
        raise ValueError("Manning mesh status/peak identity")
    grid = np.arange(1001, dtype=np.int64).reshape(91, 11)
    expected_triangles = np.concatenate((np.column_stack((grid[:-1, :-1].ravel(), grid[:-1, 1:].ravel(), grid[1:, 1:].ravel())),
                                        np.column_stack((grid[:-1, :-1].ravel(), grid[1:, 1:].ravel(), grid[1:, :-1].ravel()))))
    if not np.array_equal(arrays["triangles"], expected_triangles) or not np.array_equal(arrays["shared_section_vertex_ids"], grid[[0, 30, 60, 90]]):
        raise ValueError("Manning mesh fixed triangles/shared IDs")
    for key in ("H0", "H2"):
        world = arrays[f"vertices_{key}_local_xyz_m"] + arrays["origin_world_xyz_m"]
        expected = np.column_stack((source["world_x_m"].ravel(), source[key + "_m"].ravel(), source["world_z_m"].ravel()))
        if not np.allclose(world, expected, atol=1e-10, rtol=0):
            raise ValueError("Manning mesh coordinate forgery")
    triangles = arrays["triangles"]
    bed = arrays["vertices_H2_local_xyz_m"]
    if triangles.dtype != np.int64 or triangles.shape != (1800, 3) or (triangles < 0).any() or (triangles >= 1001).any():
        raise ValueError("Manning mesh triangle schema")
    normals = np.cross(bed[triangles[:, 1]] - bed[triangles[:, 0]], bed[triangles[:, 2]] - bed[triangles[:, 0]])
    if (normals[:, 1] <= 0).any():
        raise ValueError("Manning mesh winding")
    edges = np.sort(np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]])), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    if (counts > 2).any() or np.count_nonzero(counts == 1) != 200 or 1001 - counts.size + 1800 != 1:
        raise ValueError("Manning mesh topology")
    expected_owner = np.repeat(source["row_owner"], 11)
    if not np.array_equal(arrays["support_owner"], expected_owner) or not np.array_equal(arrays["support_area_m2"], source["support_area_m2"].ravel()):
        raise ValueError("Manning mesh support provenance")
    depth = np.maximum(state["stage_m"][indices][:, expected_owner] - source["H2_m"].ravel(), 0.)
    if not np.array_equal(arrays["water_depth_m"], depth) or not np.array_equal(arrays["wet_mask"], depth > 0):
        raise ValueError("Manning mesh water provenance")
    volume = depth @ source["support_area_m2"].ravel()
    if not np.allclose(volume, state["storage_m3"][indices].sum(axis=1), atol=1e-8, rtol=0):
        raise ValueError("Manning mesh V(h) mismatch")
    if not np.array_equal(arrays["water_volume_m3"], volume) or not np.array_equal(arrays["time_s"], indices * saved["metadata"]["dt_s"]):
        raise ValueError("Manning mesh volume/time forgery")
    expected_volume = state["storage_m3"][indices].sum(axis=1)
    expected_flux = np.zeros((indices.size, 4))
    positive = indices > 0
    expected_flux[positive] = state["qedges_m3_s"][indices[positive] - 1]
    if not np.array_equal(arrays["solver_volume_m3"], expected_volume) or not np.array_equal(arrays["display_volume_difference_m3"], volume - expected_volume) or not np.array_equal(arrays["qedges_m3_s"], expected_flux):
        raise ValueError("Manning mesh saved volume/flux mismatch")
    return {"boundary_edges": 200, "Euler": 1, "minimum_normal_Y": float(normals[:, 1].min()),
            "max_display_volume_error_m3": float(np.abs(volume - state["storage_m3"][indices].sum(axis=1)).max())}
