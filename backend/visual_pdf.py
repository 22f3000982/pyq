"""Source layout, embedded diagrams and answer-indicator evidence.
Green/red indicators are consumed during ingestion, never exposed in student assets.
"""
import io,re,hashlib,subprocess,tempfile,shutil
from pathlib import Path
import fitz
from PIL import Image
import numpy as np

def color_kind(color):
    r=(color>>16)&255;g=(color>>8)&255;b=color&255
    if g>45 and g>r*1.3 and g>b*1.2:return 'green'
    if r>65 and r>g*1.4 and r>b*1.3:return 'red'
    return None

def pixels_kind(data):
    a=np.asarray(Image.open(io.BytesIO(data)).convert('RGB'),dtype=np.float32)
    r,g,b=a[:,:,0],a[:,:,1],a[:,:,2]
    green=(g>55)&(g>r*1.35)&(g>b*1.2);red=(r>80)&(r>g*1.45)&(r>b*1.35)
    ng,nr=int(green.sum()),int(red.sum())
    if ng>=4 and ng>nr*3:return 'green'
    if nr>=4 and nr>ng*3:return 'red'
    return None

def join_items(items,bold_ranges=None):
    result='';end=None
    for item in sorted(items,key=lambda item:item[0]):
        x,text,right,*style=item
        if result and end is not None and x-end>1 and not result[-1].isspace() and not text[:1].isspace():result+=' '
        start=len(result)
        result+=text;end=right
        if bold_ranges is not None and style and style[0] and text.strip():
            left=start+len(text)-len(text.lstrip());right=len(result.rstrip())
            bold_ranges.append((left,right))
    return result

