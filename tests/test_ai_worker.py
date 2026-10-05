import importlib.util,json,pytest
from pathlib import Path

@pytest.mark.parametrize('provider_status',[200,429,400,403,503])
def test_local_worker_sends_images_and_reports_output_without_key_to_site(monkeypatch,provider_status):
    spec=importlib.util.spec_from_file_location('ai_worker',Path(__file__).parents[1]/'tools/ai-worker/worker.py');worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    for key,value in {'PYQ_SITE_URL':'https://example.test','GEMINI_API_KEY':'test-secret','GEMINI_MODEL':'fake-model','GEMINI_FREE_TIER_CONFIRMED':'yes','PYQ_ADMIN_EMAIL':'admin@example.test'}.items():monkeypatch.setenv(key,value)
    monkeypatch.setattr(worker.getpass,'getpass',lambda _: 'password')
    output={'final_answer':['A'],'explanation':'One is correct.','option_explanations':{'A':'Correct','B':'Incorrect'},'needs_review':False}
    class Response:
        headers={'Content-Type':'image/png'};content=b'fake-image';status_code=200
        def __init__(self,data,status=200):self.data=data;self.status_code=status
        def raise_for_status(self):pass
        def json(self):return self.data
    job={'id':1,'token':'lease','question':{'id':1,'text':'Question','images':[{'url':'/api/images/1?proxy=1','id':1}]}}
    finished=[];gemini=[]
    class Session:
        def get(self,url,**kwargs):
            if url.endswith('/session'):return Response({'csrf':'token'})
            assert url=='https://example.test/api/images/1?proxy=1';return Response({})
        def request(self,method,url,**kwargs):
            assert 'test-secret' not in str(kwargs)
            if url.endswith('/auth/login'):return Response({'csrf':'new-token'})
            if url.endswith('/claim'):return Response({'job':job})
            assert url.endswith('/1/finish');finished.append(kwargs['json']);return Response({'status':'DONE'})
    def post(url,**kwargs):
        assert url.endswith('/fake-model:generateContent');gemini.append(kwargs)
        return Response({'candidates':[{'content':{'parts':[{'text':json.dumps(output)}]}}]},provider_status)
    monkeypatch.setattr(worker.requests,'Session',Session);monkeypatch.setattr(worker.requests,'post',post)
    monkeypatch.setattr(worker.time,'sleep',lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):worker.main()
    assert gemini[0]['headers']['x-goog-api-key']=='test-secret'
    assert 'inlineData' in gemini[0]['json']['contents'][0]['parts'][1]
    assert '/api/images/' not in gemini[0]['json']['contents'][0]['parts'][0]['text']
    if provider_status==200:assert finished[0]['output']==output
    else:
        assert finished[0]['error']=={429:'quota',400:'config',403:'auth',503:'network'}[provider_status]
        assert finished[0]['error_detail']=='gemini_request HTTP '+str(provider_status)
        assert 'test-secret' not in finished[0]['error_detail']

def load_providers():
    spec=importlib.util.spec_from_file_location('worker_providers',Path(__file__).parents[1]/'tools/ai-worker/providers.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def configure_multi(monkeypatch):
    for key,value in {'AI_PROVIDER_ORDER':'groq,gemini,antigravity,openrouter','GROQ_API_KEY':'groq-secret','GROQ_FREE_TIER_CONFIRMED':'yes','GEMINI_API_KEY':'google-secret','GEMINI_MODEL':'fake','GEMINI_FREE_TIER_CONFIRMED':'yes','ANTIGRAVITY_ENABLED':'yes','OPENROUTER_API_KEY':'router-secret','OPENROUTER_MODEL':'openrouter/free'}.items():monkeypatch.setenv(key,value)

@pytest.mark.parametrize('status',[429,503,401,400])
def test_multi_fallback_and_cooldown(monkeypatch,status):
    m=load_providers();configure_multi(monkeypatch);pool=m.Providers({});calls=[]
    def request(provider,*args):
        calls.append(provider)
        if provider=='groq':
            response=type('Response',(),{'status_code':status})()
            m.checked_response(response,provider)
        return {'explanation':'Saved'}
    monkeypatch.setattr(pool,'request',request)
    assert pool.generate([{'text':'question'}])['provider']=='gemini'
    assert calls==['groq','gemini']
    calls.clear();pool.generate([{'text':'question'}]);assert calls==['gemini']

def test_all_providers_unavailable_preserves_job(monkeypatch):
    m=load_providers();configure_multi(monkeypatch);pool=m.Providers({})
    monkeypatch.setattr(pool,'request',lambda *args:(_ for _ in ()).throw(m.ProviderFailure('quota','HTTP 429')))
    with pytest.raises(m.ProviderFailure) as e:pool.generate([{'text':'question'}])
    assert e.value.code=='quota'

def test_images_not_dropped_when_groq_limit_exceeded(monkeypatch):
    m=load_providers();configure_multi(monkeypatch);pool=m.Providers({});seen=[]
    monkeypatch.setattr(pool,'request',lambda provider,key,model,parts,budget:seen.append((provider,len(parts))) or {})
    parts=[{'text':'question'}]+[{'inlineData':{'mimeType':'image/png','data':'abc'}}]*4
    assert pool.generate(parts)['provider']=='gemini';assert seen==[('gemini',5)]

def test_paid_router_model_rejected(monkeypatch):
    m=load_providers();configure_multi(monkeypatch);monkeypatch.setenv('OPENROUTER_MODEL','paid/model')
    with pytest.raises(SystemExit):m.Providers({})

@pytest.mark.parametrize('provider',['groq','openrouter','antigravity'])
def test_adapter_payload_and_json(monkeypatch,provider):
    m=load_providers();configure_multi(monkeypatch);pool=m.Providers({});seen=[]
    output={'final_answer':['A'],'explanation':'Correct','option_explanations':{'A':'Correct'},'needs_review':False}
    class Response:
        status_code=200
        def json(self):return {'status':'completed','outputs':[{'type':'text','text':json.dumps(output)}]} if provider=='antigravity' else {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(output)}}]}
    monkeypatch.setattr(m.requests,'post',lambda url,**kw:seen.append((url,kw)) or Response())
    assert pool.request(provider,'secret','openrouter/free' if provider=='openrouter' else 'model',[{'text':'question'},{'inlineData':{'mimeType':'image/png','data':'abc'}}],30)==output
    body=seen[0][1]['json'];assert 'secret' not in str(body)
    if provider=='openrouter':assert body['provider']['max_price']=={'prompt':0,'completion':0}
    if provider=='antigravity':assert body['input'][1]['data']=='abc' and body['tools']==[]
    else:assert body['messages'][0]['content'][1]['image_url']['url']=='data:image/png;base64,abc'

def test_invalid_or_truncated_output_falls_back(monkeypatch):
    m=load_providers();configure_multi(monkeypatch);pool=m.Providers({})
    def request(provider,*args):
        if provider=='groq':raise ValueError('Invalid JSON')
        return {'explanation':'Next provider'}
    monkeypatch.setattr(pool,'request',request)
    assert pool.generate([{'text':'question'}])['provider']=='gemini'
