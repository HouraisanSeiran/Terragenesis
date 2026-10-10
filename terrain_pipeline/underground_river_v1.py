"""Seeded bounded gallery deformation, not geological route discovery."""

from copy import deepcopy
from dataclasses import asdict, dataclass
from importlib.metadata import version
import math
import time

import numpy as np

from terrain_pipeline.hybrid_cave_geometry import (
    closed_rock_section, guard, manifold_from_record, mesh_record, ray_hits,
    save_manifold, seal, sweep_triangles, void_witnesses)

SCHEMA = "td-underground-river-preview-v1"
CAPABILITIES = {"hydraulic_solved": False, "full_network_verified": False,
                "natural_outlet_certified": False}


@dataclass(frozen=True)
class Parameters:
    seed: int = 17
    lateral_amplitude_m: float = 1.0
    width_scale: float = 1.05
    roof_variation_m: float = .2

    def __post_init__(self):
        if type(self.seed) is not int or not 0 <= self.seed <= 2**32 - 1:
            raise ValueError("seed must be an integer in [0, 4294967295]")
        for name, lower, upper in (("lateral_amplitude_m", 0., 3.),
                                   ("width_scale", .8, 1.2),
                                   ("roof_variation_m", 0., .5)):
            value = getattr(self, name)
            if type(value) not in (int, float):
                raise ValueError(name + " must be an int or float")
            if not lower <= value <= upper or not math.isfinite(value):
                raise ValueError(name + " outside bounded finite range")


def deform_charts(source_vdm, parameters):
    stations = deepcopy(source_vdm["stations"])
    phases = np.random.default_rng(parameters.seed).uniform(-math.pi, math.pi, 3)
    for ordinal, station in enumerate(stations):
        if ordinal in (0, len(stations) - 1):
            continue
        fraction = station["fraction"]
        envelope = math.sin(math.pi * fraction)**2
        transverse = np.asarray(station["transverse_unit_xz"], float)
        origin = np.asarray(station["origin_xyz_m"], float)
        baseline = np.asarray(station["derived_ring_xyz_m"], float)
        lateral = parameters.lateral_amplitude_m * envelope * math.sin(2 * math.pi * fraction + phases[0])
        shift = np.array([transverse[0] * lateral, 0., transverse[1] * lateral])
        derived = baseline + shift
        offsets = (baseline[:, [0, 2]] - origin[[0, 2]]) @ transverse
        scale = 1. + (parameters.width_scale - 1.) * envelope
        derived[:, [0, 2]] += np.outer(offsets * (scale - 1.), transverse)
        variation = parameters.roof_variation_m * envelope
        derived[-2:, 1] += variation * math.sin(4 * math.pi * fraction + phases[1])
        derived[-2, [0, 2]] += variation * math.sin(2 * math.pi * fraction + phases[2]) * transverse
        derived[-1, [0, 2]] -= variation * math.sin(2 * math.pi * fraction + phases[2]) * transverse
        station["origin_xyz_m"] = (origin + shift).tolist()
        reference = np.asarray(station["reference_ring_xyz_m"], float)
        displacement = derived - reference
        station["displacement_ring_xyz_m"] = displacement.tolist()
        station["derived_ring_xyz_m"] = (reference + displacement).tolist()
    for ordinal in (0, -1):
        if stations[ordinal] != source_vdm["stations"][ordinal]:
            raise ValueError("immutable portal station changed")
    rings = [np.asarray(station["derived_ring_xyz_m"]) for station in stations]
    if not all(np.isfinite(ring).all() for ring in rings):
        raise ValueError("nonfinite chart")
    bounds = [(np.vstack((first, second))[:, [0, 2]].min(axis=0),
               np.vstack((first, second))[:, [0, 2]].max(axis=0))
              for first, second in zip(rings, rings[1:])]
    for ordinal, (low, high) in enumerate(bounds):
        for other_low, other_high in bounds[ordinal + 2:]:
            if np.all(np.minimum(high, other_high) - np.maximum(low, other_low) > 1e-8):
                raise ValueError("nonadjacent sweep projection overlap not certified")
    return {"stations": stations, "triangles": sweep_triangles(stations)}


