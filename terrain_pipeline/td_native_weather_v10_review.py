"""Bounded native binary review of completely accepted v10 saved pages."""

import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile

import numpy as np
import psutil

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import STATES as STATES
from terrain_pipeline.basin_storage import LEDGERS as LEDGERS
from terrain_pipeline.basin_storage import storagev10_load_storage as load_storage
from terrain_pipeline.td_native_weather_storage_v10_io import load_native_weather_storage_v10_index, _json
from terrain_pipeline.td_hour_pages_review import _leaves, _chunks, _binary_chunks, _artifact
from terrain_pipeline.td_surface_reaches import _hash, _plain

SCHEMA = "td-v10-native-weather-binary-review-v1"
MAX_BYTES = 1073741824
PAGE_BYTES = 8*1024*1024
DEFAULT_OUTPUT_BYTES = 512*1024*1024


def _memory():
    values = psutil.Process().memory_info()
    rss, private = int(getattr(values,"peak_wset",values.rss)), getattr(values,"peak_pagefile",None)
    if type(private) is not int or max(rss,private) > MAX_BYTES:
        raise MemoryError("v10 review resource peak missing/exceeded")
    return dict(peak_rss_bytes=rss,peak_private_bytes=private)


def _selection(selected_steps_s, include_hour_flux, output_budget_bytes):
    if tuple(selected_steps_s) != (1.25,) or type(include_hour_flux) is not bool:
        raise ValueError("v10 review predeclares fine1.25 only and explicit flux boolean")
    if type(output_budget_bytes) is not int or not 0 < output_budget_bytes <= MAX_BYTES:
        raise ValueError("v10 review output budget must be <=1GiB")


def estimate_native_weather_v10_review(hierarchy, *, include_hour_flux=False):
    valid, labels, leaves = _leaves(hierarchy)
    cells, faces = int(valid.sum()), len(hierarchy["arrays"]["face_cells"])
    binary = cells*4*8 + 2*25*cells*4*8
    if include_hour_flux:
        binary += faces*2*8 + 2*24*(faces*4*8+cells*2*8)
    return dict(binary_bytes_exact=binary, estimated_output_upper_bytes=binary+len(leaves)*51*4096+2*PAGE_BYTES,
                cells=cells,faces=faces,leaf_count=len(leaves))


def _payloads(hierarchy, index, include_hour_flux):
    topology, geometry = hierarchy["arrays"], hierarchy["metadata"]
    valid, labels, leaves = _leaves(hierarchy)
    cells = np.flatnonzero(valid)
    area, count = geometry["spacing_m"]**2, len(leaves)
    yield from _chunks("leaves",iter(leaves))
    membership = np.column_stack((cells,topology["contribution_owner"].ravel()[cells],topology["receiver"][cells],topology["protected_mask"].ravel()[cells])).astype("<i8")
    yield from _binary_chunks("cell_membership",membership,columns=["cell_id","leaf_id","receiver_cell_id","protected"])
    del membership
    if include_hour_flux:
        yield from _binary_chunks("face_membership",topology["face_cells"].astype("<i8"),columns=["first_cell_id","second_cell_id"])
    for direction in ("eastward","westward"):
        previous = None
        for hour, page in enumerate(index["scenarios"][direction]["pages"]["1.25"]):
            saved = load_storage(**page["storage"])
            arrays = saved["arrays"]
            for local in ((0,1) if hour == 0 else (1,)):
                frame = hour+local
                fields = {name:np.bincount(labels,weights=arrays[name][local,valid]*area/(1 if name=="depth_m" else 1000),minlength=count) for name in STATES}
                total = sum(fields.values())
                wet = arrays["depth_m"][local,valid] > 1e-9
                surface = topology["height_m"].ravel()[valid]+arrays["depth_m"][local,valid]
                minimum, maximum = np.full(count,np.inf), np.full(count,-np.inf)
                np.minimum.at(minimum,labels[wet],surface[wet])
                np.maximum.at(maximum,labels[wet],surface[wet])
                wet_count = np.bincount(labels[wet],minlength=count)
                ledger = None if frame==0 else {name:np.bincount(labels,weights=arrays[name][0,valid],minlength=count) for name in LEDGERS}
                residual = None if frame==0 else ledger["rain_volume_m3"]+ledger["internal_net_m3"]-ledger["soil_et_m3"]-ledger["surface_et_m3"]-ledger["boundary_outflow_m3"]-(total-previous)
                allowed = None if frame==0 else 1e-6+1e-10*(abs(total)+abs(previous))
                if frame != 0 and (not np.isfinite(residual).all() or np.any(abs(residual)>allowed)):
                    raise ValueError("v10 review exclusive leaf interval budget failed")
                def rows():
                    for position, leaf in enumerate(leaves):
                        yield dict(leaf_id=leaf["leaf_id"],stable_leaf_id=leaf["stable_leaf_id"],time_s=frame*3600.,
                            inventories_m3={name:float(values[position]) for name,values in fields.items()},wet_count=int(wet_count[position]),
                            water_surface_min_m=float(minimum[position]) if wet_count[position] else None,
                            water_surface_max_m=float(maximum[position]) if wet_count[position] else None,
                            interval_ledger_m3=None if ledger is None else {name:float(values[position]) for name,values in ledger.items()},
                            leaf_budget=None if frame==0 else dict(residual_m3=float(residual[position]),allowed_m3=float(allowed[position]),passed=True))
                yield from _chunks("leaf_states",rows(),scenario=direction,step=1.25,frame=frame)
                native = np.column_stack([arrays[name][local,valid] for name in STATES]).astype("<f8")
                yield from _binary_chunks("native_states",native,columns=list(STATES),scenario=direction,step=1.25,frame=frame)
                actual = math.fsum((native[:,0]*area+native[:,1:].sum(axis=1)*area/1000).tolist())
                if abs(math.fsum(total.tolist())-actual) > 1e-6+abs(actual)*1e-10:
                    raise ValueError("v10 review exclusive leaf coverage budget mismatch")
                previous = total
                del native
            if include_hour_flux:
                names = ["face_forward_m3","face_reverse_m3","active_forward_s","active_reverse_s"]
                yield from _binary_chunks("hour_faces",np.column_stack([arrays[name] for name in names]).astype("<f8"),columns=names,scenario=direction,step=1.25,frame=hour+1)
                names = ["routed_volume_m3","wet_duration_s"]
                yield from _binary_chunks("hour_receivers",np.column_stack([arrays[name][valid] for name in names]).astype("<f8"),columns=names,scenario=direction,step=1.25,frame=hour+1)
            del saved, arrays
            _memory()


