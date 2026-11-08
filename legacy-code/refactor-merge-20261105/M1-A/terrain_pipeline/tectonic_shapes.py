"""Bounded periodic growth gauges; local coordinates X east, Z south.

These templates are generation priors, not models of tectonic physics.
Angles are radians from +X towards +Z; triangle direction points at its tip.
Scale is in cell widths. Ellipse semiaxes are scale*sqrt(aspect) and
scale/sqrt(aspect); triangles apply that same area-preserving stretch to
an equilateral triangle of circumradius scale (inradius scale/2).
"""
import hashlib

import numpy as np

MAX_ASPECT = 6.
MAX_PERIODIC_IMAGES = 4096
SHAPE_PURPOSE = "formation-shapes"


def shape_parameters(world_seed, plate_count):
    """Independent fixed stream, balanced mixed families without seed retries."""
    seed = int.from_bytes(hashlib.sha256(
        f"{world_seed}:tectonic:{SHAPE_PURPOSE}".encode()).digest()[:8], "little")
    rng = np.random.default_rng(seed)
    families = np.resize(np.array(["circle", "ellipse", "triangle"]), plate_count)
    rng.shuffle(families)
    result = []
    for family in families:
        angle = float(rng.uniform(0, 2 * np.pi))
        aspect = float(rng.uniform(4, 6) if family == "ellipse" else
                       rng.uniform(1, 2) if family == "triangle" else 1.)
        result.append(dict(family=str(family), angle_rad=angle, aspect_ratio=aspect,
                           scale_cells=1.))
    return seed, result


def validate_shape(parameters):
    if not isinstance(parameters, dict) or set(parameters) != {
            "family", "angle_rad", "aspect_ratio", "scale_cells"}:
        raise ValueError("invalid shape parameters")
    if parameters["family"] not in ("circle", "ellipse", "triangle"):
        raise ValueError("unknown growth shape")
    for name in ("angle_rad", "aspect_ratio", "scale_cells"):
        value = parameters[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
            raise ValueError("shape parameters must be finite numbers")
    if (not 0 <= parameters["angle_rad"] < 2 * np.pi or
            not 1 <= parameters["aspect_ratio"] <= MAX_ASPECT or
            not .25 <= parameters["scale_cells"] <= 4 or
            parameters["family"] == "circle" and parameters["aspect_ratio"] != 1):
        raise ValueError("shape parameters outside bounded range")


def _gauge(delta_xz, parameters):
    if parameters["family"] == "circle":
        return np.hypot(delta_xz[..., 0], delta_xz[..., 1]) / parameters["scale_cells"]
    angle = parameters["angle_rad"]
    cosine, sine = np.cos(angle), np.sin(angle)
    stretch = np.sqrt(parameters["aspect_ratio"])
    u = (delta_xz[..., 0] * cosine + delta_xz[..., 1] * sine) / stretch
    v = (-delta_xz[..., 0] * sine + delta_xz[..., 1] * cosine) * stretch
    if parameters["family"] == "triangle":
        # Outward normals of the three edges, with one vertex at (+1, 0).
        distance = np.maximum.reduce((u + np.sqrt(3) * v, -2 * u,
                                      u - np.sqrt(3) * v))
    else:
        distance = np.hypot(u, v)
    return distance / parameters["scale_cells"]


def periodic_shape_distance(delta_xz, period_xz, parameters):
    """Exact minimum gauge over a bounded set of periodic images.

    Every gauge >= Euclidean norm/(sqrt(aspect)*scale). The Euclidean
    nearest image supplies an upper bound B, so an improving image lies
    inside radius B*sqrt(aspect)*scale. Search that finite rectangle,
    rejecting requests above 4096 images before allocating the search.
    Storage is O(points); no [image,point] array is constructed.
    """
    validate_shape(parameters)
    delta = np.asarray(delta_xz, dtype=float)
    period = np.asarray(period_xz, dtype=float)
    if (delta.ndim < 1 or delta.shape[-1] != 2 or not np.isfinite(delta).all() or
            period.shape != (2,) or not np.isfinite(period).all() or np.any(period <= 0)):
        raise ValueError("finite XZ deltas and positive periods required")
    delta = (delta + period / 2) % period - period / 2
    best = _gauge(delta, parameters)
    radius = float(np.max(best, initial=0)) * np.sqrt(parameters["aspect_ratio"]) * parameters["scale_cells"]
    with np.errstate(over="ignore", invalid="ignore"):
        bounds = np.ceil(radius / period + .5)
        image_count = np.prod(2 * bounds + 1)
    if not np.isfinite(image_count) or image_count > MAX_PERIODIC_IMAGES:
        raise ValueError("periodic shape image resource budget exceeded")
    bounds = bounds.astype(int)
    for ix in range(-bounds[0], bounds[0] + 1):
        for iz in range(-bounds[1], bounds[1] + 1):
            if ix == 0 and iz == 0:
                continue
            candidate = _gauge(delta + period * (ix, iz), parameters)
            best = np.minimum(best, candidate)
    return best


def formation_image_budget(period_xz, shapes):
    """Conservative per-node image visits, using worst nearest-image norm.

    Rectangle diagonal/2 bounds that norm. The gauge's upper factor is
    sqrt(aspect)/scale for ellipses and twice that for triangles.
    """
    period = np.asarray(period_xz, dtype=float)
    total = 0
    for parameters in shapes:
        validate_shape(parameters)
        factor = 2 if parameters["family"] == "triangle" else 1
        radius = factor * parameters["aspect_ratio"] * np.linalg.norm(period / 2)
        bounds = np.ceil(radius / period + .5)
        images = float(np.prod(2 * bounds + 1))
        if not np.isfinite(images) or images > MAX_PERIODIC_IMAGES:
            raise ValueError("periodic shape image resource budget exceeded")
        total += int(images)
    return total
