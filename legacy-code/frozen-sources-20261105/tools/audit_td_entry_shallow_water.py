"""Cold-read source, geometry, forcing and saved HLL lake-entry transactions."""

import argparse
import gc
import json
from pathlib import Path
import sys

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, load_bundle, publish_bytes
from tools.td_entry_saved_audit import (
    assert_close, audit_first_rk, audit_interval, compare_saved_levels,
    flat_geometry, native_bilinear_source)

MAX_BYTES = 1024**3


def check_memory():
    memory = psutil.Process().memory_info()
    peak = max(memory.rss, getattr(memory, "peak_wset", 0))
    if peak > MAX_BYTES:
        raise MemoryError("entry cold audit exceeds 1GiB")
    return peak


def read_json(pin):
    path = Path(pin["path"]).resolve(strict=True)
    if not path.is_relative_to(ROOT) or path.stat().st_size > 64*1024**2 or file_sha256(path) != pin["sha256"]:
        raise ValueError("entry saved JSON pin/path/size mismatch")
    result = json.loads(path.read_text(encoding="utf8"))
    if "identity_sha256" in pin and result["identity_sha256"] != pin["identity_sha256"]:
        raise ValueError("entry saved JSON external identity mismatch")
    check_memory()
    return result


def validate_bundle(record):
    if identity(record["arrays"], record["metadata"]) != record["identity_sha256"]:
        raise ValueError("entry bundle internal identity mismatch")


def read_bundle(pin, *, native_source=False):
    path = Path(pin["path"]).resolve(strict=True)
    if not path.is_relative_to(ROOT):
        raise ValueError("entry bundle outside workspace")
    record = load_bundle(path, expected_sha256=pin["sha256"], validator=validate_bundle, max_bytes=MAX_BYTES)
    if record["identity_sha256"] != pin["identity_sha256"]:
        raise ValueError("entry bundle external identity mismatch")
    if not native_source and any(not np.isfinite(value).all() for value in record["arrays"].values()):
        raise ValueError("entry bundle nonfinite array")
    check_memory()
    return record


