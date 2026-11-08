"""Generate isolated TD samples from meter-coordinate monthly noise climate."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

import numpy as np

from diffusion.backend import TerrainDiffusionBackend
from diffusion.config import GenerationConfig
from diffusion.geography_v5 import make_geographic_map_factory
from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.climate_forcing import NoiseClimateParameters, sample_climate


ROOT = Path(__file__).resolve().parents[1]
CHANNELS = ("temperature", "temperature_std", "precipitation", "precipitation_cv")
COARSE_NATIVE_SCALE = 256
COARSE_METERS = 30. * COARSE_NATIVE_SCALE


def implementation_pins():
    names = ("tools/generate_td_noise_validation.py", "diffusion/backend.py", "diffusion/config.py",
             "diffusion/geography_v5.py", "diffusion/geography_v2.py", "diffusion/geographic_noise.py",
             "terrain_pipeline/climate_forcing.py",
             "vendor/terrain-diffusion-e8dcb4b1a834ab2f6b1a6f5256ed7c9f2f3e8230/terrain_diffusion/inference/world_pipeline.py",
             "vendor/terrain-diffusion-e8dcb4b1a834ab2f6b1a6f5256ed7c9f2f3e8230/terrain_diffusion/inference/postprocessing.py")
    return {name: file_sha256(ROOT / name) for name in names}


def select_land_origins(seed):
    factory = make_geographic_map_factory(seed=seed, base_knee_m=120., base_headroom_m=120.)
    selected = []
    candidates = []
    for z in range(-65536, 65537, 8192):
        for x in range(-65536, 65537, 8192):
            c0, r0 = x // 256, z // 256
            c1, r1 = (x + 513 + 255) // 256, (z + 513 + 255) // 256
            raw = factory.sample_raw(c0 - 8, r0 - 8, c1 + 8, r1 + 8)[0]
            record = {"origin_xz": [x, z], "coarse_bounds_xz": [c0 - 8, r0 - 8, c1 + 8, r1 + 8],
                      "condition_height_range_m": [float(raw.min()), float(raw.max())]}
            supported = bool((raw > 0.).all())
            separated = all(math_distance(x, z, old["origin_xz"]) >= 16000. for old in selected)
            record["selected"] = supported and separated and len(selected) < 3
            candidates.append(record)
            if record["selected"]:
                selected.append(record)
    if len(selected) != 3:
        raise ValueError("predeclared source-condition search lacks three full-halo land domains")
    return selected, candidates


def math_distance(x, z, old):
    return float(np.hypot(x - old[0], z - old[1]))


def prepare(output, phase, physical_reference):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    parameters = NoiseClimateParameters()
    jobs = []
    seeds = [20261011, 20261012] if phase == "development" else [20261013, 20261014]
    for seed in seeds:
        selected, candidates = select_land_origins(seed)
        factory = make_geographic_map_factory(seed=seed, base_knee_m=120., base_headroom_m=120.)
        raw = factory.sample_raw(-384, -384, 384, 384)
        x, z = np.meshgrid(np.arange(-384, 384) * COARSE_METERS, np.arange(-384, 384) * COARSE_METERS)
        climate = sample_climate(seed, x, z, raw[0], parameters=parameters)
        condition_path = output / ("noise-conditions-seed" + str(seed) + ".npz")
        np.savez_compressed(condition_path, origin=np.array([-384, -384], np.int64),
                            **{name: climate["BIO1_4_12_15"][index].astype(np.float32) for index, name in enumerate(CHANNELS)})
        config = GenerationConfig.for_profile("geographic_v5", v5_base_headroom_m=120.,
            conditions=str(condition_path.resolve().relative_to(ROOT)).replace("\\", "/"))
        generation_identity, model_metadata = config.identity()
        jobs.append({"seed": seed, "domains": selected, "source_candidates": candidates,
            "condition_path": str(condition_path.resolve()), "condition_sha256": file_sha256(condition_path),
            "generation_config": config.record(), "generation_identity": generation_identity,
            "model_metadata": model_metadata})
    physical_reference = Path(physical_reference)
    snapshots = {}
    pins = implementation_pins()
    for name, sha in pins.items():
        snapshot = output / "source-snapshots" / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes((ROOT / name).read_bytes())
        snapshots[name] = {"path": str(snapshot.resolve()), "sha256": sha}
    plan = {"schema": "TD-noise-climate-generation-plan-v1", "phase": phase, "jobs": jobs,
        "parameters": asdict(parameters), "noise_parameter_identity_sha256": parameters.identity_sha256,
        "source_condition_selection": "fixed_8192native_grid_lexicographic_first_three_16000native_separated_full513window_plus_8coarsehalo_strictly_positive_no_TD_outputs_read",
        "candidate_bounds_native_xz": [-65536, 65536], "native_side": 513, "native_spacing_m": 30.,
        "diagnostic_windows_native_zx": [[0, 0], [192, 192]],
        "coarse_climate_meter_mapping": COARSE_METERS, "condition_bounds_coarse_iz_jx": [-384, 384, -384, 384],
        "climate_semantics": "synthetic_monthly_noise_targets_BIO_derived_from_same_months_not_measured_forcing",
        "physical_reference_path": str(physical_reference.resolve()), "physical_reference_sha256": file_sha256(physical_reference),
        "source_implementation_pins": pins, "source_snapshots": snapshots,
        "elevation_condition": "original_v5_preserved_in_actual_coarse_model_input_all_jobs",
        "selection_policy": "all_selected_land_domains_retained_regardless_of_output_height_BIO_or_geometry",
        "original_negative_condition_domains": "retained_real_BIO_development_01_and_original_stage4_as_historical_counterexamples",
        "natural_certification": False}
    plan["identity_sha256"] = identity({}, plan)
    (output / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan


def generate(output, evaluation_plan=None):
    output = Path(output)
    plan_path = output / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    payload = {key: value for key, value in plan.items() if key != "identity_sha256"}
    if plan["identity_sha256"] != identity({}, payload) or plan["source_implementation_pins"] != implementation_pins():
        raise ValueError("frozen noise generation plan/actual implementation differs")
    if plan["phase"] == "holdout" and (evaluation_plan is None or not Path(evaluation_plan).is_file()):
        raise ValueError("formal holdout requires previously frozen evaluation plan")
    evaluation_plan_sha = file_sha256(Path(evaluation_plan)) if evaluation_plan else None
    samples = []
    checks = []
    start = time.perf_counter()
    backend = None
    peak_gpu = 0
    try:
        import torch
        for job in plan["jobs"]:
            if file_sha256(Path(job["condition_path"])) != job["condition_sha256"]:
                raise ValueError("noise condition source differs")
            values = dict(job["generation_config"])
            values["cond_snr"] = tuple(values["cond_snr"])
            backend = TerrainDiffusionBackend(GenerationConfig(**values))
            backend.load()
            torch.cuda.reset_peak_memory_stats()
            seed = job["seed"]
            backend.pipeline.change_seed(seed)
            backend.seed = seed
            with np.load(job["condition_path"], allow_pickle=False) as conditions:
                for domain in job["domains"]:
                    c0, r0, c1, r1 = domain["coarse_bounds_xz"]
                    actual = backend.pipeline._conditioning_model_input(r0, r1, c0, c1).numpy()
                    original = backend.pipeline.synthetic_map_factory(c0, r0, c1, r1).numpy()
                    np.testing.assert_array_equal(actual[0], original[0])
                    for channel, name in enumerate(CHANNELS, 1):
                        np.testing.assert_array_equal(actual[channel], conditions[name][r0 + 384:r1 + 384, c0 + 384:c1 + 384])
                    checks.append({"seed": seed, "origin": domain["origin_xz"], "actual_coarse_elevation_input_equal_original_v5": True,
                                   "noise_BIO_actual_model_input_equal_pinned_conditions_after_change_seed": True})
            for domain in job["domains"]:
                x, z = domain["origin_xz"]
                began = time.perf_counter()
                height, climate, metadata = backend.generate(seed, x, z, plan["native_side"])
                path = output / ("seed" + str(seed) + "-x" + str(x) + "-z" + str(z) + ".npz")
                if path.exists():
                    raise FileExistsError(path)
                np.savez_compressed(path, elevation=height, climate=climate, metadata=np.array(json.dumps(metadata)),
                                    generation_config=np.array(json.dumps(job["generation_config"])))
                samples.append({"seed": seed, "native_origin": [x, z], "raw_npz": path.name, "raw_sha256": file_sha256(path),
                    "generation_identity": job["generation_identity"], "condition_sha256": job["condition_sha256"],
                    "height_range_m": [float(height.min()), float(height.max())], "output_BIO_medians": np.median(climate, axis=(1, 2)).tolist(),
                    "elapsed_s": time.perf_counter() - began})
                print(json.dumps(samples[-1]), flush=True)
            peak_gpu = max(peak_gpu, int(torch.cuda.max_memory_allocated()))
            backend.close()
            backend = None
        if evaluation_plan and file_sha256(Path(evaluation_plan)) != evaluation_plan_sha:
            raise ValueError("evaluation plan changed during generation")
        status, failure = "completed", None
    except Exception as error:
        status, failure = "failed_with_retained_outputs", type(error).__name__ + ": " + str(error)
        raise
    finally:
        report = {"schema": "TD-noise-climate-generation-v1", "status": locals().get("status", "failed"),
            "failure": locals().get("failure"), "plan_path": str(plan_path.resolve()), "plan_sha256": file_sha256(plan_path), "samples": samples,
            "actual_source_checks": checks, "elapsed_s": time.perf_counter() - start, "gpu_peak_allocated_bytes": peak_gpu,
            "evaluation_plan_path": str(Path(evaluation_plan).resolve()) if evaluation_plan else None,
            "evaluation_plan_sha256": evaluation_plan_sha, "natural_certification": False}
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if backend is not None:
            backend.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("development", "holdout"), default="development")
    parser.add_argument("--physical-reference", type=Path)
    parser.add_argument("--evaluation-plan", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--generate-existing", action="store_true")
    args = parser.parse_args()
    if not args.generate_existing:
        prepare(args.output, args.phase, args.physical_reference)
    if not args.prepare_only:
        generate(args.output, args.evaluation_plan)
