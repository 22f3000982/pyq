from backend.automatic_parser import parse_document
from backend.ingestion import extraction_failure_message


def test_tcs_export_without_question_type_uses_label_and_keeps_options():
    text='''Question Number : 1 Question Id : 6406531963330
Correct Marks : 5
Question Label : Multiple Choice Question
Identify the minimum process maturity level.
Options :
6406536378894. Level 1
6406536378895. Level 2
Question Number : 2 Question Id : 6406531963331
Correct Marks : 5
Question Label : Multiple Select Question
Select all valid statements.
Options :
6406536378896. Alpha
6406536378897. Beta'''
    layout={'text':text,'pages':[(0,len(text),1)],'assets':{},'indicators':{},'warnings':[]}
    records,_,_=parse_document(layout)
    assert len(records)==2
    assert [q['kind'] for q in records]==['MCQ','MSQ']
    assert all(q['status']=='AVAILABLE' for q in records)
    assert records[0]['options'][1]['text']=='Level 2'
    assert all(q['answers'] is None for q in records)


def test_text_pdf_failure_is_not_described_as_scanned():
    message=extraction_failure_message({'text':'Readable question text'},[],0)
    assert 'boundaries' in message and 'not classified as image-only' in message
    assert extraction_failure_message({'text':'Readable'},[{}],0).startswith('1 question records detected')
    assert extraction_failure_message({'text':'[[PAGE_FAILED:1]]'},[],0).startswith('No readable PDF text')
    assert extraction_failure_message({'text':'Readable'},[{}],1) is None
