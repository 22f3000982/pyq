<script setup>
import {displayExamTitle} from './displayTitle';
import BusyFeedback from './BusyFeedback.vue';
import {ref,reactive,onMounted,onUnmounted,computed,nextTick,defineAsyncComponent} from 'vue';import {Clock,Bookmark,ChevronLeft,ChevronRight,Flag,Check,WifiOff,BookOpen,NotebookPen,Calculator} from 'lucide-vue-next';
import SavedAISolution from './SavedAISolution.vue';
import ReportFormat from './ReportFormat.vue';import LoadingState from './LoadingState.vue';
import {api,go,session} from './api';import {clock,paletteLabel,answerText} from './utils';import MathText from './MathText.vue';import QuestionContent from './QuestionContent.vue';import AnswerValue from './AnswerValue.vue';const ScratchBoard=defineAsyncComponent(()=>import('./ScratchBoard.vue'));const TcsCalculator=defineAsyncComponent(()=>import('./TcsCalculator.vue'));
const props=defineProps({id:Number});const attempt=ref(null),item=ref(null),index=ref(0),value=ref(null),error=ref(''),saving=ref(false),feedback=ref(null),confirm=ref(false),showPalette=ref(false),seconds=ref(null),saved=ref('All responses saved'),pending=ref(null);
const navigating=ref(false),switching=ref(false),instructions=ref(false),submitting=ref(false),scratchOpen=ref(false),calculatorOpen=ref(false),natInput=ref(null);
const reportQuestion=ref(null),reportNotice=ref('');
const cache=reactive(new Map()),queued=new Map();let ticker,poller,draftTimer,saveTask=null,serverNow=0,received=0,stopped=false,inflight=null,timeoutRequested=false;const prefetched=new Set(),prefetchAssets=new Map(),prefetchTimers=new Set();
const key='pyq-pending-'+props.id,draftKey='pyq-draft-'+props.id,visitedKey='pyq-visited-'+props.id;
const checked=reactive(new Set()),checking=ref(false);
const current=computed(()=>attempt.value?.palette[index.value]);
function inflightEntries(){return Array.isArray(inflight)?inflight:(inflight?[inflight]:[])}
function journal(){if(stopped)return;const entries=[...inflightEntries(),...queued.values()];if(entries.length)sessionStorage.setItem(key,JSON.stringify(entries));else sessionStorage.removeItem(key)}
function saveVisited(){sessionStorage.setItem(visitedKey,JSON.stringify([...cache.values()].filter(d=>d.visited).map(d=>d.question.id)))}
function markVisited(qid){const d=cache.get(qid);if(!d||d.visited)return;d.visited=true;localState(qid);saveVisited()}
function localState(qid){const d=cache.get(qid),p=attempt.value?.palette.find(p=>p.question_id===qid);if(!p||!d)return;const answered=d.answer!==null&&d.answer!==''&&d.answer!==undefined&&(!Array.isArray(d.answer)||d.answer.length>0);p.state=d.marked?(answered?'ANSWERED_AND_MARKED_FOR_REVIEW':'MARKED_FOR_REVIEW'):answered?'ANSWERED':d.touched?'NOT_ANSWERED':d.visited?'VISITED':p.state}
async function sync(initial=false){try{const a=await api('/attempts/'+props.id+(initial?'?bootstrap=1':'/status'));if(stopped)return;if(initial)attempt.value=a;else if(attempt.value){attempt.value.status=a.status;attempt.value.deadline=a.deadline;attempt.value.submitted_at=a.submitted_at;attempt.value.expires_at=a.expires_at}serverNow=a.server_time;received=performance.now();if(initial)for(const qid of cache.keys())localState(qid);if(a.status!=='ACTIVE'){sessionStorage.removeItem(key);sessionStorage.removeItem(draftKey);sessionStorage.removeItem(visitedKey);go('/result/'+a.id)}return a}catch(e){error.value=e.message}}
function scheduleHeartbeat(){clearTimeout(poller);if(stopped||!attempt.value?.deadline)return;const delay=600000+Math.floor(Math.random()*300000);poller=setTimeout(async()=>{await sync();scheduleHeartbeat()},delay)}
function show(n){index.value=n;item.value=cache.get(current.value.question_id);value.value=item.value.answer;feedback.value=checked.has(current.value.question_id)?item.value.feedback||null:null;sessionStorage.setItem('pyq-position-'+props.id,String(n));if(item.value?.question.kind==='NAT')nextTick(()=>natInput.value?.focus({preventScroll:true}))}
function prefetchImages(qid){
 const images=cache.get(qid)?.question.images||[];
 for(const img of images){
  const url=img.url||'/api/images/'+img.id+'?proxy=1';
  if(prefetched.has(url))continue;
  prefetched.add(url);
  const asset=new Image();asset.decoding='async';asset.fetchPriority='low';
  // Retain the Image object until completion so browser work is not discarded by GC.
  prefetchAssets.set(url,asset);
  const done=()=>prefetchAssets.delete(url);
  asset.onload=done;asset.onerror=done;asset.src=url;
 }
}
function later(fn,delay){
 const id=setTimeout(()=>{prefetchTimers.delete(id);if(!stopped)fn()},delay);prefetchTimers.add(id);return id
}
function idle(fn,timeout=1800){
 if(typeof requestIdleCallback==='function')return requestIdleCallback(()=>!stopped&&fn(),{timeout});
 return later(fn,900)
}
function prefetchNext(n){
 const p=attempt.value?.palette;if(!p)return;
 const connection=navigator.connection||navigator.mozConnection||navigator.webkitConnection;
 // Respect explicit data-saving and very slow mobile connections.
 const constrained=connection?.saveData||['slow-2g','2g'].includes(connection?.effectiveType);
 const strong=constrained?1:3,idleCount=constrained?0:2;
 for(let offset=1;offset<=strong;offset++){
  const qid=p[n+offset]?.question_id;if(!qid)break;
  later(()=>prefetchImages(qid),180+(offset-1)*220);
 }
 for(let offset=strong+1;offset<=strong+idleCount;offset++){
  const qid=p[n+offset]?.question_id;if(!qid)break;
  idle(()=>prefetchImages(qid),1600+(offset-strong)*500);
 }
}
function open(n){if(n<0||n>=attempt.value.palette.length||submitting.value)return;show(n);markVisited(current.value.question_id);prefetchNext(n)}
function scheduleSave(delay=250){clearTimeout(draftTimer);draftTimer=setTimeout(()=>drain(),delay)}
function persist(data){
 const d=cache.get(data.question_id);if(!d)return Promise.resolve(false);
 if('answer' in data){checked.delete(data.question_id);d.answer=data.answer;d.touched=true;d.feedback=null;if(current.value?.question_id===data.question_id){value.value=data.answer;feedback.value=null}}
 if('marked' in data)d.marked=data.marked;
 d.visited=true;localState(data.question_id);saveVisited();
 queued.set(data.question_id,{...queued.get(data.question_id),...data});journal();saved.value='Saving…';scheduleSave(attempt.value?.mode==='practice'?120:250);return Promise.resolve(true);
}
function drain(){
 clearTimeout(draftTimer);
 if(saveTask)return saveTask;
 if(!queued.size)return Promise.resolve(true);
 saveTask=(async()=>{
  saving.value=true;
  try{
   while(queued.size&&!stopped){
    const batch=[...queued.entries()].slice(0,20);
    for(const [qid] of batch)queued.delete(qid);
    inflight=batch.map(([,data])=>data);journal();
    try{
     const response=await api(`/attempts/${props.id}/answers`,{method:'POST',body:{items:inflight}});
     for(const result of response.items||[]){
      const qid=result.question_id,d=cache.get(qid);
      if(result.feedback&&!queued.has(qid)&&d){d.feedback=result.feedback;if(current.value?.question_id===qid&&checked.has(qid))feedback.value=result.feedback}
     }
     inflight=null;pending.value=null;
    }catch(e){
     for(const data of inflightEntries())queued.set(data.question_id,{...data,...queued.get(data.question_id)});
     inflight=null;pending.value=[...queued.values()].at(-1)||null;journal();saved.value='Response pending — retry to save';error.value=e.message;
     if(e.status===409){await sync();return false}
     return false;
    }
   }
   if(!queued.size){inflight=null;pending.value=null;journal();saved.value='All responses saved';return true}
   saved.value='Responses pending';return false;
  }finally{saving.value=false}
 })().finally(()=>{saveTask=null});
 return saveTask;
}
async function retry(){
 error.value='';clearTimeout(draftTimer);
 if(saveTask)await saveTask;
 const ok=await drain();
 if(ok){sessionStorage.removeItem(key);saved.value='All responses saved'}
 return ok;
}
function editText(v){
 value.value=v;feedback.value=null;const qid=current.value.question_id;checked.delete(qid);const d=cache.get(qid);d.answer=v;d.touched=true;d.visited=true;d.feedback=null;localState(qid);saveVisited();
 queued.set(qid,{...queued.get(qid),question_id:qid,answer:v});journal();saved.value='Unsaved response';scheduleSave(500);
}
async function flushText(){clearTimeout(draftTimer);return drain()}
function answer(v){return persist({question_id:current.value.question_id,answer:v})}
async function checkAnswer(){
 if(checking.value||attempt.value?.mode!=='practice')return;
 checking.value=true;const qid=current.value.question_id;
 try{if(!await flushText())return;if(current.value.question_id!==qid)return;
 const d=cache.get(qid);if(!d.feedback){const row=await api(`/attempts/${props.id}/questions/${qid}`);d.feedback=row.feedback}
 if(current.value.question_id===qid&&attempt.value.mode==='practice'){checked.add(qid);feedback.value=d.feedback||null}
 }catch(e){error.value=e.message}finally{checking.value=false}
}
function choiceFeedback(key){
 if(attempt.value?.mode!=='practice'||!feedback.value||!Array.isArray(feedback.value.answers))return {};
 const correct=feedback.value.answers.includes(key);
 return {'option-correct':correct,'option-incorrect':Array.isArray(value.value)&&value.value.includes(key)&&!correct};
}
function compactAnswer(answer){
 if(['MCQ','MSQ','TRUE_FALSE'].includes(item.value?.question.kind)&&Array.isArray(answer))return answer.length?answer.map(key=>{const n=item.value.question.options.findIndex(o=>o.key===key);return n<0?'Unavailable':String.fromCharCode(65+n)}).join(', '):'Not answered';
 return answerText(answer);
}
function option(k){const kind=item.value.question.kind;return answer(kind==='MSQ'?(Array.isArray(value.value)&&value.value.includes(k)?value.value.filter(x=>x!==k):[...(Array.isArray(value.value)?value.value:[]),k]):[k])}
async function natEnter(){
 clearTimeout(draftTimer);await drain();
 if(index.value<attempt.value.palette.length-1)open(index.value+1);
}
async function bookmark(){const target=item.value,qid=current.value.question_id,old=target.bookmarked;target.bookmarked=!old;try{await api('/questions/'+qid+'/bookmark',{method:old?'DELETE':'POST',body:old?undefined:{question:target.question}})}catch(e){target.bookmarked=old;error.value=e.message}}
async function submit(){
 if(submitting.value)return;submitting.value=true;clearTimeout(draftTimer);
 try{
  const ok=await flushText();if(!ok&&seconds.value!==0){error.value='Save pending responses before submitting.';return}
  await api(`/attempts/${props.id}/submit`,{method:'POST'});sessionStorage.removeItem(key);sessionStorage.removeItem(draftKey);sessionStorage.removeItem(visitedKey);go('/result/'+props.id);
 }catch(e){error.value=e.message}finally{submitting.value=false}
}
function markNext(){persist({question_id:current.value.question_id,marked:true});if(index.value<attempt.value.palette.length-1)open(index.value+1)}
function keyboard(e){if(!['ArrowLeft','ArrowRight'].includes(e.key)||e.altKey||e.ctrlKey||e.metaKey||e.shiftKey||confirm.value||switching.value||instructions.value||reportQuestion.value||e.target?.closest?.('input,textarea,select,[contenteditable="true"],[role="dialog"]'))return;e.preventDefault();open(index.value+(e.key==='ArrowRight'?1:-1))}
async function switchMode(){
 if(submitting.value)return;
 submitting.value=true;switching.value=true;
 try{
  if(!await flushText()){error.value='Save pending responses before switching mode.';return}
  const next=await api('/attempts/'+props.id+'/switch-mode',{method:'POST',body:{mode:attempt.value.mode==='exam'?'practice':'exam',duration_seconds:5400}});
  Object.assign(attempt.value,{mode:next.mode,title:next.title,deadline:next.deadline,expires_at:next.expires_at});
  for(const d of cache.values())d.feedback=null;
  for(const row of next.feedback||[]){const d=cache.get(row.question_id);if(d)d.feedback=row.feedback}
  checked.clear();feedback.value=null;
  serverNow=next.server_time;received=performance.now();timeoutRequested=false;
  seconds.value=next.deadline?Math.max(0,Math.ceil(next.deadline-next.server_time)):null;
  scheduleHeartbeat();error.value='';
 }catch(e){error.value=e.message}finally{submitting.value=false;switching.value=false}
}

