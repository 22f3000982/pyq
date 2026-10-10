import {it,expect,vi} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import Admin from '../src/Admin.vue';
const mocks=vi.hoisted(()=>({api:vi.fn(),loadCatalog:vi.fn(),invalidateCatalog:vi.fn(),session:{user:{role:'ADMIN'}}}));
vi.mock('../src/api',()=>mocks);
it('resets only Diploma after the exact confirmation phrase',async()=>{
 localStorage.setItem('pyq-admin-tab','Catalog Sync');
 mocks.loadCatalog.mockResolvedValue({courses:[],meta:{terms:[],exams:[]}});
 mocks.api.mockImplementation(async(path)=>{
  if(path==='/admin/library-reset/preview')return {counts:{papers:10,questions:20,attempts:0}};
  if(path==='/admin/library-reset/diploma/preview')return {counts:{papers:5,questions:10,solutions:2},blockers:[]};
  if(path==='/admin/library-reset/diploma')return {before:{papers:5}};
  if(path.startsWith('/admin/ingestion'))return {items:[],total:0};
  if(path.startsWith('/admin/catalog/campaign'))return {groups:[]};
  return {};
 });
 const confirm=vi.spyOn(window,'confirm').mockReturnValue(true);
 const w=mount(Admin);await flushPromises();
 const button=w.findAll('button').find(b=>b.text()==='Reset Diploma only');
 expect(button.attributes('disabled')).toBeDefined();
 const label=w.findAll('label').find(l=>l.text().includes('RESET DIPLOMA'));
 await label.find('input').setValue('RESET DIPLOMA');await button.trigger('click');await flushPromises();
 expect(mocks.api).toHaveBeenCalledWith('/admin/library-reset/diploma',{method:'POST',body:{confirmation:'RESET DIPLOMA'}});
 expect(mocks.api.mock.calls.some(([path,options])=>path==='/admin/library-reset'&&options?.method==='POST')).toBe(false);
 w.unmount();confirm.mockRestore();localStorage.removeItem('pyq-admin-tab');
});
