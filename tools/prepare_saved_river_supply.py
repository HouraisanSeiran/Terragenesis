import json
from pathlib import Path

import numpy as np

from terrain_pipeline.hydrology_planning import load_plan
from terrain_pipeline.hydrology_detail import file_sha256
from terrain_pipeline.common_infra import checked_archive
from terrain_pipeline.runoff import _digest as _digest
from terrain_pipeline.runoff import COLUMN_ARRAYS as COLUMN_ARRAYS
from terrain_pipeline.runoff import _array_hash as _array_hash
from terrain_pipeline.runoff import SeasonalConfig as SeasonalConfig
from terrain_pipeline.runoff import MONTH_DAYS as MONTH_DAYS


def load_saved_supply_inputs(plan_path, bundle_path):
    p = Path(plan_path).resolve()
    b = Path(bundle_path).resolve()
    parent = load_plan(p)

    mp = b / "hybrid-bundle.json"
    mhash = file_sha256(mp)
    sidecar = mp.with_suffix(".sha256").read_text(encoding="ascii").strip()
    if sidecar != mhash:
        raise ValueError("hybrid bundle sidecar sha256 does not match manifest file hash")

    manifest = json.loads(mp.read_text(encoding="utf-8"))
    if manifest["schema"] != "hydrology-hybrid-lake-seasonal-bundle-v1":
        raise ValueError("unexpected hybrid bundle schema")
    if manifest["identity_sha256"] != _digest(
        {k: v for k, v in manifest.items() if k != "identity_sha256"}
    ):
        raise ValueError("hybrid bundle identity_sha256 does not match recomputed digest")
    if manifest["parent_plan_identity_sha256"] != parent["identity_sha256"]:
        raise ValueError("hybrid bundle parent_plan_identity_sha256 does not match parent plan")

    fine = b / "fine-detail.npz"
    fine_hash = file_sha256(fine)
    if fine_hash != manifest["fine_source_sha256"]:
        raise ValueError("fine detail npz sha256 does not match manifest")

    ca_path = b / "column-plan-climate.npz"
    sa_path = b / "seasonal.npz"
    ca = checked_archive(
        ca_path, expected_sha256=manifest["column_plan_climate_sha256"]
    )
    sa = checked_archive(sa_path, expected_sha256=manifest["seasonal_sha256"])

    column = json.loads(str(ca["metadata_json"].item()))
    column.update({key: ca[key] for key in COLUMN_ARRAYS})
    record = column["seasonal_hybrid"]

    if record != manifest["replacement_audit"]:
        raise ValueError("column seasonal_hybrid record does not match manifest replacement_audit")
    if _digest(record) != column["identity_sha256"]:
        raise ValueError("column identity_sha256 does not match recomputed digest")
    if column["identity_sha256"] != manifest["hybrid_plan_identity_sha256"]:
        raise ValueError("column identity_sha256 does not match manifest hybrid_plan_identity_sha256")
    if record["parent_plan_identity_sha256"] != parent["identity_sha256"]:
        raise ValueError("column record parent_plan_identity_sha256 does not match parent plan")

    if set(record["column_array_sha256"]) != set(COLUMN_ARRAYS):
        raise ValueError("column_array_sha256 keys do not match COLUMN_ARRAYS")
    for key in COLUMN_ARRAYS:
        if _array_hash(column[key]) != record["column_array_sha256"][key]:
            raise ValueError(f"column array sha256 mismatch for {key}")

    climate = {
        name: ca["climate__" + name]
        for name in ("precipitation_mm", "potential_et_mm", "temperature_c")
    }
    if {name: _array_hash(v) for name, v in climate.items()} != record[
        "climate_sha256"
    ]:
        raise ValueError("climate array sha256 values do not match record")
    if set(climate) != set(record["climate_sha256"]):
        raise ValueError("climate keys do not match record climate_sha256 keys")

    meta = json.loads(str(sa["metadata_json"].item()))
    if meta["source_plan_identity_sha256"] != column["identity_sha256"]:
        raise ValueError("seasonal metadata source_plan_identity_sha256 does not match column")
    if meta["seasonal_hybrid"] != record:
        raise ValueError("seasonal metadata seasonal_hybrid does not match column record")
    if meta["status"] != "converged":
        raise ValueError("seasonal metadata status is not converged")

    domain_ids = meta["domain_ids"]
    if len(domain_ids) != len(set(domain_ids)):
        raise ValueError("seasonal domain_ids contains duplicates")
    if not all(isinstance(d, int) for d in domain_ids):
        raise ValueError("seasonal domain_ids must all be ints")
    if domain_ids != [d["domain_id"] for d in column["domains"]]:
        raise ValueError("seasonal domain_ids do not match column domains")

    config = SeasonalConfig(**meta["parameters"])

    for name, value in climate.items():
        if not np.array_equal(sa["climate__" + name], value):
            raise ValueError(f"seasonal climate array does not match column climate for {name}")

    saved_keys = (
        "coastal_outflow_m3",
        "runoff_to_terminal_m3",
        "land_rain_m3",
        "lake_rain_m3",
    )
    saved = {
        "soil_mm": sa["soil_mm"],
        "domain_ids": domain_ids,
        "steps": {key: sa["steps__" + key] for key in saved_keys},
        "monthly": {key: sa["monthly__" + key] for key in saved_keys},
    }

    owner = column["owner_domain_id"]
    if not (owner.ndim == 2 and owner.shape[0] == 1):
        raise ValueError("column owner_domain_id must be 2D with shape[0] == 1")
    if column["seasonal_column_area_m2"].shape != owner.shape:
        raise ValueError("column seasonal_column_area_m2 shape does not match owner_domain_id")
    if column["seasonal_parent_cell_id"].shape != owner.shape:
        raise ValueError("column seasonal_parent_cell_id shape does not match owner_domain_id")

    for name, value in climate.items():
        if value.ndim != 3:
            raise ValueError(f"climate array {name} must be 3D")
        if value.shape[0] != 12:
            raise ValueError(f"climate array {name} must have 12 months")
        if value.shape[1:] != owner.shape:
            raise ValueError(f"climate array {name} spatial shape does not match owner_domain_id")

    if saved["soil_mm"].ndim != 3:
        raise ValueError("saved soil_mm must be 3D")
    if saved["soil_mm"].shape[0] != 13:
        raise ValueError("saved soil_mm must have 13 layers")
    if saved["soil_mm"].shape[1:] != owner.shape:
        raise ValueError("saved soil_mm spatial shape does not match owner_domain_id")

    nstep = int(sum(MONTH_DAYS)) * config.substeps_per_day
    D = len(domain_ids)
    for arr in saved["steps"].values():
        if arr.shape != (nstep, D):
            raise ValueError("saved steps array shape does not match (nstep, D)")
        if not np.all(np.isfinite(arr)):
            raise ValueError("saved steps array contains non-finite values")
        if not np.all(arr >= 0):
            raise ValueError("saved steps array contains negative values")
    for arr in saved["monthly"].values():
        if arr.shape != (12, D):
            raise ValueError("saved monthly array shape does not match (12, D)")
        if not np.all(np.isfinite(arr)):
            raise ValueError("saved monthly array contains non-finite values")
        if not np.all(arr >= 0):
            raise ValueError("saved monthly array contains negative values")

    input_hashes = {
        str(p): file_sha256(p),
        str(mp): mhash,
        str(ca_path): file_sha256(ca_path),
        str(sa_path): file_sha256(sa_path),
        str(fine): fine_hash,
    }

    return {
        "parent": parent,
        "columns": column,
        "climate": climate,
        "saved": saved,
        "config": config,
        "manifest": manifest,
        "seasonal_metadata": meta,
        "input_hashes": input_hashes,
    }


