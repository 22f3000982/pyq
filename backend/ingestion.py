"""Automatic, resumable acquisition -> extraction -> validation -> availability."""
import hashlib,time,uuid,json,re
from pathlib import Path
import fitz
from flask import current_app
from sqlalchemy import update
from .models import *
from .acquisition import event,matching_import
from .visual_pdf import layout_document
from .automatic_parser import parse_document,clean_assets
from .providers import provider,segment_plain
from .storage import write_asset,ensure_local,publish,StorageError

SUCCESS=('AVAILABLE','PARTIAL','DUPLICATE')
FAILURES=('PROCESSING_FAILED','EXTRACTION_FAILED')
def root():return Path(current_app.config['UPLOAD_DIR']).resolve()
def validate_pdf(data):
    if not data.startswith(b'%PDF-'):raise ValueError('Not a PDF: invalid signature')
    if len(data)>current_app.config['MAX_UPLOAD_SIZE']:raise ValueError('PDF exceeds configured byte limit')
    with fitz.open(stream=data,filetype='pdf') as doc:
        if doc.needs_pass:raise ValueError('Encrypted PDF requires credentials; no bypass attempted')
        if not 1<=len(doc)<=200:raise ValueError('PDF must have 1–200 pages')
        if any(p.rect.width>3000 or p.rect.height>3000 for p in doc):raise ValueError('Page dimensions exceed rendering limit')
        return len(doc)

def store_upload(upload,paper,batch,replace=False):
    f=IngestionFile(batch_id=batch.id,paper_id=paper.id,filename=(upload.filename or 'upload.pdf')[:255],source_url=paper.source_url)
    db.session.add(f);db.session.flush()
    try:
        if upload.mimetype not in ('application/pdf','application/octet-stream'):raise ValueError('Only PDF uploads are accepted')
        data=upload.read(current_app.config['MAX_UPLOAD_SIZE']+1);f.pages=validate_pdf(data);sha=hashlib.sha256(data).hexdigest()
        stored,old=matching_import(sha,paper.course_id,f.id)
        if old:
            write_asset(old.path or (sha+'.pdf'),data)
            old.path=old.path or (sha+'.pdf')
            f.duplicate_of_id=old.id;f.path=old.path
            if old.paper_id!=paper.id:
                f.status='DUPLICATE';f.finished_at=time.time()
                paper.canonical_paper_id=old.paper_id
                event(f,'DEDUPLICATED',f'Identical file already stored as import {old.id}; question records are reused')
            elif replace:
                f.status='QUEUED';paper.status='PROCESSING';paper.canonical_paper_id=None
                event(f,'REPLACED',f'Identical source explicitly queued for reprocessing; SHA-256 {sha}')
            else:
                f.status='DUPLICATE';f.finished_at=time.time()
                event(f,'DEDUPLICATED',f'Identical file already imported for this paper as import {old.id}; no reprocessing needed')
            if old.status in FAILURES:old.status='QUEUED';old.error=None;old.retries+=1;paper.status='PROCESSING'
        else:
            f.file_hash=None if stored else sha;f.path=sha+'.pdf';write_asset(f.path,data);f.status='QUEUED';paper.status='PROCESSING';paper.canonical_paper_id=None
            event(f,'UPLOADED',f'{len(data)} bytes; SHA-256 {sha}')
    except Exception as e:
        f.status='PROCESSING_FAILED';f.error=str(e)[:1500];f.finished_at=time.time();event(f,'UPLOAD_FAILED',f.error)
        if not Question.query.filter_by(paper_id=paper.id,status='AVAILABLE').count():paper.status='PROCESSING_FAILED'
    db.session.commit();return f

def update_batch(id):
    b=db.session.get(IngestionBatch,id);states=[f.status for f in IngestionFile.query.filter_by(batch_id=id)]
    if any(s in ('QUEUED','FETCH_QUEUED','FETCHING','PROCESSING') for s in states):b.status='PROCESSING'
    elif states and all(s in FAILURES for s in states):b.status='FAILED'
    elif any(s in FAILURES or s=='PARTIAL' for s in states):b.status='PARTIALLY_COMPLETED'
    else:b.status='COMPLETED'
    db.session.commit()

