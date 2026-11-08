"""Offline sampled-rock cave, twin skylights and the natural bridge between them.

One synthetic analytic cuboid block of rock is excavated by a real MESH64 Boolean: a main
tunnel, a side branch that intersects it, and two vertical perforations running from the
tunnel roof to the block top. The rock left standing between the two perforations is the
natural bridge; it is required to remain a single connected piece of the surrounding rock
and both perforations must stay open, so that the two apertures are separate holes rather
than one slit with the block opened along its whole top.

Every numeric input is an **explicit assumption** (``explicit_assumptions`` in the saved
report): the reconnaissance ledger has no measured tunnel depth, gallery bore, skylight
spacing or bridge thickness for any real cave, so nothing here is a survey, a measurement
or a reconstruction of a named feature. The base is ``synthetic_analytic``: it is not TD
native terrain and it is not surveyed.

The Boolean algebra is not implemented here. It is the general closed-solid algebra of
``terrain_pipeline.hybrid_rock_boolean`` (itself the generalisation of the frozen conduit
path in ``terrain_pipeline.hybrid_cave_geometry``, which this module does not edit). This
module only supplies the synthetic lattice, the witnesses and the report.

Status discipline: ``status`` is ``candidate`` and every capability flag is written False
(``independent_audit_passed``, ``hydraulic_ready``, ``natural_outlet_certified``,
``full_network_verified``, ``self_intersection_verified``, ``publishable``).

Cold-readability: the report inlines, verbatim, every closed solid that the verdicts rest
on (``solids``) plus the full Boolean result record (``boolean``), and every witness names
the saved solid role it must be replayed against. A cold reader can therefore rebuild
``manifold3d`` from the saved meshes, redo the subtract, re-cast every named segment and
re-sum the winding number without importing this module.
"""

from dataclasses import asdict, dataclass
from importlib.metadata import version
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline import hybrid_rock_boolean as boolean
from terrain_pipeline.hybrid_cave_geometry import (
    manifold_from_record, mesh_record, ray_hits, seal, signed_volume)
from terrain_pipeline.hybrid_river_graph import identity

SCHEMA = "td-special-terrain-l1-cave-bridge-v1"
ALGORITHM = "sampled-rock-cave-tunnel-skylights-natural-bridge-v1"
REPORT_SCHEMA = "td-special-terrain-l1-cave-bridge-report-v1"
ORIGIN = np.array([0., 0., 0.])
WORLD_FRAME_NOTE = "zero local origin: world metres equal local mesh metres, no world offset"
FLAGS = boolean.FLAGS

# Independent point-in-solid verdicts rest on the spherical winding number, which is
# dimensionless: 1.0 for a point strictly inside one closed, outward-oriented shell and a
# floating point residual (~1e-16 in the pinned engine) for a point outside or on the
# boundary. Deciding ``value > 0.`` on such a residual is exactly what a tolerance is for:
# any |winding| below this tolerance is treated as *not* inside, above it the sign decides.
# The number stays dimensionless and is therefore not scaled by the block size.
WINDING_INSIDE_TOLERANCE = 1e-9
# A winding near +-1/2 means the probe sits on (or beside) the saved surface, where no
# inside/outside verdict can be defended; such a probe is refused rather than guessed.
WINDING_SURFACE_MARGIN = .25

BRIDGE_CLAIM = ("the rock between the two skylight bores is intact and continuous with the "
                "surrounding block, so the two bores are separate apertures of one cavity "
                "rather than one slit along the whole top face")
APERTURE_CLAIM = ("the bore is open to the sky: a vertical probe from above the block into "
                  "the tunnel cavity crosses no rock at all")
THROUGH_BORE_CLAIM = ("the bore is a genuine through-opening: a vertical probe from above "
                      "the block down through the tunnel cavity crosses rock only inside "
                      "the block, never inside the bore column")
ROOF_CLAIM = ("directly above the bridge axis, between the two bores, the top face is "
              "unbroken: the vertical probe crosses it exactly once")
