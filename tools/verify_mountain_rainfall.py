"""CPU-only rainfall response on pinned, complete Terrain Diffusion mountains."""

import argparse
import base64
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import html
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np

SOURCE_ROOT = ROOT / "verification/metric-rivers/run-20260929T110135621570Z"
SOURCE_NAMES = ("normal_mountain", "pressure_mountain")
EXPECTED = {
    "normal_mountain": {
        "river": "23a6b67e7783e07c2e1082400764877e5efbb36478545e5cd84b1c5f48130334",
        "raw": "0f21d61d1f0fc45b4e8a0cca9344a89b63257a717e6aa7bb5b2814c8c3b84201",
        "provenance": "cef7dddd2026b4f799abca6fdb2d7868b7cc687954a68f65a059f82738b10685",
    },
    "pressure_mountain": {
        "river": "f03f71b7179693d42056cdc232c47cd208706a17184db01e61920208494012d5",
        "raw": "c5fc2886be8048056d278751631309464ebbbe4228de034a05bb57dd9676d5d0",
        "provenance": "d3fc8aec0a68974cc8b7e2173155d301a485f0c4aa463ec4bb1b4b525b891f39",
    },
}
CONSTRAINTS = (
    "Saved Terrain Diffusion geographic_v5 mountains, historically game-conditioned "
    "(base knee/headroom 120 m); legacy metric processing and halo crop already applied. "
    "Input heights minus 126 m change only the datum to sea zero, not the relief. "
    "These are NOT newly unconstrained generated elevations or observed basins. "
    "The lowest-edge outlet is artificial; legacy channel geometry was unresolved. "
    "Only delayed LOCAL hillslope runoff is simulated. Downstream accumulated rates "
    "are instantaneous spatial diagnostics, NOT routed channel hydrographs. "
    "No bed preparation, natural mouth certification or Minecraft acceptance."
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_source(name, source_root=SOURCE_ROOT):
    if name not in SOURCE_NAMES:
        raise ValueError("Unknown pinned mountain")
    path = source_root / f"{name}.npz"
    sidecar = source_root / f"{name}-provenance.json"
    if sha256(sidecar) != EXPECTED[name]["provenance"]:
        raise ValueError("Pinned provenance hash mismatch")
    provenance = json.loads(sidecar.read_text(encoding="utf-8"))
    if (sha256(path) != EXPECTED[name]["river"]
            or provenance["river_npz_sha256"] != EXPECTED[name]["river"]
            or provenance["source_sha256"] != EXPECTED[name]["raw"]):
        raise ValueError("Mountain source hash mismatch")
    with np.load(path, allow_pickle=False) as archive:
        height = archive["input_height"].copy() - provenance["core_sea_elevation_m"]
        receiver = archive["receiver"].astype(np.int64).ravel()
        outlet = archive["outlet_mask"].copy()
        flowline = archive["flowline_mask"].copy()
    if (height.ndim != 2 or not np.isfinite(height).all() or np.ptp(height) <= 0
            or receiver.size != height.size or outlet.shape != height.shape
            or flowline.shape != height.shape):
        raise ValueError("Invalid mountain arrays")
    spacing = float(provenance["spacing_m"])
    if not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("Invalid physical spacing")
    raw_path = ROOT / Path(provenance["source_npz"].replace("\\", "/"))
    raw_available = raw_path.is_file()
    raw_config = None
    if raw_available:
        if sha256(raw_path) != provenance["source_sha256"]:
            raise ValueError("Original TD archive hash mismatch")
        with np.load(raw_path, allow_pickle=False) as archive:
            raw_config = json.loads(str(archive["generation_config"].item()))
    return {"height_m": height, "receiver": receiver, "outlet_mask": outlet,
            "flowline_mask": flowline, "spacing_m": spacing,
            "origin_m_xz": provenance["origin_core_m_xz"], "provenance": provenance,
            "source_path": path, "sidecar_path": sidecar,
            "sidecar_sha256": sha256(sidecar), "raw_path": raw_path,
            "raw_available": raw_available, "raw_config": raw_config}


def response_units(height_m, spacing_m, band_count=64):
    height = np.asarray(height_m, dtype=np.float64)
    if (height.ndim != 2 or not np.isfinite(height).all()
            or not np.isfinite(spacing_m) or spacing_m <= 0
            or not isinstance(band_count, int) or band_count < 1 or band_count > 256):
        raise ValueError("Invalid response-unit inputs")
    land = height > 0
    if not land.any() or np.ptp(height[land]) <= 0:
        raise ValueError("Expected non-flat mountain land")
    edges = np.linspace(height[land].min(), height[land].max(), band_count + 1)
    bands = np.minimum(np.searchsorted(edges, height[land], side="right") - 1,
                       band_count - 1)
    occupied, labels = np.unique(bands, return_inverse=True)
    owner = np.full(height.shape, -1, dtype=np.int32)
    owner[land] = labels
    counts = np.bincount(labels, minlength=occupied.size)
    area = counts.astype(np.float64) * spacing_m ** 2
    mean_height = np.bincount(labels, weights=height[land]) / counts
    return owner, area, mean_height, edges[occupied], edges[occupied + 1]


def downstream_order(receiver, outlet_mask):
    receiver = np.asarray(receiver, dtype=np.int64).ravel()
    outlets = np.asarray(outlet_mask, dtype=bool).ravel()
    if (receiver.size != outlets.size or (receiver < -1).any()
            or (receiver >= receiver.size).any()
            or not np.array_equal(receiver == -1, outlets)):
        raise ValueError("Invalid receiver/outlet graph")
    donors = np.bincount(receiver[receiver >= 0], minlength=receiver.size)
    queue = deque(np.flatnonzero(donors == 0).tolist())
    order = []
    while queue:
        current = queue.popleft()
        order.append(current)
        downstream = receiver[current]
        if downstream >= 0:
            donors[downstream] -= 1
            if donors[downstream] == 0:
                queue.append(int(downstream))
    if len(order) != receiver.size:
        raise ValueError("Cyclic receiver graph")
    return np.asarray(order, dtype=np.int64)


def spatial_sum(local_hru_q, owner, area_m2, spacing_m, receiver, order):
    flow = np.zeros(owner.size, dtype=np.float64)
    land = owner.ravel() >= 0
    labels = owner.ravel()[land]
    flow[land] = local_hru_q[labels] * spacing_m ** 2 / area_m2[labels]
    for current in order:
        downstream = receiver[current]
        if downstream >= 0:
            flow[downstream] += flow[current]
    return flow.reshape(owner.shape)


def rainfall_schedule(mean_height_m, scenario, dt_s=900.0, duration_h=336.0):
    if (not np.isfinite(dt_s) or dt_s <= 0 or not np.isfinite(duration_h)
            or duration_h <= 0 or duration_h * 3600 / dt_s % 1 != 0):
        raise ValueError("Duration must contain whole positive time intervals")
    start_h = np.arange(int(duration_h * 3600 / dt_s)) * dt_s / 3600
    if scenario == "steady":
        intensity = np.where(start_h < 24, 3.0, 0.0)
    elif scenario in ("dry_storm", "wet_storm"):
        intensity = np.select([(start_h >= 6) & (start_h < 9),
                               (start_h >= 9) & (start_h < 12),
                               (start_h >= 12) & (start_h < 18)],
                              [4.0, 24.0, 8.0], default=0.0)
    else:
        raise ValueError("Unknown rainfall scenario")
    mean_height = np.asarray(mean_height_m, dtype=np.float64)
    if mean_height.ndim != 1 or not np.isfinite(mean_height).all() or not mean_height.size:
        raise ValueError("Invalid HRU elevations")
    factor = np.ones(mean_height.size) if scenario == "steady" else (
        0.8 + 0.4 * (mean_height - mean_height.min()) / max(np.ptp(mean_height), 1.0))
    return start_h, intensity[:, None] * factor[None, :]


def embedded_plot(figure):
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=130, bbox_inches="tight")
    plt.close(figure)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def terrain_plot(source, peak_flow):
    height = source["height_m"]
    spacing = source["spacing_m"]
    origin_x, origin_z = source["origin_m_xz"]
    extent = [(origin_x - .5 * spacing) / 1000,
              (origin_x + (height.shape[1] - .5) * spacing) / 1000,
              (origin_z + (height.shape[0] - .5) * spacing) / 1000,
              (origin_z - .5 * spacing) / 1000]
    figure, axis = plt.subplots(figsize=(9, 7))
    image = axis.imshow(height, cmap="terrain", extent=extent)
    figure.colorbar(image, ax=axis, label="Saved mountain elevation above shifted sea zero (m)")
    donors = np.flatnonzero(source["flowline_mask"].ravel() & (source["receiver"] >= 0))
    downstream = source["receiver"][donors]
    donor_z, donor_x = np.unravel_index(donors, height.shape)
    recv_z, recv_x = np.unravel_index(downstream, height.shape)
    lines = np.stack([np.column_stack(((origin_x + donor_x * spacing) / 1000,
                                      (origin_z + donor_z * spacing) / 1000)),
                      np.column_stack(((origin_x + recv_x * spacing) / 1000,
                                      (origin_z + recv_z * spacing) / 1000))], axis=1)
    network = LineCollection(lines, cmap="Blues", linewidths=.7)
    network.set_array(np.log10(np.maximum(peak_flow.ravel()[donors], 1e-9)))
    axis.add_collection(network)
    figure.colorbar(network, ax=axis, label="log10 instantaneous spatial sum (m3/s), NOT channel routing")
    outlet_z, outlet_x = np.nonzero(source["outlet_mask"])
    axis.scatter((origin_x + outlet_x * spacing) / 1000,
                 (origin_z + outlet_z * spacing) / 1000,
                 marker="x", color="red", label="Artificial lowest-edge outlet")
    axis.set(xlabel="Source X (km)", ylabel="Source Z (km)", title="Original saved TD mountain + legacy planned river graph")
    axis.legend(loc="upper right")
    return embedded_plot(figure)


