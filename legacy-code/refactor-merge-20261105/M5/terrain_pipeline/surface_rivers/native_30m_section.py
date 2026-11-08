"""Native 30 m cross-section builder; generation geometry is not dynamic erosion."""
from __future__ import annotations

import math
import numpy as np
from terrain_pipeline.geology import sample_lithology_points
from terrain_pipeline.lake import channel_width_from_lithology_m as channel_width_from_lithology_m
from terrain_pipeline.surface_rivers.metric_dynamic_feedback import normal_depth

_CELL_SIZE_M = 30.0
_EQUIVALENT_RUNOFF_MM_H = 1.0
_ALLOWED_PARAM_KEYS = (
    "world_seed", "manning_n", "max_depth_m", "min_width_m", "max_width_m",
    "reference_width_m", "reference_discharge_m3_s", "resample_stride",
)
_DEFAULTS = {
    "world_seed": 20261020, "manning_n": 0.035, "max_depth_m": 3.0,
    "min_width_m": 30.0, "max_width_m": 3000.0, "reference_width_m": 45.0,
    "reference_discharge_m3_s": 27.77777777777778, "resample_stride": 3,
}
_MANNING_TOL = 1e-8
_MAX_SAMPLES = 128


def _is_bool(x) -> bool:
    return isinstance(x, (bool, np.bool_))


def _as_finite_positive_scalar(x, name):
    if _is_bool(x):
        raise TypeError(f"{name} must not be boolean")
    if not isinstance(x, (int, float, np.integer, np.floating)):
        raise ValueError(f"{name} must be a real numeric scalar")
    try:
        v = float(x)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a finite number") from exc
    if not math.isfinite(v) or v <= 0.0:
        raise ValueError(f"{name} must be finite and > 0")
    return v


def _validate_parameters(section_parameters):
    if not isinstance(section_parameters, dict):
        raise TypeError("section_parameters must be an explicit dict")
    unknown = set(section_parameters) - set(_ALLOWED_PARAM_KEYS)
    if unknown:
        raise KeyError(f"unknown section_parameters keys: {sorted(unknown)}")
    params = dict(_DEFAULTS)
    params.update(section_parameters)
    seed = params["world_seed"]
    if _is_bool(seed) or not isinstance(seed, (int, np.integer)):
        raise TypeError("world_seed must be an integer")
    seed = int(seed)
    if seed < 0:
        raise ValueError("world_seed must be >= 0")
    stride = params["resample_stride"]
    if _is_bool(stride) or not isinstance(stride, (int, np.integer)):
        raise TypeError("resample_stride must be an integer")
    stride = int(stride)
    if stride < 1:
        raise ValueError("resample_stride must be >= 1")
    manning_n = _as_finite_positive_scalar(params["manning_n"], "manning_n")
    max_depth_m = _as_finite_positive_scalar(params["max_depth_m"], "max_depth_m")
    min_width_m = _as_finite_positive_scalar(params["min_width_m"], "min_width_m")
    max_width_m = _as_finite_positive_scalar(params["max_width_m"], "max_width_m")
    if max_width_m < min_width_m:
        raise ValueError("max_width_m must be >= min_width_m")
    reference_width_m = _as_finite_positive_scalar(params["reference_width_m"], "reference_width_m")
    reference_discharge_m3_s = _as_finite_positive_scalar(params["reference_discharge_m3_s"], "reference_discharge_m3_s")
    actual = {
        "world_seed": seed, "manning_n": manning_n, "max_depth_m": max_depth_m,
        "min_width_m": min_width_m, "max_width_m": max_width_m,
        "reference_width_m": reference_width_m,
        "reference_discharge_m3_s": reference_discharge_m3_s,
        "resample_stride": stride,
    }
    return actual


def _validate_selection(selection):
    if not isinstance(selection, dict):
        raise TypeError("selection must be a dict")
    if "chosen" not in selection:
        raise KeyError("selection must contain 'chosen'")
    chosen = selection["chosen"]
    if not isinstance(chosen, dict):
        raise TypeError("selection['chosen'] must be a dict")
    if "stem_flat_cells" not in chosen:
        raise KeyError("chosen must contain 'stem_flat_cells'")
    stem = np.asarray(chosen["stem_flat_cells"])
    if stem.ndim != 1:
        raise ValueError("stem_flat_cells must be a 1-D vector")
    if not np.issubdtype(stem.dtype, np.integer):
        raise TypeError("stem_flat_cells must be an integer vector")
    stem = stem.astype(np.int64, copy=False)
    if stem.size < 2:
        raise ValueError("stem_flat_cells must contain at least 2 nodes")
    if np.unique(stem).size != stem.size:
        raise ValueError("stem_flat_cells must not contain duplicates")
    return stem


