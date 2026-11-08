# 复杂三角洲水网 v1（Terragenesis，P0 选址 + P1 程序化骨架 + P2 造地）

范围：只做形态验收图。不含水沙演化、守恒账本、存档冷读。

## 运行命令（工作目录：山川形意Terragenesis）

```
runtime/venv/Scripts/python.exe -B tools/run_delta_network_v1.py                      # 三组变体 + 全套图，约 1–2 分钟
runtime/venv/Scripts/python.exe -B tools/run_delta_network_v1.py --variants base --no-figs --out <目录>
runtime/venv/Scripts/python.exe -B -m pytest tests/test_delta_network_skeleton.py -q -p no:cacheprovider
```

产物目录：`.scratch/delta-network-v1-20261105/skeleton-v1/<variant>/`
（bed_dem_float64.npy、water_mask.npy、island_labels.npy、spit_mask.npy、channel_mask.npy、tidal_mask.npy、channel_graph.json[节点/边/局部与世界坐标/Q/宽/深/层级/叶瓣]、metrics.json、manifest.json、sha256sums.json；总表 sha256sums_all.json）。

## 图片

| 文件 | 内容 |
|---|---|
| 1_遥感配色平面图_*.png | 深水深蓝 / 中等水深 / 浅水浅蓝 / 沙洲·沙嘴·潮滩沙色 / 陆地绿；含 5 km 比例尺 |
| 2_汊道诊断图_*.png | 线宽∝√Q；颜色=所属叶瓣（红=最新最大，橙/绿/蓝依次变老，灰=主干）；★改道点 ●分汊 ■汇合 ◆横向连接汊起点 ▼入海口 |
| 3_床面DEM与横剖面_*.png | 灰度床面 DEM（−6 m 黑 → +3 m 白）；剖面 A 沿岸 u=10 km，剖面 B 沿最新叶瓣轴向海 |
| 4_参数种子对比.png | 基准 / 环少 / 环多 三组并排 |

## 来源与参数

- 选址：TD terrain-v3（4096²×30 m）东南向长直海岸，锚点世界约 (X 9283, Z −3005) m；局部坐标 u 向海、v 沿岸，α=45°；窗口 u∈[−4,44] km、v∈[−24,24] km，1600×1600 格，30 m。详见 `.scratch/delta-network-v1-20261105/site-selection.md`。
- 世界种子 20261020；子种子 = SHA256("20261020|用途名|变体名") 前 8 字节，numpy PCG64。用途：delta-network/lobes、relief、growth、terrain。
- 宽深：w=a·Q^b、h=c·Q^f，b=0.5、f=0.4（Leopold & Maddock 1953 指数，已核原文）；a=3.5、c=0.4 为**声明值**。
- 分汊间距 L_b=β·w，β=6（**据记忆 Edmonds & Slingerland 2007，未核原文**）；不对称比 0.5–0.8、偏转角范围、叶瓣份额比 0.55、r_decay 0.8 等均为**声明值**。
- 入口流量 Q=8000 m³/s 为声明情景。海侧陆架（起始水深 0.4 m，坡 1e-3）与三角洲前缘坡（2e-3）为声明值，替换 TD 的窄陆架。
- 转向规则：`river_path_geometry.turn_allowed(…,90)`；步进转角 ≤15°，汊口夹角用 `turn_penalty` 抽样，全图无 ≥90° 转折。
- 变体：base；few_loops（3 叶瓣、link_prob 0.08、max_level 4）；many_loops（link_prob 0.95、β=5、max_level 6）。

## 验收指标（基准）

入海口 18；层级 0–6；环数 E−V+C=13（环少 2，环多 11）；岛 48（≥0.05 km² 22 个，总面积 597 km²，其中含与陆地接壤的大块）；宽度–流量拟合指数 0.500；分汊夹角 均值 37°（P10 19.5°，P90 53.6°）；岸线长/直线长 3.17；顶点→最远岸线 36.0 km；沿岸宽度（u≥3 km）38.2 km；节点流量守恒误差 9.1e-13。两次独立运行 31 个产物文件 SHA256 全同。

## 已知限制

- 汊道最窄为 30 m 格的 1.5 格，更细的汊道在 DEM 上只是一条线；Q 小于阈值的支流不再分汊。
- 叶瓣轮廓由解析极坐标高斯瓣加噪声生成，外形偏圆润、规则，与参考图的沙嘴/多级岸线相比偏“光滑”。
- 沙洲主要来自汊道切割形成的岛；河口外沙嘴/水下扇按口门供沙份额堆出，未经沙输运演化。
- 老叶瓣的“潮沟 + 低平沙滩”是随机生成的纹理，未解潮汐。
- 窗口内 TD 陆地仅位于 u<0 的内陆带，海侧为声明陆架，因此海岸以外不代表 TD 真实水下地形。
- 入口附近 3 km 的 TD 陡坡与平原混合是人为过渡。
