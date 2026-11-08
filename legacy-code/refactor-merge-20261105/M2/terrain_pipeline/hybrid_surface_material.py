"""Signed cut-only material ledger and saved source-sampling mismatch witnesses."""
import numpy as np
from terrain_pipeline.hybrid_geometry_common import TOLERANCE_M
from terrain_pipeline.hybrid_surface_prisms import exact_depth


def volume_ledger(before, old_after, old_removed, after, removed, extra):
    values = {"original_rock_before_m3": float(before.volume()), "original_removed_m3": float(old_removed.volume()),
        "original_rock_after_m3": float(old_after.volume()), "total_removed_m3": float(removed.volume()),
        "extra_removed_m3": float(extra.volume()), "new_rock_after_m3": float(after.volume()), "fill_m3": 0.}
    residuals = [values["original_rock_before_m3"] - values["original_rock_after_m3"] - values["original_removed_m3"],
        values["original_rock_before_m3"] - values["new_rock_after_m3"] - values["total_removed_m3"],
        values["total_removed_m3"] - values["original_removed_m3"] - values["extra_removed_m3"]]
    tolerance = max(1e-7, values["original_rock_before_m3"] * 1e-10)
    if max(map(abs, residuals)) > tolerance:
        raise ValueError("signed_original_total_extra_material_balance_failed")
    values.update(signed_residuals_m3=residuals, residual_tolerance_m3=tolerance,
        fine15_material_replaced=False, sampled_solid_material_not_native_exact=True)
    return values


def saved_sampling_mismatch_witnesses(sampling, attachments, ports):
    witnesses = []
    for kind in ("sink", "spring"):
        attachment = attachments["attachments"][kind]
        triangle_ids = {"shared:" + fan["node_id"] + ":" + str(ordinal)
            for fan in attachment["compact_native_fans"][:1] for ordinal in attachment["half_arm_triangle_indices"]}
        fans = [fan for fan in attachment["compact_native_fans"] if fan["triangle_id"] in triangle_ids]
        midpoint = np.asarray(ports[kind]["midpoint_xz_m"])
        flow = np.asarray(ports[kind]["flow_unit_xz"])
        for sample in sampling["samples"]:
            point = sample["xz_m"]
            if abs(float((np.asarray(point) - midpoint) @ flow)) > TOLERANCE_M:
                continue
            hits = []
            for fan in fans:
                vertices = np.asarray(fan["vertices_xz_m"])
                if np.any(np.asarray(point) < vertices.min(axis=0)) or np.any(np.asarray(point) > vertices.max(axis=0)):
                    continue
                try:
                    depth = exact_depth(fan, point)
                except ValueError as error:
                    if str(error) == "point_outside_exact_saved_fan":
                        continue
                    raise
                hits.append({"fan_key": fan["fan_key"], "exact_domain_cut_depth_m": depth,
                    "saved_vertices_xz_m": fan["vertices_xz_m"], "saved_vertex_depths_m": fan["depth_at_vertices_m"]})
            if not hits:
                continue
            depths = [hit["exact_domain_cut_depth_m"] for hit in hits]
            if max(depths) - min(depths) > 1e-9:
                raise ValueError("independent_exact_saved_fan_shared_depth_mismatch")
            if abs(depths[0] - sample["cut_depth_m"]) > 1e-9:
                witnesses.append({"kind": kind, "source_sampling_row": sample["row"], "source_sampling_column": sample["column"],
                    "point_xz_m": point, "saved_cut_depth_m": sample["cut_depth_m"], "saved_fan_keys": sample["fan_keys"],
                    "saved_derived_bed_m": sample["derived_bed_m"], "saved_original_source_sample": sample["source_sample"],
                    "exact_domain_supports": hits, "expected_cut_depth_m": depths[0],
                    "sampled_top_excess_height_m": depths[0] - sample["cut_depth_m"],
                    "classification": "saved_cut_lookup_mismatch_exact_domain_not_source_height_recalculation",
                    "scope": "only_saved_port_plane_grid_samples_no_global_source_claim"})
    return witnesses
