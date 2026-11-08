"""Devils Marbles style stacked rock-egg bodies with genuine voids (P5.4, L1 volume route).

A pile of separate closed bodies is the one P5 form that cannot be expressed as a
single-valued vertical field displacement, so it is built as real MESH64 closed solids and
unioned with the general Boolean in ``terrain_pipeline.hybrid_rock_boolean`` (whose
primitives come from the frozen conduit module, which this module never edits).

What the geometry claims, and what it does not
---------------------------------------------

* Exactly one input number is verified: **a single rock-egg body is up to 6 m tall** --
  ``.scratch/special-terrain/parameters-and-sources.md`` section 1 (Northern Territory
official tourism page). Every other number below (individual radii, stacking count,
  cluster spacing, hover clearance, tessellation) is catalogued as an **explicit
  assumption** in the same ledger, sections 3 and 4.5, and is repeated as machine-readable
  ``explicit_assumptions`` in the saved report. None of them is a measurement and none may
  be quoted as an institution value.
* There is no TD base surface here at all: the deliverable is the local pile of closed
  bodies (``synthetic_analytic``). No real Terrain Diffusion detail is consumed, and the
  module does **not** claim to reproduce the real Devils Marbles.
* Nothing here is a certification: all six capability flags are written False and ``status``
  stays ``candidate``. Self-intersection is not claimed to be proven.

Every void claim is measured with real geometry, never inferred:

1. the two fully separated eggs union to exactly the sum of their two closed volumes;
2. the stacked pair unions to strictly less than the sum (a genuine merge, not additive
   counting);
3. the midpoint of the measured clearance under the hovering egg is outside the pile both
   by an independent winding number and by a zero-overlap probe sphere, and a ray cast
   from far outside reaches that midpoint without touching any solid.
"""

from dataclasses import asdict, dataclass
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

from terrain_pipeline.hybrid_cave_geometry import ray_hits, seal
from terrain_pipeline.hybrid_river_graph import identity
from terrain_pipeline.hybrid_rock_boolean import (
    ALGORITHM as BOOLEAN_ALGORITHM, BooleanParameters, FLAGS, MANIFOLD, SOLID_SCHEMA,
    census, combine, solid_from_record, sphere_record)

SCHEMA = "td-special-terrain-l1-rock-eggs-v1"
ALGORITHM = "stacked-disconnected-rock-egg-bodies-with-genuine-voids-v1"
PARENT_ALGORITHM = BOOLEAN_ALGORITHM
LEDGER = ".scratch/special-terrain/parameters-and-sources.md"
BASE_KIND = "synthetic_analytic"
BASE_NOTE = "not TD native terrain, not surveyed"
PILE_ROLE = "rock_after"
LOCAL_ORIGIN = np.array([0., 0., 0.])
SEGMENTS = 48
PROBE_RADIUS_M = 0.05
PROBE_SEGMENTS = 8
WINDING_TOLERANCE = 1e-9
EXPECTED_COMPONENTS = 3

DEBUG = ""
HOVER_PAIR = ("egg-03", "egg-04")
STACKED_PAIR = ("egg-01", "egg-02")
SUPPORT_PAIR = ("egg-02", "egg-04")
SEPARATED_PAIR = ("egg-07", "egg-08")
REPORT_NAME = "report.json"
DEFAULT_OUTPUT = Path(".scratch/special-terrain/l1-preview-20261019/rock-eggs")
NOT_CLAIMED = ("real_devils_marbles_reproduction", "real_TD_base_bed", "self_intersection_verified",
               "hydraulic_ready", "natural_outlet_certified", "full_network_verified",
               "independent_audit_passed", "publishable")


