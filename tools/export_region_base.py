"""Read saved RMR base samples for comparison with diffusion output.

These are pre-VDM source heights, not the final Minecraft chunk surface.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import struct

parser = argparse.ArgumentParser()
parser.add_argument("region", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--step", type=int, default=1)
args = parser.parse_args()
source = args.region.resolve()
if args.step < 1:
    raise SystemExit("--step must be positive")
data = source.read_bytes()
if hashlib.sha256(data[:-32]).digest() != data[-32:]:
    raise SystemExit("Region package checksum mismatch")

offset = 0
def read(fmt):
    global offset
    value = struct.unpack_from(">" + fmt, data, offset)[0]
    offset += struct.calcsize(">" + fmt)
    return value

def utf():
    global offset
    size = read("H")
    value = data[offset:offset + size].decode("utf-8")
    offset += size
    return value

if read("I") != 0x524D5231 or read("I") != 1:
    raise SystemExit("Unsupported RMR header")
algorithm, seed, identity, recipe = utf(), read("q"), utf(), utf()
chunks, processing = read("i"), utf()
rx, rz, side, mesh_size = read("i"), read("i"), read("i"), read("i")
if recipe != "regional-xyz-vdm-v1" or side != chunks * 16 // 3 + 1:
    raise SystemExit("Unexpected region recipe or dimensions")
samples = []
for z in range(side):
    for x in range(side):
        h, water, temp, rain, landmark = struct.unpack_from(">ddddd", data, offset)
        offset += 40
        landform = read("b")
        if x % args.step == 0 and z % args.step == 0:
            local_x, local_z = rx * (side - 1) + x, rz * (side - 1) + z
            samples.append((local_x * 3, local_z * 3, local_x, local_z,
                            h, water, temp, rain, landmark, landform))
if offset + mesh_size * mesh_size * 24 != len(data) - 32:
    raise SystemExit("RMR payload length mismatch")
args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open("w", newline="", encoding="utf-8") as stream:
    writer = csv.writer(stream)
    writer.writerow(("world_x", "world_z", "model_x", "model_z", "base_height",
                     "water", "temperature", "rain", "landmark", "landform_id"))
    writer.writerows(samples)
metadata = {"source": str(source), "sha256": hashlib.sha256(data).hexdigest(),
            "seed": seed, "source_identity": identity, "recipe": recipe,
            "algorithm": algorithm, "chunks": chunks, "processing": processing,
            "region": [rx, rz], "sample_step": args.step, "samples": len(samples),
            "meaning": "Saved base field before VDM mesh displacement, voxelization, and Minecraft chunk generation"}
args.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
print("Exported", len(samples), "saved base samples to", args.output)
