# 长垣 Remote Mountains

当前路线和待办以 [TODO.md](TODO.md) 为准：先生成基础地形，再转为 VDM 进一步塑形。当前优先使用 Terrain Diffusion；支持其他基础生成算法已列入后续计划。下文直接 VDM 扩散部分为此前实验记录，尚待整理。

Minecraft Java 26.3 / Fabric 实验地形项目。目标：扩散模型**直接生成基础三通道 VDM**，再由区域内的专用算法生成悬崖等特殊地貌，最后体素化成原版方块。

**开发中，尚无真实地形训练后的 VDM 权重，当前模组不是可正常探索的成品。** 详见 `IMPLEMENTATION_STATUS.md`。

## 模块

| 路径 | 职责 |
|---|---|
| `diffusion/` | 已有 Terrain Diffusion 高度/气候推理，提供基础条件 |
| `vdm_diffusion/` | XYZ扩散训练、采样、VDM导出、独立悬崖塑形 |
| Java `vdm/` | VDM读取、折叠网格体素化、有限区域接入 |
| Java `core/` | 区域、密度、历史程序化原型 |
| Java `world/` | Fabric世界生成、群系、方块与存档 |

## 数据定义

VDM 为 `float32[3,H,W]`，依次是 **Δx、Δy、Δz**，单位为Minecraft方块。参考点为 `(origin_x+column*spacing, 72, origin_z+row*spacing)`。实际顶点为参考点加位移。这是世界坐标方向的浮点图，不是切线空间RGB颜色贴图。

训练 `.npz` 包含：

- `vectors`：目标VDM `[3,H,W]`。
- `condition`：`[7,H,W]`，基础高度偏移/128、温度°C/40、年降雨mm/3000、四种地貌权重。权重依次为孤山/裂谷/喀斯特/石柱，总和为1。
- `metadata`：JSON字符串，包括 `reference: "world-x-y-z-plane72"`、`origin: [x,z]`、`spacing`，并建议记录来源和授权。

批次内H/W必须一致。真实数据需要共同的参考曲面参数化；普通DEM没有侧向位移监督。VDM也不能单独表达任意洞穴拓扑，洞穴仍需体积密度/SDF。

## 工作区内运行

隔离Python：`runtime/venv/Scripts/python.exe`。安装脚本为 `tools/setup_diffusion.py`；Terrain Diffusion 权重下载脚本为 `tools/download_model.py`，当前使用 `hf-mirror.com` 固定版本。这些不是自研VDM网络的权重。

```powershell
# 仅验证训练→XYZ采样→悬崖算子→导出，使用合成测试数据
runtime/venv/Scripts/python.exe -B tools/verify_vdm_pipeline.py

# 真实训练，需要先准备成对VDM数据
runtime/venv/Scripts/python.exe -B -m vdm_diffusion train --data datasets/vdm/train --output models/vdm/model.pt --data-kind measured-vdm --steps 10000

# 基础VDM采样
runtime/venv/Scripts/python.exe -B -m vdm_diffusion sample --checkpoint models/vdm/model.pt --condition datasets/vdm/condition.npz --output preview/vdm/base --seed 20260927

# 独立特殊地貌；遮罩为与VDM同尺寸、值在0到1的二维.npy数组
runtime/venv/Scripts/python.exe -B -m vdm_diffusion sculpt-cliff --input preview/vdm/base/displacement.npz --mask datasets/cliff-mask.npy --output preview/vdm/cliff --center 128 128 --normal 1 0 --height 24 --transition 12 --overhang 3
```

训练数据类型是来源声明，不是自然度认证。真实样本还须在metadata声明 `data_kind: "measured-vdm"` 和 `source`。合成权重默认拒绝普通采样，只有显式 `--allow-experimental` 可做实验。

原始VDM和塑形结果保存到不同目录，每份含 `displacement.npz`、`displacement.rmdv`、`surface.obj`、`provenance.json`。

## Minecraft当前限制

0.2.0研究版通过 `-Dremotemountains.vdmFile=<RMDV路径>` 读取有限地图，同时需要本地基础气候服务。支持方形VDM、整数原点、1～16方块采样间隔。地图必须覆盖全部请求区块，缺少覆盖会报错。尚无自交/退化面修复，任意生成网格不保证可靠体素化。

**不要用合成测试图直接创建可玩世界。** 无限分块、接缝、自然度评估及真实服务器复测尚待完成。旧 `preview/landforms.png` 是程序化原型效果，不是VDM扩散效果。

## 验证

```powershell
runtime/venv/Scripts/python.exe -B -m unittest discover -s tests -v
python tools/build_local.py
```

本地构建只读使用已有Java/Minecraft工具链，所有产物留在工作区。可移植构建另见 `build.gradle`。旧服务器脚本已停用，避免把程序化原型存档当作扩散验证。
