"""Focused region checks without the broad preset/world verification sweep."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from build_local import ROOT, JAVA, classpath


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compile-only", action="store_true")
    args = parser.parse_args()
    out = ROOT / "verification" / "regions" / "classes"
    out.mkdir(parents=True, exist_ok=True)
    sources = sorted((ROOT / "src" / "main" / "java").rglob("*.java"))
    checks = ("RegionVerification", "RawRegionVerification", "DerivedRegionVerification", "DerivedConcurrencyVerification")
    sources.extend(ROOT / "src" / "test" / "java" / "com" / "remotemountains" / "prepared" / (name + ".java") for name in checks)
    argfile = out.parent / "compile.args"
    arguments = ["-encoding", "UTF-8", "--release", "25", "-proc:none",
                 "-classpath", classpath(), "-d", str(out), *map(str, sources)]
    argfile.write_text("\n".join('"' + arg.replace('\\', '/') + '"' for arg in arguments), encoding="utf-8")
    subprocess.run([str(JAVA / "javac.exe"), "@" + str(argfile)], cwd=ROOT, check=True)
    if not args.compile_only:
        (ROOT / "verification" / "governance").mkdir(parents=True, exist_ok=True)
        for name in checks:
            package = "prepared" if name == "RegionVerification" else "region"
            subprocess.run([str(JAVA / "java.exe"), "-Xmx2G", "-Djava.awt.headless=true",
                            "-cp", str(out) + ";" + classpath(),
                            "com.remotemountains." + package + "." + name], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
