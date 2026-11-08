"""Bounded NPZ bundles with pinned reads and atomic, non-overwriting publication."""

import hashlib
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from .encoding import json_text, shaped_array_hash, strict_json


MAX_BYTES = 128 * 1024 * 1024
MAX_METADATA = 1_048_576


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_archive(path, *, expected_sha256, max_bytes=MAX_BYTES, header_validator=None):
    """Check ZIP and NPY headers before allocating any array; never allow pickle."""
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("external archive SHA256 required")
    if Path(path).stat().st_size > max_bytes:
        raise ValueError("compressed archive byte budget exceeded")
    with open(path, "rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        if digest.hexdigest() != expected_sha256:
            raise ValueError("external archive hash mismatch")
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            headers = {}
            if (not 1 <= len(members) <= 128 or
                    len({member.filename for member in members}) != len(members) or
                    sum(member.file_size for member in members) > max_bytes):
                raise ValueError("archive resource/duplicate member rejection")
            for member in members:
                if not member.filename.endswith(".npy") or "/" in member.filename:
                    raise ValueError("invalid archive member")
                with archive.open(member) as entry:
                    version = np.lib.format.read_magic(entry)
                    if version == (1, 0):
                        shape, fortran, dtype = np.lib.format.read_array_header_1_0(entry, max_header_size=4096)
                    elif version == (2, 0):
                        shape, fortran, dtype = np.lib.format.read_array_header_2_0(entry, max_header_size=4096)
                    else:
                        raise ValueError("unsupported NPY header")
                    if (dtype.hasobject or fortran or len(shape) > 3 or
                            any(size < 0 or size > 8_000_000 for size in shape) or
                            math.prod(shape) * dtype.itemsize + entry.tell() != member.file_size):
                        raise ValueError("unsafe NPY shape/dtype/size")
                    headers[member.filename[:-4]] = (shape, dtype)
            if header_validator is not None:
                header_validator(headers)
        stream.seek(0)
        with np.load(stream, allow_pickle=False) as archive:
            return {key: archive[key].copy() for key in archive.files}


def readonly(array):
    value = np.ascontiguousarray(array)
    return np.frombuffer(value.tobytes(), dtype=value.dtype).reshape(value.shape)


def identity(arrays, metadata):
    record = {"metadata": metadata, "arrays": {key: shaped_array_hash(value) for key, value in sorted(arrays.items())}}
    return hashlib.sha256(json_text(record).encode("utf-8")).hexdigest()


def publish_bytes(path, payload):
    """A hard link is the commit point; a racing existing destination wins."""
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".mountain-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


def save_bundle(path, result, *, validator):
    validator(result)
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    manifest = json_text({"metadata": result["metadata"], "identity_sha256": result["identity_sha256"]}).encode("utf-8")
    if len(manifest) > MAX_METADATA:
        raise ValueError("metadata budget exceeded")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".mountain-", suffix=".npz", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            np.savez_compressed(stream, manifest=np.frombuffer(manifest, dtype=np.uint8), **result["arrays"])
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


def load_bundle(path, *, expected_sha256, validator, max_bytes=MAX_BYTES, header_validator=None):
    arrays = checked_archive(path, expected_sha256=expected_sha256, max_bytes=max_bytes,
                             header_validator=header_validator)
    manifest = arrays.pop("manifest", None)
    if (manifest is None or manifest.dtype != np.uint8 or manifest.ndim != 1 or
            manifest.size > MAX_METADATA):
        raise ValueError("invalid manifest")
    record = strict_json(manifest.tobytes().decode("utf-8"))
    if set(record) != {"metadata", "identity_sha256"}:
        raise ValueError("unexpected manifest keys")
    result = dict(record, arrays=arrays)
    validator(result)
    result["arrays"] = {key: readonly(value) for key, value in arrays.items()}
    return result
