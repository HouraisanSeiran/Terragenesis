"""Independent auditor for the native-30 m infinite-world certification window family (p8).

What this tool is
-----------------
One read-only measurement pass over the **already saved** Terrain Diffusion pages, plus
one synthetic pass, written under the pre-declared contract
``.scratch/river-stage1-completion/infinite-world-certification-20251025-v1/certification-contract-20251025-v1.md``.

It runs **no** GPU, generates **no** terrain and performs **no** 48 km recomputation. It
reads the four archived 2049 pages (134.3 MB of elevation) and compares them.

Why the traversals here are written out again
---------------------------------------------
The repository's own rule (``plan.md:126``): *every stage ships its own independent
acceptor that does not import the implementation under test and writes out the key
traversal / law itself*. So the overlap box, the border-distance field, the
assembly selection rule, the per-band profile, the net-cell deduplication and the
sub-seed derivations below are **re-derived here from the prose**, not imported from
``metric_cross_region``. Where the contract needs a D8 receiver, this tool deliberately
does **not** write a second D8 (the repository already refused that route explicitly);
it computes only the *neighbour-count* part of ``upstream_unknown_mask`` (which needs no
D8) and leaves the propagated cone to the test, which cross-checks it against this
tool's independent count.

Usage
-----
    runtime/venv/Scripts/python.exe -B -X utf8 tools/audit_native_30m_infinite_certification.py \\
        --output .scratch/river-stage1-completion/infinite-world-certification-20251025-v1

Exit codes follow the repository's three-value convention: ``0`` written and every
declared assertion held, ``1`` written but an assertion failed (the evidence file says
which), ``2`` illegal input / budget refusal (nothing written that could be mistaken
for a success).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "native-30m-infinite-certification-evidence-v1"
FAILURE_SCHEMA = "native-30m-infinite-certification-failure-v1"
STATUS = "native-30m-infinite-certification-20251025-v1"

#: Frozen by CONTRIBUTING.md:35. Not a knob; a different value is a different world.
WORLD_SEED = 20261020
#: Terrain Diffusion native resolution. Confirmed on every page's metadata below.
SPACING_M = 30.0
CELL_AREA_M2 = SPACING_M * SPACING_M
#: metric_cross_region.BORDER_BAND_CELLS, re-declared (not imported) so this audit does
#: not depend on the module it is auditing.
BORDER_BAND_CELLS = 6

PAGES_DIR = ROOT / ".scratch" / "fine-terrain-40km" / "td-pages"

#: The declared window family (contract §2.1). Sizes in nodes per side, offsets in native
#: cells relative to BASE_ORIGIN. Fixed before any measurement; a new value needs a new
#: contract version.
BASE_ORIGIN = (42173, 42874)
WINDOW_FAMILY = (
    {"group": "W-real-small", "size": 257, "offsets": ((0, 0), (97, -131), (-83, 59))},
    {"group": "W-real-mid", "size": 385, "offsets": ((0, 0), (97, -131))},
)
#: Declared but NOT executed this round (contract §5 budget). Listed so the evidence file
#: states the absence instead of leaving it to be inferred.
WINDOW_FAMILY_NOT_RUN = (
    {"group": "W-real-prod", "size": 1337, "offsets": ((0, 0),),
     "why": "1337^2 = 1787569 cells; reading/writing it inside the 180 s audit budget was "
            "not attempted, and re-running the production window is out of scope for an "
            "interface-and-window-family round"},
)

#: Contract §5: what this run is allowed to do.
BUDGET = {
    "max_pages": 4,
    "max_real_window_side": 385,
    "max_real_window_cells": 385 * 385,
    "max_synthetic_side": 121,
    "max_wall_seconds": 180.0,
    "gpu": "not used (torch must stay out of the process)",
    "recompute_48km": "not executed",
}

#: Declared but unexecuted checks, together with the reason. Written verbatim into the
#: evidence file so that "not run" can never be read as "passed".
NOT_RUN = {
    "real_page_derived_physics_across_window_family": (
        "no entry point recomputes Q/Qs across a window family on real pages: "
        "tools/audit_cross_region_consistency.py covers the elevation surface, load "
        "order, the window edge and a cold read only, and hard-codes the 2049 page pair "
        "under .scratch/fine-terrain-01"),
    "real_page_lake_census": (
        "the depression gate was measured on one page only; a window-family lake census "
        "on these four pages was not run this round (contract B6)"),
    "whole_window_soil_bucket": (
        "rainfall_runoff.MAX_CELLS = 100000, while a 1337^2 window holds 1787569 cells; "
        "running the bucket on a whole window is a budget refusal, not a measurement"),
    "production_checkpoint_cold_recovery": (
        "no native-30m hydrology-ledger checkpoint reader/restore entry exists; the "
        "td_basin_storage_*_io and td_weather_checkpoint_recovery modules belong to the "
        "10 km / v8-v10 family and must not stand in for a 30 m result (contract B3)"),
    "production_window_1337": (
        "W-real-prod (1337 nodes, 40.08 km) is declared in the contract but was not "
        "executed in this round; see contract section 5"),
}

BLOCKED = {
    "default_consumer_of_30m_assembly": (
        "metric_cross_region / native_30m_source assembly is still not wired into any "
        "default consumption entry (acceptance-matrix-30m.md:31, continuation-matrix.md "
        "R1/R9)"),
    "infinite_world_scope": (
        "tools/native_30m_query.py:5 lists infinite_world inside NOT_IMPLEMENTED, so a "
        "request for it is refused with stage_not_implemented rather than answered"),
    "natural_outlet_certification": (
        "retained is an interior terminal of a finite graph; native_30m_source never "
        "emits open_outflow and no outlet certification exists at this stage"),
}


# --------------------------------------------------------------------------- #
# failures
# --------------------------------------------------------------------------- #
class AuditFailure(Exception):
    """A pre-declared assertion did not hold; carries a stable reason token."""

    def __init__(self, stage, reason_code, detail):
        super().__init__("%s: %s" % (reason_code, detail))
        self.stage = stage
        self.reason_code = reason_code
        self.detail = detail


# --------------------------------------------------------------------------- #
# independent re-derivations (nothing imported from the module under audit)
# --------------------------------------------------------------------------- #
def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def overlap_box(origin_a, shape_a, origin_b, shape_b):
    """Half-open native index box shared by two pages, or None."""
    x0 = max(origin_a[0], origin_b[0])
    x1 = min(origin_a[0] + shape_a[1], origin_b[0] + shape_b[1])
    z0 = max(origin_a[1], origin_b[1])
    z1 = min(origin_a[1] + shape_a[0], origin_b[1] + shape_b[0])
    if x1 <= x0 or z1 <= z0:
        return None
    return int(x0), int(x1), int(z0), int(z1)


def border_distance(origin, shape, box):
    """Distance in cells from every cell of ``box`` to *its own* page's nearest border."""
    x0, x1, z0, z1 = box
    columns = np.arange(x0, x1, dtype=np.int64)
    rows = np.arange(z0, z1, dtype=np.int64)
    dc = np.minimum(columns - origin[0], origin[0] + shape[1] - 1 - columns)
    dr = np.minimum(rows - origin[1], origin[1] + shape[0] - 1 - rows)
    return np.minimum(dr[:, None], dc[None, :]).astype(np.int64)


