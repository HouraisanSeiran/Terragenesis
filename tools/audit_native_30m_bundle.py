import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import checked_archive


BANNED = ("metric_channel_solver", "metric_sediment", "metric_bed_update",
          "world_channel_dynamics", "metric_morphology_coupling", "metric_channel_product")

def assert_independence():
    """The tested modules must not be in this process, or this is not an independent check."""
    loaded = [name for name in sys.modules if any(token in name for token in BANNED)]
    if loaded:
        raise SystemExit("not independent: tested modules are already imported: %s" % loaded)

def ratio(residual, gross):
    return float(abs(residual) / gross) if gross else None

def water_meta(metadata, index):
    return metadata["water_%d" % index]["metadata"].get("algorithm", "metric_channel_solver")

def audit_dynamics(path, expected_sha256):
    assert_independence()
    arrays = checked_archive(path, expected_sha256=expected_sha256, max_bytes=512*1024*1024)
    record = json.loads(arrays.pop("manifest").tobytes().decode("utf-8"))
    metadata = record["metadata"]
    from terrain_pipeline.common_infra import identity as artifact_identity
    if record["identity_sha256"] != artifact_identity(arrays, metadata):
        raise ValueError("root identity")
    dt = np.asarray(arrays["time_seconds"], np.float64)
    node_bed = np.asarray(arrays["node_bed_m"], np.float64)
    water_volume = np.asarray(arrays["water_volume_m3"], np.float64)
    mobile = np.asarray(arrays["mobile_solid_m3"], np.float64)
    loose = np.asarray(arrays["loose_solid_m3"], np.float64)
    rock = np.asarray(arrays["rock_removed_m3"], np.float64)
    area = np.asarray(arrays["material_area_m2"], np.float64)

    def unpack(name):
        return unpack_pin(arrays, metadata, name)

    water_rows, solid_rows, bed_rows, interval_rows = [], [], [], []
    hydraulic_rows = []
    control_discriminating = False
    for index in range(len(metadata["intervals"])):
        water, water_metadata = unpack("water_%d" % index)
        sediment, sediment_meta = unpack("sediment_%d" % index)
        interval = metadata['intervals'][index]
        n = area.size
        for trace, fields in ((water, ('trace_local_q_m3_s', 'trace_boundary_outflow_volume_m3')),
                              (sediment, ('step_eroded_loose_solid_m3', 'step_eroded_rock_m3',
                               'step_deposited_solid_m3', 'step_external_solid_m3',
                               'step_exported_solid_m3', 'step_outgoing_solid_m3', 'step_incoming_solid_m3'))):
            times = trace['trace_time_seconds']
            if (times.ndim != 1 or times.size < 2 or not np.isfinite(times).all() or
                    not np.all(np.diff(times) > 0) or times[0] != interval['start_seconds'] or
                    times[-1] != interval['end_seconds']):
                raise ValueError('trace time coverage')
            for key in fields:
                if trace[key].shape != (times.size - 1, n):
                    raise ValueError('trace flux shape: ' + key)
        if water_metadata['status'] != 'complete' or sediment_meta['status'] != 'complete':
            raise ValueError('incomplete child solver')
        hydraulic_row = recheck_hydraulic_trace(arrays, index, water)
        hydraulic_rows.append(hydraulic_row)
        control_discriminating |= hydraulic_row['initial_bed_control_discriminating']
        t = np.asarray(water["trace_time_seconds"], np.float64)
        step = np.diff(t)[:, None]
        local_input = float((np.asarray(water["trace_local_q_m3_s"], np.float64) * step).sum())
        export = float(np.asarray(water["trace_boundary_outflow_volume_m3"], np.float64).sum())
        start = float(water_volume[index].sum())
        end = float(water_volume[index + 1].sum())
        residual = start + local_input - export - end
        water_rows.append(dict(interval=index, initial_m3=start, input_m3=local_input,
                               export_m3=export, final_m3=end, residual_m3=residual,
                               residual_relative=ratio(residual, local_input)))
        st = np.asarray(sediment["trace_time_seconds"], np.float64)
        eroded_loose = float(np.asarray(sediment["step_eroded_loose_solid_m3"], np.float64).sum())
        eroded_rock = float(np.asarray(sediment["step_eroded_rock_m3"], np.float64).sum())
        deposited = float(np.asarray(sediment["step_deposited_solid_m3"], np.float64).sum())
        external = float(np.asarray(sediment["step_external_solid_m3"], np.float64).sum())
        solid_export = float(np.asarray(sediment["step_exported_solid_m3"], np.float64).sum())
        moving_out = float(np.asarray(sediment["step_outgoing_solid_m3"], np.float64).sum())
        moving_in = float(np.asarray(sediment["step_incoming_solid_m3"], np.float64).sum())
        solid_start = float((mobile[index] + loose[index]).sum())
        solid_end = float((mobile[index + 1] + loose[index + 1]).sum())
        rock_added = float(rock[index + 1].sum() - rock[index].sum())
        # `eroded_loose` and `deposited` are **internal transfers** between the bed colluvium
        # and the moving load: one adds to `mobile` exactly what it removes from `loose`, and
        # the other does the reverse. Adding them as external fluxes double-counts them;
        # measured on this run, that wrong form leaves a 4.36 m3 residual on a 3305 m3
        # inventory (1.3e-3 relative), while the correct form closes to round-off.
        combined_residual = solid_start + external + eroded_rock - solid_export - solid_end
        mobile_residual = (float(mobile[index].sum()) + moving_in + external + eroded_loose
                           + eroded_rock - moving_out - deposited
                           - float(mobile[index + 1].sum()))
        loose_residual = (float(loose[index].sum()) - eroded_loose + deposited
                          - float(loose[index + 1].sum()))
        gross = solid_start + external + eroded_rock
        solid_rows.append(dict(
            interval=index, combined_initial_m3=solid_start, external_m3=external,
            eroded_rock_m3=eroded_rock, export_m3=solid_export,
            combined_final_m3=solid_end,
            internal_eroded_loose_m3=eroded_loose, internal_deposited_m3=deposited,
            moving_in_m3=moving_in, moving_out_m3=moving_out,
            rock_inventory_added_m3=rock_added,
            combined_residual_m3=combined_residual,
            combined_residual_relative=ratio(combined_residual, gross),
            mobile_only_residual_m3=mobile_residual,
            loose_only_residual_m3=loose_residual))
        # Exner identity on this interval, from inventories only
        delta_bed = node_bed[index + 1] - node_bed[index]
        porosity = float(sediment_meta["material"]["porosity"])
        inventory_change = (loose[index + 1] - loose[index]) / ((1. - porosity) * area) \
            - (rock[index + 1] - rock[index]) / area
        exner_residual = float(np.sum(area * delta_bed) - np.sum(area * inventory_change))
        bed_rows.append(dict(interval=index,
                             sum_area_delta_bed_m3=float(np.sum(area * delta_bed)),
                             sum_area_inventory_m3=float(np.sum(area * inventory_change)),
                             exner_residual_m3=exner_residual,
                             exner_residual_relative=ratio(
                                 exner_residual,
                                 max(np.sum(area * np.abs(inventory_change)), 1e-30)),
                             max_abs_delta_bed_m=float(np.max(np.abs(delta_bed)))))
        interval_rows.append(dict(interval=index, water_algorithm=str(water_meta(metadata, index)),
                                  sediment_status=str(sediment_meta["status"]),
                                  water_steps=int(t.size) - 1,
                                  sediment_steps=int(st.size) - 1))

    water_total = dict(
        initial_m3=float(water_volume[0].sum()),
        input_m3=float(sum(r["input_m3"] for r in water_rows)),
        export_m3=float(sum(r["export_m3"] for r in water_rows)),
        final_m3=float(water_volume[-1].sum()))
    water_total["residual_m3"] = (water_total["initial_m3"] + water_total["input_m3"]
                                  - water_total["export_m3"] - water_total["final_m3"])
    water_total["residual_relative"] = ratio(water_total["residual_m3"], water_total["input_m3"])
    solid_total = dict(
        initial_m3=float((mobile[0] + loose[0]).sum()),
        external_m3=float(sum(r["external_m3"] for r in solid_rows)),
        bedrock_eroded_m3=float(sum(r["eroded_rock_m3"] for r in solid_rows)),
        export_m3=float(sum(r["export_m3"] for r in solid_rows)),
        final_m3=float((mobile[-1] + loose[-1]).sum()),
        rock_inventory_m3=float(rock[-1].sum()),
        internal_eroded_loose_m3=float(sum(r["internal_eroded_loose_m3"] for r in solid_rows)),
        internal_deposited_m3=float(sum(r["internal_deposited_m3"] for r in solid_rows)),
        max_abs_mobile_only_residual_m3=float(max(
            abs(r["mobile_only_residual_m3"]) for r in solid_rows)),
        max_abs_loose_only_residual_m3=float(max(
            abs(r["loose_only_residual_m3"]) for r in solid_rows)))
    solid_total["residual_m3"] = (solid_total["initial_m3"] + solid_total["external_m3"]
                                  + solid_total["bedrock_eroded_m3"] - solid_total["export_m3"]
                                  - solid_total["final_m3"])
    gross_solid = (solid_total["initial_m3"] + solid_total["external_m3"]
                   + solid_total["bedrock_eroded_m3"])
    solid_total["residual_relative"] = ratio(solid_total["residual_m3"], gross_solid)
    solid_total["ledger_form"] = (
        "combined inventory (moving load + bed colluvium). `eroded_loose` and `deposited` are "
        "internal transfers between those two pools, so they cancel here and are verified "
        "separately by the two sub-ledger maxima. Bedrock erosion enters the combined inventory "
        "as intact rock volume and leaves it as colluvium, so it is counted once.")
    bed_total = dict(
        total_area_delta_bed_m3=float(sum(r["sum_area_delta_bed_m3"] for r in bed_rows)),
        total_area_inventory_m3=float(sum(r["sum_area_inventory_m3"] for r in bed_rows)),
        max_abs_delta_bed_m=float(np.max(np.abs(node_bed[-1] - node_bed[0]))),
        node_bed_change_m=(node_bed[-1] - node_bed[0]).tolist(),
        bed_area_m2=area.tolist())
    bed_total["residual_m3"] = (bed_total["total_area_delta_bed_m3"]
                                - bed_total["total_area_inventory_m3"])
    bed_total["residual_relative"] = ratio(
        bed_total["residual_m3"],
        max(abs(bed_total["total_area_delta_bed_m3"]), 1e-30))

    payload = dict(
        independence=dict(imported_tested_modules=False,
                          banned_tokens=list(BANNED),
                          note="checked at process start, before any bundled array is read"),
        intervals=len(metadata["intervals"]),
        physical_seconds=float(dt[-1]),
        water=dict(total=water_total, per_interval=water_rows,
                   units="m3; residual_relative is |residual| / total local input"),
        solid=dict(total=solid_total, per_interval=solid_rows,
                   units=("solid m3 (pore space excluded from `loose`, rock is intact volume); "
                          "residual_relative is |residual| / gross inflow")),
        bed=dict(total=bed_total, per_interval=bed_rows,
                 units=("m3 for the volume identity, m for the bed change; residual_relative is "
                        "|residual| / sum(area*|delta|)")),
        solver_metadata=dict(dynamic_PL_mesh_updated=metadata.get("dynamic_PL_mesh_updated")),
    )
    payload['hydraulic_recheck'] = {'per_interval': hydraulic_rows,
        'feedback_control_discriminating': bool(control_discriminating),
        'scope': 'independent saved-state rectangular Manning; not dynamic solver replay, backwater or magnitude certification'}
    return gate_ledgers(metadata, arrays, payload)



