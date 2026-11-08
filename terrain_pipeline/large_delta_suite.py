"""Finite-inventory delta initialization on a coordinate-pinned regional source.

Initialization is geometric; it does not represent a specified elapsed time.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class Scenario:
    name: str
    anchor_xz_m: tuple[float, float]
    radius_m: float
    catchment_km2: float
    denudation_m: float
    delivery_fraction: float
    discharge_m3_s: float
    porosity: float = 0.4
    toe_depth_m: float = 30.0
    plain_slope_m_per_m: float = 0.00004
    coastal_plain_height_m: float = 0.7
    full_fill_depth_fraction: float = 0.8
    lobes_xzr_m: tuple[tuple[float, float, float], ...] = ()

    @property
    def solid_inventory_m3(self):
        return self.catchment_km2 * 1e6 * self.denudation_m * self.delivery_fraction


def initialize(bed_m, valid, ocean, origin_xz_m, spacing_m, scenario):
    """Return a connected, coast-attached, finite-volume shelf deposit.

    The input ocean is source-declared; no unknown cells become ocean. The
    radial limit is physical distance and is not a claim of achieved extent.
    """
    bed = np.asarray(bed_m, dtype=float)
    valid = np.asarray(valid, dtype=bool)
    ocean = np.asarray(ocean, dtype=bool)
    if bed.ndim != 2 or valid.shape != bed.shape or ocean.shape != bed.shape:
        raise ValueError('incompatible source arrays')
    values = [*origin_xz_m, spacing_m, *scenario.anchor_xz_m, scenario.radius_m,
              scenario.catchment_km2, scenario.denudation_m, scenario.delivery_fraction,
              scenario.discharge_m3_s, scenario.porosity, scenario.toe_depth_m,
              scenario.plain_slope_m_per_m, scenario.coastal_plain_height_m, scenario.full_fill_depth_fraction]
    if (not np.isfinite(values).all() or not np.isfinite(bed[valid]).all()
            or spacing_m <= 0 or scenario.radius_m <= 0 or scenario.toe_depth_m <= 0
            or scenario.catchment_km2 <= 0 or scenario.denudation_m <= 0
            or not 0 < scenario.delivery_fraction <= 1 or scenario.discharge_m3_s <= 0
            or not 0 <= scenario.porosity < 1 or scenario.plain_slope_m_per_m < 0
            or scenario.coastal_plain_height_m < 0 or not 0 <= scenario.full_fill_depth_fraction < 1
            or np.any(ocean & ~valid)):
        raise ValueError('invalid source or scenario')
    if any(len(lobe) != 3 or not np.isfinite(lobe).all() or lobe[2] <= 0 for lobe in scenario.lobes_xzr_m):
        raise ValueError('invalid lobe support')
    x = origin_xz_m[0] + np.arange(bed.shape[1]) * spacing_m
    z = origin_xz_m[1] + np.arange(bed.shape[0]) * spacing_m
    radius = np.hypot(x[None, :] - scenario.anchor_xz_m[0], z[:, None] - scenario.anchor_xz_m[1])
    eligible = valid & ocean & (bed < 0) & (bed > -scenario.toe_depth_m) & (radius < scenario.radius_m)
    labels, count = ndimage.label(eligible, structure=np.ones((3, 3)))
    if not count:
        raise ValueError('no eligible shallow shelf')
    cells = np.argwhere(eligible)
    anchor = np.array([(scenario.anchor_xz_m[1] - origin_xz_m[1]) / spacing_m,
                       (scenario.anchor_xz_m[0] - origin_xz_m[0]) / spacing_m])
    nearest = tuple(cells[np.argmin(np.sum((cells - anchor)**2, axis=1))])
    shelf = labels == labels[nearest]
    shore = ndimage.distance_transform_edt(ocean) * spacing_m
    edge = ndimage.distance_transform_edt(np.pad(shelf, 1))[1:-1, 1:-1] * spacing_m
    taper = np.where(shore <= 2 * spacing_m, 1., np.clip(edge / max(3 * spacing_m, 300.), 0., 1.))
    taper *= np.clip((scenario.radius_m - radius) / max(.1 * scenario.radius_m, spacing_m), 0, 1)
    if scenario.lobes_xzr_m:
        support = np.zeros(bed.shape, float)
        for lx, lz, lr in scenario.lobes_xzr_m:
            distance = np.hypot(x[None, :] - lx, z[:, None] - lz)
            support = np.maximum(support, np.clip((lr-distance)/max(.12*lr, spacing_m), 0, 1))
        taper *= support
    # Full basin accommodation to the declared fraction of the depth bound;
    # remaining deeper cells taper smoothly to the preserved TD shelf edge.
    depth_taper = np.clip((scenario.toe_depth_m + bed) /
                          (scenario.toe_depth_m * (1-scenario.full_fill_depth_fraction)), 0, 1)
    # The coastal edge grades upward toward the declared landward apex.
    # This is a bounded geometric surface, not a simulated elapsed time.
    target = scenario.coastal_plain_height_m + scenario.plain_slope_m_per_m * np.maximum(scenario.radius_m - radius, 0.)
    deposit = np.where(shelf, np.maximum(target - bed, 0) * taper * depth_taper, 0.)
    required = float(deposit.sum(dtype=np.float64) * spacing_m**2 * (1 - scenario.porosity))
    if required > scenario.solid_inventory_m3:
        deposit *= scenario.solid_inventory_m3 / required
    retained = float(deposit.sum(dtype=np.float64) * spacing_m**2 * (1 - scenario.porosity))
    formed = bed + deposit
    emerged = shelf & (formed >= 0) & (deposit > .01)
    components, n = ndimage.label(emerged, structure=np.ones((3, 3)))
    if n:
        sizes = np.bincount(components.ravel()); sizes[0] = 0
        landform = components == sizes.argmax()
    else:
        landform = np.zeros(bed.shape, bool)
    # Width-sensitive metric prevents a narrow coastal thread from inflating
    # the reported extent. Core cells are at least 2 km inside the deposit.
    interior_distance = ndimage.distance_transform_edt(np.pad(landform, 1))[1:-1, 1:-1]*spacing_m
    core_labels, core_count = ndimage.label(interior_distance >= 2000., structure=np.ones((3, 3)))
    if core_count:
        sizes = np.bincount(core_labels.ravel()); sizes[0] = 0
        core = core_labels == sizes.argmax()
    else:
        core = np.zeros(bed.shape, bool)
    core_points = np.argwhere(core)
    core_span = np.ptp(core_points, axis=0)*spacing_m if len(core_points) else np.zeros(2)
    points = np.argwhere(landform)
    span = np.ptp(points, axis=0) * spacing_m if len(points) else np.zeros(2)
    return dict(bed_m=formed, deposit_m=deposit, landform=landform, shelf=shelf,
                required_solid_m3=required, retained_solid_m3=retained,
                unplaced_solid_m3=scenario.solid_inventory_m3-retained,
                landform_area_m2=float(landform.sum()*spacing_m**2),
                landform_span_zx_m=span.tolist(), core_2km_area_m2=float(core.sum()*spacing_m**2),
                core_2km_span_zx_m=core_span.tolist(), max_interior_distance_m=float(interior_distance.max()),
                anchor_cell_zx=[int(v) for v in nearest],
                plain_target_elevation_range_m=[float(target[shelf].min()), float(target[shelf].max())])


def load_source(path):
    """Read and verify the pinned source arrays before constructing a product."""
    path = Path(path)
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8-sig'))
    if manifest['schema'] != 'large-delta-regional-source-v1' or manifest['world_seed'] != 20261020:
        raise ValueError('unsupported source')
    arrays = []
    for name in ('bed_m', 'valid', 'ocean'):
        with (path / (name + '.npy')).open('rb') as stream:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != manifest['files_sha256'][name]:
            raise ValueError('source hash mismatch: ' + name)
        arrays.append(np.load(path / (name + '.npy'), allow_pickle=False))
    return manifest, arrays







