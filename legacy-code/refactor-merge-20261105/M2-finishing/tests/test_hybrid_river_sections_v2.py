import math
import tempfile
from pathlib import Path
import unittest

from terrain_pipeline.hybrid_hydraulics import common_Section as Section
from terrain_pipeline.hybrid_hydraulics import FastSection
from tools.hybrid_hydraulics_preparation_common import atomic_save


class FastSectionTests(unittest.TestCase):
    def compare(self, record):
        original = Section.from_record(record)
        fast = FastSection(original)
        heads = [fast.floor_m - 0.25, fast.floor_m, fast.levels_m[-1] + 0.25, fast.levels_m[-1] + 3]
        for height in fast.levels_m:
            heads.extend((math.nextafter(height, -math.inf), height, math.nextafter(height, math.inf)))
        heads.extend((lower + (upper - lower) / 2) for lower, upper in zip(fast.levels_m[:-1], fast.levels_m[1:]))
        for head in heads:
            with self.subTest(kind=record["kind"], head=head):
                expected_area, expected_perimeter = original.area_perimeter(head)
                area, perimeter = fast.area_perimeter(head)
                self.assertAlmostEqual(area, expected_area, delta=1e-10)
                self.assertAlmostEqual(perimeter, expected_perimeter, delta=1e-9)
                self.assertAlmostEqual(area * 8.125, expected_area * 8.125, delta=1e-9)
                if area > 0:
                    self.assertAlmostEqual(fast.head_for_area(area), head, delta=1e-10)
                    self.assertAlmostEqual(fast.head_for_area(area), original.head_for_area(area), delta=2e-10)
        return fast

    def test_actual_linear_sections_breakpoints_pressure_and_open_bench(self):
        self.compare({"kind": "open_polyline", "polyline_transverse_elevation_m": [
            [-3.1160651283571497, 1367.680989361264], [-1.876967859454453, 1366.8883733087805],
            [0.0, 1366.626213114155], [1.876967859454453, 1366.5685119310874],
            [3.1160651283571497, 1367.1499686088753]], "sidewall_extension": "explicit_engineering_vertical"})
        closed = self.compare({"kind": "closed_polygon", "polygon_transverse_elevation_m": [
            [-3.1967823050840103, 1361.9088846317172], [-1.9354601538332739, 1361.1410485018523],
            [0.0, 1360.9324492759495], [1.9354601538332739, 1360.9335159861266],
            [3.1967823050840103, 1361.5633909417586], [3.25678230507099, 1363.8488846317173],
            [-3.25678230507099, 1363.8488846317173]], "pressure_slot_width_m": 0.02})
        self.assertAlmostEqual(closed.area_perimeter(closed.crown_m + 1)[0] - closed.area_perimeter(closed.crown_m)[0], 0.02)
        for origin in (0.0, 1360.0):
            bench = self.compare({"kind": "open_polyline", "polyline_transverse_elevation_m": [[0, origin], [1, origin], [2, origin + 1], [3, origin + 1]], "sidewall_extension": "explicit_engineering_vertical"})
            self.assertAlmostEqual(bench.area_perimeter(origin + 0.5)[0], 0.625)
            self.assertAlmostEqual(bench.area_perimeter(origin + 1)[0], 1.5)
            self.assertAlmostEqual(bench.area_perimeter(origin + 1)[1], 2 + math.sqrt(2))
            self.assertAlmostEqual(bench.area_perimeter(math.nextafter(origin + 1, math.inf))[1], 3 + math.sqrt(2))

    def test_nonconvex_multispan_narrowing_fallback_invalid_and_checkpoint(self):
        shape = self.compare({"kind": "closed_polygon", "polygon_transverse_elevation_m": [[0, 0], [1, 0], [1, 2], [3, 2], [3, 0], [4, 0], [4, 4], [0, 4]], "pressure_slot_width_m": 0.02})
        for head, area, perimeter in ((1, 2, 6), (2, 4, 12), (3, 8, 14), (4, 12, 20), (5, 12.02, 20)):
            self.assertAlmostEqual(shape.area_perimeter(head)[0], area)
            self.assertAlmostEqual(shape.area_perimeter(head)[1], perimeter)
        self.assertAlmostEqual(shape.area_perimeter(math.nextafter(2, -math.inf))[1], 10)
        self.assertAlmostEqual(shape.area_perimeter(math.nextafter(4, -math.inf))[1], 16)
        narrowing = self.compare({"kind": "closed_polygon", "polygon_transverse_elevation_m": [[0, 0], [4, 0], [3, 2], [1, 2]], "pressure_slot_width_m": 0.02})
        self.assertAlmostEqual(narrowing.area_perimeter(1)[0], 3.5)
        self.assertAlmostEqual(narrowing.area_perimeter(1)[1], 4 + math.sqrt(5))
        original = Section.from_record({"kind": "native_bed", "pieces": [{"width_m": 2, "bed_coefficients_m_t012": [1360, 0, 1]}], "sidewall_extension": "explicit_engineering_vertical"})
        fallback = FastSection(original)
        self.assertEqual(fallback.bands, ())
        self.assertEqual(fallback.area_perimeter(1360.5), original.area_perimeter(1360.5))
        self.assertEqual(fallback.head_for_area(0.25), original.head_for_area(0.25))
        for area in (-1e-16, 0, math.nan, math.inf):
            with self.assertRaises(ValueError):
                shape.head_for_area(area)
        with self.assertRaises(ValueError):
            shape.area_perimeter(math.nan)
        with self.assertRaises(ValueError):
            FastSection.from_record({"kind": "closed_polygon", "polygon_transverse_elevation_m": [[0, 0], [1, 1], [0, 1], [1, 0]], "pressure_slot_width_m": 0.02})
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            completed = atomic_save(output, "pulse-base.json", {"status": "diagnostic_completed", "value": 1})
            before = (output / "pulse-base.json").read_bytes()
            atomic_save(output, "checkpoint.json", {"status": "failed_partial", "artifacts": {"pulse-base.json": completed}})
            self.assertEqual(before, (output / "pulse-base.json").read_bytes())
            self.assertFalse(list(output.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