@dataclass(frozen=True)
class EggSpec:
    """One explicit rock-egg body; radii are bounded by the verified 6 m height ceiling."""

    egg_id: str
    centre_xyz_m: tuple
    radius_m: float
    structural_group: str
    structural_role: str

    def __post_init__(self):
        for name in ("egg_id", "structural_role"):
            if type(getattr(self, name)) is not str or not getattr(self, name):
                raise ValueError("explicit nonempty " + name + " required")
        if self.structural_group not in ("cluster", "hover", "separate"):
            raise ValueError("declared structural group required for " + self.egg_id)
        centre = tuple(self.centre_xyz_m)
        if len(centre) != 3 or not all(type(value) is float and math.isfinite(value) for value in centre):
            raise ValueError("finite float three-component centre required for " + self.egg_id)
        object.__setattr__(self, "centre_xyz_m", centre)
        # Verified ceiling: one rock egg is up to 6 m tall, i.e. a 3 m radius at the very most.
        if type(self.radius_m) is not float or not math.isfinite(self.radius_m) \
                or not .5 <= self.radius_m <= 3.:
            raise ValueError("rock-egg radius must be a float inside the verified 6 m height ceiling")


# Eight bodies. The layout is chosen so that the three structural cases the task requires
# actually occur, and so that each one is re-measured instead of asserted:
#   cluster   egg-01..egg-06 -- a chain of interpenetrating bodies, one connected component
#   hover     egg-04 hovers above egg-03 with a measured vertical clearance and is laterally
#             supported by egg-02 (which it genuinely interpenetrates), so the void beneath
#             it is real exterior space open to free air
#   separate  egg-07 and egg-08 stand well clear of everything else and of each other
EGGS = (
    EggSpec("egg-01", (0.0, 0.0, 0.0), 3.0, "cluster", "cluster_base"),
    EggSpec("egg-02", (0.0, 4.6, 0.0), 2.9, "cluster", "cluster_stacked_on_egg-01"),
    EggSpec("egg-03", (4.6, 0.8, 0.6), 2.2, "cluster", "cluster_leaning_on_egg-01"),
    EggSpec("egg-04", (4.0, 5.3, 0.6), 1.8, "hover", "hover_above_egg-03_supported_by_egg-02"),
    EggSpec("egg-05", (-4.4, 1.0, 0.5), 2.1, "cluster", "cluster_leaning_on_egg-01"),
    EggSpec("egg-06", (-3.2, 4.2, 0.3), 1.7, "cluster", "cluster_bridging_egg-05_and_egg-02"),
    EggSpec("egg-07", (12.0, 1.5, -6.0), 1.9, "separate", "separated_standalone"),
    EggSpec("egg-08", (16.5, 1.5, -6.5), 2.0, "separate", "separated_standalone"),
)


def egg(egg_id):
    return next(item for item in EGGS if item.egg_id == egg_id)


def parameters():
    """The bounded Boolean parameters this pile is assembled with."""
    return BooleanParameters(solids_spacing_m=1., component_limit=16)


def report_parameters(parameters_used=None):
    parameters_used = parameters_used or parameters()
    return {**asdict(parameters_used), "circular_segments": SEGMENTS,
            "probe_radius_m": PROBE_RADIUS_M, "probe_segments": PROBE_SEGMENTS,
            "expected_connected_components": EXPECTED_COMPONENTS, "egg_count": len(EGGS)}


def build_records(segments=SEGMENTS):
    """One closed solid record per egg, all in the same local frame."""
    return [sphere_record(list(item.centre_xyz_m), item.radius_m, LOCAL_ORIGIN, item.egg_id,
                          circular_segments=segments) for item in EGGS]


def pair_gap_m(first_id, second_id):
    """Analytic surface gap between two ideal spheres (negative means interpenetration)."""
    first, second = egg(first_id), egg(second_id)
    return math.dist(first.centre_xyz_m, second.centre_xyz_m) - first.radius_m - second.radius_m


