"""Pinned stage-one saved geometry adapter; one authenticated frame in memory."""

import os
from pathlib import Path
import sys
import threading

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[variable] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, load_bundle
from terrain_pipeline.single_domain_surface_consumer import load_consumer_manifest
from terrain_pipeline.surface_adaptive_water import load_consumer_adaptive_frame
from terrain_pipeline.fine_domain_mosaic import partition_saved_window

ACCEPTANCE = ROOT / "verification/single-domain-stage/acceptance-20261004-03/acceptance-index.json"
ACCEPTANCE_SHA = "74f4b419f7341990e254c216cd2d37798f587abbabde6bc44ed507e92629971c"
PACKAGES = {
    "amr": ("adaptive-amr-20261004-03", "170060df9b7e2ef08fed9cc1c54f586731c3644639ea0fb94444c007fc86e078"),
    "native": ("native-20261004-01", "c38262461a1cf5b6531f4463a87fdd0df14a026c02eeb6f27b04bac779d13e2a"),
    "uniform": ("fine-v7-20261004-01", "11d2d8dc87d1838487c0383bfd35fc9dd328ef09d0c2460f013f88dbcdeb5b76"),
}
LOCK = threading.RLock()
CONTEXTS = {}
CACHED = None


def context(package):
    if package not in PACKAGES:
        raise ValueError("unknown saved package")
    if file_sha256(ACCEPTANCE) != ACCEPTANCE_SHA:
        raise ValueError("stage-one acceptance changed")
    directory, digest = PACKAGES[package]
    path = ROOT / "verification/single-domain-consumer" / directory / "manifest.json"
    if package not in CONTEXTS:
        CONTEXTS[package] = load_consumer_manifest(path, expected_sha256=digest)
    result = CONTEXTS[package]
    if file_sha256(path) != digest:
        raise ValueError("saved manifest changed")
    return result


def catalog():
    with LOCK:
        packages = {}
        for key in PACKAGES:
            item = context(key)
            manifest = item["manifest"]
            packages[key] = dict(backend=manifest["backend"], evidence_status=manifest["evidence_status"],
                manifest_sha256=item["expected_sha256"], scenarios={name: dict(
                    times_s=[frame["time_s"] for frame in scenario["frames"]],
                    initial_kind=scenario.get("initial_kind"), root_spacing_m=scenario.get("root_spacing_m"))
                    for name, scenario in manifest["scenarios"].items()})
        return dict(schema="saved-surface-catalog-v1", packages=packages,
            acceptance_sha256=ACCEPTANCE_SHA, bounded_engineering_stage_accepted=True,
            hydraulic_ready=False, natural_outlet_verified=False, publishable=False)


def _load(item, name):
    record = next(value for value in item["manifest"]["artifacts"] if value["path"] == name)
    bundle = load_bundle(item["allowlist"][name], expected_sha256=record["sha256"],
                         max_bytes=268435456, validator=lambda value: True)
    if bundle["identity_sha256"] != record["identity_sha256"]:
        raise ValueError("saved payload identity changed")
    return bundle


