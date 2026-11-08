"""Reproducible offline preview of the L0 special-terrain field forms.

Reads the candidate bundles written by ``tools/prepare_special_terrain_forms.py``, then
re-derives every plotted scale (extent, colour range, profile row, 3D face stride) from
the geometry arrays and asserts the derived numbers against the bundle manifest *before*
any figure is drawn. A mismatch raises instead of emitting a pretty picture.

Output is a scratch preview directory: never a source cache, never ``verification/``.
The base bed is synthetic analytic geometry, so nothing here claims real Terrain
Diffusion detail and no figure is a certification. The L1 volume forms only get explicit
placeholder panels in this revision.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.special_terrain import METRIC_FORMS_ALGORITHM as ALGORITHM, KINDS, METRIC_FORMS_SCHEMA as SCHEMA, load_special_form_vdm
from terrain_pipeline.common_infra import identity


DEFAULT_BUNDLES = Path(".scratch/special-terrain/bundles-20261019")
DEFAULT_OUTPUT = Path(".scratch/special-terrain/preview-20261019")
SAMPLE_SEED = 20261019
MAX_FACES = 16000
PNG_META = {"Software": "preview_special_terrain_forms"}
VERIFICATION_DIRECTORY = "verification"

# The four L0 kinds are the field forms that already exist. The L1 entries are the
# volume-route forms; they are placeholders here and their geometry belongs to P5.
L1_PLACEHOLDERS = (
    ("l1-sinkhole-shaft", "Sinkhole shaft, subsurface river and skylight (tiankeng)"),
    ("l1-cave-skylight-bridge", "Cave, skylight and natural bridge"),
    ("l1-rock-egg-pile", "Devils Marbles, stacked rock eggs with voids between them"),
    ("l1-uluru-flared-slope", "Uluru flared slope, overhanging base"),
)

# The six user-named special-terrain categories and the panel that illustrates each one.
# Every entry must appear as a contact-sheet slot, otherwise the sheet refuses to be written.
SIX_CATEGORIES = (
    ("1 Devils Tower plug", "volcanic_plug"),
    ("2 Tiankeng sinkhole", "l1-sinkhole-shaft"),
    ("3 Karst tower field", "karst_tower_field"),
    ("4 Zhangjiajie sandstone pillars", "sandstone_pillar_field"),
    ("5 Uluru inselberg", "inselberg"),
    ("6 Devils Marbles rock eggs", "l1-rock-egg-pile"),
)
CONTACT_SHEET = "six-category-contact-sheet.png"
CONTACT_SLOTS = (
    ("L0 field forms, vertical displacement only", "L0",
     ("volcanic_plug", "karst_tower_field", "sandstone_pillar_field", "inselberg")),
    ("L1 volume forms, sampled rock Boolean route, geometry pending in P5", "L1",
     ("l1-sinkhole-shaft", "l1-cave-skylight-bridge", "l1-rock-egg-pile",
      "l1-uluru-flared-slope")),
)
CATEGORY_LABELS = {
    "volcanic_plug": "1 Devils Tower volcanic plug",
    "l1-sinkhole-shaft": "2 Tiankeng sinkhole shaft, river and skylight",
    "karst_tower_field": "3 Karst tower field (Guilin)",
    "sandstone_pillar_field": "4 Zhangjiajie sandstone pillar group",
    "inselberg": "5 Uluru inselberg body",
    "l1-uluru-flared-slope": "5 Uluru flared slope base",
    "l1-rock-egg-pile": "6 Devils Marbles stacked rock eggs",
    "l1-cave-skylight-bridge": "2/3 cave, skylight and natural bridge",
}


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


def load_manifest(bundles):
    path = Path(bundles) / "manifest-report.json"
    require(path.is_file(), f"missing bundle manifest: {path}")
    record = json.loads(path.read_text(encoding="utf-8"))
    require(record.get("schema") == SCHEMA, "manifest schema mismatch")
    require(record.get("algorithm") == ALGORITHM, "manifest algorithm mismatch")
    require(record.get("base") == "synthetic_analytic", "unexpected manifest base bed")
    require(record.get("status") == "candidate", "preview only accepts candidate bundles")
    return record


def measure(kind, result, entry, bundle_path):
    """Re-derive the geometry numbers and cross-check them against the manifest."""
    arrays = result["arrays"]
    reference = arrays["reference_xyz_m"]
    displacement = arrays["displacement_xyz_m"]
    vertices = arrays["vertices_xyz_m"]
    triangles = arrays["triangles"]
    mask = arrays["protected_mask"]
    rows, cols = reference.shape[:2]
    require(displacement.shape == reference.shape, f"{kind}: displacement shape mismatch")
    require(mask.shape == (rows, cols), f"{kind}: protected mask shape mismatch")
    require((rows, cols) == (int(entry["chart_rows"]), int(entry["chart_cols"])),
            f"{kind}: chart shape {rows}x{cols} disagrees with the manifest")

    spacing_x = float(reference[0, 1, 0] - reference[0, 0, 0])
    spacing_z = float(reference[1, 0, 2] - reference[0, 0, 2])
    require(abs(spacing_x - spacing_z) <= 1e-9 * max(spacing_x, spacing_z),
            f"{kind}: non-uniform chart spacing")
    spacing_m = 0.5 * (spacing_x + spacing_z)
    declared_spacing = float(entry["spacing_m"])
    require(abs(spacing_m - declared_spacing) <= 1e-9 * max(1.0, declared_spacing),
            f"{kind}: spacing {spacing_m} disagrees with the manifest {declared_spacing}")

    relief = float(np.max(displacement[:, :, 1]))
    declared_relief = float(entry["max_relief_m"])
    require(abs(relief - declared_relief) <= 1e-9 * max(1.0, abs(declared_relief)),
            f"{kind}: max relief {relief} disagrees with the manifest {declared_relief}")

    collar = float(max(np.max(np.abs(displacement[0, :, 1])),
                       np.max(np.abs(displacement[-1, :, 1])),
                       np.max(np.abs(displacement[:, 0, 1])),
                       np.max(np.abs(displacement[:, -1, 1]))))
    require(collar == 0.0, f"{kind}: chart collar displacement is {collar}, expected exactly 0")
    require(not np.any(displacement[:, :, 0] != 0) and not np.any(displacement[:, :, 2] != 0),
            f"{kind}: displacement must be vertical only")
    require(not np.any(displacement[mask] != 0), f"{kind}: a protected cell was displaced")
    require(not np.any(mask), f"{kind}: this bundle declares an empty protected mask")

    require(triangles.shape == (2 * (rows - 1) * (cols - 1), 3),
            f"{kind}: triangle count mismatch")
    require(np.array_equal(vertices, (reference + displacement).reshape(-1, 3)),
            f"{kind}: vertices are not reference plus displacement")

    digest = sha256_file(bundle_path)
    require(digest == entry["sha256"], f"{kind}: bundle bytes disagree with the manifest")
    local_identity = identity(arrays, result["metadata"])
    require(local_identity == result["identity_sha256"] == entry["identity_sha256"],
            f"{kind}: recomputed identity disagrees with the bundle or the manifest")
    require(result["metadata"]["base"] == "synthetic_analytic",
            f"{kind}: preview expects the synthetic analytic base bed")
    for flag in ("hydraulic_ready", "natural_outlet_verified", "publishable",
                 "self_intersection_verified"):
        require(result["metadata"][flag] is False, f"{kind}: status flag {flag} is not False")

    return {"kind": kind, "file": Path(bundle_path).name, "sha256": digest,
            "identity_sha256": local_identity, "chart_rows": rows, "chart_cols": cols,
            "spacing_m": spacing_m, "max_relief_m": relief, "collar_max_abs_m": collar,
            "triangles": int(triangles.shape[0]),
            "target_count": int(entry["target_count"]),
            "parameter_sources": entry["parameter_sources"]}


def chart_extent(reference):
    """Physical metre extent derived from the array, not from a hand-written number."""
    return (float(reference[0, 0, 0]), float(reference[0, -1, 0]),
            float(reference[0, 0, 2]), float(reference[-1, 0, 2]))


def plot_plan(kind, reference, displacement, output, *,
              base_label="synthetic analytic base bed"):
    surface = reference[:, :, 1] + displacement[:, :, 1]
    rows, cols = surface.shape
    x0, x1, z0, z1 = chart_extent(reference)
    extent = (x0, x1, z0, z1)
    spacing_x = (x1 - x0) / (cols - 1)
    spacing_z = (z1 - z0) / (rows - 1)
    vmin = float(np.min(surface))
    vmax = float(np.max(surface))

    fig, ax = plt.subplots(figsize=(9, 7), dpi=140)
    image = ax.imshow(surface, origin="lower", extent=extent, cmap="terrain",
                      vmin=vmin, vmax=vmax, aspect="equal")
    levels = np.linspace(vmin, vmax, 11)[1:-1]
    if levels.size:
        ax.contour(np.linspace(x0, x1, cols), np.linspace(z0, z1, rows), surface,
                   levels=levels, colors="#101010", linewidths=.4, alpha=.65)
    bar = fig.colorbar(image, ax=ax, shrink=.85)
    bar.set_label("elevation (m)")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("z (m)")
    ax.set_title(f"{kind}: plan view over {base_label}")
    ax.text(.01, .01, f"extent {x1 - x0:.1f} m x {z1 - z0:.1f} m  spacing {spacing_x:.3g} m",
            transform=ax.transAxes, fontsize=8, color="#202020")
    fig.tight_layout()
    fig.savefig(output, metadata=PNG_META)
    plt.close(fig)
    return {"file": Path(output).name, "sha256": sha256_file(output),
            "extent_m": list(extent), "spacing_x_m": spacing_x, "spacing_z_m": spacing_z,
            "colorbar_vmin_m": vmin, "colorbar_vmax_m": vmax,
            "surface_min_m": float(surface.min()), "surface_max_m": float(surface.max()),
            "contour_levels_m": [float(value) for value in levels]}


def plot_profile(kind, reference, displacement, output, *,
                 base_label="synthetic analytic base bed"):
    relief_rows = np.max(displacement[:, :, 1], axis=1)
    row = int(np.argmax(relief_rows))
    x = reference[0, :, 0]
    base = reference[row, :, 1]
    final = base + displacement[row, :, 1]

    fig, ax = plt.subplots(figsize=(10, 5), dpi=140)
    ax.plot(x, base, color="#555555", lw=1.2, label=base_label)
    ax.fill_between(x, base, final, color="#c9a227", alpha=.35,
                    label="added field displacement")
    ax.plot(x, final, color="#7a4b00", lw=1.4, label="displaced surface")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("elevation (m)")
    ax.set_title(f"{kind}: profile along z = {float(reference[row, 0, 2]):.1f} m "
                 "(row of maximum relief)")
    ax.grid(alpha=.25, lw=.5)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output, metadata=PNG_META)
    plt.close(fig)
    return {"file": Path(output).name, "sha256": sha256_file(output),
            "profile_row": row, "profile_z_m": float(reference[row, 0, 2]),
            "x_min_m": float(x.min()), "x_max_m": float(x.max()),
            "base_min_m": float(base.min()), "base_max_m": float(base.max()),
            "final_min_m": float(final.min()), "final_max_m": float(final.max()),
            "row_relief_max_m": float(relief_rows[row]),
            "row_relief_sum_m": float(np.sum(displacement[row, :, 1]))}


def plot_solid(kind, reference, displacement, vertices, triangles, output):
    faces_total = int(triangles.shape[0])
    stride = max(1, int(math.ceil(faces_total / MAX_FACES)))
    faces = triangles[::stride]
    elevation = vertices[:, 1]
    vmin = float(elevation.min())
    vmax = float(elevation.max())
    cmap = matplotlib.colormaps["viridis"]
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    points = vertices[faces]
    facecolors = cmap(norm(points[:, :, 1].mean(axis=1)))

    fig = plt.figure(figsize=(9, 7), dpi=140)
    ax = fig.add_subplot(projection="3d")
    ax.add_collection3d(Poly3DCollection(points, facecolors=facecolors,
                                         edgecolors="none", linewidths=0.0))
    x0, x1, z0, z1 = chart_extent(reference)
    ax.set_xlim(x0, x1)
    ax.set_ylim(z0, z1)
    ax.set_zlim(vmin, max(vmax, vmin + 1e-6))
    ax.set_box_aspect((max(x1 - x0, 1e-6), max(z1 - z0, 1e-6), max(vmax - vmin, 1e-6)))
    ax.view_init(elev=28, azim=-62)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("z (m)")
    ax.set_zlabel("elevation (m)")
    ax.set_title(f"{kind}: displaced surface, every {stride}th triangle shaded")
    mappable = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    mappable.set_array(elevation)
    fig.colorbar(mappable, ax=ax, shrink=.6, pad=.12, label="elevation (m)")
    fig.tight_layout()
    fig.savefig(output, metadata=PNG_META)
    plt.close(fig)
    return {"file": Path(output).name, "sha256": sha256_file(output),
            "faces_total": faces_total, "face_stride": stride,
            "faces_drawn": int(faces.shape[0]),
            "elevation_min_m": vmin, "elevation_max_m": vmax,
            "x_range_m": [x0, x1], "z_range_m": [z0, z1]}


def write_placeholder(name, label, output):
    fig, ax = plt.subplots(figsize=(8, 5), dpi=140)
    ax.axis("off")
    ax.text(.5, .62, "L1 volume path - preview pending (P5)", ha="center", va="center",
            fontsize=15, color="#333333")
    ax.text(.5, .42, label, ha="center", va="center", fontsize=11, color="#444444")
    ax.text(.5, .24, "geometry not generated: needs the sampled rock Boolean route",
            ha="center", va="center", fontsize=9, color="#777777")
    fig.tight_layout()
    fig.savefig(output, metadata=PNG_META)
    plt.close(fig)
    return {"file": Path(output).name, "sha256": sha256_file(output),
            "status": "placeholder", "label": label, "geometry_verified": False,
            "detail": "L1 volume forms are implemented in P5; this panel only reserves the slot"}


def write_contact_sheet(records, placeholders, output):
    """One labelled slot per special-terrain category, embedding the plan panels.

    Every caption number is read from the geometry-derived record (never hand-written), and
    the sheet stores the sha256 of each embedded panel, so the composite is traceable back
    to the panels it embeds. A category that has no slot refuses the whole sheet.
    """
    slotted = {kind for _, _, kinds in CONTACT_SLOTS for kind in kinds}
    for label, kind in SIX_CATEGORIES:
        require(kind in slotted, f"category {label} has no contact-sheet slot")
    rows, columns = len(CONTACT_SLOTS), max(len(slot[2]) for slot in CONTACT_SLOTS)
    fig, axes = plt.subplots(rows, columns, figsize=(5.0 * columns, 4.6 * rows), dpi=140)
    entries = []
    for row_index, (row_label, grade, kinds) in enumerate(CONTACT_SLOTS):
        for column in range(columns):
            ax = axes[row_index, column]
            ax.axis("off")
            if column >= len(kinds):
                continue
            kind = kinds[column]
            if kind in records:
                record = records[kind]
                panel = record["panels"]["plan"]
                x0, x1, z0, z1 = panel["extent_m"]
                require(abs((x1 - x0) - (record["chart_cols"] - 1) * record["spacing_m"]) <=
                        1e-9 * max(1.0, x1 - x0),
                        f"{kind}: contact-sheet extent disagrees with shape x spacing")
                caption = (f"{CATEGORY_LABELS[kind]} [{grade}]\n"
                           f"extent {x1 - x0:.1f} x {z1 - z0:.1f} m | spacing "
                           f"{record['spacing_m']:.3g} m | relief {record['max_relief_m']:.6g} m")
                status, panel_sha, panel_file = ("geometry", panel["sha256"], panel["file"])
            else:
                placeholder = placeholders[kind]
                caption = (f"{CATEGORY_LABELS[kind]} [{grade}]\n"
                           "volume geometry pending (P5): slot reserved only")
                status, panel_sha, panel_file = ("placeholder", placeholder["sha256"],
                                                 placeholder["file"])
            image_path = Path(output) / panel_file
            digest = sha256_file(image_path)
            require(digest == panel_sha,
                    f"{kind}: contact sheet would embed a changed panel {panel_file}")
            image = plt.imread(image_path)
            require(image.ndim == 3 and min(image.shape[:2]) >= 64,
                    f"{kind}: unreadable panel image {panel_file}")
            ax.imshow(image, interpolation="nearest")
            ax.set_title(caption, fontsize=9)
            entries.append({"row": row_index, "column": column, "row_label": row_label,
                            "kind": kind, "status": status, "panel_file": panel_file,
                            "panel_sha256": digest, "caption": caption})
    fig.suptitle("Six special-terrain categories: " +
                 "; ".join(label for label, _ in SIX_CATEGORIES), fontsize=11)
    fig.tight_layout()
    sheet_path = Path(output) / CONTACT_SHEET
    fig.savefig(sheet_path, metadata=PNG_META)
    plt.close(fig)
    return {"file": CONTACT_SHEET, "sha256": sha256_file(sheet_path),
            "categories": [{"label": label, "kind": kind} for label, kind in SIX_CATEGORIES],
            "slots": entries,
            "note": ("captions are formatted from the geometry-derived records; each slot records "
                     "the sha256 of the panel it embeds")}


def preview_kind(kind, bundles, entries, output):
    entry = entries[kind]
    bundle_path = Path(bundles) / entry["file"]
    result = load_special_form_vdm(bundle_path, expected_sha256=entry["sha256"],
                                   expected_identity=entry["identity_sha256"])
    record = measure(kind, result, entry, bundle_path)
    arrays = result["arrays"]
    panels = {
        "plan": plot_plan(kind, arrays["reference_xyz_m"], arrays["displacement_xyz_m"],
                          output / f"{kind}-a-plan.png"),
        "profile": plot_profile(kind, arrays["reference_xyz_m"],
                                arrays["displacement_xyz_m"],
                                output / f"{kind}-b-profile.png"),
        "solid": plot_solid(kind, arrays["reference_xyz_m"], arrays["displacement_xyz_m"],
                            arrays["vertices_xyz_m"], arrays["triangles"],
                            output / f"{kind}-c-solid.png"),
    }
    # The plotted scales must agree with the geometry, not with a hand-written constant.
    x0, x1, z0, z1 = panels["plan"]["extent_m"]
    require(abs((x1 - x0) - (record["chart_cols"] - 1) * record["spacing_m"]) <=
            1e-9 * max(1.0, x1 - x0), f"{kind}: plan extent disagrees with shape x spacing")
    require(abs((z1 - z0) - (record["chart_rows"] - 1) * record["spacing_m"]) <=
            1e-9 * max(1.0, z1 - z0), f"{kind}: plan extent disagrees with shape x spacing")
    require(abs(panels["plan"]["colorbar_vmax_m"] - record["max_relief_m"]) <=
            1e-9 * max(1.0, record["max_relief_m"]),
            f"{kind}: colour range disagrees with the measured relief")
    require(abs(panels["profile"]["row_relief_max_m"] - record["max_relief_m"]) <=
            1e-9 * max(1.0, record["max_relief_m"]),
            f"{kind}: profile row does not carry the maximum relief")
    require(abs(panels["solid"]["elevation_max_m"] - record["max_relief_m"]) <=
            1e-9 * max(1.0, record["max_relief_m"]),
            f"{kind}: 3D colour range disagrees with the measured relief")
    record["panels"] = panels
    record["status"] = "illustrated"
    record["base"] = result["metadata"]["base"]
    record["flags"] = {flag: result["metadata"][flag] for flag in
                       ("hydraulic_ready", "natural_outlet_verified", "publishable",
                        "self_intersection_verified")}
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles", type=Path, default=DEFAULT_BUNDLES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--kinds", default=",".join(sorted(KINDS)))
    args = parser.parse_args(argv)

    requested = [value for value in args.kinds.split(",") if value]
    unknown = sorted(set(requested) - KINDS)
    if unknown:
        raise SystemExit(f"unknown kinds: {unknown}")
    output = guard_output(args.output)
    manifest = load_manifest(args.bundles)
    entries = manifest["forms"]
    missing = sorted(set(requested) - set(entries))
    if missing:
        raise SystemExit(f"bundles missing from the manifest: {missing}")

    output.mkdir(parents=True, exist_ok=True)
    report = {"schema": SCHEMA, "algorithm": ALGORITHM, "base": "synthetic_analytic",
              "status": "candidate", "sample_seed": SAMPLE_SEED,
              "paths_omitted": True,
              "note": "no timestamp and no directory path is recorded so two runs compare equal",
              "claims": {"real_terrain_reconstruction": False, "publishable": False,
                         "hydraulic_ready": False, "natural_outlet_verified": False},
              "forms": {}, "l1_placeholders": {}}

    for kind in sorted(set(requested)):
        record = preview_kind(kind, args.bundles, entries, output)
        report["forms"][kind] = record
        print(f"{kind}: {record['chart_rows']}x{record['chart_cols']} @ {record['spacing_m']:g} m "
              f"relief {record['max_relief_m']:.6g} m collar {record['collar_max_abs_m']:.6g} m "
              f"faces {record['panels']['solid']['faces_drawn']}/"
              f"{record['panels']['solid']['faces_total']}")

    for name, label in L1_PLACEHOLDERS:
        report["l1_placeholders"][name] = write_placeholder(name, label, output / f"{name}.png")
        print(f"{name}: placeholder")

    report["contact_sheet"] = write_contact_sheet(report["forms"], report["l1_placeholders"],
                                                 output)
    print(f"contact sheet: {CONTACT_SHEET} sha256 {report['contact_sheet']['sha256']} "
          f"slots {len(report['contact_sheet']['slots'])}")

    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"report: {report_path.name} sha256 {sha256_file(report_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
