import sys,json,csv,collections
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import create_app
from backend.models import *
app=create_app()
with app.app_context():
    rows=[]
    for p in Paper.query.order_by(Paper.id):
        f=IngestionFile.query.filter_by(paper_id=p.id).order_by(IngestionFile.id.desc()).first()
        effective=db.session.get(Paper,p.canonical_paper_id) if p.canonical_paper_id else p
        count=Question.query.filter_by(paper_id=effective.id,status='AVAILABLE').count()
        rows.append({'paper_id':p.id,'course':p.course.name,'exam':p.exam_type.name,'term':p.term.name,'paper':p.name,'source_url':p.source_url,'paper_status':effective.status,'job_status':f.status if f else 'NOT_ATTEMPTED','available_questions':count,'canonical_paper_id':p.canonical_paper_id,'error':f.error if f else 'No processing job','warnings':f.warnings if f else [],'events':f.events if f else []})
    stats={'catalog_courses':Course.query.count(),'catalog_papers':Paper.query.count(),'terms':Term.query.count(),'paper_statuses':dict(collections.Counter(r['paper_status'] for r in rows)),'job_statuses':dict(collections.Counter(r['job_status'] for r in rows)),'unique_available_questions':Question.query.filter_by(status='AVAILABLE').count(),'flagged_questions':Question.query.filter_by(status='EXTRACTION_FAILED').count(),'source_instruction_items':Question.query.filter_by(status='INSTRUCTION').count(),'images':QuestionImage.query.count(),'papers_with_available_questions':sum(r['available_questions']>0 for r in rows)}
    Path('docs/PROCESSING-REPORT.json').write_text(json.dumps({'summary':stats,'papers':rows},indent=2))
    fields=['paper_id','course','exam','term','paper','source_url','paper_status','job_status','available_questions','canonical_paper_id','error']
    with open('docs/SOURCE-RESULTS.csv','w',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    print(json.dumps(stats,indent=2))
