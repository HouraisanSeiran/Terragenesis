"""Offline metric landform fields for special terrain that VDM cliffs cannot express.

L0 forms (volcanic plug, inselberg, sandstone pillar field, karst tower field) are
convex single-valued reliefs: they need no new surface topology, so a vertical field
displacement over a base chart is enough. Every target is one elliptical flat-top
bump whose profile decays to exactly zero at r = 1, which supplies the chart collar
by construction and keeps all four chart edges at zero displacement.

This module deliberately leaves ``metric_vdm_forms`` untouched: it carries its own
SCHEMA/ALGORITHM identity, its own kind whitelist and its own sampling-scale gate.
Nothing here is a certification: the four status flags stay False.
"""

from dataclasses import asdict, dataclass, replace
import math

import numpy as np

from terrain_pipeline.metric_vdm import _check_mesh, _smooth, _triangles
from terrain_pipeline.common_infra import (
    SOURCE_MAX_CELLS as MAX_CELLS,
    MAX_METADATA,
    identity,
    load_bundle,
    readonly,
    save_bundle,
)


SCHEMA = "metric-special-terrain-v1"
ALGORITHM = "special-terrain-field-forms-v1"
ARRAY_KEYS = {"reference_xyz_m", "displacement_xyz_m", "vertices_xyz_m", "triangles",
              "protected_mask"}
COORDINATES = "xyz metres; chart [row,col]"
BASE_KINDS = frozenset({"synthetic_analytic", "td_fine_bed"})
SAMPLES_PER_FEATURE = 4

# Radial flat-top fraction per kind: the fraction of the target radius that stays at
# full height before the wall band decays to the base. The band width is what the
# sampling gate measures.
PROFILES = {
    "volcanic_plug": 0.2754,
    "inselberg": 0.55,
    "karst_tower_field": 0.72,
    "sandstone_pillar_field": 0.80,
}
KINDS = frozenset(PROFILES)
GRADES = frozenset({"verified", "secondary", "assumed"})

# Numeric inputs and where each one comes from. Values are provenance grades against
# .scratch/special-terrain/parameters-and-sources.md; "assumed" means the number has
# no source and is only a parameterisation choice, never a measurement.
PARAMETER_SOURCES = {
    "volcanic_plug": {"height_m": ("verified", "parameters-and-sources.md#1 devils-tower NPS 264 m"),
                      "radius_x_m": ("secondary", "parameters-and-sources.md#2 base diameter 305 m"),
                      "flat_top_fraction": ("secondary", "parameters-and-sources.md#2 top/base 84/305"),
                      "joint_texture": ("verified", "parameters-and-sources.md#1 3..7 sided columns, not modelled in v1")},
    "inselberg": {"height_m": ("secondary", "parameters-and-sources.md#2 uluru 348 m, 335 m variant unresolved"),
                  "radius_x_m": ("secondary", "parameters-and-sources.md#2 length 3.6 km"),
                  "radius_z_m": ("secondary", "parameters-and-sources.md#2 perimeter 9.0..9.4 km implies half width ~1.0 km"),
                  "wall_band": ("assumed", "parameters-and-sources.md#4.2 steep wall distribution")},
    "sandstone_pillar_field": {"height_m": ("secondary", "parameters-and-sources.md#2 tens of metres to 400 m"),
                               "height_band": ("assumed", "parameters-and-sources.md#4.3 sampling gate truncates the tall end"),
                               "radius_m": ("assumed", "parameters-and-sources.md#3 base diameter not obtained"),
                               "pitch_m": ("assumed", "parameters-and-sources.md#3 pillar spacing not obtained"),
                               "iron_cap_m": ("secondary", "parameters-and-sources.md#2 about 30 m cap, not modelled in v1")},
    "karst_tower_field": {"height_m": ("secondary", "parameters-and-sources.md#2 tens to 200+ m"),
                          "radius_m": ("assumed", "parameters-and-sources.md#3 base diameter not obtained"),
                          "pitch_m": ("assumed", "parameters-and-sources.md#3 peak spacing not obtained")},
}


def _finite_number(value, name, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"invalid {name}")


