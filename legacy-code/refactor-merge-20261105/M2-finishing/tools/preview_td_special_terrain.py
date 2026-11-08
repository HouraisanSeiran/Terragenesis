"""End-to-end L0 special-terrain preview on a real pinned Terrain Diffusion 1 m bed.

This tool runs the thin adapter over the pinned 30 m hierarchy and the shared fine bed:

    pinned hierarchy -> selected fine window -> chart -> L0 field form -> preview

The identity chain of every produced bundle is recorded so the form geometry can be traced
back to the exact fine bed, native window and source hierarchy. Everything it writes lands
in a scratch evidence directory: never a source cache, never ``verification/``. Two cases
run end to end, because the shared fine bed is capped at 240x240 cells:

* a full-size ``volcanic_plug`` preset on the coarsest allowed bed (4 m, 960 m window);
* a single-centre ``karst_tower_field`` tower on the true 1 m bed (240 m window).

The second case is the closest this revision gets to a real-metre landform: the targets are
placed at the window centre by the caller. That placement is a declared assumption, not a
claim about where such a tower exists.

The field-form module fills terrain up to a declared *absolute* surface and never excavates
(``displacement = max(relief - bed, 0)``). A preset whose ``base_elevation_m`` is 0 m would
therefore sit about 1.4 km below the pinned bed and produce exactly zero relief - a silent,
all-zero form. This tool declares the foot elevation of every target as the minimum bed
elevation over the selected window and records that basis per case, so the declaration is
visible instead of implied. It is an assumption of the caller, not a surveyed value, and it
is the reason the two cases here are *fills against a real bed*, not reconstructions.
"""

import argparse
import json
import math
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.special_terrain import METRIC_FORMS_ALGORITHM as ALGORITHM, FormTarget, METRIC_FORMS_SCHEMA as FORM_SCHEMA, SpecialFormRecipe, build_special_form_vdm, form_preset, save_special_form_vdm, validate_special_form_vdm
from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.special_terrain import TD_ADAPTER_SCHEMA as ADAPTER_SCHEMA, build_td_form_chart, select_native_window
from tools.preview_special_terrain_forms import (plot_plan, plot_profile, plot_solid,
                                                 sha256_file)

SOURCE_PATH = "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz"
SOURCE = dict(path=str(ROOT / SOURCE_PATH),
              expected_sha256="36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
              expected_identity="cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998")
DEFAULT_OUTPUT = Path(".scratch/special-terrain/td-adapter-20261019")
SAMPLE_SEED = 20261019
VERIFICATION_DIRECTORY = "verification"
ALL_FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable",
             "self_intersection_verified")
WINDOW_SIZE_M = 960.0
WINDOW_CENTER_M_XZ = [-177600.0, 67680.0]
POSITION_ASSUMPTION = (
    "target centres sit at the selected window centre; the adapter and this tool choose no "
    "real-world site and no site was surveyed"
)
CHANNEL_SELECTION = (
    "empty edge selection: the passive special-terrain bed is the plain native bilinear "
    "bed, so the adapter cuts no artificial channel through the landform; the separate "
    "shared-bed channel ladder in tools/diagnose_single_domain_fine.py is deliberately not "
    "reproduced here"
)
FOOT_ELEVATION_BASIS = (
    "minimum bed elevation over the selected window, declared by this caller; the pinned "
    "hierarchy carries no surveyed landform foot and the preset foot of 0 m is a synthetic "
    "base-bed value, so the foot is an assumption and not a measurement"
)
FILL_ONLY_SEMANTICS = (
    "the form fills terrain up to the declared absolute surface and never excavates "
    "(displacement = max(declared relief - bed, 0)); on a sloping real bed the emerged "
    "footprint is therefore asymmetric and can be smaller than the nominal ellipse"
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _finite_number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"invalid {name}")


