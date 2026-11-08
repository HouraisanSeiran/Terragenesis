"""Finite-volume transfer over an explicitly declared acyclic basin graph."""
from collections import deque
import math


def transfer_basins(basins):
    """Settle known input in topological order; unresolved sources propagate unknown.

    Each item supplies label, local_m3, capacity_m3, downstream (label or None),
    destination (lake/ocean/unknown), and complete. This is a finite-volume
    fill-and-spill approximation, not a time-resolved weir calculation.
    """
    by_label = {item["label"]: item for item in basins}
    if len(by_label) != len(basins):
        raise ValueError("duplicate basin label")
    donors = {label: 0 for label in by_label}
    for item in basins:
        for name in ("local_m3", "capacity_m3"):
            if not math.isfinite(item[name]) or item[name] < 0.:
                raise ValueError("finite nonnegative basin volume required")
        target = item["downstream"]
        if target is not None:
            if target not in by_label or target == item["label"]:
                raise ValueError("invalid basin destination")
            donors[target] += 1
    ready = deque(sorted(label for label, count in donors.items() if count == 0))
    incoming = {label: 0. for label in by_label}
    uncertain = {label: not bool(item["complete"]) for label, item in by_label.items()}
    results = {}
    while ready:
        label = ready.popleft()
        item = by_label[label]
        total = item["local_m3"] + incoming[label]
        if uncertain[label]:
            stored = spill = None
        else:
            stored = min(total, item["capacity_m3"])
            spill = total - stored
        results[label] = {"local_m3": item["local_m3"], "upstream_m3": incoming[label],
                          "inflow_m3": total, "stored_m3": stored, "outflow_m3": spill,
                          "residual_m3": None if stored is None else total - stored - spill,
                          "complete": not uncertain[label], "destination": item["destination"]}
        target = item["downstream"]
        if target is not None:
            if spill is None:
                uncertain[target] = True
            else:
                incoming[target] += spill
            donors[target] -= 1
            if donors[target] == 0:
                ready.append(target)
    for label in by_label.keys() - results.keys():
        item = by_label[label]
        results[label] = {"local_m3": item["local_m3"], "upstream_m3": incoming[label],
                          "inflow_m3": item["local_m3"] + incoming[label], "stored_m3": None,
                          "outflow_m3": None, "residual_m3": None, "complete": False,
                          "destination": item["destination"]}
    return results
