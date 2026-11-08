"""Finite, explicitly supplied level-pool support and reduced outlet ratings."""

from dataclasses import dataclass, field
import math

import numpy as np

from terrain_pipeline.common_infra import readonly


MAX_LAKE_CELLS = 65536


def _finite_number(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)) or not math.isfinite(value):
        raise ValueError(name + " must be finite numeric")
    return float(value)


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("lowercase source SHA256 required")


@dataclass(frozen=True)
class LakeStorage:
    cell_ids: np.ndarray
    bed_elevation_m: np.ndarray
    cell_area_m2: np.ndarray
    seed_cell_id: int
    max_stage_m: float
    source_identity_sha256: str
    footprint_policy: str
    _levels_m: np.ndarray = field(init=False, repr=False, compare=False)
    _wetted_area_m2: np.ndarray = field(init=False, repr=False, compare=False)
    _break_volume_m3: np.ndarray = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        ids = self.cell_ids
        if not isinstance(ids, np.ndarray) or ids.dtype != np.int64 or ids.ndim != 1 or not 1 <= ids.size <= MAX_LAKE_CELLS or np.any(ids < 0) or np.unique(ids).size != ids.size:
            raise ValueError("bounded distinct nonnegative int64 cell IDs required")
        n = ids.size
        for name in ("bed_elevation_m", "cell_area_m2"):
            value = getattr(self, name)
            if not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.shape != (n,) or not np.isfinite(value).all():
                raise ValueError(name + " must be finite float64 per cell")
            if name == "cell_area_m2" and np.any(value <= 0.):
                raise ValueError("cell areas must be positive")
        if type(self.seed_cell_id) is not int or self.seed_cell_id < 0:
            raise ValueError("seed_cell_id must be a nonnegative integer")
        match = np.flatnonzero(ids == self.seed_cell_id)
        minimum = float(np.min(self.bed_elevation_m))
        if match.size != 1 or self.bed_elevation_m[match[0]] != minimum:
            raise ValueError("seed must occur at minimum lake bed")
        maximum = _finite_number(self.max_stage_m, "max_stage_m")
        if maximum <= minimum:
            raise ValueError("max_stage_m must exceed minimum bed")
        _sha(self.source_identity_sha256)
        if not isinstance(self.footprint_policy, str) or not self.footprint_policy.strip():
            raise ValueError("footprint_policy provenance required")

        levels, group = np.unique(self.bed_elevation_m, return_inverse=True)
        group_area = np.bincount(group, weights=self.cell_area_m2, minlength=levels.size)
        wet_area = np.cumsum(group_area)
        local_levels = levels - minimum
        break_volume = np.zeros(levels.size, dtype=np.float64)
        if levels.size > 1:
            break_volume[1:] = np.cumsum(np.diff(local_levels) * wet_area[:-1])
        last_active = int(np.searchsorted(levels, maximum, side="left") - 1)
        capacity = break_volume[last_active] + wet_area[last_active] * (maximum - levels[last_active])
        if not all(np.isfinite(x).all() for x in (wet_area, local_levels, break_volume)) or not math.isfinite(capacity) or capacity <= 0.:
            raise ValueError("lake area or capacity exceeds finite resource bounds")
        object.__setattr__(self, "cell_ids", readonly(ids))
        object.__setattr__(self, "bed_elevation_m", readonly(self.bed_elevation_m))
        object.__setattr__(self, "cell_area_m2", readonly(self.cell_area_m2))
        object.__setattr__(self, "max_stage_m", maximum)
        object.__setattr__(self, "_levels_m", readonly(levels))
        object.__setattr__(self, "_wetted_area_m2", readonly(wet_area))
        object.__setattr__(self, "_break_volume_m3", readonly(break_volume))

    @property
    def min_stage_m(self):
        return float(self._levels_m[0])

    @property
    def capacity_m3(self):
        return self.volume_at_stage(self.max_stage_m)

    def _checked_stage(self, stage):
        stage = _finite_number(stage, "stage")
        if not self.min_stage_m <= stage <= self.max_stage_m:
            raise ValueError("stage outside finite lake support")
        return stage

    def volume_at_stage(self, stage):
        stage = self._checked_stage(stage)
        index = int(np.searchsorted(self._levels_m, stage, side="left") - 1)
        if index < 0:
            return 0.
        return float(self._break_volume_m3[index]
                     + self._wetted_area_m2[index] * (stage - self._levels_m[index]))

    def stage_at_volume(self, volume):
        volume = _finite_number(volume, "volume")
        if not 0. <= volume <= self.capacity_m3:
            raise ValueError("volume outside finite lake capacity")
        if volume == 0.:
            return self.min_stage_m
        index = int(np.searchsorted(self._break_volume_m3, volume, side="right") - 1)
        index = min(index, int(np.searchsorted(self._levels_m, self.max_stage_m, side="left") - 1))
        return float(self._levels_m[index]
                     + (volume - self._break_volume_m3[index]) / self._wetted_area_m2[index])

    def wet_mask_at_stage(self, stage):
        return readonly(self.bed_elevation_m < self._checked_stage(stage))

    def depth_at_stage(self, stage):
        return readonly(np.maximum(self._checked_stage(stage) - self.bed_elevation_m, 0.))

    def surface_area_at_stage(self, stage):
        stage = self._checked_stage(stage)
        index = int(np.searchsorted(self._levels_m, stage, side="left") - 1)
        return 0. if index < 0 else float(self._wetted_area_m2[index])


@dataclass(frozen=True)
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
        crest = _finite_number(self.crest_stage_m, "crest_stage_m")
        coefficient = _finite_number(self.coefficient_m3_s_m15, "coefficient_m3_s_m15")
        if coefficient <= 0.:
            raise ValueError("outlet coefficient must be positive")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("outlet coefficient provenance required")
        object.__setattr__(self, "crest_stage_m", crest)
        object.__setattr__(self, "coefficient_m3_s_m15", coefficient)

    def discharge_at_stage(self, stage):
        stage = _finite_number(stage, "stage")
        with np.errstate(over="ignore", invalid="ignore"):
            discharge = self.coefficient_m3_s_m15 * max(stage - self.crest_stage_m, 0.) ** 1.5
        if not math.isfinite(discharge):
            raise ValueError("outlet discharge exceeds finite range")
        return discharge
