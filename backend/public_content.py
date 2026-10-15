"""Safe SSR content blocks. Never interpret source HTML or change stored questions."""
import re
from .engine import question_snapshot
from .ai_solutions import version
TOKEN = re.compile(r'\[\[IMAGE:([^\]]+)\]\]')

def text_blocks(text):
    lines = (text or '').splitlines(keepends=True)
    result=[]; plain=[]; i=0
    def flush():
        if plain: result.append({'text': ''.join(plain)}); plain.clear()
    def cells(line): return [s.strip() for s in re.split(r'(?<!\\)\|', line.strip().strip('|'))]
    while i < len(lines):
        if i+1<len(lines) and '|' in lines[i] and re.fullmatch(r'\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*',lines[i+1]):
            head=cells(lines[i]); rows=[]; j=i+2
            while j<len(lines) and '|' in lines[j] and len(cells(lines[j]))==len(head):
                rows.append(cells(lines[j])); j+=1
            flush(); result.append({'table': {'head':head,'rows':rows}}); i=j
        else: plain.append(lines[i]); i+=1
    flush()
    return result

def content_parts(text, images, used=None, append_unused=True):
    used = used if used is not None else set()
    result=[]; cursor=0
    for match in TOKEN.finditer(text or ''):
        result.extend(text_blocks(text[cursor:match.start()]))
        image=next((image for image in images if image.get('token')==match[1]),None)
        if image:
            result.append({'image':image}); used.add(image['id'])
        else: result.append({'missing':True})
        cursor=match.end()
    result.extend(text_blocks((text or '')[cursor:]))
    if append_unused:
        result.extend({'image':image} for image in images if image['id'] not in used)
    return result

def paper_title(p):
    return ' · '.join(filter(None,[p.course.name,p.exam_type.name,p.term.name,p.session]))

def paper_items(questions, solutions):
    items=[]
    for q in questions:
        snap=question_snapshot(q); s=solutions.get(q.id)
        images=[i for i in snap['images'] if not i.get('option_key')]; used=set()
        passage=content_parts(snap.get('passage'),images,used,False)
        parts=content_parts(snap['text'],images,used)
        options=[dict(key=o['key'],parts=content_parts(o['text'],[i for i in snap['images'] if i.get('option_key')==o['key']])) for o in snap['options']]
        solution=s.text if s and s.status=='PUBLISHED' and s.version==version(snap) else None
        items.append(dict(question=q,snapshot=snap,passage_parts=passage,parts=parts,options=options,solution=solution,solution_parts=content_parts(solution,[])))
    return items
