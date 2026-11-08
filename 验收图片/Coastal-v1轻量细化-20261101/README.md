# 按用户参考图轻量细化Coastal v1

同一旧保存TD、同一64.08km范围、固定种子20261020，30m计算；全图60m显示、局部30m显示。保留参考图的山脉、平原、主要湾岬和6个可解析岛屿，仅从TD源恢复少量被压制的近岸细节，不叠独立噪波。

![参考图与轻量细化](comparison-64km.png)

- [细化全图](overview.png)
- [北部细节](north-detail.png)
- [中部细节](central-detail.png)
- [实际床变，固定±6m色阶](bed-change.png)

1.32%格点发生非零变化，变化格点绝对床变中位约4.6cm；海转陆0.2016km²、陆转海0.3960km²。岸线双向最近格距离中位0m、P95 30m、最大161.55m。三个独立子窗重算误差均0，原始输入未改。

这是静态地形细节恢复，不是波浪或沉积演化。图片是高程配色的遥感式合成影像，不代表真实植被/雪冰/材料；紫色为封闭低洼，不是已模拟湖泊。来源是用户选定的旧Coastal v1，不能冒充新板块条件TD的形态验收。

产品身份 `4e04df7f98e8801dcacfba0b1bac842da74d7277aa412358b595ed14f47f8c97`。逐图来源与SHA256见 `manifest.json`；完整[主端验收](../../.scratch/coastal-v1-refine-20261101/main-review.md)和[交接阅读](../../.scratch/coastal-v1-refine-20261101/handoff-reading.md)。
