"""Dedicated Docker sandbox gateway. Never run this inside the PYQ web service.
Requires a dedicated host; its Docker socket must never be exposed to students.
"""
import ast,hmac,json,os,re,secrets,subprocess,tempfile,time,threading
from pathlib import Path
from flask import Flask,request,jsonify
app=Flask(__name__);app.config['MAX_CONTENT_LENGTH']=600000
slots=threading.BoundedSemaphore(2)
IMAGES={'python':'python:3.12-slim','java':'eclipse-temurin:21-jdk','shell':'mauryahub-oppe-shell:1','postgresql':'postgres:16-alpine'}

def docker(args,**kwargs):return subprocess.run(['docker',*args],**kwargs)

def test(language,code,case,setup,seconds,entrypoint="Main",execution_mode="stdin",entry_function="",entry_functions=None,comparison="text"):
    if not isinstance(entrypoint,str) or not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]{0,79}',entrypoint):raise ValueError('Invalid Java entry class')
    if execution_mode not in ('stdin','python-call','python-dispatch'):raise ValueError('Invalid execution mode')
    if execution_mode in ('python-call','python-dispatch'):
        if language!='python' or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,99}',entry_function):raise ValueError('Invalid entry function')
        call=entry_function+'(*_mh_args)'
        if execution_mode=='python-dispatch':
            if not isinstance(entry_functions,list) or not entry_functions or any(not isinstance(f,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,99}',f) for f in entry_functions):raise ValueError('Invalid dispatch allowlist')
            call="globals()[_mh_selector](*_mh_args)"
        dispatcher="_mh_selector, _mh_args = _mh_args\nif _mh_selector not in "+repr(entry_functions)+": raise ValueError('Unknown function')\n" if execution_mode=='python-dispatch' else ''
        code+="\nimport json as _mh_json, sys as _mh_sys\ndef _mh_decode(v):\n    if isinstance(v,dict):\n        if set(v)=={'__tuple__'}: return tuple(_mh_decode(x) for x in v['__tuple__'])\n        if set(v)=={'__set__'}: return set(_mh_decode(x) for x in v['__set__'])\n        if set(v)=={'__intdict__'}: return {int(k):_mh_decode(x) for k,x in v['__intdict__']}\n        return {k:_mh_decode(x) for k,x in v.items()}\n    if isinstance(v,list): return [_mh_decode(x) for x in v]\n    return v\n_mh_args=_mh_decode(_mh_json.loads(_mh_sys.stdin.read()))\nif not isinstance(_mh_args,list): raise ValueError('Expected JSON argument list')\n"+dispatcher+"_mh_result="+call+"\nprint(repr((_mh_result,_mh_args)))\n"
    started=time.monotonic();name='oppe-'+secrets.token_hex(12)
    with tempfile.TemporaryDirectory(prefix='oppe-') as folder:
        root=Path(folder);filename={'python':'main.py','java':entrypoint+'.java','shell':'main.sh','postgresql':'query.sql'}[language]
        (root/filename).write_text(code,encoding='utf-8')
        if language=='postgresql':(root/'setup.sql').write_text(case.get('setup_sql') or setup,encoding='utf-8')
        for path,text in case.get('files',{}).items():
            dest=(root/path).resolve()
            if not isinstance(path,str) or not path or len(path)>100 or root.resolve() not in dest.parents or dest.name in ('main.py','Main.java','main.sh','query.sql','setup.sql'):raise ValueError('Unsafe fixture path')
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text,encoding='utf-8')
        root.chmod(0o755)
        for p in root.rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
        commands={
          'python':['sh','-c',f'cp -R /work /tmp/work; cd /tmp/work; exec timeout {seconds}s python -I main.py'],
          'shell':['sh','-c',f'cp -R /work /tmp/work; cd /tmp/work; exec timeout {seconds}s bash main.sh'],
          'java':['sh','-c',f"mkdir /tmp/classes; timeout 10s javac -J-Xmx128m -d /tmp/classes '/work/{entrypoint}.java' || exit 65; exec timeout {seconds}s java -Xmx128m -XX:ActiveProcessorCount=1 -XX:-UsePerfData -cp /tmp/classes '{entrypoint}'"],
          'postgresql':['sh','-c',"initdb -D /tmp/pgdata -A trust >/dev/null 2>&1 && pg_ctl -D /tmp/pgdata -l /tmp/pg.log -o '-k /tmp -h \"\"' -w start >/dev/null 2>&1 && psql -h /tmp -U postgres -v ON_ERROR_STOP=1 -q -f /work/setup.sql >/dev/null && exec psql -h /tmp -U postgres -v ON_ERROR_STOP=1 -qAt -f /work/query.sql"]}
        user='postgres' if language=='postgresql' else '65534:65534'
        case_env=case.get('environment',{})
        if not isinstance(case_env,dict) or len(case_env)>15:raise ValueError('Invalid environment')
        for k,v in case_env.items():
            if not isinstance(k,str) or not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,49}',k) or k in ('PATH','HOME','BASH_ENV','ENV','TMPDIR','PGOPTIONS') or k.startswith(('LD_','PYTHON','JAVA','OPPE_')) or not isinstance(v,str) or len(v)>2000:raise ValueError('Unsafe environment variable')
        args=['run','--rm','--name',name,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','128','--memory','512m','--memory-swap','512m','--cpus','1','--ulimit','nofile=128:128','--ulimit','fsize=65536:65536','--tmpfs','/tmp:rw,nosuid,nodev,size=128m,mode=1777','--user',user,'--mount',f'type=bind,src={root},dst=/work,readonly','--workdir','/work','--env',f'PGOPTIONS=-c statement_timeout={seconds*1000}','--log-driver','none','-i',*[part for k,v in case_env.items() for part in ('--env',k+'='+v)],IMAGES[language],*commands[language]]
        try:
            # File-backed capture is capped by Docker log settings plus an active byte monitor.
            with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err,tempfile.TemporaryFile() as inp:
                inp.write(case.get('input','').encode());inp.seek(0)
                process=subprocess.Popen(['docker',*args],stdin=inp,stdout=out,stderr=err)
                deadline=started+seconds+15;reason=None
                while process.poll() is None:
                    if os.fstat(out.fileno()).st_size+os.fstat(err.fileno()).st_size>100000:reason='Output limit exceeded';break
                    if time.monotonic()>deadline:reason='Time limit exceeded';break
                    time.sleep(.03)
                if reason:
                    docker(['kill',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5);process.kill();process.wait(timeout=5)
                out.seek(0);err.seek(0);output=out.read(20000).decode('utf-8','replace');error=err.read(4000).decode('utf-8','replace')
                if process.returncode==124:reason='Time limit exceeded'
                if process.returncode==125:raise RuntimeError('Docker could not create sandbox')
                equal=output.replace('\r\n','\n').rstrip('\n')==case.get('expected','').replace('\r\n','\n').rstrip('\n')
                if comparison=='python-value':
                    try:equal=ast.literal_eval(output.strip())==ast.literal_eval(case.get('expected','').strip())
                    except (ValueError,SyntaxError,RecursionError,MemoryError):equal=False
                passed=not reason and process.returncode==0 and equal
                return dict(passed=passed,status=reason or ('Accepted' if passed else 'Compilation error' if process.returncode==65 else 'Runtime error' if process.returncode else 'Wrong answer'),output=output,error=error,duration_ms=round((time.monotonic()-started)*1000))
        finally:
            docker(['rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)

@app.post('/execute')
def execute():
    token=os.getenv('OPPE_RUNNER_TOKEN','')
    if len(token)<32 or not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+token):return jsonify(error='Unauthorized'),401
    b=request.get_json(silent=True)
    if not isinstance(b,dict) or not isinstance(b.get('language'),str) or b.get('language') not in IMAGES:return jsonify(error='Invalid language'),400
    if not isinstance(b.get('entrypoint','Main'),str) or not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]{0,79}',b.get('entrypoint','Main')):return jsonify(error='Invalid entry class'),400
    tests=b.get('tests');code=b.get('code');seconds=b.get('time_limit',3)
    if not isinstance(b.get('setup_sql',''),str) or len(b.get('setup_sql',''))>30000:return jsonify(error='Invalid SQL setup'),400
    if not isinstance(code,str) or len(code)>90000 or not isinstance(tests,list) or not 1<=len(tests)<=20 or type(seconds)!=int or not 1<=seconds<=10:return jsonify(error='Invalid execution payload'),400
    for t in tests:
        if not isinstance(t,dict) or any(not isinstance(t.get(k,''),str) or len(t.get(k,''))>20000 for k in ('input','expected')):return jsonify(error='Invalid test'),400
        if not isinstance(t.get('setup_sql',''),str) or len(t.get('setup_sql',''))>30000:return jsonify(error='Invalid test SQL setup'),400
        files=t.get('files',{})
        if not isinstance(files,dict) or len(files)>10 or any(not isinstance(k,str) or not isinstance(v,str) or len(v)>20000 for k,v in files.items()):return jsonify(error='Invalid fixtures'),400
    if not slots.acquire(blocking=False):return jsonify(error='Busy'),429
    try:return jsonify(results=[test(b['language'],code,t,b.get('setup_sql',''),seconds,b.get('entrypoint','Main'),b.get('execution_mode','stdin'),b.get('entry_function',''),b.get('entry_functions',[]),b.get('comparison','text')) for t in tests])
    except (ValueError,RuntimeError,subprocess.SubprocessError,OSError):app.logger.exception('Sandbox execution failed');return jsonify(error='Sandbox unavailable'),503
    finally:slots.release()

if __name__=='__main__':app.run(host='127.0.0.1',port=8090,threaded=True)
