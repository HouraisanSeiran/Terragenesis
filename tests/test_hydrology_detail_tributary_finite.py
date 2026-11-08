import copy
import unittest

import numpy as np

from terrain_pipeline.hydrology_detail import _steepest_receivers
from terrain_pipeline.hydrology_detail_tributary_finite import audit_finite_projection
from terrain_pipeline.channel_geometry import split_frozen_window_component, solved_shared_section
from tools.prepare_hydrology_domains import _artifact_identity


class FiniteTributaryAuditTests(unittest.TestCase):
    def test_harmonic_boundary_displacement_preserves_detail_and_dirichlet_data(self):
        from terrain_pipeline.hydrology_detail_tributary_finite import harmonic_boundary_target
        z, x = np.mgrid[:9, :9]
        raw = np.sin(x * 2.) + np.cos(z * 3.)
        correction = 10. + 2 * x + 3 * z
        macro = raw + correction
        pinned = np.minimum.reduce([x, z, 8-x, 8-z]) <= 1
        target = harmonic_boundary_target(raw, macro, pinned)
        np.testing.assert_array_equal(target[pinned], macro[pinned])
        np.testing.assert_allclose(target - raw, correction, atol=1e-12)
        displaced = target - raw
        laplacian = 4*displaced[1:-1,1:-1]-displaced[:-2,1:-1]-displaced[2:,1:-1]-displaced[1:-1,:-2]-displaced[1:-1,2:]
        self.assertLess(np.abs(laplacian[~pinned[1:-1,1:-1]]).max(), 1e-12)
        with self.assertRaisesRegex(ValueError, "pinned outer"):
            harmonic_boundary_target(raw, macro, np.zeros(raw.shape, bool))

    def test_channel_cold_audit_requires_regenerated_rows_and_rejects_violation(self):
        from terrain_pipeline.hydrology_detail_tributary_finite import CHANNEL_FEASIBILITY_POLICY
        result, expected, recipe, constraints = self.fixture()
        channel = {"columns": np.array([[0, 1]]), "coefficients": np.array([[1., -1.]]), "rhs": np.array([2.]), "metadata": {"algorithm": "test-necessary", "coverage": [], "unsupported_sections": 0}}
        recipe.update(channel_feasibility_policy=CHANNEL_FEASIBILITY_POLICY, frozen_channel_feasibility_constraints=channel["metadata"])
        result["metadata"].update(recipe)
        self.seal(result)
        with self.assertRaisesRegex(ValueError, "regenerated frozen rows"):
            audit_finite_projection(result, expected, recipe, constraints)
        self.assertEqual(audit_finite_projection(result, expected, recipe, constraints, channel)["status"], "cold_verified_finite_local_projection")
        channel["rhs"] = np.array([0.])
        with self.assertRaisesRegex(ValueError, "channel feasibility rejected"):
            audit_finite_projection(result, expected, recipe, constraints, channel)

    def test_query_scope_preserves_global_failure_and_rejects_used_bad_corner(self):
        from terrain_pipeline.hydrology_detail_ridge import continuous_macro_field
        rows, cols = np.indices((4, 4))
        owner = np.zeros((4, 4), dtype=np.int32)
        owner[0, 1] = 1
        receiver = np.full((4, 4), -1, dtype=np.int64)
        receiver[0, 0] = 5
        river = np.zeros((4, 4), bool)
        river[0, 0] = True
        plan = {"height_m": 100. - rows - cols, "owner_domain_id": owner,
                "receiver": receiver, "river_mask": river}
        far = np.array([[2.75]])
        with self.assertRaisesRegex(ValueError, "mixed-owner corner"):
            continuous_macro_field(plan, far, far)
        self.assertTrue(np.isfinite(continuous_macro_field(plan, far, far, validate_query_support_only=True)).all())
        near = np.array([[.25]])
        with self.assertRaisesRegex(ValueError, "mixed-owner corner"):
            continuous_macro_field(plan, near, near, validate_query_support_only=True)

    def fixture(self):
        rows, cols = np.indices((99, 99))
        height = 1000. - rows - cols
        pinned = np.minimum.reduce([rows, cols, 98 - rows, 98 - cols]) <= 1
        arrays = {"projection_height_m": height, "original_td_m": height.copy(),
                  "macro_height_m": height.copy(), "core_mask": ~pinned, "pinned_mask": pinned,
                  "owner_domain_id": np.zeros(height.shape, int), "actual_receiver": _steepest_receivers(height, 30)}
        recipe = {"algorithm": "finite-test", "world_seed": 20261020, "support_origin_xz_m": [0., 0.], "config": {"macro_max_abs_m": 512., "macro_absolute_volume_m3": 4.5e9, "max_slope_m_per_m": .75}}
        metadata = dict(recipe)
        metadata["identity"] = _artifact_identity(metadata, arrays)
        expected = {key: value.copy() for key, value in arrays.items() if key not in ("projection_height_m", "actual_receiver")}
        constraints = {"columns": np.array([[0, 1]]), "coefficients": np.array([[-1., 1.]]), "rhs": np.array([-0.001])}
        return {"metadata": metadata, "arrays": arrays}, expected, recipe, constraints

    def seal(self, result):
        result["metadata"]["identity"] = _artifact_identity(result["metadata"], result["arrays"])

    def test_saved_arrays_checked_without_solver(self):
        result, expected, recipe, constraints = self.fixture()
        audit = audit_finite_projection(result, expected, recipe, constraints)
        self.assertEqual(audit["status"], "cold_verified_finite_local_projection")
        self.assertFalse(audit["canonical_core_certified"])

    def test_registered_marine_terminal_is_excluded_without_allowing_land_owner_crossing(self):
        result, unused, recipe, constraints = self.fixture()
        arrays = result["arrays"]
        for key in ("projection_height_m", "original_td_m", "macro_height_m"):
            arrays[key] -= 1100.
        marine = np.indices((99, 99))[1] >= 50
        arrays.update(ocean_mask=marine, terminal_mask=marine, ocean_stencil_mask=marine.copy())
        arrays["owner_domain_id"][marine] = -1
        recipe["window"] = {"kind": "mouth"}
        result["metadata"].update(recipe)
        self.seal(result)
        expected = {key: value.copy() for key, value in arrays.items() if key not in ("projection_height_m", "actual_receiver")}
        self.assertEqual(audit_finite_projection(result, expected, recipe, constraints)["status"], "cold_verified_finite_local_projection")
        arrays["owner_domain_id"][:, 25:40] = 2
        expected["owner_domain_id"] = arrays["owner_domain_id"].copy()
        self.seal(result)
        with self.assertRaisesRegex(ValueError, "actual graph or owner"):
            audit_finite_projection(result, expected, recipe, constraints)

    def test_rehashed_boundary_and_sink_rejected(self):
        result, expected, recipe, constraints = self.fixture()
        changed = copy.deepcopy(result)
        changed["arrays"]["projection_height_m"][0, 0] += 1
        self.seal(changed)
        with self.assertRaisesRegex(ValueError, "world boundary"):
            audit_finite_projection(changed, expected, recipe, constraints)
        changed = copy.deepcopy(result)
        changed["arrays"]["projection_height_m"][49, 49] -= 10.
        changed["arrays"]["actual_receiver"] = _steepest_receivers(changed["arrays"]["projection_height_m"], 30)
        self.seal(changed)
        with self.assertRaisesRegex(ValueError, "actual graph"):
            audit_finite_projection(changed, expected, recipe, constraints)

    def test_rehashed_continuous_river_violation_rejected(self):
        result, expected, recipe, constraints = self.fixture()
        constraints["rhs"] = np.array([-2.])
        with self.assertRaisesRegex(ValueError, "continuous frozen river"):
            audit_finite_projection(result, expected, recipe, constraints)

    def test_joint_arm_preserves_all_subdivision_profile_knots(self):
        specification = {"points_xz_m": [[0., 0.], [5., 0.], [10., 0.]], "receiver": [1, 2, -1],
            "width_m": [8.] * 3, "bed_target_m": [3., 2., 1.], "node_source_edges": [[0, 1]] * 3,
            "node_edge_fractions": [0., .5, 1.], "fine_spacing_m": 1., "coverage": {},
            "joint_component_solve": True, "centerline_profile": {"parent_detail_identity": "parent",
            "offsets": [0, 6, 12], "t": [0., .2, .4, .6, .8, 1.] * 2,
            "source_m": [4., 3.8, 3.6, 3.4, 3.2, 3., 3., 2.8, 2.6, 2.4, 2.2, 2.],
            "bed_m": [3., 2.8, 2.6, 2.4, 2.2, 2., 2., 1.8, 1.6, 1.4, 1.2, 1.]}}
        piece = split_frozen_window_component(specification)[0]
        self.assertEqual(piece["receiver"], [1, -1])
        self.assertEqual(piece["parent_node_ids"], [0, 2])
        np.testing.assert_allclose(piece["centerline_profile"]["t"], np.linspace(0, 1, 11))
        np.testing.assert_allclose(piece["centerline_profile"]["bed_m"], np.linspace(3, 1, 11))

    def test_local_solved_section_preserves_shared_actual_center_ceiling_and_bank(self):
        rows, cols = np.indices((9, 9))
        detail = {"metadata": {"identity": "a" * 64, "origin_xz_m": [0., 0.], "spacing_m": 30.},
                  "arrays": {"derived_height_m": 101. - .001 * cols * 30.}}
        times = np.linspace(0., 1., 31)
        spec = {"points_xz_m": [[90., 120.], [120., 120.], [150., 120.]],
            "receiver": [1, 2, -1], "width_m": [8.] * 3,
            "bed_target_m": [100.41, 100.38, 100.35],
            "centerline_profile": {"offsets": [0, 31, 62], "t": list(times) * 2,
                "bed_m": np.r_[100.41-.03*times, 100.38-.03*times].tolist()}}
        section = solved_shared_section(detail, spec, 1, np.array([0., 1.]))
        self.assertAlmostEqual(np.interp(0., section["offsets_m"], section["bed_elevation_m"]), section["center_bed_m"])
        self.assertLessEqual(section["center_bed_m"], section["design_center_ceiling_m"]+1e-8)
        self.assertTrue(section["source_mesh_geometry_audit"]["accepted"])
        np.testing.assert_allclose(np.asarray(section["bed_elevation_m"])[[0, -1]],
                                   np.asarray(section["source_elevation_m"])[[0, -1]], atol=1e-8)


if __name__ == "__main__":
    unittest.main()
