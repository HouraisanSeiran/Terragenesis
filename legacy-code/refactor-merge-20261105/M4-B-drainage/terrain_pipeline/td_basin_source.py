"""Pinned original TD bed and explicit finite engineering boundary masks."""

import math
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle, validate_source

PRIMARY_PATH = Path(__file__).resolve().parents[1] / "verification/mountain-real-td/mountain-run-20261001T080705728662Z/primary-source.npz"
PRIMARY_SHA256 = "6e7fdf63dc02e9f14e7d83550d0c5f806b42aa7f13367ea96012787bcf069382"
MAX_CELLS = 250_000


def make_td_source(height_m, *, spacing_m, origin_m_xz=(0, 0), valid_mask=None,
                   protected_mask=None, open_boundary_mask=None, source_sha256=None):
    height = np.asarray(height_m)
    if height.ndim != 2 or height.dtype.kind not in "fiu" or not 1 <= height.size <= MAX_CELLS:
        raise ValueError("bounded numeric [z,x] height required")
    if type(spacing_m) not in (float, int) or not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("positive finite metre spacing required")
    if len(origin_m_xz) != 2 or not all(type(value) in (float, int) and math.isfinite(value) for value in origin_m_xz):
        raise ValueError("finite origin x,z required")
    valid = np.ones(height.shape, bool) if valid_mask is None else np.asarray(valid_mask)
    protected = np.zeros(height.shape, bool) if protected_mask is None else np.asarray(protected_mask)
    opened = np.zeros(height.shape, bool) if open_boundary_mask is None else np.asarray(open_boundary_mask)
    for mask in (valid, protected, opened):
        if mask.shape != height.shape or mask.dtype != bool:
            raise ValueError("boolean mask shape mismatch")
    if not valid.any() or not np.isfinite(height).all():
        raise ValueError("finite bed and nonempty coverage required")
    perimeter = np.zeros(height.shape, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    if (opened & (~valid | ~perimeter)).any() or (protected & ~valid).any():
        raise ValueError("open boundary must be valid perimeter; protection must be known")
    if source_sha256 is not None and (not isinstance(source_sha256, str) or len(source_sha256) != 64 or
                                     any(character not in "0123456789abcdef" for character in source_sha256)):
        raise ValueError("invalid external source SHA256")
    arrays = {"height_m": readonly(height.astype(np.float64)), "valid_mask": readonly(valid),
              "protected_mask": readonly(protected), "open_boundary_mask": readonly(opened)}
    metadata = {"schema": "td-basin-source-v1", "spacing_m": float(spacing_m),
                "origin_m_xz": list(origin_m_xz), "source_sha256": source_sha256,
                "coordinates": "x east, z south; arrays [z,x]; cell_id=z*nx+x",
                "boundary": "explicit_engineering_open_faces_else_closed", "natural_outlet_verified": False}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}


def load_td_source(path=None):
    original = load_bundle(PRIMARY_PATH if path is None else path, expected_sha256=PRIMARY_SHA256,
                           validator=validate_source)
    arrays, metadata = original["arrays"], original["metadata"]
    if metadata["boundary"]["policy"] != "all_edges_open":
        raise ValueError("pinned primary boundary mismatch")
    opened = np.zeros(arrays["height_m"].shape, bool)
    opened[[0, -1], :] = True
    opened[:, [0, -1]] = True
    opened &= arrays["hydrology_mask"]
    return make_td_source(arrays["height_m"], spacing_m=metadata["spacing_m"],
                          origin_m_xz=metadata["origin_m_xz"], valid_mask=arrays["hydrology_mask"],
                          open_boundary_mask=opened, source_sha256=PRIMARY_SHA256)


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


def save_td_source(path, result):
    save_bundle(path, result, validator=validate_td_source)


def load_td_source_bundle(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_td_source)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external source identity mismatch")
    return result