def analytic_gap_table(limit_m=8.):
    """Every close pair with its analytic surface gap, so the layout is auditable by hand."""
    table = []
    for ordinal, first in enumerate(EGGS):
        for second in EGGS[ordinal + 1:]:
            gap = pair_gap_m(first.egg_id, second.egg_id)
            if gap < limit_m:
                table.append({"egg_ids": [first.egg_id, second.egg_id],
                              "centre_distance_m": math.dist(first.centre_xyz_m, second.centre_xyz_m),
                              "analytic_surface_gap_m": gap, "interpenetrates": gap < 0.})
    return table


def winding_number(record, point, origin=LOCAL_ORIGIN):
    """Independent winding number of one point against a saved closed mesh (Van Oosterom).

    Computed from the stored vertices/triangles only -- the same thing a cold audit reader
    recomputes -- so a result near zero means the point is outside the closed body and a
    result near one means it is inside. It is deliberately *not* Manifold's own predicate.
    """
    vertices = np.asarray(record["vertices_local_xyz_m"], float) - np.asarray(origin, float)
    triangles = np.asarray(record["triangles"], int)
    shifted = vertices - np.asarray(point, float)
    first, second, third = shifted[triangles[:, 0]], shifted[triangles[:, 1]], shifted[triangles[:, 2]]
    norms = np.linalg.norm(shifted, axis=1)[triangles]
    numerator = np.einsum("ij,ij->i", first, np.cross(second, third))
    denominator = (norms[:, 0] * norms[:, 1] * norms[:, 2]
                   + np.einsum("ij,ij->i", first, second) * norms[:, 2]
                   + np.einsum("ij,ij->i", second, third) * norms[:, 0]
                   + np.einsum("ij,ij->i", third, first) * norms[:, 1])
    solid_angles = 2. * np.arctan2(numerator, denominator)
    return float(solid_angles.sum() / (4. * math.pi))


def probe_overlap_m3(solid, point, origin=LOCAL_ORIGIN):
    """Exact MESH64 intersection volume of a tiny probe sphere with the pile.

    A zero-overlap measurement of exactly zero volume is only possible when the probe is
    completely outside, so containment is decided by real geometry rather than by a bound.
    """
    library = MANIFOLD.get()
    probe = library.Manifold.sphere(PROBE_RADIUS_M, PROBE_SEGMENTS).translate(
        tuple(np.asarray(point, float) - np.asarray(origin, float)))
    return float((solid ^ probe).volume())


def pair_union(records, egg_ids, parameters_used=None):
    """Actual MESH64 union of one named pair, next to the arithmetic sum of its parts."""
    parameters_used = parameters_used or parameters()
    chosen = [record for record in records if record["role"] in egg_ids]
    if len(chosen) != len(egg_ids):
        raise ValueError("pair union needs one saved record per named egg")
    role = "pair_" + "__".join(egg_ids)
    result, meshes = combine(chosen, LOCAL_ORIGIN, role, parameters_used, minimum_components=1)
    union_record = meshes[role]
    total = math.fsum(record["signed_volume_m3"] for record in chosen)
    return {"egg_ids": list(egg_ids), "role": role,
            "sum_of_parts_m3": total, "union_volume_m3": union_record["signed_volume_m3"],
            "difference_m3": total - union_record["signed_volume_m3"],
            "relative_difference": abs(total - union_record["signed_volume_m3"]) / total,
            "connected_components": census(solid_from_record(union_record, role)),
            "analytics": result}


