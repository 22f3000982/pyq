import {it,expect,vi,afterEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import {api,go} from '../src/api';
import ReportFormat from '../src/ReportFormat.vue';
import Catalog from '../src/Catalog.vue';
vi.mock('../src/api',()=>({api:vi.fn(),go:vi.fn(),session:{user:{role:'GUEST'}}}));
afterEach(()=>vi.clearAllMocks());
it('shows loading immediately, blocks duplicate starts and restores controls on failure',async()=>{
 api.mockResolvedValueOnce({id:1,practice_available:true,name:'Paper',question_count:1}).mockResolvedValueOnce({items:[]});
 const w=mount(Catalog,{props:{route:'/paper/1'}});await flushPromises();
 let reject;api.mockImplementation(()=>new Promise((_,r)=>reject=r));
 const button=w.findAll('button').find(b=>b.text()==='Start exam');await button.trigger('click');
 expect(w.get('[role="status"]').text()).toContain('Preparing your exam');expect(button.attributes('disabled')).toBeDefined();
 expect(api.mock.calls.filter(c=>c[0]==='/attempts')).toHaveLength(1);
 reject(Error('Network unavailable'));await flushPromises();
 expect(w.find('.loading-state').exists()).toBe(false);expect(button.attributes('disabled')).toBeUndefined();expect(w.get('[role="alert"]').text()).toContain('Network unavailable');expect(go).not.toHaveBeenCalled();w.unmount();
});
it('reports the fixed question id and retains the dialog on submission error',async()=>{
 const w=mount(ReportFormat,{props:{questionId:9,number:'3'}});
 await w.get('select').setValue('FORMULA');await w.get('textarea').setValue('Clipped equation');
 api.mockRejectedValueOnce(Error('Please try again'));await w.get('form').trigger('submit');await flushPromises();
 expect(w.get('[role="alert"]').text()).toBe('Please try again');expect(w.emitted('close')).toBeUndefined();
 api.mockResolvedValueOnce({duplicate:false});await w.get('form').trigger('submit');await flushPromises();
 expect(api).toHaveBeenLastCalledWith('/questions/9/report-format',{method:'POST',body:{issue:'FORMULA',description:'Clipped equation'}});expect(w.emitted('sent')[0][0]).toContain('Report sent');expect(w.emitted('close')).toHaveLength(1);w.unmount();
});
