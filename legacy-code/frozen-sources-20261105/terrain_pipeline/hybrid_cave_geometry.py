"""Bounded sampled rock Boolean and independently identifiable conduit charts."""

from dataclasses import asdict, dataclass
import json
import math

import numpy as np
import psutil

from terrain_pipeline.hybrid_river_graph import identity, load_graph, native_bed_pieces
from terrain_pipeline import td_source_conforming_banks as source
from terrain_pipeline.td_shared_channel_fine import _center_cut, compact_node_fans

SCHEMA = "td-hybrid-river-geometry-v1"
MAX_BYTES = 64 * 1024**2
MAX_RSS = 1024**3
MAX_GRID = 300_000
POLICY = {
    "version": "local-rock-boolean-multichart-v1",
    "terrain": "original_native_bilinear_minus_independently_passed_saved_affine_cut_fans",
    "solid": "sampled_piecewise_planar_top_closed_sides_bottom_not_native_exact_not_fine_replacement",
    "excavation": "Mesh64_local_origin_closed_rock_minus_closed_derived_cutter_actual_volume",
    "geology": "generated_hermite_route_sine_squared_burial_not_surveyed",
    "portals": "immutable_complete_native_floor_with_engineered_ceiling_surface_ramp_openings",
    "vdm": "new_transverse_and_vertical_multichart_reference_plus_displacement_not_old_metric_vdm",
    "water": "not_generated_solid_banks_distinct_from_free_water",
    "protection": "unknown_protected_unselected_or_wet_native_support_refused_without_clamping",
    "hydraulics": "final_actual_ring_storage_sections_engineering_pressure_slot_no_solver",
}
POLICY_SHA256 = identity(POLICY)


@dataclass(frozen=True)
class Parameters:
    rock_spacing_m: float = 1.
    stations: int = 17
    burial_m: float = 6.
    ceiling_clearance_m: float = 2.
    crop_margin_m: float = 8.
    bottom_margin_m: float = 5.
    vdm_amplitude_m: float = .12
    roughness_manning: float = .035
    pressure_slot_width_m: float = .02

    def __post_init__(self):
        if not all(math.isfinite(value) and value > 0 for key, value in asdict(self).items() if key != "stations"):
            raise ValueError("positive finite explicit engineering parameters required")
        if not .175 <= self.rock_spacing_m <= 2. or type(self.stations) is not int or not 9 <= self.stations <= 33:
            raise ValueError("bounded rock resolution/stations required")
        if self.burial_m > 30 or self.ceiling_clearance_m > 8 or self.crop_margin_m > 30:
            raise ValueError("local engineering geometry bounds exceeded")


def guard():
    memory = psutil.Process().memory_info()
    if max(memory.rss, getattr(memory, "peak_wset", 0)) > MAX_RSS:
        raise MemoryError("whole_geometry_1GiB_budget_exceeded")
    return max(memory.rss, getattr(memory, "peak_wset", 0))


def seal(record):
    record.pop("identity_sha256", None)
    record["identity_sha256"] = identity(record)
    return record


class BedSampler:
    def __init__(self, context, fans):
        self.context = context
        self.fans = fans
        self.bins = {}
        for ordinal, fan in enumerate(fans):
            vertices = np.asarray(fan["vertices_xz_m"])
            low, high = np.floor(vertices.min(axis=0) / 10).astype(int), np.floor(vertices.max(axis=0) / 10).astype(int)
            for column in range(low[0], high[0] + 1):
                for row in range(low[1], high[1] + 1):
                    self.bins.setdefault((column, row), []).append(ordinal)

    def __call__(self, point):
        point = np.asarray(point, float)
        sample = source._source_sample(self.context, *point)
        if sample["rejection_reasons"] or sample["height_m"] is None or sample["wet_source_support"]:
            raise ValueError("source_gate:" + ",".join(sample["rejection_reasons"] or ["wet_native_support"]) + ":" + str(point.tolist()))
        cuts, keys = [], []
        for ordinal in self.bins.get(tuple(np.floor(point / 10).astype(int)), []):
            fan = self.fans[ordinal]
            cut = _center_cut(fan, point)
            if cut is not None:
                cuts.append(cut)
                keys.append(fan["fan_key"])
        if cuts and max(cuts) - min(cuts) > 1e-9:
            raise ValueError("saved_fan_shared_function_mismatch")
        cut = cuts[0] if cuts else 0.
        return {"source_sample": sample, "cut_depth_m": cut, "fan_keys": keys,
                "derived_bed_m": sample["height_m"] - cut}


