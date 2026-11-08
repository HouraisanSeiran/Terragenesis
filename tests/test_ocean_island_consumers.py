"""Public CPU consumer behaviour, including subgrid area and finite topology."""
from argparse import Namespace
import json

import numpy as np
from PIL import Image
import pytest

from terrain_pipeline.ocean_islands import OceanIslandConfig, PlateOceanSource, prepare_ocean_islands
from terrain_pipeline.ocean_island_consumers import connected_ocean, compose_surface, rasterize, sample_td_condition


@pytest.fixture(scope='module')
def source():
    shape = (80, 80)
    return PlateOceanSource(dict(origin_x_m=-800000.,origin_z_m=-800000.,spacing_m=20000.,shape_zx=shape),
        dict(elevation_m=np.full(shape,-4000.),plate_id=np.zeros(shape,dtype=np.int64),
             continental_fraction=np.zeros(shape),ocean_connected=np.ones(shape,dtype=bool),
             velocities_m_per_step=np.array([[1800.,500.]])), 'a'*64, 20261020)


@pytest.fixture(scope='module')
def product(source):
    return prepare_ocean_islands(source,OceanIslandConfig(hotspot_count=5,density='high',arcs=False,ridge=False,
                                                         max_support_radius_m=30000))


def test_composition_preserves_external_base_and_blends_boundary(product):
    feature = next(f for f in product.features if f.kind=='hotspot' and f.stage==0)
    radius = feature.support_radius_m
    x = feature.center_x_m - radius*np.array([0,.99,.999999,1.000001,1.1])
    z = np.full_like(x,feature.center_z_m)
    base = np.full_like(x,-9000.)
    composed = compose_surface(product,x,z,base)
    frozen = product.query(x,z)
    np.testing.assert_allclose(composed['base_elevation_m']+composed['relief_m'],composed['elevation_m'])
    np.testing.assert_array_equal(composed['base_elevation_m'],base)
    np.testing.assert_array_equal(composed['frozen_base_elevation_m'],frozen['base_elevation_m'])
    np.testing.assert_array_equal(composed['frozen_relief_m'],frozen['relief_m'])
    assert not (composed['lagoon']&composed['land']).any()
    assert composed['elevation_m'][0] == pytest.approx(frozen['elevation_m'][0])
    assert composed['elevation_m'][-1] == -9000
    assert abs(composed['elevation_m'][2]-composed['elevation_m'][3]) < .001
    assert composed['land'][0]
    np.testing.assert_array_equal(compose_surface(product,x,z)['elevation_m'],frozen['elevation_m'])


def test_off_centre_subgrid_islands_have_fraction_without_cell_inflation(product):
    grid = rasterize(product,spacing_m=20000,land_supersamples=1)
    off_centre = (~grid.fields['land']) & (grid.land_fraction>0)
    assert off_centre.any()
    assert (grid.land_fraction[off_centre]<1).all()
    assert grid.metadata['refined_cells']>0
    assert set(grid.metadata['feature_ids']) == {f.feature_id for f in product.features}
    assert len(grid.metadata['feature_support_cells'])==len(product.features)
    assert all(row['support_cells_zx'] for row in grid.metadata['feature_support_cells'])
    assert grid.metadata['source_world_seed']==20261020
    assert product.config.world_seed==20260903


def test_fractional_cell_partition_and_direct_query_agree(product):
    bounds=(-777777.,-666666.,-657777.,-552222.)
    grid=rasterize(product,bounds,spacing_m=7000,land_supersamples=2)
    assert grid.ocean_connected is None
    assert grid.cell_area_m2.sum()==pytest.approx((bounds[2]-bounds[0])*(bounds[3]-bounds[1]))
    direct=product.query(grid.x_m[None,:],grid.z_m[:,None])
    np.testing.assert_array_equal(grid.fields['elevation_m'],direct['elevation_m'])
    assert ((grid.land_fraction>=0)&(grid.land_fraction<=1)).all()


