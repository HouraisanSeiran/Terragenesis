from .paths import configure
configure()
import argparse
from .config import GenerationConfig
from .service import TerrainService,serve

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=19802)
    parser.add_argument('--device',choices=['cuda','cpu'],default='cuda')
    parser.add_argument('--conditions')
    parser.add_argument('--conditioning-mode',choices=['geographic_v1','geographic_v2','legacy_worldclim'],default='geographic_v1')
    parser.add_argument('--meters-per-height-block',type=float)
    parser.add_argument('--elevation-snr',type=float)
    parser.add_argument('--preview',action='store_true')
    parser.add_argument('--seed',type=int,default=20260927)
    parser.add_argument('--x',type=int,default=0);parser.add_argument('--z',type=int,default=0)
    args=parser.parse_args()
    overrides={'device':args.device,'dtype':'fp32','conditions':args.conditions}
    if args.meters_per_height_block is not None:overrides['meters_per_height_block']=args.meters_per_height_block
    if args.elevation_snr is not None:overrides['cond_snr']=(args.elevation_snr,0.1,1.0,0.1,1.0)
    config=GenerationConfig.for_profile(args.conditioning_mode,**overrides)
    service=TerrainService(config)
    if args.preview:
        from .preview import export
        try:export(service,args.seed,args.x,args.z)
        finally:service.backend.close()
    else:serve(service,args.port)
if __name__=='__main__':main()
