"""Independent polynomial checks for saved bilinear-source minus linear-cut edges."""

import numpy as np

from tools.td_entry_saved_audit import assert_close


def native_edge_polynomial(hierarchy, selected_leaves, first_xz, second_xz):
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    bed = arrays["height_m"]
    origin = np.asarray(metadata["origin_m_xz"], float)
    spacing = float(metadata["spacing_m"])
    first = (np.asarray(first_xz, float)-origin)/spacing
    second = (np.asarray(second_xz, float)-origin)/spacing
    if first.shape != (2,) or second.shape != (2,) or not np.isfinite([first, second]).all() or np.linalg.norm(first-second) <= 1e-14:
        raise ValueError("invalid or degenerate saved native segment")
    shape = np.array(bed.shape[::-1])
    if np.any(np.minimum(first, second) < -1e-10) or np.any(np.maximum(first, second) > shape-1+1e-10):
        raise ValueError("saved native edge outside source")
    patch = np.minimum(np.floor((first+second)/2).astype(int), shape-2)
    if np.any(np.minimum(first, second) < patch-1e-9) or np.any(np.maximum(first, second) > patch+1+1e-9):
        raise ValueError("saved native segment omitted a grid crossing")
    offset, delta = first-patch, second-first
    coefficients = np.zeros(3)
    provenance = []
    for delta_z, delta_x in ((0, 0), (0, 1), (1, 0), (1, 1)):
        x_value = offset[0] if delta_x else 1-offset[0]
        z_value = offset[1] if delta_z else 1-offset[1]
        x_delta = delta[0] if delta_x else -delta[0]
        z_delta = delta[1] if delta_z else -delta[1]
        weight = np.array([x_value*z_value, x_value*z_delta+x_delta*z_value, x_delta*z_delta])
        if np.all(weight == 0):
            continue
        row, column = int(patch[1]+delta_z), int(patch[0]+delta_x)
        owner = int(arrays["cell_owner"][row, column])
        leaf = int(arrays["contribution_owner"][row, column])
        unknown = arrays["node_unknown_contact"]
        if (not arrays["valid_mask"][row, column] or arrays["protected_mask"][row, column] or
                arrays["open_boundary_mask"][row, column] or leaf not in selected_leaves or
                owner < 0 or owner >= len(unknown) or leaf < 0 or leaf >= len(unknown) or
                unknown[owner] or unknown[leaf] or not np.isfinite(bed[row, column])):
            raise ValueError("native edge touches invalid/protected/unknown source")
        coefficients += weight*bed[row, column]
        provenance.append(dict(native_cell_id=row*bed.shape[1]+column, weight_polynomial=weight.tolist(), owner=owner, leaf=leaf))
    return dict(native_patch_row_column=[int(patch[1]), int(patch[0])],
                source_height_polynomial_m=coefficients.tolist(), provenance=provenance,
                parameter="t in [0,1], first + t*(second-first)")


def bed_edge_polynomial(source_coefficients, cut_first_m, cut_second_m):
    if not np.isfinite([cut_first_m, cut_second_m]).all() or min(cut_first_m, cut_second_m) < 0:
        raise ValueError("source-conforming edge has negative cut depth")
    result = np.asarray(source_coefficients, float).copy()
    if result.shape != (3,) or not np.isfinite(result).all():
        raise ValueError("invalid native edge polynomial")
    result[:2] -= [cut_first_m, cut_second_m-cut_first_m]
    return result


def reverse_polynomial(coefficients):
    constant, linear, quadratic = np.asarray(coefficients, float)
    return np.array([constant+linear+quadratic, -linear-2*quadratic, quadratic])


def verify_shared_segment(hierarchy, selected_leaves, first_xz, second_xz,
                          first_side_cut, second_side_cut, *, second_reversed=False):
    source = native_edge_polynomial(hierarchy, selected_leaves, first_xz, second_xz)
    expected_first = bed_edge_polynomial(source["source_height_polynomial_m"], *first_side_cut)
    if second_reversed:
        second_side_cut = list(reversed(second_side_cut))
    expected_second = bed_edge_polynomial(source["source_height_polynomial_m"], *second_side_cut)
    assert_close(expected_first, expected_second, "whole shared-edge polynomial", atol=1e-9)
    return dict(**source, derived_bed_polynomial_m=expected_first.tolist(),
                whole_segment_verified=True, proof="equal source quadratic and equal linear cut coefficients on complete native segment")
