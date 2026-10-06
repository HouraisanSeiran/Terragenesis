import unittest

import numpy as np

from tools.single_domain_linear_storage_audit import positive_affine_rectangle,positive_affine_square_line,continuous_profile_moments,exact_internal_jump_pressure


class LinearStorageAuditTests(unittest.TestCase):
    def test_clipped_plane_has_exact_positive_triangle_volume(self):
        volume,_ = positive_affine_rectangle([0.,1.,0.],(-.5,.5,-.5,.5))
        self.assertAlmostEqual(volume,.125,places=14)
        self.assertEqual(max(0.,0.),0.)

    def test_fully_wet_linear_momentum_uses_rectangle_second_moment(self):
        volume,momentum = positive_affine_rectangle([1.,.2,.3],(-.5,.5,-.5,.5),[[.4,.5,0.],[-.1,0.,.6]])
        self.assertAlmostEqual(volume,1.,places=14)
        np.testing.assert_allclose(momentum,[.4+.2*.5/12,-.1+.3*.6/12],atol=1e-14,rtol=0)

    def test_wet_dry_edge_square_integral_is_not_midpoint_square(self):
        self.assertAlmostEqual(positive_affine_square_line(-.5,.5),1/24,places=14)
        self.assertEqual(max(0.,(-.5+.5)/2)**2,0.)

    def test_flat_bed_jump_source_zero_for_arbitrary_linear_wet_cut(self):
        center = np.array([[.02,0.,0.]])
        source = exact_internal_jump_pressure(center,np.array([[.4,0,0]]),np.array([[-.2,0,0]]),np.zeros((1,4,4)),4.,9.81)
        np.testing.assert_array_equal(source,np.zeros((1,2)))

    def test_uniform_stage_jump_pressure_telescopes_to_outer_bed_pressure(self):
        bed = np.array([[[0.,.3],[.2,.7]]])
        eta = .5
        actual = exact_internal_jump_pressure(np.array([[eta,0,0]]),np.zeros((1,3)),np.zeros((1,3)),bed,2.,9.81)
        h = np.maximum(eta-bed[0],0)
        expected = 9.81/4*np.array([(h[:,-1]**2-h[:,0]**2).mean(),(h[-1,:]**2-h[0,:]**2).mean()])
        np.testing.assert_allclose(actual[0],expected,atol=1e-14,rtol=0)

    def test_fully_wet_piecewise_bed_volume_is_affine_mean(self):
        bed = np.array([[[.1,.3],[.2,.4]]])
        center = np.array([[1.,.4,-.1]])
        volumes,_ = continuous_profile_moments(center,np.array([[.2,0,0]]),np.array([[.1,0,0]]),bed)
        self.assertAlmostEqual(volumes[0],1.-bed.mean(),places=14)

    def test_exact_jump_and_outer_pressure_leave_physical_stage_gradient(self):
        for eta in (.35,2.):
            bed = np.array([[[.1,.3],[.2,.7]]])
            sx,sz,spacing,gravity = .4,-.2,2.,9.81
            center = np.array([[eta,0,0]])
            slope_x,slope_z = np.array([[sx,0,0]]),np.array([[sz,0,0]])
            volume,_ = continuous_profile_moments(center,slope_x,slope_z,bed)
            source = exact_internal_jump_pressure(center,slope_x,slope_z,bed,spacing,gravity)[0]
            divergence = np.zeros(2)
            edges = np.array([-.5,0.,.5])
            for axis in (0,1):
                for sign in (-1,1):
                    for tangent in range(2):
                        if axis==0:
                            height = bed[0,tangent,0 if sign<0 else -1]
                            first,last = eta+sign*.5*sx+sz*edges[tangent]-height,eta+sign*.5*sx+sz*edges[tangent+1]-height
                        else:
                            height = bed[0,0 if sign<0 else -1,tangent]
                            first,last = eta+sign*.5*sz+sx*edges[tangent]-height,eta+sign*.5*sz+sx*edges[tangent+1]-height
                        divergence[axis] += sign*gravity*positive_affine_square_line(first,last,.5)/(2*spacing)
            np.testing.assert_allclose(source-divergence,-gravity*volume[0]*np.array([sx,sz])/spacing,atol=1e-14,rtol=0)


if __name__=="__main__":
    unittest.main()
