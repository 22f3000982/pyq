import {it,expect,vi} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import {saveBrowse,rememberPaper,paperReturn} from '../src/browseState';
import ExamBrowser from '../src/ExamBrowser.vue';
import LoadingState from '../src/LoadingState.vue';
const mock=vi.hoisted(()=>({api:vi.fn(async()=>({items:[],total:50})),loadCatalog:vi.fn(async()=>({courses:[{id:4,name:'MLF',exams:{'Quiz 1':3}}],meta:{terms:[{id:8,name:'Jan 2026'}]}}))}));vi.mock('../src/api',()=>mock);
it('restores course term and page when returning to the paper list',async()=>{saveBrowse('/exam/Quiz%201',{course:4,term:8,page:2});rememberPaper(100,'/exam/Quiz%201');expect(paperReturn(100,'/')).toBe('/exam/Quiz%201');const w=mount(ExamBrowser,{props:{route:paperReturn(100,'/')}});await flushPromises();const params=new URLSearchParams(mock.api.mock.calls.at(-1)[0].split('?')[1]);expect(params.get('course_id')).toBe('4');expect(params.get('term_id')).toBe('8');expect(params.get('page')).toBe('2');w.unmount()});
it('shows estimated progress without claiming completion while pending',async()=>{vi.useFakeTimers();const w=mount(LoadingState);await vi.advanceTimersByTimeAsync(60000);expect(w.get('progress').attributes('value')).toBe('95');expect(w.text()).toContain('Estimated progress');w.unmount();expect(vi.getTimerCount()).toBe(0);vi.useRealTimers()});
