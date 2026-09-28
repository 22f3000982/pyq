"""Stream sanitized setup output, including failures and bounded waits."""
import os,queue,subprocess,threading,time
from pathlib import Path
from .migration_service import redact


def run_checked(args,cwd,env,label,log_path,secrets=(),timeout=1800,heartbeat=15):
    log_path=Path(log_path);log_path.parent.mkdir(parents=True,exist_ok=True)
    messages=queue.Queue()
    process=subprocess.Popen(args,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                             text=True,encoding='utf-8',errors='replace',bufsize=1)
    def read_output():
        try:
            for line in process.stdout:messages.put(line)
        finally:messages.put(None)
    reader=threading.Thread(target=read_output,daemon=True);reader.start()
    started=time.monotonic();last_notice=started;finished=False
    def stop():
        if process.poll() is None:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10)
            else:process.kill()
        # taskkill can return before a child process has released the pipe.
        # Never let cleanup replace the useful bounded-timeout error.
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
    with log_path.open('w',encoding='utf-8') as log:
        def emit(line):
            safe=redact(line,secrets);log.write(safe);log.flush();print(safe,end='',flush=True)
        try:
            while not finished:
                now=time.monotonic()
                if now-started>=timeout:
                    stop();reader.join(timeout=2)
                    while not messages.empty():
                        line=messages.get_nowait()
                        if line is not None:emit(line)
                    raise RuntimeError(label+' exceeded '+str(timeout)+' seconds. Live output saved; activation remains blocked.')
                try:
                    line=messages.get(timeout=min(1,max(.01,timeout-(now-started))))
                    if line is None:finished=True
                    else:emit(line)
                except queue.Empty:pass
                if time.monotonic()-last_notice>=heartbeat:
                    emit('['+label+'] still running: '+str(int(time.monotonic()-started))+' seconds elapsed\n')
                    last_notice=time.monotonic()
            code=process.wait(timeout=10)
            if code:raise RuntimeError(label+' failed (exit '+str(code)+'). See the failure above and '+str(log_path))
        finally:
            if process.poll() is None:stop()
            process.stdout.close()
