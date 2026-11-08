# 三角洲水力输沙能力对比图（问题单 24 前两步）

图：`legacy-vs-hydraulic-capacity.png`（D:\codexwork\山川形意Terragenesis\验收图片\三角洲水力输沙能力-20261104\）

## 内容
同一真实 TD 100 m 局部例（`reference-case-v7/year-half-d/final`，同源冻结输入），同一初态，各跑一次 600 物理秒事件。左栏旧默认（capacity = Q×0.01×时长），右栏新规则（`HydraulicCapacityRule`，过剩剪应力能力 + 欠载才冲刷 + dt≤L/v 子步）。

- 上排：末态床面高程（terrain 色标，黑细线 = 海平面 0 m 等值线）；叠加河网，线宽和颜色（cool 色标）= 该边实际 Q（m³/s，全部主干 1500）；黄星 = 口门。
- 下排：相对初态床变 m。红 = 淤积，蓝 = 冲刷，白 = 近 0；对数色标，两栏同一标尺（±0.7 m，±2 mm 内线性）。
- 文字框：模拟时长、供沙量、淤积/冲刷合计、最大抬升/下切、是否触发新汊、入海沙量、账本残差。

## 参数
- 供沙 3.0 m³/s × 600 s = 1800 m³；海平面 0 m，无潮；marine step 300 s。
- 材料（declared/uncalibrated，取 `surface_rivers.metric_sediment.MaterialParameters` 默认）：τc = 1 Pa，k = 1e-5，沉积物易蚀性 1e-6 m/s/Pa，沉降速度 0.001 m/s；曼宁 n = 0.035（保存的水力参数）。
- 不改变改道判据（0.1 m），本例未登记动态候选，故“新汊”一栏为否（dynamic_not_enrolled），两栏相同。

## 复现命令（工作区根目录，PowerShell）
```
$env:PYTHONPATH = "$PWD;$PWD\tests"
runtime/venv/Scripts/python.exe -B .scratch/delta-reference-shapes-20261104/issue24-capacity/run_real_case.py --initial .scratch/delta-reference-shapes-20261104/reference-case-v7/year-half-d/final --output .scratch/delta-reference-shapes-20261104/issue24-capacity/real-a-600s
runtime/venv/Scripts/python.exe -B .scratch/delta-reference-shapes-20261104/issue24-capacity/make_figure.py --result .scratch/delta-reference-shapes-20261104/issue24-capacity/real-a-600s/result.json --output 验收图片/三角洲水力输沙能力-20261104/legacy-vs-hydraulic-capacity.png
```
图完全由 `result.json` 里保存的床面、河网边 Q 和床变数组绘制，没有手画。

## 限制
- 只是 600 s 短事件，不是年度或百年演化；右栏最大抬升仅 7 mm，远低于 0.1 m 改道阈值，不能据此说明新规则会长出新汊。
- 材料参数未标定；供沙 3 m³/s 是固定情景，不是实测上游包。
- 旧默认下的床面冲刷（约 28 万 m³）是旧能力公式的人为结果，图中保留只为对照。
- 口门外（海侧）未出现淤积；落淤发生在河道内的入口附近和若干减速点。
