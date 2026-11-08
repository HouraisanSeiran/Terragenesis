"""Strict cold-read regional certificates; never prepare or advance dynamics."""

import json
from pathlib import Path
import zipfile

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.regional_surface_hydraulics import (
    SurfaceBudget, validate_budget, validate_surface_geometry, limited_inertial_fluxes, _net_flux)


GEOMETRY = {"H0_m": ((256, 256), "float64"), "H2_m": ((256, 256), "float64"),
    "face_left": ((130560,), "int64"), "face_right": ((130560,), "int64"),
    "face_crest_m": ((130560,), "float64"), "boundary_cell": ((1024,), "int64"),
    "boundary_kind": ((1024,), "int64"), "boundary_crest_m": ((1024,), "float64")}


def strict_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate regional JSON key")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("nonfinite regional JSON constant")
    if Path(path).stat().st_size > 1024**2:
        raise ValueError("bounded regional JSON")
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def read_arrays(path, specs, *, expected_sha256):
    path = Path(path)
    if file_sha256(path) != expected_sha256 or path.stat().st_size > 128 * 1024**2:
        raise ValueError("trusted archive SHA/size mismatch")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(specs) or set(names) != {key + ".npy" for key in specs}:
            raise ValueError("exact regional archive keys required")
        for key, (shape, dtype) in specs.items():
            info = archive.getinfo(key + ".npy")
            if info.file_size > int(np.prod(shape)) * np.dtype(dtype).itemsize + 4096:
                raise ValueError("regional header allocation ceiling")
            with archive.open(info) as stream:
                version = np.lib.format.read_magic(stream)
                if version == (1, 0):
                    found_shape, fortran, found_dtype = np.lib.format.read_array_header_1_0(stream)
                elif version == (2, 0):
                    found_shape, fortran, found_dtype = np.lib.format.read_array_header_2_0(stream)
                else:
                    raise ValueError("regional NPY header version")
                if found_shape != shape or found_dtype != np.dtype(dtype) or fortran:
                    raise ValueError("regional exact header shape/dtype/order")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in specs}
    for value in arrays.values():
        if not np.isfinite(value).all():
            raise ValueError("regional finite array gate")
        value.flags.writeable = False
    return arrays


def validate_interval(packet, geometry, forcing_volume, *, duration_s):
    area = geometry["metadata"]["spacing_m"]**2
    before, after = packet["depth_before_m"], packet["depth_after_m"]
    if before.shape != (65536,) or after.shape != before.shape or (before < 0).any() or (after < 0).any():
        raise ValueError("interval depth shape/positivity")
    if not np.allclose(packet["forcing_volume_m3"], forcing_volume.ravel(), rtol=2e-12, atol=1e-10):
        raise ValueError("saved full-area forcing mismatch")
    residual = area * (after - before) - packet["forcing_volume_m3"] - _net_flux(
        geometry, packet["internal_transfer_m3"], packet["boundary_transfer_m3"])
    tolerance = 1e-8 + 2e-12 * np.maximum(area * np.maximum(before, after), np.abs(packet["forcing_volume_m3"]))
    if (np.abs(residual) > tolerance).any() or duration_s <= 0:
        raise ValueError("saved local continuity failure")
    return float(np.abs(residual).max()), float(np.abs(residual).sum())


def validate_full_region_coordinates(geometry):
    meta = geometry["metadata"]
    if meta["shape"] != [256, 256] or meta["spacing_m"] != 30. or meta["origin_m_xz"] != [-184320., 61440.] or meta["area_m2"] != 58982400.:
        raise ValueError("fixed actual full-region 30m source footprint required")


