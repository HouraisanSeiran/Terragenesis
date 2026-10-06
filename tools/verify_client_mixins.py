"""Transform both client Mixin targets with Fabric without starting Minecraft or a GUI."""
from pathlib import Path
import argparse
import shutil
import subprocess

from build_local import ROOT, REFERENCE, JAVA, BUILD, classpath


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('jar', type=Path, help='mod JAR to verify')
    args = parser.parse_args()
    jar = args.jar.resolve()
    if not jar.is_file():
        parser.error(f'Missing mod JAR: {jar}')

    game = BUILD / 'client-mixin-probe' / jar.stem
    mods = game / 'mods'
    mods.mkdir(parents=True, exist_ok=True)
    shutil.copy2(jar, mods / jar.name)
    api = next((REFERENCE / '.gradle-user/caches/modules-2/files-2.1/net.fabricmc.fabric-api/fabric-api/0.161.0+26.3').rglob('*.jar'))
    shutil.copy2(api, mods / api.name)

    test_classes = BUILD / 'test-classes'
    test_classes.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'src/test/java/com/remotemountains/core/ClientMixinLoadVerification.java'
    subprocess.run([str(JAVA / 'javac.exe'), '--release', '25', '-cp', classpath(),
                    '-d', str(test_classes), str(source)], cwd=ROOT, check=True)
    args_file = ROOT / 'verification/client-managed-service/client.args'
    args_lines = args_file.read_text(encoding='utf-8').splitlines()
    client_cp = args_lines[args_lines.index('"-cp"') + 1].strip('"')
    cp = ';'.join((str(test_classes), client_cp))
    command = [str(JAVA / 'java.exe'), '-Djava.awt.headless=true',
               '-Dfabric.development=false', '-cp', cp,
               'com.remotemountains.core.ClientMixinLoadVerification',
               '--gameDir', str(game), '--version', '26.3']
    result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    lines = result.stdout.splitlines()
    for line in lines:
        if any(marker in line for marker in ('ERROR', 'Exception', 'Caused by:', 'PASS:', 'Mixin Subsystem', 'Loading Minecraft')):
            print(line, flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
