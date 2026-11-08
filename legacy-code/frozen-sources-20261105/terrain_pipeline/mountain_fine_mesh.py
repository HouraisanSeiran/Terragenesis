"""Read-only original/bed triangles and exact V(h) wet support prisms."""

import numpy as np

from terrain_pipeline.mountain_fine_geometry import validate_fine_chain
from terrain_pipeline.mountain_fine_storage import validate_fine_storage
from terrain_pipeline.mountain_depression_geometry import _hash


def export_fine_mesh(chain, saved, geometry):
    """No solver or geometry preparation: saved water supports retain exact weights."""
    validate_fine_chain(chain, geometry)
    validation = validate_fine_storage(saved, chain, geometry)
    source = chain["arrays"]
    rows, columns = source["H2_m"].shape
    grid = np.arange(rows * columns, dtype=np.int64).reshape(rows, columns)
    lower_left = grid[:-1, :-1].ravel()
    lower_right = grid[:-1, 1:].ravel()
    upper_left = grid[1:, :-1].ravel()
    upper_right = grid[1:, 1:].ravel()
    triangles = np.concatenate((np.column_stack((lower_left, lower_right, upper_right)),
                                np.column_stack((lower_left, upper_right, upper_left))), axis=0)
    origin = np.array([source["world_x_m"].flat[0], float(source["H0_m"].min()), source["world_z_m"].flat[0]])
    original = np.column_stack((source["world_x_m"].ravel(), source["H0_m"].ravel(), source["world_z_m"].ravel()))
    bed = original.copy()
    bed[:, 1] = source["H2_m"].ravel()
    local_bed = bed - origin
    local_original = original - origin
    area2 = np.linalg.norm(np.cross(local_bed[triangles[:, 1]] - local_bed[triangles[:, 0]],
                                   local_bed[triangles[:, 2]] - local_bed[triangles[:, 0]]), axis=1)
    if (area2 <= 0).any():
        raise ValueError("degenerate fine mesh triangle")
    normals = np.cross(local_bed[triangles[:, 1]] - local_bed[triangles[:, 0]],
                       local_bed[triangles[:, 2]] - local_bed[triangles[:, 0]])
    if (normals[:, 1] <= 0).any():
        raise ValueError("bed mesh triangle winding is not upward")
    support = saved["support"]
    row_owner = support["row_owner"]
    owner = np.repeat(row_owner, columns)
    stage = saved["arrays"]["stage_m"][:, owner]
    depth = np.maximum(stage - bed[None, :, 1], 0.)
    weights = source["quadrature_area_m2"].ravel()
    water_volume = depth @ weights
    solver_volume = saved["arrays"]["storage_m3"].sum(axis=1)
    difference = water_volume - solver_volume
    if not np.allclose(difference, 0., rtol=0., atol=1e-8):
        raise ValueError("wet prism support differs from solver V(h)")
    shared_rows = source["shared_node_section_rows"]
    shared_ids = grid[shared_rows].copy()
    return {"arrays": {"origin_world_xyz_m": origin, "vertices_H0_local_xyz_m": local_original,
                       "vertices_H2_local_xyz_m": local_bed, "triangles": triangles,
                       "shared_section_vertex_ids": shared_ids, "support_owner": owner,
                       "support_area_m2": weights, "stage_m": stage, "water_depth_m": depth,
                       "wet_mask": depth > 0., "water_volume_m3": water_volume,
                       "solver_volume_m3": solver_volume, "display_volume_difference_m3": difference,
                       "time_s": np.arange(stage.shape[0], dtype=np.float64) * saved["dt_s"],
                       "qedges_m3_s": saved["arrays"]["qedges_m3_s"].copy(),
                       "ledger_m3": saved["arrays"]["ledger_m3"].copy()},
            "metadata": {"schema": "mountain-fine-wet-support-prisms-v1",
                         "source_binding": geometry["metadata"]["source_binding"],
                         "fine_H0_sha256": _hash(source["H0_m"]), "fine_H2_sha256": _hash(source["H2_m"]),
                         "saved_stage_sha256": _hash(saved["arrays"]["stage_m"]),
                         "water_representation": "weighted_discrete_wet_support_prisms_not_interpolated_triangle_water_surface",
                         "coordinates": "local_X_Y_elevation_Z_metres_plus_saved_origin_no_hidden_vertical_exaggeration",
                         "upstream_boundary": "explicit_artificial_local_head",
                         "downstream_boundary": "explicit_artificial_tailwater",
                         "scope": saved["scope"], "state_count": int(stage.shape[0]),
                         "committed_steps": saved["committed_steps"], "failure": saved["failure"],
                         "max_display_volume_difference_m3": float(np.abs(difference).max(initial=0)),
                         "validation": validation}}
