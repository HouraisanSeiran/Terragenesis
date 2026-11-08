"""Bounded, cold-readable serial refinement with complete material checkpoints.

Each saved native water/sediment product retains its existing schema and 128MiB
limit. Checkpoints carry the original-bed inventory basis across these products.
"""

from dataclasses import asdict
import json
from pathlib import Path
import time

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity, load_bundle, save_bundle
from .metric_channel_product import (
    NETWORK_FIELDS,
    make_channel_product,
    load_channel_product,
    save_channel_product,
)
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelForcing, ChannelNetwork
from .metric_resolution_exchange import refine_channel, restrict_inventory
from .metric_sediment import (
    MaterialParameters,
    SedimentConfig,
    SedimentDomain,
    SedimentForcing,
    solve_sediment,
    load_sediment,
    save_sediment,
)

SCHEMA = "terragenesis-resolution-series-v1"
CHECKPOINT_SCHEMA = "terragenesis-resolution-checkpoint-v1"
CHECKPOINT_FIELDS = (
    "water_volume_m3",
    "mobile_solid_m3",
    "loose_solid_m3",
    "cumulative_rock_removed_m3",
    "bed_elevation_m",
)


def _pin(path, bundle):
    return dict(
        path=path.name,
        sha256=file_sha256(path),
        identity_sha256=bundle["identity_sha256"],
    )


def _write_json(path, payload):
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _validated_solver_result(bundle):
    """The private producer path saves the unchanged, already checked result."""
    if any(value.flags.writeable for value in bundle["arrays"].values()):
        raise ValueError("solver result arrays must remain readonly before saving")
    if bundle["identity_sha256"] != identity(bundle["arrays"], bundle["metadata"]):
        raise ValueError("validated solver result changed before saving")


def _bundle(arrays, metadata):
    return dict(
        arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata)
    )


def _basis(
    network, forcing, material, material_inputs, channel_config, sediment_config, counts
):
    arrays = {
        "network_" + field: np.asarray(getattr(network, field)).copy()
        for field in NETWORK_FIELDS
    }
    arrays.update(
        forcing_time_seconds=forcing.time_seconds.copy(),
        forcing_local_q_m3_s=forcing.local_q_m3_s.copy(),
        counts=np.asarray(counts, np.int64).copy(),
    )
    metadata = dict(
        schema=SCHEMA,
        network_source_identity_sha256=network.source_identity_sha256,
        forcing_source_identity_sha256=forcing.source_identity_sha256,
        section_source=network.section_source,
        roughness_source=network.roughness_source,
        material=asdict(material),
        material_inputs=material_inputs,
        channel_config=asdict(channel_config),
        sediment_config=asdict(sediment_config),
    )
    return _bundle(arrays, metadata)


def _native(basis):
    a, m = basis["arrays"], basis["metadata"]
    if m["schema"] != SCHEMA:
        raise ValueError("invalid resolution basis")
    network = ChannelNetwork(
        **{field: a["network_" + field] for field in NETWORK_FIELDS},
        source_identity_sha256=m["network_source_identity_sha256"],
        section_source=m["section_source"],
        roughness_source=m["roughness_source"],
    )
    forcing = ChannelForcing(
        a["forcing_time_seconds"],
        a["forcing_local_q_m3_s"],
        m["forcing_source_identity_sha256"],
    )
    return network, forcing


def _validate_basis(basis):
    network, forcing = _native(basis)
    a, m = basis["arrays"], basis["metadata"]
    if set(a) != {"network_" + field for field in NETWORK_FIELDS} | {
        "forcing_time_seconds",
        "forcing_local_q_m3_s",
        "counts",
    }:
        raise ValueError("unexpected resolution basis arrays")
    MaterialParameters(**m["material"])
    ChannelConfig(**m["channel_config"])
    SedimentConfig(**m["sediment_config"])
    refine_channel("validate", network, forcing, a["counts"])
    if basis["identity_sha256"] != identity(a, m):
        raise ValueError("resolution basis identity changed")


def slice_forcing(forcing, start, end):
    if not forcing.time_seconds[0] <= start < end <= forcing.time_seconds[-1]:
        raise ValueError("segment outside original forcing")
    times = np.unique(
        np.r_[
            start,
            forcing.time_seconds[
                (forcing.time_seconds > start) & (forcing.time_seconds < end)
            ],
            end,
        ]
    ).astype(np.float64)
    rows = np.searchsorted(forcing.time_seconds, times[:-1], side="right") - 1
    return ChannelForcing(
        times, forcing.local_q_m3_s[rows].copy(), forcing.source_identity_sha256
    )