def fallback(layout,config):
    text=layout['text'];llm=provider(config);records=[];issues=[]
    # Keep the complete text across page boundaries for deterministic segmentation.
    # LLM chunks overlap so a question near a chunk boundary can be deduplicated.
    chunks=[text[i:i+20000] for i in range(0,len(text),18000)] if llm else [text]
    for chunk in chunks:
        try:parsed=llm.extract(chunk) if llm else segment_plain(chunk)
        except Exception as e:issues.append({'stage':'provider','error':str(e)[:500]});continue
        for item in parsed:
            q=item.model_dump();offset=text.find(item.text[:80]);pages=[pn for start,stop,pn in layout['pages'] if start<=max(offset,0)<=stop]
            # Bind evidence to this question, never another key elsewhere in the chunk.
            boundaries=list(re.finditer(r'(?im)^\s*(?:Q(?:uestion)?\s*)?(\d{1,3})[.) :]\s*(?=\S)',chunk))
            local=''
            for n,b in enumerate(boundaries):
                if b[1]==q['number']:
                    local=chunk[b.end():boundaries[n+1].start() if n+1<len(boundaries) else len(chunk)];break
            q['evidence']={'method':'structured_model' if llm else 'numbered_text','answer_source':None}
            explicit=re.search(r'(?im)^\s*(?:Correct Answer|Answer|Ans)\s*[:=]\s*(.+)',local)
            value=explicit[1].strip() if explicit else ''
            q['answers']=None
            if q['kind']=='NAT' and value:
                from .numeric import parse_numeric_key
                try:q['answers']=parse_numeric_key(value)
                except ValueError:pass
            elif value:
                keys=re.split(r'\s*[,;&]\s*',value)
                if set(keys)<={o['key'] for o in q['options']}:q['answers']=keys
            if q['answers'] is not None:q['evidence']['answer_source']='explicit_local_key'
            # Preserve only literal source marks; model predictions cannot establish grading.
            mark=re.search(r'(?i)\[\s*(\d+(?:\.\d+)?)\s*marks?\s*\]|(?:Correct Marks|Marks)\s*:\s*(\d+(?:\.\d+)?)',local)
            negative=re.search(r'(?i)(?:Negative|Wrong) Marks\s*:\s*(\d+(?:\.\d+)?)',local)
            q['marks']=float(mark[1] or mark[2]) if mark else None
            q['negative_marks']=float(negative[1]) if negative else None
            q['explanation']=None
            q['source_pages']=pages;q['images']=[];q['status']='AVAILABLE';q['warnings']=[]
            if q['kind'] in ('MCQ','MSQ','TRUE_FALSE') and len(q['options'])<2:q['status']='EXTRACTION_FAILED';q['warnings'].append('MISSING_OPTIONS')
            if q['kind']=='SUBJECTIVE' and not re.search(r'(?im)^\s*Q(?:uestion)?\s*'+re.escape(q['number'])+r'\b',chunk):q['status']='EXTRACTION_FAILED';q['warnings'].append('UNCERTAIN_BOUNDARY')
            if re.search(r'\[\[IMAGE:',q['text']) or any('[[IMAGE:' in o['text'] for o in q['options']):
                q['text'],q['images']=clean_assets(q['text'],layout)
                for o in q['options']:
                    o['text'],imgs=clean_assets(o['text'],layout,o['key']);q['images'].extend(imgs)
            if '[[PAGE_FAILED:' in local:q['status']='EXTRACTION_FAILED';q['warnings'].append('SOURCE_PAGE_EXTRACTION_FAILED')
            q['evidence']['layout_assets']={Path(a['path']).stem:{k:a[k] for k in ('inline','width','height') if k in a} for a in q['images']}
            from .text_format import source_bold
            q['text']=source_bold(q['text'],layout)
            for o in q['options']:o['text']=source_bold(o['text'],layout)
            records.append(q)
    return records,issues

def extraction_failure_message(layout,records,available):
    if available:return None
    text=re.sub(r'\[\[(?:IMAGE|PAGE_FAILED):[^]]+\]\]','',layout['text']).strip()
    if records:
        return f'{len(records)} question records detected, but none passed automatic validation. Check extraction warnings for missing stems/options or failed source pages.'
    if text:
        return f'PDF text extracted ({len(text)} characters), but question boundaries were not recognized. This is a question-format/parser issue; the PDF is not classified as image-only. Check extraction warnings and source layout.'
    return 'No readable PDF text was recovered. Check page extraction warnings; scanned pages need working OCR.'

