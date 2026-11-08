"""Independent backend identity, same frozen control-flow and full-run certificates."""
import json
from pathlib import Path
import sys
import types
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import verify_regional_hydraulics_full as reference_runner
from terrain_pipeline.surface_hydraulics import advance_accelerated_surface
from terrain_pipeline.common_infra import file_sha256, publish_bytes

START_HASHES = {}


def accelerated_budget():
    return replace(reference_runner.SurfaceBudget(), max_wall_s=21600., max_substeps=2000000,
        max_face_evaluations=300000000000)


def publish_backend(path, payload):
    if Path(path).name == "predeclared.json":
        declaration = json.loads(payload)
        declaration["execution_backend"] = "numba_face_limiter_fastmath_false_v1_reference_control_flow"
        declaration["scope"] = "new_independent_from_initial_run_not_resume_not_old_budget_extension"
        declaration["source_hashes"]["terrain_pipeline/regional_surface_hydraulics_accelerated.py"] = file_sha256(ROOT / "terrain_pipeline/regional_surface_hydraulics_accelerated.py")
        declaration["source_hashes"]["tools/verify_regional_hydraulics_full.py"] = file_sha256(Path(reference_runner.__file__))
        declaration["source_hashes"].update(START_HASHES)
        payload = json.dumps(declaration, indent=2).encode("ascii")
    elif Path(path).name == "manifest.json":
        manifest = json.loads(payload)
        manifest["source_hashes"].update(START_HASHES)
        manifest["source_unchanged"] = manifest["source_unchanged"] and all(file_sha256(ROOT / name) == digest for name, digest in START_HASHES.items())
        payload = json.dumps(manifest, indent=2).encode("ascii")
    publish_bytes(path, payload)


def main():
    for path in (Path(__file__), Path(reference_runner.__file__), ROOT / "terrain_pipeline/regional_surface_hydraulics.py",
                 ROOT / "terrain_pipeline/regional_surface_hydraulics_accelerated.py",
                 ROOT / "terrain_pipeline/regional_surface_source.py", ROOT / "terrain_pipeline/regional_surface_forcing.py",
                 ROOT / "terrain_pipeline/common_infra.py"):
        START_HASHES[str(path.relative_to(ROOT))] = file_sha256(path)
    namespace = dict(reference_runner.main.__globals__)
    namespace["advance_inertial_surface"] = advance_accelerated_surface
    namespace["__file__"] = __file__
    namespace["publish_bytes"] = publish_backend
    namespace["SurfaceBudget"] = accelerated_budget
    run = types.FunctionType(reference_runner.main.__code__, namespace, "accelerated_full")
    run()


if __name__ == "__main__":
    main()
