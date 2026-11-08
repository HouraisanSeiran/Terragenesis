"""Build a static first-party module catalog without importing application code."""
import argparse
import ast
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys

try:  # run as `python tools/build_module_catalog.py`
    import module_categories as categories
except ImportError:  # imported as `tools.build_module_catalog`
    from tools import module_categories as categories

ROOTS = ('terrain_pipeline', 'diffusion', 'vdm_diffusion', 'tools', 'tests', 'web-preview', 'src')
EXTENSIONS = {'.py', '.java', '.js', '.mjs', '.html', '.css', '.ps1', '.gradle'}
SKIP = {'__pycache__', 'node_modules', '.git', '.venv', 'venv'}
ROOT_FILES = ('build.gradle', 'settings.gradle', 'start-diffusion.ps1')
OUTPUT = Path('docs/architecture/module-catalog')


def source_paths(root):
    found = []
    for name in ROOTS:
        folder = root / name
        if not folder.is_dir() or folder.is_symlink():
            continue
        for directory, subdirs, files in os.walk(folder, followlinks=False):
            subdirs[:] = sorted(d for d in subdirs if d not in SKIP and not (Path(directory) / d).is_symlink())
            for filename in sorted(files):
                path = Path(directory) / filename
                if path.suffix in EXTENSIONS and not path.is_symlink():
                    found.append(path.relative_to(root).as_posix())
    found.extend(name for name in ROOT_FILES if (root / name).is_file())
    return sorted(found)


