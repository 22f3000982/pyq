import {describe,it,expect,vi,beforeEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import PaperProgress from '../src/PaperProgress.vue';import ExamBrowser from '../src/ExamBrowser.vue';import Records from '../src/Records.vue';
const mocks=vi.hoisted(()=>({api:vi.fn(),go:vi.fn(),session:{user:{id:1,name:'Student'}}}));
vi.mock('../src/api',()=>({...mocks,loadCatalog:async()=>{const [c,m]=await Promise.all([mocks.api('/courses?limit=100'),mocks.api('/metadata')]);return {courses:c.items,meta:m}}}));
beforeEach(()=>{mocks.api.mockReset();mocks.go.mockReset()});
describe('latest paper progress',()=>{
 it('shows the exact latest percentage and preserves zero/unknown',async()=>{
  const w=mount(PaperProgress,{props:{progress:{attempted:true,last_score:70}}});expect(w.text()).toBe('You already attempted this QP and scored 70.0%.');
  await w.setProps({progress:{attempted:true,last_score:90}});await w.setProps({progress:{attempted:true,last_score:80}});expect(w.text()).toBe('You already attempted this QP and scored 80.0%.');expect(w.text()).not.toContain('90.0');
  await w.setProps({progress:{attempted:true,last_score:0}});expect(w.text()).toContain('0.0%');
  await w.setProps({progress:{attempted:true,last_score:null}});expect(w.text()).toContain('Score unavailable');expect(w.text()).not.toContain('0.0%');w.unmount();
 });
 it('paper cards show Take Test or latest score and Retake Test',async()=>{
  mocks.api.mockImplementation(async path=>path.startsWith('/courses')?{items:[{id:1,name:'AI',exams:{'Quiz 1':2}}]}:path==='/metadata'?{terms:[]}:{items:[{id:1,name:'New paper',progress:null},{id:2,name:'Attempted paper',progress:{attempted:true,last_score:80}}],total:2});
  const w=mount(ExamBrowser,{props:{route:'/exam/Quiz%201'}});await flushPromises();await w.get('select[aria-label="Choose course"]').setValue('1');await flushPromises();
  const cards=w.findAll('article');expect(cards[0].text()).toContain('Take Test');expect(cards[0].text()).not.toContain('already attempted');expect(cards[1].text()).toContain('You already attempted this QP and scored 80.0%.');expect(cards[1].get('a').attributes('href')).toBe('#/paper/2');expect(cards[1].text()).toContain('Retake Test');w.unmount();
 });
 it('progress page displays latest scores and active resumes, without past-attempt analytics',async()=>{
  mocks.api.mockImplementation(async path=>path.startsWith('/progress')?{items:[{paper_id:1,name:'AI',attempted:true,last_score:80}],total:1}:{items:[{id:20,title:'Active paper',mode:'exam'}]});
  const w=mount(Records,{props:{route:'/progress'}});await flushPromises();expect(w.text()).toContain('80.0%');expect(w.text()).toContain('Resume');expect(w.findAll('a').some(a=>a.attributes('href')==='#/paper/1')).toBe(true);expect(w.text()).not.toContain('Topic performance');expect(w.text()).not.toContain('Recent attempts');w.unmount();
 });
 it('result page supports temporary review and full-paper retake',async()=>{
  mocks.api.mockImplementation(async path=>path==='/attempts/1'?{id:1,paper_id:5,status:'SUBMITTED',title:'AI',expires_at:Date.now()/1000+3600,result:{score:8,total_marks:10,percentage:80,incorrect:2}}:path.endsWith('/review?page=1')?{items:[],total:0}:{id:2});
  const w=mount(Records,{props:{route:'/result/1'}});await flushPromises();expect(w.text()).toContain('Results and question review are temporary');await w.findAll('button').find(b=>b.text()==='Review solutions').trigger('click');await flushPromises();expect(mocks.api).toHaveBeenCalledWith('/attempts/1/review?page=1');await w.findAll('button').find(b=>b.text()==='Practice again').trigger('click');await flushPromises();expect(mocks.api).toHaveBeenCalledWith('/attempts',expect.objectContaining({body:{paper_id:5,mode:'practice'}}));expect(mocks.go).toHaveBeenCalledWith('/attempt/2');w.unmount();
 });
});
