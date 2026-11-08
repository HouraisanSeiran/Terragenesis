"""Native-grid material and residual-water proposals for uncommitted cutoffs."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.common_infra import TerrainGrid
from .metric_cutoff import CutoffConfig, find_cutoff_candidate
from terrain_pipeline.lake import LakeStorage as LakeStorage
from .metric_morphology_events import MorphologyEvent, event_from_record

SCHEMA = "terragenesis-cutoff-material-candidate-v1"
REVALIDATION = ("topology", "geometry", "hydraulics", "sediment", "outlet")


@dataclass(frozen=True)
class CutoffMaterialConfig:
    corridor_half_width_m: float = 15.
    shortcut_cut_depth_m: float = .1
    old_channel_fill_depth_m: float = .02
    porosity: float = .35

    def __post_init__(self):
        for name in ("corridor_half_width_m", "shortcut_cut_depth_m", "old_channel_fill_depth_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0.:
                raise ValueError(name + " must be finite nonnegative")
        if self.corridor_half_width_m <= 0. or isinstance(self.porosity, bool) or not math.isfinite(self.porosity) or not 0. <= self.porosity < 1.:
            raise ValueError("positive corridor and porosity in [0,1) required")


def _corridor(terrain, points, half_width):
    rows, cols = np.indices(terrain.elevation_m.shape)
    xz = np.stack((terrain.x0_m + cols * terrain.dx_m, terrain.z0_m + rows * terrain.dz_m), axis=-1)
    nearest = np.full(rows.shape, np.inf)
    for start, end in zip(points, points[1:]):
        delta = end - start
        fraction = np.clip(np.sum((xz - start) * delta, axis=-1) / float(delta @ delta), 0., 1.)
        nearest = np.minimum(nearest, np.linalg.norm(xz - start - fraction[..., None] * delta, axis=-1))
    return (nearest <= half_width + 1e-9) & terrain.valid_mask


def _build(terrain, centerline, edge_ids, old_water_depth_m, old_mobile_solid_m3,
           alluvium_bulk_depth_m, rock_floor_m, cutoff_config, material_config):
    shape = terrain.elevation_m.shape
    if (not isinstance(centerline, np.ndarray) or centerline.dtype != np.float64
            or centerline.ndim != 2 or centerline.shape[1] != 2 or len(centerline) < 5
            or not np.isfinite(centerline).all() or np.any(np.linalg.norm(np.diff(centerline, axis=0), axis=1) <= 0.)):
        raise ValueError("finite distinct float64 cutoff centerline required")
    inputs = (old_water_depth_m, old_mobile_solid_m3, alluvium_bulk_depth_m, rock_floor_m)
    for value in inputs:
        if not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.shape != shape or not np.isfinite(value).all():
            raise ValueError("finite float64 native inventory grids required")
    if any(np.any(value < 0.) for value in inputs[:3]):
        raise ValueError("negative cutoff inventory")
    if np.any(rock_floor_m > terrain.elevation_m - alluvium_bulk_depth_m + 1e-10):
        raise ValueError("alluvium penetrates geological rock floor")
    graph_id = identity({"centerline_xz_m": centerline}, {"edge_ids": list(edge_ids), "terrain_identity_sha256": terrain.identity_sha256,
                                                        "status": "caller_supplied_centerline_graph_not_certified_routing"})
    old = _corridor(terrain, centerline, material_config.corridor_half_width_m)
    if np.any(((old_water_depth_m != 0.) | (old_mobile_solid_m3 != 0.)) & ~old):
        raise ValueError("old water/mobile inventory outside declared old channel")
    geometry_id = identity({"old_channel_mask": old, "terrain_elevation_m": terrain.elevation_m,
                            "alluvium_bulk_depth_m": alluvium_bulk_depth_m, "rock_floor_m": rock_floor_m},
                           {"graph_identity_sha256": graph_id, "material_config": asdict(material_config)})
    result = find_cutoff_candidate(terrain, centerline, edge_ids, graph_id, geometry_id,
                                  0., 0., cutoff_config)
    arrays = {"terrain_elevation_m": terrain.elevation_m, "terrain_valid_mask": terrain.valid_mask,
              "centerline_xz_m": centerline, "old_channel_mask": old,
              "initial_water_depth_m": old_water_depth_m, "initial_mobile_solid_m3": old_mobile_solid_m3,
              "initial_alluvium_bulk_depth_m": alluvium_bulk_depth_m, "rock_floor_m": rock_floor_m}
    meta = {"schema": SCHEMA, "terrain_metadata": {name: getattr(terrain, name) for name in terrain.__dataclass_fields__ if name not in ("elevation_m", "valid_mask")},
            "terrain_identity_sha256": terrain.identity_sha256, "parent_graph_identity_sha256": graph_id,
            "parent_geometry_identity_sha256": geometry_id, "edge_ids": list(edge_ids),
            "cutoff_config": asdict(cutoff_config), "material_config": asdict(material_config),
            "status": result["status"], "failure_reason": result.get("reason"), "event_record": None,
            "revalidation_required": list(REVALIDATION), "capabilities": {"topology_mutation": False, "hydrodynamics": False,
                "dynamic_inventory_migration": False, "natural_outlet": False, "publishable": False},
            "inventory_provenance": "explicit native-cell stock scenario; not a solved ChannelState migration",
            "geometry_provenance": "explicit native-cell corridor, depth incision and old-channel fill proposal; longitudinal hydraulics unvalidated"}
    if result["status"] == "candidate":
        shortcut = _corridor(terrain, result["shortcut_xz_m"], material_config.corridor_half_width_m)
        residual = _corridor(terrain, result["loop_xz_m"], material_config.corridor_half_width_m) & ~shortcut
        if not np.any(shortcut) or not np.any(residual):
            meta.update(status="rejected", failure_reason="no_disjoint_shortcut_and_residual_native_support")
        else:
            area, solid_fraction = terrain.cell_area_m2, 1. - material_config.porosity
            cut = np.where(shortcut, np.minimum(material_config.shortcut_cut_depth_m,
                           np.maximum(terrain.elevation_m - rock_floor_m, 0.)), 0.)
            loose_cut_bulk = np.minimum(cut, alluvium_bulk_depth_m) * area
            rock_cut = cut * area - loose_cut_bulk
            cut_solid = loose_cut_bulk * solid_fraction + rock_cut
            fill_requested = residual * material_config.old_channel_fill_depth_m * area
            requested_solid = float(fill_requested.sum()) * solid_fraction
            excavated = float(cut_solid.sum())
            fill_scale = min(1., excavated / requested_solid) if requested_solid else 1.
            fill_bulk = fill_requested * fill_scale
            fill_solid = fill_bulk * solid_fraction
            unresolved_excavation = excavated - float(fill_solid.sum())
            after_bed = terrain.elevation_m - cut + fill_bulk / area
            # Preserve per-cell water volume on both proposed surviving and residual
            # supports; never silently lose water as the proposed bed rises.
            water_volume = old_water_depth_m * area
            residual_water = np.where(residual, water_volume, 0.)
            surviving_water = water_volume - residual_water
            residual_mobile = np.where(residual, old_mobile_solid_m3, 0.)
            surviving_mobile = old_mobile_solid_m3 - residual_mobile
            ids = np.flatnonzero(residual).astype(np.int64)
            lake = LakeStorage(ids, after_bed.ravel()[ids], np.full(len(ids), area), int(ids[np.argmin(after_bed.ravel()[ids])]),
                float(np.max(after_bed.ravel()[ids]) + 10. + residual_water.sum() / area), terrain.identity_sha256,
                "disjoint residual old-channel native cells; candidate level pool, no port coupling")
            stage = lake.stage_at_volume(float(residual_water.sum()))
            arrays.update(shortcut_mask=shortcut, residual_mask=residual, shortcut_xz_m=result["shortcut_xz_m"],
                loop_xz_m=result["loop_xz_m"], cut_depth_m=cut, cut_alluvium_bulk_m3=loose_cut_bulk,
                cut_rock_m3=rock_cut, cut_solid_m3=cut_solid, fill_bulk_m3=fill_bulk,
                fill_solid_m3=fill_solid, after_bed_m=after_bed,
                after_alluvium_solid_m3=(alluvium_bulk_depth_m * area - loose_cut_bulk) * solid_fraction + fill_solid,
                residual_water_m3=residual_water,
                surviving_water_m3=surviving_water, residual_mobile_solid_m3=residual_mobile,
                surviving_mobile_solid_m3=surviving_mobile, residual_lake_cell_ids=ids,
                residual_lake_hypsometry_stage_m=np.array([lake.min_stage_m, stage, lake.max_stage_m]),
                residual_lake_hypsometry_volume_m3=np.array([0., lake.volume_at_stage(stage), lake.capacity_m3]))
            ledger = {"deposited_solid_m3": float(fill_solid.sum()), "exported_solid_m3": 0.,
                      "unresolved_solid_m3": unresolved_excavation, "cut_rock_m3": float(rock_cut.sum()),
                      "fill_m3": float(fill_bulk.sum()), "porous_deposit_m3": float(fill_bulk.sum())}
            event = MorphologyEvent(result["event"].event_id, "cutoff", graph_id, geometry_id,
                result["event"].affected_edges, result["event"].added_edges, result["event"].retired_edges,
                0., excavated, ledger, {**result["event"].to_record()["parameters"],
                    "topology_status": "candidate_not_written", "stock_proposal_identity_sha256": identity(
                        {"water_depth_m": old_water_depth_m, "mobile_solid_m3": old_mobile_solid_m3},
                        {"terrain_identity_sha256": terrain.identity_sha256}),
                    "residual_water_m3": float(residual_water.sum()), "surviving_water_m3": float(surviving_water.sum()),
                    "residual_mobile_solid_m3": float(residual_mobile.sum()),
                    "unresolved_dynamic_water_m3": float(water_volume.sum()),
                    "unresolved_dynamic_mobile_solid_m3": float(old_mobile_solid_m3.sum()),
                    "residual_level_pool_stage_m": stage,
                    "residual_connectivity_status": "native_volume_support_only; wet connectivity and oxbow ports unvalidated",
                    "unfunded_fill_bulk_m3": float(fill_requested.sum() - fill_bulk.sum())}, REVALIDATION)
            meta["event_record"] = event.to_record()
            meta["material_ledger"] = ledger
    arrays = {name: readonly(np.ascontiguousarray(value)) for name, value in arrays.items()}
    bundle = {"arrays": arrays, "metadata": meta, "identity_sha256": identity(arrays, meta)}
    return bundle


def build_cutoff_material_candidate(terrain, centerline, edge_ids, old_water_depth_m,
                                    old_mobile_solid_m3, alluvium_bulk_depth_m, rock_floor_m,
                                    cutoff_config=None, material_config=None):
    return _build(terrain, centerline, edge_ids, old_water_depth_m, old_mobile_solid_m3,
                  alluvium_bulk_depth_m, rock_floor_m, cutoff_config or CutoffConfig(),
                  material_config or CutoffMaterialConfig())


def validate_cutoff_material_candidate(bundle):
    a, m = bundle["arrays"], bundle["metadata"]
    if bundle["identity_sha256"] != identity(a, m) or m.get("schema") != SCHEMA:
        raise ValueError("cutoff material identity/schema mismatch")
    terrain = TerrainGrid(a["terrain_elevation_m"], a["terrain_valid_mask"], **m["terrain_metadata"])
    rebuilt = _build(terrain, a["centerline_xz_m"], tuple(m["edge_ids"]), a["initial_water_depth_m"],
        a["initial_mobile_solid_m3"], a["initial_alluvium_bulk_depth_m"], a["rock_floor_m"],
        CutoffConfig(**m["cutoff_config"]), CutoffMaterialConfig(**m["material_config"]))
    if rebuilt["identity_sha256"] != bundle["identity_sha256"]:
        raise ValueError("cutoff material/native stock proposal not reproducible")
    if m["status"] == "candidate":
        event_from_record(m["event_record"])
        if np.any(a["shortcut_mask"] & a["residual_mask"]):
            raise ValueError("cutoff supports overlap")
        expected = a["initial_water_depth_m"] * terrain.cell_area_m2
        if not np.allclose(a["residual_water_m3"] + a["surviving_water_m3"], expected, rtol=0., atol=1e-10):
            raise ValueError("cutoff residual/surviving water budget mismatch")
        if not np.allclose(a["residual_mobile_solid_m3"] + a["surviving_mobile_solid_m3"], a["initial_mobile_solid_m3"], rtol=0., atol=1e-10):
            raise ValueError("cutoff mobile stock budget mismatch")
        if not math.isclose(float(a["cut_solid_m3"].sum()), float(a["fill_solid_m3"].sum()) + m["material_ledger"]["unresolved_solid_m3"], rel_tol=0., abs_tol=1e-8):
            raise ValueError("cutoff excavation/fill solid budget mismatch")
    return True


def save_cutoff_material_candidate(path, bundle):
    save_bundle(path, bundle, validator=validate_cutoff_material_candidate)


def load_cutoff_material_candidate(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256, validator=validate_cutoff_material_candidate)
