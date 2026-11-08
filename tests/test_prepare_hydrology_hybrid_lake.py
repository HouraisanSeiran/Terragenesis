import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from terrain_pipeline.runoff import SeasonalConfig as SeasonalConfig
from builtins import ValueError as SeasonalBalanceError
from tools import prepare_hydrology_domains as entry


class HybridLakeEntryTests(unittest.TestCase):
    def test_new_periodic_geometry_refusal_is_saved_and_cold_loaded_without_old_period(self):
        plan = {"identity_sha256": "parent"}
        parameters = asdict(SeasonalConfig())
        pin = "a" * 64
        detail = {"metadata": {"identity": "fine"}, "arrays": {}}
        bundle = {"audit": {"domain_id": 1}, "result": {"metadata": {"parameters": parameters}},
                  "connectivity": {"status": "rejected"},
                  "manifest": {"fine_source_sha256": pin, "status": "periodic_accounts_converged_local_geometry_rejected"}}

        def publish(*args, **kwargs):
            directory = args[3]
            directory.mkdir()
            (directory / "hybrid-bundle.json").write_text("test manifest")

        with tempfile.TemporaryDirectory() as temporary, \
                patch('terrain_pipeline.runoff.load_hybrid_lake_detail', return_value=detail), \
                patch('terrain_pipeline.runoff.simulate_hybrid_lake_water_balance', return_value=bundle) as solve, \
                patch('terrain_pipeline.runoff.save_hybrid_lake_bundle', side_effect=publish) as save, \
                patch('terrain_pipeline.runoff.load_hybrid_lake_bundle', return_value=bundle) as cold:
            result = entry.prepare_hybrid_lake_seasonal(plan, temporary, "fine.npz", pin, 1, parameters)
            self.assertEqual(result["status"], "periodic_accounts_converged_local_geometry_rejected")
            self.assertTrue(result["seasonal_run"])
            solve.assert_called_once()
            self.assertEqual(asdict(solve.call_args.kwargs["config"]), parameters)
            self.assertNotIn("initial_state", solve.call_args.kwargs)
            save.assert_called_once()
            cold.assert_called_once()
            cached = entry.prepare_hybrid_lake_seasonal(plan, temporary, "fine.npz", pin, 1, parameters)
            self.assertFalse(cached["seasonal_run"])
            self.assertEqual(solve.call_count, 1)
            self.assertEqual(cold.call_count, 2)

    def test_periodic_failure_remains_diagnostic_and_does_not_publish_success(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch('terrain_pipeline.runoff.load_hybrid_lake_detail', return_value={}), \
                patch('terrain_pipeline.runoff.simulate_hybrid_lake_water_balance', side_effect=SeasonalBalanceError("no periodic state")), \
                patch('terrain_pipeline.runoff.save_hybrid_lake_bundle') as save:
            result = entry.prepare_hybrid_lake_seasonal({"identity_sha256": "parent"}, temporary,
                "fine.npz", "a" * 64, 1, asdict(SeasonalConfig()))
            self.assertEqual(result["status"], "rejected")
            self.assertTrue(Path(result["path"]).exists())
            save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
