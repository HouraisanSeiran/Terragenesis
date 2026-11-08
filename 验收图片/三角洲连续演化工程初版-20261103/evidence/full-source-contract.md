# 100 m 同源窗口契约

当前正式来源为 `.scratch/coast-marine-reorganization-20261102/window100-v2/`；演化消费者必须读取该目录并核对其 manifest 的 source_identity 和文件哈希。`window100/` 是保留的历史初版，存在地质修正抬干海域的缺陷，不用于后续演化。

当前正式manifest/state身份为778970b3c367bc5896e86e69b6eb17b30998482da96cd05d9d5ed7be796beb19，source/state哈希c95f3bc.../8e6aa151...，主端独立检查通过。旧任务和早期报告中的36198...属于full-source-v2-initial历史版本，引用已更正；不要切换到历史版本或全仓查找替换当前产品。

`source.npz` 包含 `source_bed_m`, `derived_base_bed_m`, `valid_mask`, `source_ocean`, `unknown_wet`, `ocean_seed_mask`, `origin_xz_m`, `spacing_m`；数组为 [z,x]，450×450，格心原点 (-19950,-19950) m，间距 100 m。`state.npz` 使用 `coastal_marine_sediment.load_state` 读取；其 source_identity 与 manifest 一致。`manifest.json` 记录来源、参数、哈希、迁移账及限制。

原始地形来自 source-case300 清单中固定 owner 的真实 30 m TD；600 m base_change 是粗尺度地质背景。仅对 source_ocean 应用背景：负修正原样保留，正修正在接近源水深时平滑受限，至少保留 10% 原水深；参数绑定身份。源陆地和未知保持原 TD 地形。source_ocean 基底保持负高程；迁移后的有限沉积仍可改变 state.bed_m，这与地质背景本身区分。海洋以父域海洋证据约束窗口边界种子，再作四邻连通；未知不视为海。

旧库存按单元实际面积重叠迁移；裁剪外留在历史账，不是本次出口。陆地冲突在原位显式保留于 stranded 库存，不重造海底。历史时间、输入和已消费身份沿用；历史 packet 的 row/col 属于 600 m 网格，不得作为 100 m 坐标重放。100 m 后续演化另记账。此窗口没有与 600 m 域建立通量嵌套耦合。固定世界种子 20261020。

主端演化早期审查见 [full-evolution-feedback.md](full-evolution-feedback.md)；实际长案例前请处理其中有限侧向水量和不同水头可达路径两项，避免长跑后返工。来源初审见 [main-full-source-review.md](main-full-source-review.md)；修订证据见 [full-source-v2-result.md](full-source-v2-result.md)。

主端已派来源Terra继续独立实现coastal_delta_routes.py及full-routes-contract.md，接旧细河槽到真实100m外海的水头/断面/谷线。演化代理继续闭环代码和小测试，之后按full-routes-contract接入；不要把旧port断连诊断或全部水沙待交付作为完整演化交付。
