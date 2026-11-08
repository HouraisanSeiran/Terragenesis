"""Valley geometry evidence on a blocked synthetic ridge and saved mountain."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.channel_geometry import ChannelRecipe, load_plan, plan_channel
from terrain_pipeline.channel_geometry import ValleyGeometryRecipe, prepare_valley_geometry, evaluate_fine_valley_ledger, save_fine_valley_ledger
from terrain_pipeline.surface_domain import prepare_with_reroute
from terrain_pipeline.surface_domain import SurfaceNetworkBudget, save_surface_network
from terrain_pipeline.surface_hydraulics import StageRecipe
from terrain_pipeline.surface_hydraulics import InundationRecipe
from terrain_pipeline.channel_geometry import SectionRecipe
from tests.test_surface_hydraulics import conservative_plan
from tests.test_lake_balance import basin_fixture
from terrain_pipeline.lake import LakeBalanceRecipe as LakeBalanceRecipe
from terrain_pipeline.lake import evaluate_lake_balance as evaluate_lake_balance
from tests.test_surface_hydraulics import confluence_plan

def recipe_from_plan(plan):
    params = plan['identity']['parameters']
    return ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__})

def main():
    destination = ROOT / 'verification/valley-geometry' / datetime.now(timezone.utc).strftime('run-%Y%m%dT%H%M%S%fZ')
    destination.mkdir(parents=True)
    report = {}
    base = confluence_plan()
    arrays = base['arrays']
    raised = arrays['source_height_m'].copy()
    raised[3, 3] += 5
    recipe = recipe_from_plan(base)
    blocked = plan_channel(raised, arrays['receiver'], arrays['order'], arrays['outlet_mask'], arrays['discharge_m3_s'], 10.0, 10.0, 0.0, 0.0, 0.0, 'raised-ridge', recipe)
    valley = prepare_valley_geometry(blocked, np.array([[30.0, 10.0], [30.0, 60.0]]), np.array([4.7, 3.7]), np.array([30.0, 30.0]), np.ones((7, 7), bool), np.zeros((7, 7), bool), ValleyGeometryRecipe(8.0, 10000.0, 100000.0, 100000.0), recipe)
    report['blocked_synthetic'] = {'before_over_budget_nodes': int(blocked['arrays']['over_budget_mask'].sum()), 'after_over_budget_nodes': int(valley['replanned_plan']['arrays']['over_budget_mask'].sum()), **valley['summary']}
    domain_fine = np.ones((61, 61), bool)
    empty_fine = np.zeros((61, 61), bool)
    legal_fine = empty_fine.copy()
    legal_fine[-1, 27:34] = True
    from terrain_pipeline.surface_domain import prepare_surface_network
    valley_surface = prepare_surface_network(valley['replanned_plan'], 0.0, 0.0, 1.0, 1.0, (61, 61), domain_fine, empty_fine, legal_fine, np.array([5.2]), SectionRecipe(), StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0), InundationRecipe(max_lateral_reach_m=15.0), SurfaceNetworkBudget(4.0, 5000.0, 5000.0))
    fine_ledger = evaluate_fine_valley_ledger(valley, valley_surface)
    if fine_ledger['status'] == 'prepared':
        save_fine_valley_ledger(fine_ledger, destination / 'blocked-valley-fine.npz')
        save_surface_network(valley_surface, destination / 'blocked-valley-water.npz')
    report['blocked_synthetic']['fine'] = {'status': fine_ledger['status'], **fine_ledger['summary']}
    path = ROOT / 'verification/metric-channel-plan/run-20260929T140629572001Z/normal_mountain-plan.npz'
    mountain = load_plan(path)
    a = mountain['arrays']
    params = mountain['identity']['parameters']
    outlet = int(np.flatnonzero(a['outlet_mask'])[0])
    donors = [[] for _ in range(a['receiver'].size)]
    for cell in np.flatnonzero(a['channel_mask'].ravel() & (a['receiver'] >= 0)):
        donors[int(a['receiver'][cell])].append(int(cell))
    node = outlet
    path_cells = [node]
    while donors[node]:
        node = max(donors[node], key=lambda cell: float(a['discharge_m3_s'].flat[cell]))
        path_cells.append(node)
    path_cells.reverse()
    selected = path_cells[::max(1, len(path_cells) // 20)]
    if selected[-1] != path_cells[-1]:
        selected.append(path_cells[-1])
    cols = a['source_height_m'].shape[1]
    points = np.array([[params['origin_x_m'] + cell % cols * params['spacing_x_m'], params['origin_z_m'] + cell // cols * params['spacing_z_m']] for cell in selected])
    floors = np.array([float(a['source_height_m'].flat[cell] - 2.0) for cell in selected])
    widths = np.full(len(selected), 60.0)
    real = prepare_valley_geometry(mountain, points, floors, widths, np.ones(a['source_height_m'].shape, bool), np.zeros(a['source_height_m'].shape, bool), ValleyGeometryRecipe(4.0, 100000000.0, 1000000000.0, 1000000000.0), recipe_from_plan(mountain))
    report['normal_mountain'] = {'source_plan': str(path.relative_to(ROOT)), 'selected_branch_nodes': len(path_cells), 'explicit_profile_points': len(selected), 'profile_note': 'Sparse straight chords through 22 points along a largest-discharge branch; not a route-following network valley', 'before_over_budget_nodes': int(a['over_budget_mask'].sum()), 'after_over_budget_nodes': int(real['replanned_plan']['arrays']['over_budget_mask'].sum()), 'legal_natural_outlet_verified': False, 'joint_surface_water_verified': False, **real['summary']}
    reroute_source = conservative_plan()
    coarse_domain = np.ones((5, 5), bool)
    coarse_protected = np.zeros((5, 5), bool)
    coarse_protected[1, 2] = True
    fine_domain = np.ones((9, 9), bool)
    fine_protected = np.zeros((9, 9), bool)
    fine_protected[2, 4] = True
    legal = np.zeros((9, 9), bool)
    legal[-1, 3:6] = True
    recovery = prepare_with_reroute(reroute_source, (1, 1), (3, 2), coarse_domain, coarse_protected, 0.0, 0.0, 0.5, 0.5, (9, 9), fine_domain, fine_protected, legal, np.array([9.8]), SectionRecipe(), StageRecipe(max_depth_m=4.0, max_lift_above_nominal_m=3.0), InundationRecipe(max_lateral_reach_m=5.0), SurfaceNetworkBudget(4.0, 100.0, 100.0))
    if recovery['accepted']:
        saved = save_surface_network(recovery['surface_network'], destination / 'rerouted-synthetic.npz')
    report['rerouted_synthetic'] = {'accepted': recovery['accepted'], 'path_grid_zx': recovery['reroute']['path_grid_zx'], 'reroute_summary': recovery['reroute']['summary'], 'surface_summary': recovery['surface_network']['summary'], 'saved': saved.name if recovery['accepted'] else None}
    lake_h, lake_basin, lake_domain, lake_protected, lake_legal = basin_fixture()
    lake_results = {}
    for max_outflow in (1.0, 2.0):
        lake = evaluate_lake_balance(lake_h, lake_basin, (3, 5), 1.0, 1.0, 'synthetic-lake', LakeBalanceRecipe(10.0, 2.0, 0.0, 1.0, 3.0, max_outflow), [(3, 5), (3, 6)], lake_domain, lake_protected, lake_legal)
        lake_results[str(max_outflow)] = lake['summary']
    report['lake_constant_flux_synthetic'] = lake_results
    (destination / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(destination)
if __name__ == '__main__':
    main()
