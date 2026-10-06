"""Fresh workspace-only servers; real diffusion for global mode; save/reload comparison."""
import argparse
import json
import shutil
import subprocess
from datetime import datetime
from build_local import ROOT, REFERENCE, JAVA
from nbt_reader import NbtReader


def java_command(argfile):
    # Pass Unicode paths directly; the Java @argfile parser uses the host code page.
    args=[]
    for line in argfile.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        if line.startswith('"') and line.endswith('"'):line=line[1:-1]
        args.append(line)
    return [str(JAVA/'java.exe'),*args]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['demo','global','watershed','canyon','canyon_single'])
    args=parser.parse_args()
    output=ROOT/'verification'/('presets-'+args.mode)/datetime.now().strftime('%Y%m%d-%H%M%S')
    run=output/'server';(run/'mods').mkdir(parents=True)
    jar=ROOT/'build/libs/Terragenesis-26.3-0.9.0.jar'
    shutil.copy2(jar,run/'mods'/jar.name)
    api=next((REFERENCE/'.gradle-user/caches/modules-2/files-2.1/net.fabricmc.fabric-api/fabric-api/0.161.0+26.3').rglob('*.jar'))
    shutil.copy2(api,run/'mods'/api.name)
    shutil.copy2(REFERENCE/'run-26.3-server/eula.txt',run/'eula.txt')
    global_mode=args.mode=='global'
    canyon=args.mode in ('canyon','canyon_single')
    watershed=args.mode=='watershed' or canyon
    preset=args.mode if watershed else 'global_landforms' if global_mode else 'landforms'
    source='watershed_heightmap_v2' if watershed else 'live_diffusion_global' if global_mode else 'demo_landforms_perlin_v2'
    (run/'server.properties').write_text(f'''online-mode=false
server-ip=127.0.0.1
server-port={25593 if args.mode=='canyon_single' else 25592 if canyon else 25591 if watershed else 25590 if global_mode else 25589}
level-name=world
level-seed=20260927
level-type=remotemountains:{preset}
generate-structures=false
view-distance=2
simulation-distance=2
max-tick-time=-1
pause-when-empty-seconds=-1
''')
    java_args=(REFERENCE/'verification/server-26.3.args').read_text(encoding='utf-8')
    java_args=java_args.replace(str(REFERENCE/'build-tmp').replace('\\','/'),str(ROOT/'build/tmp').replace('\\','/'))
    (ROOT/'build/tmp').mkdir(parents=True,exist_ok=True)
    java_args='"-Dremotemountains.verify=true"\n'+java_args
    if global_mode:
        java_args='"-Dremotemountains.verifyGlobal=true"\n"-Dremotemountains.diffusionUrl=http://127.0.0.1:19804"\n'+java_args
    elif watershed:
        java_args='"-Dremotemountains.verifyWatershed=true"\n'+java_args
        if canyon:java_args='"-Dremotemountains.verifyCanyon=true"\n'+java_args
    else:
        java_args='"-Dremotemountains.verifyErosion=true"\n'+java_args
    argfile=output/'server.args';argfile.write_text(java_args,encoding='utf-8')
    with (output/'service.log').open('w',encoding='utf-8') as service_log:
        try:
            if global_mode:
                java_args='"-Dremotemountains.diffusionHome='+str(ROOT).replace('\\','/')+'"\n"-Dremotemountains.conditioningMode=geographic_v1"\n'+java_args
                argfile.write_text(java_args,encoding='utf-8')
            results=[]
            for attempt in range(1,3):
                log=output/f'server-{attempt}.log'
                print(f'Starting {args.mode} server pass {attempt}: {log}',flush=True)
                with log.open('w',encoding='utf-8') as stream:
                    process=subprocess.Popen(java_command(argfile),cwd=run,stdout=stream,stderr=subprocess.STDOUT)
                    try: process.wait(timeout=1800)
                    except BaseException: process.kill();process.wait();raise
                text=log.read_text(encoding='utf-8',errors='replace')
                if process.returncode or 'REMOTE_VERIFY_PASS' not in text:raise RuntimeError('Server verification failed: '+str(log))
                result=json.loads((run/'remote-verification.json').read_text())
                if watershed:
                    result={'chunks':result,'watershed':json.loads((run/'watershed-world.json').read_text())}
                    if canyon:result['canyon']=json.loads((run/'canyon-world.json').read_text())
                elif not global_mode:
                    result={'chunks':result,'tall_world':json.loads((run/'tall-world.json').read_text())}
                    for i,kind in enumerate(['inselberg','rift','karst','pillars']):
                        assert result['chunks'][i]['biome'].startswith('remotemountains:'+kind+'_')
                results.append(result)
                if not watershed:
                    regional=json.loads((run/'regional-cliff-world.json').read_text())
                    (output/f'regional-{attempt}.json').write_text(json.dumps(regional,indent=2))
                    if attempt==2:assert regional==json.loads((output/'regional-1.json').read_text())
                settings=NbtReader.read_file(run/'world/data/minecraft/world_gen_settings.dat')['data']
                generator=settings['dimensions']['minecraft:overworld']['generator']
                assert generator['terrain_source']==source
                if canyon:assert generator['vdm_recipe']==('watershed-vdm-canyon-v2' if args.mode=='canyon' else 'watershed-vdm-canyon-single-v2')
                assert generator['terrain_scale']=='relief_3x_sea62_1024_v1'
                assert settings['dimensions']['minecraft:overworld']['type']=='remotemountains:overworld_1024'
                assert generator['diffusion_identity']
                (output/f'world-{attempt}.json').write_text(json.dumps({'samples':result,'generator':generator},indent=2))
            assert results[0]==results[1],'Save/reload changed blocks'
            report={'passed':True,'restart_identical':True,'version':'0.9.0','source':source,'samples':results[0]}
            (output/'results.json').write_text(json.dumps(report,indent=2))
            print('PASS '+str(output/'results.json'),flush=True)
        finally:
            pass


if __name__=='__main__':main()
