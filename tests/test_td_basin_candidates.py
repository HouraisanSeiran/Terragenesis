import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import storageimplicit_simulate as simulate_basin_storage
from terrain_pipeline.geology import make_material_field
from terrain_pipeline.basin_topology import generate_candidate_geometries as generate_candidate_geometries
from terrain_pipeline.basin_topology import run_candidate_coupling as run_candidate_coupling
from terrain_pipeline.basin_topology import select_candidate as select_candidate
from terrain_pipeline.basin_topology import validate_candidate_inputs as validate_candidate_inputs


class CandidateTests(unittest.TestCase):
    def inputs(self, protected=False):
        mask = np.array([[False, protected, False]])
        source = make_td_source([[3., 1., 0.]], spacing_m=1, protected_mask=mask)
        topology = build_basin_hierarchy(source)
        material = make_material_field((1, 3), spacing_m=1, origin_m_xz=(0, 0), protected_mask=mask)
        ordinary = simulate_basin_storage(topology, np.array([10., 0.]), initial_depth_m=[[0.1, 0, 0]])
        strong = simulate_basin_storage(topology, np.array([30., 0.]), initial_depth_m=[[0.1, 0, 0]])
        return source, topology, material, ordinary, strong

    def test_selection_requires_sensitivity_and_improvement(self):
        records = [{"candidate_id": "valley_incision", "gates_passed": True, "improved": True,
                    "disturbance_m3": 1., "max_abs_delta_m": .1}]
        self.assertEqual(select_candidate(records, numerical_sensitivity_passed=False), "baseline")
        self.assertEqual(select_candidate(records, numerical_sensitivity_passed=True), "valley_incision")
        records[0]["improved"] = False
        self.assertEqual(select_candidate(records, numerical_sensitivity_passed=True), "baseline")

    def test_real_geometry_rebuilt_coupled_and_atomic_fallback(self):
        inputs = self.inputs()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate"
            result = run_candidate_coupling(*inputs, output, numerical_sensitivity_passed=False)
            self.assertEqual(result["selected_candidate_id"], "baseline")
            changed = [record for record in result["candidates"] if record.get("changed_cells", 0)]
            self.assertEqual(len(changed), 2)
            for record in changed:
                self.assertNotEqual(record["source"]["expected_identity"], inputs[0]["identity_sha256"])
                self.assertNotEqual(record["hierarchy"]["expected_identity"], inputs[1]["identity_sha256"])
                self.assertIn("ordinary", record)
                self.assertIn("strong", record)
                self.assertIn("baseline_strong_transient_not_converged", record["rejection_reasons"])
            self.assertTrue((output / "records.json").exists())
            with self.assertRaises(FileExistsError):
                run_candidate_coupling(*inputs, output)

    def test_identity_mismatch_rejected_before_publication(self):
        source, topology, material, ordinary, strong = self.inputs()
        invalid = dict(ordinary, identity_sha256="0" * 64)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bad"
            with self.assertRaises(ValueError):
                run_candidate_coupling(source, topology, material, invalid, strong, output)
            self.assertFalse(output.exists())

    def test_protected_actual_flux_refuses_geometry(self):
        with self.assertRaises(ValueError):
            generate_candidate_geometries(*self.inputs(protected=True))

    def test_material_origin_mismatch(self):
        source, topology, material, ordinary, strong = self.inputs()
        material = make_material_field((1, 3), spacing_m=1, origin_m_xz=(1, 0))
        with self.assertRaises(ValueError):
            validate_candidate_inputs(source, topology, material, ordinary, strong)

    def test_baseline_local_gate_cannot_certify_candidate(self):
        inputs = self.inputs()
        with tempfile.TemporaryDirectory() as directory:
            result = run_candidate_coupling(*inputs, Path(directory) / "local", numerical_sensitivity_passed=True)
            self.assertEqual(result["selected_candidate_id"], "baseline")
            for record in result["candidates"][1:]:
                self.assertFalse(record["gates_passed"])
                self.assertFalse(record["candidate_sensitivity_verified"])
                self.assertIn("candidate_specific_transient_sensitivity_not_verified", record["rejection_reasons"])

    def test_candidate_own_full_domain_refinement_gate(self):
        inputs = self.inputs()
        with tempfile.TemporaryDirectory() as directory:
            result = run_candidate_coupling(*inputs, Path(directory) / "refined", numerical_sensitivity_passed=True,
                                           refine_candidates=True)
            for record in result["candidates"][1:]:
                for scenario in ("ordinary", "strong"):
                    self.assertIn(scenario + "_refined", record)
                    self.assertEqual(record[scenario + "_sensitivity"]["scope"], "entire candidate domain")
                self.assertEqual(record["gates_passed"], record["candidate_sensitivity_verified"])
                self.assertFalse(record["publishable"])


if __name__ == "__main__":
    unittest.main()
