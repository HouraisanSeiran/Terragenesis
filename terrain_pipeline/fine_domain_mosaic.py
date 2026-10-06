"""Immutable saved canonical domain windows and uniquely owned shared face segments."""

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class DomainWindow:
    domain_id: int
    interior_zx: tuple
    halo_zx: tuple
    version: str
    bed_m: np.ndarray
    depth_m: np.ndarray


def _immutable(array):
    return np.frombuffer(array.tobytes(), dtype=array.dtype).reshape(array.shape)


def partition_saved_window(bed_m, depth_m, leaf_owner, *, row_cuts=(), column_cuts=(), version):
    bed = np.asarray(bed_m)
    depth = np.asarray(depth_m)
    leaves = np.asarray(leaf_owner)
    if (bed.dtype != np.float64 or bed.ndim != 2 or not bed.size
            or depth.shape != bed.shape or depth.dtype != np.float64
            or leaves.shape != bed.shape or leaves.dtype.kind not in "iu"
            or not np.isfinite(bed).all() or not np.isfinite(depth).all()
            or np.any(depth < 0) or np.any(leaves < 0)
            or type(version) is not str or not version):
        raise ValueError("finite canonical bed/depth/leaf ownership and saved version required")
    rows, columns = bed.shape
    boundaries = []
    for extent, cuts in ((rows, row_cuts), (columns, column_cuts)):
        if (any(type(value) is not int or not 0 < value < extent for value in cuts)
                or list(cuts) != sorted(set(cuts))):
            raise ValueError("strictly ordered interior domain cuts required")
        boundaries.append((0, *cuts, extent))
    owner = np.empty(bed.shape, np.int64)
    windows = []
    for row_index in range(len(boundaries[0]) - 1):
        for column_index in range(len(boundaries[1]) - 1):
            row0, row1 = boundaries[0][row_index:row_index+2]
            col0, col1 = boundaries[1][column_index:column_index+2]
            domain = len(windows)
            owner[row0:row1, col0:col1] = domain
            halo = max(0, row0-1), min(rows, row1+1), max(0, col0-1), min(columns, col1+1)
            windows.append(DomainWindow(domain, (row0, row1, col0, col1), halo, version,
                _immutable(bed[halo[0]:halo[1], halo[2]:halo[3]]),
                _immutable(depth[halo[0]:halo[1], halo[2]:halo[3]])))
    ordered = np.argsort(leaves.ravel(), kind="stable")
    sorted_leaves, sorted_domains = leaves.ravel()[ordered], owner.ravel()[ordered]
    if np.any((sorted_leaves[1:] == sorted_leaves[:-1]) & (sorted_domains[1:] != sorted_domains[:-1])):
        raise ValueError("domain cut splits a saved hydraulic leaf; explicit conservative leaf split required")
    first, second, axis, row, column = [], [], [], [], []
    for face_axis in (0, 1):
        if face_axis == 0:
            rz, cx = np.nonzero(owner[:, :-1] != owner[:, 1:])
            source = rz * columns + cx
            target = source + 1
        else:
            rz, cx = np.nonzero(owner[:-1] != owner[1:])
            source = rz * columns + cx
            target = source + columns
        first.extend(source.tolist())
        second.extend(target.tolist())
        axis.extend([face_axis] * len(source))
        row.extend(rz.tolist())
        column.extend(cx.tolist())
    first, second, axis = (np.asarray(values, np.int64) for values in (first, second, axis))
    face_ids = 2 * first + axis
    if np.unique(face_ids).size != face_ids.size:
        raise ValueError("duplicate shared canonical face")
    return dict(windows=tuple(windows), owner=_immutable(owner), version=version,
        face_ids=_immutable(face_ids), first_cell=_immutable(first), second_cell=_immutable(second),
        face_axis=_immutable(axis), face_row=_immutable(np.asarray(row, np.int64)),
        face_column=_immutable(np.asarray(column, np.int64)),
        face_owner_domain=_immutable(owner.ravel()[first]), neighbor_domain=_immutable(owner.ravel()[second]))


