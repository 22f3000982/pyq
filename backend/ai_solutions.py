"""Explicit admin queue and saved text delivery; never invoke an LLM on Render."""
import hashlib,json,secrets,time
from flask import Blueprint,jsonify,request,abort
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from .models import db,Question,Paper,AISolution,SolutionBatch,SolutionJob,Attempt,AttemptAnswer
from .api import require_user,require_visitor,body,integer_argument
from .engine import question_snapshot,grade
from .exam_api import owned,question_with_image_urls,prepare_image_paths,use_paper_image_delivery
bp=Blueprint('ai_solutions',__name__,url_prefix='/api')
PROMPT_VERSION='v1'

def version(s):
    fields={k:s.get(k) for k in ('text','passage','kind','options','answers','answer_status','tolerance','source_pages')}
    fields['text']=' '.join(((s.get('passage') or '')+' '+(s.get('text') or '')).split())
    fields.pop('passage',None)
    fields['images']=[{k:i.get(k) for k in ('id','_asset_path','option_key','token')} for i in s.get('images',[])]
    return hashlib.sha256(json.dumps(fields,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def snapshot(q):return question_snapshot(q)

def solution_json(s,q):
    stale=s.version!=version(snapshot(q))
    return dict(id=s.id,question_id=q.id,number=q.number,status='OUTDATED' if stale else s.status,text=s.text,final_answer=s.final_answer,checks=s.checks,model=s.model,prompt_version=s.prompt_version)

def checked_output(s,data):
    if not isinstance(data,dict):raise ValueError('Expected structured solution')
    text=data.get('explanation');opts=data.get('option_explanations',{})
    if not isinstance(text,str) or not 1<=len(text.strip())<=8000:raise ValueError('Explanation must contain 1–8000 characters')
    if not isinstance(opts,dict) or any(not isinstance(v,str) or not v.strip() or len(v)>1200 for v in opts.values()):raise ValueError('Invalid option explanations')
    choices=s['kind'] in ('MCQ','MSQ','TRUE_FALSE')
    keys=[o['key'] for o in s['options']]
    if choices and set(opts)!=set(keys):raise ValueError('Explain every source option using its exact key')
    final=data.get('final_answer');answer=final
    if choices and (not isinstance(final,list) or not final or any(not isinstance(k,str) for k in final) or len(set(final))!=len(final) or not set(final)<=set(keys)):raise ValueError('Invalid final option keys')
    if not choices and not isinstance(final,str):raise ValueError('Final answer must be text')
    failures=[]
    if data.get('needs_review') is not False:failures.append('AI flagged an inconsistency')
    if s.get('answer_status')!='ANSWER_AVAILABLE' or s.get('answers') is None:failures.append('Source answer key unavailable')
    else:
        try:
            probe={**s,'marks':1,'negative_marks':0}
            if grade(probe,answer)['outcome']!='CORRECT':failures.append('Final answer does not match source key')
        except (TypeError,ValueError,KeyError):failures.append('Final answer could not be checked')
    if any(x in text.lower() for x in ('i cannot solve','as an ai language model')):failures.append('Non-solution response')
    if '<' in text and ('<script' in text.lower() or '<img' in text.lower()):raise ValueError('Only plain text and LaTeX allowed')
    for left,right in ((r'\(',r'\)'),(r'\[',r'\]')):
        if text.count(left)!=text.count(right):failures.append('Unbalanced maths delimiters')
    combined=text.strip()
    if choices:
        combined+='\n\n'+'\n'.join(f"{chr(65+n)}: {opts[o['key']].strip()}" for n,o in enumerate(s['options']))
    if len(combined)>14000:raise ValueError('Solution too long')
    return combined,final,failures

@bp.get('/admin/ai-solutions/summary')
@require_user(True)
def solution_summary():
    # Only processed, non-archived papers with available questions count.
    counts=db.session.query(Question.paper_id.label('paper_id'),func.count(Question.id).label('total')).filter(Question.status=='AVAILABLE').group_by(Question.paper_id).subquery()
    query=db.session.query(Paper,counts.c.total).join(counts,counts.c.paper_id==Paper.id).filter(Paper.status!='ARCHIVED')
    for field,col in [('course_id',Paper.course_id),('exam_type_id',Paper.exam_type_id)]:
        if request.args.get(field):query=query.filter(col==integer_argument(field))
    records=query.options(selectinload(Paper.term),selectinload(Paper.exam_type),selectinload(Paper.course)).order_by(Paper.id.desc()).all()
    papers={p.id:dict(id=p.id,name=p.name,course=p.course.name,term=p.term.name,exam=p.exam_type.name,exam_type_id=p.exam_type_id,session=p.session or '',questions=total,uploaded=0,published=0,review=0,outdated=0) for p,total in records}
    if papers:
        rows=db.session.query(Question,AISolution).join(AISolution,AISolution.question_id==Question.id).filter(Question.status=='AVAILABLE',Question.paper_id.in_(papers)).options(selectinload(Question.options),selectinload(Question.images)).all()
        for q,s in rows:
            p=papers[q.paper_id]
            if s.version!=version(snapshot(q)):
                p['outdated']+=1
                continue
            p['uploaded']+=1
            if s.status=='PUBLISHED':p['published']+=1
            else:p['review']+=1
    values=list(papers.values())
    for p in values:
        p['missing']=p['questions']-p['uploaded']
        p['availability']='complete' if p['published']==p['questions'] else 'partial' if p['published'] else 'none'
        p['upload_state']='complete' if p['uploaded']==p['questions'] else 'partial' if p['uploaded'] else 'none'
    totals=dict(papers_total=len(values),papers_complete=sum(p['uploaded']==p['questions'] for p in values),papers_published=sum(p['published']==p['questions'] for p in values),papers_not_started=sum(p['uploaded']==0 for p in values),questions_total=sum(p['questions'] for p in values),questions_uploaded=sum(p['uploaded'] for p in values),questions_published=sum(p['published'] for p in values),questions_review=sum(p['review'] for p in values),questions_outdated=sum(p['outdated'] for p in values))
    totals['papers_without_published']=sum(p['published']==0 for p in values)
    totals['papers_partial_published']=sum(0<p['published']<p['questions'] for p in values)
    totals['papers_pending']=totals['papers_total']-totals['papers_complete']
    totals['papers_partial']=totals['papers_pending']-totals['papers_not_started']
    totals['questions_pending']=totals['questions_total']-totals['questions_uploaded']
    return jsonify(papers=values,statistics=totals)

@bp.get('/admin/ai-solutions')
@require_user(True)
def dashboard():
    query=Question.query.join(Paper).filter(Question.status=='AVAILABLE',Paper.status!='ARCHIVED')
    for field,col in [('paper_id',Question.paper_id),('course_id',Paper.course_id),('term_id',Paper.term_id),('exam_type_id',Paper.exam_type_id)]:
        if request.args.get(field):query=query.filter(col==integer_argument(field))
    if request.args.get('kind'):query=query.filter(Question.kind==request.args['kind'])
    status=request.args.get('solution_status')
    if status:
        existing=db.session.query(AISolution.question_id)
        query=query.filter(~Question.id.in_(existing)) if status=='NOT_GENERATED' else query.filter(Question.id.in_(existing.filter(AISolution.status==status)))
    page=max(1,integer_argument('page')) if request.args.get('page') else 1
    rows=query.order_by(Question.id).offset((page-1)*24).limit(24).all();ids=[q.id for q in rows]
    solutions={s.question_id:s for s in AISolution.query.filter(AISolution.question_id.in_(ids))}
    jobs={j.question_id:j for j in SolutionJob.query.filter(SolutionJob.question_id.in_(ids))}
    items=[]
    for q in rows:
        sol=solutions.get(q.id);job=jobs.get(q.id)
        item={'question_id':q.id,'paper_id':q.paper_id,'number':q.number,'kind':q.kind,'question':question_with_image_urls(snapshot(q)),'solution':solution_json(sol,q) if sol else None,'job':{'status':job.status,'attempts':job.attempts,'error':job.error} if job else None}
        item['question']['answers']=q.answers
        item['question']['answer_status']=q.answer_status
        items.append(item)
    batches=[]
    for b in SolutionBatch.query.order_by(SolutionBatch.id.desc()).limit(10):
        counts=dict(db.session.query(SolutionJob.status,func.count()).filter_by(batch_id=b.id).group_by(SolutionJob.status).all())
        paper=db.session.query(Paper).join(Question,Question.paper_id==Paper.id).join(SolutionJob,SolutionJob.question_id==Question.id).filter(SolutionJob.batch_id==b.id).first()
        batches.append(dict(id=b.id,paper_name=paper.name if paper else None,status=b.status,counts=counts,worker_online=bool(b.worker_seen and time.time()-b.worker_seen<120)))
    counts=dict(db.session.query(AISolution.status,func.count()).group_by(AISolution.status).all())
    return jsonify(items=items,total=query.count(),page=page,batches=batches,counts=counts)

@bp.post('/admin/ai-solutions/queue')
@require_user(True)
def queue():
    b=body();full=b.get('full_paper') is True;limit=None if full else b.get('limit',30)
    if full and (type(b.get('paper_id'))!=int or b.get('question_ids') or b.get('regenerate')):abort(400,description='Choose one paper to generate missing solutions')
    if not full and (type(limit)!=int or not 1<=limit<=30):abort(400,description='Choose 1–30 questions')
    query=Question.query.join(Paper).filter(Question.status=='AVAILABLE',Paper.status!='ARCHIVED')
    if b.get('question_ids'):
        ids=b['question_ids']
        if not isinstance(ids,list) or len(ids)>30 or any(type(i)!=int for i in ids):abort(400)
        query=query.filter(Question.id.in_(ids))
    elif b.get('paper_id'):query=query.filter(Question.paper_id==b['paper_id'])
    else:abort(400,description='Select a paper or specific questions')
    for field,col in [('term_id',Paper.term_id),('exam_type_id',Paper.exam_type_id),('kind',Question.kind)]:
        if not full and b.get(field):query=query.filter(col==b[field])
    batch=SolutionBatch();db.session.add(batch);db.session.flush();count=0
    # One bounded paper per full request; prefetch source data and job/solution rows.
    candidates=query.options(selectinload(Question.options),selectinload(Question.images)).order_by(Question.id)
    if not full:candidates=candidates.limit(500)
    rows=candidates.all();ids=[q.id for q in rows]
    solutions={s.question_id:s for s in AISolution.query.filter(AISolution.question_id.in_(ids))}
    jobs={j.question_id:j for j in SolutionJob.query.filter(SolutionJob.question_id.in_(ids))}
    for q in rows:
        v=version(snapshot(q));sol=solutions.get(q.id);j=jobs.get(q.id)
        if j and j.status in ('QUEUED','PROCESSING'):continue
        if sol and sol.version==v and not b.get('regenerate'):continue
        if not j:j=SolutionJob(question_id=q.id);db.session.add(j)
        j.batch_id=batch.id;j.version=v;j.status='QUEUED';j.attempts=0;j.retry_at=0;j.lease_token=None;j.error=None
        count+=1
        if limit is not None and count==limit:break
    if not count:db.session.delete(batch)
    db.session.commit();return jsonify(batch_id=batch.id if count else None,queued=count)

@bp.post('/admin/ai-solutions/batches/<int:id>')
@require_user(True)
def batch_action(id):
    b=db.get_or_404(SolutionBatch,id);action=body().get('action')
    if action not in ('pause','resume'):abort(400)
    b.status='PAUSED' if action=='pause' else 'RUNNING';db.session.commit();return jsonify(ok=True)

@bp.post('/admin/ai-solutions/<int:qid>')
@require_user(True)
def edit(qid):
    s=AISolution.query.filter_by(question_id=qid).first_or_404();q=db.get_or_404(Question,qid);b=body()
    if s.version!=version(snapshot(q)):abort(409,description='Question changed. Regenerate this solution.')
    action=b.get('action')
    if action=='edit':
        text=b.get('text','')
        if not isinstance(text,str) or not 1<=len(text.strip())<=14000:abort(400)
        s.text=text.strip();s.status='DRAFT'
    elif action=='publish':
        if s.status not in ('CHECKS_PASSED','DRAFT','PUBLISHED'):abort(409,description='Review/edit the flagged solution first')
        s.status='PUBLISHED'
    elif action=='unpublish':s.status='DRAFT'
    else:abort(400)
    s.updated_at=time.time();db.session.commit();return jsonify(ok=True)

@bp.post('/admin/ai-solutions/worker/claim')
@require_user(True)
def claim():
    now=time.time()
    # Expired leases are recoverable; completion requires the latest lease token.
    SolutionJob.query.filter_by(status='PROCESSING').filter(SolutionJob.lease_until<now).update({'status':'QUEUED','lease_token':None},synchronize_session=False)
    SolutionBatch.query.filter_by(status='RUNNING').update({'worker_seen':now},synchronize_session=False)
    j=SolutionJob.query.join(SolutionBatch).filter(SolutionBatch.status=='RUNNING',SolutionJob.status=='QUEUED',SolutionJob.retry_at<=now).order_by(SolutionJob.id).with_for_update(skip_locked=True,of=SolutionJob).first()
    if not j:db.session.commit();return jsonify(job=None)
    q=db.session.get(Question,j.question_id)
    if not q or q.status!='AVAILABLE' or db.session.get(Paper,q.paper_id).status=='ARCHIVED' or version(snapshot(q))!=j.version:
        j.status='OUTDATED';db.session.commit();return jsonify(job=None)
    j.status='PROCESSING';j.attempts+=1;j.lease_token=secrets.token_hex(24);j.lease_until=now+600
    source=snapshot(q);use_paper_image_delivery(q.paper_id);prepare_image_paths([source])
    data=dict(id=j.id,token=j.lease_token,question=question_with_image_urls(source),prompt_version=PROMPT_VERSION)
    # Worker requires source keys; public exam bootstrap still omits them.
    data['question']['answers']=q.answers;data['question']['answer_status']=q.answer_status
    db.session.commit();return jsonify(job=data)

@bp.post('/admin/ai-solutions/worker/<int:id>/finish')
@require_user(True)
def finish(id):
    b=body();j=SolutionJob.query.filter_by(id=id).with_for_update().first_or_404()
    if j.status!='PROCESSING' or j.lease_token!=b.get('token') or j.lease_until<time.time():abort(409,description='Lease expired or superseded')
    q=db.session.get(Question,j.question_id)
    if not q or q.status!='AVAILABLE' or db.session.get(Paper,q.paper_id).status=='ARCHIVED' or version(snapshot(q))!=j.version:j.status='OUTDATED'
    elif b.get('error'):
        code=b['error'];j.error={'quota':'Provider quota reached; resume later','network':'Temporary provider/network failure','auth':'Check Gemini API key/model access','invalid':'Invalid provider output','config':'Check Gemini request/model configuration'}.get(code,'Generation failed')
        detail=str(b.get('error_detail',''))
        if detail and len(detail)<=140 and all(c.isalnum() or c in ' _:-().' for c in detail):j.error=(j.error+' ['+detail+']')[:240]
        if code in ('quota','auth','config'):
            db.session.get(SolutionBatch,j.batch_id).status='QUOTA_PAUSED' if code=='quota' else 'PAUSED';j.status='QUEUED';j.attempts=max(0,j.attempts-1)
        else:j.status='FAILED' if j.attempts>=3 else 'QUEUED';j.retry_at=time.time()+60*(2**min(j.attempts,3))
    else:
        try:text,final,failures=checked_output(snapshot(q),b.get('output'))
        except ValueError as e:
            j.status='FAILED';j.error=str(e)[:240]
        else:
            s=AISolution.query.filter_by(question_id=q.id).first()
            if not s:s=AISolution(question_id=q.id);db.session.add(s)
            s.version=j.version;s.text=text;s.final_answer=final;s.status='NEEDS_REVIEW' if failures else 'CHECKS_PASSED';s.checks=failures;s.provider=b.get('provider') if b.get('provider') in ('gemini','groq','antigravity','openrouter') else 'gemini';s.model=str(b.get('model',''))[:100];s.prompt_version=PROMPT_VERSION;s.updated_at=time.time();j.status='DONE';j.error=None
    j.lease_token=None;db.session.commit();return jsonify(ok=True,status=j.status)

@bp.get('/attempts/<int:aid>/questions/<int:qid>/ai-solution')
@require_visitor
def student_solution(aid,qid):
    a=owned(aid)
    if a.status=='ACTIVE' and a.mode!='practice':abort(403,description='Solutions are available after submission')
    i=AttemptAnswer.query.filter_by(attempt_id=aid,question_id=qid).first_or_404()
    s=AISolution.query.filter_by(question_id=qid,status='PUBLISHED').first();q=db.session.get(Question,qid)
    if not s or not q or q.status!='AVAILABLE' or s.version!=version(i.snapshot) or s.version!=version(snapshot(q)):return jsonify(available=False)
    return jsonify(available=True,text=s.text,label='AI-generated explanation')


def review_solutions(items):
    """Fetch one review page in a batch, never one HTTP request per question."""
    ids=[i['question']['id'] for i in items]
    solutions={s.question_id:s for s in AISolution.query.filter(AISolution.question_id.in_(ids),AISolution.status=='PUBLISHED')}
    current={}
    if solutions:
        current={q.id:version(snapshot(q)) for q in Question.query.options(selectinload(Question.options),selectinload(Question.images)).filter(Question.id.in_(solutions),Question.status=='AVAILABLE')}
    for i in items:
        s=solutions.get(i['question']['id'])
        i['ai_solution']=dict(available=True,text=s.text,label='AI-generated explanation') if s and s.version==current.get(s.question_id) and s.version==version(i['question']) else dict(available=False)
    return items

@bp.get('/admin/ai-solutions/papers/<int:pid>/export')
@require_user(True)
def export_solution_paper(pid):
    p=db.session.get(Paper,pid)
    if not p or p.status=='ARCHIVED':abort(404)
    qs=Question.query.filter_by(paper_id=pid,status='AVAILABLE').options(selectinload(Question.options),selectinload(Question.images)).order_by(Question.id).all()
    use_paper_image_delivery(pid)
    snaps=[snapshot(q) for q in qs];prepare_image_paths(snaps)
    return jsonify(format='pyq-solutions-v1',paper_id=pid,paper_name=p.name,questions=[dict(question_id=q.id,number=q.number,version=version(s),question={**question_with_image_urls(s),'answers':s.get('answers'),'answer_status':s.get('answer_status')}) for q,s in zip(qs,snaps)],solutions=[])

@bp.post('/admin/ai-solutions/import')
@require_user(True)
def import_paper_solutions():
    b=body();bundle=b.get('bundle');pid=b.get('paper_id')
    if b.get('publish') is True and b.get('save') is not True:abort(400,description='Publishing requires saving the import')
    if type(pid)!=int or not isinstance(bundle,dict) or bundle.get('format')!='pyq-solutions-v1' or bundle.get('paper_id')!=pid:abort(400,description='Solution file must match the selected paper and pyq-solutions-v1 format')
    entries=bundle.get('solutions')
    if not isinstance(entries,list) or not 1<=len(entries)<=200:abort(400,description='Import 1–200 question solutions for one paper')
    if len(json.dumps(bundle,ensure_ascii=False))>2_000_000:abort(400,description='Solution file too large')
    p=db.session.get(Paper,pid)
    if not p or p.status=='ARCHIVED':abort(404)
    qs={q.id:q for q in Question.query.filter_by(paper_id=pid,status='AVAILABLE').options(selectinload(Question.options),selectinload(Question.images)).with_for_update().all()}
    existing={s.question_id:s for s in AISolution.query.filter(AISolution.question_id.in_(qs)).with_for_update()}
    jobs={j.question_id:j for j in SolutionJob.query.filter(SolutionJob.question_id.in_(qs)).with_for_update()}
    preview=[];seen=set()
    for e in entries:
        if not isinstance(e,dict) or type(e.get('question_id'))!=int:abort(400,description='Each solution needs an integer question_id')
        qid=e['question_id'];q=qs.get(qid)
        if not q or qid in seen:abort(400,description='Unknown, hidden, foreign or duplicate question')
        seen.add(qid);v=version(snapshot(q))
        if e.get('version')!=v:abort(409,description='Question changed since export; export the paper again')
        if qid in existing and b.get('replace_existing') is not True:abort(409,description=f'Question {q.number} already has a solution; enable Replace existing solutions to update it')
        if qid in jobs and jobs[qid].status=='PROCESSING':abort(409,description='Worker is processing a question; pause and wait before importing')
        try:text,final,flags=checked_output(snapshot(q),e.get('output'))
        except ValueError as err:abort(400,description=f'Question {q.number}: {err}')
        preview.append(dict(question_id=qid,number=q.number,version=v,text=text,final_answer=final,checks=flags,status='NEEDS_REVIEW' if flags else 'CHECKS_PASSED',replacing=qid in existing))
    if b.get('save') is True:
        for entry in preview:
            sol=existing.get(entry['question_id'])
            if not sol:sol=AISolution(question_id=entry['question_id']);db.session.add(sol)
            if b.get('publish') is True and not entry['checks']:entry['status']='PUBLISHED'
            sol.version=entry['version'];sol.text=entry['text'];sol.final_answer=entry['final_answer'];sol.checks=entry['checks'];sol.status=entry['status'];sol.provider='admin-import';sol.model='chat-assisted';sol.prompt_version='import-v1';sol.updated_at=time.time()
            job=jobs.get(entry['question_id'])
            if job:job.status='DONE';job.error=None;job.lease_token=None
        db.session.commit()
    saved=len(preview) if b.get('save') is True else 0
    return jsonify(items=preview,saved=saved,published=sum(e['status']=='PUBLISHED' for e in preview) if saved else 0,needs_review=sum(bool(e['checks']) for e in preview) if saved else 0)
