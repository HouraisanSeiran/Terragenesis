"""合成土壤条件逐点查询模块。

本模块输出为**合成土壤条件**：坡度与降水是工程假设的代理量，不对应任何真实土壤调查、质地分类或土壤分类学。

依据 `.scratch/infinite-world-geography/soil-biome-vegetation-spec.md`（P4.2）§3.1。
契约要求的三层分离（环境条件 / 群系分类 / 植被资源）中，本模块只负责第一层。

依赖注入：`elevation`、`bio12_mm`、`thickness_m` 均为可调用对象，接收
`(x_array, z_array)` 返回同形状 float64 数组（单位分别为 m、mm、m）。
本模块**不 import** 任何地形或气候模块，因此可以在没有生成后端时单独测试。

窗口无关性：坡度需要 ±`slope_spacing_m` 的四点邻域，该半径即
`required_halo_m()`。调用方必须在足够的 halo 内采样；halo 不足时本模块
不会静默缩小邻域——它只会如实使用调用方给出的采样器结果。
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import numpy as np

SOIL_ALGORITHM = "synthetic-surface-soil-condition-v1"

Sampler = Callable[[np.ndarray, np.ndarray], np.ndarray]


@dataclass(frozen=True)
class SoilParameters:
    """合成土壤条件参数，全部为工程假设量。"""

    slope_spacing_m: float = 10000.0
    # §标定：本值必须与**实际地形的坡度量级**同阶，否则坡度项恒接近 1 或恒接近 0，
    # 排水档会塌成单一值。实测（10 km 格距、35x35、合成起伏地形）坡度分布为
    # p50=0.0084、p90=0.0156、max=0.0195 m/m，故取 0.02 使坡度项能覆盖 [0,1]。
    # 早先未经实测地取 0.5（≈26.6°），在真实地形上恒得 flatness≈0.97。
    soil_slope_scale: float = 0.02
    available_water_span_mm: float = 2200.0
    retention_penalty_per_class: float = 0.25
    drainage_threshold_high: float = 0.75
    drainage_threshold_mid: float = 0.50
    drainage_threshold_low: float = 0.25

    def __post_init__(self) -> None:
        for name in (
            "slope_spacing_m",
            "soil_slope_scale",
            "available_water_span_mm",
            "retention_penalty_per_class",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} 必须为有限正数，得到 {value!r}")
        low = self.drainage_threshold_low
        mid = self.drainage_threshold_mid
        high = self.drainage_threshold_high
        if not (0.0 < low < mid < high <= 1.0):
            raise ValueError(
                "排水阈值必须满足 0 < low < mid < high <= 1，"
                f"得到 low={low!r}, mid={mid!r}, high={high!r}"
            )


def _resolve_parameters(parameters: Optional[SoilParameters]) -> SoilParameters:
    if parameters is None:
        return SoilParameters()
    if not isinstance(parameters, SoilParameters):
        raise ValueError("parameters 必须是 SoilParameters 实例或 None")
    return parameters


def _validate_seed(seed: Any) -> int:
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError(f"seed 必须为非布尔整数，得到 {type(seed).__name__}")
    seed_int = int(seed)
    if not (0 <= seed_int < 2**64):
        raise ValueError(f"seed 必须满足 0 <= seed < 2**64，得到 {seed_int}")
    return seed_int


def _as_broadcast_arrays(x_m: Any, z_m: Any) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x_m)
    z = np.asarray(z_m)
    if not np.issubdtype(x.dtype, np.floating):
        x = x.astype(np.float64, copy=False)
    if not np.issubdtype(z.dtype, np.floating):
        z = z.astype(np.float64, copy=False)
    x, z = np.broadcast_arrays(x, z)
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(z)):
        raise ValueError("x_m/z_m 必须为有限值")
    return x, z


def _sample(sampler: Sampler, x: np.ndarray, z: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    values = np.asarray(sampler(x, z), dtype=np.float64)
    if values.shape != shape:
        raise ValueError(f"采样器返回形状 {values.shape} 与期望形状 {shape} 不符")
    if not np.all(np.isfinite(values)):
        raise ValueError("采样器返回值必须为有限值")
    return values


def required_halo_m(parameters: Optional[SoilParameters] = None) -> float:
    """返回逐点查询所需的外部边缘（halo）宽度，单位 m。

    坡度用中心差分，取 `x ± slope_spacing_m` 与 `z ± slope_spacing_m` 四点，
    故半径等于 `slope_spacing_m`。调用方采样范围不足时必须显式拒绝。
    """
    return float(_resolve_parameters(parameters).slope_spacing_m)


def metadata(seed: Any, parameters: Optional[SoilParameters] = None) -> Dict[str, Any]:
    """返回合成土壤条件算法的元数据。"""
    params = _resolve_parameters(parameters)
    seed_int = _validate_seed(seed)
    return {
        "algorithm": SOIL_ALGORITHM,
        "seed": seed_int,
        "parameters": dataclasses.asdict(params),
        "halo_m": required_halo_m(params),
        "synthetic_soil": True,
        "measured_soil": False,
        "provenance": "declared engineering assumption; no soil survey, no USDA texture class, no Soil Taxonomy",
    }


def soil_condition(
    seed: Any,
    x_m: Any,
    z_m: Any,
    *,
    elevation: Sampler,
    bio12_mm: Sampler,
    thickness_m: Sampler,
    parameters: Optional[SoilParameters] = None,
) -> Dict[str, np.ndarray]:
    """逐点计算合成土壤条件：`soil_depth_m`、`drainage`、`available_water`。

    `drainage` 方向为 **0=排水快、3=易滞水**（与"坡度越大越不滞水"一致）。
    """
    _validate_seed(seed)
    params = _resolve_parameters(parameters)
    x, z = _as_broadcast_arrays(x_m, z_m)
    shape = x.shape
    s = params.slope_spacing_m

    # 中心差分坡度：四点采样，单位 m/m。
    h_xp = _sample(elevation, x + s, z, shape)
    h_xm = _sample(elevation, x - s, z, shape)
    h_zp = _sample(elevation, x, z + s, shape)
    h_zm = _sample(elevation, x, z - s, shape)
    dhdx = (h_xp - h_xm) / (2.0 * s)
    dhdz = (h_zp - h_zm) / (2.0 * s)
    slope = np.hypot(dhdx, dhdz)

    thickness = _sample(thickness_m, x, z, shape)
    precipitation = _sample(bio12_mm, x, z, shape)
    if np.any(thickness < 0.0):
        raise ValueError("thickness_m 必须非负")
    if np.any(precipitation < 0.0):
        raise ValueError("bio12_mm 必须非负")

    # 陡处难存土：因子 ∈ (0,1]，故 soil_depth_m 天然不超过母质厚度。
    soil_depth_m = thickness * (1.0 / (1.0 + (slope / params.soil_slope_scale) ** 2))

    wetness = np.clip(precipitation / params.available_water_span_mm, 0.0, 1.0)
    flatness = 1.0 - np.clip(slope / params.soil_slope_scale, 0.0, 1.0)
    waterlog_index = flatness * wetness

    drainage = np.full(shape, 0, dtype=np.int64)
    drainage = np.where(waterlog_index >= params.drainage_threshold_high, 3, drainage)
    drainage = np.where(
        (waterlog_index >= params.drainage_threshold_mid)
        & (waterlog_index < params.drainage_threshold_high),
        2,
        drainage,
    )
    drainage = np.where(
        (waterlog_index >= params.drainage_threshold_low)
        & (waterlog_index < params.drainage_threshold_mid),
        1,
        drainage,
    )

    available_water = np.clip(
        wetness * (1.0 - params.retention_penalty_per_class * drainage.astype(np.float64)),
        0.0,
        1.0,
    )

    if np.any(soil_depth_m > thickness + 1e-12):
        raise ValueError("soil_depth_m 不得超过 thickness_m")

    return {
        "soil_depth_m": soil_depth_m,
        "drainage": drainage,
        "available_water": available_water,
    }
