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
it('shows charts, honest learning signals and actionable attention links',async()=>{
 mocks.api.mockResolvedValue({first_day:'2026-10-20',generated_at:1792454400,totals:{starts:5,completions:3,active_browsers:2,returning_browsers:1,exam_starts:3,practice_starts:2,active:1,abandoned:1,completion_rate:60,average_score:40,scored_exams:3},trend:[{day:'2026-10-20',starts:5,completions:3,exam_starts:3,practice_starts:2}],weekly:[],devices:[{name:'mobile',starts:5}],papers:[],courses:[],score_distribution:[],heatmap:[{weekday:1,hour:9,starts:5}],attention:{coverage:{questions:10,published:5,percent:50},open_reports:1,reports:[{id:1,question_id:42,number:'3',paper_id:9,issue:'Unclear text'}],unsolved:[{id:9,name:'Quiz 1',course:'Maths',starts:5,published:2,total:10,missing:8}],questions:[],low_score_papers:[]}});
 const w=mount(AdminAnalytics);await flushPromises();
 expect(w.findAll('svg[role="img"]').length).toBe(3);
 expect(w.text()).toContain('Returning browsers');expect(w.text()).toContain('50%');
 expect(w.text()).toContain('at least 20');expect(w.text()).not.toContain('Admin attempts and pre-installation history are excluded');
 await w.findAll('button').find(b=>b.text().includes('Upload / review solutions')).trigger('click');
 expect(w.emitted('solutions')[0]).toEqual([9]);
 await w.findAll('button').find(b=>b.text().includes('Review question')).trigger('click');
 expect(w.emitted('review-question')[0]).toEqual([42]);
 expect(w.findAll('.heat-cell')).toHaveLength(168);w.unmount();
});
it('passes mode and course scopes to reports and CSV without polling',async()=>{
 mocks.api.mockResolvedValue({totals:{starts:0},trend:[],papers:[],courses:[],devices:[],course_options:[{key:'MLF',name:'Machine Learning Foundations'}],attention:{}});
 const w=mount(AdminAnalytics);await flushPromises();
 await w.get('[aria-label="Analytics mode"]').setValue('exam');await flushPromises();
 expect(mocks.api).toHaveBeenLastCalledWith('/admin/analytics?period=7d&mode=exam');
 const select=w.findComponent({name:'SearchableSelect'});select.vm.$emit('update:modelValue','MLF');select.vm.$emit('change');await flushPromises();
 expect(mocks.api).toHaveBeenLastCalledWith('/admin/analytics?period=7d&course=MLF&mode=exam');
 expect(w.get('a').attributes('href')).toContain('course=MLF&mode=exam&format=csv');w.unmount();
});
