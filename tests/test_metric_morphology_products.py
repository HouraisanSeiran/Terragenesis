import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import CutoffConfig
from terrain_pipeline.channel_geometry import CutoffMaterialConfig, _corridor, build_cutoff_material_candidate, load_cutoff_material_candidate, save_cutoff_material_candidate, validate_cutoff_material_candidate
from terrain_pipeline.surface_rivers.metric_morphology_product import (
    KINDS, load_morphology_proposal, validate_morphology_proposal,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "verification/td-natural-river-stages/stage3-20261011-complete"


class MorphologyProposalTests(unittest.TestCase):
    def test_six_saved_td_candidates_and_own_synthetic_refusals(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                for suffix, status in (("candidate", "candidate"), ("rejected", "rejected")):
                    path = PACKAGE / (kind + "-" + suffix + ".npz")
                    with patch('terrain_pipeline.surface_hydraulics.solve_channel', side_effect=AssertionError("water solve")), \
                         patch("terrain_pipeline.surface_rivers.metric_sediment.solve_sediment", side_effect=AssertionError("sediment solve")):
                        product = load_morphology_proposal(path, expected_sha256=file_sha256(path))
                    self.assertEqual(product["metadata"]["status"], status)
                    self.assertIn("outlet", product["metadata"]["revalidation_required"])
                    if status == "rejected":
                        self.assertTrue(product["metadata"]["failure_reason"])
                    else:
                        event = product["metadata"]["result"]["event_record"]
                        self.assertTrue(set(event["affected_edges"]).issubset(product["metadata"]["parameters"]["edge_ids"]))

    def test_all_six_rehashed_parent_and_result_tampering_rejected(self):
        for kind in KINDS:
            path = PACKAGE / (kind + "-candidate.npz")
            bundle = load_morphology_proposal(path, expected_sha256=file_sha256(path))
            for target in ("parent_geometry_identity_sha256", "parent_graph_identity_sha256"):
                changed = copy.deepcopy(bundle)
                changed["metadata"][target] = "f" * 64
                changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
                with self.assertRaises(ValueError):
                    validate_morphology_proposal(changed)
            changed = copy.deepcopy(bundle)
            result_key = next(key for key, value in changed["arrays"].items()
                              if key.startswith("result_") and value.size)
            value = changed["arrays"][result_key].copy()
            if value.dtype == bool:
                value.flat[0] = not value.flat[0]
            else:
                value.flat[0] += 1.
            changed["arrays"][result_key] = value
            changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
            with self.assertRaises(ValueError):
                validate_morphology_proposal(changed)


class CutoffMaterialTests(unittest.TestCase):
    def fixture(self, neck=7.):
        t = TerrainGrid(np.zeros((15,15)),np.ones((15,15),bool),0.,0.,1.,1.,"diagnostic_dem_proxy","cutoff-native","a"*64)
        points = np.array([[2.,2.],[2.,8.],[5.,8.],[8.,8.],[8.,2.],[10.,2.]])
        mc = CutoffMaterialConfig(corridor_half_width_m=.5,shortcut_cut_depth_m=.1,old_channel_fill_depth_m=.02)
        old = _corridor(t,points,.5)
        return build_cutoff_material_candidate(t,points,tuple("e%d"%i for i in range(5)),old*.1,old*.01,
            np.full((15,15),.05),np.full((15,15),-1.),CutoffConfig(neck_distance_m=neck,min_loop_length_m=5.),mc)

    def test_cut_loose_rock_fill_and_residual_vh_independent(self):
        b=self.fixture();a,m=b["arrays"],b["metadata"]
        self.assertEqual(m["status"],"candidate")
        self.assertFalse(np.any(a["shortcut_mask"] & a["residual_mask"]))
        np.testing.assert_allclose(a["cut_alluvium_bulk_m3"]*.65+a["cut_rock_m3"],a["cut_solid_m3"])
        np.testing.assert_allclose(a["fill_bulk_m3"]*.65,a["fill_solid_m3"])
        self.assertAlmostEqual(a["cut_solid_m3"].sum(),a["fill_solid_m3"].sum()+m["material_ledger"]["unresolved_solid_m3"])
        np.testing.assert_allclose(a["residual_water_m3"]+a["surviving_water_m3"],a["initial_water_depth_m"])
        stage=m["event_record"]["parameters"]["residual_level_pool_stage_m"]
        self.assertAlmostEqual(np.maximum(stage-a["after_bed_m"][a["residual_mask"]],0.).sum(),a["residual_water_m3"].sum())
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"cutoff.npz";save_cutoff_material_candidate(p,b)
            self.assertEqual(load_cutoff_material_candidate(p,expected_sha256=file_sha256(p))["identity_sha256"],b["identity_sha256"])

    def test_no_neck_refusal_and_rehashed_inventory_or_material_rejected(self):
        rejected=self.fixture(neck=1.)
        self.assertEqual(rejected["metadata"]["status"],"rejected")
        self.assertTrue(validate_cutoff_material_candidate(rejected))
        for field in ("residual_water_m3","cut_rock_m3","fill_bulk_m3"):
            b=copy.deepcopy(self.fixture());b["arrays"][field]=b["arrays"][field].copy()+.01
            b["identity_sha256"]=identity(b["arrays"],b["metadata"])
            with self.assertRaises(ValueError):validate_cutoff_material_candidate(b)


if __name__=="__main__":
    unittest.main()
