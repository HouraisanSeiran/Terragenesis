"""Native saved-hour review, exclusively behind complete v8 IO acceptance."""

import json
import math
from pathlib import Path
import shutil
import tempfile
import hashlib

import numpy as np

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.td_hour_pages_acceptance_io import load_hour_pages_index, _load, _json, _memory, STATES
from terrain_pipeline.td_surface_reaches import _hash, _plain, _freeze
from terrain_pipeline.basin_topology import _read_json as _read_json

SCHEMA = "td-hour-pages-native-review-v2"
MAX_BYTES = 8 * 1024 * 1024
CHUNK_ROWS = 2048
DEFAULT_OUTPUT_BYTES = 512 * 1024 * 1024
LEDGERS = ("rain_volume_m3", "soil_et_m3", "surface_et_m3", "boundary_outflow_m3", "internal_net_m3", "storage_change_m3", "balance_residual_m3")
FLAGS = dict(hydraulic_ready=False, transient_converged=False, publishable=False,
             natural_outlet_verified=False, water_interpolation=False, water_generated=False)


def _leaves(hierarchy):
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    valid = arrays["valid_mask"].ravel()
    owner = arrays["contribution_owner"].ravel()
    nodes, labels = np.unique(owner[valid], return_inverse=True)
    columns = arrays["height_m"].shape[1]
    leaves = []
    for node in nodes:
        cells = np.flatnonzero(valid & (owner == node))
        terminal = cells[arrays["receiver"][cells] < 0]
        if len(terminal) != 1:
            raise ValueError("unique catchment terminal required")
        terminal = int(terminal[0])
        row, column = divmod(terminal, columns)
        xyz = [float(metadata["origin_m_xz"][0] + column * metadata["spacing_m"]),
               float(arrays["height_m"].ravel()[terminal]), float(metadata["origin_m_xz"][1] + row * metadata["spacing_m"])]
        kind = "protected_terminal" if arrays["protected_mask"].ravel()[terminal] else "unknown_contact" if arrays["node_unknown_contact"][node] else "engineered_open" if arrays["open_boundary_mask"].ravel()[terminal] else "internal_basin"
        leaves.append(dict(leaf_id=int(node), stable_leaf_id="leaf:" + _hash([metadata["source_identity_sha256"], [value.hex() for value in xyz]]), terminal_cell_id=terminal, terminal_xyz_m=xyz, terminal_kind=kind, cell_count=len(cells)))
    return valid, labels, leaves


def _chunks(kind, rows, *, scenario=None, step=None, frame=None):
    chunk = []
    index = 0
    for row in rows:
        chunk.append(row)
        if len(chunk) == CHUNK_ROWS:
            yield dict(kind=kind, scenario=scenario, step_s=step, frame_index=frame, chunk_index=index, rows=chunk)
            chunk, index = [], index + 1
    if chunk:
        yield dict(kind=kind, scenario=scenario, step_s=step, frame_index=frame, chunk_index=index, rows=chunk)


def _selection(selected_steps_s, include_hour_flux, output_budget_bytes):
    if tuple(selected_steps_s) not in ((1.25,), (2.5,), (2.5, 1.25)) or type(include_hour_flux) is not bool:
        raise ValueError("explicit supported step selection and flux boolean required")
    if type(output_budget_bytes) is not int or not 0 < output_budget_bytes <= 10 * 1024 ** 3:
        raise ValueError("predeclared output budget must be positive and <=10GiB")


def estimate_review_output(hierarchy, *, selected_steps_s=(1.25,), include_hour_flux=False):
    valid, labels, leaves = _leaves(hierarchy)
    cells, faces = int(valid.sum()), len(hierarchy["arrays"]["face_cells"])
    series = 2 * len(selected_steps_s)
    binary = cells * 4 * 8 + series * 25 * cells * 4 * 8
    if include_hour_flux:
        binary += faces * 2 * 8 + series * 24 * (faces * 4 * 8 + cells * 2 * 8)
    json_upper = (len(leaves) * (1 + series * 25) + 1) * 2048
    return dict(binary_bytes_exact=binary, leaf_json_bytes_upper=json_upper,
        index_and_shard_overhead_reserve_bytes=2 * MAX_BYTES,
        estimated_output_upper_bytes=binary + json_upper + 2 * MAX_BYTES,
        cells=cells, faces=faces, series=series)


