"""Direction-aware chart sampling for cliff review curves."""
import unittest
import numpy as np
from tools.prepare_vdm_gallery import _parameter_section

class GallerySectionTests(unittest.TestCase):

    def test_rotated_section_samples_affine_xyz_field(self):
        row, column = np.indices((41, 41))
        reference = np.stack((column - 20, 2 * column - row, row - 20), axis=-1).astype(float)
        vertices = reference.copy()
        vertices[..., 0] += 0.25 * reference[..., 2]
        vertices[..., 1] += 0.5 * reference[..., 0]
        along = np.array([0.6, 0.8])
        outward = np.array([-0.8, 0.6])
        base, shaped = _parameter_section(reference, vertices, np.zeros(2), along, outward, 3, 8)
        np.testing.assert_allclose(base[:, [0, 2]] @ along, 3, atol=1e-12)
        np.testing.assert_allclose((base[:, [0, 2]] @ outward)[[0, -1]], [-8, 8])
        np.testing.assert_allclose(shaped[:, 0], base[:, 0] + 0.25 * base[:, 2])
        np.testing.assert_allclose(shaped[:, 1], base[:, 1] + 0.5 * base[:, 0])

    def test_section_outside_chart_rejected(self):
        row, column = np.indices((5, 5))
        reference = np.stack((column, np.zeros_like(row), row), axis=-1).astype(float)
        with self.assertRaisesRegex(ValueError, 'outside reference chart'):
            _parameter_section(reference, reference, np.array([2, 2]), np.array([1, 0]), np.array([0, 1]), 0, 8)
if __name__ == '__main__':
    unittest.main()
