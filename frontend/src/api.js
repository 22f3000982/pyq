import {reactive} from 'vue';
export const session=reactive({user:null,csrf:''});
export async function api(path,options={}){
 const {method='GET',body,form}=options;
 const r=await fetch('/api'+path,{method,credentials:'same-origin',headers:{...(body?{'Content-Type':'application/json'}:{}),...(method!=='GET'?{'X-CSRF-Token':session.csrf}:{})},body:form|| (body?JSON.stringify(body):undefined)});
 const data=await r.json();
 if(!r.ok){const error=new Error(data.error||'Request failed');error.status=r.status;throw error;}
 if(data.csrf)session.csrf=data.csrf;
 return data;
}
export async function loadSession(){const d=await api('/session');session.user=d.user;return d;}
export function go(path){window.location.hash=path;}