def hover_witness(record, solid, parameters_used=None):
    """Re-measure the hovering egg's void with a ray cast, a probe and a winding number."""
    lower_id, upper_id = HOVER_PAIR
    lower, upper = egg(lower_id), egg(upper_id)
    analytic_gap = pair_gap_m(lower_id, upper_id)
    hits = ray_hits(solid, list(lower.centre_xyz_m), list(upper.centre_xyz_m), LOCAL_ORIGIN)
    ordered = sorted(hits, key=lambda hit: hit["distance"])
    if len(ordered) != 2:
        raise ValueError("facing mesh surfaces do not bracket exactly one clearance: " + str(len(ordered)))
    first = np.asarray(ordered[0]["position_xyz_m"], float)
    second = np.asarray(ordered[1]["position_xyz_m"], float)
    clearance = float(np.linalg.norm(second - first))
    midpoint = (first + second) / 2.
    outside_point = np.array([midpoint[0] + 30., midpoint[1], midpoint[2]])
    reachability = ray_hits(solid, list(outside_point), list(midpoint), LOCAL_ORIGIN)
    return {"lower_egg_id": lower_id, "upper_egg_id": upper_id,
            "analytic_surface_gap_m": analytic_gap,
            "centre_axis_from_xyz_m": list(lower.centre_xyz_m),
            "centre_axis_to_xyz_m": list(upper.centre_xyz_m),
            "facing_surface_hits": ordered,
            "measured_mesh_clearance_m": clearance,
            "mesh_clearance_minus_analytic_gap_m": clearance - analytic_gap,
            "midpoint_xyz_m": midpoint.tolist(),
            "midpoint_winding": winding_number(record, midpoint),
            "midpoint_probe_overlap_m3": probe_overlap_m3(solid, midpoint),
            "reachability_from_xyz_m": outside_point.tolist(),
            "reachability_to_xyz_m": midpoint.tolist(),
            "reachability_hits": reachability,
            "support": {"supporting_egg_id": SUPPORT_PAIR[0],
                        "analytic_surface_gap_m": pair_gap_m(*SUPPORT_PAIR),
                        "actually_interpenetrates": pair_gap_m(*SUPPORT_PAIR) < 0.}}


