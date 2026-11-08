"""Offline L1 volume geometry: tiankeng sinkhole shaft, subsurface river and skylight.

Volume route, not a field/VMD form: a synthetic analytic rock block is really subtracted
with Mesh64 booleans. The excavated void is one connected solid made of a near-vertical
collapse funnel, two concentric terrace benches, a buried subsurface river reach and one
tributary branch, so the sinkhole floor is drained underground while nothing except the
shaft collar reaches the ground surface.

**This is not a restoration of any real landform and is not TD native terrain.** The base
is an explicit synthetic analytic flat-topped block at ``ground_surface_y_m = 0``. Every
dimension below is an ``explicit_assumption`` in the sense of
``.scratch/special-terrain/parameters-and-sources.md``: no source in that ledger supplies
a tiankeng shaft radius, wall slope, bench spacing, shaft depth, river section or burial
depth, so the numbers here are a deliberate parameterisation choice and must never be
quoted as a survey, an institutional value or a measurement.

Three prerequisites stand between this geometry and any hydraulic or consumer use, and
none of them is solved here:

1. an explicit terminal declaration for the underground reach (the engineering contract is
   "no depression filling, and a reach is only legal with an explicit outlet");
2. a lake-domain record for the shaft volume ``metric_natural_lakes`` expects;
3. an interior-loss contract for the closed reach, whose flux is currently hard zero.

``report.json`` (written by :func:`write_preview`) follows the shared P5 field contract so
a cold auditor can recompute it without importing this module: ``solids`` inlines every
complete saved mesh record, ``boolean`` inlines the ``excavate`` result verbatim, and every
``witnesses`` entry is one of the three recomputable shapes (``Manifold.ray_cast`` /
``Solid.winding`` / ``Mesh64_boolean``) referring to roles that exist in ``solids``. The
file is written compact with sorted keys and no NaN, with relative figure names and no
timestamp, so two runs of the same parameters are byte-identical; every capability flag is
written False and ``status`` is ``candidate``.

Invariant note (why the river ceiling sits *above* the shaft bottom): the buried reach must
overlap the shaft in elevation, otherwise the subtraction would leave two separate voids and
the floor would be sealed rock. The shaft therefore cuts down through the river ceiling, the
two cutters' interiors overlap, and the excavated void is a single connected solid -- which
``census`` re-checks instead of assuming.
"""

from dataclasses import asdict, dataclass
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.hybrid_cave_geometry import ray_hits, seal
from terrain_pipeline.hybrid_rock_boolean import (
    FLAGS, BooleanParameters, census, excavate, frustum_record, octagon_ring,
    polygon_prism_record, solid_from_record)
from terrain_pipeline.hybrid_river_graph import identity

SCHEMA = "td-special-terrain-l1-sinkhole-v1"
ALGORITHM = "sampled-rock-sinkhole-shaft-subsurface-river-skylight-v1"
SOLID_SCHEMA = "td-hybrid-local-solid-mesh-v1"
BASE_KIND = "synthetic_analytic"
BASE_NOTE = "not TD native terrain, not surveyed"
LOCAL_ORIGIN = np.array([1200., 480., -2500.])
WITNESS_TOLERANCE_M = 1e-6
CUTTER_ROLES = ("shaft_funnel", "upper_terrace_bench", "lower_terrace_bench", "subsurface_river",
                "river_branch")
FIGURE_NAMES = ("sinkhole-a-plan.png", "sinkhole-b-profile.png", "sinkhole-c-solid.png")
PLAN_SAMPLES = 72
PROFILE_SAMPLES = 241
WITNESS_METHODS = ("Manifold.ray_cast", "Solid.winding", "Mesh64_boolean")

