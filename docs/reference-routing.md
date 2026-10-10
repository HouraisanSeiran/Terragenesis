# 成熟河网后端接入：pyflwdir

2026-10-09。当前接入固定为 `pyflwdir==0.5.12`（MIT），要求 Python 3.11+。官方来源：[项目仓库](https://github.com/Deltares/pyflwdir)、[文档](https://deltares.github.io/pyflwdir/)。本轮实际读取安装版本的 `pyflwdir.py`、`dem.py`、`flwdir.py`、`streams.py` 等源码，并运行真实库验证；各后端源文件 SHA 随结果保存。

## 本轮改进

新增的图分析入口直接调用成熟库的 `from_array`、`accuflux`、`basins` 和 `stream_order`，从已有 TD 图计算汇水面积、终端贡献域和 Strahler 河流等级。通用计算交给 pyflwdir，项目负责米制坐标、有效格、边界分类与来源身份转换。

既有 M1/M2–M6 固定包、默认求解器和在途河槽/湖泊实现保留其版本身份。新功能有可运行的独立 CLI，尚未改为历史产品默认后端；本轮未承诺运行速度提升或河线形态改善。Minecraft 留作后续消费子项目，本轮不搬目录、不构建或增加游戏功能。

## 两个调用方式

| 接口 | 适用范围 | 执行行为 |
| --- | --- | --- |
| `analyze_td_graph(terrain, boundary, graph)` | 现有 `TerrainGrid` / `BoundaryGrid` / `RoutingGraph` | 原样转换 receiver，保留未知格、闭合盆地、规定边界和出口分类；用成熟库计算图指标 |
| `run_reference_routing(terrain, boundary, config)` | 全有效、正方形网格、外围开放、内部无指定边界的DEM | 显式运行 pyflwdir 的填洼/重排水政策，生成独立对照图 |

优先采用第一种。第二种的出口选择与 TD 的“全部开放外围格均为终端”不同，结果使用 `reference_edge_exit` / `reference_pit` 分类，比较记录明确 `equivalent_boundary_policy=false`。含 unknown 的地形走第一种；pyflwdir 的 DEM 自动路由会把 nodata 边缘作为出口候选，因此第二种对此明确拒绝。

重排水方式记录 `max_depth` 和 `outlets=edge|min`；有限填高阈值不构成自然湖泊判定。支持 `max_depth=-1` 或正数，0阈值不属于本版支持范围。已检查的后端使用 float32 优先队列高程，且路由计算本身不消费 dx/dz；因此它不是 TD float64、矩形格最陡米制坡度政策的等价实现。重排水不会修改输入地形，也不会自动生成河槽。

## 数据与适配修正

- pyflwdir 的终点 receiver 指向自身，转换为 TD 的 `-1`；排序本来就是下游优先，不反转。
- 排序只包含有效格；网格数组保留完整长度，未知格的面积/流域/等级分别为 `0/-1/0`。
- 地图变换以格心匹配 `TerrainGrid.world_xz`，使用 `northing=-Z`；这是本地米制映射，不补造地理 CRS。
- 面积通过 float64 `dx*dz` 输入 `accuflux`，避免外部默认面积精度影响矩形格统计。
- 贡献域标签统一为对应终端的 `cell_id`；不直接比较任意盆地编号或两个合法排序的排列顺序。
- 校验DAG、邻接、unknown角点、逐节点面积递推、终端总面积、流域归属和Strahler汇合规则。数组使用独立只读存储，嵌套元数据冻结。

`result_to_record(result)` 返回现有 `save_bundle` 可直接保存的 `{arrays, metadata, identity_sha256}`。`validate_reference_record(record)` 仅检查已保存数据，无需安装或运行 pyflwdir。它验证保存图的内部一致性；原始来源的可信绑定由外层 CLI 的 manifest 和父包 SHA 提供。

`compare_reference_to_td(result, graph)` 返回流向、终端格与面积差异。对同一保留图，应全部为0；重排水比较的非零结果表明政策差异，不能据此认定某一政策是自然真值。这里输出汇水面积与等级，未运行降雨产流、水动力或泥沙求解。

## 运行

现有环境安装可选依赖：

```powershell
python -m pip install -r algorithm/requirements-reference.txt
```

本次实际使用工作区隔离目录，未修改系统安装：

```powershell
$env:PYTHONPATH=(Resolve-Path '.scratch/reference-routing-deps').Path
D:/anaconda/python.exe -X utf8 -m tools.prepare_td_reference_routing --input verification/td-river-milestones/td256-20261008-01 --manifest-sha256 70f8fff227f4c32d12758157e8a958eda115b9a9629b3202b5d492d5d536c07b --policy original_bed_d8 --output verification/reference-routing/td256-new
```

支持已有保存政策 `original_bed_d8`、`priority_flood_d8`、`adapted_d4`，不会重新生成这些图。输出目录必须不存在；先在暂存目录完成生成与冷读，再原子发布 `graph-analysis.npz` 和 `report.json`。保存来源、原图、转换器和后端身份，结束前核对输入字节与代码未变。

## 实际结果

唯一集成包：`verification/reference-routing/td256-20261009-01/report.json`。

| 指标 | 结果 |
| --- | ---: |
| 原生网格 | 256×256，30m |
| 有效格数 | 65,536 |
| 终端数量 | 1,470 |
| 开放终端 / 保留闭合终端候选 | 1,020 / 450 |
| 终端汇水面积合计 | 58,982,400m² |
| 最大单终端汇水面积 | 1,268,100m² |
| 最大 Strahler 等级 | 5 |
| receiver / 终端格 / 面积差异格数 | 0 / 0 / 0 |
| 输入字节及原图 | 保持一致 |

`graph-analysis.npz` SHA256：`450266044d39348173e3e88c7d13be6f05360fa1a7329e5b63a02133388e1efb`。这些是完整诊断排水图的统计，包括细小汇流边；不等于可见河流数量或实际湖面面积。

9项针对性测试通过，包括真实pyflwdir的带孔洞Y形图与DEM政策对照、float64矩形格面积、不可变性、无依赖冷读、重新签名后篡改拒绝、CLI来源pin和不覆盖发布。新增CLI实际读取上述TD保存包，完成一次分析/保存/冷读；没有重复原降雨、水力或GPU生成。

## 接续建议

1. 后续需要新增汇水面积、等级和贡献域计算时调用 `analyze_td_graph`；冻结的旧内核用于历史重现，避免再新增同类通用算法。
2. 若要替换DEM排水核心，先明确保留盆地、unknown、格距、出口与平地政策，再选择支持这些约束的后端；从图统计接入不能直接跳到全替换。
3. 侵蚀可评估 Landlab/SPACE/Fastscape；完整水动力应专项比较成熟求解器。自研来源与耦合契约不意味着必须自研每个数值内核。
4. 地表/地下实体、VDM、自然出口、跨精度通量和应用层继续独立验收；本包的 `hydraulic_ready`、`natural_outlet_verified`、`publishable` 保持 false。
