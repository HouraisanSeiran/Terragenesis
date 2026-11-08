"""Explicit archived v3/v1 numerical comparisons; current v4 has separate tests."""
from tools.replay_natural_fv_growth_legacy import legacy_test_module

_legacy = legacy_test_module('tests.test_fv_growth_v3')
water = _legacy.water
step = _legacy.step
for _name in dir(_legacy):
    if _name.startswith('test_'):
        globals()[_name] = getattr(_legacy, _name)