# Parameter name -> the exact reason it is an explicit assumption (no ledger source).
EXPLICIT_ASSUMPTIONS = {
    "block_half_span_x_m": "analytic host block size; not a landform measurement",
    "block_half_span_z_m": "analytic host block size; not a landform measurement",
    "ground_surface_y_m": "analytic flat top elevation; not a surveyed surface",
    "block_floor_y_m": "analytic block floor chosen below every cutter; not a measurement",
    "shaft_bottom_y_m": "no tiankeng depth source; parameterisation choice",
    "shaft_collar_y_m": "protrusion above the block chosen so the subtraction is not coplanar",
    "shaft_radius_bottom_m": "no tiankeng shaft radius source; parameterisation choice",
    "shaft_radius_top_m": "no tiankeng collar radius source; parameterisation choice",
    "shaft_segments": "ring resolution of the analytic funnel; not a measurement",
    "terrace_segments": "ring resolution of the analytic benches; not a measurement",
    "upper_terrace_radius_m": "no bench spacing source; parameterisation choice",
    "upper_terrace_bottom_y_m": "no bench spacing source; parameterisation choice",
    "upper_terrace_top_y_m": "no bench spacing source; parameterisation choice",
    "lower_terrace_radius_m": "no bench spacing source; parameterisation choice",
    "lower_terrace_bottom_y_m": "no bench spacing source; parameterisation choice",
    "lower_terrace_top_y_m": "no bench spacing source; parameterisation choice",
    "river_half_width_m": "no subsurface river section source; parameterisation choice",
    "river_reach_x_m": "reach length chosen to stay wholly buried inside the block",
    "river_bed_y_m": "no subsurface river burial depth source; parameterisation choice",
    "river_ceiling_y_m": "no subsurface river burial depth source; parameterisation choice",
    "branch_x_low_m": "tributary extent chosen to stay wholly buried inside the block",
    "branch_x_high_m": "tributary extent chosen to stay wholly buried inside the block",
    "branch_z_low_m": "tributary extent chosen to overlap the main buried reach",
    "branch_z_end_m": "tributary extent chosen to stay wholly buried inside the block",
    "branch_bed_y_m": "tributary section chosen to overlap the buried reach",
    "branch_ceiling_y_m": "tributary section chosen to overlap the buried reach",
}

PREREQUISITES = (
    "explicit_terminal_declaration_for_the_buried_reach_required_before_any_routing",
    "lake_domain_record_for_the_shaft_volume_required_before_any_lake_accounting",
    "interior_loss_contract_required_because_the_closed_reach_flux_is_currently_zero",
)


