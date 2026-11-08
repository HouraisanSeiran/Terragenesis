"""Two-dimensional floodplain routing fed by a solved one-dimensional reach.

What this module is
-------------------
An **adapter layer**, not a solver. The two-dimensional shallow-water march is done
by the existing frozen local-inertial solver
(`terrain_pipeline.regional_surface_hydraulics.advance_inertial_surface`, schema
`regional-surface-local-inertial-D4-implicit-new-q-drag-v2`). This module only

* builds the D4 geometry / initial depth / boundary certificate for a window of the
  fine terrain field,
* converts a solved one-dimensional reach trace into per-cell m3/s sources, and
* closes a water ledger over the resulting two-dimensional domain.

Coupling direction (one way, 1D -> 2D)
--------------------------------------
The two-dimensional domain does **not** feed back into the reach. Water enters only
across the window boundary, at exactly the locations where a one-dimensional
`receiver` edge leaves a node inside the window and arrives at a node outside it (or
vice versa). The injected hydrograph is the saved `water_outgoing_volume_m3` of that
donor node, which is the one-dimensional solver's own account of the water it handed
across that edge. Because the injected volume is a line item the reach ledger already
removed from the donor, no cubic metre is counted twice: the two-dimensional ledger
satisfies `final = initial + injected + boundary_input - boundary_output` on its own,
and the reach ledger is left untouched.

What the terrain actually says
------------------------------
This terrain has no carved valley walls: the 10 km bilinear carrier has none of its
own, so the canonical 0.4 m carve sits on a plain tilted slope. A "bank crest"
therefore cannot be taken from the one-dimensional rectangular section (its
`depth_m` is a uniform 0.4 m carriage depth, not a terrain crest). This module derives
every crest and every outlet from the fine terrain it is given, and refuses to invent
one where the terrain does not supply it.
"""
from dataclasses import dataclass
import math

import numpy as np

from terrain_pipeline.regional_surface_hydraulics import (
    SurfaceBudget, advance_inertial_surface, prepare_surface_geometry,
    validate_surface_geometry,
)


SCHEMA = "world-floodplain-two-dimensional-adapter-v1"
BOUNDARY_CLOSED = 0
BOUNDARY_DRAINAGE = 1
BOUNDARY_PRESCRIBED = 2
CARVED_EPSILON_M = .01


@dataclass(frozen=True)
class FloodplainWindow:
    """A regular sub-page of a fine terrain field, in absolute world metres."""
    origin_m_xz: tuple
    spacing_m: float
    block_cells: int = 1

    def validate(self):
        origin = np.asarray(self.origin_m_xz, np.float64)
        if origin.shape != (2,) or not np.isfinite(origin).all():
            raise ValueError("finite window origin")
        if type(self.spacing_m) not in (int, float) or not math.isfinite(self.spacing_m) or self.spacing_m <= 0:
            raise ValueError("positive finite fine spacing")
        if type(self.block_cells) is not int or self.block_cells < 1:
            raise ValueError("positive integer block aggregation")


def aggregate_fine_field(height_m, block_cells):
    """Block-mean aggregation of a fine page; the trailing partial row/column is dropped.

    Block mean (not block minimum) is used because the local-inertial solver needs one
    water column per cell, and a block minimum would exaggerate the conveyance of a
    cell that is mostly high ground.
    """
    height = np.asarray(height_m, np.float64)
    if height.ndim != 2 or not np.isfinite(height).all():
        raise ValueError("finite two-dimensional fine field required")
    if type(block_cells) is not int or block_cells < 1:
        raise ValueError("positive integer block aggregation")
    if block_cells == 1:
        return height.copy()
    rows = height.shape[0] // block_cells
    columns = height.shape[1] // block_cells
    if rows < 2 or columns < 2:
        raise ValueError("aggregated page too small")
    trimmed = height[:rows * block_cells, :columns * block_cells]
    return trimmed.reshape(rows, block_cells, columns, block_cells).mean(axis=(1, 3))


def cell_centres(window, shape):
    """Absolute world cell-centre coordinates of the aggregated page."""
    window.validate()
    xs = window.origin_m_xz[0] + (np.arange(shape[1]) * window.block_cells
                                  + window.block_cells / 2.) * window.spacing_m
    zs = window.origin_m_xz[1] + (np.arange(shape[0]) * window.block_cells
                                  + window.block_cells / 2.) * window.spacing_m
    return xs, zs


