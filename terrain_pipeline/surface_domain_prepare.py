"""Complete declared-land routing, explicit fine recovery and read-only bundles."""

from collections import deque
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
import heapq
import json
import math
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
import zipfile

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, digest
from terrain_pipeline.channel_inundation import InundationRecipe
from terrain_pipeline.channel_reroute import RerouteRecipe
from terrain_pipeline.channel_stage import StageRecipe
from terrain_pipeline.local_channel_sections import SectionRecipe
from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel
from terrain_pipeline.network_valley import NetworkValleyRecipe
from terrain_pipeline.surface_network_consumer import _payload, _proof_gate
from terrain_pipeline.surface_network_prepare import SurfaceNetworkBudget
from terrain_pipeline.surface_network_recovery import FineGrid, RecoveryRecipe, recover_surface_network
from terrain_pipeline.valley_geometry import ValleyGeometryRecipe


VERSION = "surface-domain-prepare-v1"
MAX_BYTES = 256 * 1024 * 1024
MAX_INPUT_CELLS = 1500000


@dataclass(frozen=True)
class SurfaceDomainResources:
    max_coarse_cells: int = 250000
    max_coarse_work_cells: int = 500000
    max_fine_cells: int = 1000000
    max_fine_work_cells: int = 4000000
    max_attempts: int = 32
    max_retained_bytes: int = MAX_BYTES
    max_domains: int = 64

    def __post_init__(self):
        ceilings = (MAX_INPUT_CELLS, 8000000, 8000000, 32000000, 256, MAX_BYTES, 256)
        if any(type(value) is not int or not 0 < value <= ceiling
               for value, ceiling in zip(asdict(self).values(), ceilings)):
            raise ValueError("invalid shared domain resource bounds")


@dataclass(frozen=True)
class DomainFineConfiguration:
    fine: FineGrid
    outlet_stage_m: np.ndarray
    channel_recipe: ChannelRecipe
    section_recipe: SectionRecipe
    stage_recipe: StageRecipe
    inundation_recipe: InundationRecipe
    budget: SurfaceNetworkBudget
    network_recipe: NetworkValleyRecipe
    valley_recipe: ValleyGeometryRecipe
    reroute_recipe: RerouteRecipe
    recovery_recipe: RecoveryRecipe

    def __post_init__(self):
        expected = (FineGrid, np.ndarray, ChannelRecipe, SectionRecipe, StageRecipe,
                    InundationRecipe, SurfaceNetworkBudget, NetworkValleyRecipe,
                    ValleyGeometryRecipe, RerouteRecipe, RecoveryRecipe)
        if any(not isinstance(value, kind) for value, kind in zip(self.__dict__.values(), expected)):
            raise ValueError("every fine grid, stage and physical recipe must be explicit")
        stage = self.outlet_stage_m
        if stage.ndim != 1 or stage.dtype.kind not in "fiu" or not np.isfinite(stage).all():
            raise ValueError("outlet stages must be a finite numeric vector")
        object.__setattr__(self, "outlet_stage_m", _freeze(stage.astype(np.float64)))


def _freeze(value):
    if isinstance(value, np.ndarray):
        contiguous = np.ascontiguousarray(value)
        return np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(child) for child in value)
    return value


def _encode(value, arrays):
    if isinstance(value, np.ndarray):
        key = f"array_{len(arrays):05d}"
        arrays[key] = value
        return {"$array": key, "sha256": array_hash(value), "shape": list(value.shape), "dtype": value.dtype.str}
    if isinstance(value, Mapping):
        return {key: _encode(child, arrays) for key, child in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_encode(child, arrays) for child in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(child) for child in value]
    return value


def _hash(value):
    return digest(_encode(value, {}))


def _bytes(value):
    arrays = {}
    tree = _encode(value, arrays)
    return sum(array.nbytes for array in arrays.values()) + len(json.dumps(tree, ensure_ascii=False).encode("utf8"))


def _seal(result):
    result["identity_sha256"] = _hash(result)
    return _freeze(result)


def _neighbors(cell, shape, allowed):
    row, column = divmod(cell, shape[1])
    for dz in (-1, 0, 1):
        for dx in (-1, 0, 1):
            next_row, next_column = row + dz, column + dx
            if ((dz == 0 and dx == 0) or not 0 <= next_row < shape[0] or
                    not 0 <= next_column < shape[1] or not allowed[next_row, next_column]):
                continue
            if dz and dx and not (allowed[row, next_column] and allowed[next_row, column]):
                continue
            yield next_row * shape[1] + next_column


def _edge_ok(donor, target, shape, allowed):
    return target in _neighbors(donor, shape, allowed)


