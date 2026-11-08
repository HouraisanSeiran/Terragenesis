"""Render pinned official PDF evidence; no georeferencing or inferred river geometry."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_natural_mouth_evidence import PDF_SHA256


def render(pdf_path, runtime, output):
    sys.path.insert(0, str(runtime))
    import pypdfium2

    pdf_path = Path(pdf_path).resolve(strict=True)
    if file_sha256(pdf_path) != PDF_SHA256:
        raise ValueError("official primary PDF pin mismatch")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".mouth-page-stage-", dir=output.parent))
    try:
        document = pypdfium2.PdfDocument(str(pdf_path))
        pages = []
        titles = {11: "河流水系，正文印刷第4页", 152: "附图1 水资源利用分区与行政分区",
                  153: "附图2 雨量站点分布，含洪家塔流量站", 154: "附图3 现状水资源系统网络概化",
                  155: "附图4 现状及规划水源工程布置，含杨梅岭水库", 156: "附图5 水功能区划"}
        for number, title in titles.items():
            page = document[number - 1]
            bitmap = page.render(scale=2)
            image = bitmap.to_pil()
            filename = f"page-{number}.png"
            image.save(stage / filename)
            pages.append({"pdf_physical_page": number, "title": title, "filename": filename,
                          "sha256": file_sha256(stage / filename), "pixel_shape_xy": list(image.size),
                          "pdf_page_points_xy": list(page.get_size()),
                          "coordinate_reference_system": None, "georeferenced": False})
            image.close()
            bitmap.close()
            page.close()
        document.close()
        if file_sha256(pdf_path) != PDF_SHA256:
            raise ValueError("official primary PDF changed during rendering")
        report = {"schema": "natural-mouth-official-pdf-page-evidence-v1", "utc": datetime.now(timezone.utc).isoformat(),
                  "source_path": str(pdf_path), "source_sha256": PDF_SHA256,
                  "renderer": "pypdfium2", "renderer_version": str(pypdfium2.PYPDFIUM_INFO),
                  "renderer_script_sha256": file_sha256(__file__), "scale_pixels_per_pdf_point": 2,
                  "pages": pages, "natural_outlet_verified": False,
                  "scope": "official cartographic evidence images; no traced/coordinated mouth or hydraulic bed",
                  "acquisition_date": "2026-10-01 UTC", "map_date_requires_visual_reading": True}
        publish_bytes(stage / "manifest.json", json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
        os.rename(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=Path("D:/geography/01-完整流域样本/data/ninghai_water_plan_ch3.pdf"))
    parser.add_argument("--runtime", type=Path, default=ROOT / ".scratch/terrain-framework/pdf-runtime")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = render(args.pdf, args.runtime, args.output)
    print(json.dumps({"output": str(args.output), "pages": len(report["pages"])}))


if __name__ == "__main__":
    main()