def portal_knots(port):
    if port["status"] != "candidate" or port["rejection_reasons"]:
        raise ValueError("refused actual canonical profile")
    native_bed_pieces(port)
    values = {0., 1., 2., 3.}
    for ordinal, segment in enumerate(port["profile"]["profile_segments"]):
        for piece in segment["native_pieces"]:
            if piece["source"]["source_coefficients_m_t012"][2] != 0.:
                raise ValueError("quadratic_portal_floor_requires_new_exact_interface")
            values.update(ordinal + bound for bound in piece["interval_t01"])
    return values


def portal_point(port, parameter):
    original = port["profile"]["profile_xyz_m"]
    if parameter in (0., 1., 2., 3.):
        return np.array(original[int(parameter)], float)
    ordinal = min(int(parameter), 2)
    fraction = parameter - ordinal
    segment = port["profile"]["profile_segments"][ordinal]
    for piece in segment["native_pieces"]:
        lower, upper = piece["interval_t01"]
        if lower <= fraction <= upper:
            local = (fraction - lower) / (upper - lower)
            if fraction == lower:
                point = np.array(piece["start_xz_m"], float)
            elif fraction == upper:
                point = np.array(piece["end_xz_m"], float)
            else:
                point = (1. - local) * np.array(piece["start_xz_m"]) + local * np.array(piece["end_xz_m"])
            coefficients = piece["source"]["source_coefficients_m_t012"]
            cut = piece["depth_coefficients_m_t01"]
            depth = cut[0] if local == 0 else cut[0] + cut[1] if local == 1 else (1. - local) * cut[0] + local * (cut[0] + cut[1])
            if not 0 <= depth <= 4:
                raise ValueError("strict_negative_or_maxcut_portal_depth")
            height = coefficients[0] + coefficients[1] * local + coefficients[2] * local**2 - depth
            return np.array([point[0], height, point[1]])
    raise ValueError("canonical_native_profile_gap")


