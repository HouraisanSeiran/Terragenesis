"""Behaviour tests for the explicit window budget on the Terrain Diffusion backend.

The 513 guard was a guard, not a model limit: the decoder already runs in 512/384
tiles, and measured 1025/2049 windows peak at the same 2.2 GiB. These tests pin the
replacement contract, which is what keeps "raise the window" from silently becoming
"raise it until the machine dies":

* an int within the budget is accepted and reports its own numbers;
* anything above the budget is **refused with a reason code**, never downscaled and
  never split;
* a non-positive or non-integer size is refused with its own reason code;
* the old `size = 513` case is still accepted, so existing 513 products keep their
  meaning;
* the budget constant and the reference measurement are visible in the metadata the
  backend returns, so a report can quote them.

No GPU and no model weights are needed here: only `window_budget` and `_peak_cuda_mib`
are exercised.
"""
import unittest

from diffusion import physical_backend as backend


class WindowBudgetTests(unittest.TestCase):
    def test_a_size_inside_the_budget_is_accepted_and_reports_its_numbers(self):
        budget = backend.window_budget(1337)
        self.assertEqual(budget["window_cells"], 1337)
        self.assertEqual(budget["cells"], 1337 * 1337)
        self.assertEqual(budget["max_window_cells"], backend.MAX_WINDOW_CELLS)
        self.assertLessEqual(budget["cells"], backend.MAX_WINDOW_CELLS ** 2)
        self.assertGreater(budget["cell_fraction_of_max"], 0.0)

    def test_the_old_513_window_is_still_accepted(self):
        """Raising the guard must not change what 513 used to mean."""
        budget = backend.window_budget(513)
        self.assertEqual(budget["cells"], 513 * 513)
        self.assertLess(budget["cell_fraction_of_max"], 1.0)

    def test_a_size_above_the_budget_is_refused_with_a_reason_code(self):
        over = backend.MAX_WINDOW_CELLS + 1
        with self.assertRaises(ValueError) as caught:
            backend.window_budget(over)
        message = str(caught.exception)
        self.assertIn(backend.WINDOW_BUDGET_EXCEEDED, message)
        self.assertIn(str(over * over), message)
        # The refusal must say the number was not quietly changed, and must quote the
        # measurement that justifies the ceiling instead of asserting it.
        self.assertIn("refused rather than", message)
        self.assertIn("measured reference", message)

    def test_a_non_positive_size_is_refused(self):
        for size in (0, -1, -1337):
            with self.subTest(size=size):
                with self.assertRaises(ValueError) as caught:
                    backend.window_budget(size)
                self.assertIn(backend.WINDOW_NOT_POSITIVE, str(caught.exception))

    def test_a_non_integer_size_is_refused(self):
        """A float that happens to be whole is still refused: the count is a node count."""
        for size in (513.0, "1337", None, True):
            with self.subTest(size=size):
                with self.assertRaises(ValueError) as caught:
                    backend.window_budget(size)
                self.assertIn(backend.WINDOW_NOT_INTEGER, str(caught.exception))

    def test_the_budget_carries_the_measurement_it_is_based_on(self):
        budget = backend.window_budget(1025)
        reference = budget["declared_reference"]
        self.assertEqual(reference["device"], backend.WINDOW_BUDGET_REFERENCE["device"])
        self.assertIn(2049, reference["window_cells"])
        self.assertIsNotNone(reference["peak_cuda_mib"])

    def test_the_ceiling_is_the_declared_constant_not_a_scaled_one(self):
        """The exact boundary is inclusive; one past it is not."""
        accepted = backend.window_budget(backend.MAX_WINDOW_CELLS)
        self.assertEqual(accepted["cell_fraction_of_max"], 1.0)
        with self.assertRaises(ValueError):
            backend.window_budget(backend.MAX_WINDOW_CELLS + 1)

    def test_peak_memory_without_cuda_reports_a_reason_instead_of_a_number(self):
        """A CPU-only run must not invent a peak figure."""
        value, status = backend._peak_cuda_mib()
        if value is None:
            self.assertTrue(status, "a missing peak must carry a reason")
        else:
            self.assertGreaterEqual(value, 0.0)


if __name__ == "__main__":
    unittest.main()
