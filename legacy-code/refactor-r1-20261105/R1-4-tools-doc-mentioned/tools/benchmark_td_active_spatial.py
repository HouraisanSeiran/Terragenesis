"""One independent 256-node worker; fill the missing solve/save performance evidence."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time
import numpy as np
from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.surface_rivers.metric_channel_state import (
    ChannelConfig,
    ChannelForcing,
)
from terrain_pipeline.surface_rivers.metric_channel_solver import solve_channel
from terrain_pipeline.surface_rivers.metric_channel_product import (
    make_channel_product,
    save_channel_product,
)
from terrain_pipeline.surface_rivers.metric_sediment import (
    MaterialParameters,
    SedimentConfig,
    save_sediment,
)
from terrain_pipeline.surface_rivers.metric_resolution_exchange import (
    refine_channel,
    _sediment,
)
from tools.verify_td_active_spatial import source, peak_rss_bytes


def benchmark(output):
    started = time.perf_counter()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    net, forcing, old, pin = source()
    times = np.unique(
        np.r_[forcing.time_seconds[forcing.time_seconds < 300.0], 300.0]
    ).astype(np.float64)
    rows = np.searchsorted(forcing.time_seconds, times[:-1], side="right") - 1
    truncated = ChannelForcing(
        times, forcing.local_q_m3_s[rows].copy(), forcing.source_identity_sha256
    )
    case = refine_channel("benchmark-64", net, truncated, np.full(4, 64, np.int64))
    water_config = ChannelConfig(max_dt_seconds=0.25, max_steps=10000)
    sediment_config = SedimentConfig(max_dt_seconds=0.25, max_steps=10000)
    frozen = dict(
        schema="terragenesis-spatial-single-worker-benchmark-v1",
        source=pin,
        material=old["material"],
        material_inputs=old["material_inputs"],
        node_count=256,
        horizon_seconds=300.0,
        channel_config=asdict(water_config),
        sediment_config=asdict(sediment_config),
        limits=dict(
            elapsed_seconds=180.0,
            peak_rss_bytes=1024**3,
            per_product_trace_bytes=128 * 1024**2,
        ),
        scope="one original Stage4 forcing prefix at declared300s; full solve and save; no spatial acceptance",
    )
    (output / "frozen-policy.json").write_text(
        json.dumps(frozen, indent=2) + "\n", encoding="utf-8"
    )
    water = make_channel_product(
        case.network,
        case.forcing,
        solve_channel(case.network, case.forcing, config=water_config),
    )
    mi = old["material_inputs"]
    solid = _sediment(
        case,
        water,
        MaterialParameters(**old["material"]),
        sediment_config,
        mi["initial_alluvium_depth_m"],
        mi["rock_reserve_depth_m"],
        mi["external_solid_concentration_m3_per_m3"],
    )
    wp, sp = output / "water.npz", output / "solid.npz"
    save_channel_product(wp, water)
    save_sediment(sp, solid)
    elapsed = time.perf_counter() - started
    peak = peak_rss_bytes()
    a, b = water["arrays"], solid["arrays"]
    wb = sum(x.nbytes for x in a.values())
    sb = sum(x.nbytes for x in b.values())
    complete = water["metadata"]["status"] == solid["metadata"]["status"] == "complete"
    report = dict(
        **frozen,
        elapsed_seconds=elapsed,
        peak_rss_bytes=peak,
        water_steps=len(a["trace_time_seconds"]) - 1,
        sediment_steps=len(b["step_dt_seconds"]),
        water_trace_bytes=wb,
        solid_trace_bytes=sb,
        water_status=water["metadata"]["status"],
        solid_status=solid["metadata"]["status"],
        water_pin=dict(
            path=wp.name,
            sha256=file_sha256(wp),
            identity_sha256=water["identity_sha256"],
        ),
        solid_pin=dict(
            path=sp.name,
            sha256=file_sha256(sp),
            identity_sha256=solid["identity_sha256"],
        ),
        performance_passed=complete
        and elapsed <= 180.0
        and peak <= 1024**3
        and max(wb, sb) <= 128 * 1024**2
    )
    (output / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.output), indent=2), flush=True)