def process_file(id):
    f=db.session.get(IngestionFile,id);paper=db.session.get(Paper,f.paper_id);f.status='PROCESSING';f.started_at=time.time();paper.status='PROCESSING';event(f,'PROCESSING','Automatic extraction started');db.session.commit()
    try:
        data=ensure_local(f.path).read_bytes();f.pages=validate_pdf(data)
        with fitz.open(stream=data,filetype='pdf') as doc:layout=layout_document(doc,root(),(f.file_hash or hashlib.sha256(data).hexdigest()),current_app.config['OCR_ENABLED'])
        event(f,'DETECTING_ANSWERS','PDF layout, images and green/red visual indicators extracted');db.session.commit()
        records,meta,issues=parse_document(layout)
        if not records:
            records,extra=fallback(layout,current_app.config);issues.extend(extra)
        publish(f.path)
        # Never mark a paper available until every referenced question image is
        # present and readable in durable storage. This closes the gap where the
        # database could outlive an ephemeral worker file.
        for name in sorted({image['path'] for item in records for image in item.get('images',[])}):publish(name,verify=True)
        event(f,'EXTRACTED',f'{len(records)} question records; {len(layout["assets"])} content images');db.session.commit()
        issues.extend({'number':i.get('number'),'status':i.get('status'),'warnings':i.get('warnings',[])} for i in records if i.get('status')=='EXTRACTION_FAILED')
        effective_id=paper.canonical_paper_id or paper.id
        prior_available=Question.query.filter_by(paper_id=effective_id,status='AVAILABLE').count()
        content_savepoint=db.session.begin_nested()
        new_ids=[];seen=set();available=0;failed=0
        for item in records:
            try:
                with db.session.begin_nested():
                    payload={k:item.get(k) for k in ('number','kind','text','options','answers','marks','negative_marks')}
                    # The question fingerprint avoids duplicates across same-file retries and repeated extraction.
                    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                    if fingerprint in seen:continue
                    seen.add(fingerprint)
                    q=Question.query.filter_by(paper_id=paper.id,fingerprint=fingerprint).first()
                    if not q:
                        matches=Question.query.filter(Question.paper_id==paper.id,Question.number==str(item['number']),Question.status!='SUPERSEDED').all()
                        if len(matches)==1:q=matches[0]
                    if q and (q.evidence or {}).get('_admin_locked'):
                        new_ids.append(q.id);available+=q.status=='AVAILABLE'
                        continue
                    if q and q.fingerprint==fingerprint:
                        q.status=item.get('status','EXTRACTION_FAILED');q.evidence={**item.get('evidence',{}),**({'_active_image_ids':q.evidence['_active_image_ids']} if '_active_image_ids' in (q.evidence or {}) else {})};q.warnings=item.get('warnings',[]);q.confidence=item.get('confidence',.5)
                        new_ids.append(q.id);available+=q.status=='AVAILABLE';failed+=q.status=='EXTRACTION_FAILED';continue
                    if not q:
                        # Preserve identity when automatically upgrading the earlier parser's rows.
                        q=Question.query.filter_by(paper_id=paper.id,ingestion_file_id=f.id,number=item['number'],fingerprint=None).first()
                    if not q:q=Question(paper_id=paper.id,number=item['number'],kind=item['kind'],text=item['text']);db.session.add(q)
                    q.fingerprint=fingerprint;q.ingestion_file_id=f.id;q.number=item['number'];q.kind=item['kind'];q.text=item['text'];q.answers=item.get('answers');q.answer_status='ANSWER_AVAILABLE' if item.get('answers') is not None else 'ANSWER_UNAVAILABLE'
                    q.marks=item.get('marks');q.negative_marks=item.get('negative_marks');q.explanation=item.get('explanation');q.topic=item.get('topic');q.source_pages=item.get('source_pages') or [1];q.source_page=q.source_pages[0];q.evidence=item.get('evidence',{});q.warnings=item.get('warnings',[]);q.status=item.get('status','EXTRACTION_FAILED');q.confidence=item.get('confidence',.5)
                    # Replace normalized children safely; previous attempts already hold snapshots.
                    q.options=[];db.session.flush()
                    q.options=[QuestionOption(key=o['key'],text=o['text'],position=n) for n,o in enumerate(item['options'])]
                    new_images=[QuestionImage(path=a['path'],alt='Source diagram or notation',option_key=a.get('option_key'),source_page=a.get('page')) for a in item.get('images',[])]
                    q.images.extend(new_images)
                    db.session.flush();q.evidence={**(q.evidence or {}),'_active_image_ids':[i.id for i in new_images]};new_ids.append(q.id)
                    if q.status=='AVAILABLE':available+=1
                    if q.status=='EXTRACTION_FAILED':failed+=1
            except Exception as e:
                failed+=1;issues.append({'number':item.get('number'),'error':str(e)[:500]})
        if prior_available and (not available or failed or any(i.get('status')=='EXTRACTION_FAILED' for i in records)):
            content_savepoint.rollback()
            raise ValueError('Replacement extraction did not fully validate. Existing available questions were preserved.')
        if available and not failed:
            paper.canonical_paper_id=None
        content_savepoint.commit()
        # Retire superseded current-bank records, never historical attempt snapshots.
        if new_ids:
            for old in Question.query.filter(Question.paper_id==paper.id,Question.id.notin_(new_ids)):
                if (old.evidence or {}).get('_admin_locked'):
                    available+=old.status=='AVAILABLE';issues.append({'number':old.number,'check':'unmatched_admin_override','message':'Preserved admin correction/hide; review source numbering.'})
                else:old.status='SUPERSEDED'
        event(f,'VALIDATING','Checking numbering, marks, source keys and question structure');db.session.commit()
        numeric_numbers=[int(q['number']) for q in records if str(q['number']).isdigit()]
        if numeric_numbers:
            gaps=sorted(set(range(min(numeric_numbers),max(numeric_numbers)+1))-set(numeric_numbers))
            if gaps:issues.append({'check':'numbering','missing':gaps})
        if meta.get('declared_total_questions') is not None and meta['declared_total_questions']!=len(records):issues.append({'check':'question_count','source':meta['declared_total_questions'],'extracted_records':len(records),'available':available})
        mark_sum=sum(q.get('marks') or 0 for q in records)
        if meta.get('declared_total_marks') is not None and abs(meta['declared_total_marks']-mark_sum)>1e-6:issues.append({'check':'total_marks','source':meta['declared_total_marks'],'extracted_sum':mark_sum})
        meta.update(extracted_records=len(records),available_questions=available,extracted_marks_sum=mark_sum,discrepancies=issues,
                    question_assets_verified_r2=current_app.config.get('STORAGE_BACKEND')=='r2')
        archived_from=(paper.source_metadata or {}).get('_admin_archived_from')
        if archived_from:meta['_admin_archived_from']=archived_from
        paper.source_metadata=meta
        if meta.get('duration_seconds'):paper.duration_seconds=meta['duration_seconds']
        f.extracted=len(new_ids);f.warnings=layout['warnings']+issues;f.finished_at=time.time();f.error=extraction_failure_message(layout,records,available)
        f.status='PARTIAL' if available and failed else 'AVAILABLE' if available else 'EXTRACTION_FAILED'
        db.session.expire(paper,['status'])
        if paper.status!='ARCHIVED':
            paper.status='PARTIALLY_AVAILABLE' if available and failed else 'AVAILABLE' if available else 'EXTRACTION_FAILED'
        event(f,'AUTOMATIC_VALIDATION',{'available':available,'failed_questions':failed,'issues':issues});event(f,f.status,'Student question bank updated automatically')
        db.session.commit()
    except Exception as e:
        try:
            db.session.rollback();f=db.session.get(IngestionFile,id);paper=db.session.get(Paper,f.paper_id)
            f.status='EXTRACTION_FAILED';f.error=f'{type(e).__name__}: {str(e)[:1200]}';f.finished_at=time.time()
            if 'issues' in locals():f.warnings=layout.get('warnings',[])+issues
            if paper.status!='ARCHIVED':
                effective_id=paper.canonical_paper_id or paper.id
                existing=Question.query.filter_by(paper_id=effective_id,status='AVAILABLE').count()
                failed_existing=Question.query.filter_by(paper_id=effective_id,status='EXTRACTION_FAILED').count()
                paper.status=('PARTIALLY_AVAILABLE' if failed_existing else 'AVAILABLE') if existing else 'EXTRACTION_FAILED'
            event(f,'EXTRACTION_FAILED',f.error);db.session.commit()
        except Exception:
            db.session.remove();current_app.logger.error('ingestion_persistence_failed type=%s',type(e).__name__)
    # Aliases share question records instead of inventing independent papers for one PDF.
    for alias in Paper.query.filter_by(canonical_paper_id=paper.id):
        if alias.status!='ARCHIVED':alias.status=paper.status
        alias.source_metadata=paper.source_metadata;alias.duration_seconds=paper.duration_seconds
    db.session.commit();update_batch(f.batch_id)

