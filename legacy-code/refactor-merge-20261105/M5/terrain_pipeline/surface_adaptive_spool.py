"""Append-only workspace history stream with bounded individual temporary files."""

import os
from pathlib import Path
import tempfile


class SegmentedWorkspaceSpool:
    def __init__(self, directory, *, memory_limit_bytes=8*1024**2, segment_limit_bytes=128*1024**2):
        if not 0<memory_limit_bytes<=segment_limit_bytes<=256*1024**2:
            raise ValueError("adaptive spool requires positive RAM and at-most-256MiB segments")
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._memory_limit = memory_limit_bytes
        self._segment_limit = segment_limit_bytes
        self._files, self._lengths = [], []
        self._length = self._position = 0
        self._released_segments = 0

    def seek(self, offset, whence=0):
        position = offset if whence==0 else self._position+offset if whence==1 else self._length+offset if whence==2 else -1
        if not 0<=position<=self._length:
            raise ValueError("adaptive spool seek outside saved bytes")
        self._position = position
        return position

    def write(self, payload):
        if self._position!=self._length:
            raise ValueError("adaptive history is immutable and append-only")
        view = memoryview(payload)
        written = 0
        while written<len(view):
            index, offset = divmod(self._position, self._segment_limit)
            if index==len(self._files):
                self._files.append(tempfile.SpooledTemporaryFile(max_size=self._memory_limit,
                    dir=self._directory,prefix="adaptive-history-segment-"))
                self._lengths.append(0)
            count = min(len(view)-written,self._segment_limit-offset)
            self._files[index].seek(offset)
            self._files[index].write(view[written:written+count])
            self._lengths[index] += count
            self._position += count
            self._length += count
            written += count
        return written

    def read(self, length=-1):
        length = min(self._length-self._position,length) if length>=0 else self._length-self._position
        blocks = []
        remaining = length
        while remaining:
            index, offset = divmod(self._position,self._segment_limit)
            count = min(remaining,self._lengths[index]-offset)
            if index<self._released_segments:
                raise RuntimeError("adaptive payload was archived; use its immutable saved record")
            self._files[index].seek(offset)
            block = self._files[index].read(count)
            if len(block)!=count:
                raise RuntimeError("adaptive segmented history payload truncated")
            blocks.append(block)
            remaining -= count
            self._position += count
        return b"".join(blocks)

    def flush(self):
        for file in self._files[self._released_segments:]:
            file.flush()

    @property
    def resident_nbytes(self):
        return sum(length for length in self._lengths[self._released_segments:] if length<=self._memory_limit)

    @property
    def temporary_storage_nbytes(self):
        return sum(os.fstat(file.fileno()).st_size for file,length in zip(self._files[self._released_segments:],self._lengths[self._released_segments:]) if length>self._memory_limit)

    def release_before(self, archived_offset):
        while self._released_segments<len(self._files):
            index = self._released_segments
            segment_end = index*self._segment_limit+self._lengths[index]
            if segment_end>archived_offset:
                break
            self._files[index].close()
            self._released_segments += 1

    def close(self):
        for file in self._files:
            file.close()

    def __del__(self):
        if hasattr(self,"_files"):
            self.close()
