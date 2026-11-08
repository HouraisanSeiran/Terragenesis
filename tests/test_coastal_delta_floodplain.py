import numpy as np
import pytest

from terrain_pipeline.coastal_delta_floodplain import advance_floodplain


def advance(bed, water, mobile=None, stranded=None, **kwargs):
    shape = np.asarray(bed).shape
    parameters = dict(area_m2=100., solid_area_m2=60., allowed_mask=True,
                      spacing_m=10., duration_s=600.)
    parameters.update(kwargs)
    return advance_floodplain(
        bed, water, np.zeros(shape) if mobile is None else mobile,
        np.zeros(shape) if stranded is None else stranded, **parameters)


def assert_budget(result, water, mobile, stranded):
    assert result['water_m3'].sum() == pytest.approx(np.sum(water), abs=1e-10)
    final = sum(result[name].sum() for name in (
        'mobile_solid_m3', 'stranded_solid_m3', 'deposited_solid_m3'))
    assert final == pytest.approx(np.sum(mobile) + np.sum(stranded), abs=1e-10)
    assert abs(result['report']['water_residual_m3']) < 1e-9
    assert abs(result['report']['solid_residual_m3']) < 1e-9
    for name in ('water_m3', 'mobile_solid_m3', 'stranded_solid_m3',
                 'deposited_solid_m3'):
        assert np.all(np.isfinite(result[name]))
        assert np.all(result[name] >= 0)


def test_multiple_faces_share_finite_water_and_carry_donor_concentration():
    bed = np.zeros((3, 3))
    water = np.zeros_like(bed)
    mobile = np.zeros_like(bed)
    water[1, 1] = 100.
    mobile[1, 1] = 2.
    result = advance(bed, water, mobile, duration_s=60.,
                     settling_velocity_m_s=0.)
    assert_budget(result, water, mobile, np.zeros_like(bed))
    assert result['water_m3'][1, 1] > 0
    assert np.count_nonzero(result['water_m3']) == 5
    assert np.allclose(result['mobile_solid_m3'], .02 * result['water_m3'])
    assert result['water_m3'].max() <= 100.
    # Four equivalent faces receive the same finite parcel.
    neighbors = result['water_m3'][[0, 1, 1, 2], [1, 0, 2, 1]]
    assert np.all(neighbors > 0)
    assert np.all(neighbors == neighbors[0])


def test_multiple_donors_do_not_raise_head_above_initial_maximum():
    bed = np.zeros((3, 3))
    water = np.full_like(bed, 100.)
    water[1, 1] = 0.
    result = advance(bed, water, settling_velocity_m_s=0., duration_s=600.)
    assert result['water_m3'][1, 1] > 0
    assert result['water_m3'].max() <= 100.
    assert_budget(result, water, np.zeros_like(bed), np.zeros_like(bed))


def test_unequal_storage_areas_preserve_concentration_and_bound_water_heads():
    bed = np.zeros((3, 5))
    area = np.arange(1., 16.).reshape(bed.shape) * 20.
    water = np.zeros_like(bed)
    water[1, 2] = 900.
    mobile = .03 * water
    initial_max_head = np.max(bed + water / area)
    result = advance(bed, water, mobile, area_m2=area, solid_area_m2=.6 * area,
                     duration_s=900., max_step_s=30., settling_velocity_m_s=0.)
    assert np.all(result['water_m3'] > 0)
    assert np.max(result['bed_m'] + result['water_m3'] / area) <= initial_max_head
    assert np.allclose(result['mobile_solid_m3'], .03 * result['water_m3'])
    assert_budget(result, water, mobile, np.zeros_like(bed))


def test_actual_dry_ridge_blocks_water_and_sediment_even_diagonally():
    bed = np.array([[0., 2., 0.], [2., 2., 2.], [0., 2., 0.]])
    water = np.zeros_like(bed)
    mobile = np.zeros_like(bed)
    water[0, 0] = 100.
    mobile[0, 0] = 1.
    result = advance(bed, water, mobile, duration_s=3600.)
    assert np.count_nonzero(result['water_m3']) == 1
    assert np.count_nonzero(result['deposited_solid_m3']) == 1
    assert result['water_m3'][1, 1] == 0.
    assert_budget(result, water, mobile, np.zeros_like(bed))


def test_ridge_can_be_overtopped_only_by_sufficient_stored_water():
    bed = np.array([[0., 1., 0.]])
    low = advance(bed, np.array([[50., 0., 0.]]), duration_s=600.,
                  settling_velocity_m_s=0.)
    high = advance(bed, np.array([[300., 0., 0.]]), duration_s=600.,
                   settling_velocity_m_s=0.)
    assert low['water_m3'][0, 2] == 0.
    assert high['water_m3'][0, 2] > 0.
    assert high['water_m3'].sum() == pytest.approx(300.)


