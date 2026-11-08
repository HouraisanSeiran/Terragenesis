# 四口三角洲：转向约束与三组局部分合

600秒末态：[主图](main.png) · [32 km同源对照](source-comparison.png) · [实际湿槽局部](delta-detail.png) · [实际边流量](actual-flow.png) · [床面与水深](bed-and-depth.png) · [转角惩罚曲线](turn-penalty.png)。

转角以真实XZ入流→出流方向计算：45°以内无惩罚，45°后惩罚持续增大，至90°采用k(θ−45)/(90−θ)，默认k=1，90°及以上禁止。最终全网171条物理边、173组接续转角中，最大87.404°，≥90°为0处；全部真实边流量为正。旧基线两处急转已修复，旧河网第三处分叉提前一个站位；具体局部修复登记见构造清单。

三组新增分合围住既有沉积平原，保留四个原海口；这是显式构造，不称动态新生沙洲。地质5等效年／700扫掠与其后600秒正常事件分开记录。图中灰色为未知／无效数据，白线为构造前岸线；原生约30 m TD采样至100 m计算中心。河宽按保存断面与占地显示，无加粗；8倍显示细分不提高物理精度。

本包只读重绘。来源、检查点及图片摘要见manifest.json和render-manifest.json；本轮22项独立验收见independent-angle-acceptance.json，全网角度复查见turn-angle-review.json。报告入口：[本轮角度验收](../../.scratch/delta-braided-acceptance-20261104/angle-acceptance.md)。旧包保持冻结。
