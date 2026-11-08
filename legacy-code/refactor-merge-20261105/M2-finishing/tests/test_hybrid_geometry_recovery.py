"""Keep VC-03's precision blocker explicit; never trim or accept collapsed area."""

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import unittest

from shapely.geometry import Polygon

from tools.hybrid_geometry_audit_base import saved_slice_geometry
from tools.hybrid_saved_slice_geometry_adapter import consume_saved_slice


ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / ".scratch/module-version-consolidation-20261022/current-geometry-run04"
ORIGINAL = ROOT / "verification/natural-river-network/hybrid-surface-composition-20261006-03/composition.json"
CURRENT_SHA256 = "3bb73b2843316ebe89766c07684b7a31f96099498eb028b5e4f5431498c2efc4"
ORIGINAL_SHA256 = "88ed045a0589d130a2622cba3b4ace4a139b6513ebca2616a1bae67bdda0e4b6"
COLLAPSED_RING = [[0.0, 0.0], [1.0000000000003293, 0.1359761555989476],
                  [1.876967859454453, 0.25522287371131824]]
POSITIVE_SLIVER = [[1.876967859454453, 0.25522287371131824],
                   [2.6482670089858793, 0.7457507416435617],
                   [2.6494438944122187, 0.7464992127125799]]


def exact_binary64_area(ring):
    values = [(Fraction(float(x)), Fraction(float(y))) for x, y in ring]
    return sum((start[0] * end[1] - end[0] * start[1]
                for start, end in zip(values, values[1:] + values[:1])), Fraction(0)) / 2


def read_pinned(path, expected):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise AssertionError("recovery evidence SHA256 changed: " + str(path))
    return json.loads(raw)


class HybridGeometryPrecisionBlockerTests(unittest.TestCase):
    def test_exact_nonzero_triangle_with_zero_display_area_stays_rejected(self):
        self.assertEqual(exact_binary64_area(COLLAPSED_RING),
                         Fraction(-16176346637, 1237940039285380274899124224))
        polygon = Polygon(COLLAPSED_RING)
        self.assertTrue(polygon.is_valid)
        self.assertEqual(polygon.area, 0.0)
        record = {"polygons_uv_m": [COLLAPSED_RING], "holes_uv_m": [[]], "area_m2": 0.0}
        with self.assertRaisesRegex(ValueError, "invalid saved slice with holes"):
            saved_slice_geometry(record)
        with self.assertRaisesRegex(ValueError, "exact nonzero exterior has zero display area"):
            consume_saved_slice(record)

    def test_positive_display_sliver_is_preserved_without_area_threshold(self):
        expected = Polygon(POSITIVE_SLIVER)
        self.assertGreater(expected.area, 0.0)
        self.assertLess(expected.area, 1e-8)
        record = {"polygons_uv_m": [POSITIVE_SLIVER], "holes_uv_m": [[]],
                  "area_m2": expected.area}
        for reader in (saved_slice_geometry, consume_saved_slice):
            with self.subTest(reader=reader.__name__):
                actual = reader(record)
                self.assertTrue(actual.equals(expected))
                self.assertEqual(set(actual.exterior.coords), set(expected.exterior.coords))
                self.assertEqual(abs(exact_binary64_area(list(actual.exterior.coords)[:-1])),
                                 abs(exact_binary64_area(POSITIVE_SLIVER)))
                self.assertGreater(actual.area, 0.0)
                self.assertLess(actual.area, 1e-8)

    def test_mixed_domain_is_not_repaired_by_dropping_collapsed_component(self):
        record = {"polygons_uv_m": [POSITIVE_SLIVER, COLLAPSED_RING],
                  "holes_uv_m": [[], []], "area_m2": Polygon(POSITIVE_SLIVER).area}
        for reader in (saved_slice_geometry, consume_saved_slice):
            with self.subTest(reader=reader.__name__), self.assertRaises(ValueError):
                reader(record)
        self.assertEqual(record["polygons_uv_m"], [POSITIVE_SLIVER, COLLAPSED_RING])


@unittest.skipUnless((CURRENT / "composition.json").is_file() and ORIGINAL.is_file(),
                     "fixed VC-03 recovery artifacts are unavailable")
class HybridGeometrySavedRecoveryTests(unittest.TestCase):
    def test_fixed_saved_blocker_is_unchanged_from_original(self):
        current = read_pinned(CURRENT / "composition.json", CURRENT_SHA256)
        original = read_pinned(ORIGINAL, ORIGINAL_SHA256)
        domain = current["portal_connections"]["sink"]["blocked_domain"]
        self.assertEqual(domain, original["portal_connections"]["sink"]["blocked_domain"])
        self.assertEqual(domain["polygons_uv_m"], [POSITIVE_SLIVER, COLLAPSED_RING])
        with self.assertRaisesRegex(ValueError, "invalid saved slice with holes"):
            saved_slice_geometry(domain)
        with self.assertRaisesRegex(ValueError, "exact nonzero exterior has zero display area"):
            consume_saved_slice(domain)

    def test_failed_integration_is_refused_with_checkpoint_not_successful_faces(self):
        index = json.loads((CURRENT / "index.json").read_bytes())
        from tools.td_shared_channel_fine_saved_audit import check_identity
        check_identity(index)
        self.assertEqual(index["status"], "refused")
        self.assertEqual(index["errors"], ["ValueError: invalid saved slice with holes"])
        self.assertEqual(index["stages_completed"],
                         ["fresh-main-Boolean-saved", "rational-port-stage-saved"])
        self.assertFalse(index["hydraulic_ready"])
        self.assertFalse(index["publishable"])
        for name in ("boolean_checkpoint", "boolean_index", "composition"):
            path = Path(index[name]["path"])
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), index[name]["sha256"])
        for name in ("composition_audit", "faces", "faces_audit"):
            self.assertNotIn(name, index)
        for name in ("composition-audit.json", "faces.json", "faces-audit.json"):
            self.assertFalse((CURRENT / name).exists())


if __name__ == "__main__":
    unittest.main()
