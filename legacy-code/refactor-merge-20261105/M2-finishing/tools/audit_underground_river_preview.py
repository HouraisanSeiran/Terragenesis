"""Cold audit of saved gallery solids and air paths, not complete river certification."""

import argparse
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import publish_bytes
from tools.hybrid_cave_saved_audit import (
    Solid, boolean_evidence, check_memory, checked_path, compare, digest,
    file_sha256, read, require, saved_air_route,
)
from tools.td_shared_channel_fine_saved_audit import check_identity

SCHEMA = "td-underground-preview-saved-evidence-audit-v1"
SOURCE_INDEX_SHA = "d7b971d28f07ff457776e0ce65ff8d583a4d1f70e50cbb3bdaad8e4909679fd6"
SOURCE_AUDIT_SHA = "703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364"
FLAGS = ("hydraulic_solved", "full_network_verified", "natural_outlet_certified")


def check_capabilities(record):
    require(set(record["capabilities"]) == set(FLAGS)
            and all(record["capabilities"][flag] is False for flag in FLAGS),
            "unverified capability promoted")


def check_saved_geometry(preview, rock, source_vdm):
    """Verify saved relationships before independently replaying bounded Boolean evidence."""
    check_identity(preview)
    require(preview["schema"] == "td-underground-river-preview-v1"
            and preview["status"] == "geometry_checked", "preview schema/status differs")
    check_capabilities(preview)
    require(preview["water"] is None, "unverified water supplied")
    checks = preview["geometry_checks"]
    require(checks["independent_audit_passed"] is False
            and checks["complete_portal_certified"] is False, "producer certification promoted")
    origin = np.asarray(preview["origin_xyz_m"], float)
    compare(origin, rock["local_origin_xyz_m"], "source rock origin", atol=0.)
    require(set(preview["meshes"]) == {"rock_before", "rock_after", "removed", "cutter"},
            "four saved solids required")
    for key in ("vertices_local_xyz_m", "triangles"):
        require(preview["meshes"]["rock_before"][key] == rock[key], "source rock changed")
    stations = preview["stations"]
    source_stations = source_vdm["stations"]
    require(9 <= len(stations) == len(source_stations) <= 33, "station census differs")
    require([s["station_id"] for s in stations] == [s["station_id"] for s in source_stations]
            and len({s["station_id"] for s in stations}) == len(stations), "station IDs differ")
    vdm = preview["vdm"]
    reference, displacement, derived = (np.asarray(vdm[key], float) for key in
        ("reference_local_xyz_m", "displacement_xyz_m", "derived_local_xyz_m"))
    expected_reference = np.concatenate([s["reference_ring_xyz_m"] for s in source_stations]) - origin
    compare(reference, expected_reference, "source VDM reference", atol=1e-10)
    compare(reference + displacement, derived, "VDM displacement", atol=1e-10)
    cutter = preview["meshes"]["cutter"]
    compare(derived, cutter["vertices_local_xyz_m"], "VDM cutter vertices", atol=1e-10)
    require(vdm["triangles"] == cutter["triangles"] == source_vdm["triangles"],
            "VDM sweep topology differs")
    rings = [np.asarray(s["ring_local_xyz_m"], float) for s in stations]
    for ring, source in zip(rings, source_stations):
        require(ring.shape == np.asarray(source["derived_ring_xyz_m"]).shape, "station ring shape differs")
    compare(np.concatenate(rings), derived, "stations and VDM", atol=1e-10)
    for ordinal in (0, -1):
        compare(rings[ordinal], np.asarray(source_stations[ordinal]["derived_ring_xyz_m"]) - origin,
                "immutable portal ring", atol=1e-10)
        compare(stations[ordinal]["origin_local_xyz_m"],
                np.asarray(source_stations[ordinal]["origin_xyz_m"]) - origin,
                "immutable portal origin", atol=1e-10)
    require([p["kind"] for p in preview["portals"]] == ["sink", "spring"], "portal census differs")
    for portal, ordinal in zip(preview["portals"], (0, -1)):
        compare(portal["position_local_xyz_m"], stations[ordinal]["origin_local_xyz_m"],
                "portal station position", atol=0.)
    centers = np.asarray([s["origin_local_xyz_m"] for s in stations], float)
    compare(preview["metrics"]["length_m"], math.fsum(np.linalg.norm(np.diff(centers, axis=0), axis=1)),
            "station length", atol=1e-8)
    path = np.asarray(checks["air_path_local_xyz_m"], float)
    require(path.shape == centers.shape, "air path census differs")
    compare(checks["air_path_xyz_m"], path + origin, "air path coordinate frame", atol=1e-10)
    compare(path[:, [0, 2]], centers[:, [0, 2]], "air path station binding", atol=1e-10)
    # Bind each saved waypoint to the actual deformed cross-section interior.
    for point, center, ring, source in zip(path, centers, rings, source_stations):
        floor = ring[:source["floor_vertex_count"]]
        offsets = (floor[:, [0, 2]] - center[[0, 2]]) @ np.asarray(source["transverse_unit_xz"])
        require(np.all(np.diff(offsets) > 0.) and offsets[0] <= 0. <= offsets[-1], "unordered station floor")
        require(np.interp(0., offsets, floor[:, 1]) < point[1] < ring[-2:, 1].min(),
                "air waypoint outside station interior")
    segments = checks["air_path_segments"]
    require(len(segments) == checks["air_segment_count"] == len(path) - 1, "air segment census differs")
    for ordinal, segment in enumerate(segments):
        compare(segment["from_xyz_m"], path[ordinal] + origin, "air segment start", atol=1e-10)
        compare(segment["to_xyz_m"], path[ordinal + 1] + origin, "air segment end", atol=1e-10)
        require(segment["rock_after_hits"] == [], "saved blocked air route")
    openings = checks["portal_opening_witnesses"]
    require(set(openings) == {"sink", "spring"}, "two opening witnesses required")
    ids = [s["station_id"] for s in stations]
    opening_segments = []
    for kind in ("sink", "spring"):
        witness = openings[kind]
        ordinal = ids.index(witness["station_id"])
        require(0 < ordinal < len(ids) // 2 if kind == "sink" else len(ids) // 2 < ordinal < len(ids) - 1,
                "opening attached to wrong portal half")
        compare(witness["inside_xyz_m"], path[ordinal] + origin, "opening air path binding", atol=1e-10)
        outside = np.asarray(witness["above_xyz_m"], float) - origin
        compare(outside[[0, 2]], path[ordinal, [0, 2]], "opening vertical probe", atol=1e-10)
        require(outside[1] > path[ordinal, 1], "opening probe not above interior")
        opening_segments.append((outside, path[ordinal]))
    solids = {name: Solid(mesh["vertices_local_xyz_m"], mesh["triangles"], name)
              for name, mesh in preview["meshes"].items()}
    boolean = boolean_evidence(solids["rock_before"], solids["cutter"], solids["rock_after"], solids["removed"])
    compare(preview["metrics"]["excavated_rock_m3"], boolean["excavated_volume_m3"],
            "excavated material", atol=1e-7, rtol=1e-9)
    residual = boolean["rock_volume_m3"] - boolean["actual_rock_volume_m3"] - boolean["excavated_volume_m3"]
    compare(preview["metrics"]["material_residual_m3"], residual, "material residual", atol=1e-7)
    air = saved_air_route(solids["rock_before"], solids["cutter"], solids["rock_after"], path, opening_segments)
    return {"actual_boolean": boolean, "actual_air_route": air,
            "source_rock_unchanged": True, "immutable_endpoint_rings_verified": True,
            "saved_vdm_station_cutter_binding_verified": True}


