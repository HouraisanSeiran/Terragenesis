from dataclasses import replace
from contextlib import ExitStack
from copy import deepcopy
import json
import tempfile
from pathlib import Path
import unittest
import zipfile
from unittest.mock import patch

import numpy as np

from terrain_pipeline.channel_inundation import InundationRecipe
from terrain_pipeline.channel_reroute import RerouteRecipe
from terrain_pipeline.channel_stage import StageRecipe
from terrain_pipeline.local_channel_sections import SectionRecipe
from terrain_pipeline.metric_channel_plan import ChannelRecipe
from terrain_pipeline.network_valley import NetworkValleyRecipe
from terrain_pipeline.surface_network_prepare import SurfaceNetworkBudget
from terrain_pipeline.surface_network_recovery import RecoveryRecipe
from terrain_pipeline.valley_geometry import ValleyGeometryRecipe
from terrain_pipeline.surface_domain_prepare import (
    DomainFineConfiguration, SurfaceDomainResources, bind_surface_domain_fine,
    evaluate_surface_domains, load_surface_domains, plan_surface_domains,
    query_surface_domain, save_surface_domains, validate_surface_domains,
    _encode, _hash, _plain, _seal, _edge_ok,
)
from terrain_pipeline.artifacts.contracts import array_hash, digest


def complete_two_domain_inputs():
    shape = (9, 16)
    height = np.zeros(shape)
    labels = np.zeros(shape, np.int64)
    external = np.zeros(shape)
    for domain_id, first_column in ((1, 1), (2, 8)):
        labels[1:8, first_column:first_column + 7] = domain_id
        local = np.full((7, 7), 10.)
        for row in range(1, 7):
            local[row, 2:5] = 5. - row * .01
        local[6, :] = 10.
        local[6, 3] = 4.
        height[1:8, first_column:first_column + 7] = local
        external[2, first_column + 2] = .1
        external[2, first_column + 4] = .1
    land = labels > 0
    return dict(height_m=height, valid_mask=np.ones(shape, bool), domain_labels=labels,
        land_mask=land, ocean_mask=~land, protected_mask=np.zeros(shape, bool),
        coastal_outlets=[(1, 7 * 16 + 4, 8 * 16 + 4), (2, 7 * 16 + 11, 8 * 16 + 11)],
        runoff_m_s=np.where(land, 1e-8, 0.), external_q_m3_s=external,
        spacing_x_m=10., spacing_z_m=10., origin_x_m=0., origin_z_m=0.,
        sea_level_elevation_m=0., vertical_datum="engineering-metres-relative-sea-zero",
        source_identity="engineered-complete-two-domain-grid", source_kind="engineering_synthetic",
        boundary_complete=True, scope="complete_grid", outlet_evidence="engineering_declared",
        resources=SurfaceDomainResources())


def fine_configurations(candidate):
    channel = ChannelRecipe(reference_discharge_m3_s=.1, reference_width_m=8.,
        min_width_m=8., max_width_m=8., reference_depth_m=.5, min_depth_m=.5,
        max_depth_m=.5, max_cut_m=4., min_bed_slope_m_per_m=.00001)
    return {domain_id: DomainFineConfiguration(
        bind_surface_domain_fine(candidate, domain_id, 1., 1.), np.array([4.2]), channel,
        SectionRecipe(), StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
        InundationRecipe(max_lateral_reach_m=15.), SurfaceNetworkBudget(4., 5000., 5000.),
        NetworkValleyRecipe(3.75, 30., 30., .00001),
        ValleyGeometryRecipe(4., 10000., 100000., 100000.), RerouteRecipe(),
        RecoveryRecipe(max_attempts=4)) for domain_id in (1, 2)}


def rehash(result):
    result.pop("identity_sha256", None)
    result["identity_sha256"] = _hash(result)
    return result


def write_rehashed_bundle(result, path):
    arrays = {}
    tree = _encode(result, arrays)
    with Path(path).open("wb") as stream:
        np.savez_compressed(stream, manifest=json.dumps({"format_version": 1,
            "tree": tree, "tree_sha256": digest(tree)}), **arrays)