@dataclass(frozen=True)
class SinkholeParameters:
    """Bounded explicit engineering parameters; every value is an explicit assumption."""

    block_half_span_x_m: float = 60.
    block_half_span_z_m: float = 60.
    ground_surface_y_m: float = 0.
    block_floor_y_m: float = -40.
    shaft_bottom_y_m: float = -32.
    shaft_collar_y_m: float = 4.
    shaft_radius_bottom_m: float = 13.
    shaft_radius_top_m: float = 17.
    shaft_segments: int = 64
    terrace_segments: int = 48
    upper_terrace_radius_m: float = 21.
    upper_terrace_bottom_y_m: float = -9.
    upper_terrace_top_y_m: float = -6.
    lower_terrace_radius_m: float = 17.5
    lower_terrace_bottom_y_m: float = -22.
    lower_terrace_top_y_m: float = -19.
    river_half_width_m: float = 5.
    river_reach_x_m: float = 55.
    river_bed_y_m: float = -36.
    river_ceiling_y_m: float = -28.
    branch_x_low_m: float = -29.
    branch_x_high_m: float = -23.
    branch_z_low_m: float = -5.
    branch_z_end_m: float = 38.
    branch_bed_y_m: float = -36.
    branch_ceiling_y_m: float = -30.

    def __post_init__(self):
        floats = {key: value for key, value in asdict(self).items()
                  if key not in ("shaft_segments", "terrace_segments")}
        if not all(type(value) is float and math.isfinite(value) for value in floats.values()):
            raise ValueError("finite explicit float parameters required")
        for name in ("shaft_segments", "terrace_segments"):
            value = getattr(self, name)
            if type(value) is not int or not 12 <= value <= 512:
                raise ValueError("bounded integer segment counts required")
        if self.shaft_collar_y_m <= self.ground_surface_y_m:
            raise ValueError("shaft collar must protrude above the ground surface")
        # The buried reach must sit above the block floor and below the ground surface, and
        # the shaft must cut *down into* it (river ceiling above the shaft bottom), otherwise
        # the two cutters would not overlap and the excavation would leave two voids.
        if not self.block_floor_y_m < self.river_bed_y_m < self.river_ceiling_y_m < self.ground_surface_y_m:
            raise ValueError("river section must be buried above the block floor and below the ground surface")
        if not self.shaft_bottom_y_m < self.river_ceiling_y_m:
            raise ValueError("shaft must cut down into the river section so the void stays one connected solid")
        if not 0. < self.shaft_radius_bottom_m < self.shaft_radius_top_m <= min(
                self.block_half_span_x_m, self.block_half_span_z_m) / 2.:
            raise ValueError("shaft radii must be positive, widening upward and inside the block")
        if not self.shaft_radius_top_m < self.lower_terrace_radius_m < self.upper_terrace_radius_m <= min(
                self.block_half_span_x_m, self.block_half_span_z_m) / 2.:
            raise ValueError("terrace radii must be outside the collar and inside the block")
        if not self.upper_terrace_bottom_y_m < self.upper_terrace_top_y_m < self.ground_surface_y_m:
            raise ValueError("terrace benches must stay below the ground surface")
        if not self.lower_terrace_bottom_y_m < self.lower_terrace_top_y_m < self.upper_terrace_bottom_y_m:
            raise ValueError("terrace benches must be ordered below the upper bench")
        if not self.lower_terrace_top_y_m > self.shaft_bottom_y_m:
            raise ValueError("lower bench must stay above the shaft floor")
        if not 0. < self.river_half_width_m < self.block_half_span_z_m / 2.:
            raise ValueError("subsurface river half width must stay inside the block")
        if not self.river_half_width_m < self.river_reach_x_m < self.block_half_span_x_m:
            raise ValueError("buried reach must stop inside the block so no second surface opening appears")
        if not (self.branch_x_low_m < self.branch_x_high_m
                and -self.river_reach_x_m <= self.branch_x_low_m
                and self.branch_x_high_m <= self.river_reach_x_m):
            raise ValueError("branch must leave the main reach inside the buried footprint")
        if not -self.block_half_span_z_m < self.branch_z_low_m < self.branch_z_end_m < self.block_half_span_z_m:
            raise ValueError("branch must stay wholly buried inside the block")
        if not self.branch_z_low_m < self.river_half_width_m:
            raise ValueError("branch must overlap the main buried reach in the z direction")
        # Genuine three-axis overlap with the main reach, so the unified void stays connected.
        if not (self.branch_bed_y_m < self.branch_ceiling_y_m
                and self.branch_bed_y_m < self.river_ceiling_y_m
                and self.branch_ceiling_y_m > self.river_bed_y_m
                and self.branch_z_low_m < self.river_half_width_m):
            raise ValueError("branch section must overlap the buried reach in all three axes")


def as_parameters(parameters):
    """Accept the frozen dataclass or a plain parameter mapping; refuse anything else."""
    if isinstance(parameters, SinkholeParameters):
        return parameters
    if isinstance(parameters, dict):
        return SinkholeParameters(**parameters)
    raise ValueError("explicit SinkholeParameters or parameter mapping required")


def as_origin(origin):
    origin = np.asarray(origin, float)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("finite three-component local origin required")
    return origin


def assumption_list(parameters):
    """The report's explicit-assumption ledger; every entry is graded ``assumed``."""
    values = asdict(as_parameters(parameters))
    entries = []
    for name, reason in sorted(EXPLICIT_ASSUMPTIONS.items()):
        if name not in values:
            raise ValueError("explicit assumption names an unknown parameter: " + name)
        if not isinstance(reason, str) or not reason:
            raise ValueError("explicit assumption requires a stated reason: " + name)
        entries.append({"name": name, "value": values[name], "grade": "assumed", "reason": reason})
    return entries


def library_versions():
    return {"manifold3d": importlib.metadata.version("manifold3d"), "numpy": np.__version__}


