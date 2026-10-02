import fitz
from backend.visual_pdf import layout_document
from backend.automatic_parser import parse_document
from backend.text_format import source_bold


def test_pdf_bold_preserves_boundaries_grading_and_options(tmp_path):
    doc=fitz.open();page=doc.new_page()
    lines=[('Question Number : 1 Question Id : 123456789 Question Type : MCQ',True),
           ('Correct Marks : 2',True),('Wrong Marks : 0',True),
           ('Question Label : Multiple Choice Question',True),
           ('Choose the correct statement.',False),('Important condition applies.',True),
           ('Options :',True),('12345671.  First choice',True),('12345672.  Second choice',False),
           ('Correct Answer : 12345671',True)]
    for n,(text,bold) in enumerate(lines):page.insert_text((40,40+n*20),text,fontname='hebo' if bold else 'helv',fontsize=10)
    layout=layout_document(doc,tmp_path,'source',ocr=False)
    assert '**' not in layout['text'] and layout['bold_ranges']
    questions,meta,issues=parse_document(layout);q=questions[0]
    assert q['status']=='AVAILABLE' and q['marks']==2 and q['answers']==['12345671']
    assert q['text']=='Choose the correct statement.\n**Important condition applies.**'
    assert q['options']==[{'key':'12345671','text':'**First choice**'},{'key':'12345672','text':'Second choice'}]
    assert 'Correct Answer' not in q['text']


def test_formatting_does_not_guess_or_touch_math_and_image_tokens():
    text=r'Use \(x**2\) with [[IMAGE:token]] and value'
    layout={'text':text,'bold_ranges':[(0,len(text))]}
    result=source_bold(text,layout)
    assert r'\(x**2\)' in result and '[[IMAGE:token]]' in result
    assert '**Use**' in result and '**and value**' in result
    duplicate={'text':'same same','bold_ranges':[(0,4)]}
    assert source_bold('same',duplicate)=='same'
    assert source_bold('OCR text',{'text':'OCR text'})=='OCR text'


def test_bold_offsets_across_pages_and_scanned_page_fallback(tmp_path):
    doc=fitz.open();first=doc.new_page();first.insert_text((40,40),'A sufficiently long plain native text paragraph.',fontname='helv')
    second=doc.new_page();second.insert_text((40,40),'Bold native text on the next PDF page.',fontname='hebo')
    third=doc.new_page();third.insert_text((40,40),'tiny',fontname='hebo')
    layout=layout_document(doc,tmp_path,'pages',ocr=False)
    assert source_bold('Bold native text on the next PDF page.',layout)=='**Bold native text on the next PDF page.**'
    assert source_bold('A sufficiently long plain native text paragraph.',layout)=='A sufficiently long plain native text paragraph.'
    failed=layout['text'].index('[[PAGE_FAILED:3]]')
    assert not any(a>=failed for a,b in layout['bold_ranges'])


def test_shared_passage_keeps_bold_without_repeating_answer_metadata():
    text=('Question Numbers : (1 to 1)\nQuestion Label : Comprehension\nRead this passage.\nSub questions\n'
          'Question Number : 1 Question Id : 123456789 Question Type : SA\nCorrect Marks : 2\n'
          'Question Label : Short Answer\nFind the value.\nPossible Answer : 3')
    passage=text.index('Read this passage.');stem=text.index('Find the value.')
    layout={'text':text,'pages':[(0,len(text),1)],'assets':{},'indicators':{},'warnings':[],
            'bold_ranges':[(passage,passage+len('Read this passage.')),(stem,stem+len('Find the value.'))]}
    q=parse_document(layout)[0][0]
    assert q['text']=='**Read this passage.**\n\n**Find the value.**'
    plain=parse_document({**layout,'bold_ranges':[]})[0][0]
    assert q['answers']==plain['answers'] and q['marks']==plain['marks']
    assert q['evidence']['shared_passage_text']=='**Read this passage.**'