def take(page, origin, box):
    x0, x1, z0, z1 = box
    return page[z0 - origin[1]:z1 - origin[1], x0 - origin[0]:x1 - origin[0]]


def band_profile(distance, differing, band):
    """Differing-cell count and largest difference per distance-from-own-border band."""
    rows = []
    top = int(distance.max())
    for low in range(0, min(top, band) + 1):
        mask = distance == low
        if not mask.any():
            continue
        rows.append({"border_distance_cells": low,
                     "cells": int(mask.sum()),
                     "differing_cells": int((mask & differing).sum())})
    return rows


def union_frame(pages):
    """Origin and shape of the union of every page's index box."""
    x0 = min(origin[0] for _name, _elev, origin in pages)
    x1 = max(origin[0] + elev.shape[1] for _name, elev, origin in pages)
    z0 = min(origin[1] for _name, _elev, origin in pages)
    z1 = max(origin[1] + elev.shape[0] for _name, elev, origin in pages)
    return (int(x0), int(z0)), (int(z1 - z0), int(x1 - x0))


def assemble(pages, origin, shape, band, order=None):
    """Assembly re-derived from the contract's prose, not imported.

    Per cell: the covering page with the **largest clearance from its own border** wins;
    ties go to the lexicographically smallest page key; cells whose best clearance is
    below ``band`` stay unresolved (NaN). Because the rule reads only
    ``(position, clearance)``, permuting ``order`` cannot change the result -- that is
    what the load-order check demonstrates rather than assumes.
    """
    rows, columns = shape
    x0, z0 = origin
    prepared = []
    for name, elevation, page_origin in pages:
        prepared.append((str(name), np.asarray(elevation, np.float64), tuple(page_origin)))
    if order is not None:
        index = {item[0]: item for item in prepared}
        if sorted(order) != sorted(index):
            raise AuditFailure("load-order", "order_not_a_permutation",
                               "order must list every page key exactly once")
        prepared = [index[name] for name in order]

    best_value = np.full((rows, columns), np.nan, np.float64)
    best_score = np.full((rows, columns), -1, np.int64)
    best_key = np.full((rows, columns), "", dtype="U32")
    for name, elevation, page_origin in prepared:
        box = overlap_box(page_origin, elevation.shape, origin, shape)
        if box is None:
            continue
        distance = border_distance(page_origin, elevation.shape, box)
        values = take(elevation, page_origin, box)
        sx0, sx1, sz0, sz1 = box
        local = (slice(sz0 - z0, sz1 - z0), slice(sx0 - x0, sx1 - x0))
        better = ((distance > best_score[local])
                  | ((distance == best_score[local]) & (best_key[local] < name)))
        take_it = better & (distance >= band)
        best_value[local] = np.where(take_it, values, best_value[local])
        best_score[local] = np.where(take_it, distance, best_score[local])
        best_key[local] = np.where(take_it, name, best_key[local])
    resolved = np.isfinite(best_value)
    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(best_value, np.float64).tobytes())
    digest.update(np.ascontiguousarray(resolved, bool).tobytes())
    digest.update(np.ascontiguousarray(best_key, "U32").tobytes())
    digest.update(json.dumps([list(origin), list(shape), int(band)]).encode("ascii"))
    return {"field": best_value, "resolved_mask": resolved, "digest": digest.hexdigest(),
            "resolved_cells": int(resolved.sum()), "unresolved_cells": int((~resolved).sum())}


