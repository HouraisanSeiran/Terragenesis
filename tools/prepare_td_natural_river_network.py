"""Prepare one pinned TD natural river candidate and a bounded fine-bed sample."""
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import PRIMARY_PATH as PRIMARY_PATH
from terrain_pipeline.basin_storage import PRIMARY_SHA256 as PRIMARY_SHA256
from terrain_pipeline.td_natural_river_network import build_natural_river_network, save_natural_river_network
from tools.audit_td_natural_river_network import audit_saved_network
from tools.export_td_natural_river_review import export_review
HIERARCHY = {'path': str(ROOT / 'verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz'), 'expected_sha256': '36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422', 'expected_identity': 'cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998'}

def _pin(path, result):
    return {'path': str(path), 'expected_sha256': file_sha256(path), 'expected_identity': result['identity_sha256']}

def _json(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode('utf-8'))

def _window(network):
    arrays, metadata = (network['arrays'], network['metadata'])
    nodes = arrays['node_cell_ids']
    edges = arrays['edge_cell_ids']
    incoming = np.zeros(nodes.size, np.int64)
    np.add.at(incoming, np.searchsorted(nodes, edges[:, 1]), 1)
    junctions = np.flatnonzero(incoming > 1)
    candidates = junctions if junctions.size else np.arange(nodes.size)
    candidate = candidates[np.argmax(arrays['node_representative_q_m3_s'][candidates])]
    point = arrays['node_native_xyz_m'][candidate, [0, 2]]
    origin = np.asarray(metadata['origin_m_xz'], np.float64)
    upper = origin + (np.asarray(metadata['grid_shape'])[::-1] - 1) * metadata['spacing_m']
    size_m = min(120.0, float(np.min(upper - origin)))
    lower = np.clip(point - size_m / 2, origin, upper - size_m)
    return (lower.tolist(), [int(size_m) + 1] * 2)

def plot_overview(path, *, network, geometry, window_origin, window_shape):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle
    arrays, metadata = (network['arrays'], network['metadata'])
    origin = np.array(metadata['origin_m_xz'])
    spacing = metadata['spacing_m']
    height = arrays['source_height_m']
    lines = geometry['arrays']['edge_centerline_xyz_m'][:, :, [0, 2]]
    lines = (lines - origin) / 1000.0
    extent = [0, (height.shape[1] - 1) * spacing / 1000.0, (height.shape[0] - 1) * spacing / 1000.0, 0]
    levels = arrays['edge_level_code']
    colors = np.array(['#658d85', '#21b2c1', '#2472bf', '#df7a38'])
    widths = np.array([0.7, 1.0, 1.5, 2.1])
    figure, axes = plt.subplots(1, 2, figsize=(14, 7), constrained_layout=True)
    image = None
    for panel in axes:
        image = panel.imshow(height, extent=extent, origin='upper', cmap='gist_earth')
        panel.add_collection(LineCollection(lines, colors=colors[levels], linewidths=widths[levels]))
        panel.set_xlabel('East from TD origin (km)')
        panel.set_ylabel('South from TD origin (km)')
        panel.set_aspect('equal')
    axes[0].set_title('Full TD input / selected contribution basin only')
    cells = np.argwhere(arrays['selected_basin_mask'])
    lower = np.maximum(0.0, cells.min(axis=0)[::-1] * spacing / 1000.0 - 0.12)
    upper = cells.max(axis=0)[::-1] * spacing / 1000.0 + 0.12
    axes[1].set_xlim(lower[0], upper[0])
    axes[1].set_ylim(upper[1], lower[1])
    axes[1].set_title('Main basin / candidate bed lines, not simulated water')
    rectangle_origin = (np.asarray(window_origin) - origin) / 1000.0
    rectangle_size = (np.asarray(window_shape)[::-1] - 1) / 1000.0
    for panel in axes:
        panel.add_patch(Rectangle(rectangle_origin, rectangle_size[0], rectangle_size[1], fill=False, edgecolor='#ffee79', linewidth=1.8))
    labels = ('Small gully', 'Seasonal tributary', 'Perennial tributary', 'Mainstem')
    legend = [Line2D([0], [0], color=colors[level], linewidth=widths[level], label=labels[level]) for level in np.unique(levels)]
    legend.append(Line2D([0], [0], color='#ffee79', linewidth=1.8, label='120m fine-bed sample'))
    axes[1].legend(handles=legend, loc='lower right', fontsize=8)
    figure.colorbar(image, ax=axes, shrink=0.7, label='Native terrain elevation (m)')
    title = f'Natural-network candidate | {len(lines)} selected edges | all certification flags false'
    figure.suptitle(title, fontsize=12)
    payload = io.BytesIO()
    figure.savefig(payload, format='png', dpi=130)
    plt.close(figure)
    publish_bytes(path, payload.getvalue())