def build_charts(sink, spring, sink_xyz, spring_xyz, parameters):
    knots = sorted(portal_knots(sink) | portal_knots(spring))
    floor_ends = [np.array([portal_point(port, value) for value in knots]) for port in (sink, spring)]
    origins = np.array([sink_xyz, spring_xyz], float)
    distance = float(np.linalg.norm((origins[1] - origins[0])[[0, 2]]))
    if not 30 <= distance <= 400:
        raise ValueError("explicit_pair_outside_bounded_route_length")
    directions = np.array([sink["flow_unit_xz"], spring["flow_unit_xz"]])
    tangent_scale = min(distance * .6, 60.)
    stations = []
    for ordinal, fraction in enumerate(np.linspace(0., 1., parameters.stations)):
        complement = 1. - fraction
        horizontal = ((2 * fraction**3 - 3 * fraction**2 + 1) * origins[0, [0, 2]]
            + (-2 * fraction**3 + 3 * fraction**2) * origins[1, [0, 2]]
            + (fraction**3 - 2 * fraction**2 + fraction) * tangent_scale * directions[0]
            + (fraction**3 - fraction**2) * tangent_scale * directions[1])
        tangent = ((6 * fraction**2 - 6 * fraction) * origins[0, [0, 2]]
            + (-6 * fraction**2 + 6 * fraction) * origins[1, [0, 2]]
            + (3 * fraction**2 - 4 * fraction + 1) * tangent_scale * directions[0]
            + (3 * fraction**2 - 2 * fraction) * tangent_scale * directions[1])
        tangent /= np.linalg.norm(tangent)
        transverse = np.array([-tangent[1], tangent[0]])
        burial = parameters.burial_m * math.sin(math.pi * fraction)**2 if ordinal not in (0, parameters.stations - 1) else 0.
        origin = np.array([horizontal[0], complement * origins[0, 1] + fraction * origins[1, 1] - burial, horizontal[1]])
        floor = []
        for first, second in zip(*floor_ends):
            offset_first = (first[[0, 2]] - origins[0, [0, 2]]) @ np.array([-directions[0, 1], directions[0, 0]])
            offset_second = (second[[0, 2]] - origins[1, [0, 2]]) @ np.array([-directions[1, 1], directions[1, 0]])
            offset = complement * offset_first + fraction * offset_second
            point = np.array([horizontal[0] + offset * transverse[0], complement * first[1] + fraction * second[1] - burial, horizontal[1] + offset * transverse[1]])
            floor.append(point)
        floor = np.array(floor)
        if ordinal == 0:
            floor = floor_ends[0].copy()
            origin = origins[0].copy()
            transverse = np.array([-directions[0, 1], directions[0, 0]])
        elif ordinal == parameters.stations - 1:
            floor = floor_ends[1].copy()
            origin = origins[1].copy()
            transverse = np.array([-directions[1, 1], directions[1, 0]])
        roof_y = float(floor[:, 1].max() + parameters.ceiling_clearance_m)
        roof_first, roof_last = floor[0].copy(), floor[-1].copy()
        roof_first[1] = roof_last[1] = roof_y
        reference = np.vstack((floor, roof_last, roof_first))
        displacement = np.zeros_like(reference)
        if ordinal not in (0, parameters.stations - 1):
            amplitude = parameters.vdm_amplitude_m * math.sin(math.pi * fraction)**2
            displacement[-2, [0, 2]] = amplitude * transverse
            displacement[-1, [0, 2]] = -amplitude * transverse
            displacement[-2:, 1] = amplitude * math.cos(4 * math.pi * fraction)
        derived = reference + displacement
        stations.append({"station_id": "gallery:" + str(ordinal), "fraction": float(fraction),
            "origin_xyz_m": origin.tolist(), "transverse_unit_xz": transverse.tolist(),
            "reference_ring_xyz_m": reference.tolist(), "displacement_ring_xyz_m": displacement.tolist(),
            "derived_ring_xyz_m": derived.tolist(), "floor_vertex_count": len(knots)})
    triangles = sweep_triangles(stations)
    horizontal_rings = [np.array(station["derived_ring_xyz_m"])[:, [0, 2]] for station in stations]
    swept_bounds = [(np.vstack((first, second)).min(axis=0), np.vstack((first, second)).max(axis=0))
        for first, second in zip(horizontal_rings, horizontal_rings[1:])]
    for first_index, (first_low, first_high) in enumerate(swept_bounds):
        for second_low, second_high in swept_bounds[first_index + 2:]:
            if np.all(np.minimum(first_high, second_high) - np.maximum(first_low, second_low) > 1e-8):
                raise ValueError("nonadjacent_sweep_projection_overlap_not_certified")
    local_vertices = np.array([station["derived_ring_xyz_m"] for station in stations]).reshape(-1, 3) - origins[0]
    if signed_volume(local_vertices, triangles) < 0:
        triangles = [triangle[::-1] for triangle in triangles]
    return seal({"schema": "td-hybrid-multichart-vdm-v1", "stations": stations, "triangles": triangles,
        "profile_parameters": knots, "immutable_portal_station_ids": [stations[0]["station_id"], stations[-1]["station_id"]],
        "old_fixed_chart_vdm_accepted": False, "reference_rule": "generated_baseline_conduit_chart_bound_to_original_port_profiles_not_original_TD_surface",
        "displacement_rule": "zero_floor_and_portals_variable_ceiling_transverse_and_vertical_sine"})


def sweep_triangles(stations):
    import manifold3d as manifold
    count = len(stations[0]["derived_ring_xyz_m"])
    triangles = []
    for ordinal in range(len(stations) - 1):
        for offset in range(count):
            following = (offset + 1) % count
            first, second = ordinal * count + offset, ordinal * count + following
            third, fourth = first + count, second + count
            triangles.extend(([first, second, fourth], [first, fourth, third]))
    for ordinal, reverse in ((0, True), (len(stations) - 1, False)):
        station = stations[ordinal]
        vertices = np.asarray(station["derived_ring_xyz_m"])
        origin = np.asarray(station["origin_xyz_m"])
        transverse = np.asarray(station["transverse_unit_xz"])
        polygon = np.column_stack(((vertices[:, [0, 2]] - origin[[0, 2]]) @ transverse, vertices[:, 1] - origin[1]))
        for triangle in manifold.triangulate([polygon], allow_convex=False):
            indices = [int(value) + ordinal * count for value in triangle]
            triangles.append(indices[::-1] if reverse else indices)
    return triangles


def signed_volume(vertices, triangles):
    points = np.asarray(vertices, float)[np.asarray(triangles, int)]
    return float(np.einsum("ij,ij->i", points[:, 0], np.cross(points[:, 1], points[:, 2])).sum() / 6.)