def independent_budget(arrays, dt_s):
    area = arrays["area_m2"]
    rainfall = arrays["rain_mm_h"] * dt_s / 3600 * .001 * area[None, :]
    outflow = arrays["local_q_m3_s"] * dt_s
    if all(f"{reservoir}_mm" in arrays for reservoir in ("soil", "fast", "slow")):
        storage = np.zeros_like(arrays["soil_mm"])
        for reservoir in ("soil", "fast", "slow"):
            volume = arrays[f"{reservoir}_mm"] * .001 * area[None, :]
            if not np.array_equal(volume, arrays[f"{reservoir}_m3"]):
                raise ValueError("Saved native depth and volume storage disagree")
            storage += volume
    else:
        storage = arrays["soil_m3"] + arrays["fast_m3"] + arrays["slow_m3"]
    et = arrays["actual_et_m3"]
    if (storage.shape != (rainfall.shape[0] + 1, rainfall.shape[1])
            or et.shape != rainfall.shape or outflow.shape != rainfall.shape):
        raise ValueError("Unexpected saved state/flux shape")
    for values in (area, rainfall, outflow, storage, et):
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError("Nonfinite or negative saved water quantities")
    change = np.diff(storage, axis=0)
    residual = rainfall - et - outflow - change
    total_residual = float(rainfall.sum() - et.sum() - outflow.sum()
                           - (storage[-1].sum() - storage[0].sum()))
    step_tolerance = 1e-7 + 1e-10 * (np.abs(rainfall) + np.abs(et) + np.abs(outflow)
                                     + np.abs(change) + storage[:-1])
    tolerance = 1e-7 + float(rainfall.sum() + et.sum() + outflow.sum()
                             + storage[0].sum() + storage[-1].sum()) * 1e-10
    if abs(total_residual) > tolerance or (np.abs(residual) > step_tolerance).any():
        raise ValueError("Independent saved water budget failed")
    return {"rainfall_m3": float(rainfall.sum()), "actual_et_m3": float(et.sum()),
            "outflow_m3": float(outflow.sum()),
            "initial_storage_m3": float(storage[0].sum()),
            "final_storage_m3": float(storage[-1].sum()),
            "delta_storage_m3": float(storage[-1].sum() - storage[0].sum()),
            "residual_m3": total_residual,
            "max_hru_step_residual_m3": float(np.max(np.abs(residual))),
            "max_hru_step_tolerance_ratio": float(np.max(np.abs(residual) / step_tolerance)),
            "tolerance_m3": tolerance}