def _internal_basin_sample(destination):
    from terrain_pipeline.basin_topology import basin_volume_at_level as basin_volume_at_level
    from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
    from terrain_pipeline.basin_topology import save_basin_hierarchy as save_basin_hierarchy
    from terrain_pipeline.basin_storage import make_td_source as make_td_source
    from terrain_pipeline.basin_storage import save_td_source as save_td_source
    height = np.fromfunction(lambda row, column: 100.0 + abs(row - 10) + abs(column - 10), (21, 21))
    source = make_td_source(height, spacing_m=30.0)
    hierarchy = build_basin_hierarchy(source)
    network = build_natural_river_network(hierarchy, expected_hierarchy_identity=hierarchy['identity_sha256'])
    source_path = destination / 'internal-source.npz'
    hierarchy_path = destination / 'internal-hierarchy.npz'
    network_path = destination / 'internal-network.npz'
    save_td_source(source_path, source)
    save_basin_hierarchy(hierarchy_path, hierarchy)
    save_natural_river_network(network_path, network)
    root_nodes = np.flatnonzero(hierarchy['arrays']['node_parent'] < 0)
    if root_nodes.size != 1:
        raise ValueError('closed fixture must have one connected storage root')
    root = int(root_nodes[0])
    samples = []
    for stage_m in (100.5, 102.0, 105.0):
        expected_m3 = float(np.maximum(stage_m - height, 0.0).sum() * 30.0 ** 2)
        measured_m3 = basin_volume_at_level(hierarchy, root, stage_m)
        if not np.isclose(measured_m3, expected_m3, rtol=1e-12, atol=1e-09):
            raise ValueError('closed basin storage curve differs from terrain integral')
        samples.append({'stage_m': stage_m, 'volume_m3': measured_m3, 'independent_terrain_volume_m3': expected_m3})
    record = {'schema': 'td-natural-internal-basin-fixture-v1', 'input_kind': 'synthetic_closed_fixture_not_TD', 'source': _pin(source_path, source), 'hierarchy': _pin(hierarchy_path, hierarchy), 'network': _pin(network_path, network), 'summary': network['metadata']['summary'], 'retained_original_bed': True, 'storage_samples': samples, 'spill_dynamics_verified': False, 'cut_fill_candidates_generated': False, 'hydraulic_ready': False, 'natural_outlet_verified': False, 'publishable': False}
    _json(destination / 'internal-basin-sample.json', record)
    return record

