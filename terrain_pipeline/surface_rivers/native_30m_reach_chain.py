from __future__ import annotations

import hashlib
from typing import Any, Dict, Mapping, Tuple
import numpy as np
from terrain_pipeline.common_infra import TerrainGrid, GRID_MAX_CELLS as MAX_CELLS
from terrain_pipeline.channel_geometry import GeometryConfig
from terrain_pipeline.channel_geometry import build_monotone_union
from terrain_pipeline.surface_rivers.metric_morphology_coupling import _sample_nodes
from terrain_pipeline.channel_geometry import receiver_distances
from terrain_pipeline.artifacts.contracts import array_hash, digest


def _is_hex64(s: Any) -> bool:
    if not isinstance(s, str) or len(s) != 64:
        return False
    for ch in s:
        if ch not in "0123456789abcdef":
            return False
    return True


def _check_section(section: Mapping[str, Any]) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    if not isinstance(section, Mapping):
        raise ValueError("section_must_be_mapping")
    arrays = section.get("arrays")
    if not isinstance(arrays, Mapping):
        raise ValueError("section_arrays_must_be_mapping")
    for key in ("node_cell_ids", "node_xz_m", "receiver", "width_m", "normal_depth_m", "source_slope_per_m"):
        if key not in arrays:
            raise ValueError(f"section_arrays_missing:{key}")
    ncid = arrays["node_cell_ids"]
    nxz = arrays["node_xz_m"]
    rec = arrays["receiver"]
    if not isinstance(ncid, np.ndarray) or ncid.dtype != np.int64 or ncid.ndim != 1:
        raise ValueError("node_cell_ids_must_be_int64_vector")
    if not isinstance(nxz, np.ndarray) or nxz.dtype != np.float64 or nxz.ndim != 2 or nxz.shape[1] != 2:
        raise ValueError("node_xz_m_must_be_Nx2_float64")
    if not isinstance(rec, np.ndarray) or rec.dtype != np.int64 or rec.ndim != 1:
        raise ValueError("receiver_must_be_int64_vector")
    N = ncid.shape[0]
    if not (2 <= N <= 128):
        raise ValueError("node_count_out_of_range")
    if nxz.shape[0] != N or rec.shape[0] != N:
        raise ValueError("section_array_length_mismatch")
    for key in ("width_m", "normal_depth_m", "source_slope_per_m"):
        v = arrays[key]
        if not isinstance(v, np.ndarray) or v.dtype != np.float64 or v.ndim != 1 or v.shape[0] != N:
            raise ValueError(f"section_array_bad:{key}")
    if np.any(ncid < 0):
        raise ValueError("node_cell_ids_negative")
    meta = section.get("metadata") or {}
    if not isinstance(meta, Mapping):
        raise ValueError("section_metadata_must_be_mapping")
    return ncid, nxz, dict(meta)


