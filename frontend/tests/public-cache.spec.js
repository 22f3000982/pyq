import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {api,invalidateCatalog} from '../src/api';
beforeEach(()=>{invalidateCatalog();localStorage.clear();vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({items:[{id:9,course_id:1,name:'Paper'}],total:1})}))});
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers()});
it('deduplicates public requests and reuses full paper details from list',async()=>{
 const [a,b]=await Promise.all([api('/papers?course_id=1'),api('/papers?course_id=1')]);
 a.items[0].name='changed';expect(b.items[0].name).toBe('Paper');
 expect((await api('/papers/9')).name).toBe('Paper');expect(fetch).toHaveBeenCalledTimes(1);
});
it('expires public data and isolates different filters',async()=>{
 vi.useFakeTimers();await api('/papers?course_id=1');await api('/papers?course_id=2');
 vi.advanceTimersByTime(15001);await api('/papers?course_id=1');expect(fetch).toHaveBeenCalledTimes(3);
});
it('never caches attempts and clears public content on writes',async()=>{
 await api('/papers/9');await api('/attempts/1');await api('/attempts/1');
 await api('/admin/questions/1',{method:'POST',body:{}});await api('/papers/9');
 expect(fetch).toHaveBeenCalledTimes(5);
});
it('does not cache failed requests',async()=>{
 fetch.mockRejectedValueOnce(new Error('offline'));await expect(api('/papers/9')).rejects.toThrow('offline');
 await api('/papers/9');expect(fetch).toHaveBeenCalledTimes(2);
});

it('home response primes catalog, metadata and stats without extra requests',async()=>{
 const home={courses:[{id:1,name:'Course'}],meta:{terms:[{id:2,name:'May'}]},stats:{papers:7}};
 fetch.mockResolvedValueOnce({ok:true,json:async()=>home});
 expect(await api('/home')).toEqual(home);
 expect((await api('/catalog')).courses).toEqual(home.courses);
 expect(await api('/metadata')).toEqual(home.meta);
 expect(await api('/stats')).toEqual(home.stats);
 expect(fetch).toHaveBeenCalledTimes(1);
});