def test_closed_depression_retains_water_and_low_sill_retains_residual_pool():
    bed = np.full((5, 5), 3.)
    bed[1:4, 1:4] = 0.
    water = np.zeros_like(bed)
    water[2, 2] = 90.
    result = advance(bed, water, duration_s=3600., settling_velocity_m_s=0.)
    assert np.count_nonzero(result['water_m3']) == 9
    assert np.all(result['water_m3'][bed == 3.] == 0)
    assert result['water_m3'][1:4, 1:4].sum() == pytest.approx(90.)
    assert np.ptp(result['water_m3'][1:4, 1:4]) < 1e-6
    # A low spill cell drains excess, while the basin below its crest remains.
    bed = np.array([[0., 1., 0.]])
    water = np.array([[150., 0., 0.]])
    result = advance(bed, water, duration_s=7200., settling_velocity_m_s=0.)
    assert 100. - 1e-9 <= result['water_m3'][0, 0] < 150.
    assert result['water_m3'][0, 2] > 0.
    assert result['water_m3'].sum() == pytest.approx(150.)


def test_exponential_settling_uses_physical_seconds_and_actual_solid_area():
    bed = np.array([[2.]])
    water = np.array([[50.]])
    mobile = np.array([[4.]])
    expected_deposit = 4. * -np.expm1(-.001 * 600. / .5)
    a = advance(bed, water, mobile, settling_velocity_m_s=.001, max_step_s=60.)
    b = advance(bed, water, mobile, settling_velocity_m_s=.001, max_step_s=17.)
    assert a['deposited_solid_m3'][0, 0] == pytest.approx(expected_deposit)
    assert b['deposited_solid_m3'][0, 0] == pytest.approx(expected_deposit)
    assert a['bed_m'][0, 0] == pytest.approx(2. + expected_deposit / 60.)
    assert a['water_m3'][0, 0] == 50.
    assert a['report']['steps'] == 10
    assert b['report']['steps'] == 36
    assert 'no momentum' in a['report']['approximation']
    assert_budget(a, water, mobile, np.zeros_like(bed))


def test_finite_pulse_produces_near_to_far_settling_cross_section():
    bed = np.zeros((1, 12))
    water = np.zeros_like(bed)
    mobile = np.zeros_like(bed)
    water[0, 0] = 600.
    mobile[0, 0] = 6.
    result = advance(bed, water, mobile, duration_s=3600.,
                     settling_velocity_m_s=.001, max_step_s=15.)
    profile = result['deposited_solid_m3'][0]
    assert np.all(profile > 0)
    assert profile[0] > profile[3] > profile[-1]
    assert profile[:3].sum() > profile[-3:].sum()
    assert np.allclose(result['bed_m'], bed + result['deposited_solid_m3'] / 60.)
    assert result['deposited_solid_m3'].sum() <= mobile.sum()
    assert_budget(result, water, mobile, np.zeros_like(bed))


def test_bed_rise_changes_subsequent_water_head_without_creating_water():
    bed = np.zeros((1, 2))
    water = np.full_like(bed, 50.)
    mobile = np.array([[30., 0.]])
    result = advance(bed, water, mobile, duration_s=600.,
                     settling_velocity_m_s=.1, max_step_s=10.)
    assert result['bed_m'][0, 0] > result['bed_m'][0, 1]
    assert result['water_m3'][0, 1] > 50.
    assert result['water_m3'][0, 0] < 50.
    assert_budget(result, water, mobile, np.zeros_like(bed))


def test_allowed_mask_and_zero_area_are_closed_and_preserve_all_stocks():
    bed = np.zeros((3, 5))
    allowed = np.ones_like(bed, dtype=bool)
    allowed[:, 2] = False
    area = np.full_like(bed, 100.)
    area[2, 0] = 0.
    water = np.zeros_like(bed)
    mobile = np.zeros_like(bed)
    stranded = np.zeros_like(bed)
    water[1, 0] = 200.
    water[:, 2] = [5., 6., 7.]
    water[2, 0] = 8.
    mobile[:, 2] = [1., 2., 3.]
    mobile[2, 0] = 4.
    stranded[:, 2] = [3., 4., 5.]
    stranded[2, 0] = 6.
    result = advance(bed, water, mobile, stranded, allowed_mask=allowed, area_m2=area)
    blocked = ~allowed | (area == 0)
    for name, original in (('water_m3', water), ('mobile_solid_m3', mobile),
                           ('stranded_solid_m3', stranded)):
        assert np.array_equal(result[name][blocked], original[blocked])
    assert np.all(result['water_m3'][:, 3:] == 0)
    assert np.all(result['deposited_solid_m3'][blocked] == 0)
    assert_budget(result, water, mobile, stranded)


