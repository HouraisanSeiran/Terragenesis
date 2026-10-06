"""Check the installed DH caller and compiled generator agree on terrain completion."""
from pathlib import Path
import argparse
import re
import subprocess
from build_local import ROOT, JAVA, BUILD

parser = argparse.ArgumentParser()
parser.add_argument("dh_jar", type=Path)
args = parser.parse_args()
if not args.dh_jar.is_file():
    raise SystemExit("Distant Horizons JAR does not exist")

def bytecode(cp, name):
    return subprocess.check_output([str(JAVA / "javap.exe"), "-classpath", str(cp),
        "-c", "-p", name], cwd=ROOT, text=True, errors="replace")

dh = bytecode(args.dh_jar, "com.seibel.distanthorizons.common.wrappers.worldGeneration.step.StepTerrain")
caller = re.search(r"public void generateGroup\(.*?(?=\n  static \{|\Z)", dh, re.S)
if not caller or not re.search(r"ChunkGenerator\.buildTerrain:.*?\n\s*\d+: pop", caller.group(), re.S):
    raise AssertionError("DH call contract changed: re-inspect buildTerrain future handling")

generator = bytecode(BUILD / "classes", "com.remotemountains.world.RemoteGenerator")
method = re.search(r"public java\.util\.concurrent\.CompletableFuture<net\.minecraft\.world\.level\.chunk\.ChunkAccess> buildTerrain\(.*?(?=\n  public |\Z)", generator, re.S)
if not method:
    raise AssertionError("Compiled RemoteGenerator.buildTerrain not found")
code = method.group()
join = code.find("CompletableFuture.join")
write = code.find("ChunkAccess.setBlockState")
done = code.find("CompletableFuture.completedFuture")
if min(join, write, done) < 0 or not join < write < done:
    raise AssertionError("Chunk writes must finish on the DH calling thread before the returned future")
if "CompletableFuture.thenApply" in code or "CompletableFuture.thenApplyAsync" in code:
    raise AssertionError("Chunk writes moved back into an asynchronous callback")
print("PASS DH ignores terrain future; RemoteGenerator joins prepared data, writes chunk, then returns completed future")
