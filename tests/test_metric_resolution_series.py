import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity, load_bundle, save_bundle
from terrain_pipeline.channel_geometry import ChannelNetwork, ChannelForcing, ChannelConfig, validate_receiver_acyclic
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.surface_rivers.metric_channel_product import make_channel_product
from terrain_pipeline.surface_rivers.metric_sediment import (
    MaterialParameters,
    SedimentConfig,
    MAX_SEDIMENT_NODES,
    _candidate,
    _next_step,
    solve_sediment,
)
from terrain_pipeline.surface_rivers.metric_resolution_exchange import (
    refine_channel,
    _sediment,
)
from terrain_pipeline.surface_rivers.metric_resolution_series import (
    run_series,
    audit_series,
    _validate_checkpoint,
)


def scenario():
    network = ChannelNetwork(
        np.array([1, -1], np.int64),
        np.full(2, 10.0),
        np.full(2, 2.0),
        np.array([100.0, 99.0]),
        np.full(2, 0.1),
        np.full(2, 0.035),
        np.full(2, 2.0),
        np.array(["interior", "open_outflow"]),
        "a" * 64,
        "declared fixture",
        "declared n",
        receiver_distance_m=np.array([10.0, 0.0]),
    )
    forcing = ChannelForcing(np.array([0.0, 10.0]), np.array([[0.1, 0.01]]), "b" * 64)
    material = MaterialParameters(
        sediment_erodibility_m_s_pa=0.0,
        rock_erodibility_m_s_pa=1e-5,
        settling_velocity_m_s=0.0,
    )
    return network, forcing, material


