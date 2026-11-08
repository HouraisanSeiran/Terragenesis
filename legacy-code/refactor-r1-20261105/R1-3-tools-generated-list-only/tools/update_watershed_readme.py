from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = root / 'README.md'
s = p.read_text(encoding='utf-8')
if '## 当前测试版 0.7.0' in s:
    raise SystemExit('Already migrated; edit README.md directly.')
start, end = s.index('## 当前测试版'), s.index('## 模块')
(root / 'research/history/README-pre-watershed-0.6.0.md').write_text(s[start:end], encoding='utf-8')
new = '''## 当前测试版 0.7.0

Minecraft Java 26.3 / Fabric 0.19.5+，Java 25。安装包：build/libs/RemoteMountains-26.3-0.7.0.jar。只在新建世界时选择的自定义预设中生效；旧存档保持其生成器。安装时同一实例只保留一个 RemoteMountains JAR，并安装对应 Fabric API。

| 世界类型 | 用途 | 模型服务 |
|---|---|---|
| 长垣 · 山海流域（独立演示） | 山区源流 → 支流汇合 → 河谷与侵蚀岩壁 → 入海口 | 无需启动，使用内置扩散样片细节 |
| 长垣 · 地貌世界（有限演示） | 平原孤山、裂谷、喀斯特、石柱及三种岩壁展示 | 无需启动 |
| 长垣 · 全域地貌世界 | 全域实时 Terrain Diffusion 和区域岩壁 | 先运行 start-diffusion.ps1 |

新世界 Y=-64..1023（上边界 1024），海平面 Y=62。内部地形坐标横向放大3倍，海平面以上起伏放大3倍；海底仅平移。网格缩放后体素化，洞穴和岩层按逆变换采样。树木等装饰保持游戏尺度；高海拔矿物、生存平衡尚未专门调整。

## 体验独立山海流域

新建创造世界，种子使用 **20260927**，开启命令，世界类型选择 **长垣 · 山海流域（独立演示）**。专用服务器设置 `level-type=remotemountains:watershed`。主河从西侧山地向东流，到世界 X≈4800 入海，全程约4800格；下界和末地维持原版。

先飞到高处再下降查看：

| 样点 | 命令 |
|---|---|
| 山区及三处源流 | `/tp @s 0 850 0` |
| 两侧主支流汇入主河 | `/tp @s 1920 550 60` |
| VDM侵蚀岩壁附近 | `/tp @s 2700 500 228` |
| 入海口 | `/tp @s 4800 150 20` |

图示：[算法采样预览](preview/watershed/map.png)，不是游戏截图。最终验证记录见 IMPLEMENTATION_STATUS.md。

演示宏观坡降和支流布局由统一河网约束，Terrain Diffusion 内置样片提供细节，Perlin 山脊提供额外变化。它不是新训练的河网条件扩散模型。随后转为 XYZ VDM，并对局部河谷岩壁进行 Voronoi 节理、贴壁流水和侧蚀。

岩壁分配上游流量的2%，求解192步后将平均出水和泥沙回传下游。流域和局部账本都有守恒检查；一演示步记为60秒，但降雨参数未经过真实流域标定，3倍视觉放大不表示Minecraft方块空间也满足物理米制守恒。当前河床形态主要由河网宽度和坡降控制，泥沙通量尚未进一步塑造下游沙洲或三角洲。

## 旧有限地貌展示

新建世界选择“长垣 · 地貌世界（有限演示）”，范围 X/Z=-768..2304。先开启创造飞行：

| 地貌/样点 | 命令 |
|---|---|
| 孤山 | `/tp @s 0 850 0` |
| 裂谷与90°垂直岩壁 | `/tp @s 1536 850 0` |
| 喀斯特与68°悬挑岩壁 | `/tp @s 0 850 1536` |
| 石柱群 | `/tp @s 1536 850 1536` |
| 76°斜壁 | `/tp @s 768 850 768` |

此前安装实例实际加载0.3.0，故没有后来增加的两处岩壁。诊断见 verification/installation-20260927-latest/诊断说明.md。本轮产物都在工作区，没有修改外部游戏安装。

## 全域地貌与限制

全域预设需要真实模型服务在线，不能使用时会报错，不自动降级到演示。全域跨区域流域连接尚未接入；本轮流域只在独立山海预设中实现。相邻实时模型瓦片存在约0.04内部方块的边缘误差，详见 verification/presets-global/tile-edges.json。

洞穴使用独立三维密度处理；VDM本身不负责产生任意拓扑孔洞。崩塌、落石、任意复杂面片自交修复，以及客户端画面确认仍待完成。历史版本坐标与说明归档至 research/history/README-pre-watershed-0.6.0.md。

'''
p.write_text(s[:start] + new + s[end:], encoding='utf-8')