def response_plot(cases, dt_s):
    figure, axes = plt.subplots(4, 1, figsize=(10, 11), sharex=True)
    colors = {"dry_storm": "#b16b26", "wet_storm": "#167ca2", "steady": "#497847"}
    for name, arrays in cases.items():
        area = arrays["area_m2"]
        end_h = (np.arange(arrays["rain_mm_h"].shape[0]) + 1) * dt_s / 3600
        state_h = np.arange(end_h.size + 1) * dt_s / 3600
        color = colors[name]
        axes[0].step(end_h, arrays["rain_mm_h"] @ area / area.sum(),
                     where="pre", color=color, label=name)
        axes[1].plot(end_h, arrays["local_q_m3_s"].sum(axis=1), color=color, label=name)
        axes[2].plot(state_h, arrays["soil_m3"].sum(axis=1) / area.sum() * 1000,
                     color=color, label=name)
        reservoirs = arrays["fast_m3"] + arrays["slow_m3"]
        axes[3].plot(state_h, reservoirs.sum(axis=1) / area.sum() * 1000,
                     color=color, label=name)
    for axis in axes:
        axis.axvspan(24, float(end_h[-1]), alpha=.08, color="blue")
        axis.grid(alpha=.25)
        axis.legend()
    axes[0].set(ylabel="Rainfall (mm/h)", title="Delayed LOCAL hillslope response; shaded: all cases rain-free")
    axes[1].set(ylabel="Sum local runoff (m3/s)")
    axes[2].set(ylabel="Soil storage (mm)")
    axes[3].set(ylabel="Fast + slow storage (mm)", xlabel="Physical time (hours)")
    return embedded_plot(figure)


