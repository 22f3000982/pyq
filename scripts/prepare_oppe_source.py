"""Rebuild private import bundles from the owner's captured source pages.
Never execute source solutions here. Static parsing only; sandbox validates later.
"""
import ast,json,re,collections,base64,hashlib
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from markdownify import markdownify
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'backend/data/oppe'

def decode(value):
    if isinstance(value,dict):
        if set(value)=={'__tuple__'}:return tuple(decode(x) for x in value['__tuple__'])
        if set(value)=={'__intdict__'}:return {int(k):decode(v) for k,v in value['__intdict__']}
        if set(value)=={'__set__'}:return set(decode(x) for x in value['__set__'])
        return {k:decode(v) for k,v in value.items()}
    return [decode(v) for v in value] if isinstance(value,list) else value

def statement(html):
    soup=BeautifulSoup(html,'html.parser');folder=DATA/'images';folder.mkdir(exist_ok=True)
    for img in soup.find_all('img'):
        url=img.get('src','')
        if url.startswith('data:image/'):
            header,payload=url.split(',',1);blob=base64.b64decode(payload);ext='jpg' if 'jpeg' in header else 'png'
        else:
            try:
                response=requests.get(url,timeout=10);response.raise_for_status();blob=response.content;ext='jpg' if blob.startswith(b'\xff\xd8') else 'png'
            except requests.RequestException:
                link=soup.new_tag('a',href=url);link.string='Original question image (source server currently unavailable)';img.replace_with(link);continue
        name=hashlib.sha256(blob).hexdigest()+'.'+ext
        (folder/name).write_bytes(blob)
        img['src']='/api/admin/oppe/assets/'+name
        img['alt']=img.get('alt') or 'Original question diagram'
    return markdownify(str(soup),heading_style='ATX').strip()

def convert(record):
    slug,exam=record['track'].split('/');notes=['Imported source content; hidden tests were not exposed in the source learner interface. Keep as DRAFT until real hidden tests and reference validation are added.']
    explanation='';raw='\n\n'.join(record['solution']);reference=raw
    if slug=='sc':
        blocks=re.findall(r'```(?:bash|sh|shell)?\s*\n([\s\S]*?)```',raw)
        if blocks:reference=blocks[0];explanation=raw
        else:notes.append('Reference solution was not fenced shell code; inspect it before execution.')
    tests=[]
    if record.get('testBlocks'):
        current=None
        for b in record['testBlocks']:
            label=b['label'].strip();text=b['text']
            if label=='Input':
                if current:tests.append(current)
                current=dict(input='' if text=='(none)' else text,expected='',hidden=False,files={},environment={},expected_files=[])
            elif current is not None:
                if label=='Expected':current['expected']=text
                elif label=='Environment':current['environment']=json.loads(text)
                if label=='Environment' and isinstance(current['environment'],list):current['environment']={v['key']:v['value'] for v in current['environment']}
                elif label.startswith('File: '):current['files'][label[6:]]='' if text=='(empty)' else text
                elif label=='Expected files':current['expected_files']=text.splitlines()
                else:notes.append('Unmapped case field: '+label)
        if current:tests.append(current)
    else:
        if len(record['tests'])%2:notes.append('Unpaired source test blocks: review required.')
        else:tests=[dict(input=record['tests'][i],expected=record['tests'][i+1],hidden=False,files={}) for i in range(0,len(record['tests']),2)]
    content=dict(title=record['title'],statement=statement(record['statementHtml']),topic=record.get('topic',''),category='OPPE1' if exam=='oppe1' else 'OPPE2',difficulty='Medium',starter_code=record['starter'],prefix='',suffix='',format='program',reference_solution=reference,explanation=explanation,source=record['url'],setup_sql='',time_limit=3,entrypoint='Main',execution_mode='stdin',entry_function='',entry_functions=[],comparison='text',tests=tests,import_notes=notes)
    if 'source server currently unavailable' in content['statement']:notes.append('Original external diagram could not be downloaded. Keep this question in DRAFT until the diagram is restored.')
    if slug=='java':
        names=re.findall(r'public\s+(?:final\s+|abstract\s+)?class\s+([A-Za-z_$][\w$]*)',reference)
        if len(names)==1:content['entrypoint']=names[0]
        else:notes.append('Could not determine a single public Java class; review entry class.')
    if slug=='python':
        try:
            tree=ast.parse(reference);functions=[n.name for n in tree.body if isinstance(n,ast.FunctionDef)]
            if tests:
                try:expected=ast.literal_eval(tests[0]['expected'])
                except (ValueError,SyntaxError):expected=None
                if isinstance(expected,tuple) and len(expected)==2 and isinstance(expected[1],list) and functions:
                    inp=decode(json.loads(tests[0]['input']));content['comparison']='python-value'
                    if isinstance(inp,list) and len(inp)==2 and isinstance(inp[0],str) and inp[0] in functions and isinstance(inp[1],list):
                        content.update(execution_mode='python-dispatch',entry_function=inp[0],entry_functions=functions)
                    else:content.update(execution_mode='python-call',entry_function=functions[-1])
        except (ValueError,SyntaxError,TypeError,KeyError) as e:notes.append('Function protocol needs review: '+str(e)[:150])
    if any(t.get('expected_files') for t in tests):notes.append('File-system result checker required. Stdout-only grading is disabled for this question.')
    if not explanation:
        content['explanation']='Imported reference code from the original site. A separate stepwise explanation has not yet been reviewed for this question.'
    return dict(external_id='rangalabs-question-'+record['id'],content=content)

def main():
    raw=json.loads((DATA/'source-questions-20261020.json').read_text());groups=collections.defaultdict(list)
    for record in raw.values():groups[record['track'].split('/')[0]].append(convert(record))
    all_bundles=[]
    for slug,rows in groups.items():
        rows.sort(key=lambda r:int(r['external_id'].split('-')[-1]))
        for i in range(0,len(rows),50):
            bundle=dict(format='mauryahub-oppe-v1',course_slug=slug,questions=rows[i:i+50]);all_bundles.append(bundle)
            (DATA/f'import-{slug}-{i//50+1}.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2))
    (DATA/'seed-bundles-20261020.json').write_text(json.dumps(all_bundles,ensure_ascii=False,separators=(',',':')))
    print(json.dumps({'questions':sum(len(r) for r in groups.values()),'courses':{k:len(v) for k,v in groups.items()},'modes':dict(collections.Counter(row['content']['execution_mode'] for rows in groups.values() for row in rows))},indent=2))
if __name__=='__main__':main()