def rectangle_ring(x_low, x_high, z_low, z_high):
    """Counter-clockwise rectangle in the (x, z) plane for buried prism cutters."""
    for value in (x_low, x_high, z_low, z_high):
        if type(value) is not float or not math.isfinite(value):
            raise ValueError("finite float rectangle bounds required")
    if not (x_low < x_high and z_low < z_high):
        raise ValueError("strictly increasing rectangle bounds required")
    return np.array([[x_low, z_low], [x_high, z_low], [x_high, z_high], [x_low, z_high]], float)


def _body(parameters, origin):
    return polygon_prism_record(rectangle_ring(-parameters.block_half_span_x_m, parameters.block_half_span_x_m,
                                               -parameters.block_half_span_z_m, parameters.block_half_span_z_m),
                                parameters.block_floor_y_m, parameters.ground_surface_y_m, origin, "rock_before")


def _cutters(parameters, origin):
    """The five declared closed cutters, in the fixed ``CUTTER_ROLES`` order."""
    shaft = frustum_record([0., 0.], [0., 0.], parameters.shaft_bottom_y_m, parameters.shaft_collar_y_m,
                           parameters.shaft_radius_bottom_m, parameters.shaft_radius_top_m, origin, "shaft_funnel",
                           segments=parameters.shaft_segments)
    upper = polygon_prism_record(octagon_ring([0., 0.], parameters.upper_terrace_radius_m,
                                              parameters.upper_terrace_radius_m, parameters.terrace_segments),
                                 parameters.upper_terrace_bottom_y_m, parameters.upper_terrace_top_y_m,
                                 origin, "upper_terrace_bench")
    lower = polygon_prism_record(octagon_ring([0., 0.], parameters.lower_terrace_radius_m,
                                              parameters.lower_terrace_radius_m, parameters.terrace_segments),
                                 parameters.lower_terrace_bottom_y_m, parameters.lower_terrace_top_y_m,
                                 origin, "lower_terrace_bench")
    river = polygon_prism_record(rectangle_ring(-parameters.river_reach_x_m, parameters.river_reach_x_m,
                                                -parameters.river_half_width_m, parameters.river_half_width_m),
                                 parameters.river_bed_y_m, parameters.river_ceiling_y_m, origin, "subsurface_river")
    branch = polygon_prism_record(rectangle_ring(parameters.branch_x_low_m, parameters.branch_x_high_m,
                                                 parameters.branch_z_low_m, parameters.branch_z_end_m),
                                  parameters.branch_bed_y_m, parameters.branch_ceiling_y_m, origin, "river_branch")
    return [shaft, upper, lower, river, branch]


def solid_winding(record, point_xyz_m, origin):
    """Van Oosterom-Strackee solid-angle winding of one saved solid at one world point.

    Independent of the Mesh64 engine: it reads only the saved local vertices/triangles, so a
    cold auditor can reproduce the same number with its own implementation (the
    ``tools/hybrid_cave_saved_audit.Solid.winding`` formulation).
    """
    vertices = np.asarray(record["vertices_local_xyz_m"], float)
    local_point = np.asarray(point_xyz_m, float) - np.asarray(origin, float)
    offsets = vertices[np.asarray(record["triangles"], int)] - local_point
    lengths = np.linalg.norm(offsets, axis=2)
    if not np.all(lengths > 1e-9):
        raise ValueError("winding probe touches a saved vertex")
    first, second, third = offsets[:, 0], offsets[:, 1], offsets[:, 2]
    numerator = np.einsum("ij,ij->i", first, np.cross(second, third))
    denominator = lengths.prod(axis=1)
    denominator += np.einsum("ij,ij->i", first, second) * lengths[:, 2]
    denominator += np.einsum("ij,ij->i", second, third) * lengths[:, 0]
    denominator += np.einsum("ij,ij->i", third, first) * lengths[:, 1]
    return math.fsum((2. * np.arctan2(numerator, denominator)).tolist()) / (4. * math.pi)