def _prepare(input_index, acceptance_arguments):
    accepted = load_native_weather_storage_v10_index(input_index,**acceptance_arguments)
    hierarchy = load_basin_hierarchy(**acceptance_arguments["hierarchy_record"])
    index = _json(dict(path=str(input_index),expected_sha256=acceptance_arguments["expected_sha256"]))
    return accepted,hierarchy,index


def _manifest(input_index, arguments, accepted, hierarchy, index, pages, include_hour_flux, output_budget_bytes):
    result = dict(schema=SCHEMA,input_index=str(Path(input_index).absolute()),acceptance_arguments=_plain(arguments),
        acceptance={name:_plain(value) for name,value in accepted.items() if name!="resource"},
        hierarchy_identity_sha256=hierarchy["identity_sha256"],
        grid=dict(shape_zx=list(hierarchy["arrays"]["height_m"].shape),spacing_m=hierarchy["metadata"]["spacing_m"],origin_m_xz=hierarchy["metadata"]["origin_m_xz"]),
        directions=["eastward","westward"],selected_steps_s=[1.25],frames=25,hours=24,chunk_rows=2048,max_page_bytes=PAGE_BYTES,
        include_hour_flux=include_hour_flux,output_budget_bytes=output_budget_bytes,pages=pages,artifact_bytes=sum(item["bytes"] for item in pages),
        output_estimate=estimate_native_weather_v10_review(hierarchy,include_hour_flux=include_hour_flux),
        original_hour_pages={direction:index["scenarios"][direction]["pages"]["1.25"] for direction in ("eastward","westward")},
        diagnostic_only=not accepted["numerical_gate_passed"],wet_display_threshold_m=1e-9,
        binary_semantics="raw little-endian row-major; shape*dtype bytes exact; native row order joins cell_membership; bed from pinned hierarchy; time=frame_index*3600",
        physics_semantics="v10 rain-first finite infiltration with remaining capacity drawing surface water; all valid cells experimentally permeable; permanent lake impermeability not modelled",
        flags=dict(hydraulic_ready=False,transient_converged=False,publishable=False,natural_outlet_verified=False,water_interpolation=False,water_generated=False),
        semantics="Native four-state samples, exclusive contribution catchment inventories. Bed+depth is not a continuous water surface or river width/depth. Hour face directional volume/activity is an integral, not Q or spill onset. Unknown cells omitted by pinned valid_mask.")
    result["identity_sha256"] = _hash(result)
    return result


def _encode(result):
    return json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf8")


