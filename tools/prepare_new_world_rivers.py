"""Prepare a preliminary channel product from an explicit NPZ contract."""
import argparse
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.new_world_rivers import prepare_rivers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_npz")
    parser.add_argument("output_npz")
    parser.add_argument("--source-identity", required=True)
    args = parser.parse_args()
    with np.load(args.input_npz, allow_pickle=False) as data:
        names = ("bed_m", "receiver", "q_m3_s", "channel_mask", "ocean_mask",
                 "lake_mask", "unknown_mask", "protected_mask", "origin_native_xz",
                 "spacing_m", "bed_hardness", "bank_hardness")
        values = {name: data[name] for name in names}
        result = prepare_rivers(**values, source_identity=args.source_identity)
    destination = Path(args.output_npz)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {"array_" + k: v for k, v in result["arrays"].items()}
    arrays.update({"graph_" + k: v for k, v in result["graph"].items()})
    arrays["metadata_json"] = np.asarray(json.dumps(result["metadata"], ensure_ascii=False))
    arrays["evidence_json"] = np.asarray(json.dumps(result["evidence"], ensure_ascii=False))
    with destination.open("xb") as handle:
        np.savez_compressed(handle, **arrays)


if __name__ == "__main__":
    main()
