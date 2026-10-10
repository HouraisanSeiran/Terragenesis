"""Immutable metre-grid and physical-interval contracts for river diagnostics."""

from dataclasses import dataclass
import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, readonly

MAX_CELLS = 1024 * 1024
MAX_FORCING_ENTRIES = 3 * MAX_CELLS
BOUNDARY_KINDS = ("interior", "open_outflow", "closed_wall", "prescribed_stage",
                  "prescribed_discharge", "unknown_boundary")


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("lowercase SHA256 required")


def _number(value, label, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(label + " must be numeric")
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(label + " must be finite" + (" positive" if positive else ""))


def _mask(values, shape, label):
    if not isinstance(values, np.ndarray) or values.dtype != bool or values.shape != shape:
        raise ValueError(label + " must be a matching boolean array")
    return readonly(values)


@dataclass(frozen=True)
class TerrainGrid:
    elevation_m: np.ndarray
    valid_mask: np.ndarray
    x0_m: float
    z0_m: float
    dx_m: float
    dz_m: float
    source_kind: str
    source_id: str
    source_sha256: str
    crs: str | None = None
    vertical_datum: str | None = None
    nodata_semantics: str = "unknown_is_not_traced"
    model_version: str | None = None
    generation_seed: int | None = None
    condition_summary: str | None = None
    source_path: str | None = None

    def __post_init__(self):
        height = self.elevation_m
        if not isinstance(height, np.ndarray) or height.dtype != np.float64 or height.ndim != 2 or not 1 <= height.size <= MAX_CELLS:
            raise ValueError("bounded float64 [z,x] elevation required")
        valid = _mask(self.valid_mask, height.shape, "valid_mask")
        if not valid.any() or not np.isfinite(height[valid]).all():
            raise ValueError("nonempty finite valid terrain required")
        for name in ("x0_m", "z0_m", "dx_m", "dz_m"):
            _number(getattr(self, name), name, name in ("dx_m", "dz_m"))
            object.__setattr__(self, name, float(getattr(self, name)))
        if not math.isfinite(self.dx_m * self.dz_m) or self.dx_m * self.dz_m <= 0.:
            raise ValueError("cell area overflows or underflows")
        if (not math.isfinite(self.x0_m + height.shape[1] * self.dx_m)
                or not math.isfinite(self.z0_m + height.shape[0] * self.dz_m)):
            raise ValueError("metric grid extent overflows")
        _sha(self.source_sha256)
        if self.source_kind not in ("generated_terrain", "conditioned_terrain", "observed_dem", "diagnostic_dem_proxy"):
            raise ValueError("unrecognized source_kind")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id required")
        for name in ("crs", "vertical_datum", "model_version", "condition_summary", "source_path"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("optional provenance must be nonempty text: " + name)
        if self.generation_seed is not None and (type(self.generation_seed) is not int or self.generation_seed < 0):
            raise ValueError("generation_seed must be a nonnegative integer or None")
        if self.nodata_semantics != "unknown_is_not_traced":
            raise ValueError("unsupported nodata_semantics")
        # Masked payload is canonicalized for hashes; it never participates in routing.
        object.__setattr__(self, "elevation_m", readonly(np.where(valid, height, 0.)))
        object.__setattr__(self, "valid_mask", valid)

    @property
    def cell_area_m2(self):
        return float(self.dx_m * self.dz_m)

    def world_xz(self, cell_id):
        if type(cell_id) is not int or not 0 <= cell_id < self.elevation_m.size:
            raise ValueError("cell_id outside grid")
        row, column = divmod(cell_id, self.elevation_m.shape[1])
        return float(self.x0_m + column * self.dx_m), float(self.z0_m + row * self.dz_m)

    @property
    def provenance_status(self):
        complete = bool(self.source_path and self.crs and self.vertical_datum)
        if self.source_kind in ("generated_terrain", "conditioned_terrain"):
            complete &= self.model_version is not None and self.generation_seed is not None and self.condition_summary is not None
        return "registered_provenance" if complete else "pending_provenance"

    def metadata(self):
        return {name: getattr(self, name) for name in self.__dataclass_fields__ if name not in ("elevation_m", "valid_mask")} | {
            "coordinates": "X east, Y up, Z south; arrays [z,x]; cell_id=z*nx+x",
            "provenance_status": self.provenance_status, "hydraulic_certification_allowed": False}

    @property
    def identity_sha256(self):
        return identity({"elevation_m": self.elevation_m, "valid_mask": self.valid_mask}, self.metadata())


@dataclass(frozen=True)
class BoundaryGrid:
    kind: np.ndarray
    allow_inflow: np.ndarray
    source_id: str
    source_sha256: str
    stage_m: np.ndarray | None = None
    discharge_m3_s: np.ndarray | None = None

    def __post_init__(self):
        if not isinstance(self.kind, np.ndarray) or self.kind.ndim != 2 or not 1 <= self.kind.size <= MAX_CELLS:
            raise ValueError("bounded 2D boundary kind array required")
        if not np.isin(self.kind, BOUNDARY_KINDS).all():
            raise ValueError("invalid boundary kind")
        inflow = _mask(self.allow_inflow, self.kind.shape, "allow_inflow")
        prescribed = np.isin(self.kind, ("prescribed_stage", "prescribed_discharge"))
        if np.any(inflow & ~prescribed):
            raise ValueError("only prescribed boundaries may allow inflow")
        _sha(self.source_sha256)
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("boundary source_id required")
        for key, kind in (("stage_m", "prescribed_stage"), ("discharge_m3_s", "prescribed_discharge")):
            value = getattr(self, key)
            selected = self.kind == kind
            if value is None:
                if selected.any():
                    raise ValueError(key + " required for prescribed boundary")
            else:
                if not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.shape != self.kind.shape or not np.isfinite(value).all():
                    raise ValueError(key + " must be matching finite float64")
                if np.any(value[~selected] != 0.):
                    raise ValueError(key + " must be zero outside its boundary kind")
                if key == "discharge_m3_s" and np.any((value < 0.) & ~inflow):
                    raise ValueError("negative prescribed outflow requires allow_inflow")
                object.__setattr__(self, key, readonly(value))
        object.__setattr__(self, "kind", readonly(self.kind.astype("U24")))
        object.__setattr__(self, "allow_inflow", inflow)

    @classmethod
    def from_outlet_mask(cls, terrain, outlet_mask, *, source_id, source_sha256):
        mask = _mask(outlet_mask, terrain.valid_mask.shape, "outlet_mask")
        perimeter = np.zeros(mask.shape, bool)
        perimeter[[0, -1], :] = True
        perimeter[:, [0, -1]] = True
        if np.any(mask & (~terrain.valid_mask | ~perimeter)):
            raise ValueError("outlet_mask must select valid perimeter cells")
        kind = np.full(mask.shape, "interior", dtype="U24")
        kind[perimeter] = "closed_wall"
        kind[~terrain.valid_mask] = "unknown_boundary"
        kind[mask] = "open_outflow"
        return cls(kind, np.zeros(mask.shape, bool), source_id, source_sha256)

    @property
    def outlet_mask(self):
        return readonly(np.isin(self.kind, ("open_outflow", "prescribed_stage", "prescribed_discharge")))

    @property
    def identity_sha256(self):
        arrays = {"kind": self.kind, "allow_inflow": self.allow_inflow}
        for name in ("stage_m", "discharge_m3_s"):
            if getattr(self, name) is not None:
                arrays[name] = getattr(self, name)
        return identity(arrays, {"source_id": self.source_id, "source_sha256": self.source_sha256,
                                 "positive_direction": "out_of_domain"})


@dataclass(frozen=True)
class RainfallForcing:
    time_seconds: np.ndarray  # T+1 physical interval endpoints, not output sampling.
    rain_mm_h: np.ndarray  # T interval-average cell intensities [T,z,x].
    source_id: str
    source_sha256: str
    temporal_semantics: str = "interval_average"
    spatial_semantics: str = "cell_average"
    missing_policy: str = "reject"

    def __post_init__(self):
        times, rain = self.time_seconds, self.rain_mm_h
        if not isinstance(times, np.ndarray) or times.dtype != np.float64 or times.ndim != 1 or not 2 <= times.size <= 100001:
            raise ValueError("float64 interval endpoints required")
        if not np.isfinite(times).all() or times[0] < 0. or np.any(np.diff(times) <= 0.):
            raise ValueError("strictly increasing nonnegative physical times required")
        if not isinstance(rain, np.ndarray) or rain.dtype != np.float64 or rain.ndim != 3 or rain.shape[0] != times.size - 1 or not 1 <= rain.size <= MAX_FORCING_ENTRIES or rain.shape[1] * rain.shape[2] > MAX_CELLS:
            raise ValueError("bounded float64 rain [T,z,x] matching T+1 endpoints required")
        if not np.isfinite(rain).all() or np.any(rain < 0.) or np.any(rain > 1e6):
            raise ValueError("finite bounded nonnegative rain required")
        if (self.temporal_semantics, self.spatial_semantics, self.missing_policy) != ("interval_average", "cell_average", "reject"):
            raise ValueError("forcing must declare interval_average/cell_average/reject")
        _sha(self.source_sha256)
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("forcing source_id required")
        object.__setattr__(self, "time_seconds", readonly(times))
        object.__setattr__(self, "rain_mm_h", readonly(rain))

    @property
    def interval_seconds(self):
        return readonly(np.diff(self.time_seconds))

    @property
    def rainfall_depth_mm(self):
        return readonly(self.rain_mm_h * (self.interval_seconds[:, None, None] / 3600.))

    @property
    def identity_sha256(self):
        return identity({"time_seconds": self.time_seconds, "rain_mm_h": self.rain_mm_h},
                        {name: getattr(self, name) for name in self.__dataclass_fields__
                         if name not in ("time_seconds", "rain_mm_h")})


@dataclass(frozen=True)
class RoutingGraph:
    receiver: np.ndarray
    order_downstream_first: np.ndarray
    valid_mask: np.ndarray
    edge_length_m: np.ndarray
    edge_slope: np.ndarray
    outlet_kind: np.ndarray
    lake_id: np.ndarray  # Catchment/terminal classification, not wet lake footprint.
    terrain_identity_sha256: str
    boundary_identity_sha256: str
    policy: str = "original_bed_d8_plateau_bfs_v1"

    def __post_init__(self):
        valid = self.valid_mask
        if not isinstance(valid, np.ndarray) or valid.dtype != bool or valid.ndim != 2 or not 1 <= valid.size <= MAX_CELLS or not valid.any():
            raise ValueError("bounded nonempty valid graph mask required")
        count = valid.size
        for name in ("receiver", "lake_id"):
            value = getattr(self, name)
            if not isinstance(value, np.ndarray) or value.dtype != np.int64 or value.shape != (count,):
                raise ValueError(name + " must be int64 [N]")
        receiver = self.receiver
        order = self.order_downstream_first
        cells = np.flatnonzero(valid)
        if not isinstance(order, np.ndarray) or order.dtype != np.int64 or not np.array_equal(np.sort(order), cells):
            raise ValueError("downstream order must be a permutation of valid cells")
        if np.any(receiver < -1) or np.any(receiver >= count) or np.any(receiver[~valid.ravel()] != -1):
            raise ValueError("receiver outside domain")
        donors = np.flatnonzero(receiver >= 0)
        if np.any(~valid.ravel()[receiver[donors]]):
            raise ValueError("receiver crosses unknown terrain")
        cols = valid.shape[1]
        targets = receiver[donors]
        dr = targets // cols - donors // cols
        dc = targets % cols - donors % cols
        if np.any((np.abs(dr) > 1) | (np.abs(dc) > 1) | ((dr == 0) & (dc == 0))):
            raise ValueError("routing edges must join adjacent D8 cells")
        diagonal = (dr != 0) & (dc != 0)
        if (np.any(~valid.ravel()[donors[diagonal] + dr[diagonal] * cols])
                or np.any(~valid.ravel()[donors[diagonal] + dc[diagonal]])):
            raise ValueError("receiver crosses unknown corner")
        rank = np.full(count, -1, np.int64)
        rank[order] = np.arange(len(order))
        if np.any(rank[receiver[donors]] >= rank[donors]):
            raise ValueError("cycle or invalid downstream-first order")
        for name in ("edge_length_m", "edge_slope"):
            value = getattr(self, name)
            if not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.shape != (count,) or not np.isfinite(value).all():
                raise ValueError(name + " must be finite float64 [N]")
            if np.any(value < 0.) or np.any(value[receiver < 0] != 0.):
                raise ValueError(name + " has negative or terminal values")
        if np.any(self.edge_length_m[donors] <= 0.):
            raise ValueError("positive edge lengths required")
        kinds = self.outlet_kind
        terminal_kinds = ("open_outflow", "prescribed_stage", "prescribed_discharge", "unknown_boundary", "lake_preserved")
        if not isinstance(kinds, np.ndarray) or kinds.shape != (count,) or not np.isin(kinds, ("interior", "inactive") + terminal_kinds).all():
            raise ValueError("invalid graph outlet_kind")
        terminal = valid.ravel() & (receiver < 0)
        if not np.isin(kinds[terminal], terminal_kinds).all() or np.any(kinds[donors] != "interior") or np.any(kinds[~valid.ravel()] != "inactive"):
            raise ValueError("terminal and active edge kinds differ")
        if np.any(self.lake_id < -1) or np.any(self.lake_id[~valid.ravel()] != -1):
            raise ValueError("invalid lake_id")
        if np.any(self.lake_id[terminal & (kinds == "lake_preserved")] < 0):
            raise ValueError("lake terminal ID required")
        _sha(self.terrain_identity_sha256)
        _sha(self.boundary_identity_sha256)
        if not isinstance(self.policy, str) or not self.policy.strip():
            raise ValueError("routing policy required")
        for name in ("receiver", "order_downstream_first", "valid_mask", "edge_length_m", "edge_slope", "outlet_kind", "lake_id"):
            object.__setattr__(self, name, readonly(getattr(self, name)))

    @property
    def donors(self):
        result = [[] for _ in range(self.receiver.size)]
        for cell in np.flatnonzero(self.receiver >= 0):
            result[int(self.receiver[cell])].append(int(cell))
        return tuple(tuple(values) for values in result)

    @property
    def topology_status(self):
        return "diagnostic_topology"

    @property
    def identity_sha256(self):
        return identity({name: getattr(self, name) for name in (
            "receiver", "order_downstream_first", "valid_mask", "edge_length_m", "edge_slope", "outlet_kind", "lake_id")},
            {"terrain_identity_sha256": self.terrain_identity_sha256,
             "boundary_identity_sha256": self.boundary_identity_sha256,
             "policy": self.policy, "status": self.topology_status})
