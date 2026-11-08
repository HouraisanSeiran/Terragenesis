import time
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.surface_rivers.native_30m_source import load_native_window
from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology
from terrain_pipeline.surface_rivers.native_30m_reach_selection import select_from_topology
from terrain_pipeline.runoff import run_catchment_event as run_catchment_event
from terrain_pipeline.channel_geometry import build_section
from terrain_pipeline.surface_rivers.native_30m_reach_chain import build_reach_geometry, run_reach_dynamics
from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge


def compute_native_river(page_records, *, origin_native_xz=(42173, 42874),
                         shape_zx=(1337, 1337), coupled_intervals=12, resample_stride=3,
                         rain_mm_h=None, runoff_parameters=None, terminal_native_xz=None, selection_parameters=None) -> dict:
    from tools.native_30m_resources import observed_call, active_budget
    from tools.native_30m_event_config import event_configuration
    rain_mm_h, runoff_parameters = event_configuration(rain_mm_h, runoff_parameters)
    t0 = time.perf_counter()
    origin = origin_native_xz
    shape = shape_zx
    budget = active_budget()
    budget.check_window(page_records, shape, coupled_intervals)
    source = observed_call('native_source', load_native_window, page_records, origin_native_xz=origin,
                                shape_zx=shape, world_seed=20261020)
    return _compute_from_source(source, origin=origin, shape=shape, coupled_intervals=coupled_intervals,
                                resample_stride=resample_stride, started=t0, rain_mm_h=rain_mm_h,
                                runoff_parameters=runoff_parameters, terminal_native_xz=terminal_native_xz,
                                selection_parameters=selection_parameters)


def compute_saved_assembly(record, parameters):
    from tools.native_30m_resources import observed_call, active_budget
    from tools.native_30m_saved_source import load_saved_assembly
    from tools.native_30m_event_config import event_configuration
    event_configuration(parameters.get('storm_rain_mm_h'), parameters.get('runoff_parameters',
                         {'infiltration_capacity_mm_h': parameters.get('infiltration_capacity_mm_h', 2.)}))
    active_budget().check_window([record], parameters['shape_zx'], parameters['coupled_intervals'])
    started = time.perf_counter()
    source = observed_call('saved_assembly_source', load_saved_assembly, record, parameters)
    return _compute_from_source(source, origin=parameters['origin_native_xz'], shape=parameters['shape_zx'],
                                coupled_intervals=parameters['coupled_intervals'],
                                resample_stride=parameters['resample_stride'], started=started,
                                rain_mm_h=parameters.get('storm_rain_mm_h'),
                                runoff_parameters=parameters.get('runoff_parameters',
                                    {'infiltration_capacity_mm_h': parameters.get('infiltration_capacity_mm_h', 2.)}),
                                terminal_native_xz=parameters.get('terminal_native_xz'),
                                selection_parameters=parameters.get('selection_parameters'))


def _compute_from_source(source, *, origin, shape, coupled_intervals, resample_stride, started,
                         rain_mm_h=None, runoff_parameters=None, terminal_native_xz=None, selection_parameters=None):
    from tools.native_30m_resources import observed_call, active_budget
    t0 = started
    budget = active_budget()
    field = source["field"]
    resolved_mask = source["resolved_mask"]
    assembly_digest = source["assembly_digest"]
    topology = observed_call('strict_topology', build_strict_topology, field, resolved_mask)
    from tools.native_30m_selection_contract import selection_arguments
    selector_record = {}
    if terminal_native_xz is not None:
        selector_record['terminal_native_xz'] = list(terminal_native_xz)
    if selection_parameters is not None:
        selector_record['selection_parameters'] = dict(selection_parameters)
    selector_args = selection_arguments(dict(selector_record, origin_native_xz=list(origin), shape_zx=list(shape)))
    selection = observed_call('reach_selection', select_from_topology, field, topology, origin_native_xz=origin, **selector_args)
    chosen = selection["chosen"]
    budget.check_catchment(int(chosen['catchment_cells']))
    r0, r1, c0, c1 = (int(v) for v in chosen["subwindow_rc"])
    h = field[r0:r1, c0:c1].astype(np.float64, copy=True)
    raw = np.asarray(topology["receiver"])[r0:r1, c0:c1].astype(np.int64, copy=False)
    rr = raw // field.shape[1]
    cc = raw % field.shape[1]
    inside = (raw >= 0) & (rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)
    basin = chosen["catchment_mask"][r0:r1, c0:c1].copy()
    line = chosen["flowline_mask"][r0:r1, c0:c1].copy()
    if np.any(basin & (raw >= 0) & ~inside):
        raise ValueError("catchment_receiver_leaves_subwindow")
    sub_rec = np.where(inside, (rr - r0) * (c1 - c0) + (cc - c0), -1).astype(np.int64, copy=False)
    source_support = np.asarray(resolved_mask[r0:r1, c0:c1], dtype=bool)
    if not np.all((~basin) | source_support):
        raise ValueError("catchment_not_complete")
    raw_seed = np.asarray(topology["upstream_unknown_mask"])
    if np.any(raw_seed[r0:r1, c0:c1] & basin):
        raise ValueError("catchment_not_complete")
    suborigin = (origin[0] + c0, origin[1] + r0)
    from tools.native_30m_event_config import event_configuration
    rain, rp = event_configuration(rain_mm_h, runoff_parameters)
    event = observed_call('runoff_event', run_catchment_event, h, sub_rec, basin, line,
                                origin_native_xz=suborigin,
                                source_identity_sha256=assembly_digest,
                                world_seed=20261020, rain_mm_h=rain, dt_s=3600.0,
                                runoff_parameters=rp)
    section = observed_call('section', build_section, field, selection, event["design_q_m3_s"],
                             origin_native_xz=origin,
                             section_parameters={"resample_stride": resample_stride})
    budget.check_nodes(int(section['arrays']['node_cell_ids'].size))
    geom = observed_call('carved_geometry', build_reach_geometry, field, resolved_mask, section,
                                origin_native_xz=origin,
                                source_identity_sha256=assembly_digest,
                                world_seed=20261020)
    topo_rec = np.asarray(topology["receiver"])
    valid = np.asarray(topology["valid_mask"]).astype(np.float64)
    acc = observed_call('node_attribution', accumulate_network_discharge,
        topo_rec, valid, topology["valid_mask"],
        terminal_kind=topology["terminal_kind"],
        upstream_unknown_mask=topology["upstream_unknown_mask"],
    )
    counts_field = np.asarray(acc["known_routed_q_m3_s"], dtype=np.float64)
    node_ids = np.asarray(section["arrays"]["node_cell_ids"], dtype=np.int64)
    node_counts = counts_field.reshape(-1)[node_ids]
    if not np.allclose(node_counts, np.round(node_counts)):
        raise ValueError("node accumulated counts are not integral")
    node_counts = np.round(node_counts).astype(np.int64)
    lateral_counts = np.r_[node_counts[0], np.diff(node_counts)].astype(np.int64)
    if np.any(lateral_counts <= 0):
        raise ValueError("lateral cell counts must all be positive")
    terminal_cells = int(event["terminal"]["catchment_cells"])
    if int(lateral_counts.sum()) != terminal_cells:
        raise ValueError("lateral counts sum does not match terminal catchment cells")
    dynamics_result = observed_call('coupled_dynamics', run_reach_dynamics, geom, event, lateral_counts,
                                         coupled_intervals=coupled_intervals)
    elapsed = time.perf_counter() - t0
    from dataclasses import asdict
    event_override = ({'runoff_parameters': asdict(rp)}
                      if asdict(rp) != asdict(RunoffParameters(infiltration_capacity_mm_h=2.)) else {})
    return {
        "source": source, "topology": topology, "selection": selection,
        "event": event, "section": section, "geometry": geom, "reach": dynamics_result,
        "parameters": {
            'world_seed': 20261020, 'origin_native_xz': list(origin), 'shape_zx': list(shape), **selector_record,
            "coupled_intervals": coupled_intervals, "resample_stride": resample_stride,
            "storm_rain_mm_h": rain.tolist(), "dt_s": 3600.0,
            "infiltration_capacity_mm_h": rp.infiltration_capacity_mm_h, **event_override,
        },
        "wall_seconds": elapsed,
    }


