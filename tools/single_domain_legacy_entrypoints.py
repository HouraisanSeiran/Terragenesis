"""Explicit, pinned replay of retired shallow-water v4/v8 entrypoints.

Importing this module does not import the archived algorithms. Local source is
loaded from a frozen dependency closure under separate module names; the active
terrain_pipeline and diffusion packages are never replaced or added to sys.path.
"""

import builtins
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import types


ARCHIVE_ROOT = Path(__file__).resolve().parents[1] / "legacy-code/single-domain-entrypoints"
MANIFEST_SHA256 = "dfeb5383b63daf1e87e6c57fe1fb9b40a95b47964dc1eb472f78c0f478d1e0de"
_COUNTER = itertools.count()


def _verified_sources(archive_root):
    root = Path(archive_root).resolve(strict=True)
    raw = (root / "manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("legacy entrypoints manifest sha256 mismatch")
    manifest = json.loads(raw)
    if manifest["schema"] != "single-domain-legacy-entrypoints-v1":
        raise ValueError("legacy entrypoints manifest schema mismatch")
    sources = {}
    for name, record in manifest["files"].items():
        relative = Path(record["archive_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("legacy source path escapes archive")
        path = (root / relative).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("legacy source path escapes archive")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("legacy source sha256 mismatch: " + name)
        sources[name] = (path, data)
    return manifest, sources


class _IsolatedReplay:
    def __init__(self, sources):
        self.sources = sources
        self.modules = {}
        self.prefix = "_single_domain_legacy_replay_" + str(next(_COUNTER))
        self.registered = []

    def load(self, original_name):
        if original_name in self.modules:
            return self.modules[original_name]
        if original_name not in self.sources:
            raise ImportError("local module is outside frozen legacy closure: " + original_name)
        path, source = self.sources[original_name]
        parent_name, _, leaf = original_name.rpartition(".")
        parent = self.load(parent_name) if parent_name else None
        qualified = self.prefix + "." + original_name
        module = types.ModuleType(qualified)
        module.__file__ = str(path)
        module.__package__ = qualified if path.name == "__init__.py" else qualified.rpartition(".")[0]
        if path.name == "__init__.py":
            module.__path__ = []
        module.__dict__["__legacy_original_name__"] = original_name
        local_builtins = dict(vars(builtins))
        local_builtins["__import__"] = self.import_source
        module.__dict__["__builtins__"] = local_builtins
        self.modules[original_name] = module
        sys.modules[qualified] = module
        self.registered.append(qualified)
        if parent is not None:
            setattr(parent, leaf, module)
        exec(compile(source, str(path), "exec"), module.__dict__)
        return module

    def import_source(self, name, globals=None, locals=None, fromlist=(), level=0):
        resolved = name
        if level:
            original = globals["__legacy_original_name__"]
            path = self.sources[original][0]
            package = original if path.name == "__init__.py" else original.rpartition(".")[0]
            resolved = importlib.util.resolve_name("." * level + name, package)
        if resolved.split(".", 1)[0] not in ("terrain_pipeline", "diffusion"):
            return builtins.__import__(name, globals, locals, fromlist, level)
        module = self.load(resolved)
        if fromlist:
            for attribute in fromlist:
                candidate = resolved + "." + attribute
                if attribute != "*" and not hasattr(module, attribute) and candidate in self.sources:
                    self.load(candidate)
            return module
        return self.load(resolved.split(".", 1)[0])

    def discard_failed(self):
        for name in self.registered:
            sys.modules.pop(name, None)


def load_legacy_entrypoint(version):
    """Return an explicitly selected archived module after verifying all sources.

    Only 'v4' and 'v8' are accepted. The archive is trusted local code, not an
    arbitrary plugin or sandbox. NumPy/SciPy remain environment dependencies.
    Validation is repeated on every call, including after a previous load.
    The returned module's replay_dependencies contains archived geometry/surface
    modules (and reconstruction for v8), including the matching SurfaceBudget.
    """
    if version not in ("v4", "v8"):
        raise ValueError("explicit legacy entrypoint version must be v4 or v8")
    manifest, sources = _verified_sources(ARCHIVE_ROOT)
    replay = _IsolatedReplay(sources)
    try:
        module = replay.load(manifest["entrypoints"][version])
        module.replay_dependencies = {
            "surface": replay.load('terrain_pipeline.surface_hydraulics'),
            "geometry": replay.load('terrain_pipeline.fine_subgrid'),
        }
        if version == "v8":
            module.replay_dependencies["reconstruction"] = replay.load(
                'terrain_pipeline.shallow_water')
        return module
    except BaseException:
        replay.discard_failed()
        raise
