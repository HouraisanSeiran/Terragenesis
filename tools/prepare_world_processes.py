"""Explicit world-process preparation from a generic npz source or checkpoint."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline import world_processes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', help='npz arrays with metadata_json and optional material__ fields')
    parser.add_argument('--checkpoint')
    parser.add_argument('--product', help='published coarse process product for explicit detailed continuation')
    parser.add_argument('--native-terrain', action='append', default=[], help='JSON entry containing manifest_path and manifest_sha256; maximum four')
    parser.add_argument('--out', required=True)
    parser.add_argument('--config', help='explicit JSON numerical and resource configuration')
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args(argv)
    cfg = json.loads(Path(args.config).read_text(encoding='utf-8')) if args.config else None
    if args.product:
        entries=[json.loads(Path(path).read_text(encoding='utf-8')) for path in args.native_terrain]
        result=world_processes.continue_details(args.product,args.out,terrain_entries=entries,config=cfg)
    elif args.checkpoint:
        result = world_processes.resume(args.checkpoint, args.out, config=cfg)
    else:
        if not args.source:
            parser.error('--source, --checkpoint or --product is required')
        with np.load(args.source, allow_pickle=False) as bundle:
            source = json.loads(str(bundle['metadata_json']))
            source.update({k: bundle[k] for k in bundle.files if k != 'metadata_json' and not k.startswith('material__')})
            materials = {k[10:]: bundle[k] for k in bundle.files if k.startswith('material__')}
        if materials:
            source['materials'] = materials
        result = world_processes.plan(source, cfg) if args.plan_only else world_processes.prepare(source, args.out, cfg)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
