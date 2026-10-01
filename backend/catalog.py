"""Workbook catalog scanning, safe incremental sync, and legacy import compatibility."""
import hashlib,re
from collections import Counter
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

def structural_key(course_code,term_name,exam_name,session):
    return tuple(map(norm_key,[course_code,term_name,exam_name,session]))

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

def _existing_catalog():
    courses={c.id:c for c in Course.query.all()};terms={t.id:t for t in Term.query.all()};exams={e.id:e for e in ExamType.query.all()}
    papers=Paper.query.all();by_id={p.id:p for p in papers}
    exact={};structural={};sources={}
    def add(mapping,key,paper):
        if not key:return
        bucket=mapping.setdefault(key,[])
        if all(existing.id!=paper.id for existing in bucket):bucket.append(paper)
    for p in papers:
        course=courses.get(p.course_id);term=terms.get(p.term_id);exam=exams.get(p.exam_type_id)
        if not (course and term and exam):continue
        code=course.code or course.name
        add(exact,paper_key(code,term.name,exam.name,p.session,p.name),p)
        add(structural,structural_key(code,term.name,exam.name,p.session),p)
        add(sources,source_token(p.source_url),p)
    # Previous workbook provenance is valuable when display labels were renamed.
    for source in SourceEntry.query.all():
        paper=by_id.get(source.paper_id)
        if paper:add(sources,source_token(source.url),paper)
    return {'papers':papers,'by_id':by_id,'exact':exact,'structural':structural,'sources':sources}

def _preferred(candidates,ready):
    if not candidates:return None
    return sorted(candidates,key=lambda p:(p.status!='ARCHIVED',((p.canonical_paper_id or p.id) in ready),p.id),reverse=True)[0]

def _match_entries(scan,ready):
    catalog=_existing_catalog();claimed=set();matches={}
    structure_counts=Counter(structural_key(e['course_code'],e['term_name'],e['exam_name'],e['session']) for e in scan['entries'])
    for entry in scan['entries']:
        paper=None;token=entry['source_token'];structure=structural_key(entry['course_code'],entry['term_name'],entry['exam_name'],entry['session'])
        # Strongest signal: same source file, including links seen in older workbook imports.
        source_matches=[p for p in catalog['sources'].get(token,[]) if p.id not in claimed]
        if len(source_matches)==1:paper=source_matches[0]
        elif source_matches:
            exact_ids={p.id for p in catalog['exact'].get(entry['key'],[])}
            narrowed=[p for p in source_matches if p.id in exact_ids]
            if len(narrowed)==1:paper=narrowed[0]
            else:
                structural_ids={p.id for p in catalog['structural'].get(structure,[])}
                narrowed=[p for p in source_matches if p.id in structural_ids]
                if len(narrowed)==1:paper=narrowed[0]
        # Exact logical identity remains safe when source sharing links changed.
        if paper is None:
            exact=[p for p in catalog['exact'].get(entry['key'],[]) if p.id not in claimed]
            if exact:paper=_preferred(exact,ready)
        # Last safe fallback: one workbook paper and one DB paper for the same
        # course+term+exam+session. Never guess when either side is ambiguous.
        if paper is None and structure_counts[structure]==1:
            structural=[p for p in catalog['structural'].get(structure,[]) if p.id not in claimed]
            if len(structural)==1:paper=structural[0]
        if paper:
            matches[entry['key']]=paper;claimed.add(paper.id)
    return matches,catalog

