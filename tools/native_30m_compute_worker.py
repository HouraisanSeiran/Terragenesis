"""Dedicated compute process: writes a candidate only, never a published release."""
import argparse
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.native_30m_resources import ComputeBudget, StageObserver, observed_call
from tools.native_30m_sources import validate_request


def run_worker(request, candidate, *, on_limit=None):
    from tools.publish_native_30m_bundle import compute_native_river, compute_saved_assembly, _write_candidate, _peak_rss_bytes, _code_pins
    diagnostic = isinstance(request, dict) and request.get('schema') == 'native-30m-diagnostic-worker-v1'
    required = {'schema', 'source_request', 'budget'} | ({'rain_mm_h'} if diagnostic else set())
    if isinstance(request, dict) and 'selection_rule' in request:
        required.add('selection_rule')
    if isinstance(request, dict) and 'source_code_identity' in request:
        required.add('source_code_identity')
    if not isinstance(request, dict) or set(request) != required:
        raise ValueError('compute_worker_request_fields')
    if request['schema'] not in ('native-30m-compute-worker-v1', 'native-30m-diagnostic-worker-v1'):
        raise ValueError('compute_worker_request_schema')
    code_before = _code_pins()
    if request.get('source_code_identity', code_before) != code_before:
        raise ValueError('compute_source_code_drift_before_start')
    source = request['source_request']
    validate_request(source)
    from tools.native_30m_selection_contract import effective_rule
    rule = None if diagnostic else effective_rule(source['parameters'])
    if 'selection_rule' in request and request['selection_rule'] != rule:
        raise ValueError('selection_rule_changed_before_compute')
    budget = ComputeBudget(**request['budget'])
    p = source['parameters']
    budget.check_window(source['source_records'], p['shape_zx'], p['coupled_intervals'])
    if Path(candidate).exists():
        raise FileExistsError(candidate)
    t0 = time.perf_counter()
    with StageObserver(budget, on_limit=on_limit) as observer:
        if diagnostic:
            from tools.native_30m_diagnostic_only import build_diagnostic_candidate
            manifest = build_diagnostic_candidate(source['source_records'], p, candidate,
                source_kind=source.get('source_kind', 'td_pages'), rain_mm_h=request['rain_mm_h'])
        else:
            if source.get('source_kind') == 'saved_assembly':
                result = compute_saved_assembly(source['source_records'][0], p)
            else:
                result = compute_native_river(source['source_records'], origin_native_xz=p['origin_native_xz'],
                    shape_zx=p['shape_zx'], coupled_intervals=p['coupled_intervals'], resample_stride=p['resample_stride'],
                    rain_mm_h=p['storm_rain_mm_h'], runoff_parameters=p.get('runoff_parameters',
                        {'infiltration_capacity_mm_h': p['infiltration_capacity_mm_h']}),
                    terminal_native_xz=p.get('terminal_native_xz'), selection_parameters=p.get('selection_parameters'))
            manifest = observed_call('candidate_serialization', _write_candidate, candidate, result)
    if _code_pins() != code_before:
        raise ValueError('compute_source_code_drift_during_run')
    expected = source['expected_numerical_identity_sha256']
    if expected is not None and manifest['identity_sha256'] != expected:
        raise ValueError('source_rebuild_numerical_identity_mismatch')
    return {'candidate_only': True, 'manifest': manifest, 'resources': observer.record(),
            'selection_rule_before_compute': rule,
            'source_code_identity_at_compute': code_before,
            'compute_wall_seconds': time.perf_counter()-t0, 'process_peak_rss_bytes': _peak_rss_bytes(),
            'rss_scope': 'dedicated compute worker, not parent cold-read or entire process tree'}


def main(argv=None):
    from terrain_pipeline.common_infra import file_sha256
    from tools.native_30m_bundle_reader import _jread, _checkpath
    from tools.publish_native_30m_bundle import _write_json_synced
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args(argv)
    report = Path(args.report).absolute()
    candidate = Path(args.candidate).absolute()
    if report.exists() or candidate.exists():
        raise FileExistsError('worker never overwrites report or candidate')

    def abort(failure):
        try:
            _write_json_synced(report, {'candidate_only': True, 'passed': False, 'failure': failure})
        finally:
            # This callback exists only in this dedicated worker CLI. The parent never
            # exposes a final destination until a successful worker is independently audited.
            os._exit(2)

    try:
        path = Path(args.request).absolute()
        _checkpath(path)
        if path.stat().st_size > 1048576:
            raise ValueError('compute_worker_request_bytes')
        if file_sha256(path) != args.sha256:
            raise ValueError('compute_worker_request_pin')
        request = _jread(path)
        os.chdir(ROOT)
        payload = run_worker(request, candidate, on_limit=abort)
        _write_json_synced(report, dict(payload, passed=True))
        print('candidate computed; not published', flush=True)
        return 0
    except Exception as exc:
        if not report.exists():
            _write_json_synced(report, {'candidate_only': True, 'passed': False, 'failure': {'reason': str(exc)}})
        print(str(exc), file=sys.stderr, flush=True)
        return 2 if isinstance(exc, (ValueError, FileExistsError, FileNotFoundError)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
