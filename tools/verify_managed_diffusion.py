"""Verify that the mod starts and stops its own model service without a manual server."""
from pathlib import Path
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from build_local import ROOT, JAVA, BUILD, classpath

jar = BUILD / 'libs/Terragenesis-26.3-0.13.0.jar'
if not jar.is_file():
    raise SystemExit('Build the mod before running managed service verification.')
cp = ';'.join((str(jar), str(BUILD / 'test-classes'), classpath()))
result=subprocess.run([str(JAVA / 'java.exe'), '-Xmx2G', '-cp', cp,
    'com.remotemountains.diffusion.ManagedServiceVerification', str(ROOT)],
    cwd=ROOT, capture_output=True, text=True, timeout=420)
report=ROOT/'verification/managed-diffusion-latest.json'
report.parent.mkdir(parents=True,exist_ok=True)
report.write_text(json.dumps({
    'timestamp_utc':datetime.now(timezone.utc).isoformat(),
    'passed':result.returncode==0,
    'jar_sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),
    'output':result.stdout.strip(),
    'error':result.stderr.strip() if result.returncode else '',
    'checks':['missing home refused','managed startup','real tile sample',
              'model identity mismatch refused','owned service shutdown'],
},indent=2),encoding='utf-8')
print(result.stdout,end='')
if result.returncode:
    print(result.stderr)
    raise SystemExit(result.returncode)
print('Report:',report)
