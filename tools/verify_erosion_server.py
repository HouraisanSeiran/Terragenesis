"""Test the 0.3.0 packaged mod against real server blocks, save and restart."""
from pathlib import Path
import json
import shutil
import subprocess
from build_local import ROOT, REFERENCE, JAVA


def main():
    verification = ROOT / 'verification/erosion-server'
    run = ROOT / 'run-erosion-verification'
    verification.mkdir(parents=True, exist_ok=True)
    (run / 'mods').mkdir(parents=True, exist_ok=True)
    jar = ROOT / 'build/libs/RemoteMountains-26.3-0.3.0.jar'
    shutil.copy2(jar, run / 'mods' / jar.name)
    api = next((REFERENCE / '.gradle-user/caches/modules-2/files-2.1/net.fabricmc.fabric-api/fabric-api/0.161.0+26.3').rglob('*.jar'))
    shutil.copy2(api, run / 'mods' / api.name)
    shutil.copy2(REFERENCE / 'run-26.3-server/eula.txt', run / 'eula.txt')
    for name in ('world', 'world_nether', 'world_the_end', 'crash-reports', 'logs'):
        target = run / name
        if not target.resolve().is_relative_to(run.resolve()) or not run.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError('Refusing to clear outside the isolated workspace test run')
        if target.is_symlink():
            raise RuntimeError('Refusing a linked test directory')
        if target.exists():
            shutil.rmtree(target)
    (run / 'server.properties').write_text('''online-mode=false
server-ip=127.0.0.1
server-port=25588
level-name=world
level-seed=20260927
level-type=remotemountains:landforms
generate-structures=false
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
pause-when-empty-seconds=-1
''', encoding='utf-8')
    args = (REFERENCE / 'verification/server-26.3.args').read_text(encoding='utf-8')
    args = args.replace(str(REFERENCE / 'build-tmp').replace('\\', '/'), '../build/tmp')
    args = '"-Dremotemountains.verify=true"\n"-Dremotemountains.verifyErosion=true"\n' + args
    (ROOT / 'build/tmp').mkdir(parents=True, exist_ok=True)
    argfile = verification / 'server.args'
    argfile.write_text(args, encoding='utf-8')
    results = []
    for attempt in range(1, 3):
        log = verification / f'server-{attempt}.log'
        print(f'Starting erosion server pass {attempt}', flush=True)
        with log.open('w', encoding='utf-8') as stream:
            process = subprocess.Popen([str(JAVA / 'java.exe'), '@' + str(argfile)], cwd=run,
                stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
            try:
                process.wait(timeout=900)
            except BaseException:
                process.kill(); process.wait(); raise
        text = log.read_text(encoding='utf-8', errors='replace')
        if process.returncode or 'REMOTE_EROSION_WORLD_PASS' not in text or 'REMOTE_VERIFY_PASS' not in text:
            raise RuntimeError(f'Erosion world verification failed: {log}')
        result = {
            'chunks': json.loads((run / 'remote-verification.json').read_text()),
            'cliff': json.loads((run / 'cliff-world-verification.json').read_text()),
        }
        results.append(result)
        (verification / f'world-{attempt}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(f'Completed erosion server pass {attempt}', flush=True)
    if results[0] != results[1]:
        raise AssertionError('Blocks or erosion state changed after saving and restarting')
    summary = {
        'passed': True, 'restart_identical': True, 'version': '0.3.0',
        'checked_blocks': results[0]['cliff']['checked_blocks'],
        'changed_by_erosion': results[0]['cliff']['changed_by_erosion'],
        'recipe': results[0]['cliff']['recipe'],
        'erosion_statistics': results[0]['cliff']['erosion_statistics'],
    }
    (verification / 'results.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print('PASS actual Minecraft erosion + save/reload: ' + json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
