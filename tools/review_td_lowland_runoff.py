"""Review lowland runoff on the immutable 03 native TD receiver graph."""
import argparse
import html
import json
import os
from pathlib import Path
import sys
import time

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np
from numba import njit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256, identity
from tools.review_large_td_confluence import ELEVATION_LIMITS, load_archive, topology

SOURCE_SHA = "4f6ffcbcc9baf54ecf4ce8dc91c6afb094b181a0d7f7641e753eff1d1bf2a53f"
SOURCE = ROOT / "verification/hydrological-planning-domain/large-td-confluence-20261014-03/native-routing.npz"
WEATHER_SOURCE = ROOT / "verification/hydrological-planning-domain/large-td-lowland-20261014-01/lowland-runoff.npz"
WEATHER_SOURCE_SHA = "e7a3a7b206a84a80cb243f95b783ca3b209f333d1c6ca973c43b8737e5590621"
IMMUTABLE_KEYS = ("original_td_m", "working_height_m", "working_raise_m", "receiver", "topological_order",
                  "contributing_area_m2", "frozen_owner_domain_id", "native_planning_owner_domain_id", "terminal_status")


def sample_monthly_precipitation(metadata, height, *, stripe_rows=128):
    from terrain_pipeline.climate_forcing import sample_climate
    rain = np.empty((12,) + height.shape, np.float64)
    x = metadata["origin_xz_m"][0] + np.arange(height.shape[1]) * metadata["spacing_m"]
    for start in range(0, height.shape[0], stripe_rows):
        stop = min(start + stripe_rows, height.shape[0])
        z = metadata["origin_xz_m"][1] + np.arange(start, stop) * metadata["spacing_m"]
        climate = sample_climate(int(metadata["seed"]), x[None, :], z[:, None], height[start:stop])
        rain[:, start:stop] = climate["monthly_precipitation_mm"]
    provenance = {"algorithm": "metric-noise-climate-v1", "parameter_identity_sha256": climate["parameter_identity_sha256"],
                  "seed": int(metadata["seed"]), "origin_xz_m": metadata["origin_xz_m"],
                  "spacing_m": metadata["spacing_m"], "stripe_rows": stripe_rows,
                  "elevation_input": "immutable original_td_m", "synthetic_not_observed": True}
    return rain, provenance


def product_identity(arrays, metadata):
    return identity(arrays, {key: value for key, value in metadata.items() if key != "product_identity_sha256"})


