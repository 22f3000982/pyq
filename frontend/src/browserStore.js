const PROGRESS='pyq-browser-progress-v1',BOOKMARKS='pyq-browser-bookmarks-v1';
function read(key){try{const value=JSON.parse(localStorage.getItem(key)||'{}');return value&&typeof value==='object'&&!Array.isArray(value)?value:{}}catch{return {}}}
function write(key,value){try{localStorage.setItem(key,JSON.stringify(value))}catch{throw new Error('Your browser could not save progress or bookmarks. Allow site storage to keep them after closing this page.')}}
export function paperProgress(id){return read(PROGRESS)[String(id)]||null}
export function progressRows(){return Object.values(read(PROGRESS)).sort((a,b)=>b.last_attempted_at-a.last_attempted_at)}
export function saveResult(attempt){
 if(attempt.status!=='SUBMITTED'||!attempt.paper_id||attempt.records_progress===false||!attempt.result)return;
 const rows=read(PROGRESS),old=rows[String(attempt.paper_id)],time=attempt.submitted_at;
 if(old&&old.last_attempted_at>time)return;
 const parts=(attempt.title||'').replace(/^(?:(?:Assisted timed continuation|Practice continuation) · )+/,'').split(' · ');
 rows[String(attempt.paper_id)]={paper_id:attempt.paper_id,attempted:true,last_score:attempt.result.percentage,last_attempted_at:time,course:parts[0]||'',exam:parts[1]||'',term:parts[2]||'',name:parts[3]||attempt.title};
 write(PROGRESS,rows);
}
export function bookmarkRows(){return Object.values(read(BOOKMARKS))}
export function isBookmarked(id){return Boolean(read(BOOKMARKS)[String(id)])}
export function setBookmark(question,on){const rows=read(BOOKMARKS);if(on){if(!question?.id)throw new Error('Question unavailable for bookmarking.');rows[String(question.id)]=question}else delete rows[String(question.id)];write(BOOKMARKS,rows);return {bookmarked:on}}
export function localPage(rows,path){const params=new URLSearchParams(path.split('?')[1]||'');const page=Math.max(1,Number(params.get('page'))||1),limit=Math.min(100,Math.max(1,Number(params.get('limit'))||24));return {items:rows.slice((page-1)*limit,page*limit),total:rows.length,page,limit}}