class ResolutionSeriesTests(unittest.TestCase):
    def test_absolute_time_rounding_never_exceeds_donor_bound(self):
        from terrain_pipeline.surface_rivers.metric_sediment import _bounded_next_time

        current = 512.3174977751091
        bound = 0.050572735835260896
        legacy = float(_bounded_next_time(current, bound, 515.0, legacy=True))
        corrected = float(_bounded_next_time(current, bound, 515.0))
        self.assertGreater(legacy - current, bound)
        self.assertLessEqual(corrected - current, bound)
        self.assertEqual(corrected, np.nextafter(legacy, current))
        np.testing.assert_array_equal(
            _bounded_next_time(
                np.array([current, 0.0]),
                np.array([bound, 0.125]),
                np.array([515.0, 0.125]),
            ),
            [corrected, 0.125],
        )
        self.assertEqual(
            float(_bounded_next_time(512.0, 0.75 * np.spacing(512.0), 515.0)), 512.0
        )

    def test_floored_step_without_progress_is_rejected_before_candidate(self):
        from tests.test_metric_sediment import domain, forcing
        from dataclasses import replace
        import terrain_pipeline.surface_rivers.metric_sediment as sediment

        d = domain(open_boundary=[True])
        f = replace(forcing(1), time_seconds=np.array([512.0, 513.0]))
        config = SedimentConfig(min_dt_seconds=1e-15)
        donor_bound = 0.75 * np.spacing(512.0)
        rates = (
            np.zeros(1),
            np.zeros(1),
            np.array([config.cfl / donor_bound]),
            np.zeros(1),
            np.zeros(1),
        )
        with patch.object(sediment, "_rates", return_value=rates), patch.object(
            sediment,
            "_candidate",
            side_effect=AssertionError("zero-duration candidate"),
        ):
            next_time, candidate, reason = _next_step(
                d,
                f,
                MaterialParameters(),
                config,
                512.0,
                np.ones(1),
                np.zeros(1),
                np.zeros(1),
                0,
                100,
            )
        self.assertIsNone(next_time)
        self.assertIsNone(candidate)
        self.assertEqual(reason, "minimum internal step or time resolution exhausted")

    def test_explicit_prefix_continuation_uses_original_checkpoint_and_pins(self):
        net, forcing, material = scenario()
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original"
            continued = Path(directory) / "continued"
            common = dict(
                source_manifest={},
                channel_config=ChannelConfig(max_dt_seconds=0.05),
                sediment_config=SedimentConfig(max_dt_seconds=0.05),
            )
            full = run_series(
                net,
                forcing,
                np.ones(2, np.int64),
                material,
                output=original,
                segment_seconds=2.0,
                **common
            )
            final_pin = full["segments"][-1]["checkpoint"]
            final = load_bundle(
                original / final_pin["path"],
                expected_sha256=final_pin["sha256"],
                validator=_validate_checkpoint,
            )
            prefix = dict(
                full,
                segments=full["segments"][:2],
                status="failed_prefix",
                last_time_seconds=4.0,
            )
            (original / "manifest.json").write_text(
                json.dumps(prefix), encoding="utf-8"
            )
            parent_sha = file_sha256(original / "manifest.json")
            new = run_series(
                net,
                forcing,
                np.ones(2, np.int64),
                material,
                output=continued,
                segment_seconds=1.0,
                reuse_complete_prefix=original / "manifest.json",
                **common
            )
            self.assertEqual(file_sha256(original / "manifest.json"), parent_sha)
            self.assertEqual(
                new["segment_endpoints_seconds"],
                [0.0, 2.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            )
            self.assertEqual(new["continuation"]["transition_time_seconds"], 4.0)
            pin = new["segments"][-1]["checkpoint"]
            actual = load_bundle(
                continued / pin["path"],
                expected_sha256=pin["sha256"],
                validator=_validate_checkpoint,
            )
            for field in final["arrays"]:
                np.testing.assert_allclose(
                    actual["arrays"][field], final["arrays"][field], rtol=0, atol=1e-10
                )
            with patch(
                "terrain_pipeline.surface_rivers.metric_resolution_series.solve_channel",
                side_effect=AssertionError("cold water"),
            ), patch(
                "terrain_pipeline.surface_rivers.metric_resolution_series.solve_sediment",
                side_effect=AssertionError("cold solid"),
            ):
                self.assertEqual(
                    audit_series(continued / "manifest.json", sample_times=(10.0,))[
                        "status"
                    ],
                    "complete",
                )
            new["continuation"]["transition_time_seconds"] = 5.0
            (continued / "manifest.json").write_text(json.dumps(new), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "prefix schedule"):
                audit_series(continued / "manifest.json", sample_times=())
            new["continuation"]["transition_time_seconds"] = 4.0
            for count in (100, True):
                new["continuation"]["complete_prefix_segments"] = count
                (continued / "manifest.json").write_text(
                    json.dumps(new), encoding="utf-8"
                )
                with self.assertRaisesRegex(ValueError, "prefix count"):
                    audit_series(continued / "manifest.json", sample_times=())

    def test_checkpoint_equals_monolithic_with_actual_rock_erosion(self):
        net, forcing, material = scenario()
        config = ChannelConfig(max_dt_seconds=0.05)
        sc = SedimentConfig(max_dt_seconds=0.05)
        case = refine_channel("native", net, forcing, np.ones(2, np.int64))
        water = make_channel_product(
            net, forcing, solve_channel(net, forcing, config=config)
        )
        solid = _sediment(case, water, material, sc, 0.0, 1.0, 1e-5)
        self.assertGreater(
            float(solid["arrays"]["trace_rock_removed_m3"][-1].sum()), 0.0
        )
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "series"
            manifest = run_series(
                net,
                forcing,
                np.ones(2, np.int64),
                material,
                output=folder,
                source_manifest={},
                segment_seconds=2.0,
                channel_config=config,
                sediment_config=sc,
                initial_alluvium_depth_m=0.0,
            )
            checkpoint = load_bundle(
                folder / manifest["segments"][-1]["checkpoint"]["path"],
                expected_sha256=manifest["segments"][-1]["checkpoint"]["sha256"],
                validator=_validate_checkpoint,
            )
            for field, expected in (
                ("water_volume_m3", water["arrays"]["trace_volume_m3"][-1]),
                ("mobile_solid_m3", solid["arrays"]["trace_mobile_solid_m3"][-1]),
                ("loose_solid_m3", solid["arrays"]["trace_bed_alluvium_solid_m3"][-1]),
                (
                    "cumulative_rock_removed_m3",
                    solid["arrays"]["trace_rock_removed_m3"][-1],
                ),
                ("bed_elevation_m", solid["arrays"]["trace_bed_elevation_m"][-1]),
            ):
                np.testing.assert_allclose(
                    checkpoint["arrays"][field], expected, rtol=0, atol=1e-10
                )
            with patch(
                "terrain_pipeline.surface_rivers.metric_resolution_series.solve_channel",
                side_effect=AssertionError("cold water"),
            ), patch(
                "terrain_pipeline.surface_rivers.metric_resolution_series.solve_sediment",
                side_effect=AssertionError("cold sediment"),
            ):
                cold = audit_series(folder / "manifest.json", (2.0, 10.0))
            self.assertEqual(cold["status"], "complete")
            self.assertAlmostEqual(
                cold["solid_export_m3"],
                float(solid["arrays"]["step_exported_solid_m3"].sum()),
                places=10,
            )

    def test_rehashed_checkpoint_stock_or_parent_refused(self):
        net, forcing, material = scenario()
        for field in (
            "cumulative_rock_removed_m3",
            "water_volume_m3",
            "bed_elevation_m",
            "parent",
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory) / "series"
                report = run_series(
                    net,
                    forcing,
                    np.ones(2, np.int64),
                    material,
                    output=folder,
                    source_manifest={},
                    segment_seconds=5.0,
                    channel_config=ChannelConfig(max_dt_seconds=0.1),
                    sediment_config=SedimentConfig(max_dt_seconds=0.1),
                    initial_alluvium_depth_m=0.0,
                )
                pin = report["segments"][0]["checkpoint"]
                bundle = load_bundle(
                    folder / pin["path"],
                    expected_sha256=pin["sha256"],
                    validator=_validate_checkpoint,
                )
                changed = dict(
                    arrays={k: v.copy() for k, v in bundle["arrays"].items()},
                    metadata=dict(bundle["metadata"]),
                )
                if field == "parent":
                    changed["metadata"]["parent_checkpoint_identity_sha256"] = "c" * 64
                else:
                    changed["arrays"][field][0] += 0.001
                changed["identity_sha256"] = identity(
                    changed["arrays"], changed["metadata"]
                )
                path = folder / "changed.npz"
                save_bundle(path, changed, validator=_validate_checkpoint)
                report["segments"][0]["checkpoint"] = dict(
                    path=path.name,
                    sha256=file_sha256(path),
                    identity_sha256=changed["identity_sha256"],
                )
                (folder / "manifest.json").write_text(
                    json.dumps(report), encoding="utf-8"
                )
                with self.assertRaisesRegex(ValueError, "checkpoint"):
                    audit_series(folder / "manifest.json", (5.0, 10.0))

    def test_failed_prefix_not_complete_or_resumed(self):
        net, forcing, material = scenario()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "series"
            manifest = run_series(
                net,
                forcing,
                np.ones(2, np.int64),
                material,
                output=folder,
                source_manifest={},
                segment_seconds=5.0,
                channel_config=ChannelConfig(max_dt_seconds=0.1, max_steps=1),
                sediment_config=SedimentConfig(max_dt_seconds=0.1),
            )
            self.assertEqual(manifest["status"], "failed_prefix")
            self.assertEqual(len(manifest["segments"]), 1)
            self.assertEqual(
                audit_series(folder / "manifest.json", (0.1,))["status"],
                "failed_prefix",
            )
            manifest["status"] = "complete"
            (folder / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "completion"):
                audit_series(folder / "manifest.json", (0.1,))

    def test_expanded_node_bound_and_linear_graph_cases(self):
        for receiver in ([2, 2, -1, -1], [2, -1, 1, -1], list(range(1, 2048)) + [-1]):
            validate_receiver_acyclic(np.asarray(receiver, np.int64))
        with self.assertRaisesRegex(ValueError, "acyclic"):
            validate_receiver_acyclic(np.array([1, 2, 0], np.int64))
        net, forcing, _ = scenario()
        self.assertEqual(
            len(
                refine_channel(
                    "max", net, forcing, np.array([1024, 1024], np.int64)
                ).parent_index
            ),
            MAX_SEDIMENT_NODES,
        )
        with self.assertRaisesRegex(ValueError, "limit"):
            refine_channel("over", net, forcing, np.array([1025, 1024], np.int64))

    def test_zero_interval_water_failure_has_pinned_complete_initial_checkpoint(self):
        net, _, material = scenario()
        forcing = ChannelForcing(
            np.array([0.0, 10.0]), np.full((1, 2), 1000.0), "b" * 64
        )
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "series"
            manifest = run_series(
                net,
                forcing,
                np.ones(2, np.int64),
                material,
                output=folder,
                source_manifest={},
                segment_seconds=5.0,
                channel_config=ChannelConfig(max_dt_seconds=0.1),
                sediment_config=SedimentConfig(max_dt_seconds=0.1),
            )
            self.assertEqual(manifest["status"], "failed_prefix")
            self.assertEqual(manifest["last_time_seconds"], 0.0)
            self.assertIsNone(manifest["segments"][0]["solid"])
            self.assertEqual(
                manifest["segments"][0]["water_failure_reason"], "depth limit exceeded"
            )
            cold = audit_series(folder / "manifest.json", (0.0, 5.0))
            self.assertEqual(cold["last_time_seconds"], 0.0)
            self.assertEqual(cold["export_m3"], 0.0)
            self.assertEqual(cold["water_budget_residual_m3"], 0.0)

    def test_early_solid_failure_cold_water_budget_uses_shared_time(self):
        net, forcing, material = scenario()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "series"
            manifest = run_series(
                net,
                forcing,
                np.ones(2, np.int64),
                material,
                output=folder,
                source_manifest={},
                segment_seconds=5.0,
                channel_config=ChannelConfig(max_dt_seconds=0.1),
                sediment_config=SedimentConfig(max_dt_seconds=0.1, max_steps=1),
            )
            self.assertEqual(manifest["segments"][0]["water_status"], "complete")
            self.assertEqual(manifest["segments"][0]["solid_status"], "failed_prefix")
            cold = audit_series(folder / "manifest.json", (0.1, 5.0))
            self.assertEqual(cold["last_time_seconds"], 0.1)
            self.assertEqual(cold["export_m3"], 0.0)
            self.assertAlmostEqual(cold["water_budget_residual_m3"], 0.0, places=12)
            self.assertAlmostEqual(
                sum(cold["stocks"]["water_volume_m3"]["0.1"]), 0.011, places=12
            )
            self.assertNotIn("5.0", cold["stocks"]["water_volume_m3"])

    def test_batch_candidate_is_bit_exact_at_a_junction_without_cross_time_flux(self):
        from tests.test_metric_sediment import domain, forcing

        d = domain(
            (2, 2, -1), open_boundary=[False, False, True], alluvium=[0.5, 0.3, 0.1]
        )
        f = forcing(3, q=0.01, slope=0.005)
        material = MaterialParameters()
        config = SedimentConfig()
        mobile = np.array(
            [[0.1, 0.2, 0.3], [0.2, 0.1, 0.4], [0.4, 0.3, 0.2], [0.3, 0.4, 0.1]]
        )
        loose = np.broadcast_to(
            d.initial_alluvium_bulk_m3 * (1 - material.porosity), mobile.shape
        ).copy()
        rock = np.zeros_like(mobile)
        dt = np.array([0.01, 0.02, 0.03, 0.04])
        batched, reason = _candidate(
            d,
            f,
            material,
            config,
            np.zeros(4, np.int64),
            dt[:, None],
            mobile,
            loose,
            rock,
        )
        self.assertIsNone(reason)
        for row in range(4):
            scalar, reason = _candidate(
                d,
                f,
                material,
                config,
                0,
                float(dt[row]),
                mobile[row],
                loose[row],
                rock[row],
            )
            self.assertIsNone(reason)
            for field, value in scalar.items():
                np.testing.assert_array_equal(batched[field][row], value)

    def test_cached_rates_leave_success_and_failure_products_bit_exact(self):
        from tests.test_metric_sediment import domain, forcing
        import terrain_pipeline.surface_rivers.metric_sediment as sediment

        d = domain((1, -1), open_boundary=[False, True], alluvium=[0.5, 0.1])
        f = forcing(2, q=0.01, slope=0.005)
        original = sediment._candidate

        def uncached(*args, **kwargs):
            kwargs.pop("rates", None)
            return original(*args, **kwargs)

        for budget in (1, 1000):
            config = SedimentConfig(max_dt_seconds=0.05, max_steps=budget)
            with patch.object(sediment, "_candidate", side_effect=uncached):
                reference = solve_sediment(
                    d,
                    f,
                    MaterialParameters(),
                    initial_mobile_solid_m3=np.array([0.1, 0.2]),
                    config=config,
                )
            actual = solve_sediment(
                d,
                f,
                MaterialParameters(),
                initial_mobile_solid_m3=np.array([0.1, 0.2]),
                config=config,
            )
            self.assertEqual(actual["identity_sha256"], reference["identity_sha256"])
            for field, values in reference["arrays"].items():
                np.testing.assert_array_equal(actual["arrays"][field], values)


if __name__ == "__main__":
    unittest.main()
