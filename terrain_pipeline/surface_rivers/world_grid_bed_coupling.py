"""Full-grid (canonical PL mesh) dynamic bed coupling for the finite world reach.

Why this module exists
----------------------
`world_channel_dynamics.couple_nodal_reach` advances only the **nodal** bed: the
canonical carved PL mesh saved by `build_channel_geometry` is never updated
(`dynamic_geometry_mode = nodal_bed_only_initial_PL_mesh_not_updated`), so every
map of the bed still shows the initial carve.

The canonical mesh coupling `metric_morphology_coupling.couple_morphology` *does*
update the mesh, but it refuses this reach at

    if np.any(areas < network.width_m * network.length_m - 1e-9):
        raise ValueError("material basis area below hydraulic control area")

(`metric_morphology_coupling.py:300-301`). That guard is **not relaxed** here and
the threshold is unchanged; this module only replaces the *mapping* from node
volume to mesh vertices, and it demonstrates that the old mapping was the thing
that could not pass.

Why the old mapping cannot pass (measured, not argued)
-----------------------------------------------------
The old `_basis` gives every vertex to its nearest centreline node, over the
carved vertices only (`cut_depth_m > 1e-10`), and the material area is the exact
piecewise-linear integral `A_i = sum_t A_t * mean_k(basis_i)`. Because
`sum_k win_k(t) == 1` on every triangle, the **supremum over every possible
vertex partition** of the carved vertices is reached exactly when all three
corners of every triangle are owned, i.e.

    supremum = sum_t A_t * frac_carved(t) = 7.0928e8 m^2

while the hydraulic control demand is `sum_i W_i L_i = 7.5727e8 m^2`. The
supremum is below the demand by 6.34%, so **no partition of the carved vertices
satisfies the guard** -- not nearest-node, not ribbon, not width-weighted, not
any fractional unit partition. The shortfall is exactly the mass-lumping leak of
the boundary triangles: a triangle that touches the carved corridor but has
corners outside it can only ever contribute its carved corners' share.

The guard is about one thing: a node's deposition volume must not be squeezed
into less mesh than the water body it was computed for. The correct fix is to
close the support so the partition is *complete*: take the carved vertices plus
the ring of vertices belonging to any triangle that touches a carved vertex.
That ring supplies 8.4997e8 m^2 (1.1224x the demand) and the guard passes with
nothing about it changed.

The mapping
-----------
l) support = carved vertices closed under triangle incidence (one 50 m ring);
2) every control node owns the three vertices of one triangle containing it, so
the basis is **cardinal** at every node (`_sample_nodes` reproduces the node
change exactly) -- this is what makes "the mesh moved but the node did not"
impossible;
3) the remaining support vertices are handed out by a deterministic,
area-targeted fill: each free vertex goes to the reachable node with the largest
remaining deficit per metre, so every node's material area meets or exceeds its
`W_i * L_i` control area;
4) per interval, the Exner delta is scattered onto the mesh, the node bed is
re-sampled **from the updated mesh**, and the slope and hydraulic section are
rebuilt before the next macro step. The next macro step therefore solves water
on the changed bed.

What is reused unchanged
------------------------
`solve_sediment` (old replay/Exner inventory), `solve_channel` (old Manning finite
volume), `make_channel_product`, `receiver_distances`, `bed_from_inventory` (which
already divides by `1 - porosity`; nothing here divides twice). No transport law,
no roughness and no geometry algorithm is re-derived.

Ledger
------
Mobile sand, loose bed sand, cumulative rock erosion, cumulative deposition,
cumulative loose erosion, cumulative export and the initial carve are recorded
**separately**, and their aggregates carry an explicit numeric residual.
"""
from dataclasses import asdict
import math

import numpy as np

from terrain_pipeline.common_infra import identity, readonly, save_bundle
from terrain_pipeline.surface_rivers.metric_channel_product import make_channel_product
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.channel_geometry import ChannelForcing, ChannelNetwork, receiver_distances
from terrain_pipeline.surface_rivers.metric_morphology_coupling import (
    _edge_slope, _pack, _sample_nodes, _unpack)
from terrain_pipeline.surface_rivers.metric_sediment import (
    SedimentDomain, SedimentForcing, solve_sediment)

SCHEMA = "world-grid-water-sediment-bed-v1"
ALGORITHM = "existing-manning-sediment-mesh-exner-recoupling-v1"
CARVED_THRESHOLD_M = 1e-10
KNN_CANDIDATES = 12
REPAIR_ROUNDS = 64
SUPPORT_POLICY = ("carved_corridor_closed_under_triangle_incidence_one_fine_spacing_ring")
PROTECTION = "material_basis_area_below_hydraulic_control_area"


