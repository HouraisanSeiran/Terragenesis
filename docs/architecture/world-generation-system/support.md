# 工具、测试、展示与构建

工程支持文件也纳入系统目录；实际运行/测试未在本轮执行，分类不能代替运行认证。

| 文件 | 主归属 | 支持细项 | 职责 |
| --- | --- | --- | --- |
| [build.gradle](../../../build.gradle) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [settings.gradle](../../../settings.gradle) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [start-diffusion.ps1](../../../start-diffusion.ps1) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/environment_ecology_fixtures.py](../../../tests/environment_ecology_fixtures.py) | X4 |  | Small shared environment process fixtures; no saved-world dependency. |
| [tests/hybrid_hydraulics_fixtures.py](../../../tests/hybrid_hydraulics_fixtures.py) | X4 | S1/R7、S3/V4、S3/V8 | 固定合成水力夹具，供当前共享模型的测试共用；不含真实地形或验收记录。 |
| [tests/metric_vdm_fault_fixtures.py](../../../tests/metric_vdm_fault_fixtures.py) | X4 | S2/G2、S3/V1、S3/V5、S3/V8 | Current fault fixtures, independent of archived-v1 contract tests. |
| [tests/test_adaptive_mesh.py](../../../tests/test_adaptive_mesh.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S3/V1 | Consolidated test_adaptive_mesh implementations; numeric expressions preserved. |
| [tests/test_artifact_bundles.py](../../../tests/test_artifact_bundles.py) | X4 | S1/R5、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_network_accumulation.py](../../../tests/test_audit_network_accumulation.py) | X4 | S1/R9 | 审计工具到联合流量产品层的裁剪断边未知、负世界原点和冷读保存集成测试。 |
| [tests/test_audit_river_on_demand_contract.py](../../../tests/test_audit_river_on_demand_contract.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Tests for the on-demand consistency auditor's CONTRACT engine. The contract engine measures the worl… |
| [tests/test_audit_single_domain_surface.py](../../../tests/test_audit_single_domain_surface.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_accepted_morphology.py](../../../tests/test_audit_td_accepted_morphology.py) | X4 | S2/G2 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_accepted_topology.py](../../../tests/test_audit_td_accepted_topology.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_candidate_weather.py](../../../tests/test_audit_td_candidate_weather.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_compiled_probes.py](../../../tests/test_audit_td_compiled_probes.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_continuation_final.py](../../../tests/test_audit_td_continuation_final.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_generated_rivers.py](../../../tests/test_audit_td_generated_rivers.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_hour_pages_binary.py](../../../tests/test_audit_td_hour_pages_binary.py) | X4 | S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_hourly_seams.py](../../../tests/test_audit_td_hourly_seams.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_morphology_candidates.py](../../../tests/test_audit_td_morphology_candidates.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_native_channel_path_continuity.py](../../../tests/test_audit_td_native_channel_path_continuity.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_native_channel_tiles.py](../../../tests/test_audit_td_native_channel_tiles.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_native_storm.py](../../../tests/test_audit_td_native_storm.py) | X4 | S2/G3、S2/G4、S2/G5、S2/G14 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_native_water_surface.py](../../../tests/test_audit_td_native_water_surface.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_native_weather_storage.py](../../../tests/test_audit_td_native_weather_storage.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_river_geometry_sediment.py](../../../tests/test_audit_td_river_geometry_sediment.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_td_storage_continuation.py](../../../tests/test_audit_td_storage_continuation.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_audit_world_domains.py](../../../tests/test_audit_world_domains.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 独立结构审计字段必填/support副本一致性/有限高程/分配前头预算、空比较拒绝、真实攻击形状和提交失败门回归。 |
| [tests/test_backbone_shape_fidelity.py](../../../tests/test_backbone_shape_fidelity.py) | X4 | S1/R4、S1/R6、S1/R9 | Contract tests for native-trace / display-line shape fidelity. Every case is a synthetic ordered tra… |
| [tests/test_basin_forcing.py](../../../tests/test_basin_forcing.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | M4 tests.test_basin_forcing; merged source labels precede preserved implementations. |
| [tests/test_basin_storage.py](../../../tests/test_basin_storage.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | M4 tests.test_basin_storage; merged source labels precede preserved implementations. |
| [tests/test_basin_storage_execution.py](../../../tests/test_basin_storage_execution.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | M4 tests.test_basin_storage_execution; merged source labels precede preserved implementations. |
| [tests/test_basin_storage_io.py](../../../tests/test_basin_storage_io.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G2、S2/G5 | M4 tests.test_basin_storage_io; merged source labels precede preserved implementations. |
| [tests/test_basin_storage_profiles.py](../../../tests/test_basin_storage_profiles.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | M4 tests.test_basin_storage_profiles; merged source labels precede preserved implementations. |
| [tests/test_basin_weather_pages.py](../../../tests/test_basin_weather_pages.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | M4 tests.test_basin_weather_pages; merged source labels precede preserved implementations. |
| [tests/test_bootstrap_diffusion.py](../../../tests/test_bootstrap_diffusion.py) | X4 |  | Offline checks for the installer paths that protect downloaded assets. |
| [tests/test_bounded_glacier.py](../../../tests/test_bounded_glacier.py) | X4 | S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | Contract tests for the bounded multi-year ice body (G7 ice item). Everything here is a 3..9 cell syn… |
| [tests/test_bounded_ocean_coast.py](../../../tests/test_bounded_ocean_coast.py) | X4 | S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | Behaviour tests for the bounded basin ocean core. The four narrow points the review asked for, each … |
| [tests/test_build_module_map.py](../../../tests/test_build_module_map.py) | X4 |  | 临时隔离源码树测试BOM/CRLF原字节SHA、相对与包导入真实边、语法降级和台账生成，不修改工作区算法。 |
| [tests/test_build_td_detail_terrain.py](../../../tests/test_build_td_detail_terrain.py) | X4 | S1/R4、S1/R6、S1/R9 | Declared arithmetic of the TD detail page: seeds, interpolation, damping weights. |
| [tests/test_channel_geometry.py](../../../tests/test_channel_geometry.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8 | 有限断面宽深与坐标、参数及设计流量绑定回归。 |
| [tests/test_climate_transport.py](../../../tests/test_climate_transport.py) | X4 | S2/G3、S2/G4、S2/G5、S2/G14 | Behaviour tests for the limited G4 vapour transport. These are the **minimum** positive and negative… |
| [tests/test_coast_bounded_delta.py](../../../tests/test_coast_bounded_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | First-coast termination and frozen marine boundary behavior. |
| [tests/test_coastal_delta_along_path_cut.py](../../../tests/test_coastal_delta_along_path_cut.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_annual_capacity.py](../../../tests/test_coastal_delta_annual_capacity.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_avulsion.py](../../../tests/test_coastal_delta_avulsion.py) | X4 | S1/R2、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_bank_formation.py](../../../tests/test_coastal_delta_bank_formation.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_branch_attachment.py](../../../tests/test_coastal_delta_branch_attachment.py) | X4 | S1/R2、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_branching.py](../../../tests/test_coastal_delta_branching.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_deposition_scaling.py](../../../tests/test_coastal_delta_deposition_scaling.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_dynamic_plan.py](../../../tests/test_coastal_delta_dynamic_plan.py) | X4 | S1/R2、S1/R3、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Explicit dynamic graph enrollment and finite-stock deposition triggers. |
| [tests/test_coastal_delta_evolution.py](../../../tests/test_coastal_delta_evolution.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_formation.py](../../../tests/test_coastal_delta_formation.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_geological.py](../../../tests/test_coastal_delta_geological.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_geological_network.py](../../../tests/test_coastal_delta_geological_network.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_graph_hydraulics.py](../../../tests/test_coastal_delta_graph_hydraulics.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_graph_integration.py](../../../tests/test_coastal_delta_graph_integration.py) | X4 | S1/R2、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Real finite-stock events through consecutive attached split/rejoin arms. |
| [tests/test_coastal_delta_growth.py](../../../tests/test_coastal_delta_growth.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_hydraulic_capacity.py](../../../tests/test_coastal_delta_hydraulic_capacity.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Issue 24: hydraulic sediment capacity, loaded-only deposition, under-loaded-only erosion. |
| [tests/test_coastal_delta_hydraulics.py](../../../tests/test_coastal_delta_hydraulics.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_initial_direction.py](../../../tests/test_coastal_delta_initial_direction.py) | X4 | S1/R2、S1/R6、S1/R8、S2/G8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_irregular_consumers.py](../../../tests/test_coastal_delta_irregular_consumers.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_irregular_path.py](../../../tests/test_coastal_delta_irregular_path.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9、S2/G8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_lobes.py](../../../tests/test_coastal_delta_lobes.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_mouth_extension.py](../../../tests/test_coastal_delta_mouth_extension.py) | X4 | S1/R2、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_mouth_multicell.py](../../../tests/test_coastal_delta_mouth_multicell.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_multicell.py](../../../tests/test_coastal_delta_multicell.py) | X4 | S1/R2、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_multicell_avulsion.py](../../../tests/test_coastal_delta_multicell_avulsion.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_node_inventory.py](../../../tests/test_coastal_delta_node_inventory.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_plain.py](../../../tests/test_coastal_delta_plain.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_regional.py](../../../tests/test_coastal_delta_regional.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_routes.py](../../../tests/test_coastal_delta_routes.py) | X4 | S1/R2、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_delta_window.py](../../../tests/test_coastal_delta_window.py) | X4 | S1/R1、S1/R2、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_marine_base.py](../../../tests/test_coastal_marine_base.py) | X4 | S1/R1、S1/R2、S1/R8、S1/R9、S2/G1、S2/G2、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_marine_longterm.py](../../../tests/test_coastal_marine_longterm.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_marine_sediment.py](../../../tests/test_coastal_marine_sediment.py) | X4 | S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_river_connector.py](../../../tests/test_coastal_river_connector.py) | X4 | S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_coastal_terrain.py](../../../tests/test_coastal_terrain.py) | X4 | S1/R1、S1/R2、S2/G1、S2/G8 | Consolidated tests.test_coastal_terrain implementations; numeric expressions preserved. |
| [tests/test_common_infra.py](../../../tests/test_common_infra.py) | X4 |  | Equivalence proof for terrain_pipeline.common_infra against the legacy copies it replaces. Legacy fu… |
| [tests/test_compare_hydrology_projection_naturalness.py](../../../tests/test_compare_hydrology_projection_naturalness.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_compare_td_river_shapes.py](../../../tests/test_compare_td_river_shapes.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_complete_delta.py](../../../tests/test_complete_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Saved products, finite forcing, and one-way continuation contracts. |
| [tests/test_continue_td_weather_pipeline.py](../../../tests/test_continue_td_weather_pipeline.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_delta_distributary_trial.py](../../../tests/test_delta_distributary_trial.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_delta_forms.py](../../../tests/test_delta_forms.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_delta_network_skeleton.py](../../../tests/test_delta_network_skeleton.py) | X4 | S1/R1、S1/R4、S1/R6、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_delta_network_skeleton_v2.py](../../../tests/test_delta_network_skeleton_v2.py) | X4 | S1/R4、S1/R6、S1/R8、S1/R9、S2/G8、S2/G19 | Tests for the complex delta network skeleton v2 (whole-length bifurcation/confluence, no level cap). |
| [tests/test_delta_network_skeleton_v3.py](../../../tests/test_delta_network_skeleton_v3.py) | X4 | S1/R4、S1/R6、S1/R8、S1/R9、S2/G8、S2/G19 | Tests for the complex delta network v3 (oblique random links, meanders, soft old-PlanConfig limits). |
| [tests/test_delta_network_skeleton_v4.py](../../../tests/test_delta_network_skeleton_v4.py) | X4 | S1/R1、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Tests for the complex delta network v4 (v3 skeleton + sand-apron land building, reference-image metr… |
| [tests/test_delta_tidal_validation.py](../../../tests/test_delta_tidal_validation.py) | X4 | S1/R7、S1/R9、S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | The validation uses an ocean boundary, finite tides and no repeated river packets. |
| [tests/test_diffusion.py](../../../tests/test_diffusion.py) | X4 | S1/R1、S1/R9、S2/G1 | Protocol/cache fixtures; these tests do not claim to run the neural model. |
| [tests/test_drainage_diagnostic.py](../../../tests/test_drainage_diagnostic.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | M4 tests.test_drainage_diagnostic; merged source labels precede preserved implementations. |
| [tests/test_drainage_equivalence.py](../../../tests/test_drainage_equivalence.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | M4 tests.test_drainage_equivalence; merged source labels precede preserved implementations. |
| [tests/test_drainage_graph.py](../../../tests/test_drainage_graph.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | M4 tests.test_drainage_graph; merged source labels precede preserved implementations. |
| [tests/test_drainage_strict.py](../../../tests/test_drainage_strict.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | M4 tests.test_drainage_strict; merged source labels precede preserved implementations. |
| [tests/test_drainage_surface.py](../../../tests/test_drainage_surface.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | M4 tests.test_drainage_surface; merged source labels precede preserved implementations. |
| [tests/test_dynamic_feedback.py](../../../tests/test_dynamic_feedback.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_climate_driver.py](../../../tests/test_environment_climate_driver.py) | X4 | S1/R7、S1/R8、S1/R9、S2/G3、S2/G4、S2/G5、S2/G6、S2/G14 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_coastal_delta.py](../../../tests/test_environment_coastal_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G5、S2/G6、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_coastal_exchange.py](../../../tests/test_environment_coastal_exchange.py) | X4 | S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_context.py](../../../tests/test_environment_context.py) | X4 | S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_contract_equivalence.py](../../../tests/test_environment_contract_equivalence.py) | X4 |  | Differential tests: environment_contract must equal the three older contract modules. |
| [tests/test_environment_defaults.py](../../../tests/test_environment_defaults.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G3、S2/G4、S2/G5、S2/G6、S2/G7、S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | The default-value registry must match live behaviour, and identity must be stable. ``environment_def… |
| [tests/test_environment_delta_fv.py](../../../tests/test_environment_delta_fv.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Behavioral coverage for the persistent finite FV delta boundary. |
| [tests/test_environment_delta_source.py](../../../tests/test_environment_delta_source.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G5、S2/G6、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_ecology_integration.py](../../../tests/test_environment_ecology_integration.py) | X4 | S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | Actual process-to-process inventory transfers, separate from TD acceptance. |
| [tests/test_environment_energy_processes.py](../../../tests/test_environment_energy_processes.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_explicit_handoff.py](../../../tests/test_environment_explicit_handoff.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_groundwater.py](../../../tests/test_environment_groundwater.py) | X4 | S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_habitat.py](../../../tests/test_environment_habitat.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_land_cover.py](../../../tests/test_environment_land_cover.py) | X4 | S1/R5、S2/G5、S2/G6、S2/G7、S2/G9 | External-behaviour tests for the G6 land-cover consumer. Every test asserts something a caller can o… |
| [tests/test_environment_land_cover_coupling.py](../../../tests/test_environment_land_cover_coupling.py) | X4 | S1/R5、S2/G5、S2/G6、S2/G7、S2/G9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_mass_processes.py](../../../tests/test_environment_mass_processes.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_material_source.py](../../../tests/test_environment_material_source.py) | X4 | S2/G2、S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_network_transition.py](../../../tests/test_environment_network_transition.py) | X4 | S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_process_product.py](../../../tests/test_environment_process_product.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_process_protocol.py](../../../tests/test_environment_process_protocol.py) | X4 | S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | The init/step protocol must return exactly what the legacy process modules return. |
| [tests/test_environment_processes_cli.py](../../../tests/test_environment_processes_cli.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_regional_hydraulics.py](../../../tests/test_environment_regional_hydraulics.py) | X4 | S1/R7、S1/R8、S1/R9、S2/G5、S2/G6 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_seasonal_air.py](../../../tests/test_environment_seasonal_air.py) | X4 | S2/G3、S2/G4、S2/G5、S2/G14 | External-behaviour tests for the G3 seasonal air adapter. Scope of these tests: the **declared contr… |
| [tests/test_environment_seasonal_coupling.py](../../../tests/test_environment_seasonal_coupling.py) | X4 | S1/R5、S1/R7、S1/R8、S1/R9、S2/G3、S2/G4、S2/G5、S2/G6、S2/G7、S2/G9、S2/G14 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_soil_chemistry.py](../../../tests/test_environment_soil_chemistry.py) | X4 | S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_succession.py](../../../tests/test_environment_succession.py) | X4 | S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_environment_world_product.py](../../../tests/test_environment_world_product.py) | X4 |  | 同坐标 30 m 环境联合产品的行为测试。 只断言外部可观察的性质：装配后的字段与状态、四层身份分离、点序无关、只读查询、 拒绝缺源与非法输入、保存/读回一致。不断言内部辅助函数。 |
| [tests/test_export_td_candidate_bounded_review.py](../../../tests/test_export_td_candidate_bounded_review.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_export_vdm_geometry_io_review.py](../../../tests/test_export_vdm_geometry_io_review.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_fault_preview_bridge.py](../../../tests/test_fault_preview_bridge.py) | X4 |  | Real pinned fault preview contracts, without hydrology or saved output writes. |
| [tests/test_fictional_world_overview.py](../../../tests/test_fictional_world_overview.py) | X4 | S1/R1、S1/R2、S1/R6、S2/G1 | Contract tests for the finite fictional-world overview. These tests exercise the module's *external*… |
| [tests/test_fine_subgrid.py](../../../tests/test_fine_subgrid.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | Consolidated test_fine_subgrid implementations; numeric expressions preserved. |
| [tests/test_fine_terrain_40km_lake.py](../../../tests/test_fine_terrain_40km_lake.py) | X4 | S1/R6、S1/R7、S1/R9 | 40km湖盆验收行为测试：闭合盆、窗口收敛、A(h)/V(h)与独立复算一致、截断窗不得当湖。 |
| [tests/test_fine_terrain_40km_reach.py](../../../tests/test_fine_terrain_40km_reach.py) | X4 |  | 40km@30m河段验收行为测试：断言选区规则与拒绝码、断面深度是水力学解而非常数、三本账各自单位下闭合、床变用体积恒等式、未执行项必须声明为未执行。 |
| [tests/test_finite_multiyear_source.py](../../../tests/test_finite_multiyear_source.py) | X4 | S1/R7、S1/R8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_finite_river_block_schedule.py](../../../tests/test_finite_river_block_schedule.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | 实际异序块派发、跨块循环的格级DAG、端口去重/逐块水账、非零初态和恢复累计/末边界非法状态拒绝的行为对照。 |
| [tests/test_finite_river_event.py](../../../tests/test_finite_river_event.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | 有限事件土壤供水、端口一次交付、湖库容反函数、裁断上游拒绝和超容量不改输入的正负行为回归。 |
| [tests/test_finite_river_product.py](../../../tests/test_finite_river_product.py) | X4 | S1/R9 | 有限产品默认消费、域/时刻/坐标拒绝、只读数据不变、显式恢复和不存在产品不回退的行为回归。 |
| [tests/test_fluvial_delta_region_budget.py](../../../tests/test_fluvial_delta_region_budget.py) | X4 |  | Corrected tests for tools/fluvial_delta_region_budget.py (hand-computed). |
| [tests/test_formative_section.py](../../../tests/test_formative_section.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_frozen_hybrid_geometry.py](../../../tests/test_frozen_hybrid_geometry.py) | X4 | S3/V1、S3/V2、S3/V3、S3/V5、S3/V6、S3/V8 | Consolidated test_frozen_hybrid_geometry implementations; numeric expressions preserved. |
| [tests/test_frozen_hybrid_hydraulics.py](../../../tests/test_frozen_hybrid_hydraulics.py) | X4 | S1/R7、S3/V1、S3/V2、S3/V3、S3/V4、S3/V5、S3/V6、S3/V8 | 混合水力的字节一致、当前v8等价与历史隔离门；验证收敛未改变现有产物语义。；选择性运行的原始源码回归，仅经冻结加载器执行；不进默认测试路径。 |
| [tests/test_frozen_terrain_centerline.py](../../../tests/test_frozen_terrain_centerline.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_fv_bedload_v4.py](../../../tests/test_fv_bedload_v4.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_fv_coastal_sediment.py](../../../tests/test_fv_coastal_sediment.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_fv_current_runner_migration.py](../../../tests/test_fv_current_runner_migration.py) | X4 | S1/R8、S1/R9、S2/G8、S2/G19 | Finite, frozen-parent checks for current FV scheduler and explicit old replay. |
| [tests/test_fv_growth_v3.py](../../../tests/test_fv_growth_v3.py) | X4 |  | Explicit archived v3/v1 numerical comparisons; current v4 has separate tests. |
| [tests/test_fv_incident_wave_vectorized.py](../../../tests/test_fv_incident_wave_vectorized.py) | X4 | S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_fv_legacy_replay.py](../../../tests/test_fv_legacy_replay.py) | X4 |  | Explicit archived FV replay and source/parameter rejection checks. |
| [tests/test_fv_suspended_growth.py](../../../tests/test_fv_suspended_growth.py) | X4 |  | Explicit frozen-v1 numerical comparison tests, outside current generation. |
| [tests/test_geography.py](../../../tests/test_geography.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_geography_v2.py](../../../tests/test_geography_v2.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_geography_v3.py](../../../tests/test_geography_v3.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_geography_v4.py](../../../tests/test_geography_v4.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_geography_v5.py](../../../tests/test_geography_v5.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_geology_properties.py](../../../tests/test_geology_properties.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R9、S2/G2 | G2 地质物性组合层的验收测试（unittest，无 pytest）。 只测外部行为：非空层序与非零填充、逐位复用既有核、扩展表身份、 30 m 格心/参考点映射、乱序与分窗一致、真实宽度消费者因果对… |
| [tests/test_geology_strata.py](../../../tests/test_geology_strata.py) | X4 | S2/G2 | Declared stratigraphy tests (unittest, no pytest). Scope: the declared-parallel-strata model only — … |
| [tests/test_global_river_reference_sources.py](../../../tests/test_global_river_reference_sources.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_hybrid_geometry.py](../../../tests/test_hybrid_geometry.py) | X4 | S1/R7、S3/V1、S3/V2、S3/V3、S3/V4、S3/V5、S3/V6、S3/V8 | Consolidated test_hybrid_geometry implementations; numeric expressions preserved. |
| [tests/test_hybrid_geometry_saved_audit.py](../../../tests/test_hybrid_geometry_saved_audit.py) | X4 | S3/V1、S3/V2、S3/V3、S3/V5、S3/V6、S3/V8 | Consolidated test_hybrid_geometry_saved_audit implementations; numeric expressions preserved. |
| [tests/test_hybrid_hydraulics.py](../../../tests/test_hybrid_hydraulics.py) | X4 | S1/R7、S3/V4、S3/V8 | Consolidated test_hybrid_hydraulics implementations; numeric expressions preserved. |
| [tests/test_hybrid_hydraulics_saved_audit.py](../../../tests/test_hybrid_hydraulics_saved_audit.py) | X4 | S1/R7、S3/V4、S3/V8 | Consolidated test_hybrid_hydraulics_saved_audit implementations; numeric expressions preserved. |
| [tests/test_hybrid_kernels_equivalence.py](../../../tests/test_hybrid_kernels_equivalence.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S3/V1、S3/V2、S3/V3、S3/V4、S3/V5、S3/V6、S3/V7、S3/V8 | R3 step 1: the new shallow/hybrid/special-terrain/surface kernels equal every old entry point bit fo… |
| [tests/test_hydrology_detail.py](../../../tests/test_hydrology_detail.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9、S2/G1、S2/G3、S2/G4 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_hydrology_detail_projection.py](../../../tests/test_hydrology_detail_projection.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_hydrology_detail_tributaries.py](../../../tests/test_hydrology_detail_tributaries.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_hydrology_detail_tributary_finite.py](../../../tests/test_hydrology_detail_tributary_finite.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_hydrology_large_preview.py](../../../tests/test_hydrology_large_preview.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_hydrology_macro_channel_feasibility.py](../../../tests/test_hydrology_macro_channel_feasibility.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_hydrology_planning.py](../../../tests/test_hydrology_planning.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_hydrology_planning_naturalness.py](../../../tests/test_hydrology_planning_naturalness.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_hydrology_seasonal.py](../../../tests/test_hydrology_seasonal.py) | X4 | S1/R5、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_hydrology_seasonal_hybrid.py](../../../tests/test_hydrology_seasonal_hybrid.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_hydrology_shared_section_support.py](../../../tests/test_hydrology_shared_section_support.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_hydrovector_evidence.py](../../../tests/test_hydrovector_evidence.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_inspect_world_water_layout_page.py](../../../tests/test_inspect_world_water_layout_page.py) | X4 |  | 以合成页面检查高程与水域分类错配统计、显式水位和CLI图片输出及输入失败行为。 |
| [tests/test_integrated_delta_discharge.py](../../../tests/test_integrated_delta_discharge.py) | X4 | S1/R6、S1/R7、S1/R8 | Discharge scenarios rebuild hydraulics while preserving finite materials. |
| [tests/test_island_mountains.py](../../../tests/test_island_mountains.py) | X4 | S1/R1、S2/G1、S2/G8 | Declared analytic large-island fixtures; never a claim about the real world. |
| [tests/test_lake_balance.py](../../../tests/test_lake_balance.py) | X4 | S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_lake_river_connector.py](../../../tests/test_lake_river_connector.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_lake_routing.py](../../../tests/test_lake_routing.py) | X4 | S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_active_network.py](../../../tests/test_large_delta_active_network.py) | X4 | S1/R6、S1/R8、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_active_source.py](../../../tests/test_large_delta_active_source.py) | X4 | S1/R5、S1/R8、S1/R9、S2/G8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_evolution.py](../../../tests/test_large_delta_evolution.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_formation_source.py](../../../tests/test_large_delta_formation_source.py) | X4 | S1/R1、S1/R5、S1/R6、S1/R7、S1/R8、S2/G8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_forward.py](../../../tests/test_large_delta_forward.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_initial_cover.py](../../../tests/test_large_delta_initial_cover.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_shelf_product.py](../../../tests/test_large_delta_shelf_product.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_shelf_scenario.py](../../../tests/test_large_delta_shelf_scenario.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_source.py](../../../tests/test_large_delta_source.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_state.py](../../../tests/test_large_delta_state.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_suite.py](../../../tests/test_large_delta_suite.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_suite_network.py](../../../tests/test_large_delta_suite_network.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_suite_tidal.py](../../../tests/test_large_delta_suite_tidal.py) | X4 | S1/R6、S1/R7、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_terrain_product.py](../../../tests/test_large_delta_terrain_product.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_tidal_dynamics.py](../../../tests/test_large_delta_tidal_dynamics.py) | X4 | S1/R6、S1/R7、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_tidal_reconstruction.py](../../../tests/test_large_delta_tidal_reconstruction.py) | X4 | S1/R7、S1/R9、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_tidal_segmented.py](../../../tests/test_large_delta_tidal_segmented.py) | X4 | S1/R1、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_tidal_source.py](../../../tests/test_large_delta_tidal_source.py) | X4 | S1/R1、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_delta_trial.py](../../../tests/test_large_delta_trial.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_scale_resource_preflight.py](../../../tests/test_large_scale_resource_preflight.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_scale_surface_network.py](../../../tests/test_large_scale_surface_network.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_scale_surface_tiles.py](../../../tests/test_large_scale_surface_tiles.py) | X4 | S1/R1、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_surface_network.py](../../../tests/test_large_surface_network.py) | X4 | S1/R3、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_large_world_layout.py](../../../tests/test_large_world_layout.py) | X4 | S1/R1、S1/R2、S2/G1、S2/G3、S2/G4 | 三模式12,288km有限范围比例与同坐标分窗一致性、TD绝对条件索引测试。 |
| [tests/test_large_world_river_geometry.py](../../../tests/test_large_world_river_geometry.py) | X4 | S1/R4、S1/R6、S1/R9、S2/G2 | 河槽接线Q及床岸硬度响应、pending冷读、负坐标精确岩性、水域保护和合成页CLI集成。 |
| [tests/test_legacy_region.py](../../../tests/test_legacy_region.py) | X4 | S1/R9、S4/J1 | Behavior tests for explicit legacy import and read-only pair loading. |
| [tests/test_legacy_source_isolation.py](../../../tests/test_legacy_source_isolation.py) | X4 | S1/R7、S1/R9、S2/G2、S3/V1、S3/V5、S3/V8 | Independent cross-family checks for explicit, isolated legacy replay. |
| [tests/test_metric_backbone_precompute.py](../../../tests/test_metric_backbone_precompute.py) | X4 | S1/R4、S1/R6、S1/R9 | Contract tests for the river-backbone precompute layer. Every test builds a **synthetic** receiver g… |
| [tests/test_metric_backbone_product.py](../../../tests/test_metric_backbone_product.py) | X4 | S1/R4、S1/R6、S1/R9 | Contract tests for the river-backbone product codec and its read-only query index. These tests build… |
| [tests/test_metric_biome_climate.py](../../../tests/test_metric_biome_climate.py) | X4 | S2/G3、S2/G4、S2/G5、S2/G14 | Contract tests for the migrated Python biome-selection rules (P5.2). Acceptance mapping (contract `b… |
| [tests/test_metric_boundary_coupling.py](../../../tests/test_metric_boundary_coupling.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_budget_centerline.py](../../../tests/test_metric_budget_centerline.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_channel_product.py](../../../tests/test_metric_channel_product.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_climate_refinement.py](../../../tests/test_metric_climate_refinement.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | Contract tests for the v2 terrain-refined climate layer (P4.3). Acceptance mapping (contract `climat… |
| [tests/test_metric_coastal_transport.py](../../../tests/test_metric_coastal_transport.py) | X4 | S1/R8、S1/R9、S2/G8、S2/G19 | Behavior checks for finite phase-driven coastal transport. |
| [tests/test_metric_cohort_calibration.py](../../../tests/test_metric_cohort_calibration.py) | X4 | S1/R6 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_coupled_product.py](../../../tests/test_metric_coupled_product.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_coupled_review.py](../../../tests/test_metric_coupled_review.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_cross_region.py](../../../tests/test_metric_cross_region.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 跨区一致性行为测试：只断言任何页对都必须成立的性质，真实2049页由audit工具测量。 |
| [tests/test_metric_delta.py](../../../tests/test_metric_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_delta_graph_inlet.py](../../../tests/test_metric_delta_graph_inlet.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_delta_product.py](../../../tests/test_metric_delta_product.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_delta_sediment_product.py](../../../tests/test_metric_delta_sediment_product.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_depression_gate.py](../../../tests/test_metric_depression_gate.py) | X4 | S1/R2、S1/R3、S1/R6、S1/R7、S1/R9 | 微洼地门行为测试：合成属性断言与真实页记录数分开；归档页缺失时明确跳过而非静默通过。 |
| [tests/test_metric_design_barycentric_batch.py](../../../tests/test_metric_design_barycentric_batch.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_design_merge_groups.py](../../../tests/test_metric_design_merge_groups.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_distribution_calibration.py](../../../tests/test_metric_distribution_calibration.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_domain_bed_feedback.py](../../../tests/test_metric_domain_bed_feedback.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | `metric_domain_bed_feedback`: the derived bed-change product's contracts. What is held to account he… |
| [tests/test_metric_domain_closed_gate.py](../../../tests/test_metric_domain_closed_gate.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Finite-core gate contracts, independent of the closure algorithm. |
| [tests/test_metric_domain_closure.py](../../../tests/test_metric_domain_closure.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_domain_coupled.py](../../../tests/test_metric_domain_coupled.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | `metric_domain_coupled`: the coupled water-sediment ledger's contracts. What is held to account here… |
| [tests/test_metric_domain_eligibility.py](../../../tests/test_metric_domain_eligibility.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | p3.1 contract tests: world-anchored domain eligibility and outlet identity. `metric_domain_closure` … |
| [tests/test_metric_domain_flow.py](../../../tests/test_metric_domain_flow.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | `metric_domain_flow`: the domain water ledger's contracts. What is held to account here (and nothing… |
| [tests/test_metric_domain_pipeline.py](../../../tests/test_metric_domain_pipeline.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | P6.2 tests: the on-demand river domain pipeline's contracts. `metric_domain_closure` proves window-i… |
| [tests/test_metric_domain_sediment.py](../../../tests/test_metric_domain_sediment.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | `metric_domain_sediment`: the domain sediment ledger's contracts. What is held to account here (and … |
| [tests/test_metric_environment_query.py](../../../tests/test_metric_environment_query.py) | X4 | S1/R5、S2/G2、S2/G3、S2/G4、S2/G5、S2/G6、S2/G7、S2/G9、S2/G14 | 环境联合查询policy分派、真实DEM格对齐/覆盖、来源与landform值身份、单调调用顺序/缓存独立、30m土壤和预算拒绝的行为回归；不要求局地分类有区分度。 |
| [tests/test_metric_equilibrium_lake_support.py](../../../tests/test_metric_equilibrium_lake_support.py) | X4 | S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_event_response.py](../../../tests/test_metric_event_response.py) | X4 | S1/R5、S2/G3、S2/G4、S2/G5、S2/G14 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_extension_review.py](../../../tests/test_metric_extension_review.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Independent integration regressions for supplemental physical-state contracts. |
| [tests/test_metric_fan_floodplain.py](../../../tests/test_metric_fan_floodplain.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_flat_distance.py](../../../tests/test_metric_flat_distance.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_fluvial_delta.py](../../../tests/test_metric_fluvial_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_fluvial_diffusion_ablation.py](../../../tests/test_metric_fluvial_diffusion_ablation.py) | X4 | S1/R6、S1/R7、S1/R8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_fluvial_distributary.py](../../../tests/test_metric_fluvial_distributary.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_fluvial_inlet_weights.py](../../../tests/test_metric_fluvial_inlet_weights.py) | X4 | S1/R7、S1/R8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_fluvial_morphodynamics.py](../../../tests/test_metric_fluvial_morphodynamics.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G10、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_fluvial_slope_stability.py](../../../tests/test_metric_fluvial_slope_stability.py) | X4 | S1/R8、S2/G10 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_fluvial_water_repair.py](../../../tests/test_metric_fluvial_water_repair.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_geometry_sediment_review.py](../../../tests/test_metric_geometry_sediment_review.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Independent audit regressions for narrow bed reversals and material ledgers. |
| [tests/test_metric_highland_sources.py](../../../tests/test_metric_highland_sources.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 高地门/世界成员/首次贡献河头/去重依赖、未知传播与来源身份重封攻击测试；不以几何候选代实际供水。 |
| [tests/test_metric_integrated_delta.py](../../../tests/test_metric_integrated_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Unit tests for the integrated reduced channel-tree delta model. These tests build small synthetic ge… |
| [tests/test_metric_lake_channel_coupling.py](../../../tests/test_metric_lake_channel_coupling.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_lake_storage.py](../../../tests/test_metric_lake_storage.py) | X4 | S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_large_runoff.py](../../../tests/test_metric_large_runoff.py) | X4 | S1/R5、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_large_source.py](../../../tests/test_metric_large_source.py) | X4 | S1/R1、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_local_budget_centerline.py](../../../tests/test_metric_local_budget_centerline.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_lowland_runoff.py](../../../tests/test_metric_lowland_runoff.py) | X4 | S1/R5、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_morphology_coupling.py](../../../tests/test_metric_morphology_coupling.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_morphology_events.py](../../../tests/test_metric_morphology_events.py) | X4 | S1/R6、S1/R7、S1/R8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_morphology_products.py](../../../tests/test_metric_morphology_products.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_morphology_topology.py](../../../tests/test_metric_morphology_topology.py) | X4 | S1/R6、S1/R7、S1/R8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_natural_delta.py](../../../tests/test_metric_natural_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_natural_lakes.py](../../../tests/test_metric_natural_lakes.py) | X4 | S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_network_accumulation.py](../../../tests/test_metric_network_accumulation.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 有限联合汇流的独立逐源路径对照、重复汇流、环拒绝、未知传播、预算与存储顺序测试。 |
| [tests/test_metric_network_discharge_product.py](../../../tests/test_metric_network_discharge_product.py) | X4 | S1/R9 | 联合诊断流量产品身份、冷读复算、未知上游消费拒绝、负世界坐标及分配前预算回归。 |
| [tests/test_metric_noise_forcing.py](../../../tests/test_metric_noise_forcing.py) | X4 | S2/G3、S2/G4、S2/G5、S2/G14 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_pet_et.py](../../../tests/test_metric_pet_et.py) | X4 | S1/R5、S2/G3、S2/G4、S2/G5、S2/G6、S2/G7、S2/G9、S2/G14 | External-behaviour tests for the PET/ET adapter (G5 first card). Every test asserts an externally ob… |
| [tests/test_metric_reference_erosion.py](../../../tests/test_metric_reference_erosion.py) | X4 | S1/R6、S1/R7、S1/R8 | Local router exchange test: positive shear erodes finite bed at zero input. |
| [tests/test_metric_reference_routing.py](../../../tests/test_metric_reference_routing.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_region.py](../../../tests/test_metric_region.py) | X4 | S1/R1、S1/R9、S2/G1、S3/V8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_resolution_exchange.py](../../../tests/test_metric_resolution_exchange.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_resolution_series.py](../../../tests/test_metric_resolution_series.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_river_contracts.py](../../../tests/test_metric_river_contracts.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_river_dominant_delta.py](../../../tests/test_metric_river_dominant_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_river_forcing.py](../../../tests/test_metric_river_forcing.py) | X4 | S2/G3、S2/G4、S2/G5、S2/G14 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_river_output.py](../../../tests/test_metric_river_output.py) | X4 | S1/R4、S1/R5、S1/R9、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_river_policy_comparison.py](../../../tests/test_metric_river_policy_comparison.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_river_product.py](../../../tests/test_metric_river_product.py) | X4 | S1/R5、S1/R9、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_river_release.py](../../../tests/test_metric_river_release.py) | X4 | S1/R9 | Saved release behavior and linked evidence validation. |
| [tests/test_metric_river_runoff.py](../../../tests/test_metric_river_runoff.py) | X4 | S1/R5、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_river_source.py](../../../tests/test_metric_river_source.py) | X4 | S1/R1、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_saved_river_supply.py](../../../tests/test_metric_saved_river_supply.py) | X4 | S1/R5、S1/R9、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_sediment.py](../../../tests/test_metric_sediment.py) | X4 | S1/R6、S1/R7、S1/R8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_soil_condition.py](../../../tests/test_metric_soil_condition.py) | X4 | S1/R5、S2/G5、S2/G6、S2/G7、S2/G9 | metric_soil_condition 的单元测试（unittest，无 pytest）。 |
| [tests/test_metric_stylized_wetland.py](../../../tests/test_metric_stylized_wetland.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_support_distance.py](../../../tests/test_metric_support_distance.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_td_delta_initialization.py](../../../tests/test_metric_td_delta_initialization.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_td_generated_rivers.py](../../../tests/test_metric_td_generated_rivers.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_td_generated_source.py](../../../tests/test_metric_td_generated_source.py) | X4 | S1/R1、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_td_native_planning.py](../../../tests/test_metric_td_native_planning.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_td_single_source_review.py](../../../tests/test_metric_td_single_source_review.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | Single-source TD river review contracts; no large solve or GPU. |
| [tests/test_metric_terrain_centerline.py](../../../tests/test_metric_terrain_centerline.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_tide_wave_morphology.py](../../../tests/test_metric_tide_wave_morphology.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_upstream_sediment.py](../../../tests/test_metric_upstream_sediment.py) | X4 | S1/R6、S1/R7、S1/R8 | Behavioral tests for route_daily_sediment public API. |
| [tests/test_metric_vdm_fault.py](../../../tests/test_metric_vdm_fault.py) | X4 | S2/G2、S3/V1、S3/V5、S3/V8 | Explicit replay tests for the archived first metric VDM fault API. The original test bytes and imple… |
| [tests/test_metric_vdm_fault_migration.py](../../../tests/test_metric_vdm_fault_migration.py) | X4 | S2/G2、S3/V1、S3/V5、S3/V8 | A-plan migration: current v2 generation and explicit frozen-v1 replay. |
| [tests/test_metric_water_cycle.py](../../../tests/test_metric_water_cycle.py) | X4 | S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_metric_world_domains.py](../../../tests/test_metric_world_domains.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 有限结构域世界成员、ID、owner、上游未知、NaN往返、预算和重封派生篡改拒绝回归；不是湖或自然域认证。 |
| [tests/test_metric_world_reaches.py](../../../tests/test_metric_world_reaches.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | 河段有向承接、单格/空通道、北西向主干顺序、节点边长度与父完整路径独立绑定及篡改拒绝测试。 |
| [tests/test_minecraft_export.py](../../../tests/test_minecraft_export.py) | X4 | S1/R9、S3/V8、S4/J1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_minecraft_preset.py](../../../tests/test_minecraft_preset.py) | X4 | S1/R9、S4/J2 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_module_catalog.py](../../../tests/test_module_catalog.py) | X4 |  | Static catalog coverage, provenance and drift checks without application imports. |
| [tests/test_mountain_depression_geometry.py](../../../tests/test_mountain_depression_geometry.py) | X4 | S1/R6、S1/R7、S1/R9 | Geometry semantics, complete upstream areas and safe static persistence. |
| [tests/test_mountain_fine_geometry.py](../../../tests/test_mountain_fine_geometry.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R9 | Real TD bilinear transverse profiles and continuous shared fine sections. |
| [tests/test_mountain_fine_storage.py](../../../tests/test_mountain_fine_storage.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R9 | Source-bound fine storage, real interface sills and signed wet/dry flux. |
| [tests/test_mountain_forms.py](../../../tests/test_mountain_forms.py) | X4 | S1/R1、S1/R2、S2/G1、S2/G2、S2/G3、S2/G4 | Consolidated tests.test_mountain_forms implementations; numeric expressions preserved. |
| [tests/test_mountain_lake_coupling.py](../../../tests/test_mountain_lake_coupling.py) | X4 | S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_mountain_pool_network.py](../../../tests/test_mountain_pool_network.py) | X4 | S1/R6、S1/R7、S1/R9 | Complete real TD contribution groups, safe static pool equations and refusals. |
| [tests/test_mountain_rainfall.py](../../../tests/test_mountain_rainfall.py) | X4 | S1/R5、S2/G5 | Small helper regressions and pinned mountain provenance checks only. |
| [tests/test_mountain_runoff_routing.py](../../../tests/test_mountain_runoff_routing.py) | X4 | S1/R5、S2/G5 | Focused topology, conservative propagation and hostile archive regressions. |
| [tests/test_mountain_source_adapter.py](../../../tests/test_mountain_source_adapter.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_mountain_storm_100m.py](../../../tests/test_mountain_storm_100m.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_mountain_storm_forcing.py](../../../tests/test_mountain_storm_forcing.py) | X4 | S2/G3、S2/G4、S2/G5、S2/G14 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_mountain_storm_hru_scale.py](../../../tests/test_mountain_storm_hru_scale.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_native_30m_audit_gates.py](../../../tests/test_native_30m_audit_gates.py) | X4 |  | 三账硬门拒绝NaN、负库存、非零残差及总体抵消的局部床变错误。 |
| [tests/test_native_30m_bundle.py](../../../tests/test_native_30m_bundle.py) | X4 |  | 严格JSON、发布失败原子性、CLI拒绝与真实候选跨文件语义篡改回归；真实数据缺失明确跳过。 |
| [tests/test_native_30m_bundle_validation.py](../../../tests/test_native_30m_bundle_validation.py) | X4 | S1/R1、S1/R9 | 纯合成拓扑/侧向归属/子步强迫重封篡改与水力水沙父子状态反例。 |
| [tests/test_native_30m_compute_worker.py](../../../tests/test_native_30m_compute_worker.py) | X4 |  | 计算worker隔离、实际子进程内存预算拒绝、超时和失败不提交最终目录测试。 |
| [tests/test_native_30m_declarations.py](../../../tests/test_native_30m_declarations.py) | X4 |  | 正式有限声明的实际节点供给、时窗、坡度状态、未标定参数及未实现能力绑定测试。 |
| [tests/test_native_30m_diagnostic_only.py](../../../tests/test_native_30m_diagnostic_only.py) | X4 |  | 纯合成及真实小worker验证诊断profile无土壤桶和河段水沙、元数据重封拒绝及full scope不可用。 |
| [tests/test_native_30m_entry_guards.py](../../../tests/test_native_30m_entry_guards.py) | X4 |  | AST核对原生工具无直接粗条件/GPU导入或字面量scratch脚本生产加载；不冒充完整动态导入证明。 |
| [tests/test_native_30m_envelope_gates.py](../../../tests/test_native_30m_envelope_gates.py) | X4 |  | 小型envelope归档的重封攻击测试：能力位升级、未知真值能力、对象/结构dtype及路径逃逸须拒绝；该夹具只对envelope门有效，不代表完整数值包。 |
| [tests/test_native_30m_event_config.py](../../../tests/test_native_30m_event_config.py) | X4 | S1/R5、S2/G5 | 声明风暴和土壤参数覆盖的校验、配置身份、CLI实际传值、非法初始状态早拒及水桶/裸雨可分辨测试。 |
| [tests/test_native_30m_finite_domain_acceptance.py](../../../tests/test_native_30m_finite_domain_acceptance.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | p5: executable acceptance for the finite real 30 m cross-window integration round. What this file pi… |
| [tests/test_native_30m_hydraulic_reference.py](../../../tests/test_native_30m_hydraulic_reference.py) | X4 |  | 独立矩形Manning解析对照、干床、非法输入、保存状态篡改及更新床正反对照测试。 |
| [tests/test_native_30m_hydrology_account.py](../../../tests/test_native_30m_hydrology_account.py) | X4 | S1/R4、S1/R5、S1/R9、S2/G5 | Stage p4 gates: native-30 m soil-bucket runoff and the full hydrology ledger. What these tests pin, … |
| [tests/test_native_30m_hydrology_synthetic_baselines.py](../../../tests/test_native_30m_hydrology_synthetic_baselines.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | Executable synthetic baselines and refusal counter-examples for the native-30 m lake / depression / … |
| [tests/test_native_30m_infinite_certification_matrix.py](../../../tests/test_native_30m_infinite_certification_matrix.py) | X4 | S1/R1、S1/R3、S1/R4、S1/R5、S1/R9、S2/G1、S2/G5 | p8: the native 30 m infinite-world certification window family, as executable assertions. What this … |
| [tests/test_native_30m_lakes.py](../../../tests/test_native_30m_lakes.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Small synthetic tests for the native-30 m lake / depression storage-and-spill mechanism. Discipline … |
| [tests/test_native_30m_natural_outlet_status.py](../../../tests/test_native_30m_natural_outlet_status.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R6、S1/R9 | Synthetic pass/reject baselines for the native 30 m natural-outlet gate. Four disciplines, stated on… |
| [tests/test_native_30m_packed_archive.py](../../../tests/test_native_30m_packed_archive.py) | X4 |  | 打包trace的零填充、安全布局、dtype、越界、身份和非有限值回归。 |
| [tests/test_native_30m_query.py](../../../tests/test_native_30m_query.py) | X4 | S1/R9 | scope私有副本、批量整次拒绝、坐标时窗和诊断事件重封来源绑定合成测试。 |
| [tests/test_native_30m_reach_chain.py](../../../tests/test_native_30m_reach_chain.py) | X4 | S1/R4、S1/R6、S1/R9 | 切槽与已有水沙床变编排的同源绑定、局地产流注入和拒绝回归。 |
| [tests/test_native_30m_reach_selection.py](../../../tests/test_native_30m_reach_selection.py) | X4 | S1/R1、S1/R4、S1/R6、S1/R9 | 有限原生汇水和河段选取的合成及拒绝回归。 |
| [tests/test_native_30m_rejection_contract.py](../../../tests/test_native_30m_rejection_contract.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | 注入错误HRU面积和路由映射验证拒绝，核私有D8不调用粗规划与预算原因次序/未实现stage语义。 |
| [tests/test_native_30m_requested_selection.py](../../../tests/test_native_30m_requested_selection.py) | X4 | S1/R1、S1/R4、S1/R6、S1/R9 | 调用方指定出口的选区测试：保留完整候选普查与默认排序，非法/窗外/非候选/被拒出口拒绝，并核对选区规则身份与不支持语义拒绝。 |
| [tests/test_native_30m_resources.py](../../../tests/test_native_30m_resources.py) | X4 |  | 预算早拒、阶段RSS与历史高水位分离、采样失败不伪报0及超限通知测试。 |
| [tests/test_native_30m_review_rejection_cases.py](../../../tests/test_native_30m_review_rejection_cases.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | Review-round rejection cases: only gates that currently have no test of their own. Scope discipline … |
| [tests/test_native_30m_runoff.py](../../../tests/test_native_30m_runoff.py) | X4 | S1/R5、S2/G5 | 声明汇水土壤桶、时延设计Q与诊断Q语义分离及守恒回归。 |
| [tests/test_native_30m_saved_source.py](../../../tests/test_native_30m_saved_source.py) | X4 | S1/R1、S1/R9 | 保存装配seed/spacing/origin/SHA、缺receiver和错误拓扑拒绝、旧Q不复用及共用后续链测试。 |
| [tests/test_native_30m_scenario_cli.py](../../../tests/test_native_30m_scenario_cli.py) | X4 |  | 显式窗口/原点/步数/stride确实派发、默认1337不缩窗、未知场景和粗条件/跳冷读旋钮拒绝测试。 |
| [tests/test_native_30m_selection_contract.py](../../../tests/test_native_30m_selection_contract.py) | X4 |  | 实际规则默认值及候选表/掩码/标量重封篡改不能绕过重算的合成测试。 |
| [tests/test_native_30m_source.py](../../../tests/test_native_30m_source.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 原生页校验、装配、严格拓扑与非法输入拒绝回归。 |
| [tests/test_native_30m_sources.py](../../../tests/test_native_30m_sources.py) | X4 |  | 来源清单外部pin、原始页改变、source-only不读取旧结果与严格rerun拒损坏测试。 |
| [tests/test_native_30m_spatial_reference.py](../../../tests/test_native_30m_spatial_reference.py) | X4 |  | 独立图参照的逐源路径对照、未知锥、环及非法目标测试，正常水深解析/单调性/输水回代测试。 |
| [tests/test_native_30m_terminal_rule_acceptance.py](../../../tests/test_native_30m_terminal_rule_acceptance.py) | X4 |  | Helpers of the explicit terminal + actual-rule acceptance harness (no heavy compute). The harness li… |
| [tests/test_native_30m_unknown_cone_acceptance.py](../../../tests/test_native_30m_unknown_cone_acceptance.py) | X4 | S1/R1、S1/R9 | A3 acceptance: a declared unknown upstream spreads everywhere downstream and nowhere else. Fixture -… |
| [tests/test_native_hierarchical_delta.py](../../../tests/test_native_hierarchical_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_native_product_invariants.py](../../../tests/test_native_product_invariants.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_natural_delta_construction.py](../../../tests/test_natural_delta_construction.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Behavioral contracts of the prescribed natural construction geometry. |
| [tests/test_natural_delta_continuation.py](../../../tests/test_natural_delta_continuation.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_natural_delta_expanded_initial.py](../../../tests/test_natural_delta_expanded_initial.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_natural_delta_fv_water.py](../../../tests/test_natural_delta_fv_water.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_natural_delta_wide.py](../../../tests/test_natural_delta_wide.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_natural_outlet_certification.py](../../../tests/test_natural_outlet_certification.py) | X4 | S1/R2、S1/R3、S1/R7 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_delta.py](../../../tests/test_new_world_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_game_connectivity.py](../../../tests/test_new_world_game_connectivity.py) | X4 | S1/R2、S1/R4、S1/R6、S1/R7 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_game_delta.py](../../../tests/test_new_world_game_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_game_fine_lake.py](../../../tests/test_new_world_game_fine_lake.py) | X4 | S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_game_hydrology.py](../../../tests/test_new_world_game_hydrology.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_game_river_detail.py](../../../tests/test_new_world_game_river_detail.py) | X4 | S1/R6、S1/R7、S1/R8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_hydrology.py](../../../tests/test_new_world_hydrology.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_native_event.py](../../../tests/test_new_world_native_event.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_native_geometry.py](../../../tests/test_new_world_native_geometry.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_native_lowland.py](../../../tests/test_new_world_native_lowland.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_native_network.py](../../../tests/test_new_world_native_network.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_native_network_v2.py](../../../tests/test_new_world_native_network_v2.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_native_network_v3.py](../../../tests/test_new_world_native_network_v3.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_native_network_v4.py](../../../tests/test_new_world_native_network_v4.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_native_water.py](../../../tests/test_new_world_native_water.py) | X4 | S1/R1、S1/R2、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_river_acceptance.py](../../../tests/test_new_world_river_acceptance.py) | X4 | S1/R1、S1/R2、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_river_lifecycle.py](../../../tests/test_new_world_river_lifecycle.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_river_scene.py](../../../tests/test_new_world_river_scene.py) | X4 | S1/R1、S1/R2、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_rivers.py](../../../tests/test_new_world_rivers.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_sediment.py](../../../tests/test_new_world_sediment.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_stage1.py](../../../tests/test_new_world_stage1.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_stage1_derived_phases.py](../../../tests/test_new_world_stage1_derived_phases.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_new_world_stage1_flood_phases.py](../../../tests/test_new_world_stage1_flood_phases.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_ocean_island_consumers.py](../../../tests/test_ocean_island_consumers.py) | X4 | S1/R2、S2/G1、S2/G8 | Public CPU consumer behaviour, including subgrid area and finite topology. |
| [tests/test_ocean_islands.py](../../../tests/test_ocean_islands.py) | X4 | S1/R2、S2/G1、S2/G8 | Behavioural checks for bounded, frozen ocean landforms (CPU only). |
| [tests/test_physical_backend_window_budget.py](../../../tests/test_physical_backend_window_budget.py) | X4 | S1/R1、S1/R9、S2/G1 | TD后端显式窗口预算测试：超预算须带原因码拒绝，不得静默降采样或拆分；旧513用例仍受理。 |
| [tests/test_physical_generation.py](../../../tests/test_physical_generation.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_pillars3d_preview.py](../../../tests/test_pillars3d_preview.py) | X4 |  | The pillar-field true-3D review reader: pinned artifact, bounded routes, no rebuild. Two layers are … |
| [tests/test_plot_td_native_water_surface.py](../../../tests/test_plot_td_native_water_surface.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_prepare_basin_candidate_comparison.py](../../../tests/test_prepare_basin_candidate_comparison.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_prepare_highland_sources.py](../../../tests/test_prepare_highland_sources.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 源区声明支持、分配前预算、冷读重复来源逐份绑定、重封拒绝及原子提交失败/竞态对偶测试。 |
| [tests/test_prepare_hydrology_algorithm_release.py](../../../tests/test_prepare_hydrology_algorithm_release.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_prepare_hydrology_full_edges.py](../../../tests/test_prepare_hydrology_full_edges.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_prepare_hydrology_full_window_beds.py](../../../tests/test_prepare_hydrology_full_window_beds.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_prepare_hydrology_hybrid_lake.py](../../../tests/test_prepare_hydrology_hybrid_lake.py) | X4 | S1/R5、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_prepare_hydrology_projection_source.py](../../../tests/test_prepare_hydrology_projection_source.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_prepare_hydrology_v5_lake.py](../../../tests/test_prepare_hydrology_v5_lake.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_prepare_mountain_forms.py](../../../tests/test_prepare_mountain_forms.py) | X4 | S1/R1、S1/R2、S2/G1、S2/G2 | Consolidated tests.test_prepare_mountain_forms implementations; numeric expressions preserved. |
| [tests/test_prepare_river_reference_baseline.py](../../../tests/test_prepare_river_reference_baseline.py) | X4 |  | Reference observations remain bound to primary bytes and channel groups. |
| [tests/test_prepare_td_delta_sediment_candidate.py](../../../tests/test_prepare_td_delta_sediment_candidate.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_prepare_td_morphology_candidates.py](../../../tests/test_prepare_td_morphology_candidates.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_prepare_td_reference_routing.py](../../../tests/test_prepare_td_reference_routing.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_prepare_td_river_diagnostic.py](../../../tests/test_prepare_td_river_diagnostic.py) | X4 | S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_project_acceptance_render.py](../../../tests/test_project_acceptance_render.py) | X4 |  | Unit/geometry contracts for the read-only acceptance atlas. |
| [tests/test_publish_domain_bundle.py](../../../tests/test_publish_domain_bundle.py) | X4 |  | 现Python CLI默认有限产品消费与仅显式legacy-coarse执行历史粗链的分派，以及历史发布原断言的回归。 |
| [tests/test_publish_td_accepted_review.py](../../../tests/test_publish_td_accepted_review.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_read_domain_joint_candidate.py](../../../tests/test_read_domain_joint_candidate.py) | X4 |  | CPU-only unit coverage for the read-only joint consumer. |
| [tests/test_real_dem_flat_routing.py](../../../tests/test_real_dem_flat_routing.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_real_dem_flat_routing_export.py](../../../tests/test_real_dem_flat_routing_export.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_real_dem_outlet_classification.py](../../../tests/test_real_dem_outlet_classification.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_real_dem_outlet_classification_export.py](../../../tests/test_real_dem_outlet_classification_export.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_real_dem_rainfall_routing.py](../../../tests/test_real_dem_rainfall_routing.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_real_dem_rainfall_routing_export.py](../../../tests/test_real_dem_rainfall_routing_export.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_real_dem_review_export.py](../../../tests/test_real_dem_review_export.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_real_dem_river_3d_adapter_export.py](../../../tests/test_real_dem_river_3d_adapter_export.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_real_dem_surface_network.py](../../../tests/test_real_dem_surface_network.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_real_dem_tiled_network.py](../../../tests/test_real_dem_tiled_network.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_real_dem_tiled_network_export.py](../../../tests/test_real_dem_tiled_network_export.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_real_world_tributary.py](../../../tests/test_real_world_tributary.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Actual owning-core boundary selection, without invented receivers. |
| [tests/test_regional_forcing.py](../../../tests/test_regional_forcing.py) | X4 | S1/R5、S2/G3、S2/G4、S2/G5、S2/G14 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_regional_hydraulics_archive.py](../../../tests/test_regional_hydraulics_archive.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Cold evidence and exact discrete water-column geometry rejection tests. |
| [tests/test_regional_review.py](../../../tests/test_regional_review.py) | X4 | S1/R1、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_regional_review_diagnostics.py](../../../tests/test_regional_review_diagnostics.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_regional_review_landing.py](../../../tests/test_regional_review_landing.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_regional_source.py](../../../tests/test_regional_source.py) | X4 | S1/R1、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_regional_source_network.py](../../../tests/test_regional_source_network.py) | X4 | S1/R1、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_render_new_world_river_acceptance.py](../../../tests/test_render_new_world_river_acceptance.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_render_remote_sensing.py](../../../tests/test_render_remote_sensing.py) | X4 |  | Behaviour tests for the synthetic remote-sensing renderer. |
| [tests/test_review_large_td_confluence.py](../../../tests/test_review_large_td_confluence.py) | X4 |  | Small external-behavior checks for the large-map independent reviewer. |
| [tests/test_review_td_channel_geometry.py](../../../tests/test_review_td_channel_geometry.py) | X4 |  | Acceptance checks reject physically inconsistent saved geometry. |
| [tests/test_review_td_lowland_runoff.py](../../../tests/test_review_td_lowland_runoff.py) | X4 | S1/R5、S2/G5 | External checks for immutable-source lowland evidence and cold verification. |
| [tests/test_review_world_reaches.py](../../../tests/test_review_world_reaches.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 结构河段分类/断头拒绝/空通道原路径、分配前预算与NPY头、图例画布边界和PNG尺寸的合成对偶测试。 |
| [tests/test_river_branches_delta.py](../../../tests/test_river_branches_delta.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Focused checks for optional branch and delta geometry prototypes. |
| [tests/test_river_connectivity_audit.py](../../../tests/test_river_connectivity_audit.py) | X4 | S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_river_reference_conditions.py](../../../tests/test_river_reference_conditions.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_runoff.py](../../../tests/test_runoff.py) | X4 | S1/R5、S2/G5 | M4 tests.test_runoff; merged source labels precede preserved implementations. |
| [tests/test_saved_graph_lowland.py](../../../tests/test_saved_graph_lowland.py) | X4 | S1/R5、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_scan_40km_area.py](../../../tests/test_scan_40km_area.py) | X4 |  | 40km选区规则测试：按原因拒绝候选，不得因尺寸不匹配而静默选取更小盆地；含坐标单位误用的回归。 |
| [tests/test_seasonal_snow_ice.py](../../../tests/test_seasonal_snow_ice.py) | X4 | S1/R5、S2/G5、S2/G6、S2/G7、S2/G9 | Contract tests for the seasonal snow/SWE store (G7 first card). Every case is a small synthetic set … |
| [tests/test_shallow_water.py](../../../tests/test_shallow_water.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Consolidated test_shallow_water implementations; numeric expressions preserved. |
| [tests/test_single_domain_legacy_entrypoints.py](../../../tests/test_single_domain_legacy_entrypoints.py) | X4 | S1/R7、S1/R9 | Pinned explicit replay of retired v4/v8 shallow-water thin entrypoints. |
| [tests/test_single_domain_linear_storage_audit.py](../../../tests/test_single_domain_linear_storage_audit.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_single_domain_surface_archive.py](../../../tests/test_single_domain_surface_archive.py) | X4 | S1/R9 | Synthetic pinned IO fixtures; no hydrology execution or source generation. |
| [tests/test_single_domain_surface_consumer.py](../../../tests/test_single_domain_surface_consumer.py) | X4 | S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_single_domain_surface_geometry.py](../../../tests/test_single_domain_surface_geometry.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_skeleton_mountains.py](../../../tests/test_skeleton_mountains.py) | X4 | S1/R1、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_special_surface_preview.py](../../../tests/test_special_surface_preview.py) | X4 |  | The special-terrain review reader: pinned bundles, bounded routes, no geometry rebuild. Two layers a… |
| [tests/test_special_terrain.py](../../../tests/test_special_terrain.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S3/V1、S3/V2、S3/V3、S3/V5、S3/V6、S3/V7、S3/V8 | Consolidated test_special_terrain implementations; numeric expressions preserved. |
| [tests/test_srharness_mdbench_bridge.py](../../../tests/test_srharness_mdbench_bridge.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_srharness_windows_import.py](../../../tests/test_srharness_windows_import.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_stage1_native_checkpoint.py](../../../tests/test_stage1_native_checkpoint.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_stage1_saved_replay.py](../../../tests/test_stage1_saved_replay.py) | X4 |  | Standard-library tests for the saved-candidate replay harness. |
| [tests/test_surface_domain.py](../../../tests/test_surface_domain.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G1 | Consolidated test_surface_domain implementations; numeric expressions preserved. |
| [tests/test_surface_hydraulics.py](../../../tests/test_surface_hydraulics.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9 | 下游部分蓄水、已知溢流进入待定盆地、循环隔离及水量守恒测试。；Cross-tile local/spill edges, absolute coordinates, downstream basin … |
| [tests/test_surface_lake_network.py](../../../tests/test_surface_lake_network.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_surface_review_browser.py](../../../tests/test_surface_review_browser.py) | X4 |  | Installed Edge browser contract smoke test; no screenshots as assertions. |
| [tests/test_surface_review_export.py](../../../tests/test_surface_review_export.py) | X4 |  | Pinned sources, review gates and atomic versioned export contracts. |
| [tests/test_surface_river_diagnostics.py](../../../tests/test_surface_river_diagnostics.py) | X4 | S1/R1、S1/R9、S2/G1、S3/V8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_surface_river_transport.py](../../../tests/test_surface_river_transport.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_surface_rivers.py](../../../tests/test_surface_rivers.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_surface_routing_frame.py](../../../tests/test_surface_routing_frame.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_1024_source.py](../../../tests/test_td_1024_source.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_accepted_candidate_topology.py](../../../tests/test_td_accepted_candidate_topology.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_accepted_water_morphology.py](../../../tests/test_td_accepted_water_morphology.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G2、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_basin_breach.py](../../../tests/test_td_basin_breach.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S2/G2 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_basin_candidates.py](../../../tests/test_td_basin_candidates.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G2 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_basin_escape_plan.py](../../../tests/test_td_basin_escape_plan.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_basin_morphology.py](../../../tests/test_td_basin_morphology.py) | X4 | S1/R6、S1/R7、S1/R8、S2/G2 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_basin_overflow.py](../../../tests/test_td_basin_overflow.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_basin_overflow_implicit.py](../../../tests/test_td_basin_overflow_implicit.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_basin_overflow_radau.py](../../../tests/test_td_basin_overflow_radau.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_basin_reception.py](../../../tests/test_td_basin_reception.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_basin_review.py](../../../tests/test_td_basin_review.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G2 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_basin_runoff_exchange.py](../../../tests/test_td_basin_runoff_exchange.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | Independent runoff/surface/total water ledgers and cold strict-schema IO. |
| [tests/test_td_basin_source_hierarchy.py](../../../tests/test_td_basin_source_hierarchy.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_basin_spill_network.py](../../../tests/test_td_basin_spill_network.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_bounded_conditioning.py](../../../tests/test_td_bounded_conditioning.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G2 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_candidate_weather_jobs.py](../../../tests/test_td_candidate_weather_jobs.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_catchment_dynamic_review.py](../../../tests/test_td_catchment_dynamic_review.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_entry_pulse_incremental.py](../../../tests/test_td_entry_pulse_incremental.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_entry_pulse_propagation.py](../../../tests/test_td_entry_pulse_propagation.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_entry_shallow_water.py](../../../tests/test_td_entry_shallow_water.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_fine_bed_material.py](../../../tests/test_td_fine_bed_material.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_fine_bed_raster.py](../../../tests/test_td_fine_bed_raster.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_fine_bed_shards.py](../../../tests/test_td_fine_bed_shards.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_generated_publication.py](../../../tests/test_td_generated_publication.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_hour_pages_acceptance_io.py](../../../tests/test_td_hour_pages_acceptance_io.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_hour_pages_review.py](../../../tests/test_td_hour_pages_review.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_independent_forcing_reference.py](../../../tests/test_td_independent_forcing_reference.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_lake_entry_taper.py](../../../tests/test_td_lake_entry_taper.py) | X4 | S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_lake_interface_continuous_bed.py](../../../tests/test_td_lake_interface_continuous_bed.py) | X4 | S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_lake_outlet_forest.py](../../../tests/test_td_lake_outlet_forest.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_lake_spill_corridor.py](../../../tests/test_td_lake_spill_corridor.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_lake_spill_geometry.py](../../../tests/test_td_lake_spill_geometry.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_lithology_field.py](../../../tests/test_td_lithology_field.py) | X4 | S2/G2 | 岩性属性表与简化噪波分布的单元测试（unittest，无 pytest）。 范围：只测 td_lithology_field 的公开行为——属性表量级、同坐标稳定性、 乱序/分块一致、分布占比覆盖、非… |
| [tests/test_td_material_field.py](../../../tests/test_td_material_field.py) | X4 | S2/G2 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_morphology_candidates.py](../../../tests/test_td_morphology_candidates.py) | X4 | S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_native_channel_geometry.py](../../../tests/test_td_native_channel_geometry.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_native_channel_surface.py](../../../tests/test_td_native_channel_surface.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_native_channel_surface_review.py](../../../tests/test_td_native_channel_surface_review.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_native_channel_tiles.py](../../../tests/test_td_native_channel_tiles.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_native_channel_valley_paths.py](../../../tests/test_td_native_channel_valley_paths.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_native_domain_partition.py](../../../tests/test_td_native_domain_partition.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Independent tiny-grid checks for native partition topology and stage halos. |
| [tests/test_td_native_dynamic_scale_preflight.py](../../../tests/test_td_native_dynamic_scale_preflight.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Native v10 scale preflight uses actual driver limits without solver imports. |
| [tests/test_td_native_partition_transport.py](../../../tests/test_td_native_partition_transport.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R8、S1/R9、S2/G8、S2/G19 | Independent NumPy full-grid reference for bounded partition transport. |
| [tests/test_td_native_storm_forcing.py](../../../tests/test_td_native_storm_forcing.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_native_water_surface.py](../../../tests/test_td_native_water_surface.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_native_weather_storage_inputs.py](../../../tests/test_td_native_weather_storage_inputs.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_native_weather_storage_io.py](../../../tests/test_td_native_weather_storage_io.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_natural_bed_identity.py](../../../tests/test_td_natural_bed_identity.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_natural_outlet_certification.py](../../../tests/test_td_natural_outlet_certification.py) | X4 | S1/R2、S1/R3、S1/R6 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_natural_river_baseline.py](../../../tests/test_td_natural_river_baseline.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_natural_river_delivery.py](../../../tests/test_td_natural_river_delivery.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_natural_river_escape.py](../../../tests/test_td_natural_river_escape.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_natural_river_network.py](../../../tests/test_td_natural_river_network.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_noise_water_cycle.py](../../../tests/test_td_noise_water_cycle.py) | X4 | S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | Noise rainfall provenance remains auditable without hydrologic solvers. |
| [tests/test_td_ported_junction.py](../../../tests/test_td_ported_junction.py) | X4 | S1/R6、S3/V1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_ported_junction_saved_audit.py](../../../tests/test_td_ported_junction_saved_audit.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_ported_junction_saved_audit_v2.py](../../../tests/test_td_ported_junction_saved_audit_v2.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_ported_junction_saved_audit_v3.py](../../../tests/test_td_ported_junction_saved_audit_v3.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_ported_network_composition.py](../../../tests/test_td_ported_network_composition.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S3/V1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_ported_network_saved_audit.py](../../../tests/test_td_ported_network_saved_audit.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_radau_audit.py](../../../tests/test_td_radau_audit.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_river_bottom_budget.py](../../../tests/test_td_river_bottom_budget.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_river_resume.py](../../../tests/test_td_river_resume.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_runoff_exchange_audit.py](../../../tests/test_td_runoff_exchange_audit.py) | X4 |  | Saved independent accounts reject false storage and stage narratives. |
| [tests/test_td_shared_channel_fine.py](../../../tests/test_td_shared_channel_fine.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_shared_channel_fine_saved_audit.py](../../../tests/test_td_shared_channel_fine_saved_audit.py) | X4 |  | Tiny independent sampling/integration and sparse ownership regressions. |
| [tests/test_td_shared_port_channel.py](../../../tests/test_td_shared_port_channel.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_shared_port_channel_saved_audit.py](../../../tests/test_td_shared_port_channel_saved_audit.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_source_acceptance.py](../../../tests/test_td_source_acceptance.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Absolute world coordinates and conservative native-to-review sampling. |
| [tests/test_td_source_conforming_saved_audit_v3.py](../../../tests/test_td_source_conforming_saved_audit_v3.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_source_dem.py](../../../tests/test_td_source_dem.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_source_fine_terrain.py](../../../tests/test_td_source_fine_terrain.py) | X4 | S1/R1、S1/R2、S1/R6、S1/R7、S1/R9、S2/G1、S2/G3、S2/G4 | Behaviour tests for the 30 m base and the terrain-driven lake curves. These are external-behaviour t… |
| [tests/test_td_source_inventory.py](../../../tests/test_td_source_inventory.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_source_mosaic.py](../../../tests/test_td_source_mosaic.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_source_regions.py](../../../tests/test_td_source_regions.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | 跨存储块冷读、缓存命中、合成/求解失败隔离与真实求解的相邻扩展顺序一致性。；宏观/TD残差合成、双窗裁切一致、原源保留、海洋分量与非格线海岸采样测试。；Trusted overlap, source-… |
| [tests/test_td_source_terrain.py](../../../tests/test_td_source_terrain.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_spatial_consistency.py](../../../tests/test_td_spatial_consistency.py) | X4 |  | Spatial verification contracts, including refusal of fabricated late states. |
| [tests/test_td_stable_spill_paths.py](../../../tests/test_td_stable_spill_paths.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G2 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_stage4_falsification.py](../../../tests/test_td_stage4_falsification.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_stage_review.py](../../../tests/test_td_stage_review.py) | X4 |  | The review adapter preserves candidate identity and native arrays. |
| [tests/test_td_surface_reaches.py](../../../tests/test_td_surface_reaches.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_surface_river_edges.py](../../../tests/test_td_surface_river_edges.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_valley_global_tiled.py](../../../tests/test_td_valley_global_tiled.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_valley_scope_exclusion.py](../../../tests/test_td_valley_scope_exclusion.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_td_weather_checkpoint_recovery.py](../../../tests/test_td_weather_checkpoint_recovery.py) | X4 | S1/R9 | Read-only prefix recovery tests. |
| [tests/test_td_weather_wet_partition_causality.py](../../../tests/test_td_weather_wet_partition_causality.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Diagnostic regressions documenting original wet-bypass discontinuity. |
| [tests/test_tectonic.py](../../../tests/test_tectonic.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G2、S2/G3、S2/G4、S2/G8 | Consolidated tests.test_tectonic implementations; numeric expressions preserved. |
| [tests/test_terrain_artifacts.py](../../../tests/test_terrain_artifacts.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_terrain_map_style.py](../../../tests/test_terrain_map_style.py) | X4 |  | Contract tests for the shared terrain-map style layer. The style module is the only place that decid… |
| [tests/test_terrain_pipeline.py](../../../tests/test_terrain_pipeline.py) | X4 | S3/V1、S3/V8、S4/J2 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_tidal_creek_construction.py](../../../tests/test_tidal_creek_construction.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Actual tidal excavation, marine ownership and deterministic geometry. |
| [tests/test_underground_preview_bridge.py](../../../tests/test_underground_preview_bridge.py) | X4 |  | Local bridge guards without geometry recomputation. |
| [tests/test_underground_rivers.py](../../../tests/test_underground_rivers.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S3/V1、S3/V2、S3/V3、S3/V4、S3/V5、S3/V6、S3/V8 | Consolidated test_underground_rivers implementations; numeric expressions preserved. |
| [tests/test_upstream_sediment_connector.py](../../../tests/test_upstream_sediment_connector.py) | X4 |  | Lightweight acceptance checks for the saved connector artifact. |
| [tests/test_usgs_channel_reference.py](../../../tests/test_usgs_channel_reference.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_vdm_cuts.py](../../../tests/test_vdm_cuts.py) | X4 | S1/R4、S1/R6、S1/R9、S2/G2、S3/V1、S3/V5、S3/V8 | Consolidated test_vdm_cuts implementations; numeric expressions preserved. |
| [tests/test_vdm_diffusion.py](../../../tests/test_vdm_diffusion.py) | X4 | S1/R1、S1/R9、S2/G1、S3/V1、S3/V8 | Small CPU tests prove XYZ denoising/training and mask behavior, not artistic quality. |
| [tests/test_vdm_gallery_sections.py](../../../tests/test_vdm_gallery_sections.py) | X4 |  | Direction-aware chart sampling for cliff review curves. |
| [tests/test_verify_fluvial_channel_remobilization.py](../../../tests/test_verify_fluvial_channel_remobilization.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_verify_fluvial_distributary.py](../../../tests/test_verify_fluvial_distributary.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_verify_fluvial_morphodynamics.py](../../../tests/test_verify_fluvial_morphodynamics.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_verify_frozen_sources.py](../../../tests/test_verify_frozen_sources.py) | X4 |  | Positive and negative cases for tools/verify_frozen_sources.py (temp dirs only). |
| [tests/test_verify_large_world_erosion.py](../../../tests/test_verify_large_world_erosion.py) | X4 |  | 未耗尽材料的流量/硬度侵蚀响应、固体账和下一窗床面水力反馈测试。 |
| [tests/test_verify_native_30m_product.py](../../../tests/test_verify_native_30m_product.py) | X4 |  | 以假子进程输出验证验收报告正反例：审计/空间参照未过、数值或发布身份不一致、源码漂移须拒绝且不落盘，输出已存在或指向bundle内部时早拒。 |
| [tests/test_verify_native_ownership.py](../../../tests/test_verify_native_ownership.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_verify_river_dominant_saved_source.py](../../../tests/test_verify_river_dominant_saved_source.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_verify_td_partition_transport_saved_page.py](../../../tests/test_verify_td_partition_transport_saved_page.py) | X4 |  | Saved-page transport diagnostic rejects changed pins and false certification. |
| [tests/test_weathering_soil_inventory.py](../../../tests/test_weathering_soil_inventory.py) | X4 | S1/R5、S2/G5、S2/G6、S2/G7、S2/G9 | Conservative weathering inventory tests (unittest, no pytest). Scope: zero-weathering identity, cond… |
| [tests/test_web_preview_river_results.py](../../../tests/test_web_preview_river_results.py) | X4 | S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_world_acceptance_delta.py](../../../tests/test_world_acceptance_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | External contracts for same-world mouth selection and water/solid ledgers. |
| [tests/test_world_acceptance_processes.py](../../../tests/test_world_acceptance_processes.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G3、S2/G4、S2/G5、S2/G6、S2/G7、S2/G9、S2/G14 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_world_channel_dynamics.py](../../../tests/test_world_channel_dynamics.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | State inheritance and old-solver reuse in the nodal world reach adapter. |
| [tests/test_world_channel_graph.py](../../../tests/test_world_channel_graph.py) | X4 | S1/R4、S1/R6、S1/R9 | Behavior tests for world graph ownership, overlap and physical edge exchange. |
| [tests/test_world_demand_backend.py](../../../tests/test_world_demand_backend.py) | X4 | S1/R1、S1/R9、S2/G1 | CPU tests of fixed page planning, supervised failure, generation identity and source-page resume. |
| [tests/test_world_disk_catchment.py](../../../tests/test_world_disk_catchment.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 磁盘原床汇水与原生湖盆未知边界/泄漏计数对照。 |
| [tests/test_world_disk_water.py](../../../tests/test_world_disk_water.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G1 | 磁盘洪泛/平地与既有核逐格对照、双湖蓄溢及河槽行为、异常资源关闭测试。 |
| [tests/test_world_full_reach.py](../../../tests/test_world_full_reach.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Behaviour tests for the full real-world reach, the width law and the lake ledger. |
| [tests/test_world_grid_bed.py](../../../tests/test_world_grid_bed.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Behaviour tests for the full-grid dynamic bed: mapping, conservation, hydraulic feedback. The tests … |
| [tests/test_world_irregular_channels.py](../../../tests/test_world_irregular_channels.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_world_layout_conditioning.py](../../../tests/test_world_layout_conditioning.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4 | Contract tests for world-layout conditioning. CPU only: no model, no GPU. |
| [tests/test_world_layout_process.py](../../../tests/test_world_layout_process.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4 | CPU spawn大结果/失败/超时、显存不可测拒绝和seed一致性测试；不运行GPU。 |
| [tests/test_world_river_display.py](../../../tests/test_world_river_display.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_world_river_network_io.py](../../../tests/test_world_river_network_io.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G1 | 职责待人工核对；仅登记可确认的静态结构 |
| [tests/test_world_terrain_water_cli.py](../../../tests/test_world_terrain_water_cli.py) | X4 |  | 合成源页完整prepare/render/冷读和身份错配拒绝，源边带及滤波余量接线测试；不冒真实TD推理。 |
| [tests/test_world_water_formation.py](../../../tests/test_world_water_formation.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G1 | 双盆地水位及库存积分、真实解析床双湖溢流、全海/干地、待定状态多轮传播和岸缘保护测试。 |
| [tests/test_world_water_layout.py](../../../tests/test_world_water_layout.py) | X4 | S1/R1、S1/R2、S2/G1 | Contract tests for the public world water/land layout. These test *external* behaviour and the invar… |
| [tools/assemble_single_domain_stage_acceptance.py](../../../tools/assemble_single_domain_stage_acceptance.py) | X4 | S1/R9 | Publish one bounded stage verdict from externally pinned independent evidence. |
| [tools/audit_adaptive_mesh.py](../../../tools/audit_adaptive_mesh.py) | X4 | S1/R6、S1/R7、S1/R9、S3/V1 | Consolidated audit_adaptive_mesh implementations; numeric expressions preserved. |
| [tools/audit_basin_forcing.py](../../../tools/audit_basin_forcing.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | M4 tools.audit_basin_forcing; merged source labels precede preserved implementations. |
| [tools/audit_cross_region_consistency.py](../../../tools/audit_cross_region_consistency.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G1 | 在真实2049页上执行规范4.3跨区验收并写出报告、摘要与冷读脚本；报告数字全部由本次运行产出。 |
| [tools/audit_domain_candidate_bundle.py](../../../tools/audit_domain_candidate_bundle.py) | X4 |  | Cold-read accounting audit; never generates, solves, or republishes terrain. |
| [tools/audit_domain_coupled.py](../../../tools/audit_domain_coupled.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | Independent acceptance for the coupled water-sediment ledger. Read-only, and deliberately NOT built … |
| [tools/audit_domain_flow.py](../../../tools/audit_domain_flow.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | Independent acceptance for the domain water ledger (`metric_domain_flow`). Read-only and deliberatel… |
| [tools/audit_domain_sediment.py](../../../tools/audit_domain_sediment.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9 | Independent acceptance for the domain sediment ledger (`metric_domain_sediment`). Read-only, and del… |
| [tools/audit_hybrid_geometry.py](../../../tools/audit_hybrid_geometry.py) | X4 | S3/V1、S3/V2、S3/V3、S3/V5、S3/V6、S3/V8 | Consolidated audit_hybrid_geometry implementations; numeric expressions preserved. |
| [tools/audit_hybrid_hydraulics.py](../../../tools/audit_hybrid_hydraulics.py) | X4 | S1/R7、S3/V4、S3/V8 | Consolidated audit_hybrid_hydraulics implementations; numeric expressions preserved. |
| [tools/audit_hydrology_planning_naturalness.py](../../../tools/audit_hydrology_planning_naturalness.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Read-only coarse-plan topology metrics; no generation or TD certification. |
| [tools/audit_hydrovector_evidence.py](../../../tools/audit_hydrovector_evidence.py) | X4 |  | Read-only, standard-library vector evidence audit, not outlet certification. |
| [tools/audit_large_delta_tidal_v4.py](../../../tools/audit_large_delta_tidal_v4.py) | X4 | S1/R1、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Audit existing v4 product against the source without generating data. |
| [tools/audit_native_30m_bundle.py](../../../tools/audit_native_30m_bundle.py) | X4 |  | 独立进程安全解包原始trace，复算水、固体和逐节点Exner三账并执行失败硬门，不import被测水沙床变核。 |
| [tools/audit_native_30m_finite_domain.py](../../../tools/audit_native_30m_finite_domain.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | Independent auditor for the p5 finite real 30 m cross-window integration evidence. What this tool is… |
| [tools/audit_native_30m_hydrology.py](../../../tools/audit_native_30m_hydrology.py) | X4 |  | Independent cold audit of the native-30 m hydrology evidence. Independence rules (the whole reason t… |
| [tools/audit_native_30m_infinite_certification.py](../../../tools/audit_native_30m_infinite_certification.py) | X4 |  | Independent auditor for the native-30 m infinite-world certification window family (p8). What this t… |
| [tools/audit_native_30m_outlets.py](../../../tools/audit_native_30m_outlets.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | Independent audit of native 30 m outlet states; imports no judged kernel. Independence rules, all en… |
| [tools/audit_native_30m_spatial.py](../../../tools/audit_native_30m_spatial.py) | X4 | S1/R5、S2/G5 | 外部数值pin约束下安全读取保存数组，新进程独立核对全有限图Q、未知/节点归属和正常水深输水关系；不import被测图/水力核。 |
| [tools/audit_native_map_chains.py](../../../tools/audit_native_map_chains.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Audit five major known native mouth/pool chains with bounded equivalent beds. |
| [tools/audit_native_v4_corridors.py](../../../tools/audit_native_v4_corridors.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R9 | Read-only audit: v4 corridors re-evaluated with v3 pool levels, compared with v5 (event v3). |
| [tools/audit_natural_delta_continuation.py](../../../tools/audit_natural_delta_continuation.py) | X4 |  | Independent cold-read checks of a completed finite native continuation. |
| [tools/audit_natural_fv_coastal.py](../../../tools/audit_natural_fv_coastal.py) | X4 |  | Independent saved-array finite-bed/water audits and coastal comparison plots. |
| [tools/audit_natural_mouth_evidence.py](../../../tools/audit_natural_mouth_evidence.py) | X4 |  | Read original local evidence without treating a DEM trace as a certified mouth. |
| [tools/audit_network_accumulation.py](../../../tools/audit_network_accumulation.py) | X4 | S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | 冷读固定种子30m TD receiver，复用噪波雨量执行有限联合汇流；裁区独立逐源路径核算，保存已知Q与完整性掩码，不覆盖旧源。 |
| [tools/audit_new_world_game_connectivity.py](../../../tools/audit_new_world_game_connectivity.py) | X4 | S1/R2、S1/R4、S1/R6、S1/R7 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/audit_real_dem_tailwater.py](../../../tools/audit_real_dem_tailwater.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G1 | Real equal-height DEM path on the frozen bilateral storage-graph solver. This is a local engineered … |
| [tools/audit_river_backbone.py](../../../tools/audit_river_backbone.py) | X4 | S1/R9 | Independent cold-read audit of a prepared river-backbone product. What this tool is ----------------… |
| [tools/audit_river_connectivity.py](../../../tools/audit_river_connectivity.py) | X4 | S1/R6、S1/R7、S1/R9 | Audit flagged saved reaches without changing the input products. |
| [tools/audit_river_on_demand_consistency.py](../../../tools/audit_river_on_demand_consistency.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Read-only on-demand river consistency auditor. This is the referee for the infinite-world river work… |
| [tools/audit_river_reference_conditions.py](../../../tools/audit_river_reference_conditions.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Freeze source conditions and spatial roles without reading TD naturalness scores. |
| [tools/audit_saved_source_conforming_banks.py](../../../tools/audit_saved_source_conforming_banks.py) | X4 |  | Consolidated audit_saved_source_conforming_banks implementations; numeric expressions preserved. |
| [tools/audit_shallow_water.py](../../../tools/audit_shallow_water.py) | X4 | S1/R7、S1/R9 | Consolidated audit_shallow_water implementations; numeric expressions preserved. |
| [tools/audit_single_domain_fine_stage.py](../../../tools/audit_single_domain_fine_stage.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | Independent geometry, wet support and local budgets of pinned fine runs. |
| [tools/audit_single_domain_surface.py](../../../tools/audit_single_domain_surface.py) | X4 | S1/R5、S2/G5 | Independent raw-array audit of a pinned single-domain native surface package. |
| [tools/audit_special_terrain.py](../../../tools/audit_special_terrain.py) | X4 | S3/V1、S3/V2、S3/V3、S3/V5、S3/V6、S3/V7、S3/V8 | Consolidated audit_special_terrain implementations; numeric expressions preserved. |
| [tools/audit_stage_a_outlets.py](../../../tools/audit_stage_a_outlets.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | Independent checks and scientific map for the stage A outlet package. |
| [tools/audit_stage_b_flats.py](../../../tools/audit_stage_b_flats.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | Independent sparse connectivity and distance audit of the flat work graph. |
| [tools/audit_stage_c_water.py](../../../tools/audit_stage_c_water.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Independent volume reductions and sampled delayed-edge propagation checks. |
| [tools/audit_stage_e_geometry.py](../../../tools/audit_stage_e_geometry.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Independent shared-node, metric-coordinate and OBJ geometry audit. |
| [tools/audit_td_accepted_morphology.py](../../../tools/audit_td_accepted_morphology.py) | X4 | S1/R6、S1/R7、S1/R8 | Independent original-bed water/material reductions for accepted candidates. |
| [tools/audit_td_accepted_topology.py](../../../tools/audit_td_accepted_topology.py) | X4 |  | Independent threshold connectivity/capacity checks on a rebuilt derived bed. |
| [tools/audit_td_bank_carrier_compatibility.py](../../../tools/audit_td_bank_carrier_compatibility.py) | X4 |  | Saved-effects-only comparison of a frozen bank overlay and the prepare03 carrier. |
| [tools/audit_td_basin_generation.py](../../../tools/audit_td_basin_generation.py) | X4 |  | Independent D4 component, capacity and sediment reductions on pinned saved files. |
| [tools/audit_td_basin_spill_network.py](../../../tools/audit_td_basin_spill_network.py) | X4 |  | Independent physical-face, LCA, storage and reach-join audit of a pinned spill bundle. |
| [tools/audit_td_candidate_coupling.py](../../../tools/audit_td_candidate_coupling.py) | X4 |  | Independently inspect pinned candidate geometry, rebuilt graph and rain recoupling. |
| [tools/audit_td_candidate_weather.py](../../../tools/audit_td_candidate_weather.py) | X4 | S1/R4、S1/R6、S1/R9 | Independently inspect candidate-bed weather pages against unchanged source rain. |
| [tools/audit_td_catchment_dynamic_review.py](../../../tools/audit_td_catchment_dynamic_review.py) | X4 |  | Independently sum native leaf memberships and compare saved review pages. |
| [tools/audit_td_compiled_execution.py](../../../tools/audit_td_compiled_execution.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | Independent execution comparisons against unchanged v8 on bounded small fixtures. |
| [tools/audit_td_compiled_probes.py](../../../tools/audit_td_compiled_probes.py) | X4 |  | Independent saved-array execution equivalence on externally pinned v9 probes. |
| [tools/audit_td_conditioning_comparison.py](../../../tools/audit_td_conditioning_comparison.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G2、S2/G5 | Cold independent geometry, forcing and water-ledger conditioning audit. |
| [tools/audit_td_continuation_final.py](../../../tools/audit_td_continuation_final.py) | X4 | S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Explicit final v8 cold acceptance plus independent numerical reductions. |
| [tools/audit_td_continuation_spill_activity.py](../../../tools/audit_td_continuation_spill_activity.py) | X4 |  | Independent saved-frame wet connectivity and actual cross-catchment volume audit. |
| [tools/audit_td_entry_pulse_incremental.py](../../../tools/audit_td_entry_pulse_incremental.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Cold audit incremental fine commits, then reuse the original pulse audit. The output retains the old… |
| [tools/audit_td_entry_pulse_propagation.py](../../../tools/audit_td_entry_pulse_propagation.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Cold audit a dry-drain ordinary pulse without conflating lake boundary inflow. |
| [tools/audit_td_entry_pulse_review.py](../../../tools/audit_td_entry_pulse_review.py) | X4 |  | Decode every exported pulse array and compare with the immutable saved NPZ. |
| [tools/audit_td_entry_shallow_water.py](../../../tools/audit_td_entry_shallow_water.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Cold-read source, geometry, forcing and saved HLL lake-entry transactions. |
| [tools/audit_td_escape_reference.py](../../../tools/audit_td_escape_reference.py) | X4 |  | Independent original-grid priority flood for catchment potential escape planning. |
| [tools/audit_td_face_numerics.py](../../../tools/audit_td_face_numerics.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Compare D4 pair splitting against independent matrix/continuous ODE solutions. |
| [tools/audit_td_fine_bed_raster.py](../../../tools/audit_td_fine_bed_raster.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6 | Audit raw native DEM, original triangles and saved cut/export quadrature. |
| [tools/audit_td_fine_bed_shards.py](../../../tools/audit_td_fine_bed_shards.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6 | Independently audit append-only fine cells, native sources and material deltas. |
| [tools/audit_td_forcing_roundoff.py](../../../tools/audit_td_forcing_roundoff.py) | X4 | S1/R5、S2/G5 | Isolate forcing roundoff without transport against extended precision. |
| [tools/audit_td_full_refinement.py](../../../tools/audit_td_full_refinement.py) | X4 |  | Independent whole-domain refinement gates from pinned saved arrays, without solving. |
| [tools/audit_td_generated_rivers.py](../../../tools/audit_td_generated_rivers.py) | X4 | S1/R1、S1/R4、S1/R6、S1/R9 | Cold-read generated TD river artifacts; measure saved graphs and mesh beds. |
| [tools/audit_td_hotspot_exchange.py](../../../tools/audit_td_hotspot_exchange.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Controlled unforced multi-face ODE comparison on a pinned TD hotspot window. |
| [tools/audit_td_hour_pages_binary.py](../../../tools/audit_td_hour_pages_binary.py) | X4 |  | Decode saved review shards independently and compare original native inventories. |
| [tools/audit_td_hourly_seams.py](../../../tools/audit_td_hourly_seams.py) | X4 |  | Independent native saved-hour cut ledgers behind full continuation acceptance. |
| [tools/audit_td_lake_spill_corridors.py](../../../tools/audit_td_lake_spill_corridors.py) | X4 |  | Independent cold comparison against pinned parent graph; no generation. |
| [tools/audit_td_lake_spill_graph.py](../../../tools/audit_td_lake_spill_graph.py) | X4 |  | Independent cold audit of saved lake/spill graphs and their review artifacts. Accepted parent audits… |
| [tools/audit_td_material_field.py](../../../tools/audit_td_material_field.py) | X4 |  | Scalar independent global-lattice material checks on an externally pinned field. |
| [tools/audit_td_morphology_candidates.py](../../../tools/audit_td_morphology_candidates.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/audit_td_native_channel_geometry.py](../../../tools/audit_td_native_channel_geometry.py) | X4 | S1/R4、S1/R6、S1/R9 | Independently reduce original-grid nodes, actual face flow and candidate sections. |
| [tools/audit_td_native_channel_path_continuity.py](../../../tools/audit_td_native_channel_path_continuity.py) | X4 |  | Independent certification of saved render segments, never a generated bed. |
| [tools/audit_td_native_channel_tiles.py](../../../tools/audit_td_native_channel_tiles.py) | X4 | S1/R4、S1/R6、S1/R9 | Audit saved fine tiles against raw coarse elevations and bounded channel supports. |
| [tools/audit_td_native_channel_valley_paths.py](../../../tools/audit_td_native_channel_valley_paths.py) | X4 | S1/R4、S1/R6、S1/R9 | Check saved visual paths against raw original graph, stencils and basin owners. |
| [tools/audit_td_native_storm.py](../../../tools/audit_td_native_storm.py) | X4 |  | Independent bounded space/time quadrature of pinned native moving rainfall. |
| [tools/audit_td_native_water_surface.py](../../../tools/audit_td_native_water_surface.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Independently compare saved native water mesh, grid volume and OBJ to raw page. |
| [tools/audit_td_native_weather_final.py](../../../tools/audit_td_native_weather_final.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Bind independent spatial-weather reductions to a complete frozen execution and cold IO. |
| [tools/audit_td_native_weather_storage.py](../../../tools/audit_td_native_weather_storage.py) | X4 |  | Independently reduce saved spatial rainfall, hourly water and checkpoint chains. |
| [tools/audit_td_native_weather_v10.py](../../../tools/audit_td_native_weather_v10.py) | X4 |  | Independently reduce v10 spatial rain, compartment accounts and refinement. |
| [tools/audit_td_native_weather_v10_final.py](../../../tools/audit_td_native_weather_v10_final.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Bind complete v10 cold IO to independently reduced numerical evidence. |
| [tools/audit_td_natural_river_network.py](../../../tools/audit_td_natural_river_network.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Independent saved topology, shared-bed and material-ledger checks. |
| [tools/audit_td_original_bed_overflow.py](../../../tools/audit_td_original_bed_overflow.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Cold-read audit for the original-bed overflow diagnostic package. |
| [tools/audit_td_ported_junction.py](../../../tools/audit_td_ported_junction.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6 | Cold, independent topology/source audit of one saved ported junction. |
| [tools/audit_td_ported_junction_v2.py](../../../tools/audit_td_ported_junction_v2.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6 | Cold, independent topology/source audit of one saved ported junction. |
| [tools/audit_td_ported_junction_v3.py](../../../tools/audit_td_ported_junction_v3.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6 | Cold, independent topology/source audit of one saved ported junction. |
| [tools/audit_td_ported_network_composition_v3.py](../../../tools/audit_td_ported_network_composition_v3.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6 | Cold audit of atomic saved hubs and full-boundary composition evidence. |
| [tools/audit_td_radau_overflow.py](../../../tools/audit_td_radau_overflow.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Independent cold-read audit of pinned full-event Radau refinement. |
| [tools/audit_td_refinement_hotspots.py](../../../tools/audit_td_refinement_hotspots.py) | X4 |  | Locate saved full-domain refinement errors without advancing any solver. |
| [tools/audit_td_refinement_prefix.py](../../../tools/audit_td_refinement_prefix.py) | X4 |  | Pinned completed-hour diagnostics; never treat a prefix as full refinement. |
| [tools/audit_td_resolution_exchange.py](../../../tools/audit_td_resolution_exchange.py) | X4 | S1/R6、S1/R7、S1/R8 | Audit pinned M7 water/solid traces without invoking either solver. |
| [tools/audit_td_river_channel.py](../../../tools/audit_td_river_channel.py) | X4 | S1/R9 | Cold-audit M3 saved traces, source binding and resampling with solvers disabled. |
| [tools/audit_td_river_geometry_sediment.py](../../../tools/audit_td_river_geometry_sediment.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Cold M5/M6 audit: source, indexed geometry, Exner and independent step ledgers. |
| [tools/audit_td_river_lake_coupling.py](../../../tools/audit_td_river_lake_coupling.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Cold-audit saved M3/M4 geometry, source mappings, fluxes and real wet footprint. |
| [tools/audit_td_river_path_shape.py](../../../tools/audit_td_river_path_shape.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | Audit angular saved routing paths without generating or changing terrain. |
| [tools/audit_td_runoff_exchange.py](../../../tools/audit_td_runoff_exchange.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Independent saved-array water accounts and fixed-forcing temporal audit. |
| [tools/audit_td_shared_channel_fine.py](../../../tools/audit_td_shared_channel_fine.py) | X4 | S1/R4、S1/R6、S1/R9 | Streaming independent task15 native sampling and exact affine material audit. |
| [tools/audit_td_shared_port_channel.py](../../../tools/audit_td_shared_port_channel.py) | X4 | S1/R4、S1/R6、S1/R9 | Cold independent audit of bounded shared-midpoint saved channel geometry. |
| [tools/audit_td_simultaneous_transport.py](../../../tools/audit_td_simultaneous_transport.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Independent nonlinear ODE check of simultaneous SSP-RK2 transport. |
| [tools/audit_td_source_conforming_banks.py](../../../tools/audit_td_source_conforming_banks.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6 | Independent saved-only audit of source-relative banks and atomic replacements. |
| [tools/audit_td_source_conforming_banks_v3.py](../../../tools/audit_td_source_conforming_banks_v3.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6 | Independent v3 saved-only audit; no generator mathematics or global patching. |
| [tools/audit_td_storage_continuation.py](../../../tools/audit_td_storage_continuation.py) | X4 |  | Stream pinned hourly states, checkpoints and whole-period refinement evidence. |
| [tools/audit_td_storage_sensitivity.py](../../../tools/audit_td_storage_sensitivity.py) | X4 |  | Recompute saved TD refinement gates without advancing the simulation. |
| [tools/audit_td_surface_reaches.py](../../../tools/audit_td_surface_reaches.py) | X4 | S1/R4、S1/R6、S1/R9 | Independently check frozen TD candidate reaches and draw a scientific review figure. |
| [tools/audit_td_symmetric_forcing.py](../../../tools/audit_td_symmetric_forcing.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | Manufactured wet-domain solutions for versioned complete rain/transport solvers. |
| [tools/audit_td_threshold_pair.py](../../../tools/audit_td_threshold_pair.py) | X4 |  | Independent continuous threshold ODE checks for versioned TD face solvers. |
| [tools/audit_td_v10_temporal_refinement.py](../../../tools/audit_td_v10_temporal_refinement.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | Independent and cold-IO verification of separately resourced v10 time refinement. |
| [tools/audit_td_watershed_connectivity.py](../../../tools/audit_td_watershed_connectivity.py) | X4 |  | Independent saved-reference connectivity inspection, not a hydraulic audit. |
| [tools/audit_td_watershed_geometry.py](../../../tools/audit_td_watershed_geometry.py) | X4 | S1/R4、S1/R6、S1/R9 | Cold audit of pinned watershed candidates, without generators or water replay. |
| [tools/audit_td_weather_causality.py](../../../tools/audit_td_weather_causality.py) | X4 |  | Read pinned causal restart arrays and independently recompute their evidence. |
| [tools/audit_underground_rivers.py](../../../tools/audit_underground_rivers.py) | X4 | S1/R6、S3/V1、S3/V3、S3/V4、S3/V8 | Consolidated audit_underground_rivers implementations; numeric expressions preserved. |
| [tools/audit_usgs_channel_reference.py](../../../tools/audit_usgs_channel_reference.py) | X4 |  | Acquire bounded USGS channel measurements and audit explicit SI conversions. |
| [tools/audit_vdm_fault.py](../../../tools/audit_vdm_fault.py) | X4 | S2/G2、S3/V1、S3/V5、S3/V8 | Consolidated audit_vdm_fault implementations; numeric expressions preserved. |
| [tools/audit_world_domains.py](../../../tools/audit_world_domains.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 不import生产terrain_pipeline的独立结构审计，先验NPY头预算再读数组，复算D8/成员/未知/主干/候选ID并绑定support副本；同版双完整root跨窗比较，零可比不PASS。 |
| [tools/benchmark_height_budget.py](../../../tools/benchmark_height_budget.py) | X4 | S1/R1、S1/R9、S2/G1、S3/V8 | Run fixed real-model height-budget samples without changing generation defaults. |
| [tools/benchmark_height_budget_v5.py](../../../tools/benchmark_height_budget_v5.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4、S3/V8 | Fixed v5 input-compression screen and one held-out seed, without publication. |
| [tools/bootstrap_diffusion.py](../../../tools/bootstrap_diffusion.py) | X4 |  | Install the bundled Terrain Diffusion service under a Minecraft game directory. |
| [tools/build_fine_terrain.py](../../../tools/build_fine_terrain.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R9、S2/G1 | Build the 30 m river-network base and the terrain-driven lake curves. Stages are separated so the GP… |
| [tools/build_game_fine_lake.py](../../../tools/build_game_fine_lake.py) | X4 | S1/R6、S1/R7、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/build_local.py](../../../tools/build_local.py) | X4 |  | Offline build using read-only, already installed Java/Minecraft dependencies. All generated files st… |
| [tools/build_module_catalog.py](../../../tools/build_module_catalog.py) | X4 |  | 静态扫描一方源码、抽取说明/符号/本地导入并生成逐文件管理表；check检测台账漂移，不import算法。 |
| [tools/build_module_map.py](../../../tools/build_module_map.py) | X4 |  | 静态模块作用与引用图台账生成，UTF8-BOM解析和原字节SHA分离，解析相对/包导入；pin仅已扫描verification下界，不代替动态消费者或双pin核查。 |
| [tools/build_new_world_game_channel_bed.py](../../../tools/build_new_world_game_channel_bed.py) | X4 | S1/R4、S1/R6、S1/R9 | Build sparse shared-bed profiles from the saved 30 m refinement, without replay. |
| [tools/build_new_world_game_channel_bed_v2.py](../../../tools/build_new_world_game_channel_bed_v2.py) | X4 | S1/R4、S1/R6、S1/R9 | Build sparse shared-bed profiles from the saved 30 m refinement, without replay. |
| [tools/build_td_detail_terrain.py](../../../tools/build_td_detail_terrain.py) | X4 | S1/R1、S1/R2、S1/R4、S1/R6、S1/R9、S2/G1、S2/G3、S2/G4 | Embed Terrain Diffusion detail into one saved coarse reach window. Why --- The cross-region reach ru… |
| [tools/census_domain_closures.py](../../../tools/census_domain_closures.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Refusal-rate and performance census over the world-anchored closure tiles. Phase-1 completion asks f… |
| [tools/census_domain_coupled.py](../../../tools/census_domain_coupled.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Refusal-rate and cost census for the sediment and coupled ledgers. `census_domain_closures.py` surve… |
| [tools/check_context_usage.py](../../../tools/check_context_usage.py) | X4 |  | Read only token counters from the current session; never export conversation text. |
| [tools/check_native_products.py](../../../tools/check_native_products.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | Run native product invariants on routing and event products (read-only). |
| [tools/client_ui_probe.py](../../../tools/client_ui_probe.py) | X4 |  | Inspect and control only the Minecraft client recorded in verification/pid.txt. Coordinates for clic… |
| [tools/compare_hydrology_projection_naturalness.py](../../../tools/compare_hydrology_projection_naturalness.py) | X4 |  | Compare explicitly supplied projections against fixed same-source slots. |
| [tools/compare_natural_delta_fv_water.py](../../../tools/compare_natural_delta_fv_water.py) | X4 |  | Compare saved reference and accelerated fixed-bed FV experiments. |
| [tools/compare_natural_fv_growth_controls.py](../../../tools/compare_natural_fv_growth_controls.py) | X4 |  | Measure saved growth controls; differences are nonlinear responses, not tracers. |
| [tools/compare_td_river_shapes.py](../../../tools/compare_td_river_shapes.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9 | Compare saved river geometry at frozen baseline locations, one mesh at a time. |
| [tools/complete_game_hydro_lifecycle.py](../../../tools/complete_game_hydro_lifecycle.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/complete_td_entry_pulse_incremental.py](../../../tools/complete_td_entry_pulse_incremental.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Preflight/freeze or explicitly cold-run only the missing .005s pulse level. No --resume exists. Fail… |
| [tools/continue_natural_delta.py](../../../tools/continue_natural_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Continue actual native TD checkpoint with only a new finite source export. |
| [tools/continue_td_v10_refinement_after_baseline.py](../../../tools/continue_td_v10_refinement_after_baseline.py) | X4 |  | Wait for complete diagnostic baseline, then run one separately pinned refinement. |
| [tools/continue_td_weather_pipeline.py](../../../tools/continue_td_weather_pipeline.py) | X4 |  | Bounded serial river computation with frozen inputs and independent gates. |
| [tools/create_resources.py](../../../tools/create_resources.py) | X4 |  | Create original mod data, adapting vanilla biome schema for the exact target version. |
| [tools/delta_reference_metrics.py](../../../tools/delta_reference_metrics.py) | X4 |  | Dimensionless morphology metrics of delta reference images and of generated delta masks. runtime/ven… |
| [tools/diagnose_fv_coastal_front.py](../../../tools/diagnose_fv_coastal_front.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Replay a rejected sediment interval from archived live water and bed. |
| [tools/diagnose_fv_mpm_rejection.py](../../../tools/diagnose_fv_mpm_rejection.py) | X4 |  | Opt-in frozen-v3 MPM diagnostic; never runs the current algorithm implicitly. |
| [tools/diagnose_installation.py](../../../tools/diagnose_installation.py) | X4 |  | Read game metadata; write only an explicit report within this workspace. |
| [tools/diagnose_natural_delta_hydraulics.py](../../../tools/diagnose_natural_delta_hydraulics.py) | X4 | S1/R7、S1/R8 | Terminal diagnostic: fixed natural-delta bed, true source Q, no sediment. Paired warm checkpoint / h… |
| [tools/diagnose_natural_delta_spreading.py](../../../tools/diagnose_natural_delta_spreading.py) | X4 |  | Read-only cross-shore widths and boundary evidence from saved native states. |
| [tools/diagnose_natural_fv_morphology.py](../../../tools/diagnose_natural_fv_morphology.py) | X4 |  | Read completed FV growth evidence for spreading, inundation and edge truncation. |
| [tools/diagnose_natural_fv_residual_water.py](../../../tools/diagnose_natural_fv_residual_water.py) | X4 |  | Cold-read residual water, D4 spill barriers and last-chunk exchange. |
| [tools/diagnose_river_feasibility.py](../../../tools/diagnose_river_feasibility.py) | X4 | S1/R1、S1/R9、S2/G1、S3/V8 | Offline first-cause diagnostics and read-only coast candidate scan. |
| [tools/diagnose_single_domain_fine.py](../../../tools/diagnose_single_domain_fine.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Pin short independent fine-grid hydraulic experiments without stage acceptance. |
| [tools/diagnose_td_natural_river_escape.py](../../../tools/diagnose_td_natural_river_escape.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Read-only potential escape-chain screening for the frozen natural river basin. |
| [tools/diagnose_td_refinement_onset.py](../../../tools/diagnose_td_refinement_onset.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Locate earliest saved refinement differences and their upstream basin support. |
| [tools/diagnose_td_river_bottom_budget.py](../../../tools/diagnose_td_river_bottom_budget.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9 | Necessary transverse cut bounds on local fan4 vertices, without mesh or LP. |
| [tools/diagnose_td_source_bank_boundaries.py](../../../tools/diagnose_td_source_bank_boundaries.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6 | Saved-only whole-polynomial witnesses for source-bank boundary refusals. |
| [tools/diagnose_td_v10_saved_refinement.py](../../../tools/diagnose_td_v10_saved_refinement.py) | X4 |  | Pinned saved-page attribution of v10 temporal differences; no causal replay. |
| [tools/diagnose_td_valley_refusals.py](../../../tools/diagnose_td_valley_refusals.py) | X4 | S1/R4、S1/R6、S1/R9 | Classify refused TD valley edges without changing geometry or masks. |
| [tools/download_model.py](../../../tools/download_model.py) | X4 |  | Download pinned public weights with content validation; no model files outside workspace. |
| [tools/experiment_basin_forcing.py](../../../tools/experiment_basin_forcing.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | M4 tools.experiment_basin_forcing; merged source labels precede preserved implementations. |
| [tools/experiment_td_weather_causality.py](../../../tools/experiment_td_weather_causality.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Limited common-initial-state experiments; unchanged original v9 formulas. |
| [tools/export_hybrid_geometry_review.py](../../../tools/export_hybrid_geometry_review.py) | X4 |  | Consolidated export_hybrid_geometry_review implementations; numeric expressions preserved. |
| [tools/export_hybrid_hydraulics_review.py](../../../tools/export_hybrid_hydraulics_review.py) | X4 |  | Consolidated export_hybrid_hydraulics_review implementations; numeric expressions preserved. |
| [tools/export_metric_minecraft.py](../../../tools/export_metric_minecraft.py) | X4 | S1/R9、S3/V8、S4/J1 | Export a validated metric region for the read-only Minecraft adapter. |
| [tools/export_real_dem_review.py](../../../tools/export_real_dem_review.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Read-only review adapter for the fixed raw/flat/rainfall evidence chain. |
| [tools/export_regions.py](../../../tools/export_regions.py) | X4 |  | Prepare a bounded region rectangle with the same Java path used by the mod. |
| [tools/export_single_domain_adaptive_consumer.py](../../../tools/export_single_domain_adaptive_consumer.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S3/V1 | Export saved AMR inventories and identity-bound continuous water fans. |
| [tools/export_single_domain_fine_consumer.py](../../../tools/export_single_domain_fine_consumer.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Export saved fine stage data into a relocatable diagnostic consumer package. |
| [tools/export_td_candidate_bounded_review.py](../../../tools/export_td_candidate_bounded_review.py) | X4 |  | Explicit read-only candidate review export under a predeclared output budget. |
| [tools/export_td_conditioning_review.py](../../../tools/export_td_conditioning_review.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9 | Cold review data for bounded terrain changes, not invented river geometry. |
| [tools/export_td_entry_pulse_partial_review.py](../../../tools/export_td_entry_pulse_partial_review.py) | X4 |  | Pure-IO diagnostic export of the one recovered level, never formal acceptance. |
| [tools/export_td_entry_pulse_review.py](../../../tools/export_td_entry_pulse_review.py) | X4 |  | Lossless, bounded pure-IO review of an independently audited isolated pulse. |
| [tools/export_td_entry_shallow_water_review.py](../../../tools/export_td_entry_shallow_water_review.py) | X4 |  | Export an audited shallow-water event as one bounded front-end review JSON. This is a pure IO adapte… |
| [tools/export_td_natural_river_review.py](../../../tools/export_td_natural_river_review.py) | X4 | S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | Export pinned natural-network candidates without rebuilding or solving. |
| [tools/export_td_natural_river_review_v2.py](../../../tools/export_td_natural_river_review_v2.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | Enrich a pinned v1 review with saved discharge priors and the actual fine bed. |
| [tools/export_td_overflow_accounting.py](../../../tools/export_td_overflow_accounting.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Cold-read pinned original-bed events and export new accounting without solving. |
| [tools/export_td_ported_junction_review.py](../../../tools/export_td_ported_junction_review.py) | X4 |  | Pure IO review of td-ported-junction-v1; no generator/auditor/solver invocation. API: load_review(ju… |
| [tools/export_td_stable_basin_reception.py](../../../tools/export_td_stable_basin_reception.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Export audited Radau saved-face reception without advancing a solver. |
| [tools/export_td_v10_accepted_review.py](../../../tools/export_td_v10_accepted_review.py) | X4 | S1/R9 | Export native review using independently bound complete baseline acceptance. |
| [tools/export_td_watershed_inspection.py](../../../tools/export_td_watershed_inspection.py) | X4 |  | Read-only inspection of saved TD geometry; no routing or geometry generation. |
| [tools/export_vdm_cuts_review.py](../../../tools/export_vdm_cuts_review.py) | X4 |  | Consolidated export_vdm_cuts_review implementations; numeric expressions preserved. |
| [tools/finalize_td_generated_batch03.py](../../../tools/finalize_td_generated_batch03.py) | X4 |  | Finalize six completed saved reports after the batch03 manifest collision. |
| [tools/fluvial_delta_region_budget.py](../../../tools/fluvial_delta_region_budget.py) | X4 |  | Phase-wise sediment budget over fixed reference-defined delta regions. The public function :func:`su… |
| [tools/freeze_td_execution_code.py](../../../tools/freeze_td_execution_code.py) | X4 |  | Freeze the actual Numba storage kernel for an existing result package. This is metadata-only. It doe… |
| [tools/frozen_hybrid_geometry.py](../../../tools/frozen_hybrid_geometry.py) | X4 |  | 可信历史几何源码与数据根分离的显式复验适配；固定stage冷读有证据，全部旧下游链尚未完整迁移。 |
| [tools/frozen_hybrid_hydraulics.py](../../../tools/frozen_hybrid_hydraulics.py) | X4 |  | 显式字节校验的历史水力复演加载器；永不作为默认后端。 |
| [tools/frozen_vdm_fault.py](../../../tools/frozen_vdm_fault.py) | X4 |  | 验证断层v1可信归档并在私有命名空间显式复验完整旧生成和旧codec。 |
| [tools/generate_fictional_world_overview.py](../../../tools/generate_fictional_world_overview.py) | X4 | S1/R1、S1/R2、S1/R6、S2/G1 | CLI: build one finite fictional-world overview (three continents + islands). ``` python tools/genera… |
| [tools/generate_river_domains.py](../../../tools/generate_river_domains.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | CLI: generate on-demand river domain products for explicit world points. Contract 2.2 of `.scratch/r… |
| [tools/generate_td_1024_source.py](../../../tools/generate_td_1024_source.py) | X4 | S1/R1、S1/R9、S2/G1 | Plan or explicitly generate a real 1024-square physical TD source. |
| [tools/generate_td_noise_validation.py](../../../tools/generate_td_noise_validation.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4、S2/G5、S2/G14 | Generate isolated TD samples from meter-coordinate monthly noise climate. |
| [tools/generate_td_real_bio_validation.py](../../../tools/generate_td_real_bio_validation.py) | X4 | S1/R1、S1/R9、S2/G1 | Isolated GPU validation samples with pinned real BIO conditioning inputs. |
| [tools/generate_td_terrain_rivers.py](../../../tools/generate_td_terrain_rivers.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9 | Generate all six frozen full-resolution TD river candidates. |
| [tools/hybrid_cave_saved_audit.py](../../../tools/hybrid_cave_saved_audit.py) | X4 |  | Independent saved local solid, Boolean and air-path evidence primitives. |
| [tools/hybrid_exact_solid_saved_audit.py](../../../tools/hybrid_exact_solid_saved_audit.py) | X4 |  | Independent exact-zero saved binary64 solid validation; no mesh repairs. |
| [tools/hybrid_geometry_audit_base.py](../../../tools/hybrid_geometry_audit_base.py) | X4 |  | Independent original source/material/frame witnesses, without legacy audit entrypoints. |
| [tools/hybrid_geometry_face_checks.py](../../../tools/hybrid_geometry_face_checks.py) | X4 |  | Independent current face topology/role/boundary checks, no producer imports. |
| [tools/hybrid_geometry_records.py](../../../tools/hybrid_geometry_records.py) | X4 | S3/V1、S3/V2、S3/V3、S3/V5、S3/V6、S3/V8 | Consolidated hybrid_geometry_records implementations; numeric expressions preserved. |
| [tools/hybrid_geometry_saved_checks.py](../../../tools/hybrid_geometry_saved_checks.py) | X4 |  | Independent rational topology, native-prism and full-portal saved checks. |
| [tools/hybrid_hydraulics_records.py](../../../tools/hybrid_hydraulics_records.py) | X4 | S1/R7、S3/V1、S3/V2、S3/V3、S3/V4、S3/V5、S3/V6、S3/V8 | 当前水力准备辅助，独立于历史求解器入口；只做装配不做数值求解。 |
| [tools/hybrid_interval_winding_saved_audit.py](../../../tools/hybrid_interval_winding_saved_audit.py) | X4 |  | Certified occupancy of immutable binary64 meshes using mpmath intervals. |
| [tools/hybrid_saved_slice_geometry_adapter.py](../../../tools/hybrid_saved_slice_geometry_adapter.py) | X4 |  | Strict consumer for saved polygon slices, including owned holes. |
| [tools/hybrid_surface_resume_saved_audit.py](../../../tools/hybrid_surface_resume_saved_audit.py) | X4 |  | Explicit native identity binding and byte-bound validated solid views. |
| [tools/inspect_natural_delta_wide_result.py](../../../tools/inspect_natural_delta_wide_result.py) | X4 |  | Cold-read diagnostics for the independent wide-inlet short experiment. |
| [tools/inspect_natural_fv_growth.py](../../../tools/inspect_natural_fv_growth.py) | X4 |  | Independent chunk conservation checks and actual FV growth preview. |
| [tools/inspect_new_world_game_bed_pool.py](../../../tools/inspect_new_world_game_bed_pool.py) | X4 |  | Inspect a saved overflowing pool on its local original-grid support. |
| [tools/inspect_world_water_layout_page.py](../../../tools/inspect_world_water_layout_page.py) | X4 |  | 读取已保存TD页，比较实际高程与设计水陆分类及声明水位，生成统计和三栏图；不认证湖盆闭合或溢出口。 |
| [tools/measure_natural_delta_submergence.py](../../../tools/measure_natural_delta_submergence.py) | X4 |  | Measure actual saved FV water over above-datum deposited marine cells. |
| [tools/module_categories.py](../../../tools/module_categories.py) | X4 |  | Algorithm category lookup shared by build_module_map.py and build_module_catalog.py. A module's cate… |
| [tools/monitor_native_event_v2.py](../../../tools/monitor_native_event_v2.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/monitor_native_event_v3.py](../../../tools/monitor_native_event_v3.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/monitor_native_event_v3_reader.py](../../../tools/monitor_native_event_v3_reader.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/monitor_new_world_native_event.py](../../../tools/monitor_new_world_native_event.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/monitor_new_world_native_lowland.py](../../../tools/monitor_new_world_native_lowland.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/native_30m_bundle_reader.py](../../../tools/native_30m_bundle_reader.py) | X4 | S1/R4、S1/R6、S1/R9 | 严格冷读有限30m候选，核对文件与阶段身份、跨文件坐标/时段/事件绑定并复算诊断Q；不重放水沙数值核。 |
| [tools/native_30m_bundle_validation.py](../../../tools/native_30m_bundle_validation.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 冷读后重算拓扑/完整汇水和侧向归属，验证节点逐子步local Q及水力到水沙父子输入/库存与诊断事件绑定；不修复数据或更换算法。 |
| [tools/native_30m_compute_worker.py](../../../tools/native_30m_compute_worker.py) | X4 |  | 独立进程按固定来源参数调用已有河流链，只写候选与阶段资源报告；超RSS/时长停止，不发布最终目录。 |
| [tools/native_30m_declarations.py](../../../tools/native_30m_declarations.py) | X4 |  | 从保存数值推导正式有限包的时窗、原始节点供给、实际参数和能力边界，供冷读逐项绑定；不是独立物理认证。 |
| [tools/native_30m_diagnostic_only.py](../../../tools/native_30m_diagnostic_only.py) | X4 | S1/R1、S1/R9 | 单独保存和冷读声明裸雨换算诊断图，固定is_product=false并拒绝其冒充土壤桶/设计Q/水力水沙全链。 |
| [tools/native_30m_event_config.py](../../../tools/native_30m_event_config.py) | X4 | S1/R5、S2/G5 | 校验72项声明风暴与已有RunoffParameters覆盖，拒绝非法状态并归一为可复跑配置；不新增产流机制或标定。 |
| [tools/native_30m_graph_reference.py](../../../tools/native_30m_graph_reference.py) | X4 |  | 阿里云DeepSeek生成、输入门经审查的独立有限图Kahn遍历，核对已知Q和未知传播，不import生产累积核。 |
| [tools/native_30m_hydraulic_reference.py](../../../tools/native_30m_hydraulic_reference.py) | X4 |  | 阿里云DeepSeek生成的独立矩形Manning参照，用保存体积与几何核对水力状态，不import被测水力核。 |
| [tools/native_30m_query.py](../../../tools/native_30m_query.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 对已冷读有限河流包执行逐点和scope私有副本查询，整次拒绝未知/越界/语义不符及retained冒充自然出口，普查完整窗口。 |
| [tools/native_30m_resources.py](../../../tools/native_30m_resources.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 计算前预算与阶段内current RSS采样、采样失败及限额通知；不是OS硬内存配额或整个进程树总峰值。 |
| [tools/native_30m_saved_source.py](../../../tools/native_30m_saved_source.py) | X4 | S1/R1、S1/R5、S1/R9、S2/G5 | 读取外部SHA约束的保存装配，核seed/30m/原点/覆盖及receiver与严格D8一致；不复用旧Q，不冒充原始TD页真实性证明。 |
| [tools/native_30m_section_reference.py](../../../tools/native_30m_section_reference.py) | X4 |  | 阿里云DeepSeek生成的独立矩形Manning正常水深二分参照，不将正常流深冒充满岸或回水。 |
| [tools/native_30m_selection_contract.py](../../../tools/native_30m_selection_contract.py) | X4 | S1/R4、S1/R6、S1/R9 | 记录实际河段选择器默认规则，在冷读时重算完整候选表、选中掩码与标量，不改变原选区算法。 |
| [tools/native_30m_sources.py](../../../tools/native_30m_sources.py) | X4 |  | 仅来源重建清单的严格字段/参数校验、外部SHA及原始页pin验证；不消费旧派生目录。 |
| [tools/natural_fv_growth_interval.py](../../../tools/natural_fv_growth_interval.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Current v4 FV interval execution, explicit state protocol and carrier evidence. |
| [tools/natural_fv_growth_scheduler.py](../../../tools/natural_fv_growth_scheduler.py) | X4 | S1/R8、S1/R9、S2/G8、S2/G19 | FV区间trial调度、拒绝二分重试与完整chunk提交，核对库存/时长/源额度及失败最后检查点。 |
| [tools/natural_fv_growth_state_io.py](../../../tools/natural_fv_growth_state_io.py) | X4 |  | current FV检查点完整状态、参数绑定、源码闭包/外部SHA及载体合同校验；显式冷迁移保留旧来源。 |
| [tools/nbt_reader.py](../../../tools/nbt_reader.py) | X4 |  | Small read-only Java NBT decoder for inspecting level.dat metadata. |
| [tools/plot_td_accepted_morphology.py](../../../tools/plot_td_accepted_morphology.py) | X4 |  | Plot independently audited finite morphology candidates with original bed retained. |
| [tools/plot_td_continuation_review.py](../../../tools/plot_td_continuation_review.py) | X4 |  | Plot audited original-grid hourly water states without interpolation or simulation. |
| [tools/plot_td_native_channel_geometry.py](../../../tools/plot_td_native_channel_geometry.py) | X4 | S1/R4、S1/R6、S1/R9 | Plot saved candidate centerlines and sections beside actual native water samples. |
| [tools/plot_td_native_storm.py](../../../tools/plot_td_native_storm.py) | X4 |  | Plot independently audited native rainfall samples without interpolating weather. |
| [tools/plot_td_native_water_surface.py](../../../tools/plot_td_native_water_surface.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Plot a pinned saved native water snapshot, including wet cells absent from its mesh. |
| [tools/prepare_basin_candidate_comparison.py](../../../tools/prepare_basin_candidate_comparison.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Build a read-only basin treatment comparison for review interfaces. The command consumes an existing… |
| [tools/prepare_channel_vdm.py](../../../tools/prepare_channel_vdm.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9、S2/G2、S3/V1、S3/V5、S3/V8 | Consolidated prepare_channel_vdm implementations; numeric expressions preserved. |
| [tools/prepare_climate_matched_river_reference.py](../../../tools/prepare_climate_matched_river_reference.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Acquire fixed same-product SRTM sources and replay climate-matched real windows. |
| [tools/prepare_coast_bounded_delta.py](../../../tools/prepare_coast_bounded_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Construct one independent scene from the accepted frozen coastal inputs. |
| [tools/prepare_coastal_archipelago.py](../../../tools/prepare_coastal_archipelago.py) | X4 | S1/R1、S1/R2、S2/G1、S2/G8 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_coastal_detail.py](../../../tools/prepare_coastal_detail.py) | X4 | S1/R1、S1/R2、S2/G1、S2/G8 | Explicit CPU derivative of the user-approved old Coastal v1 saved TD. |
| [tools/prepare_coastal_terrain.py](../../../tools/prepare_coastal_terrain.py) | X4 | S1/R1、S1/R2、S2/G1、S2/G8 | Prepare the explicitly selected saved-TD coastal derivative on CPU. |
| [tools/prepare_environment_processes.py](../../../tools/prepare_environment_processes.py) | X4 | S1/R7、S1/R8、S1/R9、S2/G5、S2/G6 | Prepare or resume a finite environment process product from saved inputs. |
| [tools/prepare_environment_regional_hydraulics.py](../../../tools/prepare_environment_regional_hydraulics.py) | X4 | S1/R7、S1/R8、S1/R9、S2/G5、S2/G6 | Explicit prepare/advance/query of completed regional hydraulic products. |
| [tools/prepare_environment_snapshot.py](../../../tools/prepare_environment_snapshot.py) | X4 | S1/R5、S2/G5、S2/G6、S2/G7、S2/G9 | Export a completed seasonal-v2 process to the existing same-anchor world product. |
| [tools/prepare_environment_world.py](../../../tools/prepare_environment_world.py) | X4 | S1/R5、S2/G2、S2/G3、S2/G4、S2/G5、S2/G6、S2/G7、S2/G9、S2/G14 | 同坐标 30 m 环境联合产品的准备工具（真实生产者接线）。 在**同一组真实 TD 30 m 参考节点**上依次调用已有公开生产者，然后把结果装配成产品： 1. **elevation** — 从已… |
| [tools/prepare_finite_river_sample.py](../../../tools/prepare_finite_river_sample.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | 将已独立验收M1-M3数值和检查点晋升为稳定有限产品，绑定数据/源码身份并无覆盖发布；不重算物理或生成TD。 |
| [tools/prepare_height_budget_samples.py](../../../tools/prepare_height_budget_samples.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4、S3/V8、S4/J1 | Prepare checked, immutable metre-scale highland samples from real model output. |
| [tools/prepare_height_budget_v4.py](../../../tools/prepare_height_budget_v4.py) | X4 | S1/R1、S1/R9、S2/G1、S3/V8、S4/J1 | Finite v4 batch screening and all-or-nothing publication by seed. |
| [tools/prepare_highland_sources.py](../../../tools/prepare_highland_sources.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 显式D/H/E/V支持的页pin与NPY头预算、安全准备和完整冷读，暂存验证后Windows无覆盖提交；开发一致性与留出角色分开，不提供实际水文认证。 |
| [tools/prepare_hybrid_geometry.py](../../../tools/prepare_hybrid_geometry.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9、S3/V1、S3/V2、S3/V3、S3/V5、S3/V6、S3/V8 | 受控fresh Boolean到最新rational端口/审计/faces集成入口；现有run04严格拒绝，不能声明完整链通过。 |
| [tools/prepare_hybrid_hydraulics.py](../../../tools/prepare_hybrid_hydraulics.py) | X4 | S1/R7、S3/V1、S3/V2、S3/V3、S3/V4、S3/V5、S3/V6、S3/V8 | Consolidated prepare_hybrid_hydraulics implementations; numeric expressions preserved. |
| [tools/prepare_hydrology_algorithm_release.py](../../../tools/prepare_hydrology_algorithm_release.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | Freeze current hydrology evidence without upgrading local scope to release. |
| [tools/prepare_hydrology_domains.py](../../../tools/prepare_hydrology_domains.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1、S2/G5 | Explicit frozen-plan, seasonal and genuine TD detail preparation entry point. |
| [tools/prepare_hydrology_full_edges.py](../../../tools/prepare_hydrology_full_edges.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1、S2/G5 | Explicit serial complete coarse-edge preparation using canonical TD ownership. |
| [tools/prepare_hydrology_v5_lake.py](../../../tools/prepare_hydrology_v5_lake.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | Revalidate a saved v5 lake pair using immutable cached TD, without inference. |
| [tools/prepare_island_mountains.py](../../../tools/prepare_island_mountains.py) | X4 | S1/R1、S1/R2、S2/G1、S2/G8 | Prepare a CPU plan: exposed area strictly >100km2 by default. No TD/GPU. Width filtering is disabled… |
| [tools/prepare_large_world_river_geometry.py](../../../tools/prepare_large_world_river_geometry.py) | X4 | S1/R1、S1/R4、S1/R6、S1/R9 | 真实原生页与可选保存河网接声明年均径流、岩性和河槽宽深；新布局水体分类校验、保存产品与独立重绘。 |
| [tools/prepare_mountain_belts.py](../../../tools/prepare_mountain_belts.py) | X4 | S1/R1、S1/R2、S2/G1、S2/G2 | Prepare and export a finite, source-bound coarse world mountain product. |
| [tools/prepare_mountain_forms.py](../../../tools/prepare_mountain_forms.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | Consolidated tools.prepare_mountain_forms implementations; numeric expressions preserved. |
| [tools/prepare_native_delta_v2.py](../../../tools/prepare_native_delta_v2.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Construct one source-bound multi-junction delta on a 5 m depiction grid. |
| [tools/prepare_native_event_v2.py](../../../tools/prepare_native_event_v2.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_native_event_v3.py](../../../tools/prepare_native_event_v3.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_native_map_final.py](../../../tools/prepare_native_map_final.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Construct one source-bound multi-junction delta on a 5 m depiction grid. |
| [tools/prepare_native_map_geometry.py](../../../tools/prepare_native_map_geometry.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Read-only native event to bounded representative channel and delta. |
| [tools/prepare_native_map_window.py](../../../tools/prepare_native_map_window.py) | X4 | S1/R4、S1/R6、S1/R9 | Build a compact event-driven window channel and lake display geometry. |
| [tools/prepare_native_network.py](../../../tools/prepare_native_network.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_native_network_v2.py](../../../tools/prepare_native_network_v2.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_native_network_v3.py](../../../tools/prepare_native_network_v3.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_native_network_v4.py](../../../tools/prepare_native_network_v4.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_native_v4_corridors.py](../../../tools/prepare_native_v4_corridors.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_natural_delta_expanded_geometry.py](../../../tools/prepare_natural_delta_expanded_geometry.py) | X4 |  | Geometry only: enlarge a completed natural bed without hydraulic restart. |
| [tools/prepare_natural_delta_expanded_initial.py](../../../tools/prepare_natural_delta_expanded_initial.py) | X4 |  | Independent expanded initial state from frozen base and saved relative cuts. |
| [tools/prepare_natural_delta_wide_initial.py](../../../tools/prepare_natural_delta_wide_initial.py) | X4 |  | Explicit counterfactual wide incoming river on the unchanged marine base. |
| [tools/prepare_new_world_delta.py](../../../tools/prepare_new_world_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Build an explicit geometry and consume a single mouth's interval forcing. |
| [tools/prepare_new_world_game_delta_probe.py](../../../tools/prepare_new_world_game_delta_probe.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Audit a short real mouth reach; this is not a completed delta product. |
| [tools/prepare_new_world_game_delta_reach.py](../../../tools/prepare_new_world_game_delta_reach.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Build and audit one bounded subgrid spill-to-ocean reach from saved hydro. |
| [tools/prepare_new_world_game_delta_v1.py](../../../tools/prepare_new_world_game_delta_v1.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Prepare one representative 30-day subgrid game delta from frozen inputs. |
| [tools/prepare_new_world_game_hydrology.py](../../../tools/prepare_new_world_game_hydrology.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_new_world_hydrology.py](../../../tools/prepare_new_world_hydrology.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R9 | Prepare an immutable finite hydrology product. |
| [tools/prepare_new_world_native_water.py](../../../tools/prepare_new_world_native_water.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_new_world_river_acceptance.py](../../../tools/prepare_new_world_river_acceptance.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Run a bounded native event river diagnostic (CPU only). |
| [tools/prepare_new_world_river_scene.py](../../../tools/prepare_new_world_river_scene.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_new_world_rivers.py](../../../tools/prepare_new_world_rivers.py) | X4 | S1/R4、S1/R6、S1/R9 | Prepare a preliminary channel product from an explicit NPZ contract. |
| [tools/prepare_new_world_stage1.py](../../../tools/prepare_new_world_stage1.py) | X4 | S1/R4、S1/R6、S1/R9 | Preflight or publish an immutable native stage-1 product. |
| [tools/prepare_new_world_stage1_flood.py](../../../tools/prepare_new_world_stage1_flood.py) | X4 | S1/R9 | Report conservative mapping budgets for the experimental split flood. |
| [tools/prepare_ocean_islands.py](../../../tools/prepare_ocean_islands.py) | X4 | S1/R2、S2/G1、S2/G8 | Prepare, sample and export a provenance-bound CPU ocean-island experiment. |
| [tools/prepare_plate_source.py](../../../tools/prepare_plate_source.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G2、S2/G3、S2/G4 | Explicit experimental plate-conditioned TD entry; never the default source. |
| [tools/prepare_ridge_breakup.py](../../../tools/prepare_ridge_breakup.py) | X4 | S1/R1、S2/G1 | Produce fixed-window, source-bound ridge breakup comparisons. |
| [tools/prepare_river_backbone.py](../../../tools/prepare_river_backbone.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Prepare one river-backbone product from declared inputs, then audit it cold. This tool is **scheduli… |
| [tools/prepare_river_reference_baseline.py](../../../tools/prepare_river_reference_baseline.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Freeze existing primary measurements and bounded DEM/vector references. |
| [tools/prepare_saved_bed_grid.py](../../../tools/prepare_saved_bed_grid.py) | X4 | S1/R4、S1/R6、S1/R9 | Prepare the saved bed grid from the accepted shared-section report (20261016-01). |
| [tools/prepare_saved_river_supply.py](../../../tools/prepare_saved_river_supply.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_single_domain_consumer.py](../../../tools/prepare_single_domain_consumer.py) | X4 | S1/R9 | Export or serve a relocatable, fixed-pin read-only surface consumer package. |
| [tools/prepare_single_domain_surface.py](../../../tools/prepare_single_domain_surface.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Stream the fixed accepted native pages into an explicitly pinned surface archive. |
| [tools/prepare_source_conforming_banks.py](../../../tools/prepare_source_conforming_banks.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Consolidated prepare_source_conforming_banks implementations; numeric expressions preserved. |
| [tools/prepare_special_terrain.py](../../../tools/prepare_special_terrain.py) | X4 | S3/V1、S3/V2、S3/V3、S3/V5、S3/V6、S3/V7、S3/V8 | Consolidated prepare_special_terrain implementations; numeric expressions preserved. |
| [tools/prepare_stylized_river_mouth.py](../../../tools/prepare_stylized_river_mouth.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/prepare_td_conditioning_comparison.py](../../../tools/prepare_td_conditioning_comparison.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G2、S2/G5 | Independent bounded initial-terrain candidates and same-bed event comparison. |
| [tools/prepare_td_delta_sediment_candidate.py](../../../tools/prepare_td_delta_sediment_candidate.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Bind a fixed TD reach's saved solid export to an imposed local delta candidate. |
| [tools/prepare_td_entry_pulse_propagation.py](../../../tools/prepare_td_entry_pulse_propagation.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Pinned preparation and explicitly gated two-level isolated pulse execution. |
| [tools/prepare_td_entry_shallow_water.py](../../../tools/prepare_td_entry_shallow_water.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Prepare-only entry carrier, or explicitly run two events at two time limits. |
| [tools/prepare_td_fine_bed_raster.py](../../../tools/prepare_td_fine_bed_raster.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Pinned task06 and optional task09 to a bounded native-DEM bed raster. |
| [tools/prepare_td_fine_bed_shards.py](../../../tools/prepare_td_fine_bed_shards.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Retry only byte-budget-refused triangles in the fixed task09 fine package. |
| [tools/prepare_td_lake_entry_tapers.py](../../../tools/prepare_td_lake_entry_tapers.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R9 | Prepare pinned land-side lake-entry tapers without modifying parents. |
| [tools/prepare_td_lake_spill_corridors.py](../../../tools/prepare_td_lake_spill_corridors.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6 | Prepare pinned original-bed diagnostics, not a new or continuous channel. |
| [tools/prepare_td_lake_spill_graph.py](../../../tools/prepare_td_lake_spill_graph.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Saved-event main watershed review using retained lake and spill nodes. |
| [tools/prepare_td_morphology_candidates.py](../../../tools/prepare_td_morphology_candidates.py) | X4 | S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Prepare a pinned real-TD local candidate package for morphology review. |
| [tools/prepare_td_natural_delta.py](../../../tools/prepare_td_natural_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Prepare unchanged TD macro/residual coast and one imported river boundary. |
| [tools/prepare_td_natural_river_network.py](../../../tools/prepare_td_natural_river_network.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Prepare one pinned TD natural river candidate and a bounded fine-bed sample. |
| [tools/prepare_td_original_bed_overflow.py](../../../tools/prepare_td_original_bed_overflow.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Prepare pinned original-bed basin overflow diagnostics for the TD mountain. |
| [tools/prepare_td_ported_junction.py](../../../tools/prepare_td_ported_junction.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S3/V1 | Prepare one explicit real hub candidate or refusal from immutable 06/source-bank pins. |
| [tools/prepare_td_ported_network_composition.py](../../../tools/prepare_td_ported_network_composition.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S3/V1 | Save all bounded three-arm hub attempts and a candidate display composition. |
| [tools/prepare_td_radau_overflow.py](../../../tools/prepare_td_radau_overflow.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Pinned full-event adaptive refinement; frozen legacy results remain untouched. |
| [tools/prepare_td_reference_routing.py](../../../tools/prepare_td_reference_routing.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | Analyze one pinned M1/M2 graph without rerouting or rebuilding hydrology. Run with python -m tools.p… |
| [tools/prepare_td_resolution_exchange.py](../../../tools/prepare_td_resolution_exchange.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Run bounded 1D resolution comparison from a pinned TD M3 native product. |
| [tools/prepare_td_river_diagnostic.py](../../../tools/prepare_td_river_diagnostic.py) | X4 | S1/R1、S1/R5、S1/R6、S1/R7、S1/R9 | Prepare a pinned TD native-grid river diagnostic without channel hydraulics. |
| [tools/prepare_td_runoff_exchange.py](../../../tools/prepare_td_runoff_exchange.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | New spatial-rain and recession events, without re-running frozen overflow. |
| [tools/prepare_td_shaped_valley.py](../../../tools/prepare_td_shaped_valley.py) | X4 | S1/R4、S1/R6、S1/R9 | Save anchored real TD centerlines and the actual monotone bed they generate. |
| [tools/prepare_td_shared_channel_fine.py](../../../tools/prepare_td_shared_channel_fine.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | Prepare task15 tiles only from the fixed, independently passed task14 package. |
| [tools/prepare_td_shared_port_channel.py](../../../tools/prepare_td_shared_port_channel.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | Prepare a bounded branched shared-midpoint fragment without solver or fine cells. |
| [tools/prepare_td_stable_spill_paths.py](../../../tools/prepare_td_stable_spill_paths.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G2 | Cold-read the fixed audited reception and publish bounded, separate requests. |
| [tools/prepare_td_stage_review.py](../../../tools/prepare_td_stage_review.py) | X4 | S1/R4、S1/R6、S1/R9 | Pin completed stage reports for the existing read-only morphology API. |
| [tools/prepare_td_watershed_geometry.py](../../../tools/prepare_td_watershed_geometry.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Explicit parametric channel geometry on an accepted saved lake/spill graph. |
| [tools/prepare_tectonic.py](../../../tools/prepare_tectonic.py) | X4 | S1/R1、S1/R2、S2/G1、S2/G2 | Explicit CPU plan/generate entry point for an isolated tectonic background. |
| [tools/prepare_underground_rivers.py](../../../tools/prepare_underground_rivers.py) | X4 | S1/R6、S3/V1、S3/V2、S3/V3、S3/V4、S3/V5、S3/V6、S3/V8 | Consolidated prepare_underground_rivers implementations; numeric expressions preserved. |
| [tools/prepare_upstream_sediment_supply.py](../../../tools/prepare_upstream_sediment_supply.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Build the bounded saved-river sediment and mouth coupling case. |
| [tools/prepare_vdm_fault.py](../../../tools/prepare_vdm_fault.py) | X4 | S2/G2、S3/V1、S3/V5、S3/V8 | Consolidated prepare_vdm_fault implementations; numeric expressions preserved. |
| [tools/prepare_vdm_gallery.py](../../../tools/prepare_vdm_gallery.py) | X4 |  | Consolidated prepare_vdm_gallery implementations; numeric expressions preserved. |
| [tools/prepare_world_acceptance.py](../../../tools/prepare_world_acceptance.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Prepare the fixed 64km same-world review; GPU inference is explicit. |
| [tools/prepare_world_acceptance_processes.py](../../../tools/prepare_world_acceptance_processes.py) | X4 |  | Run same-source 90 m seasonal acceptance processes without a GPU. |
| [tools/prepare_world_domains.py](../../../tools/prepare_world_domains.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | 显式读取固定种子30m页来源并准备有界结构域候选，独立审计后在Windows不覆写提交；60秒审计限时与RSS软观测分开，不是默认无限世界入口。 |
| [tools/prepare_world_source_mosaic.py](../../../tools/prepare_world_source_mosaic.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Plan or serially generate the fixed 50 km source and terrain. |
| [tools/prepare_world_terrain.py](../../../tools/prepare_world_terrain.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Prepare a bounded unified raw-TD terrain product. |
| [tools/prepare_world_terrain_region.py](../../../tools/prepare_world_terrain_region.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G1 | Explicit finite-world demand planning, missing-page generation and joint terrain-water preparation; … |
| [tools/prepare_world_terrain_water.py](../../../tools/prepare_world_terrain_water.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G1 | 固定真实TD源先整体合成再裁有效内域，按海洋型/千湖型接水文，显式准备四阶段数组和图像。 |
| [tools/prepare_world_water_layout_page.py](../../../tools/prepare_world_water_layout_page.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4 | 准备12,288km可配置有限布局中的单张原生30m页，保存原生页、布局水体分类及来源；支持不推理dry-run。 |
| [tools/preview_delta_td_tide_wave.py](../../../tools/preview_delta_td_tide_wave.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Create a derived Terrain Diffusion delta/tide/wave preview. |
| [tools/preview_geography.py](../../../tools/preview_geography.py) | X4 | S1/R1、S1/R2、S2/G1、S2/G3、S2/G4 | Render the standalone geographic conditioning fields for inspection. |
| [tools/preview_natural_fv_landscape.py](../../../tools/preview_natural_fv_landscape.py) | X4 |  | Render actual FV growth in the unconstructed scene15 base; no simulation. |
| [tools/preview_river_experiments.py](../../../tools/preview_river_experiments.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Save isolated branch sensitivity and sediment transport comparisons. |
| [tools/preview_special_terrain.py](../../../tools/preview_special_terrain.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S3/V1、S3/V2、S3/V3、S3/V5、S3/V6、S3/V7、S3/V8 | Consolidated preview_special_terrain implementations; numeric expressions preserved. |
| [tools/preview_surface_rivers.py](../../../tools/preview_surface_rivers.py) | X4 |  | Reproducible offline surface-river preview; never edits source height caches. |
| [tools/probe_tuned_terrain.py](../../../tools/probe_tuned_terrain.py) | X4 | S1/R1、S1/R9、S2/G1 | Sample one real Terrain Diffusion profile without changing its output. |
| [tools/publish_domain_bundle.py](../../../tools/publish_domain_bundle.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | Python默认读取稳定有限河网产品并按世界点/物理时间查询真实Q和湖库存，显式checkpoint恢复发布独立结果；旧粗规划发布仅legacy-coarse，不自动回退或生成TD。 |
| [tools/publish_native_30m_bundle.py](../../../tools/publish_native_30m_bundle.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | 显式原生30m有限链CLI：构造候选、独立审计后原子发布、从源页重跑和只读摘要；不是阶段一认证或默认无限世界入口。 |
| [tools/publish_td_accepted_review.py](../../../tools/publish_td_accepted_review.py) | X4 | S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9 | Publish explicitly pinned accepted TD review or isolated geometry candidates. |
| [tools/query_environment_processes.py](../../../tools/query_environment_processes.py) | X4 |  | Read one cell of a completed environment process product without advancing it. |
| [tools/query_environment_world.py](../../../tools/query_environment_world.py) | X4 |  | 同坐标 30 m 环境联合产品的**只读**查询工具。 不生成、不推进、不改写产品：只从已保存的 ``.npz`` + ``.json`` 取字段。 某点缺少发布状态时按字段状态如实报告，不当零。 用… |
| [tools/query_large_world_river_geometry.py](../../../tools/query_large_world_river_geometry.py) | X4 | S1/R4、S1/R6、S1/R9 | 按原生世界坐标只读查询保存河槽，未知贡献与水域单独返回。 |
| [tools/query_river_backbone.py](../../../tools/query_river_backbone.py) | X4 | S1/R9 | Read-only query of one prepared river-backbone product. This tool answers questions from an already … |
| [tools/query_world_terrain_region.py](../../../tools/query_world_terrain_region.py) | X4 | S1/R1、S1/R2、S1/R4、S1/R6、S1/R9、S2/G1 | Read saved values, owning basin and spill links by world coordinates; verify ordinary or disk-tiled … |
| [tools/query_world_terrain_water.py](../../../tools/query_world_terrain_water.py) | X4 | S1/R4、S1/R6、S1/R9 | 校验已保存地形水体产品身份和形状后按原生世界坐标冷读；不启动生成。 |
| [tools/read_domain_joint_candidate.py](../../../tools/read_domain_joint_candidate.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Read saved bundle and R7 as a sidecar candidate; never generate or solve. |
| [tools/rebuild_td_accepted_candidate_topology.py](../../../tools/rebuild_td_accepted_candidate_topology.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9 | Explicit serial topology-only publication of an accepted derived TD source. |
| [tools/record_td_valley_scope_exclusion.py](../../../tools/record_td_valley_scope_exclusion.py) | X4 |  | Record an auditable scope exclusion for unresolved TD valley edges. |
| [tools/recover_natural_fv_growth_v3_prefix.py](../../../tools/recover_natural_fv_growth_v3_prefix.py) | X4 |  | Explicit frozen-v3 completed-prefix recovery; current runs use current checkpoints. |
| [tools/recover_td_entry_pulse_diagnostic.py](../../../tools/recover_td_entry_pulse_diagnostic.py) | X4 |  | Recover only complete saved pulse records after an interrupted host session. |
| [tools/refine_new_world_game_river_detail.py](../../../tools/refine_new_world_game_river_detail.py) | X4 | S1/R6、S1/R7、S1/R8 | Project the saved displayed receiver edges onto original control cells. |
| [tools/render_complete_delta.py](../../../tools/render_complete_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Render saved complete-delta arrays without adding schematic river lines. |
| [tools/render_delta_comparison.py](../../../tools/render_delta_comparison.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Compare verified saved delta rasters on one window and shared color scales. |
| [tools/render_delta_distributary_trial.py](../../../tools/render_delta_distributary_trial.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Render native saved distributary trials without inventing terrain or paths. |
| [tools/render_delta_forms.py](../../../tools/render_delta_forms.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Render hash-pinned native delta form comparisons without generated paths. |
| [tools/render_delta_mouth_16km.py](../../../tools/render_delta_mouth_16km.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Render saved river-mouth geography and the true-scale 4096 local experiment. |
| [tools/render_environment_world.py](../../../tools/render_environment_world.py) | X4 | S1/R5、S2/G5、S2/G6、S2/G7、S2/G9 | 同坐标联合产品的叠图 driver：真实接入 terrain_map_style，原生 30 m，不插值。 图上坐标轴是**真实的 30 m 世界米**（不是像素索引）；高程的色带与晕渲、比例尺均调 … |
| [tools/render_hydrology_domains.py](../../../tools/render_hydrology_domains.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | Render standalone scientific figures and a read-only HTML index; no JavaScript. |
| [tools/render_hydrology_large_preview.py](../../../tools/render_hydrology_large_preview.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9 | Read pinned canonical TD cores, route their real terrain, and render a standalone preview. |
| [tools/render_hydrology_seasonal.py](../../../tools/render_hydrology_seasonal.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | Render saved, cold-audited planning water accounts without simulation. |
| [tools/render_large_delta_tidal.py](../../../tools/render_large_delta_tidal.py) | X4 |  | Render saved tidal experiment against its frozen TD source. |
| [tools/render_large_delta_tidal_v4.py](../../../tools/render_large_delta_tidal_v4.py) | X4 |  | Render actual saved segmented-delta results; no terrain generation. |
| [tools/render_large_delta_trial.py](../../../tools/render_large_delta_trial.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Render saved large delta trial bed, water depth and sediment change maps. |
| [tools/render_native_delta_subgrid.py](../../../tools/render_native_delta_subgrid.py) | X4 | S1/R4、S1/R6、S1/R9 | Render a local one-metre representation of native derived sections. |
| [tools/render_native_delta_v2.py](../../../tools/render_native_delta_v2.py) | X4 | S1/R4、S1/R6、S1/R9 | Render saved hierarchical native delta and 50 km native network. |
| [tools/render_native_map.py](../../../tools/render_native_map.py) | X4 |  | Render the native-event 50 km terrain, lakes and channel portrayal. |
| [tools/render_native_map_final.py](../../../tools/render_native_map_final.py) | X4 | S1/R4、S1/R6、S1/R9 | Render saved hierarchical native delta and 50 km native network. |
| [tools/render_natural_delta_evolution.py](../../../tools/render_natural_delta_evolution.py) | X4 |  | Read-only natural delta evolution and measured phase-budget diagnostics. |
| [tools/render_natural_delta_growth.py](../../../tools/render_natural_delta_growth.py) | X4 |  | Read saved native beds and water separately; measure finite natural growth. |
| [tools/render_natural_fv_process.py](../../../tools/render_natural_fv_process.py) | X4 |  | Read-only natural native/FV process figures, including in-progress packets. |
| [tools/render_natural_mouth_primary_pages.py](../../../tools/render_natural_mouth_primary_pages.py) | X4 |  | Render pinned official PDF evidence; no georeferencing or inferred river geometry. |
| [tools/render_new_world_delta_subgrid.py](../../../tools/render_new_world_delta_subgrid.py) | X4 | S1/R4、S1/R6、S1/R9 | Render the saved bounded subgrid sections on a local 1 m portrayal grid. |
| [tools/render_new_world_game_delta.py](../../../tools/render_new_world_game_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Render actual 50 km TD terrain, day-30 lake state and representative delta. |
| [tools/render_project_acceptance.py](../../../tools/render_project_acceptance.py) | X4 | S1/R7、S1/R8、S1/R9、S2/G5、S2/G6 | Read-only, reproducible CPU atlas of saved stage 1/2 products. Run from the repository root with run… |
| [tools/render_remote_sensing.py](../../../tools/render_remote_sensing.py) | X4 |  | Synthetic orthophoto-style rendering of a saved world reach. What this is ------------ A **visualisa… |
| [tools/render_single_domain_adaptive_review.py](../../../tools/render_single_domain_adaptive_review.py) | X4 | S1/R6、S1/R7、S1/R9、S3/V1 | Render fixed saved AMR inventory maps and an actual junction fan patch. |
| [tools/render_td_basin_audit.py](../../../tools/render_td_basin_audit.py) | X4 |  | Static independent review figure from externally pinned, already solved TD arrays. |
| [tools/render_td_generated_rivers.py](../../../tools/render_td_generated_rivers.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9 | Render all saved native TD river domains and actual bed meshes, read-only. |
| [tools/render_terrain_map.py](../../../tools/render_terrain_map.py) | X4 | S3/V1、S3/V2、S3/V3、S3/V5、S3/V6、S3/V7、S3/V8 | Render an offline terrain map in remote-sensing or topographic style. Two declared cartographic styl… |
| [tools/render_tidal_delta.py](../../../tools/render_tidal_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Render saved tidal delta terrain and distinguish reachability from prism state. |
| [tools/render_world_acceptance.py](../../../tools/render_world_acceptance.py) | X4 | S1/R1、S1/R2、S1/R6、S1/R7、S1/R8、S1/R9、S2/G1、S2/G8、S2/G19 | Render a continuous same-world TD relief sheet and physical supporting maps. |
| [tools/render_world_river_acceptance.py](../../../tools/render_world_river_acceptance.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Render an authenticated new-world terrain baseline, without inferred water. |
| [tools/render_world_water_layout.py](../../../tools/render_world_water_layout.py) | X4 | S1/R1、S1/R2、S2/G1、S2/G3、S2/G4 | CPU生成有限世界水陆概览并报告采样水域比例；概览不是全幅30m生成。 |
| [tools/repair_td_generated_precision.py](../../../tools/repair_td_generated_precision.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9 | Repair observed TD support/closure refusals and reuse verified saved beds. |
| [tools/repair_td_river_shapes.py](../../../tools/repair_td_river_shapes.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R6、S1/R8、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | Run isolated physical river-shape repair against the six frozen TD sources. |
| [tools/replay_frozen_hybrid_hydraulics.py](../../../tools/replay_frozen_hybrid_hydraulics.py) | X4 |  | 显式历史水力复演CLI；当前生成不会选择它。 |
| [tools/replay_natural_fv_growth_legacy.py](../../../tools/replay_natural_fv_growth_legacy.py) | X4 |  | 验证可信FV原源码/模板归档，显式历史版本执行与原检查点读取；不进入默认当前生成路径。 |
| [tools/review_large_td_confluence.py](../../../tools/review_large_td_confluence.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | Regenerate and independently audit the pinned large TD routing candidate. |
| [tools/review_saved_bed_mouth.py](../../../tools/review_saved_bed_mouth.py) | X4 | S1/R4、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/review_td_channel_geometry.py](../../../tools/review_td_channel_geometry.py) | X4 | S1/R1、S1/R2、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1、S2/G3、S2/G4、S2/G5 | Cold numeric and visual acceptance for discharge-derived TD channel cuts. |
| [tools/review_td_lowland_runoff.py](../../../tools/review_td_lowland_runoff.py) | X4 | S1/R5、S2/G3、S2/G4、S2/G5、S2/G14 | Review lowland runoff on the immutable 03 native TD receiver graph. |
| [tools/review_td_single_source_river.py](../../../tools/review_td_single_source_river.py) | X4 | S1/R1、S1/R4、S1/R5、S1/R9、S2/G5 | Cold-read one finite TD river/lake case and write a bounded four-layer review. |
| [tools/review_world_reaches.py](../../../tools/review_world_reaches.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 先验JSON/支持预算/NPY头后读取已保存结构域，复用河段核并独立逐段核对承接与计数，输出全root/段分类和真实坐标图及纵剖；不做产流、蓄溢或自然域认证。 |
| [tools/run_complete_delta.py](../../../tools/run_complete_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Explicit entry point for the finite complete engineered delta. |
| [tools/run_cross_region_tributary.py](../../../tools/run_cross_region_tributary.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Run an explicit two-region trunk/tributary using existing geometry/water/sediment. |
| [tools/run_delta_distributary_trial.py](../../../tools/run_delta_distributary_trial.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Fixed finite-bed distributary trial; flux witnesses, not streamline inference. |
| [tools/run_delta_forms.py](../../../tools/run_delta_forms.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Single-factor finite engineering delta forms, with resumable cold checkpoints. |
| [tools/run_delta_fv_morphology.py](../../../tools/run_delta_fv_morphology.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Replay a finite 30 m single-feeder delta scenario without downstream paths. |
| [tools/run_delta_network_v1.py](../../../tools/run_delta_network_v1.py) | X4 | S1/R1、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Run the complex delta network v1 (site -> channel skeleton -> land) and draw the figures. runtime/ve… |
| [tools/run_delta_network_v2.py](../../../tools/run_delta_network_v2.py) | X4 | S1/R1、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Run the complex delta network v2 (site -> channel skeleton v2 -> channel-built land v2) and draw the… |
| [tools/run_delta_network_v3.py](../../../tools/run_delta_network_v3.py) | X4 | S1/R1、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Run the complex delta network v3 (site -> channel skeleton v3 -> channel-built land v3) and draw the… |
| [tools/run_delta_network_v4.py](../../../tools/run_delta_network_v4.py) | X4 | S1/R1、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Run the complex delta network v4 (site -> skeleton (= v3) -> channel-built land v3 -> v4 post-proces… |
| [tools/run_environment_coastal_delta.py](../../../tools/run_environment_coastal_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G5、S2/G6、S2/G8、S2/G19 | Run finite same-mouth delta/G8 from hash-validated regional export packets. |
| [tools/run_environment_delta_fv.py](../../../tools/run_environment_delta_fv.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Prepare, advance, query or verify an actual saved-mouth FV delta. |
| [tools/run_feedback_landward_case.py](../../../tools/run_feedback_landward_case.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Saved-source sequential channel feedback and connected coastal-land deposition. |
| [tools/run_finite_multiyear_source.py](../../../tools/run_finite_multiyear_source.py) | X4 | S1/R6、S1/R7、S1/R8 | Declared finite +9m geological scenario continued from a saved source year. Repeats the prescribed w… |
| [tools/run_floodplain_2d.py](../../../tools/run_floodplain_2d.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Two-dimensional floodplain / terminal-basin run fed by the solved reach. What this does ------------… |
| [tools/run_integrated_delta.py](../../../tools/run_integrated_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Runner for the integrated reduced channel-tree delta morphodynamics. See ``terrain_pipeline.surface_… |
| [tools/run_large_delta_trial.py](../../../tools/run_large_delta_trial.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | CPU-bounded 128x128 native-30m delta trial using the live FV water-sediment solver. |
| [tools/run_native_final_routing.py](../../../tools/run_native_final_routing.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | Run the frozen native flood in monitored, resumable worker phases. |
| [tools/run_natural_delta.py](../../../tools/run_natural_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Prepare or run a new finite natural-deposition delta mechanism experiment. |
| [tools/run_natural_delta_fv_coastal.py](../../../tools/run_natural_delta_fv_coastal.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Continue a saved FV interval with live water/finite-bed coastal transport. |
| [tools/run_natural_delta_fv_water.py](../../../tools/run_natural_delta_fv_water.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Fixed saved natural-delta bed: physical-time FV drainage, no sediment. Reuses the existing flat-cell… |
| [tools/run_natural_delta_wide.py](../../../tools/run_natural_delta_wide.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Independent wide-inlet finite-source counterfactual; never resumes old bed. |
| [tools/run_natural_fv_growth.py](../../../tools/run_natural_fv_growth.py) | X4 |  | 默认current-v4 FV命令薄入口；历史v1/v3执行不透明回退，须显式legacy。 |
| [tools/run_natural_fv_growth_v4.py](../../../tools/run_natural_fv_growth_v4.py) | X4 |  | Current v4 FV command; historical checkpoints require explicit migration/replay. |
| [tools/run_new_world_native_event.py](../../../tools/run_new_world_native_event.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/run_new_world_native_lowland.py](../../../tools/run_new_world_native_lowland.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/run_real_world_full_reach.py](../../../tools/run_real_world_full_reach.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G2、S2/G5 | Full seed-world reach: one real dendritic basin across four owning cores, ending in an endorheic lak… |
| [tools/run_real_world_tributary.py](../../../tools/run_real_world_tributary.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | Real seed-world tributary reach across an actual owning-core boundary. Uses existing coarse world te… |
| [tools/run_single_domain_adaptive_stage.py](../../../tools/run_single_domain_adaptive_stage.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S3/V1 | Predeclared finite-window adaptive leaf acceptance against frozen v7 evidence. |
| [tools/run_single_domain_fine_stage.py](../../../tools/run_single_domain_fine_stage.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Run fixed real-TD same-bed fine scenarios and predeclared refinement gates. |
| [tools/run_srharness_mdbench_bridge.py](../../../tools/run_srharness_mdbench_bridge.py) | X4 |  | SRHarness -> mdbench bridge tool. Subcommands: export - generate a synthetic problem task from a tas… |
| [tools/run_td_candidate_weather_jobs.py](../../../tools/run_td_candidate_weather_jobs.py) | X4 |  | Explicit serial candidate weather preparation/execution, dry by default. |
| [tools/run_td_coastal_delta.py](../../../tools/run_td_coastal_delta.py) | X4 | S1/R8、S1/R9、S2/G8、S2/G19 | Fixed independent coastal experiment and bit-exact cold replay entry point. |
| [tools/run_td_v10_temporal_refinement.py](../../../tools/run_td_v10_temporal_refinement.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | Prepare or explicitly execute a separate 0.625s v10 temporal refinement run. |
| [tools/scan_40km_area.py](../../../tools/scan_40km_area.py) | X4 | S1/R6、S1/R7、S1/R9 | 按声明规则在固定种子真实TD地形上选定40km@30m有界验收区：闭合、不触边、多窗口收敛；不挑选好看的位置。 |
| [tools/setup_diffusion.py](../../../tools/setup_diffusion.py) | X4 |  | Install a pinned upstream checkout, isolated runtime and model inside this workspace. |
| [tools/single_domain_legacy_entrypoints.py](../../../tools/single_domain_legacy_entrypoints.py) | X4 |  | 显式加载已退休浅水v4/v8薄入口及冻结依赖，不替换活跃模块或默认搜索路径。 |
| [tools/surface_execution_guards.py](../../../tools/surface_execution_guards.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S3/V1 | Guard saved surface readers against production construction and advance. |
| [tools/survey_global_river_climate.py](../../../tools/survey_global_river_climate.py) | X4 |  | Inventory Earth BIO coverage under an existing, unchanged river evaluation design. |
| [tools/td_entry_saved_audit.py](../../../tools/td_entry_saved_audit.py) | X4 |  | Raw saved DEM and first-order HLL transaction checks, without execution. |
| [tools/td_ported_junction_saved_audit.py](../../../tools/td_ported_junction_saved_audit.py) | X4 |  | Independent projected topology and full-function checks for saved junctions. |
| [tools/td_ported_junction_saved_audit_v2.py](../../../tools/td_ported_junction_saved_audit_v2.py) | X4 |  | V2 independent junction checks with conservative spatial edge candidates. |
| [tools/td_ported_junction_saved_audit_v3.py](../../../tools/td_ported_junction_saved_audit_v3.py) | X4 |  | V3 independent junction checks with exact support endpoint depth evaluation. |
| [tools/td_ported_network_saved_audit.py](../../../tools/td_ported_network_saved_audit.py) | X4 |  | Independent saved composition ports, selection conflicts and evidence graph. |
| [tools/td_shared_channel_fine_saved_audit.py](../../../tools/td_shared_channel_fine_saved_audit.py) | X4 |  | Independent native-source, affine-fan and streamed-grid audit primitives. |
| [tools/td_shared_port_channel_saved_audit.py](../../../tools/td_shared_port_channel_saved_audit.py) | X4 |  | Independent native affine-cut geometry and actual channel port evidence. |
| [tools/try_new_world_game_bed_reroutes.py](../../../tools/try_new_world_game_bed_reroutes.py) | X4 | S1/R6、S1/R7、S1/R8 | Try a wider existing basin-constrained search on independent over-cap paths. |
| [tools/update_native_event_channel.py](../../../tools/update_native_event_channel.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/verify_basin_storage.py](../../../tools/verify_basin_storage.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | M4 tools.verify_basin_storage; merged source labels precede preserved implementations. |
| [tools/verify_basin_storage_execution.py](../../../tools/verify_basin_storage_execution.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | M4 tools.verify_basin_storage_execution; merged source labels precede preserved implementations. |
| [tools/verify_biome_climate_distribution.py](../../../tools/verify_biome_climate_distribution.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9、S2/G1、S2/G3、S2/G4、S2/G5、S2/G14、S3/V8 | Read-only p5.3 distribution run: are all 16 biome palette slots reachable? Contract: ``.scratch/rive… |
| [tools/verify_channel_centerline.py](../../../tools/verify_channel_centerline.py) | X4 | S1/R4、S1/R6、S1/R9 | Fixed comparison of unsmoothed and constrained shared centerline geometry. |
| [tools/verify_channel_joint.py](../../../tools/verify_channel_joint.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Fixed static stage, bank inundation, and joint diagnostic verification. |
| [tools/verify_client_mixins.py](../../../tools/verify_client_mixins.py) | X4 |  | Transform both client Mixin targets with Fabric without starting Minecraft or a GUI. |
| [tools/verify_delta_fv_bar_recession.py](../../../tools/verify_delta_fv_bar_recession.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Bed-only hydraulic reinitialization at fixed low flow and low sea stage. |
| [tools/verify_delta_fv_coastal_controls.py](../../../tools/verify_delta_fv_coastal_controls.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Finite declared30m tide reversal and Airy wave-mobilization controls. |
| [tools/verify_delta_tides.py](../../../tools/verify_delta_tides.py) | X4 | S1/R7、S1/R9、S2/G19 | Validate real physical tidal periods independently of the annual river run. |
| [tools/verify_diffusion_server.py](../../../tools/verify_diffusion_server.py) | X4 |  | Exercise the packaged diffusion + generated VDM mod in a fresh isolated server, twice. |
| [tools/verify_dynamic_surface_hydraulics.py](../../../tools/verify_dynamic_surface_hydraulics.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | UTC evidence for the explicit storage graph, including failure prefixes. |
| [tools/verify_environment_processes.py](../../../tools/verify_environment_processes.py) | X4 | S2/G9、S2/G10、S2/G11、S2/G12、S2/G13、S2/G14、S2/G15、S2/G16、S2/G17、S2/G18、S2/G19、S2/G20 | Independent saved-TD finite-process acceptance; never creates terrain sources. |
| [tools/verify_environment_regional_hydraulics.py](../../../tools/verify_environment_regional_hydraulics.py) | X4 | S1/R7、S1/R8、S1/R9、S2/G5、S2/G6 | Focused real-source regional hydraulic handoff/cold-resume acceptance. |
| [tools/verify_environment_seasonal.py](../../../tools/verify_environment_seasonal.py) | X4 | S1/R7、S1/R8、S1/R9、S2/G2、S2/G3、S2/G4、S2/G5、S2/G6、S2/G14 | Independent bounded seasonal acceptance on saved seed20261020 TD and river graph. |
| [tools/verify_erosion3d.py](../../../tools/verify_erosion3d.py) | X4 |  | Compile and run only the pure-Java erosion3d verification with the pinned JDK 25. |
| [tools/verify_erosion_server.py](../../../tools/verify_erosion_server.py) | X4 |  | Test the 0.3.0 packaged mod against real server blocks, save and restart. |
| [tools/verify_fault_preview_frontend.py](../../../tools/verify_fault_preview_frontend.py) | X4 |  | Inspect actual saved fault geometry, orbit interaction and explicit preview. |
| [tools/verify_fine_domain_mosaic.py](../../../tools/verify_fine_domain_mosaic.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R9、S3/V1 | Pure IO stage-two saved AMR mosaic audit; no hydrology replay. |
| [tools/verify_first_install.py](../../../tools/verify_first_install.py) | X4 |  | Run the real first-install and cold-start probes against one prepared home. |
| [tools/verify_fluvial_channel_remobilization.py](../../../tools/verify_fluvial_channel_remobilization.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Bounded 5 m saved-TD remobilization experiment and independent cold audit. |
| [tools/verify_fluvial_delta.py](../../../tools/verify_fluvial_delta.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Finite saved-TD macrocoast experiment and independent archive audit. |
| [tools/verify_fluvial_distributary.py](../../../tools/verify_fluvial_distributary.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Saved-bed acceptance for finite source-cut distributary experiments. |
| [tools/verify_fluvial_morphodynamics.py](../../../tools/verify_fluvial_morphodynamics.py) | X4 | S1/R8、S2/G10 | Independent saved-array evidence for bounded two-dimensional delta evolution. |
| [tools/verify_frozen_sources.py](../../../tools/verify_frozen_sources.py) | X4 |  | Check the frozen evidence snapshot at legacy-code/frozen-sources-20261105/. Default run verifies eve… |
| [tools/verify_game_hydro_lifecycle.py](../../../tools/verify_game_hydro_lifecycle.py) | X4 | S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | Bounded actual-scenario durable routing evidence; no terrain regeneration. |
| [tools/verify_geography_inventory.py](../../../tools/verify_geography_inventory.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Fixed, read-only D:/geography inventory verification. |
| [tools/verify_lake_river_connector.py](../../../tools/verify_lake_river_connector.py) | X4 | S1/R6、S1/R7、S1/R9 | Fixed UTC connector evidence; CPU only, independent source sample, no default world. |
| [tools/verify_large_surface_network.py](../../../tools/verify_large_surface_network.py) | X4 | S1/R3、S1/R4、S1/R6、S1/R9 | Create and verify independent large static network evidence. |
| [tools/verify_large_world_erosion.py](../../../tools/verify_large_world_erosion.py) | X4 | S1/R6、S1/R7、S1/R8 | 独立两节点两小时未标定动态侵蚀对照，改变Q/硬度并报告有限库存和逐窗床变；不接大世界默认生成。 |
| [tools/verify_legacy_region.py](../../../tools/verify_legacy_region.py) | X4 | S1/R9、S4/J1 | Fixed GPU-free gate for the validated real legacy region pair. |
| [tools/verify_local_channel_sections.py](../../../tools/verify_local_channel_sections.py) | X4 | S1/R4、S1/R6、S1/R9 | Offline local-section geometry verification on synthetic and saved plans. |
| [tools/verify_managed_diffusion.py](../../../tools/verify_managed_diffusion.py) | X4 |  | Verify that the mod starts and stops its own model service without a manual server. |
| [tools/verify_metric_recipe_gate.py](../../../tools/verify_metric_recipe_gate.py) | X4 | S1/R1、S1/R9、S2/G1、S3/V8 | Recompute three real samples and compare physical-scale recipe candidates. |
| [tools/verify_metric_region.py](../../../tools/verify_metric_region.py) | X4 | S1/R1、S1/R9、S2/G1、S3/V8 | Fixed CPU-only real-sample comparison for metric regional processing. |
| [tools/verify_metric_rivers.py](../../../tools/verify_metric_rivers.py) | X4 | S1/R1、S1/R4、S1/R6、S1/R9、S2/G1、S3/V8 | Offline surface-river diagnostic on saved metre-scale v5 model windows. |
| [tools/verify_mountain_depression_geometry.py](../../../tools/verify_mountain_depression_geometry.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | CPU-only pinned dual-TD geometry, exact pool cascades and Chinese review. |
| [tools/verify_mountain_lake_coupling.py](../../../tools/verify_mountain_lake_coupling.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9、S2/G5 | Real-source geometry/coupling eligibility evidence, never fake lake acceptance. |
| [tools/verify_mountain_rainfall.py](../../../tools/verify_mountain_rainfall.py) | X4 | S1/R5、S2/G5 | CPU-only rainfall response on pinned, complete Terrain Diffusion mountains. |
| [tools/verify_mountain_round_acceptance.py](../../../tools/verify_mountain_round_acceptance.py) | X4 |  | One explicit CPU-only affected-module acceptance run with immutable evidence. |
| [tools/verify_mountain_runoff_routing.py](../../../tools/verify_mountain_runoff_routing.py) | X4 | S1/R5、S2/G5 | Fixed task36 sources, six conservative reach-routing cases, independent review. |
| [tools/verify_mountain_source_adapter.py](../../../tools/verify_mountain_source_adapter.py) | X4 | S1/R1、S1/R9、S2/G1 | Fixed CPU source verification; real inference requires explicit idle-GPU release. |
| [tools/verify_mountain_storm_100m.py](../../../tools/verify_mountain_storm_100m.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | Frozen 100m HRU paired hydrology and saved-data-only playback review. |
| [tools/verify_mountain_storm_60m.py](../../../tools/verify_mountain_storm_60m.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | Frozen 60m HRU paired hydrology and saved-data-only playback review. |
| [tools/verify_mountain_storm_forcing.py](../../../tools/verify_mountain_storm_forcing.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | Two opposite moving storms on frozen real four-pool lake/reach geometry. |
| [tools/verify_mountain_storm_hru_scale.py](../../../tools/verify_mountain_storm_hru_scale.py) | X4 | S2/G3、S2/G4、S2/G5、S2/G14 | Static HRU refinement experiment; no hydrology advancement or GPU work. |
| [tools/verify_mountain_storm_play_review.py](../../../tools/verify_mountain_storm_play_review.py) | X4 |  | New immutable saved-weather review with physical-time playback controls. |
| [tools/verify_mountain_storm_review.py](../../../tools/verify_mountain_storm_review.py) | X4 | S1/R6、S1/R7、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | Export and browser-audit saved weather/water only; never generate or advance. |
| [tools/verify_native_30m_product.py](../../../tools/verify_native_30m_product.py) | X4 |  | 对已发布有限30m产品聚合运行既有inspect/audit/point子进程，核对冷读身份、源码漂移与独立审计报告一致后原子写验收报告；本身不复算数值，不是阶段认证。 |
| [tools/verify_native_delta_v2.py](../../../tools/verify_native_delta_v2.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Check actual saved native hierarchical delta without replaying water. |
| [tools/verify_native_event_v3_reader.py](../../../tools/verify_native_event_v3_reader.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/verify_native_map_final.py](../../../tools/verify_native_map_final.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Check actual saved native hierarchical delta without replaying water. |
| [tools/verify_native_ownership.py](../../../tools/verify_native_ownership.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Audit frozen 30 m identity and replay actual event with owner transfers. |
| [tools/verify_new_world_game_hydrology.py](../../../tools/verify_new_world_game_hydrology.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/verify_new_world_native_event.py](../../../tools/verify_new_world_native_event.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/verify_new_world_native_lowland.py](../../../tools/verify_new_world_native_lowland.py) | X4 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [tools/verify_physical_generation.py](../../../tools/verify_physical_generation.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1、S2/G3、S2/G4、S4/J2 | CPU gates and explicit opt-in bounded TD preparation (never a fallback). |
| [tools/verify_pillars3d_browser.mjs](../../../tools/verify_pillars3d_browser.mjs) | X4 |  | Real-browser acceptance for the pillar-field true-3D workspace, without playwright. The repository's… |
| [tools/verify_real_dem_flat_routing.py](../../../tools/verify_real_dem_flat_routing.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9 | Flat routing evidence export with full frozen A/B proofs, not lake certification. Global height, mas… |
| [tools/verify_real_dem_outlet_classification.py](../../../tools/verify_real_dem_outlet_classification.py) | X4 | S1/R1、S1/R2、S1/R9、S2/G1 | Atomic stage A export and repeatable, read-only cold verification. Validation may reconstruct static… |
| [tools/verify_real_dem_rainfall_routing.py](../../../tools/verify_real_dem_rainfall_routing.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G5 | Three fixed illustrative rainfall scenarios with equation-only cold replay. Engineering boundary dis… |
| [tools/verify_real_dem_surface_network.py](../../../tools/verify_real_dem_surface_network.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | Build a review-only network from the local real DEM candidate. |
| [tools/verify_real_dem_tiled_network.py](../../../tools/verify_real_dem_tiled_network.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1 | Strict irregular-graph tiled traversal comparison. Cold verification may reconstruct static evidence… |
| [tools/verify_regional_forcing.py](../../../tools/verify_regional_forcing.py) | X4 | S1/R1、S1/R5、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | Serial full-grid forcing preparation; mmap output, no surface simulation. |
| [tools/verify_regional_review.py](../../../tools/verify_regional_review.py) | X4 | S1/R1、S1/R9 | Read-only regional static export and actual Edge browser acceptance. |
| [tools/verify_regional_review_diagnostics.py](../../../tools/verify_regional_review_diagnostics.py) | X4 |  | Read-only compact diagnostic charts from externally pinned saved summaries. |
| [tools/verify_regional_review_dry_saved.py](../../../tools/verify_regional_review_dry_saved.py) | X4 | S1/R1、S1/R6、S1/R7、S1/R8、S1/R9 | Read-only real dry-state handoff; never advances surface or invents water. |
| [tools/verify_regional_review_landing.py](../../../tools/verify_regional_review_landing.py) | X4 |  | One lightweight landing for explicitly pinned accepted regional review artifacts. |
| [tools/verify_regional_review_saved.py](../../../tools/verify_regional_review_saved.py) | X4 | S1/R1、S1/R9 | One read-only review entry for externally pinned B case/display exports. |
| [tools/verify_regional_round_acceptance.py](../../../tools/verify_regional_round_acceptance.py) | X4 | S1/R5、S2/G5 | Explicit frozen regional regression plus pinned static artifact integrity. |
| [tools/verify_regional_source.py](../../../tools/verify_regional_source.py) | X4 | S1/R1、S1/R9 | Prepare the fixed full regional source, with no GPU or surface solver. |
| [tools/verify_regional_source_network.py](../../../tools/verify_regional_source_network.py) | X4 | S1/R1、S1/R9 | Stable full-region static channel polylines; not dynamic surface fluxes. |
| [tools/verify_regions.py](../../../tools/verify_regions.py) | X4 |  | Focused region checks without the broad preset/world verification sweep. |
| [tools/verify_review_navigation_camera.py](../../../tools/verify_review_navigation_camera.py) | X4 |  | Check three-category navigation and matching orbit gestures in both viewers. |
| [tools/verify_river_bed_ribbons.py](../../../tools/verify_river_bed_ribbons.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R9、S2/G1、S3/V1、S3/V3、S3/V4、S3/V8 | Consolidated verify_river_bed_ribbons implementations; numeric expressions preserved. |
| [tools/verify_river_dominant_saved_source.py](../../../tools/verify_river_dominant_saved_source.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Cold independent verification of a saved river-dominant run against its source. |
| [tools/verify_saved_surface_frontend.py](../../../tools/verify_saved_surface_frontend.py) | X4 |  | Exercise pinned saved geometry in the actual local review frontend. |
| [tools/verify_server.py](../../../tools/verify_server.py) | X4 |  | Run the packaged mod in an isolated world, then reopen it to check persistence. |
| [tools/verify_service_required.py](../../../tools/verify_service_required.py) | X4 |  | A global saved world must fail clearly when its model service is absent. |
| [tools/verify_single_domain_fine_cold_io.py](../../../tools/verify_single_domain_fine_cold_io.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Cold-read saved fine scenarios with every production constructor disabled. |
| [tools/verify_special_surface_browser.mjs](../../../tools/verify_special_surface_browser.mjs) | X4 |  | Real-browser acceptance for the special-terrain 3D workspace, without playwright. The repository's o… |
| [tools/verify_stage1_saved_replay.py](../../../tools/verify_stage1_saved_replay.py) | X4 |  | Replay saved candidate products only; never generate terrain or solve transport. Run with runtime/ve… |
| [tools/verify_surface_adaptive_cold_io.py](../../../tools/verify_surface_adaptive_cold_io.py) | X4 | S1/R5、S1/R6、S1/R7、S2/G5、S3/V1 | Cold-read saved adaptive evidence with production construction and advance guarded. |
| [tools/verify_surface_centerline_prepare.py](../../../tools/verify_surface_centerline_prepare.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Fixed CPU-only implementation verification; not independent acceptance. |
| [tools/verify_surface_coast_drop.py](../../../tools/verify_surface_coast_drop.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | UTC fixed evidence: actual saved river endpoint plus explicit synthetic coast. |
| [tools/verify_surface_cross_domain.py](../../../tools/verify_surface_cross_domain.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Generate a small, read-only cross-domain seam audit report. |
| [tools/verify_surface_cross_domain_td.py](../../../tools/verify_surface_cross_domain_td.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Cold-read a frozen TD partition and publish an externally hashed audit. |
| [tools/verify_surface_development_readiness.py](../../../tools/verify_surface_development_readiness.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Verify the fixed, saved surface evidence without generating terrain. |
| [tools/verify_surface_domain_mosaic.py](../../../tools/verify_surface_domain_mosaic.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Verify the fixed saved two-domain dry extension and retain new UTC evidence. |
| [tools/verify_surface_domain_prepare.py](../../../tools/verify_surface_domain_prepare.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Fixed CPU-only complete-domain scenarios; retain success and failure UTC evidence. |
| [tools/verify_surface_dynamic_prepare.py](../../../tools/verify_surface_dynamic_prepare.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Fixed saved-source dynamic adapter scenarios, actual UTC evidence and static reload. |
| [tools/verify_surface_engineering_prepare.py](../../../tools/verify_surface_engineering_prepare.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Reproduce the fixed accepted two-domain engineering bundle. |
| [tools/verify_surface_fine_mosaic.py](../../../tools/verify_surface_fine_mosaic.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Fixed engineering cases; retain original domain gap, never claim full mosaic. |
| [tools/verify_surface_hydraulics.py](../../../tools/verify_surface_hydraulics.py) | X4 | S1/R1、S1/R6、S1/R7、S1/R8、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | Consolidated verify_surface_hydraulics implementations; numeric expressions preserved. |
| [tools/verify_surface_integrated_acceptance.py](../../../tools/verify_surface_integrated_acceptance.py) | X4 |  | Read-only frozen evidence gates, with opt-in joint unittest and browser audits. |
| [tools/verify_surface_lake_network.py](../../../tools/verify_surface_lake_network.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R9 | Fixed synthetic joint scenarios, real downstream gates, no publication. |
| [tools/verify_surface_land_coverage.py](../../../tools/verify_surface_land_coverage.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Freeze and independently account the fixed clamped land coverage artifact. |
| [tools/verify_surface_multidomain_dynamic.py](../../../tools/verify_surface_multidomain_dynamic.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Fixed two-domain forest verification against the unchanged saved evaluation. |
| [tools/verify_surface_network_consumer.py](../../../tools/verify_surface_network_consumer.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Fixed non-game delivery scenarios and generation-free read-only verification. |
| [tools/verify_surface_network_prepare.py](../../../tools/verify_surface_network_prepare.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Verify fixed-route preparation on synthetic and saved lowland terrain. |
| [tools/verify_surface_network_tiles.py](../../../tools/verify_surface_network_tiles.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Fixed implementation verification; no generation, GPU, game or independent certification. |
| [tools/verify_surface_review_browser.py](../../../tools/verify_surface_review_browser.py) | X4 |  | Replay read-only review contracts in installed Playwright and Edge. |
| [tools/verify_surface_variable_storage.py](../../../tools/verify_surface_variable_storage.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9 | Fixed vertex-prism evidence; only new run directories are published. |
| [tools/verify_td_accepted_water_morphology.py](../../../tools/verify_td_accepted_water_morphology.py) | X4 | S1/R9 | Synthetic accepted-water to sediment-candidate verification; no solver. |
| [tools/verify_td_active_spatial.py](../../../tools/verify_td_active_spatial.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Original Stage 4 TD domain, unchanged active material/runoff and zero stocks. |
| [tools/verify_td_active_spatial_series.py](../../../tools/verify_td_active_spatial_series.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Independent workers for the original 900s TD active spatial comparison. |
| [tools/verify_td_basin_breach.py](../../../tools/verify_td_basin_breach.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S2/G2 | Finite saddle path analytic evidence; actual TD face-flux integration pending. |
| [tools/verify_td_basin_candidates.py](../../../tools/verify_td_basin_candidates.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G2 | Pinned real TD geometry candidates and serialized diagnostic recoupling. |
| [tools/verify_td_basin_escape_plan.py](../../../tools/verify_td_basin_escape_plan.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Frozen TD potential escape forest with independent native D4 flood check. |
| [tools/verify_td_basin_source_hierarchy.py](../../../tools/verify_td_basin_source_hierarchy.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Pinned 256 squared TD static hierarchy inventory; no rainfall advancement. |
| [tools/verify_td_basin_spill_network.py](../../../tools/verify_td_basin_spill_network.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Cold-read frozen TD reach and potential spill graph review bundle. |
| [tools/verify_td_catchment_dynamic_review.py](../../../tools/verify_td_catchment_dynamic_review.py) | X4 |  | Pure IO catchment saved-frame export; versions remain separate cases. |
| [tools/verify_td_channel_distribution.py](../../../tools/verify_td_channel_distribution.py) | X4 | S1/R6、S2/G3、S2/G4、S2/G5、S2/G14 | Freeze real spatial-block channel distributions, then evaluate untouched TD. |
| [tools/verify_td_global_geometry_browser.py](../../../tools/verify_td_global_geometry_browser.py) | X4 |  | Verify the global coverage view, its controls and exported evidence. |
| [tools/verify_td_hour_pages_acceptance_io.py](../../../tools/verify_td_hour_pages_acceptance_io.py) | X4 | S1/R9 | Small pure-IO fixture acceptance; never launches a hydrological solver. |
| [tools/verify_td_hour_pages_review.py](../../../tools/verify_td_hour_pages_review.py) | X4 | S1/R9 | Native review fixture verification, without hydrological advancement. |
| [tools/verify_td_material_field.py](../../../tools/verify_td_material_field.py) | X4 | S2/G2 | Bounded independent material evidence and hostile archive checks. |
| [tools/verify_td_material_scaling.py](../../../tools/verify_td_material_scaling.py) | X4 | S2/G2 | Static synthetic material scaling; no terrain or hydrological generation. |
| [tools/verify_td_morphology_extension.py](../../../tools/verify_td_morphology_extension.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Pinned real TD PL morphology feedback, independent material and water ledgers. |
| [tools/verify_td_native_channel_geometry.py](../../../tools/verify_td_native_channel_geometry.py) | X4 | S1/R4、S1/R6、S1/R9 | Read pinned single-hour inputs and export diagnostic geometry; no solver. |
| [tools/verify_td_native_channel_surface.py](../../../tools/verify_td_native_channel_surface.py) | X4 | S1/R4、S1/R6、S1/R9 | Explicitly join four pinned candidate bed tiles and export no-water NPZ/OBJ. |
| [tools/verify_td_native_channel_tiles.py](../../../tools/verify_td_native_channel_tiles.py) | X4 | S1/R4、S1/R6、S1/R9 | Bounded four-tile prototype and expression-sampling review of pinned geometry. |
| [tools/verify_td_native_channel_valley_paths.py](../../../tools/verify_td_native_channel_valley_paths.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Build a pinned, render-only valley path prototype from saved TD evidence. |
| [tools/verify_td_native_domain_partition.py](../../../tools/verify_td_native_domain_partition.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Stream synthetic 1024/2048 native tile topology without allocating grid floats. |
| [tools/verify_td_native_storm_forcing.py](../../../tools/verify_td_native_storm_forcing.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9、S2/G3、S2/G4、S2/G5、S2/G14 | Light serial native TD weather generation and externally pinned cold reads. |
| [tools/verify_td_native_water_surface.py](../../../tools/verify_td_native_water_surface.py) | X4 | S1/R6、S1/R7、S1/R8、S1/R9 | Export one pinned saved v10 native water snapshot; never runs a solver. |
| [tools/verify_td_natural_channel_port.py](../../../tools/verify_td_natural_channel_port.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R9 | Pinned TD256 natural six-pool domain and disjoint M5 channel port replay. |
| [tools/verify_td_natural_lake_extension.py](../../../tools/verify_td_natural_lake_extension.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R9 | Independent reduced natural-lake references and pinned real D4 TD replay. |
| [tools/verify_td_natural_river_baseline.py](../../../tools/verify_td_natural_river_baseline.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9 | Freeze small TD regional diagnostics without claiming natural certification. |
| [tools/verify_td_partition_transport_saved_page.py](../../../tools/verify_td_partition_transport_saved_page.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Cold, transport-only two-second diagnostic of a pinned v10 saved page. |
| [tools/verify_td_readonly_review.py](../../../tools/verify_td_readonly_review.py) | X4 |  | Verify saved review identity, interaction and failed-read state lifetime. |
| [tools/verify_td_river_geometry.py](../../../tools/verify_td_river_geometry.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R9 | Bounded M5 fixtures and original TD geometry, independent mesh evidence. |
| [tools/verify_td_river_lake_coupling.py](../../../tools/verify_td_river_lake_coupling.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Independent M3/M4 references and bounded real-TD lake/river evidence. |
| [tools/verify_td_river_release_browser.py](../../../tools/verify_td_river_release_browser.py) | X4 |  | Actual desktop/mobile saved M8 consumer and the six renderer review contracts. |
| [tools/verify_td_river_results_browser.py](../../../tools/verify_td_river_results_browser.py) | X4 |  | Actual M8 saved-result downloads, bed layers and desktop/mobile WebGL audit. |
| [tools/verify_td_river_sediment.py](../../../tools/verify_td_river_sediment.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | M6 independent temporal references and sediment on newly solved M5 geometry. |
| [tools/verify_td_spatial_consistency.py](../../../tools/verify_td_spatial_consistency.py) | X4 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Bounded TD spatial refinement with analytical steady and transient controls. |
| [tools/verify_td_stable_overflow.py](../../../tools/verify_td_stable_overflow.py) | X4 | S1/R5、S1/R6、S1/R7、S1/R9 | Bounded full-event refinement of the pinned original TD reservoir topology. |
| [tools/verify_td_stage4_falsification.py](../../../tools/verify_td_stage4_falsification.py) | X4 | S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | Bounded multi-source falsification and actual component ablations. |
| [tools/verify_td_stage_review_browser.py](../../../tools/verify_td_stage_review_browser.py) | X4 |  | Check the actual saved stage review on desktop and mobile. |
| [tools/verify_td_surface_reaches.py](../../../tools/verify_td_surface_reaches.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Explicit threshold scan on frozen full 256-square TD topology and water. |
| [tools/verify_td_surface_river_edges.py](../../../tools/verify_td_surface_river_edges.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9 | Cold-read frozen TD edge export and independently check face provenance. |
| [tools/verify_td_tiled_valley_targeted.py](../../../tools/verify_td_tiled_valley_targeted.py) | X4 | S1/R4、S1/R6、S1/R9 | Targeted TD proof for tiled shared-field valley components. |
| [tools/verify_td_valley_global_tiled.py](../../../tools/verify_td_valley_global_tiled.py) | X4 | S1/R4、S1/R6、S1/R9 | Full declared TD valley coverage audit using tiled shared fields. |
| [tools/verify_td_valley_network_union.py](../../../tools/verify_td_valley_network_union.py) | X4 | S1/R4、S1/R6、S1/R9 | Whole declared TD edge set, connected canonical beds and unique cut ledger. |
| [tools/verify_td_water_cycle.py](../../../tools/verify_td_water_cycle.py) | X4 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R8、S1/R9、S2/G5 | Finite TD native runoff to shared-step channel/lake water-cycle acceptance. |
| [tools/verify_terrain_artifacts.py](../../../tools/verify_terrain_artifacts.py) | X4 |  | Run the portable artifact contract gate without GPU or game services. |
| [tools/verify_underground_preview_frontend.py](../../../tools/verify_underground_preview_frontend.py) | X4 |  | Focused Edge screenshots, canvas pixels, and underground view interactions. |
| [tools/verify_valley_geometry.py](../../../tools/verify_valley_geometry.py) | X4 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Valley geometry evidence on a blocked synthetic ridge and saved mountain. |
| [tools/verify_world_presets.py](../../../tools/verify_world_presets.py) | X4 |  | Fresh workspace-only servers; real diffusion for global mode; save/reload comparison. |
| [tools/view_native_30m_bundle.py](../../../tools/view_native_30m_bundle.py) | X4 |  | 只读保存的有限候选地形、PL切深、累计里程纵剖及真实毫米床变并检查地形面板像素；不生成或修改地貌。 |
| [web-preview/app.js](../../../web-preview/app.js) | X3 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [web-preview/bridge.py](../../../web-preview/bridge.py) | X3 | S1/R2、S1/R3、S1/R4、S1/R5、S1/R6、S1/R7、S1/R9、S2/G2、S3/V1、S3/V5、S3/V8 | Local read-only bridge plus explicit VDM preview/export endpoints. The bridge never runs hydrology r… |
| [web-preview/build_data.py](../../../web-preview/build_data.py) | X3 | S3/V1、S3/V8 | Export saved Java-processed NPZ samples as small local preview JSON files. |
| [web-preview/build_surface_review_data.py](../../../web-preview/build_surface_review_data.py) | X3 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R9、S2/G1 | Build fixed, offline surface-review data from accepted saved bundles. The browser never imports NPZ … |
| [web-preview/fault-surface.js](../../../web-preview/fault-surface.js) | X3 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [web-preview/fault_preview.py](../../../web-preview/fault_preview.py) | X3 | S2/G2、S3/V1、S3/V5、S3/V8 | Pinned cold fault evidence and explicit, bounded in-memory diagnostics. |
| [web-preview/global_geometry.py](../../../web-preview/global_geometry.py) | X3 |  | Read-only global valley geometry coverage and scope-exclusion review. |
| [web-preview/index.html](../../../web-preview/index.html) | X3 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [web-preview/morphology_preview.py](../../../web-preview/morphology_preview.py) | X3 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S2/G8、S2/G19 | Read-only real-TD morphology candidate package for the local review UI. |
| [web-preview/pillars3d.js](../../../web-preview/pillars3d.js) | X3 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [web-preview/pillars3d.py](../../../web-preview/pillars3d.py) | X3 |  | Read-only pillar-field true-3D bundles for the local review UI. This is the volume-form companion of… |
| [web-preview/renderer.js](../../../web-preview/renderer.js) | X3 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [web-preview/river-renderer.js](../../../web-preview/river-renderer.js) | X3 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [web-preview/river-results-3d.js](../../../web-preview/river-results-3d.js) | X3 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [web-preview/river-results.js](../../../web-preview/river-results.js) | X3 |  | Saved geometry only. Cut colours are metres; M6 millimetres are charted separately. |
| [web-preview/river_results.py](../../../web-preview/river_results.py) | X3 | S1/R4、S1/R6、S1/R7、S1/R8、S1/R9 | Read-only views of pinned M5 geometry and its actual M6 sediment replay. |
| [web-preview/saved-surface.js](../../../web-preview/saved-surface.js) | X3 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [web-preview/saved_surface.py](../../../web-preview/saved_surface.py) | X3 | S1/R1、S1/R2、S1/R3、S1/R4、S1/R6、S1/R7、S1/R8、S1/R9、S3/V1 | Pinned stage-one saved geometry adapter; one authenticated frame in memory. |
| [web-preview/serve.py](../../../web-preview/serve.py) | X3 |  | Serve the local review UI and its fixed-source bridge. |
| [web-preview/special-surface.js](../../../web-preview/special-surface.js) | X3 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [web-preview/special_surface.py](../../../web-preview/special_surface.py) | X3 | S3/V1、S3/V2、S3/V3、S3/V5、S3/V6、S3/V7、S3/V8 | Read-only special-terrain surface bundles for the local review UI. A chart in this package is a *syn… |
| [web-preview/style.css](../../../web-preview/style.css) | X3 |  | Terragenesis 审查工作台 · 现代复古 暖炭底 + 旧纸色文字 + 琥珀/青绿/赭红三个强调色；衬线标题、等宽标签、细线与硬阴影。 只改外观：选择器、id、媒体查询与布局断点沿用原结构。 |
| [web-preview/underground-contract.js](../../../web-preview/underground-contract.js) | X3 |  | Underground-river payload contract checks. This module deliberately has no DOM, canvas, or Three.js … |
| [web-preview/underground-surface.js](../../../web-preview/underground-surface.js) | X3 |  | 职责待人工核对；仅登记可确认的静态结构 |
| [web-preview/underground_preview.py](../../../web-preview/underground_preview.py) | X3 |  | Bounded explicit underground geometry generation and saved-package reads. |

## 盘点期间并行新增模块

| 文件 | 主归属 | 关联 |
| --- | --- | --- |
| [tests/test_island_peak_height.py](../../../tests/test_island_peak_height.py) | X4 | S1/R1、S2/G1、S2/G8 |
