# 单区域全格来源与流式土壤强迫

固定真实TD主窗原SHA `e1dc646b990388af3bf284b614b10c2a834d0259429539d2a7d3d2cc844712ae`，256²、30m、65536格、58.9824km²，中心原点[-184320,61440]m。中心坐标origin+index*30，footprint中心±15。没有group960裁剪、没有游戏压缩或重新推理。

## source接口

`regional_surface_source.build_source(raw,geometry,geometry_sha256=...)`绑定可信实际TD原payload与B静态geometry；保存H0、完整D4诊断receiver/order、出口归属/汇流面积、洼地标签、工程边界、保护域与独立channel阈值。静态route只用于诊断，B动态二维surface不能按它重复加入河库或强制单向流动。lake_id仅fullspill几何标签，不设统一动态湖位、不当永久水面mask。边缘所有free engineering drain，不认证天然出口/完整规划流域。

`save_source/load_source`外部SHA、精确成员/typed headers前检、全格DAG/D4和owner/area递推静态检查。source NPZ固定身份供B输入。河线阈值本模型独立1km²参数，与旧河网统计不混同。

## forcing接口与水账

新模型全部65536格作为conceptual terrestrial soil支持，暂时积水/干盆仍使用相同土库，不继承旧fixed lake direct rain。雨→soil/fast/slow→产流入B只一次，B不能再把全雨加到surface。没有额外永久湖mask，也没有动态湿面积土壤交换真实性认证。

`generate_forcing(source,directory,steps=288,dt_s=900,parameters,storm)`空间4096格分块，逐时间步，只保留当前soil/fast/slow。独立预算2500万cell-step、288步、65536格、常驻算法数组≤128MiB、磁盘≤512MiB/case，不动旧HRU/30M预算。

- `runoff_volume_m3.npy`: float64[T,256,256]，NPY mmap只读；每格时段体积m³，B除dt得到均匀时段速率，或按子步dt比例分配，不重复分配。
- `soil-final-and-time.npz`: initial/final_states_mm[3,256,256]，seconds_edges[T+1]；soil/fast/slow初末总量进入联合账。
- `manifest.json`: source_identity、全部气象/土壤参数、时段rain/ET/runoff/storage_change及residual总量、T+1土库总储量、文件SHA、范围和资源。
- 空间天气为明确参数化场，未用相同空间均雨伪装细化。uniform heavy另有uniform身份，不是原sigma300移动雨的细化。未保存144MiB逐格rain副本；静态消费不生成天气。B只需要产流mmap与账本。

每例产流144MiB（另NPY header），最终库约1.5MiB；当前算法数组预估约13MiB，不代表操作系统mmap页缓存峰值。逐步flush，不同时跑案例。外部系统空闲仅1.73GiB时不会分配T×N多中间场。

## 静态冷读信任边界

`load_forcing(directory,expected_manifest_sha256,source_identity)`必须外部可信manifest SHA，严格JSON duplicatekeys/NaN拒绝，固定basename防路径逃逸，typed NPY header在np.load前检查，read-only mmap。核对初态=parameters、NPZ时间、末态有限性、逐步总账/累计总量/产流网格和逐步ledger一致；不调用advance_soil或旧simulate。

保存只含初末库与总账，因此不宣称重签后改变产流和储量相抵的攻击可被物理逐格公式识别。模型正确性由可信生成程序、外部固定SHA及小样本旧公式逐项对照建立；此限制不能被守恒通过替代。若要不信任生成者的全物理重签认证，需要增加逐步状态/强迫证据，另作成本合同。

## 固定三场景

dry: 雨0，soil/fast/slow0，surface初水0；wet_no_rain: 雨0，soil135mm，其他0；uniform_heavy: 同湿土初态，全域24mm/h仅6–18h，72h，理论总雨16986931.2m³。其他土参数复用冻结RunoffParameters默认值，不调参。moving east/west此次不重复必跑。

当前固定入口 `tools/verify_regional_source.py` 与 `tools/verify_regional_forcing.py --source-directory ...`。新source路径见verification/regional-source/run-20261001T094825149694Z/manifest.json。forcing最终handoff记录每场景固定manifest SHA供B。本交付不推进surface、无GPU、无mesh，不宣称第一阶段五项全完成。

## 当前交付身份与内存修正

094825 source历史identity `7f6766...`保留。删除source对diffusion-wave的算法硬绑定，改为静态H0输入/由B声明solver，另存source095258，新identity `81d12179658ed02fefc94883cea1ce32888ff36199952d2bd88f68eb576f8cb2`，SHA `ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da`。不是偷偷替换旧源。forcing同步新identity，当前正式三包目录 `verification/regional-forcing/run-20261001T095608600719Z/`，入口handoff-manifest.json。

初始mmap全时序映射驻留页导致采样RSS247226368bytes，超过128MiB，保留旧profile证据。逐步写入flush后关闭重开映射、冷验每16步关闭重开，重新串行三例RSS采样峰101212160bytes（96.52MiB），含Python导入、source、初末库和mmap页；50ms采样不是OS精确峰值。profile-remap-20261001.json保留。新forcing数值与上一同步包相同，不覆写旧文件。

最新source/forcing/network针对测试13项通过（12项来源/强迫＋1项全域network）。coldload禁generate/advance_soil/weather，readonly写入拒绝；负dt、bool dt、超soil capacity、payload hash、错误typed NPY在np.load前、路径逃逸、source receiver/owner篡改和全域删格拒绝均覆盖。模型重签物理防伪范围限制仍按上节。

## 静态河段图与审查

网络 `verification/regional-source-network/run-20261001T095553240102Z/network.json`，channel1583格、1578内部receiver边、1226节点、1221连续段，稳定ID包含source identity和端点flat index，坐标XYZ米。每条边恰归属一段。520边原H0逆坡，最大单步13.006958m，每段标注uphill、未切床、hydraulic_connectivity_certified=false；跨潜在湖单列，lake0为非湖。不是已实现通水底床河线，不把fillspill计划当动态通量。

只读工具 `tools/verify_regional_review.py --source-directory verification/regional-source/run-20261001T095258008789Z --network-directory verification/regional-source-network/run-20261001T095553240102Z`。A独占新regional_surface_review模块/工具，B独占solver/物理几何/包validator。当前页全域H0、规划线/逆坡线、潜在洼地层，未接B快照则不画虚构水。B快照接口预留time_s[K]/depth_m[K,256,256]与外部B validator，保存H0+depth才可画stage。正式联合runner已准备，B稳定前不运行。

写集仅两个新regional_surface模块、regional_source/forcing tests、tools、本文及新verification。旧A/B/36/37/38冻结源码、Sonnet、TODO/issues/原数据均未修改。
