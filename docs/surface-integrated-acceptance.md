# 地表集成验收复跑入口

入口 `tools/verify_surface_integrated_acceptance.py`。在全部作者冻结后由协调运行；编写阶段不自动执行最终套件。

- 默认命令：`D:/anaconda/python.exe -X utf8 tools/verify_surface_integrated_acceptance.py`。只读核验固定31/32/33报告、独立审查、bundle、implementation和现有浏览器manifest各场景哈希，不prepare或导出manifest。
- 最终同次回归：上述命令加 `--tests`。从旧joint-regression.json的command取得27个唯一旧模块，加31/32/33/export四模块；不猜测试数量，不累计历史focused成绩。
- 浏览器：加 `--browser`，仅此时导入既有 `tools.verify_surface_review_browser.audit` 并使用当前已安装Playwright/Edge。输出在本次目录的browser子目录，失败或工具不可用均如实失败，不默认增加依赖。
- 可指定 `--manifest <manifest.json>`；只读核哈希，不替换默认manifest。可选 `--old-constrained-hashes <JSON>` 接受历史path到SHA256映射；禁止把31/32/33的新hash误当旧baseline。

固定证据目录为31 `run-20260930T192708.659151Z`、32 `run-20260930T193214454541Z`、33 `run-20260930T200657434780Z`。
缺少独立review、非accepted状态、报告与审查不绑定最终包、implementation改变、manifest场景重复或哈希不符会失败。
审查文件自身记录本次读取SHA；没有外部指定review哈希时不把该运行快照冒充第三方签名。

旧27模块列表来源 `verification/surface-continuity-resumption/run-20260930T171150.386297Z/joint-regression.json`，
并验证其原日志SHA。旧实现hash参考domain-prepare/domain-mosaic/multidomain-dynamic三份历史报告；其余旧模块
若没有明确历史hash映射，只记录本次前后稳定性，不宣称拥有27份历史冻结hash。

每次创建唯一UTC目录 `verification/surface-integrated-acceptance/runUTC`，保留report、stdout、stderr、
unittest日志与实际run/pass/skips/failures/errors/duration、唯一测试ID、skip原因。模块只加载一次，重复测试ID拒绝。
默认没有suite计数；使用--tests时，测试内部允许它们本身的prepare和临时export回归，runner不主动调用prepare、导出、GPU或Java。
所有跟踪source/evidence/test文件在结束时再次核hash，改变即失败；异常也保留诊断与report。
browser不重复加载浏览器unittest模块，直接单次audit，避免把浏览器focused次数混入joint suite。

集成通过只代表既有有界工程契约，不解除自然认证、完整动态波动、一般跨精度或地下/多层三维门禁。

## 聚焦自检与冻结

`--self-check` 只执行runner自身的合成小样本门禁：哈希/变化快照、重复JSON与非有限值、
required13集合、重复manifest/路径逃逸、重哈希后错误caseId/schema/kind/status/source、模块与测试ID去重，
以及4个合成unittest的真实pass/skip/failure/error计数；另只读核验31/32/33独立证据。
其中合成failure/error是故意负例，不计入最终回归，不运行任何工程测试模块或浏览器。
不能与--tests或--browser组合；所有自检结果、stdout/stderr和runner起止哈希写入本次UTC目录。

Manifest必须恰有13个固定case，JSON的caseId/schemaVersion/kind、manifest与evidence状态一致，
且各source path/SHA绑定固定accepted来源（DEM仍diagnostic）。旧5场景manifest不能通过。
浏览器audit当前只读取默认manifest，因此--browser与非默认--manifest组合直接拒绝。
Runner自身在开始时加入冻结快照，结束再次比较，运行中改变必失败。

## 历史说明与湿面积口径

31旧文档中的历史pending状态已被冻结目录的`independent-review.json`中
`accepted_bounded_scope`独立审查取代；不修改旧文档及其验收哈希。

33旧文档“只有all-wet三角形”的精确实现口径是：先要求一个CELL的四个顶点全部wet，
再选取该CELL的两个保存三角形积分，而不是按每个三角形三个顶点独立筛选。
因此静态land为706个wet cells、1412个三角形，水量252.72852290299738m³。
三顶点筛选会得到1444个三角形和258.2434362m³，不属于本次accepted预算，展示不得混用。
此静态口径仍不扩展原动态V(h)的676 wet cells；旧冻结文档保留，以本说明消除措辞歧义。

## 显式静态校验修复补充

最终入口先读取固定补充目录`verification/surface-static-validation-repair/run-20260930T204827573351Z`
的report及independent-review。必须report passed、review accepted_bounded_scope，且review的report_file_sha256
与implementation_frozen_sha256精确绑定报告和六个授权新文件，否则拒绝，不假装旧hash仍有效。
仅32/domain-mosaic/domain-prepare三个core及对应tests可替代：旧期望必须逐项等于repair的old_implementation_sha256，
并与原103111/170535/193214历史报告一致，才映射new_implementation_sha256。其他旧期望一律严格不变。
报告original_bundle_sha256_before/after必须相等，并逐包核对当前文件；不改已绑定的补充报告字段。
原三包前后哈希与内容身份不变，旧report/review不覆写；本次报告显式记录替代清单。
补充修复复用已保存H0 support及完整静态proof验证，保留evaluation domain/config/usage约束；prepare仍完整验证。
