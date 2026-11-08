"""lake: merged M4 implementation; source locations precede each statement."""
from __future__ import annotations

from collections import Counter as _m4_lake_entry_taper_Counter
from collections import deque as _m4_mountain_depression_geometry_deque
from collections import deque as _m4_natural_lakes_deque
from collections.abc import Mapping as _m4_lake_river_connector_Mapping
from dataclasses import asdict as _m4_equilibrium_lake_support_asdict
from dataclasses import asdict as _m4_lake_channel_coupling_asdict
from dataclasses import asdict as _m4_lake_routing_asdict
from dataclasses import asdict as _m4_mountain_depression_geometry_asdict
from dataclasses import asdict as _m4_natural_lakes_asdict
from dataclasses import asdict as _m4_surface_lake_network_asdict
from dataclasses import dataclass as _m4_equilibrium_lake_support_dataclass
from dataclasses import dataclass as _m4_lake_balance_dataclass
from dataclasses import dataclass as _m4_lake_channel_coupling_dataclass
from dataclasses import dataclass as _m4_lake_hypsometry_dataclass
from dataclasses import dataclass as _m4_lake_river_connector_dataclass
from dataclasses import dataclass as _m4_lake_routing_dataclass
from dataclasses import dataclass as _m4_lake_storage_dataclass
from dataclasses import dataclass as _m4_mountain_depression_geometry_dataclass
from dataclasses import dataclass as _m4_native_30m_lakes_dataclass
from dataclasses import dataclass as _m4_natural_lakes_dataclass
from dataclasses import dataclass as _m4_surface_lake_network_dataclass
from dataclasses import dataclass as _m4_world_reach_lake_dataclass
from dataclasses import field as _m4_lake_storage_field
from dataclasses import field as _m4_native_30m_lakes_field
from dataclasses import replace as _m4_surface_lake_network_replace
from pathlib import Path as _m4_lake_interface_continuous_bed_Path
from pathlib import Path as _m4_lake_river_connector_Path
from pathlib import Path as _m4_lake_routing_Path
from pathlib import Path as _m4_mountain_depression_geometry_Path
from pathlib import Path as _m4_mountain_pool_network_Path
from pathlib import Path as _m4_surface_lake_network_Path
from scipy import ndimage as _m4_mountain_depression_geometry_ndimage
from scipy import ndimage as _m4_mountain_lake_experiment_ndimage
from scipy import ndimage as _m4_mountain_pool_network_ndimage
from scipy.integrate import solve_ivp as _m4_natural_lakes_solve_ivp
from terrain_pipeline.common_infra import identity as _m4_lake_hypsometry_identity
from terrain_pipeline.common_infra import readonly as _m4_equilibrium_lake_support_readonly
from terrain_pipeline.common_infra import readonly as _m4_lake_channel_coupling_readonly
from terrain_pipeline.common_infra import readonly as _m4_lake_storage_readonly
from terrain_pipeline.surface_rivers.metric_cross_region import CONTACT_MARGIN_CELLS as _m4_native_30m_lakes_CONTACT_MARGIN_CELLS
from terrain_pipeline.surface_rivers.metric_depression_gate import MAX_GATE_CELLS as _m4_native_30m_lakes_MAX_GATE_CELLS
from types import MappingProxyType as _m4_lake_river_connector_MappingProxyType
import hashlib as _m4_lake_entry_taper_hashlib
import hashlib as _m4_lake_interface_continuous_bed_hashlib
import hashlib as _m4_lake_river_connector_hashlib
import hashlib as _m4_lake_routing_hashlib
import hashlib as _m4_mountain_depression_geometry_hashlib
import hashlib as _m4_surface_lake_network_hashlib
import heapq as _m4_mountain_depression_geometry_heapq
import heapq as _m4_new_world_game_fine_lake_heapq
import json as _m4_lake_entry_taper_json
import json as _m4_lake_interface_continuous_bed_json
import json as _m4_lake_river_connector_json
import json as _m4_lake_routing_json
import json as _m4_mountain_depression_geometry_json
import json as _m4_mountain_pool_network_json
import json as _m4_surface_lake_network_json
import math as _m4_equilibrium_lake_support_math
import math as _m4_lake_balance_math
import math as _m4_lake_channel_coupling_math
import math as _m4_lake_entry_taper_math
import math as _m4_lake_hypsometry_math
import math as _m4_lake_river_connector_math
import math as _m4_lake_routing_math
import math as _m4_lake_storage_math
import math as _m4_mountain_depression_geometry_math
import math as _m4_mountain_lake_coupling_math
import math as _m4_mountain_pool_network_math
import math as _m4_native_30m_lakes_math
import math as _m4_natural_lakes_math
import math as _m4_surface_lake_network_math
import math as _m4_world_reach_lake_math
import numpy as _m4_equilibrium_lake_support_np
import numpy as _m4_lake_balance_np
import numpy as _m4_lake_channel_coupling_np
import numpy as _m4_lake_entry_taper_np
import numpy as _m4_lake_hypsometry_np
import numpy as _m4_lake_river_connector_np
import numpy as _m4_lake_routing_np
import numpy as _m4_lake_storage_np
import numpy as _m4_mountain_depression_geometry_np
import numpy as _m4_mountain_lake_coupling_np
import numpy as _m4_mountain_lake_experiment_np
import numpy as _m4_mountain_pool_network_np
import numpy as _m4_native_30m_lakes_np
import numpy as _m4_natural_lakes_np
import numpy as _m4_new_world_game_fine_lake_np
import numpy as _m4_surface_lake_network_np
import numpy as _m4_world_reach_lake_np
import os as _m4_lake_river_connector_os
import os as _m4_lake_routing_os
import os as _m4_mountain_depression_geometry_os
import os as _m4_mountain_pool_network_os
import os as _m4_surface_lake_network_os
import tempfile as _m4_lake_river_connector_tempfile
import tempfile as _m4_lake_routing_tempfile
import tempfile as _m4_mountain_depression_geometry_tempfile
import tempfile as _m4_mountain_pool_network_tempfile
import tempfile as _m4_surface_lake_network_tempfile
import zipfile as _m4_lake_river_connector_zipfile
import zipfile as _m4_lake_routing_zipfile
import zipfile as _m4_mountain_depression_geometry_zipfile
import zipfile as _m4_mountain_pool_network_zipfile
import zipfile as _m4_surface_lake_network_zipfile

CATEGORY = "B"

# --- terrain_pipeline/surface_rivers/metric_lake_storage.py:11 ---
MAX_LAKE_CELLS = 65536

# --- terrain_pipeline/surface_rivers/metric_lake_storage.py:14 ---
def lakestorage_finite_number(value, name):
    if isinstance(value, (bool, _m4_lake_storage_np.bool_)) or not isinstance(value, (int, float, _m4_lake_storage_np.integer, _m4_lake_storage_np.floating)) or not _m4_lake_storage_math.isfinite(value):
        raise ValueError(name + " must be finite numeric")
    return float(value)

# --- terrain_pipeline/surface_rivers/metric_lake_storage.py:20 ---
def require_sha256_hex(value):
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("lowercase source SHA256 required")

# --- terrain_pipeline/surface_rivers/metric_lake_storage.py:26 ---
@_m4_lake_storage_dataclass(frozen=True)
class LakeStorage:
    cell_ids: _m4_lake_storage_np.ndarray
    bed_elevation_m: _m4_lake_storage_np.ndarray
    cell_area_m2: _m4_lake_storage_np.ndarray
    seed_cell_id: int
    max_stage_m: float
    source_identity_sha256: str
    footprint_policy: str
    _levels_m: _m4_lake_storage_np.ndarray = _m4_lake_storage_field(init=False, repr=False, compare=False)
    _wetted_area_m2: _m4_lake_storage_np.ndarray = _m4_lake_storage_field(init=False, repr=False, compare=False)
    _break_volume_m3: _m4_lake_storage_np.ndarray = _m4_lake_storage_field(init=False, repr=False, compare=False)

    def __post_init__(self):
        ids = self.cell_ids
        if not isinstance(ids, _m4_lake_storage_np.ndarray) or ids.dtype != _m4_lake_storage_np.int64 or ids.ndim != 1 or not 1 <= ids.size <= MAX_LAKE_CELLS or _m4_lake_storage_np.any(ids < 0) or _m4_lake_storage_np.unique(ids).size != ids.size:
            raise ValueError("bounded distinct nonnegative int64 cell IDs required")
        n = ids.size
        for name in ("bed_elevation_m", "cell_area_m2"):
            value = getattr(self, name)
            if not isinstance(value, _m4_lake_storage_np.ndarray) or value.dtype != _m4_lake_storage_np.float64 or value.shape != (n,) or not _m4_lake_storage_np.isfinite(value).all():
                raise ValueError(name + " must be finite float64 per cell")
            if name == "cell_area_m2" and _m4_lake_storage_np.any(value <= 0.):
                raise ValueError("cell areas must be positive")
        if type(self.seed_cell_id) is not int or self.seed_cell_id < 0:
            raise ValueError("seed_cell_id must be a nonnegative integer")
        match = _m4_lake_storage_np.flatnonzero(ids == self.seed_cell_id)
        minimum = float(_m4_lake_storage_np.min(self.bed_elevation_m))
        if match.size != 1 or self.bed_elevation_m[match[0]] != minimum:
            raise ValueError("seed must occur at minimum lake bed")
        maximum = lakestorage_finite_number(self.max_stage_m, "max_stage_m")
        if maximum <= minimum:
            raise ValueError("max_stage_m must exceed minimum bed")
        require_sha256_hex(self.source_identity_sha256)
        if not isinstance(self.footprint_policy, str) or not self.footprint_policy.strip():
            raise ValueError("footprint_policy provenance required")

        levels, group = _m4_lake_storage_np.unique(self.bed_elevation_m, return_inverse=True)
        group_area = _m4_lake_storage_np.bincount(group, weights=self.cell_area_m2, minlength=levels.size)
        wet_area = _m4_lake_storage_np.cumsum(group_area)
        local_levels = levels - minimum
        break_volume = _m4_lake_storage_np.zeros(levels.size, dtype=_m4_lake_storage_np.float64)
        if levels.size > 1:
            break_volume[1:] = _m4_lake_storage_np.cumsum(_m4_lake_storage_np.diff(local_levels) * wet_area[:-1])
        last_active = int(_m4_lake_storage_np.searchsorted(levels, maximum, side="left") - 1)
        capacity = break_volume[last_active] + wet_area[last_active] * (maximum - levels[last_active])
        if not all(_m4_lake_storage_np.isfinite(x).all() for x in (wet_area, local_levels, break_volume)) or not _m4_lake_storage_math.isfinite(capacity) or capacity <= 0.:
            raise ValueError("lake area or capacity exceeds finite resource bounds")
        object.__setattr__(self, "cell_ids", _m4_lake_storage_readonly(ids))
        object.__setattr__(self, "bed_elevation_m", _m4_lake_storage_readonly(self.bed_elevation_m))
        object.__setattr__(self, "cell_area_m2", _m4_lake_storage_readonly(self.cell_area_m2))
        object.__setattr__(self, "max_stage_m", maximum)
        object.__setattr__(self, "_levels_m", _m4_lake_storage_readonly(levels))
        object.__setattr__(self, "_wetted_area_m2", _m4_lake_storage_readonly(wet_area))
        object.__setattr__(self, "_break_volume_m3", _m4_lake_storage_readonly(break_volume))

    @property
    def min_stage_m(self):
        return float(self._levels_m[0])

    @property
    def capacity_m3(self):
        return self.volume_at_stage(self.max_stage_m)

    def _checked_stage(self, stage):
        stage = lakestorage_finite_number(stage, "stage")
        if not self.min_stage_m <= stage <= self.max_stage_m:
            raise ValueError("stage outside finite lake support")
        return stage

    def volume_at_stage(self, stage):
        stage = self._checked_stage(stage)
        index = int(_m4_lake_storage_np.searchsorted(self._levels_m, stage, side="left") - 1)
        if index < 0:
            return 0.
        return float(self._break_volume_m3[index]
                     + self._wetted_area_m2[index] * (stage - self._levels_m[index]))

    def stage_at_volume(self, volume):
        volume = lakestorage_finite_number(volume, "volume")
        if not 0. <= volume <= self.capacity_m3:
            raise ValueError("volume outside finite lake capacity")
        if volume == 0.:
            return self.min_stage_m
        index = int(_m4_lake_storage_np.searchsorted(self._break_volume_m3, volume, side="right") - 1)
        index = min(index, int(_m4_lake_storage_np.searchsorted(self._levels_m, self.max_stage_m, side="left") - 1))
        return float(self._levels_m[index]
                     + (volume - self._break_volume_m3[index]) / self._wetted_area_m2[index])

    def wet_mask_at_stage(self, stage):
        return _m4_lake_storage_readonly(self.bed_elevation_m < self._checked_stage(stage))

    def depth_at_stage(self, stage):
        return _m4_lake_storage_readonly(_m4_lake_storage_np.maximum(self._checked_stage(stage) - self.bed_elevation_m, 0.))

    def surface_area_at_stage(self, stage):
        stage = self._checked_stage(stage)
        index = int(_m4_lake_storage_np.searchsorted(self._levels_m, stage, side="left") - 1)
        return 0. if index < 0 else float(self._wetted_area_m2[index])

# --- terrain_pipeline/surface_rivers/metric_lake_storage.py:127 ---
@_m4_lake_storage_dataclass(frozen=True)
class LakeOutlet:
    lake_index: int
    receiver: int
    crest_stage_m: float
    coefficient_m3_s_m15: float
    provenance: str

    def __post_init__(self):
        if type(self.lake_index) is not int or self.lake_index < 0:
            raise ValueError("lake_index must be nonnegative")
        if type(self.receiver) is not int or self.receiver < -1:
            raise ValueError("receiver must be -1 or nonnegative global node")
        crest = lakestorage_finite_number(self.crest_stage_m, "crest_stage_m")
        coefficient = lakestorage_finite_number(self.coefficient_m3_s_m15, "coefficient_m3_s_m15")
        if coefficient <= 0.:
            raise ValueError("outlet coefficient must be positive")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("outlet coefficient provenance required")
        object.__setattr__(self, "crest_stage_m", crest)
        object.__setattr__(self, "coefficient_m3_s_m15", coefficient)

    def discharge_at_stage(self, stage):
        stage = lakestorage_finite_number(stage, "stage")
        with _m4_lake_storage_np.errstate(over="ignore", invalid="ignore"):
            discharge = self.coefficient_m3_s_m15 * max(stage - self.crest_stage_m, 0.) ** 1.5
        if not _m4_lake_storage_math.isfinite(discharge):
            raise ValueError("outlet discharge exceeds finite range")
        return discharge

# --- terrain_pipeline/lake_routing.py:22 ---
VERSION = "lake-routing-implicit-euler-v1"

# --- terrain_pipeline/lake_routing.py:23 ---
FORMAT_VERSION = 1

# --- terrain_pipeline/lake_routing.py:24 ---
STATUS = "diagnostic_not_publishable"

# --- terrain_pipeline/lake_routing.py:25 ---
LIMITATION = (
    "Finite supplied-flux single-pool implicit Euler engineering approximation; "
    "piecewise-linear supplied Q(h), step-end outflow, not observed hydraulics, "
    "steady state, paper reproduction or a prepared river network. Full "
    "horizontal cell estimate, not measured/subcell geometry. Downstream "
    "path is destination evidence only."
)

# --- terrain_pipeline/lake_routing.py:32 ---
NEIGHBORS = ((-1, 0), (1, 0), (0, -1), (0, 1))

# --- terrain_pipeline/lake_routing.py:33 ---
MAX_STEPS = 4096

# --- terrain_pipeline/lake_routing.py:34 ---
MAX_GRID_CELLS = 1000000

# --- terrain_pipeline/lake_routing.py:35 ---
MAX_SOLVER_ITERATIONS = 128

# --- terrain_pipeline/lake_routing.py:36 ---
MAX_RATING_POINTS = 4096

# --- terrain_pipeline/lake_routing.py:37 ---
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024

# --- terrain_pipeline/lake_routing.py:38 ---
MAX_METADATA_BYTES = 1024 * 1024

# --- terrain_pipeline/lake_routing.py:39 ---
ARRAY_NAMES = frozenset((
    "height_m", "basin_mask", "domain_mask", "protected_mask", "legal_outlet_mask",
    "legal_spill_grid_zx", "downstream_path_grid_zx", "stage_m", "storage_m3",
    "step_inflow_volume_m3", "step_loss_volume_m3", "step_outflow_volume_m3",
    "step_outflow_m3_s", "step_residual_m3", "step_solver_iterations", "wet_mask",
    "water_surface_m", "water_depth_m",
))

# --- terrain_pipeline/lake_routing.py:48 ---
def routing_number(value, name):
    if (isinstance(value, (bool, _m4_lake_routing_np.bool_)) or
            not isinstance(value, (int, float, _m4_lake_routing_np.integer, _m4_lake_routing_np.floating)) or
            not _m4_lake_routing_math.isfinite(value)):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)

# --- terrain_pipeline/lake_routing.py:56 ---
def _positive_integer(value, name):
    if isinstance(value, (bool, _m4_lake_routing_np.bool_)) or not isinstance(value, (int, _m4_lake_routing_np.integer)) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)

# --- terrain_pipeline/lake_routing.py:63 ---
@_m4_lake_routing_dataclass(frozen=True)
class LakeRoutingRecipe:
    initial_stage_m: float
    dt_s: float
    inflow_m3_s: tuple
    loss_m3_s: tuple
    rating_stage_m: tuple
    rating_outflow_m3_s: tuple
    max_stage_m: float
    max_steps: int = 4096
    max_grid_cells: int = 1000000
    max_solver_iterations: int = 128
    volume_abs_tolerance_m3: float = 1e-9
    volume_rel_tolerance: float = 1e-10

    def __post_init__(self):
        for name in ("initial_stage_m", "dt_s", "max_stage_m",
                     "volume_abs_tolerance_m3", "volume_rel_tolerance"):
            object.__setattr__(self, name, routing_number(getattr(self, name), name))
        for name in ("max_steps", "max_grid_cells", "max_solver_iterations"):
            object.__setattr__(self, name, _positive_integer(getattr(self, name), name))
        if (self.max_steps > MAX_STEPS or self.max_grid_cells > MAX_GRID_CELLS or
                self.max_solver_iterations > MAX_SOLVER_ITERATIONS):
            raise ValueError("recipe exceeds hard step/grid/solver resource ceiling")
        for name in ("inflow_m3_s", "loss_m3_s", "rating_stage_m", "rating_outflow_m3_s"):
            try:
                sequence = getattr(self, name)
                limit = MAX_RATING_POINTS if name.startswith("rating_") else MAX_STEPS
                if len(sequence) > limit:
                    raise ValueError(f"{name} exceeds hard sequence resource ceiling")
                values = tuple(routing_number(value, name) for value in sequence)
            except TypeError as error:
                raise ValueError(f"{name} must be a numeric sequence") from error
            object.__setattr__(self, name, values)
        if (self.dt_s <= 0 or self.initial_stage_m > self.max_stage_m or
                self.volume_abs_tolerance_m3 <= 0 or not 0 <= self.volume_rel_tolerance < 1):
            raise ValueError("invalid time, stage or volume tolerance bounds")
        if (not self.inflow_m3_s or len(self.inflow_m3_s) != len(self.loss_m3_s) or
                any(value < 0 for value in self.inflow_m3_s + self.loss_m3_s)):
            raise ValueError("flux sequences must have equal nonzero length and nonnegative values")
        if (len(self.rating_stage_m) < 2 or
                len(self.rating_stage_m) != len(self.rating_outflow_m3_s) or
                any(upper <= lower for lower, upper in zip(self.rating_stage_m, self.rating_stage_m[1:])) or
                self.rating_outflow_m3_s[0] != 0 or
                any(value <= 0 for value in self.rating_outflow_m3_s[1:]) or
                any(upper < lower for lower, upper in zip(self.rating_outflow_m3_s, self.rating_outflow_m3_s[1:]))):
            raise ValueError("rating requires increasing stages, Q(spill)=0 and positive nondecreasing Q above spill")

# --- terrain_pipeline/lake_routing.py:111 ---
def routing_readonly(array):
    contiguous = _m4_lake_routing_np.ascontiguousarray(array)
    return _m4_lake_routing_np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)

# --- terrain_pipeline/lake_routing.py:116 ---
def _indices(value, shape, name, path=False):
    if path:
        try:
            if len(value) > MAX_GRID_CELLS:
                raise ValueError("downstream path exceeds hard resource ceiling")
        except TypeError as error:
            raise ValueError("downstream path must be a bounded sequence") from error
    indices = _m4_lake_routing_np.asarray(value)
    expected = indices.ndim == 2 and indices.shape[1] == 2 if path else indices.shape == (2,)
    if not expected or indices.dtype.kind not in "iu":
        raise ValueError(f"{name} requires integer (z, x) indices, without coercion")
    if any(isinstance(item, (bool, _m4_lake_routing_np.bool_)) for item in _m4_lake_routing_np.asarray(value, dtype=object).flat):
        raise ValueError(f"{name} rejects boolean indices")
    pairs = indices if path else indices.reshape(1, 2)
    if (len(pairs) == 0 or _m4_lake_routing_np.any(pairs < 0) or
            _m4_lake_routing_np.any(pairs[:, 0] >= shape[0]) or _m4_lake_routing_np.any(pairs[:, 1] >= shape[1])):
        raise ValueError(f"{name} indices are outside the grid")
    return _m4_lake_routing_np.array(indices, dtype=_m4_lake_routing_np.int64, copy=True)

# --- terrain_pipeline/lake_routing.py:136 ---
def _connected(mask):
    count = int(_m4_lake_routing_np.count_nonzero(mask))
    if count == 0:
        return True
    start = tuple(_m4_lake_routing_np.argwhere(mask)[0])
    visited = {start}
    pending = [start]
    while pending:
        row, column = pending.pop()
        for delta_row, delta_column in NEIGHBORS:
            neighbor = (row + delta_row, column + delta_column)
            if (0 <= neighbor[0] < mask.shape[0] and 0 <= neighbor[1] < mask.shape[1] and
                    mask[neighbor] and neighbor not in visited):
                visited.add(neighbor)
                pending.append(neighbor)
    return len(visited) == count

# --- terrain_pipeline/lake_routing.py:154 ---
def routing_array_hash(array):
    digest = _m4_lake_routing_hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(_m4_lake_routing_json.dumps(list(array.shape)).encode("ascii"))
    digest.update(_m4_lake_routing_np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()

# --- terrain_pipeline/lake_routing.py:162 ---
def routing_json(value):
    return _m4_lake_routing_json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

# --- terrain_pipeline/lake_routing.py:166 ---
def _metadata(result):
    return {name: value for name, value in result.items() if name not in ("arrays", "identity_sha256")}

# --- terrain_pipeline/lake_routing.py:170 ---
def lake_routing_hash(result):
    """Integrity hash only; semantic acceptance additionally requires replay."""
    record = {"metadata": _metadata(result),
              "arrays": {name: routing_array_hash(array) for name, array in sorted(result["arrays"].items())}}
    return _m4_lake_routing_hashlib.sha256(routing_json(record).encode("utf-8")).hexdigest()

# --- terrain_pipeline/lake_routing.py:177 ---
def evaluate_lake_routing(height_m, basin_mask, legal_spill_grid_zx,
                          spacing_x_m, spacing_z_m, source_identity,
                          recipe: LakeRoutingRecipe, downstream_path_grid_zx,
                          domain_mask, protected_mask, legal_outlet_mask,
                          origin_x_m, origin_z_m, vertical_datum):
    """Solve V(next)+dt*Q(next)=V(previous)+dt*(inflow-loss), in SI units.

    Invalid parameters raise ValueError. Infeasibility returns entire input,
    committed trajectory prefix and failed-step evidence. Stage/storage arrays
    include initial state; step arrays do not. Dry water surface is NaN and
    dry depth zero. Even feasible results remain diagnostic_not_publishable.
    """
    if not isinstance(recipe, LakeRoutingRecipe):
        raise ValueError("recipe must be LakeRoutingRecipe")
    raw_height = _m4_lake_routing_np.asarray(height_m)
    if raw_height.ndim != 2 or raw_height.size == 0 or raw_height.dtype.kind not in "fiu":
        raise ValueError("terrain must be a nonempty real two-dimensional grid")
    if (raw_height.size > recipe.max_grid_cells or raw_height.size > MAX_GRID_CELLS or
            len(recipe.inflow_m3_s) > recipe.max_steps):
        raise ValueError("input grid or time-step count exceeds resource bounds before copying")
    raw_basin = _m4_lake_routing_np.asarray(basin_mask)
    if raw_basin.shape != raw_height.shape or raw_basin.dtype != bool or not raw_basin.any():
        raise ValueError("basin must be a nonempty boolean grid matching terrain")
    if recipe.max_stage_m < float(_m4_lake_routing_np.min(raw_height[raw_basin])):
        raise ValueError("max stage must not lie below the minimum basin bed")
    terrain = _m4_lake_routing_np.array(raw_height, dtype=_m4_lake_routing_np.float64, copy=True)
    if not _m4_lake_routing_np.isfinite(terrain).all():
        raise ValueError("terrain must be finite")
    masks = {}
    for name, value in (("basin_mask", basin_mask), ("domain_mask", domain_mask),
                        ("protected_mask", protected_mask), ("legal_outlet_mask", legal_outlet_mask)):
        mask = _m4_lake_routing_np.asarray(value)
        if mask.dtype != bool or mask.shape != terrain.shape:
            raise ValueError(f"{name} must be a boolean grid matching terrain")
        masks[name] = _m4_lake_routing_np.array(mask, copy=True)
    basin = masks["basin_mask"]
    domain = masks["domain_mask"]
    protected = masks["protected_mask"]
    legal = masks["legal_outlet_mask"]
    if not basin.any():
        raise ValueError("basin must be nonempty")
    spill_array = _indices(legal_spill_grid_zx, terrain.shape, "spill")
    spill = tuple(spill_array)
    downstream = _indices(downstream_path_grid_zx, terrain.shape, "downstream path", path=True)
    spacing_x_m = routing_number(spacing_x_m, "spacing_x_m")
    spacing_z_m = routing_number(spacing_z_m, "spacing_z_m")
    origin_x_m = routing_number(origin_x_m, "origin_x_m")
    origin_z_m = routing_number(origin_z_m, "origin_z_m")
    area = spacing_x_m * spacing_z_m
    if spacing_x_m <= 0 or spacing_z_m <= 0 or not _m4_lake_routing_math.isfinite(area) or area == 0:
        raise ValueError("spacing must give finite positive cell area")
    if (not isinstance(source_identity, str) or not source_identity.strip() or
            not isinstance(vertical_datum, str) or not vertical_datum.strip()):
        raise ValueError("explicit source identity and vertical datum are required")
    spill_stage = float(terrain[spill])
    if recipe.rating_stage_m[0] != spill_stage:
        raise ValueError("rating first stage must equal explicit spill terrain elevation")
    input_arrays = {"height_m": terrain, **masks,
                    "legal_spill_grid_zx": spill_array, "downstream_path_grid_zx": downstream}
    parameters = {"spacing_x_m": spacing_x_m, "spacing_z_m": spacing_z_m,
                  "origin_x_m": origin_x_m, "origin_z_m": origin_z_m,
                  "vertical_datum": vertical_datum, "source_identity": source_identity,
                  "recipe": _m4_lake_routing_asdict(recipe)}
    floors = terrain[basin]
    minimum_stage = float(_m4_lake_routing_np.min(floors))

    def volume(stage):
        with _m4_lake_routing_np.errstate(over="ignore", invalid="ignore"):
            return float(_m4_lake_routing_np.sum(_m4_lake_routing_np.maximum(stage - floors, 0.)) * area)

    def discharge(stage):
        if stage <= spill_stage:
            return 0.
        if stage > recipe.rating_stage_m[-1]:
            raise ValueError("rating extrapolation forbidden")
        return float(_m4_lake_routing_np.interp(stage, recipe.rating_stage_m, recipe.rating_outflow_m3_s))

    def tolerance(*terms):
        return recipe.volume_abs_tolerance_m3 + recipe.volume_rel_tolerance * max(abs(term) for term in terms)

    initial_volume = volume(recipe.initial_stage_m)
    stages = [recipe.initial_stage_m]
    storage = [initial_volume]
    steps = []
    diagnostic = {"code": "scenario_feasible", "message": "finite engineering scenario completed",
                  "failed_step": None, "evidence": {}}

    def fail(code, message, evidence=None, step=None):
        diagnostic.update(code=code, message=message, failed_step=step, evidence=evidence or {})

    if not _m4_lake_routing_math.isfinite(initial_volume):
        fail("arithmetic_overflow", "initial volume is outside finite arithmetic")
    elif not _connected(basin):
        fail("basin_disconnected", "explicit basin is not four-neighbor connected")
    elif _m4_lake_routing_np.any(basin & ~domain) or _m4_lake_routing_np.any(basin & protected):
        fail("basin_domain_or_protection", "basin crosses domain or protected cells", {
            "outside_domain_cells": int(_m4_lake_routing_np.count_nonzero(basin & ~domain)),
            "protected_cells": int(_m4_lake_routing_np.count_nonzero(basin & protected))})
    elif basin[0].any() or basin[-1].any() or basin[:, 0].any() or basin[:, -1].any():
        fail("unmodeled_grid_boundary", "basin has no modeled enclosing shore at grid edge")
    elif basin[spill] or not any(
            0 <= spill[0] + delta_row < terrain.shape[0] and
            0 <= spill[1] + delta_column < terrain.shape[1] and
            basin[spill[0] + delta_row, spill[1] + delta_column]
            for delta_row, delta_column in NEIGHBORS):
        fail("invalid_spill", "spill must be a non-basin cell touching the basin")
    elif len(downstream) < 2 or tuple(downstream[0]) != spill or not legal[tuple(downstream[-1])]:
        fail("missing_legal_outlet", "spill path must start at spill and end at an explicit legal outlet")
    elif (len({tuple(point) for point in downstream}) != len(downstream) or
            _m4_lake_routing_np.any(_m4_lake_routing_np.sum(_m4_lake_routing_np.abs(_m4_lake_routing_np.diff(downstream, axis=0)), axis=1) != 1)):
        fail("invalid_downstream_adjacency", "spill path must be simple and four-neighbor connected")
    else:
        path_rows, path_columns = downstream.T
        if (_m4_lake_routing_np.any(~domain[path_rows, path_columns]) or
                _m4_lake_routing_np.any(protected[path_rows, path_columns]) or _m4_lake_routing_np.any(basin[path_rows, path_columns])):
            fail("path_domain_or_protection", "downstream path crosses basin, protection or domain")
        elif _m4_lake_routing_np.any(_m4_lake_routing_np.diff(terrain[path_rows, path_columns]) > 0):
            fail("uphill_downstream_path", "downstream evidence must be nonascending")
        elif terrain[tuple(downstream[-1])] >= spill_stage:
            fail("outlet_not_below_spill", "legal outflow destination must be strictly below spill")
        else:
            shore = _m4_lake_routing_np.zeros(terrain.shape, dtype=bool)
            for row, column in _m4_lake_routing_np.argwhere(basin):
                for delta_row, delta_column in NEIGHBORS:
                    neighbor = (row + delta_row, column + delta_column)
                    if not basin[neighbor]:
                        shore[neighbor] = True
            shore[spill] = False
            low_shore = shore & (terrain < recipe.max_stage_m)
            if low_shore.any():
                fail("unmodeled_low_saddle", "max stage exceeds another modeled shore elevation", {
                    "lowest_unmodeled_shore_m": float(_m4_lake_routing_np.min(terrain[shore])),
                    "max_stage_m": recipe.max_stage_m,
                    "conflicting_grid_zx": _m4_lake_routing_np.argwhere(low_shore).tolist()})
    if diagnostic["code"] == "scenario_feasible":
        if recipe.initial_stage_m > recipe.rating_stage_m[-1]:
            fail("rating_range_exceeded", "initial stage is outside supplied rating range")
        elif not _connected(basin & (terrain < recipe.initial_stage_m)):
            fail("wet_pool_disconnected", "initial wet cells violate the single connected pool assumption")
    upper_stage = min(recipe.max_stage_m, recipe.rating_stage_m[-1])
    if diagnostic["code"] == "scenario_feasible":
        for step_index, (inflow, loss) in enumerate(zip(recipe.inflow_m3_s, recipe.loss_m3_s)):
            inflow_volume = recipe.dt_s * inflow
            loss_volume = recipe.dt_s * loss
            target = storage[-1] + recipe.dt_s * (inflow - loss)
            upper_storage = volume(upper_stage)
            upper_outflow = recipe.dt_s * discharge(upper_stage)
            upper_capacity = upper_storage + upper_outflow
            evidence = {"previous_storage_m3": storage[-1], "inflow_m3_s": inflow,
                        "loss_m3_s": loss, "dt_s": recipe.dt_s}
            if not all(_m4_lake_routing_math.isfinite(value) for value in (
                    target, inflow_volume, loss_volume, upper_storage, upper_outflow, upper_capacity)):
                fail("arithmetic_overflow", "step flux or capacity is outside finite arithmetic", evidence, step_index)
                break
            evidence.update(target_volume_m3=target, upper_stage_m=upper_stage,
                            upper_storage_plus_outflow_m3=upper_capacity)
            if target < 0:
                fail("dry_loss_exceeds_available_water", "prescribed losses cannot be supplied", evidence, step_index)
                break
            if target > upper_capacity:
                code = "rating_range_exceeded" if recipe.rating_stage_m[-1] < recipe.max_stage_m else "spill_capacity_exceeded"
                fail(code, "no implicit root inside the bounded modeled stage range", evidence, step_index)
                break
            lower = min(minimum_stage, upper_stage)
            upper = upper_stage
            solved = False
            if target == 0:
                next_stage = min(minimum_stage, stages[-1], upper_stage)
                next_storage = 0.
                next_outflow_volume = 0.
                residual = 0.
                iterations = 0
                solved = True
            else:
                for iterations in range(1, recipe.max_solver_iterations + 1):
                    next_stage = lower + (upper - lower) * .5
                    next_storage = volume(next_stage)
                    next_outflow_volume = recipe.dt_s * discharge(next_stage)
                    residual = next_storage + next_outflow_volume - target
                    allowed = tolerance(storage[-1], next_storage, inflow_volume, loss_volume, next_outflow_volume)
                    if abs(residual) <= allowed:
                        solved = True
                        break
                    if residual > 0:
                        upper = next_stage
                    else:
                        lower = next_stage
            if not solved:
                evidence.update(last_residual_m3=residual, iterations=iterations,
                                lower_stage_m=lower, upper_stage_m=upper)
                fail("solver_resource_limit", "bounded bisection did not meet volume tolerance", evidence, step_index)
                break
            if not _connected(basin & (terrain < next_stage)):
                evidence.update(candidate_stage_m=next_stage)
                fail("wet_pool_disconnected", "candidate wet cells violate the connected single pool", evidence, step_index)
                break
            stages.append(float(next_stage))
            storage.append(float(next_storage))
            steps.append((inflow_volume, loss_volume, next_outflow_volume,
                          next_outflow_volume / recipe.dt_s, residual, iterations))
    final_stage = stages[-1]
    with _m4_lake_routing_np.errstate(over="ignore", invalid="ignore"):
        depth = _m4_lake_routing_np.where(basin, _m4_lake_routing_np.maximum(final_stage - terrain, 0.), 0.)
    wet = depth > 0
    water = _m4_lake_routing_np.full(terrain.shape, _m4_lake_routing_np.nan)
    water[wet] = final_stage
    step_data = _m4_lake_routing_np.asarray(steps, dtype=_m4_lake_routing_np.float64).reshape(-1, 6)
    arrays = {**input_arrays, "stage_m": _m4_lake_routing_np.asarray(stages), "storage_m3": _m4_lake_routing_np.asarray(storage),
              "step_inflow_volume_m3": step_data[:, 0], "step_loss_volume_m3": step_data[:, 1],
              "step_outflow_volume_m3": step_data[:, 2], "step_outflow_m3_s": step_data[:, 3],
              "step_residual_m3": step_data[:, 4], "step_solver_iterations": step_data[:, 5].astype(_m4_lake_routing_np.int64),
              "wet_mask": wet, "water_surface_m": water, "water_depth_m": depth}
    final_volume = volume(final_stage)
    total_residual = float(_m4_lake_routing_math.fsum(step_data[:, 4]))
    feasible = diagnostic["code"] == "scenario_feasible"
    summary = {"completed_steps": len(steps), "requested_steps": len(recipe.inflow_m3_s),
               "final_stage_m": final_stage, "initial_storage_m3": initial_volume if _m4_lake_routing_math.isfinite(initial_volume) else None,
               "final_storage_m3": final_volume if _m4_lake_routing_math.isfinite(final_volume) else None,
               "cell_area_m2": area, "wet_cells": int(_m4_lake_routing_np.count_nonzero(wet)),
               "total_inflow_volume_m3": float(_m4_lake_routing_math.fsum(step_data[:, 0])),
               "total_loss_volume_m3": float(_m4_lake_routing_math.fsum(step_data[:, 1])),
               "total_outflow_volume_m3": float(_m4_lake_routing_math.fsum(step_data[:, 2])),
               "total_residual_m3": total_residual, "limitation": LIMITATION}
    if feasible:
        geometry_volume = float(_m4_lake_routing_np.sum(depth) * area)
        aggregate_error = _m4_lake_routing_math.fsum((final_volume, -initial_volume,
                                    -summary["total_inflow_volume_m3"], summary["total_loss_volume_m3"],
                                    summary["total_outflow_volume_m3"]))
        allowed_total = _m4_lake_routing_math.fsum(tolerance(storage[index], storage[index + 1], *row[:3])
                                  for index, row in enumerate(step_data))
        summary.update(geometry_volume_m3=geometry_volume, aggregate_balance_residual_m3=aggregate_error,
                       cumulative_volume_tolerance_m3=allowed_total)
        if (abs(geometry_volume - final_volume) > tolerance(final_volume, geometry_volume) or
                abs(aggregate_error) > allowed_total):
            fail("geometry_or_total_balance", "final geometry or aggregate ledger failed volume tolerance")
            feasible = False
    result = {"algorithm_version": VERSION, "format_version": FORMAT_VERSION, "status": STATUS,
              "scenario_feasible": feasible, "input": parameters, "diagnostic": diagnostic,
              "summary": summary, "arrays": {name: routing_readonly(array) for name, array in arrays.items()}}
    result["identity_sha256"] = lake_routing_hash(result)
    return result

# --- terrain_pipeline/lake_routing.py:420 ---
def _replay(result):
    try:
        if (result["algorithm_version"] != VERSION or result["format_version"] != FORMAT_VERSION or
                result["status"] != STATUS or type(result["scenario_feasible"]) is not bool or
                result["identity_sha256"] != lake_routing_hash(result)):
            raise ValueError("lake routing integrity or status mismatch")
        parameters = dict(result["input"])
        recipe = LakeRoutingRecipe(**parameters.pop("recipe"))
        arrays = result["arrays"]
        if set(arrays) != ARRAY_NAMES:
            raise ValueError("lake routing bundle has an unexpected array set")
        replayed = evaluate_lake_routing(
            arrays["height_m"], arrays["basin_mask"], arrays["legal_spill_grid_zx"],
            recipe=recipe, downstream_path_grid_zx=arrays["downstream_path_grid_zx"],
            domain_mask=arrays["domain_mask"], protected_mask=arrays["protected_mask"],
            legal_outlet_mask=arrays["legal_outlet_mask"], **parameters)
        if routing_json(_metadata(result)) != routing_json(_metadata(replayed)) or arrays.keys() != replayed["arrays"].keys():
            raise ValueError("lake routing replay metadata mismatch")
        for name, expected in replayed["arrays"].items():
            actual = arrays[name]
            if (actual.dtype != expected.dtype or actual.shape != expected.shape or
                    not _m4_lake_routing_np.array_equal(actual, expected, equal_nan=True)):
                raise ValueError(f"lake routing replay array mismatch: {name}")
        return replayed
    except (KeyError, TypeError, OverflowError, AttributeError) as error:
        raise ValueError("malformed lake routing bundle") from error

# --- terrain_pipeline/lake_routing.py:448 ---
def save_lake_routing(result, destination):
    """Atomically link a complete replay-validated diagnostic, never overwrite."""
    destination = _m4_lake_routing_Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    if destination.suffix != ".npz":
        raise ValueError("lake routing diagnostic destination must have .npz suffix")
    validated = _replay(result)
    metadata = _metadata(validated)
    metadata["identity_sha256"] = validated["identity_sha256"]
    metadata_text = routing_json(metadata)
    if len(metadata_text) * 4 + 256 > MAX_METADATA_BYTES:
        raise ValueError("diagnostic metadata exceeds archive byte ceiling")
    descriptor, temporary = _m4_lake_routing_tempfile.mkstemp(prefix=".lake-routing-", suffix=".tmp", dir=destination.parent)
    try:
        with _m4_lake_routing_os.fdopen(descriptor, "wb") as handle:
            _m4_lake_routing_np.savez_compressed(handle, metadata=_m4_lake_routing_np.asarray(metadata_text), **validated["arrays"])
            handle.flush()
            _m4_lake_routing_os.fsync(handle.fileno())
        with open(temporary, "rb") as handle:
            _check_archive(handle)
        _m4_lake_routing_os.link(temporary, destination)
    finally:
        _m4_lake_routing_os.unlink(temporary)
    return destination

# --- terrain_pipeline/lake_routing.py:475 ---
def routing_unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON key: {name}")
        result[name] = value
    return result

# --- terrain_pipeline/lake_routing.py:484 ---
def routing_reject_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")

# --- terrain_pipeline/lake_routing.py:488 ---
def _check_archive(handle):
    if _m4_lake_routing_os.fstat(handle.fileno()).st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("lake routing archive exceeds compressed byte ceiling")
    with _m4_lake_routing_zipfile.ZipFile(handle) as archive:
        entries = archive.infolist()
        expected = {name + ".npy" for name in ARRAY_NAMES} | {"metadata.npy"}
        if len(entries) != len(expected) or {entry.filename for entry in entries} != expected:
            raise ValueError("archive requires exactly the expected unique array members")
        if sum(entry.file_size for entry in entries) > MAX_ARCHIVE_BYTES:
            raise ValueError("lake routing archive exceeds decompressed byte ceiling")
        if any(entry.flag_bits & 1 for entry in entries):
            raise ValueError("encrypted lake routing members are unsupported")
        if archive.getinfo("metadata.npy").file_size > MAX_METADATA_BYTES:
            raise ValueError("lake routing metadata exceeds byte ceiling")
        for entry in entries:
            with archive.open(entry) as member:
                version = _m4_lake_routing_np.lib.format.read_magic(member)
                if version == (1, 0):
                    shape, fortran_order, dtype = _m4_lake_routing_np.lib.format.read_array_header_1_0(member)
                elif version == (2, 0):
                    shape, fortran_order, dtype = _m4_lake_routing_np.lib.format.read_array_header_2_0(member)
                else:
                    raise ValueError("unsupported lake routing array header version")
                if dtype.hasobject or fortran_order or len(shape) > 2:
                    raise ValueError("unsupported lake routing array dtype or layout")
                count = _m4_lake_routing_math.prod(shape)
                limit = MAX_METADATA_BYTES if entry.filename == "metadata.npy" else MAX_ARCHIVE_BYTES
                if count * dtype.itemsize > limit or member.tell() + count * dtype.itemsize != entry.file_size:
                    raise ValueError("array header exceeds bounded member size")
                if entry.filename == "metadata.npy":
                    if shape != () or dtype.kind != "U":
                        raise ValueError("invalid metadata scalar header")
                elif entry.filename in {name + ".npy" for name in (
                        "height_m", "basin_mask", "domain_mask", "protected_mask", "legal_outlet_mask",
                        "wet_mask", "water_surface_m", "water_depth_m")}:
                    if len(shape) != 2 or count > MAX_GRID_CELLS:
                        raise ValueError("archive grid exceeds hard cell ceiling")
                elif entry.filename == "downstream_path_grid_zx.npy":
                    if len(shape) != 2 or shape[1] != 2 or shape[0] > MAX_GRID_CELLS:
                        raise ValueError("archive path exceeds hard index ceiling")
                elif count > MAX_STEPS + 1:
                    raise ValueError("archive trajectory exceeds hard step ceiling")
    handle.seek(0)

# --- terrain_pipeline/lake_routing.py:533 ---
def load_lake_routing(source):
    """Load immutable arrays only after hashes and full semantic replay."""
    try:
        with open(source, "rb") as handle:
            _check_archive(handle)
            return _load_checked(handle)
    except (OSError, EOFError, KeyError, TypeError, _m4_lake_routing_zipfile.BadZipFile, _m4_lake_routing_json.JSONDecodeError) as error:
        raise ValueError("invalid lake routing diagnostic archive") from error

# --- terrain_pipeline/lake_routing.py:543 ---
def _load_checked(handle):
    with _m4_lake_routing_np.load(handle, allow_pickle=False) as archive:
        metadata = archive["metadata"]
        result = _m4_lake_routing_json.loads(str(metadata.item()), object_pairs_hook=routing_unique_object,
                            parse_constant=routing_reject_constant)
        result["arrays"] = {name: archive[name].copy() for name in archive.files if name != "metadata"}
    return _replay(result)

# --- terrain_pipeline/surface_lake_network.py:31 ---
NETWORK_VERSION = "surface-lake-network-v1"

# --- terrain_pipeline/surface_lake_network.py:32 ---
NETWORK_FORMAT_VERSION = 1

# --- terrain_pipeline/surface_lake_network.py:33 ---
NETWORK_STATUS = "diagnostic_not_publishable"

# --- terrain_pipeline/surface_lake_network.py:34 ---
NETWORK_MAX_ARCHIVE_BYTES = 256 * 1024 * 1024

# --- terrain_pipeline/surface_lake_network.py:35 ---
NETWORK_MAX_METADATA_BYTES = 4 * 1024 * 1024

# --- terrain_pipeline/surface_lake_network.py:36 ---
MAX_MEMBERS = 4096

# --- terrain_pipeline/surface_lake_network.py:37 ---
NETWORK_LIMITATION = (
    "Finite one-way step-end lake outflow drives separately recalculated static "
    "downstream engineering gates. No spill/drop connector water geometry, "
    "continuous lake-river geometry, dynamic backwater, observed hydraulics, "
    "steady state or complete network publication. Downstream is quasi-steady "
    "per step: river storage and propagation time are omitted from the combined ledger."
    " Bed/valley candidates restart from original H0 per scenario; this is not "
    "time-evolving erosion, and scenario cut volumes are not cumulative construction."
)

# --- terrain_pipeline/surface_lake_network.py:49 ---
@_m4_surface_lake_network_dataclass(frozen=True)
class SurfaceLakeNetworkRecipe:
    max_steps: int = 16
    max_lake_cells: int = 1000000
    max_coarse_cells: int = 250000
    max_fine_cells: int = 1000000
    max_total_attempts: int = 64
    max_total_fine_work: int = 4000000
    max_total_lake_work: int = 4000000
    max_retained_bytes: int = 268435456
    discharge_abs_tolerance_m3_s: float = 1e-9
    discharge_rel_tolerance: float = 1e-10

    def __post_init__(self):
        ceilings = dict(max_steps=64, max_lake_cells=1000000, max_coarse_cells=250000,
                        max_fine_cells=1000000, max_total_attempts=128,
                        max_total_fine_work=8000000, max_total_lake_work=8000000,
                        max_retained_bytes=268435456)
        for name, ceiling in ceilings.items():
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError(f"invalid bounded joint resource: {name}")
        for name in ("discharge_abs_tolerance_m3_s", "discharge_rel_tolerance"):
            value = getattr(self, name)
            if isinstance(value, (bool, _m4_surface_lake_network_np.bool_)) or not isinstance(value, (int, float)) or not _m4_surface_lake_network_math.isfinite(value):
                raise ValueError("joint tolerances must be finite real numbers")
        if self.discharge_abs_tolerance_m3_s <= 0 or not 0 <= self.discharge_rel_tolerance < 1:
            raise ValueError("invalid joint discharge tolerance")

# --- terrain_pipeline/surface_lake_network.py:79 ---
@_m4_surface_lake_network_dataclass(frozen=True)
class LakeRiverSeam:
    lake_path_grid_zx: tuple
    world_x_m: float
    world_z_m: float
    downstream_vertical_datum: str
    lake_source_identity: str
    downstream_source_identity: str

    def __post_init__(self):
        pair = self.lake_path_grid_zx
        if (not isinstance(pair, (tuple, list, _m4_surface_lake_network_np.ndarray)) or len(pair) != 2 or
                any(isinstance(value, (bool, _m4_surface_lake_network_np.bool_)) or not isinstance(value, (int, _m4_surface_lake_network_np.integer)) for value in pair)):
            raise ValueError("seam lake node must be a strict integer (z, x) pair")
        object.__setattr__(self, "lake_path_grid_zx", tuple(int(value) for value in pair))
        for name in ("world_x_m", "world_z_m"):
            value = getattr(self, name)
            if isinstance(value, (bool, _m4_surface_lake_network_np.bool_)) or not isinstance(value, (int, float)) or not _m4_surface_lake_network_math.isfinite(value):
                raise ValueError("seam world coordinates must be finite")
        for name in ("downstream_vertical_datum", "lake_source_identity", "downstream_source_identity"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError("explicit seam datum and source bindings required")

# --- terrain_pipeline/surface_lake_network.py:102 ---
def network_readonly(array):
    contiguous = _m4_surface_lake_network_np.ascontiguousarray(array)
    return _m4_surface_lake_network_np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)

# --- terrain_pipeline/surface_lake_network.py:107 ---
def network_freeze(value, memo=None):
    if memo is None:
        memo = {}
    if isinstance(value, _m4_surface_lake_network_np.ndarray):
        if id(value) not in memo:
            memo[id(value)] = network_readonly(value)
        return memo[id(value)]
    if isinstance(value, dict):
        return {name: network_freeze(child, memo) for name, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [network_freeze(child, memo) for child in value]
    if isinstance(value, _m4_surface_lake_network_np.generic):
        return value.item()
    return value

# --- terrain_pipeline/surface_lake_network.py:123 ---
def _retained_bytes(value):
    if isinstance(value, _m4_surface_lake_network_np.ndarray):
        return int(value.nbytes) + 256
    if isinstance(value, dict):
        return 256 + sum(128 + len(str(name)) * 4 + _retained_bytes(item) for name, item in value.items())
    if isinstance(value, (tuple, list)):
        return 128 + sum(32 + _retained_bytes(item) for item in value)
    if isinstance(value, str):
        return 64 + len(value) * 4
    return 64

# --- terrain_pipeline/surface_lake_network.py:135 ---
def network_json(value):
    return _m4_surface_lake_network_json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

# --- terrain_pipeline/surface_lake_network.py:139 ---
def network_array_hash(array):
    digest = _m4_surface_lake_network_hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(network_json(list(array.shape)).encode("ascii"))
    digest.update(_m4_surface_lake_network_np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()

# --- terrain_pipeline/surface_lake_network.py:147 ---
def network_tree(value, arrays):
    if isinstance(value, _m4_surface_lake_network_np.ndarray):
        identity = network_array_hash(value)
        name = "array_" + identity
        arrays[name] = value
        return {"$array": name, "dtype": value.dtype.str, "shape": list(value.shape), "sha256": identity}
    if isinstance(value, dict):
        return {name: network_tree(child, arrays) for name, child in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [network_tree(child, arrays) for child in value]
    if isinstance(value, _m4_surface_lake_network_np.generic):
        return value.item()
    return value

# --- terrain_pipeline/surface_lake_network.py:162 ---
def surface_lake_network_hash(result):
    """Integrity only, never a substitute for algorithm replay."""
    payload = {name: value for name, value in result.items() if name != "identity_sha256"}
    return _m4_surface_lake_network_hashlib.sha256(network_json(network_tree(payload, {})).encode("utf-8")).hexdigest()

# --- terrain_pipeline/surface_lake_network.py:168 ---
def _validated_plan(plan):
    from terrain_pipeline.channel_geometry import ChannelRecipe as _m4_surface_lake_network_ChannelRecipe
    from terrain_pipeline.channel_geometry import plan_channel as _m4_surface_lake_network_plan_channel
    try:
        parameters = plan["identity"]["parameters"]
        channel = _m4_surface_lake_network_ChannelRecipe(**{name: parameters[name] for name in _m4_surface_lake_network_ChannelRecipe.__dataclass_fields__})
        arrays = plan["arrays"]
        replay = _m4_surface_lake_network_plan_channel(arrays["source_height_m"], arrays["receiver"], arrays["order"],
                              arrays["outlet_mask"], arrays["discharge_m3_s"],
                              parameters["spacing_x_m"], parameters["spacing_z_m"],
                              parameters["origin_x_m"], parameters["origin_z_m"],
                              parameters["sea_level_elevation_m"], parameters["source_identity"], channel)
        if network_json(network_tree(replay, {})) != network_json(network_tree(plan, {})):
            raise ValueError("downstream plan differs from semantic replay")
        discharge = replay["arrays"]["discharge_m3_s"].ravel()
        receiver = replay["arrays"]["receiver"]
        local = discharge.copy()
        donors = _m4_surface_lake_network_np.flatnonzero(receiver >= 0)
        _m4_surface_lake_network_np.subtract.at(local, receiver[donors], discharge[donors])
        if _m4_surface_lake_network_np.any(local < 0):
            raise ValueError("downstream plan Q is not conservative nonnegative local inflow")
        reconstructed = _accumulate(local, replay["arrays"])
        if not _m4_surface_lake_network_np.allclose(reconstructed, discharge, rtol=1e-12, atol=1e-12):
            raise ValueError("downstream plan discharge reconstruction failed")
        return replay, channel, local
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError("invalid downstream original plan") from error

# --- terrain_pipeline/surface_lake_network.py:195 ---
def _accumulate(local, arrays):
    discharge = local.copy()
    for donor in arrays["order"][::-1]:
        target = arrays["receiver"][donor]
        if target >= 0:
            discharge[target] += discharge[donor]
    if not _m4_surface_lake_network_np.isfinite(discharge).all():
        raise ValueError("downstream accumulated discharge overflow")
    return discharge

# --- terrain_pipeline/surface_lake_network.py:206 ---
def _aligned_index(world, origin, spacing, size):
    fraction = (world - origin) / spacing
    index = round(fraction)
    if index < 0 or index >= size or origin + index * spacing != world:
        raise ValueError("seam world coordinate is not exactly aligned to a downstream node")
    return index

# --- terrain_pipeline/surface_lake_network.py:214 ---
def _overlap(lake_inputs, wet, fine, fine_wet):
    """Conservative positive footprint intersection, never point-only overlap."""
    rows, columns = _m4_surface_lake_network_np.nonzero(fine_wet)
    world_x = fine.origin_x_m + columns * fine.spacing_x_m
    world_z = fine.origin_z_m + rows * fine.spacing_z_m
    ranges = []
    for world, origin, spacing, fine_spacing, size in (
            (world_z, lake_inputs["origin_z_m"], lake_inputs["spacing_z_m"], fine.spacing_z_m, wet.shape[0]),
            (world_x, lake_inputs["origin_x_m"], lake_inputs["spacing_x_m"], fine.spacing_x_m, wet.shape[1])):
        radius = .5 * (spacing + fine_spacing)
        lower = _m4_surface_lake_network_np.clip(_m4_surface_lake_network_np.floor((world - radius - origin) / spacing).astype(_m4_surface_lake_network_np.int64) + 1, 0, size)
        upper = _m4_surface_lake_network_np.clip(_m4_surface_lake_network_np.ceil((world + radius - origin) / spacing).astype(_m4_surface_lake_network_np.int64), 0, size)
        ranges.append((lower, upper))
    prefix = _m4_surface_lake_network_np.pad(wet.astype(_m4_surface_lake_network_np.int64).cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))
    lower_z, upper_z = ranges[0]
    lower_x, upper_x = ranges[1]
    counts = prefix[upper_z, upper_x] - prefix[lower_z, upper_x] - prefix[upper_z, lower_x] + prefix[lower_z, lower_x]
    return int(_m4_surface_lake_network_np.count_nonzero(counts > 0))

# --- terrain_pipeline/surface_lake_network.py:234 ---
def evaluate_surface_lake_network(lake_inputs, plan, coarse_domain, coarse_protected,
                                  fine, outlet_stage_m, section_recipe, stage_recipe,
                                  inundation_recipe, budget, network_recipe, valley_recipe,
                                  reroute_recipe, recovery_recipe, seam,
                                  recipe=SurfaceLakeNetworkRecipe()):
    """Recompute original D8 discharge and real recovery gates per lake time step.

    outlet_stage_m is a finite full coarse-grid boundary-stage array; only
    active original-topology outlets are passed to recovery on each step.
    seam binds a strict lake-path node, world coordinates, vertical datum and
    both source identities. Origin/spacing/elevation equality is exact.
    Lake source and downstream source may differ, but must match these bindings.
    Inputs and diagnostic prefixes never authorize standalone publication.
    """
    from terrain_pipeline.surface_hydraulics import InundationRecipe as _m4_surface_lake_network_InundationRecipe
    from terrain_pipeline.surface_hydraulics import RerouteRecipe as _m4_surface_lake_network_RerouteRecipe
    from terrain_pipeline.surface_hydraulics import StageRecipe as _m4_surface_lake_network_StageRecipe
    from terrain_pipeline.channel_geometry import SectionRecipe as _m4_surface_lake_network_SectionRecipe
    from terrain_pipeline.channel_geometry import plan_channel as _m4_surface_lake_network_plan_channel
    from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _m4_surface_lake_network_NetworkValleyRecipe
    from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _m4_surface_lake_network_SurfaceNetworkBudget
    from terrain_pipeline.surface_domain import FineGrid as _m4_surface_lake_network_FineGrid
    from terrain_pipeline.surface_domain import RecoveryRecipe as _m4_surface_lake_network_RecoveryRecipe
    from terrain_pipeline.surface_domain import recover_surface_network as _m4_surface_lake_network_recover_surface_network
    from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _m4_surface_lake_network_ValleyGeometryRecipe
    expected_types = ((fine, _m4_surface_lake_network_FineGrid), (section_recipe, _m4_surface_lake_network_SectionRecipe),
                      (stage_recipe, _m4_surface_lake_network_StageRecipe), (inundation_recipe, _m4_surface_lake_network_InundationRecipe),
                      (budget, _m4_surface_lake_network_SurfaceNetworkBudget), (network_recipe, _m4_surface_lake_network_NetworkValleyRecipe),
                      (valley_recipe, _m4_surface_lake_network_ValleyGeometryRecipe), (reroute_recipe, _m4_surface_lake_network_RerouteRecipe),
                      (recovery_recipe, _m4_surface_lake_network_RecoveryRecipe), (seam, LakeRiverSeam),
                      (recipe, SurfaceLakeNetworkRecipe))
    if any(not isinstance(value, expected) for value, expected in expected_types):
        raise ValueError("explicit joint seam, fine grid and all recovery recipes required")
    if not isinstance(lake_inputs, dict) or not isinstance(lake_inputs.get("recipe"), LakeRoutingRecipe):
        raise ValueError("lake_inputs must be the explicit original evaluate_lake_routing keyword inputs")
    lake_shape = _m4_surface_lake_network_np.asarray(lake_inputs["height_m"]).shape
    downstream_shape = _m4_surface_lake_network_np.asarray(plan["arrays"]["source_height_m"]).shape
    steps_requested = len(lake_inputs["recipe"].inflow_m3_s)
    if (len(lake_shape) != 2 or len(downstream_shape) != 2 or
            _m4_surface_lake_network_math.prod(lake_shape) > recipe.max_lake_cells or
            _m4_surface_lake_network_math.prod(downstream_shape) > min(recipe.max_coarse_cells, recovery_recipe.max_coarse_cells) or
            _m4_surface_lake_network_math.prod(fine.shape_zx) > min(recipe.max_fine_cells, recovery_recipe.max_fine_cells) or
            steps_requested > recipe.max_steps):
        raise ValueError("joint input exceeds hard requested grid/step resource bounds before copying")
    full_lake_work = _m4_surface_lake_network_math.prod(lake_shape) * steps_requested
    if full_lake_work > recipe.max_total_lake_work:
        raise ValueError("initial independent lake trajectory exceeds aggregate lake-work bound")
    initial_retained_estimate = (_m4_surface_lake_network_math.prod(lake_shape) * 128 + _m4_surface_lake_network_math.prod(downstream_shape) * 1024 +
                                 _m4_surface_lake_network_math.prod(fine.shape_zx) * 32 + 65536)
    if initial_retained_estimate > recipe.max_retained_bytes:
        raise ValueError("joint initial diagnostic exceeds retained-byte bound before copying")
    original, channel, local = _validated_plan(plan)
    parameters = original["identity"]["parameters"]
    arrays = original["arrays"]
    domain = _m4_surface_lake_network_np.asarray(coarse_domain)
    protected = _m4_surface_lake_network_np.asarray(coarse_protected)
    outlet_stage = _m4_surface_lake_network_np.asarray(outlet_stage_m)
    if (any(mask.shape != downstream_shape or mask.dtype != bool for mask in (domain, protected)) or
            outlet_stage.shape != downstream_shape or outlet_stage.dtype.kind not in "fiu" or
            not _m4_surface_lake_network_np.isfinite(outlet_stage).all()):
        raise ValueError("matching explicit coarse masks and finite full-grid outlet stages required")
    if (seam.lake_source_identity != lake_inputs["source_identity"] or
            seam.downstream_source_identity != parameters["source_identity"] or
            seam.downstream_vertical_datum != lake_inputs["vertical_datum"]):
        raise ValueError("seam source provenance or vertical datum binding mismatch")
    if (lake_inputs["spacing_x_m"] != parameters["spacing_x_m"] or
            lake_inputs["spacing_z_m"] != parameters["spacing_z_m"]):
        raise ValueError("lake and downstream coarse spacing must explicitly agree")
    source = seam.lake_path_grid_zx
    path = _m4_surface_lake_network_np.asarray(lake_inputs["downstream_path_grid_zx"])
    if (path.ndim != 2 or path.shape[1] != 2 or not any(tuple(node) == source for node in path) or
            source == tuple(lake_inputs["legal_spill_grid_zx"])):
        raise ValueError("injection must be an explicit downstream lake-path node outside the spill")
    if (source[0] < 0 or source[0] >= lake_shape[0] or source[1] < 0 or source[1] >= lake_shape[1] or
            _m4_surface_lake_network_np.asarray(lake_inputs["basin_mask"])[source] or
            not _m4_surface_lake_network_np.asarray(lake_inputs["domain_mask"])[source] or
            _m4_surface_lake_network_np.asarray(lake_inputs["protected_mask"])[source]):
        raise ValueError("injection lake-path node conflicts with basin/domain/protection")
    lake_world_x = lake_inputs["origin_x_m"] + source[1] * lake_inputs["spacing_x_m"]
    lake_world_z = lake_inputs["origin_z_m"] + source[0] * lake_inputs["spacing_z_m"]
    if seam.world_x_m != lake_world_x or seam.world_z_m != lake_world_z:
        raise ValueError("seam world coordinates do not exactly match the lake-path node")
    source_row = _aligned_index(seam.world_z_m, parameters["origin_z_m"], parameters["spacing_z_m"], downstream_shape[0])
    source_column = _aligned_index(seam.world_x_m, parameters["origin_x_m"], parameters["spacing_x_m"], downstream_shape[1])
    injection = source_row * downstream_shape[1] + source_column
    if arrays["source_height_m"][source_row, source_column] != _m4_surface_lake_network_np.asarray(lake_inputs["height_m"])[source]:
        raise ValueError("seam source terrain elevation mismatch")
    fine_row = _aligned_index(seam.world_z_m, fine.origin_z_m, fine.spacing_z_m, fine.shape_zx[0])
    fine_column = _aligned_index(seam.world_x_m, fine.origin_x_m, fine.spacing_x_m, fine.shape_zx[1])
    lake = evaluate_lake_routing(**lake_inputs)
    recorded_lake = {name: _m4_surface_lake_network_asdict(value) if isinstance(value, LakeRoutingRecipe) else value
                     for name, value in lake_inputs.items()}
    inputs = dict(lake_inputs=recorded_lake, plan=original, coarse_domain=domain,
                  coarse_protected=protected, fine={name: getattr(fine, name) for name in _m4_surface_lake_network_FineGrid.__dataclass_fields__},
                  outlet_stage_m=outlet_stage,
                  section_recipe=_m4_surface_lake_network_asdict(section_recipe), stage_recipe=_m4_surface_lake_network_asdict(stage_recipe),
                  inundation_recipe=_m4_surface_lake_network_asdict(inundation_recipe), budget=_m4_surface_lake_network_asdict(budget),
                  network_recipe=_m4_surface_lake_network_asdict(network_recipe), valley_recipe=_m4_surface_lake_network_asdict(valley_recipe),
                  reroute_recipe=_m4_surface_lake_network_asdict(reroute_recipe), recovery_recipe=_m4_surface_lake_network_asdict(recovery_recipe),
                  seam=_m4_surface_lake_network_asdict(seam), recipe=_m4_surface_lake_network_asdict(recipe))
    trace = []
    ledgers = []
    attempts_used = 0
    fine_work_used = 0
    lake_work_used = full_lake_work
    diagnostic = dict(code="transfer_feasible", failed_step=None, evidence={})

    def fail(code, index=None, evidence=None):
        diagnostic.update(code=code, failed_step=index, evidence=evidence or {})

    def flow_tolerance(*values):
        return recipe.discharge_abs_tolerance_m3_s + recipe.discharge_rel_tolerance * max(abs(value) for value in values)

    if not lake["scenario_feasible"]:
        fail("lake_scenario_failed", evidence=lake["diagnostic"])
    elif (not domain[source_row, source_column] or protected[source_row, source_column] or
          not fine.domain_mask[fine_row, fine_column] or fine.protected_mask[fine_row, fine_column]):
        fail("seam_domain_or_protection")
    base_local_total = float(_m4_surface_lake_network_math.fsum(local))
    dt = lake_inputs["recipe"].dt_s
    spill_stage = float(_m4_surface_lake_network_np.asarray(lake_inputs["height_m"])[tuple(lake_inputs["legal_spill_grid_zx"])])
    if diagnostic["code"] == "transfer_feasible":
        for index in range(steps_requested):
            retained = _retained_bytes((inputs, lake, trace, ledgers))
            next_retained_estimate = (_m4_surface_lake_network_math.prod(fine.shape_zx) * 512 + _m4_surface_lake_network_math.prod(downstream_shape) * 4096 +
                                      _m4_surface_lake_network_math.prod(lake_shape) * 128 + 65536)
            if retained + next_retained_estimate > recipe.max_retained_bytes:
                fail("joint_retained_memory_exhausted", index,
                     dict(retained_bytes=retained, next_estimated_bytes=next_retained_estimate,
                          max_retained_bytes=recipe.max_retained_bytes))
                break
            replay_work = _m4_surface_lake_network_math.prod(lake_shape) * (index + 1)
            if lake_work_used + replay_work > recipe.max_total_lake_work:
                fail("joint_lake_work_exhausted", index, dict(lake_work_used=lake_work_used, next_work=replay_work))
                break
            prefix_recipe = _m4_surface_lake_network_replace(lake_inputs["recipe"],
                                    inflow_m3_s=lake_inputs["recipe"].inflow_m3_s[:index + 1],
                                    loss_m3_s=lake_inputs["recipe"].loss_m3_s[:index + 1])
            step_lake = evaluate_lake_routing(**dict(lake_inputs, recipe=prefix_recipe))
            lake_work_used += replay_work
            if (not step_lake["scenario_feasible"] or
                    not _m4_surface_lake_network_np.array_equal(step_lake["arrays"]["stage_m"], lake["arrays"]["stage_m"][:index + 2]) or
                    not _m4_surface_lake_network_np.array_equal(step_lake["arrays"]["storage_m3"], lake["arrays"]["storage_m3"][:index + 2])):
                fail("lake_prefix_replay_mismatch", index)
                break
            outflow = float(step_lake["arrays"]["step_outflow_m3_s"][-1])
            injected_local = local.copy()
            injected_local[injection] += outflow
            recomputed_discharge = _accumulate(injected_local, arrays)
            source_chain = dict(lake_identity_sha256=lake["identity_sha256"],
                                original_plan_sha256=original["identity_sha256"],
                                lake_source=seam.lake_source_identity,
                                downstream_source=seam.downstream_source_identity, step=index)
            step_plan = _m4_surface_lake_network_plan_channel(arrays["source_height_m"], arrays["receiver"], arrays["order"],
                                     arrays["outlet_mask"], recomputed_discharge.reshape(downstream_shape),
                                     parameters["spacing_x_m"], parameters["spacing_z_m"],
                                     parameters["origin_x_m"], parameters["origin_z_m"],
                                     parameters["sea_level_elevation_m"], network_json(source_chain), channel)
            step = dict(index=index, status="pending", lake_prefix_identity_sha256=step_lake["identity_sha256"],
                        lake_outflow_m3_s=outflow, original_local_inflow_m3_s=network_readonly(local.reshape(downstream_shape)),
                        injected_local_inflow_m3_s=network_readonly(injected_local.reshape(downstream_shape)),
                        recomputed_plan=step_plan, recovery=None, committed=False)
            trace.append(step)
            active = step_plan["arrays"]["channel_mask"]
            reachable = injection
            active_transfer = bool(active.flat[reachable])
            while active_transfer and arrays["receiver"][reachable] >= 0:
                reachable = int(arrays["receiver"][reachable])
                active_transfer = bool(active.flat[reachable])
            if outflow > 0 and (not active_transfer or arrays["receiver"][injection] < 0):
                step["status"] = "positive_outflow_without_active_path"
                fail(step["status"], index, dict(outflow_m3_s=outflow, original_start_threshold_m3_s=channel.start_discharge_m3_s))
                break
            if not active.any():
                if outflow != 0 or base_local_total != 0:
                    step["status"] = "positive_local_flow_without_activity"
                    fail(step["status"], index)
                    break
                step["status"] = "no_flow"
                river_outlet = 0.
            else:
                remaining_attempts = recipe.max_total_attempts - attempts_used
                remaining_fine = recipe.max_total_fine_work - fine_work_used
                if remaining_attempts < 1 or remaining_fine < _m4_surface_lake_network_math.prod(fine.shape_zx):
                    step["status"] = "joint_recovery_resource_exhausted"
                    fail(step["status"], index, dict(attempts_used=attempts_used, fine_work_used=fine_work_used))
                    break
                bounded_recovery = _m4_surface_lake_network_replace(recovery_recipe,
                    max_attempts=min(recovery_recipe.max_attempts, remaining_attempts),
                    max_total_fine_cells=min(recovery_recipe.max_total_fine_cells, remaining_fine))
                active_outlets = active & arrays["outlet_mask"]
                try:
                    recovered = _m4_surface_lake_network_recover_surface_network(step_plan, domain, protected, fine,
                        outlet_stage[active_outlets], section_recipe, stage_recipe, inundation_recipe,
                        budget, network_recipe, valley_recipe, reroute_recipe, bounded_recovery)
                except ValueError as error:
                    step["status"] = "downstream_input_gate_failed"
                    fail(step["status"], index, dict(reason=str(error)))
                    break
                attempts_used += len(recovered["attempts"])
                fine_work_used += recovered["summary"]["total_fine_cells_evaluated"]
                if _retained_bytes((inputs, lake, trace, ledgers, recovered)) > recipe.max_retained_bytes:
                    step["status"] = "joint_retained_memory_exhausted"
                    fail(step["status"], index, dict(max_retained_bytes=recipe.max_retained_bytes))
                    break
                step["recovery"] = recovered
                if not recovered["accepted"]:
                    step["status"] = "downstream_recovery_failed"
                    fail(step["status"], index, dict(recovery_status=recovered["status"], attempts=len(recovered["attempts"])))
                    break
                surface = recovered["surface"]["arrays"]
                if outflow > 0:
                    if (not recovered["final_plan"]["arrays"]["channel_mask"].flat[injection] or
                            not surface["wet_mask"][fine_row, fine_column]):
                        step["status"] = "injection_not_wet"
                        fail(step["status"], index)
                        break
                if surface["wet_mask"][fine_row, fine_column]:
                    injection_stage = float(surface["water_surface_m"][fine_row, fine_column])
                    step["injection_stage_m"] = injection_stage
                    if injection_stage >= spill_stage:
                        step["status"] = "spill_submerged_one_way_invalid"
                        fail(step["status"], index, dict(injection_stage_m=injection_stage, spill_stage_m=spill_stage))
                        break
                overlapping = _overlap(lake_inputs, step_lake["arrays"]["wet_mask"], fine, surface["wet_mask"])
                step["overlap_fine_cells"] = overlapping
                if overlapping:
                    step["status"] = "lake_river_wet_overlap"
                    fail(step["status"], index, dict(overlap_fine_cells=overlapping))
                    break
                final_arrays = recovered["final_plan"]["arrays"]
                river_outlet = float(_m4_surface_lake_network_math.fsum(final_arrays["discharge_m3_s"][final_arrays["outlet_mask"]]))
                step["status"] = "downstream_gates_passed"
            lake_change = float(lake["arrays"]["storage_m3"][index + 1] - lake["arrays"]["storage_m3"][index])
            lake_in = float(lake_inputs["recipe"].inflow_m3_s[index])
            loss = float(lake_inputs["recipe"].loss_m3_s[index])
            lake_residual = lake_change - dt * (lake_in - loss - outflow)
            river_residual = river_outlet - base_local_total - outflow
            combined = lake_change + dt * river_outlet - dt * (lake_in - loss + base_local_total)
            allowed_lake = (lake_inputs["recipe"].volume_abs_tolerance_m3 +
                lake_inputs["recipe"].volume_rel_tolerance * max(
                    lake["arrays"]["storage_m3"][index], lake["arrays"]["storage_m3"][index + 1],
                    dt * lake_in, dt * loss, dt * outflow))
            allowed_flow = flow_tolerance(river_outlet, base_local_total, outflow)
            if (abs(lake_residual) > allowed_lake + 1e-13 or abs(river_residual) > allowed_flow or
                    abs(combined) > allowed_lake + dt * allowed_flow + 1e-13):
                step["status"] = "combined_ledger_failed"
                fail(step["status"], index, dict(lake_residual_m3=lake_residual,
                                               downstream_residual_m3_s=river_residual,
                                               combined_residual_m3=combined))
                break
            ledgers.append(dict(step=index, dt_s=dt, lake_inflow_m3_s=lake_in, lake_loss_m3_s=loss,
                                lake_outflow_m3_s=outflow, downstream_local_total_m3_s=base_local_total,
                                downstream_outlet_m3_s=river_outlet, lake_storage_change_m3=lake_change,
                                lake_residual_m3=lake_residual, downstream_residual_m3_s=river_residual,
                                combined_residual_m3=combined,
                                combined_tolerance_m3=allowed_lake + dt * allowed_flow))
            step["committed"] = True
    committed = len(ledgers)
    committed_stage = float(lake["arrays"]["stage_m"][committed])
    basin = lake["arrays"]["basin_mask"]
    depth = _m4_surface_lake_network_np.where(basin, _m4_surface_lake_network_np.maximum(committed_stage - lake["arrays"]["height_m"], 0.), 0.)
    wet = depth > 0
    water = _m4_surface_lake_network_np.full(lake_shape, _m4_surface_lake_network_np.nan)
    water[wet] = committed_stage
    initial_storage = float(lake["arrays"]["storage_m3"][0])
    final_storage = float(lake["arrays"]["storage_m3"][committed])
    summary = dict(committed_steps=committed, requested_steps=steps_requested,
                   committed_final_lake_stage_m=committed_stage,
                   committed_initial_lake_storage_m3=initial_storage,
                   committed_final_lake_storage_m3=final_storage,
                   total_lake_inflow_m3=_m4_surface_lake_network_math.fsum(row["dt_s"] * row["lake_inflow_m3_s"] for row in ledgers),
                   total_lake_loss_m3=_m4_surface_lake_network_math.fsum(row["dt_s"] * row["lake_loss_m3_s"] for row in ledgers),
                   total_lake_outflow_m3=_m4_surface_lake_network_math.fsum(row["dt_s"] * row["lake_outflow_m3_s"] for row in ledgers),
                   total_downstream_local_m3=_m4_surface_lake_network_math.fsum(row["dt_s"] * row["downstream_local_total_m3_s"] for row in ledgers),
                   total_downstream_outlet_m3=_m4_surface_lake_network_math.fsum(row["dt_s"] * row["downstream_outlet_m3_s"] for row in ledgers),
                   total_combined_residual_m3=_m4_surface_lake_network_math.fsum(row["combined_residual_m3"] for row in ledgers),
                   total_combined_tolerance_m3=_m4_surface_lake_network_math.fsum(row["combined_tolerance_m3"] for row in ledgers),
                   total_attempts=attempts_used, total_fine_work=fine_work_used,
                   total_lake_work=lake_work_used, limitation=NETWORK_LIMITATION,
                   connector_geometry_generated=False, river_storage_or_propagation_modeled=False)
    aggregate = _m4_surface_lake_network_math.fsum((final_storage, -initial_storage, summary["total_downstream_outlet_m3"],
                          -summary["total_lake_inflow_m3"], summary["total_lake_loss_m3"],
                          -summary["total_downstream_local_m3"]))
    summary["aggregate_combined_residual_m3"] = aggregate
    if (diagnostic["code"] == "transfer_feasible" and
            abs(aggregate) > summary["total_combined_tolerance_m3"] + 1e-12):
        fail("aggregate_ledger_failed", evidence=dict(residual_m3=aggregate))
    result = dict(algorithm_version=NETWORK_VERSION, format_version=NETWORK_FORMAT_VERSION, status=NETWORK_STATUS,
                   transfer_feasible=diagnostic["code"] == "transfer_feasible", inputs=inputs,
                   independent_lake_diagnostic=lake, trace=trace, ledger=ledgers,
                   committed_lake_arrays=dict(stage_m=lake["arrays"]["stage_m"][:committed + 1],
                       storage_m3=lake["arrays"]["storage_m3"][:committed + 1],
                       wet_mask=wet, water_depth_m=depth, water_surface_m=water),
                   diagnostic=diagnostic, summary=summary)
    retained = _retained_bytes(result)
    if retained > recipe.max_retained_bytes:
        raise ValueError("joint final diagnostic exceeds retained-byte bound before freezing")
    summary["retained_bytes_before_freeze"] = retained
    result = network_freeze(result)
    result["identity_sha256"] = surface_lake_network_hash(result)
    return result

# --- terrain_pipeline/surface_lake_network.py:527 ---
def validate_surface_lake_network(result):
    """Replay both the lake and every downstream preparation, including failures."""
    from terrain_pipeline.surface_hydraulics import InundationRecipe as _m4_surface_lake_network_InundationRecipe
    from terrain_pipeline.surface_hydraulics import RerouteRecipe as _m4_surface_lake_network_RerouteRecipe
    from terrain_pipeline.surface_hydraulics import StageRecipe as _m4_surface_lake_network_StageRecipe
    from terrain_pipeline.channel_geometry import SectionRecipe as _m4_surface_lake_network_SectionRecipe
    from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _m4_surface_lake_network_NetworkValleyRecipe
    from terrain_pipeline.surface_domain import SurfaceNetworkBudget as _m4_surface_lake_network_SurfaceNetworkBudget
    from terrain_pipeline.surface_domain import FineGrid as _m4_surface_lake_network_FineGrid
    from terrain_pipeline.surface_domain import RecoveryRecipe as _m4_surface_lake_network_RecoveryRecipe
    from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _m4_surface_lake_network_ValleyGeometryRecipe
    try:
        if (result["algorithm_version"] != NETWORK_VERSION or result["format_version"] != NETWORK_FORMAT_VERSION or
                result["status"] != NETWORK_STATUS or type(result["transfer_feasible"]) is not bool or
                result["identity_sha256"] != surface_lake_network_hash(result)):
            raise ValueError("joint integrity or nonpublication status mismatch")
        inputs = dict(result["inputs"])
        lake_inputs = dict(inputs["lake_inputs"])
        lake_inputs["recipe"] = LakeRoutingRecipe(**lake_inputs["recipe"])
        inputs["lake_inputs"] = lake_inputs
        classes = dict(fine=_m4_surface_lake_network_FineGrid, section_recipe=_m4_surface_lake_network_SectionRecipe, stage_recipe=_m4_surface_lake_network_StageRecipe,
                       inundation_recipe=_m4_surface_lake_network_InundationRecipe, budget=_m4_surface_lake_network_SurfaceNetworkBudget,
                       network_recipe=_m4_surface_lake_network_NetworkValleyRecipe, valley_recipe=_m4_surface_lake_network_ValleyGeometryRecipe,
                       reroute_recipe=_m4_surface_lake_network_RerouteRecipe, recovery_recipe=_m4_surface_lake_network_RecoveryRecipe,
                       seam=LakeRiverSeam, recipe=SurfaceLakeNetworkRecipe)
        for name, constructor in classes.items():
            inputs[name] = constructor(**inputs[name])
        replay = evaluate_surface_lake_network(**inputs)
        if network_json(network_tree(result, {})) != network_json(network_tree(replay, {})):
            raise ValueError("joint semantic replay mismatch")
        return replay
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
        raise ValueError("malformed joint diagnostic") from error

# --- terrain_pipeline/surface_lake_network.py:553 ---
def network_unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate joint JSON key")
        result[name] = value
    return result

# --- terrain_pipeline/surface_lake_network.py:562 ---
def network_reject_constant(value):
    raise ValueError(f"nonfinite joint JSON value: {value}")

# --- terrain_pipeline/surface_lake_network.py:566 ---
def network_preflight(handle):
    if _m4_surface_lake_network_os.fstat(handle.fileno()).st_size > NETWORK_MAX_ARCHIVE_BYTES:
        raise ValueError("joint compressed archive exceeds byte ceiling")
    with _m4_surface_lake_network_zipfile.ZipFile(handle) as archive:
        members = archive.infolist()
        names = {entry.filename for entry in members}
        if (len(members) > MAX_MEMBERS or len(names) != len(members) or "manifest.npy" not in names or
                sum(entry.file_size for entry in members) > NETWORK_MAX_ARCHIVE_BYTES):
            raise ValueError("joint member count or expanded byte ceiling exceeded")
        for entry in members:
            if (not entry.filename.endswith(".npy") or "/" in entry.filename or
                    entry.flag_bits & 1):
                raise ValueError("invalid joint archive member")
            if entry.filename != "manifest.npy" and (
                    not entry.filename.startswith("array_") or len(entry.filename) != 74):
                raise ValueError("unexpected joint array member name")
            with archive.open(entry) as member:
                version = _m4_surface_lake_network_np.lib.format.read_magic(member)
                if version == (1, 0):
                    shape, fortran_order, dtype = _m4_surface_lake_network_np.lib.format.read_array_header_1_0(member)
                elif version == (2, 0):
                    shape, fortran_order, dtype = _m4_surface_lake_network_np.lib.format.read_array_header_2_0(member)
                else:
                    raise ValueError("unsupported joint NPY header")
                byte_count = _m4_surface_lake_network_math.prod(shape) * dtype.itemsize
                if (dtype.hasobject or fortran_order or len(shape) > 2 or
                        member.tell() + byte_count != entry.file_size or byte_count > NETWORK_MAX_ARCHIVE_BYTES):
                    raise ValueError("joint array header exceeds bounded payload")
                if entry.filename == "manifest.npy":
                    if shape != () or dtype.kind != "U" or entry.file_size > NETWORK_MAX_METADATA_BYTES:
                        raise ValueError("joint manifest exceeds scalar metadata bounds")
                elif dtype.kind not in "bifu" or _m4_surface_lake_network_math.prod(shape) > 2000000:
                    raise ValueError("joint array type or count exceeds hard bound")
    handle.seek(0)

# --- terrain_pipeline/surface_lake_network.py:602 ---
def save_surface_lake_network(result, destination):
    """Atomically create a replay-validated self-contained diagnostic, never replace."""
    destination = _m4_surface_lake_network_Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    if destination.suffix != ".npz":
        raise ValueError("joint diagnostic requires .npz destination")
    validated = validate_surface_lake_network(result)
    arrays = {}
    tree = network_tree(validated, arrays)
    manifest = network_json(dict(format_version=NETWORK_FORMAT_VERSION, tree=tree,
                          tree_sha256=_m4_surface_lake_network_hashlib.sha256(network_json(tree).encode("utf-8")).hexdigest()))
    if len(manifest) * 4 + 256 > NETWORK_MAX_METADATA_BYTES or len(arrays) + 1 > MAX_MEMBERS:
        raise ValueError("joint diagnostic manifest exceeds archive resource ceiling")
    retained_ceiling = validated["inputs"]["recipe"]["max_retained_bytes"]
    archive_estimate = sum(array.nbytes + 256 for array in arrays.values()) + len(manifest) * 4 + 256
    if archive_estimate > min(NETWORK_MAX_ARCHIVE_BYTES, retained_ceiling):
        raise ValueError("joint deduplicated payload exceeds byte ceiling before compression")
    descriptor, temporary = _m4_surface_lake_network_tempfile.mkstemp(prefix=".surface-lake-", suffix=".tmp", dir=destination.parent)
    try:
        with _m4_surface_lake_network_os.fdopen(descriptor, "wb") as handle:
            _m4_surface_lake_network_np.savez_compressed(handle, manifest=_m4_surface_lake_network_np.asarray(manifest), **arrays)
            handle.flush()
            _m4_surface_lake_network_os.fsync(handle.fileno())
        with open(temporary, "rb") as handle:
            network_preflight(handle)
        _m4_surface_lake_network_os.link(temporary, destination)
    finally:
        _m4_surface_lake_network_os.unlink(temporary)
    return destination

# --- terrain_pipeline/surface_lake_network.py:634 ---
def load_surface_lake_network(source):
    """Bound ZIP and NPY before allocation, enforce exact arrays, then semantic replay."""
    try:
        with open(source, "rb") as handle:
            network_preflight(handle)
            with _m4_surface_lake_network_np.load(handle, allow_pickle=False) as archive:
                manifest = _m4_surface_lake_network_json.loads(str(archive["manifest"].item()), object_pairs_hook=network_unique_object,
                                      parse_constant=network_reject_constant)
                if (set(manifest) != {"format_version", "tree", "tree_sha256"} or
                        manifest["format_version"] != NETWORK_FORMAT_VERSION or
                        _m4_surface_lake_network_hashlib.sha256(network_json(manifest["tree"]).encode("utf-8")).hexdigest() != manifest["tree_sha256"]):
                    raise ValueError("joint manifest integrity mismatch")
                used = {"manifest"}
                cache = {}

                def decode(value):
                    if isinstance(value, dict) and "$array" in value:
                        if set(value) != {"$array", "dtype", "shape", "sha256"}:
                            raise ValueError("malformed joint array reference")
                        name = value["$array"]
                        if name not in archive.files or name != "array_" + value["sha256"]:
                            raise ValueError("missing joint array binding")
                        used.add(name)
                        if name not in cache:
                            cache[name] = network_readonly(archive[name])
                        array = cache[name]
                        if (array.dtype.str != value["dtype"] or list(array.shape) != value["shape"] or
                                network_array_hash(array) != value["sha256"]):
                            raise ValueError("joint array integrity mismatch")
                        return array
                    if isinstance(value, dict):
                        return {name: decode(child) for name, child in value.items()}
                    if isinstance(value, list):
                        return [decode(child) for child in value]
                    return value

                result = decode(manifest["tree"])
                if used != set(archive.files):
                    raise ValueError("unexpected joint archive arrays")
            return validate_surface_lake_network(result)
    except (OSError, EOFError, KeyError, TypeError, AttributeError, RecursionError,
            _m4_surface_lake_network_zipfile.BadZipFile, _m4_surface_lake_network_json.JSONDecodeError) as error:
        raise ValueError("invalid joint diagnostic archive") from error

# --- terrain_pipeline/lake_river_connector.py:26 ---
CONNECTOR_VERSION = "lake-river-connector-v1"

# --- terrain_pipeline/lake_river_connector.py:27 ---
MAX_BYTES = 64 * 1024 * 1024

# --- terrain_pipeline/lake_river_connector.py:28 ---
MAX_CELLS = 250000

# --- terrain_pipeline/lake_river_connector.py:29 ---
TOL = 1e-9

# --- terrain_pipeline/lake_river_connector.py:30 ---
CONNECTOR_LIMITATION = (
    "Engineering quasi-steady geometry only; no rating-curve modification, "
    "dynamic or backwater solver, free-fall velocity, river storage or propagation. "
    "No additional injection or lake storage. The source joint remains "
    "diagnostic_not_publishable; this does not publish the whole surface system. "
    "Tailwater >= spill is rejected under the current engineering contract."
)

# --- terrain_pipeline/lake_river_connector.py:39 ---
def connector_number(value, name, positive=False):
    if (isinstance(value, (bool, _m4_lake_river_connector_np.bool_)) or not isinstance(value, (int, float, _m4_lake_river_connector_np.number))
            or not _m4_lake_river_connector_math.isfinite(value) or (positive and value <= 0)):
        raise ValueError(f"invalid finite metre/resource parameter: {name}")

# --- terrain_pipeline/lake_river_connector.py:45 ---
def connector_freeze(value):
    if isinstance(value, _m4_lake_river_connector_np.ndarray):
        contiguous = _m4_lake_river_connector_np.ascontiguousarray(value)
        return _m4_lake_river_connector_np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)
    if isinstance(value, _m4_lake_river_connector_Mapping):
        return _m4_lake_river_connector_MappingProxyType({name: connector_freeze(child) for name, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(connector_freeze(child) for child in value)
    if isinstance(value, _m4_lake_river_connector_np.generic):
        return value.item()
    return value

# --- terrain_pipeline/lake_river_connector.py:58 ---
def _thaw(value):
    if isinstance(value, _m4_lake_river_connector_Mapping):
        return {name: _thaw(child) for name, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(child) for child in value]
    return value

# --- terrain_pipeline/lake_river_connector.py:66 ---
def connector_json(value):
    return _m4_lake_river_connector_json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

# --- terrain_pipeline/lake_river_connector.py:70 ---
def connector_array_hash(array):
    digest = _m4_lake_river_connector_hashlib.sha256(array.dtype.str.encode("ascii"))
    digest.update(connector_json(list(array.shape)).encode("ascii"))
    digest.update(_m4_lake_river_connector_np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()

# --- terrain_pipeline/lake_river_connector.py:77 ---
def connector_tree(value, arrays):
    if isinstance(value, _m4_lake_river_connector_np.ndarray):
        identity = connector_array_hash(value)
        name = "array_" + identity
        arrays[name] = value
        return {"$array": name, "dtype": value.dtype.str, "shape": list(value.shape), "sha256": identity}
    if isinstance(value, _m4_lake_river_connector_Mapping):
        return {name: connector_tree(child, arrays) for name, child in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [connector_tree(child, arrays) for child in value]
    if isinstance(value, _m4_lake_river_connector_np.generic):
        return value.item()
    return value

# --- terrain_pipeline/lake_river_connector.py:92 ---
def lake_river_connector_hash(result):
    """Integrity digest, not a semantic certificate or issuer signature."""
    payload = {name: value for name, value in result.items() if name != "identity_sha256"}
    return _m4_lake_river_connector_hashlib.sha256(connector_json(connector_tree(payload, {})).encode("utf-8")).hexdigest()

# --- terrain_pipeline/lake_river_connector.py:99 ---
@_m4_lake_river_connector_dataclass(frozen=True)
class ConnectorCorridor:
    surface_m: _m4_lake_river_connector_np.ndarray
    valid_mask: _m4_lake_river_connector_np.ndarray
    domain_mask: _m4_lake_river_connector_np.ndarray
    protected_mask: _m4_lake_river_connector_np.ndarray
    origin_x_m: float
    origin_z_m: float
    spacing_x_m: float
    spacing_z_m: float
    vertical_datum: str
    source_identity: str

    def __post_init__(self):
        for name in ("origin_x_m", "origin_z_m", "spacing_x_m", "spacing_z_m"):
            connector_number(getattr(self, name), name, name.startswith("spacing"))
        for name in ("vertical_datum", "source_identity"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError("explicit corridor datum/source required")
        surface = _m4_lake_river_connector_np.asarray(self.surface_m)
        if (surface.ndim != 2 or min(surface.shape) < 2 or surface.size > MAX_CELLS
                or surface.dtype.kind not in "fiu"):
            raise ValueError("bounded 2D numeric corridor required")
        for name in ("valid_mask", "domain_mask", "protected_mask"):
            mask = _m4_lake_river_connector_np.asarray(getattr(self, name))
            if mask.dtype != bool or mask.shape != surface.shape:
                raise ValueError("matching explicit boolean corridor masks required")
            object.__setattr__(self, name, connector_freeze(mask))
        if _m4_lake_river_connector_np.isinf(surface).any() or not _m4_lake_river_connector_np.isfinite(surface[self.valid_mask]).all():
            raise ValueError("valid source terrain must be finite; unknown may be NaN")
        object.__setattr__(self, "surface_m", connector_freeze(surface.astype(_m4_lake_river_connector_np.float64)))

# --- terrain_pipeline/lake_river_connector.py:132 ---
@_m4_lake_river_connector_dataclass(frozen=True)
class ConnectorRecipe:
    path_xz_m: tuple
    width_m: tuple
    spill_vertex: int
    max_station_spacing_m: float = .02
    min_width_cells: float = 2.
    min_depth_m: float = .01
    max_depth_m: float = 4.
    max_cut_m: float = .6
    max_cut_volume_m3: float = .1
    max_changed_area_m2: float = .1
    max_stations: int = 2048
    max_triangles: int = 8192
    max_support_tests: int = 200000
    max_retained_bytes: int = MAX_BYTES

    def __post_init__(self):
        path = _m4_lake_river_connector_np.asarray(self.path_xz_m)
        if (path.ndim != 2 or path.shape[1] != 2 or not 3 <= len(path) <= 64
                or path.dtype.kind not in "fiu" or not _m4_lake_river_connector_np.isfinite(path).all()
                or _m4_lake_river_connector_np.any(_m4_lake_river_connector_np.linalg.norm(_m4_lake_river_connector_np.diff(path, axis=0), axis=1) <= 0)):
            raise ValueError("explicit finite nondegenerate bounded metric path required")
        if type(self.spill_vertex) is not int or not 0 < self.spill_vertex < len(path) - 1:
            raise ValueError("spill must be an interior path vertex")
        widths = tuple(self.width_m)
        if len(widths) != len(path):
            raise ValueError("one explicit width per path vertex required")
        for width in widths:
            connector_number(width, "width_m", True)
        for name in ("max_station_spacing_m", "min_width_cells", "min_depth_m", "max_depth_m"):
            connector_number(getattr(self, name), name, True)
        if self.min_width_cells < 2 or self.max_depth_m < self.min_depth_m:
            raise ValueError("at least two source intervals across width and ordered depth bounds required")
        for name in ("max_cut_m", "max_cut_volume_m3", "max_changed_area_m2"):
            connector_number(getattr(self, name), name)
            if getattr(self, name) < 0:
                raise ValueError("nonnegative construction budgets required")
        for name, ceiling in (("max_stations", 4096), ("max_triangles", 16384),
                              ("max_support_tests", 1000000), ("max_retained_bytes", MAX_BYTES)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError("invalid bounded connector resource: " + name)
        object.__setattr__(self, "path_xz_m", tuple(tuple(float(value) for value in point) for point in path))
        object.__setattr__(self, "width_m", tuple(float(value) for value in widths))

# --- terrain_pipeline/lake_river_connector.py:178 ---
class _Gate(Exception):
    def __init__(self, code, **evidence):
        self.code = code
        self.evidence = evidence

# --- terrain_pipeline/lake_river_connector.py:184 ---
def _grid(corridor):
    return dict(origin_x_m=corridor.origin_x_m, origin_z_m=corridor.origin_z_m,
                spacing_x_m=corridor.spacing_x_m, spacing_z_m=corridor.spacing_z_m)

# --- terrain_pipeline/lake_river_connector.py:189 ---
def _support(point, grid, shape):
    column = (point[0] - grid["origin_x_m"]) / grid["spacing_x_m"]
    row = (point[1] - grid["origin_z_m"]) / grid["spacing_z_m"]
    if column < -TOL or row < -TOL or column > shape[1] - 1 + TOL or row > shape[0] - 1 + TOL:
        raise _Gate("outside_source_support", point_xz_m=list(point))
    column = min(max(column, 0.), shape[1] - 1.)
    row = min(max(row, 0.), shape[0] - 1.)
    left = min(int(_m4_lake_river_connector_math.floor(column)), shape[1] - 2)
    top = min(int(_m4_lake_river_connector_math.floor(row)), shape[0] - 2)
    dx, dz = column - left, row - top
    if dz <= dx:
        return ((top, left), (top, left + 1), (top + 1, left + 1)), _m4_lake_river_connector_np.array([1 - dx, dx - dz, dz])
    return ((top, left), (top + 1, left + 1), (top + 1, left)), _m4_lake_river_connector_np.array([1 - dz, dx, dz - dx])

# --- terrain_pipeline/lake_river_connector.py:204 ---
def _sample(point, grid, surface, valid, domain, protected, wet=None):
    indices, weights = _support(point, grid, surface.shape)
    for index in indices:
        if not valid[index] or not _m4_lake_river_connector_np.isfinite(surface[index]):
            raise _Gate("unknown_support", grid_zx=list(index))
        if not domain[index]:
            raise _Gate("domain_support", grid_zx=list(index))
        if protected[index]:
            raise _Gate("protected_support", grid_zx=list(index))
        if wet is not None and not wet[index]:
            raise _Gate("dry_splice_support", grid_zx=list(index))
    return float(sum(weight * surface[index] for index, weight in zip(indices, weights)))

# --- terrain_pipeline/lake_river_connector.py:218 ---
def _cross(first, second):
    return float(first[0] * second[1] - first[1] * second[0])

# --- terrain_pipeline/lake_river_connector.py:222 ---
def _clip(polygon, triangle):
    output = [_m4_lake_river_connector_np.asarray(point, dtype=float) for point in polygon]
    for first, second in zip(triangle, _m4_lake_river_connector_np.roll(triangle, -1, axis=0)):
        previous = output
        output = []
        if not previous:
            break
        for begin, end in zip(previous, previous[1:] + previous[:1]):
            begin_side = _cross(second - first, begin - first)
            end_side = _cross(second - first, end - first)
            if begin_side >= 0:
                output.append(begin)
            if (begin_side < 0) != (end_side < 0):
                output.append(begin + (end - begin) * begin_side / (begin_side - end_side))
    return output

# --- terrain_pipeline/lake_river_connector.py:239 ---
def _area(polygon):
    if len(polygon) < 3:
        return 0.
    return abs(sum(_cross(point - polygon[0], following - polygon[0])
                   for point, following in zip(polygon[1:-1], polygon[2:]))) / 2

# --- terrain_pipeline/lake_river_connector.py:246 ---
def _plane_values(points, triangle, heights):
    coefficients = _m4_lake_river_connector_np.linalg.solve(_m4_lake_river_connector_np.column_stack((triangle, _m4_lake_river_connector_np.ones(3))), heights)
    return _m4_lake_river_connector_np.column_stack((points, _m4_lake_river_connector_np.ones(len(points)))) @ coefficients

# --- terrain_pipeline/lake_river_connector.py:251 ---
def _source_facets(triangle, grid, shape):
    minimum = triangle.min(axis=0)
    maximum = triangle.max(axis=0)
    origin = _m4_lake_river_connector_np.array([grid["origin_x_m"], grid["origin_z_m"]])
    spacing = _m4_lake_river_connector_np.array([grid["spacing_x_m"], grid["spacing_z_m"]])
    lower = _m4_lake_river_connector_np.floor((minimum - origin) / spacing).astype(int)
    upper = _m4_lake_river_connector_np.floor((maximum - origin) / spacing).astype(int)
    if _m4_lake_river_connector_np.any(minimum < origin - TOL) or _m4_lake_river_connector_np.any(maximum > origin + spacing * (_m4_lake_river_connector_np.array(shape[::-1]) - 1) + TOL):
        raise _Gate("outside_source_support")
    for row in range(max(0, lower[1]), min(shape[0] - 2, upper[1]) + 1):
        for column in range(max(0, lower[0]), min(shape[1] - 2, upper[0]) + 1):
            for indices in (((row, column), (row, column + 1), (row + 1, column + 1)),
                            ((row, column), (row + 1, column + 1), (row + 1, column))):
                facet = _m4_lake_river_connector_np.array([origin + spacing * _m4_lake_river_connector_np.array([index[1], index[0]]) for index in indices])
                yield indices, facet

# --- terrain_pipeline/lake_river_connector.py:268 ---
def _stations(recipe):
    path = _m4_lake_river_connector_np.asarray(recipe.path_xz_m)
    points, widths, distance, spill = [], [], [], None
    total = 0.
    for segment, (first, second) in enumerate(zip(path[:-1], path[1:])):
        length = float(_m4_lake_river_connector_np.linalg.norm(second - first))
        count = _m4_lake_river_connector_math.ceil(length / recipe.max_station_spacing_m - TOL)
        if len(points) + count + 1 > recipe.max_stations:
            raise _Gate("station_resource_exhausted")
        for offset in range(count):
            fraction = offset / count
            points.append(first + fraction * (second - first))
            widths.append(recipe.width_m[segment] * (1 - fraction) + recipe.width_m[segment + 1] * fraction)
            distance.append(total + fraction * length)
        if segment + 1 == recipe.spill_vertex:
            spill = len(points)
        total += length
    points.append(path[-1])
    widths.append(recipe.width_m[-1])
    distance.append(total)
    return _m4_lake_river_connector_np.asarray(points), _m4_lake_river_connector_np.asarray(widths), _m4_lake_river_connector_np.asarray(distance), spill

# --- terrain_pipeline/lake_river_connector.py:291 ---
def _path_crossing(path):
    for first in range(len(path) - 1):
        for second in range(first + 2, len(path) - 1):
            start, end = path[first:first + 2]
            other_start, other_end = path[second:second + 2]
            direction, other_direction = end - start, other_end - other_start
            denominator = _cross(direction, other_direction)
            if abs(denominator) < TOL:
                if abs(_cross(other_start - start, direction)) < TOL:
                    fractions = [_m4_lake_river_connector_np.dot(point - start, direction) / _m4_lake_river_connector_np.dot(direction, direction)
                                 for point in (other_start, other_end)]
                    if max(min(fractions), 0) <= min(max(fractions), 1):
                        raise _Gate("path_selfintersection")
            else:
                fraction = _cross(other_start - start, other_direction) / denominator
                other_fraction = _cross(other_start - start, direction) / denominator
                if 0 <= fraction <= 1 and 0 <= other_fraction <= 1:
                    raise _Gate("path_selfintersection")

# --- terrain_pipeline/lake_river_connector.py:311 ---
def _corridor_input(corridor):
    return {name: getattr(corridor, name) for name in ConnectorCorridor.__dataclass_fields__}

# --- terrain_pipeline/lake_river_connector.py:315 ---
def _recipe_input(recipe):
    return {name: getattr(recipe, name) for name in ConnectorRecipe.__dataclass_fields__}

# --- terrain_pipeline/lake_river_connector.py:319 ---
def _input_gate(joint, corridor, recipe):
    lake = joint["inputs"]["lake_inputs"]
    seam = joint["inputs"]["seam"]
    spill_index = tuple(lake["legal_spill_grid_zx"])
    spill = (lake["origin_x_m"] + spill_index[1] * lake["spacing_x_m"],
             lake["origin_z_m"] + spill_index[0] * lake["spacing_z_m"])
    if corridor.vertical_datum != lake["vertical_datum"] or corridor.vertical_datum != seam["downstream_vertical_datum"]:
        raise ValueError("connector datum mismatch")
    if tuple(recipe.path_xz_m[recipe.spill_vertex]) != spill:
        raise ValueError("path must pass through the actual legal spill exactly")
    if tuple(recipe.path_xz_m[-1]) != (seam["world_x_m"], seam["world_z_m"]):
        raise ValueError("path must terminate at the actual fine injection exactly")
    arrays = {}
    tree = connector_tree(dict(source_joint=joint, corridor=_corridor_input(corridor), recipe=_recipe_input(recipe)), arrays)
    if sum(array.nbytes + 256 for array in arrays.values()) + len(connector_json(tree).encode("utf-8")) * 4 > recipe.max_retained_bytes:
        raise ValueError("connector input retained byte ceiling")

# --- terrain_pipeline/lake_river_connector.py:337 ---
def _ribbon_gate(vertices, triangles, recipe, counter):
    if len(triangles) > recipe.max_triangles:
        raise _Gate("triangle_resource_exhausted")
    for indices in triangles:
        if _cross(vertices[indices[1], :2] - vertices[indices[0], :2],
                  vertices[indices[2], :2] - vertices[indices[0], :2]) <= 0:
            raise _Gate("degenerate_or_folded_ribbon")
    minimum = vertices[triangles, :2].min(axis=1)
    maximum = vertices[triangles, :2].max(axis=1)
    order = _m4_lake_river_connector_np.argsort(minimum[:, 0], kind="stable")
    for position, index in enumerate(order):
        for other in order[position + 1:]:
            if minimum[other, 0] >= maximum[index, 0]:
                break
            counter[0] += 1
            if counter[0] > recipe.max_support_tests:
                raise _Gate("support_resource_exhausted", support_tests=counter[0])
            if maximum[index, 1] <= minimum[other, 1] or maximum[other, 1] <= minimum[index, 1]:
                continue
            if _area(_clip(vertices[triangles[index], :2], vertices[triangles[other], :2])) > TOL * TOL:
                raise _Gate("ribbon_selfintersection")

# --- terrain_pipeline/lake_river_connector.py:360 ---
def _geometry_gate(joint, corridor, recipe, step, widths):
    lake = joint["inputs"]["lake_inputs"]
    spill_stage = float(lake["height_m"][tuple(lake["legal_spill_grid_zx"])])
    if step["injection_stage_m"] >= spill_stage:
        raise _Gate("tailwater_at_or_above_spill")
    _path_crossing(_m4_lake_river_connector_np.asarray(recipe.path_xz_m))
    if widths.min() + TOL < recipe.min_width_cells * max(corridor.spacing_x_m, corridor.spacing_z_m):
        raise _Gate("width_resolution_failed")
    if recipe.max_station_spacing_m > min(corridor.spacing_x_m, corridor.spacing_z_m) * 2:
        raise _Gate("longitudinal_resolution_failed")

# --- terrain_pipeline/lake_river_connector.py:372 ---
def _splice_gate(points, bed, water, binding):
    for prefix, cross_section, heights in (("lake", points[0], bed[0]), ("river", points[-1], bed[-1])):
        samples = binding[prefix + "_xz_m"]
        direction = cross_section[-1] - cross_section[0]
        fractions = (samples - cross_section[0]) @ direction / _m4_lake_river_connector_np.dot(direction, direction)
        expected_bed = _m4_lake_river_connector_np.interp(fractions, (0., .5, 1.), heights)
        expected_water = _m4_lake_river_connector_np.interp(fractions, (0., .5, 1.), water[0 if prefix == "lake" else -1])
        if (not _m4_lake_river_connector_np.allclose(expected_bed, binding[prefix + "_bed_m"], rtol=0, atol=TOL)
                or not _m4_lake_river_connector_np.allclose(expected_water, binding[prefix + "_water_m"], rtol=0, atol=TOL)):
            raise _Gate("full_cross_section_splice_mismatch")

# --- terrain_pipeline/lake_river_connector.py:384 ---
def _positive_polygon(points, values):
    output = []
    for begin, end, first, second in zip(points, _m4_lake_river_connector_np.roll(points, -1, axis=0), values, _m4_lake_river_connector_np.roll(values, -1)):
        if first > 0:
            output.append(begin)
        if (first > 0) != (second > 0):
            output.append(begin + (end - begin) * first / (first - second))
    return _m4_lake_river_connector_np.asarray(output)

# --- terrain_pipeline/lake_river_connector.py:394 ---
def _integral(points, triangle, values):
    positive = _positive_polygon(_m4_lake_river_connector_np.asarray(points), _plane_values(points, triangle, values))
    volume, area = 0., 0.
    if len(positive) >= 3:
        for index in range(1, len(positive) - 1):
            piece = positive[[0, index, index + 1]]
            piece_area = _area(piece)
            volume += piece_area * float(_m4_lake_river_connector_np.mean(_plane_values(piece, triangle, values)))
            area += piece_area
    return volume, area

# --- terrain_pipeline/lake_river_connector.py:406 ---
def _line_proof(first, second, grid, surface, valid, domain, protected, wet=None):
    _sample(first, grid, surface, valid, domain, protected, wet)
    _sample(second, grid, surface, valid, domain, protected, wet)
    fractions = {0., 1.}
    for axis, origin_name, spacing_name in ((0, "origin_x_m", "spacing_x_m"),
                                            (1, "origin_z_m", "spacing_z_m")):
        delta = second[axis] - first[axis]
        if delta != 0:
            lower, upper = sorted((first[axis], second[axis]))
            for node in range(_m4_lake_river_connector_math.floor((lower - grid[origin_name]) / grid[spacing_name]),
                              _m4_lake_river_connector_math.ceil((upper - grid[origin_name]) / grid[spacing_name]) + 1):
                fraction = (grid[origin_name] + node * grid[spacing_name] - first[axis]) / delta
                if 0 < fraction < 1:
                    fractions.add(float(fraction))
    ordered = sorted(fractions)
    for begin, end in zip(ordered[:-1], ordered[1:]):
        midpoint = first + (second - first) * ((begin + end) / 2)
        indices, weights = _support(midpoint, grid, surface.shape)
        left = min(index[1] for index in indices)
        top = min(index[0] for index in indices)
        start_dx = (first[0] - grid["origin_x_m"]) / grid["spacing_x_m"] - left
        start_dz = (first[1] - grid["origin_z_m"]) / grid["spacing_z_m"] - top
        slope = (second[0] - first[0]) / grid["spacing_x_m"] - (second[1] - first[1]) / grid["spacing_z_m"]
        if slope != 0:
            fraction = (start_dz - start_dx) / slope
            if begin < fraction < end:
                fractions.add(float(fraction))
    ordered = sorted(fractions)
    samples = sorted(set(ordered + [(begin + end) / 2 for begin, end in zip(ordered[:-1], ordered[1:])]))
    points = _m4_lake_river_connector_np.array([first + fraction * (second - first) for fraction in samples])
    values = [_sample(point, grid, surface, valid, domain, protected, wet) for point in points]
    return points, _m4_lake_river_connector_np.asarray(values)

# --- terrain_pipeline/lake_river_connector.py:440 ---
def _end_binding(points, corridor, joint, step, stage):
    inputs = joint["inputs"]
    lake = inputs["lake_inputs"]
    height = lake["height_m"]
    wet = lake["basin_mask"] & (height < stage)
    lake_grid = {name: lake[name] for name in _grid(corridor)}
    first = points[0]
    lake_points, lake_bed = _line_proof(first[0], first[-1], lake_grid, height,
        _m4_lake_river_connector_np.isfinite(height), lake["domain_mask"], lake["protected_mask"], wet)
    for point, expected in zip(lake_points, lake_bed):
        actual = _sample(point, _grid(corridor), corridor.surface_m, corridor.valid_mask,
                         corridor.domain_mask, corridor.protected_mask)
        if abs(actual - expected) > TOL:
            raise _Gate("lake_source_splice_mismatch", actual_bed_m=actual, lake_bed_m=float(expected))
    fine = inputs["fine"]
    river = step["recovery"]["surface"]["arrays"]
    river_grid = {name: fine[name] for name in _grid(corridor)}
    last = points[-1]
    river_points, source_bed = _line_proof(last[0], last[-1], river_grid, river["source_surface_m"],
        _m4_lake_river_connector_np.isfinite(river["source_surface_m"]), fine["domain_mask"], fine["protected_mask"], river["wet_mask"])
    for point, expected in zip(river_points, source_bed):
        actual = _sample(point, _grid(corridor), corridor.surface_m, corridor.valid_mask,
                         corridor.domain_mask, corridor.protected_mask)
        if abs(actual - expected) > TOL:
            raise _Gate("river_source_splice_mismatch", actual_bed_m=actual, river_H0_m=float(expected))
    actual_bed = _m4_lake_river_connector_np.array([_sample(point, river_grid, river["final_surface_m"],
        _m4_lake_river_connector_np.isfinite(river["final_surface_m"]), fine["domain_mask"], fine["protected_mask"], river["wet_mask"])
        for point in river_points])
    actual_water = _m4_lake_river_connector_np.array([_sample(point, river_grid, river["water_surface_m"],
        _m4_lake_river_connector_np.isfinite(river["water_surface_m"]), fine["domain_mask"], fine["protected_mask"], river["wet_mask"])
        for point in river_points])
    return dict(lake_xz_m=lake_points, lake_bed_m=lake_bed, lake_water_m=_m4_lake_river_connector_np.full(len(lake_points), stage),
                river_xz_m=river_points, river_bed_m=actual_bed, river_water_m=actual_water,
                source_representation="fixed NW-SE diagonal piecewise-linear node facets; full line facet proof",
                contact="shared positive-depth wet cross-section, not proximity of two endpoints")

# --- terrain_pipeline/lake_river_connector.py:477 ---
def _audit_triangles(vertices, bed, triangles, corridor, recipe, counter):
    grid = _grid(corridor)
    min_depth, max_depth, max_cut = _m4_lake_river_connector_math.inf, 0., 0.
    cut_volume, changed_area, covered_area = 0., 0., 0.
    support = set()
    for indices in triangles:
        triangle = vertices[indices, :2]
        water_heights = vertices[indices, 2]
        bed_heights = bed[indices]
        total_area = _area(triangle)
        if total_area <= TOL * TOL:
            raise _Gate("degenerate_or_folded_ribbon")
        facet_area = 0.
        for source_indices, facet in _source_facets(triangle, grid, corridor.surface_m.shape):
            counter[0] += 1
            if counter[0] > recipe.max_support_tests:
                raise _Gate("support_resource_exhausted", support_tests=counter[0])
            clipped = _clip(triangle, facet)
            area = _area(clipped)
            if area <= TOL * TOL:
                continue
            source_heights = []
            for source_index in source_indices:
                if not corridor.valid_mask[source_index]:
                    raise _Gate("unknown_support", grid_zx=list(source_index))
                if not corridor.domain_mask[source_index]:
                    raise _Gate("domain_support", grid_zx=list(source_index))
                if corridor.protected_mask[source_index]:
                    raise _Gate("protected_support", grid_zx=list(source_index))
                source_heights.append(corridor.surface_m[source_index])
                support.add(source_index)
            source = _plane_values(clipped, facet, source_heights)
            actual_bed = _plane_values(clipped, triangle, bed_heights)
            water = _plane_values(clipped, triangle, water_heights)
            depths, cuts = water - actual_bed, source - actual_bed
            min_depth = min(min_depth, float(depths.min()))
            max_depth = max(max_depth, float(depths.max()))
            max_cut = max(max_cut, float(cuts.max()))
            if depths.min() < recipe.min_depth_m - TOL:
                raise _Gate("clearance_failed", actual_min_depth_m=float(depths.min()))
            if depths.max() > recipe.max_depth_m + TOL:
                raise _Gate("depth_failed", actual_max_depth_m=float(depths.max()))
            if cuts.min() < -TOL:
                raise _Gate("bed_raise_failed", raise_m=float(-cuts.min()), triangle_xz_m=triangle.tolist(),
                            clipped_xz_m=_m4_lake_river_connector_np.asarray(clipped).tolist(), source_m=source.tolist(), bed_m=actual_bed.tolist())
            if cuts.max() > recipe.max_cut_m + TOL:
                raise _Gate("cut_depth_budget", actual_cut_m=float(cuts.max()))
            source_at_triangle = _plane_values(triangle, facet, source_heights)
            volume, positive_area = _integral(clipped, triangle, source_at_triangle - bed_heights)
            cut_volume += volume
            changed_area += positive_area
            facet_area += area
        if abs(facet_area - total_area) > TOL:
            raise _Gate("incomplete_triangle_coverage")
        covered_area += facet_area
    if cut_volume > recipe.max_cut_volume_m3 + TOL:
        raise _Gate("cut_volume_budget", actual_cut_volume_m3=cut_volume)
    if changed_area > recipe.max_changed_area_m2 + TOL:
        raise _Gate("changed_area_budget", actual_changed_area_m2=changed_area)
    return dict(min_depth_m=min_depth, max_depth_m=max_depth, max_cut_m=max_cut,
                cut_volume_m3=cut_volume, changed_area_m2=changed_area, wet_area_m2=covered_area,
                source_support_grid_zx=_m4_lake_river_connector_np.array(sorted(support), dtype=_m4_lake_river_connector_np.int64))

# --- terrain_pipeline/lake_river_connector.py:541 ---
def connector_geometry(joint, corridor, recipe, step, counter):
    lake = joint["inputs"]["lake_inputs"]
    stage = float(joint["committed_lake_arrays"]["stage_m"][step["index"] + 1])
    spill_stage = float(lake["height_m"][tuple(lake["legal_spill_grid_zx"])])
    centers, widths, stations, spill = _stations(recipe)
    _geometry_gate(joint, corridor, recipe, step, widths)
    tangents = _m4_lake_river_connector_np.empty_like(centers)
    tangents[0] = centers[1] - centers[0]
    tangents[-1] = centers[-1] - centers[-2]
    tangents[1:-1] = centers[2:] - centers[:-2]
    lengths = _m4_lake_river_connector_np.linalg.norm(tangents, axis=1)
    if _m4_lake_river_connector_np.any(lengths <= TOL):
        raise _Gate("path_fold")
    normals = _m4_lake_river_connector_np.column_stack((-tangents[:, 1], tangents[:, 0])) / lengths[:, None]
    points = centers[:, None, :] + normals[:, None, :] * widths[:, None, None] * _m4_lake_river_connector_np.array([-.5, 0., .5])[None, :, None]
    binding = _end_binding(points, corridor, joint, step, stage)
    grid = _grid(corridor)
    source = _m4_lake_river_connector_np.array([[_sample(point, grid, corridor.surface_m, corridor.valid_mask,
                                corridor.domain_mask, corridor.protected_mask) for point in cross_section]
                       for cross_section in points])
    fine = joint["inputs"]["fine"]
    river_grid = {name: fine[name] for name in grid}
    river = step["recovery"]["surface"]["arrays"]
    end_bed = _m4_lake_river_connector_np.array([_sample(point, river_grid, river["final_surface_m"],
        _m4_lake_river_connector_np.isfinite(river["final_surface_m"]), fine["domain_mask"], fine["protected_mask"], river["wet_mask"])
        for point in points[-1]])
    end_water = _m4_lake_river_connector_np.array([_sample(point, river_grid, river["water_surface_m"],
        _m4_lake_river_connector_np.isfinite(river["water_surface_m"]), fine["domain_mask"], fine["protected_mask"], river["wet_mask"])
        for point in points[-1]])
    if _m4_lake_river_connector_np.any(end_water >= spill_stage):
        raise _Gate("tailwater_at_or_above_spill")
    fraction = _m4_lake_river_connector_np.maximum(stations - stations[spill], 0.) / (stations[-1] - stations[spill])
    terminal_cut = source[-1] - end_bed
    if _m4_lake_river_connector_np.any(terminal_cut < -TOL):
        raise _Gate("bed_raise_failed")
    bed = source - fraction[:, None] * terminal_cut[None, :]
    water = stage + fraction[:, None] * (end_water[None, :] - stage)
    bed[-1] = end_bed
    water[-1] = end_water
    if _m4_lake_river_connector_np.any(_m4_lake_river_connector_np.diff(bed[spill:], axis=0) > TOL):
        raise _Gate("post_spill_bed_uphill")
    if _m4_lake_river_connector_np.any(_m4_lake_river_connector_np.diff(water[spill:], axis=0) > TOL):
        raise _Gate("post_spill_water_uphill")
    vertices = _m4_lake_river_connector_np.column_stack((points.reshape(-1, 2), water.ravel()))
    triangles = []
    for station in range(len(centers) - 1):
        for lateral in range(2):
            first = station * 3 + lateral
            triangles.extend(((first, first + 3, first + 4), (first, first + 4, first + 1)))
    triangles = _m4_lake_river_connector_np.array(triangles, dtype=_m4_lake_river_connector_np.int64)
    _ribbon_gate(vertices, triangles, recipe, counter)
    _splice_gate(points, bed, water, binding)
    audit = _audit_triangles(vertices, bed.ravel(), triangles, corridor, recipe, counter)
    return dict(geometry_type="terrain_following_excavated_water_ribbon", station_m=stations,
        station_xz_m=centers, station_width_m=widths, station_source_bed_m=source[:, 1],
        station_bed_m=bed[:, 1], station_water_m=water[:, 1], spill_station=spill,
        water_vertices_xzw_m=vertices, bed_vertices_m=bed.ravel(), triangles=triangles,
        attachment=binding, audit=audit,
        construction="actual source bed minus linear post-spill taper of actual per-step river terminal cut")

# --- terrain_pipeline/lake_river_connector.py:602 ---
def _evaluate(joint, corridor, recipe):
    _input_gate(joint, corridor, recipe)
    inputs = dict(corridor=_corridor_input(corridor), recipe=_recipe_input(recipe))
    arrays = {}
    tree = connector_tree(dict(source_joint=joint, inputs=inputs), arrays)
    initial_bytes = sum(array.nbytes + 256 for array in arrays.values()) + len(connector_json(tree).encode("utf-8")) * 4
    if initial_bytes > recipe.max_retained_bytes:
        raise ValueError("connector source input exceeds retained byte ceiling")
    counter = [0]
    steps = []
    diagnostic = dict(code="geometry_feasible", failed_step=None, evidence={})
    for step in joint["trace"]:
        if not step["committed"]:
            raise ValueError("only a complete transfer_feasible committed joint may be connected")
        ledger = joint["ledger"][step["index"]]
        outflow = step["lake_outflow_m3_s"]
        if outflow != ledger["lake_outflow_m3_s"]:
            raise ValueError("actual per-step Q/ledger mismatch")
        row = dict(index=step["index"], source_joint_identity=joint["identity_sha256"],
            lake_prefix_identity=step["lake_prefix_identity_sha256"], actual_outflow_m3_s=outflow,
            river_identity=None if step["recovery"] is None else step["recovery"]["identity_sha256"],
            ledger_recheck=ledger, added_injection_m3_s=0., connector_storage_accounted_m3=0.,
            geometry=None, status="closed_dry")
        steps.append(row)
        if outflow == 0:
            continue
        try:
            row["geometry"] = connector_geometry(joint, corridor, recipe, step, counter)
            row["status"] = "connected"
        except _Gate as error:
            row["status"] = "diagnostic"
            diagnostic = dict(code=error.code, failed_step=step["index"], evidence=error.evidence)
            break
    result = dict(algorithm_version=CONNECTOR_VERSION, format_version=1, status="engineering_quasi_steady_geometry",
        geometry_feasible=diagnostic["code"] == "geometry_feasible", source_joint=joint, inputs=inputs,
        steps=steps, diagnostic=diagnostic, summary=dict(connected_steps=sum(row["status"] == "connected" for row in steps),
            closed_steps=sum(row["status"] == "closed_dry" for row in steps), support_tests=counter[0],
            source_joint_publishable=False, limitation=CONNECTOR_LIMITATION))
    arrays = {}
    encoded = connector_tree(result, arrays)
    retained = sum(array.nbytes + 256 for array in arrays.values()) + len(connector_json(encoded).encode("utf-8")) * 4
    if retained > recipe.max_retained_bytes:
        raise ValueError("connector result exceeds retained byte ceiling")
    result["identity_sha256"] = lake_river_connector_hash(result)
    return connector_freeze(result)

# --- terrain_pipeline/lake_river_connector.py:649 ---
def evaluate_lake_river_connector(source_joint, corridor, recipe):
    """Explicit preparation; fully validate the supplied joint before any geometry."""
    if not isinstance(corridor, ConnectorCorridor) or not isinstance(recipe, ConnectorRecipe):
        raise ValueError("explicit ConnectorCorridor and ConnectorRecipe required")
    arrays = {}
    tree = connector_tree(source_joint, arrays)
    if (sum(array.nbytes + 256 for array in arrays.values()) + len(connector_json(tree).encode("utf-8")) * 4
            + corridor.surface_m.nbytes * 4 > recipe.max_retained_bytes):
        raise ValueError("connector input byte preflight before source replay")
    try:
        joint = validate_surface_lake_network(_thaw(source_joint))
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError("invalid source joint") from error
    if not joint["transfer_feasible"]:
        raise ValueError("source joint must be fully transfer_feasible")
    _static_joint(joint)
    return _evaluate(joint, corridor, recipe)

# --- terrain_pipeline/lake_river_connector.py:668 ---
def replay_lake_river_connector(result):
    """Explicit opt-in algorithm replay, including upstream lake/recovery computation."""
    try:
        if result["identity_sha256"] != lake_river_connector_hash(result):
            raise ValueError("connector integrity mismatch")
        replay = evaluate_lake_river_connector(result["source_joint"],
            ConnectorCorridor(**result["inputs"]["corridor"]), ConnectorRecipe(**result["inputs"]["recipe"]))
        if connector_json(connector_tree(result, {})) != connector_json(connector_tree(replay, {})):
            raise ValueError("connector semantic geometry replay mismatch")
        return replay
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
        raise ValueError("malformed connector") from error

# --- terrain_pipeline/lake_river_connector.py:682 ---
def query_lake_river_connector(result, step_index):
    """Read the already prepared immutable step; never validate, generate or recompute."""
    if type(step_index) is not int or not 0 <= step_index < len(result["steps"]):
        raise ValueError("invalid prepared connector step index")
    if not isinstance(result, _m4_lake_river_connector_MappingProxyType):
        raise ValueError("query requires an immutable prepared or loaded connector")
    return result["steps"][step_index]

# --- terrain_pipeline/lake_river_connector.py:691 ---
def _static_plan(plan):
    from terrain_pipeline.artifacts.contracts import array_hash as _m4_lake_river_connector_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _m4_lake_river_connector_digest
    from terrain_pipeline.channel_geometry import ChannelRecipe as _m4_lake_river_connector_ChannelRecipe
    from terrain_pipeline.channel_geometry import _mesh_from_parameters as _m4_lake_river_connector_mesh_from_parameters
    from terrain_pipeline.channel_geometry import _validate_route as _m4_lake_river_connector_validate_route
    parameters = plan["identity"]["parameters"]
    arrays = plan["arrays"]
    if _m4_lake_river_connector_digest(_thaw(plan["identity"])) != plan["identity_sha256"]:
        raise ValueError("source plan identity mismatch")
    _m4_lake_river_connector_ChannelRecipe(**{name: parameters[name] for name in _m4_lake_river_connector_ChannelRecipe.__dataclass_fields__})
    for name, field in (("source_height_m", "source_height_sha256"),
                        ("discharge_m3_s", "source_discharge_sha256"),
                        ("receiver", "source_route_sha256"), ("order", "source_order_sha256"),
                        ("outlet_mask", "source_outlet_sha256")):
        if _m4_lake_river_connector_array_hash(arrays[name]) != parameters[field]:
            raise ValueError("source plan H0/Q/route identity mismatch")
    shape = arrays["source_height_m"].shape
    _m4_lake_river_connector_validate_route(arrays["receiver"], arrays["order"], shape, arrays["outlet_mask"],
                    _m4_lake_river_connector_mesh_from_parameters(parameters, shape),
                    historical_saved_graph=plan["identity"]["algorithm_version"] == "metric-channel-plan-v1")
    discharge = arrays["discharge_m3_s"].ravel()
    if not _m4_lake_river_connector_np.isfinite(discharge).all() or _m4_lake_river_connector_np.any(discharge < 0):
        raise ValueError("invalid source plan Q")
    local = discharge.copy()
    donors = _m4_lake_river_connector_np.flatnonzero(arrays["receiver"] >= 0)
    _m4_lake_river_connector_np.subtract.at(local, arrays["receiver"][donors], discharge[donors])
    if _m4_lake_river_connector_np.any(local < -TOL):
        raise ValueError("nonconservative source plan Q")
    return local

# --- terrain_pipeline/lake_river_connector.py:718 ---
def _static_joint(joint):
    from terrain_pipeline.artifacts.contracts import array_hash as _m4_lake_river_connector_array_hash
    from terrain_pipeline.surface_domain import _payload as _m4_lake_river_connector_payload
    from terrain_pipeline.surface_domain import _proof_gate as _m4_lake_river_connector_proof_gate
    from terrain_pipeline.surface_domain import validate_surface_network as _m4_lake_river_connector_validate_surface_network
    if (joint["identity_sha256"] != surface_lake_network_hash(_thaw(joint))
            or joint["transfer_feasible"] is not True or joint["status"] != "diagnostic_not_publishable"):
        raise ValueError("invalid complete source joint identity/status")
    inputs = joint["inputs"]
    lake_inputs = inputs["lake_inputs"]
    lake = joint["independent_lake_diagnostic"]
    if lake["identity_sha256"] != lake_routing_hash(_thaw(lake)) or not lake["scenario_feasible"]:
        raise ValueError("invalid source lake identity/status")
    lake_arrays = lake["arrays"]
    for name in ("height_m", "basin_mask", "domain_mask", "protected_mask"):
        if not _m4_lake_river_connector_np.array_equal(lake_arrays[name], lake_inputs[name]):
            raise ValueError("source lake input mismatch")
    recipe = lake_inputs["recipe"]
    if connector_json(_thaw(lake["input"]["recipe"])) != connector_json(_thaw(recipe)):
        raise ValueError("source lake recipe mismatch")
    for name in ("spacing_x_m", "spacing_z_m", "origin_x_m", "origin_z_m", "vertical_datum", "source_identity"):
        if lake["input"][name] != lake_inputs[name]:
            raise ValueError("source lake coordinate/source mismatch")
    stages = lake_arrays["stage_m"]
    area = lake_inputs["spacing_x_m"] * lake_inputs["spacing_z_m"]
    volumes = _m4_lake_river_connector_np.array([_m4_lake_river_connector_np.maximum(stage - lake_inputs["height_m"][lake_inputs["basin_mask"]], 0.).sum() * area
                        for stage in stages])
    if not _m4_lake_river_connector_np.allclose(volumes, lake_arrays["storage_m3"], rtol=0, atol=TOL):
        raise ValueError("source lake actual storage mismatch")
    for name in ("stage_m", "storage_m3"):
        if not _m4_lake_river_connector_np.array_equal(joint["committed_lake_arrays"][name], lake_arrays[name]):
            raise ValueError("committed source lake timeline mismatch")
    local = _static_plan(inputs["plan"])
    params = inputs["plan"]["identity"]["parameters"]
    shape = inputs["plan"]["arrays"]["source_height_m"].shape
    outlet_stage = _m4_lake_river_connector_np.asarray(inputs["outlet_stage_m"])
    if (outlet_stage.shape != shape or outlet_stage.dtype.kind not in "fiu"
            or not _m4_lake_river_connector_np.isfinite(outlet_stage).all()
            or not _m4_lake_river_connector_np.all(outlet_stage == outlet_stage.flat[0])):
        raise ValueError("source outlet stages are not the declared uniform grid input")
    seam = inputs["seam"]
    column = round((seam["world_x_m"] - params["origin_x_m"]) / params["spacing_x_m"])
    row = round((seam["world_z_m"] - params["origin_z_m"]) / params["spacing_z_m"])
    injection = row * shape[1] + column
    if not 0 <= injection < len(local):
        raise ValueError("invalid source injection")
    if len(joint["trace"]) != len(recipe["inflow_m3_s"]) or len(joint["ledger"]) != len(joint["trace"]):
        raise ValueError("incomplete source joint")
    attempts, fine_work = 0, 0
    for index, step in enumerate(joint["trace"]):
        if not step["committed"] or step["index"] != index:
            raise ValueError("source step not committed")
        outflow = step["lake_outflow_m3_s"]
        expected_q = float(_m4_lake_river_connector_np.interp(stages[index + 1], recipe["rating_stage_m"], recipe["rating_outflow_m3_s"]))
        if abs(outflow - expected_q) > TOL or outflow != lake_arrays["step_outflow_m3_s"][index]:
            raise ValueError("source step Q differs from actual lake stage/rating")
        injected = local.copy()
        injected[injection] += outflow
        if (not _m4_lake_river_connector_np.allclose(step["original_local_inflow_m3_s"].ravel(), local, rtol=0, atol=TOL)
                or not _m4_lake_river_connector_np.allclose(step["injected_local_inflow_m3_s"].ravel(), injected, rtol=0, atol=TOL)
                or not _m4_lake_river_connector_np.allclose(_static_plan(step["recomputed_plan"]), injected, rtol=0, atol=TOL)):
            raise ValueError("source actual injection differs or is duplicated")
        final = step["recomputed_plan"]
        recovery = step["recovery"]
        if recovery is not None:
            if not recovery["accepted"]:
                raise ValueError("source river not accepted")
            proof = _thaw(recovery)
            _m4_lake_river_connector_validate_surface_network(proof["surface"])
            _m4_lake_river_connector_proof_gate(proof, _m4_lake_river_connector_payload(proof))
            recovery_inputs = recovery["inputs"]
            for name in ("coarse_domain", "coarse_protected", "fine", "section_recipe", "stage_recipe",
                         "inundation_recipe", "budget", "network_recipe", "valley_recipe", "reroute_recipe"):
                if connector_json(connector_tree(inputs[name], {})) != connector_json(connector_tree(recovery_inputs[name], {})):
                    raise ValueError("source recovery call input mismatch: " + name)
            if connector_json(connector_tree(recovery_inputs["plan"], {})) != connector_json(connector_tree(step["recomputed_plan"], {})):
                raise ValueError("source recovery did not use the actual step plan")
            active_outlets = step["recomputed_plan"]["arrays"]["channel_mask"] & inputs["plan"]["arrays"]["outlet_mask"]
            if not _m4_lake_river_connector_np.array_equal(recovery_inputs["outlet_stage_m"], inputs["outlet_stage_m"][active_outlets]):
                raise ValueError("source recovery actual outlet stages differ")
            expected_recipe = dict(inputs["recovery_recipe"])
            expected_recipe["max_attempts"] = min(expected_recipe["max_attempts"], inputs["recipe"]["max_total_attempts"] - attempts)
            expected_recipe["max_total_fine_cells"] = min(expected_recipe["max_total_fine_cells"], inputs["recipe"]["max_total_fine_work"] - fine_work)
            if connector_json(expected_recipe) != connector_json(_thaw(recovery_inputs["recovery_recipe"])):
                raise ValueError("source recovery aggregate resource call mismatch")
            attempts += len(recovery["attempts"])
            fine_work += recovery["summary"]["total_fine_cells_evaluated"]
            final = recovery["final_plan"]
            _static_plan(final)
            if _m4_lake_river_connector_array_hash(final["arrays"]["discharge_m3_s"]) != _m4_lake_river_connector_array_hash(step["recomputed_plan"]["arrays"]["discharge_m3_s"]):
                raise ValueError("source recovery Q changed")
            surface = recovery["surface"]["arrays"]
            fine = inputs["fine"]
            fine_row = round((seam["world_z_m"] - fine["origin_z_m"]) / fine["spacing_z_m"])
            fine_column = round((seam["world_x_m"] - fine["origin_x_m"]) / fine["spacing_x_m"])
            if outflow > 0 and (not surface["wet_mask"][fine_row, fine_column]
                    or surface["water_surface_m"][fine_row, fine_column] != step["injection_stage_m"]):
                raise ValueError("source actual injection wet/stage mismatch")
            original_height = inputs["plan"]["arrays"]["source_height_m"]
            ledger_source = recovery["fine_ledger"]
            original_fine = surface["source_surface_m"] if ledger_source is None else ledger_source["arrays"]["source_surface_m"]
            for coarse_row in range(shape[0]):
                for coarse_column in range(shape[1]):
                    world_x = params["origin_x_m"] + coarse_column * params["spacing_x_m"]
                    world_z = params["origin_z_m"] + coarse_row * params["spacing_z_m"]
                    fine_x = round((world_x - fine["origin_x_m"]) / fine["spacing_x_m"])
                    fine_z = round((world_z - fine["origin_z_m"]) / fine["spacing_z_m"])
                    if abs(original_fine[fine_z, fine_x] - original_height[coarse_row, coarse_column]) > TOL:
                        raise ValueError("source actual river H0 differs from original terrain")
        river_outflow = float(final["arrays"]["discharge_m3_s"][final["arrays"]["outlet_mask"]].sum())
        ledger = joint["ledger"][index]
        dt = recipe["dt_s"]
        storage_change = volumes[index + 1] - volumes[index]
        combined = storage_change + dt * river_outflow - dt * (recipe["inflow_m3_s"][index] - recipe["loss_m3_s"][index] + local.sum())
        lake_residual = storage_change - dt * (recipe["inflow_m3_s"][index] - recipe["loss_m3_s"][index] - outflow)
        river_residual = river_outflow - float(local.sum()) - outflow
        allowed_lake = recipe["volume_abs_tolerance_m3"] + recipe["volume_rel_tolerance"] * max(
            volumes[index], volumes[index + 1], dt * recipe["inflow_m3_s"][index], dt * recipe["loss_m3_s"][index], dt * outflow)
        joint_recipe = inputs["recipe"]
        allowed_flow = joint_recipe["discharge_abs_tolerance_m3_s"] + joint_recipe["discharge_rel_tolerance"] * max(
            abs(river_outflow), abs(float(local.sum())), abs(outflow))
        allowed = allowed_lake + dt * allowed_flow
        if (ledger["lake_outflow_m3_s"] != outflow or abs(ledger["downstream_outlet_m3_s"] - river_outflow) > TOL
                or abs(ledger["lake_storage_change_m3"] - storage_change) > TOL
                or abs(combined - ledger["combined_residual_m3"]) > TOL
                or ledger["dt_s"] != dt or ledger["lake_inflow_m3_s"] != recipe["inflow_m3_s"][index]
                or ledger["lake_loss_m3_s"] != recipe["loss_m3_s"][index]
                or abs(ledger["lake_residual_m3"] - lake_residual) > TOL
                or abs(ledger["downstream_residual_m3_s"] - river_residual) > TOL
                or abs(ledger["combined_tolerance_m3"] - allowed) > 1e-13
                or abs(lake_residual) > allowed_lake + 1e-13 or abs(river_residual) > allowed_flow
                or abs(combined) > allowed + 1e-13):
            raise ValueError("source actual conservation ledger mismatch")
    summary = joint["summary"]
    expected_summary = dict(committed_steps=len(joint["trace"]), requested_steps=len(recipe["inflow_m3_s"]),
        committed_final_lake_stage_m=float(stages[-1]), committed_initial_lake_storage_m3=float(volumes[0]),
        committed_final_lake_storage_m3=float(volumes[-1]), total_attempts=attempts, total_fine_work=fine_work,
        total_lake_work=lake_inputs["height_m"].size * (len(joint["trace"]) + len(joint["trace"]) * (len(joint["trace"]) + 1) // 2),
        connector_geometry_generated=False, river_storage_or_propagation_modeled=False)
    for name, field in (("total_lake_inflow_m3", "lake_inflow_m3_s"), ("total_lake_loss_m3", "lake_loss_m3_s"),
                        ("total_lake_outflow_m3", "lake_outflow_m3_s"), ("total_downstream_local_m3", "downstream_local_total_m3_s"),
                        ("total_downstream_outlet_m3", "downstream_outlet_m3_s")):
        expected_summary[name] = _m4_lake_river_connector_math.fsum(ledger["dt_s"] * ledger[field] for ledger in joint["ledger"])
    for name, field in (("total_combined_residual_m3", "combined_residual_m3"),
                        ("total_combined_tolerance_m3", "combined_tolerance_m3")):
        expected_summary[name] = _m4_lake_river_connector_math.fsum(ledger[field] for ledger in joint["ledger"])
    expected_summary["aggregate_combined_residual_m3"] = _m4_lake_river_connector_math.fsum((volumes[-1], -volumes[0],
        expected_summary["total_downstream_outlet_m3"], -expected_summary["total_lake_inflow_m3"],
        expected_summary["total_lake_loss_m3"], -expected_summary["total_downstream_local_m3"]))
    for name, value in expected_summary.items():
        if isinstance(value, float):
            if not _m4_lake_river_connector_math.isclose(summary[name], value, rel_tol=0, abs_tol=TOL):
                raise ValueError("source joint recomputed summary mismatch: " + name)
        elif summary[name] != value:
            raise ValueError("source joint summary mismatch: " + name)
    final_depth = _m4_lake_river_connector_np.where(lake_inputs["basin_mask"], _m4_lake_river_connector_np.maximum(stages[-1] - lake_inputs["height_m"], 0.), 0.)
    committed = joint["committed_lake_arrays"]
    if (not _m4_lake_river_connector_np.array_equal(committed["water_depth_m"], final_depth)
            or not _m4_lake_river_connector_np.array_equal(committed["wet_mask"], final_depth > 0)
            or not _m4_lake_river_connector_np.array_equal(committed["water_surface_m"], _m4_lake_river_connector_np.where(final_depth > 0, stages[-1], _m4_lake_river_connector_np.nan), equal_nan=True)):
        raise ValueError("source committed actual lake wet geometry mismatch")

# --- terrain_pipeline/lake_river_connector.py:877 ---
def _static_geometry(geometry, joint, corridor, recipe, step, counter):
    centers, widths, stations, spill = _stations(recipe)
    _geometry_gate(joint, corridor, recipe, step, widths)
    if (geometry["spill_station"] != spill or geometry["geometry_type"] != "terrain_following_excavated_water_ribbon"
            or geometry["construction"] != "actual source bed minus linear post-spill taper of actual per-step river terminal cut"):
        raise ValueError("connector geometry representation mismatch")
    for name, expected in (("station_xz_m", centers), ("station_width_m", widths), ("station_m", stations)):
        if not _m4_lake_river_connector_np.array_equal(geometry[name], expected):
            raise ValueError("connector station recipe mismatch")
    vertices = geometry["water_vertices_xzw_m"]
    bed = geometry["bed_vertices_m"]
    triangles = geometry["triangles"]
    if (vertices.shape != (len(centers) * 3, 3) or bed.shape != (len(vertices),)
            or not _m4_lake_river_connector_np.isfinite(vertices).all() or not _m4_lake_river_connector_np.isfinite(bed).all()):
        raise ValueError("invalid connector vertices")
    tangents = _m4_lake_river_connector_np.empty_like(centers)
    tangents[0], tangents[-1] = centers[1] - centers[0], centers[-1] - centers[-2]
    tangents[1:-1] = centers[2:] - centers[:-2]
    normals = _m4_lake_river_connector_np.column_stack((-tangents[:, 1], tangents[:, 0])) / _m4_lake_river_connector_np.linalg.norm(tangents, axis=1)[:, None]
    points = centers[:, None, :] + normals[:, None, :] * widths[:, None, None] * _m4_lake_river_connector_np.array([-.5, 0., .5])[None, :, None]
    if not _m4_lake_river_connector_np.array_equal(vertices[:, :2], points.reshape(-1, 2)):
        raise ValueError("connector actual width/position mismatch")
    expected_triangles = []
    for station in range(len(centers) - 1):
        for lateral in range(2):
            first = station * 3 + lateral
            expected_triangles.extend(((first, first + 3, first + 4), (first, first + 4, first + 1)))
    if not _m4_lake_river_connector_np.array_equal(triangles, expected_triangles):
        raise ValueError("connector triangle topology mismatch")
    _ribbon_gate(vertices, triangles, recipe, counter)
    stage = joint["committed_lake_arrays"]["stage_m"][step["index"] + 1]
    binding = _end_binding(points, corridor, joint, step, stage)
    if connector_json(connector_tree(binding, {})) != connector_json(connector_tree(geometry["attachment"], {})):
        raise ValueError("connector full-width attachment mismatch")
    source = _m4_lake_river_connector_np.array([[_sample(point, _grid(corridor), corridor.surface_m, corridor.valid_mask,
        corridor.domain_mask, corridor.protected_mask) for point in cross_section] for cross_section in points])
    fine = joint["inputs"]["fine"]
    river = step["recovery"]["surface"]["arrays"]
    river_grid = {name: fine[name] for name in _grid(corridor)}
    terminal_bed = _m4_lake_river_connector_np.array([_sample(point, river_grid, river["final_surface_m"], _m4_lake_river_connector_np.isfinite(river["final_surface_m"]),
        fine["domain_mask"], fine["protected_mask"], river["wet_mask"]) for point in points[-1]])
    terminal_water = _m4_lake_river_connector_np.array([_sample(point, river_grid, river["water_surface_m"], _m4_lake_river_connector_np.isfinite(river["water_surface_m"]),
        fine["domain_mask"], fine["protected_mask"], river["wet_mask"]) for point in points[-1]])
    fraction = _m4_lake_river_connector_np.maximum(stations - stations[spill], 0.) / (stations[-1] - stations[spill])
    expected_bed = source - fraction[:, None] * (source[-1] - terminal_bed)[None, :]
    expected_water = stage + fraction[:, None] * (terminal_water[None, :] - stage)
    expected_bed[-1], expected_water[-1] = terminal_bed, terminal_water
    spill_stage = joint["inputs"]["lake_inputs"]["height_m"][tuple(joint["inputs"]["lake_inputs"]["legal_spill_grid_zx"])]
    if _m4_lake_river_connector_np.any(terminal_water >= spill_stage) or _m4_lake_river_connector_np.any(_m4_lake_river_connector_np.diff(expected_water[spill:], axis=0) > TOL):
        raise ValueError("connector tailwater or water uphill")
    _splice_gate(points, expected_bed, expected_water, binding)
    if (not _m4_lake_river_connector_np.array_equal(bed.reshape(-1, 3), expected_bed)
            or not _m4_lake_river_connector_np.array_equal(vertices[:, 2].reshape(-1, 3), expected_water)
            or not _m4_lake_river_connector_np.array_equal(geometry["station_bed_m"], expected_bed[:, 1])
            or not _m4_lake_river_connector_np.array_equal(geometry["station_water_m"], expected_water[:, 1])
            or not _m4_lake_river_connector_np.array_equal(geometry["station_source_bed_m"], source[:, 1])):
        raise ValueError("connector actual bed/water construction mismatch")
    if _m4_lake_river_connector_np.any(_m4_lake_river_connector_np.diff(expected_bed[spill:], axis=0) > TOL):
        raise ValueError("connector post-spill bed uphill")
    audit = _audit_triangles(vertices, bed, triangles, corridor, recipe, counter)
    if connector_json(connector_tree(audit, {})) != connector_json(connector_tree(geometry["audit"], {})):
        raise ValueError("connector actual geometry budget summary mismatch")

# --- terrain_pipeline/lake_river_connector.py:941 ---
def validate_lake_river_connector(result):
    """Static source, conservation, full-width facet and geometry audit; no prepare/recovery."""
    try:
        if (result["identity_sha256"] != lake_river_connector_hash(result) or result["algorithm_version"] != CONNECTOR_VERSION
                or result["format_version"] != 1 or result["status"] != "engineering_quasi_steady_geometry"
                or type(result["geometry_feasible"]) is not bool):
            raise ValueError("connector identity mismatch")
        corridor = ConnectorCorridor(**result["inputs"]["corridor"])
        recipe = ConnectorRecipe(**result["inputs"]["recipe"])
        joint = result["source_joint"]
        _input_gate(joint, corridor, recipe)
        _static_joint(joint)
        diagnostic = result["diagnostic"]
        if (set(diagnostic) != {"code", "failed_step", "evidence"} or not isinstance(diagnostic["evidence"], _m4_lake_river_connector_Mapping)
                or not isinstance(diagnostic["code"], str)):
            raise ValueError("invalid connector diagnostic schema")
        failure_codes = {"tailwater_at_or_above_spill", "path_selfintersection", "station_resource_exhausted",
            "width_resolution_failed", "longitudinal_resolution_failed", "path_fold", "outside_source_support",
            "unknown_support", "domain_support", "protected_support", "dry_splice_support", "lake_source_splice_mismatch",
            "river_source_splice_mismatch", "bed_raise_failed", "post_spill_bed_uphill", "post_spill_water_uphill",
            "triangle_resource_exhausted", "support_resource_exhausted", "ribbon_selfintersection",
            "degenerate_or_folded_ribbon", "full_cross_section_splice_mismatch", "clearance_failed", "depth_failed",
            "cut_depth_budget", "incomplete_triangle_coverage", "cut_volume_budget", "changed_area_budget"}
        if not result["geometry_feasible"]:
            if (not result["steps"] or diagnostic["code"] not in failure_codes
                    or type(diagnostic["failed_step"]) is not int or diagnostic["failed_step"] != len(result["steps"]) - 1
                    or result["steps"][-1]["status"] != "diagnostic"):
                raise ValueError("connector diagnostic requires the real retained prefix and terminal failed step")
        counter = [0]
        connected, closed = 0, 0
        for index, row in enumerate(result["steps"]):
            step = joint["trace"][index]
            if (row["index"] != index or row["actual_outflow_m3_s"] != step["lake_outflow_m3_s"]
                    or row["source_joint_identity"] != joint["identity_sha256"]
                    or row["lake_prefix_identity"] != step["lake_prefix_identity_sha256"]
                    or row["river_identity"] != (None if step["recovery"] is None else step["recovery"]["identity_sha256"])
                    or row["added_injection_m3_s"] != 0. or row["connector_storage_accounted_m3"] != 0.
                    or connector_json(connector_tree(row["ledger_recheck"], {})) != connector_json(connector_tree(joint["ledger"][index], {}))):
                raise ValueError("connector actual Q/identity/conservation mismatch")
            if row["status"] == "connected":
                if row["actual_outflow_m3_s"] <= 0:
                    raise ValueError("zero Q cannot have wet geometry")
                _static_geometry(row["geometry"], joint, corridor, recipe, step, counter)
                connected += 1
            elif row["status"] == "closed_dry":
                if row["actual_outflow_m3_s"] != 0 or row["geometry"] is not None:
                    raise ValueError("closed connector must be dry and zero Q")
                closed += 1
            elif row["status"] != "diagnostic" or row["geometry"] is not None or result["geometry_feasible"]:
                raise ValueError("invalid connector diagnostic")
            elif index != diagnostic["failed_step"] or row["actual_outflow_m3_s"] <= 0:
                raise ValueError("connector failure must be the positive-Q terminal prefix step")
        if (result["summary"]["connected_steps"] != connected or result["summary"]["closed_steps"] != closed
                or result["summary"]["source_joint_publishable"] is not False
                or result["summary"]["limitation"] != CONNECTOR_LIMITATION
                or (result["geometry_feasible"] and result["summary"]["support_tests"] != counter[0])
                or (result["geometry_feasible"] and len(result["steps"]) != len(joint["trace"]))):
            raise ValueError("connector summary/completeness mismatch")
        if result["geometry_feasible"] and (result["diagnostic"]["code"] != "geometry_feasible"
                or result["diagnostic"]["failed_step"] is not None):
            raise ValueError("connector feasible diagnostic mismatch")
        arrays = {}
        encoded = connector_tree(result, arrays)
        if sum(array.nbytes + 256 for array in arrays.values()) + len(connector_json(encoded).encode("utf-8")) * 4 > recipe.max_retained_bytes:
            raise ValueError("connector actual retained-byte ceiling")
        return connector_freeze(result)
    except _Gate as error:
        raise ValueError("static connector gate: " + error.code) from error
    except (KeyError, TypeError, AttributeError, IndexError, OverflowError, RecursionError) as error:
        raise ValueError("malformed static connector") from error

# --- terrain_pipeline/lake_river_connector.py:1013 ---
def connector_unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate connector JSON key")
        result[name] = value
    return result

# --- terrain_pipeline/lake_river_connector.py:1022 ---
def connector_reject_constant(value):
    raise ValueError("nonfinite connector JSON constant")

# --- terrain_pipeline/lake_river_connector.py:1026 ---
def connector_preflight(handle):
    if _m4_lake_river_connector_os.fstat(handle.fileno()).st_size > MAX_BYTES:
        raise ValueError("compressed connector archive exceeds resource ceiling")
    with _m4_lake_river_connector_zipfile.ZipFile(handle) as archive:
        entries = archive.infolist()
        names = {entry.filename for entry in entries}
        if (len(entries) > 4096 or len(entries) != len(names) or "manifest.npy" not in names
                or sum(entry.file_size for entry in entries) > MAX_BYTES):
            raise ValueError("connector ZIP duplicate/member/expanded resource ceiling")
        for entry in entries:
            if (entry.flag_bits & 1 or entry.compress_type not in (_m4_lake_river_connector_zipfile.ZIP_STORED, _m4_lake_river_connector_zipfile.ZIP_DEFLATED)
                    or "/" in entry.filename or "\\" in entry.filename
                    or not entry.filename.endswith(".npy")):
                raise ValueError("invalid connector ZIP member")
            if entry.filename != "manifest.npy" and (
                    not entry.filename.startswith("array_") or len(entry.filename) != 74
                    or any(character not in "0123456789abcdef" for character in entry.filename[6:-4])):
                raise ValueError("invalid connector array member name")
            with archive.open(entry) as member:
                version = _m4_lake_river_connector_np.lib.format.read_magic(member)
                if version == (1, 0):
                    shape, fortran, dtype = _m4_lake_river_connector_np.lib.format.read_array_header_1_0(member)
                elif version == (2, 0):
                    shape, fortran, dtype = _m4_lake_river_connector_np.lib.format.read_array_header_2_0(member)
                else:
                    raise ValueError("unsupported connector NPY version")
                byte_count = _m4_lake_river_connector_math.prod(shape) * dtype.itemsize
                if (dtype.hasobject or fortran or len(shape) > 2 or dtype.itemsize <= 0
                        or any(type(size) is not int or size < 0 for size in shape)
                        or byte_count > MAX_BYTES or member.tell() + byte_count != entry.file_size):
                    raise ValueError("connector NPY header/payload/resource mismatch")
                if entry.filename == "manifest.npy":
                    if shape != () or dtype.kind != "U" or byte_count > 4 * 1024 * 1024:
                        raise ValueError("invalid bounded connector manifest")
                elif dtype.kind not in "bifu" or _m4_lake_river_connector_math.prod(shape) > 2000000:
                    raise ValueError("invalid bounded connector numeric array")
    handle.seek(0)

# --- terrain_pipeline/lake_river_connector.py:1065 ---
def save_lake_river_connector(result, destination):
    """Replay then atomic no-overwrite publication of a self-contained bundle."""
    destination = _m4_lake_river_connector_Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    if destination.suffix != ".npz":
        raise ValueError("connector requires .npz destination")
    validated = validate_lake_river_connector(result)
    arrays = {}
    tree = connector_tree(validated, arrays)
    manifest = connector_json(dict(format_version=1, tree=tree,
        tree_sha256=_m4_lake_river_connector_hashlib.sha256(connector_json(tree).encode("utf-8")).hexdigest()))
    if (len(manifest) * 4 > 4 * 1024 * 1024 or len(arrays) + 1 > 4096
            or sum(array.nbytes + 256 for array in arrays.values()) + len(manifest) * 4
            > validated["inputs"]["recipe"]["max_retained_bytes"]):
        raise ValueError("connector save exceeds resource ceiling")
    descriptor, temporary = _m4_lake_river_connector_tempfile.mkstemp(prefix=".connector-", suffix=".tmp", dir=destination.parent)
    try:
        with _m4_lake_river_connector_os.fdopen(descriptor, "wb") as handle:
            _m4_lake_river_connector_np.savez_compressed(handle, manifest=_m4_lake_river_connector_np.asarray(manifest), **arrays)
            handle.flush()
            _m4_lake_river_connector_os.fsync(handle.fileno())
        with open(temporary, "rb") as handle:
            connector_preflight(handle)
        _m4_lake_river_connector_os.link(temporary, destination)
    finally:
        _m4_lake_river_connector_os.unlink(temporary)
    return destination

# --- terrain_pipeline/lake_river_connector.py:1095 ---
def load_lake_river_connector(source, replay=False):
    """Default static semantic audit; replay=True explicitly opts into upstream computation."""
    try:
        with open(source, "rb") as handle:
            connector_preflight(handle)
            with _m4_lake_river_connector_np.load(handle, allow_pickle=False) as archive:
                manifest = _m4_lake_river_connector_json.loads(str(archive["manifest"].item()), object_pairs_hook=connector_unique_object,
                                      parse_constant=connector_reject_constant)
                if (set(manifest) != {"format_version", "tree", "tree_sha256"}
                        or manifest["format_version"] != 1
                        or _m4_lake_river_connector_hashlib.sha256(connector_json(manifest["tree"]).encode("utf-8")).hexdigest() != manifest["tree_sha256"]):
                    raise ValueError("connector manifest integrity mismatch")
                used, cache = {"manifest"}, {}

                def decode(value):
                    if isinstance(value, dict) and "$array" in value:
                        if set(value) != {"$array", "dtype", "shape", "sha256"}:
                            raise ValueError("malformed connector array reference")
                        name = value["$array"]
                        if name not in archive.files or name != "array_" + value["sha256"]:
                            raise ValueError("missing connector array binding")
                        used.add(name)
                        if name not in cache:
                            cache[name] = connector_freeze(archive[name])
                        array = cache[name]
                        if (array.dtype.str != value["dtype"] or list(array.shape) != value["shape"]
                                or connector_array_hash(array) != value["sha256"]):
                            raise ValueError("connector array integrity mismatch")
                        return array
                    if isinstance(value, dict):
                        return {name: decode(child) for name, child in value.items()}
                    if isinstance(value, list):
                        return [decode(child) for child in value]
                    return value

                result = decode(manifest["tree"])
                if used != set(archive.files):
                    raise ValueError("undeclared connector archive arrays")
        return replay_lake_river_connector(result) if replay else validate_lake_river_connector(result)
    except (OSError, EOFError, KeyError, TypeError, AttributeError, RecursionError,
            _m4_lake_river_connector_zipfile.BadZipFile, _m4_lake_river_connector_json.JSONDecodeError) as error:
        raise ValueError("invalid connector archive") from error

# --- terrain_pipeline/mountain_lake_coupling.py:17 ---
COUPLING_SCHEMA = "mountain-lake-coupling-v1"

# --- terrain_pipeline/mountain_lake_coupling.py:18 ---
BOUNDARIES = {"external_open_boundary", "closed_terminal", "ocean_open_boundary"}

# --- terrain_pipeline/mountain_lake_coupling.py:19 ---
COUPLING_MAX_BYTES = 768 * 1024 * 1024

# --- terrain_pipeline/mountain_lake_coupling.py:20 ---
BASE_KEYS = {"height_m", "hydrology_mask", "cell_owner", "receiver", "anchor_node", "node_downstream", "tau_s",
    "cell_node", "allocation_counts", "area_m2", "node_order", "lateral_volume_m3", "incoming_volume_m3",
    "land_allocation_counts", "surface_allocation_counts", "surface_rain_volume_m3", "surface_evaporation_volume_m3",
    "outflow_volume_m3", "storage_m3", "lake_stage_m", "lake_loss_volume_m3", "boundary_nodes",
    "boundary_volume_m3", "total_boundary_volume_m3"}

# --- terrain_pipeline/mountain_lake_coupling.py:25 ---
META_KEYS = {"schema", "status", "source_identity", "source_metadata", "geometry_identity", "geometry_passed",
    "node_kind", "node_boundary_type", "boundary_policy", "runoff_metadata", "lake_evidence", "river_stage_solved",
    "selection_metadata", "selection_identity", "rain_support", "lake_evaporation_mm_h", "surface_scope",
    "hydrological_closure_certified"}

# --- terrain_pipeline/mountain_lake_coupling.py:31 ---
def terminal_ownership(receiver, calculation_mask):
    """Global partition with no dynamic node allocation, including every edge outlet."""
    from terrain_pipeline.common_infra import readonly as _m4_mountain_lake_coupling_readonly
    from terrain_pipeline.drainage import segments_clear as _m4_mountain_lake_coupling_segments_clear
    from terrain_pipeline.runoff import _order as _m4_mountain_lake_coupling_order
    if (not isinstance(receiver, _m4_mountain_lake_coupling_np.ndarray) or receiver.ndim != 2 or receiver.dtype != _m4_mountain_lake_coupling_np.int64 or
            not 1 <= receiver.size <= 250_000 or not isinstance(calculation_mask, _m4_mountain_lake_coupling_np.ndarray) or
            calculation_mask.shape != receiver.shape or calculation_mask.dtype != bool or not calculation_mask.any()):
        raise ValueError("invalid bounded receiver/domain")
    flat = receiver.ravel()
    order = _m4_mountain_lake_coupling_order(flat)
    moving = _m4_mountain_lake_coupling_np.flatnonzero(flat >= 0)
    targets = flat[moving]
    active = calculation_mask.ravel()
    if (active[moving] & ~active[targets]).any():
        raise ValueError("active receiver leaves calculation domain without explicit terminal")
    participating = active[moving]
    if not _m4_mountain_lake_coupling_segments_clear(moving[participating], targets[participating], calculation_mask).all():
        raise ValueError("receiver segment crosses outside the calculation domain")
    owner = _m4_mountain_lake_coupling_np.full(flat.size, -1, _m4_mountain_lake_coupling_np.int64)
    terminals = _m4_mountain_lake_coupling_np.flatnonzero((flat == -1) & active)
    owner[terminals] = terminals
    for current in order[::-1]:
        if active[current] and flat[current] >= 0:
            owner[current] = owner[flat[current]]
    if (owner[active] < 0).any():
        raise ValueError("unmapped contributing cell")
    counts = _m4_mountain_lake_coupling_np.bincount(owner[active], minlength=flat.size)[terminals]
    return {"terminal_owner": _m4_mountain_lake_coupling_readonly(owner.reshape(receiver.shape)),
            "terminal_flat": _m4_mountain_lake_coupling_readonly(terminals), "contributing_counts": _m4_mountain_lake_coupling_readonly(counts)}

# --- terrain_pipeline/mountain_lake_coupling.py:60 ---
def contribution_mask(receiver, calculation_mask, terminal_flat):
    from terrain_pipeline.common_infra import readonly as _m4_mountain_lake_coupling_readonly
    from terrain_pipeline.runoff import _hash as _m4_mountain_lake_coupling_hash
    partition = terminal_ownership(receiver, calculation_mask)
    if type(terminal_flat) is not int or terminal_flat not in partition["terminal_flat"]:
        raise ValueError("terminal not in global partition")
    mask = partition["terminal_owner"] == terminal_flat
    return _m4_mountain_lake_coupling_readonly(mask), {
        "terminal_flat": terminal_flat, "contributing_cells": int(mask.sum()),
        "full_receiver_sha256": _m4_mountain_lake_coupling_hash(receiver), "full_domain_sha256": _m4_mountain_lake_coupling_hash(calculation_mask),
        "terminal_owner_sha256": _m4_mountain_lake_coupling_hash(partition["terminal_owner"]),
        "mask_sha256": _m4_mountain_lake_coupling_hash(mask), "upstream_complete_within_finite_window": True,
        "hydrological_closure_certified": False}

# --- terrain_pipeline/mountain_lake_coupling.py:73 ---
def local_allocation(receiver, anchor_node, cell_owner, calculation_mask, node_downstream, *, spacing_m, hrus):
    """First lake/reach encountered, never an accumulated upstream discharge input."""
    from terrain_pipeline.common_infra import readonly as _m4_mountain_lake_coupling_readonly
    from terrain_pipeline.runoff import _order as _m4_mountain_lake_coupling_order
    terminal_ownership(receiver, calculation_mask)
    shape = receiver.shape
    for value in (anchor_node, cell_owner):
        if not isinstance(value, _m4_mountain_lake_coupling_np.ndarray) or value.shape != shape or value.dtype != _m4_mountain_lake_coupling_np.int64:
            raise ValueError("typed anchor/HRU grid required")
    if (not isinstance(node_downstream, _m4_mountain_lake_coupling_np.ndarray) or node_downstream.ndim != 1 or
            node_downstream.dtype != _m4_mountain_lake_coupling_np.int64 or not 1 <= node_downstream.size <= 2048 or
            type(hrus) is not int or not 1 <= hrus <= 256 or
            isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float)) or
            not _m4_mountain_lake_coupling_math.isfinite(spacing_m) or not 0 < spacing_m <= 100000):
        raise ValueError("invalid nodes/HRUs/spacing")
    _m4_mountain_lake_coupling_order(node_downstream)
    active = calculation_mask.ravel()
    anchor = anchor_node.ravel()
    hru = cell_owner.ravel()
    if ((anchor < -1).any() or (anchor >= node_downstream.size).any() or
            (anchor[~active] != -1).any() or (hru[~active] != -1).any() or
            (hru[active] < 0).any() or (hru[active] >= hrus).any()):
        raise ValueError("invalid node or unique HRU ownership")
    if set(anchor[active & (anchor >= 0)].tolist()) != set(range(node_downstream.size)):
        raise ValueError("every dynamic node needs an explicit geometric anchor")
    receiver_flat = receiver.ravel()
    cell_node = anchor.copy()
    for current in _m4_mountain_lake_coupling_order(receiver_flat)[::-1]:
        if active[current] and cell_node[current] < 0 and receiver_flat[current] >= 0:
            cell_node[current] = cell_node[receiver_flat[current]]
    if (cell_node[active] < 0).any():
        raise ValueError("unmapped local contributing area")
    for current in _m4_mountain_lake_coupling_np.flatnonzero(active & (anchor >= 0)):
        target = receiver_flat[current]
        node = anchor[current]
        if target == -1:
            if node_downstream[node] != -1:
                raise ValueError("terminal anchor/node topology mismatch")
        elif cell_node[target] != node and node_downstream[node] != cell_node[target]:
            raise ValueError("node topology disagrees with first downstream anchor")
    counts = _m4_mountain_lake_coupling_np.bincount(cell_node[active] * hrus + hru[active],
        minlength=node_downstream.size * hrus).reshape(node_downstream.size, hrus)
    area = _m4_mountain_lake_coupling_np.bincount(hru[active], minlength=hrus).astype(_m4_mountain_lake_coupling_np.float64) * spacing_m**2
    if (area <= 0).any():
        raise ValueError("empty HRU")
    return {"cell_node": _m4_mountain_lake_coupling_readonly(cell_node.reshape(shape)), "allocation_counts": _m4_mountain_lake_coupling_readonly(counts),
            "area_m2": _m4_mountain_lake_coupling_readonly(area), "node_order": _m4_mountain_lake_coupling_readonly(_m4_mountain_lake_coupling_order(node_downstream))}

# --- terrain_pipeline/mountain_lake_coupling.py:120 ---
def _topology(source, topology, cell_owner, hrus, selection=None):
    from terrain_pipeline.common_infra import validate_source as _m4_mountain_lake_coupling_validate_source
    _m4_mountain_lake_coupling_validate_source(source)
    required = {"receiver", "anchor_node", "node_downstream", "node_kind", "node_boundary_type",
                "tau_s", "source_identity", "geometry_identity", "geometry_passed", "boundary_policy"}
    if set(topology) != required or topology["source_identity"] != source["identity_sha256"]:
        raise ValueError("same-source explicit topology required")
    if (type(topology["geometry_passed"]) is not bool or
            not isinstance(topology["geometry_identity"], str) or len(topology["geometry_identity"]) != 64 or
            topology["boundary_policy"] != source["metadata"]["boundary"]["policy"]):
        raise ValueError("geometry/boundary evidence required")
    downstream = topology["node_downstream"]
    count = downstream.size
    for key in ("node_kind", "node_boundary_type"):
        if not isinstance(topology[key], list) or len(topology[key]) != count:
            raise ValueError("invalid node records")
    if any(kind not in {"river", "lake", "terminal"} for kind in topology["node_kind"]):
        raise ValueError("invalid node kind")
    tau = topology["tau_s"]
    if (not isinstance(tau, _m4_mountain_lake_coupling_np.ndarray) or tau.shape != (count,) or tau.dtype != _m4_mountain_lake_coupling_np.float64 or
            not _m4_mountain_lake_coupling_np.isfinite(tau).all() or (tau <= 0).any() or (tau > 1e12).any()):
        raise ValueError("finite positive river residence times required")
    for node, target in enumerate(downstream):
        boundary = topology["node_boundary_type"][node]
        if (target == -1 and boundary not in BOUNDARIES) or (target >= 0 and boundary is not None):
            raise ValueError("explicit terminal type required")
        if boundary == "ocean_open_boundary":
            raise ValueError("natural coast evidence is not supported by this finite-window adapter")
        if topology["node_kind"][node] == "terminal" and target != -1:
            raise ValueError("terminal cannot have downstream node")
    mask = source["arrays"]["hydrology_mask"] if selection is None else validate_selection(source, topology, selection)
    return local_allocation(topology["receiver"], topology["anchor_node"], cell_owner,
        mask, downstream, spacing_m=source["metadata"]["spacing_m"], hrus=hrus)

# --- terrain_pipeline/mountain_lake_coupling.py:154 ---
def geometry_binding(source, topology, geometry, selection=None):
    """Bind externally accepted B payload, not caller acceptance booleans."""
    from terrain_pipeline.common_infra import identity as _m4_mountain_lake_coupling_identity
    if not isinstance(geometry, dict) or set(geometry) != {"arrays", "metadata"}:
        raise ValueError("externally accepted geometry payload required")
    arrays = geometry["arrays"]
    from terrain_pipeline.lake import validate_mountain_geometry as validate_mountain_geometry
    from terrain_pipeline.lake import certify_no_cut_groups as certify_no_cut_groups

    binding = geometry["metadata"].get("source_binding")
    if not isinstance(binding, dict) or binding.get("source_identity") != source["identity_sha256"]:
        raise ValueError("geometry source binding identity required")
    if (geometry["metadata"]["spacing_m"] != source["metadata"]["spacing_m"] or
            geometry["metadata"]["origin_m_xz"] != source["metadata"]["origin_m_xz"] or
            source["metadata"]["boundary"]["policy"] != "all_edges_open"):
        raise ValueError("geometry/source grid or boundary policy mismatch")
    validate_mountain_geometry(geometry, trusted_height=source["arrays"]["height_m"], source_binding=binding)
    if _m4_mountain_lake_coupling_identity(arrays, geometry["metadata"]) != topology["geometry_identity"]:
        raise ValueError("external geometry payload identity mismatch")
    if not _m4_mountain_lake_coupling_np.array_equal(arrays["H0_m"], source["arrays"]["height_m"]):
        raise ValueError("geometry H0 differs from trusted source")
    if not _m4_mountain_lake_coupling_np.array_equal(arrays["receiver"].reshape(topology["receiver"].shape), topology["receiver"]):
        raise ValueError("geometry receiver mismatch")
    mask = source["arrays"]["hydrology_mask"] if selection is None else validate_selection(source, topology, selection)
    no_cut = certify_no_cut_groups(geometry)
    if not no_cut["cell_valid_mask"][mask].all():
        raise ValueError("selected contribution domain lacks no-cut static geometry certificate")
    lake_cells = mask & (arrays["lake_id"] > 0)
    for cell in _m4_mountain_lake_coupling_np.flatnonzero(lake_cells):
        node = int(topology["anchor_node"].flat[cell])
        if node < 0 or topology["node_kind"][node] != "lake":
            raise ValueError("every source lake cell must map to a lake node, never a river")
    for node, kind in enumerate(topology["node_kind"]):
        if kind == "lake":
            labels = _m4_mountain_lake_coupling_np.unique(arrays["lake_id"][topology["anchor_node"] == node])
            if labels.size != 1 or labels[0] <= 0:
                raise ValueError("lake node must represent one explicit geometry basin")
    return True

# --- terrain_pipeline/mountain_lake_coupling.py:192 ---
def build_group_topology(source, geometry, group):
    """Keep every dry route cell and every lake in a complete contribution group."""
    from terrain_pipeline.common_infra import identity as _m4_mountain_lake_coupling_identity
    arrays = geometry["arrays"]
    if type(group) is not int or not 0 <= group < arrays["outlet_cells"].size:
        raise ValueError("invalid group index")
    receiver = arrays["receiver"].reshape(source["arrays"]["height_m"].shape)
    terminal = int(arrays["outlet_cells"][group])
    mask, proof = contribution_mask(receiver, source["arrays"]["hydrology_mask"], terminal)
    if not _m4_mountain_lake_coupling_np.array_equal(mask, arrays["outlet_owner"] == group):
        raise ValueError("independent global owner disagrees with selected geometry group")
    selection = make_selection(source, receiver, mask, proof=proof)
    labels = arrays["lake_id"]
    lakes = _m4_mountain_lake_coupling_np.unique(labels[mask])
    lakes = lakes[lakes > 0]
    dry_cells = _m4_mountain_lake_coupling_np.flatnonzero(mask.ravel() & (labels.ravel() == 0))
    count = lakes.size + dry_cells.size
    if not 1 <= count <= 2048:
        raise ValueError("complete group exceeds dynamic node budget; no terminal dropping")
    anchor = _m4_mountain_lake_coupling_np.full(mask.shape, -1, _m4_mountain_lake_coupling_np.int64)
    kinds = []
    lake_nodes = {}
    for node, lake in enumerate(lakes):
        anchor[mask & (labels == lake)] = node
        lake_nodes[int(lake)] = node
        kinds.append("lake")
    anchor.ravel()[dry_cells] = _m4_mountain_lake_coupling_np.arange(lakes.size, count)
    kinds.extend(["river"] * dry_cells.size)
    downstream = _m4_mountain_lake_coupling_np.full(count, -1, _m4_mountain_lake_coupling_np.int64)
    tau = _m4_mountain_lake_coupling_np.full(count, source["metadata"]["spacing_m"], _m4_mountain_lake_coupling_np.float64)
    for lake, node in lake_nodes.items():
        downstream[node] = int(anchor.flat[arrays["spill_outside"][lake - 1]])
        if downstream[node] < 0:
            raise ValueError("lake spill exits complete group unexpectedly")
    for cell in dry_cells:
        target = int(receiver.flat[cell])
        if target >= 0:
            downstream[anchor.flat[cell]] = anchor.flat[target]
    boundaries = ["external_open_boundary" if target < 0 else None for target in downstream]
    topology = {"receiver": receiver.copy(), "anchor_node": anchor, "node_downstream": downstream,
        "node_kind": kinds, "node_boundary_type": boundaries, "tau_s": tau,
        "source_identity": source["identity_sha256"], "geometry_identity": _m4_mountain_lake_coupling_identity(arrays, geometry["metadata"]),
        "geometry_passed": True, "boundary_policy": "all_edges_open"}
    geometry_binding(source, topology, geometry, selection)
    return topology, selection, lake_nodes

# --- terrain_pipeline/mountain_lake_coupling.py:238 ---
def group_lake_specs(source, geometry, topology, lake_nodes, *, steps, coefficient=1.7):
    """Uncalibrated broad-crested weir Q=C*full-cell width*head**1.5, bounded by shore."""
    if not 0 < coefficient <= 3 or type(steps) is not int or not 1 <= steps <= 3000:
        raise ValueError("invalid explicit weir parameters")
    arrays = geometry["arrays"]
    height = source["arrays"]["height_m"]
    specs = {}
    for lake, node in lake_nodes.items():
        basin = arrays["lake_id"] == lake
        outside = int(arrays["spill_outside"][lake - 1])
        spill = _m4_mountain_lake_coupling_np.array(divmod(outside, height.shape[1]), _m4_mountain_lake_coupling_np.int64)
        path_flat = [outside]
        while arrays["receiver"][path_flat[-1]] >= 0:
            target = int(arrays["receiver"][path_flat[-1]])
            if arrays["lake_id"].flat[target] > 0:
                path_flat.append(target)
                break
            path_flat.append(target)
        path = _m4_mountain_lake_coupling_np.column_stack(_m4_mountain_lake_coupling_np.unravel_index(path_flat, height.shape)).astype(_m4_mountain_lake_coupling_np.int64)
        shore = _m4_mountain_lake_coupling_np.zeros(height.shape, bool)
        for row, column in _m4_mountain_lake_coupling_np.argwhere(basin):
            for delta_row, delta_column in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                neighbor = row + delta_row, column + delta_column
                if not basin[neighbor]:
                    shore[neighbor] = True
        shore[tuple(spill)] = False
        spill_stage = float(height[tuple(spill)])
        max_stage = float(height[shore].min())
        if max_stage <= spill_stage:
            raise ValueError("no unique-sill positive headroom; multi-sill modeling required")
        stages = _m4_mountain_lake_coupling_np.linspace(spill_stage, max_stage, 65)
        flow = coefficient * source["metadata"]["spacing_m"] * (stages - spill_stage)**1.5
        legal = _m4_mountain_lake_coupling_np.zeros(height.shape, bool)
        legal[tuple(path[-1])] = True
        specs[node] = {"basin_mask": basin, "legal_spill_grid_zx": spill,
            "downstream_path_grid_zx": path, "domain_mask": source["arrays"]["hydrology_mask"],
            "protected_mask": arrays["protected_mask"], "legal_outlet_mask": legal,
            "single_pool_certified": True, "geometry_identity": topology["geometry_identity"],
            "recipe": {"initial_stage_m": float(height[basin].min()), "loss_m3_s": (0.,) * steps,
                "rating_stage_m": tuple(stages), "rating_outflow_m3_s": tuple(flow),
                "max_stage_m": max_stage, "volume_abs_tolerance_m3": 1e-9, "volume_rel_tolerance": 1e-12}}
    return specs

# --- terrain_pipeline/mountain_lake_coupling.py:282 ---
def make_selection(source, receiver, mask, *, proof):
    """Selection identity is separate from the immutable full height-source identity."""
    from terrain_pipeline.common_infra import identity as _m4_mountain_lake_coupling_identity
    from terrain_pipeline.common_infra import readonly as _m4_mountain_lake_coupling_readonly
    from terrain_pipeline.common_infra import validate_source as _m4_mountain_lake_coupling_validate_source
    from terrain_pipeline.runoff import _hash as _m4_mountain_lake_coupling_hash
    from terrain_pipeline.runoff import _json as _m4_mountain_lake_coupling_json
    from terrain_pipeline.runoff import _strict_json as _m4_mountain_lake_coupling_strict_json
    _m4_mountain_lake_coupling_validate_source(source)
    if (not isinstance(mask, _m4_mountain_lake_coupling_np.ndarray) or mask.dtype != bool or mask.shape != source["arrays"]["height_m"].shape or
            not mask.any() or (mask & ~source["arrays"]["hydrology_mask"]).any()):
        raise ValueError("invalid selection domain")
    arrays = {"mask": _m4_mountain_lake_coupling_readonly(mask)}
    metadata = {"source_identity": source["identity_sha256"], "receiver_sha256": _m4_mountain_lake_coupling_hash(receiver),
                "proof": _m4_mountain_lake_coupling_strict_json(_m4_mountain_lake_coupling_json(proof)), "hydrological_closure_certified": False}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_mountain_lake_coupling_identity(arrays, metadata)}

# --- terrain_pipeline/mountain_lake_coupling.py:294 ---
def validate_selection(source, topology, selection):
    from terrain_pipeline.common_infra import identity as _m4_mountain_lake_coupling_identity
    from terrain_pipeline.runoff import _hash as _m4_mountain_lake_coupling_hash
    from terrain_pipeline.runoff import _order as _m4_mountain_lake_coupling_order
    arrays, metadata = selection["arrays"], selection["metadata"]
    if (set(arrays) != {"mask"} or selection["identity_sha256"] != _m4_mountain_lake_coupling_identity(arrays, metadata) or
            metadata["source_identity"] != source["identity_sha256"] or
            metadata["receiver_sha256"] != _m4_mountain_lake_coupling_hash(topology["receiver"]) or
            metadata["hydrological_closure_certified"] is not False):
        raise ValueError("selection/source/topology binding mismatch")
    mask = arrays["mask"]
    if mask.dtype != bool or mask.shape != source["arrays"]["height_m"].shape or not mask.any():
        raise ValueError("invalid selected domain")
    if (mask & ~source["arrays"]["hydrology_mask"]).any():
        raise ValueError("selection exceeds source calculation domain")
    proof = metadata["proof"]
    receiver = topology["receiver"].ravel()
    _m4_mountain_lake_coupling_order(receiver)
    active = source["arrays"]["hydrology_mask"].ravel()
    selected = mask.ravel()
    moving = _m4_mountain_lake_coupling_np.flatnonzero(active & (receiver >= 0))
    if not active[receiver[moving]].all():
        raise ValueError("full source donor exits declared calculation domain")
    if (selected[moving] != selected[receiver[moving]]).any():
        raise ValueError("selection drops upstream contributions or downstream path")
    terminals = _m4_mountain_lake_coupling_np.flatnonzero(selected & (receiver == -1))
    if (terminals.size != 1 or proof.get("terminal_flat") != int(terminals[0]) or
            proof.get("contributing_cells") != int(selected.sum()) or
            proof.get("mask_sha256") != _m4_mountain_lake_coupling_hash(mask) or
            proof.get("full_receiver_sha256") != _m4_mountain_lake_coupling_hash(topology["receiver"]) or
            proof.get("full_domain_sha256") != _m4_mountain_lake_coupling_hash(source["arrays"]["hydrology_mask"]) or
            proof.get("upstream_complete_within_finite_window") is not True or
            proof.get("hydrological_closure_certified") is not False):
        raise ValueError("selection complete-contribution certificate mismatch")
    return mask

# --- terrain_pipeline/mountain_lake_coupling.py:328 ---
def single_pool_proof(height, basin, spill, path, domain, protected, legal, *, max_stage_m):
    """Every strict sublevel event must be connected, including intermediate saddles."""
    from terrain_pipeline.runoff import _hash as _m4_mountain_lake_coupling_hash
    shape = height.shape
    for mask in (basin, domain, protected, legal):
        if not isinstance(mask, _m4_mountain_lake_coupling_np.ndarray) or mask.shape != shape or mask.dtype != bool:
            raise ValueError("typed single-pool geometry masks required")
    if not basin.any() or (basin & (~domain | protected)).any():
        raise ValueError("pool outside legal unprotected domain")
    if basin[0].any() or basin[-1].any() or basin[:, 0].any() or basin[:, -1].any():
        raise ValueError("pool touches truncated boundary")
    points = _m4_mountain_lake_coupling_np.asarray(path)
    sill = _m4_mountain_lake_coupling_np.asarray(spill)
    if (sill.shape != (2,) or sill.dtype.kind not in "iu" or points.ndim != 2 or
            points.shape[1] != 2 or points.dtype.kind not in "iu" or not 2 <= len(points) <= height.size or
            (points < 0).any() or (points[:, 0] >= shape[0]).any() or (points[:, 1] >= shape[1]).any() or
            (sill < 0).any() or sill[0] >= shape[0] or sill[1] >= shape[1] or
            not _m4_mountain_lake_coupling_np.array_equal(points[0], sill)):
        raise ValueError("invalid explicit spill/path")
    spill_point = tuple(sill)
    if basin[spill_point] or not domain[spill_point] or protected[spill_point]:
        raise ValueError("spill must be outside basin inside legal domain")
    neighbors = ((-1, 0), (1, 0), (0, -1), (0, 1))
    if not any(0 <= sill[0] + delta_row < shape[0] and 0 <= sill[1] + delta_column < shape[1] and
            basin[sill[0] + delta_row, sill[1] + delta_column] for delta_row, delta_column in neighbors):
        raise ValueError("spill must touch basin")
    rows, columns = points.T
    if (not legal[tuple(points[-1])] or not domain[rows, columns].all() or
            protected[rows, columns].any() or basin[rows, columns].any() or
            _m4_mountain_lake_coupling_np.any(_m4_mountain_lake_coupling_np.abs(_m4_mountain_lake_coupling_np.diff(points, axis=0)).sum(axis=1) != 1) or
            len(set(map(tuple, points))) != len(points) or
            (_m4_mountain_lake_coupling_np.diff(height[rows, columns]) > 0).any() or
            height[tuple(points[-1])] >= height[spill_point]):
        raise ValueError("invalid downstream sill/path/closure evidence")
    if not _m4_mountain_lake_coupling_math.isfinite(max_stage_m) or max_stage_m < height[spill_point]:
        raise ValueError("invalid maximum pool stage")
    if (height[basin] >= height[spill_point]).any():
        raise ValueError("basin includes dry spill-height cells")
    for row, column in _m4_mountain_lake_coupling_np.argwhere(basin):
        for delta_row, delta_column in neighbors:
            neighbor = (row + delta_row, column + delta_column)
            if not basin[neighbor] and neighbor != spill_point and height[neighbor] < max_stage_m:
                raise ValueError("unmodeled low shore/saddle")
    cells = _m4_mountain_lake_coupling_np.flatnonzero(basin.ravel())
    ordered = cells[_m4_mountain_lake_coupling_np.argsort(height.ravel()[cells], kind="stable")]
    parent = _m4_mountain_lake_coupling_np.full(height.size, -1, _m4_mountain_lake_coupling_np.int64)
    active = _m4_mountain_lake_coupling_np.zeros(height.size, bool)
    components = 0

    def root(cell):
        while parent[cell] != cell:
            parent[cell] = parent[parent[cell]]
            cell = parent[cell]
        return cell

    position = 0
    events = 0
    while position < ordered.size:
        level = height.flat[ordered[position]]
        end = position + 1
        while end < ordered.size and height.flat[ordered[end]] == level:
            end += 1
        for cell in ordered[position:end]:
            active[cell] = True
            parent[cell] = cell
            components += 1
            row, column = divmod(int(cell), shape[1])
            for delta_row, delta_column in neighbors:
                next_row, next_column = row + delta_row, column + delta_column
                if 0 <= next_row < shape[0] and 0 <= next_column < shape[1]:
                    neighbor = next_row * shape[1] + next_column
                    if active[neighbor]:
                        first, second = root(int(cell)), root(neighbor)
                        if first != second:
                            parent[second] = first
                            components -= 1
        events += 1
        if components != 1:
            raise ValueError(f"disconnected sublevel pool at event {events}, above {level} m")
        position = end
    return {"all_sublevel_events_connected": True, "events_checked": events,
            "basin_cells": int(cells.size), "basin_sha256": _m4_mountain_lake_coupling_hash(basin)}

# --- terrain_pipeline/mountain_lake_coupling.py:411 ---
def couple_rainfall(source, topology, cell_owner, rain_mm_h, *, dt_s, geometry,
                   parameters=None, lakes=None, selection=None, surface_rain=False,
                   lake_evaporation_mm_h=0.0):
    """Solve DAG in topological order, lakes via existing bounded single-pool solver."""
    from terrain_pipeline.common_infra import identity as _m4_mountain_lake_coupling_identity
    from terrain_pipeline.common_infra import readonly as _m4_mountain_lake_coupling_readonly
    from terrain_pipeline.runoff import _hash as _m4_mountain_lake_coupling_hash
    from terrain_pipeline.runoff import _json as _m4_mountain_lake_coupling_json
    from terrain_pipeline.runoff import _strict_json as _m4_mountain_lake_coupling_strict_json
    from terrain_pipeline.runoff import preflight as _m4_mountain_lake_coupling_preflight
    from terrain_pipeline.runoff import simulate_rainfall_runoff as _m4_mountain_lake_coupling_simulate_rainfall_runoff
    if not isinstance(rain_mm_h, _m4_mountain_lake_coupling_np.ndarray) or rain_mm_h.ndim != 2:
        raise ValueError("rain [step,HRU] required")
    steps, hrus = rain_mm_h.shape
    _m4_mountain_lake_coupling_preflight(steps, source["arrays"]["height_m"].size, hrus, topology["node_downstream"].size)
    mapping = _topology(source, topology, cell_owner, hrus, selection)
    if not topology["geometry_passed"]:
        return {"status": "diagnostic_geometry_not_passed", "source_identity": source["identity_sha256"],
                "geometry_identity": topology["geometry_identity"], "mapping": mapping,
                "dynamic_water_solved": False}
    geometry_binding(source, topology, geometry, selection)
    mask = source["arrays"]["hydrology_mask"] if selection is None else selection["arrays"]["mask"]
    count = topology["node_downstream"].size
    lake_specs = {} if lakes is None else lakes
    expected_lakes = {node for node, kind in enumerate(topology["node_kind"]) if kind == "lake"}
    if set(lake_specs) != expected_lakes:
        raise ValueError("every lake needs explicit single-pool geometry/rating")
    if len(expected_lakes) * source["arrays"]["height_m"].size > 2_000_000:
        raise ValueError("retained single-pool geometry resource budget exceeded")
    if type(surface_rain) is not bool or isinstance(lake_evaporation_mm_h, bool) or not isinstance(lake_evaporation_mm_h, (int, float)) or not _m4_mountain_lake_coupling_math.isfinite(lake_evaporation_mm_h) or not 0 <= lake_evaporation_mm_h <= 1000:
        raise ValueError("invalid surface rainfall/evaporation forcing")
    if not surface_rain and lake_evaporation_mm_h != 0:
        raise ValueError("surface evaporation requires explicit surface rainfall partition")
    land_counts = mapping["allocation_counts"].copy()
    lake_counts = _m4_mountain_lake_coupling_np.zeros_like(land_counts)
    if surface_rain:
        for node in expected_lakes:
            basin = topology["anchor_node"] == node
            labels = cell_owner[basin]
            lake_counts[node] = _m4_mountain_lake_coupling_np.bincount(labels, minlength=hrus)
        land_counts -= lake_counts
    cell_area = source["metadata"]["spacing_m"]**2
    land_area = land_counts.sum(axis=0).astype(_m4_mountain_lake_coupling_np.float64) * cell_area
    if (land_area <= 0).any():
        raise ValueError("surface partition requires every HRU to retain positive land area")
    runoff = _m4_mountain_lake_coupling_simulate_rainfall_runoff(rain_mm_h, land_area, dt_s=dt_s,
        source_id=source["identity_sha256"], parameters=parameters)
    fractions = land_counts * cell_area / land_area
    lateral = runoff["local_q_m3_s"] @ fractions.T * dt_s
    direct_rain = rain_mm_h @ (lake_counts * cell_area).T / 1000. * dt_s / 3600.
    evaporation = lake_counts.sum(axis=1)[None, :] * cell_area / 1000. * lake_evaporation_mm_h * dt_s / 3600.
    evaporation = _m4_mountain_lake_coupling_np.repeat(evaporation, steps, axis=0)
    lateral += direct_rain
    incoming = lateral.copy()
    outflow = _m4_mountain_lake_coupling_np.zeros((steps, count), _m4_mountain_lake_coupling_np.float64)
    storage = _m4_mountain_lake_coupling_np.zeros((steps + 1, count), _m4_mountain_lake_coupling_np.float64)
    lake_stage = _m4_mountain_lake_coupling_np.full((steps + 1, count), _m4_mountain_lake_coupling_np.nan, _m4_mountain_lake_coupling_np.float64)
    losses = _m4_mountain_lake_coupling_np.zeros((steps, count), _m4_mountain_lake_coupling_np.float64)
    lake_evidence = {}
    lake_arrays = {}
    for node in mapping["node_order"]:
        node = int(node)
        kind = topology["node_kind"][node]
        target = int(topology["node_downstream"][node])
        if kind == "lake":
            spec = lake_specs[node]
            required = {"basin_mask", "legal_spill_grid_zx", "downstream_path_grid_zx",
                        "domain_mask", "protected_mask", "legal_outlet_mask", "recipe",
                        "single_pool_certified", "geometry_identity"}
            if (set(spec) != required or spec["single_pool_certified"] is not True or
                    spec["geometry_identity"] != topology["geometry_identity"] or
                    not isinstance(spec["recipe"], dict)):
                raise ValueError("single-pool geometry evidence required; merged dry saddles forbidden")
            if (spec["basin_mask"].shape != topology["anchor_node"].shape or
                    not _m4_mountain_lake_coupling_np.array_equal(spec["basin_mask"], topology["anchor_node"] == node)):
                raise ValueError("lake basin must match all node anchors exactly")
            if (not _m4_mountain_lake_coupling_np.array_equal(spec["domain_mask"], source["arrays"]["hydrology_mask"]) or
                    not _m4_mountain_lake_coupling_np.array_equal(spec["protected_mask"], geometry["arrays"]["protected_mask"])):
                raise ValueError("lake domain/protection must match trusted source geometry")
            _check_legal_mask(spec["legal_outlet_mask"], spec["downstream_path_grid_zx"])
            recipe_values = dict(spec["recipe"], dt_s=dt_s,
                inflow_m3_s=tuple(incoming[:, node] / dt_s))
            recipe_values["loss_m3_s"] = tuple(_m4_mountain_lake_coupling_np.asarray(spec["recipe"]["loss_m3_s"]) + evaporation[:, node] / dt_s)
            recipe = LakeRoutingRecipe(**recipe_values)
            proof = single_pool_proof(source["arrays"]["height_m"], spec["basin_mask"],
                spec["legal_spill_grid_zx"], spec["downstream_path_grid_zx"], spec["domain_mask"],
                spec["protected_mask"], spec["legal_outlet_mask"], max_stage_m=recipe.max_stage_m)
            _check_pool_path(topology["receiver"], spec["downstream_path_grid_zx"], spec["legal_outlet_mask"],
                anchor_node=topology["anchor_node"], node_kind=topology["node_kind"], current_node=node,
                node_downstream=topology["node_downstream"])
            for key in ("domain_mask", "protected_mask", "legal_outlet_mask"):
                lake_arrays[f"lake_{node}_{key}"] = spec[key].copy()
            spacing = source["metadata"]["spacing_m"]
            origin = source["metadata"]["origin_m_xz"]
            lake = evaluate_lake_routing(source["arrays"]["height_m"], spec["basin_mask"],
                spec["legal_spill_grid_zx"], spacing, spacing, source["identity_sha256"], recipe,
                spec["downstream_path_grid_zx"], spec["domain_mask"], spec["protected_mask"],
                spec["legal_outlet_mask"], origin[0], origin[1], "sea_zero_m")
            if not lake["scenario_feasible"]:
                return {"status": "diagnostic_lake_failed", "source_identity": source["identity_sha256"],
                    "geometry_identity": topology["geometry_identity"], "failed_node": node,
                    "lake_failure": lake, "dynamic_water_solved": False}
            outflow[:, node] = lake["arrays"]["step_outflow_volume_m3"]
            storage[:, node] = lake["arrays"]["storage_m3"]
            lake_stage[:, node] = lake["arrays"]["stage_m"]
            losses[:, node] = lake["arrays"]["step_loss_volume_m3"]
            lake_evidence[str(node)] = {"identity_sha256": lake["identity_sha256"],
                "summary": lake["summary"], "input": lake["input"],
                "basin_sha256": _m4_mountain_lake_coupling_hash(spec["basin_mask"]), "single_pool_proof": proof,
                "pool_geometry": {key: value.tolist() for key, value in lake["arrays"].items()
                    if key in {"legal_spill_grid_zx", "downstream_path_grid_zx"}}}
        elif topology["node_boundary_type"][node] == "closed_terminal":
            storage[1:, node] = _m4_mountain_lake_coupling_np.cumsum(incoming[:, node])
        else:
            ratio = dt_s / topology["tau_s"][node]
            for step in range(steps):
                storage[step + 1, node] = (storage[step, node] + incoming[step, node]) / (1 + ratio)
                outflow[step, node] = ratio * storage[step + 1, node]
        if target >= 0:
            incoming[:, target] += outflow[:, node]
    for node in expected_lakes:
        path = lake_specs[node]["downstream_path_grid_zx"]
        receiver_node = int(topology["anchor_node"][tuple(path[-1])])
        if receiver_node >= 0 and topology["node_kind"][receiver_node] == "lake":
            sill = float(source["arrays"]["height_m"][tuple(path[0])])
            submerged = _m4_mountain_lake_coupling_np.flatnonzero(lake_stage[:, receiver_node] > sill + 1e-9)
            if submerged.size:
                return {"status": "diagnostic_receiving_pool_submerges_free_weir",
                    "source_identity": source["identity_sha256"], "geometry_identity": topology["geometry_identity"],
                    "failed_node": node, "receiving_node": receiver_node, "failed_state": int(submerged[0]),
                    "sill_stage_m": sill, "receiving_stage_m": float(lake_stage[submerged[0], receiver_node]),
                    "dynamic_water_solved": False, "whole_system_prefix_valid": False,
                    "limitation": "independent DAG trajectories are not a committed coupled prefix under tailwater"}
    boundary_nodes = _m4_mountain_lake_coupling_np.flatnonzero((topology["node_downstream"] < 0) & _m4_mountain_lake_coupling_np.array([
        boundary == "external_open_boundary" for boundary in topology["node_boundary_type"]]))
    arrays = {"height_m": source["arrays"]["height_m"],
        "hydrology_mask": mask, "cell_owner": cell_owner,
        **{key: topology[key] for key in ("receiver", "anchor_node", "node_downstream", "tau_s")},
        **mapping, "lateral_volume_m3": lateral, "incoming_volume_m3": incoming,
        "land_allocation_counts": land_counts, "surface_allocation_counts": lake_counts,
        "surface_rain_volume_m3": direct_rain, "surface_evaporation_volume_m3": evaporation,
        "outflow_volume_m3": outflow, "storage_m3": storage, "lake_stage_m": lake_stage,
        "lake_loss_volume_m3": losses, "boundary_nodes": boundary_nodes,
        "boundary_volume_m3": outflow[:, boundary_nodes],
        "total_boundary_volume_m3": outflow[:, boundary_nodes].sum(axis=1)}
    arrays.update(lake_arrays)
    arrays.update({"runoff_" + key: value for key, value in runoff.items() if key != "metadata"})
    metadata = _m4_mountain_lake_coupling_strict_json(_m4_mountain_lake_coupling_json({"schema": COUPLING_SCHEMA, "status": "finite_window_engineering_scenario",
        "source_identity": source["identity_sha256"], "source_metadata": source["metadata"],
        "geometry_identity": topology["geometry_identity"], "geometry_passed": True,
        "node_kind": topology["node_kind"], "node_boundary_type": topology["node_boundary_type"],
        "boundary_policy": topology["boundary_policy"], "runoff_metadata": runoff["metadata"],
        "lake_evidence": lake_evidence, "river_stage_solved": False,
        "selection_metadata": None if selection is None else selection["metadata"],
        "selection_identity": None if selection is None else selection["identity_sha256"],
        "rain_support": "fixed_lake_footprint_direct_rain" if surface_rain else "fixed_land_conceptual_runoff_all_cells",
        "lake_evaporation_mm_h": float(lake_evaporation_mm_h),
        "surface_scope": "fixed_full_basin_footprint_even_when_dry; prescribed_evaporation_dry_deficit_fails; no_dynamic_wet_area",
        "hydrological_closure_certified": False}))
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_mountain_lake_coupling_identity(arrays, metadata)}
    validate_coupling(result)
    result["arrays"] = {key: _m4_mountain_lake_coupling_readonly(value) for key, value in arrays.items()}
    return result

# --- terrain_pipeline/mountain_lake_coupling.py:569 ---
def coupling_equal(actual, expected, name, *, atol=1e-8, rtol=2e-11):
    if not _m4_mountain_lake_coupling_np.allclose(actual, expected, atol=atol, rtol=rtol, equal_nan=True):
        raise ValueError("coupling semantic mismatch: " + name)

# --- terrain_pipeline/mountain_lake_coupling.py:574 ---
def _check_pool_path(receiver, path, legal, *, anchor_node, node_kind, current_node, node_downstream):
    points = _m4_mountain_lake_coupling_np.asarray(path)
    flat = points[:, 0] * receiver.shape[1] + points[:, 1]
    if not _m4_mountain_lake_coupling_np.array_equal(receiver.ravel()[flat[:-1]], flat[1:]):
        raise ValueError("lake downstream path must follow same-source topology receiver")
    if not legal[tuple(points[-1])]:
        raise ValueError("lake path must reach an explicit destination")
    endpoint_node = int(anchor_node.flat[flat[-1]])
    for cell in flat[:-1]:
        node = int(anchor_node.flat[cell])
        if node >= 0 and node_kind[node] == "lake":
            raise ValueError("downstream path may only enter a receiving lake at its endpoint")
    if receiver.ravel()[flat[-1]] != -1:
        if endpoint_node < 0 or node_kind[endpoint_node] != "lake" or endpoint_node == current_node:
            raise ValueError("lake path must end at a topology terminal or distinct receiving lake")
    path_nodes = anchor_node.ravel()[flat]
    previous = current_node
    for node in path_nodes:
        node = int(node)
        if node < 0:
            continue
        if node != previous:
            if int(node_downstream[previous]) != node:
                raise ValueError("lake path node cascade disagrees with DAG")
            previous = node

# --- terrain_pipeline/mountain_lake_coupling.py:601 ---
def _check_legal_mask(legal, path):
    expected = _m4_mountain_lake_coupling_np.zeros(legal.shape, bool)
    expected[tuple(_m4_mountain_lake_coupling_np.asarray(path)[-1])] = True
    if legal.dtype != bool or not _m4_mountain_lake_coupling_np.array_equal(legal, expected):
        raise ValueError("legal destination mask must contain exactly the explicit path endpoint")

# --- terrain_pipeline/mountain_lake_coupling.py:608 ---
def _free_weir_tailwater(sill_stage_m, receiving_stage_m):
    if not _m4_mountain_lake_coupling_np.isfinite(receiving_stage_m).all() or (receiving_stage_m > sill_stage_m + 1e-9).any():
        raise ValueError("receiving_pool_submerges_free_weir")

# --- terrain_pipeline/mountain_lake_coupling.py:613 ---
def validate_coupling(result, *, source=None, topology=None, geometry=None, selection=None):
    """Static equations only: no preparation, inference or dynamic solver replay."""
    from terrain_pipeline.common_infra import identity as _m4_mountain_lake_coupling_identity
    from terrain_pipeline.common_infra import validate_source as _m4_mountain_lake_coupling_validate_source
    from terrain_pipeline.runoff import RUNOFF_ARRAY_KEYS as _m4_mountain_lake_coupling_RUNOFF_KEYS
    from terrain_pipeline.runoff import _hash as _m4_mountain_lake_coupling_hash
    from terrain_pipeline.runoff import _order as _m4_mountain_lake_coupling_order
    from terrain_pipeline.runoff import preflight as _m4_mountain_lake_coupling_preflight
    from terrain_pipeline.runoff import validate_rainfall_runoff_result as _m4_mountain_lake_coupling_validate_rainfall_runoff_result
    arrays, meta = result["arrays"], result["metadata"]
    if (set(meta) != META_KEYS or meta["schema"] != COUPLING_SCHEMA or meta["geometry_passed"] is not True or
            meta["status"] != "finite_window_engineering_scenario" or meta["river_stage_solved"] is not False or
            meta["hydrological_closure_certified"] is not False or
            result["identity_sha256"] != _m4_mountain_lake_coupling_identity(arrays, meta)):
        raise ValueError("coupling identity/status mismatch")
    expected_masks = {f"lake_{node}_{key}" for node, kind in enumerate(meta["node_kind"]) if kind == "lake"
        for key in ("domain_mask", "protected_mask", "legal_outlet_mask")}
    if set(arrays) != BASE_KEYS | {"runoff_" + key for key in _m4_mountain_lake_coupling_RUNOFF_KEYS} | expected_masks:
        raise ValueError("unexpected coupling array schema")
    _coupling_headers(dict({key: (value.shape, value.dtype) for key, value in arrays.items()},
                           manifest=((1,), _m4_mountain_lake_coupling_np.dtype("uint8"))))
    runoff = {key[7:]: value for key, value in arrays.items() if key.startswith("runoff_")}
    runoff["metadata"] = meta["runoff_metadata"]
    _m4_mountain_lake_coupling_validate_rainfall_runoff_result(runoff)
    steps, hrus = runoff["local_q_m3_s"].shape
    count = arrays["node_downstream"].size
    _m4_mountain_lake_coupling_preflight(steps, arrays["height_m"].size, hrus, count)
    if source is not None:
        _m4_mountain_lake_coupling_validate_source(source)
        if meta["source_identity"] != source["identity_sha256"] or meta["source_metadata"] != source["metadata"]:
            raise ValueError("external trusted source mismatch")
        if _m4_mountain_lake_coupling_hash(arrays["height_m"]) != _m4_mountain_lake_coupling_hash(source["arrays"]["height_m"]):
            raise ValueError("external source height mismatch")
        if selection is None:
            if meta["selection_identity"] is not None or _m4_mountain_lake_coupling_hash(arrays["hydrology_mask"]) != _m4_mountain_lake_coupling_hash(source["arrays"]["hydrology_mask"]):
                raise ValueError("external source array mismatch")
        else:
            validate_selection(source, topology, selection)
            if (meta["selection_identity"] != selection["identity_sha256"] or
                    meta["selection_metadata"] != selection["metadata"] or
                    _m4_mountain_lake_coupling_hash(arrays["hydrology_mask"]) != _m4_mountain_lake_coupling_hash(selection["arrays"]["mask"])):
                raise ValueError("external selection mismatch")
    if topology is not None:
        if meta["geometry_identity"] != topology["geometry_identity"] or topology["geometry_passed"] is not True:
            raise ValueError("external geometry mismatch")
        for key in ("receiver", "anchor_node", "node_downstream", "tau_s"):
            if _m4_mountain_lake_coupling_hash(arrays[key]) != _m4_mountain_lake_coupling_hash(topology[key]):
                raise ValueError("external topology array mismatch")
        for key in ("node_kind", "node_boundary_type", "boundary_policy"):
            if meta[key] != topology[key]:
                raise ValueError("external topology metadata mismatch")
    if geometry is not None:
        if source is None or topology is None:
            raise ValueError("source/topology required with external geometry")
        geometry_binding(source, topology, geometry, selection)
        for node, kind in enumerate(meta["node_kind"]):
            if kind == "lake":
                if (not _m4_mountain_lake_coupling_np.array_equal(arrays[f"lake_{node}_domain_mask"], source["arrays"]["hydrology_mask"]) or
                        not _m4_mountain_lake_coupling_np.array_equal(arrays[f"lake_{node}_protected_mask"], geometry["arrays"]["protected_mask"])):
                    raise ValueError("saved lake domain/protection differs from external source geometry")
    flat_receiver = arrays["receiver"].ravel()
    _m4_mountain_lake_coupling_order(flat_receiver)
    terminal_ownership(arrays["receiver"], arrays["hydrology_mask"])
    coupling_equal(arrays["node_order"], _m4_mountain_lake_coupling_order(arrays["node_downstream"]), "saved DAG order", atol=0, rtol=0)
    active = arrays["hydrology_mask"].ravel()
    saved_node = arrays["cell_node"].ravel()
    anchor = arrays["anchor_node"].ravel()
    hru = arrays["cell_owner"].ravel()
    if ((saved_node[active] < 0).any() or (saved_node[active] >= count).any() or
            (saved_node[~active] != -1).any() or (anchor[~active] != -1).any() or
            (hru[active] < 0).any() or (hru[active] >= hrus).any() or (hru[~active] != -1).any()):
        raise ValueError("invalid saved unique ownership")
    anchors = active & (anchor >= 0)
    if (anchor[anchors] >= count).any() or (anchor < -1).any():
        raise ValueError("invalid saved anchors")
    coupling_equal(saved_node[anchors], anchor[anchors], "saved anchor ownership", atol=0, rtol=0)
    for current in _m4_mountain_lake_coupling_np.flatnonzero(active):
        target = int(flat_receiver[current])
        if target < 0:
            if anchor[current] < 0 or arrays["node_downstream"][anchor[current]] != -1:
                raise ValueError("unanchored terminal")
        else:
            if not active[target]:
                raise ValueError("saved receiver exits active domain")
            if anchor[current] < 0:
                if saved_node[current] != saved_node[target]:
                    raise ValueError("saved first-node recurrence failed")
            elif saved_node[target] != anchor[current] and arrays["node_downstream"][anchor[current]] != saved_node[target]:
                raise ValueError("saved anchor DAG mismatch")
    counts = _m4_mountain_lake_coupling_np.bincount(saved_node[active] * hrus + hru[active], minlength=count * hrus).reshape(count, hrus)
    area = _m4_mountain_lake_coupling_np.bincount(hru[active], minlength=hrus).astype(_m4_mountain_lake_coupling_np.float64) * meta["source_metadata"]["spacing_m"]**2
    coupling_equal(arrays["allocation_counts"], counts, "saved HRU/node intersection counts", atol=0, rtol=0)
    coupling_equal(arrays["area_m2"], area, "saved HRU area", atol=0, rtol=0)
    land_counts = counts.copy()
    surface_counts = _m4_mountain_lake_coupling_np.zeros_like(counts)
    if meta["rain_support"] == "fixed_lake_footprint_direct_rain":
        for node, kind in enumerate(meta["node_kind"]):
            if kind == "lake":
                labels = arrays["cell_owner"][arrays["anchor_node"] == node]
                surface_counts[node] = _m4_mountain_lake_coupling_np.bincount(labels, minlength=hrus)
        land_counts -= surface_counts
    elif meta["rain_support"] != "fixed_land_conceptual_runoff_all_cells":
        raise ValueError("unknown rainfall support")
    cell_area = meta["source_metadata"]["spacing_m"]**2
    land_area = land_counts.sum(axis=0).astype(_m4_mountain_lake_coupling_np.float64) * cell_area
    coupling_equal(arrays["land_allocation_counts"], land_counts, "unique land rainfall support", atol=0, rtol=0)
    coupling_equal(arrays["surface_allocation_counts"], surface_counts, "unique surface rainfall support", atol=0, rtol=0)
    coupling_equal(runoff["area_m2"], land_area, "runoff land HRU areas", atol=0, rtol=0)
    dt = runoff["metadata"]["dt_s"]
    surface_rain = runoff["rain_mm_h"] @ (surface_counts * cell_area).T / 1000. * dt / 3600.
    surface_evap = _m4_mountain_lake_coupling_np.repeat(surface_counts.sum(axis=1)[None, :] * cell_area / 1000. *
        meta["lake_evaporation_mm_h"] * dt / 3600., steps, axis=0)
    coupling_equal(arrays["surface_rain_volume_m3"], surface_rain, "direct surface rain")
    coupling_equal(arrays["surface_evaporation_volume_m3"], surface_evap, "prescribed surface evaporation")
    lateral = runoff["local_q_m3_s"] @ (land_counts * cell_area / land_area).T * dt + surface_rain
    coupling_equal(arrays["lateral_volume_m3"], lateral, "fresh area allocation")
    incoming = lateral.copy()
    storage = arrays["storage_m3"]
    outflow = arrays["outflow_volume_m3"]
    losses = arrays["lake_loss_volume_m3"]
    if storage.shape != (steps + 1, count) or arrays["lake_stage_m"].shape != storage.shape:
        raise ValueError("invalid state shape")
    for value in (storage, outflow, losses, arrays["incoming_volume_m3"]):
        if value.dtype != _m4_mountain_lake_coupling_np.float64 or not _m4_mountain_lake_coupling_np.isfinite(value).all() or (value < 0).any():
            raise ValueError("invalid nonnegative finite water")
    if outflow.shape != (steps, count) or losses.shape != outflow.shape:
        raise ValueError("invalid flux shape")
    for node, target in enumerate(arrays["node_downstream"]):
        if target >= 0:
            incoming[:, target] += outflow[:, node]
    coupling_equal(arrays["incoming_volume_m3"], incoming, "internal transfer exactly once")
    for node, kind in enumerate(meta["node_kind"]):
        if kind == "lake":
            evidence = meta["lake_evidence"][str(node)]
            recipe = evidence["input"]["recipe"]
            if (evidence["input"]["source_identity"] != meta["source_identity"] or
                    evidence["input"]["spacing_x_m"] != meta["source_metadata"]["spacing_m"] or
                    evidence["input"]["spacing_z_m"] != meta["source_metadata"]["spacing_m"] or
                    evidence["input"]["origin_x_m"] != meta["source_metadata"]["origin_m_xz"][0] or
                    evidence["input"]["origin_z_m"] != meta["source_metadata"]["origin_m_xz"][1] or
                    evidence["input"]["vertical_datum"] != "sea_zero_m" or recipe["dt_s"] != dt):
                raise ValueError("saved lake source/grid/time binding mismatch")
            stage = arrays["lake_stage_m"][:, node]
            basin = arrays["anchor_node"] == node
            proof = single_pool_proof(arrays["height_m"], basin,
                _m4_mountain_lake_coupling_np.array(evidence["pool_geometry"]["legal_spill_grid_zx"], _m4_mountain_lake_coupling_np.int64),
                _m4_mountain_lake_coupling_np.array(evidence["pool_geometry"]["downstream_path_grid_zx"], _m4_mountain_lake_coupling_np.int64),
                arrays[f"lake_{node}_domain_mask"], arrays[f"lake_{node}_protected_mask"],
                arrays[f"lake_{node}_legal_outlet_mask"], max_stage_m=recipe["max_stage_m"])
            if proof != evidence["single_pool_proof"]:
                raise ValueError("saved single-pool proof mismatch")
            sill = evidence["pool_geometry"]["legal_spill_grid_zx"]
            if recipe["rating_stage_m"][0] != arrays["height_m"][tuple(sill)] or recipe["rating_outflow_m3_s"][0] != 0:
                raise ValueError("saved rating must start at measured sill with zero discharge")
            coupling_equal(_m4_mountain_lake_coupling_np.array(recipe["inflow_m3_s"])*dt, incoming[:, node], "saved supplied lake inflow")
            _check_legal_mask(arrays[f"lake_{node}_legal_outlet_mask"],
                _m4_mountain_lake_coupling_np.array(evidence["pool_geometry"]["downstream_path_grid_zx"], _m4_mountain_lake_coupling_np.int64))
            _check_pool_path(arrays["receiver"], _m4_mountain_lake_coupling_np.array(evidence["pool_geometry"]["downstream_path_grid_zx"], _m4_mountain_lake_coupling_np.int64),
                arrays[f"lake_{node}_legal_outlet_mask"], anchor_node=arrays["anchor_node"],
                node_kind=meta["node_kind"], current_node=node, node_downstream=arrays["node_downstream"])
            endpoint = evidence["pool_geometry"]["downstream_path_grid_zx"][-1]
            receiving = int(arrays["anchor_node"][tuple(endpoint)])
            if receiving >= 0 and meta["node_kind"][receiving] == "lake":
                spill = evidence["pool_geometry"]["legal_spill_grid_zx"]
                _free_weir_tailwater(arrays["height_m"][tuple(spill)], arrays["lake_stage_m"][:, receiving])
            if _m4_mountain_lake_coupling_hash(basin) != evidence["basin_sha256"] or not _m4_mountain_lake_coupling_np.isfinite(stage).all():
                raise ValueError("lake basin/stage mismatch")
            floors = arrays["height_m"][basin]
            area = meta["source_metadata"]["spacing_m"]**2
            volume = _m4_mountain_lake_coupling_np.array([_m4_mountain_lake_coupling_np.maximum(level - floors, 0).sum() * area for level in stage])
            tolerance = recipe["volume_abs_tolerance_m3"]
            relative = recipe["volume_rel_tolerance"]
            coupling_equal(storage[:, node], volume, "lake V(h)", atol=tolerance, rtol=relative)
            if (stage > recipe["max_stage_m"]).any() or (stage > recipe["rating_stage_m"][-1]).any():
                raise ValueError("lake rating extrapolation")
            expected_out = _m4_mountain_lake_coupling_np.interp(stage[1:], recipe["rating_stage_m"], recipe["rating_outflow_m3_s"], left=0) * dt
            coupling_equal(outflow[:, node], expected_out, "lake rating", atol=tolerance, rtol=relative)
            coupling_equal(losses[:, node], _m4_mountain_lake_coupling_np.array(recipe["loss_m3_s"]) * dt, "lake supplied loss")
            coupling_equal(storage[0, node], _m4_mountain_lake_coupling_np.maximum(recipe["initial_stage_m"] - floors, 0).sum() * area,
                "lake initial volume", atol=tolerance, rtol=relative)
        else:
            if not _m4_mountain_lake_coupling_np.isnan(arrays["lake_stage_m"][:, node]).all():
                raise ValueError("linear reach must not display fabricated stage")
            coupling_equal(storage[0, node], 0., "zero initial river/terminal storage")
            coupling_equal(losses[:, node], 0., "no implicit river losses")
            if meta["node_boundary_type"][node] == "closed_terminal":
                coupling_equal(outflow[:, node], 0., "closed terminal outflow")
            else:
                coupling_equal(storage[1:, node], (storage[:-1, node] + incoming[:, node]) /
                    (1 + dt / arrays["tau_s"][node]), "river backward Euler")
                coupling_equal(outflow[:, node], storage[1:, node] * dt / arrays["tau_s"][node], "river release")
    residual = incoming - outflow - losses - _m4_mountain_lake_coupling_np.diff(storage, axis=0)
    scale = _m4_mountain_lake_coupling_np.maximum.reduce((incoming, outflow, storage[:-1], storage[1:], _m4_mountain_lake_coupling_np.ones_like(outflow)))
    tolerance = 1e-8 + scale * 2e-10
    if (_m4_mountain_lake_coupling_np.abs(residual) > tolerance).any():
        raise ValueError("individual lake/reach balance failed")
    boundary_nodes = _m4_mountain_lake_coupling_np.flatnonzero((arrays["node_downstream"] < 0) & _m4_mountain_lake_coupling_np.array([
        value == "external_open_boundary" for value in meta["node_boundary_type"]]))
    coupling_equal(arrays["boundary_nodes"], boundary_nodes, "boundary identifiers", atol=0, rtol=0)
    coupling_equal(arrays["boundary_volume_m3"], outflow[:, boundary_nodes], "each outlet contribution")
    boundary = outflow[:, boundary_nodes].sum(axis=1)
    coupling_equal(arrays["total_boundary_volume_m3"], boundary, "total boundary")
    rain = runoff["rain_volume_m3"].sum(axis=1) + surface_rain.sum(axis=1)
    et = runoff["et_volume_m3"].sum(axis=1) + losses.sum(axis=1)
    change = runoff["storage_change_m3"].sum(axis=1) + _m4_mountain_lake_coupling_np.diff(storage, axis=0).sum(axis=1)
    joint = rain - et - boundary - change
    allowed = tolerance.sum(axis=1) + 1e-8
    if (_m4_mountain_lake_coupling_np.abs(joint) > allowed).any() or _m4_mountain_lake_coupling_np.abs(joint).sum() > allowed.sum():
        raise ValueError("joint rain-soil-lake-river-boundary balance failed")
    return {"max_node_residual_m3": float(_m4_mountain_lake_coupling_np.abs(residual).max()),
            "max_joint_interval_residual_m3": float(_m4_mountain_lake_coupling_np.abs(joint).max()),
            "sum_absolute_joint_residual_m3": float(_m4_mountain_lake_coupling_np.abs(joint).sum()),
            "total_boundary_volume_m3": float(boundary.sum()),
            "outlet_volume_m3": {str(int(node)): float(outflow[:, node].sum()) for node in boundary_nodes},
            "boundary_condition_comparison": "separate_boundary_experiment"}

# --- terrain_pipeline/mountain_lake_coupling.py:823 ---
def save_coupling(path, result):
    from terrain_pipeline.common_infra import save_bundle as _m4_mountain_lake_coupling_save_bundle
    _m4_mountain_lake_coupling_save_bundle(path, result, validator=validate_coupling)

# --- terrain_pipeline/mountain_lake_coupling.py:827 ---
def load_coupling(path, *, expected_sha256, source, topology, geometry, selection=None):
    from terrain_pipeline.common_infra import load_bundle as _m4_mountain_lake_coupling_load_bundle
    return _m4_mountain_lake_coupling_load_bundle(path, expected_sha256=expected_sha256, max_bytes=COUPLING_MAX_BYTES,
        header_validator=_coupling_headers,
        validator=lambda result: validate_coupling(result, source=source, topology=topology,
            geometry=geometry, selection=selection))

# --- terrain_pipeline/mountain_lake_coupling.py:834 ---
def _coupling_headers(headers):
    from terrain_pipeline.runoff import RUNOFF_ARRAY_KEYS as _m4_mountain_lake_coupling_RUNOFF_KEYS
    from terrain_pipeline.runoff import preflight as _m4_mountain_lake_coupling_preflight
    shape, dtype = headers.get("height_m", ((), _m4_mountain_lake_coupling_np.dtype("O")))
    rain_shape, rain_dtype = headers.get("runoff_rain_mm_h", ((), _m4_mountain_lake_coupling_np.dtype("O")))
    node_shape, node_dtype = headers.get("node_downstream", ((), _m4_mountain_lake_coupling_np.dtype("O")))
    if (len(shape) != 2 or dtype != _m4_mountain_lake_coupling_np.float64 or len(rain_shape) != 2 or rain_dtype != _m4_mountain_lake_coupling_np.float64 or
            len(node_shape) != 1 or node_dtype != _m4_mountain_lake_coupling_np.int64):
        raise ValueError("invalid typed coupling allocation headers")
    steps, hrus = rain_shape
    nodes = node_shape[0]
    _m4_mountain_lake_coupling_preflight(steps, _m4_mountain_lake_coupling_math.prod(shape), hrus, nodes)
    lake_mask_keys = set(headers) - BASE_KEYS - {"runoff_" + key for key in _m4_mountain_lake_coupling_RUNOFF_KEYS} - {"manifest"}
    lake_nodes = set()
    for key in lake_mask_keys:
        parts = key.split("_", 2)
        if len(parts) != 3 or parts[0] != "lake" or not parts[1].isdigit() or parts[2] not in {
                "domain_mask", "protected_mask", "legal_outlet_mask"}:
            raise ValueError("unknown coupling archive member")
        node = int(parts[1])
        if not 0 <= node < nodes or str(node) != parts[1]:
            raise ValueError("invalid retained lake node")
        lake_nodes.add(node)
    expected_masks = {f"lake_{node}_{key}" for node in lake_nodes
        for key in ("domain_mask", "protected_mask", "legal_outlet_mask")}
    if lake_mask_keys != expected_masks or len(lake_nodes) * _m4_mountain_lake_coupling_math.prod(shape) > 2_000_000:
        raise ValueError("retained lake mask count budget/schema mismatch")
    if set(headers) != BASE_KEYS | {"runoff_" + key for key in _m4_mountain_lake_coupling_RUNOFF_KEYS} | expected_masks | {"manifest"}:
        raise ValueError("missing coupling archive members")
    manifest_shape, manifest_dtype = headers["manifest"]
    if manifest_dtype != _m4_mountain_lake_coupling_np.uint8 or len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= 1_048_576:
        raise ValueError("manifest allocation budget")
    grid_types = {"height_m": "float64", "hydrology_mask": "bool", "cell_owner": "int64",
        "receiver": "int64", "anchor_node": "int64", "cell_node": "int64"}
    for key, expected in grid_types.items():
        if headers.get(key) != (shape, _m4_mountain_lake_coupling_np.dtype(expected)):
            raise ValueError("coupling grid header mismatch")
    for key in ("lateral_volume_m3", "incoming_volume_m3", "outflow_volume_m3", "lake_loss_volume_m3",
                "surface_rain_volume_m3", "surface_evaporation_volume_m3"):
        if headers.get(key) != ((steps, nodes), _m4_mountain_lake_coupling_np.dtype("float64")):
            raise ValueError("coupling flux header mismatch")
    for key in ("storage_m3", "lake_stage_m"):
        if headers.get(key) != ((steps + 1, nodes), _m4_mountain_lake_coupling_np.dtype("float64")):
            raise ValueError("coupling state header mismatch")
    for key in ("allocation_counts", "land_allocation_counts", "surface_allocation_counts"):
        if headers[key] != ((nodes, hrus), _m4_mountain_lake_coupling_np.dtype("int64")):
            raise ValueError("allocation header mismatch")
    for key in ("tau_s", "node_order", "area_m2", "total_boundary_volume_m3"):
        expected_shape = (hrus,) if key == "area_m2" else (steps,) if key == "total_boundary_volume_m3" else (nodes,)
        expected_dtype = _m4_mountain_lake_coupling_np.dtype("int64" if key == "node_order" else "float64")
        if headers[key] != (expected_shape, expected_dtype):
            raise ValueError("coupling vector header mismatch")
    boundary_shape, boundary_dtype = headers["boundary_nodes"]
    if len(boundary_shape) != 1 or not 0 <= boundary_shape[0] <= nodes or boundary_dtype != _m4_mountain_lake_coupling_np.int64:
        raise ValueError("boundary node header mismatch")
    if headers["boundary_volume_m3"] != ((steps, boundary_shape[0]), _m4_mountain_lake_coupling_np.dtype("float64")):
        raise ValueError("boundary flux header mismatch")
    for key, (entry_shape, entry_dtype) in headers.items():
        if key.startswith("lake_") and key.endswith("_mask"):
            if entry_shape != shape or entry_dtype != bool:
                raise ValueError("lake retained mask header mismatch")
        if key.startswith("runoff_"):
            name = key[7:]
            expected = (hrus,) if name == "area_m2" else (steps + 1, hrus) if name in {
                "soil_mm", "fast_mm", "slow_mm"} else (steps, hrus)
            if entry_shape != expected or entry_dtype != _m4_mountain_lake_coupling_np.float64:
                raise ValueError("runoff retained header mismatch")

# --- terrain_pipeline/mountain_depression_geometry.py:18 ---
DEPRESSION_ALGORITHM = "mountain-depression-geometry-v1"

# --- terrain_pipeline/mountain_depression_geometry.py:19 ---
DEPRESSION_SCHEMA = "mountain-depression-geometry-npz-v1"

# --- terrain_pipeline/mountain_depression_geometry.py:20 ---
DEPRESSION_NEIGHBORS = ((-1, 0), (0, -1), (0, 1), (1, 0))

# --- terrain_pipeline/mountain_depression_geometry.py:21 ---
DEPRESSION_MAX_CELLS = 250000

# --- terrain_pipeline/mountain_depression_geometry.py:22 ---
DEPRESSION_MAX_BYTES = 512 * 1024 * 1024

# --- terrain_pipeline/mountain_depression_geometry.py:23 ---
MAX_METADATA = 1024 * 1024

# --- terrain_pipeline/mountain_depression_geometry.py:24 ---
DEPRESSION_TOL = 1e-9

# --- terrain_pipeline/mountain_depression_geometry.py:25 ---
ARRAY_KEYS = frozenset((
    "H0_m", "H1_m", "H2_m", "boundary_mask", "protected_mask", "escape_level_m",
    "flood_parent", "flood_order", "lake_id", "lake_mask", "lake_stage_m", "lake_area_m2",
    "lake_capacity_m3", "lake_downstream_id", "spill_lake_id", "spill_inside", "spill_outside",
    "spill_stage_m", "spill_width_m", "receiver", "order", "outlet_cells", "outlet_owner",
    "outlet_area_m2", "outlet_type", "contributing_area_m2", "flowline_mask", "dry_channel_mask",
    "accepted_mask", "accepted_outlets", "rejection_code", "candidate_H2_m", "cut_depth_m",
    "cell_cut_volume_m3", "section_cells", "section_offset_m", "section_H0_m", "section_H1_m", "section_H2_m",
))

# --- terrain_pipeline/mountain_depression_geometry.py:34 ---
BOOL_KEYS = frozenset(("boundary_mask", "protected_mask", "lake_mask", "flowline_mask",
                       "dry_channel_mask", "accepted_mask", "accepted_outlets"))

# --- terrain_pipeline/mountain_depression_geometry.py:36 ---
INT_KEYS = frozenset(("flood_parent", "flood_order", "lake_id", "lake_downstream_id", "spill_lake_id",
                      "spill_inside", "spill_outside", "receiver", "order", "outlet_cells", "outlet_owner",
                      "outlet_type", "rejection_code", "section_cells"))

# --- terrain_pipeline/mountain_depression_geometry.py:39 ---
GRID_KEYS = frozenset(("H0_m", "H1_m", "H2_m", "boundary_mask", "protected_mask", "escape_level_m",
                       "lake_id", "lake_mask", "outlet_owner", "contributing_area_m2", "flowline_mask",
                       "dry_channel_mask", "accepted_mask", "rejection_code", "candidate_H2_m",
                       "cut_depth_m", "cell_cut_volume_m3"))

# --- terrain_pipeline/mountain_depression_geometry.py:46 ---
@_m4_mountain_depression_geometry_dataclass(frozen=True)
class GeometryBudget:
    max_cells: int = 250000
    max_bytes: int = 536870912
    max_neighbor_visits: int = 4000000
    max_valley_cut_m: float = 1.0
    max_total_cut_m: float = 2.0
    max_cut_volume_m3: float = 200000.0
    shallow_cut_m: float = 0.25
    channel_area_m2: float = 1000000.0
    min_dry_slope: float = 0.0001

    def __post_init__(self):
        for name, ceiling in (("max_cells", DEPRESSION_MAX_CELLS), ("max_bytes", DEPRESSION_MAX_BYTES),
                              ("max_neighbor_visits", 4000000)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("invalid resource budget: " + name)
        for name in ("max_valley_cut_m", "max_total_cut_m", "max_cut_volume_m3",
                     "shallow_cut_m", "channel_area_m2", "min_dry_slope"):
            value = getattr(self, name)
            if isinstance(value, (bool, _m4_mountain_depression_geometry_np.bool_)) or not isinstance(value, (int, float)) or not _m4_mountain_depression_geometry_math.isfinite(value) or value <= 0:
                raise ValueError("invalid finite positive budget: " + name)
        if (self.max_valley_cut_m > 1 or self.max_total_cut_m > 2 or
                self.max_cut_volume_m3 > 200000 or self.shallow_cut_m > self.max_total_cut_m):
            raise ValueError("construction exceeds fixed ceiling")

# --- terrain_pipeline/mountain_depression_geometry.py:73 ---
def preflight(shape, budget):
    if not isinstance(budget, GeometryBudget) or len(shape) != 2 or any(type(value) is not int or value < 3 for value in shape):
        raise ValueError("bounded two-dimensional grid required")
    cells = _m4_mountain_depression_geometry_math.prod(shape)
    estimate = cells * 768 + MAX_METADATA
    if cells > budget.max_cells or estimate > budget.max_bytes or cells * 12 > budget.max_neighbor_visits:
        raise ValueError("geometry resource budget exceeded before allocation")
    return {"cells": cells, "estimated_peak_bytes": estimate, "neighbor_visit_bound": cells * 12}

# --- terrain_pipeline/mountain_depression_geometry.py:83 ---
def depression_json(value):
    return _m4_mountain_depression_geometry_json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

# --- terrain_pipeline/mountain_depression_geometry.py:87 ---
def _hash(array):
    digest = _m4_mountain_depression_geometry_hashlib.sha256(array.dtype.str.encode("ascii"))
    digest.update(depression_json(list(array.shape)).encode("ascii"))
    digest.update(_m4_mountain_depression_geometry_np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()

# --- terrain_pipeline/mountain_depression_geometry.py:94 ---
def window_boundary(shape):
    boundary = _m4_mountain_depression_geometry_np.zeros(shape, dtype=bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    return boundary

# --- terrain_pipeline/mountain_depression_geometry.py:101 ---
def depression_neighbors(cell, shape):
    row, column = divmod(int(cell), shape[1])
    for delta_row, delta_column in DEPRESSION_NEIGHBORS:
        next_row, next_column = row + delta_row, column + delta_column
        if 0 <= next_row < shape[0] and 0 <= next_column < shape[1]:
            yield next_row * shape[1] + next_column

# --- terrain_pipeline/mountain_depression_geometry.py:109 ---
def _flood(height, boundary):
    """Four-neighbor minimax escape certificate with an acyclic parent witness."""
    escape = height.ravel().copy()
    discovered = boundary.ravel().copy()
    parent = _m4_mountain_depression_geometry_np.full(height.size, -1, dtype=_m4_mountain_depression_geometry_np.int64)
    order = _m4_mountain_depression_geometry_np.empty(height.size, dtype=_m4_mountain_depression_geometry_np.int64)
    heap = [(float(escape[cell]), int(cell)) for cell in _m4_mountain_depression_geometry_np.flatnonzero(discovered)]
    _m4_mountain_depression_geometry_heapq.heapify(heap)
    position = 0
    while heap:
        stage, cell = _m4_mountain_depression_geometry_heapq.heappop(heap)
        order[position] = cell
        position += 1
        for neighbor in depression_neighbors(cell, height.shape):
            if not discovered[neighbor]:
                discovered[neighbor] = True
                escape[neighbor] = max(escape[neighbor], stage)
                parent[neighbor] = cell
                _m4_mountain_depression_geometry_heapq.heappush(heap, (float(escape[neighbor]), neighbor))
    return escape.reshape(height.shape), parent, order

# --- terrain_pipeline/mountain_depression_geometry.py:131 ---
def _topological(receiver):
    donors = _m4_mountain_depression_geometry_np.bincount(receiver[receiver >= 0], minlength=receiver.size)
    pending = _m4_mountain_depression_geometry_deque(_m4_mountain_depression_geometry_np.flatnonzero(donors == 0).tolist())
    order = []
    while pending:
        cell = pending.popleft()
        order.append(cell)
        target = int(receiver[cell])
        if target >= 0:
            donors[target] -= 1
            if donors[target] == 0:
                pending.append(target)
    if len(order) != receiver.size:
        raise ValueError("receiver cycle")
    return _m4_mountain_depression_geometry_np.asarray(order[::-1], dtype=_m4_mountain_depression_geometry_np.int64)

# --- terrain_pipeline/mountain_depression_geometry.py:148 ---
def _lake_geometry(height, escape, parent, flood_order):
    positive = escape > height + DEPRESSION_TOL
    labels, count = _m4_mountain_depression_geometry_ndimage.label(positive, _m4_mountain_depression_geometry_ndimage.generate_binary_structure(2, 1))
    labels = labels.astype(_m4_mountain_depression_geometry_np.int64)
    rank = _m4_mountain_depression_geometry_np.empty(height.size, dtype=_m4_mountain_depression_geometry_np.int64)
    rank[flood_order] = _m4_mountain_depression_geometry_np.arange(height.size)
    stages = _m4_mountain_depression_geometry_np.zeros(count, dtype=_m4_mountain_depression_geometry_np.float64)
    inside = _m4_mountain_depression_geometry_np.zeros(count, dtype=_m4_mountain_depression_geometry_np.int64)
    outside = _m4_mountain_depression_geometry_np.zeros(count, dtype=_m4_mountain_depression_geometry_np.int64)
    levels = escape.ravel()
    flat_labels = labels.ravel()
    grouped = _m4_mountain_depression_geometry_np.argsort(flat_labels, kind="stable")
    offsets = _m4_mountain_depression_geometry_np.r_[0, _m4_mountain_depression_geometry_np.cumsum(_m4_mountain_depression_geometry_np.bincount(flat_labels, minlength=count + 1))]
    for lake in range(1, count + 1):
        cells = grouped[offsets[lake]:offsets[lake + 1]]
        if _m4_mountain_depression_geometry_np.ptp(levels[cells]) > DEPRESSION_TOL:
            raise ValueError("positive component spans multiple escape levels")
        stages[lake - 1] = levels[cells[0]]
        exits = cells[flat_labels[parent[cells]] != lake]
        source = int(exits[_m4_mountain_depression_geometry_np.argmin(rank[exits])])
        inside[lake - 1], outside[lake - 1] = source, parent[source]
    return labels, stages, inside, outside

# --- terrain_pipeline/mountain_depression_geometry.py:172 ---
def _route_lakes(height, escape, labels, stages, inside, outside, parent, flood_order):
    receiver = parent.copy()
    rank = _m4_mountain_depression_geometry_np.empty(height.size, dtype=_m4_mountain_depression_geometry_np.int64)
    rank[flood_order] = _m4_mountain_depression_geometry_np.arange(height.size)
    raw = height.ravel()
    flat_labels = labels.ravel()
    for cell in flood_order:
        if parent[cell] < 0 or flat_labels[cell]:
            continue
        candidates = [neighbor for neighbor in depression_neighbors(cell, height.shape)
                      if rank[neighbor] < rank[cell] and escape.flat[neighbor] <= escape.flat[cell] + DEPRESSION_TOL]
        receiver[cell] = min(candidates, key=lambda neighbor: (raw[neighbor], rank[neighbor], neighbor))
    seen = _m4_mountain_depression_geometry_np.zeros(height.size, dtype=bool)
    for lake, source in enumerate(inside, 1):
        receiver[source] = outside[lake - 1]
        seen[source] = True
        pending = _m4_mountain_depression_geometry_deque([int(source)])
        while pending:
            cell = pending.popleft()
            for neighbor in depression_neighbors(cell, height.shape):
                if flat_labels[neighbor] == lake and not seen[neighbor]:
                    seen[neighbor] = True
                    receiver[neighbor] = cell
                    pending.append(neighbor)
    return receiver, _topological(receiver)

# --- terrain_pipeline/mountain_depression_geometry.py:199 ---
def _ownership(receiver, order, boundary, area):
    outlets = _m4_mountain_depression_geometry_np.flatnonzero(boundary.ravel()).astype(_m4_mountain_depression_geometry_np.int64)
    owner = _m4_mountain_depression_geometry_np.full(receiver.size, -1, dtype=_m4_mountain_depression_geometry_np.int64)
    owner[outlets] = _m4_mountain_depression_geometry_np.arange(outlets.size)
    accumulation = _m4_mountain_depression_geometry_np.ones(receiver.size, dtype=_m4_mountain_depression_geometry_np.float64) * area
    for cell in order:
        if receiver[cell] >= 0:
            owner[cell] = owner[receiver[cell]]
    for cell in order[::-1]:
        if receiver[cell] >= 0:
            accumulation[receiver[cell]] += accumulation[cell]
    return outlets, owner, _m4_mountain_depression_geometry_np.bincount(owner, minlength=outlets.size).astype(_m4_mountain_depression_geometry_np.float64) * area, accumulation

# --- terrain_pipeline/mountain_depression_geometry.py:213 ---
def _bed_candidates(height, lake_id, stages, receiver, order, flowline, locked, spacing, budget):
    candidate = height.ravel().copy()
    reasons = _m4_mountain_depression_geometry_np.zeros(height.size, dtype=_m4_mountain_depression_geometry_np.int64)
    dry = flowline & (lake_id.ravel() == 0)
    for cell in order:
        if not dry[cell] or locked.flat[cell]:
            continue
        target = int(receiver[cell])
        proposed = height.flat[cell] - budget.shallow_cut_m
        if target >= 0:
            lake = lake_id.flat[target]
            lower = stages[lake - 1] if lake else candidate[target] + spacing * budget.min_dry_slope
            proposed = max(proposed, lower)
        if proposed > height.flat[cell] + DEPRESSION_TOL:
            reasons[cell] = 1
        else:
            candidate[cell] = min(height.flat[cell], proposed)
    return candidate, reasons

# --- terrain_pipeline/mountain_depression_geometry.py:233 ---
def prepare_mountain_geometry(height_m, *, spacing_m, origin_m_xz, source_binding,
                              boundary_mask, protected_mask, budget=GeometryBudget()):
    """Prepare once; all areas include complete internal upstream contributions."""
    if not isinstance(height_m, _m4_mountain_depression_geometry_np.ndarray):
        raise ValueError("height must be a resource-checkable numpy array")
    resources = preflight(tuple(height_m.shape), budget)
    if (height_m.dtype != _m4_mountain_depression_geometry_np.dtype("float64") or not _m4_mountain_depression_geometry_np.isfinite(height_m).all() or
            isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float)) or
            not _m4_mountain_depression_geometry_math.isfinite(spacing_m) or not 0 < spacing_m <= 100000 or
            len(origin_m_xz) != 2 or not _m4_mountain_depression_geometry_np.isfinite(origin_m_xz).all() or
            not isinstance(source_binding, dict) or not source_binding):
        raise ValueError("invalid metre source geometry/binding")
    depression_json(source_binding)
    for mask in (boundary_mask, protected_mask):
        if not isinstance(mask, _m4_mountain_depression_geometry_np.ndarray) or mask.dtype != bool or mask.shape != height_m.shape:
            raise ValueError("explicit boolean masks required")
    if not _m4_mountain_depression_geometry_np.array_equal(boundary_mask, window_boundary(height_m.shape)):
        raise ValueError("v1 requires every window edge explicitly open")
    height = height_m.copy()
    escape, parent, flood_order = _flood(height, boundary_mask)
    labels, stages, inside, outside = _lake_geometry(height, escape, parent, flood_order)
    receiver, order = _route_lakes(height, escape, labels, stages, inside, outside, parent, flood_order)
    outlets, owner, outlet_area, accumulation = _ownership(receiver, order, boundary_mask, spacing_m ** 2)
    flowline = accumulation >= budget.channel_area_m2
    lake_mask = labels > 0
    shore = _m4_mountain_depression_geometry_ndimage.binary_dilation(lake_mask, structure=_m4_mountain_depression_geometry_ndimage.generate_binary_structure(2, 1)) & ~lake_mask
    locked = lake_mask | shore | boundary_mask | protected_mask
    candidate, reasons = _bed_candidates(height, labels, stages, receiver, order, flowline, locked, spacing_m, budget)
    proposed_volume = (height.ravel() - candidate) * spacing_m ** 2
    group_volume = _m4_mountain_depression_geometry_np.bincount(owner, weights=proposed_volume, minlength=outlets.size)
    failed_groups = _m4_mountain_depression_geometry_np.bincount(owner, weights=(reasons > 0).astype(float), minlength=outlets.size) > 0
    lake_groups = _m4_mountain_depression_geometry_np.bincount(owner, weights=lake_mask.ravel().astype(float), minlength=outlets.size) > 0
    selected = _m4_mountain_depression_geometry_np.zeros(outlets.size, dtype=bool)
    spent = 0.0
    for group in _m4_mountain_depression_geometry_np.argsort(-outlet_area, kind="stable"):
        if not lake_groups[group] or failed_groups[group] or group_volume[group] <= 0:
            continue
        if spent + group_volume[group] <= budget.max_cut_volume_m3 + DEPRESSION_TOL:
            selected[group] = True
            spent += float(group_volume[group])
    accepted = selected[owner]
    reasons[~accepted & (reasons == 0)] = 2
    bed = height.ravel().copy()
    bed[accepted] = candidate[accepted]
    count = stages.size
    lake_area = _m4_mountain_depression_geometry_np.bincount(labels.ravel(), minlength=count + 1)[1:].astype(float) * spacing_m ** 2
    lake_capacity = _m4_mountain_depression_geometry_np.bincount(labels.ravel(), weights=(escape - height).ravel(), minlength=count + 1)[1:] * spacing_m ** 2
    next_lake = _m4_mountain_depression_geometry_np.full(height.size, -1, dtype=_m4_mountain_depression_geometry_np.int64)
    for cell in order:
        target = receiver[cell]
        if target >= 0:
            next_lake[cell] = labels.flat[target] if labels.flat[target] else next_lake[target]
    downstream_lake = next_lake[outside]
    downstream_lake[labels.ravel()[outside] > 0] = labels.ravel()[outside][labels.ravel()[outside] > 0]
    cut = (height.ravel() - bed).reshape(height.shape)
    section_cells = _m4_mountain_depression_geometry_np.flatnonzero(accepted & flowline & ~lake_mask.ravel()).astype(_m4_mountain_depression_geometry_np.int64)
    arrays = {
        "H0_m": height, "H1_m": height.copy(), "H2_m": bed.reshape(height.shape),
        "boundary_mask": boundary_mask.copy(), "protected_mask": protected_mask.copy(),
        "escape_level_m": escape, "flood_parent": parent, "flood_order": flood_order,
        "lake_id": labels, "lake_mask": lake_mask, "lake_stage_m": stages,
        "lake_area_m2": lake_area, "lake_capacity_m3": lake_capacity,
        "lake_downstream_id": downstream_lake, "spill_lake_id": _m4_mountain_depression_geometry_np.arange(1, count + 1, dtype=_m4_mountain_depression_geometry_np.int64),
        "spill_inside": inside, "spill_outside": outside, "spill_stage_m": stages.copy(),
        "spill_width_m": _m4_mountain_depression_geometry_np.full(count, float(spacing_m)), "receiver": receiver, "order": order,
        "outlet_cells": outlets, "outlet_owner": owner.reshape(height.shape),
        "outlet_area_m2": outlet_area, "outlet_type": _m4_mountain_depression_geometry_np.ones(outlets.size, dtype=_m4_mountain_depression_geometry_np.int64),
        "contributing_area_m2": accumulation.reshape(height.shape),
        "flowline_mask": flowline.reshape(height.shape),
        "dry_channel_mask": (flowline & ~lake_mask.ravel()).reshape(height.shape),
        "accepted_mask": accepted.reshape(height.shape), "accepted_outlets": selected,
        "rejection_code": reasons.reshape(height.shape),
        "candidate_H2_m": candidate.reshape(height.shape), "cut_depth_m": cut,
        "cell_cut_volume_m3": cut * spacing_m ** 2, "section_cells": section_cells,
        "section_offset_m": _m4_mountain_depression_geometry_np.array([-spacing_m / 2, 0., spacing_m / 2]),
        "section_H0_m": _m4_mountain_depression_geometry_np.repeat(height.ravel()[section_cells, None], 3, axis=1),
        "section_H1_m": _m4_mountain_depression_geometry_np.repeat(height.ravel()[section_cells, None], 3, axis=1),
        "section_H2_m": _m4_mountain_depression_geometry_np.repeat(bed[section_cells, None], 3, axis=1),
    }
    metadata = {"algorithm": DEPRESSION_ALGORITHM, "schema": DEPRESSION_SCHEMA, "spacing_m": float(spacing_m),
                "origin_m_xz": list(map(float, origin_m_xz)), "source_binding": source_binding,
                "H0_sha256": _hash(height), "budget": _m4_mountain_depression_geometry_asdict(budget), "resources": resources,
                "boundary_types": {"1": "external_open_boundary"},
                "scope": "finite_window_truncated_boundary_experiment",
                "lake_semantics": "aggregate_full_spill_equilibrium_capacity_not_initial_connected_water",
                "section_semantics": "piecewise_constant_full_cell_finite_volume_not_subcell_channel",
                "rejection_codes": {"0": "accepted", "1": "dry_slope_requires_fill", "2": "unaccepted_complete_contribution_group"}}
    result = {"arrays": arrays, "metadata": metadata}
    validate_mountain_geometry(result, trusted_height=height_m, source_binding=source_binding)
    return result

# --- terrain_pipeline/mountain_depression_geometry.py:325 ---
def depression_lake_volume_at_stage(result, lake_id, stage_m):
    """Equilibrium capacity V(h), not a claim of initial pool connectivity."""
    arrays = result["arrays"]
    if type(lake_id) is not int or not 1 <= lake_id <= arrays["lake_stage_m"].size or not _m4_mountain_depression_geometry_math.isfinite(stage_m):
        raise ValueError("invalid lake stage query")
    if stage_m > arrays["lake_stage_m"][lake_id - 1] + DEPRESSION_TOL:
        raise ValueError("query exceeds represented spill level")
    return float(_m4_mountain_depression_geometry_np.maximum(stage_m - arrays["H0_m"][arrays["lake_id"] == lake_id], 0).sum() * result["metadata"]["spacing_m"] ** 2)

# --- terrain_pipeline/mountain_depression_geometry.py:335 ---
def certify_no_cut_groups(result):
    """Independent original-bed static certificate; construction selection is separate."""
    arrays, metadata = result["arrays"], result["metadata"]
    receiver = arrays["receiver"]
    height = arrays["H0_m"].ravel()
    labels = arrays["lake_id"].ravel()
    owner = arrays["outlet_owner"].ravel()
    donors = _m4_mountain_depression_geometry_np.flatnonzero((receiver >= 0) & (labels == 0))
    targets = receiver[donors]
    downstream = height[targets].copy()
    submerged = labels[targets] > 0
    downstream[submerged] = arrays["lake_stage_m"][labels[targets[submerged]] - 1]
    bad = donors[height[donors] < downstream - DEPRESSION_TOL]
    counts = _m4_mountain_depression_geometry_np.bincount(owner[bad], minlength=arrays["outlet_cells"].size)
    valid = counts == 0
    return {"scope": "original_bed_static_finite_window_no_cut_not_dynamic_single_pool",
            "outlet_valid_mask": valid, "cell_valid_mask": valid[owner].reshape(arrays["H0_m"].shape),
            "dry_uphill_count_by_outlet": counts, "failed_dry_donors": bad,
            "valid_area_m2": float(arrays["outlet_area_m2"][valid].sum()),
            "original_dry_uphill_edges": int(bad.size), "cut_volume_m3": 0.,
            "lake_spill_contract": "uncut_full_D4_cell_edge_at_equilibrium_stage_no_initial_connectivity_claim",
            "source_H0_sha256": metadata["H0_sha256"]}

# --- terrain_pipeline/mountain_depression_geometry.py:359 ---
def depression_equal(actual, expected, name):
    if actual.shape != _m4_mountain_depression_geometry_np.shape(expected) or not _m4_mountain_depression_geometry_np.array_equal(actual, expected):
        raise ValueError("static geometry mismatch: " + name)

# --- terrain_pipeline/mountain_depression_geometry.py:364 ---
def validate_mountain_geometry(result, *, trusted_height, source_binding):
    """Check static equations/certificates only: no flood, prepare or evolution."""
    arrays, meta = result["arrays"], result["metadata"]
    if set(arrays) != ARRAY_KEYS:
        raise ValueError("fixed geometry schema required")
    if meta["algorithm"] != DEPRESSION_ALGORITHM or meta["schema"] != DEPRESSION_SCHEMA or meta["source_binding"] != source_binding:
        raise ValueError("source/algorithm binding mismatch")
    budget = GeometryBudget(**meta["budget"])
    height = arrays["H0_m"]
    resources = preflight(tuple(height.shape), budget)
    if meta["resources"] != resources or len(meta["origin_m_xz"]) != 2 or not _m4_mountain_depression_geometry_np.isfinite(meta["origin_m_xz"]).all():
        raise ValueError("resource or coordinate identity")
    if (meta["lake_semantics"] != "aggregate_full_spill_equilibrium_capacity_not_initial_connected_water"
            or meta["section_semantics"] != "piecewise_constant_full_cell_finite_volume_not_subcell_channel"
            or meta["rejection_codes"] != {"0": "accepted", "1": "dry_slope_requires_fill", "2": "unaccepted_complete_contribution_group"}):
        raise ValueError("geometry semantic label forgery")
    if not _m4_mountain_depression_geometry_np.array_equal(height, trusted_height) or _hash(height) != meta["H0_sha256"]:
        raise ValueError("trusted original H0 mismatch")
    for key, values in arrays.items():
        expected_dtype = _m4_mountain_depression_geometry_np.dtype("bool" if key in BOOL_KEYS else "int64" if key in INT_KEYS else "float64")
        if not isinstance(values, _m4_mountain_depression_geometry_np.ndarray) or values.dtype != expected_dtype or not _m4_mountain_depression_geometry_np.isfinite(values).all():
            raise ValueError("invalid array: " + key)
        if key in GRID_KEYS and values.shape != height.shape:
            raise ValueError("grid shape mismatch: " + key)
    spacing = meta["spacing_m"]
    if not isinstance(spacing, (int, float)) or isinstance(spacing, bool) or not _m4_mountain_depression_geometry_math.isfinite(spacing) or not 0 < spacing <= 100000:
        raise ValueError("invalid spacing")
    if (meta["boundary_types"] != {"1": "external_open_boundary"} or
            meta["scope"] != "finite_window_truncated_boundary_experiment"):
        raise ValueError("boundary semantic forgery")
    boundary = arrays["boundary_mask"]
    depression_equal(boundary, window_boundary(height.shape), "all explicit boundary")
    for key in ("receiver", "flood_parent", "order", "flood_order", "outlet_owner", "lake_id"):
        if arrays[key].dtype != _m4_mountain_depression_geometry_np.dtype("int64"):
            raise ValueError("integer topology required")
    rank = _m4_mountain_depression_geometry_np.empty(height.size, dtype=_m4_mountain_depression_geometry_np.int64)
    for receiver_key, order_key in (("receiver", "order"), ("flood_parent", "flood_order")):
        receiver, order = arrays[receiver_key], arrays[order_key]
        depression_equal(_m4_mountain_depression_geometry_np.sort(order), _m4_mountain_depression_geometry_np.arange(height.size), "order permutation")
        if receiver.shape != (height.size,) or (receiver < -1).any() or (receiver >= height.size).any():
            raise ValueError("receiver indices")
        depression_equal((receiver == -1).reshape(height.shape), boundary, "external terminals")
        rank[order] = _m4_mountain_depression_geometry_np.arange(height.size)
        donors = _m4_mountain_depression_geometry_np.flatnonzero(receiver >= 0)
        targets = receiver[donors]
        if (rank[targets] >= rank[donors]).any() or (_m4_mountain_depression_geometry_np.abs(donors // height.shape[1] - targets // height.shape[1]) + _m4_mountain_depression_geometry_np.abs(donors % height.shape[1] - targets % height.shape[1]) != 1).any():
            raise ValueError("cycle or non-width four-neighbor connection")
    escape = arrays["escape_level_m"]
    if escape.shape != height.shape or (escape < height - DEPRESSION_TOL).any():
        raise ValueError("invalid escape levels")
    depression_equal(escape[boundary], height[boundary], "boundary unmodified escape")
    minimum_neighbor = _m4_mountain_depression_geometry_np.full(height.shape, _m4_mountain_depression_geometry_np.inf)
    minimum_neighbor[1:, :] = _m4_mountain_depression_geometry_np.minimum(minimum_neighbor[1:, :], escape[:-1, :])
    minimum_neighbor[:-1, :] = _m4_mountain_depression_geometry_np.minimum(minimum_neighbor[:-1, :], escape[1:, :])
    minimum_neighbor[:, 1:] = _m4_mountain_depression_geometry_np.minimum(minimum_neighbor[:, 1:], escape[:, :-1])
    minimum_neighbor[:, :-1] = _m4_mountain_depression_geometry_np.minimum(minimum_neighbor[:, :-1], escape[:, 1:])
    depression_equal(escape[~boundary], _m4_mountain_depression_geometry_np.maximum(height, minimum_neighbor)[~boundary], "minimax Bellman equation")
    parent = arrays["flood_parent"]
    donors = _m4_mountain_depression_geometry_np.flatnonzero(parent >= 0)
    depression_equal(escape.ravel()[donors], _m4_mountain_depression_geometry_np.maximum(height.ravel()[donors], escape.ravel()[parent[donors]]), "escape-to-boundary witness")
    labels, count = _m4_mountain_depression_geometry_ndimage.label(escape > height + DEPRESSION_TOL, _m4_mountain_depression_geometry_ndimage.generate_binary_structure(2, 1))
    depression_equal(arrays["lake_id"], labels.astype(_m4_mountain_depression_geometry_np.int64), "four-connected lake labels")
    depression_equal(arrays["lake_mask"], labels > 0, "lake mask")
    stages = arrays["lake_stage_m"]
    if stages.shape != (count,):
        raise ValueError("lake dimensions")
    flat_labels = labels.ravel()
    wet = flat_labels > 0
    depression_equal(escape.ravel()[wet], stages[flat_labels[wet] - 1], "lake equilibrium stages")
    depression_equal(arrays["lake_area_m2"], _m4_mountain_depression_geometry_np.bincount(flat_labels, minlength=count + 1)[1:] * spacing ** 2, "lake area")
    depression_equal(arrays["lake_capacity_m3"], _m4_mountain_depression_geometry_np.bincount(flat_labels, weights=(escape - height).ravel(), minlength=count + 1)[1:] * spacing ** 2, "capacity not actual storage")
    receiver, order = arrays["receiver"], arrays["order"]
    inside, outside = arrays["spill_inside"], arrays["spill_outside"]
    if inside.shape != (count,) or outside.shape != (count,) or (inside < 0).any() or (outside < 0).any() or (inside >= height.size).any() or (outside >= height.size).any():
        raise ValueError("invalid spill indices")
    depression_equal(flat_labels[inside], _m4_mountain_depression_geometry_np.arange(1, count + 1), "spill basin")
    depression_equal(flat_labels[outside], _m4_mountain_depression_geometry_np.zeros(count, dtype=_m4_mountain_depression_geometry_np.int64), "spill outside lake")
    depression_equal(height.ravel()[outside], stages, "original uncut saddle")
    depression_equal(receiver[inside], outside, "spill edge")
    depression_equal(arrays["spill_lake_id"], _m4_mountain_depression_geometry_np.arange(1, count + 1), "spill lake identity")
    depression_equal(arrays["spill_stage_m"], stages, "spill elevation")
    depression_equal(arrays["spill_width_m"], _m4_mountain_depression_geometry_np.full(count, spacing), "full-edge spill width")
    lake_donors = _m4_mountain_depression_geometry_np.flatnonzero(wet)
    exits = lake_donors[flat_labels[receiver[lake_donors]] != flat_labels[lake_donors]]
    depression_equal(_m4_mountain_depression_geometry_np.sort(exits), _m4_mountain_depression_geometry_np.sort(inside), "one canonical spill per equilibrium lake")
    rank[arrays["flood_order"]] = _m4_mountain_depression_geometry_np.arange(height.size)
    grouped = _m4_mountain_depression_geometry_np.argsort(flat_labels, kind="stable")
    offsets = _m4_mountain_depression_geometry_np.r_[0, _m4_mountain_depression_geometry_np.cumsum(_m4_mountain_depression_geometry_np.bincount(flat_labels, minlength=count + 1))]
    for lake in range(1, count + 1):
        cells = grouped[offsets[lake]:offsets[lake + 1]]
        witnesses = cells[flat_labels[parent[cells]] != lake]
        source = int(witnesses[_m4_mountain_depression_geometry_np.argmin(rank[witnesses])])
        if inside[lake - 1] != source or outside[lake - 1] != parent[source]:
            raise ValueError("canonical original saddle witness mismatch")
    next_lake = _m4_mountain_depression_geometry_np.full(height.size, -1, dtype=_m4_mountain_depression_geometry_np.int64)
    for cell in order:
        target = receiver[cell]
        if target >= 0:
            next_lake[cell] = flat_labels[target] if flat_labels[target] else next_lake[target]
    downstream_lake = next_lake[outside]
    downstream_lake[flat_labels[outside] > 0] = flat_labels[outside][flat_labels[outside] > 0]
    depression_equal(arrays["lake_downstream_id"], downstream_lake, "lake downstream hierarchy")
    if (downstream_lake == _m4_mountain_depression_geometry_np.arange(1, count + 1)).any():
        raise ValueError("lake spill routes back into itself")
    outlets = _m4_mountain_depression_geometry_np.flatnonzero(boundary.ravel())
    owner = arrays["outlet_owner"].ravel()
    area = arrays["outlet_area_m2"]
    accumulation = arrays["contributing_area_m2"].ravel()
    depression_equal(arrays["outlet_cells"], outlets, "outlet cells")
    if (owner < 0).any() or (owner >= outlets.size).any():
        raise ValueError("invalid outlet ownership")
    depression_equal(owner[outlets], _m4_mountain_depression_geometry_np.arange(outlets.size), "unique outlet identities")
    donors = _m4_mountain_depression_geometry_np.flatnonzero(receiver >= 0)
    depression_equal(owner[donors], owner[receiver[donors]], "local complete upstream ownership")
    depression_equal(area, _m4_mountain_depression_geometry_np.bincount(owner, minlength=outlets.size) * spacing ** 2, "all unique outlet areas")
    depression_equal(arrays["outlet_type"], _m4_mountain_depression_geometry_np.ones(outlets.size, dtype=_m4_mountain_depression_geometry_np.int64), "external outlet types")
    donor_sum = _m4_mountain_depression_geometry_np.bincount(receiver[donors], weights=accumulation[donors], minlength=height.size)
    depression_equal(accumulation, donor_sum + spacing ** 2, "local contributing area recurrence")
    depression_equal(accumulation[outlets], area, "outlet area conservation")
    flowline = accumulation >= budget.channel_area_m2
    depression_equal(arrays["flowline_mask"], flowline.reshape(height.shape), "channel area threshold")
    depression_equal(arrays["dry_channel_mask"], (flowline & ~wet).reshape(height.shape), "lake not dry river")
    accepted = arrays["accepted_mask"].ravel()
    selected = arrays["accepted_outlets"]
    depression_equal(accepted, selected[owner], "whole contribution groups")
    depression_equal(arrays["H1_m"], height, "unfilled valley H1")
    bed = arrays["H2_m"]
    depression_equal(arrays["cut_depth_m"], height - bed, "actual cut")
    depression_equal(arrays["cell_cut_volume_m3"], (height - bed) * spacing ** 2, "unique volume")
    cut = height - bed
    if (cut < -DEPRESSION_TOL).any() or cut.max() > budget.max_total_cut_m + DEPRESSION_TOL or cut.sum() * spacing ** 2 > budget.max_cut_volume_m3 + DEPRESSION_TOL:
        raise ValueError("cut/fill budget")
    shore = _m4_mountain_depression_geometry_ndimage.binary_dilation(wet.reshape(height.shape), structure=_m4_mountain_depression_geometry_ndimage.generate_binary_structure(2, 1)) & ~wet.reshape(height.shape)
    locked = arrays["lake_mask"] | shore | boundary | arrays["protected_mask"]
    depression_equal(bed[locked], height[locked], "lake, shore, boundary and protection unchanged")
    depression_equal(bed.ravel()[~accepted], height.ravel()[~accepted], "outside accepted groups unchanged")
    dry_donors = _m4_mountain_depression_geometry_np.flatnonzero(~wet & (receiver >= 0))
    targets = receiver[dry_donors]
    downstream = bed.ravel()[targets].copy()
    wet_targets = flat_labels[targets] > 0
    downstream[wet_targets] = stages[flat_labels[targets[wet_targets]] - 1]
    if (bed.ravel()[dry_donors] < downstream - DEPRESSION_TOL).any():
        raise ValueError("dry bed or lake-inlet uphill")
    candidate = arrays["candidate_H2_m"].ravel()
    reasons = _m4_mountain_depression_geometry_np.zeros(height.size, dtype=_m4_mountain_depression_geometry_np.int64)
    active = flowline & ~wet & ~locked.ravel()
    active_cells = _m4_mountain_depression_geometry_np.flatnonzero(active)
    active_targets = receiver[active_cells]
    expected = height.ravel()[active_cells] - budget.shallow_cut_m
    has_target = active_targets >= 0
    lower = candidate[_m4_mountain_depression_geometry_np.maximum(active_targets, 0)] + spacing * budget.min_dry_slope
    target_lakes = flat_labels[_m4_mountain_depression_geometry_np.maximum(active_targets, 0)]
    target_wet = target_lakes > 0
    lower[target_wet] = stages[target_lakes[target_wet] - 1]
    expected[has_target] = _m4_mountain_depression_geometry_np.maximum(expected[has_target], lower[has_target])
    failed = expected > height.ravel()[active_cells] + DEPRESSION_TOL
    reasons[active_cells[failed]] = 1
    expected[failed] = height.ravel()[active_cells[failed]]
    expected = _m4_mountain_depression_geometry_np.minimum(expected, height.ravel()[active_cells])
    depression_equal(candidate[active_cells], expected, "saved local bounded bed recurrence")
    depression_equal(candidate[~active], height.ravel()[~active], "inactive candidate unchanged")
    depression_equal(bed.ravel()[accepted], candidate[accepted], "accepted actual bed")
    if (reasons[accepted] > 0).any():
        raise ValueError("accepted slope failure")
    group_volume = _m4_mountain_depression_geometry_np.bincount(owner, weights=(height.ravel() - candidate) * spacing ** 2, minlength=outlets.size)
    failed_groups = _m4_mountain_depression_geometry_np.bincount(owner, weights=(reasons > 0).astype(float), minlength=outlets.size) > 0
    lake_groups = _m4_mountain_depression_geometry_np.bincount(owner, weights=wet.astype(float), minlength=outlets.size) > 0
    expected_selected = _m4_mountain_depression_geometry_np.zeros(outlets.size, dtype=bool)
    spent = 0.0
    for group in _m4_mountain_depression_geometry_np.argsort(-area, kind="stable"):
        if not lake_groups[group] or failed_groups[group] or group_volume[group] <= 0:
            continue
        if spent + group_volume[group] <= budget.max_cut_volume_m3 + DEPRESSION_TOL:
            expected_selected[group] = True
            spent += float(group_volume[group])
    depression_equal(selected, expected_selected, "fixed deterministic area-first budget selection")
    reasons[~accepted & (reasons == 0)] = 2
    depression_equal(arrays["rejection_code"], reasons.reshape(height.shape), "rejection evidence")
    section_cells = _m4_mountain_depression_geometry_np.flatnonzero(accepted & flowline & ~wet)
    depression_equal(arrays["section_cells"], section_cells, "section identity")
    depression_equal(arrays["section_offset_m"], _m4_mountain_depression_geometry_np.array([-spacing / 2, 0., spacing / 2]), "full cell sections")
    for section_key, surface_key in (("section_H0_m", "H0_m"), ("section_H1_m", "H1_m"), ("section_H2_m", "H2_m")):
        depression_equal(arrays[section_key], _m4_mountain_depression_geometry_np.repeat(arrays[surface_key].ravel()[section_cells, None], 3, axis=1), "shared bed sections")
    return {"accepted_area_m2": float(accepted.sum() * spacing ** 2), "cut_volume_m3": float(cut.sum() * spacing ** 2),
            "lake_capacity_m3": float(arrays["lake_capacity_m3"].sum()), "lake_count": count,
            "total_unique_area_m2": float(area.sum())}

# --- terrain_pipeline/mountain_depression_geometry.py:552 ---
def screen_single_pool_lakes(result, *, min_cells=4, max_event_work=4000000):
    """Screen every elevation event, deterministically; do not assemble dynamics."""
    if type(min_cells) is not int or min_cells < 1 or type(max_event_work) is not int or not 1 <= max_event_work <= 4000000:
        raise ValueError("invalid fixed screening resources")
    arrays = result["arrays"]
    labels = arrays["lake_id"]
    height = arrays["H0_m"]
    groups = _m4_mountain_depression_geometry_ndimage.find_objects(labels)
    decisions = []
    spent = labels.size
    for lake, slices in enumerate(groups, 1):
        mask = labels[slices] == lake
        count = int(mask.sum())
        if count < min_cells:
            decisions.append({"lake_id": lake, "status": "too_small", "cells": count})
            continue
        terrain = height[slices]
        levels = _m4_mountain_depression_geometry_np.unique(terrain[mask])
        work = mask.size * levels.size
        if spent + work > max_event_work:
            decisions.append({"lake_id": lake, "status": "event_resource_limit", "cells": count, "requested_work": work})
            continue
        spent += work
        disconnected = 0
        max_components = 0
        for level in levels:
            _, components = _m4_mountain_depression_geometry_ndimage.label(mask & (terrain <= level), _m4_mountain_depression_geometry_ndimage.generate_binary_structure(2, 1))
            disconnected += int(components > 1)
            max_components = max(max_components, components)
        source = int(arrays["spill_inside"][lake - 1])
        outside = int(arrays["spill_outside"][lake - 1])
        path = [outside]
        seen = {outside}
        flags = [] if disconnected == 0 else ["multiple_initial_pools"]
        while arrays["receiver"][path[-1]] >= 0:
            if spent >= max_event_work:
                flags.append("path_resource_limit")
                break
            spent += 1
            target = int(arrays["receiver"][path[-1]])
            if target in seen:
                flags.append("cycle")
                break
            if labels.flat[target] > 0:
                flags.append("downstream_lake_requires_cascade")
                break
            if height.flat[target] > height.flat[path[-1]] + DEPRESSION_TOL:
                flags.append("downstream_uphill")
                break
            seen.add(target)
            path.append(target)
        if height.flat[path[-1]] >= arrays["lake_stage_m"][lake - 1] - DEPRESSION_TOL:
            flags.append("downstream_not_strictly_lower")
        status = flags[0] if flags else "single_pool_static_candidate"
        decisions.append({"lake_id": lake, "status": status, "reason_flags": flags, "cells": count,
                          "all_elevation_events": int(levels.size), "disconnected_events": disconnected,
                          "max_wet_components": max_components, "event_work": work,
                          "bbox_cells": int(mask.size), "path_steps": len(path) - 1,
                          "capacity_m3": float(arrays["lake_capacity_m3"][lake - 1]),
                          "spill_inside": source, "spill_outside": outside, "downstream_path": path})
    return {"max_event_work": max_event_work, "event_work": spent, "decisions": decisions}

# --- terrain_pipeline/mountain_depression_geometry.py:615 ---
def save_mountain_geometry(path, result, *, trusted_height, source_binding):
    """Atomic hard-link publication; no overwrite, including racing writers."""
    validate_mountain_geometry(result, trusted_height=trusted_height, source_binding=source_binding)
    arrays = result["arrays"]
    manifest = {"metadata": result["metadata"], "hashes": {key: _hash(value) for key, value in arrays.items()}}
    payload = depression_json(manifest).encode("ascii")
    if len(payload) > MAX_METADATA:
        raise ValueError("metadata resource budget")
    target = _m4_mountain_depression_geometry_Path(path)
    if target.exists():
        raise FileExistsError(target)
    descriptor, temporary = _m4_mountain_depression_geometry_tempfile.mkstemp(prefix=".mountain-geometry-", suffix=".npz", dir=target.parent)
    try:
        with _m4_mountain_depression_geometry_os.fdopen(descriptor, "wb") as stream:
            _m4_mountain_depression_geometry_np.savez_compressed(stream, manifest=_m4_mountain_depression_geometry_np.frombuffer(payload, dtype=_m4_mountain_depression_geometry_np.uint8), **arrays)
            stream.flush()
            _m4_mountain_depression_geometry_os.fsync(stream.fileno())
        _m4_mountain_depression_geometry_os.link(temporary, target)
    finally:
        _m4_mountain_depression_geometry_os.unlink(temporary)

# --- terrain_pipeline/mountain_depression_geometry.py:637 ---
def load_mountain_geometry(path, *, trusted_height, source_binding):
    """Static cold loading with external source trust and pre-allocation checks."""
    with open(path, "rb") as stream:
        with _m4_mountain_depression_geometry_zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if len(names) != len(set(names)) or set(names) != {key + ".npy" for key in ARRAY_KEYS} | {"manifest.npy"}:
                raise ValueError("unexpected archive members")
            if sum(member.file_size for member in members) > DEPRESSION_MAX_BYTES:
                raise ValueError("archive decompression resource budget")
            headers = {}
            for member in members:
                with archive.open(member) as array_stream:
                    version = _m4_mountain_depression_geometry_np.lib.format.read_magic(array_stream)
                    if version != (1, 0):
                        raise ValueError("unsupported NPY header")
                    shape, fortran, dtype = _m4_mountain_depression_geometry_np.lib.format.read_array_header_1_0(array_stream)
                    if dtype.hasobject or dtype.kind not in "bifu" or _m4_mountain_depression_geometry_math.prod(shape) * dtype.itemsize + array_stream.tell() != member.file_size:
                        raise ValueError("unsafe array header")
                    if fortran:
                        raise ValueError("noncanonical Fortran archive")
                    headers[member.filename[:-4]] = (shape, dtype)
                    if member.filename == "manifest.npy":
                        if dtype != _m4_mountain_depression_geometry_np.dtype("uint8") or len(shape) != 1 or shape[0] > MAX_METADATA:
                            raise ValueError("manifest resource budget")
                    elif member.filename == "H0_m.npy":
                        preflight(tuple(shape), GeometryBudget())
            grid_shape = headers["H0_m"][0]
            cells = _m4_mountain_depression_geometry_math.prod(grid_shape)
            lakes = headers["lake_stage_m"][0]
            outlets = headers["outlet_cells"][0]
            sections = headers["section_cells"][0]
            if any(len(shape) != 1 or not 0 <= shape[0] <= cells for shape in (lakes, outlets, sections)):
                raise ValueError("bounded topology header dimensions")
            lake_keys = {"lake_stage_m", "lake_area_m2", "lake_capacity_m3", "lake_downstream_id",
                         "spill_lake_id", "spill_inside", "spill_outside", "spill_stage_m", "spill_width_m"}
            outlet_keys = {"outlet_cells", "outlet_area_m2", "outlet_type", "accepted_outlets"}
            for key in ARRAY_KEYS:
                shape, dtype = headers[key]
                expected_dtype = _m4_mountain_depression_geometry_np.dtype("bool" if key in BOOL_KEYS else "int64" if key in INT_KEYS else "float64")
                expected_shape = grid_shape if key in GRID_KEYS else lakes if key in lake_keys else outlets if key in outlet_keys else sections if key == "section_cells" else (3,) if key == "section_offset_m" else (sections[0], 3) if key.startswith("section_H") else (cells,)
                if dtype != expected_dtype or shape != expected_shape:
                    raise ValueError("schema header mismatch: " + key)
        stream.seek(0)
        with _m4_mountain_depression_geometry_np.load(stream, allow_pickle=False) as archive:
            manifest = _m4_mountain_depression_geometry_json.loads(archive["manifest"].tobytes().decode("ascii"))
            if set(archive.files) != set(manifest["hashes"]) | {"manifest"}:
                raise ValueError("manifest member mismatch")
            arrays = {key: archive[key].copy() for key in manifest["hashes"]}
    for key, values in arrays.items():
        if _hash(values) != manifest["hashes"][key]:
            raise ValueError("integrity hash mismatch")
    result = {"arrays": arrays, "metadata": manifest["metadata"]}
    validate_mountain_geometry(result, trusted_height=trusted_height, source_binding=source_binding)
    for key, values in arrays.items():
        arrays[key] = _m4_mountain_depression_geometry_np.frombuffer(values.tobytes(), dtype=values.dtype).reshape(values.shape)
    return result

# --- terrain_pipeline/mountain_pool_network.py:18 ---
POOL_NETWORK_MAX_STEPS = 1344

# --- terrain_pipeline/mountain_pool_network.py:19 ---
MAX_POOLS = 32

# --- terrain_pipeline/mountain_pool_network.py:20 ---
MAX_WORK = 4000000

# --- terrain_pipeline/mountain_pool_network.py:21 ---
WEIR_COEFFICIENT = 1.7

# --- terrain_pipeline/mountain_pool_network.py:22 ---
ABS_VOLUME_TOLERANCE_M3 = 1e-6

# --- terrain_pipeline/mountain_pool_network.py:23 ---
REL_VOLUME_TOLERANCE = 1e-10

# --- terrain_pipeline/mountain_pool_network.py:24 ---
POOL_NETWORK_MAX_ARCHIVE_BYTES = 32 * 1024 * 1024

# --- terrain_pipeline/mountain_pool_network.py:25 ---
POOL_ARRAY_KEYS = frozenset(("lake_ids", "pool_downstream", "pool_order", "allocation_counts", "owned_mask",
                            "first_lake_id",
                            "stage_m", "storage_m3", "lateral_volume_m3", "upstream_volume_m3",
                            "outflow_volume_m3", "pool_residual_m3", "external_outflow_volume_m3", "joint_residual_m3"))

# --- terrain_pipeline/mountain_pool_network.py:31 ---
def screen_complete_pool_groups(result, screening):
    """Complete contribution groups, every discrete pool event independently gated."""
    arrays = result["arrays"]
    owners = arrays["outlet_owner"].ravel()
    pool_groups = owners[arrays["spill_inside"]]
    decisions = {item["lake_id"]: item for item in screening["decisions"]}
    first = first_lake_ownership(result)
    proposed = []
    bbox = _m4_mountain_pool_network_ndimage.find_objects(arrays["lake_id"])
    for group in _m4_mountain_pool_network_np.argsort(-arrays["outlet_area_m2"], kind="stable"):
        lakes = _m4_mountain_pool_network_np.flatnonzero(pool_groups == group) + 1
        if not lakes.size or lakes.size > MAX_POOLS:
            continue
        flags = []
        paths = {}
        headrooms = {}
        for lake in lakes:
            event = decisions[int(lake)]
            if "disconnected_events" not in event or event["disconnected_events"] > 0:
                flags.append("multiple_initial_pools_or_unverified_events")
                continue
            path = [int(arrays["spill_outside"][lake - 1])]
            while arrays["receiver"][path[-1]] >= 0 and arrays["lake_id"].flat[path[-1]] == 0:
                target = int(arrays["receiver"][path[-1]])
                if target in path:
                    flags.append("cascade_cycle")
                    break
                path.append(target)
            if _m4_mountain_pool_network_np.any(_m4_mountain_pool_network_np.diff(arrays["H0_m"].ravel()[path]) > 1e-9):
                flags.append("downstream_original_bed_uphill")
            slices = bbox[lake - 1]
            expanded = tuple(slice(max(0, item.start - 1), min(arrays["H0_m"].shape[index], item.stop + 1)) for index, item in enumerate(slices))
            basin = arrays["lake_id"][expanded] == lake
            shore = _m4_mountain_pool_network_ndimage.binary_dilation(basin, structure=_m4_mountain_pool_network_ndimage.generate_binary_structure(2, 1)) & ~basin
            spill_row, spill_column = divmod(int(arrays["spill_outside"][lake - 1]), arrays["H0_m"].shape[1])
            shore[spill_row - expanded[0].start, spill_column - expanded[1].start] = False
            head = float(arrays["H0_m"][expanded][shore].min() - arrays["lake_stage_m"][lake - 1])
            if head <= 1e-9:
                flags.append("multiple_equal_or_lower_spills")
            paths[str(int(lake))] = path
            headrooms[str(int(lake))] = max(0., min(1., head * .5))
        proposed.append({"group": int(group), "outlet_cell": int(arrays["outlet_cells"][group]),
                         "area_m2": float(arrays["outlet_area_m2"][group]),
                         "lake_ids": lakes.tolist(), "reason_flags": sorted(set(flags)),
                         "status": "static_complete_pool_candidate" if not flags else "refused",
                         "paths": paths, "max_head_m": headrooms,
                         "pool_resolution": "30m_discrete_storage_cells_not_resolved_natural_lakes"})
    return {"groups": proposed, "first_lake_id": first,
            "selection_rule": "descending_complete_window_area_all_event_single_pools_no_unmodeled_shore",
            "max_pools": MAX_POOLS}

# --- terrain_pipeline/mountain_pool_network.py:83 ---
def route_complete_pool_group(result, proposal, *, local_q_m3_s, cell_owner, hru_area_m2, dt_s=900.):
    """Backward Euler V(next)+dt*C*b*head^1.5 = V(before)+incoming."""
    arrays, metadata = result["arrays"], result["metadata"]
    if proposal["status"] != "static_complete_pool_candidate":
        raise ValueError("complete static pool certificate required")
    _validate_forcing(result, local_q_m3_s, cell_owner, hru_area_m2, dt_s)
    if not isinstance(local_q_m3_s, _m4_mountain_pool_network_np.ndarray) or local_q_m3_s.ndim != 2:
        raise ValueError("two-dimensional forcing required")
    steps, hrus = local_q_m3_s.shape
    lakes = _m4_mountain_pool_network_np.asarray(proposal["lake_ids"], dtype=_m4_mountain_pool_network_np.int64)
    cell_counts = _m4_mountain_pool_network_np.bincount(arrays["lake_id"].ravel(), minlength=arrays["lake_stage_m"].size + 1)[lakes]
    if not 1 <= steps <= POOL_NETWORK_MAX_STEPS or lakes.size > MAX_POOLS or steps * int(cell_counts.sum()) * 64 > MAX_WORK:
        return {"status": "pool_work_limit", "requested_work": int(steps * cell_counts.sum() * 64)}
    if local_q_m3_s.dtype != _m4_mountain_pool_network_np.dtype("float64") or not _m4_mountain_pool_network_np.isfinite(local_q_m3_s).all() or (local_q_m3_s < 0).any():
        raise ValueError("invalid local forcing")
    group = proposal["group"]
    owned = arrays["outlet_owner"] == group
    first = first_lake_ownership(result)
    counts = _m4_mountain_pool_network_np.zeros((lakes.size + 1, hrus), dtype=_m4_mountain_pool_network_np.int64)
    counts[0] = _m4_mountain_pool_network_np.bincount(cell_owner[owned & (first == 0)], minlength=hrus)
    for index, lake in enumerate(lakes):
        counts[index + 1] = _m4_mountain_pool_network_np.bincount(cell_owner[owned & (first == lake)], minlength=hrus)
    if counts.sum() != owned.sum():
        raise ValueError("upstream area lost or duplicated")
    lateral = local_q_m3_s @ (counts * metadata["spacing_m"] ** 2 / hru_area_m2).T * dt_s
    stages = _m4_mountain_pool_network_np.zeros((steps + 1, lakes.size), dtype=_m4_mountain_pool_network_np.float64)
    storage = _m4_mountain_pool_network_np.zeros_like(stages)
    outflow = _m4_mountain_pool_network_np.zeros((steps, lakes.size), dtype=_m4_mountain_pool_network_np.float64)
    upstream = _m4_mountain_pool_network_np.zeros_like(outflow)
    residual = _m4_mountain_pool_network_np.zeros_like(outflow)
    terminal = lateral[:, 0].copy()
    pool_index = {int(lake): index for index, lake in enumerate(lakes)}
    downstream = _m4_mountain_pool_network_np.full(lakes.size, -1, dtype=_m4_mountain_pool_network_np.int64)
    for index, lake in enumerate(lakes):
        target_lake = int(arrays["lake_downstream_id"][lake - 1])
        if target_lake > 0:
            if target_lake not in pool_index:
                raise ValueError("downstream pool omitted from complete group")
            downstream[index] = pool_index[target_lake]
    rank = _m4_mountain_pool_network_np.empty(arrays["receiver"].size, dtype=_m4_mountain_pool_network_np.int64)
    rank[arrays["order"]] = _m4_mountain_pool_network_np.arange(rank.size)
    pool_order = _m4_mountain_pool_network_np.argsort(-rank[arrays["spill_inside"][lakes - 1]], kind="stable")
    failures = []
    floors = [arrays["H0_m"][arrays["lake_id"] == lake] for lake in lakes]
    for index, values in enumerate(floors):
        stages[0, index] = float(values.min())
    area = metadata["spacing_m"] ** 2
    width = metadata["spacing_m"]
    completed = 0
    for step in range(steps):
        next_storage = storage[step].copy()
        next_stage = stages[step].copy()
        next_outflow = _m4_mountain_pool_network_np.zeros(lakes.size)
        next_upstream = _m4_mountain_pool_network_np.zeros(lakes.size)
        next_residual = _m4_mountain_pool_network_np.zeros(lakes.size)
        terminal_step = lateral[step, 0]
        failed = False
        for index in pool_order:
            lake = int(lakes[index])
            spill = float(arrays["lake_stage_m"][lake - 1])
            upper = spill + proposal["max_head_m"][str(lake)]
            target = storage[step, index] + lateral[step, index + 1] + next_upstream[index]
            tolerance = ABS_VOLUME_TOLERANCE_M3 + REL_VOLUME_TOLERANCE * max(target, storage[step, index])
            def capacity(stage):
                return float(_m4_mountain_pool_network_np.maximum(stage - floors[index], 0).sum() * area)
            def discharge(stage):
                return WEIR_COEFFICIENT * width * max(stage - spill, 0.) ** 1.5
            available = capacity(upper) + dt_s * discharge(upper)
            if target > available + tolerance:
                failures.append({"step": step, "lake_id": lake, "code": "valid_shore_headroom_exceeded",
                                 "incoming_plus_storage_m3": float(target), "available_m3": float(available),
                                 "max_head_m": proposal["max_head_m"][str(lake)]})
                failed = True
                break
            lower = float(floors[index].min())
            stage = lower
            for iteration in range(64):
                stage = (lower + upper) / 2
                volume = capacity(stage)
                release = dt_s * discharge(stage)
                error = volume + release - target
                if abs(error) <= tolerance:
                    break
                if error > 0:
                    upper = stage
                else:
                    lower = stage
            else:
                failures.append({"step": step, "lake_id": lake, "code": "solver_precision_limit"})
                failed = True
                break
            next_stage[index], next_storage[index] = stage, volume
            next_outflow[index], next_residual[index] = release, error
            target_pool = downstream[index]
            if target_pool >= 0:
                next_upstream[target_pool] += release
            else:
                terminal_step += release
        if failed:
            break
        for index, target_pool in enumerate(downstream):
            if target_pool >= 0 and next_stage[target_pool] > arrays["lake_stage_m"][lakes[index] - 1] + 1e-9:
                failures.append({"step": step, "lake_id": int(lakes[index]), "code": "receiving_pool_submerges_free_weir"})
                failed = True
                break
        if failed:
            break
        storage[step + 1], stages[step + 1] = next_storage, next_stage
        outflow[step], upstream[step], residual[step] = next_outflow, next_upstream, next_residual
        terminal[step] = terminal_step
        completed += 1
    incoming = lateral[:completed].sum(axis=1)
    joint_residual = incoming - terminal[:completed] - _m4_mountain_pool_network_np.diff(storage[:completed + 1].sum(axis=1))
    returned = {"status": "complete_pool_group_feasible" if completed == steps else "complete_pool_group_refused",
            "scope": "finite_complete_window_contribution_group_one_way_pool_cascade_no_backwater_or_river_storage",
            "proposal": proposal, "completed_steps": completed, "requested_steps": steps,
            "failures": failures, "dt_s": dt_s, "weir_coefficient": WEIR_COEFFICIENT,
            "weir_width_m": width, "abs_volume_tolerance_m3": ABS_VOLUME_TOLERANCE_M3,
            "rel_volume_tolerance": REL_VOLUME_TOLERANCE,
            "arrays": {"lake_ids": lakes, "pool_downstream": downstream, "pool_order": pool_order,
                       "allocation_counts": counts, "owned_mask": owned,
                       "first_lake_id": first,
                       "stage_m": stages[:completed + 1], "storage_m3": storage[:completed + 1],
                       "lateral_volume_m3": lateral[:completed], "upstream_volume_m3": upstream[:completed],
                       "outflow_volume_m3": outflow[:completed], "pool_residual_m3": residual[:completed],
                       "external_outflow_volume_m3": terminal[:completed], "joint_residual_m3": joint_residual}}
    validate_complete_pool_group(returned, result, local_q_m3_s=local_q_m3_s,
                                 cell_owner=cell_owner, hru_area_m2=hru_area_m2)
    return returned

# --- terrain_pipeline/mountain_pool_network.py:214 ---
def _validate_forcing(geometry, local, owner, area, dt_s):
    shape = geometry["arrays"]["H0_m"].shape
    if type(dt_s) not in (int, float) or not _m4_mountain_pool_network_math.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("positive physical timestep required")
    if not isinstance(area, _m4_mountain_pool_network_np.ndarray) or area.dtype != _m4_mountain_pool_network_np.dtype("float64") or area.ndim != 1 or not 1 <= area.size <= 256 or not _m4_mountain_pool_network_np.isfinite(area).all() or (area <= 0).any():
        raise ValueError("positive finite HRU areas required")
    if not isinstance(owner, _m4_mountain_pool_network_np.ndarray) or owner.dtype != _m4_mountain_pool_network_np.dtype("int64") or owner.shape != shape or (owner < 0).any() or (owner >= area.size).any():
        raise ValueError("complete valid HRU owner required")
    expected = _m4_mountain_pool_network_np.bincount(owner.ravel(), minlength=area.size) * geometry["metadata"]["spacing_m"] ** 2
    if not _m4_mountain_pool_network_np.array_equal(area, expected):
        raise ValueError("original complete HRU area mismatch")
    if not isinstance(local, _m4_mountain_pool_network_np.ndarray) or local.dtype != _m4_mountain_pool_network_np.dtype("float64") or local.ndim != 2 or local.shape[1] != area.size or not 1 <= local.shape[0] <= POOL_NETWORK_MAX_STEPS or not _m4_mountain_pool_network_np.isfinite(local).all() or (local < 0).any():
        raise ValueError("bounded finite local forcing required")

# --- terrain_pipeline/mountain_pool_network.py:229 ---
def validate_complete_pool_group(saved, geometry, *, local_q_m3_s, cell_owner, hru_area_m2):
    """Static saved local balances and weir equations; never rerun pool dynamics."""
    arrays = saved["arrays"]
    _validate_forcing(geometry, local_q_m3_s, cell_owner, hru_area_m2, saved["dt_s"])
    if set(arrays) != POOL_ARRAY_KEYS:
        raise ValueError("fixed pool schema required")
    terrain = geometry["arrays"]
    spacing = geometry["metadata"]["spacing_m"]
    steps = saved["completed_steps"]
    lakes = arrays["lake_ids"]
    count = lakes.size
    group = saved["proposal"]["group"]
    if not 0 <= steps <= saved["requested_steps"] <= POOL_NETWORK_MAX_STEPS or count > MAX_POOLS:
        raise ValueError("static pool resource ceiling")
    if saved["requested_steps"] != local_q_m3_s.shape[0]:
        raise ValueError("requested forcing length")
    if saved["status"] == "complete_pool_group_feasible":
        if steps != saved["requested_steps"] or saved["failures"]:
            raise ValueError("pool success status forgery")
    elif saved["status"] == "complete_pool_group_refused":
        if steps == saved["requested_steps"] or not saved["failures"] or saved["failures"][0]["step"] != steps:
            raise ValueError("pool failure status forgery")
    else:
        raise ValueError("unknown pool status")
    if not _m4_mountain_pool_network_np.array_equal(_m4_mountain_pool_network_np.sort(arrays["pool_order"]), _m4_mountain_pool_network_np.arange(count)):
        raise ValueError("pool order permutation")
    pool_rank = _m4_mountain_pool_network_np.empty(count, dtype=_m4_mountain_pool_network_np.int64)
    pool_rank[arrays["pool_order"]] = _m4_mountain_pool_network_np.arange(count)
    for index, target in enumerate(arrays["pool_downstream"]):
        if target >= 0 and (target >= count or pool_rank[target] <= pool_rank[index]):
            raise ValueError("pool order downstream dependency")
    for key, values in arrays.items():
        if not isinstance(values, _m4_mountain_pool_network_np.ndarray) or not _m4_mountain_pool_network_np.isfinite(values).all():
            raise ValueError("nonfinite saved pool data")
        if key not in ("stage_m", "pool_downstream", "pool_residual_m3", "joint_residual_m3") and values.dtype.kind == "f" and (values < 0).any():
            raise ValueError("negative water")
    owned = terrain["outlet_owner"] == group
    if not _m4_mountain_pool_network_np.array_equal(arrays["owned_mask"], owned):
        raise ValueError("partial contribution group")
    counts = arrays["allocation_counts"]
    if not _m4_mountain_pool_network_np.array_equal(counts.sum(axis=0), _m4_mountain_pool_network_np.bincount(cell_owner[owned], minlength=hru_area_m2.size)):
        raise ValueError("omitted or double-counted upstream HRU area")
    if not _m4_mountain_pool_network_np.array_equal(_m4_mountain_pool_network_np.sort(lakes), _m4_mountain_pool_network_np.flatnonzero(terrain["outlet_owner"].ravel()[terrain["spill_inside"]] == group) + 1):
        raise ValueError("pool omitted from complete group")
    if (saved["weir_coefficient"] != WEIR_COEFFICIENT or saved["weir_width_m"] != spacing
            or saved["abs_volume_tolerance_m3"] != ABS_VOLUME_TOLERANCE_M3
            or saved["rel_volume_tolerance"] != REL_VOLUME_TOLERANCE):
        raise ValueError("weir or tolerance identity forgery")
    first = arrays["first_lake_id"].ravel()
    labels = terrain["lake_id"].ravel()
    donors = _m4_mountain_pool_network_np.flatnonzero(terrain["receiver"] >= 0)
    if arrays["first_lake_id"].shape != owned.shape or arrays["first_lake_id"].dtype != _m4_mountain_pool_network_np.dtype("int64"):
        raise ValueError("saved first lake schema")
    if not _m4_mountain_pool_network_np.array_equal(first[labels > 0], labels[labels > 0]):
        raise ValueError("lake anchor mismatch")
    dry_donors = donors[labels[donors] == 0]
    if not _m4_mountain_pool_network_np.array_equal(first[dry_donors], first[terrain["receiver"][dry_donors]]) or (first[terrain["receiver"] < 0] != 0).any():
        raise ValueError("saved local first-lake recurrence")
    expected_counts = _m4_mountain_pool_network_np.zeros_like(counts)
    expected_counts[0] = _m4_mountain_pool_network_np.bincount(cell_owner[owned & (first.reshape(owned.shape) == 0)], minlength=hru_area_m2.size)
    for index, lake in enumerate(lakes):
        expected_counts[index + 1] = _m4_mountain_pool_network_np.bincount(cell_owner[owned & (first.reshape(owned.shape) == lake)], minlength=hru_area_m2.size)
    if not _m4_mountain_pool_network_np.array_equal(counts, expected_counts):
        raise ValueError("first-pool allocation forged")
    pool_index = {int(lake): index for index, lake in enumerate(lakes)}
    expected_downstream = _m4_mountain_pool_network_np.array([pool_index.get(int(terrain["lake_downstream_id"][lake - 1]), -1) for lake in lakes])
    if not _m4_mountain_pool_network_np.array_equal(arrays["pool_downstream"], expected_downstream):
        raise ValueError("cascade connectivity forged")
    lateral = local_q_m3_s[:steps] @ (counts * spacing ** 2 / hru_area_m2).T * saved["dt_s"]
    def equal(actual, expected, name, tolerance=1e-8):
        if actual.shape != expected.shape or not _m4_mountain_pool_network_np.allclose(actual, expected, rtol=1e-12, atol=tolerance):
            raise ValueError("static pool mismatch: " + name)
    equal(arrays["lateral_volume_m3"], lateral, "authentic local forcing")
    if arrays["storage_m3"].shape != (steps + 1, count) or arrays["stage_m"].shape != (steps + 1, count):
        raise ValueError("state shape")
    if (arrays["storage_m3"][0] != 0).any():
        raise ValueError("initial water invented")
    releases = arrays["outflow_volume_m3"]
    upstream = _m4_mountain_pool_network_np.zeros((steps, count), dtype=_m4_mountain_pool_network_np.float64)
    for index, downstream in enumerate(arrays["pool_downstream"]):
        if downstream >= 0:
            if downstream >= count:
                raise ValueError("invalid cascade downstream")
            upstream[:, downstream] += releases[:, index]
    equal(arrays["upstream_volume_m3"], upstream, "each internal release injected once")
    for index, lake in enumerate(lakes):
        stage = arrays["stage_m"][:, index]
        basin = terrain["lake_id"] == lake
        slices = _m4_mountain_pool_network_ndimage.find_objects(basin.astype(_m4_mountain_pool_network_np.int64))[0]
        cropped = basin[slices]
        local_height = terrain["H0_m"][slices]
        floors = local_height[cropped]
        for level in _m4_mountain_pool_network_np.unique(floors):
            if _m4_mountain_pool_network_ndimage.label(cropped & (local_height <= level), _m4_mountain_pool_network_ndimage.generate_binary_structure(2, 1))[1] > 1:
                raise ValueError("multi-initial-pool caller proposal forged")
        shore = _m4_mountain_pool_network_ndimage.binary_dilation(basin, structure=_m4_mountain_pool_network_ndimage.generate_binary_structure(2, 1)) & ~basin
        spill_cell = int(terrain["spill_outside"][lake - 1])
        shore.flat[spill_cell] = False
        spill = terrain["lake_stage_m"][lake - 1]
        expected_head = min(1., float(terrain["H0_m"][shore].min() - spill) * .5)
        if expected_head <= 0 or saved["proposal"]["max_head_m"][str(int(lake))] != expected_head:
            raise ValueError("shore headroom forged")
        path = saved["proposal"]["paths"][str(int(lake))]
        if len(path) < 1 or path[0] != spill_cell or any(terrain["receiver"][before] != after for before, after in zip(path[:-1], path[1:])):
            raise ValueError("downstream path identity")
        if _m4_mountain_pool_network_np.any(_m4_mountain_pool_network_np.diff(terrain["H0_m"].ravel()[path]) > 1e-9):
            raise ValueError("downstream path uphill")
        target_pool = arrays["pool_downstream"][index]
        if target_pool < 0:
            if terrain["receiver"][path[-1]] != -1 or not terrain["boundary_mask"].flat[path[-1]]:
                raise ValueError("unproven external terminal")
        elif terrain["lake_id"].flat[path[-1]] != lakes[target_pool]:
            raise ValueError("receiving pool path mismatch")
        if target_pool >= 0 and (arrays["stage_m"][:, target_pool] > spill + 1e-9).any():
            raise ValueError("submerged free-weir invalid")
        volume = _m4_mountain_pool_network_np.maximum(stage[:, None] - floors[None, :], 0).sum(axis=1) * spacing ** 2
        equal(arrays["storage_m3"][:, index], volume, "native capacity equation")
        spill = terrain["lake_stage_m"][lake - 1]
        head = _m4_mountain_pool_network_np.maximum(stage[1:] - spill, 0)
        if (head > saved["proposal"]["max_head_m"][str(int(lake))] + 1e-9).any():
            raise ValueError("shore limit forged")
        expected_release = saved["dt_s"] * WEIR_COEFFICIENT * spacing * head ** 1.5
        equal(releases[:, index], expected_release, "exact engineering weir")
    change = _m4_mountain_pool_network_np.diff(arrays["storage_m3"], axis=0)
    pool_residual = lateral[:, 1:] + upstream - releases - change
    equal(arrays["pool_residual_m3"], -pool_residual, "per-pool ledger sign")
    tolerance = ABS_VOLUME_TOLERANCE_M3 + REL_VOLUME_TOLERANCE * _m4_mountain_pool_network_np.maximum(arrays["storage_m3"][:-1], lateral[:, 1:] + upstream + arrays["storage_m3"][:-1])
    if (_m4_mountain_pool_network_np.abs(pool_residual) > tolerance * 1.01).any():
        raise ValueError("local pool volume imbalance")
    terminal = lateral[:, 0] + releases[:, arrays["pool_downstream"] < 0].sum(axis=1)
    equal(arrays["external_outflow_volume_m3"], terminal, "explicit external exit")
    joint = lateral.sum(axis=1) - terminal - change.sum(axis=1)
    equal(arrays["joint_residual_m3"], joint, "complete group ledger")
    if (_m4_mountain_pool_network_np.abs(joint) > tolerance.sum(axis=1) * 1.01).any():
        raise ValueError("complete group water budget")
    return {"max_pool_residual_m3": float(_m4_mountain_pool_network_np.abs(pool_residual).max(initial=0)),
            "max_joint_residual_m3": float(_m4_mountain_pool_network_np.abs(joint).max(initial=0)),
            "input_volume_m3": float(lateral.sum()), "external_outflow_m3": float(terminal.sum()),
            "final_storage_m3": float(arrays["storage_m3"][-1].sum()),
            "total_residual_m3": float(lateral.sum() - terminal.sum() - arrays["storage_m3"][-1].sum())}

# --- terrain_pipeline/mountain_pool_network.py:371 ---
def save_pool_group(path, saved, geometry, *, local_q_m3_s, cell_owner, hru_area_m2):
    validate_complete_pool_group(saved, geometry, local_q_m3_s=local_q_m3_s,
                                 cell_owner=cell_owner, hru_area_m2=hru_area_m2)
    metadata = {key: value for key, value in saved.items() if key != "arrays"}
    binding = {"geometry_H0_sha256": geometry["metadata"]["H0_sha256"],
               "source_binding": geometry["metadata"]["source_binding"],
               "forcing_sha256": _hash(local_q_m3_s), "cell_owner_sha256": _hash(cell_owner),
               "hru_area_sha256": _hash(hru_area_m2)}
    manifest = {"metadata": metadata, "binding": binding,
                "hashes": {key: _hash(value) for key, value in saved["arrays"].items()}}
    payload = depression_json(manifest).encode("ascii")
    if len(payload) > 65536:
        raise ValueError("pool metadata ceiling")
    target = _m4_mountain_pool_network_Path(path)
    if target.exists():
        raise FileExistsError(target)
    descriptor, temporary = _m4_mountain_pool_network_tempfile.mkstemp(prefix=".mountain-pool-", suffix=".npz", dir=target.parent)
    try:
        with _m4_mountain_pool_network_os.fdopen(descriptor, "wb") as stream:
            _m4_mountain_pool_network_np.savez_compressed(stream, manifest=_m4_mountain_pool_network_np.frombuffer(payload, dtype=_m4_mountain_pool_network_np.uint8), **saved["arrays"])
            stream.flush()
            _m4_mountain_pool_network_os.fsync(stream.fileno())
        _m4_mountain_pool_network_os.link(temporary, target)
    finally:
        _m4_mountain_pool_network_os.unlink(temporary)

# --- terrain_pipeline/mountain_pool_network.py:398 ---
def load_pool_group(path, geometry, *, local_q_m3_s, cell_owner, hru_area_m2):
    """Static exact-equation checks, never advance, assemble, or infer terrain."""
    expected_names = {key + ".npy" for key in POOL_ARRAY_KEYS} | {"manifest.npy"}
    with open(path, "rb") as stream:
        with _m4_mountain_pool_network_zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            if len(members) != len(expected_names) or {item.filename for item in members} != expected_names:
                raise ValueError("pool archive schema")
            if sum(item.file_size for item in members) > POOL_NETWORK_MAX_ARCHIVE_BYTES:
                raise ValueError("pool archive resource ceiling")
            headers = {}
            for member in members:
                with archive.open(member) as item:
                    if _m4_mountain_pool_network_np.lib.format.read_magic(item) != (1, 0):
                        raise ValueError("NPY version")
                    shape, fortran, dtype = _m4_mountain_pool_network_np.lib.format.read_array_header_1_0(item)
                    key = member.filename[:-4]
                    headers[key] = shape
                    expected_dtype = _m4_mountain_pool_network_np.dtype("uint8" if key == "manifest" else "bool" if key == "owned_mask" else "int64" if key in ("first_lake_id", "lake_ids", "pool_downstream", "pool_order", "allocation_counts") else "float64")
                    if fortran or dtype != expected_dtype or dtype.hasobject or _m4_mountain_pool_network_math.prod(shape) * dtype.itemsize + item.tell() != member.file_size:
                        raise ValueError("pool header schema")
                    if key == "manifest" and (len(shape) != 1 or shape[0] > 65536):
                        raise ValueError("pool metadata ceiling")
                    if key in ("owned_mask", "first_lake_id") and shape != geometry["arrays"]["H0_m"].shape:
                        raise ValueError("pool grid shape")
                    if key not in ("owned_mask", "first_lake_id", "manifest") and (len(shape) not in (1, 2) or any(value > POOL_NETWORK_MAX_STEPS + 1 for value in shape)):
                        raise ValueError("pool header dimensions")
            count = headers["lake_ids"][0]
            if headers["lake_ids"] != (count,) or not 1 <= count <= MAX_POOLS:
                raise ValueError("pool lake-axis resource ceiling")
            state_shape = headers["stage_m"]
            if len(state_shape) != 2:
                raise ValueError("pool state header dimensions")
            completed = state_shape[0] - 1
            if not 0 <= completed <= local_q_m3_s.shape[0]:
                raise ValueError("pool completed header range")
            shapes = {"lake_ids": (count,), "pool_downstream": (count,), "pool_order": (count,),
                      "allocation_counts": (count + 1, hru_area_m2.size),
                      "stage_m": (completed + 1, count), "storage_m3": (completed + 1, count),
                      "lateral_volume_m3": (completed, count + 1),
                      "upstream_volume_m3": (completed, count), "outflow_volume_m3": (completed, count),
                      "pool_residual_m3": (completed, count), "external_outflow_volume_m3": (completed,),
                      "joint_residual_m3": (completed,)}
            for key, shape in shapes.items():
                if headers[key] != shape:
                    raise ValueError("exact pool header shape: " + key)
        stream.seek(0)
        with _m4_mountain_pool_network_np.load(stream, allow_pickle=False) as archive:
            manifest = _m4_mountain_pool_network_json.loads(archive["manifest"].tobytes().decode("ascii"))
            arrays = {key: archive[key].copy() for key in POOL_ARRAY_KEYS}
    expected_binding = {"geometry_H0_sha256": geometry["metadata"]["H0_sha256"],
                        "source_binding": geometry["metadata"]["source_binding"],
                        "forcing_sha256": _hash(local_q_m3_s), "cell_owner_sha256": _hash(cell_owner),
                        "hru_area_sha256": _hash(hru_area_m2)}
    if manifest["binding"] != expected_binding or set(manifest["hashes"]) != POOL_ARRAY_KEYS:
        raise ValueError("external pool trust mismatch")
    for key, values in arrays.items():
        if _hash(values) != manifest["hashes"][key]:
            raise ValueError("pool integrity")
    saved = dict(manifest["metadata"], arrays=arrays)
    validate_complete_pool_group(saved, geometry, local_q_m3_s=local_q_m3_s,
                                 cell_owner=cell_owner, hru_area_m2=hru_area_m2)
    saved["arrays"] = {key: _m4_mountain_pool_network_np.frombuffer(value.tobytes(), dtype=value.dtype).reshape(value.shape) for key, value in arrays.items()}
    return saved

# --- terrain_pipeline/mountain_lake_experiment.py:9 ---
LAKE_EXPERIMENT_MAX_STEPS = 1344

# --- terrain_pipeline/mountain_lake_experiment.py:10 ---
MAX_CANDIDATES = 64

# --- terrain_pipeline/mountain_lake_experiment.py:11 ---
MAX_LAKE_WORK = 4000000

# --- terrain_pipeline/mountain_lake_experiment.py:14 ---
def first_lake_ownership(result):
    """Full-window first lake mapping, not downstream accumulated-Q injection."""
    arrays = result["arrays"]
    labels = arrays["lake_id"].ravel()
    receiver = arrays["receiver"]
    first = _m4_mountain_lake_experiment_np.zeros(receiver.size, dtype=_m4_mountain_lake_experiment_np.int64)
    for cell in arrays["order"]:
        if labels[cell] > 0:
            first[cell] = labels[cell]
        elif receiver[cell] >= 0:
            first[cell] = first[receiver[cell]]
    return first.reshape(arrays["H0_m"].shape)

# --- terrain_pipeline/mountain_lake_experiment.py:28 ---
def select_leaf_pool(result, screening):
    """Largest complete local contributing area, no omitted upstream lake input."""
    arrays = result["arrays"]
    ownership = first_lake_ownership(result)
    count = arrays["lake_stage_m"].size
    contributions = _m4_mountain_lake_experiment_np.bincount(ownership.ravel(), minlength=count + 1)
    upstream = _m4_mountain_lake_experiment_np.bincount(arrays["lake_downstream_id"][arrays["lake_downstream_id"] > 0], minlength=count + 1)
    candidates = []
    for decision in screening["decisions"]:
        lake = decision["lake_id"]
        if decision["status"] != "single_pool_static_candidate" or upstream[lake] > 0:
            continue
        candidates.append((int(contributions[lake]), lake, decision))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return {"first_lake_id": ownership, "upstream_lake_count": upstream[1:],
            "local_contribution_cells": contributions[1:],
            "candidates": [item[2] for item in candidates],
            "selected": candidates[0][2] if candidates else None,
            "selection_rule": "all_event_single_pool_and_no_upstream_lakes_then_max_complete_local_area"}

# --- terrain_pipeline/mountain_lake_experiment.py:49 ---
def select_leaf_transfer(result, screening):
    """Single-pool leaf to explicit receiving-lake storage, including full local area."""
    arrays = result["arrays"]
    first = first_lake_ownership(result)
    count = arrays["lake_stage_m"].size
    contributions = _m4_mountain_lake_experiment_np.bincount(first.ravel(), minlength=count + 1)
    upstream = _m4_mountain_lake_experiment_np.bincount(arrays["lake_downstream_id"][arrays["lake_downstream_id"] > 0], minlength=count + 1)
    candidates = []
    refusals = []
    for decision in screening["decisions"]:
        lake = decision["lake_id"]
        if decision.get("disconnected_events", 1) or upstream[lake] > 0:
            continue
        flags = decision.get("reason_flags", [])
        if any(flag not in ("downstream_lake_requires_cascade", "downstream_not_strictly_lower") for flag in flags):
            continue
        path = list(decision["downstream_path"])
        target = int(arrays["receiver"][path[-1]])
        if target < 0 or arrays["lake_id"].flat[target] <= 0:
            continue
        path.append(target)
        if _m4_mountain_lake_experiment_np.any(_m4_mountain_lake_experiment_np.diff(arrays["H0_m"].ravel()[path]) > 1e-9):
            refusals.append({"lake_id": lake, "reason": "leaf_transfer_path_uphill"})
            continue
        receiving_lake = int(arrays["lake_id"].flat[target])
        capacity = float(arrays["lake_capacity_m3"][receiving_lake - 1])
        pool = arrays["lake_id"] == lake
        shore = _m4_mountain_lake_experiment_ndimage.binary_dilation(pool, structure=_m4_mountain_lake_experiment_ndimage.generate_binary_structure(2, 1)) & ~pool
        shore.flat[decision["spill_outside"]] = False
        gap = float(arrays["H0_m"][shore].min() - arrays["lake_stage_m"][lake - 1])
        if gap <= 1e-9:
            refusals.append({"lake_id": lake, "reason": "no_exclusive_single_spill_headroom"})
            continue
        proposal = dict(decision, downstream_path=path, receiving_lake_id=receiving_lake,
                        receiving_capacity_m3=capacity, local_contribution_cells=int(contributions[lake]),
                        upstream_lakes=[], shore_gap_m=gap)
        candidates.append(proposal)
    candidates.sort(key=lambda item: (-item["local_contribution_cells"], item["lake_id"]))
    return {"candidates": candidates[:MAX_CANDIDATES], "refusals": refusals,
            "first_lake_id": first, "upstream_lake_count": upstream[1:],
            "local_contribution_cells": contributions[1:],
            "selection_rule": "all_event_connected_no_upstream_lake_then_max_complete_area_to_receiving_storage",
            "max_candidates": MAX_CANDIDATES}

# --- terrain_pipeline/mountain_lake_experiment.py:94 ---
def run_leaf_lake(result, selected, *, local_q_m3_s, cell_owner, hru_area_m2, dt_s=900.,
                  volume_abs_tolerance_m3=1e-6):
    """Dry initial engineering pool, genuine first-lake runoff; no new rainfall model."""
    arrays, metadata = result["arrays"], result["metadata"]
    height = arrays["H0_m"]
    lake = selected["lake_id"]
    if local_q_m3_s.dtype != _m4_mountain_lake_experiment_np.dtype("float64") or local_q_m3_s.ndim != 2 or not 1 <= local_q_m3_s.shape[0] <= LAKE_EXPERIMENT_MAX_STEPS:
        raise ValueError("bounded authentic interval forcing required")
    if not _m4_mountain_lake_experiment_np.isfinite(local_q_m3_s).all() or (local_q_m3_s < 0).any() or cell_owner.shape != height.shape:
        raise ValueError("invalid local forcing")
    basin = arrays["lake_id"] == lake
    owned = first_lake_ownership(result) == lake
    if (arrays["lake_downstream_id"] == lake).any():
        raise ValueError("upstream lake outflows would be omitted")
    counts = _m4_mountain_lake_experiment_np.bincount(cell_owner[owned], minlength=hru_area_m2.size)
    fractions = counts * metadata["spacing_m"] ** 2 / hru_area_m2
    inflow = local_q_m3_s @ fractions
    spill = _m4_mountain_lake_experiment_np.unravel_index(selected["spill_outside"], height.shape)
    path_flat = _m4_mountain_lake_experiment_np.asarray(selected["downstream_path"], dtype=_m4_mountain_lake_experiment_np.int64)
    if path_flat.size < 2:
        raise ValueError("complete downstream route required")
    path = _m4_mountain_lake_experiment_np.column_stack(_m4_mountain_lake_experiment_np.unravel_index(path_flat, height.shape))
    shore = _m4_mountain_lake_experiment_ndimage.binary_dilation(basin, structure=_m4_mountain_lake_experiment_ndimage.generate_binary_structure(2, 1)) & ~basin
    shore[spill] = False
    stage = float(height[spill])
    gap = float(height[shore].min() - stage)
    if gap <= 1e-9:
        return {"status": "refused", "reason": "no_exclusive_single_spill_headroom", "lake_id": lake, "shore_gap_m": gap}
    maximum_stage = stage + min(1.0, gap * .5)
    if maximum_stage <= stage:
        raise ValueError("no representable stage headroom")
    rating_stages = _m4_mountain_lake_experiment_np.linspace(stage, maximum_stage, 129)
    rating_rates = 1.7 * metadata["spacing_m"] * _m4_mountain_lake_experiment_np.maximum(rating_stages - stage, 0.) ** 1.5
    recipe = LakeRoutingRecipe(initial_stage_m=float(height[basin].min()), dt_s=float(dt_s),
        inflow_m3_s=tuple(map(float, inflow)), loss_m3_s=tuple(_m4_mountain_lake_experiment_np.zeros(inflow.size)),
        rating_stage_m=tuple(map(float, rating_stages)), rating_outflow_m3_s=tuple(map(float, rating_rates)),
        max_stage_m=maximum_stage, max_grid_cells=250000,
        volume_abs_tolerance_m3=volume_abs_tolerance_m3)
    legal = arrays["boundary_mask"].copy()
    receiving_lake = selected.get("receiving_lake_id")
    if receiving_lake is not None:
        legal[:] = False
        legal[tuple(path[-1])] = True
    evidence = evaluate_lake_routing(height, basin, spill, metadata["spacing_m"], metadata["spacing_m"],
        metadata["H0_sha256"], recipe, path, _m4_mountain_lake_experiment_np.ones(height.shape, dtype=bool), arrays["protected_mask"],
        legal, *metadata["origin_m_xz"], "legacy_shifted_sea_zero_m")
    returned = {"status": evidence["diagnostic"]["code"], "lake_id": lake,
            "scope": "authentic_complete_leaf_local_catchment_not_whole_window_dynamics",
            "initial_storage_m3": 0., "upstream_lakes": [],
            "owned_area_m2": float(counts.sum() * metadata["spacing_m"] ** 2),
            "allocation_counts": counts, "first_lake_owned_mask": owned,
            "local_q_m3_s": inflow, "shore_gap_m": gap,
            "rating_assumption": "engineering_weir_Q=1.7*b*head^1.5_b=one_full_grid_edge_129_piecewise_linear_nodes_not_calibrated",
            "weir_coefficient_m_half_per_s": 1.7, "weir_width_m": metadata["spacing_m"],
            "max_valid_head_m": maximum_stage - stage,
            "evidence": evidence}
    if receiving_lake is not None:
        transfer = evidence["arrays"]["step_outflow_volume_m3"]
        storage = _m4_mountain_lake_experiment_np.r_[0., _m4_mountain_lake_experiment_np.cumsum(transfer)]
        capacity = float(arrays["lake_capacity_m3"][receiving_lake - 1])
        completed = evidence["summary"]["completed_steps"]
        incoming = inflow[:completed] * dt_s
        leaf_storage = evidence["arrays"]["storage_m3"]
        residual = incoming - _m4_mountain_lake_experiment_np.diff(leaf_storage) - _m4_mountain_lake_experiment_np.diff(storage)
        returned["terminal"] = {"type": "receiving_lake_incremental_storage_no_stage_claim",
                                "lake_id": receiving_lake, "capacity_m3": capacity,
                                "storage_m3": storage, "transfer_volume_m3": transfer.copy(),
                                "combined_step_residual_m3": residual,
                                "capacity_exceeded": bool((storage > capacity + 1e-6).any()),
                                "other_catchments": "outside_leaf_transfer_experiment_not_silently_zero_for_whole_window"}
        if returned["terminal"]["capacity_exceeded"]:
            returned["status"] = "receiving_storage_capacity_exceeded"
    return returned

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:14 ---
DOMAIN_SCHEMA = "terragenesis-natural-lake-domain-v1"

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:15 ---
TRACE_SCHEMA = "terragenesis-natural-lake-trace-v1"

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:16 ---
NATURAL_LAKES_ALGORITHM = "original-bed-d4-owner-pools-signed-weirs-v1"

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:17 ---
MAX_SUPPORT = 65536

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:18 ---
MAX_FACES = 4096

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:19 ---
MAX_TRACE_ENTRIES = 8_000_000

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:20 ---
NATURAL_LAKES_MAX_BYTES = 128 * 1024 * 1024

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:21 ---
BOUNDARY_KINDS = ("free_outflow", "tailwater", "closed", "unknown")

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:25 ---
@_m4_natural_lakes_dataclass(frozen=True)
class NaturalLakeConfig:
    max_step_seconds: float = 1.
    relative_tolerance: float = 1e-9
    absolute_tolerance_m3: float = 1e-10
    max_steps: int = 20000

    def __post_init__(self):
        for name in ("max_step_seconds", "relative_tolerance", "absolute_tolerance_m3"):
            value = getattr(self, name)
            if isinstance(value, (bool, _m4_natural_lakes_np.bool_)) or not isinstance(value, (int, float)) or not _m4_natural_lakes_math.isfinite(value) or value <= 0.:
                raise ValueError("positive finite " + name + " required")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 100000:
            raise ValueError("bounded max_steps required")

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:40 ---
def naturallakes_neighbors(cell, rows, cols):
    row, col = divmod(int(cell), cols)
    if row:
        yield cell - cols
    if col:
        yield cell - 1
    if col + 1 < cols:
        yield cell + 1
    if row + 1 < rows:
        yield cell + cols

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:52 ---
def _face(a, b, shape):
    if b < 0:
        return False
    rows, cols = shape
    if a < 0 or a >= rows * cols or b >= rows * cols:
        return False
    return b in naturallakes_neighbors(a, rows, cols)

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:61 ---
def _terrain_metadata(terrain):
    return {key: getattr(terrain, key) for key in terrain.__dataclass_fields__
            if key not in ("elevation_m", "valid_mask")}

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:66 ---
def _domain_expected(terrain, seeds, owner, boundary_faces, boundary_kinds, max_stage):
    shape = terrain.elevation_m.shape
    height = terrain.elevation_m.ravel()
    valid = terrain.valid_mask.ravel()
    flat = owner.ravel()
    count = len(seeds)
    if (seeds.dtype != _m4_natural_lakes_np.int64 or seeds.shape != (count,) or not 1 <= count <= 256
            or _m4_natural_lakes_np.unique(seeds).size != count or _m4_natural_lakes_np.any(seeds < 0) or _m4_natural_lakes_np.any(seeds >= height.size)
            or owner.dtype != _m4_natural_lakes_np.int64 or owner.shape != shape
            or _m4_natural_lakes_np.any(flat < -1) or _m4_natural_lakes_np.any(flat >= count) or _m4_natural_lakes_np.any(flat[~valid] != -1)
            or _m4_natural_lakes_np.count_nonzero(flat >= 0) > MAX_SUPPORT):
        raise ValueError("invalid bounded original-bed lake ownership")
    if (max_stage.dtype != _m4_natural_lakes_np.float64 or max_stage.shape != (count,)
            or not _m4_natural_lakes_np.isfinite(max_stage).all() or not valid[seeds].all()
            or not _m4_natural_lakes_np.array_equal(flat[seeds], _m4_natural_lakes_np.arange(count))):
        raise ValueError("invalid source seeds or finite upper stages")
    support = _m4_natural_lakes_np.flatnonzero(flat >= 0).astype(_m4_natural_lakes_np.int64)
    for lake, seed in enumerate(seeds):
        members = support[flat[support] == lake]
        if max_stage[lake] <= height[seed]:
            raise ValueError("max stage must exceed original seed bed")
        visited = _m4_natural_lakes_np.zeros(height.size, bool)
        visited[seed] = True
        pending = _m4_natural_lakes_deque([int(seed)])
        while pending:
            cell = pending.popleft()
            for neighbor in naturallakes_neighbors(cell, *shape):
                if (not visited[neighbor] and flat[neighbor] == lake
                        and height[neighbor] >= height[cell]):
                    visited[neighbor] = True
                    pending.append(neighbor)
        if not visited[members].all():
            raise ValueError("owner cells lack D4 nonascending original-bed path to seed")
    if (boundary_faces.dtype != _m4_natural_lakes_np.int64 or boundary_faces.ndim != 2
            or boundary_faces.shape[1] != 2 or len(boundary_faces) > MAX_FACES
            or boundary_kinds.dtype.kind != "U" or boundary_kinds.shape != (len(boundary_faces),)
            or not _m4_natural_lakes_np.isin(boundary_kinds, BOUNDARY_KINDS).all()):
        raise ValueError("invalid bounded boundary faces or kinds")
    interior = []
    exterior = []
    exterior_crest = {}
    rows, cols = shape
    for cell in support:
        for neighbor in (cell + 1, cell + cols):
            if neighbor >= height.size or neighbor == cell + 1 and cell % cols == cols - 1:
                continue
            if flat[neighbor] >= 0 and flat[neighbor] != flat[cell]:
                interior.append((int(cell), int(neighbor)))
        for neighbor in naturallakes_neighbors(cell, rows, cols):
            if flat[neighbor] == -1:
                exterior.append((int(cell), int(neighbor)))
                exterior_crest[(int(cell), int(neighbor))] = float(max(height[cell], height[neighbor])) if valid[neighbor] else float(height[cell])
        row, col = divmod(int(cell), cols)
        if row == 0 or row == rows - 1 or col == 0 or col == cols - 1:
            exterior.append((int(cell), -1))
            exterior_crest[(int(cell), -1)] = float(height[cell])
    interior = _m4_natural_lakes_np.asarray(interior, _m4_natural_lakes_np.int64).reshape(-1, 2)
    exterior = _m4_natural_lakes_np.asarray(sorted(exterior), _m4_natural_lakes_np.int64).reshape(-1, 2)
    if len(interior) + len(exterior) > MAX_FACES:
        raise ValueError("D4 face budget exceeded")
    permitted = set(map(tuple, exterior))
    chosen = list(map(tuple, boundary_faces))
    if len(set(chosen)) != len(chosen) or any(face not in permitted for face in chosen):
        raise ValueError("boundary requires distinct original valid D4 exterior witness")
    if boundary_faces.size and _m4_natural_lakes_np.any(~valid[boundary_faces[:, 0]]):
        raise ValueError("boundary touches unknown original source")
    internal_crest = _m4_natural_lakes_np.maximum(height[interior[:, 0]], height[interior[:, 1]])
    boundary_crest = _m4_natural_lakes_np.asarray([exterior_crest[face] for face in chosen], _m4_natural_lakes_np.float64)
    unresolved_faces = sorted(permitted - set(chosen))
    unresolved_faces.extend(face for face, kind in zip(chosen, boundary_kinds)
                            if kind == "unknown")
    unresolved = len(unresolved_faces)
    unresolved_limit = _m4_natural_lakes_np.full(count, _m4_natural_lakes_np.inf, _m4_natural_lakes_np.float64)
    for face in unresolved_faces:
        lake = int(flat[face[0]])
        unresolved_limit[lake] = min(unresolved_limit[lake], exterior_crest[face])
    return support, interior, internal_crest, boundary_crest, unresolved, unresolved_limit

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:145 ---
def _domain_arrays(terrain, seeds, owner, boundary_faces, boundary_kinds, max_stage):
    support, interior, internal_crest, boundary_crest, unresolved, unresolved_limit = _domain_expected(
        terrain, seeds, owner, boundary_faces, boundary_kinds, max_stage)
    arrays = dict(source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(),
                  seed_cell_ids=seeds.copy(), owner_grid=owner.copy(), max_stage_m=max_stage.copy(),
                  support_cell_ids=support, internal_faces=interior,
                  internal_crest_m=internal_crest, boundary_faces=boundary_faces.copy(),
                  boundary_kinds=boundary_kinds.astype("U16"), boundary_crest_m=boundary_crest,
                  unresolved_stage_limit_m=unresolved_limit)
    return arrays, unresolved

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:157 ---
def build_natural_lakes(terrain, seed_cell_ids, owner_grid, *, max_stage_m,
                        boundary_faces, boundary_kinds, weir_coefficient_m3_s_m15,
                        source_provenance, boundary_provenance):
    from terrain_pipeline.common_infra import TerrainGrid as _m4_natural_lakes_TerrainGrid
    from terrain_pipeline.common_infra import identity as _m4_natural_lakes_identity
    from terrain_pipeline.common_infra import readonly as _m4_natural_lakes_readonly
    if not isinstance(terrain, _m4_natural_lakes_TerrainGrid):
        raise ValueError("TerrainGrid required")
    if (isinstance(weir_coefficient_m3_s_m15, bool)
            or not isinstance(weir_coefficient_m3_s_m15, (int, float))
            or not _m4_natural_lakes_math.isfinite(weir_coefficient_m3_s_m15)
            or weir_coefficient_m3_s_m15 <= 0.):
        raise ValueError("positive finite explicit reduced-weir coefficient required")
    if not all(isinstance(p, str) and p.strip() for p in (source_provenance, boundary_provenance)):
        raise ValueError("source and boundary provenance required")
    arrays, unresolved = _domain_arrays(terrain, seed_cell_ids, owner_grid,
                                        boundary_faces, boundary_kinds, max_stage_m)
    metadata = dict(schema=DOMAIN_SCHEMA, algorithm=NATURAL_LAKES_ALGORITHM, terrain_metadata=_terrain_metadata(terrain),
                    source_identity_sha256=terrain.identity_sha256,
                    source_provenance=source_provenance, boundary_provenance=boundary_provenance,
                    weir_coefficient_m3_s_m15=float(weir_coefficient_m3_s_m15),
                    unresolved_exterior_faces=unresolved,
                    cell_volume_model="original_native_cell_prisms_strict_bed_below_stage",
                    hydraulic_model="reduced_level_pool_signed_weir_not_saint_venant",
                    transient_connected_not_common_stage=True, natural_boundary_certified=False)
    arrays = {key: _m4_natural_lakes_readonly(value) for key, value in arrays.items()}
    bundle = {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_natural_lakes_identity(arrays, metadata)}
    validate_natural_lakes(bundle)
    return bundle

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:185 ---
def _curves(arrays, area):
    height = arrays["source_height_m"].ravel()
    flat = arrays["owner_grid"].ravel()
    curves = []
    for lake in range(len(arrays["seed_cell_ids"])):
        levels = _m4_natural_lakes_np.sort(height[flat == lake])
        prefix = _m4_natural_lakes_np.r_[0., _m4_natural_lakes_np.cumsum(levels)]
        curves.append((levels, prefix, area))
    return curves

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:196 ---
def _volume_at_stage(curve, stage):
    levels, prefix, area = curve
    count = int(_m4_natural_lakes_np.searchsorted(levels, stage, side="left"))
    return float(area * (count * stage - prefix[count]))

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:202 ---
def _stage_at_volume(curve, volume):
    levels, prefix, area = curve
    if volume <= 0.:
        return float(levels[0] + volume / area)
    break_volume = area * (_m4_natural_lakes_np.arange(len(levels)) * levels - prefix[:-1])
    index = min(int(_m4_natural_lakes_np.searchsorted(break_volume, volume, side="right") - 1), len(levels) - 1)
    return float((volume / area + prefix[index + 1]) / (index + 1))

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:211 ---
def _rates(arrays, coefficient, stage, tailwater):
    owner = arrays["owner_grid"].ravel()
    faces = arrays["internal_faces"]
    boundary = arrays["boundary_faces"]
    internal = _m4_natural_lakes_np.zeros(len(faces), _m4_natural_lakes_np.float64)
    external = _m4_natural_lakes_np.zeros(len(boundary), _m4_natural_lakes_np.float64)
    for edge, (a, b) in enumerate(faces):
        first, second = int(owner[a]), int(owner[b])
        delta = stage[first] - stage[second]
        if delta:
            high = max(stage[first], stage[second])
            low = min(stage[first], stage[second])
            head = max(high - max(float(arrays["internal_crest_m"][edge]), low), 0.)
            internal[edge] = _m4_natural_lakes_math.copysign(coefficient * head ** 1.5, delta)
    for edge, (a, _) in enumerate(boundary):
        kind = arrays["boundary_kinds"][edge]
        lake = int(owner[a])
        crest = float(arrays["boundary_crest_m"][edge])
        if kind == "free_outflow":
            external[edge] = coefficient * max(stage[lake] - crest, 0.) ** 1.5
        elif kind == "tailwater":
            delta = stage[lake] - tailwater[edge]
            if delta:
                high = max(stage[lake], tailwater[edge])
                low = min(stage[lake], tailwater[edge])
                external[edge] = _m4_natural_lakes_math.copysign(coefficient * max(high - max(crest, low), 0.) ** 1.5, delta)
    return internal, external

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:240 ---
def _wet_state(arrays, stage):
    support = arrays["support_cell_ids"]
    owner = arrays["owner_grid"].ravel()[support]
    wet = arrays["source_height_m"].ravel()[support] < stage[owner]
    faces = arrays["internal_faces"]
    face_owner = arrays["owner_grid"].ravel()
    height = arrays["source_height_m"].ravel()
    parent = _m4_natural_lakes_np.arange(len(stage), dtype=_m4_natural_lakes_np.int64)

    def root(node):
        while parent[node] != node:
            node = int(parent[node])
        return node

    for edge, (a, b) in enumerate(faces):
        first, second = int(face_owner[a]), int(face_owner[b])
        if stage[first] > height[a] and stage[second] > height[b]:
            parent[root(second)] = root(first)
    labels = _m4_natural_lakes_np.array([root(lake) for lake in range(len(stage))], _m4_natural_lakes_np.int64)
    return wet, labels

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:262 ---
def _terrain_from_arrays(arrays, meta):
    from terrain_pipeline.common_infra import TerrainGrid as _m4_natural_lakes_TerrainGrid
    return _m4_natural_lakes_TerrainGrid(arrays["source_height_m"], arrays["source_valid_mask"],
                       **meta["terrain_metadata"])

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:267 ---
def _validate_domain(bundle):
    arrays, meta = bundle["arrays"], bundle["metadata"]
    required = {"source_height_m", "source_valid_mask", "seed_cell_ids", "owner_grid",
                "max_stage_m", "support_cell_ids", "internal_faces", "internal_crest_m",
                "boundary_faces", "boundary_kinds", "boundary_crest_m",
                "unresolved_stage_limit_m"}
    keys = {"schema", "algorithm", "terrain_metadata", "source_identity_sha256",
            "source_provenance", "boundary_provenance", "weir_coefficient_m3_s_m15",
            "unresolved_exterior_faces", "cell_volume_model", "hydraulic_model",
            "transient_connected_not_common_stage", "natural_boundary_certified"}
    if (set(arrays) != required or set(meta) != keys or meta["schema"] != DOMAIN_SCHEMA
            or meta["algorithm"] != NATURAL_LAKES_ALGORITHM or meta["cell_volume_model"] != "original_native_cell_prisms_strict_bed_below_stage"
            or meta["hydraulic_model"] != "reduced_level_pool_signed_weir_not_saint_venant"
            or meta["transient_connected_not_common_stage"] is not True
            or meta["natural_boundary_certified"] is not False
            or not all(isinstance(meta[k], str) and meta[k].strip() for k in ("source_provenance", "boundary_provenance"))
            or not _m4_natural_lakes_math.isfinite(meta["weir_coefficient_m3_s_m15"])
            or meta["weir_coefficient_m3_s_m15"] <= 0.):
        raise ValueError("natural lake domain schema or scope mismatch")
    terrain = _terrain_from_arrays(arrays, meta)
    if terrain.identity_sha256 != meta["source_identity_sha256"]:
        raise ValueError("natural lake source identity mismatch")
    expected, unresolved = _domain_arrays(terrain, arrays["seed_cell_ids"], arrays["owner_grid"],
                                          arrays["boundary_faces"], arrays["boundary_kinds"],
                                          arrays["max_stage_m"])
    if unresolved != meta["unresolved_exterior_faces"] or any(not _m4_natural_lakes_np.array_equal(arrays[k], expected[k]) for k in required):
        raise ValueError("natural lake D4 source faces or storage support mismatch")
    return terrain

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:297 ---
def validate_natural_lakes(bundle):
    from terrain_pipeline.common_infra import identity as _m4_natural_lakes_identity
    if (not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}
            or not isinstance(bundle["arrays"], dict) or not isinstance(bundle["metadata"], dict)
            or bundle["identity_sha256"] != _m4_natural_lakes_identity(bundle["arrays"], bundle["metadata"])
            or sum(value.nbytes for value in bundle["arrays"].values()) > NATURAL_LAKES_MAX_BYTES):
        raise ValueError("natural lake bundle identity or byte budget mismatch")
    if bundle["metadata"].get("schema") == DOMAIN_SCHEMA:
        _validate_domain(bundle)
    elif bundle["metadata"].get("schema") == TRACE_SCHEMA:
        _validate_trace(bundle)
    else:
        raise ValueError("unknown natural lake schema")
    return True

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:312 ---
def save_natural_lakes(path, bundle):
    from terrain_pipeline.common_infra import save_bundle as _m4_natural_lakes_save_bundle
    _m4_natural_lakes_save_bundle(path, bundle, validator=validate_natural_lakes)

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:316 ---
def load_natural_lakes(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _m4_natural_lakes_load_bundle
    bundle = _m4_natural_lakes_load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_natural_lakes, max_bytes=NATURAL_LAKES_MAX_BYTES)
    if bundle["identity_sha256"] != expected_identity:
        raise ValueError("external natural lake identity mismatch")
    return bundle

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:324 ---
def lake_volume_at_stage(domain, lake_index, stage_m):
    validate_natural_lakes(domain)
    if domain["metadata"]["schema"] != DOMAIN_SCHEMA:
        raise ValueError("natural lake domain required")
    arrays = domain["arrays"]
    if type(lake_index) is not int or not 0 <= lake_index < len(arrays["seed_cell_ids"]):
        raise ValueError("lake index outside domain")
    if not isinstance(stage_m, (int, float)) or not _m4_natural_lakes_math.isfinite(stage_m):
        raise ValueError("finite stage required")
    terrain = _terrain_from_arrays(arrays, domain["metadata"])
    curve = _curves(arrays, terrain.cell_area_m2)[lake_index]
    if not curve[0][0] <= stage_m <= arrays["max_stage_m"][lake_index]:
        raise ValueError("stage outside declared support")
    return _volume_at_stage(curve, stage_m)

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:340 ---
def lake_stage_at_volume(domain, lake_index, volume_m3):
    validate_natural_lakes(domain)
    if domain["metadata"]["schema"] != DOMAIN_SCHEMA:
        raise ValueError("natural lake domain required")
    arrays = domain["arrays"]
    if type(lake_index) is not int or not 0 <= lake_index < len(arrays["seed_cell_ids"]):
        raise ValueError("lake index outside domain")
    if not isinstance(volume_m3, (int, float)) or not _m4_natural_lakes_math.isfinite(volume_m3):
        raise ValueError("finite volume required")
    terrain = _terrain_from_arrays(arrays, domain["metadata"])
    curve = _curves(arrays, terrain.cell_area_m2)[lake_index]
    capacity = _volume_at_stage(curve, arrays["max_stage_m"][lake_index])
    if not 0. <= volume_m3 <= capacity:
        raise ValueError("volume outside finite source support")
    return _stage_at_volume(curve, volume_m3)

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:357 ---
def solve_natural_lakes(domain, time_seconds, local_q_m3_s, initial_volume_m3,
                        tailwater_stage_m, *, config=None, forcing_provenance):
    """Integrate piecewise-constant forcing; retain verified accepted-step prefix on failure."""
    from terrain_pipeline.common_infra import identity as _m4_natural_lakes_identity
    from terrain_pipeline.common_infra import readonly as _m4_natural_lakes_readonly
    validate_natural_lakes(domain)
    if domain["metadata"]["schema"] != DOMAIN_SCHEMA:
        raise ValueError("natural lake domain bundle required")
    if config is None:
        config = NaturalLakeConfig()
    if not isinstance(config, NaturalLakeConfig):
        raise ValueError("NaturalLakeConfig required")
    if not isinstance(forcing_provenance, str) or not forcing_provenance.strip():
        raise ValueError("forcing provenance required")
    a = domain["arrays"]
    lakes = len(a["seed_cell_ids"])
    edges = len(a["internal_faces"])
    boundaries = len(a["boundary_faces"])
    times = _m4_natural_lakes_np.asarray(time_seconds)
    local = _m4_natural_lakes_np.asarray(local_q_m3_s)
    initial = _m4_natural_lakes_np.asarray(initial_volume_m3)
    tailwater = _m4_natural_lakes_np.asarray(tailwater_stage_m)
    if (times.dtype != _m4_natural_lakes_np.float64 or times.ndim != 1 or not 2 <= len(times) <= 100001
            or not _m4_natural_lakes_np.isfinite(times).all() or times[0] < 0. or _m4_natural_lakes_np.any(_m4_natural_lakes_np.diff(times) <= 0.)
            or local.dtype != _m4_natural_lakes_np.float64 or local.shape != (len(times) - 1, lakes)
            or not _m4_natural_lakes_np.isfinite(local).all() or _m4_natural_lakes_np.any(local < 0.)
            or initial.dtype != _m4_natural_lakes_np.float64 or initial.shape != (lakes,) or not _m4_natural_lakes_np.isfinite(initial).all()
            or tailwater.dtype != _m4_natural_lakes_np.float64 or tailwater.shape != (len(times) - 1, boundaries)
            or not _m4_natural_lakes_np.isfinite(tailwater).all()):
        raise ValueError("finite forcing intervals, nonnegative local supply and initial stock required")
    if (times.nbytes + local.nbytes + initial.nbytes + tailwater.nbytes > NATURAL_LAKES_MAX_BYTES // 2):
        raise ValueError("forcing byte budget exceeded")
    terrain = _terrain_from_arrays(a, domain["metadata"])
    curves = _curves(a, terrain.cell_area_m2)
    capacity = _m4_natural_lakes_np.array([_volume_at_stage(curve, upper)
                         for curve, upper in zip(curves, a["max_stage_m"])])
    if _m4_natural_lakes_np.any(initial < 0.) or _m4_natural_lakes_np.any(initial > capacity):
        raise ValueError("initial lake stock outside finite source support")
    initial_stage = _m4_natural_lakes_np.array([_stage_at_volume(curve, volume)
                              for curve, volume in zip(curves, initial)])
    if _m4_natural_lakes_np.any(initial_stage > a["unresolved_stage_limit_m"]):
        raise ValueError("initial stock overtops unresolved exterior face")
    coefficient = domain["metadata"]["weir_coefficient_m3_s_m15"]
    owner = a["owner_grid"].ravel()
    edge_from = owner[a["internal_faces"][:, 0]]
    edge_to = owner[a["internal_faces"][:, 1]]
    boundary_from = owner[a["boundary_faces"][:, 0]]
    state = _m4_natural_lakes_np.r_[initial, _m4_natural_lakes_np.zeros(edges + boundaries)]
    trace_times = [float(times[0])]
    states = [state.copy()]
    intervals = [0]
    failure = None
    failure_time = None

    def derivative(_, values, interval):
        stage = _m4_natural_lakes_np.array([_stage_at_volume(curve, volume)
                          for curve, volume in zip(curves, values[:lakes])])
        internal_q, boundary_q = _rates(a, coefficient, stage, tailwater[interval])
        change = local[interval].copy()
        _m4_natural_lakes_np.add.at(change, edge_from, -internal_q)
        _m4_natural_lakes_np.add.at(change, edge_to, internal_q)
        _m4_natural_lakes_np.add.at(change, boundary_from, -boundary_q)
        return _m4_natural_lakes_np.r_[change, internal_q, boundary_q]

    events = []
    event_reasons = []
    for lake in range(lakes):
        def capacity_event(_, values, lake=lake):
            return capacity[lake] - values[lake]
        capacity_event.direction = -1
        capacity_event.terminal = True
        events.append(capacity_event)
        event_reasons.append("finite source support capacity reached")
        if _m4_natural_lakes_math.isfinite(a["unresolved_stage_limit_m"][lake]):
            def unresolved_event(_, values, lake=lake):
                stage = _stage_at_volume(curves[lake], values[lake])
                return a["unresolved_stage_limit_m"][lake] - stage
            unresolved_event.direction = -1
            unresolved_event.terminal = True
            events.append(unresolved_event)
            event_reasons.append("unresolved exterior face crest reached")

    for interval in range(len(times) - 1):
        if failure:
            break
        remaining = config.max_steps - (len(trace_times) - 1)
        if remaining <= 0:
            failure, failure_time = "maximum accepted step count exceeded", trace_times[-1]
            break
        try:
            result = _m4_natural_lakes_solve_ivp(lambda t, y: derivative(t, y, interval),
                               (float(times[interval]), float(times[interval + 1])), state,
                               method="DOP853", rtol=config.relative_tolerance,
                               atol=config.absolute_tolerance_m3,
                               max_step=config.max_step_seconds, events=events)
        except (ValueError, OverflowError, FloatingPointError) as error:
            failure, failure_time = "ODE evaluation failed: " + str(error), trace_times[-1]
            break
        if result.status == 1:
            event_index = next(index for index, hits in enumerate(result.t_events) if len(hits))
            failure, failure_time = event_reasons[event_index], float(result.t_events[event_index][0])
        elif not result.success:
            failure, failure_time = "ODE integration failed: " + result.message, float(result.t[-1])
        for t, value in zip(result.t[1:], result.y.T[1:]):
            if t <= trace_times[-1]:
                continue
            if len(trace_times) - 1 >= config.max_steps:
                failure, failure_time = "maximum accepted step count exceeded", float(t)
                break
            if not _m4_natural_lakes_np.isfinite(value).all() or _m4_natural_lakes_np.any(value[:lakes] < 0.) or _m4_natural_lakes_np.any(value[:lakes] > capacity):
                failure, failure_time = "finite stock boundary crossed", float(t)
                break
            if (len(trace_times) + 1) * (4 * lakes + 3 * edges + 3 * boundaries + len(a["support_cell_ids"])) > MAX_TRACE_ENTRIES:
                failure, failure_time = "trace entry budget exceeded", float(t)
                break
            trace_times.append(float(t))
            states.append(value.copy())
            intervals.append(interval)
        state = states[-1]
        if not failure and not _m4_natural_lakes_math.isclose(trace_times[-1], times[interval + 1], rel_tol=0., abs_tol=1e-9):
            failure, failure_time = "incomplete forcing interval", float(result.t[-1])
    state_array = _m4_natural_lakes_np.asarray(states)
    volume = state_array[:, :lakes]
    stage = _m4_natural_lakes_np.array([[_stage_at_volume(curve, v) for curve, v in zip(curves, row)]
                      for row in volume])
    wet_states = [_wet_state(a, row) for row in stage]
    internal_q = []
    boundary_q = []
    for row, interval in zip(stage, intervals):
        q, bq = _rates(a, coefficient, row, tailwater[interval])
        internal_q.append(q)
        boundary_q.append(bq)
    arrays = dict(time_seconds=_m4_natural_lakes_np.asarray(trace_times, _m4_natural_lakes_np.float64),
                  interval_index=_m4_natural_lakes_np.asarray(intervals, _m4_natural_lakes_np.int64),
                  volume_m3=volume.copy(), stage_m=stage,
                  internal_transfer_m3=state_array[:, lakes:lakes + edges].copy(),
                  boundary_transfer_m3=state_array[:, lakes + edges:].copy(),
                  internal_q_m3_s=(_m4_natural_lakes_np.asarray(internal_q, _m4_natural_lakes_np.float64).reshape(len(trace_times), edges)
                                   if edges else _m4_natural_lakes_np.empty((len(trace_times), 0), _m4_natural_lakes_np.float64)),
                  boundary_q_m3_s=(_m4_natural_lakes_np.asarray(boundary_q, _m4_natural_lakes_np.float64).reshape(len(trace_times), boundaries)
                                   if boundaries else _m4_natural_lakes_np.empty((len(trace_times), 0), _m4_natural_lakes_np.float64)),
                  wet_support=_m4_natural_lakes_np.asarray([item[0] for item in wet_states], bool),
                  wet_component=_m4_natural_lakes_np.asarray([item[1] for item in wet_states], _m4_natural_lakes_np.int64),
                  forcing_time_seconds=times.copy(), local_q_m3_s=local.copy(),
                  initial_volume_m3=initial.copy(), tailwater_stage_m=tailwater.copy())
    arrays.update({"domain_" + key: value.copy() for key, value in a.items()})
    metadata = dict(schema=TRACE_SCHEMA, algorithm=NATURAL_LAKES_ALGORITHM, domain_identity_sha256=domain["identity_sha256"],
                    domain_metadata=domain["metadata"], config=_m4_natural_lakes_asdict(config),
                    forcing_provenance=forcing_provenance,
                    status="failed_prefix" if failure else "complete",
                    failure_reason=failure, failure_time_seconds=failure_time,
                    hydraulic_model="reduced_level_pool_signed_weir_not_saint_venant",
                    common_stage_certified=False)
    arrays = {key: _m4_natural_lakes_readonly(value) for key, value in arrays.items()}
    bundle = {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_natural_lakes_identity(arrays, metadata)}
    validate_natural_lakes(bundle)
    return bundle

# --- terrain_pipeline/surface_rivers/metric_natural_lakes.py:514 ---
def _validate_trace(bundle):
    from terrain_pipeline.common_infra import identity as _m4_natural_lakes_identity
    arrays, meta = bundle["arrays"], bundle["metadata"]
    base = {"time_seconds", "interval_index", "volume_m3", "stage_m",
            "internal_transfer_m3", "boundary_transfer_m3", "internal_q_m3_s",
            "boundary_q_m3_s", "wet_support", "wet_component", "forcing_time_seconds",
            "local_q_m3_s", "initial_volume_m3", "tailwater_stage_m"}
    domain_keys = {key for key in arrays if key.startswith("domain_")}
    required_meta = {"schema", "algorithm", "domain_identity_sha256", "domain_metadata",
                     "config", "forcing_provenance", "status", "failure_reason",
                     "failure_time_seconds", "hydraulic_model", "common_stage_certified"}
    if (set(arrays) != base | domain_keys or set(meta) != required_meta
            or meta["schema"] != TRACE_SCHEMA or meta["algorithm"] != NATURAL_LAKES_ALGORITHM
            or meta["hydraulic_model"] != "reduced_level_pool_signed_weir_not_saint_venant"
            or meta["common_stage_certified"] is not False
            or not isinstance(meta["forcing_provenance"], str) or not meta["forcing_provenance"].strip()):
        raise ValueError("natural lake trace schema mismatch")
    domain_arrays = {key.removeprefix("domain_"): arrays[key] for key in domain_keys}
    domain = {"arrays": domain_arrays, "metadata": meta["domain_metadata"],
              "identity_sha256": meta["domain_identity_sha256"]}
    if _m4_natural_lakes_identity(domain_arrays, domain["metadata"]) != domain["identity_sha256"]:
        raise ValueError("natural lake embedded domain identity mismatch")
    terrain = _validate_domain(domain)
    NaturalLakeConfig(**meta["config"])
    a = domain_arrays
    n = len(a["seed_cell_ids"])
    e = len(a["internal_faces"])
    b = len(a["boundary_faces"])
    t = arrays["time_seconds"]
    intervals = arrays["interval_index"]
    forcing_time = arrays["forcing_time_seconds"]
    local = arrays["local_q_m3_s"]
    tailwater = arrays["tailwater_stage_m"]
    initial = arrays["initial_volume_m3"]
    steps = len(t)
    fields = (("volume_m3", (steps, n), _m4_natural_lakes_np.float64),
              ("stage_m", (steps, n), _m4_natural_lakes_np.float64),
              ("internal_transfer_m3", (steps, e), _m4_natural_lakes_np.float64),
              ("boundary_transfer_m3", (steps, b), _m4_natural_lakes_np.float64),
              ("internal_q_m3_s", (steps, e), _m4_natural_lakes_np.float64),
              ("boundary_q_m3_s", (steps, b), _m4_natural_lakes_np.float64),
              ("wet_support", (steps, len(a["support_cell_ids"])), bool),
              ("wet_component", (steps, n), _m4_natural_lakes_np.int64))
    if (t.dtype != _m4_natural_lakes_np.float64 or t.ndim != 1 or not 1 <= steps <= 100001
            or not _m4_natural_lakes_np.isfinite(t).all() or _m4_natural_lakes_np.any(_m4_natural_lakes_np.diff(t) <= 0.)
            or intervals.dtype != _m4_natural_lakes_np.int64 or intervals.shape != (steps,)
            or forcing_time.dtype != _m4_natural_lakes_np.float64 or forcing_time.ndim != 1
            or not 2 <= len(forcing_time) <= 100001 or not _m4_natural_lakes_np.isfinite(forcing_time).all()
            or _m4_natural_lakes_np.any(_m4_natural_lakes_np.diff(forcing_time) <= 0.) or t[0] != forcing_time[0]
            or local.dtype != _m4_natural_lakes_np.float64 or local.shape != (len(forcing_time) - 1, n)
            or not _m4_natural_lakes_np.isfinite(local).all() or _m4_natural_lakes_np.any(local < 0.)
            or tailwater.dtype != _m4_natural_lakes_np.float64 or tailwater.shape != (len(forcing_time) - 1, b)
            or not _m4_natural_lakes_np.isfinite(tailwater).all() or initial.dtype != _m4_natural_lakes_np.float64
            or initial.shape != (n,) or not _m4_natural_lakes_np.isfinite(initial).all()
            or any(arrays[name].dtype != dtype or arrays[name].shape != shape
                   for name, shape, dtype in fields)
            or any(not _m4_natural_lakes_np.isfinite(arrays[name]).all() for name, _, dtype in fields if dtype == _m4_natural_lakes_np.float64)):
        raise ValueError("natural lake trace shape/time/finite mismatch")
    if _m4_natural_lakes_np.any(intervals < 0) or _m4_natural_lakes_np.any(intervals >= len(forcing_time) - 1):
        raise ValueError("trace forcing interval outside range")
    for k, instant in enumerate(t):
        expected_interval = min(int(_m4_natural_lakes_np.searchsorted(forcing_time, instant, side="right") - 1), len(forcing_time) - 2)
        if intervals[k] != expected_interval and not (k and instant == forcing_time[intervals[k] + 1]):
            raise ValueError("trace forcing interval mismatch")
    for name in ("internal_transfer_m3", "boundary_transfer_m3"):
        if _m4_natural_lakes_np.any(arrays[name][0] != 0.):
            raise ValueError("nonzero initial paired transfer")
    if not _m4_natural_lakes_np.array_equal(arrays["volume_m3"][0], initial):
        raise ValueError("initial source stock mismatch")
    curves = _curves(a, terrain.cell_area_m2)
    capacity = _m4_natural_lakes_np.array([_volume_at_stage(curve, upper) for curve, upper in zip(curves, a["max_stage_m"])])
    volumes = arrays["volume_m3"]
    if _m4_natural_lakes_np.any(volumes < 0.) or _m4_natural_lakes_np.any(volumes > capacity):
        raise ValueError("trace finite stock outside source support")
    if _m4_natural_lakes_np.any(arrays["stage_m"] > a["unresolved_stage_limit_m"][None, :] + 1e-9):
        raise ValueError("trace crosses unresolved exterior face crest")
    owner = a["owner_grid"].ravel()
    edge_from = owner[a["internal_faces"][:, 0]]
    edge_to = owner[a["internal_faces"][:, 1]]
    boundary_from = owner[a["boundary_faces"][:, 0]]
    coefficient = domain["metadata"]["weir_coefficient_m3_s_m15"]
    for step in range(steps):
        stage = _m4_natural_lakes_np.array([_stage_at_volume(curve, v) for curve, v in zip(curves, volumes[step])])
        if not _m4_natural_lakes_np.allclose(arrays["stage_m"][step], stage, rtol=0., atol=1e-8):
            raise ValueError("source storage stage mismatch")
        wet, component = _wet_state(a, stage)
        if (not _m4_natural_lakes_np.array_equal(arrays["wet_support"][step], wet)
                or not _m4_natural_lakes_np.array_equal(arrays["wet_component"][step], component)):
            raise ValueError("original-bed wet footprint or merge state mismatch")
        q, bq = _rates(a, coefficient, stage, tailwater[intervals[step]])
        if (not _m4_natural_lakes_np.allclose(arrays["internal_q_m3_s"][step], q, rtol=1e-9, atol=1e-9)
                or not _m4_natural_lakes_np.allclose(arrays["boundary_q_m3_s"][step], bq, rtol=1e-9, atol=1e-9)):
            raise ValueError("weir law endpoint flux mismatch")
        if step:
            dt = t[step] - t[step - 1]
            previous_interval = intervals[step]
            if t[step] == forcing_time[previous_interval + 1]:
                pass
            elif (intervals[step - 1] != previous_interval
                  and t[step - 1] != forcing_time[previous_interval]):
                raise ValueError("accepted step crosses forcing change")
            budget = volumes[step - 1] + local[previous_interval] * dt
            transfer = arrays["internal_transfer_m3"][step] - arrays["internal_transfer_m3"][step - 1]
            external = arrays["boundary_transfer_m3"][step] - arrays["boundary_transfer_m3"][step - 1]
            _m4_natural_lakes_np.add.at(budget, edge_from, -transfer)
            _m4_natural_lakes_np.add.at(budget, edge_to, transfer)
            _m4_natural_lakes_np.add.at(budget, boundary_from, -external)
            if not _m4_natural_lakes_np.allclose(volumes[step], budget, rtol=1e-9, atol=1e-7):
                raise ValueError("paired lake volume ledger mismatch")
    if meta["status"] == "complete":
        if meta["failure_reason"] is not None or meta["failure_time_seconds"] is not None or abs(t[-1] - forcing_time[-1]) > 1e-9:
            raise ValueError("incomplete lake trace marked complete")
    elif meta["status"] == "failed_prefix":
        if (not isinstance(meta["failure_reason"], str) or not meta["failure_reason"]
                or not isinstance(meta["failure_time_seconds"], (int, float))
                or not _m4_natural_lakes_math.isfinite(meta["failure_time_seconds"])
                or meta["failure_time_seconds"] < t[-1] - 1e-9):
            raise ValueError("invalid actual failure prefix witness")
    else:
        raise ValueError("unknown natural lake trace status")

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:19 ---
EQUILIBRIUM_SCHEMA = "terragenesis-equilibrium-lake-support-v1"

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:20 ---
EQUILIBRIUM_ALGORITHM = "original-d4-saddle-instant-equilibrium-projection-v1"

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:21 ---
EQUILIBRIUM_MAX_BYTES = 128 * 1024 * 1024

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:22 ---
DOMAIN_FIELDS = ("source_height_m", "source_valid_mask", "seed_cell_ids", "owner_grid",
                 "max_stage_m", "support_cell_ids", "internal_faces", "internal_crest_m",
                 "boundary_faces", "boundary_kinds", "boundary_crest_m", "unresolved_stage_limit_m")

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:28 ---
@_m4_equilibrium_lake_support_dataclass(frozen=True)
class EquilibriumLakeState:
    owner_volume_m3: _m4_equilibrium_lake_support_np.ndarray
    component_id: _m4_equilibrium_lake_support_np.ndarray

    def __post_init__(self):
        volume, component = self.owner_volume_m3, self.component_id
        if (not isinstance(volume, _m4_equilibrium_lake_support_np.ndarray) or volume.dtype != _m4_equilibrium_lake_support_np.float64 or volume.ndim != 1
                or not _m4_equilibrium_lake_support_np.isfinite(volume).all() or _m4_equilibrium_lake_support_np.any(volume < 0.)
                or not isinstance(component, _m4_equilibrium_lake_support_np.ndarray) or component.dtype != _m4_equilibrium_lake_support_np.int64
                or component.shape != volume.shape or _m4_equilibrium_lake_support_np.any(component < 0.)):
            raise ValueError("finite owner inventory and int64 component labels required")
        object.__setattr__(self, "owner_volume_m3", _m4_equilibrium_lake_support_readonly(volume))
        object.__setattr__(self, "component_id", _m4_equilibrium_lake_support_readonly(component))

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:44 ---
@_m4_equilibrium_lake_support_dataclass(frozen=True)
class EquilibriumLakeForcing:
    time_seconds: _m4_equilibrium_lake_support_np.ndarray
    local_q_m3_s: _m4_equilibrium_lake_support_np.ndarray
    tailwater_stage_m: _m4_equilibrium_lake_support_np.ndarray
    port_q_m3_s: _m4_equilibrium_lake_support_np.ndarray
    source_identity_sha256: str
    provenance: str
    port_source_identity_sha256: str
    port_provenance: str

    def __post_init__(self):
        t = self.time_seconds
        if (not isinstance(t, _m4_equilibrium_lake_support_np.ndarray) or t.dtype != _m4_equilibrium_lake_support_np.float64 or t.ndim != 1
                or not 2 <= len(t) <= 100001 or not _m4_equilibrium_lake_support_np.isfinite(t).all()
                or t[0] < 0. or _m4_equilibrium_lake_support_np.any(_m4_equilibrium_lake_support_np.diff(t) <= 0.)):
            raise ValueError("finite increasing forcing times required")
        for name in ("local_q_m3_s", "tailwater_stage_m", "port_q_m3_s"):
            value = getattr(self, name)
            if (not isinstance(value, _m4_equilibrium_lake_support_np.ndarray) or value.dtype != _m4_equilibrium_lake_support_np.float64 or value.ndim != 2
                    or value.shape[0] != len(t) - 1 or not _m4_equilibrium_lake_support_np.isfinite(value).all()
                    or name == "local_q_m3_s" and _m4_equilibrium_lake_support_np.any(value < 0.)):
                raise ValueError("finite interval forcing invalid: " + name)
            object.__setattr__(self, name, _m4_equilibrium_lake_support_readonly(value))
        if (not isinstance(self.source_identity_sha256, str) or len(self.source_identity_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.source_identity_sha256)
                or not isinstance(self.port_source_identity_sha256, str) or len(self.port_source_identity_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.port_source_identity_sha256)
                or not isinstance(self.provenance, str) or not self.provenance.strip()
                or not isinstance(self.port_provenance, str) or not self.port_provenance.strip()):
            raise ValueError("forcing source identity and provenance required")
        object.__setattr__(self, "time_seconds", _m4_equilibrium_lake_support_readonly(t))

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:78 ---
@_m4_equilibrium_lake_support_dataclass(frozen=True)
class EquilibriumLakeConfig:
    max_dt_seconds: float = .5
    min_dt_seconds: float = 1e-8
    cfl: float = .5
    max_steps: int = 20000

    def __post_init__(self):
        for name in ("max_dt_seconds", "min_dt_seconds", "cfl"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not _m4_equilibrium_lake_support_math.isfinite(value) or value <= 0.:
                raise ValueError("finite positive lake step control required")
            object.__setattr__(self, name, float(value))
        if self.min_dt_seconds > self.max_dt_seconds or self.cfl > 1. or type(self.max_steps) is not int or not 1 <= self.max_steps <= 100000:
            raise ValueError("bounded lake step control required")

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:94 ---
def equilibrium_geometry(domain, volumes):
    arrays = domain["arrays"]
    terrain = domain["metadata"]["terrain_metadata"]
    area = terrain["dx_m"] * terrain["dz_m"]
    curves = _curves(arrays, area)
    stage = _m4_equilibrium_lake_support_np.array([_stage_at_volume(curve, volume) for curve, volume in zip(curves, volumes)])
    return curves, stage

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:103 ---
def _wet(domain, stage):
    return _wet_state(domain["arrays"], stage)

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:107 ---
def _labels(count, edges):
    parent = _m4_equilibrium_lake_support_np.arange(count, dtype=_m4_equilibrium_lake_support_np.int64)
    def root(index):
        while parent[index] != index:
            index = int(parent[index])
        return index
    for first, second in edges:
        a, b = root(first), root(second)
        parent[max(a, b)] = min(a, b)
    roots = [root(index) for index in range(count)]
    unique = {value: index for index, value in enumerate(sorted(set(roots)))}
    return _m4_equilibrium_lake_support_np.array([unique[value] for value in roots], _m4_equilibrium_lake_support_np.int64)

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:121 ---
def _combined_stage(curves, members, total):
    low = min(curves[i][0][0] for i in members)
    high = max(_stage_at_volume(curves[i], total) for i in members)
    for _ in range(64):
        middle = (low + high) / 2.
        if sum(_volume_at_stage(curves[i], middle) for i in members) < total:
            low = middle
        else:
            high = middle
    return (low + high) / 2.

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:133 ---
def _paired_redistribution(domain, labels, delta, bridge_stage):
    arrays = domain["arrays"]
    owner = arrays["owner_grid"].ravel()
    n = len(labels)
    adjacency = [[] for _ in range(n)]
    for edge, (a, b) in enumerate(arrays["internal_faces"]):
        first, second = int(owner[a]), int(owner[b])
        crest = arrays["internal_crest_m"][edge]
        if (labels[first] == labels[second] and
                bridge_stage[first] >= crest - 1e-12 and bridge_stage[second] >= crest - 1e-12):
            adjacency[first].append((second, edge, 1.))
            adjacency[second].append((first, edge, -1.))
    paired = _m4_equilibrium_lake_support_np.zeros(len(arrays["internal_faces"]), _m4_equilibrium_lake_support_np.float64)
    visited = _m4_equilibrium_lake_support_np.zeros(n, bool)
    for start in range(n):
        if visited[start]:
            continue
        visited[start] = True
        parent = {start: None}
        order = [start]
        for node in order:
            for neighbor, edge, sign in adjacency[node]:
                if not visited[neighbor]:
                    visited[neighbor] = True
                    parent[neighbor] = (node, edge, sign)
                    order.append(neighbor)
        remainder = delta.copy()
        for node in reversed(order[1:]):
            parent_node, edge, sign = parent[node]
            paired[edge] = sign * remainder[node]
            remainder[parent_node] += remainder[node]
        if abs(remainder[start]) > 1e-8:
            raise ValueError("unpaired component projection inventory")
    return paired

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:169 ---
def project_equilibrium_lakes(domain, owner_volume_m3, previous_component=None, *, _validated=False):
    """Return projected state and signed per-owner redistribution in m3."""
    if not _validated:
        validate_natural_lakes(domain)
    arrays = domain["arrays"]
    n = len(arrays["seed_cell_ids"])
    volume = _m4_equilibrium_lake_support_np.asarray(owner_volume_m3)
    if volume.dtype != _m4_equilibrium_lake_support_np.float64 or volume.shape != (n,) or not _m4_equilibrium_lake_support_np.isfinite(volume).all() or _m4_equilibrium_lake_support_np.any(volume < 0.):
        raise ValueError("finite nonnegative native owner volumes required")
    previous = _m4_equilibrium_lake_support_np.arange(n, dtype=_m4_equilibrium_lake_support_np.int64) if previous_component is None else _m4_equilibrium_lake_support_np.asarray(previous_component)
    if previous.dtype != _m4_equilibrium_lake_support_np.int64 or previous.shape != (n,) or _m4_equilibrium_lake_support_np.any(previous < 0.):
        raise ValueError("previous component labels invalid")
    curves, individual = equilibrium_geometry(domain, volume)
    owner = arrays["owner_grid"].ravel()
    faces = [(int(owner[a]), int(owner[b]), float(crest))
             for (a, b), crest in zip(arrays["internal_faces"], arrays["internal_crest_m"])]
    labels = previous.copy()
    # Prior components use aggregate head while deciding whether their saddle
    # remains wet; separate components use each side's own stage.
    group_stage = {}
    for label in _m4_equilibrium_lake_support_np.unique(labels):
        members = _m4_equilibrium_lake_support_np.flatnonzero(labels == label)
        group_stage[int(label)] = _combined_stage(curves, members, float(volume[members].sum()))
    active = []
    for first, second, crest in faces:
        if group_stage[int(labels[first])] >= crest - 1e-12 and group_stage[int(labels[second])] >= crest - 1e-12:
            active.append((first, second))
    labels = _labels(n, active)
    for _ in range(n):
        stage = _m4_equilibrium_lake_support_np.array([_combined_stage(curves, _m4_equilibrium_lake_support_np.flatnonzero(labels == label),
                          float(volume[labels == label].sum())) for label in range(labels.max() + 1)])
        new_edges = [(first, second) for first, second, crest in faces
                     if stage[labels[first]] >= crest - 1e-12 and stage[labels[second]] >= crest - 1e-12]
        updated = _labels(n, new_edges)
        if _m4_equilibrium_lake_support_np.array_equal(updated, labels):
            break
        labels = updated
    else:
        raise ValueError("lake component projection did not settle")
    result = volume.copy()
    for label in _m4_equilibrium_lake_support_np.unique(labels):
        members = _m4_equilibrium_lake_support_np.flatnonzero(labels == label)
        if len(members) > 1:
            level = _combined_stage(curves, members, float(volume[members].sum()))
            result[members] = [_volume_at_stage(curves[i], level) for i in members]
            result[members[-1]] += float(volume[members].sum() - result[members].sum())
    if _m4_equilibrium_lake_support_np.any(result < -1e-10):
        raise ValueError("negative equilibrium projection inventory")
    result = _m4_equilibrium_lake_support_np.maximum(result, 0.)
    return EquilibriumLakeState(result, labels), result - volume

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:221 ---
def _checked(domain, state, forcing=None):
    n = len(domain["arrays"]["seed_cell_ids"])
    if not isinstance(state, EquilibriumLakeState) or state.owner_volume_m3.shape != (n,):
        raise ValueError("bounded equilibrium state required")
    projected, redistribution = project_equilibrium_lakes(domain, state.owner_volume_m3,
                                                          state.component_id, _validated=True)
    if not _m4_equilibrium_lake_support_np.array_equal(projected.component_id, state.component_id) or not _m4_equilibrium_lake_support_np.allclose(redistribution, 0., rtol=0., atol=1e-9):
        raise ValueError("state is not at component equilibrium")
    curves, stage = equilibrium_geometry(domain, state.owner_volume_m3)
    arrays = domain["arrays"]
    if _m4_equilibrium_lake_support_np.any(state.owner_volume_m3 > _m4_equilibrium_lake_support_np.array([_volume_at_stage(c, h) for c, h in zip(curves, arrays["max_stage_m"])]) + 1e-10):
        raise ValueError("finite natural lake support exceeded")
    if _m4_equilibrium_lake_support_np.any(stage > arrays["unresolved_stage_limit_m"] + 1e-10):
        raise ValueError("unknown exterior face crest reached")
    if forcing is not None:
        if (not isinstance(forcing, EquilibriumLakeForcing)
                or forcing.source_identity_sha256 != domain["metadata"]["source_identity_sha256"]
                or forcing.local_q_m3_s.shape[1] != n or forcing.port_q_m3_s.shape[1] != n
                or forcing.tailwater_stage_m.shape[1] != len(arrays["boundary_faces"])):
            raise ValueError("equilibrium forcing/source dimensions mismatch")
    return stage

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:244 ---
def equilibrium_trace_bytes(domain, forcing, steps):
    arrays = domain["arrays"]
    n = len(arrays["seed_cell_ids"])
    faces = len(arrays["internal_faces"])
    boundary = len(arrays["boundary_faces"])
    support = len(arrays["support_cell_ids"])
    static = sum(value.nbytes for value in arrays.values())
    static += sum(getattr(forcing, key).nbytes for key in
                  ("time_seconds", "local_q_m3_s", "tailwater_stage_m", "port_q_m3_s"))
    static += 8 * (2 * n + faces)
    state = 8 * (3 * n) + support + 8 * n
    step = 8 * (faces + boundary + 2 * n + faces + 1)
    return static + state + 8 + steps * (state + step + 16)

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:259 ---
def advance_equilibrium_lakes(domain, state, dt_seconds, local_q_m3_s, tailwater_stage_m,
                              port_q_m3_s, *, cfl=1., _validated=False):
    """Advance one explicit interval; port rates are externally paired channel fluxes."""
    if not _validated:
        validate_natural_lakes(domain)
    stage = _checked(domain, state)
    arrays = domain["arrays"]
    n, nb = len(stage), len(arrays["boundary_faces"])
    local = _m4_equilibrium_lake_support_np.asarray(local_q_m3_s, _m4_equilibrium_lake_support_np.float64)
    tail = _m4_equilibrium_lake_support_np.asarray(tailwater_stage_m, _m4_equilibrium_lake_support_np.float64)
    port = _m4_equilibrium_lake_support_np.asarray(port_q_m3_s, _m4_equilibrium_lake_support_np.float64)
    if (not _m4_equilibrium_lake_support_math.isfinite(dt_seconds) or dt_seconds <= 0. or not 0. < cfl <= 1.
            or local.shape != (n,) or tail.shape != (nb,) or port.shape != (n,)
            or not _m4_equilibrium_lake_support_np.isfinite(local).all() or not _m4_equilibrium_lake_support_np.isfinite(tail).all()
            or not _m4_equilibrium_lake_support_np.isfinite(port).all() or _m4_equilibrium_lake_support_np.any(local < 0.)):
        raise ValueError("finite bounded step forcing required")
    owner = arrays["owner_grid"].ravel()
    coefficient = domain["metadata"]["weir_coefficient_m3_s_m15"]
    internal = _m4_equilibrium_lake_support_np.zeros(len(arrays["internal_faces"]))
    boundary = _m4_equilibrium_lake_support_np.zeros(nb)
    rate = local + port
    outgoing = _m4_equilibrium_lake_support_np.maximum(-port, 0.)
    for index, (a, b) in enumerate(arrays["internal_faces"]):
        first, second = int(owner[a]), int(owner[b])
        if state.component_id[first] == state.component_id[second]:
            continue
        difference = stage[first] - stage[second]
        if difference:
            high, low = max(stage[first], stage[second]), min(stage[first], stage[second])
            q = _m4_equilibrium_lake_support_math.copysign(coefficient * max(high - max(arrays["internal_crest_m"][index], low), 0.) ** 1.5, difference)
            internal[index] = q
            rate[first] -= q
            rate[second] += q
            outgoing[first] += max(q, 0.)
            outgoing[second] += max(-q, 0.)
    for index, (cell, _) in enumerate(arrays["boundary_faces"]):
        lake = int(owner[cell])
        kind, crest = arrays["boundary_kinds"][index], arrays["boundary_crest_m"][index]
        if kind == "free_outflow":
            q = coefficient * max(stage[lake] - crest, 0.) ** 1.5
        elif kind == "tailwater":
            difference = stage[lake] - tail[index]
            high, low = max(stage[lake], tail[index]), min(stage[lake], tail[index])
            q = _m4_equilibrium_lake_support_math.copysign(coefficient * max(high - max(crest, low), 0.) ** 1.5, difference) if difference else 0.
        else:
            q = 0.
        boundary[index] = q
        rate[lake] -= q
        outgoing[lake] += max(q, 0.)
    volume = state.owner_volume_m3
    curves, _ = equilibrium_geometry(domain, volume)
    for (a, b), crest in zip(arrays["internal_faces"], arrays["internal_crest_m"]):
        first, second = int(owner[a]), int(owner[b])
        if state.component_id[first] != state.component_id[second]:
            continue
        members = _m4_equilibrium_lake_support_np.flatnonzero(state.component_id == state.component_id[first])
        threshold = sum(_volume_at_stage(curves[i], crest) for i in members)
        start_total = float(volume[members].sum())
        next_total = start_total + dt_seconds * float(rate[members].sum())
        if start_total > threshold + 1e-9 and next_total < threshold - 1e-9:
            raise ValueError("step crosses equilibrium saddle event")
    ratio = _m4_equilibrium_lake_support_np.divide(outgoing, volume, out=_m4_equilibrium_lake_support_np.zeros_like(volume), where=volume > 0.)
    stability = float(dt_seconds * _m4_equilibrium_lake_support_np.max(ratio))
    if stability > cfl * (1. + 1e-12):
        raise ValueError("water donor stability bound exceeded")
    raw = volume + dt_seconds * rate
    if not _m4_equilibrium_lake_support_np.isfinite(raw).all() or _m4_equilibrium_lake_support_np.any(raw < 0.):
        raise ValueError("negative or nonfinite water inventory")
    # A joined pool stays level until its common stage reaches a saddle. Once
    # its aggregate stock is below that saddle, the prior crest allocation is
    # retained and each newly separated side receives only its own forcing.
    balanced = raw.copy()
    curves, _ = equilibrium_geometry(domain, raw)
    owner = arrays["owner_grid"].ravel()
    old_group_stage = {}
    for label in _m4_equilibrium_lake_support_np.unique(state.component_id):
        members = _m4_equilibrium_lake_support_np.flatnonzero(state.component_id == label)
        old_group_stage[int(label)] = _combined_stage(curves, members, float(raw[members].sum()))
    wet_old_edges = []
    for (a, b), crest in zip(arrays["internal_faces"], arrays["internal_crest_m"]):
        first, second = int(owner[a]), int(owner[b])
        if (state.component_id[first] == state.component_id[second]
                and old_group_stage[int(state.component_id[first])] >= crest - 1e-12):
            wet_old_edges.append((first, second))
    retained = _labels(n, wet_old_edges)
    for label in _m4_equilibrium_lake_support_np.unique(retained):
        members = _m4_equilibrium_lake_support_np.flatnonzero(retained == label)
        if len(members) > 1:
            level = _combined_stage(curves, members, float(raw[members].sum()))
            balanced[members] = [_volume_at_stage(curves[i], level) for i in members]
            balanced[members[-1]] += float(raw[members].sum() - balanced[members].sum())
    next_state, _ = project_equilibrium_lakes(domain, balanced, state.component_id,
                                              _validated=True)
    redistribution = next_state.owner_volume_m3 - raw
    _checked(domain, next_state)
    old_edges = [(int(owner[a]), int(owner[b])) for a, b in arrays["internal_faces"]
                 if state.component_id[owner[a]] == state.component_id[owner[b]]]
    new_edges = [(int(owner[a]), int(owner[b])) for a, b in arrays["internal_faces"]
                 if next_state.component_id[owner[a]] == next_state.component_id[owner[b]]]
    paired_labels = _labels(n, old_edges + new_edges)
    bridge_stage = _m4_equilibrium_lake_support_np.maximum(stage, equilibrium_geometry(domain, next_state.owner_volume_m3)[1])
    paired = _paired_redistribution(domain, paired_labels, redistribution, bridge_stage)
    ledger = {"internal_q_m3_s": internal, "boundary_q_m3_s": boundary,
              "owner_rate_m3_s": rate, "redistribution_m3": redistribution,
              "redistribution_face_m3": paired,
              "stability_number": stability}
    return next_state, ledger

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:368 ---
def _choose(domain, state, forcing, config, now):
    interval = min(int(_m4_equilibrium_lake_support_np.searchsorted(forcing.time_seconds, now, side="right") - 1),
                   len(forcing.time_seconds) - 2)
    dt = min(config.max_dt_seconds, forcing.time_seconds[interval + 1] - now)
    reason = "minimum step or time resolution exhausted"
    while dt >= config.min_dt_seconds and now + dt > now:
        try:
            result = advance_equilibrium_lakes(domain, state, dt,
                forcing.local_q_m3_s[interval], forcing.tailwater_stage_m[interval],
                forcing.port_q_m3_s[interval], cfl=config.cfl, _validated=True)
            trial_state, trial_ledger = result
            if not _m4_equilibrium_lake_support_np.array_equal(trial_state.component_id, state.component_id):
                arrays = domain["arrays"]
                owner = arrays["owner_grid"].ravel()
                curves, _ = equilibrium_geometry(domain, state.owner_volume_m3)
                event = dt
                for (a, b), crest in zip(arrays["internal_faces"], arrays["internal_crest_m"]):
                    first, second = int(owner[a]), int(owner[b])
                    if (state.component_id[first] != state.component_id[second]
                            or trial_state.component_id[first] == trial_state.component_id[second]):
                        continue
                    members = _m4_equilibrium_lake_support_np.flatnonzero(state.component_id == state.component_id[first])
                    rate = float(trial_ledger["owner_rate_m3_s"][members].sum())
                    threshold = sum(_volume_at_stage(curves[i], crest) for i in members)
                    if rate < 0.:
                        remaining = float(state.owner_volume_m3[members].sum()) - threshold
                        if remaining > 1e-9:
                            event = min(event, remaining / -rate)
                if 0. < event < dt:
                    if event < config.min_dt_seconds:
                        return None, 0., "saddle event below minimum step"
                    dt = event
                    result = advance_equilibrium_lakes(domain, state, dt,
                        forcing.local_q_m3_s[interval], forcing.tailwater_stage_m[interval],
                        forcing.port_q_m3_s[interval], cfl=config.cfl, _validated=True)
            return result, dt, None
        except ValueError as error:
            reason = str(error)
            if reason == "step crosses equilibrium saddle event":
                arrays = domain["arrays"]
                owner = arrays["owner_grid"].ravel()
                curves, _ = equilibrium_geometry(domain, state.owner_volume_m3)
                # The event time is calculated from the unchanged explicit
                # rate, including local, port, boundary, and cross-pool flow.
                probe_dt = min(dt, config.min_dt_seconds)
                try:
                    _, probe_ledger = advance_equilibrium_lakes(domain, state, probe_dt,
                        forcing.local_q_m3_s[interval], forcing.tailwater_stage_m[interval],
                        forcing.port_q_m3_s[interval], cfl=config.cfl, _validated=True)
                except ValueError:
                    dt *= .5
                    continue
                event = dt
                for (a, b), crest in zip(arrays["internal_faces"], arrays["internal_crest_m"]):
                    first, second = int(owner[a]), int(owner[b])
                    if state.component_id[first] != state.component_id[second]:
                        continue
                    members = _m4_equilibrium_lake_support_np.flatnonzero(state.component_id == state.component_id[first])
                    rate = float(probe_ledger["owner_rate_m3_s"][members].sum())
                    threshold = sum(_volume_at_stage(curves[i], crest) for i in members)
                    remaining = float(state.owner_volume_m3[members].sum()) - threshold
                    if rate < 0. and remaining > 1e-9:
                        event = min(event, remaining / -rate)
                if config.min_dt_seconds <= event < dt:
                    dt = event
                    continue
            dt *= .5
    return None, 0., reason + "; minimum step exhausted"

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:438 ---
def solve_equilibrium_lakes(domain, forcing, initial_owner_volume_m3, config=None):
    from terrain_pipeline.common_infra import identity as _m4_equilibrium_lake_support_identity
    from terrain_pipeline.common_infra import readonly as _m4_equilibrium_lake_support_readonly
    config = EquilibriumLakeConfig() if config is None else config
    validate_natural_lakes(domain)
    raw_curves, raw_stage = equilibrium_geometry(domain, _m4_equilibrium_lake_support_np.asarray(initial_owner_volume_m3, _m4_equilibrium_lake_support_np.float64))
    native = domain["arrays"]
    if (_m4_equilibrium_lake_support_np.any(_m4_equilibrium_lake_support_np.asarray(initial_owner_volume_m3) > _m4_equilibrium_lake_support_np.array([
            _volume_at_stage(curve, upper) for curve, upper in zip(raw_curves, native["max_stage_m"])]) + 1e-10)
            or _m4_equilibrium_lake_support_np.any(raw_stage > native["unresolved_stage_limit_m"] + 1e-10)):
        raise ValueError("initial owner inventory exceeds finite or known exterior support")
    initial, initial_redistribution = project_equilibrium_lakes(domain, initial_owner_volume_m3,
                                                                 _validated=True)
    initial_paired = _paired_redistribution(domain, initial.component_id, initial_redistribution,
                                           equilibrium_geometry(domain, initial.owner_volume_m3)[1])
    _checked(domain, initial, forcing)
    if equilibrium_trace_bytes(domain, forcing, 0) > EQUILIBRIUM_MAX_BYTES:
        raise ValueError("equilibrium lake static byte budget exceeded")
    state = initial
    times = [float(forcing.time_seconds[0])]
    volumes = [state.owner_volume_m3.copy()]
    components = [state.component_id.copy()]
    stage = equilibrium_geometry(domain, state.owner_volume_m3)[1]
    wet, wet_component = _wet(domain, stage)
    stages = [stage]
    wet_support = [wet]
    wet_components = [wet_component]
    step = {name: [] for name in ("internal_q_m3_s", "boundary_q_m3_s", "owner_rate_m3_s",
                                  "redistribution_m3", "redistribution_face_m3", "stability_number")}
    failure = None
    while times[-1] < forcing.time_seconds[-1]:
        if len(step["stability_number"]) >= config.max_steps:
            failure = "maximum step count exceeded"
            break
        if equilibrium_trace_bytes(domain, forcing, len(step["stability_number"]) + 1) > EQUILIBRIUM_MAX_BYTES:
            failure = "trace byte budget exhausted"
            break
        result, dt, failure = _choose(domain, state, forcing, config, times[-1])
        if failure:
            break
        state, ledger = result
        now = times[-1]
        interval = min(int(_m4_equilibrium_lake_support_np.searchsorted(forcing.time_seconds, now, side="right") - 1),
                       len(forcing.time_seconds) - 2)
        end = forcing.time_seconds[interval + 1]
        times.append(float(end if now + dt >= end - 1e-12 else now + dt))
        volumes.append(state.owner_volume_m3.copy())
        components.append(state.component_id.copy())
        stage = equilibrium_geometry(domain, state.owner_volume_m3)[1]
        wet, wet_component = _wet(domain, stage)
        stages.append(stage)
        wet_support.append(wet)
        wet_components.append(wet_component)
        for name, value in ledger.items():
            step[name].append(value.copy() if hasattr(value, "copy") else value)
    a = {"time_seconds": _m4_equilibrium_lake_support_np.array(times, _m4_equilibrium_lake_support_np.float64),
         "forcing_time_seconds": forcing.time_seconds,
         "forcing_local_q_m3_s": forcing.local_q_m3_s,
         "forcing_tailwater_stage_m": forcing.tailwater_stage_m,
         "forcing_port_q_m3_s": forcing.port_q_m3_s,
         "initial_owner_volume_m3": _m4_equilibrium_lake_support_np.asarray(initial_owner_volume_m3, _m4_equilibrium_lake_support_np.float64).copy(),
         "initial_redistribution_m3": initial_redistribution,
         "initial_redistribution_face_m3": initial_paired,
         "trace_owner_volume_m3": _m4_equilibrium_lake_support_np.array(volumes, _m4_equilibrium_lake_support_np.float64),
         "trace_component_id": _m4_equilibrium_lake_support_np.array(components, _m4_equilibrium_lake_support_np.int64),
         "trace_owner_stage_m": _m4_equilibrium_lake_support_np.array(stages, _m4_equilibrium_lake_support_np.float64),
         "trace_wet_support": _m4_equilibrium_lake_support_np.array(wet_support, bool),
         "trace_wet_component": _m4_equilibrium_lake_support_np.array(wet_components, _m4_equilibrium_lake_support_np.int64),
         "step_dt_seconds": _m4_equilibrium_lake_support_np.diff(_m4_equilibrium_lake_support_np.array(times, _m4_equilibrium_lake_support_np.float64))}
    a.update({"domain_" + key: value for key, value in domain["arrays"].items()})
    for name, values in step.items():
        width = {"internal_q_m3_s": len(domain["arrays"]["internal_faces"]),
                 "boundary_q_m3_s": len(domain["arrays"]["boundary_faces"]),
                 "owner_rate_m3_s": len(initial.owner_volume_m3),
                 "redistribution_m3": len(initial.owner_volume_m3),
                 "redistribution_face_m3": len(domain["arrays"]["internal_faces"])}.get(name)
        a["step_" + name] = _m4_equilibrium_lake_support_np.asarray(values, _m4_equilibrium_lake_support_np.float64).reshape((len(values), width)) if width is not None else _m4_equilibrium_lake_support_np.asarray(values, _m4_equilibrium_lake_support_np.float64)
    a = {key: _m4_equilibrium_lake_support_readonly(value) for key, value in a.items()}
    m = {"schema": EQUILIBRIUM_SCHEMA, "algorithm": EQUILIBRIUM_ALGORITHM,
         "domain_metadata": domain["metadata"], "domain_identity_sha256": domain["identity_sha256"],
         "forcing_source_identity_sha256": forcing.source_identity_sha256,
         "forcing_provenance": forcing.provenance, "config": _m4_equilibrium_lake_support_asdict(config),
         "port_source_identity_sha256": forcing.port_source_identity_sha256,
         "port_provenance": forcing.port_provenance,
         "status": "failed_prefix" if failure else "complete", "failure_reason": failure,
         "requested_end_time_seconds": float(forcing.time_seconds[-1]),
         "last_time_seconds": times[-1],
         "hydraulic_model": "instant_equilibrium_components_and_finite_weir_not_saint_venant",
         "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    bundle = {"arrays": a, "metadata": m, "identity_sha256": _m4_equilibrium_lake_support_identity(a, m)}
    validate_equilibrium_lakes(bundle)
    return bundle

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:530 ---
def validate_equilibrium_lakes(bundle):
    from terrain_pipeline.common_infra import identity as _m4_equilibrium_lake_support_identity
    if not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid equilibrium lake bundle")
    a, m = bundle["arrays"], bundle["metadata"]
    if m.get("schema") != EQUILIBRIUM_SCHEMA or m.get("algorithm") != EQUILIBRIUM_ALGORITHM or _m4_equilibrium_lake_support_identity(a, m) != bundle["identity_sha256"]:
        raise ValueError("equilibrium lake identity mismatch")
    expected = ({"time_seconds", "forcing_time_seconds", "forcing_local_q_m3_s",
                 "forcing_tailwater_stage_m", "forcing_port_q_m3_s", "initial_owner_volume_m3",
                 "initial_redistribution_m3", "initial_redistribution_face_m3",
                 "trace_owner_volume_m3", "trace_component_id",
                 "trace_owner_stage_m", "trace_wet_support", "trace_wet_component",
                 "step_dt_seconds", "step_internal_q_m3_s", "step_boundary_q_m3_s",
                 "step_owner_rate_m3_s", "step_redistribution_m3",
                 "step_redistribution_face_m3", "step_stability_number"}
                | {"domain_" + key for key in DOMAIN_FIELDS})
    if (set(a) != expected or len(a) > 128 or
            any(any(axis > 8_000_000 for axis in value.shape) for value in a.values()) or
            sum(value.nbytes for value in a.values()) > EQUILIBRIUM_MAX_BYTES):
        raise ValueError("equilibrium lake schema or budget mismatch")
    if any(m[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("equilibrium lake certification flags invalid")
    domain_arrays = {key: a["domain_" + key] for key in DOMAIN_FIELDS}
    domain = {"arrays": domain_arrays, "metadata": m["domain_metadata"],
              "identity_sha256": m["domain_identity_sha256"]}
    validate_natural_lakes(domain)
    forcing = EquilibriumLakeForcing(a["forcing_time_seconds"], a["forcing_local_q_m3_s"],
        a["forcing_tailwater_stage_m"], a["forcing_port_q_m3_s"],
        m["forcing_source_identity_sha256"], m["forcing_provenance"],
        m["port_source_identity_sha256"], m["port_provenance"])
    config = EquilibriumLakeConfig(**m["config"])
    initial, redistribution = project_equilibrium_lakes(domain, a["initial_owner_volume_m3"],
                                                        _validated=True)
    if not _m4_equilibrium_lake_support_np.allclose(redistribution, a["initial_redistribution_m3"], rtol=0., atol=1e-9):
        raise ValueError("initial equilibrium projection mismatch")
    paired = _paired_redistribution(domain, initial.component_id, redistribution,
                                   equilibrium_geometry(domain, initial.owner_volume_m3)[1])
    if not _m4_equilibrium_lake_support_np.allclose(paired, a["initial_redistribution_face_m3"], rtol=0., atol=1e-9):
        raise ValueError("initial paired projection mismatch")
    time = a["time_seconds"]
    k = len(time) - 1
    n = len(domain_arrays["seed_cell_ids"])
    if (time.dtype != _m4_equilibrium_lake_support_np.float64 or time.ndim != 1 or not _m4_equilibrium_lake_support_np.isfinite(time).all()
            or _m4_equilibrium_lake_support_np.any(_m4_equilibrium_lake_support_np.diff(time) <= 0.) or time[0] != forcing.time_seconds[0]
            or not _m4_equilibrium_lake_support_np.array_equal(a["step_dt_seconds"], _m4_equilibrium_lake_support_np.diff(time))
            or a["trace_owner_volume_m3"].dtype != _m4_equilibrium_lake_support_np.float64
            or a["trace_owner_volume_m3"].shape != (k + 1, n)
            or a["trace_component_id"].dtype != _m4_equilibrium_lake_support_np.int64
            or a["trace_component_id"].shape != (k + 1, n)
            or a["trace_owner_stage_m"].dtype != _m4_equilibrium_lake_support_np.float64
            or a["trace_owner_stage_m"].shape != (k + 1, n)
            or a["trace_wet_support"].dtype != _m4_equilibrium_lake_support_np.bool_
            or a["trace_wet_support"].shape != (k + 1, len(domain_arrays["support_cell_ids"]))
            or a["trace_wet_component"].dtype != _m4_equilibrium_lake_support_np.int64
            or a["trace_wet_component"].shape != (k + 1, n)
            or not _m4_equilibrium_lake_support_np.array_equal(a["trace_owner_volume_m3"][0], initial.owner_volume_m3)
            or not _m4_equilibrium_lake_support_np.array_equal(a["trace_component_id"][0], initial.component_id)):
        raise ValueError("equilibrium lake trace shape or initial state mismatch")
    shapes = {"internal_q_m3_s": (k, len(domain_arrays["internal_faces"])),
              "boundary_q_m3_s": (k, len(domain_arrays["boundary_faces"])),
              "owner_rate_m3_s": (k, n), "redistribution_m3": (k, n),
              "redistribution_face_m3": (k, len(domain_arrays["internal_faces"])),
              "stability_number": (k,)}
    for name, shape in shapes.items():
        value = a["step_" + name]
        if value.dtype != _m4_equilibrium_lake_support_np.float64 or value.shape != shape or not _m4_equilibrium_lake_support_np.isfinite(value).all():
            raise ValueError("equilibrium lake step schema mismatch")
    for i in range(k + 1):
        state = EquilibriumLakeState(a["trace_owner_volume_m3"][i], a["trace_component_id"][i])
        _checked(domain, state, forcing)
        stage = equilibrium_geometry(domain, state.owner_volume_m3)[1]
        wet, component = _wet(domain, stage)
        if (not _m4_equilibrium_lake_support_np.allclose(a["trace_owner_stage_m"][i], stage, rtol=0., atol=1e-9)
                or not _m4_equilibrium_lake_support_np.array_equal(a["trace_wet_support"][i], wet)
                or not _m4_equilibrium_lake_support_np.array_equal(a["trace_wet_component"][i], component)):
            raise ValueError("equilibrium lake stage or wet footprint mismatch")
    for i in range(k):
        state = EquilibriumLakeState(a["trace_owner_volume_m3"][i], a["trace_component_id"][i])
        result, dt, reason = _choose(domain, state, forcing, config, time[i])
        if reason or not _m4_equilibrium_lake_support_math.isclose(dt, a["step_dt_seconds"][i], rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("equilibrium lake step selection mismatch")
        next_state, ledger = result
        if (not _m4_equilibrium_lake_support_np.allclose(next_state.owner_volume_m3, a["trace_owner_volume_m3"][i + 1], rtol=0., atol=1e-9)
                or not _m4_equilibrium_lake_support_np.array_equal(next_state.component_id, a["trace_component_id"][i + 1])):
            raise ValueError("equilibrium lake next inventory or component mismatch")
        for name, value in ledger.items():
            if not _m4_equilibrium_lake_support_np.allclose(value, a["step_" + name][i], rtol=0., atol=1e-9):
                raise ValueError("equilibrium lake flux or redistribution mismatch")
    if m["last_time_seconds"] != time[-1] or m["requested_end_time_seconds"] != forcing.time_seconds[-1]:
        raise ValueError("equilibrium lake time metadata mismatch")
    if m["status"] == "complete":
        if time[-1] != forcing.time_seconds[-1] or m["failure_reason"] is not None:
            raise ValueError("invalid complete equilibrium lake trace")
    elif m["status"] == "failed_prefix":
        if time[-1] >= forcing.time_seconds[-1] or not m["failure_reason"]:
            raise ValueError("invalid equilibrium lake failed prefix")
        if k >= config.max_steps:
            reason = "maximum step count exceeded"
        elif equilibrium_trace_bytes(domain, forcing, k + 1) > EQUILIBRIUM_MAX_BYTES:
            reason = "trace byte budget exhausted"
        else:
            state = EquilibriumLakeState(a["trace_owner_volume_m3"][-1], a["trace_component_id"][-1])
            _, _, reason = _choose(domain, state, forcing, config, time[-1])
        if reason != m["failure_reason"]:
            raise ValueError("equilibrium lake failed prefix lacks witness")
    else:
        raise ValueError("invalid equilibrium lake status")
    return True

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:639 ---
def save_equilibrium_lakes(path, bundle):
    from terrain_pipeline.common_infra import save_bundle as _m4_equilibrium_lake_support_save_bundle
    _m4_equilibrium_lake_support_save_bundle(path, bundle, validator=validate_equilibrium_lakes)

# --- terrain_pipeline/surface_rivers/metric_equilibrium_lake_support.py:643 ---
def load_equilibrium_lakes(path, *, expected_sha256):
    from terrain_pipeline.common_infra import load_bundle as _m4_equilibrium_lake_support_load_bundle
    return _m4_equilibrium_lake_support_load_bundle(path, expected_sha256=expected_sha256,
                       validator=validate_equilibrium_lakes, max_bytes=EQUILIBRIUM_MAX_BYTES)

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:23 ---
LAKE_CHANNEL_SCHEMA = "terragenesis-natural-lake-channel-port-v2"

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:24 ---
LAKE_CHANNEL_ALGORITHM = "bounded-signed-level-pool-rectangular-channel-v1"

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:25 ---
LAKE_CHANNEL_MAX_BYTES = 128 * 1024 * 1024

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:29 ---
@_m4_lake_channel_coupling_dataclass(frozen=True)
class LakeChannelPort:
    boundary_face_index: int
    channel_node_index: int
    coefficient_m3_s_m15: float
    provenance: str

    def __post_init__(self):
        if type(self.boundary_face_index) is not int or self.boundary_face_index < 0:
            raise ValueError("nonnegative boundary face index required")
        if type(self.channel_node_index) is not int or self.channel_node_index < 0:
            raise ValueError("nonnegative channel node index required")
        if (isinstance(self.coefficient_m3_s_m15, bool) or
                not isinstance(self.coefficient_m3_s_m15, (int, float)) or
                not _m4_lake_channel_coupling_math.isfinite(self.coefficient_m3_s_m15) or self.coefficient_m3_s_m15 <= 0.):
            raise ValueError("finite positive port coefficient required")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("port coefficient provenance required")

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:49 ---
@_m4_lake_channel_coupling_dataclass(frozen=True)
class LakeChannelForcing:
    time_seconds: _m4_lake_channel_coupling_np.ndarray
    channel_local_q_m3_s: _m4_lake_channel_coupling_np.ndarray
    lake_local_q_m3_s: _m4_lake_channel_coupling_np.ndarray
    tailwater_stage_m: _m4_lake_channel_coupling_np.ndarray
    source_identity_sha256: str
    provenance: str

    def __post_init__(self):
        t = self.time_seconds
        if (not isinstance(t, _m4_lake_channel_coupling_np.ndarray) or t.dtype != _m4_lake_channel_coupling_np.float64 or t.ndim != 1 or
                not 2 <= len(t) <= 100001 or not _m4_lake_channel_coupling_np.isfinite(t).all() or t[0] < 0. or
                _m4_lake_channel_coupling_np.any(_m4_lake_channel_coupling_np.diff(t) <= 0.)):
            raise ValueError("finite increasing physical forcing times required")
        for name in ("channel_local_q_m3_s", "lake_local_q_m3_s", "tailwater_stage_m"):
            value = getattr(self, name)
            if (not isinstance(value, _m4_lake_channel_coupling_np.ndarray) or value.dtype != _m4_lake_channel_coupling_np.float64 or value.ndim != 2 or
                    value.shape[0] != len(t) - 1 or not _m4_lake_channel_coupling_np.isfinite(value).all()):
                raise ValueError(name + " must be finite interval-node float64")
            if name != "tailwater_stage_m" and _m4_lake_channel_coupling_np.any(value < 0.):
                raise ValueError("negative local water source")
            object.__setattr__(self, name, _m4_lake_channel_coupling_readonly(value))
        if sum(x.nbytes for x in (t, self.channel_local_q_m3_s, self.lake_local_q_m3_s,
                                  self.tailwater_stage_m)) > LAKE_CHANNEL_MAX_BYTES // 2:
            raise ValueError("forcing byte budget exceeded")
        if (not isinstance(self.source_identity_sha256, str) or len(self.source_identity_sha256) != 64 or
                any(c not in "0123456789abcdef" for c in self.source_identity_sha256)):
            raise ValueError("source identity SHA256 required")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("forcing provenance required")
        object.__setattr__(self, "time_seconds", _m4_lake_channel_coupling_readonly(t))

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:83 ---
@_m4_lake_channel_coupling_dataclass(frozen=True)
class LakeChannelConfig:
    max_dt_seconds: float = .5
    min_dt_seconds: float = 1e-8
    cfl: float = .5
    max_steps: int = 20000

    def __post_init__(self):
        for name in ("max_dt_seconds", "min_dt_seconds", "cfl"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not _m4_lake_channel_coupling_math.isfinite(value) or value <= 0.:
                raise ValueError("finite positive step control required")
            object.__setattr__(self, name, float(value))
        if self.min_dt_seconds > self.max_dt_seconds or self.cfl > 1.:
            raise ValueError("invalid step control bounds")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 1_000_000:
            raise ValueError("bounded step count required")

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:101 ---
LAKE_CHANNEL_DOMAIN_FIELDS = ("source_height_m", "source_valid_mask", "seed_cell_ids", "owner_grid",
                 "max_stage_m", "support_cell_ids", "internal_faces", "internal_crest_m",
                 "boundary_faces", "boundary_kinds", "boundary_crest_m", "unresolved_stage_limit_m")

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:104 ---
FORCING_FIELDS = ("time_seconds", "channel_local_q_m3_s", "lake_local_q_m3_s", "tailwater_stage_m")

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:105 ---
STATE_FIELDS = ("channel_volume_m3", "lake_volume_m3", "channel_stage_m", "lake_stage_m",
                "channel_depth_m", "wet_support", "wet_component")

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:107 ---
STEP_FIELDS = ("channel_q_m3_s", "lake_internal_q_m3_s", "port_q_m3_s",
               "boundary_q_m3_s", "channel_donor_q_m3_s", "lake_donor_q_m3_s",
               "channel_residual_m3", "lake_residual_m3", "stability_number")

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:112 ---
def _mesh_sample(geometry, point):
    a = geometry["arrays"]
    vertices, triangles = a["vertices_xz_m"], a["triangles"]
    spacing = geometry["metadata"]["config"]["fine_spacing_m"]
    nx = int(triangles[2, 1])
    nz = int(triangles[0, 2]) // nx
    col = min(max(int(_m4_lake_channel_coupling_math.floor((point[0] - vertices[0, 0]) / spacing)), 0), nx - 2)
    row = min(max(int(_m4_lake_channel_coupling_math.floor((point[1] - vertices[0, 1]) / spacing)), 0), nz - 2)
    cell = row * (nx - 1) + col
    for tri_id in range(4 * cell, 4 * cell + 4):
        ids = triangles[tri_id]
        triangle = vertices[ids]
        matrix = _m4_lake_channel_coupling_np.column_stack((triangle[1] - triangle[0], triangle[2] - triangle[0]))
        uv = _m4_lake_channel_coupling_np.linalg.solve(matrix, point - triangle[0])
        if min(1. - uv.sum(), uv[0], uv[1]) >= -1e-9:
            bed = a["bed_elevation_m"][ids]
            return float(bed[0] + uv @ (bed[1:] - bed[0]))
    raise ValueError("M5 channel node leaves represented mesh")

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:132 ---
def lakechannel_trace_bytes(domain, geometry, network, ports, forcing, steps):
    from terrain_pipeline.surface_rivers.metric_channel_product import NETWORK_FIELDS as _m4_lake_channel_coupling_NETWORK_FIELDS
    da = domain["arrays"]
    nc, nl = len(network.receiver), len(da["seed_cell_ids"])
    static = sum(value.nbytes for value in da.values())
    static += sum(value.nbytes for value in geometry["arrays"].values())
    static += sum(_m4_lake_channel_coupling_np.asarray(getattr(network, key)).astype("U24").nbytes
                  if key == "terminal_kind" else _m4_lake_channel_coupling_np.asarray(getattr(network, key)).nbytes
                  for key in _m4_lake_channel_coupling_NETWORK_FIELDS)
    static += sum(getattr(forcing, key).nbytes for key in FORCING_FIELDS)
    static += 8 * (nc + nl + 3 * len(ports))
    state = 8 * (3 * nc + 3 * nl) + len(da["support_cell_ids"])
    step = 8 * (3 * nc + 2 * nl + len(da["internal_faces"]) +
                len(ports) + len(da["boundary_faces"]) + 1)
    return static + state + 8 + steps * (state + step + 16)

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:148 ---
def _checked_inputs(domain, geometry, network, ports, forcing, initial_channel, initial_lake, config):
    from terrain_pipeline.channel_geometry import _modified_bed_slope as _m4_lake_channel_coupling_modified_bed_slope
    from terrain_pipeline.channel_geometry import validate_channel_geometry as _m4_lake_channel_coupling_validate_channel_geometry
    from terrain_pipeline.channel_geometry import ChannelNetwork as _m4_lake_channel_coupling_ChannelNetwork
    from terrain_pipeline.channel_geometry import receiver_distances as _m4_lake_channel_coupling_receiver_distances
    validate_natural_lakes(domain)
    _m4_lake_channel_coupling_validate_channel_geometry(geometry)
    if domain["metadata"]["schema"] != DOMAIN_SCHEMA or not isinstance(network, _m4_lake_channel_coupling_ChannelNetwork):
        raise ValueError("natural lake domain and channel network required")
    da, ga = domain["arrays"], geometry["arrays"]
    terrain = domain["metadata"]["terrain_metadata"]
    if not isinstance(forcing, LakeChannelForcing) or not isinstance(config, LakeChannelConfig):
        raise ValueError("typed forcing and config required")
    if (network.source_identity_sha256 != geometry["identity_sha256"] or
            forcing.source_identity_sha256 != domain["metadata"]["source_identity_sha256"] or
            geometry["metadata"]["source_identity_sha256"] != domain["metadata"]["source_identity_sha256"] or
            not _m4_lake_channel_coupling_np.array_equal(ga["source_height_m"], da["source_height_m"]) or
            not _m4_lake_channel_coupling_np.array_equal(ga["source_valid_mask"], da["source_valid_mask"]) or
            geometry["metadata"]["terrain_metadata"].get("vertical_datum") != domain["metadata"]["terrain_metadata"].get("vertical_datum")):
        raise ValueError("channel and natural lake source or vertical datum mismatch")
    nc, nl, nb = len(network.receiver), len(da["seed_cell_ids"]), len(da["boundary_faces"])
    if nc > 32 or nl > 16 or len(ports) > 32:
        raise ValueError("bounded lake-channel node count exceeded")
    if any(not isinstance(p, LakeChannelPort) for p in ports):
        raise ValueError("LakeChannelPort objects required")
    if (forcing.channel_local_q_m3_s.shape[1] != nc or forcing.lake_local_q_m3_s.shape[1] != nl or
            forcing.tailwater_stage_m.shape[1] != nb):
        raise ValueError("forcing node or face count mismatch")
    if (not _m4_lake_channel_coupling_np.array_equal(network.receiver, ga["receiver"]) or
            not _m4_lake_channel_coupling_np.array_equal(network.width_m, ga["width_m"])):
        raise ValueError("channel network topology or width differs from M5 geometry")
    expected_length = _m4_lake_channel_coupling_np.zeros(nc)
    if not _m4_lake_channel_coupling_np.allclose(network.receiver_distance_m, _m4_lake_channel_coupling_receiver_distances(ga["node_xz_m"], network.receiver), rtol=0., atol=1e-8):
        raise ValueError("channel receiver distances differ from M5 centerline")
    for node, target in enumerate(network.receiver):
        if target >= 0:
            half = _m4_lake_channel_coupling_np.linalg.norm(ga["node_xz_m"][node] - ga["node_xz_m"][target]) / 2.
            expected_length[node] += half
            expected_length[target] += half
    if _m4_lake_channel_coupling_np.any(expected_length <= 0.) or not _m4_lake_channel_coupling_np.allclose(network.length_m, expected_length, rtol=0., atol=1e-8):
        raise ValueError("channel lengths do not partition M5 centerline")
    vertex = ga["vertices_xz_m"]
    mesh_bed = ga["bed_elevation_m"]
    sampled = _m4_lake_channel_coupling_np.array([_mesh_sample(geometry, point) for point in ga["node_xz_m"]])
    if not _m4_lake_channel_coupling_np.allclose(network.bed_elevation_m, sampled, rtol=0., atol=1e-8):
        raise ValueError("channel bed differs from M5 represented bed")
    _m4_lake_channel_coupling_modified_bed_slope(ga["node_xz_m"], network.receiver, vertex, ga["triangles"],
                        mesh_bed, geometry["metadata"]["config"]["fine_spacing_m"])
    for node, target in enumerate(network.receiver):
        if target >= 0:
            length = _m4_lake_channel_coupling_np.linalg.norm(ga["node_xz_m"][node] - ga["node_xz_m"][target])
            slope = (sampled[node] - sampled[target]) / length
            if not _m4_lake_channel_coupling_math.isclose(network.bed_slope[node], slope, rel_tol=0., abs_tol=1e-8):
                raise ValueError("channel slope differs from M5 represented bed")
    for node, kind in enumerate(network.terminal_kind):
        if kind == "open_outflow":
            donors = _m4_lake_channel_coupling_np.flatnonzero(network.receiver == node)
            if len(donors) != 1 or not _m4_lake_channel_coupling_math.isclose(network.bed_slope[node],
                                                    network.bed_slope[donors[0]], rel_tol=0., abs_tol=1e-8):
                raise ValueError("open terminal Manning slope lacks unique M5 edge extrapolation")
    for value, shape, name in ((initial_channel, (nc,), "initial channel"),
                               (initial_lake, (nl,), "initial lake")):
        if not isinstance(value, _m4_lake_channel_coupling_np.ndarray) or value.dtype != _m4_lake_channel_coupling_np.float64 or value.shape != shape or not _m4_lake_channel_coupling_np.isfinite(value).all() or _m4_lake_channel_coupling_np.any(value < 0.):
            raise ValueError(name + " inventory invalid")
    if _m4_lake_channel_coupling_np.any(initial_channel > network.width_m * network.length_m * network.max_depth_m + 1e-10):
        raise ValueError("initial channel depth exceeds finite capacity")
    if _m4_lake_channel_coupling_np.any(initial_channel[network.terminal_kind == "unknown_boundary"] > 0.):
        raise ValueError("initial channel inventory reaches unknown terminal")
    area_m2 = terrain["dx_m"] * terrain["dz_m"]
    curves = _curves(da, area_m2)
    capacities = _m4_lake_channel_coupling_np.array([_volume_at_stage(curve, upper) for curve, upper in zip(curves, da["max_stage_m"])])
    if _m4_lake_channel_coupling_np.any(initial_lake > capacities + 1e-10):
        raise ValueError("initial natural lake inventory exceeds finite support")
    _, _, initial_stage, _, _ = lakechannel_geometry(domain, network, initial_channel, initial_lake)
    if _m4_lake_channel_coupling_np.any(initial_stage > da["unresolved_stage_limit_m"] + 1e-10):
        raise ValueError("initial lake reaches unknown exterior face crest")
    if lakechannel_trace_bytes(domain, geometry, network, ports, forcing, 0) > LAKE_CHANNEL_MAX_BYTES:
        raise ValueError("lake-channel static input byte budget exceeded")
    owner = da["owner_grid"].ravel()
    ids = ga["source_node_cell_ids"]
    if _m4_lake_channel_coupling_np.any(owner[ids] >= 0):
        raise ValueError("channel control overlaps natural lake storage support")
    # M5 stores the represented cut on canonical vertices. A positive cut on
    # an original lake support vertex would assign that prism to both stores.
    vertices = ga["vertices_xz_m"]
    terrain = domain["metadata"]["terrain_metadata"]
    gx = (vertices[:, 0] - terrain["x0_m"]) / terrain["dx_m"]
    gz = (vertices[:, 1] - terrain["z0_m"]) / terrain["dz_m"]
    rows, cols = da["owner_grid"].shape
    node_col = _m4_lake_channel_coupling_np.clip(_m4_lake_channel_coupling_np.rint(gx).astype(_m4_lake_channel_coupling_np.int64), 0, cols - 1)
    node_row = _m4_lake_channel_coupling_np.clip(_m4_lake_channel_coupling_np.rint(gz).astype(_m4_lake_channel_coupling_np.int64), 0, rows - 1)
    if _m4_lake_channel_coupling_np.any((da["owner_grid"][node_row, node_col] >= 0) &
              (ga["cut_depth_m"] > 1e-10)):
        raise ValueError("channel cut overlaps natural lake support")
    face_ids = [p.boundary_face_index for p in ports]
    nodes = [p.channel_node_index for p in ports]
    if len(set(face_ids)) != len(face_ids) or len(set(nodes)) != len(nodes):
        raise ValueError("duplicate lake-channel port face or node")
    for port in ports:
        face, node = port.boundary_face_index, port.channel_node_index
        if face >= nb or node >= nc or da["boundary_kinds"][face] != "tailwater" or network.receiver[node] != -1:
            raise ValueError("port must bind a tailwater face and terminal channel")
        lake_cell, neighbor_cell = da["boundary_faces"][face]
        if neighbor_cell < 0 or ids[node] != neighbor_cell or owner[lake_cell] < 0 or owner[neighbor_cell] >= 0:
            raise ValueError("port lacks matching original D4 lake/channel face")
        expected_xz = _m4_lake_channel_coupling_np.array([terrain["x0_m"] + neighbor_cell % cols * terrain["dx_m"],
                                terrain["z0_m"] + neighbor_cell // cols * terrain["dz_m"]])
        if not _m4_lake_channel_coupling_np.allclose(ga["node_xz_m"][node], expected_xz, rtol=0., atol=1e-9):
            raise ValueError("port terminal shifted away from original D4 outer neighbor")
        if forcing.tailwater_stage_m[:, face].any():
            raise ValueError("ported tailwater face cannot also receive external stage")
    unported_tail = _m4_lake_channel_coupling_np.flatnonzero(da["boundary_kinds"] == "tailwater")
    if any(face not in face_ids for face in unported_tail) and not _m4_lake_channel_coupling_np.isfinite(forcing.tailwater_stage_m[:, unported_tail]).all():
        raise ValueError("unported tailwater stage required")
    return nc, nl, nb

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:261 ---
def lakechannel_geometry(domain, network, channel_volume, lake_volume):
    da = domain["arrays"]
    area = network.width_m * network.length_m
    depth = channel_volume / area
    channel_stage = network.bed_elevation_m + depth
    cell_area = domain["metadata"]["terrain_metadata"]["dx_m"] * domain["metadata"]["terrain_metadata"]["dz_m"]
    curves = _curves(da, cell_area)
    lake_stage = _m4_lake_channel_coupling_np.array([_stage_at_volume(curve, volume) for curve, volume in zip(curves, lake_volume)])
    wet, component = _wet_state(da, lake_stage)
    return depth, channel_stage, lake_stage, wet, component

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:273 ---
def lakechannel_rates(domain, network, ports, forcing, interval, channel_volume, lake_volume):
    da = domain["arrays"]
    nc, nl = len(channel_volume), len(lake_volume)
    depth, channel_stage, lake_stage, _, _ = lakechannel_geometry(domain, network, channel_volume, lake_volume)
    area = network.width_m * depth
    perimeter = network.width_m + 2. * depth
    radius = _m4_lake_channel_coupling_np.divide(area, perimeter, out=_m4_lake_channel_coupling_np.zeros(nc), where=perimeter > 0.)
    channel_q = _m4_lake_channel_coupling_np.zeros(nc)
    port_nodes = _m4_lake_channel_coupling_np.array([p.channel_node_index for p in ports], _m4_lake_channel_coupling_np.int64)
    active = _m4_lake_channel_coupling_np.isin(network.terminal_kind, ("interior", "open_outflow"))
    active[port_nodes] = False
    channel_q[active] = area[active] * radius[active] ** (2. / 3.) * _m4_lake_channel_coupling_np.sqrt(network.bed_slope[active]) / network.roughness[active]
    owner = da["owner_grid"].ravel()
    internal = _m4_lake_channel_coupling_np.zeros(len(da["internal_faces"]))
    coefficient = domain["metadata"]["weir_coefficient_m3_s_m15"]
    for e, (first_cell, second_cell) in enumerate(da["internal_faces"]):
        first, second = int(owner[first_cell]), int(owner[second_cell])
        difference = lake_stage[first] - lake_stage[second]
        if difference:
            high, low = max(lake_stage[first], lake_stage[second]), min(lake_stage[first], lake_stage[second])
            internal[e] = _m4_lake_channel_coupling_math.copysign(coefficient * max(high - max(da["internal_crest_m"][e], low), 0.) ** 1.5, difference)
    boundary = _m4_lake_channel_coupling_np.zeros(len(da["boundary_faces"]))
    port_faces = {p.boundary_face_index for p in ports}
    for e, (lake_cell, _) in enumerate(da["boundary_faces"]):
        if e in port_faces:
            continue
        lake = int(owner[lake_cell])
        kind, crest = da["boundary_kinds"][e], da["boundary_crest_m"][e]
        if kind == "free_outflow":
            boundary[e] = coefficient * max(lake_stage[lake] - crest, 0.) ** 1.5
        elif kind == "tailwater":
            tail = forcing.tailwater_stage_m[interval, e]
            difference = lake_stage[lake] - tail
            if difference:
                high, low = max(lake_stage[lake], tail), min(lake_stage[lake], tail)
                boundary[e] = _m4_lake_channel_coupling_math.copysign(coefficient * max(high - max(crest, low), 0.) ** 1.5, difference)
    port_q = _m4_lake_channel_coupling_np.zeros(len(ports))
    for index, port in enumerate(ports):
        face, node = port.boundary_face_index, port.channel_node_index
        lake = int(owner[da["boundary_faces"][face, 0]])
        difference = channel_stage[node] - lake_stage[lake]
        if difference:
            high, low = max(channel_stage[node], lake_stage[lake]), min(channel_stage[node], lake_stage[lake])
            crest = da["boundary_crest_m"][face]
            port_q[index] = _m4_lake_channel_coupling_math.copysign(port.coefficient_m3_s_m15 * max(high - max(crest, low), 0.) ** 1.5, difference)
            if (port_q[index] > 0. and channel_volume[node] <= 0.) or (port_q[index] < 0. and lake_volume[lake] <= 0.):
                port_q[index] = 0.
    if not all(_m4_lake_channel_coupling_np.isfinite(x).all() for x in (channel_q, internal, boundary, port_q)):
        raise ValueError("nonfinite reduced hydraulic discharge")
    return channel_q, internal, boundary, port_q

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:325 ---
def _candidate(domain, network, ports, forcing, interval, dt, channel_volume, lake_volume):
    da = domain["arrays"]
    channel_q, internal_q, boundary_q, port_q = lakechannel_rates(domain, network, ports, forcing, interval, channel_volume, lake_volume)
    owner = da["owner_grid"].ravel()
    channel_donor = _m4_lake_channel_coupling_np.zeros_like(channel_volume)
    lake_donor = _m4_lake_channel_coupling_np.zeros_like(lake_volume)
    outward_channel = channel_q.copy()
    outward_lake = _m4_lake_channel_coupling_np.zeros_like(lake_volume)
    receiver = network.receiver
    edges = receiver >= 0
    _m4_lake_channel_coupling_np.add.at(channel_donor, receiver[edges], channel_q[edges])
    for edge, (first_cell, second_cell) in enumerate(da["internal_faces"]):
        first, second = int(owner[first_cell]), int(owner[second_cell])
        lake_donor[first] -= internal_q[edge]
        lake_donor[second] += internal_q[edge]
        outward_lake[first] += max(internal_q[edge], 0.)
        outward_lake[second] += max(-internal_q[edge], 0.)
    for edge, (lake_cell, _) in enumerate(da["boundary_faces"]):
        lake_donor[int(owner[lake_cell])] -= boundary_q[edge]
        outward_lake[int(owner[lake_cell])] += max(boundary_q[edge], 0.)
    for index, port in enumerate(ports):
        lake = int(owner[da["boundary_faces"][port.boundary_face_index, 0]])
        channel_donor[port.channel_node_index] -= port_q[index]
        lake_donor[lake] += port_q[index]
        outward_channel[port.channel_node_index] += max(port_q[index], 0.)
        outward_lake[lake] += max(-port_q[index], 0.)
    channel_next = channel_volume + dt * (forcing.channel_local_q_m3_s[interval] + channel_donor - channel_q)
    lake_next = lake_volume + dt * (forcing.lake_local_q_m3_s[interval] + lake_donor)
    if not _m4_lake_channel_coupling_np.isfinite(channel_next).all() or not _m4_lake_channel_coupling_np.isfinite(lake_next).all():
        return None, "nonfinite water inventory"
    if _m4_lake_channel_coupling_np.any(channel_next < 0.) or _m4_lake_channel_coupling_np.any(lake_next < 0.):
        return None, "negative water inventory"
    if _m4_lake_channel_coupling_np.any(channel_next[network.terminal_kind == "unknown_boundary"] > 0.):
        return None, "unknown channel terminal reached"
    if _m4_lake_channel_coupling_np.any(channel_next > network.width_m * network.length_m * network.max_depth_m + 1e-10):
        return None, "channel depth capacity exceeded"
    area = domain["metadata"]["terrain_metadata"]["dx_m"] * domain["metadata"]["terrain_metadata"]["dz_m"]
    curves = _curves(da, area)
    capacities = _m4_lake_channel_coupling_np.array([_volume_at_stage(curve, upper) for curve, upper in zip(curves, da["max_stage_m"])])
    if _m4_lake_channel_coupling_np.any(lake_next > capacities + 1e-10):
        return None, "finite natural lake support exceeded"
    _, _, next_stage, _, _ = lakechannel_geometry(domain, network, channel_next, lake_next)
    if _m4_lake_channel_coupling_np.any(next_stage > da["unresolved_stage_limit_m"] + 1e-10):
        return None, "unknown exterior face crest reached"
    channel_residual = channel_next - channel_volume - dt * (forcing.channel_local_q_m3_s[interval] + channel_donor - channel_q)
    lake_residual = lake_next - lake_volume - dt * (forcing.lake_local_q_m3_s[interval] + lake_donor)
    channel_ratio = _m4_lake_channel_coupling_np.divide(outward_channel, channel_volume, out=_m4_lake_channel_coupling_np.zeros_like(channel_volume), where=channel_volume > 0.)
    lake_ratio = _m4_lake_channel_coupling_np.divide(outward_lake, lake_volume, out=_m4_lake_channel_coupling_np.zeros_like(lake_volume), where=lake_volume > 0.)
    stability = dt * max(float(_m4_lake_channel_coupling_np.max(channel_ratio)), float(_m4_lake_channel_coupling_np.max(lake_ratio)))
    return dict(channel_volume_m3=channel_next, lake_volume_m3=lake_next,
                channel_q_m3_s=channel_q, lake_internal_q_m3_s=internal_q,
                boundary_q_m3_s=boundary_q, port_q_m3_s=port_q,
                channel_donor_q_m3_s=channel_donor, lake_donor_q_m3_s=lake_donor,
                channel_residual_m3=channel_residual, lake_residual_m3=lake_residual,
                stability_number=stability), None

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:382 ---
def _choose_step(domain, network, ports, forcing, config, now, channel, lake):
    interval = min(int(_m4_lake_channel_coupling_np.searchsorted(forcing.time_seconds, now, side="right") - 1),
                   len(forcing.time_seconds) - 2)
    end = forcing.time_seconds[interval + 1]
    dt = min(config.max_dt_seconds, end - now)
    last_reason = "minimum step or time resolution exhausted"
    while dt >= config.min_dt_seconds and now + dt > now:
        try:
            trial, reason = _candidate(domain, network, ports, forcing, interval, dt, channel, lake)
        except ValueError as error:
            return None, 0., str(error)
        if reason is None and trial["stability_number"] <= config.cfl * (1. + 1e-12):
            return trial, dt, None
        last_reason = reason or "water donor stability bound exceeded"
        dt *= .5
    return None, 0., last_reason + "; minimum step exhausted"

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:400 ---
def solve_lake_channel(domain, geometry, network, ports, forcing, initial_channel_volume_m3,
                       initial_lake_volume_m3, config=None):
    from terrain_pipeline.common_infra import identity as _m4_lake_channel_coupling_identity
    from terrain_pipeline.common_infra import readonly as _m4_lake_channel_coupling_readonly
    from terrain_pipeline.surface_rivers.metric_channel_product import NETWORK_FIELDS as _m4_lake_channel_coupling_NETWORK_FIELDS
    from terrain_pipeline.channel_geometry import GEOMETRY_SEMANTICS as _m4_lake_channel_coupling_GEOMETRY_SEMANTICS
    config = LakeChannelConfig() if config is None else config
    ports = tuple(ports)
    _checked_inputs(domain, geometry, network, ports, forcing, initial_channel_volume_m3,
                    initial_lake_volume_m3, config)
    channel, lake = initial_channel_volume_m3.copy(), initial_lake_volume_m3.copy()
    times = [float(forcing.time_seconds[0])]
    states = {name: [] for name in STATE_FIELDS}
    steps = {name: [] for name in STEP_FIELDS}
    def append_state():
        depth, cstage, lstage, wet, component = lakechannel_geometry(domain, network, channel, lake)
        for name, value in (("channel_volume_m3", channel), ("lake_volume_m3", lake),
                            ("channel_stage_m", cstage), ("lake_stage_m", lstage),
                            ("channel_depth_m", depth), ("wet_support", wet),
                            ("wet_component", component)):
            states[name].append(value.copy())
    append_state()
    failure = None
    while times[-1] < forcing.time_seconds[-1]:
        if len(steps[STEP_FIELDS[0]]) >= config.max_steps:
            failure = "maximum step count exceeded"; break
        if lakechannel_trace_bytes(domain, geometry, network, ports, forcing, len(steps[STEP_FIELDS[0]]) + 1) > LAKE_CHANNEL_MAX_BYTES:
            failure = "trace byte budget exhausted"; break
        now = times[-1]
        trial, dt, failure = _choose_step(domain, network, ports, forcing, config, now, channel, lake)
        if failure:
            break
        interval = min(int(_m4_lake_channel_coupling_np.searchsorted(forcing.time_seconds, now, side="right") - 1), len(forcing.time_seconds) - 2)
        end = forcing.time_seconds[interval + 1]
        channel, lake = trial["channel_volume_m3"], trial["lake_volume_m3"]
        for name in STEP_FIELDS:
            steps[name].append(trial[name].copy() if hasattr(trial[name], "copy") else trial[name])
        times.append(float(end if now + dt >= end else now + dt))
        append_state()
    arrays = {"trace_time_seconds": _m4_lake_channel_coupling_readonly(_m4_lake_channel_coupling_np.array(times, _m4_lake_channel_coupling_np.float64)),
              "forcing_time_seconds": forcing.time_seconds,
              "forcing_channel_local_q_m3_s": forcing.channel_local_q_m3_s,
              "forcing_lake_local_q_m3_s": forcing.lake_local_q_m3_s,
              "forcing_tailwater_stage_m": forcing.tailwater_stage_m,
              "initial_channel_volume_m3": _m4_lake_channel_coupling_readonly(initial_channel_volume_m3),
              "initial_lake_volume_m3": _m4_lake_channel_coupling_readonly(initial_lake_volume_m3),
              "port_face_index": _m4_lake_channel_coupling_readonly(_m4_lake_channel_coupling_np.array([p.boundary_face_index for p in ports], _m4_lake_channel_coupling_np.int64)),
              "port_channel_index": _m4_lake_channel_coupling_readonly(_m4_lake_channel_coupling_np.array([p.channel_node_index for p in ports], _m4_lake_channel_coupling_np.int64)),
              "port_coefficient": _m4_lake_channel_coupling_readonly(_m4_lake_channel_coupling_np.array([p.coefficient_m3_s_m15 for p in ports], _m4_lake_channel_coupling_np.float64))}
    arrays.update({"domain_" + key: value for key, value in domain["arrays"].items()})
    arrays.update({"geometry_" + key: value for key, value in geometry["arrays"].items()})
    arrays.update({"network_" + key: _m4_lake_channel_coupling_np.asarray(getattr(network, key)).copy() for key in _m4_lake_channel_coupling_NETWORK_FIELDS})
    arrays.update({"trace_" + key: _m4_lake_channel_coupling_readonly(_m4_lake_channel_coupling_np.asarray(values)) for key, values in states.items()})
    for key, values in steps.items():
        count = len(values)
        if key == "stability_number":
            arrays["step_" + key] = _m4_lake_channel_coupling_readonly(_m4_lake_channel_coupling_np.asarray(values, _m4_lake_channel_coupling_np.float64))
        else:
            width = {"channel_q_m3_s": len(channel), "lake_internal_q_m3_s": len(domain["arrays"]["internal_faces"]),
                     "port_q_m3_s": len(ports), "boundary_q_m3_s": len(domain["arrays"]["boundary_faces"]),
                     "channel_donor_q_m3_s": len(channel), "lake_donor_q_m3_s": len(lake),
                     "channel_residual_m3": len(channel), "lake_residual_m3": len(lake)}[key]
            arrays["step_" + key] = _m4_lake_channel_coupling_readonly(_m4_lake_channel_coupling_np.asarray(values, _m4_lake_channel_coupling_np.float64).reshape(count, width))
    arrays["step_dt_seconds"] = _m4_lake_channel_coupling_readonly(_m4_lake_channel_coupling_np.diff(arrays["trace_time_seconds"]))
    metadata = {"schema": LAKE_CHANNEL_SCHEMA, "algorithm": LAKE_CHANNEL_ALGORITHM, "domain_metadata": domain["metadata"],
                "geometry_semantics": dict(_m4_lake_channel_coupling_GEOMETRY_SEMANTICS),
                "geometry_metadata": geometry["metadata"], "domain_identity_sha256": domain["identity_sha256"],
                "geometry_identity_sha256": geometry["identity_sha256"],
                "network_source_identity_sha256": network.source_identity_sha256,
                "network_section_source": network.section_source, "network_roughness_source": network.roughness_source,
                "forcing_source_identity_sha256": forcing.source_identity_sha256,
                "forcing_provenance": forcing.provenance,
                "ports": [_m4_lake_channel_coupling_asdict(port) for port in ports], "config": _m4_lake_channel_coupling_asdict(config),
                "status": "failed_prefix" if failure else "complete", "failure_reason": failure,
                "last_time_seconds": times[-1], "requested_end_time_seconds": float(forcing.time_seconds[-1]),
                "hydraulic_model": "finite_level_pool_signed_port_not_saint_venant",
                "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    if len(arrays) > 128 or any(any(axis > 8_000_000 for axis in value.shape) for value in arrays.values()) or sum(value.nbytes for value in arrays.values()) > LAKE_CHANNEL_MAX_BYTES:
        raise ValueError("lake-channel trace byte budget exceeded")
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_lake_channel_coupling_identity(arrays, metadata)}
    validate_lake_channel(result)
    return result

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:480 ---
def validate_lake_channel(bundle):
    from terrain_pipeline.common_infra import identity as _m4_lake_channel_coupling_identity
    from terrain_pipeline.channel_geometry import ARRAYS as _m4_lake_channel_coupling_GEOMETRY_ARRAYS
    from terrain_pipeline.surface_rivers.metric_channel_product import LEGACY_NETWORK_FIELDS as _m4_lake_channel_coupling_LEGACY_NETWORK_FIELDS
    from terrain_pipeline.surface_rivers.metric_channel_product import NETWORK_FIELDS as _m4_lake_channel_coupling_NETWORK_FIELDS
    from terrain_pipeline.channel_geometry import ChannelNetwork as _m4_lake_channel_coupling_ChannelNetwork
    from terrain_pipeline.channel_geometry import GEOMETRY_SEMANTICS as _m4_lake_channel_coupling_GEOMETRY_SEMANTICS
    from terrain_pipeline.channel_geometry import receiver_distances as _m4_lake_channel_coupling_receiver_distances
    if not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid lake-channel bundle")
    a, m = bundle["arrays"], bundle["metadata"]
    legacy = m.get("schema") == "terragenesis-natural-lake-channel-port-v1"
    fields = _m4_lake_channel_coupling_LEGACY_NETWORK_FIELDS if legacy else _m4_lake_channel_coupling_NETWORK_FIELDS
    if (m.get("schema") != ("terragenesis-natural-lake-channel-port-v1" if legacy else LAKE_CHANNEL_SCHEMA)
            or (not legacy and m.get("geometry_semantics") != _m4_lake_channel_coupling_GEOMETRY_SEMANTICS)
            or m.get("algorithm") != LAKE_CHANNEL_ALGORITHM or _m4_lake_channel_coupling_identity(a, m) != bundle["identity_sha256"]):
        raise ValueError("lake-channel identity mismatch")
    if len(a) > 128 or any(any(axis > 8_000_000 for axis in value.shape) for value in a.values()) or sum(value.nbytes for value in a.values()) > LAKE_CHANNEL_MAX_BYTES:
        raise ValueError("lake-channel byte budget exceeded")
    expected = ({"trace_time_seconds", "step_dt_seconds", "initial_channel_volume_m3",
                 "initial_lake_volume_m3", "port_face_index", "port_channel_index", "port_coefficient"}
                | {"forcing_" + key for key in FORCING_FIELDS}
                | {"trace_" + key for key in STATE_FIELDS}
                | {"step_" + key for key in STEP_FIELDS}
                | {"domain_" + key for key in LAKE_CHANNEL_DOMAIN_FIELDS}
                | {"geometry_" + key for key in _m4_lake_channel_coupling_GEOMETRY_ARRAYS}
                | {"network_" + key for key in fields})
    if set(a) != expected:
        raise ValueError("lake-channel array schema mismatch")
    if any(m[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("lake-channel certification flags invalid")
    domain_arrays = {key[7:]: value for key, value in a.items() if key.startswith("domain_")}
    geometry_arrays = {key[9:]: value for key, value in a.items() if key.startswith("geometry_")}
    domain = {"arrays": domain_arrays, "metadata": m["domain_metadata"], "identity_sha256": m["domain_identity_sha256"]}
    geometry = {"arrays": geometry_arrays, "metadata": m["geometry_metadata"], "identity_sha256": m["geometry_identity_sha256"]}
    values = {key: a["network_" + key] for key in fields}
    if legacy:
        values["receiver_distance_m"] = _m4_lake_channel_coupling_receiver_distances(geometry_arrays["node_xz_m"], values["receiver"])
    network = _m4_lake_channel_coupling_ChannelNetwork(**values,
                             source_identity_sha256=m["network_source_identity_sha256"],
                             section_source=m["network_section_source"], roughness_source=m["network_roughness_source"])
    forcing = LakeChannelForcing(a["forcing_time_seconds"], a["forcing_channel_local_q_m3_s"],
                                 a["forcing_lake_local_q_m3_s"], a["forcing_tailwater_stage_m"],
                                 m["forcing_source_identity_sha256"], m["forcing_provenance"])
    ports = tuple(LakeChannelPort(**entry) for entry in m["ports"])
    if (not _m4_lake_channel_coupling_np.array_equal(a["port_face_index"], [p.boundary_face_index for p in ports]) or
            not _m4_lake_channel_coupling_np.array_equal(a["port_channel_index"], [p.channel_node_index for p in ports]) or
            not _m4_lake_channel_coupling_np.array_equal(a["port_coefficient"], [p.coefficient_m3_s_m15 for p in ports])):
        raise ValueError("saved port mapping mismatch")
    config = LakeChannelConfig(**m["config"])
    nc, nl, nb = _checked_inputs(domain, geometry, network, ports, forcing,
                                 a["initial_channel_volume_m3"], a["initial_lake_volume_m3"], config)
    t = a["trace_time_seconds"]
    k = len(t) - 1
    if t.dtype != _m4_lake_channel_coupling_np.float64 or t.ndim != 1 or not _m4_lake_channel_coupling_np.isfinite(t).all() or _m4_lake_channel_coupling_np.any(_m4_lake_channel_coupling_np.diff(t) <= 0.) or t[0] != forcing.time_seconds[0] or k > config.max_steps:
        raise ValueError("invalid committed lake-channel times")
    if not _m4_lake_channel_coupling_np.array_equal(a["step_dt_seconds"], _m4_lake_channel_coupling_np.diff(t)):
        raise ValueError("saved step duration mismatch")
    if (not _m4_lake_channel_coupling_np.array_equal(a["trace_channel_volume_m3"][0], a["initial_channel_volume_m3"]) or
            not _m4_lake_channel_coupling_np.array_equal(a["trace_lake_volume_m3"][0], a["initial_lake_volume_m3"])):
        raise ValueError("initial water inventory mismatch")
    shapes = {"channel_volume_m3": (k + 1, nc), "lake_volume_m3": (k + 1, nl),
              "channel_stage_m": (k + 1, nc), "lake_stage_m": (k + 1, nl),
              "channel_depth_m": (k + 1, nc), "wet_support": (k + 1, len(domain_arrays["support_cell_ids"])),
              "wet_component": (k + 1, nl)}
    for name, shape in shapes.items():
        value = a["trace_" + name]
        expected_dtype = _m4_lake_channel_coupling_np.dtype(bool if name == "wet_support" else _m4_lake_channel_coupling_np.int64 if name == "wet_component" else _m4_lake_channel_coupling_np.float64)
        if value.shape != shape or value.dtype != expected_dtype or (value.dtype.kind == "f" and not _m4_lake_channel_coupling_np.isfinite(value).all()):
            raise ValueError("lake-channel state shape or finite mismatch")
    if _m4_lake_channel_coupling_np.any(a["trace_channel_volume_m3"] < -1e-10) or _m4_lake_channel_coupling_np.any(a["trace_lake_volume_m3"] < -1e-10):
        raise ValueError("negative saved water inventory")
    step_shapes = {"channel_q_m3_s": (k, nc), "lake_internal_q_m3_s": (k, len(domain_arrays["internal_faces"])),
                   "port_q_m3_s": (k, len(ports)), "boundary_q_m3_s": (k, nb),
                   "channel_donor_q_m3_s": (k, nc), "lake_donor_q_m3_s": (k, nl),
                   "channel_residual_m3": (k, nc), "lake_residual_m3": (k, nl),
                   "stability_number": (k,)}
    for name, shape in step_shapes.items():
        value = a["step_" + name]
        if value.shape != shape or value.dtype != _m4_lake_channel_coupling_np.float64 or not _m4_lake_channel_coupling_np.isfinite(value).all():
            raise ValueError("lake-channel step shape or finite mismatch")
    for i in range(k + 1):
        depth, cstage, lstage, wet, component = lakechannel_geometry(domain, network,
            a["trace_channel_volume_m3"][i], a["trace_lake_volume_m3"][i])
        for name, expected in (("channel_depth_m", depth), ("channel_stage_m", cstage),
                               ("lake_stage_m", lstage), ("wet_support", wet), ("wet_component", component)):
            equal = _m4_lake_channel_coupling_np.array_equal(a["trace_" + name][i], expected) if name in ("wet_support", "wet_component") else _m4_lake_channel_coupling_np.allclose(a["trace_" + name][i], expected, rtol=0., atol=1e-9)
            if not equal:
                raise ValueError("wet footprint or stage mismatch")
    for i in range(k):
        interval = min(int(_m4_lake_channel_coupling_np.searchsorted(forcing.time_seconds, t[i], side="right") - 1), len(forcing.time_seconds) - 2)
        if t[i + 1] > forcing.time_seconds[interval + 1] + 1e-10 or a["step_dt_seconds"][i] > config.max_dt_seconds * (1. + 1e-12):
            raise ValueError("step crosses forcing or max dt")
        chosen, chosen_dt, chosen_reason = _choose_step(domain, network, ports, forcing, config, t[i],
            a["trace_channel_volume_m3"][i], a["trace_lake_volume_m3"][i])
        if chosen_reason or not _m4_lake_channel_coupling_math.isclose(chosen_dt, a["step_dt_seconds"][i], rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("committed step differs from solver step selection")
        candidate, reason = _candidate(domain, network, ports, forcing, interval,
            a["step_dt_seconds"][i], a["trace_channel_volume_m3"][i], a["trace_lake_volume_m3"][i])
        if reason:
            raise ValueError("committed invalid water step: " + reason)
        if candidate["stability_number"] > config.cfl * (1. + 1e-12):
            raise ValueError("committed water donor stability bound exceeded")
        for name in STEP_FIELDS:
            if not _m4_lake_channel_coupling_np.allclose(a["step_" + name][i], candidate[name], rtol=0., atol=1e-9):
                raise ValueError("paired port or water ledger mismatch: " + name)
        for name in ("channel_volume_m3", "lake_volume_m3"):
            if not _m4_lake_channel_coupling_np.allclose(a["trace_" + name][i + 1], candidate[name], rtol=0., atol=1e-9):
                raise ValueError("next water inventory mismatch")
    if m["last_time_seconds"] != t[-1] or m["requested_end_time_seconds"] != forcing.time_seconds[-1]:
        raise ValueError("lake-channel time metadata mismatch")
    if m["status"] == "complete":
        if t[-1] != forcing.time_seconds[-1] or m["failure_reason"] is not None:
            raise ValueError("invalid complete lake-channel trace")
    elif m["status"] == "failed_prefix":
        if not m["failure_reason"] or t[-1] >= forcing.time_seconds[-1]:
            raise ValueError("invalid lake-channel failed prefix")
        if k >= config.max_steps:
            expected_failure = "maximum step count exceeded"
        elif lakechannel_trace_bytes(domain, geometry, network, ports, forcing, k + 1) > LAKE_CHANNEL_MAX_BYTES:
            expected_failure = "trace byte budget exhausted"
        else:
            _, _, expected_failure = _choose_step(domain, network, ports, forcing, config,
                t[-1], a["trace_channel_volume_m3"][-1], a["trace_lake_volume_m3"][-1])
        if expected_failure != m["failure_reason"]:
            raise ValueError("failed prefix lacks physical failure witness")
    else:
        raise ValueError("invalid lake-channel status")
    return True

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:604 ---
def save_lake_channel(path, bundle):
    from terrain_pipeline.common_infra import save_bundle as _m4_lake_channel_coupling_save_bundle
    _m4_lake_channel_coupling_save_bundle(path, bundle, validator=validate_lake_channel)

# --- terrain_pipeline/surface_rivers/metric_lake_channel_coupling.py:608 ---
def load_lake_channel(path, *, expected_sha256):
    from terrain_pipeline.common_infra import load_bundle as _m4_lake_channel_coupling_load_bundle
    return _m4_lake_channel_coupling_load_bundle(path, expected_sha256=expected_sha256, validator=validate_lake_channel, max_bytes=LAKE_CHANNEL_MAX_BYTES)

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:65 ---
MAX_HYPSOMETRY_CELLS = 65536

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:66 ---
SAMPLE_LEVELS = 64

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:74 ---
DEFAULT_AGGREGATE_CELLS = 3

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:77 ---
def _finite_positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, _m4_lake_hypsometry_np.integer, _m4_lake_hypsometry_np.floating)):
        raise ValueError(name + " must be numeric")
    value = float(value)
    if not _m4_lake_hypsometry_math.isfinite(value) or value <= 0.:
        raise ValueError(name + " must be finite positive")
    return value

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:86 ---
def depression_hierarchy(elevation_m, valid_mask=None, *, mesh=None, spacing_m=30., origin_xz_m=(0., 0.), world_seed=20261020):
    """Border-seeded priority flood.

    Returns `filled_m` (the level each cell would hold water at if the window
    border drains freely) and `fill_depth_m = filled - elevation`.

    The priority queue always expands the lowest known outlet first, so a cell's
    filled level is the minimum over all drainage paths to the border of the
    maximum elevation along that path. This is the standard fill; it is stated
    here because the lake support below relies on exactly this property.
    """
    from terrain_pipeline.drainage import grid_mesh as _m4_lake_hypsometry_grid_mesh
    from terrain_pipeline.drainage import route_graph as _m4_lake_hypsometry_route_graph
    bed = _m4_lake_hypsometry_np.asarray(elevation_m, _m4_lake_hypsometry_np.float64)
    if bed.ndim != 2 or bed.size < 4:
        raise ValueError("at least a 2x2 elevation field required")
    valid = _m4_lake_hypsometry_np.ones(bed.shape, bool) if valid_mask is None else _m4_lake_hypsometry_np.asarray(valid_mask, bool)
    if valid.shape != bed.shape or not valid.all():
        raise ValueError("a closed basin needs a fully valid window")
    if not _m4_lake_hypsometry_np.isfinite(bed).all():
        raise ValueError("finite elevation required")
    rows, columns = bed.shape
    border = _m4_lake_hypsometry_np.zeros((rows, columns), bool)
    border[[0, -1], :] = True
    border[:, [0, -1]] = True
    if mesh is None:
        mesh = _m4_lake_hypsometry_grid_mesh(bed.shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1],
                         dx_m=spacing_m, world_seed=world_seed)
    filled = _m4_lake_hypsometry_route_graph(bed, border, mesh).filled.reshape(bed.shape)
    return filled, filled - bed

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:116 ---
def depression_component(fill_depth_m, seed_rc, *, mesh=None):
    """Graph-connected positive-fill-depth component containing `seed_rc`."""
    from terrain_pipeline.drainage import grid_mesh as _m4_lake_hypsometry_grid_mesh
    depth = _m4_lake_hypsometry_np.asarray(fill_depth_m, _m4_lake_hypsometry_np.float64)
    if depth.ndim != 2:
        raise ValueError("2D fill depth required")
    row, column = (int(value) for value in seed_rc)
    if not (0 <= row < depth.shape[0] and 0 <= column < depth.shape[1]):
        raise ValueError("seed cell outside the field")
    wet = depth > 0.
    if not wet[row, column]:
        return None
    mesh = _m4_lake_hypsometry_grid_mesh(depth.shape) if mesh is None else mesh
    seen = _m4_lake_hypsometry_np.zeros(depth.size, bool)
    seed = row * depth.shape[1] + column
    seen[seed] = True
    stack = [seed]
    while stack:
        cell = stack.pop()
        for target in mesh.indices[mesh.indptr[cell]:mesh.indptr[cell + 1]]:
            if wet.ravel()[target] and not seen[target]:
                seen[target] = True
                stack.append(int(target))
    return seen.reshape(depth.shape)

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:141 ---
def hypsometry_curve(bed_elevation_m, cell_area_m2, levels_m):
    """A(h) and V(h) of an explicit bed population; terrain-only, no shape law.

    A(h) counts cells strictly below the level; V(h) integrates their depth.
    Both are step functions of the bed population, which is why they are
    reported on the same sorted beds the store itself uses.
    """
    beds = _m4_lake_hypsometry_np.sort(_m4_lake_hypsometry_np.asarray(bed_elevation_m, _m4_lake_hypsometry_np.float64))
    area = _finite_positive(cell_area_m2, "cell_area_m2")
    if beds.ndim != 1 or beds.size == 0 or not _m4_lake_hypsometry_np.isfinite(beds).all():
        raise ValueError("finite nonempty bed values required")
    levels = _m4_lake_hypsometry_np.asarray(levels_m, _m4_lake_hypsometry_np.float64)
    if levels.ndim != 1 or not _m4_lake_hypsometry_np.isfinite(levels).all():
        raise ValueError("finite level list required")
    areas = _m4_lake_hypsometry_np.zeros(levels.size, _m4_lake_hypsometry_np.float64)
    volumes = _m4_lake_hypsometry_np.zeros(levels.size, _m4_lake_hypsometry_np.float64)
    for index, level in enumerate(levels):
        count = int(_m4_lake_hypsometry_np.searchsorted(beds, level, side="left"))
        areas[index] = count * area
        volumes[index] = float(_m4_lake_hypsometry_np.maximum(level - beds[:count], 0.).sum() * area)
    return areas, volumes

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:164 ---
def contraction_evidence(levels_m, areas_m2):
    """How fast the water surface shrinks as the level falls; measured, not assumed.

    For consecutive level steps going **downward**, `dA/dh` should shrink with the
    level if the basin narrows toward its bottom. The reported numbers are the
    measured secant slopes of A(h); nothing here imposes their shape.
    """
    levels = _m4_lake_hypsometry_np.asarray(levels_m, _m4_lake_hypsometry_np.float64)
    areas = _m4_lake_hypsometry_np.asarray(areas_m2, _m4_lake_hypsometry_np.float64)
    if levels.shape != areas.shape or levels.ndim != 1 or levels.size < 3:
        raise ValueError("matching level and area vectors of length >= 3 required")
    if _m4_lake_hypsometry_np.any(_m4_lake_hypsometry_np.diff(levels) <= 0.):
        raise ValueError("levels must increase")
    order = _m4_lake_hypsometry_np.argsort(-levels)
    descending_levels = levels[order]
    descending_areas = areas[order]
    rows = []
    for upper in range(len(descending_levels) - 1):
        lower = upper + 1
        delta_h = float(descending_levels[upper] - descending_levels[lower])
        delta_a = float(descending_areas[upper] - descending_areas[lower])
        if delta_h <= 0.:
            continue
        rows.append({"from_level_m": float(descending_levels[upper]),
                     "to_level_m": float(descending_levels[lower]),
                     "delta_level_m": delta_h,
                     "area_loss_m2": delta_a,
                     "secant_dA_dh_m": delta_a / delta_h,
                     "upper_area_m2": float(descending_areas[upper]),
                     "lower_area_m2": float(descending_areas[lower])})
    return rows

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:198 ---
@_m4_lake_hypsometry_dataclass(frozen=True)
class TerrainLake:
    """A closed basin's storage, V(h) and A(h) taken from the terrain itself."""

    storage: LakeStorage
    basin_mask: _m4_lake_hypsometry_np.ndarray
    spill_level_m: float
    bed_min_m: float
    closed_basin: bool
    touches_window_border: bool
    provenance: dict

    @property
    def area_km2(self):
        return float(self.basin_mask.sum()) * self.storage.cell_area_m2[0] / 1e6

    @property
    def relief_m(self):
        return self.spill_level_m - self.bed_min_m

    @property
    def capacity_m3(self):
        return self.storage.capacity_m3

    def level_table(self, levels_m):
        """A(h)/V(h) straight from the store, so table and store cannot disagree."""
        rows = []
        for level in _m4_lake_hypsometry_np.asarray(levels_m, _m4_lake_hypsometry_np.float64):
            clamped = float(min(max(level, self.storage.min_stage_m), self.storage.max_stage_m))
            rows.append({"stage_m": float(level), "clamped_stage_m": clamped,
                         "area_m2": self.storage.surface_area_at_stage(clamped),
                         "volume_m3": self.storage.volume_at_stage(clamped)})
        return rows

    def identity_sha256(self):
        return _m4_lake_hypsometry_identity({"basin_mask": self.basin_mask},
                        dict(self.provenance, spill_level_m=self.spill_level_m,
                             bed_min_m=self.bed_min_m,
                             store=self.storage.identity_sha256()
                             if hasattr(self.storage, "identity_sha256") else None))

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:239 ---
def build_terrain_lake(elevation_m, origin_xz_m, spacing_m, seed_cell_rc, *,
                       source_identity_sha256, max_cells=MAX_HYPSOMETRY_CELLS):
    """Derive one closed-basin lake store from a 30 m terrain page.

    `seed_cell_rc` is the (row, column) of the cell whose basin is wanted -- in
    practice the terminal cell of the reach. The function never guesses: if that
    cell is not inside a closed depression it returns `closed_basin=False` with
    the reason, instead of falling back to a vertical wall.
    """
    from terrain_pipeline.common_infra import readonly as _m4_lake_hypsometry_readonly
    from terrain_pipeline.drainage import grid_mesh as _m4_lake_hypsometry_grid_mesh
    bed = _m4_lake_hypsometry_np.asarray(elevation_m, _m4_lake_hypsometry_np.float64)
    if bed.ndim != 2 or bed.size < 16:
        raise ValueError("at least a 4x4 elevation field required")
    spacing = _finite_positive(spacing_m, "spacing_m")
    origin = _m4_lake_hypsometry_np.asarray(origin_xz_m, _m4_lake_hypsometry_np.float64).reshape(-1)
    if origin.size != 2 or not _m4_lake_hypsometry_np.isfinite(origin).all():
        raise ValueError("finite [x, z] origin required")
    limit = int(max_cells)
    if limit < 4 or limit > MAX_HYPSOMETRY_CELLS:
        raise ValueError("max_cells must be 4..%d" % MAX_HYPSOMETRY_CELLS)
    mesh = _m4_lake_hypsometry_grid_mesh(bed.shape, x0_m=origin[0], z0_m=origin[1], dx_m=spacing)
    filled, depth = depression_hierarchy(bed, mesh=mesh)
    row, column = (int(value) for value in seed_cell_rc)
    if not (0 <= row < bed.shape[0] and 0 <= column < bed.shape[1]):
        raise ValueError("seed cell outside the field")
    mask = depression_component(depth, (row, column), mesh=mesh)
    if mask is None:
        return TerrainLake(
            storage=None, basin_mask=_m4_lake_hypsometry_readonly(_m4_lake_hypsometry_np.zeros(bed.shape, bool)), spill_level_m=float("nan"),
            bed_min_m=float(bed[row, column]), closed_basin=False, touches_window_border=False,
            provenance={"schema": "terrain-lake-hypsometry-v1", "status": "seed cell drains",
                        "seed_row_column": [row, column],
                        "seed_elevation_m": float(bed[row, column]),
                        "max_cell_area_m2": spacing * spacing,
                        "reason": ("the seed cell has zero fill depth: its drainage path to the "
                                   "window border never rises, so there is no depression to fill"),
                        "source_identity_sha256": source_identity_sha256})
    count = int(mask.sum())
    if count > limit:
        raise ValueError("basin of %d cells exceeds the %d-cell store limit" % (count, limit))
    cells = _m4_lake_hypsometry_np.flatnonzero(mask.ravel()).astype(_m4_lake_hypsometry_np.int64)
    beds = _m4_lake_hypsometry_np.ascontiguousarray(bed.ravel()[cells], _m4_lake_hypsometry_np.float64)
    areas = _m4_lake_hypsometry_np.full(cells.size, spacing * spacing, _m4_lake_hypsometry_np.float64)
    bed_min = float(beds.min())
    spill = float(filled[mask].max())
    if not spill > bed_min:
        raise ValueError("degenerate basin: spill level does not exceed the bed")
    touches = _touches_border(mask)
    minimum_index = int(_m4_lake_hypsometry_np.argmin(beds))
    storage = LakeStorage(
        cell_ids=cells, bed_elevation_m=beds, cell_area_m2=areas,
        seed_cell_id=int(cells[minimum_index]), max_stage_m=spill,
        source_identity_sha256=source_identity_sha256,
        footprint_policy=("closed_depression_30m_cells; A(h) and V(h) are the terrain's own "
                          "hypsometry over %d cells at %.3f m; no shape function is imposed" % (
                              count, spacing)))
    provenance = {
        "schema": "terrain-lake-hypsometry-v1", "status": "closed_basin",
        "seed_row_column": [row, column], "seed_elevation_m": float(bed[row, column]),
        "basin_cells": count, "basin_area_m2": float(count * spacing * spacing),
        "bed_min_m": bed_min, "spill_level_m": spill, "relief_m": spill - bed_min,
        "touches_window_border": touches,
        "closed_basin_within_window": not touches,
        "support_policy": ("one store cell per %0.3f m terrain cell inside the drainage "
                           "depression of the seed cell" % spacing),
        "max_stage_policy": "spill level from the border-seeded priority flood",
        "shape_law": None,
        "source_identity_sha256": source_identity_sha256,
        "origin_xz_m": [float(origin[0]), float(origin[1])]}
    return TerrainLake(storage=storage, basin_mask=_m4_lake_hypsometry_readonly(mask), spill_level_m=spill,
                       bed_min_m=bed_min, closed_basin=not touches,
                       touches_window_border=touches, provenance=provenance)

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:312 ---
def sampled_levels(min_level_m, max_level_m, count=SAMPLE_LEVELS):
    """Uniform level list on [min, max]; the store clamps and rejects as it must."""
    low = float(min_level_m)
    high = float(max_level_m)
    if not (_m4_lake_hypsometry_math.isfinite(low) and _m4_lake_hypsometry_math.isfinite(high)) or not high > low:
        raise ValueError("increasing finite levels required")
    n = int(count)
    if n < 3:
        raise ValueError("at least 3 sample levels required")
    return _m4_lake_hypsometry_np.linspace(low, high, n)

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:345 ---
CONVERGENCE_LEVEL_TOLERANCE = 1e-3

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:346 ---
CONVERGENCE_AREA_TOLERANCE = 1e-3

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:347 ---
CONVERGENCE_SIZES = (513, 1025, 1537, 2049)

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:350 ---
def _touches_border(mask):
    """Does the depression run into the window edge?

    Border cells are seeds of the flood and therefore always have zero fill
    depth, so they are never *in* the component. What matters is whether the
    component comes within one cell of the edge: then its rim is outside the
    page and its spill level is the window edge, not a real saddle.

    The nearest ring of a depression whose rim is outside the page is the ring at
    index 1 / -2, not the border itself. Testing the border ring would always
    return False, because no border cell can ever carry fill depth -- that was a
    real bug here, caught by
    `test_a_basin_larger_than_the_window_is_reported_as_not_closed`.
    """
    inner = _m4_lake_hypsometry_np.zeros(mask.shape, bool)
    inner[2:-2, 2:-2] = True
    return bool((_m4_lake_hypsometry_np.asarray(mask, bool) & ~inner).any())

# --- terrain_pipeline/surface_rivers/metric_lake_hypsometry.py:369 ---
def sampled_window_basin(lake_xz_m, sizes, spacing_m, sampler):
    """Measure one basin in growing centred windows and report the convergence.

    `sampler(origin_xz_m, shape)` must return the elevation field of that window
    from **absolute world coordinates** -- that is what makes the comparison
    meaningful, because then a value at a coordinate cannot depend on which
    window asked for it.

    Convergence rule (asserted by the test suite as well): the two largest
    windows must agree to `CONVERGENCE_LEVEL_TOLERANCE` of the spill relief and
    `CONVERGENCE_AREA_TOLERANCE` of the basin area. Only then is the answer
    accepted; otherwise `converged=False` comes back with the measured numbers
    and the caller is expected to enlarge the window, not to report the
    truncated one.
    """
    spacing = _finite_positive(spacing_m, "spacing_m")
    lake = _m4_lake_hypsometry_np.asarray(lake_xz_m, _m4_lake_hypsometry_np.float64).reshape(-1)
    if lake.size != 2 or not _m4_lake_hypsometry_np.isfinite(lake).all():
        raise ValueError("finite [x, z] lake position required")
    shape_sizes = [int(value) for value in sizes]
    if len(shape_sizes) < 2 or any(value < 8 for value in shape_sizes):
        raise ValueError("at least two windows of 8 cells or more required")
    centre_column = int(round(lake[0] / spacing))
    centre_row = int(round(lake[1] / spacing))
    records = []
    for size in shape_sizes:
        origin_column = centre_column - size // 2
        origin_row = centre_row - size // 2
        origin = (origin_column * spacing, origin_row * spacing)
        field = _m4_lake_hypsometry_np.ascontiguousarray(_m4_lake_hypsometry_np.asarray(sampler(origin, (size, size)), _m4_lake_hypsometry_np.float64))
        seed_rc = (centre_row - origin_row, centre_column - origin_column)
        filled, depth = depression_hierarchy(field)
        mask = depression_component(depth, seed_rc)
        if mask is None:
            record = {"size": size, "window_km": size * spacing / 1000.0,
                      "origin_xz_m": [float(origin[0]), float(origin[1])],
                      "seed_row_column": [int(seed_rc[0]), int(seed_rc[1])],
                      "closed_basin": False, "touches_window_border": False,
                      "basin_cells": 0, "basin_area_m2": 0.0,
                      "bed_min_m": float(field[seed_rc]), "spill_level_m": float("nan"),
                      "seed_elevation_m": float(field[seed_rc])}
        else:
            record = {"size": size, "window_km": size * spacing / 1000.0,
                      "origin_xz_m": [float(origin[0]), float(origin[1])],
                      "seed_row_column": [int(seed_rc[0]), int(seed_rc[1])],
                      "closed_basin": True,
                      "touches_window_border": _touches_border(mask),
                      "basin_cells": int(mask.sum()),
                      "basin_area_m2": float(mask.sum()) * spacing * spacing,
                      "bed_min_m": float(field[mask].min()),
                      "spill_level_m": float(filled[mask].max()),
                      "seed_elevation_m": float(field[seed_rc])}
        records.append(record)

    last, previous = records[-1], records[-2]
    if not (last["closed_basin"] and previous["closed_basin"]):
        return {"converged": False, "reason": "a candidate window is not a closed basin",
                "records": records, "accepted": last,
                "tolerances": {"level": CONVERGENCE_LEVEL_TOLERANCE,
                               "area": CONVERGENCE_AREA_TOLERANCE}}
    relief = last["spill_level_m"] - last["bed_min_m"]
    level_change = abs(last["spill_level_m"] - previous["spill_level_m"])
    area_change = abs(last["basin_area_m2"] - previous["basin_area_m2"])
    level_relative = level_change / relief if relief > 0. else float("inf")
    area_relative = area_change / last["basin_area_m2"] if last["basin_area_m2"] > 0. else float("inf")
    converged = bool(level_relative <= CONVERGENCE_LEVEL_TOLERANCE
                     and area_relative <= CONVERGENCE_AREA_TOLERANCE)
    return {"converged": converged,
            "level_change_m": level_change, "level_relative": level_relative,
            "area_change_m2": area_change, "area_relative": area_relative,
            "tolerances": {"level": CONVERGENCE_LEVEL_TOLERANCE,
                           "area": CONVERGENCE_AREA_TOLERANCE},
            "records": records, "accepted": last,
            "reason": None if converged else
                      "the two largest windows still disagree; enlarge the window before reporting"}

# --- terrain_pipeline/surface_rivers/world_reach_lake.py:37 ---
DESIGN_RUNOFF_MM_H = 1.

# --- terrain_pipeline/surface_rivers/world_reach_lake.py:38 ---
WIDTH_EXPONENT = .5

# --- terrain_pipeline/surface_rivers/world_reach_lake.py:39 ---
GRAVITY_M_S2 = 9.80665

# --- terrain_pipeline/surface_rivers/world_reach_lake.py:42 ---
def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, _m4_world_reach_lake_np.integer, _m4_world_reach_lake_np.floating)):
        raise ValueError(name + " must be numeric")
    value = float(value)
    if not _m4_world_reach_lake_math.isfinite(value) or value <= 0.:
        raise ValueError(name + " must be finite positive")
    return value

# --- terrain_pipeline/surface_rivers/world_reach_lake.py:51 ---
def design_discharge_m3_s(contributing_area_m2, *, design_runoff_mm_h=DESIGN_RUNOFF_MM_H):
    """Node design discharge from contributing area (repository runoff convention)."""
    area = _m4_world_reach_lake_np.asarray(contributing_area_m2, _m4_world_reach_lake_np.float64)
    if area.ndim != 1 or not _m4_world_reach_lake_np.isfinite(area).all() or _m4_world_reach_lake_np.any(area <= 0.):
        raise ValueError("finite positive contributing area per node required")
    runoff = _positive(design_runoff_mm_h, "design_runoff_mm_h")
    return area * runoff / 1000. / 3600.

# --- terrain_pipeline/surface_rivers/world_reach_lake.py:60 ---
def channel_width_m(contributing_area_m2, *, reference_discharge_m3_s, reference_width_m,
                    min_width_m, max_width_m, design_runoff_mm_h=DESIGN_RUNOFF_MM_H,
                    width_exponent=WIDTH_EXPONENT):
    """`ChannelRecipe` width law applied per node: W = clip(W_ref*(Q/Q_ref)**b).

    Returns (width_m, design_q_m3_s). Areas are the contributing *cell* footprints
    of the selected reach, so width increases monotonically with catchment size.

    This is the flow-only law. `channel_width_from_lithology_m` is the one the
    reach builder uses now: the project's own stated rule is that width comes from
    discharge **and** rock hardness together, developed from erosion, so a
    flow-only width drops half of the original specification.
    """
    q = design_discharge_m3_s(contributing_area_m2, design_runoff_mm_h=design_runoff_mm_h)
    reference_q = _positive(reference_discharge_m3_s, "reference_discharge_m3_s")
    reference_w = _positive(reference_width_m, "reference_width_m")
    low = _positive(min_width_m, "min_width_m")
    high = _positive(max_width_m, "max_width_m")
    if high < low:
        raise ValueError("maximum width must exceed minimum width")
    exponent = float(width_exponent)
    if not _m4_world_reach_lake_math.isfinite(exponent) or exponent < 0.:
        raise ValueError("nonnegative finite width exponent required")
    ratio = q / reference_q
    return _m4_world_reach_lake_np.clip(reference_w * ratio ** exponent, low, high), q

# --- terrain_pipeline/surface_rivers/world_reach_lake.py:87 ---
def channel_width_from_lithology_m(contributing_area_m2, bed_hardness, bank_hardness, *,
                                   reference_discharge_m3_s, reference_width_m,
                                   min_width_m, max_width_m,
                                   design_runoff_mm_h=DESIGN_RUNOFF_MM_H,
                                   width_exponent=WIDTH_EXPONENT,
                                   bed_lateral_factor=1.5, bank_lateral_factor=1.5):
    """Width from discharge **and** rock hardness, reusing the repository erosion rule.

    The law is the one already implemented in
    `metric_discharge_geometry.build_discharge_geometry`, copied here rather than
    re-derived so the reach and the older geometry path cannot disagree:

        W = W_ref * (Q/Q_ref)**b * (1 + a_bed * h_bed) * (0.5 + a_bank * (1 - h_bank))

    with `a_bed = a_bank = 1.5`. Its stated intent is that a hard bed directs work
    sideways (wider), while a resistant bank resists widening. Values are the
    geology table's `bed_hardness` / `bank_hardness` in [0, 1], sampled at the
    node's absolute world coordinate, so a granite reach and a shale reach with the
    same discharge are not forced to the same width.

    `min_width_m` / `max_width_m` still clamp, because the 30 m base cannot carry a
    sub-cell channel; the clamp is reported by the caller, not hidden here.
    """
    q = design_discharge_m3_s(contributing_area_m2, design_runoff_mm_h=design_runoff_mm_h)
    reference_q = _positive(reference_discharge_m3_s, "reference_discharge_m3_s")
    reference_w = _positive(reference_width_m, "reference_width_m")
    low = _positive(min_width_m, "min_width_m")
    high = _positive(max_width_m, "max_width_m")
    if high < low:
        raise ValueError("maximum width must exceed minimum width")
    exponent = float(width_exponent)
    if not _m4_world_reach_lake_math.isfinite(exponent) or exponent < 0.:
        raise ValueError("nonnegative finite width exponent required")
    bed = _m4_world_reach_lake_np.asarray(bed_hardness, _m4_world_reach_lake_np.float64)
    bank = _m4_world_reach_lake_np.asarray(bank_hardness, _m4_world_reach_lake_np.float64)
    if bed.shape != q.shape or bank.shape != q.shape:
        raise ValueError("one hardness pair per node required")
    if not (_m4_world_reach_lake_np.isfinite(bed).all() and _m4_world_reach_lake_np.isfinite(bank).all()):
        raise ValueError("finite hardness required")
    if _m4_world_reach_lake_np.any(bed < 0.) or _m4_world_reach_lake_np.any(bed > 1.) or _m4_world_reach_lake_np.any(bank < 0.) or _m4_world_reach_lake_np.any(bank > 1.):
        raise ValueError("hardness must lie in [0, 1]")
    lateral = (1. + float(bed_lateral_factor) * bed) * (
        .5 + float(bank_lateral_factor) * (1. - bank))
    raw = reference_w * (q / reference_q) ** exponent * lateral
    return _m4_world_reach_lake_np.clip(raw, low, high), q

# --- terrain_pipeline/surface_rivers/world_reach_lake.py:134 ---
def sill_coefficient_m3_s_m15(sill_width_m, *, discharge_coefficient=.4):
    """Broad-crested weir `Q = Cd*sqrt(2g)*L*h**1.5` lumped into one `LakeOutlet` C.

        `LakeOutlet` documents its coefficient as `m3 s-1 m-1.5`; multiplying the
    per-metre weir law by the sill length keeps that unit and makes the number
    auditable instead of tuned.
    """
    width = _positive(sill_width_m, "sill_width_m")
    cd = _positive(discharge_coefficient, "discharge_coefficient")
    return cd * _m4_world_reach_lake_math.sqrt(2. * GRAVITY_M_S2) * width

# --- terrain_pipeline/surface_rivers/world_reach_lake.py:147 ---
@_m4_world_reach_lake_dataclass(frozen=True)
class SillLake:
    storage: LakeStorage
    outlets: tuple
    seed_cell_id: int
    sill_stage_m: float
    secondary_sill: dict | None
    provenance: dict

    @property
    def bed_elevation_m(self):
        return float(self.storage.bed_elevation_m[0])

    @property
    def sill_depth_m(self):
        return self.sill_stage_m - self.bed_elevation_m

    def volume_at_sill_m3(self):
        return self.storage.volume_at_stage(self.sill_stage_m)

    def capacity_m3(self):
        return self.storage.capacity_m3

# --- terrain_pipeline/surface_rivers/world_reach_lake.py:170 ---
def build_sill_lake(*, cell_ids, bed_elevation_m, cell_area_m2, seed_cell_id, sill_stage_m,
                    head_allowance_m, sill_width_m, source_identity_sha256, primary_target_xz_m,
                    secondary_sill=None, discharge_coefficient=.4, provenance):
    """Build the level-pool store and its saddle ratings from declared inputs.

    `secondary_sill` is an optional dict with `stage_m`, `width_m`, `target_xz_m` for
    a second, higher saddle; it is represented as a second `LakeOutlet` and reports
    zero outflow whenever the stage stays below its crest.
    """
    ids = _m4_world_reach_lake_np.asarray(cell_ids, _m4_world_reach_lake_np.int64)
    bed = _m4_world_reach_lake_np.asarray(bed_elevation_m, _m4_world_reach_lake_np.float64)
    area = _m4_world_reach_lake_np.asarray(cell_area_m2, _m4_world_reach_lake_np.float64)
    if ids.shape != bed.shape or ids.shape != area.shape:
        raise ValueError("lake support arrays must share one shape")
    allowance = _positive(head_allowance_m, "head_allowance_m")
    sill = float(sill_stage_m)
    if not _m4_world_reach_lake_math.isfinite(sill):
        raise ValueError("finite sill stage required")
    coefficient = sill_coefficient_m3_s_m15(sill_width_m, discharge_coefficient=discharge_coefficient)
    storage = LakeStorage(
        cell_ids=ids, bed_elevation_m=bed, cell_area_m2=area, seed_cell_id=int(seed_cell_id),
        max_stage_m=sill + allowance, source_identity_sha256=source_identity_sha256,
        footprint_policy=("single_coarse_cell_level_pool_tank_at_native_tile_spacing;"
                          "stage above the saddle is the declared weir head, not an expanded wetted footprint"))
    if storage.volume_at_stage(storage.min_stage_m) != 0.:
        raise ValueError("sill lake must start from a dry support")
    outlets = [LakeOutlet(0, -1, sill, coefficient,
                          "broad-crested sill: Cd=%.3f, sqrt(2g), sill width %.1f m; "
                          "spills out of the modelled reach to %s" % (discharge_coefficient,
                                                                     float(sill_width_m),
                                                                     list(primary_target_xz_m)))]
    secondary = None
    if secondary_sill is not None:
        crest = float(secondary_sill["stage_m"])
        width = _positive(secondary_sill["width_m"], "secondary sill width_m")
        outlets.append(LakeOutlet(0, -1, crest, sill_coefficient_m3_s_m15(width, discharge_coefficient=discharge_coefficient),
                                  "declared secondary saddle %s, higher than the primary sill" %
                                  (list(secondary_sill["target_xz_m"]),)))
        secondary = dict(stage_m=crest, width_m=width, target_xz_m=list(secondary_sill["target_xz_m"]),
                         coefficient_m3_s_m15=outlets[-1].coefficient_m3_s_m15)
    return SillLake(storage=storage, outlets=tuple(outlets), seed_cell_id=int(seed_cell_id),
                    sill_stage_m=sill, secondary_sill=secondary,
                    provenance=dict(provenance, discharge_coefficient=float(discharge_coefficient),
                                    head_allowance_m=allowance,
                                    primary_sill_width_m=float(sill_width_m),
                                    primary_target_xz_m=list(primary_target_xz_m)))

# --- terrain_pipeline/surface_rivers/world_reach_lake.py:218 ---
def integrate_sill_lake(lake, inflow_volume_m3, dt_seconds, *, initial_volume_m3):
    """March the level-pool lake with an explicit storage/spill split.

    `inflow_volume_m3[k]` is the volume the existing aqueous solver moved out of the
    reach terminal during step `k`; it is never rescaled. Spill is the sum of the
    existing `LakeOutlet` ratings at the resolved stage, capped by the volume that is
    actually there, so no step can spill water it does not hold. The ledger closes to
    floating-point round-off by construction.
    """
    inflow = _m4_world_reach_lake_np.asarray(inflow_volume_m3, _m4_world_reach_lake_np.float64)
    dt = _m4_world_reach_lake_np.asarray(dt_seconds, _m4_world_reach_lake_np.float64)
    if inflow.ndim != 1 or dt.ndim != 1 or inflow.shape != dt.shape or inflow.size == 0:
        raise ValueError("matching nonempty inflow and dt series required")
    if not _m4_world_reach_lake_np.isfinite(inflow).all() or not _m4_world_reach_lake_np.isfinite(dt).all() or _m4_world_reach_lake_np.any(inflow < 0.) or _m4_world_reach_lake_np.any(dt <= 0.):
        raise ValueError("finite nonnegative inflow and positive dt required")
    capacity = lake.storage.capacity_m3
    volume = float(initial_volume_m3)
    if not _m4_world_reach_lake_math.isfinite(volume) or volume < 0. or volume > capacity:
        raise ValueError("initial lake volume outside declared finite support")
    stages = _m4_world_reach_lake_np.empty(inflow.size + 1)
    volumes = _m4_world_reach_lake_np.empty(inflow.size + 1)
    areas = _m4_world_reach_lake_np.empty(inflow.size + 1)
    spills = _m4_world_reach_lake_np.empty((inflow.size, len(lake.outlets)))
    stages[0] = lake.storage.stage_at_volume(volume)
    volumes[0] = volume
    areas[0] = lake.storage.surface_area_at_stage(stages[0])
    for step in range(inflow.size):
        volume += float(inflow[step])
        if volume > capacity + 1e-6:
            raise ValueError("lake exceeds declared finite support: raise the declared weir head allowance")
        stage = lake.storage.stage_at_volume(min(volume, capacity))
        rate = _m4_world_reach_lake_np.array([outlet.discharge_at_stage(stage) for outlet in lake.outlets], _m4_world_reach_lake_np.float64)
        spilled = rate * dt[step]
        total = float(spilled.sum())
        if total > volume:
            spilled = spilled * (volume / total) if total > 0. else _m4_world_reach_lake_np.zeros_like(spilled)
            total = volume
        volume -= total
        spills[step] = spilled
        stages[step + 1] = lake.storage.stage_at_volume(volume)
        volumes[step + 1] = volume
        areas[step + 1] = lake.storage.surface_area_at_stage(stages[step + 1])
    total_spill = float(spills.sum())
    ledger = dict(initial_m3=float(initial_volume_m3), inflow_m3=float(inflow.sum()),
                  spill_m3=total_spill, final_m3=float(volumes[-1]),
                  residual_m3=float(initial_volume_m3 + inflow.sum() - total_spill - volumes[-1]))
    return dict(time_edges_seconds=_m4_world_reach_lake_np.concatenate(([0.], _m4_world_reach_lake_np.cumsum(dt))),
                stage_m=stages, volume_m3=volumes, surface_area_m2=areas,
                inflow_volume_m3=inflow, spill_volume_m3=spills,
                outlet_spill_m3=spills.sum(axis=0), dt_seconds=dt, ledger=ledger)

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:125 ---
NATIVE_30M_LAKE_SCHEMA = "terrain-pipeline-native-30m-lake-v1"

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:126 ---
NATIVE_30M_LAKE_ALGORITHM = "native-30m-irregular-terrain-hypsometry-level-pool-v2"

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:130 ---
BED_SURFACE_KIND = "bed_elevation_m"

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:131 ---
WATER_SURFACE_KINDS = ("water_surface_m", "stage_m", "filled_surface_m")

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:133 ---
REASON_CERTIFIED = "certified_closed_basin_lowest_saddle"

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:134 ---
REASON_NO_DEPRESSION = "no_depression_at_seed"

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:135 ---
REASON_WINDOW_UNRESOLVED = "window_not_fully_resolved"

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:136 ---
REASON_RIM_IN_BAND = "rim_inside_untrusted_band"

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:137 ---
REASON_SADDLE_IN_BAND = "exit_set_inside_untrusted_band"

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:138 ---
REASON_SADDLE_ABSENT = "basin_has_no_exit_cell"

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:139 ---
REASON_FILL_NOT_CONSTANT = "flood_level_not_constant_over_basin"

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:140 ---
REASON_UPSTREAM_UNKNOWN = "upstream_unknown_in_catchment"

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:141 ---
REASON_MEMBERSHIP_LEAK = "basin_membership_not_self_draining"

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:143 ---
REASON_CODES = (REASON_CERTIFIED, REASON_NO_DEPRESSION, REASON_WINDOW_UNRESOLVED,
                REASON_RIM_IN_BAND, REASON_SADDLE_IN_BAND, REASON_SADDLE_ABSENT,
                REASON_FILL_NOT_CONSTANT, REASON_UPSTREAM_UNKNOWN,
                REASON_MEMBERSHIP_LEAK)

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:150 ---
TRUNCATION_REASONS = (REASON_WINDOW_UNRESOLVED, REASON_RIM_IN_BAND, REASON_SADDLE_IN_BAND,
                      REASON_SADDLE_ABSENT, REASON_FILL_NOT_CONSTANT,
                      REASON_UPSTREAM_UNKNOWN, REASON_MEMBERSHIP_LEAK)

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:154 ---
UNITS = {
    "elevation_m": "m (the supplied bed's own vertical datum)",
    "stage_m": "m",
    "level_m": "m",
    "area_m2": "m2",
    "volume_m3": "m3",
    "time_seconds": "s (physical seconds)",
    "discharge_m3_s": "m3 s-1",
    "outlet_coefficient_m3_s_m15": "m3 s-1 m-1.5 (Q = C * head ** 1.5)",
    "spacing_m": "m (native 30 m; cell area = spacing ** 2)",
    "cells": "cell count at the declared spacing, not an area",
}

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:170 ---
LEVEL_TOLERANCE_M = 1e-9

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:171 ---
LEDGER_RELATIVE_TOLERANCE = 1e-12

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:173 ---
TOLERANCES = {
    "flood_level_constancy_m": LEVEL_TOLERANCE_M,
    "exit_level_agreement_m": LEVEL_TOLERANCE_M,
    "level_round_trip_m": 1e-9,
    "volume_round_trip_relative": 1e-12,
    "ledger_residual_relative": LEDGER_RELATIVE_TOLERANCE,
}

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:181 ---
MAX_FIELD_CELLS = _m4_native_30m_lakes_MAX_GATE_CELLS

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:182 ---
MAX_MARCH_STEPS = 200_000

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:183 ---
MAX_TRACE_BYTES = 64 * 1024 * 1024

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:185 ---
BUDGETS = {
    "max_field_cells": MAX_FIELD_CELLS,
    "max_basin_cells": MAX_HYPSOMETRY_CELLS,
    "max_march_steps": MAX_MARCH_STEPS,
    "max_trace_bytes": MAX_TRACE_BYTES,
}

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:197 ---
def native30_finite_number(value, name):
    if (isinstance(value, (bool, _m4_native_30m_lakes_np.bool_))
            or not isinstance(value, (int, float, _m4_native_30m_lakes_np.integer, _m4_native_30m_lakes_np.floating))
            or not _m4_native_30m_lakes_math.isfinite(float(value))):
        raise ValueError(name + " must be finite numeric")
    return float(value)

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:205 ---
def _positive_number(value, name):
    number = native30_finite_number(value, name)
    if number <= 0.:
        raise ValueError(name + " must be finite positive")
    return number

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:212 ---
def native30_sha(value, name):
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ValueError(name + " must be a lowercase SHA256")
    return value

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:219 ---
def _bed(elevation_m):
    bed = _m4_native_30m_lakes_np.asarray(elevation_m, _m4_native_30m_lakes_np.float64)
    if bed.ndim != 2 or min(bed.shape) < 3:
        raise ValueError("a 2D bed of at least 3x3 cells is required")
    if bed.size > MAX_FIELD_CELLS:
        raise ValueError("field of %d cells exceeds the declared budget of %d"
                         % (bed.size, MAX_FIELD_CELLS))
    if not _m4_native_30m_lakes_np.isfinite(bed).all():
        raise ValueError("finite elevation required: an unknown cell must be declared "
                         "through resolved_mask, never through NaN, which would let a "
                         "hole decide a path")
    return bed

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:233 ---
def _mask(resolved_mask, shape):
    mask = _m4_native_30m_lakes_np.asarray(resolved_mask)
    if mask.dtype != _m4_native_30m_lakes_np.bool_ or mask.shape != shape:
        raise ValueError("a boolean resolved_mask of the bed's shape is required")
    if not mask.any():
        raise ValueError("no resolved cells: an all-unknown window has no basin")
    return mask

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:242 ---
def _seed(seed_cell_rc, shape):
    row, column = (int(value) for value in seed_cell_rc)
    if not (0 <= row < shape[0] and 0 <= column < shape[1]):
        raise ValueError("seed cell outside the field")
    return row, column

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:249 ---
def _graph_rim(mask, mesh):
    out = _m4_native_30m_lakes_np.zeros_like(mask)
    for cell in _m4_native_30m_lakes_np.flatnonzero(mask.ravel()):
        out.ravel()[mesh.indices[mesh.indptr[cell]:mesh.indptr[cell + 1]]] = True
    return out & ~mask

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:259 ---
def measure_basin(elevation_m, seed_cell_rc, *, mesh=None):
    """The seed cell's drainage depression: filled level, fill depth, member mask.

    Reuses ``metric_lake_hypsometry``. The returned mask is that module's
    graph-connected positive-fill-depth component -- the basin's **member** set, not
    "every cell below the spill level", which would also include the plateau
    outside the rim.

    Returns ``(filled_m, fill_depth_m, basin_mask_or_None)``.
    """
    from terrain_pipeline.drainage import grid_mesh as _m4_native_30m_lakes_grid_mesh
    bed = _bed(elevation_m)
    seed = _seed(seed_cell_rc, bed.shape)
    mesh = _m4_native_30m_lakes_grid_mesh(bed.shape) if mesh is None else mesh
    filled, depth = depression_hierarchy(bed, mesh=mesh)
    mask = depression_component(depth, seed, mesh=mesh)
    return filled, depth, mask

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:277 ---
def lowest_saddle(elevation_m, filled_m, basin_mask, spill_level_m,
                  tolerance_m=LEVEL_TOLERANCE_M, *, mesh=None):
    """The exit set of a basin, and the two saddle numbers kept apart.

    ``spill_level_m`` is the flood's own level on the basin, and the exit set is the
    graph-adjacent nodes outside the basin whose ``filled`` equals it exactly. Those are
    the crossings water actually uses, and their presence is the proof that the
    level is a saddle and not the window edge.

    ``geometric_rim_minimum_m`` is the number this module **rejects**: the lowest
    *bed* on the rim. It is reported with its measured difference so a reader can see
    it was considered, and so the 77 % of depressions where it is below the true
    level cannot be quietly re-adopted later.
    """
    from terrain_pipeline.common_infra import readonly as _m4_native_30m_lakes_readonly
    from terrain_pipeline.drainage import grid_mesh as _m4_native_30m_lakes_grid_mesh
    bed = _m4_native_30m_lakes_np.asarray(elevation_m, _m4_native_30m_lakes_np.float64)
    filled = _m4_native_30m_lakes_np.asarray(filled_m, _m4_native_30m_lakes_np.float64)
    mask = _m4_native_30m_lakes_np.asarray(basin_mask, bool)
    if bed.shape != mask.shape or filled.shape != mask.shape:
        raise ValueError("bed, filled level and basin mask must share a shape")
    if not mask.any():
        raise ValueError("nonempty basin mask required")
    spill = native30_finite_number(spill_level_m, "spill_level_m")
    tolerance = native30_finite_number(tolerance_m, "tolerance_m")
    mesh = _m4_native_30m_lakes_grid_mesh(bed.shape) if mesh is None else mesh
    rim = _graph_rim(mask, mesh)
    record = {"rim_mask": _m4_native_30m_lakes_readonly(rim), "rim_cells": int(rim.sum()),
              "spill_level_m": spill, "present": False, "exit_cells": 0,
              "exit_mask": _m4_native_30m_lakes_readonly(_m4_native_30m_lakes_np.zeros_like(rim)), "exit_flat_indices": (),
              "exit_min_clearance_cells": -1, "exit_max_clearance_cells": -1,
              "geometric_rim_minimum_m": float("nan"),
              "geometric_minus_spill_m": float("nan"),
              "flood_level_constancy_m": 0.0}
    if not rim.any():
        return record
    basin_levels = filled[mask]
    constancy = float(basin_levels.max() - basin_levels.min())
    record["flood_level_constancy_m"] = constancy
    record["geometric_rim_minimum_m"] = float(bed[rim].min())
    record["geometric_minus_spill_m"] = float(bed[rim].min()) - spill
    if constancy > tolerance:
        return record
    exits = rim & (_m4_native_30m_lakes_np.abs(filled - spill) <= tolerance)
    if not exits.any():
        return record
    rows, columns = bed.shape
    flat_count = _m4_native_30m_lakes_np.flatnonzero(exits.reshape(-1))
    rr, cc = _m4_native_30m_lakes_np.nonzero(exits)
    clearance = _m4_native_30m_lakes_np.minimum(_m4_native_30m_lakes_np.minimum(rr, cc),
                           _m4_native_30m_lakes_np.minimum(rows - 1 - rr, columns - 1 - cc))
    record.update(present=True, exit_cells=int(exits.sum()),
                  exit_mask=_m4_native_30m_lakes_readonly(exits),
                  exit_flat_indices=tuple(int(value) for value in flat_count),
                  exit_min_clearance_cells=int(clearance.min()),
                  exit_max_clearance_cells=int(clearance.max()),
                  exit_level_agreement_m=float(_m4_native_30m_lakes_np.abs(filled[exits] - spill).max()),
                  exit_row_column=[[int(r), int(c)] for r, c in zip(rr, cc)])
    return record

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:336 ---
def basin_catchment(elevation_m, basin_mask, *, mesh=None):
    """Cells whose raw metric irregular graph ends on a basin minimum.

    Reuses ``metric_depression_gate.unfilled_catchment_flow`` for the raw receiver
    graph and walks it upward here (one donor list, one stack): a topological sum,
    not a second routing solve.

    ``unknown_mask`` marks catchment cells on the window border, where the flood has
    no neighbour to read: water enters there from outside the resolved window, so the
    inflow is undeclared. ``leaked_cells`` counts basin members the catchment failed
    to reach; a nonempty set means the two traversals disagree about the basin and
    the honest answer is a refusal, not a repair.

    Stated limit: on flat ground raw strict-downhill routing has almost no structure,
    so a basin fed by a plateau draws a small catchment. That is a property of the
    terrain at 30 m, not of this traversal; ``metric_depression_gate`` documents the
    same effect and it is why this module reports the count instead of a verdict.
    """
    from terrain_pipeline.common_infra import readonly as _m4_native_30m_lakes_readonly
    from terrain_pipeline.surface_rivers.metric_depression_gate import unfilled_catchment_flow as _m4_native_30m_lakes_unfilled_catchment_flow
    bed = _m4_native_30m_lakes_np.asarray(elevation_m, _m4_native_30m_lakes_np.float64)
    mask = _m4_native_30m_lakes_np.asarray(basin_mask, bool)
    if bed.shape != mask.shape:
        raise ValueError("bed and basin mask must share a shape")
    if not mask.any():
        raise ValueError("nonempty basin mask required")
    accumulator, receiver, is_minimum = _m4_native_30m_lakes_unfilled_catchment_flow(bed, mesh=mesh)
    flat_receiver = _m4_native_30m_lakes_np.asarray(receiver, _m4_native_30m_lakes_np.int64).reshape(-1)
    flat_minimum = _m4_native_30m_lakes_np.asarray(is_minimum, bool).reshape(-1)
    flat_mask = mask.reshape(-1)
    donors = {}
    for cell, target in enumerate(flat_receiver):
        if target >= 0:
            donors.setdefault(int(target), []).append(cell)
    reached = _m4_native_30m_lakes_np.zeros(flat_receiver.size, bool)
    pending = [int(cell) for cell in _m4_native_30m_lakes_np.flatnonzero(flat_minimum & flat_mask)]
    for cell in pending:
        reached[cell] = True
    while pending:
        cell = pending.pop()
        for donor in donors.get(cell, ()):
            if not reached[donor]:
                reached[donor] = True
                pending.append(donor)
    catchment = reached.reshape(bed.shape)
    border = _m4_native_30m_lakes_np.zeros(bed.shape, bool)
    border[[0, -1], :] = True
    border[:, [0, -1]] = True
    unknown = catchment & border
    leaked = mask & ~catchment
    return {"catchment_mask": _m4_native_30m_lakes_readonly(catchment), "unknown_mask": _m4_native_30m_lakes_readonly(unknown),
            "contributing_cells": int(catchment.sum()),
            "unknown_cells": int(unknown.sum()), "leaked_cells": int(leaked.sum()),
            "basin_minimum_cells": int(_m4_native_30m_lakes_np.count_nonzero(flat_minimum & flat_mask)),
            "raw_catchment_cells": accumulator}

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:395 ---
@_m4_native_30m_lakes_dataclass(frozen=True)
class Native30mLake:
    """One 30 m lake basin: certified geometry, its store, and its saddle rating.

    ``storage`` and ``outlets`` are exactly the two attributes
    ``world_reach_lake.integrate_sill_lake`` reads, so ``march_lake`` hands this
    object to it directly -- that call *is* the reuse, not a second level-pool core.
    """

    certified: bool
    reason_code: str
    seed_row_column: tuple
    spacing_m: float
    cell_area_m2: float
    basin_mask: _m4_native_30m_lakes_np.ndarray
    basin_cells: int
    basin_area_m2: float
    bed_min_m: float
    spill_level_m: float
    rim_clearance_cells: int
    saddle: dict
    catchment: dict
    storage: object
    outlets: tuple
    head_allowance_m: float
    provenance: dict = _m4_native_30m_lakes_field(default_factory=dict)

    @property
    def truncated_not_judged(self):
        """The window could not answer; the number would be a measurement artefact."""
        return self.reason_code in TRUNCATION_REASONS

    @property
    def capacity_at_spill_m3(self):
        """Water held when the basin is exactly at its lowest saddle."""
        if self.storage is None:
            return float("nan")
        return float(self.storage.volume_at_stage(self.spill_level_m))

    @property
    def storage_capacity_m3(self):
        """Water held at the declared top of the store (spill + head allowance)."""
        if self.storage is None:
            return float("nan")
        return float(self.storage.capacity_m3)

    @property
    def outlet_crest_m(self):
        return float(self.outlets[0].crest_stage_m) if self.outlets else float("nan")

    def level_table(self, levels_m):
        """A(h)/V(h) straight from the store, so a table cannot disagree with it."""
        if self.storage is None:
            raise ValueError("a refused basin has no storage curve to tabulate")
        rows = []
        for level in _m4_native_30m_lakes_np.asarray(levels_m, _m4_native_30m_lakes_np.float64):
            clamped = float(min(max(level, self.storage.min_stage_m),
                                self.storage.max_stage_m))
            rows.append({"stage_m": float(level), "clamped_stage_m": clamped,
                         "area_m2": float(self.storage.surface_area_at_stage(clamped)),
                         "volume_m3": float(self.storage.volume_at_stage(clamped))})
        return rows

    def as_record(self):
        """JSON-safe record: counts and declared numbers, never an array or an inf."""
        record = {
            "schema": NATIVE_30M_LAKE_SCHEMA, "algorithm": NATIVE_30M_LAKE_ALGORITHM,
            "certified": bool(self.certified), "reason_code": self.reason_code,
            "truncated_not_judged": bool(self.truncated_not_judged),
            "seed_row_column": [int(value) for value in self.seed_row_column],
            "spacing_m": float(self.spacing_m), "cell_area_m2": float(self.cell_area_m2),
            "basin_cells": int(self.basin_cells),
            "basin_area_m2": float(self.basin_area_m2),
            "bed_min_m": _jsonable(self.bed_min_m),
            "spill_level_m": _jsonable(self.spill_level_m),
            "rim_clearance_cells": int(self.rim_clearance_cells),
            "saddle_present": bool(self.saddle.get("present", False)),
            "saddle_rim_cells": int(self.saddle.get("rim_cells", 0)),
            "saddle_exit_cells": int(self.saddle.get("exit_cells", 0)),
            "saddle_exit_min_clearance_cells": int(
                self.saddle.get("exit_min_clearance_cells", -1)),
            "saddle_exit_max_clearance_cells": int(
                self.saddle.get("exit_max_clearance_cells", -1)),
            "flood_level_constancy_m": _jsonable(
                self.saddle.get("flood_level_constancy_m", 0.0)),
            "rejected_geometric_rim_minimum_m": _jsonable(
                self.saddle.get("geometric_rim_minimum_m", float("nan"))),
            "rejected_geometric_minus_spill_m": _jsonable(
                self.saddle.get("geometric_minus_spill_m", float("nan"))),
            "contributing_cells": int(self.catchment.get("contributing_cells", 0)),
            "unknown_upstream_cells": int(self.catchment.get("unknown_cells", 0)),
            "catchment_leaked_cells": int(self.catchment.get("leaked_cells", 0)),
            "capacity_at_spill_m3": _jsonable(self.capacity_at_spill_m3),
            "storage_capacity_m3": _jsonable(self.storage_capacity_m3),
            "outlet_crest_m": _jsonable(self.outlet_crest_m),
            "head_allowance_m": float(self.head_allowance_m),
            "units": dict(UNITS), "tolerances": dict(TOLERANCES),
            "budgets": dict(BUDGETS),
            "hydraulic_ready": False, "natural_outlet_verified": False,
            "publishable": False,
        }
        for key, value in self.provenance.items():
            record.setdefault(key, value)
        return record

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:500 ---
def _jsonable(value):
    number = float(value)
    return number if _m4_native_30m_lakes_math.isfinite(number) else None

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:505 ---
def _refused(reason, *, seed, spacing, cell_area, basin_mask, basin_cells, bed_min,
             spill, clearance, saddle, catchment, allowance, provenance):
    from terrain_pipeline.common_infra import readonly as _m4_native_30m_lakes_readonly
    return Native30mLake(
        certified=False, reason_code=reason, seed_row_column=seed, spacing_m=spacing,
        cell_area_m2=cell_area, basin_mask=_m4_native_30m_lakes_readonly(basin_mask), basin_cells=int(basin_cells),
        basin_area_m2=int(basin_cells) * cell_area, bed_min_m=float(bed_min),
        spill_level_m=float(spill), rim_clearance_cells=int(clearance), saddle=saddle,
        catchment=catchment, storage=None, outlets=(), head_allowance_m=allowance,
        provenance=dict(provenance, refusal_stage=reason,
                        refusal_policy=("a refused basin reports no store, no outlet and "
                                        "no certified spill level; the reason code is "
                                        "stable and it is the window -- not the number "
                                        "-- that has to change")))

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:520 ---
def build_native_30m_lake(elevation_m, resolved_mask, *, seed_cell_rc, spacing_m,
                          origin_xz_m, source_identity_sha256, surface_kind,
                          sill_width_m, discharge_coefficient, head_allowance_m,
                          contact_margin_cells=_m4_native_30m_lakes_CONTACT_MARGIN_CELLS,
                          level_tolerance_m=LEVEL_TOLERANCE_M,
                          max_cells=MAX_HYPSOMETRY_CELLS, produced_depth_m=None,
                          sill_provenance="declared saddle weir width", provenance=None):
    """Derive one lake from a 30 m **bed**, or refuse it with a stable reason code.

    The checks run in a fixed order, so a basin failing several is always explained
    by the same one and two runs cannot disagree about why:

        surface declaration -> domain facts -> fully resolved window -> basin
        presence -> member budget -> flood level constant -> exit set present ->
        rim clearance -> exit clearance -> catchment unknown -> catchment leak ->
        certified

    ``produced_depth_m`` is optional: when given, the unfilled-catchment inflow and
    the ``lake / pass_through`` gate are computed and reported on the same numbers.
    Certification never depends on it.
    """
    from terrain_pipeline.common_infra import readonly as _m4_native_30m_lakes_readonly
    from terrain_pipeline.drainage import grid_mesh as _m4_native_30m_lakes_grid_mesh
    from terrain_pipeline.surface_rivers.metric_depression_gate import DEFAULT_ALPHA as _m4_native_30m_lakes_DEFAULT_ALPHA
    from terrain_pipeline.surface_rivers.metric_depression_gate import DEFAULT_MIN_AREA_M2 as _m4_native_30m_lakes_DEFAULT_MIN_AREA_M2
    from terrain_pipeline.surface_rivers.metric_depression_gate import DepressionGateConfig as _m4_native_30m_lakes_DepressionGateConfig
    from terrain_pipeline.surface_rivers.metric_depression_gate import GROWTH_SINGLE_WINDOW as _m4_native_30m_lakes_GROWTH_SINGLE_WINDOW
    from terrain_pipeline.surface_rivers.metric_depression_gate import INFLOW_UNFILLED_CATCHMENT as _m4_native_30m_lakes_INFLOW_UNFILLED_CATCHMENT
    from terrain_pipeline.surface_rivers.metric_depression_gate import judge_depression as _m4_native_30m_lakes_judge_depression
    from terrain_pipeline.surface_rivers.metric_depression_gate import rim_clearance_cells as _m4_native_30m_lakes_rim_clearance_cells
    if surface_kind != BED_SURFACE_KIND:
        raise ValueError("surface_kind must be %r: %r names a lake-model result, and a "
                         "water surface must never be read back as a bed"
                         % (BED_SURFACE_KIND, surface_kind))
    bed = _bed(elevation_m)
    mask = _mask(resolved_mask, bed.shape)
    seed = _seed(seed_cell_rc, bed.shape)
    spacing = _positive_number(spacing_m, "spacing_m")
    cell_area = spacing * spacing
    allowance = _positive_number(head_allowance_m, "head_allowance_m")
    width = _positive_number(sill_width_m, "sill_width_m")
    coefficient_cd = _positive_number(discharge_coefficient, "discharge_coefficient")
    strength = contact_margin_cells
    if type(strength) is not int or strength < 0:
        raise ValueError("non-negative integer contact_margin_cells required")
    tolerance = native30_finite_number(level_tolerance_m, "level_tolerance_m")
    if tolerance < 0.:
        raise ValueError("level_tolerance_m must be nonnegative")
    limit = int(max_cells)
    if not 4 <= limit <= MAX_HYPSOMETRY_CELLS:
        raise ValueError("max_cells must be 4..%d" % MAX_HYPSOMETRY_CELLS)
    native30_sha(source_identity_sha256, "source_identity_sha256")
    origin = _m4_native_30m_lakes_np.asarray(origin_xz_m, _m4_native_30m_lakes_np.float64).reshape(-1)
    if origin.size != 2 or not _m4_native_30m_lakes_np.isfinite(origin).all():
        raise ValueError("finite [x, z] origin required")
    if not isinstance(sill_provenance, str) or not sill_provenance.strip():
        raise ValueError("sill width provenance required")
    if produced_depth_m is not None:
        depth_value = native30_finite_number(produced_depth_m, "produced_depth_m")
        if depth_value < 0.:
            raise ValueError("produced_depth_m must be nonnegative")
    else:
        depth_value = None

    base = {
        "surface_kind": surface_kind,
        "sill_width_m": width, "discharge_coefficient": coefficient_cd,
        "outlet_coefficient_m3_s_m15": sill_coefficient_m3_s_m15(
            width, discharge_coefficient=coefficient_cd),
        "sill_provenance": sill_provenance,
        "contact_margin_cells": int(strength), "level_tolerance_m": tolerance,
        "origin_xz_m": [float(origin[0]), float(origin[1])],
        "source_identity_sha256": source_identity_sha256,
        "support_policy": ("one store cell per %.3f m terrain cell of the seed cell's "
                           "graph-connected positive-fill-depth drainage depression" % spacing),
        "saddle_policy": ("exit set = graph-adjacent nodes outside the depression whose "
                          "priority-flood level equals the basin's own; the flood level "
                          "is the saddle elevation, and the lowest rim *bed* is "
                          "reported as rejected"),
        "above_saddle_pondage_policy": (
            "V(h) for h > spill is A(spill) * (h - spill) up to spill + %.6f m of declared "
            "weir head: a declared pondage, not measured terrain" % allowance),
        "gate_policy": ("judge_depression with require_growth_convergence=False; criteria "
                        "(c) growth and (d) rim clearance are this module's own band and "
                        "exit refusals, so they are not evaluated twice"),
        "hydraulic_model": "reduced_level_pool_signed_sill_weir_not_saint_venant",
        "units": dict(UNITS), "tolerances": dict(TOLERANCES),
        "budgets": dict(BUDGETS),
    }
    if provenance:
        base.update(dict(provenance))
    empty_catchment = {"contributing_cells": 0, "unknown_cells": 0, "leaked_cells": 0,
                       "basin_minimum_cells": 0}
    empty_saddle = {"present": False, "rim_cells": 0, "exit_cells": 0,
                    "exit_min_clearance_cells": -1, "exit_max_clearance_cells": -1,
                    "geometric_rim_minimum_m": float("nan"),
                    "geometric_minus_spill_m": float("nan"),
                    "flood_level_constancy_m": 0.0}

    def refuse(reason, basin_mask=None, basin_cells=0, bed_min=float("nan"),
               spill=float("nan"), clearance=-1, saddle=None, catchment=None):
        return _refused(
            reason, seed=(seed[0], seed[1]), spacing=spacing, cell_area=cell_area,
            basin_mask=(_m4_native_30m_lakes_np.zeros(bed.shape, bool) if basin_mask is None else basin_mask),
            basin_cells=basin_cells, bed_min=bed_min, spill=spill, clearance=clearance,
            saddle=dict(empty_saddle if saddle is None else saddle),
            catchment=dict(empty_catchment if catchment is None else catchment),
            allowance=allowance, provenance=base)

    if not mask.all():
        # `depression_hierarchy` requires a fully valid window for the same reason:
        # with a hole in it the flood has no neighbour to read and would answer for a
        # different basin.
        return refuse(REASON_WINDOW_UNRESOLVED, bed_min=float(bed[seed]))

    mesh = _m4_native_30m_lakes_grid_mesh(bed.shape, x0_m=origin[0], z0_m=origin[1], dx_m=spacing)
    filled, depth, basin = measure_basin(bed, seed, mesh=mesh)
    if basin is None:
        # No closed depression at the seed: a slope, a flat, a lowland that drains --
        # or a water surface, whose fill depth is zero everywhere by construction.
        return refuse(REASON_NO_DEPRESSION, bed_min=float(bed[seed]))
    cells = int(basin.sum())
    if cells > limit:
        raise ValueError("basin of %d cells exceeds the declared store limit of %d"
                         % (cells, limit))
    beds = _m4_native_30m_lakes_np.ascontiguousarray(bed[basin], _m4_native_30m_lakes_np.float64)
    bed_min = float(beds.min())
    levels = filled[basin]
    spill = float(levels.max())
    clearance = _m4_native_30m_lakes_rim_clearance_cells(basin, bed.shape)
    saddle = lowest_saddle(bed, filled, basin, spill, tolerance_m=tolerance, mesh=mesh)
    catchment = basin_catchment(bed, basin, mesh=mesh)

    if float(saddle.get("flood_level_constancy_m", 0.0)) > tolerance:
        return refuse(REASON_FILL_NOT_CONSTANT, basin, cells, bed_min, spill, clearance,
                      saddle, catchment)
    if not saddle["present"]:
        return refuse(REASON_SADDLE_ABSENT, basin, cells, bed_min, spill, clearance,
                      saddle, catchment)
    if clearance < strength:
        return refuse(REASON_RIM_IN_BAND, basin, cells, bed_min, spill, clearance,
                      saddle, catchment)
    if int(saddle["exit_min_clearance_cells"]) < strength:
        return refuse(REASON_SADDLE_IN_BAND, basin, cells, bed_min, spill, clearance,
                      saddle, catchment)
    if int(catchment["unknown_cells"]) > 0:
        return refuse(REASON_UPSTREAM_UNKNOWN, basin, cells, bed_min, spill, clearance,
                      saddle, catchment)
    if int(catchment["leaked_cells"]) > 0:
        return refuse(REASON_MEMBERSHIP_LEAK, basin, cells, bed_min, spill, clearance,
                      saddle, catchment)
    if not spill > bed_min:
        raise ValueError("degenerate basin: the spill level does not exceed the bed")

    cell_ids = _m4_native_30m_lakes_np.flatnonzero(basin.reshape(-1)).astype(_m4_native_30m_lakes_np.int64)
    areas = _m4_native_30m_lakes_np.full(cell_ids.size, cell_area, _m4_native_30m_lakes_np.float64)
    store = LakeStorage(
        cell_ids=cell_ids, bed_elevation_m=beds, cell_area_m2=areas,
        seed_cell_id=int(cell_ids[int(_m4_native_30m_lakes_np.argmin(beds))]),
        max_stage_m=spill + allowance, source_identity_sha256=source_identity_sha256,
        footprint_policy=(
            "closed_depression_30m_cells; A(h) and V(h) are the terrain's own "
            "hypsometry over %d cells at %.3f m; no shape function is imposed"
            % (cells, spacing)))
    outlets = (LakeOutlet(
        0, -1, spill, sill_coefficient_m3_s_m15(width, discharge_coefficient=coefficient_cd),
        "saddle at the flood level %.9f m with %d exit cells (nearest to the window "
        "border: %d cells); %s"
        % (spill, int(saddle["exit_cells"]), int(saddle["exit_min_clearance_cells"]),
           sill_provenance)),)

    gate = None
    record_extra = {}
    if depth_value is not None:
        inflow = float(catchment["contributing_cells"]) * cell_area * depth_value
        verdict = _m4_native_30m_lakes_judge_depression(
            basin_cells=cells, capacity_m3=float(store.volume_at_stage(spill)),
            inflow_m3=inflow, area_m2=cells * cell_area, spill_level_m=spill,
            config=_m4_native_30m_lakes_DepressionGateConfig(
                alpha=_m4_native_30m_lakes_DEFAULT_ALPHA, min_area_m2=_m4_native_30m_lakes_DEFAULT_MIN_AREA_M2,
                contact_margin_cells=strength, require_growth_convergence=False),
            label=-1, input_quantity=_m4_native_30m_lakes_INFLOW_UNFILLED_CATCHMENT,
            contributing_cells=float(catchment["contributing_cells"]),
            contributing_area_m2=float(catchment["contributing_cells"]) * cell_area,
            own_production_m3=cells * cell_area * depth_value,
            bed_min_m=bed_min, rim_clearance_cells=clearance, growth_converged=False,
            convergence_gate=_m4_native_30m_lakes_GROWTH_SINGLE_WINDOW)
        gate = dict(verdict.as_record(), growth_evaluated=False,
                    produced_depth_m=depth_value)
        record_extra = {"gate": gate}

    return Native30mLake(
        certified=True, reason_code=REASON_CERTIFIED, seed_row_column=(seed[0], seed[1]),
        spacing_m=spacing, cell_area_m2=cell_area, basin_mask=_m4_native_30m_lakes_readonly(basin),
        basin_cells=cells, basin_area_m2=cells * cell_area, bed_min_m=bed_min,
        spill_level_m=spill, rim_clearance_cells=clearance, saddle=saddle,
        catchment=catchment, storage=store, outlets=outlets,
        head_allowance_m=allowance,
        provenance=dict(base, relief_m=spill - bed_min,
                        capacity_at_spill_m3=float(store.volume_at_stage(spill)),
                        saddle_pondage_area_m2=float(store.surface_area_at_stage(spill)),
                        **record_extra))

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:718 ---
def initial_volume_m3(lake, *, initial_stage_m):
    """Initial water as the volume at a declared stage, inside the certified support."""
    _require_certified(lake)
    stage = native30_finite_number(initial_stage_m, "initial_stage_m")
    if stage > lake.spill_level_m:
        raise ValueError("initial stage above the lowest saddle is overflow, not an "
                         "initial stock: start at or below %.9f m" % lake.spill_level_m)
    if stage < lake.storage.min_stage_m:
        raise ValueError("initial stage below the minimum bed")
    return float(lake.storage.volume_at_stage(stage))

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:730 ---
def inflow_volume_m3(lake, *, produced_depth_m):
    """Inflow over a run: contributing cells x cell area x produced depth."""
    from terrain_pipeline.surface_rivers.metric_depression_gate import INFLOW_UNFILLED_CATCHMENT as _m4_native_30m_lakes_INFLOW_UNFILLED_CATCHMENT
    _require_certified(lake)
    depth = native30_finite_number(produced_depth_m, "produced_depth_m")
    if depth < 0.:
        raise ValueError("produced_depth_m must be nonnegative")
    cells = int(lake.catchment["contributing_cells"])
    return float(cells) * lake.cell_area_m2 * depth, {
        "contributing_cells": cells, "cell_area_m2": lake.cell_area_m2,
        "produced_depth_m": depth, "own_basin_cells": lake.basin_cells,
        "inflow_quantity": _m4_native_30m_lakes_INFLOW_UNFILLED_CATCHMENT,
        "note": ("the unfilled catchment is the area that actually delivers to this "
                 "hole; a filled-arival reading would double-count upstream overflow")}

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:745 ---
def march_lake(lake, inflow_volume_m3, dt_seconds, *, initial_volume_m3=0.0):
    """Storage, saddle overflow and recession through the existing sill-lake march.

    ``world_reach_lake.integrate_sill_lake`` does the stepping: storage first, then
    the existing ``LakeOutlet`` weir rating at the resolved stage, capped by the
    water actually present, so its ledger closes by construction. This function adds
    only declarations, the loss terms and the budget.
    """
    _require_certified(lake)
    inflow = _m4_native_30m_lakes_np.asarray(inflow_volume_m3, _m4_native_30m_lakes_np.float64)
    dt = _m4_native_30m_lakes_np.asarray(dt_seconds, _m4_native_30m_lakes_np.float64)
    if inflow.ndim != 1 or dt.ndim != 1 or inflow.shape != dt.shape or inflow.size == 0:
        raise ValueError("matching nonempty inflow and dt series required")
    if (not _m4_native_30m_lakes_np.isfinite(inflow).all() or not _m4_native_30m_lakes_np.isfinite(dt).all()
            or _m4_native_30m_lakes_np.any(inflow < 0.) or _m4_native_30m_lakes_np.any(dt <= 0.)):
        raise ValueError("finite nonnegative inflow and positive dt required")
    if inflow.size > MAX_MARCH_STEPS:
        raise ValueError("%d steps exceeds the declared march budget of %d"
                         % (inflow.size, MAX_MARCH_STEPS))
    if (inflow.size + 1) * (3 + len(lake.outlets)) * 8 > MAX_TRACE_BYTES:
        raise ValueError("trace byte budget exceeded before any allocation")
    start = native30_finite_number(initial_volume_m3, "initial_volume_m3")
    if start < 0. or start > lake.storage.capacity_m3:
        raise ValueError("initial lake inventory outside the declared finite support")
    trace = integrate_sill_lake(lake, inflow, dt, initial_volume_m3=start)
    ledger = dict(trace["ledger"])
    residual = float(ledger["residual_m3"])
    gross = float(ledger["initial_m3"]) + float(ledger["inflow_m3"])
    relative = abs(residual) / gross if gross > 0. else abs(residual)
    trace["loss_terms"] = {
        "saddle_overflow_m3": float(ledger["spill_m3"]),
        "residual_m3": residual,
        "evaporation_m3": None, "groundwater_m3": None,
        "policy": ("the only loss of this level pool is saddle overflow; evaporation and "
                   "groundwater are not modelled here and are declared None rather than "
                   "reported as zero"),
    }
    trace["ledger"] = ledger
    trace["ledger_residual_relative"] = relative
    trace["ledger_closed"] = bool(relative <= LEDGER_RELATIVE_TOLERANCE)
    trace["spill_level_m"] = lake.spill_level_m
    trace["requested_steps"] = int(inflow.size)
    trace["hydraulic_model"] = "reduced_level_pool_signed_sill_weir_not_saint_venant"
    trace["hydraulic_ready"] = False
    trace["natural_outlet_verified"] = False
    trace["publishable"] = False
    trace["units"] = dict(UNITS)
    trace["tolerances"] = dict(TOLERANCES)
    return trace

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:796 ---
def _require_certified(lake):
    if not isinstance(lake, Native30mLake):
        raise ValueError("Native30mLake required")
    if not lake.certified or lake.storage is None:
        raise ValueError("basin is not certified (%s): it carries no storage curve"
                         % (lake.reason_code,))
    return lake

# --- terrain_pipeline/surface_rivers/native_30m_lakes.py:805 ---
def validate_native_30m_lake(lake):
    """Internal consistency of one record; raises instead of returning a half lake."""
    if not isinstance(lake, Native30mLake):
        raise ValueError("Native30mLake required")
    if lake.reason_code not in REASON_CODES:
        raise ValueError("unknown reason code: %r" % (lake.reason_code,))
    if not lake.certified:
        if lake.storage is not None or lake.outlets:
            raise ValueError("a refused basin must carry no store and no outlet")
        if lake.reason_code == REASON_CERTIFIED:
            raise ValueError("a certified reason with certified=False")
        return True
    if lake.reason_code != REASON_CERTIFIED:
        raise ValueError("a certified basin must carry the certified reason")
    if lake.storage is None or len(lake.outlets) != 1:
        raise ValueError("a certified basin needs exactly one saddle outlet and a store")
    if abs(lake.storage.min_stage_m - lake.bed_min_m) > LEVEL_TOLERANCE_M:
        raise ValueError("store minimum stage is not the measured minimum bed")
    if abs(lake.storage.max_stage_m
           - (lake.spill_level_m + lake.head_allowance_m)) > LEVEL_TOLERANCE_M:
        raise ValueError("store top is not the spill level plus the declared head allowance")
    if abs(lake.outlets[0].crest_stage_m - lake.spill_level_m) > LEVEL_TOLERANCE_M:
        raise ValueError("outlet crest is not the measured spill level")
    if int(lake.saddle.get("exit_cells", 0)) == 0:
        raise ValueError("a certified basin must have a nonempty exit set")
    if float(lake.saddle.get("flood_level_constancy_m", 1.0)) > LEVEL_TOLERANCE_M:
        raise ValueError("a certified basin's flood level is not constant over it")
    if int(lake.saddle.get("exit_min_clearance_cells", -1)) < 0:
        raise ValueError("a certified basin must carry a measured exit clearance")
    if int(lake.catchment["unknown_cells"]) != 0:
        raise ValueError("a certified basin cannot hide unknown upstream cells")
    if int(lake.catchment["leaked_cells"]) != 0:
        raise ValueError("a certified basin's members must all be in its catchment")
    return True

# --- terrain_pipeline/td_lake_entry_taper.py:11 ---
ENTRY_TAPER_SCHEMA = "td-lake-entry-taper-v1"

# --- terrain_pipeline/td_lake_entry_taper.py:12 ---
MAX_ENTRIES = 256

# --- terrain_pipeline/td_lake_entry_taper.py:13 ---
MAX_VERTICES = 100_000

# --- terrain_pipeline/td_lake_entry_taper.py:14 ---
FLAGS = {"hydraulic_ready": False, "natural_outlet_verified": False,
         "publishable": False, "new_bed_hydrology_verified": False,
         "solver_advanced": False, "lake_bed_changed": False}

# --- terrain_pipeline/td_lake_entry_taper.py:19 ---
def digest(record):
    return _m4_lake_entry_taper_hashlib.sha256(_m4_lake_entry_taper_json.dumps(record, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()

# --- terrain_pipeline/td_lake_entry_taper.py:24 ---
def sample_source(hierarchy, selected_leaves, points_xz):
    arrays = hierarchy["arrays"]
    height = _m4_lake_entry_taper_np.asarray(arrays["height_m"], dtype=float)
    spacing = float(hierarchy["metadata"]["spacing_m"])
    origin = _m4_lake_entry_taper_np.asarray(hierarchy["metadata"]["origin_m_xz"], dtype=float)
    points = _m4_lake_entry_taper_np.asarray(points_xz, dtype=float).reshape(-1, 2)
    if not _m4_lake_entry_taper_np.isfinite(points).all() or not _m4_lake_entry_taper_math.isfinite(spacing) or spacing <= 0:
        raise ValueError("invalid_source_coordinates")
    grid = (points - origin) / spacing
    if _m4_lake_entry_taper_np.any(grid < 0) or _m4_lake_entry_taper_np.any(grid[:, 0] > height.shape[1] - 1) or _m4_lake_entry_taper_np.any(grid[:, 1] > height.shape[0] - 1):
        raise ValueError("outside_source_coverage")
    first = _m4_lake_entry_taper_np.floor(grid).astype(int)
    fraction = grid - first
    output = _m4_lake_entry_taper_np.zeros(len(points))
    for delta_x, delta_z in ((0, 0), (1, 0), (0, 1), (1, 1)):
        weight = (fraction[:, 0] if delta_x else 1 - fraction[:, 0]) * (fraction[:, 1] if delta_z else 1 - fraction[:, 1])
        active = weight > 0
        columns = first[active, 0] + delta_x
        rows = first[active, 1] + delta_z
        if not _m4_lake_entry_taper_np.asarray(arrays["valid_mask"])[rows, columns].all():
            raise ValueError("unknown_source_coverage")
        if _m4_lake_entry_taper_np.asarray(arrays["protected_mask"])[rows, columns].any():
            raise ValueError("protected_source_coverage")
        if not _m4_lake_entry_taper_np.isin(_m4_lake_entry_taper_np.asarray(arrays["contribution_owner"])[rows, columns], selected_leaves).all():
            raise ValueError("outside_selected_component")
        if _m4_lake_entry_taper_np.asarray(arrays["open_boundary_mask"])[rows, columns].any():
            raise ValueError("engineering_boundary_contact")
        values = height[rows, columns]
        if not _m4_lake_entry_taper_np.isfinite(values).all():
            raise ValueError("nonfinite_source_height")
        output[active] += weight[active] * values
    return output

# --- terrain_pipeline/td_lake_entry_taper.py:58 ---
def wet_protection(paths):
    return {"covered_native_cell_ids": sorted({cell for lake in paths["lakes"] for cell in lake["covered_cell_ids"]}),
            "stage_by_leaf": [{"leaf_id": lake["leaf_id"], "stage_m": lake["ordinary_stage_max_m"]}
                              for lake in sorted(paths["lakes"], key=lambda lake: lake["leaf_id"])],
            "semantics": "conservative maximum-saved-stage lake protection, not simultaneous water geometry"}

# --- terrain_pipeline/td_lake_entry_taper.py:65 ---
def wet_source_support(hierarchy, protection, points_xz, source_height):
    height = _m4_lake_entry_taper_np.asarray(hierarchy["arrays"]["height_m"])
    origin = _m4_lake_entry_taper_np.asarray(hierarchy["metadata"]["origin_m_xz"])
    spacing = float(hierarchy["metadata"]["spacing_m"])
    coordinates = _m4_lake_entry_taper_np.floor((_m4_lake_entry_taper_np.asarray(points_xz) - origin) / spacing + .5).astype(int)
    if _m4_lake_entry_taper_np.any(coordinates < 0) or _m4_lake_entry_taper_np.any(coordinates[:, 0] >= height.shape[1]) or _m4_lake_entry_taper_np.any(coordinates[:, 1] >= height.shape[0]):
        raise ValueError("outside_source_coverage")
    cells = coordinates[:, 1] * height.shape[1] + coordinates[:, 0]
    owners = _m4_lake_entry_taper_np.asarray(hierarchy["arrays"]["contribution_owner"])[coordinates[:, 1], coordinates[:, 0]]
    stages = {item["leaf_id"]: item["stage_m"] for item in protection["stage_by_leaf"]}
    lake_stage = _m4_lake_entry_taper_np.array([stages.get(int(owner), -_m4_lake_entry_taper_math.inf) for owner in owners])
    return _m4_lake_entry_taper_np.isin(cells, protection["covered_native_cell_ids"]) | (source_height < lake_stage)

# --- terrain_pipeline/td_lake_entry_taper.py:79 ---
def _one_entry(support, paths, sections, hierarchy, incoming, ports, nodes):
    anchor_id, wet_id = support["node_ids"]
    predecessors = incoming.get(anchor_id, [])
    if len(predecessors) != 1:
        raise ValueError("missing_or_ambiguous_land_predecessor")
    predecessor = predecessors[0]
    upstream_id = predecessor["node_ids"][0]
    upstream_ports = ports.get(upstream_id, [])
    if len(upstream_ports) != 1:
        raise ValueError("missing_or_ambiguous_accepted_port")
    port = upstream_ports[0]
    start = _m4_lake_entry_taper_np.asarray(nodes[upstream_id]["xyz_m"], dtype=float)
    end = _m4_lake_entry_taper_np.asarray(nodes[anchor_id]["xyz_m"], dtype=float)
    displacement = end[[0, 2]] - start[[0, 2]]
    length = float(_m4_lake_entry_taper_np.linalg.norm(displacement))
    spacing = float(hierarchy["metadata"]["spacing_m"])
    if not _m4_lake_entry_taper_math.isclose(length, spacing, rel_tol=0, abs_tol=1e-8):
        raise ValueError("not_native_D4_land_segment")
    receiver = _m4_lake_entry_taper_np.asarray(hierarchy["arrays"]["receiver"]).ravel()
    for first_id, second_id in ((upstream_id, anchor_id), (anchor_id, wet_id)):
        if int(receiver[nodes[first_id]["cell_id"]]) != nodes[second_id]["cell_id"]:
            raise ValueError("native_receiver_mismatch")
    profile = _m4_lake_entry_taper_np.asarray(port["cross_section_xyz_m"][-1], dtype=float)
    if profile.shape != (4, 3) or not _m4_lake_entry_taper_np.isfinite(profile).all():
        raise ValueError("invalid_accepted_port")
    longitudinal = displacement / length
    offsets = profile[:, [0, 2]] - start[[0, 2]]
    if _m4_lake_entry_taper_np.max(_m4_lake_entry_taper_np.abs(offsets @ longitudinal)) > 1e-8:
        raise ValueError("turn_requires_junction_transition")
    if _m4_lake_entry_taper_np.linalg.norm(profile[1, [0, 2]] - profile[2, [0, 2]]) <= 0:
        raise ValueError("zero_port_width")
    midpoint = (profile[1] + profile[2]) / 2
    if not _m4_lake_entry_taper_np.allclose(midpoint[[0, 2]], start[[0, 2]], atol=1e-8, rtol=0):
        raise ValueError("uncentered_accepted_port")
    expanded = _m4_lake_entry_taper_np.insert(profile, 2, midpoint, axis=0)
    offsets = expanded[:, [0, 2]] - start[[0, 2]]
    source_start = sample_source(hierarchy, paths["selected_leaf_ids"], expanded[:, [0, 2]])
    cut_start = source_start - expanded[:, 1]
    if cut_start.min() < -1e-8:
        raise ValueError("port_requires_fill")
    if cut_start.max() > 4:
        raise ValueError("port_cut_exceeds_4m")
    width = float(_m4_lake_entry_taper_np.linalg.norm(profile[1, [0, 2]] - profile[2, [0, 2]]))
    step = min(1., width / 4.)
    station_count = _m4_lake_entry_taper_math.ceil(length / step) + 1
    if station_count * 5 > MAX_VERTICES:
        raise ValueError("entry_vertex_budget_exceeded")
    fractions = _m4_lake_entry_taper_np.linspace(0, 1, station_count)
    centers = start[[0, 2]][None, :] + fractions[:, None] * displacement
    xz = centers[:, None, :] + offsets[None, :, :]
    source = sample_source(hierarchy, paths["selected_leaf_ids"], xz.reshape(-1, 2)).reshape(-1, 5)
    taper = 1 - (3 * fractions ** 2 - 2 * fractions ** 3)
    bed = source - taper[:, None] * _m4_lake_entry_taper_np.maximum(cut_start, 0)[None, :]
    bed[0] = expanded[:, 1]
    wet = wet_source_support(hierarchy, wet_protection(paths), xz.reshape(-1, 2), source.ravel()).reshape(-1, 5)
    if _m4_lake_entry_taper_np.any(wet & (source - bed > 1e-8)):
        raise ValueError("lake_wet_bed_cut_refused")
    if _m4_lake_entry_taper_np.max(_m4_lake_entry_taper_np.diff(bed[:, 2])) > 1e-8:
        raise ValueError("insufficient_downhill_grade_for_zero_cut_anchor")
    vertices = _m4_lake_entry_taper_np.stack((xz[:, :, 0], bed, xz[:, :, 1]), axis=-1).reshape(-1, 3)
    triangles = []
    for station in range(station_count - 1):
        for lateral in range(4):
            first = station * 5 + lateral
            triangles.extend([[first, first + 1, first + 6], [first, first + 6, first + 5]])
    return {"status": "candidate", "upstream_node_id": upstream_id,
            "anchor_node_id": anchor_id, "wet_node_id": wet_id,
            "land_arc_id": predecessor["arc_id"], "accepted_port_arc_id": port["arc_id"],
            "accepted_port_xyz_m": profile.tolist(), "length_m": length,
            "width_m": width, "station_spacing_m": length / (station_count - 1),
            "station_count": station_count, "vertices_xyz_m": vertices.tolist(),
            "triangles": triangles, "source_vertex_height_m": source.ravel().tolist(),
            "cut_profile_start_m": _m4_lake_entry_taper_np.maximum(cut_start, 0).tolist(),
            "maximum_vertex_cut_m": float((source - bed).max()),
            "anchor_source_profile_xyz_m": vertices[-5:].tolist(),
            "port_semantics": "exact existing four-point port with collinear midpoint subdivision",
            "support_semantics": "land predecessor only; lake_entry_support and wet lake bed unchanged",
            "rejection_reasons": []}

# --- terrain_pipeline/td_lake_entry_taper.py:159 ---
def build_lake_entry_tapers(paths, sections, hierarchy):
    if paths["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or sections["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]:
        raise ValueError("hierarchy_identity_mismatch")
    if paths["ordinary_identity_sha256"] != sections["ordinary_identity_sha256"]:
        raise ValueError("ordinary_identity_mismatch")
    if sections["composite_parent_identity"]["paths"] != paths["identity_sha256"] or sections["selected_leaf_ids"] != paths["selected_leaf_ids"]:
        raise ValueError("sections_paths_identity_mismatch")
    supports = [arc for arc in paths["arcs"] if arc["kind"] == "lake_entry_support"]
    if len(supports) > MAX_ENTRIES:
        raise ValueError("entry_count_budget_exceeded")
    incoming, ports = {}, {}
    for arc in paths["arcs"]:
        if arc["kind"] == "land_channel":
            incoming.setdefault(arc["node_ids"][-1], []).append(arc)
    for port in sections["edge_sections"]:
        ports.setdefault(port["node_ids"][-1], []).append(port)
    nodes = {node["node_id"]: node for node in paths["nodes"]}
    entries, vertices_used = [], 0
    for support in sorted(supports, key=lambda arc: arc["arc_id"]):
        entry = {"entry_id": support["arc_id"], "leaf_id": support["leaf_id"]}
        try:
            candidate = _one_entry(support, paths, sections, hierarchy, incoming, ports, nodes)
            if vertices_used + len(candidate["vertices_xyz_m"]) > MAX_VERTICES:
                raise ValueError("total_vertex_budget_exceeded")
            entry.update(candidate)
            vertices_used += len(candidate["vertices_xyz_m"])
        except ValueError as error:
            entry.update(status="refused", rejection_reasons=[str(error)],
                         vertices_xyz_m=[], triangles=[])
        entries.append(entry)
    result = {"schema": ENTRY_TAPER_SCHEMA, "algorithm": "native-source-wet-protected-smoothstep-land-entry-v2",
              "coordinate_system": "model XYZ metres; hierarchy arrays [z,x]",
              "hierarchy_identity_sha256": hierarchy["identity_sha256"],
              "paths_identity_sha256": paths["identity_sha256"],
              "sections_identity_sha256": sections["identity_sha256"],
              "selected_leaf_ids": paths["selected_leaf_ids"], "entries": entries,
              "wet_protection": wet_protection(paths),
              "parameters": {"maximum_cut_m": 4., "maximum_station_spacing_m": 1.,
                             "minimum_width_samples": 4, "maximum_vertices": MAX_VERTICES},
              "summary": {"requested": len(entries),
                          "candidates": sum(entry["status"] == "candidate" for entry in entries),
                          "vertices": vertices_used,
                          "refusals": dict(_m4_lake_entry_taper_Counter(reason for entry in entries for reason in entry["rejection_reasons"]))},
              "semantics": "source-sampled geometry candidate; interior triangle cut/fill and overlap must pass raster audit",
              **FLAGS}
    result["identity_sha256"] = digest(result)
    return result

# --- terrain_pipeline/td_lake_interface_continuous_bed.py:15 ---
INTERFACE_BED_SCHEMA = "td-lake-interface-continuous-bed-v1"

# --- terrain_pipeline/td_lake_interface_continuous_bed.py:18 ---
def _digest(value):
    return _m4_lake_interface_continuous_bed_hashlib.sha256(_m4_lake_interface_continuous_bed_json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()

# --- terrain_pipeline/td_lake_interface_continuous_bed.py:23 ---
def build_lake_interface_continuous_bed(geometry, patches):
    if geometry.get("schema") != "td-watershed-geometry-preparation-v1":
        raise ValueError("saved watershed geometry is required")
    if patches.get("schema") not in {
            "td-watershed-interface-patch-preparation-v2",
            "td-watershed-interface-patches-v1"}:
        raise ValueError("saved interface patches are required")
    lake = [patch for patch in patches.get("patches", [])
            if patch.get("kind") == "lake_anchor_transition"]
    accepted = [patch for patch in lake if patch.get("status") == "candidate"]
    rejected = [
        {"patch_id": patch.get("patch_id"),
         "rejection_reasons": list(patch.get("rejection_reasons", []))}
        for patch in lake if patch.get("status") != "candidate"
    ]
    result = {
        "schema": INTERFACE_BED_SCHEMA,
        "algorithm": "shared-port-lake-interface-continuous-bed-candidate-v1",
        "source_artifacts": {
            "geometry_identity_sha256": geometry.get("identity_sha256"),
            "patches_identity_sha256": patches.get("identity_sha256"),
        },
        "interfaces": [{
            "patch_id": patch["patch_id"],
            "vertices_xyz_m": patch["vertices_xyz_m"],
            "triangles": patch["triangles"],
            "boundary_edges": patch["boundary_edges"],
            "shared_bed_m": patch["shared_bed_m"],
            "required_cut_m": patch["required_cut_m"],
            "status": "candidate",
        } for patch in accepted],
        "rejected_interfaces": rejected,
        "summary": {
            "requested": len(lake), "accepted": len(accepted),
            "rejected": len(rejected), "triangle_count": sum(
                len(patch["triangles"]) for patch in accepted),
        },
        "status": "candidate" if accepted else "pending",
        "continuous_bed_ready": bool(accepted),
        "bed_changed": False,
        "hydraulic_solved": False,
        "natural_outlet_certified": False,
        "publish_ready": False,
        "source_bed_unchanged": True,
        "solver_calls": 0,
        "limitation": "accepted local interfaces are candidates with open ports; rejected lake anchors remain pending",
    }
    result["identity_sha256"] = _digest(result)
    validate_lake_interface_continuous_bed(result)
    return result

# --- terrain_pipeline/td_lake_interface_continuous_bed.py:75 ---
def validate_lake_interface_continuous_bed(result):
    if result.get("schema") != INTERFACE_BED_SCHEMA:
        raise ValueError("lake interface schema mismatch")
    if result.get("status") not in {"pending", "candidate"}:
        raise ValueError("invalid lake interface status")
    if result.get("continuous_bed_ready") != bool(result["interfaces"]):
        raise ValueError("continuous-bed status mismatch")
    if any(result.get(name) is not False for name in (
            "bed_changed", "hydraulic_solved", "natural_outlet_certified", "publish_ready")):
        raise ValueError("lake interface certification flags must remain false")
    if result.get("source_bed_unchanged") is not True or result.get("solver_calls") != 0:
        raise ValueError("lake interface source/solver contract mismatch")
    expected = {"requested": len(result["interfaces"]) + len(result["rejected_interfaces"]),
                "accepted": len(result["interfaces"]),
                "rejected": len(result["rejected_interfaces"]),
                "triangle_count": sum(len(item["triangles"]) for item in result["interfaces"])}
    if result.get("summary") != expected:
        raise ValueError("lake interface summary mismatch")
    identity = result.get("identity_sha256")
    unsigned = dict(result)
    unsigned.pop("identity_sha256", None)
    if identity != _digest(unsigned):
        raise ValueError("lake interface identity mismatch")
    return True

# --- terrain_pipeline/td_lake_interface_continuous_bed.py:101 ---
def save_lake_interface_continuous_bed(result, path):
    validate_lake_interface_continuous_bed(result)
    target = _m4_lake_interface_continuous_bed_Path(path)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_m4_lake_interface_continuous_bed_json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return target

# --- terrain_pipeline/td_lake_interface_continuous_bed.py:111 ---
def load_lake_interface_continuous_bed(path):
    result = _m4_lake_interface_continuous_bed_json.loads(_m4_lake_interface_continuous_bed_Path(path).read_text(encoding="utf-8"))
    validate_lake_interface_continuous_bed(result)
    return result

# --- terrain_pipeline/lake_balance.py:12 ---
BALANCE_VERSION = "lake-balance-irregular-v2"

# --- terrain_pipeline/lake_balance.py:16 ---
@_m4_lake_balance_dataclass(frozen=True)
class LakeBalanceRecipe:
    duration_s: float
    inflow_m3_s: float
    loss_m3_s: float
    initial_stage_m: float
    spill_stage_m: float
    max_outflow_m3_s: float

    def __post_init__(self):
        if any(isinstance(v, bool) or not _m4_lake_balance_math.isfinite(v) for v in self.__dict__.values()):
            raise ValueError("lake balance values must be finite")
        if (self.duration_s <= 0 or self.inflow_m3_s < 0 or self.loss_m3_s < 0 or
                self.max_outflow_m3_s < 0 or self.spill_stage_m < self.initial_stage_m):
            raise ValueError("invalid lake balance bounds")

# --- terrain_pipeline/lake_balance.py:32 ---
def evaluate_lake_balance(height_m, basin_mask, legal_spill_grid_zx, spacing_x_m,
                          spacing_z_m, source_identity, recipe: LakeBalanceRecipe,
                          downstream_path_grid_zx=None, domain_mask=None, protected_mask=None,
                          legal_outlet_mask=None, *, origin_xz_m=(0., 0.), world_seed=20261020):
    """Integrate explicit constant fluxes against measured basin capacity."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _m4_lake_balance_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _m4_lake_balance_array_hash
    from terrain_pipeline.drainage import grid_mesh as _m4_lake_balance_grid_mesh
    from terrain_pipeline.drainage import segments_clear as _m4_lake_balance_segments_clear
    terrain = _m4_lake_balance_np.asarray(height_m, dtype=_m4_lake_balance_np.float64)
    basin = _m4_lake_balance_np.asarray(basin_mask)
    if (terrain.ndim != 2 or basin.shape != terrain.shape or basin.dtype != bool or
            not _m4_lake_balance_np.isfinite(terrain).all() or not basin.any() or
            not _m4_lake_balance_math.isfinite(spacing_x_m) or not _m4_lake_balance_math.isfinite(spacing_z_m) or
            spacing_x_m <= 0 or spacing_z_m <= 0 or not source_identity):
        raise ValueError("invalid lake terrain or basin")
    spill = tuple(map(int, legal_spill_grid_zx))
    if (len(spill) != 2 or not (0 <= spill[0] < terrain.shape[0] and 0 <= spill[1] < terrain.shape[1]) or
            basin[spill] or abs(terrain[spill] - recipe.spill_stage_m) > 1e-6):
        raise ValueError("spill must be an explicit non-basin saddle at spill stage")
    mesh = _m4_lake_balance_grid_mesh(terrain.shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1],
        dx_m=spacing_x_m, dz_m=spacing_z_m, world_seed=world_seed)
    spill_id = int(_m4_lake_balance_np.ravel_multi_index(spill, terrain.shape))
    adjacent_spill = mesh.indices[mesh.indptr[spill_id]:mesh.indptr[spill_id + 1]]
    if not basin.ravel()[adjacent_spill].any():
        raise ValueError("spill does not touch basin")
    seen = _m4_lake_balance_np.zeros(basin.shape, bool)
    stack = [tuple(_m4_lake_balance_np.argwhere(basin)[0])]
    while stack:
        z, x = stack.pop()
        if seen[z, x]: continue
        seen[z, x] = True
        cell_id = z * terrain.shape[1] + x
        for target in mesh.indices[mesh.indptr[cell_id]:mesh.indptr[cell_id + 1]]:
            nz, nx = divmod(int(target), terrain.shape[1])
            if basin[nz,nx] and not seen[nz,nx]:
                stack.append((nz,nx))
    if not _m4_lake_balance_np.array_equal(seen, basin): raise ValueError("lake basin is disconnected")
    if downstream_path_grid_zx is None or domain_mask is None or protected_mask is None or legal_outlet_mask is None:
        raise ValueError("explicit downstream path, domain and protection required")
    downstream = _m4_lake_balance_np.asarray(downstream_path_grid_zx, dtype=_m4_lake_balance_np.int64)
    domain = _m4_lake_balance_np.asarray(domain_mask)
    protected = _m4_lake_balance_np.asarray(protected_mask)
    legal = _m4_lake_balance_np.asarray(legal_outlet_mask)
    if (downstream.ndim != 2 or downstream.shape[1] != 2 or len(downstream) < 2 or
            tuple(downstream[0]) != spill or
            _m4_lake_balance_np.any(downstream[:,0] < 0) or _m4_lake_balance_np.any(downstream[:,0] >= terrain.shape[0]) or
            _m4_lake_balance_np.any(downstream[:,1] < 0) or _m4_lake_balance_np.any(downstream[:,1] >= terrain.shape[1]) or
            domain.shape != terrain.shape or
            protected.shape != terrain.shape or legal.shape != terrain.shape or
            domain.dtype != bool or protected.dtype != bool or legal.dtype != bool):
        raise ValueError("invalid downstream spill path or masks")
    if not legal[tuple(downstream[-1])]: raise ValueError("spill path has no legal outlet")
    if (_m4_lake_balance_np.any(basin & ~domain) or _m4_lake_balance_np.any(basin & protected) or
            _m4_lake_balance_np.any(basin[0, :]) or _m4_lake_balance_np.any(basin[-1, :]) or
            _m4_lake_balance_np.any(basin[:, 0]) or _m4_lake_balance_np.any(basin[:, -1])):
        raise ValueError("basin leaves domain, crosses protection or touches grid boundary")
    submerged = basin & (terrain < recipe.spill_stage_m)
    if not _m4_lake_balance_np.array_equal(submerged, basin):
        raise ValueError("basin includes cells above spill stage")
    if not domain[spill] or protected[spill]: raise ValueError("spill is outside legal domain")
    for current, nxt in zip(downstream, downstream[1:]):
        z, x = map(int, nxt)
        current_id = int(_m4_lake_balance_np.ravel_multi_index(tuple(current), terrain.shape))
        target_id = z * terrain.shape[1] + x
        adjacent = mesh.indices[mesh.indptr[current_id]:mesh.indptr[current_id + 1]]
        if (not (0 <= z < terrain.shape[0] and 0 <= x < terrain.shape[1]) or
                not domain[z, x] or protected[z, x] or basin[z, x] or
                target_id not in adjacent or
                not _m4_lake_balance_segments_clear(_m4_lake_balance_np.asarray([current_id]), _m4_lake_balance_np.asarray([target_id]), domain & ~protected)[0] or
                terrain[z, x] > terrain[tuple(current)] + 1e-9):
            raise ValueError("spill path violates domain, protection or irregular graph adjacency")
    if len({tuple(point) for point in downstream}) != len(downstream):
        raise ValueError("spill path contains a cycle")
    if terrain[tuple(downstream[-1])] > recipe.spill_stage_m + 1e-9:
        raise ValueError("spill path does not reach a lower receiver")
    for z, x in _m4_lake_balance_np.argwhere(basin):
        cell_id = z * terrain.shape[1] + x
        for target in mesh.indices[mesh.indptr[cell_id]:mesh.indptr[cell_id + 1]]:
            nz, nx = divmod(int(target), terrain.shape[1])
            if not basin[nz,nx]:
                if (nz,nx) != spill and terrain[nz,nx] < recipe.spill_stage_m - 1e-9:
                    raise ValueError("basin has a lower unmodeled spill")
    area = spacing_x_m * spacing_z_m
    initial_volume = float(_m4_lake_balance_np.sum(_m4_lake_balance_np.maximum(0., recipe.initial_stage_m - terrain[basin])) * area)
    capacity = float(_m4_lake_balance_np.sum(_m4_lake_balance_np.maximum(0., recipe.spill_stage_m - terrain[basin])) * area)
    net = (recipe.inflow_m3_s - recipe.loss_m3_s) * recipe.duration_s
    before_spill = initial_volume + net
    overflow = max(0., before_spill - capacity)
    net_rate = recipe.inflow_m3_s - recipe.loss_m3_s
    time_to_spill = ((capacity - initial_volume) / net_rate if net_rate > 0 else _m4_lake_balance_math.inf)
    spill_duration = max(0., recipe.duration_s - max(0., time_to_spill))
    outflow = overflow / spill_duration if spill_duration > 0 else 0.
    balance_valid = before_spill >= -1e-9 and outflow <= recipe.max_outflow_m3_s + 1e-9
    final_volume = max(0., min(before_spill, capacity))
    residual = initial_volume + net - overflow - final_volume
    levels = _m4_lake_balance_np.unique(_m4_lake_balance_np.r_[terrain[basin], recipe.spill_stage_m])
    final_stage = float(levels[0])
    if final_volume >= capacity - 1e-9:
        final_stage = recipe.spill_stage_m
    else:
        cumulative = 0.
        for lower, upper in zip(levels[:-1], levels[1:]):
            wetted = int(_m4_lake_balance_np.count_nonzero(terrain[basin] <= lower))
            next_volume = cumulative + wetted * area * (upper - lower)
            if final_volume <= next_volume + 1e-9:
                final_stage = float(lower + (final_volume - cumulative) / (wetted * area))
                break
            cumulative = next_volume
    identity = _m4_lake_balance_ArtifactIdentity("Terragenesis", "lake-balance", BALANCE_VERSION, 0,
        {"source_identity": source_identity, "height_sha256": _m4_lake_balance_array_hash(terrain),
         "basin_sha256": _m4_lake_balance_array_hash(basin), "spill_grid_zx": list(spill),
         "downstream_path_sha256": _m4_lake_balance_array_hash(downstream), "domain_sha256": _m4_lake_balance_array_hash(domain),
         "protected_sha256": _m4_lake_balance_array_hash(protected),
         "legal_outlet_sha256": _m4_lake_balance_array_hash(legal),
         "spacing_x_m": float(spacing_x_m), "spacing_z_m": float(spacing_z_m),
         "origin_xz_m": list(map(float, origin_xz_m)), "world_seed": int(world_seed),
         **recipe.__dict__})
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": "diagnostic_not_publishable", "summary": {
                "initial_volume_m3": initial_volume, "spill_capacity_m3": capacity,
                "final_volume_m3": final_volume, "spill_outflow_m3_s": outflow,
                "final_stage_m": final_stage, "spill_duration_s": spill_duration,
                "balance_residual_m3": residual,
                "balance_valid": balance_valid,
                "limitation": "finite-duration constant supplied fluxes with idealized capped spill; no outlet rating curve or dynamic hydraulics"}}

# --- terrain_pipeline/new_world_game_fine_lake.py:7 ---
def minimax_cost(bed, allowed, seed):
    bed = _m4_new_world_game_fine_lake_np.asarray(bed, float); allowed = _m4_new_world_game_fine_lake_np.asarray(allowed, bool)
    if bed.shape != allowed.shape or not allowed[seed]:
        raise ValueError('seed must be inside finite allowed support')
    cost = _m4_new_world_game_fine_lake_np.full(bed.shape, _m4_new_world_game_fine_lake_np.inf); cost[seed] = bed[seed]
    previous = _m4_new_world_game_fine_lake_np.full((*bed.shape, 2), -1, _m4_new_world_game_fine_lake_np.int32)
    queue = [(float(bed[seed]), *seed)]
    while queue:
        h, r, c = _m4_new_world_game_fine_lake_heapq.heappop(queue)
        if h != cost[r, c]:
            continue
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == dc == 0:
                    continue
                y, x = r + dr, c + dc
                if not (0 <= y < bed.shape[0] and 0 <= x < bed.shape[1] and allowed[y, x]):
                    continue
                v = max(h, bed[y, x])
                if v < cost[y, x]:
                    cost[y, x] = v; previous[y, x] = (r, c); _m4_new_world_game_fine_lake_heapq.heappush(queue, (v, y, x))
    return cost, previous

# --- terrain_pipeline/new_world_game_fine_lake.py:31 ---
def invert_connected_storage(bed, cost, spill_m, volume_m3, identity):
    """Invert on seed-connected pre-spill cells; return storage and excess."""
    support = _m4_new_world_game_fine_lake_np.isfinite(cost) & (cost < spill_m) & (bed < spill_m)
    indices = _m4_new_world_game_fine_lake_np.flatnonzero(support)
    if not len(indices):
        raise ValueError('no connected pre-spill support')
    values = _m4_new_world_game_fine_lake_np.asarray(bed.flat[indices], dtype=_m4_new_world_game_fine_lake_np.float64)
    seed_id = int(indices[_m4_new_world_game_fine_lake_np.argmin(values)])
    lake = LakeStorage(indices.astype(_m4_new_world_game_fine_lake_np.int64), values, _m4_new_world_game_fine_lake_np.full(len(indices), 900., dtype=_m4_new_world_game_fine_lake_np.float64), seed_id,
                       float(spill_m), identity, 'minimax-connected-pre-spill-30m')
    retained = min(float(volume_m3), lake.capacity_m3)
    stage = lake.stage_at_volume(retained)
    # Cells gated by a saddle above stage must not be filled, so this inversion
    # is valid only if all cells below stage are reachable at that stage.
    if _m4_new_world_game_fine_lake_np.any((values < stage) & (cost.flat[indices] >= stage)):
        raise ValueError('internal saddle requires connected dynamic inversion')
    mask = _m4_new_world_game_fine_lake_np.zeros(bed.shape, bool); mask.flat[indices] = lake.wet_mask_at_stage(stage)
    return stage, retained, float(volume_m3)-retained, lake.capacity_m3, mask