@dataclass(frozen=True)
class FormTarget:
    """One landform centre in the chart frame.

    The footprint is an ellipse in metres about ``center_xz_m``; ``base_elevation_m``
    is the foot elevation and ``height_m`` the relief above it. Provenance grade and
    ledger reference are mandatory so no generated number is anonymous.
    """

    target_id: str
    center_x_m: float
    center_z_m: float
    base_elevation_m: float
    height_m: float
    radius_x_m: float
    radius_z_m: float
    source_grade: str
    source_ref: str

    def __post_init__(self):
        if not isinstance(self.target_id, str) or not self.target_id.strip():
            raise ValueError("invalid target id")
        for name in ("center_x_m", "center_z_m", "base_elevation_m"):
            _finite_number(getattr(self, name), name)
        for name in ("height_m", "radius_x_m", "radius_z_m"):
            _finite_number(getattr(self, name), name, positive=True)
        if self.source_grade not in GRADES:
            raise ValueError("invalid target source grade")
        if not isinstance(self.source_ref, str) or not self.source_ref.strip():
            raise ValueError("target source reference required")


@dataclass(frozen=True)
class SpecialFormRecipe:
    """Chart extent, spacing and target list for one special terrain form kind.

    ``collar_margin_m`` is the empty band that must remain between every target
    footprint and the chart edge; it is the field analogue of the VDM collar that
    keeps the four chart edges at zero displacement.
    """

    kind: str
    size_x_m: float
    size_z_m: float
    spacing_m: float
    collar_margin_m: float
    targets: tuple
    seed: int

    def __post_init__(self):
        if not isinstance(self.kind, str) or self.kind not in KINDS:
            raise ValueError("invalid special terrain form kind")
        for name in ("size_x_m", "size_z_m", "spacing_m", "collar_margin_m"):
            _finite_number(getattr(self, name), name, positive=True)
        if type(self.seed) is not int or not 0 <= self.seed <= 2**32 - 1:
            raise ValueError("invalid form seed")
        if not isinstance(self.targets, tuple) or not self.targets:
            raise ValueError("special terrain form requires a target tuple")
        for target in self.targets:
            if not isinstance(target, FormTarget):
                raise ValueError("FormTarget required")
        if len({target.target_id for target in self.targets}) != len(self.targets):
            raise ValueError("duplicate target id")


def form_preset(kind):
    """Deterministic preset per kind. Every numeric input traces to the ledger."""
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("invalid special terrain form kind")
    if kind == "volcanic_plug":
        target = FormTarget("devils-tower", 0.0, 0.0, 0.0, 264.0, 152.5, 152.5,
                            "secondary", "parameters-and-sources.md#4.1")
        return SpecialFormRecipe(kind, 410.0, 410.0, 1.0, 50.0, (target,), 20261003)
    if kind == "inselberg":
        target = FormTarget("uluru", 0.0, 0.0, 0.0, 348.0, 1800.0, 1000.0,
                            "secondary", "parameters-and-sources.md#4.2")
        return SpecialFormRecipe(kind, 3800.0, 2200.0, 8.0, 40.0, (target,), 20261003)
    if kind == "sandstone_pillar_field":
        targets = pillar_field_targets(
            prefix="zhangjiajie", rows=4, cols=4, pitch_m=30.0, seed=20261003,
            radius_m=12.0, height_band_m=(40.0, 150.0), jitter_fraction=0.25,
            source_grade="assumed", source_ref="parameters-and-sources.md#4.3")
        return SpecialFormRecipe(kind, 160.0, 160.0, 0.5, 10.0, targets, 20261003)
    if kind == "karst_tower_field":
        targets = pillar_field_targets(
            prefix="guilin-tower", rows=3, cols=3, pitch_m=160.0, seed=20261004,
            radius_m=40.0, height_band_m=(60.0, 200.0), jitter_fraction=0.0,
            source_grade="assumed", source_ref="parameters-and-sources.md#4.4")
        return SpecialFormRecipe(kind, 490.0, 490.0, 1.0, 40.0, targets, 20261004)
    raise ValueError("invalid special terrain form kind")


