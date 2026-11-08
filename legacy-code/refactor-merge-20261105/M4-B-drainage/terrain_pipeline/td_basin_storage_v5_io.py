"""Pure saved-state validation for v5; no compiled solver imports."""

import numpy as np
from terrain_pipeline.common_infra import identity, load_bundle, save_bundle
from terrain_pipeline.td_basin_storage import validate_basin_storage, MAX_STORAGE_BYTES, _storage_headers

PROFILE = "v5-symmetric-forcing-6e9-v1"


def validate_saved_storage(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if (metadata["algorithm"] != "D4-threshold-symmetric-forcing-Strang-v5" or metadata.get("work_profile") != PROFILE or
            result["identity_sha256"] != identity(arrays, metadata)):
        raise ValueError("v5 storage identity/profile mismatch")
    for name in ("hydraulic_ready", "transient_converged", "morphology_flux_ready", "natural_outlet_verified"):
        if metadata.get(name) is not False:
            raise ValueError("v5 saved flags cannot assert physical certification")
    semantics = {"forcing_semantics": "runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
                 "saved_time_semantics": "state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
                 "activity_semantics": "each face visited twice for substep_s/2 within transport; sum directional activity<=substep_s; forcing halves add no activity"}
    if any(metadata.get(name) != expected for name, expected in semantics.items()):
        raise ValueError("v5 saved time/forcing semantics mismatch")
    checked_metadata = {**metadata, "algorithm": "D4-threshold-exact-Strang-v4", "work_profile": "v4-threshold-pair-compiled-6e9-v1"}
    validate_basin_storage({"arrays": arrays, "metadata": checked_metadata,
                            "identity_sha256": identity(arrays, checked_metadata)})
    if not np.isfinite([metadata["dt_s"], metadata["substep_s"]]).all() or not 0 < metadata["substep_s"] <= metadata["dt_s"]:
        raise ValueError("v5 invalid physical time")
    total_time = len(arrays["rain_mm_h"]) * metadata["dt_s"]
    if np.any(arrays["active_forward_s"] + arrays["active_reverse_s"] > total_time + 1e-8):
        raise ValueError("v5 combined face activity exceeds physical time")
    return True


def save_storage(path, result):
    save_bundle(path, result, validator=validate_saved_storage)


def load_storage(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_saved_storage,
                         max_bytes=MAX_STORAGE_BYTES, header_validator=_storage_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external v5 identity mismatch")
    return result