def _checkpoint(state, seconds, index, basis_identity, parent_identity):
    arrays = {
        field: np.asarray(state[field], np.float64).copy()
        for field in CHECKPOINT_FIELDS
    }
    arrays["time_seconds"] = np.array([seconds], np.float64)
    return _bundle(
        arrays,
        dict(
            schema=CHECKPOINT_SCHEMA,
            index=index,
            basis_identity_sha256=basis_identity,
            parent_checkpoint_identity_sha256=parent_identity,
        ),
    )


def _validate_checkpoint(bundle):
    a, m = bundle["arrays"], bundle["metadata"]
    if m["schema"] != CHECKPOINT_SCHEMA or set(a) != set(CHECKPOINT_FIELDS) | {
        "time_seconds"
    }:
        raise ValueError("invalid checkpoint fields")
    n = a["water_volume_m3"].size
    if (
        not 1 <= n <= 2048
        or a["time_seconds"].shape != (1,)
        or a["time_seconds"].dtype != np.float64
        or not np.isfinite(a["time_seconds"]).all()
    ):
        raise ValueError("invalid checkpoint size/time")
    for field in CHECKPOINT_FIELDS:
        value = a[field]
        if (
            value.shape != (n,)
            or value.dtype != np.float64
            or not np.isfinite(value).all()
            or (field != "bed_elevation_m" and np.any(value < 0.0))
        ):
            raise ValueError("invalid checkpoint stock: " + field)
    if bundle["identity_sha256"] != identity(a, m):
        raise ValueError("checkpoint identity mismatch")


def _load_checkpoint(directory, pin):
    result = load_bundle(
        directory / pin["path"],
        expected_sha256=pin["sha256"],
        validator=_validate_checkpoint,
    )
    if result["identity_sha256"] != pin["identity_sha256"]:
        raise ValueError("checkpoint identity pin mismatch")
    return result


def _initial_state(case, material, inputs):
    area = case.network.width_m * case.network.length_m
    return dict(
        water_volume_m3=np.zeros(len(area)),
        mobile_solid_m3=np.zeros(len(area)),
        loose_solid_m3=area
        * inputs["initial_alluvium_depth_m"]
        * (1 - material.porosity),
        cumulative_rock_removed_m3=np.zeros(len(area)),
        bed_elevation_m=case.network.bed_elevation_m.copy(),
    )


def replay_segment(case, water, checkpoint, material, config, rock_floor):
    a = water["arrays"]
    net = case.network
    state = checkpoint["arrays"]
    area = net.width_m * net.length_m
    domain = SedimentDomain(
        net.receiver.copy(),
        area,
        net.width_m.copy(),
        state["bed_elevation_m"].copy(),
        rock_floor.copy(),
        state["loose_solid_m3"] / (1 - material.porosity),
        np.zeros(len(area), np.bool_),
        net.terminal_kind == "open_outflow",
        water["identity_sha256"],
        "checkpoint physical bed, remaining loose/rock stocks; frozen hydraulic geometry",
    )
    forcing = SedimentForcing(
        a["trace_time_seconds"].copy(),
        a["trace_volume_m3"][:-1].copy(),
        a["trace_depth_m"][:-1].copy(),
        a["trace_outflow_q_m3_s"].copy(),
        np.broadcast_to(net.bed_slope, a["trace_local_q_m3_s"].shape).copy(),
        a["trace_local_q_m3_s"] * checkpoint["metadata"]["external_concentration"],
        water["identity_sha256"],
        water["identity_sha256"],
        "same committed hydraulic intervals and original external concentration; mobile checkpoint carried",
    )
    return solve_sediment(
        domain,
        forcing,
        material,
        initial_mobile_solid_m3=state["mobile_solid_m3"].copy(),
        config=config,
    )


def _next_state(water, solid, previous):
    if solid is None:
        return {
            field: previous["arrays"][field].copy() for field in CHECKPOINT_FIELDS
        }, float(water["arrays"]["trace_time_seconds"][-1])
    a, b = water["arrays"], solid["arrays"]
    seconds = min(
        float(a["trace_time_seconds"][-1]), float(b["trace_time_seconds"][-1])
    )

    def at(bundle, field):
        return np.array(
            [
                np.interp(seconds, bundle["trace_time_seconds"], column)
                for column in bundle["trace_" + field].T
            ]
        )

    return (
        dict(
            water_volume_m3=at(a, "volume_m3"),
            mobile_solid_m3=at(b, "mobile_solid_m3"),
            loose_solid_m3=at(b, "bed_alluvium_solid_m3"),
            cumulative_rock_removed_m3=previous["arrays"]["cumulative_rock_removed_m3"]
            + at(b, "rock_removed_m3"),
            bed_elevation_m=at(b, "bed_elevation_m"),
        ),
        seconds,
    )