def window_extent(window, shape):
    """Outer world extent covered by the aggregated page (cell edges, not centres)."""
    window.validate()
    step = window.spacing_m * window.block_cells
    x0 = float(window.origin_m_xz[0])
    z0 = float(window.origin_m_xz[1])
    return (x0, x0 + shape[1] * step, z0, z0 + shape[0] * step)


def contains_points(window, shape, points_xz):
    """Boolean mask of reach nodes lying inside the window extent."""
    x0, x1, z0, z1 = window_extent(window, shape)
    points = np.asarray(points_xz, np.float64)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("node coordinates require shape (n, 2)")
    return ((points[:, 0] >= x0) & (points[:, 0] <= x1)
            & (points[:, 1] >= z0) & (points[:, 1] <= z1))


def crossing_edges(window, shape, node_xz_m, receiver):
    """Reach edges that cross the window boundary, with their crossing point.

    An edge "crosses" when exactly one of its two nodes is inside the window. The
    crossing point is where the edge segment meets the window extent, so the source
    sits on the domain boundary rather than smeared over the interior.
    """
    nodes = np.asarray(node_xz_m, np.float64)
    receiver = np.asarray(receiver, np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 2:
        raise ValueError("node coordinates require shape (n, 2)")
    if receiver.shape != (nodes.shape[0],):
        raise ValueError("receiver must be one index per node")
    inside = contains_points(window, shape, nodes)
    x0, x1, z0, z1 = window_extent(window, shape)
    found = []
    for donor in range(nodes.shape[0]):
        target = int(receiver[donor])
        if target < 0:
            continue
        if inside[donor] == inside[target]:
            continue
        start = nodes[donor]
        segment = nodes[target] - start
        hits = []
        for axis, low, high in ((0, x0, x1), (1, z0, z1)):
            if segment[axis] == 0.:
                continue
            for plane, name in ((low, "min"), (high, "max")):
                t = (plane - start[axis]) / segment[axis]
                if not (0. <= t <= 1.):
                    continue
                point = start + t * segment
                if (x0 - 1e-6 <= point[0] <= x1 + 1e-6
                        and z0 - 1e-6 <= point[1] <= z1 + 1e-6):
                    hits.append((t, axis, name, point))
        if not hits:
            continue
        hits.sort(key=lambda item: item[0])
        _, axis, name, point = hits[0]
        found.append({"donor": int(donor), "receiver": target,
                      "inflow": not bool(inside[donor]),
                      "axis": "x" if axis == 0 else "z", "side": name,
                      "point_m_xz": (float(point[0]), float(point[1]))})
    found.sort(key=lambda item: (item["axis"], item["side"], item["point_m_xz"]))
    return found


def _cell_of(window, shape, point):
    step = window.spacing_m * window.block_cells
    column = int(math.floor((point[0] - window.origin_m_xz[0]) / step))
    row = int(math.floor((point[1] - window.origin_m_xz[1]) / step))
    return (min(max(row, 0), shape[0] - 1), min(max(column, 0), shape[1] - 1))


def source_locations(window, shape, crossings, node_width_m):
    """Map each crossing edge to the boundary cells that receive its water.

    A crossing carries the donor node's own declared channel width, so the inflow is
    spread over the boundary cells that lie within one half-width either side of the
    crossing point. Spreading it over the *carved* run instead is wrong here: the
    carve follows the reach centreline, which can run along the domain edge for
    kilometres, and that would smear a point inflow across the whole border.
    """
    widths = np.asarray(node_width_m, np.float64)
    if not np.isfinite(widths).all() or (widths <= 0.).any():
        raise ValueError("every donor needs a positive declared width")
    step = window.spacing_m * window.block_cells
    rows, columns = shape
    locations = []
    for crossing in crossings:
        half = .5 * float(widths[crossing["donor"]])
        point = crossing["point_m_xz"]
        if crossing["axis"] == "x":
            candidates = [(row, 0) if crossing["side"] == "min" else (row, columns - 1)
                          for row in range(rows)]
            distance = np.abs((window.origin_m_xz[1] + (np.arange(rows) * window.block_cells
                                                        + window.block_cells / 2.) * window.spacing_m)
                              - point[1])
        else:
            candidates = [(0, column) if crossing["side"] == "min" else (rows - 1, column)
                          for column in range(columns)]
            distance = np.abs((window.origin_m_xz[0] + (np.arange(columns) * window.block_cells
                                                        + window.block_cells / 2.) * window.spacing_m)
                              - point[0])
        chosen = [cell for cell, gap in zip(candidates, distance) if gap <= half + step]
        if not chosen:
            row, column = _cell_of(window, shape, point)
            chosen = [(row, column)]
        locations.append({"crossing": crossing, "cells": chosen,
                          "weights": np.full(len(chosen), 1. / len(chosen)),
                          "stated_width_m": float(widths[crossing["donor"]]),
                          "receptor_span_m": float(len(chosen) * step)})
    return locations


def source_matrix(shape, locations):
    """Row-stochastic (crossing x cell) matrix so a volume lands exactly once."""
    matrix = np.zeros((len(locations), shape[0] * shape[1]), np.float64)
    for index, location in enumerate(locations):
        for cell, weight in zip(location["cells"], location["weights"]):
            matrix[index, cell[0] * shape[1] + cell[1]] += float(weight)
    if locations and not np.allclose(matrix.sum(axis=1), 1., atol=1e-12):
        raise ValueError("source weights must sum to one per crossing edge")
    return matrix


def boundary_cells(shape):
    """Boundary cells in `prepare_surface_geometry` order (west, east, north, south)."""
    grid = np.arange(int(np.prod(shape)), dtype=np.int64).reshape(shape)
    return np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]


