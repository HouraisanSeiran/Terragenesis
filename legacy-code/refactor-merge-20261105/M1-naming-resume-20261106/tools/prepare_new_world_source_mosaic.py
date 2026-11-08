"""Plan or serially generate the fixed 50 km source and terrain."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psutil
import numpy as np
from terrain_pipeline import td_source as mosaic
from terrain_pipeline import td_source as terrain


def save_preview(manifest, arrays, output):
    """Render the exact requested bounds from the authenticated raw bed."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    raw = arrays["raw_td_m"]
    x0, z0 = manifest["origin_native_xz"]
    extent = ((x0 - 0.5) * 30, (x0 + raw.shape[1] - 0.5) * 30,
              (z0 + raw.shape[0] - 0.5) * 30, (z0 - 0.5) * 30)
    fig, ax = plt.subplots(figsize=(9, 8), constrained_layout=True)
    image = ax.imshow(raw, extent=extent, origin="upper", cmap="terrain", interpolation="nearest")
    ax.set_xlim(-26170, 23830)
    ax.set_ylim(30010, -19990)
    ax.set_xlabel("World X (m, east)")
    ax.set_ylabel("World Z (m, south)")
    ax.set_title("Raw TD elevation, 50 km display; sea datum 0 m")
    fig.colorbar(image, ax=ax, label="Elevation (m)")
    fig.savefig(output, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--generate", action="store_true")
    parser.add_argument("--root", default=".scratch/river-upgrade-20261101/source50-pages")
    parser.add_argument("--mosaic", default=".scratch/river-upgrade-20261101/source50-mosaic")
    parser.add_argument("--terrain", default=".scratch/river-upgrade-20261101/terrain-v3")
    args = parser.parse_args()
    try:
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True, timeout=5).stdout.splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError, IndexError):
        gpu = "unavailable"
    report = {"mode": "generate" if args.generate else "dry-run", "host_available_bytes": psutil.virtual_memory().available,
              "host_required_bytes": 4096 * 2**20 + 300_000_000 + 1280**2 * 160,
              "gpu_free_mib": gpu, "gpu_required_mib": 4096,
              "disk_free_bytes": shutil.disk_usage(Path(args.root).resolve().parent).free,
              "pages": 16, "side": 1280, "core": 1024, "halo": 128}
    print(json.dumps(report, indent=2), flush=True)
    if not args.generate:
        return
    mosaic.prepare_mosaic_pages(args.root, generate=True)
    if Path(args.mosaic).exists():
        m, _ = mosaic.read_mosaic_product(args.mosaic)
    else:
        m, _ = mosaic.assemble(args.root, args.mosaic)
    seams = mosaic.seam_report(args.mosaic)
    Path(args.mosaic).parent.joinpath("source50-seams.json").write_text(json.dumps(seams, indent=2), encoding="utf-8")
    if Path(args.terrain).exists():
        t, terrain_arrays = terrain.read_world_terrain(args.terrain)
        if t["source_identity"] != m["identity"]:
            raise ValueError("existing terrain belongs to another mosaic")
    else:
        t, terrain_arrays = terrain.prepare_world_terrain(args.mosaic, args.terrain, expected_source_identity=m["identity"])
    save_preview(t, terrain_arrays, Path(args.mosaic).parent / "source50-preview.png")
    counts = {name: int(np.count_nonzero(terrain_arrays[name])) for name in ("ocean_mask", "closed_below_sea_mask", "unknown_mask")}
    page_runtime = []
    for page in m["source_paths"]["pages"]:
        record = json.loads((Path(page) / "manifest.json").read_text(encoding="utf-8"))
        page_runtime.append(record["generation"])
    lines = ["# Source 50 real product", "", f"Mosaic identity: `{m['identity']}`  ",
             f"Terrain identity: `{t['identity']}`  ", f"Plate identity: `{m['plate_identity']}`  ",
             f"Origin native x,z: {m['origin_native_xz']}; shape z,x: {m['shape_zx']}; spacing: 30 m.",
             "Exact display bounds X [-26170, 23830], Z [-19990, 30010] m; support X [-48670, 46330], Z [-42490, 52510] m.",
             f"Classification counts: {json.dumps(counts)}.",
             f"Maximum independent overlap difference: {max(s['overlap_max_abs_m'] for s in seams):.9g} m; maximum adjacent core step: {max(s['owner_step_max_abs_m'] for s in seams):.9g} m. See source50-seams.json.",
             f"Worker wall time sum: {sum(p['wall_clock_s'] for p in page_runtime):.2f} s; maximum sampled worker RSS: {max(p['peak_child_rss_mib'] for p in page_runtime):.2f} MiB; maximum allocated GPU: {max(p['allocated_peak_mib'] for p in page_runtime):.2f} MiB; maximum reserved GPU: {max(p['reserved_peak_mib'] for p in page_runtime):.2f} MiB.",
             "Ocean inherits a finite macro boundary condition; it is not global hydrodynamic certification. Frozen core ownership provides consistent reads, not identical independent inference. No river, catchment, delta or morphology acceptance is claimed.", ""]
    Path(args.mosaic).parent.joinpath("source50-report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"mosaic_identity": m["identity"], "terrain_identity": t["identity"]}, indent=2))


if __name__ == "__main__":
    main()