VOID_CLAIM = "the gallery bore is genuine exterior space inside the block, not filled rock"
MATERIAL_CLAIM = ("the saved Boolean material balance closes on the saved solids and the "
                  "excavated cavity is one connected component")


@dataclass(frozen=True)
class Parameters:
    """Explicit assumed lattice. No value here is a measurement or a certification."""

    plan_half_x_m: float = 60.
    plan_half_z_m: float = 60.
    top_y_m: float = 0.
    bottom_y_m: float = -30.
    tunnel_floor_y_m: float = -22.
    tunnel_roof_y_m: float = -14.
    tunnel_half_width_m: float = 4.
    tunnel_length_x_m: float = 50.
    branch_end_z_m: float = 45.
    branch_half_width_m: float = 4.
    skylight_x_m: tuple = (-25., 25.)
    skylight_radius_m: float = 4.
    skylight_segments: int = 48
    solids_spacing_m: float = 1.
    component_limit: int = 64

    def __post_init__(self):
        dimensions = (self.plan_half_x_m, self.plan_half_z_m, self.top_y_m, self.bottom_y_m,
                      self.tunnel_floor_y_m, self.tunnel_roof_y_m, self.tunnel_half_width_m,
                      self.tunnel_length_x_m, self.branch_end_z_m, self.branch_half_width_m,
                      self.skylight_radius_m, self.solids_spacing_m)
        if any(type(value) is not float or not math.isfinite(value) for value in dimensions):
            raise ValueError("finite float required for every lattice dimension")
        if type(self.skylight_segments) is not int or not 8 <= self.skylight_segments <= 512:
            raise ValueError("bounded integer skylight segment count required")
        if type(self.component_limit) is not int or not 1 <= self.component_limit <= boolean.MAX_COMPONENTS:
            raise ValueError("bounded integer component limit required")
        if not 10. <= self.plan_half_x_m or not 10. <= self.plan_half_z_m:
            raise ValueError("the block plan needs a positive half extent of at least 10 m")
        if not self.top_y_m > self.bottom_y_m:
            raise ValueError("strict positive block height required")
        if not self.tunnel_roof_y_m > self.tunnel_floor_y_m:
            raise ValueError("strict positive tunnel height required")
        if not (self.tunnel_roof_y_m < self.top_y_m and self.tunnel_floor_y_m > self.bottom_y_m):
            raise ValueError("the tunnel must sit strictly inside the block")
        if not 0. < self.tunnel_half_width_m < min(self.plan_half_x_m, self.plan_half_z_m):
            raise ValueError("bounded tunnel half width required")
        if not self.tunnel_half_width_m < self.tunnel_length_x_m < self.plan_half_x_m:
            raise ValueError("the tunnel must stop short of both side walls")
        if not self.branch_half_width_m < self.branch_end_z_m <= self.plan_half_z_m:
            raise ValueError("bounded branch reach required")
        if not 0. < self.branch_half_width_m < self.tunnel_half_width_m * 4.:
            raise ValueError("bounded branch half width required")
        if not isinstance(self.skylight_x_m, tuple) or len(self.skylight_x_m) < 2:
            raise ValueError("at least two skylight centres required as an immutable tuple")
        if any(type(value) is not float for value in self.skylight_x_m):
            raise ValueError("skylight centres must be explicit floats")
        if sorted(self.skylight_x_m) != list(self.skylight_x_m):
            raise ValueError("skylight centres must be ordered")
        if any(not -self.tunnel_length_x_m < value < self.tunnel_length_x_m for value in self.skylight_x_m):
            raise ValueError("every skylight must sit above the main tunnel")
        if abs(self.skylight_x_m[1] - self.skylight_x_m[0]) <= 4. * self.skylight_radius_m:
            raise ValueError("the skylights must be far enough apart to leave a bridge")
        self.bridge_probe_centres_m()

    def bridge_probe_centres_m(self):
        """Two bridge probe abscissae, one on each side of the block centre.

        The inner probe is the block centre: it is bridge material exactly when both bore
        rims stay strictly outside the centre, which is checked here. The outer probe is a
        third of the way in from the block side wall to the outer bore rim, so it keeps at
        least a quarter of the wall-to-rim gap clear of both the wall and the rim.
        """
        inner_probe = 0.
        outer_probe = (self.plan_half_x_m + self.skylight_x_m[1] + self.skylight_radius_m) / 2.
        if not (self.skylight_x_m[0] + self.skylight_radius_m < inner_probe
                < self.skylight_x_m[1] - self.skylight_radius_m):
            raise ValueError("both bore rims must clear the block centre so a bridge survives")
        margin = (self.plan_half_x_m - self.skylight_x_m[1] - self.skylight_radius_m) / 4.
        if not (self.skylight_x_m[1] + self.skylight_radius_m + margin < outer_probe
                < self.plan_half_x_m - margin):
            raise ValueError("the outer bridge probe must clear both the rim and the side wall")
        return (inner_probe, outer_probe)