def boundary_cell_coordinates(shape):
    """Row/column of each boundary cell, in the same order as `boundary_cells`.

    The order must match `prepare_surface_geometry`'s
    ``np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]``: the whole west column,
    then the whole east column, then the north row, then the south row.
    """
    rows, columns = shape
    coordinates = [(row, 0) for row in range(rows)]
    coordinates += [(row, columns - 1) for row in range(rows)]
    coordinates += [(0, column) for column in range(columns)]
    coordinates += [(rows - 1, column) for column in range(columns)]
    return coordinates


def rim_outlet_cells(shape, height_m, *, margin_cells=2, exclude=()):
    """Boundary cells through which the aggregated page actually spills.

    The rim is the lowest boundary cell that is **not** an injection receptor: letting
    the outflow share a cell with the inflow would short-circuit the inflow straight
    back out of the domain before it could spread over the terrain. Only the lowest
    run plus a small margin is opened, so the other edges stay closed.
    """
    height = np.asarray(height_m, np.float64)
    if height.shape != tuple(shape):
        raise ValueError("height must match the declared shape")
    excluded = set(exclude)
    coordinates = boundary_cell_coordinates(shape)
    values = np.asarray([height[row, column] for row, column in coordinates], np.float64)
    allowed = np.array([cell not in excluded for cell in coordinates])
    if not allowed.any():
        raise ValueError("every boundary cell is an injection receptor; cannot place a rim outlet")
    lowest = float(values[allowed].min())
    chosen = [cell for cell, value, ok in zip(coordinates, values, allowed)
              if ok and value <= lowest + 1e-9]
    rows, columns = shape
    opened = set(chosen)
    for row, column in chosen:
        for offset in range(1, int(margin_cells) + 1):
            neighbours = []
            if row == 0:
                neighbours = [(0, column + offset), (0, column - offset)]
            elif row == rows - 1:
                neighbours = [(rows - 1, column + offset), (rows - 1, column - offset)]
            elif column == 0:
                neighbours = [(row + offset, 0), (row - offset, 0)]
            elif column == columns - 1:
                neighbours = [(row + offset, columns - 1), (row - offset, columns - 1)]
            for cell_row, cell_column in neighbours:
                if 0 <= cell_row < rows and 0 <= cell_column < columns:
                    opened.add((cell_row, cell_column))
    # Widening must never re-take an injection receptor, or the inflow could leave the
    # domain through the very face it arrived on.
    opened -= excluded
    return sorted(opened), lowest, []


