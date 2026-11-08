"""Read-only centreline audit of saved irregular reaches on native raster cells.

Raster values are nearest native sample, constant within each cell. They are not
continuous cross sections. Node IDs select coordinates, not bed sample locations.
"""
import math
import numpy as np


def audit(graph, raw_bed, final_bed, *, lake=None, ocean=None, protected=None,
          unknown=None, water_surface=None, water_source=None, indices=None):
    raw = np.asarray(raw_bed, dtype=float)
    final = np.asarray(final_bed, dtype=float)
    if raw.ndim != 2 or not raw.size or final.shape != raw.shape or not np.isfinite(raw).all() or not np.isfinite(final).all():
        raise ValueError("finite matching nonempty 2D bed rasters required")
    shape = raw.shape
    if tuple(np.asarray(graph["native_shape"]).tolist()) != shape:
        raise ValueError("native shape mismatch")
    origin = np.asarray(graph["origin_native_xz"])
    spacing = np.asarray(graph["spacing_m"])
    if origin.shape != (2,) or origin.dtype.kind not in "iu" or spacing.shape != () or not np.isfinite(spacing) or float(spacing) <= 0:
        raise ValueError("invalid origin or spacing")
    spacing = float(spacing)
    masks = {}
    for name, value in (("lake", lake), ("ocean", ocean), ("protected", protected), ("unknown", unknown)):
        if value is None:
            masks[name] = None
        else:
            a = np.asarray(value)
            if a.shape != shape or a.dtype.kind != "b":
                raise ValueError(name + " must be a matching boolean raster")
            masks[name] = a
    water = None if water_surface is None else np.asarray(water_surface, dtype=float)
    if water is not None and (water.shape != shape or np.isinf(water).any() or not water_source):
        raise ValueError("water surface requires matching raster, no infinities, and source")
    x, z = np.asarray(graph["node_x_m"], float), np.asarray(graph["node_z_m"], float)
    sources, targets = np.asarray(graph["reach_source"]), np.asarray(graph["reach_target"])
    if x.ndim != 1 or x.shape != z.shape or x.size != raw.size or not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("invalid node coordinates")
    if sources.ndim != 1 or sources.shape != targets.shape or sources.dtype.kind not in "iu" or targets.dtype.kind not in "iu" or np.any(sources < 0) or np.any(targets < 0) or np.any(sources >= x.size) or np.any(targets >= x.size):
        raise ValueError("invalid reach nodes")
    flags = {}
    for name in ("reach_projection_blocked", "reach_max_cut_limited"):
        a = np.asarray(graph[name])
        if a.shape != sources.shape or a.dtype.kind != "b":
            raise ValueError("invalid " + name)
        flags[name] = a
    width = np.asarray(graph["node_width_m"], float)
    if width.shape != x.shape or not np.isfinite(width).all() or np.any(width < 0):
        raise ValueError("invalid widths")
    if indices is None:
        indices = np.arange(len(sources))
    indices = np.asarray(indices)
    if indices.ndim != 1 or indices.dtype.kind not in "iu" or np.any(indices < 0) or np.any(indices >= len(sources)):
        raise ValueError("invalid reach indices")
    result = []
    for edge in indices:
        a, b = int(sources[edge]), int(targets[edge])
        ax, az, bx, bz = x[a], z[a], x[b], z[b]
        dx, dz = bx-ax, bz-az
        length = math.hypot(dx, dz)
        if length <= 0:
            raise ValueError("zero length reach")
        # Partition exactly at every cell boundary, then sample inside each interval.
        # This catches arbitrarily short crossings that fixed-step sampling misses.
        gx, gz = ax / spacing - origin[0] + .5, az / spacing - origin[1] + .5
        hx, hz = bx / spacing - origin[0] + .5, bz / spacing - origin[1] + .5
        ts = [0., 1.]
        for start, end in ((gx, hx), (gz, hz)):
            if start != end:
                for k in range(math.floor(min(start, end)) + 1, math.ceil(max(start, end))):
                    t = (k-start)/(end-start)
                    if 0 < t < 1:
                        ts.append(t)
        ts = sorted(set(ts))
        # Interval midpoints plus endpoints, preserving direction and actual positions.
        sample_t = [0.] + [(u+v)/2 for u, v in zip(ts, ts[1:])] + [1.]
        records = []
        for t in sample_t:
            px, pz = ax + t*dx, az + t*dz
            col, row = math.floor(px/spacing-origin[0]+.5), math.floor(pz/spacing-origin[1]+.5)
            if not (0 <= row < shape[0] and 0 <= col < shape[1]):
                raise ValueError("reach outside raster")
            item = {"t": t, "x_m": px, "z_m": pz, "row": row, "col": col,
                    "raw_bed_m": float(raw[row, col]), "final_bed_m": float(final[row, col])}
            for name, mask in masks.items():
                item[name] = None if mask is None else bool(mask[row, col])
            item["water_surface_m"] = None if water is None or not np.isfinite(water[row, col]) else float(water[row, col])
            records.append(item)
        vals = [r["final_bed_m"] for r in records]
        peak = vals[0]
        rise = 0.
        for v in vals:
            rise = max(rise, v-peak)
            peak = min(peak, v)
        available = all(r["water_surface_m"] is not None for r in records)
        wet = "unknown" if not available else ("wet_at_samples" if all(r["water_surface_m"] > r["final_bed_m"] for r in records) else "dry_at_samples")
        crossings = {name: None if mask is None else any(r[name] for r in records) for name, mask in masks.items()}
        result.append({"reach_index": int(edge), "source_node": a, "target_node": b,
            "source_xz_m": [ax, az], "target_xz_m": [bx, bz], "length_m": length,
            "projection_blocked": bool(flags["reach_projection_blocked"][edge]),
            "max_cut_limited": bool(flags["reach_max_cut_limited"][edge]),
            "raw_bed_range_m": [min(r["raw_bed_m"] for r in records), max(r["raw_bed_m"] for r in records)],
            "final_bed_range_m": [min(vals), max(vals)], "maximum_downstream_rise_m": rise,
            "crossings": crossings, "width_m": [float(width[a]), float(width[b])],
            "resolution": "subgrid_width" if min(width[a], width[b]) < spacing else "width_at_least_one_cell_not_cross_section_certified",
            "water_surface_source": water_source if water is not None else None,
            "wet_connectivity": wet, "samples": records})
    return result
