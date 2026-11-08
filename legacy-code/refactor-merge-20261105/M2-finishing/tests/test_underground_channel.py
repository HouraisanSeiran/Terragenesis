import json
import numpy as np
import pytest

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash
from terrain_pipeline.underground_rivers import UndergroundRecipe, load_underground, plan_underground, save_underground


def _plan(shape=(5, 5)):
    h = np.full(shape, 20.0, dtype=np.float64)
    ident = ArtifactIdentity("Terragenesis", "metric-channel-plan", "metric-channel-plan-v1", 0,
                             {"source_height_sha256": array_hash(h)})
    return {"status": "diagnostic_not_publishable", "identity": ident.record(),
            "identity_sha256": ident.sha256, "arrays": {"source_height_m": h}}


def test_paths_filters_and_explicit_exits(tmp_path):
    shape = (5, 5)
    domain = np.ones(shape, bool); protected = np.zeros(shape, bool); protected[1, 1] = True
    result = plan_underground(_plan(), np.zeros(shape), np.ones(shape), domain, protected,
                              [[2, 1], [1, 1], [0, 0]],
                              [{"grid_zx": [2, 3], "type": "surface_low"}, {"grid_zx": [2, 4], "type": "subsea"}],
                              UndergroundRecipe(min_entry_score=0), np.full(shape, 10.0))
    assert result["summary"]["accepted_entries"] == 2
    assert result["exits"][1]["type"] == "subsea"
    assert result["edges"] and result["edges"][0]["path_grid_zx"]
    assert result["preview_modes"] == ["surface_only", "underground_only", "overlay"]
    path = tmp_path / "u.npz"; save_underground(result, path); loaded = load_underground(path)
    assert loaded["identity_sha256"] == result["identity_sha256"]
    with np.load(path, allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files if k != "manifest"}; manifest = str(z["manifest"].item())
    arrays["score_m"] = arrays["score_m"].copy(); arrays["score_m"][0, 0] += 1
    np.savez_compressed(path, manifest=manifest, **arrays)
    with pytest.raises(ValueError): load_underground(path)


def test_cover_is_required_and_grayscale_only_changes_ranking():
    shape = (3, 3); masks = (np.ones(shape, bool), np.zeros(shape, bool))
    with pytest.raises(ValueError):
        plan_underground(_plan(shape), np.zeros(shape), np.ones(shape), *masks, [[1, 1]], [{"grid_zx": [1, 2], "type": "surface_low"}])
    kwargs = dict(surface_plan=_plan(shape), lithology_reference=np.ones(shape), domain_mask=masks[0],
                  protected_mask=masks[1], entries=[[1, 0]], exits=[{"grid_zx": [1, 2], "type": "surface_low"}],
                  recipe=UndergroundRecipe(min_entry_score=0), cover_reference=np.full(shape, 10.0))
    a = plan_underground(grayscale_reference=np.zeros(shape), **kwargs)
    b = plan_underground(grayscale_reference=np.full(shape, 9.0), **kwargs)
    assert np.array_equal(a["arrays"]["accepted_entry_mask"], b["arrays"]["accepted_entry_mask"])
    assert not np.array_equal(a["arrays"]["score_m"], b["arrays"]["score_m"])
