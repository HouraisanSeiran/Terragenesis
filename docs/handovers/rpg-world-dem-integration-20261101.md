# 跑团世界 DEM 接入交接（2026-11-01）

目标是在跨度至少 10,000 km 的游戏世界中使用同源粗 DEM，并按需准备局部 90 m / 30 m 地形。另一项目现在即可并行搭建消费侧；万公里世界、统一按需服务和粗细水系衔接均尚未交付或实测。本文路径均相对于 Terragenesis 仓库根目录；本次核验环境的源根目录为 `D:\codexwork\山川形意Terragenesis`，迁移时不要依赖该绝对路径。

## 状态与分工

**已有**：周期平面板块生成及带身份的冻结产品；板块条件 TD 的有限窗口生成和读取；若干固定页、缓存及有限域河湖规划/细化机制。具体入口见下文。它们不是已经接好的全球产品。

**进行中**：Terragenesis 主线负责物理来源与一阶段冻结产品。一阶段尚未完成，不能把当前结果称作最终图。当前 `native-event-v1` 在原生 30 m、4096²、122.88 km 支撑域上记录两个各 15 天的声明事件，显示窗口为 50 km；这不是季节或全球模拟。`native-lowland-v1` 已 ready，`native-map-v1` 仍在审查；河段局部几何与湖泊溢流连接仍需核查。详见 `.scratch/river-upgrade-20261101/native-event-contract.md`、`native-event-report.md`、`native-lowland-contract.md`。旧 90 m 产品仅作参考；不要将此区域硬编码成全球产品。

**尚缺**：面向此世界的粗 DEM 与稳定主河湖产品、板块条件 TD 的固定 owner 页与持久缓存接线、粗水系约束细域的完整机制、统一只读查询及通用导出。已有局部规划机制不等于这些工作完成。

Terragenesis 负责物理来源、源身份和一阶段冻结产品；另一项目负责 atlas 世界域、调度控制器、适配器、缓存、导出及地图输入，美术在外部处理。两边立即并行：消费侧以冻结 fixture 和已有粗板块产品构建适配及测试，使用自己的输出目录；不要修改原始 TD、共用生成目录或消费未完成的 manifest。待主线发布冻结产品后按身份接入，无须等待另一轮许可。双方各自在自己的代码边界工作，避免同时编辑共享源文件。

## 推荐产品路线

1. 在固定种子下，以约 10–25 km 板块骨架规划至少 10,000 km 方域；先预检资源，再生成和审阅。以 5 km 间距制作首版世界 DEM，必要时考虑 2 km。插值只改变采样，不能算新增山谷或地貌细节；更细层若需新细节须另有声明的生成或物理来源。
2. 固定粗海陆、主河、湖泊、出口和流域身份；可选 250–500 m 区域层。按需准备局部 30 m TD，90 m 可从冻结 30 m 产品按明确规则降采样。不要生成全球 TD。
3. 选择跨页且有主河或湖口的区域，先验证来源覆盖、固定页复用与粗细衔接，再扩大范围。粗河路径、稳定 ID、湖面及出口必须约束细域；具体接线和约束方法仍待完成，不能假设当前接口自动做到。

核心交付是 DEM。若世界总览须显示窄于像元的河流，还需可选的河流中心线、湖泊边界和稳定 ID 等水文地理数据；严格只交粗 DEM 无法保留亚像元窄河形状与连通性。即使只向地图提供 DEM，内部仍需保留粗水系约束供细域使用。

以下仅为 10,000 × 10,000 km、单层 float32、未压缩的算术量级；不含水文、缓存、重叠、临时数组或模型资源，不是运行承诺：

| 格距 | 样点约数 | 4 字节高程层 |
| --- | ---: | ---: |
| 10 km | 1,000² | 4 MB |
| 5 km | 2,000² | 16 MB |
| 2 km | 5,000² | 100 MB |
| 1 km | 10,000² | 400 MB |
| 30 m | 约 333,334² | 约 444 GB |

实际资源依规模和实现实测。30 m 是采样间距，不是城市建设精度，街道、建筑和可通行性需要独立数据层。游戏接受合理近似，无须把源网格当科研级精度。

## 坐标、来源与拟议交换契约

世界使用米制 X 向东、Z 向南，高程米，海平面基准 0；数组按 `[z,x]`。当前板块是双向周期平面而非球面；如需经纬度、极点或球面距离，须另行设计转换和边界。有限产品查询应明确拒绝或标注越界，不把周期重复误称为新大陆。

