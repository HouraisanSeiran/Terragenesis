"""Inventory Earth BIO coverage under an existing, unchanged river evaluation design."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_river_reference_conditions import pin

DESIGN = ROOT / "verification/td-natural-river-stages/reference-geographic-20261011-04/climate-design.json"
TARGET_BINS = [[4, 2, 2, 1], [2, 3, 1, 1], [2, 2, 2, 1]]


def distance_km(first, second):
    lon1, lat1, lon2, lat2 = map(math.radians, [*first, *second])
    value = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371. * 2 * math.asin(min(1., math.sqrt(value)))


def select_locations(coordinates, minimum_distance_km=25., maximum=12):
    coordinates = sorted(coordinates, key=lambda p: hashlib.sha256(json.dumps(p).encode()).hexdigest())
    selected = []
    for coordinate in coordinates:
        if all(distance_km(coordinate, previous) >= minimum_distance_km for previous in selected):
            selected.append(coordinate)
            if len(selected) == maximum:
                break
    return selected


def survey(output, design_path=DESIGN):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    design = json.loads(Path(design_path).read_text(encoding="utf-8"))
    arrays, valid, sources, geometry = [], None, [], None
    for channel in (1, 4, 12, 15):
        path = ROOT / f"data/global/wc2.1_10m_bio_{channel}.tif"
        with rasterio.open(path) as raster:
            header = (raster.shape, raster.crs.to_string(), tuple(raster.transform))
            if geometry is not None and geometry != header:
                raise ValueError("global BIO sources must share exact geographic grid")
            geometry = header
            values = raster.read(1, masked=True)
            known = ~np.ma.getmaskarray(values) & np.isfinite(values.data)
            valid = known if valid is None else valid & known
            arrays.append(values.data)
            sources.append({**pin(path), "crs": raster.crs.to_string(), "shape": list(raster.shape),
                            "transform": list(raster.transform)[:6], "nodata": raster.nodata,
                            "scale": raster.scales[0], "offset": raster.offsets[0]})
    bins = [np.searchsorted(design["bin_edges"][channel], values, side="right")
            for channel, values in zip(design["channel_order"], arrays)]
    targets = []
    for target in TARGET_BINS:
        matched = valid & np.logical_and.reduce([observed == desired for observed, desired in zip(bins, target)])
        rows, cols = np.nonzero(matched)
        lon, lat = rasterio.transform.xy(rasterio.Affine(*geometry[2][:6]), rows, cols)
        coordinates = list(zip(map(float, lon), map(float, lat)))
        within_srtm = [p for p in coordinates if -56 < p[1] < 60]
        selected = select_locations(within_srtm)
        samples = []
        for index, coordinate in enumerate(selected):
            row, col = rasterio.transform.rowcol(rasterio.Affine(*geometry[2][:6]), *coordinate)
            samples.append({"center_lon_lat": list(coordinate), "climate_pixel_row_col": [int(row), int(col)],
                "role": ("fit", "calibration", "real_holdout")[index % 3],
                "BIO1_4_12_15": [float(values[row, col]) for values in arrays],
                "bbox_lon_lat": [coordinate[0] - .075, coordinate[1] - .075, coordinate[0] + .075, coordinate[1] + .075]})
        targets.append({"bin": target, "global_valid_pixels": int(matched.sum()),
            "pixels_within_SRTM_latitude": len(within_srtm), "preselected_locations": samples,
            "status": "observed_global_coverage" if coordinates else "no_observed_WorldClim_global_coverage",
            "absence_semantics": "no_pixels_in_this_product_and_fixed_bins_not_proof_of_physical_impossibility"})
    report = {"schema": "global-river-climate-coverage-v1", "status": "global_scan_completed",
        "climate_design": pin(design_path), "source_product": "WorldClim2.1_1970_2000_10arcmin",
        "sources": sources, "valid_global_pixels": int(valid.sum()), "target_conditions": targets,
        "sampling_plan": {"selection": "sha256_of_lonlat_order_then25km_geographic_separation",
            "plan_history": "150km_initial_source_survey_supports_only_two_locations;25km_revision_based_only_on_real_climate_coverage_before_new_TD_metrics",
            "maximum_locations_per_bin": 12, "source_tile_priority": "same_CIAT_CSI_SRTM_v4.1_then_separate_Copernicus_GLO90_stratum",
            "fixed_bbox_half_extent_degrees": .075, "spacing_m": 90, "block_size": 48,
            "role": "spatially_separated_locations_cycle_fit_calibration_real_holdout",
            "source_product_mixing": "prohibited_use_independent_product_calibration",
            "new_TD_naturalness_accessed": False}, "natural_credible": False, "publishable": False}
    probabilities = [0, .01, .05, .25, .5, .75, .95, .99, 1]
    report["physical_reference"] = {"probabilities": probabilities,
        "quantiles": {channel: np.quantile(values[valid], probabilities).tolist()
                      for channel, values in zip(design["channel_order"], arrays)},
        "unit_contract": design["units"], "observation_period": "1970_2000",
        "statistical_weighting": "equal_geographic_pixels_not_equal_surface_area_or_independent_stations",
        "role": "descriptive_physical_range_and_joint_context_not_naturalness_acceptance_cutoff",
        "temperature_conditioned_joint_envelopes": []}
    for bin_index in range(len(design["bin_edges"]["BIO1"]) + 1):
        selected = valid & (bins[0] == bin_index)
        report["physical_reference"]["temperature_conditioned_joint_envelopes"].append({
            "BIO1_bin": bin_index, "observations": int(selected.sum()),
            "quantiles": {channel: np.quantile(values[selected], probabilities).tolist() if selected.any() else None
                          for channel, values in zip(design["channel_order"], arrays)}})
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = survey(arguments.output)
    print(json.dumps({"status": result["status"], "targets": result["target_conditions"]}))
