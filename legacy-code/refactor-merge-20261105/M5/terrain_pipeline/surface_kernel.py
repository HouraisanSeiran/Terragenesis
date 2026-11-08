"""Shared surface helpers (R3 step 1).

Verbatim bodies from surface_coast_drop (_plain, _freeze), surface_adaptive_geometry
(adaptive_geometry_identity, identical to surface_adaptive_io.geometry_identity) and
surface_rivers/metric_domain_coupled (_source_grid, executable code identical to
metric_domain_sediment._source_grid).  Equivalence: tests/test_hybrid_kernels_equivalence.py.
"""

from collections.abc import Mapping
from types import MappingProxyType
import hashlib
import json
import math

import numpy as np


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(child) for child in value]
    return value


def _freeze(value):
    if isinstance(value, np.ndarray):
        return np.frombuffer(np.ascontiguousarray(value).tobytes(), dtype=value.dtype).reshape(value.shape)
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(child) for child in value)
    return value


def geometry_identity(arrays, metadata):
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode("ascii"))
    for name in sorted(arrays):
        value = arrays[name]
        digest.update(name.encode("ascii"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(np.asarray(value.shape, np.int64).tobytes())
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
        return np.full(shape, float(default_depth), np.float64)
    if isinstance(source_m_per_interval, (bool, np.bool_)):
        raise ValueError("source_m_per_interval must be a number or grid, not a bool")
    if np.ndim(source_m_per_interval) == 0:
        value = float(source_m_per_interval)
        if not math.isfinite(value) or value < 0.0:
            raise ValueError("source_m_per_interval must be finite and nonnegative")
        return np.full(shape, value, np.float64)
    grid = np.asarray(source_m_per_interval, np.float64)
    if grid.shape != shape:
        raise ValueError("source_m_per_interval grid must have shape %s; got %s"
                         % (shape, grid.shape))
    if not np.isfinite(grid).all() or np.any(grid < 0.0):
        raise ValueError("source_m_per_interval grid must be finite and nonnegative")
    return grid
