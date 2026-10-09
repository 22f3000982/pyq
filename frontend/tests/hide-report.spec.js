import {it,expect,vi} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import Admin from '../src/Admin.vue';
const mocks=vi.hoisted(()=>({api:vi.fn(),loadCatalog:vi.fn(),invalidateCatalog:vi.fn(),session:{user:{role:'ADMIN'}}}));
vi.mock('../src/api',()=>mocks);
it('places hide-and-resolve beside mark-resolved and sends the loaded question version',async()=>{
 localStorage.setItem('pyq-admin-tab','Content Reports');
 mocks.loadCatalog.mockResolvedValue({courses:[],meta:{terms:[],exams:[]}});
 mocks.api.mockImplementation(async (path,options)=>{
  if(path.startsWith('/admin/content-reports?'))return {items:[{id:4,question_id:9,status:'OPEN',paper:'Paper',number:'3',issue:'TEXT'}],total:1};
  if(path==='/admin/questions/9')return {updated_at:10};
  return {};
 });
 const w=mount(Admin);await flushPromises();
 const buttons=w.findAll('button'),index=buttons.findIndex(b=>b.text()==='Mark resolved');
 expect(buttons[index+1].text()).toBe('Hide & mark resolved');
 await buttons[index+1].trigger('click');await flushPromises();
 expect(mocks.api).toHaveBeenCalledWith('/admin/content-reports/4',{method:'PATCH',body:{status:'RESOLVED',hide_question:true,updated_at:10}});
 expect(mocks.invalidateCatalog).toHaveBeenCalled();expect(w.text()).toContain('Question hidden and report resolved');
 w.unmount();localStorage.removeItem('pyq-admin-tab');
});
