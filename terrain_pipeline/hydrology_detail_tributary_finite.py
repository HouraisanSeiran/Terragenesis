"""Explicit finite tributary projection, independent of canonical core acceptance.

The saved original97 receives one native cell of real computational support.
All outer two rows/columns stay on the existing world macro function. The
interior LP keeps the original source, owner, D8 and frozen river constraints.
This never certifies a core256 seam, exterior fine routing or global hydrology.
"""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np

ALGORITHM = "finite99-local-tributary-constrained-projection-v1"
NETWORK_ALGORITHM = "finite99-frozen-network-constrained-projection-v1"
TARGET_NETWORK_ALGORITHM = "finite99-frozen-network-target-macro-rank-projection-v2"
TARGET_LOCAL_ALGORITHM = "finite99-local-tributary-target-macro-rank-projection-v2"
CHANNEL_FEASIBILITY_POLICY = "frozen-channel-feasibility-v1"
CHANNEL_NETWORK_ALGORITHM = "finite99-frozen-network-channel-feasibility-projection-v3"
HARMONIC_TARGET_POLICY = "harmonic-boundary-residual-v1"
HARMONIC_CHANNEL_ALGORITHM = "finite99-frozen-network-harmonic-channel-projection-v4"
HARMONIC_CHANNEL_TARGET_WITNESS_ALGORITHM = "finite99-frozen-network-harmonic-channel-target-witness-projection-v5"
TARGET_GRADIENT_POLICY = "target-neighbor-gradient-l1-v1"
GRADIENT_NETWORK_ALGORITHM = "finite99-frozen-network-harmonic-channel-target-gradient-projection-v6"


def harmonic_boundary_target(original_td_m, macro_height_m, pinned_mask):
    """Extend macro-minus-TD boundary displacement with the discrete Laplacian."""
    from scipy import sparse
    from scipy.sparse.linalg import spsolve
    raw, macro, pinned = np.asarray(original_td_m, float), np.asarray(macro_height_m, float), np.asarray(pinned_mask, bool)
    if raw.ndim != 2 or raw.shape != macro.shape or raw.shape != pinned.shape or not np.isfinite(raw).all() or not np.isfinite(macro).all():
        raise ValueError("aligned finite harmonic target arrays required")
    if not (pinned[0].all() and pinned[-1].all() and pinned[:, 0].all() and pinned[:, -1].all()):
        raise ValueError("harmonic target requires a pinned outer boundary")
    ids = np.full(raw.shape, -1, int)
    ids[~pinned] = np.arange(np.sum(~pinned))
    correction = macro - raw
    rows, cols, values = [], [], []
    rhs = np.zeros(np.sum(~pinned))
    for z, x in np.argwhere(~pinned):
        index = ids[z, x]
        rows.append(index)
        cols.append(index)
        values.append(4.)
        for dz, dx in ((-1, 0), (0, -1), (0, 1), (1, 0)):
            nz, nx = z + dz, x + dx
            if pinned[nz, nx]:
                rhs[index] += correction[nz, nx]
            else:
                rows.append(index)
                cols.append(ids[nz, nx])
                values.append(-1.)
    if len(rhs):
        matrix = sparse.coo_matrix((values, (rows, cols)), shape=(len(rhs), len(rhs))).tocsr()
        correction[~pinned] = spsolve(matrix, rhs)
    target = raw + correction
    target[pinned] = macro[pinned]
    return target