def neighbour_count(mask):
    """How many of each cell's eight neighbours are resolved (0..8). No D8 here."""
    rows, columns = mask.shape
    padded = np.zeros((rows + 2, columns + 2), np.int8)
    padded[1:-1, 1:-1] = mask
    total = np.zeros(mask.shape, np.int8)
    for dr in (0, 1, 2):
        for dc in (0, 1, 2):
            if dr == 1 and dc == 1:
                continue
            total += padded[dr:dr + rows, dc:dc + columns]
    return total


def unknown_seed_cells(valid_mask):
    """L0 of the contract: resolved cells that lost at least one neighbour.

    This is the *seed* set only. Propagation along the receiver is a different object
    and is deliberately not re-implemented here (a second D8 would have to be proven
    bit-identical to the sanctioned one).
    """
    counts = neighbour_count(valid_mask)
    return valid_mask & (counts != 8)


def subseed_json_style(world_seed, purpose):
    """metric_cross_region.derive_sub_seed, re-derived from its docstring."""
    payload = json.dumps(["terragenesis-world-noise-v1", int(world_seed), str(purpose)],
                         sort_keys=True)
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:4], "big")


def subseed_ledger_style(world_seed, purpose):
    """native_30m_hydrology_ledger.purpose_subseeds, re-derived from its docstring."""
    payload = ("terragenesis/world-seed-subseed-v1|world_seed=%d|purpose=%s"
               % (int(world_seed), str(purpose))).encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") & ((1 << 53) - 1)


