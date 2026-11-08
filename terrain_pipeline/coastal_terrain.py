"""海岸底图、海岸细化与群岛产品线（A 类）。

合并自 `coastal_detail_refinement`、`coastal_archipelago`、`coastal_terrain_product`、
`coastal_archipelago_product`、`coastal_detail_product`（本模块原有的
`CoastalParameters` / `coastal_support` / `compose` / `classify` 保留原名）。
同组重名的 `prepare` / `read_product` / `identity` / `array_hash` 按产品线起命名变体：
`prepare_terrain_bed` / `read_terrain_product` / `array_hash_contiguous`、
`prepare_archipelago` / `read_archipelago_product` / `identity_archipelago` /
`archipelago_anchor`、`prepare_detail` / `read_detail_product` / `identity_detail` /
`array_hash_rowchunk`。
"""


from terrain_pipeline.common_infra import published_algorithm_matches, published_algorithm_hashes

# ========================================================================
# 外部依赖（合并前各旧文件的 import，去重后集中在此）
# ========================================================================
from dataclasses import dataclass
import numpy as np
from scipy.ndimage import gaussian_filter, label, binary_dilation, distance_transform_edt
from scipy.ndimage import gaussian_filter, distance_transform_edt, binary_dilation
import hashlib
from diffusion.geographic_noise import smooth_noise
import json
import os
from pathlib import Path
import shutil
import tempfile
from dataclasses import asdict
import psutil
from terrain_pipeline.tectonic import load_product
import math



# ------------------------------------------------------------------------
# 原 terrain_pipeline/coastal_terrain.py
# ------------------------------------------------------------------------

@dataclass(frozen=True)
class CoastalParameters:
    spacing_m: float = 30.0
    sigma_m: float = 720.0
    radius_m: float = 2880.0
    transition_elevation_m: float = 300.0
    coast_band_m: float = 6000.0
    nearshore_allowance_m: float = 200.0
    far_fraction: float = 0.85
    low_fraction: float = 0.65
    sea_m: float = 0.0

    def validate(self):
        values = np.array(list(self.__dict__.values()), dtype=float)
        if not np.isfinite(values).all() or min(self.spacing_m, self.sigma_m, self.radius_m, self.transition_elevation_m, self.coast_band_m) <= 0 or self.nearshore_allowance_m < 0 or not 0 <= self.far_fraction < 1 or not 0 <= self.low_fraction <= 1:
            raise ValueError("invalid coastal parameters")
        if self.coast_band_m < self.radius_m or abs(self.coast_band_m / self.spacing_m - round(self.coast_band_m / self.spacing_m)) > 1e-9:
            raise ValueError("coast band must be whole cells and cover filter")
        cells = self.radius_m / self.spacing_m
        if abs(cells - round(cells)) > 1e-9 or cells < 1:
            raise ValueError("filter radius must be whole cells")
        return int(round(cells))


def coastal_support(macro, params=CoastalParameters(), *, anchors=None):
    """Fixed-domain distance weight; callers crop this field, never recompute it."""
    params.validate()
    macro = np.asarray(macro)
    if macro.ndim != 2 or not np.isfinite(macro).all():
        raise ValueError("finite macro required")
    land = macro >= params.sea_m
    if land.all() or not land.any():
        return np.zeros(macro.shape, np.float32)
    if not anchors:
        raise ValueError("macro marine anchors required")
    components, _ = label(~land)
    ids = []
    for z, x in anchors:
        if z < 0 or x < 0 or z >= macro.shape[0] or x >= macro.shape[1] or land[z, x]:
            raise ValueError("macro anchor must be wet")
        ids.append(components[z, x])
    ocean = np.isin(components, ids)
    distance = np.where(ocean, distance_transform_edt(ocean), distance_transform_edt(~ocean)) * params.spacing_m
    t = np.clip(1 - distance / params.coast_band_m, 0, 1)
    return (t * t * (3 - 2 * t)).astype(np.float32)


def compose(raw, macro, params=CoastalParameters(), *, support=None):
    """Return bed on fixed support, excluding the filter halo on all sides."""
    radius = params.validate()
    raw = np.asarray(raw)
    macro = np.asarray(macro)
    if raw.ndim != 2 or raw.shape != macro.shape or min(raw.shape) <= 2 * radius or not np.isfinite(raw).all() or not np.isfinite(macro).all():
        raise ValueError("finite matching 2D inputs and full halo required")
    if support is None:
        raise ValueError("fixed-domain coastal support required")
    support = np.asarray(support)
    if support.shape != macro.shape or not np.isfinite(support).all() or np.any((support < 0) | (support > 1)):
        raise ValueError("invalid fixed coastal support")
    residual = raw.astype(np.float32) - macro.astype(np.float32)
    low = gaussian_filter(residual, sigma=params.sigma_m / params.spacing_m, radius=radius, mode="nearest")
    core = np.s_[radius:-radius, radius:-radius]
    m = macro[core].astype(np.float32)
    correction = residual[core] - (1 - params.low_fraction) * low[core]
    t = np.clip(1 - np.abs(m - params.sea_m) / params.transition_elevation_m, 0, 1)
    smooth = t * t * (3 - 2 * t)
    limit = params.far_fraction * np.abs(m - params.sea_m) + params.nearshore_allowance_m * smooth * support[core]
    return (m + np.clip(correction, -limit, limit)).astype(np.float32)


