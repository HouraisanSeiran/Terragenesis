# 三维水系源码与本地包快速开始

状态：2026-10-06，fine15与geometry03已实际独立passed；水力07/08未接受，v8的09零完整case、预算失败；08不重跑，水力未接受。本文命令不启动真实900s工程事件或旧全天求解，也不把固定工程配置当作已通过结果。接口及限制见[三维水系](hybrid-river-network.md)。

## 仅有GitHub源码

仓库不包含模型、原生TD数组、`.scratch/`环境或`verification/`真实保存包。以下Windows PowerShell命令安装独立Python 3.11环境并复现tiny，不会生成真实地形或启动真实900s工程事件、旧全天求解；水力tiny可能调用有界小型Radau求解，`--help`不求解。无需Java、Minecraft或网页服务。

```powershell
git -c core.autocrlf=false clone https://github.com/HouraisanSeiran/Terragenesis.git
Set-Location Terragenesis
py -3.11 -m venv .scratch/hybrid-river-network/venv
$py = (Resolve-Path .scratch/hybrid-river-network/venv/Scripts/python.exe).Path
& $py -m pip install -r algorithm/requirements.txt
& $py -B -m unittest tests.test_hybrid_river_graph tests.test_hybrid_cave_geometry tests.test_hybrid_cave_saved_audit -v
& $py -B -m unittest tests.test_hybrid_river_sections_v2 tests.test_hybrid_river_hydraulics_v3 -v
& $py -B -m unittest tests.test_hybrid_river_hydraulics_v8 -v
& $py -B -m unittest tests.test_hybrid_river_hydraulics_v8_saved_audit -v
& $py -B tools/prepare_hybrid_cave_geometry.py --help
& $py -B tools/prepare_hybrid_river_hydraulics.py --help
& $py -B tools/prepare_hybrid_river_hydraulics_v3.py --help
& $py -B tools/prepare_hybrid_river_hydraulics_v4.py --help
& $py -B tools/prepare_hybrid_river_hydraulics_v5.py --help
& $py -B tools/prepare_hybrid_river_hydraulics_v7.py --help
& $py -B tools/prepare_hybrid_river_hydraulics_v8.py --help
& $py -B tools/audit_hybrid_river_hydraulics_v8.py --help
```

`algorithm/requirements.txt`包含manifold3d 3.5.4、numpy/scipy/psutil/matplotlib及shapely等。tiny使用有界fixture而不是真实水文重算。依赖范围安装不保证与首例运行环境逐字节相同；真实发布仍以保存runtime、代码pins及独立审计为准。Windows首例使用`D:/anaconda/python.exe`和隔离`.scratch/hybrid-river-network/python-deps`，已安装该target时需设置`$env:PYTHONPATH`，不修改全局Python环境。

## 取得真实本地输入后

固定父包不是自动下载项。需要完整14/15保存目录、原生hierarchy/source及所有原父链文件；只取得index或几何图不能重新构造实体。包内绝对路径必须可解析，文件SHA和内容identity必须匹配；保持代码字节/换行与冻结pins一致，不手改路径或忽略校验。跨机器迁移需要独立重绑定、重新保存并审计，当前CLI不是无损路径迁移器。

在已有实际包的工程根目录配置下面路径。`Sha`仅计算本地字节，不授予passed；固定fine/geometry SHA仍在主文档。所有输出使用新目录，保留历史refused和`.partial`。

```powershell
$base = Join-Path (Get-Location) 'verification/natural-river-network'
$surface = Join-Path $base 'shared-port-channel-20261006-01'
$fine = Join-Path $base 'shared-channel-fine-20261006-01'
$geometry = Join-Path $base 'hybrid-cave-geometry-20261006-03/geometry.json'
$geometryAudit = Join-Path $base 'hybrid-cave-geometry-20261006-03/independent-audit-v2.json'
function Sha([string]$path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
```

### Typed图准备：无solver

已有固定graph时直接读取，不重复生成。确需复现图构造时，新输出目录示例：

