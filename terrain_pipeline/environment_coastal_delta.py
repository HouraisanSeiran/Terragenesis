"""Same-mouth finite channel-tree deposition and bounded marine water/heat export.

Consumes already-debited regional boundary packets exactly once. Original saved
TD-derived bed is immutable; natural sediment is the sole source of bed change.
The declared staggered channel paths are reduced geometry, not excavated sediment.
"""

from dataclasses import asdict
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import (
    checked_archive,
    file_sha256,
    identity,
    load_bundle,
    readonly,
    save_bundle,
)
from terrain_pipeline.environment_processes import ocean_coast_transport_step as ocean_step
from terrain_pipeline.environment_regional_hydraulics import validate_packet
from terrain_pipeline.surface_rivers.metric_integrated_delta import (
    IntegratedDeltaConfig, build_channel_tree, integrated_solid_ledger, run_integrated_delta,
)


SCHEMA = "environment-coastal-delta-v1"


def prepare_coastal_delta(store):
    """Pin the existing finite coastal composition and ocean classification."""
    store = Path(store)
    registry = json.loads((store / "registry.json").read_text(encoding="utf-8"))
    if registry["world"]["layout"]["world_seed"] != 20261020 or len(registry["components"]) != 1:
        raise ValueError("single saved seed20261020 coastal component required")
    component = registry["components"][0]
    root = store / "versions" / component["version"]
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    claimed = manifest.pop("identity_sha256")
    if claimed != component["identity_sha256"] or identity({}, manifest) != claimed:
        raise ValueError("coastal source manifest identity mismatch")
    if manifest["world_identity"] != registry["world_identity"]:
        raise ValueError("coastal manifest/registry world identity mismatch")
    left, top, right, bottom = component["bounds"]
    shape = bottom - top, right - left
    if math.prod(shape) > 65536:
        raise ValueError("coastal reduced domain exceeds65536 cells")
    bed, ocean = np.empty(shape), np.zeros(shape, bool)
    covered = np.zeros(shape, bool)
    sources = []
    for tile in manifest["composition_tiles"]:
        path = root / tile["file"]
        data = checked_archive(path, expected_sha256=tile["sha256"])
        x, z = tile["origin_native_xz"]
        rows, cols = tile["shape_zx"]
        sl = np.s_[z - top:z - top + rows, x - left:x - left + cols]
        bed[sl], ocean[sl] = data["composed_elevation_m"], data["ocean_mask"]
        covered[sl] = data["valid_mask"]
        sources.append({"path": str(path.resolve()), "sha256": tile["sha256"]})
    if not covered.all() or not ocean.any() or not np.isfinite(bed).all() or np.any(bed[ocean] > 0.):
        raise ValueError("finite saved submerged coastal support required")
    network_path = root / manifest["network"]["file"]
    if file_sha256(network_path) != manifest["network"]["sha256"]:
        raise ValueError("actual coastal receiver source hash mismatch")
    with np.load(network_path, allow_pickle=False) as graph:
        receiver = graph["receiver"]
    metadata = {"schema": "environment-coastal-source-v1", "world_seed": 20261020,
                "source_world_identity": registry["world_identity"], "origin_native_xz": [left, top],
                "shape_zx": list(shape), "spacing_m": 30., "tiles": sources,
                "registry_sha256": file_sha256(store / "registry.json"),
                "manifest_sha256": file_sha256(root / "manifest.json"), "source_pages": registry["pages"],
                "network_sha256": manifest["network"]["sha256"]}
    arrays = {"bed_m": readonly(bed), "ocean_mask": readonly(ocean), "receiver": readonly(receiver)}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}


