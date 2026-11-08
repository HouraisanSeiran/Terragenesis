"""General closed-solid Boolean with explicit volume, component and refusal accounting.

``hybrid_cave_geometry`` already implements the conduit-specific case: one sampled rock
body minus one conduit cutter, plus the reusable mesh primitives. This module generalises
*that algebra only* -- an arbitrary closed rock body minus an arbitrary closed cutter
set, or a union of closed bodies with no cutter at all -- and reuses the frozen module's
primitives unchanged (``mesh_record``, ``signed_volume``, ``manifold_from_record``,
``save_manifold``, ``guard``, ``seal``).

It deliberately does **not** edit ``terrain_pipeline/hybrid_cave_geometry.py``: that file
is code-pinned where every pin is consumed as evidence -- the ``code_sha256`` block of
``verification/natural-river-network/hybrid-cave-geometry-20261006-03/index.json``, the
``FROZEN_CODE`` manifests of ``tools/audit_hybrid_cave_geometry.py`` and
``tools/audit_hybrid_cave_geometry_v2.py``, and the live parent check in
``tools/prepare_underground_river_v1.py``. Adding the general algebra in a sibling module
keeps the passed independent audit of that package re-verifiable while the conduit path
and every saved byte stay identical.

Nothing here is a certification: every capability flag is written False.
"""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.hybrid_cave_geometry import (
    guard, manifold_from_record, mesh_record, save_manifold, seal, signed_volume)
from terrain_pipeline.hybrid_river_graph import identity

SCHEMA = "td-hybrid-rock-boolean-v1"
RESULT_SCHEMA = "td-hybrid-rock-boolean-result-v1"
ALGORITHM = "arbitrary-closed-rock-minus-closed-cutter-set-v1"
RELATION = ("generalises_the_excavation_step_of_td-hybrid-river-geometry-v1_"
            "without_replacing_recomputing_or_editing_it")
SOLID_SCHEMA = "td-hybrid-local-solid-mesh-v1"
MAX_COMPONENTS = 1024
FLAGS = ("independent_audit_passed", "hydraulic_ready", "natural_outlet_certified",
         "full_network_verified", "self_intersection_verified", "publishable")

# Independent policy identity. The conduit module's POLICY/POLICY_SHA256 are referenced by
# saved evidence and are neither reused nor touched here.
POLICY = {
    "version": "local-arbitrary-rock-boolean-v1",
    "rock": "caller_supplied_closed_solid_sampled_or_analytic_never_native_exact",
    "cutters": "caller_supplied_closed_solid_set_united_then_subtracted_actual_volume",
    "assembly": "caller_supplied_closed_solid_union_disconnected_components_allowed",
    "excavation": "Mesh64_local_origin_closed_rock_minus_closed_union_actual_volume",
    "water": "not_generated_solid_banks_distinct_from_free_water",
    "protection": "no_clamping_no_implicit_fill_no_hidden_truncation_refusal_only",
    "conduit_scope": "untouched_not_recomputed_and_not_reidentified_here",
    "certification": "candidate_only_every_capability_flag_written_false",
}
POLICY_SHA256 = identity(POLICY)
CONDUIT_POLICY_SHA256 = "10287323bb7fbb835d2e8de6c6e03720454b2c1538e606e09764c872ca67604b"


@dataclass(frozen=True)
class BooleanParameters:
    """Bounded explicit parameters; no default is a measurement or a certification."""

    solids_spacing_m: float = 1.
    component_limit: int = 64
    balance_relative_tolerance: float = 1e-10

    def __post_init__(self):
        if type(self.solids_spacing_m) is not float or not math.isfinite(self.solids_spacing_m) \
                or not .05 <= self.solids_spacing_m <= 8.:
            raise ValueError("bounded positive solid sampling spacing required")
        if type(self.component_limit) is not int or not 1 <= self.component_limit <= MAX_COMPONENTS:
            raise ValueError("bounded integer component limit required")
        if type(self.balance_relative_tolerance) is not float or not math.isfinite(self.balance_relative_tolerance) \
                or not 1e-15 <= self.balance_relative_tolerance <= 1e-6:
            raise ValueError("bounded relative balance tolerance required")


