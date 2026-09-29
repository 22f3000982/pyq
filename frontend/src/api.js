import {reactive} from 'vue';
export const session=reactive({user:null,csrf:''});
let catalogPromise;
const bootstraps=new Map();
export async function api(path,options={}){
 const {method='GET',body,form}=options;
 const initial=path.match(/^\/attempts\/(\d+)\?bootstrap=1$/);
 if(method==='GET'&&initial){const cached=bootstraps.get(initial[1]);bootstraps.delete(initial[1]);if(cached&&cached.user===session.user?.id&&Date.now()-cached.time<10000)return {...cached.data,server_time:cached.data.server_time+(Date.now()-cached.time)/1000}}
 if(path.startsWith('/auth/'))bootstraps.clear();
 const target=method==='POST'&&path==='/attempts'?path+'?bootstrap=1':path;
 const r=await fetch('/api'+target,{method,credentials:'same-origin',headers:{...(body?{'Content-Type':'application/json'}:{}),...(method!=='GET'?{'X-CSRF-Token':session.csrf}:{})},body:form|| (body?JSON.stringify(body):undefined)});
 let data;try{data=await r.json()}catch{const error=new Error('The server is temporarily unavailable. Please retry.');error.status=r.status;throw error;}
 if(!r.ok){const error=new Error(data.error||'Request failed');error.status=r.status;throw error;}
 if(method==='POST'&&path==='/attempts'&&data.items){bootstraps.clear();bootstraps.set(String(data.id),{data,time:Date.now(),user:session.user?.id})}
 if(data.csrf)session.csrf=data.csrf;
 return data;
}
export function loadCatalog(){
 if(!catalogPromise)catalogPromise=api('/catalog').catch(error=>{catalogPromise=null;throw error});
 return catalogPromise;
}
export function invalidateCatalog(){catalogPromise=null}
export async function loadSession(){const d=await api('/session');session.user=d.user;return d;}
export function go(path){window.location.hash=path;}
