"""Independent certification of saved render segments, never a generated bed."""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_native_channel_valley_paths import audit as audit_saved_samples

MAX_CHECKS = 262144
MAX_SEGMENTS = 262144


def _points(values, label):
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 2 or not 2 <= len(values) <= MAX_SEGMENTS + 1 or not np.isfinite(values).all():
        raise ValueError(label + " invalid points/budget")
    return values


def _distance(point, original):
    starts = original[:-1]
    delta = original[1:] - starts
    squared = np.sum(delta * delta, axis=1)
    if np.any(squared <= 0):
        raise ValueError("original polyline contains zero-length edges")
    fraction = np.clip(np.sum((point - starts) * delta, axis=1) / squared, 0., 1.)
    return float(np.min(np.linalg.norm(point - starts - fraction[:, None] * delta, axis=1)))


def certify_corridor(points, original, limit_m, *, max_checks=MAX_CHECKS):
    points = _points(points, "rendered polyline")
    original = _points(original, "original polyline")
    if type(limit_m) not in (float, int) or not math.isfinite(limit_m) or limit_m <= 0:
        raise ValueError("corridor limit invalid")
    if type(max_checks) is not int or not 1 <= max_checks <= MAX_CHECKS:
        raise ValueError("corridor check budget invalid")
    checks = 0
    maximum_observed = 0.

    def distance(point):
        nonlocal checks, maximum_observed
        checks += 1
        if checks > max_checks:
            raise ValueError("continuous corridor proof budget exhausted")
        value = _distance(point, original)
        maximum_observed = max(maximum_observed, value)
        if value > limit_m:
            raise ValueError("continuous rendered segment leaves original corridor")
        return value

    distances = [distance(point) for point in points]
    stack = [(start, end, distances[index], distances[index + 1], 0)
             for index, (start, end) in enumerate(zip(points[:-1], points[1:]))]
    certificates = 0
    maximum_certified_bound = 0.
    while stack:
        start, end, start_distance, end_distance, depth = stack.pop()
        length = float(np.linalg.norm(end - start))
        upper = (start_distance + end_distance + length) / 2
        upper = np.nextafter(upper, math.inf)
        if upper <= limit_m:
            certificates += 1
            maximum_certified_bound = max(maximum_certified_bound, upper)
            continue
        if depth >= 24:
            raise ValueError("continuous corridor proof subdivision exhausted")
        midpoint = (start + end) / 2
        if np.array_equal(midpoint, start) or np.array_equal(midpoint, end):
            raise ValueError("continuous corridor proof precision exhausted")
        midpoint_distance = distance(midpoint)
        stack.extend(((start, midpoint, start_distance, midpoint_distance, depth + 1),
                      (midpoint, end, midpoint_distance, end_distance, depth + 1)))
    return dict(distance_checks=checks, certified_subsegments=certificates,
                maximum_observed_distance_m=maximum_observed,
                maximum_certified_distance_upper_m=maximum_certified_bound)