def _geometry(prepared, inlet):
    """Two staggered splits over unmodified saved terrain; no construction volume."""
    row, col = inlet
    shape = prepared["arrays"]["bed_m"].shape
    # All offsets progress seaward (west); unequal lengths avoid a radial fan.
    offsets = np.array([[0, 0], [-3, 1], [-6, 2], [-10, 3], [-14, 4], [-18, 6]])
    local = offsets + [col, row]
    branches = [np.array([local[2], [col - 19, row + 1], [col - 34, row + 2]]),
                np.array([local[5], [col - 34, row + 12], [col - 51, row + 18]]),
                np.array([local[5], [col - 28, row + 23], [col - 44, row + 35]])]
    points = np.vstack([local, *branches])
    if (np.any(points[:, 0] < 0) or np.any(points[:, 0] >= shape[1]) or
            np.any(points[:, 1] < 0) or np.any(points[:, 1] >= shape[0])):
        raise ValueError("same-mouth staggered paths leave actual coastal support")
    origin = np.array(prepared["metadata"]["origin_native_xz"]) * 30.
    trunk = origin + local * 30.
    branch_world = [origin + branch * 30. for branch in branches]
    geometry = build_channel_tree(prepared["arrays"]["bed_m"], origin, 30.,
        trunk[-1], trunk[0], trunk, branch_world, [30., 21., 15., 18.],
        ocean_mask=prepared["arrays"]["ocean_mask"], trunk_split_station=2,
        branch_split_station=5, eligible_band_m=90., protected_band_m=0.)
    for path in geometry.paths.values():
        cc, rr = np.rint((path.points_xz - origin) / 30.).astype(int).T
        if not prepared["arrays"]["ocean_mask"][rr[-1], cc[-1]] and path.outlets_to_sea:
            raise ValueError("terminal path must reach the actual saved ocean")
    return geometry


