"""同坐标 30 m 环境联合产品的**只读**查询工具。

不生成、不推进、不改写产品：只从已保存的 ``.npz`` + ``.json`` 取字段。
某点缺少发布状态时按字段状态如实报告，不当零。

用法
----
    python -B tools/query_environment_world.py --product <dir> \\
        --x 1266450 --z 1290990 [--fields elevation_m,land_cover_index]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from terrain_pipeline.environment_product import world_load as load, world_query as query  # noqa: E402


ARRAYS = "environment-world-arrays.npz"
RECORD = "environment-world.json"


def _json_safe(value):
    """Turn a queried value into JSON-safe data: non-finite becomes ``null``.

    A pending field carries NaN by design (see ``environment_world_product``). Emitting
    NaN would produce invalid JSON, and substituting 0 would fabricate a measurement.
    ``None`` is the only honest encoding, and the per-field ``status`` next to it says
    why the value is missing.
    """
    array = np.asarray(value, np.float64)
    if array.ndim == 0:
        number = float(array)
        return number if math.isfinite(number) else None
    plain = array.tolist()

    def clean(item):
        if isinstance(item, list):
            return [clean(element) for element in item]
        return item if math.isfinite(item) else None

    return clean(plain)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--product", required=True, help="产品目录（含 npz + json）")
    parser.add_argument("--x", type=float, action="append", required=True,
                        help="查询点 x（米，可重复）")
    parser.add_argument("--z", type=float, action="append", required=True,
                        help="查询点 z（米，可重复）")
    parser.add_argument("--fields", default=None,
                        help="要取回的字段（逗号分隔）；缺省返回全部")
    parser.add_argument("--accept-offset-m", type=float, default=None,
                        help="显式接受的最大偏移（米）；缺省要求精确命中")
    parser.add_argument("--expected-world-identity", default=None,
                        help="要求产品的 world_identity 与此一致")
    arguments = parser.parse_args(argv)

    if len(arguments.x) != len(arguments.z):
        parser.error("--x 与 --z 数量必须一致")

    product = load(os.path.join(arguments.product, ARRAYS),
                    os.path.join(arguments.product, RECORD),
                    expected_world_identity=arguments.expected_world_identity)
    result = query(product, arguments.x, arguments.z,
                   accept_offset_m=arguments.accept_offset_m)

    wanted = None
    if arguments.fields:
        wanted = [name.strip() for name in arguments.fields.split(",") if name.strip()]
        unknown = [name for name in wanted if name not in product.arrays]
        if unknown:
            parser.error("产品中不存在字段：%r" % (unknown,))

    rows = []
    for position in range(result["cells"]):
        row = {
            "x_m": float(arguments.x[position]),
            "z_m": float(arguments.z[position]),
            "cell_index": int(result["cell_index"][position]),
            "offset_m": float(result["offset_m"][position]),
        }
        for name in (wanted if wanted is not None else sorted(product.arrays)):
            value = result[name][:, position] if product.arrays[name].ndim == 2 \
                else result[name][position]
            row[name] = _json_safe(np.asarray(value))
            row[name + "__status"] = product.status[name]
        rows.append(row)

    print(json.dumps({
        "product": os.path.relpath(arguments.product, ROOT).replace(os.sep, "/"),
        "world_identity": product.world_identity,
        "cells_in_product": product.cells,
        "query": rows,
        "snapped": False,
        "read_only": True,
        "note": "query 不生成、不推进、不改写产品；缺来源字段按其状态如实报告",
    }, ensure_ascii=False, indent=1, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
