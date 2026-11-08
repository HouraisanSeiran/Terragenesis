"""One lightweight landing for explicitly pinned accepted regional review artifacts."""

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.regional_surface_review import read_bounded_json
from terrain_pipeline.common_infra import publish_bytes, file_sha256


def build_landing(index, *, root=ROOT):
    if (not isinstance(index, dict) or set(index) != {'schema', 'source_identity', 'entries', 'limitations'} or
            index['schema'] != 'regional-single-landing-v1' or
            index['source_identity'] != '81d12179658ed02fefc94883cea1ce32888ff36199952d2bd88f68eb576f8cb2' or
            not isinstance(index['entries'], list) or not 1 <= len(index['entries']) <= 12 or
            not isinstance(index['limitations'], list) or not index['limitations']):
        raise ValueError('known canonical single-region landing index required')
    links = []
    seen = set()
    for entry in index['entries']:
        if not isinstance(entry, dict) or set(entry) != {'id', 'label', 'path', 'sha256', 'scope'}:
            raise ValueError('exact landing entry fields required')
        if any(not isinstance(entry[key], str) or not entry[key] for key in entry):
            raise ValueError('nonempty landing strings required')
        if entry['id'] in seen:
            raise ValueError('unique landing IDs required')
        seen.add(entry['id'])
        path = (root / entry['path']).resolve()
        if not path.is_relative_to(root.resolve()) or not entry['path'].replace('\\', '/').startswith('verification/'):
            raise ValueError('landing must target workspace verification artifacts')
        if file_sha256(path) != entry['sha256']:
            raise ValueError('landing target changed from external fixed SHA')
        href = '/' + entry['path'].replace('\\', '/')
        links.append('<li><a href="' + html.escape(href, quote=True) + '">' + html.escape(entry['label']) +
            '</a><p>' + html.escape(entry['scope']) + '</p><code>SHA256 ' + entry['sha256'] + '</code></li>')
    if any(not isinstance(value, str) or not value for value in index['limitations']):
        raise ValueError('explicit landing limitations required')
    limits = ''.join('<li>' + html.escape(value) + '</li>' for value in index['limitations'])
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>单区域河网审查</title>'
        '<style>body{max-width:1100px;margin:32px auto;font:17px sans-serif;background:#17212c;color:#eee}'
        'a{color:#80cfff}li{margin:20px 0}code{overflow-wrap:anywhere}p{line-height:1.5}</style>'
        '<h1>单区域河网与水量审查</h1><p>Terrain Diffusion生成山地 · 256² / 30m / 58.9824km²。'
        '米制格心原点[-184320,61440]；有限工程边界，不是完整自然流域。</p>'
        '<p>此入口只链接固定SHA产物，不扫描latest，不复制大JSON，不启动模型或水动力。'
        '请用workspace-root静态服务：<code>python -m http.server 8879 --bind 127.0.0.1 --directory "D:/codexwork/山川形意Terragenesis"</code>。'
        '不可假设现有8765是workspace-root。</p><ul>' + ''.join(links) + '</ul>'
        '<h2>限定与未完成</h2><ul>' + limits + '</ul></html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-index', type=Path, required=True)
    parser.add_argument('--run-index-sha256', required=True)
    args = parser.parse_args()
    index = read_bounded_json(args.run_index, expected_sha256=args.run_index_sha256, max_bytes=262144)
    page = build_landing(index)
    output = ROOT / 'verification/regional-joint-review' / ('frozen-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    publish_bytes(output / 'index.html', page.encode('utf-8'))
    publish_bytes(output / 'fixed-index.json', json.dumps(index, allow_nan=False, indent=2).encode())
    publish_bytes(output / 'manifest.json', json.dumps({'external_index_sha256': args.run_index_sha256,
        'exporter_sha256': file_sha256(Path(__file__)), 'files_sha256': {p.name: file_sha256(p) for p in output.iterdir() if p.is_file()}}, indent=2).encode())
    print(output)


if __name__ == '__main__':
    main()