def _validate_elevation(elevation_m):
    arr = np.asarray(elevation_m)
    if arr.ndim != 2:
        raise ValueError("elevation_m must be a 2-D array")
    if not isinstance(elevation_m, np.ndarray) or arr.dtype != np.float64:
        raise ValueError("elevation_m must be a float64 ndarray")
    if not arr.size:
        raise ValueError("elevation_m must not be empty")
    return arr


def _validate_origin(origin_native_xz):
    if origin_native_xz is None:
        raise TypeError("origin_native_xz must be provided")
    try:
        ox, oz = origin_native_xz
    except (TypeError, ValueError) as exc:
        raise TypeError("origin_native_xz must be a length-2 sequence") from exc
    for name, v in (("origin x", ox), ("origin z", oz)):
        if _is_bool(v) or not isinstance(v, (int, np.integer)):
            raise TypeError(f"{name} must be a signed integer")
    return int(ox), int(oz)


def _validate_design_q(design_q_m3_s):
    if _is_bool(design_q_m3_s):
        raise TypeError("design_q_m3_s must not be boolean")
    if not isinstance(design_q_m3_s, (int, float, np.integer, np.floating)):
        raise ValueError("design_q_m3_s must be a real numeric scalar")
    q = float(design_q_m3_s)
    if not math.isfinite(q) or q <= 0.0:
        raise ValueError("design_q_m3_s must be finite and > 0")
    return q