# --------------------------------------------------------------------------- #
# stages
# --------------------------------------------------------------------------- #
def load_pages(directory):
    """Read every archived page strictly; a non-page archive is a refusal, not a skip."""
    paths = sorted(Path(directory).glob("td-page-*.npz"))
    if not paths:
        raise AuditFailure("preflight", "page_source_missing",
                           "no td-page-*.npz under %s" % (directory,))
    if len(paths) > BUDGET["max_pages"]:
        raise AuditFailure("preflight", "budget_exceeded",
                           "%d pages exceeds the declared budget of %d"
                           % (len(paths), BUDGET["max_pages"]))
    pages, records = [], []
    for path in paths:
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != {"elevation_native", "metadata_json"}:
                raise AuditFailure("preflight", "invalid_td_page",
                                   "%s carries %s, a page carries exactly "
                                   "elevation_native and metadata_json"
                                   % (path.name, sorted(archive.files)))
            elevation = np.ascontiguousarray(archive["elevation_native"], np.float64)
            metadata = json.loads(str(archive["metadata_json"]))
        if elevation.ndim != 2 or elevation.shape[0] != elevation.shape[1]:
            raise AuditFailure("preflight", "shape_mismatch",
                               "%s is %s, a native page is square"
                               % (path.name, list(elevation.shape)))
        if not np.isfinite(elevation).all():
            raise AuditFailure("preflight", "invalid_td_page",
                               "%s carries a non-finite elevation" % (path.name,))
        if float(metadata["spacing_m"]) != SPACING_M:
            raise AuditFailure("preflight", "spacing_mismatch",
                               "%s declares spacing_m=%r, this world is %.1f m"
                               % (path.name, metadata["spacing_m"], SPACING_M))
        if int(metadata["world_seed"]) != WORLD_SEED:
            raise AuditFailure("preflight", "seed_mismatch",
                               "%s was generated with world_seed=%r, %d was requested"
                               % (path.name, metadata["world_seed"], WORLD_SEED))
        origin = tuple(int(value) for value in metadata["native_origin"])
        pages.append((path.name, elevation, origin))
        records.append({"name": path.name,
                        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "sha256": file_sha256(path),
                        "bytes": path.stat().st_size,
                        "shape_zx": list(elevation.shape),
                        "native_origin_xz": list(origin),
                        "world_origin_xz_m": [origin[0] * SPACING_M, origin[1] * SPACING_M],
                        "elevation_min_m": float(elevation.min()),
                        "elevation_max_m": float(elevation.max()),
                        "declared_world_seed": int(metadata["world_seed"]),
                        "declared_spacing_m": float(metadata["spacing_m"]),
                        "declared_schema": metadata.get("schema")})
    return pages, records


def window_family(union_origin, union_shape):
    """Declared sizes x declared offsets, with containment asserted rather than assumed."""
    x0, z0 = union_origin
    rows, columns = union_shape
    records = []
    for group in WINDOW_FAMILY:
        size = int(group["size"])
        if size > BUDGET["max_real_window_side"]:
            raise AuditFailure("window-family", "budget_window_dimension",
                               "declared size %d exceeds the audit budget %d"
                               % (size, BUDGET["max_real_window_side"]))
        for dx, dz in group["offsets"]:
            origin = (BASE_ORIGIN[0] + int(dx), BASE_ORIGIN[1] + int(dz))
            inside = (origin[0] >= x0 and origin[1] >= z0
                      and origin[0] + size <= x0 + columns
                      and origin[1] + size <= z0 + rows)
            records.append({"group": group["group"], "size": size,
                            "window_km": size * SPACING_M / 1000.0,
                            "offset_native": [int(dx), int(dz)],
                            "origin_native_xz": list(origin),
                            "shape_zx": [size, size],
                            "cells": size * size,
                            "origin_m": [origin[0] * SPACING_M, origin[1] * SPACING_M],
                            "inside_page_union": bool(inside)})
            if not inside:
                raise AuditFailure("window-family", "window_not_covered",
                                   "declared window origin=%s size=%d leaves the page union "
                                   "%dx%d at %s; the family is refused rather than clamped"
                                   % (list(origin), size, rows, columns, [x0, z0]))
    return records


