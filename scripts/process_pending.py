import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import create_app
from backend.ingestion import work_once
from backend.models import db,IngestionFile
import time
app=create_app()
with app.app_context():
    count=0
    while True:
        if work_once():
            count+=1
            if count%10==0:print('Processed',count,flush=True)
        elif IngestionFile.query.filter(IngestionFile.status.in_(['FETCH_QUEUED','FETCHING'])).first():time.sleep(3)
        else:break
        db.session.remove()
    print('Complete',count,flush=True)
