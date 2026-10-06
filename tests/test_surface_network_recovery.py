from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.artifacts.contracts import digest
from terrain_pipeline.channel_reroute import RerouteRecipe, reroute_channel
from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel
from terrain_pipeline.surface_network_recovery import (
    FineGrid, RecoveryRecipe, _fingerprint, load_surface_network_recovery,
    recover_surface_network, save_surface_network_recovery,
    validate_surface_network_recovery,
    prepare_with_reroute,
)
from terrain_pipeline.channel_inundation import InundationRecipe
from terrain_pipeline.channel_stage import StageRecipe
from terrain_pipeline.local_channel_sections import SectionRecipe
from terrain_pipeline.network_valley import NetworkValleyRecipe
from terrain_pipeline.surface_network_prepare import SurfaceNetworkBudget
from terrain_pipeline.valley_geometry import ValleyGeometryRecipe
from tests.test_channel_stage_inundation import confluence_plan


def recovery_case(kind="baseline"):
    base = confluence_plan()
    arrays = base["arrays"]
    height = arrays["source_height_m"].copy()
    discharge = arrays["discharge_m3_s"].copy()
    discharge.flat[[17, 24, 31, 38, 45]] = .2
    receiver, order, outlets = arrays["receiver"], arrays["order"], arrays["outlet_mask"]
    params = base["identity"]["parameters"]
    channel = ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__})
    if kind == "valley":
        height[3, 3] += 3.5
    if kind == "reroute":
        height[:] = 10.
        receiver = np.full(49, -1, dtype=np.int64)
        for row in range(1, 6):
            receiver[row * 7 + 3] = (row + 1) * 7 + 3
        outlets = (receiver == -1).reshape((7, 7))
        order = np.array(list(np.flatnonzero(outlets.ravel())) + [38, 31, 24, 17, 10], dtype=np.int64)
        discharge[:] = 0.
        discharge[1:, 3] = .1
        channel = replace(channel, reference_width_m=2., min_width_m=2., max_width_m=2.)
    plan = plan_channel(height, receiver, order, outlets, discharge,
                        10., 10., 0., 0., 0., "recovery-synthetic-" + kind, channel)
    coarse_domain = np.ones((7, 7), bool)
    coarse_protected = np.zeros((7, 7), bool)
    empty = np.zeros((61, 61), bool)
    protected = empty.copy()
    legal = empty.copy()
    legal[-1, 27:34] = True
    outlet_stage = np.array([5.2])
    network = NetworkValleyRecipe(3.75, 30., 30., .00001)
    if kind == "reroute":
        coarse_protected[3, 3] = True
        protected[30, 30] = True
        outlet_stage = np.array([9.8])
        network = NetworkValleyRecipe(1., 2., 2., .00001)
    return dict(plan=plan, coarse_domain=coarse_domain, coarse_protected=coarse_protected,
        fine=FineGrid(0., 0., 1., 1., (61, 61), ~empty, protected, legal),
        outlet_stage_m=outlet_stage, section_recipe=SectionRecipe(),
        stage_recipe=StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
        inundation_recipe=InundationRecipe(max_lateral_reach_m=15.),
        budget=SurfaceNetworkBudget(4., 5000., 5000.), network_recipe=network,
        valley_recipe=ValleyGeometryRecipe(4., 10000., 100000., 100000.),
        reroute_recipe=RerouteRecipe(), recovery_recipe=RecoveryRecipe(max_attempts=20))


