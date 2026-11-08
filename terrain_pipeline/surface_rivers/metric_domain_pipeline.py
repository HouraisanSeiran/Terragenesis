"""On-demand, window-independent river domain products (P6.2 entry).

Why this module exists
----------------------
`metric_domain_closure` answers two questions as pure functions of
`(seed, world coordinate)`: *which outlet does this point drain to*
(`outlet_at` / `eligible_owner_at`) and *is this point part of a closed domain*
(`ClosureRegion.accepted`). It publishes nothing -- its docstring is explicit
that it generates no artifact.

This module is the entry that turns an arbitrary list of world coordinates into
**publishable, re-loadable domain products plus a query index**. It computes no
physics of its own. Every geometric quantity is taken verbatim from
`metric_domain_closure` (`resolve_points`, `eligible_owner_at`, `territory_of`,
`global_ocean_mask`) and every height is the raw pure field
`coarse_condition_field`. Deliberately NOT re-derived here:

* no flood and no steepest-D8 pass of its own -- a second implementation would be
  a second truth that can drift away from the module the auditor certifies;
* no rejection vocabulary of its own -- the five reasons are
  `ClosureRegion.classify`'s, spelled verbatim (`REASON_ORDER`);
* no window: the caller passes points and the closure module picks the
  world-anchored tile, so two calls cannot disagree about a coordinate.

What a product is (and is not)
------------------------------
A *domain* is identified by its **outlet world coordinate** -- never by a
window-relative index (`spec.md:25`). One product per distinct outlet. Its
authority is the scattered territory `cells_x_m` / `cells_z_m`: the LAND cells of
the owning tile's core whose drainage terminates at that outlet.
`territory_raster`, `base_height_m` and `ocean_mask` are *derived views*
resampled on the tight bounding box of those scattered cells: convenient for a
consumer, and explicitly not authoritative. The raw face carries no local
correction (P3.2), so a product is comparable with `metric_domain_closure` node
by node, but NOT with the frozen bounded planner's filled/raised surface.

Determinism
-----------
`identity_sha256` is `mountain_source_adapter.identity` over the product's own
arrays plus a JSON metadata block (schema, kind, seed, config_id, area, bbox,
spacing, raster/identity policy, limitations, cell count) -- the same hashing
idiom the rest of this repository uses. It depends on no `hash()`, no `id()`, no
time, no dict insertion order and no file path, so the same coordinate in another
process with the same spacing reproduces it bit for bit. Note precisely what is
hashed: the *array content and metadata*, not the container bytes (a `.npz` is a
zip whose entry timestamps are not content).

Nothing is ever overwritten. An existing destination is a refusal, publication
goes through a temporary file plus a hard link (the link is the commit point), so
a half-written product can never be observed.

Contract
--------
`pipeline-spec.md` (P6, `.scratch/river-infinite-world/`) is the interface
contract: entry signature 2.1, CLI 2.2, rejection vocabulary 3, product schema
4.1, batch index 4.2, repeatability 5, limitations 6, acceptance 7.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import io
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig, coarse_condition_field
from terrain_pipeline.common_infra import identity, publish_bytes
from terrain_pipeline.surface_rivers.metric_domain_closure import (
    eligible_owner_at,
    global_ocean_mask,
    resolve_points,
    territory_of,
)

__all__ = [
    "ACCEPTED_REASONS",
    "INDEX_NAME",
    "INDEX_SCHEMA",
    "LIMITATIONS",
    "MAX_RASTER_CELLS",
    "PRODUCT_KEYS",
    "REASON_ORDER",
    "SCHEMA",
    "UNRESOLVED_REASONS",
    "DomainProduct",
    "DomainProductBatch",
    "Refusal",
    "compute_identity",
    "config_identity",
    "domain_product_name",
    "load_domain_product",
    "node_spacing_m",
    "product_set_identity",
    "resolve_domain_products",
]

SCHEMA = "river-domain-product-v1"
INDEX_SCHEMA = "river-domain-index-v1"
INDEX_NAME = "river-domain-index-v1.json"

# Verbatim vocabulary of `ClosureRegion.classify` (contract 3). A refusal reason
# that is not on this list is a contract breach, not a new label to absorb.
REASON_ORDER = ("ocean", "coastal", "closed_basin", "unresolved_border", "out_of_tile")
UNRESOLVED_REASONS = ("unresolved_border", "out_of_tile")
ACCEPTED_REASONS = ("coastal", "closed_basin")

# Derived-raster budget: the tight bbox of measured territories is a handful of
# nodes (raw-face median domain = 3 cells), so this only guards a pathological
# domain from materialising a huge resampled view.
MAX_RASTER_CELLS = 256 * 256

TERRITORY_RASTER_POLICY = (
    "territory_raster is the scattered cells rasterised on the tight bbox lattice "
    "(node index = round(coordinate / spacing_m)); the authority is cells_x_m / cells_z_m"
)
IDENTITY_POLICY = (
    "sha256 over the product's own arrays (all contract keys except identity_sha256) "
    "plus a JSON metadata block; independent of path, time, hash()/id() and insertion order"
)

LIMITATIONS = (
    "plane sample only; no claim about the whole infinite world",
    "base_height_m is the RAW pure face (coarse_condition_field) with no local correction; "
    "it is not the frozen bounded planner's filled/raised surface and the two are not "
    "comparable point by point",
    "territory granularity is the base condition field's (raw-face median 3 cells, P3.1): "
    "fine domains are a property of the base field, not a defect of this product",
    "receiver is deliberately not stored: the consumer recomputes the steepest downstream on "
    "the raw face (the validate_plan discipline). The only downstream guarantee inherited is "
    "spec.md:56 (an in-domain non-marine steepest downstream stays in the domain); no "
    "hydraulics, width or sediment is certified",
    "territory cells are the LAND cells of the owning tile's CORE that drain to the outlet "
    "(ClosureRegion.territory_of_outlet); a domain that continues past that core is stored "
    "clipped and this product claims nothing about the clipped part",
    "territory_raster / base_height_m / ocean_mask are resampled views on the tight bounding "
    "box of cells_x_m / cells_z_m; the scattered cells remain the authority",
    "this pipeline certifies no naturalness: it certifies domain closure and window "
    "independence only",
)

# Contract 4.1 key set, in contract order. The npz carries exactly these and
# nothing else, so a reader can see the whole schema at a glance.
PRODUCT_KEYS = (
    "outlet_xz_m",
    "kind",
    "cells_x_m",
    "cells_z_m",
    "area_m2",
    "bbox_origin_xz_m",
    "spacing_m",
    "territory_raster",
    "base_height_m",
    "ocean_mask",
    "seed",
    "config_id",
    "identity_sha256",
    "schema",
    "limitations",
)


def _text(value):
    """Python string of a numpy scalar / 0-d string array (stable across reloads)."""
    return str(np.asarray(value).item())


def node_spacing_m(config):
    """World spacing of the closure module's node lattice for a config."""
    return float(config.macro_span_m) / float(config.samples_per_span)