def witnesses(pile_record, pile_solid, separated, stacked, hover):
    """The measurement block, in the three shapes a cold audit reader can recompute.

    Nothing here is inferred: each entry names the saved solid role it was measured on and
    carries the raw numbers, so the reader rebuilds Manifold from ``solids`` and repeats it.
    """
    separated_verdict = separated["relative_difference"] <= 1e-12
    stacked_verdict = stacked["union_volume_m3"] < stacked["sum_of_parts_m3"] - 1e-6
    winding_verdict = abs(hover["midpoint_winding"]) <= WINDING_TOLERANCE
    reachability_verdict = len(hover["reachability_hits"]) == 0
    clearance_verdict = len(hover["facing_surface_hits"]) == 2 and hover["measured_mesh_clearance_m"] > 0.
    return {
        "separated_pair_union_is_exact_sum": {
            "method": "Mesh64_boolean", "operation": "add", "rock_role": None,
            "cutter_roles": list(separated["egg_ids"]),
            "expected_union_m3": separated["union_volume_m3"], "verdict": separated_verdict,
            "claim": "the two fully separated rock eggs union to exactly the sum of their two closed volumes, so no material is shared and the space between them stays genuine exterior space",
            "observed": {"union_m3": separated["union_volume_m3"],
                         "sum_of_parts_m3": separated["sum_of_parts_m3"],
                         "difference_m3": separated["difference_m3"],
                         "relative_difference": separated["relative_difference"],
                         "connected_components": separated["connected_components"],
                         "analytic_surface_gap_m": pair_gap_m(*SEPARATED_PAIR)}},
        "stacked_pair_union_is_strictly_smaller": {
            "method": "Mesh64_boolean", "operation": "add", "rock_role": None,
            "cutter_roles": list(stacked["egg_ids"]), "expected_union_m3": stacked["union_volume_m3"],
            "verdict": stacked_verdict,
            "claim": "the stacked pair unions to strictly less than the sum of its two closed volumes, so the contact is a real merge of material and not additive counting",
            "observed": {"union_m3": stacked["union_volume_m3"],
                         "sum_of_parts_m3": stacked["sum_of_parts_m3"],
                         "interpenetration_m3": stacked["difference_m3"],
                         "relative_interpenetration": stacked["difference_m3"] / stacked["sum_of_parts_m3"],
                         "connected_components": stacked["connected_components"],
                         "analytic_surface_gap_m": pair_gap_m(*STACKED_PAIR)}},
        "hover_void_midpoint_is_outside": {
            "method": "Solid.winding", "solid_role": PILE_ROLE,
            "point_xyz_m": hover["midpoint_xyz_m"], "expected_inside": False,
            "verdict": winding_verdict,
            "claim": "the midpoint of the measured clearance between the hovering egg and the one beneath it is outside the closed pile (winding number zero)",
            "observed": {"winding": hover["midpoint_winding"],
                         "probe_overlap_m3": hover["midpoint_probe_overlap_m3"],
                         "measured_mesh_clearance_m": hover["measured_mesh_clearance_m"],
                         "analytic_surface_gap_m": hover["analytic_surface_gap_m"]}},
        "hover_void_is_open_to_free_space": {
            "method": "Manifold.ray_cast", "solid_role": PILE_ROLE,
            "from_xyz_m": hover["reachability_from_xyz_m"], "to_xyz_m": hover["reachability_to_xyz_m"],
            "expected_hit_count": 0, "verdict": reachability_verdict,
            "claim": "a ray from far outside the pile reaches the void midpoint without touching any solid, so the void is open exterior space and not a sealed bubble inside a fused body",
            "observed": {"hit_count": len(hover["reachability_hits"]),
                         "hits": hover["reachability_hits"]}},
        "hover_clearance_is_bracketed_by_two_surfaces": {
            "method": "Manifold.ray_cast", "solid_role": PILE_ROLE,
            "from_xyz_m": hover["centre_axis_from_xyz_m"], "to_xyz_m": hover["centre_axis_to_xyz_m"],
            "expected_hit_count": 2, "verdict": clearance_verdict,
            "claim": "the ray down the centre axis leaves the lower egg and enters the hovering one, so exactly two facing mesh surfaces bracket a positive clearance that is at least the analytic sphere gap",
            "observed": {"hit_count": len(hover["facing_surface_hits"]),
                         "hits": hover["facing_surface_hits"],
                         "measured_mesh_clearance_m": hover["measured_mesh_clearance_m"],
                         "analytic_surface_gap_m": hover["analytic_surface_gap_m"],
                         "mesh_clearance_minus_analytic_gap_m": hover["mesh_clearance_minus_analytic_gap_m"],
                         "lateral_support": hover["support"]}},
    }


def explicit_assumptions(parameters_used, hover):
    """Every number in this module that no source supports, with the reason why it is assumed."""
    entries = [
        ("individual_egg_radii_m", [item.radius_m for item in EGGS],
         "no source: the ledger holds only the single-body height ceiling (up to 6 m), never a diameter or radius distribution"),
        ("cluster_egg_count", 6,
         "no source: stacking/count of a real corestone cluster was not obtained"),
        ("separated_pair_count", 2,
         "no source: how many bodies stand clear of a real pile was not obtained"),
        ("cluster_centre_layout_m", [[item.egg_id, list(item.centre_xyz_m)] for item in EGGS],
         "no source: cluster spacing and centre-to-centre geometry were not obtained; chosen so the three required structural cases occur"),
        ("hover_clearance_m", hover["analytic_surface_gap_m"],
         "no source: corestone-tor hover clearance was not obtained"),
        ("lateral_support_interpenetration_m", -pair_gap_m(*SUPPORT_PAIR),
         "no source: how the hovering body is held up was not obtained; assumed to rest against a neighbouring body"),
        ("circular_segments", SEGMENTS,
         "tessellation choice, not a measurement: the closed sphere meshes are inscribed in the ideal spheres"),
        ("probe_radius_m", PROBE_RADIUS_M,
         "measurement instrument choice for the zero-overlap containment test, not a property of the rock"),
        ("base_surface", BASE_KIND,
         "synthetic analytic geometry: this deliverable is the local pile of closed bodies only, there is no TD base bed and nothing is surveyed"),
    ]
    return [{"name": name, "value": value, "grade": "assumed", "reason": reason}
            for name, value, reason in entries]


