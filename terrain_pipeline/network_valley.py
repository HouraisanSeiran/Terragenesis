"""Explicitly opt-in, complete active-D8 valley planning on a metric grid."""

from dataclasses import asdict, dataclass
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest
from terrain_pipeline.metric_channel_plan import ChannelRecipe, PLAN_VERSION, plan_channel
from terrain_pipeline.valley_geometry import (
    ValleyGeometryRecipe, _prepare_valley_cut, _rasterize_valley_edges,
)


VERSION = "network-valley-v1"
PLANNING_VERSION = "network-valley-planning-v1"


@dataclass(frozen=True)
class NetworkValleyRecipe:
    """Widths are nominal channel widths times a ratio, bounded in metres."""

    width_multiplier: float
    min_width_m: float
    max_width_m: float
    min_floor_slope_m_per_m: float

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.min_width_m > self.max_width_m:
            raise ValueError("valley width limits must be ordered")


def _array_digest(arrays):
    return digest({name: {"sha256": array_hash(value), "shape": list(value.shape),
                          "dtype": value.dtype.str} for name, value in arrays.items()})


def _immutable(value):
    contiguous = np.ascontiguousarray(value)
    return np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)


def _freeze_plan(plan):
    plan["arrays"] = {name: _immutable(value) for name, value in plan["arrays"].items()}
    return plan


def _validated_source_plan(plan, recipe=None):
    """Recompute every derived field: legacy plan identities hash only sources."""
    try:
        identity = ArtifactIdentity(**plan["identity"])
        params = identity.record()["parameters"]
        source_recipe = ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__})
        if (identity.algorithm != "metric-channel-plan" or identity.algorithm_version != PLAN_VERSION or
                identity.backend != "Terragenesis" or identity.sha256 != plan["identity_sha256"] or
                plan["status"] != "diagnostic_not_publishable"):
            raise ValueError("invalid source plan identity")
        if recipe is not None and asdict(source_recipe) != asdict(recipe):
            raise ValueError("channel recipe mismatch with source plan")
        arrays = plan["arrays"]
        expected = plan_channel(arrays["source_height_m"], arrays["receiver"], arrays["order"],
            arrays["outlet_mask"], arrays["discharge_m3_s"], params["spacing_x_m"], params["spacing_z_m"],
            params["origin_x_m"], params["origin_z_m"], params["sea_level_elevation_m"],
            params["source_identity"], source_recipe)
        if expected["identity_sha256"] != identity.sha256 or set(arrays) != set(expected["arrays"]):
            raise ValueError("source plan inputs differ from identity")
        for name, expected_array in expected["arrays"].items():
            actual = np.asarray(arrays[name])
            if (actual.shape != expected_array.shape or actual.dtype != expected_array.dtype or
                    not np.array_equal(actual, expected_array)):
                raise ValueError(f"source plan field differs from recomputed plan: {name}")
        return _freeze_plan(expected)
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError("invalid source plan") from error