def config_identity(config):
    """Deterministic identity digest of a `PlanningConfig` (contract 8).

    Exactly the repository's existing idiom `identity({}, asdict(config))`, so
    `macro_span_m` / `samples_per_span` and every other budget are pinned by the
    digest rather than by a hand-written string.
    """
    return identity({}, {"planning_config": asdict(config)})


def domain_product_name(outlet_x_m, outlet_z_m):
    """Deterministic file name of a domain product: `<x>_<z>.npz` (contract 4.1)."""
    return "%d_%d.npz" % (int(round(float(outlet_x_m))), int(round(float(outlet_z_m))))


def _node_index(value, node_spacing):
    return float(np.rint(float(value) / node_spacing))


def _quantise(value, node_spacing, label):
    """Snap a world coordinate to the closure node lattice, refusing a stray value."""
    index = _node_index(value, node_spacing)
    quantised = index * node_spacing
    if abs(quantised - float(value)) > 1e-6 * node_spacing:
        raise ValueError(
            "%s %r is not on the planning node lattice (spacing %g m)"
            % (label, float(value), node_spacing))
    return float(quantised), int(index)


def _product_metadata(arrays):
    """JSON-able metadata block that pins the hashing semantics of a product."""
    return {
        "schema": _text(arrays["schema"]),
        "kind": _text(arrays["kind"]),
        "seed": int(np.asarray(arrays["seed"]).item()),
        "config_id": _text(arrays["config_id"]),
        "spacing_m": float(np.asarray(arrays["spacing_m"]).item()),
        "area_m2": float(np.asarray(arrays["area_m2"]).item()),
        "bbox_origin_xz_m": [float(value) for value in np.asarray(arrays["bbox_origin_xz_m"]).reshape(-1)],
        "raster_shape": [int(size) for size in np.asarray(arrays["territory_raster"]).shape],
        "cell_count": int(np.asarray(arrays["cells_x_m"]).size),
        "territory_raster_policy": TERRITORY_RASTER_POLICY,
        "identity_policy": IDENTITY_POLICY,
        "limitations": [_text(value) for value in np.asarray(arrays["limitations"]).reshape(-1)],
        "receiver_stored": False,
    }


