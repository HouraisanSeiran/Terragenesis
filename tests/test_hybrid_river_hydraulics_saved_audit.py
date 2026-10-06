import copy
import unittest

from tools.audit_hybrid_river_hydraulics import compare_saved, section_area


class SavedHydraulicsAuditTests(unittest.TestCase):
    def test_actual_open_closed_and_pressure_section_storage(self):
        surface = {"kind": "open_polyline", "polyline_transverse_elevation_m": [[-1, 100], [0, 99], [1, 100]]}
        self.assertAlmostEqual(section_area(surface, 99.5), .25)
        cave = {"kind": "closed_polygon", "polygon_transverse_elevation_m": [[-1, 99], [1, 99], [1, 101], [-1, 101]], "pressure_slot_width_m": .02}
        self.assertAlmostEqual(section_area(cave, 100), 2)
        self.assertAlmostEqual(section_area(cave, 102), 4.02)

    def test_cold_refinement_rejects_hidden_internal_exchange_difference(self):
        base = {"cell_ids": ["first", "second", "third"], "times_s": [0, 1],
                "hydraulic_head_m": [[1, 1, 1], [1, 1, 1]], "water_volume_m3": [[1, 1, 1], [1, 1, 1]],
                "source_tracer_mass_m3": [[0, 0, 0], [0, 0, 0]], "tailwater_tracer_mass_m3": [[0, 0, 0], [0, 0, 0]],
                "boundary_ledger_m3": [[0] * 6, [0] * 6]}
        for key in ("paired_link_water_integral_m3", "paired_link_source_integral_m3", "paired_link_tailwater_integral_m3"):
            base[key] = [[0, 0], [1, 1]]
        compare_saved(base, copy.deepcopy(base))
        changed = copy.deepcopy(base)
        changed["paired_link_water_integral_m3"][1][0] = 2
        with self.assertRaisesRegex(ValueError, "paired link refinement"):
            compare_saved(base, changed)


if __name__ == "__main__":
    unittest.main()