def _binary_chunks(kind, matrix, *, columns, scenario=None, step=None, frame=None):
    for start in range(0, len(matrix), CHUNK_ROWS):
        block = np.ascontiguousarray(matrix[start:start + CHUNK_ROWS])
        yield dict(kind=kind, scenario=scenario, step_s=step, frame_index=frame,
            chunk_index=start // CHUNK_ROWS, row_offset=start, row_count=len(block),
            columns=columns, dtype=block.dtype.str, shape=list(block.shape), binary=block)


def _payloads(hierarchy, index, selected_steps_s=(1.25,), include_hour_flux=False):
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    valid, labels, leaves = _leaves(hierarchy)
    cells = np.flatnonzero(valid)
    count = len(leaves)
    area = metadata["spacing_m"] ** 2
    bed = arrays["height_m"].ravel()
    owner = arrays["contribution_owner"].ravel()
    yield from _chunks("leaves", iter(leaves))
    membership = np.column_stack((cells, owner[cells], arrays["receiver"][cells], arrays["protected_mask"].ravel()[cells])).astype("<i8")
    yield from _binary_chunks("cell_membership", membership, columns=["cell_id", "leaf_id", "receiver_cell_id", "protected"])
    del membership
    if include_hour_flux:
        yield from _binary_chunks("face_membership", arrays["face_cells"].astype("<i8"), columns=["first_cell_id", "second_cell_id"])
    for scenario in ("ordinary", "strong"):
        for step in selected_steps_s:
            previous_total = None
            for hour, record in enumerate(index["scenarios"][scenario]["pages"][str(step)]):
                storage = _load(record["storage"])
                water = storage["arrays"]
                threshold = storage["metadata"]["parameters"]["wet_threshold_m"]
                for local in ((0, 1) if hour == 0 else (1,)):
                    frame = hour + local
                    depth = water["depth_m"][local, valid]
                    wet = depth > threshold
                    surface = bed[valid] + depth
                    fields = {name: np.bincount(labels, weights=water[name][local, valid] * area / (1 if name == "depth_m" else 1000), minlength=count) for name in STATES}
                    total = sum(fields.values())
                    minimum, maximum = np.full(count, np.inf), np.full(count, -np.inf)
                    np.minimum.at(minimum, labels[wet], surface[wet])
                    np.maximum.at(maximum, labels[wet], surface[wet])
                    wet_count = np.bincount(labels[wet], minlength=count)
                    ledgers = None if frame == 0 else {name: np.bincount(labels, weights=water[name][0, valid], minlength=count) for name in LEDGERS}
                    residual = None if frame == 0 else ledgers["rain_volume_m3"] + ledgers["internal_net_m3"] - ledgers["soil_et_m3"] - ledgers["surface_et_m3"] - ledgers["boundary_outflow_m3"] - (total - previous_total)
                    def leaf_rows():
                        for position, leaf in enumerate(leaves):
                            allowed = None if frame == 0 else 1e-6 + 1e-10 * (abs(total[position]) + abs(previous_total[position]))
                            yield dict(leaf_id=leaf["leaf_id"], stable_leaf_id=leaf["stable_leaf_id"], time_s=frame * 3600.,
                                inventories_m3={name: float(values[position]) for name, values in fields.items()}, wet_count=int(wet_count[position]),
                                water_surface_min_m=float(minimum[position]) if wet_count[position] else None,
                                water_surface_max_m=float(maximum[position]) if wet_count[position] else None,
                                interval_ledger_m3=None if ledgers is None else {name: float(values[position]) for name, values in ledgers.items()},
                                leaf_budget=None if frame == 0 else dict(residual_m3=float(residual[position]), allowed_m3=float(allowed), passed=bool(abs(residual[position]) <= allowed)))
                    yield from _chunks("leaf_states", leaf_rows(), scenario=scenario, step=step, frame=frame)
                    native = np.column_stack([water[name][local, valid] for name in STATES]).astype("<f8")
                    yield from _binary_chunks("native_states", native, columns=list(STATES), scenario=scenario, step=step, frame=frame)
                    del native
                    stores = water["depth_m"][local, valid] + sum(water[name][local, valid] for name in STATES[1:]) / 1000
                    actual = math.fsum((stores * area).tolist())
                    if abs(math.fsum(total.tolist()) - actual) > 1e-6 + abs(actual) * 1e-10:
                        raise ValueError("exclusive leaf inventory coverage does not close")
                    previous_total = total
                if include_hour_flux:
                    face_names = ["face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"]
                    face_values = np.column_stack([water[name] for name in face_names]).astype("<f8")
                    yield from _binary_chunks("hour_faces", face_values, columns=face_names, scenario=scenario, step=step, frame=hour + 1)
                    del face_values
                    receiver_names = ["routed_volume_m3", "wet_duration_s"]
                    receiver_values = np.column_stack([water[name][valid] for name in receiver_names]).astype("<f8")
                    yield from _binary_chunks("hour_receivers", receiver_values, columns=receiver_names, scenario=scenario, step=step, frame=hour + 1)
                    del receiver_values
                del storage, water
                _memory()


