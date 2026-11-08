"""Suite-case coastal tide adapter. Coordinates are source cell centres in metres."""
from __future__ import annotations
import argparse
import hashlib
import heapq
import json
import time
from dataclasses import fields, replace
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_propagation
from terrain_pipeline.large_delta_tidal_dynamics import Geometry, State, step, tide_stage, save_checkpoint
from terrain_pipeline.large_delta_tidal_product_v4 import volume_stage
from terrain_pipeline.large_delta_tidal_reconstruction import reconstruct_coastal_water

HYDRO_ALGORITHM = 'suite-tidal-manning-subgrid-coast-v7'
CONTINUATION_VERSION = 'suite-tidal-continuation-v1'


def _sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _cells(a, nz, nx, block):
    return a.reshape(nz, block, nx, block).transpose(0, 2, 1, 3).reshape(nz * nx, block * block)


def _coastal_subgrid_faces(bed, coast_area, ocean, block, spacing):
    """Connected subpixel bottlenecks and represented widths between blocks.

    Every block uses an ocean pixel when available as its storage anchor;
    minimum-bottleneck paths to that anchor prevent separate low edges from
    bypassing higher interior terrain. Eight-neighbour corner connections have
    half a native-pixel width, a declared coarse-grid approximation.
    """
    height, width = bed.shape
    nz, nx = height//block, width//block
    levels = np.full(bed.shape, np.inf)
    available = coast_area > 0
    for z in range(nz):
        for x in range(nx):
            z0, x0 = z*block, x*block
            a = available[z0:z0+block, x0:x0+block]
            if not a.any():
                continue
            sea = a & ocean[z0:z0+block, x0:x0+block]
            candidates = sea if sea.any() else a
            local_bed = bed[z0:z0+block, x0:x0+block]
            k = int(np.argmin(np.where(candidates, local_bed, np.inf)))
            r, c = divmod(k, block)
            levels[z0+r, x0+c] = local_bed[r, c]
            queue = [(float(local_bed[r, c]), r, c)]
            while queue:
                value, r, c = heapq.heappop(queue)
                if value != levels[z0+r, x0+c]:
                    continue
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r+dr, c+dc
                        if (dr or dc) and 0 <= rr < block and 0 <= cc < block and a[rr, cc]:
                            next_level = max(value, float(local_bed[rr, cc]))
                            if next_level < levels[z0+rr, x0+cc]:
                                levels[z0+rr, x0+cc] = next_level
                                heapq.heappush(queue, (next_level, rr, cc))
    faces = []
    cell_area = spacing*spacing
    for z in range(nz):
        for x in range(nx):
            a = z*nx+x
            for dz, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
                zz, xx = z+dz, x+dx
                if zz >= nz or xx < 0 or xx >= nx:
                    continue
                candidates = []
                # Enumerate only adjacent native pixels at the shared edge or
                # corner. Diagonal crossings have half a pixel's width.
                for r in range(block):
                    for c in range(block):
                        ar, ac = z*block+r, x*block+c
                        if not available[ar, ac]:
                            continue
                        for dr in (-1, 0, 1):
                            for dc in (-1, 0, 1):
                                if not (dr or dc):
                                    continue
                                br, bc = ar+dr, ac+dc
                                if br//block != zz or bc//block != xx or not (0 <= br < height and 0 <= bc < width):
                                    continue
                                if not available[br, bc]:
                                    continue
                                sill = max(levels[ar, ac], levels[br, bc])
                                if not np.isfinite(sill):
                                    continue
                                fraction = min(coast_area[ar, ac], coast_area[br, bc])/cell_area
                                candidates.append((sill, dr != 0 and dc != 0, fraction*spacing))
                if not candidates:
                    continue
                sill = min(v[0] for v in candidates)
                best = [v for v in candidates if np.isclose(v[0], sill, rtol=0, atol=1e-9)]
                direct = [v[2] for v in best if not v[1]]
                face_width = sum(direct) if direct else .5*max(v[2] for v in best)
                faces.append((a, zz*nx+xx, sill, face_width,
                              block*spacing*(2**.5 if dz and dx else 1.)))
    # A diagonal is redundant when an equal-or-lower pair of cardinal
    # crossings already connects the same blocks. Removing those diagonals
    # preserves every crest-threshold component without duplicating open sea.
    cardinal = {(a, c): sill for a, c, sill, _, distance in faces if distance == block*spacing}
    retained = []
    for face in faces:
        a, c, sill, _, distance = face
        if distance > block*spacing:
            az, ax = divmod(a, nx)
            cz, cx = divmod(c, nx)
            mids = (az*nx+cx, cz*nx+ax)
            if any(max(cardinal.get(tuple(sorted((a, mid))), np.inf),
                       cardinal.get(tuple(sorted((mid, c))), np.inf)) <= sill for mid in mids):
                continue
        retained.append(face)
    return retained, levels


