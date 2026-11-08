from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from tests.test_surface_lake_network import joint_case
from terrain_pipeline.channel_geometry import ChannelRecipe, plan_channel
from terrain_pipeline.lake import LakeRiverSeam as LakeRiverSeam
from terrain_pipeline.lake import evaluate_surface_lake_network as evaluate_surface_lake_network
from terrain_pipeline.lake import surface_lake_network_hash as surface_lake_network_hash
from terrain_pipeline.lake import ConnectorCorridor as ConnectorCorridor
from terrain_pipeline.lake import ConnectorRecipe as ConnectorRecipe
from terrain_pipeline.lake import evaluate_lake_river_connector as evaluate_lake_river_connector
from terrain_pipeline.lake import lake_river_connector_hash as lake_river_connector_hash
from terrain_pipeline.lake import load_lake_river_connector as load_lake_river_connector
from terrain_pipeline.lake import query_lake_river_connector as query_lake_river_connector
from terrain_pipeline.lake import save_lake_river_connector as save_lake_river_connector
from terrain_pipeline.lake import validate_lake_river_connector as validate_lake_river_connector
from terrain_pipeline.lake import replay_lake_river_connector as replay_lake_river_connector


def common_source_case(inflows=(2., 2.), width=.04, initial_stage=10., original_local=.01):
    case = joint_case(inflows=inflows, initial_stage=initial_stage, original_local=original_local)
    lake = case["lake_inputs"]
    lake["height_m"][2:7, 6] = (14., 9., 8.9, 8.8, 8.7)
    identity = "connector-independent-common-source-v1"
    lake["source_identity"] = identity
    original = case["plan"]
    arrays = original["arrays"]
    source = arrays["source_height_m"].copy()
    source[:5, :4] = lake["height_m"][2:7, 3:7]
    parameters = original["identity"]["parameters"]
    channel = ChannelRecipe(**{name: parameters[name] for name in ChannelRecipe.__dataclass_fields__})
    case["plan"] = plan_channel(source, arrays["receiver"], arrays["order"], arrays["outlet_mask"],
        arrays["discharge_m3_s"], 1., 1., -3., 0., 0., identity, channel)
    case["seam"] = LakeRiverSeam((3, 6), 0., 1., "synthetic-local-m", identity, identity)
    joint = evaluate_surface_lake_network(**case)
    assert joint["transfer_feasible"], joint["diagnostic"]
    rows, columns = np.indices((11, 121))
    world_x = -2.3 + columns * .02
    world_z = .9 + rows * .02
    column = world_x + 3.
    row = world_z
    left = np.floor(column).astype(int)
    top = np.floor(row).astype(int)
    dx, dz = column - left, row - top
    height = (source[top, left] * (1 - dx) * (1 - dz)
              + source[top, left + 1] * dx * (1 - dz)
              + source[top + 1, left] * (1 - dx) * dz
              + source[top + 1, left + 1] * dx * dz)
    corridor = ConnectorCorridor(height, np.ones(height.shape, bool), np.ones(height.shape, bool),
        np.zeros(height.shape, bool), -2.3, .9, .02, .02, "synthetic-local-m", identity)
    recipe = ConnectorRecipe(((-2.2, 1.), (-1., 1.), (0., 1.)), (width,) * 3, 1)
    return joint, corridor, recipe