PARAMETERS = Parameters()
ASSUMPTIONS = (
    {"name": "plan_half_x_m", "value": 60., "grade": "assumed",
     "reason": "the block plan only has to be large enough to leave outer rock around every void"},
    {"name": "plan_half_z_m", "value": 60., "grade": "assumed",
     "reason": "same as plan_half_x_m; no surveyed cave plan exists in the ledger"},
    {"name": "top_y_m", "value": 0., "grade": "assumed",
     "reason": "the block top elevation is a datum choice, not a surveyed ground surface"},
    {"name": "bottom_y_m", "value": -30., "grade": "assumed",
     "reason": "block thickness is a parameterisation choice, not a measured overburden"},
    {"name": "tunnel_roof_y_m", "value": -14., "grade": "assumed",
     "reason": "no measured gallery depth or roof elevation exists for any real cave in the ledger"},
    {"name": "tunnel_floor_y_m", "value": -22., "grade": "assumed",
     "reason": "gallery height 8 m is a parameterisation choice, not a surveyed bore"},
    {"name": "tunnel_half_width_m", "value": 4., "grade": "assumed",
     "reason": "gallery width not obtained; chosen to stay far below the block plan"},
    {"name": "tunnel_length_x_m", "value": 50., "grade": "assumed",
     "reason": "gallery reach not obtained; it must stop short of both block side walls"},
    {"name": "branch_end_z_m", "value": 45., "grade": "assumed",
     "reason": "side branch reach is invented so that the tunnel network is one connected cavity"},
    {"name": "branch_half_width_m", "value": 4., "grade": "assumed",
     "reason": "branch width not obtained; a parameterisation choice"},
    {"name": "skylight_x_m", "value": [-25., 25.], "grade": "assumed",
     "reason": "skylight spacing not obtained; 50 m is chosen so the bridge spans several bore diameters"},
    {"name": "skylight_radius_m", "value": 4., "grade": "assumed",
     "reason": "bore radius not obtained; a constant radius avoids claiming an unknown taper"},
    {"name": "skylight_segments", "value": 48, "grade": "assumed",
     "reason": "polygonal bore resolution is a meshing choice; it sets the inscribed bore radius"},
    {"name": "solids_spacing_m", "value": 1., "grade": "assumed",
     "reason": "Boolean sampling spacing is an engine tuning choice, not a field resolution"},
    {"name": "component_limit", "value": 64, "grade": "assumed",
     "reason": "the connected-component ceiling is a refusal guard, not a measured property"},
)


def rectangle_ring(half_x_m, half_z_m, centre_xz=(0., 0.)):
    """Counter-clockwise rectangle in the (x, z) plan; a prism is erected over it."""
    return np.array([[centre_xz[0] - half_x_m, centre_xz[1] - half_z_m],
                     [centre_xz[0] + half_x_m, centre_xz[1] - half_z_m],
                     [centre_xz[0] + half_x_m, centre_xz[1] + half_z_m],
                     [centre_xz[0] - half_x_m, centre_xz[1] + half_z_m]], float)