def _verify(directory, result, hierarchy, index, arguments):
    if {entry.name for entry in directory.iterdir()} != {"index.json",*(item["file"] for item in result["pages"])}:
        raise ValueError("v10 review missing/extra page rejected")
    generated = _payloads(hierarchy,index,result["include_hour_flux"])
    for number, record in enumerate(result["pages"]):
        try:
            value = next(generated)
        except StopIteration as error:
            raise ValueError("v10 review extra descriptor rejected") from error
        expected, payload = _artifact(value,number)
        if record != expected or record["bytes"] > PAGE_BYTES:
            raise ValueError("v10 review canonical descriptor rejected")
        target = directory/record["file"]
        if target.is_symlink() or not target.resolve().is_relative_to(directory.resolve()) or target.stat().st_size != len(payload):
            raise ValueError("v10 review page path/bytes rejected")
        if file_sha256(target) != hashlib.sha256(payload).hexdigest():
            raise ValueError("v10 review raw data mismatch")
    try:
        next(generated)
    except StopIteration:
        pass
    else:
        raise ValueError("v10 review missing descriptor rejected")
    for direction in index["scenarios"].values():
        for pages in direction["pages"].values():
            for page in pages:
                for name in ("storage","checkpoint"):
                    record = page[name]
                    if file_sha256(record["path"]) != record["expected_sha256"]:
                        raise ValueError("v10 review input changed during export/cold read")
    for name in ("weather_index_record","hierarchy_record","source_record","run_inputs_record","execution_resource_record"):
        record = arguments[name]
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("v10 review primary input pin changed")
    weather = _json(arguments["weather_index_record"])
    for case in weather["cases"].values():
        record = case["record"]
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("v10 review weather artifact pin changed")
    base = Path(arguments.get("code_root") or Path(__file__).resolve().parents[1]).resolve()
    for name, digest in index["code_sha256"].items():
        target = (base/name).resolve()
        if not target.is_relative_to(base) or file_sha256(target) != digest:
            raise ValueError("v10 review frozen dependency changed")
    if file_sha256(result["input_index"]) != arguments["expected_sha256"]:
        raise ValueError("v10 review source final index pin changed")
    _memory()


def export_native_weather_v10_review(input_index, directory, *, acceptance_arguments, selected_steps_s=(1.25,), include_hour_flux=False, output_budget_bytes=DEFAULT_OUTPUT_BYTES):
    _selection(selected_steps_s,include_hour_flux,output_budget_bytes)
    accepted,hierarchy,index = _prepare(input_index,acceptance_arguments)
    if estimate_native_weather_v10_review(hierarchy,include_hour_flux=include_hour_flux)["estimated_output_upper_bytes"] > output_budget_bytes:
        raise ValueError("v10 review preflight output budget exceeded")
    directory = Path(directory).absolute()
    if directory.exists():
        raise FileExistsError(directory)
    directory.parent.mkdir(parents=True,exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".v10-native-review-",dir=directory.parent))
    try:
        pages, written = [], 0
        for number,value in enumerate(_payloads(hierarchy,index,include_hour_flux)):
            record,payload = _artifact(value,number)
            written += len(payload)
            if written > output_budget_bytes:
                raise ValueError("v10 review actual output budget exceeded")
            publish_bytes(staging/record["file"],payload)
            pages.append(record)
        result = _manifest(input_index,acceptance_arguments,accepted,hierarchy,index,pages,include_hour_flux,output_budget_bytes)
        payload = _encode(result)
        if len(payload) > PAGE_BYTES or written+len(payload) > output_budget_bytes:
            raise ValueError("v10 review final index/output budget exceeded")
        publish_bytes(staging/"index.json",payload)
        _verify(staging,result,hierarchy,index,acceptance_arguments)
        staging.rename(directory)
        return result
    except BaseException:
        shutil.rmtree(staging)
        raise


def load_native_weather_v10_review(path, *, expected_sha256, expected_identity, input_index, acceptance_arguments,
                                   selected_steps_s=(1.25,), include_hour_flux=False, output_budget_bytes=DEFAULT_OUTPUT_BYTES):
    _selection(selected_steps_s,include_hour_flux,output_budget_bytes)
    path = Path(path).absolute()
    result = _json(dict(path=str(path),expected_sha256=expected_sha256),PAGE_BYTES)
    unsigned = {name:value for name,value in result.items() if name!="identity_sha256"}
    if result.get("schema") != SCHEMA or result.get("identity_sha256") != expected_identity or _hash(unsigned) != expected_identity:
        raise ValueError("v10 review external identity/schema rejected")
    accepted,hierarchy,index = _prepare(input_index,acceptance_arguments)
    expected = _manifest(input_index,acceptance_arguments,accepted,hierarchy,index,result["pages"],include_hour_flux,output_budget_bytes)
    if result != expected:
        raise ValueError("v10 review manifest semantic mismatch")
    if sum(item.stat().st_size for item in path.parent.iterdir() if item.is_file()) > output_budget_bytes:
        raise ValueError("v10 review cold output budget exceeded")
    _verify(path.parent,result,hierarchy,index,acceptance_arguments)
    if file_sha256(path) != expected_sha256:
        raise ValueError("v10 review final pin changed")
    return result