def mutable(value):
    from collections.abc import Mapping
    if isinstance(value, Mapping):
        return {name: mutable(child) for name, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [mutable(child) for child in value]
    if isinstance(value, np.ndarray):
        return value.copy()
    return value


def expanded_corridor(joint):
    source = joint["inputs"]["plan"]["arrays"]["source_height_m"]
    rows, columns = np.indices((31, 121))
    column, row = .7 + columns * .02, .7 + rows * .02
    left, top = np.floor(column).astype(int), np.floor(row).astype(int)
    dx, dz = column - left, row - top
    height = (source[top, left] * (1 - dx) * (1 - dz) + source[top, left + 1] * dx * (1 - dz)
              + source[top + 1, left] * (1 - dx) * dz + source[top + 1, left + 1] * dx * dz)
    return ConnectorCorridor(height, np.ones(height.shape, bool), np.ones(height.shape, bool),
        np.zeros(height.shape, bool), -2.3, .7, .02, .02, "synthetic-local-m", "connector-independent-common-source-v1")


class LakeRiverConnectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.joint, cls.corridor, cls.recipe = common_source_case()
        cls.result = evaluate_lake_river_connector(cls.joint, cls.corridor, cls.recipe)

    def test_positive_full_water_geometry_and_actual_per_step_binding(self):
        result = self.result
        self.assertTrue(result["geometry_feasible"], result["diagnostic"])
        self.assertEqual(result["summary"]["connected_steps"], 2)
        self.assertFalse(result["summary"]["source_joint_publishable"])
        terminal_beds = []
        for row, source_step in zip(result["steps"], self.joint["trace"]):
            geometry = row["geometry"]
            self.assertEqual(row["actual_outflow_m3_s"], source_step["lake_outflow_m3_s"])
            self.assertEqual(row["added_injection_m3_s"], 0.)
            self.assertEqual(geometry["station_bed_m"][0], 8.)
            self.assertEqual(geometry["station_water_m"][0], self.joint["committed_lake_arrays"]["stage_m"][row["index"] + 1])
            river = source_step["recovery"]["surface"]["arrays"]
            self.assertEqual(geometry["station_bed_m"][-1], river["final_surface_m"][10, 30])
            self.assertEqual(geometry["station_water_m"][-1], river["water_surface_m"][10, 30])
            self.assertGreater(len(geometry["triangles"]), 0)
            self.assertGreater(geometry["audit"]["wet_area_m2"], .079)
            self.assertGreater(np.diff(geometry["station_bed_m"][:geometry["spill_station"] + 1]).max(), 0)
            self.assertTrue(np.all(np.diff(geometry["station_bed_m"][geometry["spill_station"]:]) <= 1e-9))
            terminal_beds.append(geometry["station_bed_m"][-1])
        self.assertNotEqual(terminal_beds[0], terminal_beds[1])

    def test_hard_readonly_and_query_never_recalculates(self):
        result = self.result
        with self.assertRaises(TypeError):
            result["summary"]["connected_steps"] = 0
        with self.assertRaises(ValueError):
            result["steps"][0]["geometry"]["bed_vertices_m"].flags.writeable = True
        with self.assertRaises(ValueError):
            result["source_joint"]["inputs"]["lake_inputs"]["height_m"].flags.writeable = True
        with patch('terrain_pipeline.lake.evaluate_lake_river_connector', side_effect=AssertionError), patch(
                'terrain_pipeline.lake.validate_surface_lake_network', side_effect=AssertionError):
            self.assertIs(query_lake_river_connector(result, 0), result["steps"][0])

    def test_masks_and_unknown_cover_off_center_triangles(self):
        for name, value, code in (("valid_mask", False, "unknown_support"),
                                  ("domain_mask", False, "domain_support"),
                                  ("protected_mask", True, "protected_support")):
            mask = getattr(self.corridor, name).copy()
            mask[6, 75] = value
            corridor = replace(self.corridor, **{name: mask})
            result = evaluate_lake_river_connector(self.joint, corridor, self.recipe)
            self.assertFalse(result["geometry_feasible"])
            self.assertEqual(result["diagnostic"]["code"], code)

    def test_budget_and_resolution_never_relax(self):
        for changes, code in ((dict(max_cut_m=.01), "cut_depth_budget"),
                              (dict(max_cut_volume_m3=0.), "cut_volume_budget"),
                              (dict(max_changed_area_m2=0.), "changed_area_budget"),
                              (dict(width_m=(.02,) * 3), "width_resolution_failed"),
                              (dict(max_station_spacing_m=.1), "longitudinal_resolution_failed"),
                              (dict(max_stations=3), "station_resource_exhausted"),
                              (dict(max_triangles=2), "triangle_resource_exhausted"),
                              (dict(max_support_tests=1), "support_resource_exhausted")):
            result = evaluate_lake_river_connector(self.joint, self.corridor, replace(self.recipe, **changes))
            self.assertFalse(result["geometry_feasible"], changes)
            self.assertEqual(result["diagnostic"]["code"], code)

    def test_crossing_path_rejected(self):
        recipe = replace(self.recipe, path_xz_m=((-2., 1.), (-1., 1.), (-.5, 1.04), (-.5, .96), (-.9, 1.02), (0., 1.)),
                         width_m=(.04,) * 6)
        result = evaluate_lake_river_connector(self.joint, self.corridor, recipe)
        self.assertEqual(result["diagnostic"]["code"], "path_selfintersection")

    def test_unchanged_legacy_fixture_cannot_fake_source_splice(self):
        legacy = evaluate_surface_lake_network(**joint_case(inflows=(6.,)))
        result = evaluate_lake_river_connector(legacy, self.corridor, self.recipe)
        self.assertFalse(result["geometry_feasible"])

    def test_illegal_and_incomplete_inputs_early_rejected(self):
        for changes in (dict(origin_x_m=float("nan")), dict(spacing_x_m=0.),
                        dict(vertical_datum=""), dict(valid_mask=np.ones((2, 2)))):
            with self.assertRaises(ValueError):
                replace(self.corridor, **changes)
        with self.assertRaises(ValueError):
            evaluate_lake_river_connector(self.joint, self.corridor, replace(self.recipe, path_xz_m=((-2., 1.), (-1.1, 1.), (0., 1.))))
        with self.assertRaises(ValueError):
            evaluate_lake_river_connector(self.joint, replace(self.corridor, vertical_datum="other"), self.recipe)
        broken = mutable(self.joint)
        broken["trace"][0]["lake_outflow_m3_s"] += .1
        broken["identity_sha256"] = surface_lake_network_hash(broken)
        with self.assertRaises(ValueError):
            evaluate_lake_river_connector(broken, self.corridor, self.recipe)

    def test_rehashed_geometry_summary_and_q_tampering_rejected(self):
        if not self.result["geometry_feasible"]:
            self.fail(str(self.result["diagnostic"]))
        for field in ("geometry", "summary", "q"):
            altered = mutable(self.result)
            if field == "geometry":
                altered["steps"][0]["geometry"]["bed_vertices_m"][5] -= .01
            elif field == "summary":
                altered["summary"]["connected_steps"] = 99
            else:
                altered["steps"][0]["actual_outflow_m3_s"] += .1
            altered["identity_sha256"] = lake_river_connector_hash(altered)
            with self.assertRaises(ValueError):
                validate_lake_river_connector(altered)

    def test_atomic_save_load_race_and_standalone(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "connector.npz"
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(save_lake_river_connector, self.result, destination) for unused in range(2)]
                success = 0
                for future in futures:
                    try:
                        future.result()
                        success += 1
                    except FileExistsError:
                        pass
            self.assertEqual(success, 1)
            loaded = load_lake_river_connector(destination)
            self.assertEqual(loaded["identity_sha256"], self.result["identity_sha256"])
            self.assertEqual(list(Path(directory).iterdir()), [destination])

    def test_duplicate_zip_and_npy_header_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "bad.npz"
            with zipfile.ZipFile(destination, "w") as archive:
                archive.writestr("manifest.npy", b"bad")
                with self.assertWarns(UserWarning):
                    archive.writestr("manifest.npy", b"bad")
            with self.assertRaises(ValueError):
                load_lake_river_connector(destination)

    def test_static_load_forbids_upstream_evaluation_recovery_and_geometry_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "connector.npz"
            save_lake_river_connector(self.result, destination)
            with patch('terrain_pipeline.lake.connector_geometry', side_effect=AssertionError), patch(
                    'terrain_pipeline.lake.evaluate_lake_river_connector', side_effect=AssertionError), patch(
                    'terrain_pipeline.lake.validate_surface_lake_network', side_effect=AssertionError), patch(
                    'terrain_pipeline.lake.evaluate_surface_lake_network', side_effect=AssertionError), patch(
                    'terrain_pipeline.surface_domain.recover_surface_network', side_effect=AssertionError), patch(
                    'terrain_pipeline.surface_domain.recover_surface_network', side_effect=AssertionError):
                loaded = load_lake_river_connector(destination)
                self.assertEqual(query_lake_river_connector(loaded, 1)["status"], "connected")

    def test_exact_zero_q_is_closed_without_connector_water(self):
        joint, corridor, recipe = common_source_case((0., 0.), initial_stage=8., original_local=0.)
        result = evaluate_lake_river_connector(joint, corridor, recipe)
        self.assertTrue(result["geometry_feasible"])
        self.assertEqual(result["summary"]["closed_steps"], 2)
        self.assertTrue(all(row["geometry"] is None for row in result["steps"]))
        validate_lake_river_connector(result)

    def test_ridge_and_wider_dry_attachment_refuse_without_budget_changes(self):
        height = self.corridor.surface_m.copy()
        height[4:8, 68:72] = 12.
        result = evaluate_lake_river_connector(self.joint, replace(self.corridor, surface_m=height), self.recipe)
        self.assertEqual(result["diagnostic"]["code"], "post_spill_bed_uphill")
        corridor = expanded_corridor(self.joint)
        result = evaluate_lake_river_connector(self.joint, corridor, replace(self.recipe, width_m=(.4,) * 3))
        self.assertFalse(result["geometry_feasible"])
        self.assertEqual(result["diagnostic"]["code"], "dry_splice_support")

    def test_tailwater_contract_and_infeasible_source_rejected(self):
        from tests.test_surface_lake_network import high_tailwater_case
        source = evaluate_surface_lake_network(**high_tailwater_case())
        self.assertFalse(source["transfer_feasible"])
        with self.assertRaises(ValueError):
            evaluate_lake_river_connector(source, self.corridor, self.recipe)
        altered = mutable(self.result)
        altered["source_joint"]["trace"][0]["injection_stage_m"] = 10.
        altered["source_joint"]["identity_sha256"] = surface_lake_network_hash(altered["source_joint"])
        altered["identity_sha256"] = lake_river_connector_hash(altered)
        with self.assertRaises(ValueError):
            validate_lake_river_connector(altered)

    def test_static_source_h0_and_tolerance_rehash_refused(self):
        for field in ("h0", "tolerance", "recovery", "dt"):
            altered = mutable(self.result)
            joint = altered["source_joint"]
            if field == "h0":
                joint["inputs"]["plan"]["arrays"]["source_height_m"][0, 0] += .1
            elif field == "tolerance":
                joint["ledger"][0]["combined_tolerance_m3"] = 100.
            elif field == "recovery":
                joint["trace"][0]["recovery"]["inputs"]["budget"]["max_cut_volume_m3"] += 1.
            else:
                joint["ledger"][0]["dt_s"] = 2.
            joint["identity_sha256"] = surface_lake_network_hash(joint)
            for row in altered["steps"]:
                row["source_joint_identity"] = joint["identity_sha256"]
                row["ledger_recheck"] = mutable(joint["ledger"][row["index"]])
            altered["identity_sha256"] = lake_river_connector_hash(altered)
            with self.assertRaises(ValueError):
                validate_lake_river_connector(altered)

    def test_static_recipe_resource_and_summary_rehash_refused(self):
        for changes in (dict(max_triangles=1), dict(max_stations=1), dict(max_support_tests=1),
                        dict(max_retained_bytes=1024), dict(min_width_cells=3), dict(max_cut_m=.01)):
            altered = mutable(self.result)
            altered["inputs"]["recipe"].update(changes)
            altered["identity_sha256"] = lake_river_connector_hash(altered)
            with self.assertRaises(ValueError):
                validate_lake_river_connector(altered)
        altered = mutable(self.result)
        altered["summary"]["support_tests"] += 1
        altered["identity_sha256"] = lake_river_connector_hash(altered)
        with self.assertRaises(ValueError):
            validate_lake_river_connector(altered)

    def test_exact_positive_cut_polygon_integration(self):
        from terrain_pipeline.lake import _integral as _integral
        triangle = np.array([[0., 0.], [1., 0.], [0., 1.]])
        volume, area = _integral(triangle, triangle, np.array([-1., 1., 1.]))
        self.assertAlmostEqual(area, .375)
        self.assertAlmostEqual(volume, 5. / 24.)

    def test_input_bytes_rejected_before_source_replay(self):
        with patch('terrain_pipeline.lake.validate_surface_lake_network', side_effect=AssertionError):
            with self.assertRaises(ValueError):
                evaluate_lake_river_connector(self.joint, self.corridor, replace(self.recipe, max_retained_bytes=1024))

    def test_explicit_replay_is_opt_in(self):
        replay = replay_lake_river_connector(self.result)
        self.assertEqual(replay["identity_sha256"], self.result["identity_sha256"])

    def test_fixed_metadata_and_failure_prefix_rehash_refused(self):
        for field in ("status", "diagnostic", "river", "prefix", "spill", "deleted"):
            altered = mutable(self.result)
            if field == "status":
                altered["status"] = "published_full_surface_system"
            elif field == "diagnostic":
                altered["diagnostic"] = dict(code="tailwater_at_or_above_spill", failed_step=0, evidence={})
            elif field == "river":
                altered["steps"][0]["river_identity"] = "0" * 64
            elif field == "prefix":
                altered["steps"][0]["lake_prefix_identity"] = "0" * 64
            elif field == "spill":
                altered["steps"][0]["geometry"]["spill_station"] = -1
            else:
                altered["steps"] = []
                altered["geometry_feasible"] = False
                altered["summary"]["connected_steps"] = 0
                altered["diagnostic"] = dict(code="arbitrary", failed_step=0, evidence={})
            altered["identity_sha256"] = lake_river_connector_hash(altered)
            with self.assertRaises(ValueError):
                validate_lake_river_connector(altered)

    def test_source_call_inputs_and_aggregate_summary_rehash_refused(self):
        for field in ("budget", "mask", "stage", "summary"):
            altered = mutable(self.result)
            source = altered["source_joint"]
            if field == "budget":
                source["inputs"]["budget"]["max_cut_volume_m3"] = 0.
            elif field == "mask":
                source["inputs"]["coarse_protected"][1, 1] = True
            elif field == "stage":
                source["inputs"]["outlet_stage_m"][0] += 1.
            else:
                source["summary"]["total_lake_outflow_m3"] = 10000.
            source["identity_sha256"] = surface_lake_network_hash(source)
            for row in altered["steps"]:
                row["source_joint_identity"] = source["identity_sha256"]
            altered["identity_sha256"] = lake_river_connector_hash(altered)
            with self.assertRaises(ValueError):
                validate_lake_river_connector(altered)

    def test_oversized_npy_header_before_allocation(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "header.npz"
            header = io.BytesIO()
            np.lib.format.write_array_header_1_0(header, dict(descr="<f8", fortran_order=False, shape=(999999999,)))
            with zipfile.ZipFile(destination, "w") as archive:
                archive.writestr("manifest.npy", header.getvalue())
            with self.assertRaises(ValueError):
                load_lake_river_connector(destination)


if __name__ == "__main__":
    unittest.main()
