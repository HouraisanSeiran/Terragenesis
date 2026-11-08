"""Focused topology, conservative propagation and hostile archive regressions."""

from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import terrain_pipeline.runoff as routing


def inputs_fixture():
    return {"height_m": np.array([[8., 7., 6.], [7., 5., 4.], [6., 4., 3.]]),
            "receiver": np.array([[4, 4, 5], [4, 5, 8], [7, 8, -1]], dtype=np.int64),
            "flowline_mask": np.array([[False, False, False], [False, True, True], [False, True, True]]),
            "outlet_mask": np.array([[False, False, False], [False, False, False], [False, False, True]]),
            "cell_owner": np.array([[0, 0, 0], [0, 0, 1], [1, 1, 1]], dtype=np.int64),
            "area_m2": np.array([4500., 3600.]),
            "local_q_m3_s": np.column_stack((np.r_[np.ones(4) * 2, np.zeros(36)], np.r_[np.ones(4), np.zeros(36)]))}


def routed(inputs=None, dt=30.):
    return routing.route_local_discharge(inputs or inputs_fixture(), dt_s=dt, spacing_m=30., source_binding={"source": "test"})


def archive_unchecked(path, result):
    manifest = {"metadata": result["metadata"], "hashes": {key: routing._hash(result[key]) for key in routing.MOUNTAIN_ROUTING_ARRAY_KEYS}}
    np.savez_compressed(path, manifest=np.frombuffer(json.dumps(manifest).encode(), dtype=np.uint8),
                        **{key: result[key] for key in routing.MOUNTAIN_ROUTING_ARRAY_KEYS})


