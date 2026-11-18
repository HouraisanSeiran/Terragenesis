"""Deterministic coarse-to-fine selection and explicit bounded solver dispatch."""
import hashlib
import json

import numpy as np

from terrain_pipeline.common_infra import identity, json_sha256


def boundary_package(product, region, terrain_identity, *, duration_s=30.):
    """Export one representative event, distinct from generation exposure.

    Coarse discharge already includes upstream water. It is injected once at
    the reach inlet, with no second accumulation of upstream local runoff.
    Sediment rate is the actually transported generation solid divided by its
    declared equivalent exposure, rather than an invented concentration.
    """
    if not np.isfinite(duration_s) or not 0 < duration_s <= 300.:
        raise ValueError('detail representative interval must be within 0..300 seconds')
    a, m = product['arrays'], product['metadata']
    node = int(region['node'])
    if node < 0 or node >= a['elevation_m'].size:
        raise ValueError('region node outside coarse support')
    q = float(a['discharge_m3_s'].ravel()[node])
    exposure = m['config']['shaping_rounds'] * m['config']['equivalent_exposure_seconds']
    solid_rate = float(a['generation_transported_solid_m3'].ravel()[node]) / exposure
    package = dict(schema='world-detail-boundary-v1', source_identity=m['source_identity'],
        coarse_product_identity=product.get('identity', identity(a, m)), terrain_identity=terrain_identity,
        support_id=region['coarse_support_id'], node=node, mode='replace-coarse-support',
        interval_start_s=0., interval_end_s=float(duration_s), water_m3=q*duration_s,
        solid_m3=solid_rate*duration_s, discharge_m3_s=q,
        supply_semantics='representative event from coarse final annual discharge and generation mean transported solid rate',
        upstream_accounting='all upstream supplied once at native inlet; no additional upstream injection')
    package['id'] = json_sha256(package)
    return package


def validate_boundary(package, *, source_identity, terrain_identity):
    if package.get('schema') != 'world-detail-boundary-v1' or package.get('id') != json_sha256({k:v for k,v in package.items() if k != 'id'}):
        raise ValueError('boundary package identity mismatch')
    if package['source_identity'] != source_identity or package['terrain_identity'] != terrain_identity:
        raise ValueError('detail boundary source or terrain mismatch')
    if package.get('mode') != 'replace-coarse-support':
        raise ValueError('detail requires explicit coarse replacement support')
    values = [package[k] for k in ('water_m3','solid_m3','interval_start_s','interval_end_s')]
    if not np.isfinite(values).all() or min(values[:3]) < 0 or values[3] <= values[2]:
        raise ValueError('invalid finite boundary interval or inventory')


def load_native_terrain(entry, *, source_identity, world_seed=None, island_provenance=None):
    """Verify a saved local30 source. Reading never starts a model."""
    from pathlib import Path
    from terrain_pipeline.common_infra import file_sha256
    path = Path(entry['manifest_path'])
    if file_sha256(path) != entry['manifest_sha256']:
        raise ValueError('TD manifest SHA mismatch')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    calculated = json_sha256({k:v for k,v in manifest.items() if k not in ('identity','source_path')})
    if manifest.get('identity') != calculated or not manifest.get('ready'):
        raise ValueError('TD manifest identity or readiness mismatch')
    if manifest.get('schema') != 'terragenesis-local30-v1' or manifest.get('plate_identity') != source_identity:
        raise ValueError('native TD belongs to another world source')
    if world_seed is not None and manifest.get('world_seed') != world_seed:
        raise ValueError('native TD world seed differs')
    if island_provenance is not None and manifest.get('island_provenance') != island_provenance:
        raise ValueError('native TD island provenance differs')
    grid = manifest['grid']
    if grid['spacing_m'] != 30. or tuple(grid['shape_zx']) != (513,513):
        raise ValueError('native TD must retain its declared 513 x 513, 30m grid')
    spec = manifest['layers']['elevation_m']
    elevation_path = (path.parent/spec['file']).resolve()
    if not elevation_path.is_relative_to(path.parent.resolve()) or file_sha256(elevation_path) != spec['sha256']:
        raise ValueError('TD elevation path or SHA mismatch')
    bed = np.load(elevation_path, mmap_mode='r', allow_pickle=False)
    if bed.shape != (513,513) or bed.dtype != np.float32 or not np.isfinite(bed).all():
        raise ValueError('native TD array header or data mismatch')
    return dict(elevation_m=bed, grid=grid, identity=calculated, manifest=manifest,
                binding=dict(manifest_path=str(path.resolve()), manifest_sha256=entry['manifest_sha256']))


