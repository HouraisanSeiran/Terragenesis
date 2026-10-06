"""Independent source-bound tributary sections, not legacy construction acceptance."""

import numpy as np
from scipy import ndimage

from terrain_pipeline.mountain_depression_geometry import _hash
from terrain_pipeline.mountain_fine_geometry import _sample


SCHEMA = "mountain-explicit-tributary-manning-geometry-v1"
MAX_SUPPORT = 1001
CHAIN_CELLS = (219142, 219143, 219144, 219145)
GROUP = 1378
WIDTH_M = 10.0
SHALLOW_CUT_M = .25
MAX_CUT_M = 2.0
MAX_CUT_VOLUME_M3 = 200000.0
ARRAY_SHAPES = {
    "chain_cells": (4,), "along_m": (91,), "across_m": (11,),
    "world_x_m": (91, 11), "world_z_m": (91, 11), "H0_m": (91, 11),
    "H2_m": (91, 11), "cut_depth_m": (91, 11), "support_area_m2": (91, 11),
    "row_owner": (91,), "interface_before_rows": (3,), "interface_section_bed_m": (5, 11),
    "interface_crest_m": (5,), "min_bed_m": (4,), "max_stage_m": (4,),
    "node_along_m": (4,), "edge_distance_m": (5,)}


def prepare_tributary_geometry(geometry, *, chain_cells=CHAIN_CELLS, group=GROUP):
    """Explicit fixed study selection; no edits to coarse flowlines or accepted mask."""
    source, metadata = geometry["arrays"], geometry["metadata"]
    if tuple(chain_cells) != CHAIN_CELLS or group != GROUP or metadata["spacing_m"] != 30.:
        raise ValueError("fixed independent tributary identity required")
    cells = np.asarray(chain_cells, dtype=np.int64)
    width = source["H0_m"].shape[1]
    along = np.arange(91., dtype=np.float64)
    across = np.arange(-5., 6., dtype=np.float64)
    row, column = divmod(int(cells[0]), width)
    delta_row = cells[1] // width - row
    delta_column = cells[1] % width - column
    grid_rows = row + along[:, None] / 30 * delta_row + across[None, :] / 30 * delta_column
    grid_columns = column + along[:, None] / 30 * delta_column - across[None, :] / 30 * delta_row
    original = _sample(source["H0_m"], grid_columns, grid_rows)
    cut = np.broadcast_to(SHALLOW_CUT_M * (.5 * (1 + np.cos(np.pi * across / 5)))[None, :], original.shape).copy()
    weights = np.ones(original.shape)
    weights[0] *= .5
    weights[-1] *= .5
    weights[:, 0] *= .5
    weights[:, -1] *= .5
    row_owner = np.minimum(np.floor(along / 30 + .5).astype(np.int64), 3)
    interfaces = np.flatnonzero(np.diff(row_owner) != 0)
    bed = original - cut
    minimum = np.array([bed[row_owner == node].min() for node in range(4)])
    bank = np.array([np.minimum(bed[row_owner == node, 0], bed[row_owner == node, -1]).min() for node in range(4)])
    section_bed = np.vstack((bed[0], np.maximum(bed[interfaces], bed[interfaces + 1]), bed[-1]))
    arrays = {"chain_cells": cells, "along_m": along, "across_m": across,
              "world_x_m": metadata["origin_m_xz"][0] + grid_columns * 30,
              "world_z_m": metadata["origin_m_xz"][1] + grid_rows * 30,
              "H0_m": original, "H2_m": bed, "cut_depth_m": cut,
              "support_area_m2": weights, "row_owner": row_owner,
              "interface_before_rows": interfaces, "interface_section_bed_m": section_bed,
              "interface_crest_m": section_bed.min(axis=1),
              "min_bed_m": minimum, "max_stage_m": bank - 1e-6,
              "node_along_m": np.array([0., 30., 60., 90.]),
              "edge_distance_m": np.array([15., 30., 30., 30., 15.])}
    record = {"arrays": arrays, "metadata": {"schema": SCHEMA, "group": group,
              "source_binding": metadata["source_binding"], "source_H0_sha256": _hash(source["H0_m"]),
              "source_receiver_sha256": _hash(source["receiver"]), "origin_m_xz": metadata["origin_m_xz"],
              "fine_spacing_m": 1., "width_m": WIDTH_M, "shallow_cut_m": SHALLOW_CUT_M,
              "cut_volume_m3": float((cut * weights).sum()),
              "scope": "explicit_independent_small_tributary_study_not_legacy_1km2_channel_or_construction_certificate",
              "selection": "preflight_max_solved_upstream_pool_count_then_complete_subtree_area_then_flat_id",
              "coarse_channel_threshold_unchanged_m2": 1000000.,
              "subcell_limitation": "1m_bilinear_interpolation_of_30m_TD_not_new_terrain_resolution"}}
    validate_tributary_geometry(record, geometry)
    return record


