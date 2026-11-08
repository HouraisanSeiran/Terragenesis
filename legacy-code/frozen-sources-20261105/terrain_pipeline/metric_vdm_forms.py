"""Deterministic metric cliff forms layered over the validated VDM skeleton."""

from dataclasses import asdict, dataclass, replace
import math

import numpy as np

from terrain_pipeline.metric_vdm import (
    ALGORITHM as BASE_ALGORITHM, SCHEMA as BASE_SCHEMA, CliffRecipe, _smooth,
    _vdm_headers, build_vdm, validate_vdm,
)
from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle


SCHEMA = "metric-vdm-forms-v1"
ALGORITHM = "coherent-cliff-forms-v1"
SCHEMA_V2 = "metric-vdm-forms-v2"
ALGORITHM_V2 = "coherent-cliff-forms-v2"
KINDS = frozenset({"layered_ledge", "undercut_alcove", "fluted_wall", "stepped_wall",
                   "curved_escarpment", "massive_overhang"})


@dataclass(frozen=True)
class FormRecipe:
    """Wavelength is chart structural length, not vertical layer thickness.

    Curvature is outward-positive at the wall center. End difference is the added
    height at the positive inner fade end minus the negative inner fade end, both
    at v=0; the outer collar returns to the reference bed. Direction rotates
    from +X toward +Z in degrees and None inherits the cliff recipe direction.
    """

    kind: str
    amplitude_m: float
    wavelength_m: float
    seed: int
    surface_curvature_m: float = 0.0
    end_elevation_difference_m: float = 0.0
    extension_direction_degrees: float | None = None

    def __post_init__(self):
        if not isinstance(self.kind, str) or self.kind not in KINDS:
            raise ValueError("invalid cliff form kind")
        if (type(self.amplitude_m) not in (int, float) or not math.isfinite(self.amplitude_m)
                or self.amplitude_m <= 0):
            raise ValueError("invalid form amplitude_m")
        if (type(self.wavelength_m) not in (int, float) or not math.isfinite(self.wavelength_m)
                or self.wavelength_m <= 0):
            raise ValueError("invalid form wavelength_m")
        if type(self.seed) is not int or not 0 <= self.seed <= 2**32 - 1:
            raise ValueError("invalid form seed")
        for name in ("surface_curvature_m", "end_elevation_difference_m"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"invalid form {name}")
        if abs(self.surface_curvature_m) > 0.5 * self.wavelength_m:
            raise ValueError("form surface curvature exceeds structural scale")
        if self.extension_direction_degrees is not None and (
                type(self.extension_direction_degrees) not in (int, float) or
                not math.isfinite(self.extension_direction_degrees)):
            raise ValueError("invalid extension direction")


def _spacing(reference):
    horizontal = reference[:, :, (0, 2)]
    adjacent = np.concatenate((np.linalg.norm(np.diff(horizontal, axis=0), axis=2).ravel(),
                               np.linalg.norm(np.diff(horizontal, axis=1), axis=2).ravel()))
    if not np.isfinite(adjacent).all() or np.any(adjacent <= 0):
        raise ValueError("invalid adjacent horizontal reference spacing")
    return float(np.min(adjacent)), float(np.max(adjacent))


def _check_form_scale(form, recipe, reference):
    _, maximum = _spacing(reference)
    if form.wavelength_m < 4 * maximum:
        raise ValueError("form wavelength below chart sampling limit")
    if form.amplitude_m > min(0.25 * recipe.height_m, 0.5 * recipe.wall_half_width_m):
        raise ValueError("form amplitude exceeds conservative cliff scale")
    if abs(form.end_elevation_difference_m) > recipe.height_m:
        raise ValueError("end elevation difference exceeds cliff height")
    if form.end_elevation_difference_m and not 0 < recipe.end_fade_m < recipe.half_length_m:
        raise ValueError("end elevation difference requires an interior fade")