def guard_output(output):
    parts = [part.lower() for part in Path(output).resolve().parts]
    require(VERIFICATION_DIRECTORY not in parts,
            f"refusing to write under {VERIFICATION_DIRECTORY}/: {output}")
    return Path(output)


def replace_target(target, center_x_m, center_z_m, base_elevation_m):
    return FormTarget(target.target_id, center_x_m, center_z_m, base_elevation_m,
                      target.height_m, target.radius_x_m, target.radius_z_m,
                      target.source_grade, target.source_ref)


def centred_recipe(kind, *, center_x_m, center_z_m, base_elevation_m, size_x_m, size_z_m,
                   spacing_m, keep="all"):
    """The declared preset with its targets moved to the window centre and its foot set.

    Radii, heights, seed, collar margin and the target subset stay exactly the preset
    values; the chart extent and spacing are taken from the real chart being built instead,
    so the saved recipe describes the bed it was actually burned into rather than the
    synthetic preset bed. ``base_elevation_m`` must be the caller's declared absolute foot:
    a preset foot of 0 m would bury the whole form under the pinned bed and yield a silent
    all-zero displacement, which ``case_record`` would then have to report as a failed case.
    ``keep="tallest"`` takes a declared subset: the single tallest preset target, for
    windows too small to hold the whole field.
    """
    _finite_number(base_elevation_m, "foot elevation")
    for name, value in (("chart size x", size_x_m), ("chart size z", size_z_m),
                        ("chart spacing", spacing_m)):
        _finite_number(value, name)
        if value <= 0:
            raise ValueError(f"invalid {name}")
    preset = form_preset(kind)
    chosen = preset.targets
    subset = "full preset"
    if keep == "tallest":
        chosen = (max(preset.targets, key=lambda target: target.height_m),)
        subset = (f"single tallest preset target of {len(preset.targets)}; the remaining "
                  f"field does not fit the window")
    elif keep != "all":
        raise ValueError("invalid preset subset selector")
    targets = tuple(replace_target(target, center_x_m, center_z_m, base_elevation_m)
                    for target in chosen)
    return preset, SpecialFormRecipe(preset.kind, size_x_m, size_z_m, spacing_m,
                                     preset.collar_margin_m, targets, preset.seed), subset


def chart_center_m_xz(reference):
    x = reference[:, :, 0]
    z = reference[:, :, 2]
    return 0.5 * (float(x.min()) + float(x.max())), 0.5 * (float(z.min()) + float(z.max()))


def chart_size_m_xz(reference):
    x = reference[:, :, 0]
    z = reference[:, :, 2]
    return float(x.max()) - float(x.min()), float(z.max()) - float(z.min())


def _footprint_bed_min(reference, recipe):
    """Lowest bed elevation inside every nominal target ellipse.

    Reported as the floor each declared foot was set against, per target. The emerged
    outline of a fill-only form is instead set by the *highest* bed under the ellipse, so
    this number is a declaration aid and not the extent of the result.
    """
    x = reference[:, :, 0]
    z = reference[:, :, 2]
    bed = reference[:, :, 1]
    floors = []
    for target in recipe.targets:
        across = (x - target.center_x_m) / target.radius_x_m
        along = (z - target.center_z_m) / target.radius_z_m
        inside = np.sqrt(across * across + along * along) <= 1.0
        if not inside.any():
            raise ValueError(f"target {target.target_id} has no chart cell inside its footprint")
        floors.append(float(bed[inside].min()))
    return floors


