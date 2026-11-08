from types import SimpleNamespace

import numpy as np
import pytest

import terrain_pipeline.new_world_delta as delta


def test_two_mouths_and_duplicate_transaction(monkeypatch):
    calls = []
    monkeypatch.setattr(delta, "run_integrated_delta", lambda *a: calls.append(a) or {"ok": True})
    ocean = np.array([[False, True]])
    args = dict(source_identity="source", interval_ids=["month-1"], duration_s=[10.],
        water_m3=[4.], solid_m3=[.2], sediment_source="finite upstream inventory",
        bed_m=np.array([[1., -1.]]), ocean_mask=ocean,
        geometry=SimpleNamespace(ocean_mask=ocean.copy(), eligible_mask=np.zeros_like(ocean)),
        prohibited_mask=np.zeros_like(ocean))
    consumer = delta.MouthConsumer()
    consumer.run(mouth_id="a", **args)
    consumer.run(mouth_id="b", **args)
    with pytest.raises(ValueError, match="already consumed"):
        consumer.run(mouth_id="a", **args)
    assert len(calls) == 2
    assert calls[0][2].tolist() == [4.]


def test_ocean_mismatch_does_not_consume(monkeypatch):
    monkeypatch.setattr(delta, "run_integrated_delta", lambda *a: {})
    consumer = delta.MouthConsumer()
    with pytest.raises(ValueError, match="ocean classification"):
        consumer.run(source_identity="s", mouth_id="m", interval_ids=["i"],
            duration_s=[1.], water_m3=[1.], solid_m3=[0.], sediment_source="none",
            bed_m=np.zeros((1, 1)), ocean_mask=np.ones((1, 1), bool),
            geometry=SimpleNamespace(ocean_mask=np.zeros((1, 1), bool)),
            prohibited_mask=np.zeros((1, 1), bool))
    assert not consumer.consumed
