"""Automatically import the included real PDF and make reliable questions available."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import create_app
from backend.models import db,User,Paper,IngestionBatch,IngestionFile
from backend.ingestion import store_upload,process_file
from werkzeug.datastructures import FileStorage
app=create_app()
with app.app_context():
    admin=User.query.filter_by(role='ADMIN').first()
    if not admin:raise SystemExit('Create an admin account first; see README.')
    paper=Paper.query.filter(Paper.source_url.contains('1E-MmzBaggBUJMfXifzRTDhNyFaMD2DJ2')).first()
    if not paper:raise SystemExit('Import sample-data/catalog.xlsx first.')
    existing=IngestionFile.query.filter_by(paper_id=paper.id,status='AVAILABLE').first()
    if existing:raise SystemExit(f'Already imported as job {existing.id}; it is available to students.')
    batch=IngestionBatch(user_id=admin.id);db.session.add(batch);db.session.commit()
    with open(Path(__file__).resolve().parents[1]/'sample-data/software-testing-may-2026-quiz1.pdf','rb') as f:
        item=store_upload(FileStorage(stream=f,filename='Software Testing - May 2026 - Quiz 1.pdf',content_type='application/pdf'),paper,batch)
    if item.status=='QUEUED':process_file(item.id)
    print({'paper_id':paper.id,'job_id':item.id,'status':item.status,'extracted':item.extracted,'error':item.error})
