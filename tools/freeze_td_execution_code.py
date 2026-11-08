"""Freeze the actual Numba storage kernel for an existing result package.

This is metadata-only. It does not load a basin, import the refinement module,
or advance a solver, so it is safe for cold-read acceptance.
"""

import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'terrain_pipeline/basin_storage.py'


def freeze(output, *, profile="v2-full-refinement-6e9-v1"):
    source = SOURCE.read_bytes()
    manifest = {
        "schema": "td-basin-execution-code-v1",
        "execution_source": {
            "path": 'terrain_pipeline/basin_storage.py',
            "sha256": hashlib.sha256(source).hexdigest(),
            "source_utf8": source.decode("utf-8"),
        },
        "profile": {
            "name": profile,
            "algorithm": "D4-analytic-face-Strang-splitting-v2",
            "max_work_face_steps": 6000000000,
            "same_g_face_conductance_and_rain_parameters": True,
        },
        "runtime": {
            "python": platform.python_version(),
            "numba": version("numba"),
            "numpy": version("numpy"),
            "platform": platform.platform(),
        },
        "cold_read": {
            "requires": ["numpy", "numba", 'terrain_pipeline/basin_storage.py'],
            "validator_mode": "read JSON/NPZ metadata and SHA only; no module import, JIT, or solver advancement",
            "jit_on_cold_read": False,
            "advancement_on_cold_read": False,
        },
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", default="v2-full-refinement-6e9-v1")
    args = parser.parse_args()
    manifest = freeze(args.output, profile=args.profile)
    print(json.dumps({"output": str(args.output.resolve()), "source_sha256": manifest["execution_source"]["sha256"],
                      "numba": manifest["runtime"]["numba"], "profile": manifest["profile"]["name"]}, ensure_ascii=False))
