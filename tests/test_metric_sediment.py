import hashlib
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity
from terrain_pipeline.surface_rivers.metric_bed_update import bed_from_inventory
from terrain_pipeline.surface_rivers.metric_sediment import (
    MaterialParameters, SedimentConfig, SedimentDomain, SedimentForcing,
    load_sediment, save_sediment, solve_sediment, validate_sediment,
)


GEOMETRY = "a" * 64
HYDRAULICS = "b" * 64


def domain(receiver=(-1,), *, open_boundary=None, alluvium=None, area=None, is_lake=None):
    n = len(receiver)
    return SedimentDomain(
        receiver=np.array(receiver, np.int64), bed_area_m2=np.array(area if area is not None else [10.] * n),
        width_m=np.ones(n), bed_elevation_m=np.arange(n, 0, -1, dtype=np.float64),
        rock_floor_m=np.arange(n, 0, -1, dtype=np.float64) - 2.,
        initial_alluvium_bulk_m3=np.array(alluvium if alluvium is not None else [0.] * n),
        is_lake=np.array(is_lake if is_lake is not None else [False] * n, dtype=np.bool_),
        open_boundary=np.array(open_boundary if open_boundary is not None else [False] * n, dtype=np.bool_),
        geometry_identity_sha256=GEOMETRY, provenance="independent rectangular fixture",
    )


def forcing(n, *, duration=1., depth=1., volume=10., q=0., slope=0., external=0.):
    return SedimentForcing(
        time_seconds=np.array([0., duration]), water_volume_m3=np.full((1, n), volume),
        water_depth_m=np.full((1, n), depth), water_outflow_m3_s=np.full((1, n), q),
        friction_slope=np.full((1, n), slope), external_solid_m3_s=np.full((1, n), external),
        hydraulic_identity_sha256=HYDRAULICS, geometry_identity_sha256=GEOMETRY,
        provenance="pinned water fixture",
    )


