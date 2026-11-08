"""Explicit regression of the original archived hydraulics algorithm, not current generation."""

from tools.hybrid_hydraulics_legacy import HydraulicsLegacyReplay


def load_tests(loader, tests, pattern):
    replay = HydraulicsLegacyReplay()
    suite = loader.loadTestsFromModule(replay.load("tests.test_hybrid_river_hydraulics"))
    suite._hydraulics_replay = replay
    return suite