async function online(){retry();await sync();scheduleHeartbeat()}
async function visible(){if(document.visibilityState==='visible'&&performance.now()-received>120000){await sync();scheduleHeartbeat()}}
function leaving(e){if(queued.size||inflight){journal();e.preventDefault();e.returnValue=''}}
onMounted(async()=>{try{
 const bundle=await sync(true);if(stopped||!attempt.value||attempt.value.status!=='ACTIVE')return;
 if(stopped)return;if(bundle.status!=='ACTIVE')return go('/result/'+props.id);
 for(const d of bundle.items){cache.set(d.question.id,d)}
 let localVisited=[];try{localVisited=JSON.parse(sessionStorage.getItem(visitedKey)||'[]')}catch{};if(!Array.isArray(localVisited))localVisited=[];
 for(const qid of localVisited){const d=cache.get(qid);if(d)d.visited=true}
 let restored=JSON.parse(sessionStorage.getItem(key)||'[]');if(!Array.isArray(restored))restored=[restored];
 const draft=JSON.parse(sessionStorage.getItem(draftKey)||'null');if(draft)restored.push(draft);
 for(const data of restored){const d=cache.get(data.question_id);if(d){if('answer' in data){checked.delete(data.question_id);d.answer=data.answer;d.touched=true}if('marked' in data)d.marked=data.marked;queued.set(data.question_id,{...queued.get(data.question_id),...data})}}
 if(queued.size){const latest=[...queued.values()].at(-1);pending.value=latest;error.value='Response pending — retry to save';}
 sessionStorage.removeItem(draftKey);
 open(Math.max(0,Math.min(Number(sessionStorage.getItem('pyq-position-'+props.id))||0,attempt.value.palette.length-1)));
 const tick=()=>{seconds.value=attempt.value?.deadline?Math.max(0,Math.ceil(attempt.value.deadline-serverNow-(performance.now()-received)/1000)):null;if(seconds.value===0&&!timeoutRequested){timeoutRequested=true;submit()}};tick();ticker=setInterval(tick,1000);scheduleHeartbeat();
 window.addEventListener('keydown',keyboard);window.addEventListener('online',online);window.addEventListener('beforeunload',leaving);document.addEventListener('visibilitychange',visible);
}catch(e){error.value=e.message}});
onUnmounted(()=>{if(attempt.value?.status==='ACTIVE'&&!submitting.value){void api('/attempts/'+props.id,{method:'DELETE'}).catch(()=>{});for(const k of [key,draftKey,visitedKey,'pyq-position-'+props.id])sessionStorage.removeItem(k)}stopped=true;clearInterval(ticker);clearTimeout(poller);clearTimeout(draftTimer);for(const id of prefetchTimers)clearTimeout(id);prefetchTimers.clear();prefetchAssets.clear();window.removeEventListener('online',online);window.removeEventListener('keydown',keyboard);window.removeEventListener('beforeunload',leaving);document.removeEventListener('visibilitychange',visible)});
</script>
<template><template v-if="attempt"><header class="exam-header"><a class="exam-logo" href="#/progress"><BookOpen/> MauryaHub PYQ</a><div><span class="eyebrow">{{attempt.mode==='exam'?'TIMED EXAM':'PRACTICE SESSION'}}</span><h1>{{displayExamTitle(attempt.title)}}</h1></div><button class="btn btn-light mode-switch" @click="switchMode" :disabled="submitting">{{switching?'Switching…':('Switch to '+(attempt.mode==='exam'?'practice':'exam'))}}</button><button class="btn btn-light exam-tool-button mobile-hide-tool" @click="scratchOpen=!scratchOpen"><NotebookPen :size="15"/>Scratch</button><button class="btn btn-light exam-tool-button" aria-label="Open calculator" @click="calculatorOpen=!calculatorOpen"><Calculator :size="15"/>Calculator</button><button class="btn btn-light mobile-hide-tool" @click="instructions=true">Instructions</button><div class="timer" :class="{urgent:seconds!==null&&seconds<120}"><Clock :size="19"/>{{seconds===null?'Untimed':clock(seconds)}}</div></header><div class="cbt-section-bar"><strong>Section 1 · Question paper</strong><span>{{session.user?.name||'Guest'}} · {{attempt.mode==='exam'?'Exam mode':'Practice mode'}}</span></div><div v-if="error" class="alert alert-danger" role="alert">{{error}}<button v-if="pending" class="btn btn-light ms-3" @click="retry" :disabled="saving">Retry save</button></div><div class="exam-layout"><section class="question-panel panel" v-if="item"><div class="section-row"><span class="eyebrow">QUESTION {{item.question.number}} · {{index+1}} OF {{attempt.palette.length}}</span><div class="question-tools"><button @click="bookmark" class="btn btn-light btn-sm"><Bookmark :size="17" :fill="item.bookmarked?'currentColor':'none'"/>{{item.bookmarked?'Bookmarked':'Bookmark'}}</button><button class="btn btn-light btn-sm" @click="reportQuestion={id:item.question.id,number:String(item.question.number)}"><Flag :size="16"/>Report Broken Format</button></div></div><div class="question-content"><div class="question-meta"><span>{{item.question.kind.replace('_',' / ')}}</span><span>{{item.question.marks===null?'Marks not specified':'+'+item.question.marks+' marks'}}</span><span v-if="item.question.negative_marks">−{{item.question.negative_marks}} incorrect</span></div>
<div>
  <QuestionContent :text="item.question.passage ? item.question.passage+'\n\n'+item.question.text : item.question.text" :images="item.question.images.filter(i=>!i.option_key)" class="question-stem"/>
  <div v-if="['MCQ','MSQ','TRUE_FALSE'].includes(item.question.kind)" class="options"><button v-for="(o,oi) in item.question.options" class="option" :class="{chosen:Array.isArray(value)&&value.includes(o.key),...choiceFeedback(o.key)}" :aria-pressed="Array.isArray(value)&&value.includes(o.key)" :disabled="submitting" @click="option(o.key)"><span class="option-key" :class="{'option-key-square':item.question.kind==='MSQ'}">{{String.fromCharCode(65+oi)}}</span><div><QuestionContent :text="o.text" :images="item.question.images.filter(i=>i.option_key===o.key)"/></div><Check v-if="Array.isArray(value)&&value.includes(o.key)" :size="20" class="ms-auto"/></button><p v-if="item.question.kind==='MSQ'" class="muted small">Select all correct options. Correct subsets earn proportional marks; any wrong option earns zero. No negative marking.</p></div>
  <label v-else-if="item.question.kind==='NAT'">Your numerical answer (number or fraction)<input ref="natInput" type="text" inputmode="decimal" enterkeyhint="next" autocomplete="off" spellcheck="false" class="form-control numeric-answer" :value="value" @input="editText($event.target.value)" @blur="flushText()" @keydown.enter.prevent="natEnter" :disabled="navigating||submitting"><small class="nat-hint">Negative, decimal and fraction values are supported. Press Enter for next question.</small></label>
  <label v-else-if="item.question.kind==='SHORT_TEXT'">Your answer (follow the source format)<input class="form-control" type="text" :value="value" @input="editText($event.target.value)" @blur="flushText()" :disabled="navigating" maxlength="20000"></label>
  <label v-else>Your answer<textarea class="form-control long-answer" :value="value" @input="editText($event.target.value)" @blur="flushText()" :disabled="navigating" maxlength="20000" rows="9"></textarea><small>Written and code responses remain ungraded. Code is not executed.</small></label>
  <div v-if="attempt.mode==='practice'" class="check-answer-row"><button class="btn btn-outline-primary" @click="checkAnswer" :disabled="checking||submitting||value===null||value===''||Array.isArray(value)&&!value.length"><BusyFeedback v-if="checking" label="Checking…"/><template v-else>Check answer</template></button></div>
  <div v-if="feedback&&attempt.mode==='practice'" class="feedback compact-feedback" :class="'feedback-'+feedback.outcome.toLowerCase()" role="status"><span class="feedback-outcome">{{feedback.outcome==='PARTIAL'?'PARTIALLY CORRECT':feedback.outcome}}</span><span v-if="feedback.awarded!==null&&feedback.awarded!==undefined" class="feedback-marks">Marks: {{Number(feedback.awarded.toFixed(2))}} / {{item.question.marks}}</span><div class="feedback-summary"><span>Your answer: <strong>{{compactAnswer(value)}}</strong></span><span aria-hidden="true">·</span><span>Correct: <strong>{{compactAnswer(feedback.answers)}}</strong></span></div><MathText v-if="feedback.explanation" :text="feedback.explanation"/><SavedAISolution :attempt-id="id" :question-id="item.question.id"/></div>
