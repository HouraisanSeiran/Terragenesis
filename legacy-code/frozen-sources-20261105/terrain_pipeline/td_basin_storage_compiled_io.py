"""Pure pinned experimental v9 execution IO, without compiled imports."""
from terrain_pipeline.mountain_source_adapter import identity, load_bundle, save_bundle
from terrain_pipeline.td_basin_storage import MAX_STORAGE_BYTES, _storage_headers
from terrain_pipeline.td_basin_storage_continuation_io import validate_saved_storage as validate_v8
from terrain_pipeline.td_basin_storage_checkpoint_io import validate_checkpoint as validate_v8_checkpoint, checkpoint_headers
import math
import numpy as np

PROFILE="v9-compiled-hour-loop-v8-equivalent-v1"


def validate_saved_storage(result):
    arrays,metadata=result["arrays"],result["metadata"]
    if result["identity_sha256"]!=identity(arrays,metadata) or metadata["algorithm"]!="D4-threshold-compiled-hour-SSPRK2-v9" or metadata["work_profile"]!=PROFILE:
        raise ValueError("v9 execution identity/profile mismatch")
    if type(metadata.get("substeps")) is not int or type(metadata.get("forcing_hour_offset")) is not int or metadata["substeps"]<1 or metadata["forcing_hour_offset"]<0:
        raise ValueError("v9 page integer time counts required")
    if metadata["substeps"]*metadata["substep_s"] != len(arrays["rain_mm_h"])*metadata["dt_s"]:
        raise ValueError("v9 page actual substep count mismatch")
    subdivisions=math.ceil(metadata["dt_s"]/metadata["parameters"]["substep_s"])
    if metadata["substeps"]!=len(arrays["rain_mm_h"])*subdivisions or metadata["substep_s"]!=metadata["dt_s"]/subdivisions:
        raise ValueError("v9 configured versus actual substeps mismatch")
    checked={**metadata,"algorithm":"D4-threshold-checkpoint-SSPRK2-v8","work_profile":"v8-hour-pages-v7-SSPRK2"}
    return validate_v8({"arrays":arrays,"metadata":checked,"identity_sha256":identity(arrays,checked)})


def validate_checkpoint(result):
    arrays,metadata=result["arrays"],result["metadata"]
    if result["identity_sha256"]!=identity(arrays,metadata) or metadata["execution_profile"]!=PROFILE:
        raise ValueError("v9 checkpoint profile/identity mismatch")
    subdivisions=math.ceil(metadata["dt_s"]/metadata["parameters"]["substep_s"])
    if metadata["substeps"] != metadata["elapsed_s"]/metadata["dt_s"]*subdivisions or metadata["substep_s"] != metadata["dt_s"]/subdivisions:
        raise ValueError("v9 checkpoint configured count mismatch")
    if np.any(arrays["cumulative_wet_duration_s"]>metadata["elapsed_s"]+1e-8):
        raise ValueError("v9 cumulative receiver activity exceeds elapsed")
    checked={**metadata,"execution_profile":"v8-hour-pages-v7-SSPRK2"}
    return validate_v8_checkpoint({"arrays":arrays,"metadata":checked,"identity_sha256":identity(arrays,checked)})


def save_storage(path,result):
    save_bundle(path,result,validator=validate_saved_storage)


def save_checkpoint(path,result):
    save_bundle(path,result,validator=validate_checkpoint)


def load_storage(path,*,expected_sha256,expected_identity):
    result=load_bundle(path,expected_sha256=expected_sha256,validator=validate_saved_storage,max_bytes=MAX_STORAGE_BYTES,header_validator=_storage_headers)
    if result["identity_sha256"]!=expected_identity:
        raise ValueError("external v9 storage identity mismatch")
    return result


def load_checkpoint(path,*,expected_sha256,expected_identity):
    result=load_bundle(path,expected_sha256=expected_sha256,validator=validate_checkpoint,max_bytes=128*1024*1024,header_validator=checkpoint_headers)
    if result["identity_sha256"]!=expected_identity:
        raise ValueError("external v9 checkpoint identity mismatch")
    return result
