"""Opt-in original source regression suite, executed only through the frozen loader."""

import unittest

from tools.hybrid_hydraulics_legacy import HydraulicsLegacyReplay


def load_tests(loader, tests, pattern):
    replay = HydraulicsLegacyReplay()
    suite = unittest.TestSuite()
    for name in sorted(replay.sources):
        if name.startswith("tests.test_hybrid_river_"):
            suite.addTests(loader.loadTestsFromModule(replay.load(name)))
    suite._hydraulics_replay = replay
    return suite
