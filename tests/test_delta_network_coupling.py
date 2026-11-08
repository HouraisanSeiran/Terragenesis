"""Frozen DEM binding, DAG ownership and cadence continuation behavior."""
import json
import numpy as np
import pytest

from terrain_pipeline.delta_network_coupling import initialize_graph, advance_cadence, model_to_world
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_delta_hydraulic_capacity import HydraulicCapacityRule
from terrain_pipeline.coastal_marine_sediment import MarineConfig
from terrain_pipeline.coastal_delta_evolution import save, load


def fixture():
    bed = np.full((24, 20), 1.)
    bed[17:, :] = -2.
    bed[1:19, 9:12] = -1.
    seeds = np.zeros_like(bed, bool)
    seeds[-1] = True
    site = dict(anchor_world_m=[100., 200.], alpha_deg=45., u0_m=0., v0_m=0.,
                nu=24, nv=20, spacing_m=10.)
    points = [[15., 105.], [75., 105.], [135., 105.], [185., 105.]]
    nodes = [dict(id=i, u_m=p[0], v_m=p[1]) for i,p in enumerate(points)]
    edges = [dict(id=i, **{'from':i,'to':i+1}, path_uv_m=points[i:i+2],
                  width_m=24., depth_m=2., Q_m3s=99999.) for i in range(3)]
    graph = dict(nodes=nodes, edges=edges)
    kwargs = dict(source_identity='frozen-test', source_seed=20261020, algorithm_seed=20260903,
                  hydraulic_config=HydraulicConfig(4.), discharge_m3_s=2.,
                  control_spacing_m=60., geometry_tolerance_m=0., subdivisions=4)
    return graph, bed, site, np.ones_like(bed, bool), seeds, kwargs


def initialize_fixture():
    graph, bed, site, valid, seeds, kwargs = fixture()
    return initialize_graph(graph, bed, site, valid, seeds, **kwargs)


@pytest.mark.parametrize('initial_mobile', [0., 1.])
def test_nearly_dry_branch_does_not_force_microscopic_settling_substeps(initial_mobile):
    from terrain_pipeline.coastal_delta_node_inventory import ChannelInventory
    from terrain_pipeline.coastal_delta_multicell import _budgets
    from terrain_pipeline.coastal_delta_hydraulic_capacity import river_transport
    state, progress = initialize_fixture()
    pool = ChannelInventory(state, progress)
    node = tuple(progress['routes'][0][0])
    pool.add(node, 'mobile_solid_m3', initial_mobile)
    calls = 0

    def length_of(key):
        nonlocal calls
        calls += 1
        assert calls < 100, 'empty dry branch is imposing a microscopic settling step'
        return 720.

    outgoing = {node: [dict(to_zx=[23, 0], discharge_m3_s=7.5e-10)]}
    diag = {}
    before = pool.amount(node, 'bed_solid_m3')
    stage = pool.section_bed(node) + 1.3e-8
    result = river_transport(HydraulicCapacityRule(), pool, state, 0., 60.,
        outgoing, {node: 123.}, {node: stage},
        {node: .035}, length_of, {node: 0.}, _budgets(pool), diag, 2.)
    assert result[2] == 0.
    assert pool.amount(node, 'bed_solid_m3') + pool.amount(node, 'mobile_solid_m3') == pytest.approx(
        before + initial_mobile)
    assert pool.section_bed(node) <= stage + 1e-12
    assert diag[node]['seconds'] == pytest.approx(60.)


def test_distinct_parallel_arms_preserve_both_paths_and_unique_mouth_flow():
    graph,bed,site,valid,seeds,kwargs=fixture()
    upper=[[75.,105.],[105.,65.],[135.,105.]]
    lower=[[75.,105.],[105.,145.],[135.,105.]]
    graph['edges'][1]['path_uv_m']=upper
    graph['edges'].append(dict(graph['edges'][1],id=3,path_uv_m=lower))
    state,progress=initialize_graph(graph,bed,site,valid,seeds,**kwargs)
    assert len(progress['routes'])==2
    assert {tuple(route[-1]) for route in progress['routes']}=={(18,10)}
    coordinates=progress['route_geometry']['nodes']
    # Both bends remain real controls; the parallel edges are not merged or
    # counted twice as mouth outflow after they reconnect.
    assert any(abs(row[2]-65.)<1e-6 for row in coordinates)
    assert any(abs(row[2]-145.)<1e-6 for row in coordinates)
    hydro=progress['river_hydraulics']
    assert hydro['accepted_q_m3_s']==pytest.approx(2.)
    assert sum(row[2] for row in hydro['mouth_q_m3_s'])==pytest.approx(2.,rel=1e-4)
    assert hydro['max_node_residual_m3_s']<1e-4