import hashlib
import json
import os


def _write_candidate(directory, result) -> dict:
    """Write a candidate; caller must independently cold-read and audit before commit."""
    from terrain_pipeline.artifacts.contracts import canonical_json, digest
    from terrain_pipeline.channel_geometry import save_monotone_union
    from terrain_pipeline.surface_rivers.world_channel_dynamics import save_nodal_reach
    from terrain_pipeline.surface_rivers.metric_network_discharge_product import (
        build_discharge_product, save_discharge_product,
    )
    directory = Path(directory)
    if directory.exists():
        for child in directory.iterdir():
            raise RuntimeError(f"refusing: directory not empty: {child}")
    else:
        directory.mkdir(parents=True, exist_ok=False)
    dyn_meta = result["reach"]["dynamics"]["metadata"]
    if dyn_meta.get("status") != "complete":
        raise RuntimeError(f"dynamics.metadata.status != 'complete': {dyn_meta.get('status')!r}")
    src = result["source"]
    topo = result["topology"]
    sel = result["selection"]
    chosen = sel["chosen"]
    candidates = sel["candidates"]
    event = result["event"]
    section = result["section"]
    g = result["geometry"]
    reach = result["reach"]
    params = result["parameters"]
    wall_seconds = float(result.get("wall_seconds", 0.0))
    source_records = src["source_records"]
    source_identity = digest(source_records)

    def _fspath(p: Path):
        return open(p, "rb")

    def _finalize_json(p: Path, obj):
        data = canonical_json(obj).encode("utf-8") if isinstance(canonical_json(obj), str) else canonical_json(obj)
        if isinstance(data, str):
            data = data.encode("utf-8")
        with open(p, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

    def _ndarr_safe(a):
        a = np.asarray(a)
        if a.dtype.hasobject:
            raise TypeError("object array not allowed in NPZ")
        return a

    def _save_npz(p: Path, arrays: dict):
        clean = {k: _ndarr_safe(v) for k, v in arrays.items() if v is not None}
        with open(p, "wb") as f:
            np.savez(f, **clean)
            f.flush()
            os.fsync(f.fileno())

    def _jsonify(x, *, _depth=0):
        if _depth > 32:
            raise ValueError("jsonify depth exceeded")
        if isinstance(x, (bool, int, float, str)) or x is None:
            if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
                raise ValueError('nonfinite JSON value')
            return x
        if isinstance(x, (np.bool_,)):
            return bool(x)
        if isinstance(x, (np.integer,)):
            return int(x)
        if isinstance(x, (np.floating,)):
            v = float(x)
            if np.isnan(v) or np.isinf(v):
                raise ValueError('nonfinite JSON value')
            return v
        if isinstance(x, np.ndarray):
            if x.dtype == object:
                raise TypeError("object array in jsonify")
            if x.size > 1000:
                raise ValueError("array too large for jsonify; use NPZ")
            return _jsonify(x.tolist(), _depth=_depth + 1)
        if isinstance(x, dict):
            return {str(k): _jsonify(v, _depth=_depth + 1) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [_jsonify(v, _depth=_depth + 1) for v in x]
        raise TypeError("unsupported JSON value")

    source_np = {"field": src["field"], "resolved_mask": src["resolved_mask"],
                 "origin_native_xz": src["origin_native_xz"]}
    _save_npz(directory / "source.npz", source_np)
    src_json = {"assembly_digest": src.get("assembly_digest"),
                "policy": _jsonify(src.get("policy", {})),
                "source_records": _jsonify(source_records)}
    _finalize_json(directory / "source.json", src_json)
    topo_np_keys = ["receiver", "valid_mask", "terminal_kind", "upstream_unknown_mask"]
    topo_np = {k: topo[k] for k in topo_np_keys}
    _save_npz(directory / "topology.npz", topo_np)
    topo_json = {k: _jsonify(v) for k, v in topo.items() if k not in topo_np_keys}
    _finalize_json(directory / "topology.json", topo_json)
    sel_np = {"catchment_mask": chosen["catchment_mask"],
              "flowline_mask": chosen["flowline_mask"], "stem_flat_cells": chosen["stem_flat_cells"]}
    _save_npz(directory / "selection.npz", sel_np)
    mask_keys = {"catchment_mask", "flowline_mask", "stem_flat_cells"}
    chosen_scalars = {k: _jsonify(v) for k, v in chosen.items() if k not in mask_keys}
    sel_json = {"chosen": chosen_scalars, "candidates": _jsonify(candidates)}
    _finalize_json(directory / "selection.json", sel_json)
    runoff = event.get("runoff", {})
    runoff_params = runoff.get("parameters", {})
    ev_np = {
        "local_q_m3_s": event["local_q_m3_s"], "active_cells": event["active_cells"],
        "instantaneous_terminal_q_m3_s": event["instantaneous_terminal_q_m3_s"],
        "routed_terminal_q_m3_s": event["routed_terminal_q_m3_s"],
        "rain_mm_h": event["rain_mm_h"], "time_edges_s": event["time"]["time_edges_s"],
    }
    for k, v in runoff.items():
        if k == "parameters":
            continue
        if isinstance(v, np.ndarray):
            ev_np[f"bucket_{k}"] = v
    _save_npz(directory / "event.npz", ev_np)
    time_meta = {k: _jsonify(v) for k, v in event["time"].items() if k != "time_edges_s"}
    ev_json = {
        "identity": event.get("identity"),
        "event_identity": event.get("event_identity_sha256") or event.get("event_identity"),
        "source": _jsonify(event.get("source")),
        "design_q_m3_s": _jsonify(event.get("design_q_m3_s")),
        "design_q_interval_index": _jsonify(event.get("design_q_interval_index")),
        "runoff_parameters": _jsonify(runoff_params), "time_meta": time_meta,
    }
    _finalize_json(directory / "event.json", ev_json)
    sec_arrays = section.get("arrays", {})
    _save_npz(directory / "section.npz", sec_arrays)
    _finalize_json(directory / "section.json", _jsonify(section.get("metadata", {})))
    save_monotone_union(directory / "geometry.npz", g["geometry"])
    rc_np = {
        "node_bed_m": g["node_bed_m"], "node_distance_m": g["node_distance_m"],
        "node_length_m": g["node_length_m"], "node_slope_per_m": g["node_slope_per_m"],
        "initial_alluvium_bulk_m3": reach["initial_alluvium_bulk_m3"],
        "rock_floor_m": reach["rock_floor_m"], "lateral_cell_counts": reach["lateral_cell_counts"],
    }
    _save_npz(directory / "reach_context.npz", rc_np)
    rc_json = {"reach_metadata": _jsonify(reach.get("metadata", {})),
               "geometry_metadata": _jsonify(g.get("metadata", {})), "crop_rc": _jsonify(g.get("crop_rc"))}
    _finalize_json(directory / "reach_context.json", rc_json)
    save_nodal_reach(directory / "dynamics.npz", reach["dynamics"])
    diag_dir = directory / "discharge-diagnostic"
    # save_discharge_product creates the destination; it must not exist yet.
    p = event["diagnostic"]["peak_interval_payload"]
    unknown = np.array(p["upstream_unknown_mask"], copy=True)
    valid = np.array(p["valid_mask"], copy=True)
    local = p["local_q_m3_s"]
    rec = p["receiver"]
    kinds = p["terminal_kind"]
    valid_arr = np.asarray(valid, dtype=bool)
    unknown_arr = np.asarray(unknown, dtype=bool)
    edge_valid = np.zeros_like(valid_arr)
    edge_valid[0, :] = True
    edge_valid[-1, :] = True
    edge_valid[:, 0] = True
    edge_valid[:, -1] = True
    unknown_arr = (unknown_arr | edge_valid) & valid_arr
    product = build_discharge_product(
        rec, local, valid_arr, kinds, unknown_arr,
        origin_native_cells=event["source"]["origin_native_xz"], world_seed=20261020,
        interval_seconds=p["interval_seconds"], source_sha256=result["source"]["assembly_digest"],
        forcing_semantics=("instantaneous soil bucket local Q at the design-peak interval; "
                           "source SHA is assembly content identity; outside catchment local Q deliberately zero"),
    )
    save_discharge_product(diag_dir, product)
    root_files: dict = {}
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(directory).as_posix()
        if rel == "bundle.json":
            continue
        with _fspath(path) as f:
            h = hashlib.sha256(f.read()).hexdigest()
        root_files[rel] = h
    stage_identities = {
        "source_assembly": result["source"]["assembly_digest"],
        "event": event.get("event_identity_sha256") or event.get("event_identity"),
        "geometry": g["geometry"]["identity_sha256"],
        "dynamics": reach["dynamics"]["identity_sha256"], "diagnostic": product["identity_sha256"],
    }
    capabilities = {"hydraulic_ready": False, "natural_outlet_certified": False,
                    "publishable": False, "finite_graph_only": True}
    checks = {"computed": True, "cold_read_verified": False, "independent_audit_verified": False}
    schema = "native-30m-river-bundle-v1"
    manifest_core = {"schema": schema, "parameters": _jsonify(params),
                     "source_records": _jsonify(source_records), "stage_identities": stage_identities,
                     "files": root_files, "capabilities": capabilities}
    identity_sha256 = digest(manifest_core)
    record = dict(manifest_core)
    record["checks"] = checks
    record["identity_sha256"] = identity_sha256
    record["runtime"] = {"wall_seconds": wall_seconds}
    _finalize_json(directory / "bundle.json", record)
    return record


def _write_json_synced(path, value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    with open(path, 'xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _code_pins():
    from terrain_pipeline.common_infra import file_sha256
    paths = list((ROOT / 'terrain_pipeline').rglob('*.py'))
    paths += [ROOT / 'tools' / name for name in (
        'publish_native_30m_bundle.py', 'native_30m_bundle_reader.py',
        'native_30m_bundle_validation.py', 'native_30m_sources.py', 'native_30m_query.py',
        'native_30m_resources.py', 'native_30m_compute_worker.py', 'native_30m_declarations.py',
        'native_30m_hydraulic_reference.py', 'native_30m_graph_reference.py',
        'native_30m_section_reference.py', 'audit_native_30m_spatial.py', 'native_30m_saved_source.py',
        'native_30m_diagnostic_only.py', 'native_30m_selection_contract.py', 'native_30m_event_config.py',
        'audit_native_30m_bundle.py', 'view_native_30m_bundle.py')]
    return {p.relative_to(ROOT).as_posix(): file_sha256(p) for p in sorted(paths)}


def _independent_audit(data_dir, manifest, report_path):
    import subprocess
    import tempfile
    from tools.native_30m_bundle_reader import _jread
    report_path = Path(report_path)
    if report_path.exists():
        raise FileExistsError(report_path)
    with tempfile.TemporaryDirectory(prefix='native-river-independent-') as tmp:
        ledger_path, spatial_path = Path(tmp) / 'ledger.json', Path(tmp) / 'spatial.json'
        commands = [
            [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/audit_native_30m_bundle.py'),
             '--dynamics', str(data_dir / 'dynamics.npz'), '--sha256', manifest['files']['dynamics.npz'],
             '--output-report', str(ledger_path)],
            [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/audit_native_30m_spatial.py'),
             '--data', str(data_dir), '--identity', manifest['identity_sha256'], '--output', str(spatial_path)],
        ]
        for command in commands:
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                       encoding='utf-8', timeout=180, check=False)
            if completed.returncode != 0:
                raise RuntimeError('independent audit failed: ' + completed.stderr[-4000:])
        report, spatial = _jread(ledger_path), _jread(spatial_path)
        if report.get('passed') is not True or spatial.get('passed') is not True:
            raise RuntimeError('independent audit did not pass')
        report['spatial_section_reference'] = spatial
        _write_json_synced(report_path, report)
    return report


def publish_release(candidate, destination, *, expected_identity_sha256=None, provenance=None):
    """Validate a private copy, audit in a new process, then commit one directory.

    The numerical candidate remains byte-for-byte unchanged inside data/.
    Release observations and code pins are separate from numerical identity.
    """
    import shutil
    import tempfile
    from terrain_pipeline.artifacts.contracts import digest
    from terrain_pipeline.common_infra import file_sha256
    from tools.native_30m_bundle_reader import load_candidate
    target = Path(destination).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    code_before_publication = _code_pins()
    computed_code = (provenance or {}).get('source_code_identity_at_compute')
    if computed_code is not None and computed_code != code_before_publication:
        raise ValueError('compute_source_code_drift_before_publication')
    original = load_candidate(candidate, expected_identity_sha256=expected_identity_sha256)
    numerical_identity = original['manifest']['identity_sha256']
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.' + target.name + '-', dir=target.parent))
    try:
        shutil.copytree(original['directory'], staging / 'data', symlinks=False)
        verified = load_candidate(staging / 'data', expected_identity_sha256=numerical_identity)
        report = _independent_audit(staging / 'data', verified['manifest'], staging / 'audit.json')
        from tools.native_30m_sources import source_request_from_candidate, save_source_request
        source_pin = save_source_request(staging / 'source-request.json', source_request_from_candidate(verified))
        from tools.native_30m_declarations import release_declarations
        if _code_pins() != code_before_publication:
            raise ValueError('validation_source_code_drift_during_publication')
        body = {
            'schema': 'native-30m-finite-release-v4', 'numerical_identity_sha256': numerical_identity,
            'selection_verification': verified['selection_verification'],
            'declarations': release_declarations(verified),
            'source_request_sha256': source_pin,
            'cross_stage_verification': verified['verification'],
            'data_manifest_sha256': file_sha256(staging / 'data/bundle.json'),
            'audit_sha256': file_sha256(staging / 'audit.json'), 'source_code_identity': code_before_publication,
            'checks': {'strict_cold_read': True, 'independent_three_ledgers': report['passed']},
            'scope': 'finite 30m river; 72h runoff; first 12h or fewer coupled; initial PL mesh only',
            'limitations': ['No natural outlet or infinite-world certification',
                            'No backwater, floodplain or lake coupling',
                            'Uncalibrated material and erosion rates; magnitude not validated',
                            'Cold read is not a dynamic solver replay'],
            'provenance': provenance or {'mode': 'validated_candidate_copy', 'compute_rss_measured': False},
        }
        _write_json_synced(staging / 'release.json', dict(body, identity_sha256=digest(body)))
        # Flush all private files before exposing the final directory.
        for path in staging.rglob('*'):
            if path.is_file():
                with open(path, 'rb+') as stream:
                    os.fsync(stream.fileno())
        if target.exists() or target.is_symlink():
            raise FileExistsError(target)
        os.rename(staging, target)
        return body
    except Exception as exc:
        # Keep failure evidence separate from the never-created final destination.
        _write_json_synced(staging / 'failure.json', {'success': False, 'error': str(exc)})
        raise


def inspect_release(directory, *, require_source_pins=False):
    from terrain_pipeline.artifacts.contracts import digest
    from terrain_pipeline.common_infra import file_sha256
    from tools.native_30m_bundle_reader import _jread, _checkpath, load_candidate
    directory = Path(directory).absolute()
    _checkpath(directory, isdir_ok=True)
    if (directory/'diagnostic.json').exists():
        from tools.native_30m_diagnostic_only import load_diagnostic
        env = load_diagnostic(directory)
        record = env['manifest']
        current = _code_pins()
        drift = sorted(k for k, v in record['source_code_identity'].items() if current.get(k) != v)
        if require_source_pins and drift:
            raise ValueError('source_code_drift: ' + ', '.join(drift))
        return {'identity_sha256': record['identity_sha256'],
                'numerical_identity_sha256': record['diagnostic_identity_sha256'],
                'profile': 'diagnostic-only', 'is_product': False, 'role': record['role'],
                'cold_read_verified_now': True, 'source_code_drift': drift,
                'independent_audit_saved_passed': False, 'independent_audit_rerun_now': False,
                'not_computed': record['not_computed'], 'rain_semantics': 'declared_conversion',
                'limitations': ['diagnostic conversion only, not a river chain; no design Q, hydraulics or sediment']}
    for name in ('release.json', 'audit.json'):
        _checkpath(directory / name)
    record = _jread(directory / 'release.json')
    schema = record.get('schema')
    if schema not in ('native-30m-finite-release-v1', 'native-30m-finite-release-v2', 'native-30m-finite-release-v3', 'native-30m-finite-release-v4'):
        raise ValueError('release schema')
    entries = {'data', 'audit.json', 'release.json'}
    if schema in ('native-30m-finite-release-v2', 'native-30m-finite-release-v3', 'native-30m-finite-release-v4'):
        entries.add('source-request.json')
        _checkpath(directory / 'source-request.json')
    if {p.name for p in directory.iterdir()} != entries:
        raise ValueError('release entries')
    body = {k: v for k, v in record.items() if k != 'identity_sha256'}
    if digest(body) != record.get('identity_sha256'):
        raise ValueError('release identity/schema')
    for name, pin_key in (('data/bundle.json', 'data_manifest_sha256'), ('audit.json', 'audit_sha256')):
        if file_sha256(directory / name) != record[pin_key]:
            raise ValueError('release file identity: ' + name)
    audit = _jread(directory / 'audit.json')
    if audit.get('passed') is not True:
        raise ValueError('saved audit did not pass')
    env = load_candidate(directory / 'data', expected_identity_sha256=record['numerical_identity_sha256'])
    if schema in ('native-30m-finite-release-v2', 'native-30m-finite-release-v3', 'native-30m-finite-release-v4'):
        from tools.native_30m_sources import source_request_from_candidate
        if file_sha256(directory / 'source-request.json') != record['source_request_sha256']:
            raise ValueError('release source request hash')
        if _jread(directory / 'source-request.json') != source_request_from_candidate(env):
            raise ValueError('release source request binding')
        if record['cross_stage_verification'] != env['verification']:
            raise ValueError('release cross-stage verification binding')
    if schema in ('native-30m-finite-release-v3', 'native-30m-finite-release-v4'):
        from tools.native_30m_declarations import release_declarations
        if record['declarations'] != release_declarations(env):
            raise ValueError('release declaration binding')
    if schema == 'native-30m-finite-release-v4' and record['selection_verification'] != env['selection_verification']:
        raise ValueError('selection_rule_or_table_binding')
    current = _code_pins()
    drift = sorted(k for k, v in record['source_code_identity'].items() if current.get(k) != v)
    if require_source_pins and drift:
        raise ValueError('source_code_drift: ' + ', '.join(drift))
    import numpy as np
    dyn = env['dynamics']['arrays']
    return {'identity_sha256': record['identity_sha256'],
            'numerical_identity_sha256': record['numerical_identity_sha256'],
            'cold_read_verified_now': True, 'independent_audit_saved_passed': True,
            'independent_audit_rerun_now': False, 'source_code_drift': drift,
            'coupled_window_seconds': [float(dyn['time_seconds'][0]), float(dyn['time_seconds'][-1])],
            'max_cumulative_bed_change_m': float(np.max(np.abs(dyn['node_bed_m'][-1]-dyn['node_bed_m'][0]))),
            'max_interval_bed_change_m': float(np.max(np.abs(np.diff(dyn['node_bed_m'], axis=0)))),
            'capabilities': env['manifest']['capabilities'], 'limitations': record['limitations']}


def _compute_candidate_in_worker(records, parameters, candidate, budget, *, expected_identity=None, source_kind='td_pages',
                                 profile='full', rain_mm_h=None):
    from dataclasses import asdict
    import subprocess
    from tools.native_30m_bundle_reader import _jread
    from tools.native_30m_sources import compute_source_request, validate_request
    from terrain_pipeline.common_infra import file_sha256
    source_request = compute_source_request(records, parameters, expected_identity)
    if source_kind == 'saved_assembly':
        source_request.update(source_kind='saved_assembly')
        if source_request['schema'] not in ('native-30m-source-request-v3', 'native-30m-source-request-v4'):
            source_request['schema'] = 'native-30m-source-request-v2'
    elif source_kind != 'td_pages':
        raise ValueError('source_kind_not_supported')
    validate_request(source_request)
    request = {'schema': 'native-30m-compute-worker-v1',
               'source_request': source_request, 'budget': asdict(budget)}
    if profile == 'diagnostic-only':
        request.update(schema='native-30m-diagnostic-worker-v1', rain_mm_h=rain_mm_h)
    elif profile != 'full':
        raise ValueError('profile_not_supported')
    else:
        from tools.native_30m_selection_contract import effective_rule
        request['selection_rule'] = effective_rule(source_request['parameters'])
    request['source_code_identity'] = _code_pins()
    candidate = Path(candidate).absolute()
    request_path = candidate.parent / 'compute-request.json'
    report_path = candidate.parent / 'compute-report.json'
    _write_json_synced(request_path, request)
    command = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/native_30m_compute_worker.py'),
               '--request', str(request_path), '--sha256', file_sha256(request_path),
               '--candidate', str(candidate), '--report', str(report_path)]
    try:
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                 encoding='utf-8', timeout=budget.max_seconds + 10, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('budget_seconds: compute worker timed out') from exc
    report = _jread(report_path) if report_path.is_file() else None
    if process.returncode != 0 or not isinstance(report, dict) or report.get('passed') is not True:
        reason = (report or {}).get('failure', {}).get('reason', 'compute_worker_failed')
        raise ValueError(str(reason) + ': ' + process.stderr[-2000:])
    if report.get('candidate_only') is not True or report['resources']['failure'] is not None:
        raise ValueError('invalid compute worker report')
    if (report.get('source_code_identity_at_compute') != request['source_code_identity'] or
            _code_pins() != request['source_code_identity']):
        raise ValueError('compute_source_code_drift_before_publication')
    return report


def _record_compute_failure(destination, error):
    import tempfile
    target = Path(destination).absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    failed = Path(tempfile.mkdtemp(prefix='.' + target.name + '-failed-', dir=target.parent))
    _write_json_synced(failed / 'failure.json', {'success': False, 'phase': 'compute', 'error': str(error)})
    return failed


def _peak_rss_bytes():
    if os.name != 'nt':
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024))
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
            'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    get_process = ctypes.windll.kernel32.GetCurrentProcess
    get_process.restype = ctypes.c_void_p
    if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(get_process()), ctypes.byref(counters), counters.cb):
        raise OSError('cannot measure peak working set')
    return int(counters.PeakWorkingSetSize)


