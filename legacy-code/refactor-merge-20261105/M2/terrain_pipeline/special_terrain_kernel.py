"""Shared special-terrain helpers (R3 step 1).

Verbatim bodies from hybrid_rock_boolean._origin / special_terrain_l1_sinkhole.as_origin
(strict) and special_terrain_l1_uluru_flare / special_terrain_pillars3d (_origin with a
per-module default, inside_by_winding with a per-module winding_number).
Equivalence: tests/test_hybrid_kernels_equivalence.py.
"""

import numpy as np


def as_origin(origin):
    origin = np.asarray(origin, float)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("finite three-component local origin required")
    return origin


def make_origin_normalizer(DEFAULT_ORIGIN):
    """_origin of uluru_flare/pillars3d: None selects the module default."""
    def _origin(origin):
        origin = DEFAULT_ORIGIN.copy() if origin is None else np.asarray(origin, float)
        if origin.shape != (3,) or not np.isfinite(origin).all():
            raise ValueError("finite three-component local origin required")
        return origin
    return _origin


def make_inside_by_winding(winding_number):
    """inside_by_winding of uluru_flare/pillars3d for the module winding_number."""
    def inside_by_winding(record, point_world_xyz_m, origin):
        winding = winding_number(record["vertices_local_xyz_m"], record["triangles"],
                                 point_world_xyz_m, origin)
        return bool(round(winding) == 1), float(winding)
    return inside_by_winding