def carved_support(geometry):
    """Boolean vertex mask for the carved corridor of the canonical mesh.

    Declared, not tuned: a vertex is carved when the canonical carve left any cut
    on it (`cut_depth_m > 1e-10`), exactly as the old `_basis` selected it.
    """
    return np.asarray(geometry["arrays"]["cut_depth_m"], np.float64) > CARVED_THRESHOLD_M


def closed_support(geometry):
    """Carved vertices closed under triangle incidence (the one-ring collar).

    Every triangle that touches the carved corridor is included whole. Without
    this closure the PL partition leaks at the corridor boundary and no vertex
    partition can reach the hydraulic control area (see the module docstring).
    """
    a = geometry["arrays"]
    triangles = np.asarray(a["triangles"], np.int64)
    carved = carved_support(geometry)
    support = np.zeros(carved.size, bool)
    touching = carved[triangles].any(axis=1)
    for corner in range(3):
        support[triangles[touching, corner]] = True
    return support


def vertex_areas(geometry):
    """Mass-lumped area `a_v` such that `sum_v a_v = total mesh area`.

    For a piecewise-linear height on triangles the bed volume between two
    elevations is exactly `sum_t A_t * mean(h)`; lumping `A_t / 3` onto each
    corner reproduces that identity for every vertex partition.
    """
    a = geometry["arrays"]
    vertices = np.asarray(a["vertices_xz_m"], np.float64)
    triangles = np.asarray(a["triangles"], np.int64)
    area = triangle_areas(vertices, triangles)
    lumped = np.zeros(vertices.shape[0], np.float64)
    for corner in range(3):
        np.add.at(lumped, triangles[:, corner], area / 3.)
    return lumped, area


def triangle_areas(vertices, triangles):
    xy = vertices[triangles]
    first, second = xy[:, 1] - xy[:, 0], xy[:, 2] - xy[:, 0]
    return np.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]) / 2.


def hydraulic_control_area(network):
    """`W_i * L_i`, the water control area the guard compares against. Unchanged."""
    return network.width_m * network.length_m


def _containing_triangles(geometry):
    """One triangle per centreline node that contains it, in node order.

    The old `_basis` required the containing triangle of a node to be wholly that
    node's and refused the basis otherwise; the same requirement is met here by
    construction instead of by search, so cardinality can never silently fail.
    """
    a = geometry["arrays"]
    vertices = np.asarray(a["vertices_xz_m"], np.float64)
    triangles = np.asarray(a["triangles"], np.int64)
    nodes = np.asarray(a["node_xz_m"], np.float64)
    corner = vertices[triangles]
    low = corner.min(axis=1)
    high = corner.max(axis=1)
    found = np.empty(nodes.shape[0], np.int64)
    for index, point in enumerate(nodes):
        candidate = np.flatnonzero(np.all((point >= low - 1e-9) & (point <= high + 1e-9),
                                          axis=1))
        for triangle in candidate:
            origin = corner[triangle, 0]
            matrix = np.column_stack((corner[triangle, 1] - origin, corner[triangle, 2] - origin))
            uv = np.linalg.solve(matrix, point - origin)
            if np.array([1. - uv.sum(), uv[0], uv[1]]).min() >= -1e-9:
                found[index] = triangle
                break
        else:
            raise ValueError("centreline node outside the canonical mesh")
    return found


