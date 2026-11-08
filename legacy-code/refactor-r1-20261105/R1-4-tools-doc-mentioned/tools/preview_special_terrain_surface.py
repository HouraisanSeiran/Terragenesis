"""Reproducible offline preview of the v2 facet-noise + hydraulic-dissection surfaces.

Reads the candidate surface bundles written by
``tools/prepare_special_terrain_surface.py`` together with their parent bundles, then
re-derives every plotted scale from the geometry arrays and asserts the derived numbers
against both manifests *before* any figure is drawn.  A mismatch raises instead of
emitting a pretty picture.

The point of the preview is the three-stage read: the parent chart (smooth analytic
bump), the same chart after facet noise, and the same chart after hydraulic dissection.
Every panel of one kind shares one colour range so the three stages are comparable.

Output is a scratch preview directory: never a source cache, never ``verification/``.
The base bed is synthetic analytic geometry, so nothing here claims real Terrain
Diffusion detail and no figure is a certification.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.metric_special_terrain_forms import KINDS
from terrain_pipeline.metric_special_terrain_surface import (
    ALGORITHM, SCHEMA, load_special_form_surface,
)
from terrain_pipeline.metric_special_terrain_forms import load_special_form_vdm
from terrain_pipeline.mountain_source_adapter import identity


DEFAULT_BUNDLES = Path(".scratch/special-terrain/surface-20261020")
DEFAULT_PARENTS = Path(".scratch/special-terrain/bundles-20261019")
DEFAULT_OUTPUT = Path(".scratch/special-terrain/surface-preview-20261020")
PNG_META = {"Software": "preview_special_terrain_surface"}
VERIFICATION_DIRECTORY = "verification"
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable",
         "self_intersection_verified")
STAGES = (("parent chart", "parent"), ("facet noise", "roughened"),
          ("hydraulic dissection", "dissected"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b""):
            digest.update(block)
    return digest.hexdigest()


def guard_output(output):
    """Refuse to write anywhere near a source cache or the verification tree."""
    parts = [part.lower() for part in Path(output).resolve().parts]
    require(VERIFICATION_DIRECTORY not in parts,
            f"refusing to write previews under {VERIFICATION_DIRECTORY}/: {output}")
    return Path(output)


def load_manifest(bundles, schema, algorithm, label):
    path = Path(bundles) / "manifest-report.json"
    require(path.is_file(), f"missing {label} manifest: {path}")
    record = json.loads(path.read_text(encoding="utf-8"))
    require(record.get("schema") == schema and record.get("algorithm") == algorithm,
            f"{label} manifest identity mismatch")
    require(record.get("status") == "candidate", f"preview only accepts candidate {label}")
    return record


def chart_extent(reference):
    return (float(reference[0, 0, 0]), float(reference[0, -1, 0]),
            float(reference[0, 0, 2]), float(reference[-1, 0, 2]))


def measure(kind, result, entry, bundle_path, parent, parent_entry, parent_path):
    """Re-derive the geometry numbers and cross-check them against both manifests."""
    arrays, metadata = result["arrays"], result["metadata"]
    parent_arrays = parent["arrays"]
    reference = arrays["reference_xyz_m"]
    rows, cols = reference.shape[:2]
    require((rows, cols) == (int(entry["chart_rows"]), int(entry["chart_cols"])),
            f"{kind}: chart shape {rows}x{cols} disagrees with the manifest")
    require(np.array_equal(reference, parent_arrays["reference_xyz_m"]),
            f"{kind}: surface chart is not the parent chart")
    spacing_x = float(reference[0, 1, 0] - reference[0, 0, 0])
    spacing_z = float(reference[1, 0, 2] - reference[0, 0, 2])
    require(abs(spacing_x - spacing_z) <= 1e-9 * max(spacing_x, spacing_z),
            f"{kind}: non-uniform chart spacing")
    spacing_m = 0.5 * (spacing_x + spacing_z)
    require(abs(spacing_m - float(entry["spacing_m"])) <= 1e-9 * max(1.0, float(entry["spacing_m"])),
            f"{kind}: spacing disagrees with the manifest")
    require(sha256_file(bundle_path) == entry["sha256"],
            f"{kind}: surface bundle bytes disagree with the manifest")
    require(sha256_file(parent_path) == parent_entry["sha256"],
            f"{kind}: parent bundle bytes disagree with the parent manifest")
    require(metadata["parent_identity_sha256"] == parent["identity_sha256"] ==
            parent_entry["identity_sha256"], f"{kind}: parent identity chain is broken")
    require(identity(arrays, metadata) == result["identity_sha256"] == entry["identity_sha256"],
            f"{kind}: recomputed identity disagrees with the bundle or the manifest")
    for flag in FLAGS:
        require(metadata[flag] is False, f"{kind}: status flag {flag} is not False")

    parent_relief = float(np.max(parent_arrays["displacement_xyz_m"][:, :, 1]))
    roughened_relief = float(np.max(arrays["displacement_xyz_m"][:, :, 1]))
    require(parent_relief == float(parent_entry["max_relief_m"]),
            f"{kind}: parent relief disagrees with the parent manifest")
    require(metadata["relief_reference_m"] == parent_relief and
            metadata["roughened_relief_reference_m"] == roughened_relief,
            f"{kind}: declared relief references disagree with the arrays")
    change = arrays["erosion_change_m"]
    collar = float(max(np.max(np.abs(arrays["displacement_xyz_m"][0, :, 1])),
                       np.max(np.abs(arrays["displacement_xyz_m"][-1, :, 1])),
                       np.max(np.abs(arrays["displacement_xyz_m"][:, 0, 1])),
                       np.max(np.abs(arrays["displacement_xyz_m"][:, -1, 1])),
                       np.max(np.abs(change[0])), np.max(np.abs(change[-1])),
                       np.max(np.abs(change[:, 0])), np.max(np.abs(change[:, -1]))))
    require(collar == 0.0, f"{kind}: chart collar carries {collar}, expected exactly 0")
    ledger = metadata["ledger"]
    require(float(np.sum(change) * spacing_m ** 2) == ledger["net_change_ledger_m3"],
            f"{kind}: net change ledger disagrees with the stored change")
    # Mirror the auditor's self-consistency rule before drawing anything: the reported
    # convergence flag must be exactly what the per-step excesses imply, so a figure can
    # never illustrate a state the ledger contradicts.
    relaxation = metadata["dissection_recipe"]
    require(all(bool(step["relaxation_converged"]) ==
                (step["relaxation_maximum_excess_m"] <= relaxation["tolerance_m"])
                for step in ledger["steps"]),
            f"{kind}: a relaxation flag disagrees with its own recorded excess")
    require(ledger["relaxation_converged"] is
            all(step["relaxation_maximum_excess_m"] <= relaxation["tolerance_m"]
                for step in ledger["steps"]),
            f"{kind}: relaxation summary flag disagrees with the per-step excess")
    return {"kind": kind, "file": Path(bundle_path).name, "sha256": entry["sha256"],
            "identity_sha256": result["identity_sha256"],
            "parent_file": Path(parent_path).name, "parent_sha256": parent_entry["sha256"],
            "parent_identity_sha256": parent["identity_sha256"],
            "chart_rows": rows, "chart_cols": cols, "spacing_m": spacing_m,
            "parent_relief_m": parent_relief, "roughened_relief_m": roughened_relief,
            "collar_max_abs_m": collar,
            "maximum_incision_m": ledger["maximum_incision_m"],
            "maximum_deposition_m": ledger["maximum_deposition_m"],
            "incised_cells": ledger["incised_cells"], "deposited_cells": ledger["deposited_cells"],
            "detachment_ledger_m3": ledger["detachment_ledger_m3"],
            "transport_deposition_ledger_m3": ledger["transport_deposition_ledger_m3"],
            "relaxation_transferred_ledger_m3": ledger["relaxation_transferred_ledger_m3"],
            "net_change_ledger_m3": ledger["net_change_ledger_m3"],
            "relaxation_converged": ledger["relaxation_converged"],
            "relaxation_tolerance_m": ledger["relaxation_tolerance_m"],
            "relaxation_maximum_excess_m": ledger["relaxation_maximum_excess_m"],
            "relaxation_sweeps_max": ledger["relaxation_sweeps_max"],
            "facet_recipe": metadata["facet_recipe"],
            "facet_wavelengths_m": metadata["facet_wavelengths_m"],
            "dissection_recipe": metadata["dissection_recipe"]}


def plot_three_stage(kind, reference, stages, output, *, label):
    """One figure, three plan panels, one shared colour range for honest comparison."""
    x0, x1, z0, z1 = chart_extent(reference)
    extent = (x0, x1, z0, z1)
    vmin = float(min(field.min() for field in stages.values()))
    vmax = float(max(field.max() for field in stages.values()))
    fig, axes = plt.subplots(1, len(STAGES), figsize=(6.4 * len(STAGES), 6.0), dpi=130)
    panels = {}
    for axis, (title, key) in zip(axes, STAGES):
        field = stages[key]
        image = axis.imshow(field, origin="lower", extent=extent, cmap="terrain",
                            vmin=vmin, vmax=vmax, aspect="equal")
        axis.contour(np.linspace(x0, x1, field.shape[1]), np.linspace(z0, z1, field.shape[0]),
                     field, levels=np.linspace(vmin, vmax, 11)[1:-1], colors="#101010",
                     linewidths=.4, alpha=.65)
        axis.set_title(f"{title}\nmax {field.max():.3f} m | min {field.min():.3f} m", fontsize=9)
        axis.set_xlabel("x (m)")
        panels[key] = {"title": title, "max_m": float(field.max()), "min_m": float(field.min())}
    axes[0].set_ylabel("z (m)")
    bar = fig.colorbar(image, ax=axes, shrink=.78, pad=.02)
    bar.set_label("elevation (m)")
    fig.suptitle(f"{label}: {kind}, shared colour range {vmin:.3f} .. {vmax:.3f} m", fontsize=11)
    path = output / f"{kind}-a-three-stage-plan.png"
    fig.savefig(path, metadata=PNG_META, bbox_inches="tight")
    plt.close(fig)
    return {"file": path.name, "sha256": sha256_file(path), "extent_m": list(extent),
            "colorbar_vmin_m": vmin, "colorbar_vmax_m": vmax, "panels": panels}


def plot_profile(kind, reference, stages, floor, output, *, label):
    """Cross-section through the row of maximum roughened relief, all three stages."""
    rows = np.max(np.abs(stages["roughened"] - stages["parent"]), axis=1)
    row = int(np.argmax(rows))
    x = reference[0, :, 0]
    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=130)
    colors = {"parent": "#555555", "roughened": "#c9a227", "dissected": "#1f6f3f"}
    for title, key in STAGES:
        ax.plot(x, stages[key][row], color=colors[key], lw=1.3, label=f"{title} ({key})")
    ax.plot(x, floor[row], color="#8b1a1a", lw=1.0, ls="--", label="recomputed rock floor")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("elevation (m)")
    ax.set_title(f"{label}: {kind}, profile along z = {float(reference[row, 0, 2]):.1f} m "
                 "(row of maximum facet amplitude)", fontsize=10)
    ax.grid(alpha=.25, lw=.5)
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = output / f"{kind}-b-profile.png"
    fig.savefig(path, metadata=PNG_META)
    plt.close(fig)
    return {"file": path.name, "sha256": sha256_file(path), "profile_row": row,
            "profile_z_m": float(reference[row, 0, 2]),
            "parent_max_m": float(stages["parent"][row].max()),
            "roughened_max_m": float(stages["roughened"][row].max()),
            "dissected_max_m": float(stages["dissected"][row].max()),
            "floor_margin_min_m": float(np.min(stages["dissected"][row] - floor[row]))}


def plot_change(kind, reference, change, output, *, label):
    """Diverging map of the dissection change, symmetric about zero by construction."""
    x0, x1, z0, z1 = chart_extent(reference)
    limit = float(np.max(np.abs(change)))
    require(limit > 0.0, f"{kind}: dissection change is identically zero")
    fig, ax = plt.subplots(figsize=(9.2, 7.4), dpi=130)
    image = ax.imshow(change, origin="lower", extent=(x0, x1, z0, z1), cmap="RdBu",
                      vmin=-limit, vmax=limit, aspect="equal")
    bar = fig.colorbar(image, ax=ax, shrink=.85)
    bar.set_label("bed change (m), negative = incision")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("z (m)")
    ax.set_title(f"{label}: {kind}, hydraulic dissection change "
                 f"(-{float(np.min(change)):.3f} .. +{float(np.max(change)):.3f} m)", fontsize=10)
    fig.tight_layout()
    path = output / f"{kind}-c-change.png"
    fig.savefig(path, metadata=PNG_META)
    plt.close(fig)
    return {"file": path.name, "sha256": sha256_file(path),
            "extent_m": [x0, x1, z0, z1], "colorbar_vmin_m": -limit, "colorbar_vmax_m": limit,
            "incision_min_m": float(np.min(change)), "deposition_max_m": float(np.max(change))}


def preview_kind(kind, bundles, parents, entries, parent_entries, output):
    entry, parent_entry = entries[kind], parent_entries[kind]
    bundle_path = Path(bundles) / entry["file"]
    parent_path = Path(parents) / parent_entry["file"]
    result = load_special_form_surface(bundle_path, expected_sha256=entry["sha256"],
                                       expected_identity=entry["identity_sha256"])
    parent = load_special_form_vdm(parent_path, expected_sha256=parent_entry["sha256"],
                                   expected_identity=parent_entry["identity_sha256"])
    record = measure(kind, result, entry, bundle_path, parent, parent_entry, parent_path)
    arrays, metadata = result["arrays"], result["metadata"]
    reference = arrays["reference_xyz_m"]
    spacing = float(reference[0, 1, 0] - reference[0, 0, 0])
    # The rock floor is recomputed here from the stored arrays and the declared fraction;
    # the figure must not plot a bound it cannot derive.
    roughened = reference[:, :, 1] + arrays["displacement_xyz_m"][:, :, 1]
    depth = metadata["dissection_recipe"]["maximum_incision_fraction"] * \
        metadata["roughened_relief_reference_m"]
    floor = np.minimum(np.maximum(roughened - depth, reference[:, :, 1]), roughened)
    final = arrays["surface_xyz_m"][:, :, 1]
    require(float(np.min(final - floor)) >= -1e-9,
            f"{kind}: profile would plot a bed below its recomputed floor")
    stages = {"parent": reference[:, :, 1] + parent["arrays"]["displacement_xyz_m"][:, :, 1],
              "roughened": roughened, "dissected": final}
    label = f"candidate, {spacing:g} m cells"
    panels = {"three_stage_plan": plot_three_stage(kind, reference, stages, output, label=label),
              "profile": plot_profile(kind, reference, stages, floor, output, label=label),
              "change": plot_change(kind, reference, arrays["erosion_change_m"], output, label=label)}
    x0, x1, z0, z1 = panels["three_stage_plan"]["extent_m"]
    require(abs((x1 - x0) - (record["chart_cols"] - 1) * record["spacing_m"]) <= 1e-9 * max(1.0, x1 - x0),
            f"{kind}: plan extent disagrees with shape x spacing")
    require(abs((z1 - z0) - (record["chart_rows"] - 1) * record["spacing_m"]) <= 1e-9 * max(1.0, z1 - z0),
            f"{kind}: plan extent disagrees with shape x spacing")
    # The plotted stages must be exactly the stored arrays, not a re-derived approximation.
    plotted = panels["three_stage_plan"]["panels"]
    for key, field in (("parent", stages["parent"]), ("roughened", stages["roughened"]),
                       ("dissected", stages["dissected"])):
        require(plotted[key]["max_m"] == float(field.max()) and
                plotted[key]["min_m"] == float(field.min()),
                f"{kind}: the {key} panel range is not the plotted array's own range")
    require(plotted["roughened"]["max_m"] - plotted["parent"]["max_m"] > 0.0,
            f"{kind}: facet noise added no relief at the chart peak")
    require(plotted["dissected"]["min_m"] >= floor.min() - 1e-9,
            f"{kind}: the dissected panel shows a bed below the recomputed floor")
    require(abs(panels["change"]["incision_min_m"] + record["maximum_incision_m"]) <= 1e-12,
            f"{kind}: change panel incision disagrees with the ledger")
    record["panels"] = panels
    record["status"] = "illustrated"
    record["flags"] = {flag: metadata[flag] for flag in FLAGS}
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles", type=Path, default=DEFAULT_BUNDLES)
    parser.add_argument("--parents", type=Path, default=DEFAULT_PARENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--kinds", default=",".join(sorted(KINDS)))
    args = parser.parse_args(argv)
    requested = [value for value in args.kinds.split(",") if value]
    unknown = sorted(set(requested) - KINDS)
    if unknown:
        raise SystemExit(f"unknown kinds: {unknown}")
    output = guard_output(args.output)
    manifest = load_manifest(args.bundles, SCHEMA, ALGORITHM, "surface")
    parent_manifest = load_manifest(args.parents, "metric-special-terrain-v1",
                                    "special-terrain-field-forms-v1", "parent")
    entries, parent_entries = manifest["forms"], parent_manifest["forms"]
    missing = sorted(set(requested) - set(entries))
    if missing:
        raise SystemExit(f"bundles missing from the manifest: {missing}")
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema": SCHEMA, "algorithm": ALGORITHM, "status": "candidate",
              "paths_omitted": True,
              "note": "no timestamp and no directory path is recorded so two runs compare equal",
              "claims": {"real_terrain_reconstruction": False, "publishable": False,
                         "hydraulic_ready": False, "natural_outlet_verified": False},
              "forms": {}}
    for kind in sorted(set(requested)):
        record = preview_kind(kind, args.bundles, args.parents, entries, parent_entries, output)
        report["forms"][kind] = record
        print(f"{kind}: {record['chart_rows']}x{record['chart_cols']} @ {record['spacing_m']:g} m "
              f"relief {record['parent_relief_m']:.4g} -> {record['roughened_relief_m']:.4g} m "
              f"incision {record['maximum_incision_m']:.4g} m "
              f"deposit {record['maximum_deposition_m']:.4g} m "
              f"collar {record['collar_max_abs_m']:.3g} m")
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"report: {report_path.name} sha256 {sha256_file(report_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
