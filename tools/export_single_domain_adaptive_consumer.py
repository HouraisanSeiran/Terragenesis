"""Export saved AMR inventories and identity-bound continuous water fans."""
import argparse
import gc
import os
from pathlib import Path
import sys
import tempfile
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ.setdefault(name, '1')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.surface_execution_guards import guard_production_execution
from terrain_pipeline.common_infra import file_sha256, load_bundle
from terrain_pipeline.td_native_weather_storage_io import _json
from terrain_pipeline.fine_subgrid import _single_domain_fine_io_load as _load, validate_canonical_bed
from terrain_pipeline.single_domain_surface_consumer import BUDGETS, SCHEMA, copy_payload, publish_manifest, load_consumer_manifest
from terrain_pipeline.adaptive_mesh import load_adaptive_run
from terrain_pipeline.adaptive_mesh import build_adaptive_water_frame, save_adaptive_water_frame
from tools.audit_single_domain_fine_stage import audit_fan
from tools.export_single_domain_fine_consumer import resources
import time

def load_saved(pin):
    result = load_bundle(pin['path'], expected_sha256=pin['expected_sha256'], max_bytes=BUDGETS['max_artifact_bytes'], validator=lambda item: True)
    if result['identity_sha256'] != pin['expected_identity']:
        raise ValueError('adaptive consumer saved external identity mismatch')
    return result

