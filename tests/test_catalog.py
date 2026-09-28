from pathlib import Path
import pytest
from backend.catalog import import_workbook
from backend.models import *
from conftest import login
WORKBOOK=Path(__file__).resolve().parents[1]/'sample-data/catalog.xlsx'
def test_import_real_workbook_idempotent(app):
    first=import_workbook(WORKBOOK); count=Paper.query.count()
    assert Course.query.count()==39
    assert Term.query.count()==13
    assert first['linked_cells']==722
    assert Paper.query.join(Term).filter(Term.name=='Sep 2026').count()==0
    assert Paper.query.join(ExamType).filter(ExamType.name=='OPPE 1').count()>0
    assert Course.query.filter_by(name='Operating Systems').count()==0
    assert Paper.query.filter(Paper.variant!='').count()>0
    second=import_workbook(WORKBOOK)
    assert second['new_papers']==0 and Paper.query.count()==count
    assert Question.query.count()==0

def test_auth_and_catalog(client,app):
    assert client.post('/api/auth/register',json={}).status_code==403
    h=login(client)
    assert client.get('/api/session').json['user']['role']=='STUDENT'
    import_workbook(WORKBOOK)
    r=client.get('/api/courses?q=software&limit=1').json
    assert len(r['items'])==1 and r['total']==2
    assert client.get('/api/papers?exam=Quiz+2&year=2025').json['total']>0
    assert client.get('/api/courses?limit=x').status_code==400
    assert client.post('/api/auth/logout',headers=h).status_code==200
    assert client.get('/api/session').json['user'] is None

def test_shifted_headers_and_placeholders(app,tmp_path):
    import openpyxl
    w=openpyxl.load_workbook(WORKBOOK)
    s=w['May 2026']
    s.insert_cols(6)
    for row in s:
        for c in row:
            if c.hyperlink: c.hyperlink.ref=c.coordinate
    p=tmp_path/'shifted.xlsx';w.save(p)
    report=import_workbook(p)
    assert report['linked_cells']==722
    assert report['terms']['May 2026']==85
    assert not Paper.query.filter(Paper.name.in_(['No OPPE','No Quiz 1','Only 1 QP'])).first()
    assert len(report['issues'])>=4


def test_catalog_lookup_queries_are_bounded(app):
    from sqlalchemy import event
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
    event.listen(db.engine,'before_cursor_execute',capture)
    try:
        first=import_workbook(WORKBOOK)
        second=import_workbook(WORKBOOK)
    finally:event.remove(db.engine,'before_cursor_execute',capture)
    assert first['new_papers']==734 and second['new_papers']==0
    assert len(statements)<=12, 'Catalog lookups must not grow with workbook cells'
    assert SourceEntry.query.count()==734


def test_numeric_catalog_filters_validate_types(client,app):
    from test_engine import seed
    paper=seed()
    for name,value in [('course_id',paper.course_id),('term_id',paper.term_id),('exam_type_id',paper.exam_type_id),('year',paper.term.year)]:
        result=client.get('/api/papers',query_string={name:str(value)})
        assert result.status_code==200 and result.json['total']==1
        for bad in ('abc','1.5','9999999999999999999999'):
            assert client.get('/api/papers',query_string={name:bad}).status_code==400
