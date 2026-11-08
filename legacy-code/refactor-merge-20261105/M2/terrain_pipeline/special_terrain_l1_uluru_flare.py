"""Inselberg with a flared, overhanging base (Uluru flared-slope route, L1 volume form).

The L0 ``inselberg`` in ``metric_special_terrain_forms`` is a single-valued height field: it
can only raise the ground. A flared slope -- the overhanging basal concavity that makes
Uluru's base look undercut -- is **not** a single-valued field, so it needs new surface
topology. This module builds it as a real closed MESH64 solid with the general Boolean
algebra in ``terrain_pipeline.hybrid_rock_boolean`` (itself built on the frozen conduit
module, which is not edited here).

Geometry, in world metres (a local frame plus ``local_origin_xyz_m``); y is elevation and
the base plane is world y = 0. The vertical axis of both bodies passes through
``(origin[0], origin[2])``:

* ``flared_skirt``   -- a short apron on the ground, y = 0 .. ``skirt_top_elevation_m``,
  widening upward from ``skirt_base_radius_m`` to ``skirt_outer_radius_m``.
* ``inselberg_body`` -- the steep-walled tower, y = ``tower_base_elevation_m`` ..
  ``total_height_m``, with a **negative** side slope (base radius much larger than top
  radius).

The tower base radius is deliberately larger than the skirt outer radius, so the tower
overhangs the apron and leaves a genuine annular alcove of open air between the apron wall
and the tower underside. The two bodies overlap in elevation, which is what makes the union
a single connected solid.

Every dimension is an **explicit assumption** (``EXPLICIT_ASSUMPTIONS``): only the order of
magnitude of the height is supported by sources, and the two published Uluru heights
(348 m and 335 m) remain **unresolved**. The base is synthetic analytic geometry, not TD
native terrain. Nothing here is a certification: ``status`` is ``candidate`` and all six
capability flags stay False.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

from terrain_pipeline.hybrid_cave_geometry import ray_hits, seal
from terrain_pipeline.hybrid_rock_boolean import (
    ALGORITHM as BOOLEAN_ALGORITHM, BooleanParameters, FLAGS, census, combine,
    frustum_record, solid_from_record)
from terrain_pipeline.hybrid_river_graph import identity

SCHEMA = "td-special-terrain-l1-uluru-flare-v1"
REPORT_SCHEMA = "td-special-terrain-l1-uluru-flare-report-v1"
ALGORITHM = "inselberg-with-flared-overhanging-base-v1"
PARENT_ALGORITHM = BOOLEAN_ALGORITHM
BASE_KIND = "synthetic_analytic"
SOLID_ROLE = "uluru_flare"
SKIRT_ROLE = "flared_skirt"
BODY_ROLE = "inselberg_body"
DEFAULT_ORIGIN = np.array([120., 40., -75.])
DEFAULT_PREVIEW = Path(".scratch/special-terrain/l1-preview-20261019/uluru-flare")
WORLD_FRAME_NOTE = ("witness coordinates are world metres (local mesh frame + local_origin_xyz_m); "
                    "y is elevation and the model base plane is world y = 0")
FIGURE_SCOPE = "display only; a figure is never a certification"
PROBE_CUBE_EDGE_M = .2

# Height provenance: 348 m is the figure published by the park authority, 335 m is the
# competing figure. The conflict is NOT resolved here; 348 is chosen and the choice is
# recorded as an assumption, never as a measurement.
CHOSEN_HEIGHT_M = 348.
HEIGHT_CONFLICT = {"published_m": [348., 335.], "resolution": "unresolved",
                   "chosen_m": CHOSEN_HEIGHT_M,
                   "basis": "park authority figure; the conflict with 335 m is unresolved"}

# Explicit assumptions: no source supplies these numbers (see the parameter ledger).
EXPLICIT_ASSUMPTIONS = (
    {"name": "total_height_m", "value": CHOSEN_HEIGHT_M, "grade": "assumed",
     "reason": "348 m and 335 m coexist in the sources and the conflict is unresolved; "
               "this is a chosen figure, not a measurement"},
    {"name": "overhang_amplitude_m", "value": 38., "grade": "assumed",
     "reason": "flared-slope outward extent not obtained from any source"},
    {"name": "skirt_height_m", "value": 12., "grade": "assumed",
     "reason": "height of the flared basal alcove not obtained from any source"},
    {"name": "skirt_wall_slope_deg", "value": 9.4623, "grade": "assumed",
     "reason": "outward widen of the apron is a parameterisation choice; the value is the "
               "slope actually implied by skirt_base_radius_m/skirt_outer_radius_m/skirt_top_elevation_m"},
    {"name": "tower_side_slope_deg", "value": 12.0253, "grade": "assumed",
     "reason": "steep wall angle is a parameterisation choice, not a surveyed profile; the value "
               "is the slope actually implied by the tower radii and heights"},
)


@dataclass(frozen=True)
class FlareParameters:
    """Every dimension is an explicit assumption; no default is a survey value."""

    total_height_m: float = CHOSEN_HEIGHT_M
    tower_top_radius_m: float = 96.
    tower_base_radius_m: float = 168.
    tower_base_elevation_m: float = 10.
    skirt_outer_radius_m: float = 130.
    skirt_base_radius_m: float = 128.
    skirt_top_elevation_m: float = 12.
    tower_segments: int = 64
    skirt_segments: int = 64

    def __post_init__(self):
        for name in ("total_height_m", "tower_top_radius_m", "tower_base_radius_m",
                     "tower_base_elevation_m", "skirt_outer_radius_m", "skirt_base_radius_m",
                     "skirt_top_elevation_m"):
            value = getattr(self, name)
            if type(value) is not float or not math.isfinite(value) or value <= 0.:
                raise ValueError("bounded positive float required for " + name)
        for name in ("tower_segments", "skirt_segments"):
            value = getattr(self, name)
            if type(value) is not int or not 3 <= value <= 4096:
                raise ValueError("bounded integer ring segment count required for " + name)
        if not self.tower_top_radius_m < self.tower_base_radius_m:
            raise ValueError("negative side slope required: the top radius must be the smaller one")
        if self.tower_base_elevation_m >= self.total_height_m:
            raise ValueError("the tower base elevation must lie below the total height")
        if not self.skirt_base_radius_m <= self.skirt_outer_radius_m:
            raise ValueError("the flared skirt must widen upward, not narrow")
        if not self.skirt_outer_radius_m < self.tower_base_radius_m:
            raise ValueError("a positive overhang requires the tower base to outreach the skirt")
        if not self.skirt_top_elevation_m > self.tower_base_elevation_m:
            raise ValueError("the skirt must overlap the tower in elevation to stay connected")

    @property
    def overhang_amplitude_m(self):
        return self.tower_base_radius_m - self.skirt_outer_radius_m

    @property
    def tower_side_slope_deg(self):
        return math.degrees(math.atan2(self.tower_base_radius_m - self.tower_top_radius_m,
                                       self.total_height_m - self.tower_base_elevation_m))

    @property
    def skirt_wall_slope_deg(self):
        return math.degrees(math.atan2(self.skirt_outer_radius_m - self.skirt_base_radius_m,
                                       self.skirt_top_elevation_m))


def _library_versions():
    from importlib.metadata import version
    return {"manifold3d": version("manifold3d"), "numpy": np.__version__}


def _origin(origin):
    origin = DEFAULT_ORIGIN.copy() if origin is None else np.asarray(origin, float)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("finite three-component local origin required")
    return origin


def contains_point(solid, world_point, origin):
    """Independent containment: intersect a tiny closed cube with the solid.

    The saved solid lives in the local mesh frame, so the probe cube is translated to the
    *local* point. Returns the overlap volume in m^3 (0.0 means the point is outside). This
    is a MESH64 Boolean rather than a ray-parity count, so a grazing ray cannot fake it.
    """
    import manifold3d as manifold
    local = tuple(float(value) for value in (np.asarray(world_point, float) - np.asarray(origin, float)))
    probe = manifold.Manifold.cube((PROBE_CUBE_EDGE_M,) * 3, center=True).translate(local)
    return float((probe ^ solid).volume())


def build(parameters=None, origin=None):
    """Assemble the flared inselberg and measure its overhang. Nothing is certified."""
    parameters = FlareParameters() if parameters is None else parameters
    if not isinstance(parameters, FlareParameters):
        raise ValueError("explicit FlareParameters required")
    origin = _origin(origin)
    centre = [float(origin[0]), float(origin[2])]
    skirt = frustum_record(centre, centre, 0., parameters.skirt_top_elevation_m,
                           parameters.skirt_base_radius_m, parameters.skirt_outer_radius_m,
                           origin, SKIRT_ROLE, segments=parameters.skirt_segments)
    tower = frustum_record(centre, centre, parameters.tower_base_elevation_m, parameters.total_height_m,
                           parameters.tower_base_radius_m, parameters.tower_top_radius_m,
                           origin, BODY_ROLE, segments=parameters.tower_segments)
    result, meshes = combine([skirt, tower], origin, SOLID_ROLE, BooleanParameters(),
                            minimum_components=1)
    union = meshes[SOLID_ROLE]
    solid = solid_from_record(union, SOLID_ROLE)
    solids = {SKIRT_ROLE: skirt, BODY_ROLE: tower, SOLID_ROLE: union}
    witnesses = overhang_witnesses(solid, solids, parameters, origin)
    return {"result": result, "solids": solids, "witnesses": witnesses, "solid": solid,
            "origin": origin, "parameters": parameters}


def winding_number(vertices_local_xyz_m, triangles, point_world_xyz_m, origin):
    """Independent winding number of a closed triangle mesh about one point.

    Sums the signed solid angle of every triangle (Van Oosterom-Strackee) and divides by
    4*pi, using only the saved mesh arrays -- no manifold3d and no ray casting. A closed
    outward-oriented solid gives 1.0 for an interior point and 0.0 for an exterior one, so
    a cold reader can recompute containment from the saved record alone.
    """
    origin = np.asarray(origin, float)
    points = np.asarray(vertices_local_xyz_m, float) + origin - np.asarray(point_world_xyz_m, float)
    total = 0.
    for triangle in np.asarray(triangles, int):
        first, second, third = (points[index] for index in triangle)
        lengths = (np.linalg.norm(first), np.linalg.norm(second), np.linalg.norm(third))
        numerator = float(np.dot(first, np.cross(second, third)))
        denominator = (lengths[0] * lengths[1] * lengths[2]
                       + float(np.dot(first, second)) * lengths[2]
                       + float(np.dot(second, third)) * lengths[0]
                       + float(np.dot(third, first)) * lengths[1])
        total += 2. * math.atan2(numerator, denominator)
    return total / (4. * math.pi)


def inside_by_winding(record, point_world_xyz_m, origin):
    winding = winding_number(record["vertices_local_xyz_m"], record["triangles"],
                             point_world_xyz_m, origin)
    return bool(round(winding) == 1), float(winding)


def overhang_witnesses(solid, solids, parameters, origin):
    """Measure the overhang instead of asserting it.

    Every witness is one of the three cold-readable shapes: winding-number containment
    (recomputable from the saved mesh alone), a ray replay against the saved solid, or a
    MESH64 volume census. All coordinates are **world metres**. The probe point sits
    directly under the overhanging tower rim, radially outside the apron, so an
    \"everything is outside\" or \"everything is filled\" model cannot pass by accident:
    two controls (a point inside the tower, a point far outside) are recorded too.
    """
    union = solids[SOLID_ROLE]
    axis_x, axis_z = float(origin[0]), float(origin[2])
    mid_y = parameters.skirt_top_elevation_m * .5
    probe_radius_m = (parameters.skirt_outer_radius_m + parameters.tower_base_radius_m) * .5
    under_xyz = [axis_x + probe_radius_m, mid_y, axis_z]
    inside_xyz = [axis_x, parameters.total_height_m * .5, axis_z]
    far_xyz = [axis_x + parameters.tower_base_radius_m + parameters.overhang_amplitude_m + 100.,
               mid_y, axis_z]
    vertical_to = [under_xyz[0], parameters.tower_base_elevation_m + 30., under_xyz[2]]
    horizontal_to = [axis_x, mid_y, axis_z]
    under_inside, under_winding = inside_by_winding(union, under_xyz, origin)
    inside_inside, inside_winding = inside_by_winding(union, inside_xyz, origin)
    far_inside, far_winding = inside_by_winding(union, far_xyz, origin)
    vertical_hits = ray_hits(solid, under_xyz, vertical_to, origin)
    horizontal_hits = ray_hits(solid, under_xyz, horizontal_to, origin)
    components = census(solid)
    return {
        "overhang_point_outside_union": {
            "method": "Solid.winding", "solid_role": SOLID_ROLE, "point_xyz_m": under_xyz,
            "expected_inside": False, "verdict": bool(not under_inside),
            "claim": "the point directly under the overhanging tower rim is outside the union, "
                     "so the basal alcove is genuine open air rather than filled rock",
            "observed": {"winding": under_winding, "inside": under_inside},
            "probe_radius_m": probe_radius_m,
            "skirt_outer_radius_m": parameters.skirt_outer_radius_m,
            "tower_base_radius_m": parameters.tower_base_radius_m,
            "probe_cube_intersection_volume_m3": contains_point(solid, under_xyz, origin)},
        "vertical_ray_crosses_void_then_hits_rock": {
            "method": "Manifold.ray_cast", "solid_role": SOLID_ROLE,
            "from_xyz_m": under_xyz, "to_xyz_m": vertical_to,
            "expected_hit_count": 1, "verdict": bool(len(vertical_hits) == 1),
            "claim": "a segment rising from the overhang point traverses the open alcove and "
                     "then strikes the tower underside exactly once",
            "observed": {"hit_count": len(vertical_hits), "hits": vertical_hits}},
        "horizontal_ray_crosses_void_then_hits_rock": {
            "method": "Manifold.ray_cast", "solid_role": SOLID_ROLE,
            "from_xyz_m": under_xyz, "to_xyz_m": horizontal_to,
            "expected_hit_count": 1, "verdict": bool(len(horizontal_hits) == 1),
            "claim": "a segment running inward along the alcove floor crosses the open "
                     "concavity and then strikes the apron wall exactly once",
            "observed": {"hit_count": len(horizontal_hits), "hits": horizontal_hits}},
        "control_point_inside_tower": {
            "method": "Solid.winding", "solid_role": SOLID_ROLE, "point_xyz_m": inside_xyz,
            "expected_inside": True, "verdict": bool(inside_inside),
            "claim": "control: a point on the tower axis at half height is inside the union, "
                     "so the outside verdict above is not vacuous",
            "observed": {"winding": inside_winding, "inside": inside_inside},
            "probe_cube_intersection_volume_m3": contains_point(solid, inside_xyz, origin)},
        "control_point_far_outside": {
            "method": "Solid.winding", "solid_role": SOLID_ROLE, "point_xyz_m": far_xyz,
            "expected_inside": False, "verdict": bool(not far_inside),
            "claim": "control: a point well outside the model footprint is outside the union",
            "observed": {"winding": far_winding, "inside": far_inside},
            "probe_cube_intersection_volume_m3": contains_point(solid, far_xyz, origin)},
        "union_single_connected_component": {
            "method": "Mesh64_boolean", "operation": "add",
            "cutter_roles": [SKIRT_ROLE, BODY_ROLE],
            "expected_rock_after_m3": union["signed_volume_m3"], "expected_removed_m3": 0.,
            "verdict": bool(components == 1),
            "claim": "the apron and the tower overlap in elevation, so the flared base and the "
                     "body are one connected closed solid rather than two touching bodies",
            "observed": {"component_count": components, "declared_minimum_components": 1,
                         "input_roles": [SKIRT_ROLE, BODY_ROLE],
                         "rebuilt_union_volume_m3": union["signed_volume_m3"]}},
    }


def plane_section_segments(record, axis, value):
    """Intersect the saved closed mesh with one axis-aligned plane (world metres).

    Returns explicit triangle/plane crossing segments in the two remaining coordinates, so
    a true section is drawn from the actual mesh rather than from the parameters.
    """
    vertices = np.asarray(record["vertices_local_xyz_m"], float) + np.asarray(record["local_origin_xyz_m"], float)
    keep = [index for index in range(3) if index != axis]
    segments = []
    for triangle in np.asarray(record["triangles"], int):
        points = vertices[triangle]
        distances = points[:, axis] - float(value)
        crossings = []
        for first, second in ((0, 1), (1, 2), (2, 0)):
            a, b = distances[first], distances[second]
            if a == 0. and b == 0.:
                continue
            if (a <= 0. <= b) or (b <= 0. <= a):
                if a == b:
                    continue
                fraction = a / (a - b)
                crossings.append(points[first] + fraction * (points[second] - points[first]))
        if len(crossings) == 2:
            segments.append((crossings[0][keep], crossings[1][keep]))
        elif len(crossings) == 3:
            unique = {tuple(np.round(point, 9)) for point in crossings}
            if len(unique) == 2:
                first, second = (np.asarray(item) for item in sorted(unique))
                segments.append((first[keep], second[keep]))
    return segments


def _save(figure, output_directory, name):
    path = Path(output_directory) / name
    figure.savefig(path, dpi=120, metadata={"Software": "special_terrain_l1_uluru_flare"})
    import matplotlib.pyplot as plt
    plt.close(figure)
    return {"name": name, "path": path.as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def render(record, parameters, output_directory):
    """Plan, true section and 3D views of the saved union. Display only, never evidence."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Wedge
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    vertices = np.asarray(record["vertices_local_xyz_m"], float) + np.asarray(record["local_origin_xyz_m"], float)
    triangles = np.asarray(record["triangles"], int)
    panel = []

    figure, axes = plt.subplots(figsize=(8., 8.))
    axes.add_patch(Wedge((vertices[:, 0].mean(), vertices[:, 2].mean()),
                         parameters.tower_base_radius_m, 0., 360., width=parameters.overhang_amplitude_m,
                         facecolor="#f6d9a8", edgecolor="none", alpha=.85,
                         label="overhang annulus: %.0f m of open alcove" % parameters.overhang_amplitude_m))
    for triangle in triangles:
        ring = vertices[triangle][:, [0, 2]]
        closed = np.vstack((ring, ring[:1]))
        axes.plot(closed[:, 0], closed[:, 1], color="#7b5e2e", linewidth=.2, alpha=.3)
    angles = np.linspace(0., 2. * np.pi, 361)
    for radius, colour in ((parameters.skirt_outer_radius_m, "#2e7d32"),
                           (parameters.tower_base_radius_m, "#c62828")):
        axes.plot(radius * np.cos(angles) + vertices[:, 0].mean(),
                  radius * np.sin(angles) + vertices[:, 2].mean(),
                  color=colour, linewidth=1.1, linestyle="--", label="radius %.0f m" % radius)
    axes.set_aspect("equal")
    axes.set_xlabel("x (m)")
    axes.set_ylabel("z (m)")
    axes.set_title("uluru flared base: plan view (synthetic analytic, not TD)")
    axes.legend(fontsize=7, loc="upper right")
    axes.grid(alpha=.2)
    figure.tight_layout()
    panel.append(_save(figure, output, "uluru-flare-a-plan.png"))

    figure, axes = plt.subplots(figsize=(7.5, 7.))
    section_value = float(np.mean(vertices[:, 2]))
    segments = plane_section_segments(record, 2, section_value)
    if not segments:
        raise ValueError("plane section produced no segments")
    for first, second in segments:
        axes.plot([first[0], second[0]], [first[1], second[1]], color="#6b4f1d", linewidth=1.2)
    axes.annotate("open alcove under the overhang", xy=(vertices[:, 0].mean() + parameters.skirt_outer_radius_m + 10.,
                                                        parameters.skirt_top_elevation_m * .5),
                  xytext=(vertices[:, 0].mean() + parameters.tower_base_radius_m + 20., 90.),
                  fontsize=7, arrowprops={"arrowstyle": "->", "lw": .8})
    axes.set_aspect("equal")
    axes.set_xlabel("x (m)")
    axes.set_ylabel("y elevation (m)")
    axes.set_title("uluru flared base: section at z = %.2f m (triangle/plane crossings)" % section_value)
    axes.grid(alpha=.2)
    figure.tight_layout()
    panel.append(_save(figure, output, "uluru-flare-b-section.png"))

    figure = plt.figure(figsize=(9., 7.))
    axes = figure.add_subplot(111, projection="3d")
    faces = vertices[triangles][::max(1, len(triangles) // 6000)]
    axes.add_collection3d(Poly3DCollection(faces, facecolor="#c8853f", edgecolor="#6b4f1d",
                                           linewidths=.1, alpha=.95))
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    axes.set_xlim(low[0], high[0])
    axes.set_ylim(low[2], high[2])
    axes.set_zlim(low[1], high[1])
    axes.set_xlabel("x (m)")
    axes.set_ylabel("z (m)")
    axes.set_zlabel("y elevation (m)")
    axes.set_title("uluru flared base: closed MESH64 union, %d faces" % len(triangles))
    figure.tight_layout()
    panel.append(_save(figure, output, "uluru-flare-c-solid.png"))
    return panel


def report(parameters=None, origin=None, output_directory=None):
    """Build the geometry and seal the contract-shaped report for cold reading."""
    geometry = build(parameters, origin)
    parameters = geometry["parameters"]
    origin = geometry["origin"]
    figures = [] if output_directory is None else render(geometry["solids"][SOLID_ROLE], parameters,
                                                         output_directory)
    record = {"schema": REPORT_SCHEMA, "algorithm": ALGORITHM, "status": "candidate",
              "synthetic_base": {"kind": BASE_KIND, "note": "not TD native terrain, not surveyed"},
              "world_frame": WORLD_FRAME_NOTE,
              "local_origin_xyz_m": [float(value) for value in origin],
              "parent_algorithm": PARENT_ALGORITHM,
              "parameters": asdict(parameters),
              "derived": {"overhang_amplitude_m": parameters.overhang_amplitude_m,
                          "tower_side_slope_deg": parameters.tower_side_slope_deg,
                          "skirt_wall_slope_deg": parameters.skirt_wall_slope_deg},
              "explicit_assumptions": [dict(item) for item in EXPLICIT_ASSUMPTIONS],
              "height_conflict": dict(HEIGHT_CONFLICT),
              "solids": {role: dict(mesh) for role, mesh in geometry["solids"].items()},
              "boolean": geometry["result"], "witnesses": geometry["witnesses"],
              "flags": {flag: False for flag in FLAGS},
              "library_versions": _library_versions(), "figures": figures,
              "figure_scope": FIGURE_SCOPE}
    seal(record)
    return record, geometry


def encode_report(record):
    """Compact, key-sorted, NaN-refusing JSON bytes; identical input gives identical bytes."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def report_identity(record):
    return identity({key: value for key, value in record.items() if key != "identity_sha256"})


def write_report(path, parameters=None, origin=None, output_directory=None):
    record, _ = report(parameters, origin, output_directory)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_report(record))
    return record


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    output = Path(argv[0]) if argv else DEFAULT_PREVIEW
    record = write_report(output / "report.json", output_directory=output)
    print(json.dumps({"status": record["status"], "report": (output / "report.json").as_posix(),
                      "union_volume_m3": record["solids"][SOLID_ROLE]["signed_volume_m3"],
                      "components": record["boolean"]["census"]["assembled_components"],
                      "witness_verdicts": {name: witness["verdict"] for name, witness in record["witnesses"].items()},
                      "identity_sha256": record["identity_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