class _Library:
    """Lazy pinned manifold3d accessor; the module imports no Boolean engine at import time."""

    @staticmethod
    def get():
        import manifold3d as manifold
        return manifold


MANIFOLD = _Library


def _origin(origin):
    origin = np.asarray(origin, float)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("finite three-component local origin required")
    return origin


def _parameters(parameters):
    if not isinstance(parameters, BooleanParameters):
        raise ValueError("explicit BooleanParameters required")
    return parameters


def positive_int(value, label):
    if type(value) is not int or not 1 <= value <= MAX_COMPONENTS:
        raise ValueError("bounded integer " + label + " required")
    return value


def solid_from_record(record, label):
    """Validate one saved closed-solid record and return its pinned MESH64 solid.

    Every input is also volume-checked against the saved ``signed_volume_m3``: a record
    whose JSON volume disagrees with the reconstructed closed mesh is refused rather than
    quietly used as a Boolean operand.
    """
    if not isinstance(record, dict) or record.get("schema") != SOLID_SCHEMA \
            or record.get("sampled_not_native_exact") is not True:
        raise ValueError("saved closed solid mesh record required for " + label)
    if not isinstance(record.get("role"), str) or not record["role"]:
        raise ValueError("explicit solid role required for " + label)
    if len(record.get("vertices_local_xyz_m", [])) < 4 or len(record.get("triangles", [])) < 4:
        raise ValueError("degenerate closed solid record for " + label)
    solid = manifold_from_record(record)
    if "signed_volume_m3" not in record:
        raise ValueError("saved signed solid volume required for " + label)
    _volume_gate(record, solid, label)
    return solid


def census(solid):
    return len(solid.decompose())


def _status_gate(solid, label):
    library = _Library.get()
    if solid.status() != library.Error.NoError or solid.is_empty():
        raise ValueError("closed solid " + label + " failed or is empty")


def _volume_gate(record, solid, label):
    saved, actual = float(record["signed_volume_m3"]), float(solid.volume())
    if not math.isfinite(saved) or not math.isfinite(actual) or saved <= 0.:
        raise ValueError("nonpositive saved volume for " + label)
    if abs(saved - actual) > max(1e-7, actual * 1e-9):
        raise ValueError("saved mesh volume disagrees with MESH64 volume for " + label)


def _component_gate(count, minimum, maximum, label):
    if count < minimum:
        raise ValueError(label + " has fewer connected components than declared")
    if count > maximum:
        raise ValueError(label + " exceeds the explicit component limit")
    return count


def _pin(record):
    return {"role": record["role"], "identity_sha256": record["identity_sha256"],
            "signed_volume_m3": record["signed_volume_m3"]}


def _common(parameters, origin, operation):
    record = {"schema": RESULT_SCHEMA, "status": "candidate", "rejection_reasons": [],
              "algorithm": ALGORITHM, "relation": RELATION, "operation": operation,
              "policy": POLICY, "policy_identity_sha256": POLICY_SHA256,
              "parameters": asdict(parameters), "parameters_identity_sha256": identity(asdict(parameters)),
              "local_origin_xyz_m": origin.tolist(),
              "conduit_policy_identity_sha256": CONDUIT_POLICY_SHA256,
              "parent_algorithm": "td-hybrid-river-geometry-v1_conduit_step_untouched_not_recomputed",
              "sampled_not_native_exact": True, "fine15_replaced": False,
              "water_generated": False, "fill_rock_m3": 0.}
    for flag in FLAGS:
        record[flag] = False
    return record


