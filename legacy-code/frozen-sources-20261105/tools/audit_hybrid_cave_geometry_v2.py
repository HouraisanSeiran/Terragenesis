"""Version 2 cold audit binding the explicit Python-bool geometry revision.

No generator or hydraulic solver is imported or called. Mesh64 Boolean replay
is restricted to the bounded saved local solids. CLI accepts --geometry,
--geometry-sha256, --output NEW_FILE, --audit-schema.
"""

import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.hybrid_cave_saved_audit import (
    MANIFOLD_DIRECTORY, MAX_BYTES, MAX_RSS, IndependentBed, Solid,
    audit_hydraulic_sections, audit_source_sampling, audit_surface_attachments,
    audit_typed_graph, audit_vdm, boolean_evidence, check_memory, checked_path,
    compare, digest, file_sha256, read, require, saved_air_route)

AUDIT_SCHEMA = "td-hybrid-cave-geometry-independent-audit-v1"
FROZEN_CODE = {
    "terrain_pipeline/hybrid_cave_geometry.py": "dd839163651239ba358b74b79e41acf6831487a6638e980483f9825243311b55",
    "tools/prepare_hybrid_cave_geometry.py": "104d525135e081d14c5d0c1728d70d47391bf4707375c6d14ca0928a75e8e6a9",
    "tests/test_hybrid_cave_geometry.py": "98c8c229432c0e5a4819d6d8ba482da722b45a825c3e43d73614e30b9f8d4b27"}
POLICY = {"version": "local-rock-boolean-multichart-v1",
    "terrain": "original_native_bilinear_minus_independently_passed_saved_affine_cut_fans",
    "solid": "sampled_piecewise_planar_top_closed_sides_bottom_not_native_exact_not_fine_replacement",
    "excavation": "Mesh64_local_origin_closed_rock_minus_closed_derived_cutter_actual_volume",
    "geology": "generated_hermite_route_sine_squared_burial_not_surveyed",
    "portals": "immutable_complete_native_floor_with_engineered_ceiling_surface_ramp_openings",
    "vdm": "new_transverse_and_vertical_multichart_reference_plus_displacement_not_old_metric_vdm",
    "water": "not_generated_solid_banks_distinct_from_free_water",
    "protection": "unknown_protected_unselected_or_wet_native_support_refused_without_clamping",
    "hydraulics": "final_actual_ring_storage_sections_engineering_pressure_slot_no_solver"}