def audit_saved_mosaic(mosaic, bed_m, depth_m, *, spacing_m, version):
    if version != mosaic["version"] or not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("mosaic saved version/metric spacing mismatch")
    bed, depth = np.asarray(bed_m), np.asarray(depth_m)
    owner = mosaic["owner"]
    if bed.shape != owner.shape or depth.shape != owner.shape:
        raise ValueError("mosaic source shape mismatch")
    volumes = []
    for window in mosaic["windows"]:
        row0, row1, col0, col1 = window.interior_zx
        hz0, hz1, hx0, hx1 = window.halo_zx
        if (window.version != version or not np.array_equal(window.bed_m, bed[hz0:hz1, hx0:hx1])
                or not np.array_equal(window.depth_m, depth[hz0:hz1, hx0:hx1])):
            raise ValueError("mosaic stale halo or source seam mismatch")
        volumes.append(math.fsum(depth[row0:row1, col0:col1].ravel()) * spacing_m**2)
    total = math.fsum(depth.ravel()) * spacing_m**2
    residual = math.fsum(volumes) - total
    if abs(residual) > 1e-9 + abs(total) * 1e-12:
        raise ValueError("domain inventory fails canonical volume conservation")
    first, second = mosaic["first_cell"], mosaic["second_cell"]
    return dict(domain_count=len(volumes), shared_face_segments=len(first), domain_volume_m3=volumes,
        total_volume_m3=total, mosaic_volume_residual_m3=residual, halo_matches_saved_source=True,
        unique_shared_faces=True, positive_orientation="first_cell -> second_cell",
        max_cross_cell_stage_jump_m=float(np.max(np.abs((bed+depth).ravel()[first]-(bed+depth).ravel()[second]), initial=0)),
        solver_advanced=False, independent_domain_hydraulics_verified=False)


def account_shared_transfers(mosaic, signed_volume_m3):
    volumes = np.asarray(signed_volume_m3)
    if volumes.dtype != np.float64 or volumes.shape != mosaic["face_ids"].shape or not np.isfinite(volumes).all():
        raise ValueError("one finite signed cumulative volume per shared face required")
    incoming = np.bincount(mosaic["neighbor_domain"], weights=volumes, minlength=len(mosaic["windows"]))
    outgoing = np.bincount(mosaic["face_owner_domain"], weights=volumes, minlength=len(mosaic["windows"]))
    return incoming-outgoing


def bind_saved_leaf_faces(mosaic, geometry):
    rows = geometry["face_canonical_row"]-(geometry["face_axis"] == 1)
    columns = geometry["face_canonical_column"]-(geometry["face_axis"] == 0)
    ids = 2*(rows*mosaic["owner"].shape[1]+columns)+geometry["face_axis"]
    selected = np.flatnonzero(np.isin(ids, mosaic["face_ids"]))
    order = np.argsort(ids[selected])
    selected = selected[order]
    if (selected.size != mosaic["face_ids"].size
            or np.unique(ids[selected]).size != selected.size
            or not np.array_equal(ids[selected], np.sort(mosaic["face_ids"]))):
        raise ValueError("saved segmented hydraulic faces do not uniquely cover shared domain cut")
    return selected[np.argsort(np.argsort(mosaic["face_ids"]))]


def audit_saved_epoch_exchange(mosaic, geometry, packet):
    from terrain_pipeline.surface_adaptive_io import validate_epoch

    validate_epoch(packet, geometry)
    arrays = geometry["arrays"]
    selected = bind_saved_leaf_faces(mosaic, arrays)
    leaf_domains = mosaic["owner"][arrays["leaf_row"], arrays["leaf_column"]]
    shared = account_shared_transfers(mosaic, packet["internal_transfer"][selected, 0])
    domain_count = len(mosaic["windows"])
    change = np.bincount(leaf_domains, weights=(packet["state_after"][:, 0]-packet["state_before"][:, 0])*arrays["leaf_area_m2"], minlength=domain_count)
    supplied = np.bincount(leaf_domains, weights=packet["forcing_volume_m3"], minlength=domain_count)
    boundary = np.bincount(leaf_domains[arrays["boundary_cell"]], weights=packet["boundary_transfer"][:, 0], minlength=domain_count)
    residual = change-shared-supplied+boundary
    if np.max(abs(residual), initial=0) > 1e-9+1e-10*float(np.sum(abs(change))):
        raise ValueError("saved epoch per-domain exchange closure failed")
    volume = packet["internal_transfer"][selected, 0]
    return dict(time_start_s=packet["time_start_s"], time_end_s=packet["time_end_s"],
        domain_storage_change_m3=change.tolist(), domain_net_shared_input_m3=shared.tolist(),
        domain_supplied_m3=supplied.tolist(), domain_boundary_net_output_m3=boundary.tolist(),
        domain_residual_m3=residual.tolist(), forward_shared_m3=float(np.maximum(volume,0).sum()),
        reverse_shared_m3=float(np.maximum(-volume,0).sum()),
        solver_advanced=False, independent_domain_hydraulics_verified=False,
        scope="accounting of original saved single-domain adaptive epoch; no independent domain evolution")


