"""A global saved world must fail clearly when its model service is absent."""
import json
import subprocess
import sys
from pathlib import Path
from build_local import ROOT,JAVA


def main():
    folder=Path(sys.argv[1]).resolve()
    if not folder.is_relative_to(ROOT/'verification'):raise ValueError('Use an isolated verification server')
    # Reserved unused port: leave any independently running user service untouched.
    import socket
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    args=(folder/'server.args').read_text(encoding='utf-8').replace('http://127.0.0.1:19804',f'http://127.0.0.1:{port}')
    argfile=folder/'missing-service.args';argfile.write_text(args,encoding='utf-8')
    log=folder/'missing-service.log'
    with log.open('w',encoding='utf-8') as stream:
        process=subprocess.Popen([str(JAVA/'java.exe'),'@'+str(argfile)],cwd=folder/'server',stdout=stream,stderr=subprocess.STDOUT)
        try:process.wait(timeout=90)
        except BaseException:process.kill();process.wait();raise
    text=log.read_text(encoding='utf-8',errors='replace')
    assert 'True diffusion service unavailable' in text,'Missing actionable service error'
    assert 'REMOTE_VERIFY_PASS' not in text,'Global world silently fell back'
    (folder/'missing-service.json').write_text(json.dumps({'passed':True,'fallback':False,'clear_service_error':True}))
    print('PASS missing model service is explicit, no fallback')


if __name__=='__main__':main()
