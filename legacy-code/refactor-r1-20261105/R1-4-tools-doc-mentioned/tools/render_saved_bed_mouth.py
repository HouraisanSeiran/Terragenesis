#!/usr/bin/env python3
"""Re-render saved bed-mouth figures from existing artifacts without re-simulating."""
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import sys, json, hashlib
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.review_saved_bed_mouth import load_inputs, plot_profile, plot_cross_section
from tools.verify_fluvial_channel_remobilization import resource_limits


def render_saved_bed_mouth():
    out = ROOT / ".scratch/hydrological-planning-domain/saved-bed-mouth-20261016-01"
    with open(out / "summary.json", encoding="utf-8") as f:
        summary = json.load(f)
    with np.load(out / "centerline.npz", allow_pickle=False) as npz:
        connected = npz["connected_ocean_sample"].copy()
        samples = {k: npz[k].copy() for k in npz.files if k != "connected_ocean_sample" and k != "metadata_json"}
    inputs = load_inputs(ROOT)
    plot_profile(samples, summary, connected, out)
    meta = plot_cross_section(inputs, summary, out)
    for path, digest in inputs["source_hashes"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    source_sha256 = {str(path): digest for path, digest in inputs["source_hashes"].items()}
    result = {
        "cross_section": meta,
        "source_sha256": source_sha256,
        "global_hydrology_certified": False,
        "publishable": False,
    }
    with open(out / "plot-summary.json", "w", encoding="utf-8") as f:
        json.dump(result, f, allow_nan=False)
    print(result, flush=True)
