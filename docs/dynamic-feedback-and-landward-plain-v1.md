# 逐日水沙反馈与陆侧沉积

日期：2026-10-16。验收状态和实际产物统一见[当前进度](delta-progress-handoff-20261016.md)。此前草稿重复运行全年并重置库存、陆侧加高遗漏单元面积、失败后退回冻结结果，均不构成动态算法验收；相关完成声明撤回。

## 计算顺序

`metric_dynamic_feedback.route_feedback_daily` 使用既有河段的真实坐标、接收关系、季节流量和有限材料来源。每个物理时间窗只推进一次：

1. 读取上一窗床面、松散层、移动泥沙和剩余岩床，按节点到 receiver 的实际距离计算坡度。控制体长度用于存储面积，不能代替节点间距。
2. 用当前床坡、宽度和当天 Q 求矩形 Manning 正常水深。反坡或平坡不靠微小正数掩盖，当前闭合明确拒绝，需另行使用支持回水的求解器。
3. 根据水力半径和坡度计算剪应力与输沙能力，先侵蚀有限松散层，再侵蚀满足硬度阈值的有限岩床。沿程沉降与再搬运更新库存，出口只交付实际送达泥沙。
4. 从固体库存和岩床移除量重建床面，进入下一时间窗。全年各窗的账本与库存轨迹合并并重新计算保存身份。

主要关系：

```text
Q = A R^(2/3) sqrt(S) / n
tau = rho g R S
capacity = Kt width max(tau - tau_sediment, 0)^(3/2)
rock_threshold = base_rock_threshold (1 + 4 hardness)
rock_erodibility = base_rock_erodibility (1 - hardness)^2
survival = exp(-settling_velocity length / (velocity depth))
height_change_from_loose = solid_change / ((1 - porosity) cell_area)
```

硬度、初始松散层厚度和可蚀岩厚度在本例是明确的材料情景。水量来自所选上游集水区，泥沙首例只覆盖已建模主干材料，不能称为整个2500km²流域的岩性输沙预测。经验系数需要后续校准；没有用 SRHarness 自动搜索的公式替换上述核心。

## 陆海交接

陆侧入口必须位于同源原始陆地；上游计算在交接点截止，下游区域只消费该点逐窗实际输出，不重复使用交接点以下的河床侵蚀。细河床与30m地形的高差须保存，不能靠隐式挖填伪装为沉积。

河口复用 `simulate_fluvial_delta`，每窗沉积或再侵蚀后，下一窗按新床重算可达路径与分配。它是地形阻力和体积传递近似，`river_head_m` 只限定可达高程，不是已求解水面。水通过某格不能据此认定该格是湿地；应区分原陆地净沉积、潜在过水范围、海平面以上新增面积及真实水深证据。单独的 `deposit_landward_plain` 仅为面积换算辅助函数，不能用它替代河口路由。

上游正常流反馈和河口床变路由不等于完整双向水动力：尚未求解河口水位顶托上游、潮汐、波浪或洪峰传播。不得将它发布为水力已就绪的默认世界。

此前16km风格化岛湾与1.5–2.5km陆侧整地任务保持独立身份。有限真实供沙案例即使产生陆侧沉积，也不能自动认定已完成那份大范围设计地形规格。

设计平原采用保留上游纵剖、显式过渡和两岸支撑的构造方式。保存旧高程与场景基底不兼容时，保留纵剖需要大量支撑填方；它不会被加入自然泥沙账。图审发现旧构造在河槽边缘产生约132m异常深水，修正通过先抬建支撑岸坡再切出河槽解决，不能靠裁剪水深解决。上游保留仅指实际河床核心和纵剖，两岸支撑为新构造，并非旧场景整个断面原样不动。

用户进一步指出等宽陆侧廊道与海侧椭圆的组合过分规整。当前设计改为统一浅锥扇面：从保存河道在分流点附近的切线取得轴向；陆侧扇顶收窄，下游按半径与张角向海展开。径向缓坡决定上部陆地和水下前缘，小幅非对称边缘及低幅起伏调节形态。分汊从扇顶向不同前缘方向发散。扇面是明确的生成几何，不能据形状相似宣称由自然沉积涌现。

## 复用与后续边界

湖口与内陆复用的实际能力、缺口和测试见[湖泊连接与泥沙复用评估](lake-sediment-reuse-and-topology-review-20261016.md)。

## Second phase boundary: river capture and multi-domain terrain

River capture is deliberately deferred until the river-network layer can exchange water and sediment between distinct hydrological domains. That phase must first define shared outlet identities, divide and valley geometry, mass-conserving handoff, and rollback when a capture candidate fails. Valley overhangs, enclosed valleys, and underground channels belong to the same phase because they change the domain graph and require explicit surface/underground boundary contracts. They are not inferred from this delta result.

Terrain Diffusion work is a separate terrain-generation track. The next design step is a conditioning and post-processing comparison for four terrain families: inselberg/Uluru profiles, volcanic plugs such as Devils Tower, volcanic cones and calderas, and tundra low-relief/permafrost surfaces. Each family needs an explicit height-scale, slope, roughness, drainage, and material mask contract. The existing Terrain Diffusion output remains the base; any new procedural landform layer must be saved as a derived identity and tested for river, coastline, and cross-tile continuity before being used by hydrology.
