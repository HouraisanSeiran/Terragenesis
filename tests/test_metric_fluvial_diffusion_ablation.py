import json
import hashlib
import numpy as np
import pytest
from pathlib import Path
from dataclasses import asdict
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import validate_diffusion_ablation_parent
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import MorphodynamicsConfig

WATER_ROUTING_REPAIR_VERSION = "pydeltarcm-metric-adapter-v6-water-routing-repair"


@pytest.fixture
def diffusion_parent_env(tmp_path):
    config = MorphodynamicsConfig(steps=4)
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    checkpoint = resume_dir / "checkpoint.npz"
    material = resume_dir / "adapter-material-state.npz"
    checkpoint.write_bytes(b"checkpoint-bytes")
    material.write_bytes(b"material-bytes")

    checkpoint_sha = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    material_sha = hashlib.sha256(material.read_bytes()).hexdigest()
    continuation_identity = hashlib.sha256(b"source-identity").hexdigest()
    core = {
        "algorithm_version": WATER_ROUTING_REPAIR_VERSION,
        "native_end_step_index": 4224,
        "config": dict(asdict(config), steps=128, official_shape=list(config.official_shape)),
        "checkpoint_end_path": str(checkpoint),
        "checkpoint_end_sha256": checkpoint_sha,
        "material_state_end_path": str(material),
        "material_state_end_sha256": material_sha,
        "continuation_identity": continuation_identity,
    }
    archive_path = tmp_path / "parent.npz"
    metadata = {"core": core}
    np.savez(archive_path, metadata_json=json.dumps(metadata))
    archive_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()

    continuation = {
        "algorithm_version": WATER_ROUTING_REPAIR_VERSION,
        "native_end_step_index": 4224,
        "checkpoint_sha256": checkpoint_sha,
        "material_state_sha256": material_sha,
        "continuation_identity": continuation_identity,
        "mechanism_identity": "v6-mech",
        "routing_dry_depth_m": 0.01,
        "quantized_native_exchange": True,
        "water_routing_repair": True,
    }
    (resume_dir / "adapter-continuation.json").write_text(json.dumps(continuation), encoding="utf-8")

    declaration = {
        "enabled": True,
        "parent_archive_path": str(archive_path),
        "parent_archive_sha256": archive_sha,
        "checkpoint_sha256": checkpoint_sha,
        "material_state_sha256": material_sha,
    }
    return {"config": config, "resume_dir": str(resume_dir), "declaration": declaration,
            "archive_sha": archive_sha, "checkpoint_sha": checkpoint_sha,
            "material_sha": material_sha, "continuation_identity": continuation_identity}


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("steps", [4, 128])
def test_valid_true_and_false_with_tuple_and_list_shape(diffusion_parent_env, enabled, steps):
    import dataclasses
    env = diffusion_parent_env
    declaration = dict(env["declaration"], enabled=enabled)
    config = dataclasses.replace(env["config"], steps=steps)
    out = validate_diffusion_ablation_parent(declaration, config, env["resume_dir"])
    assert out["schema"] == "terminal-diffusion-ablation-v1"
    assert out["diagnostic_only"] is True
    assert out["effective_diffusion_enabled"] is enabled
    assert out["enabled"] is enabled
    assert out["steps"] == steps


def test_invalid_steps_rejected(diffusion_parent_env):
    import dataclasses
    env = diffusion_parent_env
    bad_cfg = dataclasses.replace(env["config"], steps=5)
    with pytest.raises(ValueError, match=r"requires config.steps in \(4, 128\)"):
        validate_diffusion_ablation_parent(
            dict(env["declaration"], enabled=True), bad_cfg, env["resume_dir"])


def test_malformed_enabled_rejected(diffusion_parent_env):
    env = diffusion_parent_env
    bad = dict(env["declaration"], enabled=1)
    with pytest.raises(ValueError, match="must be an explicit bool"):
        validate_diffusion_ablation_parent(bad, env["config"], env["resume_dir"])


