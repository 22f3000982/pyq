import {it,expect,vi,afterEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import MathText from '../src/MathText.vue';
import ReplacementPdf from '../src/ReplacementPdf.vue';
import {api} from '../src/api';
vi.mock('../src/api',()=>({api:vi.fn()}));
afterEach(()=>vi.clearAllMocks());
it('renders restricted bold as safe text and leaves mathematical stars alone',async()=>{
 const w=mount(MathText,{props:{text:'Plain **bold <img src=x onerror=alert(1)>** and \\(x**2\\)'}});await flushPromises();
 expect(w.get('strong').text()).toBe('bold <img src=x onerror=alert(1)>');expect(w.find('img').exists()).toBe(false);expect(w.find('.katex').exists()).toBe(true);
 await w.setProps({text:'Normal text'});await flushPromises();expect(w.find('strong').exists()).toBe(false);w.unmount();
});
it('shows actual replacement request stages and restores upload after failure',async()=>{
 const w=mount(ReplacementPdf,{props:{paperId:1}});
 Object.defineProperty(w.get('input[type=file]').element,'files',{value:[new File(['PDF'],'paper.pdf',{type:'application/pdf'})]});await w.get('input').trigger('change');
 let reject;api.mockImplementation(()=>new Promise((_,r)=>reject=r));await w.get('form').trigger('submit');
 expect(w.text()).toContain('Uploading PDF…');expect(w.get('form button').attributes('disabled')).toBeDefined();
 await w.get('form').trigger('submit');expect(api).toHaveBeenCalledTimes(1);
 reject(Error('Connection failed'));await flushPromises();expect(w.text()).toContain('Connection failed');expect(w.get('form button').attributes('disabled')).toBeUndefined();w.unmount();
});
