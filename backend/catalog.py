"""Workbook catalog scanning, safe incremental sync, and legacy import compatibility."""
import hashlib,re
from urllib.parse import urlparse,parse_qs
import openpyxl
from sqlalchemy import func
from .models import db,Course,Term,ExamType,Paper,Question,SourceEntry,ImportRun,IngestionFile

ALIASES={'operating systems':'Operating System','data visualization':'Data Visualization Design'}
TERM_MONTH={'Jan':1,'May':5,'Sep':9}

def norm(value):return re.sub(r'\s+',' ',str(value or '')).strip()
def norm_key(value):return norm(value).casefold()
def digest(value):return hashlib.sha256(value.encode()).hexdigest()

def headers(sheet):
    for row in sheet.iter_rows(min_row=1,max_row=min(20,sheet.max_row)):
        result={norm(c.value).lower():c.column for c in row if isinstance(c.value,str)}
        if 'course name' in result:return row[0].row,result
    return None,{}

def source_token(url):
    """Compare source identity without treating harmless sharing query params as changes."""
    value=norm(url)
    if not value:return ''
    try:
        u=urlparse(value);q=parse_qs(u.query)
        m=re.search(r'/file/d/([\w-]+)',u.path)
        if u.hostname=='drive.google.com' and (m or q.get('id')):
            return 'drive:'+(m[1] if m else q['id'][0])
        m=re.search(r'/(?:document|spreadsheets)/(?:u/\d+/)?d/([\w-]+)',u.path)
        if u.hostname=='docs.google.com' and m:return 'google-doc:'+m[1]
        return (u.scheme+'://'+(u.hostname or '')+u.path).rstrip('/').casefold()
    except Exception:return value.split('?',1)[0].casefold()

def paper_key(course_code,term_name,exam_name,session,name):
    return digest('|'.join(map(norm_key,[course_code,term_name,exam_name,session,name])))

def scan_workbook(path):
    raw=open(path,'rb').read();sha=hashlib.sha256(raw).hexdigest()
    workbook=openpyxl.load_workbook(path)
    report={'workbook_hash':sha,'linked_cells':0,'issues':[],'terms':{},'courses':[],'entries':[]}
    master=next((s for s in workbook if 'course code' in headers(s)[1]),None)
    if master is None:
        workbook.close();raise ValueError('No master course sheet with Course Name / Course Code found')
    rownum,cols=headers(master);master_courses={};name_to_code={}
    for row in master.iter_rows(min_row=rownum+1):
        get=lambda label:norm(row[cols[label]-1].value) if label in cols else ''
        name,code=get('course name'),get('course code')
        if not name or not code:continue
        item={'name':name,'code':code,'level':get('course level'),'course_type':get('course type')}
        master_courses[code]=item;name_to_code[norm_key(name)]=code
    for alias,target in ALIASES.items():
        target_code=name_to_code.get(norm_key(target))
        if target_code:name_to_code[norm_key(alias)]=target_code
    report['courses']=list(master_courses.values())

    seen_keys={}
    for sheet in workbook:
        match=re.fullmatch(r'(Jan|May|Sep)\s+(\d{4})',sheet.title)
        if not match:continue
        term={'name':sheet.title,'year':int(match[2]),'month':TERM_MONTH[match[1]]}
        rownum,cols=headers(sheet)
        if not rownum:
            report['issues'].append({'sheet':sheet.title,'warning':'Header not recognized'});continue
        report['terms'][sheet.title]=0
        examcols={k:v for k,v in cols.items() if k in ('quiz 1','quiz 2') or k.startswith(('fn ','an ','oppe'))}
        for row in sheet.iter_rows(min_row=rownum+1):
            course_name=norm(row[cols['course name']-1].value)
            if not course_name:continue
            code=name_to_code.get(norm_key(course_name))
            if not code:
                report['issues'].append({'sheet':sheet.title,'course':course_name,'warning':'Unknown course; not auto-merged'});continue
            course=master_courses[code]
            for header,column in examcols.items():
                cell=row[column-1];value=norm(cell.value) if isinstance(cell.value,(str,int,float)) else ''
                url=cell.hyperlink.target if cell.hyperlink else None
                if not url:
                    urls=re.findall(r'https?://[^\s"<>]+',value);url=urls[0] if len(urls)==1 else None
                if not url:
                    if value and not value.startswith('=') and not re.match(r'(?i)^(no\b|na\b|n/a\b|-)',value):
                        report['issues'].append({'sheet':sheet.title,'cell':cell.coordinate,'text':value,'warning':'No source link; not imported'})
                    elif cell.value and not isinstance(cell.value,(str,int,float)):
                        report['issues'].append({'sheet':sheet.title,'cell':cell.coordinate,'warning':'Uncached array formula; needs source review'})
                    continue
                if urlparse(url).scheme not in ('http','https'):continue
                report['linked_cells']+=1
                parts=[norm(p) for p in re.split(r'[,;]|\n(?=.*(?:QP\d|NPPE|OPPE))',value) if norm(p)] or [cell.coordinate]
                for label in parts:
                    warnings=[]
                    if len(parts)>1:warnings.append('Multiple named papers share one cell hyperlink; source mapping requires review')
                    session='FN' if header.startswith('fn ') else 'AN' if header.startswith('an ') else ''
                    if session:examname='End Term'
                    elif header in ('quiz 1','quiz 2'):examname=header.title()
                    elif re.search('project',label,re.I):examname='Project'
                    else:
                        practical=re.search(r'(N?OPPE|NPPE)[\s_-]*(\d+)',label,re.I)
                        if practical:examname=practical[1].upper()+' '+practical[2]
                        else:examname='Practical assessment';warnings.append('Assessment type requires review')
                    key=paper_key(code,term['name'],examname,session,label)
                    entry={'key':key,'course_code':code,'course_name':course['name'],'course_level':course['level'],
                           'course_type':course['course_type'],'term_name':term['name'],'term_year':term['year'],
                           'term_month':term['month'],'exam_name':examname,'session':session,'name':label,
                           'variant':label if len(parts)>1 else '','url':url,'source_token':source_token(url),
                           'sheet':sheet.title,'cell':cell.coordinate,'raw_text':value,'warnings':warnings}
                    previous=seen_keys.get(key)
                    if previous:
                        if previous['source_token']!=entry['source_token']:
                            report['issues'].append({'sheet':sheet.title,'cell':cell.coordinate,'paper':label,
                                'warning':'Same logical paper appears with different source links; first source kept'})
                        continue
                    seen_keys[key]=entry;report['entries'].append(entry);report['terms'][sheet.title]+=1
    workbook.close();return report

