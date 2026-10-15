import {it,expect,vi} from 'vitest';
import fs from 'node:fs';
const source=fs.readFileSync('public/study-ads.js','utf8');
it('makes no ad request without CMP or consent, then loads once after consent',()=>{
 document.body.innerHTML='<aside hidden id="study-ad" data-publisher="ca-pub-1234567890123456" data-slot="12345678"></aside>';
 let listener;window.__tcfapi=vi.fn((_,__,cb)=>{listener=cb});
 new Function(source)();
 listener({eventStatus:'tcloaded',purpose:{consents:{}},vendor:{consents:{}}},true);
 expect(document.querySelector('script')).toBeNull();
 const consent={eventStatus:'useractioncomplete',purpose:{consents:{1:true}},vendor:{consents:{755:true}}};
 listener(consent,true);listener(consent,true);
 expect(document.querySelectorAll('script')).toHaveLength(1);expect(document.getElementById('study-ad').hidden).toBe(false);
 document.querySelector('script').remove();delete window.__tcfapi;document.body.innerHTML='';
});
it('does not load Google when no CMP is installed',()=>{
 document.body.innerHTML='<aside hidden id="study-ad"></aside>';delete window.__tcfapi;new Function(source)();expect(document.querySelector('script')).toBeNull();document.body.innerHTML='';
});