```powershell
$graphOut = Join-Path $base 'hybrid-river-graph-local-new'
& $py -B tools/prepare_hybrid_river_hydraulics.py graph `
  --surface-index "$surface/index.json" --surface-audit "$surface/independent-audit-v1.json" `
  --fine-index "$fine/index.json" --fine-index-sha256 (Sha "$fine/index.json") `
  --fine-audit "$fine/independent-audit-v1.json" --fine-audit-sha256 (Sha "$fine/independent-audit-v1.json") `
  --sink-arc receiver:59076:59332 --spring-arc receiver:60099:60355 --output $graphOut
if ($LASTEXITCODE -ne 0) { throw 'graph preparation failed' }
```

surface CLI默认pins只支持固定已通过14包；fine必须与真实独立审计绑定。新graph的文件SHA与含绝对路径的内容身份可能不同，后续不能混用原geometry03审计。

### 洞道准备：无solver，另存候选

已有geometry03优先直接冷读/导出。重新准备会产生新身份，不能继承旧passed结论。以下消费上一步的新graph；8m埋深是显式参数，0.5m实际覆岩门槛不变：

```powershell
$newGraph = Join-Path $graphOut 'graph.json'
$caveOut = Join-Path $base 'hybrid-cave-geometry-local-new'
& $py -B tools/prepare_hybrid_cave_geometry.py `
  --graph $newGraph --graph-sha256 (Sha $newGraph) --burial-m 8 --output $caveOut
if ($LASTEXITCODE -ne 0) { throw 'geometry refused; inspect new index, do not relax gates' }
& $py -B tools/audit_hybrid_cave_geometry_v2.py `
  --geometry "$caveOut/geometry.json" --geometry-sha256 (Sha "$caveOut/geometry.json") `
  --output "$caveOut/independent-audit-v2.json" `
  --audit-schema td-hybrid-cave-geometry-independent-audit-v1
if ($LASTEXITCODE -ne 0) { throw 'new geometry audit did not pass' }
```

源码版本、binary/runtime或来源不足时拒绝是正确结果，不删unknown/wet/protected或预算门槛。prepare另存rock_before/cutter/rock_after/removed、VDM和源采样，原TD/fine不写入。

### 已接受geometry03只读导出

该命令不生成几何、不执行审计或solver，需已具备完整固定输入与实际passed审计。`$geometry`/`$geometryAudit`仍指向实际03，不混入上一步的新包。

```powershell
$reviewOut = Join-Path $base 'hybrid-cave-review-local-new'
& $py -B tools/export_hybrid_cave_review.py `
  --geometry $geometry --geometry-sha256 (Sha $geometry) `
  --audit $geometryAudit --audit-sha256 (Sha $geometryAudit) `
  --output $reviewOut --vertical-exaggeration 1
