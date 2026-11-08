"""Explicit serial complete coarse-edge preparation using canonical TD ownership."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.hydrology_planning import load_plan
from terrain_pipeline.hydrology_detail import (
    DetailBudget,
    derive_detail,
    required_td_nodes,
    save_detail,
)
from terrain_pipeline.td_source import CORE, QUERY_SIZE, CanonicalTDSource, _hydrology_td_digest as _digest
from terrain_pipeline.hydrology_detail_projection import (
    ALGORITHM,
    HALO,
    SUPPORT,
    ProjectionConfig,
    prepare_cached_projection,
    load_projection,
    save_projection,
    crop_projection,
    ProjectionError,
)
from terrain_pipeline.channel_geometry import frozen_window_profiles, split_frozen_window_component, derive_continuous_bed, audit_frozen_window_seams
from terrain_pipeline.hydrology_detail_ridge import transformed_coarse_plan
from terrain_pipeline.common_infra import file_sha256


def audit_source_tile(path, sha, generation, seed, tile):
    if file_sha256(path) != sha:
        raise ValueError("canonical source tile pin mismatch")
    with np.load(path,allow_pickle=False) as archive:
        metadata=json.loads(str(archive["metadata_json"].item()))
        height=archive["elevation_m"]
        climate=archive["climate"]
        if (metadata["identity"]!=generation["base_generation_identity"] or int(metadata["seed"])!=seed
                or metadata["native_origin"] != [tile[0]*CORE,tile[1]*CORE]
                or metadata["shape"] != [QUERY_SIZE,QUERY_SIZE]
                or metadata["artifact_kind"]!="terrain_diffusion_output"
                or height.shape!=(QUERY_SIZE,QUERY_SIZE) or climate.shape!=(5,QUERY_SIZE,QUERY_SIZE)
                or not np.isfinite(height).all() or not np.isfinite(climate).all()):
            raise ValueError("canonical source tile saved identity, grid or finite values differ")


def edge_request(plan, edge):
    receiver = np.asarray(plan["receiver"]).ravel()
    river = np.asarray(plan["river_mask"]).ravel()
    first, second = edge
    if not 0 <= first < len(receiver) or receiver[first] != second or not river[first]:
        raise ValueError("actual selected frozen river edge required")
    columns = np.asarray(plan["height_m"]).shape[1]
    points = (
        np.asarray(plan["origin_xz_m"])
        + np.array([[cell % columns, cell // columns] for cell in edge])
        * plan["spacing_m"]
    )
    # Full finite-width source support, including one native-cell margin.
    low = np.floor((points.min(axis=0) - 30) / 30).astype(int)
    high = np.ceil((points.max(axis=0) + 30) / 30).astype(int)
    owners = [
        [x, z]
        for z in range(low[1] // CORE, high[1] // CORE + 1)
        for x in range(low[0] // CORE, high[0] // CORE + 1)
    ]
    sources = sorted(
        {(x + dx, z + dz) for x, z in owners for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
    )
    length = float(np.linalg.norm(points[1] - points[0]))
    count = int(np.ceil(length / 500))
    fractions = np.linspace(0.0, 1.0, count + 1)
    return {
        "source_edge": list(edge),
        "points_xz_m": points.tolist(),
        "length_m": length,
        "native_origin_xz": low.tolist(),
        "shape": (high - low + 1)[::-1].tolist(),
        "owning_tiles": owners,
        "source_tiles": [list(tile) for tile in sources],
        "endpoint_ids": [f"{plan['identity_sha256']}:{node}" for node in edge],
        "piece_fraction_intervals": [
            [float(a), float(b)] for a, b in zip(fractions[:-1], fractions[1:])
        ],
    }


def freeze(plan_path, reports, output, *, bed_version="v5-continuous-center-floor"):
    plan = load_plan(plan_path)
    records = [json.loads(Path(path).read_text(encoding="utf-8")) for path in reports]
    if not records or any(
        record["plan_identity"] != plan["identity_sha256"]
        or not record["local_window_compatible"]
        for record in records
    ):
        raise ValueError("accepted current-plan window reports required")
    if (
        len({_digest(record["budget"]) for record in records}) != 1
        or len({record["fixed_lake_level_m"] for record in records}) != 1
    ):
        raise ValueError("same frozen budget and seasonal stage required")
    # Read source declaration from actual saved support, never a generated substitute.
    with np.load(
        records[0]["computational_support99_path"], allow_pickle=False
    ) as archive:
        metadata = json.loads(str(archive["metadata_json"].item()))
    raw_path = Path(records[0]["native97_detail_path"]).parent / (
        records[0]["window_kind"] + "-original-td.npz"
    )
    with np.load(raw_path, allow_pickle=False) as archive:
        original = json.loads(str(archive["metadata_json"].item()))
    generation = original
    anchors = dict(metadata.get("baseline_node_provenance", {}))
    for record in records:
        for parent in record["accepted_owning_core_provenance"]:
            saved = load_projection(parent["path"])
            if file_sha256(parent["path"]) != parent["archive_sha256"]:
                raise ValueError("accepted owning projection changed")
            for key, value in saved["metadata"]["baseline_node_provenance"].items():
                if (
                    key in anchors
                    and anchors[key]["elevation_m"] != value["elevation_m"]
                ):
                    raise ValueError("canonical TD anchor disagreement")
                anchors[key] = value
    requests = [
        edge_request(plan, record["declared_window"]["selection_edge_cell_ids"])
        for record in records
    ]
    for request in requests:
        if request["source_edge"] == [9223, 9222]:
            points = np.asarray(request["points_xz_m"])
            low = np.floor((points.min(axis=0) - 1080) / 30).astype(int)
            high = np.ceil((points.max(axis=0) + 1080) / 30).astype(int)
            request["macro_valley_support"] = {
                "native_origin_xz": low.tolist(),
                "shape": (high - low + 1)[::-1].tolist(),
                "padding_m": 1080,
                "derivation": "1000m transition +60m pinned interface +15m bank rounded to native grid",
                "maximum_dependency_radius_m": 1080,
                "budget": {
                    **records[0]["budget"],
                    **{
                        key: records[0]["budget"][key]
                        * np.prod(high - low + 1).item()
                        / 97**2
                        for key in (
                            "macro_absolute_volume_m3",
                            "total_absolute_volume_m3",
                        )
                    },
                },
            }
    for request in requests:
        rows, columns = request["shape"]
        request["budget"] = dict(records[0]["budget"])
        for key in ("macro_absolute_volume_m3", "total_absolute_volume_m3"):
            request["budget"][key] *= rows * columns / 97**2
        request["budget_semantics"] = (
            "pre-frozen finite rectangular support at frozen97 volume per area; no basin acceptance"
        )
    sources = {tuple(tile) for request in requests for tile in request["source_tiles"]}
    required_anchors = set()
    for request in requests:
        for tx, tz in request["owning_tiles"]:
            window = {
                "origin_xz_m": [(tx * CORE - HALO) * 30, (tz * CORE - HALO) * 30],
                "shape": [SUPPORT, SUPPORT],
                "spacing_m": 30,
            }
            required_anchors.update(required_td_nodes(plan, window))
    anchor_requests = []
    for rz, cx in sorted(required_anchors):
        world = np.asarray(plan["origin_xz_m"]) + np.array([cx, rz]) * plan["spacing_m"]
        native = world / 30
        floor = np.floor(native).astype(int)
        tiles = {
            (int((floor[0] + dx) // CORE), int((floor[1] + dz) // CORE))
            for dx in (0, 1)
            for dz in (0, 1)
        }
        sources.update(tiles)
        anchor_requests.append(
            {
                "key": f"{rz}:{cx}",
                "world_xz_m": world.tolist(),
                "native_floor_xz": floor.tolist(),
                "fraction_xz": (native - floor).tolist(),
            }
        )
    sources = sorted(sources)
    root = (
        Path(generation["canonical_cache_root"])
        / generation["identity"]
        / str(plan["seed"])
    )
    source_records = []
    for x, z in sources:
        path = root / f"tile-x{x}-z{z}.npz"
        pin = path.with_suffix(".sha256")
        ready = path.is_file() and pin.is_file()
        sha = pin.read_text().strip() if ready else None
        if ready and file_sha256(path) != sha:
            raise ValueError("canonical source tile pin mismatch")
        if ready:
            audit_source_tile(path,sha,generation,plan["seed"],[x,z])
        source_records.append(
            {
                "tile_xz": [x, z],
                "path": str(path),
                "sha256": sha,
                "status": "pinned_cached" if ready else "source_unprepared",
            }
        )
    receiver = np.asarray(plan["receiver"]).ravel()
    river = np.asarray(plan["river_mask"]).ravel()
    scheduled = {tuple(request["source_edge"]) for request in requests}
    all_edges = [
        [int(cell), int(receiver[cell])]
        for cell in np.flatnonzero(river & (receiver >= 0))
    ]
    declaration = {
        "schema": "hydrology-finite-full-edges-plan-v1",
        "plan_path": str(plan_path),
        "plan_sha256": file_sha256(plan_path),
        "plan_identity": plan["identity_sha256"],
        "generation_metadata": generation,
        "baseline_node_provenance": anchors,
        "anchor_requests": anchor_requests,
        "budget": records[0]["budget"],
        "fixed_lake_level_m": records[0]["fixed_lake_level_m"],
        "projection_algorithm": ALGORITHM,
        "bed_version": bed_version,
        "d8_detail_scope": "full rectangular support excluding exactly two pinned outer rows; all budget pixels retained",
        "macro_valley_algorithm": "sampled-macro-center-below-15m-banks-v1",
        "finite_mouth_projection": {
            "algorithm": "finite-complete-edge-world-boundary-projection-v2-fixed-slope-diagnostic",
            "fixed_boundary_slope_policy": "diagnostic_only",
            "max_nodes": max(np.prod(request["shape"]).item() for request in requests),
            "max_constraints": 2000000,
            "max_nonzeros": 8000000,
            "time_limit_s": 180.0,
            "boundary": "outer two native rows pinned to existing continuous world macro",
            "marine_continuation": "canonical nearest coastal owner; only ocean stencil and negative macro is sea",
        },
        "accepted_window_reports": [
            {"path": str(path), "sha256": file_sha256(path)} for path in reports
        ],
        "requests": requests,
        "source_tiles": source_records,
        "selected_graph_edge_count": len(all_edges),
        "unscheduled_selected_edges": [
            edge for edge in all_edges if tuple(edge) not in scheduled
        ],
        "wet_lake_edge_policy": "lake product owns wet support; complete-edge bed refuses wet lake support",
        "coverage_scope": "scheduled two complete edges only; remaining selected graph explicitly unscheduled",
        "source_query_shape": [QUERY_SIZE, QUERY_SIZE],
        "source_missing_count": sum(
            record["status"] == "source_unprepared" for record in source_records
        ),
        "global_hydrology_certified": False,
        "publishable": False,
    }
    declaration["identity"] = _digest(declaration)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "plan.json"
    if (
        path.exists()
        and json.loads(path.read_text())["identity"] != declaration["identity"]
    ):
        raise ValueError("immutable full-edge declaration differs; use a new output")
    if not path.exists():
        path.write_text(
            json.dumps(declaration, indent=2, allow_nan=False), encoding="utf-8"
        )
    return declaration


def execute(declaration, output, action):
    """Run one explicit phase, serially. Missing genuine inputs remain a refusal."""
    output = Path(output)
    plan = load_plan(declaration["plan_path"])
    if file_sha256(declaration["plan_path"]) != declaration["plan_sha256"]:
        raise ValueError("frozen coarse plan changed")
    generation = declaration["generation_metadata"]
    root = (
        Path(generation["canonical_cache_root"])
        / generation["identity"]
        / str(plan["seed"])
    )
    missing = [
        record
        for record in declaration["source_tiles"]
        if not Path(record["path"]).is_file()
        or not Path(record["path"]).with_suffix(".sha256").is_file()
    ]
    if action == "sources":
        from diffusion.physical_config import PhysicalGenerationConfig
        from terrain_pipeline.hydrology_detail_conditioning import (
            ResourcePhysicalTerrainDiffusionBackend,
        )

        backend = ResourcePhysicalTerrainDiffusionBackend(
            PhysicalGenerationConfig(), resource_tier="light"
        )
        source = CanonicalTDSource(backend, generation["canonical_cache_root"])
        if source.identity != generation["identity"]:
            source.close()
            raise ValueError("backend source identity differs from frozen original TD")
        try:
            for record in missing:
                source._tile(plan["seed"], *record["tile_xz"])
                time.sleep(5)
        finally:
            source.close()
        return {
            "status": "source_phase_completed",
            "generated_tile_count": len(missing),
        }
    if missing:
        return {
            "status": "source_unprepared",
            "missing_tiles": [record["tile_xz"] for record in missing],
            "global_hydrology_certified": False,
            "publishable": False,
        }
    current_sources = []
    for record in declaration["source_tiles"]:
        path = Path(record["path"])
        sha = path.with_suffix(".sha256").read_text().strip()
        if file_sha256(path) != sha or record["sha256"] not in (None, sha):
            raise ValueError("frozen canonical source tile pin mismatch")
        audit_source_tile(path,sha,generation,plan["seed"],record["tile_xz"])
        current_sources.append({**record, "sha256": sha, "status": "pinned_cached"})
    declaration = {**declaration, "source_tiles": current_sources}
    config = ProjectionConfig(
        macro_max_abs_m=declaration["budget"]["macro_max_abs_m"],
        macro_absolute_volume_m3=declaration["budget"]["macro_absolute_volume_m3"]
        * SUPPORT**2
        / 97**2,
    )
    anchors = dict(declaration["baseline_node_provenance"])
    for request in declaration["anchor_requests"]:
        if request["key"] in anchors:
            continue
        nx, nz = request["native_floor_xz"]
        values = np.empty((2, 2))
        for dz in (0, 1):
            for dx in (0, 1):
                px, pz = nx + dx, nz + dz
                path = root / f"tile-x{px // CORE}-z{pz // CORE}.npz"
                pin = path.with_suffix(".sha256").read_text().strip()
                if file_sha256(path) != pin:
                    raise ValueError("anchor canonical source pin mismatch")
                with np.load(path, allow_pickle=False) as archive:
                    values[dz, dx] = archive["elevation_m"][pz % CORE, px % CORE]
        fx, fz = request["fraction_xz"]
        value = float(
            (1 - fz) * ((1 - fx) * values[0, 0] + fx * values[0, 1])
            + fz * ((1 - fx) * values[1, 0] + fx * values[1, 1])
        )
        anchors[request["key"]] = {
            "elevation_m": value,
            "generation_identity": generation["identity"],
            "sampling": "bilinear fixed globally aligned native 2x2 TD nodes",
            "world_xz_m": request["world_xz_m"],
            "native_elevation_m": values.tolist(),
            "seed": plan["seed"],
            "source_tiles": [
                record
                for record in current_sources
                if record["tile_xz"]
                in [
                    [int((nx + dx) // CORE), int((nz + dz) // CORE)]
                    for dx in (0, 1)
                    for dz in (0, 1)
                ]
            ],
        }
    owners = sorted(
        {
            tuple(tile)
            for request in declaration["requests"]
            for tile in request["owning_tiles"]
        }
    )
    missing_anchors = set()
    for tx, tz in owners:
        window = {
            "origin_xz_m": [(tx * CORE - HALO) * 30, (tz * CORE - HALO) * 30],
            "shape": [SUPPORT, SUPPORT],
            "spacing_m": 30,
        }
        for rz, cx in required_td_nodes(plan, window):
            key = f"{rz}:{cx}"
            if key not in anchors:
                missing_anchors.add(key)
    if missing_anchors:
        return {
            "status": "source_unprepared",
            "missing_anchor_keys": sorted(missing_anchors),
            "global_hydrology_certified": False,
            "publishable": False,
        }
    projections = {}
    for tx, tz in owners:
        path = output / f"projection-v3-x{tx}-z{tz}.npz"
        if path.exists():
            result = load_projection(path)
        elif action == "projections":
            existing = None
            for report in declaration["accepted_window_reports"]:
                record = json.loads(Path(report["path"]).read_text())
                for parent in record["accepted_owning_core_provenance"]:
                    if parent["tile_xz"] == [tx, tz]:
                        candidate = load_projection(parent["path"])
                        if candidate["metadata"]["algorithm"] == ALGORITHM:
                            existing = candidate
            try:
                result = existing or prepare_cached_projection(
                    plan,
                    generation,
                    anchors,
                    tile_x=tx,
                    tile_z=tz,
                    lake_level_m=declaration["fixed_lake_level_m"],
                    config=config,
                )
            except ProjectionError as error:
                return {
                    "status": "rejected",
                    "phase": "canonical_projection",
                    "tile_xz": [tx, tz],
                    "reason": str(error),
                    "diagnostics": error.diagnostics,
                    "completed_owning_core_count": len(projections),
                    "declared_owning_core_count": len(owners),
                    "global_hydrology_certified": False,
                    "publishable": False,
                }
            save_projection(result, path)
        else:
            continue
        if (
            result["metadata"]["algorithm"] != ALGORITHM
            or result["metadata"]["plan_identity"] != plan["identity_sha256"]
        ):
            raise ValueError("full-edge projection identity/algorithm differs")
        if (
            result["metadata"]["config"] != asdict(config)
            or result["metadata"]["fixed_lake_level_m"]
            != declaration["fixed_lake_level_m"]
        ):
            raise ValueError("full-edge projection budget/stage differs")
        projections[tx, tz] = result
    if action == "projections":
        return {
            "status": "projection_phase_completed",
            "owning_core_count": len(projections),
            "publishable": False,
        }
    results = []
    for request in declaration["requests"]:
        missing = [
            tile for tile in request["owning_tiles"] if tuple(tile) not in projections
        ]
        if missing and request["source_edge"] == [8470, 8600]:
            try:
                results.append(
                    prepare_finite_mouth(plan, declaration, request, output, anchors)
                )
            except ProjectionError as error:
                results.append(
                    {
                        "source_edge": request["source_edge"],
                        "accepted": False,
                        "status": "rejected",
                        "reason": str(error),
                        "diagnostics": error.diagnostics,
                    }
                )
        elif missing:
            results.append(
                {
                    "source_edge": request["source_edge"],
                    "accepted": False,
                    "status": "projection_unprepared",
                    "missing_owning_tiles": missing,
                }
            )
        else:
            results.append(prepare_bed(plan, declaration, request, projections, output))
    return {
        "status": (
            "finite_edges_geometrically_compatible"
            if all(result["accepted"] for result in results)
            else "rejected"
        ),
        "edges": results,
        "global_hydrology_certified": False,
        "publishable": False,
    }


def prepare_finite_mouth(
    plan, declaration, request, output, anchors, *, diagnostic=False, macro_valley=False
):
    from scipy.ndimage import distance_transform_edt
    from terrain_pipeline.hydrology_detail import (
        _coordinates,
        _interpolate,
        _steepest_receivers,
    )
    from terrain_pipeline.hydrology_detail_projection import (
        project_arrays,
        frozen_river_derivative_constraints,
    )
    from terrain_pipeline.hydrology_detail_ridge import (
        continuous_macro_field,
        stage_fixed_transform,
    )
    from tools.prepare_hydrology_domains import _artifact_identity

    if macro_valley:
        support = request["macro_valley_support"]
        request = {
            **request,
            "native_origin_xz": support["native_origin_xz"],
            "shape": support["shape"],
            "budget": support["budget"],
        }
    x0, z0 = request["native_origin_xz"]
    rows, cols = request["shape"]
    generation = declaration["generation_metadata"]
    source_root = (
        Path(generation["canonical_cache_root"])
        / generation["identity"]
        / str(plan["seed"])
    )
    raw = np.empty((rows, cols), float)
    for tz in range(z0 // CORE, (z0 + rows - 1) // CORE + 1):
        for tx in range(x0 // CORE, (x0 + cols - 1) // CORE + 1):
            path = source_root / f"tile-x{tx}-z{tz}.npz"
            with np.load(path, allow_pickle=False) as archive:
                left, right = max(x0, tx * CORE), min(x0 + cols, (tx + 1) * CORE)
                top, bottom = max(z0, tz * CORE), min(z0 + rows, (tz + 1) * CORE)
                raw[top - z0 : bottom - z0, left - x0 : right - x0] = archive[
                    "elevation_m"
                ][
                    top - tz * CORE : bottom - tz * CORE,
                    left - tx * CORE : right - tx * CORE,
                ]
    origin = [x0 * 30, z0 * 30]
    x, z = _coordinates(plan, origin, raw.shape, 30)
    macro = stage_fixed_transform(
        continuous_macro_field(plan, x, z), declaration["fixed_lake_level_m"]
    )
    nz, nx = np.rint(z).astype(int), np.rint(x).astype(int)
    coarse = np.asarray(plan["owner_domain_id"])
    owner = coarse[nz, nx].copy()
    if np.any(owner < -1):
        raise ProjectionError(
            "finite full-edge support contains genuine unknown ownership"
        )
    coastal_ids = [
        domain["domain_id"] for domain in plan["domains"] if domain["kind"] == "coastal"
    ]
    nearest = distance_transform_edt(
        ~np.isin(coarse, coastal_ids), return_distances=False, return_indices=True
    )
    ocean_stencil = _interpolate(np.asarray(plan["ocean_mask"], float), x, z) > 0
    ocean = ocean_stencil & (macro < 0)
    extension = (owner == -1) & ~ocean
    owner[extension] = coarse[nearest[0], nearest[1]][nz, nx][extension]
    owner[ocean] = -1
    baseline = np.asarray(plan["original_height_m"], float).copy()
    for key, value in anchors.items():
        rz, cx = map(int, key.split(":"))
        baseline[rz, cx] = value["elevation_m"]
    rr, cc = np.indices(raw.shape)
    distance = np.minimum.reduce([rr, cc, rows - 1 - rr, cols - 1 - cc]) * 30
    pinned = distance <= 30
    retained = np.clip((distance - 30) / 1000, 0, 1)
    retained = retained**2 * (3 - 2 * retained)
    target = macro + retained * (raw - _interpolate(baseline, x, z))
    recipe = declaration["finite_mouth_projection"]
    if macro_valley:
        recipe = {
            **recipe,
            "algorithm": "finite-complete-river-macro-valley-projection-v1",
        }
    config = ProjectionConfig(
        macro_max_abs_m=request["budget"]["macro_max_abs_m"],
        macro_absolute_volume_m3=request["budget"]["macro_absolute_volume_m3"],
        max_nodes=recipe["max_nodes"],
        max_constraints=recipe["max_constraints"],
        max_nonzeros=recipe["max_nonzeros"],
        time_limit_s=recipe["time_limit_s"],
    )
    constraints = frozen_river_derivative_constraints(
        plan, raw.shape, origin, 30, ocean
    )
    low = np.full(raw.shape, -np.inf)
    low[ocean_stencil & ~ocean] = 0
    if diagnostic:
        from terrain_pipeline.hydrology_detail_projection import _witness

        witness = _witness(macro, owner, ocean, ocean, ~pinned, 30)
        active = ~pinned & ~ocean
        source_ids = np.flatnonzero(active.ravel())
        target_ids = witness.ravel()[source_ids]
        fixed_rows = np.all(
            pinned.ravel()[constraints["columns"]] | (constraints["coefficients"] == 0),
            axis=1,
        )
        fixed_residual = (
            np.sum(
                constraints["coefficients"] * macro.ravel()[constraints["columns"]],
                axis=1,
            )
            - constraints["rhs"]
        )
        metrics = {
            "fixed_river_derivative_conflicts": int(
                np.sum(fixed_rows & (fixed_residual > 1e-9))
            ),
            "fixed_macro_max_change_m": float(
                np.abs(macro[pinned] - raw[pinned]).max()
            ),
            "world_macro_absolute_volume_m3": float(np.abs(macro - raw).sum() * 900),
            "frozen_macro_absolute_volume_budget_m3": config.macro_absolute_volume_m3,
            "marine_positive_low_bound_pinned_conflicts": int(
                np.sum(pinned & (ocean_stencil & ~ocean) & (macro < 0))
            ),
            "witness_in_ocean_count": int(np.sum(ocean.ravel()[target_ids])),
        }
        pin_slope_conflicts = []
        for dr, dc in ((0, 1), (1, -1), (1, 0), (1, 1)):
            source = (
                slice(max(0, -dr), min(rows, rows - dr)),
                slice(max(0, -dc), min(cols, cols - dc)),
            )
            destination = (
                slice(max(0, dr), min(rows, rows + dr)),
                slice(max(0, dc), min(cols, cols + dc)),
            )
            difference = np.abs(macro[source] - macro[destination])
            bound = config.max_slope_m_per_m * 30 * np.hypot(dr, dc)
            conflict = (
                pinned[source] & pinned[destination] & (difference > bound + 1e-9)
            )
            for rz, cx in np.argwhere(conflict):
                row = rz + max(0, -dr)
                column = cx + max(0, -dc)
                pin_slope_conflicts.append(
                    {
                        "source_grid_zx": [int(row), int(column)],
                        "destination_grid_zx": [int(row + dr), int(column + dc)],
                        "source_elevation_m": float(macro[row, column]),
                        "destination_elevation_m": float(macro[row + dr, column + dc]),
                        "fixed_difference_m": float(difference[rz, cx]),
                        "allowed_difference_m": float(bound),
                    }
                )
        metrics["fixed_world_boundary_slope_conflict_count"] = len(pin_slope_conflicts)
        metrics["fixed_world_boundary_slope_conflict_witnesses"] = pin_slope_conflicts[
            :8
        ]
        try:
            project_arrays(
                raw,
                target,
                macro,
                owner,
                ocean,
                ocean,
                ~pinned,
                pinned,
                spacing_m=30,
                config=config,
                lower_height_m=low,
                frozen_river_constraints=None,
            )
            metrics["without_river_constraints"] = "feasible_diagnostic_only"
        except ProjectionError as error:
            metrics["without_river_constraints"] = str(error)
            metrics["without_river_diagnostics"] = error.diagnostics
        return {
            "status": "diagnosis_only",
            "natural_or_hydraulic_acceptance": False,
            **metrics,
        }
    directory = output / (
        "finite-river-macro-valley-v1" if macro_valley else "finite-mouth-v1"
    )
    directory.mkdir(exist_ok=True)
    path = directory / "projection.npz"
    if path.exists():
        with np.load(path, allow_pickle=False) as archive:
            result = {
                "metadata": json.loads(str(archive["metadata_json"].item())),
                "arrays": {
                    key: archive[key].copy()
                    for key in archive.files
                    if key != "metadata_json"
                },
            }
    else:
        valley = None
        if macro_valley:
            from terrain_pipeline.hydrology_detail_projection import (
                frozen_river_valley_floor_constraints,
            )

            valley = frozen_river_valley_floor_constraints(
                plan,
                raw.shape,
                origin,
                30,
                ocean,
                source_edges=[request["source_edge"]],
            )
        result = project_arrays(
            raw,
            target,
            macro,
            owner,
            ocean,
            ocean,
            ~pinned,
            pinned,
            spacing_m=30,
            config=config,
            lower_height_m=low,
            frozen_river_constraints=constraints,
            fixed_boundary_slope_policy=recipe["fixed_boundary_slope_policy"],
            frozen_valley_constraints=valley,
        )
        result["metadata"].update(
            algorithm=recipe["algorithm"],
            plan_identity=plan["identity_sha256"],
            declaration_identity=declaration["identity"],
            origin_xz_m=origin,
            shape=list(raw.shape),
            source_tiles=declaration["source_tiles"],
            coastal_extension_pixel_count=int(extension.sum()),
            canonical_core_certified=False,
            publishable=False,
        )
        result["metadata"]["identity"] = _artifact_identity(
            result["metadata"], result["arrays"]
        )
        with path.open("xb") as stream:
            np.savez_compressed(
                stream,
                metadata_json=np.array(json.dumps(result["metadata"])),
                **result["arrays"],
            )
    if result["metadata"]["identity"] != _artifact_identity(
        result["metadata"], result["arrays"]
    ):
        raise ValueError("finite full-edge saved projection identity differs")
    metadata = result["metadata"]
    if (
        metadata.get("algorithm") != recipe["algorithm"]
        or metadata.get("plan_identity") != plan["identity_sha256"]
        or metadata.get("declaration_identity") != declaration["identity"]
        or metadata.get("config") != asdict(config)
        or metadata.get("fixed_boundary_slope_policy")
        != recipe["fixed_boundary_slope_policy"]
    ):
        raise ValueError("finite full-edge saved projection frozen recipe differs")
    expected_arrays = {
        "original_td_m": raw,
        "target_height_m": target,
        "macro_height_m": macro,
        "owner_domain_id": owner,
        "ocean_mask": ocean,
        "terminal_mask": ocean,
        "core_mask": ~pinned,
        "pinned_mask": pinned,
    }
    if any(
        not np.array_equal(result["arrays"][key], value)
        for key, value in expected_arrays.items()
    ):
        raise ValueError("finite full-edge saved source, target, owner or masks differ")
    height = result["arrays"]["projection_height_m"]
    delta = height - raw
    if (
        np.abs(delta).max() > config.macro_max_abs_m + 1e-6
        or np.abs(delta).sum() * 900 > config.macro_absolute_volume_m3 + 1e-6
    ):
        raise ValueError("finite full-edge saved macro budget rejected")
    river_residual = (
        np.sum(
            constraints["coefficients"] * height.ravel()[constraints["columns"]], axis=1
        )
        - constraints["rhs"]
    )
    if river_residual.max(initial=0) > 1e-7:
        raise ValueError("finite full-edge saved continuous river derivative rejected")
    maximum_modifiable_slope = 0.0
    for dr, dc in ((0, 1), (1, -1), (1, 0), (1, 1)):
        source = (
            slice(max(0, -dr), min(rows, rows - dr)),
            slice(max(0, -dc), min(cols, cols - dc)),
        )
        destination = (
            slice(max(0, dr), min(rows, rows + dr)),
            slice(max(0, dc), min(cols, cols + dc)),
        )
        modifiable = ~(pinned[source] & pinned[destination])
        slopes = np.abs(height[source] - height[destination]) / (30 * np.hypot(dr, dc))
        maximum_modifiable_slope = max(
            maximum_modifiable_slope, float(slopes[modifiable].max(initial=0))
        )
    if (
        maximum_modifiable_slope > config.max_slope_m_per_m + 1e-8
        or not np.array_equal(height[pinned], macro[pinned])
    ):
        raise ProjectionError(
            "finite full-edge cold modifiable slope or world interface rejected"
        )
    cold = {
        "maximum_modifiable_neighbor_slope_m_per_m": maximum_modifiable_slope,
        "fixed_world_boundary_slope_policy": recipe["fixed_boundary_slope_policy"],
        "fixed_world_boundary_actual_slope_diagnostics": result["metadata"][
            "fixed_boundary_actual_slope_diagnostics"
        ],
        "scope": "modifiable interior-interior and interior-fixed pairs <=0.75; fixed-fixed world slopes only observed",
        "source_target_owner_masks_equal": True,
        "frozen_recipe_equal": True,
        "maximum_river_derivative_residual_m_per_m": float(
            river_residual.max(initial=0)
        ),
        "macro_max_abs_m": float(np.abs(delta).max()),
        "macro_absolute_volume_m3": float(np.abs(delta).sum() * 900),
    }
    (directory / "cold-slope-audit.json").write_text(
        json.dumps(cold, indent=2), encoding="utf-8"
    )
    actual = _steepest_receivers(result["arrays"]["projection_height_m"], 30)
    destination = np.maximum(actual, 0)
    core = ~pinned
    crossing = (
        core
        & (actual >= 0)
        & (owner >= 0)
        & (owner.ravel()[destination] >= 0)
        & (owner != owner.ravel()[destination])
    )
    if np.any(core & (actual < 0) & ~ocean) or crossing.any():
        raise ProjectionError("finite full-edge cold D8 owner or sink audit rejected")
    # Reuse bed path with one explicit finite-owned rectangle, no core certificate.
    synthetic = {
        key: result["arrays"][key]
        for key in (
            "original_td_m",
            "projection_height_m",
            "owner_domain_id",
            "ocean_mask",
            "terminal_mask",
        )
    }
    projection = {
        "metadata": {
            "identity": result["metadata"]["identity"],
            "native_origin_xz": [x0, z0],
            "core_native_origin_xz": [x0, z0],
            "core_shape": [rows, cols],
            "origin_xz_m": origin,
            "spacing_m": 30,
        },
        "arrays": synthetic,
    }
    return prepare_bed(
        plan,
        declaration,
        request,
        {},
        output,
        finite_arrays=synthetic,
        finite_parent=result["metadata"]["identity"],
    )


def prepare_bed(
    plan,
    declaration,
    request,
    projections,
    output,
    *,
    finite_arrays=None,
    finite_parent=None,
):
    x, z = request["native_origin_xz"]
    rows, columns = request["shape"]
    keys = (
        "original_td_m",
        "projection_height_m",
        "owner_domain_id",
        "ocean_mask",
        "terminal_mask",
    )
    arrays = finite_arrays or {
        key: np.empty(
            (rows, columns), dtype=next(iter(projections.values()))["arrays"][key].dtype
        )
        for key in keys
    }
    parents = [finite_parent] if finite_parent else []
    for tx, tz in ([] if finite_arrays is not None else request["owning_tiles"]):
        left, right = max(x, tx * CORE), min(x + columns, (tx + 1) * CORE)
        top, bottom = max(z, tz * CORE), min(z + rows, (tz + 1) * CORE)
        cropped = crop_projection(
            projections[tx, tz], [left, top], [bottom - top, right - left]
        )
        region = np.s_[top - z : bottom - z, left - x : right - x]
        for key in keys:
            arrays[key][region] = cropped["arrays"][key]
        parents.append(projections[tx, tz]["metadata"]["identity"])
    if np.any(arrays["terminal_mask"] & ~arrays["ocean_mask"]):
        return {
            "source_edge": request["source_edge"],
            "accepted": False,
            "reason": "wet_lake_support_owned_by_lake_product",
        }
    # Budget scales with actual finite support at the already frozen per-area rate.
    values = dict(request["budget"])
    budget = DetailBudget(**values)
    edge = request["source_edge"]
    directory = output / f"edge-{edge[0]}-{edge[1]}-{declaration['bed_version']}"
    if finite_parent:
        directory = directory.with_name(directory.name + "-owned-halo2")
    directory.mkdir(exist_ok=True)
    raw_path = directory / "canonical-original.npz"
    if not raw_path.exists():
        with raw_path.open("xb") as stream:
            np.savez_compressed(
                stream,
                original_td_m=arrays["original_td_m"],
                source_tiles_json=np.array(json.dumps(declaration["source_tiles"])),
                parent_projection_identities_json=np.array(json.dumps(parents)),
            )
        raw_path.with_suffix(".sha256").write_text(
            file_sha256(raw_path), encoding="ascii"
        )
    raw_sha = raw_path.with_suffix(".sha256").read_text().strip()
    if file_sha256(raw_path) != raw_sha:
        raise ValueError("immutable stitched original TD archive changed")
    raw_provenance = {
        "artifact_kind": "terrain_diffusion_output",
        "td_inference_run": True,
        "archive_sha256": raw_sha,
        "generation_metadata": declaration["generation_metadata"],
        "source_tiles": declaration["source_tiles"],
        "derivation": "owned canonical raw pixels stitched without inference",
    }
    d8_owned = None
    if finite_arrays is not None:
        d8_owned = np.zeros((rows, columns), bool)
        d8_owned[2:-2, 2:-2] = True
    detail = derive_detail(
        transformed_coarse_plan(plan, declaration["fixed_lake_level_m"]),
        arrays["original_td_m"],
        origin_xz_m=[x * 30, z * 30],
        spacing_m=30,
        raw_provenance=raw_provenance,
        window_kind="mouth" if arrays["ocean_mask"].any() else "river",
        budget=budget,
        candidate_height_m=arrays["projection_height_m"],
        candidate_provenance={
            "artifact_kind": "derived_terrain_diffusion_macro_geometry",
            "td_inference_run": False,
            "parent_archive_sha256": raw_sha,
        },
        fine_support={
            "algorithm": "frozen-ocean-support-continuous-zero-isoline-v1",
            "owner_domain_id": arrays["owner_domain_id"],
            "ocean_mask": arrays["ocean_mask"],
        },
        d8_owned_mask=d8_owned,
    )
    if not (directory / "detail.npz").exists():
        save_detail(directory / "detail.npz", detail)
    detail_reasons = [
        reason
        for reason in detail["metadata"]["rejection_reasons"]
        if reason != "continuous_fine_bed_not_certified"
    ]
    if detail_reasons:
        return {
            "source_edge": edge,
            "accepted": False,
            "reason": "parent_detail_rejected",
            "parent_detail_rejection_reasons": detail_reasons,
            "detail_path": str(directory / "detail.npz"),
        }
    profile = frozen_window_profiles(
        plan, arrays["projection_height_m"], [x * 30, z * 30], 30, source_edges=[edge]
    )[0]
    knots = np.linspace(0.0, 1.0, len(request["piece_fraction_intervals"]) + 1)
    points = (
        np.array(request["points_xz_m"])[0]
        + knots[:, None] * np.diff(np.array(request["points_xz_m"]), axis=0)[0]
    )
    spec = {
        "points_xz_m": points.tolist(),
        "receiver": list(range(1, len(knots))) + [-1],
        "width_m": [8.0] * len(knots),
        "bed_target_m": np.interp(
            knots, profile["fractions"], profile["bed_m"]
        ).tolist(),
        "node_source_edges": [edge] * len(knots),
        "node_edge_fractions": knots.tolist(),
        "fine_spacing_m": 1.0,
        "coverage": {
            "scope": "complete frozen coarse edge",
            "entire_coarse_edge_covered": True,
        },
        "centerline_profile": {
            "parent_detail_identity": detail["metadata"]["identity"],
            "offsets": [0],
            "t": [],
            "source_m": [],
            "bed_m": [],
        },
    }
    shared = spec["centerline_profile"]
    for lo, hi in zip(knots[:-1], knots[1:]):
        samples = np.r_[
            lo,
            profile["fractions"][
                (profile["fractions"] > lo) & (profile["fractions"] < hi)
            ],
            hi,
        ]
        shared["t"].extend(((samples - lo) / (hi - lo)).tolist())
        for key, source in (("source_m", "source_m"), ("bed_m", "bed_m")):
            shared[key].extend(
                np.interp(samples, profile["fractions"], profile[source]).tolist()
            )
        shared["offsets"].append(len(shared["t"]))
    completed = []
    sections = None
    if declaration["bed_version"] == "v7-shared-sections":
        from terrain_pipeline.channel_geometry import frozen_shared_sections

        sections = frozen_shared_sections(detail, spec)
        spec["shared_sections_algorithm"] = sorted({section["algorithm"] for group in sections for section in group})
        spec["shared_sections"] = sections
    request_path = directory / "request.json"
    if request_path.exists() and json.loads(request_path.read_text()) != spec:
        raise ValueError("immutable full-edge bed request differs")
    if not request_path.exists():
        request_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    piece_paths = []
    for index, piece in enumerate(split_frozen_window_component(spec)):
        cache_contract = piece if sections is None else {
            "piece": piece,
            "shared_sections_algorithm": spec["shared_sections_algorithm"],
            "shared_sections": sections[index],
        }
        path = directory / f"piece-{index:03d}-{_digest(cache_contract)[:12]}.npz"
        if path.exists():
            from tools.prepare_hydrology_domains import _read_bed_piece

            result = _read_bed_piece(path)
            if result["parent_detail_identity"] != detail["metadata"]["identity"]:
                raise ValueError(
                    "cached full-edge piece belongs to different shared profile"
                )
            from terrain_pipeline.channel_geometry import audit_saved_continuous_bed

            if not audit_saved_continuous_bed(result, detail, center_lowest=True, centerline_profile=piece["centerline_profile"])[
                "accepted"
            ]:
                raise ValueError("cached full-edge current geometry audit rejected")
        else:
            result = derive_continuous_bed(
                detail,
                piece["points_xz_m"],
                piece["receiver"],
                piece["width_m"],
                piece["bed_target_m"],
                frozen_plan=plan,
                node_source_edges=piece["node_source_edges"],
                node_edge_fractions=piece["node_edge_fractions"],
                centerline_profile=piece["centerline_profile"],
                center_lowest=True,
                continuous_center_lowest=declaration["bed_version"]
                in ("v5-continuous-center-floor", "v7-shared-sections"),
                **(
                    {"shared_sections": sections[index]} if sections is not None else {}
                ),
            )
        completed.append(result)
        if not result.get("arrays"):
            (directory / f"piece-{index:03d}-rejected.json").write_text(
                json.dumps(
                    {key: value for key, value in result.items() if key != "arrays"},
                    indent=2,
                ),
                encoding="utf-8",
            )
            break
        if not path.exists():
            record = {key: value for key, value in result.items() if key != "arrays"}
            from tools.prepare_hydrology_domains import _artifact_identity

            record["identity"] = _artifact_identity(record, result["arrays"])
            with path.open("xb") as stream:
                np.savez_compressed(
                    stream,
                    metadata_json=np.array(json.dumps(record)),
                    **result["arrays"],
                )
        piece_paths.append(str(path))
    audit = audit_frozen_window_seams(completed, spec, center_lowest=True)
    reasons = detail["metadata"]["rejection_reasons"]
    local_volume = sum(
        result.get("ledger", {}).get("local_cut_volume_m3", 0.0) for result in completed
    )
    combined = detail["metadata"]["ledger"]["macro_absolute_volume_m3"] + local_volume
    report = {
        "schema": "hydrology-complete-edge-bed-review-v1",
        "bed_version": declaration["bed_version"],
        "plan_identity": plan["identity_sha256"],
        "declaration_identity": declaration["identity"],
        "detail_path": str(directory / "detail.npz"),
        "detail_identity": detail["metadata"]["identity"],
        "component_request_path": str(request_path),
        "component_request_sha256": file_sha256(request_path),
        "piece_paths": piece_paths,
        "source_edge": edge,
        "accepted": bool(
            audit["accepted"]
            and not [
                reason
                for reason in reasons
                if reason != "continuous_fine_bed_not_certified"
            ]
            and combined <= budget.total_absolute_volume_m3
        ),
        "seam_audit": audit,
        "parent_detail_rejection_reasons": reasons,
        "combined_absolute_volume_upper_bound_m3": combined,
        "budget": asdict(budget),
        "cross_edge_endpoint_continuity_verified": False,
        "declared_piece_count": len(knots) - 1,
        "completed_piece_count": sum(
            bool(result.get("arrays")) for result in completed
        ),
        "rejection_reasons": [
            result.get("reason") for result in completed if not result.get("arrays")
        ],
        "coverage": spec["coverage"],
        "global_hydrology_certified": False,
        "publishable": False,
    }
    (directory / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def rebind_declaration(source_path, plan_path, output, fixed_lake_level_m, bed_version):
    """Reuse pinned raw TD inputs; all derived products require fresh preparation."""
    import copy

    source = json.loads(Path(source_path).read_text(encoding="utf-8"))
    if _digest({key: value for key, value in source.items() if key != "identity"}) != source["identity"]:
        raise ValueError("source declaration identity mismatch")
    previous = load_plan(source["plan_path"])
    plan = load_plan(plan_path)
    if plan["seed"] != previous["seed"] or plan["spacing_m"] != previous["spacing_m"] or plan["origin_xz_m"] != previous["origin_xz_m"]:
        raise ValueError("rebind requires same world seed and coarse grid")
    for key in ("ocean_mask",):
        if not np.array_equal(plan[key], previous[key]):
            raise ValueError("rebind requires same ocean support")
    if not np.isfinite(fixed_lake_level_m):
        raise ValueError("explicit finite frozen coarse-account stage required")
    result = copy.deepcopy(source)
    result.pop("identity")
    result.update(plan_path=str(plan_path), plan_sha256=file_sha256(plan_path), plan_identity=plan["identity_sha256"],
                  fixed_lake_level_m=float(fixed_lake_level_m), bed_version=bed_version,
                  rebind_source={"path": str(source_path), "sha256": file_sha256(source_path), "identity": source["identity"]},
                  accepted_window_reports=[], coverage_scope="rebound raw sources and finite requests; no parent derived acceptance transferred")
    for request in result["requests"]:
        checked = edge_request(plan, request["source_edge"])
        for key in ("source_edge", "points_xz_m", "length_m", "piece_fraction_intervals"):
            if request[key] != checked[key]:
                raise ValueError("rebound selected river geometry changed")
        request["endpoint_ids"] = checked["endpoint_ids"]
    selected = np.flatnonzero((np.asarray(plan["owner_domain_id"]).ravel() >= 0) & np.asarray(plan["river_mask"]).ravel() & (np.asarray(plan["receiver"]).ravel() >= 0))
    edges = [[int(cell), int(np.asarray(plan["receiver"]).ravel()[cell])] for cell in selected]
    scheduled = {tuple(request["source_edge"]) for request in result["requests"]}
    result["selected_graph_edge_count"] = len(edges)
    result["unscheduled_selected_edges"] = [edge for edge in edges if tuple(edge) not in scheduled]
    result["identity"] = _digest(result)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "plan.json"
    if path.exists() and json.loads(path.read_text())["identity"] != result["identity"]:
        raise ValueError("immutable rebound declaration differs")
    if not path.exists():
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def global_macro_bed_nodes(plan, stage):
    """One finite-DAG bed reference from the frozen continuous macro, in metres."""
    from terrain_pipeline.hydrology_detail_ridge import continuous_macro_field, stage_fixed_transform

    receiver = np.asarray(plan["receiver"]).ravel()
    selected = np.flatnonzero((np.asarray(plan["owner_domain_id"]).ravel() >= 0) & np.asarray(plan["river_mask"]).ravel() & (receiver >= 0))
    columns = np.asarray(plan["height_m"]).shape[1]
    edges, samples, distances = [], [], []
    for first in selected:
        second = int(receiver[first])
        points = np.asarray(plan["origin_xz_m"]) + np.array([[first % columns, first // columns], [second % columns, second // columns]]) * plan["spacing_m"]
        length = float(np.linalg.norm(points[1] - points[0]))
        distance = np.linspace(0, length, int(np.ceil(length)) + 1)
        samples.append(points[0] + (distance / length)[:, None] * (points[1] - points[0]))
        distances.append(distance)
        edges.append((int(first), second))
    if not edges:
        return {}
    joined = np.concatenate(samples)
    coordinates = (joined - plan["origin_xz_m"]) / plan["spacing_m"]
    source = stage_fixed_transform(continuous_macro_field(plan, coordinates[:, 0], coordinates[:, 1]), stage)
    targets, profiles = {}, []
    offset = 0
    for edge, distance in zip(edges, distances):
        heights = source[offset:offset + len(distance)]
        offset += len(distance)
        bed = np.minimum.accumulate(heights + 0.001 * distance) - 0.001 * distance - 0.5
        profiles.append(bed)
        for node, value in zip(edge, (bed[0], bed[-1])):
            targets[node] = min(targets.get(node, np.inf), float(value))
    pending = list(range(len(edges)))
    while pending:
        ready = [index for index in pending if not any(edges[upstream][1] == edges[index][0] for upstream in pending)]
        if not ready:
            raise ValueError("global bed reference contains a cycle")
        for index in ready:
            first, second = edges[index]
            bed = np.minimum(profiles[index], targets[first] - 0.001 * distances[index])
            targets[second] = min(targets[second], float(bed[-1]))
            pending.remove(index)
    return targets


def prepare_coarse_bed_graph(plan, stage, fine_ports, fine_edges, output):
    """Represent remaining river edges as source-bounded 1m sampled coarse profiles."""
    from terrain_pipeline.hydrology_detail_ridge import continuous_macro_field, stage_fixed_transform

    receiver = np.asarray(plan["receiver"]).ravel()
    owner = np.asarray(plan["owner_domain_id"]).ravel()
    river = np.asarray(plan["river_mask"]).ravel()
    columns = np.asarray(plan["height_m"]).shape[1]
    edges = [(int(first), int(receiver[first])) for first in np.flatnonzero((owner >= 0) & river & (receiver >= 0))]
    node_heights = {node: float(stage_fixed_transform(np.array([np.asarray(plan["height_m"]).ravel()[node]]), stage)[0] - 0.5) for edge in edges for node in edge}
    for node, port in fine_ports.items():
        node_heights[node] = port["realized_center_m"]
    pending = list(edges)
    order = []
    while pending:
        ready = [edge for edge in pending if not any(other[1] == edge[0] for other in pending)]
        if not ready:
            raise ValueError("coarse bed graph cycle")
        for edge in ready:
            order.append(edge)
            pending.remove(edge)
    sampled = {}
    requests = []
    coarse_edges = [edge for edge in order if edge not in fine_edges]
    pivot_positions = []
    for edge in coarse_edges:
        endpoints = np.asarray(plan["origin_xz_m"]) + np.array([[cell % columns, cell // columns] for cell in edge]) * plan["spacing_m"]
        pivot_positions.extend([endpoints[0], endpoints.mean(axis=0), endpoints[1]])
    pivot_source = np.empty((0, 3))
    if pivot_positions:
        pivot_coords = (np.asarray(pivot_positions) - plan["origin_xz_m"]) / plan["spacing_m"]
        pivot_source = continuous_macro_field(plan, pivot_coords[:, 0], pivot_coords[:, 1]).reshape(-1, 3)
    pivot_lookup = dict(zip(coarse_edges, pivot_source))
    for edge in order:
        if edge in fine_edges:
            continue
        points = np.asarray(plan["origin_xz_m"]) + np.array([[cell % columns, cell // columns] for cell in edge]) * plan["spacing_m"]
        length = float(np.linalg.norm(points[1] - points[0]))
        critical = [0., min(30., length / 2), length / 2, max(length - 30., length / 2), length]
        for ordinal in range(2):
            low, high = pivot_lookup[edge][ordinal:ordinal + 2]
            if low != high:
                for level in np.linspace(0., stage, 17):
                    fraction = (level - low) / (high - low)
                    if 0 < fraction < 1:
                        critical.append((ordinal + fraction) * length / 2)
        distances = np.unique(np.r_[np.linspace(0., length, int(np.ceil(length)) + 1), critical])
        positions = points[0] + (distances / length)[:, None] * (points[1] - points[0])
        sampled[edge] = {"distance_m": distances, "points_xz_m": positions}
        requests.append(positions)
    if requests:
        coordinates = (np.concatenate(requests) - plan["origin_xz_m"]) / plan["spacing_m"]
        heights = stage_fixed_transform(continuous_macro_field(plan, coordinates[:, 0], coordinates[:, 1]), stage)
        offset = 0
        for edge in sampled:
            size = len(sampled[edge]["distance_m"])
            sampled[edge]["source_macro_surface_m"] = heights[offset:offset + size]
            offset += size
    failures = []
    minimum_grade = 1e-5

    def design_caps(arrays, first, second):
        distance = arrays["distance_m"]
        source = arrays["source_macro_surface_m"]
        depth = np.full(len(distance), 0.5)
        depth += (source[0] - node_heights[first] - 0.5) * np.clip(1. - distance / 30., 0., 1.)
        depth += (source[-1] - node_heights[second] - 0.5) * np.clip(1. - (distance[-1] - distance) / 30., 0., 1.)
        return np.minimum(source, source - depth)

    for first, second in order:
        if (first, second) in fine_edges:
            continue
        arrays = sampled[first, second]
        distances = arrays["distance_m"]
        caps = design_caps(arrays, first, second)
        bed = np.minimum.accumulate(caps + minimum_grade * distances) - minimum_grade * distances
        if second in fine_ports and node_heights[second] > bed[-1] + 1e-6:
            failures.append({"source_edge": [first, second], "reason": "fixed_realized_port_above_upstream_profile_ceiling", "difference_m": float(node_heights[second] - bed[-1])})
        if second not in fine_ports:
            node_heights[second] = min(node_heights[second], float(bed[-1]))
    records = []
    directory = Path(output) / "coarse-bed-graph"
    directory.mkdir(parents=True, exist_ok=True)
    for first, second in order:
        if (first, second) in fine_edges:
            continue
        arrays = sampled[first, second]
        distance, source = arrays["distance_m"], arrays["source_macro_surface_m"]
        caps = design_caps(arrays, first, second)
        bed = np.minimum.accumulate(caps + minimum_grade * distance) - minimum_grade * distance
        bed[-1] = node_heights[second]
        arrays["coarse_bed_elevation_m"] = bed
        audit = {"maximum_cut_m": float(np.max(source - bed)), "minimum_cut_m": float(np.min(source - bed)),
                 "minimum_downstream_grade": float(np.min(-np.diff(bed) / np.diff(distance))),
                 "upstream_port_difference_m": float(bed[0] - node_heights[first]),
                 "downstream_port_difference_m": float(bed[-1] - node_heights[second])}
        accepted = (audit["maximum_cut_m"] <= 4. + 1e-6 and audit["minimum_cut_m"] >= -1e-6
                    and audit["minimum_downstream_grade"] >= minimum_grade - 1e-8
                    and abs(audit["upstream_port_difference_m"]) <= 1e-6
                    and abs(audit["downstream_port_difference_m"]) <= 1e-6)
        metadata = {"schema": "hydrology-coarse-river-centerline-profile-v2-realized-ports", "plan_identity": plan["identity_sha256"],
                    "source_edge": [first, second], "frozen_coarse_account_stage_m": stage, "accepted": bool(accepted),
                    "physical_constraints": {"minimum_longitudinal_grade": minimum_grade, "minimum_cut_m": 0., "maximum_cut_m": 4.},
                    "design_goals": {"default_depth_m": 0.5, "actual_port_transition_m": 30.},
                    "audit": audit, "representation": "piecewise affine centerline of coarse continuous macro, <=1m knots plus every fan-face and stage-map breakpoint; transverse terrain and hydraulic section remain coarse"}
        path = directory / f"edge-{first}-{second}.npz"
        with path.open("wb") as stream:
            np.savez_compressed(stream, metadata_json=np.array(json.dumps(metadata)), **arrays)
        records.append({**metadata, "path": str(path), "archive_sha256": file_sha256(path)})
        if not accepted:
            failures.append({"source_edge": [first, second], "reason": "coarse_profile_geometry_rejected", "audit": audit})
    return {"accepted": not failures, "failures": failures, "edge_profiles": records,
            "realized_fine_ports": [{"coarse_node": node, **record} for node, record in sorted(fine_ports.items())],
            "bed_node_heights_m": {str(node): value for node, value in sorted(node_heights.items())},
            "scope": "complete selected coarse river graph; full fine geometry on declared fine edges, source-bounded centerline profiles on coarse-only edges"}


def audit_confluence_fraction_interfaces(plan_path, continuity_path, generation_path, cold_path, sidecar_path, output):
    """Bind independently audited joint geometry to its exact source edge fractions."""
    from tools.prepare_hydrology_domains import _read_bed_piece, _artifact_identity
    from terrain_pipeline.channel_geometry import _mesh_height
    from terrain_pipeline.channel_geometry import _cell_at_point
    from terrain_pipeline.hydrology_detail_tributaries import validate_local_tributary_sidecar
    from terrain_pipeline.runoff import LakeGeometry as LakeGeometry

    plan = load_plan(plan_path)
    prior = json.loads(Path(continuity_path).read_text(encoding="utf-8"))
    generation = json.loads(Path(generation_path).read_text(encoding="utf-8"))
    cold = json.loads(Path(cold_path).read_text(encoding="utf-8"))
    sidecar = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
    stage = float(sidecar["highest_lake_level_m"])
    inland = next(domain for domain in plan["domains"] if domain["kind"] == "inland")
    mask = LakeGeometry(plan["height_m"], plan["owner_domain_id"], inland, plan["spacing_m"] ** 2).mask
    validate_local_tributary_sidecar(plan, sidecar, highest_lake_level_m=stage, lake_mask=mask)
    if prior["plan_identity"] != plan["identity_sha256"] or cold["plan_identity"] != plan["identity_sha256"]:
        raise ValueError("fraction interface evidence plan identity mismatch")
    if not generation["local_window_compatible"] or len(generation["piece_results"]) != 1:
        raise ValueError("accepted single joint confluence mesh required")
    piece_path = Path(generation["piece_results"][0]["path"])
    piece = _read_bed_piece(piece_path)
    detail_path = Path(generation["computational_support99_path"])
    with np.load(detail_path, allow_pickle=False) as archive:
        detail_metadata = json.loads(str(archive["metadata_json"].item()))
        detail_arrays = {key: archive[key] for key in archive.files if key != "metadata_json"}
    if (_artifact_identity(detail_metadata, detail_arrays) != detail_metadata["identity"]
            or cold["source_parent_identity"] != detail_metadata["identity"]
            or detail_metadata.get("raw_provenance", {}).get("artifact_kind") != "terrain_diffusion_output"):
        raise ValueError("joint source detail or real TD provenance mismatch")
    audit = cold["audit"]
    if (cold["piece_identity"] != piece["identity"] or not audit["accepted"]
            or not audit.get("frozen_profile_ceiling_verified")
            or not audit.get("continuous_longitudinal_gradient_verified")):
        raise ValueError("strong matching independent joint cold audit required")
    request_path = Path(generation["component_request_path"])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if generation.get("component_request_sha256", file_sha256(request_path)) != file_sha256(request_path):
        raise ValueError("joint component request pin mismatch")
    points = np.asarray(request["points_xz_m"])
    receivers = np.asarray(request["receiver"])
    source_edges = np.asarray(request["node_source_edges"])
    columns = np.asarray(plan["height_m"]).shape[1]
    arrays = piece["arrays"]
    lookup = {tuple(cell): index for index, cell in enumerate(arrays["cells"])}
    coverage = []
    for declaration in sidecar["edges"]:
        edge = tuple(declaration["source_edge"])
        nodes = set()
        for index in np.flatnonzero(np.all(source_edges == edge, axis=1) & (receivers >= 0)):
            nodes.update((int(index), int(receivers[index])))
        if not nodes:
            raise ValueError("declared confluence arm has no actual fine coverage")
        endpoints = np.asarray(plan["origin_xz_m"]) + np.array([[node % columns, node // columns] for node in edge]) * plan["spacing_m"]
        direction = endpoints[1] - endpoints[0]
        fractions = {node: float(np.dot(points[node] - endpoints[0], direction) / np.dot(direction, direction)) for node in nodes}
        first, last = min(nodes, key=fractions.get), max(nodes, key=fractions.get)
        heights = []
        for index in (first, last):
            point = points[index]
            key = _cell_at_point(point, lookup, piece["mesh_origin_xz_m"], piece["fine_spacing_m"])
            heights.append(float(_mesh_height(point, lookup[key], arrays["vertices_xz_m"], arrays["triangles"], arrays["bed_elevation_m"])))
        coverage.append({"source_edge": list(edge), "fraction_interval": [fractions[first], fractions[last]],
                         "source_edge_length_m": float(np.linalg.norm(direction)),
                         "fine_covered_length_m": float((fractions[last] - fractions[first]) * np.linalg.norm(direction)),
                         "upstream_realized_center_m": heights[0], "downstream_realized_center_m": heights[1],
                         "clipped_boundary_node_indices": [first, last], "piece_identity": piece["identity"],
                         "frozen_coarse_account_stage_m": stage})
    extra = [item["source_edge"] for item in sidecar["edges"] if item["category"] == "subthreshold_local_tributary_edge"]
    result = stitch_fractional_coarse_profiles(plan, prior["coarse_bed_graph"], coverage, output, extra_edges=extra)
    result.update({"schema": "hydrology-confluence-fraction-interfaces-v1", "plan_identity": plan["identity_sha256"],
                   "parent_continuity_report_path": str(continuity_path), "parent_continuity_report_sha256": file_sha256(continuity_path),
                   "generation_report_path": str(generation_path), "generation_report_sha256": file_sha256(generation_path),
                   "independent_cold_report_path": str(cold_path), "independent_cold_report_sha256": file_sha256(cold_path),
                   "sidecar_path": str(sidecar_path), "sidecar_sha256": file_sha256(sidecar_path),
                   "piece_path": str(piece_path), "piece_archive_sha256": file_sha256(piece_path),
                   "component_request_path": str(request_path), "component_request_sha256": file_sha256(request_path),
                   "detail_path": str(detail_path), "detail_archive_sha256": file_sha256(detail_path),
                   "local_window_compatible": bool(result["accepted"]), "source_artifact_kind": "terrain_diffusion_output",
                   "real_td_source": True, "global_hydrology_certified": False})
    result["total_fine_fraction_covered_length_m"] = sum(item["fine_covered_length_m"] for item in coverage)
    path = Path(output) / "fraction-interfaces.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def stitch_fractional_coarse_profiles(plan, graph, coverage, output, *, extra_edges=()):
    """Replace explicit edge intervals with fine geometry, preserving outside profiles."""
    receiver = np.asarray(plan["receiver"]).ravel()
    owner = np.asarray(plan["owner_domain_id"]).ravel()
    records = {tuple(item["source_edge"]): item for item in graph["edge_profiles"]}
    additions = []
    for edge in extra_edges:
        first, second = map(int, edge)
        if int(receiver[first]) != second or owner[first] < 0 or owner[first] != owner[second]:
            raise ValueError("extra tributary must be an actual owned receiver edge")
        if (first, second) in records:
            continue
        local_plan = dict(plan)
        mask = np.zeros_like(plan["river_mask"], dtype=bool)
        mask.ravel()[first] = True
        local_plan["river_mask"] = mask
        added = prepare_coarse_bed_graph(local_plan, coverage[0]["frozen_coarse_account_stage_m"], {}, set(), Path(output) / "sidecar-source")
        if not added["accepted"]:
            raise ValueError("sidecar source coarse profile rejected")
        record = added["edge_profiles"][0]
        records[first, second] = record
        additions.append({"source_edge": [first, second], "owner_domain_id": int(owner[first]),
                          "actual_receiver_verified": True, "registration": "explicit local tributary sidecar"})
    replacements, interfaces, failures = [], [], []
    seen = set()
    directory = Path(output) / "fractional-coarse-bed-graph"
    directory.mkdir(parents=True, exist_ok=True)
    for item in coverage:
        edge = tuple(map(int, item["source_edge"]))
        if edge in seen:
            raise ValueError("one contiguous fine interval per source edge is required")
        seen.add(edge)
        if edge not in records:
            raise ValueError("fine interval has no registered coarse source edge")
        lo, hi = map(float, item["fraction_interval"])
        if not 0 <= lo < hi <= 1:
            raise ValueError("invalid fine source edge fraction interval")
        record = records[edge]
        if abs(record["frozen_coarse_account_stage_m"] - item["frozen_coarse_account_stage_m"]) > 1e-9:
            raise ValueError("fine interval and coarse profile use different frozen stages")
        if file_sha256(record["path"]) != record["archive_sha256"]:
            raise ValueError("fractional source archive pin mismatch")
        with np.load(record["path"], allow_pickle=False) as archive:
            old_distance = archive["distance_m"]
            old_points = archive["points_xz_m"]
            old_source = archive["source_macro_surface_m"]
            old_bed = archive["coarse_bed_elevation_m"]
        length = float(old_distance[-1])
        for start, end, boundary, port in ((0., lo, lo, item["upstream_realized_center_m"]),
                                         (hi, 1., hi, item["downstream_realized_center_m"])):
            if start == end:
                continue
            absolute = np.unique(np.r_[start * length, old_distance[(old_distance > start * length) & (old_distance < end * length)], end * length])
            source = np.interp(absolute, old_distance, old_source)
            target = np.interp(absolute, old_distance, old_bed)
            distance = absolute - absolute[0]
            first_height = float(port if start == hi else target[0])
            last_height = float(port if end == lo else target[-1])
            grade = record["physical_constraints"]["minimum_longitudinal_grade"]
            upper = np.minimum(source, first_height - grade * distance)
            lower = np.maximum(source - 4., last_height + grade * (distance[-1] - distance))
            caps = np.maximum(target, lower)
            caps = np.minimum(caps, upper)
            caps[0], caps[-1] = first_height, last_height
            bed = np.minimum.accumulate(caps + grade * distance) - grade * distance
            audit = {"maximum_cut_m": float(np.max(source - bed)), "minimum_cut_m": float(np.min(source - bed)),
                     "minimum_downstream_grade": float(np.min(-np.diff(bed) / np.diff(distance))),
                     "upstream_port_difference_m": float(bed[0] - first_height),
                     "downstream_port_difference_m": float(bed[-1] - last_height)}
            accepted = (audit["maximum_cut_m"] <= 4. + 1e-6 and audit["minimum_cut_m"] >= -1e-6
                        and audit["minimum_downstream_grade"] >= grade - 1e-8
                        and abs(audit["upstream_port_difference_m"]) <= 1e-6
                        and abs(audit["downstream_port_difference_m"]) <= 1e-6)
            points = old_points[0] + (absolute / length)[:, None] * (old_points[-1] - old_points[0])
            keys = [f"{edge[0]}:{edge[1]}:{value:.17g}" for value in (start, end)]
            metadata = {**record, "schema": "hydrology-coarse-river-fraction-profile-v1", "fraction_interval": [start, end],
                        "endpoint_keys": keys, "parent_archive_sha256": record["archive_sha256"], "accepted": bool(accepted), "audit": audit}
            for key in ("path", "archive_sha256"):
                metadata.pop(key, None)
            path = directory / f"edge-{edge[0]}-{edge[1]}-{start:.9f}-{end:.9f}.npz"
            with path.open("wb") as stream:
                np.savez_compressed(stream, metadata_json=np.array(json.dumps(metadata)), distance_m=distance,
                                    points_xz_m=points, source_macro_surface_m=source, coarse_bed_elevation_m=bed)
            replacements.append({**metadata, "path": str(path), "archive_sha256": file_sha256(path)})
            difference = float((bed[0] if start == hi else bed[-1]) - port)
            interfaces.append({"source_edge": list(edge), "fraction": boundary, "realized_fine_center_m": float(port),
                               "coarse_center_difference_m": difference, "accepted": bool(accepted and abs(difference) <= 1e-6),
                               "transverse_scope": "coarse centerline only; no fine transverse representation outside clipped joint mesh"})
            if not accepted:
                failures.append({"source_edge": list(edge), "fraction_interval": [start, end], "audit": audit})
    nodes = dict(graph["bed_node_heights_m"])
    for record in replacements:
        with np.load(record["path"], allow_pickle=False) as archive:
            for key, value in zip(record["endpoint_keys"], archive["coarse_bed_elevation_m"][[0, -1]]):
                nodes[key] = float(value)
    result = {"accepted": bool(coverage and not failures), "failures": failures,
              "edge_profiles": [record for edge, record in records.items() if edge not in seen] + replacements,
              "bed_node_heights_m": nodes, "fine_fraction_coverage": coverage, "fraction_interfaces": interfaces,
              "extra_registered_receiver_edges": additions,
              "fine_to_coarse_fraction_interfaces_verified": bool(coverage and not failures and all(item["accepted"] for item in interfaces))}
    result["independent_coarse_cold_audit"] = audit_saved_coarse_bed_graph(plan, result)
    result["accepted"] &= result["independent_coarse_cold_audit"]["accepted"]
    result["fine_to_coarse_fraction_interfaces_verified"] &= result["accepted"]
    return result


def audit_saved_coarse_bed_graph(plan, graph):
    """Cold-audit the saved represented profiles against the actual world macro."""
    from terrain_pipeline.hydrology_detail_ridge import continuous_macro_field, stage_fixed_transform

    failures = []
    count = 0
    maximum_source_error = 0.
    for record in graph["edge_profiles"]:
        path = Path(record["path"])
        if file_sha256(path) != record["archive_sha256"]:
            raise ValueError("coarse bed graph archive pin mismatch")
        with np.load(path, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata_json"].item()))
            distance = archive["distance_m"]
            points = archive["points_xz_m"]
            bed = archive["coarse_bed_elevation_m"]
            saved_source = archive["source_macro_surface_m"]
        if metadata["plan_identity"] != plan["identity_sha256"]:
            raise ValueError("coarse bed graph parent identity mismatch")
        positions = np.concatenate((points, (points[:-1] + points[1:]) / 2))
        coords = (positions - plan["origin_xz_m"]) / plan["spacing_m"]
        actual = stage_fixed_transform(continuous_macro_field(plan, coords[:, 0], coords[:, 1]), metadata["frozen_coarse_account_stage_m"])
        represented_source = np.r_[saved_source, (saved_source[:-1] + saved_source[1:]) / 2]
        maximum_source_error = max(maximum_source_error, float(np.max(np.abs(actual - represented_source))))
        first, second = metadata.get("endpoint_keys", metadata["source_edge"])
        physical = metadata["physical_constraints"]
        cut = actual[:len(points)] - bed
        grade = -np.diff(bed) / np.diff(distance)
        if (np.max(np.abs(actual - represented_source)) > 1e-6
                or np.max(cut) > physical["maximum_cut_m"] + 1e-6
                or np.min(cut) < physical["minimum_cut_m"] - 1e-6
                or np.min(grade) < physical["minimum_longitudinal_grade"] - 1e-8
                or abs(bed[0] - graph["bed_node_heights_m"][str(first)]) > 1e-6
                or abs(bed[-1] - graph["bed_node_heights_m"][str(second)]) > 1e-6):
            failures.append({"source_edge": [first, second], "reason": "cold_saved_coarse_profile_rejected"})
        count += len(positions)
    return {"accepted": not failures, "failures": failures, "source_and_midpoint_samples": count,
            "maximum_actual_macro_representation_error_m": maximum_source_error,
            "scope": "cold profiles and every source interval midpoint; each represented bed/source interval is affine after explicit fan and stage breakpoints"}


def audit_basin_continuity(plan_path, reports, output, *, prior_cold_path=None):
    """Cold-check the complete owned DAG and measured fine/coarse end interfaces."""
    from terrain_pipeline.hydrology_planning import validate_plan, _steepest_receivers
    from tools.prepare_hydrology_domains import _read_bed_piece, _artifact_identity
    from terrain_pipeline.channel_geometry import audit_saved_continuous_bed, _mesh_height, represented_section_offsets
    from terrain_pipeline.channel_geometry import _cell_at_point

    plan = load_plan(plan_path)
    validate_plan(plan)
    cached = {}
    if prior_cold_path:
        prior = json.loads(Path(prior_cold_path).read_text(encoding="utf-8"))
        if prior["plan_identity"] != plan["identity_sha256"] or prior["plan_sha256"] != file_sha256(plan_path):
            raise ValueError("cached cold review belongs to another exact plan")
        for item in prior["fine_evidence"]:
            if item["report_sha256"] != file_sha256(item["report_path"]):
                raise ValueError("cached cold fine report changed")
            for pin in item["piece_archive_pins"]:
                if pin["sha256"] != file_sha256(pin["path"]):
                    raise ValueError("cached cold fine geometry changed")
            if item["local_geometry_accepted"] and all(audit.get("accepted") and audit.get("frozen_profile_ceiling_verified") and audit.get("continuous_longitudinal_gradient_verified") for audit in item["cold_geometry_audits"]):
                cached[item["report_sha256"]] = item["cold_geometry_audits"]
    owner = np.asarray(plan["owner_domain_id"]).ravel()
    receiver = np.asarray(plan["receiver"]).ravel()
    ocean = np.asarray(plan["ocean_mask"]).ravel()
    height = np.asarray(plan["height_m"]).ravel()
    river = np.asarray(plan["river_mask"]).ravel()
    legal = {int(cell): domain["kind"] for domain in plan["domains"] for cell in domain["terminal_indices"]}
    terminals = {}
    failures = []
    for start in np.flatnonzero(owner >= 0):
        path, seen = [], set()
        cell = int(start)
        while cell not in terminals:
            if cell in seen:
                failures.append({"cell": int(start), "reason": "cycle"})
                break
            seen.add(cell)
            path.append(cell)
            downstream = int(receiver[cell])
            if ocean[cell]:
                terminals[cell] = ("ocean", cell)
                break
            if downstream < 0:
                if cell not in legal:
                    failures.append({"cell": cell, "reason": "undeclared_terminal"})
                terminals[cell] = (legal.get(cell, "unknown"), cell)
                break
            if downstream >= len(owner) or (not ocean[downstream] and owner[downstream] != owner[start]):
                failures.append({"cell": cell, "reason": "unknown_or_foreign_downstream"})
                break
            cell = downstream
        if cell in terminals:
            for visited in path:
                terminals[visited] = terminals[cell]
    lakes = [domain["lake_terminal_index"] for domain in plan["domains"] if domain["lake_terminal_index"] is not None]
    actual = _steepest_receivers(plan["height_m"], plan["ocean_mask"], lakes)
    unknown_inflows = [int(cell) for cell in np.flatnonzero((owner < 0) & ~ocean)
                       if 0 <= actual[cell] < len(owner) and owner[actual[cell]] >= 0]
    if unknown_inflows:
        failures.append({"reason": "unknown_upstream_inflow", "cells": unknown_inflows})
    fine = []
    reference_nodes = {}
    fine_ports = {}
    fine_port_conflicts = []
    fine_port_meshes = {}
    columns = np.asarray(plan["height_m"]).shape[1]
    for report_path in reports or []:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        if report["plan_identity"] != plan["identity_sha256"]:
            raise ValueError("fine evidence belongs to a different coarse plan")
        declaration_path = Path(report_path).parent.parent / "plan.json"
        declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
        if declaration["identity"] != report["declaration_identity"] or _digest({key: value for key, value in declaration.items() if key != "identity"}) != declaration["identity"]:
            raise ValueError("fine declaration identity mismatch")
        stage = declaration["fixed_lake_level_m"]
        if stage not in reference_nodes:
            reference_nodes[stage] = global_macro_bed_nodes(plan, stage)
        request = json.loads(Path(report["component_request_path"]).read_text(encoding="utf-8"))
        if file_sha256(report["component_request_path"]) != report["component_request_sha256"]:
            raise ValueError("fine component request changed")
        results = [_read_bed_piece(path) for path in report["piece_paths"]]
        with np.load(report["detail_path"], allow_pickle=False) as archive:
            detail = {"metadata": json.loads(str(archive["metadata_json"].item())),
                      "arrays": {key: archive[key] for key in archive.files if key != "metadata_json"}}
        if (_artifact_identity(detail["metadata"], detail["arrays"]) != detail["metadata"]["identity"]
                or detail["metadata"]["identity"] != report["detail_identity"]):
            raise ValueError("fine parent detail identity mismatch")
        pieces = split_frozen_window_component(request)
        if len(results) != len(pieces):
            raise ValueError("complete fine saved piece coverage required")
        local = cached.get(file_sha256(report_path))
        if local is None:
            local = [audit_saved_continuous_bed(result, detail, center_lowest=True, centerline_profile=piece["centerline_profile"])
                     for result, piece in zip(results, pieces)]
        seams = audit_frozen_window_seams(results, request, center_lowest=True)
        interfaces = []
        for endpoint, (node, target) in enumerate(zip(report["source_edge"], (request["bed_target_m"][0], request["bed_target_m"][-1]))):
            point = np.asarray(request["points_xz_m"][0 if endpoint == 0 else -1])
            piece = results[0 if endpoint == 0 else -1]
            arrays = piece["arrays"]
            lookup = {tuple(cell): index for index, cell in enumerate(arrays["cells"])}
            key = _cell_at_point(point, lookup, piece["mesh_origin_xz_m"], piece["fine_spacing_m"])
            represented_height = _mesh_height(point, lookup[key], arrays["vertices_xz_m"], arrays["triangles"], arrays["bed_elevation_m"])
            reference = reference_nodes[stage][node]
            realized = float(represented_height)
            port = fine_ports.setdefault(node, {"realized_center_m": realized, "evidence": []})
            difference = realized - port["realized_center_m"]
            if abs(difference) > 1e-6:
                fine_port_conflicts.append({"coarse_node": node, "center_difference_m": difference})
            port["evidence"].append({"report_path": str(report_path), "piece_identity": piece["identity"], "realized_center_m": realized})
            nodes = arrays["node_xz_m"]
            other = nodes[1] if endpoint == 0 else nodes[-2]
            direction = other - point
            normal = np.array([-direction[1], direction[0]]) / np.linalg.norm(direction)
            half = arrays["width_m"][0 if endpoint == 0 else -1] / 2
            radius = half + (np.sqrt(2.) + 1.) * piece["fine_spacing_m"] + 8.
            fine_port_meshes.setdefault(node, []).append((piece, lookup, point, normal, radius))
            interfaces.append({"coarse_node": node, "coarse_height_m": float(height[node]),
                               "coarse_surface_height_m": float(height[node]), "global_macro_design_bed_cap_m": reference,
                               "fine_bed_target_m": target, "represented_fine_bed_m": float(represented_height), "realized_bed_minus_global_design_cap_m": float(represented_height - reference),
                               "fine_bed_minus_untransformed_coarse_surface_m": float(represented_height - height[node]),
                               "position_xz_m": (np.asarray(plan["origin_xz_m"]) + np.array([node % columns, node // columns]) * plan["spacing_m"]).tolist(),
                               "accepted": False, "status": "awaiting_actual_coarse_profile_port_validation"})
        fine.append({"report_path": str(report_path), "report_sha256": file_sha256(report_path),
                     "source_edge": report["source_edge"], "local_geometry_accepted": all(item["accepted"] and item.get("frozen_profile_ceiling_verified", False) and item.get("continuous_longitudinal_gradient_verified", False) for item in local),
                     "piece_archive_pins": [{"path": path, "sha256": file_sha256(path)} for path in report["piece_paths"]],
                     "cold_geometry_audits": local,
                     "frozen_coarse_account_stage_m": stage,
                     "common_bed_reference_algorithm": "continuous-fan-stage-map-1m-dag-minimum-grade1e-3-depth0.5-v1",
                     "seam_audit": seams, "interfaces": interfaces,
                     "fine_to_coarse_interfaces_accepted": all(item["accepted"] for item in interfaces)})
    represented = {tuple(item["source_edge"]) for item in fine}
    for node, meshes in fine_port_meshes.items():
        if len(meshes) < 2:
            continue
        maximum = 0.
        try:
            crossings = []
            for _, _, point, normal, radius in meshes:
                offsets = [-radius, 0., radius]
                for piece, _, _, _, _ in meshes:
                    offsets.extend(represented_section_offsets(piece, point, normal, radius))
                crossings.append(point + np.asarray(offsets)[:, None] * normal)
            samples = np.unique(np.concatenate(crossings), axis=0)
            for point in samples:
                heights = []
                for piece, lookup, _, _, _ in meshes:
                    arrays = piece["arrays"]
                    key = _cell_at_point(point, lookup, piece["mesh_origin_xz_m"], piece["fine_spacing_m"])
                    heights.append(_mesh_height(point, lookup[key], arrays["vertices_xz_m"], arrays["triangles"], arrays["bed_elevation_m"]))
                maximum = max(maximum, max(heights) - min(heights))
        except (KeyError, ValueError):
            fine_port_conflicts.append({"coarse_node": node, "reason": "fine_junction_mesh_common_support_missing"})
            samples = np.empty((0, 2))
        fine_ports[node]["maximum_shared_full_width_bed_difference_m"] = maximum
        fine_ports[node]["full_width_comparison_samples"] = len(samples)
        fine_ports[node]["full_width_comparison_scope"] = "union of every actual represented triangle crossing on every incident fine cross-section"
        if maximum > 1e-6:
            fine_port_conflicts.append({"coarse_node": node, "maximum_shared_full_width_bed_difference_m": maximum})
    stages = {item["frozen_coarse_account_stage_m"] for item in fine}
    if len(stages) > 1:
        raise ValueError("one frozen coarse-account stage required across fine evidence")
    coarse_bed = prepare_coarse_bed_graph(plan, next(iter(stages)), fine_ports, represented, output) if fine else None
    if coarse_bed is not None:
        coarse_bed["cold_saved_profile_audit"] = audit_saved_coarse_bed_graph(plan, coarse_bed)
        coarse_bed["accepted"] = bool(coarse_bed["accepted"] and coarse_bed["cold_saved_profile_audit"]["accepted"])
    saved_coarse_ports = {}
    for record in coarse_bed["edge_profiles"] if coarse_bed else []:
        with np.load(record["path"], allow_pickle=False) as archive:
            endpoints = archive["coarse_bed_elevation_m"][[0, -1]]
        for node, bed in zip(record["source_edge"], endpoints):
            saved_coarse_ports.setdefault(node, []).append({"path": record["path"], "archive_sha256": record["archive_sha256"], "represented_coarse_bed_m": float(bed)})
    interface_accepted = bool(fine) and not fine_port_conflicts and coarse_bed["accepted"] and all(item["local_geometry_accepted"] and item["seam_audit"]["accepted"] for item in fine)
    for evidence in fine:
        evidence["fine_to_coarse_interfaces_accepted"] = interface_accepted
        for interface in evidence["interfaces"]:
            interface["accepted"] = interface_accepted
            interface["status"] = "shared_realized_coarse_bed_port" if interface_accepted else "actual_coarse_profile_or_fine_geometry_rejected"
            interface["actual_coarse_bed_port_m"] = fine_ports[interface["coarse_node"]]["realized_center_m"]
            interface["saved_incident_coarse_ports"] = saved_coarse_ports.get(interface["coarse_node"], [])
            interface["maximum_saved_coarse_fine_bed_difference_m"] = max((abs(port["represented_coarse_bed_m"] - interface["represented_fine_bed_m"]) for port in interface["saved_incident_coarse_ports"]), default=0.)
    coarse_edges = [[int(cell), int(receiver[cell])] for cell in np.flatnonzero((owner >= 0) & river & (receiver >= 0))]
    result = {"schema": "hydrology-owned-basin-continuity-cold-v1", "plan_path": str(plan_path),
              "plan_sha256": file_sha256(plan_path), "plan_identity": plan["identity_sha256"],
              "coarse_dag_accepted": not failures, "coarse_failures": failures,
              "owned_cell_count": int(np.count_nonzero(owner >= 0)), "traced_owned_cell_count": sum(int(cell) in terminals for cell in np.flatnonzero(owner >= 0)),
              "terminal_paths": [{"kind": kind, "terminal_cell": cell, "owned_path_count": sum(value == (kind, cell) for key, value in terminals.items() if owner[key] >= 0)}
                                 for kind, cell in sorted(set(terminals.values()))],
              "fine_evidence": fine, "coarse_river_edges": coarse_edges,
              "coarse_bed_graph": coarse_bed, "fine_port_conflicts": fine_port_conflicts,
              "coarse_only_river_edges": [edge for edge in coarse_edges if tuple(edge) not in represented],
              "fine_to_coarse_interfaces_accepted": bool(interface_accepted),
              "interface_geometry_scope": "coarse centerline graph shares actual fine center ports; multiple fine products additionally require complete mutual transverse triangle-crossing consistency; coarse transverse sections remain unrefined",
              "scope": "complete owned coarse DAG with explicit measured fine endpoint interfaces; coarse-only edges retain coarse representation",
              "global_hydrology_certified": False, "publishable": False}
    if prior_cold_path:
        result["reused_strong_cold_report_path"] = str(prior_cold_path)
        result["reused_strong_cold_report_sha256"] = file_sha256(prior_cold_path)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "continuity-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def audit_seam_supplement(cold_review_path, output):
    """Reuse pinned strong geometry evidence while independently replaying all seams."""
    from tools.prepare_hydrology_domains import _read_bed_piece

    prior = json.loads(Path(cold_review_path).read_text(encoding="utf-8"))
    if prior["schema"] != "hydrology-owned-basin-continuity-cold-v1":
        raise ValueError("complete owned-basin cold review required")
    if file_sha256(prior["plan_path"]) != prior["plan_sha256"]:
        raise ValueError("cold parent plan changed")
    for record in prior["coarse_bed_graph"]["edge_profiles"]:
        if file_sha256(record["path"]) != record["archive_sha256"]:
            raise ValueError("cold coarse profile changed")
    reviews = []
    for evidence in prior["fine_evidence"]:
        if not evidence["local_geometry_accepted"] or not all(audit["accepted"] and audit.get("continuous_longitudinal_gradient_verified") and audit.get("frozen_profile_ceiling_verified") for audit in evidence["cold_geometry_audits"]):
            raise ValueError("strong triangle-gradient and frozen-profile cold geometry evidence required")
        if file_sha256(evidence["report_path"]) != evidence["report_sha256"]:
            raise ValueError("cold fine report changed")
        report = json.loads(Path(evidence["report_path"]).read_text(encoding="utf-8"))
        if file_sha256(report["component_request_path"]) != report["component_request_sha256"]:
            raise ValueError("cold fine request changed")
        if [item["path"] for item in evidence["piece_archive_pins"]] != report["piece_paths"]:
            raise ValueError("cold piece pin coverage differs")
        for pin in evidence["piece_archive_pins"]:
            if file_sha256(pin["path"]) != pin["sha256"]:
                raise ValueError("cold fine geometry changed")
        request = json.loads(Path(report["component_request_path"]).read_text(encoding="utf-8"))
        results = [_read_bed_piece(path) for path in report["piece_paths"]]
        audit = audit_frozen_window_seams(results, request, center_lowest=True)
        reviews.append({"source_edge": report["source_edge"], "seam_audit": audit})
    accepted = bool(reviews and prior["coarse_dag_accepted"] and prior["coarse_bed_graph"]["accepted"] and prior["fine_to_coarse_interfaces_accepted"]
                    and all(item["seam_audit"]["accepted"] and item["seam_audit"].get("continuous_affine_trace_verified", False) for item in reviews))
    result = {"schema": "hydrology-owned-basin-complete-seam-supplement-v1", "accepted": accepted,
              "plan_identity": prior["plan_identity"], "parent_cold_review_path": str(cold_review_path),
              "parent_cold_review_sha256": file_sha256(cold_review_path), "fine_seam_reviews": reviews,
              "scope": "same fixed fine geometry, coarse graph and ports as parent cold review; replace nine-offset seam sampling with complete two-sided represented affine trace and banks",
              "global_hydrology_certified": False, "publishable": False}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "seam-supplement.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--window-report", type=Path, action="append")
    parser.add_argument("--source-declaration", type=Path)
    parser.add_argument("--fixed-lake-level-m", type=float)
    parser.add_argument("--cold-continuity-report", type=Path)
    parser.add_argument("--generation-report", type=Path)
    parser.add_argument("--joint-cold-report", type=Path)
    parser.add_argument("--tributary-sidecar", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--bed-version",
        choices=("v5-continuous-center-floor", "v7-shared-sections"),
        default="v5-continuous-center-floor",
    )
    parser.add_argument(
        "--action",
        choices=("freeze", "sources", "projections", "beds", "macro-valley", "continuity", "rebind", "seam-cold", "fraction-interfaces"),
        default="freeze",
    )
    args = parser.parse_args()
    if args.action == "fraction-interfaces":
        if not all((args.plan, args.cold_continuity_report, args.generation_report, args.joint_cold_report, args.tributary_sidecar)):
            parser.error("fraction-interfaces needs plan, cold continuity, generation, joint cold and tributary sidecar reports")
        print(json.dumps(audit_confluence_fraction_interfaces(args.plan, args.cold_continuity_report,
            args.generation_report, args.joint_cold_report, args.tributary_sidecar, args.output)))
    elif args.action == "seam-cold":
        if not args.cold_continuity_report:
            parser.error("seam-cold needs --cold-continuity-report")
        print(json.dumps(audit_seam_supplement(args.cold_continuity_report, args.output)))
    elif args.action == "rebind":
        if not args.plan or not args.source_declaration or args.fixed_lake_level_m is None:
            parser.error("rebind needs --plan, --source-declaration and --fixed-lake-level-m")
        result = rebind_declaration(args.source_declaration, args.plan, args.output, args.fixed_lake_level_m, args.bed_version)
        print(json.dumps({key: result[key] for key in ("identity", "plan_identity", "fixed_lake_level_m")}))
    elif args.action == "continuity":
        if not args.plan:
            parser.error("continuity needs --plan")
        result = audit_basin_continuity(args.plan, args.window_report, args.output, prior_cold_path=args.cold_continuity_report)
        print(json.dumps(result))
    elif args.action == "freeze":
        if not args.plan or not args.window_report:
            parser.error("freeze needs --plan and explicit accepted --window-report")
        result = freeze(
            args.plan, args.window_report, args.output, bed_version=args.bed_version
        )
        print(
            json.dumps(
                {
                    key: result[key]
                    for key in (
                        "identity",
                        "source_missing_count",
                        "selected_graph_edge_count",
                    )
                }
            )
        )
    else:
        declaration = json.loads((args.output / "plan.json").read_text())
        if args.action == "macro-valley":
            try:
                result = prepare_finite_mouth(
                    load_plan(declaration["plan_path"]),
                    declaration,
                    declaration["requests"][0],
                    args.output,
                    declaration["baseline_node_provenance"],
                    macro_valley=True,
                )
            except ProjectionError as error:
                result = {
                    "status": "rejected",
                    "reason": str(error),
                    "diagnostics": error.diagnostics,
                    "global_hydrology_certified": False,
                    "publishable": False,
                }
        else:
            result = execute(declaration, args.output, args.action)
        (args.output / (args.action + "-result.json")).write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(json.dumps(result))


if __name__ == "__main__":
    main()
