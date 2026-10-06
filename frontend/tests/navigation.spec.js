// @vitest-environment jsdom
import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {navigate,migrateLegacyRoute,installNavigation,currentRoute} from '../src/navigation';
let stop;
beforeEach(()=>{history.replaceState(null,'','/');vi.spyOn(window,'scrollTo').mockImplementation(()=>{});document.body.innerHTML=''});
afterEach(()=>{stop?.();stop=undefined;vi.restoreAllMocks()});
it('converts old shared hash links without extra history',()=>{
 history.replaceState(null,'','/#/paper/42');const replace=vi.spyOn(history,'replaceState');migrateLegacyRoute();
 expect(currentRoute()).toBe('/paper/42');expect(location.hash).toBe('');expect(replace).toHaveBeenCalledOnce();
});
it('navigates and responds to browser back/forward state',()=>{
 const update=vi.fn();stop=installNavigation(update);navigate('/attempt/7');expect(location.pathname).toBe('/attempt/7');expect(update).toHaveBeenLastCalledWith('/attempt/7');
 history.replaceState(null,'','/paper/42');window.dispatchEvent(new PopStateEvent('popstate'));expect(update).toHaveBeenLastCalledWith('/paper/42');
 history.replaceState(null,'','/attempt/7');window.dispatchEvent(new PopStateEvent('popstate'));expect(update).toHaveBeenLastCalledWith('/attempt/7');
});
it('intercepts app links but preserves new tabs downloads and public pages',()=>{
 stop=installNavigation(()=>{});document.body.innerHTML='<a href="/bookmarks"><span>Bookmarks</span></a>';
 const event=new MouseEvent('click',{bubbles:true,cancelable:true,button:0});document.querySelector('span').dispatchEvent(event);expect(event.defaultPrevented).toBe(true);expect(location.pathname).toBe('/bookmarks');
 for(const [href,attrs,modifier] of [['/paper/4','',true],['/study','',false],['/contact','',false],['/api/papers/4/pdf','download',false],['/about','target="_blank"',false],['https://example.com','',false]]){
  document.body.innerHTML=`<a href="${href}" ${attrs}>Open</a>`;
  const e=new MouseEvent('click',{bubbles:true,cancelable:true,button:0,ctrlKey:modifier});document.querySelector('a').dispatchEvent(e);expect(e.defaultPrevented).toBe(false);
 }
});
it('preserves encoded exam routes and rejects external navigation',()=>{
 navigate('/exam/Quiz%201');expect(currentRoute()).toBe('/exam/Quiz%201');expect(()=>navigate('https://example.com/')).toThrow();
});
