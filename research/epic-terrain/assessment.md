# Epic-Terrain density-function assessment

Source snapshot: wonderfulaichen/Epic-Terrain commit `08507bd3d606ad440b40a5fa726e0098d7309347` (MIT). Examined its README and 1.20.5-1.21.4 datapack JSON. The upstream snapshot is preserved in `snapshot/`.

## 中文结论

这个项目的可借鉴点是“先用大陆性等低频场确定大区域，再用多层 spline 映射山脊和侵蚀噪声”，并在特定数值范围用 `range_choice` 切换局部规则。spline 节点的 `derivative` 指定曲线在该节点的斜率，有助于控制过渡形状；仅凭 JSON 结构不能断言最终地形必然平滑，仍需做边界连续性和游戏画面验证。这里的 `erosion` 是噪声控制量，不是水流搬运、沉积等物理侵蚀模拟。`blend_density` 是 Minecraft 内建的新旧地形混合算子，不能当作该项目自定义区域拼接技术。该数据包面向 1.20.5-1.21.4，不能直接用于本项目的 26.3；若借用具体实现或文件，MIT 许可要求保留版权及许可声明。

## Observed mechanism

- The README describes continents, alpine peaks, eroded-looking coasts, and rivers. This is a Minecraft datapack; the version table marks 1.20.5-1.21.4 as v0.1.4 Beta.
- `etn:overworld/continents/1` is shifted 2D `etn:continentalness` noise with a -0.2 offset. `etn:overworld/continents/c` maps this coordinate through nested `minecraft:spline` curves, taking ridge and erosion fields as secondary coordinates. This yields smooth height transitions.
- `etn:excessive_biomes/continents1` uses `minecraft:range_choice` on the continent field (-0.16 to 1) to add continentalness noise within that interval. `etn:excessive_biomes/erosion1` branches on the continent field (-1 to 0.6), combining `minecraft:erosion1` noise with the continent field.
- Ridge fields use sampled noise and splines (`etn:overworld/ridge/r`, `ridge/1`, `ridge/2`). The main overworld density also uses `range_choice` on ridges and depth for cave placement. The plains, hills, and mountains result from continuous fields and curves; the inspected files do not define named plain/hill/mountain algorithms.
- `continents/c2` wraps a nested spline in `minecraft:blend_density`. That built-in operator relates to Minecraft's old/new terrain blending; its name alone is not evidence of a custom seam-free region algorithm. The continuous mapping evidence is the spline coordinates, ordered points, and derivatives.
- Files named `erosion` compose `shifted_noise`, `abs`, `half_negative`, multiplication, caching, and range choices. They do not implement hydraulic or thermal transport, sediment deposition, or iterative erosion. Here erosion is a density control field that shapes eroded-looking terrain.

## Ideas relevant to Terragenesis

1. Use a low-frequency region control field for broad provinces, then smooth response curves to blend landform generators at borders. Save the field and parameter version in the region recipe.
2. Reserve discrete switches for feature families whose geometry truly differs, and use smooth transition widths for the height field to avoid seams.
3. Keep physical erosion as a distinct optional stage. Epic-Terrain's erosion noise is useful for morphology but is not a physical erosion model.
4. Validate plains, hills, mountains, and transition bands by sampling elevation and slope histograms plus boundary continuity, then inspect output in-game.

## Permanent upstream evidence

- README: https://github.com/wonderfulaichen/Epic-Terrain/blob/08507bd3d606ad440b40a5fa726e0098d7309347/README.md
- MIT license: https://github.com/wonderfulaichen/Epic-Terrain/blob/08507bd3d606ad440b40a5fa726e0098d7309347/LICENSE
- Continent base noise: https://github.com/wonderfulaichen/Epic-Terrain/blob/08507bd3d606ad440b40a5fa726e0098d7309347/versions/1.20.5-1.21.4/data/etn/worldgen/density_function/overworld/continents/1.json
- Nested continent/ridge/erosion spline: https://github.com/wonderfulaichen/Epic-Terrain/blob/08507bd3d606ad440b40a5fa726e0098d7309347/versions/1.20.5-1.21.4/data/etn/worldgen/density_function/overworld/continents/c.json
- Continent range choice: https://github.com/wonderfulaichen/Epic-Terrain/blob/08507bd3d606ad440b40a5fa726e0098d7309347/versions/1.20.5-1.21.4/data/etn/worldgen/density_function/excessive_biomes/continents1.json
- Erosion range choice: https://github.com/wonderfulaichen/Epic-Terrain/blob/08507bd3d606ad440b40a5fa726e0098d7309347/versions/1.20.5-1.21.4/data/etn/worldgen/density_function/excessive_biomes/erosion1.json
- Erosion noise and arithmetic: https://github.com/wonderfulaichen/Epic-Terrain/blob/08507bd3d606ad440b40a5fa726e0098d7309347/versions/1.20.5-1.21.4/data/etn/worldgen/density_function/overworld/erosion/a/1.json and https://github.com/wonderfulaichen/Epic-Terrain/blob/08507bd3d606ad440b40a5fa726e0098d7309347/versions/1.20.5-1.21.4/data/etn/worldgen/density_function/overworld/erosion/e/e.json
- Ridge spline: https://github.com/wonderfulaichen/Epic-Terrain/blob/08507bd3d606ad440b40a5fa726e0098d7309347/versions/1.20.5-1.21.4/data/etn/worldgen/density_function/overworld/ridge/r.json
- Main density range choices: https://github.com/wonderfulaichen/Epic-Terrain/blob/08507bd3d606ad440b40a5fa726e0098d7309347/versions/1.20.5-1.21.4/data/minecraft/worldgen/density_function/overworld.json