def _shape(form, u, v, recipe):
    phase = np.random.default_rng(form.seed).uniform(0, 2 * math.pi, size=3)
    wave = 2 * math.pi / form.wavelength_m
    across = (recipe.wall_half_width_m - v) / (2 * recipe.wall_half_width_m)
    wall = _smooth((recipe.half_depth_m - np.abs(v)) /
                   (recipe.half_depth_m - recipe.wall_half_width_m))
    ends = _smooth((recipe.half_length_m - np.abs(u)) / recipe.end_fade_m)
    envelope = wall * ends
    band = np.exp(-((v - 0.2 * recipe.wall_half_width_m) /
                    (0.8 * recipe.wall_half_width_m)) ** 2)
    longitudinal = np.sin(wave * u + phase[0])
    secondary = np.sin(0.5 * wave * u + phase[1])
    if form.kind == "layered_ledge":
        layers = np.sin(wave * v + phase[2])
        shelves = np.maximum(0, layers) ** 2
        horizontal = (0.75 * shelves - 0.2 * np.maximum(0, -layers)) * band
        vertical = 0.2 * layers * band
    elif form.kind == "undercut_alcove":
        recess = np.exp(-((across - 0.32) / 0.24) ** 2)
        arch = _smooth((secondary + 1) / 2)
        horizontal = -recess * (0.55 + 0.45 * arch)
        vertical = -0.18 * recess * arch
    elif form.kind == "fluted_wall":
        horizontal = longitudinal * band * (0.75 + 0.25 * secondary)
        vertical = 0.12 * longitudinal * band
    elif form.kind == "stepped_wall":
        terraces = np.tanh(3 * np.sin(wave * v + phase[2]))
        horizontal = terraces * band * (0.85 + 0.15 * secondary)
        vertical = 0.3 * terraces * band
    elif form.kind == "curved_escarpment":
        bend = np.sin(0.5 * wave * u + phase[0])
        horizontal = (0.85 * bend + 0.15 * secondary) * _smooth(
            (recipe.half_depth_m - np.abs(v)) / recipe.half_depth_m)
        vertical = 0.08 * bend * band
    elif form.kind == "massive_overhang":
        cap = _smooth((across - 0.42) / 0.35)
        horizontal = cap * (0.8 + 0.2 * secondary)
        vertical = 0.15 * cap
    else:  # pragma: no cover - unreachable while KINDS covers every branch
        raise ValueError(f"unknown cliff form kind: {form.kind!r}")
    if form.surface_curvature_m == 0 and form.end_elevation_difference_m == 0:
        return form.amplitude_m * envelope * horizontal, form.amplitude_m * envelope * vertical
    surface_curvature = form.surface_curvature_m * np.maximum(
        0.0, 1.0 - (v / recipe.wall_half_width_m) ** 2) ** 2 * ends
    inner_end = recipe.half_length_m - recipe.end_fade_m
    end_tilt = (0.5 * form.end_elevation_difference_m * np.clip(
        u / inner_end, -1.0, 1.0) * wall * ends) if form.end_elevation_difference_m else 0.0
    return (form.amplitude_m * envelope * horizontal + surface_curvature,
            form.amplitude_m * envelope * vertical + end_tilt)


def _oriented_recipe(recipe, form):
    if form.extension_direction_degrees is None:
        return recipe
    angle = math.radians(form.extension_direction_degrees % 360)
    along = np.array((math.cos(angle), math.sin(angle)))
    outward = (-along[1], along[0])
    return replace(recipe, outward_xz=(float(outward[0]), float(outward[1])))


def build_formed_vdm(reference_xyz_m, *, recipe: CliffRecipe, form: FormRecipe,
                     protected_mask, source_identity, protection_identity):
    if not isinstance(form, FormRecipe):
        raise ValueError("FormRecipe required")
    oriented_recipe = _oriented_recipe(recipe, form)
    base = build_vdm(reference_xyz_m, recipe=oriented_recipe, protected_mask=protected_mask,
                     source_identity=source_identity, protection_identity=protection_identity)
    arrays = base["arrays"]
    reference = arrays["reference_xyz_m"]
    _check_form_scale(form, recipe, reference)
    outward = np.asarray(oriented_recipe.outward_xz, dtype=np.float64)
    outward /= np.linalg.norm(outward)
    along = np.array((outward[1], -outward[0]))
    offset = reference[:, :, (0, 2)] - recipe.center_xz_m
    u = offset @ along
    v = offset @ outward
    horizontal, vertical = _shape(form, u, v, recipe)
    displacement = arrays["displacement_xyz_m"].copy()
    displacement[:, :, 0] += outward[0] * horizontal
    displacement[:, :, 1] += vertical
    displacement[:, :, 2] += outward[1] * horizontal
    displacement[arrays["protected_mask"]] = 0
    displacement[0] = displacement[-1] = 0
    displacement[:, 0] = displacement[:, -1] = 0
    formed_arrays = {**arrays, "displacement_xyz_m": readonly(displacement),
                     "vertices_xyz_m": readonly((reference + displacement).reshape(-1, 3))}
    form_record = asdict(form)
    default_controls = (form.surface_curvature_m == 0 and
                        form.end_elevation_difference_m == 0 and
                        form.extension_direction_degrees is None)
    if default_controls:
        form_record = {key: form_record[key] for key in
                       ("kind", "amplitude_m", "wavelength_m", "seed")}
    metadata = {**base["metadata"],
                "schema": SCHEMA if default_controls else SCHEMA_V2,
                "algorithm": ALGORITHM if default_controls else ALGORITHM_V2,
                "form": form_record, "base_identity_sha256": base["identity_sha256"]}
    result = {"arrays": formed_arrays, "metadata": metadata,
              "identity_sha256": identity(formed_arrays, metadata)}
    validate_formed_vdm(result)
    return result


