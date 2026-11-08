"""同坐标 30 m 环境联合产品：装配、保存、只读查询。

职责边界
--------
本模块**不计算任何物理量**。它把已有生产者（G2 岩性/物性、G9 母质库存、G3 月温、
G5 水状态、G6 土层与覆盖）在**同一组 30 m 世界坐标**上的结果装配成一个可保存、
可只读查询的产品，并保证：

* **同坐标**：所有字段共享同一组绝对世界米坐标（``x_m``/``z_m``），单位米，30 m 格；
* **不吸附**：调用方传入的参考点与产品格心之间存在半格（15 m）偏移时，由调用方用
  显式声明的偏移接受，本模块只记录实测偏移，从不移动坐标；
* **不把未知当零**：每个字段带自己的状态（``computed``/``declared``/``pending``/
  ``not_available``），缺来源的字段不得冒充已知；
* **库存守恒可见**：``solid_m3``/``bulk_m3`` 等库存量与水深/mm 量分开命名，不互相派生。

两个入口分离
------------
* :func:`assemble` —— 把各生产者结果组合成产品（会做一致性校验，但**不计算物理量**）；
* :func:`query` —— **只读**：从已保存产品取字段，不生成、不推进、不改写。

身份分层
--------
* ``world_seed`` + ``spacing_m`` + 坐标集 → ``world_identity``
* 每个输入源的 ``source_identities`` → 进 ``source_identity``
* 模型参数（含 G6 参数身份） → ``model_identity``
* 时间（若有时变字段） → ``time_identity``

四者分开存，不做“一个总哈希”。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np


__all__ = [
    "ALGORITHM",
    "FIELD_STATUS",
    "SCHEMA",
    "WorldProduct",
    "assemble",
    "describe",
    "load",
    "query",
    "save",
]


ALGORITHM = "environment-world-product-v1"
SCHEMA = "environment-world-product-v1"

STATUS_COMPUTED = "computed"
STATUS_DECLARED = "declared"
STATUS_PENDING = "pending"
STATUS_NOT_AVAILABLE = "not_available"
FIELD_STATUS = (STATUS_COMPUTED, STATUS_DECLARED, STATUS_PENDING, STATUS_NOT_AVAILABLE)

#: 产品允许的字段。每个字段一组：名、单位、形状语义。
#: ``per_cell`` = [N]，``monthly`` = [12, N]，``state3`` = [3, N]。
FIELD_SPECS = {
    "elevation_m": ("m", "per_cell"),
    "porosity": ("1", "per_cell"),
    "bed_hardness": ("1", "per_cell"),
    "solubility": ("1", "per_cell"),
    "parent_solid_m3": ("m3", "per_cell"),
    "parent_bulk_m3": ("m3", "per_cell"),
    "monthly_temperature_c": ("degC_monthly_mean", "monthly"),
    "annual_temperature_c": ("degC_annual_mean", "per_cell"),
    "water_state_mm": ("mm", "state3"),
    "water_state_total_mm": ("mm", "per_cell"),
    "soil_thickness_bulk_m": ("m_bulk", "per_cell"),
    "soil_water_capacity_mm": ("mm", "per_cell"),
    "suitability": ("1_normalised", "per_cell"),
    "land_cover_index": ("ordinal", "per_cell"),
    "snow_state": ("mm_equivalent_water", "per_cell"),
}

MAX_CELLS = 262144


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #

def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(payload):
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _array_digest(array):
    values = np.ascontiguousarray(np.asarray(array))
    hasher = hashlib.sha256()
    hasher.update(str(values.shape).encode("ascii"))
    hasher.update(values.dtype.str.encode("ascii"))
    hasher.update(values.tobytes(order="C"))
    return hasher.hexdigest()


def _points_digest(x_m, z_m):
    """与点序无关的点集摘要（按 (x, z) 排序后取字节）。"""
    x = np.asarray(x_m, np.float64).reshape(-1)
    z = np.asarray(z_m, np.float64).reshape(-1)
    order = np.lexsort((z, x))
    return _array_digest(np.stack((x[order], z[order])))


def _point_order(x_m, z_m):
    x = np.asarray(x_m, np.float64).reshape(-1)
    z = np.asarray(z_m, np.float64).reshape(-1)
    return np.lexsort((z, x))


# --------------------------------------------------------------------------- #
# 产品容器
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class WorldProduct:
    """一组同坐标字段 + 四层身份 + 逐字段状态。不可变。"""

    arrays: dict
    status: dict
    units: dict
    world_identity: str
    source_identity: str
    model_identity: str
    time_identity: str
    record: dict

    def __post_init__(self):
        if not isinstance(self.arrays, dict) or not self.arrays:
            raise ValueError("arrays 必须是非空字典")
        cells = None
        for name, value in self.arrays.items():
            if name not in FIELD_SPECS:
                raise ValueError("未声明的字段：%r" % (name,))
            unit, kind = FIELD_SPECS[name]
            array = np.asarray(value)
            if kind == "per_cell":
                if array.ndim != 1:
                    raise ValueError("%s 必须是 [N]" % (name,))
            elif kind == "monthly":
                if array.ndim != 2 or array.shape[0] != 12:
                    raise ValueError("%s 必须是 [12, N]" % (name,))
            elif kind == "state3":
                if array.ndim != 2 or array.shape[0] != 3:
                    raise ValueError("%s 必须是 [3, N]" % (name,))
            width = array.shape[-1]
            if cells is None:
                cells = width
            elif width != cells:
                raise ValueError("%s 的列数与其它字段不一致" % (name,))
            if name not in self.status:
                raise ValueError("字段 %r 缺少状态" % (name,))
            if self.status[name] not in FIELD_STATUS:
                raise ValueError("字段 %r 的状态 %r 不在允许集合内"
                                 % (name, self.status[name]))
        if not 1 <= cells <= MAX_CELLS:
            raise ValueError("列数超出 1..%d" % (MAX_CELLS,))
        for label in ("world_identity", "source_identity", "model_identity", "time_identity"):
            value = getattr(self, label)
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError("%s 必须是 64 位十六进制摘要" % (label,))

    @property
    def cells(self):
        return int(np.asarray(self.arrays["elevation_m"]).size)

    def count_status(self, status):
        return sorted(name for name, value in self.status.items() if value == status)


# --------------------------------------------------------------------------- #
# 装配
# --------------------------------------------------------------------------- #

def assemble(*, city_name, world_seed, spacing_m, x_m, z_m, fields, statuses,
             source_identities, model_parameters, time_record=None):
    """把各生产者**在同一组坐标上**的结果装配成产品。

    不计算任何物理量：``fields`` 里的每个数组必须由调用方从已有生产者拿到。

    参数
    ----
    x_m, z_m : [N] 绝对世界米坐标（30 m 格）。**不吸附**：非格心坐标必须由调用方
        事先显式处理并在 ``source_identities`` 里记录接受偏移；本函数只校验有限性。
    fields : {字段名: 数组}，名必须属于 :data:`FIELD_SPECS`。
    statuses : {字段名: 状态}，每个字段必须有状态。
    source_identities : 各输入源的身份字典（distinct 名字 → identity 或记录）。
    model_parameters : 模型参数（含 G6 参数身份）。
    time_record : 可选，时变字段的时间声明。
    """
    if not isinstance(world_seed, int) or isinstance(world_seed, bool) or world_seed < 0:
        raise ValueError("world_seed 必须是非负整数")
    if (isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float))
            or not math.isfinite(spacing_m) or spacing_m <= 0):
        raise ValueError("spacing_m 必须是有限正数")
    x = np.asarray(x_m, np.float64).reshape(-1)
    z = np.asarray(z_m, np.float64).reshape(-1)
    if x.size != z.size or x.size == 0:
        raise ValueError("x_m/z_m 必须等长且非空")
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("坐标必须有限")
    if max(float(np.max(np.abs(x))), float(np.max(np.abs(z)))) > 1e12:
        raise ValueError("坐标超出支持范围")
    cells = int(x.size)
    if cells > MAX_CELLS:
        raise ValueError("列数超出 %d" % (MAX_CELLS,))

    for name in fields:
        if name not in FIELD_SPECS:
            raise ValueError("未声明的字段：%r" % (name,))
    if set(fields) != set(statuses):
        raise ValueError("fields 与 statuses 的字段集必须一致")

    # 缺“同坐标”的基本证据就不能叫联合产品。
    required = ("elevation_m", "annual_temperature_c", "water_state_mm")
    missing = [name for name in required if name not in fields]
    if missing:
        raise ValueError("联合产品缺必要同坐标字段：%r" % (missing,))

    arrays = {}
    units = {}
    for name, value in fields.items():
        unit, _kind = FIELD_SPECS[name]
        arrays[name] = np.asarray(value, np.float64)
        units[name] = unit

    record = {
        "city_name": city_name,
        "world_seed": int(world_seed),
        "spacing_m": float(spacing_m),
        "cells": cells,
        "coordinate_semantics": (
            "绝对世界米；调用方提供的坐标原样进入身份，本模块从不吸附或移动"),
        "fields": sorted(fields),
        "status_counts": {
            status: sorted(n for n, s in statuses.items() if s == status)
            for status in FIELD_STATUS if any(s == status for s in statuses.values())
        },
    }

    world_identity = _digest({
        "schema": SCHEMA, "world_seed": int(world_seed),
        "spacing_m": float(spacing_m), "points_sha256": _points_digest(x, z),
    })
    source_identity = _digest({"schema": SCHEMA, "sources": source_identities})
    model_identity = _digest({"schema": SCHEMA, "parameters": model_parameters,
                              "fields": sorted(fields)})
    time_identity = _digest({"schema": SCHEMA,
                             "time": time_record if time_record is not None else None})

    return WorldProduct(
        arrays=arrays, status=dict(statuses), units=units,
        world_identity=world_identity, source_identity=source_identity,
        model_identity=model_identity, time_identity=time_identity,
        record={**record, "x_m": x, "z_m": z})


# --------------------------------------------------------------------------- #
# 保存 / 读取（紧凑 arrays + JSON，无重复证明链）
# --------------------------------------------------------------------------- #

def save(product, arrays_path, record_path):
    """保存为 ``.npz``（数组）+ ``.json``（元数据）。**不覆盖**已有文件。"""
    if not isinstance(product, WorldProduct):
        raise ValueError("WorldProduct required")
    import os
    for path in (arrays_path, record_path):
        if os.path.exists(path):
            raise FileExistsError(path)
    payload = dict(product.arrays)
    payload["x_m"] = np.asarray(product.record["x_m"], np.float64)
    payload["z_m"] = np.asarray(product.record["z_m"], np.float64)
    meta = {
        "schema": SCHEMA, "algorithm": ALGORITHM,
        "record": {k: v for k, v in product.record.items() if k not in ("x_m", "z_m")},
        "status": product.status, "units": product.units,
        "world_identity": product.world_identity,
        "source_identity": product.source_identity,
        "model_identity": product.model_identity,
        "time_identity": product.time_identity,
    }
    np.savez_compressed(arrays_path, **payload)
    with open(record_path, "w", encoding="utf-8") as stream:
        json.dump(meta, stream, ensure_ascii=False, indent=1, allow_nan=False,
                  sort_keys=True)
    return meta


def load(arrays_path, record_path, *, expected_world_identity=None):
    """读回产品。只做一致性校验，不重算物理量。"""
    with open(record_path, "r", encoding="utf-8") as stream:
        meta = json.load(stream)
    if meta.get("schema") != SCHEMA:
        raise ValueError("未知的 schema：%r" % (meta.get("schema"),))
    if expected_world_identity is not None \
            and meta.get("world_identity") != expected_world_identity:
        raise ValueError("world_identity 与期望不符（产品属于另一套坐标）")
    with np.load(arrays_path, allow_pickle=False) as archive:
        stored = {name: np.asarray(archive[name], np.float64) for name in archive.files}
    for key in ("x_m", "z_m"):
        if key not in stored:
            raise ValueError("产品缺少坐标数组：%r" % (key,))
    arrays = {name: value for name, value in stored.items() if name not in ("x_m", "z_m")}
    record = dict(meta["record"])
    record["x_m"] = stored["x_m"]
    record["z_m"] = stored["z_m"]
    return WorldProduct(
        arrays=arrays, status=dict(meta["status"]), units=dict(meta["units"]),
        world_identity=meta["world_identity"], source_identity=meta["source_identity"],
        model_identity=meta["model_identity"], time_identity=meta["time_identity"],
        record=record)


# --------------------------------------------------------------------------- #
# 只读查询
# --------------------------------------------------------------------------- #

def query(product, x_query_m, z_query_m, *, accept_offset_m=None):
    """在同坐标产品上**只读**取字段。

    不生成、不推进、不改写产品。请求点必须**恰好**落在产品格点上；若不完全重合，
    需要调用方显式传入 ``accept_offset_m`` 接受实测偏移——本函数**从不吸附**。
    """
    if not isinstance(product, WorldProduct):
        raise ValueError("WorldProduct required")
    qx = np.asarray(x_query_m, np.float64).reshape(-1)
    qz = np.asarray(z_query_m, np.float64).reshape(-1)
    if qx.size != qz.size or qx.size == 0:
        raise ValueError("查询坐标必须等长且非空")
    if not np.isfinite(qx).all() or not np.isfinite(qz).all():
        raise ValueError("查询坐标必须有限")

    px = np.asarray(product.record["x_m"], np.float64)
    pz = np.asarray(product.record["z_m"], np.float64)
    # 精确匹配：产品坐标本身就是离散集合，查询点必须与其中一点完全相等。
    index = np.full(qx.size, -1, np.int64)
    offset = np.full(qx.size, np.inf, np.float64)
    for cell in range(px.size):
        distance = np.hypot(qx - px[cell], qz - pz[cell])
        better = distance < offset
        offset = np.where(better, distance, offset)
        index = np.where(better, cell, index)
    if accept_offset_m is None:
        if np.any(offset > 1e-9):
            raise ValueError(
                "查询点不在产品格点上：实测最大偏移 %.6f m。需要时显式传 "
                "accept_offset_m；本接口从不吸附坐标" % (float(np.max(offset)),))
    else:
        limit = float(accept_offset_m)
        if not math.isfinite(limit) or limit < 0:
            raise ValueError("accept_offset_m 必须是非负有限值")
        if float(np.max(offset)) > limit + 1e-9:
            raise ValueError("实测偏移 %.6f m 超过允许的 %.6f m"
                             % (float(np.max(offset)), limit))

    result = {"cell_index": index, "offset_m": offset, "snapped": False,
              "cells": int(qx.size)}
    for name, array in product.arrays.items():
        _kind = FIELD_SPECS[name][1]
        if _kind == "per_cell":
            result[name] = np.asarray(array)[index]
        else:
            result[name] = np.asarray(array)[:, index]
    result["status"] = {name: product.status[name] for name in product.arrays}
    result["world_identity"] = product.world_identity
    return result


def describe():
    """静态声明，供审查与下游引用（无数值影响）。"""
    return {
        "schema": SCHEMA, "algorithm": ALGORITHM,
        "field_specs": {name: {"units": unit, "shape": kind}
                        for name, (unit, kind) in FIELD_SPECS.items()},
        "required_fields": ["elevation_m", "annual_temperature_c", "water_state_mm"],
        "max_cells": MAX_CELLS,
        "statuses": list(FIELD_STATUS),
        "identities": ["world_identity", "source_identity", "model_identity",
                       "time_identity"],
        "separations": {"assemble": "组合，不算物理量",
                        "query": "只读，不生成不推进不改写",
                        "load": "只读回内存，不重算"},
        "never": [
            "把缺来源的字段当零",
            "吸附或移动调用方坐标",
            "把库存量与水深/mm 互相派生",
            "把宏观网格插值成 30 m 原生格",
            "用一个总哈希代替四层身份",
        ],
    }
