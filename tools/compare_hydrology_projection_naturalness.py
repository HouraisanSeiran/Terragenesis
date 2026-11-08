"""Compare explicitly supplied projections against fixed same-source slots."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

INPUT_ARRAYS = ("original_td_m", "target_height_m", "macro_height_m", "owner_domain_id",
                "ocean_mask", "terminal_mask", "core_mask", "pinned_mask")
HARMONIC_TARGET_POLICY = "harmonic-boundary-residual-v1"


def pin(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def load_projection(path, expected_sha256=None):
    path = Path(path).resolve()
    provenance = pin(path)
    if expected_sha256 is not None and provenance["sha256"] != expected_sha256:
        raise ValueError("projection archive SHA differs: " + str(path))
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"].item()))
        arrays = {key: archive[key].copy() for key in archive.files if key != "metadata_json"}
    provenance.update(identity=metadata.get("identity"), algorithm=metadata.get("algorithm"))
    return arrays, metadata, provenance


def check_same_inputs(baseline, candidate, baseline_metadata, candidate_metadata, *, target_policy=None):
    if target_policy not in (None, "legacy-residual-v1", HARMONIC_TARGET_POLICY):
        raise ValueError("unsupported explicit target_policy")
    for key in INPUT_ARRAYS:
        if key == "target_height_m" and target_policy == HARMONIC_TARGET_POLICY:
            continue
        if key not in baseline or key not in candidate or not np.array_equal(baseline[key], candidate[key]):
            raise ValueError("same-source input differs: " + key)
    # Optional sea-stencil bounds must be identical when represented by either archive.
    for key in ("ocean_stencil_mask", "lower_height_m", "upper_height_m"):
        if key in baseline or key in candidate:
            if key not in baseline or key not in candidate or not np.array_equal(baseline[key], candidate[key]):
                raise ValueError("same-source input differs: " + key)
    for key in ("config", "budget", "plan_identity", "fixed_lake_level_m", "support_origin_xz_m", "support_shape", "window"):
        if baseline_metadata.get(key) != candidate_metadata.get(key):
            raise ValueError("frozen projection recipe differs: " + key)
    if "config" not in baseline_metadata:
        raise ValueError("explicit frozen projection config required")
    shape = baseline["original_td_m"].shape
    for arrays in (baseline, candidate):
        if shape != (99, 99) or any(arrays[key].shape != shape for key in INPUT_ARRAYS):
            raise ValueError("aligned finite99 input arrays required")
        output = arrays.get("projection_height_m")
        if output is None or output.shape != shape or not np.isfinite(output).all():
            raise ValueError("finite aligned projection output required")
        if not np.isfinite(arrays["target_height_m"]).all():
            raise ValueError("finite aligned target required")


def metrics(raw, output, spacing_m=30.):
    delta = output - raw
    gradients = [np.stack(np.gradient(field, spacing_m)) for field in (raw, output)]
    laps = [field[1:-1, :-2] + field[1:-1, 2:] + field[:-2, 1:-1] + field[2:, 1:-1] - 4 * field[1:-1, 1:-1]
            for field in (raw, output)]
    norms = [np.linalg.norm(gradient, axis=0) for gradient in gradients]
    denominator = norms[0] * norms[1]
    defined = denominator > 0
    cosine = np.sum(gradients[0] * gradients[1], axis=0)[defined] / denominator[defined]
    correlation = float(np.corrcoef(laps[0].ravel(), laps[1].ravel())[0, 1]) if all(np.std(lap) > 0 for lap in laps) else None
    return {"height_absolute_change_quantiles_m": dict(zip(("p50", "p95", "max"), np.quantile(np.abs(delta), [.5, .95, 1]).tolist())),
        "signed_mean_change_m": float(delta.mean()), "raise_volume_m3": float(np.maximum(delta, 0).sum() * spacing_m**2),
        "lower_volume_m3": float(np.maximum(-delta, 0).sum() * spacing_m**2),
        "source_slope_quantiles_m_per_m": np.quantile(norms[0], [.1, .5, .9]).tolist(),
        "output_slope_quantiles_m_per_m": np.quantile(norms[1], [.1, .5, .9]).tolist(),
        "gradient_direction_cosine_median": float(np.median(cosine)) if cosine.size else None,
        "gradient_direction_undefined_count": int((~defined).sum()),
        "laplacian_rms_source_m": float(np.sqrt(np.mean(laps[0]**2))),
        "laplacian_rms_output_m": float(np.sqrt(np.mean(laps[1]**2))), "laplacian_correlation": correlation,
        "source_axis_gradient_energy": {"x": float(np.sum(gradients[0][1]**2)), "z": float(np.sum(gradients[0][0]**2))},
        "output_axis_gradient_energy": {"x": float(np.sum(gradients[1][1]**2)), "z": float(np.sum(gradients[1][0]**2))},
        "route_metrics": {"status": "centerline_not_changed", "reason": "projection does not define a new represented river centerline"}}


def fixed_hillshade(field, spacing_m=30.):
    """Physical normal/light cosine, without per-image contrast stretching."""
    dz, dx = np.gradient(field, spacing_m)
    normal = np.stack((-dx, -dz, np.ones_like(field)), axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    # Raster z increases southward, so the NW light has negative x and z.
    light = np.array([-.5, -.5, np.sqrt(.5)])
    return np.clip(normal @ light, 0., 1.)


def render(path, baseline, candidate, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    inner = np.s_[1:-1, 1:-1]
    raw, target, old, new = [array[inner] for array in (baseline["original_td_m"], baseline["target_height_m"],
        baseline["projection_height_m"], candidate["projection_height_m"])]
    candidate_target = candidate["target_height_m"][inner]
    target_changed = not np.array_equal(target, candidate_target)
    fields = (raw, target, old, new, candidate_target) if target_changed else (raw, target, old, new)
    labels = ("Original TD", "Frozen target", "Baseline projection", "Candidate projection", "Candidate target")
    fig, axes = plt.subplots(2, len(fields), figsize=(4.25 * len(fields), 8), constrained_layout=True)
    low, high = min(field.min() for field in fields), max(field.max() for field in fields)
    for ax, field, label in zip(axes[0], fields, labels):
        im = ax.imshow(field, cmap="terrain", vmin=low, vmax=high, origin="upper", extent=(0, 2880, 2880, 0))
        ax.set_title(label)
    fig.colorbar(im, ax=list(axes[0]), label="Elevation (m)", shrink=.8)
    deltas = (old - raw, new - raw, new - old)
    bound = max(max(float(np.abs(field).max()) for field in deltas + ((candidate_target - target,) if target_changed else ())), 1e-12)
    for ax, field, label in zip(axes[1, :3], deltas, ("Baseline - source", "Candidate - source", "Candidate - baseline")):
        im = ax.imshow(field, cmap="RdBu_r", vmin=-bound, vmax=bound, origin="upper", extent=(0, 2880, 2880, 0))
        ax.set_title(label)
    fig.colorbar(im, ax=list(axes[1, :3]), label="Change (m)", shrink=.8)
    for field, label in ((raw, "Source"), (old, "Baseline"), (new, "Candidate")):
        axes[1, 3].plot(np.arange(97) * 30, field[48], label=label)
    axes[1, 3].set(title="Same central world row", xlabel="Relative x (m)", ylabel="Elevation (m)")
    axes[1, 3].legend()
    if target_changed:
        axes[1, 4].imshow(candidate_target - target, cmap="RdBu_r", vmin=-bound, vmax=bound,
                          origin="upper", extent=(0, 2880, 2880, 0))
        axes[1, 4].set_title("Candidate - frozen target")
    for ax in list(axes[0]) + list(axes[1, :3]) + (list(axes[1, 4:]) if target_changed else []):
        ax.set(xlabel="Relative x east (m)", ylabel="Relative z south (m)")
    fig.suptitle(title)
    fig.savefig(path, dpi=140)
    plt.close(fig)
    # Same physical light and vertical scale for all three surfaces, north up.
    fig, axes = plt.subplots(2, 3, figsize=(13, 8.4), constrained_layout=True)
    slopes = [np.linalg.norm(np.stack(np.gradient(field, 30.)), axis=0) for field in (raw, old, new)]
    slope_high = max(max(float(slope.max()) for slope in slopes), 1e-12)
    for ax, field, label in zip(axes[0], (raw, old, new), ("Original TD", "Baseline projection", "Candidate projection")):
        ax.imshow(fixed_hillshade(field), cmap="gray", vmin=0, vmax=1, origin="upper", extent=(0, 2880, 2880, 0))
        ax.set(title=label, xlabel="Relative x east (m)", ylabel="Relative z south (m)")
    for ax, slope, label in zip(axes[1], slopes, ("Original TD slope", "Baseline slope", "Candidate slope")):
        im = ax.imshow(slope, cmap="magma", vmin=0, vmax=slope_high, origin="upper", extent=(0, 2880, 2880, 0))
        ax.set(title=label, xlabel="Relative x east (m)", ylabel="Relative z south (m)")
    fig.colorbar(im, ax=list(axes[1]), label="Slope (m/m)", shrink=.8)
    fig.suptitle(title + " / fixed light NW315, altitude45 / vertical scale1")
    fig.savefig(path.with_name(path.stem + "-hillshade.png"), dpi=140)
    plt.close(fig)


def compare(summary_path, candidate_reports, output):
    summary_path, output = Path(summary_path).resolve(), Path(output).resolve()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    slots = {(record["seed"], record["kind"]): record for record in summary["records"]}
    if summary.get("fixed_denominator") != 12 or len(slots) != 12:
        raise ValueError("fixed twelve-slot production summary required")
    candidates, report_pins = {}, []
    for report_path in candidate_reports:
        report_path = Path(report_path).resolve()
        report_pins.append(pin(report_path))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for record in report.get("records", report.get("reports", [report])):
            key = record["seed"], record.get("kind", record.get("window_kind"))
            if key not in slots or key in candidates:
                raise ValueError("unknown or duplicate candidate slot: " + str(key))
            candidates[key] = record
    prepared = {}
    # Validate every pair before publishing figures or a summary.
    for key, candidate_record in candidates.items():
        if not candidate_record.get("projection_path"):
            prepared[key] = (candidate_record, None)
            continue
        artifacts = slots[key].get("projection", {}).get("artifacts", [])
        if not artifacts:
            raise ValueError("candidate slot has no saved baseline projection: " + str(key))
        parent = artifacts[0]
        if candidate_record.get("baseline_projection_path") and Path(candidate_record["baseline_projection_path"]).resolve() != Path(parent["path"]).resolve():
            raise ValueError("candidate report names a different baseline projection")
        if candidate_record.get("baseline_projection_sha256", parent["sha256"]) != parent["sha256"]:
            raise ValueError("candidate report baseline SHA differs")
        baseline, bm, bp = load_projection(parent["path"], parent["sha256"])
        candidate, cm, cp = load_projection(candidate_record["projection_path"], candidate_record.get("projection_sha256"))
        check_same_inputs(baseline, candidate, bm, cm, target_policy=candidate_record.get("target_policy"))
        if candidate_record.get("target_policy") is not None and cm.get("target_policy", "legacy-residual-v1") != candidate_record["target_policy"]:
            raise ValueError("candidate report/archive target_policy differs")
        if candidate_record.get("cold_audit_path"):
            pin(candidate_record["cold_audit_path"])
            audit = json.loads(Path(candidate_record["cold_audit_path"]).read_text(encoding="utf-8"))
            if audit.get("projection_sha256") != cp["sha256"]:
                raise ValueError("candidate cold audit projection SHA differs")
            if not isinstance(audit.get("status"), str):
                raise ValueError("candidate cold audit status required")
        prepared[key] = (candidate_record, (baseline, candidate, bp, cp))
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for key, slot in slots.items():
        record = {"seed": key[0], "kind": key[1], "status": "not_run", "baseline_production_status": slot["status"],
                  "naturalness_certified": False, "bed_certification_inherited": False, "lake_certification_inherited": False}
        if key in prepared:
            declared, pair = prepared[key]
            record["candidate_status"] = declared.get("status")
            if pair is None:
                record.update(status="candidate_not_produced", reason=declared.get("reason"))
            else:
                baseline, candidate, bp, cp = pair
                inner = np.s_[1:-1, 1:-1]
                figure = output / ("seed" + str(key[0]) + "-" + key[1] + ".png")
                render(figure, baseline, candidate, "Seed " + str(key[0]) + " / " + key[1] + " / same-source projection comparison")
                target_changed = not np.array_equal(baseline["target_height_m"], candidate["target_height_m"])
                record.update(status="compared_same_source", inputs_equal=not target_changed,
                    target_changed=target_changed, target_policy=declared.get("target_policy"),
                    equal_input_arrays=[key for key in INPUT_ARRAYS if not (target_changed and key == "target_height_m")], baseline=bp, candidate=cp,
                    before=metrics(baseline["original_td_m"][inner], baseline["projection_height_m"][inner]),
                    after=metrics(candidate["original_td_m"][inner], candidate["projection_height_m"][inner]), figure=pin(figure),
                    visual_review_status="pending")
                hillshade = figure.with_name(figure.stem + "-hillshade.png")
                if hillshade.exists():
                    record["hillshade_figure"] = pin(hillshade)
                if declared.get("cold_audit_path"):
                    audit = json.loads(Path(declared["cold_audit_path"]).read_text(encoding="utf-8"))
                    record["candidate_cold_audit"] = {**pin(declared["cold_audit_path"]), "status": audit["status"],
                                                     "checks": audit}
        records.append(record)
    result = {"schema": "hydrology-projection-naturalness-comparison-v1", "fixed_denominator": 12, "records": records,
        "parent_summary": pin(summary_path), "candidate_reports": report_pins, "naturalness_certified": False,
        "threshold_policy": "descriptive same-source measurements only; no naturalness acceptance thresholds",
        "comparison_scope": "original97 equal world pixels; finite99 computational halo excluded", "model_inference_run": False,
        "projection_solver_run": False, "bed_or_lake_certification_transferred": False}
    with (output / "comparison.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-summary", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from tools.prepare_hydrology_v5_lake import limit_resources
    limit_resources()
    result = compare(args.production_summary, args.candidate_report, args.output)
    print(json.dumps({"compared": sum(record["status"] == "compared_same_source" for record in result["records"]),
                      "fixed_denominator": 12, "path": str(args.output / "comparison.json")}))


if __name__ == "__main__":
    main()
