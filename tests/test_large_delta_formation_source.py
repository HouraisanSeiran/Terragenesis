import numpy as np
from terrain_pipeline.large_delta_formation_source import aggregate, assign_nodes
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.surface_rivers.metric_upstream_sediment import route_daily_sediment


def test_graph_contraction_preserves_contributions_and_parent():
    order = np.array([0, 1, 2, 3], dtype=np.int64)
    receiver = np.array([-1, 0, 1, 1], dtype=np.int64)
    selected = np.array([0, -1, 1, -1], dtype=np.int32)
    assignment = assign_nodes(order, receiver, np.ones(4, dtype=np.bool_), selected)
    assert assignment.tolist() == [0, 0, 1, 0]
    assert aggregate(np.array([1., 2., 3., 4.]), assignment, 2).tolist() == [7., 3.]
    assert assignment[receiver[2]] == 0


def test_finite_hillslope_transfer_is_counted_once_with_channel_export():
    initial_hill = 100.0
    transfer = 30.0
    result = route_daily_sediment(
        receiver=np.array([-1], dtype=np.int64), length_m=np.array([100.]),
        width_m=np.array([10.]), bed_elevation_m=np.array([2.]), rock_floor_m=np.array([1.]),
        initial_alluvium_bulk_m3=np.array([1000.]), hardness=np.ones(1),
        water_depth_m=np.array([[1.]]), water_q_m3_s=np.array([[10.]]),
        friction_slope=np.array([[.01]]), time_seconds=np.array([0., 10000.]),
        material=MaterialParameters(porosity=.4), external_solid_m3_s=np.array([[transfer/10000.]]),
        geometry_identity_sha256='a'*64, hydraulic_identity_sha256='b'*64, material_provenance='test finite stock')
    a = result['arrays']
    final_hill = initial_hill - transfer
    initial_channel = 600.0
    final_channel = a['trace_loose_solid_m3'][-1].sum() + a['trace_mobile_solid_m3'][-1].sum()
    exported = a['exported_solid_m3'].sum()
    assert np.isclose(initial_hill + initial_channel, final_hill + final_channel + exported)
    assert a['eroded_rock_m3'].sum() == 0.0