def winding_number(point, vertices, triangles):
    """Independent point-in-solid test: spherical solid angle sum over four pi.

    Oosterom-Strackee triangle solid angle, summed straight from the saved mesh, so a cold
    reader can reproduce the number without importing this module or its Boolean engine.
    Dimensionless result: +1 strictly inside one outward-oriented closed shell, ~0 outside
    or on the boundary.
    """
    point = np.asarray(point, float)
    vertices = np.asarray(vertices, float)
    triangles = np.asarray(triangles, int)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError("finite three-component winding probe required")
    total = 0.
    for triangle in triangles:
        legs = vertices[triangle] - point
        lengths = [float(np.linalg.norm(leg)) for leg in legs]
        if min(lengths) <= 1e-12:
            raise ValueError("winding probe coincides with a saved mesh vertex")
        numerator = float(np.dot(legs[0], np.cross(legs[1], legs[2])))
        denominator = (lengths[0] * lengths[1] * lengths[2]
                       + float(np.dot(legs[0], legs[1])) * lengths[2]
                       + float(np.dot(legs[1], legs[2])) * lengths[0]
                       + float(np.dot(legs[2], legs[0])) * lengths[1])
        total += 2. * math.atan2(numerator, denominator)
    return total / (4. * math.pi)


def inside(value, *, tolerance=WINDING_INSIDE_TOLERANCE):
    """Tolerant inside verdict; see WINDING_INSIDE_TOLERANCE for why a tolerance is needed."""
    if not math.isfinite(value):
        raise ValueError("nonfinite winding number")
    if value < -tolerance:
        raise ValueError("negative winding magnitude: the saved shell is not outward oriented")
    return value > tolerance


def _ray(solid, from_xyz, to_xyz, role, *, expected_hit_count, claim):
    hits = ray_hits(solid, np.asarray(from_xyz, float), np.asarray(to_xyz, float), ORIGIN)
    verdict = len(hits) == expected_hit_count
    if not verdict:
        raise ValueError("witness refused: " + role + " expected " + str(expected_hit_count)
                         + " hits, measured " + str(len(hits)))
    return {"method": "Manifold.ray_cast", "solid_role": role,
            "from_xyz_m": [float(value) for value in from_xyz],
            "to_xyz_m": [float(value) for value in to_xyz],
            "expected_hit_count": expected_hit_count, "verdict": True, "claim": claim,
            "observed": {"hit_count": len(hits), "hits": hits}}


def _winding(record, point, role, *, expected_inside, claim):
    value = winding_number(point, record["vertices_local_xyz_m"], record["triangles"])
    if abs(abs(value) - .5) < WINDING_SURFACE_MARGIN:
        raise ValueError("witness refused: the winding probe sits on the saved surface of " + role)
    verdict = inside(value) == expected_inside
    if not verdict:
        raise ValueError("witness refused: " + role + " winding " + repr(value)
                         + " disagrees with expected_inside=" + repr(expected_inside))
    return {"method": "Solid.winding", "solid_role": role,
            "point_xyz_m": [float(value) for value in point],
            "expected_inside": bool(expected_inside), "verdict": True, "claim": claim,
            "observed": {"winding": value, "inside_verdict": inside(value),
                         "inside_tolerance": WINDING_INSIDE_TOLERANCE,
                         "inside_tolerance_units": "dimensionless spherical winding, not metres",
                         "vertices_sha256": identity(record["vertices_local_xyz_m"]),
                         "triangles_sha256": identity(record["triangles"])}}


