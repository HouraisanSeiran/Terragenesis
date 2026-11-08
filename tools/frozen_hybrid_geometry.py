"""Explicit replay of the pre-consolidation hybrid geometry source closure."""

import builtins
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import types


DATA_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = DATA_ROOT / "legacy-code/hybrid-geometry-pre-consolidation"
MANIFEST_SHA256 = "82ff12cd2fc22f626b4e4871bfbee6dc19e795e78ab50a7a1a16cce942fcfbb2"
_COUNTER = itertools.count()


class GeometryLegacyReplay:
    """A trusted-code context with separate original data and frozen code roots.

    Historical source checks read only the explicitly selected archived code;
    data pins still refer to immutable artifacts beneath the original workspace.
    This context is not a sandbox and does not certify arbitrary old data.
    """
    def __init__(self, *, code_root=None, data_root=None):
        self.code_root = Path(CODE_ROOT if code_root is None else code_root).resolve(strict=True)
        self.data_root = Path(DATA_ROOT if data_root is None else data_root).resolve(strict=True)
        raw = (self.code_root / "manifest.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
            raise ValueError("hybrid legacy manifest sha256 mismatch")
        self.manifest = json.loads(raw)
        self.sources = {}
        for relative, record in self.manifest["files"].items():
            path = (self.code_root / relative).resolve(strict=True)
            if not path.is_relative_to(self.code_root) or not path.is_file():
                raise ValueError("hybrid legacy source path escapes archive")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ValueError("hybrid legacy source sha256 mismatch: " + relative)
            self.sources[record["module"]] = (path, data)
        self.modules = {}
        self.prefix = "_hybrid_geometry_legacy_" + str(next(_COUNTER))

    def source_path(self, path):
        path = Path(path).resolve()
        if path.is_relative_to(self.code_root):
            relative = path.relative_to(self.code_root).as_posix()
        elif path.is_relative_to(self.data_root) and path.suffix == ".py":
            relative = path.relative_to(self.data_root).as_posix()
        else:
            return path
        record = self.manifest["files"].get(relative)
        if record is None:
            raise ValueError("unregistered frozen hybrid source: " + relative)
        archived = self.code_root / relative
        if hashlib.sha256(archived.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("hybrid legacy source changed: " + relative)
        return archived

    def source_sha256(self, path):
        return hashlib.sha256(self.source_path(path).read_bytes()).hexdigest()

    def _bind_roots_and_source_checks(self, module):
        for key, value in list(vars(module).items()):
            if isinstance(value, Path) and key != "__file__" and value.is_relative_to(self.code_root):
                module.__dict__[key] = self.data_root / value.relative_to(self.code_root)
        for name in ("file_sha", "file_sha256"):
            if callable(getattr(module, name, None)):
                setattr(module, name, self.source_sha256)
        original_checked = getattr(module, "checked_path", None)
        if callable(original_checked):
            def checked_path(pin, *args, **kwargs):
                translated = dict(pin)
                translated["path"] = str(self.source_path(pin["path"]))
                return original_checked(translated, *args, **kwargs)
            module.checked_path = checked_path

    def load(self, original_name):
        if original_name in self.modules:
            return self.modules[original_name]
        if original_name not in self.sources and not any(
                name.startswith(original_name + ".") for name in self.sources):
            raise ImportError("module outside frozen hybrid closure: " + original_name)
        parent_name, _, leaf = original_name.rpartition(".")
        parent = self.load(parent_name) if parent_name else None
        qualified = self.prefix + "." + original_name
        module = types.ModuleType(qualified)
        self.modules[original_name] = module
        sys.modules[qualified] = module
        if parent is not None:
            setattr(parent, leaf, module)
        if original_name not in self.sources:
            if not any(name.startswith(original_name + ".") for name in self.sources):
                raise ImportError("module outside frozen hybrid closure: " + original_name)
            module.__path__ = []
            return module
        path, data = self.sources[original_name]
        module.__file__ = str(path)
        module.__package__ = qualified if path.name == "__init__.py" else qualified.rpartition(".")[0]
        if path.name == "__init__.py":
            module.__path__ = []
        module.__dict__["__legacy_original_name__"] = original_name
        local_builtins = dict(vars(builtins))
        local_builtins["__import__"] = self._import
        module.__dict__["__builtins__"] = local_builtins
        prior_path = list(sys.path)
        try:
            exec(compile(data, str(path), "exec"), module.__dict__)
            self._bind_roots_and_source_checks(module)
        except BaseException:
            self.modules.pop(original_name, None)
            sys.modules.pop(qualified, None)
            raise
        finally:
            sys.path[:] = prior_path
        return module

    def _import(self, name, globals=None, locals=None, fromlist=(), level=0):
        resolved = name
        if level:
            original = globals["__legacy_original_name__"]
            package = original if self.sources[original][0].name == "__init__.py" else original.rpartition(".")[0]
            resolved = importlib.util.resolve_name("." * level + name, package)
        if resolved.split(".", 1)[0] not in ("terrain_pipeline", "diffusion", "tools", "tests"):
            return builtins.__import__(name, globals, locals, fromlist, level)
        module = self.load(resolved)
        if fromlist:
            for attribute in fromlist:
                child = resolved + "." + attribute
                if attribute != "*" and not hasattr(module, attribute) and child in self.sources:
                    self.load(child)
            return module
        return self.load(resolved.split(".", 1)[0])


def load_legacy_module(name):
    """Load one explicitly named historical module; nothing runs on tool import."""
    context = GeometryLegacyReplay()
    module = context.load(name)
    module.legacy_replay_context = context
    return module