def validate_formed_vdm(result):
    if not isinstance(result, dict) or set(result) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid formed VDM bundle")
    metadata = result["metadata"]
    if not isinstance(metadata, dict) or set(metadata) != {
            "schema", "algorithm", "coordinates", "recipe", "source_identity",
            "protection_identity", "hydraulic_ready", "natural_outlet_verified",
            "publishable", "self_intersection_verified", "form", "base_identity_sha256"}:
        raise ValueError("invalid formed VDM metadata")
    versions = {SCHEMA: ALGORITHM, SCHEMA_V2: ALGORITHM_V2}
    if metadata["schema"] not in versions or metadata["algorithm"] != versions[metadata["schema"]]:
        raise ValueError("invalid formed VDM version")
    base_identity = metadata["base_identity_sha256"]
    if (not isinstance(base_identity, str) or len(base_identity) != 64 or
            any(character not in "0123456789abcdef" for character in base_identity)):
        raise ValueError("invalid base VDM identity")
    try:
        form_record = metadata["form"]
        form = FormRecipe(**form_record)
        expected_fields = set(asdict(form))
        if metadata["schema"] == SCHEMA:
            expected_fields -= {"surface_curvature_m", "end_elevation_difference_m",
                                "extension_direction_degrees"}
        elif (form.surface_curvature_m == 0 and form.end_elevation_difference_m == 0 and
              form.extension_direction_degrees is None):
            raise ValueError("default controls require v1")
        if set(form_record) != expected_fields:
            raise ValueError("unexpected form field")
        recipe_record = metadata["recipe"]
        recipe = CliffRecipe(**{**recipe_record,
                               "center_xz_m": tuple(recipe_record["center_xz_m"]),
                               "outward_xz": tuple(recipe_record["outward_xz"])})
        if form.extension_direction_degrees is not None:
            angle = math.radians(form.extension_direction_degrees % 360)
            expected_outward = (-math.sin(angle), math.cos(angle))
            actual_outward = np.asarray(recipe.outward_xz, dtype=float)
            actual_outward /= np.linalg.norm(actual_outward)
            if not np.allclose(actual_outward, expected_outward, rtol=0, atol=1e-12):
                raise ValueError("saved extension direction disagrees with recipe")
    except (TypeError, KeyError, ValueError, AttributeError) as error:
        raise ValueError("invalid saved form or recipe") from error
    base_metadata = {key: value for key, value in metadata.items()
                     if key not in ("form", "base_identity_sha256")}
    base_metadata.update(schema=BASE_SCHEMA, algorithm=BASE_ALGORITHM)
    projection = {"arrays": result["arrays"], "metadata": base_metadata,
                  "identity_sha256": identity(result["arrays"], base_metadata)}
    validate_vdm(projection)
    _check_form_scale(form, recipe, result["arrays"]["reference_xyz_m"])
    if result["identity_sha256"] != identity(result["arrays"], metadata):
        raise ValueError("formed VDM identity mismatch")
    return True


def save_formed_vdm(path, result):
    save_bundle(path, result, validator=validate_formed_vdm)


def load_formed_vdm(path, *, expected_sha256, expected_identity):
    if not isinstance(expected_identity, str) or len(expected_identity) != 64:
        raise ValueError("expected formed VDM identity required")
    result = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_formed_vdm, header_validator=_vdm_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external formed VDM identity mismatch")
    return result
