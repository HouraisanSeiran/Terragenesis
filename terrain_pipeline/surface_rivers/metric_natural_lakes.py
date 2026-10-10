"""Original-bed D4 lake basins with a bounded reduced level-pool/weir replay."""

from dataclasses import asdict, dataclass
from collections import deque
import math

import numpy as np
from scipy.integrate import solve_ivp

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from .metric_contracts import TerrainGrid


DOMAIN_SCHEMA = "terragenesis-natural-lake-domain-v1"
TRACE_SCHEMA = "terragenesis-natural-lake-trace-v1"
ALGORITHM = "original-bed-d4-owner-pools-signed-weirs-v1"
MAX_SUPPORT = 65536
MAX_FACES = 4096
MAX_TRACE_ENTRIES = 8_000_000
MAX_BYTES = 128 * 1024 * 1024
BOUNDARY_KINDS = ("free_outflow", "tailwater", "closed", "unknown")


@dataclass(frozen=True)
class NaturalLakeConfig:
    max_step_seconds: float = 1.
    relative_tolerance: float = 1e-9
    absolute_tolerance_m3: float = 1e-10
    max_steps: int = 20000

    def __post_init__(self):
        for name in ("max_step_seconds", "relative_tolerance", "absolute_tolerance_m3"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.:
                raise ValueError("positive finite " + name + " required")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 100000:
            raise ValueError("bounded max_steps required")


def _neighbors(cell, rows, cols):
    row, col = divmod(int(cell), cols)
    if row:
        yield cell - cols
    if col:
        yield cell - 1
    if col + 1 < cols:
        yield cell + 1
    if row + 1 < rows:
        yield cell + cols


def _face(a, b, shape):
    if b < 0:
        return False
    rows, cols = shape
    if a < 0 or a >= rows * cols or b >= rows * cols:
        return False
    return b in _neighbors(a, rows, cols)


def _terrain_metadata(terrain):
    return {key: getattr(terrain, key) for key in terrain.__dataclass_fields__
            if key not in ("elevation_m", "valid_mask")}


def _domain_expected(terrain, seeds, owner, boundary_faces, boundary_kinds, max_stage):
    shape = terrain.elevation_m.shape
    height = terrain.elevation_m.ravel()
    valid = terrain.valid_mask.ravel()
    flat = owner.ravel()
    count = len(seeds)
    if (seeds.dtype != np.int64 or seeds.shape != (count,) or not 1 <= count <= 256
            or np.unique(seeds).size != count or np.any(seeds < 0) or np.any(seeds >= height.size)
            or owner.dtype != np.int64 or owner.shape != shape
            or np.any(flat < -1) or np.any(flat >= count) or np.any(flat[~valid] != -1)
            or np.count_nonzero(flat >= 0) > MAX_SUPPORT):
        raise ValueError("invalid bounded original-bed lake ownership")
    if (max_stage.dtype != np.float64 or max_stage.shape != (count,)
            or not np.isfinite(max_stage).all() or not valid[seeds].all()
            or not np.array_equal(flat[seeds], np.arange(count))):
        raise ValueError("invalid source seeds or finite upper stages")
    support = np.flatnonzero(flat >= 0).astype(np.int64)
    for lake, seed in enumerate(seeds):
        members = support[flat[support] == lake]
        if max_stage[lake] <= height[seed]:
            raise ValueError("max stage must exceed original seed bed")
        visited = np.zeros(height.size, bool)
        visited[seed] = True
        pending = deque([int(seed)])
        while pending:
            cell = pending.popleft()
            for neighbor in _neighbors(cell, *shape):
                if (not visited[neighbor] and flat[neighbor] == lake
                        and height[neighbor] >= height[cell]):
                    visited[neighbor] = True
                    pending.append(neighbor)
        if not visited[members].all():
            raise ValueError("owner cells lack D4 nonascending original-bed path to seed")
    if (boundary_faces.dtype != np.int64 or boundary_faces.ndim != 2
            or boundary_faces.shape[1] != 2 or len(boundary_faces) > MAX_FACES
            or boundary_kinds.dtype.kind != "U" or boundary_kinds.shape != (len(boundary_faces),)
            or not np.isin(boundary_kinds, BOUNDARY_KINDS).all()):
        raise ValueError("invalid bounded boundary faces or kinds")
    interior = []
    exterior = []
    exterior_crest = {}
    rows, cols = shape
    for cell in support:
        for neighbor in (cell + 1, cell + cols):
            if neighbor >= height.size or neighbor == cell + 1 and cell % cols == cols - 1:
                continue
            if flat[neighbor] >= 0 and flat[neighbor] != flat[cell]:
                interior.append((int(cell), int(neighbor)))
        for neighbor in _neighbors(cell, rows, cols):
            if flat[neighbor] == -1:
                exterior.append((int(cell), int(neighbor)))
                exterior_crest[(int(cell), int(neighbor))] = float(max(height[cell], height[neighbor])) if valid[neighbor] else float(height[cell])
        row, col = divmod(int(cell), cols)
        if row == 0 or row == rows - 1 or col == 0 or col == cols - 1:
            exterior.append((int(cell), -1))
            exterior_crest[(int(cell), -1)] = float(height[cell])
    interior = np.asarray(interior, np.int64).reshape(-1, 2)
    exterior = np.asarray(sorted(exterior), np.int64).reshape(-1, 2)
    if len(interior) + len(exterior) > MAX_FACES:
        raise ValueError("D4 face budget exceeded")
    permitted = set(map(tuple, exterior))
    chosen = list(map(tuple, boundary_faces))
    if len(set(chosen)) != len(chosen) or any(face not in permitted for face in chosen):
        raise ValueError("boundary requires distinct original valid D4 exterior witness")
    if boundary_faces.size and np.any(~valid[boundary_faces[:, 0]]):
        raise ValueError("boundary touches unknown original source")
    internal_crest = np.maximum(height[interior[:, 0]], height[interior[:, 1]])
    boundary_crest = np.asarray([exterior_crest[face] for face in chosen], np.float64)
    unresolved_faces = sorted(permitted - set(chosen))
    unresolved_faces.extend(face for face, kind in zip(chosen, boundary_kinds)
                            if kind == "unknown")
    unresolved = len(unresolved_faces)
    unresolved_limit = np.full(count, np.inf, np.float64)
    for face in unresolved_faces:
        lake = int(flat[face[0]])
        unresolved_limit[lake] = min(unresolved_limit[lake], exterior_crest[face])
    return support, interior, internal_crest, boundary_crest, unresolved, unresolved_limit


def _domain_arrays(terrain, seeds, owner, boundary_faces, boundary_kinds, max_stage):
    support, interior, internal_crest, boundary_crest, unresolved, unresolved_limit = _domain_expected(
        terrain, seeds, owner, boundary_faces, boundary_kinds, max_stage)
    arrays = dict(source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(),
                  seed_cell_ids=seeds.copy(), owner_grid=owner.copy(), max_stage_m=max_stage.copy(),
                  support_cell_ids=support, internal_faces=interior,
                  internal_crest_m=internal_crest, boundary_faces=boundary_faces.copy(),
                  boundary_kinds=boundary_kinds.astype("U16"), boundary_crest_m=boundary_crest,
                  unresolved_stage_limit_m=unresolved_limit)
    return arrays, unresolved


def build_natural_lakes(terrain, seed_cell_ids, owner_grid, *, max_stage_m,
                        boundary_faces, boundary_kinds, weir_coefficient_m3_s_m15,
                        source_provenance, boundary_provenance):
    if not isinstance(terrain, TerrainGrid):
        raise ValueError("TerrainGrid required")
    if (isinstance(weir_coefficient_m3_s_m15, bool)
            or not isinstance(weir_coefficient_m3_s_m15, (int, float))
            or not math.isfinite(weir_coefficient_m3_s_m15)
            or weir_coefficient_m3_s_m15 <= 0.):
        raise ValueError("positive finite explicit reduced-weir coefficient required")
    if not all(isinstance(p, str) and p.strip() for p in (source_provenance, boundary_provenance)):
        raise ValueError("source and boundary provenance required")
    arrays, unresolved = _domain_arrays(terrain, seed_cell_ids, owner_grid,
                                        boundary_faces, boundary_kinds, max_stage_m)
    metadata = dict(schema=DOMAIN_SCHEMA, algorithm=ALGORITHM, terrain_metadata=_terrain_metadata(terrain),
                    source_identity_sha256=terrain.identity_sha256,
                    source_provenance=source_provenance, boundary_provenance=boundary_provenance,
                    weir_coefficient_m3_s_m15=float(weir_coefficient_m3_s_m15),
                    unresolved_exterior_faces=unresolved,
                    cell_volume_model="original_native_cell_prisms_strict_bed_below_stage",
                    hydraulic_model="reduced_level_pool_signed_weir_not_saint_venant",
                    transient_connected_not_common_stage=True, natural_boundary_certified=False)
    arrays = {key: readonly(value) for key, value in arrays.items()}
    bundle = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_natural_lakes(bundle)
    return bundle


def _curves(arrays, area):
    height = arrays["source_height_m"].ravel()
    flat = arrays["owner_grid"].ravel()
    curves = []
    for lake in range(len(arrays["seed_cell_ids"])):
        levels = np.sort(height[flat == lake])
        prefix = np.r_[0., np.cumsum(levels)]
        curves.append((levels, prefix, area))
    return curves


def _volume_at_stage(curve, stage):
    levels, prefix, area = curve
    count = int(np.searchsorted(levels, stage, side="left"))
    return float(area * (count * stage - prefix[count]))


def _stage_at_volume(curve, volume):
    levels, prefix, area = curve
    if volume <= 0.:
        return float(levels[0] + volume / area)
    break_volume = area * (np.arange(len(levels)) * levels - prefix[:-1])
    index = min(int(np.searchsorted(break_volume, volume, side="right") - 1), len(levels) - 1)
    return float((volume / area + prefix[index + 1]) / (index + 1))


def _rates(arrays, coefficient, stage, tailwater):
    owner = arrays["owner_grid"].ravel()
    faces = arrays["internal_faces"]
    boundary = arrays["boundary_faces"]
    internal = np.zeros(len(faces), np.float64)
    external = np.zeros(len(boundary), np.float64)
    for edge, (a, b) in enumerate(faces):
        first, second = int(owner[a]), int(owner[b])
        delta = stage[first] - stage[second]
        if delta:
            high = max(stage[first], stage[second])
            low = min(stage[first], stage[second])
            head = max(high - max(float(arrays["internal_crest_m"][edge]), low), 0.)
            internal[edge] = math.copysign(coefficient * head ** 1.5, delta)
    for edge, (a, _) in enumerate(boundary):
        kind = arrays["boundary_kinds"][edge]
        lake = int(owner[a])
        crest = float(arrays["boundary_crest_m"][edge])
        if kind == "free_outflow":
            external[edge] = coefficient * max(stage[lake] - crest, 0.) ** 1.5
        elif kind == "tailwater":
            delta = stage[lake] - tailwater[edge]
            if delta:
                high = max(stage[lake], tailwater[edge])
                low = min(stage[lake], tailwater[edge])
                external[edge] = math.copysign(coefficient * max(high - max(crest, low), 0.) ** 1.5, delta)
    return internal, external


def _wet_state(arrays, stage):
    support = arrays["support_cell_ids"]
    owner = arrays["owner_grid"].ravel()[support]
    wet = arrays["source_height_m"].ravel()[support] < stage[owner]
    faces = arrays["internal_faces"]
    face_owner = arrays["owner_grid"].ravel()
    height = arrays["source_height_m"].ravel()
    parent = np.arange(len(stage), dtype=np.int64)

    def root(node):
        while parent[node] != node:
            node = int(parent[node])
        return node

    for edge, (a, b) in enumerate(faces):
        first, second = int(face_owner[a]), int(face_owner[b])
        if stage[first] > height[a] and stage[second] > height[b]:
            parent[root(second)] = root(first)
    labels = np.array([root(lake) for lake in range(len(stage))], np.int64)
    return wet, labels


def _terrain_from_arrays(arrays, meta):
    return TerrainGrid(arrays["source_height_m"], arrays["source_valid_mask"],
                       **meta["terrain_metadata"])


def _validate_domain(bundle):
    arrays, meta = bundle["arrays"], bundle["metadata"]
    required = {"source_height_m", "source_valid_mask", "seed_cell_ids", "owner_grid",
                "max_stage_m", "support_cell_ids", "internal_faces", "internal_crest_m",
                "boundary_faces", "boundary_kinds", "boundary_crest_m",
                "unresolved_stage_limit_m"}
    keys = {"schema", "algorithm", "terrain_metadata", "source_identity_sha256",
            "source_provenance", "boundary_provenance", "weir_coefficient_m3_s_m15",
            "unresolved_exterior_faces", "cell_volume_model", "hydraulic_model",
            "transient_connected_not_common_stage", "natural_boundary_certified"}
    if (set(arrays) != required or set(meta) != keys or meta["schema"] != DOMAIN_SCHEMA
            or meta["algorithm"] != ALGORITHM or meta["cell_volume_model"] != "original_native_cell_prisms_strict_bed_below_stage"
            or meta["hydraulic_model"] != "reduced_level_pool_signed_weir_not_saint_venant"
            or meta["transient_connected_not_common_stage"] is not True
            or meta["natural_boundary_certified"] is not False
            or not all(isinstance(meta[k], str) and meta[k].strip() for k in ("source_provenance", "boundary_provenance"))
            or not math.isfinite(meta["weir_coefficient_m3_s_m15"])
            or meta["weir_coefficient_m3_s_m15"] <= 0.):
        raise ValueError("natural lake domain schema or scope mismatch")
    terrain = _terrain_from_arrays(arrays, meta)
    if terrain.identity_sha256 != meta["source_identity_sha256"]:
        raise ValueError("natural lake source identity mismatch")
    expected, unresolved = _domain_arrays(terrain, arrays["seed_cell_ids"], arrays["owner_grid"],
                                          arrays["boundary_faces"], arrays["boundary_kinds"],
                                          arrays["max_stage_m"])
    if unresolved != meta["unresolved_exterior_faces"] or any(not np.array_equal(arrays[k], expected[k]) for k in required):
        raise ValueError("natural lake D4 source faces or storage support mismatch")
    return terrain


def validate_natural_lakes(bundle):
    if (not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}
            or not isinstance(bundle["arrays"], dict) or not isinstance(bundle["metadata"], dict)
            or bundle["identity_sha256"] != identity(bundle["arrays"], bundle["metadata"])
            or sum(value.nbytes for value in bundle["arrays"].values()) > MAX_BYTES):
        raise ValueError("natural lake bundle identity or byte budget mismatch")
    if bundle["metadata"].get("schema") == DOMAIN_SCHEMA:
        _validate_domain(bundle)
    elif bundle["metadata"].get("schema") == TRACE_SCHEMA:
        _validate_trace(bundle)
    else:
        raise ValueError("unknown natural lake schema")
    return True


