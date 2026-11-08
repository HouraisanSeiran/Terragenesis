import math
import hashlib
import numpy as np
import pytest
from terrain_pipeline.mountain_forms import AdvancedFilterConfig, filter_height, MAX_SAMPLES


def run(x, z, seed=20260903, config=None, target=0.2):
    return filter_height(x, z, 1000, .4, -.2, target, world_seed=seed, config=config)


def scalar_one_octave(x, z, sx, sz, target, seed, c):
    # Independent scalar transcription of upstream Hash2, Phacelle and filter.
    seed = int.from_bytes(hashlib.sha256(f'advanced-terrain-filter-v1:{seed}:phacelle'.encode()).digest()[:4], 'little') % 1000000
    x, z = x/c.wavelength_m, z/c.wavelength_m
    sx, sz = sx*c.wavelength_m/c.amplitude_m, sz*c.wavelength_m/c.amplitude_m
    length = max(math.hypot(sx, sz), 1e-10)
    gx = sx*(1-c.assumed_slope[1])+sx/length*c.assumed_slope[0]*c.assumed_slope[1]
    gz = sz*(1-c.assumed_slope[1])+sz/length*c.assumed_slope[0]*c.assumed_slope[1]
    norm = math.hypot(gx,gz)
    dx, dz = (gx/norm,gz/norm) if norm > 1e-10 else (0,0)
    side_x, side_z = -dz*c.cell_scale*math.tau, dx*c.cell_scale*math.tau
    kx, kz = 1/math.pi, math.exp(-1)
    co = si = total = 0.0
    ix, iz = math.floor(x), math.floor(z)
    for i in (-1,0,1,2):
        for j in (-1,0,1,2):
            a = (ix+i+seed*.06711056)*kx+kz
            b = (iz+j+seed*.00583715)*kz+kx
            q = a*b*(a+b); t = q-math.floor(q)
            a,b = 16*kx*t,16*kz*t
            hx,hz = -1+2*(a-math.floor(a)),-1+2*(b-math.floor(b))
            rx,rz = x-ix-i-hx*.5,z-iz-j-hz*.5
            weight = max(0, math.exp(-2*(rx*rx+rz*rz))-.01111)
            phase = rx*side_x+rz*side_z+math.pi*.5
            co += math.cos(phase)*weight; si += math.sin(phase)*weight; total += weight
    co,si = co/total,si/total
    magnitude = max(1-c.normalization, math.hypot(co,si))
    co,si = co/magnitude,si/magnitude
    r,o = c.rounding,c.onset
    rounding = (r[1]+(r[0]-r[1])*max(0,min(1,target+.5)))*r[2]
    t,s = length*o[0],rounding*o[0]
    smooth = t-.5*s if t >= s else .5*t*t/s
    mask = 1-(1-max(0,min(1,smooth)))**2
    layer = target*(1-mask)+co*c.gully_weight*mask
    dx_delta = si*(-side_x)*c.gully_weight*mask
    dz_delta = si*(-side_z)*c.gully_weight*mask
    rm = 1-(1-max(0,min(1,length*o[2])))**2
    rt = target*(1-rm)+co*rm
    rm *= 1-(1-max(0,min(1,abs(si)*o[3])))**2
    return layer*c.amplitude_m, (sx+dx_delta)*c.amplitude_m/c.wavelength_m, (sz+dz_delta)*c.amplitude_m/c.wavelength_m, rt*(1-rm)


@pytest.mark.parametrize('x,z,sx,sz,target', [(123,456,.4,-.2,.3),(-333,900,.02,.04,-.8),(25,-740,0,0,-1)])
def test_one_octave_scalar_reference(x,z,sx,sz,target):
    c=AdvancedFilterConfig(octaves=1, hash_mode='upstream')
    out=filter_height(x,z,500,sx,sz,target,world_seed=42,config=c)
    expected=scalar_one_octave(x,z,sx,sz,target,42,c)
    assert np.allclose([out['delta_m'],out['artistic_slope_x'],out['artistic_slope_z'],out['ridge_map']],expected,rtol=1e-12,atol=1e-12)


def test_point_chunk_order_seed_and_zero():
    x=np.linspace(-4000,4000,35); z=np.linspace(2000,-2500,35)
    all_values=run(x,z)
    for key in all_values:
        assert np.array_equal(all_values[key],np.concatenate([run(x[:12],z[:12])[key],run(x[12:],z[12:])[key]]))
        assert np.array_equal(all_values[key],np.array([run(a,b)[key] for a,b in zip(x,z)]))
        assert np.array_equal(all_values[key],run(x[::-1],z[::-1])[key][::-1])
    assert np.any(all_values['height_m'] != run(x,z,seed=1)['height_m'])
    zero=run(x,z,config=AdvancedFilterConfig(amplitude_m=0))
    assert np.array_equal(zero['height_m'],np.full(x.shape,1000.))
    assert np.array_equal(zero['delta_m'],np.zeros_like(x))


def test_flat_structural_target_sign():
    c=AdvancedFilterConfig(octaves=1)
    for target in (-1,1):
        out=filter_height(15,99,0,0,0,target,world_seed=4,config=c)
        assert out['delta_m'] == pytest.approx(target*c.amplitude_m)


@pytest.mark.parametrize('boundary',[-3600.,-1800.,-900.,-450.,450.,900.,1800.,3600.])
@pytest.mark.parametrize('axis',[0,1])
def test_boundaries_are_continuous(boundary,axis):
    pos=boundary+np.array([-1.,0.,1.])*1e-4
    a=run(pos,111) if axis==0 else run(111,pos)
    assert abs(a['height_m'][2]-a['height_m'][0]) < .01
    assert abs((a['height_m'][2]-2*a['height_m'][1]+a['height_m'][0])/1e-4) < .01


def test_validation():
    for x,z,seed in [(np.empty(0),0,1),(np.zeros((MAX_SAMPLES//2+1,1)),np.zeros((1,2)),1),(1e9+1,0,1),(0,0,-1),(0,0,2**64)]:
        with pytest.raises(ValueError): run(x,z,seed=seed)
    with pytest.raises(ValueError): run(0,0,target=1.01)
    with pytest.raises(ValueError): run(0,0,config=AdvancedFilterConfig(lacunarity=0))

@pytest.mark.parametrize('origin', [2_200_000, -2_200_000, 900_000_000, -900_000_000])
def test_stable_hash_varies_at_far_lattice_cells(origin):
    from terrain_pipeline.mountain_forms import _stable_hash2
    x = np.arange(origin, origin + 100, dtype=np.int64)
    a, b = _stable_hash2(x, x + 18, 13)
    c, d = _stable_hash2(x, x + 18, 14)
    assert np.ptp(a) > 1.5 and np.ptp(b) > 1.5
    assert np.unique(a).size == 100 and np.unique(b).size == 100
    assert np.any(a != c) and np.any(b != d)


def test_tiny_amplitude_and_smooth_start_are_safe():
    from terrain_pipeline.mountain_forms import _smooth_start
    with pytest.raises(ValueError, match='at least'):
        run(0, 0, config=AdvancedFilterConfig(amplitude_m=1e-300))
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        assert np.array_equal(_smooth_start(np.array([1e300, 0.5]), np.array([0.0, 1.0])), np.array([1e300, 0.125]))
        result = run(0, 0, config=AdvancedFilterConfig(amplitude_m=0.001))
        assert all(np.isfinite(v) for v in result.values())
    with pytest.raises(ValueError, match='hash_mode'):
        run(0, 0, config=AdvancedFilterConfig(hash_mode='unknown'))
