"""Seed convention for new procedural sources; historical sources keep their seed."""

import hashlib

WORLD_SEED = 20260903
SEED_DERIVATION = "sha256(terragenesis-procedural-mountains-v1|world_seed|purpose), first 8 bytes big-endian"


def derive_subseed(world_seed, purpose):
    """Return a stable unsigned 64-bit, purpose-separated seed."""
    if isinstance(world_seed, bool) or not isinstance(world_seed, int) or not 0 <= world_seed < 2**64:
        raise ValueError("world_seed must be an unsigned 64-bit integer")
    if not isinstance(purpose, str) or not purpose:
        raise ValueError("purpose must be a nonempty string")
    message = f"terragenesis-procedural-mountains-v1|{world_seed}|{purpose}"
    return int.from_bytes(hashlib.sha256(message.encode("utf-8")).digest()[:8], "big")