def frame(package, scenario, index):
    global CACHED
    item = context(package)
    declared = item["manifest"]["scenarios"].get(scenario)
    if declared is None or type(index) is not int or not 0 <= index < len(declared["frames"]):
        raise ValueError("saved scenario/frame outside allowlist")
    entry = declared["frames"][index]
    names = [declared["geometry"], entry["artifact"]]
    if package != "native":
        names.append(declared["evidence"]["states"])
    if package == "amr":
        names.extend([entry["snapshot"], entry["adaptive_geometry"]])
    for name in names:
        record = next(value for value in item["manifest"]["artifacts"] if value["path"] == name)
        if file_sha256(item["allowlist"][name]) != record["sha256"]:
            raise ValueError("saved payload changed")
    key = package, scenario, index
    if CACHED is not None and CACHED[0] == key:
        return CACHED[1]
    CACHED = None
    if package == "amr":
        saved = load_consumer_adaptive_frame(item, scenario=scenario, frame_index=index)
        bundle, bed = saved["frame"], saved["bed"]
        leaf = saved["snapshot"]["arrays"]
    else:
        bundle, bed = _load(item, entry["artifact"]), _load(item, declared["geometry"])
        if package == "native":
            from terrain_pipeline.single_domain_surface_geometry import validate_water_frame
            validate_water_frame(bundle)
            if bundle["metadata"]["geometry_identity"] != bed["identity_sha256"]:
                raise ValueError("native bed binding mismatch")
        else:
            from terrain_pipeline.single_domain_fine_geometry import validate_fine_water_frame
            validate_fine_water_frame(bundle)
            if bundle["metadata"]["bed_identity"] != bed["identity_sha256"]:
                raise ValueError("uniform bed binding mismatch")
        leaf = None
    arrays, metadata = bundle["arrays"], bundle["metadata"]
    if metadata["time_s"] != entry["time_s"]:
        raise ValueError("saved frame time mismatch")
    vertices = arrays["bed_vertices_xyz_m"]
    origin = np.array([vertices[:, 0].min(), vertices[:, 1].min(), vertices[:, 2].min()])
    buffers = {}
    for name in ("bed", "water"):
        buffers[name + "_vertices"] = np.ascontiguousarray(arrays[name + "_vertices_xyz_m"] - origin, dtype="<f4")
        buffers[name + "_triangles"] = np.ascontiguousarray(arrays[name + "_triangles"], dtype="<u4")
    buffers["nodes"] = np.ascontiguousarray(arrays["node_xyz_m"] - origin, dtype="<f4")
    buffers["edges"] = np.ascontiguousarray(arrays["edge_node_indices"], dtype="<u4")
    depth = arrays["native_depth_m"] if package == "native" else arrays["cell_depth_m"]
    if package == "native":
        depth = depth.reshape(metadata["geometry_metadata"]["grid_shape"])
    spacing = float(metadata["geometry_metadata"].get("spacing_m", 30))
    buffers["depth"] = np.ascontiguousarray(depth, dtype="<f4")
    buffers["bed_height"] = np.ascontiguousarray(
        arrays["height_m"] if package == "native" else arrays["H2_m"], dtype="<f4")
    if leaf is not None:
        for name in ("leaf_row", "leaf_column", "leaf_spacing_m"):
            buffers[name] = np.ascontiguousarray(leaf[name], dtype="<u4")
        for label, cuts in (("central", (120, 120)), ("mixed", (168, 16))):
            mosaic = partition_saved_window(arrays["H2_m"], depth, leaf["canonical_owner"],
                row_cuts=(cuts[0],), column_cuts=(cuts[1],), version=bundle["identity_sha256"])
            corners = arrays["cell_corner_vertex_ids"]
            first = corners[mosaic["first_cell"]]
            second = corners[mosaic["second_cell"]]
            shared = first[np.any(first[:, :, None] == second[:, None, :], axis=2)].reshape(-1, 2)
            buffers["domain_" + label] = np.ascontiguousarray(arrays["water_vertices_xyz_m"][shared].reshape(-1, 3)-origin, dtype="<f4")
    ledger = None
    if package != "native":
        ledger = _load(item, declared["evidence"]["states"])["arrays"]["ledger"].tolist()
    descriptor = dict(schema="saved-surface-frame-v1", package=package, scenario=scenario, index=index,
        identity=bundle["identity_sha256"], time_s=entry["time_s"], origin_xyz_m=origin.tolist(),
        bed_identity=bed["identity_sha256"], manifest_sha256=item["expected_sha256"],
        depth_shape=list(depth.shape), spacing_m=spacing,
        status="diagnostic_uniform_spatial_failure" if package == "uniform" else "accepted_bounded_engineering",
        volume_m3=float(np.sum(depth) * spacing**2),
        wet_cells=int(np.count_nonzero(depth > 0)), ledger=ledger,
        leaf_counts={str(size): int(np.count_nonzero(leaf["leaf_spacing_m"] == size)) for size in (1, 2, 4)} if leaf is not None else {},
        domain_partitions={"central": dict(row_cut=120,column_cut=120), "mixed": dict(row_cut=168,column_cut=16)} if leaf is not None else {},
        representation="native disconnected cell water" if package == "native" else "conservative fan; centre depth may be three times cell mean",
        full_resolution_geometry=True, solver_advanced=False, hydraulic_ready=False,
        natural_outlet_verified=False, publishable=False,
        arrays={name: dict(dtype=str(value.dtype), shape=list(value.shape), bytes=value.nbytes,
            url=f"/api/saved/array/{package}/{scenario}/{index}/{name}") for name, value in buffers.items()})
    CACHED = key, (descriptor, buffers)
    return CACHED[1]


def descriptor(package, scenario, index):
    with LOCK:
        return frame(package, scenario, index)[0]


def binary(package, scenario, index, name):
    with LOCK:
        _, buffers = frame(package, scenario, index)
        if name not in buffers:
            raise ValueError("saved array outside allowlist")
        return buffers[name].tobytes()