def compute_identity(arrays):
    """`identity_sha256` of a product: content only, never the digest itself.

    Excluding `identity_sha256` is not an optimisation: a digest cannot contain
    itself. Everything else contract 4.1 stores -- including the derived raster
    views -- is part of the digest, so a change in any stored byte moves it.
    """
    content = {key: value for key, value in arrays.items() if key != "identity_sha256"}
    return identity(content, _product_metadata(content))


def product_set_identity(records, *, seed, config_id, spacing_m, requested_points):
    """Digest of the *set* of domain products, independent of input/refusal order.

    `records` must already be sorted by outlet coordinate (contract 4.2), so two
    runs of the same points in a different order produce the same digest while the
    per-domain products keep their own `identity_sha256`.
    """
    return identity({}, {
        "schema": SCHEMA,
        "seed": int(seed),
        "config_id": config_id,
        "spacing_m": float(spacing_m),
        "requested_points": int(requested_points),
        "domain_count": len(records),
        "domains": list(records),
    })


@dataclass(frozen=True)
class Refusal:
    """A requested point that produced no domain, with a verbatim reason.

    `reason` is one of `REASON_ORDER` (`ClosureRegion.classify`), and `resolved`
    is the closure module's own flag: False exactly for `unresolved_border` /
    `out_of_tile` (contract 3). A sea point is *resolved* -- the world is known
    there -- it simply has no domain.
    """

    x_m: float
    z_m: float
    reason: str
    resolved: bool

    def as_record(self):
        return {"x_m": float(self.x_m), "z_m": float(self.z_m),
                "reason": self.reason, "resolved": bool(self.resolved)}


@dataclass(frozen=True)
class DomainProduct:
    """One domain: outlet identity plus its territory and derived views.

    `cells_x_m` / `cells_z_m` are the authority (scattered world coordinates from
    `territory_of`); `territory_raster`, `base_height_m` and `ocean_mask` are
    resampled derived views on the tight bounding box. `identity_sha256` is the
    content digest of the whole product and is reproducible across processes.
    """

    outlet_x_m: float
    outlet_z_m: float
    kind: str
    area_m2: float
    cells_x_m: np.ndarray
    cells_z_m: np.ndarray
    bbox_origin_x_m: float
    bbox_origin_z_m: float
    spacing_m: float
    territory_raster: np.ndarray
    base_height_m: np.ndarray
    ocean_mask: np.ndarray
    seed: int
    config_id: str
    identity_sha256: str
    schema: str = SCHEMA
    limitations: tuple = LIMITATIONS
    product_name: str | None = None
    product_path: str | None = None
    source: str = "memory"

    @property
    def outlet_xz_m(self):
        return (float(self.outlet_x_m), float(self.outlet_z_m))

    @property
    def cell_count(self):
        return int(np.asarray(self.cells_x_m).size)

    @property
    def raster_shape(self):
        return tuple(int(size) for size in np.asarray(self.territory_raster).shape)

    def arrays(self):
        """The contract 4.1 npz payload, in contract order (digest included)."""
        return {
            "outlet_xz_m": np.asarray([self.outlet_x_m, self.outlet_z_m], np.float64),
            "kind": np.asarray(self.kind, dtype=np.str_),
            "cells_x_m": np.ascontiguousarray(self.cells_x_m, np.float64),
            "cells_z_m": np.ascontiguousarray(self.cells_z_m, np.float64),
            "area_m2": np.asarray(self.area_m2, np.float64),
            "bbox_origin_xz_m": np.asarray([self.bbox_origin_x_m, self.bbox_origin_z_m], np.float64),
            "spacing_m": np.asarray(self.spacing_m, np.float64),
            "territory_raster": np.ascontiguousarray(self.territory_raster, bool),
            "base_height_m": np.ascontiguousarray(self.base_height_m, np.float64),
            "ocean_mask": np.ascontiguousarray(self.ocean_mask, bool),
            "seed": np.asarray(self.seed, np.int64),
            "config_id": np.asarray(self.config_id, dtype=np.str_),
            "identity_sha256": np.asarray(self.identity_sha256, dtype=np.str_),
            "schema": np.asarray(self.schema, dtype=np.str_),
            "limitations": np.asarray(self.limitations, dtype=np.str_),
        }

    def index_record(self):
        """The domain's entry in the batch index (contract 4.2), plus extras."""
        record = {
            "outlet_x_m": float(self.outlet_x_m),
            "outlet_z_m": float(self.outlet_z_m),
            "product": self.product_name,
            "territory_cells": self.cell_count,
            "identity_sha256": self.identity_sha256,
            "kind": self.kind,
            "area_m2": float(self.area_m2),
            "raster_shape": [int(size) for size in self.raster_shape],
        }
        return record

    def identity_records(self):
        """Order-independent slice of `index_record` used for the set digest."""
        record = self.index_record()
        return {"outlet_x_m": record["outlet_x_m"], "outlet_z_m": record["outlet_z_m"],
                "product": record["product"], "territory_cells": record["territory_cells"],
                "identity_sha256": record["identity_sha256"]}


