// @vitest-environment jsdom
import {mount} from '@vue/test-utils';
import {describe,it,expect} from 'vitest';
import OppeText from '../src/OppeText.vue';
import {nextTick} from 'vue';
describe('OPPE statement rendering',()=>{
 it('renders tables and diagrams without allowing source HTML or arbitrary images',async()=>{
  const src='/api/admin/oppe/assets/'+'a'.repeat(64)+'.png';
  const wrapper=mount(OppeText,{props:{text:`| A | B |\n|---|---|\n| 1 | 2 |\n\n![diagram](${src})\n\n<img src=x onerror=alert(1)>\n\n![bad](https://example.com/tracker.png)\n\n[bad](javascript:alert(1))`}});
  await nextTick();await nextTick();
  expect(wrapper.findAll('table')).toHaveLength(1);
  expect(wrapper.findAll('img')).toHaveLength(1);
  expect(wrapper.find('img').attributes('src')).toBe(src);
  expect(wrapper.find('[onerror]').exists()).toBe(false);
  expect(wrapper.find('a[href^="javascript:"]').exists()).toBe(false);
 });
});
