"""Read-only, source-bound diagnostic gate before surface-to-3D development."""

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

import numpy as np

from terrain_pipeline import dem_domain, surface_domain_prepare, surface_fine_mosaic
from terrain_pipeline import surface_coast_drop, surface_dynamic_prepare


VERSION = "surface-development-readiness-v1"
KINDS = ("dem", "domain", "mosaic", "drop", "dynamic")
MAX_BUNDLE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
SCOPES = ("static_geometry", "lumped_storage_linear_conductance", "full_dynamic_wave")
MODULES = {
    "dem": (dem_domain, lambda path: dem_domain.load_dem_candidate(path, verify_source=False)),
    "domain": (surface_domain_prepare, lambda path: surface_domain_prepare.load_surface_domains(path, allow_unprepared=True)),
    "mosaic": (surface_fine_mosaic, lambda path: surface_fine_mosaic.load_fine_mosaic(path, allow_unprepared=True)),
    "drop": (surface_coast_drop, surface_coast_drop.load_coast_drop),
    "dynamic": (surface_dynamic_prepare, surface_dynamic_prepare.load_surface_dynamic),
}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate readiness JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("nonfinite readiness JSON value: " + value)


def _digest(path, limit):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("missing or linked input: " + str(path))
    size = path.stat().st_size
    if size <= 0 or size > limit:
        raise ValueError("readiness input size cap: " + str(path))
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if path.stat().st_size != size:
        raise ValueError("readiness input changed while hashing")
    return digest.hexdigest(), size


def _record(kind, path):
    source = Path(path).absolute()
    for component in (source, *source.parents):
        attributes = getattr(os.lstat(component), "st_file_attributes", 0) if component.exists() else 0
        if component.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise ValueError("linked or reparse input path: " + str(component))
    resolved = source.resolve(strict=True)
    digest, size = _digest(resolved, MAX_BUNDLE_BYTES)
    module, loader = MODULES[kind]
    product = loader(resolved)
    if _digest(resolved, MAX_BUNDLE_BYTES) != (digest, size):
        raise ValueError("readiness input changed while loading")
    identity = product["manifest"]["identity_sha256"] if kind == "dem" else product["identity_sha256"]
    if not isinstance(identity, str) or len(identity) != 64:
        raise ValueError("invalid bundle identity")
    module_hash, _ = _digest(Path(module.__file__), MAX_BUNDLE_BYTES)
    return product, {"path": str(resolved), "sha256": digest, "bytes": size,
                     "identity_sha256": identity, "module": module.__name__,
                     "module_sha256": module_hash}


