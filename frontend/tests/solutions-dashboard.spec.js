import {it,expect,vi} from 'vitest';import {mount,flushPromises} from '@vue/test-utils';import AISolutions from '../src/AISolutions.vue';import SearchableSelect from '../src/SearchableSelect.vue';
const mocks=vi.hoisted(()=>({api:vi.fn()}));vi.mock('../src/api',()=>mocks);
it('uses course search then exam then paper, shows statistics, and removes worker controls',async()=>{
 mocks.api.mockImplementation(async path=>path==='/catalog'?{courses:[{id:1,name:'Game Theory',code:'GT'}]}:path==='/metadata'?{exams:[{id:2,name:'Quiz 1'}]}:path.startsWith('/admin/ai-solutions/summary')?{papers:[{id:3,name:'Paper',term:'May 2026',questions:4,uploaded:2,published:0}],statistics:{papers_total:1,papers_complete:0,papers_pending:1,papers_published:0,questions_total:4,questions_uploaded:2,questions_pending:2,questions_review:2}}:{items:[],total:0});
 const w=mount(AISolutions);await flushPromises();expect(w.text()).not.toContain('Generate');expect(w.text()).not.toContain('Worker');expect(w.text()).toContain('50%');expect(w.get('[aria-label="Filter solution level"]').exists()).toBe(true);expect(w.get('[aria-label="Filter solution year"]').exists()).toBe(true);expect(w.get('[aria-label="Filter solution term"]').exists()).toBe(true);expect(w.get('[aria-label="Choose solution exam"]').attributes('disabled')).toBeDefined();
 await w.get('[aria-label="Choose solution course"]').trigger('click');await w.get('[aria-label="Search options"]').setValue('gt');expect(w.findAll('.searchable-select-option')).toHaveLength(1);await w.get('.searchable-select-option').trigger('click');await flushPromises();expect(w.get('[aria-label="Choose solution exam"]').attributes('disabled')).toBeUndefined();expect(w.get('[aria-label="Choose solution paper"]').attributes('disabled')).toBeDefined();
 await w.get('[aria-label="Choose solution exam"]').setValue(2);await flushPromises();expect(w.get('[aria-label="Choose solution paper"]').attributes('disabled')).toBeUndefined();await w.get('[aria-label="Choose solution paper"]').setValue(3);await flushPromises();expect(w.find('textarea').exists()).toBe(true);expect(mocks.api.mock.calls.some(([p])=>p.startsWith('/admin/ai-solutions?paper_id=3'))).toBe(true);
 w.findComponent(SearchableSelect).vm.$emit('update:modelValue','');w.findComponent(SearchableSelect).vm.$emit('change','');await flushPromises();expect(w.find('[aria-label="Paper solution JSON"]').exists()).toBe(false);expect(w.find('[aria-label="Bundled solution JSON"]').exists()).toBe(true);expect(w.get('[aria-label="Choose solution exam"]').element.value).toBe('');w.unmount();
});

it('filters partial or missing solutions and opens the selected paper upload',async()=>{
 const papers=[{id:1,course:'Maths',name:'Partial',term:'Jan 2025',exam:'Quiz 1',questions:4,uploaded:2,published:1},{id:2,course:'Python',name:'Missing',questions:4,uploaded:0,published:0},{id:3,name:'Complete',questions:4,uploaded:4,published:4}];
 mocks.api.mockImplementation(async path=>path==='/catalog'?{courses:[]}:path==='/metadata'?{exams:[]}:path.startsWith('/admin/ai-solutions/summary')?{papers,statistics:{}}:{items:[],total:0});
 const w=mount(AISolutions);await flushPromises();await w.get('[aria-label="Filter solution availability"]').setValue('partial');expect(w.findAll('.solution-paper-row')).toHaveLength(1);expect(w.get('.solution-paper-row').text()).toContain('Partial');
 await w.get('.solution-paper-row button').trigger('click');await flushPromises();expect(w.find('textarea').exists()).toBe(true);
 await w.get('[aria-label="Filter solution availability"]').setValue('none');expect(w.findAll('.solution-paper-row')).toHaveLength(1);expect(w.get('.solution-paper-row').text()).toContain('Missing');w.unmount();
});
it('offers a searchable list course and only exams available under that course',async()=>{
 mocks.api.mockImplementation(async path=>path==='/catalog'?{courses:[{id:1,name:'Machine Learning Foundations',code:'MLF'}]}:path==='/metadata'?{exams:[{id:2,name:'Quiz 1'},{id:3,name:'Quiz 2'},{id:4,name:'End Term'}]}:path.startsWith('/admin/ai-solutions/summary')?{papers:[{id:7,course:'MLF',name:'Paper',exam_type_id:2,questions:1,uploaded:0,published:0}],statistics:{}}:{items:[],total:0});
 const w=mount(AISolutions);await flushPromises();
 await w.get('[aria-label="Filter solution course"]').trigger('click');await w.get('[aria-label="Search options"]').setValue('MLF');await w.get('.searchable-select-option').trigger('click');await flushPromises();
 const exam=w.get('[aria-label="Filter solution exam"]');expect(exam.findAll('option').map(o=>o.text())).toEqual(['All exams under this course','Quiz 1']);
 await exam.setValue('2');await flushPromises();expect(mocks.api.mock.calls.some(([p])=>p.includes('course_id=1&exam_type_id=2'))).toBe(true);w.unmount();
});

it('combines level year term and ET session, clearing session when switching to a quiz',async()=>{
 mocks.api.mockImplementation(async path=>path==='/catalog'?{courses:[{id:1,name:'Python',level:'foundation'},{id:2,name:'Java',level:'diploma'}]}:path==='/metadata'?{exams:[{id:3,name:'End Term'},{id:4,name:'Quiz 1'}],terms:[{year:2026},{year:2025}]}:path.startsWith('/admin/ai-solutions/summary')?{papers:[{id:9,exam_type_id:3,questions:1},{id:10,exam_type_id:4,questions:1}],statistics:{}}:{items:[],total:0});
 const w=mount(AISolutions);await flushPromises();
 expect(w.find('[aria-label="Filter solution session"]').exists()).toBe(false);
 await w.get('[aria-label="Filter solution level"]').setValue('foundation');await flushPromises();
 expect(w.findComponent(SearchableSelect).props('options').map(o=>o.label)).toEqual(['Python']);
 await w.get('[aria-label="Filter solution year"]').setValue('2025');await flushPromises();
 await w.get('[aria-label="Filter solution term"]').setValue('5');await flushPromises();
 const c=w.findComponent(SearchableSelect);c.vm.$emit('update:modelValue',1);c.vm.$emit('change');await flushPromises();
 await w.get('[aria-label="Filter solution exam"]').setValue('3');await flushPromises();
 await w.get('[aria-label="Filter solution session"]').setValue('AN');await flushPromises();
 const params=new URLSearchParams(mocks.api.mock.calls.filter(([p])=>p.includes('/summary?')).at(-1)[0].split('?')[1]);
 expect(Object.fromEntries(params)).toMatchObject({level:'foundation',year:'2025',month:'5',session:'AN',course_id:'1',exam_type_id:'3'});
 await w.get('[aria-label="Filter solution exam"]').setValue('4');await flushPromises();
 expect(w.find('[aria-label="Filter solution session"]').exists()).toBe(false);
 expect(mocks.api.mock.calls.filter(([p])=>p.includes('/summary?')).at(-1)[0]).toContain('session=');
 expect(mocks.api.mock.calls.filter(([p])=>p.includes('/summary?')).at(-1)[0]).not.toContain('session=AN');w.unmount();
});