板块产品 `terrain_pipeline/tectonic_product.py` 的 origin 是网格边界，中心为 `origin + (index + 0.5) * cell_size_m`；TD 产品 `terrain_pipeline/plate_td_product.py` 的 `origin_native_xz` 是 30 m 原生索引，首样点坐标为 `origin_native_xz * 30`，没有再加半格。现有原生事件控制格中心为 `(-61440 + 30*x, -61440 + 30*z)`；图的 jitter 只用于连通，不是床面采样坐标。转换须使用各产品实际元数据，不能套用同一个 origin 规则。

统一固定 `world_seed=20261020`；随机过程按稳定用途名确定性派生独立子流，记录派生方法和实际值，空间采样依绝对坐标而非请求顺序。板块演化的 plates、crust、velocity 用 SHA-256 派生（`terrain_pipeline/tectonic_evolution.py:_purpose_seed`）；板块 TD 入口固定该种子，不能宣称已有任意根种子的统一入口。固定 owner 页供查询复用，独立 TD 请求尺寸或环境变化不保证逐位一致。

以下为**建议契约，非现有 schema 或已实现后端**，由双方适配器实现并版本化：

- 每个产品携带 ready 状态、不可变来源身份/摘要、算法与模型版本、参数、种子及子流、来源边界、格网 origin 的语义、形状、间距、轴向、单位、海平面与数据版本。仅在发布完成且身份验证通过后消费；现有 native 产品以 manifest 为对应 ready 标志，其他产品按各自格式验证。
- 显式 prepare 可计算并发布；只读点/区域查询只读 ready 产品，缺失返回未准备/未知，不隐式生成。当前一些现有查询仍有隐式生成技术债，不能假定已符合此约定。
- 分开表达有效数据、无数据/未知、已确认海洋及已知陆地/内陆水体；负高程内陆洼地不自动等于海洋。跨边界未知上游供给保持未知。
- 水体记录稳定河流、湖泊、流域和连接/出口 ID，坐标、高程、流量等分别声明单位与来源；不得把局部临时编号冒充世界稳定 ID。导出包含这些身份及网格信息，避免覆盖源。

## 已核验的接入点

- 板块：`terrain_pipeline/tectonic_evolution.py:TectonicConfig` 默认 `shape=(128,128)`、`cell_size_m=10000`，仅 1,280 km 方域；`evolve(config, initial_state=None)` 生成，`tectonic_product.py:plan(config, *, max_memory_bytes=2000000000, max_cell_plate_steps=200000000)` 预检，`prepare(config, path, **budgets)` 冻结保存，`load_product(path, *, expected_identity=None)` 读取。`FrozenTectonicProduct.sample(x_m, z_m, *, outside="wrap", state="final")` 默认 wrap；有限来源要显式 `outside="reject"`。边缘半格的双线性插值仍周期跨边。`tools/prepare_tectonic_world.py` 支持 `plan` / `generate`、`--shape NZ NX`、`--cell-size-m`、`--origin-m X Z`、`--plates`、`--steps` 和资源上限；种子固定，generate 输出须为工作区内新目录。
- TD：`diffusion/plate_td_conditioning.py:make_plate_factory(source_path, expected_identity, seed, config)` 检查身份、固定种子、30 m 原生格和 7,680 m 条件格；`conditioning_footprint(origin, side)` 给出半开条件范围。`diffusion/plate_td_backend.py:generate(source, origin, side, config, *, expected_identity)` 运行 GPU 窗口，side 为 1–1337；`terrain_pipeline/plate_td_product.py:prepare(source, output, origin, side, config, *, compose_coast, expected_identity, relief_strength=0.0)` 保存，`read_product(path, expected_identity=None)` 读取。`tools/prepare_plate_td_source.py` 需 `--source --expected-plate-identity --output --origin-x --origin-z --side`；默认 CPU dry-run，`--generate` 才运行；可选 `--model-dir`、`--compose-coast`、`--relief-strength`。origin 参数是原生格索引；条件覆盖也必须在有限源内。
- 缓存：`diffusion/store.py:TerrainTileStore(identity)` 提供 `read(seed, tx, tz)` / `write(seed, tx, tz, elev, climate, meta)`；`diffusion/world_demand_backend.py:plan_source_pages(origin_native_xz, shape_zx)` 和 `run_source_page(origin_native_xz, *, model_dir, output_dir, world_seed=20261020)` 提供固定页及恢复基础，但后者 physical-default 不自动成为板块条件源。统一调度和缓存身份仍需接线。
- 水文：`terrain_pipeline/hydrology_planning.py:plan_macro_cell(seed, cell_x=0, cell_z=0, config=None, *, general=False)` 及 `save_plan(product, path)` / `load_plan(path)` 是现有规划工具，不是任意板块世界自动规划器；`hydrology_detail.py:derive_detail(plan, raw_height_m, *, origin_xz_m, spacing_m, raw_provenance, ...)` 提供冻结路径、共享边界与湖泊支持，保留原始 TD，并可能拒绝细化。需针对新来源完成集成与验证。
- DEM：`terrain_pipeline/dem_domain.py:prepare_dem_candidate` 读取地理参考 DEM，`save_dem_candidate(candidate, path)` / `load_dem_candidate(path, *, verify_source=True)` 保存/读取校验 NPZ；读取 GeoTIFF 不代表已有通用 GeoTIFF 导出。`terrain_pipeline/surface_rivers/metric_environment_query.py:sample_environment(seed, x_m, z_m, *, elevation_sampler=None, material_seed=None, soil_parameters=None, source_identities=None, orographic_policy="pending", climate_parameters=None, landform_ordinal=None)` 是带来源的环境采样，要求 30 m 对齐点，不是通用 RPG 世界 DEM 查询。