def mountain_coast_case():
    shape = (17, 17)
    height = np.full(shape, 135.)
    for row in range(1, 17):
        height[row, 7:10] = 1.4 - row * .02
    for row in range(2, 6):
        for column in (row + 2, 14 - row):
            height[row, column - 1:column + 2] = 1.4 - row * .02
    height[1, 3:6] = 1.36
    height[1, 11:14] = 1.36
    height[15, 7:10] = 1.08
    height[16, 7:10] = 1.06
    receiver = np.full(height.size, -1, dtype=np.int64)
    for row in range(2, 6):
        for column in (row + 2, 14 - row):
            target = 8 if row == 5 else column + (1 if column < 8 else -1)
            receiver[row * 17 + column] = (row + 1) * 17 + target
    for row in range(6, 15):
        receiver[row * 17 + 8] = (row + 1) * 17 + 8
    outlets = (receiver == -1).reshape(shape)
    order = []
    seen = set()
    for start in range(height.size):
        chain = []
        cell = start
        while cell >= 0 and cell not in seen:
            seen.add(cell)
            chain.append(cell)
            cell = int(receiver[cell])
        order.extend(reversed(chain))
    discharge = np.zeros(height.size)
    discharge[[2 * 17 + 4, 2 * 17 + 12]] = .1
    for cell in reversed(order):
        if receiver[cell] >= 0:
            discharge[receiver[cell]] += discharge[cell]
    channel = ChannelRecipe(reference_discharge_m3_s=.1, reference_width_m=4.,
        min_width_m=4., max_width_m=4., reference_depth_m=.5,
        min_depth_m=.5, max_depth_m=.5, min_bed_slope_m_per_m=.00001, max_cut_m=4.)
    plan = plan_channel(height, receiver, np.array(order, dtype=np.int64), outlets,
        discharge.reshape(shape), 10., 10., 0., 0., 1.08, "engineered-mountain-coast-not-real", channel)
    empty = np.zeros((161, 161), bool)
    legal = empty.copy()
    legal[150:, 70:91] = True
    case = recovery_case()
    case.update(plan=plan, coarse_domain=np.ones(shape, bool), coarse_protected=np.zeros(shape, bool),
        fine=FineGrid(0., 0., 1., 1., (161, 161), ~empty, empty, legal),
        outlet_stage_m=np.array([1.3]), inundation_recipe=InundationRecipe(max_lateral_reach_m=15.),
        network_recipe=NetworkValleyRecipe(1., 4., 4., .00001),
        recovery_recipe=RecoveryRecipe(max_attempts=2))
    ocean = np.zeros(shape, bool)
    ocean[15:, 7:10] = True
    ocean.flags.writeable = False
    land = ~ocean
    land.flags.writeable = False
    return case, land, ocean


def rewrite_bundle(path, transform):
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files if name != "manifest"}
        manifest = json.loads(str(archive["manifest"].item()))
    transform(manifest, arrays)
    manifest["tree_sha256"] = digest(manifest["tree"])
    np.savez_compressed(path, manifest=json.dumps(manifest, sort_keys=True), **arrays)