def classify(bed, valid, anchors, sea_m=0.0):
    """Codes: 0 unknown, 1 land, 2 ocean, 3 enclosed below datum.

    Four-neighbour components touching the domain boundary or invalid cells are
    unknown unless connected to an explicitly supplied wet marine anchor.
    Shoreline marks land cells adjacent to ocean, recomputed from this bed.
    """
    bed = np.asarray(bed)
    valid = np.asarray(valid)
    if bed.ndim != 2 or valid.shape != bed.shape or valid.dtype != np.bool_ or not np.isfinite(bed[valid]).all() or not np.isfinite(sea_m):
        raise ValueError("invalid bed or domain")
    wet = valid & (bed < sea_m)
    if not anchors:
        raise ValueError("explicit marine anchor required")
    components, count = label(wet)
    ocean_ids = set()
    for point in anchors:
        if len(point) != 2 or any(not isinstance(v, (int, np.integer)) for v in point):
            raise ValueError("invalid anchor")
        z, x = point
        if z < 0 or x < 0 or z >= bed.shape[0] or x >= bed.shape[1] or not wet[z, x]:
            raise ValueError("anchor must be valid and wet")
        ocean_ids.add(int(components[z, x]))
    edge = np.zeros(bed.shape, bool)
    edge[[0, -1], :] = True
    edge[:, [0, -1]] = True
    edge |= binary_dilation(~valid)
    unknown_ids = np.unique(components[wet & edge])
    codes = np.zeros(bed.shape, np.uint8)
    codes[valid & ~wet] = 1
    codes[wet] = 3
    codes[wet & np.isin(components, unknown_ids)] = 0
    codes[wet & np.isin(components, list(ocean_ids))] = 2
    shore = (codes == 1) & binary_dilation(codes == 2)
    return codes, shore



# ------------------------------------------------------------------------
# 原 terrain_pipeline/coastal_detail_refinement.py
# ------------------------------------------------------------------------

@dataclass(frozen=True)
class DetailParameters:
    spacing_m: float = 30.0
    sigma_short_m: float = 60.0
    sigma_long_m: float = 180.0
    radius_m: float = 720.0
    coast_band_m: float = 240.0
    elevation_band_m: float = 40.0
    sign_band_m: float = 90.0
    cap_m: float = 6.0
    strength: float = 1.0

    def validate(self):
        values = np.array(list(self.__dict__.values()), dtype=float)
        if not np.isfinite(values).all() or min(values[:-1]) <= 0 or not 0 <= self.strength <= 1:
            raise ValueError("invalid detail parameters")
        if not self.sigma_short_m < self.sigma_long_m <= self.radius_m <= 720 or self.coast_band_m > 240 or self.elevation_band_m > 40 or self.sign_band_m > min(90, self.coast_band_m) or self.cap_m > 6:
            raise ValueError("detail parameters exceed bounded support")
        cells = self.radius_m / self.spacing_m
        if cells < 1 or abs(cells - round(cells)) > 1e-9:
            raise ValueError("filter radius must be whole cells")
        return int(round(cells))


def _smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def detail_support(bed, valid, classification, shoreline, params=DetailParameters()):
    """Prepare once on the full classified baseline, then slice for windows.

    Unknown and enclosed wet cells never change. Full filter support must lie
    within the valid domain; its edge clearance also has a smooth one-cell ramp.
    """
    params.validate()
    bed = np.asarray(bed)
    if bed.ndim != 2 or any(np.asarray(a).shape != bed.shape for a in (valid, classification, shoreline)) or valid.dtype != np.bool_ or shoreline.dtype != np.bool_ or classification.dtype != np.uint8 or not np.isfinite(bed).all() or not np.isin(classification, [0, 1, 2, 3]).all():
        raise ValueError("invalid baseline support fields")
    if np.any(shoreline & ((classification != 1) | ~valid)):
        raise ValueError("invalid marine shoreline")
    distance = np.full(bed.shape, params.coast_band_m, np.float32)
    if shoreline.any():
        distance[:] = np.minimum(distance_transform_edt(~shoreline) * params.spacing_m, params.coast_band_m)
    # Pad explicitly: scipy's all-true EDT otherwise has an implicit asymmetric edge.
    clearance = distance_transform_edt(np.pad(valid, 1, constant_values=False))[1:-1, 1:-1] * params.spacing_m
    weight = _smooth(1 - distance / params.coast_band_m)
    weight *= _smooth(1 - np.abs(bed) / params.elevation_band_m)
    weight *= _smooth((clearance - params.radius_m) / params.spacing_m)
    weight *= valid & ((classification == 1) | (classification == 2))
    # Keep a dry guard around nonmarine wet components so restoration cannot
    # connect a previously unknown/enclosed water body to the marine anchor.
    protected_wet = valid & (bed < 0) & (classification != 2)
    weight[binary_dilation(protected_wet)] = 0
    return {"distance_m": distance, "weight": weight.astype(np.float32)}