def total(state):
    return sum(float(getattr(state, f).sum()) for f in
               ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))+state.exported_solid_m3+state.unresolved_solid_m3


def test_frozen_dem_material_and_world_binding():
    graph, bed, site, valid, seeds, kwargs = fixture()
    state, progress = initialize_graph(graph, bed, site, valid, seeds, **kwargs)
    np.testing.assert_allclose(state.bed_m, bed, atol=1e-14, rtol=0)
    assert progress['complex_network']['construction_event_supply_solid_m3'] == 0
    assert progress['complex_network']['source_seed'] != progress['complex_network']['algorithm_seed']
    assert progress['river_hydraulics']['accepted_q_m3_s'] == pytest.approx(2.)
    assert sum(r[2] for r in progress['river_hydraulics']['mouth_q_m3_s']) == pytest.approx(2.)
    assert np.max([r[4] for r in progress['river_hydraulics']['edge_q_m3_s']]) < 3.
    assert all(row[2] <= 1. for row in progress['integrated']['owner_cells'])
    np.testing.assert_allclose(model_to_world(site, [[0., 0.]]), [[100.,200.]])
    from terrain_pipeline.coastal_delta_multicell import _prepare
    _, prepared = _prepare(state, progress)
    assert prepared['hydraulic_sections']['nodes'] == progress['hydraulic_sections']['nodes']


def test_rejects_collapsed_junctions_and_nonmarine_mouth():
    graph, bed, site, valid, seeds, kwargs = fixture()
    graph['nodes'][1].update(u_m=16.)
    with pytest.raises(ValueError, match='collapse'):
        initialize_graph(graph, bed, site, valid, seeds, **kwargs)
    graph, bed, site, valid, seeds, kwargs = fixture()
    seeds[:] = False
    with pytest.raises(ValueError, match='exterior sea'):
        initialize_graph(graph, bed, site, valid, seeds, **kwargs)


def test_interior_control_collision_moves_on_source_without_merging_topology():
    from types import SimpleNamespace
    from terrain_pipeline.delta_network_coupling import _accounts
    points=np.array([[50.,50.],[650.,350.],[650.,-100.]])
    paths=[[[50.,50.],[250.,50.],[650.,350.]],
           [[50.,50.],[290.,70.],[650.,-100.]]]
    graph={'nodes':[dict(id=i,u_m=p[0],v_m=p[1]) for i,p in enumerate(points)],
           'edges':[dict(id=i,**{'from':0,'to':i+1},path_uv_m=p,width_m=40.) for i,p in enumerate(paths)]}
    state=SimpleNamespace(origin_xz_m=(-950.,50.),spacing_m=100.,
        base_bed_m=np.empty((10,20),bool),valid_mask=np.ones((10,20),bool))
    with pytest.raises(ValueError,match='collapse'):
        _accounts(graph,state,1200.,15.,control_cell_search_m=0.)
    placements=[]
    routes,coordinates,widths=_accounts(graph,state,1200.,15.,placements=placements)
    assert len(routes)==2 and len({tuple(r[-1]) for r in routes})==2
    assert len(placements)==1
    assert placements[0]['shift_m']<=100.
    assert placements[0]['local_source_error_m']<=15.
    np.testing.assert_array_equal(coordinates[routes[0][0]],[50.,50.])
    for route,endpoint in zip(routes,points[1:]):
        np.testing.assert_array_equal(coordinates[route[-1]],endpoint[::-1])


def forcing():
    return dict(cadence_s=60., run_id='case', marine_config=MarineConfig(step_s=10.,
        settling_velocity_m_s=.01, material_source='declared test'),
        hydraulic_config=HydraulicConfig(4.), capacity_rule=HydraulicCapacityRule(
            critical_shear_pa=.001, transport_coefficient=.005, settling_velocity_m_s=.01),
        inlet_solid_rate_m3_s=.02)


