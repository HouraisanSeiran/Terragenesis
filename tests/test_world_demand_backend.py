"""CPU-only fixed page planning and supervised-provider contracts."""
import tempfile
import unittest
import queue
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from diffusion.world_demand_backend import (PAGE_SIDE, SOURCE_FAMILY, _supervise,
                                            plan_source_pages, run_source_page)


class DemandBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = MagicMock()
        self.config.record.return_value = {"model_dir": "model"}
        self.config.generation_identity.return_value = ("g" * 64, {"conditioning_identity": "c" * 64})

    def test_plans_fixed_grid_including_negative_coordinates(self):
        self.assertEqual(plan_source_pages((0, 0), (20, 20)), [[-24, -24]])
        self.assertEqual(plan_source_pages((460, -1), (2, 10)),
                         [[-24, -488], [440, -488], [-24, -24], [440, -24]])

    def test_generation_records_identity_and_resume(self):
        worker = {"ok": True, "elevation": np.zeros((PAGE_SIDE, PAGE_SIDE)),
                  "generation": {"identity": "g" * 64},
                  "peak_allocator_reserved_mib": 3000.0,
                  "peak_child_rss_mib": 1000.0, "wall_clock_s": 10.0}
        with patch("diffusion.world_demand_backend.PhysicalGenerationConfig", return_value=self.config), \
                patch("diffusion.world_demand_backend.preflight"), \
                patch("diffusion.world_demand_backend._supervise", return_value=worker) as run:
            first = run_source_page((-24, -24), model_dir="model", output_dir=self.temp.name)
            again = run_source_page((-24, -24), model_dir="model", output_dir=self.temp.name)
        self.assertEqual(first["sha256"], again["sha256"])
        self.assertEqual(first["metadata"]["source_family"], SOURCE_FAMILY)
        self.assertEqual(first["metadata"]["physical_generation_identity"], "g" * 64)
        self.assertEqual(run.call_count, 1)

    def test_failure_is_saved_and_not_retried(self):
        with patch("diffusion.world_demand_backend.PhysicalGenerationConfig", return_value=self.config), \
                patch("diffusion.world_demand_backend.preflight"), \
                patch("diffusion.world_demand_backend._supervise", side_effect=RuntimeError("failed")) as run:
            with self.assertRaises(RuntimeError):
                run_source_page((-24, -24), model_dir="model", output_dir=self.temp.name)
            with self.assertRaisesRegex(RuntimeError, "previous source page failure"):
                run_source_page((-24, -24), model_dir="model", output_dir=self.temp.name)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(len(list(Path(self.temp.name).glob("*.failure.json"))), 1)
        self.assertFalse(list(Path(self.temp.name).glob("*.npz")))

    def test_supervisor_rejects_missing_allocator_peak(self):
        context = MagicMock()
        context.Queue.return_value.get.return_value = {"ok": True, "peak_allocator_reserved_mib": None}
        context.Process.return_value.is_alive.return_value = False
        with patch("diffusion.world_demand_backend.mp.get_context", return_value=context):
            with self.assertRaisesRegex(RuntimeError, "allocator peak"):
                _supervise({})

    def test_supervisor_stops_timeout(self):
        context = MagicMock()
        context.Queue.return_value.get.side_effect = queue.Empty
        process = context.Process.return_value
        process.is_alive.side_effect = [True, True, False]
        with patch("diffusion.world_demand_backend.mp.get_context", return_value=context), \
                patch("diffusion.world_demand_backend.time.perf_counter", side_effect=[0.0, 0.0, 121.0]), \
                patch("diffusion.world_demand_backend._child_rss_mib", return_value=1):
            with self.assertRaisesRegex(RuntimeError, "120 s"):
                _supervise({})
        process.terminate.assert_called_once()
