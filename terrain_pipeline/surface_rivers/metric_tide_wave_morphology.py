"""Bounded tide and wave shaping for a frozen delta preview.

This is a derived coastal morphology stage.  It changes only open marine cells
near the first-marine boundary, conserves the signed bed-volume budget, and
never edits channel or upstream cells.  It is intentionally not a 2-D plume,
wave-resolving, or long-term shoreline model.
"""
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class TideWaveConfig:
    tide_range_m: float = 0.8
    # The tide is a snapshot of a periodic boundary forcing.  ``period_s``,
    # ``phase_rad`` and ``sea_level_m`` are kept explicit even though this
    # bounded bed stage does not solve the water column.
    period_s: float = 44714.0
    phase_rad: float = 0.0
    sea_level_m: float = 0.0
    wave_height_m: float = 0.6
    wave_length_m: float = 900.0
    wave_direction_rad: float = 0.0
    active_width_m: float = 3000.0
    max_change_m: float = 0.35
    deposition_bias: float = 0.35
    porosity: float = 0.4

    def validate(self):
        vals = (self.tide_range_m, self.wave_height_m, self.wave_length_m,
                self.active_width_m, self.max_change_m, self.period_s)
        if not all(math.isfinite(float(v)) and float(v) >= 0 for v in vals):
            raise ValueError("tide/wave magnitudes must be finite and nonnegative")
        if (self.wave_length_m <= 0 or self.active_width_m <= 0
                or self.max_change_m <= 0 or self.period_s <= 0):
            raise ValueError("period, wave length, active width and max change must be positive")
        if not all(math.isfinite(float(v)) for v in
                   (self.wave_direction_rad, self.phase_rad, self.sea_level_m)):
            raise ValueError("direction, phase and sea level must be finite")
        if not 0 <= self.deposition_bias <= 1 or not 0 <= self.porosity < 1:
            raise ValueError("bias and porosity outside range")


def _distance_to_mouth(mouth, spacing_m):
    """Return exact nearest-mouth distances without an ``(H, W, K)`` array.

    ``scipy``'s distance transform is linear in the grid size and is the
    normal path.  The fallback keeps temporary allocations bounded by using
    row and mouth tiles, so a large preview cannot exhaust memory merely
    because it has many mouth cells.
    """
    try:
        from scipy.ndimage import distance_transform_edt
    except ImportError:  # pragma: no cover - scipy is part of the workspace
        distance_transform_edt = None
    if distance_transform_edt is not None:
        # Zeros in the input are the mouth samples.  ``sampling`` converts
        # grid distances directly to metres.
        return distance_transform_edt(~np.asarray(mouth, dtype=bool),
                                      sampling=float(spacing_m))

    rows, cols = mouth.shape
    mouth_r, mouth_c = np.where(mouth)
    if mouth_r.size == 0:
        return np.full((rows, cols), np.inf, dtype=np.float64)
    out = np.empty((rows, cols), dtype=np.float64)
    # Tile both grid axes as well as mouth samples.  Tiling only rows still
    # creates a (row_tile, full_width, mouth_tile) temporary, which is large
    # enough to defeat the purpose on an 800x800 preview.
    row_tile, col_tile, mouth_tile = 32, 64, 512
    mouth_c = mouth_c.astype(np.float64, copy=False)
    mouth_r = mouth_r.astype(np.float64, copy=False)
    for r0 in range(0, rows, row_tile):
        r1 = min(rows, r0 + row_tile)
        for c0 in range(0, cols, col_tile):
            c1 = min(cols, c0 + col_tile)
            block = np.full((r1 - r0, c1 - c0), np.inf, dtype=np.float64)
            r = np.arange(r0, r1, dtype=np.float64)[:, None]
            c = np.arange(c0, c1, dtype=np.float64)[None, :]
            for k0 in range(0, mouth_r.size, mouth_tile):
                k1 = min(mouth_r.size, k0 + mouth_tile)
                # Only this bounded tile is broadcast; no grid-by-mouth array
                # is retained between iterations.
                dr = r[..., None] - mouth_r[k0:k1]
                dc = c[..., None] - mouth_c[k0:k1]
                block = np.minimum(block, np.sqrt(np.min(dr * dr + dc * dc, axis=2))
                                   * float(spacing_m))
            out[r0:r1, c0:c1] = block
    return out