def prepare(output):
    from terrain_pipeline.channel_geometry import build_natural_channel_geometry, evaluate_natural_channel_window, save_natural_channel_geometry, save_natural_channel_window
    destination = Path(output)
    if destination.exists():
        raise FileExistsError(destination)
    started = time.perf_counter()
    if file_sha256(PRIMARY_PATH) != PRIMARY_SHA256:
        raise ValueError('original TD source pin mismatch')
    hierarchy = load_basin_hierarchy(**HIERARCHY)
    network = build_natural_river_network(hierarchy, expected_hierarchy_identity=HIERARCHY['expected_identity'])
    geometry = build_natural_channel_geometry(network)
    lower, shape = _window(network)
    window = evaluate_natural_channel_window(geometry, network, window_origin_m_xz=lower, spacing_m=1.0, shape_zx=shape)
    paths = {name: destination / (name + '.npz') for name in ('network', 'geometry', 'window')}
    for name, result, saver in (('network', network, save_natural_river_network), ('geometry', geometry, save_natural_channel_geometry), ('window', window, save_natural_channel_window)):
        saver(paths[name], result)
    pins = {name: _pin(paths[name], result) for name, result in (('network', network), ('geometry', geometry), ('window', window))}
    audit = audit_saved_network(network_record=pins['network'], hierarchy_record=HIERARCHY, geometry_record=pins['geometry'], window_record=pins['window'])
    _json(destination / 'independent-audit.json', audit)
    review = export_review(destination / 'review.json', network_record=pins['network'], geometry_record=pins['geometry'])
    plot_overview(destination / 'overview.png', network=network, geometry=geometry, window_origin=lower, window_shape=shape)
    internal = _internal_basin_sample(destination)
    if file_sha256(PRIMARY_PATH) != PRIMARY_SHA256 or file_sha256(HIERARCHY['path']) != HIERARCHY['expected_sha256']:
        raise ValueError('fixed original source changed during preparation')
    artifacts = {name: {'path': paths[name].name, 'sha256': pin['expected_sha256'], 'identity_sha256': pin['expected_identity']} for name, pin in pins.items()}
    for name in ('independent-audit.json', 'review.json', 'overview.png', 'internal-basin-sample.json', 'internal-source.npz', 'internal-hierarchy.npz', 'internal-network.npz'):
        artifacts[name] = {'path': name, 'sha256': file_sha256(destination / name), 'bytes': (destination / name).stat().st_size}
    code = ('terrain_pipeline/td_natural_river_network.py', 'terrain_pipeline/channel_geometry.py', 'tools/prepare_td_natural_river_network.py', 'tools/audit_td_natural_river_network.py', 'tools/export_td_natural_river_review.py', 'terrain_pipeline/mountain_source_adapter.py', 'terrain_pipeline/basin_topology.py', 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/artifacts/contracts.py', 'terrain_pipeline/runoff.py')
    index = {'schema': 'td-natural-river-delivery-v1', 'status': 'static_candidate_only', 'input_pins': {'hierarchy': HIERARCHY, 'original_td': {'path': str(PRIMARY_PATH), 'sha256': PRIMARY_SHA256}}, 'artifacts': artifacts, 'network_summary': network['metadata']['summary'], 'geometry_summary': geometry['metadata']['summary'], 'window_summary': window['metadata']['summary'], 'window_origin_m_xz': lower, 'window_shape_zx': shape, 'review_bytes': review['bytes'], 'internal_basin_summary': internal['summary'], 'code_sha256': {name: file_sha256(ROOT / name) for name in code}, 'output_bytes_before_index': sum(((destination / record['path']).stat().st_size for record in artifacts.values())), 'budgets': {'max_native_cells': 250000, 'max_review_bytes': 32 * 1024 * 1024, 'fine_sample_points': int(np.prod(shape)), 'fine_sample_spacing_m': 1.0}, 'elapsed_s': time.perf_counter() - started, 'original_source_unchanged': True, 'solver_advanced': False, 'hydraulic_ready': False, 'natural_outlet_verified': False, 'publishable': False, 'remaining': ['same-derived-bed event hydrology and backwater', 'connected fine corridors and mixed precision', 'independent natural outlet evidence', 'basin spill and bounded cut/fill joint acceptance', 'formal frontend integration', 'underground river generation']}
    _json(destination / 'index.json', index)
    return index
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / 'verification/natural-river-network' / datetime.now(timezone.utc).strftime('run-%Y%m%dT%H%M%S%fZ')
    result = prepare(output)
    print(json.dumps({'output': str(output), 'network': result['network_summary'], 'geometry': result['geometry_summary'], 'elapsed_s': result['elapsed_s']}, ensure_ascii=False))
