"""Apply source font emphasis only when a content slice maps unambiguously to PDF text.
Parsing and grading always use the original plain text; OCR contributes no ranges.
"""
import re

PROTECTED=re.compile(r'\[\[IMAGE:[^]]+\]\]|\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)')

def source_bold(value,layout,start=0,end=None):
    if not value or not layout.get('bold_ranges'):return value
    source=layout['text'];end=len(source) if end is None else end
    offset=source.find(value,start,end)
    if offset<0 or source.find(value,offset+1,end)>=0:return value
    protected=[m.span() for m in PROTECTED.finditer(value)]
    ranges=[]
    for a,b in layout['bold_ranges']:
        left=max(0,a-offset);right=min(len(value),b-offset)
        if left>=right:continue
        pieces=[(left,right)]
        for p,q in protected:
            pieces=[part for x,y in pieces for part in ((x,min(y,p)),(max(x,q),y)) if part[0]<part[1]]
        for x,y in pieces:
            raw=value[x:y];x+=len(raw)-len(raw.lstrip());y-=len(raw)-len(raw.rstrip())
            if x<y and '**' not in value[x:y]:ranges.append((x,y))
    merged=[]
    for a,b in sorted(ranges):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    for a,b in reversed(merged):value=value[:a]+'**'+value[a:b]+'**'+value[b:]
    return value
