from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_boundary_coupling import (
    BoundarySeries, CoupledForcing, solve_coupled,
)
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelNetwork
from terrain_pipeline.surface_rivers.metric_coupled_product import (
    load_coupled_product, make_coupled_product, validate_coupled_product,
    save_coupled_product,
)
from terrain_pipeline.lake import LakeStorage as LakeStorage


def closed_network(*, count=1, bed=0., length=10., width=2., depth=10.):
    return ChannelNetwork(
        np.full(count, -1, np.int64), np.full(count, length),
        np.full(count, width), np.full(count, bed), np.zeros(count),
        np.full(count, .05), np.full(count, depth),
        np.full(count, "closed_wall", dtype="U24"),
        "a" * 64, "review rectangular", "review Manning",
    )


def empty_boundaries(times, *, stage=None, conductance=0.):
    if stage is None:
        return BoundarySeries(
            np.empty(0, np.int64), np.empty(0, dtype="U24"),
            np.empty(0, bool), times, np.empty((len(times) - 1, 0)),
            np.empty((len(times) - 1, 0)), np.empty(0), "c" * 64,
        )
    return BoundarySeries(
        np.array([0], np.int64), np.array(["prescribed_stage"]),
        np.array([False]), times, np.full((len(times) - 1, 1), stage),
        np.zeros((len(times) - 1, 1)), np.array([conductance]), "c" * 64,
    )


def forcing(times, channel_count, *, lake_q=0., lake_count=0):
    return CoupledForcing(times, np.zeros((len(times) - 1, channel_count)),
                          np.full((len(times) - 1, lake_count), lake_q), "d" * 64)


def rehash(product):
    product["identity_sha256"] = identity(product["arrays"], product["metadata"])
    return product


class CoupledColdReviewTests(unittest.TestCase):
    def test_nested_certification_claim_is_rejected_even_after_rehash(self):
        times = np.array([0., 1.])
        network = closed_network()
        boundaries = empty_boundaries(times)
        local = forcing(times, 1)
        mapping = np.array([-1], np.int64)
        result = solve_coupled(network, (), (), mapping, local, boundaries)
        product = make_coupled_product(network, (), (), mapping, local, boundaries, result)
        forged = deepcopy(product)
        forged["metadata"]["result"]["hydraulic_ready"] = True
        with self.assertRaisesRegex(ValueError, "result|scope|unsupported"):
            validate_coupled_product(rehash(forged))

    def test_large_absolute_datum_cannot_hide_forged_depth(self):
        times = np.array([0., 1.])
        network = closed_network(bed=1e9)
        boundaries = empty_boundaries(times)
        local = forcing(times, 1)
        mapping = np.array([-1], np.int64)
        result = solve_coupled(network, (), (), mapping, local, boundaries,
                               initial_channel_volume_m3=np.array([10.]))
        product = make_coupled_product(network, (), (), mapping, local, boundaries, result)
        forged = deepcopy(product)
        forged["arrays"]["trace_channel_stage_m"] = (
            forged["arrays"]["trace_channel_stage_m"].copy() + .05)
        with self.assertRaisesRegex(ValueError, "stage"):
            validate_coupled_product(rehash(forged))

    def test_finite_node_storage_with_infinite_total_is_rejected(self):
        times = np.array([0., 1.])
        network = closed_network(count=2, length=1e100, width=1e100, depth=1e108)
        boundaries = empty_boundaries(times)
        local = forcing(times, 2)
        mapping = np.array([-1, -1], np.int64)
        result = solve_coupled(network, (), (), mapping, local, boundaries,
                               initial_channel_volume_m3=np.array([1e307, 1e307]))
        product = make_coupled_product(network, (), (), mapping, local, boundaries, result)
        forged = deepcopy(product)
        forged["arrays"]["trace_channel_volume_m3"] = np.full((2, 2), 1e308)
        forged["arrays"]["trace_channel_stage_m"] = np.full((2, 2), 1e108)
        with np.errstate(over="ignore"):
            self.assertTrue(np.isinf(np.sum(forged["arrays"]["trace_channel_volume_m3"][0])))
        with np.errstate(over="ignore", invalid="ignore"):
            with self.assertRaisesRegex(ValueError, "budget|total|finite"):
                validate_coupled_product(rehash(forged))

    def test_zero_and_nonzero_failure_prefixes_survive_cold_roundtrip(self):
        times = np.array([0., 4.])
        network = closed_network()
        boundaries = empty_boundaries(times)
        mapping = np.array([-1], np.int64)
        lake = LakeStorage(np.array([0], np.int64), np.array([0.]),
                           np.array([10.]), 0, 1., "b" * 64,
                           "review finite lake")
        for initial_lake, expected_steps in ((9., 0), (0., 2)):
            with self.subTest(initial_lake=initial_lake):
                local = forcing(times, 1, lake_q=4., lake_count=1)
                result = solve_coupled(
                    network, (lake,), (), mapping, local, boundaries,
                    initial_lake_volume_m3=np.array([initial_lake]),
                    config=ChannelConfig(max_dt_seconds=1.),
                )
                self.assertEqual(result["metadata"]["status"], "failed_prefix")
                self.assertEqual(len(result["arrays"]["time_seconds"]) - 1,
                                 expected_steps)
                product = make_coupled_product(network, (lake,), (), mapping,
                                               local, boundaries, result)
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "coupled.npz"
                    save_coupled_product(path, product)
                    loaded = load_coupled_product(
                        path, expected_sha256=file_sha256(path),
                        expected_identity=product["identity_sha256"],
                    )
                self.assertEqual(loaded["metadata"]["result"]["failure_reason"],
                                 result["metadata"]["failure_reason"])
                np.testing.assert_array_equal(
                    loaded["arrays"]["trace_time_seconds"],
                    result["arrays"]["time_seconds"],
                )

    def test_nonfinite_boundary_flux_failure_has_cold_witness(self):
        times = np.array([0., 1.])
        network = closed_network()
        boundaries = empty_boundaries(times, stage=-2., conductance=1e308)
        local = forcing(times, 1)
        mapping = np.array([-1], np.int64)
        with np.errstate(over="ignore", invalid="ignore"):
            result = solve_coupled(network, (), (), mapping, local, boundaries,
                                   initial_channel_volume_m3=np.array([1.]))
            self.assertEqual(result["metadata"]["status"], "failed_prefix")
            product = make_coupled_product(network, (), (), mapping,
                                           local, boundaries, result)
        self.assertTrue(validate_coupled_product(product))

    def test_nonfinite_aggregate_candidate_failure_has_cold_witness(self):
        times = np.array([0., 1.])
        network = closed_network(count=2, length=1e100, width=1e100,
                                 depth=1e108)
        boundaries = empty_boundaries(times)
        local = CoupledForcing(times, np.full((1, 2), 1e308),
                               np.empty((1, 0)), "d" * 64)
        mapping = np.array([-1, -1], np.int64)
        with np.errstate(over="ignore", invalid="ignore"):
            result = solve_coupled(network, (), (), mapping, local, boundaries)
            self.assertEqual(result["metadata"]["failure_reason"],
                             "nonfinite water ledger")
            product = make_coupled_product(network, (), (), mapping,
                                           local, boundaries, result)
        self.assertTrue(validate_coupled_product(product))


if __name__ == "__main__":
    unittest.main()
