"""Explicit serial topology-only publication of an accepted derived TD source."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

for variable in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import psutil

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_accepted_water_morphology import load_accepted_water_morphology, KINDS, FLAGS
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy, save_basin_hierarchy, load_basin_hierarchy
from terrain_pipeline.td_basin_source import load_td_source_bundle
from terrain_pipeline.td_hour_pages_acceptance_io import _json, _sha
from terrain_pipeline.td_surface_reaches import _hash, _plain

SCHEMA = "td-accepted-candidate-topology-review-v1"
DEPENDENCIES = ("tools/rebuild_td_accepted_candidate_topology.py",
    "terrain_pipeline/td_accepted_water_morphology.py", "terrain_pipeline/td_hour_pages_acceptance_io.py",
    "terrain_pipeline/td_basin_hierarchy.py", "terrain_pipeline/td_basin_source.py",
    "terrain_pipeline/mountain_source_adapter.py")
REVIEW_FLAGS = {**FLAGS, "publishable": False}


def memory():
    info = psutil.Process().memory_info()
    rss = int(getattr(info, "peak_wset", info.rss))
    private = getattr(info, "peak_pagefile", None)
    if type(private) is not int or not 0 < private <= 1073741824 or not 0 < rss <= 1073741824:
        raise MemoryError("topology job requires peak RSS/private <=1GiB")
    return dict(peak_rss_bytes=rss, peak_private_bytes=private, within_1GiB=True)


def _parent(record):
    _sha(record["expected_identity"])
    raw = _json(dict(path=record["path"], expected_sha256=record["expected_sha256"]))
    inputs = raw["inputs"]
    return _plain(load_accepted_water_morphology(record["path"],
        expected_sha256=record["expected_sha256"], expected_identity=record["expected_identity"], **inputs))


def _inputs(parent_record, source_record, candidate_id):
    if candidate_id not in KINDS:
        raise ValueError("explicit derived candidate required")
    parent = _parent(parent_record)
    if source_record != parent["candidates"][candidate_id]["source"]:
        raise ValueError("external source differs from accepted candidate")
    source = load_td_source_bundle(**source_record)
    if source["metadata"]["source_sha256"] != parent["inputs"]["source_record"]["expected_sha256"]:
        raise ValueError("derived source original artifact chain mismatch")
    return parent, source


def _chain(hierarchy, source):
    if (hierarchy["metadata"]["source_identity_sha256"] != source["identity_sha256"] or
            hierarchy["metadata"]["source_metadata"] != source["metadata"]):
        raise ValueError("rebuilt topology actual source identity mismatch")
    for name in ("height_m", "valid_mask", "protected_mask", "open_boundary_mask"):
        if not np.array_equal(hierarchy["arrays"][name], source["arrays"][name]):
            raise ValueError("rebuilt topology actual source bed/masks mismatch")
    for name in ("spacing_m", "origin_m_xz"):
        if hierarchy["metadata"][name] != source["metadata"][name]:
            raise ValueError("rebuilt topology source grid mismatch")


def _counts(hierarchy):
    arrays = hierarchy["arrays"]
    return dict(cells=int(arrays["valid_mask"].sum()), nodes=len(arrays["node_parent"]),
        leaves=len(np.unique(arrays["contribution_owner"][arrays["valid_mask"]])),
        faces=len(arrays["face_cells"]), terminals=int(np.count_nonzero(arrays["receiver"] == -1)))


def load_topology_index(path, *, expected_sha256, expected_identity, parent_record, source_record, _staging_directory=None):
    result = _json(dict(path=str(path), expected_sha256=expected_sha256))
    unsigned = {name: value for name, value in result.items() if name != "identity_sha256"}
    if result.get("schema") != SCHEMA or _hash(unsigned) != expected_identity or result.get("identity_sha256") != expected_identity:
        raise ValueError("topology index external identity/schema mismatch")
    if result["parent_manifest"] != parent_record or result["source"] != source_record:
        raise ValueError("topology external parent/source pins mismatch")
    parent, source = _inputs(parent_record, source_record, result["candidate_id"])
    if (result["original_source_record"] != parent["inputs"]["source_record"] or
            result["selection"] != "baseline pending" or result["recoupling_required"] is not True or
            result["hydrology_solved"] is not False or result["flags"] != REVIEW_FLAGS):
        raise ValueError("topology provenance/readiness claims rejected")
    resource = result["resource"]
    if resource.get("within_1GiB") is not True or any(type(resource.get(name)) is not int or
            not 0 < resource[name] <= 1073741824 for name in ("peak_rss_bytes", "peak_private_bytes")):
        raise ValueError("topology resource evidence rejected")
    hierarchy_record = dict(result["hierarchy"])
    actual_path = Path(path).absolute().parent / "hierarchy.npz"
    declared_path = actual_path if _staging_directory is None else Path(_staging_directory).absolute() / "hierarchy.npz"
    if Path(hierarchy_record["path"]).absolute() != declared_path:
        raise ValueError("topology hierarchy layout rejected")
    if _staging_directory is not None and (not actual_path.parent.name.startswith(".accepted-topology-") or
            actual_path.parent.parent != declared_path.parent.parent):
        raise ValueError("internal topology staging layout rejected")
    if actual_path.is_symlink():
        raise ValueError("topology hierarchy symlink rejected")
    hierarchy_record["path"] = str(actual_path)
    hierarchy = load_basin_hierarchy(**hierarchy_record)
    _chain(hierarchy, source)
    if result["counts"] != _counts(hierarchy):
        raise ValueError("topology counts mismatch")
    if set(result["code_sha256"]) != set(DEPENDENCIES) or any(file_sha256(ROOT / name) != digest for name, digest in result["code_sha256"].items()):
        raise ValueError("topology frozen dependencies changed")
    memory()
    return result


def publish_topology(parent_record, source_record, directory, *, candidate_id):
    pins = {name: file_sha256(ROOT / name) for name in DEPENDENCIES}
    parent, source = _inputs(parent_record, source_record, candidate_id)
    memory()
    directory = Path(directory).absolute()
    if directory.exists():
        raise FileExistsError(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".accepted-topology-", dir=directory.parent))
    try:
        hierarchy = build_basin_hierarchy(source)
        _chain(hierarchy, source)
        save_basin_hierarchy(staging / "hierarchy.npz", hierarchy)
        record = dict(path=str(directory / "hierarchy.npz"), expected_sha256=file_sha256(staging / "hierarchy.npz"),
                      expected_identity=hierarchy["identity_sha256"])
        result = dict(schema=SCHEMA, parent_manifest=parent_record, source=source_record, hierarchy=record,
            original_source_record=parent["inputs"]["source_record"], candidate_id=candidate_id,
            counts=_counts(hierarchy), resource=memory(), code_sha256=pins,
            selection="baseline pending", recoupling_required=True, hydrology_solved=False, flags=REVIEW_FLAGS)
        result["identity_sha256"] = _hash(result)
        publish_bytes(staging / "index.json", json.dumps(result, indent=2, allow_nan=False).encode("utf-8"))
        load_topology_index(staging / "index.json", expected_sha256=file_sha256(staging / "index.json"),
            expected_identity=result["identity_sha256"], parent_record=parent_record, source_record=source_record, _staging_directory=directory)
        if any(file_sha256(ROOT / name) != digest for name, digest in pins.items()):
            raise ValueError("topology dependencies changed before publication")
        for external in (parent_record, source_record, parent["inputs"]["source_record"]):
            if file_sha256(external["path"]) != external["expected_sha256"]:
                raise ValueError("topology parent/source changed before publication")
        result["resource"] = memory()
        result.pop("identity_sha256")
        result["identity_sha256"] = _hash(result)
        publish_bytes(staging / "final-index.json", json.dumps(result, indent=2, allow_nan=False).encode("utf-8"))
        (staging / "index.json").unlink()
        (staging / "final-index.json").rename(staging / "index.json")
        staging.rename(directory)
        return result
    except BaseException:
        shutil.rmtree(staging)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ("parent", "source"):
        parser.add_argument("--" + role, type=Path, required=True)
        parser.add_argument("--" + role + "-sha256", required=True)
        parser.add_argument("--" + role + "-identity", required=True)
    parser.add_argument("--candidate-id", choices=tuple(KINDS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parent = dict(path=str(args.parent.resolve(strict=True)), expected_sha256=args.parent_sha256, expected_identity=args.parent_identity)
    source = dict(path=str(args.source.resolve(strict=True)), expected_sha256=args.source_sha256, expected_identity=args.source_identity)
    if _json(dict(path=parent["path"], expected_sha256=parent["expected_sha256"]))["inputs"]["scope"] != "original_td":
        parser.error("real CLI requires original_td accepted geometry")
    result = publish_topology(parent, source, args.output, candidate_id=args.candidate_id)
    index = args.output.absolute() / "index.json"
    print(json.dumps(dict(path=str(index), expected_sha256=file_sha256(index), expected_identity=result["identity_sha256"])))


if __name__ == "__main__":
    main()