def pillar_field_targets(*, prefix, rows, cols, pitch_m, seed, radius_m, height_band_m,
                         jitter_fraction, source_grade, source_ref):
    """Seeded, deterministic column field.

    Placement is a centred grid with bounded jitter and heights are drawn from the
    declared band, so the same seed always yields the same target tuple.
    """
    for name, value in (("pitch_m", pitch_m), ("radius_m", radius_m)):
        _finite_number(value, name, positive=True)
    if type(rows) is not int or type(cols) is not int or rows < 1 or cols < 1:
        raise ValueError("invalid pillar field rows/cols")
    low, high = height_band_m
    _finite_number(low, "height band minimum", positive=True)
    _finite_number(high, "height band maximum", positive=True)
    if high < low:
        raise ValueError("invalid pillar height band")
    _finite_number(jitter_fraction, "jitter fraction")
    if not 0.0 <= jitter_fraction < 0.5:
        raise ValueError("jitter fraction must stay below half a pitch")
    rng = np.random.default_rng(seed)
    targets = []
    for row in range(rows):
        for col in range(cols):
            center_x = (col - 0.5 * (cols - 1)) * pitch_m
            center_z = (row - 0.5 * (rows - 1)) * pitch_m
            jitter = rng.uniform(-jitter_fraction, jitter_fraction, size=2) * pitch_m
            height = float(rng.uniform(low, high))
            targets.append(FormTarget(
                f"{prefix}-{row}-{col}", float(center_x + jitter[0]),
                float(center_z + jitter[1]), 0.0, height, radius_m, radius_m,
                source_grade, source_ref))
    return tuple(targets)


def analytic_base_chart(*, size_x_m, size_z_m, spacing_m, base_elevation_m=0.0,
                        slope_x=0.0, slope_z=0.0):
    """Closed uniform analytic base bed: a plane with optional constant slope.

    This is a synthetic reference surface, not sampled Terrain Diffusion output; the
    bundle metadata records ``base = synthetic_analytic`` for exactly that reason.
    """
    for name, value in (("size_x_m", size_x_m), ("size_z_m", size_z_m), ("spacing_m", spacing_m)):
        _finite_number(value, name, positive=True)
    for name, value in (("base_elevation_m", base_elevation_m), ("slope_x", slope_x),
                        ("slope_z", slope_z)):
        _finite_number(value, name)
    cols_exact = size_x_m / spacing_m
    rows_exact = size_z_m / spacing_m
    if abs(cols_exact - round(cols_exact)) > 1e-9 or abs(rows_exact - round(rows_exact)) > 1e-9:
        raise ValueError("chart size must be an integer number of spacing steps")
    rows, cols = int(round(rows_exact)) + 1, int(round(cols_exact)) + 1
    if rows < 3 or cols < 3 or rows * cols > MAX_CELLS:
        raise ValueError("analytic base chart outside cell budget")
    x = (np.arange(cols) - 0.5 * (cols - 1)) * spacing_m
    z = (np.arange(rows) - 0.5 * (rows - 1)) * spacing_m
    reference = np.zeros((rows, cols, 3), dtype=np.float64)
    reference[:, :, 0] = x[None, :]
    reference[:, :, 2] = z[:, None]
    reference[:, :, 1] = base_elevation_m + slope_x * x[None, :] + slope_z * z[:, None]
    if not np.isfinite(reference).all():
        raise ValueError("nonfinite analytic base chart")
    return reference


def _adjacent_spacing(reference):
    horizontal = reference[:, :, (0, 2)]
    adjacent = np.concatenate((np.linalg.norm(np.diff(horizontal, axis=0), axis=2).ravel(),
                               np.linalg.norm(np.diff(horizontal, axis=1), axis=2).ravel()))
    if not np.isfinite(adjacent).all() or np.any(adjacent <= 0):
        raise ValueError("invalid adjacent horizontal chart spacing")
    return float(np.min(adjacent)), float(np.max(adjacent))


def _check_sampling_scale(recipe, reference):
    """Field analogue of the VDM wavelength gate: the narrowest wall band decides."""
    minimum, maximum = _adjacent_spacing(reference)
    if maximum - minimum > 1e-6 * maximum:
        raise ValueError("special terrain chart must be a uniform grid")
    band = 1.0 - PROFILES[recipe.kind]
    for target in recipe.targets:
        wall_width = band * min(target.radius_x_m, target.radius_z_m)
        limit = SAMPLES_PER_FEATURE * maximum
        if wall_width < limit:
            raise ValueError(
                f"target {target.target_id} wall band {wall_width:.6g} m is below the "
                f"{SAMPLES_PER_FEATURE}x sampling limit {limit:.6g} m; refine the chart "
                f"spacing or enlarge the target")
    if recipe.collar_margin_m < 2 * maximum:
        raise ValueError("collar margin below two chart cells")


