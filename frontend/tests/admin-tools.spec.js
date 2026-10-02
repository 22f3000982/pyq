import {it,expect,vi,afterEach} from 'vitest';import {mount,flushPromises} from '@vue/test-utils';
import {api} from '../src/api';import QuestionEditor from '../src/QuestionEditor.vue';import ReplacementPdf from '../src/ReplacementPdf.vue';import TcsCalculator from '../src/TcsCalculator.vue';
vi.mock('../src/api',()=>({api:vi.fn()}));afterEach(()=>{vi.clearAllMocks();vi.unstubAllGlobals()});
const question={id:9,number:'3',text:'Original stem',kind:'MCQ',options:[{key:'A',text:'Alpha'},{key:'B',text:'Beta'}],images:[],answers:['A'],marks:2,negative_marks:0,tolerance:0,status:'AVAILABLE',hidden:false,explanation:''};
it('edits a reported question with live preview and a single save-and-resolve request',async()=>{
 api.mockResolvedValue({question,updated_at:10,history:[]});const w=mount(QuestionEditor,{props:{questionId:9,reportId:4}});await flushPromises();
 await w.findAll('textarea')[1].setValue('Corrected stem');expect(w.text()).toContain('Corrected stem');
 await w.findAll('button').find(b=>b.text()==='Save & resolve report').trigger('click');await flushPromises();
 expect(api).toHaveBeenCalledWith('/admin/questions/9',expect.objectContaining({method:'PATCH',body:expect.objectContaining({updated_at:10,text:'Corrected stem',resolve_report_id:4})}));expect(w.emitted('saved')).toHaveLength(1);w.unmount();
});
it('hides questions using their loaded version without editing content',async()=>{
 api.mockResolvedValue({question,updated_at:10,history:[]});const w=mount(QuestionEditor,{props:{questionId:9}});await flushPromises();
 await w.findAll('button').find(b=>b.text()==='Hide question').trigger('click');await flushPromises();
 expect(api).toHaveBeenCalledWith('/admin/questions/9/visibility',{method:'POST',body:{updated_at:10,hidden:true}});w.unmount();
});
it('native calculator computes locally, supports memory, and reports domain errors',async()=>{
 const w=mount(TcsCalculator);expect(w.find('iframe').exists()).toBe(false);await w.get('input[aria-label="Calculator expression"]').setValue('sin(30)+2^3');await w.get('input[aria-label="Calculator expression"]').trigger('keydown',{key:'Enter'});expect(w.get('output').text()).toBe('8.5');
 await w.findAll('button').find(b=>b.text()==='MS').trigger('click');await w.get('input[aria-label="Calculator expression"]').setValue('2+');await w.findAll('button').find(b=>b.text()==='MR').trigger('click');expect(w.get('input[aria-label="Calculator expression"]').element.value).toBe('2+(8.5)');
 await w.get('input[aria-label="Calculator expression"]').setValue('1/0');await w.get('input[aria-label="Calculator expression"]').trigger('keydown',{key:'Enter'});expect(w.get('[role="alert"]').text()).toContain('Division by zero');expect(api).not.toHaveBeenCalled();w.unmount();
});
it('replacement process-now targets the uploaded job and keeps errors visible',async()=>{
 api.mockResolvedValueOnce({file:{id:12,status:'QUEUED'}});const w=mount(ReplacementPdf,{props:{paperId:7,paperName:'Paper'}});
 const file=new File(['PDF'],'new.pdf',{type:'application/pdf'});Object.defineProperty(w.get('input[type="file"]').element,'files',{value:[file]});await w.get('input[type="file"]').trigger('change');await w.get('form').trigger('submit');await flushPromises();
 expect(api.mock.calls[0][0]).toBe('/admin/papers/7/replacement');api.mockRejectedValueOnce(Error('Job already claimed'));await w.findAll('button').find(b=>b.text()==='Process now').trigger('click');await flushPromises();expect(w.get('[role="alert"]').text()).toBe('Job already claimed');expect(api).toHaveBeenLastCalledWith('/admin/ingestion/12/process-now',{method:'POST',body:{}});w.unmount();
});
