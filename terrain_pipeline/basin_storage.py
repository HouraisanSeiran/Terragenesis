"""basin_storage: merged M4 implementation; source locations precede each statement."""
from __future__ import annotations

from dataclasses import asdict as _m4_basin_overflow_asdict
from dataclasses import asdict as _m4_basin_overflow_implicit_asdict
from dataclasses import asdict as _m4_basin_overflow_radau_asdict
from dataclasses import asdict as _m4_basin_runoff_exchange_asdict
from dataclasses import asdict as _m4_basin_storage_asdict
from dataclasses import asdict as _m4_basin_storage_compiled_driver_asdict
from dataclasses import asdict as _m4_basin_storage_continuation_asdict
from dataclasses import asdict as _m4_basin_storage_v5_asdict
from dataclasses import asdict as _m4_basin_storage_v6_asdict
from dataclasses import asdict as _m4_basin_storage_v7_asdict
from dataclasses import dataclass as _m4_basin_overflow_dataclass
from dataclasses import dataclass as _m4_basin_runoff_exchange_dataclass
from numba import njit as _m4_basin_forcing_v10_njit
from numba import njit as _m4_basin_overflow_radau_njit
from numba import njit as _m4_basin_storage_compiled_njit
from numba import njit as _m4_basin_storage_refinement_njit
from numba import njit as _m4_basin_storage_v10_njit
from numba import njit as _m4_basin_storage_v4_njit
from numba import njit as _m4_basin_transport_v6_njit
from pathlib import Path as _m4_basin_overflow_Path
from pathlib import Path as _m4_basin_overflow_implicit_Path
from pathlib import Path as _m4_basin_overflow_radau_Path
from pathlib import Path as _m4_basin_review_Path
from pathlib import Path as _m4_basin_source_Path
from scipy.integrate import Radau as _m4_basin_overflow_radau_Radau
from scipy.integrate import Radau as _m4_basin_runoff_exchange_Radau
from scipy.sparse import coo_matrix as _m4_basin_overflow_implicit_coo_matrix
from scipy.sparse import coo_matrix as _m4_basin_overflow_radau_coo_matrix
from scipy.sparse.linalg import spsolve as _m4_basin_overflow_implicit_spsolve
from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_basin_review_load_basin_hierarchy
from terrain_pipeline.basin_topology import load_saddle_breach as _m4_basin_review_load_saddle_breach
from terrain_pipeline.runoff import RUNOFF_ARRAY_KEYS as _m4_basin_runoff_exchange_RUNOFF_ARRAY_KEYS
from terrain_pipeline.td_basin_morphology import load_morphology as _m4_basin_review_load_morphology
from terrain_pipeline.geology import load_material_field as _m4_basin_review_load_material_field
import hashlib as _m4_basin_overflow_hashlib
import hashlib as _m4_basin_review_hashlib
import html as _m4_basin_review_html
import json as _m4_basin_overflow_json
import json as _m4_basin_review_json
import math as _m4_basin_overflow_implicit_math
import math as _m4_basin_overflow_math
import math as _m4_basin_overflow_radau_math
import math as _m4_basin_runoff_exchange_math
import math as _m4_basin_source_math
import math as _m4_basin_storage_compiled_driver_math
import math as _m4_basin_storage_compiled_io_math
import math as _m4_basin_storage_compiled_math
import math as _m4_basin_storage_continuation_math
import math as _m4_basin_storage_dispatch_io_math
import math as _m4_basin_storage_implicit_math
import math as _m4_basin_storage_math
import math as _m4_basin_storage_refinement_math
import math as _m4_basin_storage_v10_io_math
import math as _m4_basin_storage_v10_math
import math as _m4_basin_storage_v3_math
import math as _m4_basin_storage_v4_math
import math as _m4_basin_storage_v5_math
import math as _m4_basin_storage_v6_math
import math as _m4_basin_storage_v7_math
import numpy as _m4_basin_forcing_compensated_np
import numpy as _m4_basin_forcing_v10_np
import numpy as _m4_basin_overflow_implicit_np
import numpy as _m4_basin_overflow_np
import numpy as _m4_basin_overflow_radau_np
import numpy as _m4_basin_review_np
import numpy as _m4_basin_runoff_exchange_np
import numpy as _m4_basin_source_np
import numpy as _m4_basin_storage_checkpoint_io_np
import numpy as _m4_basin_storage_compiled_driver_np
import numpy as _m4_basin_storage_compiled_io_np
import numpy as _m4_basin_storage_compiled_np
import numpy as _m4_basin_storage_continuation_io_np
import numpy as _m4_basin_storage_continuation_np
import numpy as _m4_basin_storage_dispatch_io_np
import numpy as _m4_basin_storage_implicit_np
import numpy as _m4_basin_storage_np
import numpy as _m4_basin_storage_refinement_np
import numpy as _m4_basin_storage_v10_io_np
import numpy as _m4_basin_storage_v10_np
import numpy as _m4_basin_storage_v3_np
import numpy as _m4_basin_storage_v4_np
import numpy as _m4_basin_storage_v5_io_np
import numpy as _m4_basin_storage_v5_np
import numpy as _m4_basin_storage_v6_io_np
import numpy as _m4_basin_storage_v6_np
import numpy as _m4_basin_storage_v7_io_np
import numpy as _m4_basin_storage_v7_np
import numpy as _m4_basin_transport_v6_np
import numpy as _m4_world_acceptance_processes_np
import os as _m4_basin_review_os
import re as _m4_basin_storage_checkpoint_io_re
import re as _m4_basin_storage_continuation_io_re
import re as _m4_basin_storage_v10_io_re
import shutil as _m4_basin_review_shutil
import tempfile as _m4_basin_review_tempfile

CATEGORY = "B"

# --- terrain_pipeline/td_basin_storage.py:12 ---
STORAGE_DEFAULT_PARAMETERS = {"substep_s": 60.0, "face_conductance_m_s": 0.6, "surface_evaporation_mm_h": 0.15,
    "wet_threshold_m": 1e-9, "max_substeps": 20000, "max_work_face_steps": 500000000}

# --- terrain_pipeline/td_basin_storage.py:14 ---
STORAGE_MAX_STORAGE_BYTES = 256 * 1024 * 1024

# --- terrain_pipeline/td_basin_storage.py:17 ---
def _parameters(supplied):
    supplied = {} if supplied is None else dict(supplied)
    if set(supplied) - set(STORAGE_DEFAULT_PARAMETERS):
        raise ValueError("unknown storage parameters")
    values = {**STORAGE_DEFAULT_PARAMETERS, **supplied}
    for key in ("substep_s", "face_conductance_m_s", "surface_evaporation_mm_h", "wet_threshold_m"):
        if type(values[key]) not in (int, float) or not _m4_basin_storage_math.isfinite(values[key]) or values[key] < 0:
            raise ValueError("invalid finite storage coefficient")
    if values["substep_s"] <= 0 or values["wet_threshold_m"] <= 0:
        raise ValueError("positive substep and wet threshold required")
    for key in ("max_substeps", "max_work_face_steps"):
        if type(values[key]) is not int or not 1 <= values[key] <= STORAGE_DEFAULT_PARAMETERS[key]:
            raise ValueError("invalid work budget")
    return values

# --- terrain_pipeline/td_basin_storage.py:33 ---
def _pool_count(depth, bed, valid, faces, threshold):
    wet = (depth > threshold) & valid
    parent = _m4_basin_storage_np.arange(depth.size)

    def find(cell):
        while parent[cell] != cell:
            parent[cell] = parent[parent[cell]]
            cell = parent[cell]
        return cell

    head = bed + depth
    connected = wet[faces[:, 0]] & wet[faces[:, 1]] & (_m4_basin_storage_np.minimum(head[faces[:, 0]], head[faces[:, 1]]) > _m4_basin_storage_np.max(bed[faces], axis=1) + threshold)
    for first, second in faces[connected]:
        first_root, second_root = find(first), find(second)
        parent[max(first_root, second_root)] = min(first_root, second_root)
    return len({find(cell) for cell in _m4_basin_storage_np.flatnonzero(wet)})

# --- terrain_pipeline/td_basin_storage.py:51 ---
def simulate_threshold_storage(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None,
                           runoff_parameters=None, parameters=None, _face_solver=None):
    from terrain_pipeline.basin_topology import validate_basin_hierarchy as _m4_basin_storage_validate_basin_hierarchy
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_storage_readonly
    from terrain_pipeline.runoff import RunoffParameters as _m4_basin_storage_RunoffParameters
    from terrain_pipeline.runoff import _release as _m4_basin_storage_release
    _m4_basin_storage_validate_basin_hierarchy(hierarchy)
    config = _parameters(parameters) if _face_solver is None else _face_solver.parameters(parameters)
    runoff = _m4_basin_storage_RunoffParameters() if runoff_parameters is None else runoff_parameters
    if not isinstance(runoff, _m4_basin_storage_RunoffParameters):
        raise ValueError("RunoffParameters required")
    runoff.__post_init__()
    if type(dt_s) not in (int, float) or not _m4_basin_storage_math.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("positive finite physical timestep required")
    topology = hierarchy["arrays"]
    shape = topology["height_m"].shape
    bed = topology["height_m"].ravel()
    valid = topology["valid_mask"].ravel()
    rain = _m4_basin_storage_np.asarray(rain_mm_h, dtype=_m4_basin_storage_np.float64)
    if rain.ndim == 1:
        rain = _m4_basin_storage_np.broadcast_to(rain[:, None], (len(rain), bed.size)).copy()
    elif rain.ndim == 3 and rain.shape[1:] == shape:
        rain = rain.reshape(len(rain), -1).copy()
    else:
        raise ValueError("rain must be [T] or [T,z,x]")
    if not 1 <= len(rain) <= 1000 or not _m4_basin_storage_np.isfinite(rain).all() or _m4_basin_storage_np.any((rain < 0) | (rain > 1e6)):
        raise ValueError("invalid bounded rainfall")
    rain[:, ~valid] = 0
    depth = _m4_basin_storage_np.zeros(bed.size) if initial_depth_m is None else _m4_basin_storage_np.asarray(initial_depth_m, dtype=_m4_basin_storage_np.float64).reshape(-1).copy()
    if depth.shape != bed.shape or not _m4_basin_storage_np.isfinite(depth).all() or _m4_basin_storage_np.any(depth < 0) or _m4_basin_storage_np.any(depth[~valid] != 0):
        raise ValueError("invalid initial wet state")
    subdivisions = int(_m4_basin_storage_math.ceil(dt_s / config["substep_s"]))
    substeps = len(rain) * subdivisions
    faces = topology["face_cells"]
    if substeps > config["max_substeps"] or substeps * len(faces) > config["max_work_face_steps"] or len(rain) * bed.size > 4_000_000:
        raise ValueError("storage work/memory budget exceeded")
    spacing = hierarchy["metadata"]["spacing_m"]
    area = spacing ** 2
    sub_dt = dt_s / subdivisions
    hours = sub_dt / 3600
    soil = _m4_basin_storage_np.where(valid, runoff.initial_soil_mm, 0.0)
    fast = _m4_basin_storage_np.where(valid, runoff.initial_fast_mm, 0.0)
    slow = _m4_basin_storage_np.where(valid, runoff.initial_slow_mm, 0.0)
    states = {key: _m4_basin_storage_np.zeros((len(rain) + 1, bed.size)) for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm")}
    for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
        states[key][0] = value
    ledger_keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3")
    ledgers = {key: _m4_basin_storage_np.zeros((len(rain), bed.size)) for key in ledger_keys}
    forward = _m4_basin_storage_np.zeros(len(faces))
    reverse = _m4_basin_storage_np.zeros(len(faces))
    forward_duration = _m4_basin_storage_np.zeros(len(faces))
    reverse_duration = _m4_basin_storage_np.zeros(len(faces))
    routed = _m4_basin_storage_np.zeros(bed.size)
    duration = _m4_basin_storage_np.zeros(bed.size)
    pools = _m4_basin_storage_np.zeros(len(rain) + 1, _m4_basin_storage_np.int64)
    limiter_active = _m4_basin_storage_np.zeros(len(rain), _m4_basin_storage_np.int64)
    proposed_active = _m4_basin_storage_np.zeros(len(rain), _m4_basin_storage_np.int64)
    donor_limited = _m4_basin_storage_np.zeros(len(rain), _m4_basin_storage_np.int64)
    pools[0] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    first_cells, second_cells = faces[:, 0], faces[:, 1]
    sills = topology["face_level_m"]
    boundary = topology["boundary_cells"]
    boundary_rows, boundary_columns = _m4_basin_storage_np.divmod(boundary, shape[1])
    boundary_width = spacing * ((boundary_rows == 0).astype(int) + (boundary_rows == shape[0] - 1)
        + (boundary_columns == 0) + (boundary_columns == shape[1] - 1))
    receiver = topology["receiver"]
    for step in range(len(rain)):
        before = area * (depth + (soil + fast + slow) / 1000)
        for substep in range(subdivisions):
            wet = depth > config["wet_threshold_m"]
            rainfall = rain[step] * hours
            lake_rain = _m4_basin_storage_np.where(wet, rainfall, 0)
            land_rain = rainfall - lake_rain
            infiltration = _m4_basin_storage_np.minimum(_m4_basin_storage_np.minimum(land_rain, runoff.infiltration_capacity_mm_h * hours), _m4_basin_storage_np.maximum(0, runoff.soil_capacity_mm - soil))
            soil += infiltration
            soil_et = _m4_basin_storage_np.minimum(soil, runoff.potential_et_mm_h * hours)
            soil -= soil_et
            percolation = _m4_basin_storage_np.minimum(soil, runoff.percolation_mm_h * hours)
            soil -= percolation
            fast, fast_release = _m4_basin_storage_release(fast, land_rain - infiltration, sub_dt, runoff.fast_tau_s)
            slow, slow_release = _m4_basin_storage_release(slow, percolation, sub_dt, runoff.slow_tau_s)
            release = fast_release + slow_release
            depth += (lake_rain + release) / 1000
            surface_et = _m4_basin_storage_np.minimum(depth, config["surface_evaporation_mm_h"] * hours / 1000)
            depth -= surface_et
            for key, values in (("rain_volume_m3", rainfall), ("lake_rain_m3", lake_rain), ("land_rain_m3", land_rain),
                                ("soil_et_m3", soil_et), ("local_release_m3", release)):
                ledgers[key][step] += values * area / 1000
            ledgers["surface_et_m3"][step] += surface_et * area
            if _face_solver is not None and not depth.any():
                continue
            head = bed + depth
            difference = head[first_cells] - head[second_cells]
            donors = _m4_basin_storage_np.where(difference >= 0, first_cells, second_cells)
            recipients = _m4_basin_storage_np.where(difference >= 0, second_cells, first_cells)
            excess_head = _m4_basin_storage_np.maximum(0, head[donors] - _m4_basin_storage_np.maximum(sills, head[recipients]))
            proposed = config["face_conductance_m_s"] * spacing * excess_head * sub_dt
            proposed_active[step] += _m4_basin_storage_np.count_nonzero(proposed > 0)
            limiter_active[step] += _m4_basin_storage_np.count_nonzero(proposed > excess_head * area * 0.25)
            proposed = _m4_basin_storage_np.minimum(proposed, excess_head * area * 0.25)
            boundary_proposed = _m4_basin_storage_np.minimum(config["face_conductance_m_s"] * boundary_width * depth[boundary] * sub_dt,
                                           depth[boundary] * area * 0.25)
            demand = _m4_basin_storage_np.bincount(donors, weights=proposed, minlength=bed.size)
            _m4_basin_storage_np.add.at(demand, boundary, boundary_proposed)
            scale = _m4_basin_storage_np.minimum(1, _m4_basin_storage_np.divide(depth * area, demand, out=_m4_basin_storage_np.ones_like(depth), where=demand > 0))
            donor_limited[step] += _m4_basin_storage_np.count_nonzero(scale < 1)
            if _face_solver is None:
                exchange = proposed * scale[donors]
                exported = boundary_proposed * scale[boundary]
                delta = _m4_basin_storage_np.bincount(recipients, weights=exchange, minlength=bed.size) - _m4_basin_storage_np.bincount(donors, weights=exchange, minlength=bed.size)
                depth += delta / area
                depth[boundary] -= exported / area
                signed_exchange = _m4_basin_storage_np.where(difference >= 0, exchange, -exchange)
                sub_forward_duration = ((difference >= 0) & (exchange > 0)) * sub_dt
                sub_reverse_duration = ((difference < 0) & (exchange > 0)) * sub_dt
            else:
                depth, sub_forward, sub_reverse, exported, sub_forward_duration, sub_reverse_duration = _face_solver.exchange(
                    depth, bed, faces, boundary, boundary_width, spacing, sub_dt, config, shape[1])
                signed_exchange = sub_forward - sub_reverse
                exchange = abs(signed_exchange)
                donors = _m4_basin_storage_np.where(signed_exchange >= 0, first_cells, second_cells)
                recipients = _m4_basin_storage_np.where(signed_exchange >= 0, second_cells, first_cells)
                delta = _m4_basin_storage_np.bincount(second_cells, weights=signed_exchange, minlength=bed.size) - _m4_basin_storage_np.bincount(first_cells, weights=signed_exchange, minlength=bed.size)
                limiter_active[step] = 0
                donor_limited[step] = 0
            if _m4_basin_storage_np.any(depth < -1e-12) or not _m4_basin_storage_np.isfinite(depth).all():
                raise ValueError("unstable/nonfinite water state")
            depth = _m4_basin_storage_np.maximum(depth, 0)
            ledgers["internal_net_m3"][step] += delta
            _m4_basin_storage_np.add.at(ledgers["boundary_outflow_m3"][step], boundary, exported)
            forward += _m4_basin_storage_np.maximum(signed_exchange, 0) if _face_solver is None else sub_forward
            reverse += _m4_basin_storage_np.maximum(-signed_exchange, 0) if _face_solver is None else sub_reverse
            forward_duration += sub_forward_duration
            reverse_duration += sub_reverse_duration
            selected = (receiver[donors] == recipients) & (exchange > 0)
            active_donors = _m4_basin_storage_np.unique(donors[selected])
            if _face_solver is None:
                _m4_basin_storage_np.add.at(routed, donors[selected], exchange[selected])
                duration[active_donors] += sub_dt
            else:
                receiver_forward = receiver[first_cells] == second_cells
                receiver_reverse = receiver[second_cells] == first_cells
                _m4_basin_storage_np.add.at(routed, first_cells, _m4_basin_storage_np.where(receiver_forward, sub_forward, 0))
                _m4_basin_storage_np.add.at(routed, second_cells, _m4_basin_storage_np.where(receiver_reverse, sub_reverse, 0))
                _m4_basin_storage_np.add.at(duration, first_cells, _m4_basin_storage_np.where(receiver_forward, sub_forward_duration, 0))
                _m4_basin_storage_np.add.at(duration, second_cells, _m4_basin_storage_np.where(receiver_reverse, sub_reverse_duration, 0))
        after = area * (depth + (soil + fast + slow) / 1000)
        ledgers["storage_change_m3"][step] = after - before
        residual = (ledgers["rain_volume_m3"][step] + ledgers["internal_net_m3"][step] - ledgers["soil_et_m3"][step]
                    - ledgers["surface_et_m3"][step] - ledgers["boundary_outflow_m3"][step] - (after - before))
        if _m4_basin_storage_np.any(abs(residual) > 1e-6 + 1e-10 * (abs(before) + abs(after) + ledgers["rain_volume_m3"][step])):
            raise ValueError("water ledger not conservative")
        ledgers["balance_residual_m3"][step] = residual
        for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
            states[key][step + 1] = value
        pools[step + 1] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    arrays = {key: _m4_basin_storage_readonly(value) for key, value in {**states, **ledgers, "rain_mm_h": rain,
        "height_m": topology["height_m"], "valid_mask": topology["valid_mask"], "face_cells": faces,
        "receiver": receiver, "boundary_cells": boundary, "face_forward_m3": forward, "face_reverse_m3": reverse,
        "active_forward_s": forward_duration, "active_reverse_s": reverse_duration, "boundary_width_m": boundary_width,
        "routed_volume_m3": routed, "wet_duration_s": duration, "wet_pool_count": pools}.items()}
    arrays.update({"limiter_active_count": _m4_basin_storage_readonly(limiter_active), "proposed_active_count": _m4_basin_storage_readonly(proposed_active),
                   "donor_limited_count": _m4_basin_storage_readonly(donor_limited)})
    metadata = {"schema": "td-basin-storage-v1", "algorithm": "finite-time-D4-threshold-storage-v1",
        "hierarchy_identity_sha256": hierarchy["identity_sha256"], "spacing_m": spacing,
        "origin_m_xz": hierarchy["metadata"]["origin_m_xz"], "dt_s": float(dt_s), "substep_s": sub_dt,
        "parameters": config, "runoff_parameters": _m4_basin_storage_asdict(runoff), "substeps": substeps,
        "routed_semantics": "actual positive cell-to-static-receiver D4 face flux integral; duration counts active substeps",
        "pool_semantics": "both cell heads above shared sill; no equal-level projection; conservative separation on recession",
        "boundary_semantics": "all exterior D4 sides of each declared open perimeter cell; corner has two widths",
        "limiter_semantics": "each proposed face <=0.25*area*excess_head; donor-total <=available volume; timestep dependent",
        "transient_converged": False, "morphology_flux_ready": False,
        "hydraulic_ready": False, "natural_outlet_verified": False}
    if _face_solver is not None:
        metadata.update(_face_solver.metadata(config))
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_basin_storage_identity(arrays, metadata)}

# --- terrain_pipeline/td_basin_storage.py:226 ---
def validate_basin_storage(result):
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_identity
    from terrain_pipeline.runoff import RunoffParameters as _m4_basin_storage_RunoffParameters
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata["schema"] != "td-basin-storage-v1" or _m4_basin_storage_identity(arrays, metadata) != result["identity_sha256"]:
        raise ValueError("storage schema/identity mismatch")
    if metadata["algorithm"] in ("D4-analytic-face-Strang-splitting-v2", "D4-analytic-face-event-Strang-v3", "D4-threshold-exact-Strang-v4"):
        if metadata["algorithm"] == "D4-threshold-exact-Strang-v4":
            from terrain_pipeline.basin_storage import parameters_strang_split as base_parameters

            def v2_parameters(supplied):
                if metadata.get("work_profile") != "v4-threshold-pair-compiled-6e9-v1":
                    raise ValueError("unknown v4 execution profile")
                supplied = dict(supplied)
                budget = supplied.pop("max_work_face_steps")
                if type(budget) is not int or not 1 <= budget <= 6_000_000_000:
                    raise ValueError("v4 independent work budget exceeded")
                config = base_parameters(supplied)
                config["max_work_face_steps"] = budget
                return config
        elif metadata.get("work_profile") == "v2-full-refinement-6e9-v1":
            from terrain_pipeline.basin_storage import parameters_strang_refined as v2_parameters
        elif metadata["algorithm"] == "D4-analytic-face-event-Strang-v3":
            from terrain_pipeline.basin_storage import parameters_event_strang as v2_parameters
        else:
            from terrain_pipeline.basin_storage import parameters_strang_split as v2_parameters
        config = v2_parameters(metadata["parameters"])
    else:
        config = _parameters(metadata["parameters"])
    _m4_basin_storage_RunoffParameters(**metadata["runoff_parameters"])
    bed, valid = arrays["height_m"], arrays["valid_mask"]
    cells = bed.size
    rain = arrays["rain_mm_h"]
    if rain.ndim != 2 or rain.shape[1] != cells or not 1 <= len(rain) <= 1000:
        raise ValueError("invalid forcing shape")
    states = ("depth_m", "soil_mm", "fast_mm", "slow_mm")
    ledgers = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3")
    required = set(states + ledgers) | {"rain_mm_h", "height_m", "valid_mask", "face_cells", "receiver",
        "boundary_cells", "boundary_width_m", "face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s",
        "routed_volume_m3", "wet_duration_s", "wet_pool_count"}
    diagnostic_keys = {"limiter_active_count", "proposed_active_count", "donor_limited_count"}
    if set(arrays) not in (required, required | diagnostic_keys) or bed.ndim != 2 or valid.shape != bed.shape or valid.dtype != bool:
        raise ValueError("unexpected storage arrays/coverage")
    for key in states + ledgers:
        shape = (len(rain) + 1, cells) if key in states else rain.shape
        if arrays[key].shape != shape or arrays[key].dtype != _m4_basin_storage_np.float64:
            raise ValueError("invalid state/ledger shape or dtype")
    for key, value in arrays.items():
        if not _m4_basin_storage_np.isfinite(value).all():
            raise ValueError("nonfinite storage array")
        if key not in ("height_m", "receiver", "internal_net_m3", "storage_change_m3", "balance_residual_m3") and _m4_basin_storage_np.any(value < 0):
            raise ValueError("negative water account")
    for key in states + ledgers + ("rain_mm_h",):
        if _m4_basin_storage_np.any(arrays[key][:, ~valid.ravel()] != 0):
            raise ValueError("water state/forcing on unknown cells")
    area = metadata["spacing_m"] ** 2
    volume = area * (arrays["depth_m"] + sum(arrays[key] for key in ("soil_mm", "fast_mm", "slow_mm")) / 1000)

    def near(actual, expected):
        if _m4_basin_storage_np.any(abs(actual - expected) > 1e-6 + 1e-10 * (abs(actual) + abs(expected))):
            raise ValueError("nonconservative saved water ledger")

    near(arrays["storage_change_m3"], _m4_basin_storage_np.diff(volume, axis=0))
    near(arrays["rain_volume_m3"], rain * metadata["dt_s"] / 3600 * area / 1000)
    near(arrays["rain_volume_m3"], arrays["lake_rain_m3"] + arrays["land_rain_m3"])
    residual = (arrays["rain_volume_m3"] + arrays["internal_net_m3"] - arrays["soil_et_m3"]
                - arrays["surface_et_m3"] - arrays["boundary_outflow_m3"] - _m4_basin_storage_np.diff(volume, axis=0))
    near(arrays["balance_residual_m3"], residual)
    near(residual, _m4_basin_storage_np.zeros_like(residual))
    near(arrays["internal_net_m3"].sum(axis=1), _m4_basin_storage_np.zeros(len(rain)))
    faces = arrays["face_cells"]
    if faces.dtype != _m4_basin_storage_np.int64 or faces.ndim != 2 or faces.shape[1] != 2 or _m4_basin_storage_np.any((faces < 0) | (faces >= cells)):
        raise ValueError("invalid saved D4 face")
    first, second = faces[:, 0], faces[:, 1]
    columns = bed.shape[1]
    if _m4_basin_storage_np.any(abs(first // columns - second // columns) + abs(first % columns - second % columns) != 1) or not valid.ravel()[faces].all():
        raise ValueError("unknown/non-D4 exchange")
    for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        if arrays[key].shape != (len(faces),):
            raise ValueError("invalid face ledger")
    for flow, duration_key in (("face_forward_m3", "active_forward_s"), ("face_reverse_m3", "active_reverse_s")):
        if _m4_basin_storage_np.any(arrays[duration_key] > len(rain) * metadata["dt_s"] + 1e-8) or _m4_basin_storage_np.any(
                (arrays[flow] == 0) & (arrays[duration_key] != 0)):
            raise ValueError("invalid directional face activity duration")
    net = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    net_cells = _m4_basin_storage_np.bincount(second, weights=net, minlength=cells) - _m4_basin_storage_np.bincount(first, weights=net, minlength=cells)
    near(arrays["internal_net_m3"].sum(axis=0), net_cells)
    receiver = arrays["receiver"]
    if receiver.shape != (cells,) or _m4_basin_storage_np.any((receiver < -1) | (receiver >= cells)):
        raise ValueError("invalid receiver")
    expected_routed = _m4_basin_storage_np.zeros(cells)
    _m4_basin_storage_np.add.at(expected_routed, first, _m4_basin_storage_np.where(receiver[first] == second, arrays["face_forward_m3"], 0))
    _m4_basin_storage_np.add.at(expected_routed, second, _m4_basin_storage_np.where(receiver[second] == first, arrays["face_reverse_m3"], 0))
    near(arrays["routed_volume_m3"], expected_routed)
    if arrays["wet_duration_s"].shape != (cells,) or _m4_basin_storage_np.any(arrays["wet_duration_s"] > len(rain) * metadata["dt_s"] + 1e-8):
        raise ValueError("invalid positive receiver flow duration")
    if _m4_basin_storage_np.any((arrays["routed_volume_m3"] == 0) & (arrays["wet_duration_s"] != 0)):
        raise ValueError("duration without actual routed flux")
    if metadata["substeps"] > config["max_substeps"] or metadata["substeps"] * len(faces) > config["max_work_face_steps"]:
        raise ValueError("saved work budget exceeded")
    if diagnostic_keys <= set(arrays):
        for key in diagnostic_keys:
            if arrays[key].shape != (len(rain),) or arrays[key].dtype != _m4_basin_storage_np.int64:
                raise ValueError("invalid limiter diagnostic")
        if _m4_basin_storage_np.any(arrays["limiter_active_count"] > arrays["proposed_active_count"]):
            raise ValueError("invalid limiter count")
    return True

# --- terrain_pipeline/td_basin_storage.py:334 ---
def save_basin_storage(path, result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_storage_save_bundle
    _m4_basin_storage_save_bundle(path, result, validator=validate_basin_storage)

# --- terrain_pipeline/td_basin_storage.py:338 ---
def load_basin_storage(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_storage_load_bundle
    result = _m4_basin_storage_load_bundle(path, expected_sha256=expected_sha256, validator=validate_basin_storage,
                         max_bytes=STORAGE_MAX_STORAGE_BYTES, header_validator=storage_storage_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external storage identity mismatch")
    return result

# --- terrain_pipeline/td_basin_storage.py:346 ---
def storage_storage_headers(headers):
    height_shape, height_dtype = headers.get("height_m", ((), _m4_basin_storage_np.dtype("O")))
    rain_shape, rain_dtype = headers.get("rain_mm_h", ((), _m4_basin_storage_np.dtype("O")))
    if (len(height_shape) != 2 or not 1 <= _m4_basin_storage_math.prod(height_shape) <= 250000 or height_dtype != _m4_basin_storage_np.float64 or
            len(rain_shape) != 2 or rain_shape[1] != _m4_basin_storage_math.prod(height_shape) or not 1 <= rain_shape[0] <= 1000 or
            _m4_basin_storage_math.prod(rain_shape) > 4_000_000 or rain_dtype != _m4_basin_storage_np.float64):
        raise ValueError("storage header grid/time allocation rejection")
    states = {"depth_m", "soil_mm", "fast_mm", "slow_mm"}
    ledgers = {"rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3", "rain_mm_h"}
    for key in states | ledgers:
        expected_shape = (rain_shape[0] + 1, rain_shape[1]) if key in states else rain_shape
        if headers.get(key) != (expected_shape, _m4_basin_storage_np.dtype("float64")):
            raise ValueError("storage state/ledger header mismatch")
    if headers.get("valid_mask") != (height_shape, _m4_basin_storage_np.dtype(bool)):
        raise ValueError("storage mask header mismatch")
    face_shape, face_dtype = headers.get("face_cells", ((), _m4_basin_storage_np.dtype("O")))
    if len(face_shape) != 2 or face_shape[1] != 2 or face_shape[0] > 2 * rain_shape[1] or face_dtype != _m4_basin_storage_np.int64:
        raise ValueError("storage face allocation rejection")
    for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        if headers.get(key) != ((face_shape[0],), _m4_basin_storage_np.dtype("float64")):
            raise ValueError("storage directional header mismatch")
    for key, dtype in (("receiver", _m4_basin_storage_np.int64), ("routed_volume_m3", _m4_basin_storage_np.float64), ("wet_duration_s", _m4_basin_storage_np.float64)):
        if headers.get(key) != ((rain_shape[1],), _m4_basin_storage_np.dtype(dtype)):
            raise ValueError("storage receiver output header mismatch")
    if headers.get("wet_pool_count") != ((rain_shape[0] + 1,), _m4_basin_storage_np.dtype("int64")):
        raise ValueError("storage pool count header mismatch")
    boundary_shape, boundary_dtype = headers.get("boundary_cells", ((), _m4_basin_storage_np.dtype("O")))
    if len(boundary_shape) != 1 or boundary_shape[0] > rain_shape[1] or boundary_dtype != _m4_basin_storage_np.int64 or headers.get("boundary_width_m") != (boundary_shape, _m4_basin_storage_np.dtype("float64")):
        raise ValueError("storage boundary header mismatch")
    manifest_shape, manifest_dtype = headers.get("manifest", ((), _m4_basin_storage_np.dtype("O")))
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= 1048576 or manifest_dtype != _m4_basin_storage_np.uint8:
        raise ValueError("storage manifest header mismatch")
    required = states | ledgers | {"height_m", "valid_mask", "face_cells", "face_forward_m3", "face_reverse_m3",
        "active_forward_s", "active_reverse_s", "receiver", "routed_volume_m3", "wet_duration_s", "wet_pool_count",
        "boundary_cells", "boundary_width_m", "manifest"}
    diagnostic_keys = {"limiter_active_count", "proposed_active_count", "donor_limited_count"}
    if set(headers) not in (required, required | diagnostic_keys):
        raise ValueError("unexpected storage archive headers")
    if diagnostic_keys <= set(headers):
        for key in diagnostic_keys:
            if headers[key] != ((rain_shape[0],), _m4_basin_storage_np.dtype("int64")):
                raise ValueError("invalid limiter diagnostic header")

# --- terrain_pipeline/td_basin_storage_implicit.py:9 ---
STRANG_SPLIT_DEFAULT_PARAMETERS = {"substep_s": 60.0, "face_conductance_m_s": 0.6, "surface_evaporation_mm_h": 0.15,
    "wet_threshold_m": 1e-9, "max_substeps": 100000, "max_work_face_steps": 3_000_000_000}

# --- terrain_pipeline/td_basin_storage_implicit.py:13 ---
def parameters_strang_split(supplied):
    supplied = {} if supplied is None else dict(supplied)
    if set(supplied) - set(STRANG_SPLIT_DEFAULT_PARAMETERS):
        raise ValueError("unknown v2 storage parameters")
    result = {**STRANG_SPLIT_DEFAULT_PARAMETERS, **supplied}
    for key in ("substep_s", "face_conductance_m_s", "surface_evaporation_mm_h", "wet_threshold_m"):
        if type(result[key]) not in (int, float) or not _m4_basin_storage_implicit_math.isfinite(result[key]) or result[key] < 0:
            raise ValueError("invalid v2 coefficient")
    if result["substep_s"] <= 0 or result["wet_threshold_m"] <= 0:
        raise ValueError("positive v2 step/threshold required")
    for key in ("max_substeps", "max_work_face_steps"):
        if type(result[key]) is not int or not 1 <= result[key] <= STRANG_SPLIT_DEFAULT_PARAMETERS[key]:
            raise ValueError("v2 work budget rejected")
    return result

# --- terrain_pipeline/td_basin_storage_implicit.py:29 ---
def metadata_strang_split(config):
    return {"algorithm": "D4-analytic-face-Strang-splitting-v2", "limiter_semantics": "no quarter cap; each pair solves exact threshold linear ODE",
        "solver_semantics": "four disjoint D4 matching groups, symmetric forward/reverse half sweeps; exact boundary exponential half steps",
        "work_bound": "at most two analytic face visits per substep, finite declared work budget; no nonlinear iterations",
        "transient_converged": False, "morphology_flux_ready": False}

# --- terrain_pipeline/td_basin_storage_implicit.py:36 ---
def exchange_strang_two_sweep(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns, prepared=None):
    depth = depth.copy()
    first, second = faces[:, 0], faces[:, 1]
    horizontal = first // columns == second // columns
    groups = _m4_basin_storage_implicit_np.where(horizontal, first % columns % 2, 2 + first // columns % 2) if prepared is None else None
    forward = _m4_basin_storage_implicit_np.zeros(len(faces))
    reverse = _m4_basin_storage_implicit_np.zeros(len(faces))
    forward_s = _m4_basin_storage_implicit_np.zeros(len(faces))
    reverse_s = _m4_basin_storage_implicit_np.zeros(len(faces))
    conductance = config["face_conductance_m_s"]
    area = spacing ** 2
    boundary_factor = -_m4_basin_storage_implicit_np.expm1(-conductance * boundary_width / area * dt_s / 2)
    exported = depth[boundary] * boundary_factor * area
    depth[boundary] *= 1 - boundary_factor
    rate = conductance / spacing
    half = dt_s / 2
    for group in (0, 1, 2, 3, 3, 2, 1, 0):
        indices = _m4_basin_storage_implicit_np.flatnonzero(groups == group) if prepared is None else prepared[group]
        first_selected, second_selected = first[indices], second[indices]
        head_first = bed[first_selected] + depth[first_selected]
        head_second = bed[second_selected] + depth[second_selected]
        positive = head_first >= head_second
        donor = _m4_basin_storage_implicit_np.where(positive, first_selected, second_selected)
        recipient = _m4_basin_storage_implicit_np.where(positive, second_selected, first_selected)
        sill = _m4_basin_storage_implicit_np.maximum(bed[donor], bed[recipient])
        donor_head = bed[donor] + depth[donor]
        recipient_head = bed[recipient] + depth[recipient]
        excess = _m4_basin_storage_implicit_np.maximum(0, donor_head - _m4_basin_storage_implicit_np.maximum(sill, recipient_head))
        below = _m4_basin_storage_implicit_np.maximum(0, sill - recipient_head)
        first_phase = excess * (-_m4_basin_storage_implicit_np.expm1(-rate * half))
        crosses = (below > 0) & (first_phase > below)
        transfer = _m4_basin_storage_implicit_np.where(below > 0, _m4_basin_storage_implicit_np.minimum(first_phase, below), excess / 2 * (-_m4_basin_storage_implicit_np.expm1(-2 * rate * half)))
        if crosses.any() and rate > 0:
            crossing_time = -_m4_basin_storage_implicit_np.log1p(-below[crosses] / excess[crosses]) / rate
            remaining = half - crossing_time
            transfer[crosses] = below[crosses] + (excess[crosses] - below[crosses]) / 2 * (-_m4_basin_storage_implicit_np.expm1(-2 * rate * remaining))
        transfer = _m4_basin_storage_implicit_np.minimum(transfer, depth[donor])
        depth[donor] -= transfer
        depth[recipient] += transfer
        forward[indices] += _m4_basin_storage_implicit_np.where(positive, transfer * area, 0)
        reverse[indices] += _m4_basin_storage_implicit_np.where(positive, 0, transfer * area)
        forward_s[indices] += (positive & (transfer > 0)) * half
        reverse_s[indices] += (~positive & (transfer > 0)) * half
    final_export = depth[boundary] * boundary_factor * area
    depth[boundary] *= 1 - boundary_factor
    exported += final_export
    return depth, forward, reverse, exported, forward_s, reverse_s

# --- terrain_pipeline/td_basin_storage_implicit.py:85 ---
def storageimplicit_simulate(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None, runoff_parameters=None, parameters=None):
    faces = hierarchy["arrays"]["face_cells"]
    columns = hierarchy["arrays"]["height_m"].shape[1]
    first, second = faces[:, 0], faces[:, 1]
    horizontal = first // columns == second // columns
    groups = _m4_basin_storage_implicit_np.where(horizontal, first % columns % 2, 2 + first // columns % 2)
    prepared = tuple(_m4_basin_storage_implicit_np.flatnonzero(groups == group) for group in range(4))
    class PreparedSolver:
        parameters = staticmethod(globals()['parameters_strang_split'])
        metadata = staticmethod(globals()['metadata_strang_split'])

        @staticmethod
        def exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns):
            return exchange_strang_two_sweep(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns, prepared)

    return simulate_threshold_storage(hierarchy, rain_mm_h, dt_s=dt_s, initial_depth_m=initial_depth_m,
        runoff_parameters=runoff_parameters, parameters=parameters, _face_solver=PreparedSolver)

# --- terrain_pipeline/td_basin_storage_refinement.py:10 ---
REFINEMENT_PROFILE = "v2-full-refinement-6e9-v1"

# --- terrain_pipeline/td_basin_storage_refinement.py:11 ---
REFINED_MAX_WORK_FACE_STEPS = 6_000_000_000

# --- terrain_pipeline/td_basin_storage_refinement.py:15 ---
@_m4_basin_storage_refinement_njit(cache=True)
def refinement_compiled_exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s, conductance, ordered, offsets):
    depth = depth.copy()
    forward = _m4_basin_storage_refinement_np.zeros(len(faces))
    reverse = _m4_basin_storage_refinement_np.zeros(len(faces))
    forward_s = _m4_basin_storage_refinement_np.zeros(len(faces))
    reverse_s = _m4_basin_storage_refinement_np.zeros(len(faces))
    exported = _m4_basin_storage_refinement_np.zeros(len(boundary))
    area = spacing * spacing
    rate = conductance / spacing
    half = dt_s / 2
    for index in range(len(boundary)):
        cell = boundary[index]
        amount = depth[cell] * (-_m4_basin_storage_refinement_math.expm1(-conductance * boundary_width[index] / area * half))
        depth[cell] -= amount
        exported[index] += amount * area
    for sweep in range(8):
        group = sweep if sweep < 4 else 7 - sweep
        for cursor in range(offsets[group], offsets[group + 1]):
            index = ordered[cursor]
            first, second = faces[index, 0], faces[index, 1]
            head_first, head_second = bed[first] + depth[first], bed[second] + depth[second]
            positive = head_first >= head_second
            donor = first if positive else second
            recipient = second if positive else first
            sill = max(bed[donor], bed[recipient])
            excess = max(0.0, bed[donor] + depth[donor] - max(sill, bed[recipient] + depth[recipient]))
            if excess == 0 or rate == 0:
                continue
            below = max(0.0, sill - bed[recipient] - depth[recipient])
            if below > 0:
                first_phase = excess * (-_m4_basin_storage_refinement_math.expm1(-rate * half))
                amount = min(first_phase, below)
                if first_phase > below:
                    crossing_time = -_m4_basin_storage_refinement_math.log1p(-below / excess) / rate
                    amount = below + (excess - below) / 2 * (-_m4_basin_storage_refinement_math.expm1(-2 * rate * (half - crossing_time)))
            else:
                amount = excess / 2 * (-_m4_basin_storage_refinement_math.expm1(-2 * rate * half))
            amount = min(amount, depth[donor])
            depth[donor] -= amount
            depth[recipient] += amount
            if positive:
                forward[index] += amount * area
                if amount > 0:
                    forward_s[index] += half
            else:
                reverse[index] += amount * area
                if amount > 0:
                    reverse_s[index] += half
    for index in range(len(boundary)):
        cell = boundary[index]
        amount = depth[cell] * (-_m4_basin_storage_refinement_math.expm1(-conductance * boundary_width[index] / area * half))
        depth[cell] -= amount
        exported[index] += amount * area
    return depth, forward, reverse, exported, forward_s, reverse_s

# --- terrain_pipeline/td_basin_storage_refinement.py:71 ---
def parameters_strang_refined(supplied):
    supplied = {} if supplied is None else dict(supplied)
    requested_budget = supplied.pop("max_work_face_steps", REFINED_MAX_WORK_FACE_STEPS)
    if type(requested_budget) is not int or not 1 <= requested_budget <= REFINED_MAX_WORK_FACE_STEPS:
        raise ValueError("refinement work budget exceeded")
    result = parameters_strang_split(supplied)
    result["max_work_face_steps"] = requested_budget
    return result

# --- terrain_pipeline/td_basin_storage_refinement.py:81 ---
def storagerefined_simulate(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None, runoff_parameters=None, parameters=None):
    faces = hierarchy["arrays"]["face_cells"]
    columns = hierarchy["arrays"]["height_m"].shape[1]
    first, second = faces[:, 0], faces[:, 1]
    horizontal = first // columns == second // columns
    groups = _m4_basin_storage_refinement_np.where(horizontal, first % columns % 2, 2 + first // columns % 2)
    prepared = tuple(_m4_basin_storage_refinement_np.flatnonzero(groups == group) for group in range(4))
    ordered = _m4_basin_storage_refinement_np.concatenate(prepared)
    offsets = _m4_basin_storage_refinement_np.concatenate(([0], _m4_basin_storage_refinement_np.cumsum([len(values) for values in prepared])))

    class RefinementSolver:
        parameters = staticmethod(globals()['parameters_strang_refined'])

        @staticmethod
        def metadata(config):
            return {**metadata_strang_split(config), "work_profile": REFINEMENT_PROFILE,
                    "execution": "numba scalar matching sweeps; float64 no fastmath; same analytic pair law"}

        @staticmethod
        def exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns):
            return refinement_compiled_exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s,
                                      config["face_conductance_m_s"], ordered, offsets)

    return simulate_threshold_storage(hierarchy, rain_mm_h, dt_s=dt_s, initial_depth_m=initial_depth_m,
        runoff_parameters=runoff_parameters, parameters=parameters, _face_solver=RefinementSolver)

# --- terrain_pipeline/td_basin_storage_v3.py:9 ---
EVENT_STRANG_DEFAULT_PARAMETERS = {"substep_s": 60.0, "face_conductance_m_s": 0.6, "surface_evaporation_mm_h": 0.15,
    "wet_threshold_m": 1e-9, "max_substeps": 100000, "max_work_face_steps": 6000000000}

# --- terrain_pipeline/td_basin_storage_v3.py:13 ---
def parameters_event_strang(supplied):
    supplied = {} if supplied is None else dict(supplied)
    if set(supplied) - set(EVENT_STRANG_DEFAULT_PARAMETERS):
        raise ValueError("unknown v3 storage parameters")
    result = {**EVENT_STRANG_DEFAULT_PARAMETERS, **supplied}
    for key in ("substep_s", "face_conductance_m_s", "surface_evaporation_mm_h", "wet_threshold_m"):
        if type(result[key]) not in (int, float) or not _m4_basin_storage_v3_math.isfinite(result[key]) or result[key] < 0:
            raise ValueError("invalid v3 coefficient")
    if result["substep_s"] <= 0 or result["wet_threshold_m"] <= 0:
        raise ValueError("positive v3 step/threshold required")
    for key in ("max_substeps", "max_work_face_steps"):
        if type(result[key]) is not int or not 1 <= result[key] <= EVENT_STRANG_DEFAULT_PARAMETERS[key]:
            raise ValueError("v3 work budget rejected")
    return result

# --- terrain_pipeline/td_basin_storage_v3.py:29 ---
def metadata_event_strang(config):
    return {"algorithm": "D4-analytic-face-event-Strang-v3",
        "limiter_semantics": "none; exact positive pair threshold event and exponential equalization",
        "solver_semantics": "four D4 matching groups, symmetric half sweeps; pre-sill event uses full initial head difference",
        "event_semantics": "transfer=D0/2*(1-exp(-2*g*w*t/A)); sill event target=below, then excess=D0-2*below",
        "work_bound": "at most two analytic visits per face per substep; finite declared budget",
        "transient_converged": False, "morphology_flux_ready": False}

# --- terrain_pipeline/td_basin_storage_v3.py:38 ---
def exchange_event_threshold(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns, prepared=None):
    depth = depth.copy()
    first, second = faces[:, 0], faces[:, 1]
    horizontal = first // columns == second // columns
    groups = _m4_basin_storage_v3_np.where(horizontal, first % columns % 2, 2 + first // columns % 2) if prepared is None else None
    forward = _m4_basin_storage_v3_np.zeros(len(faces)); reverse = _m4_basin_storage_v3_np.zeros(len(faces))
    forward_s = _m4_basin_storage_v3_np.zeros(len(faces)); reverse_s = _m4_basin_storage_v3_np.zeros(len(faces))
    conductance = config["face_conductance_m_s"]
    area = spacing * spacing
    rate = conductance / spacing
    half = dt_s / 2
    boundary_factor = -_m4_basin_storage_v3_np.expm1(-conductance * boundary_width / area * half)
    exported = depth[boundary] * boundary_factor * area
    depth[boundary] *= 1 - boundary_factor
    for group in (0, 1, 2, 3, 3, 2, 1, 0):
        indices = _m4_basin_storage_v3_np.flatnonzero(groups == group) if prepared is None else prepared[group]
        left, right = first[indices], second[indices]
        left_head, right_head = bed[left] + depth[left], bed[right] + depth[right]
        positive = left_head >= right_head
        donor = _m4_basin_storage_v3_np.where(positive, left, right)
        recipient = _m4_basin_storage_v3_np.where(positive, right, left)
        donor_head = bed[donor] + depth[donor]
        recipient_head = bed[recipient] + depth[recipient]
        sill = _m4_basin_storage_v3_np.maximum(bed[donor], bed[recipient])
        difference = _m4_basin_storage_v3_np.maximum(0.0, donor_head - recipient_head)
        below = _m4_basin_storage_v3_np.maximum(0.0, sill - recipient_head)
        full_transfer = difference / 2 * (-_m4_basin_storage_v3_np.expm1(-2 * rate * half))
        crosses = (below > 0) & (difference > 0) & (full_transfer > below)
        transfer = _m4_basin_storage_v3_np.where(crosses, below, full_transfer)
        if rate > 0 and _m4_basin_storage_v3_np.any(crosses):
            event_time = -_m4_basin_storage_v3_np.log1p(-2 * below[crosses] / difference[crosses]) / (2 * rate)
            remaining = half - event_time
            excess = difference[crosses] - 2 * below[crosses]
            transfer[crosses] = below[crosses] + excess / 2 * (-_m4_basin_storage_v3_np.expm1(-2 * rate * remaining))
        transfer = _m4_basin_storage_v3_np.minimum(transfer, depth[donor])
        depth[donor] -= transfer
        depth[recipient] += transfer
        forward[indices] += _m4_basin_storage_v3_np.where(positive, transfer * area, 0)
        reverse[indices] += _m4_basin_storage_v3_np.where(positive, 0, transfer * area)
        forward_s[indices] += (positive & (transfer > 0)) * half
        reverse_s[indices] += (~positive & (transfer > 0)) * half
    final_export = depth[boundary] * boundary_factor * area
    depth[boundary] *= 1 - boundary_factor
    exported += final_export
    return depth, forward, reverse, exported, forward_s, reverse_s

# --- terrain_pipeline/td_basin_storage_v3.py:85 ---
def storagev3_simulate(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None,
                           runoff_parameters=None, parameters=None):
    faces = hierarchy["arrays"]["face_cells"]
    columns = hierarchy["arrays"]["height_m"].shape[1]
    first, second = faces[:, 0], faces[:, 1]
    horizontal = first // columns == second // columns
    groups = _m4_basin_storage_v3_np.where(horizontal, first % columns % 2, 2 + first // columns % 2)
    prepared = tuple(_m4_basin_storage_v3_np.flatnonzero(groups == group) for group in range(4))

    class Solver:
        parameters = staticmethod(globals()['parameters_event_strang'])
        metadata = staticmethod(globals()['metadata_event_strang'])

        @staticmethod
        def exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns):
            return exchange_event_threshold(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns, prepared)

    return simulate_threshold_storage(hierarchy, rain_mm_h, dt_s=dt_s,
        initial_depth_m=initial_depth_m, runoff_parameters=runoff_parameters, parameters=parameters, _face_solver=Solver)

# --- terrain_pipeline/td_basin_storage_v4.py:10 ---
THRESHOLD_PAIR_PROFILE = "v4-threshold-pair-compiled-6e9-v1"

# --- terrain_pipeline/td_basin_storage_v4.py:11 ---
THRESHOLD_PAIR_MAX_WORK_FACE_STEPS = 6_000_000_000

# --- terrain_pipeline/td_basin_storage_v4.py:15 ---
@_m4_basin_storage_v4_njit(cache=True)
def exchange_strang_scalar_sweep(depth, bed, faces, boundary, boundary_width, spacing, dt_s, conductance, ordered, offsets):
    depth = depth.copy()
    forward = _m4_basin_storage_v4_np.zeros(len(faces))
    reverse = _m4_basin_storage_v4_np.zeros(len(faces))
    forward_s = _m4_basin_storage_v4_np.zeros(len(faces))
    reverse_s = _m4_basin_storage_v4_np.zeros(len(faces))
    exported = _m4_basin_storage_v4_np.zeros(len(boundary))
    area = spacing * spacing
    rate = conductance / spacing
    half = dt_s / 2
    for index in range(len(boundary)):
        cell = boundary[index]
        amount = depth[cell] * (-_m4_basin_storage_v4_math.expm1(-conductance * boundary_width[index] / area * half))
        depth[cell] -= amount
        exported[index] += amount * area
    for sweep in range(8):
        group = sweep if sweep < 4 else 7 - sweep
        for cursor in range(offsets[group], offsets[group + 1]):
            index = ordered[cursor]
            first, second = faces[index, 0], faces[index, 1]
            head_first, head_second = bed[first] + depth[first], bed[second] + depth[second]
            positive = head_first >= head_second
            donor = first if positive else second
            recipient = second if positive else first
            sill = max(bed[donor], bed[recipient])
            excess = max(0.0, bed[donor] + depth[donor] - max(sill, bed[recipient] + depth[recipient]))
            if excess == 0 or rate == 0:
                continue
            below = max(0.0, sill - bed[recipient] - depth[recipient])
            if below > 0:
                first_phase = excess * (-_m4_basin_storage_v4_math.expm1(-rate * half))
                amount = min(first_phase, below)
                if first_phase > below:
                    crossing_time = -_m4_basin_storage_v4_math.log1p(-below / excess) / rate
                    amount = below + (excess - below) / 2 * (-_m4_basin_storage_v4_math.expm1(-2 * rate * (half - crossing_time)))
            else:
                amount = excess / 2 * (-_m4_basin_storage_v4_math.expm1(-2 * rate * half))
            amount = min(amount, depth[donor])
            depth[donor] -= amount
            depth[recipient] += amount
            if positive:
                forward[index] += amount * area
                if amount > 0:
                    forward_s[index] += half
            else:
                reverse[index] += amount * area
                if amount > 0:
                    reverse_s[index] += half
    for index in range(len(boundary)):
        cell = boundary[index]
        amount = depth[cell] * (-_m4_basin_storage_v4_math.expm1(-conductance * boundary_width[index] / area * half))
        depth[cell] -= amount
        exported[index] += amount * area
    return depth, forward, reverse, exported, forward_s, reverse_s

# --- terrain_pipeline/td_basin_storage_v4.py:71 ---
def parameters_threshold_pair(supplied):
    supplied = {} if supplied is None else dict(supplied)
    requested_budget = supplied.pop("max_work_face_steps", THRESHOLD_PAIR_MAX_WORK_FACE_STEPS)
    if type(requested_budget) is not int or not 1 <= requested_budget <= THRESHOLD_PAIR_MAX_WORK_FACE_STEPS:
        raise ValueError("refinement work budget exceeded")
    supplied["max_work_face_steps"] = min(requested_budget, STRANG_SPLIT_DEFAULT_PARAMETERS["max_work_face_steps"])
    result = parameters_strang_split(supplied)
    result["max_work_face_steps"] = requested_budget
    return result

# --- terrain_pipeline/td_basin_storage_v4.py:82 ---
def storagev4_simulate(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None, runoff_parameters=None, parameters=None):
    faces = hierarchy["arrays"]["face_cells"]
    columns = hierarchy["arrays"]["height_m"].shape[1]
    first, second = faces[:, 0], faces[:, 1]
    horizontal = first // columns == second // columns
    groups = _m4_basin_storage_v4_np.where(horizontal, first % columns % 2, 2 + first // columns % 2)
    prepared = tuple(_m4_basin_storage_v4_np.flatnonzero(groups == group) for group in range(4))
    ordered = _m4_basin_storage_v4_np.concatenate(prepared)
    offsets = _m4_basin_storage_v4_np.concatenate(([0], _m4_basin_storage_v4_np.cumsum([len(values) for values in prepared])))

    class RefinementSolver:
        parameters = staticmethod(globals()['parameters_threshold_pair'])

        @staticmethod
        def metadata(config):
            return {**metadata_strang_split(config), "algorithm": "D4-threshold-exact-Strang-v4", "work_profile": THRESHOLD_PAIR_PROFILE,
                    "execution": "numba scalar matching sweeps; float64 no fastmath; same analytic pair law"}

        @staticmethod
        def exchange(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns):
            return exchange_strang_scalar_sweep(depth, bed, faces, boundary, boundary_width, spacing, dt_s,
                                      config["face_conductance_m_s"], ordered, offsets)

    return simulate_threshold_storage(hierarchy, rain_mm_h, dt_s=dt_s, initial_depth_m=initial_depth_m,
        runoff_parameters=runoff_parameters, parameters=parameters, _face_solver=RefinementSolver)

# --- terrain_pipeline/td_basin_storage_v4.py:108 ---
def exchange_threshold_pair(depth, bed, faces, boundary, boundary_width, spacing, dt_s, config, columns):
    first, second = faces[:, 0], faces[:, 1]
    horizontal = first // columns == second // columns
    groups = _m4_basin_storage_v4_np.where(horizontal, first % columns % 2, 2 + first // columns % 2)
    prepared = tuple(_m4_basin_storage_v4_np.flatnonzero(groups == group) for group in range(4))
    ordered = _m4_basin_storage_v4_np.concatenate(prepared)
    offsets = _m4_basin_storage_v4_np.concatenate(([0], _m4_basin_storage_v4_np.cumsum([len(values) for values in prepared])))
    return exchange_strang_scalar_sweep(depth, bed, faces, boundary, boundary_width, spacing, dt_s,
                              config["face_conductance_m_s"], ordered, offsets)

# --- terrain_pipeline/td_basin_storage_v5.py:12 ---
SYMMETRIC_FORCING_PROFILE = "v5-symmetric-forcing-6e9-v1"

# --- terrain_pipeline/td_basin_storage_v5.py:15 ---
def _forcing(depth, soil, fast, slow, rain_rate, sub_dt, runoff, config, area, ledgers, step):
    from terrain_pipeline.runoff import _release as _m4_basin_storage_v5_release
    hours = sub_dt / 3600
    wet = depth > config["wet_threshold_m"]
    rainfall = rain_rate * hours
    lake_rain = _m4_basin_storage_v5_np.where(wet, rainfall, 0)
    land_rain = rainfall - lake_rain
    infiltration = _m4_basin_storage_v5_np.minimum(_m4_basin_storage_v5_np.minimum(land_rain, runoff.infiltration_capacity_mm_h * hours), _m4_basin_storage_v5_np.maximum(0, runoff.soil_capacity_mm - soil))
    soil += infiltration
    soil_et = _m4_basin_storage_v5_np.minimum(soil, runoff.potential_et_mm_h * hours)
    soil -= soil_et
    percolation = _m4_basin_storage_v5_np.minimum(soil, runoff.percolation_mm_h * hours)
    soil -= percolation
    fast, fast_release = _m4_basin_storage_v5_release(fast, land_rain - infiltration, sub_dt, runoff.fast_tau_s)
    slow, slow_release = _m4_basin_storage_v5_release(slow, percolation, sub_dt, runoff.slow_tau_s)
    release = fast_release + slow_release
    depth += (lake_rain + release) / 1000
    surface_et = _m4_basin_storage_v5_np.minimum(depth, config["surface_evaporation_mm_h"] * hours / 1000)
    depth -= surface_et
    for key, values in (("rain_volume_m3", rainfall), ("lake_rain_m3", lake_rain), ("land_rain_m3", land_rain),
                        ("soil_et_m3", soil_et), ("local_release_m3", release)):
        ledgers[key][step] += values * area / 1000
    ledgers["surface_et_m3"][step] += surface_et * area
    return depth, soil, fast, slow

# --- terrain_pipeline/td_basin_storage_v5.py:39 ---
def storagev5_simulate(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None,
                           runoff_parameters=None, parameters=None):
    from terrain_pipeline.basin_topology import validate_basin_hierarchy as _m4_basin_storage_v5_validate_basin_hierarchy
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_v5_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_storage_v5_readonly
    from terrain_pipeline.runoff import RunoffParameters as _m4_basin_storage_v5_RunoffParameters
    import terrain_pipeline.basin_storage as transport

    _m4_basin_storage_v5_validate_basin_hierarchy(hierarchy)
    config = parameters_threshold_pair(parameters)
    runoff = _m4_basin_storage_v5_RunoffParameters() if runoff_parameters is None else runoff_parameters
    if not isinstance(runoff, _m4_basin_storage_v5_RunoffParameters):
        raise ValueError("RunoffParameters required")
    runoff.__post_init__()
    if type(dt_s) not in (int, float) or not _m4_basin_storage_v5_math.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("positive finite physical timestep required")
    topology = hierarchy["arrays"]
    shape = topology["height_m"].shape
    bed = topology["height_m"].ravel()
    valid = topology["valid_mask"].ravel()
    rain = _m4_basin_storage_v5_np.asarray(rain_mm_h, dtype=_m4_basin_storage_v5_np.float64)
    if rain.ndim == 1:
        rain = _m4_basin_storage_v5_np.broadcast_to(rain[:, None], (len(rain), bed.size)).copy()
    elif rain.ndim == 3 and rain.shape[1:] == shape:
        rain = rain.reshape(len(rain), -1).copy()
    else:
        raise ValueError("rain must be [T] or [T,z,x]")
    if not 1 <= len(rain) <= 1000 or not _m4_basin_storage_v5_np.isfinite(rain).all() or _m4_basin_storage_v5_np.any((rain < 0) | (rain > 1e6)):
        raise ValueError("invalid bounded rainfall")
    rain[:, ~valid] = 0
    depth = _m4_basin_storage_v5_np.zeros(bed.size) if initial_depth_m is None else _m4_basin_storage_v5_np.asarray(initial_depth_m, dtype=_m4_basin_storage_v5_np.float64).reshape(-1).copy()
    if depth.shape != bed.shape or not _m4_basin_storage_v5_np.isfinite(depth).all() or _m4_basin_storage_v5_np.any(depth < 0) or _m4_basin_storage_v5_np.any(depth[~valid] != 0):
        raise ValueError("invalid initial wet state")
    subdivisions = int(_m4_basin_storage_v5_math.ceil(dt_s / config["substep_s"]))
    substeps = len(rain) * subdivisions
    faces = topology["face_cells"]
    if substeps > config["max_substeps"] or substeps * len(faces) > config["max_work_face_steps"] or len(rain) * bed.size > 4_000_000:
        raise ValueError("storage work/memory budget exceeded")
    spacing = hierarchy["metadata"]["spacing_m"]
    area = spacing ** 2
    sub_dt = dt_s / subdivisions
    hours = sub_dt / 3600
    soil = _m4_basin_storage_v5_np.where(valid, runoff.initial_soil_mm, 0.0)
    fast = _m4_basin_storage_v5_np.where(valid, runoff.initial_fast_mm, 0.0)
    slow = _m4_basin_storage_v5_np.where(valid, runoff.initial_slow_mm, 0.0)
    states = {key: _m4_basin_storage_v5_np.zeros((len(rain) + 1, bed.size)) for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm")}
    for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
        states[key][0] = value
    ledger_keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3")
    ledgers = {key: _m4_basin_storage_v5_np.zeros((len(rain), bed.size)) for key in ledger_keys}
    forward = _m4_basin_storage_v5_np.zeros(len(faces))
    reverse = _m4_basin_storage_v5_np.zeros(len(faces))
    forward_duration = _m4_basin_storage_v5_np.zeros(len(faces))
    reverse_duration = _m4_basin_storage_v5_np.zeros(len(faces))
    routed = _m4_basin_storage_v5_np.zeros(bed.size)
    duration = _m4_basin_storage_v5_np.zeros(bed.size)
    pools = _m4_basin_storage_v5_np.zeros(len(rain) + 1, _m4_basin_storage_v5_np.int64)
    limiter_active = _m4_basin_storage_v5_np.zeros(len(rain), _m4_basin_storage_v5_np.int64)
    proposed_active = _m4_basin_storage_v5_np.zeros(len(rain), _m4_basin_storage_v5_np.int64)
    donor_limited = _m4_basin_storage_v5_np.zeros(len(rain), _m4_basin_storage_v5_np.int64)
    pools[0] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    first_cells, second_cells = faces[:, 0], faces[:, 1]
    sills = topology["face_level_m"]
    boundary = topology["boundary_cells"]
    boundary_rows, boundary_columns = _m4_basin_storage_v5_np.divmod(boundary, shape[1])
    boundary_width = spacing * ((boundary_rows == 0).astype(int) + (boundary_rows == shape[0] - 1)
        + (boundary_columns == 0) + (boundary_columns == shape[1] - 1))
    receiver = topology["receiver"]
    horizontal = first_cells // shape[1] == second_cells // shape[1]
    groups = _m4_basin_storage_v5_np.where(horizontal, first_cells % shape[1] % 2, 2 + first_cells // shape[1] % 2)
    prepared = tuple(_m4_basin_storage_v5_np.flatnonzero(groups == group) for group in range(4))
    ordered = _m4_basin_storage_v5_np.concatenate(prepared)
    offsets = _m4_basin_storage_v5_np.concatenate(([0], _m4_basin_storage_v5_np.cumsum([len(values) for values in prepared])))
    for step in range(len(rain)):
        before = area * (depth + (soil + fast + slow) / 1000)
        for substep in range(subdivisions):
            depth, soil, fast, slow = _forcing(depth, soil, fast, slow, rain[step], sub_dt / 2,
                runoff, config, area, ledgers, step)
            depth, sub_forward, sub_reverse, exported, sub_forward_duration, sub_reverse_duration = exchange_strang_scalar_sweep(
                depth, bed, faces, boundary, boundary_width, spacing, sub_dt,
                config["face_conductance_m_s"], ordered, offsets)
            signed_exchange = sub_forward - sub_reverse
            delta = _m4_basin_storage_v5_np.bincount(second_cells, weights=signed_exchange, minlength=bed.size) - _m4_basin_storage_v5_np.bincount(first_cells, weights=signed_exchange, minlength=bed.size)
            if _m4_basin_storage_v5_np.any(depth < -1e-12) or not _m4_basin_storage_v5_np.isfinite(depth).all():
                raise ValueError("unstable/nonfinite water state")
            depth = _m4_basin_storage_v5_np.maximum(depth, 0)
            ledgers["internal_net_m3"][step] += delta
            _m4_basin_storage_v5_np.add.at(ledgers["boundary_outflow_m3"][step], boundary, exported)
            forward += sub_forward
            reverse += sub_reverse
            forward_duration += sub_forward_duration
            reverse_duration += sub_reverse_duration
            receiver_forward = receiver[first_cells] == second_cells
            receiver_reverse = receiver[second_cells] == first_cells
            _m4_basin_storage_v5_np.add.at(routed, first_cells, _m4_basin_storage_v5_np.where(receiver_forward, sub_forward, 0))
            _m4_basin_storage_v5_np.add.at(routed, second_cells, _m4_basin_storage_v5_np.where(receiver_reverse, sub_reverse, 0))
            _m4_basin_storage_v5_np.add.at(duration, first_cells, _m4_basin_storage_v5_np.where(receiver_forward, sub_forward_duration, 0))
            _m4_basin_storage_v5_np.add.at(duration, second_cells, _m4_basin_storage_v5_np.where(receiver_reverse, sub_reverse_duration, 0))
            depth, soil, fast, slow = _forcing(depth, soil, fast, slow, rain[step], sub_dt / 2,
                runoff, config, area, ledgers, step)
        after = area * (depth + (soil + fast + slow) / 1000)
        ledgers["storage_change_m3"][step] = after - before
        residual = (ledgers["rain_volume_m3"][step] + ledgers["internal_net_m3"][step] - ledgers["soil_et_m3"][step]
                    - ledgers["surface_et_m3"][step] - ledgers["boundary_outflow_m3"][step] - (after - before))
        if _m4_basin_storage_v5_np.any(abs(residual) > 1e-6 + 1e-10 * (abs(before) + abs(after) + ledgers["rain_volume_m3"][step])):
            raise ValueError("water ledger not conservative")
        ledgers["balance_residual_m3"][step] = residual
        for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
            states[key][step + 1] = value
        pools[step + 1] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    arrays = {key: _m4_basin_storage_v5_readonly(value) for key, value in {**states, **ledgers, "rain_mm_h": rain,
        "height_m": topology["height_m"], "valid_mask": topology["valid_mask"], "face_cells": faces,
        "receiver": receiver, "boundary_cells": boundary, "face_forward_m3": forward, "face_reverse_m3": reverse,
        "active_forward_s": forward_duration, "active_reverse_s": reverse_duration, "boundary_width_m": boundary_width,
        "routed_volume_m3": routed, "wet_duration_s": duration, "wet_pool_count": pools}.items()}
    arrays.update({"limiter_active_count": _m4_basin_storage_v5_readonly(limiter_active), "proposed_active_count": _m4_basin_storage_v5_readonly(proposed_active),
                   "donor_limited_count": _m4_basin_storage_v5_readonly(donor_limited)})
    metadata = {"schema": "td-basin-storage-v1", "algorithm": "D4-threshold-symmetric-forcing-Strang-v5", "work_profile": "v5-symmetric-forcing-6e9-v1",
        "hierarchy_identity_sha256": hierarchy["identity_sha256"], "spacing_m": spacing,
        "origin_m_xz": hierarchy["metadata"]["origin_m_xz"], "dt_s": float(dt_s), "substep_s": sub_dt,
        "parameters": config, "runoff_parameters": _m4_basin_storage_v5_asdict(runoff), "substeps": substeps,
        "routed_semantics": "actual positive cell-to-static-receiver D4 face flux integral; duration counts active substeps",
        "pool_semantics": "both cell heads above shared sill; no equal-level projection; conservative separation on recession",
        "boundary_semantics": "all exterior D4 sides of each declared open perimeter cell; corner has two widths",
        "limiter_semantics": "no quarter cap; exact compiled threshold pair",
        "forcing_semantics": "runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
        "forcing_accuracy_limit": "soil infiltration/ET/percolation remain ordered discrete updates; no full rain-soil ODE second-order claim",
        "saved_time_semantics": "state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
        "activity_semantics": "each face visited twice for substep_s/2 within transport; sum directional activity<=substep_s; forcing halves add no activity",
        "execution": "Numba v4 pair kernel float64 no fastmath",
        "transient_converged": False, "morphology_flux_ready": False,
        "hydraulic_ready": False, "natural_outlet_verified": False}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_basin_storage_v5_identity(arrays, metadata)}

# --- terrain_pipeline/td_basin_storage_v6.py:12 ---
SYMMETRIC_SSPRK2_PROFILE = "v6-simultaneous-SSPRK2-6e9-v1"

# --- terrain_pipeline/td_basin_storage_v6.py:15 ---
def forcing_split_fer(depth, soil, fast, slow, rain_rate, sub_dt, runoff, config, area, ledgers, step):
    from terrain_pipeline.runoff import _release as _m4_basin_storage_v6_release
    hours = sub_dt / 3600
    wet = depth > config["wet_threshold_m"]
    rainfall = rain_rate * hours
    lake_rain = _m4_basin_storage_v6_np.where(wet, rainfall, 0)
    land_rain = rainfall - lake_rain
    infiltration = _m4_basin_storage_v6_np.minimum(_m4_basin_storage_v6_np.minimum(land_rain, runoff.infiltration_capacity_mm_h * hours), _m4_basin_storage_v6_np.maximum(0, runoff.soil_capacity_mm - soil))
    soil += infiltration
    soil_et = _m4_basin_storage_v6_np.minimum(soil, runoff.potential_et_mm_h * hours)
    soil -= soil_et
    percolation = _m4_basin_storage_v6_np.minimum(soil, runoff.percolation_mm_h * hours)
    soil -= percolation
    fast, fast_release = _m4_basin_storage_v6_release(fast, land_rain - infiltration, sub_dt, runoff.fast_tau_s)
    slow, slow_release = _m4_basin_storage_v6_release(slow, percolation, sub_dt, runoff.slow_tau_s)
    release = fast_release + slow_release
    depth += (lake_rain + release) / 1000
    surface_et = _m4_basin_storage_v6_np.minimum(depth, config["surface_evaporation_mm_h"] * hours / 1000)
    depth -= surface_et
    for key, values in (("rain_volume_m3", rainfall), ("lake_rain_m3", lake_rain), ("land_rain_m3", land_rain),
                        ("soil_et_m3", soil_et), ("local_release_m3", release)):
        ledgers[key][step] += values * area / 1000
    ledgers["surface_et_m3"][step] += surface_et * area
    return depth, soil, fast, slow

# --- terrain_pipeline/td_basin_storage_v6.py:39 ---
def storagev6_simulate(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None,
                           runoff_parameters=None, parameters=None):
    from terrain_pipeline.basin_topology import validate_basin_hierarchy as _m4_basin_storage_v6_validate_basin_hierarchy
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_v6_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_storage_v6_readonly
    from terrain_pipeline.runoff import RunoffParameters as _m4_basin_storage_v6_RunoffParameters
    import terrain_pipeline.basin_storage as transport

    _m4_basin_storage_v6_validate_basin_hierarchy(hierarchy)
    from terrain_pipeline.basin_storage import parameters_threshold_pair as parse_parameters
    config = parse_parameters({"substep_s": 5.0, **({} if parameters is None else parameters)})
    runoff = _m4_basin_storage_v6_RunoffParameters() if runoff_parameters is None else runoff_parameters
    if not isinstance(runoff, _m4_basin_storage_v6_RunoffParameters):
        raise ValueError("RunoffParameters required")
    runoff.__post_init__()
    if type(dt_s) not in (int, float) or not _m4_basin_storage_v6_math.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("positive finite physical timestep required")
    topology = hierarchy["arrays"]
    shape = topology["height_m"].shape
    bed = topology["height_m"].ravel()
    valid = topology["valid_mask"].ravel()
    rain = _m4_basin_storage_v6_np.asarray(rain_mm_h, dtype=_m4_basin_storage_v6_np.float64)
    if rain.ndim == 1:
        rain = _m4_basin_storage_v6_np.broadcast_to(rain[:, None], (len(rain), bed.size)).copy()
    elif rain.ndim == 3 and rain.shape[1:] == shape:
        rain = rain.reshape(len(rain), -1).copy()
    else:
        raise ValueError("rain must be [T] or [T,z,x]")
    if not 1 <= len(rain) <= 1000 or not _m4_basin_storage_v6_np.isfinite(rain).all() or _m4_basin_storage_v6_np.any((rain < 0) | (rain > 1e6)):
        raise ValueError("invalid bounded rainfall")
    rain[:, ~valid] = 0
    depth = _m4_basin_storage_v6_np.zeros(bed.size) if initial_depth_m is None else _m4_basin_storage_v6_np.asarray(initial_depth_m, dtype=_m4_basin_storage_v6_np.float64).reshape(-1).copy()
    if depth.shape != bed.shape or not _m4_basin_storage_v6_np.isfinite(depth).all() or _m4_basin_storage_v6_np.any(depth < 0) or _m4_basin_storage_v6_np.any(depth[~valid] != 0):
        raise ValueError("invalid initial wet state")
    subdivisions = int(_m4_basin_storage_v6_math.ceil(dt_s / config["substep_s"]))
    substeps = len(rain) * subdivisions
    faces = topology["face_cells"]
    if substeps > config["max_substeps"] or substeps * len(faces) > config["max_work_face_steps"] or len(rain) * bed.size > 4_000_000:
        raise ValueError("storage work/memory budget exceeded")
    spacing = hierarchy["metadata"]["spacing_m"]
    area = spacing ** 2
    sub_dt = dt_s / subdivisions
    soil = _m4_basin_storage_v6_np.where(valid, runoff.initial_soil_mm, 0.0)
    fast = _m4_basin_storage_v6_np.where(valid, runoff.initial_fast_mm, 0.0)
    slow = _m4_basin_storage_v6_np.where(valid, runoff.initial_slow_mm, 0.0)
    states = {key: _m4_basin_storage_v6_np.zeros((len(rain) + 1, bed.size)) for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm")}
    for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
        states[key][0] = value
    ledger_keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3")
    ledgers = {key: _m4_basin_storage_v6_np.zeros((len(rain), bed.size)) for key in ledger_keys}
    forward = _m4_basin_storage_v6_np.zeros(len(faces))
    reverse = _m4_basin_storage_v6_np.zeros(len(faces))
    forward_duration = _m4_basin_storage_v6_np.zeros(len(faces))
    reverse_duration = _m4_basin_storage_v6_np.zeros(len(faces))
    routed = _m4_basin_storage_v6_np.zeros(bed.size)
    duration = _m4_basin_storage_v6_np.zeros(bed.size)
    pools = _m4_basin_storage_v6_np.zeros(len(rain) + 1, _m4_basin_storage_v6_np.int64)
    limiter_active = _m4_basin_storage_v6_np.zeros(len(rain), _m4_basin_storage_v6_np.int64)
    proposed_active = _m4_basin_storage_v6_np.zeros(len(rain), _m4_basin_storage_v6_np.int64)
    donor_limited = _m4_basin_storage_v6_np.zeros(len(rain), _m4_basin_storage_v6_np.int64)
    pools[0] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    first_cells, second_cells = faces[:, 0], faces[:, 1]
    boundary = topology["boundary_cells"]
    boundary_rows, boundary_columns = _m4_basin_storage_v6_np.divmod(boundary, shape[1])
    boundary_width = spacing * ((boundary_rows == 0).astype(int) + (boundary_rows == shape[0] - 1)
        + (boundary_columns == 0) + (boundary_columns == shape[1] - 1))
    receiver = topology["receiver"]
    unused_indices = _m4_basin_storage_v6_np.array([], dtype=_m4_basin_storage_v6_np.int64)
    cfl = validate_cfl(faces, boundary, boundary_width, spacing, sub_dt, config["face_conductance_m_s"], bed.size)
    for step in range(len(rain)):
        before = area * (depth + (soil + fast + slow) / 1000)
        for substep in range(subdivisions):
            depth, soil, fast, slow = forcing_split_fer(depth, soil, fast, slow, rain[step], sub_dt / 2,
                runoff, config, area, ledgers, step)
            depth, sub_forward, sub_reverse, exported, sub_forward_duration, sub_reverse_duration = _compiled_exchange(
                depth, bed, faces, boundary, boundary_width, spacing, sub_dt,
                config["face_conductance_m_s"], unused_indices, unused_indices)
            signed_exchange = sub_forward - sub_reverse
            delta = _m4_basin_storage_v6_np.bincount(second_cells, weights=signed_exchange, minlength=bed.size) - _m4_basin_storage_v6_np.bincount(first_cells, weights=signed_exchange, minlength=bed.size)
            if _m4_basin_storage_v6_np.any(depth < -1e-12) or not _m4_basin_storage_v6_np.isfinite(depth).all():
                raise ValueError("unstable/nonfinite water state")
            if _m4_basin_storage_v6_np.any(depth < 0):
                raise ValueError("negative SSP-RK2 depth; clamp forbidden")
            ledgers["internal_net_m3"][step] += delta
            _m4_basin_storage_v6_np.add.at(ledgers["boundary_outflow_m3"][step], boundary, exported)
            forward += sub_forward
            reverse += sub_reverse
            forward_duration += sub_forward_duration
            reverse_duration += sub_reverse_duration
            receiver_forward = receiver[first_cells] == second_cells
            receiver_reverse = receiver[second_cells] == first_cells
            _m4_basin_storage_v6_np.add.at(routed, first_cells, _m4_basin_storage_v6_np.where(receiver_forward, sub_forward, 0))
            _m4_basin_storage_v6_np.add.at(routed, second_cells, _m4_basin_storage_v6_np.where(receiver_reverse, sub_reverse, 0))
            _m4_basin_storage_v6_np.add.at(duration, first_cells, _m4_basin_storage_v6_np.where(receiver_forward, sub_forward_duration, 0))
            _m4_basin_storage_v6_np.add.at(duration, second_cells, _m4_basin_storage_v6_np.where(receiver_reverse, sub_reverse_duration, 0))
            depth, soil, fast, slow = forcing_split_fer(depth, soil, fast, slow, rain[step], sub_dt / 2,
                runoff, config, area, ledgers, step)
        after = area * (depth + (soil + fast + slow) / 1000)
        ledgers["storage_change_m3"][step] = after - before
        residual = (ledgers["rain_volume_m3"][step] + ledgers["internal_net_m3"][step] - ledgers["soil_et_m3"][step]
                    - ledgers["surface_et_m3"][step] - ledgers["boundary_outflow_m3"][step] - (after - before))
        if _m4_basin_storage_v6_np.any(abs(residual) > 1e-6 + 1e-10 * (abs(before) + abs(after) + ledgers["rain_volume_m3"][step])):
            raise ValueError("water ledger not conservative")
        ledgers["balance_residual_m3"][step] = residual
        for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
            states[key][step + 1] = value
        pools[step + 1] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    arrays = {key: _m4_basin_storage_v6_readonly(value) for key, value in {**states, **ledgers, "rain_mm_h": rain,
        "height_m": topology["height_m"], "valid_mask": topology["valid_mask"], "face_cells": faces,
        "receiver": receiver, "boundary_cells": boundary, "face_forward_m3": forward, "face_reverse_m3": reverse,
        "active_forward_s": forward_duration, "active_reverse_s": reverse_duration, "boundary_width_m": boundary_width,
        "routed_volume_m3": routed, "wet_duration_s": duration, "wet_pool_count": pools}.items()}
    arrays.update({"limiter_active_count": _m4_basin_storage_v6_readonly(limiter_active), "proposed_active_count": _m4_basin_storage_v6_readonly(proposed_active),
                   "donor_limited_count": _m4_basin_storage_v6_readonly(donor_limited)})
    metadata = {"schema": "td-basin-storage-v1", "algorithm": "D4-threshold-symmetric-forcing-SSPRK2-v6", "work_profile": "v6-simultaneous-SSPRK2-6e9-v1",
        "hierarchy_identity_sha256": hierarchy["identity_sha256"], "spacing_m": spacing,
        "origin_m_xz": hierarchy["metadata"]["origin_m_xz"], "dt_s": float(dt_s), "substep_s": sub_dt,
        "parameters": config, "runoff_parameters": _m4_basin_storage_v6_asdict(runoff), "substeps": substeps,
        "routed_semantics": "actual positive cell-to-static-receiver D4 face flux integral; duration counts active substeps",
        "pool_semantics": "both cell heads above shared sill; no equal-level projection; conservative separation on recession",
        "boundary_semantics": "all exterior D4 sides of each declared open perimeter cell; corner has two widths",
        "limiter_semantics": "no cap or clamp; positivity CFL for simultaneous Euler stages",
        "forcing_semantics": "runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
        "forcing_accuracy_limit": "soil infiltration/ET/percolation remain ordered discrete updates; no full rain-soil ODE second-order claim",
        "saved_time_semantics": "state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
        "activity_semantics": "RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity",
        "positivity_cfl": cfl, "execution": "Numba simultaneous all-face SSP-RK2 float64 no fastmath",
        "transient_converged": False, "morphology_flux_ready": False,
        "hydraulic_ready": False, "natural_outlet_verified": False}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_basin_storage_v6_identity(arrays, metadata)}

# --- terrain_pipeline/td_basin_storage_v7.py:13 ---
COMPENSATED_SSPRK2_PROFILE = "v7-compensated-forcing-SSPRK2-6e9-v1"

# --- terrain_pipeline/td_basin_storage_v7.py:16 ---
def storagev7_simulate(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None,
                           runoff_parameters=None, parameters=None):
    from terrain_pipeline.basin_topology import validate_basin_hierarchy as _m4_basin_storage_v7_validate_basin_hierarchy
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_v7_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_storage_v7_readonly
    from terrain_pipeline.runoff import RunoffParameters as _m4_basin_storage_v7_RunoffParameters
    import terrain_pipeline.basin_storage as transport

    _m4_basin_storage_v7_validate_basin_hierarchy(hierarchy)
    from terrain_pipeline.basin_storage import parameters_threshold_pair as parse_parameters
    config = parse_parameters({"substep_s": 5.0, **({} if parameters is None else parameters)})
    runoff = _m4_basin_storage_v7_RunoffParameters() if runoff_parameters is None else runoff_parameters
    if not isinstance(runoff, _m4_basin_storage_v7_RunoffParameters):
        raise ValueError("RunoffParameters required")
    runoff.__post_init__()
    if type(dt_s) not in (int, float) or not _m4_basin_storage_v7_math.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("positive finite physical timestep required")
    topology = hierarchy["arrays"]
    shape = topology["height_m"].shape
    bed = topology["height_m"].ravel()
    valid = topology["valid_mask"].ravel()
    rain = _m4_basin_storage_v7_np.asarray(rain_mm_h, dtype=_m4_basin_storage_v7_np.float64)
    if rain.ndim == 1:
        rain = _m4_basin_storage_v7_np.broadcast_to(rain[:, None], (len(rain), bed.size)).copy()
    elif rain.ndim == 3 and rain.shape[1:] == shape:
        rain = rain.reshape(len(rain), -1).copy()
    else:
        raise ValueError("rain must be [T] or [T,z,x]")
    if not 1 <= len(rain) <= 1000 or not _m4_basin_storage_v7_np.isfinite(rain).all() or _m4_basin_storage_v7_np.any((rain < 0) | (rain > 1e6)):
        raise ValueError("invalid bounded rainfall")
    rain[:, ~valid] = 0
    depth = _m4_basin_storage_v7_np.zeros(bed.size) if initial_depth_m is None else _m4_basin_storage_v7_np.asarray(initial_depth_m, dtype=_m4_basin_storage_v7_np.float64).reshape(-1).copy()
    if depth.shape != bed.shape or not _m4_basin_storage_v7_np.isfinite(depth).all() or _m4_basin_storage_v7_np.any(depth < 0) or _m4_basin_storage_v7_np.any(depth[~valid] != 0):
        raise ValueError("invalid initial wet state")
    subdivisions = int(_m4_basin_storage_v7_math.ceil(dt_s / config["substep_s"]))
    substeps = len(rain) * subdivisions
    faces = topology["face_cells"]
    if substeps > config["max_substeps"] or substeps * len(faces) > config["max_work_face_steps"] or len(rain) * bed.size > 4_000_000:
        raise ValueError("storage work/memory budget exceeded")
    spacing = hierarchy["metadata"]["spacing_m"]
    area = spacing ** 2
    sub_dt = dt_s / subdivisions
    soil = _m4_basin_storage_v7_np.where(valid, runoff.initial_soil_mm, 0.0)
    fast = _m4_basin_storage_v7_np.where(valid, runoff.initial_fast_mm, 0.0)
    slow = _m4_basin_storage_v7_np.where(valid, runoff.initial_slow_mm, 0.0)
    states = {key: _m4_basin_storage_v7_np.zeros((len(rain) + 1, bed.size)) for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm")}
    for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
        states[key][0] = value
    ledger_keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3")
    ledgers = {key: _m4_basin_storage_v7_np.zeros((len(rain), bed.size)) for key in ledger_keys}
    forward = _m4_basin_storage_v7_np.zeros(len(faces))
    reverse = _m4_basin_storage_v7_np.zeros(len(faces))
    forward_duration = _m4_basin_storage_v7_np.zeros(len(faces))
    reverse_duration = _m4_basin_storage_v7_np.zeros(len(faces))
    routed = _m4_basin_storage_v7_np.zeros(bed.size)
    duration = _m4_basin_storage_v7_np.zeros(bed.size)
    pools = _m4_basin_storage_v7_np.zeros(len(rain) + 1, _m4_basin_storage_v7_np.int64)
    limiter_active = _m4_basin_storage_v7_np.zeros(len(rain), _m4_basin_storage_v7_np.int64)
    proposed_active = _m4_basin_storage_v7_np.zeros(len(rain), _m4_basin_storage_v7_np.int64)
    donor_limited = _m4_basin_storage_v7_np.zeros(len(rain), _m4_basin_storage_v7_np.int64)
    pools[0] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    first_cells, second_cells = faces[:, 0], faces[:, 1]
    boundary = topology["boundary_cells"]
    boundary_rows, boundary_columns = _m4_basin_storage_v7_np.divmod(boundary, shape[1])
    boundary_width = spacing * ((boundary_rows == 0).astype(int) + (boundary_rows == shape[0] - 1)
        + (boundary_columns == 0) + (boundary_columns == shape[1] - 1))
    receiver = topology["receiver"]
    unused_indices = _m4_basin_storage_v7_np.array([], dtype=_m4_basin_storage_v7_np.int64)
    cfl = validate_cfl(faces, boundary, boundary_width, spacing, sub_dt, config["face_conductance_m_s"], bed.size)
    forcing_keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "local_release_m3", "surface_et_m3")
    errors = {key: _m4_basin_storage_v7_np.zeros(bed.size) for key in ("depth", "soil", "fast", "slow") + forcing_keys}
    for step in range(len(rain)):
        reset_hourly_ledger_compensation(errors, forcing_keys)
        before = area * (depth + (soil + fast + slow) / 1000)
        for substep in range(subdivisions):
            depth, soil, fast, slow = forcing(depth, soil, fast, slow, rain[step], sub_dt / 2,
                runoff, config, area, ledgers, step, errors)
            depth, sub_forward, sub_reverse, exported, sub_forward_duration, sub_reverse_duration = _compiled_exchange(
                depth, bed, faces, boundary, boundary_width, spacing, sub_dt,
                config["face_conductance_m_s"], unused_indices, unused_indices)
            reset_transport_compensation(errors)
            signed_exchange = sub_forward - sub_reverse
            delta = _m4_basin_storage_v7_np.bincount(second_cells, weights=signed_exchange, minlength=bed.size) - _m4_basin_storage_v7_np.bincount(first_cells, weights=signed_exchange, minlength=bed.size)
            if _m4_basin_storage_v7_np.any(depth < -1e-12) or not _m4_basin_storage_v7_np.isfinite(depth).all():
                raise ValueError("unstable/nonfinite water state")
            if _m4_basin_storage_v7_np.any(depth < 0):
                raise ValueError("negative SSP-RK2 depth; clamp forbidden")
            ledgers["internal_net_m3"][step] += delta
            _m4_basin_storage_v7_np.add.at(ledgers["boundary_outflow_m3"][step], boundary, exported)
            forward += sub_forward
            reverse += sub_reverse
            forward_duration += sub_forward_duration
            reverse_duration += sub_reverse_duration
            receiver_forward = receiver[first_cells] == second_cells
            receiver_reverse = receiver[second_cells] == first_cells
            _m4_basin_storage_v7_np.add.at(routed, first_cells, _m4_basin_storage_v7_np.where(receiver_forward, sub_forward, 0))
            _m4_basin_storage_v7_np.add.at(routed, second_cells, _m4_basin_storage_v7_np.where(receiver_reverse, sub_reverse, 0))
            _m4_basin_storage_v7_np.add.at(duration, first_cells, _m4_basin_storage_v7_np.where(receiver_forward, sub_forward_duration, 0))
            _m4_basin_storage_v7_np.add.at(duration, second_cells, _m4_basin_storage_v7_np.where(receiver_reverse, sub_reverse_duration, 0))
            depth, soil, fast, slow = forcing(depth, soil, fast, slow, rain[step], sub_dt / 2,
                runoff, config, area, ledgers, step, errors)
        after = area * (depth + (soil + fast + slow) / 1000)
        ledgers["storage_change_m3"][step] = after - before
        residual = (ledgers["rain_volume_m3"][step] + ledgers["internal_net_m3"][step] - ledgers["soil_et_m3"][step]
                    - ledgers["surface_et_m3"][step] - ledgers["boundary_outflow_m3"][step] - (after - before))
        if _m4_basin_storage_v7_np.any(abs(residual) > 1e-6 + 1e-10 * (abs(before) + abs(after) + ledgers["rain_volume_m3"][step])):
            raise ValueError("water ledger not conservative")
        ledgers["balance_residual_m3"][step] = residual
        for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
            states[key][step + 1] = value
        pools[step + 1] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    arrays = {key: _m4_basin_storage_v7_readonly(value) for key, value in {**states, **ledgers, "rain_mm_h": rain,
        "height_m": topology["height_m"], "valid_mask": topology["valid_mask"], "face_cells": faces,
        "receiver": receiver, "boundary_cells": boundary, "face_forward_m3": forward, "face_reverse_m3": reverse,
        "active_forward_s": forward_duration, "active_reverse_s": reverse_duration, "boundary_width_m": boundary_width,
        "routed_volume_m3": routed, "wet_duration_s": duration, "wet_pool_count": pools}.items()}
    arrays.update({"limiter_active_count": _m4_basin_storage_v7_readonly(limiter_active), "proposed_active_count": _m4_basin_storage_v7_readonly(proposed_active),
                   "donor_limited_count": _m4_basin_storage_v7_readonly(donor_limited)})
    metadata = {"schema": "td-basin-storage-v1", "algorithm": "D4-threshold-compensated-forcing-SSPRK2-v7", "work_profile": "v7-compensated-forcing-SSPRK2-6e9-v1",
        "hierarchy_identity_sha256": hierarchy["identity_sha256"], "spacing_m": spacing,
        "origin_m_xz": hierarchy["metadata"]["origin_m_xz"], "dt_s": float(dt_s), "substep_s": sub_dt,
        "parameters": config, "runoff_parameters": _m4_basin_storage_v7_asdict(runoff), "substeps": substeps,
        "routed_semantics": "actual positive cell-to-static-receiver D4 face flux integral; duration counts active substeps",
        "pool_semantics": "both cell heads above shared sill; no equal-level projection; conservative separation on recession",
        "boundary_semantics": "all exterior D4 sides of each declared open perimeter cell; corner has two widths",
        "limiter_semantics": "no cap or clamp; positivity CFL for simultaneous Euler stages",
        "forcing_semantics": "runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
        "forcing_accuracy_limit": "soil infiltration/ET/percolation remain ordered discrete updates; no full rain-soil ODE second-order claim",
        "saved_time_semantics": "state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
        "activity_semantics": "RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity",
        "compensation_semantics": "soil/fast/slow increments and forcing ledgers compensated; ledger errors reset hourly; depth error reset after transport replacement; exact full-inventory removal retires compensation",
        "positivity_cfl": cfl, "execution": "Numba simultaneous all-face SSP-RK2 float64 no fastmath",
        "transient_converged": False, "morphology_flux_ready": False,
        "hydraulic_ready": False, "natural_outlet_verified": False}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_basin_storage_v7_identity(arrays, metadata)}

# --- terrain_pipeline/td_basin_storage_continuation.py:13 ---
HOUR_PAGES_PROFILE = "v8-hour-pages-v7-SSPRK2"

# --- terrain_pipeline/td_basin_storage_continuation.py:16 ---
def continuation_simulate(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None,
                           runoff_parameters=None, parameters=None, checkpoint=None, forcing_identity=None, full_rain_mm_h=None):
    from terrain_pipeline.basin_topology import validate_basin_hierarchy as _m4_basin_storage_continuation_validate_basin_hierarchy
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_continuation_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_storage_continuation_readonly
    from terrain_pipeline.runoff import RunoffParameters as _m4_basin_storage_continuation_RunoffParameters
    import terrain_pipeline.basin_storage as transport

    _m4_basin_storage_continuation_validate_basin_hierarchy(hierarchy)
    from terrain_pipeline.basin_storage import parameters_threshold_pair as parse_parameters
    config = parse_parameters({"substep_s": 5.0, **({} if parameters is None else parameters)})
    runoff = _m4_basin_storage_continuation_RunoffParameters() if runoff_parameters is None else runoff_parameters
    if not isinstance(runoff, _m4_basin_storage_continuation_RunoffParameters):
        raise ValueError("RunoffParameters required")
    runoff.__post_init__()
    if type(dt_s) not in (int, float) or not _m4_basin_storage_continuation_math.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("positive finite physical timestep required")
    topology = hierarchy["arrays"]
    shape = topology["height_m"].shape
    bed = topology["height_m"].ravel()
    valid = topology["valid_mask"].ravel()
    rain = _m4_basin_storage_continuation_np.asarray(rain_mm_h, dtype=_m4_basin_storage_continuation_np.float64)
    if rain.ndim == 1:
        rain = _m4_basin_storage_continuation_np.broadcast_to(rain[:, None], (len(rain), bed.size)).copy()
    elif rain.ndim == 3 and rain.shape[1:] == shape:
        rain = rain.reshape(len(rain), -1).copy()
    else:
        raise ValueError("rain must be [T] or [T,z,x]")
    if not 1 <= len(rain) <= 1000 or not _m4_basin_storage_continuation_np.isfinite(rain).all() or _m4_basin_storage_continuation_np.any((rain < 0) | (rain > 1e6)):
        raise ValueError("invalid bounded rainfall")
    rain[:, ~valid] = 0
    if full_rain_mm_h is None:
        raise ValueError("fixed complete forcing required for continuation")
    if checkpoint is not None:
        from terrain_pipeline.basin_storage import checkpoint_validate_checkpoint as validate_checkpoint
        validate_checkpoint(checkpoint)
    full_rain = _m4_basin_storage_continuation_np.asarray(full_rain_mm_h,dtype=_m4_basin_storage_continuation_np.float64)
    if full_rain.ndim not in (1,3) or not 1<=len(full_rain)<=1000 or len(full_rain)*bed.size>4_000_000 or not _m4_basin_storage_continuation_np.isfinite(full_rain).all() or _m4_basin_storage_continuation_np.any((full_rain<0)|(full_rain>1e6)) or (full_rain.ndim==3 and full_rain.shape[1:]!=shape):
        raise ValueError("invalid complete forcing shape/values")
    if full_rain.ndim==3:
        full_rain=full_rain.copy()
        full_rain[:,~topology["valid_mask"]]=0
    expected_forcing = _m4_basin_storage_continuation_identity({"rain_mm_h":full_rain},{"dt_s":float(dt_s)})
    if forcing_identity != expected_forcing:
        raise ValueError("complete forcing identity mismatch")
    offset = 0 if checkpoint is None else int(checkpoint["metadata"]["elapsed_s"] / dt_s)
    if offset+len(rain)>len(full_rain):
        raise ValueError("forcing slice beyond complete plan")
    expected_rain = full_rain[offset:offset+len(rain)]
    if expected_rain.ndim == 1:
        expected_rain = _m4_basin_storage_continuation_np.broadcast_to(expected_rain[:,None],rain.shape).copy()
    else:
        expected_rain = expected_rain.reshape(rain.shape).copy()
    expected_rain[:,~valid] = 0
    if not _m4_basin_storage_continuation_np.array_equal(expected_rain,rain):
        raise ValueError("checkpoint hour/forcing slice mismatch")
    depth = _m4_basin_storage_continuation_np.zeros(bed.size) if initial_depth_m is None else _m4_basin_storage_continuation_np.asarray(initial_depth_m, dtype=_m4_basin_storage_continuation_np.float64).reshape(-1).copy()
    if depth.shape != bed.shape or not _m4_basin_storage_continuation_np.isfinite(depth).all() or _m4_basin_storage_continuation_np.any(depth < 0) or _m4_basin_storage_continuation_np.any(depth[~valid] != 0):
        raise ValueError("invalid initial wet state")
    subdivisions = int(_m4_basin_storage_continuation_math.ceil(dt_s / config["substep_s"]))
    substeps = len(rain) * subdivisions
    faces = topology["face_cells"]
    if substeps > config["max_substeps"] or substeps * len(faces) > config["max_work_face_steps"] or len(rain) * bed.size > 4_000_000:
        raise ValueError("storage work/memory budget exceeded")
    spacing = hierarchy["metadata"]["spacing_m"]
    area = spacing ** 2
    sub_dt = dt_s / subdivisions
    soil = _m4_basin_storage_continuation_np.where(valid, runoff.initial_soil_mm, 0.0)
    fast = _m4_basin_storage_continuation_np.where(valid, runoff.initial_fast_mm, 0.0)
    slow = _m4_basin_storage_continuation_np.where(valid, runoff.initial_slow_mm, 0.0)
    if checkpoint is not None:
        if initial_depth_m is not None:
            raise ValueError("initial depth and checkpoint are mutually exclusive")
        from terrain_pipeline.basin_storage import checkpoint_validate_checkpoint as validate_checkpoint
        validate_checkpoint(checkpoint)
        if checkpoint["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or checkpoint["metadata"]["parameters"] != config or checkpoint["metadata"]["runoff_parameters"] != _m4_basin_storage_continuation_asdict(runoff) or checkpoint["metadata"]["forcing_identity"] != forcing_identity:
            raise ValueError("checkpoint hierarchy/config/forcing mismatch")
        if checkpoint["metadata"]["cells"] != bed.size or checkpoint["metadata"]["faces"] != len(faces) or checkpoint["metadata"]["dt_s"] != float(dt_s) or checkpoint["metadata"]["substep_s"] != sub_dt:
            raise ValueError("checkpoint geometry/time mismatch")
        depth, soil, fast, slow = (checkpoint["arrays"][key].copy() for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm"))
        if any(_m4_basin_storage_continuation_np.any(values[~valid] != 0) for values in (depth,soil,fast,slow)) or _m4_basin_storage_continuation_np.any(topology["protected_mask"]):
            raise ValueError("checkpoint unknown/protected inventory unsupported")
    states = {key: _m4_basin_storage_continuation_np.zeros((len(rain) + 1, bed.size)) for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm")}
    for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
        states[key][0] = value
    ledger_keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3")
    ledgers = {key: _m4_basin_storage_continuation_np.zeros((len(rain), bed.size)) for key in ledger_keys}
    forward = _m4_basin_storage_continuation_np.zeros(len(faces))
    reverse = _m4_basin_storage_continuation_np.zeros(len(faces))
    forward_duration = _m4_basin_storage_continuation_np.zeros(len(faces))
    reverse_duration = _m4_basin_storage_continuation_np.zeros(len(faces))
    routed = _m4_basin_storage_continuation_np.zeros(bed.size)
    duration = _m4_basin_storage_continuation_np.zeros(bed.size)
    pools = _m4_basin_storage_continuation_np.zeros(len(rain) + 1, _m4_basin_storage_continuation_np.int64)
    limiter_active = _m4_basin_storage_continuation_np.zeros(len(rain), _m4_basin_storage_continuation_np.int64)
    proposed_active = _m4_basin_storage_continuation_np.zeros(len(rain), _m4_basin_storage_continuation_np.int64)
    donor_limited = _m4_basin_storage_continuation_np.zeros(len(rain), _m4_basin_storage_continuation_np.int64)
    pools[0] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    first_cells, second_cells = faces[:, 0], faces[:, 1]
    boundary = topology["boundary_cells"]
    boundary_rows, boundary_columns = _m4_basin_storage_continuation_np.divmod(boundary, shape[1])
    boundary_width = spacing * ((boundary_rows == 0).astype(int) + (boundary_rows == shape[0] - 1)
        + (boundary_columns == 0) + (boundary_columns == shape[1] - 1))
    receiver = topology["receiver"]
    unused_indices = _m4_basin_storage_continuation_np.array([], dtype=_m4_basin_storage_continuation_np.int64)
    cfl = validate_cfl(faces, boundary, boundary_width, spacing, sub_dt, config["face_conductance_m_s"], bed.size)
    forcing_keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "local_release_m3", "surface_et_m3")
    errors = {key: _m4_basin_storage_continuation_np.zeros(bed.size) for key in ("depth", "soil", "fast", "slow") + forcing_keys}
    if checkpoint is not None:
        for key in ("depth", "soil", "fast", "slow"):
            errors[key][:] = checkpoint["arrays"]["error_" + key]
    for step in range(len(rain)):
        reset_hourly_ledger_compensation(errors, forcing_keys)
        before = area * (depth + (soil + fast + slow) / 1000)
        for substep in range(subdivisions):
            depth, soil, fast, slow = forcing(depth, soil, fast, slow, rain[step], sub_dt / 2,
                runoff, config, area, ledgers, step, errors)
            depth, sub_forward, sub_reverse, exported, sub_forward_duration, sub_reverse_duration = _compiled_exchange(
                depth, bed, faces, boundary, boundary_width, spacing, sub_dt,
                config["face_conductance_m_s"], unused_indices, unused_indices)
            reset_transport_compensation(errors)
            signed_exchange = sub_forward - sub_reverse
            delta = _m4_basin_storage_continuation_np.bincount(second_cells, weights=signed_exchange, minlength=bed.size) - _m4_basin_storage_continuation_np.bincount(first_cells, weights=signed_exchange, minlength=bed.size)
            if _m4_basin_storage_continuation_np.any(depth < -1e-12) or not _m4_basin_storage_continuation_np.isfinite(depth).all():
                raise ValueError("unstable/nonfinite water state")
            if _m4_basin_storage_continuation_np.any(depth < 0):
                raise ValueError("negative SSP-RK2 depth; clamp forbidden")
            ledgers["internal_net_m3"][step] += delta
            _m4_basin_storage_continuation_np.add.at(ledgers["boundary_outflow_m3"][step], boundary, exported)
            forward += sub_forward
            reverse += sub_reverse
            forward_duration += sub_forward_duration
            reverse_duration += sub_reverse_duration
            receiver_forward = receiver[first_cells] == second_cells
            receiver_reverse = receiver[second_cells] == first_cells
            _m4_basin_storage_continuation_np.add.at(routed, first_cells, _m4_basin_storage_continuation_np.where(receiver_forward, sub_forward, 0))
            _m4_basin_storage_continuation_np.add.at(routed, second_cells, _m4_basin_storage_continuation_np.where(receiver_reverse, sub_reverse, 0))
            _m4_basin_storage_continuation_np.add.at(duration, first_cells, _m4_basin_storage_continuation_np.where(receiver_forward, sub_forward_duration, 0))
            _m4_basin_storage_continuation_np.add.at(duration, second_cells, _m4_basin_storage_continuation_np.where(receiver_reverse, sub_reverse_duration, 0))
            depth, soil, fast, slow = forcing(depth, soil, fast, slow, rain[step], sub_dt / 2,
                runoff, config, area, ledgers, step, errors)
        after = area * (depth + (soil + fast + slow) / 1000)
        ledgers["storage_change_m3"][step] = after - before
        residual = (ledgers["rain_volume_m3"][step] + ledgers["internal_net_m3"][step] - ledgers["soil_et_m3"][step]
                    - ledgers["surface_et_m3"][step] - ledgers["boundary_outflow_m3"][step] - (after - before))
        if _m4_basin_storage_continuation_np.any(abs(residual) > 1e-6 + 1e-10 * (abs(before) + abs(after) + ledgers["rain_volume_m3"][step])):
            raise ValueError("water ledger not conservative")
        ledgers["balance_residual_m3"][step] = residual
        for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
            states[key][step + 1] = value
        pools[step + 1] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    arrays = {key: _m4_basin_storage_continuation_readonly(value) for key, value in {**states, **ledgers, "rain_mm_h": rain,
        "height_m": topology["height_m"], "valid_mask": topology["valid_mask"], "face_cells": faces,
        "receiver": receiver, "boundary_cells": boundary, "face_forward_m3": forward, "face_reverse_m3": reverse,
        "active_forward_s": forward_duration, "active_reverse_s": reverse_duration, "boundary_width_m": boundary_width,
        "routed_volume_m3": routed, "wet_duration_s": duration, "wet_pool_count": pools}.items()}
    arrays.update({"limiter_active_count": _m4_basin_storage_continuation_readonly(limiter_active), "proposed_active_count": _m4_basin_storage_continuation_readonly(proposed_active),
                   "donor_limited_count": _m4_basin_storage_continuation_readonly(donor_limited)})
    metadata = {"schema": "td-basin-storage-v1", "algorithm": "D4-threshold-compensated-forcing-SSPRK2-v7", "work_profile": "v7-compensated-forcing-SSPRK2-6e9-v1",
        "hierarchy_identity_sha256": hierarchy["identity_sha256"], "spacing_m": spacing,
        "origin_m_xz": hierarchy["metadata"]["origin_m_xz"], "dt_s": float(dt_s), "substep_s": sub_dt,
        "parameters": config, "runoff_parameters": _m4_basin_storage_continuation_asdict(runoff), "substeps": substeps,
        "routed_semantics": "actual positive cell-to-static-receiver D4 face flux integral; duration counts active substeps",
        "pool_semantics": "both cell heads above shared sill; no equal-level projection; conservative separation on recession",
        "boundary_semantics": "all exterior D4 sides of each declared open perimeter cell; corner has two widths",
        "limiter_semantics": "no cap or clamp; positivity CFL for simultaneous Euler stages",
        "forcing_semantics": "runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
        "forcing_accuracy_limit": "soil infiltration/ET/percolation remain ordered discrete updates; no full rain-soil ODE second-order claim",
        "saved_time_semantics": "state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
        "activity_semantics": "RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity",
        "compensation_semantics": "soil/fast/slow increments and forcing ledgers compensated; ledger errors reset hourly; depth error reset after transport replacement; exact full-inventory removal retires compensation",
        "positivity_cfl": cfl, "execution": "Numba simultaneous all-face SSP-RK2 float64 no fastmath",
        "transient_converged": False, "morphology_flux_ready": False,
        "hydraulic_ready": False, "natural_outlet_verified": False}
    start_time = 0 if checkpoint is None else checkpoint["metadata"]["elapsed_s"]
    metadata.update({"algorithm":"D4-threshold-checkpoint-SSPRK2-v8", "work_profile":HOUR_PAGES_PROFILE,
        "chunk_start_s":start_time,"chunk_end_s":start_time+len(rain)*dt_s,"forcing_identity":forcing_identity,"forcing_hour_offset":offset,
        "saved_time_semantics":"state0 is checkpoint time; state[k] at chunk_start_s+k*dt_s; ledger[k] covers local hour k",
        "initialization_semantics":"first page default runoff initial stores; subsequent pages restore all checkpoint stores and compensation"})
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_basin_storage_continuation_identity(arrays, metadata)}
    checkpoint_arrays = {key: _m4_basin_storage_continuation_readonly(value) for key, value in (("depth_m",depth),("soil_mm",soil),("fast_mm",fast),("slow_mm",slow))}
    for key in ("depth", "soil", "fast", "slow"):
        checkpoint_arrays["error_" + key] = _m4_basin_storage_continuation_readonly(errors[key])
    for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s", "routed_volume_m3", "wet_duration_s"):
        previous = 0 if checkpoint is None else checkpoint["arrays"]["cumulative_" + key]
        checkpoint_arrays["cumulative_" + key] = _m4_basin_storage_continuation_readonly(previous + arrays[key])
    elapsed = 0 if checkpoint is None else checkpoint["metadata"]["elapsed_s"]
    count = 0 if checkpoint is None else checkpoint["metadata"]["substeps"]
    work = 0 if checkpoint is None else checkpoint["metadata"]["work_face_steps"]
    checkpoint_metadata = {"schema":"td-storage-continuation-v1", "execution_profile":"v8-hour-pages-v7-SSPRK2",
        "hierarchy_identity_sha256":hierarchy["identity_sha256"], "parameters":config, "runoff_parameters":_m4_basin_storage_continuation_asdict(runoff),
        "forcing_identity":forcing_identity, "dt_s":float(dt_s),"substep_s":sub_dt,"elapsed_s":elapsed+len(rain)*dt_s, "substeps":count+substeps,
        "work_face_steps":work+substeps*len(faces), "cells":bed.size,"faces":len(faces),
        "last_page_storage_identity":result["identity_sha256"], "hydraulic_ready":False,"transient_converged":False}
    saved_checkpoint = {"arrays":checkpoint_arrays,"metadata":checkpoint_metadata,"identity_sha256":_m4_basin_storage_continuation_identity(checkpoint_arrays,checkpoint_metadata)}
    return {"storage":result,"checkpoint":saved_checkpoint}

# --- terrain_pipeline/td_basin_storage_compiled.py:8 ---
COMPILED_HOUR_PROFILE = "v8-compiled-hour-loop-experimental-v1"

# --- terrain_pipeline/td_basin_storage_compiled.py:12 ---
@_m4_basin_storage_compiled_njit(cache=True)
def _add(value, increment, error):
    if increment < 0 and increment == -value:
        return 0., 0.
    adjusted = increment-error
    updated = value+adjusted
    if updated < 0 or not _m4_basin_storage_compiled_math.isfinite(updated):
        raise ValueError("negative/nonfinite compensated inventory")
    return updated,(updated-value)-adjusted

# --- terrain_pipeline/td_basin_storage_compiled.py:23 ---
@_m4_basin_storage_compiled_njit(cache=True)
def _release(storage,incoming,seconds,tau):
    ratio=seconds/tau
    fraction=-_m4_basin_storage_compiled_math.expm1(-ratio)
    coefficient=ratio/2-ratio**2/6+ratio**3/24 if ratio<1e-4 else 1-fraction/ratio
    return storage*fraction+incoming*coefficient

# --- terrain_pipeline/td_basin_storage_compiled.py:31 ---
@_m4_basin_storage_compiled_njit(cache=True)
def forcing_compensated(states,errors,rain,seconds,runoff,config,area,ledger,ledger_errors):
    hours=seconds/3600
    for cell in range(states.shape[1]):
        rainfall=rain[cell]*hours
        lake=rainfall if states[0,cell]>config[1] else 0.
        land=rainfall-lake
        infiltration=min(min(land,runoff[0]*hours),max(0.,runoff[1]-states[1,cell]))
        states[1,cell],errors[1,cell]=_add(states[1,cell],infiltration,errors[1,cell])
        soil_et=min(states[1,cell],runoff[2]*hours)
        states[1,cell],errors[1,cell]=_add(states[1,cell],-soil_et,errors[1,cell])
        percolation=min(states[1,cell],runoff[3]*hours)
        states[1,cell],errors[1,cell]=_add(states[1,cell],-percolation,errors[1,cell])
        fast_release=_release(states[2,cell],land-infiltration,seconds,runoff[4])
        slow_release=_release(states[3,cell],percolation,seconds,runoff[5])
        states[2,cell],errors[2,cell]=_add(states[2,cell],land-infiltration-fast_release,errors[2,cell])
        states[3,cell],errors[3,cell]=_add(states[3,cell],percolation-slow_release,errors[3,cell])
        release=fast_release+slow_release
        states[0,cell],errors[0,cell]=_add(states[0,cell],(lake+release)/1000,errors[0,cell])
        surface_et=min(states[0,cell],config[2]*hours/1000)
        states[0,cell],errors[0,cell]=_add(states[0,cell],-surface_et,errors[0,cell])
        increments=(rainfall*area/1000,lake*area/1000,land*area/1000,soil_et*area/1000,release*area/1000,surface_et*area)
        for index in range(6):
            ledger[index,cell],ledger_errors[index,cell]=_add(ledger[index,cell],increments[index],ledger_errors[index,cell])

# --- terrain_pipeline/td_basin_storage_compiled.py:57 ---
@_m4_basin_storage_compiled_njit(cache=True)
def advance_hour_compensated(states,errors,rain,bed,faces,boundary,widths,receiver,spacing,seconds,subdivisions,runoff,config):
    ledger=_m4_basin_storage_compiled_np.zeros((8,states.shape[1]))
    ledger_errors=_m4_basin_storage_compiled_np.zeros((6,states.shape[1]))
    forward=_m4_basin_storage_compiled_np.zeros(len(faces));reverse=_m4_basin_storage_compiled_np.zeros(len(faces))
    forward_s=_m4_basin_storage_compiled_np.zeros(len(faces));reverse_s=_m4_basin_storage_compiled_np.zeros(len(faces))
    routed=_m4_basin_storage_compiled_np.zeros(states.shape[1]);duration=_m4_basin_storage_compiled_np.zeros(states.shape[1])
    indices=_m4_basin_storage_compiled_np.empty(0,_m4_basin_storage_compiled_np.int64)
    for substep in range(subdivisions):
        forcing_compensated(states,errors,rain,seconds/2,runoff,config,spacing*spacing,ledger,ledger_errors)
        depth,positive,negative,exported,positive_s,negative_s=_compiled_exchange(states[0],bed,faces,boundary,widths,spacing,seconds,config[0],indices,indices)
        states[0]=depth
        errors[0]=0
        incoming=_m4_basin_storage_compiled_np.zeros(states.shape[1]);outgoing=_m4_basin_storage_compiled_np.zeros(states.shape[1])
        for index in range(len(faces)):
            first,second=faces[index,0],faces[index,1]
            signed=positive[index]-negative[index]
            incoming[second]+=signed;outgoing[first]+=signed
            forward[index]+=positive[index];reverse[index]+=negative[index]
            forward_s[index]+=positive_s[index];reverse_s[index]+=negative_s[index]
            if receiver[first]==second:
                routed[first]+=positive[index];duration[first]+=positive_s[index]
            if receiver[second]==first:
                routed[second]+=negative[index];duration[second]+=negative_s[index]
        for cell in range(states.shape[1]):
            ledger[6,cell]+=incoming[cell]-outgoing[cell]
        for index in range(len(boundary)):
            ledger[7,boundary[index]]+=exported[index]
        forcing_compensated(states,errors,rain,seconds/2,runoff,config,spacing*spacing,ledger,ledger_errors)
    return states,errors,ledger,forward,reverse,forward_s,reverse_s,routed,duration

# --- terrain_pipeline/td_basin_storage_compiled_driver.py:14 ---
COMPILED_DRIVER_PROFILE = "v9-compiled-hour-loop-v8-equivalent-v1"

# --- terrain_pipeline/td_basin_storage_compiled_driver.py:17 ---
def compileddriver_simulate(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None,
                           runoff_parameters=None, parameters=None, checkpoint=None, forcing_identity=None, full_rain_mm_h=None):
    from terrain_pipeline.basin_topology import validate_basin_hierarchy as _m4_basin_storage_compiled_driver_validate_basin_hierarchy
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_compiled_driver_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_storage_compiled_driver_readonly
    from terrain_pipeline.runoff import RunoffParameters as _m4_basin_storage_compiled_driver_RunoffParameters
    import terrain_pipeline.basin_storage as transport

    _m4_basin_storage_compiled_driver_validate_basin_hierarchy(hierarchy)
    if _m4_basin_storage_compiled_driver_np.any(hierarchy["arrays"]["protected_mask"]):
        raise ValueError("protected cells not supported by compiled execution")
    from terrain_pipeline.basin_storage import parameters_threshold_pair as parse_parameters
    config = parse_parameters({"substep_s": 5.0, **({} if parameters is None else parameters)})
    runoff = _m4_basin_storage_compiled_driver_RunoffParameters() if runoff_parameters is None else runoff_parameters
    if not isinstance(runoff, _m4_basin_storage_compiled_driver_RunoffParameters):
        raise ValueError("RunoffParameters required")
    runoff.__post_init__()
    if type(dt_s) not in (int, float) or not _m4_basin_storage_compiled_driver_math.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("positive finite physical timestep required")
    topology = hierarchy["arrays"]
    shape = topology["height_m"].shape
    bed = topology["height_m"].ravel()
    valid = topology["valid_mask"].ravel()
    rain = _m4_basin_storage_compiled_driver_np.asarray(rain_mm_h, dtype=_m4_basin_storage_compiled_driver_np.float64)
    if rain.ndim not in (1,3) or not 1<=len(rain)<=1000 or len(rain)*bed.size>4_000_000:
        raise ValueError("rain time/cell allocation budget exceeded before broadcast")
    if rain.ndim == 1:
        rain = _m4_basin_storage_compiled_driver_np.broadcast_to(rain[:, None], (len(rain), bed.size)).copy()
    elif rain.ndim == 3 and rain.shape[1:] == shape:
        rain = rain.reshape(len(rain), -1).copy()
    else:
        raise ValueError("rain must be [T] or [T,z,x]")
    if not 1 <= len(rain) <= 1000 or not _m4_basin_storage_compiled_driver_np.isfinite(rain).all() or _m4_basin_storage_compiled_driver_np.any((rain < 0) | (rain > 1e6)):
        raise ValueError("invalid bounded rainfall")
    rain[:, ~valid] = 0
    if full_rain_mm_h is None:
        raise ValueError("fixed complete forcing required for continuation")
    if checkpoint is not None:
        from terrain_pipeline.basin_storage import compiled_validate_checkpoint as validate_checkpoint
        validate_checkpoint(checkpoint)
    full_rain = _m4_basin_storage_compiled_driver_np.asarray(full_rain_mm_h,dtype=_m4_basin_storage_compiled_driver_np.float64)
    if full_rain.ndim not in (1,3) or not 1<=len(full_rain)<=1000 or len(full_rain)*bed.size>4_000_000 or not _m4_basin_storage_compiled_driver_np.isfinite(full_rain).all() or _m4_basin_storage_compiled_driver_np.any((full_rain<0)|(full_rain>1e6)) or (full_rain.ndim==3 and full_rain.shape[1:]!=shape):
        raise ValueError("invalid complete forcing shape/values")
    if full_rain.ndim==3:
        full_rain=full_rain.copy()
        full_rain[:,~topology["valid_mask"]]=0
    expected_forcing = _m4_basin_storage_compiled_driver_identity({"rain_mm_h":full_rain},{"dt_s":float(dt_s)})
    if forcing_identity != expected_forcing:
        raise ValueError("complete forcing identity mismatch")
    offset = 0 if checkpoint is None else int(checkpoint["metadata"]["elapsed_s"] / dt_s)
    if offset+len(rain)>len(full_rain):
        raise ValueError("forcing slice beyond complete plan")
    expected_rain = full_rain[offset:offset+len(rain)]
    if expected_rain.ndim == 1:
        expected_rain = _m4_basin_storage_compiled_driver_np.broadcast_to(expected_rain[:,None],rain.shape).copy()
    else:
        expected_rain = expected_rain.reshape(rain.shape).copy()
    expected_rain[:,~valid] = 0
    if not _m4_basin_storage_compiled_driver_np.array_equal(expected_rain,rain):
        raise ValueError("checkpoint hour/forcing slice mismatch")
    depth = _m4_basin_storage_compiled_driver_np.zeros(bed.size) if initial_depth_m is None else _m4_basin_storage_compiled_driver_np.asarray(initial_depth_m, dtype=_m4_basin_storage_compiled_driver_np.float64).reshape(-1).copy()
    if depth.shape != bed.shape or not _m4_basin_storage_compiled_driver_np.isfinite(depth).all() or _m4_basin_storage_compiled_driver_np.any(depth < 0) or _m4_basin_storage_compiled_driver_np.any(depth[~valid] != 0):
        raise ValueError("invalid initial wet state")
    subdivisions = int(_m4_basin_storage_compiled_driver_math.ceil(dt_s / config["substep_s"]))
    substeps = len(rain) * subdivisions
    faces = topology["face_cells"]
    if substeps > config["max_substeps"] or substeps * len(faces) > config["max_work_face_steps"] or len(rain) * bed.size > 4_000_000:
        raise ValueError("storage work/memory budget exceeded")
    spacing = hierarchy["metadata"]["spacing_m"]
    area = spacing ** 2
    sub_dt = dt_s / subdivisions
    soil = _m4_basin_storage_compiled_driver_np.where(valid, runoff.initial_soil_mm, 0.0)
    fast = _m4_basin_storage_compiled_driver_np.where(valid, runoff.initial_fast_mm, 0.0)
    slow = _m4_basin_storage_compiled_driver_np.where(valid, runoff.initial_slow_mm, 0.0)
    if checkpoint is not None:
        if initial_depth_m is not None:
            raise ValueError("initial depth and checkpoint are mutually exclusive")
        from terrain_pipeline.basin_storage import compiled_validate_checkpoint as validate_checkpoint
        validate_checkpoint(checkpoint)
        if checkpoint["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or checkpoint["metadata"]["parameters"] != config or checkpoint["metadata"]["runoff_parameters"] != _m4_basin_storage_compiled_driver_asdict(runoff) or checkpoint["metadata"]["forcing_identity"] != forcing_identity:
            raise ValueError("checkpoint hierarchy/config/forcing mismatch")
        if checkpoint["metadata"]["cells"] != bed.size or checkpoint["metadata"]["faces"] != len(faces) or checkpoint["metadata"]["dt_s"] != float(dt_s) or checkpoint["metadata"]["substep_s"] != sub_dt:
            raise ValueError("checkpoint geometry/time mismatch")
        expected_count = int(checkpoint["metadata"]["elapsed_s"] / dt_s) * subdivisions
        if checkpoint["metadata"]["substeps"] != expected_count:
            raise ValueError("checkpoint actual derived count mismatch")
        depth, soil, fast, slow = (checkpoint["arrays"][key].copy() for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm"))
        if any(_m4_basin_storage_compiled_driver_np.any(values[~valid] != 0) for values in (depth,soil,fast,slow)) or _m4_basin_storage_compiled_driver_np.any(topology["protected_mask"]):
            raise ValueError("checkpoint unknown/protected inventory unsupported")
        if any(_m4_basin_storage_compiled_driver_np.any(checkpoint["arrays"]["error_"+key][~valid] != 0) for key in ("depth","soil","fast","slow")):
            raise ValueError("checkpoint compensation on unknown cells forbidden")
        if any(_m4_basin_storage_compiled_driver_np.any(checkpoint["arrays"]["cumulative_"+key][~valid]!=0) for key in ("routed_volume_m3","wet_duration_s")):
            raise ValueError("checkpoint cumulative receiver evidence on unknown cells forbidden")
    states = {key: _m4_basin_storage_compiled_driver_np.zeros((len(rain) + 1, bed.size)) for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm")}
    for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
        states[key][0] = value
    ledger_keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3")
    ledgers = {key: _m4_basin_storage_compiled_driver_np.zeros((len(rain), bed.size)) for key in ledger_keys}
    forward = _m4_basin_storage_compiled_driver_np.zeros(len(faces))
    reverse = _m4_basin_storage_compiled_driver_np.zeros(len(faces))
    forward_duration = _m4_basin_storage_compiled_driver_np.zeros(len(faces))
    reverse_duration = _m4_basin_storage_compiled_driver_np.zeros(len(faces))
    routed = _m4_basin_storage_compiled_driver_np.zeros(bed.size)
    duration = _m4_basin_storage_compiled_driver_np.zeros(bed.size)
    pools = _m4_basin_storage_compiled_driver_np.zeros(len(rain) + 1, _m4_basin_storage_compiled_driver_np.int64)
    limiter_active = _m4_basin_storage_compiled_driver_np.zeros(len(rain), _m4_basin_storage_compiled_driver_np.int64)
    proposed_active = _m4_basin_storage_compiled_driver_np.zeros(len(rain), _m4_basin_storage_compiled_driver_np.int64)
    donor_limited = _m4_basin_storage_compiled_driver_np.zeros(len(rain), _m4_basin_storage_compiled_driver_np.int64)
    pools[0] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    first_cells, second_cells = faces[:, 0], faces[:, 1]
    boundary = topology["boundary_cells"]
    boundary_rows, boundary_columns = _m4_basin_storage_compiled_driver_np.divmod(boundary, shape[1])
    boundary_width = spacing * ((boundary_rows == 0).astype(int) + (boundary_rows == shape[0] - 1)
        + (boundary_columns == 0) + (boundary_columns == shape[1] - 1))
    receiver = topology["receiver"]
    unused_indices = _m4_basin_storage_compiled_driver_np.array([], dtype=_m4_basin_storage_compiled_driver_np.int64)
    cfl = validate_cfl(faces, boundary, boundary_width, spacing, sub_dt, config["face_conductance_m_s"], bed.size)
    forcing_keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "local_release_m3", "surface_et_m3")
    errors = {key: _m4_basin_storage_compiled_driver_np.zeros(bed.size) for key in ("depth", "soil", "fast", "slow") + forcing_keys}
    if checkpoint is not None:
        for key in ("depth", "soil", "fast", "slow"):
            errors[key][:] = checkpoint["arrays"]["error_" + key]
    for step in range(len(rain)):
        reset_hourly_ledger_compensation(errors, forcing_keys)
        before = area * (depth + (soil + fast + slow) / 1000)
        states_buffer = _m4_basin_storage_compiled_driver_np.vstack((depth,soil,fast,slow))
        errors_buffer = _m4_basin_storage_compiled_driver_np.vstack(tuple(errors[key] for key in ("depth","soil","fast","slow")))
        runoff_buffer = _m4_basin_storage_compiled_driver_np.array([runoff.infiltration_capacity_mm_h,runoff.soil_capacity_mm,runoff.potential_et_mm_h,
                                  runoff.percolation_mm_h,runoff.fast_tau_s,runoff.slow_tau_s])
        config_buffer = _m4_basin_storage_compiled_driver_np.array([config["face_conductance_m_s"],config["wet_threshold_m"],config["surface_evaporation_mm_h"]])
        output = advance_hour_compensated(states_buffer,errors_buffer,rain[step],bed,faces,boundary,boundary_width,receiver,
                              spacing,sub_dt,subdivisions,runoff_buffer,config_buffer)
        depth,soil,fast,slow = output[0]
        for index,key in enumerate(("depth","soil","fast","slow")):
            errors[key][:] = output[1][index]
        for index,key in enumerate(("rain_volume_m3","lake_rain_m3","land_rain_m3","soil_et_m3","local_release_m3","surface_et_m3","internal_net_m3","boundary_outflow_m3")):
            ledgers[key][step] = output[2][index]
        forward += output[3]
        reverse += output[4]
        forward_duration += output[5]
        reverse_duration += output[6]
        routed += output[7]
        duration += output[8]
        after = area * (depth + (soil + fast + slow) / 1000)
        ledgers["storage_change_m3"][step] = after - before
        residual = (ledgers["rain_volume_m3"][step] + ledgers["internal_net_m3"][step] - ledgers["soil_et_m3"][step]
                    - ledgers["surface_et_m3"][step] - ledgers["boundary_outflow_m3"][step] - (after - before))
        if _m4_basin_storage_compiled_driver_np.any(abs(residual) > 1e-6 + 1e-10 * (abs(before) + abs(after) + ledgers["rain_volume_m3"][step])):
            raise ValueError("water ledger not conservative")
        ledgers["balance_residual_m3"][step] = residual
        for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
            states[key][step + 1] = value
        pools[step + 1] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    arrays = {key: _m4_basin_storage_compiled_driver_readonly(value) for key, value in {**states, **ledgers, "rain_mm_h": rain,
        "height_m": topology["height_m"], "valid_mask": topology["valid_mask"], "face_cells": faces,
        "receiver": receiver, "boundary_cells": boundary, "face_forward_m3": forward, "face_reverse_m3": reverse,
        "active_forward_s": forward_duration, "active_reverse_s": reverse_duration, "boundary_width_m": boundary_width,
        "routed_volume_m3": routed, "wet_duration_s": duration, "wet_pool_count": pools}.items()}
    arrays.update({"limiter_active_count": _m4_basin_storage_compiled_driver_readonly(limiter_active), "proposed_active_count": _m4_basin_storage_compiled_driver_readonly(proposed_active),
                   "donor_limited_count": _m4_basin_storage_compiled_driver_readonly(donor_limited)})
    metadata = {"schema": "td-basin-storage-v1", "algorithm": "D4-threshold-compensated-forcing-SSPRK2-v7", "work_profile": "v7-compensated-forcing-SSPRK2-6e9-v1",
        "hierarchy_identity_sha256": hierarchy["identity_sha256"], "spacing_m": spacing,
        "origin_m_xz": hierarchy["metadata"]["origin_m_xz"], "dt_s": float(dt_s), "substep_s": sub_dt,
        "parameters": config, "runoff_parameters": _m4_basin_storage_compiled_driver_asdict(runoff), "substeps": substeps,
        "routed_semantics": "actual positive cell-to-static-receiver D4 face flux integral; duration counts active substeps",
        "pool_semantics": "both cell heads above shared sill; no equal-level projection; conservative separation on recession",
        "boundary_semantics": "all exterior D4 sides of each declared open perimeter cell; corner has two widths",
        "limiter_semantics": "no cap or clamp; positivity CFL for simultaneous Euler stages",
        "forcing_semantics": "runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
        "forcing_accuracy_limit": "soil infiltration/ET/percolation remain ordered discrete updates; no full rain-soil ODE second-order claim",
        "saved_time_semantics": "state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
        "activity_semantics": "RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity",
        "compensation_semantics": "soil/fast/slow increments and forcing ledgers compensated; ledger errors reset hourly; depth error reset after transport replacement; exact full-inventory removal retires compensation",
        "positivity_cfl": cfl, "execution": "Numba full hourly forcing/SSPRK2 loop float64 no fastmath; execution equivalence pending",
        "transient_converged": False, "morphology_flux_ready": False,
        "hydraulic_ready": False, "natural_outlet_verified": False}
    start_time = 0 if checkpoint is None else checkpoint["metadata"]["elapsed_s"]
    metadata.update({"algorithm":"D4-threshold-compiled-hour-SSPRK2-v9", "work_profile":COMPILED_DRIVER_PROFILE,
        "chunk_start_s":start_time,"chunk_end_s":start_time+len(rain)*dt_s,"forcing_identity":forcing_identity,"forcing_hour_offset":offset,
        "saved_time_semantics":"state0 is checkpoint time; state[k] at chunk_start_s+k*dt_s; ledger[k] covers local hour k",
        "initialization_semantics":"first page default runoff initial stores; subsequent pages restore all checkpoint stores and compensation"})
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_basin_storage_compiled_driver_identity(arrays, metadata)}
    checkpoint_arrays = {key: _m4_basin_storage_compiled_driver_readonly(value) for key, value in (("depth_m",depth),("soil_mm",soil),("fast_mm",fast),("slow_mm",slow))}
    for key in ("depth", "soil", "fast", "slow"):
        checkpoint_arrays["error_" + key] = _m4_basin_storage_compiled_driver_readonly(errors[key])
    for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s", "routed_volume_m3", "wet_duration_s"):
        previous = 0 if checkpoint is None else checkpoint["arrays"]["cumulative_" + key]
        checkpoint_arrays["cumulative_" + key] = _m4_basin_storage_compiled_driver_readonly(previous + arrays[key])
    elapsed = 0 if checkpoint is None else checkpoint["metadata"]["elapsed_s"]
    count = 0 if checkpoint is None else checkpoint["metadata"]["substeps"]
    work = 0 if checkpoint is None else checkpoint["metadata"]["work_face_steps"]
    checkpoint_metadata = {"schema":"td-storage-continuation-v1", "execution_profile":"v9-compiled-hour-loop-v8-equivalent-v1",
        "hierarchy_identity_sha256":hierarchy["identity_sha256"], "parameters":config, "runoff_parameters":_m4_basin_storage_compiled_driver_asdict(runoff),
        "forcing_identity":forcing_identity, "dt_s":float(dt_s),"substep_s":sub_dt,"elapsed_s":elapsed+len(rain)*dt_s, "substeps":count+substeps,
        "work_face_steps":work+substeps*len(faces), "cells":bed.size,"faces":len(faces),
        "last_page_storage_identity":result["identity_sha256"], "hydraulic_ready":False,"transient_converged":False}
    saved_checkpoint = {"arrays":checkpoint_arrays,"metadata":checkpoint_metadata,"identity_sha256":_m4_basin_storage_compiled_driver_identity(checkpoint_arrays,checkpoint_metadata)}
    return {"storage":result,"checkpoint":saved_checkpoint}

# --- terrain_pipeline/td_basin_storage_v10.py:13 ---
@_m4_basin_storage_v10_njit(cache=True)
def advance_hour_permeable(states, errors, rain, bed, faces, boundary, widths, receiver, spacing, step, count, runoff):
    ledger = _m4_basin_storage_v10_np.zeros((13, len(bed)))
    forward = _m4_basin_storage_v10_np.zeros(len(faces)); reverse = _m4_basin_storage_v10_np.zeros(len(faces))
    forward_s = _m4_basin_storage_v10_np.zeros(len(faces)); reverse_s = _m4_basin_storage_v10_np.zeros(len(faces))
    routed = _m4_basin_storage_v10_np.zeros(len(bed)); duration = _m4_basin_storage_v10_np.zeros(len(bed))
    empty = _m4_basin_storage_v10_np.empty(0, _m4_basin_storage_v10_np.int64)
    area = spacing**2
    for substep in range(count):
        for half in range(2):
            capacity = _m4_basin_storage_v10_np.minimum(runoff[0]*step/7200, _m4_basin_storage_v10_np.maximum(0., runoff[1]-states[1]))
            result = advance_forcing(states, errors, rain, step/2, 1, runoff, .15)
            states, errors = result[0], result[1]
            ledger[:8] += result[2]*area/1000
            ledger[12] += capacity*area/1000
            if half == 0:
                exchange = _compiled_exchange(states[0], bed, faces, boundary, widths, spacing, step, .6, empty, empty)
                states[0] = exchange[0]
                errors[0] = 0
                forward += exchange[1]; reverse += exchange[2]
                forward_s += exchange[4]; reverse_s += exchange[5]
                for face in range(len(faces)):
                    first, second = faces[face]
                    signed = exchange[1][face]-exchange[2][face]
                    ledger[8, first] -= signed; ledger[8, second] += signed
                    if receiver[first] == second:
                        routed[first] += exchange[1][face]; duration[first] += exchange[4][face]
                    if receiver[second] == first:
                        routed[second] += exchange[2][face]; duration[second] += exchange[5][face]
                for index in range(len(boundary)):
                    ledger[9, boundary[index]] += exchange[3][index]
    return states, errors, ledger, forward, reverse, forward_s, reverse_s, routed, duration

# --- terrain_pipeline/td_basin_storage_v10.py:46 ---
def simulate_hour(hierarchy, full_rain_mm_h, *, substep_s, checkpoint=None):
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_v10_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_storage_v10_readonly
    topology = hierarchy['arrays']
    bed = topology['height_m'].ravel()
    valid = topology['valid_mask'].ravel()
    if topology['protected_mask'].any():
        raise ValueError('v10 protected cells unsupported')
    full = _m4_basin_storage_v10_np.asarray(full_rain_mm_h, dtype=_m4_basin_storage_v10_np.float64)
    shape = topology['height_m'].shape
    if full.shape != (24, *shape) or full.size > 4000000 or not _m4_basin_storage_v10_np.isfinite(full).all() or _m4_basin_storage_v10_np.any((full < 0) | (full > 1e6)):
        raise ValueError('v10 fixed spatial 24h forcing invalid')
    if _m4_basin_storage_v10_np.any(full[:, ~topology['valid_mask']] != 0):
        raise ValueError('v10 rainfall on unknown cells forbidden')
    full = full.copy()
    forcing_id = _m4_basin_storage_v10_identity({'rain_mm_h': full}, {'dt_s': 3600.})
    if type(substep_s) not in (float, int) or not _m4_basin_storage_v10_math.isfinite(substep_s) or substep_s <= 0 or int(3600/substep_s)*substep_s != 3600:
        raise ValueError('v10 exact integer hourly substeps required')
    count = int(3600/substep_s)
    faces = topology['face_cells']
    if count > 100000 or count*len(faces) > 6000000000:
        raise ValueError('v10 chunk work budget exceeded')
    spacing = hierarchy['metadata']['spacing_m']
    boundary = topology['boundary_cells']
    rows, columns = _m4_basin_storage_v10_np.divmod(boundary, shape[1])
    widths = spacing*((rows == 0).astype(int)+(rows == shape[0]-1)+(columns == 0)+(columns == shape[1]-1))
    cfl = validate_cfl(faces, boundary, widths, spacing, substep_s, .6, len(bed))
    runoff = _m4_basin_storage_v10_np.array([15.,150.,.15,1.,3600.,259200.])
    physical = {'substep_s':substep_s,'runoff':[15.,150.,.15,1.,3600.,259200.],
        'face_conductance_m_s':.6,'surface_evaporation_mm_h':.15,
        'forcing_profile':'v10-unified-rain-surface-infiltration-experimental-v1'}
    runoff_parameters = {'infiltration_capacity_mm_h':15.,'soil_capacity_mm':150.,
        'potential_et_mm_h':.15,'percolation_mm_h':1.,'fast_tau_s':3600.,'slow_tau_s':259200.,
        'initial_soil_mm':30.,'initial_fast_mm':0.,'initial_slow_mm':0.}
    states = _m4_basin_storage_v10_np.zeros((4,len(bed))); states[1, valid] = 30.
    errors = _m4_basin_storage_v10_np.zeros_like(states)
    offset = 0
    previous = {key: _m4_basin_storage_v10_np.zeros(len(faces) if key.startswith(('face_', 'active_')) else len(bed)) for key in FLUX}
    if checkpoint is not None:
        storagev10_validate_checkpoint(checkpoint)
        metadata = checkpoint['metadata']
        if metadata['hierarchy_identity'] != hierarchy['identity_sha256'] or metadata['forcing_identity'] != forcing_id or metadata['parameters'] != physical or metadata.get('runoff_parameters') != runoff_parameters or metadata['cells'] != len(bed) or metadata['faces'] != len(faces) or metadata['spacing_m'] != spacing or metadata['origin_m_xz'] != hierarchy['metadata']['origin_m_xz']:
            raise ValueError('v10 checkpoint topology/forcing/config mismatch')
        offset = int(metadata['end_s']/3600)
        states = _m4_basin_storage_v10_np.vstack([checkpoint['arrays'][key] for key in STATES]).copy()
        errors = _m4_basin_storage_v10_np.vstack([checkpoint['arrays'][key] for key in ERRORS]).copy()
        if _m4_basin_storage_v10_np.any(states[1] > runoff[1]):
            raise ValueError('v10 checkpoint soil exceeds capacity')
        previous = {key: checkpoint['arrays']['cumulative_'+key] for key in FLUX}
        if _m4_basin_storage_v10_np.any(states[:, ~valid] != 0) or _m4_basin_storage_v10_np.any(errors[:, ~valid] != 0) or any(_m4_basin_storage_v10_np.any(previous[key][~valid] != 0) for key in ('routed_volume_m3','wet_duration_s')):
            raise ValueError('v10 unknown checkpoint inventories/evidence forbidden')
    if offset >= 24:
        raise ValueError('v10 forcing plan exhausted')
    initial = states.copy()
    rain = full[offset].ravel()
    result = advance_hour_permeable(states, errors, rain, bed, faces, boundary, widths, topology['receiver'], spacing, substep_s, count, runoff)
    states, errors, ledger = result[:3]
    ledger[12, ~valid] = 0
    area = spacing**2
    before = area*(initial[0]+initial[1:].sum(axis=0)/1000)
    after = area*(states[0]+states[1:].sum(axis=0)/1000)
    ledger[10] = after-before
    ledger[11] = ledger[0]+ledger[8]-ledger[4]-ledger[5]-ledger[9]-ledger[10]
    arrays = {key: _m4_basin_storage_v10_np.vstack((initial[index],states[index])) for index,key in enumerate(STATES)}
    arrays.update({key: ledger[index:index+1] for index,key in enumerate(LEDGERS)})
    arrays.update({key: value for key,value in zip(FLUX,result[3:])})
    arrays.update({key: topology[key] for key in ('height_m','valid_mask','face_cells','receiver','boundary_cells')})
    arrays.update(boundary_width_m=widths, rain_mm_h=rain[None,:])
    metadata = {'schema':'td-v10-hour-page-v1','profile':STORAGEV10_PROFILE,'cells':len(bed),'faces':len(faces),
        'substeps':count,'substep_s':substep_s,'dt_s':3600.,'forcing_hour_offset':offset,
        'start_s':offset*3600.,'end_s':(offset+1)*3600.,'spacing_m':spacing,'positivity_cfl':cfl,
        'parameters':physical,'origin_m_xz':hierarchy['metadata']['origin_m_xz'],
        'runoff_parameters':runoff_parameters,
        'forcing_identity':forcing_id,'hierarchy_identity':hierarchy['identity_sha256'],
        'physics':'all valid cells experimentally permeable; rain first accesses finite capacity, remaining capacity draws surface water; rain excess enters unchanged fast store; ordered ET/percolation; no wet bypass',
        'permanent_lake_impermeability':'not modelled; requires independent material mask',
        'activity_semantics':'SSP-RK2 stage quadrature of actual signed exchange; not exact event duration',
        'hydraulic_ready':False,'transient_converged':False,'publishable':False}
    page = {'arrays':{key:_m4_basin_storage_v10_readonly(value) for key,value in arrays.items()},'metadata':metadata,'identity_sha256':_m4_basin_storage_v10_identity(arrays,metadata)}
    validate_storage(page)
    cp_arrays = {key:states[index] for index,key in enumerate(STATES)}
    cp_arrays.update({key:errors[index] for index,key in enumerate(ERRORS)})
    cp_arrays.update({'cumulative_'+key:previous[key]+arrays[key] for key in FLUX})
    cp_meta = {**metadata,'schema':'td-v10-hour-checkpoint-v1','last_page_identity':page['identity_sha256']}
    cp = {'arrays':{key:_m4_basin_storage_v10_readonly(value) for key,value in cp_arrays.items()},'metadata':cp_meta,'identity_sha256':_m4_basin_storage_v10_identity(cp_arrays,cp_meta)}
    storagev10_validate_checkpoint(cp)
    return {'storage':page,'checkpoint':cp}

# --- terrain_pipeline/td_basin_transport_v6.py:6 ---
SSPRK2_TRANSPORT_PROFILE = "v6-simultaneous-SSPRK2-6e9-v1"

# --- terrain_pipeline/td_basin_transport_v6.py:10 ---
@_m4_basin_transport_v6_njit(cache=True)
def _stage(depth, bed, faces, boundary, widths, spacing, conductance):
    derivative = _m4_basin_transport_v6_np.zeros(len(depth))
    flux = _m4_basin_transport_v6_np.zeros(len(faces))
    exported = _m4_basin_transport_v6_np.zeros(len(boundary))
    for index in range(len(faces)):
        first, second = faces[index, 0], faces[index, 1]
        first_head = bed[first] + depth[first]
        second_head = bed[second] + depth[second]
        sill = max(bed[first], bed[second])
        if first_head >= second_head:
            rate = conductance / spacing * max(first_head - max(sill, second_head), 0.0)
        else:
            rate = -conductance / spacing * max(second_head - max(sill, first_head), 0.0)
        flux[index] = rate
        derivative[first] -= rate
        derivative[second] += rate
    for index in range(len(boundary)):
        cell = boundary[index]
        rate = conductance * widths[index] / (spacing * spacing) * depth[cell]
        exported[index] = rate
        derivative[cell] -= rate
    return derivative, flux, exported

# --- terrain_pipeline/td_basin_transport_v6.py:35 ---
@_m4_basin_transport_v6_njit(cache=True)
def _compiled_exchange(depth, bed, faces, boundary, widths, spacing, dt_s, conductance, ordered, offsets):
    derivative0, flux0, boundary0 = _stage(depth, bed, faces, boundary, widths, spacing, conductance)
    stage1 = depth + dt_s * derivative0
    if _m4_basin_transport_v6_np.any(stage1 < 0):
        raise ValueError("SSP-RK2 negative Euler stage; no clamp permitted")
    derivative1, flux1, boundary1 = _stage(stage1, bed, faces, boundary, widths, spacing, conductance)
    stage2 = stage1 + dt_s * derivative1
    if _m4_basin_transport_v6_np.any(stage2 < 0):
        raise ValueError("SSP-RK2 negative second Euler stage; no clamp permitted")
    final = 0.5 * depth + 0.5 * stage2
    area = spacing * spacing
    half = dt_s / 2
    forward = half * area * (_m4_basin_transport_v6_np.maximum(flux0, 0) + _m4_basin_transport_v6_np.maximum(flux1, 0))
    reverse = half * area * (_m4_basin_transport_v6_np.maximum(-flux0, 0) + _m4_basin_transport_v6_np.maximum(-flux1, 0))
    forward_s = half * ((flux0 > 0).astype(_m4_basin_transport_v6_np.float64) + (flux1 > 0).astype(_m4_basin_transport_v6_np.float64))
    reverse_s = half * ((flux0 < 0).astype(_m4_basin_transport_v6_np.float64) + (flux1 < 0).astype(_m4_basin_transport_v6_np.float64))
    exported = half * area * (boundary0 + boundary1)
    return final, forward, reverse, exported, forward_s, reverse_s

# --- terrain_pipeline/td_basin_transport_v6.py:55 ---
def validate_cfl(faces, boundary, widths, spacing, dt_s, conductance, cells):
    degree = _m4_basin_transport_v6_np.bincount(faces.reshape(-1), minlength=cells).astype(float)
    _m4_basin_transport_v6_np.add.at(degree, boundary, widths / spacing)
    maximum = float(degree.max(initial=0)) * conductance * dt_s / spacing
    if not _m4_basin_transport_v6_np.isfinite(maximum) or maximum > 1:
        raise ValueError("SSP-RK2 positivity CFL exceeded")
    return maximum

# --- terrain_pipeline/td_basin_forcing_v10.py:9 ---
FORCING_V10_PROFILE = "v10-unified-rain-surface-infiltration-experimental-v1"

# --- terrain_pipeline/td_basin_forcing_v10.py:13 ---
@_m4_basin_forcing_v10_njit(cache=True)
def advance_forcing(states, errors, rain_mm_h, seconds, subdivisions, runoff, evaporation_mm_h):
    ledger = _m4_basin_forcing_v10_np.zeros((8, states.shape[1]))
    compensation = _m4_basin_forcing_v10_np.zeros_like(ledger)
    hours = seconds / 3600
    for substep in range(subdivisions):
        for cell in range(states.shape[1]):
            rainfall = rain_mm_h[cell] * hours
            capacity = min(runoff[0] * hours, max(0., runoff[1] - states[1, cell]))
            rain_infiltration = min(rainfall, capacity)
            surface_infiltration = min(states[0, cell] * 1000, capacity - rain_infiltration)
            infiltration = rain_infiltration + surface_infiltration
            surface_decrement = -states[0, cell] if surface_infiltration == states[0, cell]*1000 else -surface_infiltration/1000
            states[0, cell], errors[0, cell] = _add(states[0, cell], surface_decrement, errors[0, cell])
            states[1, cell], errors[1, cell] = _add(states[1, cell], infiltration, errors[1, cell])
            soil_et = min(states[1, cell], runoff[2] * hours)
            states[1, cell], errors[1, cell] = _add(states[1, cell], -soil_et, errors[1, cell])
            percolation = min(states[1, cell], runoff[3] * hours)
            states[1, cell], errors[1, cell] = _add(states[1, cell], -percolation, errors[1, cell])
            excess = rainfall - rain_infiltration
            fast_release = _release(states[2, cell], excess, seconds, runoff[4])
            slow_release = _release(states[3, cell], percolation, seconds, runoff[5])
            states[2, cell], errors[2, cell] = _add(states[2, cell], excess - fast_release, errors[2, cell])
            states[3, cell], errors[3, cell] = _add(states[3, cell], percolation - slow_release, errors[3, cell])
            release = fast_release + slow_release
            states[0, cell], errors[0, cell] = _add(states[0, cell], release / 1000, errors[0, cell])
            surface_et = min(states[0, cell], evaporation_mm_h * hours / 1000)
            states[0, cell], errors[0, cell] = _add(states[0, cell], -surface_et, errors[0, cell])
            increments = (rainfall, rain_infiltration, surface_infiltration, excess,
                          soil_et, surface_et * 1000, release, percolation)
            for index in range(8):
                ledger[index, cell], compensation[index, cell] = _add(
                    ledger[index, cell], increments[index], compensation[index, cell])
    return states, errors, ledger

# --- terrain_pipeline/td_basin_forcing_v10.py:48 ---
def simulate_forcing(states, rain_mm_h, *, duration_s=3600., substep_s=1.25,
                     runoff=None, evaporation_mm_h=.15):
    initial = _m4_basin_forcing_v10_np.asarray(states, dtype=_m4_basin_forcing_v10_np.float64)
    rain = _m4_basin_forcing_v10_np.asarray(rain_mm_h, dtype=_m4_basin_forcing_v10_np.float64)
    parameters = _m4_basin_forcing_v10_np.array([15., 150., .15, 1., 3600., 259200.]) if runoff is None else _m4_basin_forcing_v10_np.asarray(runoff, dtype=_m4_basin_forcing_v10_np.float64)
    scalars = _m4_basin_forcing_v10_np.array([duration_s, substep_s, evaporation_mm_h])
    if (initial.ndim != 2 or initial.shape[0] != 4 or not 1 <= initial.shape[1] <= 1000
            or rain.shape != (initial.shape[1],) or parameters.shape != (6,)
            or not _m4_basin_forcing_v10_np.isfinite(initial).all() or not _m4_basin_forcing_v10_np.isfinite(rain).all()
            or not _m4_basin_forcing_v10_np.isfinite(parameters).all() or not _m4_basin_forcing_v10_np.isfinite(scalars).all()
            or _m4_basin_forcing_v10_np.any(initial < 0) or _m4_basin_forcing_v10_np.any(rain < 0) or _m4_basin_forcing_v10_np.any(parameters < 0)
            or _m4_basin_forcing_v10_np.any(parameters[4:] <= 0) or _m4_basin_forcing_v10_np.any(initial[1] > parameters[1])
            or duration_s <= 0 or substep_s <= 0 or evaporation_mm_h < 0):
        raise ValueError("invalid bounded v10 forcing inputs")
    count = int(_m4_basin_forcing_v10_np.ceil(duration_s / substep_s))
    if count > 100000 or count * initial.shape[1] > 10000000:
        raise ValueError("v10 forcing experiment budget exceeded")
    result = advance_forcing(initial.copy(), _m4_basin_forcing_v10_np.zeros_like(initial), rain,
                             duration_s / count, count, parameters, evaporation_mm_h)
    before = initial[0] * 1000 + initial[1:].sum(axis=0)
    after = result[0][0] * 1000 + result[0][1:].sum(axis=0)
    residual = after - before - result[2][0] + result[2][4] + result[2][5]
    if _m4_basin_forcing_v10_np.any(_m4_basin_forcing_v10_np.abs(residual) > 1e-9):
        raise ValueError("v10 forcing water budget failed")
    return {"states": result[0], "errors": result[1], "ledger_mm": result[2],
            "balance_residual_mm": residual, "profile": FORCING_V10_PROFILE,
            "ledger_order": ["rain", "rain_infiltration", "surface_infiltration", "rain_excess",
                             "soil_et", "surface_et", "release", "percolation"],
            "semantics": "rain has first access to finite infiltration capacity; remaining capacity draws available surface water; rain excess enters unchanged fast store; ordered soil ET/percolation retained",
            "hydraulic_ready": False, "publishable": False}

# --- terrain_pipeline/td_basin_forcing_compensated.py:7 ---
def add(values, increment, compensation):
    exhausted = (increment < 0) & (increment == -values)
    adjusted = increment - compensation
    updated = values + adjusted
    updated[exhausted] = 0
    compensation[:] = (updated - values) - adjusted
    compensation[exhausted] = 0
    if _m4_basin_forcing_compensated_np.any(updated < 0) or not _m4_basin_forcing_compensated_np.isfinite(updated).all():
        raise ValueError("negative/nonfinite compensated inventory; clamp forbidden")
    values[:] = updated

# --- terrain_pipeline/td_basin_forcing_compensated.py:19 ---
def reset_transport_compensation(errors):
    errors["depth"][:] = 0

# --- terrain_pipeline/td_basin_forcing_compensated.py:23 ---
def reset_hourly_ledger_compensation(errors, keys):
    for key in keys:
        errors[key][:] = 0

# --- terrain_pipeline/td_basin_forcing_compensated.py:28 ---
def forcing(depth, soil, fast, slow, rain_rate, sub_dt, runoff, config, area, ledgers, step, errors):
    from terrain_pipeline.runoff import _release as _m4_basin_forcing_compensated_release
    hours = sub_dt / 3600
    rainfall = rain_rate * hours
    wet = depth > config["wet_threshold_m"]
    lake_rain = _m4_basin_forcing_compensated_np.where(wet, rainfall, 0)
    land_rain = rainfall - lake_rain
    infiltration = _m4_basin_forcing_compensated_np.minimum(_m4_basin_forcing_compensated_np.minimum(land_rain, runoff.infiltration_capacity_mm_h * hours),
                              _m4_basin_forcing_compensated_np.maximum(0, runoff.soil_capacity_mm - soil))
    add(soil, infiltration, errors["soil"])
    soil_et = _m4_basin_forcing_compensated_np.minimum(soil, runoff.potential_et_mm_h * hours)
    add(soil, -soil_et, errors["soil"])
    percolation = _m4_basin_forcing_compensated_np.minimum(soil, runoff.percolation_mm_h * hours)
    add(soil, -percolation, errors["soil"])
    unused_fast, fast_release = _m4_basin_forcing_compensated_release(fast, land_rain - infiltration, sub_dt, runoff.fast_tau_s)
    unused_slow, slow_release = _m4_basin_forcing_compensated_release(slow, percolation, sub_dt, runoff.slow_tau_s)
    add(fast, land_rain - infiltration - fast_release, errors["fast"])
    add(slow, percolation - slow_release, errors["slow"])
    release = fast_release + slow_release
    add(depth, (lake_rain + release) / 1000, errors["depth"])
    surface_et = _m4_basin_forcing_compensated_np.minimum(depth, config["surface_evaporation_mm_h"] * hours / 1000)
    add(depth, -surface_et, errors["depth"])
    for key, values in (("rain_volume_m3", rainfall), ("lake_rain_m3", lake_rain), ("land_rain_m3", land_rain),
                        ("soil_et_m3", soil_et), ("local_release_m3", release)):
        add(ledgers[key][step], values * area / 1000, errors[key])
    add(ledgers["surface_et_m3"][step], surface_et * area, errors["surface_et_m3"])
    return depth, soil, fast, slow

# --- terrain_pipeline/td_basin_overflow.py:22 ---
OVERFLOW_SCHEMA = "td-original-bed-basin-overflow-v1"

# --- terrain_pipeline/td_basin_overflow.py:23 ---
MAX_LEAVES = 250_000

# --- terrain_pipeline/td_basin_overflow.py:24 ---
MAX_FACES = 500_000

# --- terrain_pipeline/td_basin_overflow.py:25 ---
OVERFLOW_MAX_STEPS = 100_000

# --- terrain_pipeline/td_basin_overflow.py:29 ---
@_m4_basin_overflow_dataclass(frozen=True)
class OverflowParameters:
    runoff_coefficient: float = 0.35
    baseflow_mm_per_day: float = 0.15
    face_conductance_m_s: float = 0.6
    boundary_conductance_m_s: float = 0.6
    timestep_s: float = 300.0
    duration_s: float = 86400.0

    def __post_init__(self):
        for name, value in _m4_basin_overflow_asdict(self).items():
            if type(value) not in (int, float) or not _m4_basin_overflow_math.isfinite(value) or value <= 0:
                raise ValueError(f"positive finite overflow parameter required: {name}")
        if not 0 < self.runoff_coefficient <= 1:
            raise ValueError("runoff coefficient outside (0,1]")
        if self.duration_s / self.timestep_s != int(self.duration_s / self.timestep_s):
            raise ValueError("duration must contain an integer number of steps")

# --- terrain_pipeline/td_basin_overflow.py:47 ---
def _hash(value):
    return _m4_basin_overflow_hashlib.sha256(_m4_basin_overflow_json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

# --- terrain_pipeline/td_basin_overflow.py:51 ---
def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, _m4_basin_overflow_np.ndarray):
        return value.tolist()
    if isinstance(value, (_m4_basin_overflow_np.integer, _m4_basin_overflow_np.floating, _m4_basin_overflow_np.bool_)):
        return value.item()
    return value

# --- terrain_pipeline/td_basin_overflow.py:63 ---
def _face_id(hierarchy, face_index):
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    columns = arrays["height_m"].shape[1]
    endpoints = []
    for cell in arrays["face_cells"][face_index]:
        row, column = divmod(int(cell), columns)
        point = (float(metadata["origin_m_xz"][0] + column * metadata["spacing_m"]),
                 float(arrays["height_m"].ravel()[cell]),
                 float(metadata["origin_m_xz"][1] + row * metadata["spacing_m"]))
        endpoints.append([value.hex() for value in point])
    return "face:" + _hash([metadata["source_identity_sha256"], sorted(endpoints)])

# --- terrain_pipeline/td_basin_overflow.py:76 ---
def _curves(hierarchy):
    arrays = hierarchy["arrays"]
    owners = arrays["contribution_owner"].ravel()
    valid = arrays["valid_mask"].ravel() & ~arrays["protected_mask"].ravel()
    bed = arrays["height_m"].ravel()
    leaves = _m4_basin_overflow_np.unique(owners[valid]).astype(_m4_basin_overflow_np.int64)
    if len(leaves) == 0 or len(leaves) > MAX_LEAVES:
        raise ValueError("invalid contribution basin count")
    leaf_index = {int(leaf): index for index, leaf in enumerate(leaves)}
    offsets = [0]
    levels, areas = [], []
    for leaf in leaves:
        values = _m4_basin_overflow_np.sort(bed[valid & (owners == leaf)])
        unique, counts = _m4_basin_overflow_np.unique(values, return_counts=True)
        levels.extend(unique.tolist())
        areas.extend((counts * float(hierarchy["metadata"]["spacing_m"]) ** 2).tolist())
        offsets.append(offsets[-1] + len(unique))
    return leaves, _m4_basin_overflow_np.asarray(offsets, _m4_basin_overflow_np.int64), _m4_basin_overflow_np.asarray(levels, _m4_basin_overflow_np.float64), _m4_basin_overflow_np.asarray(areas, _m4_basin_overflow_np.float64), leaf_index

# --- terrain_pipeline/td_basin_overflow.py:96 ---
def _volume_at(stage, levels, areas):
    if stage <= levels[0]:
        return 0.0
    return float(_m4_basin_overflow_np.maximum(stage - levels, 0.0).dot(areas))

# --- terrain_pipeline/td_basin_overflow.py:102 ---
def _stage_at(volume, levels, areas):
    if volume <= 0:
        return float(levels[0])
    cumulative = 0.0
    prefix_area = 0.0
    for index, level in enumerate(levels[:-1]):
        prefix_area += float(areas[index])
        next_level = levels[index + 1]
        capacity = float((next_level - level) * prefix_area)
        if volume <= cumulative + capacity + 1e-12:
            return float(level + (volume - cumulative) / prefix_area)
        cumulative += capacity
    prefix_area += float(areas[-1])
    return float(levels[-1] + (volume - cumulative) / prefix_area)

# --- terrain_pipeline/td_basin_overflow.py:118 ---
def _physical_faces(hierarchy, leaves, leaf_index):
    arrays = hierarchy["arrays"]
    owners = arrays["contribution_owner"].ravel()
    bed = arrays["height_m"].ravel()
    candidates = {}
    for face_index, cells in enumerate(arrays["face_cells"]):
        first, second = map(int, cells)
        left, right = int(owners[first]), int(owners[second])
        if left == right or left not in leaf_index or right not in leaf_index:
            continue
        pair = tuple(sorted((left, right)))
        sill = float(max(bed[first], bed[second]))
        existing = candidates.get(pair)
        if existing is None or (sill, _face_id(hierarchy, face_index)) < (existing["sill_m"], existing["face_id"]):
            candidates[pair] = {"face_index": face_index, "face_id": _face_id(hierarchy, face_index),
                                "leaf_ids": list(pair), "cell_ids": [first, second], "sill_m": sill}
    return list(candidates.values())

# --- terrain_pipeline/td_basin_overflow.py:137 ---
def _boundary_faces(hierarchy, leaves, leaf_index):
    arrays = hierarchy["arrays"]
    owners = arrays["contribution_owner"].ravel()
    bed = arrays["height_m"].ravel()
    shape = arrays["height_m"].shape
    spacing = float(hierarchy["metadata"]["spacing_m"])
    records = []
    for cell in _m4_basin_overflow_np.flatnonzero(arrays["open_boundary_mask"].ravel()):
        leaf = int(owners[cell])
        if leaf not in leaf_index:
            continue
        row, column = divmod(int(cell), shape[1])
        sides = int(row == 0) + int(row == shape[0] - 1) + int(column == 0) + int(column == shape[1] - 1)
        records.append({"cell_id": int(cell), "leaf_id": leaf, "sill_m": float(bed[cell]),
                        "width_m": float(sides * spacing), "face_count": sides})
    return records

# --- terrain_pipeline/td_basin_overflow.py:155 ---
def build_overflow_topology(hierarchy, *, expected_hierarchy_identity=None):
    from terrain_pipeline.basin_topology import validate_basin_hierarchy as _m4_basin_overflow_validate_basin_hierarchy
    from terrain_pipeline.common_infra import readonly as _m4_basin_overflow_readonly
    _m4_basin_overflow_validate_basin_hierarchy(hierarchy)
    if expected_hierarchy_identity is not None and hierarchy["identity_sha256"] != expected_hierarchy_identity:
        raise ValueError("hierarchy identity mismatch")
    leaves, offsets, levels, areas, leaf_index = _curves(hierarchy)
    faces = _physical_faces(hierarchy, leaves, leaf_index)
    boundaries = _boundary_faces(hierarchy, leaves, leaf_index)
    if len(faces) > MAX_FACES:
        raise ValueError("physical face budget exceeded")
    leaf_areas = _m4_basin_overflow_np.zeros(len(leaves), _m4_basin_overflow_np.float64)
    for index in range(len(leaves)):
        start, end = offsets[index], offsets[index + 1]
        leaf_areas[index] = areas[start:end].sum() / (levels[end - 1] - levels[start] + 1e-300) if end > start else 0
        leaf_areas[index] = float(_m4_basin_overflow_np.sum(areas[start:end]))
    metadata = {"schema": OVERFLOW_SCHEMA, "algorithm": "original-bed-hypsometry-face-reservoir-v1",
                "hierarchy_identity_sha256": hierarchy["identity_sha256"],
                "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
                "spacing_m": hierarchy["metadata"]["spacing_m"], "origin_m_xz": hierarchy["metadata"]["origin_m_xz"],
                "leaf_count": len(leaves), "physical_face_count": len(faces),
                "engineering_boundary_face_count": len(boundaries),
                "surface_storage_semantics": "volume is water above immutable original bed inside one contribution basin",
                "face_semantics": "one lowest-sill physical D4 face per contribution-leaf pair; ties resolve by face identity",
                "boundary_semantics": "explicit engineering open perimeter discharge, never natural outlet evidence",
                "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    arrays = {"leaf_ids": _m4_basin_overflow_readonly(leaves), "curve_offsets": _m4_basin_overflow_readonly(offsets), "curve_level_m": _m4_basin_overflow_readonly(levels),
              "curve_area_m2": _m4_basin_overflow_readonly(areas), "leaf_area_m2": _m4_basin_overflow_readonly(leaf_areas)}
    result = {"arrays": arrays, "metadata": metadata,
              "faces": faces, "engineering_boundaries": boundaries}
    result["identity_sha256"] = _topology_identity(result)
    return result

# --- terrain_pipeline/td_basin_overflow.py:187 ---
def _validate_rain(rain_mm_h, steps):
    rain = _m4_basin_overflow_np.asarray(rain_mm_h, dtype=_m4_basin_overflow_np.float64)
    if rain.ndim != 1 or rain.size != steps or not _m4_basin_overflow_np.isfinite(rain).all() or _m4_basin_overflow_np.any(rain < 0):
        raise ValueError("rainfall must be a finite nonnegative hourly-rate vector")
    return rain

# --- terrain_pipeline/td_basin_overflow.py:194 ---
def simulate_overflow(topology, rain_mm_h, *, parameters=None, initial_volume_m3=None):
    from terrain_pipeline.common_infra import identity as _m4_basin_overflow_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_overflow_readonly
    if topology["metadata"]["schema"] != OVERFLOW_SCHEMA:
        raise ValueError("overflow topology schema mismatch")
    config = OverflowParameters() if parameters is None else parameters
    if not isinstance(config, OverflowParameters):
        raise ValueError("OverflowParameters required")
    steps = int(config.duration_s / config.timestep_s)
    if steps > OVERFLOW_MAX_STEPS:
        raise ValueError("overflow step budget exceeded")
    rain = _validate_rain(rain_mm_h, steps)
    arrays, metadata = topology["arrays"], topology["metadata"]
    leaf_lookup = {int(leaf): index for index, leaf in enumerate(arrays["leaf_ids"])}
    leaf_count = metadata["leaf_count"]
    levels, areas, offsets = arrays["curve_level_m"], arrays["curve_area_m2"], arrays["curve_offsets"]
    leaf_areas = arrays["leaf_area_m2"]
    volumes = _m4_basin_overflow_np.zeros(leaf_count, _m4_basin_overflow_np.float64) if initial_volume_m3 is None else _m4_basin_overflow_np.asarray(initial_volume_m3, dtype=_m4_basin_overflow_np.float64).copy()
    if volumes.shape != (leaf_count,) or not _m4_basin_overflow_np.isfinite(volumes).all() or _m4_basin_overflow_np.any(volumes < 0):
        raise ValueError("invalid initial basin water inventory")
    stages = _m4_basin_overflow_np.zeros((steps + 1, leaf_count), _m4_basin_overflow_np.float64)
    water = _m4_basin_overflow_np.zeros((steps + 1, leaf_count), _m4_basin_overflow_np.float64)
    input_volume = _m4_basin_overflow_np.zeros((steps, leaf_count), _m4_basin_overflow_np.float64)
    exchanged = _m4_basin_overflow_np.zeros((steps, len(topology["faces"])), _m4_basin_overflow_np.float64)
    exchanged_forward = _m4_basin_overflow_np.zeros_like(exchanged)
    exchanged_reverse = _m4_basin_overflow_np.zeros_like(exchanged)
    exchanged_net = _m4_basin_overflow_np.zeros_like(exchanged)
    basin_net_internal = _m4_basin_overflow_np.zeros((steps, leaf_count), _m4_basin_overflow_np.float64)
    basin_gross_internal = _m4_basin_overflow_np.zeros((steps, leaf_count), _m4_basin_overflow_np.float64)
    basin_boundary_outflow = _m4_basin_overflow_np.zeros((steps, leaf_count), _m4_basin_overflow_np.float64)
    boundary_outflow = _m4_basin_overflow_np.zeros((steps, len(topology["engineering_boundaries"])), _m4_basin_overflow_np.float64)
    balance = _m4_basin_overflow_np.zeros(steps, _m4_basin_overflow_np.float64)
    onset = _m4_basin_overflow_np.full(len(topology["faces"]), -1, _m4_basin_overflow_np.int64)
    for leaf_index in range(leaf_count):
        start, end = offsets[leaf_index], offsets[leaf_index + 1]
        stages[0, leaf_index] = _stage_at(volumes[leaf_index], levels[start:end], areas[start:end])
    water[0] = volumes
    for step in range(steps):
        before = float(volumes.sum())
        rates = rain[step] / 1000.0 * config.runoff_coefficient / 3600.0 + config.baseflow_mm_per_day / 1000.0 / 86400.0
        added = leaf_areas * rates * config.timestep_s
        input_volume[step] = added
        volumes += added
        current_stages = _m4_basin_overflow_np.zeros(leaf_count, _m4_basin_overflow_np.float64)
        for leaf_index in range(leaf_count):
            start, end = offsets[leaf_index], offsets[leaf_index + 1]
            current_stages[leaf_index] = _stage_at(volumes[leaf_index], levels[start:end], areas[start:end])
        face_proposed = _m4_basin_overflow_np.zeros(len(topology["faces"]), _m4_basin_overflow_np.float64)
        face_donors = _m4_basin_overflow_np.zeros(len(topology["faces"]), _m4_basin_overflow_np.int64)
        face_recipients = _m4_basin_overflow_np.zeros(len(topology["faces"]), _m4_basin_overflow_np.int64)
        face_directions = _m4_basin_overflow_np.zeros(len(topology["faces"]), _m4_basin_overflow_np.int8)
        for face_index, face in enumerate(topology["faces"]):
            first, second = (leaf_lookup[face["leaf_ids"][0]], leaf_lookup[face["leaf_ids"][1]])
            stage_first, stage_second = current_stages[first], current_stages[second]
            sill = face["sill_m"]
            if stage_first >= stage_second:
                donor, recipient, excess = first, second, stage_first - max(sill, stage_second)
                direction = 1
            else:
                donor, recipient, excess = second, first, stage_second - max(sill, stage_first)
                direction = -1
            face_proposed[face_index] = max(0.0, config.face_conductance_m_s * metadata["spacing_m"] * excess * config.timestep_s)
            face_donors[face_index] = donor
            face_recipients[face_index] = recipient
            face_directions[face_index] = direction
        boundary_proposed = _m4_basin_overflow_np.zeros(len(topology["engineering_boundaries"]), _m4_basin_overflow_np.float64)
        for boundary_index, boundary in enumerate(topology["engineering_boundaries"]):
            leaf = leaf_lookup[boundary["leaf_id"]]
            excess = max(0.0, current_stages[leaf] - boundary["sill_m"])
            boundary_proposed[boundary_index] = max(0.0, config.boundary_conductance_m_s * boundary["width_m"] * excess * config.timestep_s)
        demand = _m4_basin_overflow_np.bincount(face_donors, weights=face_proposed, minlength=leaf_count)
        boundary_leaves = _m4_basin_overflow_np.asarray([leaf_lookup[item["leaf_id"]] for item in topology["engineering_boundaries"]], dtype=_m4_basin_overflow_np.int64)
        if boundary_leaves.size:
            _m4_basin_overflow_np.add.at(demand, boundary_leaves, boundary_proposed)
        scale = _m4_basin_overflow_np.minimum(1.0, _m4_basin_overflow_np.divide(volumes, demand, out=_m4_basin_overflow_np.ones_like(volumes), where=demand > 0))
        delta = _m4_basin_overflow_np.zeros(leaf_count, _m4_basin_overflow_np.float64)
        for face_index in range(len(topology["faces"])):
            volume = face_proposed[face_index] * scale[face_donors[face_index]]
            if volume <= 0:
                continue
            donor, recipient = face_donors[face_index], face_recipients[face_index]
            delta[donor] -= volume
            delta[recipient] += volume
            exchanged[step, face_index] = volume
            if face_directions[face_index] > 0:
                exchanged_forward[step, face_index] = volume
            else:
                exchanged_reverse[step, face_index] = volume
            signed = volume if face_directions[face_index] > 0 else -volume
            exchanged_net[step, face_index] = signed
            basin_net_internal[step, donor] -= volume
            basin_net_internal[step, recipient] += volume
            basin_gross_internal[step, donor] += volume
            basin_gross_internal[step, recipient] += volume
            if onset[face_index] < 0:
                onset[face_index] = step
        volumes += delta
        for boundary_index, boundary in enumerate(topology["engineering_boundaries"]):
            leaf = boundary_leaves[boundary_index]
            volume = boundary_proposed[boundary_index] * scale[leaf]
            volumes[leaf] -= volume
            boundary_outflow[step, boundary_index] = volume
            basin_boundary_outflow[step, leaf] += volume
        if _m4_basin_overflow_np.any(volumes < -1e-8):
            raise ValueError("negative basin water inventory")
        volumes = _m4_basin_overflow_np.maximum(volumes, 0.0)
        after = float(volumes.sum())
        balance[step] = float(added.sum() - boundary_outflow[step].sum() - (after - before))
        for leaf_index in range(leaf_count):
            start, end = offsets[leaf_index], offsets[leaf_index + 1]
            stages[step + 1, leaf_index] = _stage_at(volumes[leaf_index], levels[start:end], areas[start:end])
        water[step + 1] = volumes
    arrays_out = {"rain_mm_h": rain, "stage_m": stages, "volume_m3": water,
                  "input_volume_m3": input_volume, "face_volume_m3": exchanged,
                  "face_forward_m3": exchanged_forward, "face_reverse_m3": exchanged_reverse,
                  "face_net_m3": exchanged_net, "basin_net_internal_m3": basin_net_internal,
                  "basin_gross_internal_m3": basin_gross_internal,
                  "basin_boundary_outflow_m3": basin_boundary_outflow,
                  "basin_balance_residual_m3": input_volume + basin_net_internal - basin_boundary_outflow - _m4_basin_overflow_np.diff(water, axis=0),
                  "engineering_boundary_outflow_m3": boundary_outflow, "balance_residual_m3": balance,
                  "spill_onset_step": onset}
    out_meta = {"schema": "td-original-bed-overflow-event-v2", "algorithm": "synchronous-basin-face-exchange-v2",
                "topology_identity_sha256": topology["identity_sha256"], "hierarchy_identity_sha256": metadata["hierarchy_identity_sha256"],
                "source_identity_sha256": metadata["source_identity_sha256"], "parameters": _m4_basin_overflow_asdict(config),
                "steps": steps, "timestep_s": config.timestep_s, "duration_s": config.duration_s,
                "rain_semantics": "representative runoff input after a fixed runoff coefficient plus uniform baseflow; no atmospheric solver",
                "spill_semantics": "a face event begins when synchronous source head exceeds its physical sill and destination head",
                "flux_semantics": "face_net_m3 is signed first-leaf-to-second-leaf volume; basin_net_internal_m3 is positive into a basin; gross exchange is a round-trip diagnostic",
                "engineering_boundary_semantics": "outflow leaves the finite engineering domain and is not natural outlet evidence",
                "hydraulic_ready": False, "transient_converged": False, "natural_outlet_verified": False, "publishable": False}
    result = {"arrays": {key: _m4_basin_overflow_readonly(value) for key, value in arrays_out.items()}, "metadata": out_meta}
    result["identity_sha256"] = _m4_basin_overflow_identity(result["arrays"], out_meta)
    validate_overflow_event(result, topology)
    return result

# --- terrain_pipeline/td_basin_overflow.py:328 ---
def validate_overflow_event(result, topology):
    from terrain_pipeline.common_infra import identity as _m4_basin_overflow_identity
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("schema") not in ("td-original-bed-overflow-event-v1", "td-original-bed-overflow-event-v2") or result["identity_sha256"] != _m4_basin_overflow_identity(arrays, metadata):
        raise ValueError("overflow event identity/schema mismatch")
    if metadata.get("topology_identity_sha256") != topology["identity_sha256"]:
        raise ValueError("overflow event topology identity mismatch")
    steps = metadata["steps"]
    leaves = topology["metadata"]["leaf_count"]
    faces = len(topology["faces"])
    boundaries = len(topology["engineering_boundaries"])
    expected = {
        "rain_mm_h": (steps,), "stage_m": (steps + 1, leaves), "volume_m3": (steps + 1, leaves),
        "input_volume_m3": (steps, leaves), "face_volume_m3": (steps, faces),
        "face_forward_m3": (steps, faces), "face_reverse_m3": (steps, faces),
        "engineering_boundary_outflow_m3": (steps, boundaries),
        "balance_residual_m3": (steps,), "spill_onset_step": (faces,),
    }
    if metadata.get("schema") == "td-original-bed-overflow-event-v2":
        expected.update({"face_net_m3": (steps, faces),
                         "basin_net_internal_m3": (steps, leaves),
                         "basin_gross_internal_m3": (steps, leaves),
                         "basin_boundary_outflow_m3": (steps, leaves),
                         "basin_balance_residual_m3": (steps, leaves)})
    if any(arrays.get(key) is None or arrays[key].shape != shape for key, shape in expected.items()):
        raise ValueError("overflow event time shape mismatch")
    if any(not _m4_basin_overflow_np.isfinite(value).all() for value in arrays.values()):
        raise ValueError("overflow event nonfinite field")
    for flag in ("hydraulic_ready", "transient_converged", "natural_outlet_verified", "publishable"):
        if metadata.get(flag) is not False:
            raise ValueError("overflow diagnostic cannot certify hydraulics or natural outlets")
    if not _m4_basin_overflow_np.isfinite(arrays["stage_m"]).all() or _m4_basin_overflow_np.any(arrays["volume_m3"] < -1e-8):
        raise ValueError("overflow event negative state")
    if any(_m4_basin_overflow_np.any(arrays[key] < 0) for key in ("rain_mm_h", "input_volume_m3", "face_volume_m3",
                                               "face_forward_m3", "face_reverse_m3", "engineering_boundary_outflow_m3")):
        raise ValueError("overflow event negative volume")
    if not _m4_basin_overflow_np.allclose(arrays["face_volume_m3"], arrays["face_forward_m3"] + arrays["face_reverse_m3"], rtol=0, atol=1e-9):
        raise ValueError("overflow event directional face ledger mismatch")
    leaf_lookup = {int(leaf): index for index, leaf in enumerate(topology["arrays"]["leaf_ids"])}
    expected_net = _m4_basin_overflow_np.zeros((steps, leaves), _m4_basin_overflow_np.float64)
    expected_gross = _m4_basin_overflow_np.zeros_like(expected_net)
    expected_boundary = _m4_basin_overflow_np.zeros_like(expected_net)
    for face_index, face in enumerate(topology["faces"]):
        first, second = (leaf_lookup[leaf] for leaf in face["leaf_ids"])
        signed = arrays["face_forward_m3"][:, face_index] - arrays["face_reverse_m3"][:, face_index]
        gross = arrays["face_volume_m3"][:, face_index]
        expected_net[:, first] -= signed
        expected_net[:, second] += signed
        expected_gross[:, first] += gross
        expected_gross[:, second] += gross
    for boundary_index, boundary in enumerate(topology["engineering_boundaries"]):
        expected_boundary[:, leaf_lookup[boundary["leaf_id"]]] += arrays["engineering_boundary_outflow_m3"][:, boundary_index]
    local_residual = arrays["input_volume_m3"] + expected_net - expected_boundary - _m4_basin_overflow_np.diff(arrays["volume_m3"], axis=0)
    if _m4_basin_overflow_np.any(_m4_basin_overflow_np.abs(local_residual) > 1e-7):
        raise ValueError("overflow event basin storage closure failed")
    global_residual = arrays["input_volume_m3"].sum(axis=1) - expected_boundary.sum(axis=1) - _m4_basin_overflow_np.diff(arrays["volume_m3"].sum(axis=1))
    if not _m4_basin_overflow_np.allclose(global_residual, arrays["balance_residual_m3"], rtol=0, atol=1e-7):
        raise ValueError("overflow event saved global residual mismatch")
    if metadata.get("schema") == "td-original-bed-overflow-event-v2":
        if not _m4_basin_overflow_np.allclose(arrays["face_net_m3"], arrays["face_forward_m3"] - arrays["face_reverse_m3"], rtol=0, atol=1e-9):
            raise ValueError("overflow event net face ledger mismatch")
        if not _m4_basin_overflow_np.allclose(arrays["basin_net_internal_m3"], expected_net, rtol=0, atol=1e-9):
            raise ValueError("overflow event basin net ledger mismatch")
        if not _m4_basin_overflow_np.allclose(arrays["basin_gross_internal_m3"], expected_gross, rtol=0, atol=1e-9):
            raise ValueError("overflow event basin gross ledger mismatch")
        if not _m4_basin_overflow_np.allclose(arrays["basin_boundary_outflow_m3"], expected_boundary, rtol=0, atol=1e-9):
            raise ValueError("overflow event basin boundary ledger mismatch")
        if not _m4_basin_overflow_np.allclose(arrays["basin_balance_residual_m3"], local_residual, rtol=0, atol=1e-9):
            raise ValueError("overflow event basin residual mismatch")
    if not _m4_basin_overflow_np.issubdtype(arrays["spill_onset_step"].dtype, _m4_basin_overflow_np.integer):
        raise ValueError("overflow event onset must be integer")
    active = arrays["face_volume_m3"] > 0
    expected_onset = _m4_basin_overflow_np.where(active.any(axis=0), active.argmax(axis=0), -1) if faces else _m4_basin_overflow_np.empty(0, _m4_basin_overflow_np.int64)
    if not _m4_basin_overflow_np.array_equal(arrays["spill_onset_step"], expected_onset):
        raise ValueError("overflow event onset differs from actual exchange")
    if _m4_basin_overflow_np.any(arrays["spill_onset_step"] < -1) or _m4_basin_overflow_np.any(arrays["spill_onset_step"] >= steps):
        raise ValueError("overflow event onset index invalid")
    if _m4_basin_overflow_np.any(_m4_basin_overflow_np.abs(arrays["balance_residual_m3"]) > 1e-7):
        raise ValueError("overflow event water ledger failed")
    return True

# --- terrain_pipeline/td_basin_overflow.py:409 ---
def _topology_payload(result):
    return {"schema": "td-original-bed-overflow-topology-v1", "metadata": result["metadata"],
               "arrays": {key: value.tolist() for key, value in result["arrays"].items()},
               "faces": result["faces"], "engineering_boundaries": result["engineering_boundaries"]}

# --- terrain_pipeline/td_basin_overflow.py:415 ---
def add_saved_overflow_accounting(event, topology):
    from terrain_pipeline.common_infra import identity as _m4_basin_overflow_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_overflow_readonly
    validate_overflow_event(event, topology)
    arrays = dict(event["arrays"])
    steps = event["metadata"]["steps"]
    leaf_lookup = {int(leaf): index for index, leaf in enumerate(topology["arrays"]["leaf_ids"])}
    net = _m4_basin_overflow_np.zeros((steps, len(leaf_lookup)), _m4_basin_overflow_np.float64)
    gross = _m4_basin_overflow_np.zeros_like(net)
    boundary = _m4_basin_overflow_np.zeros_like(net)
    signed = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    for face_index, face in enumerate(topology["faces"]):
        first, second = (leaf_lookup[leaf] for leaf in face["leaf_ids"])
        net[:, first] -= signed[:, face_index]
        net[:, second] += signed[:, face_index]
        gross[:, first] += arrays["face_volume_m3"][:, face_index]
        gross[:, second] += arrays["face_volume_m3"][:, face_index]
    for boundary_index, face in enumerate(topology["engineering_boundaries"]):
        boundary[:, leaf_lookup[face["leaf_id"]]] += arrays["engineering_boundary_outflow_m3"][:, boundary_index]
    arrays.update(face_net_m3=signed, basin_net_internal_m3=net, basin_gross_internal_m3=gross,
                  basin_boundary_outflow_m3=boundary,
                  basin_balance_residual_m3=arrays["input_volume_m3"] + net - boundary - _m4_basin_overflow_np.diff(arrays["volume_m3"], axis=0))
    metadata = dict(event["metadata"], schema="td-original-bed-overflow-event-v2",
                    algorithm="synchronous-basin-face-exchange-v2",
                    flux_semantics="face_net_m3 is signed first-leaf-to-second-leaf volume; basin_net_internal_m3 is positive into a basin; gross exchange is a round-trip diagnostic")
    result = {"arrays": {key: _m4_basin_overflow_readonly(value) for key, value in arrays.items()}, "metadata": metadata}
    result["identity_sha256"] = _m4_basin_overflow_identity(result["arrays"], metadata)
    validate_overflow_event(result, topology)
    return result

# --- terrain_pipeline/td_basin_overflow.py:444 ---
def _topology_identity(result):
    return _hash(_topology_payload(result))

# --- terrain_pipeline/td_basin_overflow.py:448 ---
def save_overflow_topology(result, path):
    from terrain_pipeline.common_infra import publish_bytes as _m4_basin_overflow_publish_bytes
    payload = _topology_payload(result)
    if _hash(payload) != result["identity_sha256"]:
        raise ValueError("topology identity mismatch")
    payload["identity_sha256"] = result["identity_sha256"]
    _m4_basin_overflow_publish_bytes(path, _m4_basin_overflow_json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())

# --- terrain_pipeline/td_basin_overflow.py:456 ---
def load_overflow_topology(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import file_sha256 as _m4_basin_overflow_file_sha256
    from terrain_pipeline.common_infra import readonly as _m4_basin_overflow_readonly
    path = _m4_basin_overflow_Path(path)
    if _m4_basin_overflow_file_sha256(path) != expected_sha256:
        raise ValueError("overflow topology SHA mismatch")
    payload = _m4_basin_overflow_json.loads(path.read_bytes())
    digest = payload.pop("identity_sha256", None)
    if digest != expected_identity or _hash(payload) != digest:
        raise ValueError("overflow topology identity mismatch")
    arrays = {key: _m4_basin_overflow_readonly(_m4_basin_overflow_np.asarray(value)) for key, value in payload["arrays"].items()}
    return {"arrays": arrays, "metadata": payload["metadata"], "faces": payload["faces"],
            "engineering_boundaries": payload["engineering_boundaries"], "identity_sha256": digest}

# --- terrain_pipeline/td_basin_overflow.py:469 ---
def save_overflow_event(result, path):
    from terrain_pipeline.common_infra import publish_bytes as _m4_basin_overflow_publish_bytes
    payload = {"schema": "td-original-bed-overflow-event-json-v1", "metadata": result["metadata"],
               "arrays": {key: value.tolist() for key, value in result["arrays"].items()},
               "identity_sha256": result["identity_sha256"]}
    _m4_basin_overflow_publish_bytes(path, _m4_basin_overflow_json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())

# --- terrain_pipeline/td_basin_overflow.py:476 ---
def load_overflow_event(path, *, expected_sha256, expected_identity, topology):
    from terrain_pipeline.common_infra import file_sha256 as _m4_basin_overflow_file_sha256
    from terrain_pipeline.common_infra import readonly as _m4_basin_overflow_readonly
    path = _m4_basin_overflow_Path(path)
    if path.stat().st_size > 128 * 1024 * 1024 or _m4_basin_overflow_file_sha256(path) != expected_sha256:
        raise ValueError("overflow event hash/budget mismatch")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("nonfinite JSON value")

    payload = _m4_basin_overflow_json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=reject_constant)
    if payload.get("schema") != "td-original-bed-overflow-event-json-v1":
        raise ValueError("overflow event schema mismatch")
    digest = payload.get("identity_sha256")
    if digest != expected_identity:
        raise ValueError("overflow event identity pin mismatch")
    arrays = {key: _m4_basin_overflow_readonly(_m4_basin_overflow_np.asarray(value, dtype=_m4_basin_overflow_np.float64 if key != "spill_onset_step" else _m4_basin_overflow_np.int64))
              for key, value in payload["arrays"].items()}
    result = {"arrays": arrays, "metadata": payload["metadata"], "identity_sha256": digest}
    validate_overflow_event(result, topology)
    return result

# --- terrain_pipeline/td_basin_overflow_implicit.py:16 ---
STABLE_OVERFLOW_ALGORITHM = "implicit-original-bed-basin-face-exchange-v3"

# --- terrain_pipeline/td_basin_overflow_implicit.py:17 ---
IMPLICIT_MAX_ARRAY_BYTES = 128 * 1024 * 1024

# --- terrain_pipeline/td_basin_overflow_implicit.py:20 ---
class _ReservoirSystem:
    def __init__(self, topology, config):
        if topology["identity_sha256"] != _topology_identity(topology):
            raise ValueError("implicit reservoir topology identity mismatch")
        arrays = topology["arrays"]
        self.count = len(arrays["leaf_ids"])
        self.offsets = arrays["curve_offsets"]
        self.levels = arrays["curve_level_m"]
        self.areas = arrays["curve_area_m2"]
        self.bottom = self.levels[self.offsets[:-1]]
        self.curve_owner = _m4_basin_overflow_implicit_np.repeat(_m4_basin_overflow_implicit_np.arange(self.count), _m4_basin_overflow_implicit_np.diff(self.offsets))
        self.relative_levels = self.levels - self.bottom[self.curve_owner]
        lookup = {int(leaf): index for index, leaf in enumerate(arrays["leaf_ids"])}
        self.first = _m4_basin_overflow_implicit_np.array([lookup[face["leaf_ids"][0]] for face in topology["faces"]], _m4_basin_overflow_implicit_np.int64)
        self.second = _m4_basin_overflow_implicit_np.array([lookup[face["leaf_ids"][1]] for face in topology["faces"]], _m4_basin_overflow_implicit_np.int64)
        sill = _m4_basin_overflow_implicit_np.array([face["sill_m"] for face in topology["faces"]])
        self.first_sill = sill - self.bottom[self.first]
        self.second_sill = sill - self.bottom[self.second]
        self.conductance = config.face_conductance_m_s * float(topology["metadata"]["spacing_m"])
        self.boundary_leaf = _m4_basin_overflow_implicit_np.array([lookup[face["leaf_id"]] for face in topology["engineering_boundaries"]], _m4_basin_overflow_implicit_np.int64)
        self.boundary_sill = _m4_basin_overflow_implicit_np.array([face["sill_m"] for face in topology["engineering_boundaries"]]) - self.bottom[self.boundary_leaf]
        self.boundary_conductance = config.boundary_conductance_m_s * _m4_basin_overflow_implicit_np.array([face["width_m"] for face in topology["engineering_boundaries"]])
        self.diagonal = _m4_basin_overflow_implicit_np.arange(self.count)
        self.rows = _m4_basin_overflow_implicit_np.concatenate((self.diagonal, self.first, self.second, self.first, self.second, self.boundary_leaf))
        self.columns = _m4_basin_overflow_implicit_np.concatenate((self.diagonal, self.first, self.second, self.second, self.first, self.boundary_leaf))

    def depth_at(self, volumes):
        return _m4_basin_overflow_implicit_np.array([_stage_at(volumes[index], self.levels[self.offsets[index]:self.offsets[index + 1]],
                                   self.areas[self.offsets[index]:self.offsets[index + 1]]) - self.bottom[index]
                         for index in range(self.count)])

    def evaluate(self, depth):
        excess = depth[self.curve_owner] - self.relative_levels
        volumes = _m4_basin_overflow_implicit_np.bincount(self.curve_owner, weights=self.areas * _m4_basin_overflow_implicit_np.maximum(excess, 0.), minlength=self.count)
        wet_area = _m4_basin_overflow_implicit_np.bincount(self.curve_owner, weights=self.areas * (excess >= 0.), minlength=self.count)
        first_head = depth[self.first] - self.first_sill
        second_head = depth[self.second] - self.second_sill
        flux = self.conductance * (_m4_basin_overflow_implicit_np.maximum(first_head, 0.) - _m4_basin_overflow_implicit_np.maximum(second_head, 0.))
        boundary_head = depth[self.boundary_leaf] - self.boundary_sill
        boundary_flux = self.boundary_conductance * _m4_basin_overflow_implicit_np.maximum(boundary_head, 0.)
        outflow = (_m4_basin_overflow_implicit_np.bincount(self.first, weights=flux, minlength=self.count)
                   - _m4_basin_overflow_implicit_np.bincount(self.second, weights=flux, minlength=self.count)
                   + _m4_basin_overflow_implicit_np.bincount(self.boundary_leaf, weights=boundary_flux, minlength=self.count))
        return volumes, wet_area, flux, boundary_flux, outflow, first_head, second_head, boundary_head

    def advance(self, previous, supplied, previous_depth, dt_s):
        depth = previous_depth.copy()
        for iteration in range(80):
            volume, wet_area, flux, boundary_flux, outflow, first_head, second_head, boundary_head = self.evaluate(depth)
            residual = volume - previous - supplied + dt_s * outflow
            norm = float(_m4_basin_overflow_implicit_np.max(_m4_basin_overflow_implicit_np.abs(residual)))
            merit = float(_m4_basin_overflow_implicit_np.sum(_m4_basin_overflow_implicit_np.abs(residual)))
            if norm <= 2e-9 and abs(float(residual.sum())) <= 2e-8:
                conservative = previous + supplied - dt_s * outflow
                if _m4_basin_overflow_implicit_np.any(conservative < -1e-8):
                    raise ValueError("implicit reservoir negative inventory")
                return _m4_basin_overflow_implicit_np.maximum(conservative, 0.), depth, dt_s * flux, dt_s * boundary_flux, iteration + 1, norm
            first_derivative = dt_s * self.conductance * (first_head >= 0.)
            second_derivative = dt_s * self.conductance * (second_head >= 0.)
            values = _m4_basin_overflow_implicit_np.concatenate((wet_area, first_derivative, second_derivative,
                                     -second_derivative, -first_derivative,
                                     dt_s * self.boundary_conductance * (boundary_head >= 0.)))
            jacobian = _m4_basin_overflow_implicit_coo_matrix((values, (self.rows, self.columns)), shape=(self.count, self.count)).tocsc()
            update = _m4_basin_overflow_implicit_spsolve(jacobian, -residual)
            if not _m4_basin_overflow_implicit_np.isfinite(update).all():
                raise ValueError("implicit reservoir nonfinite Newton update")
            scale = 1.0
            for attempt in range(32):
                candidate = _m4_basin_overflow_implicit_np.maximum(depth + scale * update, 0.)
                candidate_volume, _, _, _, candidate_outflow, *_ = self.evaluate(candidate)
                candidate_residual = candidate_volume - previous - supplied + dt_s * candidate_outflow
                if _m4_basin_overflow_implicit_np.sum(_m4_basin_overflow_implicit_np.abs(candidate_residual)) <= merit * (1. - 1e-4 * scale) + 2e-10:
                    depth = candidate
                    break
                scale *= .5
            else:
                raise ValueError("implicit reservoir line search failed")
        raise ValueError(f"implicit reservoir Newton budget exceeded: max_residual={norm}, total_abs={merit}, last_scale={scale}")

# --- terrain_pipeline/td_basin_overflow_implicit.py:100 ---
def simulate_stable_overflow(topology, rain_mm_h, *, parameters, substep_s=300.0, initial_volume_m3=None):
    from terrain_pipeline.common_infra import identity as _m4_basin_overflow_implicit_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_overflow_implicit_readonly
    if not isinstance(parameters, OverflowParameters):
        raise ValueError("OverflowParameters required")
    if (type(substep_s) not in (int, float) or not _m4_basin_overflow_implicit_math.isfinite(substep_s) or substep_s <= 0
            or parameters.timestep_s / substep_s != int(parameters.timestep_s / substep_s)):
        raise ValueError("output interval must contain integer positive implicit substeps")
    steps = int(parameters.duration_s / parameters.timestep_s)
    substeps = int(parameters.timestep_s / substep_s)
    if steps * substeps > OVERFLOW_MAX_STEPS:
        raise ValueError("implicit reservoir step budget exceeded")
    rain = _m4_basin_overflow_implicit_np.asarray(rain_mm_h, _m4_basin_overflow_implicit_np.float64)
    if rain.shape != (steps,) or not _m4_basin_overflow_implicit_np.isfinite(rain).all() or _m4_basin_overflow_implicit_np.any(rain < 0.):
        raise ValueError("invalid implicit reservoir rain vector")
    system = _ReservoirSystem(topology, parameters)
    count = system.count
    volumes = _m4_basin_overflow_implicit_np.zeros(count) if initial_volume_m3 is None else _m4_basin_overflow_implicit_np.asarray(initial_volume_m3, _m4_basin_overflow_implicit_np.float64).copy()
    if volumes.shape != (count,) or not _m4_basin_overflow_implicit_np.isfinite(volumes).all() or _m4_basin_overflow_implicit_np.any(volumes < 0.):
        raise ValueError("invalid implicit initial inventory")
    faces, boundaries = len(system.first), len(system.boundary_leaf)
    shapes = {"rain_mm_h": (steps,), "stage_m": (steps + 1, count), "volume_m3": (steps + 1, count),
              "input_volume_m3": (steps, count), "face_forward_m3": (steps, faces), "face_reverse_m3": (steps, faces),
              "face_volume_m3": (steps, faces), "face_net_m3": (steps, faces),
              "basin_net_internal_m3": (steps, count), "basin_gross_internal_m3": (steps, count),
              "basin_boundary_outflow_m3": (steps, count), "basin_balance_residual_m3": (steps, count),
              "engineering_boundary_outflow_m3": (steps, boundaries), "balance_residual_m3": (steps,),
              "face_forward_active_s": (steps, faces), "face_reverse_active_s": (steps, faces),
              "newton_max_residual_m3": (steps,), "newton_iterations": (steps,)}
    if sum(_m4_basin_overflow_implicit_math.prod(shape) * 8 for shape in shapes.values()) > IMPLICIT_MAX_ARRAY_BYTES:
        raise ValueError("implicit saved array byte budget exceeded")
    arrays = {name: _m4_basin_overflow_implicit_np.zeros(shape, _m4_basin_overflow_implicit_np.float64) for name, shape in shapes.items()}
    arrays["rain_mm_h"] = rain.copy()
    depth = system.depth_at(volumes)
    arrays["stage_m"][0] = system.bottom + depth
    arrays["volume_m3"][0] = volumes
    for step in range(steps):
        rate = rain[step] * parameters.runoff_coefficient / 3_600_000.0 + parameters.baseflow_mm_per_day / 86_400_000.0
        supplied = topology["arrays"]["leaf_area_m2"] * rate * substep_s
        arrays["input_volume_m3"][step] = supplied * substeps
        for substep in range(substeps):
            try:
                volumes, depth, signed, exported, iterations, residual = system.advance(volumes, supplied, depth, substep_s)
            except ValueError as error:
                raise ValueError(f"implicit interval={step}, substep={substep}: {error}") from error
            arrays["face_forward_m3"][step] += _m4_basin_overflow_implicit_np.maximum(signed, 0.)
            arrays["face_reverse_m3"][step] += _m4_basin_overflow_implicit_np.maximum(-signed, 0.)
            arrays["face_forward_active_s"][step] += (signed > 0.) * substep_s
            arrays["face_reverse_active_s"][step] += (signed < 0.) * substep_s
            arrays["engineering_boundary_outflow_m3"][step] += exported
            arrays["newton_max_residual_m3"][step] = max(arrays["newton_max_residual_m3"][step], residual)
            arrays["newton_iterations"][step] += iterations
        arrays["volume_m3"][step + 1] = volumes
        arrays["stage_m"][step + 1] = system.bottom + depth
    arrays["face_net_m3"] = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    arrays["face_volume_m3"] = arrays["face_forward_m3"] + arrays["face_reverse_m3"]
    for face_index, (first, second) in enumerate(zip(system.first, system.second)):
        arrays["basin_net_internal_m3"][:, first] -= arrays["face_net_m3"][:, face_index]
        arrays["basin_net_internal_m3"][:, second] += arrays["face_net_m3"][:, face_index]
        arrays["basin_gross_internal_m3"][:, first] += arrays["face_volume_m3"][:, face_index]
        arrays["basin_gross_internal_m3"][:, second] += arrays["face_volume_m3"][:, face_index]
    for boundary_index, leaf in enumerate(system.boundary_leaf):
        arrays["basin_boundary_outflow_m3"][:, leaf] += arrays["engineering_boundary_outflow_m3"][:, boundary_index]
    arrays["basin_balance_residual_m3"] = arrays["input_volume_m3"] + arrays["basin_net_internal_m3"] - arrays["basin_boundary_outflow_m3"] - _m4_basin_overflow_implicit_np.diff(arrays["volume_m3"], axis=0)
    arrays["balance_residual_m3"] = arrays["input_volume_m3"].sum(axis=1) - arrays["engineering_boundary_outflow_m3"].sum(axis=1) - _m4_basin_overflow_implicit_np.diff(arrays["volume_m3"].sum(axis=1))
    active = arrays["face_volume_m3"] > 0.
    arrays["spill_onset_step"] = _m4_basin_overflow_implicit_np.where(active.any(axis=0), active.argmax(axis=0), -1).astype(_m4_basin_overflow_implicit_np.int64) if faces else _m4_basin_overflow_implicit_np.empty(0, _m4_basin_overflow_implicit_np.int64)
    arrays["spill_last_active_step"] = _m4_basin_overflow_implicit_np.where(active.any(axis=0), steps - 1 - active[::-1].argmax(axis=0), -1).astype(_m4_basin_overflow_implicit_np.int64) if faces else _m4_basin_overflow_implicit_np.empty(0, _m4_basin_overflow_implicit_np.int64)
    metadata = {"schema": "td-original-bed-overflow-event-v2", "algorithm": STABLE_OVERFLOW_ALGORITHM,
                "topology_identity_sha256": topology["identity_sha256"],
                "hierarchy_identity_sha256": topology["metadata"]["hierarchy_identity_sha256"],
                "source_identity_sha256": topology["metadata"]["source_identity_sha256"],
                "parameters": _m4_basin_overflow_implicit_asdict(parameters), "steps": steps, "timestep_s": parameters.timestep_s,
                "duration_s": parameters.duration_s, "implicit_substep_s": substep_s,
                "integration": "backward Euler; coupled semismooth Newton with SciPy sparse linear solve; no explicit donor-emptying limiter",
                "flux_law": "same original law: conductance*(positive first head above sill - positive second head above sill)",
                "rain_semantics": "fixed runoff coefficient plus uniform baseflow, not four-store hydrology",
                "activity_semantics": "end-of-substep flux quadrature support; output-resolution first/last active steps are not exact threshold crossing times",
                "hydraulic_ready": False, "transient_converged": False, "natural_outlet_verified": False, "publishable": False}
    result = {"arrays": {name: _m4_basin_overflow_implicit_readonly(value) for name, value in arrays.items()}, "metadata": metadata}
    result["identity_sha256"] = _m4_basin_overflow_implicit_identity(result["arrays"], metadata)
    validate_stable_overflow(result, topology)
    return result

# --- terrain_pipeline/td_basin_overflow_implicit.py:183 ---
def validate_stable_overflow(event, topology):
    validate_overflow_event(event, topology)
    arrays, metadata = event["arrays"], event["metadata"]
    if metadata.get("algorithm") != STABLE_OVERFLOW_ALGORITHM:
        raise ValueError("stable overflow algorithm mismatch")
    config = OverflowParameters(**metadata["parameters"])
    if (metadata["steps"] * metadata["timestep_s"] != config.duration_s
            or metadata["timestep_s"] != config.timestep_s
            or metadata["implicit_substep_s"] <= 0
            or config.timestep_s / metadata["implicit_substep_s"] != int(config.timestep_s / metadata["implicit_substep_s"])):
        raise ValueError("stable overflow time contract mismatch")
    for name, volume_name in (("face_forward_active_s", "face_forward_m3"), ("face_reverse_active_s", "face_reverse_m3")):
        if (arrays[name].shape != arrays[volume_name].shape or _m4_basin_overflow_implicit_np.any(arrays[name] < 0.)
                or _m4_basin_overflow_implicit_np.any(arrays[name] > config.timestep_s) or not _m4_basin_overflow_implicit_np.array_equal(arrays[name] > 0., arrays[volume_name] > 0.)):
            raise ValueError("stable overflow activity mismatch")
    if _m4_basin_overflow_implicit_np.any(arrays["face_forward_active_s"] + arrays["face_reverse_active_s"] > config.timestep_s):
        raise ValueError("stable overflow bidirectional activity exceeds interval")
    active = arrays["face_volume_m3"] > 0.
    expected_last = _m4_basin_overflow_implicit_np.where(active.any(axis=0), metadata["steps"] - 1 - active[::-1].argmax(axis=0), -1) if active.shape[1] else _m4_basin_overflow_implicit_np.empty(0, _m4_basin_overflow_implicit_np.int64)
    if not _m4_basin_overflow_implicit_np.array_equal(arrays["spill_last_active_step"], expected_last):
        raise ValueError("stable overflow last active index mismatch")
    if _m4_basin_overflow_implicit_np.any(arrays["newton_max_residual_m3"] > 2e-9):
        raise ValueError("stable overflow nonlinear closure failed")
    return True

# --- terrain_pipeline/td_basin_overflow_implicit.py:209 ---
def save_stable_overflow(event, path, topology):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_overflow_implicit_save_bundle
    _m4_basin_overflow_implicit_save_bundle(path, event, validator=lambda result: validate_stable_overflow(result, topology))

# --- terrain_pipeline/td_basin_overflow_implicit.py:213 ---
def load_stable_overflow(path, *, expected_sha256, expected_identity, topology):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_overflow_implicit_load_bundle
    event = _m4_basin_overflow_implicit_load_bundle(_m4_basin_overflow_implicit_Path(path), expected_sha256=expected_sha256,
                        validator=lambda result: validate_stable_overflow(result, topology), max_bytes=IMPLICIT_MAX_ARRAY_BYTES)
    if event["identity_sha256"] != expected_identity:
        raise ValueError("stable overflow external identity mismatch")
    return event

# --- terrain_pipeline/td_basin_overflow_radau.py:17 ---
RADAU_OVERFLOW_ALGORITHM = "radau-conservative-original-bed-basin-face-exchange-v5"

# --- terrain_pipeline/td_basin_overflow_radau.py:18 ---
RADAU_WEIGHTS = _m4_basin_overflow_radau_np.array([(16. - _m4_basin_overflow_radau_math.sqrt(6.)) / 36., (16. + _m4_basin_overflow_radau_math.sqrt(6.)) / 36., 1. / 9.])

# --- terrain_pipeline/td_basin_overflow_radau.py:22 ---
@_m4_basin_overflow_radau_njit(cache=True)
def _invert_curves(volumes, offsets, relative_levels, capacities, cumulative_area):
    depth = _m4_basin_overflow_radau_np.empty(len(volumes), _m4_basin_overflow_radau_np.float64)
    area = _m4_basin_overflow_radau_np.empty(len(volumes), _m4_basin_overflow_radau_np.float64)
    for leaf in range(len(volumes)):
        start, end = offsets[leaf], offsets[leaf + 1]
        lower, upper = start, end
        while lower < upper:
            middle = (lower + upper) // 2
            if capacities[middle] <= volumes[leaf]:
                lower = middle + 1
            else:
                upper = middle
        interval = max(start, lower - 1)
        depth[leaf] = relative_levels[interval] + (volumes[leaf] - capacities[interval]) / cumulative_area[interval]
        area[leaf] = cumulative_area[interval]
    return depth, area

# --- terrain_pipeline/td_basin_overflow_radau.py:40 ---
class _IntegratedExchange:
    def __init__(self, topology, config):
        self.system = _ReservoirSystem(topology, config)
        system = self.system
        self.count, self.faces, self.boundaries = system.count, len(system.first), len(system.boundary_leaf)
        self.size = self.count + 2 * self.faces + self.boundaries
        self.capacities = _m4_basin_overflow_radau_np.zeros_like(system.areas)
        self.cumulative_area = _m4_basin_overflow_radau_np.zeros_like(system.areas)
        for start, end in zip(system.offsets[:-1], system.offsets[1:]):
            self.cumulative_area[start:end] = _m4_basin_overflow_radau_np.cumsum(system.areas[start:end])
            self.capacities[start:end] = (system.relative_levels[start:end] * self.cumulative_area[start:end]
                                          - _m4_basin_overflow_radau_np.cumsum(system.relative_levels[start:end] * system.areas[start:end]))
        self.supply_rate = _m4_basin_overflow_radau_np.zeros(self.count)

    def fields(self, values):
        system = self.system
        depth, area = _invert_curves(values[:self.count], system.offsets, system.relative_levels,
                                     self.capacities, self.cumulative_area)
        first_head = depth[system.first] - system.first_sill
        second_head = depth[system.second] - system.second_sill
        boundary_head = depth[system.boundary_leaf] - system.boundary_sill
        signed = system.conductance * (_m4_basin_overflow_radau_np.maximum(first_head, 0.) - _m4_basin_overflow_radau_np.maximum(second_head, 0.))
        boundary = system.boundary_conductance * _m4_basin_overflow_radau_np.maximum(boundary_head, 0.)
        return depth, area, first_head, second_head, boundary_head, signed, boundary

    def rhs(self, time_s, values):
        system = self.system
        _, _, _, _, _, signed, boundary = self.fields(values)
        inventory_rate = (self.supply_rate - _m4_basin_overflow_radau_np.bincount(system.first, weights=signed, minlength=self.count)
                          + _m4_basin_overflow_radau_np.bincount(system.second, weights=signed, minlength=self.count)
                          - _m4_basin_overflow_radau_np.bincount(system.boundary_leaf, weights=boundary, minlength=self.count))
        return _m4_basin_overflow_radau_np.concatenate((inventory_rate, _m4_basin_overflow_radau_np.maximum(signed, 0.), _m4_basin_overflow_radau_np.maximum(-signed, 0.), boundary))

    def jacobian(self, time_s, values):
        system = self.system
        _, area, first_head, second_head, boundary_head, signed, _ = self.fields(values)
        first = system.conductance * (first_head > 0.) / area[system.first]
        second = system.conductance * (second_head > 0.) / area[system.second]
        boundary = system.boundary_conductance * (boundary_head > 0.) / area[system.boundary_leaf]
        forward_rows = self.count + _m4_basin_overflow_radau_np.arange(self.faces)
        reverse_rows = self.count + self.faces + _m4_basin_overflow_radau_np.arange(self.faces)
        boundary_rows = self.count + 2 * self.faces + _m4_basin_overflow_radau_np.arange(self.boundaries)
        rows = _m4_basin_overflow_radau_np.concatenate((system.first, system.first, system.second, system.second, system.boundary_leaf,
                               forward_rows, forward_rows, reverse_rows, reverse_rows, boundary_rows))
        columns = _m4_basin_overflow_radau_np.concatenate((system.first, system.second, system.first, system.second, system.boundary_leaf,
                                  system.first, system.second, system.first, system.second, system.boundary_leaf))
        derivatives = _m4_basin_overflow_radau_np.concatenate((-first, second, first, -second, -boundary,
                                       first * (signed > 0.), -second * (signed > 0.),
                                       -first * (signed < 0.), second * (signed < 0.), boundary))
        return _m4_basin_overflow_radau_coo_matrix((derivatives, (rows, columns)), shape=(self.size, self.size)).tocsc()

    def conservative_step(self, solver, previous, dt_s, atol, rtol):
        increments = _m4_basin_overflow_radau_np.zeros(2 * self.faces + self.boundaries)
        for weight, stage in zip(RADAU_WEIGHTS, solver.Z):
            *_, signed, boundary = self.fields(previous + stage)
            increments += dt_s * weight * _m4_basin_overflow_radau_np.concatenate((_m4_basin_overflow_radau_np.maximum(signed, 0.), _m4_basin_overflow_radau_np.maximum(-signed, 0.), boundary))
        signed_volume = increments[:self.faces] - increments[self.faces:2 * self.faces]
        system = self.system
        inventory = (previous[:self.count] + dt_s * self.supply_rate
                     - _m4_basin_overflow_radau_np.bincount(system.first, weights=signed_volume, minlength=self.count)
                     + _m4_basin_overflow_radau_np.bincount(system.second, weights=signed_volume, minlength=self.count)
                     - _m4_basin_overflow_radau_np.bincount(system.boundary_leaf, weights=increments[2 * self.faces:], minlength=self.count))
        updated = _m4_basin_overflow_radau_np.concatenate((inventory, previous[self.count:] + increments))
        defect = _m4_basin_overflow_radau_np.abs(updated - solver.y)
        scale = atol + rtol * _m4_basin_overflow_radau_np.maximum(_m4_basin_overflow_radau_np.abs(previous), _m4_basin_overflow_radau_np.abs(updated))
        normalized_defect = float(_m4_basin_overflow_radau_np.max(defect / scale))
        if not _m4_basin_overflow_radau_np.isfinite(updated).all() or _m4_basin_overflow_radau_np.any(inventory < 0.) or normalized_defect > .05:
            raise ValueError(f"Radau collocation balance defect or negative inventory: scaled_defect={normalized_defect}")
        solver.y = updated
        solver.f = self.rhs(solver.t, updated)
        return normalized_defect, float(defect[:self.count].max())

# --- terrain_pipeline/td_basin_overflow_radau.py:113 ---
def simulate_radau_overflow(topology, rain_mm_h, *, parameters, max_step_s=300.,
                            rtol=1e-7, atol_stage_m=1e-7, flux_atol_m3=1e-6, initial_volume_m3=None):
    from terrain_pipeline.common_infra import identity as _m4_basin_overflow_radau_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_overflow_radau_readonly
    if not isinstance(parameters, OverflowParameters):
        raise ValueError("OverflowParameters required")
    if any(type(value) not in (int, float) or not _m4_basin_overflow_radau_math.isfinite(value) or value <= 0.
           for value in (max_step_s, rtol, atol_stage_m, flux_atol_m3)):
        raise ValueError("positive finite Radau step and tolerances required")
    steps = int(parameters.duration_s / parameters.timestep_s)
    rain = _m4_basin_overflow_radau_np.asarray(rain_mm_h, _m4_basin_overflow_radau_np.float64)
    if steps > OVERFLOW_MAX_STEPS or rain.shape != (steps,) or not _m4_basin_overflow_radau_np.isfinite(rain).all() or _m4_basin_overflow_radau_np.any(rain < 0.):
        raise ValueError("invalid Radau rain/output budget")
    exchange = _IntegratedExchange(topology, parameters)
    count, faces, boundaries = exchange.count, exchange.faces, exchange.boundaries
    initial = _m4_basin_overflow_radau_np.zeros(count) if initial_volume_m3 is None else _m4_basin_overflow_radau_np.asarray(initial_volume_m3, _m4_basin_overflow_radau_np.float64).copy()
    if initial.shape != (count,) or not _m4_basin_overflow_radau_np.isfinite(initial).all() or _m4_basin_overflow_radau_np.any(initial < 0.):
        raise ValueError("invalid Radau initial inventory")
    shapes = {"rain_mm_h": (steps,), "stage_m": (steps + 1, count), "volume_m3": (steps + 1, count),
              "input_volume_m3": (steps, count), "face_forward_m3": (steps, faces), "face_reverse_m3": (steps, faces),
              "face_volume_m3": (steps, faces), "face_net_m3": (steps, faces),
              "basin_net_internal_m3": (steps, count), "basin_gross_internal_m3": (steps, count),
              "basin_boundary_outflow_m3": (steps, count), "basin_balance_residual_m3": (steps, count),
              "engineering_boundary_outflow_m3": (steps, boundaries), "balance_residual_m3": (steps,)}
    if sum(_m4_basin_overflow_radau_math.prod(shape) * 8 for shape in shapes.values()) > IMPLICIT_MAX_ARRAY_BYTES:
        raise ValueError("Radau saved array byte budget exceeded")
    arrays = {name: _m4_basin_overflow_radau_np.zeros(shape) for name, shape in shapes.items()}
    arrays["rain_mm_h"] = rain.copy()
    arrays["volume_m3"][0] = initial
    values = _m4_basin_overflow_radau_np.concatenate((initial, _m4_basin_overflow_radau_np.zeros(2 * faces + boundaries)))
    depth, *_ = exchange.fields(values)
    arrays["stage_m"][0] = exchange.system.bottom + depth
    minimum_area = exchange.system.areas[exchange.system.offsets[:-1]]
    atol = _m4_basin_overflow_radau_np.concatenate((minimum_area * atol_stage_m, _m4_basin_overflow_radau_np.full(2 * faces + boundaries, flux_atol_m3)))
    accepted_steps = 0
    total_rhs, total_jacobian, total_lu = 0, 0, 0
    minimum_inventory = 0.
    maximum_scaled_defect = 0.
    maximum_inventory_correction = 0.
    solver = None
    previous_rain = None
    for step in range(steps):
        rate = rain[step] * parameters.runoff_coefficient / 3_600_000.0 + parameters.baseflow_mm_per_day / 86_400_000.0
        exchange.supply_rate = topology["arrays"]["leaf_area_m2"] * rate
        arrays["input_volume_m3"][step] = exchange.supply_rate * parameters.timestep_s
        start, end = step * parameters.timestep_s, (step + 1) * parameters.timestep_s
        before = values.copy()
        if solver is None or rain[step] != previous_rain:
            solver = _m4_basin_overflow_radau_Radau(exchange.rhs, start, values, parameters.duration_s, jac=exchange.jacobian,
                           max_step=min(max_step_s, parameters.timestep_s), rtol=rtol, atol=atol)
            solver.newton_tol = min(solver.newton_tol, 1e-8)
        before_rhs, before_jacobian, before_lu = solver.nfev, solver.njev, solver.nlu
        while solver.t < end:
            solver.max_step = min(max_step_s, end - solver.t)
            previous_step = solver.y.copy()
            previous_time = solver.t
            solver.step()
            accepted_steps += 1
            if solver.status == "failed" or accepted_steps > OVERFLOW_MAX_STEPS:
                raise ValueError("Radau integration failed or exceeded step budget")
            scaled_defect, correction = exchange.conservative_step(solver, previous_step, solver.t - previous_time, atol, rtol)
            maximum_scaled_defect = max(maximum_scaled_defect, scaled_defect)
            maximum_inventory_correction = max(maximum_inventory_correction, correction)
            minimum_inventory = min(minimum_inventory, float(solver.y[:count].min()))
            if minimum_inventory < -1e-8:
                raise ValueError("Radau integration produced negative basin inventory")
        values = solver.y.copy()
        previous_rain = rain[step]
        total_rhs += solver.nfev - before_rhs
        total_jacobian += solver.njev - before_jacobian
        total_lu += solver.nlu - before_lu
        arrays["volume_m3"][step + 1] = values[:count]
        depth, *_ = exchange.fields(values)
        arrays["stage_m"][step + 1] = exchange.system.bottom + depth
        arrays["face_forward_m3"][step] = values[count:count + faces] - before[count:count + faces]
        arrays["face_reverse_m3"][step] = values[count + faces:count + 2 * faces] - before[count + faces:count + 2 * faces]
        arrays["engineering_boundary_outflow_m3"][step] = values[count + 2 * faces:] - before[count + 2 * faces:]
        for name in ("face_forward_m3", "face_reverse_m3", "engineering_boundary_outflow_m3"):
            if arrays[name][step].size and arrays[name][step].min() < -1e-8:
                raise ValueError(f"negative directional quadrature in interval={step}, field={name}, min={arrays[name][step].min()}")
    arrays["face_net_m3"] = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    arrays["face_volume_m3"] = arrays["face_forward_m3"] + arrays["face_reverse_m3"]
    for face_index, (first, second) in enumerate(zip(exchange.system.first, exchange.system.second)):
        arrays["basin_net_internal_m3"][:, first] -= arrays["face_net_m3"][:, face_index]
        arrays["basin_net_internal_m3"][:, second] += arrays["face_net_m3"][:, face_index]
        arrays["basin_gross_internal_m3"][:, first] += arrays["face_volume_m3"][:, face_index]
        arrays["basin_gross_internal_m3"][:, second] += arrays["face_volume_m3"][:, face_index]
    for boundary_index, leaf in enumerate(exchange.system.boundary_leaf):
        arrays["basin_boundary_outflow_m3"][:, leaf] += arrays["engineering_boundary_outflow_m3"][:, boundary_index]
    arrays["basin_balance_residual_m3"] = arrays["input_volume_m3"] + arrays["basin_net_internal_m3"] - arrays["basin_boundary_outflow_m3"] - _m4_basin_overflow_radau_np.diff(arrays["volume_m3"], axis=0)
    arrays["balance_residual_m3"] = arrays["input_volume_m3"].sum(axis=1) - arrays["engineering_boundary_outflow_m3"].sum(axis=1) - _m4_basin_overflow_radau_np.diff(arrays["volume_m3"].sum(axis=1))
    active = arrays["face_volume_m3"] > 0.
    arrays["spill_onset_step"] = _m4_basin_overflow_radau_np.where(active.any(axis=0), active.argmax(axis=0), -1).astype(_m4_basin_overflow_radau_np.int64) if faces else _m4_basin_overflow_radau_np.empty(0, _m4_basin_overflow_radau_np.int64)
    arrays["spill_last_active_step"] = _m4_basin_overflow_radau_np.where(active.any(axis=0), steps - 1 - active[::-1].argmax(axis=0), -1).astype(_m4_basin_overflow_radau_np.int64) if faces else _m4_basin_overflow_radau_np.empty(0, _m4_basin_overflow_radau_np.int64)
    metadata = {"schema": "td-original-bed-overflow-event-v2", "algorithm": RADAU_OVERFLOW_ALGORITHM,
                "topology_identity_sha256": topology["identity_sha256"],
                "hierarchy_identity_sha256": topology["metadata"]["hierarchy_identity_sha256"],
                "source_identity_sha256": topology["metadata"]["source_identity_sha256"],
                "parameters": _m4_basin_overflow_radau_asdict(parameters), "steps": steps, "timestep_s": parameters.timestep_s,
                "duration_s": parameters.duration_s, "max_step_s": max_step_s, "rtol": rtol, "atol_stage_m": atol_stage_m,
                "flux_atol_m3": flux_atol_m3,
                "integration": "SciPy adaptive Radau IIA; positive collocation weights integrate actual stage fluxes; the same face volumes update both inventories and directional quadrature",
                "activity_semantics": "first/last active saved interval from actual quadrature; exact threshold crossing time is unresolved inside 300s",
                "rain_semantics": "fixed runoff coefficient plus baseflow, not four-store hydrology",
                "work": {"accepted_steps": accepted_steps, "rhs_evaluations": total_rhs,
                         "jacobian_evaluations": total_jacobian, "lu_factorizations": total_lu,
                         "minimum_inventory_m3": minimum_inventory,
                         "maximum_scaled_collocation_defect": maximum_scaled_defect,
                         "maximum_inventory_correction_m3": maximum_inventory_correction},
                "hydraulic_ready": False, "transient_converged": False, "natural_outlet_verified": False, "publishable": False}
    result = {"arrays": {name: _m4_basin_overflow_radau_readonly(value) for name, value in arrays.items()}, "metadata": metadata}
    result["identity_sha256"] = _m4_basin_overflow_radau_identity(result["arrays"], metadata)
    validate_radau_overflow(result, topology)
    return result

# --- terrain_pipeline/td_basin_overflow_radau.py:227 ---
def validate_radau_overflow(event, topology):
    validate_overflow_event(event, topology)
    if event["metadata"].get("algorithm") != RADAU_OVERFLOW_ALGORITHM:
        raise ValueError("Radau event algorithm mismatch")
    if event["metadata"]["work"]["minimum_inventory_m3"] < -1e-8:
        raise ValueError("Radau event negative internal inventory")
    return True

# --- terrain_pipeline/td_basin_overflow_radau.py:236 ---
def save_radau_overflow(event, path, topology):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_overflow_radau_save_bundle
    _m4_basin_overflow_radau_save_bundle(path, event, validator=lambda result: validate_radau_overflow(result, topology))

# --- terrain_pipeline/td_basin_overflow_radau.py:240 ---
def load_radau_overflow(path, *, expected_sha256, expected_identity, topology):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_overflow_radau_load_bundle
    event = _m4_basin_overflow_radau_load_bundle(_m4_basin_overflow_radau_Path(path), expected_sha256=expected_sha256,
                        validator=lambda result: validate_radau_overflow(result, topology), max_bytes=IMPLICIT_MAX_ARRAY_BYTES)
    if event["identity_sha256"] != expected_identity:
        raise ValueError("Radau event external identity mismatch")
    return event

# --- terrain_pipeline/td_basin_runoff_exchange.py:21 ---
RUNOFF_EXCHANGE_SCHEMA = "td-basin-runoff-exchange-v1"

# --- terrain_pipeline/td_basin_runoff_exchange.py:22 ---
RUNOFF_EXCHANGE_ALGORITHM = "lumped-three-store-runoff-radau-surface-exchange-v1"

# --- terrain_pipeline/td_basin_runoff_exchange.py:23 ---
EXCHANGE_MAX_STEPS = 100_000

# --- terrain_pipeline/td_basin_runoff_exchange.py:24 ---
MAX_ENTRIES = 1_000_000

# --- terrain_pipeline/td_basin_runoff_exchange.py:25 ---
EXCHANGE_MAX_ARRAY_BYTES = 128 * 1024 * 1024

# --- terrain_pipeline/td_basin_runoff_exchange.py:26 ---
SURFACE_KEYS = {
    "surface_volume_m3", "stage_m", "soil_volume_m3", "fast_volume_m3", "slow_volume_m3",
    "surface_input_volume_m3", "face_forward_m3", "face_reverse_m3", "face_net_m3",
    "basin_net_internal_m3", "engineering_boundary_outflow_m3", "basin_boundary_outflow_m3",
    "surface_balance_residual_m3", "total_water_m3", "total_balance_residual_m3",
}

# --- terrain_pipeline/td_basin_runoff_exchange.py:32 ---
ARRAY_KEYS = set(_m4_basin_runoff_exchange_RUNOFF_ARRAY_KEYS) | SURFACE_KEYS

# --- terrain_pipeline/td_basin_runoff_exchange.py:33 ---
FLAGS = ("hydraulic_ready", "transient_converged", "natural_outlet_verified", "publishable")

# --- terrain_pipeline/td_basin_runoff_exchange.py:34 ---
METADATA_KEYS = {"schema", "algorithm", "parameters", "runoff_metadata", "topology_identity_sha256",
                 "hierarchy_identity_sha256", "source_identity_sha256", "steps", "timestep_s", "duration_s",
                 "max_step_s", "rtol", "atol_stage_m", "flux_atol_m3", "work", "leaf_order",
                 "supply_semantics", "integration", "boundary_semantics", "balance_semantics", "limitations"} | set(FLAGS)

# --- terrain_pipeline/td_basin_runoff_exchange.py:38 ---
WORK_KEYS = {"accepted_steps", "rhs_evaluations", "jacobian_evaluations", "lu_factorizations",
             "maximum_scaled_collocation_defect", "maximum_inventory_correction_m3"}

# --- terrain_pipeline/td_basin_runoff_exchange.py:42 ---
def _positive(value, name, allow_zero=False):
    if (type(value) not in (int, float) or not _m4_basin_runoff_exchange_math.isfinite(value) or
            value < 0 or (not allow_zero and value == 0)):
        raise ValueError("invalid finite positive parameter: " + name)

# --- terrain_pipeline/td_basin_runoff_exchange.py:49 ---
@_m4_basin_runoff_exchange_dataclass(frozen=True)
class RunoffExchangeParameters:
    timestep_s: float = 300.
    duration_s: float = 3600.
    face_conductance_m_s: float = .6
    boundary_conductance_m_s: float = .6

    def __post_init__(self):
        for name, value in _m4_basin_runoff_exchange_asdict(self).items():
            _positive(value, name, allow_zero=name.endswith("conductance_m_s"))
        ratio = self.duration_s / self.timestep_s
        if not _m4_basin_runoff_exchange_math.isfinite(ratio) or ratio != int(ratio) or not 1 <= ratio <= EXCHANGE_MAX_STEPS:
            raise ValueError("duration must contain a bounded integer number of timesteps")

# --- terrain_pipeline/td_basin_runoff_exchange.py:63 ---
class _RunoffExchange(_IntegratedExchange):
    def set_runoff_volume(self, outflow_volume_m3, dt_s):
        if (outflow_volume_m3.shape != (self.count,) or not _m4_basin_runoff_exchange_np.isfinite(outflow_volume_m3).all()
                or _m4_basin_runoff_exchange_np.any(outflow_volume_m3 < 0)):
            raise ValueError("invalid runoff supply volume")
        self.supply_rate = outflow_volume_m3 / dt_s

# --- terrain_pipeline/td_basin_runoff_exchange.py:71 ---
def _exchange(topology, parameters):
    if (not isinstance(topology, dict) or topology.get("metadata", {}).get("schema") != OVERFLOW_SCHEMA or
            topology.get("identity_sha256") != _topology_identity(topology)):
        raise ValueError("runoff exchange requires pinned original-bed topology")
    return _RunoffExchange(topology, parameters)

# --- terrain_pipeline/td_basin_runoff_exchange.py:78 ---
def _shapes(steps, count, faces, boundaries):
    from terrain_pipeline.runoff import RUNOFF_ARRAY_KEYS as _m4_basin_runoff_exchange_RUNOFF_ARRAY_KEYS
    if steps * max(count, faces, boundaries, 1) > MAX_ENTRIES:
        raise ValueError("runoff exchange entry budget exceeded")
    shapes = {key: (steps, count) for key in _m4_basin_runoff_exchange_RUNOFF_ARRAY_KEYS}
    shapes["area_m2"] = (count,)
    for key in ("soil_mm", "fast_mm", "slow_mm", "surface_volume_m3", "stage_m",
                "soil_volume_m3", "fast_volume_m3", "slow_volume_m3", "total_water_m3"):
        shapes[key] = (steps + 1, count)
    for key in ("surface_input_volume_m3", "basin_net_internal_m3", "basin_boundary_outflow_m3",
                "surface_balance_residual_m3", "total_balance_residual_m3"):
        shapes[key] = (steps, count)
    for key in ("face_forward_m3", "face_reverse_m3", "face_net_m3"):
        shapes[key] = (steps, faces)
    shapes["engineering_boundary_outflow_m3"] = (steps, boundaries)
    if sum(_m4_basin_runoff_exchange_math.prod(shape) * 8 for shape in shapes.values()) > EXCHANGE_MAX_ARRAY_BYTES:
        raise ValueError("runoff exchange saved array budget exceeded")
    return shapes

# --- terrain_pipeline/td_basin_runoff_exchange.py:97 ---
def _internal_ledgers(arrays, exchange):
    steps = len(arrays["rain_mm_h"])
    net = _m4_basin_runoff_exchange_np.zeros((steps, exchange.count))
    boundary = _m4_basin_runoff_exchange_np.zeros_like(net)
    signed = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    for face, (first, second) in enumerate(zip(exchange.system.first, exchange.system.second)):
        net[:, first] -= signed[:, face]
        net[:, second] += signed[:, face]
    for face, leaf in enumerate(exchange.system.boundary_leaf):
        boundary[:, leaf] += arrays["engineering_boundary_outflow_m3"][:, face]
    return signed, net, boundary

# --- terrain_pipeline/td_basin_runoff_exchange.py:110 ---
def simulate_runoff_exchange(topology, rain_mm_h, *, parameters=None, runoff_parameters=None,
                             source_id="lumped-basin-rainfall", initial_surface_volume_m3=None,
                             max_step_s=300., rtol=1e-7, atol_stage_m=1e-7, flux_atol_m3=1e-6):
    from terrain_pipeline.common_infra import identity as _m4_basin_runoff_exchange_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_runoff_exchange_readonly
    from terrain_pipeline.runoff import RUNOFF_ARRAY_KEYS as _m4_basin_runoff_exchange_RUNOFF_ARRAY_KEYS
    from terrain_pipeline.runoff import simulate_rainfall_runoff as _m4_basin_runoff_exchange_simulate_rainfall_runoff
    parameters = RunoffExchangeParameters() if parameters is None else parameters
    if not isinstance(parameters, RunoffExchangeParameters):
        raise ValueError("RunoffExchangeParameters required; legacy coefficient/baseflow are not accepted")
    parameters.__post_init__()
    for name, value in (("max_step_s", max_step_s), ("rtol", rtol),
                        ("atol_stage_m", atol_stage_m), ("flux_atol_m3", flux_atol_m3)):
        _positive(value, name)
    exchange = _exchange(topology, parameters)
    steps = int(parameters.duration_s / parameters.timestep_s)
    count, faces, boundaries = exchange.count, exchange.faces, exchange.boundaries
    shapes = _shapes(steps, count, faces, boundaries)
    if (not isinstance(rain_mm_h, _m4_basin_runoff_exchange_np.ndarray) or rain_mm_h.shape != (steps, count)
            or rain_mm_h.dtype.kind not in "fiu" or not _m4_basin_runoff_exchange_np.isfinite(rain_mm_h).all()
            or _m4_basin_runoff_exchange_np.any(rain_mm_h < 0)):
        raise ValueError("rain_mm_h must be a finite nonnegative numeric [T,leaf] array, not bool")
    initial = _m4_basin_runoff_exchange_np.zeros(count)
    if initial_surface_volume_m3 is not None:
        raw = _m4_basin_runoff_exchange_np.asarray(initial_surface_volume_m3)
        if (raw.shape != (count,) or raw.dtype.kind not in "fiu" or
                not _m4_basin_runoff_exchange_np.isfinite(raw).all() or _m4_basin_runoff_exchange_np.any(raw < 0)):
            raise ValueError("invalid initial surface inventories")
        initial = raw.astype(_m4_basin_runoff_exchange_np.float64, copy=True)
    runoff = _m4_basin_runoff_exchange_simulate_rainfall_runoff(rain_mm_h, topology["arrays"]["leaf_area_m2"],
                                     dt_s=parameters.timestep_s, source_id=source_id,
                                     parameters=runoff_parameters)
    arrays = {key: runoff[key].copy() for key in _m4_basin_runoff_exchange_RUNOFF_ARRAY_KEYS}
    arrays.update({key: _m4_basin_runoff_exchange_np.zeros(shapes[key]) for key in SURFACE_KEYS})
    arrays["surface_volume_m3"][0] = initial
    values = _m4_basin_runoff_exchange_np.concatenate((initial, _m4_basin_runoff_exchange_np.zeros(2 * faces + boundaries)))
    depth, *_ = exchange.fields(values)
    arrays["stage_m"][0] = exchange.system.bottom + depth
    minimum_area = exchange.system.areas[exchange.system.offsets[:-1]]
    atol = _m4_basin_runoff_exchange_np.concatenate((minimum_area * atol_stage_m, _m4_basin_runoff_exchange_np.full(2 * faces + boundaries, flux_atol_m3)))
    work = {"accepted_steps": 0, "rhs_evaluations": 0, "jacobian_evaluations": 0,
            "lu_factorizations": 0, "maximum_scaled_collocation_defect": 0.,
            "maximum_inventory_correction_m3": 0.}
    for step in range(steps):
        exchange.set_runoff_volume(arrays["outflow_volume_m3"][step], parameters.timestep_s)
        arrays["surface_input_volume_m3"][step] = arrays["outflow_volume_m3"][step]
        start = step * parameters.timestep_s
        end = (step + 1) * parameters.timestep_s
        values = _m4_basin_runoff_exchange_np.concatenate((values[:count], _m4_basin_runoff_exchange_np.zeros(2 * faces + boundaries)))
        solver = _m4_basin_runoff_exchange_Radau(exchange.rhs, start, values, end, jac=exchange.jacobian,
                       max_step=min(max_step_s, parameters.timestep_s), rtol=rtol, atol=atol)
        solver.newton_tol = min(solver.newton_tol, 1e-8)
        while solver.status == "running":
            previous = solver.y.copy()
            previous_time = solver.t
            solver.step()
            work["accepted_steps"] += 1
            if solver.status == "failed" or work["accepted_steps"] > EXCHANGE_MAX_STEPS:
                raise ValueError("runoff exchange Radau integration failed or exceeded step budget")
            defect, correction = exchange.conservative_step(solver, previous, solver.t - previous_time, atol, rtol)
            work["maximum_scaled_collocation_defect"] = max(work["maximum_scaled_collocation_defect"], defect)
            work["maximum_inventory_correction_m3"] = max(work["maximum_inventory_correction_m3"], correction)
        work["rhs_evaluations"] += solver.nfev
        work["jacobian_evaluations"] += solver.njev
        work["lu_factorizations"] += solver.nlu
        values = solver.y.copy()
        arrays["surface_volume_m3"][step + 1] = values[:count]
        depth, *_ = exchange.fields(values)
        arrays["stage_m"][step + 1] = exchange.system.bottom + depth
        arrays["face_forward_m3"][step] = values[count:count + faces]
        arrays["face_reverse_m3"][step] = values[count + faces:count + 2 * faces]
        arrays["engineering_boundary_outflow_m3"][step] = values[count + 2 * faces:]
    signed, net, boundary = _internal_ledgers(arrays, exchange)
    arrays["face_net_m3"], arrays["basin_net_internal_m3"], arrays["basin_boundary_outflow_m3"] = signed, net, boundary
    arrays["surface_balance_residual_m3"] = arrays["outflow_volume_m3"] + net - boundary - _m4_basin_runoff_exchange_np.diff(arrays["surface_volume_m3"], axis=0)
    for store in ("soil", "fast", "slow"):
        arrays[store + "_volume_m3"] = arrays[store + "_mm"] * arrays["area_m2"] / 1000.
    arrays["total_water_m3"] = sum(arrays[store + "_volume_m3"] for store in ("soil", "fast", "slow", "surface"))
    arrays["total_balance_residual_m3"] = arrays["rain_volume_m3"] - arrays["et_volume_m3"] + net - boundary - _m4_basin_runoff_exchange_np.diff(arrays["total_water_m3"], axis=0)
    metadata = {"schema": RUNOFF_EXCHANGE_SCHEMA, "algorithm": RUNOFF_EXCHANGE_ALGORITHM, "parameters": _m4_basin_runoff_exchange_asdict(parameters),
                "runoff_metadata": runoff["metadata"], "topology_identity_sha256": topology["identity_sha256"],
                "hierarchy_identity_sha256": topology["metadata"]["hierarchy_identity_sha256"],
                "source_identity_sha256": topology["metadata"]["source_identity_sha256"],
                "steps": steps, "timestep_s": parameters.timestep_s, "duration_s": parameters.duration_s,
                "max_step_s": max_step_s, "rtol": rtol, "atol_stage_m": atol_stage_m, "flux_atol_m3": flux_atol_m3,
                "work": work, "leaf_order": "topology arrays.leaf_ids order; rainfall columns are not remapped",
                "supply_semantics": "runoff outflow_volume_m3 / timestep_s is the sole piecewise-constant surface supply",
                "integration": "Radau IIA positive stage weights; same conservative_step flux quadrature updates surface and face ledgers",
                "boundary_semantics": "one-way engineering perimeter outflow; no controlled tailwater inflow",
                "balance_semantics": "balance_residual_m3 is the three-store runoff ledger; surface and total ledgers are independent per leaf",
                "limitations": ["lumped independent-leaf runoff; no surface reinfiltration", "not native-grid v10 four-store hydrology", "no natural outlet or calibrated catchment certification"],
                **{flag: False for flag in FLAGS}}
    result = {"arrays": {key: _m4_basin_runoff_exchange_readonly(value) for key, value in arrays.items()}, "metadata": metadata}
    result["identity_sha256"] = _m4_basin_runoff_exchange_identity(result["arrays"], metadata)
    validate_runoff_exchange(result, topology)
    return result

# --- terrain_pipeline/td_basin_runoff_exchange.py:204 ---
def _equal(actual, expected, name):
    if not _m4_basin_runoff_exchange_np.allclose(actual, expected, rtol=1e-10, atol=1e-8):
        raise ValueError("runoff exchange ledger mismatch: " + name)

# --- terrain_pipeline/td_basin_runoff_exchange.py:209 ---
def _balanced(residual, scale, name):
    if _m4_basin_runoff_exchange_np.any(_m4_basin_runoff_exchange_np.abs(residual) > 1e-8 + 1e-10 * scale):
        raise ValueError("runoff exchange nonconservative " + name)

# --- terrain_pipeline/td_basin_runoff_exchange.py:214 ---
def validate_runoff_exchange(result, topology):
    from terrain_pipeline.common_infra import identity as _m4_basin_runoff_exchange_identity
    from terrain_pipeline.runoff import RUNOFF_ARRAY_KEYS as _m4_basin_runoff_exchange_RUNOFF_ARRAY_KEYS
    from terrain_pipeline.runoff import validate_rainfall_runoff_result as _m4_basin_runoff_exchange_validate_rainfall_runoff_result
    if not isinstance(result, dict) or set(result) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid runoff exchange bundle")
    arrays, metadata = result["arrays"], result["metadata"]
    if (not isinstance(arrays, dict) or set(arrays) != ARRAY_KEYS or not isinstance(metadata, dict) or
            set(metadata) != METADATA_KEYS or
            metadata.get("schema") != RUNOFF_EXCHANGE_SCHEMA or metadata.get("algorithm") != RUNOFF_EXCHANGE_ALGORITHM):
        raise ValueError("runoff exchange schema/fields mismatch")
    for flag in FLAGS:
        if metadata.get(flag) is not False:
            raise ValueError("runoff exchange certification flags must remain false")
    try:
        parameters = RunoffExchangeParameters(**metadata["parameters"])
    except (KeyError, TypeError) as error:
        raise ValueError("invalid runoff exchange parameters") from error
    exchange = _exchange(topology, parameters)
    steps = int(parameters.duration_s / parameters.timestep_s)
    if (type(metadata.get("steps")) is not int or metadata["steps"] != steps or
            metadata.get("timestep_s") != parameters.timestep_s or metadata.get("duration_s") != parameters.duration_s or
            metadata.get("topology_identity_sha256") != topology["identity_sha256"] or
            metadata.get("hierarchy_identity_sha256") != topology["metadata"]["hierarchy_identity_sha256"] or
            metadata.get("source_identity_sha256") != topology["metadata"]["source_identity_sha256"]):
        raise ValueError("runoff exchange topology/time identity mismatch")
    for name in ("max_step_s", "rtol", "atol_stage_m", "flux_atol_m3"):
        _positive(metadata.get(name), name)
    work = metadata["work"]
    if not isinstance(work, dict) or set(work) != WORK_KEYS:
        raise ValueError("invalid runoff exchange work summary")
    for name in ("accepted_steps", "rhs_evaluations", "jacobian_evaluations", "lu_factorizations"):
        if type(work[name]) is not int or work[name] < 0:
            raise ValueError("invalid runoff exchange work count")
    if not steps <= work["accepted_steps"] <= EXCHANGE_MAX_STEPS:
        raise ValueError("runoff exchange work step budget exceeded")
    for name in ("maximum_scaled_collocation_defect", "maximum_inventory_correction_m3"):
        _positive(work[name], name, allow_zero=True)
    if work["maximum_scaled_collocation_defect"] > .05:
        raise ValueError("runoff exchange collocation defect exceeds accepted bound")
    shapes = _shapes(steps, exchange.count, exchange.faces, exchange.boundaries)
    for name, shape in shapes.items():
        value = arrays[name]
        if not isinstance(value, _m4_basin_runoff_exchange_np.ndarray) or value.shape != shape or value.dtype != _m4_basin_runoff_exchange_np.float64 or not _m4_basin_runoff_exchange_np.isfinite(value).all():
            raise ValueError("invalid runoff exchange array: " + name)
    runoff = {key: arrays[key] for key in _m4_basin_runoff_exchange_RUNOFF_ARRAY_KEYS}
    runoff["metadata"] = metadata["runoff_metadata"]
    _m4_basin_runoff_exchange_validate_rainfall_runoff_result(runoff)
    if runoff["metadata"]["dt_s"] != parameters.timestep_s:
        raise ValueError("runoff and exchange timestep mismatch")
    _equal(arrays["area_m2"], topology["arrays"]["leaf_area_m2"], "runoff leaf areas")
    for name in ("surface_volume_m3", "surface_input_volume_m3", "face_forward_m3", "face_reverse_m3", "engineering_boundary_outflow_m3"):
        if _m4_basin_runoff_exchange_np.any(arrays[name] < 0):
            raise ValueError("negative runoff exchange inventory/flux: " + name)
    _equal(arrays["surface_input_volume_m3"], arrays["outflow_volume_m3"], "sole surface supply")
    signed, net, boundary = _internal_ledgers(arrays, exchange)
    _equal(arrays["face_net_m3"], signed, "face signed volumes")
    _equal(arrays["basin_net_internal_m3"], net, "paired internal exchange")
    _equal(arrays["basin_boundary_outflow_m3"], boundary, "engineering outflow")
    surface_change = _m4_basin_runoff_exchange_np.diff(arrays["surface_volume_m3"], axis=0)
    surface_residual = arrays["outflow_volume_m3"] + net - boundary - surface_change
    _equal(arrays["surface_balance_residual_m3"], surface_residual, "surface residual")
    _balanced(surface_residual, arrays["outflow_volume_m3"] + _m4_basin_runoff_exchange_np.abs(net) + boundary + _m4_basin_runoff_exchange_np.abs(surface_change), "surface")
    for store in ("soil", "fast", "slow"):
        _equal(arrays[store + "_volume_m3"], arrays[store + "_mm"] * arrays["area_m2"] / 1000., store + " volume")
    total = sum(arrays[store + "_volume_m3"] for store in ("soil", "fast", "slow", "surface"))
    _equal(arrays["total_water_m3"], total, "four-store total water")
    total_change = _m4_basin_runoff_exchange_np.diff(total, axis=0)
    residual = arrays["rain_volume_m3"] - arrays["et_volume_m3"] + net - boundary - total_change
    _equal(arrays["total_balance_residual_m3"], residual, "total residual")
    _balanced(residual, arrays["rain_volume_m3"] + arrays["et_volume_m3"] + _m4_basin_runoff_exchange_np.abs(net) + boundary + _m4_basin_runoff_exchange_np.abs(total_change), "four-store total")
    global_residual = arrays["rain_volume_m3"].sum(axis=1) - arrays["et_volume_m3"].sum(axis=1) - boundary.sum(axis=1) - total_change.sum(axis=1)
    _balanced(global_residual, arrays["rain_volume_m3"].sum(axis=1) + arrays["et_volume_m3"].sum(axis=1) + boundary.sum(axis=1) + _m4_basin_runoff_exchange_np.abs(total_change).sum(axis=1), "global total")
    for step, volumes in enumerate(arrays["surface_volume_m3"]):
        depth, *_ = exchange.fields(_m4_basin_runoff_exchange_np.concatenate((volumes, _m4_basin_runoff_exchange_np.zeros(exchange.size - exchange.count))))
        _equal(arrays["stage_m"][step], exchange.system.bottom + depth, "surface stage/volume")
    if result["identity_sha256"] != _m4_basin_runoff_exchange_identity(arrays, metadata):
        raise ValueError("runoff exchange identity mismatch")
    return True

# --- terrain_pipeline/td_basin_runoff_exchange.py:292 ---
def save_runoff_exchange(result, path, topology):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_runoff_exchange_save_bundle
    _m4_basin_runoff_exchange_save_bundle(path, result, validator=lambda event: validate_runoff_exchange(event, topology))

# --- terrain_pipeline/td_basin_runoff_exchange.py:296 ---
def load_runoff_exchange(path, *, expected_sha256, expected_identity, topology):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_runoff_exchange_load_bundle
    parameters = RunoffExchangeParameters()
    exchange = _exchange(topology, parameters)

    def headers(values):
        if set(values) != ARRAY_KEYS | {"manifest"}:
            raise ValueError("unexpected runoff exchange archive fields")
        shape, _ = values["rain_mm_h"]
        if len(shape) != 2 or not 1 <= shape[0] <= EXCHANGE_MAX_STEPS or shape[1] != exchange.count:
            raise ValueError("invalid runoff exchange archive rain shape")
        expected = _shapes(shape[0], exchange.count, exchange.faces, exchange.boundaries)
        if any(values[key] != (wanted, _m4_basin_runoff_exchange_np.dtype("float64")) for key, wanted in expected.items()):
            raise ValueError("runoff exchange archive array shapes/dtypes mismatch")

    result = _m4_basin_runoff_exchange_load_bundle(path, expected_sha256=expected_sha256, max_bytes=EXCHANGE_MAX_ARRAY_BYTES,
                         header_validator=headers, validator=lambda event: validate_runoff_exchange(event, topology))
    if result["identity_sha256"] != expected_identity:
        raise ValueError("runoff exchange external identity mismatch")
    return result

# --- terrain_pipeline/td_basin_storage_dispatch_io.py:9 ---
DISPATCH_MAX_STORAGE_BYTES = 256 * 1024 * 1024

# --- terrain_pipeline/td_basin_storage_dispatch_io.py:10 ---
VERSIONS = {
    ("finite-time-D4-threshold-storage-v1", None): (20000, 500000000),
    ("D4-analytic-face-Strang-splitting-v2", None): (100000, 3000000000),
    ("D4-analytic-face-Strang-splitting-v2", "v2-full-refinement-6e9-v1"): (100000, 6000000000),
    ("D4-analytic-face-event-Strang-v3", None): (100000, 6000000000),
    ("D4-threshold-exact-Strang-v4", "v4-threshold-pair-compiled-6e9-v1"): (100000, 6000000000),
    ("D4-threshold-symmetric-forcing-Strang-v5", "v5-symmetric-forcing-6e9-v1"): (100000, 6000000000),
    ("D4-threshold-symmetric-forcing-SSPRK2-v6", "v6-simultaneous-SSPRK2-6e9-v1"): (100000, 6000000000),
}

# --- terrain_pipeline/td_basin_storage_dispatch_io.py:21 ---
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
        if type(config[name]) not in (int, float) or not _m4_basin_storage_dispatch_io_math.isfinite(config[name]) or config[name] < 0:
            raise ValueError("invalid saved coefficient")
    if config["substep_s"] <= 0 or config["wet_threshold_m"] <= 0:
        raise ValueError("invalid saved step/threshold")
    for name, limit in zip(("max_substeps", "max_work_face_steps"), limits):
        if type(config[name]) is not int or not 1 <= config[name] <= limit:
            raise ValueError("invalid saved work budget")
    if type(metadata["spacing_m"]) not in (int, float) or not _m4_basin_storage_dispatch_io_math.isfinite(metadata["spacing_m"]) or metadata["spacing_m"] <= 0:
        raise ValueError("invalid saved spacing")
    origin = metadata["origin_m_xz"]
    if len(origin) != 2 or any(type(value) not in (int, float) or not _m4_basin_storage_dispatch_io_math.isfinite(value) for value in origin):
        raise ValueError("invalid saved origin")
    if any(type(metadata[name]) not in (int, float) or not _m4_basin_storage_dispatch_io_math.isfinite(metadata[name]) or metadata[name] <= 0 for name in ("dt_s", "substep_s")) or metadata["substep_s"] > metadata["dt_s"]:
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

# --- terrain_pipeline/td_basin_storage_dispatch_io.py:64 ---
def dispatch_validate_saved_storage(result):
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_dispatch_io_identity
    from terrain_pipeline.runoff import RunoffParameters as _m4_basin_storage_dispatch_io_RunoffParameters
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("schema") != "td-basin-storage-v1" or _m4_basin_storage_dispatch_io_identity(arrays, metadata) != result["identity_sha256"]:
        raise ValueError("saved storage schema/identity mismatch")
    config = _configuration(metadata)
    _m4_basin_storage_dispatch_io_RunoffParameters(**metadata["runoff_parameters"])
    bed, valid = arrays["height_m"], arrays["valid_mask"]
    cells = bed.size
    rain = arrays["rain_mm_h"]
    if rain.ndim != 2 or rain.shape[1] != cells or not 1 <= len(rain) <= 1000:
        raise ValueError("invalid forcing shape")
    subdivisions = _m4_basin_storage_dispatch_io_math.ceil(metadata["dt_s"] / config["substep_s"])
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
    if bed.dtype != _m4_basin_storage_dispatch_io_np.float64 or not 1 <= cells <= 250000 or len(rain) * cells > 4000000 or not valid.any():
        raise ValueError("invalid saved grid/allocation")
    boundary = arrays["boundary_cells"]
    widths = arrays["boundary_width_m"]
    if boundary.dtype != _m4_basin_storage_dispatch_io_np.int64 or boundary.ndim != 1 or _m4_basin_storage_dispatch_io_np.any((boundary < 0) | (boundary >= cells)) or len(_m4_basin_storage_dispatch_io_np.unique(boundary)) != len(boundary):
        raise ValueError("invalid unique boundary cells")
    boundary_rows, boundary_columns = _m4_basin_storage_dispatch_io_np.divmod(boundary, bed.shape[1])
    side_count = ((boundary_rows == 0).astype(int) + (boundary_rows == bed.shape[0] - 1)
                  + (boundary_columns == 0) + (boundary_columns == bed.shape[1] - 1))
    if not valid.ravel()[boundary].all() or _m4_basin_storage_dispatch_io_np.any(side_count == 0) or widths.dtype != _m4_basin_storage_dispatch_io_np.float64 or widths.shape != boundary.shape or not _m4_basin_storage_dispatch_io_np.array_equal(widths, side_count * metadata["spacing_m"]):
        raise ValueError("boundary cells/widths must match valid exterior sides")
    declared_boundary = _m4_basin_storage_dispatch_io_np.zeros(cells, bool)
    declared_boundary[boundary] = True
    if _m4_basin_storage_dispatch_io_np.any(arrays["boundary_outflow_m3"][:, ~declared_boundary] != 0):
        raise ValueError("outflow on undeclared boundary cell")
    pools = arrays["wet_pool_count"]
    if pools.dtype != _m4_basin_storage_dispatch_io_np.int64 or pools.shape != (len(rain) + 1,) or _m4_basin_storage_dispatch_io_np.any((pools < 0) | (pools > valid.sum())):
        raise ValueError("invalid saved wet pool count")
    for key in states + ledgers:
        shape = (len(rain) + 1, cells) if key in states else rain.shape
        if arrays[key].shape != shape or arrays[key].dtype != _m4_basin_storage_dispatch_io_np.float64:
            raise ValueError("invalid state/ledger shape or dtype")
    for key, value in arrays.items():
        if not _m4_basin_storage_dispatch_io_np.isfinite(value).all():
            raise ValueError("nonfinite storage array")
        if key not in ("height_m", "receiver", "internal_net_m3", "storage_change_m3", "balance_residual_m3") and _m4_basin_storage_dispatch_io_np.any(value < 0):
            raise ValueError("negative water account")
    for key in states + ledgers + ("rain_mm_h",):
        if _m4_basin_storage_dispatch_io_np.any(arrays[key][:, ~valid.ravel()] != 0):
            raise ValueError("water state/forcing on unknown cells")
    area = metadata["spacing_m"] ** 2
    volume = area * (arrays["depth_m"] + sum(arrays[key] for key in ("soil_mm", "fast_mm", "slow_mm")) / 1000)

    def near(actual, expected):
        if _m4_basin_storage_dispatch_io_np.any(abs(actual - expected) > 1e-6 + 1e-10 * (abs(actual) + abs(expected))):
            raise ValueError("nonconservative saved water ledger")

    near(arrays["storage_change_m3"], _m4_basin_storage_dispatch_io_np.diff(volume, axis=0))
    near(arrays["rain_volume_m3"], rain * metadata["dt_s"] / 3600 * area / 1000)
    near(arrays["rain_volume_m3"], arrays["lake_rain_m3"] + arrays["land_rain_m3"])
    residual = (arrays["rain_volume_m3"] + arrays["internal_net_m3"] - arrays["soil_et_m3"]
                - arrays["surface_et_m3"] - arrays["boundary_outflow_m3"] - _m4_basin_storage_dispatch_io_np.diff(volume, axis=0))
    near(arrays["balance_residual_m3"], residual)
    near(residual, _m4_basin_storage_dispatch_io_np.zeros_like(residual))
    near(arrays["internal_net_m3"].sum(axis=1), _m4_basin_storage_dispatch_io_np.zeros(len(rain)))
    faces = arrays["face_cells"]
    if faces.dtype != _m4_basin_storage_dispatch_io_np.int64 or faces.ndim != 2 or faces.shape[1] != 2 or _m4_basin_storage_dispatch_io_np.any((faces < 0) | (faces >= cells)):
        raise ValueError("invalid saved D4 face")
    first, second = faces[:, 0], faces[:, 1]
    columns = bed.shape[1]
    if _m4_basin_storage_dispatch_io_np.any(abs(first // columns - second // columns) + abs(first % columns - second % columns) != 1) or not valid.ravel()[faces].all():
        raise ValueError("unknown/non-D4 exchange")
    face_keys = _m4_basin_storage_dispatch_io_np.minimum(first, second) * cells + _m4_basin_storage_dispatch_io_np.maximum(first, second)
    if len(_m4_basin_storage_dispatch_io_np.unique(face_keys)) != len(faces):
        raise ValueError("duplicate physical face including reversed pair")
    for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        if arrays[key].shape != (len(faces),) or arrays[key].dtype != _m4_basin_storage_dispatch_io_np.float64:
            raise ValueError("invalid face ledger")
    for flow, duration_key in (("face_forward_m3", "active_forward_s"), ("face_reverse_m3", "active_reverse_s")):
        if _m4_basin_storage_dispatch_io_np.any(arrays[duration_key] > len(rain) * metadata["dt_s"] + 1e-8) or _m4_basin_storage_dispatch_io_np.any(
                (arrays[flow] == 0) & (arrays[duration_key] != 0)):
            raise ValueError("invalid directional face activity duration")
    net = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    net_cells = _m4_basin_storage_dispatch_io_np.bincount(second, weights=net, minlength=cells) - _m4_basin_storage_dispatch_io_np.bincount(first, weights=net, minlength=cells)
    near(arrays["internal_net_m3"].sum(axis=0), net_cells)
    receiver = arrays["receiver"]
    if receiver.dtype != _m4_basin_storage_dispatch_io_np.int64 or receiver.shape != (cells,) or _m4_basin_storage_dispatch_io_np.any((receiver < -1) | (receiver >= cells)):
        raise ValueError("invalid receiver")
    donor = _m4_basin_storage_dispatch_io_np.flatnonzero(receiver >= 0)
    targets = receiver[donor]
    receiver_keys = _m4_basin_storage_dispatch_io_np.minimum(donor, targets) * cells + _m4_basin_storage_dispatch_io_np.maximum(donor, targets)
    if _m4_basin_storage_dispatch_io_np.any(receiver[~valid.ravel()] != -1) or not valid.ravel()[donor].all() or not valid.ravel()[targets].all() or not _m4_basin_storage_dispatch_io_np.isin(receiver_keys, face_keys).all() or _m4_basin_storage_dispatch_io_np.any(bed.ravel()[targets] > bed.ravel()[donor]):
        raise ValueError("receiver must follow valid nonascending saved D4 face")
    complete = _m4_basin_storage_dispatch_io_np.zeros(cells, bool)
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
    expected_routed = _m4_basin_storage_dispatch_io_np.zeros(cells)
    _m4_basin_storage_dispatch_io_np.add.at(expected_routed, first, _m4_basin_storage_dispatch_io_np.where(receiver[first] == second, arrays["face_forward_m3"], 0))
    _m4_basin_storage_dispatch_io_np.add.at(expected_routed, second, _m4_basin_storage_dispatch_io_np.where(receiver[second] == first, arrays["face_reverse_m3"], 0))
    near(arrays["routed_volume_m3"], expected_routed)
    if arrays["routed_volume_m3"].dtype != _m4_basin_storage_dispatch_io_np.float64 or arrays["routed_volume_m3"].shape != (cells,) or arrays["wet_duration_s"].dtype != _m4_basin_storage_dispatch_io_np.float64 or arrays["wet_duration_s"].shape != (cells,) or _m4_basin_storage_dispatch_io_np.any(arrays["wet_duration_s"] > len(rain) * metadata["dt_s"] + 1e-8):
        raise ValueError("invalid positive receiver flow duration")
    if _m4_basin_storage_dispatch_io_np.any((arrays["routed_volume_m3"] == 0) & (arrays["wet_duration_s"] != 0)):
        raise ValueError("duration without actual routed flux")
    if metadata["substeps"] > config["max_substeps"] or metadata["substeps"] * len(faces) > config["max_work_face_steps"]:
        raise ValueError("saved work budget exceeded")
    if diagnostic_keys <= set(arrays):
        for key in diagnostic_keys:
            if arrays[key].shape != (len(rain),) or arrays[key].dtype != _m4_basin_storage_dispatch_io_np.int64:
                raise ValueError("invalid limiter diagnostic")
        if _m4_basin_storage_dispatch_io_np.any(arrays["limiter_active_count"] > arrays["proposed_active_count"]):
            raise ValueError("invalid limiter count")


    if _m4_basin_storage_dispatch_io_np.any(arrays["active_forward_s"] + arrays["active_reverse_s"] > len(rain) * metadata["dt_s"] + 1e-8):
        raise ValueError("combined directional activity exceeds elapsed time")
    if metadata["algorithm"] == "D4-threshold-symmetric-forcing-SSPRK2-v6":
        degree = _m4_basin_storage_dispatch_io_np.bincount(faces.reshape(-1), minlength=cells).astype(float)
        _m4_basin_storage_dispatch_io_np.add.at(degree, arrays["boundary_cells"], arrays["boundary_width_m"] / metadata["spacing_m"])
        cfl = float(degree.max(initial=0)) * config["face_conductance_m_s"] * metadata["substep_s"] / metadata["spacing_m"]
        if not _m4_basin_storage_dispatch_io_math.isfinite(cfl) or cfl > 1 or metadata.get("positivity_cfl") != cfl:
            raise ValueError("saved v6 positivity CFL mismatch")
    return True

# --- terrain_pipeline/td_basin_storage_dispatch_io.py:200 ---
def dispatch_load_storage(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_storage_dispatch_io_load_bundle
    result = _m4_basin_storage_dispatch_io_load_bundle(path, expected_sha256=expected_sha256, validator=dispatch_validate_saved_storage,
                         max_bytes=DISPATCH_MAX_STORAGE_BYTES, header_validator=_storage_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external storage identity mismatch")
    return result

# --- terrain_pipeline/td_basin_storage_dispatch_io.py:208 ---
def dispatch_save_storage(path, result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_storage_dispatch_io_save_bundle
    _m4_basin_storage_dispatch_io_save_bundle(path, result, validator=dispatch_validate_saved_storage)

# --- terrain_pipeline/td_basin_storage_dispatch_io.py:212 ---
def _storage_headers(headers):
    height_shape, height_dtype = headers.get("height_m", ((), _m4_basin_storage_dispatch_io_np.dtype("O")))
    rain_shape, rain_dtype = headers.get("rain_mm_h", ((), _m4_basin_storage_dispatch_io_np.dtype("O")))
    if (len(height_shape) != 2 or not 1 <= _m4_basin_storage_dispatch_io_math.prod(height_shape) <= 250000 or height_dtype != _m4_basin_storage_dispatch_io_np.float64 or
            len(rain_shape) != 2 or rain_shape[1] != _m4_basin_storage_dispatch_io_math.prod(height_shape) or not 1 <= rain_shape[0] <= 1000 or
            _m4_basin_storage_dispatch_io_math.prod(rain_shape) > 4_000_000 or rain_dtype != _m4_basin_storage_dispatch_io_np.float64):
        raise ValueError("storage header grid/time allocation rejection")
    states = {"depth_m", "soil_mm", "fast_mm", "slow_mm"}
    ledgers = {"rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3", "rain_mm_h"}
    for key in states | ledgers:
        expected_shape = (rain_shape[0] + 1, rain_shape[1]) if key in states else rain_shape
        if headers.get(key) != (expected_shape, _m4_basin_storage_dispatch_io_np.dtype("float64")):
            raise ValueError("storage state/ledger header mismatch")
    if headers.get("valid_mask") != (height_shape, _m4_basin_storage_dispatch_io_np.dtype(bool)):
        raise ValueError("storage mask header mismatch")
    face_shape, face_dtype = headers.get("face_cells", ((), _m4_basin_storage_dispatch_io_np.dtype("O")))
    if len(face_shape) != 2 or face_shape[1] != 2 or face_shape[0] > 2 * rain_shape[1] or face_dtype != _m4_basin_storage_dispatch_io_np.int64:
        raise ValueError("storage face allocation rejection")
    for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        if headers.get(key) != ((face_shape[0],), _m4_basin_storage_dispatch_io_np.dtype("float64")):
            raise ValueError("storage directional header mismatch")
    for key, dtype in (("receiver", _m4_basin_storage_dispatch_io_np.int64), ("routed_volume_m3", _m4_basin_storage_dispatch_io_np.float64), ("wet_duration_s", _m4_basin_storage_dispatch_io_np.float64)):
        if headers.get(key) != ((rain_shape[1],), _m4_basin_storage_dispatch_io_np.dtype(dtype)):
            raise ValueError("storage receiver output header mismatch")
    if headers.get("wet_pool_count") != ((rain_shape[0] + 1,), _m4_basin_storage_dispatch_io_np.dtype("int64")):
        raise ValueError("storage pool count header mismatch")
    boundary_shape, boundary_dtype = headers.get("boundary_cells", ((), _m4_basin_storage_dispatch_io_np.dtype("O")))
    if len(boundary_shape) != 1 or boundary_shape[0] > rain_shape[1] or boundary_dtype != _m4_basin_storage_dispatch_io_np.int64 or headers.get("boundary_width_m") != (boundary_shape, _m4_basin_storage_dispatch_io_np.dtype("float64")):
        raise ValueError("storage boundary header mismatch")
    manifest_shape, manifest_dtype = headers.get("manifest", ((), _m4_basin_storage_dispatch_io_np.dtype("O")))
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= 1048576 or manifest_dtype != _m4_basin_storage_dispatch_io_np.uint8:
        raise ValueError("storage manifest header mismatch")
    required = states | ledgers | {"height_m", "valid_mask", "face_cells", "face_forward_m3", "face_reverse_m3",
        "active_forward_s", "active_reverse_s", "receiver", "routed_volume_m3", "wet_duration_s", "wet_pool_count",
        "boundary_cells", "boundary_width_m", "manifest"}
    diagnostic_keys = {"limiter_active_count", "proposed_active_count", "donor_limited_count"}
    if set(headers) not in (required, required | diagnostic_keys):
        raise ValueError("unexpected storage archive headers")
    if diagnostic_keys <= set(headers):
        for key in diagnostic_keys:
            if headers[key] != ((rain_shape[0],), _m4_basin_storage_dispatch_io_np.dtype("int64")):
                raise ValueError("invalid limiter diagnostic header")

# --- terrain_pipeline/td_basin_storage_v5_io.py:7 ---
STORAGEV5_PROFILE = "v5-symmetric-forcing-6e9-v1"

# --- terrain_pipeline/td_basin_storage_v5_io.py:10 ---
def storagev5_validate_saved_storage(result):
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_v5_io_identity
    arrays, metadata = result["arrays"], result["metadata"]
    if (metadata["algorithm"] != "D4-threshold-symmetric-forcing-Strang-v5" or metadata.get("work_profile") != STORAGEV5_PROFILE or
            result["identity_sha256"] != _m4_basin_storage_v5_io_identity(arrays, metadata)):
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
                            "identity_sha256": _m4_basin_storage_v5_io_identity(arrays, checked_metadata)})
    if not _m4_basin_storage_v5_io_np.isfinite([metadata["dt_s"], metadata["substep_s"]]).all() or not 0 < metadata["substep_s"] <= metadata["dt_s"]:
        raise ValueError("v5 invalid physical time")
    total_time = len(arrays["rain_mm_h"]) * metadata["dt_s"]
    if _m4_basin_storage_v5_io_np.any(arrays["active_forward_s"] + arrays["active_reverse_s"] > total_time + 1e-8):
        raise ValueError("v5 combined face activity exceeds physical time")
    return True

# --- terrain_pipeline/td_basin_storage_v5_io.py:34 ---
def storagev5_save_storage(path, result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_storage_v5_io_save_bundle
    _m4_basin_storage_v5_io_save_bundle(path, result, validator=storagev5_validate_saved_storage)

# --- terrain_pipeline/td_basin_storage_v5_io.py:38 ---
def storagev5_load_storage(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_storage_v5_io_load_bundle
    result = _m4_basin_storage_v5_io_load_bundle(path, expected_sha256=expected_sha256, validator=storagev5_validate_saved_storage,
                         max_bytes=STORAGE_MAX_STORAGE_BYTES, header_validator=storage_storage_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external v5 identity mismatch")
    return result

# --- terrain_pipeline/td_basin_storage_v6_io.py:7 ---
STORAGEV6_PROFILE = "v6-simultaneous-SSPRK2-6e9-v1"

# --- terrain_pipeline/td_basin_storage_v6_io.py:10 ---
def storagev6_validate_saved_storage(result):
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_v6_io_identity
    arrays, metadata = result["arrays"], result["metadata"]
    if (metadata["algorithm"] != "D4-threshold-symmetric-forcing-SSPRK2-v6" or metadata.get("work_profile") != STORAGEV6_PROFILE or
            result["identity_sha256"] != _m4_basin_storage_v6_io_identity(arrays, metadata)):
        raise ValueError("v6 storage identity/profile mismatch")
    for name in ("hydraulic_ready", "transient_converged", "morphology_flux_ready", "natural_outlet_verified"):
        if metadata.get(name) is not False:
            raise ValueError("v6 saved flags cannot assert physical certification")
    semantics = {"forcing_semantics": "runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
                 "saved_time_semantics": "state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
                 "activity_semantics": "RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity"}
    if any(metadata.get(name) != expected for name, expected in semantics.items()):
        raise ValueError("v6 saved time/forcing semantics mismatch")
    spacing = metadata["spacing_m"]
    degree = _m4_basin_storage_v6_io_np.bincount(arrays["face_cells"].reshape(-1), minlength=arrays["height_m"].size).astype(float)
    _m4_basin_storage_v6_io_np.add.at(degree, arrays["boundary_cells"], arrays["boundary_width_m"] / spacing)
    cfl = float(degree.max(initial=0)) * metadata["parameters"]["face_conductance_m_s"] * metadata["substep_s"] / spacing
    if not _m4_basin_storage_v6_io_np.isfinite(cfl) or not _m4_basin_storage_v6_io_np.isfinite(metadata.get("positivity_cfl", _m4_basin_storage_v6_io_np.nan)) or cfl > 1 or metadata["positivity_cfl"] != cfl:
        raise ValueError("v6 saved positivity CFL mismatch/exceeded")
    checked_metadata = {**metadata, "algorithm": "D4-threshold-exact-Strang-v4", "work_profile": "v4-threshold-pair-compiled-6e9-v1"}
    validate_basin_storage({"arrays": arrays, "metadata": checked_metadata,
                            "identity_sha256": _m4_basin_storage_v6_io_identity(arrays, checked_metadata)})
    if not _m4_basin_storage_v6_io_np.isfinite([metadata["dt_s"], metadata["substep_s"]]).all() or not 0 < metadata["substep_s"] <= metadata["dt_s"]:
        raise ValueError("v6 invalid physical time")
    total_time = len(arrays["rain_mm_h"]) * metadata["dt_s"]
    if _m4_basin_storage_v6_io_np.any(arrays["active_forward_s"] + arrays["active_reverse_s"] > total_time + 1e-8):
        raise ValueError("v6 combined face activity exceeds physical time")
    return True

# --- terrain_pipeline/td_basin_storage_v6_io.py:40 ---
def storagev6_save_storage(path, result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_storage_v6_io_save_bundle
    _m4_basin_storage_v6_io_save_bundle(path, result, validator=storagev6_validate_saved_storage)

# --- terrain_pipeline/td_basin_storage_v6_io.py:44 ---
def storagev6_load_storage(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_storage_v6_io_load_bundle
    result = _m4_basin_storage_v6_io_load_bundle(path, expected_sha256=expected_sha256, validator=storagev6_validate_saved_storage,
                         max_bytes=STORAGE_MAX_STORAGE_BYTES, header_validator=storage_storage_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external v6 identity mismatch")
    return result

# --- terrain_pipeline/td_basin_storage_v7_io.py:7 ---
STORAGEV7_PROFILE = "v7-compensated-forcing-SSPRK2-6e9-v1"

# --- terrain_pipeline/td_basin_storage_v7_io.py:10 ---
def storagev7_validate_saved_storage(result):
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_v7_io_identity
    arrays, metadata = result["arrays"], result["metadata"]
    if (metadata["algorithm"] != "D4-threshold-compensated-forcing-SSPRK2-v7" or metadata.get("work_profile") != STORAGEV7_PROFILE or
            result["identity_sha256"] != _m4_basin_storage_v7_io_identity(arrays, metadata)):
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
    degree = _m4_basin_storage_v7_io_np.bincount(arrays["face_cells"].reshape(-1), minlength=arrays["height_m"].size).astype(float)
    _m4_basin_storage_v7_io_np.add.at(degree, arrays["boundary_cells"], arrays["boundary_width_m"] / spacing)
    cfl = float(degree.max(initial=0)) * metadata["parameters"]["face_conductance_m_s"] * metadata["substep_s"] / spacing
    if not _m4_basin_storage_v7_io_np.isfinite(cfl) or not _m4_basin_storage_v7_io_np.isfinite(metadata.get("positivity_cfl", _m4_basin_storage_v7_io_np.nan)) or cfl > 1 or metadata["positivity_cfl"] != cfl:
        raise ValueError("v7 saved positivity CFL mismatch/exceeded")
    checked_metadata = {**metadata, "algorithm": "D4-threshold-exact-Strang-v4", "work_profile": "v4-threshold-pair-compiled-6e9-v1"}
    validate_basin_storage({"arrays": arrays, "metadata": checked_metadata,
                            "identity_sha256": _m4_basin_storage_v7_io_identity(arrays, checked_metadata)})
    if not _m4_basin_storage_v7_io_np.isfinite([metadata["dt_s"], metadata["substep_s"]]).all() or not 0 < metadata["substep_s"] <= metadata["dt_s"]:
        raise ValueError("v7 invalid physical time")
    total_time = len(arrays["rain_mm_h"]) * metadata["dt_s"]
    if _m4_basin_storage_v7_io_np.any(arrays["active_forward_s"] + arrays["active_reverse_s"] > total_time + 1e-8):
        raise ValueError("v7 combined face activity exceeds physical time")
    return True

# --- terrain_pipeline/td_basin_storage_v7_io.py:42 ---
def storagev7_save_storage(path, result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_storage_v7_io_save_bundle
    _m4_basin_storage_v7_io_save_bundle(path, result, validator=storagev7_validate_saved_storage)

# --- terrain_pipeline/td_basin_storage_v7_io.py:46 ---
def storagev7_load_storage(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_storage_v7_io_load_bundle
    result = _m4_basin_storage_v7_io_load_bundle(path, expected_sha256=expected_sha256, validator=storagev7_validate_saved_storage,
                         max_bytes=STORAGE_MAX_STORAGE_BYTES, header_validator=storage_storage_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external v7 identity mismatch")
    return result

# --- terrain_pipeline/td_basin_storage_continuation_io.py:9 ---
def continuation_validate_saved_storage(result):
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_continuation_io_identity
    arrays, metadata = result["arrays"], result["metadata"]
    if result["identity_sha256"] != _m4_basin_storage_continuation_io_identity(arrays,metadata) or metadata["algorithm"] != "D4-threshold-checkpoint-SSPRK2-v8" or metadata["work_profile"] != "v8-hour-pages-v7-SSPRK2":
        raise ValueError("v8 page identity/profile mismatch")
    if metadata["saved_time_semantics"] != "state0 is checkpoint time; state[k] at chunk_start_s+k*dt_s; ledger[k] covers local hour k" or metadata["chunk_start_s"] < 0 or metadata["chunk_end_s"] != metadata["chunk_start_s"]+len(arrays["rain_mm_h"])*metadata["dt_s"]:
        raise ValueError("v8 page global time mismatch")
    if not _m4_basin_storage_continuation_io_np.isfinite([metadata["chunk_start_s"],metadata["chunk_end_s"]]).all() or metadata["forcing_hour_offset"]*metadata["dt_s"] != metadata["chunk_start_s"] or _m4_basin_storage_continuation_io_re.fullmatch("[0-9a-f]{64}",metadata.get("forcing_identity","")) is None:
        raise ValueError("v8 page forcing/time identity invalid")
    checked = {**metadata,"algorithm":"D4-threshold-compensated-forcing-SSPRK2-v7","work_profile":"v7-compensated-forcing-SSPRK2-6e9-v1",
               "saved_time_semantics":"state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]"}
    storagev7_validate_saved_storage({"arrays":arrays,"metadata":checked,"identity_sha256":_m4_basin_storage_continuation_io_identity(arrays,checked)})
    return True

# --- terrain_pipeline/td_basin_storage_continuation_io.py:23 ---
def continuation_save_storage(path,result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_storage_continuation_io_save_bundle
    _m4_basin_storage_continuation_io_save_bundle(path,result,validator=continuation_validate_saved_storage)

# --- terrain_pipeline/td_basin_storage_continuation_io.py:27 ---
def continuation_load_storage(path,*,expected_sha256,expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_storage_continuation_io_load_bundle
    result=_m4_basin_storage_continuation_io_load_bundle(path,expected_sha256=expected_sha256,validator=continuation_validate_saved_storage,max_bytes=STORAGE_MAX_STORAGE_BYTES,header_validator=storage_storage_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external v8 page identity mismatch")
    return result

# --- terrain_pipeline/td_basin_storage_compiled_io.py:9 ---
COMPILED_IO_PROFILE="v9-compiled-hour-loop-v8-equivalent-v1"

# --- terrain_pipeline/td_basin_storage_compiled_io.py:12 ---
def compiled_validate_saved_storage(result):
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_compiled_io_identity
    arrays,metadata=result["arrays"],result["metadata"]
    if result["identity_sha256"]!=_m4_basin_storage_compiled_io_identity(arrays,metadata) or metadata["algorithm"]!="D4-threshold-compiled-hour-SSPRK2-v9" or metadata["work_profile"]!=COMPILED_IO_PROFILE:
        raise ValueError("v9 execution identity/profile mismatch")
    if type(metadata.get("substeps")) is not int or type(metadata.get("forcing_hour_offset")) is not int or metadata["substeps"]<1 or metadata["forcing_hour_offset"]<0:
        raise ValueError("v9 page integer time counts required")
    if metadata["substeps"]*metadata["substep_s"] != len(arrays["rain_mm_h"])*metadata["dt_s"]:
        raise ValueError("v9 page actual substep count mismatch")
    subdivisions=_m4_basin_storage_compiled_io_math.ceil(metadata["dt_s"]/metadata["parameters"]["substep_s"])
    if metadata["substeps"]!=len(arrays["rain_mm_h"])*subdivisions or metadata["substep_s"]!=metadata["dt_s"]/subdivisions:
        raise ValueError("v9 configured versus actual substeps mismatch")
    checked={**metadata,"algorithm":"D4-threshold-checkpoint-SSPRK2-v8","work_profile":"v8-hour-pages-v7-SSPRK2"}
    return continuation_validate_saved_storage({"arrays":arrays,"metadata":checked,"identity_sha256":_m4_basin_storage_compiled_io_identity(arrays,checked)})

# --- terrain_pipeline/td_basin_storage_compiled_io.py:27 ---
def compiled_validate_checkpoint(result):
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_compiled_io_identity
    arrays,metadata=result["arrays"],result["metadata"]
    if result["identity_sha256"]!=_m4_basin_storage_compiled_io_identity(arrays,metadata) or metadata["execution_profile"]!=COMPILED_IO_PROFILE:
        raise ValueError("v9 checkpoint profile/identity mismatch")
    subdivisions=_m4_basin_storage_compiled_io_math.ceil(metadata["dt_s"]/metadata["parameters"]["substep_s"])
    if metadata["substeps"] != metadata["elapsed_s"]/metadata["dt_s"]*subdivisions or metadata["substep_s"] != metadata["dt_s"]/subdivisions:
        raise ValueError("v9 checkpoint configured count mismatch")
    if _m4_basin_storage_compiled_io_np.any(arrays["cumulative_wet_duration_s"]>metadata["elapsed_s"]+1e-8):
        raise ValueError("v9 cumulative receiver activity exceeds elapsed")
    checked={**metadata,"execution_profile":"v8-hour-pages-v7-SSPRK2"}
    return checkpoint_validate_checkpoint({"arrays":arrays,"metadata":checked,"identity_sha256":_m4_basin_storage_compiled_io_identity(arrays,checked)})

# --- terrain_pipeline/td_basin_storage_compiled_io.py:40 ---
def compiled_save_storage(path,result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_storage_compiled_io_save_bundle
    _m4_basin_storage_compiled_io_save_bundle(path,result,validator=compiled_validate_saved_storage)

# --- terrain_pipeline/td_basin_storage_compiled_io.py:44 ---
def compiledio_save_checkpoint(path,result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_storage_compiled_io_save_bundle
    _m4_basin_storage_compiled_io_save_bundle(path,result,validator=compiled_validate_checkpoint)

# --- terrain_pipeline/td_basin_storage_compiled_io.py:48 ---
def compiled_load_storage(path,*,expected_sha256,expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_storage_compiled_io_load_bundle
    result=_m4_basin_storage_compiled_io_load_bundle(path,expected_sha256=expected_sha256,validator=compiled_validate_saved_storage,max_bytes=STORAGE_MAX_STORAGE_BYTES,header_validator=storage_storage_headers)
    if result["identity_sha256"]!=expected_identity:
        raise ValueError("external v9 storage identity mismatch")
    return result

# --- terrain_pipeline/td_basin_storage_compiled_io.py:55 ---
def compiled_load_checkpoint(path,*,expected_sha256,expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_storage_compiled_io_load_bundle
    result=_m4_basin_storage_compiled_io_load_bundle(path,expected_sha256=expected_sha256,validator=compiled_validate_checkpoint,max_bytes=128*1024*1024,header_validator=checkpoint_headers)
    if result["identity_sha256"]!=expected_identity:
        raise ValueError("external v9 checkpoint identity mismatch")
    return result

# --- terrain_pipeline/td_basin_storage_v10_io.py:8 ---
STORAGEV10_PROFILE = 'v10-unified-infiltration-SSPRK2-hour-pages-v1'

# --- terrain_pipeline/td_basin_storage_v10_io.py:9 ---
STATES = ('depth_m', 'soil_mm', 'fast_mm', 'slow_mm')

# --- terrain_pipeline/td_basin_storage_v10_io.py:10 ---
ERRORS = ('error_depth', 'error_soil', 'error_fast', 'error_slow')

# --- terrain_pipeline/td_basin_storage_v10_io.py:11 ---
LEDGERS = ('rain_volume_m3', 'rain_infiltration_m3', 'surface_infiltration_m3',
    'rain_excess_m3', 'soil_et_m3', 'surface_et_m3', 'local_release_m3', 'percolation_m3',
    'internal_net_m3', 'boundary_outflow_m3', 'storage_change_m3', 'balance_residual_m3',
    'infiltration_capacity_m3')

# --- terrain_pipeline/td_basin_storage_v10_io.py:15 ---
FLUX = ('face_forward_m3', 'face_reverse_m3', 'active_forward_s', 'active_reverse_s',
        'routed_volume_m3', 'wet_duration_s')

# --- terrain_pipeline/td_basin_storage_v10_io.py:17 ---
STATIC = ('height_m', 'valid_mask', 'face_cells', 'receiver', 'boundary_cells', 'boundary_width_m')

# --- terrain_pipeline/td_basin_storage_v10_io.py:20 ---
def _metadata(result):
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_v10_io_identity
    arrays, metadata = result['arrays'], result['metadata']
    if result['identity_sha256'] != _m4_basin_storage_v10_io_identity(arrays, metadata) or metadata.get('profile') != STORAGEV10_PROFILE:
        raise ValueError('v10 profile/identity mismatch')
    physical = metadata.get('parameters', {})
    if physical.get('runoff') != [15.,150.,.15,1.,3600.,259200.] or physical.get('face_conductance_m_s') != .6 or physical.get('surface_evaporation_mm_h') != .15 or physical.get('forcing_profile') != 'v10-unified-rain-surface-infiltration-experimental-v1':
        raise ValueError('v10 complete physical parameters mismatch')
    origin = metadata.get('origin_m_xz')
    if not isinstance(origin,list) or len(origin)!=2 or any(type(value) not in (int,float) or not _m4_basin_storage_v10_io_math.isfinite(value) for value in origin):
        raise ValueError('v10 native origin invalid')
    for key in ('forcing_identity', 'hierarchy_identity'):
        if _m4_basin_storage_v10_io_re.fullmatch('[0-9a-f]{64}', metadata.get(key, '')) is None:
            raise ValueError('v10 external identity syntax invalid')
    for key in ('cells', 'faces', 'substeps', 'forcing_hour_offset'):
        if type(metadata.get(key)) is not int or metadata[key] < 0:
            raise ValueError('v10 integer counts required')
    for key in ('dt_s', 'substep_s', 'spacing_m', 'start_s', 'end_s', 'positivity_cfl'):
        if type(metadata.get(key)) not in (int, float) or not _m4_basin_storage_v10_io_math.isfinite(metadata[key]):
            raise ValueError('v10 finite time/CFL required')
    if (metadata['dt_s'] != 3600 or metadata['substep_s'] <= 0 or metadata['spacing_m'] <= 0
            or metadata['start_s'] != metadata['forcing_hour_offset'] * 3600
            or metadata['end_s'] != metadata['start_s'] + 3600):
        raise ValueError('v10 hourly time alignment invalid')
    count = _m4_basin_storage_v10_io_math.ceil(3600 / metadata['parameters']['substep_s'])
    if metadata['substeps'] != count or metadata['substep_s'] != 3600 / count:
        raise ValueError('v10 derived step count mismatch')
    if not 1 <= metadata['cells'] <= 250000 or count * metadata['faces'] > 6000000000:
        raise ValueError('v10 chunk work budget exceeded')
    if any(not _m4_basin_storage_v10_io_np.isfinite(value).all() for value in arrays.values()):
        raise ValueError('v10 nonfinite arrays')
    return arrays, metadata

# --- terrain_pipeline/td_basin_storage_v10_io.py:53 ---
def validate_storage(result):
    arrays, metadata = _metadata(result)
    if metadata.get('schema') != 'td-v10-hour-page-v1' or set(arrays) != set(STATES + LEDGERS + FLUX + STATIC + ('rain_mm_h',)):
        raise ValueError('v10 page schema/arrays mismatch')
    cells, faces = metadata['cells'], metadata['faces']
    height = arrays['height_m']
    if height.ndim != 2 or height.size != cells or height.dtype != _m4_basin_storage_v10_io_np.float64 or arrays['valid_mask'].shape != height.shape or arrays['valid_mask'].dtype != bool:
        raise ValueError('v10 grid/mask mismatch')
    valid = arrays['valid_mask'].ravel()
    links = arrays['face_cells']
    if links.shape != (faces, 2) or links.dtype != _m4_basin_storage_v10_io_np.int64 or _m4_basin_storage_v10_io_np.any((links < 0) | (links >= cells)):
        raise ValueError('v10 face indices invalid')
    rows, columns = _m4_basin_storage_v10_io_np.divmod(links, height.shape[1])
    if _m4_basin_storage_v10_io_np.any(abs(rows[:, 0]-rows[:, 1])+abs(columns[:, 0]-columns[:, 1]) != 1) or not valid[links].all():
        raise ValueError('v10 faces must be valid D4')
    boundary = arrays['boundary_cells']
    widths = arrays['boundary_width_m']
    if boundary.dtype != _m4_basin_storage_v10_io_np.int64 or boundary.ndim != 1 or _m4_basin_storage_v10_io_np.any((boundary < 0) | (boundary >= cells)) or widths.shape != boundary.shape or _m4_basin_storage_v10_io_np.any(widths <= 0):
        raise ValueError('v10 boundary invalid')
    degree = _m4_basin_storage_v10_io_np.bincount(links.ravel(), minlength=cells).astype(float)
    _m4_basin_storage_v10_io_np.add.at(degree, boundary, widths/metadata['spacing_m'])
    cfl = float(degree.max(initial=0)) * .6 * metadata['substep_s'] / metadata['spacing_m']
    if cfl > 1 or cfl != metadata['positivity_cfl']:
        raise ValueError('v10 actual geometry CFL mismatch')
    for key in STATES:
        if arrays[key].shape != (2, cells) or _m4_basin_storage_v10_io_np.any(arrays[key] < 0) or _m4_basin_storage_v10_io_np.any(arrays[key][:, ~valid] != 0):
            raise ValueError('v10 state positivity/unknown invalid')
    for key in LEDGERS + ('rain_mm_h',):
        if arrays[key].shape != (1, cells) or _m4_basin_storage_v10_io_np.any(arrays[key][:, ~valid] != 0):
            raise ValueError('v10 ledger/rain shape/unknown invalid')
        if key not in ('internal_net_m3', 'storage_change_m3', 'balance_residual_m3') and _m4_basin_storage_v10_io_np.any(arrays[key] < 0):
            raise ValueError('v10 negative gross ledger')
    for key in FLUX:
        size = faces if key.startswith(('face_', 'active_')) else cells
        if arrays[key].shape != (size,) or _m4_basin_storage_v10_io_np.any(arrays[key] < 0):
            raise ValueError('v10 flux shape/positivity invalid')
        if ('duration' in key or key.startswith('active_')) and _m4_basin_storage_v10_io_np.any(arrays[key] > 3600 + 1e-8):
            raise ValueError('v10 activity exceeds page time')
    if arrays['receiver'].shape != (cells,) or arrays['receiver'].dtype != _m4_basin_storage_v10_io_np.int64 or _m4_basin_storage_v10_io_np.any((arrays['receiver'] < -1) | (arrays['receiver'] >= cells)):
        raise ValueError('v10 receiver invalid')
    rain = arrays['rain_volume_m3']
    if not _m4_basin_storage_v10_io_np.allclose(rain, arrays['rain_infiltration_m3'] + arrays['rain_excess_m3'], rtol=1e-12, atol=1e-9):
        raise ValueError('v10 unique rain allocation failed')
    if _m4_basin_storage_v10_io_np.any(arrays['rain_infiltration_m3'] + arrays['surface_infiltration_m3'] > arrays['infiltration_capacity_m3'] + 1e-8):
        raise ValueError('v10 infiltration capacity violated')
    signed = arrays['face_forward_m3'] - arrays['face_reverse_m3']
    net = _m4_basin_storage_v10_io_np.bincount(links[:, 1], weights=signed, minlength=cells) - _m4_basin_storage_v10_io_np.bincount(links[:, 0], weights=signed, minlength=cells)
    if not _m4_basin_storage_v10_io_np.allclose(net, arrays['internal_net_m3'][0], rtol=1e-10, atol=1e-7):
        raise ValueError('v10 face divergence ledger mismatch')
    area = metadata['spacing_m']**2
    before = area*(arrays['depth_m'][0] + sum(arrays[key][0] for key in STATES[1:])/1000)
    after = area*(arrays['depth_m'][1] + sum(arrays[key][1] for key in STATES[1:])/1000)
    change = after-before
    residual = rain[0]+net-arrays['soil_et_m3'][0]-arrays['surface_et_m3'][0]-arrays['boundary_outflow_m3'][0]-change
    tolerance = 1e-6+1e-10*(abs(before)+abs(after)+rain[0])
    if _m4_basin_storage_v10_io_np.any(abs(residual)>tolerance) or abs(float(residual.sum())) > 1e-6+1e-10*float(abs(change).sum()+rain.sum()):
        raise ValueError('v10 water ledger failed')
    if not _m4_basin_storage_v10_io_np.allclose(change, arrays['storage_change_m3'][0], rtol=0, atol=1e-9) or not _m4_basin_storage_v10_io_np.allclose(residual, arrays['balance_residual_m3'][0], rtol=0, atol=1e-7):
        raise ValueError('v10 saved balance mismatch')
    return True

# --- terrain_pipeline/td_basin_storage_v10_io.py:115 ---
def storagev10_validate_checkpoint(result):
    arrays, metadata = _metadata(result)
    required = STATES + ERRORS + tuple('cumulative_'+key for key in FLUX)
    if metadata.get('schema') != 'td-v10-hour-checkpoint-v1' or set(arrays) != set(required):
        raise ValueError('v10 checkpoint arrays/schema mismatch')
    for key in STATES + ERRORS:
        if arrays[key].shape != (metadata['cells'],):
            raise ValueError('v10 checkpoint state shape mismatch')
        if key in STATES and _m4_basin_storage_v10_io_np.any(arrays[key] < 0):
            raise ValueError('v10 checkpoint negative state')
    if _m4_basin_storage_v10_io_np.any(arrays['soil_mm'] > 150):
        raise ValueError('v10 checkpoint soil capacity exceeded')
    for key in FLUX:
        values = arrays['cumulative_'+key]
        size = metadata['faces'] if key.startswith(('face_', 'active_')) else metadata['cells']
        if values.shape != (size,) or _m4_basin_storage_v10_io_np.any(values < 0):
            raise ValueError('v10 checkpoint evidence invalid')
        if ('duration' in key or key.startswith('active_')) and _m4_basin_storage_v10_io_np.any(values > metadata['end_s']+1e-8):
            raise ValueError('v10 cumulative duration invalid')
    if _m4_basin_storage_v10_io_re.fullmatch('[0-9a-f]{64}', metadata.get('last_page_identity', '')) is None:
        raise ValueError('v10 checkpoint last-page identity invalid')
    return True

# --- terrain_pipeline/td_basin_storage_v10_io.py:139 ---
def _headers(headers):
    if 'manifest' not in headers or len(headers) > 64:
        raise ValueError('v10 archive headers invalid')
    for key, (shape, dtype) in headers.items():
        if key == 'manifest':
            if dtype != _m4_basin_storage_v10_io_np.uint8 or len(shape) != 1 or _m4_basin_storage_v10_io_math.prod(shape) > 1048576:
                raise ValueError('v10 manifest allocation invalid')
        elif dtype not in (_m4_basin_storage_v10_io_np.dtype('float64'), _m4_basin_storage_v10_io_np.dtype('int64'), _m4_basin_storage_v10_io_np.dtype('bool')) or _m4_basin_storage_v10_io_math.prod(shape) > 1000000:
            raise ValueError('v10 array allocation/type invalid')

# --- terrain_pipeline/td_basin_storage_v10_io.py:150 ---
def storagev10_save_storage(path, result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_storage_v10_io_save_bundle
    _m4_basin_storage_v10_io_save_bundle(path, result, validator=validate_storage)

# --- terrain_pipeline/td_basin_storage_v10_io.py:154 ---
def save_checkpoint(path, result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_storage_v10_io_save_bundle
    _m4_basin_storage_v10_io_save_bundle(path, result, validator=storagev10_validate_checkpoint)

# --- terrain_pipeline/td_basin_storage_v10_io.py:158 ---
def _load(path, expected_sha256, expected_identity, validator):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_storage_v10_io_load_bundle
    result = _m4_basin_storage_v10_io_load_bundle(path, expected_sha256=expected_sha256, validator=validator,
                         max_bytes=128*1024*1024, header_validator=_headers)
    if result['identity_sha256'] != expected_identity:
        raise ValueError('v10 external identity mismatch')
    return result

# --- terrain_pipeline/td_basin_storage_v10_io.py:166 ---
def storagev10_load_storage(path, *, expected_sha256, expected_identity):
    return _load(path, expected_sha256, expected_identity, validate_storage)

# --- terrain_pipeline/td_basin_storage_v10_io.py:170 ---
def storagev10_load_checkpoint(path, *, expected_sha256, expected_identity):
    return _load(path, expected_sha256, expected_identity, storagev10_validate_checkpoint)

# --- terrain_pipeline/td_basin_storage_checkpoint_io.py:8 ---
def checkpoint_validate_checkpoint(result):
    from terrain_pipeline.common_infra import identity as _m4_basin_storage_checkpoint_io_identity
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("schema") != "td-storage-continuation-v1" or metadata.get("execution_profile") != "v8-hour-pages-v7-SSPRK2" or result["identity_sha256"] != _m4_basin_storage_checkpoint_io_identity(arrays, metadata):
        raise ValueError("checkpoint identity/profile mismatch")
    cells, faces = metadata["cells"], metadata["faces"]
    if type(metadata.get("substeps")) is not int or type(metadata.get("work_face_steps")) is not int or metadata["substeps"]<1 or metadata["work_face_steps"]<0:
        raise ValueError("checkpoint integer count required")
    if not isinstance(metadata.get("forcing_identity"),str) or _m4_basin_storage_checkpoint_io_re.fullmatch("[0-9a-f]{64}",metadata["forcing_identity"]) is None:
        raise ValueError("checkpoint forcing identity invalid")
    if not _m4_basin_storage_checkpoint_io_np.isfinite([metadata["substep_s"],metadata["dt_s"],metadata["elapsed_s"]]).all() or metadata["substep_s"] <= 0 or metadata["dt_s"] <= 0 or metadata["substeps"] * metadata["substep_s"] != metadata["elapsed_s"] or metadata["elapsed_s"] % metadata["dt_s"] != 0:
        raise ValueError("checkpoint time/count mismatch")
    states = {"depth_m", "soil_mm", "fast_mm", "slow_mm", "error_depth", "error_soil", "error_fast", "error_slow"}
    cumulative = {"cumulative_" + key for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s", "routed_volume_m3", "wet_duration_s")}
    if set(arrays) != states | cumulative or type(cells) is not int or not 1 <= cells <= 1_000_000 or type(faces) is not int or not 0 <= faces <= 2*cells:
        raise ValueError("checkpoint arrays/budget invalid")
    for key, values in arrays.items():
        expected = faces if key.startswith("cumulative_") and key not in ("cumulative_routed_volume_m3", "cumulative_wet_duration_s") else cells
        if values.shape != (expected,) or values.dtype != _m4_basin_storage_checkpoint_io_np.float64 or not _m4_basin_storage_checkpoint_io_np.isfinite(values).all():
            raise ValueError("checkpoint shape/nonfinite state")
        if not key.startswith("error_") and _m4_basin_storage_checkpoint_io_np.any(values < 0):
            raise ValueError("checkpoint negative state")
    if not _m4_basin_storage_checkpoint_io_np.isfinite(metadata["elapsed_s"]) or metadata["elapsed_s"] <= 0 or metadata["substeps"] < 1 or metadata["work_face_steps"] != metadata["substeps"] * faces:
        raise ValueError("checkpoint elapsed/work mismatch")
    if _m4_basin_storage_checkpoint_io_np.any(arrays["cumulative_active_forward_s"] + arrays["cumulative_active_reverse_s"] > metadata["elapsed_s"] + 1e-8):
        raise ValueError("checkpoint duplicated activity")
    if metadata["hydraulic_ready"] is not False or metadata["transient_converged"] is not False:
        raise ValueError("checkpoint certification forbidden")
    return True

# --- terrain_pipeline/td_basin_storage_checkpoint_io.py:38 ---
def checkpointio_save_checkpoint(path, result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_storage_checkpoint_io_save_bundle
    _m4_basin_storage_checkpoint_io_save_bundle(path, result, validator=checkpoint_validate_checkpoint)

# --- terrain_pipeline/td_basin_storage_checkpoint_io.py:42 ---
def checkpoint_load_checkpoint(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_storage_checkpoint_io_load_bundle
    result = _m4_basin_storage_checkpoint_io_load_bundle(path, expected_sha256=expected_sha256, validator=checkpoint_validate_checkpoint, max_bytes=128*1024*1024,header_validator=checkpoint_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external checkpoint identity mismatch")
    return result

# --- terrain_pipeline/td_basin_storage_checkpoint_io.py:49 ---
def checkpoint_headers(headers):
    shape,dtype=headers.get("depth_m",((),_m4_basin_storage_checkpoint_io_np.dtype("O")))
    if len(shape)!=1 or not 1<=shape[0]<=250000 or dtype!=_m4_basin_storage_checkpoint_io_np.float64:
        raise ValueError("checkpoint allocation rejection")
    for key in ("soil_mm","fast_mm","slow_mm","error_depth","error_soil","error_fast","error_slow","cumulative_routed_volume_m3","cumulative_wet_duration_s"):
        if headers.get(key)!=(shape,_m4_basin_storage_checkpoint_io_np.dtype("float64")):
            raise ValueError("checkpoint state header mismatch")
    faces,face_dtype=headers.get("cumulative_face_forward_m3",((),_m4_basin_storage_checkpoint_io_np.dtype("O")))
    if len(faces)!=1 or faces[0]>2*shape[0] or face_dtype!=_m4_basin_storage_checkpoint_io_np.float64:
        raise ValueError("checkpoint face allocation rejection")
    for key in ("cumulative_face_reverse_m3","cumulative_active_forward_s","cumulative_active_reverse_s"):
        if headers.get(key)!=(faces,_m4_basin_storage_checkpoint_io_np.dtype("float64")):
            raise ValueError("checkpoint directional header mismatch")

# --- terrain_pipeline/td_basin_source.py:10 ---
PRIMARY_PATH = _m4_basin_source_Path(__file__).resolve().parents[1] / "verification/mountain-real-td/mountain-run-20261001T080705728662Z/primary-source.npz"

# --- terrain_pipeline/td_basin_source.py:11 ---
PRIMARY_SHA256 = "6e7fdf63dc02e9f14e7d83550d0c5f806b42aa7f13367ea96012787bcf069382"

# --- terrain_pipeline/td_basin_source.py:12 ---
MAX_CELLS = 250_000

# --- terrain_pipeline/td_basin_source.py:15 ---
def make_td_source(height_m, *, spacing_m, origin_m_xz=(0, 0), valid_mask=None,
                   protected_mask=None, open_boundary_mask=None, source_sha256=None):
    from terrain_pipeline.common_infra import identity as _m4_basin_source_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_source_readonly
    height = _m4_basin_source_np.asarray(height_m)
    if height.ndim != 2 or height.dtype.kind not in "fiu" or not 1 <= height.size <= MAX_CELLS:
        raise ValueError("bounded numeric [z,x] height required")
    if type(spacing_m) not in (float, int) or not _m4_basin_source_math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("positive finite metre spacing required")
    if len(origin_m_xz) != 2 or not all(type(value) in (float, int) and _m4_basin_source_math.isfinite(value) for value in origin_m_xz):
        raise ValueError("finite origin x,z required")
    valid = _m4_basin_source_np.ones(height.shape, bool) if valid_mask is None else _m4_basin_source_np.asarray(valid_mask)
    protected = _m4_basin_source_np.zeros(height.shape, bool) if protected_mask is None else _m4_basin_source_np.asarray(protected_mask)
    opened = _m4_basin_source_np.zeros(height.shape, bool) if open_boundary_mask is None else _m4_basin_source_np.asarray(open_boundary_mask)
    for mask in (valid, protected, opened):
        if mask.shape != height.shape or mask.dtype != bool:
            raise ValueError("boolean mask shape mismatch")
    if not valid.any() or not _m4_basin_source_np.isfinite(height).all():
        raise ValueError("finite bed and nonempty coverage required")
    perimeter = _m4_basin_source_np.zeros(height.shape, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    if (opened & (~valid | ~perimeter)).any() or (protected & ~valid).any():
        raise ValueError("open boundary must be valid perimeter; protection must be known")
    if source_sha256 is not None and (not isinstance(source_sha256, str) or len(source_sha256) != 64 or
                                     any(character not in "0123456789abcdef" for character in source_sha256)):
        raise ValueError("invalid external source SHA256")
    arrays = {"height_m": _m4_basin_source_readonly(height.astype(_m4_basin_source_np.float64)), "valid_mask": _m4_basin_source_readonly(valid),
              "protected_mask": _m4_basin_source_readonly(protected), "open_boundary_mask": _m4_basin_source_readonly(opened)}
    metadata = {"schema": "td-basin-source-v1", "spacing_m": float(spacing_m),
                "origin_m_xz": list(origin_m_xz), "source_sha256": source_sha256,
                "coordinates": "x east, z south; arrays [z,x]; cell_id=z*nx+x",
                "boundary": "explicit_engineering_open_faces_else_closed", "natural_outlet_verified": False}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_basin_source_identity(arrays, metadata)}

# --- terrain_pipeline/td_basin_source.py:49 ---
def load_td_source(path=None):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_source_load_bundle
    from terrain_pipeline.common_infra import validate_source as _m4_basin_source_validate_source
    original = _m4_basin_source_load_bundle(PRIMARY_PATH if path is None else path, expected_sha256=PRIMARY_SHA256,
                           validator=_m4_basin_source_validate_source)
    arrays, metadata = original["arrays"], original["metadata"]
    if metadata["boundary"]["policy"] != "all_edges_open":
        raise ValueError("pinned primary boundary mismatch")
    opened = _m4_basin_source_np.zeros(arrays["height_m"].shape, bool)
    opened[[0, -1], :] = True
    opened[:, [0, -1]] = True
    opened &= arrays["hydrology_mask"]
    return make_td_source(arrays["height_m"], spacing_m=metadata["spacing_m"],
                          origin_m_xz=metadata["origin_m_xz"], valid_mask=arrays["hydrology_mask"],
                          open_boundary_mask=opened, source_sha256=PRIMARY_SHA256)

# --- terrain_pipeline/td_basin_source.py:64 ---
def validate_td_source(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if set(arrays) != {"height_m", "valid_mask", "protected_mask", "open_boundary_mask"}:
        raise ValueError("unexpected source arrays")
    rebuilt = make_td_source(arrays["height_m"], spacing_m=metadata["spacing_m"],
                             origin_m_xz=metadata["origin_m_xz"], valid_mask=arrays["valid_mask"],
                             protected_mask=arrays["protected_mask"], open_boundary_mask=arrays["open_boundary_mask"],
                             source_sha256=metadata["source_sha256"])
    if metadata != rebuilt["metadata"] or result["identity_sha256"] != rebuilt["identity_sha256"]:
        raise ValueError("source identity/schema mismatch")
    return True

# --- terrain_pipeline/td_basin_source.py:77 ---
def save_td_source(path, result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_source_save_bundle
    _m4_basin_source_save_bundle(path, result, validator=validate_td_source)

# --- terrain_pipeline/td_basin_source.py:81 ---
def load_td_source_bundle(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_source_load_bundle
    result = _m4_basin_source_load_bundle(path, expected_sha256=expected_sha256, validator=validate_td_source)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external source identity mismatch")
    return result

# --- terrain_pipeline/td_basin_review.py:22 ---
BASIN_REVIEW_SCHEMA = "td-basin-review-v1"

# --- terrain_pipeline/td_basin_review.py:23 ---
BASIN_REVIEW_ALGORITHM = "td-pinned-native-data-continuous-terrain-native-water-lod-v3"

# --- terrain_pipeline/td_basin_review.py:24 ---
LOADERS = {"source": load_td_source_bundle, "hierarchy": _m4_basin_review_load_basin_hierarchy,
           "storage": dispatch_load_storage, "material": _m4_basin_review_load_material_field,
           "morphology": _m4_basin_review_load_morphology, "breach": _m4_basin_review_load_saddle_breach}

# --- terrain_pipeline/td_basin_review.py:27 ---
MAX_REVIEW_BYTES = 256 * 1024 ** 2

# --- terrain_pipeline/td_basin_review.py:30 ---
def load_review_inputs(records):
    if not isinstance(records, dict) or not {"source", "hierarchy", "material"} <= set(records) or set(records) - set(LOADERS):
        raise ValueError("review needs pinned source/hierarchy/material and known optional roles")
    inputs = {}
    for role, record in records.items():
        if not isinstance(record, dict) or set(record) != {"path", "expected_sha256", "expected_identity"}:
            raise ValueError("each review input requires path and both external pins")
        for key in ("expected_sha256", "expected_identity"):
            value = record[key]
            if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError("invalid review external pin")
        inputs[role] = LOADERS[role](record["path"], expected_sha256=record["expected_sha256"], expected_identity=record["expected_identity"])
    _validate_links(inputs)
    return inputs

# --- terrain_pipeline/td_basin_review.py:46 ---
def _validate_links(inputs):
    source = inputs["source"]
    hierarchy = inputs["hierarchy"]
    height = source["arrays"]["height_m"]
    shape = height.shape
    source_metadata = source["metadata"]
    if hierarchy["metadata"]["source_identity_sha256"] != source["identity_sha256"]:
        raise ValueError("review source/hierarchy identity chain mismatch")
    for role, bundle in inputs.items():
        metadata = bundle["metadata"]
        if metadata["spacing_m"] != source_metadata["spacing_m"] or metadata["origin_m_xz"] != source_metadata["origin_m_xz"]:
            raise ValueError("review coordinate mismatch: " + role)
        arrays = bundle["arrays"]
        if role == "material":
            if arrays["erodibility"].shape != shape or not _m4_basin_review_np.array_equal(arrays["protected_mask"], source["arrays"]["protected_mask"]):
                raise ValueError("review material coverage/protection mismatch")
        else:
            bed = arrays["original_height_m"] if role in ("morphology", "breach") else arrays["height_m"]
            if not _m4_basin_review_np.array_equal(bed, height, equal_nan=True) or not _m4_basin_review_np.array_equal(arrays["valid_mask"], source["arrays"]["valid_mask"]):
                raise ValueError("review original bed/coverage mismatch: " + role)
    if "storage" in inputs:
        storage = inputs["storage"]
        if storage["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or not _m4_basin_review_np.array_equal(storage["arrays"]["face_cells"], hierarchy["arrays"]["face_cells"]):
            raise ValueError("review hydro/topology identity chain mismatch")
    if "morphology" in inputs and inputs["morphology"]["metadata"]["material_identity_sha256"] != inputs["material"]["identity_sha256"]:
        raise ValueError("review morphology material identity mismatch")
    if "breach" in inputs:
        metadata = inputs["breach"]["metadata"]
        if metadata["source_identity_sha256"] != source["identity_sha256"] or metadata["topology_identity_sha256"] != hierarchy["identity_sha256"] or metadata["material_identity_sha256"] != inputs["material"]["identity_sha256"]:
            raise ValueError("review breach source/topology/material chain mismatch")
        if "storage" not in inputs or metadata["hydro_identity_sha256"] != inputs["storage"]["identity_sha256"]:
            raise ValueError("review breach requires pinned matching hydro package")

# --- terrain_pipeline/td_basin_review.py:80 ---
def review_plain(value):
    if isinstance(value, _m4_basin_review_np.ndarray):
        return review_plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): review_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [review_plain(item) for item in value]
    if isinstance(value, (_m4_basin_review_np.integer, _m4_basin_review_np.bool_)):
        return value.item()
    if isinstance(value, (float, _m4_basin_review_np.floating)):
        return float(value) if _m4_basin_review_np.isfinite(value) else None
    return value

# --- terrain_pipeline/td_basin_review.py:94 ---
def make_basin_review(inputs):
    """Adapt complete frozen arrays only; never interpolate a hydraulic state."""
    _validate_links(inputs)
    source = inputs["source"]
    topology = inputs["hierarchy"]["arrays"]
    height = source["arrays"]["height_m"]
    material = inputs["material"]["arrays"]
    fields = {"H0_m": height, "valid_mask": source["arrays"]["valid_mask"],
              "protected_mask": source["arrays"]["protected_mask"], "basin_owner": topology["cell_owner"],
              "contribution_owner": topology["contribution_owner"],
              "erodibility": material["erodibility"], "erodible_thickness_m": material["erodible_thickness_m"],
              "weak_path_preference": material["weak_path_preference"]}
    candidates = {"baseline": {"height_m": height, "height_delta_m": _m4_basin_review_np.zeros(height.shape),
                               "flags": {"status": "baseline", "hydrology_coupled_verified": False,
                                         "transient_converged": False, "morphology_flux_ready": False}}}
    for role in ("morphology", "breach"):
        if role in inputs:
            bundle = inputs[role]
            candidates[role] = {"height_m": bundle["arrays"]["height_m"],
                                "height_delta_m": bundle["arrays"]["height_delta_m"],
                                "flags": bundle["metadata"],
                                "material_ledger": bundle["metadata"]["ledger"],
                                "stored_solid_m3": bundle["arrays"]["stored_solid_m3"]}
            if role == "breach":
                candidates[role]["path_cell_ids"] = bundle["arrays"]["path_cell_ids"]
    water = None
    if "storage" in inputs:
        storage = inputs["storage"]
        depth = storage["arrays"]["depth_m"]
        if depth.ndim == 2:
            depth = depth.reshape((-1,) + height.shape)
        threshold = storage["metadata"]["parameters"]["wet_threshold_m"]
        water = {"time_s": _m4_basin_review_np.arange(depth.shape[0]) * storage["metadata"]["dt_s"],
                 "cell_stores_mm": {name: storage["arrays"][name].reshape((-1,) + height.shape) for name in ("soil_mm", "fast_mm", "slow_mm")},
                 "depth_m": depth, "surface_formula": "H0_m + depth_m where valid and depth > wet_threshold_m; otherwise no water surface",
                 "bed_identity_sha256": source["identity_sha256"], "hydro_identity_sha256": storage["identity_sha256"],
                 "semantics": "solved cell water on original storage bed; never coupled to unverified candidate",
                 "ledger": {name: _m4_basin_review_np.sum(values, axis=1) for name, values in storage["arrays"].items() if name.endswith("_m3") and values.ndim == 2 and values.shape[1] == height.size},
                 "flags": {**storage["metadata"], "transient_converged": storage["metadata"].get("transient_converged", False),
                           "morphology_flux_ready": storage["metadata"].get("morphology_flux_ready", False)}}
    stride = max(1, int(_m4_basin_review_np.ceil(max(height.shape) / 64)))
    displayed = int(_m4_basin_review_np.count_nonzero(source["arrays"]["valid_mask"][::stride, ::stride]))
    displayed_mask = _m4_basin_review_np.zeros(height.shape, bool)
    displayed_mask[::stride, ::stride] = True
    omitted = source["arrays"]["valid_mask"] & ~displayed_mask
    omitted_ids = _m4_basin_review_np.flatnonzero(omitted.ravel())
    review = {"schema": BASIN_REVIEW_SCHEMA, "algorithm": BASIN_REVIEW_ALGORITHM, "shape": list(height.shape), "spacing_m": source["metadata"]["spacing_m"],
              "origin_m_xz": source["metadata"]["origin_m_xz"], "coordinates": "X east; Z south; [z,x]; cell_id=z*nx+x; metres",
              "inputs": {role: bundle["identity_sha256"] for role, bundle in inputs.items()},
              "fields": fields, "candidates": candidates,
              "topology": {name: topology[name] for name in ("node_parent", "node_birth_m", "node_upper_m", "node_unknown_contact", "face_cells", "face_level_m", "face_merge_node")},
              "water": water, "sampling": {"stride": 1, "omitted_cells": 0, "omitted_water_volume_m3": 0},
              "render_lod": {"stride": stride, "displayed_points": displayed,
                             "terrain_interpolation": True, "water_interpolation": False,
                             "omitted_points": int(_m4_basin_review_np.count_nonzero(omitted)),
                             "omitted_cell_ids": omitted_ids,
                             "omitted_footprint_area_m2": int(_m4_basin_review_np.count_nonzero(omitted)) * source["metadata"]["spacing_m"] ** 2,
                             "footprint_policy": "terrain triangles interpolate sampled native centre heights for display only; water covers only sampled native footprints; no wetness interpolation",
                             "omitted_water_volume_m3_by_frame": None if water is None else _m4_basin_review_np.sum(depth[:, omitted], axis=1) * source["metadata"]["spacing_m"] ** 2},
              "flags": {"readonly": True, "hydraulic_ready": False, "natural_outlet_verified": False,
                        "transient_converged": False, "morphology_flux_ready": False,
                        "water_available": water is not None, "water_on_candidate_verified": False},
              "limitations": "Finite generative prototype. Solved water belongs to baseline bed; derived geometry needs topology rebuild and separate coupled validation. 3D cell surfaces do not certify hydraulic connectivity."}
    return review_plain(review)

# --- terrain_pipeline/td_basin_review.py:160 ---
HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TD 盆地只读审查</title>
<style>body{font:14px system-ui;margin:16px;background:#142126;color:#dfebe9}select,input,button{margin:5px}canvas{display:block;width:100%;height:65vh;background:#0a151a}pre{white-space:pre-wrap;max-height:30vh;overflow:auto}.note{color:#f0c985}</style>
<h2>TD 盆地只读审查</h2><p class="note">生成启发原型；瞬态未认证，形态通量未就绪。地形连续LOD三角面是高度插值，仅供展示；水保持原生采样格片，不插值。水面只对应冻结求解状态。未解析米级河槽，不认证水力连通；水遗漏footprint和体积见详情。</p>
<label>候选<select id="candidate"></select></label><label>图层<select id="layer"><option value="bed">床面</option><option value="H0_m">原床</option><option value="delta">切填差</option><option value="erodibility">抗蚀倒数</option><option value="erodible_thickness_m">材料厚度</option><option value="weak_path_preference">弱路径偏好</option><option value="basin_owner">盆地归属</option></select></label>
<label>视图<select id="view"><option>2D</option><option>3D</option></select></label><label><input id="water" type="checkbox" checked>求解水面</label><label><input id="saddle" type="checkbox">跨归属鞍部面</label>
<label>水深展示阈值(m)<input id="waterThreshold" type="number" min="0" step="0.01" value="0.05"></label>
<label>时间<input id="time" type="range" min="0" max="0" value="0"><span id="stamp"></span></label><button id="play">播放</button><button id="fit">重置视角</button><span>拖动旋转 · 滚轮缩放 · 点击采样格读取</span><canvas id="canvas"></canvas><pre id="details"></pre>
<script>const data=__DATA__;const canvas=document.getElementById('canvas'),context=canvas.getContext('2d');const candidate=document.getElementById('candidate'),layer=document.getElementById('layer'),view=document.getElementById('view'),time=document.getElementById('time');let yaw=-.6,pitch=.7,last=null,zoom=1,playing=null,moved=false,pick=null,screenCells=[];
for(const name of Object.keys(data.candidates)){const option=document.createElement('option');option.value=name;option.textContent=name;candidate.append(option)}time.max=data.water?data.water.time_s.length-1:0;
view.value='3D';zoom=1.2;
function range(values){let low=Infinity,high=-Infinity;for(const row of values)for(const value of row)if(value!==null){low=Math.min(low,value);high=Math.max(high,value)}return[low,high]}
function draw(){canvas.width=canvas.clientWidth*devicePixelRatio;canvas.height=canvas.clientHeight*devicePixelRatio;context.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);const width=canvas.clientWidth,height=canvas.clientHeight,rows=data.shape[0],cols=data.shape[1],chosen=data.candidates[candidate.value];let values=layer.value==='bed'?chosen.height_m:layer.value==='delta'?chosen.height_delta_m:data.fields[layer.value];const[low,high]=range(values),[bedLow,bedHigh]=range(chosen.height_m);const scale=Math.min(width/(cols+rows*.35),height/(rows+cols*.25))*.8*zoom;context.clearRect(0,0,width,height);screenCells=[];
function project(col,row,elevation){if(view.value==='2D')return[width/2+(col-cols/2)*scale,height/2+(row-rows/2)*scale];const centerX=col-cols/2,centerZ=row-rows/2,rotX=centerX*Math.cos(yaw)-centerZ*Math.sin(yaw),rotZ=centerX*Math.sin(yaw)+centerZ*Math.cos(yaw),vertical=(elevation-bedLow)/data.spacing_m;return[width/2+rotX*scale,height*.7+(rotZ*Math.sin(pitch)-vertical*Math.cos(pitch))*scale]}
function quad(col,row,elevation,fill){const extent=1/data.render_lod.stride,points=[[col,row],[col+extent,row],[col+extent,row+extent],[col,row+extent]].map(point=>project(point[0],point[1],elevation));context.beginPath();points.forEach((point,index)=>index?context.lineTo(...point):context.moveTo(...point));context.closePath();context.fillStyle=fill;context.fill()}
function terrain(col,row,fill){if(row+1>=rows||col+1>=cols){quad(col,row,chosen.height_m[row][col],fill);return}const corners=[[row,col],[row,col+1],[row+1,col+1],[row+1,col]];if(corners.some(([cornerRow,cornerCol])=>!data.fields.valid_mask[cornerRow][cornerCol]))return;const points=corners.map(([cornerRow,cornerCol])=>project(cornerCol+.5/data.render_lod.stride,cornerRow+.5/data.render_lod.stride,chosen.height_m[cornerRow][cornerCol]));const slopeX=(chosen.height_m[row][col+1]-chosen.height_m[row][col])/data.spacing_m,slopeZ=(chosen.height_m[row+1][col]-chosen.height_m[row][col])/data.spacing_m;const shade=Math.max(.45,Math.min(1.15,.85+(-slopeX*.4+slopeZ*.3)/Math.sqrt(1+slopeX*slopeX+slopeZ*slopeZ)));for(const triangle of [[0,1,2],[0,2,3]]){context.beginPath();triangle.forEach((index,position)=>position?context.lineTo(...points[index]):context.moveTo(...points[index]));context.closePath();context.fillStyle=fill;context.fill();if(layer.value==='bed'||layer.value==='H0_m'){context.fillStyle=shade<1?`rgba(0,0,0,${1-shade})`:`rgba(255,255,255,${shade-1})`;context.fill()}}}
const cells=[];for(let row=0;row<rows;row++)for(let col=0;col<cols;col++)if(data.fields.valid_mask[row][col])cells.push([row,col]);if(view.value==='3D')cells.sort((first,second)=>((first[1]-second[1])*Math.sin(yaw)+(first[0]-second[0])*Math.cos(yaw)));
const frame=Number(time.value),showWater=data.water&&candidate.value==='baseline'&&document.getElementById('water').checked;
for(const[row,col]of cells){const value=values[row][col],fraction=(value-low)/(high-low||1);let fill=`rgb(${Math.round(35+150*fraction)},${Math.round(75+110*fraction)},${Math.round(70+80*fraction)})`;if(layer.value==='delta')fill=value<0?'#d99b60':value>0?'#88cbb4':'#32464c';if(data.fields.protected_mask[row][col])fill='#e784ad';terrain(col,row,fill);screenCells.push({row,col,point:project(col+.5/data.render_lod.stride,row+.5/data.render_lod.stride,chosen.height_m[row][col])})}
const displayThreshold=Math.max(0,Number(document.getElementById('waterThreshold').value)||0),sampleArea=(data.spacing_m/data.render_lod.stride)**2;let thresholdHiddenVolume=0;if(data.water)for(const[row,col]of cells){const depth=data.water.depth_m[frame][row][col];if(depth<=Math.max(displayThreshold,data.water.flags.parameters.wet_threshold_m))thresholdHiddenVolume+=depth*sampleArea;else if(showWater)quad(col,row,data.fields.H0_m[row][col]+depth,'#5aaee5aa')}data.display_omission={threshold_m:displayThreshold,threshold_hidden_sampled_water_m3:thresholdHiddenVolume,lod_omitted_water_m3:data.render_lod.omitted_water_volume_m3_by_frame?.[frame]||0,total_hidden_water_m3:thresholdHiddenVolume+(data.render_lod.omitted_water_volume_m3_by_frame?.[frame]||0),scope:'threshold acts only on rendered native samples; LOD omission separate; computational depth unchanged'};
if(pick){const pickedRow=pick.row/data.render_lod.stride,pickedCol=pick.col/data.render_lod.stride;pick.derived_m=chosen.height_m[pickedRow][pickedCol];pick.delta_m=chosen.height_delta_m[pickedRow][pickedCol];pick.erodible_thickness_m=data.fields.erodible_thickness_m[pickedRow][pickedCol];pick.weak_path_preference=data.fields.weak_path_preference[pickedRow][pickedCol];pick.water_depth_m=showWater?data.water?.depth_m[frame][pickedRow][pickedCol]:null;pick.water_scope=showWater?'matching baseline solved state':'no matching candidate solved state';pick.soil_mm=data.water?.cell_stores_mm.soil_mm[frame][pickedRow][pickedCol];pick.fast_mm=data.water?.cell_stores_mm.fast_mm[frame][pickedRow][pickedCol];pick.slow_mm=data.water?.cell_stores_mm.slow_mm[frame][pickedRow][pickedCol]}
data.render_lod.current_display_omission=data.display_omission;
if(document.getElementById('saddle').checked){context.strokeStyle='#ffd77e';context.lineWidth=1;for(const face of data.saddle_overlay){context.beginPath();context.moveTo(...project(face[0],face[1],face[4]));context.lineTo(...project(face[2],face[3],face[4]));context.stroke()}}
document.getElementById('stamp').textContent=data.water?`${data.water.time_s[frame]} s`:'无求解水帧';document.getElementById('details').textContent=JSON.stringify({global_flags:data.flags,water_flags:data.water?.flags,candidate_flags:chosen.flags,picked_cell:pick,material_ledger:chosen.material_ledger,inputs:data.inputs,raw_input_records:data.raw_input_records,sampling:data.sampling,render_lod:data.render_lod,water:showWater?'baseline solved cell surfaces':'hidden: no matching solved candidate state',limitations:data.limitations},null,2)}
for(const control of document.querySelectorAll('select,input'))control.addEventListener('input',draw);canvas.addEventListener('pointerdown',event=>{moved=false;last=[event.clientX,event.clientY];canvas.setPointerCapture(event.pointerId)});canvas.addEventListener('pointermove',event=>{if(last){const deltaX=event.clientX-last[0],deltaY=event.clientY-last[1];if(Math.abs(deltaX)+Math.abs(deltaY)>2)moved=true;yaw+=deltaX*.005;pitch=Math.max(.1,Math.min(1.5,pitch+deltaY*.005));last=[event.clientX,event.clientY];draw()}});canvas.addEventListener('pointerup',event=>{last=null;if(!moved){const rectangle=canvas.getBoundingClientRect(),point=[event.clientX-rectangle.left,event.clientY-rectangle.top];let nearest=null,distance=Infinity;for(const cell of screenCells){const squared=(cell.point[0]-point[0])**2+(cell.point[1]-point[1])**2;if(squared<distance){distance=squared;nearest=cell}}if(nearest&&distance<400){const {row,col}=nearest,frame=Number(time.value),nativeRow=row*data.render_lod.stride,nativeCol=col*data.render_lod.stride;pick={cell_id:nativeRow*data.native_shape[1]+nativeCol,row:nativeRow,col:nativeCol,H0_m:data.fields.H0_m[row][col],derived_m:data.candidates[candidate.value].height_m[row][col],delta_m:data.candidates[candidate.value].height_delta_m[row][col],erodibility:data.fields.erodibility[row][col],basin_owner:data.fields.basin_owner[row][col],water_depth_m:data.water?.depth_m[frame][row][col]}}draw()}});canvas.addEventListener('wheel',event=>{event.preventDefault();zoom=Math.max(.2,Math.min(10,zoom*Math.exp(-event.deltaY*.001)));draw()},{passive:false});document.getElementById('fit').onclick=()=>{yaw=-.6;pitch=.7;zoom=1;draw()};document.getElementById('play').onclick=()=>{if(playing){clearInterval(playing);playing=null;document.getElementById('play').textContent='播放'}else if(data.water){document.getElementById('play').textContent='暂停';playing=setInterval(()=>{time.value=(Number(time.value)+1)%(Number(time.max)+1);draw()},500)}};window.addEventListener('resize',draw);draw();</script></html>'''

# --- terrain_pipeline/td_basin_review.py:186 ---
def export_basin_review(records, output_dir):
    from terrain_pipeline.common_infra import file_sha256 as _m4_basin_review_file_sha256
    output = _m4_basin_review_Path(output_dir)
    if output.exists():
        raise FileExistsError(output)
    inputs = load_review_inputs(records)
    review = make_basin_review(inputs)
    review["raw_input_records"] = {role: {**record, "path": str(_m4_basin_review_Path(record["path"]).resolve())} for role, record in records.items()}
    payload = _m4_basin_review_json.dumps(review, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_REVIEW_BYTES:
        raise ValueError("review byte budget exceeded")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = _m4_basin_review_Path(_m4_basin_review_tempfile.mkdtemp(prefix=".td-review-stage-", dir=output.parent))
    try:
        (temporary / "review.json").write_text(payload, encoding="utf-8")
        browser_review = dict(review)
        browser_review["fields"] = {name: _m4_basin_review_np.asarray(values)[::review["render_lod"]["stride"], ::review["render_lod"]["stride"]].tolist() for name, values in review["fields"].items()}
        browser_review["candidates"] = {}
        for name, candidate in review["candidates"].items():
            browser_review["candidates"][name] = {key: value for key, value in candidate.items() if key not in ("height_m", "height_delta_m", "stored_solid_m3")}
            for key in ("height_m", "height_delta_m"):
                browser_review["candidates"][name][key] = _m4_basin_review_np.asarray(candidate[key])[::review["render_lod"]["stride"], ::review["render_lod"]["stride"]].tolist()
        if review["water"] is not None:
            browser_review["water"] = {key: value for key, value in review["water"].items() if key not in ("depth_m", "surface_m", "cell_stores_mm")}
            browser_review["water"]["cell_stores_mm"] = {name: _m4_basin_review_np.asarray(values)[:, ::review["render_lod"]["stride"], ::review["render_lod"]["stride"]].tolist() for name, values in review["water"]["cell_stores_mm"].items()}
            browser_review["water"]["depth_m"] = _m4_basin_review_np.asarray(review["water"]["depth_m"])[:, ::review["render_lod"]["stride"], ::review["render_lod"]["stride"]].tolist()
        browser_review["native_shape"] = review["shape"]
        browser_review["shape"] = list(_m4_basin_review_np.asarray(browser_review["fields"]["H0_m"]).shape)
        browser_review["spacing_m"] = review["spacing_m"] * review["render_lod"]["stride"]
        browser_review["topology"] = {"face_cells": [], "face_level_m": [], "face_merge_node": []}
        saddle_overlay = []
        native_cols = review["shape"][1]
        owners = _m4_basin_review_np.asarray(review["fields"]["basin_owner"]).ravel()
        stride = review["render_lod"]["stride"]
        for face, level in zip(review["topology"]["face_cells"], review["topology"]["face_level_m"]):
            first, second = face
            if owners[first] == owners[second]:
                continue
            row, col = divmod(first, native_cols)
            target_row, target_col = divmod(second, native_cols)
            endpoints = [col + 1, row, col + 1, row + 1] if row == target_row else [col, row + 1, col + 1, row + 1]
            saddle_overlay.append([coordinate / stride for coordinate in endpoints] + [level])
        browser_review["saddle_overlay"] = saddle_overlay
        browser_review["render_lod"] = {key: value for key, value in review["render_lod"].items() if key != "omitted_cell_ids"}
        safe_payload = _m4_basin_review_json.dumps(browser_review, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        (temporary / "review.html").write_text(HTML.replace("__DATA__", safe_payload), encoding="utf-8")
        manifest = {"schema": BASIN_REVIEW_SCHEMA, "algorithm": BASIN_REVIEW_ALGORITHM,
                    "input_algorithms": {role: bundle["metadata"].get("algorithm", bundle["metadata"].get("schema")) for role, bundle in inputs.items()},
                    "flags": review["flags"],
                    "inputs": {role: {**record, "path": str(_m4_basin_review_Path(record["path"]).resolve())} for role, record in records.items()},
                    "files": {name: _m4_basin_review_file_sha256(temporary / name) for name in ("review.json", "review.html")},
                    "review_identity_sha256": _m4_basin_review_hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                    "renderer": "offline canvas projected cell surfaces; no external dependencies", "source_unchanged": True}
        for record in records.values():
            if _m4_basin_review_file_sha256(record["path"]) != record["expected_sha256"]:
                raise ValueError("review input changed during export")
        (temporary / "manifest.json").write_text(_m4_basin_review_json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        _m4_basin_review_os.rename(temporary, output)
    finally:
        if temporary.exists():
            _m4_basin_review_shutil.rmtree(temporary)
    return manifest

# --- terrain_pipeline/td_basin_review.py:249 ---
def load_selection_proof(record, *, expected_candidate_records_sha256=None):
    """Load separately pinned evidence; never promote bundle flags from a scope claim."""
    from terrain_pipeline.common_infra import file_sha256 as _m4_basin_review_file_sha256
    if not isinstance(record, dict) or set(record) != {"path", "expected_sha256"}:
        raise ValueError("selection proof requires external path/SHA256")
    path = _m4_basin_review_Path(record["path"])
    if path.stat().st_size > 4 * 1024 ** 2 or _m4_basin_review_file_sha256(path) != record["expected_sha256"]:
        raise ValueError("selection proof hash/size mismatch")
    proof = _m4_basin_review_json.loads(path.read_text(encoding="utf-8"))
    if proof.get("schema") != "td-basin-selection-proof-v1" or not isinstance(proof.get("scopes"), list):
        raise ValueError("unsupported selection proof schema")
    if expected_candidate_records_sha256 is not None and proof.get("candidate_records_sha256") != expected_candidate_records_sha256:
        raise ValueError("selection proof refers to another candidate index")
    scope_ids = set()
    allowed = {"representative_basin", "full_domain_baseline", "candidate_full_domain", "candidate_selection"}
    for scope in proof["scopes"]:
        if not isinstance(scope, dict) or scope.get("scope") not in allowed or not isinstance(scope.get("scope_id"), str) or scope["scope_id"] in scope_ids:
            raise ValueError("invalid proof scope")
        scope_ids.add(scope["scope_id"])
        if type(scope.get("passed")) is not bool or not isinstance(scope.get("artifacts"), list) or not scope["artifacts"]:
            raise ValueError("proof scope requires a boolean verdict and external artifacts")
        for artifact in scope["artifacts"]:
            if set(artifact) != {"path", "expected_sha256"} or _m4_basin_review_file_sha256(artifact["path"]) != artifact["expected_sha256"]:
                raise ValueError("proof scope artifact external hash mismatch")
        if scope["scope"] in ("candidate_full_domain", "candidate_selection") and not isinstance(scope.get("candidate_id"), str):
            raise ValueError("candidate proof needs candidate_id")
        if not isinstance(scope.get("limitations"), str):
            raise ValueError("proof must describe scope limitations")
    return proof

# --- terrain_pipeline/td_basin_review.py:279 ---
def load_basin_review(directory, *, expected_manifest_sha256):
    from terrain_pipeline.common_infra import file_sha256 as _m4_basin_review_file_sha256
    directory = _m4_basin_review_Path(directory)
    if _m4_basin_review_file_sha256(directory / "manifest.json") != expected_manifest_sha256:
        raise ValueError("external review manifest hash mismatch")
    manifest = _m4_basin_review_json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["schema"] != BASIN_REVIEW_SCHEMA or set(manifest["files"]) != {"review.json", "review.html"}:
        raise ValueError("unsupported review manifest")
    for name, expected in manifest["files"].items():
        if (directory / name).stat().st_size > MAX_REVIEW_BYTES * 2 or _m4_basin_review_file_sha256(directory / name) != expected:
            raise ValueError("review file hash or size mismatch")
    payload = (directory / "review.json").read_bytes()
    if _m4_basin_review_hashlib.sha256(payload).hexdigest() != manifest["review_identity_sha256"]:
        raise ValueError("review identity mismatch")
    return _m4_basin_review_json.loads(payload)

# --- terrain_pipeline/td_basin_review.py:295 ---
def load_candidate_comparison(records_path, *, expected_sha256, baseline_records,
                              selection_proof=None):
    """Cold-load 55's fixed index, then check each candidate without retaining all water arrays."""
    from terrain_pipeline.common_infra import file_sha256 as _m4_basin_review_file_sha256
    records_path = _m4_basin_review_Path(records_path).resolve()
    if records_path.stat().st_size > 4 * 1024 ** 2 or _m4_basin_review_file_sha256(records_path) != expected_sha256:
        raise ValueError("external candidate records hash/size mismatch")
    index = _m4_basin_review_json.loads(records_path.read_text(encoding="utf-8"))
    if index.get("schema") != "td-basin-candidate-records-v1":
        raise ValueError("unsupported candidate comparison schema")
    candidate_proof = None
    if selection_proof is not None:
        candidate_proof = load_selection_proof(selection_proof, expected_candidate_records_sha256=expected_sha256)
    if not isinstance(baseline_records, dict) or set(baseline_records) != {"source", "hierarchy", "material", "ordinary", "strong"}:
        raise ValueError("comparison requires exact baseline source/hierarchy/material/ordinary/strong pins")
    base = {role: baseline_records[role] for role in ("source", "hierarchy", "material")}
    original = None
    baseline_ids = {}
    algorithms = {}
    for scenario in ("ordinary", "strong"):
        inputs = load_review_inputs({**base, "storage": baseline_records[scenario]})
        original = inputs["source"]["arrays"]["height_m"].copy()
        baseline_ids[scenario] = inputs["storage"]["identity_sha256"]
        algorithms[scenario] = inputs["storage"]["metadata"]["algorithm"]
        del inputs
    candidates = index.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 11:
        raise ValueError("candidate count exceeds baseline + two morphology + eight saddle budget")
    ids = [record.get("candidate_id") for record in candidates]
    if any(not isinstance(value, str) for value in ids) or len(set(ids)) != len(ids) or "baseline" not in ids or index.get("selected_candidate_id") not in ids:
        raise ValueError("invalid candidate IDs/selection")
    source_identity = baseline_records["source"]["expected_identity"]
    topology_identity = baseline_records["hierarchy"]["expected_identity"]
    summaries = []
    for record in candidates:
        candidate_id = record["candidate_id"]
        if candidate_id == "baseline":
            if record.get("source_identity_sha256") != source_identity or record.get("hierarchy_identity_sha256") != topology_identity:
                raise ValueError("candidate index baseline identity mismatch")
            if any(record.get(scenario + "_identity_sha256") != baseline_ids[scenario] for scenario in baseline_ids):
                raise ValueError("candidate index baseline hydro mismatch")
            summaries.append({"candidate_id": "baseline", "records": baseline_records, "flags": record})
            continue
        role = "breach" if candidate_id.startswith("saddle_breach") else "morphology"
        artifact = record.get("morphology")
        _candidate_artifact(artifact, records_path.parent)
        geometry_inputs = load_review_inputs({**base, "storage": baseline_records["ordinary"], role: artifact})
        geometry = geometry_inputs[role]
        derived = geometry["arrays"]["height_m"].copy()
        ledger = geometry["metadata"]["ledger"]
        if record.get("material_ledger") != ledger:
            raise ValueError("candidate summary ledger differs from pinned geometry")
        delta = derived - original
        if record.get("changed_cells") != int(_m4_basin_review_np.count_nonzero(delta)) or not _m4_basin_review_np.isclose(record.get("max_abs_delta_m"), float(_m4_basin_review_np.max(_m4_basin_review_np.abs(delta))), rtol=0, atol=1e-9):
            raise ValueError("candidate summary geometry differs from pinned geometry")
        del geometry_inputs, geometry
        coupled = {}
        if any(key in record for key in ("source", "hierarchy", "ordinary", "strong")):
            if not all(key in record for key in ("source", "hierarchy", "ordinary", "strong")):
                raise ValueError("partially published candidate coupled state")
            for key in ("source", "hierarchy", "ordinary", "strong"):
                _candidate_artifact(record[key], records_path.parent)
            for scenario in ("ordinary", "strong"):
                selected_records = {"source": record["source"], "hierarchy": record["hierarchy"],
                                    "material": base["material"], "storage": record[scenario]}
                inputs = load_review_inputs(selected_records)
                if not _m4_basin_review_np.array_equal(inputs["source"]["arrays"]["height_m"], derived, equal_nan=True):
                    raise ValueError("candidate rebuilt source differs from pinned geometry")
                if inputs["storage"]["metadata"]["algorithm"] != algorithms[scenario]:
                    raise ValueError("candidate/baseline water algorithm differs")
                coupled[scenario] = {"records": selected_records, "algorithm": algorithms[scenario],
                                     "transient_converged": False, "morphology_flux_ready": False,
                                     "water_bed_identity_sha256": record["source"]["expected_identity"]}
                del inputs
        summaries.append({"candidate_id": candidate_id, "geometry_role": role, "geometry_record": artifact,
                          "original_source_record": base["source"], "flags": record,
                          "coupled_scenarios": coupled, "water_available": bool(coupled),
                          "material_ledger": ledger})
    if _m4_basin_review_file_sha256(records_path) != expected_sha256:
        raise ValueError("candidate index changed during cold adaptation")
    return {"schema": "td-basin-candidate-review-v1", "algorithm": BASIN_REVIEW_ALGORITHM,
            "records_path": str(records_path), "expected_sha256": expected_sha256,
            "selected_candidate_id": index["selected_candidate_id"], "candidates": summaries,
            "selection_proof": candidate_proof,
            "flags": {"transient_converged": False, "morphology_flux_ready": False, "publishable": False},
            "limitations": "Coupled water is bound to each rebuilt bed; selection/sensitivity evidence is reported separately and never inferred from a successful load."}

# --- terrain_pipeline/td_basin_review.py:382 ---
def _candidate_artifact(record, directory):
    if not isinstance(record, dict) or set(record) != {"path", "expected_sha256", "expected_identity"}:
        raise ValueError("candidate artifact requires both external pins")
    path = _m4_basin_review_Path(record["path"]).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("candidate artifact escapes fixed candidate directory")

# --- terrain_pipeline/td_basin_review.py:390 ---
def export_comparison_navigation(comparison, page_links, output_path):
    """Publish actual page links and explicit selection scope, without inventing candidate water."""
    from terrain_pipeline.common_infra import publish_bytes
    if set(page_links) - {candidate["candidate_id"] for candidate in comparison["candidates"]}:
        raise ValueError("navigation links name an unknown candidate")
    rows = []
    for candidate in comparison["candidates"]:
        candidate_id = candidate["candidate_id"]
        links = page_links.get(candidate_id, {})
        if set(links) - {"ordinary", "strong"}:
            raise ValueError("navigation scenario must be ordinary or strong")
        anchors = []
        for scenario in ("ordinary", "strong"):
            if scenario in links:
                target = _m4_basin_review_Path(links[scenario]).resolve(strict=True)
                relative = _m4_basin_review_os.path.relpath(target, _m4_basin_review_Path(output_path).resolve().parent).replace("\\", "/")
                anchors.append('<a href="' + _m4_basin_review_html.escape(relative, quote=True) + '">' + scenario + '</a>')
            else:
                anchors.append(scenario + '：无冻结审查页面')
        flags = candidate.get("flags", {})
        reasons = flags.get("rejection_reasons", [])
        rows.append('<tr><td>' + _m4_basin_review_html.escape(candidate_id) + '</td><td>' + ' · '.join(anchors) + '</td><td>' + _m4_basin_review_html.escape('; '.join(reasons) or '未记录拒绝') + '</td><td>' + _m4_basin_review_html.escape(str(flags.get("selected", False))) + '</td></tr>')
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>TD 候选对照</title><h1>TD 候选只读对照</h1><p>选择范围：固定记录中的有限候选。数值敏感性、形态通量及发布门槛未认证；冷读成功不构成候选接受。没有匹配新床水文时不提供新水面。</p><p>记录选择：' + _m4_basin_review_html.escape(comparison["selected_candidate_id"]) + '</p><table border="1"><tr><th>候选</th><th>两雨页面</th><th>拒绝原因</th><th>记录选中</th></tr>' + ''.join(rows) + '</table><pre>' + _m4_basin_review_html.escape(_m4_basin_review_json.dumps(comparison["flags"], ensure_ascii=False, indent=2)) + '</pre></html>'
    publish_bytes(output_path, page.encode("utf-8"))
    return _m4_basin_review_Path(output_path)

# --- terrain_pipeline/world_acceptance_processes.py:206 ---
class PoolStorage:
    """Use existing exact prism kernels in bounded support chunks, at actual area."""
    def __init__(self, ids, bed, stage, area):
        from terrain_pipeline.lake import LakeStorage as _m4_world_acceptance_processes_LakeStorage
        self.parts = []
        for start in range(0, ids.size, 65536):
            chunk = ids[start:start + 65536].astype(_m4_world_acceptance_processes_np.int64)
            levels = bed[chunk].astype(_m4_world_acceptance_processes_np.float64)
            self.parts.append(_m4_world_acceptance_processes_LakeStorage(chunk, levels, _m4_world_acceptance_processes_np.full(chunk.size, area),
                int(chunk[_m4_world_acceptance_processes_np.argmin(levels)]), float(stage), "0" * 64,
                "equal-spill positive-fill connected Delaunay cells; input identity in report"))
        self.capacity_m3 = sum(part.capacity_m3 for part in self.parts)
        self.minimum = min(part.min_stage_m for part in self.parts)
        self.maximum = float(stage)

    def volume_at_stage(self, stage):
        return sum(part.volume_at_stage(max(part.min_stage_m, stage)) for part in self.parts)

    def stage_at_volume(self, volume):
        if len(self.parts) == 1:
            return self.parts[0].stage_at_volume(min(volume, self.capacity_m3))
        low, high = self.minimum, self.maximum
        for _ in range(55):
            middle = (low + high) / 2
            if self.volume_at_stage(middle) < volume:
                low = middle
            else:
                high = middle
        return (low + high) / 2

# Profile selection keeps every original integrator and its arithmetic.
PROFILES = {
    'threshold_storage': simulate_threshold_storage,
    'strang_split': storageimplicit_simulate,
    'strang_split_refined': storagerefined_simulate,
    'event_strang': storagev3_simulate,
    'threshold_pair': storagev4_simulate,
    'symmetric_forcing': storagev5_simulate,
    'symmetric_ssprk2': storagev6_simulate,
    'compensated_ssprk2': storagev7_simulate,
    'hour_pages': continuation_simulate,
    'compiled_hour': compileddriver_simulate,
    'unified_infiltration': simulate_hour,
}

def simulate_basin_storage(hierarchy, rain_mm_h, *, profile="threshold_storage", **kwargs):
    """Select the original solver; each profile keeps its original keyword contract."""
    try:
        solver = PROFILES[profile]
    except KeyError:
        raise ValueError("Unknown basin storage profile: " + str(profile)) from None
    return solver(hierarchy, rain_mm_h, **kwargs)
