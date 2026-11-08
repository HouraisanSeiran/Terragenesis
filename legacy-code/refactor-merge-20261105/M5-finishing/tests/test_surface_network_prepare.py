import tempfile
import unittest
from pathlib import Path
import json

import numpy as np
from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest

from terrain_pipeline.surface_hydraulics import InundationRecipe
from terrain_pipeline.surface_hydraulics import StageRecipe
from terrain_pipeline.channel_geometry import SectionRecipe
from terrain_pipeline.surface_domain import SurfaceNetworkBudget, load_surface_network, prepare_surface_network, save_surface_network, slice_surface_network
from tests.test_channel_stage_inundation import confluence_plan


class SurfaceNetworkPrepareTests(unittest.TestCase):
    def make_result(self, budget):
        plan = confluence_plan()
        domain = np.ones((61, 61), bool)
        protected = np.zeros((61, 61), bool)
        legal = np.zeros((61, 61), bool)
        legal[-1, 27:34] = True
        result = prepare_surface_network(plan, 0., 0., 1., 1., (61, 61), domain,
            protected, legal, np.array([5.2]), SectionRecipe(),
            StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
            InundationRecipe(max_lateral_reach_m=15.), budget)
        return plan, result

    def test_confluence_prepared_and_reloaded(self):
        plan, result = self.make_result(SurfaceNetworkBudget(4., 5000., 5000.))
        self.assertEqual(result["status"], "prepared")
        self.assertGreater(result["summary"]["cut_volume_m3"], 0)
        self.assertEqual(result["summary"]["max_stage_bed_error_m"], 0)
        self.assertTrue(result["arrays"]["wet_mask"].any())
        np.testing.assert_array_equal(plan["arrays"]["source_height_m"], confluence_plan()["arrays"]["source_height_m"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "surface.npz"
            save_surface_network(result, path)
            loaded = load_surface_network(path)
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
            with np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files if name != "manifest"}
                manifest = archive["manifest"].item()
            arrays["bed_cut_m"] = arrays["bed_cut_m"].copy()
            arrays["bed_cut_m"][0, 0] += 1
            np.savez_compressed(path, manifest=manifest, **arrays)
            with self.assertRaises(ValueError):
                load_surface_network(path)

    def test_budget_failure_refuses_publication(self):
        _, result = self.make_result(SurfaceNetworkBudget(4., 10., 10.))
        self.assertFalse(result["summary"]["publishable"])
        self.assertTrue(result["summary"]["budget_failures"]["area"])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                save_surface_network(result, Path(directory) / "failed.npz")

    def test_semantic_summary_tamper_rejected(self):
        _, result = self.make_result(SurfaceNetworkBudget(4., 5000., 5000.))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "surface.npz"
            save_surface_network(result, path)
            with np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files if name != "manifest"}
                manifest = json.loads(str(archive["manifest"].item()))
            manifest["summary"]["joint_blockers"]["stage"] = True
            np.savez_compressed(path, manifest=json.dumps(manifest), **arrays)
            with self.assertRaises(ValueError):
                load_surface_network(path)

    def test_reidentified_failed_result_cannot_publish(self):
        _, result = self.make_result(SurfaceNetworkBudget(4., 10., 10.))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forged.npz"
            summary = json.loads(json.dumps(result["summary"]))
            summary["publishable"] = True
            identity_record = json.loads(json.dumps(result["identity"]))
            identity_record["parameters"]["summary_sha256"] = digest(summary)
            identity = ArtifactIdentity(**identity_record)
            forged = {**result, "summary": summary, "status": "prepared",
                      "identity": identity.record(), "identity_sha256": identity.sha256}
            with self.assertRaises(ValueError):
                save_surface_network(forged, path)

    def test_reidentified_isolated_wet_cell_rejected(self):
        _, result = self.make_result(SurfaceNetworkBudget(4., 5000., 5000.))
        arrays = {name: value.copy() for name, value in result["arrays"].items()}
        arrays["wet_mask"][0, 0] = True
        arrays["water_surface_m"][0, 0] = arrays["final_surface_m"][0, 0] + 1
        summary = json.loads(json.dumps(result["summary"]))
        summary["inundation"]["wet_nodes"] += 1
        identity_record = json.loads(json.dumps(result["identity"]))
        identity_record["parameters"]["output_sha256"] = digest({name: array_hash(value) for name, value in arrays.items()})
        identity_record["parameters"]["summary_sha256"] = digest(summary)
        identity = ArtifactIdentity(**identity_record)
        forged = {**result, "arrays": arrays, "summary": summary,
                  "identity": identity.record(), "identity_sha256": identity.sha256}
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                save_surface_network(forged, Path(directory) / "isolated.npz")

    def test_outside_domain_cut_rejected(self):
        plan = confluence_plan()
        domain = np.ones((61, 61), bool)
        domain[20, 30] = False
        blank = np.zeros((61, 61), bool)
        legal = blank.copy(); legal[-1, 27:34] = True
        result = prepare_surface_network(plan, 0., 0., 1., 1., (61, 61), domain,
            blank, legal, np.array([5.2]), SectionRecipe(),
            StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
            InundationRecipe(max_lateral_reach_m=15.), SurfaceNetworkBudget(4., 5000., 5000.))
        self.assertTrue(result["summary"]["budget_failures"]["outside_domain_cut"])
        self.assertEqual(result["status"], "diagnostic_not_publishable")

    def test_overlapping_world_slices_share_exact_values(self):
        _, result = self.make_result(SurfaceNetworkBudget(4., 5000., 5000.))
        first = slice_surface_network(result, slice(0, 40), slice(0, 40))
        second = slice_surface_network(result, slice(20, 61), slice(20, 61))
        self.assertEqual(second["origin_x_m"], 20.)
        self.assertEqual(second["origin_z_m"], 20.)
        for name in result["arrays"]:
            np.testing.assert_array_equal(first["arrays"][name][20:40,20:40],
                                          second["arrays"][name][0:20,0:20])
            self.assertFalse(first["arrays"][name].flags.writeable)


if __name__ == "__main__":
    unittest.main()
