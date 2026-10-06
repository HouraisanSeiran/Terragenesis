"""Render the standalone geographic conditioning fields for inspection."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image, ImageDraw

from diffusion.geography import make_geographic_map_factory as factory_v1
from diffusion.geography_v2 import make_geographic_map_factory as factory_v2


def render(output=ROOT / "preview/geography/conditioning.png", seed=20260927, profile="geographic_v1"):
    factory = factory_v2 if profile == "geographic_v2" else factory_v1
    field = factory(seed=seed).sample_raw(-128, -128, 128, 128)
    ranges = [(-1100, 4500) if profile == "geographic_v2" else (-1000, 2500),
              (-25, 35), (400, 2500), (100, 3000), (15, 85)]
    labels = ["elevation m", "temperature C", "temperature std C x100",
              "precipitation mm/year", "precipitation CV percent"]
    canvas = Image.new("RGB", (256 * 5, 318), "#172330")
    draw = ImageDraw.Draw(canvas)
    for index, (low, high) in enumerate(ranges):
        values = np.clip((field[index] - low) / (high - low), 0, 1)
        if index == 0:
            rgb = np.stack((80 + 160 * values, 80 + 125 * values, 110 + 95 * values), axis=-1)
            rgb[field[index] < 0] = (38, 91, 150)
        elif index == 1:
            rgb = np.stack((50 + 205 * values, 100 + 95 * (1 - abs(values - .5) * 2), 245 - 210 * values), axis=-1)
        else:
            rgb = np.stack((40 + 180 * values, 70 + 150 * values, 110 + 110 * (1 - values)), axis=-1)
        tile = Image.fromarray(rgb.astype(np.uint8), "RGB")
        canvas.paste(tile, (index * 256, 0))
        draw.text((index * 256 + 8, 265), labels[index], fill="white")
        draw.text((index * 256 + 8, 282), f"{low:g} to {high:g}", fill="#bed4e1")
    draw.text((8, 301), f"{profile} | seed {seed} | conditioning only, not generated terrain | 1 cell = 256 model pixels", fill="#bed4e1")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    statistics={"profile":profile,"seed":seed,"region":"conditioning cells x,z -128..127",
                "units":labels,"channels":[{"minimum":float(values.min()),"maximum":float(values.max()),
                "p50":float(np.percentile(values,50)),"p95":float(np.percentile(values,95))} for values in field]}
    output.with_suffix(".json").write_text(json.dumps(statistics,indent=2),encoding="utf-8")
    print(output)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--profile",choices=("geographic_v1","geographic_v2"),default="geographic_v1")
    parser.add_argument("--seed",type=int,default=20260927)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    render(args.output or ROOT / "preview" / args.profile / "conditioning.png",args.seed,args.profile)