def mesh_record(vertices, triangles, origin, role):
    vertices = np.asarray(vertices, float)
    triangles = np.asarray(triangles, int)
    if not np.isfinite(vertices).all() or vertices.ndim != 2 or vertices.shape[1] != 3:
        raise ValueError("invalid solid vertices")
    if signed_volume(vertices, triangles) < 0:
        triangles = triangles[:, ::-1]
    uses = {}
    for triangle in triangles:
        if len(set(triangle)) != 3 or min(triangle) < 0 or max(triangle) >= len(vertices):
            raise ValueError("invalid_solid_triangle")
        for first, second in zip(triangle, np.roll(triangle, -1)):
            uses.setdefault(tuple(sorted((int(first), int(second)))), []).append((int(first), int(second)))
    if any(len(sides) != 2 or sides[0] != sides[1][::-1] for sides in uses.values()):
        raise ValueError("solid_is_not_closed_reverse_two_use_manifold")
    return seal({"schema": "td-hybrid-local-solid-mesh-v1", "role": role,
        "local_origin_xyz_m": list(origin), "vertices_local_xyz_m": vertices.tolist(), "triangles": triangles.tolist(),
        "signed_volume_m3": signed_volume(vertices, triangles), "sampled_not_native_exact": True})


def manifold_from_record(record):
    import manifold3d as manifold
    solid = manifold.Manifold(manifold.Mesh64(np.array(record["vertices_local_xyz_m"], dtype=np.float64, order="C", copy=True),
        np.array(record["triangles"], dtype=np.uint64, order="C", copy=True)))
    if solid.status() != manifold.Error.NoError or solid.is_empty():
        raise ValueError("invalid_closed_manifold:" + str(solid.status()))
    if solid.volume() <= 0:
        raise ValueError("nonpositive_solid_volume")
    return solid


def save_manifold(solid, origin, role):
    mesh = solid.to_mesh64()
    return mesh_record(np.array(mesh.vert_properties[:, :3], copy=True), np.array(mesh.tri_verts, copy=True), origin, role)


def build_rock(vdm, sampler, parameters, origin):
    rings = np.array([station["derived_ring_xyz_m"] for station in vdm["stations"]])
    low = np.floor((rings[:, :, [0, 2]].min(axis=(0, 1)) - parameters.crop_margin_m) / parameters.rock_spacing_m) * parameters.rock_spacing_m
    high = np.ceil((rings[:, :, [0, 2]].max(axis=(0, 1)) + parameters.crop_margin_m) / parameters.rock_spacing_m) * parameters.rock_spacing_m
    counts = np.rint((high - low) / parameters.rock_spacing_m).astype(int) + 1
    columns, rows = map(int, counts)
    if columns * rows > MAX_GRID:
        raise ValueError("whole_rock_grid_budget_exceeded_no_crop_truncation")
    bottom = float(rings[:, :, 1].min() - parameters.bottom_margin_m)
    vertices, samples = [], []
    for row in range(rows):
        for column in range(columns):
            point = low + np.array([column, row]) * parameters.rock_spacing_m
            result = sampler(point)
            samples.append({"row": row, "column": column, "xz_m": point.tolist(), **result})
            if result["derived_bed_m"] <= bottom:
                raise ValueError("rock_bottom_above_sampled_top")
            vertices.append([point[0] - origin[0], result["derived_bed_m"] - origin[1], point[1] - origin[2]])
        if row % 16 == 0:
            guard()
    triangles = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            first = row * columns + column
            triangles.extend(([first, first + columns, first + columns + 1], [first, first + columns + 1, first + 1]))
    perimeter = list(range(columns)) + [row * columns + columns - 1 for row in range(1, rows)]
    perimeter += list(range((rows - 1) * columns + columns - 2, (rows - 1) * columns - 1, -1))
    perimeter += [row * columns for row in range(rows - 2, 0, -1)]
    bottom_ids = []
    for index in perimeter:
        bottom_ids.append(len(vertices))
        point = vertices[index]
        vertices.append([point[0], bottom - origin[1], point[2]])
    for ordinal in range(len(perimeter)):
        following = (ordinal + 1) % len(perimeter)
        first, second = perimeter[ordinal], perimeter[following]
        third, fourth = bottom_ids[ordinal], bottom_ids[following]
        triangles.extend(([first, second, fourth], [first, fourth, third]))
    center_id = len(vertices)
    vertices.append([(low[0] + high[0]) / 2 - origin[0], bottom - origin[1], (low[1] + high[1]) / 2 - origin[2]])
    for first, second in zip(bottom_ids, bottom_ids[1:] + bottom_ids[:1]):
        triangles.append([center_id, first, second])
    record = mesh_record(vertices, triangles, origin, "rock_before")
    sampling = seal({"schema": "td-hybrid-rock-source-sampling-v1", "origin_xz_m": low.tolist(), "spacing_m": parameters.rock_spacing_m,
        "rows": rows, "columns": columns, "top_vertex_count": rows * columns, "bottom_elevation_m": bottom,
        "samples": samples, "native_exact": False, "fine15_replaced": False})
    return record, sampling


