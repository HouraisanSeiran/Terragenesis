"""Explicit, hash-pinned replay of the archived metric VDM fault v1.

Nothing is loaded on import. The original source bytes remain unchanged;
replay redirects only their local imports and preparation data root into an
isolated module namespace. Current generation must use metric_vdm_fault_v2.
"""

import ast
import hashlib
import json
from pathlib import Path
import sys
import threading
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "legacy-code" / "metric-vdm-fault-v1"
MANIFEST_SHA256 = "79f5a568db4820da1f6c429f41fd2071d733db54724d40936254e7d4152d408d"
_BEFORE_FILES = frozenset({
    "terrain_pipeline/metric_vdm_fault.py", "terrain_pipeline/metric_vdm_fault_v2.py",
    "terrain_pipeline/metric_vdm.py", "terrain_pipeline/metric_vdm_forms.py",
    "terrain_pipeline/mountain_source_adapter.py", "terrain_pipeline/rainfall_runoff.py",
    "tools/prepare_metric_vdm_fault.py", "tools/prepare_metric_vdm_fault_v2.py",
    "tools/audit_metric_vdm_fault.py", "tests/test_metric_vdm_fault.py",
    "tests/test_metric_vdm_fault_v2.py",
})
_MODULE_ORDER = (
    "terrain_pipeline.rainfall_runoff", "terrain_pipeline.mountain_source_adapter",
    "terrain_pipeline.metric_vdm", "terrain_pipeline.metric_vdm_forms",
    "terrain_pipeline.metric_vdm_fault", "terrain_pipeline.metric_vdm_fault_v2",
    "tools.prepare_metric_vdm_fault", "tools.prepare_metric_vdm_fault_v2",
    "tools.audit_metric_vdm_fault",
)
_CACHE = {}
_LOCK = threading.RLock()