def _ocean_connected(ocean, valid, protected):
    allowed = ocean & valid & ~protected
    connected = np.zeros(ocean.shape, bool)
    boundary = np.zeros(ocean.shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    queue = deque(int(cell) for cell in np.flatnonzero(allowed & boundary))
    connected.flat[list(queue)] = True
    while queue:
        cell = queue.popleft()
        for target in _neighbors(cell, ocean.shape, allowed):
            if not connected.flat[target]:
                connected.flat[target] = True
                queue.append(target)
    return connected


def _normalize_inputs(height_m, valid_mask, domain_labels, land_mask, ocean_mask, protected_mask,
                      coastal_outlets, runoff_m_s, external_q_m3_s, spacing_x_m, spacing_z_m,
                      origin_x_m, origin_z_m, sea_level_elevation_m, vertical_datum,
                      source_identity, source_kind, boundary_complete, scope, outlet_evidence, resources):
    height = np.asarray(height_m)
    if (height.ndim != 2 or min(height.shape) < 2 or height.size > MAX_INPUT_CELLS or
            height.dtype.kind not in "fiu"):
        raise ValueError("invalid or excessive source grid")
    masks = [np.asarray(value) for value in (valid_mask, land_mask, ocean_mask, protected_mask)]
    if any(mask.dtype != bool or mask.shape != height.shape for mask in masks):
        raise ValueError("matching explicit boolean valid/land/ocean/protected masks required")
    valid, land, ocean, protected = masks
    if np.any(ocean & (~valid | (height > sea_level_elevation_m))):
        raise ValueError("declared ocean must be finite-valid and H0 at or below explicit sea level")
    labels = np.asarray(domain_labels)
    if (labels.shape != height.shape or labels.dtype.kind not in "iu" or np.any(labels < -1) or
            np.any(land & ocean) or np.any((labels > 0) & ~land) or
            np.any((labels == 0) != ocean) or np.any(land & (labels == 0)) or
            np.any(valid & ~np.isfinite(height))):
        raise ValueError("inconsistent land/ocean/unknown labels or finite-valid declaration")
    for name, value in (("spacing_x_m", spacing_x_m), ("spacing_z_m", spacing_z_m),
                        ("origin_x_m", origin_x_m), ("origin_z_m", origin_z_m),
                        ("sea_level_elevation_m", sea_level_elevation_m)):
        if isinstance(value, bool) or not math.isfinite(value) or (name.startswith("spacing") and value <= 0):
            raise ValueError("invalid metric coordinate or sea level")
    if (not isinstance(resources, SurfaceDomainResources) or type(boundary_complete) is not bool or
            scope not in ("complete_grid", "subdomain") or
            outlet_evidence not in ("engineering_declared", "independently_observed") or
            any(not isinstance(value, str) or not value.strip()
                for value in (vertical_datum, source_identity, source_kind))):
        raise ValueError("source identity/datum/kind, scope, boundary and outlet evidence required")
    rate = np.broadcast_to(np.asarray(runoff_m_s), height.shape)
    external = np.asarray(external_q_m3_s)
    if any(value.shape != height.shape or value.dtype.kind not in "fiu" or
           not np.isfinite(value).all() or np.any(value < 0) for value in (rate, external)):
        raise ValueError("runoff and external Q must be finite nonnegative matching fields")
    if np.any((rate != 0) & ~land) or np.any((external != 0) & ~land):
        raise ValueError("water inputs may only be assigned to declared land")
    exits = []
    if not isinstance(coastal_outlets, (tuple, list)):
        raise ValueError("explicit coastal outlet triples required")
    for entry in coastal_outlets:
        if (not isinstance(entry, (tuple, list)) or len(entry) != 3 or
                any(type(value) is not int for value in entry) or entry[0] <= 0 or
                any(not 0 <= value < height.size for value in entry[1:])):
            raise ValueError("coastal outlet must be (domain id, flat land node, flat ocean node)")
        exits.append(list(entry))
    if len({entry[1] for entry in exits}) != len(exits):
        raise ValueError("duplicate coastal land outlet")
    return {"height_m": height.astype(np.float64), "valid_mask": valid, "domain_labels": labels.astype(np.int64),
        "land_mask": land, "ocean_mask": ocean, "protected_mask": protected,
        "coastal_outlets": sorted(exits), "runoff_m_s": rate.astype(np.float64),
        "external_q_m3_s": external.astype(np.float64), "spacing_x_m": float(spacing_x_m),
        "spacing_z_m": float(spacing_z_m), "origin_x_m": float(origin_x_m), "origin_z_m": float(origin_z_m),
        "sea_level_elevation_m": float(sea_level_elevation_m), "vertical_datum": vertical_datum,
        "source_identity": source_identity, "source_kind": source_kind, "boundary_complete": boundary_complete,
        "scope": scope, "outlet_evidence": outlet_evidence, "resources": asdict(resources)}


def _declaration_failures(inputs):
    labels, land = inputs["domain_labels"], inputs["land_mask"]
    failures = []
    if np.any(labels == -1):
        failures.append("unknown_or_unassigned_cells")
    if np.any(land & ((labels <= 0) | ~inputs["valid_mask"])):
        failures.append("land_not_uniquely_valid_assigned")
    if np.any(~inputs["valid_mask"]):
        failures.append("invalid_source_cells")
    if np.any(land & inputs["protected_mask"]):
        failures.append("protected_land_cannot_be_routed_without_losing_local_water")
    return failures


def _coast_gate(inputs):
    if not inputs["coastal_outlets"]:
        return np.zeros(inputs["height_m"].shape, bool)
    connected = _ocean_connected(inputs["ocean_mask"], inputs["valid_mask"], inputs["protected_mask"])
    labels, shape = inputs["domain_labels"], inputs["height_m"].shape
    for domain_id, land_cell, ocean_cell in inputs["coastal_outlets"]:
        allowed = ((labels == domain_id) | connected) & inputs["valid_mask"] & ~inputs["protected_mask"]
        if (labels.flat[land_cell] != domain_id or not connected.flat[ocean_cell] or
                not allowed.flat[land_cell] or not _edge_ok(land_cell, ocean_cell, shape, allowed)):
            raise ValueError("false coast: land exit needs boundary-connected declared ocean and legal orthogonal supports")
    return connected


def _flood(height, allowed, exits, cancel):
    receiver = np.full(height.size, -2, np.int64)
    working = np.full(height.size, np.nan)
    queue = []
    for cell in sorted(exits):
        receiver[cell] = -1
        working[cell] = height.flat[cell]
        heapq.heappush(queue, (working[cell], cell))
    order = []
    while queue:
        if cancel is not None and cancel():
            return None
        level, cell = heapq.heappop(queue)
        order.append(cell)
        for donor in _neighbors(cell, height.shape, allowed):
            if receiver[donor] != -2:
                continue
            receiver[donor] = cell
            working[donor] = max(float(height.flat[donor]), level)
            heapq.heappush(queue, (working[donor], donor))
    if len(order) != int(allowed.sum()):
        raise ValueError("land component has no supported route to explicit coast exit")
    return receiver, working, order


def plan_surface_domains(height_m, valid_mask, domain_labels, land_mask, ocean_mask,
                         protected_mask, coastal_outlets, runoff_m_s, external_q_m3_s,
                         spacing_x_m, spacing_z_m, origin_x_m, origin_z_m,
                         sea_level_elevation_m, vertical_datum, source_identity, source_kind,
                         boundary_complete, scope, outlet_evidence, resources, *, cancel=None):
    """Route all declared land; never present planning as fine terrain completion."""
    if not isinstance(resources, SurfaceDomainResources):
        raise ValueError("explicit shared resources required")
    count = np.asarray(height_m).size
    if count * 200 + 32768 > resources.max_retained_bytes:
        raise ValueError("retained input evidence resource preflight")
    inputs = _normalize_inputs(height_m, valid_mask, domain_labels, land_mask, ocean_mask, protected_mask,
        coastal_outlets, runoff_m_s, external_q_m3_s, spacing_x_m, spacing_z_m, origin_x_m,
        origin_z_m, sea_level_elevation_m, vertical_datum, source_identity, source_kind,
        boundary_complete, scope, outlet_evidence, resources)
    labels, height = inputs["domain_labels"], inputs["height_m"]
    domain_ids = sorted(int(value) for value in np.unique(labels[labels > 0]))
    failures = _declaration_failures(inputs)
    _coast_gate(inputs)
    if height.size > resources.max_coarse_cells or len(domain_ids) > resources.max_domains:
        failures.append("coarse_resource_limit")
    local = inputs["runoff_m_s"] * spacing_x_m * spacing_z_m + inputs["external_q_m3_s"]
    if not np.isfinite(local).all():
        raise ValueError("local runoff discharge overflows")
    receiver = np.full(height.size, -2, np.int64)
    working = np.full(height.shape, np.nan)
    discharge = np.zeros(height.shape)
    orders, domains = [], []
    cancelled = False
    for domain_id in domain_ids:
        allowed = (labels == domain_id) & inputs["valid_mask"] & ~inputs["protected_mask"]
        rows, columns = np.nonzero(labels == domain_id)
        bounds = [int(rows.min()), int(rows.max()) + 1, int(columns.min()), int(columns.max()) + 1]
        for axis in (0, 2):
            if bounds[axis + 1] - bounds[axis] < 2:
                bounds[axis] = max(0, bounds[axis] - 1)
                bounds[axis + 1] = min(height.shape[axis // 2], bounds[axis] + 2)
        record = {"domain_id": domain_id, "bounds_zx": bounds, "status": "pending", "reason": None}
        domains.append(record)
        if failures or cancelled:
            continue
        if cancel is not None and cancel():
            cancelled = True
            continue
        exits = [entry[1] for entry in inputs["coastal_outlets"] if entry[0] == domain_id]
        try:
            if not exits:
                raise ValueError("domain has no explicit coast exit")
            routed = _flood(height, allowed, exits, cancel)
            if routed is None:
                cancelled = True
                continue
            routed_receiver, routed_working, order = routed
            receiver[allowed.ravel()] = routed_receiver[allowed.ravel()]
            working[allowed] = routed_working.reshape(height.shape)[allowed]
            discharge[allowed] = local[allowed]
            for donor in reversed(order):
                target = receiver[donor]
                if target >= 0:
                    discharge.flat[target] += discharge.flat[donor]
            if not np.isfinite(discharge).all():
                raise ValueError("accumulated discharge overflows")
            orders.extend(order)
            record["status"] = "routed"
        except ValueError as error:
            record.update(status="diagnostic", reason=str(error))
    if cancelled:
        failures.append("cancelled")
    if any(domain["status"] == "diagnostic" for domain in domains):
        failures.append("unrouted_domain")
    transfers = [{"domain_id": domain_id, "land_cell": land_cell, "ocean_cell": ocean_cell,
                  "discharge_m3_s": float(discharge.flat[land_cell])}
                 for domain_id, land_cell, ocean_cell in inputs["coastal_outlets"]]
    result = {"algorithm_version": VERSION, "kind": "plan", "status": "diagnostic" if failures else "candidate",
        "inputs": inputs, "arrays": {"receiver": receiver, "order": np.array(orders, np.int64),
            "working_fill_m": working, "local_discharge_m3_s": local, "discharge_m3_s": discharge},
        "domains": domains, "failures": failures, "coastal_transfers": transfers,
        "unrouted_local_discharge_m3_s": float(local.ravel()[receiver == -2].sum())}
    if _bytes(result) > resources.max_retained_bytes:
        raise ValueError("retained input evidence exceeds limit")
    return _seal(result)


def _domain_arrays(candidate, record):
    inputs, arrays = candidate["inputs"], candidate["arrays"]
    first_row, last_row, first_column, last_column = record["bounds_zx"]
    window = np.s_[first_row:last_row, first_column:last_column]
    shape = inputs["height_m"][window].shape
    global_cells = np.arange(inputs["height_m"].size).reshape(inputs["height_m"].shape)[window].ravel()
    local_indices = {int(cell): index for index, cell in enumerate(global_cells)}
    receiver = np.full(len(global_cells), -1, np.int64)
    for index, cell in enumerate(global_cells):
        target = int(arrays["receiver"][cell])
        if inputs["domain_labels"].flat[cell] == record["domain_id"] and target >= 0:
            receiver[index] = local_indices[target]
    domain = inputs["domain_labels"][window] == record["domain_id"]
    order = [index for index in range(len(receiver)) if not domain.flat[index]]
    order.extend(local_indices[int(cell)] for cell in arrays["order"]
                 if int(cell) in local_indices and domain.flat[local_indices[int(cell)]])
    discharge = np.where(domain, arrays["discharge_m3_s"][window], 0.)
    return window, domain, receiver, np.array(order, np.int64), (receiver == -1).reshape(shape), discharge


def _fine_binding(candidate, record, fine):
    inputs = candidate["inputs"]
    first_row, last_row, first_column, last_column = record["bounds_zx"]
    axes = []
    for axis, first, last, size in (("z", first_row, last_row, fine.shape_zx[0]),
                                    ("x", first_column, last_column, fine.shape_zx[1])):
        origin = inputs[f"origin_{axis}_m"] + first * inputs[f"spacing_{axis}_m"]
        expected_last = origin + (last - first - 1) * inputs[f"spacing_{axis}_m"]
        actual_last = getattr(fine, f"origin_{axis}_m") + (size - 1) * getattr(fine, f"spacing_{axis}_m")
        ratio = inputs[f"spacing_{axis}_m"] / getattr(fine, f"spacing_{axis}_m")
        if (not math.isclose(origin, getattr(fine, f"origin_{axis}_m"), abs_tol=1e-8, rel_tol=0) or
                not math.isclose(expected_last, actual_last, abs_tol=1e-8, rel_tol=0) or
                not math.isclose(ratio, round(ratio), abs_tol=1e-8, rel_tol=0) or ratio < 1):
            raise ValueError("fine grid must exactly cover domain bounding grid at integer refinement")
        axes.append(first + np.floor(np.arange(size) / ratio + .5).astype(np.int64))
    sample = np.ix_(*axes)
    expected_domain = inputs["domain_labels"][sample] == record["domain_id"]
    protected = inputs["protected_mask"][sample]
    legal = np.zeros(inputs["height_m"].shape, bool)
    for domain_id, land_cell, _ in inputs["coastal_outlets"]:
        if domain_id == record["domain_id"]:
            legal.flat[land_cell] = True
    return expected_domain, protected, legal[sample] & expected_domain


def bind_surface_domain_fine(candidate, domain_id, spacing_x_m, spacing_z_m):
    """Derive bound fine masks, without selecting physical recipes or preparing terrain."""
    record = next((item for item in candidate["domains"] if item["domain_id"] == domain_id), None)
    if record is None or record["status"] != "routed":
        raise ValueError("fine binding requires a fully routed domain")
    inputs = candidate["inputs"]
    first_row, last_row, first_column, last_column = record["bounds_zx"]
    sizes = []
    for length, coarse, fine_spacing in ((last_row - first_row, inputs["spacing_z_m"], spacing_z_m),
                                         (last_column - first_column, inputs["spacing_x_m"], spacing_x_m)):
        if isinstance(fine_spacing, bool) or not math.isfinite(fine_spacing) or fine_spacing <= 0:
            raise ValueError("invalid explicit fine spacing")
        ratio = coarse / fine_spacing
        if ratio < 1 or not math.isclose(ratio, round(ratio), abs_tol=1e-8):
            raise ValueError("integer refinement required")
        sizes.append((length - 1) * round(ratio) + 1)
    shape = tuple(sizes)
    if math.prod(shape) > 1000000:
        raise ValueError("fine shape exceeds existing fine grid bound")
    empty = np.zeros(shape, bool)
    stub = FineGrid(inputs["origin_x_m"] + first_column * inputs["spacing_x_m"],
        inputs["origin_z_m"] + first_row * inputs["spacing_z_m"], spacing_x_m, spacing_z_m,
        shape, empty, empty, empty)
    domain, protected, legal = _fine_binding(candidate, record, stub)
    return replace(stub, domain_mask=domain, protected_mask=protected, legal_outlet_mask=legal & ~protected)


def _configuration_record(config):
    return {name: ({key: _plain(value) for key, value in config.fine.__dict__.items()} if name == "fine" else
                  config.outlet_stage_m if name == "outlet_stage_m" else asdict(getattr(config, name)))
            for name in config.__dict__}


def _check_fine(candidate, record, fine):
    domain, protected, legal = _fine_binding(candidate, record, fine)
    if (not np.array_equal(domain, fine.domain_mask) or not np.array_equal(protected, fine.protected_mask) or
            not np.array_equal(legal & ~fine.protected_mask, fine.legal_outlet_mask)):
        raise ValueError("fine/domain/protection/coast masks disagree with complete coarse declaration")


def _config_from_record(record):
    kinds = {"channel_recipe": ChannelRecipe, "section_recipe": SectionRecipe, "stage_recipe": StageRecipe,
        "inundation_recipe": InundationRecipe, "budget": SurfaceNetworkBudget, "network_recipe": NetworkValleyRecipe,
        "valley_recipe": ValleyGeometryRecipe, "reroute_recipe": RerouteRecipe, "recovery_recipe": RecoveryRecipe}
    values = {name: kind(**record[name]) for name, kind in kinds.items()}
    fine = _plain(record["fine"])
    fine["shape_zx"] = tuple(fine["shape_zx"])
    return DomainFineConfiguration(FineGrid(**fine), record["outlet_stage_m"], **values)


def _prepared_gate(candidate, record, config, recovery, *, saved_support=None):
    _check_fine(candidate, record, config.fine)
    arrays = _payload(recovery)
    if saved_support is None:
        _proof_gate(recovery, arrays)
    else:
        from terrain_pipeline.surface_fine_mosaic import _static_proof
        _static_proof(recovery, saved_support)
    window, domain, receiver, order, outlets, discharge = _domain_arrays(candidate, record)
    original = recovery["inputs"]["plan"]["arrays"]
    if any(not np.array_equal(original[name], expected) for name, expected in
           (("source_height_m", candidate["inputs"]["height_m"][window]), ("receiver", receiver),
            ("order", order), ("outlet_mask", outlets), ("discharge_m3_s", discharge))):
        raise ValueError("fine recovery source differs from complete coarse route/Q/H0")
    fine_inputs = recovery["inputs"]
    config_record = _configuration_record(config)
    for name in config_record:
        if name not in ("channel_recipe", "recovery_recipe") and _hash(config_record[name]) != _hash(fine_inputs[name]):
            raise ValueError("fine recovery changed original configuration or physical budget")
    params = recovery["inputs"]["plan"]["identity"]["parameters"]
    if any(params[name] != value for name, value in asdict(config.channel_recipe).items()):
        raise ValueError("channel recipe changed")
    inputs = candidate["inputs"]
    first_row, _, first_column, _ = record["bounds_zx"]
    expected_params = {"spacing_x_m": inputs["spacing_x_m"], "spacing_z_m": inputs["spacing_z_m"],
        "origin_x_m": inputs["origin_x_m"] + first_column * inputs["spacing_x_m"],
        "origin_z_m": inputs["origin_z_m"] + first_row * inputs["spacing_z_m"],
        "sea_level_elevation_m": inputs["sea_level_elevation_m"],
        "source_identity": candidate["identity_sha256"] + ":domain:" + str(record["domain_id"])}
    if any(params[name] != value for name, value in expected_params.items()):
        raise ValueError("fine recovery source coordinates, sea level or source identity changed")
    final = recovery["final_plan"]["arrays"]
    allowed = domain & ~fine_inputs["coarse_protected"]
    for cell in np.flatnonzero(domain):
        target = int(final["receiver"][cell])
        if ((target < 0 and receiver[cell] != -1) or
                (target >= 0 and not _edge_ok(int(cell), target, domain.shape, allowed))):
            raise ValueError("recovered route crosses domain/protection corner or changes legal coast terminals")


def evaluate_surface_domains(candidate, configurations, *, cancel=None):
    """Explicit channel planning and bounded recovery, after joint resource preflight."""
    validate_surface_domains(candidate, allow_unprepared=True)
    if candidate["kind"] != "plan":
        raise ValueError("explicit preparation requires a domain plan")
    resources = SurfaceDomainResources(**candidate["inputs"]["resources"])
    ids = [record["domain_id"] for record in candidate["domains"]]
    if (not isinstance(configurations, Mapping) or set(configurations) != set(ids) or
            any(type(key) is not int or not isinstance(value, DomainFineConfiguration)
                for key, value in configurations.items())):
        raise ValueError("every land domain needs explicit fine configuration; no omitted domains")
    configs = {str(key): _configuration_record(value) for key, value in sorted(configurations.items())}
    entries = [{"domain_id": domain_id, "status": "pending", "reason": None, "recovery": None,
                "charged_coarse_cells": 0, "charged_fine_cells": 0} for domain_id in ids]
    usage = {"coarse_work_cells": 0, "fine_cells": 0, "fine_work_cells": 0, "attempts": 0}
    failures = list(candidate["failures"])
    result = {"algorithm_version": VERSION, "kind": "evaluation", "status": "diagnostic",
        "candidate": candidate, "configurations": configs, "domains": entries, "usage": usage, "failures": failures}
    if failures:
        if _bytes(result) > resources.max_retained_bytes:
            raise ValueError("retained diagnostic evidence resource limit")
        return _seal(result)
    sizes = []
    try:
        for record in candidate["domains"]:
            config = configurations[record["domain_id"]]
            _check_fine(candidate, record, config.fine)
            bounds = record["bounds_zx"]
            coarse_count = (bounds[1] - bounds[0]) * (bounds[3] - bounds[2])
            fine_count = math.prod(config.fine.shape_zx)
            if (coarse_count > config.recovery_recipe.max_coarse_cells or
                    fine_count > config.recovery_recipe.max_fine_cells or
                    fine_count > config.recovery_recipe.max_total_fine_cells or
                    coarse_count * 1024 + fine_count * 512 > config.recovery_recipe.max_working_bytes):
                raise ValueError("original per-domain recovery resource preflight")
            sizes.append((coarse_count, fine_count))
        total_coarse, total_fine = map(sum, zip(*sizes)) if sizes else (0, 0)
        if (total_coarse > resources.max_coarse_work_cells or total_fine > resources.max_fine_cells or
                total_fine > resources.max_fine_work_cells or len(ids) > resources.max_attempts or
                _bytes(result) * 2 + total_coarse * 2048 + total_fine * 1024 > resources.max_retained_bytes):
            raise ValueError("shared resource preflight: coarse/fine/attempt/retained limit")
    except ValueError as error:
        failures.append(str(error))
        if _bytes(result) > resources.max_retained_bytes:
            raise ValueError("retained resource preflight diagnostic too large")
        return _seal(result)
    for index, (record, entry) in enumerate(zip(candidate["domains"], entries)):
        if cancel is not None and cancel():
            failures.append("cancelled")
            break
        config = configurations[record["domain_id"]]
        coarse_count, fine_count = sizes[index]
        reserved_attempts = len(ids) - index - 1
        reserved_fine = sum(size[1] for size in sizes[index + 1:])
        attempts_left = resources.max_attempts - usage["attempts"] - reserved_attempts
        fine_left = resources.max_fine_work_cells - usage["fine_work_cells"] - reserved_fine
        try:
            if attempts_left <= 0 or fine_left < fine_count:
                raise ValueError("shared recovery work exhausted")
            effective = replace(config.recovery_recipe,
                max_attempts=min(config.recovery_recipe.max_attempts, attempts_left),
                max_total_fine_cells=min(config.recovery_recipe.max_total_fine_cells, fine_left))
            entry["charged_coarse_cells"], entry["charged_fine_cells"] = coarse_count, fine_count
            usage["coarse_work_cells"] += coarse_count
            usage["fine_cells"] += fine_count
            window, domain, receiver, order, outlets, discharge = _domain_arrays(candidate, record)
            inputs = candidate["inputs"]
            first_row, _, first_column, _ = record["bounds_zx"]
            plan = plan_channel(inputs["height_m"][window], receiver, order, outlets, discharge,
                inputs["spacing_x_m"], inputs["spacing_z_m"],
                inputs["origin_x_m"] + first_column * inputs["spacing_x_m"],
                inputs["origin_z_m"] + first_row * inputs["spacing_z_m"],
                inputs["sea_level_elevation_m"], candidate["identity_sha256"] + ":domain:" + str(record["domain_id"]),
                config.channel_recipe)
            recovery = recover_surface_network(plan, domain, inputs["protected_mask"][window], config.fine,
                config.outlet_stage_m, config.section_recipe, config.stage_recipe, config.inundation_recipe,
                config.budget, config.network_recipe, config.valley_recipe, config.reroute_recipe, effective)
            usage["attempts"] += len(recovery["attempts"])
            usage["fine_work_cells"] += recovery["summary"]["total_fine_cells_evaluated"]
            entry["recovery"] = recovery
            if recovery["accepted"]:
                _prepared_gate(candidate, record, config, recovery)
                entry["status"] = "prepared"
            else:
                entry.update(status="diagnostic", reason="actual_fine_recovery_" + recovery["status"])
        except ValueError as error:
            entry.update(status="diagnostic", reason=str(error))
        if entry["status"] != "prepared":
            failures.append("domain_" + str(record["domain_id"]) + "_not_prepared")
    if not failures and (not candidate["inputs"]["boundary_complete"] or candidate["inputs"]["scope"] != "complete_grid"):
        failures.append("unverified_or_subdomain_boundary_not_system_prepared")
        result["status"] = "candidate"
    elif not failures and entries:
        result["status"] = "prepared"
    if _bytes(result) > resources.max_retained_bytes:
        raise ValueError("retained result resource limit")
    return _seal(result)


def _validate_plan(result):
    stored = result["inputs"]
    resources = SurfaceDomainResources(**stored["resources"])
    normalized = _normalize_inputs(**{name: value for name, value in _plain(stored).items() if name != "resources"},
                                   resources=resources)
    if _hash(normalized) != _hash(stored):
        raise ValueError("noncanonical domain inputs")
    _coast_gate(stored)
    failures = _declaration_failures(stored)
    if any(reason not in result["failures"] for reason in failures):
        raise ValueError("complete-land declaration failure concealed")
    labels, arrays = stored["domain_labels"], result["arrays"]
    expected_ids = sorted(int(value) for value in np.unique(labels[labels > 0]))
    if [item["domain_id"] for item in result["domains"]] != expected_ids:
        raise ValueError("missing or duplicate land domain")
    receiver, order = arrays["receiver"], arrays["order"]
    if (receiver.shape != (labels.size,) or receiver.dtype != np.int64 or order.ndim != 1 or order.dtype != np.int64 or
            set(arrays) != {"receiver", "order", "working_fill_m", "local_discharge_m3_s", "discharge_m3_s"}):
        raise ValueError("invalid masked route arrays")
    for name in ("working_fill_m", "local_discharge_m3_s", "discharge_m3_s"):
        if arrays[name].shape != labels.shape or arrays[name].dtype != np.float64:
            raise ValueError("invalid coarse field shape/dtype")
    local = stored["runoff_m_s"] * stored["spacing_x_m"] * stored["spacing_z_m"] + stored["external_q_m3_s"]
    if not np.array_equal(local, arrays["local_discharge_m3_s"]):
        raise ValueError("local runoff area or external Q changed")
    routed = np.zeros(labels.shape, bool)
    allowed_by_id = {}
    for record in result["domains"]:
        rows, columns = np.nonzero(labels == record["domain_id"])
        bounds = [int(rows.min()), int(rows.max()) + 1, int(columns.min()), int(columns.max()) + 1]
        for axis in (0, 2):
            if bounds[axis + 1] - bounds[axis] < 2:
                bounds[axis] = max(0, bounds[axis] - 1)
                bounds[axis + 1] = min(labels.shape[axis // 2], bounds[axis] + 2)
        if list(record["bounds_zx"]) != bounds:
            raise ValueError("domain bounding grid changed")
        if record["status"] == "routed":
            domain = labels == record["domain_id"]
            routed |= domain
            allowed_by_id[record["domain_id"]] = domain & stored["valid_mask"] & ~stored["protected_mask"]
        elif record["status"] not in ("pending", "diagnostic"):
            raise ValueError("invalid route domain state")
    cells = np.flatnonzero(routed)
    if (not np.array_equal(np.sort(order), cells) or np.any(receiver[~routed.ravel()] != -2) or
            np.any(~np.isnan(arrays["working_fill_m"][~routed])) or np.any(arrays["discharge_m3_s"][~routed] != 0)):
        raise ValueError("masked coverage or dormant cells disagree")
    rank = np.full(labels.size, -1, np.int64)
    rank[order] = np.arange(len(order))
    working = arrays["working_fill_m"].ravel()
    discharge = arrays["discharge_m3_s"].ravel()
    accumulated = np.where(routed, local, 0.).ravel()
    legal = {entry[1] for entry in stored["coastal_outlets"]}
    for cell in order:
        target = int(receiver[cell])
        allowed = allowed_by_id[int(labels.flat[cell])]
        if not allowed.flat[cell] or not math.isfinite(working[cell]):
            raise ValueError("invalid routed land")
        if target == -1:
            if int(cell) not in legal or working[cell] != stored["height_m"].flat[cell]:
                raise ValueError("false coast terminal")
        elif (target < 0 or target >= labels.size or rank[target] < 0 or rank[target] >= rank[cell] or
              not _edge_ok(int(cell), target, labels.shape, allowed) or
              working[cell] != max(stored["height_m"].flat[cell], working[target])):
            raise ValueError("cross-domain/corner/cyclic route or separate working fill mismatch")
        if int(cell) not in legal:
            for neighbor in _neighbors(int(cell), labels.shape, allowed):
                if working[cell] > max(stored["height_m"].flat[cell], working[neighbor]):
                    raise ValueError("working fill is not a minimal supported flood")
    for cell in reversed(order):
        target = int(receiver[cell])
        if target >= 0:
            accumulated[target] += accumulated[cell]
    if not np.isfinite(discharge).all() or not np.array_equal(discharge, accumulated):
        raise ValueError("domain discharge is not conservative")
    transfers = [{"domain_id": domain_id, "land_cell": land_cell, "ocean_cell": ocean_cell,
                  "discharge_m3_s": float(discharge[land_cell])}
                 for domain_id, land_cell, ocean_cell in stored["coastal_outlets"]]
    if (_hash(transfers) != _hash(result["coastal_transfers"]) or
            result["unrouted_local_discharge_m3_s"] != float(local.ravel()[receiver == -2].sum())):
        raise ValueError("land-ocean transfer or unprocessed source ledger changed")
    complete = np.array_equal(routed, stored["land_mask"])
    if result["status"] == "candidate" and (not complete or result["failures"] or
            labels.size > resources.max_coarse_cells or len(expected_ids) > resources.max_domains):
        raise ValueError("incomplete or resource-limited routing cannot be successful candidate")
    if result["status"] not in ("candidate", "diagnostic") or (result["status"] == "diagnostic" and not result["failures"]):
        raise ValueError("invalid plan state")


def validate_surface_domains(result, *, allow_unprepared=False, saved_support=None):
    """Static topology/geometry/budget gates; never reroute, plan or recover."""
    try:
        record = {key: value for key, value in result.items() if key != "identity_sha256"}
        if result["algorithm_version"] != VERSION or _hash(record) != result["identity_sha256"]:
            raise ValueError("domain bundle identity mismatch")
        if result["kind"] == "plan":
            if saved_support is not None:
                raise ValueError("saved support is only valid for domain evaluations")
            _validate_plan(result)
            resources = result["inputs"]["resources"]
        elif result["kind"] == "evaluation":
            candidate = result["candidate"]
            validate_surface_domains(candidate, allow_unprepared=True)
            ids = [item["domain_id"] for item in candidate["domains"]]
            if saved_support is not None:
                expected_proofs = {entry["recovery"]["identity_sha256"] for entry in result["domains"]
                                   if entry["status"] == "prepared" and entry["recovery"] is not None}
                if not hasattr(saved_support, "keys") or set(saved_support) != expected_proofs:
                    raise ValueError("saved support must bind every prepared recovery exactly")
            if ([item["domain_id"] for item in result["domains"]] != ids or
                    set(result["configurations"]) != {str(value) for value in ids}):
                raise ValueError("fine preparation omits declared land domain")
            usage = {"coarse_work_cells": 0, "fine_cells": 0, "fine_work_cells": 0, "attempts": 0}
            for index, (domain, entry) in enumerate(zip(candidate["domains"], result["domains"])):
                config = _config_from_record(result["configurations"][str(domain["domain_id"])])
                recovery = entry["recovery"]
                bounds = domain["bounds_zx"]
                coarse_count = (bounds[1] - bounds[0]) * (bounds[3] - bounds[2])
                fine_count = math.prod(config.fine.shape_zx)
                charged = (entry["charged_coarse_cells"], entry["charged_fine_cells"])
                if (charged not in ((0, 0), (coarse_count, fine_count)) or
                        (recovery is not None and charged != (coarse_count, fine_count)) or
                        (entry["status"] == "pending" and charged != (0, 0))):
                    raise ValueError("charged coarse/fine sizes differ from actual domain/fine grids")
                if recovery is not None:
                    reserved_attempts = len(ids) - index - 1
                    reserved_fine = sum(math.prod(result["configurations"][str(value)]["fine"]["shape_zx"])
                                        for value in ids[index + 1:])
                    resources = candidate["inputs"]["resources"]
                    effective = replace(config.recovery_recipe,
                        max_attempts=min(config.recovery_recipe.max_attempts,
                            resources["max_attempts"] - usage["attempts"] - reserved_attempts),
                        max_total_fine_cells=min(config.recovery_recipe.max_total_fine_cells,
                            resources["max_fine_work_cells"] - usage["fine_work_cells"] - reserved_fine))
                    if (_hash(asdict(effective)) != _hash(recovery["inputs"]["recovery_recipe"]) or
                            len(recovery["attempts"]) > effective.max_attempts or
                            recovery["summary"]["attempt_count"] != len(recovery["attempts"]) or
                            recovery["summary"]["total_fine_cells_evaluated"] != len(recovery["attempts"]) * fine_count or
                            recovery["summary"]["total_fine_cells_evaluated"] > effective.max_total_fine_cells):
                        raise ValueError("original/effective recovery attempt or fine work bounds changed")
                usage["coarse_work_cells"] += entry["charged_coarse_cells"]
                usage["fine_cells"] += entry["charged_fine_cells"]
                if recovery is not None:
                    usage["attempts"] += len(recovery["attempts"])
                    usage["fine_work_cells"] += recovery["summary"]["total_fine_cells_evaluated"]
                    body = {key: value for key, value in recovery.items() if key != "identity_sha256"}
                    if _hash(body) != recovery["identity_sha256"]:
                        raise ValueError("recovery proof identity mismatch")
                if entry["status"] == "prepared":
                    if domain["status"] != "routed" or recovery is None:
                        raise ValueError("prepared domain lacks complete route/recovery")
                    support = None if saved_support is None else saved_support[recovery["identity_sha256"]]
                    if saved_support is not None and (not hasattr(support, "keys") or set(support) != {"indices", "weights"}):
                        raise ValueError("explicit saved proof indices/weights required")
                    _prepared_gate(candidate, domain, config, _plain(recovery), saved_support=support)
                elif entry["status"] not in ("pending", "diagnostic"):
                    raise ValueError("invalid fine domain state")
            if _hash(usage) != _hash(result["usage"]):
                raise ValueError("shared resource ledger disagrees")
            resources = candidate["inputs"]["resources"]
            if any(type(value) is not int or value < 0 or value > resources["max_" + name]
                   for name, value in usage.items()):
                raise ValueError("shared work exceeds resource cap")
            prepared = all(item["status"] == "prepared" for item in result["domains"]) and bool(ids)
            if result["status"] == "prepared" and (not prepared or result["failures"] or
                    candidate["status"] != "candidate" or not candidate["inputs"]["boundary_complete"] or
                    candidate["inputs"]["scope"] != "complete_grid"):
                raise ValueError("prepared publication conceals incomplete domains/boundary")
            if result["status"] not in ("candidate", "diagnostic", "prepared"):
                raise ValueError("invalid domain product state")
        else:
            raise ValueError("invalid domain bundle kind")
        if _bytes(record) > resources["max_retained_bytes"]:
            raise ValueError("retained bundle exceeds original resource cap")
        if not allow_unprepared and result["status"] != "prepared":
            raise ValueError("candidate/diagnostic is not a prepared complete-land product")
        return result
    except (KeyError, TypeError, IndexError, OverflowError, AttributeError) as error:
        raise ValueError("invalid surface domain bundle") from error


def save_surface_domains(result, path):
    """Atomic self-contained NPZ; explicit candidate/diagnostic allowed, no overwrite."""
    validate_surface_domains(result, allow_unprepared=True)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    arrays = {}
    tree = _encode(result, arrays)
    manifest = json.dumps({"format_version": 1, "tree": tree, "tree_sha256": digest(tree)}, ensure_ascii=False, allow_nan=False)
    if sum(array.nbytes for array in arrays.values()) + len(manifest.encode("utf8")) > MAX_BYTES:
        raise ValueError("domain bundle exceeds hard storage bound")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".npz", delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=manifest, **arrays)
        load_surface_domains(temporary, allow_unprepared=True)
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate domain manifest JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("nonfinite domain JSON constant: " + value)


def load_surface_domains(path, *, allow_unprepared=False):
    """Bounded read and static semantic validation, never routing/recovery."""
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if (len(entries) > 8192 or sum(item.file_size for item in entries) > MAX_BYTES or
                    len({item.filename for item in entries}) != len(entries)):
                raise ValueError("duplicate or excessive domain archive members")
            for entry in entries:
                if not entry.filename.endswith(".npy") or "/" in entry.filename or "\\" in entry.filename:
                    raise ValueError("invalid domain archive member")
                with archive.open(entry) as stream:
                    version = np.lib.format.read_magic(stream)
                    if version == (1, 0):
                        shape, _, dtype = np.lib.format.read_array_header_1_0(stream)
                    elif version == (2, 0):
                        shape, _, dtype = np.lib.format.read_array_header_2_0(stream)
                    else:
                        raise ValueError("unsupported domain array format")
                    size = math.prod(shape) * dtype.itemsize
                    if dtype.hasobject or size > MAX_BYTES or size != entry.file_size - stream.tell():
                        raise ValueError("invalid or excessive domain array header")
                    if entry.filename == "manifest.npy" and (shape != () or dtype.kind != "U" or size > 16 * 1024 * 1024):
                        raise ValueError("domain manifest must be bounded Unicode scalar")
        with np.load(path, allow_pickle=False) as archive:
            manifest = json.loads(str(archive["manifest"].item()), object_pairs_hook=_pairs, parse_constant=_constant)
            if manifest["format_version"] != 1 or digest(manifest["tree"]) != manifest["tree_sha256"]:
                raise ValueError("domain manifest hash mismatch")
            used = {"manifest"}

            def decode(value):
                if isinstance(value, dict) and "$array" in value:
                    key = value["$array"]
                    if key in used or set(value) != {"$array", "sha256", "shape", "dtype"}:
                        raise ValueError("invalid domain array reference")
                    used.add(key)
                    array = archive[key]
                    if (array.dtype.kind not in "bifu" or array.dtype.str != value["dtype"] or
                            list(array.shape) != value["shape"] or array_hash(array) != value["sha256"]):
                        raise ValueError("domain array hash/shape mismatch")
                    return _freeze(array)
                if isinstance(value, dict):
                    return {key: decode(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [decode(child) for child in value]
                return value

            result = decode(manifest["tree"])
            if used != set(archive.files):
                raise ValueError("unexpected domain archive arrays")
        validate_surface_domains(result, allow_unprepared=allow_unprepared)
        return _freeze(result)
    except (OSError, KeyError, TypeError, RecursionError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError("invalid domain bundle") from error


def query_surface_domain(result, domain_id, z_slice, x_slice):
    """Read immutable fine windows only from a completely prepared multi-domain product."""
    validate_surface_domains(result)
    if result["status"] != "prepared" or result["kind"] != "evaluation":
        raise ValueError("only complete prepared domain products are queryable")
    entry = next((item for item in result["domains"] if item["domain_id"] == domain_id), None)
    if entry is None or entry["status"] != "prepared":
        raise ValueError("unknown or unprepared domain")
    arrays = _payload(_plain(entry["recovery"]))
    names = ("source_surface_m", "valley_surface_m", "final_surface_m", "water_surface_m", "wet_mask",
             "domain_mask", "protected_mask", "legal_outlet_mask", "total_cut_m")
    return _freeze({name: arrays[name][z_slice, x_slice] for name in names})
