---
title: Terragenesis 河网工程总览
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 3
  maxWidth: 280
---

# Terragenesis 河网工程

## 阅读入口 · 2026-10-15

- 点击节点圆点展开／折叠，滚轮缩放，拖动平移
- 状态按限定证据标注，不代表整个系统已完成
- [任务总览](../TODO.md) · [对话移交](river-visual-overview-handoff-20261015.md)
- 当前顺序：二维完善 → 三维完善 → Minecraft 接入
- 本图为人工整理快照，更新源文档后需重新生成

## 地形来源与水文规划域

- Terrain Diffusion 基础地形【已使用】
  - TD 生成地形，河网由后续算法生成，并非训练得到的河流模型
  - [六份 TD 河网生成记录](td-terrain-generated-rivers-20261011.md)
- 水文规划域【有限样例验证】
  - 共享山脊两侧：海岸流域／内陆湖流域
  - 有限支持范围、冻结归属、12 个月季节水账
  - [设计](hydrological-planning-domain-design.md) · [实施进度](hydrological-planning-domain-progress.md)
  - 【待完善】全域覆盖、局部地形衔接与自然度
- 无限世界【长期目标】
  - 分区与生成都须有有限依赖
  - 【待验证】窗口外延续、加载顺序与跨窗口一致性

## 二维汇水与河网

- 降雨与季节变化【限定情景验证】
  - 重复 12 个月背景曲线＋短时强降雨
  - 季节河道虚线；暴雨不直接升级永久河网
  - [38.4 km TD 天气与径流报告](td-lowland-runoff-20261014.md)
- 汇流与主河【同源大图修复】
  - 支流共享下游，汇流保留水量贡献
  - [大图汇流结果](td-large-map-confluence-20261014.md)
  - 【已修复】粗标签造成的内部矩形截河
    - [原生汇水重规划](td-large-map-native-replan-20261014.md)
  - 【待完善】深洼终点、窗口外连接、栅格折角及长直路径
- 低地承接【首版验证】
  - 保留降雨水量，减少不必要的可见河道
  - 主河／支流／湿地／浅湖／季节沟槽／洪泛区
  - 按实际地形连通承接，各对象无类别优先级
  - [结果与限制](td-lowland-runoff-20261014.md)
- 湖泊与湖岸【局部验证】
  - 已有季节水账、局部混合湖与临界水位连接检查
  - 【待完善】完整流域湖岸、连续床面与共同水面衔接
  - [证据入口](hydrological-planning-domain-progress.md)

## 河槽与河口塑形

- 流量与材料控制宽深【首版验证】
  - 汇流增流；硬床软岸偏展宽，软床偏下切
  - 209 处汇流增流／204 处展宽／207 处加深
  - [38.4 km 可视预览](../verification/hydrological-planning-domain/large-td-channel-geometry-20261015-01/preview.html)
  - [断面与验收报告](td-discharge-rock-channel-geometry-20261015.md)
  - 【待完善】小于 30 m 格距的细河槽；切深不等于水深
- 连续河床【局部成果】
  - [六源河槽形态修复](td-river-shape-repair-20261013-final.md)
  - [同源地形保留与床面修复](td-hydrology-naturalness-improvement-20261014.md)
  - 【待完善】汇流折角、条带、谷侧偏位与完整连续性
