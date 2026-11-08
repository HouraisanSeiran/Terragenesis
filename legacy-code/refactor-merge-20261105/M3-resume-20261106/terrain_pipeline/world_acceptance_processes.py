"""Same-source 90 m seasonal acceptance adapter, with explicit cropped boundaries."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import time

import numpy as np
from numba import njit
from scipy.ndimage import map_coordinates

from terrain_pipeline.drainage import build_mesh as build_mesh
from terrain_pipeline.drainage import route_graph as route_graph
from terrain_pipeline.drainage import accumulate_graph as accumulate_graph
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.regional_surface_forcing import advance_soil
from terrain_pipeline.seasonal_snow_ice import advance_snow_ice, SnowParameters
from terrain_pipeline.surface_rivers.metric_climate_refinement import sample_climate_v2, RefinedClimateParameters
from terrain_pipeline.surface_rivers.metric_noise_forcing import MONTH_DAYS, YEAR_S
from terrain_pipeline.surface_rivers.metric_pet_et import temperature_index_pet_rate_mm_h
from terrain_pipeline.lake import LakeStorage as LakeStorage
from terrain_pipeline.td_lithology_field import sample_lithology_points, rock_table
from terrain_pipeline import weathering_soil_inventory as weathering
from terrain_pipeline.environment_land_cover import assess_land_cover
from terrain_pipeline.world_irregular_channels import build_irregular_channel_geometry
from terrain_pipeline.surface_rivers.metric_discharge_geometry import DischargeGeometryConfig
from terrain_pipeline.environment_succession import initialize_succession, advance_succession
from terrain_pipeline.common_infra import file_sha256


TD_CLIMATE_CHANNELS = ["temperature_mean_c", "temperature_std_c_times_100",
    "precipitation_mean_mm_year", "precipitation_cv_times_100", "temperature_elevation_beta_c_per_m"]


def atomic_npz(path, **arrays):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        np.savez(stream, **arrays)
    os.replace(temporary, path)


def couple_td_climate(climate_base, raw_td_m, composed_m, refined_climate):
    """Retain actual TD conditioned means/variability and existing seasonal phase.

    TD's first channel is already temperature at raw TD elevation. Only the
    composed-minus-raw positive-elevation difference receives its lapse rate.
    """
    base = np.asarray(climate_base, np.float64)
    raw, composed = np.broadcast_arrays(np.asarray(raw_td_m, np.float64), np.asarray(composed_m, np.float64))
    if (base.shape != (5, *raw.shape) or not np.isfinite(base).all()
            or not np.isfinite(raw).all() or not np.isfinite(composed).all()
            or np.any(base[1:4] < 0.)):
        raise ValueError("Actual five-channel finite TD climate and matching terrain fields required")
    mean_temperature = base[0] + base[4] * (np.maximum(composed, 0.) - np.maximum(raw, 0.))
    reference_temperature = np.asarray(refined_climate["monthly_temperature_c"], np.float64)
    reference_rain = np.asarray(refined_climate["monthly_precipitation_mm"], np.float64)
    if reference_temperature.shape != (12, *raw.shape) or reference_rain.shape != reference_temperature.shape:
        raise ValueError("Existing monthly phase must match TD climate coordinates")
    anomaly = reference_temperature - reference_temperature.mean(axis=0)
    standard_deviation = anomaly.std(axis=0)
    standardized = np.divide(anomaly, standard_deviation, out=np.zeros_like(anomaly),
        where=standard_deviation > 0.)
    temperature = mean_temperature + standardized * (base[1] / 100.)
    # Recenter roundoff so BIO1 remains the conditioned TD mean, unweighted.
    temperature += mean_temperature - temperature.mean(axis=0)
    target_annual = np.clip(base[2] * refined_climate["precipitation_multiplier"], 100., 3200.)
    weights = reference_rain / reference_rain.mean(axis=0)
    rain_anomaly = weights - 1.
    reference_cv = rain_anomaly.std(axis=0)
    requested_cv = base[3] / 100.
    ratio = np.divide(requested_cv, reference_cv, out=np.zeros_like(reference_cv),
        where=reference_cv > 0.)
    rescaled = 1. + rain_anomaly * ratio
    fallback = np.any(rescaled <= 0., axis=0) | ((reference_cv == 0.) & (requested_cv > 0.))
    # A linear anomaly scaling can ask for negative monthly rain. In that case
    # retain the existing positive seasonal phase and explicitly flag its CV.
    weights = np.where(fallback[None], weights, rescaled)
    precipitation = weights / weights.sum(axis=0) * target_annual
    precipitation[-1] += target_annual - precipitation.sum(axis=0)
    return dict(monthly_temperature_c=temperature, monthly_precipitation_mm=precipitation,
        temperature_target_c=mean_temperature, annual_precipitation_target_mm=target_annual,
        precipitation_cv_fallback=fallback,
        realized_precipitation_cv=precipitation.std(axis=0) / precipitation.mean(axis=0))


def native_climate_sampler(metadata):
    """Read the genuine composed 30 m source and reject unsupported queries."""
    source_record = metadata["native_source_paths"]["composed_30m"]
    source_path = Path(source_record["path"])
    native = np.load(source_path, mmap_mode="r", allow_pickle=False)
    origin = np.asarray(metadata["native_source_origin_xz_m"], np.float64)
    if native.ndim != 2 or origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("2D composed native source and centre origin required")
    support = metadata.get("source_support", {})
    # Composition filtering consumes a margin of the outer source. Synthetic
    # test fixtures can explicitly declare a zero filter margin.
    margin = int(metadata.get("composition", {}).get("filter_radius_native_cells", 0))
    minimum = origin + margin * 30.
    maximum = origin + (np.array(native.shape[::-1]) - 1 - margin) * 30.

    def sample(x_m, z_m):
        sx, sz = np.broadcast_arrays(x_m, z_m)
        if (np.any(sx < minimum[0]) or np.any(sx > maximum[0])
                or np.any(sz < minimum[1]) or np.any(sz > maximum[1])):
            raise ValueError("Native terrain lacks unfiltered climate query support")
        values = map_coordinates(native, [(sz - origin[1]) / 30.,
            (sx - origin[0]) / 30.], order=1, mode="constant", cval=np.nan)
        if not np.isfinite(values).all():
            raise ValueError("Native climate sampler encountered nonfinite terrain")
        return values

    return sample, dict(path=str(source_path.resolve()), source=source_record,
        origin_xz_m=origin.tolist(), spacing_m=30., shape=list(native.shape),
        filter_margin_native_cells=margin, valid_minimum_xz_m=minimum.tolist(),
        valid_maximum_xz_m=maximum.tolist(), source_support=support)


def boundary_influence_mask(shape, ocean, width=8):
    rows, cols = np.indices(shape)
    return ((rows < width) | (cols < width) | (rows >= shape[0] - width)
        | (cols >= shape[1] - width)) & ~ocean


def advance_cover_carbon(elevation, ocean, lake, river, receiver, origin_native,
                         monthly_temperature, monthly_water_mm, seed):
    """One final year of existing succession, with finite soil nutrient exchange."""
    shape = elevation.shape
    area = 8100.
    context = dict(height_m=elevation, spacing_m=90., world_seed=seed,
        origin_native_xz=origin_native, receiver=receiver.reshape(shape),
        valid_mask=~ocean & ~lake, protected_mask=lake, ocean_mask=ocean, river_mask=river)
    state = initialize_succession(context, biomass_carbon_kg_m2=2.)
    nutrient = np.full(shape, .05 * area) * (~ocean & ~lake)
    initial_nutrient = float(nutrient.sum() + state["plant_nutrient_kg"].sum())
    records = []
    litter = 0.
    for month, days in enumerate(MONTH_DAYS):
        result = advance_succession(state, dict(temperature_c=monthly_temperature[month].reshape(shape),
            water_available_fraction=np.clip(monthly_water_mm[month].reshape(shape) / 150., 0., 1.),
            plant_nutrient_uptake_kg=nutrient), context, float(days * 86400.))
        # All offered soil nutrient is debited once; unused and released nutrient
        # is returned by the kernel, conserving the finite soil+plant account.
        nutrient = result["fluxes"]["plant_nutrient_return_kg"]
        state = result["state"]
        litter += result["ledger"]["soil_litter_carbon_kg"]
        records.append(result["ledger"])
    final_nutrient = float(nutrient.sum() + state["plant_nutrient_kg"].sum())
    return result["fluxes"]["cover_fraction"], state["biomass_carbon_kg"] / area, dict(
        initial_biomass_carbon_kg_m2=2., initial_soil_nutrient_kg_m2=.05,
        initial_nutrient_kg=initial_nutrient, final_nutrient_kg=final_nutrient,
        nutrient_residual_kg=initial_nutrient - final_nutrient,
        returned_soil_litter_carbon_kg=litter, monthly_ledgers=records,
        forcing="monthly end-of-month total soil+fast+slow water / 150mm; monthly temperature; zero fire/disturbance hazards",
        time="final year monthly transient, declared initial canopy; no equilibrium or species claim")











def constant_month_soil(liquid_mm, states, temperature_c, days, *, failure_path=None,
                        frame_metadata=None):
    """Stream real hourly bucket calls, grouping declared PET into 0.25 C bins.

    Once the entire state changes less than 1e-12 mm/h, the constant-forcing
    fixed point is repeated. The final release is repaired by the water ledger.
    """
    hours = int(days * 24)
    rain = liquid_mm / hours
    runoff = np.zeros(rain.size)
    actual_et = np.zeros(rain.size)
    initial = states.copy()
    # The scalar PET API is grouped by an explicitly recorded temperature bin.
    bands = np.floor(temperature_c * 4.) / 4.
    for band in np.unique(bands):
        ids = np.flatnonzero(bands == band)
        current = states[:, ids].copy()
        group_rain = rain[ids]
        parameters = RunoffParameters(potential_et_mm_h=float(
            temperature_index_pet_rate_mm_h(np.array([band]))[0]))
        for hour in range(hours):
            try:
                updated, release, et, _ = advance_soil(group_rain, current,
                    dt_s=3600., parameters=parameters)
            except ValueError:
                if failure_path is not None:
                    atomic_npz(failure_path, rain_mm_h=group_rain, states=current,
                        global_cell_ids=ids, parameters_json=np.array(json.dumps(asdict(parameters))),
                        metadata_json=np.array(json.dumps(dict(frame_metadata or {},
                            hour=hour, temperature_band_c=float(band),
                            rain_dtype=str(group_rain.dtype), state_dtype=str(current.dtype)))))
                raise
            runoff[ids] += release
            actual_et[ids] += et
            difference = np.max(np.abs(updated - current))
            current = updated
            if difference < 1e-12:
                remaining = hours - hour - 1
                runoff[ids] += release * remaining
                actual_et[ids] += et * remaining
                break
        states[:, ids] = current
    # Roundoff from the fixed-point skip is assigned to release, never lost.
    residual = liquid_mm - actual_et - runoff - (states - initial).sum(axis=0)
    runoff += residual
    if np.min(runoff) < -1e-8:
        raise RuntimeError("negative runoff after soil ledger closure")
    return np.maximum(runoff, 0.), actual_et


def prepare_world_acceptance_processes(terrain_path, output_dir, *, spinup_years=1,
                                       river_display_q_m3_s=2., resume=False):
    """Produce final-year seasonal fields and route that year's runoff from dry lakes."""
    started = time.perf_counter()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    source_sha256 = file_sha256(terrain_path)
    with np.load(terrain_path, allow_pickle=False) as source:
        elevation = np.asarray(source["elevation_m"], np.float64)
        ocean = np.asarray(source["ocean_mask"], bool)
        td_climate = np.asarray(source["climate_base"], np.float64)
        raw_td = np.asarray(source["raw_td_m"], np.float64)
        metadata = json.loads(str(source["metadata_json"].item()))
    spacing = float(metadata["spacing_m"])
    origin = np.asarray(metadata["origin_xz_m"], np.float64)
    seed = int(metadata.get("world_seed", 20261020))
    if (spacing != 90. or elevation.ndim != 2 or ocean.shape != elevation.shape
            or not np.isfinite(elevation).all() or origin.shape != (2,)
            or not np.isfinite(origin).all() or seed != 20261020
            or type(spinup_years) is not int or not 0 <= spinup_years <= 5
            or not np.isfinite(river_display_q_m3_s) or river_display_q_m3_s <= 0):
        raise ValueError("finite same-source 90 m terrain, fixed seed and bounded spinup required")
    shape, count, area = elevation.shape, elevation.size, spacing ** 2
    flat = np.arange(count)
    x = origin[0] + flat % shape[1] * spacing
    z = origin[1] + flat // shape[1] * spacing
    land = ~ocean.ravel()

    sampler, climate_support = native_climate_sampler(metadata)
    climate_parameters = RefinedClimateParameters()
    radius = climate_parameters.orographic_scale_m + max(abs(v) for v in climate_parameters.ridge_offsets_m)
    # Validate the full possible wind/ridge footprint before doing any seasonal work.
    sampler(np.array([x.min() - radius, x.max() + radius]),
        np.array([z.min() - radius, z.max() + radius]))

    monthly_temperature = np.empty((12, count), np.float64)
    monthly_precipitation = np.empty_like(monthly_temperature)
    cv_fallback = np.zeros(count, bool)
    if td_climate.shape != (5, *shape) or raw_td.shape != shape:
        raise ValueError("Same-source terrain must include actual five-channel TD climate_base and raw_td_m")
    td_flat = td_climate.reshape(5, count)
    cache_path = output / "climate-cache.npz"
    checkpoint_path = output / "monthly-checkpoint.npz"
    if resume and cache_path.exists():
        with np.load(cache_path, allow_pickle=False) as cache:
            if str(cache["source_sha256"].item()) != source_sha256:
                raise ValueError("Climate cache terrain SHA does not match")
            monthly_temperature[:] = cache["monthly_temperature"]
            monthly_precipitation[:] = cache["monthly_precipitation"]
            cv_fallback[:] = cache["cv_fallback"]
            climate_identity = str(cache["climate_identity"].item())
    else:
        for start in range(0, count, 16384):
            stop = min(start + 16384, count)
            climate = sample_climate_v2(seed, x[start:stop], z[start:stop],
                elevation.ravel()[start:stop], elevation_sampler=sampler)
            coupled = couple_td_climate(td_flat[:, start:stop], raw_td.ravel()[start:stop],
                elevation.ravel()[start:stop], climate)
            monthly_temperature[:, start:stop] = coupled["monthly_temperature_c"]
            monthly_precipitation[:, start:stop] = coupled["monthly_precipitation_mm"]
            cv_fallback[start:stop] = coupled["precipitation_cv_fallback"]
        climate_identity = climate["parameter_identity_sha256"]
        atomic_npz(cache_path, monthly_temperature=monthly_temperature,
            monthly_precipitation=monthly_precipitation, cv_fallback=cv_fallback,
            source_sha256=np.array(source_sha256), climate_identity=np.array(climate_identity))
    lithology = sample_lithology_points(x, z, world_seed=seed)
    records = rock_table()
    for name in ("porosity", "solubility"):
        lithology[name] = np.array([record[name] for record in records])[lithology["rock_index"]]
    states = np.zeros((3, count), np.float64)
    swe = np.zeros(count)
    monthly_runoff = np.zeros((12, count), np.float64)
    monthly_snow = np.zeros((12, count), np.float32)
    monthly_soil = np.zeros((12, count), np.float32)
    monthly_root_water = np.zeros((12, count), np.float32)
    ledger = []
    final_start_storage = None
    completed_months = 0
    if resume and checkpoint_path.exists():
        with np.load(checkpoint_path, allow_pickle=False) as checkpoint:
            checkpoint_metadata = json.loads(str(checkpoint["metadata_json"].item()))
            if (checkpoint_metadata["source_sha256"] != source_sha256
                    or checkpoint_metadata["spinup_years"] != spinup_years):
                raise ValueError("Monthly checkpoint source or spinup does not match")
            completed_months = checkpoint_metadata["completed_months"]
            ledger = checkpoint_metadata["ledger"]
            final_start_storage = checkpoint_metadata["final_start_storage"]
            states[:] = checkpoint["states"]
            swe[:] = checkpoint["swe"]
            monthly_runoff[:] = checkpoint["monthly_runoff"]
            monthly_snow[:] = checkpoint["monthly_snow"]
            monthly_soil[:] = checkpoint["monthly_soil"]
            monthly_root_water[:] = checkpoint["monthly_root_water"]
        print(f"Resuming after {completed_months} completed months", flush=True)
    for year in range(spinup_years + 1):
        if year == spinup_years and completed_months <= year * 12:
            final_start_storage = float((states[:, land].sum() + swe[land].sum()) * area / 1000.)
        for month, days in enumerate(MONTH_DAYS):
            if year * 12 + month < completed_months:
                continue
            liquid = np.zeros(count)
            sublimation = 0.
            for start in range(0, count, 16384):
                stop = min(start + 16384, count)
                section = slice(start, stop)
                snow = advance_snow_ice(swe_start_mm=swe[section],
                    temperature_c=monthly_temperature[month:month + 1, section],
                    precip_mm=monthly_precipitation[month:month + 1, section] * land[section],
                    time_edges_s=np.array([0., float(days * 86400.)]),
                    x_m=x[section], z_m=z[section], temperature_source="declared_interval",
                    parameters=SnowParameters(max_swe_mm=100000.))
                swe[section] = snow["arrays"]["swe_edge_mm"][-1]
                liquid[section] = snow["arrays"]["liquid_to_land_mm"][0]
                sublimation += float(snow["arrays"]["sublimation_mm"][0][land[section]].sum())
            release, et = constant_month_soil(liquid, states, monthly_temperature[month], days,
                failure_path=output / f"failed-soil-year{year + 1}-month{month + 1}.npz",
                frame_metadata=dict(year=year + 1, month=month + 1, source_sha256=source_sha256))
            if year == spinup_years:
                monthly_runoff[month] = release * land * area / 1000.
                monthly_snow[month] = swe
                monthly_soil[month] = states[0]
                monthly_root_water[month] = states.sum(axis=0)
                ledger.append(dict(month=month + 1, precipitation_m3=float(
                    monthly_precipitation[month, land].sum() * area / 1000.),
                    et_m3=float(et[land].sum() * area / 1000.),
                    sublimation_m3=sublimation * area / 1000.,
                    runoff_m3=float(monthly_runoff[month].sum())))
            atomic_npz(checkpoint_path, states=states, swe=swe, monthly_runoff=monthly_runoff,
                monthly_snow=monthly_snow, monthly_soil=monthly_soil, monthly_root_water=monthly_root_water,
                metadata_json=np.array(json.dumps(dict(source_sha256=source_sha256,
                    spinup_years=spinup_years, completed_months=year * 12 + month + 1,
                    final_start_storage=final_start_storage, ledger=ledger))))
            print(f"seasonal year {year + 1}/{spinup_years + 1} month {month + 1}/12", flush=True)

    # Geometry runs in a local coordinate frame; returned positions are translated
    # back to the input world origin, including non-integral native origins.
    native_origin = tuple(np.floor(origin / spacing).astype(int))
    mesh = build_mesh(shape, native_origin, spacing, seed)
    offset = origin - np.asarray(native_origin) * spacing
    boundary = np.zeros(shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    unknown_boundary = boundary & ~ocean
    routing = route_graph(elevation, ocean | unknown_boundary, mesh)
    labels, pool_count = pool_labels(elevation.ravel(), routing.filled.ravel(), mesh.indptr, mesh.indices)
    anchors = np.full(pool_count, -1, np.int64)
    groups = np.argsort(labels, kind="stable")
    starts = np.searchsorted(labels[groups], np.arange(pool_count))
    stops = np.searchsorted(labels[groups], np.arange(pool_count), side="right")
    stores, capacities = [], np.empty(pool_count)
    for label in range(pool_count):
        ids = groups[starts[label]:stops[label]]
        anchor = ids[np.argmin(routing.rank[ids])]
        anchors[label] = anchor
        store = PoolStorage(ids, elevation.ravel(), routing.filled.ravel()[anchor], area)
        stores.append(store)
        capacities[label] = store.capacity_m3
    storage = np.zeros(pool_count)
    discharge = np.zeros(count)
    routing_ledger = []
    for month, days in enumerate(MONTH_DAYS):
        flow, retained = route_pool_interval(monthly_runoff[month], routing.order,
            routing.receiver, labels, anchors, capacities, storage)
        discharge += flow / YEAR_S
        ocean_out = float(flow[ocean.ravel()].sum())
        boundary_out = float(flow[unknown_boundary.ravel()].sum())
        incoming = float(monthly_runoff[month].sum())
        routing_ledger.append(dict(month=month + 1, input_runoff_m3=incoming,
            ocean_export_m3=ocean_out, cropped_land_export_m3=boundary_out,
            lake_storage_change_m3=float(retained),
            residual_m3=incoming - ocean_out - boundary_out - retained))
    lake_depth = np.zeros(count)
    pool_records = []
    for label, store in enumerate(stores):
        ids = groups[starts[label]:stops[label]]
        stage = store.stage_at_volume(storage[label])
        lake_depth[ids] = np.maximum(stage - elevation.ravel()[ids], 0.)
        target = int(routing.receiver[anchors[label]])
        pool_records.append(dict(pool_id=label, cells=int(ids.size), capacity_m3=float(capacities[label]),
            stored_m3=float(storage[label]), stage_m=float(stage), spill_stage_m=float(store.maximum),
            spill_source_node=int(anchors[label]), spill_receiver_node=target,
            downstream_pool_id=int(labels[target]) if target >= 0 else -1))
    lake = lake_depth.reshape(shape) > 1e-6
    influence = boundary_influence_mask(shape, ocean)
    unknown = accumulate_graph(routing.receiver, routing.order, influence.astype(float)).ravel() > 0
    river = (discharge.reshape(shape) >= river_display_q_m3_s) & ~ocean & ~lake
    geometry = build_irregular_channel_geometry(elevation, discharge.reshape(shape), river, mesh,
        routing.receiver, bed_hardness=lithology["bed_hardness"].reshape(shape),
        bank_hardness=lithology["bank_hardness"].reshape(shape),
        lake_mask=lake, ocean_mask=ocean, config=DischargeGeometryConfig())
    # Soil parent is a declared finite initial mantle, advanced by the actual
    # conservative weathering kernel for the same final year (no fake millennia).
    annual_temperature = monthly_temperature.mean(axis=0)
    soil_depth = np.zeros(count)
    vegetation = np.zeros(count)
    cover_class = np.zeros(count, np.uint8)
    weathered_m3, dissolved_m3 = 0., 0.
    for start in range(0, count, 4096):
        stop = min(start + 4096, count)
        section = slice(start, stop)
        size = stop - start
        section_land = land[section]
        state = weathering.initial_state(bedrock_thickness_m=10. * section_land,
            area_m2=area, bed_hardness=lithology["bed_hardness"][section],
            solubility=lithology["solubility"][section])
        moisture = np.clip(monthly_soil[:, section].mean(axis=0) / 150., 0., 1.)
        state, flux = weathering.advance(state, dt_s=float(YEAR_S),
            temperature_c=annual_temperature[section], moisture=moisture)
        pore = np.minimum(lithology["porosity"][section], .8)
        initial_solid = .45 * (1. - pore) * area * section_land
        cover = assess_land_cover(parent_solid_m3=initial_solid + state["parent_solid_m3"],
            porosity=pore, horizontal_area_m2=area,
            family_temperature_c=annual_temperature[section],
            water_state_mm=monthly_soil[:, section].mean(axis=0),
            water_capacity_reference_mm=np.full(size, 150.))
        soil_depth[section] = cover["soil_thickness_bulk_m"]
        vegetation[section] = cover["suitability"]
        cover_class[section] = cover["land_cover_index"]
        weathered_m3 += float(flux["weathered_solid_m3"].sum())
        dissolved_m3 += float(flux["dissolved_solid_m3"].sum())
    suitability = vegetation.copy()
    suitability[~land | lake.ravel()] = 0.
    cover_class[~land | lake.ravel()] = 0
    vegetation, biomass_carbon, succession = advance_cover_carbon(elevation, ocean, lake, river,
        routing.receiver, native_origin, monthly_temperature, monthly_root_water, seed)
    soil_depth[~land] = 0.
    sources = np.flatnonzero((routing.receiver >= 0) & land)
    mouth_ids = sources[ocean.ravel()[routing.receiver[sources]]]
    mouths = []
    node_x, node_z = mesh.node_x_m + offset[0], mesh.node_z_m + offset[1]
    for cell in sorted(mouth_ids, key=lambda i: -discharge[i])[:20]:
        target = int(routing.receiver[cell])
        direction = np.array([node_x[cell] - node_x[target], node_z[cell] - node_z[target]])
        direction /= np.linalg.norm(direction)
        mouths.append(dict(source_node=int(cell), ocean_receiver_node=target,
            source_xz_m=[float(node_x[cell]), float(node_z[cell])],
            ocean_xz_m=[float(node_x[target]), float(node_z[target])],
            inward_unit_xz=direction.tolist(), q_m3_s=float(discharge[cell]),
            annual_volume_m3=float(discharge[cell] * YEAR_S),
            unknown_external_inflow=bool(unknown[cell])))
    final_storage = float((states[:, land].sum() + swe[land].sum()) * area / 1000.)
    balance = (sum(item["precipitation_m3"] - item["et_m3"] - item["sublimation_m3"]
        - item["runoff_m3"] for item in ledger) - final_storage + final_start_storage)
    seasonal_scale = max(sum(item["precipitation_m3"] for item in ledger), 1.)
    routing_scale = max(float(monthly_runoff.sum()), 1.)
    checks = dict(seasonal_water_closes=abs(balance) <= seasonal_scale * 1e-10,
        routed_water_closes=all(abs(item["residual_m3"]) <= routing_scale * 1e-10
            for item in routing_ledger),
        lake_prisms_match_storage=abs(float(lake_depth.sum() * area) - float(storage.sum()))
            <= max(float(storage.sum()), 1.) * 1e-10,
        no_lakes_in_ocean=not bool(np.any(lake & ocean)),
        incision_bounded=bool(np.max(elevation - geometry["arrays"]["bed_elevation_m"]) <= 4. + 1e-9))
    if not all(checks.values()):
        raise RuntimeError(f"Acceptance aggregate checks failed: {checks}")
    report = dict(schema="world-acceptance-processes-v1", source_terrain=metadata, origin_xz_m=origin.tolist(),
        spacing_m=spacing, cell_area_m2=area, shape=list(shape), world_seed=seed,
        climate_parameter_identity=climate_identity, climate_terrain_support=climate_support,
        td_climate_coupling=dict(algorithm="conditioned-TD-means-existing-phase-orography-v1",
            authoritative_channel_definition=TD_CLIMATE_CHANNELS,
            upstream_source="WorldPipeline._compute_climate actual returned five-channel tensor",
            input_channel_metadata_disagrees=metadata.get("climate_base_channels") != TD_CLIMATE_CHANNELS,
            temperature_mean="TD temp + TD beta * (max(composed,0)-max(rawTD,0)); no independent-noise mean",
            temperature_variability="existing monthly anomalies centered and normalized to TD std/100; BIO mean/std use 12 unweighted months",
            precipitation_mean="clip(TD annualP * existing terrain precipitation_multiplier,100,3200) mm/year",
            precipitation_variability="existing monthly anomaly scaled to TD CV/100 when all months remain nonnegative; otherwise existing positive seasonal shape retained",
            precipitation_cv_fallback_cells=int(cv_fallback.sum()),
            precipitation_cv_fallback_fraction=float(cv_fallback.mean()),
            independent_noise_role="deterministic monthly phase only; annual climate means come from TD conditions"),
        algorithms=["sample_climate_v2", "couple_td_climate", "advance_snow_ice:depth-only adapter",
            "temperature_index_pet_rate_mm_h", "advance_soil", "build_mesh", "route_graph",
            "LakeStorage", "weathering_soil_inventory.advance", "assess_land_cover",
            "build_irregular_channel_geometry", "initialize_succession", "advance_succession"],
        time=dict(calendar="365 day", spinup_years=spinup_years, final_year=spinup_years + 1,
            assimilation_epoch="declared synthetic year 1 start at physical t=0 seconds; not a civil date",
            final_year_start_s=float(spinup_years * YEAR_S),
            final_year_end_s=float((spinup_years + 1) * YEAR_S),
            snow_interval_clock="each call uses relative 0..month-duration seconds under declared_interval temperatures; no calendar lookup; physical month follows chronological loop",
            soil_timestep_s=3600, snow_timestep="monthly distributed mean",
            lake_timestep="final-year monthly runoff volumes", equilibrium_claim=False,
            instantaneous_fields="snow_swe_mm, soil_water_mm, lake_depth_m, vegetation_fraction, biomass_carbon_kg_m2: final year end",
            annual_fields="temperature and cover_suitability: TD-conditioned 12-month unweighted BIO mean; Q: final-year volume / 31536000 seconds",
            monthly_fields="monthly snow/soil are month-end stores; rain/runoff are interval totals"),
        assumptions=dict(initial_soil_fast_slow_snow_mm=0., initial_lake_storage_m3=0.,
            initial_soil_bulk_depth_m=.45, weatherable_bedrock_m=10.,
            pet_temperature_bin_c=.25, climate_halo="genuine composed30m native source; checked filter-valid support; no clamping",
            lake_evaporation="not modelled; lakes receive terrestrial runoff only",
            lake_scope="final-year filling from dry; no external inflow supplied",
            vegetation_fraction="existing succession live carbon / declared carrying carbon; actual final-year-end cover",
            snow_adapter="only returned mm stores used; native30m metadata/volumes not used"),
        boundaries=dict(actual_ocean_cells=int(ocean.sum()), cropped_land_outlet_cells=int(unknown_boundary.sum()),
            unknown_influence_band_cells=int(influence.sum()), unknown_influence_band_width_cells=8,
            affected_downstream_cells=int(unknown.sum()), external_inflow_m3=None,
            external_inflow_status="unknown; eight-cell land-boundary influence propagated on receiver DAG; imposed exports are separate"),
        seasonal_water_ledger=ledger, routing_water_ledger=routing_ledger,
        seasonal_storage_start_m3=final_start_storage, seasonal_storage_end_m3=final_storage,
        seasonal_balance_residual_m3=float(balance), pools=pool_records, major_ocean_mouths=mouths,
        aggregate_checks=checks,
        units=dict(elevation_m="metres above declared datum", bed_m="metres above declared datum",
            node_x_m="world metres", node_z_m="world metres", discharge_m3_s="final-year volume / year seconds",
            soil_depth_m="bulk metres", vegetation_fraction="actual succession cover_fraction [0,1]",
            cover_suitability_fraction="computed environment_land_cover suitability [0,1]",
            biomass_carbon_kg_m2="live plant carbon kg C per m2",
            snow_swe_mm="mm water equivalent", soil_water_mm="mm water depth",
            annual_precipitation_mm="mm per declared 365-day year", annual_temperature_c="degree Celsius",
            monthly_runoff_volume_m3="m3 per cell per calendar month", receiver="row-major cell account ID; -1 explicit outlet"),
        river_display_q_m3_s=float(river_display_q_m3_s),
        geometry=geometry["metadata"],
        weathering=dict(weathered_solid_m3=weathered_m3, dissolved_solid_m3=dissolved_m3,
            domain="terrestrial land only; ocean weatherable bedrock and initial mantle are zero"),
        succession=succession,
        runtime_seconds=float(time.perf_counter() - started),
        limitations=["synthetic climate and declared uncalibrated coefficients",
            "cropped land boundary exports and missing inflow remain explicit",
            "generation incision is bounded geometry; no hydraulic erosion or calibrated ecology"])
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    arrays = dict(elevation_m=elevation, bed_m=geometry["arrays"]["bed_elevation_m"],
        ocean_mask=ocean, lake_mask=lake, lake_depth_m=lake_depth.reshape(shape),
        river_mask=river, receiver=routing.receiver, discharge_m3_s=discharge.reshape(shape),
        node_x_m=node_x, node_z_m=node_z, annual_precipitation_mm=monthly_precipitation.sum(axis=0).reshape(shape),
        annual_temperature_c=annual_temperature.reshape(shape), vegetation_fraction=vegetation.reshape(shape),
        td_climate_precipitation_cv_fallback_mask=cv_fallback.reshape(shape),
        cover_suitability_fraction=suitability.reshape(shape), biomass_carbon_kg_m2=biomass_carbon,
        soil_depth_m=soil_depth.reshape(shape), snow_swe_mm=swe.reshape(shape),
        soil_water_mm=states[0].reshape(shape), land_cover_index=cover_class.reshape(shape),
        unknown_external_inflow_mask=unknown.reshape(shape),
        unknown_external_inflow_source_mask=influence,
        monthly_temperature_c=monthly_temperature.reshape((12, *shape)),
        monthly_precipitation_mm=monthly_precipitation.reshape((12, *shape)),
        monthly_runoff_volume_m3=monthly_runoff.reshape((12, *shape)),
        monthly_snow_swe_mm=monthly_snow.reshape((12, *shape)),
        monthly_soil_water_mm=monthly_soil.reshape((12, *shape)),
        pool_id=labels.reshape(shape), metadata_json=np.array(json.dumps(report, ensure_ascii=True)))
    np.savez_compressed(output / "product.npz", **arrays)
    graph = geometry["graph"]
    graph["node_x_m"] = node_x
    graph["node_z_m"] = node_z
    for name in ("reach_min_x_m", "reach_max_x_m"):
        graph[name] += offset[0]
    for name in ("reach_min_z_m", "reach_max_z_m"):
        graph[name] += offset[1]
    np.savez_compressed(output / "river_graph.npz", **graph)
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report

from terrain_pipeline.drainage import pool_labels, route_pool_interval
from terrain_pipeline.basin_storage import PoolStorage
