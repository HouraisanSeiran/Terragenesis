"""Area-conserving local TD replacement in a coarse seasonal lake model.

Fine pixel centres own square footprints. Overlaps with coarse node-centred
control volumes become separate weighted columns; uncovered coarse area remains.
This closes arithmetic under a declared mixed-basin connectivity assumption,
not a certificate of fine face connectivity throughout the annual water cycle.
"""

import hashlib
import heapq
import json
from pathlib import Path
import shutil

import numpy as np

from terrain_pipeline.hydrology_seasonal import LakeGeometry, SeasonalConfig


ALGORITHM = "hydrology-seasonal-hybrid-lake-v1"
COLUMN_ARRAYS = ("height_m", "owner_domain_id", "seasonal_column_area_m2",
                 "seasonal_parent_cell_id", "seasonal_lake_domain_id")


def _digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _array_hash(array):
    array = np.ascontiguousarray(array)
    return _digest({"shape": list(array.shape), "dtype": array.dtype.str,
                    "bytes_sha256": hashlib.sha256(array.tobytes()).hexdigest()})


class WeightedLakeGeometry:
    """Exact weighted column hypsometry, with zero-storage level at lowest bed."""

    def __init__(self, height, area, mask, spill_m):
        height, area, mask = np.asarray(height), np.asarray(area), np.asarray(mask)
        if (height.shape != area.shape or height.shape != mask.shape or mask.dtype != bool
                or not mask.any() or not np.isfinite(height).all() or not np.isfinite(area).all()
                or np.any(area <= 0) or not np.isfinite(spill_m) or np.any(height[mask] >= spill_m)):
            raise ValueError("finite positive weighted lake columns below spill required")
        order = np.argsort(height[mask], kind="stable")
        self.beds = height[mask][order].astype(float)
        self.areas = area[mask][order].astype(float)
        self.mask = mask.copy()
        self.spill_m = float(spill_m)
        self.cell_area_m2 = None
        self.prefix_area = np.concatenate(([0.], np.cumsum(self.areas)))
        self.prefix_bed_volume = np.concatenate(([0.], np.cumsum(self.beds * self.areas)))
        self.break_volumes = self.beds * self.prefix_area[:-1] - self.prefix_bed_volume[:-1]
        self.capacity_m3 = self.volume(self.spill_m)

    def volume(self, level_m):
        if not np.isfinite(level_m):
            raise ValueError("finite lake level required")
        return float(np.sum(np.maximum(level_m - self.beds, 0) * self.areas))

    def area(self, level_m):
        if not np.isfinite(level_m):
            raise ValueError("finite lake level required")
        return float(self.areas[self.beds < level_m].sum())

    def level(self, volume_m3):
        if not np.isfinite(volume_m3) or volume_m3 < 0:
            raise ValueError("finite nonnegative lake storage required")
        count = min(int(np.searchsorted(self.break_volumes, volume_m3, side="right")), len(self.beds))
        return float((volume_m3 + self.prefix_bed_volume[count]) / self.prefix_area[count])


def load_hybrid_lake_detail(path, expected_sha256):
    """Read one pinned derived TD product; no generation or projection."""
    from terrain_pipeline.mountain_source_adapter import checked_archive
    archive = checked_archive(path, expected_sha256=expected_sha256)
    return {"arrays": {key: value for key, value in archive.items() if key != "metadata_json"},
            "metadata": json.loads(str(archive["metadata_json"].item()))}


def _checked_detail(plan, detail, source_sha256):
    from terrain_pipeline.hydrology_detail import _digest as detail_digest
    metadata, arrays = detail["metadata"], detail["arrays"]
    if (not isinstance(source_sha256, str) or len(source_sha256) != 64
            or any(c not in "0123456789abcdef" for c in source_sha256)):
        raise ValueError("pinned fine detail SHA256 required")
    unsigned = {key: value for key, value in metadata.items() if key != "identity"}
    expected = detail_digest({"metadata": unsigned, "arrays": {
        name: hashlib.sha256(np.asarray(value).tobytes()).hexdigest() for name, value in sorted(arrays.items())}})
    if metadata.get("identity") != expected or metadata.get("plan_identity") != plan.get("identity_sha256"):
        raise ValueError("fine detail content or frozen parent identity mismatch")
    generated = metadata.get("raw_provenance", {}).get("generation_metadata", {})
    if (generated.get("artifact_kind") != "terrain_diffusion_output"
            or generated.get("schema") != "hydrology-canonical-td-window-v1"
            or int(generated.get("seed", -1)) != plan["seed"]
            or not generated.get("tile_assembly") or not generated.get("identity")):
        raise ValueError("genuine pinned canonical TD provenance required")
    heights = np.asarray(arrays["derived_height_m"])
    owners = np.asarray(arrays["owner_domain_id"])
    spacing = float(metadata["spacing_m"])
    origin = np.asarray(metadata["origin_xz_m"], dtype=float)
    if (heights.ndim != 2 or heights.size > 250000 or owners.shape != heights.shape
            or owners.dtype.kind not in "iu" or not np.isfinite(heights).all()
            or not np.isfinite(spacing) or not 0 < spacing <= plan["spacing_m"]
            or origin.shape != (2,) or not np.isfinite(origin).all()):
        raise ValueError("aligned bounded fine lake raster and physical coordinates required")
    if metadata.get("schema") == "hydrology-local-connected-lake-basin-v1":
        _audit_lake_correction(detail)
    return metadata, heights, owners, spacing, origin


