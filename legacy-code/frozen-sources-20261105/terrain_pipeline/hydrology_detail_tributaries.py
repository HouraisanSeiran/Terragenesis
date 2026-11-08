"""Explicit bounded local tributary declarations on an immutable coarse receiver.

These declarations are geometry requests, not additions to the registered river
mask, changed river-source thresholds, or accepted fine-water geometry.
"""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np


ALGORITHM = "frozen-local-tributary-confluence-v1"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _array_digest(value):
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode())
    digest.update(array.dtype.str.encode())
    digest.update(array.tobytes())
    return digest.hexdigest()


def freeze_local_tributary_confluence(plan, *, junction_id, incoming_ids, highest_lake_level_m, lake_mask):
    """Freeze one explicit natural two-in/one-out coastal receiver junction."""
    if not isinstance(plan.get("identity_sha256"), str) or not plan["identity_sha256"]:
        raise ValueError("immutable parent plan identity required")
    height = np.asarray(plan["height_m"])
    owner = np.asarray(plan["owner_domain_id"])
    receiver = np.asarray(plan["receiver"])
    registered = np.asarray(plan["river_mask"])
    accumulation = np.asarray(plan["accumulation_area_m2"])
    mask = np.asarray(lake_mask)
    if (height.ndim != 2 or any(a.shape != height.shape for a in (owner, receiver, registered, accumulation, mask))
            or registered.dtype != bool or mask.dtype != bool or receiver.dtype.kind not in "iu"
            or not np.isfinite(height).all() or not np.isfinite(accumulation).all() or np.any(accumulation < 0)):
        raise ValueError("aligned finite frozen receiver/owner/area/river/lake arrays required")
    if not np.isfinite(highest_lake_level_m):
        raise ValueError("explicit verified finite highest lake level required")
    if isinstance(junction_id, bool) or not isinstance(junction_id, (int, np.integer)):
        raise ValueError("explicit integer coarse junction required")
    incoming = np.asarray(incoming_ids)
    if incoming.shape != (2,) or incoming.dtype.kind not in "iu" or len(set(incoming.tolist())) != 2:
        raise ValueError("exactly two distinct explicit coarse incoming ids required")
    junction = int(junction_id)
    upstream = sorted(int(value) for value in incoming)
    flat_height, flat_owner, flat_receiver = height.ravel(), owner.ravel(), receiver.ravel()
    flat_registered, flat_area = registered.ravel(), accumulation.ravel()
    cells = height.size
    if any(index < 0 or index >= cells for index in upstream + [junction]):
        raise ValueError("coarse tributary index out of range")
    downstream = int(flat_receiver[junction])
    if downstream < 0 or downstream >= cells:
        raise ValueError("junction requires a real outgoing receiver")
    domain_id = int(flat_owner[junction])
    domains = [domain for domain in plan["domains"] if domain["domain_id"] == domain_id]
    if len(domains) != 1 or domains[0]["kind"] != "coastal":
        raise ValueError("first local tributary declaration requires a registered coastal catchment")
    domain = domains[0]
    actual_incoming = np.flatnonzero((flat_receiver == junction) & (flat_owner == domain_id)).tolist()
    if actual_incoming != upstream:
        raise ValueError("explicit incoming edges are not the true two-in receiver junction")
    edges = [[upstream[0], junction], [upstream[1], junction], [junction, downstream]]
    wet = mask.ravel() & (flat_height < highest_lake_level_m)
    for first, second in edges:
        if flat_receiver[first] != second or flat_owner[first] != domain_id or flat_owner[second] != domain_id:
            raise ValueError("tributary edge crosses owner or is not an actual frozen receiver")
        if flat_height[first] <= flat_height[second]:
            raise ValueError("tributary receiver edge is not strictly descending")
        if wet[first] or wet[second]:
            raise ValueError("tributary confluence is submerged in the verified highest wet lake")
    # Every downstream step is bounded, owner-consistent and reaches the already
    # registered marine terminal. A window edge is never treated as an outlet.
    chain, seen = [], set()
    index = junction
    ocean = np.asarray(plan["ocean_mask"])
    if ocean.shape != height.shape or ocean.dtype != bool:
        raise ValueError("frozen marine identity mask required")
    for unused_step in range(cells):
        if index < 0 or index >= cells or index in seen:
            raise ValueError("cyclic or out-of-range tributary terminal trace")
        seen.add(index)
        chain.append(index)
        if wet[index]:
            raise ValueError("tributary downstream trace enters verified wet lake")
        if flat_owner[index] == -1:
            if not ocean.ravel()[index] or flat_height[index] >= 0 or index not in domain["terminal_indices"]:
                raise ValueError("tributary trace lacks an already registered marine terminal")
            if flat_receiver[index] != -1:
                raise ValueError("registered marine terminal must terminate the frozen receiver")
            break
        if flat_owner[index] != domain_id:
            raise ValueError("tributary trace enters another or unknown owner")
        other = int(flat_receiver[index])
        if other < 0 or other >= cells or flat_height[index] <= flat_height[other]:
            raise ValueError("tributary downstream trace lacks a descending registered terminal path")
        index = other
    else:
        raise ValueError("tributary terminal trace exceeds receiver-size bound")
    spacing = float(plan["spacing_m"])
    threshold = float(plan["river_threshold_area_m2"])
    origin = np.asarray(plan["origin_xz_m"], dtype=float)
    if spacing <= 0 or threshold <= 0 or not np.isfinite([spacing, threshold]).all() or origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("finite physical grid and unchanged river threshold required")
    columns = height.shape[1]
    records = []
    for first, second in edges:
        is_registered = bool(flat_registered[first])
        if is_registered != bool(flat_area[first] >= threshold):
            raise ValueError("frozen river mask disagrees with the frozen accumulation threshold")
        records.append({"source_edge": [first, second], "owner_domain_id": domain_id,
                        "start_world_xz_m": (origin + [first % columns * spacing, first // columns * spacing]).tolist(),
                        "end_world_xz_m": (origin + [second % columns * spacing, second // columns * spacing]).tolist(),
                        "start_height_m": float(flat_height[first]), "end_height_m": float(flat_height[second]),
                        "start_accumulation_area_m2": float(flat_area[first]),
                        "end_accumulation_area_m2": float(flat_area[second]),
                        "category": "registered_river_edge" if is_registered else "subthreshold_local_tributary_edge"})
    if not any(record["category"] == "subthreshold_local_tributary_edge" for record in records[:2]):
        raise ValueError("local tributary sidecar requires an explicit unregistered incoming tributary")
    declaration = {"algorithm": ALGORITHM, "status": "frozen_geometry_unverified",
                   "parent_plan_identity_sha256": plan["identity_sha256"], "junction_id": junction,
                   "incoming_ids": upstream, "owner_domain_id": domain_id,
                   "river_threshold_area_m2": threshold, "edges": records,
                   "registered_terminal_id": chain[-1], "downstream_receiver_chain": chain,
                   "receiver_sha256": _array_digest(receiver), "river_mask_sha256": _array_digest(registered),
                   "highest_lake_level_m": float(highest_lake_level_m), "lake_mask_sha256": _array_digest(mask),
                   "scope": "bounded three-edge local tributary geometry; parent river mask and threshold unchanged",
                   "freeze_order": "declaration must be saved before any new TD source inference or geometry solve",
                   "fine_geometry_certified": False, "global_hydrology_certified": False}
    declaration["identity_sha256"] = _digest(declaration)
    return declaration


def validate_local_tributary_sidecar(plan, declaration, *, highest_lake_level_m, lake_mask):
    """Cold-check the frozen declaration against its real receiver and wet stage."""
    expected = freeze_local_tributary_confluence(plan, junction_id=declaration["junction_id"],
        incoming_ids=declaration["incoming_ids"], highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    if declaration != expected:
        raise ValueError("local tributary declaration or immutable parent provenance mismatch")
    return {"status": "verified_declared_receiver_graph", "fine_geometry_certified": False,
            "sidecar_identity_sha256": declaration["identity_sha256"]}


def validate_local_tributary_source_edges(plan, declaration, node_source_edges, *, highest_lake_level_m, lake_mask):
    """Opt-in fine nodes may use only one of the three declared real edges."""
    validate_local_tributary_sidecar(plan, declaration, highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    edges = np.asarray(node_source_edges)
    if edges.ndim != 2 or edges.shape[1] != 2 or edges.dtype.kind not in "iu" or not len(edges):
        raise ValueError("integer clipped-node source edges required")
    allowed = {tuple(record["source_edge"]) for record in declaration["edges"]}
    if any(tuple(int(value) for value in edge) not in allowed for edge in edges):
        raise ValueError("fine tributary source edge is outside the explicit three-edge declaration")
    return {"status": "verified_declared_receiver_edges", "sidecar_identity_sha256": declaration["identity_sha256"],
            "fine_geometry_certified": False}


def save_local_tributary_sidecar(declaration, path):
    """Publish a new declaration using the existing immutable JSON-file pattern."""
    unsigned = {key: value for key, value in declaration.items() if key != "identity_sha256"}
    if declaration.get("identity_sha256") != _digest(unsigned) or declaration.get("status") != "frozen_geometry_unverified":
        raise ValueError("invalid frozen local tributary declaration identity")
    payload = json.dumps(declaration, indent=2, allow_nan=False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload)


def load_local_tributary_sidecar(plan, path, *, highest_lake_level_m, lake_mask):
    declaration = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_local_tributary_sidecar(plan, declaration, highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    return declaration


def build_local_tributary_window(plan, declaration, *, highest_lake_level_m, lake_mask):
    """Select one frozen native97 window at the explicit junction, no search."""
    validate_local_tributary_sidecar(plan, declaration, highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    junction = declaration["junction_id"]
    columns = plan["height_m"].shape[1]
    center = np.asarray(plan["origin_xz_m"], float) + np.array([junction % columns, junction // columns]) * plan["spacing_m"]
    native_origin = np.floor(center / 30.0).astype(np.int64) - 48
    return {"kind": "confluence", "status": "planned", "coarse_cell": junction,
            "native_origin_xz": native_origin.tolist(), "shape": [97, 97],
            "origin_xz_m": (native_origin * 30.0).tolist(), "spacing_m": 30.0,
            "selection_edge_cell_ids": declaration["edges"][2]["source_edge"],
            "declared_source_edge_cell_ids": [record["source_edge"] for record in declaration["edges"]],
            "selection_algorithm": "explicit-local-tributary-junction-native-floor-v1",
            "local_tributary_sidecar_identity_sha256": declaration["identity_sha256"],
            "river_selection_semantics": "local subthreshold tributary geometry request; not two previously registered river branches",
            "fine_geometry_certified": False, "global_hydrology_certified": False}


def _save_matching_json(path, record):
    path = Path(path)
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != record:
            raise ValueError("immutable local tributary preparation declaration differs")
        return
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, allow_nan=False)


def prepare_local_tributary_source_declaration(plan, declaration, output, *, budget, highest_lake_level_m,
                                             lake_mask, maximum_source_tiles=15):
    """CPU-only frozen collection/detail declarations plus existing dependency API.

    This never generates TD or projects terrain. After reviewing the written
    dependencies, the caller may invoke existing prepare_projection_source with
    generate=True. Original97 assembly must honor this custom frozen selection.
    """
    from diffusion.physical_config import PhysicalGenerationConfig
    from terrain_pipeline.hydrology_detail_td import source_contract
    from tools.prepare_hydrology_domains import prepare_projection_source, projection_source_declaration

    if type(maximum_source_tiles) is not int or not 1 <= maximum_source_tiles <= 15:
        raise ValueError("explicit canonical source dependency bound must be 1..15")
    window = build_local_tributary_window(plan, declaration, highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    budget_record = asdict(budget)
    if budget_record["channel_max_cut_m"] > 4:
        raise ValueError("local tributary channel budget cannot exceed 4m")
    config = PhysicalGenerationConfig()
    generation_identity, _ = config.generation_identity()
    # Use the source tool's exact identity convention, not the sidecar convention.
    from terrain_pipeline.hydrology_detail_td import _digest as source_digest
    canonical_identity = source_digest(source_contract(generation_identity))
    output = Path(output)
    child = output / "confluence"
    child.mkdir(parents=True, exist_ok=True)
    collection = {"schema": "hydrology-formal-local-tributary-confluence-v1",
                  "source_plan_identity": plan["identity_sha256"], "windows": [window],
                  "budget": budget_record, "budget_status": "frozen_after_calibration",
                  "local_tributary_sidecar": declaration,
                  "local_tributary_sidecar_identity_sha256": declaration["identity_sha256"],
                  "maximum_source_tiles": maximum_source_tiles, "global_hydrology_certified": False,
                  "scope": "single explicit subthreshold tributary confluence; historical five-window collection unchanged"}
    detail = {"schema": "hydrology-detail-execution-v1", "seed": int(plan["seed"]),
              "plan_identity": plan["identity_sha256"], "generation_identity": generation_identity,
              "canonical_source_identity": canonical_identity, "raw_source_schema": "hydrology-canonical-td-window-v1",
              "windows": [window], "budget": budget_record, "budget_status": "frozen_after_calibration",
              "physical_config": json.loads(json.dumps(config.record(), allow_nan=False)), "divide_taper_width_m": 0.0,
              "local_tributary_sidecar_identity_sha256": declaration["identity_sha256"],
              "scope": "frozen local tributary source request; geometry unverified"}
    _save_matching_json(output / "collection-plan.json", collection)
    _save_matching_json(child / "detail-plan.json", detail)
    dependencies = projection_source_declaration(plan, output, "confluence")
    if len(dependencies["required_source_tile_xz"]) > maximum_source_tiles:
        raise ValueError("local tributary source declaration exceeds frozen dependency bound")
    record = prepare_projection_source(plan, output, "light", "confluence", generate=False)
    return {**record, "collection_path": str(output / "collection-plan.json"),
            "detail_plan_path": str(child / "detail-plan.json"), "window": window,
            "local_tributary_sidecar_identity_sha256": declaration["identity_sha256"],
            "required_source_tile_xz": dependencies["required_source_tile_xz"],
            "required_coarse_node_zx": dependencies["required_coarse_node_zx"],
            "maximum_source_tiles": maximum_source_tiles, "fine_geometry_certified": False}


def prepare_local_tributary_original(plan, declaration, output, *, budget, highest_lake_level_m, lake_mask,
                                    resource_tier="light", canonical_cache_root=None):
    """Assemble only already cached genuine TD and derive the new native97 crop.

    Every declared tile and pin must exist before constructing the backend. The
    backend inference method is explicitly disabled, including a later cache
    race. This does not perform a macro projection or continuous bed solve.
    """
    from diffusion.physical_config import PhysicalGenerationConfig
    from terrain_pipeline.hydrology_detail import derive_detail, file_sha256, load_raw_td, required_td_nodes, save_detail
    from terrain_pipeline.hydrology_detail_conditioning import ResourcePhysicalTerrainDiffusionBackend
    from terrain_pipeline.hydrology_detail_td import CanonicalTDSource
    from tools.prepare_hydrology_domains import CANONICAL_CACHE

    preparation = prepare_local_tributary_source_declaration(plan, declaration, output, budget=budget,
        highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    output = Path(output)
    child = output / "confluence"
    detail_declaration = json.loads((child / "detail-plan.json").read_text(encoding="utf-8"))
    cache_root = Path(canonical_cache_root) if canonical_cache_root is not None else CANONICAL_CACHE
    folder = cache_root / detail_declaration["canonical_source_identity"] / str(plan["seed"] & 0xFFFFFFFFFFFFFFFF)
    missing = []
    for tx, tz in preparation["required_source_tile_xz"]:
        tile = folder / f"tile-x{tx}-z{tz}.npz"
        pin = tile.with_suffix(".sha256")
        if not tile.exists() or not pin.exists():
            missing.append({"tile_xz": [tx, tz], "missing_npz": not tile.exists(), "missing_pin": not pin.exists()})
        elif file_sha256(tile) != pin.read_text(encoding="ascii").strip():
            raise ValueError("declared local tributary TD cache pin mismatch")
    if missing:
        return {**preparation, "status": "source_unprepared", "missing_source_tiles": missing,
                "backend_created": False, "model_inference_run": False, "macro_projection_run": False}
    backend = ResourcePhysicalTerrainDiffusionBackend(PhysicalGenerationConfig(), resource_tier)
    def forbidden_inference(*args, **kwargs):
        raise ValueError("local tributary original assembly forbids new TD inference")
    backend.generate = forbidden_inference
    canonical = CanonicalTDSource(backend, cache_root)
    if canonical.identity != detail_declaration["canonical_source_identity"]:
        canonical.close()
        raise ValueError("local tributary cached source scientific identity mismatch")
    window = preparation["window"]
    nodes = {}
    try:
        node_folder = child / "td-coarse-node-cache"
        node_folder.mkdir(exist_ok=True)
        for cz, cx in required_td_nodes(plan, window):
            cz, cx = int(cz), int(cx)
            key = f"{cz}:{cx}"
            world = np.asarray(plan["origin_xz_m"]) + np.array([cx, cz]) * plan["spacing_m"]
            native = world / 30.0
            floor = np.floor(native).astype(int)
            elevation, _, metadata = canonical.generate(int(plan["seed"]), int(floor[0]), int(floor[1]), 2)
            wx, wz = native - floor
            sampled = (1 - wz) * ((1 - wx) * elevation[0, 0] + wx * elevation[0, 1]) + wz * ((1 - wx) * elevation[1, 0] + wx * elevation[1, 1])
            record = {"elevation_m": float(sampled), "world_xz_m": world.tolist(),
                      "generation_identity": canonical.identity, "seed": plan["seed"], "generation_metadata": metadata,
                      "native_elevation_m": elevation.tolist(), "sampling": "bilinear fixed globally aligned native 2x2 TD nodes"}
            _save_matching_json(node_folder / f"{cz}-{cx}.json", record)
            nodes[key] = record
        raw_path = child / "confluence-original-td.npz"
        pin = raw_path.with_suffix(".sha256")
        if not raw_path.exists():
            x, z = window["native_origin_xz"]
            elevation, climate, metadata = canonical.generate(int(plan["seed"]), x, z, 97)
            with raw_path.open("xb") as stream:
                np.savez_compressed(stream, elevation_m=elevation, climate=climate,
                                    metadata_json=np.array(json.dumps(metadata, allow_nan=False)))
            with pin.open("x", encoding="ascii") as stream:
                stream.write(file_sha256(raw_path))
        if not pin.exists():
            raise ValueError("local tributary original TD requires a saved pin")
        raw, source_metadata = load_raw_td(raw_path, pin.read_text(encoding="ascii").strip())
        provenance = source_metadata["provenance"]
        generated = provenance["generation_metadata"]
        if (generated["identity"] != canonical.identity or int(generated["seed"]) != plan["seed"]
                or generated["native_origin"] != window["native_origin_xz"] or generated["shape"] != window["shape"]):
            raise ValueError("saved local tributary original differs from the frozen source window")
        derived_plan = dict(plan, frozen_td_baseline_nodes=nodes)
        result = derive_detail(derived_plan, raw["arrays"]["height_m"], origin_xz_m=window["origin_xz_m"],
            spacing_m=30.0, raw_provenance=provenance, budget=budget, window_kind="confluence")
        result["metadata"]["local_tributary_sidecar_identity_sha256"] = declaration["identity_sha256"]
        result["metadata"]["local_tributary_semantics"] = window["river_selection_semantics"]
        result["metadata"]["model_inference_run"] = False
        from terrain_pipeline.hydrology_detail import _digest as detail_digest
        unsigned_metadata = {key: value for key, value in result["metadata"].items() if key != "identity"}
        result["metadata"]["identity"] = detail_digest({"metadata": unsigned_metadata, "arrays": {
            name: hashlib.sha256(value.tobytes()).hexdigest() for name, value in sorted(result["arrays"].items())}})
        detail_path = child / "confluence-detail.npz"
        if detail_path.exists():
            with np.load(detail_path, allow_pickle=False) as archive:
                previous = json.loads(str(archive["metadata_json"].item()))
            if previous["identity"] != result["metadata"]["identity"]:
                raise ValueError("immutable local tributary native detail differs")
        else:
            save_detail(detail_path, result)
    finally:
        canonical.close()
    report = {**preparation, "status": "cached_original_assembled_geometry_unverified", "backend_created": True,
              "raw_path": str(raw_path), "raw_sha256": pin.read_text(encoding="ascii").strip(),
              "detail_path": str(detail_path), "detail_metadata": result["metadata"],
              "original_raw_source_is_genuine_td": True, "model_inference_run": False, "macro_projection_run": False,
              "scope": "cached genuine original97 and native diagnostic crop; full confluence geometry not certified"}
    _save_matching_json(child / "detail-review.json", report)
    return report