def partition_fan_geometry(mosaic, arrays):
    owner = mosaic["owner"]
    corners = np.asarray(arrays["cell_corner_vertex_ids"])
    bed = np.asarray(arrays["bed_vertices_xyz_m"])
    water = np.asarray(arrays["water_vertices_xyz_m"])
    bed_triangles = np.asarray(arrays["bed_triangles"])
    wet_ids = np.asarray(arrays["wet_cell_ids"])
    water_triangles = np.asarray(arrays["water_triangles"])
    if (corners.shape != (owner.size, 4) or corners.dtype.kind not in "iu"
            or bed.ndim != 2 or bed.shape[1] != 3 or water.shape != bed.shape
            or not np.isfinite(bed).all() or not np.isfinite(water).all()
            or bed_triangles.shape != (owner.size*4, 3) or bed_triangles.dtype.kind not in "iu"
            or wet_ids.ndim != 1 or wet_ids.dtype.kind not in "iu"
            or np.any(wet_ids < 0) or np.any(wet_ids >= owner.size)
            or np.unique(wet_ids).size != wet_ids.size
            or np.any(corners < 0) or np.any(corners >= len(bed))
            or np.any(bed_triangles < 0) or np.any(bed_triangles >= len(bed))
            or not np.array_equal(water_triangles, bed_triangles.reshape(-1, 4, 3)[wet_ids].reshape(-1, 3))):
        raise ValueError("canonical saved cell fan topology/coordinates required")
    meshes = []
    for window in mosaic["windows"]:
        cells = np.flatnonzero(owner.ravel() == window.domain_id)
        triangles = bed_triangles.reshape(-1, 4, 3)[cells].reshape(-1, 3)
        ids, remapped = np.unique(triangles, return_inverse=True)
        selected_wet = wet_ids[owner.ravel()[wet_ids] == window.domain_id]
        wet_triangles = bed_triangles.reshape(-1, 4, 3)[selected_wet].reshape(-1, 3)
        meshes.append(dict(domain_id=window.domain_id, global_vertex_ids=_immutable(ids),
            cell_ids=_immutable(cells), wet_cell_ids=_immutable(selected_wet),
            bed_vertices_xyz_m=_immutable(bed[ids]), water_vertices_xyz_m=_immutable(water[ids]),
            bed_triangles=_immutable(remapped.reshape(-1, 3)),
            water_triangles=_immutable(np.searchsorted(ids, wet_triangles))))
    maximum_bed, maximum_water = 0., 0.
    shared_vertices = set()
    for domain in range(len(meshes)):
        for neighbor in range(domain+1, len(meshes)):
            first, second = meshes[domain], meshes[neighbor]
            ids, first_index, second_index = np.intersect1d(first["global_vertex_ids"], second["global_vertex_ids"], return_indices=True)
            shared_vertices.update(ids.tolist())
            for name in ("bed_vertices_xyz_m", "water_vertices_xyz_m"):
                difference = float(np.max(abs(first[name][first_index]-second[name][second_index]), initial=0))
                if name.startswith("bed"):
                    maximum_bed = max(maximum_bed, difference)
                else:
                    maximum_water = max(maximum_water, difference)
    first_corners = corners[mosaic["first_cell"]]
    second_corners = corners[mosaic["second_cell"]]
    matches = np.any(first_corners[:, :, None] == second_corners[:, None, :], axis=2)
    if np.any(matches.sum(axis=1) != 2) or maximum_bed != 0 or maximum_water != 0:
        raise ValueError("shared domain fan edge/coordinate seam mismatch")
    report = dict(shared_vertex_count=len(shared_vertices), max_bed_seam_error_m=maximum_bed,
        max_water_seam_error_m=maximum_water, bed_triangle_count=sum(len(mesh["bed_triangles"]) for mesh in meshes),
        water_triangle_count=sum(len(mesh["water_triangles"]) for mesh in meshes),
        wet_cells_omitted=0, geometry_reconstructed=False, independent_domain_hydraulics_verified=False)
    return tuple(meshes), report
