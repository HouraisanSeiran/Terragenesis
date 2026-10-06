"""Generate an auditable local bibliography without treating failed requests as evidence."""
from pathlib import Path
import json, re

root=Path(__file__).resolve().parent
entries=json.loads((root/'sources.json').read_text(encoding='utf-8'))
ok=[r for r in entries if r.get('http_status')=='200' and r.get('exit_code')==0]
failed=[r for r in entries if r not in ok]
lines=['# 资料索引','',f'本轮请求 {len(entries)} 项，成功保存 {len(ok)} 项，未成功 {len(failed)} 项。成功表示读到了公开资源，不代表运行验证了项目。',
       '', '## 成功保存','', '| ID | 公开来源 | 本地副本 | 字节数 |','|---|---|---|---|']
for r in ok:
    p=root/r['local_file']
    assert p.is_file() and p.stat().st_size==r['bytes']
    lines.append(f"| {r['id']} | [来源]({r['url']}) | [副本]({r['local_file']}) | {r['bytes']} |")
lines+=['','## 未成功获取','','这些失败项不能当作已读取全文的证据。','', '| ID | HTTP 状态 | 来源 |','|---|---|---|']
for r in failed:lines.append(f"| {r['id']} | {r['http_status']} | [链接]({r['url']}) |")
lines+=['','部分论文题录另由 Crossref 查询核对，但失败的批量下载不被改标为成功。完整时间戳、返回状态和文件哈希见 sources.json。','']
(root/'资料索引.md').write_text('\n'.join(lines),encoding='utf-8')
broken=[]
for p in root.glob('*.md'):
    for link in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
        if '://' not in link and not (p.parent/link.split('#')[0]).exists():broken.append((p.name,link))
assert not broken,broken
print(json.dumps({'sources':len(entries),'downloaded':len(ok),'unavailable':len(failed),'local_links_valid':True},ensure_ascii=False))