def repair_question_image_asset(image):
    """Recreate one missing extracted image deterministically from its source PDF."""
    question=db.session.get(Question,image.question_id)
    if question is None or not question.ingestion_file_id:return False
    source=db.session.get(IngestionFile,question.ingestion_file_id)
    if source is None or not source.path or not source.file_hash:return False
    try:
        data=ensure_local(source.path).read_bytes()
        with fitz.open(stream=data,filetype='pdf') as doc:
            layout=layout_document(doc,root(),source.file_hash,False)
        generated={asset['path'] for asset in layout.get('assets',{}).values()}
        if image.path not in generated or not (root()/image.path).is_file():return False
        publish(image.path,verify=True)
        current_app.logger.warning('question_image_repaired image_id=%s paper_id=%s',image.id,question.paper_id)
        return True
    except Exception as exc:
        current_app.logger.error('question_image_repair_failed image_id=%s type=%s',image.id,type(exc).__name__)
        return False

def process_one(file_id):
    """Atomically process one downloaded ingestion record by id."""
    from .engine import expire_all
    expire_all()
    record=db.session.get(IngestionFile,file_id)
    if record is None:return False
    if record.status!='QUEUED':return record.status in SUCCESS
    changed=db.session.execute(update(IngestionFile).where(
        IngestionFile.id==file_id,IngestionFile.status=='QUEUED'
    ).values(status='PROCESSING',started_at=time.time(),error=None)).rowcount
    db.session.commit()
    if not changed:return False
    process_file(file_id)
    return True