def build_case(kind, hierarchy, *, spacing_m, requested_size_m, window_center_m_xz, keep="all"):
    native_shape = hierarchy["arrays"]["height_m"].shape
    native_origin = hierarchy["metadata"]["origin_m_xz"]
    window = select_native_window(center_m_xz=window_center_m_xz,
                                  size_m_xz=[requested_size_m] * 2, spacing_m=spacing_m,
                                  native_shape=native_shape,
                                  native_origin_m_xz=native_origin)
    chart = build_td_form_chart(hierarchy, window=window, spacing_m=spacing_m,
                                source_hierarchy_sha256=SOURCE["expected_sha256"],
                                selected_edge_cell_ids=np.zeros((0, 2), dtype=np.int64),
                                channel_policy="reject")
    reference = chart["chart_reference_xyz_m"]
    center_x_m, center_z_m = chart_center_m_xz(reference)
    size_x_m, size_z_m = chart_size_m_xz(reference)
    # Declared foot: the lowest bed elevation in the window, so a fill-only form emerges
    # above the whole bed instead of being buried by the ~1.4 km pinned base.
    foot_elevation_m = float(np.min(reference[:, :, 1]))
    preset, recipe, subset = centred_recipe(kind, center_x_m=center_x_m, center_z_m=center_z_m,
                                          base_elevation_m=foot_elevation_m,
                                          size_x_m=size_x_m, size_z_m=size_z_m,
                                          spacing_m=float(window["spacing_m"]), keep=keep)
    result = build_special_form_vdm(reference, recipe=recipe,
                                    protected_mask=chart["protected_mask"],
                                    source_identity=chart["source_identity"],
                                    protection_identity=chart["protection_identity"],
                                    base_kind="td_fine_bed")
    require(result["metadata"]["base"] == "td_fine_bed", "form did not record the TD bed base")
    require(validate_special_form_vdm(result), "form bundle failed its own validator")
    placement = {
        "kind": kind,
        "preset_kind": preset.kind,
        "preset_subset": subset,
        "target_count": len(recipe.targets),
        "target_center_m_xz": [center_x_m, center_z_m],
        "target_ids": [target.target_id for target in recipe.targets],
        "preset_radius_x_m": [target.radius_x_m for target in recipe.targets],
        "preset_height_m": [target.height_m for target in recipe.targets],
        "declared_foot_elevation_m": foot_elevation_m,
        "declared_foot_basis": FOOT_ELEVATION_BASIS,
        "window_bed_min_m": foot_elevation_m,
        "window_bed_max_m": float(np.max(reference[:, :, 1])),
        "nominal_footprint_bed_min_m": _footprint_bed_min(reference, recipe),
        "fill_only_semantics": FILL_ONLY_SEMANTICS,
        "placement_semantics": POSITION_ASSUMPTION,
        "parameter_sources": result["metadata"]["parameter_sources"][kind],
    }
    return {"window": window, "chart": chart, "result": result, "recipe": recipe,
            "placement": placement}