def test_split_and_permuted_queries_inherit_same_features(product):
    whole=rasterize(product,(-100000.,-100000.,100000.,100000.),10000,1)
    left=rasterize(product,(-100000.,-100000.,0.,100000.),10000,1)
    right=rasterize(product,(0.,-100000.,100000.,100000.),10000,1)
    np.testing.assert_array_equal(whole.fields['elevation_m'],np.concatenate([left.fields['elevation_m'],right.fields['elevation_m']],axis=1))
    np.testing.assert_array_equal(whole.land_fraction,np.concatenate([left.land_fraction,right.land_fraction],axis=1))
    x,z=np.meshgrid(whole.x_m,whole.z_m)
    order=np.random.default_rng(31).permutation(x.size)
    a=sample_td_condition(product,x,z)['elevation_m'].ravel()
    b=sample_td_condition(product,x.ravel()[order],z.ravel()[order])['elevation_m']
    np.testing.assert_array_equal(a[order],b)


def test_closed_negative_basin_lagoon_and_nonnegative_cells_are_not_ocean():
    h=np.full((9,9),-100.)
    h[2:7,2:7]=10
    h[3:6,3:6]=-5
    h[0,4]=0
    lagoon=np.zeros_like(h,dtype=bool)
    lagoon[0,0]=True
    ocean=connected_ocean(h,lagoon)
    assert ocean[0,1]
    assert not ocean[4,4]
    assert not ocean[0,0]
    assert not ocean[0,4]
    assert not (ocean&(h>=0)).any()


def test_atoll_lagoon_is_preserved_against_positive_external_base(source):
    product=prepare_ocean_islands(source,OceanIslandConfig(hotspot_count=20,density='high',atolls=True,warm_water_scenario=True,arcs=False,ridge=False))
    atoll=next(f for f in product.features if f.kind=='atoll')
    sampled=compose_surface(product,atoll.center_x_m,atoll.center_z_m,1000.)
    assert sampled['lagoon'] and sampled['elevation_m']<0
    radius=atoll.support_radius_m*.4
    bounds=(atoll.center_x_m-radius,atoll.center_z_m-radius,atoll.center_x_m+radius,atoll.center_z_m+radius)
    raster=rasterize(product,bounds,spacing_m=2000,land_supersamples=1)
    assert raster.lagoon_fraction.sum()>0
    assert raster.land_fraction.sum()>0
    assert not ((raster.land_fraction>0)&(raster.land_fraction==1)).all()


def test_td_periodicity_is_explicit_and_finite(product):
    feature=product.features[0]
    x,z=feature.center_x_m,feature.center_z_m
    width=product.source.bounds_m[2]-product.source.bounds_m[0]
    expected=sample_td_condition(product,x,z)
    repeated=sample_td_condition(product,x+width,z,periodic=True)
    assert repeated['elevation_m']==pytest.approx(expected['elevation_m'])
    with pytest.raises(ValueError):
        sample_td_condition(product,x+width,z)


@pytest.mark.parametrize('kwargs',[{'spacing_m':0},{'spacing_m':float('nan')},{'land_supersamples':9},{'area_refinement':0},{'max_cells':2},{'bounds_m':(-1e9,0,0,1)}])
def test_invalid_sampling_is_rejected_before_large_allocation(product,kwargs):
    with pytest.raises(ValueError):
        rasterize(product,**kwargs)


def test_missing_product_and_nonfinite_base_fail(product):
    with pytest.raises(TypeError):
        compose_surface(None,0,0)
    with pytest.raises(ValueError):
        compose_surface(product,0,0,float('nan'))


