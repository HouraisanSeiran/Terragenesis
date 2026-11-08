"""Finite geological material and actual spatial width of a routed delta front."""
import numpy as np
import pytest

from terrain_pipeline.delta_network_morphology import PlainParameters, whole_plain
from terrain_pipeline.delta_network_site import SiteSpec


def coast(land_height=4., depth=1000.):
    spec=SiteSpec(u0_m=-4000.,v0_m=-6000.,nu=120,nv=120,spacing_m=100.)
    ocean=np.indices((spec.nu,spec.nv))[0]>=40
    bed=np.where(ocean,-depth,land_height)
    return spec,bed,ocean


def test_landward_fill_cannot_spend_more_than_the_finite_geological_supply():
    spec,bed,ocean=coast(land_height=.1,depth=10.)
    pp=PlainParameters(catchment_km2=.001,denudation_m=.01,delivery_fraction=1.)
    result=whole_plain(spec,bed,ocean,pp)
    ledger=result['ledger']
    spent=ledger['landward_fill_solid_m3']+ledger['marine_retained_solid_m3']
    assert ledger['declared_geological_solid_m3']==pytest.approx(10.)
    assert spent<=10.+1e-7
    assert ledger['landward_unmet_fill_solid_m3']>0.
    assert ledger['physical_event_input_solid_m3']==0.


def test_deep_water_resistance_does_not_collapse_the_front_to_one_cell():
    spec,bed,ocean=coast()
    pp=PlainParameters(catchment_km2=100000.,denudation_m=1.,delivery_fraction=.3,
        shelf_depth_bound_m=2000.,front_transition_m=2000.)
    result=whole_plain(spec,bed,ocean,pp)
    profile=result['bed'][40:,60]
    dry=np.flatnonzero(profile>0.)
    assert len(dry)>0
    first_wet=int(dry[-1])+1
    assert first_wet+1<len(profile)
    # Routing resistance is roughly56 here. The old fixed cost-width taper
    # made the first two wet samples plunge hundreds of metres.
    assert profile[first_wet+1]>-100.
    ledger=result['ledger']
    assert ledger['marine_retained_solid_m3']<=ledger['declared_geological_solid_m3']+1e-3


def test_depth_eligibility_boundary_grades_into_the_original_bathymetry():
    spec,bed,ocean=coast(depth=1.)
    depth=.4+np.maximum(np.arange(spec.nu)-40,0.)*2.
    bed=np.where(ocean,-depth[:,None],bed)
    pp=PlainParameters(catchment_km2=100000.,denudation_m=1.,delivery_fraction=.3,
        shelf_depth_bound_m=80.,front_transition_m=2000.)
    result=whole_plain(spec,bed,ocean,pp)
    assert np.max(np.abs(np.diff(result['bed'][74:84,60])))<8.
    np.testing.assert_array_equal(result['bed'][bed<=-80.],bed[bed<=-80.])
