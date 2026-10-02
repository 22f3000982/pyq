from pathlib import Path
import re,hashlib,json
from .numeric import parse_numeric_key
from .text_format import source_bold

Q_PATTERN=r'Question\s+Number\s*:\s*(\d+)\s+Question\s+Id\s*:\s*(\d+)(?:\s+Question\s+Type\s*:\s*([\w/-]+))?'
MARKER=r'\[\[IMAGE:([^]]+)\]\]'

def source_metadata(text):
    declarations=[]
    for kind,pattern in [('questions',r'(?:Total\s+(?:Number\s+of\s+)?Questions|Number of Questions)\s*:\s*(\d+)'),('marks',r'(?:Total Marks|Section Marks)\s*:\s*(\d+(?:\.\d+)?)'),('duration',r'(?:Test Duration|Exam Duration|Total Duration|Maximum Duration|Duration)\s*(?:\(?(?:Minutes|mins?)\)?)?\s*:\s*(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)?')]:
        for m in re.finditer(pattern,text,re.I):declarations.append({'kind':kind,'raw':m[0],'value':float(m[1]),'offset':m.start(),'unit':m[2] if kind=='duration' else None})
    durations=[d for d in declarations if d['kind']=='duration' and d['value']>0]
    seconds=None
    if durations:
        d=durations[0];seconds=int(d['value']*(3600 if (d.get('unit') or '').lower().startswith(('hour','hr')) else 60))
    return {'declarations':declarations,'declared_total_questions':next((int(d['value']) for d in declarations if d['kind']=='questions'),None),'declared_total_marks':next((d['value'] for d in declarations if d['kind']=='marks'),None),'duration_seconds':seconds}

def clean_assets(text,layout,option_key=None):
    images=[]
    def sub(m):
        asset=layout['assets'].get(m[1])
        if asset:images.append({**asset,'option_key':option_key})
        return m[0] if asset else ''
    return re.sub(MARKER,sub,text).strip(),images