def _existing_index():
    courses={c.id:c for c in Course.query.all()};terms={t.id:t for t in Term.query.all()};exams={e.id:e for e in ExamType.query.all()}
    index={}
    for p in Paper.query.all():
        c=courses.get(p.course_id);t=terms.get(p.term_id);e=exams.get(p.exam_type_id)
        if not (c and t and e):continue
        key=paper_key(c.code or c.name,t.name,e.name,p.session,p.name)
        index.setdefault(key,[]).append(p)
    return index

def compare_scan(scan):
    existing=_existing_index()
    ready={pid for pid, in db.session.query(Question.paper_id).filter(Question.status=='AVAILABLE').distinct()}
    latest_ids=db.session.query(func.max(IngestionFile.id)).group_by(IngestionFile.paper_id)
    latest={f.paper_id:f for f in IngestionFile.query.filter(IngestionFile.id.in_(latest_ids)).all()}
    categories={'new':[],'unprocessed':[],'changed':[],'available':[],'ignored':[]}
    seen=set()
    for entry in scan['entries']:
        seen.add(entry['key']);matches=existing.get(entry['key'],[])
        if not matches:
            item={**entry,'category':'new','paper_id':None};categories['new'].append(item);continue
        # Prefer a visible paper with available content, then newest id.
        matches=sorted(matches,key=lambda p:(p.status!='ARCHIVED',((p.canonical_paper_id or p.id) in ready),p.id),reverse=True)
        paper=matches[0];effective=paper.canonical_paper_id or paper.id;is_available=effective in ready
        job=latest.get(paper.id)
        base={**entry,'paper_id':paper.id,'paper_status':paper.status,'old_url':paper.source_url,
              'available':is_available,'latest_ingestion_status':job.status if job else None}
        if paper.status=='ARCHIVED':base['category']='ignored';categories['ignored'].append(base)
        elif source_token(paper.source_url)!=entry['source_token']:
            base['category']='changed';categories['changed'].append(base)
        elif is_available:
            base['category']='available';categories['available'].append(base)
        else:
            base['category']='unprocessed';categories['unprocessed'].append(base)
    absent=[]
    for key,papers in existing.items():
        if key in seen:continue
        for p in papers:
            if p.status!='ARCHIVED' and p.source_url:
                absent.append({'paper_id':p.id,'name':p.name,'course_id':p.course_id,'term_id':p.term_id,'exam_type_id':p.exam_type_id})
    already_applied=ImportRun.query.filter_by(workbook_hash=scan['workbook_hash']).first() is not None
    summary={k:len(v) for k,v in categories.items()}
    summary.update(total=len(scan['entries']),invalid=len(scan['issues']),absent=len(absent))
    return {'workbook_hash':scan['workbook_hash'],'already_applied':already_applied,'summary':summary,
            'items':categories,'issues':scan['issues'],'absent':absent,'terms':scan['terms'],'linked_cells':scan['linked_cells']}

