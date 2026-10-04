import importlib.util,json,pytest
from pathlib import Path

@pytest.mark.parametrize('provider_status',[200,429])
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
    assert finished[0].get('output')==output if provider_status==200 else finished[0]['error']=='quota'
