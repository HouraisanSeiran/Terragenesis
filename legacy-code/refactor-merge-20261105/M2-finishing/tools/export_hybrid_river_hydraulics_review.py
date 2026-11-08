"""Export audited actual-section inventories; never fabricate continuous water."""

import argparse
import json
from pathlib import Path
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, check_memory, digest, file_sha256, read, read_audit, require)


def export(index_pin, audit_pin, output):
    index = read(index_pin)
    audit = read_audit(audit_pin)
    require(audit["schema"] == "td-hybrid-river-hydraulics-independent-audit-v1"
            and audit["status"] == "passed" and not audit["errors"]
            and audit["index_sha256"] == index_pin["sha256"] and audit["inputs"] == index["inputs"],
            "independent saved hydraulics audit must actually pass and match")
    for name, sha in audit["code_sha256"].items():
        require(file_sha256(ROOT / name) == sha, "independent audit code changed")
    geometry = read(index["inputs"]["geometry"])
    cells = geometry["hydraulic_cells"]
    centers = np.asarray([cell["section_geometry_reference"]["origin_xyz_m"] for cell in cells])
    distance = np.r_[0., np.cumsum(np.linalg.norm(np.diff(centers, axis=0), axis=1))]
    records = {}
    review = {"schema": "td-hybrid-river-hydraulics-review-v1", "inputs": index["inputs"],
              "hydraulics_index": index_pin, "independent_audit": audit_pin,
              "graph_identity_sha256": index["graph_identity_sha256"],
              "geometry_identity_sha256": index["geometry_identity_sha256"],
              "actual_hydraulic_cells": cells, "actual_hydraulic_links": geometry["hydraulic_links"],
              "station_distance_m": distance.tolist(), "scenarios": {},
              "free_surface_semantics": "discrete_1d_actual_section_stages_not_connected_3d_water_mesh",
              "pressure_semantics": "pressure_heads_above_crown_not_open_water_surfaces",
              "natural_outlet_certified": False, "full_network_verified": False,
              "three_dimensional_flow_solved": False}
    for scenario in ("pulse", "reverse_tailwater"):
        result_pin = index["artifacts"][scenario + "-refined.json"]
        result = read(result_pin)
        fields = ("times_s", "cell_ids", "water_volume_m3", "source_tracer_mass_m3", "tailwater_tracer_mass_m3",
                  "hydraulic_head_m", "open_channel_stage_m", "pressurized_head_m", "boundary_ledger_m3",
                  "ledger_columns", "paired_link_water_integral_m3", "paired_link_source_integral_m3",
                  "paired_link_tailwater_integral_m3", "parameters", "arrival_semantics", "boundary_scope")
        review["scenarios"][scenario] = {"saved_result": result_pin, **{key: result[key] for key in fields},
                                         "independent_report": audit["reports"][scenario]}
        for key in ("numerical_version", "model_version", "integration", "accuracy_policy", "accuracy_level",
                    "input_parameters_identity_sha256", "numerical_frame", "local_hydraulic_head_m",
                    "local_tailwater_head_m", "friction_policy", "jacobian_policy", "inventory_policy",
                    "saved_section_diagnostics", "instantaneous_flux_probes", "untraced_water_volume_m3",
                    "paired_link_untraced_integral_m3", "outlet_untraced_out_m3", "dense_positivity_witness"):
            if key in result:
                review["scenarios"][scenario][key] = result[key]
    review["identity_sha256"] = digest(review)
    records["review.json"] = review
    case = {"schema": "td-hybrid-river-hydraulics-caseartifact-v1", "artifact_type": "saved_1d_hydraulics_review",
            "review_identity_sha256": review["identity_sha256"], "graph_identity_sha256": index["graph_identity_sha256"],
            "geometry_identity_sha256": index["geometry_identity_sha256"], "independent_audit_passed": True,
            "hydraulics_index": index_pin, "independent_audit": audit_pin,
            "continuous_water_surface_generated": False, "natural_outlet_certified": False}
    case["identity_sha256"] = digest(case)
    records["caseartifact.json"] = case
    output = Path(output).resolve()
    require(not output.exists() and output.is_relative_to(ROOT / "verification"), "new verification review directory required")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".hydraulics-review-", dir=output.parent) as temporary:
        staging = Path(temporary) / "publish"
        staging.mkdir()
        for name, record in records.items():
            payload = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            require(len(payload) <= MAX_BYTES, "review JSON exceeds 64MiB")
            (staging / name).write_bytes(payload)
        render(review, staging)
        check_memory()
        staging.rename(output)
    return {"output": str(output), "review_identity_sha256": review["identity_sha256"], "status": "audited_saved_review"}


def render(review, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cells = review["actual_hydraulic_cells"]
    floors, crowns = [], []
    for cell in cells:
        section = cell["section"]
        shape = section.get("polygon_transverse_elevation_m", section.get("polyline_transverse_elevation_m"))
        floors.append(min(point[1] for point in shape))
        crowns.append(max(point[1] for point in shape) if cell["kind"] == "underground" else np.nan)
    distance = review["station_distance_m"]
    for scenario, result in review["scenarios"].items():
        figure, axes = plt.subplots(2, 1, figsize=(12, 8))
        axes[0].plot(distance, floors, color="#78634b", label="Actual section floor")
        axes[0].plot(distance, crowns, color="#666c68", label="Actual cave crown")
        heads = np.asarray(result["hydraulic_head_m"])
        indices = sorted({0, len(heads) // 2, len(heads) - 1})
        for ordinal, color in zip(indices, ("#3c7d8c", "#6b9242", "#bd4e50")):
            axes[0].plot(distance, heads[ordinal], color=color, marker=".", markersize=4,
                         label="Hydraulic head at " + str(result["times_s"][ordinal]) + " s")
        axes[0].set_xlabel("Section-origin route distance (m)")
        axes[0].set_ylabel("Model Y (m)")
        axes[0].ticklabel_format(style="plain", useOffset=False)
        axes[0].legend(fontsize=8)
        axes[0].grid(alpha=.2)
        times = result["times_s"]
        for key, color, label in (("water_volume_m3", "#404c52", "Stored water"),
                                  ("source_tracer_mass_m3", "#3c7d8c", "Pulse-origin water"),
                                  ("tailwater_tracer_mass_m3", "#bd4e50", "Tailwater-origin water")):
            axes[1].plot(times, np.sum(result[key], axis=1), color=color, label=label)
        axes[1].set_xlabel("Physical time (s)")
        axes[1].set_ylabel("Total inventory (m3)")
        axes[1].legend(fontsize=8)
        axes[1].grid(alpha=.2)
        figure.suptitle(scenario + " | actual VDM-section finite 1D storage\n"
                        "Above-crown heads are pressure, not free surfaces; engineering boundaries", fontsize=12)
        figure.tight_layout()
        figure.savefig(output / (scenario + ".png"), dpi=140)
        plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("index", "audit"):
        parser.add_argument("--" + key, type=Path, required=True)
        parser.add_argument("--" + key + "-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = export({"path": str(args.index.resolve()), "sha256": args.index_sha256},
                    {"path": str(args.audit.resolve()), "sha256": args.audit_sha256}, args.output)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
