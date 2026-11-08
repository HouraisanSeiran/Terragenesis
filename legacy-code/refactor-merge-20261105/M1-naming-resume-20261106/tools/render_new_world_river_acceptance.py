"""Render an authenticated new-world terrain baseline, without inferred water."""
import argparse
import ctypes
import gc
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.td_source import read_world_terrain as read_product

BOUNDS = (-26170, 23830, -19990, 30010)
EXPECTED = "c751a09a6f02e8c336b6b9b8fb4b11b5dc67386e9a8470b0b1d90858bf1ffb72"


def crop_slices(manifest, bounds=BOUNDS):
    spacing = manifest["spacing_m"]
    ox, oz = manifest["origin_native_xz"]
    height, width = manifest["shape_zx"]
    xmin, xmax, zmin, zmax = bounds
    if not (xmin < xmax and zmin < zmax and spacing > 0):
        raise ValueError("invalid bounds or spacing")
    # Include every cell intersecting the rectangle; plotting clips at exact bounds.
    x0 = math.floor(xmin / spacing - ox + 0.5)
    x1 = math.ceil(xmax / spacing - ox + 0.5)
    z0 = math.floor(zmin / spacing - oz + 0.5)
    z1 = math.ceil(zmax / spacing - oz + 0.5)
    if x0 < 0 or z0 < 0 or x1 > width or z1 > height:
        raise ValueError("display bounds outside terrain")
    extent = ((ox + x0 - .5) * spacing, (ox + x1 - .5) * spacing,
              (oz + z1 - .5) * spacing, (oz + z0 - .5) * spacing)
    return (slice(z0, z1), slice(x0, x1)), extent


def colorize(bed, ocean, unknown, valid, spacing):
    """Elevation tone and multidirectional relief; mask alone identifies ocean."""
    dz, dx = np.gradient(bed, float(spacing))
    norm = np.sqrt(1 + dx * dx + dz * dz)
    shade = np.zeros(bed.shape, dtype=np.float32)
    for azimuth in (45, 135, 225, 315):
        a = np.deg2rad(azimuth)
        # Azimuth clockwise from north, Z points south.
        shade += np.maximum(0, (-dx * np.sin(a) + dz * np.cos(a)) * .70710678 + .70710678) / norm / 4
    del dx, dz, norm
    t = np.clip((bed + 200) / 2600, 0, 1)
    rgb = np.empty((*bed.shape, 3), dtype=np.float32)
    for i, (low, high) in enumerate(zip((.40, .43, .36), (.78, .75, .67))):
        rgb[..., i] = (low + (high - low) * t) * (.48 + .65 * shade)
    rgb[ocean] = (.12, .28, .36)
    rgb[unknown | ~valid] = (.64, .32, .60)
    return np.clip(rgb, 0, 1)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def available_memory():
    if sys.platform == "win32":
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in ("total_phys", "avail_phys", "total_page", "avail_page", "total_virtual", "avail_virtual", "avail_extended")]
        s = Status()
        s.length = ctypes.sizeof(s)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
            raise OSError("cannot measure available memory")
        return s.avail_phys
    return os_available_memory()


def os_available_memory():
    import os
    return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")