def test_archive_wrong_sha_rejected(diffusion_parent_env):
    env = diffusion_parent_env
    bad = dict(env["declaration"], parent_archive_sha256="0" * 64)
    with pytest.raises(ValueError, match="archive sha256 mismatch"):
        validate_diffusion_ablation_parent(bad, env["config"], env["resume_dir"])


@pytest.mark.parametrize("mutator,msg", [
    (lambda e: e.__setitem__("checkpoint_sha256", "1" * 64), "declaration checkpoint_sha256 mismatch"),
    (lambda e: e.__setitem__("material_state_sha256", "2" * 64), "declaration material_state_sha256 mismatch"),
])
def test_mismatched_real_checkpoint_hash_rejected(diffusion_parent_env, mutator, msg):
    env = diffusion_parent_env
    bad = dict(env["declaration"])
    mutator(bad)
    with pytest.raises(ValueError, match=msg):
        validate_diffusion_ablation_parent(bad, env["config"], env["resume_dir"])


def test_wrong_core_path_rejected(diffusion_parent_env, tmp_path):
    env = diffusion_parent_env
    archive_path = Path(env["declaration"]["parent_archive_path"])
    with np.load(archive_path, allow_pickle=False) as z:
        metadata = json.loads(z["metadata_json"].item())
    metadata["core"]["checkpoint_end_path"] = str(tmp_path / "other-checkpoint.npz")
    np.savez(archive_path, metadata_json=json.dumps(metadata))
    new_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    decl = dict(env["declaration"], parent_archive_sha256=new_sha)
    with pytest.raises(ValueError, match="checkpoint_end_path does not match resume checkpoint"):
        validate_diffusion_ablation_parent(decl, env["config"], env["resume_dir"])


def test_mismatched_continuation_metadata_rejected(diffusion_parent_env):
    env = diffusion_parent_env
    cont_path = Path(env["resume_dir"]) / "adapter-continuation.json"
    cont = json.loads(cont_path.read_text(encoding="utf-8"))
    cont["continuation_identity"] = "different-identity"
    cont_path.write_text(json.dumps(cont), encoding="utf-8")
    with pytest.raises(ValueError, match="continuation_identity mismatch"):
        validate_diffusion_ablation_parent(env["declaration"], env["config"], env["resume_dir"])


@pytest.mark.parametrize("location,msg", [
    ("continuation", "continuation must not be diagnostic_only"),
    ("core", "archive core must not be diagnostic_only"),
])
def test_diagnostic_only_rejected(tmp_path, location, msg):
    config = MorphodynamicsConfig(steps=4)
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    checkpoint = resume_dir / "checkpoint.npz"
    material = resume_dir / "adapter-material-state.npz"
    checkpoint.write_bytes(b"cp")
    material.write_bytes(b"ms")
    cp_sha = hashlib.sha256(b"cp").hexdigest()
    ms_sha = hashlib.sha256(b"ms").hexdigest()
    core = {
        "algorithm_version": WATER_ROUTING_REPAIR_VERSION,
        "native_end_step_index": 4224,
        "config": dict(asdict(config), steps=128, official_shape=list(config.official_shape)),
        "checkpoint_end_path": str(checkpoint),
        "checkpoint_end_sha256": cp_sha,
        "material_state_end_path": str(material),
        "material_state_end_sha256": ms_sha,
        "continuation_identity": "x",
        "diagnostic_only": location == "core",
    }
    archive_path = tmp_path / "parent.npz"
    np.savez(archive_path, metadata_json=json.dumps({"core": core}))
    decl = {
        "enabled": True,
        "parent_archive_path": str(archive_path),
        "parent_archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "checkpoint_sha256": cp_sha,
        "material_state_sha256": ms_sha,
    }
    continuation = {
        "algorithm_version": WATER_ROUTING_REPAIR_VERSION,
        "native_end_step_index": 4224,
        "checkpoint_sha256": cp_sha,
        "material_state_sha256": ms_sha,
        "continuation_identity": "x",
        "diagnostic_only": location == "continuation",
    }
    (resume_dir / "adapter-continuation.json").write_text(json.dumps(continuation), encoding="utf-8")
    with pytest.raises(ValueError, match=msg):
        validate_diffusion_ablation_parent(decl, config, str(resume_dir))