def _ray_witness(solid, origin, role, first, second, expected_hit_count, claim, first_hit_y_m=None):
    hits = ray_hits(solid, list(first), list(second), origin)
    observed_first = hits[0]["position_xyz_m"][1] if hits else None
    verdict = bool(len(hits) == expected_hit_count)
    if first_hit_y_m is not None:
        verdict = bool(verdict and observed_first is not None
                       and abs(observed_first - float(first_hit_y_m)) <= WITNESS_TOLERANCE_M)
    if not verdict:
        raise ValueError("vertical_ray_witness_failed:" + role + ":" + str(claim))
    return {"method": "Manifold.ray_cast", "solid_role": role,
            "from_xyz_m": [float(value) for value in first],
            "to_xyz_m": [float(value) for value in second],
            "expected_hit_count": int(expected_hit_count), "verdict": True, "claim": claim,
            "observed": {"hit_count": len(hits), "first_hit_y_m": observed_first, "hits": hits}}


def _winding_witness(record, origin, point_xyz_m, expected_inside, claim):
    winding = solid_winding(record, point_xyz_m, origin)
    near_integer = min(abs(winding), abs(1. - winding)) <= 1e-6
    verdict = bool(near_integer and (winding > .5) == bool(expected_inside))
    if not verdict:
        raise ValueError("winding_witness_failed:" + str(claim))
    return {"method": "Solid.winding", "solid_role": record["role"],
            "point_xyz_m": [float(value) for value in point_xyz_m],
            "expected_inside": bool(expected_inside), "verdict": True, "claim": claim,
            "observed": {"winding": winding}}


def _vertical(x_m, z_m, from_y_m, to_y_m):
    return (float(x_m), float(from_y_m), float(z_m)), (float(x_m), float(to_y_m), float(z_m))


