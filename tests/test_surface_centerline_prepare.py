from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import io
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
import warnings
import zipfile
from pathlib import Path

import numpy as np
from numpy.lib import format as npy_format

from terrain_pipeline.channel_centerline import SmoothingRecipe, build_centerline
from terrain_pipeline.channel_inundation import InundationRecipe
from terrain_pipeline.channel_stage import StageRecipe
from terrain_pipeline.local_channel_sections import SectionRecipe, evaluate_sections
from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel
from terrain_pipeline.surface_centerline_prepare import (
    load_surface_centerline, prepare_surface_centerline, save_surface_centerline,
    slice_surface_centerline)
from terrain_pipeline.surface_network_prepare import SurfaceNetworkBudget
from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest
from terrain_pipeline import surface_centerline_prepare as preparation


def bent_plan():
    height = np.full((7, 7), 10.)
    height[1:6, 2:5] = 5. + np.arange(5, 0, -1)[:, None] * .1
    height[6, 3] = 4.
    receiver = np.full(49, -1, np.int64)
    outlet = np.ones((7, 7), bool)
    for donor, target in ((9, 17), (11, 17), (17, 25), (25, 31), (31, 38), (38, 45)):
        receiver[donor] = target
        outlet.flat[donor] = False
    order = np.array([cell for cell in range(49) if outlet.flat[cell]] +
                     [38, 31, 25, 17, 9, 11], dtype=np.int64)
    discharge = np.full((7, 7), .01)
    discharge.flat[[9, 11, 17, 25, 31, 38, 45]] = .2
    discharge.flat[[9, 11]] = .1
    recipe = ChannelRecipe(reference_discharge_m3_s=.1, reference_width_m=8.,
                           min_width_m=8., max_width_m=8., reference_depth_m=.5,
                           min_depth_m=.5, max_depth_m=.5, max_cut_m=4.,
                           min_bed_slope_m_per_m=.00001)
    return plan_channel(height, receiver, order, outlet, discharge, 10., 10.,
                        0., 0., 0., "bent-confluence", recipe)


def prepare_case(plan=None, centerline=None, budget=None, domain=None, protected=None, legal=None,
                 spacing=1.):
    plan = bent_plan() if plan is None else plan
    centerline = build_centerline(plan, SmoothingRecipe(max_offset_m=10.)) if centerline is None else centerline
    shape = (int(60 / spacing) + 1,) * 2
    domain = np.ones(shape, bool) if domain is None else domain
    protected = np.zeros(shape, bool) if protected is None else protected
    if legal is None:
        legal = np.zeros(shape, bool)
        legal[-1, int(27 / spacing):int(33 / spacing) + 1] = True
    budget = SurfaceNetworkBudget(4., 5000., 5000.) if budget is None else budget
    return prepare_surface_centerline(plan, centerline, 0., 0., spacing, spacing, shape,
                                      domain, protected, legal, np.array([5.2]),
                                      SectionRecipe(), StageRecipe(max_depth_m=4.,
                                      max_lift_above_nominal_m=3.),
                                      InundationRecipe(max_lateral_reach_m=15.), budget)


def rehash_result(result):
    record = result["identity"]
    record["parameters"]["arrays_sha256"] = digest({
        name: array_hash(value) for name, value in result["arrays"].items()})
    record["parameters"]["summary_sha256"] = digest(result["summary"])
    record["parameters"]["component_sha256"] = {
        name: value["identity_sha256"] for name, value in result["components"].items()}
    identity = ArtifactIdentity(**record)
    result.update(identity=identity.record(), identity_sha256=identity.sha256)


def write_package(result, path):
    manifest = {key: result[key] for key in ("identity", "identity_sha256", "status", "components", "summary")}
    manifest["format_version"] = 1
    np.savez_compressed(path, manifest=json.dumps(manifest, sort_keys=True), **result["arrays"])


def replace_member(source, destination, name, contents, duplicate=False):
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as rewritten:
        for member in original.infolist():
            rewritten.writestr(member.filename, contents if member.filename == name else original.read(member))
        if duplicate:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                rewritten.writestr(name, contents)