def save_natural_lakes(path, bundle):
    save_bundle(path, bundle, validator=validate_natural_lakes)


def load_natural_lakes(path, *, expected_sha256, expected_identity):
    bundle = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_natural_lakes, max_bytes=MAX_BYTES)
    if bundle["identity_sha256"] != expected_identity:
        raise ValueError("external natural lake identity mismatch")
    return bundle


def lake_volume_at_stage(domain, lake_index, stage_m):
    validate_natural_lakes(domain)
    if domain["metadata"]["schema"] != DOMAIN_SCHEMA:
        raise ValueError("natural lake domain required")
    arrays = domain["arrays"]
    if type(lake_index) is not int or not 0 <= lake_index < len(arrays["seed_cell_ids"]):
        raise ValueError("lake index outside domain")
    if not isinstance(stage_m, (int, float)) or not math.isfinite(stage_m):
        raise ValueError("finite stage required")
    terrain = _terrain_from_arrays(arrays, domain["metadata"])
    curve = _curves(arrays, terrain.cell_area_m2)[lake_index]
    if not curve[0][0] <= stage_m <= arrays["max_stage_m"][lake_index]:
        raise ValueError("stage outside declared support")
    return _volume_at_stage(curve, stage_m)


def lake_stage_at_volume(domain, lake_index, volume_m3):
    validate_natural_lakes(domain)
    if domain["metadata"]["schema"] != DOMAIN_SCHEMA:
        raise ValueError("natural lake domain required")
    arrays = domain["arrays"]
    if type(lake_index) is not int or not 0 <= lake_index < len(arrays["seed_cell_ids"]):
        raise ValueError("lake index outside domain")
    if not isinstance(volume_m3, (int, float)) or not math.isfinite(volume_m3):
        raise ValueError("finite volume required")
    terrain = _terrain_from_arrays(arrays, domain["metadata"])
    curve = _curves(arrays, terrain.cell_area_m2)[lake_index]
    capacity = _volume_at_stage(curve, arrays["max_stage_m"][lake_index])
    if not 0. <= volume_m3 <= capacity:
        raise ValueError("volume outside finite source support")
    return _stage_at_volume(curve, volume_m3)