@dataclass(frozen=True)
class DomainProductBatch:
    """Result of one `resolve_domain_products` call.

    `domains` maps the **outlet world coordinate** (the domain identity) to its
    product and is ordered by that key; `refusals` keeps the caller's input order.
    `accepted_points` counts accepted *points* (so `accepted + refused ==
    requested` always holds), while `len(domains)` counts distinct domains --
    two points in one domain share one product by contract 2.1.
    """

    seed: int
    config_id: str
    spacing_m: float
    node_spacing_m: float
    domains: dict
    refusals: tuple
    requested_points: int
    accepted_points: int
    refused_points: int
    reason_tally: dict
    product_set_sha256: str
    schema: str = INDEX_SCHEMA
    limitations: tuple = LIMITATIONS
    output_dir: str | None = None
    index_path: str | None = None

    @property
    def outlet_keys(self):
        """The domain identities, sorted by outlet world coordinate."""
        return tuple(self.domains)

    @property
    def domain_count(self):
        return len(self.domains)

    def domain(self, outlet_x_m, outlet_z_m):
        """Product of one domain identity, or KeyError (never a nearest guess)."""
        key = (float(outlet_x_m), float(outlet_z_m))
        if key not in self.domains:
            raise KeyError("no product for outlet %s; known outlets: %s"
                           % (key, list(self.outlet_keys)))
        return self.domains[key]

    def refusal_records(self):
        return tuple(refusal.as_record() for refusal in self.refusals)

    def identity_records(self):
        return [self.domains[key].identity_records() for key in self.outlet_keys]

    def index_record(self):
        """The batch index of contract 4.2 (plus the fields this module pinned)."""
        return {
            "schema": INDEX_SCHEMA,
            "seed": int(self.seed),
            "config_id": self.config_id,
            "spacing_m": float(self.spacing_m),
            "node_spacing_m": float(self.node_spacing_m),
            "domains": [self.domains[key].index_record() for key in self.outlet_keys],
            "refusals": [refusal.as_record() for refusal in self.refusals],
            "requested_points": int(self.requested_points),
            "accepted_points": int(self.accepted_points),
            "refused_points": int(self.refused_points),
            "domain_count": int(self.domain_count),
            "reason_tally": dict(self.reason_tally),
            "product_set_sha256": self.product_set_sha256,
            "output_dir": self.output_dir,
            "index": self.index_path,
            "limitations": [str(line) for line in self.limitations],
            "identity_policy": IDENTITY_POLICY,
            "territory_raster_policy": TERRITORY_RASTER_POLICY,
        }


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------

def _point_arrays(points_xz_m):
    """Normalise `(x, z)` input to two float64 vectors, preserving input order.

    Accepts an `(N, 2)` array (or a single `(2,)` pair) and any iterable of
    two-element sequences -- a list of tuples is the documented form, and the
    scalar/array flexibility contract 2.1 asks for is a property of the closure
    module's own entry points, which this module never bypasses.
    """
    if points_xz_m is None:
        raise ValueError("points_xz_m is required")
    if isinstance(points_xz_m, np.ndarray):
        array = np.asarray(points_xz_m, np.float64)
        if array.ndim == 1 and array.size == 2:
            return array[:1].copy(), array[1:].copy()
        if array.ndim == 2 and array.shape[1] == 2:
            return np.ascontiguousarray(array[:, 0]), np.ascontiguousarray(array[:, 1])
        raise ValueError("points_xz_m array must be (2,) or (N, 2); got shape %s" % (array.shape,))
    xs, zs = [], []
    for position, point in enumerate(points_xz_m):
        try:
            x_m, z_m = point
        except (TypeError, ValueError):
            raise ValueError("points_xz_m[%d] is not an (x, z) pair: %r" % (position, point))
        x_value, z_value = float(x_m), float(z_m)
        if not (math.isfinite(x_value) and math.isfinite(z_value)):
            raise ValueError("points_xz_m[%d] is not finite: %r" % (position, point))
        xs.append(x_value)
        zs.append(z_value)
    return np.asarray(xs, np.float64), np.asarray(zs, np.float64)


