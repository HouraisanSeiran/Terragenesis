"""Isolated GPU validation samples with pinned real BIO conditioning inputs."""

import argparse
import json
from pathlib import Path
import time

import numpy as np

from diffusion.backend import TerrainDiffusionBackend
from diffusion.config import GenerationConfig
from terrain_pipeline.mountain_source_adapter import file_sha256, identity


ROOT = Path(__file__).resolve().parents[1]
ORIGINS = ((0, 0), (384, 15488), (11520, 15360))
CHANNELS = ("temperature", "temperature_std", "precipitation", "precipitation_cv")


def prepare(output, phase, reference_path):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    reference_path = Path(reference_path)
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    selected = [block["climate_BIO1_4_12_15"] for block in reference["blocks"]
                if block["role"] == "train" and block["status"] == "measured"]
    values = np.median(selected, axis=0)
    condition_path = output / "real-bio-conditions.npz"
    arrays = {name: np.full((512, 512), value, np.float32) for name, value in zip(CHANNELS, values)}
    np.savez_compressed(condition_path, origin=np.array([-256, -256], np.int64), **arrays)
    config = GenerationConfig.for_profile("geographic_v5", v5_base_headroom_m=120.,
        conditions=str(condition_path.resolve().relative_to(ROOT)).replace("\\", "/"))
    config_identity, model_metadata = config.identity()
    plan = {"schema": "TD-real-BIO-validation-plan-v1", "phase": phase,
            "seeds": [20261011, 20261012] if phase == "development" else [20261013, 20261014],
            "native_origins_xz": [list(origin) for origin in ORIGINS], "native_side": 513,
            "native_spacing_m": 30., "diagnostic_windows_zx": [[0, 0], [192, 192]],
            "source_reference_path": str(reference_path.resolve()), "source_reference_sha256": file_sha256(reference_path),
            "BIO_values": values.tolist(), "BIO_selection": "median_real_training_blocks_only",
            "BIO_semantics": "model_condition_inputs_from_real_reference_not_measured_forcing",
            "condition_path": str(condition_path.resolve()), "condition_sha256": file_sha256(condition_path),
            "coarse_condition_bounds_iz_jx": [-256, 256, -256, 256],
            "elevation_condition": "original_geographic_v5_no_elevation_override",
            "generation_config": config.record(), "generation_identity": config_identity,
            "model_metadata": model_metadata, "tool_sha256": file_sha256(__file__),
            "resource_policy": "isolated_offline_GPU_generation_no_default_world_changes",
            "selection_policy": "all_three_origins_each_seed_retained_regardless_of_output_conditions_or_geometry"}
    plan["identity_sha256"] = identity({}, plan)
    (output / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan


def generate(output):
    output = Path(output)
    plan_path = output / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    payload = {key: value for key, value in plan.items() if key != "identity_sha256"}
    if plan["identity_sha256"] != identity({}, payload) or file_sha256(__file__) != plan["tool_sha256"]:
        raise ValueError("frozen generation plan/tool differs")
    if file_sha256(Path(plan["condition_path"])) != plan["condition_sha256"]:
        raise ValueError("real BIO condition pin differs")
    config_values = dict(plan["generation_config"])
    config_values["cond_snr"] = tuple(config_values["cond_snr"])
    config = GenerationConfig(**config_values)
    backend = TerrainDiffusionBackend(config)
    records = []
    checks = []
    started = time.perf_counter()
    try:
        backend.load()
        import torch
        torch.cuda.reset_peak_memory_stats()
        for seed in plan["seeds"]:
            backend.pipeline.change_seed(seed)
            backend.seed = seed
            raw = backend.pipeline._raw_conditioning_with_imports(-80, 100, -80, 100)
            expected = np.array(plan["BIO_values"], np.float32)
            for channel in range(4):
                np.testing.assert_array_equal(raw[channel + 1], np.full(raw.shape[1:], expected[channel], np.float32))
            factory = backend.pipeline.synthetic_map_factory
            original = factory.sample_raw(-80, -80, 100, 100)
            np.testing.assert_array_equal(raw[0], original[0])
            checks.append({"seed": seed, "custom_BIO_survives_change_seed": True,
                           "original_v5_elevation_condition_unchanged": True,
                           "checked_coarse_bounds_iz_jx": [-80, 100, -80, 100]})
            for x, z in plan["native_origins_xz"]:
                elapsed = time.perf_counter()
                height, climate, metadata = backend.generate(seed, x, z, plan["native_side"])
                path = output / ("seed" + str(seed) + "-x" + str(x) + "-z" + str(z) + ".npz")
                if path.exists():
                    raise FileExistsError(path)
                np.savez_compressed(path, elevation=height, climate=climate,
                    metadata=np.array(json.dumps(metadata)), generation_config=np.array(json.dumps(config.record())))
                records.append({"seed": seed, "native_origin": [x, z], "raw_npz": path.name,
                    "raw_sha256": file_sha256(path), "shape_zx": list(height.shape),
                    "native_spacing_m": metadata["native_resolution_m"],
                    "output_BIO_medians": np.median(climate, axis=(1, 2)).tolist(),
                    "height_range_m": [float(height.min()), float(height.max())],
                    "elapsed_s": time.perf_counter() - elapsed})
                print(json.dumps(records[-1]), flush=True)
        status = "completed"
        failure = None
    except Exception as error:
        status = "failed_with_retained_outputs"
        failure = type(error).__name__ + ": " + str(error)
        raise
    finally:
        report = {"schema": "TD-real-BIO-validation-generation-v1", "status": locals().get("status", "failed"),
                  "failure": locals().get("failure"), "plan_sha256": file_sha256(plan_path),
                  "generation_identity": plan["generation_identity"], "generation_config": plan["generation_config"],
                  "condition_sha256": plan["condition_sha256"], "samples": records, "source_checks": checks,
                  "elapsed_s": time.perf_counter() - started,
                  "gpu_peak_allocated_bytes": int(torch.cuda.max_memory_allocated()) if "torch" in locals() else None,
                  "natural_certification": False}
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        backend.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("development", "holdout"), default="development")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--generate-existing", action="store_true")
    args = parser.parse_args()
    if not args.generate_existing:
        prepare(args.output, args.phase, args.reference)
    if not args.prepare_only:
        generate(args.output)