def audit_carrier(index):
    inputs = index["inputs"]
    hierarchy = read_bundle(inputs["hierarchy"], native_source=True)
    paths, sections, transitions, fine = (read_json(inputs[key]) for key in ("paths", "sections", "transitions", "fine"))
    bed, geometry, forcing = (read_bundle(index[key]) for key in ("carrier", "geometry", "forcing"))
    arrays, meta = bed["arrays"], bed["metadata"]
    spacing, shape = meta["spacing_m"], arrays["source_bed_m"].shape
    if spacing != .175 or arrays["source_bed_m"].size > 65536:
        raise ValueError("entry fine lattice/cell budget mismatch")
    for key, record in (("hierarchy", hierarchy), ("paths", paths), ("sections", sections), ("transitions", transitions), ("fine", fine)):
        if meta["parent_identities"][key] != record["identity_sha256"]:
            raise ValueError("entry carrier parent identity mismatch")
    first_row, first_column = meta["global_origin_row_column"]
    rows, columns = np.indices(shape)
    assert_close(arrays["global_row"], rows+first_row, "global row lattice")
    assert_close(arrays["global_column"], columns+first_column, "global column lattice")
    origin = np.asarray(fine["grid"]["origin_m_xz"])
    points = origin+(np.column_stack((columns.ravel()+first_column, rows.ravel()+first_row))+.5)*spacing
    source, wet = native_bilinear_source(hierarchy, paths["selected_leaf_ids"], points, fine["wet_protection"])
    assert_close(arrays["source_bed_m"].ravel(), source, "real native DEM background")
    assert_close(arrays["wet_protected_mask"].ravel(), wet, "wet source protection")
    if not arrays["valid_mask"].all() or arrays["protected_mask"].any():
        raise ValueError("entry carrier invalid source mask")
    entry_index = meta["entry_index"]
    entry = transitions["entries"][entry_index]
    port = next(item for item in sections["edge_sections"] if item["arc_id"] == entry["accepted_port_arc_id"])
    nodes = {item["node_id"]: item for item in paths["nodes"]}
    chain = [port["node_ids"][0], entry["upstream_node_id"], entry["anchor_node_id"], entry["wet_node_id"]]
    xyz = np.array([nodes[node]["xyz_m"] for node in chain])
    assert_close(arrays["chain_xyz_m"], xyz, "actual edge/taper/wet support chain")
    assert_close(arrays["chain_native_cell_ids"], [nodes[node]["cell_id"] for node in chain], "chain native ids")
    if entry["entry_id"] != meta["entry_id"] or meta["injection_node_id"] != chain[0] or meta["injection_native_cell_id"] != nodes[chain[0]]["cell_id"]:
        raise ValueError("entry id or ordinary Q injection node mismatch")
    q_section = next(item for item in sections["node_sections"] if item["node_id"] == chain[0])
    assert_close(meta["ordinary_q_m3_s"], q_section["representative_q_m3_s"], "ordinary Q at exact first node")
    triangles = [item for item in fine["triangles"] if
                 (item["source_package"] == "09" and item["source_entry_index"] == entry_index) or
                 (item["source_package"] == "06" and item["source_arc_id"] == port["arc_id"])]
    if any(item["rejection_reasons"] or item["status"] not in ("rasterized", "no_center_coverage") for item in triangles):
        raise ValueError("entry whole triangle coverage incomplete")
    if meta["selected_triangle_ids"] != [item["triangle_id"] for item in triangles]:
        raise ValueError("entry permitted triangle set mismatch")
    assert_close(arrays["selected_triangle_vertices_xyz_m"], [item["vertices_xyz_m"] for item in triangles], "saved parent mesh")
    selected = set(meta["selected_triangle_ids"])
    expected_overlay = np.zeros(len(points), bool)
    expected_bed = source.copy()
    referenced = set()
    for window_index, window in enumerate(fine["windows"]):
        row_base, column_base = window["global_origin_row_column"]
        for cell_index, cell in enumerate(window["cells"]):
            if not any(item["triangle_id"] in selected for item in cell["triangle_sources"]):
                continue
            if cell["status"] != "candidate" or cell["rejection_reasons"]:
                raise ValueError("entry overlay contains refused parent cell")
            row = row_base+cell["local_index"]//fine["grid"]["tile_cells"]-first_row
            column = column_base+cell["local_index"]%fine["grid"]["tile_cells"]-first_column
            if not 0 <= row < shape[0] or not 0 <= column < shape[1]:
                raise ValueError("entry selected cell missing from rectangular carrier")
            local = row*shape[1]+column
            if local in referenced:
                raise ValueError("entry duplicate fine global owner")
            referenced.add(local)
            expected_overlay[local] = True
            expected_bed[local] = cell["derived_bed_m"]
            assert_close(arrays["fine_window_index"][row, column], window_index, "fine window reference")
            assert_close(arrays["fine_cell_index"][row, column], cell_index, "fine cell reference")
            assert_close(source[local], cell["source_sample"]["height_m"], "fine native source")
    geometric_coverage = np.zeros(len(points), bool)
    for triangle in triangles:
        vertices = np.array(triangle["vertices_xyz_m"])
        inside_box = ((points >= vertices[:, [0, 2]].min(axis=0)-1e-8) & (points <= vertices[:, [0, 2]].max(axis=0)+1e-8)).all(axis=1)
        candidates = np.flatnonzero(inside_box)
        matrix = np.vstack((vertices[:, [0, 2]].T, np.ones(3)))
        weights = np.linalg.solve(matrix, np.vstack((points[candidates].T, np.ones(len(candidates))))).T
        inside = weights.min(axis=1) >= -1e-9
        indices = candidates[inside]
        geometric_coverage[indices] = True
        if not expected_overlay[indices].all():
            raise ValueError("entry parent triangles contain unfilled fine holes")
        if np.any(abs(expected_bed[indices]-weights[inside] @ vertices[:, 1]) > fine["parameters"]["conflict_tolerance_m"]):
            raise ValueError("entry parent interpolated bed mismatch")
    assert_close(expected_overlay, geometric_coverage, "actual mesh center coverage")
    assert_close(arrays["overlay_mask"].ravel(), expected_overlay, "only permitted cut overlay")
    assert_close(arrays["derived_bed_m"].ravel(), expected_bed, "actual fine derived DEM")
    cut = source-expected_bed
    if cut.min() < -1e-8 or cut.max() > 4+1e-8 or np.any(wet & (cut > meta["wet_cut_tolerance_m"])):
        raise ValueError("entry no-fill/max-cut/wet-bed gate")
    assert_close(arrays["fine_window_index"].ravel()[~expected_overlay], -np.ones((~expected_overlay).sum()), "source-only window sentinel")
    bed_values = arrays["derived_bed_m"]
    boundary_count = 2*sum(shape)
    kinds = np.zeros(boundary_count, int)
    direction = (xyz[-1, [0, 2]]-xyz[0, [0, 2]])/90
    axis = int(np.argmax(abs(direction)))
    side = (1 if direction[0] > 0 else 0) if axis == 0 else (3 if direction[1] > 0 else 2)
    lengths = [shape[0], shape[0], shape[1], shape[1]]
    start = sum(lengths[:side])
    kinds[start:start+lengths[side]] = 2
    expected_geometry = flat_geometry(bed_values, spacing, kinds, geometry["arrays"]["boundary_crest_m"])
    for name, expected in expected_geometry.items():
        assert_close(geometry["arrays"][name], expected, "D4 geometry "+name)
    assert_close(geometry["arrays"]["H0_m"], bed_values, "H0 on same new bed")
    assert_close(geometry["arrays"]["boundary_crest_m"], bed_values.ravel()[expected_geometry["boundary_cell"]], "physical boundary bed crest")
    assert_close(geometry["arrays"]["face_crest_m"], np.maximum(bed_values.ravel()[expected_geometry["face_left"]], bed_values.ravel()[expected_geometry["face_right"]]), "internal face crest")
    longitudinal = (points-xyz[0, [0, 2]]) @ direction
    cross = np.array(port["cross_section_xyz_m"][0])[1:3, [0, 2]]
    lateral = 1-axis
    injection = (longitudinal >= -1e-8) & (longitudinal < spacing+1e-8) & expected_overlay
    injection &= (points[:, lateral] >= cross[:, lateral].min()-1e-8) & (points[:, lateral] <= cross[:, lateral].max()+1e-8)
    assert_close(arrays["forcing_mask"].ravel(), injection, "actual upstream cross-section injection")
    times = forcing["arrays"]["time_s"]
    interval_s, duration = forcing["metadata"]["interval_s"], forcing["metadata"]["duration_s"]
    assert_close(np.diff(times), np.full(len(times)-1, interval_s), "uniform saved physical time")
    expected_forcing = np.zeros_like(forcing["arrays"]["forcing_m3_s"])
    expected_forcing[0] = (times[:-1] < duration/3)[:, None]*injection[None]*meta["ordinary_q_m3_s"]/injection.sum()
    assert_close(forcing["arrays"]["forcing_m3_s"], expected_forcing, "ordinary Q schedule without duplicated rain")
    stage = next(item for item in paths["lakes"] if item["leaf_id"] == nodes[chain[-1]]["leaf_id"])["ordinary_stage_max_m"]
    initial = np.zeros_like(forcing["arrays"]["initial_depth_m"])
    initial[1] = np.maximum(stage-bed_values, 0)
    assert_close(forcing["arrays"]["initial_depth_m"], initial, "own-bed initialized water")
    boundary = np.full_like(forcing["arrays"]["boundary_stage_m"], stage)
    rise = ((times[:-1] >= duration/3) & (times[:-1] < 2*duration/3))*forcing["metadata"]["tailwater_rise_m"]
    boundary[1] += rise[:, None]
    assert_close(forcing["arrays"]["boundary_stage_m"], boundary, "declared engineering lake schedule")
    report = dict(native_source_verified=True, unique_fine_overlay_verified=True, whole_mesh_centers_verified=True,
                  no_fill_and_wet_protection_verified=True, exact_injection_node_q_verified=True,
                  unique_D4_faces_verified=True, own_bed_forcing_verified=True, cells=bed_values.size,
                  shape=list(shape), cut_rock_m3=float(cut.sum()*spacing**2), entry_id=meta["entry_id"],
                  ordinary_q_m3_s=meta["ordinary_q_m3_s"], background_source_resolution_m=hierarchy["metadata"]["spacing_m"],
                  lake_support_bed_unmodified=True, natural_outlet_verified=False)
    del hierarchy, paths, sections, transitions, fine
    gc.collect()
    return report, bed, geometry, forcing, longitudinal


