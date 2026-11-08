"""同坐标 30 m 环境联合产品的准备工具（真实生产者接线）。

在**同一组真实 TD 30 m 参考节点**上依次调用已有公开生产者，然后把结果装配成产品：

1. **elevation** — 从已登记有限 TD 稳定 domain 的 `elevation_m.npy` 精确取点；
2. **G3 温度** — `environment_seasonal_air.sample_seasonal_air`，传入**实际点高**；
3. **G2 物性** — `geology_properties.properties_at` 在同点求值；
4. **G9 母质** — 在本点集上声明有限母质初态并 `advance`/`allocate`，所得 parent solid 入产品；
5. **G6 土层与覆盖** — 用真实 parent solid +  porosity + G5 水状态 + G3 年均温调用
   `assess_land_cover`，bulk 厚按实际面积与孔隙得。

坐标语义
--------
目标点集就是 **TD 参考节点**（`world = (origin_native + index) * 30`，不插值）。
高程数组本身就是参考点网格，所以直接把数组元素**索引取值**，不做任何 15 m 映射。
只有调用 material/物性相关接口时才用 `reference_points_to_cells` 报告偏移。

缺源处理
--------
S2 新布局 / G8 海岸 / 雪冰不在本步支持范围，标 `pending`/`not_available` 并写明原因。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from terrain_pipeline.soil_water import LandCoverParameters, assess_land_cover
from terrain_pipeline.climate_forcing import sample_seasonal_air  # noqa: E402
from terrain_pipeline.environment_product import FIELD_SPECS, STATUS_COMPUTED, STATUS_DECLARED, STATUS_NOT_AVAILABLE, STATUS_PENDING, world_assemble as assemble, world_save as save
from terrain_pipeline.geology import properties_at  # noqa: E402
from terrain_pipeline.soil_water import advance, allocate, initial_state


ARRAYS = "environment-world-arrays.npz"
RECORD = "environment-world.json"
TD_DOMAIN = os.path.join(ROOT, "artifacts", "finite-river-sample-v1", "domain")
TD_PRODUCT = os.path.join(ROOT, "artifacts", "finite-river-sample-v1", "product.json")
DEFAULT_WORLD_SEED = 20261020

#: 声明的有限母质初态：可风化岩层厚度（m）。工程假设，未标定。
DECLARED_BEDROCK_THICKNESS_M = 2.0
#: 声明的风化时间步（一个季度量级，秒）。
DECLARED_WEATHERING_DT_S = 90.0 * 86400.0


def load_td_domain():
    """读已登记有限 TD domain 的高程与网格几何（只读）。"""
    with open(TD_PRODUCT, "r", encoding="utf-8") as stream:
        product = json.load(stream)
    domain = product["domain"]
    elevation = np.load(os.path.join(TD_DOMAIN, "elevation_m.npy"))
    shape = tuple(int(v) for v in domain["grid_shape_zx"])
    if elevation.shape != shape:
        raise ValueError("TD elevation 与声明的 grid_shape 不符")
    return elevation, domain


def sample_elevation(elevation, domain, origin_x, origin_z, size, spacing):
    """在**TD 参考节点**上精确取高程：world = origin + index*spacing，不插值。"""
    ox, oz = float(domain["origin_m_xz"][0]), float(domain["origin_m_xz"][1])
    rows = np.rint((origin_z - oz) / spacing).astype(np.int64)
    cols = np.rint((origin_x - ox) / spacing).astype(np.int64)
    if (rows < 0 or cols < 0 or rows + size > elevation.shape[0]
            or cols + size > elevation.shape[1]):
        raise ValueError("请求的 %dx%d 窗口超出已登记 TD domain" % (size, size))
    if not np.isclose(origin_z - oz, rows * spacing, atol=1e-9) \
            or not np.isclose(origin_x - ox, cols * spacing, atol=1e-9):
        raise ValueError(
            "请求原点不在 TD 参考节点上：本工具不接受半格请求，也不吸附")
    x_axis = ox + spacing * np.arange(cols, cols + size, dtype=np.float64)
    z_axis = oz + spacing * np.arange(rows, rows + size, dtype=np.float64)
    block = elevation[rows:rows + size, cols:cols + size].astype(np.float64)
    gx, gz = np.meshgrid(x_axis, z_axis)
    return gx.reshape(-1), gz.reshape(-1), block.reshape(-1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--origin", nargs=2, type=float, required=True,
                        metavar=("X", "Z"), help="TD 参考节点原点（世界米）")
    parser.add_argument("--size", type=int, default=8)
    parser.add_argument("--spacing", type=float, default=30.0)
    parser.add_argument("--world-seed", type=int, default=DEFAULT_WORLD_SEED)
    arguments = parser.parse_args(argv)

    if os.path.exists(arguments.output_dir):
        print(json.dumps({"ok": False, "reason": "输出目录已存在"}, ensure_ascii=False))
        return 2
    if arguments.size < 1 or arguments.spacing <= 0:
        parser.error("--size 必须正整数，--spacing 必须正数")

    # --- 1. 真实 TD 高程（参考节点，不插值） -------------------------------------
    elevation_grid, domain = load_td_domain()
    x, z, elevation = sample_elevation(elevation_grid, domain, arguments.origin[0],
                                      arguments.origin[1], arguments.size,
                                      arguments.spacing)
    cells = int(x.size)
    area = float(domain["cell_area_m2"])

    # --- 2. G3：同点月温与年均温，传实际点高 ----------------------------------
    air = sample_seasonal_air(arguments.world_seed, x, z, elevation_m=elevation)
    monthly_temperature = np.asarray(air["monthly_temperature_c"], np.float64)
    annual_temperature = np.asarray(air["annual_mean_temperature_c"], np.float64)
    air_identity = air.get("identity", {})
    if isinstance(air_identity, dict) and "identity_sha256" in air_identity:
        air_identity = air_identity["identity_sha256"]

    # --- 3. G2：同点岩性物性 -------------------------------------------------------
    properties = properties_at(x, z, world_seed=arguments.world_seed)
    arrays = properties["arrays"] if "arrays" in properties else properties
    porosity = np.asarray(arrays["porosity"], np.float64).reshape(-1)
    bed_hardness = np.asarray(arrays["bed_hardness"], np.float64).reshape(-1)
    solubility = np.asarray(arrays["solubility"], np.float64).reshape(-1)

    # --- 4. G9：在本点集上声明有限母质，真跑一次风化与分配 ----------------------
    state = initial_state(
        bedrock_thickness_m=np.full(cells, DECLARED_BEDROCK_THICKNESS_M),
        area_m2=np.full(cells, area), bed_hardness=bed_hardness,
        solubility=solubility)
    # 驱动物理取同点年均温；湿度用声明值（本版无 G4 水汽收支）。
    moisture_declared = 0.35
    state, _flux = advance(state, dt_s=DECLARED_WEATHERING_DT_S,
                           temperature_c=annual_temperature,
                           moisture=np.full(cells, moisture_declared))
    # 把已风化的母质全部分配给土壤（请求 = 当前 parent 库存），不超额。
    request = np.asarray(state["parent_solid_m3"], np.float64)
    state, soil_delivery, _sediment, _remaining, _accounts = allocate(
        state, soil_parent_solid_m3=request, sediment_solid_m3=0.0)
    # G9 的 soil_delivery 键是 ``soil_parent_solid_m3``（不是 solid_m3），且它只给 solid；
    # bulk 由本模块自己的孔隙换算得到（G9 的 regolith_bulk 是风化壳总 bulk，不是土壤）。
    parent_solid = np.asarray(soil_delivery["soil_parent_solid_m3"], np.float64).reshape(-1)
    parent_bulk = parent_solid / (1.0 - porosity)

    # --- 5. G5：声明的有限雨事件，在同点跑桶得到真实水状态 -------------------
    # 土壤容量由 G6 自己的 bulk 厚 * 声明可用水比得出（与 G6 交付一致），
    # 桶的容量是标量，所以按**精确容量值分组**逐组推进，不平均。
    params = LandCoverParameters()
    # 土壤 bulk 厚 = parent solid / ((1-porosity) * area)，与 G6 的换算同一处口径。
    thickness_preview = parent_solid / ((1.0 - porosity) * area)
    model_parameters = {
        "land_cover_parameters_identity_sha256": params.identity_sha256,
        "land_cover_parameters": {name: getattr(params, name)
                                  for name in params.__dataclass_fields__},
        "declared_bedrock_thickness_m": DECLARED_BEDROCK_THICKNESS_M,
        "declared_weathering_dt_s": DECLARED_WEATHERING_DT_S,
        "declared_moisture": moisture_declared,
        "spacing_m": float(arguments.spacing),
    }

    fields = {
        "elevation_m": elevation,
        "porosity": porosity,
        "bed_hardness": bed_hardness,
        "solubility": solubility,
        "parent_solid_m3": parent_solid,
        "parent_bulk_m3": parent_bulk,
        "monthly_temperature_c": monthly_temperature,
        "annual_temperature_c": annual_temperature,
    }
    statuses = {
        "elevation_m": STATUS_COMPUTED,
        "porosity": STATUS_DECLARED,
        "bed_hardness": STATUS_DECLARED,
        "solubility": STATUS_DECLARED,
        "parent_solid_m3": STATUS_COMPUTED,
        "parent_bulk_m3": STATUS_COMPUTED,
        "monthly_temperature_c": STATUS_COMPUTED,
        "annual_temperature_c": STATUS_COMPUTED,
    }

    # --- 6. G5 + G6：同点水状态与覆盖 --------------------------------------------
    from terrain_pipeline.climate_forcing import advance_soil
    from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
    from dataclasses import replace as _replace

    # 异质容量：每个点用自己的 bulk 厚度推出的容量。桶只接受标量容量与标量 PET 速率，
    # 所以按**精确容量值分组**逐组调用，不平均、不分箱。
    capacity_mm = thickness_preview * 1000.0 * params.available_water_fraction

    # --- 初始化声明（不是无条件物理守恒） ----------------------------------------
    # 声明的初始土壤水是 30 mm，但很多点的真实容量比 30 mm 小得多。桶参数会校验
    # ``initial_soil_mm <= soil_capacity_mm``，所以每个**参数组**必须显式声明一个不超
    # 自己容量的土壤初值；真实 state 另行传入。
    #
    # fast/slow 没有容量上限（核只校验 soil 一库，实读 rainfall_runoff:60 与
    # regional_surface_forcing:40 确认），所以不被 soil 容量抢占。
    #
    # 这是一个**初始化的声明选择**，不是从已有库存里丢水：没有先前的实时库存被截掉，
    # 而是「要求的初值」本身就无法放进这么薄的土。差额计入 initial_adjustment。
    requested_initial_soil_mm = 30.0
    requested_initial_fast_mm = 0.0
    requested_initial_slow_mm = 0.0
    soil_layer = np.minimum(np.full(cells, requested_initial_soil_mm, np.float64),
                            capacity_mm)
    fast_layer = np.full(cells, requested_initial_fast_mm, np.float64)
    slow_layer = np.full(cells, requested_initial_slow_mm, np.float64)
    state3 = np.stack([soil_layer, fast_layer, slow_layer])
    # 声明值多于容量的部分，单独记账（未进桶、也未从任何已有库存扣）。
    initial_adjustment_mm = np.stack([
        np.full(cells, requested_initial_soil_mm) - soil_layer,
        np.zeros(cells, np.float64),
        np.zeros(cells, np.float64),
    ])

    dt_s = 3600.0
    intervals = 12
    rain_mm_h = np.zeros((intervals, cells), np.float64)
    rain_mm_h[:6] = 4.0   # 前 6 h 4 mm/h，后 6 h 停雨

    # 每个点的容量不同 -> 土壤容量在 RunoffParameters 里是标量；按精确容量值分组推进。
    # 容量为 0 的点无法承接任何入渗，单独作为一组（桶核要求 positive 容量以外的路径）。
    capacity_positive = capacity_mm > 0.0
    positive_index = np.flatnonzero(capacity_positive)
    grouped_values = np.unique(capacity_mm[capacity_positive])

    # 每组一个 parameters：容量、三库初值都显式声明，并保持 ``initial <= capacity``。
    # 这里一次算好、后面每个 interval 复用，避免重复构造时又踩同一个校验。
    group_parameters = {}
    for value in grouped_values:
        limit = float(value)
        # 只有 soil 有容量上限；fast/slow 原值声明即可（核不校验它们）。
        seed_soil = min(requested_initial_soil_mm, limit)
        group_parameters[float(value)] = _replace(
            RunoffParameters(),
            soil_capacity_mm=limit,
            initial_soil_mm=seed_soil,
            initial_fast_mm=requested_initial_fast_mm,
            initial_slow_mm=requested_initial_slow_mm)

    for interval in range(intervals):
        values, inverse = np.unique(capacity_mm[capacity_positive], return_inverse=True)
        next_state = state3.copy()
        for index, value in enumerate(values):
            mask = inverse == index
            cells_in_group = positive_index[mask]
            updated, _release, _et, _change = advance_soil(
                rain_mm_h[interval][cells_in_group], state3[:, cells_in_group],
                dt_s=dt_s, parameters=group_parameters[float(value)])
            next_state[:, cells_in_group] = updated
        state3 = next_state
    water_total = state3.sum(axis=0)
    cover = assess_land_cover(
        parent_solid_m3=parent_solid, porosity=porosity,
        horizontal_area_m2=area, family_temperature_c=annual_temperature,
        water_state_mm=state3, hard_substrate=None,
        status={"material": STATUS_COMPUTED, "water_state": STATUS_COMPUTED,
                "family_temperature": STATUS_COMPUTED})

    fields["water_state_mm"] = state3
    fields["water_state_total_mm"] = water_total
    fields["soil_thickness_bulk_m"] = cover["soil_thickness_bulk_m"]
    fields["soil_water_capacity_mm"] = cover["soil_water_capacity_mm"]
    fields["suitability"] = cover["suitability"]
    fields["land_cover_index"] = cover["land_cover_index"].astype(np.float64)
    statuses["water_state_mm"] = STATUS_COMPUTED
    statuses["water_state_total_mm"] = STATUS_COMPUTED
    statuses["soil_thickness_bulk_m"] = STATUS_COMPUTED
    statuses["soil_water_capacity_mm"] = STATUS_COMPUTED
    statuses["suitability"] = STATUS_COMPUTED
    statuses["land_cover_index"] = STATUS_COMPUTED

    # --- 7. 不在本步支持范围：S2 布局 / G8 海岸 / 雪冰 ---------------------------
    external = {
        "snow_state": (STATUS_NOT_AVAILABLE, "G7 雪冰本版不建模"),
    }
    for name, (status, _reason) in external.items():
        kind = FIELD_SPECS[name][1]
        if kind == "per_cell":
            fields[name] = np.full(cells, np.nan, np.float64)
        elif kind == "monthly":
            fields[name] = np.full((12, cells), np.nan, np.float64)
        else:
            fields[name] = np.full((3, cells), np.nan, np.float64)
        statuses[name] = status

    source_identities = {
        "td_domain": {
            "product": "artifacts/finite-river-sample-v1/product.json",
            "elevation": "domain/elevation_m.npy",
            "world_convention": domain["world_convention"],
            "support_identity": domain["support_identity"],
        },
        "environment_seasonal_air": air_identity,
        "geology_properties.properties_at": {
            "world_seed": int(arguments.world_seed),
            "read_only_call": True,
        },
        "weathering_soil_inventory": {
            "declared_bedrock_thickness_m": DECLARED_BEDROCK_THICKNESS_M,
            "dt_s": DECLARED_WEATHERING_DT_S,
            "moisture": moisture_declared,
        },
        "regional_surface_forcing.advance_soil": {
            "declared_rain": "6 h at 4 mm/h then 6 h dry, 1 h steps",
            "initial_soil_mm": 30.0,
            "capacity_grouping": "exact np.unique over per-cell capacity",
        },
        "environment_land_cover": {
            "parameters_identity_sha256": params.identity_sha256,
        },
    }

    product = assemble(
        city_name="environment-world-td-%dx%d" % (arguments.size, arguments.size),
        world_seed=arguments.world_seed, spacing_m=float(arguments.spacing),
        x_m=x, z_m=z, fields=fields, statuses=statuses,
        source_identities=source_identities, model_parameters=model_parameters,
        time_record={"epoch_s": 0.0, "weathering_dt_s": DECLARED_WEATHERING_DT_S,
                     "rain_intervals": intervals, "rain_dt_s": dt_s})

    os.makedirs(arguments.output_dir)
    save(product, os.path.join(arguments.output_dir, ARRAYS),
         os.path.join(arguments.output_dir, RECORD))

    with open(os.path.join(arguments.output_dir, "pending-sources.json"),
              "w", encoding="utf-8") as stream:
        json.dump({
            "schema": "environment-world-pending-sources-v1",
            "not_available": {name: reason
                              for name, (status, reason) in external.items()
                              if status == STATUS_NOT_AVAILABLE},
            "note": "雪冰为可选；S2 新布局与 G8 海岸尚未接入本步",
        }, stream, ensure_ascii=False, indent=1, allow_nan=False, sort_keys=True)

    print(json.dumps({
        "ok": True,
        "dir": os.path.relpath(arguments.output_dir, ROOT).replace(os.sep, "/"),
        "cells": cells,
        "world_identity": product.world_identity,
        "computed_fields": product.count_status(STATUS_COMPUTED),
        "declared_fields": product.count_status(STATUS_DECLARED),
        "pending_fields": product.count_status(STATUS_PENDING),
        "not_available_fields": product.count_status(STATUS_NOT_AVAILABLE),
        "cover_counts": {str(k): int(np.sum(cover["land_cover_index"] == k))
                         for k in range(len(cover["cover_classes"]))},
        "max_bulk_thickness_m": float(np.max(cover["soil_thickness_bulk_m"])),
        "max_parent_solid_m3": float(np.max(parent_solid)),
        "initial_state_declaration": {
            "requested_mm": {
                "soil": requested_initial_soil_mm,
                "fast": requested_initial_fast_mm,
                "slow": requested_initial_slow_mm,
            },
            "effective_mm": {
                "soil": [float(v) for v in soil_layer],
                "fast": [float(v) for v in fast_layer],
                "slow": [float(v) for v in slow_layer],
            },
            "adjustment_mm": {
                "soil": [float(v) for v in initial_adjustment_mm[0]],
                "fast": [0.0] * cells,
                "slow": [0.0] * cells,
            },
            "total_adjustment_mm": float(initial_adjustment_mm.sum()),
            "cells_capacity_below_request": int(
                np.count_nonzero(capacity_mm < requested_initial_soil_mm)),
            "semantics": (
                "初始化的声明选择，不是无条件物理守恒：声明的 30 mm 初值放不进薄土时，"
                "差额计入 adjustment，不从任何已有实时库存中扣除"),
            "capacity_mm": [float(v) for v in capacity_mm],
        },
        "snapped": False,
    }, ensure_ascii=False, indent=1, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
