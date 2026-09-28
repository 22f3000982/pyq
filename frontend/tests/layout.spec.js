import {describe,it,expect} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import MathText from '../src/MathText.vue';import QuestionContent from '../src/QuestionContent.vue';
describe('source fidelity',()=>{
 it('preserves dollar prices and word spaces, while rendering explicit mathematics',async()=>{
  const text='Worth $2000 and he offers it for sale. Players 2 and 3 pay $2,800 or $3,000.';
  const w=mount(MathText,{props:{text}});await flushPromises();expect(w.text()).toBe(text);expect(w.find('.katex').exists()).toBe(false);
  await w.setProps({text:'Value \\(x^{2}\\)'});await flushPromises();expect(w.find('.katex').exists()).toBe(true);w.unmount();
 });
 it('keeps inline images between their source words without duplicating assets',async()=>{
  const w=mount(QuestionContent,{props:{text:'Setup with [[IMAGE:l]] tables and [[IMAGE:k]] functions.\n[[IMAGE:graph]]\nWhich is correct?',images:[{id:1,token:'l',inline:true,width:2},{id:2,token:'k',inline:true,width:2},{id:3,token:'graph',inline:false,width:15}]}});await flushPromises();
  const nodes=[...w.element.children];expect(nodes.map(n=>n.tagName)).toEqual(['SPAN','IMG','SPAN','IMG','SPAN','IMG','SPAN']);expect(nodes[0].textContent).toBe('Setup with ');expect(nodes[2].textContent).toBe(' tables and ');expect(w.findAll('img')).toHaveLength(3);expect(w.findAll('.inline-notation')).toHaveLength(2);expect(w.text()).not.toContain('[[IMAGE:');expect(w.findAll('img')[0].attributes('style')).toContain('width: 2em');w.unmount();
 });
});
