"""Independent saved-TD finite-process acceptance; never creates terrain sources."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASES = {"inland": ("real-lakes-small", 88, 32, (43912, 41588)),
         "coastal": ("real-coastal", 0, 168, (45868, 41400))}


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
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def source_snapshot(store):
    registry = json.loads((store / "registry.json").read_text(encoding="utf-8"))
    paths = set(store.rglob("*"))
    paths.update(Path(page["path"]) for page in registry["pages"])
    return {str(path.resolve()): sha256(path) for path in sorted(paths) if path.is_file()}


def independent_window(store, row, col, size):
    registry = json.loads((store / "registry.json").read_text(encoding="utf-8"))
    component = registry["components"][0]
    directory = store / "versions" / component["version"]
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    water = json.loads((directory / "water" / "manifest.json").read_text(encoding="utf-8"))
    window = np.s_[row:row + size, col:col + size]
    fields = {}
    for key in ("bed_before_m", "ocean_mask", "channel_mask", "receiver", "known_q_m3_s", "upstream_unknown_mask",
                "complete_mask", "protected_shore_mask", "pending_basin_mask", "lake_mask"):
        fields[key] = np.load(directory / "water" / water["fields"][key], mmap_mode="r")[window].copy()
    full_shape = tuple(water["metadata"]["shape_zx"])
    with np.load(directory / manifest["network"]["file"], allow_pickle=False) as graph:
        fields["node_terminal_kind"] = graph["node_terminal_kind"].reshape(full_shape)[window].copy()
        fields["receiver"] = graph["receiver"].reshape(full_shape)[window].copy()
    with np.load(directory / manifest["composition_tiles"][0]["file"], allow_pickle=False) as composition:
        fields["valid_mask"] = composition["valid_mask"][window].copy() & fields["complete_mask"]
    original = fields["receiver"]
    target_row = np.where(original >= 0, original // full_shape[1] - row, -1)
    target_col = np.where(original >= 0, original % full_shape[1] - col, -1)
    external = (original >= 0) & ((target_row < 0) | (target_row >= size) | (target_col < 0) | (target_col >= size))
    local = np.where((original >= 0) & ~external, target_row * size + target_col, -1)
    fields.update(local_receiver=local, external_receiver_mask=external)
    fields["source_identity"] = manifest["identity_sha256"]
    fields["td_pages_valid"] = all(sha256(page["path"]) == page["sha256"] for page in registry["pages"])
    return fields


def inventory(product):
    """Count physical stocks explicitly; never use production inventory_totals."""
    states = product["states"]
    area = float(product["context"]["spacing_m"]) ** 2
    total = {key: 0. for key in ("water_m3", "solid_m3", "carbon_kg", "salt_kg", "nutrient_kg")}
    stock_map = {
        "mass": ("solid_m3", ("bedrock_solid_m3", "regolith_solid_m3", "soil_solid_m3",
                               "hillslope_deposit_solid_m3", "river_sediment_solid_m3")),
        "groundwater": ("water_m3", ("groundwater_water_m3", "surface_water_m3")),
        "aeolian": ("solid_m3", ("loose_solid_m3", "airborne_solid_m3")),
        "volcanism": ("solid_m3", ("mobile_lava_m3", "airborne_ash_m3", "deposited_lava_m3", "deposited_ash_m3")),
    }
    for module, (kind, names) in stock_map.items():
        for name in names:
            total[kind] += float(np.asarray(states[module][name]).sum())
    frozen = states["frozen_ground"]
    total["water_m3"] += area * sum(float(frozen[name].sum()) for name in ("liquid_water_m", "ground_ice_m", "snow_swe_m"))
    soil = states["soil_chemistry"]
    total["water_m3"] += float(soil["water_m3"].sum())
    total["salt_kg"] += float((soil["salt_dissolved_kg"] + soil["salt_solid_kg"]).sum())
    total["carbon_kg"] += float(soil["organic_carbon_kg"].sum())
    total["nutrient_kg"] += float((soil["nutrient_kg"] + soil["organic_nutrient_kg"]).sum())
    plant = states["succession"]
    total["carbon_kg"] += sum(float(plant[name].sum()) for name in ("biomass_carbon_kg", "dead_carbon_kg", "char_carbon_kg"))
    total["nutrient_kg"] += float(plant["plant_nutrient_kg"].sum())
    coast = states["coastal_exchange"]
    for name, kind in (("water_m3", "water_m3"), ("salt_kg", "salt_kg"), ("bed_solid_m3", "solid_m3")):
        total[kind] += float(coast[name].sum())
    # Network inventories are native-account views; mass dissolved/export fields
    # are historical delivered counters. Neither is a second spendable stock.
    pending = product["pending_packets"]
    for name, kind in (("litter_carbon_kg", "carbon_kg"), ("plant_nutrient_return_kg", "nutrient_kg"),
                       ("soil_water_m3", "water_m3"), ("soil_salt_kg", "salt_kg"),
                       ("subsurface_salt_kg", "salt_kg"), ("subsurface_nutrient_kg", "nutrient_kg")):
        total[kind] += float(pending[name].sum())
    return total


def budgets(initial, final):
    before, after = inventory(initial), inventory(final)
    account = final["cumulative_ledger"]
    expected = dict(before)
    flows = {
        "water_m3": {"rainfall_m3": 1., "ocean_water_input_m3": 1., "evaporation_m3": -1., "window_water_export_m3": -1., "pumping_m3": -1.},
        "solid_m3": {"eruption_solid_input_m3": 1., "solid_boundary_export_m3": -1., "dissolved_solid_export_m3": -1.},
        "carbon_kg": {"photosynthesis_carbon_kg": 1., "atmosphere_carbon_export_kg": -1.},
        "salt_kg": {"salt_boundary_input_kg": 1., "salt_boundary_export_kg": -1.},
        "nutrient_kg": {"nutrient_boundary_input_kg": 1., "nutrient_boundary_export_kg": -1.},
    }
    result = {}
    for kind, terms in flows.items():
        for name, sign in terms.items():
            expected[kind] += sign * (float(account[name]) - float(initial["cumulative_ledger"].get(name, 0.)))
        residual = after[kind] - expected[kind]
        tolerance = max(1.e-7, abs(expected[kind]) * 2.e-11)
        result[kind] = {"initial": before[kind], "final": after[kind], "expected": expected[kind],
                        "residual": residual, "tolerance": tolerance, "pass": abs(residual) <= tolerance}
    return result


def equal_states(first, second):
    for group in ("states", "pending_packets", "context"):
        left, right = first[group], second[group]
        if set(left) != set(right):
            return False
        for name in left:
            if isinstance(left[name], dict):
                if set(left[name]) != set(right[name]):
                    return False
                if not all(np.array_equal(left[name][key], right[name][key]) for key in left[name]):
                    return False
            elif not np.array_equal(left[name], right[name]):
                return False
    return first["time_s"] == second["time_s"] and first["step_index"] == second["step_index"]


def scenario(context):
    shape = context["height_m"].shape
    land = context["valid_mask"] & ~context["ocean_mask"] & ~context["protected_mask"]
    cells = np.flatnonzero(land)
    if not cells.size:
        raise ValueError("acceptance requires land support")
    event = np.zeros(shape)
    event.flat[cells[len(cells) // 2]] = .2
    rows, _ = np.indices(shape)
    corridor = land & (rows >= shape[0] // 2)
    corridor_cells = np.flatnonzero(corridor)
    population = np.zeros(shape)
    population.flat[corridor_cells[len(corridor_cells) // 2]] = .001
    initial = {"succession": {"biomass_carbon_kg_m2": np.where(corridor, 1., .01), "dead_carbon_kg_m2": .005},
               "habitat": {"population_individuals": population},
               "frozen_ground": {"liquid_water_m": 0., "ground_ice_m": .02, "snow_swe_m": .001},
               "aeolian": {"loose_solid_m3": land * .05}}
    forcing = {"rainfall_m_s": 2.e-7, "air_temperature_c": 12., "wind_x_m_s": 12., "wind_z_m_s": 3.,
               "radiation": {"latitude_deg": 35., "longitude_deg": 180.},
               "mass": {"soil_request_solid_m3": land * .001,
                        "repose_angle_deg": 0., "transport_fraction_per_s": .001},
               "groundwater": {"lateral_conductance_m2_s": .00001, "surface_conductance_m2_s": 1.e-8},
               "volcanism": {"lava_input_m3": event, "ash_input_m3": event * .2, "geothermal_w_m2": land * 2.},
               "succession": {"fire_hazard_s": land * 1.e-6},
               "coastal_exchange": {"tide_amplitude_m": .6, "tide_period_s": 7200.,
                                    "wave_height_m": .8, "wave_direction_xz": (1., 1.),
                                    "soil_exchange_m3_s": land * .0001}}
    return initial, forcing


def draw(initial, final, destination, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    states = final["states"]
    area = float(final["context"]["spacing_m"]) ** 2
    coast_porosity = final["results"].get("coastal_exchange", {}).get("metadata", {}).get("parameters", {}).get("porosity", .35)
    coast_only_change = (states["coastal_exchange"]["bed_solid_m3"]
                         - initial["states"]["coastal_exchange"]["bed_solid_m3"]) / (area * (1. - coast_porosity))
    panels = [(final["context"]["height_m"] - initial["context"]["height_m"], "Derived bed change (m)", "RdBu_r"),
              (states["frozen_ground"]["ground_ice_m"] - initial["states"]["frozen_ground"]["ground_ice_m"], "Ground ice change (m SWE)", "RdBu_r"),
              (states["succession"]["biomass_carbon_kg"] / area, "Living vegetation (kg C/m2)", "YlGn"),
              (states["soil_chemistry"]["salt_dissolved_kg"] / np.maximum(states["soil_chemistry"]["water_m3"], 1.e-12), "Soil dissolved salinity (kg/m3)", "viridis"),
              (coast_only_change, "Coastal sediment-only bed change (m)", "RdBu_r"),
              (states["habitat"]["population_individuals"], "Expected population (individuals)", "magma")]
    figure, axes = plt.subplots(2, 3, figsize=(13, 7), constrained_layout=True)
    for axis, (data, label, palette) in zip(axes.ravel(), panels):
        picture = axis.imshow(data, origin="lower", cmap=palette)
        axis.set_title(label)
        axis.set_xlabel("Native account column")
        axis.set_ylabel("Native account row")
        figure.colorbar(picture, ax=axis, shrink=.75)
    figure.suptitle(title + ": fixed saved TD, declared finite process scenario")
    figure.savefig(destination, dpi=150)
    plt.close(figure)


def flux_total(history, module, field):
    return sum(float(np.abs(np.asarray(item["results"].get(module, {}).get("fluxes", {}).get(field, 0.))).sum()) for item in history)


def external_packets(initial, history, forcing, dt_s):
    """Re-sum actual signed packets, rather than trusting cumulative scalars."""
    def packet(module, name):
        return sum(float(np.asarray(item["results"].get(module, {}).get("fluxes", {}).get(name, 0.)).sum()) for item in history)
    def transfer(name):
        return sum(float(np.asarray(item["last_transfers"][name]).sum()) for item in history)
    final = history[-1]
    expected = {"rainfall_m3": transfer("rainfall_m3"),
        "evaporation_m3": packet("soil_chemistry", "evaporation_m3"),
        "window_water_export_m3": transfer("window_water_export_m3"),
        "pumping_m3": packet("groundwater", "pumping_m3"),
        "ocean_water_input_m3": packet("coastal_exchange", "tide_water_m3"),
        "eruption_solid_input_m3": len(history) * sum(float(np.asarray(forcing["volcanism"].get(name, 0.)).sum())
                                                     for name in ("lava_input_m3", "ash_input_m3")),
        "solid_boundary_export_m3": transfer("window_solid_export_m3")
            + packet("aeolian", "boundary_export_solid_m3") + packet("volcanism", "ash_boundary_export_solid_m3"),
        "dissolved_solid_export_m3": float((final["states"]["mass"]["dissolved_solid_m3"]
                                           - initial["states"]["mass"]["dissolved_solid_m3"]).sum()),
        "photosynthesis_carbon_kg": packet("succession", "photosynthesis_carbon_kg"),
        "atmosphere_carbon_export_kg": packet("succession", "fire_atmosphere_carbon_kg") + packet("soil_chemistry", "respired_carbon_kg"),
        "salt_boundary_input_kg": packet("coastal_exchange", "tide_salt_kg"),
        "salt_boundary_export_kg": 0., "nutrient_boundary_input_kg": 0., "nutrient_boundary_export_kg": 0.}
    records = {}
    for name, amount in expected.items():
        actual = float(final["cumulative_ledger"][name])
        records[name] = {"module_packet_sum": amount, "cumulative_scalar": actual,
                         "pass": bool(np.isclose(amount, actual, rtol=2.e-12, atol=1.e-9))}
    return records


def energy_accounts(initial, history, forcing, dt_s):
    records = []
    previous = initial
    latent = 3.34e8
    for current in history:
        area = float(current["context"]["spacing_m"]) ** 2
        results = current["results"]
        rad = results["radiation"]["fluxes"]
        frozen = results["frozen_ground"]
        vol = results["volcanism"]
        old_ice, new_ice = previous["states"]["frozen_ground"], current["states"]["frozen_ground"]
        p = frozen["metadata"]["parameters"]
        active = current["context"]["valid_mask"] & ~current["context"]["protected_mask"] & ~current["context"]["ocean_mask"]
        incoming_heat = (rad["net_ground_heat_w_m2"] + vol["fluxes"]["geothermal_heat_w_m2"]
            + p["air_exchange_w_m2_k"] * (forcing["air_temperature_c"] - old_ice["soil_temperature_c"])
            / (1. + p["snow_insulation_per_m_swe"] * old_ice["snow_swe_m"])) * active * dt_s * area
        enthalpy_change = ((new_ice["soil_temperature_c"] - old_ice["soil_temperature_c"]) * p["soil_heat_capacity_j_m2_k"]
            + (new_ice["liquid_water_m"] - old_ice["liquid_water_m"]) * latent) * area
        # Rain adds liquid enthalpy before the freeze/thaw step; snow melt leaves
        # its latent energy in the explicit exported meltwater packet.
        rain_enthalpy = current["last_transfers"]["rain_to_frozen_m3"] * latent
        frozen_residual = float((enthalpy_change - rain_enthalpy
            + frozen["fluxes"]["snow_meltwater_m"] * area * latent - incoming_heat).sum())
        radiation_change = (current["states"]["radiation"]["absorbed_energy_j_m2"]
                            - previous["states"]["radiation"]["absorbed_energy_j_m2"]) * area
        radiation_residual = float((radiation_change - rad["absorbed_shortwave_w_m2"] * dt_s * area).sum())
        evaporation = results["soil_chemistry"]["fluxes"]["evaporation_m3"]
        evaporation_within_energy = bool(np.all(evaporation <= rad["potential_evaporation_m"] * area + 1.e-10))
        pvol = vol["metadata"]["parameters"]
        external_geo = np.asarray(forcing["volcanism"].get("geothermal_w_m2", 0.)) * active
        cooling = (vol["fluxes"]["geothermal_heat_w_m2"] - external_geo) * area * dt_s
        heat_change = current["states"]["volcanism"]["lava_heat_j"] - previous["states"]["volcanism"]["lava_heat_j"]
        eruption_heat = np.asarray(forcing["volcanism"].get("lava_input_m3", 0.)) * pvol["lava_heat_j_m3"]
        volcano_residual = float((heat_change + cooling - eruption_heat).sum())
        scale = max(1., float(np.abs(incoming_heat).sum()), float(np.abs(eruption_heat).sum()))
        tolerance = max(1.e-5, scale * 1.e-10)
        records.append({"frozen_enthalpy_residual_j": frozen_residual, "radiation_residual_j": radiation_residual,
                        "lava_heat_residual_j": volcano_residual, "tolerance_j": tolerance,
                        "evaporation_within_radiation_energy": evaporation_within_energy,
                        "pass": max(abs(frozen_residual), abs(radiation_residual), abs(volcano_residual)) <= tolerance
                                and evaporation_within_energy})
        previous = current
    return records


def mechanism_checks(initial, history, coastal):
    final = history[-1]
    results = final["results"]
    transfers = final["last_transfers"]
    plant = results["succession"]["fluxes"]
    checks = {
        "G9_weathering_material_response": flux_total(history, "mass", "weathered_solid_m3") > 0.,
        "G10_actual_slope_mobilization": flux_total(history, "mass", "mobilized_solid_m3") > 0.,
        "G11_actual_surface_aquifer_exchange_consumer": flux_total(history, "groundwater", "groundwater_to_surface_m3") > 0.,
        "G12_phase_change_and_infiltration_consumer": flux_total(history, "frozen_ground", "thawed_water_m") > 0.
            and any(np.asarray(item["last_transfers"]["rain_to_aquifer_m3"]).sum() > 0. for item in history),
        "G13_wind_entrainment_and_derived_bed": flux_total(history, "aeolian", "entrained_solid_m3") > 0.
            and flux_total(history, "aeolian", "height_change_m") > 0.,
        "G14_radiation_and_actual_evaporation": flux_total(history, "radiation", "absorbed_shortwave_w_m2") > 0.
            and float(final["cumulative_ledger"]["evaporation_m3"]) > 0.,
        "G15_fire_and_root_roughness_consumers": flux_total(history, "succession", "fire_atmosphere_carbon_kg") > 0.
            and np.array_equal(transfers["soil_root_cohesion_pa"], plant["root_cohesion_pa"])
            and np.array_equal(transfers["hydraulic_manning_n"], plant["manning_n"]),
        "G16_actual_nutrient_transfer_and_stress": flux_total(history, "soil_chemistry", "plant_uptake_kg") > 0.
            and all(np.isclose(item["results"]["succession"]["ledger"]["nutrient_input_kg"],
                               item["results"]["soil_chemistry"]["ledger"]["plant_uptake_kg"], rtol=1.e-12) for item in history),
        "G17_committed_graph_and_next_consumer": np.array_equal(final["context"]["receiver"], final["states"]["network_transition"]["receiver"])
            and np.array_equal(final["context"]["height_m"], final["states"]["network_transition"]["height_m"])
            and np.any(final["context"]["height_m"] != initial["context"]["height_m"]),
        "G18_event_solid_and_geothermal_consumer": flux_total(history, "volcanism", "solidified_lava_m3") > 0.
            and flux_total(history, "volcanism", "geothermal_heat_w_m2") > 0.,
        "G20_actual_population_migration_and_occupancy": flux_total(history, "habitat", "migration_net_individuals") > 0.
            and final["states"]["habitat"]["occupancy_s"].sum() > 0.,
    }
    if coastal:
        checks["G19_tide_water_salt_wave_and_soil_consumer"] = (
            flux_total(history, "coastal_exchange", "flood_water_m3") > 0.
            and flux_total(history, "coastal_exchange", "ebb_water_m3") > 0.
            and flux_total(history, "coastal_exchange", "tide_salt_kg") > 0.
            and flux_total(history, "coastal_exchange", "wave_bed_transfer_m3") > 0.
            and flux_total(history, "coastal_exchange", "soil_water_m3") > 0.)
    else:
        checks["G19_inland_not_mislabeled_as_marine"] = "coastal_exchange" not in results
    return checks


def cold_cli(product_module, prefix, final_sha, checkpoint_sha, forcing_path, steps, dt_s, expected):
    query_cmd = [sys.executable, "-B", str(ROOT / "tools/query_environment_processes.py"),
                 "--product", str(prefix / "product.npz"), "--expected-sha256", final_sha,
                 "--row", "16", "--col", "16"]
    before = {str(path): (path.stat().st_size, path.stat().st_mtime_ns) for path in prefix.rglob("*") if path.is_file()}
    query = subprocess.run(query_cmd, capture_output=True, text=True, cwd=ROOT, timeout=60)
    after = {str(path): (path.stat().st_size, path.stat().st_mtime_ns) for path in prefix.rglob("*") if path.is_file()}
    query_pass = query.returncode == 0 and before == after
    if query_pass:
        payload = json.loads(query.stdout)
        query_pass = payload.get("time_s") == expected["time_s"]
    resume_path = prefix / "cold-resumed.npz"
    counter = 0
    while resume_path.exists():
        counter += 1
        resume_path = prefix / ("cold-resumed-%d.npz" % counter)
    resume_cmd = [sys.executable, "-B", str(ROOT / "tools/prepare_environment_processes.py"),
                  "--resume", str(prefix / "checkpoint.npz"), "--expected-sha256", checkpoint_sha,
                  "--forcing", str(forcing_path), "--steps", str(steps), "--dt-s", str(dt_s), "--output", str(resume_path)]
    resume = subprocess.run(resume_cmd, capture_output=True, text=True, cwd=ROOT, timeout=120)
    resumed_pass = False
    if resume.returncode == 0 and resume_path.exists():
        restored = product_module.load_product(resume_path, expected_sha256=sha256(resume_path))
        resumed_pass = equal_states(expected, restored)
    return {"cold_query_reads_without_generating": query_pass, "cold_cli_resume_exact": resumed_pass}, {
        "query_command": query_cmd, "query_exit": query.returncode, "query_stdout": query.stdout, "query_stderr": query.stderr,
        "resume_command": resume_cmd, "resume_exit": resume.returncode, "resume_stdout": resume.stdout, "resume_stderr": resume.stderr}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".scratch/stage2-g9-g20/verification")
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--dt-s", type=float, default=1800.)
    args = parser.parse_args(argv)
    if not 2 <= args.steps <= 12 or not 0. < args.dt_s <= 3600.:
        parser.error("acceptance budget requires 2..12 steps and 0<dt_s<=3600")
    from terrain_pipeline import environment_product as product
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    report = {"schema": "saved-td-environment-process-acceptance-v1", "world_seed": 20261020,
              "scenario": "declared finite physical drivers, immutable saved TD; not observations or whole-world certification",
              "steps": args.steps, "dt_s": args.dt_s, "cases": {}}
    for name, (store_name, row, col, origin) in CASES.items():
        store = ROOT / ".scratch/river-generation-review" / store_name
        snapshots = source_snapshot(store)
        direct = independent_window(store, row, col, 33)
        context, sources = product.context_from_store(store, row, col, size=33)
        checks = {"source_td_hashes": direct["td_pages_valid"],
                  "fixed_seed": context["world_seed"] == 20261020,
                  "absolute_origin": tuple(context["origin_native_xz"]) == origin,
                  "height_from_immutable_source": np.array_equal(context["height_m"], direct["bed_before_m"]),
                  "ocean_from_saved_macro_identity": np.array_equal(context["ocean_mask"], direct["ocean_mask"]),
                  "source_unknown_support_kept": np.array_equal(context["valid_mask"], direct["valid_mask"])
                    and np.array_equal(context["source_upstream_unknown_mask"], direct["upstream_unknown_mask"]),
                  "source_protected_shore_kept": np.array_equal(context["protected_mask"], direct["protected_shore_mask"]),
                  "external_receivers_not_natural_outlets": np.array_equal(context["external_receiver_mask"], direct["external_receiver_mask"]),
                  "original_terminal_unknown_kept": np.array_equal(context["source_terminal_kind"], direct["node_terminal_kind"])}
        initial_options, forcing = scenario(context)
        initial = product.initialize(context, sources=sources, initial=initial_options)
        current = initial
        history = []
        halfway = args.steps // 2
        prefix = args.output / name
        prefix.mkdir(exist_ok=True)
        for index in range(args.steps):
            current = product.advance(current, forcing, args.dt_s)
            history.append(current)
            if index + 1 == halfway:
                checkpoint_sha = product.save_product(current, prefix / "checkpoint.npz")
        final_sha = product.save_product(current, prefix / "product.npz")
        restored = product.load_product(prefix / "checkpoint.npz", expected_sha256=checkpoint_sha)
        for _ in range(halfway, args.steps):
            restored = product.advance(restored, forcing, args.dt_s)
        checks["split_checkpoint_restore_exact"] = equal_states(current, restored)
        checks.update(mechanism_checks(initial, history, name == "coastal"))
        independent_budgets = budgets(initial, current)
        packet_evidence = external_packets(initial, history, forcing, args.dt_s)
        checks["boundary_ledger_matches_actual_flux_packets"] = all(entry["pass"] for entry in packet_evidence.values())
        independent_energy = energy_accounts(initial, history, forcing, args.dt_s)
        checks["independent_enthalpy_solar_lava_energy"] = all(entry["pass"] for entry in independent_energy)
        checks.update({"physical_budget_" + key: entry["pass"] for key, entry in independent_budgets.items()})
        declared_rain = forcing["rainfall_m_s"] * args.steps * args.dt_s * context["spacing_m"] ** 2 * np.count_nonzero(
            context["valid_mask"] & ~context["ocean_mask"] & ~context["protected_mask"])
        checks["source_cumulative_Q_not_injected"] = bool(np.isclose(current["cumulative_ledger"]["rainfall_m3"], declared_rain, rtol=1.e-12))
        fixed = ~context["valid_mask"] | context["protected_mask"]
        checks["unknown_protected_height_untouched"] = np.array_equal(current["context"]["height_m"][fixed], context["height_m"][fixed])
        checks["external_receiver_stays_explicit"] = bool(np.all(current["context"]["receiver"][context["external_receiver_mask"]] == -1))
        forcing_path = prefix / "forcing.json"
        forcing_path.write_text(json.dumps(plain(forcing), indent=2, allow_nan=False), encoding="utf-8")
        (prefix / "initial-declarations.json").write_text(json.dumps(plain(initial_options), indent=2, allow_nan=False), encoding="utf-8")
        cli_checks, cli_evidence = cold_cli(product, prefix, final_sha, checkpoint_sha, forcing_path,
                                            args.steps - halfway, args.dt_s, current)
        checks.update(cli_checks)
        quiet = product.advance(initial, {"rainfall_m_s": 0., "air_temperature_c": 0.,
            "wind_x_m_s": 0., "wind_z_m_s": 0., "radiation": {"longitude_deg": 0.}}, args.dt_s)
        checks["zero_external_drivers_control"] = all((
            float(quiet["cumulative_ledger"]["rainfall_m3"]) == 0.,
            flux_total([quiet], "volcanism", "solidified_lava_m3") == 0.,
            flux_total([quiet], "aeolian", "entrained_solid_m3") == 0.,
            flux_total([quiet], "succession", "fire_atmosphere_carbon_kg") == 0.,
            flux_total([quiet], "coastal_exchange", "tide_water_m3") == 0.))
        checks["source_files_unchanged"] = snapshots == source_snapshot(store)
        draw(initial, current, prefix / "derived-changes.png", name.title())
        exchanges = [np.asarray(item["results"]["groundwater"]["fluxes"]["groundwater_to_surface_m3"]) for item in history]
        graph_changes = [int(np.count_nonzero(item["results"]["network_transition"]["fluxes"]["receiver_changed_mask"])) for item in history]
        baseline_changes = [int(np.count_nonzero(item["results"]["network_transition"]["fluxes"]["baseline_policy_changed_mask"])) for item in history]
        bed_changes = [int(np.count_nonzero(item["results"]["network_transition"]["fluxes"]["bed_induced_receiver_changed_mask"])) for item in history]
        report["cases"][name] = {"checks": checks, "independent_budgets": independent_budgets,
            "independent_energy": independent_energy,
            "external_packet_checks": packet_evidence,
            "actual_scope_evidence": {"G11_groundwater_to_surface_positive_m3": sum(float(np.maximum(v, 0.).sum()) for v in exchanges),
                "G11_surface_to_groundwater_negative_m3": sum(float(np.minimum(v, 0.).sum()) for v in exchanges),
                "G17_changed_receiver_counts_by_step": graph_changes,
                "G17_old_bed_same_policy_changed_edges_by_step": baseline_changes,
                "G17_bed_induced_changed_edges_by_step": bed_changes,
                "G17_natural_capture_certified": False,
                "G20_initial_population": float(initial["states"]["habitat"]["population_individuals"].sum()),
                "source_unknown_cells": int(np.count_nonzero(~context["valid_mask"])),
                "source_upstream_unknown_cells": int(np.count_nonzero(context["source_upstream_unknown_mask"])),
                "external_handoff_cells": int(np.count_nonzero(context["external_receiver_mask"]))},
            "product_sha256": final_sha, "source_file_sha256": snapshots,
            "source_product_identity": direct["source_identity"], "source_window_zx": [row, col, 33, 33],
            "origin_native_xz": origin, "cumulative_ledger": current["cumulative_ledger"],
            "cold_cli": cli_evidence,
            "nonzero_flux_totals": {module: {key: flux_total(history, module, key)
                for key in result["fluxes"] if np.asarray(result["fluxes"][key]).ndim == 2}
                for module, result in current["results"].items()},
            "last_transfers": {key: float(np.asarray(value).sum()) for key, value in current["last_transfers"].items()}}
    report["elapsed_s"] = time.monotonic() - started
    report["pass"] = all(all(case["checks"].values()) for case in report["cases"].values())
    (args.output / "acceptance.json").write_text(json.dumps(plain(report), indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(plain({"pass": report["pass"], "cases": {name: case["checks"] for name, case in report["cases"].items()},
                      "elapsed_s": report["elapsed_s"], "report": str(args.output / "acceptance.json")}), indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