def prepare(case, manifest, hydro_spacing_m=600., reach_length_m=600., calibration='median'):
    spacing = float(manifest['source']['spacing_m'])
    origin = np.asarray(manifest['source']['origin_xz_m'], float)
    valid = np.asarray(case['valid'], bool)
    bed = np.asarray(case['final_bed_m'], float)
    ocean = np.asarray(case['ocean'], bool) & valid
    sections = np.asarray(case['sections'], float)
    parent = np.asarray(case['parent'], int)
    if spacing <= 0 or hydro_spacing_m < spacing or reach_length_m <= 0 or bed.shape != valid.shape:
        raise ValueError('invalid geometry')
    if not np.isfinite(bed[valid]).all() or not np.isfinite(sections).all():
        raise ValueError('nonfinite valid bed or sections')
    block = max(1, round(hydro_spacing_m / spacing))
    # Crop around the entire network, retaining every upstream source and outlet.
    rc = np.rint((sections[:, [2, 1]] - origin[::-1]) / spacing).astype(int)
    if np.any(rc < 0) or np.any(rc[:, 0] >= bed.shape[0]) or np.any(rc[:, 1] >= bed.shape[1]):
        raise ValueError('section outside source coordinates')
    margin = max(2 * block, int(np.ceil(10000 / spacing)))
    lo = np.maximum(0, (rc.min(axis=0) - margin) // block * block)
    hi = np.minimum(bed.shape, ((rc.max(axis=0) + margin + block) // block) * block)
    # Pad only outside source; padded cells are unknown and have zero area.
    size = ((hi - lo + block - 1) // block) * block
    nz, nx = size // block
    shape = tuple(size)
    def crop(array, fill):
        out = np.full(shape, fill, dtype=array.dtype)
        out[:hi[0]-lo[0], :hi[1]-lo[1]] = array[lo[0]:hi[0], lo[1]:hi[1]]
        return out
    local_valid = crop(valid, False)
    local_ocean = crop(ocean, False)
    local_bed = crop(np.where(valid, bed, 0.), 0.)
    owner = np.full(shape, -1, np.int32)
    fraction = np.zeros(shape, float)
    river_bed_sum = np.zeros(shape, float)
    node_rows = []
    branch_nodes = []
    cell_area = spacing * spacing
    # Assign each length-weighted section sample to nearby unclaimed pixel
    # area. Pixel fractions partition river and coast, including wide rivers.
    for bi in range(len(parent)):
        sec = sections[sections[:, 0] == bi]
        if len(sec) < 2:
            raise ValueError('branch needs at least two sections')
        seg = np.linalg.norm(np.diff(sec[:, 1:3], axis=0), axis=1)
        dist = np.r_[0., np.cumsum(seg)]
        weights = np.r_[seg[0]/2, (seg[:-1]+seg[1:])/2, seg[-1]/2]
        groups = np.floor(np.minimum(dist, max(dist[-1]-1e-7, 0)) / reach_length_m).astype(int)
        nodes = []
        for group in np.unique(groups):
            ids = np.flatnonzero(groups == group)
            node = len(node_rows)
            coords = np.rint((sec[ids][:, [2, 1]] - origin[::-1]) / spacing).astype(int) - lo
            width = float(np.average(sec[ids, 6], weights=weights[ids]))
            target = float(np.sum(weights[ids] * sec[ids, 6]))
            allocated = 0.
            # One shared pixel belongs to one reach; nearby pixels represent
            # the remaining analytic width without double counting area.
            for (row, col), sample in zip(coords, ids):
                remaining = float(weights[sample] * sec[sample, 6] / cell_area)
                radius = max(2, int(np.ceil(sec[sample, 6] / spacing)) + 1)
                offsets = sorted(((dr*dr+dc*dc, dr, dc) for dr in range(-radius, radius+1) for dc in range(-radius, radius+1)))
                for _, dr, dc in offsets:
                    y, x = row + dr, col + dc
                    if not (0 <= y < shape[0] and 0 <= x < shape[1] and local_valid[y, x]):
                        continue
                    if owner[y, x] not in (-1, node):
                        continue
                    take = min(remaining, 1. - fraction[y, x])
                    if take > 0:
                        owner[y, x] = node
                        fraction[y, x] += take
                        # Section cut bed describes the channel subpixel;
                        # the surrounding native pixel may be uncut upland.
                        sample_bed = sec[sample, 9] if sec.shape[1] > 9 else local_bed[row, col]
                        river_bed_sum[y, x] += take * sample_bed
                        remaining -= take
                        allocated += take * cell_area
                    if remaining < 1e-12:
                        break
                if remaining > 1e-8:
                    raise ValueError('insufficient valid area for analytic river footprint')
            if not np.isclose(allocated, target, rtol=1e-8, atol=1e-5):
                raise ValueError('river area mismatch')
            node_rows.append(dict(branch=bi, width=width, length=float(weights[ids].sum()),
                                  stage=float(np.average(sec[ids, 5], weights=weights[ids])),
                                  q=float(np.average(sec[ids, 8], weights=weights[ids]))))
            nodes.append(node)
        branch_nodes.append(nodes)
    n = nz * nx
    river_area = fraction * cell_area
    river_initial_bed = np.divide(river_bed_sum, fraction, out=np.zeros(shape), where=fraction > 0)
    coast_area = (1 - fraction) * cell_area * local_valid
    ca = _cells(coast_area, nz, nx, block)
    cb = _cells(local_bed, nz, nx, block)
    coast_sum = ca.sum(axis=1)
    active = coast_sum > 1e-6
    safe_area = np.where(active, coast_sum, 1.)
    mean = (ca * cb).sum(axis=1) / safe_area
    node_area = np.bincount(owner[owner >= 0], weights=river_area[owner >= 0], minlength=len(node_rows))
    node_bed = np.bincount(owner[owner >= 0], weights=(river_area * river_initial_bed)[owner >= 0], minlength=len(node_rows)) / node_area
    area = np.r_[safe_area, node_area]
    base = np.r_[mean, node_bed]
    porosity = float(manifest['scenario']['porosity'])
    if not 0 <= porosity < 1:
        raise ValueError('invalid porosity')
    floor = base - .25
    # Do not apply the shallow-coast mobile cover to deep offshore cells.
    # This also avoids interpreting the open-boundary head as seabed shear.
    floor[:n][mean < -20.] = base[:n][mean < -20.]
    floor[:n][~active] = 0.
    stock = (base - floor) * area * (1 - porosity)
    ocean_cells = (_cells(local_ocean, nz, nx, block) & (ca > 0)).any(axis=1).reshape(nz, nx)
    active_grid = active.reshape(nz, nx)
    perimeter = np.zeros((nz, nx), bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    # Also permit a real source edge where padding occurs, but never an
    # invalid-data boundary inside the source.
    edge = np.zeros(shape, bool)
    edge[0, :] = edge[-1, :] = True
    edge[:, 0] = edge[:, -1] = True
    edge[max(hi[0]-lo[0]-1, 0), :] = True
    edge[:, max(hi[1]-lo[1]-1, 0)] = True
    perimeter |= _cells(edge & local_valid, nz, nx, block).any(axis=1).reshape(nz, nx)
    connected = binary_propagation(perimeter & ocean_cells, mask=ocean_cells & active_grid)
    # As in the accepted coastal model, the perimeter-connected deep sea is
    # an offshore reservoir, not only the far edge of the rectangular crop.
    # Keep every river-containing block distinct from this prescribed tide.
    river_blocks = _cells(river_area, nz, nx, block).sum(axis=1).reshape(nz, nx) > 0
    offshore = connected & (perimeter | (mean.reshape(nz, nx) < -40.)) & ~river_blocks
    boundary = np.flatnonzero(offshore.ravel())
    if not len(boundary):
        raise ValueError('no source-ocean-connected offshore boundary in crop')
    left, right, cond, crest = [], [], [], []
    coast_faces, coast_widths = [], []
    sorted_idx = np.argsort(cb, axis=1)
    sorted_bed = np.take_along_axis(cb, sorted_idx, axis=1)
    sorted_area = np.take_along_axis(ca, sorted_idx, axis=1)
    # Faces follow actual connected native coast pixels, including diagonal
    # corner paths. Their crest is not a statistic of unrelated cell pixels.
    coast_links, coast_path_levels = _coastal_subgrid_faces(local_bed, coast_area, local_ocean, block, spacing)
    coast_distances = []
    for a, c, sill, face_width, distance in coast_links:
        coast_faces.append(len(left))
        coast_widths.append(face_width)
        coast_distances.append(distance)
        left.append(a); right.append(c); cond.append(280.)
        crest.append(sill - max(base[a], base[c]))
    # Fit a shared closure to input Q and source stage gradients; clamp near-
    # flat and adverse drops so no single section makes infinite resistance.
    fits = []
    fit_numerators = []
    fit_drops = []
    for bi, nodes in enumerate(branch_nodes):
        sec = sections[sections[:, 0] == bi]
        length = sum(node_rows[j]['length'] for j in nodes)
        drop = max(float(sec[0, 5] - sec[-1, 5]), .00005 * length, .05)
        numerator = max(node_rows[nodes[0]]['q'], 0.) * length / (max(node_rows[nodes[0]]['width'], 1.) * reach_length_m)
        fits.append(numerator / drop)
        fit_numerators.append(numerator)
        fit_drops.append(drop)
    if calibration == 'median':
        fitted = np.median(fits)
    elif calibration == 'weighted':
        numerator = np.asarray(fit_numerators)
        denominator = np.dot(numerator, fit_drops)
        fitted = np.dot(numerator, numerator) / denominator if denominator > 0 else 1.
    else:
        raise ValueError('unknown conveyance calibration')
    coefficient = float(np.clip(fitted, 1., 100.))
    river_faces, river_widths, river_distances = [], [], []
    def add_river(a, c, width):
        def half(node):
            return hydro_spacing_m/2 if node < n else node_rows[node-n]['length']/2
        distance = max(half(a) + half(c), spacing/2)
        river_faces.append(len(left)); river_widths.append(width); river_distances.append(distance)
        left.append(a); right.append(c); cond.append(width * coefficient * reach_length_m / distance); crest.append(0.)
    for bi, nodes in enumerate(branch_nodes):
        for a, c in zip(nodes[:-1], nodes[1:]):
            add_river(n+a, n+c, min(node_rows[a]['width'], node_rows[c]['width']))
        if parent[bi] >= 0:
            a, c = branch_nodes[parent[bi]][-1], nodes[0]
            add_river(n+a, n+c, min(node_rows[a]['width'], node_rows[c]['width']))
    leaves = [i for i in range(len(parent)) if i not in set(parent)]
    outlet_faces = []
    for bi in leaves:
        sec = sections[sections[:, 0] == bi]
        row, col = np.rint((sec[-1, [2, 1]]-origin[::-1])/spacing).astype(int)-lo
        coast = (row//block)*nx + col//block
        if not active[coast] or coast in boundary:
            raise ValueError('outlet lacks separate coastal storage')
        outlet_faces.append(len(left))
        add_river(n+branch_nodes[bi][-1], coast, node_rows[branch_nodes[bi][-1]]['width'])
    bank_sills = np.full(len(node_rows), np.nan)
    bank_faces = np.full(len(node_rows), -1, dtype=int)
    for node in range(len(node_rows)):
        rr, cc = np.where(owner == node)
        neigh = []
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            yy, xx = rr+dr, cc+dc
            good = (yy >= 0) & (yy < shape[0]) & (xx >= 0) & (xx < shape[1])
            yy, xx = yy[good], xx[good]
            good = local_valid[yy, xx] & (owner[yy, xx] < 0)
            neigh.extend(zip(yy[good], xx[good]))
        if neigh:
            coords = np.asarray(neigh)
            coast = int(np.bincount((coords[:, 0]//block)*nx+coords[:, 1]//block, minlength=n).argmax())
            bank = float(np.median(local_bed[coords[:, 0], coords[:, 1]]))
            bank_sills[node] = bank
            bank_faces[node] = len(left)
            left.append(n+node); right.append(coast); cond.append(280.); crest.append(bank-max(base[n+node], base[coast]))
    geom = Geometry(area, floor, np.asarray(left, int), np.asarray(right, int), np.asarray(cond), boundary, np.full(len(boundary), 280.), porosity,
                    np.asarray(river_faces, int), np.asarray(river_widths), np.asarray(river_distances),
                    .035, bank_faces[(bank_faces >= 0) & (bank_sills > base[n:])],
                    np.asarray([node_rows[i]['length'] for i in np.flatnonzero((bank_faces >= 0) & (bank_sills > base[n:]))]),
                    np.asarray(coast_faces, int), np.asarray(coast_widths), np.asarray(coast_distances))
    coast_water = (np.maximum(-cb, 0.) * ca * _cells(local_ocean, nz, nx, block)).sum(axis=1)
    river_counts = np.bincount(owner[owner >= 0], minlength=len(node_rows))
    river_sorted_bed = np.zeros((len(node_rows), int(river_counts.max())))
    river_sorted_area = np.zeros_like(river_sorted_bed)
    river_water = np.zeros(len(node_rows))
    for i, row in enumerate(node_rows):
        mask = owner == i
        heights, weights = river_initial_bed[mask], river_area[mask]
        order = np.argsort(heights)
        count = len(heights)
        river_sorted_bed[i, :] = heights.max() + 1e6
        river_sorted_bed[i, :count] = heights[order]
        river_sorted_area[i, :count] = weights[order]
        river_water[i] = np.dot(np.maximum(row['stage'] - heights, 0.), weights)
    state = State(0., np.r_[coast_water, river_water], stock.copy(), np.zeros(len(area)))
    return locals()


def _stages(p, state):
    g, n = p['geom'], p['n']
    current_bed = g.floor_m + state.bed_solid_m3 / ((1-g.porosity) * g.area_m2)
    stage = current_bed + state.water_m3 / g.area_m2
    shift = current_bed[:n] - p['base'][:n]
    stage[:n], wet = volume_stage(p['sorted_bed'], p['sorted_area'], state.water_m3[:n], shift)
    river_stage, river_wet = volume_stage(p['river_sorted_bed'], p['river_sorted_area'],
                                           state.water_m3[n:], current_bed[n:] - p['base'][n:])
    stage[n:] = river_stage
    return stage, np.r_[wet, river_wet]


def _project(p, state, iterations):
    n, block, nz, nx = p['n'], p['block'], p['nz'], p['nx']
    g = p['geom']
    initial = p['stock']
    diff = state.bed_solid_m3 - initial
    def expand(values):
        return np.repeat(np.repeat(values.reshape(nz, nx), block, 0), block, 1)
    # The reference stock may be any explicit thickness; it is already
    # included in the reference bed and must not be added a second time.
    delta = diff / (g.area_m2 * (1-g.porosity))
    coast_bed = p['local_bed'] + expand(delta[:n])
    river_bed = p['river_initial_bed'].copy()
    mask = p['owner'] >= 0
    river_bed[mask] += delta[n:][p['owner'][mask]]
    area = p['cell_area']
    native_bed = p['local_bed'] + ((coast_bed-p['local_bed'])*p['coast_area'] +
                                    (river_bed-p['river_initial_bed'])*p['river_area']) / area
    cb = _cells(coast_bed, nz, nx, block)
    order = np.argsort(cb, axis=1)
    levels, _ = volume_stage(np.take_along_axis(cb, order, axis=1), np.take_along_axis(p['ca'], order, axis=1), state.water_m3[:n], np.zeros(n))
    coast_depth = np.maximum(expand(levels)-coast_bed, 0.)
    river_depth = np.zeros(p['shape'])
    river_stage = np.full(p['shape'], np.nan)
    for i in range(len(p['node_rows'])):
        rr, cc = np.where(p['owner'] == i)
        heights = river_bed[rr, cc]
        weights = p['river_area'][rr, cc]
        order = np.argsort(heights)
        level, _ = volume_stage(heights[order][None, :], weights[order][None, :], state.water_m3[n+i:n+i+1], np.zeros(1))
        river_depth[rr, cc] = np.maximum(level[0]-heights, 0.)
        river_stage[rr, cc] = level[0]
    depth = (coast_depth*p['coast_area'] + river_depth*p['river_area'])/area
    pure = p['local_valid'] & (p['fraction'] == 0)
    if iterations:
        relaxed = reconstruct_coastal_water(native_bed, np.where(pure, area, 0.), np.where(pure, depth, 0.), iterations=iterations)
        depth[pure] = relaxed[pure]
    wet = (depth > 1e-10) & p['local_valid']
    seed_coarse = np.zeros(n, bool)
    seed_coarse[p['boundary']] = True
    seed = expand(seed_coarse) & p['local_ocean'] & wet
    sea = binary_propagation(seed, mask=wet)
    return dict(bed_m=native_bed, water_depth_m=depth,
                water_stage_m=np.where(wet, native_bed+depth, np.nan),
                river_stage_m=river_stage, river_depth_m=river_depth, channel_fraction=p['fraction'],
                coverage=p['local_valid'], water_class=np.where(sea, 1, np.where(wet, 2, 0)).astype(np.uint8))


def _advance_step(p, state, dt, source_water_m3_s, source_solid_m3_s):
    """The shared graph update, using the same hypsometry for every caller."""
    g = p['geom']
    stage, storage = _stages(p, state)
    def crest_available(donor, crest):
        result = np.empty(len(donor))
        for is_river in (False, True):
            mask = (donor >= p['n']) == is_river
            cells = donor[mask] - (p['n'] if is_river else 0)
            heights = p['river_sorted_bed'] if is_river else p['sorted_bed']
            areas = p['river_sorted_area'] if is_river else p['sorted_area']
            idx = donor[mask]
            current_bed = g.floor_m[idx] + state.bed_solid_m3[idx] / ((1-g.porosity)*g.area_m2[idx])
            shift = current_bed - p['base'][idx]
            below = (np.maximum(crest[mask, None] - heights[cells] - shift[:, None], 0.) * areas[cells]).sum(axis=1)
            result[mask] = np.maximum(state.water_m3[idx] - below, 0.)
        return result
    source = p['n'] + p['branch_nodes'][0][0]
    return step(g, state, dt, tide_stage(state.time_s + dt/2), source,
                source_water_m3_s, source_solid_m3_s, stage_override=stage,
                storage_area=storage, face_crest_offset=np.asarray(p['crest']),
                crest_available=crest_available)


def _geometry_identity(p, source_identity):
    """Hash all fixed storage curves, stock reference and hydraulic faces."""
    digest = hashlib.sha256()
    digest.update((CONTINUATION_VERSION + '\0' + HYDRO_ALGORITHM + '\0').encode('utf8'))
    digest.update(source_identity.encode('utf8'))
    g = p['geom']
    values = [p['origin'], np.asarray([p['spacing'], p['block'], g.porosity,
                                       g.river_roughness, g.coast_roughness]),
              p['lo'], p['hi'], p['owner'], p['river_area'], p['coast_area'],
              p['local_bed'], p['local_valid'], p['local_ocean'], p['river_initial_bed'],
              p['bank_sills'], p['bank_faces'], p['outlet_faces'],
              np.asarray([len(nodes) for nodes in p['branch_nodes']]),
              np.asarray([node for nodes in p['branch_nodes'] for node in nodes]),
              np.asarray([[r['branch'], r['width'], r['length'], r['stage'], r['q']] for r in p['node_rows']]),
              p['base'], p['stock'], p['sorted_bed'], p['sorted_area'],
              p['river_sorted_bed'], p['river_sorted_area'], p['parent'],
              p['crest'], g.area_m2, g.floor_m, g.left, g.right,
              g.conductance_m2_s, g.boundary_cell, g.boundary_conductance_m2_s,
              g.river_faces, g.river_width_m, g.river_distance_m,
              g.bank_faces, g.bank_length_m, g.coast_faces, g.coast_width_m,
              g.coast_distance_m]
    for value in values:
        array = np.ascontiguousarray(value)
        digest.update(array.dtype.str.encode('ascii'))
        digest.update(np.asarray(array.shape, dtype='<i8').tobytes())
        digest.update(array.tobytes())
    return digest.hexdigest()


def bind_continuation(prepared, reference_bed_solid_m3, *, source_identity, floor_m=None):
    """Bind an existing prepared geometry to explicit already-present stock.

    The returned dictionary shares immutable geometry arrays with the input;
    its floor and reference stock are independently bound. Geometry changes
    require caller-conservative transfer and a new identity.
    """
    if not isinstance(source_identity, str) or not source_identity or prepared['manifest']['source']['source_identity'] != source_identity:
        raise ValueError('source identity mismatch')
    p = dict(prepared)
    g = p['geom']
    stock = np.asarray(reference_bed_solid_m3, dtype=float)
    if (stock.shape != g.area_m2.shape or not np.isfinite(stock).all() or np.any(stock < 0)
            or np.any(stock[:p['n']][~p['active']] != 0)):
        raise ValueError('invalid reference bed stock')
    reference_floor = p['base'] - stock / ((1-g.porosity)*g.area_m2)
    if floor_m is not None:
        supplied = np.asarray(floor_m, dtype=float)
        if supplied.shape != reference_floor.shape or not np.isfinite(supplied).all() or not np.allclose(supplied, reference_floor, rtol=0, atol=1e-8):
            raise ValueError('floor inconsistent with reference bed and stock')
        reference_floor = supplied.copy()
    p['stock'] = stock.copy()
    p['geom'] = replace(g, floor_m=reference_floor)
    p['floor'] = reference_floor
    p['source_identity'] = source_identity
    p['algorithm_id'] = HYDRO_ALGORITHM
    p['geometry_id'] = _geometry_identity(p, source_identity)
    # Do not expose the default active-layer state as a valid seed.
    p['state'] = None
    return p


def prepare_continuation(case, manifest, reference_bed_solid_m3, *, source_identity,
                         floor_m=None, hydro_spacing_m=600., reach_length_m=600.,
                         calibration='median'):
    """Prepare and bind explicit stock to the supplied already-elevated bed."""
    if not isinstance(source_identity, str) or not source_identity or manifest['source']['source_identity'] != source_identity:
        raise ValueError('source identity mismatch')
    p = prepare(case, manifest, hydro_spacing_m, reach_length_m, calibration)
    return bind_continuation(p, reference_bed_solid_m3, source_identity=source_identity, floor_m=floor_m)


def _validate_seed(p, state, source_identity, geometry_id):
    if source_identity != p.get('source_identity') or geometry_id != p.get('geometry_id'):
        raise ValueError('source or geometry identity mismatch')
    if not isinstance(state, State):
        raise TypeError('state must be State')
    for name in ('water_m3', 'bed_solid_m3', 'mobile_solid_m3'):
        value = np.asarray(getattr(state, name))
        if (value.shape != p['geom'].area_m2.shape or not np.issubdtype(value.dtype, np.number)
                or not np.isfinite(value).all() or np.any(value < 0)
                or np.any(value[:p['n']][~p['active']] != 0)):
            raise ValueError('invalid state ' + name)
    for field in fields(State):
        if field.name in ('water_m3', 'bed_solid_m3', 'mobile_solid_m3'):
            continue
        value = getattr(state, field.name)
        if not np.isscalar(value) or not np.isfinite(value) or (field.name != 'wave_bed_transfer_m3' and value < 0):
            raise ValueError('invalid state ' + field.name)


def advance_prepared(prepared, state, *, source_identity, geometry_id, duration_s,
                     dt_s, source_water_m3_s, source_solid_m3_s):
    """Continue an exact seed, returning integrated exchanges and interval ledger."""
    p = prepared
    _validate_seed(p, state, source_identity, geometry_id)
    if not np.isfinite([duration_s, dt_s, source_water_m3_s, source_solid_m3_s]).all() or duration_s <= 0 or dt_s <= 0 or source_water_m3_s < 0 or source_solid_m3_s < 0:
        raise ValueError('invalid interval or source')
    s = State(**{f.name: (np.array(getattr(state, f.name), dtype=float, copy=True)
                          if f.name in ('water_m3', 'bed_solid_m3', 'mobile_solid_m3')
                          else float(getattr(state, f.name))) for f in fields(State)})
    start_time = s.time_s
    initial_water = float(s.water_m3.sum())
    initial_bed = float(s.bed_solid_m3.sum())
    initial_mobile = float(s.mobile_solid_m3.sum())
    counter_names = ('source_water_m3', 'source_solid_m3', 'sea_water_in_m3',
                     'sea_water_out_m3', 'sea_solid_out_m3')
    counters = {key: getattr(s, key) for key in counter_names}
    g = p['geom']
    exchanges = dict(internal_water_m3=np.zeros(len(g.left)), internal_solid_m3=np.zeros(len(g.left)),
                     boundary_water_m3=np.zeros(len(g.boundary_cell)), boundary_solid_m3=np.zeros(len(g.boundary_cell)))
    end_time = start_time + duration_s
    if not np.isfinite(end_time) or end_time <= start_time:
        raise ValueError('duration cannot advance physical time')
    while s.time_s < end_time:
        dt = min(dt_s, end_time-s.time_s)
        if s.time_s + dt <= s.time_s:
            raise ValueError('timestep cannot advance physical time')
        packet = _advance_step(p, s, dt, source_water_m3_s, source_solid_m3_s)
        for key in exchanges:
            exchanges[key] += packet[key]
    stage, _ = _stages(p, s)
    bed = g.floor_m + s.bed_solid_m3 / ((1-g.porosity)*g.area_m2)
    ledger = dict(initial_water_m3=initial_water, initial_bed_solid_m3=initial_bed,
                  initial_mobile_solid_m3=initial_mobile,
                  initial_solid_m3=initial_bed+initial_mobile,
                  final_water_m3=float(s.water_m3.sum()), final_bed_solid_m3=float(s.bed_solid_m3.sum()),
                  final_mobile_solid_m3=float(s.mobile_solid_m3.sum()))
    ledger.update({key: float(getattr(s, key)-counters[key]) for key in counter_names})
    ledger['water_residual_m3'] = initial_water+ledger['source_water_m3']+ledger['sea_water_in_m3']-ledger['sea_water_out_m3']-ledger['final_water_m3']
    ledger['solid_residual_m3'] = initial_bed+initial_mobile+ledger['source_solid_m3']-ledger['sea_solid_out_m3']-ledger['final_bed_solid_m3']-ledger['final_mobile_solid_m3']
    return dict(state=s, source_identity=source_identity, geometry_id=geometry_id,
                algorithm_id=HYDRO_ALGORITHM, continuation_version=CONTINUATION_VERSION,
                start_time_s=start_time, end_time_s=s.time_s, node_stage_m=stage,
                node_bed_m=bed, node_water_depth_m=s.water_m3/g.area_m2,
                exchanges=exchanges, ledger=ledger)


def save_continuation_checkpoint(path, prepared, state):
    """Save exact state and its source/geometry binding for restart."""
    _validate_seed(prepared, state, prepared['source_identity'], prepared['geometry_id'])
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    with path.open('xb') as stream:
        try:
            np.savez_compressed(stream, **vars(state), continuation_source_identity=prepared['source_identity'],
                                continuation_geometry_id=prepared['geometry_id'],
                                continuation_algorithm=HYDRO_ALGORITHM, continuation_version=CONTINUATION_VERSION)
        except Exception:
            stream.close()
            path.unlink(missing_ok=True)
            raise


def load_continuation_checkpoint(path, prepared, *, source_identity):
    """Load a checkpoint only against the same prepared reference geometry."""
    with np.load(path, allow_pickle=False) as data:
        if (str(data['continuation_source_identity']) != source_identity
                or str(data['continuation_geometry_id']) != prepared.get('geometry_id')
                or str(data['continuation_algorithm']) != HYDRO_ALGORITHM
                or str(data['continuation_version']) != CONTINUATION_VERSION):
            raise ValueError('checkpoint source or geometry identity mismatch')
        state = State(**{f.name: (data[f.name].copy() if data[f.name].ndim else float(data[f.name])) for f in fields(State)})
    _validate_seed(prepared, state, source_identity, prepared['geometry_id'])
    return state


def run_case(case_dir, output_dir, hours=24., *, hydro_spacing_m=600., reach_length_m=600.,
             dt_s=2.5, sediment_m3_s=.03, discharge_m3_s=None, relaxation_iterations=40,
             calibration='median'):
    """Run a source-bound short event and write a new independent product.

    The default 0.03 m3/s solid is an explicit illustrative event input, not
    catchment inference. The case's scenario discharge is used by default.
    """
    case_dir, output_dir = Path(case_dir), Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(output_dir)
    if hours <= 0 or dt_s <= 0 or sediment_m3_s < 0 or relaxation_iterations < 0:
        raise ValueError('invalid event parameters')
    manifest_path, product_path = case_dir/'manifest.json', case_dir/'product.npz'
    hashes = {'manifest.json': _sha(manifest_path), 'product.npz': _sha(product_path)}
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    with np.load(product_path, allow_pickle=False) as data:
        case = {k: data[k] for k in ('final_bed_m', 'valid', 'ocean', 'sections', 'parent')}
    q = float(manifest['scenario']['discharge_m3_s'] if discharge_m3_s is None else discharge_m3_s)
    if not np.isfinite([q, sediment_m3_s, hours, dt_s]).all() or q < 0:
        raise ValueError('invalid forcing')
    started = time.perf_counter()
    p = prepare(case, manifest, hydro_spacing_m, reach_length_m, calibration)
    g, s = p['geom'], p['state']
    water0, solid0 = float(s.water_m3.sum()), float(s.bed_solid_m3.sum())
    records = []
    node_stages = []
    instantaneous = []
    next_sample = 3600.
    faces = np.asarray(p['outlet_faces'])
    interval_water = np.zeros(len(faces))
    interval_solid = np.zeros(len(faces))
    interval_time = 0.
    duration = hours * 3600
    source = p['n'] + p['branch_nodes'][0][0]
    while s.time_s < duration - 1e-8:
        dt = min(dt_s, duration-s.time_s, next_sample-s.time_s)
        sea = tide_stage(s.time_s + dt/2)
        packet = _advance_step(p, s, dt, q, sediment_m3_s)
        interval_water += packet['internal_water_m3'][faces]
        interval_solid += packet['internal_solid_m3'][faces]
        interval_time += dt
        if s.time_s >= next_sample-1e-8 or s.time_s >= duration-1e-8:
            f = faces
            current = _stages(p, s)[0]
            node_stages.append(current[p['n']:].copy())
            instantaneous.append(packet['internal_water_m3'][f]/dt)
            records.append(np.r_[s.time_s, sea, interval_water/interval_time,
                                 interval_solid/interval_time, current[g.left[f]], current[g.right[f]]])
            interval_water[:] = 0.
            interval_solid[:] = 0.
            interval_time = 0.
            next_sample += 3600.
    projected = _project(p, s, relaxation_iterations)
    # Restore original full source shape, leaving unknown and outside-coverage
    # beds unchanged; water outside coverage is explicitly unknown.
    lo, hi = p['lo'], p['hi']
    local_slice = np.s_[:hi[0]-lo[0], :hi[1]-lo[1]]
    region = np.s_[lo[0]:hi[0], lo[1]:hi[1]]
    native = {}
    for key, value in projected.items():
        if key == 'bed_m':
            full = case['final_bed_m'].copy()
            local_valid = p['local_valid'][local_slice]
            full[region] = np.where(local_valid, value[local_slice], full[region])
        else:
            fill = np.nan if key in ('water_stage_m', 'river_stage_m') else 0
            full = np.full(case['valid'].shape, fill, dtype=value.dtype)
            full[region] = value[local_slice]
        native[key] = full
    native['origin_xz_m'] = p['origin']
    native['spacing_m'] = p['spacing']
    led = dict(initial_water_m3=water0, initial_active_solid_m3=solid0,
               source_water_m3=s.source_water_m3, source_solid_m3=s.source_solid_m3,
               sea_water_in_m3=s.sea_water_in_m3, sea_water_out_m3=s.sea_water_out_m3,
               sea_solid_out_m3=s.sea_solid_out_m3, final_water_m3=float(s.water_m3.sum()),
               final_bed_solid_m3=float(s.bed_solid_m3.sum()), final_mobile_solid_m3=float(s.mobile_solid_m3.sum()))
    led['water_residual_m3'] = water0+s.source_water_m3+s.sea_water_in_m3-s.sea_water_out_m3-led['final_water_m3']
    led['solid_residual_m3'] = solid0+s.source_solid_m3-s.sea_solid_out_m3-led['final_bed_solid_m3']-led['final_mobile_solid_m3']
    led['native_water_error_m3'] = float(projected['water_depth_m'].sum()*p['cell_area']-led['final_water_m3'])
    led['native_bed_delta_solid_m3'] = float(((projected['bed_m']-p['local_bed'])*p['local_valid']).sum()*p['cell_area']*(1-g.porosity))
    led['graph_bed_delta_solid_m3'] = float((s.bed_solid_m3-p['stock']).sum())
    result = dict(schema='suite-regional-tidal-v1', algorithm=HYDRO_ALGORITHM, input_case=str(case_dir.resolve()), input_sha256=hashes,
                  source_identity=manifest['source']['source_identity'], origin_xz_m=p['origin'].tolist(),
                  source_spacing_m=p['spacing'], hydro_spacing_m=p['block']*p['spacing'],
                  bounds_z0_z1_x0_x1=[int(lo[0]), int(hi[0]), int(lo[1]), int(hi[1])],
                  reach_length_target_m=reach_length_m, river_nodes=len(p['node_rows']), outlets=p['leaves'],
                  forcing=dict(discharge_m3_s=q, solid_m3_s=sediment_m3_s, hours=hours, dt_s=dt_s,
                               tide='illustrative M2 1 m and S2 0.35 m; absolute phase zero'),
                  assumptions=dict(active_layer_m=.25, deep_coast_active_layer_m=0., deep_coast_cutoff_m=-20., porosity=g.porosity, river_conveyance_coefficient= p['coefficient'],
                                   river_conveyance_calibration=calibration, legacy_fitted_coefficient_unused=True,
                                   manning_n_s_m_third=g.river_roughness,
                                   river_conveyance='rectangular wetted section, frozen Manning secant, implicit coupled storage',
                                   bank_conveyance='bank sill above river bed: one assumed broad overflow crest per reach, length equals reach length, coefficient 1.7; lower sills use legacy closure',
                                   coast_conveyance='explicit Manning section on valid native coast crossings; 8-neighbour bottleneck paths, corner width half pixel, n=0.04',
                                   geological_stock='input case initialization, excluded from event source',
                                   projection_iterations=relaxation_iterations),
                  ledger=led, elapsed_s=time.perf_counter()-started,
                  series_columns='time_s, sea_stage_m, preceding-interval mean signed outlet water m3/s, solid m3/s, end river stage m, end coast stage m; positive seaward',
                  limitations='Frozen rectangular Manning secant with tangent storage and proportional conservative donor/crest bound; coarse coast exchange is explicit and storage-limited; bank sills above the riverbed use one assumed reach-length crest; lower sills use the explicit closure. No momentum or waves; roughness and finite active layer assumed. Native depth is an area-weighted representation; outside coverage water unknown. Finite-domain source ocean connectivity is not open-ocean certification.')
    output_dir.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(output_dir/'native.npz', **native)
    np.savez_compressed(output_dir/'series.npz', records=np.asarray(records), outlet_branch=np.asarray(p['leaves']),
                        river_node_stage_m=np.asarray(node_stages), instantaneous_outlet_water_m3_s=np.asarray(instantaneous))
    np.savez_compressed(output_dir/'geometry.npz', area_m2=g.area_m2, floor_m=g.floor_m, left=g.left, right=g.right,
                        conductance_m2_s=g.conductance_m2_s, boundary=g.boundary_cell,
                        boundary_conductance_m2_s=g.boundary_conductance_m2_s, river_faces=g.river_faces,
                        river_width_m=g.river_width_m, river_distance_m=g.river_distance_m,
                        bank_overflow_faces=g.bank_faces, bank_overflow_length_m=g.bank_length_m,
                        coast_faces=g.coast_faces, coast_width_m=g.coast_width_m,
                        coast_distance_m=g.coast_distance_m, coast_path_level_m=np.where(np.isfinite(p['coast_path_levels']), p['coast_path_levels'], np.nan), face_crest_offset=np.asarray(p['crest']),
                        initial_bed_m=p['base'], initial_stock_m3=p['stock'], owner=p['owner'],
                        river_area_m2=p['river_area'], coast_area_m2=p['coast_area'],
                        sorted_bed_m=p['sorted_bed'], sorted_area_m2=p['sorted_area'], outlet_faces=p['outlet_faces'],
                        node_branch=np.array([r['branch'] for r in p['node_rows']]),
                        node_width_m=np.array([r['width'] for r in p['node_rows']]),
                        node_length_m=np.array([r['length'] for r in p['node_rows']]),
                        river_initial_bed_m=p['river_initial_bed'], river_sorted_bed_m=p['river_sorted_bed'],
                        river_sorted_area_m2=p['river_sorted_area'], bank_sill_m=p['bank_sills'],
                        bank_faces=p['bank_faces'],
                        branch_parent=p['parent'], bounds_z0_z1_x0_x1=np.array([lo[0], hi[0], lo[1], hi[1]]))
    save_checkpoint(output_dir/'checkpoint.npz', s)
    final_stage = _stages(p, s)[0]
    final_bed = g.floor_m + s.bed_solid_m3 / ((1-g.porosity)*g.area_m2)
    np.savez_compressed(output_dir/'node_state.npz', stage_m=final_stage, bed_m=final_bed,
                        water_depth_m=s.water_m3/g.area_m2, coast_node_count=p['n'])
    (output_dir/'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('case_dir')
    parser.add_argument('output_dir')
    parser.add_argument('--hours', type=float, default=24.)
    parser.add_argument('--dt', type=float, default=2.5)
    parser.add_argument('--hydro-spacing', type=float, default=600.)
    parser.add_argument('--reach-length', type=float, default=600.)
    parser.add_argument('--sediment', type=float, default=.03)
    parser.add_argument('--calibration', choices=('median', 'weighted'), default='median')
    args = parser.parse_args()
    print(json.dumps(run_case(args.case_dir, args.output_dir, hours=args.hours, dt_s=args.dt,
                              hydro_spacing_m=args.hydro_spacing, reach_length_m=args.reach_length,
                              sediment_m3_s=args.sediment, calibration=args.calibration), indent=2))


if __name__ == '__main__':
    main()
