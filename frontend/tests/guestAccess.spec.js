import {describe,it,expect,vi,beforeEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import {reactive} from 'vue';
const state=vi.hoisted(()=>({api:vi.fn(),go:vi.fn()}));
vi.mock('../src/api',()=>({api:state.api,go:state.go,session:{user:null},loadCatalog:vi.fn()}));
import Catalog from '../src/Catalog.vue';
describe('direct paper entry',()=>{
 beforeEach(()=>{state.api.mockReset();state.go.mockReset()});
 it('starts an exam without requiring a signed-in user',async()=>{
  const paper={id:5,course_id:1,course:'Course',name:'Paper',exam:'Quiz 1',term:'Jan 2026',practice_available:true,question_count:1,source_metadata:{},warnings:[]};
  state.api.mockImplementation(async(path,options)=>path==='/papers/5'?paper:path==='/attempts'?{id:7}:{items:[]});
  const wrapper=mount(Catalog,{props:{route:'/paper/5'}});await flushPromises();
  await wrapper.findAll('button').find(b=>b.text()==='Start exam').trigger('click');await flushPromises();
  expect(state.api).toHaveBeenCalledWith('/attempts',expect.objectContaining({method:'POST',body:expect.objectContaining({paper_id:5,mode:'exam'})}));
  expect(state.go).toHaveBeenCalledWith('/attempt/7');expect(state.go).not.toHaveBeenCalledWith('/login');wrapper.unmount();
 });
});