def _tally(reasons):
    """Verbatim reason tally with a fixed slot per known reason (auditor style).

    Known reasons keep a zero slot so a zero is explicit, and an unknown label gets
    its own key instead of being dropped -- dropping it is exactly how a new
    refusal reason could hide.
    """
    tally = {name: 0 for name in REASON_ORDER}
    extra = {}
    for reason in reasons:
        name = str(reason)
        if name in tally:
            tally[name] += 1
        else:
            extra[name] = extra.get(name, 0) + 1
    for name in sorted(extra):
        tally[name] = extra[name]
    return tally


# ---------------------------------------------------------------------------
# Product construction (verbatim consumption of metric_domain_closure)
# ---------------------------------------------------------------------------

def _check_spacing(spacing_m, node_spacing, label="spacing_m"):
    """The resample lattice must CONTAIN the planning nodes, exactly.

    A territory is delivered as scattered planning-node coordinates, so every one
    of them has to land *on* a resample node, or `territory_raster` would be a
    picture of something that is not there. `spacing_m` must therefore be the node
    spacing divided by a positive integer: equal to it, or finer.

    A *coarser* lattice cannot hold the cells at all -- measured, not assumed: with
    `spacing_m = 2 x` node spacing the fixture domain's cell at z = 30000 m falls
    exactly halfway between two nodes, and rounding it would move a territory cell
    10 km while still looking like a plausible raster. Such a value is refused.
    """
    if not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("%s must be finite and positive; got %r" % (label, spacing_m))
    quotient = float(node_spacing) / float(spacing_m)
    if abs(quotient - round(quotient)) > 1e-9 or round(quotient) < 1:
        raise ValueError(
            "%s must divide the planning node spacing (%g m) by a positive integer, so "
            "that every territory cell lands exactly on a resample node; got %g m "
            "(node_spacing / spacing_m = %r)" % (label, node_spacing, spacing_m, quotient))
    return int(round(quotient))


def _raster_geometry(cells_x, cells_z, spacing_m, outlet_xz_m):
    """Tight bounding box of the scattered cells on the resample lattice.

    Returns ``(origin_x, origin_z, nz, nx, row_index, column_index)`` where the
    returned index arrays are already offsets into the raster: rows run along z and
    columns along x (the array order contract 4.1 publishes as `(nz, nx)`), so a
    caller can assign `raster[row_index, column_index] = True` directly.
    """
    if cells_x.size == 0:
        # A domain with no land cell in the owning core (a marine mouth whose
        # upstream lies outside the core) still gets a well-formed, explicitly
        # empty 1x1 view: the shape contract holds and nothing is invented.
        return float(outlet_xz_m[0]), float(outlet_xz_m[1]), 1, 1, \
            np.zeros(0, np.int64), np.zeros(0, np.int64)
    index_x = np.rint(cells_x / spacing_m).astype(np.int64)
    index_z = np.rint(cells_z / spacing_m).astype(np.int64)
    if not (np.allclose(index_x * spacing_m, cells_x, rtol=0.0, atol=1e-6)
            and np.allclose(index_z * spacing_m, cells_z, rtol=0.0, atol=1e-6)):
        raise ValueError(
            "territory cells are not on the resample lattice of spacing %g m; the "
            "scattered authority cannot be rasterised without inventing positions" % spacing_m)
    origin_x = float(index_x.min()) * spacing_m
    origin_z = float(index_z.min()) * spacing_m
    nx = int(index_x.max()) - int(index_x.min()) + 1
    nz = int(index_z.max()) - int(index_z.min()) + 1
    if nx * nz > MAX_RASTER_CELLS:
        raise ValueError(
            "derived raster budget exceeded: %d x %d > %d cells; the scattered cells "
            "remain available but this product refuses to materialise such a view"
            % (nz, nx, MAX_RASTER_CELLS))
    return (origin_x, origin_z, nz, nx,
            index_z - int(index_z.min()), index_x - int(index_x.min()))