def compare_scan(scan):
    ready={pid for pid, in db.session.query(Question.paper_id).filter(Question.status=='AVAILABLE').distinct()}
    matches,catalog=_match_entries(scan,ready)
    latest_ids=db.session.query(func.max(IngestionFile.id)).group_by(IngestionFile.paper_id)
    latest={f.paper_id:f for f in IngestionFile.query.filter(IngestionFile.id.in_(latest_ids)).all()}
    categories={'new':[],'unprocessed':[],'changed':[],'available':[],'ignored':[],'queued':[],'failed':[]}
    matched_ids=set()
    active_states={'QUEUED','FETCH_QUEUED','FETCHING','PROCESSING'}
    failed_states={'PROCESSING_FAILED','EXTRACTION_FAILED'}
    for entry in scan['entries']:
        paper=matches.get(entry['key'])
        if not paper:
            categories['new'].append({**entry,'category':'new','paper_id':None});continue
        matched_ids.add(paper.id)
        effective=paper.canonical_paper_id or paper.id;is_available=effective in ready
        job=latest.get(paper.id)
        base={**entry,'paper_id':paper.id,'paper_status':paper.status,'old_url':paper.source_url,
              'available':is_available,'latest_ingestion_status':job.status if job else None}
        if paper.status=='ARCHIVED':category='ignored'
        elif source_token(paper.source_url)!=entry['source_token']:category='changed'
        elif job and job.status in active_states:category='queued'
        elif job and job.status in failed_states and not is_available:category='failed'
        elif is_available:category='available'
        else:category='unprocessed'
        base['category']=category;categories[category].append(base)
    absent=[{'paper_id':p.id,'name':p.name,'course_id':p.course_id,'term_id':p.term_id,'exam_type_id':p.exam_type_id}
            for p in catalog['papers'] if p.id not in matched_ids and p.status!='ARCHIVED' and p.source_url]
    already_applied=ImportRun.query.filter_by(workbook_hash=scan['workbook_hash']).first() is not None
    summary={k:len(v) for k,v in categories.items()}
    summary.update(total=len(scan['entries']),invalid=len(scan['issues']),absent=len(absent),
                   pending=len(categories['new'])+len(categories['unprocessed']))
    return {'workbook_hash':scan['workbook_hash'],'already_applied':already_applied,'summary':summary,
            'items':categories,'issues':scan['issues'],'absent':absent,'terms':scan['terms'],'linked_cells':scan['linked_cells']}

def _ensure_metadata(scan):
    by_code={c.code:c for c in Course.query.all() if c.code};by_name={norm_key(c.name):c for c in Course.query.all()}
    new_courses=0
    for item in scan['courses']:
        incoming_code=item['code'];incoming_name=norm_key(item['name'])
        c=by_code.get(incoming_code) or by_name.get(incoming_name)
        if not c:
            c=Course(name=item['name'],code=incoming_code);db.session.add(c);db.session.flush();new_courses+=1
        elif not c.code:
            # Adopt the workbook code only when the existing course has no stable code.
            c.code=incoming_code
        # A production catalog can contain legacy course codes while the maintained
        # workbook uses the current IITM code. The workbook code is an alias for the
        # same name-matched Course during this sync; never assume c.code == incoming_code.
        by_code[incoming_code]=c
        if c.code:by_code[c.code]=c
        by_name[incoming_name]=c;by_name[norm_key(c.name)]=c
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

