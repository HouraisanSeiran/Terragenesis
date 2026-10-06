# 三维地表/地下几何与 VDM 纯 IO 审查

日期：2026-10-06

范围：只读检查当前三维地表、地下几何、VDM 保存接口和前端消费边界。未修改 `web-preview/`、Java/JAR、原 Terrain Diffusion/source，也未修改任何既有 `verification/` 验证包。

## 结论

当前结果可以接入前端做“保存几何审查”，但接入形态应是独立的只读案例包，不应直接把几何生成器、审计器或水力求解器放进浏览器。

可消费的首个地下案例已经具备前端所需的主要数据：

- 地表来源片段：`verification/natural-river-network/shared-port-channel-review-20261006-01/review.json`。
- 不可变 typed graph：`verification/natural-river-network/hybrid-river-graph-20261006-01/graph.json`，122 节点、121 弧；动态水状态不包含在内。
- 地下几何审查包：`verification/natural-river-network/hybrid-cave-review-20261006-01/review.json`。
- 网格消费包：同目录 `caseartifact.json`，schema 为 `td-hybrid-cave-mesh-case-v1`。
- 独立几何证据：`verification/natural-river-network/hybrid-cave-geometry-20261006-03/independent-audit-v2.json`，当前 `status=passed`，且 `binding_status=matched`、`referenced_status=passed`。

因此，前端可以显示地表半臂、`rock_before`、`cutter`、`rock_after`、`removed`、洞道 chart、VDM reference/displacement/derived 和实际断面选择。当前工程没有发现一个同时绑定这些文件、统一做 SHA/identity 门禁、面向网页提供案例索引的最小入口；这是本轮最小 IO 补口。

## 几何与 VDM 现状

地下首例是限定范围的局部工程几何，不是完整三维河网产品：

- 洞道长度 125.2468065569576 m，17 个站，19 个实际水力断面；`gallery:4..12` 为实际岩体封闭核心，其余是敞口坡道。
- `rock_before`、`rock_after`、`cutter`、`removed` 均为带 `local_origin_xyz_m` 的局部实体网格；顶面是 1 m 采样近似，字段明确 `sampled_not_native_exact=true`。
- Boolean 差、两个实际地形坡道开口和空域路径已有独立证据；控制用的 canonical `sink/spring` 点、实际 `portal_opening_witnesses` 和 gallery 核心边界必须在界面中分开标注。
- VDM 使用 `td-hybrid-multichart-vdm-v1`。每站同时保存 reference ring、displacement ring 和 derived ring，并保存 234 个 cutter 三角形；洞底和端口保持不移动。它明确不是旧 `metric_vdm` 固定 chart 接口，也不应覆盖或重解释旧 VDM。
- 地表细床、洞道实体、岩体切除量和动态水面是不同语义。已有 `caseartifact.json` 的 `mesh.water=null`，不能由前端根据断面或 VDM 自行补造水体。

三维地表已有可复用的保存审查路径，`docs/surface-review-viewer.md` 规定浏览器只读派生 JSON，不直接解析 NPZ、不执行 prepare/recovery/advance/solver。这套边界可直接沿用到地下几何案例。

## 能否接入前端

能，但当前应标成“只读保存几何审查”或“局部地下几何案例”，而不是“地下水系完成”或“VDM 水力结果”。推荐的首期画面顺序如下：

1. 读取一个独立案例 manifest。
2. 校验 manifest 中的文件 SHA-256、geometry identity、graph identity、VDM identity 和独立审计 binding。
3. 使用 `local_origin_xyz_m` 将网格转到局部浮点渲染坐标，再按保存的世界 XYZ 米制显示位置。
4. 通过图层开关显示地表半臂、原岩、切割体、剩余岩体、移除岩体和洞道；默认关闭拓扑线。
5. 用站点选择器显示实际断面、`kind`、`route_region`、封闭/敞口分类和 portal opening witness。
6. 将 VDM 三套 ring 作为几何对照显示，位移向量只作位移可视化，不推导水体或地质真实性。

前端消费必须保留以下状态标签：`hydraulic_solved=false`、`three_dimensional_flow_solved=false`、`full_network_verified=false`、`natural_outlet_certified=false`。地下审计通过只表示有限几何和开口证据通过；它不授权水量动画、连续三维水面、自然海口或完整河网宣称。已有水力包也不能在当前状态接入，因为本轮记录明确存在未通过的细化/预算案例。

## 本轮建议新增的最小纯 IO 接口

建议新增独立工具，例如 `tools/export_vdm_geometry_io_review.py`，以及一个独立保存 schema，例如 `td-vdm-geometry-io-review-v1`。它只读取已经存在的 `review.json`、`caseartifact.json`、geometry/index、VDM 和 audit 文件；不调用 `prepare_*`、`build_*`、source sampler、Boolean、VDM 生成器或 solver。