def _domain_product(seed, config, config_id, spacing_m, node_spacing, outlet_x_m, outlet_z_m):
    """Build one domain product from `territory_of`'s own return body.

    Contract 4.0 is a hard requirement here: the returned dict *is* the data
    source. `outlet_xz_m` / `kind` / `cell_count` / `cells_*` / `area_m2` come
    from it verbatim; nothing is re-flooded and no steepest-D8 is recomputed.
    """
    requested = (float(outlet_x_m), float(outlet_z_m))
    territory = territory_of(seed, requested[0], requested[1], config)
    if territory is None:
        raise ValueError(
            "territory_of returned None for outlet %r, but the point was accepted: "
            "metric_domain_closure contradicts itself" % (requested,))
    returned = (float(territory["outlet_xz_m"][0]), float(territory["outlet_xz_m"][1]))
    for label, one, two in (("outlet x", returned[0], requested[0]),
                            ("outlet z", returned[1], requested[1])):
        if abs(one - two) > 1e-6 * node_spacing:
            raise ValueError(
                "eligible_owner_at said %r but territory_of says %r (%s differs by %g m): "
                "the two halves of the closure contract disagree"
                % (requested, returned, label, abs(one - two)))
    key, index_x = _quantise(returned[0], node_spacing, "outlet x")
    key_z, index_z = _quantise(returned[1], node_spacing, "outlet z")

    cells_x = np.ascontiguousarray(np.asarray(territory["cells_x_m"], np.float64).reshape(-1))
    cells_z = np.ascontiguousarray(np.asarray(territory["cells_z_m"], np.float64).reshape(-1))
    if cells_x.size != cells_z.size:
        raise ValueError("territory_of returned %d x cells but %d z cells"
                         % (cells_x.size, cells_z.size))
    cell_count = int(territory["cell_count"])
    if cell_count != cells_x.size:
        raise ValueError("territory_of cell_count %d != %d scattered cells"
                         % (cell_count, cells_x.size))
    area_m2 = float(territory["area_m2"])
    expected_area = cell_count * node_spacing ** 2
    if abs(area_m2 - expected_area) > 1e-6 * max(1.0, expected_area):
        raise ValueError("territory_of area_m2 %r is not %d cells x %g m^2"
                         % (area_m2, cell_count, node_spacing))

    origin_x, origin_z, nz, nx, row_index, column_index = _raster_geometry(
        cells_x, cells_z, spacing_m, returned)
    territory_raster = np.zeros((nz, nx), bool)
    if cell_count:
        territory_raster[row_index, column_index] = True
    if int(territory_raster.sum()) != cell_count:
        raise ValueError("rasterised territory holds %d cells, territory_of says %d"
                         % (int(territory_raster.sum()), cell_count))

    axis_x = origin_x + np.arange(nx) * spacing_m
    axis_z = origin_z + np.arange(nz) * spacing_m
    grid_x, grid_z = np.meshgrid(axis_x, axis_z)
    base_height, _, _ = coarse_condition_field(seed, grid_x, grid_z, config)
    base_height = np.ascontiguousarray(np.asarray(base_height, np.float64).reshape(nz, nx))
    ocean_mask = np.ascontiguousarray(
        np.asarray(global_ocean_mask(seed, grid_x, grid_z, config), bool).reshape(nz, nx))

    product = DomainProduct(
        outlet_x_m=key,
        outlet_z_m=key_z,
        kind=str(territory["kind"]),
        area_m2=area_m2,
        cells_x_m=cells_x,
        cells_z_m=cells_z,
        bbox_origin_x_m=origin_x,
        bbox_origin_z_m=origin_z,
        spacing_m=float(spacing_m),
        territory_raster=territory_raster,
        base_height_m=base_height,
        ocean_mask=ocean_mask,
        seed=int(seed),
        config_id=config_id,
        identity_sha256="",
        product_name=domain_product_name(key, key_z),
        source="memory",
    )
    return replace(product, identity_sha256=compute_identity(product.arrays()))


def _npz_bytes(arrays):
    """The product's container bytes: contract 4.1 keys, in contract order."""
    missing = [key for key in PRODUCT_KEYS if key not in arrays]
    if missing:
        raise ValueError("product is missing contract keys: %s" % missing)
    buffer = io.BytesIO()
    np.savez(buffer, **{key: arrays[key] for key in PRODUCT_KEYS})
    return buffer.getvalue()