def run_series(
    network,
    forcing,
    counts,
    material,
    *,
    output,
    source_manifest,
    segment_seconds=15.0,
    channel_config=ChannelConfig(max_dt_seconds=0.25),
    sediment_config=SedimentConfig(max_dt_seconds=0.25),
    initial_alluvium_depth_m=0.01,
    rock_reserve_depth_m=1.0,
    external_concentration=1e-5,
    reuse_complete_prefix=None,
):
    directory = Path(output).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    if not np.isfinite(segment_seconds) or segment_seconds <= 0.0:
        raise ValueError("positive segment duration required")
    material_inputs = dict(
        initial_alluvium_depth_m=initial_alluvium_depth_m,
        rock_reserve_depth_m=rock_reserve_depth_m,
        external_solid_concentration_m3_per_m3=external_concentration,
    )
    basis = _basis(
        network,
        forcing,
        material,
        material_inputs,
        channel_config,
        sediment_config,
        counts,
    )
    basis_path = directory / "basis.npz"
    save_bundle(basis_path, basis, validator=_validate_basis)
    case = refine_channel("series", network, forcing, np.asarray(counts, np.int64))
    starts = np.unique(
        np.r_[
            forcing.time_seconds[0],
            np.arange(
                forcing.time_seconds[0] + segment_seconds,
                forcing.time_seconds[-1],
                segment_seconds,
            ),
            forcing.time_seconds[-1],
        ]
    )
    initial = _checkpoint(
        _initial_state(case, material, material_inputs),
        float(starts[0]),
        0,
        basis["identity_sha256"],
        None,
    )
    initial_path = directory / "checkpoint-0000.npz"
    save_bundle(initial_path, initial, validator=_validate_checkpoint)
    manifest = dict(
        schema=SCHEMA,
        basis=_pin(basis_path, basis),
        source_manifest=source_manifest,
        segment_endpoints_seconds=starts.tolist(),
        initial_checkpoint=_pin(initial_path, initial),
        segments=[],
        status="running",
        scope="serial spatial refinement, frozen-water active sediment; original-bed cumulative material checkpoint",
    )
    manifest_path = directory / "manifest.json"
    _write_json(manifest_path, manifest)
    previous = initial
    first_index = 0
    if reuse_complete_prefix is not None:
        parent_path = Path(reuse_complete_prefix).absolute()
        audit_started = time.perf_counter()
        audit_series(parent_path, sample_times=())
        prefix_cold_audit_seconds = time.perf_counter() - audit_started
        parent = json.loads(parent_path.read_text(encoding="utf-8"))
        parent_basis = load_bundle(
            parent_path.parent / parent["basis"]["path"],
            expected_sha256=parent["basis"]["sha256"],
            validator=_validate_basis,
        )
        if (
            parent_basis["identity_sha256"] != basis["identity_sha256"]
            or parent["source_manifest"] != source_manifest
        ):
            raise ValueError("continued series original basis changed")
        import os

        for saved in parent["segments"]:
            if (
                saved["water_status"] != "complete"
                or saved["solid_status"] != "complete"
            ):
                break
            copied = dict(saved)
            for field in ("water", "solid", "checkpoint"):
                copied[field] = dict(
                    saved[field],
                    path=os.path.relpath(
                        parent_path.parent / saved[field]["path"], directory
                    ),
                )
            manifest["segments"].append(copied)
        first_index = len(manifest["segments"])
        previous = (
            _load_checkpoint(directory, manifest["segments"][-1]["checkpoint"])
            if first_index
            else initial
        )
        transition = float(previous["arrays"]["time_seconds"][0])
        starts = np.r_[
            parent["segment_endpoints_seconds"][: first_index + 1],
            np.arange(
                transition + segment_seconds, forcing.time_seconds[-1], segment_seconds
            ),
            forcing.time_seconds[-1],
        ]
        manifest["segment_endpoints_seconds"] = starts.tolist()
        manifest["continuation"] = dict(
            parent_manifest_path=os.path.relpath(parent_path, directory),
            parent_manifest_sha256=file_sha256(parent_path),
            complete_prefix_segments=first_index,
            transition_time_seconds=float(previous["arrays"]["time_seconds"][0]),
            prefix_algorithm="pinned-parent-product-versions",
            suffix_algorithm="bounded-frozen-water-exner-v2",
            suffix_water_algorithm="manning-rectangular-explicit-v2",
        )
        manifest["prefix_cold_audit_seconds"] = prefix_cold_audit_seconds
        _write_json(manifest_path, manifest)
    rock_floor = (
        case.network.bed_elevation_m - initial_alluvium_depth_m - rock_reserve_depth_m
    )
    for index, (start, end) in enumerate(zip(starts[:-1], starts[1:])):
        if index < first_index:
            continue
        started = time.perf_counter()
        segment_forcing = slice_forcing(case.forcing, float(start), float(end))
        water = make_channel_product(
            case.network,
            segment_forcing,
            solve_channel(
                case.network,
                segment_forcing,
                initial_volume_m3=previous["arrays"]["water_volume_m3"].copy(),
                config=channel_config,
            ),
        )
        # Metadata used only by the replay adapter; the pinned checkpoint remains immutable.
        replay_checkpoint = dict(
            arrays=previous["arrays"],
            metadata=dict(
                previous["metadata"], external_concentration=external_concentration
            ),
        )
        solid = (
            replay_segment(
                case, water, replay_checkpoint, material, sediment_config, rock_floor
            )
            if len(water["arrays"]["trace_time_seconds"]) > 1
            else None
        )
        water_path = directory / f"segment-{index:04d}-water.npz"
        solid_path = directory / f"segment-{index:04d}-solid.npz"
        save_bundle(water_path, water, validator=_validated_solver_result)
        if solid is not None:
            save_bundle(solid_path, solid, validator=_validated_solver_result)
        next_state, seconds = _next_state(water, solid, previous)
        checkpoint = _checkpoint(
            next_state,
            seconds,
            index + 1,
            basis["identity_sha256"],
            previous["identity_sha256"],
        )
        checkpoint_path = directory / f"checkpoint-{index+1:04d}.npz"
        save_bundle(checkpoint_path, checkpoint, validator=_validate_checkpoint)
        complete = (
            solid is not None
            and water["metadata"]["status"] == solid["metadata"]["status"] == "complete"
        )
        manifest["segments"].append(
            dict(
                index=index,
                water=_pin(water_path, water),
                solid=_pin(solid_path, solid) if solid is not None else None,
                checkpoint=_pin(checkpoint_path, checkpoint),
                water_status=water["metadata"]["status"],
                solid_status=(
                    solid["metadata"]["status"] if solid is not None else "not_run"
                ),
                water_failure_reason=water["metadata"]["failure_reason"],
                solid_failure_reason=(
                    solid["metadata"]["failure_reason"]
                    if solid is not None
                    else "no committed hydraulic intervals"
                ),
                elapsed_seconds=time.perf_counter() - started,
            )
        )
        previous = checkpoint
        manifest["status"] = "running" if complete else "failed_prefix"
        _write_json(manifest_path, manifest)
        del water, solid, replay_checkpoint
        if not complete:
            break
    if manifest["status"] == "running":
        manifest["status"] = "complete"
    manifest["last_time_seconds"] = float(previous["arrays"]["time_seconds"][0])
    _write_json(manifest_path, manifest)
    return manifest