def gate_ledgers(metadata, arrays, payload):
    try:
        T=len(metadata['intervals'])
        area=np.asarray(arrays['material_area_m2'],dtype=float)
        if not 1 <= T <= 12 or area.ndim!=1 or area.size<1 or not np.all(np.isfinite(area)) or not np.all(area>0):
            raise ValueError
        N=area.size
        keys=('node_bed_m','water_volume_m3','mobile_solid_m3','loose_solid_m3','rock_removed_m3')
        arrs={k:np.asarray(arrays[k],dtype=float) for k in keys}
        for k in keys:
            if arrs[k].shape!=(T+1,N) or not np.all(np.isfinite(arrs[k])):
                raise ValueError
        if not (np.all(arrs['water_volume_m3']>=0) and np.all(arrs['mobile_solid_m3']>=0) and np.all(arrs['loose_solid_m3']>=0) and np.all(arrs['rock_removed_m3']>=0)):
            raise ValueError
        t=np.asarray(arrays['time_seconds'],dtype=float)
        if t.shape!=(T+1,) or not np.all(np.isfinite(t)) or t[0]!=0 or not np.all(np.diff(t)>0):
            raise ValueError
        ivs=metadata['intervals']
        if not isinstance(ivs,list) or len(ivs)!=T:
            raise ValueError
        for i,iv in enumerate(ivs):
            if iv.get('start_seconds')!=t[i] or iv.get('end_seconds')!=t[i+1]:
                raise ValueError
        if metadata.get('status')!='complete':
            raise ValueError
        w=payload['water']['per_interval']
        s=payload['solid']['per_interval']
        if len(w)!=T or len(s)!=T:
            raise ValueError
        wf=('initial_m3','input_m3','export_m3','final_m3','residual_m3')
        sf=('combined_initial_m3','external_m3','eroded_rock_m3','export_m3','combined_final_m3','combined_residual_m3','mobile_only_residual_m3','loose_only_residual_m3','rock_inventory_added_m3')
        for i in range(T):
            vals=[]
            for f in wf:
                v=w[i].get(f)
                if v is None or isinstance(v,bool) or not np.isfinite(v):
                    raise ValueError
                vals.append(v)
            lim=1e-12+1e-10*max(max(abs(x) for x in vals[:4]),1e-300)
            if abs(vals[4])>lim:
                raise ValueError
            sv=[]
            for f in sf:
                v=s[i].get(f)
                if v is None or isinstance(v,bool) or not np.isfinite(v):
                    raise ValueError
                sv.append(v)
            lim=1e-12+1e-10*max(max(abs(x) for x in sv[:5]),1e-300)
            for idx in (5,6,7):
                if abs(sv[idx])>lim:
                    raise ValueError
            if abs(sv[8]-sv[2])>lim:
                raise ValueError
        passed=True
        max_err_log=[]
        for i in range(T):
            p=metadata['sediment_%d'%i]['metadata']['material']['porosity']
            if isinstance(p,bool) or not np.isfinite(p) or not (0<=p<1):
                raise ValueError
            expected=(arrs['loose_solid_m3'][i+1]-arrs['loose_solid_m3'][i])/((1-p)*area)-(arrs['rock_removed_m3'][i+1]-arrs['rock_removed_m3'][i])/area
            actual=arrs['node_bed_m'][i+1]-arrs['node_bed_m'][i]
            err=np.abs(expected-actual)
            if not np.all(np.isfinite(expected)) or not np.all(np.isfinite(actual)) or not np.all(np.isfinite(err)):
                raise ValueError
            lim=1e-8+1e-10*np.maximum(np.abs(expected),np.abs(actual))
            if np.any(err>lim):
                passed=False
            max_err_log.append(float(np.max(err)))
        payload['pointwise_bed_residual_m']=list(max_err_log)
        payload['passed']=bool(passed)
        return payload
    except KeyError:
        raise ValueError


