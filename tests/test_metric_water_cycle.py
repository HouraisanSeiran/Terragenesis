import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from terrain_pipeline.common_infra import file_sha256, identity, load_bundle
from terrain_pipeline.surface_rivers.metric_morphology_coupling import _pack, _unpack
from terrain_pipeline.surface_rivers.metric_water_cycle import load_water_cycle, validate_water_cycle

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "verification/td-natural-river-stages/water-cycle-20261011-final-bound/dry-closed-30-evidence.npz"


class WaterCycleColdTests(unittest.TestCase):
    def fixture(self):
        return load_bundle(PACKAGE, expected_sha256=file_sha256(PACKAGE), validator=validate_water_cycle)

    def test_cold_read_forbids_hydrologic_and_coupled_solves(self):
        with patch('terrain_pipeline.runoff.simulate_rainfall_runoff', side_effect=AssertionError("native solve")), \
             patch("terrain_pipeline.surface_rivers.metric_boundary_coupling.solve_coupled", side_effect=AssertionError("coupled solve")):
            load_water_cycle(PACKAGE, expected_sha256=file_sha256(PACKAGE))

    def test_rehashed_dt_owner_port_and_boundary_rejected(self):
        cases = (("native", "dt"), ("inputs", "owner"), ("coupled", "port"), ("coupled", "boundary"))
        for name, change in cases:
            with self.subTest(change=change):
                bundle = copy.deepcopy(self.fixture())
                piece = _unpack(bundle["arrays"], bundle["metadata"], name)
                if change == "dt":
                    piece["arrays"]["time_seconds"] = piece["arrays"]["time_seconds"].copy() * 2.
                elif change == "owner":
                    owner = piece["arrays"]["contribution_owner"].copy()
                    owner[owner == 0] = 1
                    piece["arrays"]["contribution_owner"] = owner
                elif change == "port":
                    piece["arrays"]["channel_to_lake"] = piece["arrays"]["channel_to_lake"].copy() - 1
                else:
                    piece["metadata"]["forcing_source_identity_sha256"] = "f" * 64
                piece["identity_sha256"] = identity(piece["arrays"], piece["metadata"])
                _pack(bundle["arrays"], bundle["metadata"], name, piece)
                bundle["identity_sha256"] = identity(bundle["arrays"], bundle["metadata"])
                with self.assertRaises(ValueError):
                    validate_water_cycle(bundle)


if __name__ == "__main__":
    unittest.main()