def solve_native_reach(product, region, terrain, *, config=None):
    """Solve native downhill flow or an explicitly closed short storage event.

    Adverse slopes retain raw TD and use the 2D signed-face finite-volume
    adapter. It does not claim a complete seasonal/downstream solution.
    """
    from terrain_pipeline import drainage
    from terrain_pipeline.channel_geometry import ChannelNetwork, ChannelForcing, ChannelConfig
    from terrain_pipeline.surface_hydraulics import solve_channel
    from terrain_pipeline.surface_rivers.metric_sediment import (
        MaterialParameters, SedimentConfig, SedimentDomain, SedimentForcing, solve_sediment)
    cfg = config or {}
    bed = np.asarray(terrain['elevation_m'],np.float64)
    first = terrain['grid']['first_sample_xz_m']
    spacing = terrain['grid']['spacing_m']
    x,z = region['location_xz_m']
    col,row = int(round((x-first[0])/spacing)),int(round((z-first[1])/spacing))
    if not 0 <= row < bed.shape[0] or not 0 <= col < bed.shape[1]:
        raise ValueError('selected location lies outside prepared native TD tile')
    from terrain_pipeline.ocean_island_consumers import connected_ocean
    from terrain_pipeline.world_process_backwater import solve_native_backwater
    sea = connected_ocean(bed)
    coarse_lake = np.asarray(product['arrays'].get('lake_id', np.zeros_like(product['arrays']['elevation_m'])))
    if region['kind'] == 'lake_port' or coarse_lake.ravel()[region['node']] > 0 or sea[row,col]:
        return solve_native_backwater(product, region, terrain, config=cfg)
    outlets = sea.copy()
    outlets[[0,-1],:] = True
    outlets[:,[0,-1]] = True
    mesh = drainage.grid_mesh(bed.shape,x0_m=first[0],z0_m=first[1],dx_m=spacing,
                              world_seed=int(product['metadata']['world_seed']))
    route = drainage.route_graph(bed,outlets,mesh)
    path = []
    node = row*bed.shape[1]+col
    limit = min(2048,int(cfg.get('max_detail_nodes',256)))
    while node >= 0 and len(path)<limit:
        path.append(node)
        target = int(route.receiver[node])
        if target < 0:
            break
        if bed.ravel()[node] <= bed.ravel()[target]:
            break
        node = target
    if len(path) < 2:
        return solve_native_backwater(product, region, terrain, config=cfg)
    last = path[-1]
    downstream = int(route.receiver[last])
    if downstream < 0 or bed.ravel()[downstream] >= bed.ravel()[last]:
        return solve_native_backwater(product, region, terrain, config=cfg)
    coarse = product['arrays'];m=product['metadata'];cspacing=m['spacing_m'];cfirst=m['first_xz_m']
    lx = int(round((mesh.node_x_m[last]-cfirst[0])/cspacing))
    lz = int(round((mesh.node_z_m[last]-cfirst[1])/cspacing))
    if not 0 <= lx < coarse['elevation_m'].shape[1] or not 0 <= lz < coarse['elevation_m'].shape[0]:
        raise ValueError('native downstream boundary outside known coarse routing')
    coarse_last = lz*coarse['elevation_m'].shape[1]+lx
    coarse_receiver = np.asarray(coarse.get('receiver',[])).ravel()
    if coarse_receiver.size != coarse['elevation_m'].size or coarse_receiver[coarse_last] < 0:
        raise ValueError('explicit known coarse downstream continuation required for normal-flow boundary')
    if np.asarray(coarse.get('lake_id',np.zeros_like(coarse['elevation_m']))).ravel()[coarse_last] > 0:
        return solve_native_backwater(product, region, terrain, config=cfg)
    boundary = dict(kind='coarse-supported-normal-flow',coarse_node=coarse_last,
        coarse_receiver=int(coarse_receiver[coarse_last]),native_downstream_node=downstream,
        semantics='truncated downhill reach with declared normal-flow continuation; not ocean or external land outlet')
    selected = np.asarray(path,np.int64)
    heights = bed.ravel()[selected].copy()
    distance = np.hypot(np.diff(mesh.node_x_m[selected]),np.diff(mesh.node_z_m[selected]))
    if np.any(np.diff(heights)>=0):
        raise ValueError('unsupported native backwater or lake connection')
    lengths = np.r_[distance,distance[-1]]
    slopes = np.r_[-np.diff(heights)/distance,(heights[-2]-heights[-1])/distance[-1]]
    n = len(selected)
    receiver = np.r_[np.arange(1,n,dtype=np.int64),np.int64(-1)]
    package = boundary_package(product,region,terrain['identity'],duration_s=cfg.get('detail_duration_s',30.))
    validate_boundary(package,source_identity=product['metadata']['source_identity'],terrain_identity=terrain['identity'])
    q = package['discharge_m3_s']
    if q <= 0:
        raise ValueError('no water available in coarse boundary')
    width = np.full(n,max(1.,min(200.,4*np.sqrt(q))))
    roughness = np.full(n,float(product['metadata']['config']['roughness']))
    # Each inlet uses the single coarse package; intermediate nodes add no
    # duplicate upstream water. Initially dry channels are an explicit event.
    geom_id = identity(dict(node=selected,bed_m=heights,width_m=width),dict(terrain=terrain['identity'],support=region['id']))
    kind = np.full(n,'interior',dtype='U24');kind[-1]='open_outflow'
    network = ChannelNetwork(receiver,lengths,width,heights,slopes,roughness,np.full(n,100.),
                             kind,geom_id,'native TD bed, declared formative rectangular width',
                             'coarse world Manning roughness',np.r_[distance,0.])
    duration = package['interval_end_s']-package['interval_start_s']
    forcing_q = np.zeros((1,n));forcing_q[0,0]=q
    forcing = ChannelForcing(np.array([0.,duration]),forcing_q,package['id'])
    hydraulic = solve_channel(network,forcing,np.zeros(n),ChannelConfig(max_dt_seconds=1.,max_steps=100000))
    if hydraulic['metadata']['status']!='complete':
        raise ValueError('unsupported detailed hydraulic prefix: '+str(hydraulic['metadata'].get('failure_reason')))
    coarse = product['arrays'];m=product['metadata'];cspacing=m['spacing_m'];cfirst=m['first_xz_m']
    ix = np.rint((mesh.node_x_m[selected]-cfirst[0])/cspacing).astype(int)
    iz = np.rint((mesh.node_z_m[selected]-cfirst[1])/cspacing).astype(int)
    if np.any((ix<0)|(ix>=coarse['elevation_m'].shape[1])|(iz<0)|(iz>=coarse['elevation_m'].shape[0])):
        raise ValueError('native support extends outside known coarse world')
    coarse_nodes = iz*coarse['elevation_m'].shape[1]+ix
    porosity = float(np.mean(np.asarray(coarse.get('porosity',np.full(coarse['elevation_m'].shape,.35))).ravel()[coarse_nodes]))
    erodibility = float(np.mean(np.asarray(coarse.get('erodibility',np.full(coarse['elevation_m'].shape,.5))).ravel()[coarse_nodes]))
    material = MaterialParameters(porosity=porosity,sediment_erodibility_m_s_pa=1e-6*erodibility,
        rock_erodibility_m_s_pa=1e-8*erodibility,provenance='source-bound coarse geological material, support mean')
    area = width*lengths
    loose_density = np.asarray(coarse['loose_solid_m3']).ravel()[coarse_nodes]/cspacing**2
    initial_alluvium = loose_density*area/(1-porosity)
    reserve = float(m['config']['rock_reserve_m'])
    domain = SedimentDomain(receiver,area,width,heights,heights-reserve,initial_alluvium,
        np.zeros(n,bool),receiver<0,geom_id,material.provenance)
    h=hydraulic['arrays'];dt=np.diff(h['time_seconds'])
    external=np.zeros_like(h['outflow_q_m3_s'])
    external[:,0]=package['solid_m3']/duration
    sf=SedimentForcing(h['time_seconds'],h['volume_m3'][:-1],h['depth_m'][:-1],h['outflow_q_m3_s'],
        np.broadcast_to(slopes,h['outflow_q_m3_s'].shape).copy(),external,
        identity(h,hydraulic['metadata']),geom_id,'single coarse boundary water and transported-solid event')
    sediment=solve_sediment(domain,sf,material,np.zeros(n),SedimentConfig(max_dt_seconds=.5,max_steps=20000,max_bed_change_m=.05))
    if sediment['metadata']['status']!='complete':
        raise ValueError('unsupported detailed sediment prefix: '+str(sediment['metadata'].get('failure_reason')))
    s=sediment['arrays'];delta=s['trace_bed_elevation_m'][-1]-heights
    support=np.unique(coarse_nodes)
    replacement=[]
    loose_replacement=[]
    rock_replacement=[]
    erosion_replacement=[]
    deposition_replacement=[]
    mobile_replacement=[]
    event_fraction=min(1.,duration/(m['config']['shaping_rounds']*m['config']['equivalent_exposure_seconds']))
    reversed_rock=0.
    reversed_loose_change=0.
    reversed_mobile=0.
    for coarse_node in support:
        use=coarse_nodes==coarse_node
        fraction=min(1.,float(area[use].sum()/cspacing**2))
        coarse_change=(coarse['elevation_m'].ravel()[coarse_node]-coarse.get('shaping_initial_elevation_m',coarse['initial_elevation_m']).ravel()[coarse_node])*fraction*event_fraction
        detailed_change=float(np.sum(delta[use]*area[use])/cspacing**2)
        replacement.append(coarse['elevation_m'].ravel()[coarse_node]-coarse_change+detailed_change)
        coarse_erosion=float(np.asarray(coarse.get('erosion_m',np.zeros_like(coarse['elevation_m']))).ravel()[coarse_node])
        coarse_deposition=float(np.asarray(coarse.get('deposition_m',np.zeros_like(coarse['elevation_m']))).ravel()[coarse_node])
        fine_erosion=float(s['step_bulk_erosion_m3'][:,use].sum()/cspacing**2)
        fine_deposition=float(s['step_bulk_deposition_m3'][:,use].sum()/cspacing**2)
        erosion_replacement.append(coarse_erosion*(1-fraction*event_fraction)+fine_erosion)
        deposition_replacement.append(coarse_deposition*(1-fraction*event_fraction)+fine_deposition)
        initial_native_loose=initial_alluvium[use].sum()*(1-porosity)
        final_native_loose=s['trace_bed_alluvium_solid_m3'][-1,use].sum()
        old_loose=float(coarse['loose_solid_m3'].ravel()[coarse_node])
        original_loose=float(np.asarray(coarse.get('shaping_initial_loose_solid_m3',coarse.get('initial_loose_solid_m3',coarse['loose_solid_m3']))).ravel()[coarse_node])
        loose_replacement.append(old_loose-(old_loose-original_loose)*fraction*event_fraction+
                                 final_native_loose-initial_native_loose)
        old_rock=float(np.asarray(coarse.get('rock_removed_m3',np.zeros_like(coarse['elevation_m']))).ravel()[coarse_node])
        original_rock=float(np.asarray(coarse.get('shaping_initial_rock_removed_m3',np.zeros_like(coarse['elevation_m']))).ravel()[coarse_node])
        rock_replacement.append(old_rock-(old_rock-original_rock)*fraction*event_fraction+float(s['trace_rock_removed_m3'][-1,use].sum()))
        old_mobile=float(np.asarray(coarse.get('mobile_solid_m3',np.zeros_like(coarse['elevation_m']))).ravel()[coarse_node])
        mobile_replacement.append(old_mobile*(1-fraction*event_fraction)+float(s['trace_mobile_solid_m3'][-1,use].sum()))
        reversed_rock+=(old_rock-original_rock)*fraction*event_fraction
        reversed_loose_change+=(old_loose-original_loose)*fraction*event_fraction
        reversed_mobile+=old_mobile*fraction*event_fraction
    water_input=float(np.sum(h['local_q_m3_s']*np.diff(h['time_seconds'])[:,None]))
    water_output=float(h['boundary_outflow_volume_m3'].sum())
    water_storage=float(h['volume_m3'][-1].sum()-h['volume_m3'][0].sum())
    solid_initial=float(s['initial_mobile_solid_m3'].sum()+s['trace_bed_alluvium_solid_m3'][0].sum())
    solid_external=float(s['step_external_solid_m3'].sum())
    solid_rock=float(s['step_eroded_rock_m3'].sum())
    solid_final=float(s['trace_mobile_solid_m3'][-1].sum()+s['trace_bed_alluvium_solid_m3'][-1].sum())
    solid_export=float(s['step_exported_solid_m3'].sum())
    return dict(status='complete',kind=region['kind'],region_id=region['id'],source_identity=m['source_identity'],
        terrain_identity=terrain['identity'],terrain_binding=terrain['binding'],boundary_package=package,
        downstream_boundary=boundary,
        replacement_accounting=dict(reversed_rock_removed_m3=reversed_rock,
            reversed_loose_change_solid_m3=reversed_loose_change,reversed_mobile_solid_m3=reversed_mobile,
            coarse_support_transfer_reversal_solid_m3=reversed_rock-reversed_loose_change-reversed_mobile,
            semantics='signed reversal of the coarse support transfer for the replaced area/time; not a marine outlet'),
        replaces_support_id=region['coarse_support_id'],consumed_package_id=package['id'],
        support_indices=support, replacement_arrays=dict(elevation_m=np.asarray(replacement),
            loose_solid_m3=np.asarray(loose_replacement),rock_removed_m3=np.asarray(rock_replacement),
            mobile_solid_m3=np.asarray(mobile_replacement),
            erosion_m=np.asarray(erosion_replacement),deposition_m=np.asarray(deposition_replacement)),
        native_arrays=dict(node=selected,node_x_m=mesh.node_x_m[selected],node_z_m=mesh.node_z_m[selected],
            initial_bed_m=heights,final_bed_m=s['trace_bed_elevation_m'][-1],area_m2=area),
        hydraulic=hydraulic,sediment=sediment,
        budgets=dict(boundary_water_m3=package['water_m3'],solver_water_input_m3=water_input,
            solver_water_export_m3=water_output,solver_water_storage_change_m3=water_storage,
            water_residual_m3=water_input-water_output-water_storage,
            boundary_solid_m3=package['solid_m3'],solver_external_solid_m3=solid_external,
            initial_alluvium_and_mobile_solid_m3=solid_initial,eroded_rock_m3=solid_rock,
            final_alluvium_and_mobile_solid_m3=solid_final,exported_solid_m3=solid_export,
            solid_residual_m3=solid_initial+solid_external+solid_rock-solid_final-solid_export,
            coarse_equivalent_event_fraction=event_fraction),
        limitations=['representative short event; not a full seasonal detailed solve',
            'fixed hydraulic trace; sediment bed changes require subsequent hydraulic revalidation',
            'only the matching representative fraction of coarse equivalent process is replaced over actual rectangular support area; other generation history remains',
            'native TD absolute height retained separately; coarse seasonal inventories are separate from the representative event'])


