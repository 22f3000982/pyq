import {it,expect,vi} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import Admin from '../src/Admin.vue';
const mocks=vi.hoisted(()=>({api:vi.fn(),loadCatalog:vi.fn(),invalidateCatalog:vi.fn(),session:{user:{role:'ADMIN'}}}));
vi.mock('../src/api',()=>mocks);
it('previews the Java repair before confirming and queuing it',async()=>{
 localStorage.setItem('pyq-admin-tab','Papers');
 mocks.loadCatalog.mockResolvedValue({courses:[],meta:{terms:[],exams:[]}});
 mocks.api.mockImplementation(async (path,options)=>{
  if(path==='/admin/catalog/repair-java-2025')return options.body.apply?{queued:2,batch_id:7}:{count:2,active_jobs:0};
  if(path.startsWith('/admin/papers?'))return {items:[],total:0};
  return {};
 });
 const confirmation=vi.spyOn(window,'confirm').mockReturnValue(true);
 const w=mount(Admin);await flushPromises();
 await w.findAll('button').find(b=>b.text()==='Repair Java / App Dev-1 May/Sep 2025').trigger('click');await flushPromises();
 expect(confirmation).toHaveBeenCalledTimes(1);
 expect(mocks.api).toHaveBeenCalledWith('/admin/catalog/repair-java-2025',{method:'POST',body:{apply:false}});
 expect(mocks.api).toHaveBeenCalledWith('/admin/catalog/repair-java-2025',{method:'POST',body:{apply:true}});
 expect(w.text()).toContain('2 Java papers queued');
 w.unmount();confirmation.mockRestore();localStorage.removeItem('pyq-admin-tab');
});