def audit(geometry_pin):
    started = time.perf_counter()
    geometry = read(geometry_pin)
    require(geometry["schema"] == "td-hybrid-river-geometry-v1" and geometry["status"] == "candidate"
            and geometry["rejection_reasons"] == [] and geometry["sampled_not_native_exact"] is True
            and geometry["fine15_replaced"] is False, "candidate local sampled geometry scope differs")
    require(geometry["policy"] == POLICY and geometry["policy_identity_sha256"] == digest(POLICY)
            and geometry["parameters_identity_sha256"] == digest(geometry["parameters"]), "geometry policy/parameters identity differs")
    for flag in ("independent_audit_passed", "hydraulic_solved", "hydraulic_ready", "free_water_surface_generated", "natural_outlet_certified", "full_network_verified"):
        require(geometry[flag] is False, "geometry prematurely promoted capability: "+flag)
    for pin in geometry["inputs"].values():
        checked_path(pin)
    for code in (geometry["code_sha256"], geometry["readonly_dependency_code_sha256"]):
        for name, sha in code.items():
            checked_path({"path": str(ROOT/name), "sha256": sha})
    require(geometry["code_sha256"] == FROZEN_CODE, "frozen actual geometry implementation differs")
    require(geometry["runtime"]["manifold3d"] == "3.5.4", "geometry not frozen Mesh64 runtime")
    parameters = geometry["parameters"]
    require(.175 <= parameters["rock_spacing_m"] <= 2. and type(parameters["stations"]) is int
            and 9 <= parameters["stations"] <= 33
            and all(math.isfinite(value) and value > 0 for value in parameters.values()), "local engineering parameter bounds differ")
    graph = read(geometry["inputs"]["graph"])
    require(graph["identity_sha256"] == geometry["graph_identity_sha256"]
            and all(geometry["inputs"].get(key) == pin for key, pin in graph["inputs"].items()), "geometry graph parent binding differs")
    graph_result, portals, native = audit_typed_graph(graph)
    compact = read(graph["inputs"]["fine_compact_fans"])
    bed = IndependentBed(native, compact)
    require(set(geometry["mesh_pins"]) == {"rock_before", "cutter", "rock_after", "removed"}, "solid mesh pin census differs")
    records, solids = {}, {}
    origin = None
    peak = check_memory()
    for name, pin in geometry["mesh_pins"].items():
        record = read(pin)
        require(record["schema"] == "td-hybrid-local-solid-mesh-v1" and record["role"] == name
                and record["sampled_not_native_exact"] is True, "saved solid role/schema/scope differs")
        local_origin = np.asarray(record["local_origin_xyz_m"], float)
        require(local_origin.shape == (3,) and np.isfinite(local_origin).all(), "invalid local origin")
        if origin is None:
            origin = local_origin
        require(np.array_equal(origin, local_origin), "Boolean solid local origins differ")
        solid = Solid(record["vertices_local_xyz_m"], record["triangles"], name)
        compare(record["signed_volume_m3"], solid.signed_volume, "saved signed solid volume", atol=1e-7, rtol=1e-9)
        records[name], solids[name] = record, solid
        peak = max(peak, check_memory())
    compare(origin, portals["sink"]["node"]["xyz_m"], "fixed local origin at canonical sink")
    vdm = read(geometry["vdm_pin"])
    vdm_result = audit_vdm(vdm, solids["cutter"], origin, portals)
    require(len(vdm["stations"]) == parameters["stations"], "explicit station parameter differs")
    sampling = read(geometry["source_sampling_pin"])
    source_result = audit_source_sampling(sampling, solids["rock_before"], origin, bed, parameters["rock_spacing_m"])
    boolean = boolean_evidence(solids["rock_before"], solids["cutter"], solids["rock_after"], solids["removed"])
    actual_material = geometry["actual_solid_material"]
    for key, value in (("rock_before_m3", boolean["rock_volume_m3"]), ("rock_after_m3", boolean["actual_rock_volume_m3"]),
                        ("excavated_rock_m3", boolean["excavated_volume_m3"]), ("exported_excavated_rock_m3", boolean["excavated_volume_m3"]),
                        ("signed_residual_m3", boolean["rock_volume_m3"]-boolean["actual_rock_volume_m3"]-boolean["excavated_volume_m3"])):
        compare(actual_material[key], value, "actual rock material "+key, atol=1e-7, rtol=1e-9)
    require(actual_material["fill_rock_m3"] == 0., "actual rock adds fill")
    attachment_record = read(geometry["surface_attachments_pin"])
    attachments = audit_surface_attachments(attachment_record, geometry, portals, bed, compact)
    sections = audit_hydraulic_sections(geometry, vdm, solids["rock_before"], sampling, origin, bed)
    path = np.asarray(geometry["air_path_xyz_m"], float)
    require(path.shape == (len(vdm["stations"]), 3), "saved station air path census differs")
    for point, station in zip(path, vdm["stations"]):
        station_origin = np.asarray(station["origin_xyz_m"])
        compare(point[[0, 2]], station_origin[[0, 2]], "air route references actual VDM station horizontal position")
        floor = np.asarray(station["derived_ring_xyz_m"])[:station["floor_vertex_count"]]
        offsets = (floor[:, [0, 2]]-station_origin[[0, 2]])@np.asarray(station["transverse_unit_xz"])
        require(np.all(np.diff(offsets) > 0.), "air station floor not ordered")
        require(np.interp(0., offsets, floor[:, 1]) < point[1] < min(np.asarray(station["derived_ring_xyz_m"])[-2:, 1]), "saved air station not in actual profile interior")
    segments = geometry["air_path_segments"]
    require(len(segments) == len(path)-1, "saved air route segments omitted")
    for ordinal, segment in enumerate(segments):
        compare(segment["from_xyz_m"], path[ordinal], "air segment origin")
        compare(segment["to_xyz_m"], path[ordinal+1], "air segment target")
        require(segment["rock_after_hits"] == [], "generator reported blocked air segment")
    openings = geometry["portal_opening_witnesses"]
    require(set(openings) == {"sink", "spring"}, "portal aperture witness census differs")
    opening_segments = []
    station_ids = [station["station_id"] for station in vdm["stations"]]
    for kind, endpoint in (("sink", 0), ("spring", -1)):
        portal_binding = geometry["portal_bindings"][kind]
        require(portal_binding["port_arc_id"] == portals[kind]["port"]["arc_id"]
                and portal_binding["port_identity_sha256"] == portals[kind]["port"]["identity_sha256"]
                and portal_binding["immutable_station_id"] == vdm["stations"][endpoint]["station_id"]
                and portal_binding["full_native_floor_preserved"] is True and portal_binding["hydraulic_boundary_certified"] is False,
                "actual canonical portal binding differs")
        require(geometry["portal_sections"][kind]["pieces"] == portals[kind]["pieces"]
                and geometry["portal_sections"][kind]["canonical_profile"] == portals[kind]["port"]["profile"], "actual portal complete native function differs")
        witness = openings[kind]
        require(witness["station_id"] in station_ids and witness["opening_kind"] == "actual_terrain_top_ramp_aperture_not_entire_planar_port_cap"
                and witness["rock_before_hits"] and witness["rock_after_hits"] == [], "actual ramp aperture incorrectly identified")
        index = station_ids.index(witness["station_id"])
        require(0 < index < len(station_ids)//2 if kind == "sink" else len(station_ids)//2 < index < len(station_ids)-1, "aperture associated with wrong portal half")
        compare(witness["inside_xyz_m"], path[index], "aperture joins saved station air route")
        point = np.asarray(witness["inside_xyz_m"])
        bed.verify(point[[0, 2]], witness["source_bed_witness"])
        require(witness["above_xyz_m"][0] == point[0] and witness["above_xyz_m"][2] == point[2]
                and witness["above_xyz_m"][1] > witness["source_bed_witness"]["derived_bed_m"] > point[1], "aperture exterior/source-bed ordering differs")
        opening_segments.append((np.asarray(witness["above_xyz_m"])-origin, point-origin))
    air = saved_air_route(solids["rock_before"], solids["cutter"], solids["rock_after"], path-origin, opening_segments)
    distances = np.linalg.norm(np.diff(np.asarray([station["origin_xyz_m"] for station in vdm["stations"]]), axis=0), axis=1)
    compare(geometry["conduit_length_m"], math.fsum(distances.tolist()), "saved conduit station length")
    resource = geometry["resource"]
    require(resource["top_grid_count"] == sampling["top_vertex_count"] <= resource["hard_grid_count"] == 300000
            and resource["hard_rss_bytes"] == MAX_RSS and resource["hard_file_bytes"] == MAX_BYTES, "explicit local geometry resources differ")
    result = {"schema": AUDIT_SCHEMA, "audit_implementation_version": "generator-bool-boundary-v2", "status": "passed", "errors": [],
        "geometry": geometry_pin, "geometry_sha256": geometry_pin["sha256"], "geometry_identity_sha256": geometry["identity_sha256"],
        "graph_identity_sha256": graph["identity_sha256"], "inputs": geometry["inputs"], "mesh_pins": geometry["mesh_pins"],
        "vdm_pin": geometry["vdm_pin"], "source_sampling_pin": geometry["source_sampling_pin"], "surface_attachments_pin": geometry["surface_attachments_pin"],
        "policy_identity_sha256": geometry["policy_identity_sha256"], "parameters_identity_sha256": geometry["parameters_identity_sha256"],
        "typed_graph": graph_result, "source_sampling": source_result, "vdm": vdm_result,
        "actual_boolean": boolean, "surface_attachments": attachments, "actual_air_route": air,
        "actual_hydraulic_sections_verified": True, "actual_portal_connections_verified": True,
        "section_classification": sections, "portal_scope": "two actual terrain ramp apertures tied to immutable canonical floors, not complete planar cap/whole-bank opening certification",
        "hydraulic_exchange_scope": "actual open-ramp to covered-core transitions, not automatically the canonical midpoint portals",
        "source_native_function_verified_at_saved_samples": True, "sampled_top_not_native_exact": True,
        "hydraulic_solved": False, "three_dimensional_flow_solved": False, "natural_outlet_certified": False,
        "full_network_verified": False, "fine15_replaced": False, "free_water_surface_generated": False,
        "scope": "bounded sampled local rock Boolean, actual openings, saved VDM and explicit open/closed engineering sections only",
        "runtime_pins": {str(path.resolve()): file_sha256(path) for path in MANIFOLD_DIRECTORY.glob("*.pyd")},
        "resource": {"actual_peak_audit_rss_bytes": max(peak, check_memory()), "max_rss_bytes": MAX_RSS,
            "max_file_bytes": MAX_BYTES, "max_vertices_per_solid": 100000, "max_faces_per_solid": 200000,
            "solver_calls": 0, "elapsed_s": time.perf_counter()-started}}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--geometry-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-schema", default=AUDIT_SCHEMA, choices=[AUDIT_SCHEMA])
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT/"verification"), "new verification audit file required")
    result = audit({"path": str(args.geometry.resolve()), "sha256": args.geometry_sha256})
    result["audit_code_sha256"] = {name: file_sha256(ROOT/name) for name in (
        "tools/audit_hybrid_cave_geometry_v2.py", "tools/hybrid_cave_saved_audit.py", "tests/test_hybrid_cave_saved_audit.py",
        "tools/audit_td_shared_channel_fine.py", "tools/td_shared_channel_fine_saved_audit.py")}
    result["identity_sha256"] = digest(result)
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(payload) <= MAX_BYTES, "audit exceeds 64MiB output budget")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(json.dumps({"status": result["status"], "actual_boolean": result["actual_boolean"], "section_classification": result["section_classification"]}))


if __name__ == "__main__":
    main()
