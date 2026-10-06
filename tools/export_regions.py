"""Prepare a bounded region rectangle with the same Java path used by the mod."""
import argparse
import subprocess

from build_local import ROOT, JAVA, classpath


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', help='Region cache directory; use the same path in game')
    parser.add_argument('seed', type=int, help='Minecraft world seed')
    parser.add_argument('min_rx', type=int)
    parser.add_argument('min_rz', type=int)
    parser.add_argument('max_rx', type=int)
    parser.add_argument('max_rz', type=int)
    parser.add_argument('--identity', default='', help='Require this Terrain Diffusion model identity')
    parser.add_argument('--chunks', type=int, default=24, help='Storage region width in chunks (default: 24)')
    parser.add_argument('--offline', action='store_true', help='Require existing region files')
    parser.add_argument('--port', type=int, default=19802, help='Local model service port (default: 19802)')
    args = parser.parse_args()
    jar = ROOT / 'build/libs/Terragenesis-26.3-0.13.0.jar'
    if not jar.is_file():
        parser.error(f'Build the mod first: {jar}')
    command = [str(JAVA / 'java.exe'), '-Xmx4G',
               f'-Dremotemountains.diffusionHome={ROOT}',
               '-Dremotemountains.conditioningMode=geographic_v1',
               f'-Dremotemountains.diffusionUrl=http://127.0.0.1:{args.port}',
               f'-Dremotemountains.regionOffline={str(args.offline).lower()}',
               '-cp', str(jar) + ';' + classpath(),
               'com.remotemountains.region.RegionExport',
               args.output_dir, str(args.seed), args.identity,
               str(args.min_rx), str(args.min_rz), str(args.max_rx), str(args.max_rz), str(args.chunks)]
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