def _diagnose(products, scope):
    dem = products.get("dem")
    domain = products.get("domain")
    mosaic = products.get("mosaic")
    drop = products.get("drop")
    dynamic = products.get("dynamic")
    blockers = []
    facts = {}

    if dem is None:
        blockers.append("dem_bundle_missing")
    else:
        unknown = int(np.count_nonzero(dem["arrays"]["unknown_mask"]))
        facts["dem_unknown_cells"] = unknown
        facts["dem_source_identity"] = dem["manifest"]["identity_sha256"]
        blockers.append("dem_source_replay_not_performed_and_observation_validator_unsupported")
        if unknown:
            blockers.append("dem_unknown_coverage")
        if dem["manifest"]["status"] != "publishable":
            blockers.append("dem_candidate_not_publishable")

    if domain is None:
        blockers.append("domain_bundle_missing")
    else:
        inputs = domain["candidate"]["inputs"]
        facts["domain_source_identity"] = inputs["source_identity"]
        facts["domain_source_kind"] = inputs["source_kind"]
        facts["domain_recovery_ids"] = sorted(item["recovery"]["identity_sha256"] for item in domain["domains"] if item["recovery"])
        if domain["status"] != "prepared":
            blockers.append("domain_not_prepared")
        if inputs["source_kind"] == "engineering_synthetic":
            blockers.append("domain_engineering_synthetic")
        if dem is not None:
            blockers.append("dem_and_domain_source_graph_not_bound")

    if mosaic is None:
        blockers.append("mosaic_bundle_missing")
    else:
        missing = int(np.count_nonzero(np.asarray(mosaic["cell_owner"]) < 0))
        facts["mosaic_missing_cells"] = missing
        facts["mosaic_source_identity"] = mosaic["source_identity"]
        facts["mosaic_proof_ids"] = sorted(mosaic["proofs"])
        if missing or mosaic["status"] != "prepared" or not mosaic["full_domain_mosaic_prepared"]:
            blockers.append("full_domain_mosaic_gap_or_unprepared")
        if domain is not None and not set(facts["domain_recovery_ids"]).issubset(mosaic["proofs"]):
            blockers.append("domain_and_mosaic_proof_graph_mismatch")

    if drop is None:
        blockers.append("drop_bundle_missing")
    else:
        facts["drop_mode"] = drop["mode"]
        facts["drop_attachment_recovery_id"] = drop["attachment"]["recovery_sha256"]
        if drop["mode"] != surface_coast_drop.MODE or not drop["natural_outlet_certified"]:
            blockers.append("coastline_and_natural_outlet_not_certified")
        if domain is not None and facts["drop_attachment_recovery_id"] not in facts["domain_recovery_ids"]:
            blockers.append("drop_and_domain_proof_graph_mismatch")
        if mosaic is not None and facts["drop_attachment_recovery_id"] not in facts["mosaic_proof_ids"]:
            blockers.append("drop_and_mosaic_proof_graph_mismatch")

    if dynamic is None:
        facts["dynamic_scope"] = "not_supplied"
        if scope != "static_geometry":
            blockers.append("dynamic_bundle_missing_for_scope")
    else:
        binding = dynamic["binding"]
        facts["dynamic_scope"] = binding["area_semantics"]
        source_mosaic = binding["source_mosaic"]
        facts["dynamic_source_mosaic_id"] = source_mosaic["identity_sha256"]
        facts["dynamic_source_proof_id"] = binding["source_proof_sha256"]
        facts["dynamic_embedded_proof_ids"] = sorted(source_mosaic["proofs"])
        dynamic_proof = facts["dynamic_source_proof_id"]
        if domain is not None and dynamic_proof not in facts["domain_recovery_ids"]:
            blockers.append("dynamic_and_domain_proof_graph_mismatch")
        if mosaic is not None and dynamic_proof not in facts["mosaic_proof_ids"]:
            blockers.append("dynamic_and_mosaic_proof_graph_mismatch")
        if mosaic is not None:
            embedded_proofs = set(facts["dynamic_embedded_proof_ids"])
            external_proofs = set(facts["mosaic_proof_ids"])
            facts["dynamic_mosaic_artifact_different"] = facts["dynamic_source_mosaic_id"] != mosaic["identity_sha256"]
            if embedded_proofs < external_proofs:
                blockers.append("dynamic_partial_graph_not_full_mosaic")
            elif not embedded_proofs.issubset(external_proofs):
                blockers.append("dynamic_and_mosaic_proof_graph_mismatch")
        if scope == "full_dynamic_wave" and not dynamic["full_dynamic_wave_prepared"]:
            blockers.append("full_dynamic_wave_not_prepared")
        if scope != "static_geometry":
            blockers.append("constant_area_linear_conductance_not_calibrated_section_hydraulics")

    blockers.append("independent_geographic_certification_unsupported")
    return {"ready": False, "blockers": sorted(set(blockers)), "facts": facts,
            "certification": "unsupported_no_independent_evidence_validator"}


def _evaluate(paths, dynamic_scope):
    if dynamic_scope not in SCOPES:
        raise ValueError("unsupported dynamic scope")
    if not isinstance(paths, dict) or not paths or set(paths) - set(KINDS):
        raise ValueError("expected at most five named bundle paths")
    products, bindings = {}, {}
    for kind in KINDS:
        if kind in paths:
            products[kind], bindings[kind] = _record(kind, paths[kind])
    if "domain" in products and products["domain"].get("kind") != "evaluation":
        raise ValueError("domain bundle must be an evaluation")
    return {"format": VERSION, "dynamic_scope": dynamic_scope, "bundles": bindings,
            "diagnosis": _diagnose(products, dynamic_scope)}


def prepare_readiness(paths, *, dynamic_scope="lumped_storage_linear_conductance"):
    return _evaluate(paths, dynamic_scope)


def _canonical_json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid readiness JSON types") from error


def save_readiness(manifest, path):
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    validated = load_readiness_dict(manifest)
    payload = (json.dumps(validated, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ValueError("readiness manifest size cap")
    descriptor, temporary = tempfile.mkstemp(prefix=".readiness-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        stored = json.loads(Path(temporary).read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                            parse_constant=_constant)
        if _canonical_json(stored) != _canonical_json(validated):
            raise ValueError("readiness temporary validation failed")
        os.link(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_readiness_dict(manifest):
    if (not isinstance(manifest, dict) or set(manifest) != {"format", "dynamic_scope", "bundles", "diagnosis"} or
            manifest["format"] != VERSION or manifest["dynamic_scope"] not in SCOPES or
            not isinstance(manifest["bundles"], dict) or not manifest["bundles"] or
            set(manifest["bundles"]) - set(KINDS)):
        raise ValueError("invalid readiness manifest schema")
    paths = {}
    for kind, binding in manifest["bundles"].items():
        if (not isinstance(binding, dict) or set(binding) != {"path", "sha256", "bytes", "identity_sha256", "module", "module_sha256"} or
                not isinstance(binding["path"], str) or not Path(binding["path"]).is_absolute()):
            raise ValueError("invalid readiness bundle binding")
        paths[kind] = binding["path"]
    current = _evaluate(paths, manifest["dynamic_scope"])
    if _canonical_json(current) != _canonical_json(manifest):
        raise ValueError("readiness conclusion or bundle identity changed")
    return current


def load_readiness(path):
    source = Path(path)
    _digest(source, MAX_MANIFEST_BYTES)
    manifest = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    return load_readiness_dict(manifest)
