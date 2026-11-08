# -*- coding: utf-8 -*-
"""Native 30 m backbone shape fidelity over a **published** backbone product.

What this reads
---------------
A published ``metric-river-backbone-v1`` product only: ``product["arrays"]["reach_cells"]`` with
``reach_ptr`` gives the authoritative **ordered native trace** of every reach, and
``product["reaches"]`` gives the world anchors. Nothing here reads a TD page, re-derives a receiver,
re-simplifies the routing graph or writes into the product. The product is evidence, not input to be
edited.

Two objects, never merged
-------------------------
``source_line``   the ordered native 30 m trace (world native cells). Authoritative. Excavation,
                  routing and any physics must use this and the original DEM.
``display_line``  an optional simplified polyline for drawing/index only, with a declared tolerance
                  and **two-way conservative bounds**. A simplified line is never a routing basis.

The native receiver's watershed membership is a separate fact from "is this polyline close": a
shortcut that stays within tolerance can still join two different valleys. This module reports the
two independently and refuses to call one a proof of the other.

See ``.scratch/river-backbone-precompute-v1/shape-scale-v1/DELIVERY-02.md`` for the experiment this
reproduces in production form: same tolerance idea, same two-way bound semantics, same anchor and
contact verification. The scratch drivers are **not** imported.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np

SCHEMA = "backbone-shape-fidelity-v1"
LOGICAL_VERSION = "native-trace-display-lod-v1"

#: Declared display tolerances in metres. 30 m is the shipped default (one native cell); 60 and 120
#: are negative controls only — a coarser budget is never silently adopted.
DEFAULT_TOLERANCE_M = 30.0
DECLARED_TOLERANCES_M = (0.0, 30.0, 60.0, 120.0)

#: Sampling step used for the *reverse* (simplified -> source) distance. It is a declared
#: approximation with a stated error bound, never presented as a continuous Hausdorff distance.
REVERSE_SAMPLE_M = 3.0
REVERSE_MARGIN_M = 0.5 * REVERSE_SAMPLE_M


def _array(value, name, dtype, ndim=None, allow_nan=False):
    array = np.asarray(value, dtype)
    if ndim is not None and array.ndim != ndim:
        raise ValueError("%s must be %d-dimensional" % (name, ndim))
    if array.dtype.kind == "f":
        if allow_nan:
            if np.isinf(array).any():
                raise ValueError("%s must not carry infinities" % name)
        elif not np.isfinite(array).all():
            raise ValueError("%s must be finite" % name)
    return array


def world_trace(*, reach_cells, reach_ptr, origin_native_xz, reach_index, columns):
    """The ordered world-native trace of one reach, straight from the stored arrays."""
    cells = _array(reach_cells, "reach_cells", np.int64, 1)
    pointer = _array(reach_ptr, "reach_ptr", np.int64, 1)
    index = int(reach_index)
    if not 0 <= index < pointer.size - 1:
        raise ValueError("reach_index %d is outside the stored reach table" % index)
    start, stop = int(pointer[index]), int(pointer[index + 1])
    if stop <= start:
        raise ValueError("reach %d carries no cell" % index)
    chain = cells[start:stop]
    return trace_world(chain, origin_native_xz, columns)


def trace_world(chain_flat, origin_native_xz, columns):
    chain = _array(chain_flat, "chain_flat", np.int64, 1)
    origin = _array(origin_native_xz, "origin_native_xz", np.int64, 1)
    if origin.size != 2:
        raise ValueError("origin_native_xz must be a signed (x, z) pair")
    x = origin[0] + chain % int(columns)
    z = origin[1] + chain // int(columns)
    return np.stack([x, z], axis=1).astype(np.int64)


def receiver_consistency(world_native, receiver, columns, origin_native_xz):
    """Every consecutive pair of the ordered trace must be a real receiver edge.

    ``world_native`` is **absolute** world native ``(x, z)``; ``receiver`` is a local flat ``[z, x]``
    raster of the product. The origin is subtracted before flattening — without that, an absolute
    coordinate around 42 000 indexes far outside the raster and every check would be wrong (or
    silently index nowhere). The two coordinate systems are therefore never mixed.
    """
    trace = _array(world_native, "world_native", np.int64, 2)
    rec = _array(receiver, "receiver", np.int64).reshape(-1)
    origin = _array(origin_native_xz, "origin_native_xz", np.int64, 1)
    if trace.shape[1] != 2:
        raise ValueError("world_native must be [n, 2]")
    if origin.size != 2:
        raise ValueError("origin_native_xz must be a signed (x, z) pair")
    columns = int(columns)
    local_x = trace[:, 0] - int(origin[0])
    local_z = trace[:, 1] - int(origin[1])
    rows = rec.size // columns if columns else 0
    if np.any(local_x < 0) or np.any(local_x >= columns) \
            or np.any(local_z < 0) or np.any(local_z >= rows):
        raise ValueError("the world trace leaves the declared grid; origin/shape mismatch")
    flat = (local_z * columns + local_x).astype(np.int64)
    if flat.size < 2:
        return {"consistent": True, "cell_count": int(flat.size), "broken_pairs": 0,
                "first_broken_index": None,
                "coordinate_system": "world_native_minus_origin_to_local_flat"}
    # a tail may drain to a structural terminal (receiver -1) or off the channel; only an
    # *interior* break is a disagreement between the saved trace and the saved receiver
    broken = np.flatnonzero(rec[flat[:-1]] != flat[1:])
    # the tail cell's **own** receiver decides whether the reach ends on a structural terminal
    terminal_tail = bool(rec[flat[-1]] < 0)
    if broken.size:
        return {"consistent": False, "cell_count": int(flat.size),
                "broken_pairs": int(broken.size),
                "first_broken_index": int(broken[0]),
                "coordinate_system": "world_native_minus_origin_to_local_flat"}
    return {"consistent": True, "cell_count": int(flat.size), "broken_pairs": 0,
            "first_broken_index": None,
            "tail_is_terminal": bool(terminal_tail),
            "coordinate_system": "world_native_minus_origin_to_local_flat"}


def segment_distances(points, first, second):
    """Distance from every point to the segment ``first``-``second`` (all in the same unit)."""
    pts = _array(points, "points", np.float64, 2)
    a = np.asarray(first, np.float64)
    b = np.asarray(second, np.float64)
    ab = b - a
    denominator = float(ab @ ab)
    if denominator <= 0.0:
        return np.linalg.norm(pts - a, axis=1)
    t = np.clip(((pts - a) @ ab) / denominator, 0.0, 1.0)
    projection = a[None, :] + t[:, None] * ab[None, :]
    return np.linalg.norm(pts - projection, axis=1)


def douglas_peucker(world_native, tolerance_m, *, spacing_m=30.0):
    """Fixed-rule simplification of an ordered trace, seeded with both ends.

    The two ends are **anchors** and are never dropped. With ``tolerance_m == 0`` the trace is
    returned unchanged, which is the shipped lossless fallback.
    """
    trace = _array(world_native, "world_native", np.int64, 2).astype(np.float64) * float(spacing_m)
    tolerance = float(tolerance_m)
    if tolerance < 0.0 or not math.isfinite(tolerance):
        raise ValueError("tolerance_m must be a finite non-negative number")
    count = trace.shape[0]
    if count <= 2 or tolerance == 0.0:
        kept = np.arange(count, dtype=np.int64)
    else:
        keep = np.zeros(count, np.bool_)
        keep[0] = keep[-1] = True
        stack = [(0, count - 1)]
        while stack:
            first, last = stack.pop()
            if last <= first + 1:
                continue
            distances = segment_distances(trace[first + 1:last], trace[first], trace[last])
            if distances.size == 0:
                continue
            peak = int(np.argmax(distances))
            if float(distances[peak]) > tolerance:
                index = first + 1 + peak
                keep[index] = True
                stack.append((first, index))
                stack.append((index, last))
        kept = np.flatnonzero(keep).astype(np.int64)
    return ((trace[kept] / float(spacing_m)).round().astype(np.int64), kept)


def two_way_bounds(world_native, display_native, *, spacing_m=30.0):
    """Conservative bounds in metres, in both directions, with the sampling stated.

    Both directions take the distance to the **nearest** segment of the other polyline and then the
    maximum over the relevant points. Taking a maximum over “distance to each segment” would report
    the farthest segment instead of the closest one, which even makes an identical pair of lines
    look far apart.

    forward   every source **vertex** to its nearest display segment, max. Exact over source
              vertices; conservative for the continuous polyline.
    reverse   sampled every ``REVERSE_SAMPLE_M`` along the display polyline, each sample to its
              nearest **source** segment, max; plus the declared half-step margin, so the reported
              value is an upper bound with a stated sampling error. The raw sample maximum is a
              lower bound and is reported separately, never used as certification.
    """
    source = _array(world_native, "world_native", np.int64, 2).astype(np.float64) * float(spacing_m)
    display = _array(display_native, "display_native", np.int64, 2).astype(np.float64) * float(spacing_m)
    if source.shape[0] < 1 or display.shape[0] < 1:
        raise ValueError("both lines need at least one point")

    # Both directions are **continuous** samples along the whole polyline, not just vertices: a
    # vertex-only test misses the maximum that occurs inside a corner segment. Each sample is
    # measured to the nearest segment of the other line, then the declared half-step margin is
    # added, so the reported value is an upper bound with a stated sampling error.
    forward_raw = float(np.max(_min_distance_to_polyline(_densify(source), display)))
    reverse_raw = float(np.max(_min_distance_to_polyline(_densify(display), source)))
    margin = 0.5 * REVERSE_SAMPLE_M
    return {
        "forward_max_m": float(forward_raw + margin),
        "reverse_sample_max_m": reverse_raw,
        "reverse_conservative_bound_m": float(reverse_raw + margin),
        "forward_sample_max_m": forward_raw,
        "reverse_sample_step_m": REVERSE_SAMPLE_M,
        "reverse_margin_m": margin,
        "max_bound_m": float(max(forward_raw + margin, reverse_raw + margin)),
        "semantics": ("both directions are sampled along the full polyline at the declared step, "
                      "each sample measured to its nearest segment of the other line, and "
                      "reported as an upper bound with a half-step margin; the raw sample maxima "
                      "are lower bounds and are never used as certification"),
    }


def _densify(polyline, *, step_m=None):
    """Sample a polyline continuously, so a maximum inside a segment cannot be missed."""
    step = REVERSE_SAMPLE_M if step_m is None else float(step_m)
    line = np.asarray(polyline, np.float64).reshape(-1, 2)
    if line.shape[0] == 1:
        return line.copy()
    samples = [line[0]]
    for first, second in zip(line[:-1], line[1:]):
        length = float(np.linalg.norm(second - first))
        count = max(1, int(math.ceil(length / step)))
        for index in range(1, count + 1):
            samples.append(first + (second - first) * (index / count))
    return np.asarray(samples, np.float64).reshape(-1, 2)


def _min_distance_to_polyline(points, polyline):
    """Distance from each point to its **nearest** segment of ``polyline``."""
    pts = np.asarray(points, np.float64).reshape(-1, 2)
    line = np.asarray(polyline, np.float64).reshape(-1, 2)
    if line.shape[0] == 1:
        return np.linalg.norm(pts - line[0], axis=1)
    best = np.full(pts.shape[0], np.inf, np.float64)
    for first, second in zip(line[:-1], line[1:]):
        best = np.minimum(best, segment_distances(pts, first, second))
    return best


def anchors_preserved(*, source_native, display_native, expected_tail_native=None):
    """Head, tail and (optionally) the stored tail anchor must be identical world cells.

    ``expected_tail_native`` is the **world (x, z)** of the tail the product stored, so the anchor is
    compared in one coordinate system. Passing a flat local index here would be a different quantity
    and is refused rather than silently mismatched.
    """
    source = _array(source_native, "source_native", np.int64, 2)
    display = _array(display_native, "display_native", np.int64, 2)
    head_ok = bool(np.array_equal(source[0], display[0]))
    tail_ok = bool(np.array_equal(source[-1], display[-1]))
    anchor_ok = True
    if expected_tail_native is not None:
        expected = _array(expected_tail_native, "expected_tail_native", np.int64, 1)
        if expected.size != 2:
            raise ValueError("expected_tail_native must be a world (x, z) pair")
        anchor_ok = bool(np.array_equal(expected, display[-1]))
    return {"head_preserved": head_ok, "tail_preserved": tail_ok,
            "stored_tail_anchor_preserved": anchor_ok,
            "all_preserved": head_ok and tail_ok and anchor_ok}


def directed_continuity(*, source_native, display_native, receiver, columns):
    """The display line must keep the same direction and the same ordered subsequence.

    ``columns`` is accepted for call-site symmetry with the other readers but is **not** used to
    flatten anything: a world cell is keyed as its ``(x, z)`` pair. Flattening absolute natives
    with ``z * columns + x`` collides distinct cells once ``x`` can exceed the column count, which
    is always true here (x is around 42 000).
    """
    source = _array(source_native, "source_native", np.int64, 2)
    display = _array(display_native, "display_native", np.int64, 2)
    del columns                    # accepted for call-site symmetry; a world cell is a pair
    positions = {(int(x), int(z)): index for index, (x, z) in enumerate(source.tolist())}
    order = []
    for cell in [(int(x), int(z)) for x, z in display.tolist()]:
        if cell not in positions:
            return {"ordered_subsequence": False, "reason": "display_cell_not_on_source",
                    "offending_cell": list(cell), "monotone": False}
        order.append(positions[cell])
    monotone = all(first < second for first, second in zip(order[:-1], order[1:]))
    return {"ordered_subsequence": True, "monotone": bool(monotone),
            "reason": None if monotone else "order_reversed_or_repeated",
            "offending_cell": None}


TERRAIN_SCREEN_CLEAR = "terrain_shortcut_screen_clear"
TERRAIN_SCREEN_REFUSED = "terrain_shortcut_screen_refused"
TERRAIN_SCREEN_PENDING = "terrain_shortcut_screen_pending_unknown"
TERRAIN_SCREEN_LABEL = "terrain_shortcut_screen_not_watershed_certificate"

#: What the contact gate actually did. It scans the **cell occupancy** of the cells a display chord
#: passes over on the integer lattice and compares them with the source line's own cells. It does
#: **not** intersect display chords of different reaches with each other: two simplified chords can
#: cross inside a cell while neither passes over the other's source cells, and that case is
#: invisible to a cell scan. Declaring the stronger statement as unsupported is the honest option —
#: the alternative would be a `preserved` flag that silently certifies more than it checked.
CROSSING_RELATION = "cross_reach_cell_occupancy_only"
CROSSING_UNSUPPORTED = "continuous_display_display_segment_intersection_not_performed"


def valley_axis_crossing(*, source_native, display_native, elevation_m, origin_native_xz,
                         columns, spacing_m=30.0):
    """A **conservative screen** for "does this chord cut ground the source path did not".

    This is a screen, not a watershed certificate. It samples the bed along every display chord and
    compares it with the **maximum bed along the source sub-path that chord replaces** — not with the
    two endpoints, because two endpoints prove nothing about the ridge between them. It also refuses
    to call an unknown cell clear:

    ``clear``     every sample was resolved and none rose above the source sub-path ceiling
    ``refused``   a resolved sample rose above that ceiling
    ``pending``   at least one sample or ceiling value was unresolved (NaN / off-grid); the result
                  is **not** a pass and the chord must not be accepted on it

    Adjacent source cells with no intermediate sample are an independent fact: the source line
    itself was already checked against the receiver, so nothing here needs to be sampled and that
    chord simply does not enter the screen.
    """
    source = _array(source_native, "source_native", np.int64, 2)
    display = _array(display_native, "display_native", np.int64, 2)
    field = None if elevation_m is None else _array(
        elevation_m, "elevation_m", np.float64, 2, allow_nan=True)
    origin = _array(origin_native_xz, "origin_native_xz", np.int64, 1)
    columns = int(columns)
    spacing = float(spacing_m)
    if field is None:
        return {"label": TERRAIN_SCREEN_LABEL, "status": TERRAIN_SCREEN_PENDING,
                "samples_checked": 0, "samples_unknown": 0, "ridge_crossings": 0,
                "crossing_sample": [],
                "note": "no elevation supplied: the screen is pending, never a pass"}
    if origin.size != 2:
        raise ValueError("origin_native_xz must be a signed (x, z) pair")

    def sample(world_x, world_z):
        row = int(world_z) - int(origin[1])
        column = int(world_x) - int(origin[0])
        if not (0 <= row < field.shape[0] and 0 <= column < field.shape[1]):
            return None
        value = float(field[row, column])
        return value if math.isfinite(value) else None

    # map every source cell to its position so each chord knows which source sub-path it replaces
    positions = {(int(x), int(z)): index for index, (x, z) in enumerate(source.tolist())}
    checked = 0
    unknown = 0
    crossings = []
    for first, second in zip(display[:-1], display[1:]):
        start = positions.get((int(first[0]), int(first[1])))
        stop = positions.get((int(second[0]), int(second[1])))
        if start is None or stop is None or stop <= start:
            unknown += 1
            continue
        if stop == start + 1:
            # adjacent native cells: no interior sample exists, and the source path is already
            # verified against the receiver, so this chord does not enter the screen
            continue
        ceiling_values = [sample(x, z) for x, z in source[start:stop + 1].tolist()]
        if any(value is None for value in ceiling_values):
            unknown += 1
            continue
        ceiling = max(ceiling_values)
        steps = max(abs(int(second[0]) - int(first[0])), abs(int(second[1]) - int(first[1])))
        chord_unknown = False
        hit = None
        for step in range(1, steps):
            fraction = step / steps
            world_x = first[0] + (second[0] - first[0]) * fraction
            world_z = first[1] + (second[1] - first[1]) * fraction
            # nearest native cell, sampled on the integer lattice the raster lives on
            value = sample(round(world_x), round(world_z))
            checked += 1
            if value is None:
                chord_unknown = True
                continue
            if value > ceiling + 1e-9:
                hit = {"between": [[int(first[0]), int(first[1])],
                                   [int(second[0]), int(second[1])]],
                       "sample": [int(round(world_x)), int(round(world_z))],
                       "bed_m": value, "source_subpath_ceiling_m": ceiling}
                break
        if chord_unknown:
            unknown += 1
        if hit is not None:
            crossings.append(hit)
    if crossings:
        status = TERRAIN_SCREEN_REFUSED
    elif unknown:
        status = TERRAIN_SCREEN_PENDING
    else:
        status = TERRAIN_SCREEN_CLEAR
    return {"label": TERRAIN_SCREEN_LABEL, "status": status,
            "samples_checked": int(checked), "samples_unknown": int(unknown),
            "ridge_crossings": len(crossings), "crossing_sample": crossings[:8],
            "note": ("a chord above the maximum bed of the source sub-path it replaces cut ground "
                     "the 30 m path did not; an unresolved sample leaves the screen pending, and "
                     "neither outcome is a watershed or basin-membership certificate")}


def world_path_sha256(world_native):
    block = np.ascontiguousarray(_array(world_native, "world_native", np.int64, 2).reshape(-1, 2),
                                 dtype="<i8")
    return hashlib.sha256(block.tobytes()).hexdigest()


def _flatten(world_native, origin_native_xz, columns):
    """Local flat index of a world trace (subtract the origin first, never index with natives)."""
    world = _array(world_native, "world_native", np.int64, 2)
    origin = _array(origin_native_xz, "origin_native_xz", np.int64, 1)
    return ((world[:, 1] - int(origin[1])) * int(columns)
            + (world[:, 0] - int(origin[0]))).astype(np.int64)


def _foreign_contacts(display_native, chain, reach_index, reach_of_cell, origin_native_xz,
                      columns):
    """Cells a display **chord passes over** that the source never entered and the product
    assigns to another reach.

    Checking only the display *vertices* would be vacuous: Douglas-Peucker keeps a subset of the
    source vertices, so every vertex is by construction a source cell. What a simplification can
    invent is a chord that *cuts across* a neighbouring reach, and that is only visible in the
    cells between two kept vertices.
    """
    if reach_of_cell is None:
        return []
    display = _array(display_native, "display_native", np.int64, 2)
    own = set(int(cell) for cell in np.asarray(chain, np.int64).tolist())
    found = []
    seen = set()
    for first, second in zip(display[:-1], display[1:]):
        steps = max(abs(int(second[0]) - int(first[0])), abs(int(second[1]) - int(first[1])))
        for step in range(1, steps):
            fraction = step / steps
            world_x = int(round(first[0] + (second[0] - first[0]) * fraction))
            world_z = int(round(first[1] + (second[1] - first[1]) * fraction))
            flat = ((world_z - int(origin_native_xz[1])) * int(columns)
                    + (world_x - int(origin_native_xz[0])))
            if flat in seen or flat in own:
                continue
            seen.add(flat)
            owner = int(reach_of_cell[flat]) if 0 <= flat < reach_of_cell.size else -1
            if owner >= 0 and owner != int(reach_index):
                found.append({"reach_index": int(reach_index), "display_cell_local_flat": flat,
                              "owner_reach_index": owner})
    return found


def contact_preserved(source_contacts, display_contacts, foreign_contacts=()):
    """Inter-reach contact is preserved, and no simplification invents a new one.

    A **contact** here is the handoff edge from one reach's tail to the cell its stored receiver
    drains into: the only place two reaches actually meet. A chord *inside* one reach is
    simplification, not contact -- counting those would fail every simplified line by
    construction, which would be a gate that measures nothing.

    ``lost_contacts``      a stored handoff whose display counterpart is gone (a moved tail, a
                           display end that is no longer the stored anchor): connectivity the
                           product has and the drawing does not.
    ``invented_handoffs``  a display handoff that the source never had.
    ``new_contacts``       a display cell the source line never entered but that the published
                           product assigns to a *different* reach: the drawing touches a reach
                           it must not.

    ``preserved`` is about the *handoff and cell occupancy* only. It is not a watershed or basin
    certificate, and it is not a continuous segment-intersection certificate: see
    ``crossing_relation``.
    """
    source = set((int(a), int(b)) for a, b in source_contacts)
    display = set((int(a), int(b)) for a, b in display_contacts)
    lost = sorted(source - display)
    invented = sorted(display - source)
    foreign = [dict(item) for item in foreign_contacts]
    return {
        "label": "network_contact_gate_not_watershed_certificate",
        "source_contact_count": len(source),
        "display_contact_count": len(display),
        "lost_contacts": lost[:32],
        "lost_contact_count": len(lost),
        "invented_handoffs": invented[:32],
        "invented_handoff_count": len(invented),
        "new_contacts": foreign[:32],
        "new_contact_count": len(foreign) + len(invented),
        "preserved": bool(not lost and not invented and not foreign),
        "crossing_relation": CROSSING_RELATION,
        "preserved_scope": ("inter-reach handoff edges and cross-reach cell occupancy on the "
                            "native lattice; a continuous segment-intersection proof between "
                            "two reaches' display chords is NOT performed and is not implied"),
    }


def build_fidelity(*, product, tolerance_m=DEFAULT_TOLERANCE_M, spacing_m=30.0,
                   elevation_m=None, max_reaches=None):
    """Source/display separation for every reach of a published product.

    ``product`` is the dict returned by ``metric_backbone_product.load_backbone_product`` (read-only).
    ``display_native`` equals ``source_native`` whenever ``tolerance_m == 0`` or when no simplification
    passes the declared gates — a lossless fallback is a legitimate first-version result, and it is
    reported as such rather than papered over with a coarser line.
    """
    arrays = product["arrays"]
    metadata = product["metadata"]
    receiver = np.asarray(arrays["receiver"], np.int64)
    columns = int(receiver.shape[1])
    origin = [int(v) for v in metadata["origin_native_xz"]]
    cells = np.asarray(arrays["reach_cells"], np.int64)
    pointer = np.asarray(arrays["reach_ptr"], np.int64)
    reach_of_cell = (np.asarray(arrays["reach_of_cell"], np.int64).reshape(-1)
                     if "reach_of_cell" in arrays else None)
    rows = product.get("reaches") or []
    if len(rows) != pointer.size - 1:
        raise ValueError("the product holds %d reach rows for %d stored reaches"
                         % (len(rows), pointer.size - 1))
    tolerance = float(tolerance_m)
    if tolerance not in DECLARED_TOLERANCES_M:
        raise ValueError("tolerance_m %r is not a declared budget %s"
                         % (tolerance_m, list(DECLARED_TOLERANCES_M)))
    # Two layers, deliberately kept apart:
    #   * the **candidate** simplification budget below the declared gate, with the sampling margin
    #     already reserved, so a candidate that passes its own vertex test can still certify against
    #     the final conservative bound;
    #   * the **final** certificate at the declared tolerance, measured on the conservative bound.
    # Conflating them would either certify a 31.5 m line against a 30 m gate or silently widen the
    # gate; neither is allowed.
    candidate_tolerance = max(0.0, tolerance - REVERSE_MARGIN_M)
    limit = len(rows) if max_reaches is None else min(len(rows), int(max_reaches))

    reports = []
    kept_total = 0
    source_total = 0
    fallback = 0
    blocked_by_contact = 0
    refusal_reasons = {}
    source_contacts = set()
    display_contacts = set()
    foreign_contacts = []
    for index in range(limit):
        start, stop = int(pointer[index]), int(pointer[index + 1])
        chain = cells[start:stop]
        source = trace_world(chain, origin, columns)
        display, kept = douglas_peucker(source, candidate_tolerance, spacing_m=spacing_m)
        bounds = two_way_bounds(source, display, spacing_m=spacing_m)
        anchors = anchors_preserved(source_native=source, display_native=display)
        continuity = directed_continuity(source_native=source, display_native=display,
                                         receiver=receiver, columns=columns)
        consistent = receiver_consistency(source, receiver, columns, origin)
        crossing = (valley_axis_crossing(source_native=source, display_native=display,
                                         elevation_m=elevation_m, origin_native_xz=origin,
                                         columns=columns, spacing_m=spacing_m)
                    if elevation_m is not None else
                    {"label": TERRAIN_SCREEN_LABEL, "status": TERRAIN_SCREEN_PENDING,
                     "samples_checked": 0, "samples_unknown": 0, "ridge_crossings": 0,
                     "crossing_sample": [],
                     "note": "no elevation supplied: the screen is pending, never a pass"})
        # ``tolerance == 0`` asks for the lossless line: nothing was simplified, so there is no
        # deviation to certify and ``within`` is trivially true. It is **not** an exact-identical
        # exemption inside the bound arithmetic -- the bound still carries its half-step margin and
        # is still reported; there is simply no candidate here to be measured.
        within = tolerance <= 0.0 or bounds["max_bound_m"] <= tolerance + 1e-9
        # ``pending`` is NOT a pass: an unresolved screen blocks simplification and the reach falls
        # back to its lossless source line.
        screen_ok = crossing["status"] == TERRAIN_SCREEN_CLEAR
        # A chord that lands on a cell the product assigns to *another* reach touches a reach this
        # drawing must not touch. It is refused **before** acceptance (the reach falls back to its
        # lossless line) rather than reported after the fact: a lost or invented contact must not
        # survive into the published display line at all.
        candidate_foreign = _foreign_contacts(display, chain, index, reach_of_cell, origin,
                                             columns)
        # The **candidate** is judged on its own evidence and its refusal reasons are recorded
        # before any fallback: after falling back the terrain screen and the bounds describe the
        # lossless source line, which would erase *why* the candidate was rejected. With
        # ``tolerance == 0`` there is no candidate at all (the caller asked for the lossless line),
        # so nothing is recorded -- counting that as a "refusal" would inflate the tally.
        candidate_reasons = []
        if tolerance > 0.0:
            if not within:
                candidate_reasons.append("bound_exceeds_declared_tolerance")
            if not anchors["all_preserved"]:
                candidate_reasons.append("anchor_lost")
            if not continuity["ordered_subsequence"]:
                candidate_reasons.append("display_cell_not_on_source")
            if not continuity["monotone"]:
                candidate_reasons.append("direction_not_monotone")
            if crossing["status"] == TERRAIN_SCREEN_REFUSED:
                candidate_reasons.append("terrain_chord_refused")
            elif crossing["status"] == TERRAIN_SCREEN_PENDING:
                candidate_reasons.append("terrain_screen_pending_not_a_pass")
            if candidate_foreign:
                candidate_reasons.append("crosses_another_reach_cell")
            if display.shape[0] >= source.shape[0]:
                candidate_reasons.append("simplification_removed_nothing")
            if not consistent["consistent"]:
                candidate_reasons.append("source_trace_disagrees_with_stored_receiver")
        for reason in candidate_reasons:
            refusal_reasons[reason] = refusal_reasons.get(reason, 0) + 1
        accepted = (tolerance > 0.0
                    and within
                    and anchors["all_preserved"]
                    and continuity["ordered_subsequence"] and continuity["monotone"]
                    and screen_ok
                    and not candidate_foreign
                    and consistent["consistent"]
                    and display.shape[0] < source.shape[0])
        if not accepted:
            fallback += 1
            display = source.copy()
            kept = np.arange(source.shape[0], dtype=np.int64)
            bounds = two_way_bounds(source, display, spacing_m=spacing_m)
            anchors = anchors_preserved(source_native=source, display_native=display)
            continuity = directed_continuity(source_native=source, display_native=display,
                                             receiver=receiver, columns=columns)
            crossing = (valley_axis_crossing(source_native=source, display_native=display,
                                             elevation_m=elevation_m, origin_native_xz=origin,
                                             columns=columns, spacing_m=spacing_m)
                        if elevation_m is not None else crossing)
            # The published line is now the lossless source line, so the reported bound and the
            # tolerance flag describe **that** line, not the rejected candidate. The candidate's own
            # refusal stays on the record in ``candidate_refusal_reasons``; replacing it here would
            # be exactly the "clear screen hides the refusal" failure this row is meant to prevent.
            within = tolerance <= 0.0 or bounds["max_bound_m"] <= tolerance + 1e-9
            if candidate_foreign:
                blocked_by_contact += 1
            candidate_foreign = []
        kept_total += int(kept.size)
        source_total += int(source.shape[0])
        display_flat = _flatten(display, origin, columns)
        # Only the inter-reach handoff counts as contact: the edge from this reach's tail to the
        # cell its stored receiver drains into. The display line must keep that same handoff.
        flat_next = int(receiver.reshape(-1)[int(chain[-1])])
        if flat_next >= 0:
            source_contacts.add((int(chain[-1]), flat_next))
            display_contacts.add((int(display_flat[-1]), flat_next))
        foreign_contacts.extend(candidate_foreign)
        reports.append({
            "reach_index": index,
            "reach_id": rows[index].get("reach_id"),
            "source_cell_count": int(source.shape[0]),
            "display_cell_count": int(display.shape[0]),
            "display_is_source": bool(display.shape[0] == source.shape[0]),
            "fallback_to_source": bool(not accepted),
            "candidate_refusal_reasons": candidate_reasons,
            "source_world_path_sha256": world_path_sha256(source),
            "source_native": [[int(a), int(b)] for a, b in source.tolist()],
            "display_native": [[int(a), int(b)] for a, b in display.tolist()],
            "bounds": bounds,
            "anchors": anchors,
            "continuity": continuity,
            "receiver": consistent,
            "valley": crossing,
            "within_tolerance": bool(within),
        })
    return {
        "schema": SCHEMA,
        "logical_version": LOGICAL_VERSION,
        "tolerance_m": tolerance,
        "spacing_m": float(spacing_m),
        "origin_native_xz": origin,
        "grid_shape_zx": [int(receiver.shape[0]), int(receiver.shape[1])],
        "product_identity_sha256": product.get("identity_sha256"),
        "source_line": {"role": "authoritative ordered native trace",
                        "may_be_used_for": ["excavation", "routing", "physics", "audit"],
                        "cells_total": int(source_total)},
        "display_line": {"role": "drawing/index only",
                         "may_be_used_for": ["render", "index"],
                         "must_not_be_used_for": ["excavation", "routing", "physics"],
                         "cells_total": int(kept_total),
                         "lossless_fallback_reaches": int(fallback)},
        "reaches": reports,
        "counts": {"reaches": len(reports),
                   "display_equals_source": int(sum(1 for r in reports if r["display_is_source"])),
                   "simplified": int(sum(1 for r in reports if not r["display_is_source"])),
                   "fallback_to_source": int(fallback),
                   "fallback_because_of_foreign_contact": int(blocked_by_contact),
                   "candidate_refusal_reasons": dict(sorted(refusal_reasons.items())),
                   "source_cells": int(source_total),
                   "display_cells": int(kept_total)},
        "contact": contact_preserved(source_contacts, display_contacts, foreign_contacts),
        "separate_statements": {
            "receiver_consistency": "the ordered native trace must be the saved receiver's own path",
            "valley_axis": "a chord above both endpoints is a terrain cut, independent of area",
            "watershed_membership": ("the native receiver's basin membership is NOT implied by a "
                                     "polyline staying inside tolerance; the two are reported "
                                     "separately and neither certifies the other"),
        },
        "claims_denied": {"lowered_dem_resolution": True, "compression_ratio_claim": True,
                          "watershed_membership_from_polyline": True,
                          "one_metre_accuracy": True, "hydraulics": True},
    }


def describe():
    return {
        "schema": SCHEMA,
        "logical_version": LOGICAL_VERSION,
        "tolerances_m": list(DECLARED_TOLERANCES_M),
        "default_tolerance_m": DEFAULT_TOLERANCE_M,
        "reverse_sample_m": REVERSE_SAMPLE_M,
        "source_line_is_authoritative": True,
        "display_line_is_render_only": True,
        "contact_crossing_relation": CROSSING_RELATION,
        "contact_unsupported": CROSSING_UNSUPPORTED,
        "not_modelled": ["lowered_dem_resolution", "compression_ratio_claim",
                         "watershed_membership_from_polyline", "one_metre_accuracy",
                         "hydraulics", CROSSING_UNSUPPORTED],
    }
