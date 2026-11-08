"""Build a dense per-module purpose map for the active first-party source tree.

Differs from build_module_catalog.py by adding the columns an unfamiliar agent
actually needs before touching a file:
  * purpose (docstring summary; falls back to top-level symbols, marked unreviewed)
  * public symbols
  * internal dependencies (what it imports from this repo)
  * imported_by count (static, incl. tools/tests)
  * version family and whether this is the newest member
  * pinned_by_evidence: how many frozen verification records carry its sha256

Read-only with respect to sources; writes only the two output files.

Each module's sha256 is the digest of its **original bytes**: a UTF-8 BOM is stripped
only for parsing and CRLF is never normalised, so the value matches frozen evidence
and catalog records for the same file.

Import resolution (static, per the boundary rules in CONTRIBUTING and
.legacy-code/README.md):
  * a file's module name is its path below the root, `__init__.py` naming the package;
  * `import a.b` and `from a.b import c` give candidates `a.b` and `a.b.c`;
  * `from . import x` / `from .mod import x` / `from ..pkg import x` are resolved
    against the importing module's package, one level per leading dot;
  * a candidate only becomes a dependency edge when it names a file inside the
    scanned roots (see `import_graph`). Imports that leave the roots, name
    nothing in the tree, or belong to third parties are dropped, so a same-named
    module in another package is never counted.

Boundaries that are deliberately *not* covered (do not read a 0 as "unused"):
  * `importlib.import_module` / `__import__` / `eval` of computed names;
    imports inside functions are still seen because the AST is walked whole;
  * module paths assembled from strings, CLI invocations (`subprocess python
    tools/x.py`), config files, and shell/PowerShell helpers;
  * evidence pinning only indexes `.json`/`.md` under `verification/` and skips files
    over 4 MB, so a pin count of 0 is a lower bound, not proof of no frozen use;
    `.scratch/**/release.json` source-code snapshots are not indexed at all.
"""
import ast
import hashlib
import json
import os
import re
from collections import Counter, defaultdict

try:  # run as `python tools/build_module_map.py`
    import module_categories as categories
except ImportError:  # imported as `tools.build_module_map`
    from tools import module_categories as categories

ROOTS = ["terrain_pipeline", "diffusion", "tools", "tests", "web-preview", "src", "vdm_diffusion"]
SKIP_DIRS = {"__pycache__", "node_modules", ".git", "legacy-code", "verification",
             "service-0.9.0", "build", "dist", "runtime", "vendor", ".claude",
             ".vantaloom", "backups"}
CODE_EXT = (".py",)
OUT_MD = "docs/architecture/module-map.md"
OUT_JSON = "docs/architecture/module-map.json"


def first_docstring(tree):
    doc = ast.get_docstring(tree)
    if not doc:
        return None
    for raw in doc.splitlines():
        line = raw.strip()
        if not line:
            continue
        return re.sub(r"\s+", " ", line)[:160]
    return None


def _posix(path):
    """Canonical, platform-independent path form used as the map's key."""
    return path.replace(os.sep, "/").replace("\\", "/")


def module_name_of(path):
    """Dotted module name for a source path; `__init__.py` names its package."""
    parts = _posix(path)[:-3].split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def package_of(path):
    """Package a module lives in; the package itself for `__init__.py`."""
    parts = _posix(path)[:-3].split("/")
    return ".".join(parts[:-1])


def _import_candidates(node, package):
    """Absolute dotted module names one import node can refer to.

    Relative forms are anchored at `package` (the importing module's package),
    `from .` staying inside it and each extra dot climbing one level. A relative
    import that climbs past the root yields nothing instead of a bogus name.
    """
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    level = node.level or 0
    parts = package.split(".") if package else []
    if level > len(parts):
        return []
    prefix = parts[:len(parts) - (level - 1)] if level else []
    base = prefix + (node.module.split(".") if node.module else [])
    if not base:
        return []
    base_name = ".".join(base)
    candidates = [base_name]
    for alias in node.names:
        if alias.name != "*":
            candidates.append(base_name + "." + alias.name)
    return candidates


def analyse(path):
    path = _posix(path)
    try:
        with open(path, "rb") as stream:
            raw = stream.read()
    except OSError:
        return None
    try:
        source = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return None
    symbols = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                symbols.append(node.name)
    package = package_of(path)
    internal = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for name in _import_candidates(node, package):
            head = name.split(".")[0]
            if head in ROOTS:
                internal.add(name)
    # sha256 stays the hash of the file's original bytes: decoding with
    # utf-8-sig only strips the BOM from what ast sees, never from the digest.
    digest = hashlib.sha256(raw).hexdigest()
    return {
        "docstring": first_docstring(tree),
        "symbols": symbols[:8],
        "symbol_count": len(symbols),
        "internal_imports": sorted(internal),
        "lines": len(source.splitlines()),
        "sha256": digest,
        "category_declared": categories.declared_category(tree),
    }