def render(source, output, expected_identity, base_only, product=None):
    if not base_only:
        raise ValueError("--base-only is required until authenticated native water and delta schemas are available")
    if product is not None:
        raise ValueError("native product reader unavailable: verified terrain, classification, coordinates, physical time and forcing bindings are required")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    free = available_memory()
    minimum = 1800 * 1024 * 1024
    if free < minimum:
        raise MemoryError(f"cold-read preflight needs {minimum} available bytes; found {free}")
    manifest, arrays = read_product(source, expected_identity=expected_identity)
    slices, extent = crop_slices(manifest)
    crop = {name: np.array(arrays[name][slices], copy=True) for name in ("bed_m", "ocean_mask", "unknown_mask", "valid_mask", "closed_below_sea_mask")}
    del arrays
    gc.collect()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    rgb = colorize(crop["bed_m"], crop["ocean_mask"], crop["unknown_mask"], crop["valid_mask"], manifest["spacing_m"])
    fig, ax = plt.subplots(figsize=(11, 11.8), layout="constrained")
    ax.imshow(rgb, extent=extent, origin="upper", interpolation="nearest")
    ax.set_xlim(BOUNDS[0], BOUNDS[1]); ax.set_ylim(BOUNDS[3], BOUNDS[2])
    ax.set_xlabel("X east (m)"); ax.set_ylabel("Z south (m)")
    ax.set_title("Terrain baseline: river network and delta pending\nRemote-sensing-style model rendering | not satellite imagery", fontsize=13)
    ax.text(.02, .97, "N ↑", transform=ax.transAxes, color="white", fontsize=13, va="top", bbox=dict(facecolor="black", alpha=.6, edgecolor="none"))
    ax.plot([-23500, -13500], [27000, 27000], color="white", lw=4)
    ax.text(-18500, 26000, "10 km", color="white", ha="center", fontsize=10, bbox=dict(facecolor="black", alpha=.55, edgecolor="none"))
    ax.legend(handles=[Patch(color=(.49,.50,.42), label="Elevation tone (not observed vegetation)"), Patch(color=(.12,.28,.36), label="Authoritative finite-domain ocean mask"), Patch(color=(.64,.32,.60), label="Unknown / invalid")], loc="lower right", fontsize=8, framealpha=.9)
    fig.text(.5, .015, "Seed 20261020 | TD terrain c751a09a6f02… | 30 m cells | time / forcing: not applicable\nNo native river, lake or delta state; closed below-datum land is not water. Ocean boundary is inherited, not global certification.", ha="center", fontsize=8)
    output.mkdir(parents=True)
    figure = output / "terrain-baseline.png"
    fig.savefig(figure, dpi=180, facecolor="white")
    plt.close(fig)
    provenance = {"schema": "new-world-river-render-baseline-v1", "completion": False, "base_only": True,
        "terrain_basis": "authenticated Terrain Diffusion terrain-v3", "terrain_identity": manifest["identity"], "source_identity": manifest["source_identity"], "plate_identity": manifest["plate_identity"], "world_seed": manifest["world_seed"],
        "source_path": str(Path(source).resolve()), "source_manifest_sha256": sha256(Path(source) / "manifest.json"), "source_file_sha256": manifest["files"], "renderer_sha256": sha256(Path(__file__)),
        "figure": figure.name, "figure_sha256": sha256(figure), "bounds_xz_m": list(BOUNDS), "cell_spacing_m": manifest["spacing_m"], "cell_extent_xz_m": list(extent), "orientation": "north up, X east, Z south; cell centres",
        "time": "not applicable to static terrain", "forcing": "not applicable; native water not supplied", "algorithms": ["authenticated cold read", "elevation tone", "four-direction hillshade"], "hillshade": {"azimuth_degrees": [45,135,225,315], "altitude_degrees": 45, "vertical_exaggeration": 1},
        "coverage_status": {"terrain": "complete_in_window", "ocean_classification": "complete_in_window", "river_lake_water": "not_available", "network": "not_available", "delta": "not_available"},
        "known_unknowns": ["ocean mask inherits finite macro boundary; not global hydrodynamic certification", "closed below-datum cells are not classified as water", "surface tone is not observed vegetation or material", "native water and delta are not available", "independent source page overlap differences are documented in source50-report.md"],
        "window_cell_counts": {name: int(np.count_nonzero(crop[name])) for name in ("ocean_mask", "unknown_mask", "valid_mask", "closed_below_sea_mask")}, "available_memory_preflight_bytes": free, "minimum_memory_preflight_bytes": minimum}
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source"); parser.add_argument("output")
    parser.add_argument("--expected-terrain-identity", required=True)
    parser.add_argument("--base-only", action="store_true")
    parser.add_argument("--native-product", help="reserved; unsupported products are rejected")
    args = parser.parse_args()
    render(args.source, args.output, args.expected_terrain_identity, args.base_only, args.native_product)


if __name__ == "__main__":
    main()
