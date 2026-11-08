"""Independent audit of native 30 m outlet states; imports no judged kernel.

Independence rules, all enforced at runtime and not just by convention:

1. This process must not have imported ``natural_outlet_status`` (the gate under
   audit), nor ``native_30m_source`` (the topology being described), nor
   ``metric_network_accumulation`` (the discharge ledger). Importing this tool is
   therefore refused if any of them is already loaded -- see :func:`assert_independence`.
2. Everything below is recomputed here from the raw arrays: the shared strict graph
   receiver, the terminal labels, the catchment of a terminal, the artificial
   boundary mask, and every gate decision. Topology uses the shared graph; gate and accounting checks remain separate.
3. The only shared object is the *report format*: the auditor is handed a saved
   report as data (JSON) and re-derives its booleans, so a report whose flags were
   edited cannot pass.

Usage::

    python tools/audit_native_30m_outlets.py --report report.json \\
        --evidence arrays.npz [--json audit.json]

Exit codes: 0 audited and consistent, 1 refused or inconsistent, 2 usage.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BANNED = ("natural_outlet_status", "native_30m_source", "metric_network_accumulation",
          "metric_network_discharge_product", "natural_outlet_certification",
          "td_natural_outlet_certification")

#: Re-declared here on purpose. If the gate's list ever changes, this audit fails
#: instead of silently agreeing with it.
GATES = ("continuous_downstream_coverage",
         "not_artificial_boundary",
         "no_unknown_pollution",
         "world_coordinate_source_pin",
         "water_quantity_evidence",
         "water_level_evidence")
STATES = ("lake", "natural_outlet", "retained", "open_outflow", "unknown_boundary",
          "truncated_not_judged", "artificial_window_boundary")
CANDIDATE = "unverified_outlet_candidate"
EXPECTED_WORLD_SEED = 20261020
NATIVE_SPACING_M = 30.0


def assert_independence():
    """Refuse to run in a process that already imported a judged kernel."""
    loaded = [name for name in sys.modules
              if any(token in name for token in BANNED)]
    if loaded:
        raise SystemExit("not independent: judged modules are already imported: %s"
                         % loaded)


# --------------------------------------------------------------------------- #
# independent recomputation
# --------------------------------------------------------------------------- #
NEIGHBOURS8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def graph_receiver(height, valid, *, origin_native_xz=(0, 0), world_seed=20261020):
    """Shared graph routing, separate terminal/gate/accounting verification."""
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import masked_mesh as masked_mesh
    from terrain_pipeline.drainage import strict_receivers as strict_receivers
    mesh = grid_mesh(height.shape, x0_m=origin_native_xz[0] * 30.,
        z0_m=origin_native_xz[1] * 30., world_seed=world_seed)
    return strict_receivers(height, masked_mesh(mesh, valid), valid_mask=valid)[0].reshape(height.shape)


def independent_terminals(receiver, height, valid):
    """Terminal of every valid cell, by ascending bed height (receiver is lower)."""
    flat_receiver = np.asarray(receiver).reshape(-1)
    flat_height = np.asarray(height).reshape(-1)
    flat_valid = np.asarray(valid).reshape(-1)
    labels = np.full(flat_height.size, -1, np.int64)
    live = np.flatnonzero(flat_valid)
    for position in live[np.argsort(flat_height[live], kind="stable")]:
        downstream = int(flat_receiver[position])
        labels[position] = int(position) if downstream < 0 else labels[downstream]
    return labels.reshape(np.asarray(height).shape)


def independent_window_ring(rows, columns):
    """The declared artificial boundary of a saved run: its own window ring."""
    mask = np.zeros((rows, columns), bool)
    mask[[0, -1], :] = True
    mask[:, [0, -1]] = True
    return mask


def audit_report(report, arrays):
    """Re-derive every boolean of one saved report from the raw arrays."""
    expected_gates = set(GATES)
    if set(report.get("gates", {})) != expected_gates:
        raise ValueError("the report declares a gate set this audit does not know")
    if report.get("schema") != "native-30m-natural-outlet-status-v1":
        raise ValueError("unsupported report schema")

    receiver = np.asarray(arrays["receiver"], np.int64)
    height = np.asarray(arrays["height_m"], np.float64)
    valid = np.asarray(arrays["valid_mask"], np.bool_)
    kinds = np.asarray(arrays["terminal_kind"])
    if not (receiver.shape == height.shape == valid.shape == kinds.shape):
        raise ValueError("evidence arrays must share one shape")

    pin = report["evidence"]["source_pin"]
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    mesh = grid_mesh(height.shape, x0_m=pin["native_origin_xz"][0] * 30.,
        z0_m=pin["native_origin_xz"][1] * 30., world_seed=pin["world_seed"])
    recomputed = graph_receiver(height, valid, origin_native_xz=pin["native_origin_xz"], world_seed=pin["world_seed"])
    if not np.array_equal(recomputed, receiver):
        raise ValueError("the saved receiver is not the strict downhill irregular graph of the saved bed")
    labels = independent_terminals(receiver, height, valid)

    terminal = report["terminal_cell_id"]
    if isinstance(terminal, bool) or not isinstance(terminal, int):
        raise ValueError("terminal_cell_id must be an integer")
    if not 0 <= terminal < receiver.size:
        raise ValueError("terminal_cell_id outside the grid")
    if receiver.reshape(-1)[terminal] != -1:
        raise ValueError("the audited terminal is not a receiver exit")
    if not valid.reshape(-1)[terminal]:
        raise ValueError("the audited terminal is not a resolved cell")

    artificial = independent_window_ring(*height.shape)
    catchment = (labels.reshape(-1) == terminal) & valid.reshape(-1)
    path = [int(cell) for cell in report["evidence"]["path_cell_ids"]]
    coast = int(report["evidence"]["coastline_cell_id"])
    # The coastline is an external declaration, so the auditor must be handed it;
    # reading it out of the report would be trusting the report to certify itself.
    if "coastline_mask" not in arrays:
        raise ValueError("evidence carries no coastline_mask: an outlet claim cannot be "
                         "audited without the declared coastline")
    coastline = np.asarray(arrays["coastline_mask"], np.bool_)
    if coastline.shape != height.shape:
        raise ValueError("coastline_mask must share the graph's shape")

    # ---- 1. continuous downstream coverage --------------------------------- #
    coverage = bool(path)
    if coverage:
        coverage = (path[0] == terminal and path[-1] == coast
                    and len(set(path)) == len(path)
                    and all(0 <= cell < receiver.size for cell in path))
    if coverage and 0 <= coast < receiver.size:
        coverage = bool(coastline.reshape(-1)[coast])
    if coverage:
        coverage = all(path[index + 1] in mesh.indices[mesh.indptr[path[index]]:mesh.indptr[path[index] + 1]]
                       for index in range(len(path) - 1))
    if coverage:
        heights = [float(height.reshape(-1)[cell]) for cell in path]
        coverage = all(heights[index + 1] <= heights[index] + 1e-9
                       for index in range(len(heights) - 1))
    if coverage:
        # The path may only start inside the catchment; re-entering it would mean
        # the observed continuation doubles back into water the graph already
        # routed to this same terminal.
        coverage = not any(catchment[cell] for cell in path[1:])
    if coverage:
        coverage = bool(valid.reshape(-1)[path].all())

    # ---- 2. not an artificial boundary ------------------------------------- #
    boundary = (str(kinds.reshape(-1)[terminal]) == "open_outflow"
                and not artificial.reshape(-1)[terminal]
                and all(not artificial.reshape(-1)[cell] for cell in path)
                and 0 <= coast < receiver.size
                and not artificial.reshape(-1)[coast])

    # ---- 3. no unknown pollution ------------------------------------------ #
    # A cell is upstream-unknown when it is resolved but has an unresolved or
    # out-of-window neighbour: recomputed here from the resolved mask alone.
    from terrain_pipeline.drainage import graph_support_unknown as graph_support_unknown
    unknown = graph_support_unknown(valid, x0_m=pin["native_origin_xz"][0] * 30.,
        z0_m=pin["native_origin_xz"][1] * 30., world_seed=pin["world_seed"])
    pollution = (not unknown.reshape(-1)[catchment].any()
                 and not (coverage and any(unknown.reshape(-1)[cell] for cell in path)))

    # ---- 4. world-coordinate source pin ----------------------------------- #
    pin = report["evidence"]["source_pin"]
    origin = pin["native_origin_xz"]
    pinned = (pin["world_seed"] == EXPECTED_WORLD_SEED
              and pin["spacing_m"] == NATIVE_SPACING_M
              and isinstance(origin, list) and len(origin) == 2
              and all(isinstance(value, int) and not isinstance(value, bool)
                      for value in origin)
              and isinstance(pin["page_sha256"], list) and bool(pin["page_sha256"])
              and all(isinstance(item, str) and len(item) == 64
                      and all(c in "0123456789abcdef" for c in item)
                      for item in pin["page_sha256"])
              and pin["pinned"] is True)
    if pinned:
        row, column = divmod(terminal, height.shape[1])
        pinned = (abs(pin["outlet_world_xz_m"][0] - (origin[0] + column) * NATIVE_SPACING_M) <= 1e-9
                  and abs(pin["outlet_world_xz_m"][1] - (origin[1] + row) * NATIVE_SPACING_M) <= 1e-9)

    # ---- 5. water quantity ------------------------------------------------- #
    quantity_block = report["evidence"]["water_quantity"]
    q = quantity_block["q_m3_s"]
    quantity = (isinstance(q, (int, float)) and not isinstance(q, bool)
                and math.isfinite(q) and q > 0.0
                and isinstance(quantity_block["provenance"], str)
                and bool(quantity_block["provenance"])
                and quantity_block["independent"] is True)

    # ---- 6. water level ---------------------------------------------------- #
    level_block = report["evidence"]["water_level"]
    level = True
    sea = level_block["sea_level_m"]
    surface = level_block["water_surface_m"]
    bed = level_block["outlet_bed_m"]
    uncertainty = level_block["uncertainty_m"]
    for value in (sea, surface, bed, uncertainty):
        if not isinstance(value, (int, float)) or isinstance(value, bool) \
                or not math.isfinite(value):
            level = False
    if level:
        tolerance = uncertainty + 1e-9
        level = (uncertainty >= 0.0 and bed <= sea + tolerance
                 and surface <= sea + tolerance and bed <= surface + tolerance
                 and isinstance(level_block["datum"], str) and bool(level_block["datum"]))

    recomputed_gates = {
        "continuous_downstream_coverage": coverage,
        "not_artificial_boundary": boundary,
        "no_unknown_pollution": pollution,
        "world_coordinate_source_pin": pinned,
        "water_quantity_evidence": quantity,
        "water_level_evidence": level,
    }
    if recomputed_gates != {name: bool(value) for name, value in report["gates"].items()}:
        raise ValueError("the report's gate values disagree with an independent "
                         "recomputation: %s vs %s"
                         % (recomputed_gates, report["gates"]))

    declared = report["declared_state"]
    if declared not in STATES:
        raise ValueError("invalid declared state")
    certified = declared == "natural_outlet" and all(recomputed_gates.values())
    if report["natural_outlet_verified"] is not certified:
        raise ValueError("natural_outlet_verified does not follow from the evidence")
    if report["ocean_outlet_certified"] is not certified:
        raise ValueError("ocean_outlet_certified does not follow from the evidence")
    expected_state = ("natural_outlet" if certified
                      else (CANDIDATE if declared == "natural_outlet" else declared))
    if report["assigned_state"] != expected_state:
        raise ValueError("assigned_state %r is not derivable from the evidence "
                         "(expected %r)" % (report["assigned_state"], expected_state))
    if report["graph_terminal_kind"] != str(kinds.reshape(-1)[terminal]):
        raise ValueError("the report's graph label does not match the saved arrays")
    if report["evidence"]["upstream_catchment_cells"] != int(catchment.sum()):
        raise ValueError("the reported catchment size is not recomputable")

    return {
        "terminal_cell_id": terminal,
        "declared_state": declared,
        "assigned_state": expected_state,
        "natural_outlet_verified": certified,
        "graph_terminal_kind": str(kinds.reshape(-1)[terminal]),
        "recomputed_gates": recomputed_gates,
        "upstream_catchment_cells": int(catchment.sum()),
        "receiver_recomputed_strict_graph": True,
        "independent": True,
    }


def census(arrays):
    """A whole-window outlet census that certifies nothing.

    Answers only: how many terminals carry which graph label, how many of them sit
    on the declared window ring, and how many have a complete 8-neighbourhood. The
    split between "interior terminal" and "possible mouth" is *not* decided here.
    """
    receiver = np.asarray(arrays["receiver"], np.int64)
    valid = np.asarray(arrays["valid_mask"], np.bool_)
    kinds = np.asarray(arrays["terminal_kind"])
    artificial = independent_window_ring(*receiver.shape)
    terminal = valid & (receiver < 0)
    labels = {}
    for label in ("inactive", "interior", "retained", "open_outflow", "unknown_boundary"):
        labels[label] = int((kinds == label).sum())
    on_ring = int((terminal & artificial).sum())
    return {
        "cells": int(receiver.size),
        "resolved_cells": int(valid.sum()),
        "terminals": int(terminal.sum()),
        "terminal_on_artificial_window_boundary": on_ring,
        "terminal_labels": labels,
        "open_outflow_terminals": int((terminal & (kinds == "open_outflow")).sum()),
        "natural_outlet_certified": 0,
        "policy": "a census of labels and boundaries; it certifies nothing",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", help="saved natural-outlet status report (JSON)")
    parser.add_argument("--evidence", required=True,
                        help="npz holding receiver, height_m, valid_mask, terminal_kind")
    parser.add_argument("--json", help="optional path to write the audit result")
    arguments = parser.parse_args(argv)
    assert_independence()

    evidence_path = Path(arguments.evidence)
    if not evidence_path.is_file():
        print("evidence_missing: %s" % evidence_path, file=sys.stderr)
        return 2
    with np.load(evidence_path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    for name in ("receiver", "height_m", "valid_mask", "terminal_kind"):
        if name not in arrays:
            print("evidence_incomplete: %s" % name, file=sys.stderr)
            return 2

    window = census(arrays)
    result = {"census": window, "independence": "no judged kernel imported"}
    if arguments.report:
        report_path = Path(arguments.report)
        if not report_path.is_file():
            print("report_missing: %s" % report_path, file=sys.stderr)
            return 2
        report = json.loads(report_path.read_text(encoding="utf-8"))
        try:
            result["report"] = audit_report(report, arrays)
        except (KeyError, TypeError, ValueError) as error:
            print("audit_refused: %s" % error, file=sys.stderr)
            return 1
        result["consistent"] = True
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if arguments.json:
        Path(arguments.json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
