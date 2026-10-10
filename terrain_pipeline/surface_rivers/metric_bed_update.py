"""Exner conversion for a bounded, one-way sediment replay."""

import numpy as np


def bed_from_inventory(initial_bed_m, initial_loose_solid_m3, loose_solid_m3,
                       rock_removed_m3, bed_area_m2, porosity):
    """Return bed elevation; rock and porous alluvium occupy distinct volumes."""
    return (initial_bed_m + (loose_solid_m3 - initial_loose_solid_m3)
            / ((1. - porosity) * bed_area_m2) - rock_removed_m3 / bed_area_m2)


def bed_rejection(initial_bed_m, next_bed_m, rock_floor_m, receiver,
                  water_depth_m, max_bed_change_m):
    if not np.isfinite(next_bed_m).all():
        return "nonfinite bed elevation"
    if np.any(next_bed_m < rock_floor_m - 1e-10):
        return "rock floor exceeded"
    if np.any(np.abs(next_bed_m - initial_bed_m) > max_bed_change_m + 1e-12):
        return "maximum cumulative bed change exceeded"
    wet = water_depth_m > 0.
    if np.any(wet & (next_bed_m - initial_bed_m >= water_depth_m)):
        return "deposition invalidates frozen water depth"
    edges = receiver >= 0
    if np.any(next_bed_m[edges] <= next_bed_m[receiver[edges]]):
        return "receiver bed slope reversed or flattened"
    return None