def test_dry_mobile_is_stranded_and_local_rewetting_remobilizes_only_local_stock():
    bed = np.array([[0., 0., 3.]])
    water = np.array([[100., 0., 0.]])
    mobile = np.array([[0., .2, .3]])
    stranded = np.array([[.1, .4, .5]])
    result = advance(bed, water, mobile, stranded, duration_s=60.,
                     settling_velocity_m_s=0.)
    assert result['water_m3'][0, 1] > 0
    assert result['stranded_solid_m3'][0, 0] == 0.
    assert result['stranded_solid_m3'][0, 1] == 0.
    assert result['mobile_solid_m3'][0, 1] >= .6
    assert result['mobile_solid_m3'][0, 2] == 0.
    assert result['stranded_solid_m3'][0, 2] == pytest.approx(.8)
    assert_budget(result, water, mobile, stranded)


def test_zero_water_and_zero_supply_cannot_create_water_or_deposited_terrain():
    bed = np.array([[0., 1.], [-1., 3.]])
    zeros = np.zeros_like(bed)
    empty = advance(bed, zeros)
    stranded = np.full_like(bed, 2.)
    dry = advance(bed, zeros, stranded=stranded)
    for result in (empty, dry):
        assert np.array_equal(result['bed_m'], bed)
        assert np.array_equal(result['water_m3'], zeros)
        assert np.array_equal(result['deposited_solid_m3'], zeros)
        assert result['report']['steps'] == 0
    assert np.array_equal(dry['stranded_solid_m3'], stranded)
    water_only = advance(bed, np.array([[200., 0.], [0., 0.]]))
    assert np.array_equal(water_only['bed_m'], bed)
    assert np.array_equal(water_only['deposited_solid_m3'], zeros)


def test_deterministic_cropped_update_preserves_inputs_and_returns_independent_arrays():
    bed = np.zeros((19, 23))
    water = np.zeros_like(bed)
    mobile = np.zeros_like(bed)
    stranded = np.zeros_like(bed)
    water[8, 10] = 200.
    mobile[8, 10] = 2.
    originals = [array.copy() for array in (bed, water, mobile, stranded)]
    a = advance(bed, water, mobile, stranded, duration_s=120.)
    b = advance(bed, water, mobile, stranded, duration_s=120.)
    assert 0 < a['report']['max_active_box_cells'] < bed.size
    assert a['water_m3'][8, 11] > 0
    for name, original, supplied in zip(
            ('bed_m', 'water_m3', 'mobile_solid_m3', 'stranded_solid_m3'),
            originals, (bed, water, mobile, stranded)):
        assert np.array_equal(supplied, original)
        assert not np.shares_memory(a[name], supplied)
        assert np.array_equal(a[name], b[name])
    assert a['report'] == b['report']
    assert_budget(a, water, mobile, stranded)


def test_zero_duration_preserves_phase_inventories():
    bed = np.zeros((1, 2))
    water = np.array([[0., 10.]])
    mobile = np.array([[2., 3.]])
    stranded = np.array([[4., 5.]])
    result = advance(bed, water, mobile, stranded, duration_s=0.)
    for name, original in (('water_m3', water), ('mobile_solid_m3', mobile),
                           ('stranded_solid_m3', stranded)):
        assert np.array_equal(result[name], original)
    assert result['report']['steps'] == 0


@pytest.mark.parametrize('parameter,value', [
    ('spacing_m', 0.), ('spacing_m', np.nan), ('duration_s', -1.),
    ('duration_s', np.inf), ('roughness', 0.), ('roughness', -.1),
    ('settling_velocity_m_s', -1.), ('settling_velocity_m_s', np.nan),
    ('max_step_s', 0.), ('max_step_s', -1.), ('max_step_s', np.inf),
    ('area_m2', -1.), ('area_m2', np.nan), ('solid_area_m2', 0.),
    ('solid_area_m2', -1.), ('solid_area_m2', np.inf),
    ('area_m2', np.zeros((2, 3))), ('allowed_mask', np.ones((2, 3), dtype=bool)),
    ('allowed_mask', 1),
])
def test_invalid_parameters_are_rejected(parameter, value):
    with pytest.raises(ValueError):
        advance(np.zeros((2, 2)), np.zeros((2, 2)), **{parameter: value})


@pytest.mark.parametrize('name,defect', [
    (name, defect)
    for name in ('bed_m', 'water_m3', 'mobile_solid_m3', 'stranded_solid_m3')
    for defect in ('shape', 'nan', 'negative')
    if (name, defect) != ('bed_m', 'negative')
])
def test_invalid_arrays_are_rejected_without_modification(name, defect):
    arrays = {key: np.zeros((2, 2)) for key in (
        'bed_m', 'water_m3', 'mobile_solid_m3', 'stranded_solid_m3')}
    if defect == 'shape':
        arrays[name] = np.zeros((2, 3)) if name != 'bed_m' else np.zeros(4)
    elif defect == 'nan':
        arrays[name][0, 0] = np.nan
    else:
        arrays[name][0, 0] = -1.
    originals = {key: value.copy() for key, value in arrays.items()}
    with pytest.raises(ValueError):
        advance_floodplain(**arrays, area_m2=100., solid_area_m2=60.,
                           allowed_mask=True, spacing_m=10., duration_s=60.)
    for key in arrays:
        assert np.array_equal(arrays[key], originals[key], equal_nan=True)
