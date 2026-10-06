# 大规模静态河网验证 v1

本写集独立于 `surface_network_tiles`、`surface_domain_mosaic` 和
`surface_network_prepare` 的旧产物。既有模块提供了分块存储、拼接和只读
契约；本验证器在全局坐标上先生成确定性高度，再生成全格静态 receiver，
最后以 tile 摘要验证覆盖和跨 tile 拓扑，不改既有交付物或正式前端。

## 接口与边界

入口是 `build_large_surface_network(size, seed, tile_cells)`，默认 1024×1024、
128-cell tile、8 邻域。高度由一个固定的全局函数生成，所以 tile 边界来自同一
函数而不是独立 tile 拼接。当前实现验证 synthetic Terrain Diffusion 风格基准，
不把它认证为真实 TD 输出；真实 4×4 窗口可在后续以同一数组契约接入。

全局 cell ID 为 `row * size + column`。每个 cell 恰好属于一个 tile，receiver
只引用全局 ID。南边界标记 `natural_outlet`，其余工程开放边界标记
`engineering_outlet`，内部无下降邻居标记 `internal_terminal`；工程出口不是
天然海口认证。河线是面积阈值后的静态 channel 诊断，不代表已实现水动力或动态
流向。`dynamic_status` 固定为 `not_computed`。

## 预算与证据

预检在分配高度和图数组之前执行。默认 1024² 估算工作集小于 256 MiB；不保存
T×grid 中间量或 polyline，证据只保存 manifest、tile hash、统计和验证结果。
单次 evidence JSON 上限 16 MiB。CLI 采用 no-clobber 输出目录。

```powershell
python tools/verify_large_surface_network.py --size 1024 --tile-cells 128 `
  --output verification/large-surface-network/run-20261001-synthetic-1024
```

输出的 `manifest.json` 是静态合成基准证据，`verification.json` 是全格、边界、
跨 tile receiver 和统计验证结果。2048² 只应在资源预检通过后运行；本写集不把
资源拒绝或 synthetic 结果解释成真实水文认证。