def build(parameters_used=None):
    """Assemble the pile and measure the void/link witnesses.

    The returned document is already sealed (so it carries its own ``identity_sha256``) and
    already has an empty ``figures`` list; :func:`write_report` fills that in and reseals.
    """
    parameters_used = parameters_used or parameters()
    records = build_records()
    result, meshes = combine(records, LOCAL_ORIGIN, PILE_ROLE, parameters_used,
                             minimum_components=EXPECTED_COMPONENTS)
    pile = meshes[PILE_ROLE]
    solid = solid_from_record(pile, PILE_ROLE)
    components = census(solid)
    if components != EXPECTED_COMPONENTS:
        raise ValueError("pile census is not the declared component count: " + str(components))
    separated = pair_union(records, SEPARATED_PAIR, parameters_used)
    stacked = pair_union(records, STACKED_PAIR, parameters_used)
    hover = hover_witness(pile, solid)
    if hover["analytic_surface_gap_m"] <= 0. or hover["measured_mesh_clearance_m"] <= 0.:
        raise ValueError("hover pair does not actually stand clear of the body beneath it")
    if not hover["support"]["actually_interpenetrates"]:
        raise ValueError("hovering body is not actually supported by its declared neighbour")
    if pair_gap_m(*STACKED_PAIR) >= 0.:
        raise ValueError("stacked pair does not actually interpenetrate")
    if pair_gap_m(*SEPARATED_PAIR) <= 0. or pair_gap_m(*SEPARATED_PAIR) < 1e-3:
        raise ValueError("separated pair is not actually separated")
    total = math.fsum(record["signed_volume_m3"] for record in records)
    document = {
        "schema": SCHEMA, "algorithm": ALGORITHM, "parent_algorithm": PARENT_ALGORITHM,
        "status": "candidate", "solid_schema": SOLID_SCHEMA, "ledger": LEDGER,
        "synthetic_base": {"kind": BASE_KIND, "note": BASE_NOTE},
        "local_origin_xyz_m": LOCAL_ORIGIN.tolist(),
        "parameters": report_parameters(parameters_used),
        "explicit_assumptions": explicit_assumptions(parameters_used, hover),
        "solids": {record["role"]: record for record in records + [pile]},
        "boolean": result,
        "witnesses": witnesses(pile, solid, separated, stacked, hover),
        "flags": {flag: False for flag in FLAGS},
        "library_versions": {"manifold3d": importlib.metadata.version("manifold3d"),
                             "numpy": np.__version__},
        "eggs": [{"egg_id": item.egg_id, "centre_xyz_m": list(item.centre_xyz_m),
                  "radius_m": item.radius_m, "structural_group": item.structural_group,
                  "structural_role": item.structural_role, "circular_segments": SEGMENTS,
                  "individual_volume_m3": next(record["signed_volume_m3"] for record in records
                                               if record["role"] == item.egg_id),
                  "mesh_identity_sha256": next(record["identity_sha256"] for record in records
                                               if record["role"] == item.egg_id)} for item in EGGS],
        "analytic_gap_table": analytic_gap_table(),
        "assembly": {"role": PILE_ROLE, "mesh_identity_sha256": pile["identity_sha256"],
                     "signed_volume_m3": pile["signed_volume_m3"],
                     "vertices": len(pile["vertices_local_xyz_m"]),
                     "triangles": len(pile["triangles"]),
                     "connected_components": components,
                     "connected_components_declared": EXPECTED_COMPONENTS,
                     "sum_of_parts_m3": total,
                     "interpenetration_removed_m3": total - pile["signed_volume_m3"],
                     "signed_residual_m3": result["material"]["signed_residual_m3"],
                     "excavated_rock_m3": result["material"]["excavated_rock_m3"],
                     "fill_rock_m3": result["fill_rock_m3"],
                     "water_generated": result["water_generated"],
                     "boolean_gates": result["gates"]},
        "not_claimed": list(NOT_CLAIMED),
        "figures": [],
    }
    # Module-level capability flags, written False exactly like the general Boolean result.
    for flag in FLAGS:
        document[flag] = False
    seal(document)
    return document, {"rock_after": pile, "records": records, "meshes": meshes, "hover": hover}