def witnesses(record, solids, parameters, origin):
    """Actual recomputable evidence: skylight rays, void winding, and volume accounting.

    Every entry is one of the three cold-auditable shapes and refers only to roles saved in
    ``solids``. Each claim is *refused* (raise) here when the measured geometry disagrees, so
    a recorded ``verdict: true`` is a measurement rather than a declaration of intent.
    """
    before = solid_from_record(solids["rock_before"], "rock_before")
    after = solid_from_record(solids["rock_after"], "rock_after")
    above = 20.
    river_entry_y = parameters.river_ceiling_y_m - 2.
    under_floor_y = parameters.block_floor_y_m + 1.
    entries = {}

    entries["skylight_axis_blocked_before_excavation"] = _ray_witness(
        before, origin, "rock_before", *_vertical(0., 0., above, river_entry_y), 1,
        "before the Boolean the shaft axis was solid rock: a vertical ray meets exactly one "
        "crossing, the intact top face, so no skylight existed there")
    entries["skylight_axis_open_after_excavation"] = _ray_witness(
        after, origin, "rock_after", *_vertical(0., 0., above, river_entry_y), 0,
        "after the Boolean a vertical ray on the shaft axis meets no rock surface between "
        "above ground and the buried river ceiling: the collar is a real skylight into the "
        "excavated void, measured with Manifold.ray_cast, not inferred")
    entries["shaft_floor_is_the_buried_river_bed"] = _ray_witness(
        after, origin, "rock_after", *_vertical(0., 0., above, under_floor_y), 1,
        "the only rock crossing on the shaft axis below the void is the buried river bed at "
        "the declared bed elevation, so the shaft floor drains into the subsurface reach "
        "instead of being sealed by rock",
        first_hit_y_m=parameters.river_bed_y_m)

    # Surface-band rays stop just below the ground surface, so they measure surface openings
    # only: a buried conduit crossing further down cannot be confused with a second opening.
    surface_band_to_y = parameters.ground_surface_y_m - 3.
    open_samples = ((4., 0.), (8., 0.), (11.5, 8.), (14., -6.), (8., -12.))
    for ordinal, (x_m, z_m) in enumerate(open_samples):
        entries["collar_footprint_open_sample_%02d" % ordinal] = _ray_witness(
            after, origin, "rock_after", *_vertical(x_m, z_m, above, surface_band_to_y), 0,
            "footprint sample inside the collar radius: the surface-band ray meets no rock, so the "
            "collar is an opening between above ground and the near-surface rock band")

    closed_samples = ((24., 0.), (21., 21.), (36., 0.), (0., 36.), (-32., 32.), (-54., 0.),
                      (-24., 0.), (32., -32.), (-54., 12.), (50., 0.), (0., 24.), (0., -24.),
                      (0., -52.), (12., -52.))
    for ordinal, (x_m, z_m) in enumerate(closed_samples):
        entries["outside_collar_surface_intact_sample_%02d" % ordinal] = _ray_witness(
            after, origin, "rock_after", *_vertical(x_m, z_m, above, surface_band_to_y), 1,
            "footprint sample outside the collar radius: exactly one crossing, the intact top face "
            "at the declared ground surface, so the ground surface is continuous here and this is "
            "not a second surface opening",
            first_hit_y_m=parameters.ground_surface_y_m)

    winding_cases = (
        ("shaft_interior_is_void", (0., -10., 0.), False,
         "the carved shaft interior is outside the remaining rock"),
        ("buried_river_interior_is_void", (40., -32., 0.), False,
         "the buried reach interior is outside the remaining rock and stays wholly under the block"),
        ("branch_interior_is_void", (-26., -33., 30.), False,
         "the tributary branch interior is outside the remaining rock"),
        ("intact_rock_mass_is_solid", (40., -20., 40.), True,
         "rock far from the excavation stays inside the remaining rock"),
        ("ground_surface_outside_collar_is_solid_a", (40., -.5, 40.), True,
         "just below the ground surface outside the collar the remaining rock is solid"),
        ("ground_surface_outside_collar_is_solid_b", (-52., -.5, 8.), True,
         "just below the ground surface outside the collar the remaining rock is solid"),
        ("ground_surface_outside_collar_is_solid_c", (10., -.5, 50.), True,
         "just below the ground surface outside the collar the remaining rock is solid"),
        ("ground_surface_outside_collar_is_solid_d", (0., -.5, 44.), True,
         "just below the ground surface outside the collar the remaining rock is solid"),
    )
    for name, point, inside, claim in winding_cases:
        entries[name] = _winding_witness(solids["rock_after"], origin, point, inside, claim)

    material = record["material"]
    entries["material_balance_actual_volume"] = {
        "method": "Mesh64_boolean", "operation": "subtract", "rock_role": "rock_before",
        "cutter_roles": list(CUTTER_ROLES),
        "expected_rock_after_m3": material["rock_after_m3"],
        "expected_removed_m3": material["excavated_rock_m3"], "verdict": True,
        "claim": "rock_before minus the union of the five closed cutters, recomputed from the "
                 "saved meshes alone, must reproduce these rock_after and removed volumes; the "
                 "excavated void is one connected solid and the residual stays inside the "
                 "declared balance budget",
        "observed": {"rock_before_m3": material["rock_before_m3"],
                     "rock_after_m3": material["rock_after_m3"],
                     "removed_m3": material["excavated_rock_m3"],
                     "residual_m3": material["signed_residual_m3"],
                     "balance_budget_m3": material["balance_budget_m3"],
                     "cutter_union_m3": solids["cutter_union"]["signed_volume_m3"],
                     "removed_components": record["census"]["removed_components"],
                     "rock_after_components": record["census"]["rock_after_components"],
                     "cutter_count": record["census"]["cutter_count"]}}
    return entries


