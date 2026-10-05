"""Two small Groq checks. Does not log in to PYQ or claim jobs."""
import os,json,base64,io,re
from pathlib import Path
import requests
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('local.env'))
def safe_error(data,key):
    error=data.get('error',{})
    message=str(error.get('message','No error message'))
    for value in [key]+[v for k,v in os.environ.items() if ('KEY' in k or 'SECRET' in k or 'PASSWORD' in k) and len(v)>6]:message=message.replace(value,'[REDACTED]')
    message=re.sub(r'https?://\S+|data:image/\S+','[URL REDACTED]',message)
    return message[:600].replace('\n',' ')
def main():
    key=os.getenv('GROQ_API_KEY','')
    if not key:raise SystemExit('Set GROQ_API_KEY in local.env')
    if os.getenv('GROQ_FREE_TIER_CONFIRMED','').lower()!='yes':raise SystemExit('Confirm Groq free account in local.env first')
    # Valid 32x32 RGB PNG made without an extra dependency.
    import struct,zlib
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',32,32,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\xff\xff\xff'*32)*32))+chunk(b'IEND',b'')
    for image in (False,True):
        model=os.getenv('GROQ_VISION_MODEL','qwen/qwen3.8-27b') if image else os.getenv('GROQ_MODEL','openai/gpt-oss-120b')
        content=[{'type':'text','text':'Return only a JSON object with one field ok set to true.'}]
        if image:content.append({'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(png).decode()}})
        print(('IMAGE' if image else 'TEXT')+' check model='+model,flush=True)
        try:
            r=requests.post('https://api.groq.com/openai/v1/chat/completions',headers={'Authorization':'Bearer '+key},json={'model':model,'messages':[{'role':'user','content':content}],'response_format':{'type':'json_object'},'max_completion_tokens':512},timeout=(10,60))
            data=r.json();print('HTTP',r.status_code)
            if r.status_code>=400:print('Reason:',safe_error(data,key))
            else:
                c=data['choices'][0];print('finish_reason='+str(c.get('finish_reason')))
                try:print('Valid JSON:',isinstance(json.loads(c['message']['content']),dict))
                except (ValueError,TypeError):print('Valid JSON: False')
        except requests.RequestException as e:print('Connection error:',type(e).__name__)
        except (ValueError,KeyError,IndexError,TypeError):print('Unexpected API response structure')
    print('Finished. These checks use two API requests. No PYQ jobs changed.')
if __name__=='__main__':main()
