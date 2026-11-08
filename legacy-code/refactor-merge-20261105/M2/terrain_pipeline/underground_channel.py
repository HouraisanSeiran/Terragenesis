"""Explainable underground-channel entry ranking and hard feasibility filters."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash


VERSION = "underground-channel-v1"


@dataclass(frozen=True)
class UndergroundRecipe:
    min_cover_m: float = 8.
    min_entry_score: float = .5
    grayscale_weight: float = .45
    lithology_weight: float = .35
    cover_weight: float = .20

    def __post_init__(self):
        if any(isinstance(v, bool) or not math.isfinite(v) or v < 0
               for v in (self.min_cover_m, self.min_entry_score,
                         self.grayscale_weight, self.lithology_weight, self.cover_weight)):
            raise ValueError("recipe values must be finite and nonnegative")
        if self.grayscale_weight + self.lithology_weight + self.cover_weight <= 0:
            raise ValueError("at least one score weight is required")


def plan_underground(surface_plan, grayscale_reference, lithology_reference,
                     domain_mask, protected_mask, entries, exits, recipe=UndergroundRecipe(),
                     cover_reference=None):
    """Rank explicit candidate entrances and connect only accepted entry/exit pairs."""
    if not isinstance(recipe, UndergroundRecipe) or surface_plan.get("status") != "diagnostic_not_publishable":
        raise ValueError("validated surface plan and recipe required")
    identity = ArtifactIdentity(**surface_plan["identity"])
    if (identity.sha256 != surface_plan.get("identity_sha256") or
            identity.algorithm != "metric-channel-plan"):
        raise ValueError("invalid surface plan identity")
    height = np.asarray(surface_plan["arrays"]["source_height_m"])
    if height.dtype != np.float64 or height.ndim != 2 or not np.isfinite(height).all():
        raise ValueError("surface height must be a finite float64 grid")
    source_hash = identity.record()["parameters"].get("source_height_sha256")
    if source_hash and array_hash(height) != source_hash:
        raise ValueError("surface height differs from identity")
    shape = height.shape
    gray = np.asarray(grayscale_reference, dtype=np.float64)
    lithology = np.asarray(lithology_reference, dtype=np.float64)
    domain = np.asarray(domain_mask)
    protected = np.asarray(protected_mask)
    if (gray.shape != shape or lithology.shape != shape or domain.shape != shape or
            protected.shape != shape or not np.isfinite(gray).all() or
            not np.isfinite(lithology).all() or domain.dtype != bool or protected.dtype != bool):
        raise ValueError("references and masks must be finite arrays matching the surface plan")
    if cover_reference is None:
        raise ValueError("an explicit underground cover reference is required")
    cover = np.asarray(cover_reference, dtype=np.float64)
    if cover.shape != shape or not np.isfinite(cover).all() or np.any(cover < 0):
        raise ValueError("cover reference must be a finite nonnegative grid")
    entry_array = np.asarray(entries, dtype=np.int64)
    if entry_array.ndim != 2 or entry_array.shape[1] != 2:
        raise ValueError("entries must be z,x pairs")
    exit_records = []
    for item in exits:
        if isinstance(item, dict):
            point, kind = item.get("grid_zx"), item.get("type")
        else:
            if len(item) != 3:
                raise ValueError("exits require grid_zx and explicit type")
            point, kind = item[:2], item[2]
        if kind not in {"surface_low", "spring", "coast", "subsea"}:
            raise ValueError("unknown exit type")
        if point is None or len(point) != 2:
            raise ValueError("exit coordinates must be z,x")
        exit_records.append((int(point[0]), int(point[1]), kind))
    scores = np.zeros(shape, dtype=np.float64)
    gray_norm = (gray - gray.min()) / max(np.ptp(gray), 1e-12)
    lith_norm = (lithology - lithology.min()) / max(np.ptp(lithology), 1e-12)
    total_weight = recipe.grayscale_weight + recipe.lithology_weight + recipe.cover_weight
    scores = (recipe.grayscale_weight * (1 - gray_norm) +
              recipe.lithology_weight * lith_norm +
              recipe.cover_weight * np.clip(cover / max(recipe.min_cover_m, 1.), 0., 1.)) / total_weight
    accepted = []
    rejected = []
    for z, x in entry_array:
        reasons = []
        valid = 0 <= z < shape[0] and 0 <= x < shape[1]
        if not valid:
            reasons.append("outside_grid")
        else:
            if protected[z, x]: reasons.append("protected")
            if not domain[z, x]: reasons.append("outside_hydrologic_domain")
            if cover[z, x] < recipe.min_cover_m: reasons.append("insufficient_cover")
            if scores[z, x] < recipe.min_entry_score: reasons.append("score_below_threshold")
        item = {"grid_zx": [int(z), int(x)], "score": float(scores[z, x]) if valid else None,
                "accepted": not reasons, "reasons": reasons}
        (accepted if not reasons else rejected).append(item)
    accepted_exits = []
    for z, x, exit_type in exit_records:
        valid = 0 <= z < shape[0] and 0 <= x < shape[1]
        reasons = [] if valid and domain[z, x] and not protected[z, x] else ["invalid_or_protected_exit"]
        item = {"grid_zx": [int(z), int(x)], "accepted": not reasons, "reasons": reasons,
                "type": exit_type}
        if exit_type == "subsea":
            item["diagnostic_only"] = True
        (accepted_exits if not reasons else rejected).append(item)
    edges = []
    blocked = protected | (~domain) | (cover < recipe.min_cover_m)
    if accepted and accepted_exits:
        for source in accepted:
            target = min(accepted_exits, key=lambda item: abs(item["grid_zx"][0] - source["grid_zx"][0]) + abs(item["grid_zx"][1] - source["grid_zx"][1]))
            start, goal = tuple(source["grid_zx"]), tuple(target["grid_zx"])
            # Deterministic breadth first path; blocked cells cannot be traversed.
            queue, previous = [start], {start: None}
            for cell in queue:
                if cell == goal: break
                for dz, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                    nxt = (cell[0] + dz, cell[1] + dx)
                    if (0 <= nxt[0] < shape[0] and 0 <= nxt[1] < shape[1] and
                            (nxt == goal or not blocked[nxt]) and nxt not in previous):
                        previous[nxt] = cell; queue.append(nxt)
            if goal not in previous:
                continue
            path = []; cell = goal
            while cell is not None: path.append(list(cell)); cell = previous[cell]
            path.reverse()
            edges.append({"entry_grid_zx": source["grid_zx"], "exit_grid_zx": target["grid_zx"],
                          "path_grid_zx": path, "status": "candidate_only"})
    identity = ArtifactIdentity("Terragenesis", "underground-channel", VERSION, 0,
                                {**asdict(recipe), "surface_plan_sha256": surface_plan["identity_sha256"],
                                 "height_sha256": array_hash(height), "grayscale_sha256": array_hash(gray),
                                 "lithology_sha256": array_hash(lithology), "domain_sha256": array_hash(domain),
                                 "protected_sha256": array_hash(protected),
                                 "cover_sha256": array_hash(cover)})
    outputs = {"score_m": scores, "accepted_entry_mask": np.zeros(shape, bool),
               "domain_mask": domain.copy(), "protected_mask": protected.copy()}
    for item in accepted:
        outputs["accepted_entry_mask"][tuple(item["grid_zx"])] = True
    for value in outputs.values(): value.flags.writeable = False
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": "diagnostic_not_publishable", "arrays": outputs,
            "entries": accepted + rejected, "exits": accepted_exits,
            "edges": edges, "preview_modes": ["surface_only", "underground_only", "overlay"],
            "summary": {"accepted_entries": len(accepted), "rejected_candidates": len(rejected),
                        "accepted_exits": len(accepted_exits), "candidate_edges": len(edges),
                        "grayscale_is_ranking_only": True,
                        "cover_is_explicit_reference": True}}


def save_underground(result, path):
    destination = Path(path)
    if destination.exists(): raise FileExistsError(destination)
    if not destination.parent.is_dir(): raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ("identity", "identity_sha256", "status", "entries", "exits", "edges", "preview_modes", "summary")}
    record["format_version"] = 1
    record["array_sha256"] = {name: array_hash(np.ascontiguousarray(value)) for name, value in result["arrays"].items()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, delete=False, suffix=".npz") as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(record, sort_keys=True), **result["arrays"])
        load_underground(temporary)
        os.link(temporary, destination)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
    return destination


def load_underground(path):
    expected = {"score_m", "accepted_entry_mask", "domain_mask", "protected_mask"}
    with np.load(path, allow_pickle=False) as archive:
        record = json.loads(str(archive["manifest"].item()))
        if set(archive.files) != expected | {"manifest"} or set(record.get("array_sha256", {})) != expected:
            raise ValueError("invalid underground array set")
        arrays = {name: archive[name].copy() for name in expected}
    identity = ArtifactIdentity(**record["identity"])
    if (record.get("format_version") != 1 or record.get("status") != "diagnostic_not_publishable" or
            identity.algorithm != "underground-channel" or identity.algorithm_version != VERSION or
            identity.sha256 != record["identity_sha256"] or
            any(array_hash(np.ascontiguousarray(arrays[name])) != expected for name, expected in record["array_sha256"].items())):
        raise ValueError("underground identity or arrays differ")
    shape = arrays["score_m"].shape
    if (len(shape) != 2 or min(shape) < 1 or arrays["score_m"].dtype != np.float64 or
            not np.isfinite(arrays["score_m"]).all() or
            any(arrays[name].shape != shape or arrays[name].dtype != bool for name in ("accepted_entry_mask", "domain_mask", "protected_mask"))):
        raise ValueError("invalid underground shapes or values")
    if record.get("preview_modes") != ["surface_only", "underground_only", "overlay"]:
        raise ValueError("invalid preview modes")
    for value in arrays.values(): value.flags.writeable = False
    return {**{key: record[key] for key in ("identity", "identity_sha256", "status", "entries", "exits", "edges", "preview_modes", "summary")}, "arrays": arrays}