class MountainRunoffRoutingTests(unittest.TestCase):
    def test_all_land_first_downstream_and_terminal(self):
        result = routed()
        self.assertEqual(len(result["tau_s"]), 3)
        owners = result["cell_reach"].ravel()
        river = result["river_reach"].ravel()
        self.assertEqual(owners[0], river[4])
        self.assertEqual(owners[2], river[5])
        self.assertEqual(owners[6], river[7])
        terminal = river[8]
        self.assertEqual(result["reach_length_m"][terminal], 0.)
        self.assertEqual(result["tau_s"][terminal], 30.)
        np.testing.assert_array_equal(result["allocation_counts"].sum(axis=0), [5, 4])
        np.testing.assert_allclose(result["reach_length_m"][river[4]], 60.)

    def test_conservative_delayed_positive_tail(self):
        result = routed()
        local = result["local_q_m3_s"].sum(axis=1)
        outlet = result["outlet_q_m3_s"]
        self.assertLess(outlet.max(), local.max())
        self.assertGreater(outlet.argmax(), local.argmax())
        self.assertGreater(outlet[-1], 0.)
        self.assertGreater(result["storage_m3"][-1].sum(), 0.)
        self.assertAlmostEqual(local.sum() * 30., outlet.sum() * 30. + result["storage_m3"][-1].sum(), places=10)
        self.assertLess(routing.validate_routing_result(result)["max_reach_residual_m3"], 1e-10)

    def test_cold_load_no_assembly_or_solving(self):
        result = routed()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routing.npz"
            routing.save_routing_npz(path, result)
            with patch.object(routing, "build_reaches", side_effect=AssertionError("assembly")), \
                 patch.object(routing, "route_local_discharge", side_effect=AssertionError("solve")):
                loaded = routing.load_routing_npz(path, trusted_inputs=inputs_fixture(), source_binding={"source": "test"})
            for key in routing.MOUNTAIN_ROUTING_ARRAY_KEYS:
                np.testing.assert_array_equal(loaded[key], result[key])

    def test_static_rejects_wrong_first_downstream_even_recounted(self):
        result = routed()
        result["cell_reach"][0, 0] = result["river_reach"][2, 2]
        result["allocation_counts"] = np.bincount(result["cell_reach"].ravel() * 2 + result["cell_owner"].ravel(), minlength=6).reshape(3, 2)
        with self.assertRaisesRegex(ValueError, "mapping"):
            routing.validate_routing_result(result)

    def test_coherent_split_merge_rejected(self):
        original = routed()
        split = copy.deepcopy(original)
        split["river_reach"][1, 2] = split["river_reach"][2, 1]
        split["cell_reach"][1, 2] = split["river_reach"][2, 1]
        merge = copy.deepcopy(original)
        merge["river_reach"][2, 1] = merge["river_reach"][1, 1]
        for result in (split, merge):
            with self.assertRaises(ValueError):
                routing.validate_routing_result(result)

    def test_conservative_dynamics_forgery_rejected_after_rehash(self):
        result = routed()
        result["outflow_volume_m3"][0, 0] += .1
        result["storage_m3"][1, 0] -= .1
        result["storage_change_m3"] = np.diff(result["storage_m3"], axis=0)
        result["balance_residual_m3"] = (result["lateral_volume_m3"] + result["upstream_volume_m3"]
            - result["outflow_volume_m3"] - result["storage_change_m3"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forge.npz"
            archive_unchecked(path, result)
            with self.assertRaises(ValueError):
                routing.load_routing_npz(path, trusted_inputs=inputs_fixture(), source_binding={"source": "test"})

    def test_coherent_source_forgery_needs_external_identity(self):
        forged_inputs = inputs_fixture()
        forged_inputs["local_q_m3_s"] *= 2
        result = routed(forged_inputs)
        with self.assertRaisesRegex(ValueError, "external input"):
            routing.validate_routing_result(result, trusted_inputs=inputs_fixture(), source_binding={"source": "test"})

    def test_header_shape_rejected_before_numpy_load(self):
        result = routed()
        result["upstream_volume_m3"] = np.zeros((40, 4))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.npz"
            archive_unchecked(path, result)
            with patch.object(np, "load", side_effect=AssertionError("allocated before header validation")):
                with self.assertRaisesRegex(ValueError, "header shape"):
                    routing.load_routing_npz(path, trusted_inputs=inputs_fixture(), source_binding={"source": "test"})

    def test_resource_check_before_build(self):
        inputs = inputs_fixture()
        inputs["local_q_m3_s"] = np.zeros((3001, 2))
        with patch.object(routing, "build_reaches", side_effect=AssertionError("mapping before preflight")):
            with self.assertRaisesRegex(ValueError, "resource"):
                routed(inputs)
        routing.preflight(2688, 237169, 64, 29)
        with self.assertRaises(ValueError):
            routing.preflight(2688, 237169, 256, 2048)

    def test_cycles_not_closed_bad_area_nonfinite(self):
        for kind in ("cycle", "closure", "area", "nan"):
            inputs = inputs_fixture()
            if kind == "cycle":
                inputs["receiver"][1, 1] = 0
            elif kind == "closure":
                inputs["flowline_mask"][1, 2] = False
            elif kind == "area":
                inputs["area_m2"][0] += 1
            else:
                inputs["local_q_m3_s"][0, 0] = np.nan
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                routed(inputs)

    def test_no_clobber_race_and_invalid_no_artifact(self):
        result = routed()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "race.npz"
            def publish():
                try:
                    routing.save_routing_npz(path, result)
                    return True
                except FileExistsError:
                    return False
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(lambda unused: publish(), range(2)))
            self.assertEqual(sum(outcomes), 1)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            bad = copy.deepcopy(result)
            bad["storage_m3"][0, 0] = 1
            with self.assertRaises(ValueError):
                routing.save_routing_npz(Path(directory) / "invalid.npz", bad)
            self.assertFalse((Path(directory) / "invalid.npz").exists())

    def test_constant_interval_split_sensitivity(self):
        coarse = routed()
        inputs = inputs_fixture()
        inputs["local_q_m3_s"] = np.repeat(inputs["local_q_m3_s"], 2, axis=0)
        fine = routed(inputs, dt=15.)
        self.assertAlmostEqual(coarse["local_q_m3_s"].sum() * 30, fine["local_q_m3_s"].sum() * 15)
        self.assertGreater(np.max(np.abs(fine["outlet_q_m3_s"].reshape(40, 2).mean(axis=1) - coarse["outlet_q_m3_s"])), 0)


if __name__ == "__main__":
    unittest.main()