def audit_case(case, bed, geometry, forcing, longitudinal):
    state, transfers, witness = (read_bundle(case[key]) for key in ("state", "intervals", "first_rk"))
    arrays, meta = state["arrays"], state["metadata"]
    case_index = case["case_index"]
    for key, expected in (("source_identity", bed["identity_sha256"]), ("forcing_identity", forcing["identity_sha256"]), ("geometry_identity_sha256", geometry["identity_sha256"])):
        if meta[key] != expected:
            raise ValueError("entry case wrong bed/forcing/geometry")
    for record in (transfers, witness):
        if record["metadata"]["state_identity_sha256"] != state["identity_sha256"]:
            raise ValueError("entry observer wrong state identity")
    assert_close(arrays["time_s"], forcing["arrays"]["time_s"], "case snapshot times")
    assert_close(arrays["depth_m"][0], forcing["arrays"]["initial_depth_m"][case_index], "case own-bed initial water")
    intervals = len(arrays["time_s"])-1
    momentum = np.stack((arrays["momentum_x_m2_s"], arrays["momentum_z_m2_s"]), axis=-1).reshape(intervals+1, -1, 2)
    spacing = bed["metadata"]["spacing_m"]
    reports = []
    for interval in range(intervals):
        packet = {key: value[interval] for key, value in transfers["arrays"].items()}
        before, after = arrays["depth_m"][interval:interval+2].reshape(2, -1)
        dt = arrays["time_s"][interval+1]-arrays["time_s"][interval]
        source = forcing["arrays"]["forcing_m3_s"][case_index, interval].ravel()
        reports.append(audit_interval(packet, geometry["arrays"], spacing, before, after,
                                     momentum[interval], momentum[interval+1], source*dt))
        rk = {key: value[interval] for key, value in witness["arrays"].items()}
        assert_close(rk["state_before"], np.column_stack((before, momentum[interval])), "first RK interval continuity")
        assert_close(rk["time_start_s"], arrays["time_s"][interval], "first RK physical time")
        audit_first_rk(rk, rk["dt_s"], geometry["arrays"], spacing, meta["budget"], source,
                       forcing["arrays"]["boundary_stage_m"][case_index, interval])
    volumes = arrays["depth_m"].sum(axis=(1, 2))*spacing**2
    assert_close(arrays["ledger"][:, 3], volumes, "snapshot volume ledger")
    supplied = np.r_[0, np.cumsum(forcing["arrays"]["forcing_m3_s"][case_index].sum(axis=1)*forcing["metadata"]["interval_s"])]
    assert_close(arrays["ledger"][:, 0], supplied, "total supply ledger")
    external = np.r_[0, np.cumsum(transfers["arrays"]["boundary_transfer_m3"].sum(axis=1))]
    assert_close(volumes-volumes[0], supplied-external, "full saved water conservation")
    assert_close(arrays["ledger"][:, 1]-arrays["ledger"][:, 2], -external, "gross totals net consistency only")
    face_count = len(geometry["arrays"]["face_left"])+len(geometry["arrays"]["boundary_cell"])
    if meta["face_evaluations"] != 2*face_count*meta["substeps"] or meta["actual_peak_rss_bytes"] > MAX_BYTES:
        raise ValueError("actual case work/RSS mismatch")
    water = arrays["depth_m"].reshape(intervals+1, -1)
    head = longitudinal < 5
    lake_reception = longitudinal >= 60
    middle = (longitudinal >= 30) & (longitudinal < 60)
    boundary_transfer = transfers["arrays"]["boundary_transfer_m3"]
    report = dict(case_id=case["case_id"], status="passed", substeps=meta["substeps"],
                  maximum_cell_mass_residual_m3=max(item["maximum_cell_mass_residual_m3"] for item in reports),
                  maximum_cell_momentum_residual=max(item["maximum_cell_momentum_residual"] for item in reports),
                  first_RK_hll_ssprk2_manning_cfl_verified=True, interval_mass_momentum_verified=True,
                  maximum_conservation_residual_m3=float(abs(volumes-volumes[0]-supplied+external).max()),
                  downstream_net_out_m3=float(boundary_transfer.sum()),
                  signed_interval_inflow_m3=float(np.maximum(-boundary_transfer, 0).sum()),
                  signed_interval_outflow_m3=float(np.maximum(boundary_transfer, 0).sum()),
                  headwater_volume_m3=(water[:, head].sum(axis=1)*spacing**2).tolist(),
                  taper_volume_m3=(water[:, middle].sum(axis=1)*spacing**2).tolist(),
                  lake_support_volume_m3=(water[:, lake_reception].sum(axis=1)*spacing**2).tolist(),
                  gross_directional_face_certified=False)
    compact = {"arrays": {key: arrays[key].copy() for key in ("time_s", "depth_m")},
               "internal": transfers["arrays"]["internal_transfer_m3"].copy(),
               "boundary": boundary_transfer.copy(), "metadata": meta}
    del state, transfers, witness
    gc.collect()
    return report, compact