def layout_document(doc,asset_dir,sha,ocr=True):
    texts=[];spans=[];assets={};indicators={};warnings=[];page_ranges=[];offset=0;bold_ranges=[]
    for pn,page in enumerate(doc,1):
        try:
            data=page.get_text('dict');lines=[];images=[];ids=[]
            for block in data['blocks']:
                if block['type']==1:images.append(block);continue
                for line in block.get('lines',[]):
                    items=[]
                    for span in line['spans']:
                        text=span['text'];bbox=fitz.Rect(span['bbox'])
                        if span['flags']&1 and text.strip():text=r'\(^{'+text+r'}\)'
                        items.append((bbox.x0,text,bbox.x1,bool(span['flags']&16 or re.search(r'(?:bold|demi|semibold|black)',span.get('font',''),re.I))))
                        key=re.match(r'\s*(\d{7,})\.\s*',text)
                        if key:
                            ids.append((key[1],bbox))
                            kind=color_kind(span['color'])
                            if kind:indicators.setdefault(key[1],[]).append({'kind':kind,'method':'pdf_text_color','color':hex(span['color']),'page':pn})
                        spans.append({'text':text,'bbox':list(bbox),'page':pn,'color':span['color']})
                    lines.append({'bbox':fitz.Rect(line['bbox']),'items':items})
            # PDF option content may begin above the coloured ID (superscripts or tall images).
            # Bind by the shared visual baseline before linearizing reading order.
            option_lines={key:next((l for l in lines if any(re.match(r'\s*'+key+r'\.',t) for _,t,*_ in l['items'])),None) for key,_ in ids}
            for line in list(lines):
                rect=line['bbox']
                near=next((key for key,b in ids if rect.x0>=b.x1 and abs(rect.y1-b.y1)<3),None)
                target=option_lines.get(near)
                if target is not None and line is not target:
                    target['items'].extend(line['items']);lines.remove(line)
            # Join fragments on the same visual baseline before inserting inline notation.
            # PDF exporters often split 'text [formula] text' into separate lines.
            merged=[]
            for line in sorted(lines,key=lambda l:(l['bbox'].y1,l['bbox'].x0)):
                target=next((other for other in merged if abs(other['bbox'].y1-line['bbox'].y1)<2),None)
                if target is not None:
                    target['items'].extend(line['items']);target['bbox']|=line['bbox']
                else:merged.append(line)
            lines=merged
            option_lines={key:next((l for l in lines if any(re.match(r'\s*'+key+r'\.',t) for _,t,*_ in l['items'])),None) for key,_ in ids}
            for im in images:
                rect=fitz.Rect(im['bbox']);near=next(((key,b) for key,b in ids if abs((b.y0+b.y1-rect.y0-rect.y1)/2)<12 and b.x1-4<=rect.x0<=b.x1+25 and rect.width<=20 and rect.height<=20),None)
                indicator=pixels_kind(im['image']) if near else None
                if indicator:
                    indicators.setdefault(near[0],[]).append({'kind':indicator,'method':'embedded_indicator_pixels','page':pn});continue
                # Keep diagrams and inline math, including small monochrome glyph images.
                token=f'{sha[:16]}_{pn}_{len(assets)}';path=token+'.png'
                Image.open(io.BytesIO(im['image'])).convert('RGBA').save(Path(asset_dir)/path)
                assets[token]={'path':path,'page':pn,'bbox':list(rect),'width':rect.width/11,'height':rect.height/11}
                marker=' [[IMAGE:'+token+']] '
                option_target=next((option_lines[key] for key,b in ids if rect.x0>=b.x1 and abs(rect.y1-b.y1)<6),None)
                target=option_target or next((line for line in lines if abs((line['bbox'].y0+line['bbox'].y1-rect.y0-rect.y1)/2)<max(5,rect.height*.5) and rect.height<35),None)
                assets[token]['inline']=target is not None
                if target:target['items'].append((rect.x0,marker,rect.x1))
                else:lines.append({'bbox':rect,'items':[(rect.x0,marker,rect.x1)]})
            # Detect colored drawn/highlight marks around option IDs even without colored text.
            for key,bbox in ids:
                clip=fitz.Rect(bbox.x0-2,bbox.y0+bbox.height*.25,min(page.rect.width,bbox.x1+18),bbox.y1-bbox.height*.25)&page.rect
                if clip.is_empty:continue
                detected=pixels_kind(page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),clip=clip).tobytes('png'))
                if detected:indicators.setdefault(key,[]).append({'kind':detected,'method':'rendered_option_marker_pixels','page':pn})
            # Vector-only figures must not silently disappear. Crop vector-only blocks away from markers.
            # Embedded image extraction handles the inspected exam exports. Unsupported vectors are logged.
            if page.get_drawings() and not images:warnings.append(f'Page {pn}: vector graphics present; text/layout parser may not recover every figure')
            page_bold=[];pieces=[];line_offset=0
            for line in sorted(lines,key=lambda l:(round(l['bbox'].y0,1),l['bbox'].x0)):
                ranges=[];piece=join_items(line['items'],ranges)
                page_bold.extend((line_offset+a,line_offset+b) for a,b in ranges)
                pieces.append(piece);line_offset+=len(piece)+1
            text='\n'.join(pieces)
            if len(re.sub(r'\[\[IMAGE:[^]]+\]\]','',text).strip())<30:
                page_bold=[]
                if not ocr or not shutil.which('tesseract'):
                    warnings.append(f'Page {pn}: OCR unavailable');text=f'[[PAGE_FAILED:{pn}]]'
                else:
                    # OCR provides searchable text and word boxes for scanned answer indicators.
                    pix=page.get_pixmap(matrix=fitz.Matrix(2,2))
                    with tempfile.TemporaryDirectory() as td:
                        src=Path(td)/'page.png';pix.save(src)
                        r=subprocess.run(['tesseract',str(src),'stdout','-l','eng'],capture_output=True,text=True,timeout=60,check=True)
                        text=r.stdout
                        # For scans, inspect colored option-number lines from OCR boxes.
                        tsv=subprocess.run(['tesseract',str(src),'stdout','-l','eng','tsv'],capture_output=True,text=True,timeout=60,check=True).stdout
                        import csv
                        for word in csv.DictReader(tsv.splitlines(),delimiter='\t'):
                            key=re.fullmatch(r'(\d{7,})\.?',word.get('text','').strip())
                            if key:
                                x,y,w,h=[int(word[k]) for k in ('left','top','width','height')]
                                clip=fitz.Rect(max(0,x/2-2),max(0,y/2-2),min(page.rect.width,(x+w)/2+18),min(page.rect.height,(y+h)/2+2))
                                detected=pixels_kind(page.get_pixmap(matrix=fitz.Matrix(2,2),clip=clip).tobytes('png'))
                                if detected:indicators.setdefault(key[1],[]).append({'kind':detected,'method':'ocr_marker_pixels','page':pn})
                    warnings.append(f'Page {pn}: OCR used; confidence reduced')
        except Exception as e:
            page_bold=[]
            warnings.append(f'Page {pn}: extraction failed: {type(e).__name__}: {str(e)[:250]}');text=f'[[PAGE_FAILED:{pn}]]'
        bold_ranges.extend((offset+a,offset+b) for a,b in page_bold)
        texts.append(text);page_ranges.append((offset,offset+len(text),pn));offset+=len(text)+1
    return {'text':'\n'.join(texts),'pages':page_ranges,'assets':assets,'indicators':indicators,'warnings':warnings,'bold_ranges':bold_ranges}
