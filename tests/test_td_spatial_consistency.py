"""Spatial verification contracts, including refusal of fabricated late states."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from tools.verify_td_spatial_consistency import (
    equilibrium_volume,
    inlet_case,
    native_network,
    POLICY,
    observe,
)
from tools.verify_td_active_spatial import cold, source, POLICY as ACTIVE_POLICY


class SpatialConsistencyTest(unittest.TestCase):
    def test_real_td_equilibrium_and_initial_restriction(self):
        network, _ = native_network()
        initial = equilibrium_volume(network, 0.01)
        for level in (1, 8, 16):
            case = inlet_case(network, level, "drain", POLICY)
            children = equilibrium_volume(case.network, 0.01)
            np.testing.assert_allclose(
                children, initial[case.parent_index] * case.fraction, rtol=0, atol=1e-12
            )
            np.testing.assert_allclose(
                case.forcing.local_q_m3_s.sum(axis=1), [0.01, 0.0], rtol=0, atol=0
            )
            self.assertEqual(np.count_nonzero(case.forcing.local_q_m3_s), 1)

    def test_original_active_source_and_material_unchanged(self):
        network, forcing, old, _ = source()
        self.assertEqual(len(network.receiver), 4)
        self.assertEqual(forcing.time_seconds[-1], 900.0)
        self.assertEqual(old["material"]["sediment_erodibility_m_s_pa"], 1e-6)
        self.assertEqual(old["material"]["settling_velocity_m_s"], 1e-6)

    def test_changed_policy_and_material_refused_before_replay(self):
        _, _, old, pin = source()
        base = dict(
            policy=ACTIVE_POLICY,
            source=pin,
            material=old["material"],
            material_inputs=old["material_inputs"],
        )
        for field in ("policy", "material", "material_inputs"):
            report = json.loads(json.dumps(base))
            report[field] = {}
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "report.json"
                path.write_text(json.dumps(report), encoding="utf-8")
                with self.assertRaisesRegex(
                    AssertionError, "frozen source/material/policy"
                ):
                    cold(path)

    def test_no_inventory_extrapolation_after_failure(self):
        water = dict(
            arrays=dict(
                trace_time_seconds=np.array([0.0, 10.0]),
                trace_boundary_outflow_volume_m3=np.array([[1.0]]),
            )
        )
        solid = dict(
            arrays=dict(
                trace_time_seconds=np.array([0.0, 10.0]),
                step_exported_solid_m3=np.array([[0.1]]),
            )
        )
        with self.assertRaisesRegex(AssertionError, "horizon exceeds"):
            observe(water, solid, np.array([0]), 1, (300.0,), end_time=300.0)


if __name__ == "__main__":
    unittest.main()