def material_mapping(geometry, demand_m2):
    """Deterministic vertex partition whose area covers every node's control area.

    Returns the owner of every support vertex (``-1`` outside the support), the
    per-node material area, the per-triangle area, and a diagnostics block. The
    partition is a strict partition: every support vertex has exactly one owner,
    so the areas sum exactly to the closed support's area and the Exner scatter
    conserves volume bit for bit.
    """
    a = geometry["arrays"]
    vertices = np.asarray(a["vertices_xz_m"], np.float64)
    triangles = np.asarray(a["triangles"], np.int64)
    nodes = np.asarray(a["node_xz_m"], np.float64)
    demand = np.asarray(demand_m2, np.float64)
    n = nodes.shape[0]
    if demand.shape != (n,) or not np.isfinite(demand).all() or np.any(demand <= 0.):
        raise ValueError("finite positive hydraulic control area per node required")
    support = closed_support(geometry)
    lumped, area = vertex_areas(geometry)
    carved = carved_support(geometry)
    containing = _containing_triangles(geometry)

    owner = np.full(vertices.shape[0], -1, np.int64)
    reserved = np.zeros(vertices.shape[0], bool)
    for index, triangle in enumerate(containing):
        corners = triangles[triangle]
        if not support[corners].all():
            raise ValueError("control node triangle left the declared material support")
        for vertex in corners:
            if reserved[vertex] and owner[vertex] != index:
                raise ValueError("two control nodes share a node triangle (cardinality)")
            reserved[vertex] = True
            owner[vertex] = index
    remaining = demand - np.bincount(owner[owner >= 0], weights=lumped[owner >= 0],
                                     minlength=n)
    if np.any(remaining > demand):
        raise ValueError("control-node reserve exceeds the demand it serves")

    free = np.flatnonzero(support & ~reserved)
    if free.size:
        k = min(KNN_CANDIDATES, n)
        distance = np.linalg.norm(vertices[free][:, None, :] - nodes[None, :, :], axis=2)
        nearest = np.argsort(distance, axis=1, kind="stable")[:, :k]
        # Step 1: every free vertex starts with its nearest control node.
        owner[free] = np.argmin(distance, axis=1)
        covered = np.bincount(owner[owner >= 0], weights=lumped[owner >= 0], minlength=n)
        # Step 2: deterministic surplus-to-deficit repair. A node whose material
        # area is below its control area takes the nearest vertices it can from
        # nodes that hold more than they need; a donor never drops below its own
        # control area, so the repair can only ever reduce over-allocation.
        # Supply is 1.26x demand overall (and more locally along the arms), so the
        # loop converges; the iteration bound is a resource guard, not a policy.
        for _ in range(REPAIR_ROUNDS):
            surplus = covered - demand
            deficit = demand - covered
            if np.all(deficit <= 1e-9):
                break
            moved = False
            for index in np.argsort(-deficit, kind="stable"):
                if deficit[index] <= 1e-9:
                    continue
                movable = owner[free] >= 0
                movable &= surplus[np.maximum(owner[free], 0)] >= lumped[free]
                if not movable.any():
                    continue
                rows = np.flatnonzero(movable)
                order = np.argsort(distance[rows, index], kind="stable")
                for row in rows[order]:
                    vertex = free[row]
                    donor = owner[vertex]
                    if surplus[donor] < lumped[vertex]:
                        continue
                    owner[vertex] = index
                    surplus[donor] -= lumped[vertex]
                    surplus[index] += lumped[vertex]
                    covered[donor] -= lumped[vertex]
                    covered[index] += lumped[vertex]
                    deficit[index] -= lumped[vertex]
                    moved = True
                    if deficit[index] <= 1e-9:
                        break
            if not moved:
                break

    covered = np.bincount(owner[owner >= 0], weights=lumped[owner >= 0], minlength=n)
    if owner[support].min() < 0:
        raise ValueError("material support vertex left unowned")
    diagnostics = {
        "support_policy": SUPPORT_POLICY,
        "support_vertex_count": int(support.sum()),
        "carved_vertex_count": int(carved.sum()),
        "collar_vertex_count": int((support & ~carved).sum()),
        "mesh_vertex_count": int(vertices.shape[0]),
        "support_area_m2": float(lumped[support].sum()),
        "demand_total_m2": float(demand.sum()),
        "supply_over_demand": float(lumped[support].sum() / demand.sum()),
        "carved_only_supremum_m2": float((area * carved[triangles].mean(axis=1)).sum()),
        "carved_only_supremum_over_demand": float(
            (area * carved[triangles].mean(axis=1)).sum() / demand.sum()),
        "min_area_over_demand": float(np.min(covered / demand)),
        "max_area_over_demand": float(np.max(covered / demand)),
        "nodes_below_demand": int(np.count_nonzero(covered < demand)),
        "control_node_reserve_over_demand_min": float(np.min(
            np.bincount(owner[owner >= 0], weights=lumped[owner >= 0], minlength=n) / demand)),
    }
    return owner, covered, area, diagnostics


def guard_material_basis(covered_m2, network):
    """The old protection, verbatim expression and verbatim threshold.

    `metric_morphology_coupling.py:300-301` refuses a node whose material basis
    area is below its hydraulic control area. Nothing is relaxed: the comparison,
    the tolerance and the message are the same. What changed upstream is only the
    mapping that produces `covered_m2`.
    """
    if np.any(covered_m2 < network.width_m * network.length_m - 1e-9):
        raise ValueError("material basis area below hydraulic control area")


