import os,sys
import pytest
from backend.setup_runner import run_checked


def test_live_output_redacts_and_stops_on_failure(tmp_path,capsys):
    log=tmp_path/'test.txt'
    with pytest.raises(RuntimeError,match='failed'):
        run_checked([sys.executable,'-c',"print('secret-token-123');raise SystemExit(2)"],tmp_path,os.environ.copy(),'test',log,['secret-token-123'])
    assert 'secret-token-123' not in log.read_text()
    assert '[REDACTED]' in log.read_text()
    assert 'secret-token-123' not in capsys.readouterr().out


def test_live_output_timeout_keeps_partial_output(tmp_path):
    log=tmp_path/'test.txt'
    with pytest.raises(RuntimeError,match='exceeded'):
        run_checked([sys.executable,'-u','-c',"import time;print('started');time.sleep(20)"],tmp_path,os.environ.copy(),'test',log,timeout=1,heartbeat=.2)
    assert 'started' in log.read_text()
    assert 'still running' in log.read_text()