def select_regions(source, arrays, config=None):
    config = config or {}
    shape = np.asarray(arrays['elevation_m']).shape
    rec = np.asarray(arrays['receiver']).ravel()
    area = np.asarray(arrays['drainage_area_m2']).ravel()
    discharge = np.asarray(arrays['discharge_m3_s']).ravel()
    ocean = np.asarray(source['ocean_mask']).ravel()
    lake = np.asarray(arrays['lake_id']).ravel()
    spacing = float(source['spacing_m'])
    first = source['first_xz_m']
    selected = []
    occupied = set()
    candidates = {'river_reach': [], 'lake_port': [], 'river_mouth': []}
    for cell in np.flatnonzero((discharge > 0) & ~ocean & (rec >= 0)):
        target = rec[cell]
        if ocean[target]:
            kind = 'river_mouth'
        elif lake[cell] > 0 and lake[target] != lake[cell]:
            kind = 'lake_port'
        elif lake[cell] == 0:
            kind = 'river_reach'
        else:
            continue
        z, x = divmod(int(cell), shape[1])
        location = [first[0] + x * spacing, first[1] + z * spacing]
        identifier = hashlib.sha256(json.dumps([source['source_identity'], kind, location], separators=(',', ':')).encode()).hexdigest()
        candidates[kind].append((int(cell), identifier, location))
    for kind, limit in (('river_mouth', 1), ('lake_port', 1), ('river_reach', 2)):
        rows = sorted(candidates[kind], key=lambda row: (-discharge[row[0]], -area[row[0]], row[1]))
        for cell, identifier, location in rows:
            native = (int(np.floor(location[0] / 15360)), int(np.floor(location[1] / 15360)))
            if native in occupied:
                continue
            occupied.add(native)
            selected.append(dict(id=identifier, kind=kind, node=cell, location_xz_m=location,
                native_td_tile_xz=list(native), discharge_m3_s=float(discharge[cell]), drainage_area_m2=float(area[cell]),
                status='pending-terrain', reason='requires verified same-source native TD terrain and boundary package',
                max_nodes=min(2048, int(config.get('max_detail_nodes', 2048))),
                max_cells=min(65536, int(config.get('max_estuary_cells', 65536))),
                coarse_support_id=identifier, replacement_policy='replace coarse support, never add upstream contribution twice'))
            limit -= 1
            if not limit:
                break
    return sorted(selected, key=lambda row: (row['kind'], row['id']))


