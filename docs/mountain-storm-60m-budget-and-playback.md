# 60m 联算预算阻塞与只读播放交付

已固定与原300m相同的source/selection/geometry、全部雨团参数、72h、900s、初始soil135mm、零湖蒸发、湖rating和surface rain语义；仅60m绝对分区208HRU。未修改冻A或旧36/37/38文件。

冻结 `mountain_runoff_routing.preflight` 用 `steps*nodes*(HRUs+1)+full_source_cells*8` 计work。实际288步、749节点、208HRU、237169来源格需要46981160 work，超过原30000000上限；估计数组37100960bytes仍低于768MiB。故在水文推进前拒绝，并保留 `verification/mountain-storm-60m/run-20261001T073545802079Z/resource-precheck.json` 及 `failure.json`。早一次相同预算失败证据也保留。不能把≤256HRU误当整个联算预算通过。

未静默放宽上限、未monkeypatch冻结preflight、未缩短时段或更改HRU，以免伪装成授权的同物理时间对照。后续需协调明确的新版本资源入口，或明确批准独立复制的预算适配实验；冻A旧冷load规则不应暗改。60m联算及60m页面尚未完成，工具 `tools/verify_mountain_storm_60m.py` 是受此预检阻塞的实验入口，不是已验收生产接口。

先独立交付原300m的新版播放页：`verification/mountain-storm-play-review/run-20261001T073625264384Z/review.html`。播放150ms推进一个900s保存状态，非实时模拟；暂停、72h自动停止、末尾重新播放从初始状态、后台页面暂停均有明确行为。浏览器检查前三项及重播成功，三案例18个时间定位点也通过，零pageerror。加载仍只读保存JSON、不生成天气、不推进水文、不使用GPU推理。071520所有文件SHA不变，072059原页未改；新增目录有freeze-manifest及播放浏览器证据。

新写集：两个独立tools、此文档、新verification目录。100/150静态证据保持，不跑其水文。
