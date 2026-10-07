import {it,expect,vi,afterEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import Exam from '../src/Exam.vue';
const mocks=vi.hoisted(()=>({api:vi.fn(),go:vi.fn(),session:{user:null}}));
vi.mock('../src/api',()=>mocks);
afterEach(()=>{vi.clearAllMocks();sessionStorage.clear()});
async function render(kind,mode='practice',outcome='INCORRECT'){
 const question={id:1,number:'1',kind,text:'Choose',images:[],options:[{key:'internal-a',text:'One'},{key:'internal-b',text:'Two'}],marks:1};
 mocks.api.mockImplementation(async()=>({id:10,status:'ACTIVE',mode,title:'Test',server_time:Date.now()/1000,palette:[{question_id:1,number:'1',state:'ANSWERED'}],items:[{question,answer:['internal-b'],feedback:{outcome,awarded:outcome==='PARTIAL'?.5:0,answers:['internal-a'],explanation:null}}]}));
 const w=mount(Exam,{props:{id:10}});await flushPromises();return w;
}
it('uses circles for MCQ, highlights incorrect/correct options and maps internal keys to compact letters',async()=>{
 const w=await render('MCQ');expect(w.find('.option-key-square').exists()).toBe(false);expect(w.find('.feedback').exists()).toBe(false);await w.findAll('button').find(b=>b.text()==='Check answer').trigger('click');await flushPromises();
 expect(w.findAll('.option')[0].classes()).toContain('option-correct');expect(w.findAll('.option')[1].classes()).toContain('option-incorrect');
 expect(w.get('.feedback-summary').text()).toBe('Your answer: B·Correct: A');expect(w.get('.feedback').classes()).toContain('feedback-incorrect');expect(w.text()).not.toContain('Solution explanation not available');w.unmount();
});
it('uses square indicators for MSQ',async()=>{const w=await render('MSQ');expect(w.findAll('.option-key-square')).toHaveLength(2);w.unmount()});
it('keeps exam answers private even when the cache contains practice feedback',async()=>{const w=await render('MCQ','exam');expect(w.find('.check-answer-row').exists()).toBe(false);expect(w.find('.feedback').exists()).toBe(false);expect(w.find('.option-correct').exists()).toBe(false);expect(w.find('.option-incorrect').exists()).toBe(false);w.unmount()});

it('reveals partial marks only on Check answer and hides feedback after changing the selection',async()=>{const w=await render('MSQ','practice','PARTIAL');expect(w.find('.feedback').exists()).toBe(false);await w.findAll('button').find(b=>b.text()==='Check answer').trigger('click');await flushPromises();expect(w.get('.feedback').text()).toContain('PARTIALLY CORRECT');expect(w.get('.feedback-marks').text()).toBe('Marks: 0.5 / 1');await w.findAll('.option')[0].trigger('click');expect(w.find('.feedback').exists()).toBe(false);w.unmount()});

it('checks an unanswered practice question without saving an answer and scrolls to feedback',async()=>{
 const scroll=vi.fn();Element.prototype.scrollIntoView=scroll;
 const question={id:1,number:'1',kind:'MCQ',text:'Choose',images:[],options:[{key:'A',text:'One'},{key:'B',text:'Two'}],marks:1};
 mocks.api.mockImplementation(async(path)=>path.includes('?reveal=1')?{question,answer:null,feedback:{outcome:'SKIPPED',awarded:0,answers:['A']}}:{id:10,status:'ACTIVE',mode:'practice',title:'Test',server_time:Date.now()/1000,palette:[{question_id:1,number:'1',state:'VISITED'}],items:[{question,answer:null}]});
 const w=mount(Exam,{props:{id:10}});await flushPromises();
 const button=w.findAll('button').find(b=>b.text()==='Check answer');expect(button.attributes('disabled')).toBeUndefined();await button.trigger('click');await flushPromises();
 expect(w.get('.feedback-summary').text()).toContain('Correct: A');expect(scroll).toHaveBeenCalled();expect(mocks.api.mock.calls.some(([p])=>p.includes('?reveal=1'))).toBe(true);w.unmount();
});

it('reveals prefetched feedback and solution immediately while answer save is pending',async()=>{
 const question={id:1,number:'1',kind:'MSQ',text:'Choose',images:[],options:[{key:'A',text:'One'},{key:'B',text:'Two'}],marks:2};
 let finishSave;
 mocks.api.mockImplementation(async(path,options)=>{
  if(path.includes('/practice-feedback?'))return {items:[{question_id:1,key:{kind:'MSQ',answers:['A','B'],answer_status:'ANSWER_AVAILABLE',marks:2,negative_marks:0,msq_scoring:'proportional-v1'},solution:{available:true,text:'Cached explanation'}}]};
  if(options?.method==='POST'&&path.endsWith('/answers'))return new Promise(resolve=>{finishSave=resolve});
  return {id:10,status:'ACTIVE',mode:'practice',title:'Test',server_time:Date.now()/1000,palette:[{question_id:1,number:'1',state:'VISITED'}],items:[{question,answer:null}]};
 });
 const w=mount(Exam,{props:{id:10}});await flushPromises();expect(w.find('.feedback').exists()).toBe(false);
 await w.findAll('.option')[0].trigger('click');await w.findAll('button').find(b=>b.text()==='Check answer').trigger('click');await flushPromises();expect(w.get('.feedback-marks').text()).toBe('Marks: 1 / 2');expect(w.text()).toContain('Cached explanation');
 await w.findAll('.option')[1].trigger('click');expect(w.find('.feedback').exists()).toBe(false);await w.findAll('button').find(b=>b.text()==='Check answer').trigger('click');await flushPromises();expect(w.get('.feedback-marks').text()).toBe('Marks: 2 / 2');
 expect(mocks.api.mock.calls.some(([p])=>p.includes('?reveal=1')||p.endsWith('/ai-solution'))).toBe(false);
 w.unmount();finishSave?.({items:[]});await flushPromises();
});
