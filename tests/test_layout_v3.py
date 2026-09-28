import io
import fitz
from PIL import Image,ImageDraw
from backend.visual_pdf import layout_document
from backend.automatic_parser import parse_document
from backend.engine import question_order
from backend.models import db,Question,AttemptAnswer
from conftest import login
from test_engine import seed

def test_inline_notation_and_source_spacing(tmp_path):
    doc=fitz.open();p=doc.new_page()
    p.insert_text((40,40),'Question Number : 2 Question Id : 123456789 Question Type : MCQ')
    p.insert_text((40,60),'Correct Marks : 2')
    p.insert_text((40,80),'Question Label : Multiple Choice Question')
    p.insert_text((40,110),'Consider an LSH setup with')
    for x,label in [(180,'L=2'),(290,'K=2')]:
        im=Image.new('RGB',(80,24),'white');ImageDraw.Draw(im).text((0,0),label,fill='black');b=io.BytesIO();im.save(b,format='PNG');p.insert_image(fitz.Rect(x,97,x+30,110),stream=b.getvalue())
    p.insert_text((214,110),'tables and')
    p.insert_text((325,110),'hash functions.')
    p.insert_text((40,140),'Options :')
    p.insert_text((40,160),'123456701. Correct',color=(0,.6,0))
    p.insert_text((40,180),'123456702. Incorrect',color=(1,0,0))
    layout=layout_document(doc,tmp_path,'synthetic12345678',False)
    records,_,_=parse_document(layout);q=records[0]
    assert 'with [[IMAGE:' in q['text'] and ']] tables and [[IMAGE:' in q['text'] and ']] hash functions.' in q['text']
    assert len(q['images'])==2 and all(a['inline'] for a in q['images'])
    assert q['answers']==['123456701']

def test_numeric_palette_order_for_existing_and_new_attempts(client):
    p=seed();h=login(client)
    qs=Question.query.filter_by(paper_id=p.id).all()
    for q,n in zip(qs,['10','2','3']):q.number=n
    db.session.commit()
    a=client.post('/api/attempts',json={'paper_id':p.id,'mode':'practice'},headers=h).json
    numbers=[x['number'] for x in a['palette']]
    assert numbers==sorted(numbers,key=question_order)
    rows=AttemptAnswer.query.filter_by(attempt_id=a['id']).all()
    for n,i in enumerate(rows):i.position=len(rows)-n
    db.session.commit()
    numbers=[x['number'] for x in client.get('/api/attempts/'+str(a['id'])).json['palette']]
    assert numbers==sorted(numbers,key=question_order)

def test_timer_override_preserves_source_duration(client):
    p=seed();h=login(client)
    a=client.post('/api/attempts',json={'paper_id':p.id,'mode':'exam','duration_seconds':5400},headers=h)
    assert a.status_code==201
    assert 5395<a.json['deadline']-a.json['server_time']<=5400
    assert p.duration_seconds==60
    b=client.post('/api/attempts',json={'paper_id':p.id,'mode':'exam','duration_seconds':7200},headers=h)
    assert 7195<b.json['deadline']-b.json['server_time']<=7200