import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from terrain_pipeline.surface_rivers.metric_saved_river_supply import (
    partition_saved_supply,
    replay_saved_supply,
)
from tools.verify_fluvial_channel_remobilization import resource_limits




def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    resource_limits()

    loaded = load_saved_supply_inputs(args.plan, args.bundle)
    parent = loaded["parent"]
    columns = loaded["columns"]

    partition = partition_saved_supply(
        parent, columns, source_node=8470, receiver_node=8600
    )
    result = replay_saved_supply(
        partition, columns, loaded["climate"], loaded["saved"], loaded["config"]
    )

    for path, hash_value in loaded["input_hashes"].items():
        if file_sha256(Path(path)) != hash_value:
            raise ValueError(
                "input hash mismatch for %s: expected %s, got %s"
                % (path, hash_value, file_sha256(Path(path)))
            )

    arrays = {}
    arrays.update(
        {key: value for key, value in result.items() if isinstance(value, np.ndarray)}
    )
    arrays.update(
        {
            key: value
            for key, value in partition.items()
            if isinstance(value, np.ndarray)
        }
    )
    arrays["seasonal_parent_cell_id"] = columns["seasonal_parent_cell_id"]
    arrays["seasonal_column_area_m2"] = columns["seasonal_column_area_m2"]
    arrays["monthly_end_s"] = np.cumsum(MONTH_DAYS) * 86400.0
    arrays["monthly_start_s"] = np.concatenate(
        ([0.0], arrays["monthly_end_s"][:-1])
    )

    area = columns["seasonal_column_area_m2"].ravel()
    q = result["selected_q_m3_s"]
    width = parent["receiver"].shape[1]

    sourcexz = [
        parent["origin_xz_m"][0] + (8470 % width) * parent["spacing_m"],
        parent["origin_xz_m"][1] + (8470 // width) * parent["spacing_m"],
    ]
    receiverxz = [
        parent["origin_xz_m"][0] + (8600 % width) * parent["spacing_m"],
        parent["origin_xz_m"][1] + (8600 // width) * parent["spacing_m"],
    ]

    summary = {
        "schema": "saved-river-seasonal-supply-v1",
        "status": "verified_saved_coastal_replay",
        "publishable": False,
        "hydraulics_certified": False,
        "sediment_supply_known": False,
        "plan_identity": parent["identity_sha256"],
        "hybrid_identity": loaded["manifest"]["hybrid_plan_identity_sha256"],
        "bundle_identity": loaded["manifest"]["identity_sha256"],
        "input_hashes": loaded["input_hashes"],
        "parameters": asdict(loaded["config"]),
        "audit": result["audit"],
        "source_node": 8470,
        "receiver_node": 8600,
        "source_world_xz_m": sourcexz,
        "receiver_world_xz_m": receiverxz,
        "selected_parent_count": int(partition["selected_parent_mask"].sum()),
        "selected_column_count": int(partition["selected_column_mask"].sum()),
        "selected_area_m2": float(area[partition["selected_column_mask"]].sum()),
        "coastal_column_count": int(partition["coastal_column_mask"].sum()),
        "terminal_ids": partition["terminal_ids"].tolist(),
        "terminal_land_areas_m2": [
            float(area[mask].sum()) for mask in partition["terminal_column_masks"]
        ],
        "selected_Q_m3s_min": float(q.min()),
        "selected_Q_m3s_mean": float(q.mean()),
        "selected_Q_m3s_max": float(q.max()),
        "annual_selected_volume_m3": float(result["annual_selected_volume_m3"]),
        "monthly_selected_volume_m3": result[
            "monthly_selected_volume_m3"
        ].tolist(),
        "annual_terminal_volume_m3": result["annual_terminal_volume_m3"].tolist(),
        "annual_other_receiver_volume_m3": float(
            result["annual_other_receiver_volume_m3"]
        ),
        "units": {
            "time": "s from model-year start",
            "Q": "m3/s",
            "volume": "m3",
            "area": "m2",
            "soil": "mm",
            "world_xz": "m",
        },
        "assumptions": [
            "instantaneous coarse routing",
            "daily apportioned saved monthly forcing",
            "selected upstream supply not complete 8600",
            "other branches not placed along edge",
            "no travel time/fine hydraulics/sediment/delta certification",
            "8m width not derived from Q",
        ],
    }

    args.output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(args.output / "supply.npz", **arrays)
    summary["supply_archive_sha256"] = file_sha256(args.output / "supply.npz")
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8"
    )

    print(json.dumps(summary, indent=2, allow_nan=False))
    print(
        "Q min/mean/max m3/s: %.6f %.6f %.6f"
        % (
            summary["selected_Q_m3s_min"],
            summary["selected_Q_m3s_mean"],
            summary["selected_Q_m3s_max"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
