import {it,expect,vi} from 'vitest';import {mount,flushPromises} from '@vue/test-utils';import ImportSolutionBundle from '../src/ImportSolutionBundle.vue';
const mock=vi.hoisted(()=>({api:vi.fn()}));vi.mock('../src/api',()=>mock);
it('previews one bundled JSON then saves valid papers in one request',async()=>{
 mock.api.mockResolvedValue({papers:[{paper_id:1,paper_name:'Paper',missing:0,items:[{question_id:2,number:'1',text:'Explanation',status:'CHECKS_PASSED',checks:[]}]}],saved:1,published:1,needs_review:0});
 const w=mount(ImportSolutionBundle,{props:{paperIds:[1,2]}});
 expect(w.text()).toContain('2 / 5');const data={format:'pyq-solutions-bundle-v1',papers:[]};
 await w.get('textarea').setValue(JSON.stringify(data));
 await w.findAll('button').find(b=>b.text()==='Preview bundle').trigger('click');await flushPromises();
 expect(w.text()).toContain('Question 1');
 await w.findAll('button').find(b=>b.text()==='Save & Publish valid solutions').trigger('click');await flushPromises();
 expect(mock.api).toHaveBeenLastCalledWith('/admin/ai-solutions/bundle/import',{method:'POST',body:{bundle:data,replace_existing:false,save:true,publish:true}});
 expect(w.emitted('saved')).toHaveLength(1);w.unmount();
});
