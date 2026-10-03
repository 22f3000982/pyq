const memory=new Map();
export function readBrowse(key){try{return JSON.parse(sessionStorage.getItem('pyq-browse:'+key)||'null')||memory.get(key)||{}}catch{return memory.get(key)||{}}}
export function saveBrowse(key,value){memory.set(key,value);try{sessionStorage.setItem('pyq-browse:'+key,JSON.stringify(value))}catch{}}
export function rememberPaper(id,route){saveBrowse('paper:'+id,{route})}
export function paperReturn(id,fallback){const route=readBrowse('paper:'+id).route;return typeof route==='string'&&/^\/(exam|course)\//.test(route)?route:fallback}
