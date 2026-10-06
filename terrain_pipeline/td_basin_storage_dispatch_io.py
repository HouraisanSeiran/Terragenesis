"""Version-aware saved-state validation without solver or compiled imports."""

import math
import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, save_bundle
from terrain_pipeline.rainfall_runoff import RunoffParameters

MAX_STORAGE_BYTES = 256 * 1024 * 1024
VERSIONS = {
    ("finite-time-D4-threshold-storage-v1", None): (20000, 500000000),
    ("D4-analytic-face-Strang-splitting-v2", None): (100000, 3000000000),
    ("D4-analytic-face-Strang-splitting-v2", "v2-full-refinement-6e9-v1"): (100000, 6000000000),
    ("D4-analytic-face-event-Strang-v3", None): (100000, 6000000000),
    ("D4-threshold-exact-Strang-v4", "v4-threshold-pair-compiled-6e9-v1"): (100000, 6000000000),
    ("D4-threshold-symmetric-forcing-Strang-v5", "v5-symmetric-forcing-6e9-v1"): (100000, 6000000000),
    ("D4-threshold-symmetric-forcing-SSPRK2-v6", "v6-simultaneous-SSPRK2-6e9-v1"): (100000, 6000000000),
}


def _configuration(metadata):
    version = (metadata.get("algorithm"), metadata.get("work_profile"))
    if version not in VERSIONS:
        raise ValueError("unknown saved storage algorithm/profile")
    limits = VERSIONS[version]
    config = metadata["parameters"]
    coefficients = ("substep_s", "face_conductance_m_s", "surface_evaporation_mm_h", "wet_threshold_m")
    if set(config) != set(coefficients) | {"max_substeps", "max_work_face_steps"}:
        raise ValueError("unexpected saved storage parameters")
    for name in coefficients:
        if type(config[name]) not in (int, float) or not math.isfinite(config[name]) or config[name] < 0:
            raise ValueError("invalid saved coefficient")
    if config["substep_s"] <= 0 or config["wet_threshold_m"] <= 0:
        raise ValueError("invalid saved step/threshold")
    for name, limit in zip(("max_substeps", "max_work_face_steps"), limits):
        if type(config[name]) is not int or not 1 <= config[name] <= limit:
            raise ValueError("invalid saved work budget")
    if type(metadata["spacing_m"]) not in (int, float) or not math.isfinite(metadata["spacing_m"]) or metadata["spacing_m"] <= 0:
        raise ValueError("invalid saved spacing")
    origin = metadata["origin_m_xz"]
    if len(origin) != 2 or any(type(value) not in (int, float) or not math.isfinite(value) for value in origin):
        raise ValueError("invalid saved origin")
    if any(type(metadata[name]) not in (int, float) or not math.isfinite(metadata[name]) or metadata[name] <= 0 for name in ("dt_s", "substep_s")) or metadata["substep_s"] > metadata["dt_s"]:
        raise ValueError("invalid saved physical time")
    if type(metadata["substeps"]) is not int or metadata["substeps"] < 1:
        raise ValueError("invalid saved substep count")
    for name in ("hydraulic_ready", "transient_converged", "morphology_flux_ready", "natural_outlet_verified", "publishable"):
        if name in metadata and metadata[name] is not False:
            raise ValueError("saved flags cannot assert certification")
    if version[0].endswith(("-v5", "-v6")):
        for name in ("hydraulic_ready", "transient_converged", "morphology_flux_ready", "natural_outlet_verified"):
            if metadata.get(name) is not False:
                raise ValueError("missing conservative version flags")
        expected = {
            "forcing_semantics": "runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
            "saved_time_semantics": "state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
            "activity_semantics": "RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity" if version[0].endswith("-v6") else "each face visited twice for substep_s/2 within transport; sum directional activity<=substep_s; forcing halves add no activity",
        }
        if any(metadata.get(name) != value for name, value in expected.items()):
            raise ValueError("saved version semantics mismatch")
    return config


