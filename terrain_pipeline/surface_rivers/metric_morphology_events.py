"""Immutable event contracts for topology-changing river morphology candidates."""

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType


SCHEMA = "terragenesis-morphology-event-v1"
EVENT_TYPES = ("delta_growth", "cutoff", "bifurcation", "avulsion", "bank_migration",
               "alluvial_fan", "floodplain_inundation")
EVENT_STATUSES = ("candidate", "bounded", "validated")
REVALIDATION_KINDS = ("topology", "geometry", "hydraulics", "sediment", "outlet")
LEDGER_KEYS = ("deposited_solid_m3", "exported_solid_m3", "unresolved_solid_m3",
               "cut_rock_m3", "fill_m3", "porous_deposit_m3")


def _sha(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(name + " must be a lowercase SHA256")


def _finite(value, name, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + " must be finite")
    if nonnegative and value < 0.:
        raise ValueError(name + " must be nonnegative")
    return float(value)


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in sorted(value.items())})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError("event parameters must be JSON-compatible")


def _plain(value):
    if isinstance(value, MappingProxyType):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _digest(record):
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class MorphologyEvent:
    event_id: str
    event_type: str
    parent_graph_identity_sha256: str
    parent_geometry_identity_sha256: str
    affected_edges: tuple[str, ...]
    added_edges: tuple[str, ...]
    retired_edges: tuple[str, ...]
    water_transfer_m3: float
    sediment_transfer_solid_m3: float
    material_ledger: MappingProxyType
    parameters: MappingProxyType
    revalidation_required: tuple[str, ...] = ("topology", "geometry", "hydraulics", "sediment")
    status: str = "candidate"

    def __post_init__(self):
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id required")
        if self.event_type not in EVENT_TYPES:
            raise ValueError("unsupported morphology event type")
        _sha(self.parent_graph_identity_sha256, "parent graph identity")
        _sha(self.parent_geometry_identity_sha256, "parent geometry identity")
        for name in ("affected_edges", "added_edges", "retired_edges"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(value, str) or not value for value in values):
                raise ValueError(name + " must contain nonempty edge IDs")
            if len(set(values)) != len(values):
                raise ValueError(name + " contains duplicate edge IDs")
        if set(self.added_edges) & set(self.retired_edges):
            raise ValueError("an edge cannot be added and retired in one event")
        object.__setattr__(self, "water_transfer_m3", _finite(self.water_transfer_m3, "water_transfer_m3", True))
        object.__setattr__(self, "sediment_transfer_solid_m3",
                           _finite(self.sediment_transfer_solid_m3, "sediment_transfer_solid_m3", True))
        if not isinstance(self.material_ledger, Mapping):
            raise ValueError("material_ledger must be a mapping")
        ledger = {}
        for key, value in self.material_ledger.items():
            if key not in LEDGER_KEYS:
                raise ValueError("unknown material ledger key: " + str(key))
            ledger[key] = _finite(value, "material_ledger." + key, True)
        object.__setattr__(self, "material_ledger", MappingProxyType(ledger))
        if not isinstance(self.parameters, Mapping):
            raise ValueError("parameters must be a mapping")
        object.__setattr__(self, "parameters", _freeze(_plain(self.parameters)))
        if not isinstance(self.revalidation_required, tuple) or not self.revalidation_required:
            raise ValueError("revalidation_required is required")
        if any(value not in REVALIDATION_KINDS for value in self.revalidation_required):
            raise ValueError("unknown revalidation kind")
        if self.status not in EVENT_STATUSES:
            raise ValueError("unsupported event status")

    @property
    def identity_sha256(self):
        return _digest(self.to_record(include_identity=False))

    def to_record(self, *, include_identity=True):
        record = {"schema": SCHEMA, "event_id": self.event_id, "event_type": self.event_type,
                  "parent_graph_identity_sha256": self.parent_graph_identity_sha256,
                  "parent_geometry_identity_sha256": self.parent_geometry_identity_sha256,
                  "affected_edges": list(self.affected_edges), "added_edges": list(self.added_edges),
                  "retired_edges": list(self.retired_edges), "water_transfer_m3": self.water_transfer_m3,
                  "sediment_transfer_solid_m3": self.sediment_transfer_solid_m3,
                  "material_ledger": _plain(self.material_ledger), "parameters": _plain(self.parameters),
                  "revalidation_required": list(self.revalidation_required), "status": self.status}
        if include_identity:
            record["identity_sha256"] = self.identity_sha256
        return record


def event_from_record(record):
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise ValueError("invalid morphology event schema")
    expected = record.get("identity_sha256")
    body = dict(record)
    body.pop("identity_sha256", None)
    if expected != _digest(body):
        raise ValueError("morphology event identity mismatch")
    return MorphologyEvent(
        event_id=record["event_id"], event_type=record["event_type"],
        parent_graph_identity_sha256=record["parent_graph_identity_sha256"],
        parent_geometry_identity_sha256=record["parent_geometry_identity_sha256"],
        affected_edges=tuple(record["affected_edges"]), added_edges=tuple(record["added_edges"]),
        retired_edges=tuple(record["retired_edges"]), water_transfer_m3=record["water_transfer_m3"],
        sediment_transfer_solid_m3=record["sediment_transfer_solid_m3"],
        material_ledger=_freeze(record["material_ledger"]), parameters=_freeze(record["parameters"]),
        revalidation_required=tuple(record["revalidation_required"]), status=record["status"])
