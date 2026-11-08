# 子格水力断面契约

`progress['hydraulic_sections'] = {'nodes': [[z, x, bed_m, width_m, bank_m], ...]}` 启用断面求解；每行可选第六项 Manning 糙率（省略使用 HydraulicConfig.roughness）。坐标为 state 网格索引，床面、矩形有效宽度和岸顶单位为米；宽度和糙率必须为正，岸顶不低于床面。每个路线节点须有唯一断面；缺失节点所在路线关闭并参与局部分流，绝不从 state 补造断面。断面由演化端在实际几何提交后刷新；求解不更改几何或库存。岸顶目前只记录，不作为无限高侧墙或自动挖床。

调用仍为 `solve(state, progress, sea_level_m, HydraulicConfig(...))`，未提供字段时旧路径完全不变，config 参数身份不变。返回原有 `nodes`（每行 [z,x,stage_m,depth_m,Q_m3_s]，共享节点唯一）、`route_q_m3_s`、`actual_shares`（相对输入 Q）、`active`、`accepted_q_m3_s`、`rejected_q_m3_s`、`exterior_faces` 和 `parameters`。外海潮位施于独立交换面，口门中心计算半格摩阻及临界深度。上游水头限制不能通过的水计入 rejected。

使用准稳态矩形 Manning 阻力和局部分叉分配；无二维流场、漫滩或动态蓄水。几何改变后重新调用才能反馈分流。