def audit(index):
    for name, sha256 in index["code_sha256"].items():
        if file_sha256(ROOT/name) != sha256:
            raise ValueError("entry execution code pin changed")
    carrier_report, bed, geometry, forcing, longitudinal = audit_carrier(index)
    case_reports, comparisons = [], []
    for case_index in (0, 1):
        cases = sorted((case for case in index["cases"] if case.get("case_index") == case_index), key=lambda item: item["level"])
        levels = []
        for case in cases:
            report, compact = audit_case(case, bed, geometry, forcing, longitudinal)
            case_reports.append(report)
            levels.append(compact)
        if len(levels) == 2:
            coarse, fine = levels
            comparison = compare_saved_levels(coarse["arrays"], fine["arrays"], coarse["internal"], fine["internal"],
                        bed["metadata"]["spacing_m"], coarse["metadata"]["substeps"], fine["metadata"]["substeps"])
            denominator = float(abs(fine["boundary"].sum(axis=0)).sum())
            boundary_l1 = float(abs(coarse["boundary"].sum(axis=0)-fine["boundary"].sum(axis=0)).sum()/max(denominator, 1e-12))
            effective = fine["metadata"]["diagnostics"]["maximum_dt_s"] < coarse["metadata"]["diagnostics"]["maximum_dt_s"]
            comparison.update(case_name=forcing["metadata"]["case_names"][case_index], cumulative_boundary_net_relative_l1=boundary_l1,
                              maxdt_constraint_effective=effective, passed=comparison["passed"] and effective and boundary_l1 <= .01)
            comparisons.append(comparison)
        del levels
        gc.collect()
    complete = len(case_reports) == 4 and len(comparisons) == 2
    return dict(schema="td-entry-shallow-water-independent-audit-v1", status="passed",
                carrier=carrier_report, cases=case_reports, comparisons=comparisons,
                local_saved_hydraulics_verified=complete, time_refinement_verified=complete and all(item["passed"] for item in comparisons),
                gross_directional_time_convergence_verified=False, natural_outlet_verified=False,
                complete_river_hydraulics_verified=False, cross_domain_hydraulics_verified=False,
                actual_peak_rss_bytes=check_memory(), scope="real native background and accepted fine local engineering window; not full mainstem or natural mouth")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT/"verification/natural-river-network"):
        raise ValueError("new entry audit output required")
    result = audit(read_json({"path": str(args.input.resolve()), "sha256": args.sha256}))
    result["index_sha256"] = args.sha256
    result["audit_code_sha256"] = {name: file_sha256(ROOT/name) for name in (
        "tools/audit_td_entry_shallow_water.py", "tools/td_entry_saved_audit.py", "tools/single_domain_shallow_water_audit.py")}
    publish_bytes(output, (json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+"\n").encode())
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
