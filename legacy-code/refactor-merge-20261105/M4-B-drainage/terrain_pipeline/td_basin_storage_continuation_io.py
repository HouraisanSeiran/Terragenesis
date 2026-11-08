"""Pure IO for versioned v8 hourly pages with global checkpoint time."""
from terrain_pipeline.common_infra import identity, load_bundle, save_bundle
from terrain_pipeline.td_basin_storage import MAX_STORAGE_BYTES, _storage_headers
from terrain_pipeline.td_basin_storage_v7_io import validate_saved_storage as validate_v7
import numpy as np
import re


def validate_saved_storage(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if result["identity_sha256"] != identity(arrays,metadata) or metadata["algorithm"] != "D4-threshold-checkpoint-SSPRK2-v8" or metadata["work_profile"] != "v8-hour-pages-v7-SSPRK2":
        raise ValueError("v8 page identity/profile mismatch")
    if metadata["saved_time_semantics"] != "state0 is checkpoint time; state[k] at chunk_start_s+k*dt_s; ledger[k] covers local hour k" or metadata["chunk_start_s"] < 0 or metadata["chunk_end_s"] != metadata["chunk_start_s"]+len(arrays["rain_mm_h"])*metadata["dt_s"]:
        raise ValueError("v8 page global time mismatch")
    if not np.isfinite([metadata["chunk_start_s"],metadata["chunk_end_s"]]).all() or metadata["forcing_hour_offset"]*metadata["dt_s"] != metadata["chunk_start_s"] or re.fullmatch("[0-9a-f]{64}",metadata.get("forcing_identity","")) is None:
        raise ValueError("v8 page forcing/time identity invalid")
    checked = {**metadata,"algorithm":"D4-threshold-compensated-forcing-SSPRK2-v7","work_profile":"v7-compensated-forcing-SSPRK2-6e9-v1",
               "saved_time_semantics":"state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]"}
    validate_v7({"arrays":arrays,"metadata":checked,"identity_sha256":identity(arrays,checked)})
    return True


def save_storage(path,result):
    save_bundle(path,result,validator=validate_saved_storage)


def load_storage(path,*,expected_sha256,expected_identity):
    result=load_bundle(path,expected_sha256=expected_sha256,validator=validate_saved_storage,max_bytes=MAX_STORAGE_BYTES,header_validator=_storage_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external v8 page identity mismatch")
    return result
