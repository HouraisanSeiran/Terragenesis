import copy
import json
import tempfile
from pathlib import Path
import unittest

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity, publish_bytes
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import OverflowParameters as OverflowParameters
from terrain_pipeline.basin_storage import _topology_identity as _topology_identity
from terrain_pipeline.basin_storage import build_overflow_topology as build_overflow_topology
from terrain_pipeline.basin_topology import build_basin_reception as build_basin_reception
from terrain_pipeline.basin_topology import load_basin_reception as load_basin_reception
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from tools.export_td_stable_basin_reception import run


class ReceptionTests(unittest.TestCase):
    def setUp(self):
        self.hierarchy = build_basin_hierarchy(make_td_source(np.array([[0., 1., 0.]]), spacing_m=2.))
        self.topology = build_overflow_topology(self.hierarchy)

    def event(self, forward, reverse):
        forward = np.asarray(forward, dtype=float)[:, None]
        reverse = np.asarray(reverse, dtype=float)[:, None]
        steps = len(forward)
        config = OverflowParameters(timestep_s=300., duration_s=300. * steps)
        leaves = len(self.topology["arrays"]["leaf_ids"])
        rain = np.zeros(steps)
        supplied = np.tile(self.topology["arrays"]["leaf_area_m2"] *
                           config.baseflow_mm_per_day / 86_400_000. * 300., (steps, 1))
        water = np.zeros((steps + 1, leaves))
        water[0] = 20.
        for step in range(steps):
            water[step + 1] = water[step] + supplied[step]
            water[step + 1, 0] -= forward[step, 0] - reverse[step, 0]
            water[step + 1, 1] += forward[step, 0] - reverse[step, 0]
        net = forward - reverse
        basin_net = np.column_stack((-net[:, 0], net[:, 0]))
        basin_gross = np.repeat(forward + reverse, leaves, axis=1)
        residual = supplied + basin_net - np.diff(water, axis=0)
        arrays = {"rain_mm_h": rain, "input_volume_m3": supplied,
                           "volume_m3": water, "face_forward_m3": forward,
                           "face_reverse_m3": reverse, "face_net_m3": net,
                           "face_volume_m3": forward + reverse,
                           "stage_m": np.zeros_like(water),
                           "basin_net_internal_m3": basin_net, "basin_gross_internal_m3": basin_gross,
                           "basin_boundary_outflow_m3": np.zeros_like(supplied),
                           "basin_balance_residual_m3": residual,
                           "balance_residual_m3": residual.sum(axis=1),
                           "spill_onset_step": np.array([0], dtype=np.int64),
                           "engineering_boundary_outflow_m3": np.zeros((steps, 0))}
        metadata = {"schema": "td-original-bed-overflow-event-v2",
                             "topology_identity_sha256": self.topology["identity_sha256"],
                             "hierarchy_identity_sha256": self.hierarchy["identity_sha256"],
                             "source_identity_sha256": self.hierarchy["metadata"]["source_identity_sha256"],
                             "parameters": vars(config), "steps": steps, "timestep_s": 300.,
                             "duration_s": 300. * steps, "hydraulic_ready": False,
                             "transient_converged": False, "natural_outlet_verified": False,
                             "publishable": False}
        return {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}

    def test_true_reversal_is_accounted_but_not_stable(self):
        event = self.event([2., 2., 0., 0., 0.], [0., 0., 1., 1., 1.])
        result = build_basin_reception(self.topology, event, copy.deepcopy(event), self.hierarchy)
        face = result["faces"][0]
        self.assertEqual(face["active_interval_sign_switches"], 1)
        self.assertEqual(face["net_m3"], 1.)
        self.assertEqual(face["gross_m3"], 7.)
        self.assertEqual(face["canceled_m3"], 6.)
        self.assertFalse(face["stable_relationship"])
        self.assertIsNone(face["receiver_leaf_id"])
        self.assertEqual(face["first_active_interval"], 0)
        self.assertEqual(face["last_active_interval"], 4)
        self.assertEqual(face["late_net_m3"], -1.)
        self.assertLess(result["max_abs_inventory_residual_m3"], 1e-12)

    def test_stability_requires_interval_agreement_and_late_direction(self):
        event = self.event([1., 1., 1., 1., 1.], [0.] * 5)
        result = build_basin_reception(self.topology, event, copy.deepcopy(event), self.hierarchy)
        self.assertTrue(result["faces"][0]["stable_relationship"])
        self.assertEqual(result["faces"][0]["late_direction_consistency"], 1.)
        reference = self.event([1., 1., 1., 1.1, .9], [0.] * 5)
        result = build_basin_reception(self.topology, event, reference, self.hierarchy)
        self.assertFalse(result["faces"][0]["stable_relationship"])

    def test_rejects_inventory_and_physics_tampering(self):
        event = self.event([1., 1.], [0., 0.])
        corrupted = copy.deepcopy(event)
        corrupted["arrays"]["volume_m3"][1, 0] += .01
        corrupted["identity_sha256"] = identity(corrupted["arrays"], corrupted["metadata"])
        with self.assertRaisesRegex(ValueError, "storage closure"):
            build_basin_reception(self.topology, corrupted, event, self.hierarchy)
        corrupted = copy.deepcopy(event)
        corrupted["metadata"]["parameters"]["face_conductance_m_s"] = .9
        corrupted["identity_sha256"] = identity(corrupted["arrays"], corrupted["metadata"])
        with self.assertRaisesRegex(ValueError, "physics"):
            build_basin_reception(self.topology, event, corrupted, self.hierarchy)

    def test_d4_pairing_and_protection(self):
        event = self.event([1., 1.], [0., 0.])
        corrupted = copy.deepcopy(self.topology)
        corrupted["faces"][0]["cell_ids"] = list(reversed(corrupted["faces"][0]["cell_ids"]))
        corrupted["identity_sha256"] = _topology_identity(corrupted)
        changed = copy.deepcopy(event)
        changed["metadata"]["topology_identity_sha256"] = corrupted["identity_sha256"]
        changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
        with self.assertRaisesRegex(ValueError, "cell pairing"):
            build_basin_reception(corrupted, changed, changed, self.hierarchy)
        corrupted = copy.deepcopy(self.hierarchy)
        corrupted["arrays"]["protected_mask"] = corrupted["arrays"]["protected_mask"].copy()
        cell = self.topology["faces"][0]["cell_ids"][0]
        corrupted["arrays"]["protected_mask"].ravel()[cell] = True
        with self.assertRaisesRegex(ValueError, "identity"):
            build_basin_reception(self.topology, event, event, corrupted)

    def test_cold_read_sha_and_identity(self):
        event = self.event([1., 1.], [0., 0.])
        result = build_basin_reception(self.topology, event, event, self.hierarchy)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "reception.json"
            publish_bytes(path, json.dumps(result, sort_keys=True).encode())
            loaded = load_basin_reception(path, expected_sha256=file_sha256(path),
                                          expected_identity=result["identity_sha256"])
            self.assertEqual(loaded, result)
            with self.assertRaisesRegex(ValueError, "hash"):
                load_basin_reception(path, expected_sha256="0" * 64,
                                     expected_identity=result["identity_sha256"])

    def test_export_requires_bound_passed_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            index_path = directory / "index.json"
            audit_path = directory / "independent-audit.json"
            publish_bytes(index_path, json.dumps({"schema": "td-radau-overflow-refinement-v1",
                                                  "status": "ready_for_independent_audit"}).encode())
            publish_bytes(audit_path, json.dumps({"schema": "td-radau-overflow-independent-audit-v1",
                                                  "status": "passed", "index_sha256": "0" * 64}).encode())
            with self.assertRaisesRegex(ValueError, "audit"):
                run(directory, file_sha256(index_path), file_sha256(audit_path), directory / "new")
            self.assertFalse((directory / "new").exists())

    def test_cold_validator_rejects_rehashed_inventory_and_directional_totals(self):
        from terrain_pipeline.basin_topology import _sha as _sha
        from terrain_pipeline.basin_topology import validate_basin_reception as validate_basin_reception

        event = self.event([1., 1.], [0., 0.])
        result = build_basin_reception(self.topology, event, event, self.hierarchy)
        corrupted = copy.deepcopy(result)
        corrupted["basins"][0]["inventory_m3"][1] += .01
        corrupted.pop("identity_sha256")
        corrupted["identity_sha256"] = _sha(corrupted)
        with self.assertRaisesRegex(ValueError, "reconstructed inventory"):
            validate_basin_reception(corrupted, expected_identity=corrupted["identity_sha256"])
        corrupted = copy.deepcopy(result)
        corrupted["faces"][0]["gross_m3"] += .01
        corrupted.pop("identity_sha256")
        corrupted["identity_sha256"] = _sha(corrupted)
        with self.assertRaisesRegex(ValueError, "directional totals"):
            validate_basin_reception(corrupted, expected_identity=corrupted["identity_sha256"])


if __name__ == "__main__":
    unittest.main()
