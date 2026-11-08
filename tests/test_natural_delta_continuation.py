import json

import pytest

from terrain_pipeline.common_infra import file_sha256
from tools.continue_natural_delta import consumed_sources, prepare


def test_consumed_sources_inherit_ancestors_and_original_forcing():
    assert consumed_sources({"forcing": {"source_sha256": "original"}}) == ["original"]
    child = {"steps": 1, "remaining_new_source_solid_m3": 100.,
        "consumed_source_sha256s": ["original", "new"], "forcing": {"source_sha256": "new"}}
    assert consumed_sources(child) == ["new", "original"]
    grandchild = {"consumed_source_sha256s": consumed_sources(child), "forcing": {"source_sha256": "third"}}
    assert consumed_sources(grandchild) == ["new", "original", "third"]


@pytest.mark.parametrize("parent_report", [
    {"forcing": {}},
    {"steps": 1, "remaining_new_source_solid_m3": 100., "forcing": {}},
])
def test_prepare_rejects_consumed_source_before_loading_or_creating_output(tmp_path, parent_report):
    parent = tmp_path / "parent"
    source = tmp_path / "source"
    parent.mkdir()
    source.mkdir()
    (source / "result.npz").write_bytes(b"finite source identity")
    digest = file_sha256(source / "result.npz")
    parent_report["consumed_source_sha256s"] = [digest]
    (parent / "summary.json").write_text(json.dumps(parent_report), encoding="utf-8")
    with pytest.raises(ValueError, match="already consumed in parent ancestry"):
        prepare(parent, source)
    # Consumption is branch-local: the original parent has no claim on this new source.
    assert digest not in consumed_sources({"forcing": {"source_sha256": "original"}})