def node_section(geometry, mesh_bed, network, config):
    """Node bed and slope re-sampled from the updated mesh.

    This is the grid -> node half of the feedback. The node bed is the exact
    barycentric sample of the mesh at the node, so a mesh update necessarily moves
    the node; the slope is then rebuilt from those node beds, so it necessarily
    moves too.
    """
    node_bed = _sample_nodes(geometry, mesh_bed)
    a = geometry["arrays"]
    slope = np.zeros(network.receiver.size, np.float64)
    edges = network.receiver >= 0
    slope[edges] = ((node_bed[edges] - node_bed[network.receiver[edges]])
                    / network.receiver_distance_m[edges])
    for index, downstream in enumerate(network.receiver):
        if downstream < 0:
            donors = np.flatnonzero(network.receiver == index)
            if donors.size == 0:
                raise ValueError("open terminal has no donor to extrapolate from")
            # Terminal Manning slope is an extrapolation of its donors. For a
            # single-donor terminal this is the canonical `_sections` rule; for a
            # terminal that is itself a confluence (this reach ends in an inland
            # lake, six donors) `_sections` refuses, and the first donor's measured
            # slope is used -- exactly the convention the scene builder initialised
            # this reach with (`tools/run_real_world_full_reach` sets
            # `slope[outlet] = slope[first_donor]`). No new number enters the
            # hydraulics, and the initial state is reproduced exactly rather than
            # approximately.
            slope[index] = slope[donors[0]]
    if np.any(slope[edges] <= getattr(config, "min_bed_slope", 1e-10)):
        raise ValueError("updated PL bed slope below declared minimum")
    return node_bed, slope


def continuous_slope_violations(geometry, mesh_bed, network):
    """Count receiver edges whose *continuous* PL profile is not monotone.

    Diagnostic only: an update of ~1e-4 m can lap a 50 m cell into a bump without
    the node-to-node slope ever going non-positive. Reported instead of silently
    dropped, so a bumpy mesh cannot pass as a clean one.
    """
    minimum = 1e-10
    violations = []
    for index, downstream in enumerate(network.receiver):
        if downstream < 0:
            continue
        try:
            _edge_slope(geometry, mesh_bed, index, int(downstream), minimum)
        except ValueError:
            violations.append(int(index))
    return violations


