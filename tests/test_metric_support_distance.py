import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from terrain_pipeline.channel_geometry import _segment_box_distance
from terrain_pipeline.channel_geometry import _segment_boxes_distance, _sparse_cells


class BatchedSupportDistanceTests(unittest.TestCase):
    def assert_distance_equal(self, a, b, low, high):
        scalar = np.array([_segment_box_distance(a, b, lo, hi) for lo, hi in zip(low, high)])
        batched = _segment_boxes_distance(a, b, low, high)
        np.testing.assert_array_equal(batched, scalar)
        for radius in (0.0, 0.5, 1.0, np.sqrt(2.0), 3.5):
            np.testing.assert_array_equal(batched <= radius + 1e-10,
                                          scalar <= radius + 1e-10)

    def test_axis_diagonal_corner_touch_and_large_world_coordinates(self):
        x, z = np.meshgrid(np.arange(-3.0, 12.0), np.arange(-3.0, 12.0))
        boxes = np.column_stack((x.ravel(), z.ravel()))
        segments = (
            (np.array([0.0, 2.0]), np.array([8.0, 2.0])),
            (np.array([2.0, 8.0]), np.array([2.0, 0.0])),
            (np.array([0.0, 0.0]), np.array([8.0, 8.0])),
            (np.array([1.125, 2.75]), np.array([8.375, 5.625])),
            (np.array([8.375, 5.625]), np.array([1.125, 2.75])),
            (np.array([0.0, 0.0]), np.array([2.0, 2.0])),
        )
        for offset in (np.zeros(2), np.array([1_228_800.0, 2_457_600.0])):
            for a, b in segments:
                with self.subTest(offset=offset, a=a, b=b):
                    self.assert_distance_equal(a + offset, b + offset,
                                               boxes + offset, boxes + offset + 1.0)

    def test_radius_threshold_preserves_tangency_tolerance(self):
        a, b = np.array([0.0, 0.0]), np.array([2.0, 0.0])
        low = np.array([[0.5, 1.0], [0.5, 1.0 + 0.5e-10], [0.5, 1.0 + 2e-10]])
        distances = _segment_boxes_distance(a, b, low, low + 1.0)
        np.testing.assert_array_equal(distances <= 1.0 + 1e-10, [True, True, False])
        self.assert_distance_equal(a, b, low, low + 1.0)

    def test_optional_real_saved_s4c9_every_candidate_and_sorted_support_match(self):
        path = Path(__file__).resolve().parents[1] / "verification/td-terrain-generated-rivers/shape-repair-20261012-09-s4c9/sample-4-component-9.npz"
        if not path.is_file():
            self.skipTest("optional integration case: real TD saved artifact required")
        with np.load(path, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata"]))
            terrain = SimpleNamespace(elevation_m=archive["source_height_m"],
                                      **{key: metadata["terrain_metadata"][key]
                                         for key in ("x0_m", "z0_m", "dx_m", "dz_m")})
            points, receiver, width = archive["node_xz_m"], archive["receiver"], archive["width_m"]
            profile = tuple(archive[key] for key in
                            ("profile_offsets", "profile_t", "profile_source_m", "profile_center_bed_m"))
            saved_cells = archive["sparse_cell_xy"]
        spacing = metadata["config"]["fine_spacing_m"]
        edges = np.flatnonzero(receiver >= 0)
        radii = np.maximum(width[edges], width[receiver[edges]]) / 2.0 + (np.sqrt(2.0) + 1.0) * spacing + 2.0 * metadata["config"]["max_cut_m"]
        origin = np.array([terrain.x0_m, terrain.z0_m])
        maximum = np.array([(terrain.elevation_m.shape[1] - 1) * round(terrain.dx_m / spacing),
                            (terrain.elevation_m.shape[0] - 1) * round(terrain.dz_m / spacing)], np.int64)
        expected = set()
        for edge, i in enumerate(edges):
            a, b, radius = points[i], points[receiver[i]], radii[edge]
            first = np.maximum(np.floor((np.minimum(a, b) - radius - origin) / spacing).astype(int), 0)
            last = np.minimum(np.ceil((np.maximum(a, b) + radius - origin) / spacing).astype(int), maximum)
            x, z = np.meshgrid(np.arange(first[0], last[0]), np.arange(first[1], last[1]))
            cells = np.column_stack((x.ravel(), z.ravel()))
            low = origin + spacing * cells
            scalar = np.array([_segment_box_distance(a, b, lo, lo + spacing) for lo in low])
            batched = _segment_boxes_distance(a, b, low, low + spacing)
            np.testing.assert_array_equal(scalar, batched)
            expected.update(map(tuple, cells[scalar <= radius + 1e-10]))
        expected = np.asarray(sorted(expected, key=lambda cell: (cell[1], cell[0])), np.int64)
        actual = _sparse_cells(points, receiver, width, profile,
                               SimpleNamespace(fine_spacing_m=spacing, max_vertices=8_000_000),
                               terrain, support_radius_m=radii)
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(actual, saved_cells)


if __name__ == "__main__":
    unittest.main()