def build(parameters=SinkholeParameters(), origin=LOCAL_ORIGIN):
    """Excavate the sinkhole and return the candidate report record with its closed solids."""
    parameters = as_parameters(parameters)
    origin = as_origin(origin)
    rock_record = _body(parameters, origin)
    cutters = _cutters(parameters, origin)
    if tuple(cutter["role"] for cutter in cutters) != CUTTER_ROLES:
        raise ValueError("cutter roles differ from the declared closed cutter set")
    boolean_parameters = BooleanParameters(solids_spacing_m=1., component_limit=16)
    result, meshes = excavate(rock_record, cutters, boolean_parameters, origin,
                              minimum_removed_components=1, minimum_rock_after_components=1)
    solids = {"rock_before": rock_record}
    solids.update({cutter["role"]: cutter for cutter in cutters})
    solids.update(meshes)
    if census(solid_from_record(meshes["removed"], "removed")) != 1:
        raise ValueError("excavated_sinkhole_void_is_not_one_connected_solid")
    record = {
        "schema": SCHEMA, "algorithm": ALGORITHM, "status": "candidate",
        "synthetic_base": {"kind": BASE_KIND, "note": BASE_NOTE},
        "parameters": asdict(parameters),
        "explicit_assumptions": assumption_list(parameters),
        "solids": solids,
        "boolean": result,
        "witnesses": witnesses(result, solids, parameters, origin),
        "flags": {flag: False for flag in FLAGS},
        "library_versions": library_versions(),
        "local_origin_xyz_m": origin.tolist(),
        "source_grade": "no_ledger_source_for_any_dimension_here",
        "hydraulic_status": "offline_geometry_only_no_routing_no_filling_no_water_surface",
        "prerequisites_before_hydraulic_or_consumer_use": list(PREREQUISITES),
        "note": "offline candidate geometry of a synthetic analytic block; not a real landform restoration",
    }
    seal(record)
    return record, solids


def audit(record):
    """Cold re-check of a saved record or report: seals, flags, balance and void connectedness."""
    unsigned = {key: value for key, value in record.items() if key != "identity_sha256"}
    if identity(unsigned) != record.get("identity_sha256"):
        raise ValueError("saved sinkhole identity mismatch")
    if record["schema"] != SCHEMA or record["algorithm"] != ALGORITHM or record["status"] != "candidate" \
            or record["synthetic_base"] != {"kind": BASE_KIND, "note": BASE_NOTE}:
        raise ValueError("saved sinkhole schema/algorithm/status/base differs")
    if any(record["flags"].get(flag) is not False for flag in FLAGS):
        raise ValueError("saved sinkhole promoted a capability flag")
    boolean = record["boolean"]
    if any(boolean.get(flag) is not False for flag in FLAGS) or boolean.get("status") != "candidate":
        raise ValueError("saved sinkhole boolean promoted a capability flag or status")
    material = boolean["material"]
    if abs(material["rock_before_m3"] - material["rock_after_m3"] - material["excavated_rock_m3"]) \
            > material["balance_budget_m3"]:
        raise ValueError("saved sinkhole material balance fails cold re-check")
    if material["fill_rock_m3"] != 0. or material["rock_after_m3"] <= 0. or material["excavated_rock_m3"] <= 0.:
        raise ValueError("saved sinkhole material is not purely excavated")
    if boolean["census"]["removed_components"] != 1:
        raise ValueError("saved sinkhole void is not one connected solid")
    for name, solid in record["solids"].items():
        if solid.get("role") != name or solid.get("schema") != SOLID_SCHEMA \
                or solid.get("sampled_not_native_exact") is not True:
            raise ValueError("saved sinkhole solid role/schema mismatch for " + name)
        if identity({key: value for key, value in solid.items() if key != "identity_sha256"}) \
                != solid["identity_sha256"]:
            raise ValueError("saved sinkhole solid seal mismatch for " + name)
    for name, entry in record["witnesses"].items():
        if entry.get("method") not in WITNESS_METHODS:
            raise ValueError("unsupported witness method for " + name)
        if entry.get("verdict") is not True:
            raise ValueError("saved sinkhole witness not verified: " + name)
    return {"status": "passed", "identity_sha256": record["identity_sha256"],
            "solid_roles": sorted(record["solids"]), "witness_count": len(record["witnesses"]),
            "material": dict(material),
            "checks": ["identity", "schema", "flags", "synthetic_base", "material_balance",
                       "void_connectedness", "solid_seals", "witness_shapes"]}


