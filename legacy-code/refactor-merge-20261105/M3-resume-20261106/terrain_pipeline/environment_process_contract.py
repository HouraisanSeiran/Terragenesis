"""Shared numeric contracts for gridded finite environment processes."""
import numpy as np


def _grid(context, dt_s):
    height = np.asarray(context["height_m"], dtype=float)
    spacing = float(context["spacing_m"])
    if (height.ndim != 2 or height.size == 0 or height.size > 262144
            or not np.isfinite(height).all() or not np.isfinite(spacing) or spacing <= 0
            or not np.isfinite(dt_s) or dt_s <= 0):
        raise ValueError("finite bounded height grid, positive spacing and physical seconds required")
    valid = _field(context.get("valid_mask", True), height.shape, "valid_mask").astype(bool)
    protected = _field(context.get("protected_mask", False), height.shape, "protected_mask").astype(bool)
    return height, spacing, valid & ~protected


def _field(value, shape, name, minimum=None, maximum=None):
    array = np.broadcast_to(np.asarray(value, dtype=float), shape).copy()
    if (not np.isfinite(array).all() or (minimum is not None and np.any(array < minimum))
            or (maximum is not None and np.any(array > maximum))):
        raise ValueError(f"invalid {name}")
    return array


def _parameters(parameters, defaults):
    values = dict(defaults)
    if parameters:
        if set(parameters) - set(values):
            raise ValueError("unknown process parameter")
        values.update(parameters)
    if any(not np.isfinite(value) or value <= 0 for value in values.values()):
        raise ValueError("process parameters must be finite and positive")
    return values

