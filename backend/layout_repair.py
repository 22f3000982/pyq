"""Offline presentation repair. Never acquire catalog PDFs or change grading data."""
import hashlib
from pathlib import Path
import fitz
from flask import current_app
from .models import db,Question,QuestionImage,IngestionFile,Attempt,AttemptAnswer
from .visual_pdf import layout_document
from .automatic_parser import parse_document
from .engine import question_snapshot,question_order

def repair_layouts():
    report=[]
    # Only sources already attached to the current student question bank.
    ids={q.ingestion_file_id for q in Question.query.filter_by(status='AVAILABLE') if q.ingestion_file_id}
    for fid in sorted(ids):
        f=db.session.get(IngestionFile,fid);entry={'file_id':fid,'paper_id':f.paper_id,'filename':f.filename,'updated':0,'skipped':[]}
        try:
            path=Path(current_app.config['UPLOAD_DIR'])/f.path
            data=path.read_bytes()
            with fitz.open(stream=data,filetype='pdf') as doc:
                layout=layout_document(doc,Path(current_app.config['UPLOAD_DIR']),f.file_hash or hashlib.sha256(data).hexdigest(),current_app.config['OCR_ENABLED'])
            records,_,_=parse_document(layout)
            if not records:raise ValueError('No recognized source question boundaries; existing content preserved')
            by_source={r['evidence']['source_question_id']:r for r in records}
            for q in Question.query.filter_by(ingestion_file_id=fid,status='AVAILABLE'):
                r=by_source.get((q.evidence or {}).get('source_question_id'))
                if not r:
                    matches=[r for r in records if r['number']==q.number]
                    r=matches[0] if len(matches)==1 else None
                # Presentation only. A disagreement never changes an existing key/score.
                if not r or r['status']!='AVAILABLE' or r['kind']!=q.kind or {o.key for o in q.options}!={o['key'] for o in r['options']} or r['answers']!=q.answers or r['marks']!=q.marks or r['negative_marks']!=q.negative_marks:
                    entry['skipped'].append(q.number);continue
                q.text=r['text'];values={o['key']:o['text'] for o in r['options']}
                for o in q.options:o.text=values[o.key]
                existing={(i.path,i.option_key):i for i in q.images}
                for asset in r['images']:
                    if (asset['path'],asset.get('option_key')) not in existing:
                        image=QuestionImage(question_id=q.id,path=asset['path'],option_key=asset.get('option_key'),alt='Source diagram or notation',source_page=asset.get('page'))
                        db.session.add(image);q.images.append(image);existing[(asset['path'],asset.get('option_key'))]=image
                q.evidence={**(q.evidence or {}),'layout_assets':r['evidence']['layout_assets'],'layout_version':3}
                payload={k:r.get(k) for k in ('number','kind','text','options','answers','marks','negative_marks')}
                import json
                q.fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                db.session.flush();fresh=question_snapshot(q)
                for item in AttemptAnswer.query.filter_by(question_id=q.id):
                    old=item.snapshot
                    if {o['key'] for o in old.get('options',[])}==set(values) and old.get('answers')==q.answers:
                        item.snapshot={**old,**{k:fresh[k] for k in ('text','options','images')}}
                entry['updated']+=1
            db.session.commit();entry['status']='PARTIAL' if entry['skipped'] else 'COMPLETED'
        except Exception as exc:
            db.session.rollback();entry['updated']=0;entry['status']='FAILED';entry['error']=str(exc)
        report.append(entry)
    # Reorder existing palettes/reviews without changing IDs, responses or timestamps.
    for attempt in Attempt.query:
        for pos,item in enumerate(sorted(attempt.items,key=lambda i:(i.snapshot.get('paper_id',0),question_order(i.snapshot['number']),i.position))):item.position=pos
    db.session.commit()
    return report