def run_coastal_delta(prepared, packets, *, river_temperature_c=12., ocean_temperature_c=18.,
                      current_speed_m_s=.01, zero_sediment_control=False):
    """Receive one mouth's already-debited packets and save quasi-steady results.

    Packets represent another control volume's exports. This operation does not
    mutate or add to any active environment/coastal_exchange inventory.
    """
    if prepared["identity_sha256"] != identity(prepared["arrays"], prepared["metadata"]):
        raise ValueError("prepared coastal source identity mismatch")
    if not isinstance(packets, (tuple, list)) or not 1 <= len(packets) <= 32:
        raise ValueError("one to32 finite coastal delivery intervals required")
    shape = prepared["arrays"]["bed_m"].shape
    ids, target = set(), None
    water, solid, seconds = [], [], []
    previous_end = None
    for packet in packets:
        validate_packet(packet)
        if packet["packet_id"] in ids:
            raise ValueError("duplicate coastal packet would consume water/solid twice")
        ids.add(packet["packet_id"])
        if packet["source_world_identity"] != prepared["metadata"]["source_world_identity"]:
            raise ValueError("coastal packet belongs to another source world")
        donor = packet["source_node"]
        if (type(donor) is not int or not 0 <= donor < math.prod(shape) or
                prepared["arrays"]["receiver"][donor] != packet["target_node"]):
            raise ValueError("packet is not an actual saved coastal receiver edge")
        if target is None:
            target = packet["target_node"]
        if packet["target_node"] != target:
            raise ValueError("one reduced delta consumes one actual mouth, not mixed mouth coordinates")
        dt = packet["time_end_s"] - packet["time_start_s"]
        if (not all(math.isfinite(packet[key]) for key in
                    ("time_start_s", "time_end_s", "water_m3", "solid_m3")) or dt <= 0 or
                packet["time_start_s"] < 0 or min(packet["water_m3"], packet["solid_m3"]) < 0 or
                (previous_end is not None and packet["time_start_s"] != previous_end)):
            raise ValueError("contiguous positive physical intervals and finite nonnegative packets required")
        previous_end = packet["time_end_s"]
        water.append(packet["water_m3"])
        solid.append(0. if zero_sediment_control else packet["solid_m3"])
        seconds.append(dt)
    if type(target) is not int or not 0 <= target < math.prod(shape):
        raise ValueError("target_node must use saved coastal component row-major native identity")
    inlet = divmod(target, shape[1])
    if not prepared["arrays"]["ocean_mask"][inlet]:
        raise ValueError("packet receiving node is not the actual saved ocean mouth")
    geometry = _geometry(prepared, inlet)
    config = IntegratedDeltaConfig()
    summary = run_integrated_delta(prepared["arrays"]["bed_m"], geometry, water, solid, seconds, config)
    ledger = integrated_solid_ledger(summary, np.asarray(solid))
    ledger["residual_solid_m3"] = (ledger["input_solid_m3"] - ledger["retained_solid_m3"] -
                                   ledger["exported_solid_m3"] - ledger["escrow_solid_m3"])
    ocean = prepared["arrays"]["ocean_mask"]
    initial_volume = np.where(ocean, -prepared["arrays"]["bed_m"] * 900., 0.)
    volume, temperature = initial_volume.copy(), np.full(shape, ocean_temperature_c)
    control_volume, control_temperature = volume.copy(), temperature.copy()
    water_out = heat_out = no_river_out = 0.
    branch_q = []
    terminal_water = []
    for record, dt in zip(summary["records"], seconds):
        q = np.array([record.q_branch0_m3_s, record.q_branch1_m3_s, record.q_branch2_m3_s])
        if not np.isclose(q.sum() * dt, record.water_input_m3, rtol=1e-7, atol=1e-7):
            raise ValueError("quasi-steady terminal water does not match inlet")
        branch_q.append([record.q_trunk0_m3_s, record.q_trunk1_m3_s, *q])
        terminal_water.append(q * dt)
        for name, amount in zip(("branch0", "branch1", "branch2"), q * dt):
            col, row = np.rint((geometry.sea_xz[name] - geometry.origin_xz) / 30.).astype(int)
            old = volume[row, col]
            volume[row, col] += amount
            temperature[row, col] = ((old * temperature[row, col] + amount * river_temperature_c) /
                                     max(volume[row, col], 1e-300))
        count = max(1, math.ceil(current_speed_m_s * dt / 30.))
        if count > 10000:
            raise ValueError("bounded ocean CFL budget exceeded")
        for _ in range(count):
            step = ocean_step(volume, temperature, ocean, wind_bearing=(-1, 0),
                              wind_speed_m_s=current_speed_m_s, dt_s=dt / count, spacing_m=30.)
            baseline = ocean_step(control_volume, control_temperature, ocean, wind_bearing=(-1, 0),
                                  wind_speed_m_s=current_speed_m_s, dt_s=dt / count, spacing_m=30.)
            volume, temperature = step["volume_m3"], step["temperature_c"]
            control_volume, control_temperature = baseline["volume_m3"], baseline["temperature_c"]
            water_out += step["ledger"]["boundary_outflow_m3"]
            heat_out += step["ledger"]["boundary_heat_outflow_m3_degc"]
            no_river_out += baseline["ledger"]["boundary_outflow_m3"]
    marine = {"river_water_input_m3": float(sum(water)), "river_heat_input_m3_degc": float(sum(water) * river_temperature_c),
              "ocean_boundary_water_export_m3": water_out, "ocean_boundary_heat_export_m3_degc": heat_out,
              "water_residual_m3": float(initial_volume.sum() + sum(water) - volume.sum() - water_out),
              "heat_residual_m3_degc": float((initial_volume * ocean_temperature_c).sum() +
                                           sum(water) * river_temperature_c - (volume * temperature).sum() - heat_out),
              "no_river_boundary_water_export_m3": no_river_out}
    arrays = {name: summary[name] for name in ("initial_bed_m", "final_bed_m", "height_delta_m",
               "stored_solid_m3", "deposited_solid_m3", "reentrained_solid_m3", "stage_m", "depth_m", "ocean_mask")}
    arrays.update(branch_q_m3_s=np.asarray(branch_q), terminal_water_m3=np.asarray(terminal_water),
                  terminal_export_solid_m3=summary["monthly_terminal_export_solid_m3"],
                  ocean_volume_m3=volume, ocean_temperature_c=temperature,
                  no_river_ocean_volume_m3=control_volume,
                  original_receiver=prepared["arrays"]["receiver"])
    arrays.update({"path_" + name: path.points_xz for name, path in geometry.paths.items()})
    metadata = {"schema": SCHEMA, "prepared_source": prepared["metadata"],
                "prepared_identity_sha256": prepared["identity_sha256"], "packets": packets,
                "target_node": target, "inlet_row_col": list(inlet), "solid_ledger": ledger,
                "marine_ledger": marine, "config": asdict(config),
                "zero_sediment_control": zero_sediment_control,
                "construction_budget": {"excavated_solid_m3": 0., "fill_solid_m3": 0.},
                "geometry_source": "declared staggered two-level asymmetric channel paths over unchanged saved bed",
                "control_volume": "regional already-debited export received by independent delta/marine successor; no reinjection",
                "limitations": ["quasi-steady tree, not full2D hydraulics or Bengal-scale maturity",
                                "ocean water/heat uses fixed wet support, not bed-displacement hydrodynamics",
                                "terminal sediment is explicit sea-side export, offshore plume not solved"],
                "river_temperature_c": river_temperature_c, "ocean_temperature_c": ocean_temperature_c,
                "temperature_source": "declared engineering boundary; regional hydraulic packets carry no heat stock",
                "current_speed_m_s": current_speed_m_s,
                "code_sha256": {name: file_sha256(path) for name, path in (
                    ("environment_coastal_delta.py", Path(__file__)),
                    ("metric_integrated_delta.py", Path(__file__).parent / "surface_rivers/metric_integrated_delta.py"),
                    ("environment_processes.py", Path(__file__).with_name("environment_processes.py")))}}
    result = {"arrays": {name: readonly(value) for name, value in arrays.items()}, "metadata": metadata,
              "identity_sha256": identity(arrays, metadata)}
    validate_coastal_delta(result)
    return result