def import_graph(info):
    """Map module file -> set of files that statically import it.

    Only candidates that name a scanned file become edges, so packages resolve to
    their `__init__.py`, submodules resolve to their own file, and a same-named
    module elsewhere is never credited. Self references are dropped.
    """
    by_module = {}
    for path in info:
        by_module[module_name_of(path)] = path
    graph = defaultdict(set)
    for path, record in info.items():
        for name in record["internal_imports"]:
            target = by_module.get(name)
            if target is None or target == path:
                continue
            graph[target].add(path)
    return graph


def layer_of(path):
    """Top-level source root, e.g. 'terrain_pipeline'; used as the table's section key."""
    head, _, tail = path.partition("/")
    return head if tail else os.path.basename(head)


def subdir_of(path):
    """Directory below the root, e.g. 'surface_rivers'; empty for root-level files."""
    parts = path.split("/")
    return "/".join(parts[1:-1])


def main():
    files = []
    for root in ROOTS:
        if not os.path.isdir(root):
            continue
        for directory, subdirs, names in os.walk(root):
            subdirs[:] = [d for d in subdirs if d not in SKIP_DIRS]
            for name in names:
                if name.endswith(CODE_EXT):
                    files.append(_posix(os.path.join(directory, name)))
    files.sort()
    print("modules: %d" % len(files), flush=True)

    info = {}
    for path in files:
        record = analyse(path)
        if record is None:
            record = {"docstring": None, "symbols": [], "symbol_count": 0,
                      "internal_imports": [], "lines": 0, "sha256": None,
                      "category_declared": None, "parse_error": True}
        info[path] = record

    # imported_by: resolve every candidate to a real file before counting it, so a
    # relative import or a package import lands on the right module instead of
    # producing a phantom path.
    imported_by = import_graph(info)

    # version families
    families = defaultdict(list)
    for path in files:
        base = os.path.basename(path)[:-3]
        match = re.match(r"^(.*?)_v(\d+)$", base)
        key, version = (match.group(1), int(match.group(2))) if match else (base, 1)
        families[(os.path.dirname(path), key)].append((version, path))
    newest = {}
    for members in families.values():
        if len(members) > 1:
            top = max(v for v, _ in members)
            for version, path in members:
                newest[path] = (len(members), version == top)

    # evidence pins: build a set of every 64-hex token found in the evidence once,
    # then intersect with module hashes. A single alternation regex over 1500 hashes
    # is catastrophically slow on multi-MB text, so tokens are extracted instead.
    print("indexing verification pins ...", flush=True)
    sha_to_modules = defaultdict(list)
    for module_path, record in info.items():
        if record["sha256"]:
            sha_to_modules[record["sha256"]].append(module_path)
    hex_token = re.compile(r"\b[0-9a-f]{64}\b")
    pin_hits = defaultdict(int)
    evidence_files = 0
    for directory, subdirs, names in os.walk("verification"):
        subdirs[:] = [d for d in subdirs if d != "__pycache__"]
        for name in names:
            if not name.endswith((".json", ".md")):
                continue
            path = os.path.join(directory, name)
            try:
                if os.path.getsize(path) > 4_000_000:
                    continue
                text = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            evidence_files += 1
            for sha in set(hex_token.findall(text.lower())):
                for module_path in sha_to_modules.get(sha, ()):
                    pin_hits[module_path] += 1
        if evidence_files and evidence_files % 2000 == 0:
            print("  ... %d evidence files" % evidence_files, flush=True)
    print("evidence files scanned: %d" % evidence_files, flush=True)

    labels, registry = categories.load_registry(".")
    rows = []
    for path in files:
        record = info[path]
        callers = len(imported_by.get(path, ()))
        fam = newest.get(path)
        category, category_source = categories.resolve(
            path, record["category_declared"], registry)
        rows.append({
            "path": path,
            "layer": layer_of(path),
            "subdir": subdir_of(path),
            "category": category,
            "category_source": category_source,
            "is_algorithm_module": categories.is_algorithm_module(path),
            "purpose": record["docstring"],
            "unreviewed": record["docstring"] is None,
            "symbols": record["symbols"],
            "symbol_count": record["symbol_count"],
            "imports": record["internal_imports"][:6],
            "imported_by": callers,
            "lines": record["lines"],
            "version_family": fam[0] if fam else 1,
            "is_newest_in_family": fam[1] if fam else None,
            "pinned_by_evidence": pin_hits.get(path, 0),
            "parse_error": record.get("parse_error", False),
        })

    with open(OUT_JSON, "w", encoding="utf-8") as stream:
        json.dump({"schema": "module-map-v1", "modules": rows}, stream,
                  ensure_ascii=False, indent=1)

    total = len(rows)
    unreviewed = sum(1 for r in rows if r["unreviewed"])
    pinned = sum(1 for r in rows if r["pinned_by_evidence"])
    multi = sum(1 for r in rows if r["version_family"] > 1)
    algorithm_rows = [r for r in rows if r["is_algorithm_module"]]
    by_category = Counter(r["category"] for r in algorithm_rows)
    missing = sorted(r["path"] for r in algorithm_rows if r["category"] is None)

    lines = [
        "# 全仓模块作用表（精确版）",
        "",
        "自动生成，勿手改；重跑 `runtime/venv/Scripts/python.exe -B tools/build_module_map.py`。",
        "",
        "## 怎么用这张表",
        "",
        "**动任何文件之前，先在这一行里确认三件事**：",
        "",
        "1. **证据 pin > 0** → 该文件被冻结验收记录用 SHA256 点名。改一个字节（哪怕只改 import 或注释）就会让历史证据校验失败。**不要动，除非用户明确批准并另立证据修订。**",
        "2. **被引用 = 0 且证据 pin = 0** → 可能是死代码，但仍要看是否被 CLI 调用、动态导入、字符串路径引用。归档前用 `tools/build_module_map.py` 同级的方法核实。",
        "3. **版本族 > 1** → 同目录存在同名多版本。看「最新」列判断是不是最新；**最新 ≠ 应该删旧的**，旧版常常仍被新版依赖或承担不同物理语义。",
        "",
        "**推荐阅读顺序**：先看本表的「版本族总览」了解哪些族有多个版本；再看目标大类分节（算法模块）或目标层分节（tools/tests 等），按「证据pin」降序（表格已按此排序）避开雷区；最后看「符号」列确认职责，不必打开源码。",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        "| 模块总数 | %d |" % total,
        "| 无 docstring（需人工核对） | %d |" % unreviewed,
        "| 被冻结证据 pin | %d |" % pinned,
        "| 属于多版本族 | %d |" % multi,
        "| 算法模块（terrain_pipeline/diffusion/vdm_diffusion） | %d |" % len(algorithm_rows),
        "| 算法模块缺大类 | %d |" % len(missing),
        "",
        "## 算法大类",
        "",
        "大类按编码规范 §11：模块级 `CATEGORY = \"...\"` 声明优先，其次 `docs/architecture/algorithm-categories.json` 登记。"
        "只是逻辑分类，不代表文件位置或 import 关系；`?` 为已登记、待用户确认。",
        "",
        "| 大类 | 模块数 | 声明 | 登记 |",
        "|---|---:|---:|---:|",
    ]
    for category in categories.section_order(by_category):
        members = [r for r in algorithm_rows if r["category"] == category]
        lines.append("| %s | %d | %d | %d |" % (
            categories.heading(category, labels), len(members),
            sum(1 for r in members if r["category_source"] == "declared"),
            sum(1 for r in members if r["category_source"] == "registry")))
    lines.append("")
    if missing:
        lines.append("缺大类的算法模块：" + "、".join("`%s`" % p for p in missing))
        lines.append("")
    lines += [
        "**列含义**",
        "",
        "- **模块**：文件名；完整路径见同名 JSON。",
        "- **子目录 / 目录**：tools/tests 等分节给根下子目录；大类分节给完整目录（一个大类跨多个根）。",
        "- **作用**：源码 docstring 首行；标 `⚠` 表示源码无说明，此时给出可见公开符号，仍需人工确认。",
        "- **符号**：公开函数/类（最多 4 个），看这个文件到底提供什么最快的入口。",
        "- **依赖**：本仓库内的 import（最多 3 个）。",
        "- **被引用**：静态 import 它的活跃文件数（含 tools/tests）。",
        "- **版本族**：同目录同名 `_vN` 成员数；**最新**列标 `是/否`。",
        "- **证据 pin**：`verification/` 里出现其 sha256 的记录数。",
        "- **行数**：源码行数，粗略反映体量。",
        "",
    ]

    # version family overview: the single most asked question about this repo
    families_rows = []
    by_family = defaultdict(list)
    family_key = {}
    for row in rows:
        base = os.path.basename(row["path"])[:-3]
        match = re.match(r"^(.*?)_v(\d+)$", base)
        if match:
            family_key[row["path"]] = (row["subdir"], match.group(1))
        else:
            family_key[row["path"]] = (row["subdir"], base)
    # second pass: a family only exists if some member carries a _vN suffix
    versioned = {key for key in family_key.values()
                 if any(re.match(r"^.*_v\d+$", os.path.basename(r["path"])[:-3])
                        and family_key[r["path"]] == key for r in rows)}
    for row in rows:
        key = family_key[row["path"]]
        if key in versioned:
            by_family[key].append(row)
    if by_family:
        lines.append("## 版本族总览")
        lines.append("")
        lines.append("同目录下同名 `_vN` 的模块。**有多个成员不代表冗余**——旧版常被新版依赖，或承担不同物理语义。")
        lines.append("")
        lines.append("| 族（目录/名称） | 成员数 | 版本号 | 被 pin 的成员 | 说明 |")
        lines.append("|---|---:|---|---:|---|")
        for (subdir, name), members in sorted(by_family.items()):
            # bare (un-versioned) file is v1; versioned members carry _vN
            parsed = []
            for m in members:
                stem = os.path.basename(m["path"])[:-3]
                match = re.match(r"^(.*?)_v(\d+)$", stem)
                parsed.append((int(match.group(2)) if match else 1, m))
            versions = sorted(v for v, _ in parsed)
            pinned_members = sum(1 for m in members if m["pinned_by_evidence"])
            newest = max(versions)
            entries = []
            for version, m in sorted(parsed):
                marks = []
                if m["pinned_by_evidence"]:
                    marks.append("pin%d" % m["pinned_by_evidence"])
                if m["imported_by"]:
                    marks.append("ref%d" % m["imported_by"])
                if not marks:
                    marks.append("无引用无pin")
                entries.append("v%d[%s]" % (version, ",".join(marks)))
            lines.append("| `%s/%s` | %d | %s | %d | 最新 v%d；%s |" % (
                subdir or ".", name, len(members), ", ".join(str(v) for v in versions),
                pinned_members, newest, " ".join(entries)))
        lines.append("")

    # Algorithm modules are grouped by category; the directory column then carries
    # the source root too, since one category spans several roots. Everything
    # else (tools, tests, web-preview, src) keeps one section per layer.
    sections = []
    for category in categories.section_order(by_category):
        subset = [r for r in algorithm_rows if r["category"] == category]
        sections.append(("大类 %s" % categories.heading(category, labels), subset, True))
    for layer in ["tools", "tests", "web-preview", "src"]:
        subset = [r for r in rows if r["layer"] == layer and not r["is_algorithm_module"]]
        sections.append((layer, subset, False))
    for title, subset, by_root in sections:
        if not subset:
            continue
        lines.append("## %s（%d）" % (title, len(subset)))
        lines.append("")
        lines.append("| 模块 | %s | 作用 | 符号 | 依赖 | 被引用 | 版本族 | 最新 | 证据pin | 行数 |"
                     % ("目录" if by_root else "子目录"))
        lines.append("|---|---|---|---|---|---:|---:|---|---:|---:|")
        if by_root:
            def place(r):
                return os.path.dirname(r["path"])
        else:
            def place(r):
                return r["subdir"]
        for row in sorted(subset, key=lambda r: (place(r), -r["pinned_by_evidence"], -r["imported_by"], r["path"])):
            purpose = row["purpose"]
            if not purpose:
                hint = ", ".join(row["symbols"][:3])
                purpose = ("⚠ 无docstring；可见符号: " + hint) if hint else "⚠ 无docstring且无公开符号"
            if len(purpose) > 90:
                purpose = purpose[:88] + "…"
            symbols = ", ".join(row["symbols"][:4]) or "—"
            if len(symbols) > 60:
                symbols = symbols[:58] + "…"
            deps = ", ".join(d.split(".")[-1] for d in row["imports"][:3]) or "—"
            fam = str(row["version_family"]) if row["version_family"] > 1 else "—"
            newest_flag = ("是" if row["is_newest_in_family"] else "否") if row["version_family"] > 1 else "—"
            pin = str(row["pinned_by_evidence"]) if row["pinned_by_evidence"] else "—"
            lines.append("| `%s` | %s | %s | %s | %s | %d | %s | %s | %s | %d |" % (
                os.path.basename(row["path"]), place(row) or "—", purpose, symbols, deps,
                row["imported_by"], fam, newest_flag, pin, row["lines"]))
        lines.append("")

    with open(OUT_MD, "w", encoding="utf-8") as stream:
        stream.write("\n".join(lines))

    print("written: %s (%d modules), %s" % (OUT_MD, total, OUT_JSON))
    print("unreviewed: %d, pinned: %d, multi-version: %d" % (unreviewed, pinned, multi))
    print("categories: %s; algorithm modules missing a category: %d" % (
        ", ".join("%s=%d" % (categories.slug(c), by_category[c])
                  for c in categories.section_order(by_category)), len(missing)))


if __name__ == "__main__":
    main()
