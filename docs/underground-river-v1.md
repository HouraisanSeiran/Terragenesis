# 地下暗河生成与前端预览 V1

## 已实现范围

第一版在已保存的真实 Terrain Diffusion 山地采样岩体中，以固定的潜入点、复出点和17站洞道样例为基础，生成带种子身份的新洞道几何。内部侧向路径、断面宽度和洞顶形态可以改变；两端断面保持原样，避免参数变形偷偷移动接回位置。坐标为 XYZ 米制，Y 向上；来源不变，结果另存，不写 Minecraft 世界。

这是**固定山地窗口中的有界构造洞道生成器**，不是从任意地图自动识别岩溶、选洞口、寻找路线或生成多层暗河网络。继承来源的 geometry03 审计不等于新参数成果已经独立审计，也不等于完整地表接回端口通过。当前状态为 `geometry_checked`，表示生成器几何检查通过。

生成使用 `manifold3d==3.5.4` 的 Mesh64 实体布尔运算，输出开挖前岩体、开挖体 `cutter`、开挖后岩体和实际移除岩石。VDM 多断面保存 `reference + displacement = derived`，洞道不是叠在地形上的装饰线。

生成器检查核心段实际覆岩、固定裁剪边界、非相邻扫掠投影重叠、移除体连通、材料体积收支、逐段空气路线和两个实际地表开口。完整射线、来源采样及开口见证随包保存。超出参数、预算或几何约束时明确拒绝，不缩小用户参数或伪造结果。

覆岩证据来自离散站点环顶点及连续的封闭站点索引，不等于整个站间洞顶/壁面连续最小覆岩已认证。空气路线的逐段射线检查与覆岩检查分开，也不等于全部洞口截面认证。

## 固定成果

- 默认包：`verification/natural-river-network/underground-river-v1-20261006-01/index.json`。
- 默认参数：seed17、侧向幅度1m、宽度倍率1.05、洞顶变化0.2m。
- 洞道长度125.3232537059252m；实际切岩1885.0505245753225m³。
- 材料账残差7.73070496506989e-12m³；9个有覆岩的核心断面。
- preview identity：`11384908c1309b3b92b710a83946d232f83333d100ab6ce64e76c38c7a6245c8`。
- `water=null`；`hydraulic_solved`、`full_network_verified`、`natural_outlet_certified` 均为 false。不显示假水面或假流动动画。

原 geometry03、地表连续床、拒绝的端口与水力证据、原始 terrain source 均未修改。新洞道切岩账仅针对局部采样岩体，不能与全域 fine 材料账相加冒充新全域账。

## 算法接口

`terrain_pipeline.underground_river_v1.Parameters` 接受四项参数：

| 参数 | 范围 | 作用 |
| --- | --- | --- |
| `seed` | uint32 | 确定侧向及洞顶变化相位 |
| `lateral_amplitude_m` | 0..3m | 内部路径的水平侧向变形 |
| `width_scale` | 0.8..1.2 | 内部断面宽度倍率 |
| `roof_variation_m` | 0..0.5m | 内部洞顶高度及侧向变化 |

`deform_charts(source_vdm, parameters)` 返回新站点及扫掠三角拓扑，不修改输入。

`build_preview(rock_record, source_vdm, sampler, source_pins, parameters)` 执行有界布尔及几何检查，返回 `td-underground-river-preview-v1` 记录。几何证据中世界坐标和局部坐标分别标记。

`tools/prepare_underground_river_v1.py` 校验固定来源 SHA/identity 和冻结代码，原子发布新包；目录已经存在则拒绝覆盖。运行独立参数成果：

```powershell
& D:/anaconda/python.exe tools/prepare_underground_river_v1.py --seed 18 --output verification/natural-river-network/underground-river-v1-seed18
```

单次限制60秒、1GiB进程RSS检查、64MiB包体。网页额外用60秒子进程超时和单次生成锁限制运行。producer的时间/RSS检查不能中断正在执行的native Boolean，RSS不是操作系统强制配额。index的elapsed_s在序列化前记录，完整发布另有时间检查；网页子进程超时覆盖发布。

## 前端接口

在本工程运行：

```powershell
& D:/anaconda/python.exe -X utf8 web-preview/serve.py --port 8765
```

打开 `http://127.0.0.1:8765/?workspace=underground`，归类为「河网算法 → 地下暗河 · 第一版生成」。可查看洞道、开挖前后岩体、移除岩石、VDM参考面、断面及沿程剖切；中心线默认关闭，半透明岩体默认开启。支持2D/3D、轨道相机、站点选择、参数生成和审查导出。站点的世界坐标由裁剪锚点加局部坐标得到，不受显示垂直倍率影响。

- `GET /api/underground/case` 只读默认保存包，校验包身份、preview SHA、来源 SHA及参数一致性；不重算。
- `POST /api/underground/generate` 接受上述四个字段，不接受来源路径；仅显式点击生成时运行。
- 新成果写入独立 `underground-river-v1-preview-<uuid>` 包，不改变默认包。
- 生成中清除旧几何，禁用导出；失败不回退假成果；过期导航响应不覆盖当前视图。

浏览器真实seed18生成、旧包重新读取、剖切、导航隔离、桌面/手机画布与相机检查通过，证据见 `verification/frontend-review/underground-v1-20261006-01/report.json`。仅显示修正后的检查不再生成新几何，见 `underground-v1-20261006-02/report.json`。

## 下一步

2026-10-07 接续：固定 seed17 包新增有限独立冷读报告 `verification/natural-river-network/underground-cold-audit-20261007-01/audit.json`，四实体布尔/材料、源岩体不变、固定端点、VDM/断面关联及空气路径通过；6项定向回归通过。入口为 `tools/audit_underground_river_preview.py --index <index.json> --index-sha256 <SHA256> --output <新的审计文件>`。该报告不改变原包的 `geometry_checked` 状态，不重放种子配方、不认证连续覆岩/完整接回端口/水力，其他参数变体不继承本报告。接续任务见 `.scratch/river-continuation-20261007/spec.md`。

1. 自动选择合法潜入/复出点，加入地层、覆盖厚度、断层约束及有界路线搜索；当前固定洞道不能承担这些能力。
2. 从单洞道扩展到 typed 水系图中的分叉、汇合、多层洞道；为每段确定独立来源及材料所有权。
3. 修复并独立审查地表接回的全端口几何；旧 composition03 sink 退化切片拒绝仍保留。
4. 重新定义并验证开口/封闭断面水力、蓄量、传播、回水及地表交换；旧07/08/09失败不继承为通过。
5. 自然海口认证、完整主流域细槽水力及独立跨精度河网仍属于后续主线。
