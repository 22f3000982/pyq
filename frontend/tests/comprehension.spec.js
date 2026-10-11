import {it,expect} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import ComprehensionLayout from '../src/ComprehensionLayout.vue';
it('keeps shared passage scroll position and resets for a new passage',async()=>{
 const w=mount(ComprehensionLayout,{props:{passage:'Shared data'},slots:{default:'Question one'}});
 const body=w.get('.comprehension-passage-body').element;body.scrollTop=120;
 await w.setProps({images:[]});expect(body.scrollTop).toBe(120);
 await w.setProps({passage:'Different data'});await flushPromises();expect(body.scrollTop).toBe(0);
 await w.get('.passage-toggle').trigger('click');expect(w.get('.passage-toggle').attributes('aria-expanded')).toBe('false');
 await w.get('.passage-toggle').trigger('click');expect(w.get('.passage-toggle').attributes('aria-expanded')).toBe('true');
 await w.setProps({passage:''});expect(w.find('.comprehension-split').exists()).toBe(false);expect(w.text()).toContain('Question one');w.unmount();
});
it('renders passage image tokens on the passage side',()=>{
 const w=mount(ComprehensionLayout,{props:{passage:'Table [[IMAGE:table]]',images:[{id:1,token:'table',url:'/table.png'},{id:2,token:'prompt',url:'/prompt.png'}]}});
 expect(w.findAll('img')).toHaveLength(1);expect(w.get('img').attributes('src')).toBe('/table.png');w.unmount();
});