def solve_natural_lakes(domain, time_seconds, local_q_m3_s, initial_volume_m3,
                        tailwater_stage_m, *, config=None, forcing_provenance):
    """Integrate piecewise-constant forcing; retain verified accepted-step prefix on failure."""
    validate_natural_lakes(domain)
    if domain["metadata"]["schema"] != DOMAIN_SCHEMA:
        raise ValueError("natural lake domain bundle required")
    if config is None:
        config = NaturalLakeConfig()
    if not isinstance(config, NaturalLakeConfig):
        raise ValueError("NaturalLakeConfig required")
    if not isinstance(forcing_provenance, str) or not forcing_provenance.strip():
        raise ValueError("forcing provenance required")
    a = domain["arrays"]
    lakes = len(a["seed_cell_ids"])
    edges = len(a["internal_faces"])
    boundaries = len(a["boundary_faces"])
    times = np.asarray(time_seconds)
    local = np.asarray(local_q_m3_s)
    initial = np.asarray(initial_volume_m3)
    tailwater = np.asarray(tailwater_stage_m)
    if (times.dtype != np.float64 or times.ndim != 1 or not 2 <= len(times) <= 100001
            or not np.isfinite(times).all() or times[0] < 0. or np.any(np.diff(times) <= 0.)
            or local.dtype != np.float64 or local.shape != (len(times) - 1, lakes)
            or not np.isfinite(local).all() or np.any(local < 0.)
            or initial.dtype != np.float64 or initial.shape != (lakes,) or not np.isfinite(initial).all()
            or tailwater.dtype != np.float64 or tailwater.shape != (len(times) - 1, boundaries)
            or not np.isfinite(tailwater).all()):
        raise ValueError("finite forcing intervals, nonnegative local supply and initial stock required")
    if (times.nbytes + local.nbytes + initial.nbytes + tailwater.nbytes > MAX_BYTES // 2):
        raise ValueError("forcing byte budget exceeded")
    terrain = _terrain_from_arrays(a, domain["metadata"])
    curves = _curves(a, terrain.cell_area_m2)
    capacity = np.array([_volume_at_stage(curve, upper)
                         for curve, upper in zip(curves, a["max_stage_m"])])
    if np.any(initial < 0.) or np.any(initial > capacity):
        raise ValueError("initial lake stock outside finite source support")
    initial_stage = np.array([_stage_at_volume(curve, volume)
                              for curve, volume in zip(curves, initial)])
    if np.any(initial_stage > a["unresolved_stage_limit_m"]):
        raise ValueError("initial stock overtops unresolved exterior face")
    coefficient = domain["metadata"]["weir_coefficient_m3_s_m15"]
    owner = a["owner_grid"].ravel()
    edge_from = owner[a["internal_faces"][:, 0]]
    edge_to = owner[a["internal_faces"][:, 1]]
    boundary_from = owner[a["boundary_faces"][:, 0]]
    state = np.r_[initial, np.zeros(edges + boundaries)]
    trace_times = [float(times[0])]
    states = [state.copy()]
    intervals = [0]
    failure = None
    failure_time = None

    def derivative(_, values, interval):
        stage = np.array([_stage_at_volume(curve, volume)
                          for curve, volume in zip(curves, values[:lakes])])
        internal_q, boundary_q = _rates(a, coefficient, stage, tailwater[interval])
        change = local[interval].copy()
        np.add.at(change, edge_from, -internal_q)
        np.add.at(change, edge_to, internal_q)
        np.add.at(change, boundary_from, -boundary_q)
        return np.r_[change, internal_q, boundary_q]

    events = []
    event_reasons = []
    for lake in range(lakes):
        def capacity_event(_, values, lake=lake):
            return capacity[lake] - values[lake]
        capacity_event.direction = -1
        capacity_event.terminal = True
        events.append(capacity_event)
        event_reasons.append("finite source support capacity reached")
        if math.isfinite(a["unresolved_stage_limit_m"][lake]):
            def unresolved_event(_, values, lake=lake):
                stage = _stage_at_volume(curves[lake], values[lake])
                return a["unresolved_stage_limit_m"][lake] - stage
            unresolved_event.direction = -1
            unresolved_event.terminal = True
            events.append(unresolved_event)
            event_reasons.append("unresolved exterior face crest reached")

    for interval in range(len(times) - 1):
        if failure:
            break
        remaining = config.max_steps - (len(trace_times) - 1)
        if remaining <= 0:
            failure, failure_time = "maximum accepted step count exceeded", trace_times[-1]
            break
        try:
            result = solve_ivp(lambda t, y: derivative(t, y, interval),
                               (float(times[interval]), float(times[interval + 1])), state,
                               method="DOP853", rtol=config.relative_tolerance,
                               atol=config.absolute_tolerance_m3,
                               max_step=config.max_step_seconds, events=events)
        except (ValueError, OverflowError, FloatingPointError) as error:
            failure, failure_time = "ODE evaluation failed: " + str(error), trace_times[-1]
            break
        if result.status == 1:
            event_index = next(index for index, hits in enumerate(result.t_events) if len(hits))
            failure, failure_time = event_reasons[event_index], float(result.t_events[event_index][0])
        elif not result.success:
            failure, failure_time = "ODE integration failed: " + result.message, float(result.t[-1])
        for t, value in zip(result.t[1:], result.y.T[1:]):
            if t <= trace_times[-1]:
                continue
            if len(trace_times) - 1 >= config.max_steps:
                failure, failure_time = "maximum accepted step count exceeded", float(t)
                break
            if not np.isfinite(value).all() or np.any(value[:lakes] < 0.) or np.any(value[:lakes] > capacity):
                failure, failure_time = "finite stock boundary crossed", float(t)
                break
            if (len(trace_times) + 1) * (4 * lakes + 3 * edges + 3 * boundaries + len(a["support_cell_ids"])) > MAX_TRACE_ENTRIES:
                failure, failure_time = "trace entry budget exceeded", float(t)
                break
            trace_times.append(float(t))
            states.append(value.copy())
            intervals.append(interval)
        state = states[-1]
        if not failure and not math.isclose(trace_times[-1], times[interval + 1], rel_tol=0., abs_tol=1e-9):
            failure, failure_time = "incomplete forcing interval", float(result.t[-1])
    state_array = np.asarray(states)
    volume = state_array[:, :lakes]
    stage = np.array([[_stage_at_volume(curve, v) for curve, v in zip(curves, row)]
                      for row in volume])
    wet_states = [_wet_state(a, row) for row in stage]
    internal_q = []
    boundary_q = []
    for row, interval in zip(stage, intervals):
        q, bq = _rates(a, coefficient, row, tailwater[interval])
        internal_q.append(q)
        boundary_q.append(bq)
    arrays = dict(time_seconds=np.asarray(trace_times, np.float64),
                  interval_index=np.asarray(intervals, np.int64),
                  volume_m3=volume.copy(), stage_m=stage,
                  internal_transfer_m3=state_array[:, lakes:lakes + edges].copy(),
                  boundary_transfer_m3=state_array[:, lakes + edges:].copy(),
                  internal_q_m3_s=(np.asarray(internal_q, np.float64).reshape(len(trace_times), edges)
                                   if edges else np.empty((len(trace_times), 0), np.float64)),
                  boundary_q_m3_s=(np.asarray(boundary_q, np.float64).reshape(len(trace_times), boundaries)
                                   if boundaries else np.empty((len(trace_times), 0), np.float64)),
                  wet_support=np.asarray([item[0] for item in wet_states], bool),
                  wet_component=np.asarray([item[1] for item in wet_states], np.int64),
                  forcing_time_seconds=times.copy(), local_q_m3_s=local.copy(),
                  initial_volume_m3=initial.copy(), tailwater_stage_m=tailwater.copy())
    arrays.update({"domain_" + key: value.copy() for key, value in a.items()})
    metadata = dict(schema=TRACE_SCHEMA, algorithm=ALGORITHM, domain_identity_sha256=domain["identity_sha256"],
                    domain_metadata=domain["metadata"], config=asdict(config),
                    forcing_provenance=forcing_provenance,
                    status="failed_prefix" if failure else "complete",
                    failure_reason=failure, failure_time_seconds=failure_time,
                    hydraulic_model="reduced_level_pool_signed_weir_not_saint_venant",
                    common_stage_certified=False)
    arrays = {key: readonly(value) for key, value in arrays.items()}
    bundle = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_natural_lakes(bundle)
    return bundle


def _validate_trace(bundle):
    arrays, meta = bundle["arrays"], bundle["metadata"]
    base = {"time_seconds", "interval_index", "volume_m3", "stage_m",
            "internal_transfer_m3", "boundary_transfer_m3", "internal_q_m3_s",
            "boundary_q_m3_s", "wet_support", "wet_component", "forcing_time_seconds",
            "local_q_m3_s", "initial_volume_m3", "tailwater_stage_m"}
    domain_keys = {key for key in arrays if key.startswith("domain_")}
    required_meta = {"schema", "algorithm", "domain_identity_sha256", "domain_metadata",
                     "config", "forcing_provenance", "status", "failure_reason",
                     "failure_time_seconds", "hydraulic_model", "common_stage_certified"}
    if (set(arrays) != base | domain_keys or set(meta) != required_meta
            or meta["schema"] != TRACE_SCHEMA or meta["algorithm"] != ALGORITHM
            or meta["hydraulic_model"] != "reduced_level_pool_signed_weir_not_saint_venant"
            or meta["common_stage_certified"] is not False
            or not isinstance(meta["forcing_provenance"], str) or not meta["forcing_provenance"].strip()):
        raise ValueError("natural lake trace schema mismatch")
    domain_arrays = {key.removeprefix("domain_"): arrays[key] for key in domain_keys}
    domain = {"arrays": domain_arrays, "metadata": meta["domain_metadata"],
              "identity_sha256": meta["domain_identity_sha256"]}
    if identity(domain_arrays, domain["metadata"]) != domain["identity_sha256"]:
        raise ValueError("natural lake embedded domain identity mismatch")
    terrain = _validate_domain(domain)
    NaturalLakeConfig(**meta["config"])
    a = domain_arrays
    n = len(a["seed_cell_ids"])
    e = len(a["internal_faces"])
    b = len(a["boundary_faces"])
    t = arrays["time_seconds"]
    intervals = arrays["interval_index"]
    forcing_time = arrays["forcing_time_seconds"]
    local = arrays["local_q_m3_s"]
    tailwater = arrays["tailwater_stage_m"]
    initial = arrays["initial_volume_m3"]
    steps = len(t)
    fields = (("volume_m3", (steps, n), np.float64),
              ("stage_m", (steps, n), np.float64),
              ("internal_transfer_m3", (steps, e), np.float64),
              ("boundary_transfer_m3", (steps, b), np.float64),
              ("internal_q_m3_s", (steps, e), np.float64),
              ("boundary_q_m3_s", (steps, b), np.float64),
              ("wet_support", (steps, len(a["support_cell_ids"])), bool),
              ("wet_component", (steps, n), np.int64))
    if (t.dtype != np.float64 or t.ndim != 1 or not 1 <= steps <= 100001
            or not np.isfinite(t).all() or np.any(np.diff(t) <= 0.)
            or intervals.dtype != np.int64 or intervals.shape != (steps,)
            or forcing_time.dtype != np.float64 or forcing_time.ndim != 1
            or not 2 <= len(forcing_time) <= 100001 or not np.isfinite(forcing_time).all()
            or np.any(np.diff(forcing_time) <= 0.) or t[0] != forcing_time[0]
            or local.dtype != np.float64 or local.shape != (len(forcing_time) - 1, n)
            or not np.isfinite(local).all() or np.any(local < 0.)
            or tailwater.dtype != np.float64 or tailwater.shape != (len(forcing_time) - 1, b)
            or not np.isfinite(tailwater).all() or initial.dtype != np.float64
            or initial.shape != (n,) or not np.isfinite(initial).all()
            or any(arrays[name].dtype != dtype or arrays[name].shape != shape
                   for name, shape, dtype in fields)
            or any(not np.isfinite(arrays[name]).all() for name, _, dtype in fields if dtype == np.float64)):
        raise ValueError("natural lake trace shape/time/finite mismatch")
    if np.any(intervals < 0) or np.any(intervals >= len(forcing_time) - 1):
        raise ValueError("trace forcing interval outside range")
    for k, instant in enumerate(t):
        expected_interval = min(int(np.searchsorted(forcing_time, instant, side="right") - 1), len(forcing_time) - 2)
        if intervals[k] != expected_interval and not (k and instant == forcing_time[intervals[k] + 1]):
            raise ValueError("trace forcing interval mismatch")
    for name in ("internal_transfer_m3", "boundary_transfer_m3"):
        if np.any(arrays[name][0] != 0.):
            raise ValueError("nonzero initial paired transfer")
    if not np.array_equal(arrays["volume_m3"][0], initial):
        raise ValueError("initial source stock mismatch")
    curves = _curves(a, terrain.cell_area_m2)
    capacity = np.array([_volume_at_stage(curve, upper) for curve, upper in zip(curves, a["max_stage_m"])])
    volumes = arrays["volume_m3"]
    if np.any(volumes < 0.) or np.any(volumes > capacity):
        raise ValueError("trace finite stock outside source support")
    if np.any(arrays["stage_m"] > a["unresolved_stage_limit_m"][None, :] + 1e-9):
        raise ValueError("trace crosses unresolved exterior face crest")
    owner = a["owner_grid"].ravel()
    edge_from = owner[a["internal_faces"][:, 0]]
    edge_to = owner[a["internal_faces"][:, 1]]
    boundary_from = owner[a["boundary_faces"][:, 0]]
    coefficient = domain["metadata"]["weir_coefficient_m3_s_m15"]
    for step in range(steps):
        stage = np.array([_stage_at_volume(curve, v) for curve, v in zip(curves, volumes[step])])
        if not np.allclose(arrays["stage_m"][step], stage, rtol=0., atol=1e-8):
            raise ValueError("source storage stage mismatch")
        wet, component = _wet_state(a, stage)
        if (not np.array_equal(arrays["wet_support"][step], wet)
                or not np.array_equal(arrays["wet_component"][step], component)):
            raise ValueError("original-bed wet footprint or merge state mismatch")
        q, bq = _rates(a, coefficient, stage, tailwater[intervals[step]])
        if (not np.allclose(arrays["internal_q_m3_s"][step], q, rtol=1e-9, atol=1e-9)
                or not np.allclose(arrays["boundary_q_m3_s"][step], bq, rtol=1e-9, atol=1e-9)):
            raise ValueError("weir law endpoint flux mismatch")
        if step:
            dt = t[step] - t[step - 1]
            previous_interval = intervals[step]
            if t[step] == forcing_time[previous_interval + 1]:
                pass
            elif (intervals[step - 1] != previous_interval
                  and t[step - 1] != forcing_time[previous_interval]):
                raise ValueError("accepted step crosses forcing change")
            budget = volumes[step - 1] + local[previous_interval] * dt
            transfer = arrays["internal_transfer_m3"][step] - arrays["internal_transfer_m3"][step - 1]
            external = arrays["boundary_transfer_m3"][step] - arrays["boundary_transfer_m3"][step - 1]
            np.add.at(budget, edge_from, -transfer)
            np.add.at(budget, edge_to, transfer)
            np.add.at(budget, boundary_from, -external)
            if not np.allclose(volumes[step], budget, rtol=1e-9, atol=1e-7):
                raise ValueError("paired lake volume ledger mismatch")
    if meta["status"] == "complete":
        if meta["failure_reason"] is not None or meta["failure_time_seconds"] is not None or abs(t[-1] - forcing_time[-1]) > 1e-9:
            raise ValueError("incomplete lake trace marked complete")
    elif meta["status"] == "failed_prefix":
        if (not isinstance(meta["failure_reason"], str) or not meta["failure_reason"]
                or not isinstance(meta["failure_time_seconds"], (int, float))
                or not math.isfinite(meta["failure_time_seconds"])
                or meta["failure_time_seconds"] < t[-1] - 1e-9):
            raise ValueError("invalid actual failure prefix witness")
    else:
        raise ValueError("unknown natural lake trace status")