def test_fixed_cadence_cold_load_equivalence_and_stock(tmp_path):
    state, progress = initialize_fixture()
    full, full_p, _ = advance_cadence(state, progress, 2, **forcing())
    half, half_p, _ = advance_cadence(state, progress, 1, **forcing())
    prefix = str(tmp_path/'checkpoint')
    save(prefix, half, half_p)
    cold, cold_p = load(prefix)
    resumed, resumed_p, _ = advance_cadence(cold, cold_p, 1, **forcing())
    for field in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'):
        np.testing.assert_array_equal(getattr(full, field), getattr(resumed, field))
    assert full_p == resumed_p
    delivered = sum(r['delivered_solid_m3'] for r in full_p['physical_cadence']['reports'])
    assert total(full)-total(state) == pytest.approx(delivered, abs=1e-7)
    reports = full_p['physical_cadence']['reports']
    assert all(sum(m['water_m3'] for m in r['outlet_water']) == pytest.approx(r['delivered_water_m3']) for r in reports)
    assert any(np.any(full.bed_m != state.bed_m) for _ in [0])
    wrong = forcing(); wrong['cadence_s']=30.
    with pytest.raises(ValueError, match='identity'):
        advance_cadence(resumed, resumed_p, 1, **wrong)


@pytest.mark.parametrize('settling_velocity_m_s',[0.,.01])
def test_solid_retention_allows_zero_mouth_and_boundary_export(settling_velocity_m_s):
    from terrain_pipeline.delta_network_coupling import coupled_evidence
    initial,p=initialize_fixture()
    options=forcing()
    options.update(marine_config=MarineConfig(step_s=10.,settling_velocity_m_s=0.,
        export_rate_s=0.,material_source='declared retention behavior test'),
        capacity_rule=HydraulicCapacityRule(critical_shear_pa=1e12,settling_velocity_m_s=settling_velocity_m_s),
        inlet_solid_rate_m3_s=.2)
    result,progress,reports=advance_cadence(initial,p,1,**options)
    report=reports[0]
    assert report['delivered_water_m3']>0.
    assert report['delivered_solid_m3']==pytest.approx(12.)
    if settling_velocity_m_s>0:
        assert report['river_deposited_solid_m3']>0.
    else:
        assert report['river_deposited_solid_m3']==0.
    assert sum(item['gross_solid_m3'] for item in report['outlet_delivery'])==0.
    assert result.exported_solid_m3==0.
    mobile=float(result.mobile_solid_m3.sum())
    assert mobile>0.
    assert mobile+report['river_deposited_solid_m3']==pytest.approx(12.)
    owned=np.zeros(initial.base_bed_m.shape,bool)
    for row in p['integrated']['owner_cells']:
        owned[tuple(row[:2])]=True
    np.testing.assert_array_equal(result.bed_solid_m3[~owned],initial.bed_solid_m3[~owned])
    assert total(result)-total(initial)==pytest.approx(12.,abs=1e-7)
    evidence=coupled_evidence(result,progress)
    assert evidence['channel_exterior_deposition'] is None
    assert evidence['inventory_solid_m3']['mobile_solid_m3']==pytest.approx(mobile)
    assert not evidence['deposition_semantics']['positive_exterior_deposition_required']


def reconnecting_fixture():
    points = np.array([[15.,155.],[75.,155.],[135.,95.],[135.,215.],
                       [195.,155.],[265.,95.],[265.,215.]])
    pairs = [(0,1),(1,2),(1,3),(2,4),(3,4),(4,5),(4,6)]
    bed = np.ones((32,32))
    bed[24:] = -2.
    rr, cc = np.indices(bed.shape)
    uv = np.stack(((rr+.5)*10., (cc+.5)*10.), axis=-1)
    for a,b in pairs:
        vector = points[b]-points[a]
        t = np.clip(np.sum((uv-points[a])*vector, axis=-1)/(vector@vector),0.,1.)
        distance = np.linalg.norm(uv-points[a]-t[...,None]*vector,axis=-1)
        bed[distance < 20.] = -1.
    seeds = np.zeros_like(bed,bool); seeds[-1]=True
    graph = dict(nodes=[dict(id=i,u_m=p[0],v_m=p[1]) for i,p in enumerate(points)],
        edges=[dict(id=i,**{'from':a,'to':b},path_uv_m=points[[a,b]].tolist(),
                    width_m=24.,depth_m=2.,Q_m3s=99999.) for i,(a,b) in enumerate(pairs)])
    _,_,site,_,_,kwargs=fixture()
    site.update(nu=32,nv=32)
    kwargs.update(discharge_m3_s=20., control_spacing_m=85.)
    return initialize_graph(graph,bed,site,np.ones_like(bed,bool),seeds,**kwargs)


