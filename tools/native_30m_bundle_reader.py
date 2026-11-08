import json, math, os, stat, sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.common_infra import checked_archive, file_sha256
from terrain_pipeline.artifacts.contracts import digest

def _jread(p):
    with open(p, "rb") as f:
        raw = f.read(1048577)
    if len(raw) > 1048576:
        raise ValueError("json too large")
    def _flo(s):
        v = float(s)
        if not math.isfinite(v):
            raise ValueError("non-finite float")
        return v
    def _pairs(items):
        d = {}
        for k, v in items:
            if k in d:
                raise ValueError("duplicate key: " + k)
            d[k] = v
        return d
    def _const(_):
        raise ValueError("constant not allowed")
    return json.loads(raw.decode("utf-8"), parse_float=_flo, parse_int=int,
                      parse_constant=_const, object_pairs_hook=_pairs)

def _checkpath(p, isdir_ok=False):
    st = os.lstat(p)
    if stat.S_ISLNK(st.st_mode):
        raise ValueError("symlink: " + str(p))
    if getattr(st, "st_file_attributes", 0) & 0x400:
        raise ValueError("junction: " + str(p))
    if isdir_ok:
        if not stat.S_ISDIR(st.st_mode):
            raise ValueError("not dir: " + str(p))
    else:
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("not regular: " + str(p))

_NAMES = {
    "source.npz", "source.json", "topology.npz", "topology.json",
    "selection.npz", "selection.json", "event.npz", "event.json",
    "section.npz", "section.json", "geometry.npz", "reach_context.npz",
    "reach_context.json", "dynamics.npz", "bundle.json",
}

def load_candidate_envelope(directory, expected_identity_sha256=None):
    root = Path(directory).absolute()
    _checkpath(root, isdir_ok=True)
    found = {}
    diag = root / "discharge-diagnostic"
    for entry in os.listdir(root):
        p = root / entry
        if entry == "discharge-diagnostic":
            _checkpath(p, isdir_ok=True)
            for sub in os.listdir(p):
                sp = p / sub
                _checkpath(sp)
                rel = "discharge-diagnostic/" + sub
                if rel not in ("discharge-diagnostic/manifest.json", "discharge-diagnostic/arrays.npz"):
                    raise ValueError("extra diag: " + rel)
                found[rel] = sp
            continue
        _checkpath(p)
        if entry not in _NAMES:
            raise ValueError("unexpected entry: " + entry)
        found[entry] = p
    want = set(_NAMES) | {"discharge-diagnostic/manifest.json", "discharge-diagnostic/arrays.npz"}
    if set(found.keys()) != want:
        raise ValueError("missing: " + str(want - set(found.keys())))
    bundle = _jread(found["bundle.json"])
    if bundle.get("schema") != "native-30m-river-bundle-v1":
        raise ValueError("schema")
    id_keys = ["schema", "parameters", "source_records", "stage_identities", "files", "capabilities"]
    ident_payload = {k: bundle[k] for k in id_keys}
    ident = digest(ident_payload)
    if bundle.get("identity_sha256") != ident:
        raise ValueError("identity mismatch")
    if expected_identity_sha256 is not None and ident != expected_identity_sha256:
        raise ValueError("external pin mismatch")
    files = bundle["files"]
    if set(files.keys()) != want - {"bundle.json"}:
        raise ValueError("files keys")
    for n, h in files.items():
        if not isinstance(h, str) or len(h) != 64 or not all(c in "0123456789abcdef" for c in h):
            raise ValueError("hash fmt: " + n)
    pr = bundle["parameters"]
    if type(pr["world_seed"]) is not int or pr["world_seed"] != 20261020:
        raise ValueError("world_seed")
    if not (isinstance(pr["origin_native_xz"], list) and len(pr["origin_native_xz"]) == 2 and all(type(x) is int for x in pr["origin_native_xz"])):
        raise ValueError("origin")
    zx = pr["shape_zx"]
    if not (isinstance(zx, list) and len(zx) == 2 and all(type(x) is int and 1 <= x <= 1337 for x in zx)):
        raise ValueError("shape_zx")
    ci = pr["coupled_intervals"]
    if type(ci) is not int or not (1 <= ci <= 12):
        raise ValueError("coupled_intervals")
    rs = pr["resample_stride"]
    if type(rs) is not int or rs <= 0:
        raise ValueError("resample_stride")
    dt = pr["dt_s"]
    if isinstance(dt, bool) or not isinstance(dt, (int, float)) or dt != 3600:
        raise ValueError("dt_s")
    stg = bundle["stage_identities"]
    if set(stg.keys()) != {"source_assembly", "event", "geometry", "dynamics", "diagnostic"}:
        raise ValueError("stage keys")
    for k, v in stg.items():
        if not isinstance(v, str) or len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("stage hash: " + k)
    caps = bundle["capabilities"]
    if not isinstance(caps, dict) or set(caps) != {'hydraulic_ready', 'natural_outlet_certified', 'publishable', 'finite_graph_only'}:
        raise ValueError('capability key whitelist')
    for k in ("hydraulic_ready", "natural_outlet_certified", "publishable"):
        if caps[k] is not False:
            raise ValueError("cap false: " + k)
    if caps["finite_graph_only"] is not True:
        raise ValueError("finite_graph_only")
    def _hv(headers):
        for name, (shape, dtype) in headers.items():
            if dtype.hasobject or dtype.fields is not None:
                raise ValueError("bad dtype: " + name)
            if math.prod(shape) > 16777216:
                raise ValueError("too big: " + name)
    arrays = {}
    for n, p in found.items():
        if not n.endswith(".npz"):
            continue
        if n in ("geometry.npz", "dynamics.npz", "discharge-diagnostic/arrays.npz"):
            continue
        arrays[n] = checked_archive(str(p), expected_sha256=files[n],
                                    max_bytes=512 * 1024 * 1024, header_validator=_hv)
    json_records = {}
    for n in ("source.json", "topology.json", "selection.json", "event.json",
              "section.json", "reach_context.json"):
        json_records[n] = _jread(found[n])
    json_records["discharge-diagnostic/manifest.json"] = _jread(found["discharge-diagnostic/manifest.json"])
    for n, h in files.items():
        if file_sha256(root / n) != h:
            raise ValueError("hash mismatch: " + n)
    return {"manifest": bundle, "directory": root, "json_records": json_records, "arrays": arrays}


