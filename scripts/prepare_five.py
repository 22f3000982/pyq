"""Only the five selected catalog papers; uses the production acquisition/ingestion pipeline."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import create_app
from backend.models import *
from backend.acquisition import download_pending,event
from backend.ingestion import process_file
SELECTED=[13,1,50,54,7]
app=create_app()
with app.app_context():
    for pid in SELECTED:
        f=IngestionFile.query.filter_by(paper_id=pid).order_by(IngestionFile.id.desc()).first()
        if not f:raise RuntimeError('Catalog job missing for '+str(pid))
        if not f.path:
            f.status='FETCH_QUEUED';f.error=None;f.retries+=1;event(f,'SELECTED_DEMO','Selected for five-paper demonstration')
    db.session.commit()
    download_pending(app,workers=3,paper_ids=SELECTED)
    for pid in SELECTED:
        f=IngestionFile.query.filter_by(paper_id=pid).order_by(IngestionFile.id.desc()).first()
        if f.path:process_file(f.id)
        print(pid,f.status,f.error,flush=True)
