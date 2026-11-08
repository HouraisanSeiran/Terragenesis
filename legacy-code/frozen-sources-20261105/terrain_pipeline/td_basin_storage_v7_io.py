"""Pure saved-state validation for v7; no compiled solver imports."""

import numpy as np
from terrain_pipeline.mountain_source_adapter import identity, load_bundle, save_bundle
from terrain_pipeline.td_basin_storage import validate_basin_storage, MAX_STORAGE_BYTES, _storage_headers

PROFILE = "v7-compensated-forcing-SSPRK2-6e9-v1"


def validate_saved_storage(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if (metadata["algorithm"] != "D4-threshold-compensated-forcing-SSPRK2-v7" or metadata.get("work_profile") != PROFILE or
            result["identity_sha256"] != identity(arrays, metadata)):
        raise ValueError("v7 storage identity/profile mismatch")
    for name in ("hydraulic_ready", "transient_converged", "morphology_flux_ready", "natural_outlet_verified"):
        if metadata.get(name) is not False:
            raise ValueError("v7 saved flags cannot assert physical certification")
    semantics = {"forcing_semantics": "runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
                 "saved_time_semantics": "state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
                 "activity_semantics": "RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity"}
    if any(metadata.get(name) != expected for name, expected in semantics.items()):
        raise ValueError("v7 saved time/forcing semantics mismatch")
    if metadata.get("compensation_semantics") != "soil/fast/slow increments and forcing ledgers compensated; ledger errors reset hourly; depth error reset after transport replacement; exact full-inventory removal retires compensation":
        raise ValueError("v7 compensation semantics mismatch")
    spacing = metadata["spacing_m"]
    degree = np.bincount(arrays["face_cells"].reshape(-1), minlength=arrays["height_m"].size).astype(float)
    np.add.at(degree, arrays["boundary_cells"], arrays["boundary_width_m"] / spacing)
    cfl = float(degree.max(initial=0)) * metadata["parameters"]["face_conductance_m_s"] * metadata["substep_s"] / spacing
    if not np.isfinite(cfl) or not np.isfinite(metadata.get("positivity_cfl", np.nan)) or cfl > 1 or metadata["positivity_cfl"] != cfl:
        raise ValueError("v7 saved positivity CFL mismatch/exceeded")
    checked_metadata = {**metadata, "algorithm": "D4-threshold-exact-Strang-v4", "work_profile": "v4-threshold-pair-compiled-6e9-v1"}
    validate_basin_storage({"arrays": arrays, "metadata": checked_metadata,
                            "identity_sha256": identity(arrays, checked_metadata)})
    if not np.isfinite([metadata["dt_s"], metadata["substep_s"]]).all() or not 0 < metadata["substep_s"] <= metadata["dt_s"]:
        raise ValueError("v7 invalid physical time")
    total_time = len(arrays["rain_mm_h"]) * metadata["dt_s"]
    if np.any(arrays["active_forward_s"] + arrays["active_reverse_s"] > total_time + 1e-8):
        raise ValueError("v7 combined face activity exceeds physical time")
    return True


def save_storage(path, result):
    save_bundle(path, result, validator=validate_saved_storage)


def load_storage(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_saved_storage,
                         max_bytes=MAX_STORAGE_BYTES, header_validator=_storage_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external v7 identity mismatch")
    return result
