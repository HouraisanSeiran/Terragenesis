已完成潮相、口门延伸和逐步断面同步，并生成 `full-final-initial/formed/event1/event2` 检查点。主端的独立冷读验收 **全部通过**，包括来源、库存、几何、湿路、时钟和水沙预算检查。

五年案例使用 `1e-5 m/s` 海洋沉降速度、0.3 m 潮振幅和四个等权潮相。主口门延伸 8 次；五年末平均海位评估触发真实候选，切除约 **72.2 m³** 现有沉积，新支路初始流量约 **7.5 m³/s**。两个带潮浪的 25 小时事件均有水沙交付，输水分别约 **374 万**和 **150 万 m³**；受端口水头限制，其余输入保留为待交付量。

- [结果说明](</D:/codexwork/山川形意Terragenesis/.scratch/coast-marine-reorganization-20261102/full-final-result.md>)
- [独立冷读验收](</D:/codexwork/山川形意Terragenesis/.scratch/coast-marine-reorganization-20261102/full-final-accept.json>)
- [参数与库存报告](</D:/codexwork/山川形意Terragenesis/.scratch/coast-marine-reorganization-20261102/full-final-report.json>)

演化测试 **13 项通过**。事件求解仍出现有界比值计算的中间除法溢出警告；保存库存均有限，守恒和冷读检查通过。最终检查点采用五年末单独执行平均海位候选评估的过程；代码现已将该评估接入每个形态步末，因此从初始状态重跑可能更早激活支路，不能保证逐位复现这组检查点。