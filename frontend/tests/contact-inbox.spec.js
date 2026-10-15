import {it,expect,vi} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import ContactInbox from '../src/ContactInbox.vue';
const mocks=vi.hoisted(()=>({api:vi.fn()}));
vi.mock('../src/api',()=>mocks);
it('renders untrusted messages as text and resolves a message',async()=>{
 mocks.api.mockResolvedValueOnce({items:[{id:7,name:'Student',email:'student@example.com',topic:'General enquiry',message:'<script>alert(1)</script>',created_at:1,status:'OPEN'}],total:1});
 const w=mount(ContactInbox);await flushPromises();
 expect(w.text()).toContain('<script>alert(1)</script>');expect(w.find('script').exists()).toBe(false);
 expect(w.get('a').attributes('href')).toContain('mailto:');
 mocks.api.mockResolvedValueOnce({ok:true}).mockResolvedValueOnce({items:[],total:0});
 await w.findAll('button').find(b=>b.text()==='Mark resolved').trigger('click');await flushPromises();
 expect(mocks.api).toHaveBeenCalledWith('/admin/contact-messages/7',{method:'PATCH',body:{status:'RESOLVED'}});
 expect(w.text()).toContain('No messages.');w.unmount();
});