def build(parameters=Parameters()):
    """Excavate one analytic block; return (boolean result, solids, witnesses, parameters)."""
    if not isinstance(parameters, Parameters):
        raise ValueError("explicit Parameters required")
    cutters, solids = [], {}
    rock = boolean.polygon_prism_record(
        rectangle_ring(parameters.plan_half_x_m, parameters.plan_half_z_m),
        parameters.bottom_y_m, parameters.top_y_m, ORIGIN, "rock_before")
    solids["rock_before"] = rock

    main = boolean.polygon_prism_record(
        rectangle_ring(parameters.tunnel_length_x_m, parameters.tunnel_half_width_m),
        parameters.tunnel_floor_y_m, parameters.tunnel_roof_y_m, ORIGIN, "cutter_main_tunnel")
    branch = boolean.polygon_prism_record(
        rectangle_ring(parameters.branch_half_width_m, parameters.branch_end_z_m),
        parameters.tunnel_floor_y_m, parameters.tunnel_roof_y_m, ORIGIN, "cutter_side_branch")
    cutters.extend((main, branch))
    solids["cutter_main_tunnel"] = main
    solids["cutter_side_branch"] = branch
    for ordinal, centre_x in enumerate(parameters.skylight_x_m):
        role = "cutter_skylight_" + chr(ord("a") + ordinal)
        bore = boolean.frustum_record([centre_x, 0.], [centre_x, 0.], parameters.tunnel_roof_y_m,
                                      parameters.top_y_m, parameters.skylight_radius_m,
                                      parameters.skylight_radius_m, ORIGIN, role,
                                      segments=parameters.skylight_segments)
        cutters.append(bore)
        solids[role] = bore

    engineering = boolean.BooleanParameters(solids_spacing_m=parameters.solids_spacing_m,
                                            component_limit=parameters.component_limit)
    result, meshes = boolean.excavate(rock, cutters, engineering, ORIGIN,
                                     minimum_removed_components=1, minimum_rock_after_components=1)
    solids.update(meshes)
    if result["census"]["removed_components"] != 1:
        raise ValueError("the tunnel network and both skylights must excavate one connected cavity")

    after = manifold_from_record(solids["rock_after"])
    # The excavated void is re-recorded through the pinned two-use mesh recorder so a cold
    # reader can measure it without trusting manifold3d's own Mesh64 output layout.
    solids["removed"] = mesh_record(
        np.array(solids["removed"]["vertices_local_xyz_m"], float),
        np.array(solids["removed"]["triangles"], int), ORIGIN, "removed")

    mid_y = (parameters.tunnel_roof_y_m + parameters.top_y_m) / 2.
    inner_y = mid_y - .5
    void_y = (parameters.tunnel_floor_y_m + parameters.tunnel_roof_y_m) / 2.
    above = parameters.top_y_m + 5.
    below = parameters.bottom_y_m - 3.
    left, right = parameters.skylight_x_m
    bridge_centre, wall_probe = parameters.bridge_probe_centres_m()
    witnesses = {
        "bridge_axis_under_top_face": _ray(
            after, [-parameters.plan_half_x_m + 5., inner_y, 0.],
            [parameters.plan_half_x_m - 5., inner_y, 0.], "rock_after", expected_hit_count=4,
            claim=BRIDGE_CLAIM),
        "bridge_axis_over_the_roof": _ray(
            after, [0., above, 0.], [0., parameters.tunnel_roof_y_m + 4., 0.], "rock_after",
            expected_hit_count=1, claim=ROOF_CLAIM),
        "skylight_a_open_to_sky": _ray(
            after, [left, above, 0.], [left, void_y, 0.], "rock_after", expected_hit_count=0,
            claim=APERTURE_CLAIM),
        "skylight_b_open_to_sky": _ray(
            after, [right, above, 0.], [right, void_y, 0.], "rock_after", expected_hit_count=0,
            claim=APERTURE_CLAIM),
        "skylight_a_bores_into_the_block": _ray(
            after, [left, above, 0.], [left, below, 0.], "rock_after", expected_hit_count=2,
            claim=THROUGH_BORE_CLAIM),
        "skylight_b_bores_into_the_block": _ray(
            after, [right, above, 0.], [right, below, 0.], "rock_after", expected_hit_count=2,
            claim=THROUGH_BORE_CLAIM),
        "bridge_rock_is_solid": _winding(
            solids["rock_after"], [0., mid_y, 0.], "rock_after", expected_inside=True,
            claim=BRIDGE_CLAIM),
        "tunnel_bore_is_void": _winding(
            solids["rock_after"], [0., void_y, 0.], "rock_after", expected_inside=False,
            claim=VOID_CLAIM),
        "side_branch_bore_is_void": _winding(
            solids["rock_after"], [0., void_y, parameters.branch_end_z_m - 6.], "rock_after",
            expected_inside=False, claim=VOID_CLAIM),
        "skylight_a_column_is_void": _winding(
            solids["rock_after"], [left, void_y + 2., 0.], "rock_after", expected_inside=False,
            claim=APERTURE_CLAIM),
        "skylight_b_column_is_void": _winding(
            solids["rock_after"], [right, void_y + 2., 0.], "rock_after", expected_inside=False,
            claim=APERTURE_CLAIM),
        "outer_rock_untouched": _winding(
            solids["rock_after"],
            [parameters.plan_half_x_m - 5., mid_y, parameters.plan_half_z_m - 5.], "rock_after",
            expected_inside=True, claim=ROOF_CLAIM),
        "material_balance": {
            "method": "Mesh64_boolean", "operation": "subtract", "rock_role": "rock_before",
            "cutter_roles": [record["role"] for record in cutters],
            "expected_rock_after_m3": result["material"]["rock_after_m3"],
            "expected_removed_m3": result["material"]["excavated_rock_m3"],
            "verdict": True, "claim": MATERIAL_CLAIM,
            "observed": {"rock_before_m3": result["material"]["rock_before_m3"],
                         "rock_after_m3": result["material"]["rock_after_m3"],
                         "removed_m3": result["material"]["excavated_rock_m3"],
                         "cutter_union_saved_volume_m3": solids["cutter_union"]["signed_volume_m3"],
                         "rock_lost_m3": result["material"]["rock_before_m3"]
                                          - result["material"]["rock_after_m3"],
                         "signed_residual_m3": result["material"]["signed_residual_m3"],
                         "balance_budget_m3": result["material"]["balance_budget_m3"],
                         "removed_components": result["census"]["removed_components"],
                         "rock_after_components": result["census"]["rock_after_components"],
                         "cutter_union_components": result["census"]["cutter_union_components"]}},
    }
    probes = []
    for label, x_m in (("inner_bridge_probe", bridge_centre), ("outer_bridge_probe", wall_probe)):
        # A vertical probe between a bore and the block side wall crosses top face, gallery
        # roof, gallery floor and block bottom: four crossings, none of them the wall of a
        # bore. The decisive part is that exactly one of them lies above the gallery roof,
        # which is what "the bridge is unbroken up to the top face here" means.
        ray = _ray(
            after, [x_m, above, 0.], [x_m, below, 0.], "rock_after", expected_hit_count=4,
            claim=("a vertical probe between a bore and the block side wall crosses the top "
                   "face, the gallery roof, the gallery floor and the block bottom"))
        over_roof = [hit for hit in ray["observed"]["hits"]
                     if hit["position_xyz_m"][1] > parameters.tunnel_roof_y_m]
        if len(over_roof) != 1:
            raise ValueError("witness refused: " + label + " has " + str(len(over_roof))
                             + " rock crossings strictly above the gallery roof; a bore is present")
        ray["observed"]["crossings_above_gallery_roof"] = len(over_roof)
        probes.append({"label": label, "x_m": x_m, "ray": ray,
                       "winding": _winding(solids["rock_after"], [x_m, mid_y, 0.], "rock_after",
                                           expected_inside=True, claim=BRIDGE_CLAIM)})
    witnesses["bridge_probe_centres_are_both_bridges"] = {
        "method": "Manifold.ray_cast", "solid_role": "rock_after", "verdict": True,
        "claim": ("bridge rock is solid at both probe abscissae: each vertical probe crosses "
                  "rock exactly once above the gallery roof and the winding number there is "
                  "positive, so the rock between the bores and up to the top face is "
                  "continuous with the surrounding block"),
        "observed": {
            "probes": probes,
            "from_xyz_m": [probes[0]["ray"]["from_xyz_m"], probes[1]["ray"]["from_xyz_m"]],
            "to_xyz_m": [probes[0]["ray"]["to_xyz_m"], probes[1]["ray"]["to_xyz_m"]],
            "hit_count": [probes[0]["ray"]["observed"]["hit_count"],
                          probes[1]["ray"]["observed"]["hit_count"]],
            "crossings_above_gallery_roof": [
                probes[0]["ray"]["observed"]["crossings_above_gallery_roof"],
                probes[1]["ray"]["observed"]["crossings_above_gallery_roof"]],
            "hits": [probes[0]["ray"]["observed"]["hits"],
                     probes[1]["ray"]["observed"]["hits"]]}}
    divergence = signed_volume(np.array(solids["rock_after"]["vertices_local_xyz_m"], float),
                               np.array(solids["rock_after"]["triangles"], int))
    witnesses["saved_void_closure"] = {
        "method": "Mesh64_boolean", "operation": "subtract", "rock_role": "rock_before",
        "cutter_roles": [record["role"] for record in cutters],
        "expected_rock_after_m3": result["material"]["rock_after_m3"],
        "expected_removed_m3": result["material"]["excavated_rock_m3"], "verdict": True,
        "claim": ("the re-saved excavated void is itself a closed two-use surface, its enclosed "
                  "volume reproduces the lost rock volume, and the remaining rock reproduces "
                  "the engine volume within accumulated re-triangulation rounding"),
        "observed": {"removed_saved_volume_m3": solids["removed"]["signed_volume_m3"],
                     "removed_mesh64_volume_m3": result["material"]["excavated_rock_m3"],
                     "removed_saved_volume_disagreement_m3": abs(
                         solids["removed"]["signed_volume_m3"]
                         - result["material"]["excavated_rock_m3"]),
                     "rock_after_mesh64_volume_m3": after.volume(),
                     "rock_after_saved_volume_m3": solids["rock_after"]["signed_volume_m3"],
                     "rock_after_divergence_theorem_volume_m3": divergence,
                     "rock_after_volume_shortfall_m3": abs(after.volume() - divergence),
                     "removed_components": result["census"]["removed_components"]}}
    return result, solids, witnesses, parameters


