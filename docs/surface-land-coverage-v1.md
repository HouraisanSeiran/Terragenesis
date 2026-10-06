# 陆地半像素工程覆盖 v1

本模块仅接受已冻结 32 聚合包，身份 `381e60743e03cee6859c5cce46cb6337c8ea601ed5eb4cc1258e18cf51092860`。
旧来源、旧模块及旧包不修改。显式 `prepare_surface_land_coverage` 生成新几何；保存、加载和查询不准备、恢复、组装地形或推进状态。

## 来源解释与切方阶段

这是一种新声明的 `clamped_engineering_interpretation`，不是实测海岸或自然流域认证。
陆地范围 x5..145、z5..75，以 1m 节点保存 10011 个唯一节点、9800 个方格、19600 个三角形。
域分界 x75 的 71 个节点共享，左右各 4900m²，每个陆地方格只归一个域。

原 candidate 陆地像素中心 H0 在半像素外缘 clamp 到 x10..140、z10..70；内部使用双线性。
保存四角 indices/weights/positive_mask/valid_land_support/protected_support，所有正权支持必须是 valid land。
零权支持可能落在 ocean，不能贡献高度、保护或有效性。旧内部全部节点数组和三角拓扑逐项保持。

北、西、东外缘 H2=H0、水面0。南缘 z70 整行保留旧 mosaic；x38..41 与 x108..111 的 z70..75
床面/水面严格使用各自实际 drop。新 land H0 仍取原 candidate clamp，不采用旧 synthetic corridor H0。
`phase=original_land_clamped_h0_with_engineering_bed_water` 明示这种双来源接缝：切方基准是原陆地 H0，
加工床面来自实际工程 drop。dry-cut bank x35..37/42..43（第二域 +70）向 z75 线性衰减，水面0。
只有 all-wet 三角形参与静态水量积分。禁止保护切割、unknown 支持、负切深及切深超过4m。

新增外圈切方预计算为 70.77028762295504m³，限额固定100m³，最大切深2.294117033896341m。
旧内部切方576.8710544290027m³独立保留；新 land 总切方647.6413420519577m³。
不与旧两 drop 各100m³预算混账，不以旧 synthetic H0 重新解释外圈切方。

## 唯一裁接与动态限制

旧 drop 的 z70..75 三角形仅由新 landmesh 表示，不再次积分；outside_outlets 仅保存 z75..90，
每域45m²，共90m²。外口保存 source node/triangle IDs、shared_land_node_ids 和原始 XYZ，
z75 四个共享床/水节点完全对齐。图 Q 仍每出口一份，不按面积重新累计。

`dynamic_boundary_z_m=70`，`static_geometry_coast_z_m=75`：现有 lumped graph 的 prescribed boundary
仍在 z70，不因几何扩展变成全 land 流体求解。V(h) 仍只使用旧676 wet cells；海口动态 storage 未计。
静态陆地包含706 wet cells（旧676加南缘30），不是动态 V 的676 cells。
静态陆地水量252.72852290299738m³与外口47.257489257730654m³不是动态库容。
验证器按保存三角坐标 determinant 独立计算面积与水量，不更换旧三角对角线。

`land_pixel_footprint_represented=true` 仅指上述工程解释；`natural_outlets_certified`、
`general_cross_precision`、`dynamic_fine`、`full_dynamic_wave_prepared`、`ready_for_3d` 均 false。
不解除自然流域、完整波动、地下或多层三维河网门禁。

## 静态验真与运行

静态校验按保存节点/方格/三角映射检验唯一拓扑、域归属、来源插值、旧内部完全相等、
湿 strip 和干岸公式、裁接映射与独立预算；不调用 `_algebra` 或 `_topology` 生成目标几何。
Archive 全部 ZIP/NPY 元数据与严格 AST 头预检在任何 payload 加载前完成；禁止对象 pickle、
压缩、重复成员、float/bool 形状、整数 Fortran 标志及重复头字段。资源包括来源、生成网格和工作副本，
在生成前检查。保存同目录临时文件加原子 hardlink，不覆盖目标，失败不发布部分成品。

运行 `D:/anaconda/python.exe -X utf8 tools/verify_surface_land_coverage.py`。
验证器缓存 fixture，输出新的 UTC verification 目录，包括 NPZ、独立面积/切方报告、focused 测试与哈希。
`land-coverage-review.json` 的 `saved_query` 包含 land nodes/cells/triangles/domain_owner、strip mask、
两 cropped outlets、ledger、phase 和限制，可供现有前端 adapter 追加；本模块不修改前端或声明浏览器验收。
