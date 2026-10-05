"""Free-tier opt-in adapters; no credentials or source URLs in diagnostics."""
import json
import os
import time
import urllib.parse
import requests
import re

class ProviderFailure(Exception):
    def __init__(self, code, detail):
        self.code, self.detail = code, detail
        super().__init__(detail)

def checked_response(response, provider):
    status = response.status_code
    if status >= 400:
        code = 'quota' if status == 429 else 'network' if status == 408 or status >= 500 else 'auth' if status in (401,403,404) else 'config'
        reason=''
        try:
            error=response.json().get('error',{})
            original=str(error.get('message',''))
            # Terminal only: redact secrets, URLs, embedded binary and payload echoes.
            if provider=='groq' and status==400:
                safe=original
                for name,value in os.environ.items():
                    if any(k in name for k in ('KEY','SECRET','PASSWORD')) and len(value)>6:safe=safe.replace(value,'[REDACTED]')
                safe=re.sub(r'https?://\S+|data:image/\S+|[A-Za-z0-9+/=]{100,}','[REDACTED]',safe)
                if any(k in safe.lower() for k in ('question data','messages','inlineData'.lower())):safe='Request payload rejected; message omitted because it echoes source data'
                print('Groq reason:',safe[:600].replace('\n',' '),flush=True)
            message=original.lower()
            for needle,label in [('json','JSON format rejected'),('image','Image input rejected'),('token','Token limit or budget rejected'),('model','Model unavailable or unsupported'),('permission','Model permission denied'),('parameter','Request parameter rejected')]:
                if needle in message:reason=' '+label;break
        except (ValueError,AttributeError,TypeError):pass
        raise ProviderFailure(code, provider + '_request HTTP ' + str(status)+reason)
    return response.json()

def parse_output(text):
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = text.split('\n',1)[1].rsplit('```',1)[0].strip()
    data = json.loads(text)
    if not isinstance(data,dict) or not all(k in data for k in ('final_answer','explanation','option_explanations','needs_review')):
        raise ValueError('Missing solution fields')
    if not isinstance(data['explanation'],str) or not data['explanation'].strip() or not isinstance(data['option_explanations'],dict) or not isinstance(data['needs_review'],bool):
        raise ValueError('Invalid solution fields')
    return data

