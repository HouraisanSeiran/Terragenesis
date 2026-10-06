# 物理地形生成 v1

这是显式选择的物理 TD 生成路径，不改变旧配置、旧后端、默认值、缓存身份、Java 或 TGMCMT01，不自动接入默认世界。

## 坐标、尺度和身份

`PhysicalGenerationConfig` 不可变，支持 JSON 往返。海平面基准为 0 米，海底允许负高程；没有游戏高度上限、压缩因子或软拐点。坐标 x 向东、z 向南，数组为 `[channel,z,x]`，窗口为整数半开区间。

模型原生像素为 30 米。上游 coarse 条件格对应 32 个 latent 像素，每个 latent 像素对应 8 个原生像素，因此条件格间距为 **32 × 8 × 30 = 7680 米**，不是 30 米。后端加载前校验模型原生分辨率及此间距与配置相符。

复用原始 `geographic_noise.field`，默认大陆抬升 3600 米、海底深度系数 2200 米、山脊起伏 2400 米、山体起伏 1050 米、细节起伏 90 米。大陆噪声格尺度为 245.76 / 92.16 / 30.72 千米，山体为 46.08 / 15.36 / 7.68 千米。这是合理尺度的合成目标，不是现实 DEM 标定结果，不保证模型一定遵循输入。

五个条件通道为高程米、温度摄氏度、温度标准差摄氏度乘 100、年降水毫米、降水变异系数乘 100。气温使用 6.5 摄氏度/千米递减率。仅在模型边界对高程作带符号平方根编码，这是可逆编码，不是游戏压缩。

条件身份包含物理参数、配置/条件工厂/后端及复用噪声源码哈希；生成身份另外包含本地模型 manifest、模型配置哈希和固定上游元数据。输出记录正规化无符号 64 位种子、窗口、坐标与单位。CPU 条件采样在网格分配前限制为最多 1048576 格点。

## CPU 门禁与审查页

工程根目录使用已有运行时，不下载依赖或权重。配置导出原子排他发布，目标存在时拒绝；重复运行复用配置，不重复第一条命令。

```powershell
runtime/venv/Scripts/python.exe -m diffusion.physical_config verification/physical-generation-configs/physical-v1.json
runtime/venv/Scripts/python.exe tools/verify_physical_generation.py --config verification/physical-generation-configs/physical-v1.json --output verification/physical-generation-v1
runtime/venv/Scripts/python.exe -m unittest tests.test_physical_generation tests.test_minecraft_preset tests.test_geography_v5
```

输出 `physical-config.json`、`conditioning.npz`、`cpu-report.json`、`minecraft-dryrun.json`、`conditioning.svg` 和独立 `review.html`。审查页展示固定显示色标的条件高程图及 1 / 10 / 20 米每方块映射对照；不修改 Sonnet 页面。显示色标饱和不改变 NPZ 原始数据。

门禁检查高程超过 1024 米、负海底、零海平面、相邻窗口精确拼接、重复采样、种子差异和配置身份往返。**产物为 `conditioning_only`，不是新 TD 地形。** 条件连续不能证明模型输出连续。

整次 CPU 产物先写完整 staging 目录，再原子重命名发布。显式输出目录已存在时立即拒绝，重复运行必须指定新目录；不要预先创建输出目录。独立配置位于另一目录，因此配置导出与运行输出不冲突。报告同时记录验证器、预设、测试和文档的交付源码哈希。早期 `verification/physical-generation-v1` 草稿保留，不再覆盖。

## 真实 TD 推理入口

本轮用户游戏占用 GPU，不启动推理，不结束或配置游戏。协调者确认 GPU 空闲后执行：

```powershell
runtime/venv/Scripts/python.exe tools/verify_physical_generation.py --config verification/physical-generation-configs/physical-v1.json --generate --seed 20261001 --x 0 --z 0 --size 256 --output verification/physical-generation-v1-inference
```

新 `PhysicalTerrainDiffusionBackend` 继承固定上游条件初始化钩子。只用已有本地模型，要求 CUDA，无程序噪声回退。单种子、batch 1、不启用 torch compile、直接 tile 缓存 256 MiB。边长限制 1..513 原生像素，x/z 是原生像素而非条件格。请求和缓存边界不保证显存适配，上游 halo 与 tile 计算可能大于请求。

真实结果 `generation/td-output.npz` 保存 `elevation_m`、五通道 `climate`；`generation/td-report.json` 保存来源、身份、种子、原点、耗时、极值及校验和。验证高程 `(size,size)`、气候 `(5,size,size)` 和有限性后，两个文件在新目录一次原子发布，拒绝覆盖已有生成目录。失败不发布半成品生成，也不以条件数组冒充结果。

自然度、条件遵循、模型输出接缝与实际显存需求仍待真实推理验收。Y64 / 1024 只属于 Minecraft 导出预设。