建议命令形态：

```text
python tools/export_vdm_geometry_io_review.py \
  --case verification/natural-river-network/hybrid-cave-review-20261006-01 \
  --geometry verification/natural-river-network/hybrid-cave-geometry-20261006-03 \
  --graph verification/natural-river-network/hybrid-river-graph-20261006-01/graph.json \
  --output <new-output-directory>
```

工具只做四件事：

- 冷读并校验允许的输入文件、文件 SHA-256、schema、identity 和数组/三角索引边界。
- 将前端需要的元数据和网格字段整理为独立输出；不重新采样、不重三角化、不坐标变换原始几何。
- 复制或引用必要的 PNG 审查图，并把所有相对路径解析为输出包内路径。
- 原子写入 `manifest.json`，失败时不发布半包；输出包新建目录，拒绝覆盖既有目录。

最小 `manifest.json` 可采用下列结构：

```json
{
  "schema": "td-vdm-geometry-io-review-v1",
  "status": "saved_geometry_review",
  "coordinates": {"system": "local Cartesian metres", "axes": "X east, Y up, Z south"},
  "case": {"geometry_identity_sha256": "...", "graph_identity_sha256": "...", "vdm_identity_sha256": "..."},
  "audit": {"status": "passed", "binding_status": "matched", "geometry_sha256": "..."},
  "layers": {
    "surface_attachment": {"path": "surface_attachment.json", "role": "surface_half_arm"},
    "rock_before": {"path": "rock_before.json", "role": "remaining_rock_before"},
    "cutter": {"path": "cutter.json", "role": "derived_cutter"},
    "rock_after": {"path": "rock_after.json", "role": "remaining_rock_after"},
    "removed": {"path": "removed.json", "role": "excavated_rock"},
    "conduit_vdm": {"path": "vdm.json", "role": "reference_displacement_derived"}
  },
  "stations": {"path": "stations.json", "count": 17},
  "flags": {
    "hydraulic_solved": false,
    "three_dimensional_flow_solved": false,
    "full_network_verified": false,
    "natural_outlet_certified": false
  },
  "limitations": ["sampled_not_native_exact", "no_water_mesh", "local_bounded_case"]
}
```

每个 mesh 文件保留现有字段：`schema`、`role`、`identity_sha256`、`local_origin_xyz_m`、`vertices_local_xyz_m`、`triangles`、`signed_volume_m3`、`sampled_not_native_exact`。接口不要把局部顶点改写成大世界绝对坐标，也不要把 `signed_volume_m3` 混作水量或原生精确地质体积。

## 接入门禁与验收

导出工具应在发布前拒绝以下情况：

- `review.json`、geometry、graph、VDM 或 audit identity 不匹配。
- audit 不是 `passed`，或 binding 不是 `matched`。
- 缺文件、未知 schema、三角索引越界、非有限顶点或不安全数组类型。
- 试图把未通过水力结果、checkpoint、配置或失败 partial 包加入 manifest。
- 输出目录已存在，或导出过程中出现半成品。

最小工具验收只需覆盖：冷读无生成调用、SHA/identity 绑定、网格逐字段无损、三角索引和局部 origin 保留、输出 manifest 原子发布、拒绝错误 audit，以及四个能力 false 标志原样保留。可以新增独立 `tests/test_vdm_geometry_io_review.py`，但测试输入应只来自现有保存包，不能改写冻结包。

## 不建议本轮做的事

- 不把地下 mesh 接入既有地表 review 页面，除非另有前端任务；本报告只提供可供前端消费的纯 IO 契约。
- 不导出 glTF/OBJ 作为唯一接口。它们可作为附加预览格式，但会丢失 source pin、role、station、portal 和 audit 语义；规范消费应以 manifest + JSON mesh 为准。
- 不把 VDM displacement 当作可重复执行的算法 API，不在浏览器重建 chart 或重新施加位移。
- 不导出动态水面、连续水体或水力动画；当前几何审计不能授予这些内容。
- 不修改 `web-preview/`、Java/JAR、原 Terrain Diffusion/source、既有 verification 包或冻结验证依赖。

## 审查依据

- `docs/hybrid-river-network.md`
- `.scratch/hybrid-river-network/frontend-consumption-contract.md`
- `docs/terrain-artifact-v1.md`
- `docs/surface-review-viewer.md`
- `verification/natural-river-network/hybrid-cave-review-20261006-01/review.json`
- `verification/natural-river-network/hybrid-cave-review-20261006-01/caseartifact.json`
- `verification/natural-river-network/hybrid-cave-geometry-20261006-03/geometry.json`
- `verification/natural-river-network/hybrid-cave-geometry-20261006-03/independent-audit-v2.json`
- `verification/natural-river-network/hybrid-cave-geometry-20261006-03/vdm.json`
