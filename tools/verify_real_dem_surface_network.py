"""Build a review-only network from the local real DEM candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.dem_domain import prepare_dem_candidate
from terrain_pipeline.real_dem_surface_network import build_real_dem_network, validate_real_dem_network


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("D:/geography/01-完整流域样本/data/srtm_61_07.tif"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate = prepare_dem_candidate(
        args.source, (121.25, 29.15, 121.65, 29.65), target_crs="EPSG:32651",
        spacing_m=90., halo_m=900., sea_level_m=0.,
        sea_datum="unverified numeric zero; not current tidal sea level",
        source_declaration="local CIAT-CSI SRTM v4.1; elevation assumed metres; local research only",
        vertical_datum="unknown; horizontal WGS84 does not verify vertical datum",
        max_cells=500000, max_source_cells=599999)
    arrays = candidate["arrays"]
    network = build_real_dem_network(arrays["height_m"], arrays["valid_mask"])
    report = validate_real_dem_network(network, arrays["height_m"], arrays["valid_mask"])
    report.update({"source": str(args.source), "candidate_format": candidate["manifest"]["format"],
                   "shape": list(arrays["height_m"].shape),
                   "spacing_m": 90.0,
                   "network_sha256": __import__("hashlib").sha256(network.receiver.tobytes()).hexdigest()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
