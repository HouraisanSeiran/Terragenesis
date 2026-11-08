# 阶段4真实参考来源与条件核查：2026-10-11

本轮使用 research 技能的主来源核查约定，按本轮要求不再派生代理。来源入口为 `tools/audit_river_reference_conditions.py`。本报告提供来源、条件与覆盖范围证据；自然度分布的训练、校准、真实留出和 TD 留出由独立基线工具执行。参考设计不依据 TD 自然度结果选窗或放宽阈值。

## 旧窗口的实际地貌与质量

原始栅格是本地 `D:/geography/01-完整流域样本/data/srtm_61_07.tif`，SHA256 `a0d97c11e2d53b8c78a05ac8488a6dadd603c27f32e32c493a7e08a928222acd`。6000×6000 格，EPSG:4326，范围 120–125°E、25–30°N，3角秒、int16、nodata=-32768、scale=1、offset=0。文件 band unit 缺失，米制仍为原 manifest 明示的源声明假定；WGS84 是水平基准，不能据此认证垂直基准。原 [CIAT-CSI SRTM 产品](https://srtm.csi.cgiar.org/)与本地 readme 说明这是洞填充 v4.1，可能含插值；整数米保存和最近邻采样不代表新增细河床测量。

既有候选 `verification/dem-domain/run-20261001T135530750135Z/dem-candidate.npz` SHA256 `d081ff6439a4d8bd57add2e6316096009a57b197f27e4ad7a93608f1bcd605b3`，642×460，EPSG:32651，90米投影目标格网，X=easting、Z=-northing。本轮再次 `load_dem_candidate(..., verify_source=True)`，逐源字节 hash、header、mask 和目标中心逆投影源像元取值重放。90米是保存目标间距，不是角度栅格的原生米制分辨率。

西北96×96窗口全部9216格有效，unknown=0，最小/5%/中位/95%/最大高程为27/55/279/601.25/799米，max-min起伏772米。因此旧参考不能称为“平坦海岸”；它是实际高起伏窗口。全候选有效高程分位为-5/5/137/528/924米，共261866有效、33454 unknown。有效格中853个数值零仅为源高程零；未知/缺测、负高程和零值都不构成自然海洋或海口认证。完整来源审查在 `verification/td-natural-river-stages/reference-conditions-20261011-01/report.json`。

旧逐样本 q05–q95 全在区间内的成功规则有统计缺陷：参考自身也会约有10%落在两端之外。它不能充当自然河网接受标准。分布比较需先在真实样本上训练、校准，并在真实空间留出上验证。新基线还需将达到相同汇水面积阈值的河道节点/边与一般 D8 山坡区分，不能将全部山坡样本改称河槽。

## 新地理来源与空间分离

本地精细真实DEM仅发现这张SRTM瓦片。四个历史 dem-domain 目录是同源派生，并非四个独立真实流域。HydroRIVERS 是 DEM 派生矢量，USGS-06719505 的100次断面记录是同站重复测量；均不能增加独立DEM/流域总体数量。粗 ETOPO 和 WorldClim 不当作90米河道地形参考。

先冻结八个0.4×0.4度地理格窗：west=120.2/121.0，south=26.2/27.2/28.2/29.4，均位于原瓦片范围。八窗只有四个完整低起伏block，故在尚未评价新的TD自然度之前，追加整个北缘条带：29.55–29.95°N、120.0–123.2°E，按0.4度连续八窗；保留全部窗口，不挑选通过者。地理设计分别在输出目录 `design.json` 中先于地形读取保存。

复用现有 `prepare_dem_candidate`，90米目标格网、900米halo、原源声明和掩码规则。每份保存 NPZ 再 `verify_source=True` 冷读。全源无覆盖窗口保留 `unsupported_no_source_coverage`，不产生虚假零高程；有效但不完整的block保留统计并拒绝作为完整参考。

每个地理候选固定48×48不重叠block，名义面积范围4320×4320米。按 `(block_row+block_col)%3` 固定 fit/calibration/real_holdout；max-min起伏类为<50、50–250、>=250米。最终 `eligible_for_evaluation` 同时要求全部有效、无unknown且整个block都在core_mask内；halo边界块全部剔除。旧south=29.4的geographic-06/07不参与最终校准，由北缘连续条带替代，避免与新增条带交叠。基线工具另检验世界坐标block范围互不重叠。类别只在这个尺度有含义，不是外部认证的山地或流域分类。空间留出仍有相邻空间相关性，同一产品也有相关性，不主张样本交换性、独立流域或全球覆盖。

最终条件化来源清单为 `verification/td-natural-river-stages/reference-geographic-20261011-04/report.json`，保留上游03的设计与源包hash；datasets逐份有dem path/hash/grid/identity，block ID含dataset前缀，保持来源可回查。01地理尝试在全源nodata窗口处终止，02只有八窗，均不冒充最终评价证据。03北缘西端窗口因900米halo越出源瓦片边界被拒绝，保留具体reason，没有移动窗口以补造覆盖。

04最终SHA256为 `bbc234d52145beceaf03dd61e32af3bfc7526adc0d4722b56be3184c3c58eb51`。437个可评价block按fit/calibration/real_holdout计数：低起伏8/8/8，中起伏17/18/12，高起伏121/123/122。独立 `--check-inventory` 对所有可评价block逐对核验世界坐标目标范围不交叠，通过；两个针对固定角色、完整覆盖、非有限输入与掩码重叠拒绝的测试通过。

04冻结清单的 `spatial_exclusion_policy` 中 `no_halo_or_shared_source_cells` 措辞超出实际审计，准确含义是 `no_halo_or_overlapping_target_blocks`。本轮未扫描原TIF源像元共享：90米投影目标格不重叠不保证最近邻地理坐标源像元独立。这个勘误保留在文档，不改已经冻结的04字节或统计阈值。05为措辞纠正副本，不作为已经启动的最终基线来源设计，不要求重复437块计算。

## 气候量纲与数值匹配

官方 [WorldClim2.1](https://www.worldclim.org/data/worldclim21.html) 明示1970–2000长期气候、温度°C、降雨mm、10角分约340km²。官方 [BIO定义](https://www.worldclim.org/data/bioclim.html) 明示BIO1年均温、BIO4温度标准差×100、BIO12年降水、BIO15降水变异系数。本轮保存两份官方HTML、实际请求URL/返回URL/UTC获取时刻/字节hash。它们不补造历史本地TIF的原始下载URL。

四个本地 `data/global/wc2.1_10m_bio_{1,4,12,15}.tif` 保留字节hash、header、resolution、nodata/scale/offset。按每个DEM block中心最近源气候像元取值。粗气候像元可能被多个block共享，不能当作48²局地气候测量或短时暴雨forcing。旧西北block中心实际BIO为15.193260°C、819.589783（SD°C×100）、1332mm、46.068157（CV百分数）。

TD `diffusion/backend.py` 保存 `WorldPipeline` 输出climate前四通道；`diffusion/geography_v5.py` 产生合成温度、温度SD×100、降水mm、降水CV×100。固定上游 `world_pipeline.py::_compute_climate` 对温度做地形递减率修正，后三量按原通道插值；上游 `minecraft_api.py` 明示precipitation coefficient of variation (%)。保存的climate是合成条件输出，不是实测气候或同期实测产流。四量纲可和真实BIO进行数值条件匹配，虚构地点无需对应真实城市；来源语义仍分开。

四维分层预注册边界：BIO1=[0,10,20,30]°C；BIO4=[500,1000,1500,2000]；BIO12=[500,1000,2000,3000]mm；BIO15=[30,60,90]%。使用右侧归箱规则，四个维度全部一致且起伏类一致才有条件支持。TD在相同物理范围原生窗口内按各保存气候通道中位值归箱。真实参考训练、校准、留出支持不足的类不评价，不用TD结果扩大边界；数值条件一致也不代表真实气候或forcing已认证。

## TD留出与能力边界

原height-budget-v5保存有seed20261004的四个区域。stage4已经评价其origin=[0,0]，因此不能再宣称这个seed完全未见。其[-16000,-13952]、[384,15488]、[11520,15360]是尚未用于旧自然度评价的区域候选；原生成报告已包含height/slope与condition诊断，所以“留出”仅指新的河网自然度分布评价。数据身份及所有screen/holdout库存保存在01来源审查包。未发现额外现成独立TD种子；不启动GPU补生成。

`metric_resolution_exchange.py` 的公开合同是固定一维河段串联细分、原生库存求和回粗及水沙轨迹，不是二维动态AMR。阶段4可检验这个现有能力的开关、时间步和空间对照；完整二维动态交换仍是明确未实现能力，若要求相应自然可信覆盖则门槛不通过。`docs/td-river-m7-m8-20261010.md` 已明确空间收敛 unresolved、全域二维动态交换与自然出口未解除。

原生积分是体积基准；统一细分的失败须来自实测而非预写。one_way是工程边界，不是认证自然海口。源DEM缺测/未测垂直datum、未独立河线/完整流域边界、未认证海口、同源空间相关性、气候类别支持不足均必须留在能力判定中。来源审查和真实留出校准可完成，但不能据此直接将natural_credible或publishable置true。