def _plan_nodes(plan, recipe, channel_recipe):
    arrays = plan["arrays"]
    params = plan["identity"]["parameters"]
    source = arrays["source_height_m"]
    active = arrays["channel_mask"].ravel()
    receiver = arrays["receiver"]
    donors = np.flatnonzero(active & (receiver >= 0))
    if not len(donors):
        raise ValueError("network valley requires at least one active D8 edge")
    edges = np.column_stack((donors, receiver[donors])).astype(np.int64)
    columns = source.shape[1]
    delta_x = (edges[:, 1] % columns - edges[:, 0] % columns) * params["spacing_x_m"]
    delta_z = (edges[:, 1] // columns - edges[:, 0] // columns) * params["spacing_z_m"]
    lengths = np.hypot(delta_x, delta_z)
    floor = source.ravel().copy()
    depth = arrays["nominal_depth_m"].ravel()
    for donor in arrays["order"][::-1]:
        target = receiver[donor]
        if target < 0 or not active[donor]:
            continue
        length = math.hypot((target % columns - donor % columns) * params["spacing_x_m"],
                            (target // columns - donor // columns) * params["spacing_z_m"])
        floor_limit = floor[donor] - recipe.min_floor_slope_m_per_m * length
        bed_limit = (floor[donor] - depth[donor] + depth[target] -
                     channel_recipe.min_bed_slope_m_per_m * length)
        floor[target] = min(floor[target], floor_limit, bed_limit)
    width = np.zeros(source.shape, dtype=np.float64)
    with np.errstate(over="ignore", invalid="ignore"):
        scaled = arrays["nominal_width_m"].ravel()[active] * recipe.width_multiplier
    if not np.isfinite(scaled).all() or not np.isfinite(floor).all() or not np.isfinite(lengths).all():
        raise ValueError("network valley geometry overflows")
    width.ravel()[active] = np.clip(scaled, recipe.min_width_m, recipe.max_width_m)
    return {"floor_elevation_m": floor.reshape(source.shape), "width_m": width,
            "active_mask": active.reshape(source.shape).copy(), "active_edges": edges,
            "edge_length_m": lengths}


def prepare_network_valley(plan, domain_mask, protected_mask, network_recipe,
                           valley_recipe, channel_recipe):
    """Return a coarse diagnostic compatible with evaluate_fine_valley_ledger.

    Every active donor/receiver segment is rasterized independently in its local
    bounding box. Node floors start at H0 and propagate both floor and nominal-bed
    slope constraints upstream to downstream, sharing a single floor and width at
    each confluence. The cosine cut envelope is a union, not a summed excavation.
    Budget, domain and protection failures remain diagnostics, never clipped passes.
    No outlet legality is inferred here; only fine joint acceptance can publish.
    """
    if (not isinstance(network_recipe, NetworkValleyRecipe) or
            not isinstance(valley_recipe, ValleyGeometryRecipe) or
            not isinstance(channel_recipe, ChannelRecipe)):
        raise ValueError("network, valley and channel recipes required")
    source_plan = _validated_source_plan(plan, channel_recipe)
    source = source_plan["arrays"]["source_height_m"]
    domain = np.asarray(domain_mask)
    protected = np.asarray(protected_mask)
    if (domain.shape != source.shape or protected.shape != source.shape or
            domain.dtype != bool or protected.dtype != bool):
        raise ValueError("domain and protected masks must be matching boolean grids")
    domain = _immutable(domain)
    protected = _immutable(protected)
    network = _plan_nodes(source_plan, network_recipe, channel_recipe)
    params = source_plan["identity"]["parameters"]
    edges = network["active_edges"]
    points = np.stack((params["origin_x_m"] + (edges % source.shape[1]) * params["spacing_x_m"],
                       params["origin_z_m"] + (edges // source.shape[1]) * params["spacing_z_m"]), axis=2)
    if not np.isfinite(points).all():
        raise ValueError("network world coordinates overflow")
    requested = _rasterize_valley_edges(source, params, points,
        network["floor_elevation_m"].ravel()[edges], network["width_m"].ravel()[edges], local_bounds=True)
    if not np.isfinite(requested).all():
        raise ValueError("network valley cut overflows")
    network["domain_mask"] = domain
    network["protected_mask"] = protected
    network = {name: _immutable(value) for name, value in network.items()}
    planning = ArtifactIdentity("Terragenesis", "network-valley-planning", PLANNING_VERSION, 0,
        {"network_recipe": asdict(network_recipe), "valley_recipe": asdict(valley_recipe),
         "channel_recipe": asdict(channel_recipe), "source_plan_sha256": source_plan["identity_sha256"],
         "source_plan_identity": source_plan["identity"],
         "source_arrays_sha256": _array_digest(source_plan["arrays"]),
         "network_sha256": _array_digest(network), "requested_cut_sha256": array_hash(requested)})
    arrays, replanned, summary = _prepare_valley_cut(source_plan, requested, domain, protected,
        valley_recipe, channel_recipe, planning.sha256)
    failures = summary["failures"]
    failures["total_area"] = summary["total_cut_area_m2"] > valley_recipe.max_total_cut_area_m2 + 1e-9
    failures["active_domain"] = bool(np.any(network["active_mask"] & ~domain))
    failures["active_protection"] = bool(np.any(network["active_mask"] & protected))
    summary["geometry_feasible"] = not any(failures.values())
    arrays = {name: _immutable(value) for name, value in arrays.items()}
    replanned = _freeze_plan(replanned)
    identity = ArtifactIdentity("Terragenesis", "network-valley", VERSION, 0,
        {**asdict(valley_recipe), "source_plan_sha256": source_plan["identity_sha256"],
         "planning_identity_sha256": planning.sha256, "replanned_sha256": replanned["identity_sha256"],
         "network_sha256": _array_digest(network), "arrays_sha256": _array_digest(arrays),
         "replanned_arrays_sha256": _array_digest(replanned["arrays"]), "summary_sha256": digest(summary)})
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "planning_identity": planning.record(), "planning_identity_sha256": planning.sha256,
            "status": "diagnostic_not_publishable", "arrays": arrays, "network": network,
            "replanned_plan": replanned, "summary": summary}


def validate_network_valley(result):
    """Reject altered automatic geometry, planning provenance or replanned fields."""
    try:
        identity = ArtifactIdentity(**result["identity"])
        planning = ArtifactIdentity(**result["planning_identity"])
        params = identity.record()["parameters"]
        planned = planning.record()["parameters"]
        replanned = _validated_source_plan(result["replanned_plan"])
        source_identity = ArtifactIdentity(**planned["source_plan_identity"])
        source_params = source_identity.record()["parameters"]
        channel_recipe = ChannelRecipe(**planned["channel_recipe"])
        NetworkValleyRecipe(**planned["network_recipe"])
        ValleyGeometryRecipe(**planned["valley_recipe"])
        original = plan_channel(result["arrays"]["source_height_m"], replanned["arrays"]["receiver"],
            replanned["arrays"]["order"], replanned["arrays"]["outlet_mask"],
            replanned["arrays"]["discharge_m3_s"], source_params["spacing_x_m"], source_params["spacing_z_m"],
            source_params["origin_x_m"], source_params["origin_z_m"], source_params["sea_level_elevation_m"],
            source_params["source_identity"], channel_recipe)
        if (identity.algorithm != "network-valley" or identity.algorithm_version != VERSION or
                identity.sha256 != result["identity_sha256"] or
                planning.algorithm != "network-valley-planning" or planning.algorithm_version != PLANNING_VERSION or
                planning.sha256 != result["planning_identity_sha256"] or
                source_identity.sha256 != planned["source_plan_sha256"] or
                source_identity.sha256 != params["source_plan_sha256"] or
                original["identity_sha256"] != source_identity.sha256 or
                _array_digest(original["arrays"]) != planned["source_arrays_sha256"] or
                any(params[name] != value for name, value in planned["valley_recipe"].items()) or
                array_hash(result["arrays"]["valley_cut_m"]) != planned["requested_cut_sha256"] or
                params["planning_identity_sha256"] != planning.sha256 or
                replanned["identity"]["parameters"]["source_identity"] != planning.sha256 or
                params["replanned_sha256"] != replanned["identity_sha256"] or
                params["replanned_arrays_sha256"] != _array_digest(replanned["arrays"]) or
                params["network_sha256"] != _array_digest(result["network"]) or
                planned["network_sha256"] != params["network_sha256"] or
                params["arrays_sha256"] != _array_digest(result["arrays"]) or
                params["summary_sha256"] != digest(result["summary"]) or
                result["status"] != "diagnostic_not_publishable"):
            raise ValueError("network valley identity or arrays mismatch")
        if (not np.array_equal(result["arrays"]["valley_surface_m"], replanned["arrays"]["source_height_m"]) or
                not np.array_equal(result["arrays"]["final_bed_m"], replanned["arrays"]["bounded_bed_m"])):
            raise ValueError("network valley replan source mismatch")
        expected = prepare_network_valley(original, result["network"]["domain_mask"],
            result["network"]["protected_mask"], NetworkValleyRecipe(**planned["network_recipe"]),
            ValleyGeometryRecipe(**planned["valley_recipe"]), channel_recipe)
        if (expected["identity_sha256"] != identity.sha256 or
                expected["planning_identity_sha256"] != planning.sha256):
            raise ValueError("network valley geometry or budget semantics mismatch")
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("invalid network valley result") from error


def save_network_valley(result, path):
    """Atomically save a validated diagnostic bundle, never overwrite or publish."""
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    snapshot = deepcopy(result)
    validate_network_valley(snapshot)
    record = {name: snapshot[name] for name in
              ("identity", "identity_sha256", "planning_identity", "planning_identity_sha256", "status", "summary")}
    record["format_version"] = 1
    record["replanned_plan"] = {name: snapshot["replanned_plan"][name] for name in
                               ("identity", "identity_sha256", "status")}
    payload = {f"{group}__{name}": value for group, arrays in
               (("geometry", snapshot["arrays"]), ("network", snapshot["network"]),
                ("replanned", snapshot["replanned_plan"]["arrays"])) for name, value in arrays.items()}
    record["payload_sha256"] = _array_digest(payload)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent,
                                         prefix=f".{destination.name}-", suffix=".npz", delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(record, sort_keys=True), **payload)
        load_network_valley(temporary)
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_network_valley(path):
    """Load immutable H0/H1/H2, complete network and replan with semantic checks."""
    try:
        with np.load(path, allow_pickle=False) as archive:
            record = json.loads(str(archive["manifest"].item()))
            payload = {name: archive[name].copy() for name in archive.files if name != "manifest"}
        if record["format_version"] != 1 or record["payload_sha256"] != _array_digest(payload):
            raise ValueError("invalid network valley archive format or payload")
        groups = {name: {} for name in ("geometry", "network", "replanned")}
        for key, value in payload.items():
            group, separator, name = key.partition("__")
            if group not in groups or not separator or not name:
                raise ValueError("invalid network valley archive fields")
            groups[group][name] = _immutable(value)
        result = {name: record[name] for name in
                  ("identity", "identity_sha256", "planning_identity", "planning_identity_sha256", "status", "summary")}
        result["arrays"] = groups["geometry"]
        result["network"] = groups["network"]
        result["replanned_plan"] = {**record["replanned_plan"], "arrays": groups["replanned"]}
        validate_network_valley(result)
        return result
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError("invalid network valley archive") from error
