"""Offline metric VDM adapter for saved TD river-bed meshes."""

import numpy as np

from terrain_pipeline.metric_vdm import build_vdm
from terrain_pipeline.common_infra import identity, readonly
from terrain_pipeline.basin_topology import validate_basin_hierarchy as validate_basin_hierarchy
from terrain_pipeline.td_native_channel_surface import validate_channel_surface


def channel_protection(surface, hierarchy):
    validate_channel_surface(surface)
    validate_basin_hierarchy(hierarchy)
    metadata = surface["metadata"]
    if metadata["hierarchy_identity"] != hierarchy["identity_sha256"]:
        raise ValueError("surface/hierarchy identity mismatch")
    first_x, last_x, first_z, last_z = metadata["window"]
    shape = (last_z - first_z + 1, last_x - first_x + 1)
    reference = surface["arrays"]["vertices_xyz_m"].reshape(*shape, 3)
    topology = hierarchy["arrays"]
    origin = hierarchy["metadata"]["origin_m_xz"]
    spacing = hierarchy["metadata"]["spacing_m"]
    fractional = (reference[..., [0, 2]] - origin) / spacing
    lower = np.floor(fractional).astype(np.int64)
    upper = np.ceil(fractional).astype(np.int64)
    if (np.any(lower < 0) or np.any(upper[..., 0] >= topology["height_m"].shape[1])
            or np.any(upper[..., 1] >= topology["height_m"].shape[0])):
        raise ValueError("surface outside hierarchy sample coverage")
    protected = surface["arrays"]["candidate_cut_m"].reshape(shape) > 0
    for column in (lower[..., 0], upper[..., 0]):
        for row in (lower[..., 1], upper[..., 1]):
            protected |= topology["protected_mask"][row, column] | ~topology["valid_mask"][row, column]
    padded = np.pad(protected, 1)
    expanded = np.zeros(shape, bool)
    for row in range(3):
        for column in range(3):
            expanded |= padded[row:row + shape[0], column:column + shape[1]]
    return readonly(expanded)


def reject_protected_sweep(reference, displaced, triangles, protected):
    """Reject projected swept triangle boxes intersecting protected metre cells."""
    rows, columns = protected.shape
    original = reference.reshape(-1, 3)
    changed = np.any(displaced != original, axis=1)
    moving_faces = triangles[np.any(changed[triangles], axis=1)]
    if not len(moving_faces):
        return
    before = original[moving_faces][:, :, [0, 2]]
    after = displaced[moving_faces][:, :, [0, 2]]
    lower = np.minimum(before.min(axis=1), after.min(axis=1))
    upper = np.maximum(before.max(axis=1), after.max(axis=1))
    origin = reference[0, 0, [0, 2]]
    if (np.any(lower < origin) or
            np.any(upper > reference[-1, -1, [0, 2]])):
        raise ValueError("VDM moved face outside source domain")
    first = np.maximum(np.ceil(lower - origin - .5).astype(np.int64), 0)
    last = np.minimum(np.floor(upper - origin + .5).astype(np.int64), [columns - 1, rows - 1])
    prefix = np.pad(protected.astype(np.int64), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    count = (prefix[last[:, 1] + 1, last[:, 0] + 1] - prefix[first[:, 1], last[:, 0] + 1]
             - prefix[last[:, 1] + 1, first[:, 0]] + prefix[first[:, 1], first[:, 0]])
    if np.any(count):
        raise ValueError("VDM swept triangle box intersects protected river/domain footprint")


def build_channel_vdm(surface, hierarchy, *, recipe, form=None):
    protected = channel_protection(surface, hierarchy)
    reference = surface["arrays"]["vertices_xyz_m"].reshape(*protected.shape, 3)
    protection_identity = identity({"protected_mask": protected}, {
        "surface_identity": surface["identity_sha256"], "hierarchy_identity": hierarchy["identity_sha256"],
        "policy": "positive_candidate_cut_or_coarse_protected_unknown_stencil_plus_1m_collar"})
    options = dict(recipe=recipe, protected_mask=protected,
                   source_identity=surface["identity_sha256"], protection_identity=protection_identity)
    if form is None:
        result = build_vdm(reference, **options)
    else:
        from terrain_pipeline.metric_vdm_forms import build_formed_vdm
        result = build_formed_vdm(reference, form=form, **options)
    if not np.array_equal(result["arrays"]["triangles"], surface["arrays"]["triangles"]):
        raise ValueError("VDM changed source triangle connectivity")
    reject_protected_sweep(reference, result["arrays"]["vertices_xyz_m"],
                           result["arrays"]["triangles"], protected)
    return result
