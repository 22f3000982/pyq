import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';import Exam from '../src/Exam.vue';
const mocks=vi.hoisted(()=>({api:vi.fn(),go:vi.fn(),session:{user:{name:'Student'}}}));vi.mock('../src/api',()=>({...mocks,api:async(path,o)=>{if(path.endsWith('?bootstrap=1')){const base=path.split('?')[0];return {...await mocks.api(base,o),...await mocks.api(base+'/questions')}}return mocks.api(path,o)}}));
let stored,attempt;
beforeEach(()=>{vi.useFakeTimers();sessionStorage.clear();stored={1:null,2:null};attempt={id:1,title:'NAT paper',mode:'exam',status:'ACTIVE',deadline:Date.now()/1000+90,server_time:Date.now()/1000,palette:[{question_id:1,number:'1',state:'NOT_VISITED'},{question_id:2,number:'2',state:'NOT_VISITED'}]};mocks.go.mockReset();mocks.api.mockImplementation(async(path,options)=>{if(path==='/attempts/1')return {...attempt};if(path==='/attempts/1/questions')return {status:'ACTIVE',items:[1,2].map(id=>({status:'ACTIVE',answer:stored[id],question:{id,number:String(id),kind:'NAT',text:'Enter a number',marks:1,options:[],images:[]}}))};if(path.includes('/questions/')){const id=Number(path.split('/').at(-1));return {status:'ACTIVE',answer:stored[id],question:{id,number:String(id),kind:'NAT',text:'Enter a number',marks:1,options:[],images:[]}}}if(path.endsWith('/answers')){if('answer' in options.body)stored[options.body.question_id]=options.body.answer;return {state:stored[options.body.question_id]?'ANSWERED':'VISITED'}}return {id:2}})});
afterEach(()=>{vi.useRealTimers()});
describe('NAT drafts in timed exams',()=>{
 it('survives timer ticks and metadata polling while focused, and autosaves',async()=>{
  const w=mount(Exam,{props:{id:1}});await flushPromises();const input=w.get('input.numeric-answer');
  await input.setValue('-12.5');await vi.advanceTimersByTimeAsync(1000);await flushPromises();expect(input.element.value).toBe('-12.5');expect(stored[1]).toBe('-12.5');
  await vi.advanceTimersByTimeAsync(15000);await flushPromises();expect(input.element.value).toBe('-12.5');w.unmount();
 });
 it('flushes a fraction before navigation, restores it on return and saves zero',async()=>{
  const w=mount(Exam,{props:{id:1}});await flushPromises();await w.get('input.numeric-answer').setValue('3/4');
  await w.findAll('button').find(b=>b.text().includes('Save & next')).trigger('click');await flushPromises();expect(stored[1]).toBe('3/4');
  await w.findAll('button').find(b=>b.text().includes('Previous')).trigger('click');await flushPromises();expect(w.get('input.numeric-answer').element.value).toBe('3/4');
  await w.get('input.numeric-answer').setValue('0');await vi.advanceTimersByTimeAsync(400);expect(stored[1]).toBe('0');w.unmount();
 });
 it('recovers an unsaved draft on refresh and flushes before submit',async()=>{
  let w=mount(Exam,{props:{id:1}});await flushPromises();await w.get('input.numeric-answer').setValue('42');w.unmount();
  w=mount(Exam,{props:{id:1}});await flushPromises();expect(w.get('input.numeric-answer').element.value).toBe('42');
  await w.findAll('button').find(b=>b.text()==='Submit exam').trigger('click');await w.findAll('button').find(b=>b.text()==='Submit attempt').trigger('click');await flushPromises();expect(stored[1]).toBe('42');expect(mocks.go).toHaveBeenCalledWith('/result/1');w.unmount();
 });
});