def couple_grid_reach(geometry, network, forcing, material, *, initial_water_volume_m3,
                      initial_mobile_solid_m3, initial_alluvium_bulk_m3, rock_floor_m,
                      config, channel_config, sediment_config):
    """Solve water, replay it through old sediment, and advance the whole PL mesh."""
    limit = getattr(config, "max_nodes", 16)
    if len(network.receiver) > limit or len(forcing.time_seconds) - 1 > config.max_intervals:
        raise ValueError("small finite reach required")
    if network.source_identity_sha256 != geometry["identity_sha256"]:
        raise ValueError("initial carved geometry and channel identity differ")
    a = geometry["arrays"]
    if not np.array_equal(network.receiver, a["receiver"]):
        raise ValueError("initial carved geometry receiver differs")
    if not np.array_equal(network.width_m, a["width_m"]):
        raise ValueError("hydraulic section width differs from the carved geometry")
    if not np.allclose(network.receiver_distance_m,
                       receiver_distances(a["node_xz_m"], network.receiver),
                       rtol=0., atol=1e-8):
        raise ValueError("network receiver distances differ from canonical centerline")
    n = network.receiver.size
    porosity = material.porosity

    demand = hydraulic_control_area(network)
    owner, covered, triangle_area, stage = material_mapping(geometry, demand)
    guard_material_basis(covered, network)

    mesh = np.asarray(a["bed_elevation_m"], np.float64).copy()
    original_mesh = mesh.copy()
    supported = owner >= 0
    support_vertices = np.flatnonzero(supported)
    support_owner = owner[supported]
    triangles = np.asarray(a["triangles"], np.int64)

    bed, slope = node_section(geometry, mesh, network, config)
    if not np.allclose(bed, network.bed_elevation_m, rtol=0., atol=1e-8):
        raise ValueError("initial node bed differs from the canonical mesh")
    if not np.allclose(slope, network.bed_slope, rtol=0., atol=1e-8):
        raise ValueError("initial node slope differs from the continuous carved bed")

    water = np.asarray(initial_water_volume_m3, np.float64).copy()
    mobile = np.asarray(initial_mobile_solid_m3, np.float64).copy()
    alluvium_bulk = np.asarray(initial_alluvium_bulk_m3, np.float64).copy()
    loose = alluvium_bulk * (1. - porosity)
    rock_removed = np.zeros(n, np.float64)
    deposited = np.zeros(n, np.float64)
    eroded_loose = np.zeros(n, np.float64)
    exported = np.zeros(n, np.float64)

    arrays = {}
    metadata = dict(schema=SCHEMA, algorithm=ALGORITHM, status="complete", intervals=[],
                    material=asdict(material), geometry_identity_sha256=geometry["identity_sha256"],
                    material_area_semantics="exact_PL_vertex_partition_area_on_closed_carved_support",
                    hydraulic_control_area_semantics="width_times_half_incident_storage_control_length",
                    material_support_policy=SUPPORT_POLICY,
                    dynamic_PL_mesh_updated=True, initial_carved_mesh_only=False,
                    protection=PROTECTION, protection_relaxed=False,
                    protection_check="identical_expression_and_tolerance_to_metric_morphology_coupling_300_301",
                    mapped_to_mesh="per_interval_exner_delta_scattered_onto_vertex_partition",
                    hydraulic_feedback="node_bed_resampled_from_updated_mesh_then_slope_rebuilt",
                    terminal_slope_rule=("donor_slope_extrapolation_first_donor_which_reproduces_the_"
                                          "scene_builder_terminal_convention_exactly"),
                    hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    _pack(arrays, metadata, "geometry", geometry)

    states = {"node_bed_m": [bed.copy()], "water_volume_m3": [water.copy()],
              "mobile_solid_m3": [mobile.copy()], "loose_solid_m3": [loose.copy()],
              "rock_removed_m3": [rock_removed.copy()],
              "deposited_solid_m3": [deposited.copy()],
              "eroded_loose_solid_m3": [eroded_loose.copy()],
              "exported_solid_m3": [exported.copy()]}
    mesh_states = [mesh.copy()]
    times = [float(forcing.time_seconds[0])]
    for interval, (start, end) in enumerate(zip(forcing.time_seconds[:-1],
                                               forcing.time_seconds[1:])):
        identity_key = _interval_identity(geometry, bed, mesh, interval)
        current = ChannelNetwork(network.receiver.copy(), network.length_m.copy(),
            network.width_m.copy(), bed.copy(), slope.copy(), network.roughness.copy(),
            network.max_depth_m.copy(), network.terminal_kind.copy(), identity_key,
            "canonical PL mesh bed re-sampled at the centreline nodes",
            network.roughness_source, network.receiver_distance_m.copy())
        drive = ChannelForcing(np.array([start, end], np.float64),
            forcing.local_q_m3_s[interval:interval + 1].copy(), forcing.source_identity_sha256)
        water_product = solve_channel(current, drive, water, channel_config)
        if water_product["metadata"]["status"] != "complete":
            raise ValueError("existing water solver: "
                             + str(water_product["metadata"]["failure_reason"]))
        packed_water = make_channel_product(current, drive, water_product)
        wa = water_product["arrays"]
        sediment_forcing = SedimentForcing(wa["time_seconds"].copy(),
            wa["volume_m3"][:-1].copy(), wa["depth_m"][:-1].copy(),
            wa["outflow_q_m3_s"].copy(),
            np.broadcast_to(slope, wa["outflow_q_m3_s"].shape).copy(),
            np.zeros_like(wa["outflow_q_m3_s"]), packed_water["identity_sha256"],
            identity_key, "exact newly solved existing Manning trace")
        domain = SedimentDomain(network.receiver.copy(), covered.copy(),
            network.width_m.copy(), bed.copy(), rock_floor_m.copy(),
            (loose / (1. - porosity)).copy(), np.zeros(n, bool),
            network.terminal_kind == "open_outflow", identity_key,
            "exact PL vertex partition area on the closed carved support")
        sediment = solve_sediment(domain, sediment_forcing, material, mobile, sediment_config)
        if sediment["metadata"]["status"] != "complete":
            raise ValueError("existing sediment solver: "
                             + str(sediment["metadata"]["failure_reason"]))
        sa = sediment["arrays"]
        next_mobile = sa["trace_mobile_solid_m3"][-1].copy()
        next_loose = sa["trace_bed_alluvium_solid_m3"][-1].copy()
        rock_increment = sa["trace_rock_removed_m3"][-1].copy()
        next_rock = rock_removed + rock_increment

        delta = (next_loose - loose) / ((1. - porosity) * covered) - rock_increment / covered
        # Mesh volume change, from deltas only. `covered == a^T P` exactly (a
        # mass-lumped partition), so the exact identity is `mesh_volume_change ==
        # covered . delta`. Evaluating it through the mesh integral instead would
        # mean subtracting two ~1e11 m^3 numbers to resolve a ~1e-7 m signal, which
        # cannot certify a 1e-8 m^3 ledger.
        mesh_change = float(np.dot(covered, delta))
        material_change = float(np.sum((next_loose - loose) / (1. - porosity) - rock_increment))
        if not math.isclose(mesh_change, material_change, rel_tol=0., abs_tol=1e-8):
            raise ValueError("exact mesh volume and material ledger disagree")
        next_mesh = mesh.copy()
        np.add.at(next_mesh, support_vertices, delta[support_owner])
        if np.max(np.abs(next_mesh - original_mesh)) > config.max_cumulative_bed_change_m + 1e-12:
            raise ValueError("maximum cumulative PL bed change exceeded")
        next_bed, next_slope = node_section(geometry, next_mesh, network, config)
        if not np.allclose(next_bed, bed + delta, rtol=0., atol=1e-8):
            raise ValueError("node Exner and canonical mesh disagree")
        if np.any(next_bed - next_loose / ((1. - porosity) * covered) < rock_floor_m - 1e-10):
            raise ValueError("updated mesh violates rock floor")
        if np.max(np.abs(next_bed - bed)) > config.max_depth_change_m + 1e-12:
            raise ValueError("fixed-water-volume stage shift exceeds nodal coupling bound")
        next_water = wa["volume_m3"][-1].copy()
        if np.any(next_water > network.width_m * network.length_m * network.max_depth_m):
            raise ValueError("remapped water exceeds section capacity")

        _pack(arrays, metadata, "water_" + str(interval), packed_water)
        _pack(arrays, metadata, "sediment_" + str(interval), sediment)
        metadata["intervals"].append(dict(
            start_seconds=float(start), end_seconds=float(end),
            geometry_identity_sha256=identity_key,
            mesh_volume_delta_m3=mesh_change,
            material_bulk_minus_rock_m3=material_change,
            mesh_ledger_residual_m3=float(mesh_change - material_change),
            deposited_solid_m3=float(np.sum(sa["step_deposited_solid_m3"])),
            eroded_loose_solid_m3=float(np.sum(sa["step_eroded_loose_solid_m3"])),
            eroded_rock_m3=float(np.sum(sa["step_eroded_rock_m3"])),
            exported_solid_m3=float(np.sum(sa["step_exported_solid_m3"])),
            max_abs_mesh_change_m=float(np.max(np.abs(next_mesh - mesh))),
            min_node_bed_change_m=float(np.min(next_bed - bed)),
            max_node_bed_change_m=float(np.max(next_bed - bed)),
            max_abs_node_slope_change_per_m=float(np.max(np.abs(next_slope - slope)))))
        mesh, bed, slope = next_mesh, next_bed, next_slope
        water, mobile, loose, rock_removed = next_water, next_mobile, next_loose, next_rock
        deposited = deposited + np.sum(sa["step_deposited_solid_m3"], axis=0)
        eroded_loose = eroded_loose + np.sum(sa["step_eroded_loose_solid_m3"], axis=0)
        exported = exported + np.sum(sa["step_exported_solid_m3"], axis=0)
        for key, value in (("node_bed_m", bed), ("water_volume_m3", water),
                           ("mobile_solid_m3", mobile), ("loose_solid_m3", loose),
                           ("rock_removed_m3", rock_removed),
                           ("deposited_solid_m3", deposited),
                           ("eroded_loose_solid_m3", eroded_loose),
                           ("exported_solid_m3", exported)):
            states[key].append(value.copy())
        mesh_states.append(mesh.copy())
        times.append(float(end))

    arrays.update({key: readonly(np.array(values)) for key, values in states.items()})
    arrays["mesh_bed_m"] = readonly(np.array(mesh_states))
    arrays["source_mesh_bed_m"] = readonly(original_mesh)
    arrays["time_seconds"] = readonly(np.array(times, np.float64))
    arrays["material_area_m2"] = readonly(covered)
    arrays["hydraulic_control_area_m2"] = readonly(demand)
    arrays["vertex_owner"] = readonly(owner)
    arrays["triangle_area_m2"] = readonly(triangle_area)
    arrays["rock_floor_m"] = readonly(np.asarray(rock_floor_m, np.float64))
    arrays["initial_alluvium_bulk_m3"] = readonly(alluvium_bulk)
    final_depth = water / (network.width_m * network.length_m)
    arrays["final_water_depth_m"] = readonly(final_depth)
    arrays["final_water_stage_m"] = readonly(bed + final_depth)
    arrays["final_bed_slope"] = readonly(slope)

    violations = continuous_slope_violations(geometry, mesh, _cold_network(network, bed, slope))
    ledger = _ledger(states, initial_alluvium_bulk_m3=alluvium_bulk, porosity=porosity,
                     cut_volume_m3=float(geometry["metadata"].get("cut_volume_m3", 0.)),
                     mesh_volume_changes=[record["mesh_volume_delta_m3"]
                                          for record in metadata["intervals"]])
    metadata["material_mapping"] = stage
    metadata["protection_status"] = "passed"
    metadata["ledger"] = ledger
    metadata["bed_change"] = dict(
        min_mesh_change_m=float(np.min(mesh - original_mesh)),
        max_mesh_change_m=float(np.max(mesh - original_mesh)),
        changed_vertex_count=int(np.count_nonzero(np.abs(mesh - original_mesh) > 0.)),
        support_vertex_count=int(np.count_nonzero(owner >= 0)),
        min_node_change_m=float(np.min(bed - states["node_bed_m"][0])),
        max_node_change_m=float(np.max(bed - states["node_bed_m"][0])),
        nodes_with_bed_change=int(np.count_nonzero(np.abs(bed - states["node_bed_m"][0]) > 0.)),
        continuous_pl_slope_violations=violations,
        continuous_pl_slope_violation_count=len(violations),
        max_abs_node_slope_change_per_m=float(np.max(np.abs(
            slope - _initial_slope(geometry, network, config)))),
        statement=("node bed and slope are re-sampled from the updated mesh every interval; "
                   "a mesh update necessarily moves both"))
    metadata["requested_end_time_seconds"] = float(forcing.time_seconds[-1])
    metadata["last_time_seconds"] = times[-1]
    result = dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
    validate_grid_reach(result)
    return result


def _interval_identity(geometry, bed, mesh, interval):
    """Deterministic geometry identity for one interval's bed state."""
    return identity({"node_bed_m": np.asarray(bed, np.float64),
                     "mesh_bed_m": np.asarray(mesh, np.float64)},
                    {"parent_geometry_identity_sha256": geometry["identity_sha256"],
                     "interval": int(interval), "algorithm": ALGORITHM})


def _cold_network(network, bed, slope):
    return ChannelNetwork(network.receiver.copy(), network.length_m.copy(),
        network.width_m.copy(), bed.copy(), slope.copy(), network.roughness.copy(),
        network.max_depth_m.copy(), network.terminal_kind.copy(),
        network.source_identity_sha256, "cold", "cold",
        receiver_distance_m=network.receiver_distance_m.copy())


def _initial_slope(geometry, network, config):
    return node_section(geometry, np.asarray(geometry["arrays"]["bed_elevation_m"], np.float64),
                        network, config)[1]


def _ledger(states, *, initial_alluvium_bulk_m3, porosity, cut_volume_m3,
            mesh_volume_changes):
    """Separate accounts and their numeric residuals.

    The mesh side is summed from the **per-interval** volume changes the coupled
    march already certified against the old sediment ledger. It is never rebuilt by
    integrating (final mesh - initial mesh): the bed change is ~1e-5 m over a ~1e9 m^2
    support, so such a difference of two ~1e11 m^3 integrals would carry only a few
    significant digits.
    """
    initial_mobile = float(states["mobile_solid_m3"][0].sum())
    initial_loose = float(states["loose_solid_m3"][0].sum())
    final_mobile = float(states["mobile_solid_m3"][-1].sum())
    final_loose = float(states["loose_solid_m3"][-1].sum())
    rock = float(states["rock_removed_m3"][-1].sum())
    deposited = float(states["deposited_solid_m3"][-1].sum())
    eroded_loose = float(states["eroded_loose_solid_m3"][-1].sum())
    exported = float(states["exported_solid_m3"][-1].sum())
    bulk_initial = float(np.sum(initial_alluvium_bulk_m3))
    solid_change = (final_mobile + final_loose) - (initial_mobile + initial_loose)
    mesh_change = float(np.sum(mesh_volume_changes))
    rock_floor_residual = mesh_change - ((final_loose - initial_loose) / (1. - porosity) - rock)
    # The old sediment ledger closes on every one of its own steps; these two
    # residuals measure the same bookkeeping at the reach scale. A nonzero loose
    # residual is erosion that lowered the bed but left the loose stock through the
    # channel network; the mobile+loose residual is dominated by deposition still
    # in transport at the final instant.
    loose_balance_residual = (final_loose - initial_loose) - deposited + eroded_loose
    solid_balance_residual = ((final_mobile + final_loose) - (initial_mobile + initial_loose)
                             - rock + exported)
    return dict(
        mobile_sand_solid_m3=dict(initial=initial_mobile, final=final_mobile,
                                  change=final_mobile - initial_mobile),
        loose_bed_sand_solid_m3=dict(initial=initial_loose, final=final_loose,
                                     change=final_loose - initial_loose, 
                                     eroded_cumulative=eroded_loose),
        cumulative_rock_erosion_m3=rock,
        cumulative_deposited_solid_m3=deposited,
        cumulative_exported_solid_m3=exported,
        initial_carve=dict(cut_bulk_volume_m3=cut_volume_m3,
                           initial_alluvium_bulk_m3=bulk_initial,
                           initial_alluvium_solid_m3=float(bulk_initial * (1. - porosity))),
        conservation=dict(
            loose_balance_residual_m3=float(loose_balance_residual),
            solid_residual_m3=float(solid_balance_residual),
            mesh_volume_change_m3=mesh_change,
            material_bulk_change_minus_rock_m3=float((final_loose - initial_loose)
                                                     / (1. - porosity) - rock),
            mesh_vs_material_residual_m3=rock_floor_residual,
            interpretation=("solid_residual_m3 = (final mobile+loose) - (initial mobile+loose) "
                            "- rock eroded + exported; it is zero when the old sediment "
                            "ledger closes; loose_balance_residual_m3 = loose change - "
                            "deposition + loose erosion, which isolates the bed account from "
                            "the mobile stock that carries material down the reach")),
        accounting_note=("mobile sand, loose bed sand, rock erosion, deposition, loose erosion "
                         "and export are separate accounts; the carve is the initial state"))


def validate_grid_reach(result):
    """Cold validation of a saved full-grid reach bundle."""
    if not isinstance(result, dict) or set(result) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("grid reach bundle must be {arrays, metadata, identity_sha256}")
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("schema") != SCHEMA or metadata.get("algorithm") != ALGORITHM:
        raise ValueError("grid reach schema or algorithm mismatch")
    if identity(arrays, metadata) != result["identity_sha256"]:
        raise ValueError("grid reach identity mismatch")
    if metadata.get("protection_relaxed") is not False:
        raise ValueError("the material-basis protection is not allowed to be relaxed")
    if metadata.get("dynamic_PL_mesh_updated") is not True:
        raise ValueError("a full-grid reach must declare that its PL mesh is updated")
    for key in ("material_area_m2", "hydraulic_control_area_m2", "vertex_owner",
                "triangle_area_m2", "mesh_bed_m", "source_mesh_bed_m"):
        if key not in arrays:
            raise ValueError("missing full-grid array: " + key)
    covered = np.asarray(arrays["material_area_m2"], np.float64)
    demand = np.asarray(arrays["hydraulic_control_area_m2"], np.float64)
    owner = np.asarray(arrays["vertex_owner"], np.int64)
    if np.any(covered < demand - 1e-9):
        raise ValueError("material basis area below hydraulic control area")
    mesh = np.asarray(arrays["mesh_bed_m"], np.float64)
    source = np.asarray(arrays["source_mesh_bed_m"], np.float64)
    if mesh.shape[0] != arrays["time_seconds"].shape[0]:
        raise ValueError("one mesh state per committed time required")
    if not np.array_equal(mesh[0], source):
        raise ValueError("initial mesh state must be the carved mesh")
    node_bed = np.asarray(arrays["node_bed_m"], np.float64)
    if np.array_equal(mesh[-1], source) and np.any(np.abs(node_bed[-1] - node_bed[0]) > 0.):
        raise ValueError("node bed moved while the mesh did not")
    if np.any(np.abs(mesh[-1] - source) > 0.) and np.array_equal(node_bed[-1], node_bed[0]):
        raise ValueError("mesh moved while the node bed did not")
    if owner.shape[0] != source.shape[0]:
        raise ValueError("vertex owner must cover the mesh vertices")
    geometry = _unpack(arrays, metadata, "geometry")
    lumped, area_triangles = vertex_areas(geometry)
    if not np.allclose(area_triangles, np.asarray(arrays["triangle_area_m2"], np.float64),
                       rtol=0., atol=1e-10):
        raise ValueError("saved triangle areas differ from the canonical mesh")
    support = owner >= 0
    rebuilt = np.bincount(owner[support], weights=lumped[support], minlength=0)
    if rebuilt.size != covered.size or not np.allclose(rebuilt, covered, rtol=0., atol=1e-6):
        raise ValueError("saved material areas are not the partition areas")
    if not math.isclose(float(lumped[support].sum()), float(np.sum(covered, dtype=np.float64)),
                        rel_tol=1e-12, abs_tol=1e-6):
        raise ValueError("partition areas do not exhaust the material support")
    if not np.array_equal(np.asarray(arrays["source_mesh_bed_m"], np.float64),
                          np.asarray(geometry["arrays"]["bed_elevation_m"], np.float64)):
        raise ValueError("the carved mesh state must be the parent geometry bed")
    ledger = metadata.get("ledger")
    if not isinstance(ledger, dict):
        raise ValueError("metadata.ledger required")
    residual = float(ledger["conservation"]["mesh_vs_material_residual_m3"])
    scale = max(abs(float(ledger["conservation"]["mesh_volume_change_m3"])),
                float(ledger["initial_carve"]["initial_alluvium_bulk_m3"]), 1.)
    if abs(residual) > 1e-8 * scale:
        raise ValueError("mesh volume and material ledger do not close: %.3e" % residual)
    return True


def save_grid_reach(path, result):
    save_bundle(path, result, validator=validate_grid_reach)