from terrain_pipeline.common_infra import load_bundle, identity
from terrain_pipeline.channel_geometry import load_monotone_union
from terrain_pipeline.surface_rivers.metric_network_discharge_product import load_discharge_product


def load_candidate(directory, *, expected_identity_sha256=None):
    env = load_candidate_envelope(directory, expected_identity_sha256)
    m = env['manifest']
    d = env['directory']
    stages = m['stage_identities']
    hashes = m['files']

    def validator(x):
        valid = (
            identity(x['arrays'], x['metadata']) == x['identity_sha256']
            and x['metadata']['schema'] == 'world-nodal-water-sediment-bed-v1'
            and x['metadata']['status'] == 'complete'
            and x['metadata']['geometry_identity_sha256'] == stages['geometry']
            and x['metadata']['hydraulic_ready'] is False
            and x['metadata']['natural_outlet_verified'] is False
            and x['metadata']['publishable'] is False
        )
        if not valid:
            raise ValueError('invalid dynamics metadata or identity')

    geometry = load_monotone_union(
        d / 'geometry.npz',
        expected_sha256=hashes['geometry.npz'],
        expected_identity=stages['geometry'],
    )
    dynamics = load_bundle(
        d / 'dynamics.npz',
        expected_sha256=hashes['dynamics.npz'],
        validator=validator,
        max_bytes=512 * 1024 * 1024,
    )
    if dynamics['identity_sha256'] != stages['dynamics']:
        raise ValueError('dynamics identity mismatch')
    diagnostic = load_discharge_product(d / 'discharge-diagnostic')
    if diagnostic['identity_sha256'] != stages['diagnostic']:
        raise ValueError('diagnostic identity mismatch')
    srcjson = env['json_records']['source.json']
    if srcjson['assembly_digest'] != stages['source_assembly']:
        raise ValueError('source assembly digest mismatch')
    eventjson = env['json_records']['event.json']
    if eventjson['event_identity'] != stages['event']:
        raise ValueError('event identity mismatch')
    if digest(eventjson['identity']) != stages['event']:
        raise ValueError('event digest mismatch')
    env.update(geometry=geometry, dynamics=dynamics, diagnostic=diagnostic)
    validate_candidate_shapes(env)
    validate_candidate_event(env)
    from tools.native_30m_bundle_validation import (
        validate_graph_bindings, validate_nodal_supply, validate_solver_states, validate_diagnostic_binding)
    validate_diagnostic_binding(env)
    env['verification'] = {'graph': validate_graph_bindings(env), 'nodal_supply': validate_nodal_supply(env),
                           'solver_states': validate_solver_states(env)}
    from tools.native_30m_selection_contract import verify_saved_selection
    env['selection_verification'] = verify_saved_selection(env)
    return env