def _prepare(input_index, acceptance_arguments):
    accepted = load_hour_pages_index(input_index, **acceptance_arguments)
    hierarchy = load_basin_hierarchy(**acceptance_arguments["hierarchy_record"])
    index = _json(dict(path=str(input_index), expected_sha256=acceptance_arguments["expected_sha256"]))
    return accepted, hierarchy, index


def _encode(value):
    payload = json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise ValueError("review JSON shard exceeds 8MiB")
    return payload


def _artifact(value, number):
    descriptor = {key: item for key, item in value.items() if key != "binary"}
    binary = "binary" in value
    payload = value["binary"].tobytes(order="C") if binary else _encode(value)
    if len(payload) > MAX_BYTES:
        raise ValueError("review binary shard exceeds 8MiB")
    digest = hashlib.sha256(payload).hexdigest()
    record = dict(file=f"page-{number:06d}.{'bin' if binary else 'json'}", expected_sha256=digest,
        expected_identity=_hash([descriptor, digest]), bytes=len(payload), format="raw-le" if binary else "json",
        **{key: descriptor[key] for key in ("kind", "scenario", "step_s", "frame_index", "chunk_index")},
        row_count=descriptor["row_count"] if binary else len(value["rows"]))
    if binary:
        record.update({key: descriptor[key] for key in ("columns", "dtype", "shape", "row_offset")})
    return record, payload


def _manifest(input_index, arguments, accepted, hierarchy, pages, selected_steps_s=(1.25,), include_hour_flux=False, output_budget_bytes=DEFAULT_OUTPUT_BYTES):
    acceptance_summary = {key: _plain(value) for key, value in accepted.items() if key != "resource"}
    input_pages = _json(dict(path=str(input_index), expected_sha256=arguments["expected_sha256"]))
    references = {scenario: {str(step): [{key: page[key] for key in ("hour", "storage", "checkpoint", "forcing_identity")}
        for page in input_pages["scenarios"][scenario]["pages"][str(step)]] for step in selected_steps_s} for scenario in ("ordinary", "strong")}
    value = dict(schema=SCHEMA, input_index=str(input_index), acceptance_arguments=_plain(arguments),
        acceptance=acceptance_summary, hierarchy_identity_sha256=hierarchy["identity_sha256"],
        grid=dict(shape_zx=list(hierarchy["arrays"]["height_m"].shape), spacing_m=hierarchy["metadata"]["spacing_m"], origin_m_xz=hierarchy["metadata"]["origin_m_xz"]),
        frames=25, hours=24, chunk_rows=CHUNK_ROWS, max_page_bytes=MAX_BYTES, pages=pages, flags=FLAGS,
        selected_steps_s=list(selected_steps_s), include_hour_flux=include_hour_flux, output_budget_bytes=output_budget_bytes,
        output_estimate=estimate_review_output(hierarchy, selected_steps_s=selected_steps_s, include_hour_flux=include_hour_flux),
        artifact_bytes=sum(page["bytes"] for page in pages),
        original_hour_pages=references,
        binary_semantics="raw little-endian row-major blocks, no headers; exact byte count=product(shape)*dtype.itemsize; native row order joins cell_membership row_offset, time=frame_index*3600; bed from pinned hierarchy, wet threshold from pinned page parameters; no unknown interpolation",
        diagnostic_only=not all(scenario["numerical_gate_passed"] for scenario in accepted["scenarios"].values()),
        semantics="Native saved samples only; bed+depth is not a continuous water surface or channel width/depth. Leaf inventories are exclusive contribution-owner cells, not a uniform stage. Hour directional volume/activity and receiver accounts are actual page integrals, never Q or inferred spill onset. Unknown cells omitted explicitly by hierarchy valid_mask. No static reach smoothing; native receiver endpoints support optional downstream line joining.")
    value["identity_sha256"] = _hash(value)
    return value


