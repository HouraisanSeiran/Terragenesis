"""Fresh TD source for a fixed continent, with an explicit coastal derivative."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
from scipy.ndimage import gaussian_filter

from diffusion.geographic_noise import field

WORLD_SEED = 20261020
ALGORITHM = "single-continent-coastal-td-v1"
VIEW_BOUNDS_M = (126000.0, -32040.0, 190000.0, 31960.0)
NATIVE_SPACING_M = 30.0
# Climate ridge queries reach 1.5 * 15km; retain their interpolation cell plus
# the finite composition filter outside that complete query support.
CLIMATE_QUERY_SUPPORT_M = 22500.0
HALO_CELLS = 849
FILTER_SIGMA_CELLS = 24.0
FILTER_RADIUS_CELLS = 96
TD_CLIMATE_CHANNELS = ["temperature_mean_c", "temperature_std_c_times_100",
                       "precipitation_mean_mm_year", "precipitation_cv_times_100",
                       "temperature_elevation_beta_c_per_m"]


def array_sha256(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def terrain_identity(plan, paths, backend_identity, composition):
    """Content identity excludes execution timings, host memory and file paths."""
    record = {"algorithm": ALGORITHM, "world_seed": plan["world_seed"],
              "requested_view_bounds_m": plan["requested_view_bounds_m"],
              "origin_native_xz": plan["origin_native_xz"],
              "shape_native_zx": plan["shape_native_zx"],
              "source_origin_native_xz": plan["source_origin_native_xz"],
              "source_shape_zx": plan["source_shape_zx"],
              "native_spacing_m": plan["native_spacing_m"], "spacing_m": plan["spacing_m"],
              "backend_identity": backend_identity, "composition": composition,
              "macro_conditioning": plan["macro_conditioning"],
              "source_array_sha256": {name: source["array_sha256"] for name, source in paths.items()}}
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def overlap_comparison(raw, covered, tile, request, origin_xz):
    """Compare new inference halo to prior owned cores at identical coordinates."""
    ox, oz = origin_xz
    tx, tz, size = request["native_x"], request["native_z"], request["size"]
    x0, z0 = max(ox, tx), max(oz, tz)
    x1, z1 = min(ox + raw.shape[1], tx + size), min(oz + raw.shape[0], tz + size)
    selection = np.s_[z0 - oz:z1 - oz, x0 - ox:x1 - ox]
    known = covered[selection]
    count = int(np.count_nonzero(known))
    result = {"count": count, "maximum_absolute_difference_m": 0.0,
              "rms_difference_m": 0.0, "absolute_difference_quantiles_m": [0.0, 0.0, 0.0],
              "quantiles": [.5, .9, .99]}
    if count:
        incoming = tile[z0 - tz:z1 - tz, x0 - tx:x1 - tx]
        delta = incoming[known].astype(np.float64) - raw[selection][known]
        result.update(maximum_absolute_difference_m=float(np.max(np.abs(delta))),
                      rms_difference_m=float(np.sqrt(np.mean(delta * delta))),
                      absolute_difference_quantiles_m=np.quantile(np.abs(delta), [.5, .9, .99]).tolist())
    return result


def macro_fields(x_m, z_m, seed=WORLD_SEED):
    """Sample the same 500 km continent at any absolute metre coordinates.

    A positive polar radius gives exactly one star-shaped landmass, without
    enclosed macro lakes. The eastern orogen includes saddles and a coastal
    piedmont; the acceptance window crosses this orogen and the east coast.
    """
    x, z = np.broadcast_arrays(np.asarray(x_m, dtype=np.float64),
                               np.asarray(z_m, dtype=np.float64))
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("finite world coordinates required")
    angle = np.arctan2(z / 0.93, x)
    radius = np.hypot(x, z / 0.93)
    phase = (int(seed) % 997) / 997.0 * 2 * np.pi
    coast_radius = (173000.0 + 11000.0 * np.sin(3 * angle + phase)
                    + 6500.0 * np.sin(7 * angle - .7)
                    + 2400.0 * np.sin(13 * angle + .4))
    inland = coast_radius - radius
    broad = field(x / 12000.0, z / 12000.0, seed, 1901, ((5, 1), (2, .35)))
    ridge_axis = 135000.0 + 6500.0 * np.sin(z / 37000.0) + 2500.0 * np.sin(z / 11000.0)
    ridge = np.exp(-((x - ridge_axis) / 15500.0) ** 2)
    saddles = .68 + .24 * np.sin(z / 14500.0 + .4) + .08 * np.cos(z / 4700.0)
    land_taper = np.clip(inland / 14000.0, 0, 1)
    interior = 180.0 + 480.0 * np.clip(inland / 100000.0, 0, 1)
    elevation = np.where(inland > 0,
        land_taper * (interior + 2100.0 * ridge * saddles + 180.0 * broad),
        -1400.0 * np.tanh(-inland / 23000.0))
    temperature = 16.0 - .0065 * np.maximum(elevation, 0) - z / 65000.0
    precipitation = np.clip(1100.0 + 500.0 * ridge + 200.0 * broad, 400, 2400)
    return {"elevation_m": elevation.astype(np.float32),
            "ocean_mask": inland <= 0, "inland_distance_m": inland.astype(np.float32),
            "temperature_c": temperature.astype(np.float32),
            "precipitation_mm_year": precipitation.astype(np.float32)}


def make_acceptance_map_factory(seed, config):
    """Use existing physical climate noise and replace the elevation condition."""
    from diffusion.geography_physical import make_physical_map_factory
    physical = make_physical_map_factory(seed, config)

    def sample_raw(x1, z1, x2, z2):
        values = physical.sample_raw(x1, z1, x2, z2)
        x = np.arange(x1, x2, dtype=np.float64)[None, :] * config.conditioning_spacing_m
        z = np.arange(z1, z2, dtype=np.float64)[:, None] * config.conditioning_spacing_m
        macro = macro_fields(x, z, seed)
        values[0] = macro["elevation_m"]
        values[1] = macro["temperature_c"]
        values[3] = macro["precipitation_mm_year"]
        return values

    def sample_full(x1, z1, x2, z2):
        import torch
        values = physical.finalize(sample_raw(x1, z1, x2, z2))
        values[0] = np.sign(values[0]) * np.sqrt(np.abs(values[0]))
        return torch.from_numpy(values)

    sample_full.sample_raw = sample_raw
    sample_full.finalize = physical.finalize
    return sample_full


def preparation_plan(bounds_m=VIEW_BOUNDS_M):
    x0, z0, x1, z1 = map(float, bounds_m)
    if not all(math.isfinite(v) for v in bounds_m) or x1 <= x0 or z1 <= z0:
        raise ValueError("finite increasing view bounds required")
    # Anchor three-cell blocks globally: coarse centres are 30 mod 90 metres.
    origin = [int(math.floor((x0 + 15) / 90)) * 3,
              int(math.floor((z0 + 15) / 90)) * 3]
    columns = int(math.ceil((x1 - (origin[0] * 30 - 15)) / 90)) * 3
    rows = int(math.ceil((z1 - (origin[1] * 30 - 15)) / 90)) * 3
    return {"algorithm": ALGORITHM, "world_seed": WORLD_SEED,
            "world_frame_bounds_m": [-250000, -250000, 250000, 250000],
            "requested_view_bounds_m": [x0, z0, x1, z1],
            "origin_native_xz": origin, "shape_native_zx": [rows, columns],
            "source_origin_native_xz": [v - HALO_CELLS for v in origin],
            "source_shape_zx": [rows + 2 * HALO_CELLS, columns + 2 * HALO_CELLS],
            "spacing_m": 90.0, "native_spacing_m": 30.0, "halo_native_cells": HALO_CELLS,
            "source_support": {"climate_orographic_scale_m": 15000.0,
                "climate_max_axis_query_offset_m": CLIMATE_QUERY_SUPPORT_M,
                "interpolation_support_m": 30.0,
                "composition_filter_support_m": FILTER_RADIUS_CELLS * 30.0,
                "total_source_halo_m": HALO_CELLS * 30.0,
                "composition_valid_margin_native_cells": FILTER_RADIUS_CELLS,
                "inference_tile_halo_native_cells": 96},
            "origin_xz_m": [origin[0] * 30 + 30, origin[1] * 30 + 30],
            "output_cell_bounds_m": [origin[0] * 30 - 15, origin[1] * 30 - 15,
                                     origin[0] * 30 - 15 + columns * 30,
                                     origin[1] * 30 - 15 + rows * 30],
            "coordinate_convention": "x east, z south; arrays [z,x]; origins are cell centres",
            "macro_conditioning": {
                "formula": "polar star-shaped continent; inland=coast_radius-hypot(x,z/0.93); coastal taper times uplift plus eastern Gaussian orogen",
                "coast_radius_m": 173000, "polar_radius_harmonics_m": [11000, 6500, 2400],
                "polar_radius_frequencies": [3, 7, 13], "north_south_aspect": .93,
                "coastal_land_taper_m": 14000, "ocean_tanh_depth_m": 1400,
                "ocean_tanh_scale_m": 23000, "orogen_axis_x_m": 135000,
                "orogen_width_m": 15500, "orogen_relief_m": 2100,
                "noise": "existing diffusion.geographic_noise.field, purpose1901, scale12000m",
                "condition_channels": "elevation, mean temperature and precipitation replaced; physical temperature variability and precipitation CV retained",
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "lake_status": "no macro lakes; hydrological lakes are not yet modelled",
            "gpu_policy": {"allocator_cap_gib": 4, "max_request_side": 1337,
                           "processes": 1, "inference": "explicit --generate only"}}


def area_mean_3(array):
    """Conservative native30m to90m cell area average, including extra channels."""
    values = np.asarray(array)
    rows, columns = values.shape[-2:]
    if rows % 3 or columns % 3:
        raise ValueError("native shape must be divisible by three")
    return values.reshape(*values.shape[:-2], rows // 3, 3, columns // 3, 3).mean(
        axis=(-3, -1), dtype=np.float64).astype(np.float32)


def compose_native(raw, plan):
    """Keep TD high frequencies and 65% TD low frequencies, constrain shore sign."""
    raw = np.asarray(raw, dtype=np.float32)
    if list(raw.shape) != plan["source_shape_zx"] or not np.isfinite(raw).all():
        raise ValueError("finite TD source matching the prepared shape required")
    x0, z0 = plan["source_origin_native_xz"]
    x = (x0 + np.arange(raw.shape[1]))[None, :] * 30.0
    z = (z0 + np.arange(raw.shape[0]))[:, None] * 30.0
    fields = macro_fields(x, z)
    macro = fields["elevation_m"]
    low = gaussian_filter(raw, sigma=FILTER_SIGMA_CELLS,
                          radius=FILTER_RADIUS_CELLS, mode="nearest")
    # Subtract the same linear low-pass of the macro, not a window statistic.
    macro_low = gaussian_filter(macro, sigma=FILTER_SIGMA_CELLS,
                                radius=FILTER_RADIUS_CELLS, mode="nearest")
    detail = raw - low
    correction = detail + .65 * (low - macro_low)
    limit = .85 * np.abs(macro)
    composed = macro + np.clip(correction, -limit, limit)
    return composed.astype(np.float32), fields


def tile_requests(shape_zx, origin_xz, overlap=96):
    """Absolute anchored cores: requested extent and order never change TD calls."""
    rows, columns = shape_zx
    step = 1024
    ox, oz = origin_xz
    for core_z in range((oz // step) * step, oz + rows, step):
        for core_x in range((ox // step) * step, ox + columns, step):
            x0, z0 = max(ox, core_x), max(oz, core_z)
            x1, z1 = min(ox + columns, core_x + step), min(oz + rows, core_z + step)
            yield {"row": z0 - oz, "column": x0 - ox,
                   "rows": z1 - z0, "columns": x1 - x0,
                   "tile_row": z0 - core_z + overlap, "tile_column": x0 - core_x + overlap,
                   "native_x": core_x - overlap, "native_z": core_z - overlap,
                   "size": step + 2 * overlap}


def _backend(config):
    from diffusion.physical_backend import PhysicalTerrainDiffusionBackend
    from diffusion.paths import ROOT, inside

    class AcceptanceBackend(PhysicalTerrainDiffusionBackend):
        def __init__(self):
            super().__init__(config)
            self.metadata = dict(self.metadata, algorithm=ALGORITHM,
                adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                conditioning="absolute-coordinate single continent, independent fresh TD")
            self.identity = hashlib.sha256(json.dumps(self.metadata, sort_keys=True).encode()).hexdigest()

        def load(self):
            if self.pipeline is not None:
                return
            model_config = json.loads((inside(config.model_dir) / "config.json").read_text(encoding="utf-8"))
            native = model_config["native_resolution"]
            if (native != config.native_resolution_m or
                    native * model_config["latent_compression"] * 32 != config.conditioning_spacing_m):
                raise ValueError("physical checkpoint native/coarse metre grid mismatch")
            upstream = json.loads((ROOT / "runtime/upstream.json").read_text(encoding="utf-8"))
            sys.path.insert(0, str(inside(upstream["source"])))
            import torch
            from terrain_diffusion.inference.world_pipeline import WorldPipeline
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA required for genuine TD; no fallback")
            torch.cuda.set_per_process_memory_fraction(4 * 2**30 / torch.cuda.get_device_properties(0).total_memory)
            torch.set_num_threads(2)

            class AcceptancePipeline(WorldPipeline):
                def _init_conditioning(self):
                    self.synthetic_map_factory = make_acceptance_map_factory(int(self.seed), config)

            pipeline = AcceptancePipeline.from_pretrained(str(inside(config.model_dir)), seed=0,
                latents_batch_size=1, torch_compile=False,
                dtype=config.dtype if config.dtype == "fp16" else None,
                caching_strategy="direct", cache_limit=64 * 1024 * 1024,
                cond_snr=list(config.cond_snr))
            try:
                pipeline.to("cuda")
                pipeline.bind()
            except BaseException:
                pipeline.close()
                raise
            self.pipeline = pipeline

    return AcceptanceBackend()


def generate_product(output, plan=None, backend=None):
    """Generate genuine native TD in one process and persist source provenance."""
    from diffusion.physical_config import PhysicalGenerationConfig
    import psutil

    plan = preparation_plan() if plan is None else plan
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    backend = _backend(PhysicalGenerationConfig()) if backend is None else backend
    rows, columns = plan["source_shape_zx"]
    halo = plan["halo_native_cells"]
    nr_core, nc_core = plan["shape_native_zx"]
    raw = np.zeros((rows, columns), dtype=np.float32)
    climate = np.zeros((5, nr_core, nc_core), dtype=np.float32)
    covered = np.zeros((rows, columns), dtype=bool)
    records = []
    started = time.perf_counter()
    rss_peak = psutil.Process().memory_info().rss
    try:
        for request in tile_requests((rows, columns), plan["source_origin_native_xz"]):
            print(json.dumps({"stage": "td_request", **request}), flush=True)
            tile, tile_climate, record = backend.generate(WORLD_SEED, request["native_x"],
                                                        request["native_z"], request["size"])
            overlap = overlap_comparison(raw, covered, tile, request, plan["source_origin_native_xz"])
            nr, nc = request["rows"], request["columns"]
            r, c = request["row"], request["column"]
            tr, tc = request["tile_row"], request["tile_column"]
            selection = np.s_[r:r + nr, c:c + nc]
            raw[selection] = tile[tr:tr + nr, tc:tc + nc]
            covered[selection] = True
            cr0, cc0 = max(r, halo), max(c, halo)
            cr1, cc1 = min(r + nr, halo + nr_core), min(c + nc, halo + nc_core)
            if cr1 > cr0 and cc1 > cc0:
                climate[:, cr0 - halo:cr1 - halo, cc0 - halo:cc1 - halo] = tile_climate[
                    :, tr + cr0 - r:tr + cr1 - r, tc + cc0 - c:tc + cc1 - c]
            rss_peak = max(rss_peak, psutil.Process().memory_info().rss)
            records.append({"request": request, "source_metadata": record,
                            "tile_array_sha256": array_sha256(tile), "raw_overlap_comparison": overlap})
    finally:
        backend.close()
    raw = raw.astype(np.float32)
    climate = climate.astype(np.float32)
    composed, fields = compose_native(raw, plan)
    rss_peak = max(rss_peak, psutil.Process().memory_info().rss)
    paths = {}
    for name, array in (("raw_td_30m", raw), ("composed_30m", composed),
                        ("macro_30m", fields["elevation_m"])):
        path = destination / (name + ".npy")
        np.save(path, array, allow_pickle=False)
        paths[name] = {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "array_sha256": array_sha256(array)}
    halo = plan["halo_native_cells"]
    nr, nc = plan["shape_native_zx"]
    crop = np.s_[halo:halo + nr, halo:halo + nc]
    source_metadata = {**plan, "native_source_origin_xz_m": [v * 30 for v in plan["source_origin_native_xz"]],
        "native_source_paths": paths, "tiles": records,
        "climate_base_channels": list(TD_CLIMATE_CHANNELS),
        "runtime_seconds": time.perf_counter() - started, "sampled_peak_rss_bytes": rss_peak,
        "composition": {"detail_gain": 1.0, "low_frequency_td_gain": .65,
            "sigma_native_cells": FILTER_SIGMA_CELLS, "filter_radius_native_cells": FILTER_RADIUS_CELLS,
            "formula": "macro + clip(raw-lowpass(raw)+0.65*(lowpass(raw)-lowpass(macro)), +/-0.85*abs(macro))",
            "coastline": "declared macro sign constrained derivative; not raw TD coastline",
            "tile_assembly": "absolute 1024-cell cores with 96-cell inference halo; trusted core crop, no blending"}}
    source_metadata["terrain_identity"] = terrain_identity(plan, paths, backend.identity,
                                                           source_metadata["composition"])
    source_metadata["raw_overlap_summary"] = {
        "comparison_count": sum(r["raw_overlap_comparison"]["count"] for r in records),
        "maximum_absolute_difference_m": max(r["raw_overlap_comparison"]["maximum_absolute_difference_m"] for r in records),
        "semantics": "new differently located request halo versus already owned absolute core; diagnostic only, cores never overwritten"}
    elevation90 = area_mean_3(composed[crop])
    np.savez_compressed(destination / "terrain90.npz", elevation_m=elevation90,
        raw_td_m=area_mean_3(raw[crop]), macro_elevation_m=area_mean_3(fields["elevation_m"][crop]),
        ocean_mask=elevation90 < 0,
        ocean_area_fraction=area_mean_3(fields["ocean_mask"][crop].astype(np.float32)),
        climate_base=area_mean_3(climate),
        metadata_json=np.asarray(json.dumps(source_metadata, sort_keys=True)))
    (destination / "terrain_metadata.json").write_text(json.dumps(source_metadata, indent=2), encoding="utf-8")
    return source_metadata


def correct_climate_metadata_export(original_directory, corrected_directory):
    """Export unchanged numerical data with the actual TD climate channel names."""
    source = Path(original_directory).resolve()
    destination = Path(corrected_directory).resolve()
    if source == destination:
        raise ValueError("metadata correction requires a separate derived output directory")
    metadata_path = source / "terrain_metadata.json"
    product_path = source / "terrain90.npz"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    upstream = metadata["tiles"][0]["source_metadata"]["upstream"]
    from diffusion.paths import inside
    upstream_path = inside(upstream["source"]) / "terrain_diffusion/inference/world_pipeline.py"
    metadata["metadata_correction"] = {
        "schema": "td-climate-channel-names-correction-v1",
        "reason": "WorldPipeline._compute_climate returns temperature, temperature variability, precipitation, precipitation CV and lapse beta; conditioning elevation is not an output climate channel",
        "original_metadata_path": str(metadata_path),
        "original_metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        "original_product_path": str(product_path),
        "original_product_sha256": hashlib.sha256(product_path.read_bytes()).hexdigest(),
        "original_climate_base_channels": metadata["climate_base_channels"],
        "upstream_source_path": str(upstream_path),
        "upstream_source_sha256": hashlib.sha256(upstream_path.read_bytes()).hexdigest(),
        "upstream_revision": upstream["revision"],
        "upstream_definition": "WorldPipeline._compute_climate lines1413-1463: torch.stack([temp_realistic, coarse_up[3], coarse_up[4], coarse_up[5], beta_up[0]])",
        "correction_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "numerical_arrays": "unchanged; metadata-only derived export; terrain_identity retained",
        "gpu_generation": "not repeated"}
    metadata["climate_base_channels"] = list(TD_CLIMATE_CHANNELS)
    with np.load(product_path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files if name != "metadata_json"}
    destination.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(destination / "terrain90.npz", **arrays,
                        metadata_json=np.asarray(json.dumps(metadata, sort_keys=True)))
    (destination / "terrain_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    with np.load(destination / "terrain90.npz", allow_pickle=False) as corrected:
        if any(not np.array_equal(array, corrected[name]) for name, array in arrays.items()):
            raise RuntimeError("derived climate metadata export changed numerical data")
    return metadata


def write_preview(output, plan=None):
    """CPU-only preview, explicitly labelled macro rather than TD acceptance."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    plan = preparation_plan() if plan is None else plan
    x0, z0, x1, z1 = plan["requested_view_bounds_m"]
    x = np.linspace(x0, x1, 512)[None, :]
    z = np.linspace(z0, z1, 512)[:, None]
    fields = macro_fields(x, z)
    np.savez_compressed(destination / "macro_preview.npz", **fields,
                        metadata_json=np.asarray(json.dumps(plan)))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    whole = np.linspace(-250000, 250000, 512)
    for axis, image, extent in ((axes[0], macro_fields(whole[None, :], whole[:, None])["elevation_m"],
                                [-250, 250, 250, -250]),
                               (axes[1], fields["elevation_m"], [x0 / 1000, x1 / 1000, z1 / 1000, z0 / 1000])):
        axis.imshow(image, cmap="terrain", vmin=-1400, vmax=2400, extent=extent)
        axis.set_xlabel("East (km)")
        axis.set_ylabel("South (km)")
    from matplotlib.patches import Rectangle
    axes[0].add_patch(Rectangle((x0 / 1000, z0 / 1000), (x1 - x0) / 1000,
                                (z1 - z0) / 1000, fill=False, edgecolor="red"))
    fig.suptitle("CPU macro plan only - fresh TD generation pending")
    fig.tight_layout()
    fig.savefig(destination / "macro_preview.png", dpi=140)
    plt.close(fig)
    (destination / "preparation_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan
