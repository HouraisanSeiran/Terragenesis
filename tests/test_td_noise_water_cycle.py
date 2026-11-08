"""Noise rainfall provenance remains auditable without hydrologic solvers."""

import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_morphology_coupling import _pack, _unpack
from terrain_pipeline.surface_rivers.metric_water_cycle import load_water_cycle, output_times, validate_water_cycle

PACKAGE = Path(__file__).resolve().parents[1] / "verification/td-natural-river-stages/noise-water-cycle-20261011-02/noise-water-cycle.npz"


class NoiseWaterCycleTests(unittest.TestCase):
    def test_fractional_endpoint_is_retained_without_future_frame(self):
        for name in ("dense", "sparse", "hourly"):
            np.testing.assert_array_equal(output_times(299.5, name), [0., 299.5])

    def fixture(self):
        return load_water_cycle(PACKAGE, expected_sha256=file_sha256(PACKAGE))

    def test_cold_read_with_both_solvers_forbidden(self):
        with patch('terrain_pipeline.runoff.simulate_rainfall_runoff', side_effect=AssertionError("native solver")), \
             patch("terrain_pipeline.surface_rivers.metric_boundary_coupling.solve_coupled", side_effect=AssertionError("coupled solver")):
            self.fixture()

    def test_rehashed_noise_seed_and_sampling_changes_rejected(self):
        for key, value in (("seed", 20261012), ("spatial_subsamples", 1)):
            with self.subTest(key=key):
                bundle = copy.deepcopy(self.fixture())
                native = _unpack(bundle["arrays"], bundle["metadata"], "native")
                native["metadata"]["noise_rainfall_provenance"][key] = value
                native["identity_sha256"] = identity(native["arrays"], native["metadata"])
                _pack(bundle["arrays"], bundle["metadata"], "native", native)
                bundle["identity_sha256"] = identity(bundle["arrays"], bundle["metadata"])
                with self.assertRaisesRegex(ValueError, "noise rainfall provenance"):
                    validate_water_cycle(bundle)


if __name__ == "__main__":
    unittest.main()