def export_hour_pages_review(input_index, directory, *, acceptance_arguments, selected_steps_s=(1.25,), include_hour_flux=False, output_budget_bytes=DEFAULT_OUTPUT_BYTES):
    _selection(selected_steps_s, include_hour_flux, output_budget_bytes)
    accepted, hierarchy, index = _prepare(input_index, acceptance_arguments)
    estimate = estimate_review_output(hierarchy, selected_steps_s=selected_steps_s, include_hour_flux=include_hour_flux)
    if estimate["estimated_output_upper_bytes"] > output_budget_bytes:
        raise ValueError("diagnostic: preflight output estimate exceeds predeclared budget; no final published")
    directory = Path(directory).absolute()
    if directory.exists():
        raise FileExistsError(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".hour-review-", dir=directory.parent))
    try:
        pages = []
        written = 0
        for number, value in enumerate(_payloads(hierarchy, index, selected_steps_s, include_hour_flux)):
            record, payload = _artifact(value, number)
            written += len(payload)
            if written > output_budget_bytes:
                raise ValueError("diagnostic: actual output exceeds predeclared budget")
            publish_bytes(temporary / record["file"], payload)
            pages.append(record)
        result = _manifest(input_index, acceptance_arguments, accepted, hierarchy, pages, selected_steps_s, include_hour_flux, output_budget_bytes)
        index_payload = _encode(result)
        if written + len(index_payload) > output_budget_bytes:
            raise ValueError("diagnostic: root output bytes exceed predeclared budget")
        publish_bytes(temporary / "index.json", index_payload)
        if _memory()[1] is None:
            raise ValueError("private memory observation required before final review publication")
        temporary.rename(directory)
        return _freeze(result)
    except BaseException:
        shutil.rmtree(temporary)
        raise


def load_hour_pages_review(path, *, expected_sha256, expected_identity, input_index, acceptance_arguments, selected_steps_s=(1.25,), include_hour_flux=False, output_budget_bytes=DEFAULT_OUTPUT_BYTES):
    _selection(selected_steps_s, include_hour_flux, output_budget_bytes)
    path = Path(path)
    if path.is_symlink() or path.name != "index.json" or path.stat().st_size > MAX_BYTES or file_sha256(path) != expected_sha256:
        raise ValueError("review final index pin/layout rejected")
    result = _read_json(path)
    unsigned = {key: value for key, value in result.items() if key != "identity_sha256"}
    if result.get("schema") != SCHEMA or result.get("identity_sha256") != expected_identity or _hash(unsigned) != expected_identity:
        raise ValueError("review external identity/schema rejected")
    accepted, hierarchy, index = _prepare(input_index, acceptance_arguments)
    if estimate_review_output(hierarchy, selected_steps_s=selected_steps_s, include_hour_flux=include_hour_flux)["estimated_output_upper_bytes"] > output_budget_bytes:
        raise ValueError("review predeclared estimate budget rejected")
    records = result["pages"]
    if {entry.name for entry in path.parent.iterdir()} != {"index.json"} | {record["file"] for record in records}:
        raise ValueError("review extra/missing page coverage")
    number = 0
    written = path.stat().st_size
    for number, value in enumerate(_payloads(hierarchy, index, selected_steps_s, include_hour_flux), start=1):
        if number > len(records):
            raise ValueError("review incomplete page list")
        record = records[number - 1]
        expected_record, payload = _artifact(value, number - 1)
        name = expected_record["file"]
        target = path.parent / name
        if record["file"] != name or target.is_symlink() or not target.is_file():
            raise ValueError("review page order/path rejected")
        written += len(payload)
        if written > output_budget_bytes or target.stat().st_size != len(payload) or target.read_bytes() != payload:
            raise ValueError("review page semantic/pin mismatch")
        if record != expected_record:
            raise ValueError("review page metadata coverage mismatch")
    if number != len(records):
        raise ValueError("review extra page list")
    expected = _manifest(input_index, acceptance_arguments, accepted, hierarchy, records, selected_steps_s, include_hour_flux, output_budget_bytes)
    expected.pop("identity_sha256")
    if _hash(expected) != expected_identity:
        raise ValueError("review input/flags/time identity mismatch")
    _memory()
    return _freeze(result)
