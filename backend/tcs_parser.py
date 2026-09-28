"""TCS-style export adapter, based on the inspected source PDF.
Cross-page segmentation preserves original option identifiers. No color-derived
answer is accepted automatically: all extracted keys require review.
"""
import re
from .providers import ExtractedQuestion,ExtractedOption

def parse_tcs(doc):
    texts=[p.get_text('text') for p in doc];combined='\n'.join(texts)
    pattern=r'Question Number\s*:\s*(\d+)\s+Question Id\s*:\s*(\d+)\s+Question Type\s*:\s*(\w+)'
    matches=list(re.finditer(pattern,combined))
    if not matches:return []
    # Only interpret green IDs when the document explicitly declares that convention.
    declared='Options shown in green color' in combined and 'are correct' in combined
    colored={}
    if declared:
        for page in doc:
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines',[]):
                    for span in line['spans']:
                        m=re.match(r'\s*(\d{8,})\.',span['text'])
                        if m and span['color']==0x008000:colored[m[1]]=True
    negatives=re.search(r'Section Negative Marks\s*:\s*(\d+(?:\.\d+)?)',combined)
    groups=[]
    for group in re.finditer(r'Question Numbers\s*:\s*\((\d+) to (\d+)\).*?Question Label\s*:\s*Comprehension\s*\n(.*?)Sub questions',combined,re.S):
        groups.append((int(group[1]),int(group[2]),group[3].strip()))
    output=[]
    offsets=[];offset=0
    for text in texts:offsets.append(offset);offset+=len(text)+1
    for i,m in enumerate(matches):
        chunk=combined[m.end():matches[i+1].start() if i+1<len(matches) else len(combined)]
        marks=re.search(r'Correct Marks\s*:\s*(\d+(?:\.\d+)?)',chunk)
        label=re.search(r'Question Label\s*:[^\n]*\n',chunk)
        if not label:continue
        body=chunk[label.end():]
        body=re.split(r'\n\s*(?:Sub-Section Number|Question Id)\s*:',body)[0]
        parts=re.split(r'Options\s*:',body,maxsplit=1)
        stem=parts[0].strip();options=[]
        for lo,hi,passage in groups:
            if lo<=int(m[1])<=hi:stem=passage+'\n\n'+stem
        if len(parts)>1:
            option_matches=list(re.finditer(r'(?m)^\s*(\d{8,})\.\s*',parts[1]))
            for n,o in enumerate(option_matches):
                value=parts[1][o.end():option_matches[n+1].start() if n+1<len(option_matches) else len(parts[1])].strip()
                options.append(ExtractedOption(key=o[1],text=value or '[Image-only option: source review required]'))
        answers=[o.key for o in options if o.key in colored] or None
        kind=m[3].upper();kind=kind if kind in ('MCQ','MSQ','NAT') else 'SUBJECTIVE'
        page=next((n for n in range(len(offsets)-1,-1,-1) if offsets[n]<=m.start()),0)+1
        warnings=['Verify all text and diagrams against source; image-only formulae may be missing']
        if answers:warnings.append('Answer extracted from explicitly declared green option-ID convention; verify visually')
        if marks and float(marks[1])==0:warnings.append('Zero-mark item may be an administrative instruction; reject when not a practice question')
        output.append((page,ExtractedQuestion(number=m[1],kind=kind,text=stem,options=options,answers=answers,marks=float(marks[1]) if marks else None,negative_marks=float(negatives[1]) if negatives else None,confidence=.7,warnings=warnings)))
    return output
