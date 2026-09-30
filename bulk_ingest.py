"""Bounded, resumable catalog ingestion.

This command only claims eligible paper records. It never resets completed
imports and isolates acquisition/extraction failures per paper.
"""
import argparse,json,sys,time,os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from backend import create_app
from backend.acquisition import queue_catalog,download_pending
from backend.ingestion import work_once
from backend.models import db,IngestionFile,Paper
from sqlalchemy import func

SUCCESS={'AVAILABLE','PARTIAL','DUPLICATE'}
ACTIVE={'QUEUED','FETCHING','PROCESSING','FETCH_QUEUED'}
FAILURES={'PROCESSING_FAILED','EXTRACTION_FAILED'}

def candidates(limit,retry_failed):
    ids=[]
    latest_ids=db.session.query(func.max(IngestionFile.id)).group_by(IngestionFile.paper_id)
    latest_by_paper={f.paper_id:f for f in IngestionFile.query.filter(IngestionFile.id.in_(latest_ids))}
    for paper in Paper.query.filter(Paper.source_url.isnot(None)).order_by(Paper.id):
        if paper.status in ('AVAILABLE','PARTIALLY_AVAILABLE','ARCHIVED') or paper.canonical_paper_id:continue
        latest=latest_by_paper.get(paper.id)
        if retry_failed and (not latest or latest.status not in FAILURES):continue
        if latest and latest.status in SUCCESS|ACTIVE:continue
        if latest and latest.status in FAILURES and not retry_failed:continue
        if latest and latest.status=='PAUSED':continue
        ids.append(paper.id)
        if len(ids)>=limit:break
    return ids

def main():
    parser=argparse.ArgumentParser(description='Process a bounded batch of new catalog papers.')
    parser.add_argument('--limit',type=int,default=20)
    parser.add_argument('--retry-failed',action='store_true',help='Select only failed papers; do not include new catalog entries')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--enqueue',action='store_true',help='Queue only; background worker handles acquisition/extraction')
    args=parser.parse_args()
    if args.limit<1:parser.error('--limit must be positive')
    app=create_app()
    with app.app_context():
        ids=candidates(args.limit,args.retry_failed)
        if args.dry_run:
            rows=[{'id':p.id,'name':p.name,'status':p.status} for p in Paper.query.filter(Paper.id.in_(ids)).order_by(Paper.id)] if ids else []
            print(json.dumps({'dry_run':True,'limit':args.limit,'retry_failed':args.retry_failed,'papers':rows},indent=2))
            return 0
        if not ids:
            print(json.dumps({'processed':0,'message':'No eligible papers.'}));return 0
        batch,count=queue_catalog(retry=args.retry_failed,limit=args.limit,paper_ids=ids)
        if args.enqueue or os.getenv('CELERY_BROKER_URL'):
            print(json.dumps({'batch_id':batch,'queued_papers':count,'paper_ids':ids,'status':'QUEUED'}));return 0
        download_pending(app,workers=4,paper_ids=ids)
        processed=0
        while work_once(paper_ids=ids):
            processed+=1
            db.session.remove()
        print(json.dumps({'batch_id':batch,'queued_papers':count,'processed_files':processed,'paper_ids':ids},indent=2))
        return 0

if __name__=='__main__':raise SystemExit(main())
