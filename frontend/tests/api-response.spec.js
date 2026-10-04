import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {api,invalidateCatalog} from '../src/api';
beforeEach(()=>{localStorage.clear();invalidateCatalog()});
afterEach(()=>vi.unstubAllGlobals());
function response(data){vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>data})));}
it('preserves numeric paper counts in public and admin stats',async()=>{
 for(const papers of [0,722]){
  invalidateCatalog();
  const stats={papers,courses:39,questions:400,exam_papers:{'Quiz 1':22}};response(stats);
  expect(await api('/stats')).toEqual(stats);
 }
});
it('decorates paper arrays with browser-local latest progress',async()=>{
 localStorage.setItem('pyq-browser-progress-v1',JSON.stringify({'5':{attempted:true,last_score:85}}));
 response({papers:[{id:5,course_id:1}]});
 expect((await api('/search?q=paper')).papers[0].progress.last_score).toBe(85);
 response({items:[{id:5,course_id:1}]});
 expect((await api('/papers')).items[0].progress.last_score).toBe(85);
});