def main(argv=None):
    import argparse
    import tempfile
    from tools.native_30m_bundle_reader import load_candidate, _jread
    parser = argparse.ArgumentParser(description='Finite native 30m river pipeline; not a certification of stage one.')
    parser.add_argument('--mode', default='publish', choices=('publish', 'rerun', 'source-rebuild', 'inspect', 'audit'))
    parser.add_argument('--source-request')
    parser.add_argument('--source-request-sha256')
    parser.add_argument('--assembly')
    parser.add_argument('--profile', choices=('full', 'diagnostic-only'))
    parser.add_argument('--rain-semantics', choices=('soil_bucket_catchment', 'declared_conversion'))
    parser.add_argument('--rain-mm-h', type=float)
    parser.add_argument('--storm-table')
    parser.add_argument('--runoff-parameters')
    parser.add_argument('--stages')
    parser.add_argument('--assembly-sha256')
    parser.add_argument('--candidate')
    parser.add_argument('--bundle')
    parser.add_argument('--identity')
    parser.add_argument('--output-dir')
    parser.add_argument('--td-page', action='append', default=[])
    parser.add_argument('--page-sha256', action='append', default=[])
    parser.add_argument('--require-source-pins', action='store_true')
    parser.add_argument('--point', nargs=2, type=float, metavar=('X', 'Z'))
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--scope')
    parser.add_argument('--semantics')
    parser.add_argument('--as-natural-outlet', action='store_true')
    parser.add_argument('--census', action='store_true')
    parser.add_argument('--world-seed', type=int)
    parser.add_argument('--spacing-m', type=float)
    parser.add_argument('--origin-native-xz', nargs=2, type=int, metavar=('X', 'Z'))
    window = parser.add_mutually_exclusive_group()
    window.add_argument('--window-nodes', type=int)
    window.add_argument('--window-shape', nargs=2, type=int, metavar=('ROWS', 'COLS'))
    parser.add_argument('--coupled-intervals', type=int)
    parser.add_argument('--resample-stride', type=int)
    parser.add_argument('--terminal-native-xz', nargs=2, type=int, metavar=('X', 'Z'))
    parser.add_argument('--reach-rule-file')
    parser.add_argument('--dt-s', type=float)
    budget_fields = {'max_pages': int, 'max_window_nodes': int, 'max_window_cells': int,
                     'max_bucket_cells': int, 'max_bucket_entries': int, 'max_channel_nodes': int,
                     'max_coupled_intervals': int, 'max_local_q_bytes': int, 'max_trace_reserved_bytes': int,
                     'max_rss_bytes': int, 'max_seconds': float}
    for name, kind in budget_fields.items():
        parser.add_argument('--' + name.replace('_', '-'), type=kind,
                            help='compute worker budget only; no silent spatial or temporal downgrade')
    args = parser.parse_args(argv)
    try:
        from tools.native_30m_resources import ComputeBudget
        overrides = {name: getattr(args, name) for name in budget_fields if getattr(args, name) is not None}
        budget = ComputeBudget(**overrides)
        budget.validate()
        profile = args.profile or 'full'
        semantics = args.rain_semantics or ('declared_conversion' if profile == 'diagnostic-only' else 'soil_bucket_catchment')
        if any(v is not None for v in (args.profile, args.rain_semantics, args.rain_mm_h, args.stages,
                                        args.storm_table, args.runoff_parameters)) and args.mode != 'publish':
            raise ValueError('profile/forcing flags require publish')
        if semantics != ('declared_conversion' if profile == 'diagnostic-only' else 'soil_bucket_catchment'):
            raise ValueError('profile_stage_conflict')
        if args.candidate and any(v is not None for v in (args.profile, args.rain_semantics, args.rain_mm_h, args.stages,
                                                         args.storm_table, args.runoff_parameters)):
            raise ValueError('candidate profile cannot be overridden')
        if profile == 'diagnostic-only':
            import math
            if args.rain_mm_h is None or not math.isfinite(args.rain_mm_h) or args.rain_mm_h < 0:
                raise ValueError('diagnostic-only requires finite nonnegative --rain-mm-h')
            if (args.coupled_intervals is not None or args.resample_stride is not None or args.storm_table or
                    args.runoff_parameters or args.terminal_native_xz is not None or args.reach_rule_file):
                raise ValueError('profile_stage_conflict')
        elif args.rain_mm_h is not None:
            raise ValueError('profile_stage_conflict')
        if args.stages is not None:
            stages = set(args.stages.split(','))
            if stages & {'lake', 'backwater', 'floodplain_2d', 'natural_outlet', 'infinite_world'}:
                from tools.native_30m_query import ScopeRefusal
                raise ScopeRefusal('stage_not_implemented')
            diagnostic_stages = {'source', 'topology', 'runoff', 'diagnostic_q'}
            full_stages = diagnostic_stages | {'design_q', 'reach_selection', 'reach_section', 'hydraulics', 'sediment', 'bed'}
            if profile == 'diagnostic-only' and stages != diagnostic_stages:
                raise ValueError('profile_stage_conflict')
            if profile == 'full' and stages != full_stages:
                raise ValueError('full profile requires its complete stage chain')
        scenario_flags = (args.world_seed, args.spacing_m, args.origin_native_xz, args.window_nodes,
                          args.window_shape, args.coupled_intervals, args.resample_stride, args.dt_s,
                          args.terminal_native_xz, args.reach_rule_file)
        if any(v is not None for v in scenario_flags) and (args.mode != 'publish' or args.candidate):
            raise ValueError('scenario overrides require publish from pinned pages; source rebuild uses recorded parameters')
        if args.world_seed is not None and args.world_seed != 20261020:
            raise ValueError('unsupported_scenario')
        if args.spacing_m is not None and args.spacing_m != 30.0:
            raise ValueError('spacing_mismatch')
        if args.dt_s is not None and args.dt_s != 3600.0:
            raise ValueError('unsupported_scenario:dt_s')
        if overrides and (args.mode in ('inspect', 'audit') or (args.mode == 'publish' and args.candidate)):
            raise ValueError('compute budget flags require a source computation')
        if bool(args.assembly) != bool(args.assembly_sha256):
            raise ValueError('assembly and external sha256 required together')
        if args.assembly and (args.mode != 'publish' or args.candidate or args.bundle or args.td_page or args.page_sha256):
            raise ValueError('saved assembly cannot be mixed with pages, bundles or candidates')
        if args.mode != 'source-rebuild' and (args.source_request or args.source_request_sha256):
            raise ValueError('source request flags require source-rebuild')
        if args.mode != 'inspect' and (args.point is not None or args.census or args.native or
                args.scope is not None or args.semantics is not None or args.as_natural_outlet):
            raise ValueError('query flags require inspect')
        if args.point is None and (args.native or args.scope is not None or args.semantics is not None or args.as_natural_outlet):
            raise ValueError('point-specific flags require --point')
        if args.point is not None and args.census:
            raise ValueError('choose --point or --census')
        if args.mode in ('inspect', 'audit'):
            if not args.bundle or args.output_dir or args.candidate or args.td_page or args.page_sha256:
                raise ValueError('inspect/audit requires --bundle only (plus optional checks/query)')
            result = inspect_release(args.bundle, require_source_pins=args.require_source_pins)
            if args.identity and args.identity != result['numerical_identity_sha256']:
                raise ValueError('external numerical identity mismatch')
            if args.point is not None or args.census or args.mode == 'audit':
                if result.get('profile') == 'diagnostic-only':
                    if args.mode == 'audit':
                        raise ValueError('stage_absent: diagnostic-only has no water/sediment/bed ledgers')
                    from tools.native_30m_diagnostic_only import load_diagnostic
                    env = load_diagnostic(args.bundle)
                else:
                    env = load_candidate(Path(args.bundle) / 'data', expected_identity_sha256=result['numerical_identity_sha256'])
                if args.point is not None:
                    from tools.native_30m_query import query_point
                    result['point'] = query_point(env, *args.point, native=args.native,
                        scope=args.scope or 'terrain_surface', semantics=args.semantics,
                        as_natural_outlet=args.as_natural_outlet)
                elif args.census:
                    from tools.native_30m_query import census
                    result['census'] = census(env)
                else:
                    with tempfile.TemporaryDirectory(prefix='native-30m-audit-') as tmp:
                        result['audit'] = _independent_audit(Path(args.bundle).absolute() / 'data',
                            env['manifest'], Path(tmp) / 'audit.json')
                    result['independent_audit_rerun_now'] = True
                    result['independent_audit_scope'] = 'raw trace ledgers and Manning; full finite graph and section reference'
        else:
            if not args.output_dir:
                raise ValueError('--output-dir required')
            if Path(args.output_dir).exists():
                raise FileExistsError(args.output_dir)
            if args.mode == 'publish' and args.candidate:
                if args.bundle or args.td_page or args.page_sha256:
                    raise ValueError('candidate cannot be mixed with source input')
                result = publish_release(args.candidate, args.output_dir, expected_identity_sha256=args.identity)
            else:
                reference = None
                expected_numerical = None
                source_kind = 'td_pages'
                if args.mode == 'source-rebuild':
                    if (not args.source_request or not args.source_request_sha256 or args.bundle or
                            args.candidate or args.td_page or args.page_sha256):
                        raise ValueError('source-rebuild requires only pinned source request and output')
                    from tools.native_30m_sources import load_source_request
                    request = load_source_request(args.source_request, expected_sha256=args.source_request_sha256)
                    records, params = request['source_records'], request['parameters']
                    source_kind = request.get('source_kind', 'td_pages')
                    expected_numerical = request['expected_numerical_identity_sha256']
                    if args.identity and expected_numerical and args.identity != expected_numerical:
                        raise ValueError('source request external numerical identity mismatch')
                    expected_numerical = args.identity or expected_numerical
                elif args.mode == 'rerun':
                    if not args.bundle or args.candidate or args.td_page or args.page_sha256:
                        raise ValueError('rerun requires --bundle and --output-dir')
                    inspect_release(args.bundle, require_source_pins=args.require_source_pins)
                    reference = load_candidate(Path(args.bundle) / 'data', expected_identity_sha256=args.identity)
                    records = [{k: r[k] for k in ('path', 'sha256')} for r in reference['manifest']['source_records']]
                    params = reference['manifest']['parameters']
                    from tools.native_30m_sources import source_request_from_candidate
                    source_kind = source_request_from_candidate(reference).get('source_kind', 'td_pages')
                    expected_numerical = reference['manifest']['identity_sha256']
                else:
                    if args.bundle or args.candidate or not (args.td_page or args.assembly):
                        raise ValueError('publish requires pinned --td-page inputs, --assembly or --candidate')
                    pins = {}
                    for item in args.page_sha256:
                        path, sha = item.rsplit('=', 1)
                        if path in pins:
                            raise ValueError('duplicate source pin')
                        pins[path] = sha
                    if set(pins) != set(args.td_page) or len(set(args.td_page)) != len(args.td_page):
                        raise ValueError('exactly one pin per page required')
                    records = [{'path': path, 'sha256': pins[path]} for path in args.td_page]
                    if args.assembly:
                        records = [{'path': args.assembly, 'sha256': args.assembly_sha256}]
                        source_kind = 'saved_assembly'
                    shape = args.window_shape or ([args.window_nodes, args.window_nodes] if args.window_nodes is not None else [1337, 1337])
                    params = {'origin_native_xz': args.origin_native_xz or [42173, 42874], 'shape_zx': shape,
                              'coupled_intervals': (1 if profile == 'diagnostic-only' else 12) if args.coupled_intervals is None else args.coupled_intervals,
                              'resample_stride': 3 if args.resample_stride is None else args.resample_stride}
                    from tools.native_30m_sources import compute_source_request
                    if args.storm_table or args.runoff_parameters:
                        from dataclasses import asdict
                        from tools.native_30m_event_config import event_configuration
                        rain_input = _jread(args.storm_table) if args.storm_table else None
                        rp_input = _jread(args.runoff_parameters) if args.runoff_parameters else None
                        rain_actual, rp_actual = event_configuration(rain_input, rp_input)
                        params.update(storm_rain_mm_h=rain_actual.tolist(), runoff_parameters=asdict(rp_actual),
                                      infiltration_capacity_mm_h=rp_actual.infiltration_capacity_mm_h)
                    if args.terminal_native_xz is not None:
                        params['terminal_native_xz'] = args.terminal_native_xz
                    if args.reach_rule_file:
                        from tools.native_30m_selection_contract import parameters_from_rule_file
                        params['selection_parameters'] = parameters_from_rule_file(_jread(args.reach_rule_file))
                    budget.check_window(records, params['shape_zx'], params['coupled_intervals'])
                    compute_source_request(records, params)  # refuse unsupported values before dispatch
                if any(not Path(r['path']).is_absolute() for r in records) and Path.cwd().resolve() != ROOT:
                    raise ValueError('relative source page paths require execution from project root')
                budget.check_window(records, params['shape_zx'], params['coupled_intervals'])
                with tempfile.TemporaryDirectory(prefix='native-30m-compute-') as tmp:
                    path = Path(tmp) / 'candidate'
                    try:
                        worker = _compute_candidate_in_worker(records, params, path, budget,
                                                              expected_identity=expected_numerical, source_kind=source_kind,
                                                              profile=profile, rain_mm_h=args.rain_mm_h)
                        manifest = worker['manifest']
                        if expected_numerical is not None and manifest['identity_sha256'] != expected_numerical:
                            raise RuntimeError('same-source rebuild numerical identity mismatch')
                    except Exception as exc:
                        failed = _record_compute_failure(args.output_dir, exc)
                        print('compute failure evidence: ' + str(failed), file=sys.stderr)
                        raise
                    if profile == 'diagnostic-only':
                        from tools.native_30m_diagnostic_only import publish_diagnostic
                        result = publish_diagnostic(path, args.output_dir)
                    else:
                        result = publish_release(path, args.output_dir, expected_identity_sha256=manifest['identity_sha256'],
                            provenance={'mode': args.mode, 'compute_wall_seconds': worker['compute_wall_seconds'],
                                        'compute_process_peak_rss_bytes': worker['process_peak_rss_bytes'],
                                        'compute_rss_measured': True, 'rss_scope': worker['rss_scope'],
                                        'selection_rule_before_compute': worker.get('selection_rule_before_compute'),
                                        'source_code_identity_at_compute': worker.get('source_code_identity_at_compute'),
                                        'per_stage_resources': worker['resources']})
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        if hasattr(exc, 'reason_code'):
            print(json.dumps({'resolved': False, 'reason': exc.reason_code}, allow_nan=False))
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