def build_section(elevation_m, selection, design_q_m3_s, *, origin_native_xz, section_parameters) -> dict:
    params = _validate_parameters(section_parameters)
    stem = _validate_selection(selection)
    field = _validate_elevation(elevation_m)
    ox, oz = _validate_origin(origin_native_xz)
    design_q = _validate_design_q(design_q_m3_s)
    rows, cols = np.divmod(stem, field.shape[1])
    if np.any(rows < 0) or np.any(rows >= field.shape[0]):
        raise ValueError("stem_flat_cells contains out-of-range row indices")
    node_cell_ids = (rows * field.shape[1] + cols).astype(np.int64)
    source_bed_m = np.asarray(field[rows, cols], dtype=np.float64)
    if not np.all(np.isfinite(source_bed_m)):
        raise ValueError("selected elevation nodes must be finite")
    for i in range(stem.size - 1):
        if not (source_bed_m[i] > source_bed_m[i + 1]):
            raise ValueError("source elevation along stem must strictly decrease downstream")
    stride = params["resample_stride"]
    n = int(stem.size)
    indices = np.unique(np.r_[np.arange(0, n - 1, stride, dtype=np.int64), np.int64(n - 1)])
    if indices.size > _MAX_SAMPLES or indices.size < 2:
        raise ValueError("resampled stem must contain between 2 and 128 nodes")
    actual_stride = float(stride)
    sub_rows = rows[indices]
    sub_cols = cols[indices]
    node_xz_m = np.stack([
        (ox + sub_cols.astype(np.float64)) * _CELL_SIZE_M,
        (oz + sub_rows.astype(np.float64)) * _CELL_SIZE_M,
    ], axis=1)
    source_bed_sub = source_bed_m[indices]
    dx = np.diff(node_xz_m[:, 0])
    dz = np.diff(node_xz_m[:, 1])
    seg_len = np.sqrt(dx * dx + dz * dz).astype(np.float64)
    if not np.all(np.isfinite(seg_len)) or np.any(seg_len <= 0.0):
        raise ValueError("resampled stem contains zero or non-finite segment length")
    slope_seg = (source_bed_sub[:-1] - source_bed_sub[1:]) / seg_len
    source_slope_per_m = np.empty_like(source_bed_sub)
    source_slope_per_m[:-1] = slope_seg
    source_slope_per_m[-1] = slope_seg[-1]
    length = seg_len
    full_stem_length_m = float(np.sum(seg_len))
    lith = sample_lithology_points(node_xz_m[:, 0], node_xz_m[:, 1], world_seed=params["world_seed"])
    bed_hardness = np.asarray(lith["bed_hardness"], dtype=np.float64)
    bank_hardness = np.asarray(lith["bank_hardness"], dtype=np.float64)
    equivalent_area_m2 = design_q / (_EQUIVALENT_RUNOFF_MM_H / 1000.0 / 3600.0)
    width_m = np.empty_like(source_bed_sub)
    normal_depth_m = np.empty_like(source_bed_sub)
    design_q_per_node = np.full_like(source_bed_sub, design_q)
    for i in range(source_bed_sub.size):
        w, _q = channel_width_from_lithology_m(
            np.array([equivalent_area_m2], dtype=np.float64),
            np.array([bed_hardness[i]], dtype=np.float64),
            np.array([bank_hardness[i]], dtype=np.float64),
            reference_discharge_m3_s=params["reference_discharge_m3_s"],
            reference_width_m=params["reference_width_m"],
            min_width_m=params["min_width_m"], max_width_m=params["max_width_m"],
            design_runoff_mm_h=_EQUIVALENT_RUNOFF_MM_H,
        )
        w = float(w[0])
        if not math.isfinite(w) or w <= 0.0:
            raise ValueError("invalid_width_from_lithology")
        depth = normal_depth(float(design_q_per_node[i]), w, float(source_slope_per_m[i]), params["manning_n"])
        depth = float(depth)
        if not math.isfinite(depth) or depth <= 0.0:
            raise ValueError("depth_budget_exceeded")
        if depth > float(params["max_depth_m"]):
            raise ValueError("depth_budget_exceeded")
        width_m[i] = w
        normal_depth_m[i] = depth
    for i in range(source_bed_sub.size):
        w = float(width_m[i])
        d = float(normal_depth_m[i])
        if w <= 0.0 or d <= 0.0:
            raise ValueError("invalid_hydraulic_section")
        slope = float(source_slope_per_m[i])
        q_check = ((1.0 / float(params["manning_n"])) * w * d
                   * ((w * d / (w + 2.0 * d)) ** (2.0 / 3.0))
                   * math.sqrt(max(slope, 0.0)))
        q_target = float(design_q_per_node[i])
        if q_target == 0.0:
            if abs(q_check) > 1e-8:
                raise ValueError("manning_roundtrip_mismatch")
        else:
            rel_err = abs(q_check - q_target) / abs(q_target)
            if not (rel_err <= 1e-8):
                raise ValueError("manning_roundtrip_mismatch")
    full_rows = rows
    full_cols = cols
    full_stem_length_m = 0.0
    if full_rows.size >= 2:
        dx = np.diff(full_rows.astype(np.float64))
        dz = np.diff(full_cols.astype(np.float64))
        seg = np.hypot(dx, dz) * float(_CELL_SIZE_M)
        full_stem_length_m = float(seg.sum())
    sampled_stem_length_m = float(seg_len.sum())
    length_difference_m = float(full_stem_length_m - sampled_stem_length_m)
    receiver = np.r_[np.arange(1, len(indices), dtype=np.int64), np.int64(-1)].astype(np.int64)
    arrays = {
        "node_cell_ids": node_cell_ids[indices], "node_xz_m": node_xz_m,
        "source_bed_m": source_bed_sub, "source_slope_per_m": source_slope_per_m,
        "width_m": width_m, "normal_depth_m": normal_depth_m,
        "design_q_m3_s": design_q_per_node, "bed_hardness": bed_hardness,
        "bank_hardness": bank_hardness, "receiver": receiver,
    }
    metadata = {
        "world_seed": params["world_seed"], "origin_native_xz": origin_native_xz,
        "actual_parameters": params, "actual_stride": params["resample_stride"],
        "full_stem_length_m": full_stem_length_m, "sampled_stem_length_m": sampled_stem_length_m,
        "length_difference_m": length_difference_m,
        "equivalent_area_not_physical_catchment": True, "normal_depth_not_bankfull": True,
        "generation_section_not_dynamic_erosion": True, "hydraulic_ready": False,
        "natural_outlet_certified": False,
    }
    return {"arrays": arrays, "metadata": metadata}
