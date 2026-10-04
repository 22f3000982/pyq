import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import Exam from '../src/Exam.vue';import QuestionContent from '../src/QuestionContent.vue';import MathText from '../src/MathText.vue';
const mocks=vi.hoisted(()=>({api:vi.fn(),go:vi.fn(),session:{user:{name:'Student'}}}));vi.mock('../src/api',()=>({...mocks,api:async(path,o)=>{if(path.endsWith('?bootstrap=1')){const base=path.split('?')[0];return {...await mocks.api(base,o),...await mocks.api(base+'/questions')}}return mocks.api(path,o)}}));
let attempt;
beforeEach(()=>{vi.useFakeTimers();sessionStorage.clear();mocks.go.mockReset();mocks.api.mockReset();attempt={id:4,title:'Source paper',mode:'exam',status:'ACTIVE',deadline:Date.now()/1000+600,server_time:Date.now()/1000,palette:[1,2].map(id=>({question_id:id,number:String(id),state:'NOT_VISITED'}))};
 mocks.api.mockImplementation(async(path,o)=>path==='/attempts/4'?structuredClone(attempt):path==='/attempts/4/status'?{id:attempt.id,status:attempt.status,deadline:attempt.deadline,submitted_at:null,expires_at:Date.now()/1000+3600,server_time:Date.now()/1000}:path==='/attempts/4/questions'?{status:'ACTIVE',items:[1,2].map(id=>({question:{id,number:String(id),kind:'NAT',text:'Source question '+id,images:[],options:[],marks:1},answer:null,marked:false}))}:path.endsWith('/answers')?{items:(o?.body?.items||[]).map(x=>({question_id:x.question_id,state:'ANSWERED'}))}:{state:'ANSWERED'});
});
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers()});
const button=(w,label)=>w.findAll('button').find(b=>b.text()===label);
describe('nonblocking exam navigation',()=>{
 it('navigates immediately while save is unresolved; serializes newer responses and submit',async()=>{
  const w=mount(Exam,{props:{id:4}});await flushPromises();let release;
  const base=mocks.api.getMockImplementation();mocks.api.mockImplementation((path,o)=>path.endsWith('/answers')&&o.body.items?.some(x=>x.answer==='3/4')?new Promise(r=>release=r):base(path,o));
  await w.get('input.numeric-answer').setValue('3/4');await vi.advanceTimersByTimeAsync(400);
  await button(w,'Save & next').trigger('click');expect(w.text()).toContain('QUESTION 2');
  await w.get('input.numeric-answer').setValue('0');await button(w,'Previous').trigger('click');expect(w.get('input.numeric-answer').element.value).toBe('3/4');
  await button(w,'Submit exam').trigger('click');await button(w,'Submit attempt').trigger('click');expect(mocks.api.mock.calls.some(c=>c[0].endsWith('/submit'))).toBe(false);
  release({items:[{question_id:1,state:'ANSWERED'}]});await flushPromises();expect(mocks.api).toHaveBeenCalledWith('/attempts/4/answers',expect.objectContaining({body:expect.objectContaining({items:expect.arrayContaining([expect.objectContaining({question_id:2,answer:'0'})])})}));
  expect(mocks.go).toHaveBeenCalledWith('/result/4');expect(mocks.api.mock.calls.filter(c=>c[0]==='/attempts/4/questions')).toHaveLength(1);w.unmount();
 });
 it('focuses NAT automatically and Enter moves to the next question with signed decimals intact',async()=>{
  const w=mount(Exam,{props:{id:4},attachTo:document.body});await flushPromises();
  const first=w.get('input.numeric-answer');expect(document.activeElement).toBe(first.element);
  await first.setValue('-2.75');await first.trigger('keydown',{key:'Enter'});await flushPromises();
  expect(w.text()).toContain('QUESTION 2');await button(w,'Previous').trigger('click');expect(w.get('input.numeric-answer').element.value).toBe('-2.75');w.unmount();
 });
 it('navigates through untouched questions without writing visited state to the server',async()=>{
  const w=mount(Exam,{props:{id:4}});await flushPromises();await button(w,'Save & next').trigger('click');await button(w,'Previous').trigger('click');await vi.advanceTimersByTimeAsync(1000);
  expect(mocks.api.mock.calls.filter(c=>c[0].endsWith('/answers'))).toHaveLength(0);expect(sessionStorage.getItem('pyq-visited-4')).toContain('1');w.unmount();
 });
 it('prefetches the next three image questions plus two idle lookahead questions',async()=>{
  const urls=[];vi.stubGlobal('Image',class{set src(v){urls.push(v);queueMicrotask(()=>this.onload?.())}});
  attempt.palette=[1,2,3,4,5,6].map(id=>({question_id:id,number:String(id),state:'NOT_VISITED'}));
  mocks.api.mockImplementation(async(path,o)=>path==='/attempts/4'?structuredClone(attempt):path==='/attempts/4/status'?{id:4,status:'ACTIVE',deadline:attempt.deadline,server_time:Date.now()/1000}:path==='/attempts/4/questions'?{status:'ACTIVE',items:[1,2,3,4,5,6].map(id=>({question:{id,number:String(id),kind:'MCQ',text:'Q'+id,images:[{id:100+id,url:'/api/images/'+(100+id)+'?proxy=1'}],options:[{key:'A',text:'A'},{key:'B',text:'B'}],marks:1},answer:null,marked:false}))}:path.endsWith('/answers')?{items:[]}:{state:'VISITED'});
  const w=mount(Exam,{props:{id:4}});await flushPromises();
  await vi.advanceTimersByTimeAsync(3500);await flushPromises();
  expect(urls).toEqual(expect.arrayContaining(['/api/images/102?proxy=1','/api/images/103?proxy=1','/api/images/104?proxy=1','/api/images/105?proxy=1','/api/images/106?proxy=1']));
  expect(new Set(urls).size).toBe(urls.length);w.unmount();
 });
 it('uses a sparse jittered heartbeat instead of synchronized polling',async()=>{
  vi.spyOn(Math,'random').mockReturnValue(0);
  const w=mount(Exam,{props:{id:4}});await flushPromises();expect(mocks.api.mock.calls.filter(c=>c[0]==='/attempts/4/status')).toHaveLength(0);
  await vi.advanceTimersByTimeAsync(599000);expect(mocks.api.mock.calls.filter(c=>c[0]==='/attempts/4/status')).toHaveLength(0);
  await vi.advanceTimersByTimeAsync(1000);await flushPromises();expect(mocks.api.mock.calls.filter(c=>c[0]==='/attempts/4/status')).toHaveLength(1);
  expect(mocks.api.mock.calls.filter(c=>c[0]==='/attempts/4/questions')).toHaveLength(1);w.unmount();
 });
 it('keeps offline responses across navigation and restores them after remount',async()=>{
  let w=mount(Exam,{props:{id:4}});await flushPromises();const base=mocks.api.getMockImplementation();mocks.api.mockImplementation((path,o)=>path.endsWith('/answers')?Promise.reject(new Error('Offline')):base(path,o));
  await w.get('input.numeric-answer').setValue('-2.5');await vi.advanceTimersByTimeAsync(400);await button(w,'Save & next').trigger('click');await w.get('input.numeric-answer').setValue('7');w.unmount();
  w=mount(Exam,{props:{id:4}});await flushPromises();expect(w.get('input.numeric-answer').element.value).toBe('7');await button(w,'Previous').trigger('click');expect(w.get('input.numeric-answer').element.value).toBe('-2.5');
  mocks.api.mockImplementation(base);await button(w,'Retry save').trigger('click');await flushPromises();expect(sessionStorage.getItem('pyq-pending-4')).toBeNull();w.unmount();
 });
 it('submits only once when the timer expires while the response is pending',async()=>{
  attempt.deadline=Date.now()/1000+1;const base=mocks.api.getMockImplementation();let release;
  mocks.api.mockImplementation((p,o)=>p.endsWith('/submit')?new Promise(r=>release=r):base(p,o));
  const w=mount(Exam,{props:{id:4}});await flushPromises();await vi.advanceTimersByTimeAsync(6000);expect(mocks.api.mock.calls.filter(c=>c[0].endsWith('/submit'))).toHaveLength(1);release({});await flushPromises();w.unmount();
 });
});
describe('visible source fidelity',()=>{
 it('shows an explicit recoverable error instead of silently removing source notation',async()=>{
  const w=mount(QuestionContent,{props:{text:'Function [[IMAGE:x]] at [[IMAGE:missing]]',images:[{id:1,token:'x',inline:true,width:3}]}});await w.get('img').trigger('error');expect(w.find('img').exists()).toBe(false);expect(w.text()).toContain('Source diagram or notation unavailable');expect(w.text()).toContain('[Source notation unavailable]');await w.get('button').trigger('click');expect(w.get('img').attributes('src')).toBe('/api/images/1?proxy=1');w.unmount();
 });
 it('renders source fractions, Greek letters and matrices without trusting HTML',async()=>{
  const w=mount(MathText,{props:{text:String.raw`Inline \(\frac{\alpha_1^2}{2}\) display \[\begin{pmatrix}1&2\\3&4\end{pmatrix}\] <img src=x onerror=alert(1)>`}});await flushPromises();expect(w.findAll('.katex')).toHaveLength(2);expect(w.find('img').exists()).toBe(false);expect(w.text()).toContain('<img src=x');w.unmount();
 });
});

