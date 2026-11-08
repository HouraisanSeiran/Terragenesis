"""Fixed local-research DEM preparation, without services, GPU or game integration."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import rasterio
from rasterio.warp import transform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.dem_domain import (
    file_sha256, load_dem_candidate, prepare_dem_candidate, route_dem_candidate, save_dem_candidate,
)


SOURCE = Path("D:/geography/01-完整流域样本/data/srtm_61_07.tif")
BBOX = (121.25, 29.15, 121.65, 29.65)


def main():
    before = file_sha256(SOURCE)
    readme = SOURCE.with_name("readme.txt")
    readme_before = file_sha256(readme)
    candidate = prepare_dem_candidate(
        SOURCE, BBOX, target_crs="EPSG:32651", spacing_m=90., halo_m=900.,
        sea_level_m=0., sea_datum="Unverified numeric zero in source elevations, not current tidal sea level",
        source_declaration="Local CIAT-CSI hole-filled SRTM v4.1; readme.txt distribution/commercial restrictions; local research only, license not cleared; elevation assumed metres",
        vertical_datum="Unknown: horizontal WGS84 and local readme do not verify an EGM96 vertical datum",
        max_cells=500000, max_source_cells=599999)
    output = ROOT / "verification/dem-domain" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    package = save_dem_candidate(candidate, output / "dem-candidate.npz")
    loaded = load_dem_candidate(package)
    for name in candidate["arrays"]:
        np.testing.assert_array_equal(candidate["arrays"][name], loaded["arrays"][name])
    summary = loaded["manifest"]["summary"]
    if summary["unknown_cells"]:
        try:
            route_dem_candidate(loaded)
        except ValueError as error:
            hydrology = {"status": "skipped_unknown_coverage", "guard_verified": True, "reason": str(error),
                         "outlet_candidates": [], "closed_observed_candidate": False,
                         "river_independently_verified": False}
        else:
            raise AssertionError("unknown coverage must block routing")
    else:
        hydrology = {"status": "skipped_no_explicit_outlet_evidence", "outlet_candidates": [],
                     "closed_observed_candidate": False, "river_independently_verified": False}
    observations = []
    with rasterio.open(SOURCE, "r") as source:
        grid = loaded["manifest"]["identity"]["grid"]
        height = loaded["arrays"]["height_m"]
        indices = np.linspace(0, height.size - 1, 251, dtype=int)
        regression_zx = np.asarray([(84, 342), (138, 308), (236, 117), (382, 290),
                                    (475, 36), (480, 98), (593, 94)], dtype=int)
        all_indices = np.concatenate([indices, regression_zx[:, 0] * height.shape[1] + regression_zx[:, 1]])
        sample_rows, sample_cols = np.divmod(all_indices, height.shape[1])
        source_x, source_y = transform("EPSG:32651", source.crs,
            grid["origin_x_m"] + sample_cols * 90,
            -(grid["origin_z_m"] + sample_rows * 90))
        expected = np.asarray([np.nan if np.ma.is_masked(sample[0]) else float(sample[0])
                               for sample in source.sample(zip(source_x, source_y), masked=True)])
        actual = height.ravel()[all_indices]
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(loaded["arrays"]["valid_mask"].ravel()[all_indices], np.isfinite(expected))
        np.testing.assert_array_equal(loaded["arrays"]["unknown_mask"].ravel()[all_indices], ~np.isfinite(expected))
        fixed_sample_check = {"method": "exact target centers inverse transform then independent source.sample",
                              "uniform_samples": 251, "known_v1_mismatch_samples": 7,
                              "height_mismatch_count": 0, "mask_mismatch_count": 0,
                              "max_abs_difference_m": 0.,
                              "known_v1_mismatch_zx": regression_zx.tolist(),
                              "known_v1_mismatch_exact_height_m": expected[-7:].tolist()}
        for name, longitude, latitude in (("old_control_candidate", 121.430833, 29.423333),
                                          ("old_window_mouth_candidate", 121.5025, 29.550833)):
            row, col = source.index(longitude, latitude)
            center_longitude, center_latitude = source.xy(row, col, offset="center")
            sample = next(source.sample([(longitude, latitude)], masked=True))[0]
            observations.append({"name": name, "requested_lon_lat": [longitude, latitude],
                                 "source_pixel_row_col": [row, col],
                                 "actual_pixel_center_lon_lat": [center_longitude, center_latitude],
                                 "nearest_source_height_m": None if np.ma.is_masked(sample) else float(sample),
                                 "scope": "metadata candidate only, no target snap or area reverse selection",
                                 "natural_mouth_verified": False,
                                 "old_7m_control_not_confirmed": name == "old_control_candidate"})
    after = file_sha256(SOURCE)
    if before != after or readme_before != file_sha256(readme):
        raise AssertionError("read-only sources changed")
    report = {"purpose": "task17 bounded real DEM diagnostic preparation, not real-basin acceptance",
              "package": package.name, "package_sha256": file_sha256(package),
              "source_sha256_before": before, "source_sha256_after": after,
              "source_unchanged": True, "source_readme": str(readme), "source_readme_sha256": readme_before,
              "license": {"scope": "local research only", "cleared": False,
                          "declaration": "CIAT written permission required for commercial/non-free resale or redistribution; no default-world integration"},
              "manifest": loaded["manifest"], "hydrology": hydrology,
              "fixed_center_sampling_check": fixed_sample_check,
              "control_point_metadata_candidates": observations,
              "acceptance": {"projection_and_candidate_guard_verified": True,
                             "real_basin_passed": False, "natural_mouth_verified": False,
                             "two_tributaries_observed": False, "mainstem_observed": False,
                             "observation_note": "Not established, not proof of absence: missing coverage blocks full-domain routing; no independent river geometry supplied",
                             "fine_bed_verified": False},
              "scope": "No target-area reverse outlet selection, fake outlet migration, front end, core/Java changes, GPU or full raster read"}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "shape_zx": grid["shape_zx"],
                      "format": loaded["manifest"]["format"],
                      "source_read_cells": loaded["manifest"]["identity"]["source"]["read_cells"],
                      "valid_cells": summary["valid_cells"], "unknown_cells": summary["unknown_cells"],
                      "center_sampling_check": fixed_sample_check, "hydrology": hydrology},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