def prepare_channel_detail(*, source_identity, terrain_identity, network, water_forcing,
                           boundary_package, material, rock_floor_m, initial_alluvium_bulk_m3,
                           initial_mobile_solid_m3, initial_water_m3, is_lake,
                           mouth_nodes, hydraulic_config=None, sediment_config=None):
    """Existing finite Manning + sediment solver, with single-use boundary identity.

    The caller supplies a verified local terrain/network; no terrain is generated
    here and no final-only coarse bed is presented as TD terrain.
    """
    from terrain_pipeline.new_world_sediment import produce_supply
    if boundary_package.get('source_identity') != source_identity:
        raise ValueError('detail boundary belongs to another coarse source')
    if boundary_package.get('terrain_identity') != terrain_identity:
        raise ValueError('detail terrain identity differs from boundary binding')
    if boundary_package.get('consumed', False):
        raise ValueError('boundary package already consumed')
    if boundary_package.get('mode') != 'replace-coarse-support':
        raise ValueError('detail requires explicit coarse replacement support')
    if network.receiver.size > 2048:
        raise ValueError('detail node budget exceeded')
    supply = produce_supply(network, water_forcing, terrain_identity=terrain_identity, mouth_nodes=mouth_nodes,
        rock_floor_m=rock_floor_m, initial_alluvium_bulk_m3=initial_alluvium_bulk_m3,
        initial_mobile_solid_m3=initial_mobile_solid_m3, is_lake=is_lake, material=material,
        bed_material_provenance=material.provenance, bank_material_provenance=material.provenance,
        initial_water_m3=initial_water_m3, hydraulic_config=hydraulic_config, sediment_config=sediment_config)
    return dict(status='complete', source_identity=source_identity, terrain_identity=terrain_identity,
                replaces_support_id=boundary_package['support_id'], consumed_package_id=boundary_package['id'],
                supply=supply)


