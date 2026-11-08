import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.hydrology_detail_projection import (
    CORE, QUERY_SIZE, ProjectionConfig, ProjectionError, _coarse_port_progress, _coastal_suffix, _digest, _identity, _validate_port,
    crop_projection, frozen_river_derivative_constraints, load_cached_support, load_projection, project_arrays, save_projection,
)
from terrain_pipeline.td_source import source_contract


class HydrologyDetailProjectionTests(unittest.TestCase):
    def test_target_gradient_policy_preserves_feasible_relations_and_all_hard_gates(self):
        args = self.fixture()
        z, x = np.mgrid[:11, :11]
        args[1][2:-2,2:-2] += (8*np.sin(1.7*x)*np.cos(2.3*z))[2:-2,2:-2]
        old = project_arrays(*args, spacing_m=30.)
        new = project_arrays(*args, spacing_m=30., gradient_policy="target-neighbor-gradient-l1-v1")
        def gradient_defect(result):
            delta = result["arrays"]["projection_height_m"]-args[1]
            return sum(np.abs(np.diff(delta,axis=axis)).sum() for axis in (0,1))
        self.assertLess(gradient_defect(new), gradient_defect(old))
        np.testing.assert_array_equal(new["arrays"]["projection_height_m"][args[7]], args[2][args[7]])
        self.assertEqual(new["metadata"]["config"], old["metadata"]["config"])
        self.assertEqual(new["metadata"]["ledger"]["unplanned_interior_sink_count"],0)
        self.assertEqual(new["metadata"]["gradient_objective"]["relation_weight"],1.)
        feasible = self.fixture()
        preserved = project_arrays(*feasible, spacing_m=30., gradient_policy="target-neighbor-gradient-l1-v1")
        np.testing.assert_allclose(preserved["arrays"]["projection_height_m"][feasible[6]], feasible[1][feasible[6]], atol=.1)

    def test_channel_rows_change_projection_and_reject_fixed_conflict(self):
        args = self.fixture()
        columns = np.array([[60, 61, 0, 0, 0, 0, 0, 0]])
        coefficients = np.array([[1., -1., 0., 0., 0., 0., 0., 0.]])
        rows = {"columns": columns, "coefficients": coefficients, "rhs": np.array([1.]), "metadata": {"algorithm": "test-necessary"}}
        old = project_arrays(*args, spacing_m=30)
        result = project_arrays(*args, spacing_m=30, frozen_channel_constraints=rows)
        height = result["arrays"]["projection_height_m"]
        self.assertLessEqual(height.ravel()[60] - height.ravel()[61], 1. + 1e-8)
        self.assertGreater(old["arrays"]["projection_height_m"].ravel()[60] - old["arrays"]["projection_height_m"].ravel()[61], 1.)
        np.testing.assert_array_equal(height[args[7]], args[2][args[7]])
        self.assertEqual(result["metadata"]["config"], old["metadata"]["config"])
        rows["columns"] = np.array([[0, 1, 0, 0, 0, 0, 0, 0]])
        with self.assertRaisesRegex(ProjectionError, "fixed interface.*channel"):
            project_arrays(*args, spacing_m=30, frozen_channel_constraints=rows)

    def test_target_guided_witness_keeps_macro_rank_and_fixed_exits(self):
        from terrain_pipeline.hydrology_detail_projection import _witness, TARGET_WITNESS_POLICY
        z, x = np.mgrid[:9, :9]
        macro = 100. - 2*x - z
        core = np.zeros(macro.shape, bool)
        core[1:-1,1:-1] = True
        owner = np.zeros(macro.shape, int)
        water = np.zeros(macro.shape, bool)
        old = _witness(macro, owner, water, water, core, 30.)
        target = macro.copy()
        target.ravel()[old[4,4]] = target[4,4] + 3.
        new = _witness(macro, owner, water, water, core, 30., target=target, pinned=~core, policy=TARGET_WITNESS_POLICY)
        self.assertNotEqual(old[4,4], new[4,4])
        self.assertLess(target.ravel()[new[4,4]], target[4,4])
        active = np.flatnonzero(core)
        self.assertTrue(np.all(macro.ravel()[new.ravel()[active]] < macro.ravel()[active]))
        exits = core & (~core).ravel()[np.maximum(old,0)]
        np.testing.assert_array_equal(new[exits],old[exits])
        repeated = _witness(macro, owner, water, water, core, 30., target=target, pinned=~core, policy=TARGET_WITNESS_POLICY)
        np.testing.assert_array_equal(new,repeated)
        target[4,4] = -100.
        fallback = _witness(macro, owner, water, water, core, 30., target=target, pinned=~core, policy=TARGET_WITNESS_POLICY)
        self.assertEqual(fallback[4,4],old[4,4])

    def test_target_witness_has_independent_algorithm_identity(self):
        from terrain_pipeline.hydrology_detail_projection import TARGET_WITNESS_POLICY, TARGET_WITNESS_ALGORITHM, ALGORITHM
        args = self.fixture()
        old = project_arrays(*args, spacing_m=30)
        new = project_arrays(*args, spacing_m=30, witness_policy=TARGET_WITNESS_POLICY)
        self.assertEqual(old["metadata"]["algorithm"],ALGORITHM)
        self.assertNotIn("witness_policy",old["metadata"])
        self.assertEqual(new["metadata"]["algorithm"],TARGET_WITNESS_ALGORITHM)
        self.assertEqual(new["metadata"]["witness_policy"],TARGET_WITNESS_POLICY)

    def test_fixed_boundary_slope_policy_keeps_internal_to_interface_limit(self):
        z, x = np.mgrid[:5, :5]
        macro = 100. - x - z
        macro[0, 0] += 30.
        original = macro.copy()
        core = np.zeros(macro.shape, bool)
        core[1:-1, 1:-1] = True
        owner = np.zeros(macro.shape, np.int32)
        water = np.zeros(macro.shape, bool)
        args = (original, original, macro, owner, water, water, core, ~core)
        with self.assertRaises(ProjectionError):
            project_arrays(*args, spacing_m=30)
        result = project_arrays(*args, spacing_m=30, fixed_boundary_slope_policy="diagnostic_only")
        height = result["arrays"]["projection_height_m"]
        np.testing.assert_array_equal(height[~core], macro[~core])
        self.assertGreater(sum(row["fixed_pair_above_internal_limit_count"] for row in
            result["metadata"]["fixed_boundary_actual_slope_diagnostics"]), 0)
        self.assertLessEqual(abs(height[1,1]-height[0,0]) / (30*np.sqrt(2)), .75 + 1e-8)
        locked = ProjectionConfig(macro_max_abs_m=.01)
        with self.assertRaises(ProjectionError):
            project_arrays(*args, spacing_m=30, config=locked, fixed_boundary_slope_policy="diagnostic_only")

    def test_sampled_macro_valley_floor_rows_bind_center_and_both_banks(self):
        from terrain_pipeline.hydrology_detail_projection import frozen_river_valley_floor_constraints
        plan = self.river_plan(origin=(30,60),spacing=90,first=0,second=1)
        rows = frozen_river_valley_floor_constraints(plan,(7,7),(0,0),30,np.zeros((7,7),bool),source_edges=[(0,1)])
        self.assertEqual(rows["columns"].shape[1],8)
        self.assertTrue(np.allclose(np.sum(rows["coefficients"],axis=1),0))
        z,x=np.mgrid[:7,:7]
        height=10+2*np.abs(z-2)
        residual=np.sum(rows["coefficients"]*height.ravel()[rows["columns"]],axis=1)
        self.assertTrue(np.all(residual<=0))
        height=10-2*np.abs(z-2)
        residual=np.sum(rows["coefficients"]*height.ravel()[rows["columns"]],axis=1)
        self.assertTrue(np.all(residual>0))

    def river_plan(self, *, origin=(150, 30), spacing=240, first=0, second=2):
        receiver = np.full((2, 2), -1, dtype=int)
        river = np.zeros((2, 2), bool)
        receiver.ravel()[first] = second
        river.ravel()[first] = True
        return {"height_m": np.array([[100., 99.], [90., 89.]]), "receiver": receiver,
                "river_mask": river, "owner_domain_id": np.zeros((2, 2), int),
                "origin_xz_m": list(origin), "spacing_m": spacing}

    def fixture(self):
        z, x = np.mgrid[:11, :11]
        macro = 100.0 - 2 * x - z
        original = macro + 0.1 * np.sin(x) * np.sin(z)
        core = np.zeros(macro.shape, bool)
        core[1:-1, 1:-1] = True
        return original, original.copy(), macro, np.zeros(macro.shape, np.int32), np.zeros(macro.shape, bool), np.zeros(macro.shape, bool), core, ~core

    def test_preserves_full_feasible_interior_residual_and_fixed_interface(self):
        args = self.fixture()
        result = project_arrays(*args, spacing_m=30)
        height = result["arrays"]["projection_height_m"]
        np.testing.assert_allclose(height[args[6]], args[1][args[6]], atol=1e-8)
        np.testing.assert_array_equal(height[args[7]], args[2][args[7]])
        self.assertEqual(result["metadata"]["ledger"]["unplanned_interior_sink_count"], 0)
        self.assertGreater(np.std(height[2:-2, 2:-2] - args[2][2:-2, 2:-2]), 0.01)

    def test_pit_is_corrected_without_flattening_entire_target(self):
        args = self.fixture()
        args[1][5, 5] -= 20
        result = project_arrays(*args, spacing_m=30)
        height = result["arrays"]["projection_height_m"]
        self.assertGreater(height[5, 5], args[1][5, 5] + 1)
        self.assertGreater(result["metadata"]["ledger"]["target_unchanged_core_fraction"], 0.8)
        self.assertTrue(np.all(result["arrays"]["actual_receiver"][args[6]] >= 0))

    def test_continuous_frozen_river_valley_corrects_reverse_profile_without_changing_dag_or_budget(self):
        args = self.fixture()
        args[0][5, 5] += 5
        args[1][5, 5] += 5
        plan = self.river_plan()
        frozen_receiver = plan["receiver"].copy()
        constraints = frozen_river_derivative_constraints(plan, args[0].shape, [0, 0], 30, args[5])
        previous = project_arrays(*args, spacing_m=30)
        old = previous["arrays"]["projection_height_m"].ravel()
        self.assertGreater(np.max(np.sum(constraints["coefficients"] * old[constraints["columns"]], axis=1)), 0)
        result = project_arrays(*args, spacing_m=30, frozen_river_constraints=constraints)
        height = result["arrays"]["projection_height_m"]
        derivative = np.sum(constraints["coefficients"] * height.ravel()[constraints["columns"]], axis=1)
        self.assertTrue(np.all(derivative <= -0.001 + 1e-8))
        np.testing.assert_array_equal(height[args[7]], args[2][args[7]])
        np.testing.assert_array_equal(plan["receiver"], frozen_receiver)
        self.assertGreater(result["metadata"]["ledger"]["target_unchanged_core_fraction"], 0.8)
        self.assertEqual(result["metadata"]["config"], previous["metadata"]["config"])

    def test_cell_endpoint_derivatives_catch_reverse_slope_hidden_by_descending_endpoint_heights(self):
        plan = self.river_plan(origin=(0, 0), spacing=30, first=0, second=3)
        constraints = frozen_river_derivative_constraints(plan, (3, 3), [0, 0], 30, np.zeros((3, 3), bool))
        height = np.array([[100., 100., 98.], [100., 99., 97.], [98., 97., 96.]])
        self.assertGreater(height[0, 0] - height[1, 1], np.sqrt(2) * 30 * 0.001)
        derivative = np.sum(constraints["coefficients"] * height.ravel()[constraints["columns"]], axis=1)
        self.assertEqual(len(derivative), 2)
        self.assertAlmostEqual(derivative[0], 0)
        self.assertLess(derivative[1], -0.001)
        self.assertGreater(derivative[0] - constraints["rhs"][0], 0)

    def test_world_defined_frozen_river_rows_match_overlapping_support_and_exclude_registered_water(self):
        plan = self.river_plan(origin=(0, 0), spacing=150, first=0, second=3)
        first = frozen_river_derivative_constraints(plan, (5, 5), [0, 0], 30, np.zeros((5, 5), bool))
        second = frozen_river_derivative_constraints(plan, (5, 5), [30, 30], 30, np.zeros((5, 5), bool))

        def world_rows(result, origin):
            records = {}
            for indices, coefficients, point in zip(result["columns"], result["coefficients"], result["world_xz_m"]):
                z, x = np.divmod(indices, 5)
                coordinates = np.column_stack((x, z)) * 30 + origin
                records[(tuple(point), tuple(coordinates.ravel()))] = coefficients
            return records

        rows_a, rows_b = world_rows(first, [0, 0]), world_rows(second, [30, 30])
        common = rows_a.keys() & rows_b.keys()
        self.assertEqual(len(common), 6)
        for key in common:
            np.testing.assert_allclose(rows_a[key], rows_b[key], atol=0, rtol=0)
        wet = np.zeros((5, 5), bool)
        wet[2, 2] = True
        excluded = frozen_river_derivative_constraints(plan, (5, 5), [0, 0], 30, wet)
        self.assertLess(len(excluded["rhs"]), len(first["rhs"]))
        self.assertGreater(excluded["metadata"]["registered_terminal_stencil_excluded_length_m"], 0)

    def test_fixed_river_interface_incompatibility_is_rejected_without_a_waiver(self):
        args = list(self.fixture())
        args[7] = np.ones(args[0].shape, bool)
        plan = self.river_plan(origin=(30, 150), spacing=240, first=1, second=0)
        constraints = frozen_river_derivative_constraints(plan, args[0].shape, [0, 0], 30, args[5])
        with self.assertRaisesRegex(ProjectionError, "fixed interface cannot satisfy") as caught:
            project_arrays(*args, spacing_m=30, frozen_river_constraints=constraints)
        self.assertGreater(caught.exception.diagnostics["incompatible_river_rows"], 0)

    def test_explicit_subthreshold_derivative_rows_keep_frozen_receiver_unchanged(self):
        from tests.test_hydrology_detail_tributaries import fixture
        plan = fixture()
        plan["spacing_m"] = 30.
        frozen = plan["receiver"].copy()
        regular = frozen_river_derivative_constraints(plan, (5, 5), [0, 0], 30, np.zeros((5, 5), bool))
        local = frozen_river_derivative_constraints(plan, (5, 5), [0, 0], 30, np.zeros((5, 5), bool),
                                                   additional_source_edges=[[0, 5], [1, 5], [5, 6]])
        self.assertNotIn((0, 5), set(map(tuple, regular["source_edges"])))
        self.assertIn((0, 5), set(map(tuple, local["source_edges"])))
        np.testing.assert_array_equal(plan["receiver"], frozen)
        with self.assertRaisesRegex(ValueError, "receiver"):
            frozen_river_derivative_constraints(plan, (5, 5), [0, 0], 30, np.zeros((5, 5), bool),
                                               additional_source_edges=[[0, 6]])

    def test_cross_owner_competition_uses_actual_unmasked_d8(self):
        args = list(self.fixture())
        args[3][:, 6:] = 1
        args[2] = 100.0 - np.mgrid[:11, :11][0] * 2
        args[0] = args[2].copy()
        args[1] = args[2].copy()
        args[1][:, 6:] -= 4
        result = project_arrays(*args, spacing_m=30)
        receiver = result["arrays"]["actual_receiver"].ravel()
        active = args[6].ravel()
        owners = args[3].ravel()
        np.testing.assert_array_equal(owners[active], owners[receiver[active]])
        self.assertGreater(result["metadata"]["ledger"]["target_l1_change_m"], 0)

    def test_impossible_pins_and_full_support_volume_are_refused(self):
        args = list(self.fixture())
        args[0][0, 0] += 600
        with self.assertRaisesRegex(ProjectionError, "interface"):
            project_arrays(*args, spacing_m=30)
        args = self.fixture()
        with self.assertRaisesRegex(ProjectionError, "not solved"):
            project_arrays(*args, spacing_m=30, config=ProjectionConfig(macro_absolute_volume_m3=0.001))

    def test_roundtrip_and_owned_crop_refuse_tampering_or_other_core(self):
        result = project_arrays(*self.fixture(), spacing_m=30)
        result["arrays"]["frozen_river_derivative_rhs"] = np.array([-0.001])
        result["metadata"].update(native_origin_xz=[-2, -2], core_native_origin_xz=[0, 0], spacing_m=30)
        result["metadata"]["identity"] = _identity(result["metadata"], result["arrays"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "projection.npz"
            save_projection(result, path)
            cold = load_projection(path)
            np.testing.assert_array_equal(cold["arrays"]["projection_height_m"], result["arrays"]["projection_height_m"])
            crop = crop_projection(cold, [0, 0], [3, 3])
            self.assertNotIn("frozen_river_derivative_rhs", crop["arrays"])
            np.testing.assert_array_equal(crop["arrays"]["projection_height_m"], result["arrays"]["projection_height_m"][2:5, 2:5])
            with self.assertRaisesRegex(ValueError, "owned core"):
                crop_projection(cold, [-1, 0], [3, 3])
            cold["arrays"]["projection_height_m"][0, 0] += 1
            with self.assertRaisesRegex(ValueError, "identity"):
                save_projection(cold, Path(directory) / "tampered.npz")

    def test_missing_source_lists_nine_tiles_without_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            contract = source_contract("test")
            meta = dict(canonical_source_contract=contract, identity=_digest(contract), seed="3", canonical_cache_root=directory, artifact_kind="terrain_diffusion_output")
            with self.assertRaises(ProjectionError) as caught:
                load_cached_support(meta, tile_x=0, tile_z=0)
            self.assertEqual(caught.exception.diagnostics["status"], "source_unprepared")
            self.assertEqual(len(caught.exception.diagnostics["missing_tiles"]), 9)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cache_assembly_never_uses_discarded_257th_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            base = {"model": "synthetic-fixture"}
            identity = _digest(base)
            contract = source_contract(identity)
            meta = dict(canonical_source_contract=contract, identity=_digest(contract), seed="3", canonical_cache_root=directory, artifact_kind="terrain_diffusion_output")
            root = Path(directory) / meta["identity"] / "3"
            root.mkdir(parents=True)
            for tz in range(-1, 2):
                for tx in range(-1, 2):
                    z, x = np.mgrid[:QUERY_SIZE, :QUERY_SIZE]
                    elevation = (tx * CORE + x) + 10000.0 * (tz * CORE + z)
                    elevation[-1, :] = elevation[:, -1] = -999999999.0
                    generated = dict(base, identity=identity, seed="3", native_origin=[tx * CORE, tz * CORE], shape=[QUERY_SIZE, QUERY_SIZE], native_resolution_m=30.0, artifact_kind="terrain_diffusion_output")
                    path = root / f"tile-x{tx}-z{tz}.npz"
                    np.savez_compressed(path, elevation_m=elevation, climate=np.zeros((5, QUERY_SIZE, QUERY_SIZE)), metadata_json=np.array(json.dumps(generated)))
                    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest(), encoding="ascii")
            height, provenance = load_cached_support(meta, tile_x=0, tile_z=0)
            z, x = np.mgrid[-2:258, -2:258]
            np.testing.assert_array_equal(height, x + 10000.0 * z)
            self.assertEqual(len(provenance["tile_assembly"]), 9)
            self.assertFalse(provenance["td_inference_run"])

    def test_port_accepts_other_downstream_branch_with_same_terminal(self):
        receiver = np.array([1, 3, 3, -1])
        terminals = np.array([3, 3, 3, 3])
        ranks = np.array([2, 1, 1, 0])
        progress = _coarse_port_progress(receiver, terminals, ranks, 0, 2)
        self.assertEqual(progress["coarse_progress"], "same_terminal_lower_rank")
        self.assertEqual(progress["coarse_rank_drop"], 1)
        self.assertEqual(progress["halo_coarse_receiver"], 3)
        self.assertEqual(_coarse_port_progress(receiver, terminals, ranks, 0, 0)["coarse_progress"], "within_same_coarse_cell")
        with self.assertRaisesRegex(ProjectionError, "rank"):
            _coarse_port_progress(receiver, terminals, ranks, 1, 2)
        with self.assertRaisesRegex(ProjectionError, "terminal"):
            _coarse_port_progress(receiver, np.array([3, 3, 2, 3]), ranks, 0, 2)

    def test_port_refuses_unpinned_and_non_downhill_interfaces(self):
        plan = {"receiver": np.array([[1, -1]]), "ocean_mask": np.array([[False, False]]), "domains": []}
        arrays = {"projection_height_m": np.array([[10., 9.]]), "macro_height_m": np.array([[10., 9.]]),
                  "pinned_mask": np.array([[True, True]]), "owner_domain_id": np.array([[0, 0]]), "ocean_mask": np.array([[False, False]])}
        result = {"arrays": arrays}
        coarse_ids = np.array([[0, 1]])
        terminals, ranks = np.array([1, 1]), np.array([1, 0])
        certificate = _validate_port(plan, result, coarse_ids, terminals, ranks, 0, 1)
        self.assertEqual(certificate["coarse_progress"], "same_terminal_lower_rank")
        self.assertEqual(certificate["coarse_rank_drop"], 1)
        arrays["pinned_mask"][0, 0] = False
        with self.assertRaisesRegex(ProjectionError, "fixed downhill"):
            _validate_port(plan, result, coarse_ids, terminals, ranks, 0, 1)
        arrays["pinned_mask"][0, 0] = True
        arrays["macro_height_m"][0, 1] = arrays["projection_height_m"][0, 1] = 11
        with self.assertRaisesRegex(ProjectionError, "fixed downhill"):
            _validate_port(plan, result, coarse_ids, terminals, ranks, 0, 1)

    def test_marine_port_requires_registered_coastal_domain(self):
        plan = {"receiver": np.array([[1, -1]]), "ocean_mask": np.array([[False, True]]),
                "domains": [{"domain_id": 0, "kind": "coastal", "terminal_indices": [1]}]}
        arrays = {"projection_height_m": np.array([[1., -1.]]), "macro_height_m": np.array([[1., -1.]]),
                  "pinned_mask": np.array([[True, True]]), "owner_domain_id": np.array([[0, -1]]), "ocean_mask": np.array([[False, True]])}
        args = (plan, {"arrays": arrays}, np.array([[0, 1]]), np.array([1, 1]), np.array([1, 0]), 0, 1)
        certificate = _validate_port(*args)
        self.assertEqual(certificate["kind"], "registered_marine_entry")
        plan["domains"][0]["kind"] = "inland"
        with self.assertRaisesRegex(ProjectionError, "coastal terminal"):
            _validate_port(*args)

    def test_solver_scheduling_stays_outside_scientific_configuration(self):
        from terrain_pipeline import hydrology_detail_projection as module
        with patch.object(module, "linprog", wraps=module.linprog) as solver:
            result = project_arrays(*self.fixture(), spacing_m=30)
        self.assertEqual(solver.call_args.kwargs["options"]["threads"], 1)
        self.assertIs(solver.call_args.kwargs["options"]["parallel"], False)
        self.assertNotIn("threads", result["metadata"]["config"])
        self.assertNotIn("parallel", result["metadata"]["config"])

    def test_real_pinned_ridge_tie_does_not_require_impossible_margin(self):
        from terrain_pipeline.drainage import grid_mesh as grid_mesh
        mesh = grid_mesh((11, 11), dx_m=30)
        source = 5 * 11 + 5
        edges = np.arange(mesh.indptr[source], mesh.indptr[source + 1])
        same, competitor = mesh.indices[edges[:2]]
        own_length, competing_length = mesh.edge_length_m[edges[:2]]
        macro = np.full((11, 11), 100.)
        macro.ravel()[same] -= own_length * .01
        macro.ravel()[competitor] -= competing_length * (.01 - 1e-10)
        owners = np.ones(macro.shape, int)
        owners.ravel()[competitor] = 0
        core = np.zeros(macro.shape, bool)
        core[5, 5] = True
        zero = np.zeros(macro.shape, bool)
        result = project_arrays(macro, macro, macro, owners, zero, zero, core, np.ones(macro.shape, bool), spacing_m=30)
        self.assertEqual(int(result["arrays"]["actual_receiver"][5, 5]), same)
        self.assertEqual(len(result["metadata"]["fixed_competition_waivers"]), 1)
        np.testing.assert_array_equal(result["arrays"]["projection_height_m"], macro)
        # The same fixed terrain becomes impossible when the foreign slope wins.
        macro.ravel()[competitor] -= competing_length * 2e-10
        with self.assertRaisesRegex(ProjectionError, "not solved"):
            project_arrays(macro, macro, macro, owners, zero, zero, core, np.ones(macro.shape, bool), spacing_m=30)

    def coastal_suffix_fixture(self):
        owner = np.full((3, 3), -1, np.int32)
        owner[1, 0] = 0
        ocean = owner == -1
        plan = {"height_m": np.zeros((3, 3)), "owner_domain_id": owner, "ocean_mask": ocean,
                "origin_xz_m": [0, 0], "spacing_m": 7680}
        nearest = np.empty((2, 3, 3), int)
        nearest[0] = 1
        nearest[1] = 0
        return plan, nearest

    def test_coastal_suffix_reaches_selected_real_marine_support_with_fixed_world_values(self):
        plan, nearest = self.coastal_suffix_fixture()
        from terrain_pipeline import hydrology_detail_projection as module
        with patch.object(module, "continuous_macro_field", side_effect=lambda plan, x, z: 2 - 1.5 * (x * 256 - 256)):
            certificate = _coastal_suffix(plan, [256, 256], 4, 0, spacing_m=30, lake_level_m=526,
                                          nearest_coastal_indices=nearest)
        self.assertEqual(certificate["registered_marine_terminal"], 4)
        self.assertEqual(certificate["macro_suffix_steps"], 2)
        self.assertEqual(certificate["macro_suffix"][-1]["native_xz"], [258, 256])
        self.assertLess(certificate["macro_suffix"][-1]["height_m"], 0)

    def test_coastal_suffix_refuses_unpinned_support_and_fixed_work_budget(self):
        plan, nearest = self.coastal_suffix_fixture()
        from terrain_pipeline import hydrology_detail_projection as module
        with patch.object(module, "continuous_macro_field", side_effect=lambda plan, x, z: 100 - 0.01 * x):
            with self.assertRaisesRegex(ProjectionError, "unpinned"):
                _coastal_suffix(plan, [260, 260], 4, 0, spacing_m=30, lake_level_m=526, nearest_coastal_indices=nearest)
            with self.assertRaisesRegex(ProjectionError, "finite step budget"):
                _coastal_suffix(plan, [256, 256], 4, 0, spacing_m=30, lake_level_m=526, nearest_coastal_indices=nearest)

    def test_same_coastal_cell_and_reference_continue_without_immediate_marine_suffix(self):
        plan = {"height_m": np.array([[10., -1.]]), "owner_domain_id": np.array([[0, -1]]),
                "receiver": np.array([[1, -1]]), "ocean_mask": np.array([[False, True]]),
                "domains": [{"domain_id": 0, "kind": "coastal", "terminal_indices": [1]}]}
        arrays = {"projection_height_m": np.array([[10., 9.]]), "macro_height_m": np.array([[10., 9.]]),
                  "pinned_mask": np.array([[True, True]]), "owner_domain_id": np.array([[0, 0]]), "ocean_mask": np.array([[False, False]])}
        context = {"extension_mask": np.array([[True, True]]), "nearest_coastal_cell": np.array([[0, 0]]),
                   "native_origin_xz": [256, 0], "spacing_m": 30, "lake_level_m": 526,
                   "nearest_coastal_indices": np.zeros((2, 1, 2), int)}
        coarse_ids = np.array([[1, 1]])
        args = (plan, {"arrays": arrays}, coarse_ids, np.array([1, 1]), np.array([1, 0]), 0, 1)
        from terrain_pipeline import hydrology_detail_projection as module
        with patch.object(module, "_coastal_suffix", side_effect=ProjectionError("unpinned suffix")) as suffix:
            certificate = _validate_port(*args, coastal_context=context)
            self.assertEqual(certificate["registered_marine_terminal"], 1)
            self.assertEqual(certificate["coastal_reference_ranks"], [1, 1])
            self.assertEqual(certificate["coarse_progress"], "within_same_actual_coarse_cell_and_registered_coastal_reference")
            suffix.assert_not_called()
            # Crossing an actual coarse cell still requires the fixed suffix proof.
            coarse_ids[0, 1] = 0
            with self.assertRaisesRegex(ProjectionError, "unpinned suffix"):
                _validate_port(*args, coastal_context=context)
            suffix.assert_called_once()


if __name__ == "__main__":
    unittest.main()