def prepare_hybrid_lake_plan(plan, detail, *, source_sha256, domain_id, coarse_climate):
    """Replace a single nonoverlapping fine raster footprint, retaining remainder.

    Climate depths are inherited from each fragment's frozen parent coarse cell.
    Fine soil states are separate, so temporarily wet fractions never duplicate
    coarse soil/rain. Lake membership inherits the connected coarse basin and is
    explicitly an assumption until all-stage fine connectivity is supplied.
    """
    metadata, fine, fine_owner, fine_spacing, fine_origin = _checked_detail(plan, detail, source_sha256)
    domains = plan["domains"]
    matches = [d for d in domains if d["domain_id"] == domain_id and d["kind"] == "inland"]
    if len(matches) != 1 or sum(d["kind"] == "inland" for d in domains) != 1:
        raise ValueError("one explicit registered inland lake required")
    domain = matches[0]
    coarse = np.asarray(plan["height_m"])
    owner = np.asarray(plan["owner_domain_id"])
    spacing = float(plan["spacing_m"])
    origin = np.asarray(plan["origin_xz_m"], float)
    coarse_area = spacing**2
    lake = LakeGeometry(coarse, owner, domain, coarse_area)
    if np.any(fine_owner != domain_id):
        raise ValueError("fine replacement footprint must remain inside its frozen inland owner")
    for key in ("precipitation_mm", "potential_et_mm"):
        values = np.asarray(coarse_climate[key])
        if values.shape != (12,) + coarse.shape or not np.isfinite(values).all() or np.any(values < 0):
            raise ValueError("finite parent coarse forcing required")
    # Rectangles are half-open; measure-zero shared edges never own area twice.
    fragments, replaced = [], np.zeros(coarse.size)
    width = coarse.shape[1]
    for fz, fx in np.ndindex(fine.shape):
        center = fine_origin + np.array([fx, fz]) * fine_spacing
        lower, upper = center - fine_spacing / 2, center + fine_spacing / 2
        first = np.floor((lower - origin + spacing / 2) / spacing).astype(int)
        last = np.ceil((upper - origin + spacing / 2) / spacing).astype(int) - 1
        if (first < 0).any() or last[0] >= coarse.shape[1] or last[1] >= coarse.shape[0]:
            raise ValueError("fine footprint extends beyond finite coarse control volumes")
        for cz in range(first[1], last[1] + 1):
            for cx in range(first[0], last[0] + 1):
                coarse_center = origin + np.array([cx, cz]) * spacing
                overlap = np.minimum(upper, coarse_center + spacing / 2) - np.maximum(lower, coarse_center - spacing / 2)
                area = float(np.prod(np.maximum(overlap, 0)))
                if area == 0:
                    continue
                if owner[cz, cx] != domain_id:
                    raise ValueError("fine fragment crosses frozen coarse owner")
                parent_id = int(cz * width + cx)
                replaced[parent_id] += area
                membership = domain_id if lake.mask[cz, cx] and fine[fz, fx] < lake.spill_m else -1
                fragments.append((float(fine[fz, fx]), area, parent_id, membership))
    if not np.any(replaced[lake.mask.ravel()] > 0) or np.any(replaced > coarse_area + 1e-7):
        raise ValueError("replacement must cover the connected coarse basin without duplicate area")
    remainder = np.maximum(coarse_area - replaced, 0)
    retained = np.flatnonzero(remainder > 1e-7)
    heights = np.concatenate((coarse.ravel()[retained], [f[0] for f in fragments]))[None, :]
    areas = np.concatenate((remainder[retained], [f[1] for f in fragments]))[None, :]
    parents = np.concatenate((retained, [f[2] for f in fragments])).astype(np.int64)[None, :]
    memberships = np.concatenate((np.where(lake.mask.ravel()[retained], domain_id, -1),
                                  [f[3] for f in fragments])).astype(np.int32)[None, :]
    column_plan = {"height_m": heights, "owner_domain_id": owner.ravel()[parents],
                   "seasonal_column_area_m2": areas, "seasonal_parent_cell_id": parents,
                   "seasonal_lake_domain_id": memberships, "seed": plan["seed"],
                   "origin_xz_m": [0., 0.], "spacing_m": spacing, "domains": domains}
    climate = {key: np.asarray(values).reshape((12, -1))[:, parents.ravel()][:, None, :]
               for key, values in coarse_climate.items()}
    source = metadata["raw_provenance"]
    record = {"algorithm": ALGORITHM, "parent_plan_identity_sha256": plan["identity_sha256"],
              "seed": int(plan["seed"]), "parent_domains": json.loads(json.dumps(domains, allow_nan=False)),
              "parent_origin_xz_m": origin.tolist(), "parent_spacing_m": spacing,
              "fine_detail_identity_sha256": metadata["identity"], "fine_detail_archive_sha256": source_sha256,
              "raw_td_archive_sha256": source["archive_sha256"],
              "canonical_td_identity_sha256": source["generation_metadata"]["identity"],
              "fine_lake_support": metadata.get("fine_lake_support"),
              "fine_connected_wet_mask_sha256": (_array_hash(detail["arrays"]["connected_lake_wet_mask"])
                                                  if "connected_lake_wet_mask" in detail["arrays"] else None),
              "domain_id": domain_id, "fine_shape": list(fine.shape), "fine_origin_xz_m": fine_origin.tolist(),
              "fine_spacing_m": fine_spacing, "fine_footprint_area_m2": float(replaced.sum()),
              "coarse_cell_area_m2": coarse_area, "parent_cell_count": int(coarse.size),
              "parent_owner_sha256": _array_hash(owner.ravel()),
              "replacement_cell_ids": np.flatnonzero(replaced).tolist(),
              "replacement_areas_m2": replaced[replaced > 0].tolist(),
              "coarse_basin_area_m2": float(lake.mask.sum() * coarse_area),
              "replaced_coarse_basin_area_m2": float(replaced[lake.mask.ravel()].sum()),
              "retained_coarse_basin_area_m2": float(remainder[lake.mask.ravel()].sum()),
              "fine_basin_area_below_spill_m2": float(areas[0, len(retained):][memberships[0, len(retained):] == domain_id].sum()),
              "column_count": int(heights.size), "retained_coarse_column_count": int(len(retained)),
              "fine_fragment_count": len(fragments), "area_ownership": "node-centred half-open square control-volume intersection; subtract covered coarse area exactly once",
              "forcing": "each weighted column inherits monthly depths from its frozen parent coarse cell",
              "connectivity_assumption": "fine beds below spill in replaced connected coarse lake cells share one pool; disconnected fine pockets unverified",
              "seasonal_certification_inherited": False, "fine_geometry_certified": False,
              "global_hydrology_certified": False,
              "column_array_sha256": {key: _array_hash(column_plan[key]) for key in COLUMN_ARRAYS},
              "climate_sha256": {key: _array_hash(value) for key, value in climate.items()}}
    column_plan["seasonal_hybrid"] = record
    column_plan["identity_sha256"] = _digest(record)
    hybrid_column_inputs(column_plan)
    return {"plan": column_plan, "climate": climate, "audit": record}