class SurfaceNetworkRecoveryTests(unittest.TestCase):
    def test_baseline_conservative_success(self):
        case = recovery_case()
        original = case["plan"]["arrays"]["source_height_m"].copy()
        result = recover_surface_network(**case)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["selected_method"], "baseline")
        np.testing.assert_array_equal(original, case["plan"]["arrays"]["source_height_m"])
        self.assertEqual(result["surface"]["status"], "prepared")

    def test_valley_requires_actual_fine_ledger(self):
        result = recover_surface_network(**recovery_case("valley"))
        self.assertTrue(result["accepted"])
        self.assertEqual(result["selected_method"], "network_valley")
        self.assertFalse(result["attempts"][0]["accepted"])
        self.assertEqual(result["fine_ledger"]["status"], "prepared")
        self.assertGreater(result["fine_ledger"]["summary"]["valley_cut_volume_m3"], 0.)

    def test_automatic_protection_reroute_uses_upstream_donor(self):
        case = recovery_case("reroute")
        result = recover_surface_network(**case)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["selected_method"], "reroute_bed")
        chosen = result["attempts"][-1]
        self.assertNotEqual(chosen["source_grid_zx"], [3, 3])
        self.assertLess(chosen["source_grid_zx"][0], 3)
        self.assertGreater(chosen["anchor_grid_zx"][0], 3)
        self.assertNotIn([3, 3], chosen["path_grid_zx"])
        self.assertFalse(np.any(result["final_plan"]["arrays"]["channel_mask"] & case["coarse_protected"]))
        self.assertEqual(result["final_plan"]["arrays"]["discharge_m3_s"][6, 3], .1)

    def test_budget_failure_has_trace_and_never_relaxes(self):
        case = recovery_case()
        case["budget"] = SurfaceNetworkBudget(4., 0., 0.)
        result = recover_surface_network(**case)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["attempts"][0]["failures"]["volume"])
        self.assertEqual(result["inputs"]["budget"]["max_cut_volume_m3"], 0.)

    def test_fine_ledger_total_budget_rejects_surface_prepared(self):
        case = recovery_case("valley")
        case["valley_recipe"] = replace(case["valley_recipe"], max_total_cut_volume_m3=0.)
        case["recovery_recipe"] = RecoveryRecipe(max_attempts=2)
        result = recover_surface_network(**case)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["surface"]["status"], "prepared")
        self.assertTrue(result["attempts"][1]["failures"]["ledger_total_volume"])

    def test_coarse_fine_mask_mismatch_rejected(self):
        for mask in ("domain_mask", "protected_mask"):
            case = recovery_case()
            changed = getattr(case["fine"], mask).copy()
            changed[30, 30] = not changed[30, 30]
            case["fine"] = replace(case["fine"], **{mask: changed})
            with self.subTest(mask=mask), self.assertRaisesRegex(ValueError, "disagree"):
                recover_surface_network(**case)

    def test_domain_blocks_coarse_route_and_fine_cut(self):
        case = recovery_case()
        domain = case["fine"].domain_mask.copy()
        domain[30, 30] = False
        case["fine"] = replace(case["fine"], domain_mask=domain)
        case["coarse_domain"][3, 3] = False
        case["recovery_recipe"] = RecoveryRecipe(max_attempts=2)
        result = recover_surface_network(**case)
        self.assertFalse(result["accepted"])
        self.assertTrue(result["attempts"][0]["failures"]["coarse_domain"])

    def test_nonconservative_q_rejected_before_attempts(self):
        case = recovery_case()
        arrays = case["plan"]["arrays"]
        discharge = arrays["discharge_m3_s"].copy()
        discharge[2, 3] = .1
        case["plan"] = plan_channel(arrays["source_height_m"], arrays["receiver"], arrays["order"],
            arrays["outlet_mask"], discharge, 10., 10., 0., 0., 0., "bad-q", ChannelRecipe(
                **{name: case["plan"]["identity"]["parameters"][name] for name in ChannelRecipe.__dataclass_fields__}))
        with self.assertRaisesRegex(ValueError, "conservative"):
            recover_surface_network(**case)

    def test_all_derived_plan_fields_recomputed(self):
        for field in ("bounded_bed_m", "channel_mask", "nominal_width_m"):
            case = recovery_case()
            case["plan"] = deepcopy(case["plan"])
            case["plan"]["arrays"][field] = case["plan"]["arrays"][field].copy()
            case["plan"]["arrays"][field].flat[9] = 0
            with self.subTest(field=field), self.assertRaises(ValueError):
                recover_surface_network(**case)

    def test_reroute_pairs_strict_integer_and_bed_bound(self):
        case = recovery_case("reroute")
        for endpoint in ((1.1, 3), (True, 3), (1,), (1, 3, 4)):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                reroute_channel(case["plan"], endpoint, (4, 3), case["coarse_domain"], case["coarse_protected"])
        case["reroute_recipe"] = RerouteRecipe(max_extra_cut_m=4.1)
        with self.assertRaisesRegex(ValueError, "original allowed bed"):
            recover_surface_network(**case)

    def test_search_attempt_exhaustion_is_deterministic(self):
        case = recovery_case("reroute")
        case["reroute_recipe"] = RerouteRecipe(max_expansions=1)
        first = recover_surface_network(**case)
        second = recover_surface_network(**case)
        self.assertFalse(first["accepted"])
        self.assertEqual(first["identity_sha256"], second["identity_sha256"])
        self.assertTrue(any("expansion bound" in attempt.get("error", "") for attempt in first["attempts"]))
        self.assertLessEqual(len(first["attempts"]), case["recovery_recipe"].max_attempts)

    def test_fine_work_exhaustion_preserves_diagnostic(self):
        case = recovery_case("valley")
        case["recovery_recipe"] = RecoveryRecipe(max_total_fine_cells=61 * 61)
        result = recover_surface_network(**case)
        self.assertEqual(len(result["attempts"]), 1)
        self.assertFalse(result["accepted"])
        self.assertTrue(result["summary"]["fine_work_limit_reached"])

    def test_cell_memory_and_recipe_bounds_rejected(self):
        for recipe in (RecoveryRecipe(max_fine_cells=100), RecoveryRecipe(max_coarse_cells=10),
                       RecoveryRecipe(max_working_bytes=100)):
            case = recovery_case()
            case["recovery_recipe"] = recipe
            with self.subTest(recipe=recipe), self.assertRaises(ValueError):
                recover_surface_network(**case)
        with self.assertRaises(ValueError):
            RecoveryRecipe(max_attempts=True)
        with self.assertRaises(ValueError):
            FineGrid(0., 0., 0., 1., (3, 3), np.ones((3, 3), bool), np.zeros((3, 3), bool), np.zeros((3, 3), bool))

    def test_outlet_stage_and_source_identity_invalid(self):
        case = recovery_case()
        case["outlet_stage_m"] = np.array([np.nan])
        with self.assertRaises(ValueError):
            recover_surface_network(**case)

    def test_legal_outlet_elsewhere_cannot_replace_active_outlet(self):
        case = recovery_case()
        legal = case["fine"].legal_outlet_mask.copy()
        legal[60, 30] = False
        case["fine"] = replace(case["fine"], legal_outlet_mask=legal)
        with self.assertRaisesRegex(ValueError, "active plan outlets"):
            recover_surface_network(**case)
        case = recovery_case()
        case["plan"]["identity"]["parameters"]["source_identity"] = ""
        with self.assertRaises(ValueError):
            recover_surface_network(**case)

    def test_success_and_failure_bundles_readonly_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind in ("baseline", "valley", "reroute", "failed"):
                case = recovery_case("baseline" if kind == "failed" else kind)
                if kind == "failed":
                    case["budget"] = SurfaceNetworkBudget(4., 0., 0.)
                    case["recovery_recipe"] = RecoveryRecipe(max_attempts=2)
                original = recover_surface_network(**case)
                path = Path(directory) / (kind + ".npz")
                save_surface_network_recovery(original, path)
                loaded = load_surface_network_recovery(path)
                self.assertEqual(loaded["identity_sha256"], original["identity_sha256"])
                with self.assertRaises(ValueError):
                    loaded["final_plan"]["arrays"]["source_height_m"].flags.writeable = True
                with self.assertRaises(FileExistsError):
                    save_surface_network_recovery(original, path)

    def test_rehashed_summary_status_and_surface_forgery_rejected(self):
        result = recover_surface_network(**recovery_case("valley"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forged.npz"
            save_surface_network_recovery(result, path)
            rewrite_bundle(path, lambda manifest, arrays: manifest["tree"]["attempts"][0].update(accepted=True))
            with self.assertRaisesRegex(ValueError, "semantic replay"):
                load_surface_network_recovery(path)
        case = recovery_case()
        case["budget"] = SurfaceNetworkBudget(4., 0., 0.)
        forged = recover_surface_network(**case)
        forged.update(status="accepted", accepted=True, selected_method="baseline")
        forged["identity_sha256"] = _fingerprint({key: value for key, value in forged.items() if key != "identity_sha256"})
        with self.assertRaises(ValueError):
            validate_surface_network_recovery(forged)

    def test_hash_tamper_and_load_garbage_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tampered.npz"
            save_surface_network_recovery(recover_surface_network(**recovery_case()), path)
            def corrupt(manifest, arrays):
                arrays[next(iter(arrays))] = arrays[next(iter(arrays))].copy()
                arrays[next(iter(arrays))].flat[0] += 1
            rewrite_bundle(path, corrupt)
            with self.assertRaises(ValueError):
                load_surface_network_recovery(path)
            path.write_bytes(b"not a bundle")
            with self.assertRaises(ValueError):
                load_surface_network_recovery(path)

    def test_atomic_save_failure_leaves_no_destination(self):
        result = recover_surface_network(**recovery_case())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "never.npz"
            with patch("terrain_pipeline.surface_network_recovery.os.link", side_effect=OSError("no link")):
                with self.assertRaises(OSError):
                    save_surface_network_recovery(result, path)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_legacy_explicit_reroute_interface_still_accepted(self):
        case = recovery_case("reroute")
        fine = case["fine"]
        result = prepare_with_reroute(case["plan"], (1, 3), (4, 3),
            case["coarse_domain"], case["coarse_protected"], fine.origin_x_m, fine.origin_z_m,
            fine.spacing_x_m, fine.spacing_z_m, fine.shape_zx, fine.domain_mask,
            fine.protected_mask, fine.legal_outlet_mask, case["outlet_stage_m"],
            case["section_recipe"], case["stage_recipe"], case["inundation_recipe"], case["budget"])
        self.assertTrue(result["accepted"])

    def test_rehashed_actual_surface_array_cannot_load(self):
        result = recover_surface_network(**recovery_case())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "surface_forged.npz"
            save_surface_network_recovery(result, path)
            def corrupt(manifest, arrays):
                from terrain_pipeline.artifacts.contracts import array_hash
                reference = manifest["tree"]["surface"]["arrays"]["final_surface_m"]
                array = arrays[reference["$array"]].copy()
                array[30, 30] -= .1
                arrays[reference["$array"]] = array
                reference["sha256"] = array_hash(array)
            rewrite_bundle(path, corrupt)
            with self.assertRaisesRegex(ValueError, "semantic replay"):
                load_surface_network_recovery(path)

    def test_manifest_duplicate_keys_and_nonfinite_constants_rejected(self):
        result = recover_surface_network(**recovery_case())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strict_json.npz"
            save_surface_network_recovery(result, path)
            with np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files if name != "manifest"}
                encoded = str(archive["manifest"].item())
            for invalid, reason in (
                    ('{"format_version":0,' + encoded[1:], "duplicate"),
                    ('{"extra":NaN,' + encoded[1:], "nonfinite"),
                    ('{"extra":Infinity,' + encoded[1:], "nonfinite")):
                np.savez_compressed(path, manifest=invalid, **arrays)
                with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                    load_surface_network_recovery(path)

    def test_manifest_scalar_unicode_header_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong_manifest.npz"
            for manifest in (np.array(["{}"]), np.array(1), np.array(b"{}")):
                np.savez_compressed(path, manifest=manifest)
                with self.subTest(dtype=manifest.dtype), self.assertRaisesRegex(ValueError, "Unicode scalar"):
                    load_surface_network_recovery(path)

    def test_mountain_coast_has_frozen_evidence_and_actual_gate(self):
        case, land, ocean = mountain_coast_case()
        height = case["plan"]["arrays"]["source_height_m"]
        self.assertGreaterEqual(float(height.max() - height.min()), 100.)
        self.assertFalse(land.flags.writeable)
        self.assertFalse(ocean.flags.writeable)
        result = recover_surface_network(**case)
        self.assertTrue(result["accepted"], result["attempts"])
        self.assertEqual(result["summary"]["outlet_evidence"], "caller_supplied_not_naturally_certified")


if __name__ == "__main__":
    unittest.main()
