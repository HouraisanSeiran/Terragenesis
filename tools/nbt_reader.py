"""Small read-only Java NBT decoder for inspecting level.dat metadata."""
from __future__ import annotations

import gzip
import io
import struct
from pathlib import Path


class NbtReader:
    def __init__(self, data: bytes):
        self.stream = io.BytesIO(data)
        self.size = len(data)

    def take(self, size: int) -> bytes:
        if size < 0 or size > self.size - self.stream.tell():
            raise ValueError("NBT payload exceeds available bytes")
        result = self.stream.read(size)
        return result

    def number(self, fmt: str):
        return struct.unpack(">" + fmt, self.take(struct.calcsize(">" + fmt)))[0]

    def string(self) -> str:
        return self.take(self.number("H")).decode("utf-8", errors="replace")

    def count(self) -> int:
        value = self.number("i")
        if value < 0 or value > self.size:
            raise ValueError("Invalid NBT list/array length")
        return value

    def payload(self, tag: int, depth: int = 0):
        if depth > 64:
            raise ValueError("NBT nesting limit exceeded")
        numeric = {1: "b", 2: "h", 3: "i", 4: "q", 5: "f", 6: "d"}
        if tag in numeric:
            return self.number(numeric[tag])
        if tag == 7:
            return self.take(self.count())
        if tag == 8:
            return self.string()
        if tag == 9:
            child, length = self.number("B"), self.count()
            if child == 0 and length:
                raise ValueError("Nonempty NBT list has END type")
            return [self.payload(child, depth + 1) for _ in range(length)]
        if tag == 10:
            result = {}
            while True:
                child = self.number("B")
                if child == 0:
                    return result
                name = self.string()
                result[name] = self.payload(child, depth + 1)
        if tag in (11, 12):
            length = self.count()
            fmt = "i" if tag == 11 else "q"
            return [self.number(fmt) for _ in range(length)]
        raise ValueError(f"Unknown NBT type {tag}")

    @classmethod
    def read_file(cls, path: Path):
        with gzip.open(path, "rb") as stream:
            data = stream.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024:
            raise ValueError("NBT metadata exceeds 32 MiB")
        reader = cls(data)
        tag = reader.number("B")
        if tag != 10:
            raise ValueError("Expected NBT compound root")
        reader.string()
        return reader.payload(tag)
