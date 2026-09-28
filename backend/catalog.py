"""Inspected workbook importer, with provenance and conservative ambiguity handling."""
import hashlib, re
from urllib.parse import urlparse
import openpyxl
from .models import db, Course, Term, ExamType, Paper, SourceEntry, ImportRun
ALIASES = {'operating systems':'Operating System','data visualization':'Data Visualization Design'}
def norm(value): return re.sub(r'\s+',' ',str(value or '')).strip()
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def headers(sheet):
    for row in sheet.iter_rows(min_row=1,max_row=min(20,sheet.max_row)):
        result={norm(c.value).lower():c.column for c in row if isinstance(c.value,str)}
        if 'course name' in result: return row[0].row,result
    return None,{}
def get_or_add(model, **fields):
    obj=model.query.filter_by(**fields).first()
    if obj is None: obj=model(**fields); db.session.add(obj); db.session.flush()
    return obj

def import_workbook(path):
    raw=open(path,'rb').read(); sha=hashlib.sha256(raw).hexdigest()
    workbook=openpyxl.load_workbook(path); cached=openpyxl.load_workbook(path,data_only=True)
    report={'new_courses':0,'new_papers':0,'existing_papers':0,'linked_cells':0,'issues':[], 'terms':{}}
    master=next((s for s in workbook if 'course code' in headers(s)[1]),None)
    if master is None: raise ValueError('No master course sheet with Course Name / Course Code found')
    # Load lookup tables once: remote databases must not do several queries
    # and flushes for every workbook cell. Preserve the same identities/rules.
    existing_courses=Course.query.all()
    by_code={c.code:c for c in existing_courses if c.code}
    terms={t.name:t for t in Term.query.all()}
    exams={e.name:e for e in ExamType.query.all()}
    papers={p.identity:p for p in Paper.query.all()}
    provenance_seen={identity for (identity,) in db.session.query(SourceEntry.identity).all()}
    pending_sources=[]
    rownum,cols=headers(master)
    for row in master.iter_rows(min_row=rownum+1):
        values=lambda label: norm(row[cols[label]-1].value) if label in cols else ''
        name,code=values('course name'),values('course code')
        if not name or not code: continue
        course=by_code.get(code)
        if not course:
            course=Course(name=name,code=code);db.session.add(course);by_code[code]=course;existing_courses.append(course);report['new_courses']+=1
        course.level=values('course level');course.course_type=values('course type')
        course.aliases=[alias for alias,target in ALIASES.items() if target==name]
    courses={norm(c.name).lower():c for c in existing_courses}
    for alias,target in ALIASES.items():
        if target.lower() in courses: courses[alias]=courses[target.lower()]
    for sheet in workbook:
        match=re.fullmatch(r'(Jan|May|Sep)\s+(\d{4})',sheet.title)
        if not match: continue
        term=terms.get(sheet.title)
        if term is None:
            term=Term(name=sheet.title,year=int(match[2]),month={'Jan':1,'May':5,'Sep':9}[match[1]])
            terms[sheet.title]=term;db.session.add(term)
        rownum,cols=headers(sheet)
        if not rownum: report['issues'].append({'sheet':sheet.title,'warning':'Header not recognized'});continue
        report['terms'][sheet.title]=0
        examcols={k:v for k,v in cols.items() if k in ('quiz 1','quiz 2') or k.startswith(('fn ','an ','oppe'))}
        for row in sheet.iter_rows(min_row=rownum+1):
            name=norm(row[cols['course name']-1].value)
            if not name:continue
            course=courses.get(name.lower())
            if not course:
                report['issues'].append({'sheet':sheet.title,'course':name,'warning':'Unknown course; not auto-merged'});continue
            for header,column in examcols.items():
                cell=row[column-1];value=norm(cell.value) if isinstance(cell.value,(str,int,float)) else ''
                url=cell.hyperlink.target if cell.hyperlink else None
                if not url:
                    urls=re.findall(r'https?://[^\s"<>]+',value)
                    url=urls[0] if len(urls)==1 else None
                if not url:
                    if value and not value.startswith('=') and not re.match(r'(?i)^(no\b|na\b|n/a|-) ',value+' '):
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
                    if session: examname='End Term'
                    elif header in ('quiz 1','quiz 2'):examname=header.title()
                    elif re.search('project',label,re.I):examname='Project'
                    else:
                        practical=re.search(r'(N?OPPE|NPPE)[\s_-]*(\d+)',label,re.I)
                        if practical:examname=practical[1].upper()+' '+practical[2]
                        else:examname='Practical assessment';warnings.append('Assessment type requires review')
                    exam=exams.get(examname)
                    if exam is None:
                        exam=ExamType(name=examname);exams[examname]=exam;db.session.add(exam)
                    # URL + label, rather than row/column, survives header/row movement.
                    identity=digest('|'.join([course.code,term.name,examname,session,label,url.split('?')[0]]))
                    paper=papers.get(identity)
                    if not paper:
                        paper=Paper(identity=identity,course=course,term=term,exam_type=exam,name=label,session=session,variant=label if len(parts)>1 else '',source_url=url,warnings=warnings)
                        db.session.add(paper);papers[identity]=paper;report['new_papers']+=1
                    else:report['existing_papers']+=1
                    provenance=digest('|'.join([sha,sheet.title,cell.coordinate,identity]))
                    if provenance not in provenance_seen:
                        provenance_seen.add(provenance)
                        pending_sources.append((paper,dict(identity=provenance,workbook_hash=sha,sheet=sheet.title,cell=cell.coordinate,raw_text=value,url=url)))
                    report['terms'][sheet.title]+=1
    # SQLAlchemy orders parent/child inserts and batches PostgreSQL inserts.
    db.session.flush()
    db.session.add_all([SourceEntry(paper_id=paper.id,**fields) for paper,fields in pending_sources])
    workbook.close();cached.close()
    db.session.add(ImportRun(workbook_hash=sha,report=report));db.session.commit()
    return report
