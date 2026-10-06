"""Cold audit a dry-drain ordinary pulse without conflating lake boundary inflow."""

import argparse
import gc
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_entry_shallow_water import audit_case, read_bundle, read_json, check_memory
from tools.td_entry_saved_audit import assert_close, compare_saved_levels

SOURCE_INDEX_SHA = "232c9d1d378b02a7abc76670a8989fa97c58d7201b0ec3b323876ceaf5aedc56"


def audit_preparation(index):
    parent_pin = index["source_parent_index"]
    if parent_pin["sha256"] != SOURCE_INDEX_SHA:
        raise ValueError("pulse carrier must reuse the fixed source preparation")
    parent = read_json(parent_pin)
    parent_audit = read_json(index["source_parent_audit"])
    if parent_audit["status"] != "passed" or parent_audit["index_sha256"] != SOURCE_INDEX_SHA:
        raise ValueError("pulse parent independent source audit missing")
    if index["carrier"] != parent["carrier"]:
        raise ValueError("pulse bed changed instead of same-bed forcing experiment")
    for code, sha256 in dict(parent["code_sha256"], **index["code_sha256"]).items():
        if file_sha256(ROOT/code) != sha256:
            raise ValueError("pulse execution/source code changed")
    for pin in parent["inputs"].values():
        if file_sha256(pin["path"]) != pin["sha256"]:
            raise ValueError("pulse parent dependency no longer immutable")
    bed, geometry, forcing = (read_bundle(index[key]) for key in ("carrier", "geometry", "forcing"))
    old_geometry = read_bundle(parent["geometry"])
    for name, value in old_geometry["arrays"].items():
        expected = np.where(value == 2, 1, value) if name == "boundary_kind" else value
        assert_close(geometry["arrays"][name], expected, "dry-drain same bed/face "+name)
    for name in ("spacing_m", "origin_m_xz", "source_identity"):
        if geometry["metadata"][name] != old_geometry["metadata"][name]:
            raise ValueError("pulse geometry coordinates or source identity changed")
    if geometry["metadata"]["bed_identity_sha256"] != bed["identity_sha256"]:
        raise ValueError("pulse geometry bed identity mismatch")
    kinds = geometry["arrays"]["boundary_kind"]
    if not np.any(kinds == 1) or np.any(kinds == 2) or not np.isin(kinds, (0, 1)).all():
        raise ValueError("pulse exterior must be closed or dry engineering drain")
    arrays, meta = forcing["arrays"], forcing["metadata"]
    duration, interval = float(meta["duration_s"]), float(meta["interval_s"])
    pulse_duration = float(meta["pulse_duration_s"])
    if duration <= 60 or not 0 < pulse_duration < duration or duration/interval != round(duration/interval):
        raise ValueError("pulse long/retreat schedule invalid")
    times = np.arange(round(duration/interval)+1)*interval
    assert_close(arrays["time_s"], times, "pulse physical saved schedule")
    initial = arrays["initial_depth_m"]
    if initial.shape[1:] != bed["arrays"]["derived_bed_m"].shape or np.any(initial != 0):
        raise ValueError("pulse source isolation requires exactly dry initial water")
    case_count = initial.shape[0]
    if case_count not in (1, 2):
        raise ValueError("pulse forcing case carrier shape invalid")
    forcing_mask = bed["arrays"]["forcing_mask"].ravel()
    q_value = float(bed["metadata"]["ordinary_q_m3_s"])
    rates = (times[:-1] < pulse_duration)[:, None]*forcing_mask[None]*q_value/forcing_mask.sum()
    expected = np.repeat(rates[None], case_count, axis=0)
    assert_close(arrays["forcing_m3_s"], expected, "unmodified ordinary Q without rain")
    if meta["bed_identity_sha256"] != bed["identity_sha256"] or meta["geometry_identity_sha256"] != geometry["identity_sha256"]:
        raise ValueError("pulse forcing parent identity mismatch")
    if len(meta["case_names"]) != case_count:
        raise ValueError("pulse forcing case names mismatch")
    boundary = arrays["boundary_stage_m"]
    if boundary.shape != (case_count, len(times)-1, len(kinds)) or not np.isfinite(boundary).all():
        raise ValueError("pulse finite boundary carrier shape mismatch")
    time_limits = index["declared_maxdt_s"]
    if len(time_limits) != 2 or not 0 < time_limits[1] < time_limits[0]:
        raise ValueError("pulse actual time limits not refined")
    faces = len(geometry["arrays"]["face_left"])+len(kinds)
    projected = 3*faces*sum(math.ceil(duration/value) for value in time_limits)
    if projected > 6_000_000_000:
        raise ValueError("pulse minimum projected RK+endpoint work already over budget")
    longitudinal = bed["arrays"]["longitudinal_from_upstream_m"].ravel()
    if np.any(forcing_mask & (longitudinal >= 5)):
        raise ValueError("pulse supply injected beyond upstream source region")
    report = dict(status="passed", immutable_carrier_verified=True, source_parent_audit_reused=True,
                  dry_initial_and_drain_verified=True, exact_ordinary_Q_mask_verified=True,
                  duration_s=duration, pulse_duration_s=pulse_duration, interval_s=interval,
                  ordinary_q_m3_s=q_value, injection_node_id=bed["metadata"]["injection_node_id"],
                  cells=len(longitudinal), minimum_projected_face_work=projected,
                  projected_work_is_not_a_CFL_upper_bound=True, natural_outlet_verified=False)
    return report, bed, geometry, forcing, longitudinal