def audit_finite_projection(result, expected_arrays, recipe, constraints, channel_constraints=None):
    from terrain_pipeline.hydrology_detail import _steepest_receivers
    from terrain_pipeline.hydrology_detail_projection import audit_neighbor_slopes
    from tools.prepare_hydrology_domains import _artifact_identity
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("identity") != _artifact_identity(metadata, arrays) or any(metadata.get(key) != value for key, value in recipe.items()):
        raise ValueError("finite tributary saved identity or frozen recipe differs")
    if any(not np.array_equal(arrays[key], value) for key, value in expected_arrays.items()):
        raise ValueError("finite tributary saved source, owner or boundary differs")
    height, raw = arrays["projection_height_m"], arrays["original_td_m"]
    if height.shape != (99, 99) or not np.isfinite(height).all():
        raise ValueError("finite tributary saved elevation invalid")
    delta = height - raw
    config = recipe["config"]
    if np.abs(delta).max() > config["macro_max_abs_m"] + 1e-6 or np.abs(delta).sum() * 900 > config["macro_absolute_volume_m3"] + 1e-6:
        raise ValueError("finite tributary saved full-support budget exceeded")
    pinned = arrays["pinned_mask"]
    if np.max(np.abs(height[pinned] - arrays["macro_height_m"][pinned]), initial=0) > 1e-8:
        raise ValueError("finite tributary saved world boundary differs")
    routing_frame = {"origin_xz_m": recipe["support_origin_xz_m"], "world_seed": recipe["world_seed"]}
    slope_audit = audit_neighbor_slopes(height, pinned, 30, maximum_modifiable_slope=config["max_slope_m_per_m"], **routing_frame)
    fixed_slopes = slope_audit["fixed_world_boundary_actual_slope_diagnostics"]
    if any(record["fixed_pair_above_internal_limit_count"] for record in fixed_slopes):
        raise ValueError("finite tributary saved strict neighboring slope rejected")
    maximum_slope = max(slope_audit["maximum_modifiable_neighbor_slope_m_per_m"],
        max(record["maximum_actual_fixed_slope_m_per_m"] for record in fixed_slopes))
    actual = _steepest_receivers(height, 30, **routing_frame)
    destination = np.maximum(actual, 0)
    core = arrays["core_mask"]
    owner = arrays["owner_domain_id"]
    if recipe.get("window", {}).get("kind") == "mouth":
        ocean_stencil = arrays["ocean_stencil_mask"]
        if np.any(height[arrays["ocean_mask"]] > -1e-6 + 1e-8) or np.any(height[ocean_stencil & ~arrays["ocean_mask"]] < -1e-8):
            raise ValueError("finite mouth saved sea-stage bounds rejected")
    active = core & ~arrays.get("terminal_mask", np.zeros(height.shape, bool))
    crosses = active & ~arrays.get("ocean_mask", np.zeros(height.shape, bool)).ravel()[destination] & (owner != owner.ravel()[destination])
    if not np.array_equal(actual, arrays["actual_receiver"]) or np.any(active & (actual < 0)) or np.any(crosses):
        raise ValueError("finite tributary saved actual graph or owner rejected")
    residual = np.sum(constraints["coefficients"] * height.ravel()[constraints["columns"]], axis=1) - constraints["rhs"]
    if residual.max(initial=0) > 1e-7:
        raise ValueError("finite tributary saved continuous frozen river descent rejected")
    channel_audit = {}
    if recipe.get("channel_feasibility_policy") == CHANNEL_FEASIBILITY_POLICY:
        if channel_constraints is None or metadata.get("frozen_channel_feasibility_constraints") != channel_constraints["metadata"]:
            raise ValueError("finite channel feasibility audit requires regenerated frozen rows")
        channel_residual = np.sum(channel_constraints["coefficients"] * height.ravel()[channel_constraints["columns"]], axis=1) - channel_constraints["rhs"]
        if channel_residual.max(initial=0) > 1e-7:
            raise ValueError("finite saved channel feasibility rejected")
        channel_audit = {"maximum_channel_feasibility_residual_m": float(channel_residual.max(initial=0)),
                         "channel_sampled_coverage": channel_constraints["metadata"]["coverage"],
                         "channel_unsupported_sections": channel_constraints["metadata"]["unsupported_sections"],
                         "channel_constraint_count": len(channel_residual)}
    return {"status": "cold_verified_finite_local_projection", "macro_max_abs_m": float(np.abs(delta).max()),
            "macro_absolute_volume_m3": float(np.abs(delta).sum() * 900), "maximum_river_derivative_residual_m_per_m": float(residual.max(initial=0)),
            "maximum_actual_neighbor_slope_m_per_m": maximum_slope,
            "canonical_core_certified": False, "exterior_fine_routing_certified": False, **channel_audit}