class SurfaceCenterlinePrepareTests(unittest.TestCase):
    def test_active_flow_conserves_at_confluence(self):
        arrays = bent_plan()["arrays"]
        discharge = arrays["discharge_m3_s"].ravel()
        self.assertEqual(discharge[9], .1)
        self.assertEqual(discharge[11], .1)
        for target in (17, 25, 31, 38, 45):
            donors = np.flatnonzero(arrays["receiver"] == target)
            self.assertAlmostEqual(float(np.sum(discharge[donors])), discharge[target])

    def test_arrays_are_hard_readonly(self):
        result = prepare_case()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.npz"
            save_surface_centerline(result, path)
            for surface in (result, load_surface_centerline(path)):
                window = slice_surface_centerline(surface, slice(0, 30), slice(0, 30))
                for array in (*surface["arrays"].values(), *window["arrays"].values()):
                    with self.assertRaises(ValueError):
                        array.setflags(write=True)
                    ancestor = array.base
                    while isinstance(ancestor, np.ndarray):
                        with self.assertRaises(ValueError):
                            ancestor.setflags(write=True)
                        ancestor = ancestor.base

    def test_exact_sample_ignores_zero_weight_unknown(self):
        from terrain_pipeline.surface_centerline_prepare import _sample
        field = np.array([[5., np.nan], [np.nan, np.nan]])
        value, valid = _sample(field, 0., 0., 0., 0., 1., 1.)
        self.assertTrue(valid)
        self.assertEqual(value, 5.)

    def test_bent_confluence_replays_and_changes_actual_cut(self):
        plan = bent_plan()
        centerline = build_centerline(plan, SmoothingRecipe(max_offset_m=10.))
        self.assertGreater(centerline["summary"]["moved_nodes"], 0)
        geometry = centerline["arrays"]
        np.testing.assert_array_equal(geometry["node_world_xz_m"][geometry["anchor_mask"]],
                                      geometry["original_world_xz_m"][geometry["anchor_mask"]])
        result = prepare_case(plan, centerline)
        self.assertEqual(result["status"], "prepared", result["summary"])
        legacy = evaluate_sections(plan, 0., 0., 1., 1., (61, 61),
                                   np.zeros((61, 61), bool), SectionRecipe())
        moved = result["arrays"]["section__actual_cut_m"]
        self.assertFalse(np.array_equal(moved, legacy["arrays"]["actual_cut_m"]))
        self.assertEqual(result["summary"]["max_stage_bed_error_m"], 0.)
        self.assertGreater(result["summary"]["max_edge_bed_error_m"], 0.)
        self.assertTrue(preparation._outlet_connected(result["arrays"]["flood__wet_mask"],
                                                      result["arrays"]["legal_outlet_mask"]))
        weights = np.ones((61, 61))
        weights[[0, -1], :] *= .5
        weights[:, [0, -1]] *= .5
        self.assertAlmostEqual(float(np.sum(moved * weights)), result["summary"]["cut_volume_m3"])
        self.assertEqual(float(np.sum((moved > 1e-9) * weights)), result["summary"]["area_m2"])
        np.testing.assert_array_equal(plan["arrays"]["source_height_m"], bent_plan()["arrays"]["source_height_m"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prepared.npz"
            save_surface_centerline(result, path)
            loaded = load_surface_centerline(path)
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
            with self.assertRaises(FileExistsError):
                save_surface_centerline(result, path)
            first = slice_surface_centerline(loaded, slice(0, 40), slice(0, 40))
            second = slice_surface_centerline(loaded, slice(20, 61), slice(20, 61))
            for name in first["arrays"]:
                np.testing.assert_array_equal(first["arrays"][name][20:40, 20:40],
                                              second["arrays"][name][:20, :20])
                self.assertFalse(first["arrays"][name].flags.writeable)

    def test_budget_and_masks_fail(self):
        self.assertTrue(prepare_case(budget=SurfaceNetworkBudget(4., 1., 1.))["summary"]["budget_failures"]["area"])
        domain = np.ones((61, 61), bool)
        domain[20, 30] = False
        self.assertEqual(prepare_case(domain=domain)["status"], "diagnostic_not_publishable")
        protected = np.zeros((61, 61), bool)
        protected[20, 30] = True
        self.assertEqual(prepare_case(protected=protected)["status"], "diagnostic_not_publishable")
        legal = np.zeros((61, 61), bool)
        self.assertEqual(prepare_case(legal=legal)["status"], "diagnostic_not_publishable")

    def test_nonconservative_discharge_is_rejected_before_sections(self):
        plan = bent_plan()
        params = plan["identity"]["parameters"]
        discharge = plan["arrays"]["discharge_m3_s"].copy()
        discharge.flat[[9, 11]] = .2
        recipe = ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__})
        plan = plan_channel(plan["arrays"]["source_height_m"], plan["arrays"]["receiver"],
                            plan["arrays"]["order"], plan["arrays"]["outlet_mask"], discharge,
                            10., 10., 0., 0., 0., "nonconservative", recipe)
        centerline = build_centerline(plan, SmoothingRecipe(max_offset_m=10.))
        with patch.object(preparation, "evaluate_sections") as sections:
            with self.assertRaisesRegex(ValueError, "discharge conservation"):
                prepare_case(plan, centerline)
            sections.assert_not_called()

    def test_all_donors_including_inactive_are_counted(self):
        plan = bent_plan()
        params = plan["identity"]["parameters"]
        receiver = plan["arrays"]["receiver"].copy()
        receiver[10] = 17
        outlet = plan["arrays"]["outlet_mask"].copy()
        outlet.flat[10] = False
        order = np.array([cell for cell in range(49) if outlet.flat[cell]] +
                         [38, 31, 25, 17, 9, 11, 10], dtype=np.int64)
        recipe = ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__})
        plan = plan_channel(plan["arrays"]["source_height_m"], receiver, order, outlet,
                            plan["arrays"]["discharge_m3_s"], 10., 10., 0., 0., 0., "inactive-donor", recipe)
        with self.assertRaisesRegex(ValueError, "discharge conservation"):
            prepare_case(plan)

    def test_positive_local_inflow_is_allowed(self):
        plan = bent_plan()
        params = plan["identity"]["parameters"]
        discharge = plan["arrays"]["discharge_m3_s"].copy()
        discharge.flat[[17, 25, 31, 38, 45]] = .25
        recipe = ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__})
        plan = plan_channel(plan["arrays"]["source_height_m"], plan["arrays"]["receiver"],
                            plan["arrays"]["order"], plan["arrays"]["outlet_mask"], discharge,
                            10., 10., 0., 0., 0., "local-inflow", recipe)
        self.assertEqual(prepare_case(plan)["status"], "prepared")

    def test_positive_weight_support_cannot_cross_masks_unknown_or_dry(self):
        field = np.full((2, 2), 5.)
        for name in ("domain", "protected", "dry", "unknown"):
            with self.subTest(name=name):
                sampled = field.copy()
                support = np.ones((2, 2), bool)
                if name == "unknown":
                    sampled[0, 1] = np.nan
                else:
                    support[0, 1] = False
                diagnostics = {key: 0 for key in ("outside_grid", "domain", "protected", "dry", "unknown")}
                value, valid = preparation._sample(sampled, 1e-14, 0., 0., 0., 1., 1.,
                                                    (support,), diagnostics, (name,))
                self.assertFalse(valid)
                self.assertIsNone(value)
                self.assertEqual(diagnostics[name], 1)
        self.assertEqual(preparation._sample(field, -1., 0., 0., 0., 1., 1.), (None, False))

    def test_subgrid_domain_and_protection_are_diagnostic(self):
        domain = np.ones((61, 61), bool)
        domain[11, 21] = False
        protected = np.zeros((61, 61), bool)
        protected[11, 21] = True
        for reason, result in (("domain", prepare_case(domain=domain)),
                               ("protected", prepare_case(protected=protected))):
            self.assertEqual(result["status"], "diagnostic_not_publishable")
            self.assertGreater(result["summary"]["support_failures"][reason], 0)
            self.assertTrue(result["summary"]["budget_failures"]["edge_support"])

    def test_actual_water_depth_and_dry_unknown_support_gate(self):
        result = prepare_case()
        components = {group: {**metadata, "arrays": {
            name.split("__", 1)[1]: value.copy() for name, value in result["arrays"].items()
            if name.startswith(group + "__")}} for group, metadata in result["components"].items()}
        budget = SurfaceNetworkBudget(4., 5000., 5000.)
        stage_recipe = StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.)
        final = components["section"]["arrays"]["bounded_surface_m"]
        for depth, expected in ((.1, "edge_clearance"), (4.1, "edge_max_depth")):
            flood = deepcopy(components["flood"])
            wet = flood["arrays"]["wet_mask"]
            flood["arrays"]["water_surface_m"][wet] = final[wet] + depth
            failures, _ = preparation._geometry_gate(components["plan"], components["centerline"],
                components["section"], components["stage"], flood, budget, stage_recipe)
            self.assertTrue(failures[expected])
        for reason in ("dry", "unknown"):
            flood = deepcopy(components["flood"])
            if reason == "dry":
                flood["arrays"]["wet_mask"][11, 21] = False
            else:
                flood["arrays"]["water_surface_m"][11, 21] = np.nan
            failures, metrics = preparation._geometry_gate(components["plan"], components["centerline"],
                components["section"], components["stage"], flood, budget, stage_recipe)
            self.assertTrue(failures["edge_support"])
            self.assertGreater(metrics["support_failures"][reason], 0)

    def test_resolution_failure_keeps_original_tolerance_and_diagnostic_roundtrip(self):
        result = prepare_case(spacing=2.)
        self.assertEqual(result["status"], "diagnostic_not_publishable")
        self.assertTrue(result["summary"]["needs_finer_grid"])
        self.assertTrue(result["summary"]["budget_failures"]["stage_bed_mismatch"])
        self.assertEqual(result["identity"]["parameters"]["budget"]["bed_match_tolerance_m"], 1e-6)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.npz"
            with self.assertRaises(ValueError):
                save_surface_centerline(result, path)
            self.assertFalse(path.exists())
            save_surface_centerline(result, path, allow_diagnostic=True)
            with self.assertRaises(ValueError):
                load_surface_centerline(path)
            loaded = load_surface_centerline(path, allow_diagnostic=True)
            self.assertEqual(loaded["summary"], result["summary"])
            with self.assertRaises(ValueError):
                slice_surface_centerline(loaded, slice(0, 10), slice(0, 10))

    def test_plan_and_centerline_identity_status_geometry_and_summary_replay(self):
        for group, mutation in (("plan", "identity"), ("plan", "status"), ("plan", "geometry"),
                                ("centerline", "identity"), ("centerline", "status"),
                                ("centerline", "geometry"), ("centerline", "summary")):
            with self.subTest(group=group, mutation=mutation):
                plan = bent_plan()
                centerline = build_centerline(plan, SmoothingRecipe(max_offset_m=10.))
                component = deepcopy(plan if group == "plan" else centerline)
                if mutation == "identity":
                    component["identity"]["backend"] = "other-backend"
                    identity = ArtifactIdentity(**component["identity"])
                    component.update(identity=identity.record(), identity_sha256=identity.sha256)
                elif mutation == "status":
                    component["status"] = "prepared"
                elif mutation == "summary":
                    component["summary"]["moved_nodes"] = 0
                elif group == "plan":
                    component["arrays"]["bounded_bed_m"].flat[17] += .2
                else:
                    component["arrays"]["node_world_xz_m"][3, 0] += .2
                with self.assertRaises(ValueError):
                    prepare_case(component if group == "plan" else plan,
                                 component if group == "centerline" else centerline)

    def test_rehashed_package_geometry_summary_status_and_extra_fields_rejected(self):
        original = prepare_case()
        for mutation in ("bed", "wet", "summary", "status", "component-status", "component-summary",
                         "component-identity", "extra-array", "dtype"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                result = deepcopy(original)
                if mutation == "bed":
                    result["arrays"]["section__bounded_surface_m"][30, 38] += .1
                elif mutation == "wet":
                    result["arrays"]["flood__wet_mask"][11, 21] = False
                elif mutation == "summary":
                    result["summary"]["area_m2"] += 1.
                elif mutation == "status":
                    result["status"] = "diagnostic_not_publishable"
                elif mutation == "component-status":
                    result["components"]["stage"]["status"] = "prepared"
                elif mutation == "component-summary":
                    result["components"]["section"]["summary"]["actual_cut_volume_m3"] += 1.
                elif mutation == "component-identity":
                    record = result["components"]["flood"]["identity"]
                    record["backend"] = "other-backend"
                    identity = ArtifactIdentity(**record)
                    result["components"]["flood"].update(identity=identity.record(), identity_sha256=identity.sha256)
                elif mutation == "extra-array":
                    result["arrays"]["unused"] = np.zeros(1)
                else:
                    result["arrays"]["domain_mask"] = result["arrays"]["domain_mask"].astype(np.uint8)
                rehash_result(result)
                path = Path(directory) / "rehashed.npz"
                write_package(result, path)
                with self.assertRaises(ValueError):
                    load_surface_centerline(path, allow_diagnostic=True)
                with self.assertRaises(ValueError):
                    save_surface_centerline(result, Path(directory) / "saved.npz", allow_diagnostic=True)

    def test_resource_limits_precede_expensive_preparation(self):
        for constant, limit, options in (("MAX_FINE_NODES", 100, {}), ("MAX_FINE_NODES", 40, {"spacing": 10.}),
                                         ("MAX_GRAPH_NODES", 6, {}), ("MAX_EDGE_SAMPLES", 10, {})):
            with self.subTest(constant=constant, options=options):
                with patch.object(preparation, constant, limit), patch.object(preparation, "evaluate_sections") as sections:
                    with self.assertRaisesRegex(ValueError, "resource limit"):
                        prepare_case(**options)
                    sections.assert_not_called()
        for options in ({"domain": np.ones((61, 61))}, {"protected": np.zeros((2, 2), bool)},
                        {"spacing": float("inf")}, {"spacing": -1.}):
            with self.assertRaises((ValueError, OverflowError)):
                prepare_case(**options)

    def test_zip_and_npy_preflight_before_numpy_load(self):
        result = prepare_case()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.npz"
            save_surface_centerline(result, source)
            with zipfile.ZipFile(source) as archive:
                original = archive.read("domain_mask.npy")
            oversized = io.BytesIO()
            npy_format.write_array_header_1_0(oversized, {
                "descr": "<f8", "fortran_order": False, "shape": (preparation.MAX_FINE_NODES * 20 + 1,)})
            objects = io.BytesIO()
            np.save(objects, np.array([object()], dtype=object), allow_pickle=True)
            for name, contents, duplicate in (("truncated", original[:-1], False),
                                               ("extra-bytes", original + b"extra", False),
                                               ("oversized", oversized.getvalue(), False),
                                               ("object", objects.getvalue(), False),
                                               ("duplicate", original, True)):
                with self.subTest(name=name):
                    path = Path(directory) / (name + ".npz")
                    replace_member(source, path, "domain_mask.npy", contents, duplicate)
                    with patch.object(preparation.np, "load") as loader:
                        with self.assertRaises(ValueError):
                            load_surface_centerline(path)
                        loader.assert_not_called()
            for constant, limit in (("MAX_PACKAGE_BYTES", 100), ("MAX_ARCHIVE_MEMBERS", 2),
                                     ("MAX_MANIFEST_BYTES", 100)):
                with patch.object(preparation, constant, limit), patch.object(preparation.np, "load") as loader:
                    with self.assertRaises(ValueError):
                        load_surface_centerline(source)
                    loader.assert_not_called()

    def test_atomic_save_race_has_one_winner_and_no_partial_files(self):
        result = prepare_case()
        barrier = threading.Barrier(2)
        real_link = os.link
        def contested_link(source, destination):
            barrier.wait(timeout=10)
            return real_link(source, destination)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "winner.npz"
            with patch.object(preparation.os, "link", side_effect=contested_link):
                with ThreadPoolExecutor(max_workers=2) as workers:
                    futures = [workers.submit(save_surface_centerline, result, destination) for _ in range(2)]
                    successes, conflicts = 0, 0
                    for future in futures:
                        try:
                            self.assertEqual(future.result(timeout=15), destination)
                            successes += 1
                        except FileExistsError:
                            conflicts += 1
            self.assertEqual((successes, conflicts), (1, 1))
            self.assertEqual(list(Path(directory).iterdir()), [destination])
            self.assertEqual(load_surface_centerline(destination)["identity_sha256"], result["identity_sha256"])

    def test_failed_save_cleans_temporary_and_preserves_existing_target(self):
        result = prepare_case()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "result.npz"
            with patch.object(preparation.np, "savez_compressed", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    save_surface_centerline(result, destination)
            self.assertEqual(list(Path(directory).iterdir()), [])
            save_surface_centerline(result, destination)
            contents = destination.read_bytes()
            with self.assertRaises(FileExistsError):
                save_surface_centerline(result, destination)
            self.assertEqual(contents, destination.read_bytes())

    def test_slices_are_bounded_and_do_not_generate(self):
        result = prepare_case()
        with patch.object(preparation, "prepare_surface_centerline", side_effect=AssertionError("must not generate")):
            window = slice_surface_centerline(result, slice(20, 40), slice(10, 30))
        self.assertEqual((window["origin_x_m"], window["origin_z_m"]), (10., 20.))
        for selection in (slice(None, 10), slice(-1, 10), slice(1, 62), slice(1, 10, 2), slice(2, 2), 1):
            with self.assertRaises(ValueError):
                slice_surface_centerline(result, selection, slice(0, 10))


if __name__ == "__main__":
    unittest.main()
