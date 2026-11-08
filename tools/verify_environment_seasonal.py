"""Independent bounded seasonal acceptance on saved seed20261020 TD and river graph."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ORIGIN = (43700, 42100)
SHAPE = (64, 64)
DT_S = 3600.
STEPS = 3
BOUNDARY = {"external_inflow_kg_per_s": 10., "wind_speed_m_s": 1., "uplift_gain": .01}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(child) for child in value]
    return value


def write_json(path, value):
    path.write_text(json.dumps(plain(value), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def source_files(store):
    registry_path = store / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    component = registry["components"][0]
    directory = store / "versions" / component["version"]
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = {registry_path, manifest_path, directory / manifest["network"]["file"]}
    paths.update(Path(page["path"]) for page in registry["pages"])
    for group in ("composition_tiles", "water_tiles"):
        paths.update(directory / item["file"] for item in manifest[group])
    return sorted(paths), registry, manifest, directory


def snapshot(paths):
    return {str(path.resolve()): sha256(path) for path in paths}


def source_masks(manifest, directory):
    result = {}
    for group, names in (("composition_tiles", ("valid_mask",)),
                         ("water_tiles", ("complete_mask", "protected_shore_mask", "upstream_unknown_mask", "channel_mask"))):
        fields = {name: np.zeros(SHAPE, bool) for name in names}
        covered = np.zeros(SHAPE, bool)
        for tile in manifest[group]:
            left, top = tile["origin_native_xz"]
            rows, cols = tile["shape_zx"]
            x0, z0 = max(left, ORIGIN[0]), max(top, ORIGIN[1])
            x1, z1 = min(left + cols, ORIGIN[0] + SHAPE[1]), min(top + rows, ORIGIN[1] + SHAPE[0])
            if x0 >= x1 or z0 >= z1:
                continue
            src = np.s_[z0 - top:z1 - top, x0 - left:x1 - left]
            dst = np.s_[z0 - ORIGIN[1]:z1 - ORIGIN[1], x0 - ORIGIN[0]:x1 - ORIGIN[0]]
            with np.load(directory / tile["file"], allow_pickle=False) as arrays:
                for name in names:
                    fields[name][dst] = arrays[name][src]
            covered[dst] = True
        if not covered.all():
            raise ValueError("source mask tiles do not cover fixed query domain")
        result.update(fields)
    return result


def choose_internal_boundary(context):
    """Choose from immutable geometry and support before running any water event."""
    width = context["height_m"].shape[1]
    receiver = context["receiver"].ravel()
    donors = np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    active = (context["valid_mask"] & ~context["protected_mask"] & ~context["ocean_mask"]).ravel()
    channel = context["river_mask"].ravel()
    keep = active[donors] & active[targets] & channel[donors] & channel[targets]
    pairs = list(zip(donors[keep], targets[keep]))
    for axis, divisor in (("x", 1), ("z", width)):
        def coordinate(node):
            return int(node % width) if divisor == 1 else int(node // width)
        candidates = [(min(coordinate(donor), coordinate(target)) + 1, int(donor), int(target))
                      for donor, target in pairs if coordinate(donor) != coordinate(target)]
        if candidates:
            cut, donor, target = min(candidates)
            return {"axis": axis, "cut_index": cut, "source_donor_local_id": donor,
                    "source_receiver_local_id": target,
                    "selection": "x before z; minimum cut index then donor and target id; both active channel nodes; no event outputs inspected"}
    raise ValueError("fixed source window has no active river edge for an internal query boundary")


def compare(checks, name, actual, expected, *, atol=1.e-8, rtol=2.e-11):
    actual, expected = np.asarray(actual), np.asarray(expected)
    residual = np.asarray(actual - expected, np.float64)
    maximum = float(np.max(np.abs(residual)))
    scale = max(1., float(np.max(np.abs(actual))), float(np.max(np.abs(expected))))
    tolerance = max(atol, rtol * scale)
    checks[name] = {"pass": bool(np.isfinite(residual).all() and maximum <= tolerance),
                    "max_abs_residual": maximum, "tolerance": tolerance}
    return maximum


def condition(checks, name, value):
    checks[name] = {"pass": bool(value)}


def water_inventory(product):
    """Count spendable physical stocks directly; history/network views are excluded."""
    states, seasonal = product["states"], product["seasonal"]
    area = float(product["context"]["spacing_m"]) ** 2
    stocks = {
        "soil_m3": float(states["soil_chemistry"]["water_m3"].sum()),
        "fast_m3": float(seasonal["fast_mm"].sum()) * area / 1000.,
        "slow_m3": float(seasonal["slow_mm"].sum()) * area / 1000.,
        "snow_m3": float(seasonal["snow_swe_mm"].sum()) * area / 1000.,
        "groundwater_m3": float(states["groundwater"]["groundwater_water_m3"].sum()),
        "river_surface_m3": float(states["groundwater"]["surface_water_m3"].sum()),
        "thermal_liquid_m3": float(states["frozen_ground"]["liquid_water_m"].sum()) * area,
        "thermal_ice_m3": float(states["frozen_ground"]["ground_ice_m"].sum()) * area,
        "thermal_snow_m3": float(states["frozen_ground"]["snow_swe_m"].sum()) * area,
        "coastal_m3": float(states["coastal_exchange"]["water_m3"].sum()),
        "pending_coastal_soil_m3": float(product["pending_packets"]["soil_water_m3"].sum()),
        "atmosphere_m3": float(seasonal["climate_state"]["arrays"]["vapour_kg"].sum()) / 1000.,
        "pending_et_m3": float(np.asarray(seasonal["pending_et_kg"]).sum()) / 1000.,
    }
    return {**stocks, "total_m3": sum(stocks.values())}


def route_observation(before, after, dt_s, boundary):
    """Reconstruct the delivered one-edge packets from stocks and public exchange fluxes."""
    context = before["context"]
    transfer = after["last_transfers"]
    surface = before["states"]["groundwater"]["surface_water_m3"].copy()
    flux = after["results"]["groundwater"]["fluxes"]
    surface += flux["surface_input_m3"] + flux["groundwater_to_surface_m3"] + flux["spring_m3"]
    receiver = context["receiver"].ravel()
    donors = np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    x, z = context["node_x_m"].ravel(), context["node_z_m"].ravel()
    distance = np.hypot(x[donors] - x[targets], z[donors] - z[targets])
    roughness = transfer["hydraulic_manning_n"].ravel()[donors]
    fraction = np.minimum(1., .5 * .025 / roughness * dt_s / distance)
    moved = surface.ravel()[donors] * fraction
    expected = surface.copy()
    expected.ravel()[donors] -= moved
    ocean = context["ocean_mask"].ravel()[targets]
    np.add.at(expected.ravel(), targets[~ocean], moved[~ocean])
    coast = np.zeros_like(expected)
    np.add.at(coast.ravel(), targets[ocean], moved[ocean])
    exported = np.where(context["external_receiver_mask"] & (context["receiver"] < 0), expected, 0.)
    expected -= exported
    width = surface.shape[1]
    channel = context["river_mask"].ravel()
    river_edge = channel[donors] & channel[targets]
    # A fixed internal split is a query boundary, never a new climate inflow face.
    donor_coordinate = donors % width if boundary["axis"] == "x" else donors // width
    target_coordinate = targets % width if boundary["axis"] == "x" else targets // width
    crossing = ((donor_coordinate < boundary["cut_index"]) != (target_coordinate < boundary["cut_index"])) & river_edge
    records = [{"donor_local_id": int(donor), "receiver_local_id": int(target), "water_m3": float(amount)}
               for donor, target, amount in zip(donors[crossing], targets[crossing], moved[crossing]) if amount > 0.]
    return expected, coast, exported, records


def step_accounts(checks, before, after, index, dt_s, boundary):
    key = "step_%d_" % index
    transfer = after["last_transfers"]
    area = float(before["context"]["spacing_m"]) ** 2
    s0, s1 = before["seasonal"], after["seasonal"]
    climate = after["results"]["climate"]
    ledger = climate["ledger"]
    precipitation_m3 = float(ledger["precipitation_kg"]) / 1000.
    before_vapour = float(s0["climate_state"]["arrays"]["vapour_kg"].sum())
    after_vapour = float(s1["climate_state"]["arrays"]["vapour_kg"].sum())
    recycled = float(np.asarray(s0["pending_et_kg"]).sum())
    compare(checks, key + "atmosphere", after_vapour - before_vapour,
            BOUNDARY["external_inflow_kg_per_s"] * SHAPE[0] * dt_s + recycled
            - ledger["precipitation_kg"] - ledger["outflow_kg"] - ledger["nondepositing_kg"])
    compare(checks, key + "et_recycled_once", ledger["recycle_kg"], recycled)
    compare(checks, key + "et_spatial_recycle", transfer["seasonal_et_recycle_kg"], s0["pending_et_kg"], atol=0., rtol=0.)
    compare(checks, key + "et_pending_once", np.asarray(s1["pending_et_kg"]).sum(), transfer["g5_et_m3"].sum() * 1000.)
    if np.asarray(s1["pending_et_kg"]).shape == SHAPE:
        compare(checks, key + "et_spatial_pending", s1["pending_et_kg"], transfer["g5_et_m3"] * 1000.)
    else:
        condition(checks, key + "et_spatial_pending", False)
    compare(checks, key + "snow", (s1["snow_swe_mm"] - s0["snow_swe_mm"]) * area / 1000.,
            transfer["seasonal_solid_precip_m3"] - transfer["seasonal_melt_m3"] - transfer["seasonal_sublimation_m3"])
    compare(checks, key + "phase_once", transfer["rainfall_m3"],
            transfer["seasonal_solid_precip_m3"] + transfer["seasonal_liquid_precip_m3"])
    compare(checks, key + "liquid_once", transfer["seasonal_liquid_to_land_m3"],
            transfer["seasonal_liquid_precip_m3"] + transfer["seasonal_melt_m3"])
    compare(checks, key + "soil", after["states"]["soil_chemistry"]["water_m3"] - before["states"]["soil_chemistry"]["water_m3"],
            transfer["g5_infiltration_m3"] - transfer["g5_percolation_m3"] - transfer["g5_et_m3"])
    compare(checks, key + "fast", (s1["fast_mm"] - s0["fast_mm"]) * area / 1000.,
            transfer["seasonal_liquid_to_land_m3"] - transfer["g5_infiltration_m3"] - transfer["g5_fast_release_m3"])
    compare(checks, key + "slow", (s1["slow_mm"] - s0["slow_mm"]) * area / 1000.,
            transfer["g5_percolation_m3"] - transfer["g5_slow_release_m3"])
    compare(checks, key + "release", transfer["g5_release_m3"], transfer["g5_fast_release_m3"] + transfer["g5_slow_release_m3"])
    compare(checks, key + "river_input_once", after["results"]["groundwater"]["fluxes"]["surface_input_m3"], transfer["g5_release_m3"])
    condition(checks, key + "no_duplicate_percolation_gw", not np.any(after["results"]["groundwater"]["fluxes"]["recharge_m3"]))
    expected, coast, exported, crossings = route_observation(before, after, dt_s, boundary)
    compare(checks, key + "river_route", after["states"]["groundwater"]["surface_water_m3"], expected)
    compare(checks, key + "river_coast", transfer["river_to_coast_water_m3"], coast)
    compare(checks, key + "river_export", transfer["window_water_export_m3"], exported)
    inv0, inv1 = water_inventory(before), water_inventory(after)
    entries = {name: after["cumulative_ledger"].get(name, 0.) - before["cumulative_ledger"].get(name, 0.)
               for name in after["cumulative_ledger"]}
    unmodelled = precipitation_m3 - float(transfer["rainfall_m3"].sum())
    external_net = (BOUNDARY["external_inflow_kg_per_s"] * SHAPE[0] * dt_s / 1000.
                    - ledger["outflow_kg"] / 1000. - unmodelled
                    - float(transfer["seasonal_sublimation_m3"].sum())
                    - float(exported.sum()) - entries.get("pumping_m3", 0.) + entries.get("ocean_water_input_m3", 0.))
    compare(checks, key + "whole_water", inv1["total_m3"] - inv0["total_m3"], external_net)
    compare(checks, key + "declared_unmodelled_precip", entries["precipitation_unmodelled_export_m3"], unmodelled)
    condition(checks, key + "fixed_receiver", np.array_equal(before["context"]["receiver"], after["context"]["receiver"]))
    condition(checks, key + "fixed_height", np.array_equal(before["context"]["height_m"], after["context"]["height_m"]))
    compare(checks, key + "absolute_clock", [after["time_s"], s1["climate_state"]["metadata"]["time_s"]],
            [before["time_s"] + dt_s] * 2)
    condition(checks, key + "g7_owns_only_snow", not np.any(after["states"]["frozen_ground"]["snow_swe_m"]))
    mass_result = after["results"]["mass"]
    condition(checks, key + "G9_weathering_nonzero", float(np.asarray(mass_result["fluxes"]["weathered_solid_m3"]).sum()) > 0.)
    mass_state = after["states"]["mass"]
    physical_solid = sum(float(mass_state[name].sum()) for name in (
        "bedrock_solid_m3", "regolith_solid_m3", "soil_solid_m3", "hillslope_deposit_solid_m3",
        "river_sediment_solid_m3", "dissolved_solid_m3", "ocean_export_solid_m3", "downstream_delivered_solid_m3"))
    compare(checks, key + "G9_solid_inventory", physical_solid,
            float(mass_state["initial_bedrock_solid_m3"].sum()), atol=1.e-8, rtol=2.e-13)
    compare(checks, key + "G9_bedrock_debited", before["states"]["mass"]["bedrock_solid_m3"] - mass_state["bedrock_solid_m3"],
            mass_result["fluxes"]["weathered_solid_m3"], atol=2.e-13, rtol=2.e-11)
    condition(checks, key + "G9_parent_subpool_not_duplicated", np.all(mass_state["parent_solid_m3"] <= mass_state["regolith_solid_m3"] + 1.e-12))
    condition(checks, key + "G9_dissolved_inventory_finite",
              np.isfinite(after["states"]["mass"]["dissolved_solid_m3"]).all())
    return {"index": index, "time_s": after["time_s"], "inventory_before": inv0, "inventory_after": inv1,
            "external_net_m3": external_net, "climate_ledger": ledger, "entries": entries,
            "melt_m3": float(transfer["seasonal_melt_m3"].sum()), "et_m3": float(transfer["g5_et_m3"].sum()),
            "release_m3": float(transfer["g5_release_m3"].sum()), "internal_river_packets": crossings}


def cold_checks(api, output, final, checkpoint_sha, final_sha, forcing, checks):
    force_path = output / "forcing.json"
    write_json(force_path, forcing)
    query_command = [sys.executable, "-B", str(ROOT / "tools/query_environment_processes.py"),
                     "--product", str(output / "final.npz"), "--expected-sha256", final_sha, "--row", "32", "--col", "32"]
    query = subprocess.run(query_command, cwd=ROOT, check=True, capture_output=True, text=True)
    result = json.loads(query.stdout)
    write_json(output / "cold-query.json", result)
    compare(checks, "cold_query_soil", result["states"]["soil_chemistry"]["water_m3"], final["states"]["soil_chemistry"]["water_m3"][32, 32])
    condition(checks, "cold_query_read_only", result["read_only"] and result["time_s"] == final["time_s"])
    cold_material_checks(checks, result, final)
    resume_command = [sys.executable, "-B", str(ROOT / "tools/prepare_environment_processes.py"),
                      "--resume", str(output / "checkpoint.npz"), "--expected-sha256", checkpoint_sha,
                      "--forcing", str(force_path), "--steps", str(STEPS - 1), "--dt-s", str(DT_S), "--output", str(output / "cold-resumed.npz")]
    resume = subprocess.run(resume_command, cwd=ROOT, check=True, capture_output=True, text=True)
    resumed_info = json.loads(resume.stdout)
    resumed = api.load_product(output / "cold-resumed.npz", expected_sha256=resumed_info["sha256"])
    condition(checks, "cold_resume_exact_identity", api.product_identity(resumed) == api.product_identity(final))
    condition(checks, "queries_did_not_write_final", sha256(output / "final.npz") == final_sha)
    return {"query_command": query_command, "resume_command": resume_command, "resume_result": resumed_info}


def cold_material_checks(checks, result, final):
    seasonal = result["seasonal"]
    condition(checks, "cold_query_driver_provenance", seasonal["driver_identity_sha256"] == final["seasonal"]["climate_driver"]["identity_sha256"])
    condition(checks, "cold_query_world_provenance", seasonal["source_world_identity"] == final["sources"]["source_world_identity"])
    condition(checks, "cold_query_initial_snow_provenance", seasonal["initial_swe_source"] == final["seasonal"]["initial_swe_source"])
    material = seasonal["material"]
    compare(checks, "cold_query_material_solubility", material["solubility"], final["states"]["mass"]["solubility"][32, 32], atol=0., rtol=0.)
    condition(checks, "cold_query_material_identity", material["source"]["identity_sha256"] == final["seasonal"]["material_source"]["identity_sha256"])
    condition(checks, "cold_query_unknown_material_status", material["status"]["intrinsic_permeability_m2"] == "pending"
              and material["status"]["bedrock_thickness_m"] == "unknown_no_source")


def run(output, store, baseline=None):
    from terrain_pipeline import environment_regional_hydraulics as climate
    from terrain_pipeline import environment_product as api
    from terrain_pipeline.climate_forcing import _interval_mean_monthly

    start = time.perf_counter()
    paths, registry, manifest, directory = source_files(store)
    before_hashes = snapshot(paths)
    checks = {}
    condition(checks, "world_seed_fixed", registry["world"]["layout"]["world_seed"] == 20261020)
    condition(checks, "source_td_pages_valid", all(before_hashes[str(Path(page["path"]).resolve())] == page["sha256"] for page in registry["pages"]))
    driver = climate.build_climate_driver(store, origin_native_xz=ORIGIN, shape_zx=SHAPE)
    context, sources = api.context_from_store(store, 600, 300, size=64)
    condition(checks, "bounded4096", context["height_m"].size == 4096)
    condition(checks, "same_world_identity", driver["metadata"]["source"]["world_identity"] == sources["source_world_identity"])
    compare(checks, "same_original_bed", driver["arrays"]["elevation_m"], context["height_m"], atol=0., rtol=0.)
    direct_masks = source_masks(manifest, directory)
    expected_valid = direct_masks["valid_mask"] & direct_masks["complete_mask"]
    for name, actual, expected in (
            ("valid", context["valid_mask"], expected_valid),
            ("complete", context["source_complete_mask"], direct_masks["complete_mask"]),
            ("protected", context["protected_mask"], direct_masks["protected_shore_mask"]),
            ("upstream_unknown", context["source_upstream_unknown_mask"], direct_masks["upstream_unknown_mask"]),
            ("channel", context["river_mask"], direct_masks["channel_mask"])):
        condition(checks, "source_mask_preserved_" + name, np.array_equal(actual, expected))
    active = context["valid_mask"] & ~context["ocean_mask"] & ~context["protected_mask"]
    condition(checks, "source_nonempty_active_land", np.any(active))
    condition(checks, "source_has_river", np.any(context["river_mask"]))
    boundary = choose_internal_boundary(context)
    write_json(output / "preselected-internal-boundary.json", boundary)
    condition(checks, "full15km_support", driver["metadata"]["orographic_scale_m"] == 15000. and driver["metadata"]["ridge_offsets_m"] == [-7500., 0., 7500.])
    with np.load(directory / manifest["network"]["file"], allow_pickle=False) as graph:
        native_shape = tuple(graph["native_shape"])
        region = np.s_[600:664, 300:364]
        compare(checks, "source_graph_bed", context["height_m"], graph["node_raw_bed_m"].reshape(native_shape)[region], atol=0., rtol=0.)
        compare(checks, "source_receiver_identity", context["source_receiver_node"], graph["receiver"].reshape(native_shape)[region], atol=0., rtol=0.)
    climate.save_climate_driver(output / "driver.npz", driver)
    climate_state = climate.initial_climate_state(driver)
    _, forcing = climate.advance_climate_driver(driver, climate_state, DT_S, **BOUNDARY)
    _, no_uplift = climate.advance_climate_driver(driver, climate_state, DT_S, **dict(BOUNDARY, uplift_gain=0.))
    gradient = driver["arrays"]["orographic_gradient"]
    positive, negative = gradient > 0., gradient <= 0.
    rain = forcing["precipitation_mm"]
    windward_mean, leeward_mean = float(rain[positive].mean()), float(rain[negative].mean())
    condition(checks, "observed_windward_leeward", positive.any() and negative.any() and windward_mean > leeward_mean)
    condition(checks, "uplift_ablation_changes_actual_rain", rain.sum() > 0. and not np.any(no_uplift["precipitation_mm"]))
    condition(checks, "vapour_actual_interior_transport", np.count_nonzero(rain[:, :-1]) > 0 and forcing["ledger"]["outflow_kg"] > 0.)
    expected_temp = _interval_mean_monthly(driver["arrays"]["monthly_temperature_c"].reshape(12, -1), 0., DT_S).reshape(SHAPE)
    compare(checks, "unaltered_G3_temperature", forcing["air_temperature_c"], expected_temp, atol=0., rtol=0.)
    pieces = [climate.crop_climate_result(forcing, row=0, col=col, shape_zx=(64, 32)) for col in (0, 32)]
    for field in ("precipitation_mm", "air_temperature_c", "rainfall_m_s"):
        compare(checks, "adjacent_fixed_support_" + field, np.concatenate([piece[field] for piece in pieces], axis=1), forcing[field], atol=0., rtol=0.)
    overlap_a = climate.crop_climate_result(forcing, row=0, col=16, shape_zx=(64, 32))
    overlap_b = climate.crop_climate_result(forcing, row=0, col=32, shape_zx=(64, 32))
    compare(checks, "overlap_query_order", overlap_a["precipitation_mm"][:, 16:], overlap_b["precipitation_mm"][:, :16], atol=0., rtol=0.)
    initial_options = {"soil_chemistry": {"water_depth_m": .01}}
    seasonal_options = {"initial_swe_mm": 20., "initial_swe_source": "declared20mm_initial_SWE_mechanism_event_not_observed_or_climate_generated"}
    product = api.initialize(context, sources=sources, initial=initial_options, mode="seasonal",
                             climate_driver=driver, seasonal_parameters=seasonal_options)
    material = product["seasonal"]["material_source"]["arrays"]
    mass_state = product["states"]["mass"]
    compare(checks, "G2_solubility_bound_to_G9", mass_state["solubility"], material["solubility"], atol=0., rtol=0.)
    compare(checks, "G2_hardness_bound_to_G9", mass_state["bed_hardness"], material["bed_hardness"], atol=0., rtol=0.)
    from terrain_pipeline.geology import ROCK_ORDER, ROCK_BY_ID
    solubility_table = np.array([ROCK_BY_ID[rock]["solubility"] for rock in ROCK_ORDER])
    hardness_table = np.array([ROCK_BY_ID[rock]["bed_hardness"] for rock in ROCK_ORDER])
    compare(checks, "G2_solubility_independent_table", material["solubility"], solubility_table[material["rock_index"]], atol=0., rtol=0.)
    compare(checks, "G2_hardness_independent_table", material["bed_hardness"], hardness_table[material["rock_index"]], atol=0., rtol=0.)
    condition(checks, "G2_solubility_not_old_constant", bool(np.any(material["solubility"] != .2)))
    condition(checks, "G2_material_identity_saved", bool(product["seasonal"]["material_source"]["identity_sha256"]))
    initial_inventory = water_inventory(product)
    initial_sha = api.save_product(product, output / "initial.npz")
    driving = {"climate": BOUNDARY, "radiation": {"latitude_deg": 30., "longitude_deg": 180.},
               "groundwater": {"surface_conductance_m2_s": 0.}}
    steps = []
    for index in range(1, STEPS + 1):
        current = api.advance(product, driving, DT_S)
        steps.append(step_accounts(checks, product, current, index, DT_S, boundary))
        if index == 1:
            checkpoint_sha = api.save_product(current, output / "checkpoint.npz")
        product = current
    condition(checks, "nonzero_real_temperature_melt", sum(item["melt_m3"] for item in steps) > 0.)
    condition(checks, "nonzero_actual_ET_recycled_second_step", steps[0]["et_m3"] > 0. and steps[1]["climate_ledger"]["recycle_kg"] > 0.)
    condition(checks, "nonzero_G5_to_saved_river", sum(item["release_m3"] for item in steps) > 0.)
    condition(checks, "river_crosses_internal_query_boundary", any(item["internal_river_packets"] for item in steps))
    final_sha = api.save_product(product, output / "final.npz")
    cold = cold_checks(api, output, product, checkpoint_sha, final_sha, driving, checks)
    query_points = [(0, 0), (32, 31), (32, 32), (63, 63)]
    direct = [api.query_product(product, row, col) for row, col in query_points]
    reverse = [api.query_product(product, row, col) for row, col in reversed(query_points)]
    condition(checks, "query_order_independent", direct == list(reversed(reverse)))
    condition(checks, "source_files_unchanged", before_hashes == snapshot(paths))
    baseline_summary = None
    if baseline is not None:
        previous = json.loads((baseline / "acceptance.json").read_text(encoding="utf-8"))
        original_start = api.load_product(baseline / "initial.npz", expected_sha256=previous["initial_sha256"])
        original_end = api.load_product(baseline / "final.npz", expected_sha256=previous["final_sha256"])
        condition(checks, "baseline_same_sources", previous["source_file_sha256"] == before_hashes)
        condition(checks, "baseline_same_driver", original_end["seasonal"]["climate_driver"]["identity_sha256"] == driver["identity_sha256"])
        condition(checks, "baseline_same_material", original_end["seasonal"]["material_source"]["identity_sha256"] == product["seasonal"]["material_source"]["identity_sha256"])
        before_water, after_water = water_inventory(original_start), water_inventory(original_end)
        declared = original_end["cumulative_ledger"]
        expected_net = (declared["atmosphere_inflow_m3"] - declared["atmosphere_outflow_m3"]
                        - declared["precipitation_unmodelled_export_m3"] - declared["sublimation_m3"]
                        + declared["ocean_water_input_m3"] - declared["window_water_export_m3"] - declared["pumping_m3"])
        compare(checks, "baseline_whole_water_independent_cold", after_water["total_m3"] - before_water["total_m3"], expected_net)
        prior_water_checks = {name: item for name, item in previous["checks"].items()
                              if name.startswith("step_") and not "G9_" in name}
        condition(checks, "baseline_all_step_water_checks", all(item["pass"] for item in prior_water_checks.values()))
        baseline_summary = {"path": str(baseline), "source_report_sha256": sha256(baseline / "acceptance.json"),
                            "initial_sha256": previous["initial_sha256"], "final_sha256": previous["final_sha256"],
                            "independent_inventory_start": before_water, "independent_inventory_end": after_water,
                            "step_water_checks_reused": len(prior_water_checks),
                            "step_water_checks_pass": all(item["pass"] for item in prior_water_checks.values()),
                            "internal_crossing_observed": False,
                            "interpretation": "default river-bed exchange absorbed small runoff before the selected edge; no crossing packet in3h",
                            "original_failed_checks_preserved": [name for name, item in previous["checks"].items() if not item["pass"]]}
    report = {"schema": "environment-seasonal-independent-acceptance-v1", "checks": checks,
              "passed": sum(item["pass"] for item in checks.values()), "total": len(checks),
              "source_file_sha256": before_hashes, "world_identity": registry["world_identity"],
              "source_product_identity": registry["components"][0]["identity_sha256"],
              "origin_native_xz": ORIGIN, "shape_zx": SHAPE, "dt_s": DT_S, "steps": steps,
              "initial_declarations": initial_options, "seasonal_declarations": seasonal_options,
              "forcing_declaration": driving, "initial_inventory": initial_inventory,
              "final_inventory": water_inventory(product), "initial_sha256": initial_sha,
              "final_sha256": final_sha, "driver_identity_sha256": driver["identity_sha256"],
              "support": driver["metadata"]["source"], "cold": cold,
              "scenario": "declared_zero_river_bed_exchange_handoff_control",
              "default_exchange_baseline": baseline_summary,
              "internal_boundary": boundary,
              "support_counts": {"calculation_cells": int(context["height_m"].size),
                  "valid_complete_cells": int(context["valid_mask"].sum()), "active_unprotected_land_cells": int(active.sum()),
                  "protected_cells": int(context["protected_mask"].sum()), "upstream_unknown_cells": int(context["source_upstream_unknown_mask"].sum()),
                  "pending_basin_cells": int(context["pending_basin_mask"].sum()), "river_mask_cells": int(context["river_mask"].sum())},
              "rain_shadow_observation": {"windward_cells": int(positive.sum()), "leeward_cells": int(negative.sum()),
                  "windward_mean_mm": windward_mean, "leeward_mean_mm": leeward_mean,
                  "gradient_range": [float(gradient.min()), float(gradient.max())]},
              "pending": ["full reverse-wind 15km support exceeds saved42km composition; uplift-off ablation and actual original-wind slopes only",
                          "G2 permeability, strength and strata thickness have no source; regolith porosity0.35 remains a separate engineering declaration",
                          "independent neighbouring climate simulations and persistent cross-domain river ownership are not implemented",
                          "glacier movement/ice erosion and natural river capture are outside this bounded seasonal event"],
              "seconds": time.perf_counter() - start}
    write_json(output / "acceptance.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--store", type=Path, default=ROOT / ".scratch/river-generation-review/real-lakes-42km")
    parser.add_argument("--baseline", type=Path, help="previous default-exchange acceptance directory, reused only after matching source/driver/material identities")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        parser.error("--output must be a new directory")
    if output.is_relative_to(args.store.resolve()):
        parser.error("--output must be outside immutable source store")
    output.mkdir(parents=True)
    try:
        report = run(output, args.store.resolve(), None if args.baseline is None else args.baseline.resolve())
    except Exception as failure:
        write_json(output / "failure.json", {"error": str(failure), "traceback": traceback.format_exc()})
        raise
    print(json.dumps({"passed": report["passed"], "total": report["total"], "seconds": report["seconds"],
                      "failed_checks": [name for name, item in report["checks"].items() if not item["pass"]]}, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
