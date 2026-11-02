"""Watchdog for the wall static server: probes the port, respawns serve.py when it goes down.

usage: python serve_guard.py [port] [root]     defaults: 8899, current working directory
Idempotent — if something else already serves the port it stands by instead of colliding.
Acts only on `connection refused` (two in a row) or a child that exited; a merely slow probe is
counted and only treated as wedged after 8 consecutive misses (64s).
Start it detached so closing a terminal does not take the wall with it:
  powershell -NoProfile -Command "Start-Process -FilePath <python> -ArgumentList '<path>\\serve_guard.py','<port>','<root>' -WindowStyle Hidden"
"""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
ROOT = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, 'serve_guard.log')
PROBE = 'http://127.0.0.1:%d/' % PORT

child = None
restarts = 0


def note(msg):
    line = '%s guard(py) %s' % (time.strftime('%Y-%m-%dT%H:%M:%S'), msg)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass
    print(line, flush=True)


def probe():
    """'up' = answered; 'slow' = connected but too busy to answer in time; 'refused' = nothing listening."""
    try:
        with urllib.request.urlopen(PROBE, timeout=6) as r:
            r.read(64)
        return 'up'
    except Exception as e:
        reason = getattr(e, 'reason', e)
        if isinstance(reason, ConnectionRefusedError) or '10061' in str(reason) or 'refused' in str(reason).lower():
            return 'refused'
        return 'slow'


def start():
    global child
    out = open(os.path.join(HERE, 'serve.out.log'), 'a', encoding='utf-8')
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    child = subprocess.Popen([sys.executable, os.path.join(HERE, 'serve.py'), str(PORT), ROOT],
                             stdout=out, stderr=subprocess.STDOUT, creationflags=flags)
    note('spawned serve.py pid=%d port=%d root=%s' % (child.pid, PORT, ROOT))


if __name__ == '__main__':
    note('guard start pid=%d watching port %d (restart on refused x2 or wedged slow x8)' % (os.getpid(), PORT))
    stood_by = False
    refused = slow = 0
    while True:
        if child is not None and child.poll() is not None:
            note('serve.py exited code=%s' % child.returncode)
            child = None
            refused = 2
        state = probe()
        if state == 'up':
            refused = slow = 0
            if child is None and not stood_by:
                note('port served by something else (not my child); standing by')
                stood_by = True
        elif state == 'slow':
            refused = 0
            slow += 1
            if child is not None and slow >= 8:
                note('port unresponsive to 8 probes (64s) though pid=%s lives -> restart as wedged' % child.pid)
                child = None
                refused = 2
            elif slow in (1, 5):
                note('probe slow (%d) — busy, not dead' % slow)
        else:
            slow = 0
            refused += 1
            if refused == 1:
                note('connection refused (1/2)')
            if refused >= 2:
                stood_by = False
                refused = 0
                if child is not None:
                    note('refused while pid=%s listed -> killing it' % child.pid)
                    try:
                        child.kill()
                        child.wait(timeout=3)
                    except Exception:
                        pass
                    child = None
                restarts += 1
                note('port %d down -> restart #%d' % (PORT, restarts))
                start()
        time.sleep(8)
