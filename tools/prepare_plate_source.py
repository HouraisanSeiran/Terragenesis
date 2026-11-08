"""Explicit experimental plate-conditioned TD entry; never the default source."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path

import psutil

from diffusion.physical_config import PhysicalGenerationConfig
from terrain_pipeline.tectonic import load_product
from terrain_pipeline.tectonic import prepare_plate_source as prepare
from diffusion.plate_td_conditioning import conditioning_footprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--expected-plate-identity", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-dir", default="models/terrain-diffusion-30m")
    parser.add_argument("--origin-x", type=int, required=True)
    parser.add_argument("--origin-z", type=int, required=True)
    parser.add_argument("--side", type=int, required=True)
    parser.add_argument("--compose-coast", action="store_true")
    parser.add_argument("--relief-strength", type=float, default=0.0, help="optional coastal relief strength 0..1 (default 0)")
    parser.add_argument("--generate", action="store_true", help="explicitly run the GPU worker; default is a CPU plan")
    parser.add_argument("--dry-run", action="store_true", help="validate and plan without inference (default)")
    args = parser.parse_args()
    if args.generate and args.dry_run:
        parser.error("--generate and --dry-run are mutually exclusive")
    if not math.isfinite(args.relief_strength) or not 0 <= args.relief_strength <= 1 or (not args.compose_coast and args.relief_strength != 0):
        parser.error("relief strength must be 0..1 and requires --compose-coast when nonzero")
    if args.side < 1 or args.side > 1337 or (args.compose_coast and args.side <= 400):
        parser.error("side must be 1..1337 and coastal side must exceed 400")
    product = load_product(args.source, expected_identity=args.expected_plate_identity)
    if product.manifest["config"]["world_seed"] != 20261020:
        raise ValueError("plate seed mismatch")
    product.sample([args.origin_x * 30., (args.origin_x + args.side - 1) * 30.],
                   [args.origin_z * 30., (args.origin_z + args.side - 1) * 30.], outside="reject")
    footprint = conditioning_footprint((args.origin_x, args.origin_z), args.side)
    product.sample([footprint[0] * 7680., (footprint[2] - 1) * 7680.],
                   [footprint[1] * 7680., (footprint[3] - 1) * 7680.], outside="reject")
    if Path(args.output).exists():
        raise FileExistsError(args.output)
    if not args.generate:
        host = psutil.virtual_memory().available
        gpu_free = None
        try:
            query = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5, check=True)
            gpu_free = int(query.stdout.splitlines()[0].strip())
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass
        plan = {"mode": "dry-run", "origin_native_xz": [args.origin_x, args.origin_z],
                "source_shape_zx": [args.side, args.side], "valid_core_origin_native_xz": [args.origin_x + 200, args.origin_z + 200] if args.compose_coast else None,
                "valid_core_shape_zx": [args.side - 400, args.side - 400] if args.compose_coast else None,
                "conditioning_bounds_half_open_xz": footprint, "relief_strength": args.relief_strength,
                "world_seed": 20261020, "plate_identity": args.expected_plate_identity,
                "host_available_bytes": host, "host_required_bytes": 4096 * 2**20 + 300_000_000 + args.side * args.side * 160,
                "gpu_free_mib": gpu_free, "gpu_worker_cap_mib": 4096,
                "gpu_readiness": "allocator cap; excludes CUDA driver, non-PyTorch allocations and other processes",
                "staging_estimate_bytes": 300_000_000 + args.side * args.side * 160,
                "boundary": "finite reject; bilinear edge interpolation is periodic"}
        print(json.dumps(plan, indent=2))
        return
    manifest, _ = prepare(args.source, args.output, (args.origin_x, args.origin_z), args.side,
                          PhysicalGenerationConfig(model_dir=args.model_dir), compose_coast=args.compose_coast,
                          expected_identity=args.expected_plate_identity, relief_strength=args.relief_strength)
    print(json.dumps({"identity": manifest["identity"], "output": args.output}))


if __name__ == "__main__":
    main()
