"""CPU-only spawned worker and GPU measurement contracts."""
import multiprocessing as mp
import numpy as np
import unittest
from unittest.mock import MagicMock, patch

from diffusion.world_layout_backend import (BudgetExceeded, _check_driver_monitoring,
                                            _child_gpu_mib, _collect_result,
                                            preflight, run_single_page)
from diffusion.world_layout_conditioning import WorldLayoutGenerationConfig
from terrain_pipeline.world_water_layout import LayoutSpec


def _send_large(queue):
    queue.put({"data": b"x" * 400_000})


def _send_error(queue):
    queue.put({"ok": False, "error": "worker failure"})


def _no_result(queue):
    return


class ProcessTests(unittest.TestCase):
    def test_large_payload_and_error_are_drained_before_join(self):
        context = mp.get_context("spawn")
        for worker in (_send_large, _send_error):
            queue = context.Queue()
            process = context.Process(target=worker, args=(queue,))
            process.start()
            result = _collect_result(process, queue, 10)
            process.join(10)
            self.assertFalse(process.is_alive())
            self.assertIsNotNone(result)
            queue.close()

    def test_missing_result_times_out(self):
        context = mp.get_context("spawn")
        queue = context.Queue()
        process = context.Process(target=_no_result, args=(queue,))
        process.start()
        self.assertIsNone(_collect_result(process, queue, 2))
        process.join(10)
        self.assertFalse(process.is_alive())
        queue.close()

    def test_unavailable_gpu_memory_is_rejected(self):
        class Result:
            returncode = 0
            stdout = "42, N/A\n"
        with patch("subprocess.run", return_value=Result()):
            with self.assertRaises(BudgetExceeded):
                _child_gpu_mib(42)

    def test_wddm_rejected_before_worker_start(self):
        result = MagicMock(returncode=0, stdout="WDDM\n", stderr="")
        with patch("diffusion.world_layout_backend.os.name", "nt"), \
                patch("subprocess.run", return_value=result):
            with self.assertRaises(BudgetExceeded) as caught:
                _check_driver_monitoring()
        self.assertEqual(caught.exception.observed, "WDDM")

    def test_seed_mismatch_rejected_before_preflight(self):
        spec = LayoutSpec("lakes", .12)
        config = WorldLayoutGenerationConfig.from_layout(spec)
        with patch("diffusion.world_layout_backend.preflight") as preflight:
            with self.assertRaisesRegex(ValueError, "seed must match"):
                run_single_page(spec, config, origin_native_xz=(0, 0),
                                model_dir="unused", seed=1)
            preflight.assert_not_called()

    def test_monitor_preserves_budget_failure_detail(self):
        spec = LayoutSpec("lakes", .12)
        config = WorldLayoutGenerationConfig.from_layout(spec)
        context = MagicMock()
        process = context.Process.return_value
        process.is_alive.side_effect = [True, False]
        context.Queue.return_value.get_nowait.side_effect = __import__("queue").Empty
        failure = BudgetExceeded("measurement", "[N/A]", "child GPU memory is unavailable")
        with patch("diffusion.world_layout_backend.preflight"), \
                patch("diffusion.world_layout_backend.mp.get_context", return_value=context), \
                patch("diffusion.world_layout_backend._child_rss_mib", return_value=0), \
                patch("diffusion.world_layout_backend._child_gpu_mib", side_effect=failure):
            with self.assertRaises(BudgetExceeded) as caught:
                run_single_page(spec, config, origin_native_xz=(0, 0), model_dir="unused")
        self.assertIs(caught.exception, failure)
        self.assertEqual(caught.exception.observed, "[N/A]")

    def test_preflight_dispatches_monitor(self):
        torch = MagicMock()
        torch.cuda.is_available.return_value = True
        with patch.dict("sys.modules", {"torch": torch, "psutil": MagicMock()}), \
                patch("diffusion.world_layout_backend._check_driver_monitoring") as check, \
                patch("diffusion.world_layout_backend._device_memory_mib"), \
                patch("diffusion.world_layout_backend.os.path.isdir", return_value=True):
            preflight("unused", gpu_monitor="allocator")
            check.assert_not_called()
            preflight("unused", gpu_monitor="pid")
            check.assert_called_once()

    def test_allocator_requires_peak_within_limit(self):
        spec = LayoutSpec("lakes", .12)
        config = WorldLayoutGenerationConfig.from_layout(spec)
        for peak in (None, 4097.0, 4096.0):
            with self.subTest(peak=peak):
                context = MagicMock()
                process = context.Process.return_value
                process.is_alive.return_value = False
                context.Queue.return_value.get.return_value = {
                    "ok": True, "peak_reserved_mib": peak,
                    "elevation": np.zeros((129, 129), dtype=np.float32),
                    "climate": np.zeros((4, 129, 129), dtype=np.float32)}
                with patch("diffusion.world_layout_backend.preflight") as check, \
                        patch("diffusion.world_layout_backend.mp.get_context", return_value=context), \
                        patch("diffusion.world_layout_backend._child_gpu_mib") as pid_monitor:
                    if peak is None or peak > 4096:
                        with self.assertRaises(BudgetExceeded):
                            run_single_page(spec, config, origin_native_xz=(0, 0),
                                            model_dir="unused", gpu_monitor="allocator")
                    else:
                        result = run_single_page(spec, config, origin_native_xz=(0, 0),
                                                 model_dir="unused", gpu_monitor="allocator")
                        self.assertEqual(result["metadata"]["peak_allocator_reserved_mib"], peak)
                        self.assertEqual(result["metadata"]["gpu_limit_scope"],
                                         "pytorch_allocator_only_excludes_driver_and_other_processes")
                    check.assert_called_once_with("unused", gpu_monitor="allocator")
                    pid_monitor.assert_not_called()
