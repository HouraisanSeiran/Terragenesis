# 板块海洋岛屿与岛链

## 当前版本：v3（2026-11-07）

当前正式岛产品为 `ocean-islands-metric-detail-smooth-seabed-v3`，身份 `cc04a382d6636effd9ce8294a2a6f16f57ca4d0929d30c38c16a52be292f60f6`。
小岛不强制谷切；轮廓与露海细节采用米制多尺度噪波，海底重叠底座使用有界平滑拼接。

![相同位置的噪波与拼接对照](v3-primary-review/islands_noise_and_joins.png)

![10m采样的表面细节对照](v3-primary-review/surface_detail_10m.png)

[正式全域对照](run-metric-v3-2km/world_comparison.png) · [热点链](run-metric-v3-2km/representative_chain_comparison.png) · [世界16位灰度](run-metric-v3-2km/world_elevation16.png) · [50m环礁](atoll-focus-v3-50m/atoll_focus_comparison.png) · [主端逐值审计与图源](v3-primary-review/image_binding.json)

正式800×800@2km、各类型局部及代表链的全部查询字段与冻结产品逐值相等；50m环礁同源冷读通过。2km格距不能解析80m细节，细图是同连续算法的更密采样，不是新增地质模拟。
大型岛TD入口按真实露海面积与内陆宽度判资格；当前真实来源无合格岛，没有TD推理成果图。

织梦实际v3世界已经生成并通过加强审计：[保存世界总览](dream-v3-saved/world_saved_elevation.png) · [同坐标热点链](dream-v3-saved/hotspot_same_coordinates_saved_elevation.png) · [最终世界16位灰度](dream-v3-saved/world_height16.png) · [来源绑定及灰度映射](dream-v3-saved/image_binding.json)。图像直接读取保存数组，2km格距，配色仅表示高程；包含织梦自身山系/侵蚀，与独立岛产品分别报告，没有TD推理或补造细节。

## 历史v1/v2对照（保留原图）

本图集来自已保存的算法高程。共用种子20260903；主世界为1600×1600km板块骨架上的2km产品。
示例配置：群岛型、高密度、热点数量上限25、明示暖水环礁。颜色表示高程与海底地形，不表示真实植被覆盖。

[算法调用说明](../../docs/ocean-islands.md) · [主端审查与性能](../../.scratch/ocean-islands-20261106/review.md) · [主世界文件及来源清单](../../.scratch/ocean-islands-20261106/run-main-2km/delivery_manifest.json)

## 主世界与热点链

左为原始板块基底，右为合成后的同坐标地表。新增岛体、浅滩和海山不由图像绘制生成。

![原始基底与岛链](run-main-2km/world_comparison.png)

![热点链](run-main-2km/representative_chain_comparison.png)

![沿板块运动方向的岛链剖面](run-main-2km/representative_chain_section.png)

主清册46个地貌要素，包含热点、海山、岛弧、张裂脊台和环礁；不等于46座陆岛。
直接数值、16位灰度及浮点床面位于[主数据目录](../../.scratch/ocean-islands-20261106/run-main-2km)。
主图格距2km，局部图约171–216m或500m，原始板块格距10km；局部细采样没有新增地质过程。

## 环礁近景

同一主世界冻结产品的50m直接采样。低矮环缘和潟湖保留，部分环缘随适宜性淡出而破碎。
位置按第一个环礁ID固定选取，未重新挑选种子或另造环礁。

![同一环礁的50m近景](atoll-focus-50m/atoll_focus_comparison.png)

[近景来源及采样清单](atoll-focus-50m/image_binding.json) · [灰度图](atoll-focus-50m/atoll_focus_elevation16.png)

## 岛弧参考：独立旧来源

以下属于另一份旧冻结板块来源，来源种子20261020、岛屿算法种子20260903；不属于上方主世界。
500m局部包含同一板块对的三座露海岛弧，位置和上盘侧有记录；两条相邻中心剖面保留水下海峡。

![旧来源的岛弧局部](arc-reference-legacy/arc_window_comparison.png)

[岛弧位置诊断](arc-reference-legacy/arc_positions_diagnostic.png) · [海峡剖面](arc-reference-legacy/arc_strait_sections.png) · [独立来源清单](arc-reference-legacy/image_binding.json)

主世界64万格、50m环礁255025格及旧来源岛弧198500格均已核对冻结冷读。
本图集覆盖实际保存的CPU几何窗口；未验证TD模型响应、完整无限板块来源、河网或织梦生产接线。
