import {it,expect,vi,afterEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import Exam from '../src/Exam.vue';
const mocks=vi.hoisted(()=>({api:vi.fn(),go:vi.fn(),session:{user:null}}));
vi.mock('../src/api',()=>mocks);
afterEach(()=>{vi.clearAllMocks();sessionStorage.clear()});
async function render(kind,mode='practice'){
 const question={id:1,number:'1',kind,text:'Choose',images:[],options:[{key:'internal-a',text:'One'},{key:'internal-b',text:'Two'}],marks:1};
 mocks.api.mockImplementation(async()=>({id:10,status:'ACTIVE',mode,title:'Test',server_time:Date.now()/1000,palette:[{question_id:1,number:'1',state:'ANSWERED'}],items:[{question,answer:['internal-b'],feedback:{outcome:'INCORRECT',answers:['internal-a'],explanation:null}}]}));
 const w=mount(Exam,{props:{id:10}});await flushPromises();return w;
}
it('uses circles for MCQ, highlights incorrect/correct options and maps internal keys to compact letters',async()=>{
 const w=await render('MCQ');expect(w.find('.option-key-square').exists()).toBe(false);
 expect(w.findAll('.option')[0].classes()).toContain('option-correct');expect(w.findAll('.option')[1].classes()).toContain('option-incorrect');
 expect(w.get('.feedback-summary').text()).toBe('Your answer: B·Correct: A');expect(w.get('.feedback').classes()).toContain('feedback-incorrect');expect(w.text()).not.toContain('Solution explanation not available');w.unmount();
});
it('uses square indicators for MSQ',async()=>{const w=await render('MSQ');expect(w.findAll('.option-key-square')).toHaveLength(2);w.unmount()});
it('keeps exam answers private even when the cache contains practice feedback',async()=>{const w=await render('MCQ','exam');expect(w.find('.feedback').exists()).toBe(false);expect(w.find('.option-correct').exists()).toBe(false);expect(w.find('.option-incorrect').exists()).toBe(false);w.unmount()});