class Providers:
    def __init__(self, schema):
        self.schema = schema
        self.cooldown = {}
        self.order = [p.strip() for p in os.getenv('AI_PROVIDER_ORDER','groq,gemini,antigravity,openrouter').split(',') if p.strip()]
        if any(p not in ('groq','gemini','antigravity','openrouter') for p in self.order):
            raise SystemExit('Invalid AI_PROVIDER_ORDER')
        self.config = {}
        google_key = os.getenv('GEMINI_API_KEY','').strip()
        if google_key and os.getenv('GEMINI_FREE_TIER_CONFIRMED','').lower() == 'yes':
            if os.getenv('GEMINI_MODEL','').strip():self.config['gemini']=(google_key,os.environ['GEMINI_MODEL'].strip())
            if os.getenv('ANTIGRAVITY_ENABLED','no').lower()=='yes':self.config['antigravity']=(google_key,os.getenv('ANTIGRAVITY_AGENT','antigravity-preview-09-2026'))
        if os.getenv('GROQ_API_KEY') and os.getenv('GROQ_FREE_TIER_CONFIRMED','').lower()=='yes':
            self.config['groq']=(os.environ['GROQ_API_KEY'],os.getenv('GROQ_MODEL','openai/gpt-oss-120b'))
        if os.getenv('OPENROUTER_API_KEY'):
            model=os.getenv('OPENROUTER_MODEL','openrouter/free').strip()
            if model!='openrouter/free' and not model.endswith(':free'):raise SystemExit('OpenRouter model must be openrouter/free or end in :free; paid models disabled.')
            self.config['openrouter']=(os.environ['OPENROUTER_API_KEY'],model)
        if not any(p in self.config for p in self.order):raise SystemExit('Configure at least one provider key and its free-tier confirmation in local.env.')

    def generate(self, parts):
        failures=[]
        deadline=time.monotonic()+420
        for provider in self.order:
            if provider not in self.config or self.cooldown.get(provider,0)>time.monotonic():continue
            if time.monotonic()>deadline-20:break
            key,model=self.config[provider]
            images=[p['inlineData'] for p in parts if 'inlineData' in p]
            if provider=='groq' and images:
                model=os.getenv('GROQ_VISION_MODEL','qwen/qwen3.8-27b')
                # Verified default has a three-image limit. Never drop source images.
                if model!='qwen/qwen3.8-27b' or len(images)>3:
                    failures.append(ProviderFailure('config','groq skipped unsupported image configuration'));continue
            try:
                budget=min(90,max(10,int(deadline-time.monotonic()-10)))
                output=self.request(provider,key,model,parts,budget)
                return {'provider':provider,'model':model,'output':output}
            except ProviderFailure as e:
                failures.append(e)
                self.cooldown[provider]=time.monotonic()+(900 if e.code=='quota' else 86400 if e.code in ('auth','config') else 60)
                print('Fallback:',e.detail,flush=True)
            except requests.RequestException as e:
                failure=ProviderFailure('network',provider+'_request '+type(e).__name__)
                failures.append(failure);self.cooldown[provider]=time.monotonic()+60
                print('Fallback:',failure.detail,flush=True)
            except (ValueError,KeyError,IndexError,TypeError):
                failure=ProviderFailure('invalid',provider+'_response invalid or incomplete JSON')
                failures.append(failure);self.cooldown[provider]=time.monotonic()+60
                print('Fallback:',failure.detail,flush=True)
        # All configured providers exhausted: preserve queued job and pause batch.
        if not failures:raise ProviderFailure('quota','All compatible providers cooling down; resume later')
        if len(self.config)==1 and len(failures)==1:raise failures[0]
        raise ProviderFailure('quota','All compatible providers unavailable; see worker terminal')

    def request(self, provider, key, model, parts, budget):
        google='https://generativelanguage.googleapis.com/v1beta/'
        if provider=='groq':
            images=[p['inlineData'] for p in parts if 'inlineData' in p]
            print('Groq request model='+model+' images='+str(len(images))+' image_bytes='+str([len(i['data'])*3//4 for i in images]),flush=True)
        prompt=parts[0]['text']+'\nRequired JSON schema: '+json.dumps(self.schema)
        if provider=='gemini':
            r=requests.post(google+'models/'+urllib.parse.quote(model,safe='')+':generateContent',headers={'x-goog-api-key':key},json={'contents':[{'parts':parts}],'generationConfig':{'responseMimeType':'application/json','responseJsonSchema':self.schema,'maxOutputTokens':4096}},timeout=(10,budget))
            data=checked_response(r,provider);candidate=data['candidates'][0]
            if candidate.get('finishReason','STOP')!='STOP':raise ValueError('Incomplete candidate')
            text=''.join(p.get('text','') for p in candidate['content']['parts'] if not p.get('thought'))
        elif provider=='antigravity':
            content=[{'type':'text','text':prompt}]+[{'type':'image','data':p['inlineData']['data'],'mime_type':p['inlineData']['mimeType']} for p in parts if 'inlineData' in p]
            r=requests.post(google+'interactions',headers={'x-goog-api-key':key,'Api-Revision':'2026-05-20'},json={'agent':model,'input':content,'tools':[],'agent_config':{'type':'antigravity','max_total_tokens':12000}},timeout=(10,budget))
            data=checked_response(r,provider)
            if data.get('status') not in (None,'completed'):raise ValueError('Incomplete interaction')
            text=data.get('output_text') or ''.join(p.get('text','') for p in data.get('outputs',[]) if p.get('type')=='text')
        else:
            content=[{'type':'text','text':prompt}]+[{'type':'image_url','image_url':{'url':'data:'+p['inlineData']['mimeType']+';base64,'+p['inlineData']['data']}} for p in parts if 'inlineData' in p]
            body={'model':model,'messages':[{'role':'user','content':content}],'response_format':{'type':'json_object'}}
            body['max_completion_tokens' if provider=='groq' else 'max_tokens']=4096
            if provider=='openrouter':body['provider']={'max_price':{'prompt':0,'completion':0}}
            endpoint='https://api.groq.com/openai/v1/chat/completions' if provider=='groq' else 'https://openrouter.ai/api/v1/chat/completions'
            r=requests.post(endpoint,headers={'Authorization':'Bearer '+key},json=body,timeout=(10,budget))
            data=checked_response(r,provider);choice=data['choices'][0]
            if choice.get('finish_reason','stop')!='stop':raise ProviderFailure('invalid',provider+'_response finish reason '+('length' if choice.get('finish_reason')=='length' else 'non-stop'))
            text=choice['message']['content']
        try:return parse_output(text)
        except json.JSONDecodeError:raise ProviderFailure('invalid',provider+'_response malformed JSON')
        except (ValueError,AttributeError,TypeError):raise ProviderFailure('invalid',provider+'_response missing or invalid solution fields')
