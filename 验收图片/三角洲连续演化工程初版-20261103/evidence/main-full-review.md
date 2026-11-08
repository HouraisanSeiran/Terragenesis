# 完整三角洲演化：主端验收记录

Status: resolved

本轮用户要求完成完整演化工程。验收以可重复的游戏用途流水线为准，主要地貌和水沙关系合理，不要求科研二维水动力、所有次汊常年活动或百公里案例。

## 验收内容

- 100m窗口确实读取同源30mTD，历史600m地质背景/库存迁移独立标注；有限库存区域内+裁剪外守恒，未知输入保持，原始来源不覆盖。
- 真实细河槽断面与端口接入，实际Q/水面/深度与分叉守恒对应，Q150等情景不冒充世界真实实测来水。河宽不等于网格宽。
- 水沙从上游经河道至各口及海洋，允许有限漫滩/回流/暂存，外输与未决都有账；开挖未知归宿和河流供沙不混用。
- 保存床面出现可量化的漫滩/分汊间沉积；岸顶和实际水头约束成立，新增平原/岛洲按同海位、同源初态比较。没有预画楔形、圆形平台或独立噪声造形。
- 淤积、冲刷与宽深/阻力反馈分流，新分叉或改道有实际几何/有限物源；弱汊可关闭或恢复，局部分流不牵动无关分组。
- 至少两个连续物理事件，周期潮浪与河流用同一床面、同址库存，时间和等效年分账；保存重载可继续，唯一输入不重放。
- 清晰可调用的准备/推进/保存入口与同源图集，主端冷读实际数组并查看图，运行受影响的小测试，不重复无关全域回放。

## 当前记录

两个Terra任务已接受固定来源契约。100m窗口source/state/manifest路径见full-source-contract.md；演化接口设计见full-evolution-design.md。当前处于实现阶段，不能据此宣布完整目标完成。

## 来源和水力独立验收补充

window100-v2修订已通过main-full-source-accept.json：source/state摘要和正式identity一致，原海洋地质基底非负格0，非海洋基底与原TD精确相等，库存迁移残差-1.19e-7m³，历史未知records/物理时钟保留。主端5项来源测试通过。该结论替代初稿来源失败，不覆盖初稿证据。

主端又通过6项routes测试、独立main-full-routes-accept.json和10项水力测试、main-full-hydraulics-accept.json。三者只证明来源、几何所有权和静态真实水力接线；07/08仍等待年度有限河漫滩/断面反馈、实际分汊、多年潮浪和续算图，不能因此标整体完成。

## 口门延伸独立真实诊断

main-full-mouth-probe-before为正式778970来源一年正常LongtermConfig沉降1e-5情景，旧口门失去独立外海面。主端检查最近真实外海距旧口门2601.9m，默认radius2000m无可行路符合约束。以明确radius4000m调用已验extend_mouths，0.625秒内成功延伸26个100m节点，无新增挖方/供沙，实际水力试算通水。完整结果main-full-mouth-probe-radius4km.json。正式集成应在较小年内形态步追踪岸线，或用显式有限4km搜索，不能将2km搜索失败误报成整个物理系统无法进积。

主端回归：D:/anaconda/python.exe -m pytest tests/test_coastal_delta_evolution.py tests/test_coastal_delta_hydraulics.py tests/test_coastal_delta_branching.py tests/test_coastal_marine_sediment.py tests/test_coastal_delta_plain.py tests/test_coastal_marine_longterm.py -q，64 passed，25.99s。覆盖本轮实际床宽输沙、统计潮相、统一node几何和旧默认兼容。只剩pytest插件弃用警告，不为此扩大修改。

## 最终主端验收（2026-11-03）

来源5、routes6、组合64、avulsion8共83个不同测试通过；最终平均海位评估接线后演化+avulsion21项复测通过，9.03s。main-full-evolution-accept.json和main-full-active-continuation-probe.json均pass=true。主端已看01全域、01b同址初末及床变、02实际河口、03床变/断面；确认新汊实际通水和事件后仍活动，同时记录D4长直/直角局限，不判自然成熟形态。

本验收resolved指有限窗口工程闭环；交付、时序版本差异、库存贡献、容量缺口与无限世界未测项见[main-full-delivery.md](../工程验收与接口.md)。05额外稳定/多汊形态仍开放，09已记录具体范围。图集与四组正式存档发布到根验收图片/三角洲连续演化工程初版-20261103，未覆盖历史成果。
