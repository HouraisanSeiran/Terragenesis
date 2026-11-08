# 虚构世界噪波气候的真实物理参照

用户本轮指定输入模型为噪波生成的强度场，计算气候与降雨，面向具有现实风格的虚构世界。真实地理数据用于量纲、物理范围、联合统计和地形参考，不要求每片虚构地形对应真实城市或逐点真实气候。新噪波版本必须与旧 geographic_v5 的输入身份和历史评价分开。

## 固定全球来源调查

入口 `tools/survey_global_river_climate.py`，最终物理参照报告 `verification/td-natural-river-stages/global-climate-physical-20261011-01/report.json`。四份已保存的WorldClim2.1、1970–2000、10角分BIO栅格逐文件固定hash/header/nodata/scale/offset，要求完全一致的全球地理网格；只取四通道共同有效且有限的808053像元。官方定义及本地量纲见 [来源核查](td-stage4-reference-conditions-20261011.md)。

报告固定BIO1（°C）、BIO4（温度标准差°C×100）、BIO12（年降水mm）、BIO15（降水变异系数%），全局min/1%/5%/25%/50%/75%/95%/99%/max及按年均温分箱的联合物理上下文。它们是描述性观测范围，不是新的自然度接受cutoff。统计按等经纬度像元计权，极地占比较大；不能将全球中位值直接解释为一般虚构世界的目标气候。

| 条件 | 实际全球共同有效像元 |
| --- | ---: |
| 旧联合bin [4,2,2,1] | 0 |
| 旧联合bin [2,3,1,1] | 0 |
| 旧联合bin [2,2,2,1] | 64 |

前两类并非只在宁海SRTM窗口中缺测，而是在这个全球产品和冻结分箱中无观测支持；不能据单产品的缺席证明物理不可能，也不能伪造匹配。BIO1>=30°C只有264个共同有效像元，实际BIO4范围110.798836–509.702057（即温度SD约1.108–5.097°C）。旧v5高温窗口约32.9–34.0°C且温度SD约12.0–12.5°C，超出这个真实联合上下文。旧bin和拒绝保留，不为新噪波模型修改旧cutoff。

## 同产品独立地理来源

为补充实际地形与气候统计，先冻结全球调查与地点计划，再获取官方同CIAT-CSI SRTM源瓦片。初始150km分离规则在64个匹配真实气候像元中仅产生两个地点；根据真实来源支持数量，未查看新TD自然度前修订为25km分离、最多12地点，仍按SHA256地理坐标顺序确定选择。此规则在 `global-climate-coverage-20261011-02/report.json` 中冻结。每地点0.15×0.15度，地理窗口分离，整地点按fit/calibration/real_holdout循环赋角色，不在同地点中拆分角色。

实际源地址为CIAT官方的 `https://srtm.csi.cgiar.org/wp-content/uploads/files/srtm_5x5/TIFF/` 下 `srtm_17_05.zip`、`srtm_18_04.zip`、`srtm_18_05.zip`。入口 `tools/prepare_climate_matched_river_reference.py` 保存预注册plan、实际HTTP地址/状态、ZIP/TIF字节hash和原readme。最终重用完整本地下载的条目标记 `reused_immutable_local_download`，由于首次下载未保留时刻，`retrieved_utc` 为null，不推造精确时间。传输采用HTTP Range响应范围与长度检查，完整ZIP解压校验后再使用。原产品仅本地研究、未获再分发许可，不接入默认世界。

source候选通过既有 `prepare_dem_candidate` 形成90m米制UTM15N目标格网，900mhalo。既有UTM51N规则保留，新增UTM15N必须bbox属于声明的带；跨带、错带、经纬度目标和非法单位仍拒绝。每个保存候选再次完整源hash/header/mask/目标中心逆投影源像元取值冷重放。只有全部有效且全core的48²block可评价，角色属于整地点。目标范围不共享并不保证原地理源像元或流域统计独立，同产品空间相关性保留。

新Missouri来源是独立版本参考设计，不混进旧宁海已冻结cutoff；即使产品相同，也需新的真实训练、校准与留出支持。Copernicus DSM不能无区分混入SRTM，本轮没有用它替代官方SRTM。用户改噪波输入后，不再继续为旧零支持bin追逐更多地理资料；Missouri保留为有用的真实地形/条件参照。

最终 `reference-missouri-20261011-01/report.json` 固定SHA256 `0bb325691fe831dc5560e7d1eaf09dc47b2cf9cf3d9f362926f161430dfa29e0`，12地点共72有效block；低起伏fit/calibration/holdout为14/15/11，中起伏为10/9/13。第11地点halo越过瓦片边界，使用三份原TIF原生affine有界拼接，`crop_provenance`固定原文件与裁剪身份。随后冻结 `reference-combined-20261011-01/report.json`，SHA256 `a5bba60119943e2016ebb5297e0b904d8d7dda69a148720e04e85b727aa6bc47`，原宁海437与Missouri72块合为509块，逐字节固定两份输入报告，保留角色、无支持条目与eligible标记；重叠与配对只在相同目标CRS内比较，避免将UTM15N与51N局部坐标误当同地点。BIO仅作上下文，几何比较按起伏与格网。

