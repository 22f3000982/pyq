import {it,expect,vi,beforeEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import ContentQuality from '../src/ContentQuality.vue';
const mocks=vi.hoisted(()=>({api:vi.fn()}));vi.mock('../src/api',()=>mocks);
beforeEach(()=>mocks.api.mockReset());
it('scans explicitly and opens source/review without changing content',async()=>{
 mocks.api.mockImplementation(async(path)=>{
  if(path==='/catalog')return {courses:[]};
  if(!path)return {};
  if(path.endsWith('/deployment'))return {commit:'abc',note:'Compare commits'};
  if(path.includes('/scan'))return {items:[{id:1,paper_id:9,paper:'Finance',number:'1',status:'AVAILABLE',flags:['Course mismatch'],reviewed:false}],scanned:200,next_after:200,has_more:true};
  return {};
 });
 const w=mount(ContentQuality);await flushPromises();
 expect(mocks.api.mock.calls.some(c=>c[0].includes('/scan'))).toBe(false);
 await w.findAll('button').find(b=>b.text()==='Scan from beginning').trigger('click');await flushPromises();
 expect(w.text()).toContain('Course mismatch');expect(w.get('a[target="_blank"]').attributes('href')).toBe('/api/papers/9/source');
 expect(mocks.api.mock.calls.every(c=>!c[1]?.method)).toBe(true);
 await w.findAll('button').find(b=>b.text()==='Edit / repair').trigger('click');expect(w.emitted('edit')[0]).toEqual([1]);w.unmount();
});
