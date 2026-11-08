"""G6 adapter over delivered G9 soil, root-zone G5 water and pinned G3 climate."""
from copy import deepcopy

import numpy as np

from terrain_pipeline.environment_land_cover import assess_land_cover, LandCoverParameters

ALGORITHM = "environment-delivered-soil-land-cover-v1"


def assess(product):
    from terrain_pipeline.environment_seasonal_coupling import driver_slices
    ctx, states, seasonal = product["context"], product["states"], product["seasonal"]
    shape = ctx["height_m"].shape
    area = float(ctx["spacing_m"]) ** 2
    window = driver_slices(ctx, seasonal["climate_driver"])
    monthly = seasonal["climate_driver"]["arrays"]["monthly_temperature_c"][:, window[0], window[1]]
    annual = monthly.mean(axis=0)
    active = ctx["valid_mask"] & ~ctx["ocean_mask"] & ~ctx["protected_mask"]
    soil = states["mass"]["soil_solid_m3"]
    result = assess_land_cover(parent_solid_m3=soil.ravel(),
        porosity=states["mass"]["regolith_porosity"].ravel(), horizontal_area_m2=area,
        family_temperature_c=annual.ravel(),
        water_state_mm=(states["soil_chemistry"]["water_m3"] * 1000. / area).ravel(),
        hard_substrate=(soil <= 0.).ravel(), parameters=LandCoverParameters(),
        status={"material": "computed", "family_temperature": "computed", "water_state": "computed"})
    # Product packing is numeric; class names are a table, never string arrays.
    result["land_cover"] = result["land_cover"].tolist()
    for key, value in result.items():
        if isinstance(value, np.ndarray) and value.size == soil.size:
            result[key] = value.reshape(shape)
    result["material_solid_m3"] = soil.copy()
    result["unallocated_parent_potential_solid_m3"] = states["mass"]["parent_solid_m3"].copy()
    result["growth_support_factor"] = result["suitability"] * result["normalised_material"] * active
    result["active_mask"] = active
    result["adapter"] = {
        "algorithm": ALGORITHM,
        "material_source": "G9 allocated soil_solid_m3 only; parent remains unallocated regolith potential",
        "porosity_source": "mass.regolith_porosity, not sampled bedrock porosity",
        "water_source": "G5 sole root-zone soil water; fast/slow excluded from suitability",
        "temperature_source": "arithmetic mean of original G3 twelve monthly means",
        "consumer": "growth_support_factor scales G15 plant stress; resulting roots/roughness feed existing consumers",
    }
    return result


def validate(product):
    record = product["seasonal"]["land_cover"]
    shape = product["context"]["height_m"].shape
    for key in ("soil_thickness_bulk_m", "soil_water_capacity_mm", "suitability", "land_cover_index", "growth_support_factor"):
        values = np.asarray(record[key])
        if values.shape != shape or not np.isfinite(values).all():
            raise ValueError("invalid persistent G6 field: " + key)
    if not np.array_equal(record["material_solid_m3"], product["states"]["mass"]["soil_solid_m3"]):
        raise ValueError("G6 delivered-soil source differs from current G9 inventory")
    if not np.array_equal(record["porosity"], product["states"]["mass"]["regolith_porosity"]):
        raise ValueError("G6 must use the current regolith porosity")


def query(product, row, col):
    record = product["seasonal"]["land_cover"]
    index = int(record["land_cover_index"][row, col])
    result = {key: float(record[key][row, col]) for key in
              ("soil_thickness_bulk_m", "soil_water_capacity_mm", "suitability", "growth_support_factor",
               "material_solid_m3", "unallocated_parent_potential_solid_m3", "porosity")}
    result.update(land_cover_index=index, land_cover=record["cover_classes"][index],
                  active=bool(record["active_mask"][row, col]), adapter=deepcopy(record["adapter"]))
    return result


def snapshot(product, *, city_name="saved seasonal environment"):
    """Assemble the completed same-anchor fields without sampling or advancing."""
    from terrain_pipeline import environment_process_product as api
    from terrain_pipeline import environment_world_product as world
    if "land_cover" not in product.get("seasonal", {}):
        raise ValueError("a completed seasonal-v2 G6 product is required for a snapshot")
    api._validate_product(product)
    record, ctx, states = product["seasonal"]["land_cover"], product["context"], product["states"]
    area = float(ctx["spacing_m"]) ** 2
    rows, cols = np.indices(ctx["height_m"].shape)
    x = (cols + ctx["origin_native_xz"][0]) * ctx["spacing_m"]
    z = (rows + ctx["origin_native_xz"][1]) * ctx["spacing_m"]
    fields = {"elevation_m": ctx["height_m"].ravel(), "annual_temperature_c": record["family_temperature_c"].ravel(),
              "water_state_mm": np.stack((states["soil_chemistry"]["water_m3"] * 1000. / area,
                                           product["seasonal"]["fast_mm"], product["seasonal"]["slow_mm"])).reshape(3, -1),
              "parent_solid_m3": record["material_solid_m3"].ravel(),
              "parent_bulk_m3": (record["soil_thickness_bulk_m"] * area).ravel(),
              "porosity": record["porosity"].ravel(), "bed_hardness": states["mass"]["bed_hardness"].ravel(),
              "solubility": states["mass"]["solubility"].ravel(), "snow_state": product["seasonal"]["snow_swe_mm"].ravel()}
    for key in ("soil_thickness_bulk_m", "soil_water_capacity_mm", "suitability", "land_cover_index"):
        fields[key] = record[key].ravel()
    selected = np.flatnonzero(record["active_mask"].ravel())
    if not selected.size:
        raise ValueError("no active land accounts available for a G6 snapshot")
    fields = {key: (value[:, selected] if value.ndim == 2 else value[selected])
              for key, value in fields.items()}
    return world.assemble(city_name=city_name, world_seed=int(ctx["world_seed"]), spacing_m=float(ctx["spacing_m"]),
        x_m=x.ravel()[selected], z_m=z.ravel()[selected], fields={key: np.array(value, copy=True) for key, value in fields.items()},
        statuses={key: ("declared" if key in ("porosity", "bed_hardness", "solubility", "soil_water_capacity_mm") else "computed")
                  for key in fields},
        source_identities={"process_identity_sha256": api.product_identity(product),
                           "saved_world_identity": product["sources"]["source_world_identity"],
                           "climate_driver_identity": product["seasonal"]["climate_driver"]["identity_sha256"],
                           "material_source_identity": product["seasonal"]["material_source"]["identity_sha256"],
                           "material_semantics": "G2 same-world engineering rock-table lookup; regolith porosity is separately declared",
                           "support_masks": "active land only: valid & ~ocean & ~protected; other accounts excluded",
                           "parent_solid_semantics": "allocated G9 soil only; no unallocated parent potential added"},
        model_parameters={"adapter": record["adapter"], "G6": record["parameters"],
                          "G6_parameters_identity": record["parameters_identity_sha256"]},
        time_record={"physical_time_s": float(product["time_s"]), "step_index": int(product["step_index"]),
                     "temperature_statistic": record["adapter"]["temperature_source"]})


def prepare_snapshot(process_path, *, expected_sha256, arrays_path, record_path):
    from terrain_pipeline import environment_process_product as api
    from terrain_pipeline import environment_world_product as world
    product = api.load_product(process_path, expected_sha256=expected_sha256)
    result = snapshot(product)
    world.save(result, arrays_path, record_path)
    return result
