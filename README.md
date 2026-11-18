# Terragenesis 核心算法

面向世界地形生成的 Python 算法源码。包含板块构造、山系和岛链、气候与陆面水文、河湖与三角洲、水沙过程，以及局部三维地貌与几何表示。各模块有独立的适用边界；完整无限世界生成尚未通过端到端验收。

需要 Python 3.11。在仓库根目录运行：

```sh
python -m pip install -r requirements.txt
```

最小示例：在 10 km 格距的有限周期平面上演化 12 步，返回米制高程数组。将下段粘贴到从仓库根目录启动的 Python 解释器。

```python
from terrain_pipeline.tectonic import TectonicConfig, evolve

config = TectonicConfig(
    shape=(64, 64), cell_size_m=10_000, plate_count=6,
    world_seed=20260903, steps=12,
)
result = evolve(config)
print(result.elevation_m.shape)
```

`terrain_pipeline/` 是算法主体；`diffusion/` 保留算法依赖的噪声、条件场和可选后端适配。纯 CPU 示例不需要模型。使用 Terrain Diffusion 推理须自行准备匹配的上游实现、PyTorch 和本地模型；使用 pyDeltaRCM 后端须单独安装 `pyDeltaRCM==2.3.0`。完整工程的预览、游戏适配、历史数据和验收入口不在此发行范围。
