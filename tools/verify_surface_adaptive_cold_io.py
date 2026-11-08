"""Cold-read saved adaptive evidence with production construction and advance guarded."""
import argparse
import importlib.abc
import json
import os
from pathlib import Path
import sys
import time
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ.setdefault(name, '1')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.surface_execution_guards import guard_production_execution
import psutil
from terrain_pipeline.adaptive_mesh import load_adaptive_run
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.runoff import _strict_json as _strict_json

@guard_production_execution()
def verify(index_record, output):
    started = time.monotonic()
    if file_sha256(index_record['path']) != index_record['expected_sha256']:
        raise ValueError('adaptive cold external index hash mismatch')
    index = _strict_json(Path(index_record['path']).read_text(encoding='utf-8'))
    runs = {'run': index_record} if index.get('schema') == 'surface-adaptive-run-index-v1' else {name: case['run'] for name, case in index['cases'].items()}
    cases = {}
    for name, pin in runs.items():
        loaded = load_adaptive_run(pin['path'], expected_sha256=pin['expected_sha256'])
        cases[name] = dict(geometries_verified=len(loaded['geometries']), snapshots_verified=len(loaded['snapshots']), epochs_verified=len(loaded['epochs']), refinement_transactions_verified=len(loaded['refinements']), first_steps_verified=len(loaded['first_steps']))
        print('cold adaptive verified ' + name, flush=True)
        del loaded
    memory = psutil.Process().memory_info()
    rss, private = (int(getattr(memory, 'peak_wset', memory.rss)), int(getattr(memory, 'peak_pagefile', memory.vms)))
    elapsed = time.monotonic() - started
    if max(rss, private) > 1073741824 or elapsed > 1800:
        raise RuntimeError('adaptive cold resource budget exceeded')
    result = dict(schema='surface-adaptive-cold-io-v1', index_record=index_record, cases=cases, pure_io_verified=True, production_execution_imports_forbidden=False, execution_modules_absent=False, solver_advanced=False, equations_sampled_only=True, canonical_source_recipe_verified=False, stage_accepted=False, uniform_coarse_convergence_claim=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False, resource=dict(elapsed_s=elapsed, peak_rss_bytes=rss, peak_private_bytes=private), code_sha256=file_sha256(Path(__file__)), execution_functions_guarded=True, production_construction_disabled=True)
    root = Path(output).resolve()
    root.relative_to(ROOT)
    root.mkdir(parents=True, exist_ok=False)
    target = root / 'report.json'
    publish_bytes(target, (json.dumps(result, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    print(json.dumps(dict(path=str(target), expected_sha256=file_sha256(target))), flush=True)
    return result
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True, type=Path)
    parser.add_argument('--index-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    verify(dict(path=str(args.index.resolve()), expected_sha256=args.index_sha256), args.output)