def validate_coastal_delta(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata["schema"] != SCHEMA or result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("coastal delta identity mismatch")
    if any(not np.isfinite(value).all() for value in arrays.values()):
        raise ValueError("finite coastal results required")
    ledger = metadata["solid_ledger"]
    if abs(ledger["residual_solid_m3"]) > 1e-8 * max(ledger["input_solid_m3"], 1.):
        raise ValueError("coastal solid budget does not close")
    if not np.allclose(arrays["height_delta_m"], arrays["stored_solid_m3"] / (900. * .65), atol=1e-12):
        raise ValueError("coastal derived bed is not supported by finite sediment inventory")
    marine = metadata["marine_ledger"]
    if abs(marine["water_residual_m3"]) > 1e-5 or abs(marine["heat_residual_m3_degc"]) > 1e-3:
        raise ValueError("coastal marine water/heat budget does not close")
    return True


def continue_coastal_delta(saved_result, new_packets):
    """Replay bounded complete packet history from its sole original bed/sea state.

    Never use the previous derived bed as another initial sediment inventory.
    Repeated packet IDs are refused by the same single-consumption validation.
    """
    validate_coastal_delta(saved_result)
    metadata, arrays = saved_result["metadata"], saved_result["arrays"]
    if metadata["zero_sediment_control"]:
        raise ValueError("diagnostic zero-sediment control cannot continue as a physical receiver")
    prepared = {"arrays": {"bed_m": arrays["initial_bed_m"], "ocean_mask": arrays["ocean_mask"],
                           "receiver": arrays["original_receiver"]},
                "metadata": metadata["prepared_source"], "identity_sha256": metadata["prepared_identity_sha256"]}
    return run_coastal_delta(prepared, list(metadata["packets"]) + list(new_packets),
        river_temperature_c=metadata["river_temperature_c"], ocean_temperature_c=metadata["ocean_temperature_c"],
        current_speed_m_s=metadata["current_speed_m_s"])


def save_coastal_delta(path, result):
    save_bundle(path, result, validator=validate_coastal_delta)


def load_coastal_delta(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256, validator=validate_coastal_delta)