`noise-water-cycle-20261011-02/report.json` 将seed20261011噪波降雨接入原96贡献格河/湖域，900物理秒、2×2等面积midpoint近似、300秒forcing区间与绝对900秒weather节点。独立mm/h→m3积分雨量1.8874177297m3，native最大差1.73e-18m3；河湖本地入水0.03745663487m3、闭边界最终储量相同、全局残差0。保存后禁止两类solver冷读并重放降雨来源身份；种子/参数/米制坐标/边界/近似规则均入forcing和product身份。它仍是工程假设的短时有限域验证，不是年度实际降雨或自然湖出口认证。

## 噪波与模型合同

现有 `diffusion/geographic_noise.py` 以绝对conditioning格坐标、seed、salt及多尺度smooth_noise生成可跨tile重放的强度场，`field`返回归一化多尺度值。其坐标尺度是conditioning格，不应在没有显式换算的情况下称为米。旧 `geography_v5.py` 由多个强度场直接计算年均温、温度SD、年降水、降水CV，温度与SD的联合关系没有来自月度物理过程的约束。

已实现 `terrain_pipeline/surface_rivers/metric_noise_forcing.py`：复用既有 `field`，将绝对米制坐标上的240km气候场、60km区域场映射为相关的温度、湿润度与大陆性，12个月温度含-0.0065°C/m高程递减，12个月正降水带明确季节变化。BIO1为月温度均值°C，BIO4为月温度标准差°C×100，BIO12为月降水总和mm，BIO15为月降水变异系数%；四量从同一月序列导出并实际核验。来源、seed、参数、米制坐标、格网与时间边界进入身份，原始v5高程条件不变。

短时降雨另以12km/3km天气强度场和8m/s、2m/s平流计算，绝对900秒weather节点间线性插值，并跨月精确积分；`grid_rainfall` 输出明确的mm/h，以等面积midpoint子格近似单元平均，1/2/4子采样规则写入身份。空间切片保持绝对坐标，时间区间拆分保持雨深预算。年度月降水目标不等于实际全年天气累计，也不直接当暴雨强度。实际短时forcing与native产流、河湖水账的证据见上述noise-water报告。真实资料仍是范围与相关性参照，合成强度场不是实测气候。

## 最终独立留出结果

已在读取新TD结果前固定参数、实现源码快照、源模型、独立seed20261013/14、每seed三个来源条件区域及两个48²/90m观察窗口。区域按原始v5完整正高程与halo条件确定，未根据TD输出或自然度挑选。`noise-holdout-20261011-01/plan.json` 绑定最终 `channel-real-calibration-20261011-04/plan.json`；生成前逐项核验九份源码pin，生成report保留评价plan开始时SHA。六包实际模型输入检查均确认原始v5高程不变、change_seed后噪波BIO等于固定条件。

最终几何评价按起伏/格网，采用相同1m观测投影、米制平坦区距离路由及稳健atan2曲率。单块CDF联合距离与两窗口均值cohort均只由真实calibration固定alpha=.2秩阈值，真实validation不参与阈值；没有要求所有窗口或所有cohort必须通过的总门槛。509个真实区块中的166留出块为133通过、33拒绝；六类cohort实际移位负对照全部拒绝。

独立结果为12窗口10通过、2拒绝，6组5通过、1拒绝；12份canonical噪波月气候的有限值、非负降雨和同月BIO一致性全部通过。月气候以实际native物理高程直接采样并另存12份派生NPZ，上游模型辅助BIO单列真实范围上下文，不替代canonical气候。开发seed20261011/12的六组全部通过，明确仅为开发回归。

保留拒绝的区域为seed20261014、native origin(-40960,-57344)，源高程206.589218–503.369171m。两个窗口分别为低起伏29m、高起伏281m；高起伏窗口纵坡CDF距离0.473503108超过单块cutoff0.315133082。组合分数0.407135314超过high-low cutoff0.371450750，也高于对应八个真实validation组合的最大值0.391977596；该真实组本身六通过、两拒绝。另seed14、origin(0,-65536)保留一个低起伏窗口拒绝，但其组合通过。五个低/中起伏组合通过与一次high-low拒绝分别记录，不将有限拒绝解释为普遍自然度或缺实现。

最终汇总 `noise-holdout-evaluation-20261011-01/report.json` SHA256 `a1590f7ae05c2e1f3f470b3aeb4a170ebd42670304b60463f0d156f55c4d0eae`；生成report SHA256 `1e5eaa4f0068c19d6eace19eddb69b4ecfc59727067f5bf89d97a860166beaf7`；reference04 SHA256 `84bdcca476d3767fabea135c8692ee9a6da6fc4d63fd8a0225726247afdb5d32`。独立进程冷核验六原始包、六评价报告、十二派生月气候包及实现/生成/评价绑定均一致。20项聚焦测试通过。复现使用 `tools.generate_td_noise_validation`、`tools.verify_td_channel_distribution` 与 `tools.summarize_td_noise_evaluation` 的新输出目录，不覆盖冻结证据。

旧seed20261004及已读自然度区域没有重新作为新留出，历史全球无支持组合、几何拒绝和空间数值失败均保留。真实样本来自同SRTM产品且空间相关，目标网格不重叠不等于源像元独立；真实配对距离与TD目标5760m×5760m存在偏差，已记录实际范围。两个新seed的区域与窗口仍相关，评价属于有限经验支持。实现与本轮评价已完成，普遍自然认证和默认发布仍为false，阶段5消费固定报告及来源身份。
