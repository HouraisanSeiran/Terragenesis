"""Explicit finite original-TD planning candidates; coarse labels are references."""

from dataclasses import replace

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.channel_geometry import TERMINAL_STATUS_CODES, bounded_confluence_candidate

ALGORITHM = "finite_td_native_planning_candidate_v1"


def native_planning_identity(native_planning_owner_domain_id, *, source_identity_sha256,
                             boundary_identity_sha256, support_identity_sha256,
                             routing_identity_sha256, max_fill_depth_m):
    """Cold-readable candidate identity, independent of obsolete coarse labels."""
    return identity({"native_planning_owner_domain_id": native_planning_owner_domain_id}, dict(
        algorithm=ALGORITHM, source_identity_sha256=source_identity_sha256,
        boundary_identity_sha256=boundary_identity_sha256,
        support_identity_sha256=support_identity_sha256,
        routing_identity_sha256=routing_identity_sha256,
        max_fill_depth_m=float(max_fill_depth_m),
        owner_semantics="terminal cell ID in a fixed finite TD support; unresolved local catchments",
    ))


def native_planning_candidate(terrain, boundary, coarse_owner_reference, *,
                              baseline_receiver=None, max_fill_depth_m=4.0,
                              local_q_m3_s=None):
    height, valid = terrain.elevation_m, terrain.valid_mask
    coarse = np.asarray(coarse_owner_reference)
    if coarse.shape != height.shape or coarse.dtype.kind not in "iu":
        raise ValueError("matching integer coarse_owner_reference grid required")
    if not valid.all():
        raise ValueError("native planning requires a fixed complete rectangular TD support")
    perimeter = np.zeros(height.shape, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    if (boundary.kind.shape != height.shape
            or np.any(boundary.kind[perimeter] != "unknown_boundary")
            or np.any(boundary.kind[~perimeter] != "interior")):
        raise ValueError("native planning requires unknown exterior and no internal label boundaries")
    if baseline_receiver is not None:
        baseline_receiver = np.asarray(baseline_receiver)
        if baseline_receiver.shape != (height.size,) or baseline_receiver.dtype != np.int64:
            raise ValueError("baseline_receiver must be int64 [N]")
        if np.any(baseline_receiver[perimeter.ravel()] != -1):
            raise ValueError("baseline must retain explicit unknown perimeter terminals")

    # This mask expresses one bounded computation support, not frozen hydrologic
    # ownership. Ownership is constructed below from the final TD catchments.
    organization_mask = np.zeros(height.shape, np.int64)
    graph, work, kernel_metadata, arrays = bounded_confluence_candidate(
        terrain, boundary, organization_mask, baseline_receiver=baseline_receiver,
        max_fill_depth_m=max_fill_depth_m, local_q_m3_s=local_q_m3_s)
    graph = replace(graph, policy=ALGORITHM)
    owner = arrays["terminal_owner"].reshape(height.shape)
    arrays["native_planning_owner_domain_id"] = owner
    arrays["coarse_owner_reference"] = coarse.copy()
    arrays["native_planning_terminal_ids"] = np.flatnonzero(graph.receiver < 0)
    sources = np.flatnonzero(graph.receiver >= 0)
    targets = graph.receiver[sources]
    coarse_sources, coarse_targets = coarse.ravel()[sources], coarse.ravel()[targets]
    cross_label = coarse_sources != coarse_targets
    known_cross_label = cross_label & (coarse_sources >= 0) & (coarse_targets >= 0)
    status = arrays["terminal_status"]
    terminal = graph.receiver < 0
    artificial = terminal & ~perimeter.ravel() & (
        status == TERMINAL_STATUS_CODES["unresolved_domain_boundary"])
    if artificial.any() or np.any(owner.ravel()[sources] != owner.ravel()[targets]):
        raise ValueError("native candidate contains artificial label terminals or inconsistent catchments")
    support_metadata = dict(
        shape=list(height.shape), origin_xz_m=[terrain.x0_m, terrain.z0_m],
        spacing_xz_m=[terrain.dx_m, terrain.dz_m],
        cell_footprint_m_xz=[height.shape[1] * terrain.dx_m, height.shape[0] * terrain.dz_m],
        coordinates="cell centres X east, Z south; fixed complete finite rectangular support",
    )
    support_identity = identity({"valid_mask": valid}, support_metadata)
    identity_inputs = dict(
        source_identity_sha256=terrain.identity_sha256,
        boundary_identity_sha256=boundary.identity_sha256,
        support_identity_sha256=support_identity,
        routing_identity_sha256=graph.identity_sha256,
        max_fill_depth_m=float(max_fill_depth_m),
    )
    planning_metadata = dict(identity_inputs, algorithm=ALGORITHM,
        owner_semantics="terminal cell ID in a fixed finite TD support; unresolved local catchments")
    metadata = dict(
        schema="finite-td-native-planning-candidate-v1", algorithm=ALGORITHM,
        routing_kernel_algorithm=kernel_metadata["algorithm"],
        routing_kernel_metadata=kernel_metadata,
        native_planning_identity_sha256=native_planning_identity(owner, **identity_inputs),
        native_planning_metadata=planning_metadata,
        planning_identity_inputs=identity_inputs, fixed_support=support_metadata,
        source_identity_sha256=identity_inputs["source_identity_sha256"],
        boundary_identity_sha256=identity_inputs["boundary_identity_sha256"],
        support_identity_sha256=support_identity,
        routing_identity_sha256=identity_inputs["routing_identity_sha256"],
        coarse_reference_identity_sha256=identity({"coarse_owner_reference": coarse}, {}),
        coarse_reference_diagnostics=dict(
            cross_label_edge_count=int(cross_label.sum()),
            cross_known_label_edge_count=int(known_cross_label.sum()),
            cross_unknown_reference_edge_count=int((cross_label & ~known_cross_label).sum()),
            original_label_count=int(np.unique(coarse).size),
            interpretation="original coarse labels disagree with native TD drainage; diagnostic only, never routing walls",
        ),
        max_fill_depth_m=float(max_fill_depth_m), maximum_fill_m=kernel_metadata["maximum_fill_m"],
        filled_volume_m3=kernel_metadata["filled_volume_m3"],
        raised_cell_count=kernel_metadata["raised_cell_count"],
        terminal_status_codes=kernel_metadata["terminal_status_codes"],
        terminal_status_counts=kernel_metadata["terminal_status_counts"],
        artificial_internal_domain_terminal_count=int(artificial.sum()),
        candidate_catchment_count=int(terminal.sum()),
        organization_policy="one explicitly fixed finite TD support; organization mask is not hydrological ownership",
        native_owner_semantics="downstream terminal cell ID from native TD receiver DAG; local candidate catchment membership",
        candidate_scope="finite TD window only; not complete infinite-world planning domains or a replacement of the coarse domain inventory",
        ownership_check_semantics="construction consistency along receiver edges; not independent watershed or divide certification",
        independent_divide_certification=False, complete_hydrological_domains=False,
        external_boundary_semantics="unclosed unknown exterior; never inferred coast or ocean",
        terminal_semantics="deep depressions and exterior discharge remain unresolved; no accepted lake or sea outlet",
        work_surface_only=True, natural_outlet_verified=False, hydraulic_ready=False, publishable=False,
    )
    return graph, work, metadata, arrays