def verify_archive(archive_dir=None):
    """Reject source and manifest rewrites against the independent trusted pin."""
    archive = Path(archive_dir or ARCHIVE).resolve(strict=True)
    manifest_bytes = (archive / "manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256:
        raise ValueError("legacy fault manifest SHA256 mismatch")
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema") != "metric-vdm-fault-before-snapshot-v1":
        raise ValueError("legacy fault manifest schema mismatch")
    records = manifest.get("files", [])
    if len(records) != len(_BEFORE_FILES) or {entry["original_path"] for entry in records} != _BEFORE_FILES:
        raise ValueError("legacy fault source list mismatch")
    sources = {}
    for entry in records:
        relative = entry["original_path"]
        if entry["archive_path"] != relative:
            raise ValueError("legacy fault archive mapping mismatch")
        path = (archive / relative).resolve(strict=True)
        if not path.is_relative_to(archive):
            raise ValueError("legacy fault source escapes archive")
        data = path.read_bytes()
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError("legacy fault source SHA256 mismatch: " + relative)
        sources[relative] = data
    return archive, sources


class _ReplayImports(ast.NodeTransformer):
    _path_bootstrap = ast.dump(ast.parse("sys.path.insert(0, str(ROOT))").body[0].value)

    def __init__(self, names):
        self.names = names

    def visit_Expr(self, node):
        # Imports are explicitly redirected; the archived tools' exact path
        # bootstrap is unnecessary and must not mutate process-global sys.path.
        if ast.dump(node.value) == self._path_bootstrap:
            return None
        return self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.level == 0 and node.module in self.names:
            node.module = self.names[node.module]
        return node

    def visit_Assign(self, node):
        # The archived preparation/audit tools locate data from ROOT. Their
        # source file now lives elsewhere, so bind a declared project data root.
        if any(isinstance(target, ast.Name) and target.id == "ROOT" for target in node.targets):
            node.value = ast.Call(func=ast.Name(id="Path", ctx=ast.Load()),
                                  args=[ast.Name(id="_LEGACY_PROJECT_ROOT", ctx=ast.Load())], keywords=[])
        return self.generic_visit(node)


def _modules(archive_dir=None, project_root=None):
    archive, sources = verify_archive(archive_dir)
    data_root = Path(project_root or ROOT).resolve(strict=True)
    key = (str(archive), str(data_root))
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
        token = hashlib.sha256((str(archive) + "\0" + str(data_root)).encode("utf-8")).hexdigest()[:16]
        namespace = "_terragenesis_legacy_fault_v1_" + token
        names = {name: namespace + "." + name for name in _MODULE_ORDER}
        installed = []
        try:
            for package in (namespace, namespace + ".terrain_pipeline", namespace + ".tools"):
                module = ModuleType(package)
                module.__path__ = []
                sys.modules[package] = module
                installed.append(package)
            modules = {}
            for name in _MODULE_ORDER:
                relative = name.replace(".", "/") + ".py"
                tree = ast.parse(sources[relative].decode("utf-8-sig"), filename=str(archive / relative))
                tree = ast.fix_missing_locations(_ReplayImports(names).visit(tree))
                module = ModuleType(names[name])
                module.__file__ = str(archive / relative)
                module.__package__ = names[name].rsplit(".", 1)[0]
                module._LEGACY_PROJECT_ROOT = str(data_root)
                sys.modules[names[name]] = module
                installed.append(names[name])
                exec(compile(tree, module.__file__, "exec"), module.__dict__)
                modules[name] = module
            prepare = modules["tools.prepare_metric_vdm_fault"]
            archived_file_sha = prepare.file_sha256

            def replay_source_sha(path):
                path = Path(path).resolve()
                if path.is_relative_to(data_root):
                    relative = path.relative_to(data_root).as_posix()
                    if relative in sources:
                        return hashlib.sha256(sources[relative]).hexdigest()
                return archived_file_sha(path)

            prepare.file_sha256 = replay_source_sha
            _CACHE[key] = modules
            return modules
        except Exception:
            for name in reversed(installed):
                sys.modules.pop(name, None)
            raise


def load_legacy_api(*, archive_dir=None, project_root=None):
    """Explicitly expose the complete original v1 algorithm for historical replay."""
    return _modules(archive_dir, project_root)["terrain_pipeline.metric_vdm_fault"]


def load_legacy_fault(path, *, expected_sha256, expected_identity):
    return load_legacy_api().load_fault(path, expected_sha256=expected_sha256,
                                       expected_identity=expected_identity)


def replay_legacy_preparation(configuration, expected_sha256, output, *, archive_dir=None, project_root=None):
    """Run original v1 preparation with archived dependencies and declared data root."""
    module = _modules(archive_dir, project_root)["tools.prepare_metric_vdm_fault"]
    result = module.prepare(configuration, expected_sha256, output)
    archive, sources = verify_archive(archive_dir)
    sidecar = {
        "schema": "metric-vdm-fault-explicit-legacy-replay-v1",
        "archive_directory": str(archive), "manifest_sha256": MANIFEST_SHA256,
        "project_data_root": str(module.ROOT),
        "execution_adapter": str(Path(__file__).resolve()),
        "execution_adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "original_source_sha256": {name: hashlib.sha256(data).hexdigest()
                                   for name, data in sources.items()},
        "adaptations": ["isolated local import namespace", "explicit project data ROOT",
                        "skip the archived tools' exact sys.path bootstrap",
                        "original code_sha256 labels map to the archived source bytes"],
        "algorithm_source_unchanged": True, "report_schema": result["schema"],
        "historical_algorithm_not_production_default": True,
    }
    path = Path(output).resolve() / "legacy-replay.json"
    module._publish_json(path, sidecar)
    return {**result, "legacy_replay": {"path": str(path),
                                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}


def audit_legacy_fault(path, *, expected_sha256=None, expected_identity=None):
    module = _modules()["tools.audit_metric_vdm_fault"]
    return module.audit_fault(path, expected_sha256=expected_sha256, expected_identity=expected_identity)
