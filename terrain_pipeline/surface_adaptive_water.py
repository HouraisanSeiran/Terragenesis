"""Conservative display fans bound to saved adaptive canonical inventories."""

import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, save_bundle
from terrain_pipeline.single_domain_fine_geometry import (
    COORDINATES, FLAGS, _equal, _freeze, _sha, _water_arrays, validate_fine_geometry,
)
from terrain_pipeline.surface_adaptive_io import MAX_BYTES, validate_geometry, validate_snapshot

SCHEMA = "surface-adaptive-canonical-water-fan-v1"
EXTRA = {"cell_depth_m", "corner_depth_m", "center_depth_m", "water_vertices_xyz_m",
         "water_triangles", "wet_cell_ids", "cell_volume_m3"}
SEMANTICS = "conservative canonical inventory visualization; no hydraulic order claim"


def snapshot_record(bundle):
    if (bundle["identity_sha256"] != identity(bundle["arrays"], bundle["metadata"])
            or bundle["metadata"].get("schema") != "surface-adaptive-canonical-snapshot-v1"
            or any(bundle["metadata"].get(flag) is not False for flag in FLAGS)):
        raise ValueError("adaptive water requires an authenticated saved snapshot")
    return dict(bundle["metadata"], **bundle["arrays"])


def bind_sources(bed, snapshot_bundle, geometry):
    validate_fine_geometry(bed)
    validate_geometry(geometry)
    snapshot = snapshot_record(snapshot_bundle)
    validate_snapshot(snapshot, geometry)
    if (bed["metadata"]["spacing_m"] != 1.
            or not np.array_equal(bed["arrays"]["H2_m"], geometry["arrays"]["canonical_bed_m"])
            or bed["metadata"]["origin_m_xz"] != geometry["metadata"]["origin_m_xz"]):
        raise ValueError("adaptive water canonical bed/origin binding mismatch")
    return snapshot


def build_adaptive_water_frame(bed, snapshot_bundle, geometry, *, state_index):
    snapshot = bind_sources(bed, snapshot_bundle, geometry)
    if type(state_index) is not int or state_index < 0:
        raise ValueError("adaptive water saved state index invalid")
    arrays, diagnostics = _water_arrays(bed, snapshot["canonical_depth_m"])
    metadata = dict(schema=SCHEMA, algorithm="saved-adaptive-canonical-inventory-shared-fan-v1",
        coordinates=COORDINATES, representation=SEMANTICS, bed_identity=bed["identity_sha256"],
        geometry_metadata=bed["metadata"], adaptive_snapshot_identity=snapshot_bundle["identity_sha256"],
        adaptive_geometry_identity=geometry["identity_sha256"], state_index=state_index,
        time_s=float(snapshot["time_s"]), canonical_spacing_m=1.,
        leaf_counts=geometry["metadata"]["leaf_counts"], leaf_count=geometry["metadata"]["leaf_count"],
        water_generated=False, solver_advanced=False, continuous_shared_surface=True,
        limitation="centre depth may reach 3x canonical mean; shared fan stage differs from hydraulic leaf stage",
        **diagnostics, **{flag: False for flag in FLAGS})
    frame = _freeze(arrays, metadata)
    validate_bound_adaptive_water_frame(frame, bed, snapshot_bundle, geometry)
    return frame


def validate_adaptive_water_frame(frame):
    arrays, meta = frame["arrays"], frame["metadata"]
    if (frame["identity_sha256"] != identity(arrays, meta) or meta.get("schema") != SCHEMA
            or meta.get("algorithm") != "saved-adaptive-canonical-inventory-shared-fan-v1"
            or meta.get("representation") != SEMANTICS or meta.get("coordinates") != COORDINATES
            or meta.get("water_generated") is not False or meta.get("solver_advanced") is not False
            or meta.get("continuous_shared_surface") is not True or meta.get("canonical_spacing_m") != 1.
            or any(meta.get(flag) is not False for flag in FLAGS)):
        raise ValueError("adaptive water schema/identity/semantics mismatch")
    for name in ("bed_identity", "adaptive_snapshot_identity", "adaptive_geometry_identity"):
        _sha(meta[name])
    if type(meta["state_index"]) is not int or meta["state_index"] < 0 or not math.isfinite(meta["time_s"]):
        raise ValueError("adaptive water saved time/index mismatch")
    bed = dict(arrays={name: value for name, value in arrays.items() if name not in EXTRA},
               metadata=meta["geometry_metadata"], identity_sha256=meta["bed_identity"])
    validate_fine_geometry(bed)
    expected, diagnostics = _water_arrays(bed, arrays["cell_depth_m"])
    _equal(arrays, expected)
    if any(meta.get(name) != value for name, value in diagnostics.items()):
        raise ValueError("adaptive water conservative fan diagnostics mismatch")
    return True


