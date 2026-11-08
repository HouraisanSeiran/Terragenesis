"""Cold audit a saved monotone component without invoking its optimizer."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.surface_rivers.metric_monotone_union import load_monotone_union
from tools.audit_td_river_geometry_sediment import independent_continuous_bed


def audit(path):
    with np.load(path, allow_pickle=False) as archive:
        manifest = json.loads(archive["manifest"].tobytes().decode("utf-8"))
    sha = file_sha256(path)
    with (patch("terrain_pipeline.surface_rivers.metric_monotone_union.linprog",
                side_effect=AssertionError("cold audit invoked optimizer")),
          patch("terrain_pipeline.surface_rivers.metric_monotone_union.build_monotone_union",
                side_effect=AssertionError("cold audit invoked builder"))):
        product = load_monotone_union(path, expected_sha256=sha,
                                      expected_identity=manifest["identity_sha256"])
    return dict(path=str(path.resolve()), sha256=sha,
                identity_sha256=product["identity_sha256"],
                independent_PL=independent_continuous_bed(product),
                cut_volume_m3=product["metadata"]["cut_volume_m3"],
                cold_optimizer_disabled=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("product", type=Path)
    print(json.dumps(audit(parser.parse_args().product), indent=2))
