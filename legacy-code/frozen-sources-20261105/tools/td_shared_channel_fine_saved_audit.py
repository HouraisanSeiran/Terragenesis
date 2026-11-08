"""Independent native-source, affine-fan and streamed-grid audit primitives."""

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import zipfile

import numpy as np
import psutil


ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 64 * 1024**2
MAX_RSS = 1024**3
MAX_CELLS = 2_000_000
MAX_TILES = 16384
LEDGER_KEYS = ("cut_rock_m3", "exported_excavated_rock_m3", "solid_fill_m3",
               "sediment_deposited_solid_m3", "sediment_deposited_bulk_m3",
               "sediment_pore_m3", "external_fill_import_m3")
POLICY = {"schema": "td-shared-channel-fine-v1",
    "source": "unchanged_original_native_bilinear_height",
    "bed": "only_accepted_task14_saved_source_minus_affine_cut_fans",
    "grid": "native_origin_fixed_spacing_0.175m_rows_z_columns_x_sparse_unique_integer_cells",
    "budget": "exact_positive_area_intersection_unique_cells_preflight_all_or_none",
    "cut_evaluation": "saved_affine_fan_via_congruent_nonnegative_vertex_convex_interpolation_exact_support_endpoints_no_clamp",
    "material": "actual_fan_intersection_cell_polygon_affine_cut_area_integral",
    "outside_center": "unchanged_source_even_if_cell_has_partial_material_coverage",
    "rock": "all_excavated_rock_exported_zero_fill_zero_sediment_conversion",
    "hydraulics": "not_generated_no_solver_no_old_carrier_acceptance"}
FLAGS = {"fine_generated": True, "hydraulic_ready": False, "hydraulic_solved": False,
         "material_budget_verified": False, "full_network_verified": False,
         "natural_outlet_certified": False, "old_source_changed": False, "old_fine_changed": False}
PARAMETERS = {"spacing_m": .175, "tile_cells": 64, "max_cells": MAX_CELLS,
              "max_cut_m": 4., "max_tiles": MAX_TILES, "max_json_bytes": MAX_BYTES, "max_rss_bytes": MAX_RSS,
              "function_difference_tolerance_m": 1e-9, "integral_absolute_tolerance": 1e-8,
              "integral_relative_tolerance": 1e-9}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(record):
    result = hashlib.sha256()
    for fragment in json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False).iterencode(record):
        result.update(fragment.encode("utf-8"))
    return result.hexdigest()


POLICY_SHA256 = digest(POLICY)
PARAMETERS_SHA256 = digest(PARAMETERS)


def file_sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            result.update(block)
    return result.hexdigest()


def check_memory():
    memory = psutil.Process().memory_info()
    peak = max(memory.rss, getattr(memory, "peak_wset", 0))
    require(peak <= MAX_RSS, "independent fine audit exceeds 1GiB RSS")
    return peak


def check_identity(record):
    require(record.get("identity_sha256") == digest({key: value for key, value in record.items() if key != "identity_sha256"}), "saved content identity mismatch")


def checked_path(pin):
    require(Path(pin["path"]).is_absolute(), "absolute saved input path required")
    path = Path(pin["path"]).resolve(strict=True)
    require(path.is_relative_to(ROOT) and path.is_file() and path.stat().st_size <= MAX_BYTES,
            "input path/64MiB budget mismatch")
    require(file_sha256(path) == pin["sha256"], "input file SHA256 mismatch")
    if "bytes" in pin:
        require(pin["bytes"] == path.stat().st_size, "input byte-count pin mismatch")
    return path


def read(pin):
    record = json.loads(checked_path(pin).read_bytes())
    check_identity(record)
    if "identity_sha256" in pin:
        require(record["identity_sha256"] == pin["identity_sha256"], "external record identity mismatch")
    check_memory()
    return record


def read_audit(pin):
    record = json.loads(checked_path(pin).read_bytes())
    if "identity_sha256" in record:
        check_identity(record)
    return record


def pin_signature(pin):
    require(isinstance(pin, dict) and "path" in pin and "sha256" in pin, "missing path/SHA pin")
    return str(Path(pin["path"]).resolve()), pin["sha256"], pin.get("identity_sha256")


