"""Array contract shared by the finite ecology/coast processes; no IO or randomness."""
import numpy as np
from terrain_pipeline.environment_context import field


def frame(context, dt_s):
    height = np.asarray(context["height_m"], np.float64)
    spacing = float(context["spacing_m"])
    if (height.ndim != 2 or height.size > 1_000_000 or not np.isfinite(height).all()
            or not np.isfinite(spacing) or spacing <= 0.
            or not np.isfinite(dt_s) or dt_s < 0.):
        raise ValueError("bounded finite grid, positive spacing and nonnegative physical dt_s required")
    masks = {}
    for name in ("valid_mask", "protected_mask", "ocean_mask", "river_mask"):
        value = np.asarray(context[name])
        if value.dtype != bool or value.shape != height.shape:
            raise ValueError(name + " must be a same-shape boolean mask")
        masks[name] = value
    if type(context["world_seed"]) is not int or context["world_seed"] < 0:
        raise ValueError("explicit nonnegative world_seed required")
    origin = np.asarray(context["origin_native_xz"])
    if origin.shape != (2,) or not np.issubdtype(origin.dtype, np.integer):
        raise ValueError("integer native origin required")
    receiver = np.asarray(context["receiver"])
    if (receiver.shape != height.shape or not np.issubdtype(receiver.dtype, np.integer)
            or np.any((receiver < -1) | (receiver >= height.size))):
        raise ValueError("same-shape receiver indices required")
    return height.shape, spacing ** 2, masks


def stocks(state, names, shape, *, signed=()):
    if not isinstance(state, dict) or not set(names).issubset(state):
        raise ValueError("complete explicit state inventory required")
    return {name: field(state, name, shape, nonnegative=name not in signed) for name in names}


def metadata(algorithm, context, dt_s, limitations, parameters):
    return {"algorithm": algorithm, "world_seed": context["world_seed"],
            "origin_native_xz": list(map(int, context["origin_native_xz"])),
            "spacing_m": float(context["spacing_m"]), "dt_s": float(dt_s),
            "parameters": parameters, "forcing_semantics": "explicit_declared_scenario",
            "limitations": limitations, "default_world_registered": False}
