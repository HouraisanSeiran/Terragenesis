"""Export pinned geometry03 bytes only; CLI: --output NEW_VERIFICATION_DIRECTORY."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "verification" / "natural-river-network"
MAX_BYTES = 64 * 1024**2
MESH_NAMES = ("rock_before", "cutter", "rock_after", "removed")
FLAGS = dict(hydraulic_solved=False, three_dimensional_flow_solved=False,
             full_network_verified=False, natural_outlet_certified=False)
FIXED_PINS = {
    "geometry": {"path": str(BASE / "hybrid-cave-geometry-20261006-03" / "geometry.json"),
                 "sha256": "3ba55abbb06f6f4cd8ac5a65dba2de362df958acf48843adcef2351bd465f593"},
    "review": {"path": str(BASE / "hybrid-cave-review-20261006-01" / "review.json"),
               "sha256": "53be2917160175d499f0c3eb231c62a73d9b5afdb09cf2a9bfe7004beb73c049"},
    "graph": {"path": str(BASE / "hybrid-river-graph-20261006-01" / "graph.json"),
              "sha256": "279d632e6f471c2629a37d7d6954adbcb734be19278e009eb352c9852593846a"},
    "audit": {"path": str(BASE / "hybrid-cave-geometry-20261006-03" / "independent-audit-v2.json"),
              "sha256": "703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364"},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(record):
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_identity(record):
    return hashlib.sha256(encoded({key: value for key, value in record.items()
                                  if key != "identity_sha256"})).hexdigest()


def unique_object(pairs):
    record = {}
    for key, value in pairs:
        require(key not in record, "duplicate JSON key: " + key)
        record[key] = value
    return record


def reject_constant(value):
    raise ValueError("nonfinite JSON constant: " + value)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_path(pin):
    path = Path(pin["path"])
    require(path.is_absolute(), "absolute source pin required")
    require(path.is_file() and path.stat().st_size <= MAX_BYTES, "missing/oversized source file")
    require(sha256_file(path) == pin["sha256"], "source SHA256 mismatch: " + str(path))
    if "bytes" in pin:
        require(path.stat().st_size == pin["bytes"], "source byte count mismatch")
    return path


def read_record(pin, schema, *, sealed=True):
    payload = checked_path(pin).read_bytes()
    require(hashlib.sha256(payload).hexdigest() == pin["sha256"], "source changed during read")
    record = json.loads(payload, object_pairs_hook=unique_object, parse_constant=reject_constant)
    require(isinstance(record, dict) and record.get("schema") == schema, "unexpected source schema")
    if sealed:
        require(record.get("identity_sha256") == content_identity(record), "content identity mismatch")
    if "identity_sha256" in pin:
        require(record.get("identity_sha256") == pin["identity_sha256"], "external identity mismatch")
    return record, payload


def same_pin(actual, expected):
    require(Path(actual["path"]).resolve() == Path(expected["path"]).resolve()
            and actual["sha256"] == expected["sha256"], "source pin binding mismatch")
    for key in ("identity_sha256", "bytes"):
        if key in actual and key in expected:
            require(actual[key] == expected[key], "source pin " + key + " mismatch")


def validate_vectors(points):
    require(isinstance(points, list) and bool(points), "missing XYZ vectors")
    for point in points:
        require(isinstance(point, list) and len(point) == 3
                and all(type(value) in (int, float) and math.isfinite(value) for value in point),
                "invalid finite XYZ vector")


def validate_mesh(mesh, name):
    require(mesh["role"] == name and mesh["sampled_not_native_exact"] is True,
            "mesh role/sampling semantics mismatch")
    validate_vectors([mesh["local_origin_xyz_m"]])
    validate_vectors(mesh["vertices_local_xyz_m"])
    require(len(mesh["vertices_local_xyz_m"]) <= 100000, "mesh vertex budget exceeded")
    triangles = mesh["triangles"]
    require(isinstance(triangles, list) and 0 < len(triangles) <= 200000, "mesh triangle budget exceeded")
    for triangle in triangles:
        require(isinstance(triangle, list) and len(triangle) == 3
                and all(type(index) is int and 0 <= index < len(mesh["vertices_local_xyz_m"])
                        for index in triangle) and len(set(triangle)) == 3, "invalid triangle indices")
    require(type(mesh["signed_volume_m3"]) in (int, float)
            and math.isfinite(mesh["signed_volume_m3"]), "invalid saved solid volume")


def load_inputs(pins):
    records, payloads = {}, {}
    schemas = {"geometry": "td-hybrid-river-geometry-v1", "review": "td-hybrid-cave-review-v1",
               "graph": "td-hybrid-river-graph-v1", "audit": "td-hybrid-cave-geometry-independent-audit-v1"}
    for name, schema in schemas.items():
        records[name], payloads[name + ".json"] = read_record(pins[name], schema, sealed=name != "review")
    geometry, review, graph, audit = (records[name] for name in ("geometry", "review", "graph", "audit"))
    require(geometry["status"] == "candidate" and geometry["rejection_reasons"] == [], "refused geometry")
    same_pin(geometry["inputs"]["graph"], pins["graph"])
    require(geometry["graph_identity_sha256"] == graph["identity_sha256"]
            == review["graph_identity_sha256"] == audit["graph_identity_sha256"], "graph identity binding mismatch")
    require(geometry["identity_sha256"] == review["geometry_identity_sha256"]
            == audit["geometry_identity_sha256"], "geometry identity binding mismatch")
    same_pin(audit["geometry"], pins["geometry"])
    require(audit["geometry_sha256"] == pins["geometry"]["sha256"], "audit geometry SHA binding mismatch")
    require(audit["status"] == "passed" and audit["errors"] == []
            and audit["actual_hydraulic_sections_verified"] is True
            and audit["actual_portal_connections_verified"] is True, "independent audit not passed")
    binding = review["independent_audit_reference"]
    require(binding["binding_status"] == "matched" and binding["referenced_status"] == "passed"
            and binding["binding_failures"] == [] and binding["errors"] == [], "review audit binding not passed")
    for key in ("inputs", "mesh_pins", "vdm_pin", "source_sampling_pin", "surface_attachments_pin",
                "policy_identity_sha256", "parameters_identity_sha256"):
        require(audit[key] == geometry[key], "audit geometry binding mismatch: " + key)
    require(all(geometry["inputs"].get(key) == pin for key, pin in graph["inputs"].items()),
            "graph parent binding mismatch")
    expected_review_pins = {"geometry": pins["geometry"], "graph": pins["graph"], "audit": pins["audit"]}
    for key, pin in expected_review_pins.items():
        same_pin(review["pins"][key], pin)
    for review_key, geometry_key in (("inputs", "inputs"), ("meshes", "mesh_pins"), ("vdm", "vdm_pin"),
                                     ("source_sampling", "source_sampling_pin"),
                                     ("surface_attachments", "surface_attachments_pin")):
        require(review["pins"][review_key] == geometry[geometry_key], "review source binding mismatch")
    for key in FLAGS:
        require(review.get(key) is False and audit.get(key) is False, "unexpected certified capability: " + key)
        if key in geometry:
            require(geometry[key] is False, "geometry capability mismatch")
    dependencies = list(pins.values()) + list(geometry["inputs"].values())
    require(set(geometry["mesh_pins"]) == set(MESH_NAMES), "unexpected mesh roles")
    for name in MESH_NAMES:
        pin = geometry["mesh_pins"][name]
        mesh, payloads[name + ".json"] = read_record(pin, "td-hybrid-local-solid-mesh-v1")
        validate_mesh(mesh, name)
        require(mesh == review["meshes"][name], "review mesh differs from saved mesh")
        dependencies.append(pin)
    for name, schema in (("vdm", "td-hybrid-multichart-vdm-v1"),
                         ("surface_attachments", "td-hybrid-surface-attachments-v1"),
                         ("source_sampling", "td-hybrid-rock-source-sampling-v1")):
        pin = geometry[name + "_pin"]
        records[name], payloads[name + ".json"] = read_record(pin, schema)
        dependencies.append(pin)
    vdm = records["vdm"]
    require(len(vdm["stations"]) == 17 and vdm["stations"] == review["stations"], "17 saved stations required")
    for station in vdm["stations"]:
        for key in ("reference_ring_xyz_m", "displacement_ring_xyz_m", "derived_ring_xyz_m"):
            validate_vectors(station[key])
        reference, displacement, derived = (station[key] for key in (
            "reference_ring_xyz_m", "displacement_ring_xyz_m", "derived_ring_xyz_m"))
        require(len(reference) == len(displacement) == len(derived), "VDM ring shape mismatch")
        require(all(math.isclose(base + delta, result, rel_tol=0., abs_tol=1e-9)
                    for before, offset, after in zip(reference, displacement, derived)
                    for base, delta, result in zip(before, offset, after)), "VDM reference/displacement binding mismatch")
    require(len(geometry["hydraulic_cells"]) == 19
            and review["hydraulic_cells"] == geometry["hydraulic_cells"], "19 saved cells required")
    require(records["surface_attachments"]["attachments"] == review["surface_attachments"],
            "saved attachment binding mismatch")
    require(review["actual_closed_core_station_indices"] == geometry["actual_closed_core_station_indices"],
            "closed core binding mismatch")
    for pin in dependencies:
        checked_path(pin)
    return records, payloads, dependencies


def write_synced(path, payload):
    require(len(payload) <= MAX_BYTES, "output file exceeds 64MiB")
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def export(output, *, pins=None):
    output = Path(output).absolute()
    require(not output.exists(), "new output directory required")
    records, payloads, dependencies = load_inputs(FIXED_PINS if pins is None else pins)
    geometry, review = records["geometry"], records["review"]
    manifest = {"schema": "td-vdm-geometry-io-review-v1", "status": "saved_geometry_review",
                "coordinates": review["coordinates"], "water": None, "flags": FLAGS.copy(),
                "geometry_identity_sha256": geometry["identity_sha256"],
                "graph_identity_sha256": records["graph"]["identity_sha256"],
                "vdm_identity_sha256": records["vdm"]["identity_sha256"],
                "independent_audit_reference": review["independent_audit_reference"],
                "source_pins": dependencies, "station_count": 17, "hydraulic_cell_count": 19,
                "layers": {name: name + ".json" for name in MESH_NAMES},
                "vdm": "vdm.json", "stations": {"path": "vdm.json", "field": "stations"},
                "hydraulic_cells": {"path": "geometry.json", "field": "hydraulic_cells"},
                "surface_attachments": "surface_attachments.json", "graph": "graph.json",
                "geometry": "geometry.json", "review": "review.json", "audit": "audit.json",
                "limitations": review["limitations"],
                "files": {name: {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
                          for name, payload in payloads.items()}}
    manifest.update(FLAGS)
    manifest["identity_sha256"] = content_identity(manifest)
    require(output.parent.is_dir(), "existing output parent required")
    staging = Path(tempfile.mkdtemp(prefix="." + output.name + "-", dir=output.parent))
    try:
        for name, payload in payloads.items():
            write_synced(staging / name, payload)
        write_synced(staging / "manifest.json", encoded(manifest))
        for pin in dependencies:
            checked_path(pin)
        require(not output.exists(), "output appeared during export")
        os.rename(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    require(destination.is_relative_to((ROOT / "verification").resolve()), "output must be in verification")
    manifest = export(destination)
    print(json.dumps({"output": str(destination), "identity_sha256": manifest["identity_sha256"],
                      "status": manifest["status"]}))


if __name__ == "__main__":
    main()
