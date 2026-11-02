"""Run both local services: .venv/Scripts/python -m scripts.dev"""
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from backend.data import ROOT


def main():
    node = shutil.which('node')
    vite = ROOT / 'frontend/node_modules/vite/bin/vite.js'
    if not node or not vite.exists():
        raise SystemExit('Install Node.js, then run npm ci in frontend first.')
    for port in (8000, 5173):
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit(f'Port {port} is already in use. Stop the existing service first.')
    children = []
    try:
        children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.api:app', '--host', '127.0.0.1', '--port', '8000'], cwd=ROOT))
        children.append(subprocess.Popen([node, str(vite), '--host', '127.0.0.1', '--port', '5173', '--strictPort'], cwd=ROOT/'frontend'))
        deadline = time.monotonic()+45
        while time.monotonic()<deadline:
            if any(p.poll() is not None for p in children):
                raise RuntimeError('A service exited. See its error above.')
            try:
                with urlopen('http://127.0.0.1:8000/api/health', timeout=1) as backend:
                    if b'"ok"' not in backend.read():
                        raise RuntimeError('Backend reports degraded health. See its startup error.')
                with urlopen('http://127.0.0.1:5173/api/health', timeout=1) as response:
                    if b'"ok"' in response.read():
                        break
            except OSError:
                time.sleep(.3)
        else:
            raise RuntimeError('Services did not become ready within 45 seconds.')
        print('\nREADY: http://127.0.0.1:5173\nAPI docs: http://127.0.0.1:8000/docs\nKeep this terminal open. Ctrl+C stops both services.\n', flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in children:
            if p.poll() is None:
                p.terminate()
        for p in children:
            p.wait(timeout=10)


if __name__ == '__main__':
    main()
