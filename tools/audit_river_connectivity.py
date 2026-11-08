"""Audit flagged saved reaches without changing the input products."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.river_connectivity_audit import audit


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("product", type=Path)
    parser.add_argument("graph", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with np.load(args.product, allow_pickle=False) as p, np.load(args.graph, allow_pickle=False) as g:
        lake, ocean = p["lake_mask"], p["ocean_mask"]
        # This chain passes no additional protected or incomplete masks.
        # Boundary-inflow unknown describes hydrological support, not completeness.
        water = np.where(lake, p["elevation_m"] + p["lake_depth_m"], np.nan)
        selected = np.flatnonzero(g["reach_projection_blocked"] | g["reach_max_cut_limited"])
        reaches = audit(g, p["elevation_m"], p["bed_m"], lake=lake, ocean=ocean,
            protected=np.zeros(lake.shape, dtype=bool), unknown=p["unknown_external_inflow_mask"],
            water_surface=water, water_source="product lake elevation_m + lake_depth_m; elsewhere unknown",
            indices=selected)
        blocked, limited = g["reach_projection_blocked"], g["reach_max_cut_limited"]
        counts = {"reaches": int(len(blocked)), "projection_blocked": int(blocked.sum()),
                  "max_cut_limited": int(limited.sum()), "intersection": int((blocked & limited).sum()),
                  "union": int(len(selected))}
    for r in reaches:
        if r["crossings"]["lake"] or r["crossings"]["ocean"]:
            r["recommendation"] = "inspect protected water boundary and actual lake/ocean head; do not cut protected cells"
        elif r["resolution"] == "subgrid_width":
            r["recommendation"] = "resolve subgrid cross section and hydraulic head before considering bounded repair"
        else:
            r["recommendation"] = "evaluate bounded local repair against protection, cut budget and hydraulic head"
    result = {"schema": "river-centreline-audit-v1", "scope": "nearest-cell centreline samples, not a cross-section or hydraulic proof",
        "units": "world coordinates and elevations in metres; x east, z south; raster [z,x]",
        "unknown_semantics": "boundary external inflow influence, not incomplete terrain; additional protected mask absent in this producer",
        "sampling": "each crossed cell interior, plus endpoints; piecewise constant nearest native sample; corner-only contacts excluded",
        "water_semantics": "lake surface only where saved lake mask is true; wet_at_samples is not full cross-section or hydraulic certification",
        "sources": {str(p): sha256(p) for p in (args.product, args.graph, args.report)},
        "counts": counts, "reaches": reaches}
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps(counts))

if __name__ == "__main__":
    main()