def _array_hash(value):
    import hashlib
    import numpy as np
    h = hashlib.sha256()
    h.update(str(value.shape).encode('ascii'))
    h.update(value.dtype.str.encode('ascii'))
    h.update(np.ascontiguousarray(value).tobytes(order='C'))
    return h.hexdigest()


def validate_candidate_shapes(env):
    import numpy as np
    a = env['arrays']
    p = env['manifest']['parameters']
    shape = tuple(p['shape_zx'])
    size = math.prod(shape)

    def array(record, key, dtype, dimensions):
        value = record[key]
        if value.dtype != np.dtype(dtype) or value.shape != dimensions:
            raise ValueError('array dtype/shape: ' + key)
        if value.dtype.kind in 'fc' and not np.isfinite(value).all():
            raise ValueError('nonfinite array: ' + key)
        return value

    src, top, sel, sec, rc = (a[k + '.npz'] for k in
                              ('source', 'topology', 'selection', 'section', 'reach_context'))
    field = src['field']
    if field.dtype != np.float64 or field.shape != shape:
        raise ValueError('source field dtype/shape')
    mask = array(src, 'resolved_mask', bool, shape)
    if not np.isfinite(field[mask]).all() or np.isinf(field).any():
        raise ValueError('source field validity')
    origin = array(src, 'origin_native_xz', np.int64, (2,))
    if not np.array_equal(origin, p['origin_native_xz']):
        raise ValueError('source origin binding')
    rec = array(top, 'receiver', np.int64, shape)
    valid = array(top, 'valid_mask', bool, shape)
    unknown = array(top, 'upstream_unknown_mask', bool, shape)
    kinds = top['terminal_kind']
    if kinds.dtype.kind != 'U' or kinds.shape != shape:
        raise ValueError('terminal kind shape/type')
    if not np.isin(kinds, ['inactive', 'interior', 'retained', 'open_outflow', 'unknown_boundary']).all():
        raise ValueError('terminal kind vocabulary')
    if not np.array_equal(valid, mask) or np.any((rec < -1) | (rec >= size)):
        raise ValueError('topology source binding/range')
    catch = array(sel, 'catchment_mask', bool, shape)
    flow = array(sel, 'flowline_mask', bool, shape)
    stem = sel['stem_flat_cells']
    if stem.dtype != np.int64 or stem.ndim != 1 or not stem.size:
        raise ValueError('stem dtype/shape')
    if np.any((stem < 0) | (stem >= size)) or not flow.ravel()[stem].all():
        raise ValueError('stem range/flowline')
    if np.any(flow & ~catch) or np.any(catch & (~valid | unknown)):
        raise ValueError('catchment incomplete')
    ids = sec['node_cell_ids']
    if ids.dtype != np.int64 or ids.ndim != 1 or not 2 <= ids.size <= 128:
        raise ValueError('section node ids')
    n = ids.size
    if np.any((ids < 0) | (ids >= size)) or not np.isin(ids, stem).all():
        raise ValueError('section node selection binding')
    chain = array(sec, 'receiver', np.int64, (n,))
    if not np.array_equal(chain, np.r_[np.arange(1, n), -1]):
        raise ValueError('section receiver chain')
    xz = array(sec, 'node_xz_m', np.float64, (n, 2))
    expected_xz = np.column_stack((ids % shape[1], ids // shape[1])) + origin
    if not np.array_equal(xz, expected_xz * 30.0):
        raise ValueError('section coordinates binding')
    for key in ('source_bed_m', 'source_slope_per_m', 'width_m', 'normal_depth_m', 'design_q_m3_s'):
        v = array(sec, key, np.float64, (n,))
        if key in ('width_m', 'normal_depth_m', 'design_q_m3_s') and np.any(v <= 0):
            raise ValueError('nonpositive section: ' + key)
    if not np.array_equal(sec['source_bed_m'], src['field'].ravel()[ids]):
        raise ValueError('section source bed binding')
    for key in ('node_bed_m', 'node_distance_m', 'node_length_m', 'node_slope_per_m',
                'initial_alluvium_bulk_m3', 'rock_floor_m'):
        array(rc, key, np.float64, (n,))
    edge = rc['node_distance_m']
    if (edge[-1] != 0 or np.any(edge[:-1] <= 0) or
            not np.allclose(edge[:-1], np.linalg.norm(np.diff(xz, axis=0), axis=1), rtol=1e-12, atol=1e-9)):
        raise ValueError('receiver edge distance binding')
    if np.any(rc['node_length_m'] <= 0) or np.any(rc['initial_alluvium_bulk_m3'] < 0):
        raise ValueError('reach control volumes')
    counts = array(rc, 'lateral_cell_counts', np.int64, (n,))
    if np.any(counts <= 0) or counts.sum() != np.count_nonzero(catch):
        raise ValueError('lateral catchment allocation')
    dyn = env['dynamics']['arrays']
    t = p['coupled_intervals']
    for key in ('node_bed_m', 'water_volume_m3', 'mobile_solid_m3', 'loose_solid_m3', 'rock_removed_m3'):
        v = array(dyn, key, np.float64, (t + 1, n))
        if key != 'node_bed_m' and np.any(v < 0):
            raise ValueError('negative inventory: ' + key)
    if not np.array_equal(dyn['node_bed_m'][0], rc['node_bed_m']):
        raise ValueError('initial bed binding')
    if np.any(array(dyn, 'material_area_m2', np.float64, (n,)) <= 0):
        raise ValueError('material area')
    times = array(dyn, 'time_seconds', np.float64, (t + 1,))
    if not np.array_equal(times, np.arange(t + 1) * p['dt_s']):
        raise ValueError('coupled time binding')
    g = env['geometry']['arrays']
    if not np.array_equal(g['receiver'], chain) or not np.array_equal(g['node_xz_m'], xz):
        raise ValueError('geometry section binding')


def validate_candidate_event(env):
    import numpy as np
    a, j = env['arrays'], env['json_records']
    ev, ej = a['event.npz'], j['event.json']
    ident, source = ej['identity'], ej['source']
    chosen = j['selection.json']['chosen']
    p = env['manifest']['parameters']
    from dataclasses import asdict
    import hashlib
    from tools.native_30m_event_config import event_configuration
    _, actual_rp = event_configuration(p['storm_rain_mm_h'], p.get('runoff_parameters',
                                        {'infiltration_capacity_mm_h': p['infiltration_capacity_mm_h']}))
    rp_values = asdict(actual_rp)
    rp_sha = hashlib.sha256(json.dumps(rp_values, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
    if ej['runoff_parameters'] != rp_values or source['runoff_parameter_sha256'] != rp_sha:
        raise ValueError('event_runoff_parameter_binding')
    if source != ident['source'] or source['source_identity_sha256'] != env['manifest']['stage_identities']['source_assembly']:
        raise ValueError('event source identity binding')
    if source['spacing_m'] != 30 or source['world_seed'] != 20261020 or source['dt_s'] != p['dt_s']:
        raise ValueError('event source units/seed')
    box = chosen['subwindow_rc']
    if not isinstance(box, list) or len(box) != 4 or any(type(x) is not int for x in box):
        raise ValueError('event crop type')
    r0, r1, c0, c1 = box
    h, w = p['shape_zx']
    if not (0 <= r0 < r1 <= h and 0 <= c0 < c1 <= w):
        raise ValueError('event crop bounds')
    crop = np.s_[r0:r1, c0:c1]
    origin = a['source.npz']['origin_native_xz'] + [c0, r0]
    if not np.array_equal(source['origin_native_xz'], origin) or source['grid_shape'] != [r1-r0, c1-c0]:
        raise ValueError('event coordinate binding')
    catch = a['selection.npz']['catchment_mask'][crop]
    active = ev['active_cells']
    if active.dtype != np.int64 or not np.array_equal(active, np.flatnonzero(catch)):
        raise ValueError('event active catchment binding')
    if active.size != chosen['catchment_cells']:
        raise ValueError('chosen catchment count')
    shapes = {'local_q_m3_s': (72, active.size), 'rain_mm_h': (72,), 'time_edges_s': (73,),
              'routed_terminal_q_m3_s': (72,), 'instantaneous_terminal_q_m3_s': (72,)}
    for key, shape in shapes.items():
        value = ev[key]
        if value.dtype != np.float64 or value.shape != shape or not np.isfinite(value).all() or np.any(value < 0):
            raise ValueError('event array: ' + key)
    if (not np.array_equal(ev['time_edges_s'], np.arange(73) * p['dt_s']) or
            not np.array_equal(ev['time_edges_s'], ident['time_edges_s']) or
            not np.array_equal(ev['rain_mm_h'], p['storm_rain_mm_h'])):
        raise ValueError('event forcing/time binding')
    for key, pin in (('local_q_m3_s', 'local_q_m3_s_sha256'), ('active_cells', 'active_cells_sha256'),
                     ('rain_mm_h', 'rain_mm_h_sha256'), ('routed_terminal_q_m3_s', 'routed_terminal_q_sha256'),
                     ('instantaneous_terminal_q_m3_s', 'instantaneous_terminal_q_sha256')):
        if _array_hash(ev[key]) != ident[pin]:
            raise ValueError('event array identity: ' + key)
    raw = a['topology.npz']['receiver'][crop]
    rr, cc = raw // w, raw % w
    inside = (raw >= 0) & (rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)
    receiver = np.where(inside, (rr-r0)*(c1-c0)+cc-c0, -1).astype(np.int64)
    for pin, value in (('elevation_sha256', a['source.npz']['field'][crop]),
                       ('catchment_mask_sha256', catch),
                       ('flowline_mask_sha256', a['selection.npz']['flowline_mask'][crop]),
                       ('receiver_sha256', receiver), ('rain_mm_h_sha256', ev['rain_mm_h'])):
        if _array_hash(value) != source[pin]:
            raise ValueError('event topology/source array binding: ' + pin)
    q = ev['routed_terminal_q_m3_s']
    if ej['design_q_m3_s'] != float(q.max()) or ej['design_q_interval_index'] != int(q.argmax()):
        raise ValueError('design Q is not routed event peak')
    if not np.all(a['section.npz']['design_q_m3_s'] == ej['design_q_m3_s']):
        raise ValueError('section design Q binding')
    keys = ('rain_volume_m3', 'et_volume_m3', 'outflow_volume_m3', 'storage_change_m3', 'balance_residual_m3')
    values = [ev['bucket_' + key] for key in keys]
    for i, value in enumerate(values):
        if value.dtype != np.float64 or value.shape != (72,) or not np.isfinite(value).all():
            raise ValueError('bucket array')
        if i < 3 and np.any(value < 0):
            raise ValueError('negative bucket flux')
    residual = values[0] - values[1] - values[2] - values[3]
    tolerance = 1e-12 + 1e-10 * np.maximum.reduce([np.abs(v) for v in values[:4]])
    if np.any(np.abs(residual) > tolerance) or np.any(np.abs(residual-values[4]) > tolerance):
        raise ValueError('bucket independent balance')
    if not np.allclose(ev['local_q_m3_s'].sum(axis=1) * p['dt_s'], values[2], rtol=1e-12, atol=1e-9):
        raise ValueError('local Q bucket release binding')
