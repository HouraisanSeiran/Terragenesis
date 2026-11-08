"""Site, local frame and base surface for the complex delta network v1.

The delta is built in a rotated local metric frame (u seaward, v along shore).
Everything stored in the products is also expressible in absolute world metres
(X east, Z south) through ``local_to_world``; no sphere mapping is used.

TD (terrain-v3) supplies: coast position/orientation and the land behind the
coast.  The sea side is replaced by a *declared* gentle shelf because the TD
shelf at this site is only ~5-10 km wide before dropping to hundreds of metres.
"""
from __future__ import annotations

import hashlib
import math
import os
from dataclasses import asdict, dataclass

import numpy as np
from scipy import ndimage as ndi
from scipy.ndimage import map_coordinates

WORLD_SEED = 20261020
TD_DIR = os.path.join(".scratch", "river-upgrade-20261101", "terrain-v3")
TD_ORIGIN_CENTER_M = -61440.0   # centre of TD cell [0, 0] (native-event-v3 manifest origin_center_m)
TD_SPACING_M = 30.0


def derive_seed(purpose: str, *extra, world_seed: int = WORLD_SEED) -> int:
    """Stable sub-seed: SHA256('world_seed|purpose|extra...') first 8 bytes."""
    text = "|".join([str(world_seed), purpose] + [repr(e) for e in extra])
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def rng_for(purpose: str, *extra, world_seed: int = WORLD_SEED) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(derive_seed(purpose, *extra, world_seed=world_seed)))


@dataclass(frozen=True)
class SiteSpec:
    # World coordinates (X east, Z south, metres) of the inlet on the TD coast.
    anchor_world_m: tuple = (0.0, 0.0)
    alpha_deg: float = 45.0           # seaward direction: eu = (cos a, sin a) in (X, Z)
    u0_m: float = -4000.0
    v0_m: float = -24000.0
    nu: int = 1600
    nv: int = 1600
    spacing_m: float = 30.0
    # declared shelf (replaces TD sea bed)
    shelf_d0_m: float = 0.4
    shelf_slope: float = 1.0e-3       # m of depth per m of distance from TD land
    shelf_max_depth_m: float = 80.0

    def to_dict(self):
        return asdict(self)


def axes(spec: SiteSpec):
    a = math.radians(spec.alpha_deg)
    eu = np.array([math.cos(a), math.sin(a)])
    ev = np.array([math.sin(a), -math.cos(a)])   # proper rotation, u down / v right image is un-mirrored
    return eu, ev


def local_to_world(spec: SiteSpec, u, v):
    eu, ev = axes(spec)
    ax, az = spec.anchor_world_m
    u = np.asarray(u, float)
    v = np.asarray(v, float)
    return ax + u * eu[0] + v * ev[0], az + u * eu[1] + v * ev[1]


def world_to_local(spec: SiteSpec, X, Z):
    eu, ev = axes(spec)
    ax, az = spec.anchor_world_m
    dx = np.asarray(X, float) - ax
    dz = np.asarray(Z, float) - az
    return dx * eu[0] + dz * eu[1], dx * ev[0] + dz * ev[1]


def grid_centres(spec: SiteSpec):
    u = spec.u0_m + (np.arange(spec.nu) + .5) * spec.spacing_m
    v = spec.v0_m + (np.arange(spec.nv) + .5) * spec.spacing_m
    return u, v


def _td_open(td_dir=TD_DIR):
    bed = np.load(os.path.join(td_dir, "bed_m.npy"), mmap_mode="r")
    ocean = np.load(os.path.join(td_dir, "ocean_mask.npy"), mmap_mode="r")
    return bed, ocean


def find_anchor(td_dir=TD_DIR, t=0.30, alpha_deg=45.0):
    """Probe used once during site selection: coast crossing on the straight A-B segment."""
    _, ocean = _td_open(td_dir)
    a = math.radians(alpha_deg)
    eu = np.array([math.cos(a), math.sin(a)])
    A = np.array([2488., 1800.])
    B = np.array([2008., 2248.])
    P = A + t * (B - A)
    q = P - 400 * eu
    for k in range(1200):
        c = q + k * eu
        if ocean[int(round(c[1])), int(round(c[0]))]:
            # (X, Z) in world metres of the first ocean cell centre
            return (TD_ORIGIN_CENTER_M + c[0] * TD_SPACING_M, TD_ORIGIN_CENTER_M + c[1] * TD_SPACING_M)
    raise RuntimeError("no coast found")


def sample_td(spec: SiteSpec, td_dir=TD_DIR):
    """TD bed (m) and ocean flag resampled onto the local grid (bilinear / nearest)."""
    bed, ocean = _td_open(td_dir)
    u, v = grid_centres(spec)
    U, V = np.meshgrid(u, v, indexing="ij")
    X, Z = local_to_world(spec, U, V)
    ix = (X - TD_ORIGIN_CENTER_M) / TD_SPACING_M
    iz = (Z - TD_ORIGIN_CENTER_M) / TD_SPACING_M
    n = bed.shape[0]
    inside = (ix >= 0) & (ix <= n - 1) & (iz >= 0) & (iz <= n - 1)
    x0 = int(max(math.floor(ix[inside].min()) - 2, 0)); x1 = int(min(math.ceil(ix[inside].max()) + 3, n))
    z0 = int(max(math.floor(iz[inside].min()) - 2, 0)); z1 = int(min(math.ceil(iz[inside].max()) + 3, n))
    sub_b = np.array(bed[z0:z1, x0:x1], dtype=np.float64)
    sub_o = np.array(ocean[z0:z1, x0:x1], dtype=np.float64)
    coords = [np.clip(iz - z0, 0, sub_b.shape[0] - 1.001), np.clip(ix - x0, 0, sub_b.shape[1] - 1.001)]
    td_bed = map_coordinates(sub_b, coords, order=1, mode="nearest")
    td_ocean = map_coordinates(sub_o, coords, order=0, mode="nearest") > .5
    td_ocean = np.where(inside, td_ocean, True)           # outside TD tile: treat as open sea
    td_bed = np.where(inside, td_bed, -1.0)
    return td_bed, td_ocean, inside


def base_surface(spec: SiteSpec, td_bed, td_ocean):
    """Pre-delta surface: TD land unchanged, TD sea replaced by the declared shelf."""
    dist_m = ndi.distance_transform_edt(td_ocean) * spec.spacing_m
    depth = np.minimum(spec.shelf_d0_m + spec.shelf_slope * dist_m, spec.shelf_max_depth_m)
    base = np.where(td_ocean, -depth, np.maximum(td_bed, 0.0))
    return base, ~td_ocean