def test_cli_exports_fixed_mapping_float_source_binding_and_no_overwrite(tmp_path,source,monkeypatch):
    from tools import prepare_ocean_islands as cli
    source_file=tmp_path/'source.npz'
    source_file.write_bytes(b'fixture-source-frozen')
    calls=[]
    def read(path,expected):
        calls.append(expected)
        return source
    monkeypatch.setattr(cli.PlateOceanSource,'from_npz',read)
    args=Namespace(source=source_file,expected_identity=source.identity,out=tmp_path/'run',spacing=200000,
                   supersamples=1,world_seed=20260903,world_type='balanced',density='none',atolls=False,
                   warm_water_scenario=False,no_details=True,gallery=tmp_path/'gallery')
    out=cli.prepare(args)
    manifest=json.loads((out/'delivery_manifest.json').read_text(encoding='utf-8'))
    assert calls==[source.identity]
    assert manifest['source_world_seed']==20261020
    assert manifest['config']['world_seed']==20260903
    assert manifest['exports']['world']['elevation_png_mapping']['zero_code_m']==-8000
    floating=np.load(out/'world_elevation_m.npy')
    codes=np.asarray(Image.open(out/'world_elevation16.png'))
    np.testing.assert_allclose(-8000+codes.astype(float)*16000/65535,floating,atol=16000/65535)
    assert (out/'world_comparison.png').exists()
    gallery=tmp_path/'gallery'/'run'
    assert cli.digest(out/'world_comparison.png')==cli.digest(gallery/'world_comparison.png')
    binding=json.loads((gallery/'image_binding.json').read_text(encoding='utf-8'))
    assert binding['product_identity']==manifest['product_identity']
    with pytest.raises(FileExistsError):
        cli.prepare(args)


@pytest.mark.parametrize('world_type',['multi-continent','pangaea','two-continents','inland-sea'])
def test_cli_preserves_caller_world_names_and_optional_controls(world_type,monkeypatch):
    from tools import prepare_ocean_islands as cli
    seen=[]
    monkeypatch.setattr(cli,'prepare',lambda args:seen.append(args) or 'captured')
    cli.main(['--source','source.npz','--expected-identity','a'*64,'--out','new-run',
              '--world-type',world_type,'--hotspot-count','3','--no-arcs','--no-ridge','--target-ocean-fraction','.7',
              '--volcanic-fraction','.35','--volcanic-lava-strength','.65'])
    assert seen[0].world_type==world_type
    assert seen[0].hotspot_count==3 and seen[0].no_arcs and seen[0].no_ridge
    assert seen[0].target_ocean_fraction==.7
    assert seen[0].volcanic_fraction==.35
    assert seen[0].volcanic_lava_strength==.65


def test_explicit_fine_map_area_budget_and_cli_details(tmp_path,product):
    from tools import prepare_ocean_islands as cli
    feature=next(f for f in product.features if f.kind=='hotspot' and f.stage==0)
    radius=feature.support_radius_m*.35
    bounds=(feature.center_x_m-radius,feature.center_z_m-radius,feature.center_x_m+radius,feature.center_z_m+radius)
    spacing=radius*2/600
    with pytest.raises(ValueError,match='refinement exceeds'):
        rasterize(product,bounds,spacing,1)
    fine=rasterize(product,bounds,spacing,1,area_refinement=2)
    assert fine.fields['elevation_m'].shape==(600,600)
    assert fine.metadata['area_refinement_requested']==2
    assert fine.metadata['area_refinement_used']==2
    assert fine.metadata['refinement_query_points']==600*600*4
    records=cli.detail_exports(tmp_path,product)
    assert 'hotspot' in records and 'representative_chain' in records
    assert records['hotspot']['export']['area_refinement_used']==2
    assert records['hotspot']['export']['refinement_query_points']<=8000000
    assert (tmp_path/'detail_hotspot_comparison.png').is_file()
    assert (tmp_path/'representative_chain_section.png').is_file()


@pytest.mark.parametrize('shape',[(1,1),(1,7),(7,1)])
def test_cli_shading_accepts_single_row_or_column(shape):
    from tools import prepare_ocean_islands as cli
    image=cli.terrain_rgb(np.full(shape,-4000.),2000)
    assert image.shape==shape+(3,)
    assert image.dtype==np.uint8
