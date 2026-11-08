# 有限闭合河网样本 v1

交付日期：2026-10-28。**本次有限样本四项能力已验收：真实供水、范围内合法接收终点、跨块冷恢复、Python默认消费。** 不等待全R1–R9/S1–S6通过，不称无限世界河网已完成。

## 产物

- 稳定只读产品：`artifacts/finite-river-sample-v1/`（14个数据文件+product.json，约1.87MB）。不依赖scratch脚本，保存地形、域成员、Q/土壤/湖时间序列及k8完整检查点。
- 总览图：`artifacts/finite-river-sample-v1-overview-v2.png`。
- Python默认入口：`tools/publish_domain_bundle.py`。默认即有限产品；旧粗规划仅显式`--legacy-coarse`，缺产品或域外不会静默回退。
- product.json SHA256：`226cd4f6421213b9431288b431394957b67a674478019b0b2b5cc5b8424fb8e8`。

代码在本工程的Python环境中运行。数据包不是独立安装包，不含TD模型权重；查询不调用TD/GPU，也不重新计算事件。

## 直接使用

在工程根目录执行。查询高地起点的6小时末流量和接收湖状态，不需`--product-dir`或实验开关：

```powershell
runtime/venv/Scripts/python.exe -B tools/publish_domain_bundle.py --point 1267800 1292580 --time-s 21600
```

预期：该格Q约`0.001173518818 m³/s`；接收湖V=`763.7682321972277 m³`、h=`795.7910454208821 m`、湿格2。

查询河道中点、湖终点的多个时刻：

```powershell
runtime/venv/Scripts/python.exe -B tools/publish_domain_bundle.py --point 1267080 1291440 --point 1265790 1290900 --time-s 0 7200 13500 21600
```

默认坐标单位为世界米，必须是30m格参考点，不插值/不吸附。`--native`显式改用原生格号（例如head `42260 43086`）。只接受所交3951格和`0..21600s`时窗，域外/缺依赖/错时刻明确拒绝。

显式恢复到**不存在的新目录**，从k8（2小时）继续余下16步；原成品不改：

```powershell
runtime/venv/Scripts/python.exe -B tools/publish_domain_bundle.py --point 1267800 1292580 --time-s 21600 --resume-checkpoint k8 --resume-output-dir artifacts/finite-river-sample-v1-user-resume
runtime/venv/Scripts/python.exe -B tools/publish_domain_bundle.py --product-dir artifacts/finite-river-sample-v1-user-resume --point 1267800 1292580 --time-s 21600
```

恢复后的查询与连续产品逐位一致。已存在输出目录会拒绝，不覆盖。普通query无输出参数时只读、只向终端打印JSON；`--output-dir`可将查询报告另存新目录。

## 四个已验收里程碑

| 里程碑 | 主端通过范围 |
|---|---|
| M1 静态有限域 | 固定seed20261020/原生30m；3951格完整汇水（3.5559km²）、0unknown、0支撑触边、89格strict路径至16格单叶局地湖盆 |
| M2 真实供水 | 固定4mm雨/6小时，3935陆格复用soil产流、16湖盆床格直接雨；逐格Q/ET/库存在独立水账闭合 |
| M3 跨块与恢复 | 2/4块×正逆固定打乱共6组实际调度；42/123条真实跨块边；7组实际新进程恢复，逐步Q/soil/湖状态与整体一致 |
| M4 默认消费 | 现Python默认CLI实际查询稳定产品；恢复产物经同一query消费；域外/错时刻/缺产品拒绝，不回退粗链 |

物理结果（m³）：总雨14223.6 = ET1859.2875 + 末陆地三库11600.544267802776 + 末湖763.7682321972277，独立残差约`-3.64e-12`，低于预声明门`1.43236e-6`。

## 合法接收终点与限制

接收为`finite_event_lake_storage`，不是永久内流根或海口。已知最低D8边界crest800.8836059570312m，比D4合并位802.6686401367188m更低；留1m显式余量，safe_level799.8836059570312m，safe_capacity20854.193115234375m³。实际库存约占3.66%。越过该安全事件范围硬拒，不能从本样本推断未来spill的全世界去向。

- 模型`quasi_steady_d8_no_channel_storage`：每interval内路由并交付，无河槽库存、行程延迟或洪峰到时认证。
- 固定声明雨情景和示例土壤参数，非实测标定/噪波气候；湖盆床视为事件内不渗裸岩，忽略湖面蒸发渗漏，陆地ET由现soil核计算。
- 时间：Q属于`[edge_i,edge_(i+1))`；湖状态存于edge。内部非边界时刻返回该interval末湖状态并标`asof=interval_end`；t=end返回末interval Q与末状态并标`asof=t=end`。不是连续时间插值。
- 仅interval边界checkpoint，不含wave级恢复；域准备已拒unknown，不声称脏状态恢复。
- 不含回水洪泛、冰雪、水沙床变、无限世界覆盖、1m全域网格或Java/Mod。最小空间单位约定1m不等本包已提供1m地形精度。
- `finite_sample_complete=true`只对应本样本四能力；`world_complete/hydraulic_ready/natural_outlet_verified/publishable`保持false，其中后者沿用全量认证语义，不否认这份有限产品的可用交付。

## 证据与复跑

主端记录在`.scratch/finite-river-sample/m1-domain-v1/DELIVERY-M1.md`、`m2-supply-v1/DELIVERY-M2.md`、`m3-recovery-v1/DELIVERY-M3.md`及`m4-default-v1/DELIVERY-M4.md`。scratch是开发/验收证据位置，运行产品不依赖其中脚本或相对数据。

主端M4联合63tests通过；完整8stage新进程复跑29.958s全部通过；18个连续query与18个恢复query逐项零差；另不传产品路径的真实默认15query逐项零差，5源码SHA与14数据SHA一致，产品字节不变。Windows独立探针首回因stdout编码解码失败已保留，修为明确子进程UTF8后通过，非数值失败。

后续如需更多范围，以新的独立版本继续；旧W1与世界目录的失败和未闭合记录照存，不回写、不把未覆盖项说成已完成。
