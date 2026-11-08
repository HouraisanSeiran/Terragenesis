"""Explicit frozen-v1 numerical comparison tests, outside current generation."""
from tools.replay_natural_fv_growth_legacy import legacy_test_module

_legacy = legacy_test_module('tests.test_fv_suspended_growth')
geometry = _legacy.geometry
packet = _legacy.packet
for _name in dir(_legacy):
    if _name.startswith('test_'):
        globals()[_name] = getattr(_legacy, _name)
