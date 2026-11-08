"""Cold-auditable finite TD runoff/channel/lake evidence; no new solver."""

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, save_bundle
from terrain_pipeline.runoff import RUNOFF_ARRAY_KEYS as ARRAY_KEYS
from terrain_pipeline.runoff import validate_rainfall_runoff_result as validate_rainfall_runoff_result
from terrain_pipeline.common_infra import BoundaryGrid, RainfallForcing, TerrainGrid
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from .metric_coupled_product import sample_coupled_output, validate_coupled_product
from .metric_morphology_coupling import MAX_BYTES, _pack, _unpack

SCHEMA = "terragenesis-finite-water-cycle-evidence-v1"
THRESHOLDS = {"scaled_mass_residual": 1e-8, "step_final_storage_relative": .01}


def forcing_identity(channel, lake, rainfall_identity, boundary_kind):
    return identity({"channel_local_q_m3_s": channel, "lake_local_q_m3_s": lake},
                    {"rainfall_identity_sha256": rainfall_identity, "external_boundary_kind": boundary_kind,
                     "semantics": "local-native-release-once;unknown-retains-unresolved-inventory"})


def validate_water_cycle(bundle):
    a, m = bundle["arrays"], bundle["metadata"]
    names = ("inputs", "native", "coupled", "dense", "sparse", "hourly")
    if (bundle["identity_sha256"] != identity(a, m) or m.get("schema") != SCHEMA
            or set(a) != {name + "__payload" for name in names}
            or set(m) != {"schema", "boundary_kind", "thresholds", *names}
            or m["boundary_kind"] not in ("closed", "unknown", "one_way") or m["thresholds"] != THRESHOLDS):
        raise ValueError("invalid finite water-cycle evidence contract")
    pieces = {name: _unpack(a, m, name) for name in names}
    for p in pieces.values():
        if p["identity_sha256"] != identity(p["arrays"], p["metadata"]):
            raise ValueError("water-cycle parent identity mismatch")
    ia, im = pieces["inputs"]["arrays"], pieces["inputs"]["metadata"]
    terrain = TerrainGrid(ia["terrain_height_m"], ia["valid_mask"], **im["terrain_metadata"])
    raw = im["raw_source_metadata"]
    generation = raw["provenance"]["generation_metadata"]
    if (terrain.vertical_datum != raw["vertical_datum"] or terrain.generation_seed != int(generation["seed"])
            or terrain.model_version != generation["model"]["revision"]
            or terrain.condition_summary != generation["conditioning_identity"]
            or terrain.source_sha256 != im["source_file_sha256"]):
        raise ValueError("water-cycle raw TD generation provenance mismatch")
    kinds = np.full(terrain.elevation_m.shape, "interior", "U24")
    kinds[[0, -1], :] = "closed_wall"
    kinds[:, [0, -1]] = "closed_wall"
    kinds[~terrain.valid_mask] = "unknown_boundary"
    boundary = BoundaryGrid(kinds, np.zeros(kinds.shape, bool), "explicit finite closed TD diagnostic domain", im["source_identity_sha256"])
    graph = route_diagnostic(terrain, boundary)
    if not np.array_equal(graph.receiver, ia["receiver"]) or graph.identity_sha256 != im["graph_identity_sha256"] or terrain.identity_sha256 != im["terrain_identity_sha256"]:
        raise ValueError("water-cycle terrain/routing source mismatch")
    owner = np.full(graph.receiver.shape, -1, np.int64)
    for cell in np.flatnonzero(terrain.valid_mask):
        path = [int(cell)]
        while graph.receiver[path[-1]] >= 0:
            path.append(int(graph.receiver[path[-1]]))
        if path[-1] == im["lake_cell"]:
            owner[cell] = 0 if im["channel_cell"] in path else 1
    if not np.array_equal(owner, ia["contribution_owner"]) or graph.receiver[im["channel_cell"]] != im["lake_cell"]:
        raise ValueError("water-cycle native contribution/port connection mismatch")
    na, nm = pieces["native"]["arrays"], pieces["native"]["metadata"]
    native = {key: na[key] for key in ARRAY_KEYS} | {"metadata": nm["native_metadata"]}
    validate_rainfall_runoff_result(native)
    if (not np.array_equal(ia["time_seconds"], na["time_seconds"])
            or not np.all(np.diff(na["time_seconds"]) == nm["native_metadata"]["dt_s"])
            or nm["native_metadata"]["source_id"] != nm["rainfall_source_id"]):
        raise ValueError("water-cycle native physical time/source mismatch")
    selected = np.flatnonzero(owner >= 0)
    rt = TerrainGrid(terrain.elevation_m, (owner >= 0).reshape(terrain.valid_mask.shape), **im["terrain_metadata"])
    if (not np.array_equal(na["selected_cell_ids"], selected) or not np.array_equal(na["contribution_owner"], owner[selected])
            or nm["terrain_identity_sha256"] != rt.identity_sha256 or nm["source_terrain_identity_sha256"] != terrain.identity_sha256
            or not np.array_equal(na["area_m2"], np.full(len(selected), terrain.cell_area_m2))):
        raise ValueError("water-cycle runoff source/support mismatch")
    rain = np.zeros((len(na["time_seconds"]) - 1, *terrain.valid_mask.shape))
    rain.reshape(len(rain), -1)[:, selected] = na["rain_mm_h"]
    rf = RainfallForcing(na["time_seconds"], rain, nm["rainfall_source_id"], nm["rainfall_source_sha256"])
    expected_source = im["source_identity_sha256"]
    if "noise_rainfall_provenance" in nm:
        from terrain_pipeline.climate_forcing import NoiseClimateParameters, grid_rainfall
        provenance = nm["noise_rainfall_provenance"]
        generated, expected_provenance = grid_rainfall(
            provenance["seed"], origin_xz_m=(terrain.x0_m, terrain.z0_m),
            shape_zx=terrain.valid_mask.shape, spacing_m=terrain.dx_m,
            time_edges_s=na["time_seconds"], parameters=NoiseClimateParameters(**provenance["parameters"]),
            spatial_subsamples=provenance["spatial_subsamples"])
        expected_rain = generated.rain_mm_h.copy()
        expected_rain[:, owner.reshape(terrain.valid_mask.shape) < 0] = 0.
        if provenance != expected_provenance or not np.array_equal(rain, expected_rain) or rf.source_id != "synthetic_noise_climate":
            raise ValueError("water-cycle noise rainfall provenance/replay mismatch")
        expected_source = expected_provenance["source_identity_sha256"]
    if rf.identity_sha256 != nm["rainfall_forcing_identity_sha256"] or rf.source_sha256 != expected_source:
        raise ValueError("water-cycle rainfall identity mismatch")
    cq = na["local_q_m3_s"][:, owner[selected] == 0].sum(axis=1)[:, None]
    lq = na["local_q_m3_s"][:, owner[selected] == 1].sum(axis=1)[:, None]
    coupled = pieces["coupled"]
    validate_coupled_product(coupled)
    ca, cm = coupled["arrays"], coupled["metadata"]
    if (not np.array_equal(ca["forcing_channel_local_q_m3_s"], cq)
            or not np.array_equal(ca["forcing_lake_local_q_m3_s"], lq)
            or not np.array_equal(ca["forcing_time_seconds"], na["time_seconds"])
            or cm["forcing_source_identity_sha256"] != forcing_identity(cq, lq, rf.identity_sha256, m["boundary_kind"])
            or cm["network"]["source_identity_sha256"] != terrain.identity_sha256
            or not np.array_equal(ca["lake_cell_ids"], [im["lake_cell"]])
            or not np.array_equal(ca["lake_bed_elevation_m"], [terrain.elevation_m.ravel()[im["lake_cell"]]])
            or not np.array_equal(ca["lake_cell_area_m2"], [terrain.cell_area_m2])):
        raise ValueError("water-cycle runoff hydraulic parent or native lake mismatch")
    if bool(cm["outlets"]) != (m["boundary_kind"] == "one_way"):
        raise ValueError("water-cycle external boundary classification mismatch")
    if m["boundary_kind"] == "one_way" and (len(cm["outlets"]) != 1 or cm["outlets"][0]["lake_index"] != 0):
        raise ValueError("water-cycle requires exactly one declared lake exterior port")
    width = terrain.elevation_m.shape[1]
    distance = float(np.linalg.norm(np.subtract(divmod(im["channel_cell"], width), divmod(im["lake_cell"], width))) * terrain.dx_m)
    bed = terrain.elevation_m.ravel()[im["channel_cell"]]
    slope = (bed - terrain.elevation_m.ravel()[im["lake_cell"]]) / distance
    if (not np.array_equal(ca["channel_to_lake"], [0]) or not np.array_equal(ca["network_receiver"], [-1])
            or not np.array_equal(ca["network_bed_elevation_m"], [bed])
            or not np.array_equal(ca["network_length_m"], [distance])
            or not np.array_equal(ca["network_bed_slope"], [slope])
            or len(cm["lakes"]) != 1 or cm["lakes"][0]["source_identity_sha256"] != terrain.identity_sha256
            or len(ca["boundary_node_ids"]) != 0
            or any(o["receiver"] != -1 for o in cm["outlets"])):
        raise ValueError("water-cycle native geometry/port/exterior mismatch")
    dt = np.diff(ca["trace_time_seconds"])
    local = float((ca["trace_channel_local_q_m3_s"] * dt[:, None]).sum() + (ca["trace_lake_local_q_m3_s"] * dt[:, None]).sum())
    external = float(ca["trace_channel_boundary_volume_m3"].sum() + ca["trace_lake_external_volume_m3"].sum())
    change = float(ca["trace_channel_volume_m3"][-1].sum() + ca["trace_lake_volume_m3"][-1].sum()
                   - ca["trace_channel_volume_m3"][0].sum() - ca["trace_lake_volume_m3"][0].sum())
    end = ca["trace_time_seconds"][-1]
    overlap = np.maximum(np.minimum(na["time_seconds"][1:], end) - na["time_seconds"][:-1], 0.) / np.diff(na["time_seconds"])
    total = {key: float((na[key] * overlap[:, None]).sum()) for key in ("rain_volume_m3", "et_volume_m3", "storage_change_m3", "outflow_volume_m3")}
    tolerance = THRESHOLDS["scaled_mass_residual"] * max(1., local, external)
    if (abs(local - total["outflow_volume_m3"]) > tolerance or abs(local - external - change) > tolerance
            or abs(total["rain_volume_m3"] - total["et_volume_m3"] - total["storage_change_m3"] - external - change) > tolerance
            or m["boundary_kind"] != "one_way" and external != 0.):
        raise ValueError("water-cycle independent native/hydraulic mass budget mismatch")
    for name in ("dense", "sparse", "hourly"):
        saved = pieces[name]
        if cm["result"]["status"] == "complete":
            last = ca["trace_time_seconds"][-1]
            times = output_times(last, name)
            if not np.array_equal(saved["arrays"]["time_seconds"], times):
                raise ValueError("water-cycle declared output cadence mismatch")
        expected = sample_coupled_output(coupled, saved["arrays"]["time_seconds"])
        if saved["identity_sha256"] != expected["identity_sha256"]:
            raise ValueError("water-cycle saved frame differs from full trace")
    return True


def output_times(last, name):
    if name == "sparse":
        return np.array([0., last])
    return np.unique(np.r_[np.arange(0., last, 300. if name == "dense" else 3600.), last])


def make_water_cycle(inputs, native, coupled, frames, boundary_kind):
    arrays = {}
    metadata = {"schema": SCHEMA, "boundary_kind": boundary_kind, "thresholds": dict(THRESHOLDS)}
    for name, piece in {"inputs": inputs, "native": native, "coupled": coupled, **frames}.items():
        _pack(arrays, metadata, name, piece)
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_water_cycle(result)
    return result


def save_water_cycle(path, bundle):
    save_bundle(path, bundle, validator=validate_water_cycle)


def load_water_cycle(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256, validator=validate_water_cycle, max_bytes=6 * MAX_BYTES)
