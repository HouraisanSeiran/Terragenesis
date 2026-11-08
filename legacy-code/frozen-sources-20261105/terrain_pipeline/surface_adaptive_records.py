"""Lossless immutable saved-array histories with bounded in-memory storage."""

from collections.abc import Mapping, Sequence
import io
import json
from pathlib import Path
import zipfile

import numpy as np
from terrain_pipeline.surface_adaptive_spool import SegmentedWorkspaceSpool


def _encode(record):
    arrays = {key: value for key, value in record.items() if isinstance(value, np.ndarray)}
    metadata = {key: value for key, value in record.items() if not isinstance(value, np.ndarray)}
    serialized = json.dumps(metadata, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    arrays["_record_metadata_json"] = np.frombuffer(serialized, np.uint8)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for name, value in arrays.items():
            with archive.open(name+".npy", "w", force_zip64=True) as entry:
                np.lib.format.write_array(entry, value, allow_pickle=False)
    return buffer.getvalue()


def _decode(payload):
    with np.load(io.BytesIO(payload), allow_pickle=False) as saved:
        result = json.loads(saved["_record_metadata_json"].tobytes().decode("utf-8"))
        result.update({key: saved[key].copy() for key in saved.files if key != "_record_metadata_json"})
    return result


class CompressedRecordList(Sequence):
    def __init__(self, directory=None, memory_limit_bytes=8*1024**2, append_observer=None, segment_limit_bytes=128*1024**2):
        directory = Path(directory) if directory is not None else Path(__file__).resolve().parents[1]/".scratch/adaptive-history"
        directory.mkdir(parents=True, exist_ok=True)
        self._memory_limit = memory_limit_bytes
        self._file = SegmentedWorkspaceSpool(directory,memory_limit_bytes=memory_limit_bytes,segment_limit_bytes=segment_limit_bytes)
        self._offsets = []
        self._length = 0
        self._maximum_payload = 0
        self._saved = {}
        self._saved_loader = None
        self._archived_prefix_count = 0
        self._append_observer = append_observer

    def append(self, record):
        self._append_payload(_encode(record))

    def _append_payload(self, payload):
        if self._saved:
            raise RuntimeError("adaptive archived record collection cannot append")
        if len(payload)>256*1024**2:
            raise RuntimeError("adaptive single compressed record exceeds artifact budget")
        self._file.seek(self._length)
        self._file.write(payload)
        self._offsets.append((self._length, len(payload)))
        self._length += len(payload)
        if self._length>self._memory_limit:
            self._file.flush()
        self._maximum_payload = max(self._maximum_payload, len(payload))
        if self._append_observer is not None:
            self._append_observer()

    def _payload(self, index):
        offset, length = self._offsets[index]
        self._file.seek(offset)
        payload = self._file.read(length)
        if len(payload)!=length:
            raise RuntimeError("adaptive immutable history payload truncated")
        return payload

    @property
    def storage_nbytes(self):
        resident = self._file.resident_nbytes
        return resident+64*len(self._offsets)+self._maximum_payload

    @property
    def temporary_storage_nbytes(self):
        return self._file.temporary_storage_nbytes

    @property
    def serialized_nbytes(self):
        return self._length

    def __len__(self):
        return len(self._offsets)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[position] for position in range(*index.indices(len(self)))]
        if index<0:
            index += len(self)
        if not 0<=index<len(self):
            raise IndexError("adaptive history record index outside collection")
        if index in self._saved:
            return self._saved_loader(self._saved[index])
        return _decode(self._payload(index))

    def bind_saved_record(self, index, pin, loader):
        if not 0<=index<len(self) or index in self._saved:
            raise ValueError("adaptive saved-record binding must replace a unique original record")
        self._saved[index] = dict(pin)
        self._saved_loader = loader
        while self._archived_prefix_count in self._saved:
            self._archived_prefix_count += 1
        if self._archived_prefix_count:
            offset,length = self._offsets[self._archived_prefix_count-1]
            self._file.release_before(offset+length)

    def close(self):
        self._file.close()

    def __del__(self):
        if hasattr(self, "_file"):
            self._file.close()


class CompressedGeometryHistory(Mapping):
    def __init__(self, directory=None, memory_limit_bytes=8*1024**2, append_observer=None):
        self._indices = {}
        self._records = CompressedRecordList(directory, memory_limit_bytes, append_observer)

    def register(self, geometry):
        identity = geometry["identity_sha256"]
        payload = _encode(dict(geometry["arrays"], metadata=geometry["metadata"], identity_sha256=identity))
        if identity in self._indices:
            if self._records._payload(self._indices[identity]) != payload:
                raise ValueError("immutable geometry history identity collision")
            return
        self._indices[identity] = len(self._records)
        self._records._append_payload(payload)

    @property
    def storage_nbytes(self):
        return self._records.storage_nbytes+128*len(self._indices)

    @property
    def temporary_storage_nbytes(self):
        return self._records.temporary_storage_nbytes

    @property
    def serialized_nbytes(self):
        return self._records.serialized_nbytes

    def __len__(self):
        return len(self._indices)

    def __iter__(self):
        return iter(self._indices)

    def bind_saved_geometry(self, identity, pin, loader):
        def original_record(pin):
            geometry = loader(pin)
            return dict(geometry["arrays"], metadata=geometry["metadata"], identity_sha256=geometry["identity_sha256"])
        self._records.bind_saved_record(self._indices[identity],pin,original_record)

    def __getitem__(self, identity):
        record = self._records[self._indices[identity]]
        metadata, saved_identity = record.pop("metadata"), record.pop("identity_sha256")
        if saved_identity != identity:
            raise ValueError("saved geometry history identity binding invalid")
        from terrain_pipeline.surface_adaptive_geometry import adaptive_geometry_identity
        if adaptive_geometry_identity(record, metadata) != identity:
            raise ValueError("decoded geometry history content identity mismatch")
        return dict(arrays=record, metadata=metadata, identity_sha256=saved_identity)
