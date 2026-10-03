import {it,expect,vi,beforeEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import About from '../src/About.vue';
const mocks=vi.hoisted(()=>({api:vi.fn(),session:{user:{role:'GUEST'}}}));vi.mock('../src/api',()=>mocks);
const page={headline:'Practise',description:'<script>alert(1)</script>',name:'Ash',bio:'Student',photo_url:null};
beforeEach(()=>{mocks.session.user={role:'GUEST'};mocks.api.mockReset();mocks.api.mockResolvedValue({...page})});
it('shows public text safely without edit controls',async()=>{const w=mount(About);await flushPromises();expect(w.text()).toContain(page.description);expect(w.find('script').exists()).toBe(false);expect(w.text()).not.toContain('Edit About');w.unmount()});
it('allows admin editing and retains text on failure',async()=>{mocks.session.user={role:'ADMIN'};const w=mount(About);await flushPromises();await w.get('button').trigger('click');await w.get('input').setValue('New headline');mocks.api.mockRejectedValueOnce(new Error('Try again'));await w.get('form').trigger('submit');await flushPromises();expect(w.get('input').element.value).toBe('New headline');expect(w.text()).toContain('Try again');mocks.api.mockResolvedValueOnce({...page,headline:'New headline'});await w.get('form').trigger('submit');await flushPromises();expect(w.find('form').exists()).toBe(false);expect(w.text()).toContain('About page saved.');w.unmount()});