def certify_stencils(points, topology, origin_m_xz, spacing_m, *, max_checks=MAX_CHECKS):
    points = _points(points, "rendered polyline")
    origin = np.asarray(origin_m_xz, dtype=np.float64)
    if origin.shape != (2,) or not np.isfinite(origin).all() or not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("continuous stencil grid invalid")
    valid = topology["valid_mask"]
    protected = topology["protected_mask"]
    boundary = topology["open_boundary_mask"]
    owners = topology["contribution_owner"]
    parents = topology["node_parent"]
    if (valid.ndim != 2 or min(valid.shape) < 2 or valid.dtype != bool or
            protected.shape != valid.shape or protected.dtype != bool or
            boundary.shape != valid.shape or boundary.dtype != bool or
            owners.shape != valid.shape or owners.dtype != np.int64 or
            parents.ndim != 1 or parents.dtype != np.int64 or
            np.any((parents < -1) | (parents >= len(parents)))):
        raise ValueError("continuous stencil topology invalid")
    if type(max_checks) is not int or not 1 <= max_checks <= MAX_CHECKS:
        raise ValueError("stencil check budget invalid")
    rows, columns = valid.shape
    grid = (points - origin) / spacing_m
    if np.any(grid < 0) or np.any(grid > [columns - 1, rows - 1]):
        raise ValueError("continuous segment outside native grid")
    children = np.bincount(parents[parents >= 0], minlength=len(parents))
    owner = None
    checks = 0
    intervals = 0

    def check(point):
        nonlocal owner, checks
        checks += 1
        if checks > max_checks:
            raise ValueError("continuous stencil proof budget exhausted")
        column, row = np.floor(point).astype(np.int64)
        next_column, next_row = min(column + 1, columns - 1), min(row + 1, rows - 1)
        stencil = (np.array([row, row, next_row, next_row]),
                   np.array([column, next_column, column, next_column]))
        local_owners = owners[stencil]
        if (not valid[stencil].all() or protected[stencil].any() or boundary[stencil].any() or
                np.any(local_owners < 0) or np.any(local_owners >= len(parents)) or
                np.any(local_owners != local_owners[0])):
            raise ValueError("continuous stencil crosses unknown/protected/boundary/owner")
        current_owner = int(local_owners[0])
        if children[current_owner] != 0:
            raise ValueError("continuous stencil owner is not a leaf")
        if owner is None:
            owner = current_owner
        if current_owner != owner:
            raise ValueError("continuous rendered chain crosses basin leaves")

    for start, end in zip(grid[:-1], grid[1:]):
        fractions = [0., 1.]
        for axis in (0, 1):
            delta = end[axis] - start[axis]
            if delta == 0:
                continue
            first = math.floor(min(start[axis], end[axis])) + 1
            last = math.ceil(max(start[axis], end[axis]))
            if last - first > max_checks:
                raise ValueError("continuous grid crossing budget exceeded")
            fractions.extend((line - start[axis]) / delta for line in range(first, last)
                             if 0 < (line - start[axis]) / delta < 1)
        fractions = sorted(set(fractions))
        for fraction in fractions:
            check(start + fraction * (end - start))
        for first, last in zip(fractions[:-1], fractions[1:]):
            check(start + (first + last) / 2 * (end - start))
            intervals += 1
    return dict(stencil_checks=checks, constant_stencil_intervals=intervals, leaf_owner=owner)


def audit(report_path, expected_sha256):
    base = audit_saved_samples(report_path, expected_sha256)
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    paths, metadata = read_record(report["paths"])
    topology, hierarchy_metadata = read_record(report["hierarchy"])
    columns = topology["height_m"].shape[1]
    spacing = hierarchy_metadata["spacing_m"]
    origin = np.asarray(hierarchy_metadata["origin_m_xz"])
    if metadata["recipe"]["max_corridor_fraction"] != .25:
        raise ValueError("independent corridor recipe mismatch")
    certified = []
    for chain in np.flatnonzero(paths["chain_accepted"]):
        point_begin, point_end = paths["point_offsets"][chain:chain + 2]
        edge_begin, edge_end = paths["chain_edge_offsets"][chain:chain + 2]
        edges = paths["chain_edge_cell_ids"][edge_begin:edge_end]
        cells = np.concatenate((edges[:1, 0], edges[:, 1]))
        original = np.column_stack((origin[0] + cells % columns * spacing,
                                    origin[1] + cells // columns * spacing))
        points = paths["points_xyz_m"][point_begin:point_end][:, [0, 2]]
        corridor = certify_corridor(points, original, spacing / 4)
        stencils = certify_stencils(points, topology, origin, spacing)
        certified.append(dict(chain=int(chain), **corridor, **stencils))
    if file_sha256(report_path) != expected_sha256:
        raise ValueError("continuous path report changed during audit")
    return dict(schema="td-independent-visual-path-continuity-v1", accepted=True,
                saved_sample_audit=base, certified_chains=certified,
                certified_segments=sum(int(paths["point_offsets"][chain + 1] - paths["point_offsets"][chain] - 1)
                                       for chain in np.flatnonzero(paths["chain_accepted"])),
                proof="constant stencil on each grid-split open interval; grid crossings checked separately; 1-Lipschitz distance endpoint cones with adaptive subdivision",
                fallback_chains_certified=False, hydraulic_ready=False,
                natural_outlet_verified=False, publishable=False,
                scope="continuous saved rendered polylines only; not mathematical quadratic curves, new bed or hydraulic certification")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    args = parser.parse_args()
    result = audit(args.report, args.report_sha256)
    destination = ROOT / "verification/td-native-channel-valley-paths" / ("independent-continuity-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(destination, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(destination), expected_sha256=file_sha256(destination), **result)))


if __name__ == "__main__":
    main()