def unpack_pin(arrays, metadata, name):
    import numpy as np
    from terrain_pipeline.common_infra import identity

    pin = metadata[name]
    payload = np.asarray(arrays[name + "__payload"])
    if payload.dtype != np.uint8 or payload.ndim != 2:
        raise ValueError("payload must be uint8 ndim2")
    payload_bytes = pin["payload_bytes"]
    size = payload.size
    if (not isinstance(payload_bytes, int)) or isinstance(payload_bytes, bool):
        raise ValueError("payload_bytes must be int")
    if not (0 <= payload_bytes <= size):
        raise ValueError("payload_bytes out of range")
    layout = pin["layout"]
    seen = set()
    prev_stop = 0
    out = {}
    for ent in layout:
        nm = ent["name"]
        if not isinstance(nm, str) or nm in seen:
            raise ValueError("bad/duplicate layout name")
        seen.add(nm)
        dt = np.dtype(ent["dtype"])
        if dt.hasobject or dt.fields is not None or dt.subdtype is not None:
            raise ValueError("bad dtype")
        shape = ent["shape"]
        if not isinstance(shape, list) or len(shape) > 3:
            raise ValueError("bad shape")
        n = 1
        for d in shape:
            if (not isinstance(d, int)) or isinstance(d, bool) or d < 0:
                raise ValueError("bad dim")
            n *= d
        start, stop = ent["start"], ent["stop"]
        for v in (start, stop):
            if (not isinstance(v, int)) or isinstance(v, bool):
                raise ValueError("bad range")
        if not (0 <= start <= stop <= payload_bytes):
            raise ValueError("range out of payload")
        if start != prev_stop:
            raise ValueError("overlap or gap")
        if stop - start != n * dt.itemsize:
            raise ValueError("size mismatch")
        prev_stop = stop
        buf = payload.ravel()[start:stop].tobytes()
        arr = np.frombuffer(buf, dtype=dt).reshape(shape)
        out[nm] = arr
        if arr.dtype.kind in "fc" and arr.size:
            if not np.all(np.isfinite(arr)):
                raise ValueError("nonfinite " + nm)
        if nm in ("step_eroded_loose_solid_m3", "step_eroded_rock_m3", "step_deposited_solid_m3", "step_external_solid_m3", "step_exported_solid_m3", "step_outgoing_solid_m3", "step_incoming_solid_m3", "trace_local_q_m3_s", "trace_boundary_outflow_volume_m3"):
            if arr.size and np.any(np.asarray(arr, dtype=float) < 0):
                raise ValueError("negative " + nm)
    if prev_stop != payload_bytes:
        raise ValueError("layout does not cover payload")

    if identity(out, pin["metadata"]) != pin["identity_sha256"]:
        raise ValueError("identity mismatch")
    return out, pin["metadata"]


