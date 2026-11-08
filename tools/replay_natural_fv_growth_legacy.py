"""Explicit trusted FV legacy replay; current generation never imports this module.

Numerical historical CLI runs in a separate worker process. The opt-in module
API is also available to old numerical comparison tests in private namespaces.
"""
import argparse
import ast
import atexit
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "legacy-code/fv-growth-before-20261022"
MANIFEST_SHA256 = "f76ddcec2d4523ae9ef31f5da7ae03c1eb5e4aaa267797b590310940c739da70"
_COUNTER = itertools.count()
_LOCK = threading.RLock()
_TEST_CONTEXTS = {}
_ROOTS = {"tools", "terrain_pipeline", "diffusion", "tests"}
_SUPPLEMENTAL = {
    "tools/diagnose_fv_mpm_rejection.py": ("supplemental/tools/diagnose_fv_mpm_rejection.py", 11877,
        "c87c6880f0f8a5bd4600603218edd56e8c548678cce838e3a740923a713802d4"),
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_archive(archive_dir=None):
    archive = Path(archive_dir or ARCHIVE).resolve(strict=True)
    raw = (archive / "manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("FV legacy trusted manifest SHA256 mismatch")
    manifest = json.loads(raw)
    if manifest["schema"] != "fv-growth-legacy-snapshot-v1":
        raise ValueError("FV legacy manifest schema mismatch")
    sources = {}
    for record in manifest["source_files"]:
        relative = record["original_path"]
        path = (archive / record["archive_path"]).resolve(strict=True)
        if record["archive_path"] != "sources/" + relative or not path.is_relative_to(archive):
            raise ValueError("FV legacy source mapping escapes archive")
        data = path.read_bytes()
        if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("FV legacy source SHA256 mismatch: " + relative)
        if relative in sources:
            raise ValueError("duplicate FV legacy source")
        sources[relative] = data
    for record in manifest["templates"]:
        path = (archive / record["archive_path"]).resolve(strict=True)
        if not path.is_relative_to(archive) or path.stat().st_size != record["bytes"] or sha256(path) != record["sha256"]:
            raise ValueError("FV legacy parameter template SHA256 mismatch")
    supplemental_raw = (archive / 'supplemental-manifest.json').read_bytes()
    if hashlib.sha256(supplemental_raw).hexdigest() != '01d9f6d904cd71d65674d1a6d476ce437527aa9089efa0855ee3108b3f64c3dd':
        raise ValueError('FV supplemental trusted manifest SHA256 mismatch')
    supplemental = json.loads(supplemental_raw)
    if (supplemental['schema'] != 'FV-legacy-diagnostic-supplement-v1'
            or supplemental['base_manifest_sha256'] != MANIFEST_SHA256):
        raise ValueError('FV supplemental manifest base mismatch')
    for name, (relative, size, digest) in _SUPPLEMENTAL.items():
        path = (archive / relative).resolve(strict=True)
        data = path.read_bytes()
        if not path.is_relative_to(archive) or len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("FV supplemental historical source SHA256 mismatch: " + name)
        sources[name] = data
    return archive, manifest, sources


class _Redirect(ast.NodeTransformer):
    bootstrap = ast.dump(ast.parse("sys.path.insert(0, str(ROOT))").body[0].value)

    def __init__(self, namespace):
        self.namespace = namespace

    def visit_ImportFrom(self, node):
        if not node.level and node.module and node.module.split(".")[0] in _ROOTS:
            node.module = self.namespace + "." + node.module
        return node

    def visit_Expr(self, node):
        if ast.dump(node.value) == self.bootstrap:
            return None
        return self.generic_visit(node)

    def visit_Assign(self, node):
        if any(isinstance(target, ast.Name) and target.id == "ROOT" for target in node.targets):
            node.value = ast.Call(ast.Name("Path", ast.Load()), [ast.Name("_FV_DATA_ROOT", ast.Load())], [])
        return self.generic_visit(node)

    def visit_Call(self, node):
        node = self.generic_visit(node)
        if (isinstance(node.func, ast.Name) and node.func.id == "file_sha256" and len(node.args) == 1
                and isinstance(node.args[0], ast.BinOp) and isinstance(node.args[0].op, ast.Div)
                and isinstance(node.args[0].left, ast.Name) and node.args[0].left.id == "ROOT"):
            return ast.copy_location(ast.Call(ast.Name("_FV_SOURCE_SHA", ast.Load()), [node.args[0].right], []), node)
        return node


class _Loader(importlib.abc.Loader):
    def __init__(self, context, relative):
        self.context, self.relative = context, relative

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        if self.relative is None:
            return
        path = self.context.archive / ("supplemental" if self.relative in _SUPPLEMENTAL else "sources") / self.relative
        module.__file__ = str(path)
        module._FV_DATA_ROOT = str(self.context.data_root)
        module._FV_SOURCE_SHA = self.context.source_sha
        tree = ast.parse(self.context.sources[self.relative].decode("utf-8-sig"), filename=str(path))
        tree = ast.fix_missing_locations(_Redirect(self.context.namespace).visit(tree))
        exec(compile(tree, str(path), "exec"), module.__dict__)
        if self.relative == 'terrain_pipeline/drainage.py':
            def retired_raster_route(*args, **kwargs):
                raise RuntimeError(
                    "Historical D8 generation is retired. Read saved historical results or "
                    "prepare a new irregular river network through tools/prepare_world_terrain_water.py.")
            module.route = retired_raster_route


class _Finder(importlib.abc.MetaPathFinder):
    def __init__(self, context):
        self.context = context

    def find_spec(self, fullname, path=None, target=None):
        prefix = self.context.namespace
        if fullname == prefix:
            relative, package = None, True
        elif fullname.startswith(prefix + "."):
            base = fullname[len(prefix) + 1:].replace(".", "/")
            if base + ".py" in self.context.sources:
                relative, package = base + ".py", False
            elif base + "/__init__.py" in self.context.sources:
                relative, package = base + "/__init__.py", True
            elif any(name.startswith(base + "/") for name in self.context.sources):
                relative, package = None, True
            else:
                raise ImportError("FV archive has no source for " + fullname)
        else:
            return None
        return importlib.machinery.ModuleSpec(fullname, _Loader(self.context, relative), is_package=package)


class LegacyContext:
    def __init__(self, *, archive_dir=None, data_root=None):
        self.archive, self.manifest, self.sources = verify_archive(archive_dir)
        self.data_root = Path(data_root or ROOT).resolve(strict=True)
        token = hashlib.sha256((str(self.archive) + str(self.data_root)).encode("utf-8")).hexdigest()[:12]
        self.namespace = "_terragenesis_fv_legacy_" + token + "_" + str(next(_COUNTER))
        self.cache = tempfile.TemporaryDirectory(prefix="fv-legacy-numba-")
        self.finder = _Finder(self)
        self.closed = False
        sys.meta_path.insert(0, self.finder)

    def source_sha(self, original_path):
        key = str(original_path).replace("\\", "/")
        if key not in self.sources:
            raise ValueError("FV legacy undeclared source identity: " + key)
        return hashlib.sha256(self.sources[key]).hexdigest()

    def module(self, name):
        if self.closed:
            raise RuntimeError("closed FV legacy context")
        verify_archive(self.archive)
        with _LOCK:
            environment, search_path = dict(os.environ), list(sys.path)
            numba_config, old_cache = None, None
            try:
                os.environ["NUMBA_CACHE_DIR"] = self.cache.name
                import numba
                numba_config, old_cache = numba.config, numba.config.CACHE_DIR
                numba.config.CACHE_DIR = self.cache.name
                return importlib.import_module(self.namespace + "." + name)
            except Exception:
                self.close()
                raise
            finally:
                if numba_config is not None:
                    numba_config.CACHE_DIR = old_cache
                os.environ.clear()
                os.environ.update(environment)
                sys.path[:] = search_path

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.finder in sys.meta_path:
            sys.meta_path.remove(self.finder)
        for name in list(sys.modules):
            if name == self.namespace or name.startswith(self.namespace + "."):
                del sys.modules[name]
        self.cache.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def legacy_test_module(name):
    """Opt-in test-only access; numerical production replay uses a child process."""
    verify_archive()
    with _LOCK:
        if "default" not in _TEST_CONTEXTS:
            _TEST_CONTEXTS["default"] = LegacyContext()
        return _TEST_CONTEXTS["default"].module(name)


def _close_test_contexts():
    for context in _TEST_CONTEXTS.values():
        context.close()


atexit.register(_close_test_contexts)


def read_legacy_checkpoint(path, expected_sha256, *, data_root=None, archive_dir=None):
    """Strictly verify using original loaders, then return the untouched saved state."""
    if sha256(path) != expected_sha256:
        raise ValueError("FV legacy checkpoint external SHA256 mismatch")
    with LegacyContext(archive_dir=archive_dir, data_root=data_root) as context:
        original = context.module("tools.inspect_natural_fv_growth").read_arrays(path)
        metadata = json.loads(str(original.pop("metadata_json")))
        schema = metadata["schema"]
        if schema in ("finite-FV-growth-checkpoint-v1", "finite-FV-growth-checkpoint-v2"):
            context.module("tools.run_natural_fv_growth_v2").load_checkpoint(path)
        elif schema == "finite-FV-growth-checkpoint-v3":
            context.module("tools.run_natural_fv_growth_v3").load_checkpoint(path)
        elif schema == "finite-FV-growth-checkpoint-v4":
            context.module("tools.run_natural_fv_growth_v4").load_checkpoint(path)
        else:
            raise ValueError("unsupported explicit FV legacy schema")
        if sha256(path) != expected_sha256:
            raise ValueError("FV parent checkpoint changed during cold read")
        return original, metadata


def _parameters(context, profile, template, template_sha256):
    if sha256(template) != template_sha256:
        raise ValueError("FV legacy parameter template external SHA256 mismatch")
    record = json.loads(Path(template).read_text(encoding="utf-8"))
    params = record.get("parameters", record)
    required = {"interval_s", "source_time_scale", "max_input_concentration", "supply_off", "river_q",
                "sea_mean", "tide_amplitude", "tide_period", "tide_phase", "wave_height", "wave_period",
                "settling_velocity", "max_bed_change", "packet_stride", "max_wall_s", "max_bytes_mib",
                "intervals", "chunk_intervals"}
    if profile != "v1":
        required |= {"duration_s", "chunk_duration_s", "min_interval_s", "recover_completed_prefix"}
    if profile in ("v3", "v4"):
        required |= {"disable_exchange", "erosion_velocity", "exchange_max_concentration", "disable_slope",
                     "critical_slope", "slope_mobility"}
    if not required <= set(params):
        raise ValueError("incomplete FV legacy parameter template: " + str(sorted(required - set(params))))
    return dict(params)


def _worker(args):
    import numpy as np
    if sha256(args.resume) != args.resume_sha256:
        raise ValueError("FV legacy checkpoint external SHA256 mismatch")
    with LegacyContext(archive_dir=args.archive, data_root=args.data_root) as context:
        profile = args.legacy_runner
        module_name = "tools.run_natural_fv_growth" + ("" if profile == "v1" else "_" + profile)
        runner = context.module(module_name)
        data = context.module("tools.inspect_natural_fv_growth").read_arrays(args.resume)
        meta = json.loads(str(data.pop("metadata_json")))
        if meta["schema"] != "finite-FV-growth-checkpoint-" + profile:
            raise ValueError("legacy runner/profile does not match checkpoint schema")
        if profile == "v1":
            expected = {name: context.source_sha(name) for name in runner.IMPLEMENTATIONS}
            if meta["implementation_hashes"] != expected:
                raise ValueError("legacy v1 checkpoint implementation mismatch")
        else:
            runner.load_checkpoint(args.resume)
        params = _parameters(context, profile, args.parameters, args.parameters_sha256)
        parameter_record = json.loads(Path(args.parameters).read_text(encoding='utf-8'))
        if ('checkpoint_sha256' in parameter_record
                and parameter_record['checkpoint_sha256'] != args.resume_sha256):
            raise ValueError('historical FV summary does not bind the selected checkpoint')
        if profile in ("v3", "v4") and "exchange_config" in meta:
            exchange = context.module("terrain_pipeline.surface_rivers.metric_fv_exchange_v3").ExchangeConfig(
                enabled=not params["disable_exchange"], erosion_velocity_m_s=params["erosion_velocity"],
                maximum_concentration=params["exchange_max_concentration"], slope_enabled=not params["disable_slope"],
                critical_slope_m_m=params["critical_slope"], slope_mobility_m2_s=params["slope_mobility"])
            from dataclasses import asdict
            if meta["exchange_config"] != asdict(exchange):
                raise ValueError("legacy exchange parameters disagree with parent checkpoint")
        for key in ("parent", "water_run", "append_source", "recover_completed_prefix"):
            value = params.get(key)
            params[key] = None if value is None else Path(value)
        if params.get("append_source") is not None:
            raise ValueError("historical resume must not automatically re-append a template source")
        params.update(resume=Path(args.resume), output=Path(args.output))
        if args.duration_s is not None:
            if profile == "v1":
                count = args.duration_s / params["interval_s"]
                if count != int(count):
                    raise ValueError("legacy v1 duration must be divisible by its interval")
                params["intervals"] = int(count)
            else:
                params["duration_s"] = args.duration_s
        params["recover_completed_prefix"] = None
        runner_args = argparse.Namespace(**params)
        resources = context.module("tools.verify_fluvial_channel_remobilization")
        resources.resource_limits()
        report = runner.run(runner_args)
        verify_archive(context.archive)
        if sha256(args.resume) != args.resume_sha256 or sha256(args.parameters) != args.parameters_sha256:
            raise ValueError("legacy source checkpoint or template changed during execution")
        provenance = {"schema": "FV-explicit-legacy-replay-v1", "legacy_runner": profile,
            "archive": str(context.archive), "manifest_sha256": MANIFEST_SHA256,
            "data_root": str(context.data_root), "source_root": str(context.archive / "sources"),
            "parent_checkpoint": str(args.resume), "parent_sha256": args.resume_sha256,
            "parameter_template": str(args.parameters), "parameter_template_sha256": args.parameters_sha256,
            "adapter_sha256": sha256(__file__), "source_files_verified": len(context.sources),
            "adaptations": ["private import namespace", "declared data root", "source hash resolver",
                            "skip exact sys.path bootstrap", "temporary Numba cache"],
            "not_current_default": True}
        (Path(args.output) / "legacy-replay.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        print(json.dumps({"checkpoint": report["checkpoint"], "schema": report["schema"]}))


def replay_legacy(*, resume, resume_sha256, parameters, parameters_sha256, output, legacy_runner,
                  duration_s=None, data_root=None, archive_dir=None, timeout_s=120):
    """Launch full old generation/resume with explicit parent and parameter pins."""
    verify_archive(archive_dir)
    command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", "--resume", str(Path(resume).resolve()),
        "--resume-sha256", resume_sha256, "--parameters", str(Path(parameters).resolve()),
        "--parameters-sha256", parameters_sha256, "--output", str(Path(output).resolve()),
        "--legacy-runner", legacy_runner, "--data-root", str(Path(data_root or ROOT).resolve()),
        "--archive", str(Path(archive_dir or ARCHIVE).resolve())]
    if duration_s is not None:
        command += ["--duration-s", str(duration_s)]
    environment = dict(os.environ)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
        environment[name] = "1"
    with tempfile.TemporaryDirectory(prefix="fv-replay-worker-cache-") as cache:
        environment["NUMBA_CACHE_DIR"] = cache
        completed = subprocess.run(command, cwd=Path(data_root or ROOT), env=environment, capture_output=True,
                                   text=True, timeout=timeout_s)
    if completed.returncode:
        raise RuntimeError("explicit FV legacy worker failed:\n" + completed.stdout[-4000:] + completed.stderr[-8000:])
    return json.loads((Path(output) / "summary.json").read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--resume", type=Path, required=True)
    parser.add_argument("--resume-sha256", required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--parameters-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--legacy-runner", choices=("v1", "v2", "v3", "v4"), required=True)
    parser.add_argument("--duration-s", type=float)
    parser.add_argument("--data-root", type=Path, default=ROOT)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    args = parser.parse_args()
    if args.worker:
        _worker(args)
    else:
        print(json.dumps(replay_legacy(resume=args.resume, resume_sha256=args.resume_sha256,
            parameters=args.parameters, parameters_sha256=args.parameters_sha256, output=args.output,
            legacy_runner=args.legacy_runner, duration_s=args.duration_s, data_root=args.data_root, archive_dir=args.archive), indent=2))


def replay_legacy_diagnostic(*, checkpoint, checkpoint_sha256, parameters, parameters_sha256,
                             output, interval_s=.0625, duration_s=.125, captured_input=None,
                             captured_input_sha256=None, timeout_s=90):
    """Run the pinned historical v3 diagnostic in a separate process."""
    verify_archive()
    for path, digest in ((checkpoint, checkpoint_sha256), (parameters, parameters_sha256)):
        if sha256(path) != digest:
            raise ValueError('FV diagnostic external pin mismatch')
    if captured_input is not None and (not captured_input_sha256 or sha256(captured_input) != captured_input_sha256):
        raise ValueError('FV diagnostic captured input external pin mismatch')
    if duration_s <= 0. or duration_s > 4. or interval_s <= 0.:
        raise ValueError('historical diagnostic requires finite positive <=4s window')
    payload = dict(checkpoint=str(Path(checkpoint).resolve()), checkpoint_sha256=checkpoint_sha256,
        parameters=str(Path(parameters).resolve()), parameters_sha256=parameters_sha256,
        output=str(Path(output).resolve()), interval_s=interval_s, duration_s=duration_s,
        captured_input=None if captured_input is None else str(Path(captured_input).resolve()),
        captured_input_sha256=captured_input_sha256)
    code = ("import json,sys; from tools.replay_natural_fv_growth_legacy import _diagnostic_worker_payload; "
            "_diagnostic_worker_payload(json.loads(sys.argv[1]))")
    environment = dict(os.environ)
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS'):
        environment[name] = '1'
    completed = subprocess.run([sys.executable, '-B', '-c', code, json.dumps(payload)], cwd=ROOT,
        env=environment, capture_output=True, text=True, timeout=timeout_s)
    if completed.returncode:
        raise RuntimeError('explicit archived FV diagnostic failed:\n' + completed.stderr[-8000:])
    provenance = dict(payload, schema='FV-explicit-legacy-diagnostic-v1',
        manifest_sha256=MANIFEST_SHA256, supplemental_source_sha256=_SUPPLEMENTAL['tools/diagnose_fv_mpm_rejection.py'][2],
        adapter_sha256=sha256(__file__), not_current_diagnostic=True)
    (Path(output)/'legacy-diagnostic.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    return provenance


def recover_legacy_prefix(source, through_checkpoint, parameters_from, output, *, checkpoint_sha256, parameters_sha256):
    """Explicit cold reconstruction of only complete original v3 evidence."""
    if sha256(through_checkpoint) != checkpoint_sha256 or sha256(parameters_from) != parameters_sha256:
        raise ValueError('FV prefix recovery external pin mismatch')
    with LegacyContext() as context:
        recovered = context.module('tools.recover_natural_fv_growth_v3_prefix').recover(
            Path(source), Path(through_checkpoint), Path(parameters_from), Path(output))
    if sha256(through_checkpoint) != checkpoint_sha256 or sha256(parameters_from) != parameters_sha256:
        raise ValueError('FV prefix recovery parent/template changed')
    sidecar = dict(schema='FV-explicit-legacy-prefix-v1', manifest_sha256=MANIFEST_SHA256,
        checkpoint_sha256=checkpoint_sha256, parameters_sha256=parameters_sha256, adapter_sha256=sha256(__file__))
    (Path(output)/'legacy-recovery.json').write_text(json.dumps(sidecar,indent=2),encoding='utf-8')
    return recovered


def _diagnostic_worker_payload(payload):
    pins = [(payload['checkpoint'], payload['checkpoint_sha256']),
            (payload['parameters'], payload['parameters_sha256'])]
    if payload['captured_input'] is not None:
        pins.append((payload['captured_input'], payload['captured_input_sha256']))
    if any(sha256(path) != digest for path,digest in pins):
        raise ValueError('FV diagnostic worker external pin mismatch')
    arguments = ['diagnose','--checkpoint',payload['checkpoint'],'--parameters-from',payload['parameters'],
        '--output',payload['output'],'--interval-s',str(payload['interval_s']),
        '--duration-s',str(payload['duration_s'])]
    if payload['captured_input'] is not None:
        arguments += ['--captured-input',payload['captured_input']]
    original = list(sys.argv)
    try:
        sys.argv = arguments
        with LegacyContext() as context:
            context.module('tools.verify_fluvial_channel_remobilization').resource_limits()
            context.module('tools.diagnose_fv_mpm_rejection').main()
    finally:
        sys.argv[:] = original
    if any(sha256(path) != digest for path,digest in pins):
        raise ValueError('FV diagnostic source changed during execution')


if __name__ == '__main__':
    main()
