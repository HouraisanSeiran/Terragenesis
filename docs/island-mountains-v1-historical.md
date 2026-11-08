# 大型岛屿的显式 Terrain Diffusion 山系计划

`terrain_pipeline.island_mountains` 负责CPU资格分析、冻结计划、连续内陆权重与派生高程组合。它不导入torch、不启动模型；织梦通过独立工具显式调度现有local30默认TD链。无计划时默认世界路径不变。

首版以源域原点固定1km格分析实际露海4邻连通体，不按feature水下半径判断大小。默认露海面积至少2000km²；距岸3km缓冲后的同一连续内陆组件，保守最大内接圆直径至少20km。该直径表示可容纳山系的腹地，不是整岛精确短轴。面积与距离均为栅格近似，岸距和内接半径扣除一个格对角线余量；亚格海峡/陆桥仍可能漏辨。接原大陆、碰有限域边界、接登记潟湖环缘的组件排除，多个feature融合成一岛按同一组件统计。分析超过固定预算明确拒绝，不按查询窗口改变资格。

```powershell
python tools/prepare_island_mountains.py --islands <islands.npz> --expected-island-identity <岛身份> --out <新plan.npz>
```

阈值可通过对应参数显式设置并进入身份。plan保存源/岛身份、算法、配置、固定格、每组件面积/腹地直径/排除理由、选中内陆标签、保守岸距和内陆边缘距离，数组SHA入身份。保存拒绝覆盖，加载检查身份/数组/源范围；内存清册按值返回，数组的bytes backing不能重新开启写入。该模块不写岛原产品。

公共接口：`analyze_island_mountains(product,config)`、`save_mountain_plan(plan,path)`、`load_mountain_plan(path,expected_identity,product)`、`sample_mountain_weights(plan,product,x_m,z_m)`、`blend_mountain_surface(plan,product,x_m,z_m,decoded)`。查询只采冻结plan；岸距与内陆边界分别以smoothstep淡入后双线性插值，再用同产品真实海/潟湖/原陆判定限制为0。权重与查询窗口、顺序无关；不重新分析或生成。

派生场在同一绝对坐标使用 `base + weight * (max(decoded,land_floor) - base)`；默认land_floor=2m，只作用于派生target，原始TD高程不修改。base是同一冻结岛产品解析高程，不是30m实测地形，也不冒称独立fast世界层含旧山系/侵蚀的最终场。

织梦显式入口：

```powershell
python tools/prepare_island_mountains.py --skeleton <原骨架.npz> --island-product-path <同islands.npz> --expected-island-identity <同岛身份> --plan <plan.npz> --expected-plan-identity <计划身份> --out-root <新任务根目录> --reason <明确理由> --skeleton-run <同骨架run.json> --dry-run
```

去掉dry-run才可能启动模型；空plan在任何GPU、worker或内存门槛调用之前直接返回。非空时只调度选中内陆覆盖且完全位于有限源内的tile；`--tile ix iz`可重复选择该集合子集。一个任务惰性创建并复用一个已有local30生成器；不创建另一模型服务，不降低现有门槛。缺页调用现有`local30.prepare_tile -> _default_generator -> WorldPipeline`，已冻结raw可复用。

raw位于`<out-root>/raw/<island_identity>/local30/<tile>/`，派生位于`<out-root>/derived/<plan_identity>/local30/<tile>/`。派生绑定raw identity/高程SHA、plan identity/文件SHA、岛/源身份、基底和混合政策、模块SHA；混合后复核raw文件未变。换/移除plan或换政策时旧派生tile为stale；默认真实TD任务拒绝复用CPU注入的raw。只读local30查询不会触发准备。

CPU测试覆盖固定资格、海峡分离、环礁/小岛/大陆/触边排除、查询预算分批、plan不变性、连续性、同坐标分窗、实际CLI、空plan无GPU、单生成器复用、邻tile边一致、raw不变与stale。解析大岛/CPU注入器仅证明机制，不能作为真实TD模型地貌验收。真实世界按原大小判定；若无合格岛，记录空计划，不放大岛或降低阈值凑图。