if ($LASTEXITCODE -ne 0) { throw 'review export failed' }
```

输出`review.json`、`caseartifact.json`、`overview.png`、`profile.png`、`oblique-3d.png`。消费前检查review中的matched/passed及pins；`caseartifact.mesh.water=null`，透明rock和removed mesh不是水体。读取说明见主文档“源码与只读消费”，无需改UI即可查看保存JSON与PNG。

## 水力入口：尚未实际通过

`tools/prepare_hybrid_river_hydraulics.py experiments`只准备显式工程配置。v2至v5准备器分别为`tools/prepare_hybrid_river_hydraulics_v2.py`、`tools/prepare_hybrid_river_hydraulics_v3.py`、`tools/prepare_hybrid_river_hydraulics_v4.py`、`tools/prepare_hybrid_river_hydraulics_v5.py`；BDF入口为`tools/prepare_hybrid_river_hydraulics_v7.py`。这些CLI没有`run`子命令，均要求graph、geometry、geometry-audit、experiments各自文件路径及SHA和新output。这里只提供`--help`，不重跑08，也不把实现或已保存case作为可通过的solver教程。

v4/v5另有`--crown-friction-transition-m`（0..0.05m）与`--diagnostic-stop-s`。宽度0只能用于带短stop的旧law诊断，正宽度也允许短stop；2cm是显式新有效屋顶摩阻law，不是静默更改原实际断面/压力槽库容。模型参数、代码pins、三来源库存政策及失败/停止实际work保存至`hydraulic-model.json`和版本化checkpoint/诊断。v5把untraced/source/tailwater直接积分并求和为V，保存观察时刻实际Radau端点；严格负库存拒步重试，不做clamp、事后归一或dense库存正性认证，重试不重置forcing和预算。两个新kernel都可用各自同名tiny测试模块检查有界行为，但tiny可能执行小型Radau，不替代真实900s验收。

v7的base/refined相对及绝对容差分别为原配置的1/64、1/256，最大步长为原配置的1/4、1/8（本例2.5s/1.25s）；不复用07旧精度case，forcing、预算与1e-4m³等接受门槛不改。保存观察时刻采用实际BDF端点，仍须严格负库存拒步和累计重试预算检查；08实际两个pulse完成、reverse未全完成，不是已通过结果。

v8入口为`tools/prepare_hybrid_river_hydraulics_v8.py`，参数同样要求graph/geometry/geometry-audit/experiments路径与SHA、新output，并支持显式摩阻过渡和短diagnostic stop。它从实际最低floor取共同整数datum，local化断面与head/尾水后委托冻结v6 Radau，不复制kernel；不改几何、law、forcing、预算或门槛。保存local数组、`numerical_frame`、local solver参数及身份，global head须等于datum+local head。冷读入口为`tools/audit_hybrid_river_hydraulics_v8.py --input <index.json> --sha256 <SHA> --output <NEW audit.json>`，明确核对共同frame与实际物理账；不可仅看global输出近似相等。上列worker与saved-frame测试各两项，在本次环境分别1.404s/1.063s通过，可能运行小型Radau，不代表09接受。

checkpoint只把完整case作为结果保存，不把中途截取当通过；07显式复用06的pulse-base，不等于任意失败运行可自动resume。02/03零完整case，04是旧lawcrown停滞诊断，05虽推进900s仍因source超V约2.607e-6m³被拒。07已failed_partial退出，三个完整case为pulse-base（复用06）、pulse-refined07、reverse-base07；pulse head差0.142606mm/相对差0.000521807通过，但V/tracer约0.0047851m³、link约0.0120924m³未过1e-4m³。reverse-refined在物理528.71458s、RHS200001预算停止。

08亦已failed_partial退出：两个BDF pulse精度case完整900s，但head差1.87169mm、体积差0.0897506m³、link差0.226888m³均未过对应绝对门槛；reverse-base工作上限停止，reverse-refined未启动。Main对两pulse的面积/Q/三来源库存与逐cell账独立冷读通过，不等于时间精度通过。转压力强瞬变是当前分析方向，不是已确认或已修复根因；不重跑08，不允许前端消费这些未接受时序。fine与几何已交付，水力仍未接受。

09实际零完整case，在物理548.6969417s、RHS200001/link3952019、墙钟107.141s预算停止，26pins不改，不重复真实运行。诊断观察到08逆向global head近1367±1e-12m的绝对高程量化与窄slot刚性；pulse625..645s涉及近干receiver的minK自湿释放，不是645s roof-band根因。local datum未证明唯一根因或修复成功；Main先补实际face几何，未接受时序继续禁止前端消费。

将来只有实际四case及独立水力审计passed，才可导出保存时序。原审计入口为`tools/audit_hybrid_river_hydraulics.py --input <index.json> --sha256 <SHA> --output <NEW audit.json>`，原导出入口为`tools/export_hybrid_river_hydraulics_review.py --index <index.json> --index-sha256 <SHA> --audit <audit.json> --audit-sha256 <SHA> --output <NEW目录>`。它们不能仅换文件名就当作支持v4/v5/v7：新case/index schema、模型law pins、三来源直接库存和端点正性语义均须由对应独立审计/导出实现显式支持，并核对真实passed输入；适用入口及最终验收由主协调更新。

以上命令没有全主流域、自然海口、三维Navier-Stokes、Minecraft写入或网页导航的接受含义。
