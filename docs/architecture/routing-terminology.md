# 路由术语（2026-11-08 收口）

本文是河网**空间离散与流向**命名的唯一权威定义。此前代码、文档与评审记录把三种不同的东西都写成 "D8"，造成过实际误读（2026-11-08 对照 dreamulator 时，本工程被误述为"使用栅格 D8"）。新增代码、docstring、验收记录与评审意见一律按本文用词。

## 1. 三个不同的东西

| 术语 | 定义 | 用在哪里 | 禁止的说法 |
| --- | --- | --- | --- |
| **图接收点**（graph receiver）<br>全称：不规则图单流向最陡坡 | 节点按绝对世界坐标确定性抖动（0.7 格），块内 Delaunay 三角化后用真实边长求最陡下坡，每节点一个 `receiver`；平地与未解决格保持显式汇点 | 30 m 主线：`drainage.strict_receivers`、`new_world_stage1.route_native_graph`、`native_30m_source.build_strict_topology` | ~~strict-D8~~、~~严格 D8~~、~~栅格 D8~~ |
| **宏观格 D8** | 规则栅格 8 邻域、每格一个最陡下坡方向（对角距离 √2） | 只在粗规划与审计掩膜：`hydrology_detail` 的 `cross_owner_d8_mask` / `unplanned_sink_mask`、三角洲与河口的 8 邻域几何搜索 | 用 "D8" 泛指本工程河网；用宏观 D8 结果冒充 30 m 河床 |
| **D4 分组 / D4 面** | 规则栅格 4 邻接：连通分量标记、湖盆蓄水曲面、有限体积共享面 | `basin_topology._neighbors`（盆地层次）、`metric_highland_sources._D4_STEPS`（**仅**源区分组）、`environment_delta_fv` 与 `world_process_estuary` 的有限体积 | 把 D4 连通当作汇流方向；把 D4 湖盆数量当作自然湖泊数 |

## 2. 判定方法

改动或评审时按顺序问：

1. 这段代码是否读 `shape=(rows, cols)` 的二维数组并按 ±1 行列偏移取邻居？否 → 不是栅格 D8 / D4。
2. 邻居是否来自 `indptr/indices`（CSR）或 `mesh`？是 → 图接收点，不是 D8。
3. 用途是汇流路由，还是连通分组／审计掩膜／有限体积面？只有前者才涉及"流向"命名。

## 3. 为什么不是 D8

- **邻域不同。** 抖动后 Delaunay 的度数约 6 且逐点不同，没有"固定 8 方向"，也没有 45°/90° 方向量化。
- **边长不同。** 接收点比较的是真实边长下的坡度（`hypot`），不是 1 与 √2 的栅格约定。
- **平局键不同。** 图上按节点编号破平（已知缺陷，见下），栅格 D8 按固定的邻居遍历顺序破平。

## 4. 仍然存在的问题（不属于术语，不要用改名掩盖）

1. **平局键是窗口局部编号。** `_strict` 的破平键 `target < receiver[node]` 是相对索引；抖动坐标是绝对坐标，但破平不是。平地与等坡面上的选择仍可能随窗口原点变化。应改为世界坐标派生的稳定键。
2. **平地不做路由。** 图接收点让平地为显式汇点（`flats remain explicit sinks`），这是保守取舍，不是 bug；但会留下断头，需要在产品层用微洼地溢门或填洼工作面处理。
3. **单流向。** 图接收点仍是单流向，坡面汇流会被压成细线；MFD / D∞ 未采用。
4. **宏观格 D8 的残余命名。** `hydrology_detail` 等模块的 `d8_*` 键与掩膜是准确的（它们确实是宏观栅格 D8），不要为了统一而改这些存储键；改名会动已保存产物的身份。

## 5. 与外部工程的对照

dreamulator 的河网确实是规则栅格 D8（`media/canvas_hydrology.flow_directions`）：固定 8 邻域、对角 √2、`(level, 全局 index)` 破平，并用 ε 坡化让平地也有方向。两边的共同点是**单流向最陡坡**，不是"都用 D8"。详细对照见 [dreamulator 河网算法对照](../research/dreamulator-河网算法对照-20261108.md)。

## 6. 历史名称的处理

- 代码 docstring、工具说明与测试注释中的 "strict-D8" / "严格 D8" 已统一改为"图接收点（不规则图严格下坡）"（2026-11-08）。
- 已保存产物、metadata 键、算法身份字符串中的 `d8` 一律**保留原字面**：它们对应的是宏观格 D8 的真实语义，且改名会破坏哈希与冷读校验。`finite_river_event.ROUTING_POLICY` 这类持久化策略名同理，保留 `d8` 拼写并在 docstring 注明它指图接收点。
- 新增代码禁止使用栅格 D8 做河网流向（2026-11-05 用户决定，记录见 `third_party/textingdream-terrain-20261108/docs/river-routing-d8-deprecated.md`）。
- **机生成台账的同步状态**：`CONTEXT.md`、源 docstring、`docs/architecture/module-catalog/annotations.json` 与 `docs/architecture/module-map.{md,json}` 已同步。`docs/architecture/world-generation-system/{stage-1.md,modules.json,support.md}` 与 `module-catalog/{catalog.json,category-B-01.md,tools-02.md}` 仍是旧措辞。
  刷新方式：`runtime/venv/Scripts/python.exe -B tools/build_module_catalog.py --write`，以及生成 `world-generation-system/` 台账的对应工具。
  **暂缓原因与决定（用户 2026-11-08）**：当前工作树含未跟踪的在途气候/环境模块，提前重生成会把它们写进台账；**等气候库落库后统一刷新，并单独提交**。`docs/architecture/archive/` 为冻结历史，**不**回改。
