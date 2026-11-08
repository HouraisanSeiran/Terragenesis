"""CPU gates and explicit opt-in bounded TD preparation (never a fallback)."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import tempfile
import shutil
import html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from diffusion.geography_physical import make_physical_map_factory
from diffusion.paths import configure, inside
from diffusion.physical_config import PhysicalGenerationConfig


def verify(config, seed):
    factory = make_physical_map_factory(seed, config)
    full = factory.sample_raw(-128, -128, 129, 129)
    tiled = np.concatenate((factory.sample_raw(-128, -128, 0, 129),
                            factory.sample_raw(0, -128, 129, 129)), axis=2)
    identity, metadata = config.identity()
    gates = {"finite": bool(np.isfinite(full).all()),
             "above_1024_m": bool(full[0].max() > 1024),
             "negative_bathymetry": bool(full[0].min() < 0),
             "sea_datum_zero": config.sea_datum_m == 0,
             "adjacent_windows_exact": bool(np.array_equal(full, tiled)),
             "repeat_exact": bool(np.array_equal(full, factory.sample_raw(-128, -128, 129, 129))),
             "seed_changes_field": not np.array_equal(full,
                 make_physical_map_factory(seed + 1, config).sample_raw(-128, -128, 129, 129)),
             "config_roundtrip_identity": identity == PhysicalGenerationConfig.from_record(
                 json.loads(json.dumps(config.record()))).identity()[0]}
    if not all(gates.values()):
        raise RuntimeError(f"Physical CPU gates failed: {gates}")
    report = {"artifact_kind": "conditioning_only", "td_inference_run": False,
              "seed": str(seed & 0xFFFFFFFFFFFFFFFF), "identity": identity,
              "metadata": metadata, "gates": gates,
              "minimum_condition_elevation_m": float(full[0].min()),
              "maximum_condition_elevation_m": float(full[0].max()),
              "window_coarse_half_open": [-128, -128, 129, 129]}
    return report, full


def publish(destination, payload):
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
        os.link(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def write_review(destination, conditioning, report):
    elevation = conditioning[0, ::2, ::2]
    rows, columns = elevation.shape
    cells = []
    for row in range(rows):
        for column in range(columns):
            height = float(elevation[row, column])
            if height < 0:
                shade = int(80 + 150 * min(1, -height / 2200))
                color = f"rgb(20,80,{shade})"
            else:
                shade = int(60 + 190 * min(1, height / 4500))
                color = f"rgb({shade},{min(230, shade + 25)},60)"
            cells.append(f'<rect x="{column}" y="{row}" width="1" height="1" fill="{color}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {columns} {rows}">'
           + "".join(cells) + '</svg>')
    publish(destination / "conditioning.svg", svg.encode())
    comparison = []
    from terrain_pipeline.minecraft_preset import MinecraftExportPreset

    for scale in (1, 10, 20):
        result = MinecraftExportPreset(scale).dry_run(conditioning[0])
        comparison.append(f'<tr><td>{scale}</td><td>{result["mapped_min_y"]:.2f}</td>'
            f'<td>{result["mapped_max_y"]:.2f}</td><td>{result["below_min_count"]}</td>'
            f'<td>{result["above_safe_top_count"]}</td><td>{result["accepted"]}</td></tr>')
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>物理条件场 CPU 审查</title><style>body{{font:16px sans-serif;max-width:1100px;margin:30px auto;background:#18202b;color:#eee}}
img{{width:650px;max-width:100%;image-rendering:pixelated}}td,th{{padding:8px;border:1px solid #777}}pre{{white-space:pre-wrap;word-break:break-all}}</style>
<h1>物理条件场：conditioning_only</h1><p>这是 CPU 合成条件输入，不是 TD 推理地形。本轮未启动 GPU，也没有导出游戏世界。</p>
<p>蓝色：海底负高程；黄绿色：陆地。固定显示色标 -2200 m 至 4500 m，不截断原始数据。每两个条件格采样一个显示像素。</p>
<p>条件格间距 7680 m = 原生 30 m × latent 8 × coarse 32；x 向东、z 向南。</p>
<img src="conditioning.svg" alt="CPU 条件高程图"><p>高程范围 {report["minimum_condition_elevation_m"]:.2f} 至 {report["maximum_condition_elevation_m"]:.2f} m，海平面 0 m。</p>
<h2>Minecraft 独立映射预检</h2><p>仅比较条件场映射。Y64 / 顶部安全 1022 / 最低 -64；拒绝越界，不静默裁剪。</p>
<table><tr><th>米/方块</th><th>最小连续 Y</th><th>最大连续 Y</th><th>低于下限</th><th>高于安全顶</th><th>接受</th></tr>{"".join(comparison)}</table>
<h2>CPU 门禁和冻结身份</h2><pre>{html.escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre>
<p>实际 TD 自然度、模型条件遵循程度与模型输出接缝仍待 GPU 空闲后的独立推理验收。</p></html>'''
    publish(destination / "review.html", page.encode("utf-8"))


def prepare_cpu_artifacts(destination, config, seed):
    if destination.exists():
        raise FileExistsError("Output already exists; select a new run directory")
    report, conditioning = verify(config, seed)
    report["delivery_source_sha256"] = {
        name: hashlib.sha256(inside(name).read_bytes()).hexdigest()
        for name in ("tools/verify_physical_generation.py", "terrain_pipeline/minecraft_preset.py",
                     "tests/test_physical_generation.py", "tests/test_minecraft_preset.py",
                     "docs/physical-generation-v1.md", "docs/minecraft-preset-v1.md")}
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix=".physical-cpu-"))
    try:
        import io
        from terrain_pipeline.minecraft_preset import MinecraftExportPreset

        artifact = io.BytesIO()
        np.savez_compressed(artifact, conditioning=conditioning,
                            origin_coarse=np.array([-128, -128]),
                            metadata_json=np.array(json.dumps(report)))
        publish(staging / "conditioning.npz", artifact.getvalue())
        publish(staging / "physical-config.json", json.dumps(config.record(), indent=2).encode())
        publish(staging / "cpu-report.json", json.dumps(report, indent=2).encode())
        export_report = MinecraftExportPreset(metres_per_block=20).dry_run(conditioning[0])
        export_report["source_artifact_kind"] = "conditioning_only"
        export_report["source_identity"] = report["identity"]
        publish(staging / "minecraft-dryrun.json", json.dumps(export_report, indent=2).encode())
        write_review(staging, conditioning, report)
        os.rename(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Workspace-relative physical JSON; default is physical-v1")
    parser.add_argument("--output", default="verification/physical-generation-v1")
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--generate", action="store_true", help="Explicit real CUDA TD inference")
    parser.add_argument("--x", type=int, default=0, help="Native 30m pixel east origin")
    parser.add_argument("--z", type=int, default=0, help="Native 30m pixel south origin")
    parser.add_argument("--size", type=int, default=256, help="Native square side, max 513")
    args = parser.parse_args()
    if not 1 <= args.size <= 513:
        parser.error("--size must be 1..513")
    config = PhysicalGenerationConfig.from_record(json.loads(inside(args.config).read_text(
        encoding="utf-8"))) if args.config else PhysicalGenerationConfig()
    destination = inside(args.output)
    report = prepare_cpu_artifacts(destination, config, args.seed)
    import io
    if args.generate:
        configure()
        from diffusion.physical_backend import PhysicalTerrainDiffusionBackend

        backend = PhysicalTerrainDiffusionBackend(config)
        try:
            elevation, climate, metadata = backend.generate(args.seed, args.x, args.z, args.size)
        finally:
            backend.close()
        artifact = io.BytesIO()
        np.savez_compressed(artifact, elevation_m=elevation, climate=climate,
                            metadata_json=np.array(json.dumps(metadata)))
        payload = artifact.getvalue()
        metadata["artifact_sha256"] = hashlib.sha256(payload).hexdigest()
        metadata["minimum_elevation_m"] = float(elevation.min())
        metadata["maximum_elevation_m"] = float(elevation.max())
        staging = Path(tempfile.mkdtemp(dir=destination, prefix=".generation-"))
        try:
            (staging / "td-output.npz").write_bytes(payload)
            (staging / "td-report.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            os.rename(staging, destination / "generation")
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        print(json.dumps({"td_inference_run": True,
                          "report": str(destination / "generation/td-report.json")}))
    else:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
