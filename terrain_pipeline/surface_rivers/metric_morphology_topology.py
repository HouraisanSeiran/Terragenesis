"""Candidate-only topology patch contracts for metric morphology events."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
import math

from .metric_morphology_events import MorphologyEvent


SCHEMA = "terragenesis-morphology-topology-patch-v1"
REQUIRED_REVALIDATION_KINDS = frozenset(("topology", "geometry", "hydraulics", "sediment"))


def _sha256(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value):
        raise ValueError(name + " must be a lowercase SHA256")


def _finite_nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + " must be finite")
    if value < 0:
        raise ValueError(name + " must be nonnegative")
    return float(value)


def _edge_ids(values, name):
    if isinstance(values, (str, bytes)):
        raise ValueError(name + " must contain edge IDs")
    try:
        result = tuple(values)
    except TypeError as error:
        raise ValueError(name + " must contain edge IDs") from error
    if any(not isinstance(value, str) or not value for value in result):
        raise ValueError(name + " must contain nonempty edge IDs")
    if len(set(result)) != len(result):
        raise ValueError(name + " contains duplicate edge IDs")
    return result


def _lake_ids(values):
    if isinstance(values, (str, bytes)):
        raise ValueError("retained_lake_ids must contain lake IDs")
    try:
        result = tuple(values)
    except TypeError as error:
        raise ValueError("retained_lake_ids must contain lake IDs") from error
    if any(not isinstance(value, str) or not value for value in result):
        raise ValueError("retained_lake_ids must contain nonempty lake IDs")
    if len(set(result)) != len(result):
        raise ValueError("retained_lake_ids contains duplicate lake IDs")
    return result


def _digest(record):
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class TopologyPatch:
    parent_graph_identity_sha256: str
    event_identity_sha256: str
    active_edge_ids: tuple[str, ...]
    added_edge_ids: tuple[str, ...]
    retired_edge_ids: tuple[str, ...]
    retained_lake_ids: tuple[str, ...]
    water_transfer_m3: float
    sediment_transfer_solid_m3: float
    status: str = "candidate"
    revalidation_required: tuple[str, ...] = (
        "topology", "geometry", "hydraulics", "sediment")

    def __post_init__(self):
        _sha256(self.parent_graph_identity_sha256, "parent graph identity")
        _sha256(self.event_identity_sha256, "event identity")
        active = _edge_ids(self.active_edge_ids, "active_edge_ids")
        added = _edge_ids(self.added_edge_ids, "added_edge_ids")
        retired = _edge_ids(self.retired_edge_ids, "retired_edge_ids")
        lakes = _lake_ids(self.retained_lake_ids)
        if set(added) & set(retired):
            raise ValueError("an edge cannot be added and retired in one patch")
        if set(active) & set(added):
            raise ValueError("an added edge is already active")
        if not set(retired).issubset(active):
            raise ValueError("a retired edge is not active")
        if not isinstance(self.status, str) or self.status != "candidate":
            raise ValueError("topology patch status must be candidate")
        if not isinstance(self.revalidation_required, tuple):
            raise ValueError("revalidation_required must be a tuple")
        if any(not isinstance(value, str) for value in self.revalidation_required):
            raise ValueError("revalidation_required must contain strings")
        if not REQUIRED_REVALIDATION_KINDS.issubset(self.revalidation_required):
            raise ValueError("topology, geometry, hydraulics, and sediment revalidation are required")
        object.__setattr__(self, "active_edge_ids", active)
        object.__setattr__(self, "added_edge_ids", added)
        object.__setattr__(self, "retired_edge_ids", retired)
        object.__setattr__(self, "retained_lake_ids", lakes)
        object.__setattr__(self, "water_transfer_m3",
                           _finite_nonnegative(self.water_transfer_m3, "water_transfer_m3"))
        object.__setattr__(self, "sediment_transfer_solid_m3", _finite_nonnegative(
            self.sediment_transfer_solid_m3, "sediment_transfer_solid_m3"))

    @classmethod
    def from_event(cls, event: MorphologyEvent, active_edge_ids: Iterable[str],
                   retained_lake_ids: Iterable[str] = ()):
        if not isinstance(event, MorphologyEvent):
            raise ValueError("event must be a MorphologyEvent")
        event_identity = event.identity_sha256
        return cls(
            parent_graph_identity_sha256=event.parent_graph_identity_sha256,
            event_identity_sha256=event_identity,
            active_edge_ids=tuple(active_edge_ids),
            added_edge_ids=event.added_edges,
            retired_edge_ids=event.retired_edges,
            retained_lake_ids=tuple(retained_lake_ids),
            water_transfer_m3=event.water_transfer_m3,
            sediment_transfer_solid_m3=event.sediment_transfer_solid_m3,
            revalidation_required=tuple(event.revalidation_required))

    @property
    def identity_sha256(self):
        return _digest(self.to_record(include_identity=False))

    def to_record(self, *, include_identity=True):
        record = {
            "schema": SCHEMA,
            "parent_graph_identity_sha256": self.parent_graph_identity_sha256,
            "event_identity_sha256": self.event_identity_sha256,
            "active_edge_ids": list(self.active_edge_ids),
            "added_edge_ids": list(self.added_edge_ids),
            "retired_edge_ids": list(self.retired_edge_ids),
            "retained_lake_ids": list(self.retained_lake_ids),
            "water_transfer_m3": self.water_transfer_m3,
            "sediment_transfer_solid_m3": self.sediment_transfer_solid_m3,
            "status": self.status,
            "revalidation_required": list(self.revalidation_required),
        }
        if include_identity:
            record["identity_sha256"] = self.identity_sha256
        return record

    @classmethod
    def from_record(cls, record: Mapping):
        if not isinstance(record, Mapping) or record.get("schema") != SCHEMA:
            raise ValueError("invalid topology patch schema")
        expected = record.get("identity_sha256")
        body = dict(record)
        body.pop("identity_sha256", None)
        if expected != _digest(body):
            raise ValueError("topology patch identity mismatch")
        return cls(
            parent_graph_identity_sha256=record["parent_graph_identity_sha256"],
            event_identity_sha256=record["event_identity_sha256"],
            active_edge_ids=tuple(record["active_edge_ids"]),
            added_edge_ids=tuple(record["added_edge_ids"]),
            retired_edge_ids=tuple(record["retired_edge_ids"]),
            retained_lake_ids=tuple(record["retained_lake_ids"]),
            water_transfer_m3=record["water_transfer_m3"],
            sediment_transfer_solid_m3=record["sediment_transfer_solid_m3"],
            status=record["status"],
            revalidation_required=tuple(record["revalidation_required"]))

    def validate_against(self, active_edge_ids: Iterable[str]):
        current = _edge_ids(active_edge_ids, "active_edge_ids")
        if current != self.active_edge_ids:
            raise ValueError("active edge identity does not match topology patch")
        if set(self.added_edge_ids) & set(current):
            raise ValueError("an added edge is already active")
        if not set(self.retired_edge_ids).issubset(current):
            raise ValueError("a retired edge is not active")
        return True


def topology_patch_from_record(record):
    return TopologyPatch.from_record(record)