def compare(actual, expected, label, atol=1e-9, rtol=0.):
    actual, expected = np.asarray(actual), np.asarray(expected)
    require(actual.shape == expected.shape and np.isfinite(actual).all() and np.isfinite(expected).all()
            and np.allclose(actual, expected, atol=atol, rtol=rtol), "fine audit mismatch: " + label)


@dataclass
class NativeSource:
    arrays: dict
    metadata: dict
    selected_leaves: set
    wet_protection: dict

    def __post_init__(self):
        self.height = self.arrays["height_m"]
        self.origin = np.asarray(self.metadata["origin_m_xz"], float)
        self.spacing = float(self.metadata["spacing_m"])
        require(self.height.ndim == 2 and min(self.height.shape) >= 2 and self.height.size <= 250000
                and self.origin.shape == (2,) and np.isfinite(self.origin).all()
                and math.isfinite(self.spacing) and self.spacing > 0., "invalid native source")
        for name in ("valid_mask", "protected_mask", "open_boundary_mask", "cell_owner", "contribution_owner"):
            require(self.arrays[name].shape == self.height.shape, "native source mask/owner shape mismatch")
        self.covered = set(self.wet_protection["covered_native_cell_ids"])
        self.stages = {item["leaf_id"]: item["stage_m"] for item in self.wet_protection["stage_by_leaf"]}

    def sample(self, point):
        point = np.asarray(point, float)
        require(point.shape == (2,) and np.isfinite(point).all(), "nonfinite native sample coordinate")
        position = (point-self.origin)/self.spacing
        rows, columns = self.height.shape
        provenance = {"native_cell_ids": [], "weights": [], "owner_ids": [], "contribution_leaf_ids": []}
        if np.any(position < 0.) or position[0] > columns-1 or position[1] > rows-1:
            return {"height_m": None, "rejection_reasons": ["outside_native_dem"], "wet_source_support": False, **provenance}
        column = min(math.floor(position[0]), columns-2)
        row = min(math.floor(position[1]), rows-2)
        horizontal, vertical = position-[column, row]
        weights = [(1-horizontal)*(1-vertical), horizontal*(1-vertical), (1-horizontal)*vertical, horizontal*vertical]
        corners = [(row, column), (row, column+1), (row+1, column), (row+1, column+1)]
        reasons, heights = set(), []
        unknown = self.arrays["node_unknown_contact"]
        for (native_row, native_column), weight in zip(corners, weights):
            if weight == 0.:
                continue
            owner = int(self.arrays["cell_owner"][native_row, native_column])
            leaf = int(self.arrays["contribution_owner"][native_row, native_column])
            provenance["native_cell_ids"].append(native_row*columns+native_column)
            provenance["weights"].append(float(weight))
            provenance["owner_ids"].append(owner)
            provenance["contribution_leaf_ids"].append(leaf)
            if leaf not in self.selected_leaves:
                reasons.add("outside_selected_component")
            for mask, reason in (("valid_mask", "unknown_native_corner"), ("protected_mask", "protected_native_corner"),
                                 ("open_boundary_mask", "open_boundary_native_corner")):
                invalid = not self.arrays[mask][native_row, native_column] if mask == "valid_mask" else self.arrays[mask][native_row, native_column]
                if invalid:
                    reasons.add(reason)
            if owner < 0 or leaf < 0 or owner >= len(unknown) or leaf >= len(unknown) or unknown[owner] or unknown[leaf]:
                reasons.add("unknown_native_owner")
            value = float(self.height[native_row, native_column])
            if not math.isfinite(value):
                reasons.add("nonfinite_native_height")
            else:
                heights.append(float(weight)*value)
        height = None if reasons & {"unknown_native_corner", "nonfinite_native_height"} else math.fsum(heights)
        nearest_column, nearest_row = np.floor(position+.5).astype(int)
        nearest_leaf = int(self.arrays["contribution_owner"][nearest_row, nearest_column])
        wet = nearest_row*columns+nearest_column in self.covered or height is not None and height < self.stages.get(nearest_leaf, -math.inf)
        return {"height_m": height, "rejection_reasons": sorted(reasons), "wet_source_support": bool(wet), **provenance}