def audit(index_pin):
    started = time.perf_counter()
    index = read(index_pin)
    require(index["schema"] == "td-underground-river-preparation-v1"
            and index["status"] == "geometry_checked" and index["rejection_reasons"] == [],
            "successful preparation required")
    check_capabilities(index)
    preview = read(index["preview"])
    require(preview["parameters"] == index["parameters"] and preview["source_pins"] == index["parents"]
            and preview["metrics"] == index["metrics"], "index/preview linkage differs")
    parents = index["parents"]
    require(parents["geometry03_index"]["sha256"] == SOURCE_INDEX_SHA
            and parents["geometry03_audit"]["sha256"] == SOURCE_AUDIT_SHA, "fixed source pins differ")
    source_index, source_audit = read(parents["geometry03_index"]), read(parents["geometry03_audit"])
    require(source_audit["status"] == "passed" and not source_audit.get("errors")
            and source_audit["geometry_sha256"] == source_index["geometry"]["sha256"], "source audit linkage differs")
    require(parents["geometry03"] == source_index["geometry"] and parents["graph"] == source_index["graph"]
            and parents["rock_before"] == source_index["artifacts"]["rock_before"]
            and parents["vdm"] == source_index["artifacts"]["vdm"], "source artifacts substituted")
    for pin in parents.values():
        checked_path(pin)
    evidence = check_saved_geometry(preview, read(parents["rock_before"]), read(parents["vdm"]))
    result = {"schema": SCHEMA, "status": "passed", "index": index_pin, "preview": index["preview"],
              "parents": parents, "evidence": evidence, "capabilities": {key: False for key in FLAGS},
              "scope": "saved solids, material, fixed endpoints, VDM binding and air polyline only",
              "continuous_roof_cover_verified": False, "complete_portal_certified": False,
              "seed_recipe_replayed": False, "water": None,
              "resource": {"solver_calls": 0, "producer_calls": 0, "elapsed_s": time.perf_counter() - started,
                           "peak_rss_bytes": check_memory()},
              "audit_code_sha256": {name: file_sha256(ROOT / name) for name in (
                  "tools/audit_underground_river_preview.py", "tools/hybrid_cave_saved_audit.py",
                  "tools/td_shared_channel_fine_saved_audit.py")}}
    result["identity_sha256"] = digest(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / "verification") and not output.exists(), "new verification file required")
    pin = {"path": str(args.index.resolve()), "sha256": args.index_sha256}
    try:
        result = audit(pin)
    except (ValueError, KeyError, TypeError, IndexError, OSError) as error:
        result = {"schema": SCHEMA, "status": "refused", "index": pin, "errors": [str(error)]}
        result["identity_sha256"] = digest(result)
    publish_bytes(output, json.dumps(result, sort_keys=True, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({"status": result["status"], "output": str(output), "errors": result.get("errors", [])}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
