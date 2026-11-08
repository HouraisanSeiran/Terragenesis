"""Cold-read saved fine scenarios with every production constructor disabled."""

def forbidden(*args, **kwargs):
    raise RuntimeError('production construction/solver forbidden in fine cold IO')
import argparse
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ.setdefault(name, '1')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.surface_execution_guards import guard_production_execution
import numpy as np
import psutil
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline import fine_subgrid as fine_io
from terrain_pipeline import fine_subgrid as fine_geometry
from terrain_pipeline import surface_hydraulics as regional
from tools.audit_single_domain_fine_stage import read_json, audit_fan

@guard_production_execution()
def verify(index_record, output):
    started = time.monotonic()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    with patch.object(fine_geometry, 'build_fine_geometry', forbidden), patch.object(fine_geometry, 'build_fine_water_frame', forbidden), patch.object(fine_geometry, '_geometry_arrays', forbidden), patch.object(fine_geometry, 'prepare_subgrid_support', forbidden), patch.object(fine_geometry, 'segmented_flux', forbidden), patch.object(regional, 'prepare_surface_geometry', forbidden), patch.object(regional, 'advance_inertial_surface', forbidden):
        index = read_json(index_record)
        short = index.get('schema') == 'single-domain-fine-short-index-v1'
        declaration = read_json(index['predeclared'])
        if short:
            boundary = dict(initial_lake_stage_m=index['initial_lake_stage_m'])
            if set(index['cases']) != {'1.0', '2.0', '4.0'} or index.get('stage_accepted') is not False or declaration['source'] != index['source'] or any((index.get(name) is not False for name in fine_io.FLAGS)):
                raise ValueError('fine short diagnostic declaration/flags mismatch')
        else:
            report, resource = (read_json(index[name]) for name in ('report', 'resource'))
            boundary = read_json(index['boundary_declaration'])
            if index.get('schema') != 'single-domain-fine-stage-index-v1' or report['cases'] != index['cases'] or resource.get('complete') is not True or (resource['budgets'] != declaration['budgets']) or (len(index['cases']) != 7) or any((index.get(name) is not False for name in fine_io.FLAGS)):
                raise ValueError('fine complete stage/report/resource binding mismatch')
        if 'code_records' in index:
            fine_io._validate_code_records(index['code_sha256'], index['code_records'], Path(index_record['path']).resolve().parent)
        else:
            for name, digest in index['code_sha256'].items():
                path = (ROOT / name).resolve(strict=True)
                if not path.is_relative_to(ROOT) or file_sha256(path) != digest:
                    raise ValueError('fine cold current code pin mismatch')
        source = fine_io._single_domain_fine_io_load(index['source'], lambda item: True)
        cases = {}
        frames_total = 0
        for name, case in index['cases'].items():
            bed = fine_io._single_domain_fine_io_load(case['bed'], fine_io.validate_canonical_bed)
            if bed['metadata']['source_hierarchy_sha256'] != index['source']['expected_sha256'] or bed['metadata']['hierarchy_identity'] != source['identity_sha256']:
                raise ValueError('fine cold original hierarchy binding mismatch')
            for field in ('height_m', 'valid_mask', 'protected_mask', 'receiver'):
                if not np.array_equal(bed['arrays']['native_' + field], source['arrays'][field]):
                    raise ValueError('fine cold actual source bed mismatch')
            loaded = fine_io.load_fine_run(case['run']['path'], expected_sha256=case['run']['expected_sha256'], bed=bed)
            fine_io.validate_initial_contract(loaded['states'], bed=bed, lake_stage_m=boundary['initial_lake_stage_m'], initial_kind=case.get('initial_kind', 'lake'))
            steps = loaded['forcing']['metadata']['steps']
            if short and 'frames' in case or (not short and len(case['frames']) != steps + 1):
                raise ValueError('fine cold complete frame coverage mismatch')
            maximum_volume_error = 0.0
            for number, entry in enumerate(case.get('frames', [])):
                frame = fine_io._single_domain_fine_io_load(entry['frame'], lambda item: fine_io._single_domain_fine_io_check(item, 'single-domain-fine-water-fan-v1'))
                metadata = frame['metadata']
                if entry['state_index'] != number or metadata['state_index'] != number or metadata['bed_identity'] != bed['identity_sha256'] or (metadata['hydraulic_state_identity'] != loaded['states']['identity_sha256']) or (abs(metadata['time_s'] - loaded['states']['arrays']['time_s'][number]) > 1e-09) or (not np.array_equal(frame['arrays']['cell_depth_m'], loaded['states']['arrays']['depth_m'][number])):
                    raise ValueError('fine cold original frame state/time binding mismatch')
                diagnostics = audit_fan(bed['arrays'], frame['arrays'], bed['metadata']['spacing_m'])
                maximum_volume_error = max(maximum_volume_error, diagnostics['maximum_cell_volume_difference_m3'])
                frames_total += 1
            cases[name] = dict(frames=len(case.get('frames', [])), saved_states=steps + 1, intervals_verified=loaded['intervals_verified'], maximum_cell_volume_difference_m3=maximum_volume_error, hydraulic_model=loaded['geometry']['metadata'].get('hydraulic_model', 'flat-cell-D4'))
            print('cold verified ' + name, flush=True)
        memory = psutil.Process().memory_info()
        rss, private = (int(getattr(memory, 'peak_wset', memory.rss)), int(getattr(memory, 'peak_pagefile', memory.vms)))
        elapsed = time.monotonic() - started
        if max(rss, private) > 1073741824 or elapsed > 1800:
            raise RuntimeError('fine cold resource budget exceeded')
        result = dict(schema='single-domain-fine-cold-io-v1', index_record=index_record, cases=cases, frame_count=frames_total, pure_io_verified=True, production_construction_disabled=True, solver_advanced=False, execution_modules_absent=False, code_sha256=file_sha256(Path(__file__)), resource=dict(peak_rss_bytes=rss, peak_private_bytes=private, elapsed_s=elapsed), canonical_recipe_independently_verified=False, no_source_recipe_verified=True, stage_accepted=False, limitations=['Cold IO validates pinned saved algebra; source capsule/protection provenance requires separate independent audit.'], hydraulic_ready=False, natural_outlet_verified=False, publishable=False, execution_functions_guarded=True)
        target = output / 'report.json'
        publish_bytes(target, (json.dumps(result, indent=2, allow_nan=False) + '\n').encode('utf-8'))
        print(json.dumps(dict(path=str(target), expected_sha256=file_sha256(target), frames=frames_total)), flush=True)
        return result
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True, type=Path)
    parser.add_argument('--index-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    verify(dict(path=str(args.index.resolve()), expected_sha256=args.index_sha256), args.output)