def test_reconnecting_dag_actual_mouth_water_and_offshore_bed_receipt():
    state,p=reconnecting_fixture()
    unique={(tuple(a),tuple(b)) for r in p['routes'] for a,b in zip(r,r[1:])}
    hydraulic=p['river_hydraulics']
    assert len(hydraulic['edge_q_m3_s']) == len(unique)
    assert len(hydraulic['mouth_q_m3_s']) == 2
    assert len(p['routes']) <= 4
    options=forcing()
    options.update(cadence_s=600.,marine_config=MarineConfig(step_s=120.,
        settling_velocity_m_s=.01,material_source='declared bifurcating test'),
        inlet_solid_rate_m3_s=.2)
    result,progress,reports=advance_cadence(state,p,2,**options)
    owned=np.zeros(state.bed_m.shape,bool)
    for row in p['integrated']['owner_cells']:
        owned[tuple(row[:2])]=True
    offshore=(~owned)&state.valid_mask&(state.bed_m<0.)
    assert np.max((result.bed_solid_m3-state.bed_solid_m3)[offshore]) > 0.
    assert all(len(report['outlet_water']) == 2 for report in reports)
    assert all(sum(m['water_m3'] for m in report['outlet_water']) == pytest.approx(
        report['delivered_water_m3'],rel=1e-7) for report in reports)
    assert sum(len(report['outlet_delivery']) for report in reports)>0
    assert any(report['entrained_solid_m3']>0 for report in reports)
    assert any(row[2] != before[2] for row,before in zip(progress['hydraulic_sections']['nodes'],
        p['hydraulic_sections']['nodes']))
    assert total(result)-total(state) == pytest.approx(sum(r['delivered_solid_m3'] for r in reports),abs=1e-6)


def test_frozen_product_hashes_and_construction_separate_from_event_supply(tmp_path,monkeypatch):
    from terrain_pipeline.delta_network_coupling import load_frozen_product, coupled_evidence, file_sha256
    graph,bed,site,valid,seeds,kwargs=fixture()
    graph['nodes'][0]['Q_m3s']=2.
    manifest=dict(site=site,world_seed=20260903,source_world_seed=20261020,
                  declaration='declared test initial geology',td_source={'identity':'frozen TD test'})
    for name,value in [('manifest.json',manifest),('channel_graph.json',graph)]:
        (tmp_path/name).write_text(json.dumps(value),encoding='utf-8')
    for name,value in [('bed_dem_float64.npy',bed),('valid_mask.npy',valid),
                       ('td_ocean_mask.npy',bed<0),('td_original_bed_m.npy',bed)]:
        np.save(tmp_path/name,value)
    sums={p.name:file_sha256(p) for p in tmp_path.iterdir()}
    (tmp_path/'sha256sums.json').write_text(json.dumps(sums),encoding='utf-8')
    state,p=load_frozen_product(tmp_path,hydraulic_config=kwargs['hydraulic_config'],
        control_spacing_m=60.,geometry_tolerance_m=0.)
    assert p['complex_network']['frozen_product']['td_source']==manifest['td_source']
    assert p['complex_network']['frozen_product']['unknown_cells']==0
    assert p['complex_network']['frozen_product']['construction_reference_mode']=='historical declared-shelf fallback'
    assert p['complex_network']['frozen_product']['construction_reference']=='TD land plus saved declared shelf parameters'
    assert p['complex_network']['construction_event_supply_solid_m3']==0.
    assert coupled_evidence(state,p)['solid_residual_m3']==0.
    import sys
    from tools.run_delta_network_coupled import main
    output=tmp_path/'physical'
    monkeypatch.setattr(sys,'argv',['run_delta_network_coupled.py','--source',str(tmp_path),
        '--out',str(output),'--q','20','--stage-limit','4','--control-spacing','60',
        '--geometry-tolerance','0','--ticks','2','--cadence','600','--marine-step','120',
        '--solid-rate','.2','--verify-restart'])
    main()
    evidence=json.loads((output/'physical-report.json').read_text(encoding='utf-8'))
    assert evidence['continuation']['tested']
    assert evidence['continuation']['progress_equal']
    assert all(evidence['continuation']['arrays_bitwise_equal'].values())
    exterior=evidence['channel_exterior_deposition']
    assert exterior['rise_m']>0.
    assert exterior['receiver_classification'].startswith('unclassified')
    assert evidence['offshore_deposition']==exterior
    assert 'deprecated compatibility alias' in evidence['deposition_semantics']['offshore_deposition']
    assert not evidence['deposition_semantics']['positive_exterior_deposition_required']
    assert abs(evidence['solid_residual_m3'])<1e-6
    assert (output/'checkpoint.npz').exists()
    (tmp_path/'manifest.json').write_text(json.dumps(manifest)+' ',encoding='utf-8')
    with pytest.raises(ValueError,match='hash'):
        load_frozen_product(tmp_path,hydraulic_config=kwargs['hydraulic_config'])


