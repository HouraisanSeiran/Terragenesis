#!/usr/bin/env python3
"""Independent CLI acceptance verifier for published native 30m products."""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
PUBLISH = ROOT / "tools" / "publish_native_30m_bundle.py"
SCHEMA = "native-30m-product-verification-v1"


def fail(msg: str) -> "NoReturn":
    print(f"verify_native_30m_product: {msg}", file=sys.stderr)
    raise SystemExit(1)


def run(argv, timeout):
    t0 = time.monotonic()
    try:
        p = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        fail(f"command timed out after {timeout}s: {argv!r}")
    except OSError as e:
        fail(f"command failed to start {argv!r}: {e}")
    elapsed = time.monotonic() - t0
    rec = {"argv": [str(x) for x in argv], "elapsed_seconds": elapsed, "returncode": p.returncode}
    if p.returncode != 0:
        fail(f"command exited {p.returncode}: {argv!r}\nstderr:\n{p.stderr}")
    try:
        obj = json.loads(p.stdout)
    except Exception as e:
        fail(f"stdout not a JSON object for {argv!r}: {e}\nstdout:\n{p.stdout[:2000]}")
    if not isinstance(obj, dict):
        fail(f"stdout JSON is not an object for {argv!r}")
    return obj, rec


def publish_argv(mode, bundle, identity, extra=None):
    argv = [PY, "-B", "-X", "utf8", str(PUBLISH), "--mode", mode,
            "--bundle", str(bundle), "--require-source-pins"]
    if identity:
        argv += ["--identity", identity]
    if extra:
        argv += extra
    return argv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--identity")
    ap.add_argument("--timeout-seconds", type=float, default=180.0)
    ap.add_argument("--point-native", nargs=2, type=float, metavar=("X", "Z"))
    a = ap.parse_args()
    if not (math.isfinite(a.timeout_seconds) and a.timeout_seconds > 0):
        fail("--timeout-seconds must be positive finite")
    if a.point_native is not None and any(not math.isfinite(v) or int(v) != v for v in a.point_native):
        fail('--point-native requires two finite integers')
    bundle = Path(a.bundle)
    if not bundle.is_absolute():
        bundle = Path.cwd() / bundle
    bundle = bundle.resolve(strict=False)
    if not bundle.exists():
        fail(f"bundle does not exist: {bundle}")
    out = Path(a.output)
    if not out.is_absolute():
        out = Path.cwd() / out
    if os.path.lexists(out):
        fail("--out path already exists")
    out = out.resolve(strict=False)
    bundle = bundle.resolve(strict=False)
    if out == bundle or bundle in out.parents:
        fail("--out must not be inside the verified bundle")
    if out.exists():
        fail(f"output target already exists (refusing to overwrite): {out}")
    if not out.parent.is_dir():
        fail(f"output parent directory does not exist: {out.parent}")
    checks = {"inspect": False, "audit": False, "point_native": None}
    commands = []
    results = {}
    ins, rec = run(publish_argv("inspect", bundle, a.identity), a.timeout_seconds)
    commands.append(rec)
    results["inspect"] = ins
    if ins.get("cold_read_verified_now") is not True:
        fail("inspect cold_read_verified_now is not true")
    if ins.get("source_code_drift") != []:
        fail("inspect source_code_drift is not empty")
    ins_sha = ins.get("numerical_identity_sha256")
    if not ins_sha:
        fail("inspect missing numerical_identity_sha256")
    checks["inspect"] = True
    aud, rec = run(publish_argv("audit", bundle, a.identity), a.timeout_seconds)
    commands.append(rec)
    results["audit"] = aud
    if aud.get("independent_audit_rerun_now") is not True:
        fail("audit independent_audit_rerun_now is not true")
    audit = aud.get("audit")
    if not isinstance(audit, dict) or audit.get("passed") is not True:
        fail("audit.passed is not true")
    ssr = audit.get("spatial_section_reference")
    if not isinstance(ssr, dict) or ssr.get("passed") is not True:
        fail("audit.spatial_section_reference.passed is not true")
    aud_sha = aud.get("numerical_identity_sha256")
    if aud_sha != ins_sha:
        fail("inspect/audit numerical_identity_sha256 mismatch")
    release_sha = ins.get('identity_sha256')
    if not isinstance(release_sha, str) or len(release_sha) != 64:
        fail('release_sha_invalid')
    for _c in release_sha:
        if _c not in '0123456789abcdef':
            fail('release_sha_invalid')
    if aud.get('identity_sha256') != release_sha:
        fail('audit_identity_sha256_mismatch')
    if aud.get('source_code_drift') != []:
        fail('source_code_drift_present')
    if aud.get('cold_read_verified_now') is not True:
        fail('cold_read_not_verified')
    if getattr(a, 'identity', None) is not None and a.identity != ins_sha:
        fail('artifact_numerical_identity_mismatch')
    checks["audit"] = True
    if a.point_native is not None:
        px, pz = a.point_native
        extra = ["--point", repr(px), repr(pz), "--native", "--scope", "channel_section"]
        pt, rec = run(publish_argv("inspect", bundle, a.identity, extra), a.timeout_seconds)
        commands.append(rec)
        results["point_native"] = pt
        point = pt.get("point")
        if not isinstance(point, dict) or point.get("resolved") is not True:
            fail("point native resolution failed: point.resolved is not true")
        if point.get("scope") != "channel_section":
            fail("point native scope is not channel_section")
        got = point.get("sampled_native_xz")
        if not (isinstance(got, list) and len(got) == 2 and
                float(got[0]) == float(px) and float(got[1]) == float(pz)):
            fail(f"point native sampled_native_xz != request: {got!r} vs {[px, pz]!r}")
        if pt.get('numerical_identity_sha256') != ins_sha or pt.get('identity_sha256') != release_sha or pt.get('source_code_drift') != []:
            fail('point identity or source drift mismatch')
        checks["point_native"] = True
    passed = (
        checks.get("inspect") is True
        and checks.get("audit") is True
        and (not a.point_native or checks.get("point_native") is True)
    )
    if not passed:
        fail("not all checks passed")
    report = {"schema": SCHEMA, "passed": True, "bundle": str(bundle),
              "numerical_identity_sha256": ins_sha, "release_identity_sha256": release_sha,
              "checks": checks, "commands": commands, "results": results}
    tmp = None
    try:
        fd = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False,
            dir=str(out.parent), prefix=out.name + ".", suffix=".tmp", newline="\n")
        tmp = Path(fd.name)
        with fd:
            json.dump(report, fd, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            fd.write("\n")
            fd.flush()
            os.fsync(fd.fileno())
        os.link(str(tmp), str(out))
    except FileExistsError:
        fail(f"output target appeared during verification (refusing to overwrite): {out}")
    except OSError as e:
        fail(f"failed to write report atomically: {e}")
    finally:
        if tmp is not None and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    print(f"verification passed: {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"verify_native_30m_product: unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