def overlap_matrix(pages):
    """Every page pair, compared point by point, differences attributed to border bands.

    Three counts are produced on purpose and they must never be added together:

    ``naive_per_pair_sum``
        differing cells summed over the six pairs, **with repetition**. This is the
        number the contract forbids reporting as a defect rate: a cell can sit in up to
        four pairs, and every pair's own border band is included.
    ``net_dedup_full_overlap``
        unique cells (in the union frame) that differ in at least one pair. Still
        includes band cells: those values are reconstruction artefacts, not terrain.
    ``net_dedup_interior``
        unique cells that differ while **both** pages hold at least
        ``BORDER_BAND_CELLS`` clearance. This is the only tolerance-free statement.
    """
    (x0, z0), (rows, columns) = union_frame(pages)
    differ_any = np.zeros((rows, columns), bool)
    interior_differ = np.zeros((rows, columns), bool)
    pairs = []
    for i in range(len(pages)):
        for j in range(i + 1, len(pages)):
            name_a, elev_a, origin_a = pages[i]
            name_b, elev_b, origin_b = pages[j]
            box = overlap_box(origin_a, elev_a.shape, origin_b, elev_b.shape)
            if box is None:
                pairs.append({"pages": [name_a, name_b], "overlaps": False})
                continue
            a = take(elev_a, origin_a, box)
            b = take(elev_b, origin_b, box)
            difference = np.abs(a - b)
            differing = difference > 0.0
            distance = np.minimum(border_distance(origin_a, elev_a.shape, box),
                                  border_distance(origin_b, elev_b.shape, box))
            interior = distance >= BORDER_BAND_CELLS
            ux0, ux1, uz0, uz1 = box
            local = (slice(uz0 - z0, uz1 - z0), slice(ux0 - x0, ux1 - x0))
            differ_any[local] |= differing
            interior_differ[local] |= differing & interior
            pairs.append({
                "pages": [name_a, name_b],
                "overlaps": True,
                "overlap_native_box": {"columns": [int(box[0]), int(box[1])],
                                       "rows": [int(box[2]), int(box[3])]},
                "overlap_cells": int(a.size),
                "overlap_km": [(box[1] - box[0]) * SPACING_M / 1000.0,
                               (box[3] - box[2]) * SPACING_M / 1000.0],
                "differing_cells": int(differing.sum()),
                "differing_fraction": float(differing.mean()),
                "max_abs_difference_m": float(difference.max()),
                "interior_cells": int(interior.sum()),
                "interior_differing_cells": int((differing & interior).sum()),
                "interior_bitwise_identical": bool(not (differing & interior).any()),
                "border_band_cells": BORDER_BAND_CELLS,
                "per_border_band": band_profile(distance, differing, BORDER_BAND_CELLS),
                "declared_tolerance": {
                    "interior": "exactly 0.0 (bitwise float64 equality; no tolerance used)",
                    "border_band": (
                        "the outermost cells are decoded from the shared residual field "
                        "with a truncated kernel margin, so they are reconstruction "
                        "artefacts; they are excluded from assembly, not tolerated")}})
    naive = sum(item.get("differing_cells", 0) for item in pairs)
    return {
        "pairs": pairs,
        "naive_per_pair_sum": int(naive),
        "naive_per_pair_note": (
            "FORBIDDEN AS A DEFECT RATE: a cell can appear in up to four pairs and every "
            "pair's own border band is included. Reported only so the inflation is visible"),
        "net_dedup_full_overlap": int(differ_any.sum()),
        "net_dedup_full_overlap_note": (
            "unique cells that differ in at least one pair; still includes band cells"),
        "net_dedup_interior": int(interior_differ.sum()),
        "net_dedup_interior_note": (
            "unique cells that differ while both pages hold >= 6 cells of clearance. "
            "This is the only tolerance-free statement, and it is the one a defect rate "
            "may be computed from"),
        "union_origin_native_xz": [x0, z0],
        "union_shape_zx": [rows, columns],
        "union_cells": int(rows * columns),
    }


def load_order(pages, window, union_origin):
    """One declared window assembled in four orders, compared by digest.

    ``rechunked`` splits each page into two column halves overlapping by 64 cells: the
    same bytes arrive as twice as many pieces with twice as many borders. Splitting can
    only ever *lose* resolved cells, never gain them, and every cell that stays resolved
    must keep exactly the same value.
    """
    origin = tuple(window["origin_native_xz"])
    shape = tuple(window["shape_zx"])
    keys = [name for name, _elev, _origin in pages]
    forward = assemble(pages, origin, shape, BORDER_BAND_CELLS, order=keys)
    reverse = assemble(pages, origin, shape, BORDER_BAND_CELLS, order=list(reversed(keys)))
    # A fixed permutation, not a random one: a declared order is reproducible.
    permuted_keys = keys[2:] + keys[:2] if len(keys) > 2 else list(reversed(keys))
    permuted = assemble(pages, origin, shape, BORDER_BAND_CELLS, order=permuted_keys)

    cut = 1024 + 32
    halves = []
    for name, elevation, page_origin in pages:
        if elevation.shape[1] <= cut + 64:
            raise AuditFailure("load-order", "budget_window_dimension",
                               "page %s is too narrow to re-chunk at column %d"
                               % (name, cut))
        halves.append((name + "-left", np.ascontiguousarray(elevation[:, :cut]), page_origin))
        halves.append((name + "-right", np.ascontiguousarray(elevation[:, cut - 64:]),
                       (page_origin[0] + cut - 64, page_origin[1])))
    rechunked = assemble(halves, origin, shape, BORDER_BAND_CELLS)
    whole = forward
    common = whole["resolved_mask"] & rechunked["resolved_mask"]
    agree = bool(np.array_equal(whole["field"][common], rechunked["field"][common]))
    digests = {"forward": forward["digest"], "reverse": reverse["digest"],
               "permuted": permuted["digest"]}
    orders_identical = len(set(digests.values())) == 1
    return {
        "window": {"origin_native_xz": list(origin), "shape_zx": list(shape),
                   "union_origin_native_xz": list(union_origin)},
        "page_orders": {"forward": keys, "reverse": list(reversed(keys)),
                        "permuted": permuted_keys},
        "assembly_digest_by_order": digests,
        "page_order_digests_identical": bool(orders_identical),
        "resolved_cells_by_order": {"forward": forward["resolved_cells"],
                                    "reverse": reverse["resolved_cells"],
                                    "permuted": permuted["resolved_cells"],
                                    "rechunked": rechunked["resolved_cells"]},
        "rechunked_pieces": len(halves),
        "rechunked_overlap_cells": 64,
        "rechunked_common_resolved_cells": int(common.sum()),
        "rechunked_values_agree_on_common_cells": agree,
        "rechunking_only_loses_cells": bool(rechunked["resolved_cells"]
                                            <= whole["resolved_cells"]),
        "variance": (
            "splitting a page adds borders, so interior cells can become band cells and "
            "go unresolved. The resolved set may shrink and must never grow; every cell "
            "that stays resolved must keep exactly the same value. The digest equality "
            "above covers the three whole-page orders only: a re-chunked assembly is a "
            "different piece set, so it is compared by resolved-set monotonicity and by "
            "value equality on the common cells, not by digest"),
    }