def validate_tributary_geometry(record, geometry):
    """Static original samples, full strip masks, sections and bank-limited wet events."""
    arrays, meta = record["arrays"], record["metadata"]
    source, source_meta = geometry["arrays"], geometry["metadata"]
    if set(arrays) != set(ARRAY_SHAPES):
        raise ValueError("exact tributary geometry schema")
    for key, shape in ARRAY_SHAPES.items():
        if not isinstance(arrays[key], np.ndarray) or arrays[key].shape != shape:
            raise ValueError("tributary exact shape: " + key)
    if (meta["schema"] != SCHEMA or meta["group"] != GROUP or meta["source_binding"] != source_meta["source_binding"]
            or meta["source_H0_sha256"] != _hash(source["H0_m"]) or meta["source_receiver_sha256"] != _hash(source["receiver"])):
        raise ValueError("independent geometry source binding mismatch")
    if (meta["origin_m_xz"] != source_meta["origin_m_xz"] or meta["fine_spacing_m"] != 1.
            or meta["width_m"] != WIDTH_M or meta["shallow_cut_m"] != SHALLOW_CUT_M
            or meta["coarse_channel_threshold_unchanged_m2"] != 1000000.
            or meta["scope"] != "explicit_independent_small_tributary_study_not_legacy_1km2_channel_or_construction_certificate"):
        raise ValueError("fixed tributary parameter/scope identity")
    cells = arrays["chain_cells"]
    if not np.array_equal(cells, CHAIN_CELLS) or cells.dtype != np.dtype("int64") or not np.array_equal(source["receiver"][cells[:-1]], cells[1:]):
        raise ValueError("fixed selected chain topology")
    if not np.array_equal(source["outlet_owner"].ravel()[cells], np.full(4, GROUP)):
        raise ValueError("chain leaves complete contribution group")
    if arrays["H0_m"].shape != (91, 11) or arrays["H0_m"].size > MAX_SUPPORT:
        raise ValueError("independent strip resource ceiling")
    for key, value in arrays.items():
        dtype = np.dtype("int64" if key in ("chain_cells", "row_owner", "interface_before_rows") else "float64")
        if not isinstance(value, np.ndarray) or value.dtype != dtype or not np.isfinite(value).all():
            raise ValueError("typed finite tributary arrays required")
    origin_x, origin_z = source_meta["origin_m_xz"]
    grid_columns = (arrays["world_x_m"] - origin_x) / 30
    grid_rows = (arrays["world_z_m"] - origin_z) / 30
    if (grid_columns < 0).any() or (grid_columns > source["H0_m"].shape[1] - 1).any() or (grid_rows < 0).any() or (grid_rows > source["H0_m"].shape[0] - 1).any():
        raise ValueError("strip exceeds original source")
    row, column = divmod(CHAIN_CELLS[0], source["H0_m"].shape[1])
    expected_columns = np.broadcast_to(column + np.arange(91.)[:, None] / 30, (91, 11))
    expected_rows = np.broadcast_to(row + np.arange(-5., 6.)[None, :] / 30, (91, 11))
    def equal(actual, expected, name):
        if actual.shape != expected.shape or not np.allclose(actual, expected, atol=1e-10, rtol=0):
            raise ValueError("static tributary mismatch: " + name)
    equal(grid_columns, expected_columns, "source X coordinate")
    equal(grid_rows, expected_rows, "source Z coordinate")
    equal(arrays["along_m"], np.arange(91.), "along")
    equal(arrays["across_m"], np.arange(-5., 6.), "across")
    original = _sample(source["H0_m"], grid_columns, grid_rows)
    equal(arrays["H0_m"], original, "original sampled H0")
    expected_cut = np.broadcast_to(.25 * (.5 * (1 + np.cos(np.pi * arrays["across_m"] / 5)))[None, :], original.shape)
    equal(arrays["cut_depth_m"], expected_cut, "fixed cosine shallow cut")
    equal(arrays["H2_m"], original - expected_cut, "original source bed")
    nearest_rows = np.floor(grid_rows + .5).astype(np.int64)
    nearest_columns = np.floor(grid_columns + .5).astype(np.int64)
    if ((source["outlet_owner"][nearest_rows, nearest_columns] != GROUP) | source["lake_mask"][nearest_rows, nearest_columns] | source["protected_mask"][nearest_rows, nearest_columns]).any():
        raise ValueError("full strip leaves group or crosses lake/protection")
    owner = np.minimum(np.floor(np.arange(91.) / 30 + .5).astype(np.int64), 3)
    equal(arrays["row_owner"], owner, "support partition")
    weights = np.ones(original.shape)
    weights[0] *= .5
    weights[-1] *= .5
    weights[:, 0] *= .5
    weights[:, -1] *= .5
    equal(arrays["support_area_m2"], weights, "unique support quadrature")
    bed = arrays["H2_m"]
    if (np.diff(bed[:, 5]) > 1e-9).any() or (bed < bed[:, 5:6] - 1e-9).any():
        raise ValueError("longitudinal or transverse bed not legal")
    interfaces = np.flatnonzero(np.diff(owner) != 0)
    equal(arrays["interface_before_rows"], interfaces, "shared interface rows")
    sections = np.vstack((bed[0], np.maximum(bed[interfaces], bed[interfaces + 1]), bed[-1]))
    equal(arrays["interface_section_bed_m"], sections, "real conservative section crest")
    equal(arrays["interface_crest_m"], sections.min(axis=1), "interface crest")
    for node in range(4):
        local_bed = bed[owner == node]
        bank = float(np.minimum(local_bed[:, 0], local_bed[:, -1]).min()) - 1e-6
        if arrays["min_bed_m"][node] != local_bed.min() or arrays["max_stage_m"][node] != bank:
            raise ValueError("bank or bed certificate forged")
        for level in np.unique(local_bed[local_bed <= bank]):
            if ndimage.label(local_bed <= level, ndimage.generate_binary_structure(2, 1))[1] > 1:
                raise ValueError("support wet events disconnected")
    equal(arrays["node_along_m"], np.array([0., 30., 60., 90.]), "node positions")
    equal(arrays["edge_distance_m"], np.array([15., 30., 30., 30., 15.]), "diffusive distances")
    volume = float((expected_cut * weights).sum())
    if volume != meta["cut_volume_m3"] or volume > MAX_CUT_VOLUME_M3 or expected_cut.max() > MAX_CUT_M:
        raise ValueError("independent cut budget")
    return {"cut_volume_m3": volume, "minimum_bank_margin_m": float(np.min(arrays["max_stage_m"] - arrays["min_bed_m"])),
            "scope": meta["scope"]}


def section_hydraulics(across_m, bed_m, stage_m):
    """Exact clipped linear transverse segments: wetted A, P, R and top width."""
    depth = stage_m - bed_m
    lengths = np.diff(across_m)
    left = depth[:-1]
    right = depth[1:]
    both = (left > 0) & (right > 0)
    one = (left > 0) ^ (right > 0)
    fraction = np.zeros(lengths.size)
    fraction[both] = 1.
    fraction[one] = np.maximum(left[one], right[one]) / np.maximum(np.abs(left[one] - right[one]), 1e-30)
    area = float(np.sum(lengths[both] * (left[both] + right[both]) * .5)
                 + np.sum(lengths[one] * fraction[one] * np.maximum(left[one], right[one]) * .5))
    perimeter = float(np.sum(np.hypot(lengths, np.diff(bed_m)) * fraction))
    top_width = float(np.dot(lengths, fraction))
    return {"area_m2": area, "wetted_perimeter_m": perimeter,
            "hydraulic_radius_m": area / perimeter if perimeter > 0 else 0., "top_width_m": top_width}