def audit_reception(case, bed, geometry, forcing, longitudinal):
    state = read_bundle(case["state"])
    transfers = read_bundle(case["intervals"])
    arrays = state["arrays"]
    depth = arrays["depth_m"].reshape(len(arrays["time_s"]), -1)
    if state["metadata"]["status"] != "completed" or state["metadata"]["case_index"] != 0:
        raise ValueError("pulse case incomplete or wrong forcing scene")
    if np.any(depth < 0) or np.any(arrays["momentum_x_m2_s"][0] != 0) or np.any(arrays["momentum_z_m2_s"][0] != 0):
        raise ValueError("pulse water positivity or dry momentum initialization mismatch")
    no_import = bool(np.all(arrays["ledger"][:, 1] == 0) and state["metadata"]["boundary_input_m3"] == 0)
    if not no_import:
        raise ValueError("dry-drain event imported water; cannot certify upstream-only provenance")
    spacing = bed["metadata"]["spacing_m"]
    area = spacing**2
    left, right, boundary = (geometry["arrays"][name] for name in ("face_left", "face_right", "boundary_cell"))
    internal = transfers["arrays"]["internal_transfer_m3"]
    exterior = transfers["arrays"]["boundary_transfer_m3"]
    times = arrays["time_s"]
    cuts = []
    for station in (5., 30., 60.):
        in_receiver = longitudinal >= station
        forward = ~in_receiver[left] & in_receiver[right]
        backward = in_receiver[left] & ~in_receiver[right]
        signed = internal[:, forward].sum(axis=1)-internal[:, backward].sum(axis=1)
        outgoing = exterior[:, in_receiver[boundary]].sum(axis=1)
        volume = depth[:, in_receiver].sum(axis=1)*area
        expected = np.r_[0., np.cumsum(signed-outgoing)]
        assert_close(volume, expected, "downstream receiving region "+str(station))
        crossing = np.flatnonzero(np.cumsum(signed) > 1e-8)
        cuts.append(dict(station_m=station, signed_interval_downstream_m3=signed.tolist(),
                         cumulative_downstream_m3=float(signed.sum()), receiver_storage_m3=volume.tolist(),
                         receiving_region_mass_balance_verified=True,
                         first_saved_interval_with_positive_cumulative_transfer_end_s=float(times[crossing[0]+1]) if len(crossing) else None))
    wet_support = bed["arrays"]["wet_protected_mask"].ravel() & (longitudinal >= 60)
    protected_volume = depth[:, wet_support].sum(axis=1)*area
    center = bed["arrays"]["centerline_offset_m"].ravel() <= .175
    wet_front = [float(longitudinal[(row > 1e-6) & center].max(initial=0)) for row in depth]
    head = longitudinal < 5
    head_volume = depth[:, head].sum(axis=1)*area
    head_retreat = bool(head_volume[-1] < head_volume.max()-1e-8)
    at_lake = cuts[-1]
    lake_arrival = bool(at_lake["cumulative_downstream_m3"] > 1e-8 and protected_volume.max(initial=0) > 1e-6)
    return dict(case_id=case["case_id"], time_s=times.tolist(), cuts=cuts,
                exact_zero_external_water_input_verified=no_import, all_water_from_upstream_Q_verified=True,
                provenance_method="exact dry initial water + unchanged ordinary Q as sole source + no imported boundary water",
                maximum_protected_support_water_m3=float(protected_volume.max(initial=0)),
                protected_support_water_m3=protected_volume.tolist(), headwater_volume_m3=head_volume.tolist(),
                headwater_retreat_observed=head_retreat, centerline_wet_front_m=wet_front,
                upstream_pulse_to_saved_source_wet_support_verified=lake_arrival,
                engineering_drain_output_m3=state["metadata"]["boundary_output_m3"],
                supplied_m3=state["metadata"]["supplied_m3"],
                actual_lake_boundary_hydraulics_verified=False, natural_outlet_verified=False)