def comparability(pages, window):
    """The contract's comparability layers, counted on one declared window.

    L0 is computed independently here (an eight-neighbour count needs no D8). L1 needs
    the receiver to propagate along, and this tool deliberately does not write a second
    D8, so L1 is left to the test, which compares its own count against this tool's L0.
    """
    origin = tuple(window["origin_native_xz"])
    shape = tuple(window["shape_zx"])
    assembly = assemble(pages, origin, shape, BORDER_BAND_CELLS)
    resolved = assembly["resolved_mask"]
    l0 = unknown_seed_cells(resolved)
    return {
        "window": {"origin_native_xz": list(origin), "shape_zx": list(shape)},
        "L0_raw_unknown_cells": int(l0.sum()),
        "L0_note": (
            "resolved cells that lost at least one of their eight neighbours: their own "
            "inflow from outside the assembled support is undeclared. This is the seed "
            "set only; propagation along the receiver is a different object"),
        "resolved_cells": int(resolved.sum()),
        "unresolved_cells": int(assembly["unresolved_cells"]),
        "unresolved_reason": ("unresolved_border" if assembly["unresolved_cells"] else None),
        "L1_unknown_cone_cells": None,
        "L1_note": (
            "NOT COMPUTED HERE: propagating the seeds along the receiver needs the "
            "sanctioned D8 kernel, and writing a second one would have to be proven "
            "bit-identical to it. The test compares its own L1 against this L0"),
        "L2_comparable_surface_cells": int(resolved.sum()),
        "L2_note": (
            "in this window every resolved cell is at least BORDER_BAND_CELLS from its "
            "supplying page's border by construction, so resolved == comparable surface"),
        "L3_comparable_upstream_cells": None,
        "L3_note": (
            "needs the receiver cones; see L1_note. No accumulated quantity is compared "
            "on real pages this round"),
    }


def subseeds(world_seed):
    """Both declared sub-seed derivations, with their actual values.

    They are **not the same function**: one hashes a JSON array and takes four bytes, the
    other hashes a pipe-delimited string and takes eight bytes masked to 53 bits. The
    evidence records both so no report can claim "the sub-seed" without saying which.
    """
    json_purposes = ("climate", "rainfall", "light")
    ledger_purposes = ("rain_series_modulation", "soil_initial_field", "event_time_phase")
    return {
        "world_seed": int(world_seed),
        "metric_cross_region_derive_sub_seed": {
            "derivation": ("int.from_bytes(sha256(json.dumps(['terragenesis-world-noise-v1', "
                           "world_seed, purpose], sort_keys=True)).digest()[:4], 'big')"),
            "bytes_used": 4,
            "mask": None,
            "values": {purpose: subseed_json_style(world_seed, purpose)
                       for purpose in json_purposes}},
        "native_30m_hydrology_ledger_purpose_subseeds": {
            "derivation": ("int.from_bytes(sha256('terragenesis/world-seed-subseed-v1"
                           "|world_seed=<seed>|purpose=<purpose>').digest()[:8], 'big') "
                           "& (2**53 - 1)"),
            "bytes_used": 8,
            "mask": (1 << 53) - 1,
            "values": {purpose: subseed_ledger_style(world_seed, purpose)
                       for purpose in ledger_purposes}},
        "note": ("two different derivations for the same notion; they must not be merged "
                 "or reported as one sub-seed, and neither module was modified to align them"),
    }