def apply_sync(path,expected_hash=None,process_new=True,process_unprocessed=True,changed_keys=None,queue=True,batch_limit=20):
    scan=scan_workbook(path)
    if expected_hash and scan['workbook_hash']!=expected_hash:raise ValueError('Workbook changed after preview; preview the file again')
    batch_limit=max(1,min(int(batch_limit or 20),50))
    preview=compare_scan(scan);changed_keys=set(changed_keys or [])
    by_code,terms,exams,new_courses=_ensure_metadata(scan)
    state={item['key']:item for values in preview['items'].values() for item in values}
    new_candidates=[e for e in scan['entries'] if process_new and state[e['key']]['category']=='new']
    changed_candidates=[e for e in scan['entries'] if state[e['key']]['category']=='changed' and e['key'] in changed_keys]
    unprocessed_candidates=[e for e in scan['entries'] if process_unprocessed and state[e['key']]['category']=='unprocessed']
    # Fresh monthly papers take priority, then explicitly approved replacements,
    # then the older backlog. Only this slice is touched/queued in this run.
    candidates=new_candidates+changed_candidates+unprocessed_candidates
    selected=candidates[:batch_limit];selected_keys={e['key'] for e in selected}
    paper_by_id={p.id:p for p in Paper.query.all()}
    selected_ids=[];force_ids=[];new_papers=0;existing_papers=0;updated_sources=0;paper_for_key={}
    for entry in scan['entries']:
        item=state[entry['key']];paper=paper_by_id.get(item.get('paper_id'))
        if entry['key'] not in selected_keys:
            if paper:paper_for_key[entry['key']]=paper
            continue
        category=item['category']
        if category=='new':
            identity=digest('sync-v2|'+entry['key'])
            paper=Paper(identity=identity,course=by_code[entry['course_code']],term=terms[entry['term_name']],
                        exam_type=exams[entry['exam_name']],name=entry['name'],session=entry['session'],
                        variant=entry['variant'],source_url=entry['url'],warnings=entry['warnings'],
                        source_metadata={'catalog_sync_key':entry['key']})
            db.session.add(paper);db.session.flush();paper_by_id[paper.id]=paper
            new_papers+=1;selected_ids.append(paper.id)
        elif paper:
            existing_papers+=1
            if category=='unprocessed':selected_ids.append(paper.id)
            elif category=='changed':
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
    eligible=len(candidates);remaining=max(0,eligible-len(selected))
    report={'mode':'manual_incremental_sync','summary':preview['summary'],'new_courses':new_courses,'new_papers':new_papers,
            'existing_papers':existing_papers,'updated_sources':updated_sources,'selected_for_processing':len(set(selected_ids)),
            'batch_limit':batch_limit,'eligible_pending':eligible,'remaining_pending':remaining,
            'linked_cells':scan['linked_cells'],'issues':scan['issues'],'terms':scan['terms']}
    db.session.add(ImportRun(workbook_hash=scan['workbook_hash'],report=report));db.session.commit()
    batch_id=queued=0
    if queue and selected_ids:
        from .acquisition import queue_catalog
        batch_id,queued=queue_catalog(limit=batch_limit,paper_ids=selected_ids,retry=False,force_paper_ids=set(force_ids))
    report.update(batch_id=batch_id or None,queued=queued)
    return report

def preview_workbook(path):
    result=compare_scan(scan_workbook(path))
    # Keep the admin preview payload bounded even when the catalog grows into
    # thousands of papers. Counts remain exact; only actionable samples travel.
    result['items']={
        'new':result['items']['new'][:100],
        'unprocessed':result['items']['unprocessed'][:100],
        'changed':result['items']['changed'],
        'available':[],
        'ignored':result['items']['ignored'][:100],
        'queued':result['items']['queued'][:100],
        'failed':result['items']['failed'][:100],
    }
    result['issues']=result['issues'][:100]
    result['absent']=result['absent'][:100]
    return result

def import_workbook(path):
    """Legacy catalog-only import kept efficient for setup/CLI and older clients."""
    scan=scan_workbook(path)
    courses_list=Course.query.all();terms_list=Term.query.all();exams_list=ExamType.query.all();papers_list=Paper.query.all()
    by_code={c.code:c for c in courses_list if c.code};by_name={norm_key(c.name):c for c in courses_list}
    terms={t.name:t for t in terms_list};exams={e.name:e for e in exams_list}
    report={'new_courses':0,'new_papers':0,'existing_papers':0,'linked_cells':scan['linked_cells'],
            'issues':scan['issues'],'terms':scan['terms']}
    for item in scan['courses']:
        incoming=item['code'];course=by_code.get(incoming) or by_name.get(norm_key(item['name']))
        if not course:
            course=Course(name=item['name'],code=incoming);db.session.add(course);report['new_courses']+=1
        elif not course.code:course.code=incoming
        by_code[incoming]=course
        if course.code:by_code[course.code]=course
        by_name[norm_key(item['name'])]=course;by_name[norm_key(course.name)]=course
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
