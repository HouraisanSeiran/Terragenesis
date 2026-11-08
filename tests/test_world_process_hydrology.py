import numpy as np

from terrain_pipeline import drainage
from terrain_pipeline.world_process_hydrology import lake_balance, representative_hydraulics


def test_actual_lake_storage_and_overflow():
    receiver = np.array([1, 2, -1], np.int64)
    order = np.array([2, 1, 0], np.int64)
    bed = np.array([10., 0., -1.])
    filled = np.array([10., 5., -1.])
    lakes = np.array([0, 1, 0])
    flow, surface, budget = lake_balance(np.array([3., 0., 0.]), receiver, order, lakes, bed, filled, 1.)
    assert budget['final_storage_m3'] == 3.
    assert flow[-1] == 0
    np.testing.assert_allclose(surface[1], 3., atol=1e-9)
    flow, surface, budget = lake_balance(np.array([4., 0., 0.]), receiver, order, lakes, bed, filled, 1., budget['storage_by_pool_m3'])
    assert budget['final_storage_m3'] == 5.
    assert flow[-1] == 2.


def test_existing_manning_kernel_inversion():
    shape = (4, 4)
    mesh = drainage.grid_mesh(shape, x0_m=0., z0_m=0., dx_m=2000., world_seed=20260903)
    bed = np.arange(16., 0., -1).reshape(shape) * 20
    ocean = np.zeros(shape, bool)
    ocean[-1] = True
    route = drainage.route_graph(bed, ocean, mesh)
    q = np.full(shape, 20.)
    result = representative_hydraulics(bed, route.receiver, q, mesh)
    active = result['slope'] > 0
    width, depth, slope = (result[name][active] for name in ('width_m', 'depth_m', 'slope'))
    solved = width * depth * (width * depth / (width + 2 * depth)) ** (2/3) * np.sqrt(slope) / .04
    np.testing.assert_allclose(solved, 20., rtol=1e-5)