def case_record(kind, case, bundle_path):
    result = case["result"]
    arrays = result["arrays"]
    reference = arrays["reference_xyz_m"]
    displacement = arrays["displacement_xyz_m"]
    chart_record = case["chart"]["record"]
    rows, cols = reference.shape[:2]
    relief = float(np.max(displacement[:, :, 1]))
    require(relief > 0.0, f"{kind}: form produced no relief")
    collar = float(max(np.max(np.abs(displacement[0, :, 1])),
                       np.max(np.abs(displacement[-1, :, 1])),
                       np.max(np.abs(displacement[:, 0, 1])),
                       np.max(np.abs(displacement[:, -1, 1]))))
    require(collar == 0.0, f"{kind}: collar displacement is {collar}, expected exactly 0")
    require(np.array_equal(arrays["vertices_xyz_m"],
                           (reference + displacement).reshape(-1, 3)),
            f"{kind}: vertices are not reference plus displacement")
    require(not np.any(displacement[cases_mask(case)] != 0),
            f"{kind}: a protected cell was displaced")
    # The chart the form was built on must be the chart of this case, and the form must
    # carry that chart's two upstream identities through to its own metadata: that is the
    # whole point of the thin adapter, so it is re-checked here from the arrays rather than
    # trusted from the build path.
    require(np.array_equal(reference, case["chart"]["chart_reference_xyz_m"]),
            f"{kind}: form reference chart is not the adapter chart")
    require(np.array_equal(arrays["protected_mask"], case["chart"]["protected_mask"]),
            f"{kind}: form protected mask is not the adapter mask")
    metadata = result["metadata"]
    for key in ("source_identity", "protection_identity"):
        require(metadata[key] == case["chart"][key],
                f"{kind}: form {key} does not match the adapter chart")
    require(metadata["source_identity"] == chart_record["identity_chain"]["chart_source_identity"],
            f"{kind}: chart source identity disagrees with its own chain record")
    require(metadata["protection_identity"] ==
            chart_record["identity_chain"]["chart_protection_identity"],
            f"{kind}: chart protection identity disagrees with its own chain record")
    require(result["identity_sha256"] == identity(arrays, metadata),
            f"{kind}: re-derived form identity disagrees with the declared identity")
    declared = {target.target_id: target for target in case["recipe"].targets}
    for entry in metadata["recipe"]["targets"]:
        target = declared[entry["target_id"]]
        require(entry["base_elevation_m"] == target.base_elevation_m,
                f"{kind}: saved target foot disagrees with the declared recipe")
    require(float(np.min(reference[:, :, 1])) ==
            float(case["placement"]["declared_foot_elevation_m"]),
            f"{kind}: declared foot is not the window bed minimum")
    require(relief <= max(float(value) for value in case["placement"]["preset_height_m"]) + 1e-9,
            f"{kind}: relief exceeds the declared preset height")
    digest = file_sha256(bundle_path)
    return {
        "kind": kind,
        "file": Path(bundle_path).name,
        "sha256": digest,
        "identity_sha256": result["identity_sha256"],
        "form_schema": FORM_SCHEMA,
        "form_algorithm": ALGORITHM,
        "adapter_schema": ADAPTER_SCHEMA,
        "chart_rows": rows,
        "chart_cols": cols,
        "spacing_m": float(case["window"]["spacing_m"]),
        "max_relief_m": relief,
        "collar_max_abs_m": collar,
        "triangles": int(arrays["triangles"].shape[0]),
        "target_count": len(case["recipe"].targets),
        "declared_flags": {flag: result["metadata"][flag] for flag in
                           ("hydraulic_ready", "natural_outlet_verified", "publishable",
                            "self_intersection_verified")},
        "base": result["metadata"]["base"],
        "window": case["window"],
        "chart_record": chart_record,
        "placement": case["placement"],
    }