def apply_tide_wave_morphology(height_m, marine_mask, channel_mask, *, spacing_m,
                               mouth_mask=None, config=None, snapshot_time_s=0.0):
    """Return a bounded derived bed and diagnostics.

    Tide is represented by a deterministic low-frequency cross-shore signal;
    waves add a directional alongshore signal.  The signal is attenuated away
    from ``mouth_mask`` (or the marine boundary), clipped, and projected to
    zero on channels and land.  Positive and negative bed changes are balanced
    by a scalar correction over active cells, so net solid volume is zero.
    """
    cfg = TideWaveConfig() if config is None else config
    if not isinstance(cfg, TideWaveConfig):
        raise TypeError("config must be TideWaveConfig")
    cfg.validate()
    if not math.isfinite(float(snapshot_time_s)):
        raise ValueError("snapshot_time_s must be finite")
    h = np.asarray(height_m, dtype=np.float64)
    marine = np.asarray(marine_mask, dtype=bool)
    channels = np.asarray(channel_mask, dtype=bool)
    if h.ndim != 2 or marine.shape != h.shape or channels.shape != h.shape:
        raise ValueError("height and masks must share a 2D shape")
    if not np.isfinite(h).all() or not math.isfinite(float(spacing_m)) or spacing_m <= 0:
        raise ValueError("invalid height or spacing")
    if np.any(marine & channels):
        raise ValueError("marine channel overlap violates first-marine gate")
    active = marine & ~channels
    if mouth_mask is None:
        # marine boundary cells are a deterministic proxy for the first-marine edge
        edge = np.zeros_like(active)
        edge[1:, :] |= active[1:, :] & ~active[:-1, :]
        edge[:-1, :] |= active[:-1, :] & ~active[1:, :]
        edge[:, 1:] |= active[:, 1:] & ~active[:, :-1]
        edge[:, :-1] |= active[:, :-1] & ~active[:, 1:]
        mouth = edge
    else:
        mouth = np.asarray(mouth_mask, dtype=bool)
        if mouth.shape != h.shape or np.any(mouth & ~active):
            raise ValueError("mouth mask must be marine non-channel cells")
    if not mouth.any() or not active.any():
        return {"height_m": h.copy(), "height_delta_m": np.zeros_like(h),
                "active_mask": active, "net_volume_m3": 0.0,
                "metadata": {"schema": "delta-tide-wave-derived-v1", "active_cells": 0}}
    rows, cols = h.shape
    rr, cc = np.indices(h.shape, dtype=np.float64)
    # A distance transform avoids the former O(H*W*K) temporary, which could
    # exhaust memory for the 800x800 preview when the mouth mask is wide.
    dist = _distance_to_mouth(mouth, spacing_m)
    envelope = np.exp(-dist / cfg.active_width_m)
    x = cc * spacing_m
    z = rr * spacing_m
    along = x * math.cos(cfg.wave_direction_rad) + z * math.sin(cfg.wave_direction_rad)
    cross = -x * math.sin(cfg.wave_direction_rad) + z * math.cos(cfg.wave_direction_rad)
    temporal_phase = (2 * math.pi * float(snapshot_time_s) / cfg.period_s
                      + cfg.phase_rad)
    tide = (cfg.tide_range_m * math.cos(temporal_phase)
            * np.cos(2 * math.pi * cross / max(cfg.active_width_m, spacing_m)))
    wave = cfg.wave_height_m * np.sin(2 * math.pi * along / cfg.wave_length_m)
    raw = envelope * (cfg.deposition_bias * tide + (1 - cfg.deposition_bias) * wave)
    raw[~active] = 0.0
    raw = np.clip(raw, -cfg.max_change_m, cfg.max_change_m)
    # balance deposition and erosion without touching protected cells
    positive = raw > 0
    negative = raw < 0
    if positive.any() and negative.any():
        p, n = float(raw[positive].sum()), float(-raw[negative].sum())
        if p > n: raw[positive] *= n / p
        elif n > p: raw[negative] *= p / n
    delta = raw
    result = h + delta
    area = float(spacing_m) ** 2
    return {"height_m": result, "height_delta_m": delta, "active_mask": active,
            "net_volume_m3": float(delta.sum() * area),
            "deposition_volume_m3": float(delta[delta > 0].sum() * area * (1 - cfg.porosity)),
            "erosion_volume_m3": float(-delta[delta < 0].sum() * area * (1 - cfg.porosity)),
            "metadata": {"schema": "delta-tide-wave-derived-v1", "active_cells": int(active.sum()),
                         "mouth_cells": int(mouth.sum()), "spacing_m": float(spacing_m),
                         "config": cfg.__dict__.copy(), "period_s": float(cfg.period_s),
                         "phase_rad": float(cfg.phase_rad), "snapshot_time_s": float(snapshot_time_s),
                         "sea_level_m": float(cfg.sea_level_m),
                         "sea_level_boundary": "fixed",
                         "scope": "marine bounded derived morphology"}}
