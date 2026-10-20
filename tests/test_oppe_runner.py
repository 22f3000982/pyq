import importlib.util
from pathlib import Path
import pytest

@pytest.fixture
def gateway():
    path=Path(__file__).parents[1]/'tools/oppe-runner/runner.py'
    spec=importlib.util.spec_from_file_location('oppe_gateway',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_gateway_auth_and_validation(gateway,monkeypatch):
    c=gateway.app.test_client();assert c.post('/execute',json={}).status_code==401
    monkeypatch.setenv('OPPE_RUNNER_TOKEN','x'*40);headers={'Authorization':'Bearer '+'x'*40}
    assert c.post('/execute',json={'language':'host-shell'},headers=headers).status_code==400
    monkeypatch.setattr(gateway,'test',lambda *args:dict(passed=True,status='Accepted',output='5',error='',duration_ms=1))
    r=c.post('/execute',json={'language':'python','code':'print(5)','time_limit':3,'tests':[{'input':'','expected':'5'}]},headers=headers)
    assert r.json['results'][0]['passed']
    gateway.slots.acquire();gateway.slots.acquire()
    try:assert c.post('/execute',json={'language':'python','code':'x','tests':[{}]},headers=headers).status_code==429
    finally:gateway.slots.release();gateway.slots.release()

@pytest.mark.parametrize('language',['python','java','shell','postgresql'])
def test_gateway_uses_isolated_nonroot_docker_not_host_execution(gateway,monkeypatch,language):
    calls=[]
    class Process:
        returncode=0
        def poll(self):return 0
    def popen(args,**kwargs):
        calls.append(args);kwargs['stdout'].write(b'5\n');return Process()
    monkeypatch.setattr(gateway.subprocess,'Popen',popen)
    monkeypatch.setattr(gateway,'docker',lambda args,**kwargs:None)
    r=gateway.test(language,'example',{'input':'','expected':'5\n','files':{'data/file.txt':'fixture'}},'SELECT 1;',3)
    assert r['passed'];cmd=calls[0]
    for flag in ('--network','--read-only','--cap-drop','--security-opt','--pids-limit','--memory','--memory-swap','--cpus','--user','--tmpfs','--log-driver'):assert flag in cmd
    assert cmd[cmd.index('--network')+1]=='none'
    assert cmd[cmd.index('--user')+1]!='root'
    assert cmd[0]=='docker'

def test_gateway_rejects_traversal_before_execution(gateway):
    with pytest.raises(ValueError):gateway.test('python','x',{'files':{'../escape':'bad'}},'',3)

@pytest.mark.parametrize('mode',['python-call','python-dispatch'])
def test_function_harness_is_built_inside_sandbox(gateway,monkeypatch,mode):
    import ast
    captured={}
    class Process:
        returncode=0
        def poll(self):return 0
    def popen(args,**kwargs):
        mount=args[args.index('--mount')+1]
        root=Path(mount.split('src=')[1].split(',')[0])
        captured['source']=(root/'main.py').read_text()
        captured['cmd']=args
        kwargs['stdout'].write(b"({2, 1}, [])\n")
        return Process()
    monkeypatch.setattr(gateway.subprocess,'Popen',popen)
    monkeypatch.setattr(gateway,'docker',lambda *a,**k:None)
    result=gateway.test('python','def solve(*args): return set(args)',{'input':'[]','expected':'({1, 2}, [])','environment':{'COURSE':'Python'}},'',3,execution_mode=mode,entry_function='solve',entry_functions=['solve'],comparison='python-value')
    assert result['passed']
    ast.parse(captured['source'])
    assert '__intdict__' in captured['source']
    assert 'COURSE=Python' in captured['cmd']
    if mode=='python-dispatch':assert "Unknown function" in captured['source']

def test_java_custom_entrypoint_is_quoted_and_named(gateway,monkeypatch):
    class Process:
        returncode=0
        def poll(self):return 0
    def popen(args,**kwargs):
        mount=args[args.index('--mount')+1]
        root=Path(mount.split('src=')[1].split(',')[0])
        assert (root/'Test.java').exists()
        assert "'/work/Test.java'" in args[-1]
        kwargs['stdout'].write(b'ok');return Process()
    monkeypatch.setattr(gateway.subprocess,'Popen',popen)
    monkeypatch.setattr(gateway,'docker',lambda *a,**k:None)
    assert gateway.test('java','public class Test {}',{'expected':'ok'},'',3,entrypoint='Test')['passed']