def validate_momentum(packet, meta, geometry, budget):
    dt = meta["dt_s"]
    if not isinstance(dt, (int, float)) or not np.isfinite(dt) or not 0 < dt <= budget.max_dt_s:
        raise ValueError("sampled momentum dt")
    if (packet["forcing_m3_s"] < 0).any() or (packet["depth_before_m"] < 0).any():
        raise ValueError("sampled forcing/depth positivity")
    kinds = geometry["arrays"]["boundary_kind"]
    crest = geometry["arrays"]["boundary_crest_m"]
    exterior = np.where(kinds == 1, crest, packet["tailwater_m"])
    maximum = max(float(packet["depth_before_m"].max()), float(np.maximum(exterior - crest, 0)[kinds != 0].max(initial=0)))
    gravity_cap = budget.inertial_cfl * geometry["metadata"]["spacing_m"] / 2 / np.sqrt(budget.gravity_m_s2 * maximum) if maximum else np.inf
    if dt > gravity_cap + 1e-10:
        raise ValueError("sampled gravity CFL")
    internal, boundary, limiter = limited_inertial_fluxes(geometry, packet["depth_before_m"],
        packet["internal_q_before_m3_s"], packet["boundary_q_before_m3_s"], packet["tailwater_m"],
        packet["forcing_m3_s"], dt, budget)
    for actual, expected in ((packet["internal_q_after_m3_s"], internal), (packet["boundary_q_after_m3_s"], boundary)):
        if not np.allclose(actual, expected, rtol=1e-12, atol=1e-12):
            raise ValueError("sampled discrete momentum/limiter forged")
    if meta["limiter"] != limiter:
        raise ValueError("sampled limiter ledger forged")
    expected_depth = packet["depth_before_m"] + dt * (packet["forcing_m3_s"] + _net_flux(geometry, internal, boundary)) / geometry["metadata"]["spacing_m"]**2
    if not np.allclose(packet["depth_after_m"], expected_depth, rtol=1e-12, atol=1e-13):
        raise ValueError("sampled momentum continuity forged")


