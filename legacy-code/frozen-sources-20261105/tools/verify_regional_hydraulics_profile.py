"""Fixed real-state hot-path measurements without modifying production runs."""
import cProfile
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import pstats
import sys
import time

import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget, limited_inertial_fluxes, _net_flux
from terrain_pipeline.mountain_source_adapter import publish_bytes, file_sha256


def main():
    case = ROOT / "verification/regional-hydraulics/full-20261001T110401380014Z/uniform_heavy_half_cfl"
    packets = sorted(case.glob("interval-*.npz"))
    path = packets[-1]
    with np.load(case / "geometry.npz", allow_pickle=False) as archive:
        geometry = {"arrays": {key: archive[key] for key in archive.files}, "metadata": json.loads((case / "geometry.json").read_text())}
    with np.load(path, allow_pickle=False) as archive:
        packet = {key: archive[key] for key in archive.files}
    depth = packet["depth_before_m"]
    forcing = packet["forcing_volume_m3"] / 900.
    internal, boundary = packet["internal_q_before_m3_s"], packet["boundary_q_before_m3_s"]
    tailwater = geometry["arrays"]["boundary_crest_m"]
    budget = SurfaceBudget()
    profile = cProfile.Profile()
    start = time.perf_counter()
    profile.enable()
    for index in range(200):
        updated_internal, updated_boundary, stats = limited_inertial_fluxes(geometry, depth, internal, boundary, tailwater, forcing, .5, budget)
        net = _net_flux(geometry, updated_internal, updated_boundary)
        residual = 900 * (depth + .5 * (forcing + net) / 900 - depth) - .5 * (forcing + net)
    profile.disable()
    elapsed = time.perf_counter() - start
    stream = io.StringIO()
    pstats.Stats(profile, stream=stream).sort_stats("cumtime").print_stats(25)
    compression = {}
    for compressed in (False, True):
        buffer = io.BytesIO()
        start = time.perf_counter()
        (np.savez_compressed if compressed else np.savez)(buffer, **packet)
        compression[str(compressed)] = {"wall_s": time.perf_counter()-start, "bytes": buffer.tell()}
    output = ROOT / "verification/regional-hydraulics" / ("profile-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir()
    report = {"input_packet": str(path.relative_to(ROOT)), "input_sha256": file_sha256(path), "iterations": 200,
        "wall_s": elapsed, "compression": compression, "profile": stream.getvalue(), "state_max_depth_m": float(depth.max())}
    publish_bytes(output / "report.json", json.dumps(report, indent=2).encode("ascii"))
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
