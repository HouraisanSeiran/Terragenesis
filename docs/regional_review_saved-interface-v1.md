# 单区域保存状态审查接口

正式前端接入以`.scratch/terrain-framework/single-region-frontend-contract.md`为准，本文件仅A独立审查页消费说明。不会使用旧双域prompt包作为本轮区域成果。最终唯一索引待B全部场景及联合验收冻结，禁止扫描latest自动选包。

最终landing生成器为tools/verify_regional_review_landing.py，输入外部固定SHA索引，单一页面链接二维、三维、diagnostics和限定说明；不复制大JSON、不启动模型。landing索引必须显式列出所有目标及SHA，允许正式heavy/tailwater完成后一次冻结。潜在lake标签不是统一动态湖位：本轮湿土诊断中lake242的439个≥1mm格自由面极差13.617m，lake173极差11.252m；页面不得写“湖水位”。

A只写HTML/export/tests/tools；B独占水动力与水体几何。只读页面不求解、不生成天气，不从潜在湖标签造水。当前运行环境没有暴露用户指定的multi_agent_v1 send_input，不能用thread工具冒充联系。

## 保存与显示分离

完整每格闭柱：65536湿格可达524288顶点/786432三角，留在B物理NPZ及其验证证据，不受页面显示格式限额约束。B提供完整保存depth状态；显示建议另导上表面quad，最多262144顶点/131072三角。若使用显示深度阈值，必须记录阈值、遗漏格数和遗漏体积；不得据此改变物理状态或水账。A不自行减裁闭柱假称完整mesh。

目前显示JSON单文件16MiB、300000顶点/400000三角，总复制512MiB；不能将全湿闭柱直接塞入此接口。Canvas全水性能尚未认证，非零正式接入前必须用真实水测试或升级renderer。

## 外部可信索引

`regional-saved-B-mesh-cases-v1`：source_identity、fixture_only、cases。每case包含id/model/requested_time_s/committed_time_s/status/failure/snapshots/B_validation。status枚举completed/refused；completed时间必须相等且failure=null；refused要求严格短前缀与非空失败原因。快照必须含t0和已提交末态，严格递增，不插值。每快照含time_s/path/sha256/volume_m3/max_depth_m；path限basename，时间与水量非负有限。

mesh JSON只含source_identity/vertices_xyz_m/triangles。索引需外部SHA；这不是物理认证替代物。B_validation只引用独立验收证据，最终需固定证据路径+hash；A结构校验本身不证明动力学。

两页读取同一case/time索引，按保存时刻播放，显示请求和已提交时长。切场景不重置相机；异步加载使用ticket防旧请求覆盖。合成fixture只进入独立regional-review-fixture目录，正式导出默认拒绝。导出全部校验后暂存、原子no-clobber发布，失败不留半页。

统一正式入口：`tools/verify_regional_review_saved.py --run-index PATH --run-index-sha256 SHA`。run index固定source/network及每case manifest、B显示index的外部SHA，不在读取随意路径时现算hash充当认证。只读adapter接受B单case索引和带遗漏字段的top-quad JSON，聚合为cases索引；保留原mesh全部字段，UI显示总/显示/遗漏储水与比例和阈值。物理NPZ仍在原B包，引用不冒充已复制认证。

不采用B另导出的剥离omitted三键过滤consumer：过滤后总solver volume不等于显示体积。原saved-water是唯一正式适配入口。三键mesh仅供明确隔离UI fixture及历史真实零水证据；通用真实入口要求全部display统计。

failure保留B原dict的reason/time，不转字符串丢细节；显示顶点最大深度名为display_max_depth_m，不冒充solver最大水深。case附water_summary初水/产流/边界进出/末水；边界读取固定geometry的kind面数。抬尾水case可在run index case中提供predeclared_sha256，显式显示8个指定stage面、12–24h事件与绝对stage，不能套用全边free-drain说明。

浏览器命令另加`--browser`；验证每个保存索引、播放/暂停/末态停止，场景及时间选择后相机保持。t0-only拒绝单帧直接停播，不虚构后继帧。合成fixture另测异步race guard；非零全水性能仍待真实数据测，不由小quad证据认证。

## 性能证据

隔离满格fixture：65536quad/262144顶点/131072三角。Canvas旧包103516测10帧461–505ms，不足交互。新WebGL使用深度测试、terrain/water缓存buffer（只在mesh切换上传）、相机uniform；103834包10帧0.3–1.4ms，计时包含gl.finish，零pageerror。这是该机器合成渲染测量，非真实湿水物理认证或所有浏览器性能保证。context loss显式退回Canvas；降级可能慢，不改变数据。

真实dry+拒绝统一浏览器包103937通过：两页三case；dry0/24/72h、depth_zero_commit仅0、work_two_commit0/60s。后者阈值.001m遗漏1.7046930714428778m³（100%），UI显著展示，不画成无水。失败reason/time保留；全部仍请求72h而仅短前缀提交。