def hybrid_column_inputs(plan, climate=None):
    """Cold-check disjoint column area, domain membership and frozen provenance."""
    record = plan["seasonal_hybrid"]
    if record.get("algorithm") != ALGORITHM or plan.get("identity_sha256") != _digest(record):
        raise ValueError("hybrid column scientific identity mismatch")
    if record["parent_domains"] != plan["domains"] or record["seed"] != plan["seed"]:
        raise ValueError("hybrid frozen domain or seed differs")
    height, owner = np.asarray(plan["height_m"]), np.asarray(plan["owner_domain_id"])
    areas, parents = np.asarray(plan["seasonal_column_area_m2"]), np.asarray(plan["seasonal_parent_cell_id"])
    membership = np.asarray(plan["seasonal_lake_domain_id"])
    if (height.ndim != 2 or any(np.asarray(plan[key]).shape != height.shape for key in COLUMN_ARRAYS)
            or not np.isfinite(areas).all() or np.any(areas <= 0) or parents.dtype.kind not in "iu"
            or np.any(parents < 0) or np.any(parents >= record["parent_cell_count"])):
        raise ValueError("aligned positive hybrid area and parent columns required")
    if any(record["column_array_sha256"][key] != _array_hash(plan[key]) for key in COLUMN_ARRAYS):
        raise ValueError("hybrid column source arrays differ from frozen declaration")
    if climate is not None and {key: _array_hash(value) for key, value in climate.items()} != record["climate_sha256"]:
        raise ValueError("hybrid climate differs from frozen parent forcing")
    totals = np.bincount(parents.ravel(), weights=areas.ravel(), minlength=record["parent_cell_count"])
    if not np.allclose(totals, record["coarse_cell_area_m2"], rtol=1e-12, atol=1e-7):
        raise ValueError("covered coarse area duplicated or omitted")
    if np.any((membership >= 0) & (membership != owner)):
        raise ValueError("hybrid lake column crosses parent ownership")
    parent_owners = np.empty(record["parent_cell_count"], dtype=owner.dtype)
    parent_owners[parents.ravel()] = owner.ravel()
    if (not np.array_equal(parent_owners[parents], owner)
            or _array_hash(parent_owners) != record["parent_owner_sha256"]):
        raise ValueError("hybrid columns differ from frozen parent ownership")
    lakes = {}
    for column, domain in enumerate(plan["domains"]):
        if domain["kind"] == "inland":
            lakes[column] = WeightedLakeGeometry(height, areas, membership == domain["domain_id"], domain["lake_spill_elevation_m"])
    return areas, lakes