</div></div><div class="save-status" role="status"><Check v-if="!pending" :size="15"/><WifiOff v-else :size="15"/>{{saved}}</div><div class="question-actions"><button class="btn btn-review" :disabled="submitting" @click="markNext">Mark for review &amp; next</button><button class="btn btn-light" :disabled="submitting" @click="answer(null)">Clear response</button><button class="btn btn-review" :disabled="submitting" @click="persist({question_id:current.question_id,marked:!item.marked})"><Flag :size="16"/>{{item.marked?'Unmark review':'Mark for review'}}</button><div class="spacer"></div><button class="btn btn-light" @click="open(index-1)" :disabled="index===0||submitting"><ChevronLeft :size="17"/>Previous</button><button class="btn btn-primary" @click="open(index+1)" :disabled="index===attempt.palette.length-1||submitting">Save &amp; next<ChevronRight :size="17"/></button></div></section>
<aside class="palette-panel panel" :class="{'palette-open':showPalette}"><button class="palette-toggle text-btn" @click="showPalette=!showPalette">Question palette {{showPalette?'−':'+'}}</button><div :class="{'mobile-hidden':!showPalette}"><h2 class="palette-heading">Question palette</h2><p class="muted small">{{attempt.palette.filter(p=>p.state.startsWith('ANSWERED')).length}} / {{attempt.palette.length}} answered</p><div class="palette"><button v-for="(p,n) in attempt.palette" :class="[p.state,{current:n===index}]" :aria-label="'Question '+(p.number||n+1)+', '+paletteLabel(p.state)" :aria-current="n===index?'step':undefined" :disabled="submitting" @click="open(n)">{{p.number||n+1}}</button></div><div class="palette-legend"><div v-for="s in ['ANSWERED','NOT_ANSWERED','NOT_VISITED','MARKED_FOR_REVIEW','ANSWERED_AND_MARKED_FOR_REVIEW']"><i :class="s"></i>{{paletteLabel(s)}}</div><div><i class="current"></i>Current question</div></div></div><button class="btn btn-primary w-100 mt-3" @click="confirm=true" :disabled="submitting">Submit {{attempt.mode==='exam'?'exam':'practice'}}</button><p class="small muted mt-3 mb-0">← / → previous / next question. Responses are saved temporarily during this session. {{attempt.mode==='exam'?'The server enforces the deadline, including after refresh.':'Click Check answer to reveal answers and marks.'}}</p></aside></div>
<ReportFormat v-if="reportQuestion" :question-id="reportQuestion.id" :number="reportQuestion.number" @close="reportQuestion=null" @sent="reportNotice=$event"/><div v-if="reportNotice" class="report-toast panel" role="status">{{reportNotice}}<button class="text-btn" @click="reportNotice=''" aria-label="Dismiss report confirmation">Dismiss</button></div><ScratchBoard :session-id="id" v-if="scratchOpen" @close="scratchOpen=false"/><TcsCalculator v-if="calculatorOpen" @close="calculatorOpen=false"/><div v-if="instructions" class="modal-backdrop-custom"><section class="confirm-dialog panel" role="dialog" aria-modal="true" aria-labelledby="instructions-title"><h2 id="instructions-title">Exam instructions</h2><ul><li>Use the question palette or ← / → keys to navigate. Arrow shortcuts are disabled while typing.</li><li>Responses save automatically. Use Clear response to remove your answer.</li><li>Green: answered. Orange: visited without an answer. Grey: not visited. Purple: marked for review. Purple with a tick: answered and marked.</li><li>Marked answers are included in scoring.</li><li>The server submits timed attempts when time expires. Practice is untimed.</li><li>Keys and explanations appear after submission in exam mode.</li></ul><button class="btn btn-primary" @click="instructions=false">Back to questions</button></section></div><div v-if="confirm" class="modal-backdrop-custom"><section class="confirm-dialog panel" role="dialog" aria-modal="true" aria-labelledby="submit-title"><h2 id="submit-title">Finish this attempt?</h2><p>You have answered {{attempt.palette.filter(p=>p.state.startsWith('ANSWERED')).length}} of {{attempt.palette.length}} questions. Marked answers are included in scoring.</p><div class="d-flex gap-3"><button class="btn btn-light" @click="confirm=false" :disabled="submitting">Keep working</button><button class="btn btn-primary" @click="submit" :disabled="submitting"><BusyFeedback v-if="submitting" label="Submitting…"/><template v-else>Submit attempt</template></button></div></section></div></template><div v-else><p v-if="error" role="alert" class="alert alert-danger">{{error}}</p><LoadingState v-else title="Loading your session…"/></div></template>