def _check_target_containment(recipe, reference):
    x0, x1 = float(reference[:, :, 0].min()), float(reference[:, :, 0].max())
    z0, z1 = float(reference[:, :, 2].min()), float(reference[:, :, 2].max())
    margin = recipe.collar_margin_m
    for target in recipe.targets:
        if (target.center_x_m - target.radius_x_m - margin < x0 or
                target.center_x_m + target.radius_x_m + margin > x1 or
                target.center_z_m - target.radius_z_m - margin < z0 or
                target.center_z_m + target.radius_z_m + margin > z1):
            raise ValueError(f"target {target.target_id} leaves no chart collar")


def _relief(reference, recipe):
    """Maximum flat-top elliptical bump over every target, evaluated in metres."""
    x = reference[:, :, 0]
    z = reference[:, :, 2]
    flat_top = PROFILES[recipe.kind]
    band = 1.0 - flat_top
    relief = np.full(reference.shape[:2], -np.inf, dtype=np.float64)
    for target in recipe.targets:
        across = (x - target.center_x_m) / target.radius_x_m
        along = (z - target.center_z_m) / target.radius_z_m
        radial = np.sqrt(across * across + along * along)
        profile = _smooth((1.0 - radial) / band)
        relief = np.maximum(relief, target.base_elevation_m + target.height_m * profile)
    if not np.isfinite(relief).all():
        raise ValueError("nonfinite special terrain relief")
    return relief


def _recipe_record(recipe):
    record = asdict(recipe)
    return {**record, "targets": [asdict(target) for target in recipe.targets]}


def _parse_recipe_record(record):
    if not isinstance(record, dict) or set(record) != {
            "kind", "size_x_m", "size_z_m", "spacing_m", "collar_margin_m", "targets", "seed"}:
        raise ValueError("invalid saved special terrain recipe")
    targets = tuple(FormTarget(**target) for target in record["targets"])
    return SpecialFormRecipe(**{**record, "targets": targets})


def build_special_form_vdm(reference_xyz_m, *, recipe: SpecialFormRecipe, protected_mask,
                           source_identity: str, protection_identity: str,
                           base_kind: str = "synthetic_analytic"):
    if not isinstance(recipe, SpecialFormRecipe):
        raise ValueError("SpecialFormRecipe required")
    if base_kind not in BASE_KINDS:
        raise ValueError("invalid base kind")
    reference = np.asarray(reference_xyz_m)
    if (reference.ndim != 3 or reference.shape[2] != 3 or min(reference.shape[:2]) < 3 or
            reference.shape[0] * reference.shape[1] > MAX_CELLS or
            reference.dtype.kind not in "fiu" or not np.isfinite(reference).all()):
        raise ValueError("invalid metric special terrain reference chart")
    reference = np.array(reference, dtype=np.float64, copy=True)
    mask = np.asarray(protected_mask)
    if mask.shape != reference.shape[:2] or mask.dtype != bool:
        raise ValueError("protected_mask must be a boolean chart")
    for name, value in (("source_identity", source_identity),
                        ("protection_identity", protection_identity)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} required")
    _check_sampling_scale(recipe, reference)
    _check_target_containment(recipe, reference)

    bed = reference[:, :, 1]
    displacement = np.zeros_like(reference)
    displacement[:, :, 1] = np.maximum(_relief(reference, recipe) - bed, 0.0)
    displacement[mask] = 0
    displacement[0] = displacement[-1] = 0
    displacement[:, 0] = displacement[:, -1] = 0
    vertices = (reference + displacement).reshape(-1, 3)
    if not np.isfinite(vertices).all():
        raise ValueError("nonfinite special terrain position")
    triangles = _triangles(*mask.shape)
    _check_mesh(vertices, triangles)
    arrays = {"reference_xyz_m": readonly(reference), "displacement_xyz_m": readonly(displacement),
              "vertices_xyz_m": readonly(vertices), "triangles": readonly(triangles),
              "protected_mask": readonly(mask)}
    metadata = {"schema": SCHEMA, "algorithm": ALGORITHM, "coordinates": COORDINATES,
                "base": base_kind, "recipe": _recipe_record(recipe),
                "parameter_sources": {recipe.kind: {field: list(value) for field, value in
                                                   PARAMETER_SOURCES[recipe.kind].items()}},
                "source_identity": source_identity, "protection_identity": protection_identity,
                "hydraulic_ready": False, "natural_outlet_verified": False,
                "publishable": False, "self_intersection_verified": False}
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_special_form_vdm(result)
    return result


