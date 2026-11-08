"""Generate all six frozen full-resolution TD river candidates."""

import argparse
import json
import shutil
from pathlib import Path

from terrain_pipeline.surface_rivers.metric_td_generated_source import (
    load_generated_td_source,
)
from terrain_pipeline.surface_rivers.metric_td_generated_rivers import (
    write_preflight,
    generate_sample,
)
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = (
    ROOT / "verification/td-natural-river-stages/noise-holdout-20261011-01/report.json"
)


def snapshot_generation_sources(output):
    names = [
        "tools/generate_td_terrain_rivers.py",
        "tools/repair_td_river_shapes.py",
        "terrain_pipeline/mountain_source_adapter.py",
        "diffusion/geographic_noise.py",
    ]
    names.extend(
        "terrain_pipeline/surface_rivers/" + name + ".py"
        for name in (
            "metric_td_generated_rivers",
            "metric_td_generated_source",
            "metric_source",
            "metric_contracts",
            "metric_drainage",
            "metric_network_geometry",
            "metric_noise_forcing",
            "metric_channel_geometry",
            "metric_valley_incision",
            "metric_valley_union",
            "metric_monotone_union",
            "metric_design_bed",
            "metric_valley_centerline",
            "metric_terrain_centerline",
            "metric_budget_centerline",
            "metric_local_budget_centerline",
            "metric_local_bed_assessment",
            "metric_local_design_bed",
            "metric_transverse_budget",
            "metric_reference_routing",
        )
    )
    records = []
    for name in names:
        source = ROOT / name
        target = output / "source-snapshots" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        digest = file_sha256(source)
        if file_sha256(target) != digest:
            raise ValueError("generation snapshot differs: " + name)
        records.append(
            dict(source_path=name, path="source-snapshots/" + name, sha256=digest)
        )
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--bounded-spills", action="store_true")
    parser.add_argument("--first-sample", action="store_true")
    args = parser.parse_args(argv)
    if args.preflight:
        report = write_preflight(
            args.output,
            load_generated_td_source(args.report, 0),
            bounded_spills=args.bounded_spills,
        )
        print(
            json.dumps(
                {
                    key: report[key]
                    for key in (
                        "selected_edges",
                        "component_count",
                        "component_edge_counts",
                        "terminal_count",
                        "terminal_kinds",
                        "maximum_terminal_catchment_m2",
                        "preflight_counts",
                    )
                }
            ),
            flush=True,
        )
    else:
        args.output.mkdir(parents=True, exist_ok=False)
        snapshots = snapshot_generation_sources(args.output)
        samples = []
        publish_bytes(
            args.output / "startup-manifest.json",
            json.dumps(
                dict(
                    schema="td-terrain-generated-rivers-v1",
                    status="running",
                    source_snapshots=snapshots,
                    samples=[],
                ),
                indent=2,
            ).encode(),
        )
        for index in range(1 if args.first_sample else 6):
            report, _ = generate_sample(
                args.output / f"sample-{index}",
                load_generated_td_source(args.report, index),
            )
            samples.append(
                dict(
                    sample_index=index,
                    report_path=f"sample-{index}/report.json",
                    report_sha256=file_sha256(
                        args.output / f"sample-{index}/report.json"
                    ),
                    accepted_edges=report["accepted_edges"],
                    rejected_edges=report["rejected_edges"],
                )
            )
        manifest = dict(
            schema="td-terrain-generated-rivers-v1",
            status="first_sample_diagnostic" if args.first_sample else "completed",
            generation_report_path=str(args.report.resolve()),
            generation_report_sha256=file_sha256(args.report),
            samples=samples,
            selection="all_six_frozen_manifest_order_no_output_filtering",
            natural_outlet_verified=False,
            hydraulic_ready=False,
            publishable=False,
            entrypoint_sha256=file_sha256(Path(__file__)),
        )
        manifest["source_snapshots"] = snapshots
        publish_bytes(
            args.output / "manifest.json",
            json.dumps(manifest, indent=2, allow_nan=False).encode(),
        )


if __name__ == "__main__":
    main()
