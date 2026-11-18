"""Consolidated surface_identity implementations; numeric expressions preserved."""
from __future__ import annotations
from collections.abc import Mapping as _i118_Mapping
from types import MappingProxyType as _i118_MappingProxyType
import hashlib as _i118_hashlib
import json as _i118_json
import math as _i118_math
import numpy as _i118_np
CATEGORY = 'B'

def _plain(value):
    if isinstance(value, _i118_Mapping):
        return {key: _plain(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(child) for child in value]
    return value

def _freeze(value):
    if isinstance(value, _i118_np.ndarray):
        return _i118_np.frombuffer(_i118_np.ascontiguousarray(value).tobytes(), dtype=value.dtype).reshape(value.shape)
    if isinstance(value, _i118_Mapping):
        return _i118_MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple((_freeze(child) for child in value))
    return value

def geometry_identity(arrays, metadata):
    digest = _i118_hashlib.sha256(_i118_json.dumps(metadata, sort_keys=True).encode('ascii'))
    for name in sorted(arrays):
        value = arrays[name]
        digest.update(name.encode('ascii'))
        digest.update(str(value.dtype).encode('ascii'))
        digest.update(_i118_np.asarray(value.shape, _i118_np.int64).tobytes())
        digest.update(value.tobytes())
    return digest.hexdigest()

def source_grid(source_m_per_interval, default_depth, core_cells):
    """Declared weathering depth per interval [m] on the core node lattice.

    Same injection discipline as `metric_domain_sediment`: `None` (the parameter
    default), a scalar, or a `(core+1, core+1)` grid. Anything else is an input
    error, never silently broadcast -- a mis-shaped field would move the whole
    budget.
    """
    shape = (core_cells + 1, core_cells + 1)
    if source_m_per_interval is None:
        return _i118_np.full(shape, float(default_depth), _i118_np.float64)
    if isinstance(source_m_per_interval, (bool, _i118_np.bool_)):
        raise ValueError('source_m_per_interval must be a number or grid, not a bool')
    if _i118_np.ndim(source_m_per_interval) == 0:
        value = float(source_m_per_interval)
        if not _i118_math.isfinite(value) or value < 0.0:
            raise ValueError('source_m_per_interval must be finite and nonnegative')
        return _i118_np.full(shape, value, _i118_np.float64)
    grid = _i118_np.asarray(source_m_per_interval, _i118_np.float64)
    if grid.shape != shape:
        raise ValueError('source_m_per_interval grid must have shape %s; got %s' % (shape, grid.shape))
    if not _i118_np.isfinite(grid).all() or _i118_np.any(grid < 0.0):
        raise ValueError('source_m_per_interval grid must be finite and nonnegative')
    return grid