def python_details(text, relative):
    tree = ast.parse(text, filename=relative)
    symbols = [n.name for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
    module = relative[:-3].replace('/', '.')
    package = module.rsplit('.', 1)[0] if '.' in module else ''
    if relative.endswith('/__init__.py'):
        package = module.rsplit('.', 1)[0]
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            pieces = package.split('.') if package else []
            prefix = '.'.join(pieces[:len(pieces) - node.level + 1]) if node.level else ''
            base = '.'.join(x for x in (prefix, node.module) if x)
            imports.add(base)
            imports.update(base + '.' + alias.name for alias in node.names)
    return ast.get_docstring(tree), symbols, sorted(imports), categories.declared_category(tree)


def classify(path):
    root, name = path.split('/')[0], Path(path).name
    if root == 'tests':
        return 'test'
    if root == 'src':
        return 'minecraft-test' if path.startswith('src/test/') else 'minecraft-consumer'
    if root == 'web-preview':
        return 'presentation-adapter' if name.endswith('.py') else 'presentation'
    if root == 'tools':
        if any(word in name for word in ('legacy', 'replay')):
            return 'explicit-legacy-tool'
        return 'audit-tool' if name.startswith(('audit_', 'verify_', 'inspect_')) else 'offline-tool'
    if root in ('diffusion', 'vdm_diffusion'):
        return 'generation-support'
    if root == 'terrain_pipeline':
        return 'algorithm-or-io'
    return 'build-launch'


def leading_comment(text):
    text = text.lstrip('\ufeff \t\r\n')
    match = re.match(r'(?:/\*+|<!--)(.*?)(?:\*/|-->)', text, re.S)
    if match:
        value = re.sub(r'^\s*\* ?', '', match.group(1), flags=re.M).strip()
        return value if len(value) > 8 else None
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('#!'):
            continue
        if stripped.startswith(('#', '//')):
            lines.append(stripped.lstrip('#/ ').strip())
        else:
            break
    return ' '.join(lines) or None


def collect(root, annotations):
    labels, registry = categories.load_registry(root)
    paths = source_paths(root)
    modules = {}
    for path in paths:
        if path.endswith('.py'):
            name = path[:-3].replace('/', '.')
            if name.endswith('.__init__'):
                name = name[:-9]
            modules[name] = path
    entries = []
    for path in paths:
        raw = (root / path).read_bytes()
        symbols, imports, error, declared = [], [], None, None
        try:
            text = raw.decode('utf-8-sig')
            if path.endswith('.py'):
                doc, symbols, imports, declared = python_details(text, path)
            else:
                doc = leading_comment(text)
                symbols = re.findall(r'\b(?:class|interface|enum|function)\s+(\w+)', text)[:12]
        except (UnicodeError, SyntaxError) as exc:
            doc, error = None, str(exc)
        note = annotations.get(path, {})
        purpose = note.get('purpose') or doc or '职责待人工核对；仅登记可确认的静态结构'
        evidence = 'manual-reviewed' if note.get('purpose') else ('source-docstring' if doc and path.endswith('.py') else 'source-comment' if doc else 'unreviewed')
        category, category_source = categories.resolve(path, declared, registry)
        entries.append({'path': path, 'role': note.get('role', classify(path)), 'stage': note.get('stage', 'shared-or-unmapped'),
            'category': category, 'category_source': category_source, 'algorithm_module': categories.is_algorithm_module(path),
            'purpose': purpose, 'purpose_evidence': evidence, 'symbols': symbols,
            'python_imports': imports, 'local_import_targets': sorted({modules[n] for n in imports if n in modules and modules[n] != path}),
            'static_importers': [], 'sha256': hashlib.sha256(raw).hexdigest(), 'parse_error': error})
    lookup = {e['path']: e for e in entries}
    for entry in entries:
        for target in entry['local_import_targets']:
            lookup[target]['static_importers'].append(entry['path'])
    return {'schema': 'terragenesis-module-catalog-v1', 'scope_roots': list(ROOTS), 'root_files': list(ROOT_FILES),
        'notes': ['Static structure, not runtime coverage or certification.', 'Local imports/importers are Python AST edges only; JS/Java symbols are lexical hints.',
                  'Source descriptions are author claims, not independent semantic verification.'],
        'category_registry': categories.REGISTRY.as_posix(), 'category_labels': labels,
        'algorithm_roots': list(categories.ALGORITHM_ROOTS),
        'algorithm_modules_missing_category': sorted(e['path'] for e in entries if e['algorithm_module'] and e['category'] is None),
        'annotation_paths_missing_from_scope': sorted(set(annotations) - set(paths)), 'entries': entries}


def cell(text):
    return re.sub(r'\s+', ' ', str(text)).replace('|', '\\|').strip()


def layer_group(path):
    return path.split('/')[0] if '/' in path else 'root'


def page_groups(entries, labels):
    """(file prefix, title, entries) per page group: algorithm categories first, then layers.

    Algorithm modules (.py below categories.ALGORITHM_ROOTS) are grouped by category;
    every other file keeps its top-level source root as before.
    """
    algorithm = [e for e in entries if e['algorithm_module']]
    groups = []
    for category in categories.section_order(e['category'] for e in algorithm):
        selected = [e for e in algorithm if e['category'] == category]
        groups.append((f'category-{categories.slug(category)}', '大类 ' + categories.heading(category, labels), selected))
    rest = [e for e in entries if not e['algorithm_module']]
    for group in sorted({layer_group(e['path']) for e in rest}):
        groups.append((group, group, [e for e in rest if layer_group(e['path']) == group]))
    return groups


def render(catalog):
    entries = catalog['entries']
    labels = catalog.get('category_labels', {})
    products = {'catalog.json': json.dumps(catalog, ensure_ascii=False, indent=2) + '\n'}
    algorithm = [e for e in entries if e['algorithm_module']]
    index = ['# 全仓一方源码模块职责台账', '', '此目录为自动生成的逐文件静态台账，不是各阶段已完成/已认证清单。', '',
        '人工职责覆盖在 annotations.json 管理，生成器不改该文件。源码正文说明与人工审阅分开标记；缺少说明不按文件名猜测职责。', '',
        '## 算法大类', '',
        f"算法模块（{'、'.join(categories.ALGORITHM_ROOTS)} 下的 .py）按编码规范 §11 的大类分表：模块级 `CATEGORY = \"...\"` 声明优先，其次 "
        f"[归类表](../{categories.REGISTRY.name})登记。只是逻辑分类，不改文件位置和 import；`?` 为已登记、待用户确认。tools/tests 等不要求大类，仍按源码范围分表。", '',
        '| 大类 | 模块数 | 声明 | 登记 |', '| --- | --- | --- | --- |']
    for category in categories.section_order(e['category'] for e in algorithm):
        members = [e for e in algorithm if e['category'] == category]
        index.append(f"| {cell(categories.heading(category, labels))} | {len(members)} | "
                     f"{sum(e['category_source'] == 'declared' for e in members)} | {sum(e['category_source'] == 'registry' for e in members)} |")
    index += ['', f"缺大类的算法模块：{catalog.get('algorithm_modules_missing_category', [])}。", '',
        '## 分表', '', '| 分组 | 文件数 | 分表 |', '| --- | --- | --- |']
    for group, title, selected in page_groups(entries, labels):
        for number, offset in enumerate(range(0, len(selected), 120), 1):
            name = f'{group}-{number:02d}.md'
            table = [f'# {title} 模块表 {number}', '', '职责原文不代表认证；静态调用者只含Python AST本地导入。完整符号/依赖/hash见 catalog.json。', '',
                '| 模块 | 类别／阶段 | 职责说明 | 说明依据 | 顶层符号／静态导入者数 |', '| --- | --- | --- | --- | --- |']
            for entry in selected[offset:offset + 120]:
                link = '../../../' + entry['path']
                summary = entry['purpose'][:220] + ('…' if len(entry['purpose']) > 220 else '')
                table.append(f"| [{entry['path']}]({link}) | {cell(entry['role'])} / {cell(entry['stage'])} | {cell(summary)} | {entry['purpose_evidence']} | {cell(', '.join(entry['symbols'][:5])) or '(无顶层命名声明)'} / {len(entry['static_importers'])} |")
            products[name] = '\n'.join(table) + '\n'
            index.append(f'| {cell(title)} | {len(selected[offset:offset + 120])} | [{name}]({name}) |')
    evidence = Counter(e['purpose_evidence'] for e in entries)
    index += ['', f"共 **{len(entries)}** 个文件；说明依据计数：`{dict(sorted(evidence.items()))}`。",
        f"解析/解码错误：{sum(e['parse_error'] is not None for e in entries)}。人工标注未匹配路径：{catalog['annotation_paths_missing_from_scope']}。", '',
        '## 范围与排除', '',
        '- 活跃一方源码逐文件覆盖：terrain_pipeline、diffusion、vdm_diffusion、tools、tests、web-preview、src，以及根构建/启动入口。tests和tools有独立角色，不当成生产算法。',
        '- legacy-code：冻结历史复验源码，见[归档规范](../../../legacy-code/README.md)，不重复计入活跃模块。service-0.9.0、backups、.claude/worktrees：历史/副本，不作为当前调用者。',
        '- vendor、runtime、node_modules、models：第三方源码/运行环境/权重；data、cache、build、dist、preview、verification、各run-*和deltaRCM_Output：数据/构建/结果/冻结证据；不作为一方活跃算法。',
        '- docs、research、algorithm、river-system、minecraft-mod、bootstrap-assets、.scratch：文档、清单、实验和交付记录；按目录身份管理，不将内部实验脚本登记为默认生产模块。其余根临时数据/日志不归为模块。',
        '- .git、.vantaloom等运行元数据不扫描；不读凭据、环境配置和数据内容。', '',
        '## 维护', '',
        '```powershell', 'runtime/venv/Scripts/python.exe -B tools/build_module_catalog.py --write',
        'runtime/venv/Scripts/python.exe -B tools/build_module_catalog.py --check', '```', '',
        '新增/删除/移动源码或职责改变时，先更新 annotations.json（人工确认的用途/阶段），再重新生成。--check 对比文件覆盖、内容哈希和全部生成表，不会写入或替代测试。',
        '自动说明只取模块docstring/首注释；source-comment可能只是版权/格式声明，需人工复核。shared-or-unmapped表示尚未完成阶段映射，不能解释为无用文件。静态无调用者也不能作为删除依据：动态导入、反射、命令行、HTTP/配置、外部消费者和源码pin须另审。', '',
        '具体方法、现有入口与设计缺口见[工程实现说明](../implementation-guide.md)。']
    products['README.md'] = '\n'.join(index) + '\n'
    return products


def update(root, write=False):
    folder = root / OUTPUT
    annotations_path = folder / 'annotations.json'
    annotations = json.loads(annotations_path.read_text(encoding='utf-8')) if annotations_path.exists() else {}
    products = render(collect(root, annotations))
    expected = set(products)
    managed = re.compile(r'^(?:' + '|'.join(re.escape(x) for x in (*ROOTS, 'root')) + r'|category-[A-Za-z0-9]+)-\d+\.md$')
    existing = {p.name for p in folder.glob('*.md') if p.name == 'README.md' or managed.fullmatch(p.name)}
    existing |= {p.name for p in folder.glob('catalog.json')}
    changed = [name for name, text in products.items() if not (folder / name).exists() or (folder / name).read_bytes() != text.encode('utf-8')]
    stale = sorted(existing - expected)
    if write:
        folder.mkdir(parents=True, exist_ok=True)
        for name in changed:
            (folder / name).write_text(products[name], encoding='utf-8', newline='\n')
        for name in stale:
            (folder / name).unlink()
    return changed + stale


def missing_categories(root):
    """Algorithm modules with no usable category (no valid declaration and no valid registry entry)."""
    return collect(root, {})['algorithm_modules_missing_category']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    drift = update(root, write=args.write)
    missing = missing_categories(root)
    print(json.dumps({'mode': 'write' if args.write else 'check', 'changed_products': drift,
                      'algorithm_modules_missing_category': missing}, ensure_ascii=False))
    return 1 if args.check and (drift or missing) else 0


if __name__ == '__main__':
    raise SystemExit(main())
