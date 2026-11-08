# -*- coding: utf-8 -*-
"""Read-only query of one prepared river-backbone product.

This tool answers questions from an already published product directory. It never routes,
never re-derives D8, never fills a depression and never re-accumulates discharge: a load
verifies bytes, budget, headers, identity and the internal coherence of the stored arrays,
and the query then indexes those stored arrays.

Scope
-----
``census``            counts, declared gates, quantity list, hydraulic availability
``reach``             one reach row plus its ordered native trace
``cell``              one world cell: area, area status, geometry, quantities
``scope``             one named read scope through the same index

Refusals are specific
---------------------
A point outside the support, a point that does not land on a cell reference point, an
unresolved cell, a cell outside the prepared channel, an undeclared quantity and anything
this product does not contain (water depth, stage, hydraulics, a natural outlet, a
permanent terminal) are all refused by name, never answered with a zero or a blank.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "river-backbone-query-v1"


def _load(directory, expected_identity):
    from terrain_pipeline.surface_rivers.metric_backbone_product import (
        load_backbone_product,
    )

    return load_backbone_product(directory, expected_identity_sha256=expected_identity)


def _emit(payload, path):
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path:
        Path(path).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


def run(arguments):
    from terrain_pipeline.surface_rivers import metric_backbone_product as product_module

    product = _load(arguments.product, arguments.expected_identity)
    answer = {
        "schema": SCHEMA,
        "product": str(Path(arguments.product)),
        "product_identity_sha256": product["identity_sha256"],
        "read_only": True,
        "reaccumulated": False,
        "policy": ("this query indexes the stored arrays only; it never re-runs the network "
                   "accumulation and never re-derives the D8 topology"),
    }
    if arguments.mode == "census":
        answer["census"] = product_module.census(product)
        return _emit(answer, arguments.output)
    if arguments.mode == "reach":
        if not arguments.reach_id:
            raise SystemExit("--reach-id is required for --mode reach")
        product_module.require_scope("backbone_path")
        answer["reach"] = product_module.query_reach(product, reach_id=arguments.reach_id)
        return _emit(answer, arguments.output)
    if arguments.mode == "cell":
        if arguments.point_native is None:
            raise SystemExit("--point-native X Z is required for --mode cell")
        product_module.require_scope("backbone_area")
        point = [int(arguments.point_native[0]), int(arguments.point_native[1])]
        answer["cell"] = product_module.query_reach(product, world_native_xz=point)
        return _emit(answer, arguments.output)
    if arguments.mode == "scope":
        if not arguments.scope:
            raise SystemExit("--scope is required for --mode scope")
        product_module.require_scope(arguments.scope)
        if arguments.point_native is not None:
            point = [int(arguments.point_native[0]), int(arguments.point_native[1])]
            answer["answer"] = product_module.query_reach(product, world_native_xz=point)
        elif arguments.reach_id:
            answer["answer"] = product_module.query_reach(product, reach_id=arguments.reach_id)
        else:
            answer["answer"] = product_module.census(product)
        return _emit(answer, arguments.output)
    raise SystemExit("unknown mode %r" % (arguments.mode,))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--product", required=True)
    parser.add_argument("--mode", required=True,
                        choices=("census", "reach", "cell", "scope"))
    parser.add_argument("--reach-id")
    parser.add_argument("--point-native", nargs=2, type=int, metavar=("X", "Z"),
                        help="signed native (x, z) of a cell reference point")
    parser.add_argument("--scope")
    parser.add_argument("--expected-identity")
    parser.add_argument("--output")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
