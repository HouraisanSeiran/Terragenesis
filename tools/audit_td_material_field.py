"""Scalar independent global-lattice material checks on an externally pinned field."""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import publish_bytes
from tools.audit_td_basin_generation import file_record, read_saved


def lattice_value(lattice_x, lattice_z, seed, channel):
    mask = 2 ** 64 - 1
    value = ((lattice_x & mask) * 0x9E3779B185EBCA87) & mask
    value ^= ((lattice_z & mask) * 0xC2B2AE3D27D4EB4F) & mask
    value ^= seed
    value ^= (channel * 0x165667B19E3779F9) & mask
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
    value ^= value >> 31
    return (value >> 11) / 2 ** 53


def scalar_noise(global_x, global_z, scale, seed, channel):
    coordinate_x, coordinate_z = global_x / scale, global_z / scale
    lattice_x, lattice_z = math.floor(coordinate_x), math.floor(coordinate_z)
    fraction_x, fraction_z = coordinate_x - lattice_x, coordinate_z - lattice_z
    smooth_x = fraction_x ** 3 * (fraction_x * (fraction_x * 6 - 15) + 10)
    smooth_z = fraction_z ** 3 * (fraction_z * (fraction_z * 6 - 15) + 10)
    upper = lattice_value(lattice_x, lattice_z, seed, channel) * (1 - smooth_x)
    upper += lattice_value(lattice_x + 1, lattice_z, seed, channel) * smooth_x
    lower = lattice_value(lattice_x, lattice_z + 1, seed, channel) * (1 - smooth_x)
    lower += lattice_value(lattice_x + 1, lattice_z + 1, seed, channel) * smooth_x
    return upper * (1 - smooth_z) + lower * smooth_z


def audit(arrays, metadata):
    shape = tuple(metadata["shape"])
    parameters = metadata["parameters"]
    seed = metadata["seed"]
    spacing = metadata["spacing_m"]
    origin = np.rint(np.array(metadata["origin_m_xz"]) / spacing).astype(np.int64)
    sampled = np.unique(np.concatenate((np.linspace(0, math.prod(shape) - 1, 128).astype(int),
                                        [0, shape[1] - 1, (shape[0] - 1) * shape[1]])))
    max_error = 0.
    fields = []
    for channel, (name, range_name) in enumerate((
        ("erodibility", "erodibility_range"),
        ("erodible_thickness_m", "erodible_thickness_range_m"),
        ("weak_path_preference", "weak_path_preference_range")), start=1):
        field = arrays[name]
        low, high = parameters[range_name]
        if field.shape != shape or not np.isfinite(field).all() or np.any(field < low) or np.any(field > high):
            raise ValueError("material outside source parameters")
        for cell in sampled:
            row, column = divmod(int(cell), shape[1])
            global_x = (int(origin[0]) + column + 0.5) * spacing
            global_z = (int(origin[1]) + row + 0.5) * spacing
            value = scalar_noise(global_x, global_z, parameters["correlation_length_m"], seed, channel)
            expected = min(high, max(low, low + (high - low) * value))
            error = abs(float(field[row, column]) - expected)
            max_error = max(max_error, error)
            if error > 1e-12:
                raise ValueError("material differs from independent integer lattice reference")
        fields.append({"field": name, "minimum": float(field.min()), "maximum": float(field.max()),
                       "max_neighbor_difference": max(float(np.max(np.abs(np.diff(field, axis=axis))))
                                                      if shape[axis] > 1 else 0. for axis in (0, 1))})
    return {"shape": list(shape), "scalar_samples": len(sampled), "scalar_checks": 3 * len(sampled),
            "max_scalar_error": max_error, "fields": fields, "synthetic_material": True,
            "measured_lithology": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--material", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    arrays, metadata = read_saved(args.material, args.sha256)
    report = {"algorithm": "td-material-independent-scalar-v1", "reviewed_utc": datetime.now(timezone.utc).isoformat(),
              "input": file_record(args.material), "auditor": file_record(__file__), "checks": audit(arrays, metadata)}
    publish_bytes(args.output, (json.dumps(report, sort_keys=True, allow_nan=False, indent=2) + "\n").encode())
    print(json.dumps(report["checks"], sort_keys=True))


if __name__ == "__main__":
    main()
