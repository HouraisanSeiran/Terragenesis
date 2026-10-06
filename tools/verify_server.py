"""Run the packaged mod in an isolated world, then reopen it to check persistence."""
from pathlib import Path
import subprocess, shutil, sys, json, time
from build_local import ROOT, REFERENCE, JAVA

raise SystemExit('Legacy procedural-world harness disabled. Direct VDM needs a trained map covering spawn and all tested chunks; do not reuse prototype worlds as diffusion validation.')
run=ROOT/'run-verification';(run/'mods').mkdir(parents=True,exist_ok=True)
verification=ROOT/'verification';verification.mkdir(exist_ok=True)
shutil.copy2(ROOT/'build/libs/RemoteMountains-26.3-0.1.0.jar',run/'mods')
api=next((REFERENCE/'.gradle-user/caches/modules-2/files-2.1/net.fabricmc.fabric-api/fabric-api/0.161.0+26.3').rglob('*.jar'))
shutil.copy2(api,run/'mods'/api.name)
shutil.copy2(REFERENCE/'run-26.3-server/eula.txt',run/'eula.txt')
(run/'server.properties').write_text('''online-mode=false
server-ip=127.0.0.1
server-port=25587
level-name=world
level-seed=20260927
level-type=remotemountains:landforms
generate-structures=true
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=180000
pause-when-empty-seconds=-1
''',encoding='utf-8')
args=(REFERENCE/'verification/server-26.3.args').read_text(encoding='utf-8')
args=args.replace(str(REFERENCE/'build-tmp').replace('\\','/'),str(ROOT/'build/tmp').replace('\\','/'))
args='"-Dremotemountains.verify=true"\n'+args
(ROOT/'build/tmp').mkdir(parents=True,exist_ok=True)
argfile=verification/'server.args';argfile.write_text(args,encoding='utf-8')
for attempt in range(2):
    log=verification/f'server-{attempt+1}.log'
    print('Starting isolated packaged server pass',attempt+1,flush=True)
    with log.open('w',encoding='utf-8') as stream:
        p=subprocess.Popen([str(JAVA/'java.exe'),'@'+str(argfile)],cwd=run,stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.PIPE)
        try:p.wait(timeout=240)
        except subprocess.TimeoutExpired:
            p.stdin.write(b'stop\n');p.stdin.flush()
            try:p.wait(timeout=30)
            except subprocess.TimeoutExpired:p.kill();p.wait()
            raise RuntimeError('Server verification timed out; see '+str(log))
    text=log.read_text(encoding='utf-8',errors='replace')
    if p.returncode or 'REMOTE_VERIFY_PASS' not in text:
        print(text[-15000:]);raise RuntimeError('Server verification failed')
    shutil.copy2(run/'remote-verification.json',verification/f'world-{attempt+1}.json')
    print('Server pass',attempt+1,'completed',flush=True)
a=json.loads((verification/'world-1.json').read_text());b=json.loads((verification/'world-2.json').read_text())
assert a==b,'Saved chunks changed after server restart'
(verification/'server-results.json').write_text(json.dumps({'passed':True,'restart_identical':True,'chunks':a},indent=2),encoding='utf-8')
print('PASS: packaged Fabric loading, four landforms, biome lookup, chunk generation, save/reload')