def _ensure_metadata(scan):
    by_code={c.code:c for c in Course.query.all() if c.code};by_name={norm_key(c.name):c for c in Course.query.all()}
    new_courses=0
    for item in scan['courses']:
        c=by_code.get(item['code']) or by_name.get(norm_key(item['name']))
        if not c:
            c=Course(name=item['name'],code=item['code']);db.session.add(c);db.session.flush();new_courses+=1
            by_code[c.code]=c;by_name[norm_key(c.name)]=c
        c.level=item['level'];c.course_type=item['course_type'];c.aliases=[a for a,target in ALIASES.items() if norm_key(target)==norm_key(c.name)]
    terms={t.name:t for t in Term.query.all()}
    for name in scan['terms']:
        if name not in terms:
            m=re.fullmatch(r'(Jan|May|Sep)\s+(\d{4})',name)
            if m:
                terms[name]=Term(name=name,year=int(m[2]),month=TERM_MONTH[m[1]]);db.session.add(terms[name])
    exams={e.name:e for e in ExamType.query.all()}
    for entry in scan['entries']:
        if entry['exam_name'] not in exams:
            exams[entry['exam_name']]=ExamType(name=entry['exam_name']);db.session.add(exams[entry['exam_name']])
    db.session.flush();return by_code,terms,exams,new_courses

def apply_sync(path,expected_hash=None,process_new=True,process_unprocessed=True,changed_keys=None,queue=True):
    scan=scan_workbook(path)
    if expected_hash and scan['workbook_hash']!=expected_hash:raise ValueError('Workbook changed after preview; preview the file again')
    preview=compare_scan(scan);changed_keys=set(changed_keys or [])
    by_code,terms,exams,new_courses=_ensure_metadata(scan);existing=_existing_index()
    selected_ids=[];force_ids=[];new_papers=0;existing_papers=0;updated_sources=0;paper_for_key={}
    categories={item['key']:item['category'] for values in preview['items'].values() for item in values}
    for entry in scan['entries']:
        category=categories[entry['key']];matches=existing.get(entry['key'],[])
        paper=sorted(matches,key=lambda p:(p.status!='ARCHIVED',p.id),reverse=True)[0] if matches else None
        if category=='new' and process_new:
            identity=digest('sync-v2|'+entry['key'])
            paper=Paper(identity=identity,course=by_code[entry['course_code']],term=terms[entry['term_name']],
                        exam_type=exams[entry['exam_name']],name=entry['name'],session=entry['session'],
                        variant=entry['variant'],source_url=entry['url'],warnings=entry['warnings'],
                        source_metadata={'catalog_sync_key':entry['key']})
            db.session.add(paper);db.session.flush();existing.setdefault(entry['key'],[]).append(paper)
            new_papers+=1;selected_ids.append(paper.id)
        elif paper:
            existing_papers+=1
            if category=='unprocessed' and process_unprocessed:selected_ids.append(paper.id)
            elif category=='changed' and entry['key'] in changed_keys:
                paper.source_url=entry['url'];paper.canonical_paper_id=None
                meta=dict(paper.source_metadata or {});meta['catalog_sync_key']=entry['key'];paper.source_metadata=meta
                updated_sources+=1;selected_ids.append(paper.id);force_ids.append(paper.id)
        if paper:paper_for_key[entry['key']]=paper
    db.session.flush()
    seen={identity for identity, in db.session.query(SourceEntry.identity).all()}
    for entry in scan['entries']:
        paper=paper_for_key.get(entry['key'])
        if not paper:continue
        provenance=digest('|'.join([scan['workbook_hash'],entry['sheet'],entry['cell'],entry['key']]))
        if provenance not in seen:
            db.session.add(SourceEntry(identity=provenance,paper_id=paper.id,workbook_hash=scan['workbook_hash'],
                sheet=entry['sheet'],cell=entry['cell'],raw_text=entry['raw_text'],url=entry['url']));seen.add(provenance)
    report={'mode':'manual_incremental_sync','summary':preview['summary'],'new_courses':new_courses,'new_papers':new_papers,
            'existing_papers':existing_papers,'updated_sources':updated_sources,'selected_for_processing':len(set(selected_ids)),
            'linked_cells':scan['linked_cells'],'issues':scan['issues'],'terms':scan['terms']}
    db.session.add(ImportRun(workbook_hash=scan['workbook_hash'],report=report));db.session.commit()
    batch_id=queued=0
    if queue and selected_ids:
        from .acquisition import queue_catalog
        batch_id,queued=queue_catalog(limit=None,paper_ids=sorted(set(selected_ids)),retry=True,force_paper_ids=set(force_ids))
    report.update(batch_id=batch_id or None,queued=queued)
    return report