def build_preview(rock_record, source_vdm, sampler, source_pins, parameters=Parameters(), *, started=None):
    started = time.perf_counter() if started is None else started

    def budget_guard():
        guard()
        if time.perf_counter() - started > 60.:
            raise ValueError("60s generation budget exceeded")

    def bounded_sampler(point):
        budget_guard()
        return sampler(point)

    if version("manifold3d") != "3.5.4":
        raise ValueError("only manifold3d==3.5.4 authorized")
    import manifold3d
    budget_guard()
    origin = np.asarray(rock_record["local_origin_xyz_m"], float)
    if not np.array_equal(origin, source_vdm["stations"][0]["origin_xyz_m"]):
        raise ValueError("source sink and fixed rock origin differ")
    for station in source_vdm["stations"]:
        if not np.array_equal(np.asarray(station["reference_ring_xyz_m"]) +
                np.asarray(station["displacement_ring_xyz_m"]), station["derived_ring_xyz_m"]):
            raise ValueError("source VDM reference displacement mismatch")
    before = manifold_from_record(rock_record)
    vdm = deform_charts(source_vdm, parameters)
    stations = vdm["stations"]
    rings = np.asarray([station["derived_ring_xyz_m"] for station in stations])
    local = rings.reshape(-1, 3) - origin
    rock_vertices = np.asarray(rock_record["vertices_local_xyz_m"])
    if np.any(local[:, [0, 2]] <= rock_vertices[:, [0, 2]].min(axis=0)) or np.any(
            local[:, [0, 2]] >= rock_vertices[:, [0, 2]].max(axis=0)):
        raise ValueError("cutter leaves fixed rock crop")
    if local[:, 1].min() <= rock_vertices[:, 1].min():
        raise ValueError("cutter leaves fixed rock bottom")
    above_y = float(rock_vertices[:, 1].max() + origin[1] + 10.)
    closed_indices = []
    cover_witnesses = []
    for ordinal, (station, ring) in enumerate(zip(stations, rings)):
        containment = []
        for point in ring:
            source_witness = bounded_sampler(point[[0, 2]])
            hits = ray_hits(before, [point[0], above_y, point[2]], point, origin)
            cover = min((hit["position_xyz_m"][1] - point[1] for hit in hits), default=None)
            containment.append({"point_xyz_m": point.tolist(),
                "vertical_ray_start_xyz_m": [float(point[0]), above_y, float(point[2])],
                "rock_before_vertical_hits": hits, "actual_sampled_top_cover_m": cover,
                "source_bed_witness": source_witness})
        closed = closed_rock_section(containment)
        cover_witnesses.append({"station_id": station["station_id"], "fraction": station["fraction"],
            "actual_ring_containment": containment, "physical_closed_rock_section": closed})
        if .25 <= station["fraction"] <= .75 and not closed:
            raise ValueError("insufficient actual core rock cover:" + station["station_id"])
        if closed:
            closed_indices.append(ordinal)
    if not closed_indices or closed_indices != list(range(closed_indices[0], closed_indices[-1] + 1)):
        raise ValueError("covered core missing or not contiguous")
    cutter_record = mesh_record(local, vdm["triangles"], origin, "cutter")
    cutter = manifold_from_record(cutter_record)
    after, removed = before - cutter, before ^ cutter
    budget_guard()
    if any(solid.status() != manifold3d.Error.NoError or solid.is_empty() for solid in (after, removed)):
        raise ValueError("actual rock Boolean failed or empty")
    if len(cutter.decompose()) != 1 or len(removed.decompose()) != 1:
        raise ValueError("cutter or removed not connected")
    residual = before.volume() - after.volume() - removed.volume()
    if abs(residual) > max(1e-7, before.volume() * 1e-10):
        raise ValueError("material balance failed")
    path, segments, openings = void_witnesses(before, after, removed, vdm, origin, bounded_sampler)
    for segment in segments:
        budget_guard()
        segment["rock_before_hits"] = ray_hits(before, segment["from_xyz_m"], segment["to_xyz_m"], origin)
        segment["removed_hits"] = ray_hits(removed, segment["from_xyz_m"], segment["to_xyz_m"], origin)
    records = {"rock_before": rock_record, "cutter": cutter_record,
               "rock_after": save_manifold(after, origin, "rock_after"),
               "removed": save_manifold(removed, origin, "removed")}
    reference = np.asarray([station["reference_ring_xyz_m"] for station in stations]).reshape(-1, 3) - origin
    displacement = np.asarray([station["displacement_ring_xyz_m"] for station in stations]).reshape(-1, 3)
    derived = reference + displacement
    if not np.allclose(derived, local, atol=1e-10, rtol=0.):
        raise ValueError("VDM reference displacement mismatch")
    budget_guard()
    return seal({"schema": SCHEMA, "status": "geometry_checked", "origin_xyz_m": origin.tolist(),
        "parameters": asdict(parameters), "source_pins": source_pins, "capabilities": dict(CAPABILITIES),
        "scope": "seeded engineered gallery in fixed sampled mountain rock; generator checks only, no independent audit or complete portal certification",
        "meshes": {key: {name: record[name] for name in ("vertices_local_xyz_m", "triangles")}
                   for key, record in records.items()},
        "vdm": {"reference_local_xyz_m": reference.tolist(), "derived_local_xyz_m": derived.tolist(),
                "displacement_xyz_m": displacement.tolist(), "triangles": cutter_record["triangles"]},
        "stations": [{"station_id": station["station_id"],
            "origin_local_xyz_m": (np.asarray(station["origin_xyz_m"]) - origin).tolist(),
            "ring_local_xyz_m": (ring - origin).tolist()} for station, ring in zip(stations, rings)],
        "portals": [{"kind": kind, "position_local_xyz_m": (np.asarray(stations[ordinal]["origin_xyz_m"]) - origin).tolist()}
                    for kind, ordinal in (("sink", 0), ("spring", -1))],
        "metrics": {"length_m": math.fsum(math.dist(first["origin_xyz_m"], second["origin_xyz_m"])
                    for first, second in zip(stations, stations[1:])), "excavated_rock_m3": removed.volume(),
                    "material_residual_m3": residual, "closed_core_count": len(closed_indices)},
        "geometry_checks": {"air_path_local_xyz_m": (np.asarray(path) - origin).tolist(),
            "evidence_coordinates": "world XYZ metres for *_xyz_m; local only for *_local_xyz_m",
            "producer_check_scope": "new generator geometry checks, not independent audit or complete portal certification",
            "independent_audit_passed": False, "complete_portal_certified": False,
            "station_source_cover_witnesses": cover_witnesses,
            "air_path_xyz_m": path, "air_path_segments": segments,
            "portal_opening_witnesses": openings,
            "air_segment_count": len(segments), "terrain_opening_kinds": sorted(openings),
            "closed_core_station_indices": closed_indices, "removed_components": 1}, "water": None})