def build_reach_geometry(elevation_m: np.ndarray, resolved_mask: np.ndarray,
                         section: Mapping[str, Any], *, origin_native_xz: Tuple[int, int],
                         source_identity_sha256: str, world_seed: int = 20261020) -> Dict[str, Any]:
    if not isinstance(elevation_m, np.ndarray) or elevation_m.dtype != np.float64 or elevation_m.ndim != 2:
        raise ValueError("elevation_m_must_be_2d_float64")
    if not isinstance(resolved_mask, np.ndarray) or resolved_mask.dtype != np.bool_ or resolved_mask.shape != elevation_m.shape:
        raise ValueError("resolved_mask_must_be_bool_equal_shape")
    if not _is_hex64(source_identity_sha256):
        raise ValueError("source_identity_sha256_must_be_lower_hex64")
    if isinstance(world_seed, bool) or not isinstance(world_seed, int) or world_seed < 0:
        raise ValueError("world_seed_must_be_nonnegative_int")
    if (not isinstance(origin_native_xz, (tuple, list)) or len(origin_native_xz) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) for v in origin_native_xz)):
        raise ValueError("origin_native_xz_must_be_two_ints")
    ox, oz = int(origin_native_xz[0]), int(origin_native_xz[1])
    ncid, nxz, smeta = _check_section(section)
    expected_receiver = np.r_[np.arange(1, ncid.size), -1].astype(np.int64)
    if not np.array_equal(section['arrays']['receiver'], expected_receiver):
        raise ValueError('section_not_a_path')
    expected_nxz = np.column_stack((
        (ox + ncid % elevation_m.shape[1]) * 30.,
        (oz + ncid // elevation_m.shape[1]) * 30.,
    ))
    if not np.array_equal(nxz, expected_nxz):
        raise ValueError('section_coordinates_mismatch')
    if "origin_native_xz" in smeta:
        so = smeta["origin_native_xz"]
        if (not isinstance(so, (tuple, list)) or len(so) != 2
                or int(so[0]) != ox or int(so[1]) != oz):
            raise ValueError("section_origin_mismatch")
    H, W = elevation_m.shape
    rows = ncid // W
    cols = ncid % W
    if np.any(rows >= H) or np.any(cols >= W):
        raise ValueError("node_cell_ids_out_of_grid")
    r_lo = int(rows.min()) - 12
    r_hi = int(rows.max()) + 13
    c_lo = int(cols.min()) - 12
    c_hi = int(cols.max()) + 13
    r0 = max(0, r_lo)
    c0 = max(0, c_lo)
    r1 = min(H, r_hi)
    c1 = min(W, c_hi)
    if r1 <= r0 or c1 <= c0:
        raise ValueError("crop_empty")
    crop = resolved_mask[r0:r1, c0:c1]
    if crop.size > MAX_CELLS:
        raise ValueError("crop_exceeds_max_cells")
    if not bool(crop.all()):
        raise ValueError("geometry_support_unknown")
    crop_elev = np.ascontiguousarray(elevation_m[r0:r1, c0:c1])
    source_sha = hashlib.sha256(crop_elev.tobytes()).hexdigest()
    local_rows = rows - r0
    local_cols = cols - c0
    crop_w = c1 - c0
    local_ids = (local_rows * crop_w + local_cols).astype(np.int64)
    terrain = TerrainGrid(
        elevation_m=crop_elev,
        valid_mask=np.ascontiguousarray(crop, dtype=bool),
        x0_m=float((ox + c0) * 30), z0_m=float((oz + r0) * 30),
        dx_m=30.0, dz_m=30.0, source_kind="generated_terrain",
        source_id="native30m", source_sha256=source_sha,
        generation_seed=int(world_seed), condition_summary="native30m_reach_chain",
    )
    section_arrays = section["arrays"]
    id_digest = digest({
        "source_identity_sha256": source_identity_sha256,
        "section_arrays": {k: array_hash(np.asarray(v)) for k, v in section_arrays.items()},
        "origin_native_xz": [ox, oz],
    })
    owner_grid = np.ones(crop_elev.shape, dtype=np.int64)
    corridor_mask = np.ones(crop_elev.shape, dtype=np.bool_)
    lake_mask = np.zeros(crop_elev.shape, dtype=np.bool_)
    geometry = build_monotone_union(
        terrain, local_ids,
        section_arrays["receiver"].astype(np.int64, copy=False),
        section_arrays["width_m"].astype(np.float64, copy=False),
        section_arrays["normal_depth_m"].astype(np.float64, copy=False),
        owner_grid=owner_grid, corridor_mask=corridor_mask, lake_mask=lake_mask,
        source_plan_identity_sha256=id_digest,
        config=GeometryConfig(fine_spacing_m=15.0, width_resolution=2.0, max_cut_m=4.0, max_vertices=262144, smoothing_iterations=0),
    )
    garr = geometry["arrays"]
    node_xz = np.asarray(garr["node_xz_m"], dtype=np.float64)
    recv = np.asarray(garr["receiver"], dtype=np.int64)
    bed = _sample_nodes(geometry, garr["bed_elevation_m"])
    bed = np.asarray(bed, dtype=np.float64)
    N = bed.shape[0]
    distance = np.asarray(receiver_distances(node_xz, recv), dtype=np.float64)
    if distance.shape[0] != N:
        raise ValueError("receiver_distance_length_mismatch")
    lengths = np.zeros(N, dtype=np.float64)
    slopes = np.zeros(N, dtype=np.float64)
    order = list(range(N - 1))
    for i in order:
        j = int(recv[i])
        if j < 0 or j >= N:
            raise ValueError("receiver_index_out_of_range")
        d = float(distance[i])
        if not np.isfinite(d) or d <= 0.0:
            raise ValueError("invalid_receiver_distance")
        drop = float(bed[i] - bed[j])
        if not (drop > 0.0):
            raise ValueError("bed_not_strictly_monotone_downstream")
        s = drop / d
        slopes[i] = s
        lengths[i] += 0.5 * d
        lengths[j] += 0.5 * d
    terminal = -1
    term_drop = None
    for idx in range(N):
        if int(recv[idx]) == -1:
            if terminal != -1:
                raise ValueError("multiple_terminals")
            terminal = idx
    if terminal == -1:
        raise ValueError("no_terminal_receiver")
    if N >= 2:
        prev = terminal - 1 if terminal > 0 else terminal + 1
        slopes[terminal] = slopes[prev]
    else:
        slopes[terminal] = 0.0
    return {
        "geometry": geometry, "node_bed_m": bed, "node_distance_m": distance,
        "node_length_m": lengths, "node_slope_per_m": slopes,
        "crop_rc": [int(r0), int(r1), int(c0), int(c1)],
        "metadata": {
            "source_identity_sha256": source_identity_sha256,
            "source_plan_identity_sha256": id_digest, "origin_native_xz": [ox, oz],
            "world_seed": int(world_seed), "generation_excavation_not_dynamic_erosion": True,
            "dynamic_PL_mesh_updated": False, "natural_outlet_certified": False,
        },
    }


from types import SimpleNamespace
from terrain_pipeline.channel_geometry import ChannelNetwork, ChannelForcing, ChannelConfig
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters, SedimentConfig
from terrain_pipeline.surface_rivers.world_channel_dynamics import couple_nodal_reach


def run_reach_dynamics(geometry_result: dict, event: dict, lateral_cell_counts,
                       *, coupled_intervals: int = 12, material: Any = None) -> dict:
    geom_keys = ("geometry", "node_bed_m", "node_distance_m", "node_length_m", "node_slope_per_m")
    for k in geom_keys:
        if k not in geometry_result:
            raise ValueError(f"geometry_result missing key {k!r}")
    geometry = geometry_result["geometry"]
    if not isinstance(geometry, dict) or "arrays" not in geometry:
        raise ValueError("geometry_result['geometry'] must be dict with 'arrays'")
    arrays = geometry["arrays"]
    receiver = np.asarray(arrays["receiver"], dtype=np.int64)
    width_m = np.asarray(arrays["width_m"], dtype=np.float64)
    geometry_sha = geometry.get("identity_sha256")
    if geometry_sha is None:
        raise ValueError("geometry identity_sha256 required")
    node_bed_m = np.asarray(geometry_result["node_bed_m"], dtype=np.float64)
    node_distance_m = np.asarray(geometry_result["node_distance_m"], dtype=np.float64)
    node_length_m = np.asarray(geometry_result["node_length_m"], dtype=np.float64)
    node_slope_per_m = np.asarray(geometry_result["node_slope_per_m"], dtype=np.float64)
    N = receiver.shape[0]
    if width_m.shape[0] != N or node_bed_m.shape[0] != N or node_distance_m.shape[0] != N:
        raise ValueError("geometry array length mismatch")
    if node_length_m.shape[0] != N or node_slope_per_m.shape[0] != N:
        raise ValueError("geometry node_length_m/node_slope_per_m length mismatch")
    if not np.all(np.isfinite(width_m)) or not np.all(width_m > 0.0):
        raise ValueError("width_m must be finite and > 0")
    if not np.all(np.isfinite(node_length_m)) or not np.all(node_length_m > 0.0):
        raise ValueError("node_length_m must be finite and > 0")
    if not np.all(np.isfinite(node_bed_m)):
        raise ValueError("node_bed_m must be finite")
    if not np.all(np.isfinite(node_slope_per_m)):
        raise ValueError("node_slope_per_m must be finite")
    if not np.all(node_slope_per_m > 0.0):
        raise ValueError("bed must be strictly downslope (node_slope_per_m > 0)")
    event_keys = ("local_q_m3_s", "time", "terminal", "event_identity_sha256", "design_q_m3_s")
    for k in event_keys:
        if k not in event:
            raise ValueError(f"event missing key {k!r}")
    event_source_sha = event.get("source", {}).get("source_identity_sha256")
    geometry_source_sha = geometry_result.get("metadata", {}).get("source_identity_sha256")
    if not event_source_sha or not geometry_source_sha or event_source_sha != geometry_source_sha:
        raise ValueError("event_geometry_source_mismatch")
    raw_local_q = event.get("local_q_m3_s")
    if not isinstance(raw_local_q, np.ndarray) or raw_local_q.dtype != np.float64 or raw_local_q.ndim != 2 or raw_local_q.shape[0] <= 0 or raw_local_q.shape[1] <= 0 or not np.all(np.isfinite(raw_local_q)) or np.any(raw_local_q < 0):
        raise ValueError("invalid_event_local_q")
    local_q = np.asarray(event["local_q_m3_s"], dtype=np.float64)
    if local_q.ndim != 2:
        raise ValueError("event.local_q_m3_s must be 2D [T, catchment_cells]")
    T = local_q.shape[0]
    n_cells = local_q.shape[1]
    terminal_cells = int(event["terminal"]["catchment_cells"])
    if terminal_cells != n_cells:
        raise ValueError("terminal.catchment_cells mismatch with local_q shape")
    time_block = event["time"]
    time_edges = np.asarray(time_block["time_edges_s"], dtype=np.float64)
    if time_edges.shape[0] != T + 1:
        raise ValueError("time_edges_s must have length T+1")
    design_q = float(event["design_q_m3_s"])
    event_sha = event["event_identity_sha256"]
    counts = np.asarray(lateral_cell_counts)
    if counts.ndim != 1:
        raise ValueError("lateral_cell_counts must be 1D")
    if counts.shape[0] != N:
        raise ValueError("lateral_cell_counts length must equal number of nodes")
    if counts.dtype.kind not in ("i", "u"):
        raise ValueError("lateral_cell_counts must be integer dtype")
    if np.any(counts <= 0):
        raise ValueError("lateral_cell_counts must be > 0 for every node")
    total = int(counts.sum())
    if total != terminal_cells or total <= 0:
        raise ValueError("sum(lateral_cell_counts) must equal terminal.catchment_cells and > 0")
    if isinstance(coupled_intervals, bool) or not isinstance(coupled_intervals, int):
        raise ValueError("coupled_intervals must be int (not bool)")
    if coupled_intervals < 1 or coupled_intervals > 12:
        raise ValueError("coupled_intervals must be in [1, 12]")
    if coupled_intervals > T:
        raise ValueError("coupled_intervals must be <= T")
    absmax = float(np.max(np.abs(local_q))) if local_q.size else 0.0
    tol = 1e-14 * max(1.0, absmax)
    spread = np.max(local_q, axis=1) - np.min(local_q, axis=1)
    if np.any(spread > tol):
        raise ValueError("nonuniform_catchment_requires_explicit_node_attribution")
    sim_local_q = local_q[:coupled_intervals, 0:1] * counts[None, :].astype(np.float64)
    lhs = sim_local_q.sum(axis=1)
    rhs = local_q[:coupled_intervals].sum(axis=1)
    cons_tol = 1e-12 * np.maximum(1.0, np.abs(rhs))
    if np.any(np.abs(lhs - rhs) > cons_tol):
        raise ValueError("local forcing conservation check failed pre-transmit")
    sim_time_edges = time_edges[: coupled_intervals + 1]
    terminal_kind = np.where(receiver >= 0, "interior", "open_outflow")
    area = width_m * node_length_m
    network = ChannelNetwork(
        receiver=receiver, length_m=node_length_m, width_m=width_m,
        bed_elevation_m=node_bed_m, bed_slope=node_slope_per_m,
        roughness=np.full(N, 0.035, dtype=np.float64),
        max_depth_m=np.full(N, 3.0, dtype=np.float64), terminal_kind=terminal_kind,
        source_identity_sha256=geometry_sha, section_source="design_q_only_geometry_uncalibrated",
        roughness_source="explicit_uncalibrated_0p035", receiver_distance_m=node_distance_m,
    )
    forcing = ChannelForcing(time_seconds=sim_time_edges, local_q_m3_s=sim_local_q,
                             source_identity_sha256=geometry_sha)
    rock_floor = node_bed_m - 1.0
    initial_alluvium_bulk = area * 0.02
    initial_water = np.zeros(N, dtype=np.float64)
    initial_mobile_solid = np.zeros(N, dtype=np.float64)
    if material is None:
        mat = MaterialParameters(
            sediment_erodibility_m_s_pa=1e-10, rock_erodibility_m_s_pa=1e-12,
            transport_coefficient=1e-5, settling_velocity_m_s=1e-4,
            provenance="explicit uncalibrated",
        )
    else:
        if not isinstance(material, MaterialParameters):
            raise TypeError("material must be a MaterialParameters instance")
        mat = material
    channel_config = ChannelConfig(max_dt_seconds=30.0)
    sediment_config = SedimentConfig(max_dt_seconds=30.0, max_bed_change_m=0.01, max_steps=200000)
    core_config = SimpleNamespace(max_nodes=N, max_intervals=12,
                                max_cumulative_bed_change_m=0.1, max_depth_change_m=0.1)
    result = couple_nodal_reach(
        geometry, network, forcing, mat,
        initial_water_volume_m3=initial_water, initial_mobile_solid_m3=initial_mobile_solid,
        initial_alluvium_bulk_m3=initial_alluvium_bulk, rock_floor_m=rock_floor,
        config=core_config, channel_config=channel_config, sediment_config=sediment_config,
    )
    metadata = {
        "forcing_event_identity_sha256": event_sha,
        "forcing_time_edges_s": time_edges.tolist(), "simulation_time_edges_s": sim_time_edges.tolist(),
        "simulation_mode": "storm_transient_local_runoff",
        "computational_outflow_not_natural_outlet": True,
        "initial_material_uncalibrated": True, "geometry_size_design_q_m3_s": design_q,
        "dynamic_PL_mesh_updated": False,
    }
    return {
        "dynamics": result, "network": network, "forcing": forcing,
        "initial_alluvium_bulk_m3": initial_alluvium_bulk,
        "rock_floor_m": rock_floor, "lateral_cell_counts": counts.copy(), "metadata": metadata,
    }
