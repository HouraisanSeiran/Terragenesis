"""Explicit, byte-verified historical hydraulics replay; never a default backend."""

import ast
import builtins
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import types

DATA_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = DATA_ROOT / "legacy-code/hybrid-hydraulics-before-20261023"
MANIFEST_SHA256 = "8bea4e029f8625c0f8ed8e163877cd1e1d9d60bd02735fcef9e43f17a1665209"
_COUNTER = itertools.count()
_LOCAL_PACKAGES = frozenset(("terrain_pipeline", "tools", "tests", "diffusion"))


class _ReplayBindings(ast.NodeTransformer):
    """Remove legacy path bootstrap and bind only physical-AST reads to source root."""

    def visit_Expr(self, node):
        call = node.value
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "insert" and isinstance(call.func.value, ast.Attribute)
                and isinstance(call.func.value.value, ast.Name)
                and call.func.value.value.id == "sys" and call.func.value.attr == "path"):
            return None
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if node.name == "check_same_physics":
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id == "ROOT" and isinstance(child.ctx, ast.Load):
                    child.id = "SOURCE_ROOT"
        return self.generic_visit(node)


class HydraulicsLegacyReplay:
    """Trusted archived code, not a sandbox; data inputs keep their original pins.

    No archived code executes until every allowlisted file and the externally
    pinned manifest has been checked. Repository imports cannot fall back live.
    """

    def __init__(self, *, source_root=None, data_root=None):
        self.source_root = Path(SOURCE_ROOT if source_root is None else source_root).resolve(strict=True)
        self.data_root = Path(DATA_ROOT if data_root is None else data_root).resolve(strict=True)
        raw = (self.source_root / "manifest.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
            raise ValueError("hydraulics legacy manifest sha256 mismatch")
        self.manifest = json.loads(raw)
        self.sources = {}
        for relative, record in self.manifest["files"].items():
            path = self._verified_path(relative, record)
            self.sources[record["module"]] = (path, path.read_bytes())
        self.modules = {}
        self.prefix = "_hybrid_hydraulics_legacy_" + str(next(_COUNTER))

    def _verified_path(self, relative, record):
        path = (self.source_root / relative).resolve(strict=True)
        if not path.is_relative_to(self.source_root) or not path.is_file():
            raise ValueError("hydraulics legacy path escapes source root")
        data = path.read_bytes()
        if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("hydraulics legacy source sha256 mismatch: " + relative)
        return path

    def source_path(self, path):
        path = Path(path).resolve()
        if path.is_relative_to(self.source_root):
            relative = path.relative_to(self.source_root).as_posix()
        elif path.is_relative_to(self.data_root) and path.suffix == ".py":
            relative = path.relative_to(self.data_root).as_posix()
        else:
            raise ValueError("not a registered hydraulics source path")
        record = self.manifest["files"].get(relative)
        if record is None:
            raise ValueError("unregistered hydraulics legacy source: " + relative)
        return self._verified_path(relative, record)

    def file_sha(self, path):
        path = Path(path)
        if path.suffix == ".py":
            path = self.source_path(path)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _bind(self, module):
        module.DATA_ROOT = self.data_root
        module.SOURCE_ROOT = self.source_root
        if hasattr(module, "ROOT"):
            module.ROOT = self.data_root
        for name in ("file_sha", "file_sha256"):
            if callable(getattr(module, name, None)):
                setattr(module, name, self.file_sha)
        original = getattr(module, "checked_path", None)
        if callable(original):
            def checked_path(pin):
                if Path(pin["path"]).suffix != ".py":
                    return original(pin)
                path = self.source_path(pin["path"])
                if (self.file_sha(path) != pin["sha256"]
                        or ("bytes" in pin and pin["bytes"] != path.stat().st_size)):
                    raise ValueError("historical source pin mismatch")
                return path
            module.checked_path = checked_path

    def load(self, name):
        if name in self.modules:
            return self.modules[name]
        if name not in self.sources and not any(key.startswith(name + ".") for key in self.sources):
            raise ImportError("outside frozen hydraulics closure: " + name)
        parent_name, _, leaf = name.rpartition(".")
        parent = self.load(parent_name) if parent_name else None
        qualified = self.prefix + "." + name
        module = types.ModuleType(qualified)
        self.modules[name] = module
        sys.modules[qualified] = module
        if parent is not None:
            setattr(parent, leaf, module)
        if name not in self.sources:
            module.__path__ = []
            return module
        path, data = self.sources[name]
        self.source_path(path)
        module.__file__ = str(path)
        module.__package__ = qualified.rpartition(".")[0]
        module.__dict__["__legacy_original_name__"] = name
        local_builtins = dict(vars(builtins))
        local_builtins["__import__"] = self._import
        module.__dict__["__builtins__"] = local_builtins
        try:
            tree = _ReplayBindings().visit(ast.parse(data, filename=str(path)))
            exec(compile(ast.fix_missing_locations(tree), str(path), "exec"), module.__dict__)
            self._bind(module)
        except BaseException:
            self.modules.pop(name, None)
            sys.modules.pop(qualified, None)
            raise
        return module

    def _import(self, name, globals=None, locals=None, fromlist=(), level=0):
        resolved = name
        if level:
            original = globals["__legacy_original_name__"]
            resolved = importlib.util.resolve_name("." * level + name, original.rpartition(".")[0])
        if resolved.split(".", 1)[0] not in _LOCAL_PACKAGES:
            return builtins.__import__(name, globals, locals, fromlist, level)
        module = self.load(resolved)
        if fromlist:
            for attribute in fromlist:
                child = resolved + "." + attribute
                if attribute != "*" and not hasattr(module, attribute) and child in self.sources:
                    self.load(child)
            return module
        return self.load(resolved.split(".", 1)[0])

    def close(self):
        for name in self.modules:
            sys.modules.pop(self.prefix + "." + name, None)
        self.modules.clear()


def load_legacy_module(name):
    context = HydraulicsLegacyReplay()
    module = context.load(name)
    module.legacy_replay_context = context
    return module