def validate_saved_storage(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("schema") != "td-basin-storage-v1" or identity(arrays, metadata) != result["identity_sha256"]:
        raise ValueError("saved storage schema/identity mismatch")
    config = _configuration(metadata)
    RunoffParameters(**metadata["runoff_parameters"])
    bed, valid = arrays["height_m"], arrays["valid_mask"]
    cells = bed.size
    rain = arrays["rain_mm_h"]
    if rain.ndim != 2 or rain.shape[1] != cells or not 1 <= len(rain) <= 1000:
        raise ValueError("invalid forcing shape")
    subdivisions = math.ceil(metadata["dt_s"] / config["substep_s"])
    if metadata["substeps"] != len(rain) * subdivisions or metadata["substep_s"] != metadata["dt_s"] / subdivisions:
        raise ValueError("saved actual substep count/duration mismatch")
    states = ("depth_m", "soil_mm", "fast_mm", "slow_mm")
    ledgers = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3")
    required = set(states + ledgers) | {"rain_mm_h", "height_m", "valid_mask", "face_cells", "receiver",
        "boundary_cells", "boundary_width_m", "face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s",
        "routed_volume_m3", "wet_duration_s", "wet_pool_count"}
    diagnostic_keys = {"limiter_active_count", "proposed_active_count", "donor_limited_count"}
    if set(arrays) not in (required, required | diagnostic_keys) or bed.ndim != 2 or valid.shape != bed.shape or valid.dtype != bool:
        raise ValueError("unexpected storage arrays/coverage")
    if bed.dtype != np.float64 or not 1 <= cells <= 250000 or len(rain) * cells > 4000000 or not valid.any():
        raise ValueError("invalid saved grid/allocation")
    boundary = arrays["boundary_cells"]
    widths = arrays["boundary_width_m"]
    if boundary.dtype != np.int64 or boundary.ndim != 1 or np.any((boundary < 0) | (boundary >= cells)) or len(np.unique(boundary)) != len(boundary):
        raise ValueError("invalid unique boundary cells")
    boundary_rows, boundary_columns = np.divmod(boundary, bed.shape[1])
    side_count = ((boundary_rows == 0).astype(int) + (boundary_rows == bed.shape[0] - 1)
                  + (boundary_columns == 0) + (boundary_columns == bed.shape[1] - 1))
    if not valid.ravel()[boundary].all() or np.any(side_count == 0) or widths.dtype != np.float64 or widths.shape != boundary.shape or not np.array_equal(widths, side_count * metadata["spacing_m"]):
        raise ValueError("boundary cells/widths must match valid exterior sides")
    declared_boundary = np.zeros(cells, bool)
    declared_boundary[boundary] = True
    if np.any(arrays["boundary_outflow_m3"][:, ~declared_boundary] != 0):
        raise ValueError("outflow on undeclared boundary cell")
    pools = arrays["wet_pool_count"]
    if pools.dtype != np.int64 or pools.shape != (len(rain) + 1,) or np.any((pools < 0) | (pools > valid.sum())):
        raise ValueError("invalid saved wet pool count")
    for key in states + ledgers:
        shape = (len(rain) + 1, cells) if key in states else rain.shape
        if arrays[key].shape != shape or arrays[key].dtype != np.float64:
            raise ValueError("invalid state/ledger shape or dtype")
    for key, value in arrays.items():
        if not np.isfinite(value).all():
            raise ValueError("nonfinite storage array")
        if key not in ("height_m", "receiver", "internal_net_m3", "storage_change_m3", "balance_residual_m3") and np.any(value < 0):
            raise ValueError("negative water account")
    for key in states + ledgers + ("rain_mm_h",):
        if np.any(arrays[key][:, ~valid.ravel()] != 0):
            raise ValueError("water state/forcing on unknown cells")
    area = metadata["spacing_m"] ** 2
    volume = area * (arrays["depth_m"] + sum(arrays[key] for key in ("soil_mm", "fast_mm", "slow_mm")) / 1000)

    def near(actual, expected):
        if np.any(abs(actual - expected) > 1e-6 + 1e-10 * (abs(actual) + abs(expected))):
            raise ValueError("nonconservative saved water ledger")

    near(arrays["storage_change_m3"], np.diff(volume, axis=0))
    near(arrays["rain_volume_m3"], rain * metadata["dt_s"] / 3600 * area / 1000)
    near(arrays["rain_volume_m3"], arrays["lake_rain_m3"] + arrays["land_rain_m3"])
    residual = (arrays["rain_volume_m3"] + arrays["internal_net_m3"] - arrays["soil_et_m3"]
                - arrays["surface_et_m3"] - arrays["boundary_outflow_m3"] - np.diff(volume, axis=0))
    near(arrays["balance_residual_m3"], residual)
    near(residual, np.zeros_like(residual))
    near(arrays["internal_net_m3"].sum(axis=1), np.zeros(len(rain)))
    faces = arrays["face_cells"]
    if faces.dtype != np.int64 or faces.ndim != 2 or faces.shape[1] != 2 or np.any((faces < 0) | (faces >= cells)):
        raise ValueError("invalid saved D4 face")
    first, second = faces[:, 0], faces[:, 1]
    columns = bed.shape[1]
    if np.any(abs(first // columns - second // columns) + abs(first % columns - second % columns) != 1) or not valid.ravel()[faces].all():
        raise ValueError("unknown/non-D4 exchange")
    face_keys = np.minimum(first, second) * cells + np.maximum(first, second)
    if len(np.unique(face_keys)) != len(faces):
        raise ValueError("duplicate physical face including reversed pair")
    for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        if arrays[key].shape != (len(faces),) or arrays[key].dtype != np.float64:
            raise ValueError("invalid face ledger")
    for flow, duration_key in (("face_forward_m3", "active_forward_s"), ("face_reverse_m3", "active_reverse_s")):
        if np.any(arrays[duration_key] > len(rain) * metadata["dt_s"] + 1e-8) or np.any(
                (arrays[flow] == 0) & (arrays[duration_key] != 0)):
            raise ValueError("invalid directional face activity duration")
    net = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    net_cells = np.bincount(second, weights=net, minlength=cells) - np.bincount(first, weights=net, minlength=cells)
    near(arrays["internal_net_m3"].sum(axis=0), net_cells)
    receiver = arrays["receiver"]
    if receiver.dtype != np.int64 or receiver.shape != (cells,) or np.any((receiver < -1) | (receiver >= cells)):
        raise ValueError("invalid receiver")
    donor = np.flatnonzero(receiver >= 0)
    targets = receiver[donor]
    receiver_keys = np.minimum(donor, targets) * cells + np.maximum(donor, targets)
    if np.any(receiver[~valid.ravel()] != -1) or not valid.ravel()[donor].all() or not valid.ravel()[targets].all() or not np.isin(receiver_keys, face_keys).all() or np.any(bed.ravel()[targets] > bed.ravel()[donor]):
        raise ValueError("receiver must follow valid nonascending saved D4 face")
    complete = np.zeros(cells, bool)
    for start in donor:
        cursor = int(start)
        pending = set()
        while cursor >= 0 and not complete[cursor]:
            if cursor in pending:
                raise ValueError("receiver cycle")
            pending.add(cursor)
            cursor = int(receiver[cursor])
        if pending:
            complete[list(pending)] = True
    expected_routed = np.zeros(cells)
    np.add.at(expected_routed, first, np.where(receiver[first] == second, arrays["face_forward_m3"], 0))
    np.add.at(expected_routed, second, np.where(receiver[second] == first, arrays["face_reverse_m3"], 0))
    near(arrays["routed_volume_m3"], expected_routed)
    if arrays["routed_volume_m3"].dtype != np.float64 or arrays["routed_volume_m3"].shape != (cells,) or arrays["wet_duration_s"].dtype != np.float64 or arrays["wet_duration_s"].shape != (cells,) or np.any(arrays["wet_duration_s"] > len(rain) * metadata["dt_s"] + 1e-8):
        raise ValueError("invalid positive receiver flow duration")
    if np.any((arrays["routed_volume_m3"] == 0) & (arrays["wet_duration_s"] != 0)):
        raise ValueError("duration without actual routed flux")
    if metadata["substeps"] > config["max_substeps"] or metadata["substeps"] * len(faces) > config["max_work_face_steps"]:
        raise ValueError("saved work budget exceeded")
    if diagnostic_keys <= set(arrays):
        for key in diagnostic_keys:
            if arrays[key].shape != (len(rain),) or arrays[key].dtype != np.int64:
                raise ValueError("invalid limiter diagnostic")
        if np.any(arrays["limiter_active_count"] > arrays["proposed_active_count"]):
            raise ValueError("invalid limiter count")


    if np.any(arrays["active_forward_s"] + arrays["active_reverse_s"] > len(rain) * metadata["dt_s"] + 1e-8):
        raise ValueError("combined directional activity exceeds elapsed time")
    if metadata["algorithm"] == "D4-threshold-symmetric-forcing-SSPRK2-v6":
        degree = np.bincount(faces.reshape(-1), minlength=cells).astype(float)
        np.add.at(degree, arrays["boundary_cells"], arrays["boundary_width_m"] / metadata["spacing_m"])
        cfl = float(degree.max(initial=0)) * config["face_conductance_m_s"] * metadata["substep_s"] / metadata["spacing_m"]
        if not math.isfinite(cfl) or cfl > 1 or metadata.get("positivity_cfl") != cfl:
            raise ValueError("saved v6 positivity CFL mismatch")
    return True


def load_storage(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_saved_storage,
                         max_bytes=MAX_STORAGE_BYTES, header_validator=_storage_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external storage identity mismatch")
    return result


def save_storage(path, result):
    save_bundle(path, result, validator=validate_saved_storage)


def _storage_headers(headers):
    height_shape, height_dtype = headers.get("height_m", ((), np.dtype("O")))
    rain_shape, rain_dtype = headers.get("rain_mm_h", ((), np.dtype("O")))
    if (len(height_shape) != 2 or not 1 <= math.prod(height_shape) <= 250000 or height_dtype != np.float64 or
            len(rain_shape) != 2 or rain_shape[1] != math.prod(height_shape) or not 1 <= rain_shape[0] <= 1000 or
            math.prod(rain_shape) > 4_000_000 or rain_dtype != np.float64):
        raise ValueError("storage header grid/time allocation rejection")
    states = {"depth_m", "soil_mm", "fast_mm", "slow_mm"}
    ledgers = {"rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3", "rain_mm_h"}
    for key in states | ledgers:
        expected_shape = (rain_shape[0] + 1, rain_shape[1]) if key in states else rain_shape
        if headers.get(key) != (expected_shape, np.dtype("float64")):
            raise ValueError("storage state/ledger header mismatch")
    if headers.get("valid_mask") != (height_shape, np.dtype(bool)):
        raise ValueError("storage mask header mismatch")
    face_shape, face_dtype = headers.get("face_cells", ((), np.dtype("O")))
    if len(face_shape) != 2 or face_shape[1] != 2 or face_shape[0] > 2 * rain_shape[1] or face_dtype != np.int64:
        raise ValueError("storage face allocation rejection")
    for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        if headers.get(key) != ((face_shape[0],), np.dtype("float64")):
            raise ValueError("storage directional header mismatch")
    for key, dtype in (("receiver", np.int64), ("routed_volume_m3", np.float64), ("wet_duration_s", np.float64)):
        if headers.get(key) != ((rain_shape[1],), np.dtype(dtype)):
            raise ValueError("storage receiver output header mismatch")
    if headers.get("wet_pool_count") != ((rain_shape[0] + 1,), np.dtype("int64")):
        raise ValueError("storage pool count header mismatch")
    boundary_shape, boundary_dtype = headers.get("boundary_cells", ((), np.dtype("O")))
    if len(boundary_shape) != 1 or boundary_shape[0] > rain_shape[1] or boundary_dtype != np.int64 or headers.get("boundary_width_m") != (boundary_shape, np.dtype("float64")):
        raise ValueError("storage boundary header mismatch")
    manifest_shape, manifest_dtype = headers.get("manifest", ((), np.dtype("O")))
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= 1048576 or manifest_dtype != np.uint8:
        raise ValueError("storage manifest header mismatch")
    required = states | ledgers | {"height_m", "valid_mask", "face_cells", "face_forward_m3", "face_reverse_m3",
        "active_forward_s", "active_reverse_s", "receiver", "routed_volume_m3", "wet_duration_s", "wet_pool_count",
        "boundary_cells", "boundary_width_m", "manifest"}
    diagnostic_keys = {"limiter_active_count", "proposed_active_count", "donor_limited_count"}
    if set(headers) not in (required, required | diagnostic_keys):
        raise ValueError("unexpected storage archive headers")
    if diagnostic_keys <= set(headers):
        for key in diagnostic_keys:
            if headers[key] != ((rain_shape[0],), np.dtype("int64")):
                raise ValueError("invalid limiter diagnostic header")