def preview_workbook(path):
    return compare_scan(scan_workbook(path))

def import_workbook(path):
    """Legacy catalog-only import kept efficient for setup/CLI and older clients."""
    scan=scan_workbook(path)
    courses_list=Course.query.all();terms_list=Term.query.all();exams_list=ExamType.query.all();papers_list=Paper.query.all()
    by_code={c.code:c for c in courses_list if c.code};by_name={norm_key(c.name):c for c in courses_list}
    terms={t.name:t for t in terms_list};exams={e.name:e for e in exams_list}
    report={'new_courses':0,'new_papers':0,'existing_papers':0,'linked_cells':scan['linked_cells'],
            'issues':scan['issues'],'terms':scan['terms']}
    for item in scan['courses']:
        course=by_code.get(item['code']) or by_name.get(norm_key(item['name']))
        if not course:
            course=Course(name=item['name'],code=item['code']);db.session.add(course);by_code[item['code']]=course;by_name[norm_key(item['name'])]=course;report['new_courses']+=1
        course.level=item['level'];course.course_type=item['course_type'];course.aliases=[a for a,target in ALIASES.items() if norm_key(target)==norm_key(course.name)]
    for name in scan['terms']:
        if name not in terms:
            m=re.fullmatch(r'(Jan|May|Sep)\s+(\d{4})',name);terms[name]=Term(name=name,year=int(m[2]),month=TERM_MONTH[m[1]]);db.session.add(terms[name])
    for entry in scan['entries']:
        if entry['exam_name'] not in exams:
            exams[entry['exam_name']]=ExamType(name=entry['exam_name']);db.session.add(exams[entry['exam_name']])
    db.session.flush()
    # Rebuild a logical index after metadata IDs exist, without extra SELECTs.
    index={}
    for p in papers_list:
        course=next((x for x in courses_list if x.id==p.course_id),None) or by_code.get(next((k for k,v in by_code.items() if v.id==p.course_id),None))
        term=next((x for x in terms_list if x.id==p.term_id),None) or next((x for x in terms.values() if x.id==p.term_id),None)
        exam=next((x for x in exams_list if x.id==p.exam_type_id),None) or next((x for x in exams.values() if x.id==p.exam_type_id),None)
        if course and term and exam:index.setdefault(paper_key(course.code or course.name,term.name,exam.name,p.session,p.name),p)
    provenance_seen={identity for identity, in db.session.query(SourceEntry.identity).all()};pending=[]
    for entry in scan['entries']:
        paper=index.get(entry['key'])
        if not paper:
            paper=Paper(identity=digest('sync-v2|'+entry['key']),course=by_code[entry['course_code']],term=terms[entry['term_name']],
                        exam_type=exams[entry['exam_name']],name=entry['name'],session=entry['session'],variant=entry['variant'],
                        source_url=entry['url'],warnings=entry['warnings'],source_metadata={'catalog_sync_key':entry['key']})
            db.session.add(paper);db.session.flush();index[entry['key']]=paper;report['new_papers']+=1
        else:report['existing_papers']+=1
        provenance=digest('|'.join([scan['workbook_hash'],entry['sheet'],entry['cell'],entry['key']]))
        if provenance not in provenance_seen:
            provenance_seen.add(provenance);pending.append(SourceEntry(identity=provenance,paper_id=paper.id,workbook_hash=scan['workbook_hash'],
                sheet=entry['sheet'],cell=entry['cell'],raw_text=entry['raw_text'],url=entry['url']))
    db.session.add_all(pending);db.session.add(ImportRun(workbook_hash=scan['workbook_hash'],report=report));db.session.commit()
    return report
