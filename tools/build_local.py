"""Offline build using read-only, already installed Java/Minecraft dependencies.
All generated files stay in this workspace. Gradle is the portable alternative.
"""
from pathlib import Path
import argparse, os, json, subprocess, zipfile, shutil, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(os.environ.get('REMOTE_TOOLCHAIN_ROOT', r'D:\codexwork\MinecraftZombieArmy'))
JAVA = REFERENCE / 'tools/jdk-25.0.2/bin'
BUILD = ROOT / 'build'
OUT = BUILD / 'classes'

def classpath():
    paths = (REFERENCE / 'verification/server-classpath.txt').read_text().strip().split(';')
    paths = [p for p in paths if '.gradle-user' in p and Path(p).is_file()]
    paths += [str(REFERENCE / '.gradle-user/caches/fabric-loom/26.3/minecraft-common.jar')]
    paths += [str(REFERENCE / '.gradle-user/caches/fabric-loom/26.3/minecraft-client.jar')]
    api = next((REFERENCE / '.gradle-user/caches/modules-2/files-2.1/net.fabricmc.fabric-api/fabric-api/0.161.0+26.3').rglob('*.jar'))
    extracted=BUILD/'api';extracted.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(api) as archive:
        for name in archive.namelist():
            if name.endswith('.jar'):
                target=extracted/Path(name).name
                if not target.exists():target.write_bytes(archive.read(name))
                paths.append(str(target))
    return ';'.join(dict.fromkeys(paths))

def run(main, extra=()):
    cp = ';'.join([str(OUT), str(OUT.parent / 'test-classes'), str(ROOT / 'src/main/resources'), classpath()])
    return subprocess.run([str(JAVA / 'java.exe'), '-Xmx2G', '-Djava.awt.headless=true', '-cp', cp, main, *extra], cwd=ROOT, check=True)

def build(version=None, output=None, verify_only=True):
    if version is None:
        version = next(line.split("'", 2)[1] for line in (ROOT/'build.gradle').read_text(encoding='utf-8').splitlines()
                       if line.startswith('version = '))
    if not version or any(c not in '0123456789.' for c in version):
        raise ValueError('Invalid build version')
    (BUILD / 'candidates').mkdir(parents=True, exist_ok=True)
    build_root = Path(tempfile.mkdtemp(prefix=version+'-', dir=BUILD/'candidates'))
    global OUT
    OUT = build_root / 'classes'
    OUT.mkdir(parents=True, exist_ok=True)
    args = ['-encoding', 'UTF-8', '--release', '25', '-proc:none', '-classpath', classpath(), '-d', str(OUT)]
    args += [str(p) for p in (ROOT / 'src/main/java').rglob('*.java')]
    argfile = build_root / 'compile.args'
    argfile.write_text('\n'.join('"'+a.replace('\\','/')+'"' for a in args), encoding='utf-8')
    subprocess.run([str(JAVA / 'javac.exe'), '@'+str(argfile)], cwd=ROOT, check=True)
    tests = list((ROOT / 'src/test/java').rglob('*.java'))
    if tests:
        testout = build_root / 'test-classes'; testout.mkdir(exist_ok=True)
        args = ['-encoding','UTF-8','--release','25','-proc:none','-cp',str(OUT)+';'+classpath(),'-d',str(testout),*map(str,tests)]
        argfile.write_text('\n'.join('"'+a.replace('\\','/')+'"' for a in args), encoding='utf-8')
        subprocess.run([str(JAVA / 'javac.exe'), '@'+str(argfile)], cwd=ROOT, check=True)
        run('com.remotemountains.core.CoreVerification')
        run('com.remotemountains.diffusion.ManagedInstallationVerification')
        run('com.remotemountains.region.RawRegionVerification')
        run('com.remotemountains.region.DerivedRegionVerification')
        run('com.remotemountains.region.DerivedConcurrencyVerification')
        metric_fixture=ROOT/'verification/metric-region-v1/minecraft-plains.tgmc'
        if metric_fixture.exists():run('com.remotemountains.region.MetricProcessedVerification',[str(metric_fixture)])
        run('com.remotemountains.region.processing.RegionProcessorVerification')
        run('com.remotemountains.core.TerrainModeRegistryVerification')
        run('com.remotemountains.core.TerrainTileCacheVerification')
        run('com.remotemountains.hydrology3d.RiverNetworkVerification')
        run('com.remotemountains.core.DiffusionVerification')
        run('com.remotemountains.cliff.CliffVerification')
        run('com.remotemountains.core.DemoVerification')
        run('com.remotemountains.cliff.RegionalCliffVerification')
        run('com.remotemountains.prepared.RegionVerification')
        run('com.remotemountains.core.TerrainScaleVerification')
        run('com.remotemountains.watershed.WatershedVerification')
        run('com.remotemountains.watershed.WatershedHeightmapVerification')
        run('com.remotemountains.prepared.PreparedArtifactVerification')
        run('com.remotemountains.watershedcliff.WatershedCliffVerification')
        run('com.remotemountains.canyon.CanyonVerification')
        fixture=ROOT/'verification/vdm-contract/displacement.rmdv'
        if fixture.exists():run('com.remotemountains.core.DiffusionVerification',[str(fixture)])
    if verify_only:
        print('Verified sources; Jar unchanged', flush=True)
        return
    if output is None:
        raise ValueError('Jar output path is required; pass --output')
    jar = Path(output).resolve()
    jar.relative_to(ROOT.resolve())
    jar.parent.mkdir(parents=True, exist_ok=True)
    if jar.exists():
        raise FileExistsError(f'Refusing to overwrite existing Jar: {jar}')
    with zipfile.ZipFile(jar,'x',zipfile.ZIP_DEFLATED) as archive:
        for folder in [OUT, ROOT / 'src/main/resources']:
            for p in folder.rglob('*'):
                if p.is_file():
                    data=p.read_bytes()
                    if p.name=='fabric.mod.json':data=data.replace(b'${version}',version.encode('ascii'))
                    archive.writestr(p.relative_to(folder).as_posix(), data)
        for p in (ROOT / 'diffusion').glob('*.py'):
            archive.write(p, 'remotemountains-service/diffusion/' + p.name)
        archive.write(ROOT/'tools/bootstrap_diffusion.py', 'remotemountains-service/tools/bootstrap_diffusion.py')
        for p in (ROOT/'bootstrap-assets').iterdir():
            if p.is_file():archive.write(p,'remotemountains-service/bootstrap-assets/'+p.name)
        upstream=ROOT/'vendor/terrain-diffusion-e8dcb4b1a834ab2f6b1a6f5256ed7c9f2f3e8230'
        for name in json.loads((upstream/'inference-files.json').read_text(encoding='utf-8')):
            archive.write(upstream/name,
                'remotemountains-service/vendor/'+upstream.name+'/'+name)
        upstream_license=ROOT/'vendor/terrain-diffusion-e8dcb4b1a834ab2f6b1a6f5256ed7c9f2f3e8230/LICENSE'
        archive.write(upstream_license,'META-INF/licenses/terrain-diffusion-LICENSE.txt')
    print('Built',jar,flush=True)
    if '--preview' in sys.argv:run('com.remotemountains.core.PreviewExporter')

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--version')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    build(args.version, args.output, args.verify_only or args.output is None)