class SedimentTests(unittest.TestCase):
    def test_static_water_preserves_bed_and_inventory(self):
        result = solve_sediment(domain(alluvium=[1.]), forcing(1), MaterialParameters(),
                                initial_mobile_solid_m3=np.array([0.]),
                                config=SedimentConfig(max_dt_seconds=.25))
        self.assertEqual(result["metadata"]["status"], "complete")
        self.assertFalse(result["metadata"]["needs_geometry_and_hydraulic_revalidation"])
        np.testing.assert_array_equal(result["arrays"]["trace_bed_elevation_m"][-1], [1.])
        self.assertEqual(np.sum(result["arrays"]["step_eroded_rock_m3"]), 0.)

    def test_shear_threshold_and_finite_rock_reserve(self):
        material = MaterialParameters(porosity=0., sediment_critical_shear_pa=1., rock_critical_shear_pa=2.,
                                      rock_erodibility_m_s_pa=.001, transport_coefficient=1.,
                                      settling_velocity_m_s=0., provenance="fixture")
        below = solve_sediment(domain(open_boundary=[True]), forcing(1, q=1., slope=.0001), material)
        self.assertEqual(np.sum(below["arrays"]["step_eroded_rock_m3"]), 0.)
        above = solve_sediment(domain(open_boundary=[True]), forcing(1, q=1., slope=.002), material,
                               config=SedimentConfig(max_dt_seconds=.05, max_bed_change_m=1.))
        self.assertGreater(np.sum(above["arrays"]["step_eroded_rock_m3"]), 0.)
        self.assertLessEqual(above["arrays"]["trace_rock_removed_m3"][-1, 0], 20.)

    def test_porosity_and_closed_terminal_settling(self):
        material = MaterialParameters(porosity=.35, settling_velocity_m_s=1., provenance="fixture")
        result = solve_sediment(domain(area=[1.]), forcing(1, depth=2., volume=2.), material,
                                initial_mobile_solid_m3=np.array([.65]),
                                config=SedimentConfig(max_dt_seconds=.02, max_bed_change_m=2.))
        a = result["arrays"]
        deposited = np.sum(a["step_deposited_solid_m3"])
        self.assertAlmostEqual(np.sum(a["step_bulk_deposition_m3"]), deposited / .65)
        self.assertAlmostEqual(np.sum(a["step_pore_deposition_m3"]), deposited * .35 / .65)
        self.assertEqual(np.sum(a["step_exported_solid_m3"]), 0.)
        self.assertAlmostEqual(a["trace_mobile_solid_m3"][-1, 0] + a["trace_bed_alluvium_solid_m3"][-1, 0], .65)
        self.assertAlmostEqual(bed_from_inventory(np.array([0.]), np.array([0.]),
                                                  np.array([.65]), np.array([0.]),
                                                  np.array([1.]), .35)[0], 1.)

    def test_settling_refines_toward_independent_exponential(self):
        d = domain(area=[10.])
        f = forcing(1, depth=2., volume=20.)
        material = MaterialParameters(settling_velocity_m_s=1., provenance="constant-depth reference")
        start = np.array([.65])
        coarse = solve_sediment(d, f, material, start, SedimentConfig(max_dt_seconds=.2))
        fine = solve_sediment(d, f, material, start, SedimentConfig(max_dt_seconds=.01))
        exact = .65 * math.exp(-.5)
        coarse_error = abs(coarse["arrays"]["trace_mobile_solid_m3"][-1, 0] - exact)
        fine_error = abs(fine["arrays"]["trace_mobile_solid_m3"][-1, 0] - exact)
        self.assertLess(fine_error / exact, .005)
        self.assertLess(fine_error, coarse_error)
        deposited = .65 - fine["arrays"]["trace_mobile_solid_m3"][-1, 0]
        self.assertAlmostEqual(fine["arrays"]["trace_bed_elevation_m"][-1, 0] - 1.,
                               deposited / (.65 * 10.), places=9)

    def test_two_node_transfer_and_open_export(self):
        material = MaterialParameters(porosity=0., sediment_critical_shear_pa=0.,
                                      transport_coefficient=100., settling_velocity_m_s=0., provenance="fixture")
        d = domain(receiver=(1, -1), open_boundary=[False, True])
        f = SedimentForcing(np.array([0., 1.]), np.full((1, 2), 10.), np.ones((1, 2)),
                            np.ones((1, 2)), np.full((1, 2), .001), np.zeros((1, 2)),
                            HYDRAULICS, GEOMETRY, "test")
        a = solve_sediment(d, f, material, np.array([1., 0.]),
                           SedimentConfig(max_dt_seconds=.1))["arrays"]
        self.assertGreater(np.sum(a["step_incoming_solid_m3"][:, 1]), 0.)
        self.assertGreater(a["cumulative_exported_solid_m3"][-1], 0.)
        self.assertAlmostEqual(np.sum(a["trace_mobile_solid_m3"][-1]) + a["cumulative_exported_solid_m3"][-1], 1.)

    def test_failed_prefix_witness_and_cold_load(self):
        material = MaterialParameters(porosity=0., sediment_critical_shear_pa=0.,
                                      rock_critical_shear_pa=0., rock_erodibility_m_s_pa=.01,
                                      transport_coefficient=1., settling_velocity_m_s=0., provenance="fixture")
        result = solve_sediment(domain(open_boundary=[True]), forcing(1, q=1., slope=.01), material,
                                config=SedimentConfig(max_dt_seconds=.1, max_bed_change_m=.001))
        self.assertEqual(result["metadata"]["status"], "failed_prefix")
        self.assertLess(result["metadata"]["last_time_seconds"], 1.)
        validate_sediment(result)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sediment.npz"
            save_sediment(path, result)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            loaded = load_sediment(path, expected_sha256=digest)
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])

    def test_identity_and_closed_water_guard(self):
        f = forcing(1)
        changed = SedimentForcing(f.time_seconds, f.water_volume_m3, f.water_depth_m,
                                  f.water_outflow_m3_s, f.friction_slope, f.external_solid_m3_s,
                                  HYDRAULICS, "c" * 64, "test")
        with self.assertRaisesRegex(ValueError, "geometry identity"):
            solve_sediment(domain(), changed, MaterialParameters())
        with self.assertRaisesRegex(ValueError, "closed terminal"):
            solve_sediment(domain(), forcing(1, q=1.), MaterialParameters())

    def test_lake_outlet_advects_without_lake_entrainment(self):
        d = domain(receiver=(1, -1), is_lake=[True, False], open_boundary=[False, True])
        f = SedimentForcing(np.array([0., 1.]), np.full((1, 2), 10.), np.ones((1, 2)),
                            np.array([[1., 0.]]), np.full((1, 2), .1), np.zeros((1, 2)),
                            HYDRAULICS, GEOMETRY, "test")
        result = solve_sediment(d, f, MaterialParameters(settling_velocity_m_s=0.),
                                np.array([1., 0.]))
        a = result["arrays"]
        self.assertGreater(np.sum(a["step_incoming_solid_m3"][:, 1]), 0.)
        self.assertEqual(np.sum(a["step_eroded_rock_m3"][:, 0]), 0.)
        self.assertEqual(np.sum(a["step_shear_pa"][:, 0]), 0.)

    def test_cold_validator_rejects_rehashed_forgery(self):
        good = solve_sediment(domain(open_boundary=[True]), forcing(1, q=1., slope=.001),
                              MaterialParameters(), np.array([.1]))

        def forged(array_name=None, change=None, metadata=None):
            arrays = {key: value.copy() for key, value in good["arrays"].items()}
            meta = dict(good["metadata"])
            if array_name is not None:
                change(arrays[array_name])
            if metadata:
                meta.update(metadata)
            return {"arrays": arrays, "metadata": meta, "identity_sha256": identity(arrays, meta)}

        with self.assertRaisesRegex(ValueError, "maximum time step"):
            validate_sediment(forged(metadata={"config": {**good["metadata"]["config"], "max_dt_seconds": .01}}))
        with self.assertRaisesRegex(ValueError, "failure prefix|complete"):
            validate_sediment(forged(metadata={"status": "failed_prefix", "failure_reason": "invented"}))
        with self.assertRaisesRegex(ValueError, "revalidation|certify"):
            validate_sediment(forged(metadata={"hydraulic_ready": 0}))

        def negate(values):
            values[-1, 0] = -1e-14

        with self.assertRaisesRegex(ValueError, "negative sediment inventory"):
            validate_sediment(forged("trace_mobile_solid_m3", negate))

    def test_large_datum_bed_tampering_is_visible(self):
        d = SedimentDomain(np.array([-1], np.int64), np.array([10.]), np.array([1.]),
                           np.array([1e9]), np.array([1e9 - 2.]), np.array([0.]),
                           np.array([False]), np.array([False]), GEOMETRY, "large datum fixture")
        good = solve_sediment(d, forcing(1), MaterialParameters())
        arrays = {key: value.copy() for key, value in good["arrays"].items()}
        arrays["trace_bed_elevation_m"][-1, 0] += .01
        forged = {"arrays": arrays, "metadata": dict(good["metadata"]),
                  "identity_sha256": identity(arrays, good["metadata"])}
        with self.assertRaisesRegex(ValueError, "bed_elevation_m"):
            validate_sediment(forged)


if __name__ == "__main__":
    unittest.main()
