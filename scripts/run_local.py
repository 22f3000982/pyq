"""Run web + upload worker locally, without starting paused catalog jobs."""
import subprocess,sys,time,webbrowser
from pathlib import Path
root=Path(__file__).resolve().parents[1]
worker=subprocess.Popen([sys.executable,'-m','flask','--app','backend:create_app','worker'],cwd=root)
web=subprocess.Popen([sys.executable,'-m','flask','--app','backend:create_app','run','--port','5000'],cwd=root)
print('Open http://127.0.0.1:5000 — Ctrl+C stops web and worker. Bulk catalog remains paused.',flush=True)
try:
    time.sleep(2)
    if web.poll() is not None:raise RuntimeError('Web server did not start; check output above.')
    webbrowser.open('http://127.0.0.1:5000')
    while web.poll() is None and worker.poll() is None:time.sleep(1)
finally:
    for p in (web,worker):
        if p.poll() is None:p.terminate()
    for p in (web,worker):
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:p.kill()
