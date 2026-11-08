"""Draw saved joined fine bed and incisions without interpolating water."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_native_channel_tiles import assemble


def plot(report_path, report_sha256):
    if file_sha256(report_path) != report_sha256:
        raise ValueError("external tile report pin mismatch")
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    grids, metadata, bounds, shared = assemble(report["tiles"], report["geometry"]["expected_identity"])
    spacing = metadata["recipe"]["sample_spacing_m"]
    local_x, local_z = np.meshgrid(np.arange(grids["candidate_bed_m"].shape[1]) * spacing,
                                  np.arange(grids["candidate_bed_m"].shape[0]) * spacing)
    figure = plt.figure(figsize=(16, 6), constrained_layout=True)
    planar = figure.add_subplot(131)
    image = planar.imshow(grids["candidate_cut_m"], extent=(local_x.min(), local_x.max(), local_z.max(), local_z.min()), cmap="magma")
    planar.set(title="Saved bounded channel incision", xlabel="local X (m)", ylabel="local Z (m)")
    figure.colorbar(image, ax=planar, label="cut (m)", shrink=.6)
    planar.axvline((bounds[1] - bounds[0]) * spacing / 2, color="cyan", linewidth=.6)
    planar.axhline((bounds[3] - bounds[2]) * spacing / 2, color="cyan", linewidth=.6)
    spatial = figure.add_subplot(132, projection="3d")
    spatial.plot_surface(local_x, local_z, grids["candidate_bed_m"], cmap="terrain", rcount=128, ccount=128, linewidth=0)
    spatial.set(title="Continuous candidate bed expression", xlabel="local X (m)", ylabel="local Z (m)", zlabel="elevation (m)")
    incision = figure.add_subplot(133, projection="3d")
    incision.plot_surface(local_x, local_z, -grids["candidate_cut_m"], cmap="magma_r", rcount=128, ccount=128, linewidth=0)
    incision.set(title="Isolated incision geometry", xlabel="local X (m)", ylabel="local Z (m)", zlabel="bed change (m)")
    figure.suptitle(f"TD {local_x.max():g}m window | {spacing:g}m sampling | four shared tiles | candidate bed only; water unsolved")
    directory = ROOT / "verification/td-native-channel-tiles" / ("independent-figure-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "fine-channel-bed.png"
    figure.savefig(path, dpi=160)
    plt.close(figure)
    result = dict(schema="td-native-channel-tile-figure-v1", source_report=str(Path(report_path).resolve()),
                  source_report_sha256=report_sha256, figure_path=str(path), figure_sha256=file_sha256(path),
                  window=bounds, display_surface_max_axis_samples=128, source_samples_unchanged=True,
                  water_drawn=False, physical_fine_solver_run=False, shared_sample_checks=shared)
    if file_sha256(report_path) != report_sha256:
        raise ValueError("source report changed")
    publish_bytes(directory / "report.json", json.dumps(result, indent=2, allow_nan=False).encode("utf-8"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    arguments = parser.parse_args()
    print(json.dumps(plot(arguments.report, arguments.report_sha256), ensure_ascii=True))


if __name__ == "__main__":
    main()