def ray_hits(solid, first, second, origin):
    hits = solid.ray_cast(tuple(np.array(first) - origin), tuple(np.array(second) - origin))
    return [{"face_id": int(hit.face_id), "distance": float(hit.distance),
        "position_xyz_m": (np.array(hit.position) + origin).tolist()} for hit in hits]


def closed_rock_section(containment):
    covered = all(item["actual_sampled_top_cover_m"] is not None and item["actual_sampled_top_cover_m"] > 0. for item in containment)
    roof_cover = min((item["actual_sampled_top_cover_m"] if item["actual_sampled_top_cover_m"] is not None else -math.inf for item in containment[-2:]))
    return bool(covered and roof_cover >= .5)


def void_witnesses(before, after, removed, vdm, origin, sampler):
    stations = vdm["stations"]
    path = []
    for station in stations:
        ring = np.asarray(station["derived_ring_xyz_m"])
        count = station["floor_vertex_count"]
        transverse = np.array(station["transverse_unit_xz"])
        point = np.array(station["origin_xyz_m"])
        floor = ring[:count]
        offsets = (floor[:, [0, 2]] - point[[0, 2]]) @ transverse
        point[1] = float(np.interp(0., offsets, floor[:, 1]) + .35)
        if point[1] >= ring[-2:, 1].min():
            raise ValueError("no_positive_portal_air_clearance")
        path.append(point.tolist())
    segments = []
    for first, second in zip(path, path[1:]):
        hits = ray_hits(after, first, second, origin)
        if hits:
            raise ValueError("actual_rock_blocks_continuous_air_path")
        segments.append({"from_xyz_m": first, "to_xyz_m": second, "rock_after_hits": hits})
    openings = {}
    for kind, indices in (("sink", range(1, len(path) // 2)), ("spring", range(len(path) - 2, len(path) // 2, -1))):
        witness = None
        for ordinal in indices:
            inside = path[ordinal]
            terrain = sampler(np.array(inside)[[0, 2]])
            if inside[1] >= terrain["derived_bed_m"] - .05:
                continue
            above = [inside[0], terrain["derived_bed_m"] + 3., inside[2]]
            old_hits = ray_hits(before, above, inside, origin)
            new_hits = ray_hits(after, above, inside, origin)
            if old_hits and not new_hits:
                witness = {"station_id": stations[ordinal]["station_id"], "above_xyz_m": above, "inside_xyz_m": inside,
                    "rock_before_hits": old_hits, "rock_after_hits": new_hits, "source_bed_witness": terrain,
                    "opening_kind": "actual_terrain_top_ramp_aperture_not_entire_planar_port_cap"}
                break
        if witness is None:
            raise ValueError("actual_" + kind + "_terrain_opening_not_verified")
        openings[kind] = witness
    if len(removed.decompose()) != 1:
        raise ValueError("excavated_cavity_not_one_connected_solid")
    return path, segments, openings


def cell_record(station, region, arc_id, length, parameters, reference, *, closed_rock=False):
    ring = np.array(station["derived_ring_xyz_m"])
    if region == "underground" and not closed_rock:
        ring = ring[:station["floor_vertex_count"]]
    origin = np.array(station["origin_xyz_m"])
    transverse = np.array(station["transverse_unit_xz"])
    shape = np.column_stack(((ring[:, [0, 2]] - origin[[0, 2]]) @ transverse, ring[:, 1])).tolist()
    underground = region == "underground" and closed_rock
    section = {"kind": "closed_polygon", "polygon_transverse_elevation_m": shape,
        "pressure_slot_width_m": parameters.pressure_slot_width_m} if underground else {
        "kind": "open_polyline", "polyline_transverse_elevation_m": shape,
        "sidewall_extension": "explicit_engineering_vertical"}
    return {"cell_id": station["station_id"], "kind": "underground" if underground else "surface", "route_region": region,
        "graph_arc_id": arc_id, "length_m": length, "roughness_manning": parameters.roughness_manning,
        "physical_section_scope": "actual_rock_enclosed_cutter_ring" if underground else "actual_open_floor_engineered_vertical_overflow_walls",
        "section": section, "section_geometry_reference": {"station_id": station["station_id"],
            "derived_ring_xyz_m": ring.tolist(), "origin_xyz_m": origin.tolist(),
            "transverse_unit_xz": transverse.tolist(), **reference}}


def surface_cell(attachment, port, sampler, region, parameters):
    record = attachment["surface_node_record"]
    arm = next(arm for arm in record["arms"] if arm["arc_id"] == port["arc_id"])
    vertices = np.asarray(record["geometry"]["vertices_xyz_m"])
    inner = vertices[arm["inner_vertex_ids"]]
    midpoint = np.array(port["midpoint_xz_m"])
    origin_xz = (inner[1, [0, 2]] + inner[2, [0, 2]]) / 2.
    transverse = np.array([-port["flow_unit_xz"][1], port["flow_unit_xz"][0]])
    order = np.argsort((inner[:, [0, 2]] - origin_xz) @ transverse)
    inner = inner[order].copy()
    own_fans = compact_node_fans(record)
    half_arm_ids = {"shared:" + record["node_id"] + ":" + str(ordinal) for ordinal in attachment["half_arm_triangle_indices"]}
    lower, upper = inner[0, [0, 2]], inner[-1, [0, 2]]
    vector = upper - lower
    denominator = float(vector @ vector)
    points = {tuple(point[[0, 2]]) for point in inner}
    for fan in own_fans:
        if fan["triangle_id"] not in half_arm_ids:
            continue
        for vertex in fan["vertices_xz_m"]:
            delta = np.array(vertex) - lower
            fraction = float(delta @ vector / denominator)
            distance = abs(float(delta[0] * vector[1] - delta[1] * vector[0])) / math.sqrt(denominator)
            if (distance <= 1e-8 and 0. < fraction < 1.
                    and all(math.dist(vertex, point) > 1e-8 for point in points)):
                points.add(tuple(vertex))
    horizontal = sorted(points, key=lambda point: float((np.array(point) - lower) @ vector))
    inner = np.array([[point[0], 0., point[1]] for point in horizontal])
    witnesses = []
    for point in inner:
        result = sampler(point[[0, 2]])
        point[1] = result["derived_bed_m"]
        witnesses.append(result)
    origin = [origin_xz[0], float(inner[:, 1].min()), origin_xz[1]]
    length = float(np.linalg.norm(origin_xz - midpoint))
    if length <= 0:
        raise ValueError("zero_actual_surface_half_arm_length")
    station = {"station_id": region + ":half_arm", "derived_ring_xyz_m": inner.tolist(),
        "origin_xyz_m": origin, "transverse_unit_xz": transverse.tolist()}
    saved = {"surface_node_pin": attachment["surface_node_pin"], "canonical_port_pin": attachment["canonical_port_pin"],
        "actual_complete_port_proof": attachment["actual_complete_port_proof"],
        "half_arm_triangle_indices": attachment["half_arm_triangle_indices"], "geometry": record["geometry"],
        "compact_native_fans": own_fans, "inner_vertex_ids": arm["inner_vertex_ids"], "inner_source_witnesses": witnesses,
        "hydraulic_inner_ring_xyz_m": inner.tolist(), "hydraulic_station_id": station["station_id"],
        "midpoint_geometry_only_not_hydraulic_bc": True}
    return cell_record(station, region, "engineered:sink:half_arm_attachment" if region == "surface_in" else "engineered:spring:half_arm_attachment",
        length, parameters, {"actual_half_arm_triangle_indices": attachment["half_arm_triangle_indices"]}), saved


def build_geometry(graph_record, sampler, parameters=Parameters()):
    graph = load_graph(graph_record)
    portals = {kind: next(node for node in graph.nodes if node.kind == kind) for kind in ("sink", "spring")}
    ports = {kind: json.loads(node.source_record_json) for kind, node in portals.items()}
    for kind, port in ports.items():
        for value in sorted(portal_knots(port)):
            point = portal_point(port, value)
            result = sampler(point[[0, 2]])
            if abs(result["derived_bed_m"] - point[1]) > 1e-8:
                raise ValueError("actual_canonical_port_differs_from_saved_fan_bed:" + kind)
    vdm = build_charts(ports["sink"], ports["spring"], portals["sink"].xyz_m, portals["spring"].xyz_m, parameters)
    cover_witnesses = []
    for station in vdm["stations"]:
        ring = np.array(station["derived_ring_xyz_m"])
        witnesses = [sampler(point[[0, 2]]) for point in ring]
        roof_cover = min(witness["derived_bed_m"] - point[1] for point, witness in zip(ring[-2:], witnesses[-2:]))
        if .25 <= station["fraction"] <= .75 and roof_cover < .5:
            raise ValueError("generated_route_has_insufficient_actual_roof_cover:" + station["station_id"])
        source_reference = [[point[0], witness["source_sample"]["height_m"], point[2]] for point, witness in zip(ring, witnesses)]
        cover_witnesses.append({"station_id": station["station_id"], "ring_source_witnesses": witnesses, "minimum_roof_cover_m": roof_cover,
            "original_source_reference_ring_xyz_m": source_reference,
            "source_to_derived_displacement_ring_xyz_m": (ring - np.array(source_reference)).tolist(),
            "separate_from_conduit_chart_VDM_displacement": True})
    origin = np.array(portals["sink"].xyz_m)
    rock_record, sampling = build_rock(vdm, sampler, parameters, origin)
    before = manifold_from_record(rock_record)
    above_y = max(sample["derived_bed_m"] for sample in sampling["samples"]) + 10.
    closed_sections = []
    for station, witness in zip(vdm["stations"], cover_witnesses):
        ring = np.array(station["derived_ring_xyz_m"])
        containment = []
        for point in ring:
            hits = ray_hits(before, [point[0], above_y, point[2]], point.tolist(), origin)
            actual_cover = min((hit["position_xyz_m"][1] - point[1] for hit in hits), default=-math.inf)
            containment.append({"point_xyz_m": point.tolist(), "rock_before_vertical_hits": hits,
                "actual_sampled_top_cover_m": actual_cover if math.isfinite(actual_cover) else None})
        closed = closed_rock_section(containment)
        closed_sections.append(closed)
        witness.update(actual_ring_containment=containment, physical_closed_rock_section=closed)
    core_ids = [ordinal for ordinal, closed in enumerate(closed_sections) if closed]
    if not core_ids or core_ids != list(range(core_ids[0], core_ids[-1] + 1)):
        raise ValueError("actual_covered_core_missing_or_not_contiguous")
    vertices = np.array([station["derived_ring_xyz_m"] for station in vdm["stations"]]).reshape(-1, 3) - origin
    cutter_record = mesh_record(vertices, vdm["triangles"], origin, "cutter")
    cutter = manifold_from_record(cutter_record)
    after, removed = before - cutter, before ^ cutter
    import manifold3d as manifold
    if any(solid.status() != manifold.Error.NoError or solid.is_empty() for solid in (after, removed)):
        raise ValueError("actual_rock_boolean_failed_or_empty")
    if abs(before.volume() - after.volume() - removed.volume()) > max(1e-7, before.volume() * 1e-10):
        raise ValueError("signed_actual_solid_material_balance_failed")
    path, segments, openings = void_witnesses(before, after, removed, vdm, origin, sampler)
    attachments = {}
    cells = []
    for region, kind in (("surface_in", "sink"), ("surface_out", "spring")):
        arc = next(arc for arc in graph.arcs if arc.kind == "portal_attachment" and portals[kind].node_id in arc.node_ids)
        evidence = json.loads(arc.source_record_json)
        cell, attachment = surface_cell(evidence, ports[kind], sampler, region, parameters)
        cells.append(cell)
        attachments[kind] = attachment
    stations = vdm["stations"]
    distances = [math.dist(first["origin_xyz_m"], second["origin_xyz_m"]) for first, second in zip(stations, stations[1:])]
    if min(distances) <= 0:
        raise ValueError("degenerate_conduit_station")
    gallery = [cell_record(station, "underground", "engineered:underground",
        (distances[ordinal - 1] if ordinal else 0.) / 2 + (distances[ordinal] if ordinal < len(distances) else 0.) / 2,
        parameters, {"vdm_station_index": ordinal, "vdm_floor_vertex_indices": list(range(station["floor_vertex_count"])),
            "cutter_ring_vertex_indices": list(range(ordinal * len(station["derived_ring_xyz_m"]), ordinal * len(station["derived_ring_xyz_m"]) +
                (len(station["derived_ring_xyz_m"]) if closed_sections[ordinal] else station["floor_vertex_count"])))}, closed_rock=closed_sections[ordinal])
        for ordinal, station in enumerate(stations)]
    cells = [cells[0], *gallery, cells[1]]
    links = []
    for ordinal, (first, second) in enumerate(zip(cells, cells[1:])):
        kind = {("surface", "surface"): "surface_half_arm", ("surface", "underground"): "sink_exchange",
            ("underground", "surface"): "spring_exchange", ("underground", "underground"): "conduit"}[(first["kind"], second["kind"])]
        links.append({"link_id": "physical:" + str(ordinal), "from_cell_id": first["cell_id"], "to_cell_id": second["cell_id"],
            "kind": kind, "length_m": (first["length_m"] + second["length_m"]) / 2,
            "physical_attachment_reference": {"vdm_station_ids": [first["cell_id"], second["cell_id"]], "shared_native_port": ordinal in (0, len(cells) - 2)}})
    binding = {kind: {"port_arc_id": node.port_arc_id, "port_identity_sha256": ports[kind]["identity_sha256"],
        "immutable_station_id": stations[0 if kind == "sink" else -1]["station_id"], "full_native_floor_preserved": True,
        "hydraulic_boundary_certified": False} for kind, node in portals.items()}
    beds = [min(point[1] for point in station["derived_ring_xyz_m"][:station["floor_vertex_count"]]) for station in stations]
    geometry = {"schema": SCHEMA, "status": "candidate", "rejection_reasons": [], "graph_identity_sha256": graph_record["identity_sha256"],
        "inputs": {key: asdict(pin) for key, pin in graph.inputs}, "policy": POLICY, "policy_identity_sha256": POLICY_SHA256,
        "parameters": asdict(parameters), "parameters_identity_sha256": identity(asdict(parameters)),
        "portal_bindings": binding, "portal_sections": {kind: {"pieces": native_bed_pieces(port), "canonical_profile": port["profile"], "geometry_port_only": True} for kind, port in ports.items()},
        "hydraulic_cells": cells, "hydraulic_links": links, "surface_attachment_route": "actual_saved_half_arm_to_immutable_midpoint_floor",
        "hydraulic_section_classification": "physical_kind_surface_for_open_gallery_ramps_closed_underground_only_actual_rock_enclosed_core_route_region_unchanged",
        "actual_closed_core_station_indices": core_ids,
        "hydraulic_contract_identity_sha256": identity({"contract": "actual-open-ramp-v2", "physical_kind_independent_of_graph_route_region": True}),
        "air_path_xyz_m": path, "air_path_segments": segments, "portal_opening_witnesses": openings,
        "station_source_cover_witnesses": cover_witnesses,
        "actual_solid_material": {"rock_before_m3": before.volume(), "rock_after_m3": after.volume(), "excavated_rock_m3": removed.volume(),
            "exported_excavated_rock_m3": removed.volume(), "fill_rock_m3": 0., "signed_residual_m3": before.volume() - after.volume() - removed.volume()},
        "bed_slope_diagnostic": {"station_floor_elevation_m": beds, "adverse_segments": [ordinal for ordinal in range(len(beds) - 1) if beds[ordinal + 1] > beds[ordinal]],
            "not_adjusted_for_hydraulic_convenience": True},
        "conduit_length_m": math.fsum(distances), "sampled_not_native_exact": True, "fine15_replaced": False,
        "independent_audit_passed": False, "hydraulic_solved": False, "hydraulic_ready": False,
        "free_water_surface_generated": False, "natural_outlet_certified": False, "full_network_verified": False}
    guard()
    return geometry, {"rock_before": rock_record, "cutter": cutter_record,
        "rock_after": save_manifold(after, origin, "rock_after"), "removed": save_manifold(removed, origin, "removed"),
        "vdm": vdm, "source_sampling": sampling, "surface_attachments": seal({"schema": "td-hybrid-surface-attachments-v1", "attachments": attachments})}