def prepare_finite_tributary_source(plan, output, budget, lake_level_m, declaration, *, window_kind="confluence", frozen_network=False,
                                   witness_policy="macro-steepest-v1", channel_feasibility_policy=None, target_policy=None,
                                   gradient_policy=None):
    from diffusion.physical_config import PhysicalGenerationConfig
    from terrain_pipeline.hydrology_detail import _coordinates, _interpolate, file_sha256, load_raw_td, required_td_nodes
    from terrain_pipeline.hydrology_detail_conditioning import ResourcePhysicalTerrainDiffusionBackend
    from terrain_pipeline.hydrology_detail_projection import ProjectionConfig, project_arrays, frozen_river_derivative_constraints, MACRO_WITNESS_POLICY, TARGET_WITNESS_POLICY
    from terrain_pipeline.hydrology_detail_ridge import continuous_macro_field, stage_fixed_transform
    from terrain_pipeline.td_source import CanonicalTDSource
    from terrain_pipeline.hydrology_detail_tributaries import validate_local_tributary_sidecar
    from terrain_pipeline.runoff import LakeGeometry as LakeGeometry
    from tools.prepare_hydrology_domains import CANONICAL_CACHE, _artifact_identity, _json_new, projection_source_declaration

    output = Path(output)
    if witness_policy not in (MACRO_WITNESS_POLICY, TARGET_WITNESS_POLICY):
        raise ValueError("explicit finite projection witness policy required")
    if channel_feasibility_policy not in (None, CHANNEL_FEASIBILITY_POLICY):
        raise ValueError("explicit finite channel feasibility policy required")
    if channel_feasibility_policy is not None and (not frozen_network or
            (witness_policy == TARGET_WITNESS_POLICY and target_policy != HARMONIC_TARGET_POLICY)):
        raise ValueError("channel candidate requires frozen network and an explicit harmonic target for target-guided witnesses")
    if target_policy not in (None, HARMONIC_TARGET_POLICY):
        raise ValueError("explicit finite target policy required")
    if target_policy is not None and channel_feasibility_policy != CHANNEL_FEASIBILITY_POLICY:
        raise ValueError("harmonic candidate requires explicit channel feasibility policy")
    if gradient_policy not in (None, TARGET_GRADIENT_POLICY):
        raise ValueError("explicit finite target gradient policy required")
    if gradient_policy is not None and (target_policy != HARMONIC_TARGET_POLICY or witness_policy != TARGET_WITNESS_POLICY):
        raise ValueError("gradient candidate requires explicit harmonic target and target-guided witness")
    window = projection_source_declaration(plan, output, window_kind)["windows"][0]
    if frozen_network:
        if window_kind not in ("river", "confluence", "mouth"):
            raise ValueError("finite frozen network source supports river/confluence/mouth only")
        cell = window["coarse_cell"]
        receiver, owners = plan["receiver"].ravel(), plan["owner_domain_id"].ravel()
        owner_id = int(owners[cell])
        domain = next(domain for domain in plan["domains"] if domain["domain_id"] == owner_id)
        if domain["kind"] != "coastal":
            raise ValueError("finite frozen network source requires a coastal owner")
        if window_kind == "confluence":
            incoming = np.flatnonzero((receiver == cell) & (owners == owner_id) & plan["river_mask"].ravel())
            if len(incoming) < 2 or receiver[cell] < 0:
                raise ValueError("fixed confluence needs all true registered incoming arms and outgoing receiver")
            edges = [[int(value), int(cell)] for value in incoming] + [[int(cell), int(receiver[cell])]]
        else:
            edges = [window["selection_edge_cell_ids"]]
        for first, second in edges:
            marine_receiver = window_kind == "mouth" and bool(plan["ocean_mask"].ravel()[second]) and second in domain["terminal_indices"]
            if receiver[first] != second or owners[first] != owner_id or (owners[second] != owner_id and not marine_receiver):
                raise ValueError("finite network edges must be true same-owner frozen receivers")
        declaration = {"owner_domain_id": owner_id, "parent_plan_identity": plan["identity_sha256"],
                       "window_kind": window_kind, "source_edges": edges}
        declaration["identity_sha256"] = _artifact_identity(declaration, {})
        source_edges = edges
        mask = np.zeros(plan["height_m"].shape, bool)
    else:
        if window_kind != "confluence":
            raise ValueError("legacy tributary source supports confluence only")
        inland = next(domain for domain in plan["domains"] if domain["kind"] == "inland")
        mask = LakeGeometry(plan["height_m"], plan["owner_domain_id"], inland, plan["spacing_m"] ** 2).mask
        validate_local_tributary_sidecar(plan, declaration, highest_lake_level_m=lake_level_m, lake_mask=mask)
        source_edges = window["declared_source_edge_cell_ids"]
    detail_declaration = json.loads((output / window_kind / "detail-plan.json").read_text(encoding="utf-8"))
    if (detail_declaration["budget"] != asdict(budget) or detail_declaration["budget_status"] != "frozen_after_calibration"
            or (not frozen_network and window.get("local_tributary_sidecar_identity_sha256") != declaration["identity_sha256"])):
        raise ValueError("finite tributary frozen budget or selected sidecar differs")
    raw97_path = output / window_kind / (window_kind + "-original-td.npz")
    raw97, metadata = load_raw_td(raw97_path, raw97_path.with_suffix(".sha256").read_text(encoding="ascii").strip())
    generation = metadata["provenance"]["generation_metadata"]
    if generation["native_origin"] != window["native_origin_xz"] or generation["shape"] != [97, 97] or int(generation["seed"]) != plan["seed"]:
        raise ValueError("finite tributary original source differs from frozen window")
    backend = ResourcePhysicalTerrainDiffusionBackend(PhysicalGenerationConfig(), "light")
    def forbidden(*args, **kwargs):
        raise ValueError("finite tributary source assembly forbids model inference")
    backend.generate = forbidden
    canonical = CanonicalTDSource(backend, CANONICAL_CACHE)
    if canonical.identity != generation["identity"]:
        canonical.close()
        raise ValueError("finite tributary canonical source identity differs")
    native_origin = np.asarray(window["native_origin_xz"]) - 1
    anchor_records = {}
    anchor_folder = output / "canonical-projection-td-nodes"
    if frozen_network:
        anchor_folder = output / window_kind / "td-coarse-node-cache"
    for path in anchor_folder.glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if frozen_network:
            record = dict(record, coarse_node_key=path.stem.replace("-", ":"))
        anchor_records[record["coarse_node_key"]] = record
    required_nodes = required_td_nodes(plan, {"origin_xz_m": (native_origin * 30).tolist(), "shape": [99, 99], "spacing_m": 30})
    try:
        raw, climate, provenance = canonical.generate(plan["seed"], int(native_origin[0]), int(native_origin[1]), 99)
        for cz, cx in required_nodes:
            record = anchor_records.get(f"{cz}:{cx}")
            if record is None:
                raise ValueError("finite tributary required genuine coarse anchor missing")
            world = np.asarray(plan["origin_xz_m"]) + np.array([cx, cz]) * plan["spacing_m"]
            native = world / 30.
            floor = np.floor(native).astype(int)
            native_height, _, anchor_provenance = canonical.generate(plan["seed"], int(floor[0]), int(floor[1]), 2)
            wx, wz = native - floor
            sampled = (1 - wz) * ((1 - wx) * native_height[0, 0] + wx * native_height[0, 1]) + wz * ((1 - wx) * native_height[1, 0] + wx * native_height[1, 1])
            normalized_saved = json.loads(json.dumps(record["generation_metadata"]))
            normalized_current = json.loads(json.dumps(anchor_provenance))
            normalized_saved.pop("canonical_cache_root", None)
            normalized_current.pop("canonical_cache_root", None)
            if record["elevation_m"] != float(sampled) or normalized_saved != normalized_current or record["native_elevation_m"] != native_height.tolist():
                raise ValueError("finite tributary anchor differs from genuine pinned TD")
    finally:
        canonical.close()
    if not np.array_equal(raw[1:-1, 1:-1], raw97["arrays"]["height_m"]):
        raise ValueError("finite99 genuine pixels differ from immutable original97")
    origin = (native_origin * 30).tolist()
    x, z = _coordinates(plan, origin, raw.shape, 30)
    macro = continuous_macro_field(plan, x, z, validate_query_support_only=True) if frozen_network else continuous_macro_field(plan, x, z)
    if lake_level_m is not None:
        macro = stage_fixed_transform(macro, lake_level_m)
    owner = plan["owner_domain_id"][np.rint(z).astype(int), np.rint(x).astype(int)].copy()
    terminal = np.zeros(raw.shape, bool)
    if frozen_network and window_kind == "mouth":
        from scipy.ndimage import distance_transform_edt
        if np.any(owner < -1):
            raise ValueError("finite mouth support contains genuine unknown ownership")
        coarse = np.asarray(plan["owner_domain_id"])
        coastal_ids = [domain["domain_id"] for domain in plan["domains"] if domain["kind"] == "coastal"]
        nearest = distance_transform_edt(~np.isin(coarse, coastal_ids), return_distances=False, return_indices=True)
        ocean_stencil = _interpolate(np.asarray(plan["ocean_mask"], float), x, z) > 0
        terminal = ocean_stencil & (macro < 0)
        extension = (owner == -1) & ~terminal
        owner[extension] = coarse[nearest[0], nearest[1]][np.rint(z).astype(int), np.rint(x).astype(int)][extension]
        owner[terminal] = -1
    wet_lake = np.zeros(raw.shape, bool) if frozen_network else ((_interpolate(mask.astype(float), x, z) > 0)
        & (owner == inland["domain_id"]) & (macro < lake_level_m))
    if np.any(~terminal & (owner != declaration["owner_domain_id"])) or np.any(wet_lake):
        raise ValueError("finite tributary support must remain one dry declared coastal owner")
    baseline = np.asarray(plan["original_height_m"], float).copy()
    for record in anchor_records.values():
        cz, cx = map(int, record["coarse_node_key"].split(":"))
        baseline[cz, cx] = record["elevation_m"]
    rows, cols = np.indices(raw.shape)
    distance = np.minimum.reduce([rows, cols, 98 - rows, 98 - cols]) * 30.
    pinned = distance <= 30.
    retained = np.clip((distance - 30.) / 1000., 0, 1)
    retained = retained * retained * (3 - 2 * retained)
    target = macro + retained * (raw - _interpolate(baseline, x, z))
    if target_policy == HARMONIC_TARGET_POLICY:
        target = harmonic_boundary_target(raw, macro, pinned)
    constraints = frozen_river_derivative_constraints(plan, raw.shape, origin, 30, terminal,
        additional_source_edges=source_edges)
    channel_constraints = None
    if channel_feasibility_policy is not None:
        from terrain_pipeline.hydrology_macro_channel_feasibility import frozen_river_channel_feasibility_constraints
        channel_constraints = frozen_river_channel_feasibility_constraints(plan, raw.shape, origin, 30, terminal,
            source_edges=source_edges, owner_domain_id=owner, ocean_mask=terminal, pinned_mask=pinned)
    config = ProjectionConfig(macro_max_abs_m=budget.macro_max_abs_m,
        macro_absolute_volume_m3=budget.macro_absolute_volume_m3 * 99 ** 2 / 97 ** 2)
    recipe = {"algorithm": NETWORK_ALGORITHM if frozen_network else ALGORITHM, "plan_identity": plan["identity_sha256"],
        "sidecar_identity": declaration["identity_sha256"], "window": window, "support_origin_xz_m": origin,
        "support_shape": [99, 99], "budget": asdict(budget), "config": asdict(config),
        "world_seed": int(plan["seed"]), "routing": "irregular-graph-v1",
        "fixed_lake_level_m": lake_level_m, "source_provenance": provenance,
        "boundary": "two outer native rows fixed to world continuous_macro_field and stage_fixed_transform",
        "scope": "original97 local tributary only; full canonical core256 rejected; exterior fine routing unverified"}
    if frozen_network:
        recipe.update(network_declaration=declaration,
                      macro_corner_validation="only fan corners actually used by finite99 query; no global field certificate",
                      stage_policy="explicit frozen stage or no lake-stage warp for a wholly coastal finite support",
                      scope="fixed original97 frozen network finite99 support; canonical256 seams and exterior routing unverified")
    if witness_policy == TARGET_WITNESS_POLICY:
        recipe.update(algorithm=TARGET_NETWORK_ALGORITHM if frozen_network else TARGET_LOCAL_ALGORITHM,
                      witness_policy=witness_policy)
    if channel_constraints is not None:
        recipe.update(algorithm=CHANNEL_NETWORK_ALGORITHM, channel_feasibility_policy=channel_feasibility_policy,
                      frozen_channel_feasibility_constraints=channel_constraints["metadata"])
    if target_policy is not None:
        recipe.update(algorithm=HARMONIC_CHANNEL_ALGORITHM, target_policy=target_policy)
        if witness_policy == TARGET_WITNESS_POLICY:
            recipe["algorithm"] = HARMONIC_CHANNEL_TARGET_WITNESS_ALGORITHM
    if gradient_policy is not None:
        recipe.update(algorithm=GRADIENT_NETWORK_ALGORITHM, gradient_policy=gradient_policy)
    if frozen_network and window_kind == "mouth":
        recipe["marine_support_policy"] = "prepare_finite_mouth rules: interpolated frozen ocean stencil and macro<0; nearest registered coastal owner extension; nonmarine stencil lower bound sea0; unknown refused"
    recipe = json.loads(json.dumps(recipe, allow_nan=False))
    directory = output / ("finite-network-" + window_kind + "-v1" if frozen_network else "finite-local-tributary-v1")
    if witness_policy == TARGET_WITNESS_POLICY:
        directory = output / ("finite-network-" + window_kind + "-target-witness-v2" if frozen_network else "finite-local-tributary-target-witness-v2")
    if channel_constraints is not None:
        directory = output / ("finite-network-" + window_kind + "-channel-feasibility-v3")
    if target_policy is not None:
        directory = output / ("finite-network-" + window_kind + "-harmonic-channel-v4")
        if witness_policy == TARGET_WITNESS_POLICY:
            directory = output / ("finite-network-" + window_kind + "-harmonic-channel-target-witness-v5")
    if gradient_policy is not None:
        directory = output / ("finite-network-" + window_kind + "-harmonic-channel-target-gradient-v6")
    directory.mkdir(exist_ok=True)
    recipe_path = directory / "declaration.json"
    if recipe_path.exists():
        if json.loads(recipe_path.read_text(encoding="utf-8")) != recipe:
            raise ValueError("immutable finite tributary projection declaration differs")
    else:
        _json_new(recipe_path, recipe)
    projection_path = directory / "projection99.npz"
    if projection_path.exists():
        with np.load(projection_path, allow_pickle=False) as saved:
            result = {"metadata": json.loads(str(saved["metadata_json"].item())),
                      "arrays": {key: saved[key].copy() for key in saved.files if key != "metadata_json"}}
    else:
        low = None
        if frozen_network and window_kind == "mouth":
            low = np.full(raw.shape, -np.inf)
            low[ocean_stencil & ~terminal] = 0
        result = project_arrays(raw, target, macro, owner, terminal, terminal, ~pinned, pinned,
            spacing_m=30, origin_xz_m=origin, world_seed=int(plan["seed"]), config=config, frozen_river_constraints=constraints, lower_height_m=low,
            witness_policy=witness_policy, frozen_channel_constraints=channel_constraints, gradient_policy=gradient_policy)
        if frozen_network and window_kind == "mouth":
            result["arrays"]["ocean_stencil_mask"] = ocean_stencil
        result["metadata"].update(recipe, status="accepted_finite_local_projection", canonical_core_certified=False,
            model_inference_run=False, source_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        result["metadata"]["identity"] = _artifact_identity(result["metadata"], result["arrays"])
        with projection_path.open("xb") as stream:
            np.savez_compressed(stream, **result["arrays"], metadata_json=np.array(json.dumps(result["metadata"], allow_nan=False)))
    expected = {"original_td_m": raw, "target_height_m": target, "macro_height_m": macro,
        "owner_domain_id": owner, "ocean_mask": terminal, "terminal_mask": terminal, "core_mask": ~pinned, "pinned_mask": pinned}
    if frozen_network and window_kind == "mouth":
        expected["ocean_stencil_mask"] = ocean_stencil
    audit = audit_finite_projection(result, expected, recipe, constraints, channel_constraints)
    audit_path = directory / "cold-audit-strict-neighbor-slope-v2.json"
    if not audit_path.exists():
        _json_new(audit_path, audit)
    raw99_path = directory / "original99.npz"
    pin = raw99_path.with_suffix(".sha256")
    if not raw99_path.exists():
        with raw99_path.open("xb") as stream:
            np.savez_compressed(stream, elevation_m=raw, climate=climate, metadata_json=np.array(json.dumps(provenance, allow_nan=False)))
        pin.write_text(file_sha256(raw99_path), encoding="ascii")
    _, raw99_metadata = load_raw_td(raw99_path, pin.read_text(encoding="ascii").strip())
    parent = {"identity": result["metadata"]["identity"], "path": str(projection_path),
              "archive_sha256": file_sha256(projection_path), "scope": recipe["scope"]}
    return window, metadata["provenance"], raw99_metadata["provenance"], result["arrays"], [parent]
