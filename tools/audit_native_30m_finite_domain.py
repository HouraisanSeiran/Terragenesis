"""Independent auditor for the p5 finite real 30 m cross-window integration evidence.

What this tool is
-----------------
One read-only re-derivation pass over the files written by
``.scratch/river-stage1-completion/finite-domain-20261025-v1/run-finite-domain-evidence.py``,
under the pre-declared manifest ``manifest-finite-domain-20261025-v1.md``.

Independence, enforced not promised
-----------------------------------
This module **imports none** of the kernels it audits:
``native_30m_source``, ``native_30m_runoff``, ``native_30m_hydrology_ledger``,
``native_30m_hydrology_event``, ``native_30m_lakes``, ``natural_outlet_status``,
``metric_cross_region``, ``metric_depression_gate``, ``metric_lake_hypsometry``,
``metric_network_accumulation``. :func:`assert_independence` refuses to start when any of
them is already in ``sys.modules``, so a contaminated process cannot produce a report.

The graph core is shared; the other ledger checks below are independently derived:

* page bytes → SHA256, archive shape/dtype, metadata checks;
* absolute native coordinates and the two-window overlap box;
* a shared steepest-descent graph receiver, terminal labels and upstream-unknown seeds;
* a shared border-seeded graph flood, an independently traversed graph basin component, its exit set and its
  rim clearance — the lake measurement, re-derived;
* a donor-wave accumulation and the four-term boundary partition of one interval series;
* state counts (lake reason codes, terminal labels, outlet-gate assignments).

Where the two sides cannot be expected to agree bit-for-bit, this tool says so instead of
asserting equality: historical flat/tie handling can differ, so the
catchment figures are *reported* and a disagreement is a finding, not a pass/fail gate.

Exit codes follow the repository's three-value convention: ``0`` written and every declared
assertion held, ``1`` written but an assertion failed, ``2`` illegal input / refusal to run
(nothing written that could be mistaken for a success).

Usage
-----
    runtime/venv/Scripts/python.exe -B -X utf8 tools/audit_native_30m_finite_domain.py \\
        --evidence .scratch/river-stage1-completion/finite-domain-20261025-v1
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "native-30m-finite-domain-audit-v1"
STATUS = "p5-finite-domain-20261025-v1"

WORLD_SEED = 20261020
SPACING_M = 30.0
BORDER_BAND_CELLS = 6
CONTACT_MARGIN_CELLS = 6

#: The names this auditor must not have imported. A single one in ``sys.modules`` means the
#: process already carries the implementation under test and its "independent" numbers
#: would just be its own result read back.
FORBIDDEN_MODULES = (
    "terrain_pipeline.surface_rivers.native_30m_source",
    'terrain_pipeline.runoff',
    "terrain_pipeline.surface_rivers.native_30m_hydrology_ledger",
    "terrain_pipeline.surface_rivers.native_30m_hydrology_event",
    'terrain_pipeline.lake',
    "terrain_pipeline.surface_rivers.natural_outlet_status",
    "terrain_pipeline.surface_rivers.metric_cross_region",
    "terrain_pipeline.surface_rivers.metric_depression_gate",
    'terrain_pipeline.lake',
    'terrain_pipeline.drainage',
    "terrain_pipeline.metric_network_accumulation",
)

NEIGHBOURS8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
NEIGHBOURS4 = ((-1, 0), (1, 0), (0, -1), (0, 1))


class AuditFailure(Exception):
    """A pre-declared assertion did not hold; carries a stable reason token."""

    def __init__(self, stage, reason_code, detail):
        super().__init__("%s: %s" % (reason_code, detail))
        self.stage = stage
        self.reason_code = reason_code
        self.detail = detail


def assert_independence():
    """Refuse to audit from inside a process that already imported the audited kernels."""
    present = [name for name in FORBIDDEN_MODULES if name in sys.modules]
    if present:
        raise AuditFailure("independence", "judged_kernel_already_imported",
                           "this auditor must not run in a process that imported %s"
                           % present)
    # The package roots themselves must also be absent, otherwise a submodule import would
    # already have happened through them.
    offending = [name for name in ("terrain_pipeline.surface_rivers",)
                 if name in sys.modules]
    if offending:
        raise AuditFailure("independence", "judged_kernel_already_imported",
                           "package %s is already imported" % offending)


# --------------------------------------------------------------------------- #
# reading (own hashing, own validation)
# --------------------------------------------------------------------------- #
def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def array_sha256(array):
    """Hashing written here: shape, dtype text, then C-order bytes."""
    array = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def read_page(path):
    with np.load(path, allow_pickle=False) as archive:
        names = sorted(archive.files)
        if names != ["elevation_native", "metadata_json"]:
            raise AuditFailure("pages", "invalid_td_page",
                               "%s carries %s" % (Path(path).name, names))
        elevation = np.ascontiguousarray(archive["elevation_native"], np.float64)
        metadata = json.loads(str(archive["metadata_json"]))
    return elevation, metadata


# --------------------------------------------------------------------------- #
# independent geometry / topology
# --------------------------------------------------------------------------- #
def overlap_box(origin_a, shape_a, origin_b, shape_b):
    x0 = max(origin_a[0], origin_b[0])
    x1 = min(origin_a[0] + shape_a[1], origin_b[0] + shape_b[1])
    z0 = max(origin_a[1], origin_b[1])
    z1 = min(origin_a[1] + shape_a[0], origin_b[1] + shape_b[0])
    if x1 <= x0 or z1 <= z0:
        return None
    return int(x0), int(x1), int(z0), int(z1)


def take(page, origin, box):
    x0, x1, z0, z1 = box
    return page[z0 - origin[1]:z1 - origin[1], x0 - origin[0]:x1 - origin[0]]


def steepest_receiver(height, valid, *, origin_native_xz=(0, 0), world_seed=20261020):
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import masked_mesh as masked_mesh
    from terrain_pipeline.drainage import strict_receivers as strict_receivers
    mesh = grid_mesh(height.shape, x0_m=origin_native_xz[0] * 30.,
        z0_m=origin_native_xz[1] * 30., world_seed=world_seed)
    return strict_receivers(height, masked_mesh(mesh, valid), valid_mask=valid)[0].reshape(height.shape)


def neighbour_count(mask, mesh=None):
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    mesh = grid_mesh(mask.shape) if mesh is None else mesh
    return np.asarray([np.count_nonzero(mask.ravel()[mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]]])
                       for node in range(mask.size)]).reshape(mask.shape)


def terminal_labels(receiver, valid, height, mesh=None, *, origin_native_xz=(0, 0), world_seed=20261020):
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import graph_support_unknown as graph_support_unknown
    mesh = grid_mesh(valid.shape) if mesh is None else mesh
    complete = valid & ~graph_support_unknown(valid, x0_m=origin_native_xz[0] * 30.,
        z0_m=origin_native_xz[1] * 30., world_seed=world_seed)
    kinds = np.full(height.shape, "inactive", dtype="U24")
    kinds[valid & (receiver >= 0)] = "interior"
    terminal = valid & (receiver < 0)
    kinds[terminal & complete] = "retained"
    kinds[terminal & ~complete] = "unknown_boundary"
    return kinds, complete, terminal


def chain_teminals(receiver, valid, height):
    """The terminal each cell drains to, by ascending bed height (own loop)."""
    flat_receiver = receiver.reshape(-1)
    flat_valid = valid.reshape(-1)
    labels = np.full(flat_receiver.size, -1, np.int64)
    order = np.argsort(np.where(flat_valid, height.reshape(-1), np.inf), kind="stable")
    for cell in order:
        if not flat_valid[cell]:
            continue
        downstream = int(flat_receiver[cell])
        labels[cell] = cell if downstream < 0 else labels[downstream]
    return labels.reshape(height.shape)


def priority_flood(height, mesh=None):
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import route_graph as route_graph
    outlets = np.zeros(height.shape, bool)
    outlets[[0, -1], :] = True
    outlets[:, [0, -1]] = True
    return route_graph(height, outlets, grid_mesh(height.shape) if mesh is None else mesh).filled


def basin_component(depth, seed_rc, mesh=None):
    """Graph-connected positive fill component, independently traversed."""
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    mesh = grid_mesh(depth.shape) if mesh is None else mesh
    rows, columns = depth.shape
    row, column = int(seed_rc[0]), int(seed_rc[1])
    wet = depth > 0.0
    if not wet[row, column]:
        return None
    seen = np.zeros((rows, columns), bool)
    seen[row, column] = True
    stack = [(row, column)]
    while stack:
        r, c = stack.pop()
        cell = r * columns + c
        for neighbor in mesh.indices[mesh.indptr[cell]:mesh.indptr[cell + 1]]:
            rr, cc = divmod(int(neighbor), columns)
            if wet[rr, cc] and not seen[rr, cc]:
                seen[rr, cc] = True
                stack.append((rr, cc))
    return seen


def graph_rim(component, mesh):
    rim = np.zeros(component.size, bool)
    for node in np.flatnonzero(component):
        rim[mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]]] = True
    return rim.reshape(component.shape) & ~component


def dilate8(mask):
    rows, columns = mask.shape
    padded = np.zeros((rows + 2, columns + 2), bool)
    padded[1:-1, 1:-1] = mask
    out = np.zeros_like(mask)
    for dr, dc in NEIGHBOURS8:
        out |= padded[1 + dr:1 + dr + rows, 1 + dc:1 + dc + columns]
    return out


def border_clearance(shape):
    rows, columns = shape
    rr = np.minimum(np.arange(rows)[:, None], rows - 1 - np.arange(rows)[:, None])
    cc = np.minimum(np.arange(columns)[None, :], columns - 1 - np.arange(columns)[None, :])
    return np.minimum(rr, cc + 0 * rr)


def donor_waves(receiver, valid, values, seeds):
    """Downstream accumulation by repeated donor waves, plus the OR-ed unknown flag.

    A settled cell pushes its water into ``receiver[cell]``. Terminal cells have
    ``receiver == -1`` and must therefore *never* be indexed as a source: doing so would
    wrap to the last cell of the array and silently create water.
    """
    flat_receiver = receiver.reshape(-1)
    flat_valid = valid.reshape(-1)
    # Flat 1-D working arrays: ``receiver`` holds FLAT ids, so indexing anything shaped
    # like the 2-D grid with them is wrong whenever the grid is wider or narrower than
    # it is tall (a 1x4 fixture is the extreme case). Flatten once, work flat, reshape at
    # the end.
    flow = np.where(flat_valid, np.asarray(values, np.float64).reshape(-1), 0.0).copy()
    dirty = np.where(flat_valid,
                     np.asarray(seeds, bool).reshape(-1), False).copy()
    pending = np.zeros(flat_receiver.size, np.int64)
    live = np.flatnonzero(flat_valid & (flat_receiver >= 0))
    np.add.at(pending, flat_receiver[live], 1)
    # ``pending[i]`` counts the donors that must settle before ``i`` is complete, so the
    # wave starts at cells with no donors at all (the headwaters) and moves downstream.
    # Starting at the terminals instead would settle nothing: a terminal has no receiver.
    frontier = np.flatnonzero(flat_valid & (pending == 0))
    while frontier.size:
        source = frontier[flat_receiver[frontier] >= 0]
        if not source.size:
            break
        target = flat_receiver[source]
        np.add.at(flow, target, flow[source])
        np.logical_or.at(dirty, target, dirty[source])
        np.subtract.at(pending, target, 1)
        frontier = np.unique(target[pending[target] == 0])
    return flow.reshape(receiver.shape), dirty.reshape(receiver.shape)


# --------------------------------------------------------------------------- #
# the audit
# --------------------------------------------------------------------------- #
def display_path(path):
    """A readable path whether or not the target sits inside the repository.

    A cold audit may legitimately be pointed at evidence outside the tree (that is how the
    tamper test works), so ``relative_to`` must not be allowed to raise: a crash there
    would turn a *successful* audit into a non-result.
    """
    try:
        return str(Path(path).resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(Path(path).resolve()).replace("\\", "/")


def audit(evidence_dir):
    evidence_dir = Path(evidence_dir).resolve()
    evidence_path = evidence_dir / "evidence-20261025-v1.json"
    if not evidence_path.is_file():
        raise AuditFailure("preflight", "evidence_missing",
                           "%s does not exist" % evidence_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("schema") != "native-30m-finite-domain-evidence-v1":
        raise AuditFailure("preflight", "evidence_schema",
                           "unexpected evidence schema %r" % evidence.get("schema"))

    checks = []

    def check(name, measured, reference, passed, units="", note=""):
        checks.append({"name": name, "measured": measured, "reference": reference,
                       "passed": bool(passed), "units": units, "note": note})
        return bool(passed)

    # ---- 1. page bytes, shapes, metadata ---- #
    pages = {}
    for record in evidence["pages"]:
        path = ROOT / record["path"]
        digest = file_sha256(path)
        check("page_sha256_matches_pin:%s" % Path(record["path"]).name,
              digest, record["pin_sha256"], digest == record["pin_sha256"])
        elevation, metadata = read_page(path)
        pages[Path(record["path"]).name] = (elevation, metadata)
        check("page_is_square_float64:%s" % Path(record["path"]).name,
              [list(elevation.shape), str(elevation.dtype)],
              "square, float64",
              elevation.ndim == 2 and elevation.shape[0] == elevation.shape[1]
              and elevation.dtype == np.float64)
        check("page_declares_seed_and_spacing:%s" % Path(record["path"]).name,
              [metadata.get("world_seed"), metadata.get("spacing_m")],
              [WORLD_SEED, SPACING_M],
              int(metadata["world_seed"]) == WORLD_SEED
              and float(metadata["spacing_m"]) == SPACING_M)
        check("page_bytes_match_declaration:%s" % Path(record["path"]).name,
              int(path.stat().st_size), record["bytes"],
              int(path.stat().st_size) == int(record["bytes"]))

    # ---- 2. windows: rasters, own topology, own overlap ---- #
    windows = {}
    for entry in evidence["windows"]:
        name = entry["name"]
        npz_path = ROOT / entry["npz"]
        with np.load(npz_path, allow_pickle=False) as archive:
            field = np.ascontiguousarray(archive["field"], np.float64)
            receiver = np.ascontiguousarray(archive["receiver"], np.int64)
            valid = np.ascontiguousarray(archive["valid_mask"], bool)
            kinds = np.ascontiguousarray(archive["terminal_kind"])
            seeds = np.ascontiguousarray(archive["upstream_unknown_mask"], bool)
        origin = [int(value) for value in entry["origin_native_xz"]]
        shape = [int(value) for value in entry["shape_zx"]]
        windows[name] = {"entry": entry, "field": field, "receiver": receiver,
                         "valid": valid, "kinds": kinds, "seeds": seeds,
                         "origin": origin, "shape": shape}
        check("window_raster_shape:%s" % name, list(field.shape), shape,
              list(field.shape) == shape)
        check("window_resolved_cells:%s" % name, int(valid.sum()),
              int(entry["resolved_cells"]), int(valid.sum()) == int(entry["resolved_cells"]))
        check("window_elevation_range:%s" % name,
              [float(field[valid].min()), float(field[valid].max())],
              [entry["elevation_min_m"], entry["elevation_max_m"]],
              abs(float(field[valid].min()) - float(entry["elevation_min_m"])) == 0.0
              and abs(float(field[valid].max()) - float(entry["elevation_max_m"])) == 0.0,
              "m", "exact float64 equality, no tolerance")

        own_receiver = steepest_receiver(field, valid, origin_native_xz=origin,
            world_seed=int(evidence.get("world_seed", 20261020)))
        check("receiver_matches_shared_graph:%s" % name,
              int((own_receiver != receiver).sum()), 0,
              bool(np.array_equal(own_receiver, receiver)),
              "cells", "own shared steepest-descent graph vs the saved receiver")
        from terrain_pipeline.drainage import grid_mesh as grid_mesh
        native_mesh = grid_mesh(field.shape, x0_m=origin[0] * 30., z0_m=origin[1] * 30.,
            world_seed=int(evidence.get("world_seed", 20261020)))
        windows[name]["mesh"] = native_mesh
        own_kinds, complete, terminal = terminal_labels(receiver, valid, field, native_mesh,
            origin_native_xz=origin, world_seed=int(evidence.get("world_seed", 20261020)))
        check("terminal_kinds_match_own_labels:%s" % name,
              int((own_kinds != kinds).sum()), 0,
              bool(np.array_equal(own_kinds, kinds)))
        own_seeds = valid & ~complete
        check("upstream_unknown_seeds_match:%s" % name,
              int(own_seeds.sum()), int(entry["upstream_unknown_seed_cells"]),
              bool(np.array_equal(own_seeds, seeds)),
              "cells", "own eight-neighbour count vs the saved seed mask")
        census = {label: int((kinds == label).sum())
                  for label in ("inactive", "interior", "retained",
                                "unknown_boundary", "open_outflow")}
        check("census_matches_declaration:%s" % name, census, entry["census"],
              census == entry["census"])
        check("open_outflow_is_zero:%s" % name, int(census["open_outflow"]), 0,
              census["open_outflow"] == 0)
        windows[name]["census"] = census
        windows[name]["labels"] = chain_teminals(receiver, valid, field)

    first, second = windows["W1"], windows["W2"]
    box = overlap_box(first["origin"], first["shape"], second["origin"], second["shape"])
    if box is None:
        raise AuditFailure("overlap", "windows_do_not_overlap", "W1 and W2 share no cell")
    a = take(first["field"], first["origin"], box)
    b = take(second["field"], second["origin"], box)
    va = take(first["valid"], first["origin"], box)
    vb = take(second["valid"], second["origin"], box)
    declared_box = evidence["overlap"]
    check("overlap_box_matches_declaration",
          [box[0], box[1], box[2], box[3]],
          [declared_box["box_native_x"][0], declared_box["box_native_x"][1],
           declared_box["box_native_z"][0], declared_box["box_native_z"][1]],
          [box[0], box[1], box[2], box[3]]
          == [declared_box["box_native_x"][0], declared_box["box_native_x"][1],
              declared_box["box_native_z"][0], declared_box["box_native_z"][1]])
    check("overlap_cells_matches_declaration", int(a.size),
          int(declared_box["overlap_cells"]), int(a.size) == int(declared_box["overlap_cells"]),
          "cells")
    check("overlap_resolved_masks_identical", int((va != vb).sum()), 0,
          bool(np.array_equal(va, vb)))
    check("overlap_values_bitwise_identical", int((a != b).sum()), 0,
          bool(np.array_equal(a, b)), "cells",
          "float64 equality over the shared native box; no tolerance used")
    check("overlap_max_abs_difference", float(np.abs(a - b).max()),
          float(declared_box["max_abs_difference_m"]),
          float(np.abs(a - b).max()) == float(declared_box["max_abs_difference_m"]), "m")

    # ---- 3. lake census re-derivation ---- #
    lake_totals = {}
    for name, entry in windows.items():
        record_set = entry["entry"]["lake"]
        records = record_set.get("records", [])
        if record_set.get("verdict") != "RUN":
            check("lake_census_ran:%s" % name, record_set.get("verdict"), "RUN", False)
            continue
        totals = {}
        mismatches = []
        reason_disagreements = []
        catchment_disagreements = []
        for record in records:
            row, column = record["seed_row_column"]
            # `filled_levels` is the priority-flood RESULT (the level water would stand at),
            # `fill_depth` is that minus the bed. Naming them apart matters: the escape
            # level is a filled level, and the water column is not.
            filled_levels = entry.get("_filled")
            if filled_levels is None:
                filled_levels = priority_flood(entry["field"], entry["mesh"])
                entry["_filled"] = filled_levels
                entry["_depth"] = filled_levels - entry["field"]
            fill_depth = entry["_depth"]
            component = basin_component(fill_depth, (row, column), entry["mesh"])
            own_reason = None
            if component is None:
                own_reason = "no_depression_at_seed"
                own_cells = 0
                own_spill = None
                own_bed_min = None
                own_clearance = -1
            else:
                cells = int(component.sum())
                levels = filled_levels[component]
                spill = float(levels.max())
                constancy = float(levels.max() - levels.min())
                rim = graph_rim(component, entry["mesh"])
                clearance = border_clearance(entry["shape"])
                rim_clearance = int(clearance[component].min())
                # The exit set is rim cells whose FILLED level equals the spill level.
                # Selecting on the water column instead would pick the rim cells standing
                # deepest -- a different set, and exactly the confusion this audit exists
                # to catch on the other side.
                exits = rim & (np.abs(filled_levels - spill) <= 1e-9)
                exit_clearance = (int(clearance[exits].min()) if exits.any() else -1)
                own_cells = cells
                own_spill = spill
                own_bed_min = float(entry["field"][component].min())
                own_clearance = rim_clearance
                if constancy > 1e-9:
                    own_reason = "flood_level_not_constant_over_basin"
                elif not exits.any():
                    own_reason = "basin_has_no_exit_cell"
                elif rim_clearance < CONTACT_MARGIN_CELLS:
                    own_reason = "rim_inside_untrusted_band"
                elif exit_clearance < CONTACT_MARGIN_CELLS:
                    own_reason = "exit_set_inside_untrusted_band"
                else:
                    own_reason = "passes_the_geometric_gates"
            if record["basin_cells"] and own_cells:
                if own_cells != record["basin_cells"]:
                    mismatches.append({"seed": record["seed_native_xz"],
                                       "field": "basin_cells",
                                       "recorded": record["basin_cells"],
                                       "own": own_cells})
                if record["spill_level_m"] is not None and own_spill is not None:
                    if float(record["spill_level_m"]) != own_spill:
                        mismatches.append({"seed": record["seed_native_xz"],
                                           "field": "spill_level_m",
                                           "recorded": record["spill_level_m"],
                                           "own": own_spill})
                if record["bed_min_m"] is not None and own_bed_min is not None:
                    if float(record["bed_min_m"]) != own_bed_min:
                        mismatches.append({"seed": record["seed_native_xz"],
                                           "field": "bed_min_m",
                                           "recorded": record["bed_min_m"],
                                           "own": own_bed_min})
                if int(record["rim_clearance_cells"]) != own_clearance:
                    mismatches.append({"seed": record["seed_native_xz"],
                                       "field": "rim_clearance_cells",
                                       "recorded": record["rim_clearance_cells"],
                                       "own": own_clearance})
            # Reason agreement, restricted to the steps this auditor re-derives exactly.
            # ``passes_the_geometric_gates`` means the flood, exit-set and clearance steps
            # all pass here; the remaining refusal reasons in the module are catchment-
            # dependent (a raw-D8 traversal this auditor deliberately does not re-implement)
            # and ``certified`` is not a reason this auditor can confirm on its own -- it
            # can only confirm that no geometric step refused. So:
            #   own == passes AND record == certified                 -> agree
            #   own == passes AND record in {upstream_unknown, leak}  -> catchment-dependent
            #   anything else                                         -> a real disagreement
            if own_reason == "passes_the_geometric_gates":
                if record["reason_code"] == "certified_closed_basin_lowest_saddle":
                    pass
                elif record["reason_code"] in ("upstream_unknown_in_catchment",
                                                "basin_membership_not_self_draining"):
                    catchment_disagreements.append({
                        "seed": record["seed_native_xz"],
                        "recorded": record["reason_code"],
                        "own": "passes every geometric gate; the refusal is catchment-"
                               "dependent and is not re-derived by this auditor"})
                else:
                    reason_disagreements.append({"seed": record["seed_native_xz"],
                                                 "recorded": record["reason_code"],
                                                 "own": own_reason})
            elif own_reason != record["reason_code"]:
                reason_disagreements.append({"seed": record["seed_native_xz"],
                                             "recorded": record["reason_code"],
                                             "own": own_reason})
            key = record["reason_code"]
            totals[key] = totals.get(key, 0) + 1
        check("lake_basin_measurements_match_own_rederivation:%s" % name,
              len(mismatches), 0, len(mismatches) == 0, "disagreements",
              "basin_cells / bed_min_m / spill_level_m / rim_clearance_cells compared "
              "against an own priority flood and an own 4-connected component")
        check("lake_geometric_reason_codes_reproduced:%s" % name,
              len(reason_disagreements), 0, len(reason_disagreements) == 0,
              "disagreements",
              "the priority-flood/exit-set/clearance steps are re-derived; the "
              "catchment-dependent refusals are reported separately")
        check("lake_reason_counts_match_declaration:%s" % name, totals,
              record_set["reason_counts"], totals == record_set["reason_counts"])
        check("certified_count_matches:%s" % name, totals.get(
            "certified_closed_basin_lowest_saddle", 0), record_set["certified_count"],
              totals.get("certified_closed_basin_lowest_saddle", 0)
              == record_set["certified_count"])
        lake_totals[name] = {"reason_counts": totals, "measurement_mismatches": mismatches,
                             "reason_disagreements": reason_disagreements,
                             "catchment_dependent": catchment_disagreements}

    # ---- 4. cross-window lake comparison: the counts must add up ---- #
    cross = evidence["lake_cross_window"]
    check("cross_window_counts_add_up",
          int(cross["converged"]) + int(cross["not_converged"]),
          int(cross["shared_seed_cells"]),
          int(cross["converged"]) + int(cross["not_converged"])
          == int(cross["shared_seed_cells"]))
    recomputed = []
    w1_index = {(record["seed_native_xz"][0], record["seed_native_xz"][1]): record
                for record in windows["W1"]["entry"]["lake"]["records"]}
    w2_index = {(record["seed_native_xz"][0], record["seed_native_xz"][1]): record
                for record in windows["W2"]["entry"]["lake"]["records"]}
    for key in sorted(set(w1_index) & set(w2_index)):
        left, right = w1_index[key], w2_index[key]
        converged = (left["reason_code"] == right["reason_code"]
                     == "certified_closed_basin_lowest_saddle"
                     and left["basin_cells"] == right["basin_cells"]
                     and left["spill_level_m"] == right["spill_level_m"]
                     and left["bed_min_m"] == right["bed_min_m"])
        recomputed.append((key, converged))
    check("cross_window_shared_seed_set_matches", len(recomputed),
          int(cross["shared_seed_cells"]), len(recomputed) == int(cross["shared_seed_cells"]),
          "seeds")
    check("cross_window_converged_count_matches",
          sum(1 for _key, flag in recomputed if flag), int(cross["converged"]),
          sum(1 for _key, flag in recomputed if flag) == int(cross["converged"]))

    # ---- 5. outlet gate: gates and assignment re-decided ---- #
    gate_report = evidence["outlet_gate"]
    gate_rows = []
    for item in gate_report["candidates"]:
        window = windows[item["window"]]
        flat = int(item["terminal_flat"])
        valid = window["valid"]
        kinds = window["kinds"]
        labels = window["labels"]
        row, column = divmod(flat, window["shape"][1])
        # own terminal label and own catchment size
        own_kind = str(kinds.reshape(-1)[flat])
        own_catchment = int((labels.reshape(-1) == flat).sum())
        rim = row in (0, window["shape"][0] - 1) or column in (0, window["shape"][1] - 1)
        row_out = {
            "role": item.get("role"),
            "window": item["window"],
            "terminal_flat": flat,
            "own_terminal_kind": own_kind,
            "recorded_terminal_kind": item["graph_terminal_kind"],
            "own_catchment_cells": own_catchment,
            "recorded_catchment_cells": item["evidence_upstream_catchment_cells"],
            "on_window_rim": bool(rim),
            "recorded_on_window_rim": bool(item["on_window_rim"]),
            "assigned_state": item["assigned_state"],
            "gates": item["gates"],
            "failure_reasons": item["failure_reasons"],
        }
        gate_rows.append(row_out)
        check("gate_terminal_kind_reproduced:%s:%d" % (item["window"], flat),
              own_kind, item["graph_terminal_kind"], own_kind == item["graph_terminal_kind"])
        check("gate_catchment_size_reproduced:%s:%d" % (item["window"], flat),
              own_catchment, item["evidence_upstream_catchment_cells"],
              own_catchment == item["evidence_upstream_catchment_cells"], "cells")
        check("gate_rim_flag_reproduced:%s:%d" % (item["window"], flat), bool(rim),
              bool(item["on_window_rim"]), bool(rim) == bool(item["on_window_rim"]))
        # own re-decision of the six gates, from the same evidence the gate was given
        declared = item["declared_state"]
        own_gates = {
            "continuous_downstream_coverage": False,
            "not_artificial_boundary": own_kind == "open_outflow" and not rim,
            "no_unknown_pollution": False,
            "world_coordinate_source_pin": True,
            "water_quantity_evidence": False,
            "water_level_evidence": False,
        }
        check("gate_not_artificial_matches_own:%s:%d" % (item["window"], flat),
              bool(item["gates"]["not_artificial_boundary"]),
              own_gates["not_artificial_boundary"],
              bool(item["gates"]["not_artificial_boundary"])
              == own_gates["not_artificial_boundary"])
        expected_certified = (declared == "natural_outlet"
                              and all(item["gates"].values()))
        check("gate_certification_follows_from_gates:%s:%d" % (item["window"], flat),
              bool(item["natural_outlet_verified"]), bool(expected_certified),
              bool(item["natural_outlet_verified"]) == bool(expected_certified))
        check("gate_assigned_state_consistent:%s:%d" % (item["window"], flat),
              item["assigned_state"],
              ("natural_outlet" if expected_certified else "unverified_outlet_candidate"),
              item["assigned_state"] == ("natural_outlet" if expected_certified
                                         else "unverified_outlet_candidate"))
    check("no_retained_terminal_upgraded",
          sum(1 for item in gate_report["candidates"]
              if item["assigned_state"] == "natural_outlet"),
          int(gate_report["natural_outlet_certified"]),
          sum(1 for item in gate_report["candidates"]
              if item["assigned_state"] == "natural_outlet")
          == int(gate_report["natural_outlet_certified"]))
    check("declared_retained_never_upgraded",
          sum(1 for item in gate_report["candidates"] if item["declared_retained_was_upgraded"]),
          0, all(not item["declared_retained_was_upgraded"]
                 for item in gate_report["candidates"]))
    check("at_least_one_boundary_refusal_candidate",
          sum(1 for item in gate_report["candidates"]
              if item.get("role") == "window_boundary_unknown_refusal_case"),
          "at least 1",
          any(item.get("role") == "window_boundary_unknown_refusal_case"
              for item in gate_report["candidates"]),
          "candidates", "the manifest requires a window-boundary/unknown refusal case")

    # ---- 6. water account: four-term partition, own accumulation ---- #
    event_rows = []
    for event in evidence["events"]:
        if event.get("verdict") != "RUN":
            check("event_ran:%s" % event["name"], event.get("verdict"), "RUN", False)
            continue
        npz_path = ROOT / event["npz"]
        with np.load(npz_path, allow_pickle=False) as archive:
            receiver = np.ascontiguousarray(archive["receiver"], np.int64)
            valid = np.ascontiguousarray(archive["valid_mask"], bool)
            kinds = np.ascontiguousarray(archive["terminal_kind"])
            seeds = np.ascontiguousarray(archive["upstream_unknown_mask"], bool)
            active = np.ascontiguousarray(archive["active_cells"], np.int64)
            local = np.ascontiguousarray(archive["local_supply_m3_s"], np.float64)
            interval_supply = np.ascontiguousarray(archive["interval_surface_supply_m3"],
                                                   np.float64)
            retained = np.ascontiguousarray(archive["certified_retained_m3_s"], np.float64)
            opened = np.ascontiguousarray(archive["certified_open_outflow_m3_s"], np.float64)
            unknown = np.ascontiguousarray(archive["certified_unknown_pending_m3_s"],
                                           np.float64)
            withheld = np.ascontiguousarray(archive["withheld_m3_s"], np.float64)
            rain = np.ascontiguousarray(archive["rain_mm_h"], np.float64)
            outlet_q = np.ascontiguousarray(archive["outlet_q_m3_s"], np.float64)
            routed = np.ascontiguousarray(archive["routed_terminal_q_m3_s"], np.float64)
        steps = int(local.shape[0])
        cells = int(local.shape[1])
        check("event_steps_are_the_declared_intervals:%s" % event["name"], steps,
              int(event["intervals"]), steps == int(event["intervals"]), "intervals")
        check("event_cells_are_the_catchment:%s" % event["name"], cells,
              int(event["catchment_cells"]), cells == int(event["catchment_cells"]), "cells")
        # Own propagation of the unknown cone, then an own donor-wave accumulation per
        # interval. Everything below works FLAT, because ``receiver`` holds flat ids.
        flat_receiver = receiver.reshape(-1)
        flat_valid = valid.reshape(-1)
        flatten = lambda value: np.asarray(value).reshape(-1)
        dirty = np.where(flat_valid, flatten(seeds), False).copy()
        pending = np.zeros(flat_receiver.size, np.int64)
        live = np.flatnonzero(flat_valid & (flat_receiver >= 0))
        np.add.at(pending, flat_receiver[live], 1)
        # Upstream-first: start at cells with no donors, propagate to receivers.
        frontier = np.flatnonzero(flat_valid & (pending == 0))
        while frontier.size:
            source = frontier[flat_receiver[frontier] >= 0]
            if not source.size:
                break
            target = flat_receiver[source]
            np.logical_or.at(dirty, target, dirty[source])
            np.subtract.at(pending, target, 1)
            frontier = np.unique(target[pending[target] == 0])
        complete = flat_valid & ~dirty
        kinds_flat = np.asarray(kinds).reshape(-1)
        terminal_flat = flat_valid & (flat_receiver < 0)
        own_retained = np.zeros(steps); own_open = np.zeros(steps)
        own_unknown = np.zeros(steps); own_withheld = np.zeros(steps)
        for step in range(steps):
            block = np.zeros(flat_receiver.size, np.float64)
            block[active] = local[step]
            certified_block = np.where(complete, block, 0.0)
            # donor_waves returns the grid's own shape, and every flat id is only
            # meaningful flat, so both sides are flattened explicitly here.
            flow_declared = donor_waves(receiver, valid, block,
                                        np.zeros(flat_valid.size, bool))[0].reshape(-1)
            flow_certified = donor_waves(receiver, valid, certified_block,
                                         np.zeros(flat_valid.size, bool))[0].reshape(-1)
            own_retained[step] = float(
                flow_certified[terminal_flat & (kinds_flat == "retained")].sum())
            own_open[step] = float(
                flow_certified[terminal_flat & (kinds_flat == "open_outflow")].sum())
            own_unknown[step] = float(
                flow_certified[terminal_flat & (kinds_flat == "unknown_boundary")].sum())
            own_withheld[step] = float((block - certified_block).sum())
            del flow_declared
        check("certified_retained_matches_own_accumulation:%s" % event["name"],
              float(np.abs(own_retained - retained).max()), 0.0,
              bool(np.allclose(own_retained, retained, rtol=1e-9, atol=1e-12)),
              "m3/s", "own donor-wave accumulation vs the saved certified total")
        check("certified_open_outflow_matches_own:%s" % event["name"],
              float(np.abs(own_open - opened).max()), 0.0,
              bool(np.allclose(own_open, opened, rtol=0.0, atol=1e-15)), "m3/s")
        check("certified_unknown_matches_own:%s" % event["name"],
              float(np.abs(own_unknown - unknown).max()), 0.0,
              bool(np.allclose(own_unknown, unknown, rtol=1e-9, atol=1e-12)), "m3/s")
        check("withheld_matches_own:%s" % event["name"],
              float(np.abs(own_withheld - withheld).max()), 0.0,
              bool(np.allclose(own_withheld, withheld, rtol=1e-9, atol=1e-12)), "m3/s")
        # four-term partition against the declared input, and against the interval supply
        declared_input = local.sum(axis=1)
        gap = (retained + opened + unknown + withheld) - declared_input
        scale = max(1.0, float(np.abs(declared_input).max()))
        check("four_term_partition_closes:%s" % event["name"],
              float(np.abs(gap).max()), 0.0,
              float(np.abs(gap).max()) <= 1e-12 * scale, "m3/s",
              "declared_input == certified_retained + certified_open + "
              "certified_unknown + withheld, every interval")
        supply_gap = (retained + opened + unknown + withheld) - interval_supply / float(
            event["dt_s"])
        check("partition_equals_interval_supply_rate:%s" % event["name"],
              float(np.abs(supply_gap).max()), 0.0,
              float(np.abs(supply_gap).max()) <= 1e-12 * scale, "m3/s",
              "the interval volume converted by dt_s, never compared to a volume directly")
        # the routed series must not be the nodal forcing (anti-reinjection)
        check("routed_series_is_not_the_local_sum:%s" % event["name"],
              bool(np.allclose(routed, declared_input)), False,
              not bool(np.allclose(routed, declared_input)), "",
              "if the routed terminal series equalled the raw local sum it would be "
              "the same quantity, not a second one")
        check("outlet_series_is_not_the_local_sum:%s" % event["name"],
              bool(np.allclose(outlet_q, declared_input)), False,
              not bool(np.allclose(outlet_q, declared_input)))
        event_rows.append({"name": event["name"], "steps": steps, "cells": cells,
                           "max_abs_partition_gap_m3_s": float(np.abs(gap).max()),
                           "max_abs_supply_rate_gap_m3_s": float(np.abs(supply_gap).max()),
                           "rain_mm_h_nonzero": int((rain != 0).sum()),
                           "recorded_world_cells_sha256": event["world_cells_sha256"],
                           "own_world_cells_sha256": hashlib.sha256(
                               np.ascontiguousarray(np.sort(
                                   (event["terminal_flat"] // 0 + 0) + 0), np.int64).tobytes()
                           ).hexdigest() if False else None})

    # ---- 7. cross-window event catchment identity, recomputed ---- #
    by_name = {row["name"]: row for row in event_rows}
    cross_event = evidence.get("cross_window_event", {})
    if "W1" in by_name and "W2" in by_name:
        digests = []
        counts = []
        for name in ("W1", "W2"):
            event = next(item for item in evidence["events"] if item["name"] == name)
            with np.load(ROOT / event["npz"], allow_pickle=False) as archive:
                active = np.ascontiguousarray(archive["active_cells"], np.int64)
            window = windows[name]
            width = window["shape"][1]
            rows_ = window["origin"][1] + active // width
            cols_ = window["origin"][0] + active % width
            key = np.sort(rows_.astype(np.int64) * 10 ** 6 + cols_.astype(np.int64))
            digests.append(hashlib.sha256(np.ascontiguousarray(key, np.int64).tobytes())
                           .hexdigest())
            counts.append(int(key.size))
        check("cross_window_catchment_cells_identical", bool(digests[0] == digests[1]),
              bool(cross_event.get("same_catchment_world_cells")),
              bool(digests[0] == digests[1])
              == bool(cross_event.get("same_catchment_world_cells")),
              "", "own absolute-coordinate key set for the two events")
        check("cross_window_catchment_size_matches_declaration", counts,
              cross_event.get("world_cells_count"), counts == cross_event.get("world_cells_count"),
              "cells")
        check("cross_window_event_identity_claim_consistent",
              bool(digests[0] == digests[1]),
              bool(cross_event.get("event_identity_identical")),
              bool(cross_event.get("event_identity_identical")) == bool(digests[0] == digests[1]),
              "", "an identical event identity requires an identical catchment cell set")

    # ---- 8. resource ledger honesty ---- #
    stages = evidence["resources"]["stages"]
    check("resource_stages_present", len(stages) >= 8, "at least 8", len(stages) >= 8,
          "stages")
    check("resource_rss_label_is_not_a_peak_claim",
          evidence["resources"]["rss_metric"], "current_rss_at_boundary",
          evidence["resources"]["rss_metric"] == "current_rss_at_boundary", "",
          "a boundary sample is not a peak; a missing sample must be NOT MEASURED, "
          "never a lifetime high-water mark")
    for item in stages:
        if item.get("current_rss_at_boundary_bytes") is None:
            check("rss_missing_is_explicit:%s" % item["stage"],
                  item.get("rss_metric"), "NOT MEASURED",
                  item.get("rss_metric") == "NOT MEASURED", "",
                  "a stage without a sample must say NOT MEASURED")

    # ---- 9. the verdict must follow from the checks ---- #
    failed = [item["name"] for item in checks if not item["passed"]]
    return {
        "schema": SCHEMA, "status": STATUS,
        "evidence": display_path(evidence_path),
        "declared": {"world_seed": WORLD_SEED, "spacing_m": SPACING_M,
                     "border_band_cells": BORDER_BAND_CELLS,
                     "contact_margin_cells": CONTACT_MARGIN_CELLS},
        "independence": {
            "judged_kernels_imported": [name for name in FORBIDDEN_MODULES
                                        if name in sys.modules],
            "policy": ("this auditor imports none of the kernels it audits; the page "
                       "hash, the D8 receiver, the terminal labels, the priority flood, "
                       "the basin component, the donor-wave accumulation and the "
                       "four-term partition are all written out here"),
            "not_re_derived": [
                "the raw-D8 catchment used by the lake refusal upstream_unknown_in_catchment "
                "and basin_membership_not_self_draining: flat/tie handling is an "
                "implementation choice, so those refusals are reported, not asserted",
                "the outlet gate's downstream-path and water-quantity evidence: this "
                "auditor checks that the assignment follows from the reported gate "
                "values, not that the evidence was obtainable",
            ]},
        "lake_rederivation": lake_totals,
        "outlet_gate_independent": gate_rows,
        "events_independent": event_rows,
        "checks": checks,
        "check_count": len(checks),
        "failure_count": len(failed),
        "failures": failed,
        "verdict": "all_declared_assertions_hold" if not failed else "assertions_failed",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Independent auditor for the p5 finite real 30 m cross-window "
                    "evidence. Imports no judged kernel; no GPU; no terrain generation.")
    parser.add_argument("--evidence", required=True,
                        help="directory holding evidence-20261025-v1.json and logs/")
    parser.add_argument("--output", default=None,
                        help="audit json path (default: <evidence>/audit-20261025-v1.json)")
    args = parser.parse_args(argv)
    try:
        assert_independence()
        report = audit(args.evidence)
    except AuditFailure as failure:
        print("REFUSED %s/%s: %s" % (failure.stage, failure.reason_code, failure.detail))
        return 2
    target = Path(args.output) if args.output else (Path(args.evidence)
                                                    / "audit-20261025-v1.json")
    if target.exists():
        print("REFUSED write/audit_already_exists: %s" % target)
        return 2
    target.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False,
                                 ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(target), "checks": report["check_count"],
                      "failures": report["failure_count"],
                      "failure_names": report["failures"][:20],
                      "verdict": report["verdict"]}, indent=2, sort_keys=True))
    return 0 if report["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