def parse_document(layout):
    text=layout['text'];matches=list(re.finditer(Q_PATTERN,text,re.I));questions=[];issues=[];meta=source_metadata(text)
    groups=[]
    for g in re.finditer(r'Question Numbers\s*:\s*\((\d+)\s*to\s*(\d+)\).*?Question Label\s*:\s*Comprehension\s*\n(.*?)Sub questions',text,re.S|re.I):groups.append((int(g[1]),int(g[2]),g[3],g.start()))
    for i,m in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(text)
        chunk=text[m.end():end];number,qid,kind=m[1],m[2],(m[3] or '').upper();warnings=[];images=[];evidence={'source_question_id':qid,'answer_indicators':{},'method':'tcs_layout'}
        chunk=re.split(r'\n\s*(?:Sub-Section Number|Question Id)\s*:',chunk)[0]
        mark=re.search(r'Correct Marks\s*:\s*([\d.]+)',chunk,re.I)
        wrong=re.search(r'(?:Wrong|Negative|Incorrect) Marks\s*:\s*([\d.]+)',chunk,re.I)
        if not wrong:
            preceding=list(re.finditer(r'Section Negative Marks\s*:\s*([\d.]+)',text[:m.start()],re.I));wrong=preceding[-1] if preceding else None
        label=re.search(r'Question Label\s*:[^\n]*\n',chunk,re.I)
        if not label:
            issues.append({'number':number,'error':'Question label/boundary not recognized'});continue
        if not kind:
            # Some official TCS exports omit Question Type but retain Question Label.
            label_text=label[0].split(':',1)[1].strip().casefold()
            if 'multiple choice' in label_text:kind='MCQ'
            elif 'multiple select' in label_text or 'multiple response' in label_text:kind='MSQ'
            elif 'short answer' in label_text or re.search(r'Possible Answers?\s*:',chunk,re.I):kind='SA'
            elif 'true' in label_text and 'false' in label_text:kind='TRUE_FALSE'
            else:kind='SUBJECTIVE'
        body=chunk[label.end():];parts=re.split(r'Options\s*:',body,maxsplit=1,flags=re.I)
        stem=parts[0];options=[];answers=None;source_pages={pn for start,stop,pn in layout['pages'] if start<end and stop>m.start()}
        shared=None
        for lo,hi,passage,groupstart in groups:
            if lo<=int(number)<=hi:
                subquestion=stem.strip()
                stem=passage+'\n\n'+stem;source_pages|={pn for start,stop,pn in layout['pages'] if start<=groupstart<=stop}
                shared=(passage,groupstart)
                evidence['shared_passage']=True
                evidence['shared_passage_text']=passage.strip()
                evidence['subquestion_text']=subquestion
        if len(parts)>1:
            opts=list(re.finditer(r'(?m)^\s*(\d{7,})\.\s*',parts[1]))
            for n,o in enumerate(opts):
                raw=parts[1][o.end():opts[n+1].start() if n+1<len(opts) else len(parts[1])]
                raw=re.split(r'(?im)^\s*(?:Correct Answer|Answer Key|Possible Answers?)\s*:',raw)[0]
                value,assets=clean_assets(source_bold(raw,layout,m.end(),end),layout,o[1]);images.extend(assets)
                options.append({'key':o[1],'text':value})
            greens=[];reds=[]
            for o in options:
                indicators=layout['indicators'].get(o['key'],[]);colors={x['kind'] for x in indicators};evidence['answer_indicators'][o['key']]=indicators
                if 'green' in colors and 'red' in colors:warnings.append('CONFLICTING_ANSWER_INDICATOR:'+o['key'])
                elif 'green' in colors:greens.append(o['key'])
                elif 'red' in colors:reds.append(o['key'])
            if greens and not any('CONFLICTING' in w for w in warnings):answers=greens;evidence['answer_source']='green_visual_indicator'
            # Red-only options never imply the remaining option is correct.
            if not answers:
                key=re.search(r'(?:Correct Answer|Answer Key)\s*:\s*([\d,; ]+)',body,re.I)
                if key:
                    values=re.findall(r'\d{7,}',key[1])
                    if values and set(values)<={o['key'] for o in options} and not set(values)&set(reds):answers=values;evidence['answer_source']='explicit_key'
        if kind in ('SA','NAT','INTEGER','NUMERICAL','NUMERIC') or re.search(r'Possible Answers?\s*:',body,re.I):
            alpha=bool(re.search(r'Response Type\s*:\s*Alphanumeric',body,re.I))
            kind='SHORT_TEXT' if alpha else 'NAT'
            key=re.search(r'(?:Possible Answers?|Correct Answer|Answer)\s*:[ \t]*\n?(.*)',body,re.I|re.S)
            if key:
                raw=key[1].strip();values=[line.strip() for line in raw.splitlines() if line.strip()]
                evidence['raw_answer']=raw
                if alpha and values and not any('[[IMAGE:' in v for v in values):
                    case=re.search(r'Answers Case Sensitive\s*:\s*(Yes|No)',body,re.I)
                    answers={'kind':'text_values','raw':raw,'values':values,'case_sensitive':not case or case[1].lower()=='yes'}
                    evidence['answer_source']='explicit_text_key'
                elif not alpha:
                    try:
                        keys=[parse_numeric_key(v) for v in values]
                        if not keys:raise ValueError('Missing key')
                        answers=keys[0] if len(keys)==1 else {'kind':'alternatives','raw':raw,'keys':keys}
                        evidence['answer_source']='explicit_numeric_key'
                    except ValueError:warnings.append('UNPARSED_NUMERIC_KEY:'+raw)
            elif alpha:kind='SUBJECTIVE'
            stem=re.split(r'(?:Response Type|Evaluation Required For SA|Possible Answers?|Correct Answer|Answer)\s*:',stem,flags=re.I)[0]
        elif kind in ('MCQ','MSQ'):pass
        elif kind in ('TF','TRUEFALSE','TRUE_FALSE'):kind='TRUE_FALSE'
        elif kind in ('PROGRAMMING','CODE'):kind='CODE'
        else:kind='SUBJECTIVE'
        stem,assets=clean_assets(stem,layout);images.extend(assets)
        # Prevent printed keys leaking into stems/options.
        stem=re.split(r'(?im)^\s*(?:Correct Answer|Answer Key|Possible Answers?)\s*:',stem)[0].strip()
        if shared:
            passage,groupstart=shared
            formatted=source_bold(passage.strip(),layout,groupstart,m.start())
            # Use the cleaned stem to avoid reintroducing numeric-answer metadata.
            plain_sub=stem[len(passage.strip()):].strip() if stem.startswith(passage.strip()) else stem
            subquestion=source_bold(plain_sub,layout,m.end(),end)
            stem=formatted+'\n\n'+subquestion
            evidence['shared_passage_text']=formatted;evidence['subquestion_text']=subquestion
        else:stem=source_bold(stem,layout,m.end(),end)
        evidence['layout_assets']={Path(a['path']).stem:{k:a[k] for k in ('inline','width','height') if k in a} for a in images}
        marks=float(mark[1]) if mark else None;negative=float(wrong[1]) if wrong else None
        state='AVAILABLE'
        if '[[PAGE_FAILED:' in chunk or '[[PAGE_FAILED:' in stem:
            warnings.append('SOURCE_PAGE_EXTRACTION_FAILED');state='EXTRACTION_FAILED'
            stem=re.sub(r'\[\[PAGE_FAILED:\d+\]\]','',stem)
        if marks==0 and re.search(r'(HALL TICKET|ARE YOU SURE|THIS IS QUESTION PAPER)',stem,re.I):state='INSTRUCTION'
        if not stem and not any(not a['option_key'] for a in images):warnings.append('MISSING_STEM');state='EXTRACTION_FAILED'
        if kind in ('MCQ','MSQ','TRUE_FALSE'):
            if len(options)<2:warnings.append('MISSING_OPTIONS');state='EXTRACTION_FAILED'
            if any(not o['text'] and not any(a['option_key']==o['key'] for a in images) for o in options):warnings.append('EMPTY_OPTION');state='EXTRACTION_FAILED'
            if kind!='MSQ' and answers and len(answers)!=1:warnings.append('MULTIPLE_KEYS_FOR_SINGLE_CHOICE');answers=None
        if any('CONFLICTING' in w for w in warnings):answers=None
        if not answers and answers!=0:warnings.append('ANSWER_UNAVAILABLE')
        if marks is None:warnings.append('MARKS_UNAVAILABLE')
        if negative is None:warnings.append('NEGATIVE_MARKS_UNAVAILABLE')
        if any('OCR' in w for w in layout['warnings']):warnings.append('OCR_DERIVED_TEXT')
        questions.append({'number':number,'kind':kind,'text':stem,'options':options,'answers':answers,'marks':marks,'negative_marks':negative,'explanation':None,'source_pages':sorted(source_pages|{a['page'] for a in images}),'images':images,'status':state,'confidence':.9 if not warnings else .65,'warnings':warnings,'evidence':evidence})
    return questions,meta,issues
