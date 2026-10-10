"""Pinned pyflwdir graph analysis and explicitly separate DEM routing experiments."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import importlib
import math
from pathlib import Path
from types import MappingProxyType

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, readonly
from .metric_contracts import MAX_CELLS, BoundaryGrid, RoutingGraph, TerrainGrid

SCHEMA = "terragenesis-reference-routing-v1"
BACKEND_VERSION = "0.5.12"
ARRAY_NAMES = ("receiver", "order_downstream_first", "valid_mask", "upstream_area_m2",
               "basin_id", "stream_order", "outlet_kind")
CAPABILITIES = ("hydraulic_ready", "natural_outlet_verified", "publishable")
TERMINALS = ("open_outflow", "prescribed_stage", "prescribed_discharge", "unknown_boundary",
             "lake_preserved", "reference_edge_exit", "reference_pit")
D8_CODES = np.array([[32, 64, 128], [16, 0, 1], [8, 4, 2]], dtype=np.uint8)


class OptionalDependencyError(ImportError):
    pass


class ReferenceBoundaryUnsupported(ValueError):
    pass


def _number(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(name + " must be numeric")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(name + " must be finite") from error
    if not math.isfinite(result):
        raise ValueError(name + " must be finite")
    return result


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("lowercase SHA256 identity required")


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class ReferenceRoutingConfig:
    backend: str = "pyflwdir"
    max_depth: float = -1.0
    outlets: str = "edge"
    nodata: float = -9999.0

    def __post_init__(self):
        if self.backend != "pyflwdir" or self.outlets not in ("edge", "min"):
            raise ValueError("pyflwdir with edge or min outlets required")
        depth = _number(self.max_depth, "max_depth")
        if depth != -1.0 and depth <= 0.0:
            raise ValueError("max_depth must be -1 or positive; zero-depth routing is unsupported")
        object.__setattr__(self, "max_depth", depth)
        object.__setattr__(self, "nodata", _number(self.nodata, "nodata"))


def _check_arrays(arrays, cell_area_m2):
    valid = arrays["valid_mask"]
    if (not isinstance(valid, np.ndarray) or valid.dtype != np.bool_ or valid.ndim != 2
            or not 1 < valid.size <= MAX_CELLS or not valid.any()):
        raise ValueError("bounded nonempty boolean grid mask required")
    mask = valid.ravel()
    size = valid.size
    for name in ("receiver", "basin_id", "stream_order", "upstream_area_m2"):
        dtype = np.dtype(np.float64 if name == "upstream_area_m2" else np.int64)
        value = arrays[name]
        if not isinstance(value, np.ndarray) or value.dtype != dtype or value.shape != (size,):
            raise ValueError(name + " must be " + dtype.name + " [N]")
        if not np.isfinite(value).all():
            raise ValueError(name + " must be finite")
    order = arrays["order_downstream_first"]
    if (not isinstance(order, np.ndarray) or order.dtype != np.int64 or order.ndim != 1
            or not np.array_equal(np.sort(order), np.flatnonzero(mask))):
        raise ValueError("downstream order must contain each valid cell exactly once")
    receiver = arrays["receiver"]
    if np.any(receiver < -1) or np.any(receiver >= size) or np.any(receiver[~mask] != -1):
        raise ValueError("reference receiver outside valid domain")
    donors = np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    if np.any(~mask[targets]):
        raise ValueError("reference receiver crosses nodata")
    columns = valid.shape[1]
    row_delta = targets // columns - donors // columns
    col_delta = targets % columns - donors % columns
    if np.any(np.maximum(abs(row_delta), abs(col_delta)) != 1):
        raise ValueError("reference receiver is not a D8 neighbour")
    diagonal = (row_delta != 0) & (col_delta != 0)
    if (np.any(~mask[donors[diagonal] + col_delta[diagonal]])
            or np.any(~mask[donors[diagonal] + row_delta[diagonal] * columns])):
        raise ValueError("reference receiver crosses unknown corner")
    rank = np.full(size, -1, dtype=np.int64)
    rank[order] = np.arange(order.size)
    if np.any(rank[targets] >= rank[donors]):
        raise ValueError("reference graph is cyclic or downstream order is invalid")
    kinds = arrays["outlet_kind"]
    terminal = mask & (receiver == -1)
    if (not isinstance(kinds, np.ndarray) or kinds.shape != (size,) or kinds.dtype.kind != "U"
            or not np.isin(kinds[terminal], TERMINALS).all()
            or np.any(kinds[donors] != "interior") or np.any(kinds[~mask] != "inactive")):
        raise ValueError("reference terminal kinds differ from topology")
    area = arrays["upstream_area_m2"]
    if np.any(area[~mask] != 0.) or np.any(area[mask] < cell_area_m2):
        raise ValueError("reference contributing area or nodata area invalid")
    expected = mask * cell_area_m2 + np.bincount(targets, weights=area[donors], minlength=size)
    if not np.allclose(area, expected, rtol=1e-10, atol=1e-8):
        raise ValueError("reference upstream area does not close at every node")
    if not math.isclose(float(area[terminal].sum()), int(mask.sum()) * cell_area_m2,
                        rel_tol=1e-10, abs_tol=1e-8):
        raise ValueError("reference terminal areas do not cover the domain")
    basins = arrays["basin_id"]
    if (np.any(basins[~mask] != -1) or np.any(basins[mask] < 0) or np.any(basins[mask] >= size)
            or not np.array_equal(basins[terminal], np.flatnonzero(terminal))
            or np.any(basins[donors] != basins[targets])):
        raise ValueError("basin_id must be the downstream terminal cell ID")
    streams = arrays["stream_order"]
    if np.any(streams[~mask] != 0) or np.any(streams[mask] < 1):
        raise ValueError("invalid Strahler stream order")
    maximum = np.zeros(size, dtype=np.int64)
    np.maximum.at(maximum, targets, streams[donors])
    tied = targets[streams[donors] == maximum[targets]]
    multiplicity = np.bincount(tied, minlength=size)
    expected_order = np.maximum(maximum, 1) + (multiplicity >= 2)
    if np.any(streams[mask] != expected_order[mask]):
        raise ValueError("reference Strahler order disagrees with donor branches")


@dataclass(frozen=True)
class ReferenceRoutingResult:
    backend: str
    version: str
    config: ReferenceRoutingConfig
    receiver: np.ndarray
    order_downstream_first: np.ndarray
    upstream_area_m2: np.ndarray
    basin_id: np.ndarray
    stream_order: np.ndarray
    terrain_identity: str
    boundary_identity: str
    valid_mask: np.ndarray
    cell_area_m2: float
    outlet_kind: np.ndarray
    metadata: Mapping

    def __post_init__(self):
        if self.backend != "pyflwdir" or self.version != BACKEND_VERSION:
            raise ValueError("reference backend must be pyflwdir==" + BACKEND_VERSION)
        if not isinstance(self.config, ReferenceRoutingConfig):
            raise ValueError("ReferenceRoutingConfig required")
        _sha(self.terrain_identity)
        _sha(self.boundary_identity)
        area = _number(self.cell_area_m2, "cell_area_m2")
        if area <= 0.:
            raise ValueError("positive cell area required")
        arrays = {name: getattr(self, name) for name in ARRAY_NAMES}
        _check_arrays(arrays, area)
        for name, value in arrays.items():
            object.__setattr__(self, name, readonly(value))
        object.__setattr__(self, "cell_area_m2", area)
        if not isinstance(self.metadata, Mapping):
            raise ValueError("reference metadata mapping required")
        details = _plain(self.metadata)
        if details.get("mode") == "preserved_td_graph":
            _sha(details.get("source_graph_identity_sha256"))
        elif details.get("mode") != "recomputed_dem_policy":
            raise ValueError("reference mode must declare whether TD topology is retained")
        object.__setattr__(self, "metadata", _freeze(details))


def _load_backend():
    try:
        backend = importlib.import_module("pyflwdir")
    except ImportError as error:
        raise OptionalDependencyError(
            "Install algorithm/requirements-reference.txt in an isolated environment for pyflwdir routing"
        ) from error
    if getattr(backend, "__version__", None) != BACKEND_VERSION:
        raise OptionalDependencyError("Expected pyflwdir==" + BACKEND_VERSION + "; install algorithm/requirements-reference.txt")
    return backend


def _inputs(terrain, boundary):
    if not isinstance(terrain, TerrainGrid) or not isinstance(boundary, BoundaryGrid):
        raise TypeError("TerrainGrid and BoundaryGrid required")
    if terrain.elevation_m.shape != boundary.kind.shape or terrain.elevation_m.size < 2:
        raise ValueError("matching grid with at least two cells required")


def _transform(terrain):
    from affine import Affine
    return Affine(terrain.dx_m, 0., terrain.x0_m - terrain.dx_m / 2.,
                  0., -terrain.dz_m, -terrain.z0_m + terrain.dz_m / 2.)


def _extract(backend, routing, terrain, boundary, config, details, outlet_kind=None):
    mask = terrain.valid_mask.ravel()
    size = mask.size
    receiver = np.asarray(routing.idxs_ds, dtype=np.int64).reshape(-1).copy()
    if receiver.size != size:
        raise ValueError("pyflwdir receiver size differs")
    receiver[~mask] = -1
    receiver[receiver == np.arange(size)] = -1
    order = np.asarray(routing.idxs_seq, dtype=np.int64).reshape(-1).copy()
    if np.any(order < 0) or np.any(order >= size):
        raise ValueError("pyflwdir sequence contains invalid indices")
    terminals = np.flatnonzero(mask & (receiver == -1))
    local_area = np.where(terrain.valid_mask, terrain.cell_area_m2, 0.).astype(np.float64)
    upstream = np.asarray(routing.accuflux(local_area, nodata=-9999.), dtype=np.float64).reshape(-1).copy()
    basins = np.asarray(routing.basins(idxs=terminals, ids=(terminals + 1).astype(np.uint32)),
                        dtype=np.int64).reshape(-1) - 1
    stream = np.asarray(routing.stream_order(), dtype=np.int64).reshape(-1).copy()
    upstream[~mask], basins[~mask], stream[~mask] = 0., -1, 0
    if outlet_kind is None:
        outlet_kind = np.full(size, "interior", dtype="U24")
        outlet_kind[~mask] = "inactive"
        outlet_kind[terminals] = "reference_pit"
        rows, columns = terrain.valid_mask.shape
        on_edge = ((terminals // columns == 0) | (terminals // columns == rows - 1)
                   | (terminals % columns == 0) | (terminals % columns == columns - 1))
        outlet_kind[terminals[on_edge]] = "reference_edge_exit"
    root = Path(backend.__file__).parent
    sources = ("__init__.py", "pyflwdir.py", "flwdir.py", "core.py", "core_d8.py",
               "dem.py", "basins.py", "streams.py", "gis_utils.py")
    details = dict(details, transform=list(_transform(terrain)),
                   coordinates="pixel centers X east, northing=-Z; local metric frame, not geographic CRS",
                   backend_source_sha256={name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                          for name in sources},
                   accumulation="pyflwdir.accuflux of float64 dx_m*dz_m per valid cell",
                   basin_id_semantics="downstream terminal cell_id; not wet lake footprint")
    return ReferenceRoutingResult(
        "pyflwdir", backend.__version__, config, receiver, order, upstream, basins, stream,
        terrain.identity_sha256, boundary.identity_sha256, terrain.valid_mask,
        terrain.cell_area_m2, outlet_kind, details)


def analyze_td_graph(terrain, boundary, graph):
    """Reuse pyflwdir metrics while preserving TD receiver, mask and terminal semantics."""
    _inputs(terrain, boundary)
    if not isinstance(graph, RoutingGraph):
        raise TypeError("RoutingGraph required")
    if (graph.terrain_identity_sha256 != terrain.identity_sha256
            or graph.boundary_identity_sha256 != boundary.identity_sha256
            or not np.array_equal(graph.valid_mask, terrain.valid_mask)):
        raise ValueError("TD graph source, boundary or valid mask differs")
    backend = _load_backend()
    codes = np.full(terrain.elevation_m.size, 247, dtype=np.uint8)
    codes[terrain.valid_mask.ravel()] = 0
    donors = np.flatnonzero(graph.receiver >= 0)
    targets = graph.receiver[donors]
    columns = terrain.elevation_m.shape[1]
    row_delta = targets // columns - donors // columns
    col_delta = targets % columns - donors % columns
    codes[donors] = D8_CODES[row_delta + 1, col_delta + 1]
    routing = backend.from_array(codes.reshape(terrain.valid_mask.shape), ftype="d8",
                                 transform=_transform(terrain), latlon=False, cache=False)
    result = _extract(backend, routing, terrain, boundary, ReferenceRoutingConfig(),
                      {"mode": "preserved_td_graph", "api": "pyflwdir.from_array",
                       "source_graph_identity_sha256": graph.identity_sha256,
                       "routing_policy": graph.policy,
                       "boundary_policy": "TD receiver and terminal kinds preserved; no DEM routing"},
                      outlet_kind=graph.outlet_kind)
    if not np.array_equal(result.receiver, graph.receiver):
        raise ValueError("pyflwdir conversion changed TD receivers")
    return result


def run_reference_routing(terrain, boundary, config=ReferenceRoutingConfig()):
    """Explicit external fill/routing experiment; its exit policy differs from TD."""
    _inputs(terrain, boundary)
    if not isinstance(config, ReferenceRoutingConfig):
        raise TypeError("ReferenceRoutingConfig required")
    if not terrain.valid_mask.all():
        raise ReferenceBoundaryUnsupported("from_dem treats nodata rims as exits; use analyze_td_graph for unknown terrain")
    perimeter = np.zeros(terrain.valid_mask.shape, dtype=bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    if (np.any(boundary.kind[perimeter] != "open_outflow")
            or np.any(boundary.kind[~perimeter] != "interior")):
        raise ReferenceBoundaryUnsupported("DEM comparison requires an open perimeter and no internal boundaries")
    if terrain.dx_m != terrain.dz_m:
        raise ReferenceBoundaryUnsupported("from_dem routing does not use metric dx/dz; use a square grid or analyze_td_graph")
    if np.any(terrain.elevation_m == config.nodata):
        raise ValueError("nodata sentinel collides with a valid elevation")
    if np.any(np.abs(terrain.elevation_m) > np.finfo(np.float32).max):
        raise ValueError("elevation exceeds pyflwdir float32 priority queue range")
    backend = _load_backend()
    routing = backend.from_dem(terrain.elevation_m.copy(), nodata=config.nodata,
                               max_depth=config.max_depth, transform=_transform(terrain),
                               outlets=config.outlets, latlon=False)
    return _extract(backend, routing, terrain, boundary, config,
                    {"mode": "recomputed_dem_policy", "api": "pyflwdir.from_dem",
                     "source_graph_identity_sha256": None,
                     "routing_policy": "pyflwdir_wang_liu_fill_d8",
                     "boundary_policy": "external edge/min candidates; TD open cells need not remain terminals",
                     "queue_elevation_dtype": "float32", "work_surface_only": True})


def metadata(result):
    return _plain(result.metadata)


def result_to_record(result):
    arrays = {name: getattr(result, name) for name in ARRAY_NAMES}
    meta = {"schema": SCHEMA, "backend": result.backend, "version": result.version,
            "config": asdict(result.config), "cell_area_m2": result.cell_area_m2,
            "terrain_identity_sha256": result.terrain_identity,
            "boundary_identity_sha256": result.boundary_identity,
            "details": metadata(result), **dict.fromkeys(CAPABILITIES, False)}
    return {"arrays": arrays, "metadata": meta, "identity_sha256": identity(arrays, meta)}


def validate_reference_record(record):
    arrays, meta = record["arrays"], record["metadata"]
    keys = {"schema", "backend", "version", "config", "cell_area_m2", "terrain_identity_sha256",
            "boundary_identity_sha256", "details", *CAPABILITIES}
    if (set(meta) != keys or set(arrays) != set(ARRAY_NAMES) or meta["schema"] != SCHEMA
            or any(meta[name] is not False for name in CAPABILITIES)
            or record["identity_sha256"] != identity(arrays, meta)):
        raise ValueError("reference record schema, identity or capability mismatch")
    ReferenceRoutingResult(backend=meta["backend"], version=meta["version"],
                           config=ReferenceRoutingConfig(**meta["config"]),
                           terrain_identity=meta["terrain_identity_sha256"],
                           boundary_identity=meta["boundary_identity_sha256"],
                           cell_area_m2=meta["cell_area_m2"], metadata=meta["details"], **arrays)


def compare_reference_to_td(reference, td_graph):
    if not isinstance(reference, ReferenceRoutingResult) or not isinstance(td_graph, RoutingGraph):
        raise TypeError("ReferenceRoutingResult and RoutingGraph required")
    if reference.terrain_identity != td_graph.terrain_identity_sha256:
        raise ValueError("terrain identity differs")
    if reference.boundary_identity != td_graph.boundary_identity_sha256:
        raise ValueError("boundary identity differs")
    if not np.array_equal(reference.valid_mask, td_graph.valid_mask):
        raise ValueError("valid mask or grid shape differs")
    flat_valid = reference.valid_mask.ravel()
    area = flat_valid.astype(np.float64) * reference.cell_area_m2
    terminal = np.full(area.size, -1, dtype=np.int64)
    for cell in td_graph.order_downstream_first:
        target = td_graph.receiver[cell]
        terminal[cell] = cell if target < 0 else terminal[target]
    for cell in td_graph.order_downstream_first[::-1]:
        target = td_graph.receiver[cell]
        if target >= 0:
            area[target] += area[cell]
    differences = {"receiver": reference.receiver != td_graph.receiver,
                   "terminal_cell": reference.basin_id != terminal,
                   "upstream_area_m2": ~np.isclose(reference.upstream_area_m2, area, rtol=1e-10, atol=1e-8)}
    counts = {name: int(np.count_nonzero(difference & flat_valid)) for name, difference in differences.items()}
    return {"status": "diagnostic_comparison_not_td_certification",
            "reference_mode": reference.metadata["mode"], "td_policy": td_graph.policy,
            "valid_cells": int(flat_valid.sum()), "mismatch_counts": counts,
            "mismatch_ratios": {name: value / int(flat_valid.sum()) for name, value in counts.items()},
            "maximum_area_difference_m2": float(np.max(abs(reference.upstream_area_m2 - area))),
            "orders_valid": True, "order_comparison": "topological permutations need not be identical",
            "equivalent_boundary_policy": reference.metadata["mode"] == "preserved_td_graph"}
