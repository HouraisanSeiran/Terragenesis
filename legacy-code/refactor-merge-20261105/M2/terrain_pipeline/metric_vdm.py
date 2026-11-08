"""Metric surface-chart VDM using the CliffGeometry skeleton without game scaling."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.common_infra import (
    SOURCE_MAX_CELLS as MAX_CELLS,
    MAX_METADATA,
    identity,
    load_bundle,
    readonly,
    save_bundle,
)


SCHEMA = "metric-vdm-v1"
ALGORITHM = "cliff-skeleton-v1"
ARRAY_KEYS = {"reference_xyz_m", "displacement_xyz_m", "vertices_xyz_m", "triangles", "protected_mask"}


def _finite_number(value, name, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"invalid {name}")


@dataclass(frozen=True)
class CliffRecipe:
    center_xz_m: tuple
    outward_xz: tuple
    height_m: float
    half_length_m: float
    half_depth_m: float
    wall_half_width_m: float
    end_fade_m: float
    angle_degrees: float
    lean: int

    def __post_init__(self):
        for name in ("center_xz_m", "outward_xz"):
            pair = getattr(self, name)
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError(f"invalid {name}")
            for value in pair:
                _finite_number(value, name)
        if math.hypot(*self.outward_xz) == 0:
            raise ValueError("outward direction must be nonzero")
        for name in ("height_m", "half_length_m", "half_depth_m", "wall_half_width_m", "end_fade_m"):
            _finite_number(getattr(self, name), name, positive=True)
        if self.wall_half_width_m >= self.half_depth_m:
            raise ValueError("wall must fit inside depth collar")
        _finite_number(self.angle_degrees, "angle_degrees")
        if not 60 <= self.angle_degrees <= 90 or type(self.lean) is not int or self.lean not in (-1, 1):
            raise ValueError("invalid cliff angle or lean")


def _smooth(value):
    fraction = np.clip(value, 0, 1)
    return fraction * fraction * (3 - 2 * fraction)


def _triangles(rows, cols):
    cell_rows, cell_cols = np.indices((rows - 1, cols - 1))
    upper_left = (cell_rows * cols + cell_cols).ravel()
    upper_right = upper_left + 1
    lower_left = upper_left + cols
    lower_right = lower_left + 1
    triangles = np.empty((2 * upper_left.size, 3), dtype=np.int64)
    triangles[0::2] = np.stack((upper_left, lower_left, lower_right), axis=-1)
    triangles[1::2] = np.stack((upper_left, lower_right, upper_right), axis=-1)
    return triangles


def _check_mesh(vertices, triangles):
    points = vertices[triangles]
    first = points[:, 1] - points[:, 0]
    second = points[:, 2] - points[:, 0]
    cross = np.cross(first, second)
    scale = np.linalg.norm(first, axis=1) * np.linalg.norm(second, axis=1)
    if (not np.isfinite(points).all() or not np.isfinite(cross).all() or
            np.any(scale == 0) or np.any(np.linalg.norm(cross, axis=1) <= 1e-12 * scale)):
        raise ValueError("nonfinite or degenerate VDM triangle")


def build_vdm(reference_xyz_m, *, recipe: CliffRecipe, protected_mask, source_identity: str,
              protection_identity: str):
    if not isinstance(recipe, CliffRecipe):
        raise ValueError("CliffRecipe required")
    reference = np.asarray(reference_xyz_m)
    if (reference.ndim != 3 or reference.shape[2] != 3 or min(reference.shape[:2]) < 3 or
            reference.shape[0] * reference.shape[1] > MAX_CELLS or
            reference.dtype.kind not in "fiu" or not np.isfinite(reference).all()):
        raise ValueError("invalid metric reference chart")
    reference = np.array(reference, dtype=np.float64, copy=True)
    mask = np.asarray(protected_mask)
    if mask.shape != reference.shape[:2] or mask.dtype != bool:
        raise ValueError("protected_mask must be a boolean chart")
    for name, value in (("source_identity", source_identity), ("protection_identity", protection_identity)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} required")

    outward = np.array(recipe.outward_xz, dtype=np.float64)
    outward /= np.linalg.norm(outward)
    along = np.array((outward[1], -outward[0]))
    offset = reference[:, :, (0, 2)] - recipe.center_xz_m
    u = offset @ along
    v = offset @ outward
    end = _smooth((recipe.half_length_m - np.abs(u)) / recipe.end_fade_m)
    collar = _smooth((recipe.half_depth_m - np.abs(v)) /
                     (recipe.half_depth_m - recipe.wall_half_width_m))
    active = (end > 0) & (collar > 0)
    if (active[0].any() or active[-1].any() or active[:, 0].any() or active[:, -1].any()):
        raise ValueError("active cliff reaches chart perimeter; provide an outer collar")
    if not active.any():
        raise ValueError("cliff does not intersect chart interior")
    fraction = np.clip((recipe.wall_half_width_m - v) / (2 * recipe.wall_half_width_m), 0, 1)
    top_offset = recipe.lean * recipe.height_m / math.tan(math.radians(recipe.angle_degrees))
    horizontal = ((fraction - 0.5) * top_offset -
                  np.clip(v, -recipe.wall_half_width_m, recipe.wall_half_width_m)) * end * collar
    vertical = (fraction - 0.5) * recipe.height_m * end * collar
    displacement = np.zeros_like(reference)
    displacement[:, :, 0] = outward[0] * horizontal
    displacement[:, :, 1] = vertical
    displacement[:, :, 2] = outward[1] * horizontal
    displacement[mask] = 0
    vertices = (reference + displacement).reshape(-1, 3)
    if not np.isfinite(vertices).all():
        raise ValueError("nonfinite VDM position")
    triangles = _triangles(*mask.shape)
    _check_mesh(vertices, triangles)
    arrays = {"reference_xyz_m": readonly(reference), "displacement_xyz_m": readonly(displacement),
              "vertices_xyz_m": readonly(vertices), "triangles": readonly(triangles),
              "protected_mask": readonly(mask)}
    metadata = {"schema": SCHEMA, "algorithm": ALGORITHM, "coordinates": "xyz metres; chart [row,col]",
                "recipe": asdict(recipe), "source_identity": source_identity,
                "protection_identity": protection_identity, "hydraulic_ready": False,
                "natural_outlet_verified": False, "publishable": False,
                "self_intersection_verified": False}
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_vdm(result)
    return result


def validate_vdm(result):
    if not isinstance(result, dict) or set(result) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid VDM bundle")
    arrays, metadata = result["arrays"], result["metadata"]
    if not isinstance(arrays, dict) or set(arrays) != ARRAY_KEYS or not isinstance(metadata, dict):
        raise ValueError("invalid VDM fields")
    if (set(metadata) != {"schema", "algorithm", "coordinates", "recipe", "source_identity",
                          "protection_identity", "hydraulic_ready", "natural_outlet_verified",
                          "publishable", "self_intersection_verified"} or
            metadata["schema"] != SCHEMA or metadata["algorithm"] != ALGORITHM or
            metadata["coordinates"] != "xyz metres; chart [row,col]" or
            any(metadata[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified",
                                                     "publishable", "self_intersection_verified"))):
        raise ValueError("invalid VDM metadata")
    for key in ("source_identity", "protection_identity"):
        if not isinstance(metadata[key], str) or not metadata[key].strip():
            raise ValueError("missing upstream identity")
    try:
        recipe_record = metadata["recipe"]
        recipe = CliffRecipe(**{**recipe_record,
                               "center_xz_m": tuple(recipe_record["center_xz_m"]),
                               "outward_xz": tuple(recipe_record["outward_xz"])})
    except (TypeError, KeyError, ValueError) as error:
        raise ValueError("invalid saved cliff recipe") from error
    if set(recipe_record) != set(asdict(recipe)):
        raise ValueError("unexpected cliff recipe field")
    reference = arrays["reference_xyz_m"]
    displacement = arrays["displacement_xyz_m"]
    vertices = arrays["vertices_xyz_m"]
    triangles = arrays["triangles"]
    mask = arrays["protected_mask"]
    if (not all(isinstance(value, np.ndarray) for value in arrays.values()) or
            reference.ndim != 3 or reference.shape[2] != 3 or min(reference.shape[:2]) < 3 or
            reference.shape[0] * reference.shape[1] > MAX_CELLS or
            reference.dtype != np.float64 or displacement.shape != reference.shape or
            displacement.dtype != np.float64 or vertices.shape != (reference.shape[0] * reference.shape[1], 3) or
            vertices.dtype != np.float64 or mask.shape != reference.shape[:2] or mask.dtype != bool or
            triangles.shape != (2 * (mask.shape[0] - 1) * (mask.shape[1] - 1), 3) or
            triangles.dtype != np.int64):
        raise ValueError("invalid VDM array shape or dtype")
    if (not np.isfinite(reference).all() or not np.isfinite(displacement).all() or
            not np.isfinite(vertices).all() or not np.array_equal(vertices, (reference + displacement).reshape(-1, 3)) or
            not np.array_equal(triangles, _triangles(*mask.shape)) or
            np.any(displacement[mask] != 0) or np.any(displacement[0] != 0) or
            np.any(displacement[-1] != 0) or np.any(displacement[:, 0] != 0) or
            np.any(displacement[:, -1] != 0)):
        raise ValueError("invalid VDM geometry or collar")
    _check_mesh(vertices, triangles)
    if result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("VDM identity mismatch")
    return True


def _vdm_headers(headers):
    if set(headers) != ARRAY_KEYS | {"manifest"}:
        raise ValueError("unexpected VDM archive fields")
    shape, dtype = headers["reference_xyz_m"]
    if (len(shape) != 3 or shape[2] != 3 or min(shape[:2]) < 3 or
            shape[0] * shape[1] > MAX_CELLS or dtype != np.float64):
        raise ValueError("invalid VDM reference header")
    rows, cols = shape[:2]
    expected = {"displacement_xyz_m": (shape, np.dtype("float64")),
                "vertices_xyz_m": ((rows * cols, 3), np.dtype("float64")),
                "triangles": ((2 * (rows - 1) * (cols - 1), 3), np.dtype("int64")),
                "protected_mask": ((rows, cols), np.dtype(bool))}
    if any(headers[key] != value for key, value in expected.items()):
        raise ValueError("invalid VDM array header")
    manifest_shape, manifest_dtype = headers["manifest"]
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= MAX_METADATA or manifest_dtype != np.uint8:
        raise ValueError("invalid VDM manifest header")


def save_vdm(path, result):
    save_bundle(path, result, validator=validate_vdm)


def load_vdm(path, *, expected_sha256, expected_identity):
    if not isinstance(expected_identity, str) or len(expected_identity) != 64:
        raise ValueError("expected VDM identity required")
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_vdm,
                         header_validator=_vdm_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external VDM identity mismatch")
    return result