def combine(records, origin, role, parameters, *, minimum_components=1):
    """Union caller-supplied closed solids into one closed record (gaps stay outside).

    ``minimum_components`` is the caller's own claim about the result (for example a rock
    egg pile must stay disconnected); it is refused rather than adjusted when unmet.
    """
    origin = _origin(origin)
    parameters = _parameters(parameters)
    positive_int(minimum_components, "minimum component count")
    if not isinstance(records, (list, tuple)) or not records:
        raise ValueError("at least one closed input solid required")
    if not isinstance(role, str) or not role:
        raise ValueError("explicit result role required")
    library = _Library.get()
    solids = [solid_from_record(record, "input " + str(ordinal)) for ordinal, record in enumerate(records)]
    for ordinal, solid in enumerate(solids):
        _status_gate(solid, "input " + str(ordinal))
    union = library.Manifold.batch_boolean(solids, library.OpType.Add)
    _status_gate(union, "assembled union")
    fence = _component_gate(census(union), minimum_components, parameters.component_limit, "assembled union")
    assembly = save_manifold(union, origin, role)
    _volume_gate(assembly, union, "assembled union")
    result = _common(parameters, origin, "closed_solid_union_no_cutter")
    result.update({
        "inputs": {"solids": [_pin(record) for record in records]},
        "census": {"input_solids": len(records), "assembled_components": fence,
                   "component_limit": parameters.component_limit, "minimum_components_declared": minimum_components},
        "material": {"assembled_volume_m3": union.volume(), "excavated_rock_m3": 0.,
                     "exported_excavated_rock_m3": 0., "signed_residual_m3": 0.},
        "mesh_pins": {role: {"identity_sha256": assembly["identity_sha256"],
                             "signed_volume_m3": assembly["signed_volume_m3"]}},
        "gates": {"each_input_closed_two_use_manifold": True, "each_input_saved_volume_matches_mesh": True,
                  "assembled_closed_two_use_manifold": True,
                  "mesh_volume_matches_manifold_volume": True, "component_census_within_limit": True,
                  "no_cutter_applied": True, "no_clamping_no_implicit_fill": True},
        "refusals": "open_or_degenerate_inputs_declared_component_shortfall_and_component_limit_excess_are_refused",
    })
    seal(result)
    guard()
    return result, {role: assembly}


