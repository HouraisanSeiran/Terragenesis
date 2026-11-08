import json
import subprocess
import sys
import time
from pathlib import Path
import psutil
from tools.run_native_final_routing import memory

if __name__ == '__main__':
    available, commit = memory()
    if available < 1024**3 or commit < 2*1024**3:
        raise RuntimeError('insufficient reserve')
    started = time.monotonic()
    proc = subprocess.Popen([sys.executable, '-m', 'tools.prepare_native_event_v2'])
    root = psutil.Process(proc.pid)
    peak = private = 0
    minimum = available
    while proc.poll() is None:
        available, commit = memory()
        minimum = min(minimum, available)
        try:
            members = [root] + root.children(recursive=True)
            infos = [p.memory_full_info() for p in members if p.is_running()]
            peak = max(peak, sum(x.rss for x in infos))
            private = max(private, sum(getattr(x, 'private', 0) for x in infos))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            members = []
        if available < 1024**3 or commit < 2*1024**3:
            for p in reversed(members):
                try: p.terminate()
                except psutil.NoSuchProcess: pass
            proc.wait()
            break
        time.sleep(.5)
    result = dict(seconds=time.monotonic()-started, peak_rss=peak, peak_private=private, minimum_available=minimum, exit_code=proc.returncode)
    Path('.scratch/river-upgrade-20261101/native-event-v2-measurements.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(result, flush=True)