def simulate_hybrid_lake_water_balance(plan, detail, *, source_sha256, domain_id, config=None, climate=None):
    """Recompute periodic soil/lake state with new geometry and no warm-start claim."""
    from terrain_pipeline.hydrology_seasonal import seasonal_climate, simulate_seasonal_water_balance
    config = config or SeasonalConfig()
    climate = seasonal_climate(plan, config) if climate is None else climate
    prepared = prepare_hybrid_lake_plan(plan, detail, source_sha256=source_sha256,
                                       domain_id=domain_id, coarse_climate=climate)
    result = simulate_seasonal_water_balance(prepared["plan"], config, prepared["climate"])
    connectivity = validate_hybrid_lake_connectivity(plan, detail, prepared, result)
    return {**prepared, "result": result, "connectivity": connectivity}


def _face_component_roots(mask):
    """Return one component label per true raster cell, using physical faces."""
    labels = np.full(mask.shape, -1, np.int32)
    component = 0
    rows, columns = mask.shape
    for row, column in zip(*np.where(mask)):
        if labels[row, column] >= 0:
            continue
        labels[row, column] = component
        stack = [(int(row), int(column))]
        while stack:
            r, c = stack.pop()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < rows and 0 <= cc < columns and mask[rr, cc] and labels[rr, cc] < 0:
                    labels[rr, cc] = component
                    stack.append((rr, cc))
        component += 1
    return labels, component