def write_review(output, report, panels):
    labels = {"normal_mountain": "普通山地", "pressure_mountain": "压力山地"}
    scenario_labels = {"dry_storm": "干土暴雨", "wet_storm": "湿土暴雨", "steady": "均匀持续降雨"}
    sections = []
    for name, panel in panels.items():
        sample = report["samples"][name]
        rows = []
        for scenario, evidence in sample["scenarios"].items():
            budget = evidence["budget"]
            rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
                scenario_labels[scenario], f'{evidence["peak_local_q_m3_s"]:.3f}',
                f'{evidence["recession_q_168h_m3_s"]:.3f} / {evidence["recession_q_336h_m3_s"]:.3f}',
                f'{budget["rainfall_m3"]:.3f}', f'{budget["actual_et_m3"]:.3f}',
                f'{budget["outflow_m3"]:.3f}', f'{budget["delta_storage_m3"]:.3f}',
                f'{budget["residual_m3"]:.3g}')) + "</tr>")
        sections.append(f'<section><h2>{labels[name]}</h2>'
                        f'<p>完整 {sample["shape"]} 山地；面积 {sample["area_m2"]:,.0f} m²；'
                        f'高程 {sample["min_height_m"]:.2f}–{sample["max_height_m"]:.2f} m。'
                        '地图按源采样中心坐标绘制，河线为旧规划接收图。</p>'
                        f'<img alt="原山地与旧规划河网" src="{panel[0]}">'
                        f'<img alt="降雨、局地产流、土壤与快慢库退水" src="{panel[1]}">'
                        '<div class="scroll"><table><thead><tr>'
                        '<th>情景</th><th>峰值局地产流 m³/s</th><th>168h / 336h 退水 m³/s</th>'
                        '<th>降雨 m³</th><th>蒸散 m³</th><th>局地出流 m³</th>'
                        '<th>储量变化 m³</th><th>独立水账残差 m³</th>'
                        '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'
                        '<details><summary>源身份、参数与独立复算证据</summary><pre>'
                        + html.escape(json.dumps(sample, indent=2, ensure_ascii=False))
                        + '</pre></details></section>')
    document = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>TD 山地降雨产流审查</title><style>'
                'body{font:16px system-ui,sans-serif;margin:0 auto;padding:24px;max-width:1100px;'
                'color:#24323c;background:#eef2f4}section{background:white;padding:24px;'
                'margin:24px 0;border-radius:12px}img{width:100%;height:auto}p{line-height:1.7}'
                '.notice{padding:18px;background:#fff0d4}table{border-collapse:collapse;'
                'white-space:nowrap;font-size:14px}td,th{padding:10px;text-align:right;'
                'border-bottom:1px solid #ccd5da}.scroll{overflow:auto}pre{white-space:pre-wrap;'
                'overflow-wrap:anywhere;font-size:12px}</style><body>'
                '<h1>Terrain Diffusion 山地：降雨、产流与退水</h1>'
                '<p>干土暴雨 / 湿土暴雨 / 均匀持续降雨；物理米、平方米、秒。'
                '土壤与快慢水库跨时间持续保存，非双域平面示例。</p>'
                '<div class="notice">来源是历史 geographic_v5 限高条件生成并加工的完整山地；'
                '海拔减去126米仅改变基准，不代表解除历史压缩或重新无约束生成。'
                '出口是人工最低边界。地图河线仅为旧规划接收图，不能证明河床已准备。'
                '沿图累积仅为空间瞬时诊断，绝不是河道传播水文过程。'
                '暴雨的0.8–1.2高程倍率是情景假设，不是已验证的地形降雨物理；持续降雨空间均匀。'
                '图中英文 dry_storm / wet_storm / steady 分别对应干土暴雨、湿土暴雨、持续降雨。'
                '慢库持续获得土壤渗漏补给，48至96小时流量可能上升；延长至14天观察168至336小时退水。'
                '本页不要求真实观测流域认证，也不宣称自然河口或Minecraft验收。</div>'
                + "".join(sections) + '</body></html>')
    (output / "review.html").write_text(document, encoding="utf-8")


