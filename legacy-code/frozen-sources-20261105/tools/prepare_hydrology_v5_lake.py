"""Revalidate a saved v5 lake pair using immutable cached TD, without inference."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.hydrology_detail import DetailBudget, derive_detail, file_sha256, load_raw_td, save_detail
from terrain_pipeline.hydrology_planning import load_plan, save_plan, select_development_pair
from terrain_pipeline.hydrology_seasonal import SeasonalConfig, load_seasonal_water_balance, save_seasonal_water_balance, simulate_seasonal_water_balance


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def limit_resources():
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
    kernel.GetProcessAffinityMask.restype = wintypes.BOOL
    kernel.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    kernel.SetProcessAffinityMask.restype = wintypes.BOOL
    kernel.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.SetPriorityClass.restype = wintypes.BOOL
    process = kernel.GetCurrentProcess()
    available = ctypes.c_size_t()
    system = ctypes.c_size_t()
    if not kernel.GetProcessAffinityMask(process, ctypes.byref(available), ctypes.byref(system)):
        raise ctypes.WinError(ctypes.get_last_error())
    cpus = [1 << index for index in range(available.value.bit_length()) if available.value & (1 << index)][:2]
    if not kernel.SetProcessAffinityMask(process, ctypes.c_size_t(sum(cpus))):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.SetPriorityClass(process, 0x4000):
        raise ctypes.WinError(ctypes.get_last_error())


def revalidate_existing(plan_path, corrected_path, output):
    """Solve both time resolutions from zero state against one pinned geometry."""
    from tools.prepare_hydrology_domains import prepare_hybrid_lake_seasonal
    from terrain_pipeline.hydrology_seasonal_hybrid import load_hybrid_lake_bundle
    from terrain_pipeline.hydrology_seasonal import WATER_STEP_ALGORITHM, PERIODIC_SOLVER
    limit_resources()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    plan = load_plan(plan_path)
    corrected_path = Path(corrected_path)
    pin = file_sha256(corrected_path)
    write(output / "declaration.json", {"parent_plan_identity_sha256": plan["identity_sha256"],
        "fine_source_sha256": pin, "water_step_algorithm": WATER_STEP_ALGORITHM,
        "periodic_solver_algorithm": PERIODIC_SOLVER, "initial_state": "zero soil and lake storage",
        "cpu_limit": 2, "priority": "BelowNormal", "python_executable": sys.executable})
    results, bundles = {}, {}
    for name, substeps in (("daily", 1), ("halfday", 2)):
        config = SeasonalConfig(substeps_per_day=substeps)
        target = output / name
        target.mkdir()
        result = prepare_hybrid_lake_seasonal(plan, target, corrected_path, pin, 1, asdict(config))
        write(output / (name + "-result.json"), result)
        results[name] = result
        if result["status"] != "rejected":
            bundles[name] = load_hybrid_lake_bundle(plan, result["path"])
    comparison = {"status": "unavailable_periodic_rejection", "runs": {
        name: result["status"] for name, result in results.items()}}
    if len(bundles) == 2:
        daily, half = (bundles[name]["result"] for name in ("daily", "halfday"))
        inland = daily["metadata"]["domain_ids"].index(1)
        comparison.update(status="both_periodic_cycles_cold_verified",
            maximum_monthly_soil_difference_mm=float(np.abs(daily["soil_mm"] - half["soil_mm"]).max()),
            maximum_monthly_lake_level_difference_m=float(np.abs(
                daily["lake_level_m"][:, inland] - half["lake_level_m"][:, inland]).max()),
            convergence_depth_mm=SeasonalConfig().convergence_depth_mm,
            convergence_lake_level_m=SeasonalConfig().convergence_lake_level_m)
    write(output / "time-resolution-comparison.json", comparison)
    return results


def prepare(support_path, old_lake_detail, output):
    limit_resources()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    support = load_plan(support_path)
    plan = select_development_pair(support, 46)
    if plan["domains"][0]["kind"] != "coastal" or plan["domains"][1]["kind"] != "inland":
        raise ValueError("explicit coastal/inland development pair required")
    save_plan(plan, output / "plan.npz")
    plan = load_plan(output / "plan.npz")
    with np.load(old_lake_detail, allow_pickle=False) as archive:
        old = json.loads(str(archive["metadata_json"].item()))
        old_raw = archive["original_td_m"].copy()
    budget = DetailBudget(**old["budget"])
    declaration = {"schema": "hydrology-v5-lake-revalidation-declaration-v1",
        "plan_identity": plan["identity_sha256"], "support_identity": support["identity_sha256"],
        "lake_domain_id_in_support": 46, "lake_domain_id_in_pair": 1,
        "coastal_terminal_count": len(plan["domains"][0]["terminal_indices"]),
        "old_detail_sha256": file_sha256(old_lake_detail), "budget": asdict(budget),
        "seasonal_parameters": asdict(SeasonalConfig()), "gpu_inference": False,
        "validation_runtime": {"python_executable": sys.executable, "python_version": sys.version},
        "revalidation": ["new v5 pair periodic water account", "original raw TD archive and component SHA",
            "new v5 canonical projection and crop budget", "new v5 lake saddle correction",
            "new hybrid periodic accounts and all-critical-stage connectivity"],
        "not_inherited": ["old v4 periodic state", "old projected height", "old geometry identity", "old 22-terminal coastal grouping"]}
    write(output / "declaration.json", declaration)
    raw_path = Path(old_lake_detail).parent / "lake_shore-original-td.npz"
    raw, generated = load_raw_td(raw_path, old["raw_provenance"]["archive_sha256"])
    if not np.array_equal(raw["arrays"]["height_m"], old_raw):
        raise ValueError("pinned raw lake window differs from old raw TD")
    write(output / "raw-cache-audit.json", {"schema": "hydrology-v5-raw-cache-reuse-v1",
        "plan_identity": plan["identity_sha256"], "archive_path": str(raw_path),
        "archive_sha256": file_sha256(raw_path), "raw_pixels_equal": True,
        "tile_assembly": old["raw_provenance"]["generation_metadata"]["tile_assembly"], "derived_geometry_reused": False})
    seasonal = simulate_seasonal_water_balance(plan, SeasonalConfig())
    save_seasonal_water_balance(plan, seasonal, output / "seasonal.npz")
    cold = load_seasonal_water_balance(plan, output / "seasonal.npz")
    lake_column = cold["metadata"]["domain_ids"].index(1)
    maximum = float(cold["lake_level_m"][:, lake_column].max())
    write(output / "seasonal-audit.json", {"schema": "hydrology-v5-lake-seasonal-cold-audit-v1",
        "plan_identity": plan["identity_sha256"], "metadata": cold["metadata"],
        "minimum_lake_level_m": float(cold["lake_level_m"][:, lake_column].min()),
        "maximum_lake_level_m": maximum, "archive_sha256": file_sha256(output / "seasonal.npz")})
    detail = derive_detail(plan, old_raw, origin_xz_m=old["origin_xz_m"], spacing_m=old["spacing_m"],
        raw_provenance=old["raw_provenance"], budget=budget, window_kind="lake_shore")
    detail["metadata"]["baseline_node_provenance"] = old.get("baseline_node_provenance", {})
    from terrain_pipeline.hydrology_detail import _digest
    import hashlib
    detail["metadata"].pop("identity", None)
    detail["metadata"]["identity"] = _digest({"metadata": detail["metadata"], "arrays": {
        key: hashlib.sha256(value.tobytes()).hexdigest() for key, value in sorted(detail["arrays"].items())}})
    lake_folder = output / "lake_shore"
    lake_folder.mkdir()
    save_detail(lake_folder / "lake_shore-detail.npz", detail)
    anchors = output / "canonical-projection-td-nodes"
    anchors.mkdir()
    old_nodes = Path("verification/hydrological-planning-domain/formal-02/canonical-projection-td-nodes")
    for path in old_nodes.glob("*.json"):
        shutil.copyfile(path, anchors / path.name)
    from tools.prepare_hydrology_domains import prepare_canonical_projection, prepare_hybrid_lake_seasonal
    projected = prepare_canonical_projection(plan, output, budget, maximum, window_kind="lake_shore", projection_version="v3")
    write(output / "projection-result.json", projected)
    crop = next((entry for entry in projected["owned_window_crops"] if entry.get("path")
        and entry.get("status") == "local_compatible_global_unverified" and not entry.get("rejection_reasons")), None)
    if crop is None:
        return projected
    from terrain_pipeline.hydrology_seasonal_hybrid import load_hybrid_lake_detail, prepare_connected_hybrid_lake_detail
    source_path = Path(crop["path"])
    source_sha = file_sha256(source_path)
    source = load_hybrid_lake_detail(source_path, source_sha)
    original_result = prepare_hybrid_lake_seasonal(plan, output, source_path, source_sha, 1, asdict(SeasonalConfig()))
    write(output / "hybrid-original-result.json", original_result)
    correction = prepare_connected_hybrid_lake_detail(plan, source, source_sha256=source_sha, domain_id=1)
    corrected_path = output / "lake-connected-detail.npz"
    save_detail(corrected_path, correction)
    corrected = prepare_hybrid_lake_seasonal(plan, output, corrected_path, file_sha256(corrected_path), 1, asdict(SeasonalConfig()))
    write(output / "hybrid-corrected-result.json", corrected)
    return corrected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--support")
    parser.add_argument("--old-lake-detail")
    parser.add_argument("--existing-plan")
    parser.add_argument("--corrected-detail")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.existing_plan and args.corrected_detail:
        revalidate_existing(args.existing_plan, args.corrected_detail, args.output)
    elif args.support and args.old_lake_detail:
        prepare(args.support, args.old_lake_detail, args.output)
    else:
        parser.error("supply existing-plan/corrected-detail or support/old-lake-detail")


if __name__ == "__main__":
    main()