def validate_hybrid_lake_connectivity(parent_plan, detail, prepared, result):
    """Certify every actual cycle topology between critical fine bed elevations.

    This first local contract requires a rectangular fine patch strictly inside
    one coarse lake control volume. Its uncovered constant-bed ring is explicit
    known support. It must be wet at the cycle minimum and connected by coarse
    faces to the registered terminal. All fine wet components must meet that
    ring at every topology change, not merely at the maximum saved stage.
    """
    from terrain_pipeline.hydrology_seasonal import validate_seasonal_water_balance
    validate_seasonal_water_balance(prepared["plan"], result)
    record = prepared["audit"]
    metadata, fine, _, spacing, origin = _checked_detail(parent_plan, detail, record["fine_detail_archive_sha256"])
    if (record != prepared["plan"]["seasonal_hybrid"]
            or metadata["identity"] != record["fine_detail_identity_sha256"]):
        raise ValueError("cycle connectivity source differs from hybrid preparation")
    _, lakes = hybrid_column_inputs(prepared["plan"], prepared["climate"])
    columns = result["metadata"]["domain_ids"]
    column = columns.index(record["domain_id"])
    volumes = result["lake_volume_m3"][0, column] + np.concatenate(([0.], np.cumsum(result["steps"]["lake_change_m3"][:, column])))
    levels = np.array([lakes[column].level(float(v)) for v in volumes])
    minimum, maximum = float(levels.min()), float(levels.max())
    report = {"algorithm": "hybrid-local-lake-cycle-face-connectivity-v1",
              "parent_plan_identity_sha256": parent_plan["identity_sha256"],
              "hybrid_plan_identity_sha256": prepared["plan"]["identity_sha256"],
              "fine_detail_identity_sha256": metadata["identity"],
              "minimum_cycle_level_m": minimum, "maximum_cycle_level_m": maximum,
              "step_boundary_count": len(levels), "fine_geometry_certified": False,
              "global_hydrology_certified": False,
              "scope": "rectangular local fine footprint and retained coarse basin; actual converged cycle range only"}
    def reject(reason, **extra):
        return {**report, "status": "rejected", "reason": reason, **extra}
    replacements = record["replacement_cell_ids"]
    if len(replacements) != 1:
        return reject("fine footprint needs explicit retained support geometry across multiple coarse cells")
    parent_id = replacements[0]
    coarse = np.asarray(parent_plan["height_m"])
    coarse_owner = np.asarray(parent_plan["owner_domain_id"])
    row, col = divmod(parent_id, coarse.shape[1])
    coarse_spacing = float(parent_plan["spacing_m"])
    coarse_center = np.asarray(parent_plan["origin_xz_m"]) + np.array([col, row]) * coarse_spacing
    lower = origin - spacing / 2
    upper = origin + np.array([fine.shape[1] - 1, fine.shape[0] - 1]) * spacing + spacing / 2
    if not np.all(lower > coarse_center - coarse_spacing / 2) or not np.all(upper < coarse_center + coarse_spacing / 2):
        return reject("fine footprint lacks a strictly interior connected retained coarse ring")
    report.update(retained_support_parent_cell_id=parent_id, retained_support_bed_m=float(coarse[row, col]),
                  retained_support_area_m2=coarse_spacing**2 - record["fine_footprint_area_m2"],
                  retained_support_geometry="coarse square minus strictly interior fine rectangle; connected constant-bed ring")
    if coarse[row, col] >= minimum:
        return reject("retained coarse ring is dry at actual cycle minimum; unknown external fine terrain is not lake support")
    domain = next(d for d in parent_plan["domains"] if d["domain_id"] == record["domain_id"])
    coarse_lake = LakeGeometry(coarse, coarse_owner, domain, coarse_spacing**2)
    coarse_wet = coarse_lake.mask & (coarse < minimum)
    coarse_labels, _ = _face_component_roots(coarse_wet)
    terminal_row, terminal_col = divmod(domain["lake_terminal_index"], coarse.shape[1])
    if (coarse_labels[row, col] < 0 or coarse_labels[terminal_row, terminal_col] != coarse_labels[row, col]):
        return reject("retained wet coarse support lacks a face-connected registered-terminal path at cycle minimum")
    critical = np.unique(fine[(fine >= minimum) & (fine <= maximum)])
    stages = np.unique(np.concatenate(([minimum, maximum], critical, np.nextafter(critical, np.inf))))
    stages = stages[(stages >= minimum) & (stages <= maximum)]
    boundary = np.zeros(fine.shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    maximum_components = 0
    for stage in stages:
        wet = fine < stage
        labels, count = _face_component_roots(wet)
        reached = np.unique(labels[boundary & wet])
        reached = reached[reached >= 0]
        if len(reached) != count:
            disconnected = wet & ~np.isin(labels, reached)
            return reject("fine wet component does not meet known wet retained coarse ring at a cycle-critical stage",
                          failing_stage_m=float(stage), disconnected_pixel_count=int(disconnected.sum()),
                          tested_stage_count=len(stages), critical_bed_count=len(critical))
        maximum_components = max(maximum_components, count)
    return {**report, "status": "verified_local_actual_cycle_connectivity",
            "fine_geometry_certified": True, "critical_bed_count": len(critical),
            "tested_stage_count": len(stages), "maximum_fine_wet_component_count": maximum_components,
            "coarse_terminal_index": domain["lake_terminal_index"],
            "proof": "wet coarse ring and face path persist above cycle minimum; fine wet masks change only at bed elevations, checked with strict< on both sides"}


def fill_lake_patch_to_boundary_saddles(height):
    """Minimum D4 depression fill with every boundary bed held immutable."""
    height = np.asarray(height, dtype=float)
    if height.ndim != 2 or min(height.shape) < 3 or height.size > 250000 or not np.isfinite(height).all():
        raise ValueError("finite bounded lake patch with an outer ring required")
    rows, columns = height.shape
    filled = height.copy()
    visited = np.zeros(height.shape, bool)
    visited[[0, -1], :] = True
    visited[:, [0, -1]] = True
    heap = [(float(height[r, c]), int(r), int(c)) for r, c in zip(*np.where(visited))]
    heapq.heapify(heap)
    while heap:
        level, row, column = heapq.heappop(heap)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            r, c = row + dr, column + dc
            if 0 <= r < rows and 0 <= c < columns and not visited[r, c]:
                visited[r, c] = True
                filled[r, c] = max(level, height[r, c])
                heapq.heappush(heap, (float(filled[r, c]), r, c))
    return filled


def _audit_lake_correction(detail):
    """Cold-recompute the fill witness and its combined frozen budget."""
    from terrain_pipeline.hydrology_detail import DetailBudget
    arrays, metadata = detail["arrays"], detail["metadata"]
    height = np.asarray(arrays["derived_height_m"])
    fill = np.asarray(arrays["lake_depression_fill_m"])
    raw, macro = np.asarray(arrays["original_td_m"]), np.asarray(arrays["macro_delta_m"])
    channel, protected = np.asarray(arrays["local_channel_delta_m"]), np.asarray(arrays["shared_boundary_protected"])
    if (any(a.shape != height.shape for a in (fill, raw, macro, channel, protected))
            or protected.dtype != bool or not all(np.isfinite(a).all() for a in (fill, raw, macro, channel))
            or np.any(fill < 0) or np.any(fill[protected] != 0) or np.any(fill[[0, -1], :] != 0)
            or np.any(fill[:, [0, -1]] != 0)
            or not np.allclose(height, raw + macro + channel, rtol=0, atol=1e-6)
            or not np.allclose(height, fill_lake_patch_to_boundary_saddles(height - fill), rtol=0, atol=1e-10)):
        raise ValueError("saved lake correction is not the minimum fill with immutable protected boundary")
    budget = DetailBudget(**metadata["budget"])
    area = float(metadata["spacing_m"])**2
    total = height - raw
    ledger = {"macro_max_abs_m": float(np.abs(macro).max()), "total_max_abs_m": float(np.abs(total).max()),
              "macro_absolute_volume_m3": float(np.abs(macro).sum() * area),
              "total_absolute_volume_m3": float(np.abs(total).sum() * area),
              "channel_max_cut_m": float(max(0., -channel.min()))}
    correction = metadata["lake_correction"]
    def same_reduction(first, second):
        return bool(np.isclose(first, second, rtol=8 * np.finfo(float).eps, atol=0))
    recorded_ledger_matches = all(
        key in metadata["ledger"] and key in correction["combined_ledger"]
        and same_reduction(value, metadata["ledger"][key])
        and same_reduction(value, correction["combined_ledger"][key]) for key, value in ledger.items())
    if (any(value > getattr(budget, key) for key, value in ledger.items())
            or not recorded_ledger_matches
            or correction["budget"] != metadata["budget"]
            or correction["filled_pixel_count"] != int(np.count_nonzero(fill))
            or correction["filled_area_m2"] != float(np.count_nonzero(fill) * area)
            or correction["maximum_fill_m"] != float(fill.max())
            or not same_reduction(correction["fill_volume_m3"], float(fill.sum() * area))
            or correction["canonical_core_exact_crop"] is not False):
        raise ValueError("saved lake fill or combined budget ledger mismatch")


def prepare_connected_hybrid_lake_detail(plan, detail, *, source_sha256, domain_id):
    """New bounded lake-only correction layer; parent/source/boundary unchanged.

    No canonical core crop identity is claimed. D4 priority flood raises only
    internal depressions to the minimum real patch-boundary saddle. The coarse
    ring must subsequently be wet across the freshly solved periodic range.
    """
    from terrain_pipeline.hydrology_detail import DetailBudget, _digest as detail_digest
    metadata, height, owners, spacing, origin = _checked_detail(plan, detail, source_sha256)
    domains = [d for d in plan["domains"] if d["domain_id"] == domain_id and d["kind"] == "inland"]
    if len(domains) != 1 or np.any(owners != domain_id):
        raise ValueError("one immutable inland owner across the local lake correction required")
    arrays = detail["arrays"]
    raw = np.asarray(arrays["original_td_m"])
    macro = np.asarray(arrays["macro_delta_m"])
    channel = np.asarray(arrays["local_channel_delta_m"])
    protected = np.asarray(arrays["shared_boundary_protected"])
    if (any(a.shape != height.shape for a in (raw, macro, channel, protected)) or protected.dtype != bool
            or not all(np.isfinite(a).all() for a in (raw, macro, channel))
            or not np.allclose(raw + macro + channel, height, rtol=0, atol=1e-6)):
        raise ValueError("matched raw/macro/channel source arrays and shared-boundary protection required")
    coarse_spacing = float(plan["spacing_m"])
    coarse_origin = np.asarray(plan["origin_xz_m"])
    lower = origin - spacing / 2
    upper = origin + np.array([height.shape[1] - 1, height.shape[0] - 1]) * spacing + spacing / 2
    low_parent = np.floor((lower - coarse_origin + coarse_spacing / 2) / coarse_spacing).astype(int)
    high_parent = np.ceil((upper - coarse_origin + coarse_spacing / 2) / coarse_spacing).astype(int) - 1
    if (not np.array_equal(low_parent, high_parent) or (low_parent < 0).any()
            or low_parent[0] >= plan["height_m"].shape[1] or low_parent[1] >= plan["height_m"].shape[0]):
        raise ValueError("local correction requires a patch strictly inside one coarse lake cell")
    coarse_center = coarse_origin + low_parent * coarse_spacing
    if not np.all(lower > coarse_center - coarse_spacing / 2) or not np.all(upper < coarse_center + coarse_spacing / 2):
        raise ValueError("fine patch boundary must preserve a known uncovered coarse support ring")
    lake = LakeGeometry(plan["height_m"], plan["owner_domain_id"], domains[0], coarse_spacing**2)
    if not lake.mask[low_parent[1], low_parent[0]]:
        raise ValueError("local correction lacks registered coarse lake support")
    filled = fill_lake_patch_to_boundary_saddles(height)
    delta = filled - height
    if np.any(delta[protected] != 0):
        raise ValueError("minimum lake depression fill would alter a protected shared boundary")
    if not np.array_equal(filled[[0, -1], :], height[[0, -1], :]) or not np.array_equal(filled[:, [0, -1]], height[:, [0, -1]]):
        raise ValueError("lake correction changed immutable patch boundary")
    new_macro = macro + delta
    total = filled - raw
    budget = DetailBudget(**metadata["budget"])
    ledger = {"macro_max_abs_m": float(np.abs(new_macro).max()),
              "total_max_abs_m": float(np.abs(total).max()),
              "macro_absolute_volume_m3": float(np.abs(new_macro).sum() * spacing**2),
              "total_absolute_volume_m3": float(np.abs(total).sum() * spacing**2),
              "channel_max_cut_m": float(max(0., -channel.min()))}
    violations = [name for name, value in ledger.items() if value > getattr(budget, name)]
    if violations:
        raise ValueError("combined local lake correction exceeds frozen budget: " + ", ".join(violations))
    new_arrays = {"original_td_m": raw.copy(), "derived_height_m": filled,
                  "owner_domain_id": owners.copy(), "macro_delta_m": new_macro,
                  "local_channel_delta_m": channel.copy(), "total_delta_m": total,
                  "shared_boundary_protected": protected.copy(), "lake_depression_fill_m": delta}
    correction = {"algorithm": "local-lake-d4-minimum-boundary-saddle-fill-v1",
                  "source_detail_identity_sha256": metadata["identity"], "source_detail_archive_sha256": source_sha256,
                  "parent_coarse_cell_id": int(low_parent[1] * plan["height_m"].shape[1] + low_parent[0]),
                  "filled_pixel_count": int(np.count_nonzero(delta)),
                  "filled_area_m2": float(np.count_nonzero(delta) * spacing**2),
                  "maximum_fill_m": float(delta.max()), "fill_volume_m3": float(delta.sum() * spacing**2),
                  "patch_boundary_unchanged": True, "parent_coarse_plan_unchanged": True,
                  "raw_td_unchanged": True, "canonical_core_exact_crop": False,
                  "budget": metadata["budget"], "combined_ledger": ledger,
                  "scope": "new lake-only correction above frozen derived TD; no changed seasonal water-level clamp"}
    new_metadata = {"schema": "hydrology-local-connected-lake-basin-v1",
                    "algorithm": correction["algorithm"], "window_kind": "lake_shore",
                    "plan_identity": plan["identity_sha256"], "origin_xz_m": origin.tolist(), "spacing_m": spacing,
                    "budget": metadata["budget"], "raw_provenance": metadata["raw_provenance"],
                    "lake_correction": correction, "ledger": ledger,
                    "status": "budget_verified_periodic_cycle_and_connectivity_pending",
                    "fine_geometry_certified": False, "global_hydrology_certified": False}
    new_metadata["identity"] = detail_digest({"metadata": new_metadata, "arrays": {
        name: hashlib.sha256(value.tobytes()).hexdigest() for name, value in sorted(new_arrays.items())}})
    return {"arrays": new_arrays, "metadata": new_metadata}


def save_hybrid_lake_bundle(parent_plan, detail, bundle, output, *, source_path, source_sha256):
    """Publish a new pinned bundle, including exact fine source and column plan."""
    from terrain_pipeline.hydrology_detail import file_sha256
    from terrain_pipeline.hydrology_seasonal import save_seasonal_water_balance
    source_path = Path(source_path)
    if file_sha256(source_path) != source_sha256:
        raise ValueError("fine source archive changed before bundle publication")
    if source_sha256 != bundle["audit"]["fine_detail_archive_sha256"]:
        raise ValueError("bundle fine source pin differs from the prepared lake")
    connectivity = validate_hybrid_lake_connectivity(parent_plan, detail, bundle, bundle["result"])
    if connectivity != bundle["connectivity"]:
        raise ValueError("bundle connectivity differs from actual periodic geometry")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    fine_path = output / "fine-detail.npz"
    with source_path.open("rb") as source, fine_path.open("xb") as target:
        shutil.copyfileobj(source, target)
    plan = bundle["plan"]
    plan_metadata = {key: plan[key] for key in ("seed", "origin_xz_m", "spacing_m", "domains",
                                               "seasonal_hybrid", "identity_sha256")}
    payload = {key: np.ascontiguousarray(plan[key]) for key in COLUMN_ARRAYS}
    payload.update({"climate__" + key: np.ascontiguousarray(value) for key, value in bundle["climate"].items()})
    payload["metadata_json"] = np.array(json.dumps(plan_metadata, allow_nan=False))
    plan_path = output / "column-plan-climate.npz"
    with plan_path.open("xb") as stream:
        np.savez_compressed(stream, **payload)
    seasonal_path = output / "seasonal.npz"
    save_seasonal_water_balance(plan, bundle["result"], seasonal_path)
    manifest = {"schema": "hydrology-hybrid-lake-seasonal-bundle-v1",
                "water_step_algorithm": bundle["result"]["metadata"].get("water_step_algorithm"),
                "periodic_solver_algorithm": bundle["result"]["metadata"].get("periodic_solver_algorithm"),
                "shore_event_schema": bundle["result"]["metadata"].get("shore_event_schema"),
                "parent_plan_identity_sha256": parent_plan["identity_sha256"],
                "hybrid_plan_identity_sha256": plan["identity_sha256"],
                "fine_source_original_path": str(source_path.resolve()),
                "fine_source_sha256": source_sha256,
                "column_plan_climate_sha256": file_sha256(plan_path),
                "seasonal_sha256": file_sha256(seasonal_path), "replacement_audit": bundle["audit"],
                "connectivity": connectivity,
                "status": ("verified_local_periodic_lake" if connectivity["fine_geometry_certified"]
                           else "periodic_accounts_converged_local_geometry_rejected"),
                "global_hydrology_certified": False}
    manifest["identity_sha256"] = _digest(manifest)
    manifest_path = output / "hybrid-bundle.json"
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
    with manifest_path.with_suffix(".sha256").open("x", encoding="ascii") as stream:
        stream.write(file_sha256(manifest_path))
    return manifest


def load_hybrid_lake_bundle(parent_plan, output):
    """Rebuild replacement geometry from pinned source and cold-audit the cycle."""
    from terrain_pipeline.hydrology_detail import file_sha256
    from terrain_pipeline.hydrology_seasonal import load_seasonal_water_balance
    from terrain_pipeline.mountain_source_adapter import checked_archive
    output = Path(output)
    manifest_path = output / "hybrid-bundle.json"
    if file_sha256(manifest_path) != manifest_path.with_suffix(".sha256").read_text(encoding="ascii").strip():
        raise ValueError("hybrid bundle manifest pin mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    unsigned = {key: value for key, value in manifest.items() if key != "identity_sha256"}
    if (manifest.get("schema") != "hydrology-hybrid-lake-seasonal-bundle-v1"
            or manifest["identity_sha256"] != _digest(unsigned)
            or manifest["parent_plan_identity_sha256"] != parent_plan["identity_sha256"]):
        raise ValueError("hybrid bundle schema, identity or parent mismatch")
    archive = checked_archive(output / "column-plan-climate.npz", expected_sha256=manifest["column_plan_climate_sha256"])
    plan = json.loads(str(archive["metadata_json"].item()))
    plan.update({key: archive[key] for key in COLUMN_ARRAYS})
    climate = {key.split("__", 1)[1]: value for key, value in archive.items() if key.startswith("climate__")}
    hybrid_column_inputs(plan, climate)
    detail = load_hybrid_lake_detail(output / "fine-detail.npz", manifest["fine_source_sha256"])
    parents = plan["seasonal_parent_cell_id"].ravel()
    coarse_climate = {}
    for name, values in climate.items():
        coarse_values = np.empty((12, parent_plan["height_m"].size), dtype=values.dtype)
        coarse_values[:, parents] = values[:, 0, :]
        if not np.array_equal(coarse_values[:, parents], values[:, 0, :]):
            raise ValueError("saved hybrid forcing does not inherit one parent climate per cell")
        coarse_climate[name] = coarse_values.reshape((12,) + parent_plan["height_m"].shape)
    prepared = prepare_hybrid_lake_plan(parent_plan, detail, source_sha256=manifest["fine_source_sha256"],
        domain_id=manifest["replacement_audit"]["domain_id"], coarse_climate=coarse_climate)
    if (prepared["audit"] != manifest["replacement_audit"] or prepared["audit"] != plan["seasonal_hybrid"]
            or prepared["plan"]["identity_sha256"] != manifest["hybrid_plan_identity_sha256"]):
        raise ValueError("saved hybrid replacement differs from the real fine source and parent geometry")
    seasonal_path = output / "seasonal.npz"
    if file_sha256(seasonal_path) != manifest["seasonal_sha256"]:
        raise ValueError("saved hybrid seasonal archive pin mismatch")
    result = load_seasonal_water_balance(prepared["plan"], seasonal_path)
    for name in ("water_step_algorithm", "periodic_solver_algorithm", "shore_event_schema"):
        if name in manifest and manifest[name] != result["metadata"].get(name):
            raise ValueError("hybrid manifest seasonal algorithm differs: " + name)
    connectivity = validate_hybrid_lake_connectivity(parent_plan, detail, prepared, result)
    if connectivity != manifest["connectivity"]:
        raise ValueError("saved hybrid cycle connectivity report differs from cold geometry")
    return {**prepared, "result": result, "connectivity": connectivity, "manifest": manifest, "detail": detail}