def load_case(directory, *, expected_manifest_sha256, trusted_height, source_identity, forcing_volumes):
    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    if file_sha256(manifest_path) != expected_manifest_sha256:
        raise ValueError("external case manifest SHA required")
    manifest = strict_json(manifest_path)
    for name, digest in manifest["artifacts"].items():
        if Path(name).name != name or file_sha256(directory / name) != digest:
            raise ValueError("regional artifact SHA/name mismatch")
    def metadata(name):
        path = directory / (name + ".json")
        if path.name not in manifest["artifacts"] or path.stat().st_size > 1024**2:
            raise ValueError("bounded authenticated metadata")
        return strict_json(path)
    def arrays(name, specs):
        return read_arrays(directory / (name + ".npz"), specs, expected_sha256=manifest["artifacts"][name + ".npz"])
    geometry = {"arrays": arrays("geometry", GEOMETRY), "metadata": metadata("geometry")}
    validate_surface_geometry(geometry, trusted_height=trusted_height, source_identity=source_identity)
    validate_full_region_coordinates(geometry)
    state_meta = metadata("states")
    meta = state_meta["metadata"]
    binding = strict_json(directory / "binding.json")
    declaration = strict_json(directory.parent / "predeclared.json")
    if declaration["source_identity"] != source_identity or declaration["height_source_identity"] != binding["height_source_identity"]:
        raise ValueError("case declaration source binding")
    kinds = np.ones(1024, np.int64)
    if directory.name == "uniform_heavy_tailwater":
        kinds[np.r_[256 + np.arange(252, 256), 768 + np.arange(252, 256)]] = 2
    if not np.array_equal(geometry["arrays"]["boundary_kind"], kinds) or not np.array_equal(geometry["arrays"]["boundary_crest_m"], trusted_height.ravel()[geometry["arrays"]["boundary_cell"]]):
        raise ValueError("fixed case engineering/SE tailwater boundary")
    if meta["forcing_identity"] != binding["forcing_manifest_sha256"] or binding["source_identity"] != source_identity or meta["budget"] != binding["budget"]:
        raise ValueError("regional forcing/source/budget binding")
    for value in meta.values():
        if isinstance(value, (int, float)) and (isinstance(value, bool) or not np.isfinite(value)):
            raise ValueError("regional finite scalar metadata")
    budget = SurfaceBudget(**meta["budget"])
    validate_budget(budget)
    if meta["schema"] != "regional-surface-local-inertial-D4-implicit-new-q-drag-v2" or meta["source_identity"] != source_identity:
        raise ValueError("regional dynamic algorithm/source identity")
    committed, requested = meta["committed_time_s"], meta["requested_time_s"]
    if not 0 <= committed <= requested <= budget.max_duration_s:
        raise ValueError("regional committed/requested time")
    if meta["status"] == "completed":
        if meta["failure"] is not None or abs(committed - requested) > 1e-7:
            raise ValueError("regional complete status mismatch")
    elif meta["status"] == "refused":
        if not isinstance(meta["failure"], dict) or committed >= requested:
            raise ValueError("regional refused status mismatch")
    else:
        raise ValueError("unknown regional dynamic status")
    if type(meta["substeps"]) is not int or not 0 <= meta["substeps"] <= budget.max_substeps or type(meta["face_evaluations"]) is not int or not 0 <= meta["face_evaluations"] <= budget.max_face_evaluations:
        raise ValueError("regional integer work budget")
    snapshot_count = None
    with zipfile.ZipFile(directory / "states.npz") as archive:
        with archive.open("time_s.npy") as stream:
            version = np.lib.format.read_magic(stream)
            header = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
            shape, fortran, dtype = header(stream)
            if len(shape) != 1 or not 1 <= shape[0] <= budget.max_snapshots or dtype != np.float64 or fortran:
                raise ValueError("bounded time header")
            snapshot_count = shape[0]
    states = arrays("states", {"time_s": ((snapshot_count,), "float64"),
        "depth_m": ((snapshot_count, 256, 256), "float64"), "initial_depth_m": ((256, 256), "float64"),
        "ledger": ((snapshot_count, 5), "float64"), "final_internal_q_m3_s": ((130560,), "float64"),
        "final_boundary_q_m3_s": ((1024,), "float64")})
    times, depths, ledger = states["time_s"], states["depth_m"], states["ledger"]
    if times[0] != 0 or abs(times[-1] - committed) > 1e-7 or (np.diff(times) <= 0).any() or (depths < 0).any() or (depths > budget.max_depth_m).any():
        raise ValueError("regional saved depth/time constraints")
    if not np.array_equal(states["initial_depth_m"], depths[0]) or np.any(states["initial_depth_m"] != 0):
        raise ValueError("full runner initial dry surface identity")
    if np.any(np.abs(times[1:-1] / 900. - np.rint(times[1:-1] / 900.)) > 1e-8):
        raise ValueError("frozen full-run intermediate snapshots must coincide with saved interval endpoints")
    area = geometry["metadata"]["spacing_m"]**2
    volumes = depths.sum(axis=(1, 2)) * area
    if not np.allclose(ledger[:, 3], volumes, atol=1e-7, rtol=1e-12) or (ledger[:, :3] < 0).any() or (np.diff(ledger[:, :3], axis=0) < -1e-8).any():
        raise ValueError("regional snapshot volume/cumulative ledger")
    balance = volumes - volumes[0] - ledger[:, 0] - ledger[:, 1] + ledger[:, 2]
    if not np.allclose(ledger[:, 4], balance, atol=1e-7, rtol=1e-12) or (np.abs(balance) > 1e-5 + 2e-11 * np.maximum(volumes, ledger[:, 0])).any():
        raise ValueError("regional cumulative conservation")
    for key, value in (("initial_volume_m3", volumes[0]), ("final_volume_m3", volumes[-1]), ("supplied_m3", ledger[-1, 0]), ("boundary_input_m3", ledger[-1, 1]), ("boundary_output_m3", ledger[-1, 2])):
        if not np.isclose(meta[key], value, rtol=1e-12, atol=1e-7):
            raise ValueError("regional metadata ledger mismatch")
    interval_specs = {"depth_before_m": ((65536,), "float64"), "depth_after_m": ((65536,), "float64"),
        "forcing_volume_m3": ((65536,), "float64"), "internal_transfer_m3": ((130560,), "float64"),
        "boundary_transfer_m3": ((1024,), "float64"), "internal_q_before_m3_s": ((130560,), "float64"),
        "internal_q_after_m3_s": ((130560,), "float64"), "boundary_q_before_m3_s": ((1024,), "float64"),
        "boundary_q_after_m3_s": ((1024,), "float64")}
    previous = np.zeros(65536)
    previous_q = np.zeros(130560)
    previous_boundary = np.zeros(1024)
    end = maximum = total_l1 = net_exported = integrated_supplied = 0.
    count = int(np.ceil(committed / 900. - 1e-12))
    interval_names = {"interval-%03d.npz" % index for index in range(count)}
    actual_intervals = {name for name in manifest["artifacts"] if name.startswith("interval-") and name.endswith(".npz")}
    if actual_intervals != interval_names:
        raise ValueError("regional exact interval prefix archives")
    for index in range(count):
        name = "interval-%03d" % index
        packet, info = arrays(name, interval_specs), metadata(name)
        if info["interval"] != index or abs(info["time_start_s"] - end) > 1e-7:
            raise ValueError("regional interval continuity/time")
        for key, saved in (("depth_before_m", previous), ("internal_q_before_m3_s", previous_q), ("boundary_q_before_m3_s", previous_boundary)):
            if not np.array_equal(packet[key], saved):
                raise ValueError("regional saved state discontinuity")
        duration = info["time_end_s"] - end
        if abs(info["time_end_s"] - min((index + 1) * 900., committed)) > 1e-7:
            raise ValueError("regional forcing interval exact end")
        peak, l1 = validate_interval(packet, geometry, forcing_volumes[index] * duration / 900., duration_s=duration)
        integrated_supplied += float(packet["forcing_volume_m3"].sum())
        net_exported += float(packet["boundary_transfer_m3"].sum())
        maximum, total_l1 = max(maximum, peak), total_l1 + l1
        previous, previous_q, previous_boundary = packet["depth_after_m"], packet["internal_q_after_m3_s"], packet["boundary_q_after_m3_s"]
        end = info["time_end_s"]
        matches = np.flatnonzero(np.abs(times - end) < 1e-7)
        for snapshot in matches:
            if not np.allclose(depths[snapshot].ravel(), previous, rtol=1e-12, atol=1e-12):
                raise ValueError("snapshot/interval state binding")
            if not np.isclose(ledger[snapshot, 0], integrated_supplied, rtol=2e-11, atol=1e-7) or not np.isclose(ledger[snapshot, 2] - ledger[snapshot, 1], net_exported, rtol=2e-11, atol=1e-7):
                raise ValueError("snapshot/interval cumulative flux binding")
    if abs(end - committed) > 1e-7:
        raise ValueError("regional interval prefix incomplete")
    if not np.isclose(meta["supplied_m3"], integrated_supplied, rtol=2e-11, atol=1e-7) or not np.isclose(meta["boundary_output_m3"] - meta["boundary_input_m3"], net_exported, rtol=2e-11, atol=1e-7):
        raise ValueError("regional total integrated flux binding")
    for actual, expected in ((depths[-1].ravel(), previous), (states["final_internal_q_m3_s"], previous_q), (states["final_boundary_q_m3_s"], previous_boundary)):
        if not np.array_equal(actual, expected):
            raise ValueError("regional terminal state/Q mismatch")
    sample_count = 0
    expected_samples = {"momentum-%03d.npz" % index for index in range(0, count, 24)}
    actual_samples = {name for name in manifest["artifacts"] if name.startswith("momentum-") and name.endswith(".npz")}
    if actual_samples != expected_samples:
        raise ValueError("regional exact declared sample archives")
    for index in range(0, count, 24):
        name = "momentum-%03d" % index
        specs = {key: interval_specs[key] for key in ("depth_before_m", "depth_after_m", "internal_q_before_m3_s", "internal_q_after_m3_s", "boundary_q_before_m3_s", "boundary_q_after_m3_s")}
        specs.update({"forcing_m3_s": ((65536,), "float64"), "tailwater_m": ((1024,), "float64")})
        sample, sample_meta = arrays(name, specs), metadata(name)
        interval = arrays("interval-%03d" % index, interval_specs)
        if sample_meta["interval"] != index or sample_meta["time_start_s"] != index * 900.:
            raise ValueError("sampled momentum source time")
        if sample_meta["dt_s"] > min((index + 1) * 900., committed) - sample_meta["time_start_s"] + 1e-10:
            raise ValueError("sampled forcing remainder dt")
        for key in ("depth_before_m", "internal_q_before_m3_s", "boundary_q_before_m3_s"):
            if not np.array_equal(sample[key], interval[key]):
                raise ValueError("sampled momentum disconnected from interval state")
        if not np.allclose(sample["forcing_m3_s"], forcing_volumes[index].ravel() / 900., rtol=1e-12, atol=1e-13):
            raise ValueError("sampled momentum source forcing")
        tailwater = geometry["arrays"]["boundary_crest_m"].copy()
        if 48 <= index < 96:
            prescribed = geometry["arrays"]["boundary_kind"] == 2
            tailwater[prescribed] = trusted_height[-1, -1] + 10.
        if not np.array_equal(sample["tailwater_m"], tailwater):
            raise ValueError("sampled momentum prescribed tailwater")
        validate_momentum(sample, sample_meta, geometry, budget)
        sample_count += 1
    return {"geometry": geometry, "states": states, "metadata": state_meta, "interval_max_residual_m3": maximum,
        "interval_sum_absolute_residual_m3": total_l1, "sampled_momentum_steps": sample_count,
        "scope": "all_interval_continuity_and_sampled_momentum_not_full_trajectory",
        "snapshot_scope": "trusted_hash_plus_volume_ledger_and_matching_interval_endpoints_not_all_intermediate_step_momentum"}
