import {it,expect,vi} from 'vitest';import {mount,flushPromises} from '@vue/test-utils';import Records from '../src/Records.vue';
const mocks=vi.hoisted(()=>({api:vi.fn(),session:{},go:vi.fn()}));vi.mock('../src/api',()=>mocks);
it('colours outcomes and jumps to the correct review page',async()=>{
 const palette=['CORRECT','INCORRECT','PARTIAL','SKIPPED'].map((outcome,n)=>({question_id:n+1,number:String(n+1),state:outcome==='SKIPPED'?'NOT_VISITED':'ANSWERED',outcome,review_index:n===3?25:n}));
 mocks.api.mockImplementation(async path=>path==='/attempts/1'?{id:1,status:'SUBMITTED',palette,result:{score:2,total_marks:4,percentage:50}}:{items:[{question:{id:4,number:'4',text:'Fourth',options:[],images:[],answers:['A']},outcome:'SKIPPED',ai_solution:{available:false}}],total:26});
 const scroll=vi.fn();Element.prototype.scrollIntoView=scroll;
 const w=mount(Records,{props:{route:'/result/1'},attachTo:document.body});await flushPromises();
 expect(w.find('.result-correct').exists()).toBe(true);expect(w.find('.result-incorrect').exists()).toBe(true);expect(w.find('.result-partial').exists()).toBe(true);expect(w.find('.result-skipped').exists()).toBe(true);
 await w.get('.result-skipped').trigger('click');await flushPromises();
 expect(mocks.api).toHaveBeenCalledWith('/attempts/1/review?page=26&limit=1');expect(scroll).toHaveBeenCalledWith({behavior:'smooth',block:'start'});
 const count=mocks.api.mock.calls.length;await w.get('.result-skipped').trigger('click');await flushPromises();expect(mocks.api.mock.calls.length).toBe(count);w.unmount();delete Element.prototype.scrollIntoView;
});