def cases_mask(case):
    return case["chart"]["protected_mask"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--kinds", default="volcanic_plug,karst_tower_field")
    args = parser.parse_args(argv)
    output = guard_output(args.output)

    hierarchy = load_basin_hierarchy(**SOURCE)
    require(file_sha256(SOURCE["path"]) == SOURCE["expected_sha256"],
            "pinned hierarchy changed on disk")
    require(hierarchy["identity_sha256"] == SOURCE["expected_identity"],
            "pinned hierarchy identity changed")
    report = {
        "source": {"path": SOURCE_PATH, "expected_sha256": SOURCE["expected_sha256"],
                   "expected_identity": SOURCE["expected_identity"]},
        "adapter_schema": ADAPTER_SCHEMA,
        "form_schema": FORM_SCHEMA,
        "form_algorithm": ALGORITHM,
        "sample_seed": SAMPLE_SEED,
        "position_assumption": POSITION_ASSUMPTION,
        "channel_selection": CHANNEL_SELECTION,
        "foot_elevation_basis": FOOT_ELEVATION_BASIS,
        "fill_only_semantics": FILL_ONLY_SEMANTICS,
        "paths_omitted": True,
        "note": "no timestamp and no absolute path is recorded so two runs compare equal",
        "claims": {"real_terrain_reconstruction": False, "publishable": False,
                   "natural_outlet_certified": False, "hydraulic_ready": False,
                   "foot_elevation_surveyed": False, "preset_foot_is_synthetic": True,
                   "excavation_modelled": False,
                   **{flag: False for flag in ALL_FLAGS}},
        "cases": {},
    }

    requested = [value for value in args.kinds.split(",") if value]
    output.mkdir(parents=True, exist_ok=True)
    for kind in requested:
        if kind == "volcanic_plug":
            spacing_m, requested_size, keep = 4.0, WINDOW_SIZE_M, "all"
        elif kind == "karst_tower_field":
            spacing_m, requested_size, keep = 1.0, 240.0, "tallest"
        else:
            raise SystemExit(f"no declared adapter ladder for kind {kind}")
        case = build_case(kind, hierarchy, spacing_m=spacing_m,
                          requested_size_m=requested_size,
                          window_center_m_xz=WINDOW_CENTER_M_XZ, keep=keep)
        bundle_path = output / f"{kind}-td-bundle.npz"
        if bundle_path.exists():
            bundle_path.unlink()
        save_special_form_vdm(bundle_path, case["result"])
        record = case_record(kind, case, bundle_path)
        arrays = case["result"]["arrays"]
        base_label = (f"pinned TD {case['window']['spacing_m']:g} m fine bed "
                      f"{case['window']['fine_shape_zx'][1]}x{case['window']['fine_shape_zx'][0]}")
        panels = {
            "plan": plot_plan(kind, arrays["reference_xyz_m"], arrays["displacement_xyz_m"],
                              output / f"{kind}-td-a-plan.png", base_label=base_label),
            "profile": plot_profile(kind, arrays["reference_xyz_m"],
                                    arrays["displacement_xyz_m"],
                                    output / f"{kind}-td-b-profile.png", base_label=base_label),
            "solid": plot_solid(kind, arrays["reference_xyz_m"], arrays["displacement_xyz_m"],
                                arrays["vertices_xyz_m"], arrays["triangles"],
                                output / f"{kind}-td-c-solid.png"),
        }
        record["panels"] = panels
        surface = arrays["reference_xyz_m"][:, :, 1] + arrays["displacement_xyz_m"][:, :, 1]
        require(abs(panels["plan"]["colorbar_vmin_m"] - float(surface.min()))
                <= 1e-9 * max(1.0, abs(float(surface.min()))),
                f"{kind}: plan colour floor disagrees with the plotted surface")
        require(abs(panels["plan"]["colorbar_vmax_m"] - float(surface.max()))
                <= 1e-9 * max(1.0, abs(float(surface.max()))),
                f"{kind}: plan colour ceiling disagrees with the plotted surface")
        require(abs(panels["plan"]["extent_m"][1] - panels["plan"]["extent_m"][0]
                    - (record["chart_cols"] - 1) * record["spacing_m"])
                <= 1e-9 * 960.0, f"{kind}: plan extent disagrees with shape x spacing")
        require(abs(panels["profile"]["row_relief_max_m"] - record["max_relief_m"])
                <= 1e-9 * max(1.0, record["max_relief_m"]),
                f"{kind}: profile row does not carry the maximum relief")
        require(abs(panels["solid"]["elevation_max_m"] - float(surface.max()))
                <= 1e-9 * max(1.0, abs(float(surface.max()))),
                f"{kind}: 3D colour range disagrees with the plotted surface")
        report["cases"][kind] = record
        print(f"{kind}: {record['chart_rows']}x{record['chart_cols']} @ {record['spacing_m']:g} m "
              f"relief {record['max_relief_m']:.6g} m collar {record['collar_max_abs_m']:.6g} m "
              f"bed {case['window']['fine_shape_zx'][1]}x{case['window']['fine_shape_zx'][0]}"
              f" snap {case['window']['maximum_snap_observed_m']:.6g} m")

    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"report: {report_path.name} sha256 {sha256_file(report_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