def excavate(rock_record, cutter_records, parameters, origin, *, minimum_removed_components=1,
             minimum_rock_after_components=1):
    """Subtract an explicit closed cutter set from one closed rock body.

    Both the unified cutter set and the excavated void are saved as closed solid records,
    so tunnel/void volume is independently re-checkable. Disjoint cutters are allowed; the
    void may legitimately consist of several separated cavities.
    """
    origin = _origin(origin)
    parameters = _parameters(parameters)
    positive_int(minimum_removed_components, "minimum removed component count")
    positive_int(minimum_rock_after_components, "minimum remaining rock component count")
    if not isinstance(cutter_records, (list, tuple)) or not cutter_records:
        raise ValueError("explicit closed cutter set required; use combine for a cutter-free union")
    library = _Library.get()
    rock = solid_from_record(rock_record, "rock")
    _status_gate(rock, "rock")
    cutters = [solid_from_record(record, "cutter " + str(ordinal)) for ordinal, record in enumerate(cutter_records)]
    for ordinal, cutter in enumerate(cutters):
        _status_gate(cutter, "cutter " + str(ordinal))
    union = library.Manifold.batch_boolean(cutters, library.OpType.Add)
    _status_gate(union, "unified cutter set")
    cutter_census = _component_gate(census(union), 1, parameters.component_limit, "unified cutter set")
    after = rock - union
    removed = rock ^ union
    _status_gate(after, "remaining rock")
    _status_gate(removed, "excavated void")
    if after.volume() <= 0. or removed.volume() <= 0.:
        raise ValueError("excavation refused: no positive remaining rock and excavated void volume")
    residual = rock.volume() - after.volume() - removed.volume()
    budget = max(1e-7, rock.volume() * parameters.balance_relative_tolerance)
    if abs(residual) > budget:
        raise ValueError("actual closed solid material balance failed")
    floor = _component_gate(census(after), minimum_rock_after_components, parameters.component_limit, "remaining rock")
    void = _component_gate(census(removed), minimum_removed_components, parameters.component_limit, "excavated void")
    rock_after = save_manifold(after, origin, "rock_after")
    removed_record = save_manifold(removed, origin, "removed")
    union_record = save_manifold(union, origin, "cutter_union")
    for record, solid, label in ((rock_after, after, "remaining rock"), (removed_record, removed, "excavated void"),
                                 (union_record, union, "unified cutter set")):
        _volume_gate(record, solid, label)
    result = _common(parameters, origin, "rock_minus_closed_cutter_union")
    result.update({
        "inputs": {"rock": _pin(rock_record), "cutters": [_pin(record) for record in cutter_records]},
        "census": {"rock_before_components": census(rock), "cutter_union_components": cutter_census,
                   "rock_after_components": floor, "removed_components": void,
                   "cutter_count": len(cutters), "component_limit": parameters.component_limit,
                   "minimum_removed_components_declared": minimum_removed_components,
                   "minimum_rock_after_components_declared": minimum_rock_after_components},
        "material": {"rock_before_m3": rock.volume(), "rock_after_m3": after.volume(),
                     "excavated_rock_m3": removed.volume(), "exported_excavated_rock_m3": removed.volume(),
                     "fill_rock_m3": 0., "signed_residual_m3": residual, "balance_budget_m3": budget},
        "mesh_pins": {name: {"identity_sha256": record["identity_sha256"],
                             "signed_volume_m3": record["signed_volume_m3"]}
                      for name, record in (("rock_after", rock_after), ("removed", removed_record),
                                           ("cutter_union", union_record))},
        "gates": {"input_closed_two_use_manifold": True, "input_saved_volume_matches_mesh": True,
                  "unified_cutter_closed_two_use_manifold": True,
                  "remaining_and_void_closed_two_use_manifold": True, "mesh_volume_matches_manifold_volume": True,
                  "actual_volume_balance": True, "positive_remaining_and_void_volume": True,
                  "component_census_within_limit": True, "no_clamping_no_implicit_fill": True,
                  "no_silent_truncation": True},
        "refusals": "open_or_degenerate_inputs_disjoint_or_empty_cutters_consumed_rock_and_"
                     "declared_component_shortfall_are_refused",
    })
    seal(result)
    guard()
    return result, {"rock_after": rock_after, "removed": removed_record, "cutter_union": union_record}


def octagon_ring(centre_xz, radius_x_m, radius_z_m, segments):
    """Deterministic regular ring for prisms/frusta; counter-clockwise in the (x, z) plane."""
    centre_xz = np.asarray(centre_xz, float)
    if centre_xz.shape != (2,) or not np.isfinite(centre_xz).all():
        raise ValueError("finite ring centre required")
    if type(segments) is not int or not 3 <= segments <= 4096:
        raise ValueError("bounded integer ring segment count required")
    for value in (radius_x_m, radius_z_m):
        if type(value) is not float or not math.isfinite(value) or value <= 0.:
            raise ValueError("bounded positive ring radii required")
    angles = np.arange(segments) * (2. * math.pi / segments)
    return centre_xz + np.column_stack((radius_x_m * np.cos(angles), radius_z_m * np.sin(angles)))


def _ring(polygon_xz, label):
    ring = np.asarray(polygon_xz, float)
    if ring.ndim != 2 or ring.shape[1] != 2 or len(ring) < 3 or not np.isfinite(ring).all():
        raise ValueError("finite closed polygon with at least three points required for " + label)
    if len(np.unique(ring, axis=0)) != len(ring):
        raise ValueError("repeated polygon point refused for " + label)
    area = float(np.sum(ring[:, 0] * np.roll(ring[:, 1], -1) - np.roll(ring[:, 0], -1) * ring[:, 1]) / 2.)
    if abs(area) < 1e-12:
        raise ValueError("degenerate polygon area refused for " + label)
    return ring if area > 0. else ring[::-1]