def work_once(paper_ids=None):
    from .engine import expire_all
    expire_all()
    for stale in IngestionFile.query.filter(IngestionFile.status=='PROCESSING',IngestionFile.started_at<time.time()-1800):
        stale.status='EXTRACTION_FAILED';stale.error='Worker lease expired; automatic retry is safe';event(stale,'LEASE_EXPIRED',stale.error)
    db.session.commit()
    candidate_query=IngestionFile.query.join(Paper,Paper.id==IngestionFile.paper_id).filter(IngestionFile.status=='QUEUED',Paper.status!='ARCHIVED')
    if paper_ids is not None:candidate_query=candidate_query.filter(IngestionFile.paper_id.in_(paper_ids))
    candidate=candidate_query.order_by(IngestionFile.id).first()
    if not candidate:return False
    id=candidate.id;changed=db.session.execute(update(IngestionFile).where(IngestionFile.id==id,IngestionFile.status=='QUEUED').values(status='PROCESSING',started_at=time.time())).rowcount;db.session.commit()
    if changed:process_file(id)
    return bool(changed)

def worker_loop(once=False):
    while True:
        try:
            worked=work_once()
            # Process uploaded bytes before acquiring catalog URLs. Catalog work is
            # deliberately bounded so a large backlog cannot starve user uploads.
            if not worked and IngestionFile.query.filter_by(status='FETCH_QUEUED').first():
                from .acquisition import download_pending
                download_pending(current_app._get_current_object(),workers=1,limit=1)
                worked=work_once()
        except Exception as exc:
            db.session.remove();current_app.logger.error('worker_tick_failed type=%s',type(exc).__name__);worked=False
        if once:return
        db.session.remove()
        if not worked:time.sleep(2)