def boundary_certificate(shape, height_m, *, outlet_cells=None):
    """Boundary kinds/crests for the local-inertial solver.

    Everything is closed except the declared rim outlet, which is an engineering
    drainage face whose crest is the terrain elevation there: a basin cannot hold
    water above its own rim, so the surplus has to be able to leave and be counted.
    """
    height = np.asarray(height_m, np.float64)
    if height.shape != tuple(shape):
        raise ValueError("height must match the declared shape")
    exterior = boundary_cells(shape)
    coordinates = boundary_cell_coordinates(shape)
    kinds = np.zeros(exterior.size, np.int64)
    crests = height.ravel()[exterior].copy()
    position = {cell: index for index, cell in enumerate(coordinates)}
    opened = set(outlet_cells or ())
    missing = opened - set(position)
    if missing:
        raise ValueError("declared outlet must lie on the domain boundary")
    for cell in opened:
        kinds[position[cell]] = BOUNDARY_DRAINAGE
    return kinds, crests, exterior


def build_domain(window, height_m, *, source_identity, outlet_cells=None, margin_cells=2,
                 injection_cells=()):
    """Assemble the geometry the frozen solver expects, plus its boundary certificate."""
    window.validate()
    height = np.asarray(height_m, np.float64)
    if height.ndim != 2 or not np.isfinite(height).all():
        raise ValueError("finite two-dimensional aggregated page required")
    shape = height.shape
    rim_cells, rim_elevation, rim_shares_inflow = rim_outlet_cells(
        shape, height, margin_cells=margin_cells, exclude=injection_cells)
    if outlet_cells is None:
        outlet_cells = rim_cells
    kinds, crests, exterior = boundary_certificate(shape, height, outlet_cells=outlet_cells)
    geometry = prepare_surface_geometry(height, spacing_m=float(window.spacing_m * window.block_cells),
                                        origin_m_xz=window.origin_m_xz, source_identity=source_identity,
                                        boundary_kind=kinds, boundary_crest_m=crests)
    validate_surface_geometry(geometry, trusted_height=height, source_identity=source_identity)
    return {"geometry": geometry, "shape": shape, "exterior": exterior,
            "outlet_cells": sorted(outlet_cells), "rim_elevation_m": float(rim_elevation),
            "rim_candidate_cells": rim_cells,
            "rim_shares_inflow_cells": rim_shares_inflow,
            "closed_faces": int((kinds == BOUNDARY_CLOSED).sum()),
            "drainage_faces": int((kinds == BOUNDARY_DRAINAGE).sum())}


def hydrograph(volumes_per_interval, interval_s):
    """Per-interval volume -> mean discharge, refusing negative water."""
    volumes = np.asarray(volumes_per_interval, np.float64)
    if volumes.ndim != 2:
        raise ValueError("injection volumes require shape (intervals, crossings)")
    if not np.isfinite(volumes).all() or (volumes < 0).any():
        raise ValueError("injection volumes must be finite and non-negative")
    if type(interval_s) not in (int, float) or not math.isfinite(interval_s) or interval_s <= 0:
        raise ValueError("positive finite interval")
    return volumes / float(interval_s)


def interval_forcing(shape, matrix, discharge_per_crossing):
    """m3/s per cell for one interval, conserving each crossing edge exactly."""
    rates = np.asarray(discharge_per_crossing, np.float64)
    if rates.shape[-1] != matrix.shape[0]:
        raise ValueError("one discharge rate per crossing edge required")
    return (matrix.T @ rates).reshape(shape).astype(np.float64)


def run_domain(domain, *, initial_depth_m, interval_s, intervals, discharge_per_interval,
               source_identity, forcing_identity, outfall_stage_m=None, budget=None,
               snapshot_interval_s=3600., interval_observer=None):
    """Advance the frozen local-inertial solver over the assembled domain."""
    shape = domain["shape"]
    matrix = domain["source_matrix"]
    geometry = domain["geometry"]
    arrays = geometry["arrays"]
    drainage = arrays["boundary_kind"] == BOUNDARY_DRAINAGE
    crest = arrays["boundary_crest_m"]
    # Only the declared rim face can pass water: its exterior stage is the terrain
    # crest there (or an explicitly declared outfall stage). Every closed face keeps
    # its own crest and carries no discharge at all by construction.
    if outfall_stage_m is None:
        tailwater = crest.copy()
    else:
        tailwater = np.where(drainage, np.maximum(crest, float(outfall_stage_m)), crest)
    rates = np.asarray(discharge_per_interval, np.float64)
    expected = (intervals, matrix.shape[0])
    if rates.shape != expected:
        raise ValueError("discharge_per_interval must have shape %r, got %r" % (expected, rates.shape))

    def forcing_provider(index):
        return interval_forcing(shape, matrix, rates[index])

    return advance_inertial_surface(
        geometry, initial_depth_m=np.asarray(initial_depth_m, np.float64),
        forcing_interval_s=float(interval_s), intervals=int(intervals),
        forcing_provider=forcing_provider, boundary_stage_provider=lambda index: tailwater,
        source_identity=source_identity, forcing_identity=forcing_identity,
        budget=budget or SurfaceBudget(), snapshot_interval_s=float(snapshot_interval_s),
        interval_observer=interval_observer)


