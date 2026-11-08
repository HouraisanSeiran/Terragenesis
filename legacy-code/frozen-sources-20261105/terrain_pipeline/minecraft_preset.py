"""Pure export mapping; no changes to physical terrain or old binary exporters."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math

import numpy as np


@dataclass(frozen=True)
class MinecraftExportPreset:
    metres_per_block: float
    name: str = "minecraft-y64-ceiling1024-v1"
    sea_level_y: int = 64
    ceiling_exclusive_y: int = 1024
    safe_top_y: int = 1022
    min_y: int = -64

    def __post_init__(self):
        if (type(self.metres_per_block) not in (int, float)
                or not math.isfinite(self.metres_per_block) or self.metres_per_block <= 0):
            raise ValueError("Explicit finite positive metres_per_block required")
        if (self.name, self.sea_level_y, self.ceiling_exclusive_y, self.safe_top_y, self.min_y) != (
                "minecraft-y64-ceiling1024-v1", 64, 1024, 1022, -64):
            raise ValueError("Named Y64/1024 preset geometry is fixed")

    def record(self):
        return asdict(self)

    def identity(self):
        return hashlib.sha256(json.dumps(self.record(), sort_keys=True).encode()).hexdigest()

    def dry_run(self, elevation_m):
        heights = np.asarray(elevation_m, dtype=np.float64)
        if heights.size == 0 or not np.isfinite(heights).all():
            raise ValueError("Nonempty finite metre elevations required")
        with np.errstate(over="ignore", invalid="ignore"):
            mapped = self.sea_level_y + heights / self.metres_per_block
        below = int(np.count_nonzero(mapped < self.min_y))
        above = int(np.count_nonzero(mapped > self.safe_top_y))
        return {"preset": self.record(), "preset_identity": self.identity(),
                "physical_min_m": float(heights.min()), "physical_max_m": float(heights.max()),
                "mapped_min_y": float(mapped.min()), "mapped_max_y": float(mapped.max()),
                "below_min_count": below, "above_safe_top_count": above,
                "would_clip": bool(below or above), "accepted": not bool(below or above)}

    def transform(self, elevation_m):
        report = self.dry_run(elevation_m)
        if not report["accepted"]:
            raise ValueError("Export would clip physical terrain; choose a larger metres_per_block")
        return np.floor(self.sea_level_y + np.asarray(elevation_m, dtype=np.float64)
                        / self.metres_per_block).astype(np.int32)
