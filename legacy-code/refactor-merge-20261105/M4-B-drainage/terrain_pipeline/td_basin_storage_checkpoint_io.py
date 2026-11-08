"""Pure pinned checkpoint IO; never imports or advances a solver."""

import numpy as np
import re
from terrain_pipeline.common_infra import identity, load_bundle, save_bundle


def validate_checkpoint(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("schema") != "td-storage-continuation-v1" or metadata.get("execution_profile") != "v8-hour-pages-v7-SSPRK2" or result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("checkpoint identity/profile mismatch")
    cells, faces = metadata["cells"], metadata["faces"]
    if type(metadata.get("substeps")) is not int or type(metadata.get("work_face_steps")) is not int or metadata["substeps"]<1 or metadata["work_face_steps"]<0:
        raise ValueError("checkpoint integer count required")
    if not isinstance(metadata.get("forcing_identity"),str) or re.fullmatch("[0-9a-f]{64}",metadata["forcing_identity"]) is None:
        raise ValueError("checkpoint forcing identity invalid")
    if not np.isfinite([metadata["substep_s"],metadata["dt_s"],metadata["elapsed_s"]]).all() or metadata["substep_s"] <= 0 or metadata["dt_s"] <= 0 or metadata["substeps"] * metadata["substep_s"] != metadata["elapsed_s"] or metadata["elapsed_s"] % metadata["dt_s"] != 0:
        raise ValueError("checkpoint time/count mismatch")
    states = {"depth_m", "soil_mm", "fast_mm", "slow_mm", "error_depth", "error_soil", "error_fast", "error_slow"}
    cumulative = {"cumulative_" + key for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s", "routed_volume_m3", "wet_duration_s")}
    if set(arrays) != states | cumulative or type(cells) is not int or not 1 <= cells <= 1_000_000 or type(faces) is not int or not 0 <= faces <= 2*cells:
        raise ValueError("checkpoint arrays/budget invalid")
    for key, values in arrays.items():
        expected = faces if key.startswith("cumulative_") and key not in ("cumulative_routed_volume_m3", "cumulative_wet_duration_s") else cells
        if values.shape != (expected,) or values.dtype != np.float64 or not np.isfinite(values).all():
            raise ValueError("checkpoint shape/nonfinite state")
        if not key.startswith("error_") and np.any(values < 0):
            raise ValueError("checkpoint negative state")
    if not np.isfinite(metadata["elapsed_s"]) or metadata["elapsed_s"] <= 0 or metadata["substeps"] < 1 or metadata["work_face_steps"] != metadata["substeps"] * faces:
        raise ValueError("checkpoint elapsed/work mismatch")
    if np.any(arrays["cumulative_active_forward_s"] + arrays["cumulative_active_reverse_s"] > metadata["elapsed_s"] + 1e-8):
        raise ValueError("checkpoint duplicated activity")
    if metadata["hydraulic_ready"] is not False or metadata["transient_converged"] is not False:
        raise ValueError("checkpoint certification forbidden")
    return True


def save_checkpoint(path, result):
    save_bundle(path, result, validator=validate_checkpoint)


def load_checkpoint(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_checkpoint, max_bytes=128*1024*1024,header_validator=checkpoint_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external checkpoint identity mismatch")
    return result


def checkpoint_headers(headers):
    shape,dtype=headers.get("depth_m",((),np.dtype("O")))
    if len(shape)!=1 or not 1<=shape[0]<=250000 or dtype!=np.float64:
        raise ValueError("checkpoint allocation rejection")
    for key in ("soil_mm","fast_mm","slow_mm","error_depth","error_soil","error_fast","error_slow","cumulative_routed_volume_m3","cumulative_wet_duration_s"):
        if headers.get(key)!=(shape,np.dtype("float64")):
            raise ValueError("checkpoint state header mismatch")
    faces,face_dtype=headers.get("cumulative_face_forward_m3",((),np.dtype("O")))
    if len(faces)!=1 or faces[0]>2*shape[0] or face_dtype!=np.float64:
        raise ValueError("checkpoint face allocation rejection")
    for key in ("cumulative_face_reverse_m3","cumulative_active_forward_s","cumulative_active_reverse_s"):
        if headers.get(key)!=(faces,np.dtype("float64")):
            raise ValueError("checkpoint directional header mismatch")