def refine(raw, bed, *, support, params=DetailParameters()):
    """Return bed and actual float32 delta, without mutating any input.

    Difference of bandpasses equals the bandpass of raw minus baseline. The
    finite Gaussian radius is explicit, with no noise or stochastic state.
    """
    radius = params.validate()
    raw, bed = np.asarray(raw), np.asarray(bed)
    if bed.dtype != np.float32 or raw.ndim != 2 or raw.shape != bed.shape or min(bed.shape) <= 2 * radius or not np.isfinite(raw).all() or not np.isfinite(bed).all():
        raise ValueError("finite aligned raw/float32 baseline with halo required")
    if set(support) != {"distance_m", "weight"}:
        raise ValueError("shared full-domain support required")
    distance, weight = support["distance_m"], support["weight"]
    if any(a.shape != bed.shape or a.dtype != np.float32 or not np.isfinite(a).all() for a in (distance, weight)) or np.any((weight < 0) | (weight > 1)) or np.any((distance < 0) | (distance > params.coast_band_m)) or np.any((weight > 0) & ((distance >= params.coast_band_m) | (np.abs(bed) >= params.elevation_band_m))):
        raise ValueError("invalid shared support")
    if params.strength == 0:
        return bed.copy(), np.zeros_like(bed)
    residual = raw.astype(np.float32) - bed
    if not np.isfinite(residual).all():
        raise ValueError("unrepresentable raw/baseline residual")
    short = gaussian_filter(residual, params.sigma_short_m / params.spacing_m, radius=radius, mode="nearest")
    long = gaussian_filter(residual, params.sigma_long_m / params.spacing_m, radius=radius, mode="nearest")
    delta = (short - long) * (params.strength * weight)
    # Smoothly reduce the allowed crossing as the sign-change boundary approaches.
    crossing = _smooth(1 - distance / params.sign_band_m) * params.cap_m
    delta = np.clip(delta, -params.cap_m, params.cap_m)
    delta = np.where(bed >= 0, np.maximum(delta, -bed - crossing), np.minimum(delta, -bed + crossing))
    result = (bed + delta).astype(np.float32)
    locked_wet = (distance >= params.sign_band_m) & (bed < 0)
    result[locked_wet] = np.minimum(result[locked_wet], np.nextafter(np.float32(0), np.float32(-1)))
    result[weight == 0] = bed[weight == 0]
    return result, (result - bed).astype(np.float32)



# ------------------------------------------------------------------------
# 原 terrain_pipeline/coastal_archipelago.py
# ------------------------------------------------------------------------

WORLD_SEED = 20261020


SUBSEED = int.from_bytes(hashlib.sha256(b'20261020:regional-coastal-relief-v3').digest()[:8], 'big')


def relief(bed, valid, support, origin_xz_m, spacing_m=30., strength=1.):
    bed, valid, support = np.asarray(bed), np.asarray(valid), np.asarray(support)
    if (bed.ndim != 2 or valid.shape != bed.shape or valid.dtype != np.bool_ or support.shape != bed.shape or
        not np.isfinite(bed).all() or not np.isfinite(support).all() or np.any((support < 0) | (support > 1)) or
        not np.isfinite(spacing_m) or spacing_m <= 0 or not np.isfinite(strength) or not 0 <= strength <= 1 or
        len(origin_xz_m) != 2 or not np.isfinite(origin_xz_m).all()):
        raise ValueError('invalid coastal relief inputs')
    out = np.zeros(bed.shape, np.float32)
    if strength == 0 or not support.any():
        return out
    x = origin_xz_m[0] + np.arange(bed.shape[1], dtype=np.float64)[None, :] * spacing_m
    for start in range(0, bed.shape[0], 128):
        end = min(start + 128, bed.shape[0])
        z = origin_xz_m[1] + np.arange(start, end, dtype=np.float64)[:, None] * spacing_m
        xx, zz = np.broadcast_arrays(x, z)
        envelope_noise = smooth_noise(xx, zz, 18000., SUBSEED, 10)
        envelope = np.clip((envelope_noise + 0.55) / 0.9, 0, 1) ** 2
        warp_x = 900. * smooth_noise(xx, zz, 4000., SUBSEED, 20)
        warp_z = 900. * smooth_noise(xx, zz, 4000., SUBSEED, 30)
        u = 0.8 * (xx + warp_x) + 0.6 * (zz + warp_z)
        w = -0.6 * (xx + warp_x) + 0.8 * (zz + warp_z)
        ridge = smooth_noise(u / 1.8, w, 850., SUBSEED, 50)
        detail = smooth_noise(xx, zz, 260., SUBSEED, 60)
        micro = smooth_noise(xx, zz, 150., SUBSEED, 70)
        shape = 0.78 * ridge + 0.17 * detail + 0.05 * micro
        depth = np.clip((450. - np.abs(bed[start:end])) / 250., 0, 1)
        out[start:end] = (strength * 300. * support[start:end] * depth * envelope * shape * valid[start:end]).astype(np.float32)
    return out



# ------------------------------------------------------------------------
# 原 terrain_pipeline/coastal_terrain_product.py
# ------------------------------------------------------------------------

RAW_HASH = "1dfa01dbb798fa698a7a68a1fc820e33e90606a67c79c2a6498967440ea35aaa"


RAW_ARRAY = "f414d614e665400125815ff0c6f06135f6c8700da5d615ecb463379b5bdcdd30"


MACRO_HASH = "81d70f255b7b91ed7c2b04795c9bf91d9eb49a447361e6d5349c75716558573f"


MACRO_ARRAY = "6c12aa113d67bad5ca94f0fc1fa8ce384a509692f47d8e4b33eb1acdd7f930af"