def _json_bytes(record):
    return json.dumps(record, ensure_ascii=False, indent=2,
                      allow_nan=False, sort_keys=False).encode("utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def resolve_domain_products(seed, points_xz_m, *, config=None, spacing_m=None,
                            output_dir=None, cache=None):
    """Turn world coordinates into domain products, one per distinct outlet.

    Contract 2.1. `points_xz_m` is any iterable of `(x_m, z_m)` world coordinates
    (or an `(N, 2)` array). Every accepted point maps to the domain whose outlet
    world coordinate identifies it; points that hit the same domain share one
    product. Every non-accepted point becomes a `Refusal` carrying the verbatim
    `ClosureRegion.classify` reason and the closure module's `resolved` flag.

    `spacing_m` is the resample spacing of the derived views and defaults to the
    planning node spacing; it must divide that node spacing by a positive integer
    (see `_check_spacing`, and contract 8 in the report). `output_dir` given writes
    one `.npz` per domain plus the batch index JSON -- and refuses to overwrite an
    existing product or index. `output_dir=None` returns the same batch in memory.

    `cache` is accepted for signature parity with contract 2.1 and must be None:
    the only cache in this pipeline is `metric_domain_closure._CACHE`, which is
    looked after by `clear_cache()`. A caller-supplied cache would have to be part
    of the identity contract to be honest, and it is not.

    Raises ValueError for invalid input or a contract breach detected on the
    closure module's own return bodies (never silently absorbed), and
    FileExistsError when a destination already exists.
    """
    if cache is not None:
        raise ValueError(
            "cache is not supported: in-memory caching lives in "
            "metric_domain_closure (clear_cache()); a caller cache would change no "
            "identity and is therefore refused rather than silently ignored")
    config = config or PlanningConfig()
    config.validate()
    seed = int(seed)
    node_spacing = node_spacing_m(config)
    effective_spacing = node_spacing if spacing_m is None else float(spacing_m)
    _check_spacing(effective_spacing, node_spacing)
    config_id = config_identity(config)

    xs, zs = _point_arrays(points_xz_m)
    requested = int(xs.size)

    # Both answers come from the closure module verbatim; this module adds only
    # bookkeeping (contract 4.0: no second flood, no second steepest-D8).
    resolved = resolve_points(seed, xs, zs, config)
    reasons = [str(value) for value in np.asarray(resolved["reason"], object).reshape(-1)]
    resolved_flags = [bool(value) for value in np.asarray(resolved["resolved"], bool).reshape(-1)]
    if len(reasons) != requested or len(resolved_flags) != requested:
        raise ValueError("resolve_points returned %d answers for %d points"
                         % (len(reasons), requested))
    accepted, (outlet_x, outlet_z) = eligible_owner_at(seed, xs, zs, config)
    accepted = np.asarray(accepted, bool).reshape(-1)
    outlet_x = np.asarray(outlet_x, np.float64).reshape(-1)
    outlet_z = np.asarray(outlet_z, np.float64).reshape(-1)
    if accepted.size != requested:
        raise ValueError("eligible_owner_at returned %d answers for %d points"
                         % (accepted.size, requested))

    refusals = []
    domain_points = {}
    for position in range(requested):
        reason = reasons[position]
        flag = resolved_flags[position]
        if reason not in REASON_ORDER:
            raise ValueError(
                "unknown reason %r at point %d: the rejection vocabulary is "
                "ClosureRegion.classify's five labels, verbatim (contract 3)"
                % (reason, position))
        expected_flag = reason not in UNRESOLVED_REASONS
        if flag is not expected_flag:
            raise ValueError(
                "resolve_points says resolved=%s for reason %r (point %d); contract 3 "
                "requires resolved == (reason not in %s)"
                % (flag, reason, position, list(UNRESOLVED_REASONS)))
        if accepted[position]:
            if reason not in ACCEPTED_REASONS:
                raise ValueError(
                    "point %d (%r, %r) is accepted by eligible_owner_at yet classified %r"
                    % (position, float(xs[position]), float(zs[position]), reason))
            key_x, _ = _quantise(outlet_x[position], node_spacing, "owner outlet x")
            key_z, _ = _quantise(outlet_z[position], node_spacing, "owner outlet z")
            domain_points.setdefault((key_x, key_z), []).append(position)
        else:
            refusals.append(Refusal(float(xs[position]), float(zs[position]),
                                    reason, flag))

    domains = {}
    for key in sorted(domain_points):
        domains[key] = _domain_product(seed, config, config_id, effective_spacing,
                                       node_spacing, key[0], key[1])

    accepted_points = requested - len(refusals)
    records = [domains[key].identity_records() for key in domains]
    batch = DomainProductBatch(
        seed=seed,
        config_id=config_id,
        spacing_m=effective_spacing,
        node_spacing_m=node_spacing,
        domains=domains,
        refusals=tuple(refusals),
        requested_points=requested,
        accepted_points=accepted_points,
        refused_points=len(refusals),
        reason_tally=_tally(reasons),
        product_set_sha256=product_set_identity(
            records, seed=seed, config_id=config_id,
            spacing_m=effective_spacing, requested_points=requested),
    )

    if output_dir is None:
        return batch
    return _publish_batch(batch, output_dir)