可在仓库根目录使用下列**只预检、不生成**的真实 CLI；具体规模须结合预算调整，拒绝是有效结果：

```powershell
python -m tools.prepare_tectonic_world plan --shape 1000 1000 --cell-size-m 10000
```

## 工作顺序与验收

### 另一工程可以立即领取的任务

| 顺序 | 工作 | 可交付结果 |
| --- | --- | --- |
| A1 | 以可配置源仓库/依赖路径接入 Python 地形模块；记录采用的代码版本及本地修改快照 | 独立适配层与可重复启动方式，不依赖 Minecraft 或本工程前端 |
| A2 | 用现有冻结样本实现只读点查询、范围裁取和坐标转换 | 返回高程、有效性、海洋分类、来源身份；缺页明确返回未准备 |
| A3 | 封装板块配置与预检入口，先跑小样，再准备万公里骨架与 5 km 世界 DEM | 世界参数清单、粗 DEM、来源/分辨率说明及实际资源记录；新增加的地形细节单独标明来源 |
| A4 | 建立按需区域准备队列和独立页缓存，接入板块条件 TD | 同一世界区域重复请求复用产品；不同剧情区域可独立准备，不预生成全世界 30 m |
| A5 | 对接粗主河、湖泊与出口约束，验证一个跨页的 30 m 故事区域 | 粗细地形对照、主要水系连接与边界检查，再向地图侧导出 |

A1–A3 可立即推进。A4 可先实现调度接口和冻结样本缓存，板块条件页的完整接线仍需开发。A5 依赖双方约定的粗水系产品；不要为了等待这一依赖，阻塞整个消费工程。另一工程若需要更改共享地形实现，先明确改动文件归属并回传补丁，避免两边同时改写同一工作区。

可用冻结 fixture 位于 `.scratch/river-upgrade-20261101/terrain-v3/`：`manifest.json`、`bed_m.npy`、`valid_mask.npy`、`ocean_mask.npy`、`unknown_mask.npy`；高程和分类为 4096×4096，30 m，首样点坐标 (-61440,-61440) m，来源身份 `c751a09a6f02e8c336b6b9b8fb4b11b5dc67386e9a8470b0b1d90858bf1ffb72`。这是当前本机实际文件，Git 克隆未必包含；由配置引用或另行复制到消费侧只读数据目录。不要只复制 manifest 而遗漏数组，也不要用这个 fixture 冒充万公里来源。可选水文 fixture 为同目录旁的 `native-event-v1/`，其相对来源路径在迁移时需要适配，现有 reader 不会自动重定位。

建议双方交换的最小交付包为：交接文档、源代码版本/必要本地补丁、fixture 数组及 manifest、运行环境与模型位置说明。模型权重通过已有本地配置引用，不把机器专属路径写死在另一工程代码中。本文不要求另一工程采用特定 Web 框架或前端技术。

消费侧先用隔离 fixture 实现来源校验、坐标适配、ready/unknown 和只读查询，再接已有粗板块产品。Terragenesis 主线继续完成一阶段；随后双方固定世界边界、粗产品和水体身份，接入按需页，试一个跨页河湖区域并导出。没有已验证的统一 `world DEM` 生成、查询或导出 API，以上路线是实现任务，不是可直接调用的命令。

验收以游戏用途为准：粗图可辨大陆、山脉、海岸和主要河湖；样例细域的主河、湖岸和出口与粗约束衔接，跨页无明显断裂；已知/未知及越界正确，重开同一冻结产品得到相同身份与查询结果。记录实际时间、内存、磁盘和失败恢复；允许记录小幅高差与次要支流差异。参见 `.scratch/rpg-world-dem-20261101/assessment.md` 和 `resolution-recommendation.md` 获取依据。