def polygon_prism_record(polygon_xz, bottom_y_m, top_y_m, origin, role, *, maximum_vertices=200000):
    """Closed vertical prism over an explicit simple polygon (shaft walls, terraces, tunnels).

    The ring is normalised counter-clockwise and the caps are triangulated by the pinned
    MESH64 triangulator, so the closed two-use manifold gate is decided by geometry rather
    than by hand-chosen winding.
    """
    origin = _origin(origin)
    ring = _ring(polygon_xz, "prism")
    bottom, top = float(bottom_y_m), float(top_y_m)
    if not (math.isfinite(bottom) and math.isfinite(top)) or top - bottom <= 0.:
        raise ValueError("strict positive prism height required")
    library = _Library.get()
    count = len(ring)
    if 2 * count > maximum_vertices:
        raise ValueError("prism vertex budget exceeded before triangulation")
    vertices = [[point[0] - origin[0], bottom - origin[1], point[1] - origin[2]] for point in ring]
    vertices += [[point[0] - origin[0], top - origin[1], point[1] - origin[2]] for point in ring]
    triangles = []
    for ordinal in range(count):
        following = (ordinal + 1) % count
        triangles.extend(([ordinal, following, count + following], [ordinal, count + following, count + ordinal]))
    for triangle in library.triangulate([ring], allow_convex=False):
        first, second, third = (int(index) for index in triangle)
        triangles.append([count + first, count + second, count + third])
        triangles.append([third, second, first])
    if len(vertices) > maximum_vertices:
        raise ValueError("prism vertex budget exceeded")
    return mesh_record(vertices, triangles, origin, role)


def frustum_record(bottom_centre_xz, top_centre_xz, bottom_y_m, top_y_m, radius_bottom_m, radius_top_m,
                   origin, role, *, segments=64, maximum_vertices=200000):
    """Closed circular frustum between two explicit centres (funnel walls, flared bases)."""
    origin = _origin(origin)
    bottom_ring = _ring(octagon_ring(bottom_centre_xz, radius_bottom_m, radius_bottom_m, segments), "frustum base")
    top_ring = _ring(octagon_ring(top_centre_xz, radius_top_m, radius_top_m, segments), "frustum top")
    bottom, top = float(bottom_y_m), float(top_y_m)
    if not (math.isfinite(bottom) and math.isfinite(top)) or top - bottom <= 0.:
        raise ValueError("strict positive frustum height required")
    count = segments
    if 2 * count + 2 > maximum_vertices:
        raise ValueError("frustum vertex budget exceeded")
    vertices = [[point[0] - origin[0], bottom - origin[1], point[1] - origin[2]] for point in bottom_ring]
    vertices += [[point[0] - origin[0], top - origin[1], point[1] - origin[2]] for point in top_ring]
    base_centre = len(vertices)
    vertices.append([bottom_centre_xz[0] - origin[0], bottom - origin[1], bottom_centre_xz[1] - origin[2]])
    top_centre = len(vertices)
    vertices.append([top_centre_xz[0] - origin[0], top - origin[1], top_centre_xz[1] - origin[2]])
    triangles = []
    for ordinal in range(count):
        following = (ordinal + 1) % count
        triangles.extend(([ordinal, following, count + following], [ordinal, count + following, count + ordinal]))
        triangles.append([top_centre, count + ordinal, count + following])
        triangles.append([base_centre, following, ordinal])
    return mesh_record(vertices, triangles, origin, role)


def sphere_record(centre_xyz_m, radius_m, origin, role, *, circular_segments=48):
    """Closed geodesic sphere (stacked egg bodies); the pinned engine owns the mesh."""
    origin = _origin(origin)
    centre = np.asarray(centre_xyz_m, float)
    if centre.shape != (3,) or not np.isfinite(centre).all():
        raise ValueError("finite sphere centre required")
    if type(radius_m) is not float or not math.isfinite(radius_m) or radius_m <= 0.:
        raise ValueError("bounded positive sphere radius required")
    if type(circular_segments) is not int or not 4 <= circular_segments <= 512:
        raise ValueError("bounded integer sphere segment count required")
    library = _Library.get()
    solid = library.Manifold.sphere(radius_m, circular_segments).translate(tuple(centre - origin))
    _status_gate(solid, "sphere")
    return save_manifold(solid, origin, role)
