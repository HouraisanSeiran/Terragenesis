from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.mountain_source_adapter import identity
from terrain_pipeline.mountain_storm_forcing import (
    StormParameters, generate_forcing, interval_mean_mm_h, load_forcing,
    preflight, save_forcing, validate_forcing,
)


class StormForcingTests(unittest.TestCase):
    def parameters(self, **changes):
        return replace(StormParameters(1000.,2000.,.1,0.,300.,24.,0.,3600.),**changes)

    def generate(self,owner,**changes):
        kwargs=dict(origin_m_xz=[1000.,2000.],spacing_m=30.,steps=8,dt_s=450.,start_s=0.,
            parameters=self.parameters(),source_identity="a"*64,selection_identity="b"*64)
        kwargs.update(changes)
        return generate_forcing(owner,**kwargs)

    def test_uniform_area_time_integral_and_unique_counts(self):
        owner=np.array([[0,0,1],[-1,1,1]],np.int64)
        forcing=self.generate(owner,parameters=self.parameters(spatial_mode="uniform",start_s=225.,end_s=3375.))
        np.testing.assert_array_equal(forcing["arrays"]["counts"],[2,3])
        self.assertAlmostEqual(validate_forcing(forcing)["total_rain_m3"],24.*3150./3600./1000.*4500.)

    def test_analytic_time_average_matches_fine_numeric_integral(self):
        parameters=self.parameters()
        east=np.array([1000.,1300.,9000.])
        south=np.array([2000.,2050.,2000.])
        exact=interval_mean_mm_h(east,south,0.,900.,parameters)
        times=(np.arange(20000)+.5)*900./20000
        numeric=24*np.exp(-((east[:,None]-1000-.1*times)**2+(south[:,None]-2000)**2)/(2*300**2))
        np.testing.assert_allclose(exact,numeric.mean(axis=1),atol=1e-8,rtol=1e-9)
        split=(interval_mean_mm_h(east,south,0.,450.,parameters)+interval_mean_mm_h(east,south,450.,900.,parameters))/2
        np.testing.assert_allclose(exact,split,atol=1e-13,rtol=1e-13)

    def test_absolute_translation_equivariance(self):
        parameters=self.parameters()
        east=np.array([1000.,1100.])
        south=np.array([2000.,2100.])
        first=interval_mean_mm_h(east,south,100.,900.,parameters)
        moved=replace(parameters,center_x_m=parameters.center_x_m+345000,center_z_m=parameters.center_z_m-70000)
        second=interval_mean_mm_h(east+345000,south-70000,100.,900.,moved)
        np.testing.assert_array_equal(first,second)

    def test_window_split_and_reverse_loading_order(self):
        owner=np.zeros((8,12),np.int64)
        full=self.generate(owner)
        west=self.generate(owner[:,:5])
        east=self.generate(owner[:,5:],origin_m_xz=[1150.,2000.])
        merged=(west["arrays"]["rain_mm_h"]*40+east["arrays"]["rain_mm_h"]*56)/96
        np.testing.assert_allclose(full["arrays"]["rain_mm_h"],merged,atol=1e-13,rtol=1e-13)
        repeated_east=self.generate(owner[:,5:],origin_m_xz=[1150.,2000.])
        np.testing.assert_array_equal(east["arrays"]["rain_mm_h"],repeated_east["arrays"]["rain_mm_h"])

    def test_outside_active_time_zero_and_tiny_velocity_stable(self):
        parameters=self.parameters(start_s=3600.,end_s=7200.)
        np.testing.assert_array_equal(interval_mean_mm_h(np.array([1000.]),np.array([2000.]),0.,900.,parameters),[0.])
        still=self.parameters(velocity_x_m_s=0.)
        moving=replace(still,velocity_x_m_s=1e-10)
        np.testing.assert_allclose(interval_mean_mm_h(np.array([1000.]),np.array([2000.]),0.,900.,still),
            interval_mean_mm_h(np.array([1000.]),np.array([2000.]),0.,900.,moving),rtol=1e-12,atol=1e-12)

    def test_spatial_subsample_refinement_is_explicit(self):
        owner=np.zeros((3,3),np.int64)
        center=self.generate(owner,parameters=self.parameters(sigma_m=20.))
        refined=self.generate(owner,parameters=self.parameters(sigma_m=20.),spatial_subsamples=4)
        self.assertGreater(np.max(np.abs(center["arrays"]["rain_mm_h"]-refined["arrays"]["rain_mm_h"])),.001)
        self.assertEqual(refined["metadata"]["spatial_subsamples"],4)

    def test_save_atomic_coldload_no_generation_and_external_identity(self):
        owner=np.zeros((4,4),np.int64)
        forcing=self.generate(owner)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"weather.npz"
            save_forcing(path,forcing)
            with self.assertRaises(FileExistsError):
                save_forcing(path,forcing)
            with patch("terrain_pipeline.mountain_storm_forcing.generate_forcing",side_effect=AssertionError("weather prepare")):
                loaded=load_forcing(path,expected_sha256=file_sha256(path),cell_owner=owner,
                    source_identity="a"*64,selection_identity="b"*64)
            self.assertEqual(loaded["identity_sha256"],forcing["identity_sha256"])
            with self.assertRaises(ValueError):
                load_forcing(path,expected_sha256=file_sha256(path),cell_owner=owner,
                    source_identity="c"*64,selection_identity="b"*64)

    def test_resource_and_illegal_inputs_rejected(self):
        with self.assertRaises(ValueError):
            preflight(250000,250000,1344,256,1)
        with self.assertRaises(ValueError):
            self.generate(np.array([[0,2]],np.int64))
        for changes in ({"sigma_m":0.},{"peak_mm_h":float("nan")},{"velocity_x_m_s":200.}):
            with self.assertRaises(ValueError):
                self.parameters(**changes)

    def test_extremely_low_speed_matches_high_resolution_quadrature(self):
        east=np.array([1000.,1300.,1900.])
        south=np.array([2000.,2050.,2000.])
        times=(np.arange(20000)+.5)*900/20000
        for velocity in (1e-8,1e-10,1e-12,1e-14):
            parameters=self.parameters(velocity_x_m_s=velocity)
            actual=interval_mean_mm_h(east,south,0.,900.,parameters)
            reference=(24*np.exp(-((east[:,None]-1000-velocity*times)**2+
                (south[:,None]-2000)**2)/(2*300**2))).mean(axis=1)
            np.testing.assert_allclose(actual,reference,atol=1e-12,rtol=1e-12)

    def test_resigned_invalid_grid_time_metadata_rejected(self):
        import copy

        forcing=self.generate(np.zeros((4,4),np.int64))
        for key,value in (("dt_s",-450.),("dt_s",float("nan")),("spacing_m",0.),
                ("origin_m_xz",[float("nan"),2000.]),("start_s",-1.)):
            forged=copy.deepcopy(forcing)
            forged["metadata"][key]=value
            if not (isinstance(value,float) and np.isnan(value)) and key!="origin_m_xz":
                forged["identity_sha256"]=identity(forged["arrays"],forged["metadata"])
            with self.assertRaises(ValueError):
                validate_forcing(forged)


if __name__=="__main__":
    unittest.main()