- 河流主导三角洲【有限机制验证】
  - 沉积更新床面，下一阶段重新分配通路
  - [TD 河口预览](../verification/fluvial-delta/river-led-20261015-03/preview.html) · [报告](td-fluvial-delta-20261015.md)
  - TD 案例仍为水下沉积，新出露海洋格为 0
  - 合成浅水例：8 格出露，4 格连接原陆地
  - 覆盖层再侵蚀【5 m 局部验证，2026-10-15】
    - 只搬运已有沉积库存，床面不低于输入地形
    - TD 清水阶段最大净降床 0.8 m，连续凹槽门槛未通过
    - [局部床变预览](../verification/fluvial-delta/channel-remobilization-20261015-02/index.html) · [材料账与审查报告](td-fluvial-remobilization-20261015.md)
  - 原床切槽及近岸协调【有限样本验收，2026-10-15】
    - TD 30 m 主槽＋670/700 m 两支，连续 3 阶段真实几何及独立冷审通过
    - 准备材料单独计账；旧覆盖层连续槽 gate 仍 false
    - 326 格局部正增 4676.442 m³ 固体，海洋覆盖层整体净减 224.464 m³
    - [实际床面图集](../verification/fluvial-delta/distributary-20261015-01/index.html) · [预算与验收](td-fluvial-distributary-20261015.md)
  - 二维水沙形态演化【正式候选验收中，2026-10-15】
    - 独立接入pyDeltaRCM 2.3.0及保守扩散，仅给短入口，不预设下游双槽
    - v2在2048形态失败停止：海洋净床增500875.738 m³ bulk，实质最大连片77875 m²
    - 几何连陆150 m²、推进5 m、实际干出0、持续双支未过；新增前缘陡阶15.6 m/5 m
    - v3守恒松散层坡稳：6算子+9核心+21工具测试与两类短试独立冷审通过
    - v3正式2176保存并完成17批混合链冷审及主协调图审；新沉积坡差约2.887 m/5 m
    - 净增532261.557 m³ bulk、最大连片84500 m²；有向接海重审为100 m双支，替代旧105 m结论
    - 2560同初态0.1 m/0.01 m对照：连陆250/175 m²、岸进15/10 m，持续双支均false，整体验收未过
    - [实际成对图集](../verification/fluvial-delta/morphodynamics-20261015-03/comparison-2432-2560/index.html)：两组材料/坡稳通过；观察精确对照及16步诊断完成
    - v4接受2688：连陆1225 m²、岸进40.3113 m，持续双支false；旧2816材料失败保留
    - [v5实际2816图集](../verification/fluvial-delta/morphodynamics-20261015-04/index.html)：材料/坡稳通过，连陆1225 m²/岸进40.3113 m仍不足，末三帧双支false/false/true，持续false
    - [3072冻结图集及退化诊断](../verification/fluvial-delta/morphodynamics-20261015-04/accepted-3072-directed/index.html)：材料/原床/坡稳通过，连陆250 m²/岸进20 m、持续双支false；扩散冲断薄桥已核
    - [4096冻结图集](../verification/fluvial-delta/morphodynamics-20261015-04/accepted-4096-directed/index.html)：已正常退出，材料/原床/坡稳通过，连陆1100 m²/岸进40 m、持续双支false，整体形态未通过
    - 末批lost约19855 m³来自原生570跳预算耗尽；先做同父点单步570/1140与水路由诊断，不直接延长正式候选或改门槛
    - 保留v1/v2成功链及531越底失败，v3每128步检查、候选上限4096步；原forcing/门槛不变
    - [实际图集](../verification/fluvial-delta/morphodynamics-20261015-02/corrected-2176-directed/index.html) · [参数与材料报告](td-fluvial-morphodynamics-20261015.md)
  - 【待验收】连陆出露、岸线推进、持续真实分流及整体实际形态；近似稳态水场不等于精确水量认证
  - 【下一版，先讨论】潮汐及双向水沙交换
  - 【后续 TODO】波浪与沿岸输沙

## 三维完善 · 二维之后推进

- 地下暗河【已有局部原型】
  - [地下暗河 V1](underground-river-v1.md)
  - [地表／地下混合河网](hybrid-river-network.md)
  - 局部构造与几何成果，不等于完整地下水系或水力通过
- 洞口、潜入与复出【后续完善】
  - 域内连接优先
  - 自动选址、地质约束、多层洞道与连续水力
  - 跨域地下连接须严格条件，不能无限合并水文域
- 特殊三维地貌【研究候选】
  - VDM／体积表示、悬挑及洞穴
  - Nucleation 候选，与“河源萌生”概念分开
  - [参考资料采用记录](river-progress-and-reference-use-20261013.md)

## 验收、研究与交付

- 关键验收【持续执行】
  - 来源身份、边界和尺度一致
  - 同种子稳定、有限依赖、水沙收支与连续性
  - 同源图审、多种子对照，保留真实失败
  - 既有结果不是本次新运行；守恒通过不等于自然度通过
- 论文资料【参考用途】
  - Plate-Local：借鉴组织方式，不照搬板块模型
  - Tokunaga：拓扑评价尺子，不强制生成模板
  - [使用程度与边界](river-progress-and-reference-use-20261013.md)
- 论文发表【仅讨论】
  - 候选方向：有限依赖的虚构世界水文规划域
  - 创新性、对照实验与投稿目标尚未确定
- Minecraft 适配【后置】
  - 先成熟算法，再研究尺度映射与分块消费
  - 当前局部算法验收不等于 MC 世界生成验收
