import argparse
import json
from terrain_pipeline import new_world_river_scene as scene


def main():
    p = argparse.ArgumentParser(description='Extract an authenticated raw river scene from a native water event')
    p.add_argument('water')
    p.add_argument('output')
    p.add_argument('--expected-terrain-identity', required=True)
    p.add_argument('--expected-planner-identity', required=True)
    p.add_argument('--expected-water-identity', required=True)
    p.add_argument('--mouth-id', required=True)
    p.add_argument('--interval', required=True, type=int)
    p.add_argument('--origin-native-xz', required=True, nargs=2, type=int)
    p.add_argument('--shape-zx', required=True, nargs=2, type=int)
    args = vars(p.parse_args())
    water_path = args.pop('water')
    output = args.pop('output')
    manifest, _ = scene.prepare(water_path, output, **args)
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