更正证据关联：103834/104210旧full-water截图误放在race切回t0之后，不足作为满水图验收。104559新包锁定1800s同态：262144 vertices、131072 triangles、GLwaterTriangles=131072、蓝像素86734；同步10帧p95=1ms，截图就在计时处。满规模门槛预声明p95≤50ms、零pageerror且支持/体积不变。104449真实60s拒绝包full-top131072三角、遗漏0、p95=.9ms；仍不是长时湿水动力学认证。

新版B consumer-cases-index如果保留完整display统计，可在trusted run case加representation_id选择full_top_threshold_0或display_filtered_1mm。adapter仍逐mesh校验source/H0/格中心±15 footprint、time、总/显示/遗漏体积；从外部固定case metadata保留原failure dict和水账，不沿用B显示索引中字符串化的failure。不再派生额外物理或mesh包。

三维增加隐藏地形背景开关，关闭只影响terrain draw call，不改变water buffer/水位/竖比。105012隔离fixture同态水131072三角、相机保持，关闭后蓝像素增加并独立截图browser-full-water-no-terrain.png；读者可据此审查微水完整支持区。静态河段始终是前景审查叠加，不认证遮挡关系或动态流向。

105404真实失败双表示浏览器包：局地click cell0在60s full-top深度2.8900103643536568e-8m，显示体积2.601009327918291e-5m³；同格filtered表示深度未知而非干。UI显式关键帧，不称连续72h回放。指定stage边界定位采用bound geometry boundary_cell/kind面数；60m UI切换未实现。

联合回归runner等待B冻结才正式运行，包含regional source/forcing/network/review、hydraulics/archive（含mesh）、rainfall/source_adapter/depression及surface_network_consumer。artifact index必须包含递归本地import的源码、相关tools/tests及实际冷读fixture hash；执行前后比较，原包不重签。只--help和review聚焦测试已运行，不声称完整联合回归已完成。

当前source/forcing功能测试已迁移到canonical095258/095608，源与dry/wet/storm三个manifest SHA固定在测试中。人为重签攻击副本可以重新算攻击hash，但不作为真实来源信任。25项source/forcing/network/review聚焦测试通过；canonical三forcing全格形状、T+1时间、初始135mm与16.9869312Mm³暴雨账覆盖。联合index要求这三包全部manifest/NPZ/NPY及原network，不用旧094825/094853包声称本轮验收。

## 只读诊断图

tools/verify_regional_review_diagnostics.py消费外部固定regional-diagnostics-trusted-run-v1：每case固定summary_path/summary_sha256、forcing_manifest_path/forcing_manifest_sha256、case_manifest_path/case_manifest_sha256。case manifest的binding.json及states.json SHA验证后，forcing identity必须同该forcing SHA；仅source相同不充分。读取saved partitions验证lake+nonlake=total、严格时间，输出实际committed prefix，不延到72h。

雨强(mm/h)、土库产流(m³/s)按forcing时段阶梯；出界和尾水入界率按preceding saved interval画阶梯平均，不连接成瞬时洪峰。存量全域/lake/nonlake按保存点画，标签湖不是统一stage。显示requested/status/failure及雨土surface水账；实际包尚待B summary，不能把fixture图当真实暴雨/退水成果。

112751真实dry+两拒绝诊断浏览器通过，三个canvas、case切换、metadata/time核对、零pageerror；run index在verification/regional-review-diagnostics/dry-failure-trusted-run-v1.json。summary工具需绝对case路径，原包未修改；只另存邻接summary。此包没有真实wet/heavy长时退水，等待最终数据继续集成。

113651真实wet审查包：原full101153/wet_no_rain manifest b19ce75839d9ce99b6937f6c22acb938e6698a72ed08265bbf4e6546fde3cd9d；mesh113511的filtered/full-top两表示各7帧、两页播放/暂停/末态/相机/隐藏床/click验收通过，零pageerror。113728诊断页消费49个真实保存状态及288 forcing时段，case/forcing SHA一致。无雨但湿土释放仍令72h地表储水上升至1385929.220198729m³，不声称已有全域退水或峰后回落；累计出界176356.46906973587m³，雨土surface联合残差1.0782969184219837e-7m³。湿包仍局部惯性有限范围，非完整浅水认证。

最终页面默认1mm过滤，中文“湿土无雨/均匀暴雨/抬尾水”和“全量微水膜”分开命名；微膜蓝满坡不等于可见河道。诊断图增加实际时段四等分x刻度（完整72h为0/18/36/54/72h）、y轴0/半量/最大值。最后统一浏览器待heavy固定，原113651/113728不覆盖。

旧一次性dry工具仅历史开发证据，不是正式通用入口，直接np.load没有header前检；统一入口不调用它或任何solver。真实dry固定run index在verification/regional-review-saved/dry-trusted-run-v1.json；只代表零水case，不认证湿流或尾水。
