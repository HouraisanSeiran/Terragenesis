from diffusion.paths import configure
configure()
import argparse

def main():
    parser=argparse.ArgumentParser(description='Train / sample direct XYZ vector displacement diffusion')
    sub=parser.add_subparsers(dest='command',required=True)
    train=sub.add_parser('train');train.add_argument('--data',required=True);train.add_argument('--output',required=True)
    train.add_argument('--data-kind',choices=['synthetic-fixture','measured-vdm'],required=True)
    train.add_argument('--steps',type=int,default=10000);train.add_argument('--batch',type=int,default=4)
    train.add_argument('--width',type=int,default=32);train.add_argument('--timesteps',type=int,default=1000)
    train.add_argument('--learning-rate',type=float,default=2e-4)
    sample=sub.add_parser('sample');sample.add_argument('--checkpoint',required=True);sample.add_argument('--condition',required=True)
    sample.add_argument('--output',required=True);sample.add_argument('--steps',type=int,default=50)
    sample.add_argument('--allow-experimental',action='store_true')
    sculpt=sub.add_parser('sculpt-cliff');sculpt.add_argument('--input',required=True);sculpt.add_argument('--mask',required=True)
    sculpt.add_argument('--output',required=True);sculpt.add_argument('--center',type=float,nargs=2,required=True)
    sculpt.add_argument('--normal',type=float,nargs=2,required=True);sculpt.add_argument('--height',type=float,default=24)
    sculpt.add_argument('--transition',type=float,default=12);sculpt.add_argument('--overhang',type=float,default=3)
    prepare=sub.add_parser('prepare-condition');prepare.add_argument('--tile',required=True);prepare.add_argument('--output',required=True)
    prepare.add_argument('--origin',type=float,nargs=2,required=True);prepare.add_argument('--spacing',type=float,default=2)
    prepare.add_argument('--region',type=int,choices=range(4),required=True)
    for command in (train,sample):
        command.add_argument('--device',choices=['cuda','cpu'],default='cuda');command.add_argument('--seed',type=int,default=20260927)
    args=parser.parse_args()
    if args.command=='train':
        from .train import train
        train(args)
    elif args.command=='sample':
        from .sample import sample
        sample(args)
    elif args.command=='sculpt-cliff':
        from .postprocess import sculpt
        sculpt(args)
    else:
        from .conditions import prepare
        prepare(args)

if __name__=='__main__':main()