def verify_one(output, name, dt_s=900.0):
    from terrain_pipeline.rainfall_runoff import (
        RunoffParameters, simulate_rainfall_runoff, save_rainfall_runoff_npz,
        load_rainfall_runoff_npz,
    )
    from unittest.mock import patch

    source = load_source(name)
    height = source["height_m"]
    owner, area, mean, lower, upper = response_units(height, source["spacing_m"])
    order = downstream_order(source["receiver"], source["outlet_mask"])
    provenance = source["provenance"]
    source_identity = hashlib.sha256(json.dumps({
        "source_sha256": EXPECTED[name]["river"],
        "provenance_sha256": EXPECTED[name]["provenance"],
        "raw_sha256": EXPECTED[name]["raw"],
        "datum_shift_m": -126.0, "response_units": "equal-height-land-bands-v1",
        "band_count": 64,
    }, sort_keys=True).encode("ascii")).hexdigest()
    sample = {"source_identity": source_identity, "shape": list(height.shape),
              "min_height_m": float(height.min()), "max_height_m": float(height.max()),
              "land_cells": int((owner >= 0).sum()), "area_m2": float(area.sum()),
              "hru_count": int(area.size), "spacing_m": source["spacing_m"],
              "origin_m_xz": source["origin_m_xz"], "coordinate_convention": "node/sample centers; Z rows, X columns",
              "datum_shift_m": -126.0, "provenance": provenance,
              "fixed_expected_sha256": EXPECTED[name],
              "raw_available": source["raw_available"], "raw_generation_config": source["raw_config"],
              "constraints": CONSTRAINTS, "dt_s": dt_s, "duration_h": 336.0,
              "scenarios": {}}
    cases = {}
    peak_map = None
    for scenario in ("dry_storm", "wet_storm", "steady"):
        parameters = RunoffParameters(initial_soil_mm=135.0 if scenario == "wet_storm" else 15.0)
        time_h, rain = rainfall_schedule(mean, scenario, dt_s)
        result = simulate_rainfall_runoff(rain, area, dt_s=dt_s,
                                         parameters=parameters, source_id=source_identity)
        native_artifact = output / f"{name}-{scenario}-runoff.npz"
        save_rainfall_runoff_npz(native_artifact, result)
        with patch("terrain_pipeline.rainfall_runoff.simulate_rainfall_runoff",
                   side_effect=AssertionError("Reload must not simulate rainfall")):
            native_loaded = load_rainfall_runoff_npz(native_artifact)
        for key, value in result.items():
            if isinstance(value, np.ndarray) and not np.array_equal(value, native_loaded[key]):
                raise ValueError(f"Native runoff reload changed: {key}")
        arrays = {"area_m2": area, "rain_mm_h": rain,
                  "local_q_m3_s": result["local_q_m3_s"],
                  "actual_et_m3": result["et_volume_m3"]}
        for reservoir in ("soil", "fast", "slow"):
            arrays[f"{reservoir}_m3"] = result[f"{reservoir}_mm"] * .001 * area[None, :]
        local_total = arrays["local_q_m3_s"].sum(axis=1)
        peak_index = int(np.argmax(local_total))
        snapshot_indices = np.unique([peak_index, int(24 * 3600 / dt_s) - 1,
                                     int(168 * 3600 / dt_s) - 1, rain.shape[0] - 1])
        snapshots = np.stack([spatial_sum(arrays["local_q_m3_s"][index], owner, area,
                                           source["spacing_m"], source["receiver"], order)
                              for index in snapshot_indices])
        outlet_sum = snapshots[:, source["outlet_mask"]].sum(axis=1)
        if not np.allclose(outlet_sum, local_total[snapshot_indices], rtol=1e-10, atol=1e-8):
            raise ValueError("Spatial diagnostic duplicates or loses local runoff")
        if scenario == "wet_storm":
            peak_map = snapshots[np.flatnonzero(snapshot_indices == peak_index)[0]]
        scenario_meta = {
            "schema": "mountain-rainfall-demo-v1", "algorithm": "hru-elevation-bands-v1",
            "source_identity": source_identity, "source_expected_sha256": EXPECTED[name],
            "source_provenance": provenance, "raw_generation_config": source["raw_config"],
            "scenario": scenario, "parameters": asdict(parameters), "dt_s": dt_s,
            "coordinate_convention": sample["coordinate_convention"],
            "height_datum": "input_height minus126m; sea zero; processed legacy heights",
            "rainfall_assumption": "steady uniform; storm synthetic elevation multiplier0.8..1.2",
            "snapshot_semantics": "instantaneous downstream spatial sums, NOT routed channel hydrographs",
            "constraints": CONSTRAINTS, "runoff_metadata": result["metadata"],
        }
        saved = dict(arrays)
        saved.update({"height_m": height, "cell_owner": owner,
                      "hru_mean_height_m": mean, "hru_lower_m": lower, "hru_upper_m": upper,
                      "receiver": source["receiver"].reshape(height.shape),
                      "legacy_flowline_mask": source["flowline_mask"],
                      "outlet_mask": source["outlet_mask"],
                      "origin_m_xz": np.asarray(source["origin_m_xz"], dtype=np.float64),
                      "spacing_m": np.asarray(source["spacing_m"]), "dt_s": np.asarray(dt_s),
                      "interval_start_s": time_h * 3600,
                      "snapshot_interval_indices": snapshot_indices,
                      "spatial_diagnostic_q_m3_s": snapshots,
                      "metadata": np.asarray(json.dumps(scenario_meta, sort_keys=True)),
                      "soil_mm": result["soil_mm"], "fast_mm": result["fast_mm"],
                      "slow_mm": result["slow_mm"],
                      "solver_rain_volume_m3": result["rain_volume_m3"],
                      "solver_outflow_volume_m3": result["outflow_volume_m3"],
                      "solver_storage_change_m3": result["storage_change_m3"],
                      "solver_balance_residual_m3": result["balance_residual_m3"]})
        artifact = output / f"{name}-{scenario}.npz"
        if artifact.exists():
            raise FileExistsError(artifact)
        np.savez_compressed(artifact, **saved)
        with np.load(artifact, allow_pickle=False) as archive:
            reloaded = {key: archive[key].copy() for key in arrays}
            for reservoir in ("soil", "fast", "slow"):
                reloaded[f"{reservoir}_mm"] = archive[f"{reservoir}_mm"].copy()
            for key, value in saved.items():
                if not np.array_equal(archive[key], value):
                    raise ValueError(f"Saved array changed: {key}")
            budget = independent_budget(reloaded, float(archive["dt_s"]))
            np.testing.assert_array_equal(archive["area_m2"],
                                          np.bincount(archive["cell_owner"][owner >= 0]) * source["spacing_m"] ** 2)
        cases[scenario] = reloaded
        recession_48 = float(local_total[int(48 * 3600 / dt_s) - 1])
        recession_96 = float(local_total[int(96 * 3600 / dt_s) - 1])
        recession_168 = float(local_total[int(168 * 3600 / dt_s) - 1])
        recession_336 = float(local_total[-1])
        if recession_168 <= 0 or not 0 < recession_336 < recession_168:
            raise ValueError("Expected positive declining rain-free recession")
        sample["scenarios"][scenario] = {
            "npz": artifact.name, "npz_sha256": sha256(artifact),
            "native_runoff_npz": native_artifact.name,
            "native_runoff_npz_sha256": sha256(native_artifact),
            "native_reload_no_simulation": True,
            "parameters": asdict(parameters), "budget": budget,
            "peak_local_q_m3_s": float(local_total[peak_index]),
            "peak_interval_end_h": float((peak_index + 1) * dt_s / 3600),
            "recession_q_48h_m3_s": recession_48,
            "recession_q_96h_m3_s": recession_96,
            "recession_q_168h_m3_s": recession_168,
            "recession_q_336h_m3_s": recession_336,
            "saved_arrays_equal": True, "spatial_sum_preserves_local_total": True}
    wet_peak = sample["scenarios"]["wet_storm"]["peak_local_q_m3_s"]
    dry_peak = sample["scenarios"]["dry_storm"]["peak_local_q_m3_s"]
    if wet_peak <= dry_peak:
        raise ValueError("Wet soil should produce greater storm peak than dry soil")
    sample["wet_minus_dry_peak_m3_s"] = wet_peak - dry_peak
    sample["source_hashes_preserved"] = (
        sha256(source["source_path"]) == EXPECTED[name]["river"]
        and sha256(source["sidecar_path"]) == EXPECTED[name]["provenance"]
        and (not source["raw_available"] or sha256(source["raw_path"]) == EXPECTED[name]["raw"]))
    if not sample["source_hashes_preserved"]:
        raise ValueError("Immutable source changed during verification")
    return sample, (terrain_plot(source, peak_map), response_plot(cases, dt_s))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "verification/mountain-rainfall")
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    if not output_root.is_relative_to(ROOT / "verification"):
        parser.error("Outputs must remain in the workspace verification directory")
    output = output_root / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "mountain-rainfall-demo-v1", "constraints": CONSTRAINTS,
              "samples": {}, "pass": False,
              "code_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path)
                              for path in (Path(__file__), ROOT / "tests/test_mountain_rainfall.py",
                                           ROOT / "docs/mountain-rainfall-v1.md",
                                           ROOT / "terrain_pipeline/rainfall_runoff.py",
                                           ROOT / "tests/test_rainfall_runoff.py",
                                           ROOT / "docs/rainfall-runoff-v1.md")}}
    panels = {}
    for name in SOURCE_NAMES:
        report["samples"][name], panels[name] = verify_one(output, name)
        print(name, "passed independent water budget / wet-dry response / recession", flush=True)
    report["pass"] = True
    if any(sha256(ROOT / path) != digest for path, digest in report["code_sha256"].items()):
        raise ValueError("Implementation changed during verification; rerun after freeze")
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_review(output, report, panels)
    print(output, flush=True)


if __name__ == "__main__":
    main()
