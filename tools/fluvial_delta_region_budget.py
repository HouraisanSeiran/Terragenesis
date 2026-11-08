"""Phase-wise sediment budget over fixed reference-defined delta regions.

The public function :func:`summarize_phase_regions` summarizes per-phase bed
change (bulk volumes, m^3) against regions fixed on a reference bed and,
separately, the endpoint budget implied by ``final_bed_m - reference_bed_m``.

Regions (all overlapping diagnostics, NOT independent ledger partitions):
  * ``region_all_ocean``     - every valid ocean cell.
  * ``region_near_sea_level``- valid ocean cells with |reference - sea_level| <= band_m.
  * ``region_above_sea_level``- valid ocean cells with reference > sea_level.

Reported JSON keys and meanings:
  * ``spacing_m``: cell size (m); cell area is ``spacing_m**2``.
  * ``sea_level_m``, ``band_m``: region definitions as passed in.
  * ``phase_names``: unique phase names in first-seen order.
  * ``cell_area_m2``: ``spacing_m**2``.
  * ``regions``: dict keyed by region name, each with
      - ``cell_count``: number of cells in the region.
      - ``area_m2``: ``cell_count * cell_area_m2``.
      - ``phase_net_m3``: per unique phase, sum of delta over region (m^3).
      - ``phase_positive_m3``: per phase, sum of positive deltas (>=0, m^3).
      - ``phase_negative_m3``: per phase, sum of negative deltas (<=0, m^3).
      - ``phase_net_total_m3``: sum over phases of phase_net_m3 (m^3).
      - ``endpoint_m3``: sum over region of (final-reference)*cell_area (m^3).
      - ``residual_m3``: ``endpoint_m3 - phase_net_total_m3`` (signed, preserved).
  * ``reference_area_m2``/``n_phases`` top-level keys are intentionally omitted.

Per-phase positive/negative bed-change volumes are NOT gross particle sediment
deposition/erosion: they are sign-split sums of the bulk bed change. Regions
overlap and must not be summed as independent partitions.

Inputs are not mutated. Invalid cells (where ``valid_mask`` is False) may hold
NaN and are excluded from finiteness checks and from all statistics. Finite
arrays are validated explicitly on ALL valid cells.
"""

from __future__ import annotations

import numpy as np


def summarize_phase_regions(
    phase_names,
    phase_delta_bulk_m3,
    reference_bed_m,
    final_bed_m,
    valid_mask,
    ocean_mask,
    spacing_m,
    sea_level_m=0.0,
    band_m=0.25,
):
    """Return a JSON-compatible phase/region budget dict (see module docstring)."""
    # ---- validate names -------------------------------------------------
    if isinstance(phase_names, str):
        raise TypeError("phase_names must be a sequence of strings, not a single str")
    try:
        names = list(phase_names)
    except TypeError as exc:
        raise TypeError("phase_names must be a sequence of strings") from exc
    for name in names:
        if not isinstance(name, str) or name.strip() == "":
            raise ValueError("phase_names entries must be non-empty strings")

    # ---- validate arrays / shapes ---------------------------------------
    delta = np.asarray(phase_delta_bulk_m3, dtype=np.float64)
    ref = np.asarray(reference_bed_m, dtype=np.float64)
    fin = np.asarray(final_bed_m, dtype=np.float64)
    if delta.ndim != 3:
        raise ValueError("phase_delta_bulk_m3 must have shape (N,H,W)")
    n_phase, height, width = delta.shape
    if n_phase != len(names):
        raise ValueError("len(phase_names) must equal phase_delta_bulk_m3.shape[0]")
    if ref.shape != (height, width) or fin.shape != (height, width):
        raise ValueError("reference_bed_m and final_bed_m must have shape (H,W)")
    if valid_mask.shape != (height, width) or ocean_mask.shape != (height, width):
        raise ValueError("valid_mask and ocean_mask must have shape (H,W)")
    if valid_mask.dtype != np.bool_ or ocean_mask.dtype != np.bool_:
        raise TypeError("valid_mask and ocean_mask must be boolean arrays")

    # ---- validate scalars -----------------------------------------------
    if not np.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("spacing_m must be positive and finite")
    if not np.isfinite(band_m) or band_m < 0:
        raise ValueError("band_m must be nonnegative and finite")
    if not np.isfinite(sea_level_m):
        raise ValueError("sea_level_m must be finite")

    # ---- unique phases in first-seen order ------------------------------
    unique, first_index = [], {}
    for i, name in enumerate(names):
        if name not in first_index:
            first_index[name] = i
            unique.append(name)

    # ---- finite check on ALL valid cells (single pass) -------------------
    if np.any(valid_mask):
        if not np.all(np.isfinite(ref[valid_mask])):
            raise ValueError("reference_bed_m has non-finite values on valid cells")
        if not np.all(np.isfinite(fin[valid_mask])):
            raise ValueError("final_bed_m has non-finite values on valid cells")
        for k in range(n_phase):
            if not np.all(np.isfinite(delta[k][valid_mask])):
                raise ValueError("phase_delta_bulk_m3 has non-finite values on valid cells")

    cell_area = float(spacing_m) ** 2
    ocean = valid_mask & ocean_mask
    near = ocean & (np.abs(ref - sea_level_m) <= band_m)
    above = ocean & (ref > sea_level_m)
    regions = {
        "region_all_ocean": ocean,
        "region_near_sea_level": near,
        "region_above_sea_level": above,
    }

    endpoint_change = fin - ref  # m, signed; volume conversion below
    out_regions = {}
    for rname, rmask in regions.items():
        count = int(np.count_nonzero(rmask))
        phase_net, phase_pos, phase_neg = {}, {}, {}
        net_total = 0.0
        for name in unique:
            total = 0.0
            pos = 0.0
            neg = 0.0
            for k in range(n_phase):
                if names[k] != name:
                    continue
                values = delta[k][rmask]
                total += float(values.sum(dtype=np.float64))
                pos += float(values[values > 0].sum(dtype=np.float64))
                neg += float(values[values < 0].sum(dtype=np.float64))
            phase_net[name] = total
            phase_pos[name] = pos
            phase_neg[name] = neg
            net_total += total
        endpoint_m3 = float(endpoint_change[rmask].sum(dtype=np.float64)) * cell_area
        out_regions[rname] = {
            "cell_count": count,
            "area_m2": count * cell_area,
            "phase_net_m3": phase_net,
            "phase_positive_m3": phase_pos,
            "phase_negative_m3": phase_neg,
            "phase_net_total_m3": net_total,
            "endpoint_m3": endpoint_m3,
            "residual_m3": endpoint_m3 - net_total,
        }

    return {
        "spacing_m": float(spacing_m),
        "sea_level_m": float(sea_level_m),
        "band_m": float(band_m),
        "phase_names": unique,
        "cell_area_m2": cell_area,
        "regions": out_regions,
    }
