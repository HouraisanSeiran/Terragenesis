"""Exercise the packaged diffusion + generated VDM mod in a fresh isolated server, twice."""
import json,shutil,subprocess,time,urllib.request
from pathlib import Path
from build_local import ROOT,REFERENCE,JAVA

def main():
    verification=ROOT/'verification/diffusion-server';verification.mkdir(parents=True,exist_ok=True)
    run=ROOT/'run-diffusion-verification';(run/'mods').mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'build/libs/RemoteMountains-26.3-0.2.0.jar',run/'mods')
    api=next((REFERENCE/'.gradle-user/caches/modules-2/files-2.1/net.fabricmc.fabric-api/fabric-api/0.161.0+26.3').rglob('*.jar'))
    shutil.copy2(api,run/'mods'/api.name);shutil.copy2(REFERENCE/'run-26.3-server/eula.txt',run/'eula.txt')
    # A verification run must begin with a fresh world; reusing a previous baked hash
    # intentionally fails the mod's compatibility guard.
    for generated in ('world','world_nether','world_the_end','crash-reports','logs'):
        target=run/generated
        if target.exists():shutil.rmtree(target)
    (run/'server.properties').write_text('''online-mode=false
server-ip=127.0.0.1
server-port=25587
level-name=world
level-seed=20260927
level-type=remotemountains:landforms
generate-structures=false
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
pause-when-empty-seconds=-1
''',encoding='utf-8')
    args=(REFERENCE/'verification/server-26.3.args').read_text(encoding='utf-8')
    args=args.replace(str(REFERENCE/'build-tmp').replace('\\','/'),'../build/tmp')
    args='"-Dremotemountains.verify=true"\n'+args
    (ROOT/'build/tmp').mkdir(parents=True,exist_ok=True)
    argfile=verification/'server.args';argfile.write_text(args,encoding='utf-8')
    service_log=None;service=None
    try:
        health={'backend':'baked real Terrain Diffusion','source':json.loads((ROOT/'src/main/resources/assets/remotemountains/terrain/demo.json').read_text())}
        results=[]
        for attempt in range(2):
            log=verification/f'server-{attempt+1}.log'
            print('Starting packaged server pass',attempt+1,flush=True)
            with log.open('w',encoding='utf-8') as stream:
                process=subprocess.Popen([str(JAVA/'java.exe'),'@'+str(argfile)],cwd=run,stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.PIPE)
                try:process.wait(timeout=1800)
                except BaseException:
                    process.kill();process.wait();raise
            content=log.read_text(encoding='utf-8',errors='replace')
            if process.returncode or 'REMOTE_VERIFY_PASS' not in content:raise RuntimeError('Server verification failed: '+str(log))
            result=json.loads((run/'remote-verification.json').read_text())
            results.append(result);(verification/f'world-{attempt+1}.json').write_text(json.dumps(result,indent=2))
            print('Server pass completed',attempt+1,flush=True)
        if results[0]!=results[1]:raise AssertionError('Saved chunks changed after restart')
        (verification/'results.json').write_text(json.dumps({'passed':True,'restart_identical':True,'service':health,'chunks':results[0]},indent=2))
        print('PASS: real Terrain Diffusion + VDM + Minecraft generation/save/reload',flush=True)
    finally:
        if service is not None:
            service.terminate()
            try:service.wait(timeout=10)
            except subprocess.TimeoutExpired:service.kill();service.wait()
        if service_log is not None:service_log.close()

if __name__=='__main__':main()
