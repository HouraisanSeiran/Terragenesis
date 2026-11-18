"""Frozen tectonic conditioning for the physical TD checkpoint.

All queries use absolute coordinates. The product's finite rectangle is enforced;
its bilinear interpolation still wraps across the last half-cell at the edge.
"""
import re

import numpy as np

from diffusion.geography_physical import make_physical_map_factory
from diffusion.physical_config import PhysicalGenerationConfig
from terrain_pipeline.tectonic import load_product

# Historical defaults only; no longer enforced as hard checks. Callers pass the
# identity and seed recorded in their own skeleton manifest.
WORLD_SEED = 20261020
PLATE_IDENTITY = "b4c8bbdba29111b8c3ba3270e2f0d3a4fed3544655249fa07c506654b8ae6af9"
_HEX64 = re.compile(r"[0-9a-fA-F]{64}")


def make_plate_factory(source_path, expected_identity, seed, config):
    if not isinstance(expected_identity, str) or not _HEX64.fullmatch(expected_identity):
        raise ValueError("expected_identity must be 64 hexadecimal characters")
    if type(seed) is not int:
        raise ValueError("seed must be an int")
    if not isinstance(config, PhysicalGenerationConfig) or config.native_resolution_m != 30 or config.conditioning_spacing_m != 7680 or config.sea_datum_m != 0:
        raise ValueError("wrong physical grid or sea datum")
    product = load_product(source_path, expected_identity=expected_identity.lower())
    if product.identity != expected_identity.lower():
        raise ValueError("plate identity mismatch")
    if product.manifest["config"]["world_seed"] != seed:
        raise ValueError("plate world seed mismatch")
    physical = make_physical_map_factory(seed, config)

    def sample_raw(x1, z1, x2, z2):
        values = physical.sample_raw(x1, z1, x2, z2)
        x = np.arange(x1, x2, dtype=np.float64)[None, :] * config.conditioning_spacing_m
        z = np.arange(z1, z2, dtype=np.float64)[:, None] * config.conditioning_spacing_m
        elevation = product.sample(x, z, outside="reject")["elevation_m"]
        old_elevation = values[0].copy()
        # Approximate rebase: the physical climate has already been clipped, so
        # this cannot recover its unclipped lapse or precipitation terms.
        values[1] = np.clip(values[1] + .0065 * (np.maximum(old_elevation, 0) - np.maximum(elevation, 0)), -35, 38)
        values[3] = np.clip(values[3] + .08 * (np.maximum(old_elevation - 1800, 0) - np.maximum(elevation - 1800, 0)), 100, 3200)
        values[0] = elevation
        return values

    def sample_full(x1, z1, x2, z2):
        import torch
        values = physical.finalize(sample_raw(x1, z1, x2, z2))
        values[0] = np.sign(values[0]) * np.sqrt(np.abs(values[0]))
        return torch.from_numpy(values)

    sample_full.sample_raw = sample_raw
    sample_full.finalize = physical.finalize
    return sample_full


def conditioning_footprint(origin, side):
    """Conservative coarse-tile coverage, half-open conditioning indices.

    Pinned pipeline uses 64-cell tiles at stride 48; climate pads eight
    coarse cells and latent windows add four. The 12-cell expansion covers climate padding and the four-cell latent
    window; complete overlapping coarse tiles are then included.
    Every actual factory query still passes the finite source sampler.
    """
    if len(origin) != 2 or any(type(v) is not int for v in origin) or type(side) is not int or not 1 <= side <= 1337:
        raise ValueError("invalid native window")
    bounds = []
    for value in origin:
        low = value // 256 - 12
        high = -(-(value + side) // 256) + 12
        bounds.append((((low - 64) // 48 + 1) * 48, ((high - 1) // 48) * 48 + 64))
    return [bounds[0][0], bounds[1][0], bounds[0][1], bounds[1][1]]
