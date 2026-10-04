import {it,expect,vi,afterEach} from 'vitest';
import {loadCatalog,invalidateCatalog,api} from '../src/api';
afterEach(()=>{invalidateCatalog();vi.unstubAllGlobals()});
it('shares a complete catalog request and reloads after a catalog mutation',async()=>{
 const payload={courses:Array.from({length:130},(_,id)=>({id,name:'Course '+id})),meta:{exams:[],terms:[]}};
 const fetch=vi.fn(async()=>({ok:true,json:async()=>payload}));vi.stubGlobal('fetch',fetch);
 const [a,b]=await Promise.all([loadCatalog(),loadCatalog()]);expect(fetch).toHaveBeenCalledTimes(1);expect(a.courses).toHaveLength(130);expect(a).toEqual(b);expect(a).not.toBe(b);a.courses[0].name='Changed locally';expect(b.courses[0].name).toBe('Course 0');
 invalidateCatalog();await loadCatalog();expect(fetch).toHaveBeenCalledTimes(2);
});
it('does not cache a failed catalog response and explains non-JSON upstream errors',async()=>{
 const fetch=vi.fn().mockResolvedValueOnce({ok:false,status:502,json:async()=>{throw Error('HTML')}}).mockResolvedValue({ok:true,json:async()=>({courses:[],meta:{}})});vi.stubGlobal('fetch',fetch);
 await expect(loadCatalog()).rejects.toThrow('temporarily unavailable');await expect(loadCatalog()).resolves.toHaveProperty('courses');expect(fetch).toHaveBeenCalledTimes(2);
});