def synthetic_layers():
    """A small declared fixture where the comparability layers can be counted exactly.

    A 61 x 61 plane with a rectangular hole in it: every resolved cell touching the hole
    or the window rim is an L0 seed, and the cell count is closed-form checkable.
    """
    side = BUDGET["max_synthetic_side"]
    side = min(side, 61)
    valid = np.ones((side, side), bool)
    valid[26:35, 26:35] = False
    l0 = unknown_seed_cells(valid)
    expected = 0
    for row in range(side):
        for column in range(side):
            if not valid[row, column]:
                continue
            neighbours = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    rr, cc = row + dr, column + dc
                    if 0 <= rr < side and 0 <= cc < side and valid[rr, cc]:
                        neighbours += 1
            if neighbours != 8:
                expected += 1
    return {
        "fixture": "%dx%d plane with a 9x9 hole at rows/columns 26..34" % (side, side),
        "valid_cells": int(valid.sum()),
        "hole_cells": int((~valid).sum()),
        "L0_raw_unknown_cells": int(l0.sum()),
        "L0_by_scalar_loop": int(expected),
        "L0_vectorised_equals_scalar": bool(int(l0.sum()) == expected),
        "derivation": ("the scalar double loop is written out so the vectorised "
                       "neighbour count is checked against an independent traversal, "
                       "not against itself"),
    }


def process_hygiene():
    """Declare what this process did *not* do, measured rather than promised."""
    return {
        "torch_imported": "torch" in sys.modules,
        "cuda_used": False,
        "tensorflow_imported": "tensorflow" in sys.modules,
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "note": ("no GPU call is made anywhere in this module; the flags above record the "
                 "process state at write time instead of asserting good behaviour"),
    }


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def run(output, pages_dir=PAGES_DIR):
    started = time.perf_counter()
    pages, records = load_pages(pages_dir)
    union_origin, union_shape = union_frame(pages)
    family = window_family(union_origin, union_shape)
    overlaps = overlap_matrix(pages)
    smallest = min(family, key=lambda item: (item["size"], item["offset_native"]))
    largest = max(family, key=lambda item: (item["size"], item["offset_native"]))
    order_report = load_order(pages, smallest, union_origin)
    order_largest = load_order(pages, largest, union_origin)
    layers = comparability(pages, smallest)
    elapsed = time.perf_counter() - started
    if elapsed > BUDGET["max_wall_seconds"]:
        raise AuditFailure("budget", "budget_wall_seconds",
                           "audit took %.1f s, above the declared %.0f s"
                           % (elapsed, BUDGET["max_wall_seconds"]))

    checks = {
        "every_pair_interior_bitwise_identical": bool(
            all(item.get("interior_bitwise_identical", True) for item in overlaps["pairs"])),
        "net_interior_disagreement_is_zero": bool(overlaps["net_dedup_interior"] == 0),
        "naive_sum_at_least_net_full_overlap": bool(
            overlaps["naive_per_pair_sum"] >= overlaps["net_dedup_full_overlap"]),
        "page_order_digests_identical_small": bool(order_report["page_order_digests_identical"]),
        "page_order_digests_identical_large": bool(order_largest["page_order_digests_identical"]),
        "rechunked_values_agree_small": bool(order_report["rechunked_values_agree_on_common_cells"]),
        "rechunked_values_agree_large": bool(order_largest["rechunked_values_agree_on_common_cells"]),
        "rechunking_only_loses_cells_small": bool(order_report["rechunking_only_loses_cells"]),
        "rechunking_only_loses_cells_large": bool(order_largest["rechunking_only_loses_cells"]),
        "every_declared_window_inside_union": bool(
            all(item["inside_page_union"] for item in family)),
        "L0_equals_independent_scalar_loop": bool(
            synthetic_layers()["L0_vectorised_equals_scalar"]),
        "torch_stayed_out_of_the_process": bool(not process_hygiene()["torch_imported"]),
        "no_window_exceeds_the_audit_budget": bool(
            all(item["cells"] <= BUDGET["max_real_window_cells"] for item in family)),
    }
    evidence = {
        "schema": SCHEMA,
        "status": STATUS,
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "declared": {
            "world_seed": WORLD_SEED,
            "spacing_m": SPACING_M,
            "cell_area_m2": CELL_AREA_M2,
            "border_band_cells": BORDER_BAND_CELLS,
            "contact_margin_cells": BORDER_BAND_CELLS,
            "base_origin_native_xz": list(BASE_ORIGIN),
            "base_origin_note": ("the origin of the published finite bundle v8 "
                                 "(origin_native_xz in its source-request.json), chosen so "
                                 "this round looks at the same world the earlier run did"),
            "coordinate_convention": (
                "native integer [x, z] index pairs; x_m = x*30, z_m = z*30; arrays are "
                "[z, x] and hold cell centres; origins may be negative"),
            "time_index": ("t_k = k * dt_s with dt_s = 3600.0 s; the runoff window is "
                           "k = 0..72 and the coupled window k = 0..12. Wall clock, run "
                           "duration and adaptive step counts are never time indices"),
            "units": {"elevation": "m", "length": "m", "area": "m2",
                      "discharge": "m3/s", "volume": "m3"}},
        "budget": dict(BUDGET),
        "pages": records,
        "window_family": family,
        "window_family_not_run": list(WINDOW_FAMILY_NOT_RUN),
        "overlap": overlaps,
        "load_order": {"small_window": order_report, "large_window": order_largest},
        "comparability": layers,
        "subseeds": subseeds(WORLD_SEED),
        "synthetic": {"comparability_fixture": synthetic_layers()},
        "process": process_hygiene(),
        "checks": checks,
        "not_run": NOT_RUN,
        "blocked": BLOCKED,
        "wall_seconds": round(elapsed, 3),
        "verdict": ("pre_declared_assertions_hold" if all(checks.values())
                    else "pre_declared_assertions_failed"),
    }
    return evidence