def _assert_equal(actual, expected, label, atol=1e-10):
    if np.asarray(actual).shape != np.asarray(expected).shape or not np.allclose(
        actual, expected, rtol=0.0, atol=atol
    ):
        raise ValueError("resolution series mismatch: " + label)


def audit_series(path, sample_times=(300.0, 600.0, 900.0)):
    path = Path(path)
    directory = path.parent
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["schema"] != SCHEMA:
        raise ValueError("invalid resolution series schema")
    interruption = manifest.get("storage_interruption")
    if interruption is not None:
        original_path = Path(interruption["original_manifest_path"])
        if file_sha256(original_path) != interruption["original_manifest_sha256"]:
            raise ValueError("storage interruption original manifest changed")
        original = json.loads(original_path.read_text(encoding="utf-8"))
        if (
            original["status"] != "running"
            or original["segment_endpoints_seconds"]
            != manifest["segment_endpoints_seconds"]
            or len(original["segments"]) != len(manifest["segments"])
            or original["source_manifest"] != manifest["source_manifest"]
        ):
            raise ValueError("storage interruption committed prefix changed")
        for field in ("basis", "initial_checkpoint"):
            if (
                original[field]["sha256"] != manifest[field]["sha256"]
                or original[field]["identity_sha256"]
                != manifest[field]["identity_sha256"]
            ):
                raise ValueError("storage interruption basis changed")
        for old, new in zip(original["segments"], manifest["segments"]):
            if old["water_status"] != "complete" or old["solid_status"] != "complete":
                raise ValueError("storage interruption contains physical failure")
            for field in ("water", "solid", "checkpoint"):
                if (
                    old[field]["sha256"] != new[field]["sha256"]
                    or old[field]["identity_sha256"] != new[field]["identity_sha256"]
                    or (original_path.parent / old[field]["path"]).resolve()
                    != (directory / new[field]["path"]).resolve()
                ):
                    raise ValueError("storage interruption product changed")
    continuation = manifest.get("continuation")
    if continuation is not None:
        parent_path = directory / continuation["parent_manifest_path"]
        if file_sha256(parent_path) != continuation["parent_manifest_sha256"]:
            raise ValueError("continued series parent manifest changed")
        parent = json.loads(parent_path.read_text(encoding="utf-8"))
        prefix_count = continuation["complete_prefix_segments"]
        if type(prefix_count) is not int or not 1 <= prefix_count <= min(
            len(parent["segments"]), len(manifest["segments"])
        ):
            raise ValueError("continued series prefix count exceeds pinned segments")
        if (
            prefix_count < 1
            or continuation["prefix_algorithm"]
            not in ("pinned-parent-product-versions", "bounded-frozen-water-exner-v1")
            or continuation["suffix_algorithm"] != "bounded-frozen-water-exner-v2"
        ):
            raise ValueError("invalid explicit time-policy transition")
        if (
            parent["source_manifest"] != manifest["source_manifest"]
            or parent["basis"]["identity_sha256"]
            != manifest["basis"]["identity_sha256"]
        ):
            raise ValueError("continued series parent basis changed")
        if (
            continuation["transition_time_seconds"]
            != manifest["segment_endpoints_seconds"][prefix_count]
            or parent["segment_endpoints_seconds"][: prefix_count + 1]
            != manifest["segment_endpoints_seconds"][: prefix_count + 1]
        ):
            raise ValueError("continued series prefix schedule changed")
        for old, new in zip(
            parent["segments"][:prefix_count], manifest["segments"][:prefix_count]
        ):
            if old["water_status"] != "complete" or old["solid_status"] != "complete":
                raise ValueError("continued incomplete parent segment")
            for field in ("water", "solid", "checkpoint"):
                if (
                    old[field]["sha256"] != new[field]["sha256"]
                    or old[field]["identity_sha256"] != new[field]["identity_sha256"]
                    or (parent_path.parent / old[field]["path"]).resolve()
                    != (directory / new[field]["path"]).resolve()
                ):
                    raise ValueError("continued prefix product changed")
    basis = load_bundle(
        directory / manifest["basis"]["path"],
        expected_sha256=manifest["basis"]["sha256"],
        validator=_validate_basis,
    )
    if basis["identity_sha256"] != manifest["basis"]["identity_sha256"]:
        raise ValueError("basis pin changed")
    native, forcing = _native(basis)
    m = basis["metadata"]
    material = MaterialParameters(**m["material"])
    case = refine_channel("series", native, forcing, basis["arrays"]["counts"])
    inputs = m["material_inputs"]
    initial = _initial_state(case, material, inputs)
    previous = _load_checkpoint(directory, manifest["initial_checkpoint"])
    if previous["metadata"] != dict(
        schema=CHECKPOINT_SCHEMA,
        index=0,
        basis_identity_sha256=basis["identity_sha256"],
        parent_checkpoint_identity_sha256=None,
    ):
        raise ValueError("initial checkpoint parent changed")
    for field in CHECKPOINT_FIELDS:
        _assert_equal(previous["arrays"][field], initial[field], "initial " + field)
    _assert_equal(
        previous["arrays"]["time_seconds"], [forcing.time_seconds[0]], "initial time"
    )
    endpoints = np.asarray(manifest["segment_endpoints_seconds"], np.float64)
    if (
        endpoints.ndim != 1
        or endpoints[0] != forcing.time_seconds[0]
        or endpoints[-1] != forcing.time_seconds[-1]
        or np.any(np.diff(endpoints) <= 0.0)
    ):
        raise ValueError("invalid segment endpoints")
    stocks = {field: {} for field in CHECKPOINT_FIELDS}
    water_times = [float(endpoints[0])]
    solid_times = [float(endpoints[0])]
    water_export = [0.0]
    solid_export = [0.0]
    maximum_water_residual = maximum_solid_residual = 0.0
    total_external_water = total_external_solid = 0.0
    max_product_bytes = 0
    water_steps = solid_steps = 0
    cumulative_rock = np.zeros(len(case.parent_index))
    rock_floor = (
        case.network.bed_elevation_m
        - inputs["initial_alluvium_depth_m"]
        - inputs["rock_reserve_depth_m"]
    )
    any_failure = False
    for index, pin in enumerate(manifest["segments"]):
        if index >= len(endpoints) - 1 or pin["index"] != index or any_failure:
            raise ValueError("reordered or continued failure series")
        water = load_channel_product(
            directory / pin["water"]["path"],
            expected_sha256=pin["water"]["sha256"],
            expected_identity=pin["water"]["identity_sha256"],
        )
        if pin["solid"] is None:
            a = water["arrays"]
            if (
                len(a["trace_time_seconds"]) != 1
                or water["metadata"]["status"] != "failed_prefix"
                or pin["solid_status"] != "not_run"
                or pin["solid_failure_reason"] != "no committed hydraulic intervals"
            ):
                raise ValueError("missing sediment without zero-interval water failure")
            if (
                water["metadata"]["config"] != m["channel_config"]
                or water["metadata"]["network_source_identity_sha256"]
                != case.network.source_identity_sha256
                or water["metadata"]["forcing_source_identity_sha256"]
                != case.forcing.source_identity_sha256
            ):
                raise ValueError("zero-interval source/config changed")
            for field in NETWORK_FIELDS:
                if not np.array_equal(
                    a["network_" + field], getattr(case.network, field)
                ):
                    raise ValueError("zero-interval geometry changed")
            sf = slice_forcing(
                case.forcing, float(endpoints[index]), float(endpoints[index + 1])
            )
            _assert_equal(
                a["forcing_time_seconds"], sf.time_seconds, "zero-interval forcing time"
            )
            _assert_equal(
                a["forcing_local_q_m3_s"],
                sf.local_q_m3_s,
                "zero-interval forcing source",
            )
            _assert_equal(
                a["trace_volume_m3"][0],
                previous["arrays"]["water_volume_m3"],
                "zero-interval water checkpoint",
            )
            checkpoint = _load_checkpoint(directory, pin["checkpoint"])
            if checkpoint["metadata"] != dict(
                schema=CHECKPOINT_SCHEMA,
                index=index + 1,
                basis_identity_sha256=basis["identity_sha256"],
                parent_checkpoint_identity_sha256=previous["identity_sha256"],
            ):
                raise ValueError("zero-interval checkpoint parent changed")
            for field in CHECKPOINT_FIELDS:
                _assert_equal(
                    checkpoint["arrays"][field],
                    previous["arrays"][field],
                    "zero-interval checkpoint " + field,
                )
            _assert_equal(
                checkpoint["arrays"]["time_seconds"],
                previous["arrays"]["time_seconds"],
                "zero-interval checkpoint time",
            )
            if (
                pin["water_status"] != water["metadata"]["status"]
                or pin["water_failure_reason"] != water["metadata"]["failure_reason"]
            ):
                raise ValueError("zero-interval failure record changed")
            max_product_bytes = max(
                max_product_bytes, sum(v.nbytes for v in a.values())
            )
            any_failure = True
            previous = checkpoint
            del water, a
            continue
        solid = load_sediment(
            directory / pin["solid"]["path"], expected_sha256=pin["solid"]["sha256"]
        )
        if solid["identity_sha256"] != pin["solid"]["identity_sha256"]:
            raise ValueError("solid pin changed")
        a, b = water["arrays"], solid["arrays"]
        if (
            continuation is not None
            and index >= continuation["complete_prefix_segments"]
        ):
            if solid["metadata"]["algorithm"] != continuation[
                "suffix_algorithm"
            ] or water["metadata"]["algorithm"] != continuation.get(
                "suffix_water_algorithm", "manning-rectangular-explicit-v1"
            ):
                raise ValueError("continued series time-policy version changed")
        if (
            water["metadata"]["config"] != m["channel_config"]
            or solid["metadata"]["config"] != m["sediment_config"]
            or solid["metadata"]["material"] != m["material"]
        ):
            raise ValueError("segment material/config changed")
        if (
            water["metadata"]["network_source_identity_sha256"]
            != case.network.source_identity_sha256
            or water["metadata"]["forcing_source_identity_sha256"]
            != case.forcing.source_identity_sha256
        ):
            raise ValueError("segment source identity changed")
        for field in NETWORK_FIELDS:
            if not np.array_equal(a["network_" + field], getattr(case.network, field)):
                raise ValueError("segment geometry changed: " + field)
        segment_forcing = slice_forcing(
            case.forcing, float(endpoints[index]), float(endpoints[index + 1])
        )
        _assert_equal(
            a["forcing_time_seconds"],
            segment_forcing.time_seconds,
            "segment forcing time",
        )
        _assert_equal(
            a["forcing_local_q_m3_s"],
            segment_forcing.local_q_m3_s,
            "segment forcing source",
        )
        state = previous["arrays"]
        _assert_equal(
            a["trace_volume_m3"][0], state["water_volume_m3"], "water checkpoint"
        )
        _assert_equal(
            b["trace_mobile_solid_m3"][0], state["mobile_solid_m3"], "mobile checkpoint"
        )
        _assert_equal(
            b["trace_bed_alluvium_solid_m3"][0],
            state["loose_solid_m3"],
            "loose checkpoint",
        )
        _assert_equal(
            b["domain_bed_elevation_m"], state["bed_elevation_m"], "bed checkpoint"
        )
        _assert_equal(
            b["domain_initial_alluvium_bulk_m3"],
            state["loose_solid_m3"] / (1 - material.porosity),
            "alluvium checkpoint",
        )
        _assert_equal(b["domain_rock_floor_m"], rock_floor, "original rock floor")
        area = case.network.width_m * case.network.length_m
        _assert_equal(b["domain_bed_area_m2"], area, "material area")
        _assert_equal(b["domain_receiver"], case.network.receiver, "sediment graph")
        _assert_equal(b["domain_width_m"], case.network.width_m, "sediment width")
        _assert_equal(
            b["forcing_time_seconds"], a["trace_time_seconds"], "water replay times"
        )
        _assert_equal(
            b["forcing_water_volume_m3"],
            a["trace_volume_m3"][:-1],
            "water replay volume",
        )
        _assert_equal(
            b["forcing_water_depth_m"], a["trace_depth_m"][:-1], "water replay depth"
        )
        _assert_equal(
            b["forcing_water_outflow_m3_s"],
            a["trace_outflow_q_m3_s"],
            "water replay discharge",
        )
        _assert_equal(
            b["forcing_external_solid_m3_s"],
            a["trace_local_q_m3_s"] * inputs["external_solid_concentration_m3_per_m3"],
            "external solid source",
        )
        _assert_equal(
            b["forcing_friction_slope"],
            np.broadcast_to(case.network.bed_slope, b["forcing_friction_slope"].shape),
            "fixed friction slope",
        )
        if (
            solid["metadata"]["hydraulic_identity_sha256"] != water["identity_sha256"]
            or solid["metadata"]["geometry_identity_sha256"] != water["identity_sha256"]
        ):
            raise ValueError("segment replay parent changed")
        dt = np.diff(a["trace_time_seconds"])
        edges = case.network.receiver >= 0
        incoming = np.zeros_like(a["trace_outflow_q_m3_s"])
        np.add.at(
            incoming.T,
            case.network.receiver[edges],
            a["trace_outflow_q_m3_s"][:, edges].T,
        )
        wr = np.diff(a["trace_volume_m3"], axis=0) - dt[:, None] * (
            a["trace_local_q_m3_s"] + incoming - a["trace_outflow_q_m3_s"]
        )
        maximum_water_residual = max(
            maximum_water_residual, float(np.max(np.abs(wr), initial=0.0))
        )
        incoming_solid = np.zeros_like(b["step_outgoing_solid_m3"])
        np.add.at(
            incoming_solid.T,
            case.network.receiver[edges],
            b["step_outgoing_solid_m3"][:, edges].T,
        )
        _assert_equal(
            b["step_incoming_solid_m3"], incoming_solid, "shared solid interface"
        )
        solid_stock = (
            b["trace_mobile_solid_m3"]
            + b["trace_bed_alluvium_solid_m3"]
            - b["trace_rock_removed_m3"]
        )
        sr = (
            np.diff(solid_stock, axis=0)
            - incoming_solid
            - b["step_external_solid_m3"]
            + b["step_outgoing_solid_m3"]
        )
        maximum_solid_residual = max(
            maximum_solid_residual, float(np.max(np.abs(sr), initial=0.0))
        )
        if max(maximum_water_residual, maximum_solid_residual) > 1e-8:
            raise ValueError("independent segment budget failed")
        cumulative_rock = (
            state["cumulative_rock_removed_m3"] + b["trace_rock_removed_m3"][-1]
        )
        physical_bed = (
            initial["bed_elevation_m"]
            + (b["trace_bed_alluvium_solid_m3"][-1] - initial["loose_solid_m3"])
            / ((1 - material.porosity) * area)
            - cumulative_rock / area
        )
        _assert_equal(
            b["trace_bed_elevation_m"][-1],
            physical_bed,
            "original-bed cumulative rock/loose basis",
            atol=1e-8,
        )
        checkpoint = _load_checkpoint(directory, pin["checkpoint"])
        if checkpoint["metadata"] != dict(
            schema=CHECKPOINT_SCHEMA,
            index=index + 1,
            basis_identity_sha256=basis["identity_sha256"],
            parent_checkpoint_identity_sha256=previous["identity_sha256"],
        ):
            raise ValueError("checkpoint chain parent changed")
        expected, seconds = _next_state(water, solid, previous)
        for field in CHECKPOINT_FIELDS:
            _assert_equal(
                checkpoint["arrays"][field], expected[field], "next checkpoint " + field
            )
        _assert_equal(
            checkpoint["arrays"]["time_seconds"], [seconds], "next checkpoint time"
        )
        for name, bundle, field, clock in (
            ("water_volume_m3", a, "volume_m3", a["trace_time_seconds"]),
            ("mobile_solid_m3", b, "mobile_solid_m3", b["trace_time_seconds"]),
            ("loose_solid_m3", b, "bed_alluvium_solid_m3", b["trace_time_seconds"]),
            (
                "cumulative_rock_removed_m3",
                b,
                "rock_removed_m3",
                b["trace_time_seconds"],
            ),
            ("bed_elevation_m", b, "bed_elevation_m", b["trace_time_seconds"]),
        ):
            trajectory = bundle["trace_" + field]
            if name == "cumulative_rock_removed_m3":
                trajectory = trajectory + state[name]
            if name == "bed_elevation_m":
                trajectory = trajectory - initial[name]
            restricted = restrict_inventory(
                trajectory * (area if name == "bed_elevation_m" else 1.0),
                case.parent_index,
                len(native.receiver),
            )
            if name == "bed_elevation_m":
                restricted = restricted / (native.width_m * native.length_m)
            for sample in sample_times:
                if clock[0] <= sample <= min(clock[-1], seconds):
                    stocks[name][str(sample)] = [
                        float(np.interp(sample, clock, col)) for col in restricted.T
                    ]
        committed_dt = np.maximum(
            0.0,
            np.minimum(a["trace_time_seconds"][1:], seconds)
            - np.minimum(a["trace_time_seconds"][:-1], seconds),
        )
        total_external_water += float(
            np.sum(a["trace_local_q_m3_s"] * committed_dt[:, None])
        )
        total_external_solid += float(b["step_external_solid_m3"].sum())
        water_clock = np.unique(
            np.r_[
                a["trace_time_seconds"][
                    (a["trace_time_seconds"] > a["trace_time_seconds"][0])
                    & (a["trace_time_seconds"] <= seconds)
                ],
                seconds,
            ]
        )
        water_clock = water_clock[water_clock > a["trace_time_seconds"][0]]
        full_water_export = np.r_[
            0.0, np.cumsum(a["trace_boundary_outflow_volume_m3"].sum(axis=1))
        ]
        local_water_export = np.interp(
            water_clock, a["trace_time_seconds"], full_water_export
        )
        local_solid_export = np.cumsum(b["step_exported_solid_m3"].sum(axis=1))
        water_times.extend(water_clock.tolist())
        solid_times.extend(b["trace_time_seconds"][1:].tolist())
        water_export.extend((water_export[-1] + local_water_export).tolist())
        solid_export.extend((solid_export[-1] + local_solid_export).tolist())
        water_steps += len(dt)
        solid_steps += len(b["step_dt_seconds"])
        max_product_bytes = max(
            max_product_bytes,
            sum(v.nbytes for v in a.values()),
            sum(v.nbytes for v in b.values()),
        )
        failed = (
            water["metadata"]["status"] != "complete"
            or solid["metadata"]["status"] != "complete"
        )
        if (
            pin["water_status"] != water["metadata"]["status"]
            or pin["solid_status"] != solid["metadata"]["status"]
            or pin["water_failure_reason"] != water["metadata"]["failure_reason"]
            or pin["solid_failure_reason"] != solid["metadata"]["failure_reason"]
        ):
            raise ValueError("segment completion record changed")
        any_failure |= failed
        previous = checkpoint
        del water, solid, a, b, incoming, incoming_solid, trajectory, restricted
    seconds = float(previous["arrays"]["time_seconds"][0])
    complete = (
        not any_failure
        and len(manifest["segments"]) == len(endpoints) - 1
        and seconds == forcing.time_seconds[-1]
    )
    if (
        manifest["status"] != ("complete" if complete else "failed_prefix")
        or manifest["last_time_seconds"] != seconds
    ):
        raise ValueError("series completion claim changed")
    if np.any(np.diff(water_times) <= 0.0) or np.any(np.diff(solid_times) <= 0.0):
        raise ValueError("duplicate/reordered series frames")
    final = previous["arrays"]
    water_residual = (
        initial["water_volume_m3"].sum()
        + total_external_water
        - water_export[-1]
        - final["water_volume_m3"].sum()
    )
    solid_residual = (
        initial["mobile_solid_m3"].sum()
        + initial["loose_solid_m3"].sum()
        + total_external_solid
        + final["cumulative_rock_removed_m3"].sum()
        - solid_export[-1]
        - final["mobile_solid_m3"].sum()
        - final["loose_solid_m3"].sum()
    )
    if max(abs(water_residual), abs(solid_residual)) > 1e-8:
        raise ValueError("independent cumulative series budget failed")
    return dict(
        status=manifest["status"],
        last_time_seconds=seconds,
        stocks=stocks,
        export_m3=water_export[-1],
        solid_export_m3=solid_export[-1],
        half_export_seconds=float(
            np.interp(water_export[-1] / 2.0, water_export, water_times)
        ),
        half_solid_export_seconds=float(
            np.interp(solid_export[-1] / 2.0, solid_export, solid_times)
        ),
        water_budget_residual_m3=float(water_residual),
        solid_budget_residual_m3=float(solid_residual),
        maximum_node_water_residual_m3=maximum_water_residual,
        maximum_node_solid_residual_m3=maximum_solid_residual,
        max_product_bytes=max_product_bytes,
        nodes=len(case.parent_index),
        water_steps=water_steps,
        solid_steps=solid_steps,
        basis_identity_sha256=basis["identity_sha256"],
        source_manifest=manifest["source_manifest"],
    )