def apply_replacements(coarse, detailed, *, consumed_package_ids=()):
    """Replace numerical support once; retain published coarse data separately."""
    result = {name: np.asarray(value).copy() for name, value in coarse.items()}
    consumed = set(consumed_package_ids)
    supported = set()
    occupied = set()
    for detail in detailed:
        package = detail['consumed_package_id']
        support = detail['replaces_support_id']
        if package in consumed or support in supported:
            raise ValueError('detail boundary or support would be counted twice')
        indices = np.asarray(detail['support_indices'], np.int64)
        if indices.ndim != 1 or np.unique(indices).size != indices.size or occupied.intersection(indices.tolist()):
            raise ValueError('detailed supports overlap or contain duplicate indices')
        for name, value in detail['replacement_arrays'].items():
            numeric=np.asarray(value)
            if not np.isfinite(numeric).all():
                raise ValueError('finite detailed replacement values required')
            if (name.endswith('solid_m3') or name=='rock_removed_m3') and np.any(numeric<0):
                raise ValueError('detailed replacement inventory must be nonnegative')
            if name not in result:
                result[name] = np.zeros_like(result['elevation_m'],dtype=np.asarray(value).dtype)
            if np.any((indices<0)|(indices>=result[name].size)) or np.asarray(value).shape != indices.shape:
                raise ValueError('replacement support or value shape invalid')
            result[name].ravel()[indices] = value
        consumed.add(package)
        supported.add(support)
        occupied.update(indices.tolist())
    return result, sorted(consumed)