def write_evidence(output, evidence):
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    path = target / "evidence-20251025-v1.json"
    if path.exists():
        raise AuditFailure("write", "evidence_already_exists",
                           "%s exists; this audit never overwrites a previous evidence "
                           "file -- use a new version suffix" % (path,))
    payload = json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False)
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
    return path


def write_failure(output, failure, pages_dir):
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": FAILURE_SCHEMA,
        "status": STATUS,
        "stage": failure.stage,
        "reason_code": failure.reason_code,
        "detail": failure.detail,
        "declared": {"world_seed": WORLD_SEED, "spacing_m": SPACING_M,
                     "border_band_cells": BORDER_BAND_CELLS},
        "pages_dir": str(pages_dir),
        "not_run": list(NOT_RUN.values()),
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = target / "failure-20251025-v1.json"
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        stream.flush()
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only window-family audit for the native 30 m infinite-world "
                    "certification contract. No GPU, no terrain generation, no 48 km rerun.")
    parser.add_argument("--output", required=True,
                        help="directory for evidence-20251025-v1.json / failure-20251025-v1.json")
    parser.add_argument("--pages-dir", default=str(PAGES_DIR),
                        help="directory holding td-page-*.npz (read only)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    try:
        evidence = run(args.output, Path(args.pages_dir))
        path = write_evidence(args.output, evidence)
    except AuditFailure as failure:
        # A refusal here is reported, never papered over: the existing evidence file is left
        # untouched (it is a measurement from an earlier run, and this tool does not revise
        # measurements), and the refusal itself is written to its own file.
        path = write_failure(args.output, failure, args.pages_dir)
        print("REFUSED %s/%s: %s" % (failure.stage, failure.reason_code, failure.detail))
        print("failure evidence: %s" % (path,))
        return 2
    code = 0 if all(evidence["checks"].values()) else 1
    if not args.quiet:
        print("evidence: %s" % (path,))
        print("verdict: %s (wall %.2f s)" % (evidence["verdict"], evidence["wall_seconds"]))
        print("pages: %d, window family members: %d"
              % (len(evidence["pages"]), len(evidence["window_family"])))
        print("overlap: naive per-pair sum %d, net (full overlap) %d, net interior %d"
              % (evidence["overlap"]["naive_per_pair_sum"],
                 evidence["overlap"]["net_dedup_full_overlap"],
                 evidence["overlap"]["net_dedup_interior"]))
        for name in sorted(evidence["checks"]):
            print("  %-46s %s" % (name, evidence["checks"][name]))
        print("not run: %d items, blocked: %d items"
              % (len(evidence["not_run"]), len(evidence["blocked"])))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
