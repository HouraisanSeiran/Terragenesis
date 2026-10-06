"""Run the real first-install and cold-start probes against one prepared home."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import shutil
from datetime import datetime, timezone
from build_local import ROOT, JAVA, BUILD, classpath

parser = argparse.ArgumentParser()
parser.add_argument("home", type=Path)
args = parser.parse_args()
home = args.home.resolve()
jar = BUILD / "libs/Terragenesis-26.3-0.13.0.jar"
if not jar.is_file():
    raise SystemExit("Build the final mod JAR before running this probe.")
if (home / ".install-ready").exists():
    raise SystemExit("The first probe requires a prepared home without .install-ready.")
if not (home / "models/terrain-diffusion-30m/manifest.json").is_file():
    raise SystemExit("Wait for the cold bootstrap process to finish and report READY.")

cp = ";".join((str(jar), str(BUILD / "test-classes"), classpath()))
source = ROOT / "src/test/java/com/remotemountains/diffusion/FirstInstallProbe.java"
subprocess.run([str(JAVA / "javac.exe"), "-encoding", "UTF-8", "--release", "25",
    "-proc:none", "-cp", cp, "-d", str(BUILD / "test-classes"), str(source)],
    cwd=ROOT, check=True)
archive = ROOT / "verification/python-3.11.9-embed-amd64.zip"
downloads = home / "runtime/downloads"
downloads.mkdir(parents=True, exist_ok=True)
target = downloads / archive.name
if not target.is_file():
    shutil.copyfile(archive, target)
results = []
for mode, timeout in (("first", 2100), ("cold", 30)):
    command = [str(JAVA / "java.exe"), "-Xmx4G", "-cp", cp,
        "com.remotemountains.diffusion.FirstInstallProbe", mode, str(home)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    results.append({"mode": mode, "passed": result.returncode == 0,
                    "stdout": result.stdout.strip(), "stderr": result.stderr.strip()})
    print(result.stdout, end="")
    if result.returncode:
        print(result.stderr)
        break

report = ROOT / "verification/first-install-latest.json"
report.write_text(json.dumps({"timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "home": str(home), "jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
    "results": results}, indent=2), encoding="utf-8")
print("Report:", report)
if len(results) != 2 or not all(item["passed"] for item in results):
    raise SystemExit(1)