class SurfaceDomainPrepareTests(unittest.TestCase):
    def test_saved_support_preserves_evaluation_constraints_without_sampling(self):
        from terrain_pipeline.surface_engineering_prepare import load_surface_engineering
        from tests.test_surface_variable_storage import static_disabled
        root = Path(__file__).resolve().parents[1]
        bundle = load_surface_engineering(root / "verification/surface-engineering-prepare/run-20260930T193214454541Z/two-domain-engineering.npz")
        evaluation = bundle["evaluation"]
        support = {identity: saved for mesh in bundle["domain_mosaic"]["domain_meshes"]
                   for identity, saved in mesh["proof_h0_support"].items()}
        with ExitStack() as stack:
            static_disabled(stack)
            self.assertIs(validate_surface_domains(evaluation, saved_support=support), evaluation)
            with self.assertRaises(ValueError):
                validate_surface_domains(evaluation["candidate"], allow_unprepared=True, saved_support=support)
            for mode in ("missing", "support", "swapped", "charged", "usage", "config"):
                changed = deepcopy(_plain(evaluation))
                saved = deepcopy(_plain(support))
                if mode == "missing":
                    saved.pop(next(iter(saved)))
                elif mode == "support":
                    saved[next(iter(saved))]["weights"][0, 0] += .2
                elif mode == "swapped":
                    first, second = list(saved)
                    saved[first], saved[second] = saved[second], saved[first]
                    saved[first]["indices"][0, 0] += 1
                elif mode == "charged":
                    changed["domains"][0]["charged_fine_cells"] += 1
                elif mode == "usage":
                    changed["usage"]["fine_work_cells"] += 1
                else:
                    changed["configurations"]["1"]["outlet_stage_m"] += 1.
                changed["identity_sha256"] = _hash({key: value for key, value in changed.items()
                                                    if key != "identity_sha256"})
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    validate_surface_domains(changed, saved_support=saved)

    def test_complete_two_domains_prepare_reload_readonly(self):
        inputs = complete_two_domain_inputs()
        candidate = plan_surface_domains(**inputs)
        self.assertEqual(candidate["status"], "candidate")
        validate_surface_domains(candidate, allow_unprepared=True)
        result = evaluate_surface_domains(candidate, fine_configurations(candidate))
        self.assertEqual(result["status"], "prepared", [(item["domain_id"], item["reason"]) for item in result["domains"]])
        validate_surface_domains(result)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "complete.npz"
            save_surface_domains(result, path)
            with patch("terrain_pipeline.surface_domain_prepare.plan_channel", side_effect=AssertionError("load planned")), \
                 patch("terrain_pipeline.surface_domain_prepare.recover_surface_network", side_effect=AssertionError("load recovered")), \
                 patch("terrain_pipeline.surface_domain_prepare._flood", side_effect=AssertionError("load routed")):
                loaded = load_surface_domains(path)
                window = query_surface_domain(loaded, 1, slice(None), slice(None))
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
            self.assertGreater(int(window["wet_mask"].sum()), 0)
            self.assertGreater(float(window["total_cut_m"].sum()), 0.)
            with self.assertRaises(ValueError):
                window["final_surface_m"].flags.writeable = True
            with self.assertRaises(TypeError):
                loaded["usage"]["attempts"] = 0

    def test_complete_land_q_and_coastal_transfer_two_tributaries(self):
        inputs = complete_two_domain_inputs()
        result = plan_surface_domains(**inputs)
        receiver = result["arrays"]["receiver"]
        labels = inputs["domain_labels"].ravel()
        donors = np.flatnonzero(receiver >= 0)
        np.testing.assert_array_equal(labels[donors], labels[receiver[donors]])
        self.assertEqual(int(np.count_nonzero(receiver >= -1)), int(inputs["land_mask"].sum()))
        self.assertEqual(int(np.count_nonzero(receiver == -1)), 2)
        local = result["arrays"]["local_discharge_m3_s"]
        self.assertAlmostEqual(sum(item["discharge_m3_s"] for item in result["coastal_transfers"]), float(local.sum()))
        self.assertEqual(result["unrouted_local_discharge_m3_s"], 0.)
        for transfer in result["coastal_transfers"]:
            self.assertEqual(labels[transfer["ocean_cell"]], 0)
            self.assertGreater(transfer["discharge_m3_s"], .2)
        paths = []
        for source in (2 * 16 + 3, 2 * 16 + 5):
            path_cells = []
            while source >= 0:
                path_cells.append(source)
                source = int(receiver[source])
            paths.append(path_cells)
        self.assertNotEqual(paths[0][0], paths[1][0])
        self.assertTrue(set(paths[0][1:]) & set(paths[1][1:]))

    def test_deterministic_and_original_height_unchanged(self):
        inputs = complete_two_domain_inputs()
        before = array_hash(inputs["height_m"])
        first = plan_surface_domains(**inputs)
        second = plan_surface_domains(**inputs)
        self.assertEqual(first["identity_sha256"], second["identity_sha256"])
        self.assertEqual(array_hash(inputs["height_m"]), before)
        self.assertFalse(np.shares_memory(inputs["height_m"], first["arrays"]["working_fill_m"]))

    def test_unknown_unassigned_preserves_nonzero_local_water(self):
        inputs = complete_two_domain_inputs()
        inputs["domain_labels"][1, 1] = -1
        result = plan_surface_domains(**inputs)
        self.assertEqual(result["status"], "diagnostic")
        self.assertIn("unknown_or_unassigned_cells", result["failures"])
        self.assertGreater(result["unrouted_local_discharge_m3_s"], .4)
        validate_surface_domains(result, allow_unprepared=True)

    def test_label_contract_invalid(self):
        inputs = complete_two_domain_inputs()
        inputs["domain_labels"][0, 0] = 1
        with self.assertRaises(ValueError):
            plan_surface_domains(**inputs)

    def test_false_ocean_above_sea(self):
        inputs = complete_two_domain_inputs()
        inputs["height_m"][8, 4] = 100.
        with self.assertRaisesRegex(ValueError, "sea level"):
            plan_surface_domains(**inputs)

    def test_false_coast_interior_ocean_not_boundary_connected(self):
        inputs = complete_two_domain_inputs()
        inputs["domain_labels"][4, 4] = 0
        inputs["land_mask"][4, 4] = False
        inputs["ocean_mask"][4, 4] = True
        inputs["height_m"][4, 4] = 0.
        inputs["runoff_m_s"][4, 4] = 0.
        inputs["coastal_outlets"][0] = (1, 4 * 16 + 3, 4 * 16 + 4)
        with self.assertRaisesRegex(ValueError, "false coast"):
            plan_surface_domains(**inputs)

    def test_domain_without_outlet_is_diagnostic(self):
        inputs = complete_two_domain_inputs()
        inputs["coastal_outlets"] = inputs["coastal_outlets"][:1]
        result = plan_surface_domains(**inputs)
        self.assertEqual(result["status"], "diagnostic")
        self.assertEqual(result["domains"][0]["status"], "routed")
        self.assertEqual(result["domains"][1]["status"], "diagnostic")
        self.assertGreater(result["unrouted_local_discharge_m3_s"], .2)
        validate_surface_domains(result, allow_unprepared=True)

    def test_protected_land_nonzero_and_zero_are_explicit_failures(self):
        for zero in (False, True):
            inputs = complete_two_domain_inputs()
            inputs["protected_mask"][1, 1] = True
            if zero:
                inputs["runoff_m_s"][1, 1] = 0.
            result = plan_surface_domains(**inputs)
            self.assertEqual(result["status"], "diagnostic")
            self.assertTrue(any("protected_land" in reason for reason in result["failures"]))
            self.assertGreater(result["unrouted_local_discharge_m3_s"], .4)

    def test_d8_diagonal_requires_both_orthogonal_supports(self):
        allowed = np.ones((3, 3), bool)
        self.assertTrue(_edge_ok(0, 4, allowed.shape, allowed))
        allowed[0, 1] = False
        self.assertFalse(_edge_ok(0, 4, allowed.shape, allowed))
        allowed[0, 1] = True
        allowed[1, 0] = False
        self.assertFalse(_edge_ok(0, 4, allowed.shape, allowed))

    def test_corner_only_land_component_cannot_drain(self):
        inputs = complete_two_domain_inputs()
        for cell in ((1, 1), (1, 2), (2, 1)):
            inputs["domain_labels"][cell] = 0
            inputs["land_mask"][cell] = False
            inputs["ocean_mask"][cell] = True
            inputs["height_m"][cell] = 0.
            inputs["runoff_m_s"][cell] = 0.
        inputs["domain_labels"][1, 1] = 1
        inputs["land_mask"][1, 1] = True
        inputs["ocean_mask"][1, 1] = False
        inputs["height_m"][1, 1] = 10.
        result = plan_surface_domains(**inputs)
        self.assertEqual(result["status"], "diagnostic")
        self.assertIn("supported route", result["domains"][0]["reason"])

    def test_coarse_resource_rejected_before_flood(self):
        inputs = complete_two_domain_inputs()
        inputs["resources"] = SurfaceDomainResources(max_coarse_cells=10)
        with patch("terrain_pipeline.surface_domain_prepare._flood", side_effect=AssertionError("routed")):
            result = plan_surface_domains(**inputs)
        self.assertIn("coarse_resource_limit", result["failures"])

    def test_retained_resource_preflight_before_normalization(self):
        inputs = complete_two_domain_inputs()
        inputs["resources"] = SurfaceDomainResources(max_retained_bytes=100)
        with patch("terrain_pipeline.surface_domain_prepare._normalize_inputs", side_effect=AssertionError("copied")):
            with self.assertRaisesRegex(ValueError, "resource preflight"):
                plan_surface_domains(**inputs)

    def test_joint_fine_preflight_no_partial_recovery(self):
        inputs = complete_two_domain_inputs()
        inputs["resources"] = SurfaceDomainResources(max_fine_cells=5000)
        candidate = plan_surface_domains(**inputs)
        with patch("terrain_pipeline.surface_domain_prepare.recover_surface_network", side_effect=AssertionError("recovered")):
            result = evaluate_surface_domains(candidate, fine_configurations(candidate))
        self.assertEqual(result["status"], "diagnostic")
        self.assertEqual(result["usage"]["fine_cells"], 0)
        validate_surface_domains(result, allow_unprepared=True)

    def test_joint_attempt_finework_bytes_preflight(self):
        for limits in ({"max_attempts": 1}, {"max_fine_work_cells": 5000}, {"max_retained_bytes": 1000000}):
            inputs = complete_two_domain_inputs()
            inputs["resources"] = SurfaceDomainResources(**limits)
            candidate = plan_surface_domains(**inputs)
            with patch("terrain_pipeline.surface_domain_prepare.recover_surface_network", side_effect=AssertionError("recovered")):
                result = evaluate_surface_domains(candidate, fine_configurations(candidate))
            self.assertEqual(result["status"], "diagnostic")
            self.assertEqual(result["usage"]["attempts"], 0)

    def test_missing_fine_domain_cannot_be_ignored(self):
        candidate = plan_surface_domains(**complete_two_domain_inputs())
        configs = fine_configurations(candidate)
        configs.pop(2)
        with self.assertRaisesRegex(ValueError, "every land domain"):
            evaluate_surface_domains(candidate, configs)

    def test_fine_mask_domain_coast_protection_binding(self):
        candidate = plan_surface_domains(**complete_two_domain_inputs())
        for name in ("domain_mask", "protected_mask", "legal_outlet_mask"):
            configs = fine_configurations(candidate)
            fine = configs[1].fine
            mask = getattr(fine, name).copy()
            mask[20, 20] = not mask[20, 20]
            configs[1] = replace(configs[1], fine=replace(fine, **{name: mask}))
            with patch("terrain_pipeline.surface_domain_prepare.recover_surface_network", side_effect=AssertionError("recovered")):
                result = evaluate_surface_domains(candidate, configs)
            self.assertEqual(result["status"], "diagnostic")
            self.assertTrue(any("masks disagree" in reason for reason in result["failures"]))

    def test_actual_fine_budget_failure_preserved(self):
        candidate = plan_surface_domains(**complete_two_domain_inputs())
        configs = fine_configurations(candidate)
        configs = {key: replace(value, budget=SurfaceNetworkBudget(4., 0., 0.),
            recovery_recipe=RecoveryRecipe(max_attempts=1)) for key, value in configs.items()}
        result = evaluate_surface_domains(candidate, configs)
        self.assertEqual(result["status"], "diagnostic")
        self.assertTrue(result["domains"][0]["recovery"]["attempts"][0]["failures"]["area"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.npz"
            save_surface_domains(result, path)
            with self.assertRaises(ValueError):
                load_surface_domains(path)
            load_surface_domains(path, allow_unprepared=True)

    def test_cancel_flood_retains_completed_domain_prefix(self):
        def cancel():
            cancel.calls += 1
            return cancel.calls > 50
        cancel.calls = 0
        result = plan_surface_domains(**complete_two_domain_inputs(), cancel=cancel)
        self.assertEqual(result["status"], "diagnostic")
        self.assertEqual(result["domains"][0]["status"], "routed")
        self.assertEqual(result["domains"][1]["status"], "pending")
        validate_surface_domains(result, allow_unprepared=True)

    def test_cancel_prepare_retains_actual_fine_prefix_never_publish(self):
        candidate = plan_surface_domains(**complete_two_domain_inputs())
        def cancel():
            cancel.calls += 1
            return cancel.calls > 1
        cancel.calls = 0
        result = evaluate_surface_domains(candidate, fine_configurations(candidate), cancel=cancel)
        self.assertEqual(result["status"], "diagnostic")
        self.assertEqual(result["domains"][0]["status"], "prepared")
        self.assertEqual(result["domains"][1]["status"], "pending")
        validate_surface_domains(result, allow_unprepared=True)
        with self.assertRaises(ValueError):
            query_surface_domain(result, 1, slice(None), slice(None))

    def test_subdomain_or_unverified_boundary_never_system_prepared(self):
        for change in ({"scope": "subdomain"}, {"boundary_complete": False}):
            inputs = complete_two_domain_inputs()
            inputs.update(change)
            candidate = plan_surface_domains(**inputs)
            result = evaluate_surface_domains(candidate, fine_configurations(candidate))
            self.assertEqual(result["status"], "candidate")
            self.assertTrue(all(item["status"] == "prepared" for item in result["domains"]))
            with self.assertRaises(ValueError):
                validate_surface_domains(result)

    def test_rehashed_cross_domain_route_rejected(self):
        result = _plain(plan_surface_domains(**complete_two_domain_inputs()))
        result["arrays"]["receiver"] = result["arrays"]["receiver"].copy()
        result["arrays"]["receiver"][3 * 16 + 7] = 3 * 16 + 8
        with self.assertRaises(ValueError):
            validate_surface_domains(rehash(result), allow_unprepared=True)

    def test_rehashed_nonconservative_q_transfer_fill_rejected(self):
        for field in ("discharge_m3_s", "working_fill_m", "coastal_transfers"):
            result = _plain(plan_surface_domains(**complete_two_domain_inputs()))
            if field == "coastal_transfers":
                result[field][0]["discharge_m3_s"] = 0.
            else:
                result["arrays"][field] = result["arrays"][field].copy()
                result["arrays"][field][3, 4] += 1.
            with self.assertRaises(ValueError):
                validate_surface_domains(rehash(result), allow_unprepared=True)

    def test_rehashed_usage_zero_cannot_hide_actual_fine_work(self):
        candidate = plan_surface_domains(**complete_two_domain_inputs())
        result = _plain(evaluate_surface_domains(candidate, fine_configurations(candidate)))
        for item in result["domains"]:
            item["charged_coarse_cells"] = 0
            item["charged_fine_cells"] = 0
        result["usage"]["coarse_work_cells"] = 0
        result["usage"]["fine_cells"] = 0
        with self.assertRaisesRegex(ValueError, "charged"):
            validate_surface_domains(rehash(result))

    def test_rehashed_original_attempt_cap_cannot_be_relaxed(self):
        candidate = plan_surface_domains(**complete_two_domain_inputs())
        result = _plain(evaluate_surface_domains(candidate, fine_configurations(candidate)))
        result["configurations"]["1"]["recovery_recipe"]["max_attempts"] = 1
        with self.assertRaisesRegex(ValueError, "recovery.*bounds"):
            validate_surface_domains(rehash(result))

    def test_rehashed_fine_geometry_and_publication_rejected(self):
        candidate = plan_surface_domains(**complete_two_domain_inputs())
        result = _plain(evaluate_surface_domains(candidate, fine_configurations(candidate)))
        surface = result["domains"][0]["recovery"]["surface"]
        surface["arrays"]["final_surface_m"] = surface["arrays"]["final_surface_m"].copy()
        surface["arrays"]["final_surface_m"][30, 30] -= 100.
        surface["identity"]["parameters"]["output_sha256"] = digest({name: array_hash(value) for name, value in surface["arrays"].items()})
        surface["identity_sha256"] = digest(surface["identity"])
        rehash(result["domains"][0]["recovery"])
        rehash(result)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rehash.npz"
            write_rehashed_bundle(result, path)
            with self.assertRaises(ValueError):
                load_surface_domains(path)

    def test_candidate_default_load_and_duplicate_member_rejected(self):
        candidate = plan_surface_domains(**complete_two_domain_inputs())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.npz"
            save_surface_domains(candidate, path)
            with self.assertRaises(ValueError):
                load_surface_domains(path)
            load_surface_domains(path, allow_unprepared=True)
            with self.assertRaises(FileExistsError):
                save_surface_domains(candidate, path)
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("manifest.npy", archive.read("manifest.npy"))
            with self.assertRaises(ValueError):
                load_surface_domains(path, allow_unprepared=True)

    def test_nonfinite_valid_source_rejected(self):
        inputs = complete_two_domain_inputs()
        inputs["height_m"][1, 1] = np.nan
        with self.assertRaises(ValueError):
            plan_surface_domains(**inputs)


if __name__ == "__main__":
    unittest.main()
