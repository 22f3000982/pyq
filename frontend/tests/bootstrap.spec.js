import {it,expect,vi,afterEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import {api,session} from '../src/api';
import QuestionContent from '../src/QuestionContent.vue';
afterEach(()=>vi.unstubAllGlobals());
it('reuses the just-created combined attempt without another HTTP request',async()=>{
 session.user={id:7};
 const fetch=vi.fn(async()=>({ok:true,json:async()=>({id:90,items:[],server_time:10})}));vi.stubGlobal('fetch',fetch);
 await api('/attempts',{method:'POST',body:{paper_id:1,mode:'exam'}});
 expect(fetch.mock.calls[0][0]).toBe('/api/attempts?bootstrap=1');
 const a=await api('/attempts/90?bootstrap=1');expect(a.id).toBe(90);expect(fetch).toHaveBeenCalledTimes(1);
 await api('/attempts/90?bootstrap=1');expect(fetch).toHaveBeenCalledTimes(2);
});
it('does not reuse another user bootstrap',async()=>{
 session.user={id:8};const fetch=vi.fn(async()=>({ok:true,json:async()=>({id:91,items:[]})}));vi.stubGlobal('fetch',fetch);
 await api('/attempts',{method:'POST',body:{paper_id:1}});session.user={id:9};
 await api('/attempts/91?bootstrap=1');expect(fetch).toHaveBeenCalledTimes(2);
});
it('refreshes an expired signed image through the authenticated redirect once',async()=>{
 const w=mount(QuestionContent,{props:{text:'[[IMAGE:x]]',images:[{id:5,token:'x',url:'https://r2.example.test/signed'}]}});
 await w.get('img').trigger('error');expect(w.get('img').attributes('src')).toBe('/api/images/5');
 await w.get('img').trigger('error');expect(w.text()).toContain('Source diagram or notation unavailable');w.unmount();
});