@guard_production_execution()
def export(index_path, index_sha256, output):
    started = time.monotonic()
    source = dict(path=str(Path(index_path).resolve()), expected_sha256=index_sha256)
    index = _json(source)
    if index.get('schema') != 'single-domain-adaptive-stage-index-v1' or not index.get('cases'):
        raise ValueError('adaptive consumer requires complete saved stage index')
    uniform = _json(index['source_v7_index'])
    output = Path(output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    artifacts, scenarios, beds = ([], {}, {})
    for name, case in index['cases'].items():
        if Path(name).name != name or name in ('.', '..') or '\\' in name or (':' in name):
            raise ValueError('adaptive consumer case path invalid')
        bed = _load(case['bed'], validate_canonical_bed)
        key = bed['identity_sha256']
        if key not in beds:
            beds[key] = 'beds/' + key + '.npz'
            artifacts.append(copy_payload(output, beds[key], case['bed'], bed, role='continuous-bed-and-network', provenance=dict(source_index=source, source_artifact=case['bed'])))
        run = load_adaptive_run(case['run']['path'], expected_sha256=case['run']['expected_sha256'])
        evidence, geometry_payloads, frames = ({}, {}, [])
        original_run_pin = uniform['cases'][case['source_v7_case']]['run']
        if run['index']['source_record'] != original_run_pin:
            raise ValueError('adaptive consumer original runoff source mismatch')
        original_run = _json(original_run_pin)
        original_forcing_pin = original_run['forcing']
        original_forcing_name = name + '/original-rainfall-runoff.npz'
        artifacts.append(copy_payload(output, original_forcing_name, original_forcing_pin, load_saved(original_forcing_pin), role='original-rainfall-runoff', provenance=dict(source_index=index['source_v7_index'], source_run=original_run_pin, source_artifact=original_forcing_pin, used_hydraulic_forcing_zero=case['initial_kind'] == 'zero_source_lake')))
        evidence['original_rainfall_runoff'] = original_forcing_name
        for role in ('forcing', 'states'):
            pin = run['index'][role]
            payload = name + '/' + role + '.npz'
            artifacts.append(copy_payload(output, payload, pin, load_saved(pin), role='saved-adaptive-' + role, provenance=dict(source_index=source, source_run=case['run'], source_artifact=pin)))
            evidence[role] = payload
        for number, pin in enumerate(run['index']['snapshots']):
            snapshot = load_saved(pin)
            raw_key = snapshot['metadata']['geometry_identity']
            geometry = run['geometries'][raw_key]
            if raw_key not in geometry_payloads:
                geometry_pin = run['index']['geometries'][raw_key]
                payload = name + '/geometry-' + raw_key + '.npz'
                artifacts.append(copy_payload(output, payload, geometry_pin, load_saved(geometry_pin), role='saved-adaptive-leaf-geometry', provenance=dict(source_run=case['run'], source_artifact=geometry_pin)))
                geometry_payloads[raw_key] = payload
            snapshot_name = name + f'/snapshot-{number:02d}.npz'
            artifacts.append(copy_payload(output, snapshot_name, pin, snapshot, role='saved-adaptive-snapshot', provenance=dict(source_run=case['run'], source_artifact=pin)))
            frame = build_adaptive_water_frame(bed, snapshot, geometry, state_index=number)
            audit_fan(bed['arrays'], frame['arrays'], 1.0)
            frame_name = name + f'/frame-{number:02d}.npz'
            with tempfile.TemporaryDirectory(dir=output) as temporary:
                path = Path(temporary) / 'frame.npz'
                save_adaptive_water_frame(path, frame)
                frame_pin = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=frame['identity_sha256'])
                artifacts.append(copy_payload(output, frame_name, frame_pin, frame, role='saved-water-frame', provenance=dict(source_run=case['run'], source_snapshot=pin, source_bed=case['bed'], source_adaptive_geometry_identity=raw_key)))
            frames.append(dict(frame=number, time_s=frame['metadata']['time_s'], artifact=frame_name, snapshot=snapshot_name, adaptive_geometry=geometry_payloads[raw_key]))
            resources(started, artifacts)
            del frame, snapshot, geometry
        scenarios[name] = dict(geometry=beds[key], frames=frames, evidence=evidence, root_spacing_m=case['root_spacing_m'], max_dt_s=case['max_dt_s'], initial_kind=case['initial_kind'], used_hydraulic_forcing_zero=case['initial_kind'] == 'zero_source_lake', full_selected_window_covered=True, all_substep_states_saved=False)
        print('exported ' + name, flush=True)
        del run, bed
        gc.collect()
    if file_sha256(index_path) != index_sha256:
        raise ValueError('adaptive stage index changed during consumer export')
    manifest = dict(schema=SCHEMA, backend='adaptive-saved-canonical-fan', evidence_status='adaptive-finite-window-evidence', source_index=source, artifacts=artifacts, scenarios=scenarios, budgets=BUDGETS, output_bytes=sum((item['bytes'] for item in artifacts)), resource=resources(started, artifacts), coordinates='physical metres [x,y,z]; x east, y up, z south; raster [z,x]', solver_advanced=False, execution_modules_absent=False, uniform_coarse_convergence_claim=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False, official_frontend_integrated=False, full_native_domain_fine_verified=False, limitations=['Fine coverage is the selected 240m by 240m window inside the native domain.', 'Water fans conserve canonical inventory; they do not increase hydraulic solution order.', 'Actual 4/2/1m leaf occupancy is saved; useful wet regions may be entirely refined to 1m.', 'Uniform coarse depth comparisons failed and are not relabeled as AMR convergence.', 'Original soil/fast/slow runoff records are included; the zero-source lake overrides actual hydraulic supply to zero.', 'Full epoch transfers and sampled physical equations remain in the pinned source runs.'], code_sha256={name: file_sha256(ROOT / name) for name in ('terrain_pipeline/adaptive_mesh.py', 'terrain_pipeline/single_domain_surface_consumer.py', 'tools/export_single_domain_adaptive_consumer.py')}, execution_functions_guarded=True)
    pin = publish_manifest(output, manifest)
    load_consumer_manifest(pin['path'], expected_sha256=pin['expected_sha256'])
    print(pin, flush=True)
    return pin
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True, type=Path)
    parser.add_argument('--index-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    export(args.index, args.index_sha256, args.output)
