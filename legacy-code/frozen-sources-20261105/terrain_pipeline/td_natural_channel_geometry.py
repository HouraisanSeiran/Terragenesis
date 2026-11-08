"""Shared-bed natural channel geometry and bounded, diagnostic terrain cuts."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest
from terrain_pipeline.channel_centerline import (SmoothingRecipe, _sample_height, _segments_cross,
                                                 build_centerline, validate_centerline_for_plan)
from terrain_pipeline.local_channel_sections import SectionRecipe, evaluate_sections
from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel
from terrain_pipeline.mountain_source_adapter import (identity, load_bundle, readonly,
                                                      save_bundle)
from terrain_pipeline.td_natural_river_network import validate_natural_river_network


SCHEMA = "td-natural-channel-geometry-v1"
WINDOW_SCHEMA = "td-natural-channel-window-v1"
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable")
ARRAY_NAMES = {"node_cell_ids", "edge_cell_ids", "node_world_xz_m", "node_world_xyz_m",
               "edge_centerline_xyz_m", "edge_sections_xyz_m", "node_native_xz_m",
               "node_bed_m", "node_width_m", "node_depth_m", "node_representative_q_m3_s",
               "node_anchor_mask", "edge_requires_refinement", "node_over_budget_mask",
               "edge_slope_failed_mask", "source_height_m", "valid_mask", "protected_mask",
               "open_boundary_mask", "bounded_bed_m", "required_cut_m"}


@dataclass(frozen=True)
class NaturalGeometryRecipe:
    smoothing_strength: float = .2
    max_offset_m: float = 5.
    max_cut_m: float = 4.
    min_bed_slope_m_per_m: float = .0001
    max_window_span_m: float = 240.
    min_cells_across_width: float = 2.

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if (self.smoothing_strength > .5 or not 0 < self.max_window_span_m <= 240 or
                self.min_cells_across_width <= 0):
            raise ValueError("invalid smoothing or window resolution policy")


def _network_fields(network):
    validate_natural_river_network(network)
    arrays, metadata = network["arrays"], network["metadata"]
    required = ("source_height_m", "valid_mask", "protected_mask", "open_boundary_mask",
                "receiver", "routing_order", "selected_basin_mask", "edge_cell_ids",
                "node_cell_ids", "node_native_xyz_m", "node_width_m", "node_depth_m",
                "node_representative_q_m3_s", "edge_requires_refinement")
    if any(name not in arrays for name in required):
        raise ValueError("natural network core arrays required")
    height = np.asarray(arrays["source_height_m"])
    if height.ndim != 2 or list(height.shape) != list(metadata["grid_shape"]):
        raise ValueError("network grid shape mismatch")
    nodes = np.asarray(arrays["node_cell_ids"])
    edges = np.asarray(arrays["edge_cell_ids"])
    if (nodes.dtype != np.int64 or edges.dtype != np.int64 or
            edges.shape != (len(edges), 2) or not np.array_equal(nodes, np.unique(nodes)) or
            not np.array_equal(np.unique(edges.ravel()), nodes) or
            not np.array_equal(arrays["receiver"][edges[:, 0]], edges[:, 1])):
        raise ValueError("network edge and node topology mismatch")
    if np.any(~arrays["selected_basin_mask"].ravel()[nodes]) or np.any(~arrays["valid_mask"].ravel()[nodes]):
        raise ValueError("network nodes outside usable selected basin")
    if np.any(arrays["protected_mask"].ravel()[nodes]):
        raise ValueError("network node lies in protection")
    return arrays, metadata


def _make_plan(network, recipe):
    arrays, metadata = _network_fields(network)
    shape = arrays["source_height_m"].shape
    nodes = arrays["node_cell_ids"]
    receiver = np.asarray(arrays["receiver"], dtype=np.int64)
    discharge = np.zeros(shape, np.float64)
    discharge.ravel()[nodes] = np.asarray(arrays["node_representative_q_m3_s"])
    positive = discharge.ravel()[nodes]
    if not np.isfinite(positive).all() or np.any(positive <= 0):
        raise ValueError("network node discharge must be positive")
    natural = metadata["recipe"]
    width = np.asarray(arrays["node_width_m"])
    depth = np.asarray(arrays["node_depth_m"])
    if (np.any(~np.isfinite(width)) or np.any(~np.isfinite(depth)) or
            np.any(width <= 0) or np.any(depth <= 0)):
        raise ValueError("network width and depth must be finite positive")
    plan_recipe = ChannelRecipe(
        start_discharge_m3_s=float(positive.min()),
        reference_discharge_m3_s=float(natural["reference_q_m3_s"]),
        reference_width_m=float(natural["reference_width_m"]),
        reference_depth_m=float(natural["reference_depth_m"]),
        width_exponent=float(natural["width_exponent"]),
        depth_exponent=float(natural["depth_exponent"]),
        min_width_m=float(natural["minimum_width_m"]),
        max_width_m=float(natural["maximum_width_m"]),
        min_depth_m=float(natural["minimum_depth_m"]),
        max_depth_m=float(natural["maximum_depth_m"]),
        min_bed_slope_m_per_m=recipe.min_bed_slope_m_per_m,
        max_cut_m=recipe.max_cut_m,
        min_cells_across_width=recipe.min_cells_across_width)
    outlet = receiver == -1
    spacing = float(metadata["spacing_m"])
    origin_x, origin_z = metadata["origin_m_xz"]
    plan = plan_channel(arrays["source_height_m"], receiver, arrays["routing_order"],
                        outlet.reshape(shape), discharge, spacing, spacing,
                        float(origin_x), float(origin_z), 0., network["identity_sha256"], plan_recipe)
    result = {name: value.copy() for name, value in plan["arrays"].items()}
    result["nominal_width_m"].ravel()[nodes] = width
    result["nominal_depth_m"].ravel()[nodes] = depth
    native = np.asarray(arrays["node_native_xyz_m"])
    if native.shape != (len(nodes), 3) or not np.isfinite(native).all():
        raise ValueError("invalid native node positions")
    expected_xz = np.column_stack((origin_x + nodes % shape[1] * spacing,
                                   origin_z + nodes // shape[1] * spacing))
    if not np.allclose(native[:, (0, 2)], expected_xz, atol=1e-8, rtol=0):
        raise ValueError("native node positions differ from route grid")
    if not np.allclose(native[:, 1], arrays["source_height_m"].ravel()[nodes], atol=1e-8, rtol=0):
        raise ValueError("native node heights differ from source")
    target = result["source_height_m"].ravel().copy()
    target[nodes] -= depth
    active = result["channel_mask"].ravel()
    for donor in np.asarray(arrays["routing_order"])[::-1]:
        downstream = int(receiver[donor])
        if downstream >= 0 and active[donor] and active[downstream]:
            target[downstream] = min(target[downstream], target[donor] -
                                     recipe.min_bed_slope_m_per_m * spacing)
    required = np.maximum(0., result["source_height_m"].ravel() - target)
    bounded = result["source_height_m"].ravel() - np.minimum(required, recipe.max_cut_m)
    over = active & (required > recipe.max_cut_m + 1e-9)
    failed = np.zeros(receiver.size, bool)
    for donor, downstream in arrays["edge_cell_ids"]:
        if bounded[downstream] > bounded[donor] - recipe.min_bed_slope_m_per_m * spacing + 1e-9:
            failed[donor] = True
    result["target_bed_m"] = target.reshape(shape)
    result["required_cut_m"] = required.reshape(shape)
    result["bounded_bed_m"] = bounded.reshape(shape)
    result["over_budget_mask"] = over.reshape(shape)
    result["failed_slope_edge_donor_mask"] = failed.reshape(shape)
    result["needs_refinement_mask"] = (result["channel_mask"] &
        (result["nominal_width_m"] < recipe.min_cells_across_width * spacing))
    params = dict(plan["identity"]["parameters"])
    params["natural_network_identity_sha256"] = network["identity_sha256"]
    params["natural_geometry_sha256"] = digest({name: array_hash(np.ascontiguousarray(result[name]))
        for name in ("nominal_width_m", "nominal_depth_m", "target_bed_m", "bounded_bed_m")})
    plan_identity = ArtifactIdentity("Terragenesis", "metric-channel-plan", "metric-channel-plan-v1", 0, params)
    for value in result.values():
        value.flags.writeable = False
    return {"identity": plan_identity.record(), "identity_sha256": plan_identity.sha256,
            "status": "diagnostic_not_publishable", "arrays": result}


def _blocked_contact(cell, arrays, shape):
    row, column = divmod(int(cell), shape[1])
    blocked = ~arrays["valid_mask"] | arrays["protected_mask"]
    if row in (0, shape[0] - 1) or column in (0, shape[1] - 1):
        return True
    return bool(blocked[row - 1:row + 2, column - 1:column + 2].any() or
                arrays["open_boundary_mask"][row, column])


def _reject_crossings(nodes, edges, positions, bucket_size):
    index = {int(cell): place for place, cell in enumerate(nodes)}
    buckets = {}
    for edge_index, (donor, downstream) in enumerate(edges):
        first, second = positions[index[int(donor)]], positions[index[int(downstream)]]
        x0, x1 = math.floor(min(first[0], second[0]) / bucket_size), math.floor(max(first[0], second[0]) / bucket_size)
        z0, z1 = math.floor(min(first[1], second[1]) / bucket_size), math.floor(max(first[1], second[1]) / bucket_size)
        nearby = set()
        for column in range(x0, x1 + 1):
            for row in range(z0, z1 + 1):
                nearby.update(buckets.get((column, row), ()))
        for other_index in nearby:
            other_donor, other_downstream = edges[other_index]
            if {int(donor), int(downstream)} & {int(other_donor), int(other_downstream)}:
                continue
            if _segments_cross(first, second, positions[index[int(other_donor)]],
                               positions[index[int(other_downstream)]]):
                raise ValueError("channel centerline self-intersects")
        for column in range(x0, x1 + 1):
            for row in range(z0, z1 + 1):
                buckets.setdefault((column, row), []).append(edge_index)


def _make_centerline(plan, network, recipe):
    arrays = network["arrays"]
    line = build_centerline(plan, SmoothingRecipe(recipe.smoothing_strength, recipe.max_offset_m))
    values = {name: value.copy() for name, value in line["arrays"].items()}
    nodes = values["node_flat_index"]
    shape = arrays["source_height_m"].shape
    anchored = np.array([_blocked_contact(cell, arrays, shape) for cell in nodes])
    anchored |= values["anchor_mask"]
    values["node_world_xz_m"][anchored] = values["original_world_xz_m"][anchored]
    positions = values["node_world_xz_m"]
    index = {int(cell): place for place, cell in enumerate(nodes)}
    edges = np.asarray(arrays["edge_cell_ids"])
    for donor, downstream in edges:
        first, second = positions[index[int(donor)]], positions[index[int(downstream)]]
        if np.linalg.norm(first - second) <= 1e-9:
            raise ValueError("zero-length channel edge")
        for fraction in np.linspace(0., 1., 9):
            x, z = first * (1 - fraction) + second * fraction
            column = int(round((x - plan["identity"]["parameters"]["origin_x_m"]) /
                               plan["identity"]["parameters"]["spacing_x_m"]))
            row = int(round((z - plan["identity"]["parameters"]["origin_z_m"]) /
                            plan["identity"]["parameters"]["spacing_z_m"]))
            if (row < 0 or column < 0 or row >= shape[0] or column >= shape[1] or
                    not arrays["valid_mask"][row, column] or arrays["protected_mask"][row, column]):
                raise ValueError("channel crosses protected or unknown gap")
        if (values["node_bed_m"][index[int(donor)]] - values["node_bed_m"][index[int(downstream)]] + 1e-9 <
                recipe.min_bed_slope_m_per_m * np.linalg.norm(first - second)):
            raise ValueError("smoothed channel reverses bed slope")
    _reject_crossings(nodes, edges, positions, plan["identity"]["parameters"]["spacing_x_m"])
    parameters = plan["identity"]["parameters"]
    values["local_budget_failed_mask"] = np.array([
        _sample_height(plan["arrays"]["source_height_m"], position, parameters) - bed >
        recipe.max_cut_m + 1e-9
        for position, bed in zip(positions, values["node_bed_m"])
    ], bool)
    values["slope_failed_donor_mask"] = np.zeros(len(nodes), bool)
    line_parameters = dict(line["identity"]["parameters"])
    line_parameters["result_geometry_sha256"] = digest({name: array_hash(np.ascontiguousarray(value))
                                                    for name, value in values.items()})
    line_identity = ArtifactIdentity("Terragenesis", "channel-centerline", "channel-centerline-v1", 0,
                                     line_parameters)
    for value in values.values():
        value.flags.writeable = False
    adjusted = {"identity": line_identity.record(), "identity_sha256": line_identity.sha256,
                "status": "diagnostic_not_publishable", "arrays": values}
    validate_centerline_for_plan(adjusted, plan)
    return adjusted, anchored


def build_natural_channel_geometry(network, recipe=NaturalGeometryRecipe()):
    """Build shared node bed and centerline from a validated natural network."""
    if not isinstance(recipe, NaturalGeometryRecipe):
        raise ValueError("natural geometry recipe required")
    arrays, metadata = _network_fields(network)
    plan = _make_plan(network, recipe)
    centerline, anchored = _make_centerline(plan, network, recipe)
    nodes = arrays["node_cell_ids"]
    edges = arrays["edge_cell_ids"]
    plan_arrays = plan["arrays"]
    line_arrays = centerline["arrays"]
    node_index = {int(cell): index for index, cell in enumerate(nodes)}
    edge_slope_failed = np.array([plan_arrays["failed_slope_edge_donor_mask"].flat[donor]
                                  for donor, _ in edges], bool)
    geometry_arrays = {
        "node_cell_ids": nodes.copy(), "edge_cell_ids": edges.copy(),
        "node_world_xz_m": line_arrays["node_world_xz_m"].copy(),
        "node_native_xz_m": line_arrays["original_world_xz_m"].copy(),
        "node_bed_m": line_arrays["node_bed_m"].copy(),
        "node_width_m": line_arrays["node_width_m"].copy(),
        "node_depth_m": np.asarray(arrays["node_depth_m"]).copy(),
        "node_representative_q_m3_s": np.asarray(arrays["node_representative_q_m3_s"]).copy(),
        "node_anchor_mask": anchored,
        "edge_requires_refinement": np.asarray(arrays["edge_requires_refinement"]).copy(),
        "node_over_budget_mask": line_arrays["local_budget_failed_mask"].copy(),
        "edge_slope_failed_mask": edge_slope_failed,
        "source_height_m": plan_arrays["source_height_m"].copy(),
        "valid_mask": np.asarray(arrays["valid_mask"]).copy(),
        "protected_mask": np.asarray(arrays["protected_mask"]).copy(),
        "open_boundary_mask": np.asarray(arrays["open_boundary_mask"]).copy(),
        "bounded_bed_m": plan_arrays["bounded_bed_m"].copy(),
        "required_cut_m": plan_arrays["required_cut_m"].copy(),
    }
    geometry_arrays["node_world_xyz_m"] = np.column_stack((
        geometry_arrays["node_world_xz_m"][:, 0], geometry_arrays["node_bed_m"],
        geometry_arrays["node_world_xz_m"][:, 1]))
    edge_centers = np.empty((len(edges), 2, 3), np.float64)
    edge_sections = np.empty((len(edges), 6, 3), np.float64)
    source_flat = geometry_arrays["source_height_m"].ravel()
    for edge_index, (donor, downstream) in enumerate(edges):
        endpoint_indices = (node_index[int(donor)], node_index[int(downstream)])
        edge_centers[edge_index] = geometry_arrays["node_world_xyz_m"][list(endpoint_indices)]
        direction = edge_centers[edge_index, 1, [0, 2]] - edge_centers[edge_index, 0, [0, 2]]
        direction /= np.linalg.norm(direction)
        normal = np.array([-direction[1], direction[0]])
        for endpoint, (cell, node_index_value) in enumerate(zip((donor, downstream), endpoint_indices)):
            center = edge_centers[edge_index, endpoint]
            bank = np.array([center[0], source_flat[cell], center[2]])
            half_width = geometry_arrays["node_width_m"][node_index_value] / 2
            left, right = bank.copy(), bank.copy()
            left[[0, 2]] -= normal * half_width
            right[[0, 2]] += normal * half_width
            edge_sections[edge_index, endpoint * 3:endpoint * 3 + 3] = (left, center, right)
    geometry_arrays["edge_centerline_xyz_m"] = edge_centers
    geometry_arrays["edge_sections_xyz_m"] = edge_sections
    summary = {"node_count": len(nodes), "edge_count": len(edges),
               "moved_nodes": int(np.count_nonzero(np.linalg.norm(
                   geometry_arrays["node_world_xz_m"] - geometry_arrays["node_native_xz_m"], axis=1) > 1e-9)),
               "over_budget_nodes": int(geometry_arrays["node_over_budget_mask"].sum()),
               "native_plan_over_budget_nodes": int(plan_arrays["over_budget_mask"].ravel()[nodes].sum()),
               "failed_slope_edges": int(edge_slope_failed.sum()),
               "needs_refinement_edges": int(geometry_arrays["edge_requires_refinement"].sum()),
               "diagnostic_failure": bool(geometry_arrays["node_over_budget_mask"].any() or
                                          edge_slope_failed.any())}
    result_metadata = {"schema": SCHEMA, "algorithm": SCHEMA,
                       "status": "diagnostic_failure" if summary["diagnostic_failure"] else "diagnostic_not_publishable",
                       "network_identity_sha256": network["identity_sha256"],
                       "grid_shape": list(metadata["grid_shape"]),
                       "spacing_m": float(metadata["spacing_m"]),
                       "origin_m_xz": list(metadata["origin_m_xz"]),
                       "recipe": asdict(recipe), "plan_parameters": plan["identity"]["parameters"],
                       "plan_identity_sha256": plan["identity_sha256"],
                       "centerline_identity_sha256": centerline["identity_sha256"],
                       "summary": summary, "coordinates": "arrays [z,x]; world XYZ metres",
                       **{flag: False for flag in FLAGS}}
    result = {"arrays": {name: readonly(value) for name, value in geometry_arrays.items()},
              "metadata": result_metadata}
    result["identity_sha256"] = identity(result["arrays"], result_metadata)
    validate_natural_channel_geometry(result)
    return result


def validate_natural_channel_geometry(geometry):
    """Validate stored geometry without rebuilding its source network."""
    arrays, metadata = geometry["arrays"], geometry["metadata"]
    if (metadata.get("schema") != SCHEMA or metadata.get("algorithm") != SCHEMA or
            set(arrays) != ARRAY_NAMES or any(metadata.get(flag) is not False for flag in FLAGS) or
            geometry.get("identity_sha256") != identity(arrays, metadata)):
        raise ValueError("natural geometry identity/schema invalid")
    shape = tuple(metadata["grid_shape"])
    if (len(shape) != 2 or min(shape) < 2 or shape[0] * shape[1] > 250_000 or
            any(arrays[name].shape != shape for name in
                ("source_height_m", "valid_mask", "protected_mask", "open_boundary_mask",
                 "bounded_bed_m", "required_cut_m"))):
        raise ValueError("natural geometry grid invalid")
    nodes, edges = arrays["node_cell_ids"], arrays["edge_cell_ids"]
    if (nodes.dtype != np.int64 or edges.dtype != np.int64 or edges.shape != (len(edges), 2) or
            not np.array_equal(nodes, np.unique(nodes)) or not np.array_equal(nodes, np.unique(edges)) or
            np.any(nodes < 0) or np.any(nodes >= math.prod(shape)) or
            len(set(int(cell) for cell in edges[:, 0])) != len(edges)):
        raise ValueError("natural geometry graph invalid")
    count = len(nodes)
    for name in ("node_world_xz_m", "node_native_xz_m"):
        if arrays[name].shape != (count, 2) or arrays[name].dtype != np.float64:
            raise ValueError("natural geometry position invalid")
    if (arrays["node_world_xyz_m"].shape != (count, 3) or
            arrays["edge_centerline_xyz_m"].shape != (len(edges), 2, 3) or
            arrays["edge_sections_xyz_m"].shape != (len(edges), 6, 3) or
            any(arrays[name].dtype != np.float64 or not np.isfinite(arrays[name]).all() for name in
                ("node_world_xyz_m", "edge_centerline_xyz_m", "edge_sections_xyz_m"))):
        raise ValueError("natural geometry XYZ arrays invalid")
    for name in ("node_bed_m", "node_width_m", "node_depth_m", "node_representative_q_m3_s"):
        if arrays[name].shape != (count,) or arrays[name].dtype != np.float64 or not np.isfinite(arrays[name]).all():
            raise ValueError("natural geometry node metric invalid")
    for name, length in (("node_anchor_mask", count), ("node_over_budget_mask", count),
                         ("edge_requires_refinement", len(edges)), ("edge_slope_failed_mask", len(edges))):
        if arrays[name].shape != (length,) or arrays[name].dtype != bool:
            raise ValueError("natural geometry diagnostic mask invalid")
    if any(arrays[name].dtype != bool for name in ("valid_mask", "protected_mask", "open_boundary_mask")) or any(
            arrays[name].dtype != np.float64 or not np.isfinite(arrays[name]).all() for name in
            ("source_height_m", "bounded_bed_m", "required_cut_m")):
        raise ValueError("natural geometry terrain invalid")
    if (np.any(arrays["node_width_m"] <= 0) or np.any(arrays["node_depth_m"] <= 0) or
            np.any(arrays["node_representative_q_m3_s"] <= 0) or
            np.any(arrays["protected_mask"].ravel()[nodes]) or
            np.any(~arrays["valid_mask"].ravel()[nodes])):
        raise ValueError("natural geometry node constraints invalid")
    max_cut = metadata["recipe"]["max_cut_m"]
    inactive = np.ones(math.prod(shape), bool)
    inactive[nodes] = False
    if (np.any(arrays["required_cut_m"].ravel()[inactive] != 0) or
            np.any(arrays["required_cut_m"].ravel()[nodes] + 1e-9 < arrays["node_depth_m"]) or
            not np.allclose(arrays["bounded_bed_m"], arrays["source_height_m"] -
                            np.minimum(arrays["required_cut_m"], max_cut), atol=1e-9, rtol=0) or
            not np.allclose(arrays["node_bed_m"],
                            arrays["source_height_m"].ravel()[nodes] - arrays["required_cut_m"].ravel()[nodes],
                            atol=1e-9, rtol=0)):
        raise ValueError("natural geometry bed/cut ledger invalid")
    plan_parameters = metadata["plan_parameters"]
    if (plan_parameters["source_height_sha256"] != array_hash(np.ascontiguousarray(arrays["source_height_m"])) or
            plan_parameters["natural_network_identity_sha256"] != metadata["network_identity_sha256"] or
            ArtifactIdentity("Terragenesis", "metric-channel-plan", "metric-channel-plan-v1", 0,
                             plan_parameters).sha256 != metadata["plan_identity_sha256"]):
        raise ValueError("natural geometry source plan identity invalid")
    nominal_width = np.zeros(shape, np.float64)
    nominal_depth = np.zeros(shape, np.float64)
    nominal_width.ravel()[nodes] = arrays["node_width_m"]
    nominal_depth.ravel()[nodes] = arrays["node_depth_m"]
    target_bed = arrays["source_height_m"] - arrays["required_cut_m"]
    geometry_hash = digest({name: array_hash(np.ascontiguousarray(value)) for name, value in (
        ("nominal_width_m", nominal_width), ("nominal_depth_m", nominal_depth),
        ("target_bed_m", target_bed), ("bounded_bed_m", arrays["bounded_bed_m"]))})
    if geometry_hash != plan_parameters["natural_geometry_sha256"]:
        raise ValueError("natural geometry plan metrics differ from identity")
    spacing = metadata["spacing_m"]
    origin_x, origin_z = metadata["origin_m_xz"]
    expected = np.column_stack((origin_x + nodes % shape[1] * spacing,
                                origin_z + nodes // shape[1] * spacing))
    if (not np.allclose(arrays["node_native_xz_m"], expected, atol=1e-8, rtol=0) or
            not np.array_equal(arrays["node_world_xz_m"][arrays["node_anchor_mask"]],
                               arrays["node_native_xz_m"][arrays["node_anchor_mask"]])):
        raise ValueError("natural geometry anchor mismatch")
    index = {int(cell): position for position, cell in enumerate(nodes)}
    donor_count = np.bincount(edges[:, 1], minlength=math.prod(shape))
    outgoing = set(int(cell) for cell in edges[:, 0])
    expected_anchors = np.array([donor_count[cell] != 1 or int(cell) not in outgoing or
                                 _blocked_contact(cell, arrays, shape) for cell in nodes], bool)
    if not np.array_equal(arrays["node_anchor_mask"], expected_anchors):
        raise ValueError("natural geometry graph/protection anchors invalid")
    expected_xyz = np.column_stack((arrays["node_world_xz_m"][:, 0], arrays["node_bed_m"],
                                    arrays["node_world_xz_m"][:, 1]))
    if not np.array_equal(arrays["node_world_xyz_m"], expected_xyz):
        raise ValueError("natural geometry shared node bed mismatch")
    _reject_crossings(nodes, edges, arrays["node_world_xz_m"], spacing)
    slope = NaturalGeometryRecipe(**metadata["recipe"]).min_bed_slope_m_per_m
    params = {"origin_x_m": origin_x, "origin_z_m": origin_z,
              "spacing_x_m": spacing, "spacing_z_m": spacing}
    budget = np.array([_sample_height(arrays["source_height_m"], point, params) - bed > max_cut + 1e-9
                       for point, bed in zip(arrays["node_world_xz_m"], arrays["node_bed_m"])], bool)
    if not np.array_equal(budget, arrays["node_over_budget_mask"]):
        raise ValueError("natural geometry moved-node budget mismatch")
    for edge_index, (donor, target) in enumerate(edges):
        first, second = index[int(donor)], index[int(target)]
        if (not np.array_equal(arrays["edge_centerline_xyz_m"][edge_index],
                               arrays["node_world_xyz_m"][[first, second]]) or
                not np.array_equal(arrays["edge_sections_xyz_m"][edge_index, (1, 4)],
                                   arrays["node_world_xyz_m"][[first, second]])):
            raise ValueError("natural geometry edge does not share node bed")
        start, end = arrays["node_world_xyz_m"][[first, second]]
        horizontal = end[[0, 2]] - start[[0, 2]]
        horizontal /= np.linalg.norm(horizontal)
        normal = np.array([-horizontal[1], horizontal[0]])
        for endpoint, (cell, node_position) in enumerate(((donor, first), (target, second))):
            bank = np.array([arrays["node_world_xyz_m"][node_position, 0],
                             arrays["source_height_m"].ravel()[cell],
                             arrays["node_world_xyz_m"][node_position, 2]])
            half_width = arrays["node_width_m"][node_position] / 2
            for side, sign in ((0, -1), (2, 1)):
                expected_bank = bank.copy()
                expected_bank[[0, 2]] += sign * normal * half_width
                if not np.array_equal(arrays["edge_sections_xyz_m"][edge_index, endpoint * 3 + side],
                                      expected_bank):
                    raise ValueError("natural geometry bank section differs from node width")
        distance = np.linalg.norm(arrays["node_world_xz_m"][first] - arrays["node_world_xz_m"][second])
        if (distance <= 0 or arrays["node_bed_m"][first] - arrays["node_bed_m"][second] + 1e-9 < slope * distance):
            raise ValueError("natural geometry edge reverses slope")
        bounded = arrays["bounded_bed_m"].ravel()
        failed = bounded[target] > bounded[donor] - slope * spacing + 1e-9
        if failed != arrays["edge_slope_failed_mask"][edge_index]:
            raise ValueError("natural geometry bounded slope diagnostic mismatch")
    if (np.any(arrays["bounded_bed_m"] > arrays["source_height_m"] + 1e-9) or
            np.any(arrays["required_cut_m"] < -1e-9) or
            metadata["summary"]["edge_count"] != len(edges) or
            metadata["summary"]["over_budget_nodes"] != int(budget.sum()) or
            metadata["summary"]["failed_slope_edges"] != int(arrays["edge_slope_failed_mask"].sum()) or
            metadata["summary"]["diagnostic_failure"] != bool(budget.any() or arrays["edge_slope_failed_mask"].any())):
        raise ValueError("natural geometry budget summary invalid")
    if metadata["status"] != ("diagnostic_failure" if metadata["summary"]["diagnostic_failure"] else
                              "diagnostic_not_publishable"):
        raise ValueError("natural geometry status invalid")
    return True


def save_natural_channel_geometry(path, geometry):
    save_bundle(path, geometry, validator=validate_natural_channel_geometry)


def load_natural_channel_geometry(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_natural_channel_geometry)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("natural geometry external identity mismatch")
    return result


def evaluate_natural_channel_window(geometry, network, *, window_origin_m_xz,
                                    spacing_m, shape_zx, recipe=None):
    """Sweep shared centerline sections into one bounded refinement window."""
    validate_natural_channel_geometry(geometry)
    arrays, _ = _network_fields(network)
    if geometry["metadata"]["network_identity_sha256"] != network["identity_sha256"]:
        raise ValueError("geometry and network identity mismatch")
    settings = NaturalGeometryRecipe(**geometry["metadata"]["recipe"])
    if recipe is not None and recipe != settings:
        raise ValueError("window recipe must match shared geometry")
    if (len(shape_zx) != 2 or any(type(size) is not int or size < 2 for size in shape_zx) or
            math.prod(shape_zx) > 250_000 or
            not math.isfinite(spacing_m) or spacing_m <= 0 or
            max((size - 1) * spacing_m for size in shape_zx) > settings.max_window_span_m):
        raise ValueError("window exceeds bounded refinement policy")
    plan = _make_plan(network, settings)
    centerline, _ = _make_centerline(plan, network, settings)
    if centerline["identity_sha256"] != geometry["metadata"]["centerline_identity_sha256"]:
        raise ValueError("stored geometry differs from rebuilt centerline")
    origin_x, origin_z = window_origin_m_xz
    source_origin_x, source_origin_z = geometry["metadata"]["origin_m_xz"]
    coarse_spacing = geometry["metadata"]["spacing_m"]
    x = origin_x + np.arange(shape_zx[1]) * spacing_m
    z = origin_z + np.arange(shape_zx[0]) * spacing_m
    fine_columns = (x - source_origin_x) / coarse_spacing
    fine_rows = (z - source_origin_z) / coarse_spacing
    if (fine_columns.min() < -1e-9 or fine_rows.min() < -1e-9 or
            fine_columns.max() > arrays["valid_mask"].shape[1] - 1 + 1e-9 or
            fine_rows.max() > arrays["valid_mask"].shape[0] - 1 + 1e-9):
        raise ValueError("window exceeds source domain")
    column_low = np.floor(np.clip(fine_columns, 0, arrays["valid_mask"].shape[1] - 1)).astype(int)
    row_low = np.floor(np.clip(fine_rows, 0, arrays["valid_mask"].shape[0] - 1)).astype(int)
    column_high = np.ceil(np.clip(fine_columns - 1e-12, 0, arrays["valid_mask"].shape[1] - 1)).astype(int)
    row_high = np.ceil(np.clip(fine_rows - 1e-12, 0, arrays["valid_mask"].shape[0] - 1)).astype(int)
    protected = np.zeros(tuple(shape_zx), bool)
    unknown = np.zeros(tuple(shape_zx), bool)
    for row_ids in (row_low, row_high):
        for column_ids in (column_low, column_high):
            protected |= arrays["protected_mask"][np.ix_(row_ids, column_ids)]
            unknown |= ~arrays["valid_mask"][np.ix_(row_ids, column_ids)]
    blocked = protected | unknown
    section = evaluate_sections(plan, float(origin_x), float(origin_z), float(spacing_m),
                                float(spacing_m), tuple(shape_zx), blocked,
                                SectionRecipe(settings.max_cut_m, settings.min_cells_across_width),
                                centerline=centerline)
    output_arrays = {**section["arrays"], "unknown_mask": readonly(unknown)}
    output_metadata = {"schema": WINDOW_SCHEMA, "algorithm": WINDOW_SCHEMA,
                       "geometry_identity_sha256": geometry["identity_sha256"],
                       "network_identity_sha256": network["identity_sha256"],
                       "section_identity_sha256": section["identity_sha256"],
                       "source_surface_sha256": array_hash(section["arrays"]["source_surface_m"]),
                       "required_cut_sha256": array_hash(section["arrays"]["required_cut_m"]),
                       "origin_m_xz": [float(origin_x), float(origin_z)],
                       "spacing_m": float(spacing_m), "shape_zx": list(shape_zx),
                       "max_cut_m": settings.max_cut_m,
                       "summary": {**section["summary"],
                           "blocked_by_protection_or_unknown": bool(np.any(section["arrays"]["protected_conflict_mask"])),
                           "trapezoid_cut_volume_m3": section["summary"]["actual_cut_volume_m3"]},
                       **{flag: False for flag in FLAGS}}
    output_metadata["status"] = ("diagnostic_failure" if
        (geometry["metadata"]["summary"]["diagnostic_failure"] or
         section["summary"]["blocked_by_plan"] or section["summary"]["blocked_by_centerline"] or
         output_metadata["summary"]["blocked_by_protection_or_unknown"] or
         section["summary"]["requires_shared_fine_extension"] or
         section["summary"]["needs_refinement_nodes"] > 0)
        else "diagnostic_not_publishable")
    output = {"arrays": {name: readonly(value) for name, value in output_arrays.items()},
              "metadata": output_metadata}
    output["identity_sha256"] = identity(output["arrays"], output_metadata)
    validate_natural_channel_window(output)
    return output


def validate_natural_channel_window(window):
    arrays, metadata = window["arrays"], window["metadata"]
    expected = {"source_surface_m", "required_cut_m", "bounded_surface_m", "actual_cut_m",
                "over_budget_mask", "protected_mask", "protected_conflict_mask",
                "clipped_boundary_mask", "needs_refinement_mask", "unknown_mask"}
    if (metadata.get("schema") != WINDOW_SCHEMA or metadata.get("algorithm") != WINDOW_SCHEMA or
            set(arrays) != expected or any(metadata.get(flag) is not False for flag in FLAGS) or
            window.get("identity_sha256") != identity(arrays, metadata)):
        raise ValueError("natural window identity/schema invalid")
    shape = tuple(metadata["shape_zx"])
    if (len(shape) != 2 or min(shape) < 2 or math.prod(shape) > 250_000 or
            any(value.shape != shape for value in arrays.values())):
        raise ValueError("natural window shape invalid")
    for name in ("source_surface_m", "required_cut_m", "bounded_surface_m", "actual_cut_m"):
        if arrays[name].dtype != np.float64 or not np.isfinite(arrays[name]).all():
            raise ValueError("natural window elevation/cut invalid")
    for name in expected - {"source_surface_m", "required_cut_m", "bounded_surface_m", "actual_cut_m"}:
        if arrays[name].dtype != bool:
            raise ValueError("natural window mask invalid")
    if (not np.allclose(arrays["bounded_surface_m"], arrays["source_surface_m"] - arrays["actual_cut_m"], atol=1e-9, rtol=0) or
            np.any(arrays["actual_cut_m"] < 0) or
            np.any(arrays["actual_cut_m"] - arrays["required_cut_m"] > 1e-9) or
            np.any(arrays["actual_cut_m"][arrays["protected_mask"]] != 0) or
            np.any(arrays["unknown_mask"] & ~arrays["protected_mask"])):
        raise ValueError("natural window material ledger invalid")
    cap = metadata["max_cut_m"]
    if not math.isfinite(cap) or cap < 0:
        raise ValueError("natural window cut cap invalid")
    expected_actual = np.minimum(arrays["required_cut_m"], cap).copy()
    expected_actual[arrays["protected_mask"]] = 0.
    boundary = np.zeros(shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    if (not np.allclose(arrays["actual_cut_m"], expected_actual, atol=1e-9, rtol=0) or
            not np.array_equal(arrays["over_budget_mask"], arrays["required_cut_m"] > cap + 1e-9) or
            not np.array_equal(arrays["protected_conflict_mask"],
                               arrays["protected_mask"] & (arrays["required_cut_m"] > 1e-9)) or
            not np.array_equal(arrays["clipped_boundary_mask"],
                               boundary & (arrays["required_cut_m"] > 1e-9))):
        raise ValueError("natural window cut diagnostics invalid")
    if (metadata["source_surface_sha256"] != array_hash(arrays["source_surface_m"]) or
            metadata["required_cut_sha256"] != array_hash(arrays["required_cut_m"])):
        raise ValueError("natural window source/cut identity mismatch")
    spacing = metadata["spacing_m"]
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("natural window spacing invalid")
    weights = np.ones(shape)
    weights[[0, -1], :] *= .5
    weights[:, [0, -1]] *= .5
    volume = float(np.sum(arrays["actual_cut_m"] * weights) * spacing ** 2)
    if not math.isclose(volume, metadata["summary"]["trapezoid_cut_volume_m3"], abs_tol=1e-7):
        raise ValueError("natural window trapezoid ledger mismatch")
    return True


def save_natural_channel_window(path, window):
    save_bundle(path, window, validator=validate_natural_channel_window)


def load_natural_channel_window(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_natural_channel_window)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("natural window external identity mismatch")
    return result
