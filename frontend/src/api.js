import {reactive} from 'vue';
import {paperProgress,progressRows,saveResult,bookmarkRows,isBookmarked,setBookmark,localPage} from './browserStore';
export const session=reactive({user:null,csrf:'',storageWarning:''});
let catalogPromise;
const bootstraps=new Map();
const publicReads=new Map();
let publicGeneration=0;
const clone=value=>JSON.parse(JSON.stringify(value));
const publicPath=path=>/^\/(?:catalog|metadata|papers(?:\/\d+)?)$/.test(path.split('?')[0]);
function clearPublicReads(){publicGeneration++;publicReads.clear();catalogPromise=null}

export async function api(path,options={}){
 const method=options.method||'GET';
 if(method!=='GET')clearPublicReads();
 if(method!=='GET'||!publicPath(path))return requestApi(path,options);
 const existing=publicReads.get(path);
 if(existing&&existing.expires>Date.now())return browserData(clone(await existing.promise));
 const generation=publicGeneration;
 const entry={expires:Date.now()+15000,promise:null};
 entry.promise=requestApi(path,options).then(data=>{
   if(generation===publicGeneration){
     entry.expires=Date.now()+15000;
     // List rows already contain the complete detail response. Reuse briefly.
     if(path.split('?')[0]==='/papers')for(const row of data.items||[]){
       publicReads.set('/papers/'+row.id,{expires:entry.expires,promise:Promise.resolve(clone(row))});
     }
     while(publicReads.size>100)publicReads.delete(publicReads.keys().next().value);
   }
   return clone(data);
 }).catch(error=>{if(publicReads.get(path)===entry)publicReads.delete(path);throw error});
 publicReads.set(path,entry);
 return browserData(clone(await entry.promise));
}
async function requestApi(path,options={}){
 let {method='GET',body,form}=options;
 if(method==='GET'&&path.split('?')[0]==='/progress')return localPage(progressRows(),path);
 if(method==='GET'&&path.split('?')[0]==='/bookmarks')return localPage(bookmarkRows(),path);
 const bookmark=path.match(/^\/questions\/(\d+)\/bookmark$/);
 if(bookmark&&['POST','DELETE'].includes(method))return setBookmark(body?.question||{id:Number(bookmark[1])},method==='POST');
 if(method==='POST'&&path==='/attempts'&&body?.collection==='bookmarks')body={...body,question_ids:bookmarkRows().map(q=>q.id).slice(0,500)};
 const initial=path.match(/^\/attempts\/(\d+)\?bootstrap=1$/);
 if(method==='GET'&&initial){const cached=bootstraps.get(initial[1]);bootstraps.delete(initial[1]);if(cached&&cached.user===session.user?.id&&Date.now()-cached.time<10000)return browserData({...cached.data,server_time:cached.data.server_time+(Date.now()-cached.time)/1000})}
 if(path.startsWith('/auth/'))bootstraps.clear();
 const createsAttempt=method==='POST'&&path==='/attempts';
 const target=createsAttempt?path+'?bootstrap=1':path;
 const r=await fetch('/api'+target,{method,credentials:'same-origin',headers:{...(body?{'Content-Type':'application/json'}:{}),...(method!=='GET'?{'X-CSRF-Token':session.csrf}:{})},body:form|| (body?JSON.stringify(body):undefined)});
 let data;try{data=await r.json()}catch{const error=new Error('The server is temporarily unavailable. Please retry.');error.status=r.status;throw error;}
 if(!r.ok){const error=new Error(data.error||'Request failed');error.status=r.status;throw error;}
 if(createsAttempt&&data.items){bootstraps.clear();bootstraps.set(String(data.id),{data,time:Date.now(),user:session.user?.id})}
 if(data.csrf)session.csrf=data.csrf;
 return browserData(data);
}
function browserData(data){
 if(data?.paper_id&&data.result){try{saveResult(data)}catch(e){session.storageWarning=e.message}}
 const decorate=row=>{if(row?.course_id&&row?.id)row.progress=paperProgress(row.id);if(row?.question)row.bookmarked=isBookmarked(row.question.id)};
 decorate(data);if(Array.isArray(data?.items))for(const row of data.items)decorate(row);
 if(Array.isArray(data?.papers))for(const row of data.papers)decorate(row);
 return data;
}
export function loadCatalog(){
 return api('/catalog');
}
export function invalidateCatalog(){clearPublicReads()}
export async function loadSession(){const d=await api('/session');session.user=d.user||{id:'browser',name:'Guest',role:'GUEST'};return d;}
export function go(path){window.location.hash=path;}