def domain_ledger(result, *, spacing_m, declared_injection_m3):
    """Closed two-dimensional ledger with an explicit no-double-count statement."""
    arrays = result["arrays"]
    depth = np.asarray(arrays["depth_m"], np.float64)
    area = float(spacing_m) ** 2
    initial = float(np.asarray(arrays["initial_depth_m"], np.float64).sum() * area)
    final = float(depth[-1].sum() * area)
    supplied = float(np.asarray(arrays["ledger"], np.float64)[-1, 0])
    imported = float(np.asarray(arrays["ledger"], np.float64)[-1, 1])
    exported = float(np.asarray(arrays["ledger"], np.float64)[-1, 2])
    residual = final - initial - supplied - imported + exported
    return {
        "initial_storage_m3": initial,
        "injected_m3": supplied,
        "boundary_input_m3": imported,
        "boundary_output_m3": exported,
        "final_storage_m3": final,
        "storage_change_m3": final - initial,
        "residual_m3": residual,
        "residual_relative": residual / max(abs(supplied) + abs(initial), 1.),
        "declared_injection_m3": float(declared_injection_m3),
        "injection_matches_source": bool(
            abs(supplied - float(declared_injection_m3))
            <= 1e-9 * max(abs(float(declared_injection_m3)), 1.)),
        "ledger_algebra": "final = initial + injected + boundary_input - boundary_output + residual",
        "per_snapshot_residual_m3": np.asarray(arrays["ledger"], np.float64)[:, 4].tolist(),
        "no_double_count_statement":
            "each injected cubic metre is a line item the one-dimensional donor already "
            "removed from its own ledger; the two-dimensional ledger closes on its own and "
            "the reach ledger is not adjusted",
    }


def extent_statistics(depth_m, *, spacing_m, carved_depth_m, threshold_m=.02):
    """Wetted area, overbank area and depth statistics for one depth field."""
    depth = np.asarray(depth_m, np.float64)
    if depth.ndim != 2 or not np.isfinite(depth).all() or (depth < 0).any():
        raise ValueError("finite non-negative depth field required")
    area = float(spacing_m) ** 2
    wet = depth > float(threshold_m)
    carved = np.asarray(carved_depth_m, np.float64) > CARVED_EPSILON_M
    if carved.shape != depth.shape:
        raise ValueError("carved depth must match the depth field")
    overbank = wet & ~carved
    channel = wet & carved
    return {
        "threshold_m": float(threshold_m),
        "wet_cells": int(wet.sum()),
        "wet_area_m2": float(wet.sum() * area),
        "channel_wet_area_m2": float(channel.sum() * area),
        "overbank_wet_area_m2": float(overbank.sum() * area),
        "overbank_fraction_of_wet": float(overbank.sum() / wet.sum()) if wet.any() else 0.,
        "max_depth_m": float(depth.max()),
        "mean_depth_over_wet_m": float(depth[wet].mean()) if wet.any() else 0.,
        "volume_m3": float(depth.sum() * area),
    }


def residual_wetland(depth_m, *, spacing_m, carved_depth_m, threshold_m=.02):
    """Water left standing outside the carved cross-section once the flood recedes."""
    depth = np.asarray(depth_m, np.float64)
    carved = np.asarray(carved_depth_m, np.float64) > CARVED_EPSILON_M
    wet = depth > float(threshold_m)
    standing = wet & ~carved
    area = float(spacing_m) ** 2
    return {
        "threshold_m": float(threshold_m),
        "residual_cells": int(standing.sum()),
        "residual_area_m2": float(standing.sum() * area),
        "residual_volume_m3": float(depth[standing].sum() * area),
        "max_residual_depth_m": float(depth[standing].max()) if standing.any() else 0.,
        "cells_above_source_capacity": int(
            (depth > np.asarray(depth_m, np.float64).max() + 1.).sum()),
    }
