import unittest

import numpy as np

from tests.test_td_basin_morphology import fixture
from tools.audit_td_accepted_morphology import audit_fields
from terrain_pipeline.td_material_field import make_material_field


class IndependentAcceptedMorphologyTests(unittest.TestCase):
    def audit(self, result):
        arrays = result["arrays"]
        bed = arrays["original_height_m"]
        source = dict(height_m=bed, valid_mask=np.ones(bed.shape, bool),
            protected_mask=np.zeros(bed.shape, bool), open_boundary_mask=arrays["engineering_open_boundary_mask"])
        material = make_material_field(bed.shape, origin_m_xz=(0, 0), spacing_m=1., parameters={
            "erodibility_range": [1, 1], "weak_path_preference_range": [1, 1], "erodible_thickness_range_m": [4, 4]})
        checkpoint = dict(cumulative_routed_volume_m3=arrays["routed_volume_m3"].ravel(),
                          cumulative_wet_duration_s=arrays["wet_duration_s"].ravel())
        return audit_fields(arrays, result["metadata"], source, dict(receiver=arrays["receiver"]),
                            material["arrays"], material["metadata"], checkpoint, 1.)

    def test_nonzero_incision_closed_storage_and_deposition(self):
        incision = self.audit(fixture())
        deposition = self.audit(fixture(candidate_kind="deposition"))
        self.assertEqual(incision["eroded_cells"], 2)
        self.assertGreater(incision["ledger"]["stored_solid_m3"], 0)
        self.assertEqual(deposition["deposited_cells"], 1)
        self.assertGreater(deposition["ledger"]["deposit_geometry_m3"], 0)
        self.assertAlmostEqual(deposition["ledger"]["source_solid_m3"], deposition["ledger"]["deposited_solid_m3"])

    def test_open_terminal_exports_actual_source_once(self):
        result = self.audit(fixture(parameters={"engineering_open_boundary_cell_ids": [2]}))
        self.assertGreater(result["ledger"]["exported_solid_m3"], 0)
        self.assertEqual(result["ledger"]["stored_solid_m3"], 0)

    def test_conservative_reallocation_does_not_match_frozen_candidate(self):
        result = fixture(candidate_kind="deposition")
        arrays = {name: value.copy() for name, value in result["arrays"].items()}
        transfer = arrays["deposited_solid_m3"][0, 2] / 2
        arrays["deposited_solid_m3"][0, 2] -= transfer
        arrays["stored_solid_m3"][0, 2] += transfer
        forged = dict(result, arrays=arrays)
        with self.assertRaisesRegex(ValueError, "reduction"):
            self.audit(forged)

    def test_stale_water_evidence_rejected(self):
        result = fixture()
        arrays = result["arrays"]
        material = make_material_field((1, 3), origin_m_xz=(0, 0), spacing_m=1.)
        source = dict(height_m=arrays["original_height_m"], valid_mask=np.ones((1, 3), bool),
            protected_mask=np.zeros((1, 3), bool), open_boundary_mask=np.zeros((1, 3), bool))
        checkpoint = dict(cumulative_routed_volume_m3=np.zeros(3), cumulative_wet_duration_s=np.full(3, 3600.))
        with self.assertRaises(AssertionError):
            audit_fields(arrays, result["metadata"], source, dict(receiver=arrays["receiver"]),
                material["arrays"], material["metadata"], checkpoint, 1.)


if __name__ == "__main__":
    unittest.main()
