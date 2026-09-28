from scripts import finish_setup

def test_database_failure_never_starts_storage_sync(monkeypatch,tmp_path):
    monkeypatch.setattr(finish_setup,'ROOT',tmp_path);calls=[]
    def run(args,**kwargs):calls.append(args);return 1
    monkeypatch.setattr(finish_setup.subprocess,'call',run)
    assert finish_setup.main()==1
    assert len(calls)==1 and 'scripts/migrate_to_supabase.py' in calls[0]

def test_missing_r2_credentials_remain_pending(monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(finish_setup,'ROOT',tmp_path);calls=[]
    def run(args,**kwargs):calls.append(args);return 0 if len(calls)==1 else 2
    monkeypatch.setattr(finish_setup.subprocess,'call',run)
    assert finish_setup.main()==2
    assert 'scripts/sync_r2.py' in calls[1]
    assert 'DATABASE AND R2 READY' not in capsys.readouterr().out
