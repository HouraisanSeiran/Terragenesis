"""Independent metre-space identity; never a Minecraft generation profile."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

from .paths import inside


@dataclass(frozen=True)
class PhysicalGenerationConfig:
    algorithm: str = "geography_physical_v1"
    native_resolution_m: float = 30.0
    conditioning_spacing_m: float = 7680.0
    geographic_scale_m: float = 7680.0
    continental_uplift_m: float = 3600.0
    ocean_depth_m: float = 2200.0
    ridge_relief_m: float = 2400.0
    massif_relief_m: float = 1050.0
    detail_relief_m: float = 90.0
    sea_datum_m: float = 0.0
    model_dir: str = "models/terrain-diffusion-30m"
    dtype: str = "fp32"
    cond_snr: tuple = (0.65, 0.1, 1.0, 0.1, 1.0)

    def __post_init__(self):
        if self.algorithm != "geography_physical_v1":
            raise ValueError("Unsupported physical algorithm")
        for name in ("native_resolution_m", "conditioning_spacing_m", "geographic_scale_m",
                     "continental_uplift_m", "ocean_depth_m", "ridge_relief_m",
                     "massif_relief_m", "detail_relief_m"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if (type(self.sea_datum_m) not in (int, float) or self.sea_datum_m != 0
                or self.dtype not in ("fp16", "fp32")):
            raise ValueError("Physical sea datum is zero; dtype must be fp16 or fp32")
        if type(self.cond_snr) is not tuple or len(self.cond_snr) != 5:
            raise ValueError("Five immutable conditioning strengths required")
        if any(type(value) not in (int, float) or not math.isfinite(value)
               or not 0 <= value <= 100 for value in self.cond_snr):
            raise ValueError("Invalid conditioning strengths")
        inside(self.model_dir)

    def record(self):
        return asdict(self)

    @classmethod
    def from_record(cls, record):
        values = dict(record)
        if "cond_snr" in values:
            values["cond_snr"] = tuple(values["cond_snr"])
        return cls(**values)

    def identity(self):
        sources = ("physical_config.py", "geography_physical.py", "geographic_noise.py",
                   "physical_backend.py")
        source_hashes = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                         for name in sources}
        metadata = {"schema": "physical-generation-v1", "config": self.record(),
                    "source_sha256": source_hashes, "elevation_units": "m",
                    "coordinates": "x east, z south; arrays [channel,z,x]"}
        digest = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
        return digest, metadata

    def generation_identity(self):
        from .paths import ROOT

        identity, metadata = self.identity()
        model = inside(self.model_dir)
        if not (model / "manifest.json").is_file():
            raise RuntimeError("Existing local model manifest required; no downloads performed")
        metadata = dict(metadata, conditioning_identity=identity,
                        model=json.loads((model / "manifest.json").read_text(encoding="utf-8")),
                        model_config_sha256=hashlib.sha256((model / "config.json").read_bytes()).hexdigest(),
                        upstream=json.loads((ROOT / "runtime/upstream.json").read_text(encoding="utf-8")))
        digest = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
        return digest, metadata


def main():
    import argparse
    import os
    import tempfile

    parser = argparse.ArgumentParser(description="Write an explicit physical TD config (no inference)")
    parser.add_argument("output", help="Workspace-relative JSON path")
    args = parser.parse_args()
    destination = inside(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(json.dumps(PhysicalGenerationConfig().record(), indent=2))
        os.link(temporary, destination)
    finally:
        os.remove(temporary)
    print(destination)


if __name__ == "__main__":
    main()
