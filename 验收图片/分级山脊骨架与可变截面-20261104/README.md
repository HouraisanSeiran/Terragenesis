# 分级山脊骨架与可变截面

2026-11-04，世界种子 **20260903**。本目录图片均来自实际算法采样，没有AI生成位图或手绘输入。新来源 `skeleton-mountains-v2-ribbons-on-relief`，旧同窗对照 `local-volume-mountains-v1`。[主端验收与限制](../../.scratch/mountain-skeleton/review.md) · [算法及支持上界](../../.scratch/mountain-skeleton/algorithm.md)。

本轮已有宽肩/窄脊/不对称侧坡的控制能力，**自然山脉仍未通过**：三向分叉与带状侧壁偏规则，部分脊线细线残留，未接真实河网或冰川。主窗和负窗的mixed均由固定种子选中granite，主窗mixed与granite相同，不是第四种不同山形。

## 先看这些图

- [灰度六组比较](main_gray_comparison.png)：旧对照、纯骨架、granite、alpine、asymmetric、mixed。
- [关闭噪波与雕刻的主峰局部](main_peak_macro_views.png)：同一骨架、同一低幅背景，检查截面是否真正改变山体，而不是只改变沟纹。
- [同尺度阴影](main_hillshade_comparison.png) · [两方向无材质几何](main_bare_views.png) · [真实主峰/峰肩剖面](main_peak_sections.png)。
- [主峰/主支脊叠图](main_skeleton_overlay.png) · [负窗](negative_hillshade_comparison.png)。彩色线是生成骨架，不是河流。

![灰度六组比较](main_gray_comparison.png)

## 可直接使用的高度图

| 形态 | 16位原始灰度 | 8位快速预览 |
| --- | --- | --- |
| 宽肩陡壁 | [granite](main_granite_height_m.png) | [预览](main_granite_height_m_preview.png) |
| 尖峰窄脊 | [alpine](main_alpine_height_m.png) | [预览](main_alpine_height_m_preview.png) |
| 不对称侧坡 | [asymmetric](main_asymmetric_height_m.png) | [预览](main_asymmetric_height_m_preview.png) |
| 当前种子混合配置 | [mixed](main_mixed_height_m.png) | [预览](main_mixed_height_m_preview.png) |
| 负坐标混合 | [negative](negative_mixed_height_m.png) | [预览](negative_mixed_height_m_preview.png) |

401×401、间距60米；主窗原点(0,0)m，负窗(-24000,-24000)m，各覆盖24×24km。行Z向南、列X向东，高程米制。16位单通道、黑低白高，统一固定 **−500至6000米**：编码 `round(clip((h+500)/6500,0,1)*65535)`，解码 `h=-500+code*6500/65535`。没有逐图拉伸，没有阴影烘焙进高程；14幅高度图无饱和，最大量化误差≤0.049593米。8位预览仅便于查看。

浮点原数组和全部阶段字段在[正式run03](../../.scratch/mountain-skeleton/run-20261104-03/)，每组NPZ为float64；图库仅复制PNG/JSON/精确剖面，未重复存放大型地形NPZ。[manifest](manifest.json)登记配置、子种子、源码/数组/图片SHA、源支持、导出和性能；[剖面数组](sections.npz)由精确世界位置采样，不是图像读数。

裸山全景为180m显示采样、主峰局部120m，均垂直夸张1.00倍；高度PNG及NPZ仍为60m原采样。Advanced仅是外观雕刻，不表示水沙守恒、风化史或真实冰川演算。源内支脊连接不等同源间整条山系已连通。

重新生成到新目录：

```powershell
runtime/venv/Scripts/python.exe tools/prepare_skeleton_mountains.py .scratch/mountain-skeleton/<新目录> --size 401 --spacing 60 --benchmark
```

65项相关检查通过，512²60m近/远生成10.662/9.892秒，RSS峰约183/206MiB；机器与测量限制见验收记录。此轮Terra服务503后，经用户授权由主端实现并审查。