def network_metrics(receiver, selected, lowland, shape, spacing):
    rec = np.asarray(receiver).ravel()
    mask = np.asarray(selected, bool).ravel()
    low = np.asarray(lowland, bool).ravel()
    ids = np.flatnonzero(mask & (rec >= 0))
    target = rec[ids]
    incoming = np.bincount(target, minlength=rec.size)
    lengths = spacing * np.hypot(target // shape[1] - ids // shape[1], target % shape[1] - ids % shape[1])
    low_area = float(low.sum() * spacing ** 2)
    low_length = float(lengths[low[ids]].sum())
    return {"selected_edge_count": int(ids.size), "head_count": int(np.sum(mask & (rec >= 0) & (incoming == 0))),
            "confluence_count": int(np.sum(incoming >= 2)), "length_km": float(lengths.sum() / 1000.),
            "lowland_area_km2": low_area / 1e6, "lowland_length_km": low_length / 1000.,
            "lowland_drainage_density_km_per_km2": low_length * 1000. / low_area if low_area else None}


@njit(cache=True)
def replay_monthly(local, receiver, order, capacity, perimeter, years, evaporation, release_fraction, month_seconds, q_threshold):
    """Independent recurrence used only by the cold reader."""
    storage = np.zeros(receiver.size)
    mean_q = np.zeros(receiver.size)
    wet = np.zeros(receiver.size, np.uint8)
    evidence = np.zeros((years * 12, 7))
    for step in range(years * 12):
        evidence[step, 0] = storage.sum()
        incoming = local[step % 12].copy()
        flow = np.zeros(receiver.size)
        for cell in order:
            total = incoming[cell] + storage[cell]
            held = min(total, capacity[cell])
            spill = total - held
            loss = min(held, evaporation) if capacity[cell] > 0 else 0.
            release = (held - loss) * release_fraction
            storage[cell] = held - loss - release
            flow[cell] = spill + release
            evidence[step, 2] += loss
            evidence[step, 3] += release
            evidence[step, 4] += spill if capacity[cell] > 0 else 0.
            if receiver[cell] >= 0:
                incoming[receiver[cell]] += flow[cell]
            elif perimeter[cell]:
                evidence[step, 5] += flow[cell]
            else:
                evidence[step, 6] += flow[cell]
        evidence[step, 1] = storage.sum()
        if step >= (years - 1) * 12:
            mean_q += flow / month_seconds.sum()
            wet += flow >= q_threshold * month_seconds[step % 12]
    return storage, mean_q, wet, evidence


def cold_audit(arrays, metadata, source, source_metadata):
    """Recompute receiver reachability and balances without calling the classifier."""
    rec = arrays["receiver"].ravel()
    h = arrays["original_td_m"]
    order, cycles = topology(rec)
    flags = arrays["object_flags"].ravel()
    permanent = arrays["permanent_channel_mask"].ravel().astype(bool)
    seasonal = arrays["seasonal_channel_mask"].ravel().astype(bool)
    lowland = arrays["lowland_mask"].ravel().astype(bool)
    expected_first = np.full(rec.size, -1, np.int64)
    terminal = np.arange(rec.size, dtype=np.int64)
    for cell in order[::-1]:
        if rec[cell] >= 0:
            terminal[cell] = terminal[rec[cell]]
        if flags[cell]:
            expected_first[cell] = cell
        elif rec[cell] >= 0:
            expected_first[cell] = expected_first[rec[cell]]
    first = arrays["first_receiving_object_id"].ravel()
    expected_flags = np.zeros(rec.size, flags.dtype)
    found = expected_first >= 0
    expected_flags[found] = flags[expected_first[found]]
    ids = np.flatnonzero((permanent | seasonal) & (rec >= 0))
    nonriver = flags.astype(np.uint16) & 30
    class_valid = np.isin(nonriver, [0, 2, 4, 8, 16])
    rain_volume = arrays["monthly_precipitation_mm"] * metadata["spacing_m"] ** 2 / 1000.
    local = arrays["monthly_local_runoff_m3"]
    ledger = metadata["classification"]["month_ledger"]
    residuals = []
    input_errors = []
    storage_links = []
    for index, month in enumerate(ledger):
        residuals.append(month["input_runoff_m3"] + month["storage_before_m3"] - month["storage_after_m3"]
                         - month["evaporation_m3"] - month["unknown_boundary_export_m3"] - month["unresolved_terminal_export_m3"])
        input_errors.append(month["input_runoff_m3"] - float(local[index % 12].sum()))
        if index:
            storage_links.append(month["storage_before_m3"] - ledger[index - 1]["storage_after_m3"])
    volume_scale = max(1., float(local.sum()))
    tolerance = volume_scale * 1e-10
    immutable = {key: bool(key in arrays and np.array_equal(arrays[key], source[key]))
                 for key in IMMUTABLE_KEYS if key in source}
    capacity = arrays["storage_capacity_m3"]
    storage = arrays["final_storage_m3"]
    config = metadata["classification"]["config"]
    perimeter = np.zeros(h.shape, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    month_seconds = np.broadcast_to(np.asarray(metadata["classification"]["monthly_seconds"], np.float64), (12,))
    replay_storage, replay_q, replay_wet, replay_ledger = replay_monthly(local.reshape(12, -1), rec, order,
        capacity.ravel(), perimeter.ravel(), config["simulation_years"],
        config["monthly_evaporation_depth_m"] * metadata["spacing_m"] ** 2,
        config["monthly_release_fraction"], month_seconds, config["channel_q_threshold_m3_s"])
    ledger_keys = ("storage_before_m3", "storage_after_m3", "evaporation_m3", "storage_release_m3", "overflow_m3",
                   "unknown_boundary_export_m3", "unresolved_terminal_export_m3")
    saved_evidence = np.asarray([[month[key] for key in ledger_keys] for month in ledger])
    concentration = arrays["contributing_area_m2"].ravel() >= np.where(lowland,
        config["lowland_initiation_area_m2"], config["upland_initiation_area_m2"])
    permanent_seeds = concentration & (replay_wet >= config["persistent_months"])
    seasonal_seeds = concentration & (replay_wet >= config["seasonal_months"])
    expected_permanent = permanent_seeds.copy()
    expected_seasonal = seasonal_seeds.copy()
    for cell in order:
        if rec[cell] >= 0:
            expected_permanent[rec[cell]] |= expected_permanent[cell]
            expected_seasonal[rec[cell]] |= expected_seasonal[cell]
    expected_seasonal &= ~expected_permanent
    saved_order_valid = np.array_equal(arrays["topological_order"], source["topological_order"])
    no_object = expected_first < 0
    sources = np.flatnonzero(rec >= 0)
    targets = rec[sources]
    step_row = np.abs(targets // h.shape[1] - sources // h.shape[1])
    step_col = np.abs(targets % h.shape[1] - sources % h.shape[1])
    gates = {"source_arrays_exact": all(immutable.values()), "acyclic": cycles == 0,
             "saved_order_immutable": saved_order_valid,
             "local_d8": bool(np.all((step_row <= 1) & (step_col <= 1) & (step_row + step_col > 0))),
             "product_identity": metadata["product_identity_sha256"] == product_identity(arrays, metadata),
             "source_identity": metadata["source_identity"] == source_metadata["source_identity"],
             "planning_identity": metadata["native_planning_identity_sha256"] == source_metadata["native_planning_identity_sha256"],
             "first_receiver_reachable_and_first": bool(np.array_equal(first, expected_first)),
             "first_receiver_flags": bool(np.array_equal(arrays["first_receiving_object_flags"].ravel(), expected_flags)),
             "unassigned_receivers_explicit": bool(np.all(first[no_object] == -1)),
             "active_downstream_continuity": bool(np.all(flags[rec[ids]] != 0)),
             "permanent_downstream_continuity": bool(np.all(permanent[rec[np.flatnonzero(permanent & (rec >= 0))]])),
             "seasonal_downstream_continuity": bool(np.all((permanent | seasonal)[rec[np.flatnonzero(seasonal & (rec >= 0))]])),
             "classification_codes": bool(np.all(flags <= 31) and class_valid.all()),
             "river_flags_match_masks": bool(np.array_equal((flags & 1) > 0, permanent | seasonal)),
             "channel_masks_disjoint": not bool(np.any(permanent & seasonal)),
             "rain_runoff_partition": bool(np.allclose(local, rain_volume * .5, rtol=1e-15, atol=0.)),
             "finite_nonnegative_monthly_runoff": bool(np.isfinite(local).all() and np.all(local >= 0)),
             "finite_storage_within_capacity": bool(np.isfinite(storage).all() and np.isfinite(capacity).all()
                  and np.all(storage >= 0) and np.all(capacity >= storage - tolerance)),
             "monthly_balance": max(map(abs, residuals), default=0.) <= tolerance,
             "monthly_input_complete": max(map(abs, input_errors), default=0.) <= tolerance,
             "monthly_storage_continuity": max(map(abs, storage_links), default=0.) <= tolerance,
             "final_storage_matches_ledger": abs(float(storage.sum()) - ledger[-1]["storage_after_m3"]) <= tolerance,
             "independent_storage_replay": bool(np.allclose(storage.ravel(), replay_storage, rtol=1e-12, atol=1e-8)),
             "independent_flow_replay": bool(np.allclose(arrays["mean_routed_q_m3_s"].ravel(), replay_q, rtol=1e-12, atol=1e-12)),
             "independent_wet_month_replay": bool(np.array_equal(arrays["wet_month_count"].ravel(), replay_wet)),
             "independent_month_ledger_replay": bool(np.allclose(saved_evidence, replay_ledger, rtol=1e-12, atol=tolerance)),
             "permanent_seed_evidence": bool(np.array_equal(arrays["permanent_initiation_mask"].ravel(), permanent_seeds)),
             "seasonal_seed_evidence": bool(np.array_equal(arrays["seasonal_initiation_mask"].ravel(), seasonal_seeds & ~permanent_seeds)),
             "channel_selection_from_seed_closure": bool(np.array_equal(permanent, expected_permanent)
                  and np.array_equal(seasonal, expected_seasonal))}
    if "last_year_outflow_m3" in arrays:
        out = arrays["last_year_outflow_m3"].ravel()
        incoming = np.bincount(rec[sources], weights=out[sources], minlength=rec.size)
        cell_residual = arrays["last_year_local_runoff_m3"].ravel() + incoming + arrays["last_year_initial_storage_m3"].ravel()
        cell_residual -= out + arrays["last_year_evaporation_m3"].ravel() + storage.ravel()
        gates["saved_per_cell_last_year_water_balance"] = bool(np.all(np.abs(cell_residual) <= tolerance))
    baseline = np.zeros(rec.size, bool)
    baseline[source["selected_edge_source_ids"]] = True
    report = {"gates": gates, "passed": all(gates.values()), "immutable_arrays": immutable,
              "monthly_balance_max_abs_m3": max(map(abs, residuals), default=0.),
              "monthly_input_max_abs_m3": max(map(abs, input_errors), default=0.),
              "unassigned_object_explicit_terminal_export_cell_count": int(no_object.sum()),
              "unassigned_object_perimeter_destination_cell_count": int(np.sum(no_object & perimeter.ravel()[terminal])),
              "unassigned_object_interior_destination_cell_count": int(np.sum(no_object & ~perimeter.ravel()[terminal])),
              "annual_first_object_delivered_runoff_m3": float(local.reshape(12, -1)[:, found].sum()),
              "annual_unassigned_perimeter_delivered_runoff_m3": float(local.reshape(12, -1)[:, no_object & perimeter.ravel()[terminal]].sum()),
              "annual_unassigned_interior_delivered_runoff_m3": float(local.reshape(12, -1)[:, no_object & ~perimeter.ravel()[terminal]].sum()),
              "baseline_03": network_metrics(rec, baseline, lowland, h.shape, metadata["spacing_m"]),
              "permanent_candidate": network_metrics(rec, permanent, lowland, h.shape, metadata["spacing_m"]),
              "all_channel_candidates": network_metrics(rec, permanent | seasonal, lowland, h.shape, metadata["spacing_m"]),
              "class_cell_counts": {name: int(np.sum((flags & code) > 0)) for name, code in
                  (("river", 1), ("wetland", 2), ("shallow_lake", 4), ("seasonal_swale", 8), ("floodplain", 16))},
              "annual_rain_volume_m3": float(rain_volume.sum()), "annual_delivered_runoff_m3": float(local.sum()),
              "annual_outside_delivered_runoff_partition_m3": float((rain_volume * .5).sum()),
              "interpretation": "Candidate classes are not calibrated perennial rivers; finite storage is a routing bookkeeping prototype, not a solved lake. The 0.5 rainfall remainder is outside delivered runoff, not independently solved land ET. Perimeter exports have unknown continuation, not sea."}
    return report


def generate(source, source_metadata, source_path, source_sha):
    from terrain_pipeline.runoff import classify_and_route as classify_and_route
    rain, climate = sample_monthly_precipitation(source_metadata, source["original_td_m"])
    local = .5 * rain / 1000. * source_metadata["spacing_m"] ** 2
    result = classify_and_route(source["original_td_m"], source["working_raise_m"], source["receiver"],
                               source["topological_order"], source["contributing_area_m2"], source_metadata["spacing_m"], local)
    arrays = {key: source[key] for key in IMMUTABLE_KEYS if key in source}
    arrays.update(result["arrays"])
    arrays.update(monthly_precipitation_mm=rain, monthly_local_runoff_m3=local)
    metadata = {"schema": "td-lowland-runoff-review-v1", "source_identity": source_metadata["source_identity"],
                "native_planning_identity_sha256": source_metadata["native_planning_identity_sha256"],
                "routing_identity": source_metadata["routing_identity"],
                "source_archive": {"path": str(source_path.resolve()), "sha256": source_sha},
                "seed": int(source_metadata["seed"]), "origin_xz_m": source_metadata["origin_xz_m"],
                "spacing_m": source_metadata["spacing_m"], "climate": climate, "classification": result["metadata"],
                "runoff_coefficient": .5, "outside_delivered_runoff_coefficient": .5,
                "coordinate_convention": "row z south, column x east; absolute meters; native cell IDs unchanged",
                "resources": {"max_cpu_cores": 2, "priority": "BelowNormal", "numeric_threads": 1},
                "calibrated_perennial": False, "lake_solved": False, "perimeter_is_sea": False}
    metadata["product_identity_sha256"] = product_identity(arrays, metadata)
    return arrays, metadata


def render(source, arrays, metadata, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from tools.compare_hydrology_projection_naturalness import fixed_hillshade
    h = arrays["original_td_m"]
    spacing = metadata["spacing_m"]
    ox, oz = metadata["origin_xz_m"]
    extent = np.array([ox-spacing/2, ox+(h.shape[1]-.5)*spacing, oz+(h.shape[0]-.5)*spacing, oz-spacing/2])/1000.
    cmap = LinearSegmentedColormap.from_list("fixed-relief", ["#123a9b", "#00a8d5", "#27bb72", "#f3e85b", "#ef9a33", "#cb2d32"])
    norm = Normalize(*ELEVATION_LIMITS)
    rgb = np.clip(cmap(norm(h))[..., :3] * (.55 + .65 * fixed_hillshade(h, spacing)[..., None]), 0., 1.)
    rec = arrays["receiver"].ravel()
    def xy(ids):
        return np.c_[ox + ids % h.shape[1]*spacing, oz + ids // h.shape[1]*spacing] / 1000.
    def lines(ax, ids, color, label, style="solid"):
        ids = np.asarray(ids)
        ids = ids[rec[ids] >= 0]
        segments = np.stack([xy(ids), xy(rec[ids])], axis=1)
        ax.add_collection(LineCollection(segments, colors="white", linewidths=1.5, alpha=.85))
        ax.add_collection(LineCollection(segments, colors=color, linewidths=.7, linestyles=style, label=label))
    def draw(ax, old=False, zoom=False):
        ax.imshow(rgb, extent=extent, interpolation="nearest")
        if old:
            lines(ax, source["selected_edge_source_ids"], "#053455", "03 / area >= 1 km2")
        else:
            flags = arrays["object_flags"].reshape(h.shape)
            overlay = np.zeros(h.shape + (4,))
            for code, color, name in [(2, [.05,.95,.65,.7], "Wetland candidate"), (4, [.0,.8,1.,.8], "Shallow lake candidate"),
                                      (8, [.95,.1,.65,.65], "Seasonal swale candidate"), (16, [.75,.15,.9,.5], "Floodplain candidate")]:
                overlay[(flags & code) > 0] = color
                ax.plot([], [], color=color[:3], linewidth=4, label=name)
            ax.imshow(overlay, extent=extent, interpolation="nearest")
            lines(ax, np.flatnonzero(arrays["permanent_channel_mask"].ravel()), "#053455", "Persistent channel candidate")
            lines(ax, np.flatnonzero(arrays["seasonal_channel_mask"].ravel()), "#9d0054", "Seasonal channel candidate", "dashed")
        ax.set(xlabel="World x east (km)", ylabel="World z south (km)", aspect="equal")
        if zoom:
            low = np.flatnonzero(arrays["lowland_mask"].ravel())
            old_selected = np.zeros(h.size, bool)
            old_selected[source["selected_edge_source_ids"]] = True
            removed = np.flatnonzero(old_selected & arrays["lowland_mask"].ravel()
                & ~(arrays["permanent_channel_mask"].ravel() | arrays["seasonal_channel_mask"].ravel()))
            candidates = removed if removed.size else low
            chosen = candidates[np.argmax(arrays["contributing_area_m2"].ravel()[candidates])] if candidates.size else h.size // 2
            point = xy(np.array([chosen]))[0]
            ax.set_xlim(max(extent[0], point[0]-2.5), min(extent[1], point[0]+2.5))
            ax.set_ylim(min(extent[2], point[1]+2.5), max(extent[3], point[1]-2.5))
        ax.legend(loc="lower left", fontsize=7)
    fig, axes = plt.subplots(1, 2, figsize=(19, 10), constrained_layout=True)
    draw(axes[0], old=True); draw(axes[1])
    axes[0].set_title("Immutable 03 selection"); axes[1].set_title("Lowland runoff / equal line width comparison")
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=axes, label="Original elevation (m), fixed original scale", shrink=.7)
    fig.savefig(output / "comparison-full.png", dpi=160); plt.close(fig)
    for name, zoom in [("full-region.png", False), ("lowland-zoom.png", True)]:
        fig, ax = plt.subplots(figsize=(12, 11), constrained_layout=True)
        draw(ax, zoom=zoom)
        ax.set_title("Uncalibrated lowland candidates / unknown perimeter continuation")
        fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, label="Original elevation (m), fixed original scale", shrink=.7)
        fig.savefig(output / name, dpi=160); plt.close(fig)
    return ["comparison-full.png", "full-region.png", "lowland-zoom.png"]


def cold_weather_audit(arrays, metadata, source):
    """Audit event water independently from cumulative cell evidence and source topology."""
    rec = source["receiver"].ravel()
    local = arrays["cumulative_local_runoff_m3"].ravel()
    outflow = arrays["cumulative_outflow_m3"].ravel()
    incoming = local.copy()
    routed = rec >= 0
    np.add.at(incoming, rec[routed], outflow[routed])
    initial = arrays["initial_storage_m3"].ravel()
    final = arrays["final_storage_m3"].ravel()
    loss = arrays["cumulative_evaporation_m3"].ravel()
    residual = initial + incoming - final - loss - outflow
    tolerance = max(1., float(local.sum())) * 1e-10
    ledger = metadata["step_ledger"]
    step_residual = [row["local_runoff_m3"] + row["storage_before_m3"] - row["storage_after_m3"]
                     - row["evaporation_m3"] - row["outlet_m3"] for row in ledger]
    partition_residual = [row["rain_volume_m3"] - row["local_runoff_m3"] - row["outside_delivered_runoff_m3"] for row in ledger]
    links = [ledger[i]["storage_before_m3"] - ledger[i-1]["storage_after_m3"] for i in range(1, len(ledger))]
    mask_keys = ("permanent_channel_mask", "seasonal_channel_mask", "object_flags")
    source_masks = {key: identity({key: source[key]}, {}) for key in mask_keys}
    graph_keys = ("receiver", "topological_order", "original_td_m")
    graph_identity = identity({key: source[key] for key in graph_keys}, {})
    capacity = source["storage_capacity_m3"].ravel()
    active = arrays["event_active_seasonal_mask"].ravel().astype(bool)
    height = source["original_td_m"]
    perimeter = np.zeros(height.shape, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    cell_tolerance = 1e-8 + 1e-10 * (initial + incoming)
    maximum_storm_intensity = max(row["max_local_storm_mm_h"] for row in ledger)
    maximum_area_mean_storm = max(row["storm_rain_volume_m3"] for row in ledger) / (height.size * metadata["spacing_m"]**2) * 1000.
    gates = {
        "event_product_identity": metadata["product_identity_sha256"] == product_identity(arrays, metadata),
        "fixed_source_masks": metadata["fixed_source_mask_identities"] == source_masks,
        "immutable_source_graph_and_terrain": metadata["fixed_source_graph_identity"] == graph_identity,
        "deterministic_forcing_identity": metadata["forcing_identity_sha256"] == identity({}, metadata["forcing"]),
        "initial_storage_from_source": bool(np.array_equal(initial, source["final_storage_m3"].ravel())),
        "finite_nonnegative_evidence": all(bool(np.all(np.isfinite(value)) and np.all(value >= 0.)) for value in arrays.values()),
        "finite_storage_capacity": bool(np.all(final <= capacity + tolerance) and np.all(arrays["peak_storage_m3"].ravel() <= capacity + tolerance)),
        "independent_per_cell_water_balance": bool(np.all(np.abs(residual) <= cell_tolerance)),
        "hourly_event_water_balance": max(map(abs, step_residual), default=0.) <= tolerance,
        "rain_partition": max(map(abs, partition_residual), default=0.) <= tolerance,
        "seasonal_plus_storm_rain_partition": all(abs(row["rain_volume_m3"] - row["seasonal_rain_volume_m3"] - row["storm_rain_volume_m3"]) <= tolerance for row in ledger),
        "perimeter_export_matches_cells": abs(float(outflow[~routed & perimeter.ravel()].sum()) - sum(row["unknown_boundary_export_m3"] for row in ledger)) <= tolerance,
        "interior_export_matches_cells": abs(float(outflow[~routed & ~perimeter.ravel()].sum()) - sum(row["unresolved_terminal_export_m3"] for row in ledger)) <= tolerance,
        "every_step_storage_bounds": all(row["storage_max_capacity_excess_m3"] <= 1e-8 and row["storage_min_m3"] >= 0. for row in ledger),
        "storage_step_continuity": max(map(abs, links), default=0.) <= tolerance,
        "cumulative_local_matches_steps": abs(float(local.sum()) - sum(row["local_runoff_m3"] for row in ledger)) <= tolerance,
        "cumulative_et_matches_steps": abs(float(loss.sum()) - sum(row["evaporation_m3"] for row in ledger)) <= tolerance,
        "cumulative_outlets_match_steps": abs(float(outflow[~routed].sum()) - sum(row["outlet_m3"] for row in ledger)) <= tolerance,
        "active_seasonal_subset_of_fixed_candidates": bool(np.all(~active | source["seasonal_channel_mask"].ravel().astype(bool))),
        "no_permanent_promotion": "permanent_channel_mask" not in arrays,
        "storage_endpoints_match_steps": abs(float(initial.sum())-ledger[0]["storage_before_m3"]) <= tolerance and abs(float(final.sum())-ledger[-1]["storage_after_m3"]) <= tolerance,
    }
    budget_passed = all(gates.values())
    if metadata.get("require_strong_storm", False):
        gates["declared_stress_storm_present"] = maximum_storm_intensity >= metadata["stress_min_local_intensity_mm_h"]
    return {"passed": all(gates.values()), "gates": gates, "cell_balance_max_abs_m3": float(np.max(np.abs(residual), initial=0.)),
            "budget_and_identity_passed": budget_passed,
            "max_local_storm_mm_h": maximum_storm_intensity, "max_area_mean_storm_mm_h": maximum_area_mean_storm,
            "storage_initial_peak_final_m3": [float(arrays[key].sum()) for key in ("initial_storage_m3", "peak_storage_m3", "final_storage_m3")],
            "step_balance_max_abs_m3": max(map(abs, step_residual), default=0.), "tolerance_m3": tolerance,
            "event_active_seasonal_cells": int(active.sum()), "steps": len(ledger),
            "initial_peak_final_active_seasonal_counts": [int(np.sum(source["seasonal_channel_mask"].astype(bool) & (arrays[key] >= metadata["channel_q_threshold_m3_s"]))) for key in ("before_q_m3_s", "peak_q_m3_s", "after_q_m3_s")],
            "interpretation": "Synthetic hourly event response; fixed permanent and seasonal candidates. Rain outside delivered runoff is an explicit unsolved land partition. Perimeter export has unknown continuation; interior terminal export is unresolved. No perennial calibration or solved lake is claimed."}


def generate_weather(source, source_metadata, source_path, source_sha, *, hours=72, start_seconds=0., storm_radius_m=22000., require_strong_storm=False):
    from dataclasses import asdict
    from terrain_pipeline.climate_forcing import NoiseStormParameters as StormParameters, interval_seasonal_storm_rain_mm
    from terrain_pipeline.runoff import LowlandRunoffConfig as LowlandRunoffConfig
    from terrain_pipeline.runoff import prepare_event_routing as prepare_event_routing
    shape = source["original_td_m"].shape
    spacing = source_metadata["spacing_m"]
    perimeter = np.zeros(shape, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    config = source_metadata["classification"]["config"]
    storm = StormParameters(occurrence_probability=1., max_radius_m=storm_radius_m)
    baseline_only = StormParameters(occurrence_probability=0.)
    router = prepare_event_routing(source["receiver"], source["topological_order"], source["storage_capacity_m3"],
                                  source["final_storage_m3"], perimeter, spacing, config=LowlandRunoffConfig(**config))
    arrays = {"initial_storage_m3": source["final_storage_m3"].copy(),
              "cumulative_local_runoff_m3": np.zeros(shape), "cumulative_outflow_m3": np.zeros(shape),
              "cumulative_evaporation_m3": np.zeros(shape)}
    rows = []
    ox, oz = source_metadata["origin_xz_m"]
    x = ox + np.arange(shape[1]) * spacing
    peak_storm = -1.
    peak_storage = float(arrays["initial_storage_m3"].sum())
    arrays["peak_storage_m3"] = arrays["initial_storage_m3"].copy()
    threshold = config["channel_q_threshold_m3_s"]
    active = np.zeros(shape, bool)
    for step in range(hours):
        begin = start_seconds + step * 3600.
        rain = np.empty(shape)
        storm_volume = 0.
        max_local_storm = 0.
        seasonal_volume = 0.
        for start in range(0, shape[0], 128):
            stop = min(start + 128, shape[0])
            z = oz + np.arange(start, stop) * spacing
            forcing = interval_seasonal_storm_rain_mm(int(source_metadata["seed"]), x[None, :], z[:, None], begin, begin+3600.,
                monthly_precipitation_mm=source["monthly_precipitation_mm"][:, start:stop],
                storm_parameters=storm if 12 <= step < 36 else baseline_only)
            event_depth = forcing["storm_depth_mm"] if 12 <= step < 36 else 0.
            rain[start:stop] = forcing["seasonal_depth_mm"] + event_depth
            storm_volume += float(np.sum(event_depth)) * spacing**2 / 1000.
            max_local_storm = max(max_local_storm, float(np.max(event_depth)))
            seasonal_volume += float(forcing["seasonal_depth_mm"].sum()) * spacing**2 / 1000.
        rain_volume = float(rain.sum()) * spacing**2 / 1000.
        local = rain * (.5 * spacing**2 / 1000.)
        before = float(router.storage.sum())
        result = router.step(local, 3600.)
        storage = result["arrays"]["storage_m3"].reshape(shape)
        q = result["arrays"]["routed_q_m3_s"].reshape(shape)
        out = result["arrays"]["outflow_m3"].reshape(shape)
        et = result["arrays"]["evaporation_m3"].reshape(shape)
        arrays["cumulative_local_runoff_m3"] += local
        arrays["cumulative_outflow_m3"] += out
        arrays["cumulative_evaporation_m3"] += et
        active |= source["seasonal_channel_mask"].astype(bool) & (q >= threshold)
        if step == 0:
            arrays["before_q_m3_s"] = q.copy()
        if storm_volume > peak_storm:
            peak_storm = storm_volume
            peak_step = step
            arrays["peak_q_m3_s"] = q.copy()
        total_storage = float(storage.sum())
        if total_storage > peak_storage:
            peak_storage = total_storage
            arrays["peak_storage_m3"] = storage.copy()
        rows.append({"step": step, "start_seconds": begin, "interval_seconds": 3600., "seasonal_rain_volume_m3": seasonal_volume,
            "max_local_storm_mm_h": max_local_storm,
            "storm_rain_volume_m3": storm_volume, "rain_volume_m3": rain_volume, "local_runoff_m3": float(local.sum()),
            "outside_delivered_runoff_m3": rain_volume*.5, "storage_before_m3": before, "storage_after_m3": total_storage,
            "evaporation_m3": float(et.sum()), "outlet_m3": float(out.ravel()[source["receiver"].ravel() < 0].sum()),
            "storage_release_m3": float(result["ledger"]["storage_release_m3"]), "overflow_m3": float(result["ledger"]["overflow_m3"]),
            "storage_max_capacity_excess_m3": float(np.max(storage - source["storage_capacity_m3"])),
            "storage_min_m3": float(storage.min()), "active_seasonal_cells": int(np.sum(source["seasonal_channel_mask"].astype(bool) & (q >= threshold))),
            "unknown_boundary_export_m3": float(out.ravel()[(source["receiver"].ravel() < 0) & perimeter.ravel()].sum()),
            "unresolved_terminal_export_m3": float(out.ravel()[(source["receiver"].ravel() < 0) & ~perimeter.ravel()].sum())})
        rows[-1]["water_balance_residual_m3"] = rows[-1]["local_runoff_m3"] + before - total_storage - rows[-1]["evaporation_m3"] - rows[-1]["outlet_m3"]
        if shape[0]*shape[1] > 100000 and (step+1)%12 == 0:
            print(json.dumps({"weather_hours_completed": step+1, "storm_rain_m3": storm_volume, "storage_m3": total_storage}), flush=True)
    arrays.update(final_storage_m3=storage.copy(), after_q_m3_s=q.copy(), event_active_seasonal_mask=active)
    metadata = {"schema": "td-lowland-weather-response-v1", "source_archive": {"path": str(source_path.resolve()), "sha256": source_sha},
        "seed": int(source_metadata["seed"]), "spacing_m": spacing, "origin_xz_m": source_metadata["origin_xz_m"],
        "step_ledger": rows, "peak_storm_step": peak_step, "forcing": {"storm_parameters": asdict(storm), "start_seconds": start_seconds,
        "hours": hours, "interval_seconds": 3600., "storm_enabled_scenario_hours": [12, 36], "seasonal_algorithm": "smooth-month-center-exact-interval", "synthetic_not_observed": True},
        "initial_storage_context": "immutable monthly final state; next year day zero scenario continuation",
        "channel_q_threshold_m3_s": threshold,
        "require_strong_storm": bool(require_strong_storm), "stress_min_local_intensity_mm_h": 5.,
        "stress_criterion_context": "5 mm/hour at a native cell is a declared scenario demonstration criterion, not a calibrated physical classification threshold",
        "source_identity": source_metadata.get("source_identity"), "native_planning_identity_sha256": source_metadata.get("native_planning_identity_sha256"),
        "routing_identity": source_metadata.get("routing_identity"),
        "fixed_source_graph_identity": identity({key: source[key] for key in ("receiver", "topological_order", "original_td_m")}, {}),
        "fixed_source_mask_identities": {key: identity({key: source[key]}, {}) for key in ("permanent_channel_mask", "seasonal_channel_mask", "object_flags")},
        "resources": {"max_cpu_cores": 2, "priority": "BelowNormal", "numeric_threads": 1}}
    metadata["forcing_identity_sha256"] = identity({}, metadata["forcing"])
    metadata["product_identity_sha256"] = product_identity(arrays, metadata)
    return arrays, metadata


def render_weather(source, arrays, metadata, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from tools.compare_hydrology_projection_naturalness import fixed_hillshade
    height = source["original_td_m"]
    spacing = metadata["spacing_m"]
    ox, oz = metadata["origin_xz_m"]
    extent = np.array([ox-spacing/2, ox+(height.shape[1]-.5)*spacing, oz+(height.shape[0]-.5)*spacing, oz-spacing/2])/1000.
    cmap = LinearSegmentedColormap.from_list("event-relief", ["#123a9b", "#00a8d5", "#27bb72", "#f3e85b", "#ef9a33", "#cb2d32"])
    rgb = np.clip(cmap(Normalize(*ELEVATION_LIMITS)(height))[..., :3] * (.55+.65*fixed_hillshade(height, spacing)[..., None]), 0., 1.)
    rec = source["receiver"].ravel()
    permanent = source["permanent_channel_mask"].ravel().astype(bool)
    seasonal = source["seasonal_channel_mask"].ravel().astype(bool)
    threshold = metadata["channel_q_threshold_m3_s"]
    def lines(ax, mask, color, label, style="solid", width=.65):
        ids = np.flatnonzero(mask & (rec >= 0))
        def xy(cells):
            return np.c_[ox+cells%height.shape[1]*spacing, oz+cells//height.shape[1]*spacing]/1000.
        segments = np.stack([xy(ids), xy(rec[ids])], axis=1)
        ax.add_collection(LineCollection(segments, colors=color, linewidths=width, linestyles=style, label=label))
    phases = [("Initial hour", "before_q_m3_s", 0), ("Peak storm hour", "peak_q_m3_s", metadata["peak_storm_step"]),
              ("Final hour", "after_q_m3_s", len(metadata["step_ledger"])-1)]
    fig, axes = plt.subplots(1, 3, figsize=(22, 8), constrained_layout=True)
    for ax, (title, key, step) in zip(axes, phases):
        ax.imshow(rgb, extent=extent, interpolation="nearest")
        lines(ax, permanent, "#043c67", "Fixed persistent candidate")
        lines(ax, seasonal, "#b80a82", "Fixed seasonal candidate", "dashed")
        lines(ax, seasonal & (arrays[key].ravel() >= threshold), "#00ffff", "Seasonal currently flowing", "dashed", 1.25)
        ax.set(xlabel="World x east (km)", ylabel="World z south (km)", title=f"{title}: hour {step+1}", aspect="equal")
        ax.legend(loc="lower left", fontsize=7)
    fig.savefig(output / "weather-phases.png", dpi=150)
    plt.close(fig)
    rows = metadata["step_ledger"]
    hours = np.arange(len(rows)) + 1
    area = height.size*spacing**2
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True, constrained_layout=True)
    axes[0].plot(hours, [row["seasonal_rain_volume_m3"]/area*1000 for row in rows], label="Smooth seasonal rain")
    axes[0].plot(hours, [row["storm_rain_volume_m3"]/area*1000 for row in rows], label="Short storm rain")
    axes[0].set_ylabel("Area mean rain (mm/hour)")
    axes[0].legend()
    axes[1].plot(hours, [row["storage_after_m3"] for row in rows], color="#a6348d")
    axes[1].set_ylabel("Finite stored water (m3)")
    axes[2].plot(hours, [row["unknown_boundary_export_m3"]/3600 for row in rows], label="Unknown perimeter continuation")
    axes[2].plot(hours, [row["unresolved_terminal_export_m3"]/3600 for row in rows], label="Unresolved interior terminal")
    axes[2].set(xlabel="Scenario hour", ylabel="Outlet Q (m3/s)")
    axes[2].legend()
    for ax in axes:
        ax.grid(alpha=.2)
    fig.savefig(output / "weather-timeseries.png", dpi=150)
    plt.close(fig)
    return ["weather-phases.png", "weather-timeseries.png"]


def weather_main(args):
    from tools.prepare_hydrology_v5_lake import limit_resources
    limit_resources()
    if not 48 <= args.hours <= 72:
        raise ValueError("weather acceptance requires 48..72 hourly steps")
    if args.output.exists():
        raise FileExistsError(args.output)
    start = time.perf_counter()
    source, source_metadata = load_archive(args.source, args.expected_source_sha256)
    if source["original_td_m"].shape != (1280, 1280) or source_metadata["spacing_m"] != 30.:
        raise ValueError("expected immutable 38.4km 1280-square lowland source at 30m")
    arrays, metadata = generate_weather(source, source_metadata, args.source, args.expected_source_sha256, hours=args.hours,
        storm_radius_m=args.storm_radius_m, require_strong_storm=args.require_strong_storm)
    args.output.mkdir(parents=True, exist_ok=False)
    archive = args.output / "weather-response.npz"
    with archive.open("xb") as stream:
        np.savez_compressed(stream, **arrays, metadata_json=np.array(json.dumps(metadata, allow_nan=False)))
    del arrays
    cold, cold_metadata = load_archive(archive)
    report = cold_weather_audit(cold, cold_metadata, source)
    report.update(archive_sha256=file_sha256(archive), source_archive=cold_metadata["source_archive"], resources=cold_metadata["resources"])
    maps = render_weather(source, cold, cold_metadata, args.output)
    report["total_wall_seconds"] = time.perf_counter()-start
    with (args.output / "audit.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    document = '<!doctype html><meta charset="utf-8"><title>TD hourly weather response</title><style>body{font-family:sans-serif;margin:24px;background:#f6f7f8;color:#202326}img{width:100%;height:auto}pre{white-space:pre-wrap}</style>'
    document += '<h1>Hourly weather response on fixed river candidates</h1><p>' + ('Passed' if report["passed"] else 'Failed; evidence retained') + '</p>'
    document += '<p>' + html.escape(report["interpretation"]) + '</p><p>Explicit seeded storm stress scenario: smooth baseline throughout, storm catalogue clipped to scenario hours 12 through 36, then baseline alone. Initial water is the immutable monthly run final state, continuing at year day zero. Candidate geometry remains fixed throughout the event. Same-step bucket routing has no channel travel-time model. Flowing seasonal candidates indicate event activity, without a baseline-only counterfactual claim.</p>'
    for name in maps:
        document += '<img alt="' + name + '" src="' + name + '">'
    document += '<pre>' + html.escape(json.dumps(report, indent=2, allow_nan=False)) + '</pre>'
    (args.output / "preview.html").write_text(document, encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(args.output.resolve()), "total_wall_seconds": report["total_wall_seconds"]}))
    if not report["passed"]:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--expected-source-sha256", default=SOURCE_SHA)
    parser.add_argument("--output", type=Path, default=ROOT / "verification/hydrological-planning-domain/large-td-lowland-20261014-01")
    parser.add_argument("--weather-response", action="store_true")
    parser.add_argument("--hours", type=int, default=72)
    parser.add_argument("--storm-radius-m", type=float, default=22000.)
    parser.add_argument("--require-strong-storm", action="store_true", help="require >=5 mm/hour at a native cell as declared stress-scenario evidence")
    args = parser.parse_args()
    if args.weather_response:
        if args.source == SOURCE:
            args.source = WEATHER_SOURCE
            args.expected_source_sha256 = WEATHER_SOURCE_SHA
        if args.output == ROOT / "verification/hydrological-planning-domain/large-td-lowland-20261014-01":
            args.output = ROOT / "verification/hydrological-planning-domain/large-td-weather-20261014-01"
        return weather_main(args)
    from tools.prepare_hydrology_v5_lake import limit_resources
    limit_resources()
    start = time.perf_counter()
    if args.output.exists():
        raise FileExistsError(args.output)
    source, source_metadata = load_archive(args.source, args.expected_source_sha256)
    if source["original_td_m"].shape != (1280, 1280) or source_metadata["spacing_m"] != 30. or source_metadata["seed"] != 3:
        raise ValueError("expected immutable seed3 native 1280-square TD at 30m")
    if source_metadata.get("planning_policy") != "native-source-replan":
        raise ValueError("03 native planning policy required")
    args.output.mkdir(parents=True, exist_ok=False)
    arrays, metadata = generate(source, source_metadata, args.source, args.expected_source_sha256)
    archive_path = args.output / "lowland-runoff.npz"
    with archive_path.open("xb") as stream:
        np.savez_compressed(stream, **arrays, metadata_json=np.array(json.dumps(metadata, allow_nan=False)))
    del arrays
    cold, cold_metadata = load_archive(archive_path)
    report = cold_audit(cold, cold_metadata, source, source_metadata)
    report.update(archive_sha256=file_sha256(archive_path), source_archive=cold_metadata["source_archive"],
                  resources=cold_metadata["resources"], total_wall_seconds=time.perf_counter()-start)
    with (args.output / "audit.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    maps = render(source, cold, cold_metadata, args.output)
    status = "Passed" if report["passed"] else "Failed; evidence retained"
    document = '<!doctype html><meta charset="utf-8"><title>TD lowland runoff review</title><style>body{font-family:sans-serif;margin:24px;background:#f6f7f8;color:#202326}img{width:100%;height:auto}pre{white-space:pre-wrap}</style>'
    document += '<h1>TD lowland runoff candidates</h1><p>' + status + '</p><p>' + html.escape(report["interpretation"]) + '</p>'
    document += '<p>Same immutable terrain, receiver graph and map extent. Both channel selections use equal line width. Lowland drainage density is normalized by lowland area.</p>'
    for name in maps:
        document += '<img alt="' + html.escape(name) + '" src="' + name + '">'
    document += '<pre>' + html.escape(json.dumps(report, indent=2, allow_nan=False)) + '</pre>'
    (args.output / "preview.html").write_text(document, encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(args.output.resolve())}))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
