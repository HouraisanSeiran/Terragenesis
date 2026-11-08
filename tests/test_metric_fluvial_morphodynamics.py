from dataclasses import replace
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import FluvialDeltaBoundary
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import (
    MorphodynamicsConfig, NATIVE_EXCHANGE_VERSION, SOURCE_LIMITED_VERSION, GRAVITY_VERSION,
    DRY_DEPTH_VERSION, QUANTIZED_EXCHANGE_VERSION, GRAVITY_PARAMETERS, mechanism_identity_for, _mapped_input,
    conservative_diffusion_step, phase_record, simulate_fluvial_morphodynamics,
)


class MorphodynamicsTests(unittest.TestCase):
    def test_sediment_budget_diagnostic_rejects_implicit_or_nonterminal_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            for cap in (True, 569, 571, 2280):
                with self.subTest(cap=cap), self.assertRaisesRegex(ValueError, "routing-budget diagnostic"):
                    simulate_fluvial_morphodynamics(output_dir=directory, diagnostic_sediment_stepmax=cap)
            with self.assertRaisesRegex(ValueError, "routing-budget diagnostic"):
                simulate_fluvial_morphodynamics(output_dir=directory,
                    diagnostic_sediment_stepmax=1140, config=MorphodynamicsConfig(steps=2))
            parent = Path(directory) / "terminal-parent"
            parent.mkdir()
            (parent / "adapter-continuation.json").write_text(
                json.dumps({"diagnostic_only": True}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "terminal and cannot continue"):
                simulate_fluvial_morphodynamics(output_dir=Path(directory) / "forbidden-continuation",
                    config=MorphodynamicsConfig(steps=1), resume_checkpoint=parent,
                    gravity_stability=True, routing_dry_depth_m=.01, quantized_native_exchange=True)

    def test_quantized_exchange_requires_explicit_inherited_thin_layer_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            for kwargs in ({}, {"gravity_stability": True}, {"routing_dry_depth_m": .01}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    simulate_fluvial_morphodynamics(output_dir=directory,
                        quantized_native_exchange=True, **kwargs)
            with self.assertRaisesRegex(ValueError, "inherited"):
                simulate_fluvial_morphodynamics(output_dir=directory,
                    gravity_stability=True, routing_dry_depth_m=.01, quantized_native_exchange=True)
        self.assertNotEqual(mechanism_identity_for(QUANTIZED_EXCHANGE_VERSION),
                            mechanism_identity_for(DRY_DEPTH_VERSION))

    def test_phase_ledger_preserves_native_imbalance_and_bc_sign(self):
        before = np.zeros((2, 3))
        after = before.copy()
        after[0, 0] = 1.
        phase = phase_record(before, after, phase="sand", step_index=0, dx_m=5.,
                             injected_bulk_m3=30., exported_bulk_m3=2., lost_bulk_m3=1.,
                             inlet_correction_bulk_m3=-1.)
        self.assertEqual(phase["delta_bulk_m3"].sum(), 25.)
        self.assertEqual(phase["raw_residual_bulk_m3"], -1.)
        self.assertEqual(phase["exported_bulk_m3"], 2.)
        self.assertFalse(phase["start_bed_m"].flags.writeable)

    def test_zero_water_or_sediment_and_unresolved_inlet_reject(self):
        for kwargs in ({"inlet_velocity_m_s": 0.}, {"sediment_concentration_percent": 0.},
                       {"inlet_width_m": 5.}, {"maximum_original_source_cut_m": 4.1},
                       {"porosity": 1.}, {"steps": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                MorphodynamicsConfig(**kwargs)

    def test_source_mapping_preserves_original_and_prepared_support(self):
        bed = np.arange(30 * 40, dtype=np.float64).reshape(30, 40) * -.001
        terrain = TerrainGrid(bed, np.ones(bed.shape, bool), 100., 200., 5., 5.,
                              "diagnostic_dem_proxy", "mapped-source", "a" * 64)
        export = np.zeros(bed.shape, bool)
        export[:, -1] = True
        boundary = FluvialDeltaBoundary(bed <= 0., export, 0., 2., "east-ocean")
        config = MorphodynamicsConfig()
        cover = np.full(bed.shape, .65 * 25.)
        arrays, mapping, center = _mapped_input(terrain, boundary, (15, 8), cover, config)
        self.assertEqual(center, 15)
        self.assertEqual(mapping["source_rows_columns"], [0, 30, 8, 40])
        self.assertTrue(mapping["transpose"])
        np.testing.assert_array_equal(arrays["backend_source_bed_m"], bed[:, 8:].T)
        np.testing.assert_allclose(arrays["backend_prepared_bed_m"], bed[:, 8:].T + 1.)
        np.testing.assert_array_equal(terrain.elevation_m, bed)
        bad_exports = export.copy()
        bad_exports[0, 20] = True
        with self.assertRaises(ValueError):
            _mapped_input(terrain, replace(boundary, ocean_export_mask=bad_exports), (15, 8), cover, config)

    def test_actual_pinned_control_phase_ledger_and_reproducibility(self):
        config = MorphodynamicsConfig(steps=2, official_shape=(40, 40), inlet_length_m=15.,
                                      water_parcels=100, sediment_parcels=100, water_iterations=1,
                                      diffusion_enabled=False)
        with tempfile.TemporaryDirectory() as directory:
            first = simulate_fluvial_morphodynamics(config=config, output_dir=directory + "/first")
            second = simulate_fluvial_morphodynamics(config=config, output_dir=directory + "/second")
            native = simulate_fluvial_morphodynamics(config=config, output_dir=directory + "/native", source_limited_erosion=False)
        self.assertEqual(first["metadata"]["backend_version"], "2.3.0")
        np.testing.assert_array_equal(first["beds_m"], second["beds_m"])
        np.testing.assert_array_equal(first["qx_m2_s"], second["qx_m2_s"])
        for field in ("beds_m", "depths_m", "stages_m", "qx_m2_s", "qz_m2_s"):
            np.testing.assert_array_equal(first[field], native[field])
        self.assertTrue(all(phase.get("source_floor_limited_exchange_count", 0) == 0 for phase in first["phases"]))
        self.assertGreater(first["bulk_ledger"]["bed_change_bulk_m3"], 0.)
        self.assertEqual(len(first["phases"]), 8)
        for index, phase in enumerate(first["phases"]):
            if index:
                np.testing.assert_array_equal(first["phases"][index - 1]["end_bed_m"], phase["start_bed_m"])
            if phase["phase"] == "diffusion":
                self.assertEqual(phase["delta_bulk_m3"].sum(), 0.)
            else:
                self.assertLess(abs(phase["raw_residual_bulk_m3"]),
                                .01 + 1e-5 * (phase["injected_bulk_m3"] + phase["exported_bulk_m3"]
                                              + phase["lost_bulk_m3"] + abs(phase["inlet_correction_bulk_m3"])))
        ledger = first["bulk_ledger"]
        expected = (ledger["injected_bulk_m3"] - ledger["exported_bulk_m3"] - ledger["lost_bulk_m3"]
                    + ledger["inlet_correction_bulk_m3"] + ledger["raw_residual_bulk_m3"])
        self.assertAlmostEqual(ledger["bed_change_bulk_m3"], expected)
        self.assertAlmostEqual(first["solid_ledger"]["bed_change_solid_m3"],
                               .65 * ledger["bed_change_bulk_m3"])

    def test_pair_diffusion_is_conservative_and_preserves_wall_and_floor(self):
        bed = np.zeros((9, 9))
        bed[4, 4] = 3.
        floor = bed - .05
        cell_type = np.zeros(bed.shape, np.int64)
        cell_type[:, 0] = -2
        bed[4, 0] = 10.
        floor[:, 0] = bed[:, 0]
        result = conservative_diffusion_step(bed, np.ones(bed.shape), cell_type, floor, 10., 5.)
        self.assertAlmostEqual(float(result.sum()), float(bed.sum()))
        self.assertTrue(np.all(result >= floor))
        np.testing.assert_array_equal(result[0], bed[0])
        np.testing.assert_array_equal(result[:, 0], bed[:, 0])

    def test_native_checkpoint_matches_continuous_fields_and_phases_exactly(self):
        config = MorphodynamicsConfig(steps=4, official_shape=(40, 40), inlet_length_m=15.,
                                      water_parcels=100, sediment_parcels=100, water_iterations=1)
        archive_root = os.environ.get("MORPHODYNAMICS_TEST_ARCHIVE_ROOT")
        directory_context = tempfile.TemporaryDirectory() if archive_root is None else nullcontext(str(Path(archive_root).resolve()))
        with directory_context as directory:
            continuous = simulate_fluvial_morphodynamics(config=config, output_dir=directory + "/continuous")
            first = simulate_fluvial_morphodynamics(config=replace(config, steps=2), output_dir=directory + "/first")
            second = simulate_fluvial_morphodynamics(config=replace(config, steps=2), output_dir=directory + "/second",
                                                     resume_checkpoint=directory + "/first/backend")
            simulate_fluvial_morphodynamics(config=replace(config, steps=2), output_dir=directory + "/native-first",
                                            source_limited_erosion=False)
            with self.assertRaisesRegex(ValueError, "mechanism change"):
                simulate_fluvial_morphodynamics(config=replace(config, steps=2), output_dir=directory + "/unannounced",
                                                resume_checkpoint=directory + "/native-first/backend")
            mixed = simulate_fluvial_morphodynamics(config=replace(config, steps=2), output_dir=directory + "/mixed",
                resume_checkpoint=directory + "/native-first/backend", mechanism_transition={"after_step": 2,
                    "from_algorithm_version": NATIVE_EXCHANGE_VERSION, "to_algorithm_version": SOURCE_LIMITED_VERSION,
                    "reason": "short control of explicit checkpoint mechanism handoff"})
            with self.assertRaisesRegex(ValueError, "identity"):
                simulate_fluvial_morphodynamics(config=replace(config, steps=2, inlet_velocity_m_s=1.1),
                                                output_dir=directory + "/mismatch",
                                                resume_checkpoint=directory + "/first/backend")
            if archive_root is not None:
                from tools.verify_fluvial_morphodynamics import archive_result
                batches = []
                for name, result in (("first", first), ("second", second)):
                    artifact = Path(directory) / name / "detail.npz"
                    archive_result(artifact, result)
                    batches.append({"path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()})
                (Path(directory) / "chain.json").write_text(json.dumps({"schema": "saved-pydeltarcm-chain-v1", "batches": batches}, indent=2), encoding="utf-8")
        for field in ("times_s", "beds_m", "depths_m", "stages_m", "qx_m2_s", "qz_m2_s"):
            np.testing.assert_array_equal(np.concatenate((first[field], second[field][1:])), continuous[field])
            np.testing.assert_array_equal(mixed[field], second[field])
        for expected, actual in zip(continuous["phases"], first["phases"] + second["phases"]):
            self.assertEqual(expected.keys(), actual.keys())
            for key in expected:
                np.testing.assert_array_equal(actual[key], expected[key])
        self.assertEqual(second["metadata"]["native_start_step_index"], 2)
        self.assertEqual(second["metadata"]["native_end_step_index"], 4)
        self.assertEqual(first["metadata"]["checkpoint_end_sha256"], second["metadata"]["checkpoint_start_sha256"])
        self.assertEqual(first["metadata"]["continuation_identity"], continuous["metadata"]["continuation_identity"])
        self.assertEqual(first["ledger"]["declared_boundary_input_bulk_m3"], second["ledger"]["declared_boundary_input_bulk_m3"])
        np.testing.assert_array_equal(first["backend_initialization_delta_m"], second["backend_initialization_delta_m"])

    def test_sand_and_mud_exchange_cap_preserves_parcel_bed_volume(self):
        from terrain_pipeline.surface_rivers.metric_fluvial_native_routers import initialize_source_limited_routers
        vector = np.zeros(9, np.float32)
        steps = np.zeros(9, np.int64)
        model = SimpleNamespace(_dt=1., _dx=5., Vp_sed=1., u_max=20., U_dep_mud=.1,
            U_ero_mud=.2, U_ero_sand=.2, ivec_flat=vector, jvec_flat=vector,
            iwalk_flat=steps, jwalk_flat=steps, distances_flat=np.ones(9, np.float32),
            dry_depth=.1, _lambda=.1, _beta=3., stepmax=30, force_deposit=False,
            theta_mud=1., theta_sand=1., mod_erosion=np.ones((3, 3), np.float32),
            qs0=.1, _u0=1., _f_bedload=.5)
        initialize_source_limited_routers(model, np.full((3, 3), -4.))
        for router in (model._sr, model._mr):
            for field in ("eta", "depth", "stage", "uw", "ux", "uy", "qw", "qx", "qy", "qs",
                          "Vp_dep_sand", "Vp_dep_mud", "mod_stable_weight"):
                setattr(router, field, np.zeros((3, 3), np.float32))
            router.pad_depth = np.zeros((5, 5), np.float32)
            router.eta[:] = -3.99
            router.depth[:] = 3.99
            router.uw[:] = 10.
            router.qw[:] = 39.9
            router.qx[:] = 39.9
            router.mod_stable_weight[:] = 1.
            router.Vp_res = 1.
            before_bed, before_parcel = float(router.eta[1, 1]), float(router.Vp_res)
            router._deposit_or_erode(1, 1)
            self.assertGreater(router.source_floor_limited_bulk_m3, 0.)
            self.assertEqual(router.source_floor_limited_exchange_count, 1)
            self.assertGreaterEqual(float(router.eta[1, 1]), -4. - 2e-6)
            self.assertAlmostEqual((float(router.eta[1, 1]) - before_bed) * 25.
                                   + float(router.Vp_res) - before_parcel, 0., places=5)
            at_floor = float(router.eta[1, 1]), float(router.Vp_res)
            router.uw[:] = 10.
            router._deposit_or_erode(1, 1)
            self.assertEqual((float(router.eta[1, 1]), float(router.Vp_res)), at_floor)

    def test_gravity_checkpoint_preserves_mobile_base_fields_and_actual_phase_evidence(self):
        config = MorphodynamicsConfig(steps=4, official_shape=(40, 40), inlet_length_m=15.,
                                      water_parcels=100, sediment_parcels=100, water_iterations=1)
        archive_root = os.environ.get("MORPHODYNAMICS_GRAVITY_TEST_ARCHIVE_ROOT")
        directory_context = tempfile.TemporaryDirectory() if archive_root is None else nullcontext(str(Path(archive_root).resolve()))
        with directory_context as directory:
            continuous = simulate_fluvial_morphodynamics(config=config, output_dir=directory + "/continuous",
                                                         gravity_stability=True)
            first = simulate_fluvial_morphodynamics(config=replace(config, steps=2),
                output_dir=directory + "/first", gravity_stability=True)
            second = simulate_fluvial_morphodynamics(config=replace(config, steps=2),
                output_dir=directory + "/second", gravity_stability=True, resume_checkpoint=directory + "/first/backend")
            native = simulate_fluvial_morphodynamics(config=replace(config, steps=2), output_dir=directory + "/v2")
            with self.assertRaisesRegex(ValueError, "mechanism change"):
                simulate_fluvial_morphodynamics(config=replace(config, steps=1), output_dir=directory + "/unannounced-v3",
                    gravity_stability=True, resume_checkpoint=directory + "/v2/backend")
            switched = simulate_fluvial_morphodynamics(config=replace(config, steps=1), output_dir=directory + "/switched-v3",
                gravity_stability=True, resume_checkpoint=directory + "/v2/backend", mechanism_transition={
                    "after_step": 2, "from_algorithm_version": SOURCE_LIMITED_VERSION,
                    "to_algorithm_version": GRAVITY_VERSION, "reason": "explicit short gravity mechanism handoff"})
            np.testing.assert_array_equal(switched["initial_mobile_base_m"],
                                          np.minimum(native["backend_source_bed_m"], native["final_bed_m"]))
            material_path = Path(directory) / "first/backend/adapter-material-state.npz"
            with np.load(material_path, allow_pickle=False) as archive:
                np.testing.assert_array_equal(archive["mobile_base_m"], first["final_mobile_base_m"])
            if archive_root is not None:
                from tools.verify_fluvial_morphodynamics import archive_result
                batches = []
                for name, result in (("first", first), ("second", second)):
                    artifact = Path(directory) / name / "detail.npz"
                    archive_result(artifact, result)
                    batches.append({"path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()})
                (Path(directory) / "chain.json").write_text(json.dumps({"schema": "saved-pydeltarcm-chain-v1", "batches": batches}, indent=2), encoding="utf-8")
            # Keep archived native/material checkpoints immutable for cold audit.
            original_material_bytes = material_path.read_bytes()
            material_path.write_bytes(material_path.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "mobile material bytes"):
                simulate_fluvial_morphodynamics(config=replace(config, steps=1), output_dir=directory + "/tampered",
                    gravity_stability=True, resume_checkpoint=directory + "/first/backend")
            material_path.write_bytes(original_material_bytes)
        self.assertEqual(len(continuous["phases"]), 20)
        for field in ("times_s", "beds_m", "depths_m", "stages_m", "qx_m2_s", "qz_m2_s",
                      "ux_m_s", "uz_m_s", "speed_m_s"):
            np.testing.assert_array_equal(np.concatenate((first[field], second[field][1:])), continuous[field])
        np.testing.assert_array_equal(first["final_mobile_base_m"], second["initial_mobile_base_m"])
        np.testing.assert_array_equal(second["final_mobile_base_m"], continuous["final_mobile_base_m"])
        self.assertEqual(first["metadata"]["material_state_end_sha256"], second["metadata"]["material_state_start_sha256"])
        self.assertEqual(first["metadata"]["mechanism_identity"], second["metadata"]["mechanism_identity"])
        for expected, actual in zip(continuous["phases"], first["phases"] + second["phases"]):
            self.assertEqual(expected.keys(), actual.keys())
            for key in expected:
                if key == "gravity_ledger":
                    self.assertEqual(expected[key], actual[key])
                else:
                    np.testing.assert_array_equal(expected[key], actual[key])
        base = continuous["initial_mobile_base_m"].copy()
        for phase in continuous["phases"]:
            if phase["phase"] != "gravity":
                base = np.minimum(base, phase["end_bed_m"])
                continue
            before = (phase["start_bed_m"] - base) * config.dx_m ** 2
            after = (phase["end_bed_m"] - base) * config.dx_m ** 2
            sand_residual = np.sum(after * phase["end_sand_fraction"] - before * phase["start_sand_fraction"])
            self.assertEqual(float(sand_residual), phase["gravity_ledger"]["actual_raw_residual_sand_bulk_m3"])
        np.testing.assert_array_equal(base, continuous["final_mobile_base_m"])

    def test_unconverged_gravity_is_saved_as_rejected_proposal_not_completed_phase(self):
        from terrain_pipeline.surface_rivers.metric_fluvial_slope_stability import relax_mobile_slopes
        config = MorphodynamicsConfig(steps=1, official_shape=(40, 40), inlet_length_m=15.,
                                      water_parcels=100, sediment_parcels=100, water_iterations=1)

        def rejected(*args, **kwargs):
            return replace(relax_mobile_slopes(*args, **kwargs), converged=False)

        with tempfile.TemporaryDirectory() as directory:
            with patch("terrain_pipeline.surface_rivers.metric_fluvial_slope_stability.relax_mobile_slopes", side_effect=rejected):
                with self.assertRaisesRegex(ValueError, "did not converge"):
                    simulate_fluvial_morphodynamics(config=config, output_dir=directory, gravity_stability=True)
            self.assertFalse((Path(directory) / "backend/checkpoint.npz").exists())
            with np.load(Path(directory) / "failed-native-state.npz", allow_pickle=False) as archive:
                self.assertEqual(archive["completed_phase_names"].tolist(), ["sand", "diffusion", "mud", "finalize"])
                self.assertEqual(json.loads(str(archive["metadata_json"].item()))["proposed_phase"], "gravity")
                np.testing.assert_array_equal(archive["rejected_gravity_end_bed_m"], archive["proposed_bed_m"])
                np.testing.assert_array_equal(archive["rejected_gravity_start_bed_m"], archive["completed_phase_end_bed_m"][-1])
                np.testing.assert_array_equal(archive["rejected_gravity_end_sand_fraction"], archive["sand_fraction"])
                np.testing.assert_array_equal(archive["rejected_gravity_end_active_layer"], archive["active_layer"])
                self.assertEqual(archive["rejected_gravity_step_index"].item(), 0)
                self.assertIn("actual_raw_residual_bulk_m3", json.loads(str(archive["rejected_gravity_ledger_json"].item())))
                self.assertIn("mobile_base_m", archive.files)

    def test_routing_depth_sensitivity_restores_fields_base_and_explicit_v3_transition(self):
        config = MorphodynamicsConfig(steps=4, official_shape=(40, 40), inlet_length_m=15.,
                                      water_parcels=100, sediment_parcels=100, water_iterations=1)
        archive_root = os.environ.get("MORPHODYNAMICS_DRY_DEPTH_TEST_ARCHIVE_ROOT")
        directory_context = tempfile.TemporaryDirectory() if archive_root is None else nullcontext(str(Path(archive_root).resolve()))
        with directory_context as directory:
            parent = simulate_fluvial_morphodynamics(config=replace(config, steps=2), output_dir=directory + "/parent-v3",
                gravity_stability=True)
            self.assertNotIn("routing_dry_depth_m", parent["metadata"])
            simulate_fluvial_morphodynamics(config=replace(config, steps=1), output_dir=directory + "/parent-v2")
            with self.assertRaisesRegex(ValueError, "inherited gravity mobile material"):
                simulate_fluvial_morphodynamics(config=replace(config, steps=1), output_dir=directory + "/unsupported-v2-to-v4",
                    gravity_stability=True, routing_dry_depth_m=.01, resume_checkpoint=directory + "/parent-v2/backend",
                    mechanism_transition={"after_step": 1, "from_algorithm_version": SOURCE_LIMITED_VERSION,
                        "to_algorithm_version": DRY_DEPTH_VERSION})
            with self.assertRaisesRegex(ValueError, "mechanism change"):
                simulate_fluvial_morphodynamics(config=replace(config, steps=1), output_dir=directory + "/unannounced",
                    gravity_stability=True, routing_dry_depth_m=.01, resume_checkpoint=directory + "/parent-v3/backend")
            transition = {"after_step": 2, "from_algorithm_version": GRAVITY_VERSION,
                "to_algorithm_version": DRY_DEPTH_VERSION, "routing_dry_depth_m": .01,
                "from_routing_dry_depth_m": .1, "gravity_parameters": dict(GRAVITY_PARAMETERS),
                "mechanism_identity": mechanism_identity_for(DRY_DEPTH_VERSION),
                "checkpoint_path": parent["metadata"]["checkpoint_end_path"],
                "checkpoint_sha256": parent["metadata"]["checkpoint_end_sha256"],
                "material_state_start_path": parent["metadata"]["material_state_end_path"],
                "material_state_start_sha256": parent["metadata"]["material_state_end_sha256"],
                "reason": "short explicit numerical routing-depth sensitivity inheritance control"}
            if archive_root is not None:
                from tools.verify_fluvial_morphodynamics import archive_result
                artifact = Path(directory) / "parent-v3/detail.npz"
                archive_result(artifact, parent)
                parent_batch = {"path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
                parent_manifest = Path(directory) / "parent-chain.json"
                parent_manifest.write_text(json.dumps({"schema": "saved-pydeltarcm-chain-v1", "batches": [parent_batch]}, indent=2), encoding="utf-8")
                transition.update(parent_manifest_path=str(parent_manifest),
                                  parent_manifest_sha256=hashlib.sha256(parent_manifest.read_bytes()).hexdigest())
                transition["numerical_sensitivity_evidence"] = [parent_batch]
            for field, bad in (("routing_dry_depth_m", .02), ("material_state_start_sha256", "f" * 64)):
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "transition parameters or inherited material"):
                    simulate_fluvial_morphodynamics(config=replace(config, steps=1), output_dir=directory + "/wrong-" + field,
                        gravity_stability=True, routing_dry_depth_m=.01, resume_checkpoint=directory + "/parent-v3/backend",
                        mechanism_transition={**transition, field: bad})
            continuous = simulate_fluvial_morphodynamics(config=config, output_dir=directory + "/continuous",
                gravity_stability=True, routing_dry_depth_m=.01, resume_checkpoint=directory + "/parent-v3/backend",
                mechanism_transition=transition)
            first = simulate_fluvial_morphodynamics(config=replace(config, steps=2), output_dir=directory + "/first",
                gravity_stability=True, routing_dry_depth_m=.01, resume_checkpoint=directory + "/parent-v3/backend",
                mechanism_transition=transition)
            second = simulate_fluvial_morphodynamics(config=replace(config, steps=2), output_dir=directory + "/second",
                gravity_stability=True, routing_dry_depth_m=.01, resume_checkpoint=directory + "/first/backend")
            switched = first
            for field in ("beds_m", "depths_m", "stages_m", "qx_m2_s", "qz_m2_s", "ux_m_s", "uz_m_s", "speed_m_s"):
                np.testing.assert_array_equal(switched[field][0], parent[field][-1])
                np.testing.assert_array_equal(np.concatenate((first[field], second[field][1:])), continuous[field])
            np.testing.assert_array_equal(switched["initial_mobile_base_m"], parent["final_mobile_base_m"])
            self.assertEqual(switched["metadata"]["material_state_start_sha256"], parent["metadata"]["material_state_end_sha256"])
            self.assertEqual(switched["metadata"]["checkpoint_start_sha256"], parent["metadata"]["checkpoint_end_sha256"])
            self.assertEqual(switched["metadata"]["config"], parent["metadata"]["config"])
            self.assertEqual(switched["metadata"]["continuation_identity"], parent["metadata"]["continuation_identity"])
            self.assertNotEqual(switched["metadata"]["mechanism_identity"], parent["metadata"]["mechanism_identity"])
            for result in (continuous, first, second, switched):
                self.assertEqual(result["metadata"]["algorithm_version"], DRY_DEPTH_VERSION)
                self.assertEqual(result["metadata"]["native_water_dry_depth_m"], .01)
                self.assertEqual(result["metadata"]["native_sand_router_dry_depth_m"], float(np.float32(.01)))
                self.assertEqual(result["metadata"]["native_mud_router_dry_depth_m"], float(np.float32(.01)))
            np.testing.assert_array_equal(first["final_mobile_base_m"], second["initial_mobile_base_m"])
            np.testing.assert_array_equal(second["final_mobile_base_m"], continuous["final_mobile_base_m"])
            np.testing.assert_array_equal(np.concatenate((first["times_s"], second["times_s"][1:])), continuous["times_s"])
            for expected, actual in zip(continuous["phases"], first["phases"] + second["phases"]):
                for key in expected:
                    if key == "gravity_ledger":
                        self.assertEqual(expected[key], actual[key])
                    else:
                        np.testing.assert_array_equal(expected[key], actual[key])
            if archive_root is not None:
                batches = []
                for name, result in (("first", first), ("second", second)):
                    artifact = Path(directory) / name / "detail.npz"
                    archive_result(artifact, result)
                    batches.append({"path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()})
                (Path(directory) / "chain.json").write_text(json.dumps({"schema": "saved-pydeltarcm-chain-v1",
                    "batches": [parent_batch] + batches, "mechanism_transitions": [transition]}, indent=2), encoding="utf-8")

    def test_routing_depth_sensitivity_rejects_undeclared_values_and_requires_gravity(self):
        with tempfile.TemporaryDirectory() as directory:
            for value in (.1, .02, 0., float("nan")):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    simulate_fluvial_morphodynamics(output_dir=directory, gravity_stability=True, routing_dry_depth_m=value)
            with self.assertRaises(ValueError):
                simulate_fluvial_morphodynamics(output_dir=directory, routing_dry_depth_m=.01)
            with self.assertRaisesRegex(ValueError, "inherited gravity checkpoint"):
                simulate_fluvial_morphodynamics(output_dir=directory, gravity_stability=True, routing_dry_depth_m=.01)


if __name__ == "__main__":
    unittest.main()