def _publish_batch(batch, output_dir):
    """Write every product plus the index; refuse any existing destination.

    Every target is checked *before* anything is written, so a batch that would
    collide leaves the directory exactly as it was found (no half-published set),
    and each write itself commits through a hard link.
    """
    root = Path(output_dir)
    index_path = root / INDEX_NAME
    targets = [(index_path, None)]
    for key in batch.outlet_keys:
        product = batch.domains[key]
        targets.append((root / product.product_name, product))
    clashes = [str(path) for path, _ in targets if path.exists()]
    if clashes:
        raise FileExistsError(
            "refusing to overwrite existing product/index: %s (contract 5.1)" % clashes)
    root.mkdir(parents=True, exist_ok=True)
    written = {}
    for path, product in targets[1:]:
        publish_bytes(path, _npz_bytes(product.arrays()))
        written[product.outlet_xz_m] = replace(
            product, product_path=str(path), product_name=path.name, source="file")
    published = replace(batch, domains=written, output_dir=str(root),
                        index_path=str(index_path))
    publish_bytes(index_path, _json_bytes(published.index_record()))
    return published


# ---------------------------------------------------------------------------
# Reload (same identity, path is not content)
# ---------------------------------------------------------------------------

def load_domain_product(path, *, expected_identity_sha256=None):
    """Re-load one written product and re-derive its content digest.

    A load is an integrity check, not a blind read: the digest is recomputed from
    the stored arrays and metadata and must match the stored `identity_sha256`
    (and `expected_identity_sha256` when given). A mismatch raises instead of
    handing the caller a product whose identity cannot be trusted.
    """
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    missing = [key for key in PRODUCT_KEYS if key not in arrays]
    if missing:
        raise ValueError("%s is missing contract keys: %s" % (path, missing))
    extra = sorted(set(arrays) - set(PRODUCT_KEYS))
    if extra:
        raise ValueError("%s carries keys outside schema %s: %s" % (path, SCHEMA, extra))
    if _text(arrays["schema"]) != SCHEMA:
        raise ValueError("%s declares schema %r, not %r"
                         % (path, _text(arrays["schema"]), SCHEMA))
    stored = _text(arrays["identity_sha256"])
    computed = compute_identity(arrays)
    if computed != stored:
        raise ValueError("product identity mismatch in %s: stored %s, recomputed %s"
                         % (path, stored, computed))
    if expected_identity_sha256 is not None and stored != expected_identity_sha256:
        raise ValueError("product %s has identity %s, expected %s"
                         % (path, stored, expected_identity_sha256))
    outlet = np.asarray(arrays["outlet_xz_m"], np.float64).reshape(-1)
    bbox = np.asarray(arrays["bbox_origin_xz_m"], np.float64).reshape(-1)
    limitations = tuple(_text(value) for value in np.asarray(arrays["limitations"]).reshape(-1))
    return DomainProduct(
        outlet_x_m=float(outlet[0]),
        outlet_z_m=float(outlet[1]),
        kind=_text(arrays["kind"]),
        area_m2=float(np.asarray(arrays["area_m2"]).item()),
        cells_x_m=np.ascontiguousarray(np.asarray(arrays["cells_x_m"], np.float64).reshape(-1)),
        cells_z_m=np.ascontiguousarray(np.asarray(arrays["cells_z_m"], np.float64).reshape(-1)),
        bbox_origin_x_m=float(bbox[0]),
        bbox_origin_z_m=float(bbox[1]),
        spacing_m=float(np.asarray(arrays["spacing_m"]).item()),
        territory_raster=np.ascontiguousarray(np.asarray(arrays["territory_raster"], bool)),
        base_height_m=np.ascontiguousarray(np.asarray(arrays["base_height_m"], np.float64)),
        ocean_mask=np.ascontiguousarray(np.asarray(arrays["ocean_mask"], bool)),
        seed=int(np.asarray(arrays["seed"]).item()),
        config_id=_text(arrays["config_id"]),
        identity_sha256=stored,
        schema=_text(arrays["schema"]),
        limitations=limitations,
        product_name=Path(path).name,
        product_path=str(path),
        source="file",
    )