TD_ID = "b11092789e5077fbe7c61926b2b1c0788ef22065edf2597035a13abe506ee607"


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def array_hash_contiguous(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def plate_macro(path, identity, shape, origin_xz_m, spacing_m):
    product = load_product(path, expected_identity=identity)
    out = np.empty(shape, np.float32)
    x = origin_xz_m[0] + np.arange(shape[1])[None, :] * spacing_m
    for start in range(0, shape[0], 64):
        stop = min(start + 64, shape[0])
        z = origin_xz_m[1] + np.arange(start, stop)[:, None] * spacing_m
        out[start:stop] = product.sample(x, z, outside="reject")["elevation_m"]
    return out


def prepare_terrain_bed(raw_path, macro_path, metadata_path, output, *, plate_path=None, plate_identity=None, memory_budget_bytes=850_000_000):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    # Estimate before reading or allocating any terrain arrays.
    needed = 850_000_000
    disk_parent = output.parent
    while not disk_parent.exists():
        disk_parent = disk_parent.parent
    if memory_budget_bytes < needed or psutil.virtual_memory().available < needed or shutil.disk_usage(disk_parent).free < 500_000_000:
        raise ValueError("insufficient memory or disk budget")
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    if (metadata.get("terrain_identity") != TD_ID or metadata.get("source_shape_zx") != [3834, 3834] or metadata.get("source_origin_native_xz") != [3351, -1917] or metadata.get("native_spacing_m") != 30):
        raise ValueError("wrong TD metadata or coordinate identity")
    if file_hash(raw_path) != RAW_HASH or file_hash(macro_path) != MACRO_HASH:
        raise ValueError("source file hash mismatch")
    raw = np.load(raw_path, mmap_mode="r", allow_pickle=False)
    original_macro = np.load(macro_path, mmap_mode="r", allow_pickle=False)
    if raw.shape != (3834, 3834) or original_macro.shape != raw.shape or array_hash_contiguous(raw) != RAW_ARRAY or array_hash_contiguous(original_macro) != MACRO_ARRAY:
        raise ValueError("source array hash or shape mismatch")
    # Fixed source extent includes the review window, filter support, coastal
    # distance support and independently identified offshore anchor.
    z0, z1, x0, x1 = 640, 3210, 640, 3450
    raw = raw[z0:z1, x0:x1]
    if plate_path is None:
        macro = original_macro[z0:z1, x0:x1]
        macro_identity = MACRO_ARRAY
    else:
        if not plate_identity:
            raise ValueError("plate identity required")
        macro = plate_macro(plate_path, plate_identity, raw.shape, (100530+x0*30, -57510+z0*30), 30)
        plate = load_product(plate_path, expected_identity=plate_identity)
        if not bool(plate.sample(190050, 0, outside="reject")["ocean_connected"]):
            raise ValueError("plate anchor is not connected ocean")
        macro_identity = plate_identity
    params = CoastalParameters()
    support = coastal_support(macro, params, anchors=[(1917-z0, 2984-x0)])
    bed = compose(raw, macro, params, support=support)
    radius = params.validate()
    # Anchor is an independently identified offshore point in the source macro.
    anchors = [(1917-z0-radius, 2984-x0-radius)]
    valid = np.ones(bed.shape, bool)
    margin = int(params.coast_band_m / params.spacing_m) - radius
    valid[:margin,:] = False
    valid[-margin:,:] = False
    valid[:,:margin] = False
    valid[:,-margin:] = False
    codes, shore = classify(bed, valid, anchors)
    output.parent.mkdir(parents=True, exist_ok=True)
    peak_rss = getattr(psutil.Process().memory_info(), "peak_wset", psutil.Process().memory_info().rss)
    del support, macro, raw, original_macro
    tmp = Path(tempfile.mkdtemp(prefix=".coast-", dir=output.parent))
    try:
        arrays = {"bed": bed, "valid": valid, "classification": codes, "shoreline": shore}
        hashes = {}
        for name, array in arrays.items():
            path = tmp / (name + ".npy")
            np.save(path, array, allow_pickle=False)
            hashes[path.name] = file_hash(path)
        source_files = [Path(__file__)]
        manifest = {"schema": "coastal-terrain-v1", "algorithm_version": "coastal-bed-v1", "preflight_estimated_bytes": needed, "parameters": asdict(params), "origin_xz_m": [100530 + (x0+radius)*30, -57510 + (z0+radius)*30], "spacing_m": 30, "shape_zx": list(bed.shape), "source_shape_zx": [3834,3834], "source_origin_xz_m": [100530,-57510], "valid_margin_cells": radius, "coast_support_margin_cells": 200, "support_boundary_note": "outer 104 cells of saved bed may lack full horizontal coastal support; review window has complete support", "fixed_source_slice_zx": [z0,z1,x0,x1], "coast_support": "fixed macro shoreline distance, capped at coast_band_m; computed before crop", "coordinate_convention": "cell centres; x east, z south; arrays z,x", "terrain_identity": TD_ID, "world_seed": 20261020, "raw_path": str(Path(raw_path).resolve()), "raw_file_sha256": RAW_HASH, "raw_array_sha256": RAW_ARRAY, "original_macro_path": str(Path(macro_path).resolve()), "original_macro_file_sha256": MACRO_HASH, "original_macro_array_sha256": MACRO_ARRAY, "metadata_path": str(Path(metadata_path).resolve()), "metadata_sha256": file_hash(metadata_path), "macro_identity": macro_identity, "plate_path": str(Path(plate_path).resolve()) if plate_path else None, "plate_file_sha256": file_hash(plate_path) if plate_path else None, "td_conditioning": "original macro; plate combination is derived adaptation, not new inference", "anchor_source_zx": [1917,2984], "anchor_world_xz_m": [190050,0], "anchor_provenance": ("plate frozen ocean_connected and final wet bed" if plate_path else "interior offshore point east of original macro coast; final bed wet"), "algorithm_sha256": {p.name:file_hash(p) for p in source_files}, "files": hashes}
        (tmp / "performance.json").write_text(json.dumps({"measured_peak_rss_bytes_before_staging": peak_rss, "preflight_estimated_bytes": needed}, indent=2), encoding="utf-8")
        manifest["identity"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        read_terrain_product(tmp, expected_identity=manifest["identity"])
        os.rename(tmp, output)
    finally:
        if tmp.exists() and tmp.resolve().parent == output.parent.resolve() and tmp.name.startswith(".coast-"):
            shutil.rmtree(tmp)
    return read_terrain_product(output)


def read_terrain_product(path, *, expected_identity=None):
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    identity = manifest.pop("identity", None)
    actual = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if identity != actual or (expected_identity is not None and identity != expected_identity):
        raise ValueError("product identity mismatch")
    manifest["identity"] = identity
    if manifest.get("schema") != "coastal-terrain-v1" or set(manifest.get("files", {})) != {"bed.npy", "valid.npy", "classification.npy", "shoreline.npy"}:
        raise ValueError("invalid product manifest")
    result = {}
    for name, expected in manifest["files"].items():
        if file_hash(path / name) != expected:
            raise ValueError("product hash mismatch")
        result[name[:-4]] = np.load(path / name, allow_pickle=False)
        if list(result[name[:-4]].shape) != manifest["shape_zx"]:
            raise ValueError("product shape mismatch")
    bed, valid, codes, shore = result["bed"], result["valid"], result["classification"], result["shoreline"]
    if bed.dtype != np.float32 or not np.isfinite(bed).all() or codes.dtype != np.uint8 or not np.isin(codes, [0,1,2,3]).all() or shore.dtype != np.bool_ or valid.dtype != np.bool_:
        raise ValueError("invalid product fields")
    z0, _, x0, _ = manifest["fixed_source_slice_zx"]
    radius = manifest["valid_margin_cells"]
    anchor = (1917-z0-radius, 2984-x0-radius)
    params = CoastalParameters(**manifest["parameters"])
    if (manifest.get("algorithm_version") != "coastal-bed-v1" or manifest.get("anchor_source_zx") != [1917,2984] or manifest.get("anchor_world_xz_m") != [190050,0] or params.validate() != radius or manifest["spacing_m"] != 30 or params.spacing_m != 30 or any(not isinstance(v, int) for v in manifest["fixed_source_slice_zx"]) or not (0 <= z0 < manifest["fixed_source_slice_zx"][1] <= 3834 and 0 <= x0 < manifest["fixed_source_slice_zx"][3] <= 3834) or manifest["source_shape_zx"] != [3834,3834] or manifest["source_origin_xz_m"] != [100530,-57510] or manifest["origin_xz_m"] != [100530+(x0+radius)*30,-57510+(z0+radius)*30] or manifest["shape_zx"] != [manifest["fixed_source_slice_zx"][1]-z0-2*radius, manifest["fixed_source_slice_zx"][3]-x0-2*radius]):
        raise ValueError("inconsistent product coordinates")
    border = int(params.coast_band_m / params.spacing_m) - radius
    expected_valid = np.ones(bed.shape, bool)
    if border > 0:
        expected_valid[:border,:] = expected_valid[-border:,:] = False
        expected_valid[:,:border] = expected_valid[:,-border:] = False
    if not np.array_equal(valid, expected_valid):
        raise ValueError("invalid domain mask")
    check_codes, check_shore = classify(bed, valid, [anchor], params.sea_m)
    if not np.array_equal(codes, check_codes) or not np.array_equal(shore, check_shore):
        raise ValueError("inconsistent classification")
    for array in result.values():
        array.flags.writeable = False
    return manifest, result



# ------------------------------------------------------------------------
# 原 terrain_pipeline/coastal_archipelago_product.py
# ------------------------------------------------------------------------

PARAMETERS = {'amplitude_m':300.0, 'envelope_spacing_m':18000.0, 'envelope_offset':0.55, 'envelope_range':0.9, 'envelope_power':2, 'warp_spacing_m':4000.0, 'warp_m':900.0, 'rotation_cos_sin':[0.8,0.6], 'ridge_spacing_m':850.0, 'ridge_anisotropy':1.8, 'detail_spacing_m':260.0, 'micro_spacing_m':150.0, 'weights':[0.78,0.17,0.05], 'depth_limit_m':450.0, 'depth_taper_m':250.0, 'salts':[10,20,30,50,60,70]}


def identity_archipelago(m):
    return hashlib.sha256(json.dumps(m, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def archipelago_anchor(m):
    z0, _, x0, _ = m['fixed_source_slice_zx']
    radius = m['valid_margin_cells']
    return (m['anchor_source_zx'][0]-z0-radius, m['anchor_source_zx'][1]-x0-radius)


def read_archipelago_product(path, expected_identity=None):
    path = Path(path)
    m = json.loads((path/'manifest.json').read_text(encoding='utf-8'))
    ident = m.pop('identity')
    if identity_archipelago(m) != ident or (expected_identity and ident != expected_identity):
        raise ValueError('identity mismatch')
    m['identity'] = ident
    if (m.get('schema') != 'coastal-archipelago-v3' or m.get('algorithm_version') != 'regional-relief-v3' or
        m.get('parameters') != PARAMETERS or m.get('subseed_derivation') != 'first 8 bytes big endian SHA256 of 20261020:regional-coastal-relief-v3' or m.get('noise_helper_sha256') != file_hash(Path(__file__).resolve().parents[1]/'diffusion/geographic_noise.py') or m.get('world_seed') != 20261020 or m.get('subseed') != SUBSEED or not isinstance(m.get('strength'), (int,float)) or
        not np.isfinite(m['strength']) or not 0 <= m['strength'] <= 1 or
        set(m['files']) != {'bed.npy','valid.npy','classification.npy','shoreline.npy','relief.npy','support.npy'}):
        raise ValueError('invalid schema or parameters')
    arrays = {}
    for name, digest in m['files'].items():
        if file_hash(path/name) != digest:
            raise ValueError('file hash mismatch')
        arrays[name[:-4]] = np.load(path/name, allow_pickle=False)
    b, v, c, s, r, support = (arrays[k] for k in ('bed','valid','classification','shoreline','relief','support'))
    if (any(list(a.shape) != m['shape_zx'] for a in arrays.values()) or b.dtype != np.float32 or r.dtype != np.float32 or support.dtype != np.float32 or v.dtype != np.bool_ or c.dtype != np.uint8 or s.dtype != np.bool_ or not np.isfinite(b).all() or not np.isfinite(r).all() or not np.isfinite(support).all() or np.any((support<0)|(support>1)) or np.any(r[~v] != 0) or np.any(np.abs(r) > 300*m['strength']+0.001)):
        raise ValueError('invalid fields')
    base, source = read_terrain_product(m['baseline_path'], expected_identity=m['baseline_identity'])
    if (any(m[k] != base[k] for k in ('origin_xz_m','spacing_m','terrain_identity','raw_file_sha256','macro_identity','anchor_world_xz_m')) or not np.array_equal(v, source['valid']) or not np.array_equal(b, source['bed'] + r)):
        raise ValueError('source mismatch')
    expected_relief = relief(source['bed'], v, support, m['origin_xz_m'], m['spacing_m'], m['strength'])
    if not np.array_equal(r, expected_relief):
        raise ValueError('relief parameter mismatch')
    cc, ss = classify(b, v, [archipelago_anchor(base)])
    if not np.array_equal(c, cc) or not np.array_equal(s, ss):
        raise ValueError('classification mismatch')
    for a in arrays.values(): a.flags.writeable = False
    return m, arrays


def prepare_archipelago(baseline, output, strength, expected_baseline_identity, memory_budget_bytes=1200000000):
    output = Path(output)
    if output.exists(): raise FileExistsError(output)
    if not expected_baseline_identity or not np.isfinite(strength) or not 0 <= strength <= 1: raise ValueError('invalid source or strength')
    parent = output.parent
    while not parent.exists(): parent = parent.parent
    if memory_budget_bytes < 1200000000 or psutil.virtual_memory().available < 1200000000 or shutil.disk_usage(parent).free < 400000000: raise ValueError('insufficient resources')
    m, a = read_terrain_product(baseline, expected_identity=expected_baseline_identity)
    z0,z1,x0,x1 = m['fixed_source_slice_zx']
    if m['plate_path']:
        if file_hash(m['plate_path']) != m['plate_file_sha256']: raise ValueError('plate source mismatch')
        macro = plate_macro(m['plate_path'], m['macro_identity'], (z1-z0,x1-x0), (100530+x0*30,-57510+z0*30), 30)
    else:
        if file_hash(m['original_macro_path']) != m['original_macro_file_sha256']: raise ValueError('macro source mismatch')
        macro = np.load(m['original_macro_path'], mmap_mode='r', allow_pickle=False)[z0:z1,x0:x1]
    if file_hash(m['raw_path']) != m['raw_file_sha256']: raise ValueError('TD source mismatch')
    support = coastal_support(macro, CoastalParameters(**m['parameters']), anchors=[(m['anchor_source_zx'][0]-z0,m['anchor_source_zx'][1]-x0)])
    radius=m['valid_margin_cells']; support=support[radius:-radius,radius:-radius].copy()
    r = relief(a['bed'], a['valid'], support, m['origin_xz_m'], m['spacing_m'], strength)
    bed = a['bed'] + r
    codes, shore = classify(bed, a['valid'], [archipelago_anchor(m)])
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.archipelago-', dir=output.parent))
    try:
        arrays = {'bed':bed, 'valid':a['valid'], 'classification':codes, 'shoreline':shore, 'relief':r, 'support':support}
        files = {}
        for name, array in arrays.items():
            np.save(tmp/(name+'.npy'), array, allow_pickle=False)
            files[name+'.npy'] = file_hash(tmp/(name+'.npy'))
        manifest = {'schema':'coastal-archipelago-v3', 'algorithm_version':'regional-relief-v3', 'baseline_path':str(Path(baseline).resolve()), 'baseline_identity':m['identity'], 'terrain_identity':m['terrain_identity'], 'raw_file_sha256':m['raw_file_sha256'], 'macro_identity':m['macro_identity'], 'origin_xz_m':m['origin_xz_m'], 'spacing_m':m['spacing_m'], 'shape_zx':m['shape_zx'], 'world_seed':20261020, 'subseed':SUBSEED, 'subseed_derivation':'first 8 bytes big endian SHA256 of 20261020:regional-coastal-relief-v3', 'strength':strength, 'anchor_world_xz_m':m['anchor_world_xz_m'], 'parameters': PARAMETERS, 'noise_helper_sha256': file_hash(Path(__file__).resolve().parents[1]/'diffusion/geographic_noise.py'), 'engineering_note':'continuous engineering relief; not geological reconstruction', 'algorithm_sha256':{p.name:file_hash(p) for p in [Path(__file__)]}, 'files':files}
        manifest['identity'] = identity_archipelago(manifest)
        (tmp/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        read_archipelago_product(tmp, manifest['identity'])
        os.rename(tmp, output)
    finally:
        if tmp.exists() and tmp.parent.resolve() == output.parent.resolve() and tmp.name.startswith('.archipelago-'): shutil.rmtree(tmp)
    return read_archipelago_product(output)



# ------------------------------------------------------------------------
# 原 terrain_pipeline/coastal_detail_product.py
# ------------------------------------------------------------------------

APPROVED_BASELINE = "42a50c3b13f8f4169002438e879d54e53fb094cff9bde9dd7659bfebe4336c60"


BASE_FIELDS = {"bed.npy", "valid.npy", "classification.npy", "shoreline.npy"}


OUTPUT_FIELDS = BASE_FIELDS | {"delta.npy", "distance_m.npy", "weight.npy"}


SOURCE_KEYS = {"kind", "baseline_path", "baseline_identity", "files", "raw_path", "raw_file_sha256", "raw_array_sha256", "metadata_path", "metadata_sha256", "terrain_identity", "world_seed", "shape_zx", "origin_xz_m", "spacing_m", "source_shape_zx", "source_origin_xz_m", "source_slice_zx", "anchors_zx"}


def identity_detail(record):
    """Canonical identity excludes only paths and the identity field itself."""
    def numerical(value):
        if isinstance(value, dict):
            return {k: numerical(v) for k, v in value.items() if k != "identity" and not k.endswith("_path")}
        if isinstance(value, list):
            return [numerical(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(numerical(record), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def array_hash_rowchunk(array):
    digest = hashlib.sha256()
    for start in range(0, array.shape[0], 64):
        digest.update(np.ascontiguousarray(array[start:start + 64]).tobytes())
    return digest.hexdigest()


def _algorithms():
    return {Path(__file__).name: file_hash(Path(__file__))}


def _preflight(source, budget, output=None):
    # Includes mapped new raw source pages, EDT temporaries, independent cold
    # recomputation and saved arrays. No model or macro array is loaded here.
    shape = source.get("shape_zx", [])
    raw_shape = source.get("source_shape_zx", [])
    if len(shape) != 2 or len(raw_shape) != 2 or any(type(v) is not int or v <= 0 for v in shape + raw_shape):
        raise ValueError("invalid source shape")
    needed = math.prod(shape) * 128 + math.prod(raw_shape) * 4 + 32_000_000
    if needed > budget or budget > 1_000_000_000 or psutil.virtual_memory().available < needed:
        raise ValueError("insufficient memory budget (maximum 1GB)")
    if output is not None:
        parent = Path(output).parent
        while not parent.exists():
            parent = parent.parent
        if shutil.disk_usage(parent).free < math.prod(shape) * 32 + 1_000_000:
            raise ValueError("insufficient disk budget")
    return needed


def _approved_record(path):
    path = Path(path).resolve()
    m = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if m.get("identity") != APPROVED_BASELINE:
        raise ValueError("approved baseline identity required")
    z0, z1, x0, x1 = m["fixed_source_slice_zx"]
    radius = m["valid_margin_cells"]
    return {"kind": "approved-coastal-v1", "baseline_path": str(path), "baseline_identity": m["identity"], "files": m["files"],
            **{k: m[k] for k in ("raw_path", "raw_file_sha256", "raw_array_sha256", "metadata_path", "metadata_sha256", "terrain_identity", "world_seed", "shape_zx", "origin_xz_m", "spacing_m", "source_shape_zx", "source_origin_xz_m")},
            "source_slice_zx": [z0 + radius, z1 - radius, x0 + radius, x1 - radius],
            "anchors_zx": [[m["anchor_source_zx"][0] - z0 - radius, m["anchor_source_zx"][1] - x0 - radius]]}


def _frozen_baseline_identity(source):
    return identity_detail({k: source[k] for k in ("files", "shape_zx", "origin_xz_m", "spacing_m", "anchors_zx")})


def _load_source(source):
    if set(source) != SOURCE_KEYS or set(source["files"]) != BASE_FIELDS or source["world_seed"] != 20261020 or source["spacing_m"] != 30:
        raise ValueError("invalid frozen source record")
    for name in ("origin_xz_m", "source_origin_xz_m"):
        if not isinstance(source[name], list) or len(source[name]) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in source[name]):
            raise ValueError("invalid source origin")
    if source["kind"] == "approved-coastal-v1":
        if _approved_record(source["baseline_path"]) != source:
            raise ValueError("baseline source binding mismatch")
        _, baseline = read_terrain_product(source["baseline_path"], expected_identity=APPROVED_BASELINE)
    elif source["kind"] == "frozen-detail-source-v1":
        if source["baseline_identity"] != _frozen_baseline_identity(source):
            raise ValueError("frozen baseline identity mismatch")
        baseline = {}
        for name, digest in source["files"].items():
            path = Path(source["baseline_path"]) / name
            if file_hash(path) != digest:
                raise ValueError("baseline source hash mismatch")
            baseline[name[:-4]] = np.load(path, mmap_mode="r", allow_pickle=False)
    else:
        raise ValueError("unknown source kind")
    for name, dtype in (("bed", np.float32), ("valid", np.bool_), ("classification", np.uint8), ("shoreline", np.bool_)):
        if list(baseline[name].shape) != source["shape_zx"] or baseline[name].dtype != dtype:
            raise ValueError("baseline source arrays mismatch")
    if not np.isfinite(baseline["bed"]).all():
        raise ValueError("nonfinite baseline")
    codes, shore = classify(baseline["bed"], baseline["valid"], source["anchors_zx"])
    if not np.array_equal(codes, baseline["classification"]) or not np.array_equal(shore, baseline["shoreline"]):
        raise ValueError("baseline classification mismatch")
    if file_hash(source["metadata_path"]) != source["metadata_sha256"] or file_hash(source["raw_path"]) != source["raw_file_sha256"]:
        raise ValueError("external source hash mismatch")
    metadata = json.loads(Path(source["metadata_path"]).read_text(encoding="utf-8"))
    if (metadata.get("terrain_identity") != source["terrain_identity"] or metadata.get("world_seed") != 20261020 or metadata.get("source_shape_zx") != source["source_shape_zx"] or metadata.get("native_spacing_m") != source["spacing_m"] or metadata.get("native_source_origin_xz_m") != source["source_origin_xz_m"] or metadata.get("source_origin_native_xz") != [v / source["spacing_m"] for v in source["source_origin_xz_m"]]):
        raise ValueError("metadata source coordinates mismatch")
    binding = metadata.get("native_source_paths", {}).get("raw_td_30m", {})
    # The metadata's original path is provenance. Actual mapped bytes are bound
    # by both hashes, permitting relocation without changing numerical identity.
    if binding.get("sha256") != source["raw_file_sha256"] or binding.get("array_sha256") != source["raw_array_sha256"]:
        raise ValueError("metadata raw binding mismatch")
    raw = np.load(source["raw_path"], mmap_mode="r", allow_pickle=False)
    if list(raw.shape) != source["source_shape_zx"] or raw.dtype != np.float32 or array_hash_rowchunk(raw) != source["raw_array_sha256"]:
        raise ValueError("raw source array mismatch")
    mapping = source["source_slice_zx"]
    if len(mapping) != 4 or any(type(v) is not int for v in mapping):
        raise ValueError("invalid source slice")
    z0, z1, x0, x1 = mapping
    if not (0 <= z0 < z1 <= raw.shape[0] and 0 <= x0 < x1 <= raw.shape[1]) or [z1 - z0, x1 - x0] != source["shape_zx"] or source["origin_xz_m"] != [source["source_origin_xz_m"][0] + x0 * source["spacing_m"], source["source_origin_xz_m"][1] + z0 * source["spacing_m"]]:
        raise ValueError("source slice/world mapping mismatch")
    return baseline, raw[z0:z1, x0:x1]


def _derive(source, params):
    baseline, raw = _load_source(source)
    support = detail_support(baseline["bed"], baseline["valid"], baseline["classification"], baseline["shoreline"], params)
    bed, delta = refine(raw, baseline["bed"], support=support, params=params)
    codes, shore = classify(bed, baseline["valid"], source["anchors_zx"])
    return {"bed": bed, "delta": delta, "valid": baseline["valid"], "classification": codes, "shoreline": shore, **support}


def prepare_source(source, output, *, params=DetailParameters(), memory_budget_bytes=1_000_000_000):
    """Prepare an explicitly frozen source record (portable fixtures included)."""
    params.validate()
    if params.spacing_m != source["spacing_m"]:
        raise ValueError("parameter/source spacing mismatch")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    needed = _preflight(source, memory_budget_bytes, output)
    arrays = _derive(source, params)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".coastal-detail-", dir=output.parent))
    try:
        files = {}
        for name, array in arrays.items():
            path = stage / (name + ".npy")
            np.save(path, array, allow_pickle=False)
            files[path.name] = file_hash(path)
        manifest = {"schema": "coastal-detail-product-v1", "algorithm_version": "static-td-bandpass-restoration-v1", "source": source, "parameters": asdict(params), "origin_xz_m": source["origin_xz_m"], "spacing_m": source["spacing_m"], "shape_zx": source["shape_zx"], "world_seed": 20261020, "randomness": "none", "finite_support": {"filter_radius_cells": params.validate(), "filter_radius_m": params.radius_m, "distance_support": "shared full-baseline connected-ocean land-cell shoreline; capped raster EDT", "window_contract": "slice shared support; discard radius cells on each edge"}, "algorithm_sha256": _algorithms(), "files": files}
        manifest["identity"] = identity_detail(manifest)
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (stage / "performance.json").write_text(json.dumps({"estimated_working_bytes": needed, "new_raw_source_count": 1, "raw_access": "stream hash and read-only mmap", "peak_process_bytes_before_cold_read": getattr(psutil.Process().memory_info(), "peak_wset", psutil.Process().memory_info().rss)}, indent=2), encoding="utf-8")
        del arrays
        read_detail_product(stage, expected_identity=manifest["identity"], memory_budget_bytes=memory_budget_bytes)
        if output.exists():
            raise FileExistsError(output)
        os.rename(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest


def prepare_detail(baseline, output, *, params=DetailParameters(), memory_budget_bytes=1_000_000_000):
    return prepare_source(_approved_record(baseline), output, params=params, memory_budget_bytes=memory_budget_bytes)


def read_detail_product(path, *, expected_identity=None, memory_budget_bytes=1_000_000_000):
    """Hash sources and arrays, then independently reproduce every derived field."""
    path = Path(path)
    m = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if m.get("identity") != identity_detail(m) or (expected_identity is not None and m["identity"] != expected_identity):
        raise ValueError("product identity mismatch")
    if m.get("schema") != "coastal-detail-product-v1" or m.get("algorithm_version") != "static-td-bandpass-restoration-v1" or set(m.get("files", {})) != OUTPUT_FIELDS or not published_algorithm_matches("coastal_detail_product", m.get("algorithm_sha256"), _algorithms()) or m.get("world_seed") != 20261020 or m.get("randomness") != "none":
        raise ValueError("invalid product schema or algorithm")
    if set(m["parameters"]) != set(asdict(DetailParameters())):
        raise ValueError("incomplete detail parameters")
    params = DetailParameters(**m["parameters"])
    radius = params.validate()
    source = m["source"]
    if any(m[k] != source[k] for k in ("shape_zx", "origin_xz_m", "spacing_m")) or params.spacing_m != source["spacing_m"] or m["finite_support"] != {"filter_radius_cells": radius, "filter_radius_m": params.radius_m, "distance_support": "shared full-baseline connected-ocean land-cell shoreline; capped raster EDT", "window_contract": "slice shared support; discard radius cells on each edge"}:
        raise ValueError("inconsistent product coordinates or support")
    _preflight(source, memory_budget_bytes)
    arrays = {}
    for name, digest in m["files"].items():
        if file_hash(path / name) != digest:
            raise ValueError("product array hash mismatch")
        array = np.load(path / name, mmap_mode="r", allow_pickle=False)
        dtype = np.bool_ if name in {"valid.npy", "shoreline.npy"} else np.uint8 if name == "classification.npy" else np.float32
        if list(array.shape) != m["shape_zx"] or array.dtype != dtype or not np.isfinite(array).all():
            raise ValueError("invalid product array")
        arrays[name[:-4]] = array
    derived = _derive(source, params)
    for name, actual in arrays.items():
        if not np.array_equal(actual, derived[name]):
            raise ValueError("derived relation mismatch: " + name)
        actual.flags.writeable = False
    return m, arrays

CATEGORY = "A"
