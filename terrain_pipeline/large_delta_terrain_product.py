"""Native-grid, finite-budget initialization of the mouth 5879 delta plain."""

import numpy as np
from scipy import ndimage


def make_product(bed, ocean, valid, footprint, *, spacing_m=30.0,
                 fine_origin_xz=(-12570.0, -59040.0),
                 coarse_origin_xz=(-12435.0, -58905.0), coarse_spacing_m=300.0,
                 solid_budget_m3=693094416.2372826, porosity=0.4,
                 footprint_expansion_m=0.0, full_depth_m=12.0, toe_depth_m=24.0):
    """Return deposit and derived bed; footprint samples are at coarse cell centers.

    Distances and slopes are metric. This is a geometric initialization, not a
    time-dependent sediment simulation. No cuts or external sediment are used.
    """
    bed = np.asarray(bed)
    ocean = np.asarray(ocean, dtype=bool)
    valid = np.asarray(valid, dtype=bool)
    footprint = np.asarray(footprint, dtype=bool)
    if bed.ndim != 2 or bed.shape != ocean.shape or bed.shape != valid.shape:
        raise ValueError('source arrays must have identical two-dimensional shapes')
    if (not np.isfinite(bed[valid]).all() or not (0 <= porosity < 1)
            or not np.isfinite(solid_budget_m3) or solid_budget_m3 < 0
            or not np.isfinite([footprint_expansion_m, full_depth_m, toe_depth_m]).all()
            or full_depth_m < 0 or toe_depth_m <= full_depth_m):
        raise ValueError('invalid bed or sediment budget')
    signed = (ndimage.distance_transform_edt(footprint) -
              ndimage.distance_transform_edt(~footprint)) * coarse_spacing_m
    rows = (fine_origin_xz[1] + np.arange(bed.shape[0]) * spacing_m - coarse_origin_xz[1]) / coarse_spacing_m
    cols = (fine_origin_xz[0] + np.arange(bed.shape[1]) * spacing_m - coarse_origin_xz[0]) / coarse_spacing_m
    coords = np.meshgrid(rows, cols, indexing='ij')
    distance = ndimage.map_coordinates(signed, coords, order=1, mode='constant', cval=-5000)
    # Smoothstep creates a continuous toe on both sides of the coarse envelope.
    u = np.clip((distance + footprint_expansion_m + 450.0) / 900.0, 0, 1)
    envelope = u * u * (3 - 2 * u)
    depth = np.maximum(-bed, 0)
    u = np.clip((toe_depth_m - depth) / (toe_depth_m - full_depth_m), 0, 1)
    depth_taper = u * u * (3 - 2 * u)
    z = fine_origin_xz[1] + np.arange(bed.shape[0]) * spacing_m
    target = np.clip(0.8 - (z[:, None] + 29040.0) * 0.000012, 0.4, 1.2)
    eligible = valid & ocean & (bed < 0)
    deposit = np.where(eligible, np.maximum(target - bed, 0) * envelope * depth_taper, 0)
    solid = float(np.sum(deposit, dtype=np.float64) * spacing_m**2 * (1 - porosity))
    if solid > solid_budget_m3:
        deposit *= solid_budget_m3 / solid
    derived = bed + deposit
    wet = valid & ocean & (derived < 0)
    labels, _ = ndimage.label(wet)
    edge = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])))
    edge = edge[edge != 0]
    connected_ocean = np.isin(labels, edge)
    return derived, deposit, connected_ocean


def plot_terrain(ax, bed, valid, extent_km, *, title='Terrain'):
    """Draw native elevations with metric hillshade on an existing axes.

    Extent is (left, right, bottom, top) in kilometres. Returns the image,
    leaving the axes available for network overlays.
    """
    from matplotlib.colors import BoundaryNorm, LightSource, ListedColormap

    colors = ['#254f6d', '#477e99', '#b1a777', '#c8c18d', '#d9d7a4',
              '#c1c998', '#9aa87f', '#758c68', '#65785c', '#8c8a73',
              '#b3ad9d', '#eee9df']
    bounds = [-10000, -20, 0, .4, 1.2, 3, 6, 10, 30, 100, 300, 800, 10000]
    cmap = ListedColormap(colors)
    rgba = cmap(BoundaryNorm(bounds, cmap.N)(bed))
    safe_bed = np.where(valid, bed, 0)
    shade = LightSource(azdeg=315, altdeg=45).hillshade(safe_bed, dx=30, dy=30, vert_exag=2)
    # Retain the low-relief plain and ocean palette while showing TD slopes.
    strength = np.where(bed >= 0, .30, .08)
    rgba[..., :3] *= (1 - strength + strength * shade)[..., None]
    rgba[..., 3] = valid
    image = ax.imshow(rgba, extent=extent_km, interpolation='nearest')
    ax.set(xlabel='x east (km)', ylabel='z south (km)', title=title)
    return image