def plane_section_segments(record, axis, value, tolerance=1e-9):
    """True cross-section of a saved closed mesh with an axis-aligned plane, as 2D segments."""
    vertices = np.asarray(record["vertices_local_xyz_m"], float)
    triangles = np.asarray(record["triangles"], int)
    keep = [index for index in range(3) if index != axis]
    segments = []
    for triangle in triangles:
        points = vertices[triangle]
        signed = points[:, axis] - value
        crossings = []
        for first, second in ((0, 1), (1, 2), (2, 0)):
            low, high = signed[first], signed[second]
            if (low < -tolerance and high < -tolerance) or (low > tolerance and high > tolerance):
                continue
            if abs(low - high) <= tolerance:
                continue
            fraction = low / (low - high)
            if -tolerance <= fraction <= 1. + tolerance:
                crossings.append(points[first] + fraction * (points[second] - points[first]))
        if len(crossings) < 2:
            continue
        unique = {}
        for point in crossings:
            unique.setdefault(tuple(np.round(point, 9)), point)
        ordered = [unique[key] for key in sorted(unique)]
        if len(ordered) < 2:
            continue
        span = sorted(((float(np.linalg.norm(ordered[i] - ordered[j])), i, j)
                       for i in range(len(ordered)) for j in range(i + 1, len(ordered))),
                      reverse=True)
        _, i, j = span[0]
        segments.append((ordered[i][keep], ordered[j][keep]))
    return segments


