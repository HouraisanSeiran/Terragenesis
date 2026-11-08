import unittest

import numpy as np

from terrain_pipeline.surface_hydraulics import prepare_surface_geometry, SurfaceBudget
from terrain_pipeline.fine_subgrid import coarsen_cell_field, prepare_subgrid_support
from terrain_pipeline.shallow_water import single_domain_shallow_water_support_shallow_water_rhs as flat_rhs
from terrain_pipeline.shallow_water import single_domain_shallow_water_support_mechanism_3_shallow_water_rhs as shallow_water_rhs
from terrain_pipeline.shallow_water import single_domain_shallow_water_mechanism_3_advance_shallow_water as advance_shallow_water


class ShallowWaterV3Tests(unittest.TestCase):
    def test_ritter_dry_bed_evolution_refines_toward_exact_cell_means(self):
        gravity, duration, dam, extent = 9.81, 5., 80., 160.
        celerity = np.sqrt(gravity)
        errors = []
        for factor in (4, 2, 1):
            geometry, _, _ = self.geometry(np.zeros((12, 160)), factor)
            bed = geometry["arrays"]["H2_m"]
            depth = np.zeros_like(bed)
            depth[:, :int(dam/factor)] = 1.
            result = advance_shallow_water(geometry, initial_depth_m=depth, forcing_interval_s=duration, intervals=1,
                forcing_provider=lambda i: np.zeros_like(bed), boundary_stage_provider=lambda i: np.zeros(2*sum(bed.shape)),
                source_identity="synthetic", forcing_identity="Ritter-dry-bed",
                budget=SurfaceBudget(max_dt_s=.025, max_snapshots=3, max_duration_s=duration, roughness_s_m_third=.000001),
                snapshot_interval_s=duration, interval_observer=lambda packet: None, momentum_observer=lambda packet: None)
            # Integrate the rarefaction polynomial exactly, including its two
            # moving breaks, instead of sampling an exact solution at centers.
            lo = np.arange(int(extent/factor))*factor-dam
            hi = lo+factor
            upstream_end, downstream_start = -celerity*duration, 2*celerity*duration
            upstream = np.maximum(np.minimum(hi, upstream_end)-lo, 0.)
            rare_lo, rare_hi = np.maximum(lo, upstream_end), np.minimum(hi, downstream_start)
            primitive_lo = -duration/(27*gravity)*(2*celerity-rare_lo/duration)**3
            primitive_hi = -duration/(27*gravity)*(2*celerity-rare_hi/duration)**3
            rare = np.where(rare_hi > rare_lo, primitive_hi-primitive_lo, 0.)
            exact = (upstream+rare)/factor
            numerical = result["arrays"]["depth_m"][-1].mean(axis=0)
            errors.append(float(np.mean(abs(numerical-exact))))
            self.assertLess(abs(result["arrays"]["ledger"][-1, -1]), 1e-9)
        self.assertLess(errors[1], errors[0]*.85, errors)
        self.assertLess(errors[2], errors[1]*.85, errors)
        self.assertLess(errors[2], .025, errors)
        self.ritter_l1_errors = errors

    def geometry(self, canonical, factor):
        coarse = canonical if factor == 1 else coarsen_cell_field(canonical, factor=factor)
        bed = dict(arrays=dict(canonical_bed_center_m=canonical, H2_m=coarse), metadata=dict(spacing_m=float(factor)))
        support, datum = prepare_subgrid_support(bed)
        geometry = prepare_surface_geometry(coarse, spacing_m=float(factor), origin_m_xz=[0., 0.], source_identity="synthetic")
        geometry["arrays"].update(support)
        geometry["metadata"]["hydraulic_datum_m"] = datum
        return geometry, support, datum

    def test_canonical_half_wet_lake_at_all_resolutions(self):
        canonical = 1350.+np.tile(np.arange(16)*.1, (12, 1))+.05*np.arange(12)[:, None]
        fine_depth = np.maximum(1350.8-canonical, 0.)
        for factor in (1, 2, 4):
            geometry, support, datum = self.geometry(canonical, factor)
            bed = geometry["arrays"]["H2_m"]
            depth = fine_depth if factor == 1 else coarsen_cell_field(fine_depth, factor=factor)
            state = np.column_stack((depth.ravel(), np.zeros((bed.size, 2))))
            rhs, _ = shallow_water_rhs(state, bed-datum, support=support, spacing=float(factor), gravity=9.81,
                boundary_kind=geometry["arrays"]["boundary_kind"], tailwater=np.zeros(2*sum(bed.shape)), roughness=.035, dt=.01)
            np.testing.assert_allclose(rhs, 0., rtol=0., atol=2e-12)
            result = advance_shallow_water(geometry, initial_depth_m=depth, forcing_interval_s=.1, intervals=2,
                forcing_provider=lambda i: np.zeros_like(bed), boundary_stage_provider=lambda i: np.zeros(2*sum(bed.shape)),
                source_identity="synthetic", forcing_identity="synthetic", budget=SurfaceBudget(max_dt_s=.01, max_snapshots=4),
                snapshot_interval_s=.1, interval_observer=lambda packet: None, momentum_observer=lambda packet: None)
            np.testing.assert_allclose(result["arrays"]["depth_m"][-1], depth, rtol=0., atol=2e-12)

    def test_flat_bed_nonuniform_state_matches_standard_shallow_water(self):
        canonical = np.zeros((12, 16))
        rng = np.random.default_rng(13)
        for factor in (1, 2, 4):
            geometry, support, datum = self.geometry(canonical, factor)
            bed = geometry["arrays"]["H2_m"]
            state = np.column_stack((rng.uniform(.1, 2., bed.size), rng.uniform(-.2, .2, (bed.size, 2))))
            args = dict(spacing=float(factor), gravity=9.81, boundary_kind=geometry["arrays"]["boundary_kind"],
                tailwater=np.zeros(2*sum(bed.shape)), roughness=.035, dt=.01)
            rhs, witness = shallow_water_rhs(state, bed, support=support, **args)
            expected, _ = flat_rhs(state, bed, **args)
            np.testing.assert_allclose(witness["bed_source"], 0., rtol=0., atol=1e-14)
            np.testing.assert_allclose(rhs, expected, rtol=0., atol=1e-13)

    def test_flat_dam_break_has_pressure_driven_momentum(self):
        geometry, support, _ = self.geometry(np.zeros((8, 16)), 2)
        bed = geometry["arrays"]["H2_m"]
        depth = np.ones_like(bed)
        depth[:, :bed.shape[1]//2] = 2.
        state = np.column_stack((depth.ravel(), np.zeros((bed.size, 2))))
        rhs, witness = shallow_water_rhs(state, bed, support=support, spacing=2., gravity=9.81,
            boundary_kind=geometry["arrays"]["boundary_kind"], tailwater=np.zeros(2*sum(bed.shape)), roughness=.035, dt=.01)
        self.assertGreater(float(rhs[:, 1].max()), 1.)
        self.assertAlmostEqual(float(rhs[:, 0].sum()), 0., places=13)
        np.testing.assert_allclose(witness["bed_source"], 0., rtol=0., atol=1e-14)


if __name__ == "__main__":
    unittest.main()
