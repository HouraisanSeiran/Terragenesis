"""Native 30 m source windows and deterministic strict irregular topology.

Original TD elevations remain cell representatives. Graph positions use absolute
native indices and the fixed world seed. Unknown support is declared before
accumulation, and no finite-window terminal is certified as a natural outlet.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import re
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import MAX_METADATA, checked_archive, file_sha256
from terrain_pipeline.surface_rivers import metric_cross_region
from terrain_pipeline.surface_rivers.metric_network_discharge_product import (
    TERMINAL_KIND_DTYPE,
    TERMINAL_LABELS,
)

__all__ = [
    "BORDER_BAND_CELLS",
    "DEFAULT_MAX_CELLS",
    "DEFAULT_WORLD_SEED",
    "MAX_METADATA_BYTES",
    "MAX_PAGES",
    "MAX_PAGE_BYTES",
    "MAX_PAGE_SIDE",
    "MAX_TOTAL_PAGE_CELLS",
    "MAX_TOPOLOGY_CELLS",
    "NATIVE_SPACING_M",
    "PAGE_SCHEMA",
    "REASON_BUDGET",
    "REASON_DUPLICATE_PAGE",
    "REASON_PAGE_INVALID",
    "REASON_PAGE_MISSING",
    "REASON_PIN_MISMATCH",
    "REASON_PIN_MISSING",
    "REASON_SEED_MISMATCH",
    "REASON_SHAPE_MISMATCH",
    "REASON_SPACING_MISMATCH",
    "REASON_WINDOW_NOT_COVERED",
    "REQUIRED_PAGE_ARRAYS",
    "TERMINAL_KIND_DTYPE",
    "TERMINAL_LABELS",
    "build_strict_topology",
    "load_native_window",
]

# --------------------------------------------------------------------------- #
# declared budgets and vocabulary
# --------------------------------------------------------------------------- #
#: 30 m is the Terrain Diffusion native resolution; it is confirmed against every
#: page's metadata and is never a scale knob.
NATIVE_SPACING_M = 30.0

#: The continuous test baseline (``CONTRIBUTING.md``): fixed, never re-chosen.
DEFAULT_WORLD_SEED = 20261020

#: 1337² = 40.08 km, the declared M1 window (see ``.scratch/river-stage1-completion``).
DEFAULT_MAX_CELLS = 1_787_569

#: Declared page-side and archive ceilings; a page is refused, never downsampled.
MAX_PAGE_SIDE = 4096
MAX_PAGE_BYTES = 512 * 1024 * 1024

#: The ``U`` itemsize budget of ``metadata_json`` (see the module docstring).
MAX_METADATA_BYTES = MAX_METADATA

MAX_PAGES = 64

#: Total elevation cells held across all pinned pages at once. A page count alone is
#: not a memory budget: 64 pages of 4096² float64 would be 8.6 GB. The real M1 page
#: set is four 2049² pages = 16.8 M cells, so this ceiling is generous and still
#: refuses a request that could not fit. Refused, never dropped to a subset.
MAX_TOTAL_PAGE_CELLS = 32 * 1024 * 1024

#: The cell ceiling of ``build_strict_topology``. It is a public entry point, so it
#: carries its own guard instead of relying on a caller having gone through
#: ``load_native_window``: the irregular graph kernel and the three full-extent output arrays are
#: allocated before any other check could fire. Equal to the declared M1 window
#: (1337² = 1 787 569) with the same 16 777 216-cell ceiling the network accumulator
#: uses, so a legal window is never refused here for being legal.
MAX_TOPOLOGY_CELLS = 16_777_216

PAGE_SCHEMA = "td-native-page-v1"
REQUIRED_PAGE_ARRAYS = ("elevation_native", "metadata_json")
REQUIRED_METADATA_KEYS = ("native_origin", "size", "spacing_m", "world_seed")

#: The assembly kernel's own refusal band; not a copy, the single authority.
BORDER_BAND_CELLS = metric_cross_region.BORDER_BAND_CELLS

# Stable refusal reasons. They are part of the message, so a caller can classify a
# refusal without matching prose.
REASON_PIN_MISSING = "pin_missing"
REASON_PIN_MISMATCH = "pin_mismatch"
REASON_PAGE_MISSING = "page_source_missing"
REASON_PAGE_INVALID = "invalid_td_page"
REASON_SEED_MISMATCH = "seed_mismatch"
REASON_SPACING_MISMATCH = "spacing_mismatch"
REASON_SHAPE_MISMATCH = "shape_mismatch"
REASON_DUPLICATE_PAGE = "duplicate_page_key"
REASON_WINDOW_NOT_COVERED = "window_not_covered"
REASON_BUDGET = "budget_exceeded"

_PIN_PATTERN = re.compile(r"[0-9a-f]{64}")
_PAGE_RECORD_KEYS = {"path", "sha256"}

# The terminal labels this module is willing to emit. ``open_outflow`` is
# deliberately absent: no finite assembled window certifies a natural outlet.
_EMITTABLE_TERMINALS = ("inactive", "interior", "retained", "unknown_boundary")


#: Height substituted for a cell the pages could not answer, before the irregular graph kernel
#: runs. ``+inf`` makes every slope towards such a cell ``-inf`` (never the
#: steepest) and every slope *from* it ``+inf``, so an unresolved cell can never
#: become a receiver target; its own receiver is then forced to ``-1``.
_UNCOMPUTABLE_HEIGHT = np.inf

_SOURCE_SHA_CACHE = {}


# --------------------------------------------------------------------------- #
# scalar validation
# --------------------------------------------------------------------------- #
def _strict_int(value, name):
    """Reject bools, floats and strings: an index is an integer, not a coin flip."""
    if isinstance(value, bool) or isinstance(value, np.bool_):
        raise ValueError("%s must be an integer, not a boolean" % name)
    if isinstance(value, (int, np.integer)):
        return int(value)
    raise ValueError("%s must be an integer, got %s" % (name, type(value).__name__))


def _integer_pair(values, name):
    if isinstance(values, np.ndarray):
        if values.shape != (2,):
            raise ValueError("%s must carry exactly two integers" % name)
        items = values.tolist()
    elif isinstance(values, (list, tuple)) and len(values) == 2:
        items = list(values)
    else:
        raise ValueError("%s must be a two-element sequence of integers" % name)
    return [_strict_int(item, name) for item in items]


def _window_shape(shape_zx):
    rows, columns = _integer_pair(shape_zx, "shape_zx")
    if rows < 2 or columns < 2:
        raise ValueError("%s: at least 2x2 cells required, got %dx%d"
                         % (REASON_SHAPE_MISMATCH, rows, columns))
    return rows, columns


def _seed_value(world_seed):
    """A positive integer world seed, or a refusal carrying the stable reason."""
    try:
        seed = _strict_int(world_seed, "world_seed")
    except ValueError as error:
        raise ValueError("%s: %s" % (REASON_SEED_MISMATCH, error)) from None
    if seed <= 0:
        raise ValueError("%s: world_seed must be positive, got %d"
                         % (REASON_SEED_MISMATCH, seed))
    return seed


# --------------------------------------------------------------------------- #
# 1. page records and pinned reading
# --------------------------------------------------------------------------- #
def _page_records(records):
    """Validate the ``[{path, sha256}]`` contract before touching any file."""
    if isinstance(records, (str, bytes)) or not isinstance(records, (list, tuple)):
        raise ValueError("page_records must be a list of {path, sha256} records")
    if not records:
        raise ValueError("at least one pinned page is required")
    if len(records) > MAX_PAGES:
        raise ValueError("%s: %d pages exceeds the declared budget of %d"
                         % (REASON_BUDGET, len(records), MAX_PAGES))
    checked = []
    seen = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError("page record %d must be a dict" % index)
        if "sha256" not in record:
            raise ValueError("%s: page record %d carries no sha256; every page must be "
                             "pinned to a source hash" % (REASON_PIN_MISSING, index))
        if set(record) != _PAGE_RECORD_KEYS:
            raise ValueError("page record %d must carry exactly path and sha256, got %s"
                             % (index, sorted(record)))
        path = record["path"]
        digest = record["sha256"]
        if not isinstance(path, str) or not path:
            raise ValueError("page record %d needs a non-empty path string" % index)
        if not isinstance(digest, str) or _PIN_PATTERN.fullmatch(digest) is None:
            raise ValueError("%s: page record %d needs a lowercase 64-character sha256, got %r"
                             % (REASON_PIN_MISSING, index, digest))
        if path in seen:
            raise ValueError("%s: %s appears twice; one page cannot be pinned twice"
                             % (REASON_DUPLICATE_PAGE, path))
        seen.add(path)
        checked.append({"path": path, "sha256": digest})
    return checked


def _page_headers(headers):
    """Header gate handed to ``checked_archive``: shape/dtype/budget, before loading.

    Nothing here reads a single elevation value, so an archive that cannot be a
    native page is refused without allocating its payload. Member names are exact:
    a page carrying a routed-Q or reach array is a *result* file, not a source
    page, and must not be read as terrain.
    """
    names = set(headers)
    if names != set(REQUIRED_PAGE_ARRAYS):
        raise ValueError("%s: a native 30 m page carries exactly %s, got %s "
                         "(historical Q/reach results are not a page)"
                         % (REASON_PAGE_INVALID, list(REQUIRED_PAGE_ARRAYS), sorted(names)))
    shape, dtype = headers["elevation_native"]
    if dtype != np.dtype(np.float64):
        raise ValueError("%s: elevation_native must be float64, got %s"
                         % (REASON_PAGE_INVALID, dtype))
    if len(shape) != 2:
        raise ValueError("%s: elevation_native must be 2D, got shape %s"
                         % (REASON_PAGE_INVALID, list(shape)))
    rows, columns = shape
    if rows != columns:
        raise ValueError("%s: a native page is square, got %dx%d"
                         % (REASON_SHAPE_MISMATCH, rows, columns))
    if not 2 <= rows <= MAX_PAGE_SIDE:
        raise ValueError("%s: page side %d outside [2, %d]"
                         % (REASON_BUDGET, rows, MAX_PAGE_SIDE))
    meta_shape, meta_dtype = headers["metadata_json"]
    if meta_shape != () or meta_dtype.kind != "U":
        raise ValueError("%s: metadata_json must be a 0-d unicode scalar, got shape %s dtype %s"
                         % (REASON_PAGE_INVALID, list(meta_shape), meta_dtype))
    if meta_dtype.itemsize > MAX_METADATA_BYTES:
        raise ValueError("%s: metadata_json needs %d bytes, budget is %d"
                         % (REASON_BUDGET, meta_dtype.itemsize, MAX_METADATA_BYTES))


def _page_metadata(raw):
    """Parse and validate ``metadata_json`` against the real page format."""
    if not isinstance(raw, np.ndarray) or raw.shape != () or raw.dtype.kind != "U":
        raise ValueError("%s: metadata_json must be a 0-d unicode scalar"
                         % REASON_PAGE_INVALID)
    try:
        record = json.loads(str(raw.item()))
    except ValueError as error:
        raise ValueError("%s: metadata_json is not JSON (%s)"
                         % (REASON_PAGE_INVALID, error)) from None
    if not isinstance(record, dict) or not record:
        raise ValueError("%s: metadata_json must hold a JSON object" % REASON_PAGE_INVALID)
    schema = record.get("schema")
    if schema is not None and schema != PAGE_SCHEMA:
        raise ValueError("%s: schema %r is not %r"
                         % (REASON_PAGE_INVALID, schema, PAGE_SCHEMA))
    missing = [key for key in REQUIRED_METADATA_KEYS if key not in record]
    if missing:
        raise ValueError("%s: metadata_json is missing %s"
                         % (REASON_PAGE_INVALID, missing))
    declared = record["native_origin"]
    if not isinstance(declared, (list, tuple)) or len(declared) != 2:
        raise ValueError("%s: native_origin must be a two-element [x, z] pair"
                         % REASON_PAGE_INVALID)
    origin = []
    for value in declared:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("%s: native_origin entries must be numbers, got %r"
                             % (REASON_PAGE_INVALID, value))
        if not math.isfinite(float(value)) or float(value) != float(int(round(float(value)))):
            raise ValueError("%s: native_origin entry %r is not on the native lattice"
                             % (REASON_PAGE_INVALID, value))
        origin.append(int(round(float(value))))
    return record, origin


def _read_page(record, *, seed):
    """One pinned archive → ``(elevation, metadata, native_origin)`` or a refusal."""
    path = Path(record["path"])
    if not path.is_file():
        raise ValueError("%s: %s" % (REASON_PAGE_MISSING, path))
    # Checked here rather than by matching `checked_archive`'s message, so a
    # substituted file and a malformed archive get different, stable reasons.
    actual = file_sha256(path)
    if actual != record["sha256"]:
        raise ValueError("%s: %s hashes to %s, the pin says %s"
                         % (REASON_PIN_MISMATCH, path, actual, record["sha256"]))
    try:
        arrays = checked_archive(path, expected_sha256=record["sha256"],
                                 max_bytes=MAX_PAGE_BYTES,
                                 header_validator=_page_headers)
    except ValueError as error:
        raise ValueError("%s: %s (%s)" % (REASON_PAGE_INVALID, path, error)) from None
    except Exception as error:  # a non-ZIP file, a truncated member, a bad CRC
        raise ValueError("%s: %s (%s: %s)"
                         % (REASON_PAGE_INVALID, path, type(error).__name__, error)) from None

    if set(arrays) != set(REQUIRED_PAGE_ARRAYS):
        raise ValueError("%s: %s did not yield exactly %s after reading"
                         % (REASON_PAGE_INVALID, path, list(REQUIRED_PAGE_ARRAYS)))
    elevation = np.ascontiguousarray(arrays["elevation_native"], np.float64)
    if elevation.dtype != np.float64 or elevation.ndim != 2:
        raise ValueError("%s: %s elevation_native is not a 2D float64 array"
                         % (REASON_PAGE_INVALID, path))
    if not np.isfinite(elevation).all():
        raise ValueError("%s: %s carries a non-finite elevation"
                         % (REASON_PAGE_INVALID, path))

    metadata, origin = _page_metadata(arrays["metadata_json"])

    rows, columns = elevation.shape
    if rows != columns:
        raise ValueError("%s: %s window is %dx%d, a native page is square"
                         % (REASON_SHAPE_MISMATCH, path, rows, columns))
    size = _declared_size(metadata, path)
    if size != rows:
        raise ValueError("%s: %s metadata size %d disagrees with elevation shape %s"
                         % (REASON_SHAPE_MISMATCH, path, size, list(elevation.shape)))

    spacing = metadata["spacing_m"]
    if (isinstance(spacing, bool) or not isinstance(spacing, (int, float))
            or float(spacing) != NATIVE_SPACING_M):
        raise ValueError("%s: %s declares spacing_m=%r, this world is %.1f m"
                         % (REASON_SPACING_MISMATCH, path, spacing, NATIVE_SPACING_M))

    declared_seed = metadata["world_seed"]
    if isinstance(declared_seed, bool) or not isinstance(declared_seed, int):
        raise ValueError("%s: %s declares a non-integer world_seed %r"
                         % (REASON_SEED_MISMATCH, path, declared_seed))
    if declared_seed != seed:
        raise ValueError("%s: %s was generated with world_seed=%d, %d was requested"
                         % (REASON_SEED_MISMATCH, path, declared_seed, seed))
    return elevation, metadata, origin


def _declared_size(metadata, path):
    size = metadata["size"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 2:
        raise ValueError("%s: %s declares an invalid size %r"
                         % (REASON_SHAPE_MISMATCH, path, size))
    return size


# --------------------------------------------------------------------------- #
# 2. the assembled window
# --------------------------------------------------------------------------- #
def load_native_window(page_records, *, origin_native_xz, shape_zx,
                       world_seed=DEFAULT_WORLD_SEED, max_cells=DEFAULT_MAX_CELLS):
    """One assembled 30 m window from pinned TD pages, unresolved cells preserved.

    ``page_records`` is ``[{"path": str, "sha256": str}]``: **every** page needs a
    pin, both members are required and no other member is accepted — there is no
    "trust this one" flag and no optional-role field, so a caller cannot smuggle an
    unpinned or role-relabelled page past the check. The order of the list does not
    matter: pages are addressed by path-sorted labels, so permuting the list cannot
    change a value or the digest.

    ``origin_native_xz`` is a **signed** native ``[x, z]`` pair (both entries may be
    negative), ``shape_zx`` is ``[rows, columns]``. Cells the pinned pages cannot
    answer stay unresolved (NaN in ``field``, ``False`` in ``resolved_mask``); this
    function never fills a hole and never treats the window edge as an outlet.
    A window no page covers at all is refused outright rather than returned empty.

    Returns ``field``, ``resolved_mask``, ``origin_native_xz``, ``shape_zx``,
    ``world_seed``, ``spacing_m``, ``source_records`` (path-sorted, with SHA256 and
    native origin) and ``assembly_digest`` (which includes *which* page supplied
    each cell).
    """
    seed = _seed_value(world_seed)
    budget = _strict_int(max_cells, "max_cells")
    if budget <= 0:
        raise ValueError("%s: max_cells must be positive, got %d"
                         % (REASON_BUDGET, budget))
    origin = _integer_pair(origin_native_xz, "origin_native_xz")
    rows, columns = _window_shape(shape_zx)
    if rows * columns > budget:
        raise ValueError("%s: window %dx%d = %d cells exceeds max_cells=%d"
                         % (REASON_BUDGET, rows, columns, rows * columns, budget))

    records = _page_records(page_records)
    ordered = sorted(records, key=lambda item: item["path"])
    pages = []
    source_records = []
    held_cells = 0
    for index, record in enumerate(ordered):
        elevation, metadata, native_origin = _read_page(record, seed=seed)
        held_cells += int(elevation.size)
        if held_cells > MAX_TOTAL_PAGE_CELLS:
            raise ValueError("%s: the pinned pages hold more than %d elevation cells at "
                             "once after reading %s; pages are refused, never dropped "
                             "to a subset"
                             % (REASON_BUDGET, MAX_TOTAL_PAGE_CELLS, record["path"]))
        # Short, path-sorted label: `assemble_pages` holds these in a U32 array and
        # a truncated path could turn two pages into an order-dependent tie.
        key = "p%02d" % index
        pages.append({"key": key, "page": elevation, "native_origin": native_origin})
        source_records.append({
            "page_key": key,
            "path": record["path"],
            "sha256": record["sha256"],
            "native_origin_xz": list(native_origin),
            "shape_zx": list(elevation.shape),
            "schema": metadata.get("schema"),
            "world_seed": int(metadata["world_seed"]),
            "spacing_m": float(metadata["spacing_m"]),
        })

    assembly = metric_cross_region.assemble_pages(
        pages, border_band_cells=BORDER_BAND_CELLS,
        origin=(origin[0], origin[1]), shape=(rows, columns))

    if assembly["resolved_cells"] == 0:
        raise ValueError("%s: no pinned page answers any cell of the window "
                         "origin=%s shape=%s; nothing is filled in or extrapolated"
                         % (REASON_WINDOW_NOT_COVERED, list(origin), [rows, columns]))

    field = np.ascontiguousarray(assembly["field"], np.float64)
    resolved = np.ascontiguousarray(assembly["resolved_mask"], bool)
    return {
        "field": field,
        "resolved_mask": resolved,
        "origin_native_xz": [origin[0], origin[1]],
        "shape_zx": [rows, columns],
        "world_seed": seed,
        "spacing_m": NATIVE_SPACING_M,
        "source_records": source_records,
        "assembly_digest": metric_cross_region.assembly_digest(assembly),
        "border_band_cells": int(assembly["border_band_cells"]),
        "resolved_cells": int(assembly["resolved_cells"]),
        "unresolved_cells": int(assembly["unresolved_cells"]),
        "unresolved_reason": assembly["unresolved_reason"],
        "selection_rule": assembly["selection_rule"],
        "source_code_sha256": {
            "terrain_pipeline.surface_rivers.metric_cross_region":
                _module_source_sha256("terrain_pipeline.surface_rivers.metric_cross_region"),
        },
        "policy": {
            "reading": ("pinned archives only: every page carries a lowercase 64-character "
                        "sha256, the hash is recomputed before use, the ZIP/NPY headers are "
                        "gated before any array is allocated, and np.load runs with "
                        "allow_pickle=False inside checked_archive"),
            "page_arrays": list(REQUIRED_PAGE_ARRAYS),
            "unresolved": ("cells no page answers inside the border band stay unresolved; "
                           "they are never filled, never extrapolated, and are not an outlet"),
            "window_edge": "a window edge is never an outlet (metric_cross_region constraint)",
            "assembly": "metric_cross_region.assemble_pages with border_band_cells=%d"
                        % BORDER_BAND_CELLS,
            "page_key": ("short positional label assigned in path-sorted order, so permuting "
                         "page_records cannot change a key, a value or the digest"),
            "spacing_m": "30.0 confirmed on every page; never taken from a planning config",
        },
    }


# --------------------------------------------------------------------------- #
# 3. strict irregular-graph joint topology
# --------------------------------------------------------------------------- #
def _module_source_sha256(name):
    if name not in _SOURCE_SHA_CACHE:
        module = importlib.import_module(name)
        path = getattr(module, "__file__", None)
        _SOURCE_SHA_CACHE[name] = (
            hashlib.sha256(Path(path).read_bytes()).hexdigest()
            if path and Path(path).is_file() else None)
    return _SOURCE_SHA_CACHE[name]


def build_strict_topology(field, resolved_mask, *, origin_native_xz=(0, 0),
                          spacing_m=30., world_seed=20261020, mesh=None):
    """Strict raw-bed graph routing with local unsupported-neighbour seeds."""
    bed = np.asarray(field, np.float64)
    if bed.ndim != 2 or min(bed.shape) < 2:
        raise ValueError("a 2D window of at least 2x2 cells is required, got shape %s"
                         % (list(bed.shape),))
    mask = np.asarray(resolved_mask)
    if mask.dtype != np.bool_ or mask.shape != bed.shape:
        raise ValueError("a boolean resolved_mask of the field's shape is required")
    if not mask.any():
        raise ValueError("no resolved cells: an all-unknown window has no topology")
    if bed.size > MAX_TOPOLOGY_CELLS:
        raise ValueError("%s: %d cells exceeds the declared topology budget of %d "
                         "(this entry point is public, so it carries its own guard)"
                         % (REASON_BUDGET, bed.size, MAX_TOPOLOGY_CELLS))
    if not np.isfinite(bed[mask]).all():
        raise ValueError("resolved cells must carry finite elevation; unresolved values "
                         "are ignored, so a non-finite *resolved* value is a broken input")

    rows, columns = bed.shape
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import masked_mesh as masked_mesh
    from terrain_pipeline.drainage import strict_receivers as strict_receivers
    if mesh is not None:
        origin_native_xz = mesh.origin_native_xz
        spacing_m = mesh.spacing_m
        world_seed = mesh.world_seed
    x0, z0 = (float(v) * spacing_m for v in origin_native_xz)
    mesh = grid_mesh(bed.shape, x0_m=x0, z0_m=z0, dx_m=spacing_m,
                     world_seed=world_seed) if mesh is None else mesh
    routing_mesh = masked_mesh(mesh, mask)
    computed, _, _ = strict_receivers(bed, routing_mesh, valid_mask=mask)
    receiver = computed.reshape(bed.shape)
    from terrain_pipeline.drainage import graph_support_unknown as graph_support_unknown
    complete = mask & ~graph_support_unknown(mask, x0_m=x0, z0_m=z0,
        dx_m=spacing_m, world_seed=world_seed)

    # Seeds exactly: a resolved cell that lost at least one neighbour to the window
    # cut. Not propagated here (rule 3).
    seeds = mask & ~complete

    kinds = np.full(bed.shape, "inactive", dtype=TERMINAL_KIND_DTYPE)
    kinds[mask & (receiver >= 0)] = "interior"
    terminal = mask & (receiver < 0)
    kinds[terminal & complete] = "retained"
    kinds[terminal & ~complete] = "unknown_boundary"

    census = {label: int((kinds == label).sum()) for label in TERMINAL_LABELS}
    return {
        "receiver": receiver,
        "node_x_m": mesh.node_x_m.reshape(bed.shape),
        "node_z_m": mesh.node_z_m.reshape(bed.shape),
        "mesh": routing_mesh,
        "valid_mask": mask.copy(),
        "terminal_kind": kinds,
        "upstream_unknown_mask": seeds,
        "shape_zx": [rows, columns],
        "census": census,
        "upstream_unknown_seed_cells": int(seeds.sum()),
        "topology_policy": _topology_policy(),
        "dependency_source_sha256": {
            'terrain_pipeline.drainage':
                _module_source_sha256('terrain_pipeline.drainage'),
            "terrain_pipeline.surface_rivers.metric_network_discharge_product":
                _module_source_sha256(
                    "terrain_pipeline.surface_rivers.metric_network_discharge_product"),
        },
    }


def _topology_policy():
    return {
        "algorithm": "strict_downhill_irregular_graph_v2",
        "implementation": 'terrain_pipeline.drainage.strict_receivers',
        "receiver": "rowmajor native control-cell id; -1 at terminals and invalid cells",
        "representative_position": "absolute native indices plus deterministic centered subcell displacement; original TD cell elevation retained",
        "unresolved": "masked graph edges cannot cross unknown cells or unknown corner contacts",
        "validity": "resolved_mask is preserved without upgrading unknown cells",
        "upstream_unknown_seed": "any full bounded-radius graph neighbour or crossing control cell outside resolved support",
        "upstream_unknown_mask": "local seeds only; downstream propagation belongs to accumulate_network_discharge",
        "terminal_kind": str(list(_EMITTABLE_TERMINALS)) + "; open_outflow is never emitted",
        "retained": "interior raw-bed sink; not a natural lake or certified outlet",
        "unknown_boundary": "unresolved downstream continuation; never repaired into an outlet",
        "natural_outlet": "not inferred by a finite source window",
        "repair": "strict receiver is unchanged after routing",
    }
