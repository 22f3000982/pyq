import {describe,it,expect,vi,beforeEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import Catalog from '../src/Catalog.vue';import Exam from '../src/Exam.vue';import Admin from '../src/Admin.vue';
const mocks=vi.hoisted(()=>({api:vi.fn(),go:vi.fn(),session:{user:{id:1,name:'Test',role:'ADMIN'}}}));
vi.mock('../src/api',()=>({...mocks,api:async(path,o)=>{if(path.endsWith('?bootstrap=1')){const base=path.split('?')[0];return {...await mocks.api(base,o),...await mocks.api(base+'/questions')}}return mocks.api(path,o)},loadCatalog:async()=>{const [c,m]=await Promise.all([mocks.api('/courses?limit=100'),mocks.api('/metadata')]);return {courses:c.items,meta:m}},invalidateCatalog:vi.fn()}));
vi.mock('../src/MathText.vue',()=>({default:{props:['text'],template:'<div>{{text}}</div>'}}));
beforeEach(()=>{mocks.api.mockReset();mocks.go.mockReset();sessionStorage.clear()});
describe('student surfaces',()=>{
it('homepage stays focused on high-level stats and direct exam actions',async()=>{
 mocks.api.mockImplementation(async path=>path==='/stats'?{courses:39,papers:734,questions:1403,exam_papers:{'Quiz 1':42,'Quiz 2':38,'End Term':31}}:path==='/metadata'?{levels:['DEGREE']}:{items:[],total:0});
 const w=mount(Catalog,{props:{route:'/'}});await flushPromises();expect(w.text()).toContain('734');expect(w.text()).toContain('Quiz 1');expect(w.text()).toContain('42 papers available');expect(w.text()).not.toContain('Five papers to try');expect(w.text()).not.toContain('Explore your courses');expect(mocks.api.mock.calls.some(c=>String(c[0]).startsWith('/courses?'))).toBe(false);w.unmount();
});
it('unimported paper disables exam and practice but preserves source',async()=>{
 mocks.api.mockImplementation(async path=>path==='/stats'?{}:path==='/metadata'?{levels:[]}:({id:1,course_id:1,course:'Test',name:'Source paper',practice_available:false,question_count:0,source_url:'https://example.com/paper',warnings:[]}));
 const w=mount(Catalog,{props:{route:'/paper/1'}});await flushPromises();expect(w.text()).toContain('Questions not imported yet.');expect(w.findAll('button').filter(b=>b.text().startsWith('Start')).every(b=>b.attributes('disabled')!==undefined)).toBe(true);w.unmount();
});
it('exam saves options and review mark, then submits through confirmation',async()=>{
 const a={id:1,mode:'exam',title:'DEMO DATA',status:'ACTIVE',deadline:Date.now()/1000+3600,server_time:Date.now()/1000,palette:[{question_id:1,state:'NOT_VISITED'}]};
 mocks.api.mockImplementation(async(path,options)=>path==='/attempts/1'?a:path.endsWith('/questions')?{status:'ACTIVE',items:[{question:{id:1,kind:'MCQ',text:'DEMO DATA question',marks:2,negative_marks:0,options:[{key:'A',text:'Alpha'},{key:'B',text:'Beta'}],images:[]},answer:null,marked:false}]}:path.endsWith('/answers')?{state:options.body.marked?'ANSWERED_AND_MARKED_FOR_REVIEW':options.body.answer?'ANSWERED':'VISITED'}:{});
 const w=mount(Exam,{props:{id:1}});await flushPromises();await w.findAll('.option')[0].trigger('click');await new Promise(r=>setTimeout(r,300));await flushPromises();expect(mocks.api).toHaveBeenCalledWith('/attempts/1/answers',expect.objectContaining({body:{items:expect.arrayContaining([expect.objectContaining({question_id:1,answer:['A']})])}}));
 await w.findAll('button').find(b=>b.text()==='Mark for review').trigger('click');await flushPromises();expect(w.text()).not.toContain('Correct answer');await w.findAll('button').find(b=>b.text()==='Submit exam').trigger('click');expect(w.find('[role="dialog"]').exists()).toBe(true);await w.findAll('button').find(b=>b.text()==='Submit attempt').trigger('click');await flushPromises();expect(mocks.go).toHaveBeenCalledWith('/result/1');w.unmount();
});
});
describe('automatic processing',()=>{it('shows processing counters and queues catalog without approval controls',async()=>{
 mocks.api.mockImplementation(async(path,options)=>path.startsWith('/courses')?{items:[]}:path==='/metadata'?{terms:[],exams:[]}:path==='/admin/stats'?{papers:734,processed:1,questions:20}:path.startsWith('/admin/ingestion')?{items:[],total:0}:({queued:3,batch_id:1}));
 const w=mount(Admin);await flushPromises();expect(w.text()).toContain('734');expect(w.text()).not.toContain('Verify');expect(w.text()).not.toContain('Publish');await w.findAll('button').find(b=>b.text()==='Resume full catalog processing').trigger('click');await flushPromises();expect(mocks.api).toHaveBeenCalledWith('/admin/process-catalog',expect.objectContaining({method:'POST'}));w.unmount();
})});

describe('PDF upload form',()=>{it('posts the PDF and metadata and displays real processing completion',async()=>{
 const {default:Upload}=await import('../src/Upload.vue');
 mocks.api.mockImplementation(async(path)=>path.startsWith('/courses')?{items:[{id:1,name:'Deep Learning'}]}:path==='/metadata'?{terms:[{id:1,name:'May 2026'}],exams:[{id:1,name:'Quiz 1'}]}:path==='/admin/upload-pyq'?{file:{id:17,status:'QUEUED'},paper:{id:13}}:{file:{id:17,status:'AVAILABLE',effective_status:'AVAILABLE',events:[{stage:'AVAILABLE',message:'Ready'}]},paper:{id:13,question_count:20}});
 const w=mount(Upload);await flushPromises();await w.get('[aria-label="Upload course"]').setValue('1');await w.get('[aria-label="Upload exam type"]').setValue('1');await w.get('[aria-label="Upload term"]').setValue('1');
 const input=w.get('input[type="file"]');Object.defineProperty(input.element,'files',{value:[new File(['%PDF-test'],'real.pdf',{type:'application/pdf'})]});await input.trigger('change');await w.get('form').trigger('submit');await flushPromises();
 const call=mocks.api.mock.calls.find(c=>c[0]==='/admin/upload-pyq');expect(call[1].form.get('course_id')).toBe('1');expect(call[1].form.get('file').name).toBe('real.pdf');expect(w.text()).toContain('Completed ✓');expect(w.get('a').attributes('href')).toBe('#/paper/13');w.unmount();
})});

describe('student requested improvements',()=>{
 it('renders option letters, exact text and image options instead of internal IDs',async()=>{
  const {default:AnswerValue}=await import('../src/AnswerValue.vue');const question={kind:'MSQ',options:[{key:'6406537043813',text:'(0, 0)'},{key:'6406537043814',text:''}],images:[{id:8,option_key:'6406537043814',alt:'Source option'}]};
  const w=mount(AnswerValue,{props:{question,value:['6406537043813','6406537043814']}});expect(w.text()).toContain('Option A');expect(w.text()).toContain('(0, 0)');expect(w.text()).toContain('Option B');expect(w.text()).not.toContain('640653');expect(w.get('img').attributes('src')).toBe('/api/images/8');w.unmount();
 });
 it('uses arrow keys for navigation and ignores them inside a text input',async()=>{
  const a={id:1,mode:'practice',title:'DEMO DATA',status:'ACTIVE',deadline:null,server_time:Date.now()/1000,palette:[{question_id:1,number:'2',state:'NOT_VISITED'},{question_id:2,number:'3',state:'NOT_VISITED'}]};
  mocks.api.mockImplementation(async(path)=>path==='/attempts/1'?a:path.endsWith('/questions')?{status:'ACTIVE',items:[1,2].map(id=>({status:'ACTIVE',question:{id,number:String(id+1),kind:'NAT',text:'DEMO DATA',marks:1,options:[],images:[]},answer:null,marked:false}))}:{state:'VISITED'});
  const w=mount(Exam,{props:{id:1},attachTo:document.body});await flushPromises();window.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight'}));await flushPromises();expect(w.text()).toContain('QUESTION 3');
  const count=mocks.api.mock.calls.length;await w.get('input').trigger('keydown',{key:'ArrowLeft'});await flushPromises();expect(mocks.api.mock.calls.length).toBe(count);window.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowLeft'}));await flushPromises();expect(w.text()).toContain('QUESTION 2');expect(mocks.api.mock.calls.filter(c=>c[0]==='/attempts/1/questions').length).toBe(1);expect(mocks.api.mock.calls.some(c=>c[0].includes('/questions/1'))).toBe(false);w.unmount();
 });
 it('loads available papers after choosing a course within an exam type',async()=>{
  const {default:ExamBrowser}=await import('../src/ExamBrowser.vue');mocks.api.mockImplementation(async(path)=>path.startsWith('/courses')?{items:[{id:27,name:'Game Theory',exams:{'Quiz 1':3}}]}:path==='/metadata'?{terms:[{id:1,name:'May 2026'}]}:{items:[{id:50,name:'Game Theory.pdf',term:'May 2026',exam:'Quiz 1',question_count:16,total_marks:25}],total:1});
  const w=mount(ExamBrowser,{props:{route:'/exam/Quiz%201'}});await flushPromises();await w.get('button[aria-label="Choose course"]').trigger('click');const search=w.get('.searchable-select-search input');await search.setValue('Game');expect(w.findAll('.searchable-select-option')).toHaveLength(1);await w.findAll('.searchable-select-option')[0].trigger('click');await flushPromises();expect(mocks.api.mock.calls.at(-1)[0]).toContain('available=true');expect(w.text()).toContain('Game Theory.pdf');expect(w.text()).toContain('May 2026');expect(w.findAll('a').at(-1).attributes('href')).toBe('#/paper/50');w.unmount();
 });
});

describe('editable exam timer',()=>{
 it('starts at 90 minutes and sends a changed duration even when source duration exists',async()=>{
  mocks.api.mockImplementation(async path=>path==='/stats'?{}:path==='/metadata'?{levels:[]}:path==='/attempts'?{id:10}:{id:1,course_id:1,course:'Test',name:'Source paper',practice_available:true,question_count:2,duration_seconds:1800,warnings:[]});
  const w=mount(Catalog,{props:{route:'/paper/1'}});await flushPromises();expect(w.get('input[type="number"]').element.value).toBe('90');await w.get('input[type="number"]').setValue('120');await w.findAll('button').find(b=>b.text()==='Start exam').trigger('click');await flushPromises();expect(mocks.api).toHaveBeenCalledWith('/attempts',expect.objectContaining({body:expect.objectContaining({duration_seconds:7200})}));w.unmount();
 });
});
