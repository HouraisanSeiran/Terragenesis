"""Stable JSON and shape/dtype/content hashes for legacy NPZ bundle identities.

These byte conventions differ from contracts.canonical_json and array_hash.
The frozen rainfall_runoff v1 helpers retain equivalent implementations because
their complete source file is part of the PET algorithm identity.
"""

import hashlib
import json


def json_text(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def strict_json(payload):
    def pairs(items):
        parsed = {}
        for key, value in items:
            if key in parsed:
                raise ValueError("duplicate JSON key")
            parsed[key] = value
        return parsed

    def constant(value):
        raise ValueError(f"invalid JSON constant: {value}")

    return json.loads(payload, object_pairs_hook=pairs, parse_constant=constant)


def shaped_array_hash(array):
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()
