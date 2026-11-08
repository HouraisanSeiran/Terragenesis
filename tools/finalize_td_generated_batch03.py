"""Finalize six completed saved reports after the batch03 manifest collision."""

import json
import shutil
from pathlib import Path

from terrain_pipeline.common_infra import file_sha256, publish_bytes


def finalize():
    root = Path("verification/td-terrain-generated-rivers/generated-20261011-03")
    path = root / "manifest.json"
    startup = json.loads(path.read_text(encoding="utf-8"))
    if startup["status"] != "running" or startup["samples"]:
        raise ValueError("original running startup manifest required")
    for pin in startup["source_snapshots"]:
        if file_sha256(root / pin["path"]) != pin["sha256"]:
            raise ValueError("original startup source snapshot differs")
    samples = []
    for index in range(6):
        report_path = root / f"sample-{index}/report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report["status"] != "completed_all_selected_edges_classified":
            raise ValueError("all six actual completed sample reports required")
        for name, digest in report["algorithm_source_sha256"].items():
            pin = next(
                pin for pin in startup["source_snapshots"] if pin["source_path"] == name
            )
            if digest != pin["sha256"]:
                raise ValueError(
                    "sample source pins differ from actual startup snapshot"
                )
        samples.append(
            dict(
                sample_index=index,
                report_path=f"sample-{index}/report.json",
                report_sha256=file_sha256(report_path),
                accepted_edges=report["accepted_edges"],
                rejected_edges=report["rejected_edges"],
            )
        )
    saved_startup = root / "startup-manifest.json"
    shutil.copy2(path, saved_startup)
    failure = dict(
        status="geometry_and_six_reports_completed_final_manifest_publication_failed",
        error="FileExistsError: manifest.json; immutable publish_bytes collided with original startup manifest",
        startup_manifest_sha256=file_sha256(saved_startup),
        finalization_policy="preserve all original report and mesh bytes; finalize only manifest from six saved completed reports",
    )
    publish_bytes(
        root / "manifest-publication-failure.json",
        json.dumps(failure, indent=2).encode(),
    )
    shutil.move(str(path), str(root / "original-running-manifest.json"))
    source_report = Path(
        "verification/td-natural-river-stages/noise-holdout-20261011-01/report.json"
    )
    final = dict(
        schema="td-terrain-generated-rivers-v1",
        status="completed",
        generation_report_path=str(source_report.resolve()),
        generation_report_sha256=file_sha256(source_report),
        samples=samples,
        selection="all_six_frozen_manifest_order_no_output_filtering",
        source_snapshots=startup["source_snapshots"],
        entrypoint_sha256=file_sha256(
            root / "source-snapshots/tools/generate_td_terrain_rivers.py"
        ),
        natural_outlet_verified=False,
        hydraulic_ready=False,
        publishable=False,
        manifest_finalization=dict(
            startup_manifest_path="startup-manifest.json",
            startup_manifest_sha256=file_sha256(saved_startup),
            publication_failure_path="manifest-publication-failure.json",
            publication_failure_sha256=file_sha256(
                root / "manifest-publication-failure.json"
            ),
            finalizer_source_path="tools/finalize_td_generated_batch03.py",
            finalizer_source_sha256=file_sha256(Path(__file__)),
        ),
    )
    publish_bytes(path, json.dumps(final, indent=2, allow_nan=False).encode())
    print(json.dumps(dict(status=final["status"], samples=samples)), flush=True)


if __name__ == "__main__":
    finalize()
