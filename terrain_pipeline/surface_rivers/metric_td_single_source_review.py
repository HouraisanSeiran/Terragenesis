"""Read-only, single-source TD river review; no naturalness certification or solver."""

from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.common_infra import BoundaryGrid, TerrainGrid
from terrain_pipeline.drainage import accumulate_local_discharge as accumulate_local_discharge
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from .metric_distribution_calibration import evaluate_distribution
from .metric_morphology_coupling import _unpack
from .metric_naturalness_audit import channel_graph_observations
from .metric_water_cycle import validate_water_cycle

SCHEMA = "terragenesis-td-single-source-river-review-v1"
CHANNEL_AREA_M2 = 100_000.
METRICS = ("longitudinal_slope", "curvature_rad_per_m", "signed_slope_jump_knickpoint_candidate")


def _real_reference(reference):
    if reference is None:
        return None
    if (reference.get("schema") != "real-channel-distribution-reference-v1"
            or reference.get("identity_sha256") != identity({}, {k: v for k, v in reference.items() if k != "identity_sha256"})):
        raise ValueError("frozen real-reference identity required")
    return reference


def review_water_cycle_case(evidence, *, real_reference=None):
    """Review one verified saved TD terrain, diagnostic graph and channel/lake trace.

    A separate 90m real block is context, never pointwise truth for a 30m TD tile.
    Caller must pin/cold-read external artifact bytes before calling this function.
    """
    validate_water_cycle(evidence)
    reference = _real_reference(real_reference)
    a, m = evidence["arrays"], evidence["metadata"]
    inputs = _unpack(a, m, "inputs")
    ia, im = inputs["arrays"], inputs["metadata"]
    terrain = TerrainGrid(ia["terrain_height_m"], ia["valid_mask"], **im["terrain_metadata"])
    source_path = Path(terrain.source_path) if terrain.source_path else None
    if source_path is None or file_sha256(source_path) != terrain.source_sha256:
        raise ValueError("pinned TD source bytes unavailable or changed")
    if im["source_file_sha256"] != terrain.source_sha256:
        raise ValueError("saved case source SHA differs")
    if m["boundary_kind"] != "closed":
        raise ValueError("single-source review currently supports only explicit closed finite domain")
    kind = np.full(terrain.valid_mask.shape, "interior", dtype="U24")
    kind[[0, -1], :] = "closed_wall"
    kind[:, [0, -1]] = "closed_wall"
    kind[~terrain.valid_mask] = "unknown_boundary"
    boundary = BoundaryGrid(kind, np.zeros(kind.shape, bool),
                            "explicit finite closed TD diagnostic domain", im["source_identity_sha256"])
    graph = route_diagnostic(terrain, boundary)
    if (graph.identity_sha256 != im["graph_identity_sha256"]
            or not np.array_equal(graph.receiver, ia["receiver"])):
        raise ValueError("single-source receiver graph differs")
    valid = terrain.valid_mask.ravel()
    area = accumulate_local_discharge(graph, terrain.valid_mask * terrain.cell_area_m2)
    upstream = area["routed_q_m3_s"].ravel()
    channel = channel_graph_observations(terrain, graph, upstream,
                                         minimum_area_m2=CHANNEL_AREA_M2, curvature_method="atan2")
    owner = ia["contribution_owner"]
    selected = owner >= 0
    if np.any(selected & ~valid):
        raise ValueError("invalid native contribution cell")
    selected_area = float(np.count_nonzero(selected) * terrain.cell_area_m2)
    terminal = valid & (graph.receiver == -1)
    kinds, counts = np.unique(graph.outlet_kind[terminal], return_counts=True)
    terminal_area = float(upstream[terminal].sum())
    source = {"status": "verified_generated_TD_not_observed_DEM",
              "raw_source_sha256": terrain.source_sha256,
              "terrain_identity_sha256": terrain.identity_sha256,
              "shape_zx": list(terrain.valid_mask.shape), "spacing_m_xz": [terrain.dx_m, terrain.dz_m],
              "vertical_datum": terrain.vertical_datum,
              "valid_cell_count": int(valid.sum()), "selected_native_cell_count": int(selected.sum()),
              "selected_native_area_m2": selected_area,
              "exterior_interpretation": "finite_closed_cut_unknown_invalid_not_verified_natural_outlet",
              "natural_outlet_verified": False}
    catchment = {"status": "original_bed_D8_diagnostic_not_excavated_channel",
                 "graph_identity_sha256": graph.identity_sha256,
                 "terminal_kind_counts": dict(zip(kinds.tolist(), map(int, counts))),
                 "terminal_area_residual_m2": float(valid.sum() * terrain.cell_area_m2 - terminal_area),
                 "channel_threshold_m2": CHANNEL_AREA_M2,
                 "channel_support_node_count": int(np.count_nonzero(valid & (upstream >= CHANNEL_AREA_M2))),
                 "selected_area_fraction": float(selected.sum() / valid.sum())}
    coupled = _unpack(a, m, "coupled")
    ca, cm = coupled["arrays"], coupled["metadata"]
    channel_cell, lake_cell = im["channel_cell"], im["lake_cell"]
    if (cm["network"]["source_identity_sha256"] != terrain.identity_sha256
            or not np.array_equal(ca["lake_cell_ids"], [lake_cell])):
        raise ValueError("channel or lake is not bound to reviewed terrain")
    if (len(ca["network_width_m"]) != 1 or ca["network_width_m"].shape != (1,)
            or ca["network_length_m"].shape != (1,) or ca["network_bed_slope"].shape != (1,)):
        raise ValueError("bounded review expects one saved channel reach")
    width = float(ca["network_width_m"][0])
    length = float(ca["network_length_m"][0])
    bed = float(ca["network_bed_elevation_m"][0])
    downstream_bed = float(terrain.elevation_m.ravel()[lake_cell])
    distance = float(np.linalg.norm(np.subtract(terrain.world_xz(int(channel_cell)),
                                                terrain.world_xz(int(lake_cell)))))
    slope = (bed - downstream_bed) / distance
    if abs(length - distance) > 1e-8 or abs(float(ca["network_bed_slope"][0]) - slope) > 1e-10:
        raise ValueError("saved channel geometry differs from original TD bed")
    geometry = {"status": "saved_assumed_rectangular_one_reach_plus_D8_diagnostic",
                "channel_cell": int(channel_cell), "lake_cell": int(lake_cell),
                "length_m": length, "width_m": width, "bed_elevation_m": bed,
                "downstream_bed_elevation_m": downstream_bed,
                "bed_slope": float(ca["network_bed_slope"][0]),
                "original_bed_slope_difference": float(ca["network_bed_slope"][0] - slope),
                "channel_observations": channel,
                "cross_section_evidence": "assumed_rectangular_not_field_observed",
                "visual_similarity_certified": False}
    na = _unpack(a, m, "native")["arrays"]
    t = ca["trace_time_seconds"]
    dt = np.diff(t)
    local = float(np.sum((ca["trace_channel_local_q_m3_s"] + ca["trace_lake_local_q_m3_s"]) * dt[:, None]))
    external = float(ca["trace_channel_boundary_volume_m3"].sum() + ca["trace_lake_external_volume_m3"].sum())
    initial = float(ca["trace_channel_volume_m3"][0].sum() + ca["trace_lake_volume_m3"][0].sum())
    final = float(ca["trace_channel_volume_m3"][-1].sum() + ca["trace_lake_volume_m3"][-1].sum())
    residual = initial + local - external - final
    tolerance = 1e-8 * max(1., initial, local, external)
    if cm["result"]["status"] != "complete" or abs(residual) > tolerance:
        raise ValueError("saved water balance incomplete or unclosed")
    water = {"status": "verified_saved_native_runoff_channel_lake_finite_domain",
             "physical_duration_seconds": float(t[-1] - t[0]),
             "native_interval_count": len(na["time_seconds"]) - 1,
             "channel_initial_final_m3": [float(ca["trace_channel_volume_m3"][0].sum()),
                                          float(ca["trace_channel_volume_m3"][-1].sum())],
             "lake_initial_final_m3": [float(ca["trace_lake_volume_m3"][0].sum()),
                                       float(ca["trace_lake_volume_m3"][-1].sum())],
             "local_release_m3": local, "external_export_m3": external,
             "whole_inventory_residual_m3": residual, "tolerance_m3": tolerance,
             "boundary_kind": m["boundary_kind"],
             "real_water_comparison": "unavailable_no_matching_observed_hydrograph_or_cross_section"}
    comparison = {"status": "no_reference_provided", "metric_distances": {}}
    if reference is not None:
        comparison = {"status": "not_assessed_grid_extent_or_channel_support_mismatch",
                      "reference_identity_sha256": reference["identity_sha256"],
                      "reference_spacing_m": 90., "reference_extent_m": 4320.,
                      "observed_extent_m_xz": [terrain.valid_mask.shape[1] * terrain.dx_m,
                                               terrain.valid_mask.shape[0] * terrain.dz_m],
                      "metric_distances": {}, "real_holdout_summary": reference.get("relief_grid_real_holdout_summary")}
        if channel.get("status") != "insufficient_channel_support":
            samples = {key: channel[key]["samples"] for key in METRICS}
            relief = float(np.ptp(np.rint(terrain.elevation_m[terrain.valid_mask])))
            label = "low_relief" if relief < 50. else "moderate_relief" if relief < 250. else "high_relief"
            calibration = reference["calibrations"].get(label)
            if calibration and all(len(values) >= 2 for values in samples.values()):
                distances = evaluate_distribution(samples, calibration, conditions_match=False)
                comparison.update(metric_distances=distances["metric_scores"],
                                  joint_cdf_distance=distances["joint_score"],
                                  real_calibration_cutoff_context_only=distances["cutoff"],
                                  status="context_only_scale_mismatch_not_assessed")
    result = {"schema": SCHEMA, "status": "bounded_review_not_natural_certification",
              "evidence_identity_sha256": evidence["identity_sha256"],
              "source": source, "catchment": catchment, "channel_geometry": geometry,
              "saved_water": water, "real_reference_comparison": comparison,
              "unresolved": ["no observed matching cross-section or hydrograph",
                             "no direct image or perceptual evaluation on this single-source tile",
                             "small finite domain cannot establish full-network visual realism",
                             "unknown original TD land-water exterior; closed engineered cut is not a natural outlet"],
              "natural_certification": False, "publishable": False}
    result["identity_sha256"] = identity({}, result)
    return result
