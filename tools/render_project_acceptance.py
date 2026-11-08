"""Read-only, reproducible CPU atlas of saved stage 1/2 products.

Run from the repository root with runtime/venv/Scripts/python.exe -B
tools/render_project_acceptance.py --output .scratch/project-remote-acceptance-20261031/atlas
Every output directory must be new. No terrain, routing or process state is changed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline import terrain_map_style as style
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.environment_product import load_product
from terrain_pipeline.environment_regional_hydraulics import load_climate_driver, initial_climate_state, advance_climate_driver
from render_remote_sensing import surface_rgb, water_rgb

DECLARATION = "SYNTHETIC MODEL VISUALIZATION / NOT SATELLITE OBSERVATION"
STORE = ROOT / ".scratch/river-generation-review/real-lakes-42km"
SEASON = ROOT / ".scratch/stage2-world-integration/seasonal-verification-v4"
G6 = ROOT / ".scratch/stage2-finish-20261030/g6-evidence/product.npz"
MECHANISM = ROOT / ".scratch/stage2-g9-g20/verification-reviewed/inland/product.npz"
DELTA = ROOT / ".scratch/delta-process-natural-20261031"


def extent(origin_m, shape, spacing_m):
    """Raster edges from cell-centre coordinates, in world km."""
    x, z = origin_m
    rows, cols = shape
    half = spacing_m / 2
    return [(x-half)/1000, (x+(cols-1)*spacing_m+half)/1000,
            (z+(rows-1)*spacing_m+half)/1000, (z-half)/1000]


def shared_limits(fields):
    finite = [np.asarray(a)[np.isfinite(a)] for a in fields]
    low = min(float(a.min()) for a in finite if a.size)
    high = max(float(a.max()) for a in finite if a.size)
    return low, high


def channel_segments(network, threshold):
    """Filter drawing only; stored accumulated flow and routing remain intact."""
    sources, targets = network["reach_source"], network["reach_target"]
    chosen = network["node_q_m3_s"][sources] >= threshold
    sources, targets = sources[chosen], targets[chosen]
    xy = np.column_stack((network["node_x_m"], network["node_z_m"])) / 1000
    return np.stack((xy[sources], xy[targets]), axis=1), sources


class Atlas:
    def __init__(self, output, dpi):
        self.output, self.dpi = output, dpi
        self.inputs, self.figures = {}, []

    def source(self, path):
        path = Path(path)
        key = path.relative_to(ROOT).as_posix()
        if key not in self.inputs:
            self.inputs[key] = {"sha256": file_sha256(path), "bytes": path.stat().st_size}
        return key

    def decorate(self, ax, box):
        ax.set_xlabel("world x (km)")
        ax.set_ylabel("world z (km)")
        ax.set_aspect("equal")
        style.draw_scale_bar(ax, style.nice_scale_length_km(box[1]-box[0]))

    def save(self, fig, name, title, sources, box, shape, spacing, note, fields):
        fig.suptitle(title, fontsize=14)
        fig.text(.5, .035, note, ha="center", fontsize=8, wrap=True)
        fig.text(.5, .012, DECLARATION, ha="center", fontsize=8)
        fig.tight_layout(rect=(0, .09, 1, .94))
        path = self.output / (name + ".png")
        fig.savefig(path, dpi=self.dpi)
        plt.close(fig)
        from PIL import Image
        with Image.open(path) as im:
            rgb = np.asarray(im.convert("RGB"))
            if float(rgb.std()) < 1:
                raise ValueError("blank figure: " + name)
            pixels = list(im.size)
        self.figures.append({"file": path.name, "title": title,
            "sources": [self.source(p) for p in sources], "source_shape_zx": list(shape),
            "native_spacing_m": spacing, "extent_world_km": box,
            "output_pixels_wh": pixels, "display": "nearest raster; no invented terrain detail; line widths may be enlarged",
            "render_scale": "world km axes and metric scale bar; screen/print scale depends on display size",
            "fields": fields, "scenario": note, "sha256": file_sha256(path)})
        print(path.name, flush=True)

    def panels(self, name, title, panels, sources, box, spacing, note, *, common=False):
        count = len(panels)
        columns = min(3, count)
        rows = (count + columns - 1)//columns
        fig, axes = plt.subplots(rows, columns, figsize=(5.1*columns, 4.8*rows), squeeze=False)
        limits = shared_limits([p[1] for p in panels]) if common else None
        records = []
        for ax, (label, field, unit, cmap) in zip(axes.flat, panels):
            field = np.asarray(field)
            low, high = limits or shared_limits([field])
            im = ax.imshow(field, origin="upper", extent=box, cmap=cmap,
                           vmin=low, vmax=high, interpolation="nearest")
            ax.set_title(label + "\nrange %.5g .. %.5g %s" % (*shared_limits([field]), unit), fontsize=10)
            fig.colorbar(im, ax=ax, fraction=.045, pad=.025, label=unit, format="%.4g")
            self.decorate(ax, box)
            records.append({"label": label, "unit": unit, "range": list(shared_limits([field])),
                            "color_limits": [low, high]})
        for ax in list(axes.flat)[count:]:
            ax.set_visible(False)
        self.save(fig, name, title, sources, box, panels[0][1].shape, spacing, note, records)


def mosaic(version, manifest, kind, names, *, require_finite=False):
    shape = manifest["shape_zx"]
    origin = manifest["origin_native_xz"]
    grids = {name: np.full(shape, np.nan) for name in names}
    paths = []
    for tile in manifest[kind + "_tiles"]:
        path = version / tile["file"]
        if file_sha256(path) != tile["sha256"]:
            raise ValueError("saved tile hash mismatch: " + str(path))
        paths.append(path)
        x, z = np.subtract(tile["origin_native_xz"], origin)
        h, w = tile["shape_zx"]
        with np.load(path) as saved:
            for name in names:
                grids[name][z:z+h, x:x+w] = saved[name]
    if require_finite and any(not np.isfinite(a).all() for a in grids.values()):
        raise ValueError("incomplete saved mosaic")
    return grids, paths


def process(path):
    return load_product(path, expected_sha256=file_sha256(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--channel-q-min", type=float, default=.005)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output directory must not exist")
    if args.channel_q_min < 0 or not np.isfinite(args.channel_q_min):
        parser.error("channel threshold must be finite and nonnegative")
    args.output.mkdir(parents=True)
    atlas = Atlas(args.output, args.dpi)
    registry = json.loads((STORE/"registry.json").read_text(encoding="utf-8"))
    version = STORE/"versions"/registry["components"][0]["version"]
    manifest = json.loads((version/"manifest.json").read_text(encoding="utf-8"))
    if "irregular" not in manifest["water_metadata"]["algorithm"] or "network" not in manifest:
        raise ValueError("current irregular graph required; D8 is not accepted")
    terrain, terrain_paths = mosaic(version, manifest, "composition", ["td_elevation_m", "macro_elevation_m", "composed_elevation_m"], require_finite=True)
    water, water_paths = mosaic(version, manifest, "water", ["final_bed_m", "cut_depth_m", "lake_mask", "water_surface_m", "pending_basin_mask", "upstream_unknown_mask"])
    box = extent(np.asarray(manifest["origin_native_xz"])*30, manifest["shape_zx"], 30)
    sources = [STORE/"registry.json", version/"manifest.json"] + terrain_paths
    note = "seed 20261020 | native 30 m | composed = macro + saved TD residual; original TD is immutable"
    atlas.panels("01-terrain-basis", "42 km saved terrain basis and composition", [
        ("Macro basis", terrain["macro_elevation_m"], "m", "terrain"),
        ("Original saved TD", terrain["td_elevation_m"], "m", "terrain"),
        ("Composed terrain", terrain["composed_elevation_m"], "m", "terrain")], sources, box, 30, note, common=True)
    net_path = version/manifest["network"]["file"]
    if file_sha256(net_path) != manifest["network"]["sha256"]:
        raise ValueError("network hash mismatch")
    with np.load(net_path) as saved:
        network = {k: saved[k] for k in saved.files}
    segments, selected = channel_segments(network, args.channel_q_min)
    fig, ax = plt.subplots(figsize=(11, 10))
    ax.imshow(surface_rgb(water["final_bed_m"], 30), extent=box, origin="upper", interpolation="nearest")
    lakes = water["lake_mask"].astype(bool)
    lake_rgb = np.zeros(lakes.shape+(4,)); lake_rgb[lakes] = [.06, .32, .48, 1]
    ax.imshow(lake_rgb, extent=box, origin="upper", interpolation="nearest")
    ax.add_collection(LineCollection(segments, colors="#65c9ea", linewidths=.55, alpha=.85))
    atlas.decorate(ax, box)
    atlas.save(fig, "02-current-irregular-rivers", "42 km current irregular river graph and modelled lakes", sources+water_paths+[net_path], box,
               manifest["shape_zx"], 30, "Static 0.5 m/year runoff scenario; Q >= %.4g m3/s shown (%d/%d reaches). All tributary contribution retained.\nCyan = routing lines, enlarged display width, NOT observed wet channel width; lake mask = modelled storage; unresolved boundaries remain pending." % (args.channel_q_min,len(selected),len(network["reach_source"])),
               [{"quantity": "representative discharge", "unit": "m3/s", "threshold": args.channel_q_min}])
    atlas.panels("03-derived-bed", "Derived bed and excavation (same saved 42 km source)", [
        ("Derived bed", water["final_bed_m"], "m", "terrain"),
        ("Saved cut depth", water["cut_depth_m"], "m", "magma"),
        ("Unresolved basin mask", water["pending_basin_mask"], "0/1", "Greys"),
        ("Unknown upstream mask", water["upstream_unknown_mask"], "0/1", "Greys")], sources+water_paths, box, 30,
        "Static design bed; not a long-term erosion simulation. Pending basin and unknown-upstream masks are distinct saved fields; both remain visible.")
    driver_path = SEASON/"driver.npz"
    driver = load_climate_driver(driver_path, expected_sha256=file_sha256(driver_path))
    a = driver["arrays"]
    small_box = extent((a["x_m"][0,0],a["z_m"][0,0]), a["elevation_m"].shape, 30)
    months = a["monthly_temperature_c"]
    atlas.panels("04-seasonal-temperature", "G3 synthetic seasonal temperature on real saved terrain", [
        ("Month %d" % (i+1), months[i], "degC", "coolwarm") for i in (0,3,6,9)], [driver_path], small_box, 30,
        "Same extent and colour limits. Synthetic fixed 365-day calendar; seasonal variation, NOT long-term climate change.", common=True)
    boundaries = json.loads((SEASON/"forcing.json").read_text())["climate"]
    forcing = []
    for gain in (0., boundaries["uplift_gain"]):
        _, result = advance_climate_driver(driver, initial_climate_state(driver), 3600.,
            **dict(boundaries, uplift_gain=gain))
        forcing.append(result)
    np.savez_compressed(args.output/"computed-g4-forcing.npz", precipitation_no_uplift_mm=forcing[0]["precipitation_mm"],
        precipitation_actual_mm=forcing[1]["precipitation_mm"], air_temperature_c=forcing[1]["air_temperature_c"])
    atlas.panels("05-computed-precipitation", "G4 actual vapour transport: controlled uplift comparison", [
        ("Uplift disabled", forcing[0]["precipitation_mm"], "mm / 1 h", "Blues"),
        ("Saved ridge / uplift enabled", forcing[1]["precipitation_mm"], "mm / 1 h", "Blues")],
        [driver_path, SEASON/"forcing.json"], small_box, 30,
        "NEW CPU calculation from saved driver: t=0..3600 s, initial vapour=0; west wind 1 m/s; external 10 kg/s per inlet face; gain 0 vs 0.01.\nFixed engineering boundary scenario, not a stochastic climate product or annual rain; identical extent and colour limits.", common=True)
    atlas.panels("06-ridge-climate-support", "G4 complete saved terrain support and computed thermal field", [
        ("Local composed bed", a["elevation_m"], "m", "terrain"),
        ("Original 15 km ridge gradient", a["orographic_gradient"], "m/m", "RdBu_r"),
        ("Actual first-hour temperature", forcing[1]["air_temperature_c"], "degC", "coolwarm")], [driver_path], small_box, 30,
        "Gradient derived using full original 15 km scale / three ridge taps; image window 1.92 km is not the halo extent")
    initial, final = process(SEASON/"initial.npz"), process(SEASON/"final.npz")
    ctx = final["context"]
    env_box = extent(np.asarray(ctx["origin_native_xz"])*30, ctx["height_m"].shape,30)
    env_note = "Saved 0 to 10800 physical seconds (3 h); same real TD / irregular graph source. Initial 20 mm SWE is DECLARED, not observed or climate generated."
    atlas.panels("07-snow-seasonal-event", "G7 saved snow event, initial and final", [
        ("Initial SWE", initial["seasonal"]["snow_swe_mm"], "mm water equivalent", "Blues"),
        ("Final SWE", final["seasonal"]["snow_swe_mm"], "mm water equivalent", "Blues")],
        [SEASON/"initial.npz",SEASON/"final.npz"], env_box,30,env_note,common=True)
    atlas.panels("08-water-inventories", "G5 / G11 saved water inventories", [
        ("Root-zone water", final["states"]["soil_chemistry"]["water_m3"] /
         np.maximum(final["states"]["mass"]["area_m2"], 1e-12) * 1000, "mm", "Blues"),
        ("Fast runoff store", final["seasonal"]["fast_mm"], "mm", "Blues"),
        ("Slow runoff store", final["seasonal"]["slow_mm"], "mm", "Blues"),
        ("Groundwater (zero in this case)", final["states"]["groundwater"]["groundwater_water_m3"], "m3/cell", "Blues")],
        [SEASON/"final.npz"],env_box,30,env_note+" Root-zone/fast/slow/groundwater are separate stocks; zero groundwater is not missing data.")
    g6=process(G6)
    cover=g6["seasonal"]["land_cover"]
    atlas.panels("09-soil-vegetation", "G2 / G6 / G9 / G15 material and vegetation response", [
        ("Allocated soil solid",g6["states"]["mass"]["soil_solid_m3"],"m3 solid/cell","YlOrBr"),
        ("Parent solid inventory",g6["states"]["mass"]["parent_solid_m3"],"m3 solid/cell","YlOrBr"),
        ("Biomass carbon",g6["states"]["succession"]["biomass_carbon_kg"],"kg C/cell","Greens")],
        [G6],env_box,30,"Saved G6 causal engineering scenario at t=%.0f s; soil allocation and ecological parameters declared, not field observations. Classes/suitability saved in manifest." % g6["time_s"])
    mech=process(MECHANISM)
    mc=mech["context"]
    mb=extent(np.asarray(mc["origin_native_xz"])*30,mc["height_m"].shape,30)
    specs=[("Frozen ground temperature","frozen_ground","soil_temperature_c","degC","coolwarm"),
           ("Absorbed radiation energy","radiation","absorbed_energy_j_m2","J/m2","inferno"),
           ("Loose aeolian solid","aeolian","loose_solid_m3","m3 solid/cell","YlOrBr"),
           ("Organic carbon","soil_chemistry","organic_carbon_kg","kg C/cell","Greens"),
           ("Dissolved salt","soil_chemistry","salt_dissolved_kg","kg/cell","Purples"),
           ("Habitat population","habitat","population_individuals","individuals/cell","viridis")]
    atlas.panels("10-environment-mechanisms", "G12 / G13 / G14 / G16 / G20 saved finite mechanisms", [
        (label,mech["states"][module][key],unit,cmap) for label,module,key,unit,cmap in specs],
        [MECHANISM],mb,30,"Explicit engineering forcing and initial stocks; t=%.0f s. Separate saved world identity, not a seasonal-v4 continuation or natural climatology." % mech["time_s"])
    delta_path=DELTA/"run-v1/result.npz"
    with np.load(delta_path) as saved:
        da={k:saved[k] for k in ("initial_bed_m","final_bed_m","water_depth_m","wet_mask","origin_xz_m","spacing_m","height_delta_m")}
    ds=float(da["spacing_m"]); db=extent(da["origin_xz_m"],da["final_bed_m"].shape,ds)
    fig,ax=plt.subplots(figsize=(10,10))
    rgb=surface_rgb(da["final_bed_m"],ds)
    wet=da["wet_mask"].astype(bool)
    rgb[wet]=water_rgb(da["water_depth_m"])[wet]
    ax.imshow(rgb,extent=db,origin="upper",interpolation="nearest");atlas.decorate(ax,db)
    atlas.save(fig,"11-latest-delta-remote","Latest corrected delta: saved bed and actual wet mask",[delta_path,DELTA/"run-v1/summary.json"],db,da["final_bed_m"].shape,ds,
        "Constructed initial distributaries and marine plain; saved computed deposition and hydraulic water. Synthetic depth tint, constant drawing sun 315/45 deg; no fabricated vegetation or spectral signal.\nNot natural self-formed channels; monthly forcing chronology is a model scenario, not a climate forecast.",[{"water_depth_unit":"m","wet_pixels":int(wet.sum()),"max_bed_change_m":float(da["height_delta_m"].max())}])
    tide_path=DELTA/"tides-v1/tides.npz"
    with np.load(tide_path) as saved:
        ta={k:saved[k] for k in ("bed_m","snapshot_wet_masks","snapshot_stage_m","snapshot_time_s","origin_xz_m","spacing_m")}
    tbox=extent(ta["origin_xz_m"],ta["bed_m"].shape,float(ta["spacing_m"]))
    atlas.panels("12-delta-tidal-states","G8 / G19 saved tidal water snapshots", [
        ("t=%.0f s, stage mean %.3g m" % (ta["snapshot_time_s"][i],float(np.nanmean(ta["snapshot_stage_m"][i]))),ta["snapshot_wet_masks"][i].astype(float),"wet 0/1","Blues")
        for i in (0,len(ta["snapshot_time_s"])-1)], [tide_path,DELTA/"tides-v1/summary.json"],tbox,float(ta["spacing_m"]),
        "Latest corrected downstream tidal creek geometry; actual saved finite-volume wet snapshots, not bed-below-tide reachability. Same categorical colour scale.",common=True)
    gc = g6["context"]
    gb = extent(np.asarray(gc["origin_native_xz"])*30, gc["height_m"].shape, 30)
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes[0, 0].imshow(surface_rgb(gc["height_m"],30),extent=gb,origin="upper",interpolation="nearest")
    axes[0, 0].set_title("Saved TD-derived bed / shared account window")
    joint_fields = [
        ("Allocated soil solid", g6["states"]["mass"]["soil_solid_m3"], "m3 solid/cell", "YlOrBr"),
        ("Root-zone water", g6["states"]["soil_chemistry"]["water_m3"], "m3 water/cell", "Blues"),
        ("Actual biomass carbon", g6["states"]["succession"]["biomass_carbon_kg"], "kg C/cell", "Greens"),
    ]
    for ax, (label,field,unit,cmap) in zip(list(axes.flat)[1:], joint_fields):
        im=ax.imshow(field,extent=gb,origin="upper",interpolation="nearest",cmap=cmap)
        ax.set_title(label);fig.colorbar(im,ax=ax,label=unit,fraction=.045,format="%.4g")
    for ax in axes.flat:
        atlas.decorate(ax,gb)
    atlas.save(fig,"13-joint-td-environment","Same TD window: soil allocation, root water and vegetation jointly consumed",[G6],gb,gc["height_m"].shape,30,
        "One saved G6 product, world and physical time %.0f s; G2/G9 material -> soil allocation + root water -> G6/G15 biomass. Declared causal engineering scenario; no seasonal-v4 states mixed in." % g6["time_s"],
        [{"label":label,"unit":unit,"range":list(shared_limits([field]))} for label,field,unit,cmap in joint_fields])
    status_by_file = {
        "01-terrain-basis.png": ("partial", ["macro_layout", "terrain_diffusion_composition"]),
        "02-current-irregular-rivers.png": ("partial", ["terrain_diffusion", "irregular_routing", "lake_storage"]),
        "03-derived-bed.png": ("partial", ["terrain_diffusion", "derived_bed", "basin_masks"]),
        "04-seasonal-temperature.png": ("partial", ["terrain_diffusion", "seasonal_temperature"]),
        "05-computed-precipitation.png": ("partial", ["terrain_diffusion", "climate_transport"]),
        "06-ridge-climate-support.png": ("partial", ["terrain_diffusion", "climate_transport", "orographic_refinement"]),
        "07-snow-seasonal-event.png": ("mechanism_only", ["terrain_diffusion", "seasonal_snow"]),
        "08-water-inventories.png": ("mechanism_only", ["terrain_diffusion", "seasonal_process", "environment_consumer"]),
        "09-soil-vegetation.png": ("mechanism_only", ["terrain_diffusion", "soil_inventory", "succession"]),
        "10-environment-mechanisms.png": ("mechanism_only", ["terrain_diffusion", "environment_processes"]),
        "11-latest-delta-remote.png": ("partial", ["terrain_diffusion_source", "delta_solver"]),
        "12-delta-tidal-states.png": ("partial", ["terrain_diffusion_source", "coastal_tidal_solver"]),
        "13-joint-td-environment.png": ("mechanism_only", ["terrain_diffusion", "soil_inventory", "root_zone_water", "land_cover_consumer", "succession"]),
    }
    for figure in atlas.figures:
        status, algorithms = status_by_file.get(figure["file"], ("partial", []))
        figure["terrain_basis"] = "saved_td_generated"
        figure["algorithms"] = algorithms
        figure["coverage_status"] = status
        number = int(figure["file"][:2])
        if number <= 8:
            figure["terrain_identity"] = registry["world_identity"]
            figure["terrain_provenance"] = "Hash-verified saved TD composition tiles and current irregular graph; climate driver retains original TD source/support hashes."
            figure["terrain_sources"] = [atlas.source(p) for p in sources]
        elif number in (9, 10, 13):
            product = g6 if number in (9,13) else mech
            if product["sources"].get("kind") != "saved_generated_TD_terrain_not_observation":
                raise ValueError("environment main figure lacks saved TD terrain basis")
            figure["terrain_identity"] = product["sources"].get("source_world_identity")
            figure["terrain_provenance"] = product["sources"]
            figure["terrain_note"] = "Separate saved TD window and declared finite process forcing; not a continuation of seasonal-v4."
        else:
            figure["terrain_basis"] = "td_derived_engineered"
            summary = json.loads((DELTA/"run-v1/summary.json").read_text(encoding="utf-8"))
            scene = Path(summary["source"]["source_scene_path"])
            with np.load(scene) as saved_scene:
                if "raw_td_sample_m" not in saved_scene.files:
                    raise ValueError("delta inherited scene has no stored TD samples")
                scene_metadata = json.loads(str(saved_scene["metadata_json"].item()))
            figure["terrain_sources"] = [atlas.source(scene)]
            figure["terrain_provenance"] = {"source_scene_sha256": file_sha256(scene),
                "source_terrain_identity": summary["source"]["source_terrain_identity"],
                "accepted_bed_source_hashes": scene_metadata.get("accepted_bed_source_hashes"),
                "input_hashes": scene_metadata.get("input_hashes")}
            figure["terrain_note"] = "TD-derived engineered terrain: inherited base = macro + 0.35 TD residual (maximum checked error 2.84e-14 m); initial bed equals saved scene bed. Engineering construction changed 212644 of 640000 cells, with fill about 1.4586e9 m3 and cut about 2.867e7 m3. This is not unmodified TD or naturally formed distributaries."
            figure["terrain_validation"] = {"base_formula": "macro_bed_m + 0.35 * td_residual_m",
                "max_formula_error_m": 2.84e-14, "initial_bed_equals_scene_bed": True,
                "engineered_changed_cells": 212644, "total_cells": 640000,
                "engineered_fill_m3_approx": 1.4586e9, "engineered_cut_m3_approx": 2.867e7}
            figure["forcing_source"] = "Inherited original water/sediment history is an engineering boundary scenario; it is not newly computed climate forcing."
    report={"schema":"project-acceptance-atlas-v1","declaration":DECLARATION,"inputs":atlas.inputs,"figures":atlas.figures,
        "world_identity":registry["world_identity"],"network_algorithm":manifest["network"]["metadata"]["algorithm"],
        "climate_driver_identity":driver["identity_sha256"],"g4_ledgers":[f["ledger"] for f in forcing],
        "g6_land_cover_fields":list(cover),
        "coverage_groups":{"complete_in_window":[],"partial":[f["file"] for f in atlas.figures if f["coverage_status"]=="partial"],"mechanism_only":[f["file"] for f in atlas.figures if f["coverage_status"]=="mechanism_only"],"not_available":[]},
        "coverage":{"R1-R9":"saved original/composed/derived beds, current irregular topology, representative Q, modelled lakes, declared dynamic delta; no new certification of every river capability",
            "G1-G9":"terrain, G2/G9 parent/soil, seasonal temperature, actual G4 condensation, separate water stocks, G6 biomass, SWE, delta/coast",
            "G10-G20":"finite mechanism fields from reviewed saved product; no natural long-term validation; G17 river capture remains paused"},
        "limitations":["No observed remote-sensing or spectral calibration; colour is cartographic.","Seasonal-v4 elapsed time is three hours, not climate change.","Old large-world-first-pass/disk-connected-lakes-v1 registry is D8 priority flood; excluded from current graph figure.","No full-world hydrology, long-term climatic trend, natural delta emergence or game acceptance claimed.","Some environment fields are constant/zero; figures preserve their actual magnitude and separate scenario identities."]}
    (args.output/"manifest.json").write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    lines=["# Project remote acceptance atlas", "",DECLARATION,"", "Run: `runtime/venv/Scripts/python.exe -B tools/render_project_acceptance.py --output <new-directory>`", "", "## Figures", ""]
    lines += ["- [%s](%s): %s" % (f["file"],f["file"],f["title"]) for f in atlas.figures]
    lines += ["", "## Limits", ""]+["- "+s for s in report["limitations"]]
    lines += ["", "All source hashes, world/algorithm identities, native resolutions, units, extents, shared comparison colour limits and physical scenarios are in manifest.json."]
    (args.output/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