def validate_bound_adaptive_water_frame(frame, bed, snapshot_bundle, geometry):
    validate_adaptive_water_frame(frame)
    snapshot = bind_sources(bed, snapshot_bundle, geometry)
    meta = frame["metadata"]
    if (meta["bed_identity"] != bed["identity_sha256"]
            or meta["adaptive_snapshot_identity"] != snapshot_bundle["identity_sha256"]
            or meta["adaptive_geometry_identity"] != geometry["identity_sha256"]
            or meta["time_s"] != snapshot["time_s"]
            or meta["leaf_counts"] != geometry["metadata"]["leaf_counts"]
            or meta["leaf_count"] != geometry["metadata"]["leaf_count"]
            or not np.array_equal(frame["arrays"]["cell_depth_m"], snapshot["canonical_depth_m"])):
        raise ValueError("adaptive water original snapshot/leaf inventory binding mismatch")
    return True


def save_adaptive_water_frame(path, frame):
    save_bundle(path, frame, validator=validate_adaptive_water_frame)


def load_adaptive_water_frame(path, *, expected_sha256, expected_identity):
    frame = load_bundle(path, expected_sha256=expected_sha256, max_bytes=MAX_BYTES,
                        validator=validate_adaptive_water_frame)
    if frame["identity_sha256"] != expected_identity:
        raise ValueError("adaptive water external identity mismatch")
    return frame


def load_consumer_adaptive_frame(context, *, scenario, frame_index):
    """Load and bind a relocated consumer frame using only allowlisted payloads."""
    manifest = context["manifest"]
    if manifest.get("backend") != "adaptive-saved-canonical-fan":
        raise ValueError("adaptive frame requires an adaptive consumer context")
    frames = manifest["scenarios"][scenario]["frames"]
    if type(frame_index) is not int or not 0 <= frame_index < len(frames):
        raise ValueError("adaptive consumer frame index invalid")
    items = {item["path"]:item for item in manifest["artifacts"]}

    def load(name):
        item = items[name]
        bundle = load_bundle(context["allowlist"][name], expected_sha256=item["sha256"],
                             max_bytes=MAX_BYTES, validator=lambda value:True)
        if bundle["identity_sha256"] != item["identity_sha256"]:
            raise ValueError("adaptive consumer external payload identity mismatch")
        return bundle

    entry = frames[frame_index]
    bed = load(manifest["scenarios"][scenario]["geometry"])
    frame, snapshot, saved_geometry = (load(entry[name]) for name in ("artifact", "snapshot", "adaptive_geometry"))
    if (saved_geometry["metadata"].get("schema") != "surface-adaptive-geometry-v1"
            or any(saved_geometry["metadata"].get(flag) is not False for flag in FLAGS)):
        raise ValueError("adaptive consumer raw geometry schema/flags mismatch")
    geometry = dict(arrays=saved_geometry["arrays"], metadata=saved_geometry["metadata"]["raw_geometry_metadata"],
                    identity_sha256=saved_geometry["metadata"]["raw_geometry_identity"])
    validate_bound_adaptive_water_frame(frame, bed, snapshot, geometry)
    if frame["metadata"]["state_index"] != frame_index or frame["metadata"]["time_s"] != entry["time_s"]:
        raise ValueError("adaptive consumer manifest original frame/time binding mismatch")
    return dict(frame=frame, bed=bed, snapshot=snapshot, geometry=geometry, solver_advanced=False)