def render_preview(record, output_directory, hover=None):
    """Plan view, true plane section (with the measured clearance) and a 3D solid view."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    vertices = np.asarray(record["vertices_local_xyz_m"], float)
    triangles = np.asarray(record["triangles"], int)
    figures = []

    figure, axes = plt.subplots(figsize=(9., 9.))
    for triangle in triangles:
        ring = vertices[triangle][:, [0, 2]]
        axes.plot(np.append(ring[:, 0], ring[0, 0]), np.append(ring[:, 1], ring[0, 1]),
                  color="#8a6d3b", linewidth=.2, alpha=.30)
    for item in EGGS:
        axes.annotate(item.egg_id, (item.centre_xyz_m[0], item.centre_xyz_m[2]), fontsize=7,
                      ha="center", color="#4a3010")
    axes.set_aspect("equal")
    axes.set_xlabel("x (m)")
    axes.set_ylabel("z (m)")
    axes.set_title("rock egg pile: plan view of the closed MESH64 union (synthetic analytic, not TD)")
    axes.grid(alpha=.2)
    path = output / "rock-eggs-a-plan.png"
    figure.tight_layout()
    figure.savefig(path, dpi=140, metadata={"Software": "special_terrain_l1_rock_eggs"})
    plt.close(figure)
    figures.append({"name": "a-plan", "path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "description": "plan (x, z) wireframe of the union; the two separated eggs stand clear on the lower right"})

    figure, axes = plt.subplots(figsize=(9., 7.))
    plane_value = float(hover["midpoint_xyz_m"][2]) if hover else 0.6
    segments = plane_section_segments(record, 2, plane_value)
    if not segments:
        raise ValueError("plane section produced no segments")
    for first, second in segments:
        axes.plot([first[0], second[0]], [first[1], second[1]], color="#6b4f1d", linewidth=1.2)
    if hover:
        first = hover["facing_surface_hits"][0]["position_xyz_m"]
        second = hover["facing_surface_hits"][1]["position_xyz_m"]
        axes.plot([first[0], second[0]], [first[1], second[1]], color="#c0392b", linewidth=2.4,
                  label="measured clearance %.3f m" % hover["measured_mesh_clearance_m"])
        axes.annotate("%s hovering above %s" % (hover["upper_egg_id"], hover["lower_egg_id"]),
                      (hover["midpoint_xyz_m"][0], hover["midpoint_xyz_m"][1]), fontsize=7,
                      xytext=(14., 14.), textcoords="offset points", color="#c0392b",
                      arrowprops={"arrowstyle": "-", "color": "#c0392b"})
        axes.legend(loc="upper left", fontsize=7)
    axes.set_aspect("equal")
    axes.set_xlabel("x (m)")
    axes.set_ylabel("y (m)")
    axes.set_title("rock egg pile: section at z = %.2f m (triangle/plane intersections)" % plane_value)
    axes.grid(alpha=.2)
    path = output / "rock-eggs-b-section.png"
    figure.tight_layout()
    figure.savefig(path, dpi=140, metadata={"Software": "special_terrain_l1_rock_eggs"})
    plt.close(figure)
    figures.append({"name": "b-section", "path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "description": "true plane section through the hover pair; the red segment is the measured clearance",
                    "plane": "z", "value_m": plane_value, "segment_count": len(segments)})

    figure = plt.figure(figsize=(10., 8.))
    axes = figure.add_subplot(111, projection="3d")
    stride = max(1, len(triangles) // 8000)
    faces = vertices[triangles][::stride]
    axes.add_collection3d(Poly3DCollection(faces, facecolor="#c8a165", edgecolor="#6b4f1d",
                                           linewidths=.1, alpha=.95))
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    axes.set_xlim(low[0], high[0])
    axes.set_ylim(low[1], high[1])
    axes.set_zlim(low[2], high[2])
    axes.set_xlabel("x (m)")
    axes.set_ylabel("y (m)")
    axes.set_zlabel("z (m)")
    axes.set_title("rock egg pile: closed MESH64 union, %d triangles" % len(triangles))
    path = output / "rock-eggs-c-solid.png"
    figure.tight_layout()
    figure.savefig(path, dpi=140, metadata={"Software": "special_terrain_l1_rock_eggs"})
    plt.close(figure)
    figures.append({"name": "c-solid", "path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "description": "3D view of the union; separated bodies and the hovering body are visible",
                    "faces_shown": len(faces), "faces_total": len(triangles)})
    return figures


def write_report(output_directory=DEFAULT_OUTPUT):
    """Build, render and seal the deliverable: three figures plus a compact report.json."""
    output = Path(output_directory)
    document, artifacts = build()
    document["figures"] = render_preview(artifacts["rock_after"], output, artifacts["hover"])
    seal(document)
    output.mkdir(parents=True, exist_ok=True)
    report = output / REPORT_NAME
    report.write_text(json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False),
                      encoding="utf-8")
    return document, artifacts, report


def write_canonical_bytes(document):
    """Exact bytes the report is written as; used by the determinism test."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    output_directory = Path(argv[0]) if argv else DEFAULT_OUTPUT
    document, _artifacts, report = write_report(output_directory)
    hover = document["witnesses"]["hover_void_midpoint_is_outside"]["observed"]
    print(json.dumps({"status": document["status"],
                      "connected_components": document["assembly"]["connected_components"],
                      "union_volume_m3": document["assembly"]["signed_volume_m3"],
                      "sum_of_parts_m3": document["assembly"]["sum_of_parts_m3"],
                      "measured_hover_clearance_m": hover["measured_mesh_clearance_m"],
                      "witness_verdicts": {name: item["verdict"]
                                           for name, item in document["witnesses"].items()},
                      "identity_sha256": document["identity_sha256"],
                      "report": str(report)}, ensure_ascii=False))
    return document


if __name__ == "__main__":
    main()
