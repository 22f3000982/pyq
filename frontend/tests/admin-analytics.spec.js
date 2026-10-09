import {it,expect,vi,afterEach} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import AdminAnalytics from '../src/AdminAnalytics.vue';
const mocks=vi.hoisted(()=>({api:vi.fn()}));
vi.mock('../src/api',()=>mocks);
afterEach(()=>{vi.clearAllMocks();vi.useRealTimers()});
it('loads only on opening, period changes and refresh; shows empty metrics honestly',async()=>{
 mocks.api.mockResolvedValue({first_day:null,totals:{starts:0,completions:0,completion_rate:null,average_seconds:null,automatic:0},papers:[],courses:[],devices:[],trend:[],writer:{queued:0,dropped:0,failed:0}});
 vi.useFakeTimers();const w=mount(AdminAnalytics);await flushPromises();
 expect(mocks.api).toHaveBeenCalledWith('/admin/analytics?period=7d');
 expect(w.text()).toContain('No recorded attempts yet');expect(w.text()).toContain('—');
 await vi.advanceTimersByTimeAsync(30000);expect(mocks.api).toHaveBeenCalledTimes(1);
 await w.get('select').setValue('today');await flushPromises();
 expect(mocks.api).toHaveBeenLastCalledWith('/admin/analytics?period=today');
 await w.get('form').trigger('submit');await flushPromises();expect(mocks.api).toHaveBeenCalledTimes(3);w.unmount();
});
it('shows request failures with a retry button',async()=>{
 mocks.api.mockRejectedValue(Error('Unavailable'));
 const w=mount(AdminAnalytics);await flushPromises();
 expect(w.get('[role="alert"]').text()).toBe('Unavailable');expect(w.get('button').attributes('disabled')).toBeUndefined();w.unmount();
});
