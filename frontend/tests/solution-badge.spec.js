// @vitest-environment jsdom
import {mount} from '@vue/test-utils';
import {it,expect} from 'vitest';
import SolutionBadge from '../src/SolutionBadge.vue';
it('distinguishes complete green and partial light green, hiding unavailable solutions',()=>{
 const full=mount(SolutionBadge,{props:{coverage:{total:17,published:17}}});
 expect(full.text()).toBe('Solutions · 17/17');expect(full.classes()).toContain('complete');
 const partial=mount(SolutionBadge,{props:{coverage:{total:17,published:15}}});
 expect(partial.text()).toBe('Solutions · 15/17');expect(partial.classes()).not.toContain('complete');
 expect(mount(SolutionBadge,{props:{coverage:{total:17,published:0}}}).find('span').exists()).toBe(false);
});
