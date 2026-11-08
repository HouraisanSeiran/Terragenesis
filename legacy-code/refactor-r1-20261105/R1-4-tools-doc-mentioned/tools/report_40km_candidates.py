"""Render the full candidate table for a 40 km selection run (24 rows, none omitted).

Why this is a separate tool: the requirement is that **every evaluated candidate
appears with its outcome**, so that no report can say "accepted" while the largest
basin was never measured. Printing that from the JSON by hand is exactly how a row
gets dropped, so it is generated instead.

Run:
    runtime/venv/Scripts/python.exe -B tools/report_40km_candidates.py \
        --selection .scratch/fine-terrain-40km/selection-v10/selection.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

COLUMNS = ("#", "area_km2", "cells", "bed_m", "spill_m", "measured", "window_family",
           "converged", "reason_code")


def rows(selection):
    """One row per candidate, measured or not, in the declared ranking order."""
    evaluated = list(selection.get("accepted", [])) + list(selection.get("rejected", []))
    evaluated.sort(key=lambda item: (-item["area_km2"], item["centre_rc"]))
    table = []
    for index, entry in enumerate(evaluated, 1):
        records = entry.get("convergence_records") or []
        measured = bool(records)
        family = "/".join(str(record["size"]) for record in records) if measured else "-"
        table.append({
            "#": index,
            "area_km2": round(entry["area_km2"], 4),
            "cells": entry["cells"],
            "bed_m": round(entry["bed_m"], 2),
            "spill_m": round(entry["spill_m"], 2),
            "measured": "yes" if measured else "NO",
            "window_family": family,
            "converged": ("yes" if entry.get("converged") else "no") if measured else "-",
            "reason_code": entry.get("reason_code", "accepted"),
        })
    return table


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    table = rows(selection)

    widths = {name: max(len(name), *(len(str(row[name])) for row in table))
              for name in COLUMNS} if table else {name: len(name) for name in COLUMNS}
    header = "| " + " | ".join(name.ljust(widths[name]) for name in COLUMNS) + " |"
    rule = "|" + "|".join("-" * (widths[name] + 2) for name in COLUMNS) + "|"
    lines = [header, rule]
    for row in table:
        lines.append("| " + " | ".join(str(row[name]).ljust(widths[name])
                                       for name in COLUMNS) + " |")
    text = "\n".join(lines)

    unmeasured = sum(1 for row in table if row["measured"] == "NO")
    summary = dict(status=selection.get("status"), rows=len(table),
                   measured=len(table) - unmeasured, unmeasured=unmeasured,
                   rejection_counts=selection.get("rejection_counts"))
    print(text)
    print()
    print(json.dumps(summary, indent=2))
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n\n" + json.dumps(summary, indent=2) + "\n",
                          encoding="utf-8")
    # a run that leaves any candidate unmeasured cannot be called complete
    return 0 if unmeasured == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