def audit(index):
    preparation, bed, geometry, forcing, longitudinal = audit_preparation(index)
    cases = index.get("cases", [])
    if not cases:
        return dict(schema="td-entry-pulse-independent-audit-v1", status="passed", preparation=preparation,
                    local_saved_hydraulics_verified=False, time_refinement_verified=False,
                    upstream_pulse_to_saved_source_wet_support_verified=False, natural_outlet_verified=False)
    if len(cases) != 2 or sorted(case["level"] for case in cases) != [0, 1] or any(case["case_index"] != 0 for case in cases):
        raise ValueError("pulse requires two distinct complete levels of one isolated scene")
    reports, receptions, levels = [], [], []
    work = 0
    for case in sorted(cases, key=lambda item: item["level"]):
        if case["status"] != "saved_requires_independent_audit":
            raise ValueError("pulse case failure preserved, not accepted")
        report, compact = audit_case(case, bed, geometry, forcing, longitudinal)
        reports.append(report)
        receptions.append(audit_reception(case, bed, geometry, forcing, longitudinal))
        levels.append(compact)
        work += compact["metadata"]["face_evaluations"]*3//2
        if compact["metadata"]["max_dt_requested_s"] != index["declared_maxdt_s"][case["level"]]:
            raise ValueError("pulse level requested time not bound to declaration")
        gc.collect()
    coarse, fine = levels
    comparison = compare_saved_levels(coarse["arrays"], fine["arrays"], coarse["internal"], fine["internal"],
        bed["metadata"]["spacing_m"], coarse["metadata"]["substeps"], fine["metadata"]["substeps"])
    boundary_delta = float(abs(coarse["boundary"].sum(axis=0)-fine["boundary"].sum(axis=0)).sum())
    denominator = float(abs(fine["boundary"].sum(axis=0)).sum())
    boundary_l1 = boundary_delta/max(denominator, 1e-12)
    effective = fine["metadata"]["diagnostics"]["maximum_dt_s"] < coarse["metadata"]["diagnostics"]["maximum_dt_s"]
    comparison.update(cumulative_boundary_net_relative_l1=boundary_l1,
                      maxdt_constraint_effective=effective, passed=bool(comparison["passed"] and effective and boundary_l1 <= .01))
    resource = index["resource"]
    if work > 6_000_000_000 or resource["actual_peak_rss_bytes"] > 1024**3:
        raise ValueError("pulse actual execution resource gate failed")
    reached = all(item["upstream_pulse_to_saved_source_wet_support_verified"] for item in receptions)
    return dict(schema="td-entry-pulse-independent-audit-v1", status="passed", preparation=preparation,
                cases=reports, source_isolated_reception=receptions, comparison=comparison,
                local_saved_hydraulics_verified=True, time_refinement_verified=comparison["passed"],
                upstream_pulse_to_saved_source_wet_support_verified=bool(reached and comparison["passed"]),
                all_water_from_upstream_Q_verified=True, actual_face_work_verified=work,
                actual_peak_audit_rss_bytes=check_memory(),
                actual_lake_boundary_hydraulics_verified=False, natural_outlet_verified=False,
                complete_river_hydraulics_verified=False, cross_domain_hydraulics_verified=False,
                scope="isolated ordinary pulse reaches unchanged native wet-support location; dry engineering drain, not a natural lake or mouth")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT/"verification/natural-river-network"):
        raise ValueError("new pulse independent audit output required")
    index = read_json(dict(path=str(args.input.resolve()), sha256=args.sha256))
    result = audit(index)
    result.update(index_sha256=args.sha256, audit_code_sha256={name: file_sha256(ROOT/name) for name in (
        "tools/audit_td_entry_pulse_propagation.py", "tools/audit_td_entry_shallow_water.py",
        "tools/td_entry_saved_audit.py", "tools/single_domain_shallow_water_audit.py")})
    publish_bytes(output, (json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+"\n").encode())
    summary = {key: value for key, value in result.items() if key not in ("cases", "source_isolated_reception", "audit_code_sha256")}
    print(json.dumps(summary, allow_nan=False))


if __name__ == "__main__":
    main()
