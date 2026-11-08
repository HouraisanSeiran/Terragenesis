"""Cold-audit M3 saved traces, source binding and resampling with solvers disabled."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_product import load_channel_product, load_channel_output, sample_channel_output, save_channel_output
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
DISABLED = ('terrain_pipeline.surface_hydraulics.solve_channel', 'terrain_pipeline.drainage.route_diagnostic', 'terrain_pipeline.drainage.route_priority_flood', 'terrain_pipeline.drainage.compare_routing_policies', 'terrain_pipeline.runoff.runoff_from_forcing', 'terrain_pipeline.runoff.runoff_from_forcing_large', 'terrain_pipeline.climate_forcing.build_spatial_forcing', 'terrain_pipeline.surface_rivers.metric_product.build_diagnostic_product')

def audit(directory, output):
    directory, output = (Path(directory).resolve(), Path(output).resolve())
    report_path = directory / 'acceptance.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if report['status'] != 'accepted_bounded_kinematic_baseline' or any((report[key] is not False for key in ('hydraulic_ready', 'natural_outlet_verified', 'publishable'))):
        raise ValueError('accepted bounded M3 report required')
    loaded = {}
    sample_pins = {}
    with ExitStack() as stack:
        for entrypoint in DISABLED:
            stack.enter_context(patch(entrypoint, side_effect=AssertionError('cold audit invoked ' + entrypoint)))
        for name, pin in report['artifacts'].items():
            if pin.get('artifact_kind') == 'sampled_output':
                continue
            loaded[name] = load_channel_product(directory / pin['path'], expected_sha256=pin['sha256'], expected_identity=pin['identity_sha256'])
        selection = report['td_selection']
        source_manifest_path = Path(selection['source_manifest_path'])
        source_manifest = json.loads(source_manifest_path.read_text(encoding='utf-8'))
        source_pin = selection['source_product']
        if source_pin != source_manifest['artifacts']['product']:
            raise ValueError('source product pin differs')
        source = load_diagnostic_product(source_manifest_path.parent / source_pin['path'], expected_sha256=source_pin['sha256'], expected_identity=source_pin['identity_sha256'])
        if file_sha256(source_manifest['source_path']) != selection['source_sha256']:
            raise ValueError('TD raw source hash changed')
        data = source['arrays']
        ids = np.asarray(selection['selected_cell_ids'], np.int64)
        if len(ids) < 2 or len(set(ids.tolist())) != len(ids):
            raise ValueError('distinct TD controls required')
        np.testing.assert_array_equal(data['graph_receiver'][ids[:-1]], ids[1:])
        if data['graph_outlet_kind'][ids[-1]] != 'open_outflow' or np.any(data['graph_edge_slope'][ids[:-1]] <= 0.0):
            raise ValueError('TD path must end at known open terminal with positive original slopes')
        if source['metadata']['routing_identity_sha256'] != selection['routing_identity_sha256']:
            raise ValueError('TD original graph identity differs')
        for name in ('td_coarse', 'td_fine'):
            product = loaded[name]
            arrays = product['arrays']
            if product['metadata']['network_source_identity_sha256'] != source['identity_sha256']:
                raise ValueError('TD channel geometry source identity differs')
            if product['metadata']['forcing_source_identity_sha256'] != source['identity_sha256']:
                raise ValueError('TD local input source identity differs')
            np.testing.assert_array_equal(arrays['network_bed_elevation_m'], data['elevation_m'].ravel()[ids])
            np.testing.assert_array_equal(arrays['network_receiver'], np.r_[np.arange(1, len(ids)), -1])
            np.testing.assert_array_equal(arrays['network_length_m'][:-1], data['graph_edge_length_m'][ids[:-1]])
            np.testing.assert_array_equal(arrays['network_bed_slope'][:-1], data['graph_edge_slope'][ids[:-1]])
            if arrays['network_length_m'][-1] != arrays['network_length_m'][-2] or arrays['network_bed_slope'][-1] != arrays['network_bed_slope'][-2]:
                raise ValueError('TD terminal extension differs from declared assumption')
            np.testing.assert_array_equal(arrays['forcing_time_seconds'], data['time_seconds'])
            np.testing.assert_array_equal(arrays['forcing_local_q_m3_s'], data['local_q_m3_s'].reshape(3, -1)[:, ids])
            np.testing.assert_array_equal(arrays['network_width_m'], np.full(len(ids), 3.0))
            np.testing.assert_array_equal(arrays['network_roughness'], np.full(len(ids), 0.035))
            np.testing.assert_array_equal(arrays['network_max_depth_m'], np.full(len(ids), 10.0))
        output.mkdir(parents=True, exist_ok=False)
        for name in ('td_coarse', 'td_fine'):
            product = loaded[name]
            sampled = {}
            for label, times in (('dense', np.arange(0.0, 901.0, 30.0)), ('sparse', np.array([0.0, 900.0]))):
                value = sample_channel_output(product, times)
                path = output / (name + '_' + label + '.npz')
                save_channel_output(path, value)
                pin = {'path': path.name, 'sha256': file_sha256(path), 'identity_sha256': value['identity_sha256'], 'source_product_identity_sha256': product['identity_sha256']}
                sampled[label] = load_channel_output(path, expected_sha256=pin['sha256'], expected_identity=pin['identity_sha256'], expected_product_identity=product['identity_sha256'])
                sample_pins[name + '_' + label] = pin
            dense, sparse = (sampled['dense']['arrays'], sampled['sparse']['arrays'])
            np.testing.assert_array_equal(dense['volume_m3'][0], product['arrays']['trace_volume_m3'][0])
            np.testing.assert_array_equal(dense['volume_m3'][-1], sparse['volume_m3'][-1])
            np.testing.assert_allclose(dense['cumulative_boundary_outflow_volume_m3'][-1], sparse['cumulative_boundary_outflow_volume_m3'][-1], rtol=1e-12, atol=1e-10)
    result = {'schema': 'td-river-m3-cold-audit-v1', 'status': 'passed', 'disabled_entrypoints': list(DISABLED), 'acceptance_sha256': file_sha256(report_path), 'verified_product_count': len(loaded), 'source_binding_verified': True, 'local_Q_not_preaccumulated_verified': True, 'dense_sparse_initial_final_and_total_verified': True, 'sample_artifacts': sample_pins, 'code_sha256': {name: file_sha256(Path(__file__).resolve().parents[1] / name) for name in ('terrain_pipeline/channel_geometry.py', 'terrain_pipeline/surface_hydraulics.py', 'terrain_pipeline/surface_rivers/metric_channel_product.py', 'tools/audit_td_river_channel.py')}}
    publish_bytes(output / 'cold-audit.json', json.dumps(result, indent=2).encode('utf-8'))
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.input, args.output), indent=2))
if __name__ == '__main__':
    main()
