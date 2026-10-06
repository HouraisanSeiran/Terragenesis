# B阶段接口：全区域局部惯性v2

## 当前固定生产运行

目录：`verification/regional-hydraulics/full-20261001T101153406000Z/`。

模型：`regional-surface-local-inertial-D4-implicit-new-q-drag-v2`。采用真实水面梯度、新Q解析隐式Manning摩阻，忽略平流动量；不是完整浅水或陡坡物理认证。n=.035，max_dt=30s，CFL=.45。对照仅改max_dt=15s、CFL=.225，雨土强迫仍900s。

每case固定7200s墙钟、1000亿面评估、100万子步、256MiB估计内存、最多50快照、最大水深20m。失败保存最后一致前缀，不加预算凑通过。完整65536格、58.9824km²，H2=H0；外边界是工程排水或指定水位，不是天然海口。

强迫使用A保存的完整runoff_volume_m3/900，不重复加雨。region与height来源身份独立保存在binding.json。尾水为东边最后4格及南边最后4格共8个面，统一绝对水位最低床+10m，12–24h抬起，其他时段恢复局地crest工程排水。角格两个面共享同一格存量。

## A只读对接

各case的states.npz保存depth_m[S,256,256]、time_s[S]、ledger[S,5]及最终内部/边界Q；states.json包含metadata与diagnostics。ledger列为累计局地供水、外部进入、外部流出、存水、累计残差。初始与最后状态均保存，requested与committed时间分开。

geometry.npz保存H0/H2、共享面、crest及边界类型。interval-NNN保存区间首末深度、积分共享面体积、局地供水、首末Q。momentum-NNN是每24个强迫区间首个子步的完整抽样动量证据，不宣称全部轨迹重认证。manifest.json在每case完成后发布，含所有产物SHA与运行前源码SHA。

B将另发布离散水柱mesh索引供A消费；在此之前A不得从depth插值冒充同体积水面。A renderer文件仍由A独占。当前工具没有multi_agent send_input，不使用thread工具替代；本共享文档为接口交付。

最终兼容A的入口是每mesh目录`consumer-cases-index.json`，采用`regional-saved-B-mesh-cases-v1`。其path直接指向带统计的saved-water JSON，不剥离omitted字段或复制三字段消费者版本。完整物理统计同时保存在saved-mesh-index.json与physical-water JSON。两个独立case展示同动力结果：显式1mm显示过滤与0阈值全部顶面，均带threshold/omitted/solver/display体积及cell ids。界面须标注显示过滤/遗漏体积及关键帧回放，非全时间步播放。全部水柱NPZ保留每个非零格；顶面quad不是连续共享顶高水面。若0阈值超过16MiB，记录显式拒绝，不静默删格。

## 已完成可行性证据

## A真实失败UI输入

失败源包：`verification/regional-hydraulics/failure-20261001T102852005353Z/`，depth_zero_commit是0秒单帧、work_two_commit是60秒两帧，请求仍72小时。两包已独立禁止prepare/advance冷读接受，非合成UI fixture。work两步mesh兼容包位于`verification/regional-hydraulics/mesh-work_two_commit-20261001T102959321929Z/consumer-cases-index.json`；此早期导出仍有三字段版本，不作为最终统计协议。最终重导出会使用直接带统计JSON。0秒单帧禁止假播放或显示请求72小时为已计算时长。

均匀坡稳态、湿干静水平衡、双盆越鞍、真实尾水倒灌、守恒和资源失败前缀共9测试通过。峰值900s max_dt30/3/.3均完成、限流为0，Froude仍约3.19。30/3相对.3参考的水深RMS分别.00019856/.00005572m，显示趋近而非现实标定。

连续7h完整强迫探针耗39.985s、1712步，限流0。旧v1旧Q摩阻、显式和Picard失败证据保留，不追溯标成v2。当前主运行串行，进度每12强迫区间（3h）打印，最终状态以case manifest为准。