def test_saved_td_construction_reference_controls_ledger_and_source_identity(tmp_path,monkeypatch):
    from terrain_pipeline.delta_network_coupling import load_frozen_product,file_sha256
    from terrain_pipeline import delta_network_site
    graph,bed,site,valid,seeds,kwargs=fixture()
    graph['nodes'][0]['Q_m3s']=2.
    reference=bed.copy()
    reference[3,4]-=2.
    reference[3,5]+=3.
    reference_metadata={'file':'construction_reference_bed_m.npy',
        'semantics':'Original saved TD topography and bathymetry before geological construction; no replacement shelf.'}
    manifest=dict(site=site,world_seed=20260903,source_world_seed=20261020,
                  construction_reference=reference_metadata)
    for name,value in [('manifest.json',manifest),('channel_graph.json',graph)]:
        (tmp_path/name).write_text(json.dumps(value),encoding='utf-8')
    for name,value in [('bed_dem_float64.npy',bed),('valid_mask.npy',valid),
        ('td_ocean_mask.npy',bed<0),('td_original_bed_m.npy',reference),
        ('construction_reference_bed_m.npy',reference)]:
        np.save(tmp_path/name,value)
    sums={path.name:file_sha256(path) for path in tmp_path.iterdir()}
    (tmp_path/'sha256sums.json').write_text(json.dumps(sums),encoding='utf-8')
    def reject_shelf_reconstruction(*args,**kwargs):
        pytest.fail('an explicit saved reference must not reconstruct a declared shelf')
    monkeypatch.setattr(delta_network_site,'base_surface',reject_shelf_reconstruction)
    options=dict(hydraulic_config=kwargs['hydraulic_config'],control_spacing_m=60.,geometry_tolerance_m=0.)
    state,p=load_frozen_product(tmp_path,**options)
    info=p['complex_network']['frozen_product']
    assert info['construction_reference']==reference_metadata['semantics']
    assert info['construction_reference_metadata']==reference_metadata
    assert info['construction_reference_mode']=='explicit saved array'
    assert info['construction_fill_bulk_m3']==pytest.approx(200.)
    assert info['construction_cut_bulk_m3']==pytest.approx(300.)
    assert info['construction_fill_solid_m3']==pytest.approx(120.)
    assert info['construction_cut_solid_m3']==pytest.approx(180.)
    assert info['files_sha256']['construction_reference_bed_m.npy']==sums['construction_reference_bed_m.npy']
    assert info['declared_shelf_cells'] is None
    reference[4,4]+=1.
    np.save(tmp_path/'construction_reference_bed_m.npy',reference)
    with pytest.raises(ValueError,match='hash'):
        load_frozen_product(tmp_path,**options)
    sums['construction_reference_bed_m.npy']=file_sha256(tmp_path/'construction_reference_bed_m.npy')
    (tmp_path/'sha256sums.json').write_text(json.dumps(sums),encoding='utf-8')
    changed,changed_p=load_frozen_product(tmp_path,**options)
    assert changed.source_identity!=state.source_identity
    assert changed_p['complex_network']['frozen_product']['construction_cut_bulk_m3']==pytest.approx(400.)
