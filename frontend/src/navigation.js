// History routing keeps SPA navigation immediate while exposing real URLs.
const routePattern=/^\/(?:|about|bookmarks|progress|history|dashboard|mistakes|login|admin(?:\/login)?|(?:course|paper|attempt|result)\/\d+|exam\/[^/]+)$/;
export function isAppPath(path){return routePattern.test(path)}
export function currentRoute(){return window.location.pathname}
export function migrateLegacyRoute(){
 const legacy=window.location.hash.slice(1);
 if(window.location.hash.startsWith('#/')&&isAppPath(legacy.split('?')[0])){
  window.history.replaceState(null,'',legacy);
 }
}
export function navigate(path){
 const url=new URL(path,window.location.origin);
 if(url.origin!==window.location.origin||!isAppPath(url.pathname))throw new Error('Invalid application route');
 if(url.pathname+url.search+url.hash!==window.location.pathname+window.location.search+window.location.hash){
  window.history.pushState(null,'',url.pathname+url.search+url.hash);
  window.dispatchEvent(new Event('appnavigate'));
 }
}
export function installNavigation(onRoute){
 migrateLegacyRoute();
 const changed=()=>{onRoute(currentRoute());window.scrollTo(0,0)};
 const click=e=>{
  if(e.defaultPrevented||e.button!==0||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;
  const a=e.target.closest?.('a[href]');
  if(!a||a.hasAttribute('download')||(a.target&&a.target!=='_self'))return;
  const raw=a.getAttribute('href');if(!raw||raw.startsWith('#'))return;
  const url=new URL(a.href,window.location.href);
  if(url.origin!==window.location.origin||!isAppPath(url.pathname)||url.hash)return;
  e.preventDefault();navigate(url.pathname+url.search);
 };
 const legacy=()=>{migrateLegacyRoute();changed()};
 window.addEventListener('popstate',changed);window.addEventListener('appnavigate',changed);
 window.addEventListener('hashchange',legacy);document.addEventListener('click',click);
 return ()=>{window.removeEventListener('popstate',changed);window.removeEventListener('appnavigate',changed);window.removeEventListener('hashchange',legacy);document.removeEventListener('click',click)};
}
