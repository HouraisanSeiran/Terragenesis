"""Verify the global coverage view, its controls and exported evidence."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright


def audit(url, output):
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'running', 'pageerrors': [], 'checks': {}}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            for name, width, height in [('desktop', 1440, 900), ('mobile', 390, 844)]:
                page = browser.new_page(viewport={'width': width, 'height': height}, accept_downloads=True)
                page.on('pageerror', lambda error: report['pageerrors'].append(str(error)))
                page.goto(url + '/?workspace=global', wait_until='networkidle')
                page.wait_for_function("surfaceRenderer.state.case?.kind==='global-geometry'")
                assert page.locator('#globalEdge option').count() == 51
                assert page.locator('#view3d').is_disabled()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                canvas = page.locator('#surface')
                canvas.screenshot(path=str(output / (name + '-coverage.png')))
                before = np.asarray(Image.open(output / (name + '-coverage.png')).convert('RGB'))
                assert len(np.unique(before.reshape(-1, 3), axis=0)) > 100
                page.locator('#globalExcluded').uncheck()
                canvas.screenshot(path=str(output / (name + '-accepted.png')))
                after = np.asarray(Image.open(output / (name + '-accepted.png')).convert('RGB'))
                changed = int(np.count_nonzero(np.any(before != after, axis=-1)))
                assert changed > 20
                page.locator('#globalExcluded').check()
                page.select_option('#globalEdge', '0')
                assert page.evaluate('surfaceReview.getSelection().type') == 'excludedEdge'
                with page.expect_download() as download:
                    page.locator('#exportReview').click()
                path = output / (name + '-review.json')
                download.value.save_as(path)
                record = json.loads(path.read_text(encoding='utf-8'))
                assert record['coverage']['declared_edges'] == 673
                assert record['coverage']['accepted_edges'] == 623
                assert record['scope_exclusion']['unresolved_count'] == 50
                assert record['scope_exclusion']['factor_0_1_owner_crossing_count'] == 50
                assert record['publishable'] is False
                assert record['selection']['source_cell_id'] == 88060
                page.screenshot(path=str(output / (name + '-page.png')), full_page=True)
                page.select_option('#reviewProject', 'release')
                page.wait_for_function("surfaceRenderer.state.case?.results?.id==='valley-4'", timeout=90000)
                assert page.locator('#globalGeometryControls').is_hidden()
                report['checks'][name] = {'excluded_layer_changed_pixels': changed, 'exported_edges': 673,
                                         'selected_edge': 88060, 'return_to_results': True}
                page.close()
            browser.close()
        assert not report['pageerrors'], report['pageerrors']
        report['status'] = 'passed'
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.url, args.output)))
