"""Regression for preserving VDM curvature during local fault cuts."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.metric_vdm_fault_v2 import apply_fault, load_fault, save_fault, validate_fault
from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from tests.test_metric_vdm_fault import source, selection, recipe


class DeformedFaultTests(unittest.TestCase):
    def test_zero_slip_keeps_deformed_source_not_original_chart(self):
        original = source()
        result = apply_fault(original, recipe=recipe(slip=0.), selection_mask=selection())
        arrays = result["arrays"]
        exact = arrays["vertex_source_index"] >= 0
        source_index = arrays["vertex_source_index"][exact]
        np.testing.assert_allclose(arrays["vertices_xyz_m"][exact], original["arrays"]["vertices_xyz_m"][source_index])
        self.assertGreater(np.max(np.abs(original["arrays"]["vertices_xyz_m"] - original["arrays"]["reference_xyz_m"].reshape(-1, 3))), 1.)
        np.testing.assert_array_equal(arrays["source_vertices_xyz_m"], original["arrays"]["vertices_xyz_m"])

    def test_edge_interpolation_is_independent_of_triangle_vertex_order(self):
        original = source()
        result = apply_fault(original, recipe=recipe(strike=18.), selection_mask=selection())
        arrays = result["arrays"]
        edges = arrays["vertex_source_edge"]
        fraction = arrays["vertex_source_fraction"][:, None]
        before = original["arrays"]["vertices_xyz_m"][edges[:, 0]] * (1. - fraction) + original["arrays"]["vertices_xyz_m"][edges[:, 1]] * fraction
        np.testing.assert_allclose(arrays["vertices_xyz_m"] - arrays["applied_displacement_xyz_m"], before, atol=1e-10)
        self.assertGreater(np.count_nonzero(arrays["vertex_source_index"] < 0), 0)
        self.assertLess(result["metadata"]["cut_source_triangle_count"], len(original["arrays"]["triangles"]))

    def test_negative_slip_and_saved_cold_read(self):
        original = source()
        result = apply_fault(original, recipe=recipe(slip=-2., strike=18.), selection_mask=selection())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fault.npz"
            save_fault(path, result)
            loaded = load_fault(path, expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"])
            self.assertTrue(validate_fault(loaded))
            self.assertTrue(all(not value.flags.writeable for value in loaded["arrays"].values()))

    def test_geometry_erasure_rejected_even_with_updated_identity(self):
        result = apply_fault(source(), recipe=recipe(), selection_mask=selection())
        arrays = {key: value.copy() for key, value in result["arrays"].items()}
        arrays["vertices_xyz_m"][0, 1] += 1.
        corrupted = {"arrays": arrays, "metadata": result["metadata"], "identity_sha256": identity(arrays, result["metadata"])}
        with self.assertRaisesRegex(ValueError, "erased source"):
            validate_fault(corrupted)

    def test_swept_patch_protection_is_not_just_selection_protection(self):
        protected = np.zeros((25, 25), bool)
        protected[15, 22] = True
        original = source(protected=protected)
        self.assertFalse(np.any(selection() & protected))
        with self.assertRaisesRegex(ValueError, "swept"):
            apply_fault(original, recipe=recipe(slip=12.), selection_mask=selection())


if __name__ == "__main__":
    unittest.main()