it('switches with one click and saves pending answers first',async()=>{
 const w=mount(Exam,{props:{id:4}});await flushPromises();let release;
 const base=mocks.api.getMockImplementation();
 mocks.api.mockImplementation((path,o)=>path.endsWith('/switch-mode')?new Promise(r=>release=r):base(path,o));
 await w.get('input.numeric-answer').setValue('7');
 await button(w,'Switch to practice').trigger('click');await flushPromises();
 expect(w.find('[aria-labelledby="switch-title"]').exists()).toBe(false);
 expect(mocks.api.mock.calls.filter(c=>c[0].endsWith('/switch-mode'))).toHaveLength(1);
 expect(button(w,'Switching…').attributes('disabled')).toBeDefined();
 const paths=mocks.api.mock.calls.map(c=>c[0]);expect(paths.indexOf('/attempts/4/answers')).toBeLessThan(paths.indexOf('/attempts/4/switch-mode'));
 release({id:4,mode:'practice',title:'Source paper',deadline:null,server_time:Date.now()/1000,feedback:[]});await flushPromises();expect(mocks.go).not.toHaveBeenCalled();expect(button(w,'Switch to exam')).toBeDefined();expect(mocks.api.mock.calls.filter(c=>c[0]==='/attempts/4/questions')).toHaveLength(1);w.unmount();
});
