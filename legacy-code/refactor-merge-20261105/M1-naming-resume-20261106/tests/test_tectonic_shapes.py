"""External directional and periodic behavior of bounded growth priors."""
import unittest

import numpy as np

from terrain_pipeline.tectonic import periodic_shape_distance, shape_parameters


def parameters(family="ellipse", angle=0., aspect=4., scale=1.):
    return dict(family=family, angle_rad=angle, aspect_ratio=aspect, scale_cells=scale)


class ShapeTests(unittest.TestCase):
    def test_circle_rotation_and_ellipse_direction(self):
        points = np.array([[12., 0.], [0., 12.], [3., -7.]])
        circle = periodic_shape_distance(points, [100, 100], parameters("circle", aspect=1.))
        np.testing.assert_array_equal(circle, periodic_shape_distance(
            points, [100, 100], parameters("circle", angle=1.7, aspect=1.)))
        ellipse = periodic_shape_distance(points, [100, 100], parameters())
        self.assertLess(ellipse[0], ellipse[1])
        rotated = periodic_shape_distance(points, [100, 100], parameters(angle=np.pi / 2))
        np.testing.assert_allclose(ellipse[:2], rotated[:2][::-1])

    def test_triangle_tip_and_rotation_differ_from_symmetric_shapes(self):
        points = np.array([[10., 0.], [-10., 0.]])
        triangle = periodic_shape_distance(points, [100, 100], parameters("triangle", aspect=1.))
        np.testing.assert_allclose(triangle, [10., 20.])
        rotated = periodic_shape_distance(points, [100, 100], parameters("triangle", np.pi, 1.))
        np.testing.assert_allclose(triangle, rotated[::-1])
        for family, aspect in (("circle", 1.), ("ellipse", 4.)):
            symmetric = periodic_shape_distance(points, [100, 100], parameters(family, aspect=aspect))
            self.assertEqual(symmetric[0], symmetric[1])

    def test_periodic_minimum_can_use_non_euclidean_nearest_image(self):
        # Both anisotropic ellipse and directed triangle need non-nearest images.
        for family in ("ellipse", "triangle"):
            p = parameters(family, angle=.7, aspect=6.)
            period = np.array([40., 30.])
            points = np.array([[19., -14.], [-17., 13.], [2., 8.]])
            actual = periodic_shape_distance(points, period, p)
            # Independent explicit gauge and generous 41x41 reference enumeration.
            reference = np.full(3, np.inf)
            nearest = None
            for ix in range(-20, 21):
                for iz in range(-20, 21):
                    q = points + period * (ix, iz)
                    u = (q[:, 0] * np.cos(.7) + q[:, 1] * np.sin(.7)) / np.sqrt(6)
                    v = (-q[:, 0] * np.sin(.7) + q[:, 1] * np.cos(.7)) * np.sqrt(6)
                    value = np.hypot(u, v) if family == "ellipse" else np.maximum.reduce(
                        (u + np.sqrt(3) * v, -2 * u, u - np.sqrt(3) * v))
                    reference = np.minimum(reference, value)
                    if ix == iz == 0:
                        nearest = value
            np.testing.assert_allclose(actual, reference)
            self.assertTrue(np.any(actual < nearest - 1e-8))
            np.testing.assert_allclose(actual, periodic_shape_distance(
                points + period * [11, -9], period, p))

    def test_invalid_inputs_and_resource_budget(self):
        for p in (parameters(aspect=0), parameters(aspect=7), parameters(angle=np.nan),
                  parameters(scale=0), parameters("unknown"), parameters(angle=1e100)):
            with self.subTest(parameters=p), self.assertRaises(ValueError):
                periodic_shape_distance([[1, 2]], [100, 100], p)
        for period, point in (([0, 2], [1, 2]), ([2, np.inf], [1, 2]),
                              ([2, 2], [np.nan, 2]), ([1e-8, 100], [0, 49])):
            with self.subTest(period=period), self.assertRaises(ValueError):
                periodic_shape_distance([point], period, parameters())
        self.assertEqual(shape_parameters(20261020, 8), shape_parameters(20261020, 8))


if __name__ == "__main__":
    unittest.main()