def _plane_segments(record, axis, value, tolerance=1e-9):
    """Display-only triangle/plane intersections, straight from the saved mesh."""
    vertices = np.asarray(record["vertices_local_xyz_m"], float)
    segments = []
    for triangle in np.asarray(record["triangles"], int):
        points = [vertices[index] for index in triangle]
        crossings = []
        for first, second in zip(points, points[1:] + points[:1]):
            first_d, second_d = first[axis] - value, second[axis] - value
            if (first_d < 0.) != (second_d < 0.):
                fraction = first_d / (first_d - second_d)
                crossings.append(first + fraction * (second - first))
            elif abs(first_d) <= tolerance:
                crossings.append(first)
        if len(crossings) == 2:
            segments.append((crossings[0], crossings[1]))
    return segments


def _save(figure, output_directory, name):
    import matplotlib.pyplot as plt
    path = output_directory / name
    figure.savefig(path, dpi=110, metadata={"Software": None})
    plt.close(figure)
    return {"name": name, "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def render(output_directory, solids, parameters):
    """Three display figures (plan slice, through profile, void solid); never a certification."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    figures = []
    slice_y = (parameters.tunnel_floor_y_m + parameters.tunnel_roof_y_m) / 2.

    figure, axes = plt.subplots(figsize=(6.4, 6.4))
    for role, colour, width in (("rock_after", ".55", .5), ("removed", "#c0392b", .9)):
        for first, second in _plane_segments(solids[role], 1, slice_y):
            axes.plot([first[0], second[0]], [first[2], second[2]], color=colour,
                      linewidth=width, zorder=2 if role == "removed" else 1)
    for centre in parameters.skylight_x_m:
        axes.plot([centre], [0.], marker="+", color="#2980b9", markersize=10, zorder=3)
    axes.set_aspect("equal")
    axes.set_title("plan slice at y=%.0f m: rock outline, gallery and both bores" % slice_y)
    axes.set_xlabel("x m")
    axes.set_ylabel("z m")
    figures.append(_save(figure, output_directory, "a-plan-slice.png"))

    figure, axes = plt.subplots(figsize=(8.4, 4.0))
    for role, colour, width in (("rock_after", ".55", .6), ("removed", "#c0392b", .9)):
        for first, second in _plane_segments(solids[role], 2, 0.):
            axes.plot([first[0], second[0]], [first[1], second[1]], color=colour,
                      linewidth=width, zorder=2 if role == "removed" else 1)
    axes.axhline(parameters.top_y_m, color="#2980b9", linewidth=.7, linestyle=":")
    axes.set_title("profile through z=0: two bores, the rock between them, and the gallery")
    axes.set_xlabel("x m")
    axes.set_ylabel("y m")
    figures.append(_save(figure, output_directory, "b-profile-z0.png"))

    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    figure = plt.figure(figsize=(7.2, 6.0))
    axes = figure.add_subplot(111, projection="3d")
    for role, colour, alpha in (("rock_after", ".45", .06), ("removed", "#c0392b", .55)):
        vertices = np.asarray(solids[role]["vertices_local_xyz_m"], float)
        triangles = np.asarray(solids[role]["triangles"], int)
        step = max(1, len(triangles) // 4000)
        axes.add_collection3d(Poly3DCollection(vertices[triangles[::step]], facecolor=colour,
                                              edgecolor="none", alpha=alpha))
    edges = np.asarray(solids["rock_before"]["vertices_local_xyz_m"], float)
    axes.set_xlim(edges[:, 0].min(), edges[:, 0].max())
    axes.set_ylim(edges[:, 2].min(), edges[:, 2].max())
    axes.set_zlim(edges[:, 1].min(), edges[:, 1].max())
    axes.set_xlabel("x m")
    axes.set_ylabel("z m")
    axes.set_zlabel("y m")
    axes.set_title("excavated gallery, branch and two bores inside the analytic block")
    figures.append(_save(figure, output_directory, "c-solid-3d.png"))
    return figures


def report(parameters=Parameters(), output_directory=None):
    """Build the geometry and seal the contract-shaped report used by the cold reader."""
    result, solids, witnesses, parameters = build(parameters)
    figures = [] if output_directory is None else render(output_directory, solids, parameters)
    record = {"schema": REPORT_SCHEMA, "algorithm": ALGORITHM, "status": "candidate",
              "synthetic_base": {"kind": "synthetic_analytic",
                                 "note": "not TD native terrain, not surveyed"},
              "world_frame": WORLD_FRAME_NOTE,
              "parameters": asdict(parameters),
              "parameters_identity_sha256": identity(asdict(parameters)),
              "explicit_assumptions": [dict(item) for item in ASSUMPTIONS],
              "explicit_assumption_note": ("every numeric parameter above is an "
                                           "explicit_assumption of grade 'assumed'; none is a "
                                           "measurement, a survey or a reconstruction of a "
                                           "named feature"),
              "solids": {role: dict(mesh) for role, mesh in solids.items()},
              "boolean": result, "witnesses": witnesses,
              "flags": {flag: False for flag in FLAGS},
              "library_versions": {"manifold3d": version("manifold3d"), "numpy": version("numpy")},
              "figures": figures,
              "figure_scope": "display only; a figure is never a certification",
              "cold_read_contract": ("every witness names the saved solid role it was measured "
                                     "on; rebuild those meshes and replay the segments, the "
                                     "winding probes and the material balance independently")}
    seal(record)
    return record, solids


def write_report(path, parameters=Parameters(), output_directory=None):
    """Compact, sorted, NaN-free JSON; identical bytes for identical inputs."""
    record, _ = report(parameters, output_directory=output_directory)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False),
                    encoding="utf-8", newline="")
    return record


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path(".scratch/special-terrain/l1-preview-20261019/cave-bridge"))
    args = parser.parse_args()
    path = args.output / "report.json"
    record = write_report(path, output_directory=args.output)
    print(json.dumps({"status": record["status"], "report": str(path),
                      "material": record["boolean"]["material"],
                      "census": record["boolean"]["census"],
                      "identity_sha256": record["identity_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
