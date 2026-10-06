"""Plot independently audited finite morphology candidates with original bed retained."""

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
from tools.audit_td_candidate_coupling import read_record


def plot(publication_path, expected_sha256):
    publication_path = Path(publication_path).resolve(strict=True)
    if file_sha256(publication_path) != expected_sha256:
        raise ValueError("external geometry publication report pin mismatch")
    publication = json.loads(publication_path.read_text(encoding="utf-8"))
    if (publication["stage"] != "geometry_only" or publication["recoupling_required"] is not True or
            publication["selection"] != "baseline pending"):
        raise ValueError("independently audited isolated geometry publication required")
    index_record = publication["index"]
    index_path = Path(index_record["path"])
    if file_sha256(index_path) != index_record["expected_sha256"]:
        raise ValueError("audited geometry candidate manifest changed")
    manifest = json.loads(index_path.read_text(encoding="utf-8"))
    if publication["independent_morphology_audit"]["input_sha256"] != index_record["expected_sha256"]:
        raise ValueError("independent geometry audit does not bind candidate manifest")
    source, metadata = read_record(manifest["inputs"]["source_record"])
    spacing = metadata["spacing_m"]
    extent = [0, source["height_m"].shape[1] * spacing / 1000,
              source["height_m"].shape[0] * spacing / 1000, 0]
    figure, axes = plt.subplots(3, 4, figsize=(17, 12), constrained_layout=True)
    original = axes[0, 0].imshow(source["height_m"], extent=extent, interpolation="nearest", cmap="terrain")
    axes[0, 0].set(title="Original immutable TD bed (m)", xlabel="local X (km)", ylabel="local Z (km)")
    figure.colorbar(original, ax=axes[0, 0], shrink=.7)
    summaries = {}
    for row, candidate_id in enumerate(("valley_incision", "source_deposition"), start=1):
        candidate = manifest["candidates"][candidate_id]
        arrays, geometry = read_record(candidate["morphology"])
        np.testing.assert_array_equal(arrays["original_height_m"], source["height_m"])
        audit = publication["independent_morphology_audit"]["candidates"][candidate_id]
        if audit["frozen_sediment_allocation_verified"] is not True:
            raise ValueError("independent full sediment allocation audit required")
        maximum = max(1e-6, float(np.abs(arrays["height_delta_m"]).max()))
        layers = ((arrays["height_delta_m"], "Actual bed change (m)", "RdBu", -maximum, maximum),
                  (arrays["erosion_depth_m"], "Eroded depth (m)", "Oranges", 0, max(1e-6, float(arrays["erosion_depth_m"].max()))),
                  (arrays["deposit_depth_m"], "Deposited bulk depth (m)", "YlGn", 0, max(1e-6, float(arrays["deposit_depth_m"].max()))),
                  (arrays["routed_volume_m3"], "Original ordinary receiver integral (m3)", "Blues", 0, max(1e-6, float(arrays["routed_volume_m3"].max()))))
        for column, (values, title, cmap, minimum, maximum) in enumerate(layers):
            image = axes[row, column].imshow(values, extent=extent, interpolation="nearest", cmap=cmap,
                                              vmin=minimum, vmax=maximum)
            axes[row, column].set(title=f"{candidate_id}\n{title}", xlabel="local X (km)", ylabel="local Z (km)")
            figure.colorbar(image, ax=axes[row, column], shrink=.7)
        summaries[candidate_id] = dict(changed_cells=int(np.count_nonzero(arrays["height_delta_m"])),
            min_delta_m=float(arrays["height_delta_m"].min()), max_delta_m=float(arrays["height_delta_m"].max()),
            ledger=geometry["ledger"])
    axes[0, 1].axis("off")
    axes[0, 1].text(0, .95, "One finite water/material heuristic round\nOriginal saved 24 h ordinary water used\nClosed basins retained\nDerived water NOT solved\nTopology rebuild and recoupling pending\nSelection remains baseline\nNo resolved channel width or depth", va="top", fontsize=11)
    for column, candidate_id in enumerate(("valley_incision", "source_deposition"), start=2):
        ledger = summaries[candidate_id]["ledger"]
        names = ["source_solid_m3", "deposited_solid_m3", "stored_solid_m3", "exported_solid_m3"]
        axes[0, column].bar(np.arange(len(names)), [ledger[name] for name in names])
        axes[0, column].set_xticks(np.arange(len(names)), [name.replace("_solid_m3", "") for name in names], rotation=25)
        axes[0, column].set(title=f"{candidate_id} solid ledger", ylabel="solid cubic metres")
    figure.suptitle("Accepted water to derived bed candidates | Native 30 m geometry | New hydrology required")
    output = ROOT / "verification/td-accepted-water-morphology" / ("figure-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    image_path = output / "accepted-water-bed-candidates.png"
    figure.savefig(image_path, dpi=150)
    plt.close(figure)
    publish_bytes(output / "report.json", json.dumps(dict(publication=str(publication_path),
        publication_sha256=expected_sha256, index_sha256=index_record["expected_sha256"],
        image_sha256=file_sha256(image_path), candidates=summaries, water_solved=False,
        recoupling_required=True, plotter_sha256=file_sha256(__file__)), indent=2, allow_nan=False).encode("utf-8"))
    return image_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    print(plot(args.publication, args.expected_sha256))