def _top_surface_map(solid, origin, span, samples):
    xs = np.linspace(-span, span, samples)
    grid = np.full((samples, samples), np.nan)
    for row, x in enumerate(xs):
        for column, z in enumerate(xs):
            hits = ray_hits(solid, [float(x), 20., float(z)], [float(x), -46., float(z)], origin)
            if hits:
                grid[row, column] = hits[0]["position_xyz_m"][1]
    return xs, grid


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_preview(directory, parameters=SinkholeParameters(), origin=LOCAL_ORIGIN):
    """Write the plan / profile / solid figures plus the contract ``report.json``."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    record, solids = build(parameters, origin)
    parameters = as_parameters(parameters)
    origin = as_origin(origin)
    after = solid_from_record(solids["rock_after"], "rock_after")

    xs, grid = _top_surface_map(after, origin, parameters.block_half_span_x_m, PLAN_SAMPLES)
    figure, axes = plt.subplots(figsize=(7.2, 6.4), dpi=140)
    image = axes.imshow(grid, origin="lower", extent=[xs[0], xs[-1], xs[0], xs[-1]], cmap="terrain", aspect="equal")
    axes.set_xlabel("x [m]")
    axes.set_ylabel("z [m]")
    axes.set_title("sinkhole plan view: first vertical-hit elevation [m]")
    axes.plot([0.], [0.], marker="x", color="black")
    axes.add_patch(plt.Circle((0., 0.), parameters.shaft_radius_top_m, fill=False, color="black", linestyle=":"))
    axes.text(parameters.shaft_radius_top_m + 3., 0., "shaft collar r = %.1f m" % parameters.shaft_radius_top_m)
    figure.colorbar(image, ax=axes, label="elevation [m]")
    figure.tight_layout()
    figure.savefig(directory / FIGURE_NAMES[0])
    plt.close(figure)

    profile_z = 0.
    centres = np.linspace(-parameters.block_half_span_x_m, parameters.block_half_span_x_m, PROFILE_SAMPLES)
    columns = []
    for x in centres:
        hits = ray_hits(after, [float(x), 20., profile_z], [float(x), -46., profile_z], origin)
        if len(hits) % 2:
            raise ValueError("profile column has an odd hit count; geometry not y-columnar here")
        heights = [hit["position_xyz_m"][1] for hit in hits]
        columns.append((float(x), [(heights[index], heights[index + 1]) for index in range(0, len(heights), 2)]))
    figure, axes = plt.subplots(figsize=(9.6, 4.6), dpi=140)
    for x, pairs in columns:
        for low, high in pairs:
            axes.plot([x, x], [low, high], color="#6b4f31", linewidth=2.2)
    axes.axhline(parameters.ground_surface_y_m, color="black", linewidth=1.)
    axes.set_xlim(-parameters.block_half_span_x_m, parameters.block_half_span_x_m)
    axes.set_ylim(parameters.block_floor_y_m - 4., 12.)
    axes.set_xlabel("x [m]")
    axes.set_ylabel("elevation [m]")
    axes.set_title("sinkhole section at z = 0 m: rock [brown] left by the Mesh64 subtraction")
    figure.tight_layout()
    figure.savefig(directory / FIGURE_NAMES[1])
    plt.close(figure)

    vertices = np.array(solids["rock_after"]["vertices_local_xyz_m"], float) + origin
    triangles = np.array(solids["rock_after"]["triangles"], int)
    figure = plt.figure(figsize=(8.2, 6.4), dpi=140)
    axes = figure.add_subplot(projection="3d")
    step = max(1, len(triangles) // 1600)
    for triangle in triangles[::step]:
        loop = np.vstack((vertices[triangle], vertices[triangle[0]]))
        axes.plot(loop[:, 0], loop[:, 2], loop[:, 1], color="#6b4f31", linewidth=.35, alpha=.5)
    axes.set_xlabel("x [m]")
    axes.set_ylabel("z [m]")
    axes.set_zlabel("elevation [m]")
    axes.set_title("sinkhole solid: rock_after wireframe (sampled triangles)")
    figure.tight_layout()
    figure.savefig(directory / FIGURE_NAMES[2])
    plt.close(figure)

    report = {key: value for key, value in record.items() if key != "identity_sha256"}
    report["figures"] = [{"name": name, "path": name, "sha256": file_sha256(directory / name)}
                         for name in FIGURE_NAMES]
    seal(report)
    (directory / "report.json").write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = write_preview(arguments.output)
    print(json.dumps({"status": report["status"], "identity_sha256": report["identity_sha256"],
                      "figures": report["figures"], "material": report["boolean"]["material"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())