def load_native(pin, selected_leaves, protection):
    path = checked_path(pin)
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        require(len(members) <= 128 and len({member.filename for member in members}) == len(members)
                and sum(member.file_size for member in members) <= MAX_RSS//2, "native archive expansion exceeds budget")
    names = ("height_m", "valid_mask", "protected_mask", "open_boundary_mask", "cell_owner", "contribution_owner", "node_unknown_contact")
    with np.load(path, allow_pickle=False) as bundle:
        manifest = json.loads(bytes(bundle["manifest"]))
        require(manifest["identity_sha256"] == pin["identity_sha256"], "native hierarchy identity mismatch")
        arrays = {name: bundle[name].copy() for name in names}
    check_memory()
    return NativeSource(arrays, manifest["metadata"], set(selected_leaves), protection)


@dataclass
class Fan:
    saved: dict

    def __post_init__(self):
        self.key = self.saved["fan_key"]
        self.points = np.asarray(self.saved["vertices_xz_m"], float)
        self.depths = np.asarray(self.saved["depth_at_vertices_m"], float)
        self.origin = np.asarray(self.saved["depth_origin_xz_m"], float)
        self.coefficients = np.asarray(self.saved["depth_coefficients_m_1xz"], float)
        require(self.points.shape == (3, 2) and self.depths.shape == (3,) and self.origin.shape == (2,)
                and self.coefficients.shape == (3,) and all(np.isfinite(value).all() for value in (self.points, self.depths, self.origin, self.coefficients)), "invalid affine fan")
        require(np.all(self.depths >= 0.) and np.all(self.depths <= 4.), "strict fan no-fill/4m constraint failed")
        self.matrix = (self.points[1:]-self.points[0]).T
        first, second = self.matrix[:, 0], self.matrix[:, 1]
        self.determinant = float(first[0]*second[1]-first[1]*second[0])
        self.area = abs(self.determinant)/2
        require(self.area > 1e-14, "degenerate affine fan")
        predicted_supports = self.coefficients[0]+(self.points-self.origin)@self.coefficients[1:]
        compare(predicted_supports, self.depths, "saved affine polynomial at all support vertices")
        self.volume = self.area*math.fsum(self.depths.tolist())/3
        compare(self.saved["projected_area_m2"], self.area, "full fan area", atol=1e-10)
        compare(self.saved["expected_integrated_cut_m3"], self.volume, "full fan affine material integral", atol=1e-10)

    def center_cut(self, point):
        point = np.asarray(point, float)
        for vertex, depth in zip(self.points, self.depths):
            if np.array_equal(point, vertex):
                return float(depth)
        offset = point-self.points[0]
        first, second = self.matrix[:, 0], self.matrix[:, 1]
        weight_first = float((offset[0]*second[1]-offset[1]*second[0])/self.determinant)
        weight_second = float((first[0]*offset[1]-first[1]*offset[0])/self.determinant)
        weights = [1-weight_first-weight_second, weight_first, weight_second]
        if min(weights) < 0.:
            return None
        depth = float(self.depths[0]) if np.all(self.depths == self.depths[0]) else math.fsum(weight*float(value) for weight, value in zip(weights, self.depths))
        require(0. <= depth <= 4., "strict fan center cut invalid; no clamp")
        return depth


def cell_intersection(fan, row, column, grid):
    vertices = (fan.points-np.asarray(grid["origin_m_xz"]))/grid["spacing_m"]-[column, row]
    polygon = [[float(point[0]), float(point[1]), float(depth)] for point, depth in zip(vertices, fan.depths)]
    for axis, bound, sign in ((0, 0., 1), (0, 1., -1), (1, 0., 1), (1, 1., -1)):
        output = []
        for first, second in zip(polygon, polygon[1:]+polygon[:1]):
            first_distance = sign*(first[axis]-bound)
            second_distance = sign*(second[axis]-bound)
            if first_distance >= 0.:
                output.append(first)
            if (first_distance >= 0.) != (second_distance >= 0.):
                fraction = first_distance/(first_distance-second_distance)
                require(0. <= fraction <= 1., "invalid independent clip fraction")
                if fraction == 0.:
                    crossing = list(first)
                elif fraction == 1.:
                    crossing = list(second)
                else:
                    crossing = [(1-fraction)*left+fraction*right for left, right in zip(first, second)]
                crossing[axis] = bound
                output.append(crossing)
        polygon = output
    area, volume = integrate_polygon(polygon, grid["spacing_m"])
    return polygon, area, volume


def integrate_polygon(polygon, spacing):
    if len(polygon) < 3:
        return 0., 0.
    points = np.asarray(polygon, float)
    require(points.ndim == 2 and points.shape[1] == 3 and np.isfinite(points).all()
            and np.all(points[:, 2] >= 0.) and np.all(points[:, 2] <= 4.), "invalid clipped support cut; no clamp")
    areas, volumes = [], []
    anchor = points[0]
    for first, second in zip(points[1:], points[2:]):
        offset_first, offset_second = first[:2]-anchor[:2], second[:2]-anchor[:2]
        area = abs(float(offset_first[0]*offset_second[1]-offset_first[1]*offset_second[0]))*spacing**2/2
        areas.append(area)
        volumes.append(area*math.fsum([anchor[2], first[2], second[2]])/3)
    return math.fsum(areas), math.fsum(volumes)


def tile_candidates(fans, grid):
    result = defaultdict(list)
    tile_size = grid["tile_cells"]
    visits = 0
    for fan in fans.values():
        vertices = (fan.points-np.asarray(grid["origin_m_xz"]))/grid["spacing_m"]
        low = np.floor(vertices.min(axis=0)).astype(int)
        high = np.ceil(vertices.max(axis=0)).astype(int)-1
        visits += max(0, int(high[0]-low[0]+1))*max(0, int(high[1]-low[1]+1))
        require(visits <= MAX_CELLS*64, "independent fan-cell bbox visit budget exceeded")
        for tile_row in range(int(low[1])//tile_size, int(high[1])//tile_size+1):
            for tile_column in range(int(low[0])//tile_size, int(high[0])//tile_size+1):
                result[(tile_row, tile_column)].append(fan.key)
        require(len(result) <= MAX_TILES, "independent tile candidate budget exceeded")
    return result, visits


class GlobalGrid:
    def __init__(self, grid):
        self.grid = grid
        self.tiles = set()
        self.cell_count = 0
        self.previous_tile = None

    def begin_tile(self, key):
        require(len(key) == 2 and all(type(value) is int for value in key), "noninteger tile coordinate")
        key = tuple(key)
        require(key not in self.tiles and (self.previous_tile is None or key > self.previous_tile), "duplicate or out-of-order tile")
        self.tiles.add(key)
        require(len(self.tiles) <= MAX_TILES, "global tile budget exceeded")
        self.previous_tile = key
        self.current = key
        self.mask = 0
        self.previous_local = -1

    def accept_cell(self, cell):
        tile_size = self.grid["tile_cells"]
        row, column, local = (cell[name] for name in ("global_row", "global_col", "local_index"))
        require(all(type(value) is int for value in (row, column, local)) and 0 <= local < tile_size**2,
                "invalid global/local cell integer key")
        require((row//tile_size, column//tile_size) == self.current
                and local == row%tile_size*tile_size+column%tile_size, "cell outside canonical tile / global key mismatch")
        bit = 1 << local
        require(not self.mask & bit and local > self.previous_local, "duplicate or out-of-order global cell")
        self.mask |= bit
        self.previous_local = local
        self.cell_count += 1
        require(self.cell_count <= MAX_CELLS, "global unique fine cell budget exceeded")


class Sum:
    def __init__(self):
        self.value = 0.
        self.correction = 0.

    def add(self, value):
        total = self.value+value
        self.correction += (self.value-total)+value if abs(self.value) >= abs(value) else (value-total)+self.value
        self.value = total

    def total(self):
        return self.value+self.correction


def audit_ledger(ledger, volume):
    require(set(ledger) == set(LEDGER_KEYS), "material ledger keys differ")
    for name in LEDGER_KEYS:
        require(math.isfinite(ledger[name]) and ledger[name] >= 0., "negative/nonfinite material ledger")
        if name not in ("cut_rock_m3", "exported_excavated_rock_m3"):
            require(ledger[name] == 0., "nonzero fill/sediment/import ledger")
        compare(ledger[name], volume if name in ("cut_rock_m3", "exported_excavated_rock_m3") else 0.,
                "material ledger " + name, atol=1e-8, rtol=1e-10)


def expected_tile_intersections(fans, candidate_keys, key, grid):
    tile_size = grid["tile_cells"]
    tile_row, tile_column = key
    row_base, column_base = tile_row*tile_size, tile_column*tile_size
    result = defaultdict(dict)
    for fan_key in candidate_keys:
        fan = fans[fan_key]
        vertices = (fan.points-np.asarray(grid["origin_m_xz"]))/grid["spacing_m"]
        low = np.floor(vertices.min(axis=0)).astype(int)
        high = np.ceil(vertices.max(axis=0)).astype(int)-1
        for row in range(max(row_base, int(low[1])), min(row_base+tile_size-1, int(high[1]))+1):
            for column in range(max(column_base, int(low[0])), min(column_base+tile_size-1, int(high[0]))+1):
                polygon, area, volume = cell_intersection(fan, row, column, grid)
                if area > 0.:
                    local = (row-row_base)*tile_size+column-column_base
                    result[local][fan_key] = (polygon, area, volume)
    return result


def audit_tile(tile, fans, expected, source, global_grid):
    grid = global_grid.grid
    tile_size, spacing = grid["tile_cells"], grid["spacing_m"]
    key = tuple(tile["tile_row_column"])
    require(tile["grid"] == grid and tile["global_origin_row_column"] == [value*tile_size for value in key], "tile grid/origin mismatch")
    global_grid.begin_tile(tile["tile_row_column"])
    contribution_pairs = set()
    actual_by_cell = defaultdict(dict)
    totals = defaultdict(lambda: [[], []])
    contributions = tile["contributions"]
    for index, contribution in enumerate(contributions):
        row, column, local = (contribution[name] for name in ("global_row", "global_col", "local_index"))
        require(all(type(value) is int for value in (row, column, local))
                and (row//tile_size, column//tile_size) == key
                and local == row%tile_size*tile_size+column%tile_size, "invalid contribution global/tile/local key")
        fan_key = contribution["fan_key"]
        require(fan_key in fans and contribution["fan_id"] == fans[fan_key].saved["fan_id"], "contribution fan identity mismatch")
        require((local, fan_key) not in contribution_pairs, "fan/cell counted more than once")
        contribution_pairs.add((local, fan_key))
        require(local in expected and fan_key in expected[local], "contribution does not intersect actual saved fan")
        polygon, area, volume = expected[local][fan_key]
        actual_polygon = contribution["polygon_cell_local_uv_cut_m"]
        integrate_polygon(actual_polygon, spacing)
        require(contribution["coverage_area_m2"] > 0. and contribution["integrated_cut_m3"] >= 0., "negative/empty saved contribution")
        compare(actual_polygon, polygon, "actual fan/cell polygon and affine support", atol=1e-9)
        world = [[grid["origin_m_xz"][0]+(column+point[0])*spacing,
                  grid["origin_m_xz"][1]+(row+point[1])*spacing] for point in polygon]
        compare(contribution["polygon_xz_m"], world, "material polygon world witness", atol=1e-8)
        compare(contribution["coverage_area_m2"], area, "fan/cell area", atol=1e-10)
        compare(contribution["integrated_cut_m3"], volume, "fan/cell affine integral", atol=1e-10)
        actual_by_cell[local][fan_key] = index
        totals[fan_key][0].append(area)
        totals[fan_key][1].append(volume)
    expected_pairs = {(local, fan_key) for local, entries in expected.items() for fan_key in entries}
    require(contribution_pairs == expected_pairs, "missing actual fan/cell intersections")
    require(len(tile["cells"]) == len(expected) > 0, "sparse tile cell coverage differs")
    centers, invalid_centers, outside_centers = [], 0, 0
    seen_cells = set()
    for cell in tile["cells"]:
        global_grid.accept_cell(cell)
        local = cell["local_index"]
        require(local in expected and local not in seen_cells, "missing/duplicate sparse cell")
        seen_cells.add(local)
        row, column = cell["global_row"], cell["global_col"]
        point = np.asarray(grid["origin_m_xz"])+(np.asarray([column, row])+.5)*spacing
        compare(cell["center_xz_m"], point, "global cell center", atol=1e-10)
        sample = source.sample(point)
        saved_sample = cell["source_sample"]
        require(set(saved_sample) == set(sample), "source sample fields differ")
        for name in ("native_cell_ids", "owner_ids", "contribution_leaf_ids", "rejection_reasons", "wet_source_support"):
            require(saved_sample[name] == sample[name], "native provenance/validity mismatch: " + name)
        compare(saved_sample["weights"], sample["weights"], "native bilinear weights", atol=1e-12)
        for value in (saved_sample["height_m"], cell["source_height_m"]):
            if sample["height_m"] is None:
                require(value is None, "unknown native source falsely filled")
            else:
                compare(value, sample["height_m"], "original native bilinear height")
        require(type(cell["valid"]) is bool and cell["valid"] == (not sample["rejection_reasons"] and sample["height_m"] is not None), "fine cell valid mask differs")
        invalid_centers += not cell["valid"]
        owners, cuts = [], []
        for fan_key in expected[local]:
            cut = fans[fan_key].center_cut(point)
            if cut is not None:
                owners.append(fan_key)
                cuts.append(cut)
        require(type(cell["center_inside"]) is bool and cell["center_inside"] == bool(owners)
                and sorted(cell["center_fan_keys"]) == sorted(owners), "center support fan census mismatch")
        if cuts:
            require(max(cuts)-min(cuts) <= 1e-9 and not sample["rejection_reasons"] and sample["height_m"] is not None, "covered center invalid or shared fan cuts inconsistent")
        cut = cuts[0] if cuts else 0.
        require(0. <= cut <= 4. and not (cut > 0. and sample["wet_source_support"]), "fine center violates strict no-fill/4m/wet gate")
        require(0. <= cell["cut_depth_m"] <= 4., "saved fine center cut violates strict no-fill/4m")
        compare(cell["cut_depth_m"], cut, "center affine cut")
        bed = sample["height_m"] if not cuts or sample["height_m"] is None else sample["height_m"]-cut
        if bed is None:
            require(cell["derived_bed_m"] is None, "invalid source has fabricated bed")
        else:
            compare(cell["derived_bed_m"], bed, "source minus actual center cut")
            require(cell["derived_bed_m"] <= cell["source_height_m"], "saved fine bed violates no-fill")
        outside_centers += not owners
        if not owners:
            require(cell["derived_bed_m"] == cell["source_height_m"] and cell["cut_depth_m"] == 0., "outside fan center changed original source")
        indices = cell["contribution_indices"]
        require(all(type(value) is int for value in indices) and len(indices) == len(set(indices))
                and set(indices) == set(actual_by_cell[local].values()), "cell contribution references missing/duplicate/foreign")
        area = math.fsum(value[1] for value in expected[local].values())
        volume = math.fsum(value[2] for value in expected[local].values())
        require(area <= spacing**2+1e-10, "positive fan overlap in fine cell")
        compare(cell["coverage_area_m2"], area, "fine cell coverage area", atol=1e-10)
        compare(cell["integrated_cut_m3"], volume, "fine cell exact affine material", atol=1e-10)
        centers.append(cut*spacing**2)
    require(seen_cells == set(expected), "missing sparse affected cell")
    saved_totals = {item["fan_key"]: item for item in tile["fan_integrals"]}
    require(len(saved_totals) == len(tile["fan_integrals"]) and set(saved_totals) == set(totals), "tile fan integral census differs")
    independent = {}
    for fan_key, (areas, volumes) in totals.items():
        area, volume = math.fsum(areas), math.fsum(volumes)
        require(saved_totals[fan_key]["fan_id"] == fans[fan_key].saved["fan_id"], "tile material fan reference differs")
        compare(saved_totals[fan_key]["coverage_area_m2"], area, "tile per-fan area", atol=1e-8, rtol=1e-10)
        compare(saved_totals[fan_key]["integrated_cut_m3"], volume, "tile per-fan affine material", atol=1e-8, rtol=1e-10)
        independent[fan_key] = (area, volume)
    volume = math.fsum(value[1] for value in independent.values())
    center_volume = math.fsum(centers)
    audit_ledger(tile["material_ledger"], volume)
    compare(tile["center_sample_cut_volume_m3"], center_volume, "tile sampled-center quadrature", atol=1e-8, rtol=1e-10)
    check_memory()
    return {"fan_integrals": independent, "integrated_cut_m3": volume, "center_sample_cut_volume_m3": center_volume,
            "contribution_count": len(contributions), "cell_count": len(seen_cells),
            "invalid_outside_centers": int(invalid_centers), "outside_fan_centers": int(outside_centers)}