def validate_special_form_vdm(result):
    if not isinstance(result, dict) or set(result) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid special terrain bundle")
    arrays, metadata = result["arrays"], result["metadata"]
    if not isinstance(arrays, dict) or set(arrays) != ARRAY_KEYS or not isinstance(metadata, dict):
        raise ValueError("invalid special terrain fields")
    if (set(metadata) != {"schema", "algorithm", "coordinates", "base", "recipe",
                          "parameter_sources", "source_identity", "protection_identity",
                          "hydraulic_ready", "natural_outlet_verified", "publishable",
                          "self_intersection_verified"} or
            metadata["schema"] != SCHEMA or metadata["algorithm"] != ALGORITHM or
            metadata["coordinates"] != COORDINATES or metadata["base"] not in BASE_KINDS or
            any(metadata[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified",
                                                      "publishable", "self_intersection_verified"))):
        raise ValueError("invalid special terrain metadata")
    for key in ("source_identity", "protection_identity"):
        if not isinstance(metadata[key], str) or not metadata[key].strip():
            raise ValueError("missing upstream identity")
    try:
        recipe = _parse_recipe_record(metadata["recipe"])
    except (TypeError, KeyError, ValueError) as error:
        raise ValueError("invalid saved special terrain recipe") from error
    if metadata["parameter_sources"] != {recipe.kind: {field: list(value) for field, value in
                                                       PARAMETER_SOURCES[recipe.kind].items()}}:
        raise ValueError("special terrain parameter provenance mismatch")
    reference = arrays["reference_xyz_m"]
    displacement = arrays["displacement_xyz_m"]
    vertices = arrays["vertices_xyz_m"]
    triangles = arrays["triangles"]
    mask = arrays["protected_mask"]
    if (not all(isinstance(value, np.ndarray) for value in arrays.values()) or
            reference.ndim != 3 or reference.shape[2] != 3 or min(reference.shape[:2]) < 3 or
            reference.shape[0] * reference.shape[1] > MAX_CELLS or
            reference.dtype != np.float64 or displacement.shape != reference.shape or
            displacement.dtype != np.float64 or
            vertices.shape != (reference.shape[0] * reference.shape[1], 3) or
            vertices.dtype != np.float64 or mask.shape != reference.shape[:2] or
            mask.dtype != bool or
            triangles.shape != (2 * (mask.shape[0] - 1) * (mask.shape[1] - 1), 3) or
            triangles.dtype != np.int64):
        raise ValueError("invalid special terrain array shape or dtype")
    if (not np.isfinite(reference).all() or not np.isfinite(displacement).all() or
            not np.isfinite(vertices).all() or
            not np.array_equal(vertices, (reference + displacement).reshape(-1, 3)) or
            not np.array_equal(triangles, _triangles(*mask.shape)) or
            np.any(displacement[mask] != 0) or np.any(displacement[0] != 0) or
            np.any(displacement[-1] != 0) or np.any(displacement[:, 0] != 0) or
            np.any(displacement[:, -1] != 0)):
        raise ValueError("invalid special terrain geometry or collar")
    _check_mesh(vertices, triangles)
    if result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("special terrain identity mismatch")
    return True


def _special_headers(headers):
    if set(headers) != ARRAY_KEYS | {"manifest"}:
        raise ValueError("unexpected special terrain archive fields")
    shape, dtype = headers["reference_xyz_m"]
    if (len(shape) != 3 or shape[2] != 3 or min(shape[:2]) < 3 or
            shape[0] * shape[1] > MAX_CELLS or dtype != np.float64):
        raise ValueError("invalid special terrain reference header")
    rows, cols = shape[:2]
    expected = {"displacement_xyz_m": (shape, np.dtype("float64")),
                "vertices_xyz_m": ((rows * cols, 3), np.dtype("float64")),
                "triangles": ((2 * (rows - 1) * (cols - 1), 3), np.dtype("int64")),
                "protected_mask": ((rows, cols), np.dtype(bool))}
    if any(headers[key] != value for key, value in expected.items()):
        raise ValueError("invalid special terrain array header")
    manifest_shape, manifest_dtype = headers["manifest"]
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= MAX_METADATA or manifest_dtype != np.uint8:
        raise ValueError("invalid special terrain manifest header")


def save_special_form_vdm(path, result):
    save_bundle(path, result, validator=validate_special_form_vdm)


def load_special_form_vdm(path, *, expected_sha256, expected_identity):
    if not isinstance(expected_identity, str) or len(expected_identity) != 64:
        raise ValueError("expected special terrain identity required")
    result = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_special_form_vdm, header_validator=_special_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external special terrain identity mismatch")
    return result