def recheck_hydraulic_trace(arrays, index, water):
    from tools.native_30m_hydraulic_reference import manning_trace_reference
    bed = arrays['node_bed_m'][index]
    n = bed.size
    receiver = water['network_receiver']
    distance = water['network_receiver_distance_m']
    if receiver.dtype != np.int64 or not np.array_equal(receiver, np.r_[np.arange(1, n), -1]):
        raise ValueError('independent hydraulic receiver chain')
    if distance.shape != (n,) or not np.isfinite(distance).all() or np.any(distance[:-1] <= 0) or distance[-1] != 0:
        raise ValueError('independent hydraulic edge lengths')
    slope = water['network_bed_slope'].copy()
    slope[:-1] = (bed[:-1] - bed[1:]) / distance[:-1]
    if not np.allclose(water['network_bed_elevation_m'], bed, rtol=0, atol=0):
        raise ValueError('independent hydraulic bed binding')
    if not np.allclose(water['network_bed_slope'], slope, rtol=1e-12, atol=1e-12):
        raise ValueError('independent hydraulic slope binding')
    volume = water['trace_volume_m3']
    if volume.ndim != 2 or volume.shape[1] != n or volume.size > 2000000:
        raise ValueError('independent hydraulic trace budget')
    args = (volume, water['network_length_m'], water['network_width_m'], water['network_roughness'])
    reference = manning_trace_reference(*args, slope, bed)
    mapping = {'area_m2': 'trace_area_m2', 'depth_m': 'trace_depth_m',
               'stage_m': 'trace_stage_m', 'outflow_q_m3_s': 'trace_outflow_end_q_m3_s'}
    residuals = {}
    for name, key in mapping.items():
        actual, expected = water[key], reference[name]
        if actual.shape != expected.shape or not np.isfinite(actual).all():
            raise ValueError('independent hydraulic trace shape/finite:' + key)
        error = np.abs(actual-expected)
        tolerance = 1e-12 + 1e-10*np.maximum(np.abs(actual), np.abs(expected))
        if np.any(error > tolerance):
            raise ValueError('independent Manning mismatch:' + key)
        residuals[name] = {'max_abs_error': float(error.max()),
                           'max_error_over_tolerance': float((error/tolerance).max())}
    initial = arrays['node_bed_m'][0]
    counter_slope = slope.copy()
    counter_slope[:-1] = (initial[:-1]-initial[1:]) / distance[:-1]
    control = manning_trace_reference(*args, counter_slope, initial)
    delta = np.abs(control['outflow_q_m3_s']-reference['outflow_q_m3_s'])
    tolerance = 1e-12 + 1e-10*np.abs(reference['outflow_q_m3_s'])
    return {'interval': index, 'residuals': residuals,
            'bed_differs_from_initial': not np.array_equal(bed, initial),
            'initial_bed_control_max_q_difference_m3_s': float(delta.max()),
            'initial_bed_control_discriminating': bool(np.any(delta > 100*tolerance))}


import argparse

def _cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dynamics', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output-report', default=None)
    args = parser.parse_args()
    try:
        report = audit_dynamics(args.dynamics, args.sha256)
        text = json.dumps(report, allow_nan=False)
        if args.output_report:
            with open(args.output_report, 'x') as f:
                f.write(text)
        print(text)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0 if report.get('passed') is True else 1

if __name__ == '__main__':
    sys.exit(_cli())
