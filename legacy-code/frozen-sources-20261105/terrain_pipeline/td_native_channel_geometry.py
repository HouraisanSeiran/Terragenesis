"""Static metric morphology candidates from pinned hierarchy and one v10 hour."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, load_bundle, readonly, save_bundle
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy, validate_basin_hierarchy
from terrain_pipeline.td_basin_storage_v10_io import load_storage, validate_storage


FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable")


@dataclass(frozen=True)
class GeometryRecipe:
    reference_q_m3_s: float = 1.
    reference_width_m: float = 3.
    reference_depth_m: float = .5
    minimum_width_m: float = 1.
    maximum_width_m: float = 30.
    minimum_depth_m: float = .1
    maximum_depth_m: float = 3.
    width_exponent: float = .5
    depth_exponent: float = .3
    active_q_threshold_m3_s: float = 0.

    def __post_init__(self):
        positive = {name: value for name, value in asdict(self).items() if name != "active_q_threshold_m3_s"}
        if any(not math.isfinite(value) or value <= 0 for value in positive.values()):
            raise ValueError("recipe requires finite positive values")
        if not math.isfinite(self.active_q_threshold_m3_s) or self.active_q_threshold_m3_s < 0:
            raise ValueError("active Q threshold must be finite nonnegative")
        if self.minimum_width_m > self.maximum_width_m or self.minimum_depth_m > self.maximum_depth_m:
            raise ValueError("recipe bounds inverted")


def _topology(node_ids, receiver, faces, shape):
    cells = math.prod(shape)
    if (node_ids.dtype != np.int64 or node_ids.ndim != 1 or
            np.any((node_ids < 0) | (node_ids >= cells)) or
            np.any(np.diff(node_ids) <= 0) or receiver.shape != node_ids.shape or
            receiver.dtype != np.int64 or np.any(receiver < -1)):
        raise ValueError("node IDs/receiver invalid or duplicated")
    known = set(node_ids.tolist())
    if any(int(target) not in known for target in receiver if target >= 0):
        raise ValueError("topology is not closed")
    if faces.dtype != np.int64 or faces.ndim != 2 or faces.shape[1] != 2:
        raise ValueError("face shape/type invalid")
    pairs = set()
    for first, second in faces:
        if first not in known or second not in known or first >= second:
            raise ValueError("invalid or zero-length face")
        if abs(first // shape[1] - second // shape[1]) + abs(first % shape[1] - second % shape[1]) != 1:
            raise ValueError("non-D4 face")
        if (int(first), int(second)) in pairs:
            raise ValueError("duplicate face")
        pairs.add((int(first), int(second)))
    mapping = dict(zip(node_ids.tolist(), receiver.tolist()))
    completed = set()
    for first in node_ids:
        path = set()
        cell = int(first)
        while cell >= 0 and cell not in completed:
            if cell in path:
                raise ValueError("receiver cycle")
            path.add(cell)
            target = mapping[cell]
            if target >= 0 and tuple(sorted((cell, target))) not in pairs:
                raise ValueError("receiver missing D4 face")
            cell = target
        completed.update(path)


def build_channel_geometry(hierarchy, hour_page, recipe=GeometryRecipe()):
    """All valid receiver links, including dry links; no inferred flow completion."""
    validate_basin_hierarchy(hierarchy)
    validate_storage(hour_page)
    topology, page = hierarchy["arrays"], hour_page["arrays"]
    grid, hour = hierarchy["metadata"], hour_page["metadata"]
    if hour["hierarchy_identity"] != hierarchy["identity_sha256"]:
        raise ValueError("page hierarchy identity mismatch")
    for name in ("height_m", "valid_mask", "receiver", "face_cells", "boundary_cells"):
        if not np.array_equal(topology[name], page[name]):
            raise ValueError("page topology mismatch: " + name)
    if any(grid[name] != hour[name] for name in ("spacing_m", "origin_m_xz")):
        raise ValueError("page coordinate mismatch")
    node_ids = np.flatnonzero(topology["valid_mask"].ravel()).astype(np.int64)
    receivers = topology["receiver"][node_ids]
    shape = topology["height_m"].shape
    _topology(node_ids, receivers, topology["face_cells"], shape)
    routed = np.zeros(topology["height_m"].size)
    first, second = page["face_cells"].T
    for source, target, volume in ((first, second, page["face_forward_m3"]),
                                  (second, first, page["face_reverse_m3"])):
        follows = topology["receiver"][source] == target
        np.add.at(routed, source[follows], volume[follows])
    if not np.allclose(routed, page["routed_volume_m3"], rtol=1e-10, atol=1e-8):
        raise ValueError("page receiver interval volume mismatch")
    bed = topology["height_m"].ravel()[node_ids]
    depth = page["depth_m"][-1, node_ids]
    q_mean = page["routed_volume_m3"][node_ids] / 3600.
    own_active, inherited_width, inherited_incision, width, incision = _node_shapes(node_ids, receivers, q_mean, recipe)
    candidate_bed = bed - incision
    origin = grid["origin_m_xz"]
    world = np.column_stack((origin[0] + node_ids % shape[1] * grid["spacing_m"],
                             candidate_bed, origin[1] + node_ids // shape[1] * grid["spacing_m"]))
    sources = node_ids[receivers >= 0]
    targets = receivers[receivers >= 0]
    edges = np.column_stack((sources, targets)).astype(np.int64)
    indices = np.searchsorted(node_ids, edges)
    centerline = world[indices]
    direction = centerline[:, 1, [0, 2]] - centerline[:, 0, [0, 2]]
    perpendicular = np.column_stack((-direction[:, 1], direction[:, 0])) / grid["spacing_m"]
    sections = np.repeat(centerline[:, :, None, :], 3, axis=2)
    for side, sign in ((0, -1), (2, 1)):
        sections[:, :, side, 0] += sign * perpendicular[:, None, 0] * width[indices] / 2
        sections[:, :, side, 2] += sign * perpendicular[:, None, 1] * width[indices] / 2
        sections[:, :, side, 1] = bed[indices]
    boundary = np.isin(node_ids, topology["boundary_cells"])
    arrays = dict(node_cell_ids=node_ids, node_receiver_cell_ids=receivers,
                  node_world_xyz_m=world, node_native_bed_m=bed,
                  node_candidate_bed_m=candidate_bed, node_hour_end_water_depth_m=depth,
                  node_hour_end_surface_sample_m=bed + depth,
                  node_receiver_interval_mean_q_m3_s=q_mean,
                  node_width_m=width, node_candidate_incision_m=incision,
                  node_geometry_active=width > 0, node_receiver_geometry_active=own_active,
                  node_incoming_shape_width_m=inherited_width, node_incoming_shape_incision_m=inherited_incision,
                  node_engineering_boundary=boundary,
                  node_internal_sink=(receivers < 0) & ~boundary,
                  edge_cell_ids=edges, edge_geometry_active=own_active[indices[:, 0]], edge_centerline_xyz_m=centerline,
                  edge_sections_xyz_m=sections.reshape(len(edges), 6, 3), actual_face_cells=page["face_cells"].copy())
    for name in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        arrays["actual_" + name] = page[name].copy()
    metadata = dict(schema="td-native-channel-geometry-v1", algorithm="static-D4-shared-nodes-recipe-v1",
                    hierarchy_identity=hierarchy["identity_sha256"], hour_page_identity=hour_page["identity_sha256"],
                    forcing_identity=hour["forcing_identity"], start_s=hour["start_s"], end_s=hour["end_s"],
                    grid_shape=list(shape), spacing_m=grid["spacing_m"], origin_m_xz=list(origin),
                    coordinates="arrays [z,x]; x east, z south; world [x,y,z] in metres",
                    recipe=asdict(recipe), scope="diagnostic single saved hour; numerical acceptance unverified",
                    q_semantics="page receiver volume / 3600; interval mean morphology prior, not instantaneous Q",
                    geometry_semantics="candidate bed and edge-oriented schematic sections; not carved source or 3D hydraulics",
                    section_point_order="source left/center/right, target left/center/right; left relative to static receiver direction",
                    shape_semantics="Q strictly above declared threshold activates receiver edge; node width/incision=max(own active edge recipe, actual incoming active edge recipe); no Q inheritance or downstream extension",
                    junction_semantics="shared candidate centerline endpoints only; edge-normal sections are not a unified joint surface; inactive edge sections are placeholders",
                    surface_semantics="native bed + actual hour-end depth at nodes only; no continuous water surface",
                    flow_semantics="all actual bidirectional faces retained; no static-tree continuity assertion",
                    **{name: False for name in FLAGS})
    result = dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
    validate_channel_geometry(result)
    result["arrays"] = {name: readonly(values) for name, values in arrays.items()}
    return result


def _node_shapes(node_ids, receiver, q_mean, recipe):
    active = (q_mean > recipe.active_q_threshold_m3_s) & (receiver >= 0)
    ratio = q_mean / recipe.reference_q_m3_s
    own_width = np.where(active, np.clip(recipe.reference_width_m * ratio ** recipe.width_exponent,
                                       recipe.minimum_width_m, recipe.maximum_width_m), 0.)
    own_incision = np.where(active, np.clip(recipe.reference_depth_m * ratio ** recipe.depth_exponent,
                                          recipe.minimum_depth_m, recipe.maximum_depth_m), 0.)
    incoming_width = np.zeros(len(node_ids))
    incoming_incision = np.zeros(len(node_ids))
    targets = np.searchsorted(node_ids, receiver[active])
    np.maximum.at(incoming_width, targets, own_width[active])
    np.maximum.at(incoming_incision, targets, own_incision[active])
    return active, incoming_width, incoming_incision, np.maximum(own_width, incoming_width), np.maximum(own_incision, incoming_incision)


def validate_channel_geometry(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("schema") != "td-native-channel-geometry-v1" or any(metadata.get(name) is not False for name in FLAGS):
        raise ValueError("geometry schema/certification invalid")
    if result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("geometry identity mismatch")
    recipe = GeometryRecipe(**metadata["recipe"])
    shape = metadata["grid_shape"]
    if len(shape) != 2 or any(type(size) is not int or size <= 0 for size in shape):
        raise ValueError("grid shape invalid")
    spacing = metadata["spacing_m"]
    origin = metadata["origin_m_xz"]
    if not math.isfinite(spacing) or spacing <= 0 or len(origin) != 2 or not np.isfinite(origin).all():
        raise ValueError("coordinate invalid")
    if metadata["end_s"] - metadata["start_s"] != 3600 or not math.isfinite(metadata["start_s"]):
        raise ValueError("hour interval invalid")
    for name in ("hierarchy_identity", "hour_page_identity", "forcing_identity"):
        value = metadata[name]
        if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("source identity invalid")
    if any(not np.isfinite(values).all() for values in arrays.values()):
        raise ValueError("nonfinite geometry")
    node_ids, receiver = arrays["node_cell_ids"], arrays["node_receiver_cell_ids"]
    _topology(node_ids, receiver, arrays["actual_face_cells"], shape)
    count = len(node_ids)
    for name in ("node_native_bed_m", "node_candidate_bed_m", "node_hour_end_water_depth_m",
                 "node_hour_end_surface_sample_m", "node_receiver_interval_mean_q_m3_s",
                 "node_width_m", "node_candidate_incision_m", "node_engineering_boundary", "node_internal_sink"):
        if arrays[name].shape != (count,):
            raise ValueError("node attribute shape invalid")
    for name in ("node_engineering_boundary", "node_internal_sink"):
        if arrays[name].dtype != bool:
            raise ValueError("node classification type invalid")
    if not np.array_equal(arrays["node_internal_sink"], (receiver < 0) & ~arrays["node_engineering_boundary"]):
        raise ValueError("sink classification invalid")
    edges = np.column_stack((node_ids[receiver >= 0], receiver[receiver >= 0]))
    if not np.array_equal(arrays["edge_cell_ids"], edges):
        raise ValueError("edges not closed over receiver topology")
    indices = np.searchsorted(node_ids, edges)
    world = arrays["node_world_xyz_m"]
    if world.shape != (count, 3) or not np.array_equal(arrays["edge_centerline_xyz_m"], world[indices]):
        raise ValueError("centerline/shared junction invalid")
    expected_world = np.column_stack((origin[0] + node_ids % shape[1] * spacing,
                                     arrays["node_candidate_bed_m"], origin[1] + node_ids // shape[1] * spacing))
    if not np.array_equal(world, expected_world):
        raise ValueError("world coordinates invalid")
    bed, depth = arrays["node_native_bed_m"], arrays["node_hour_end_water_depth_m"]
    q_mean = arrays["node_receiver_interval_mean_q_m3_s"]
    if np.any(depth < 0) or np.any(q_mean < 0) or not np.array_equal(arrays["node_hour_end_surface_sample_m"], bed + depth):
        raise ValueError("sample depth/surface invalid")
    _validate_actual_faces(arrays, node_ids, receiver, q_mean)
    active, inherited_width, inherited_incision, width, incision = _node_shapes(node_ids, receiver, q_mean, recipe)
    for name, expected in (("node_receiver_geometry_active", active), ("node_geometry_active", width > 0),
                           ("node_incoming_shape_width_m", inherited_width), ("node_incoming_shape_incision_m", inherited_incision),
                           ("edge_geometry_active", active[indices[:, 0]])):
        if not np.array_equal(arrays[name], expected):
            raise ValueError("explicit geometry activity/incoming shape mismatch")
    if (not np.array_equal(arrays["node_width_m"], width) or not np.array_equal(arrays["node_candidate_incision_m"], incision)
            or not np.array_equal(arrays["node_candidate_bed_m"], bed - incision)):
        raise ValueError("candidate recipe mismatch")
    sections = arrays["edge_sections_xyz_m"]
    if sections.shape != (len(edges), 6, 3):
        raise ValueError("section shape invalid")
    sections = sections.reshape(len(edges), 2, 3, 3)
    if not np.array_equal(sections[:, :, 1], world[indices]):
        raise ValueError("section shape/center invalid")
    direction = world[indices][:, 1, [0, 2]] - world[indices][:, 0, [0, 2]]
    perpendicular = np.column_stack((-direction[:, 1], direction[:, 0])) / spacing
    expected_sections = np.repeat(world[indices][:, :, None, :], 3, axis=2)
    for side, sign in ((0, -1), (2, 1)):
        expected_sections[:, :, side, 0] += sign * perpendicular[:, None, 0] * width[indices] / 2
        expected_sections[:, :, side, 2] += sign * perpendicular[:, None, 1] * width[indices] / 2
        expected_sections[:, :, side, 1] = bed[indices]
    if not np.array_equal(sections, expected_sections):
        raise ValueError("section recipe geometry invalid")
    return True


def _validate_actual_faces(arrays, node_ids, receiver, q_mean):
    faces = arrays["actual_face_cells"]
    routed = np.zeros(len(node_ids))
    positions = np.searchsorted(node_ids, faces)
    for direction, source_column, target_column in (("forward", 0, 1), ("reverse", 1, 0)):
        volume = arrays["actual_face_" + direction + "_m3"]
        activity = arrays["actual_active_" + direction + "_s"]
        for values in (volume, activity):
            if values.dtype != np.float64 or values.shape != (len(faces),) or not np.isfinite(values).all() or np.any(values < 0):
                raise ValueError("actual directional evidence shape/type/positivity invalid")
        if np.any(activity > 3600.) or np.any((volume == 0) != (activity == 0)):
            raise ValueError("actual directional volume/activity mismatch")
        sources = positions[:, source_column]
        follows = receiver[sources] == faces[:, target_column]
        np.add.at(routed, sources[follows], volume[follows])
    if np.any(arrays["actual_active_forward_s"] + arrays["actual_active_reverse_s"] > 3600. + 1e-8):
        raise ValueError("combined actual activity exceeds hour")
    if not np.array_equal(q_mean, routed / 3600.):
        raise ValueError("interval mean Q differs from actual directional faces")


def load_geometry_inputs(hierarchy_record, hour_page_record, *, load_order=("hierarchy", "hour_page")):
    if tuple(sorted(load_order)) != ("hierarchy", "hour_page"):
        raise ValueError("load order must cover each input once")
    records = (hierarchy_record, hour_page_record)
    _check_input_pins(records)
    loaders = dict(hierarchy=lambda: load_basin_hierarchy(**hierarchy_record),
                   hour_page=lambda: load_storage(**hour_page_record))
    loaded = {name: loaders[name]() for name in load_order}
    _check_input_pins(records)
    return loaded["hierarchy"], loaded["hour_page"]


def _check_input_pins(records):
    for record in records:
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("source chain SHA changed or mismatched")


def save_channel_geometry(path, result):
    save_bundle(path, result, validator=validate_channel_geometry)


def load_channel_geometry(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_channel_geometry,
                         max_bytes=128 * 1024 * 1024)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external geometry identity mismatch")
    return result
