import json

import numpy as np
from PIL import Image
import pytest

from tools import prepare_skeleton_mountains as prepare


def test_export_real_arrays_gray_depth_hashes_and_refuse_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare, "plot_results", lambda *args: None)
    monkeypatch.setattr(prepare, "plot_sections", lambda *args: None)
    out = tmp_path / "height-evidence"
    prepare.generate(out, size=17, spacing=1500.)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["world_seed"] == 20260903
    assert len(manifest["cases"]) == 7
    for item in manifest["cases"]:
        with np.load(out / item["npz"]) as saved:
            fields = dict(saved)
        for key, image in item["height_images"].items():
            path = out / image["file"]
            assert path.read_bytes()[24:26] == bytes([16, 0])  # PNG IHDR depth, color type.
            with Image.open(path) as png:
                decoded = -500 + np.asarray(png, dtype=np.float64)*6500/65535
            assert np.max(np.abs(decoded - fields[key])) <= 6500/65535/2 + 1e-10
            assert prepare.digest(path) == image["sha256"]
        x, z = item["origin_xz_m"]
        config_class = prepare.LocalVolumeConfig if item["name"] == "main_previous" else prepare.SkeletonMountainConfig
        fresh = prepare.sample(config_class(**item["config"]), x+7500., z+9000.)
        assert fields["height_m"][6, 5] == fresh["height_m"]
    before = prepare.digest(out / "manifest.json")
    with pytest.raises(FileExistsError):
        prepare.generate(out, size=17, spacing=1500.)
    assert before == prepare.digest(out / "manifest.json")


def test_failed_generation_never_publishes_partial_target(tmp_path, monkeypatch):
    def fail(*args):
        raise RuntimeError("injected generation failure")
    monkeypatch.setattr(prepare, "sample", fail)
    with pytest.raises(RuntimeError, match="injected"):
        prepare.generate(tmp_path / "failed")
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        prepare.generate(tmp_path / "invalid", size=0)
    assert list(tmp_path.iterdir()) == []
