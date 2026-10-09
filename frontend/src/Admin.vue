<script setup>
import BusyFeedback from './BusyFeedback.vue';
import QuestionContent from './QuestionContent.vue';import QuestionEditor from './QuestionEditor.vue';import ReplacementPdf from './ReplacementPdf.vue';
import {defineAsyncComponent,ref,onMounted,onUnmounted} from 'vue';import {api,loadCatalog,invalidateCatalog,session} from './api';import MathText from './MathText.vue';import Upload from './Upload.vue';
const AISolutions=defineAsyncComponent(()=>import('./AISolutions.vue'));
const AdminAnalytics=defineAsyncComponent(()=>import('./AdminAnalytics.vue'));
const uploadForm=ref(null);
const tabs=['Analytics','Solutions','Content Reports','Processing','Upload PDFs','Papers','Question bank','Catalog Sync','Settings'];const savedTab=localStorage.getItem('pyq-admin-tab')?.replace('AI Solutions','Solutions');const tab=ref(tabs.includes(savedTab)?savedTab:'Processing');
const editingQuestion=ref(null),replacement=ref(null),questionStatus=ref('');
const reports=ref([]),reportStatus=ref('OPEN'),reportDetail=ref(null);
const stats=ref({}),jobs=ref([]),questions=ref([]),courses=ref([]),papers=ref([]),adminPapers=ref([]),meta=ref({terms:[],exams:[]}),course=ref(''),paper=ref(''),files=ref([]),error=ref(''),notice=ref(''),busy=ref(false),page=ref(1),total=ref(0),settings=ref({}),detail=ref(null),paperSearch=ref(''),paperStatus=ref(''),editPaper=ref(null),manageCourse=ref(''),syncFile=ref(null),syncPreview=ref(null),syncBatch=ref(null),batchLimit=ref(20),selectedChanged=ref([]),processNew=ref(true),processUnprocessed=ref(true),campaign=ref(null),resetPreview=ref(null),resetPhrase=ref(''),cleanupStorage=ref(true),catalogLevel=ref('Degree'),masterPreview=ref(null),masterFile=ref(null),driveStatus=ref(null),webRunnerActive=ref(false),webRunnerStop=ref(false),newPaper=ref({name:'',term_id:'',exam_type_id:'',session:''}),newTerm=ref({kind:'term',name:'',year:2026,month:9});let timer;
async function run(fn){if(busy.value)return;busy.value=true;error.value='';notice.value='';try{await fn()}catch(e){error.value=e.message}finally{busy.value=false}}
async function refresh(){stats.value=await api('/admin/stats');if(tab.value==='Content Reports'){const d=await api('/admin/content-reports?'+new URLSearchParams({status:reportStatus.value,page:page.value,limit:24}));reports.value=d.items;total.value=d.total}else if(tab.value==='Processing'){const d=await api('/admin/ingestion?page='+page.value);jobs.value=d.items;total.value=d.total}else if(tab.value==='Papers'){const d=await api('/admin/papers?'+new URLSearchParams({page:page.value,limit:24,q:paperSearch.value,status:paperStatus.value,course_id:manageCourse.value}));adminPapers.value=d.items;total.value=d.total}else if(tab.value==='Question bank'){const d=await api('/admin/questions?'+new URLSearchParams({page:page.value,paper_id:paper.value,status:questionStatus.value}));questions.value=d.items;total.value=d.total}else if(tab.value==='Settings')settings.value=await api('/admin/settings')}
async function chooseTab(t){if(busy.value)return;tab.value=t;localStorage.setItem('pyq-admin-tab',t);page.value=1;detail.value=null;await run(async()=>{await refresh();if(t==='Catalog Sync'){await loadCampaign();await loadResetPreview();await loadDriveStatus()}})}
async function loadPapers(){papers.value=(await api('/papers?limit=100&course_id='+course.value)).items;paper.value=''}
async function queue(retry=false){await run(async()=>{const d=await api('/admin/process-catalog',{method:'POST',body:{retry,limit:20}});notice.value=d.queued+' sources queued (maximum 20 this run). The worker stops after the bounded queue is exhausted.';await refresh()})}
function chooseFiles(e){files.value=Array.from(e.target.files).map(file=>({file,paper_id:paper.value}))}
async function upload(){await run(async()=>{if(files.value.some(f=>!f.paper_id))throw Error('Choose a paper for each PDF.');const form=new FormData();files.value.forEach(f=>form.append('files',f.file));form.append('paper_ids',JSON.stringify(files.value.map(f=>Number(f.paper_id))));const d=await api('/admin/papers/bulk-upload',{method:'POST',form});notice.value='Batch '+d.batch_id+' accepted. Extraction and availability are automatic; no approval is needed.';files.value=[];await refresh()})}
async function previewWorkbook(e){
 const file=e.target.files?.[0];if(!file)return;syncFile.value=file;syncPreview.value=null;selectedChanged.value=[];syncBatch.value=null;
 await run(async()=>{const form=new FormData();form.append('file',file);form.append('level',catalogLevel.value);syncPreview.value=await api('/admin/catalog/preview',{method:'POST',form});notice.value=syncPreview.value.already_applied?'This workbook was used before. Counts below show what is still pending now.':'Workbook checked. Nothing has been changed yet.'})
}
function chooseChanged(key,checked){selectedChanged.value=checked?[...new Set([...selectedChanged.value,key])]:selectedChanged.value.filter(x=>x!==key)}
async function refreshSyncBatch(){
 if(!syncBatch.value?.id)return;
 try{
  syncBatch.value=await api('/admin/catalog/batches/'+syncBatch.value.id);
  if(syncBatch.value.done){notice.value=`Batch complete: ${syncBatch.value.completed} successful, ${syncBatch.value.failed} failed.`;await loadCampaign()}
 }catch(e){error.value=e.message}
}
async function runWebBatch(){
 if(!syncBatch.value?.id||webRunnerActive.value)return;
 webRunnerActive.value=true;webRunnerStop.value=false;error.value='';let consecutiveFailures=0;
 try{
  while(!webRunnerStop.value&&syncBatch.value&&!syncBatch.value.done){
   const beforeFailed=syncBatch.value.failed||0,beforeCompleted=syncBatch.value.completed||0;
   syncBatch.value=await api('/admin/catalog/batches/'+syncBatch.value.id+'/run-next',{method:'POST',body:{}});
   await loadCampaign();
   const failedNow=(syncBatch.value.failed||0)>beforeFailed,completedNow=(syncBatch.value.completed||0)>beforeCompleted;
   consecutiveFailures=failedNow&&!completedNow?consecutiveFailures+1:0;
   if(consecutiveFailures>=3&&!syncBatch.value.done){
    webRunnerStop.value=true;
    notice.value='Processing paused automatically after 3 consecutive failures. Read the paper error messages below before retrying.';
    break
   }
   if(syncBatch.value.active>0&&syncBatch.value.queued===0&&!syncBatch.value.done){
    notice.value='A paper is still marked active. You can start another term batch; use Recover interrupted paper once recovery becomes available.';break
   }
  }
  if(syncBatch.value?.done)notice.value=syncBatch.value.completed?`Batch finished: ${syncBatch.value.completed} successful, ${syncBatch.value.failed} failed.`:`Batch finished with 0 successful and ${syncBatch.value.failed} failed. Read the failure reasons below before retrying.`;
  else if(webRunnerStop.value&&!notice.value)notice.value='Batch paused in this browser. Remaining papers are still safely queued.';
 }catch(e){error.value=e.message}
 finally{webRunnerActive.value=false}
}
async function retryPaper(item){await run(async()=>{const d=await api('/admin/catalog/files/'+item.id+'/retry',{method:'POST',body:{}});if(!d.queued)throw Error('Paper is already queued or available. Refresh status.');syncBatch.value={id:d.batch_id};await refreshSyncBatch();await loadCampaign();await runWebBatch()})}
async function recoverPaper(item){await run(async()=>{await api('/admin/catalog/files/'+item.id+'/recover',{method:'POST',body:{}});notice.value='Interrupted paper recovered. Use Retry failed to process it again; successful papers were preserved.';await refreshSyncBatch();await loadCampaign()})}
function pauseWebBatch(){webRunnerStop.value=true}
async function applyWorkbook(){
 if(!syncFile.value||!syncPreview.value)return;
 await run(async()=>{
  const form=new FormData();form.append('file',syncFile.value);form.append('level',catalogLevel.value);form.append('workbook_hash',syncPreview.value.workbook_hash);
  form.append('process_new',String(processNew.value));form.append('process_unprocessed',String(processUnprocessed.value));
  form.append('changed_keys',JSON.stringify(selectedChanged.value));form.append('batch_limit',String(batchLimit.value));
  const d=await api('/admin/catalog/apply',{method:'POST',form});
  notice.value=d.queued?`Batch #${d.batch_id} started: ${d.queued} papers queued. ${d.remaining_pending} remain for later batches.`:'No eligible papers were queued.';
  syncBatch.value=d.batch_id?{id:d.batch_id,total:d.queued,completed:0,failed:0,active:0,queued:d.queued,finished:0,percent:0,done:false,items:[]}:null;
  syncPreview.value=null;syncFile.value=null;selectedChanged.value=[];invalidateCatalog();await refreshCatalog();await refresh();await refreshSyncBatch();if(syncBatch.value&&!syncBatch.value.done)await runWebBatch();
 })
}
async function loadCampaign(){campaign.value=await api('/admin/catalog/campaign?level='+encodeURIComponent(catalogLevel.value))}
async function loadDriveStatus(){driveStatus.value=await api('/admin/google-drive/status')}
function connectDrive(){window.location.href='/api/admin/google-drive/connect'}
async function disconnectDrive(){if(!confirm('Disconnect Google Drive source access?'))return;await run(async()=>{await api('/admin/google-drive/disconnect',{method:'POST',body:{}});await loadDriveStatus();notice.value='Google Drive disconnected.'})}
async function loadResetPreview(){resetPreview.value=await api('/admin/library-reset/preview')}
function chooseMasterFile(e){masterFile.value=e.target.files?.[0]||null;masterPreview.value=null}
async function previewMasterCatalog(){await run(async()=>{const form=new FormData();form.append('file',masterFile.value);form.append('level',catalogLevel.value);masterPreview.value=await api('/admin/catalog/preview',{method:'POST',form})})}
async function refreshMasterCatalog(){
 if(!masterFile.value)throw Error('Choose the latest Excel workbook first.');
 await run(async()=>{const form=new FormData();form.append('file',masterFile.value);form.append('level',catalogLevel.value);const d=await api('/admin/catalog/refresh',{method:'POST',form});notice.value=`Master catalog refreshed: ${d.new_papers} new papers, ${d.existing_papers} already known. Nothing was queued.`;masterFile.value=null;masterPreview.value=null;invalidateCatalog();await refreshCatalog();await loadCampaign();await loadResetPreview()})
}
async function processCampaign(retry=false,selected=null){
 const target=selected||(retry?campaign.value?.retry_target:campaign.value?.current);if(!target)return;
 await run(async()=>{const endpoint=retry?'/admin/catalog/campaign/retry-failed':'/admin/catalog/campaign/process';const d=await api(endpoint,{method:'POST',body:{stage:target.stage,term_id:target.term_id,limit:20,level:catalogLevel.value}});notice.value=d.queued?`Batch #${d.batch_id}: ${d.queued} papers queued for ${target.label} · ${target.term}.`:(d.note||'Nothing to queue.');syncBatch.value=d.batch_id?{id:d.batch_id,total:d.queued,completed:0,failed:0,active:0,queued:d.queued,percent:0,done:false,items:[]}:null;await loadCampaign();if(syncBatch.value){await refreshSyncBatch();if(!syncBatch.value.done)await runWebBatch()}})
}
async function resetLibrary(){
 if(resetPhrase.value!=='RESET PYQ LIBRARY')return;
 const active=resetPreview.value?.counts?.active_ingestion||0;if(!confirm(active?active+' processing job(s) will be cancelled, then the PYQ library will be permanently cleared. User accounts stay untouched. Continue?':'This will permanently clear PYQ papers, questions, attempts, progress and bookmarks while keeping user accounts. Continue?'))return;
 await run(async()=>{const cancelActive=(resetPreview.value?.counts?.active_ingestion||0)>0;const d=await api('/admin/library-reset',{method:'POST',body:{confirmation:resetPhrase.value,cleanup_storage:cleanupStorage.value,cancel_active:cancelActive}});notice.value=d.warning?'Library reset completed, but R2 cleanup needs attention: '+d.warning:`Library reset complete. Removed ${d.before.papers} papers and ${d.before.questions} questions; R2 objects deleted: ${d.storage?.deleted??0}.`;resetPhrase.value='';syncBatch.value=null;campaign.value=null;invalidateCatalog();await refreshCatalog();await loadCampaign();await loadResetPreview();await refresh()})
}
async function createPaper(){await run(async()=>{if(!manageCourse.value)throw Error('Choose a course.');const d=await api('/admin/papers',{method:'POST',body:{...newPaper.value,course_id:Number(manageCourse.value),term_id:Number(newPaper.value.term_id),exam_type_id:Number(newPaper.value.exam_type_id)}});notice.value='Paper created. You can upload its PDF from Upload PDFs.';newPaper.value={name:'',term_id:'',exam_type_id:'',session:''};invalidateCatalog();await refreshCatalog();await refresh()})}
async function savePaper(){if(!editPaper.value)return;await run(async()=>{const p=editPaper.value;await api('/admin/papers/'+p.id,{method:'PATCH',body:{name:p.name,course_id:Number(p.course_id),term_id:Number(p.term_id),exam_type_id:Number(p.exam_type_id),session:p.session||'',duration_seconds:p.duration_seconds||null,source_url:p.source_url||null}});notice.value='Paper updated.';editPaper.value=null;invalidateCatalog();await refreshCatalog();await refresh()})}
async function archivePaper(p){if(!confirm('Hide this paper from students? Existing attempt snapshots remain safe.'))return;await run(async()=>{await api('/admin/papers/'+p.id+'/archive',{method:'POST',body:{}});notice.value='Paper archived and hidden from student pages.';invalidateCatalog();await refreshCatalog();await refresh()})}
async function restorePaper(p){await run(async()=>{await api('/admin/papers/'+p.id+'/restore',{method:'POST',body:{}});notice.value='Paper restored.';invalidateCatalog();await refreshCatalog();await refresh()})}
async function repairJavaSources(){await run(async()=>{const preview=await api('/admin/catalog/repair-java-2025',{method:'POST',body:{apply:false}});if(!preview.count){notice.value='No known swapped Java sources remain.';return}if(preview.active_jobs)throw Error('Java papers are already processing. Finish or recover those jobs first.');if(!confirm('Repair '+preview.count+' known Java/App Dev-1 source mappings for May/Sep 2025 and queue extraction? App Dev-1 question banks stay unchanged.'))return;const d=await api('/admin/catalog/repair-java-2025',{method:'POST',body:{apply:true}});notice.value=d.queued+' Java papers queued with corrected sources. Use Processing to run this batch.';invalidateCatalog();await refreshCatalog();await refresh()})}
async function deletePaper(p){if(!confirm('Permanently delete this catalog paper? This is allowed only when it has no linked questions, imports, attempts or progress.'))return;await run(async()=>{await api('/admin/papers/'+p.id,{method:'DELETE'});notice.value='Paper permanently deleted.';invalidateCatalog();await refreshCatalog();await refresh()})}
async function refreshCatalog(){invalidateCatalog();const catalog=await loadCatalog();courses.value=catalog.courses;meta.value=catalog.meta;await uploadForm.value?.refreshCatalog()}
onMounted(async()=>{if(session.user?.role!=='ADMIN')return;await run(async()=>{const catalog=await loadCatalog();courses.value=catalog.courses;meta.value=catalog.meta;await refresh();if(tab.value==='Catalog Sync'){await loadCampaign();await loadResetPreview();await loadDriveStatus()}const latest=await api('/admin/catalog/batches/latest');if(latest.batch_id){syncBatch.value={id:latest.batch_id};await refreshSyncBatch()}});timer=setInterval(()=>{if(tab.value==='Processing')refresh().catch(e=>error.value=e.message)},8000)});onUnmounted(()=>{webRunnerStop.value=true;clearInterval(timer)});
async function inspectReport(r){await run(async()=>{reportDetail.value=await api('/admin/content-reports/'+r.id)})}
async function resolveReport(r){await run(async()=>{await api('/admin/content-reports/'+r.id,{method:'PATCH',body:{status:r.status==='OPEN'?'RESOLVED':'OPEN'}});reportDetail.value=null;await refresh();notice.value='Report status updated.'})}
async function hideAndResolveReport(r){await run(async()=>{const q=await api('/admin/questions/'+r.question_id);await api('/admin/content-reports/'+r.id,{method:'PATCH',body:{status:'RESOLVED',hide_question:true,updated_at:q.updated_at}});reportDetail.value=null;invalidateCatalog();await refresh();notice.value='Question hidden and report resolved.'})}
async function openEditor(id,reportId=null){editingQuestion.value={id,reportId}}
async function failedQuestions(f){paper.value=String(f.paper_id);questionStatus.value='EXTRACTION_FAILED';await chooseTab('Question bank')}
async function toggleQuestion(q){await run(async()=>{const d=await api('/admin/questions/'+q.id);await api('/admin/questions/'+q.id+'/visibility',{method:'POST',body:{updated_at:d.updated_at,hidden:!q.hidden}});await refresh()})}
</script>
<template><QuestionEditor v-if="editingQuestion" :question-id="editingQuestion.id" :report-id="editingQuestion.reportId" @close="editingQuestion=null" @saved="run(refresh)"/><ReplacementPdf v-if="replacement" :paper-id="replacement.id" :paper-name="replacement.name" @close="replacement=null" @updated="run(refresh)"/><section v-if="session.user?.role!=='ADMIN'" class="empty panel"><h1>Administrator access required</h1><a href="/admin/login" class="btn btn-primary">Sign in</a></section><template v-else><div class="eyebrow">AUTOMATIC QUESTION BANK</div><h1>Processing & sources</h1><p class="muted">Upload once. Reliable questions become available automatically.</p><nav class="admin-tabs"><button v-for="t in tabs" :class="{active:tab===t}" @click="chooseTab(t)">{{t}}</button></nav><div v-if="error" class="alert alert-danger" role="alert">{{error}}</div><div v-if="busy" class="request-feedback" aria-busy="true"><BusyFeedback label="Working… Please wait."/></div><div v-if="notice" class="alert alert-success" role="status">{{notice}}</div>
<AdminAnalytics v-if="tab==='Analytics'"/><AISolutions v-if="tab==='Solutions'"/><template v-if="tab==='Content Reports'"><section class="panel mb-3"><div class="section-row"><div><h2>Content reports</h2><p class="muted mb-0">Review formatting issues reported by students. Mark resolved keeps the question visible. Hide & mark resolved removes it from new attempts.</p></div><button class="btn btn-light" :disabled="busy" @click="run(refresh)">Refresh</button></div><label>Report status<select class="form-select" v-model="reportStatus" @change="page=1;run(refresh)"><option value="OPEN">Open</option><option value="RESOLVED">Resolved</option><option value="ALL">All</option></select></label></section><article v-for="r in reports" :key="r.id" class="panel mb-3"><div class="section-row"><h3>{{r.paper}} · Q{{r.number}}</h3><span class="status">{{r.status}}</span></div><p><strong>{{r.issue}}</strong> · {{new Date(r.created_at*1000).toLocaleString()}}</p><p v-if="r.description" class="report-description">{{r.description}}</p><div class="d-flex gap-2 flex-wrap"><button class="btn btn-outline-primary" :disabled="busy" @click="inspectReport(r)">Review question</button><button class="btn btn-primary" @click="openEditor(r.question_id,r.id)">Edit question</button><button class="btn btn-light" :disabled="busy" @click="resolveReport(r)">{{r.status==='OPEN'?'Mark resolved':'Reopen'}}</button><button v-if="r.status==='OPEN'" class="btn btn-outline-danger" :disabled="busy" @click="hideAndResolveReport(r)">Hide &amp; mark resolved</button><a :href="'/paper/'+r.paper_id" class="btn btn-light">Open paper</a></div><section v-if="reportDetail?.id===r.id" class="report-preview mt-3"><QuestionContent :text="[reportDetail.question.passage,reportDetail.question.text].filter(Boolean).join('\n\n')" :images="reportDetail.question.images.filter(i=>!i.option_key)"/><div v-for="o in reportDetail.question.options" :key="o.key" class="review-option"><strong>{{o.key}}.</strong><QuestionContent :text="o.text" :images="reportDetail.question.images.filter(i=>i.option_key===o.key)"/></div></section></article><p v-if="!reports.length" class="empty panel">No {{reportStatus==='ALL'?'':reportStatus.toLowerCase()+' '}}reports.</p></template>
<template v-if="tab==='Processing'"><div class="admin-stat-grid"><div class="panel" v-for="k in ['papers','processed','queued','active_processing','failed','questions','flagged_questions']"><span class="eyebrow">{{k.replaceAll('_',' ')}}</span><strong>{{stats[k]??0}}</strong></div></div><details class="panel my-4"><summary>Advanced processing controls</summary><div class="d-flex gap-3 flex-wrap my-4"><button class="btn btn-primary" :disabled="busy" @click="queue(false)">Queue next 20 pending</button><button class="btn btn-outline-primary" :disabled="busy" @click="queue(true)">Retry next 20 failed/pending</button><button class="btn btn-light" @click="run(refresh)">Refresh</button></div></details><article class="panel job-card" v-for="f in jobs"><div class="section-row"><strong>#{{f.paper_id}} · {{f.filename}}</strong><span class="status">{{f.status}}</span></div><p class="muted small">{{f.extracted}} question records · {{f.pages??'—'}} pages · {{f.retries}} retries</p><a v-if="f.source_url" :href="f.source_url" target="_blank" rel="noopener noreferrer">Source link ↗</a><p v-if="f.error" class="alert alert-danger mt-3">{{f.error}}</p><details class="mt-3"><summary>Processing evidence & logs</summary><pre>{{JSON.stringify({events:f.events,warnings:f.warnings,duplicate_of:f.duplicate_of_id},null,2)}}</pre></details><div v-if="['PROCESSING_FAILED','EXTRACTION_FAILED'].includes(f.status)" class="d-flex gap-2 flex-wrap mt-3"><button class="btn btn-primary" @click="replacement={id:f.paper_id,name:f.filename}">Upload replacement PDF</button><button class="btn btn-light" @click="failedQuestions(f)">View failed questions</button></div><button v-if="['PROCESSING_FAILED','EXTRACTION_FAILED'].includes(f.status)" class="btn btn-light mt-3" @click="run(async()=>{await api('/admin/ingestion/'+f.id+'/retry',{method:'POST'});await refresh()})">Retry processing</button></article><p v-if="!jobs.length" class="empty panel">No processing jobs yet.</p></template>
<div v-if="tab==='Question bank'" class="filters"><select class="form-select" v-model="course" @change="run(loadPapers)" aria-label="Course"><option value="">Select course</option><option v-for="c in courses" :value="c.id">{{c.code}} · {{c.name}}</option></select><select class="form-select" v-model="paper" @change="page=1;run(refresh)" aria-label="Paper"><option value="">Select paper</option><option v-if="paper&&!papers.some(p=>String(p.id)===String(paper))" :value="paper">Paper #{{paper}}</option><option v-for="p in papers" :value="p.id">{{p.term}} · {{p.exam}} {{p.session}} · {{p.name}}</option></select><select class="form-select" v-model="questionStatus" @change="page=1;run(refresh)" aria-label="Question status"><option value="">All current questions</option><option value="AVAILABLE">Available</option><option value="HIDDEN">Hidden</option><option value="EXTRACTION_FAILED">Extraction failed</option></select></div>
<template v-if="tab==='Upload PDFs'"><Upload ref="uploadForm"/><details class="panel mb-4"><summary>Add a new term/year</summary><form @submit.prevent="run(async()=>{await api('/admin/metadata',{method:'POST',body:newTerm});await refreshCatalog();notice='Term added'})"><div class="form-grid"><label>Term name<input class="form-control" v-model="newTerm.name" placeholder="January 2027" required></label><label>Year<input type="number" v-model="newTerm.year" class="form-control" required></label><label>Month<input type="number" min="1" max="12" v-model="newTerm.month" class="form-control" required></label></div><button class="btn btn-primary mt-3">Add term</button></form></details></template><template v-if="tab==='Papers'">
<section class="panel mb-4"><div class="section-row"><div><h2>Manage papers</h2><button class="btn btn-outline-primary mb-2" :disabled="busy" @click="repairJavaSources">Repair Java / App Dev-1 May/Sep 2025</button><p class="muted mb-0">Edit metadata, hide unwanted papers, restore them later, or permanently delete empty catalog entries.</p></div><strong>{{total}} papers</strong></div>
<div class="filters mt-3"><input class="form-control" v-model="paperSearch" @keyup.enter="page=1;run(refresh)" placeholder="Search title, course, term or exam" aria-label="Search papers"><select class="form-select" v-model="manageCourse" @change="page=1;run(refresh)"><option value="">All courses</option><option v-for="c in courses" :value="c.id">{{c.code}} · {{c.name}}</option></select><select class="form-select" v-model="paperStatus" @change="page=1;run(refresh)"><option value="">All statuses</option><option value="ARCHIVED">Archived</option><option value="CATALOG_ONLY">Catalog only</option><option value="AVAILABLE">Available</option><option value="PARTIALLY_AVAILABLE">Partially available</option><option value="PROCESSING">Processing</option><option value="PROCESSING_FAILED">Processing failed</option><option value="EXTRACTION_FAILED">Extraction failed</option></select><button class="btn btn-primary" @click="page=1;run(refresh)">Search</button></div>
</section>
<details class="panel mb-4"><summary>Create a paper manually</summary><form @submit.prevent="createPaper" class="mt-3"><div class="form-grid"><label>Course<select class="form-select" v-model="manageCourse" required><option value="">Select course</option><option v-for="c in courses" :value="c.id">{{c.code}} · {{c.name}}</option></select></label><label>Exam type<select class="form-select" v-model="newPaper.exam_type_id" required><option value="">Select exam</option><option v-for="e in meta.exams" :value="e.id">{{e.name}}</option></select></label><label>Term<select class="form-select" v-model="newPaper.term_id" required><option value="">Select term</option><option v-for="t in meta.terms" :value="t.id">{{t.name}}</option></select></label><label>Session<input class="form-control" v-model="newPaper.session" placeholder="FN / AN"></label><label class="w-100">Paper title<input class="form-control" v-model="newPaper.name" required></label></div><button class="btn btn-primary mt-3" :disabled="busy">Create paper</button></form></details>
<section v-if="editPaper" class="panel mb-4"><div class="section-row"><h2>Edit paper #{{editPaper.id}}</h2><button class="btn btn-light" @click="editPaper=null">Cancel</button></div><div class="form-grid"><label>Title<input class="form-control" v-model="editPaper.name"></label><label>Course<select class="form-select" v-model="editPaper.course_id"><option v-for="c in courses" :value="c.id">{{c.code}} · {{c.name}}</option></select></label><label>Exam<select class="form-select" v-model="editPaper.exam_type_id"><option v-for="e in meta.exams" :value="e.id">{{e.name}}</option></select></label><label>Term<select class="form-select" v-model="editPaper.term_id"><option v-for="t in meta.terms" :value="t.id">{{t.name}}</option></select></label><label>Session<input class="form-control" v-model="editPaper.session"></label><label>Duration seconds<input class="form-control" type="number" min="30" max="28800" v-model="editPaper.duration_seconds"></label><label class="w-100">Source URL<input class="form-control" v-model="editPaper.source_url"></label></div><button class="btn btn-primary mt-3" :disabled="busy" @click="savePaper">Save changes</button></section>
<article class="panel mb-3" v-for="p in adminPapers" :key="p.id"><div class="section-row"><div><span class="eyebrow">#{{p.id}} · {{p.exam}} · {{p.term}} {{p.session}}</span><h3 class="mb-1">{{p.name}}</h3><p class="muted small mb-0">{{p.course}} · {{p.question_count}} questions · {{p.status}}</p></div><span class="status" :class="{ready:p.practice_available}">{{p.status}}</span></div><div class="d-flex gap-2 flex-wrap mt-3"><button class="btn btn-light" @click="editPaper={...p}">Edit</button><button v-if="p.status!=='ARCHIVED'" class="btn btn-light" @click="replacement={id:p.id,name:p.name}">Upload replacement PDF</button><a v-if="p.status!=='ARCHIVED'" class="btn btn-light" :href="'/paper/'+p.id">Open</a><button v-if="p.status!=='ARCHIVED'" class="btn btn-outline-primary" @click="archivePaper(p)">Archive</button><button v-else class="btn btn-outline-primary" @click="restorePaper(p)">Restore</button><button class="btn btn-light" @click="deletePaper(p)">Delete permanently</button></div></article>
<p v-if="!adminPapers.length" class="empty panel">No papers match these filters.</p>
</template>
<template v-if="tab==='Question bank'"><article class="panel mb-3" v-for="q in questions"><div class="section-row"><h3>Question {{q.number}} · {{q.kind}}</h3><span class="status">{{q.status}}</span></div><div class="d-flex gap-2 flex-wrap mb-3"><button class="btn btn-primary" @click="openEditor(q.id)">Edit question</button><button class="btn btn-light" :disabled="busy" @click="toggleQuestion(q)">{{q.hidden?'Restore question':'Hide question'}}</button></div><MathText :text="q.text"/><p class="small muted">Source pages: {{q.source_pages?.join(', ')||q.source_page}} · confidence {{Math.round(q.confidence*100)}}%</p><details><summary>Extraction metadata</summary><pre>{{JSON.stringify({answers:q.answers,marks:q.marks,negative_marks:q.negative_marks,evidence:q.evidence,warnings:q.warnings},null,2)}}</pre></details></article><p v-if="!questions.length" class="empty panel">Questions appear here after automatic processing.</p></template>
<template v-if="tab==='Catalog Sync'">
<section class="panel mb-4 campaign-guide">
 <div class="eyebrow">HOW TO USE — FIRST TIME</div>
 <h2>Build the PYQ library systematically</h2>
 <ol class="campaign-steps">
  <li><strong>Optional clean start:</strong> use Library Reset once if the current catalog is mixed/test data.</li>
  <li><strong>Connect Google Drive:</strong> authorize the Google/IITM account that can open the source PDFs. This is required for private links.</li>
  <li><strong>Upload the latest Excel:</strong> this creates the full source catalog only; it does not start 700 downloads.</li>
  <li><strong>Choose any term:</strong> use Process 20 on its card. Quiz 2 or End Term can be processed before Quiz 1; the highlighted target is only a suggestion.</li>
  <li><strong>Process 20 at a time:</strong> each batch stops automatically. Retry failed papers separately.</li>
  <li><strong>Future months:</strong> upload the newly updated Excel again; only new catalog entries are added.</li>
 </ol>
</section>

<section class="panel mb-4">
 <div class="section-row">
  <div><div class="eyebrow">GOOGLE DRIVE SOURCE ACCESS</div><h2>{{driveStatus?.connected?'Connected':'Connect the account that can open the PYQ PDFs'}}</h2>
   <p class="muted mb-0" v-if="driveStatus?.connected">Connected as {{driveStatus.email||'Google account'}}. Private/shared Drive PDFs can now be downloaded through the official Drive API.</p>
   <p class="muted mb-0" v-else-if="driveStatus?.configured">Authorize once with the Google/IITM account that can open the workbook paper links. The app stores only an encrypted refresh token.</p>
   <p class="muted mb-0" v-else>OAuth server credentials are not configured yet. Add the Google OAuth Client ID and Client Secret in Render, then use the redirect URI shown below.</p>
  </div>
  <span class="status" :class="{ready:driveStatus?.connected}">{{driveStatus?.connected?'CONNECTED':'NOT CONNECTED'}}</span>
 </div>
 <div v-if="driveStatus" class="mt-3">
  <p class="small muted mb-2"><strong>Authorized redirect URI:</strong> {{driveStatus.redirect_uri}}</p>
  <div class="d-flex gap-2 flex-wrap">
   <button v-if="driveStatus.configured&&!driveStatus.connected" class="btn btn-primary" @click="connectDrive">Connect Google Drive</button>
   <button v-if="driveStatus.connected" class="btn btn-outline-primary" @click="disconnectDrive">Disconnect</button>
   <button class="btn btn-light" @click="run(loadDriveStatus)">Refresh status</button>
  </div>
  <p v-if="!driveStatus.configured" class="alert alert-warning mt-3 mb-0">Render needs GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET. In Google Cloud, enable Google Drive API, create a Web application OAuth client, and add the redirect URI above exactly.</p>
 </div>
</section>

<section class="panel mb-4">
 <div class="section-row"><div><div class="eyebrow">MASTER EXCEL CATALOG</div><h2>Refresh source catalog</h2><p class="muted mb-0">Upload the student-maintained XLSX. Every valid linked paper becomes a catalog entry, but no PDF is processed until you start a campaign batch.</p></div></div>
 <label class="mt-3">Course level<select class="form-select" v-model="catalogLevel" :disabled="busy" @change="masterPreview=null;syncPreview=null;loadCampaign()"><option>Degree</option><option>Diploma</option><option>Foundation</option></select></label>
 <p class="muted">Choose the level, upload Excel, check the preview, then import. Course names come from Excel. Existing papers remain unchanged.</p>
 <input type="file" accept=".xlsx" class="form-control mt-3" @change="chooseMasterFile" :disabled="busy">
<button class="btn btn-outline-primary mt-3" :disabled="busy||!masterFile" @click="previewMasterCatalog">Preview Excel</button>
 <div v-if="masterPreview" class="mt-3"><p>{{masterPreview.summary.total}} papers · {{masterPreview.summary.new}} new · {{masterPreview.summary.invalid}} issues</p><p>Courses: {{masterPreview.courses.map(c=>c.name).join(", ")}}</p><p v-for="issue in masterPreview.issues">{{issue.sheet}} {{issue.cell}}: {{issue.warning}}</p></div>
 <button class="btn btn-primary mt-3" :disabled="busy||!masterFile||!masterPreview" @click="refreshMasterCatalog">Import catalog</button>
</section>

<section v-if="campaign" class="panel mb-4">
 <div class="section-row"><div><div class="eyebrow">FULL PYQ LIBRARY PROGRESS</div><h2>{{campaign.available}} / {{campaign.total}} papers ready</h2></div><strong class="campaign-percent">{{campaign.percent}}%</strong></div>
 <div class="batch-progress-track"><div class="batch-progress-fill" :style="{width:campaign.percent+'%'}"></div></div>
 <div class="admin-stat-grid mt-3">
  <div class="panel"><span class="eyebrow">available</span><strong>{{campaign.available}}</strong></div>
  <div class="panel"><span class="eyebrow">pending</span><strong>{{campaign.pending}}</strong></div>
  <div class="panel"><span class="eyebrow">queued</span><strong>{{campaign.queued}}</strong></div>
  <div class="panel"><span class="eyebrow">failed</span><strong>{{campaign.failed}}</strong></div>
 </div>
 <div v-if="campaign.current" class="campaign-current mt-3">
  <div><span class="eyebrow">CURRENT TARGET</span><h3>{{campaign.current.label}} · {{campaign.current.term}}</h3><p class="muted">{{campaign.current.available}} / {{campaign.current.total}} ready · {{campaign.current.pending}} pending · {{campaign.current.failed}} failed · {{campaign.current.queued}} queued</p></div>
  <div class="d-flex gap-2 flex-wrap"><button class="btn btn-primary" :disabled="busy||campaign.current.pending===0" @click="processCampaign(false)">Process next 20</button></div>
 </div>
 <p v-else class="alert mt-3 mb-0" :class="campaign.failed?'alert-warning':'alert-success'">{{campaign.failed?'All pending papers processed. Failed papers remain available for retry below.':'All catalog papers are complete.'}}</p>
 <div v-if="campaign.retry_target" class="mt-3">
  <p class="muted">{{campaign.retry_target.failed}} failed paper(s) in {{campaign.retry_target.label}} · {{campaign.retry_target.term}}. Failures do not block the next term.</p>
  <button class="btn btn-outline-primary" :disabled="busy||webRunnerActive" @click="processCampaign(true)">Retry failed (max 20)</button>
 </div>
</section>

<section v-if="campaign?.groups?.length" class="panel mb-4">
 <h2>Campaign roadmap</h2><p class="muted">Choose any assessment and term to process first. The display order is only a suggestion. A missing paper in Excel is absent from the total.</p>
 <div class="campaign-roadmap">
  <div v-for="g in campaign.groups" class="campaign-row" :class="{current:campaign.current&&g.stage===campaign.current.stage&&g.term_id===campaign.current.term_id,complete:g.complete}">
   <div><strong>{{g.label}}</strong><span>{{g.term}}</span></div>
   <div class="campaign-row-progress"><div class="batch-progress-track"><div class="batch-progress-fill" :style="{width:g.percent+'%'}"></div></div><small>{{g.available}}/{{g.total}} ready · {{g.pending}} pending<span v-if="g.failed"> · {{g.failed}} failed</span></small></div>
   <div class="campaign-term-actions"><strong>{{g.percent}}%</strong><button class="btn btn-outline-primary btn-sm" :disabled="busy||webRunnerActive||g.pending===0" @click="processCampaign(false,g)" :aria-label="'Process up to 20 papers: '+g.label+' · '+g.term">Process 20</button></div>
  </div>
 </div>
</section>

<section v-if="syncBatch" class="panel catalog-batch-progress mb-4">
 <div class="section-row"><div><div class="eyebrow">ACTIVE BATCH #{{syncBatch.id}}</div><h2>{{syncBatch.done?(syncBatch.completed?'Batch complete':'Batch failed — no papers imported'):(webRunnerActive?'Processing on this web service':'Batch queued / paused')}}</h2><p class="muted mb-0">Free mode processes one paper per request. Keep this admin tab open while running; closing it safely pauses after the current paper.</p></div><strong>{{syncBatch.percent??0}}%</strong></div>
 <div class="batch-progress-track"><div class="batch-progress-fill" :style="{width:(syncBatch.percent??0)+'%'}"></div></div>
 <div class="admin-stat-grid mt-3"><div class="panel"><span class="eyebrow">successful</span><strong>{{syncBatch.completed??0}}</strong></div><div class="panel"><span class="eyebrow">failed</span><strong>{{syncBatch.failed??0}}</strong></div><div class="panel"><span class="eyebrow">active</span><strong>{{syncBatch.active??0}}</strong></div><div class="panel"><span class="eyebrow">waiting</span><strong>{{syncBatch.queued??0}}</strong></div></div>
 <div v-if="syncBatch.done&&syncBatch.failed" class="alert alert-warning mt-3 mb-0"><strong>{{syncBatch.failed}} paper(s) reached a failure state.</strong> 100% here means the batch finished, not that it succeeded. The exact reason for each paper is shown below. Fix the common cause before retrying.</div>
 <div v-if="!syncBatch.done" class="d-flex gap-2 flex-wrap mt-3"><button v-if="!webRunnerActive" class="btn btn-primary" @click="runWebBatch">Resume processing</button><button v-else class="btn btn-outline-primary" @click="pauseWebBatch">Pause after current paper</button><button class="btn btn-light" :disabled="webRunnerActive" @click="refreshSyncBatch">Refresh status</button></div>
 <div class="sync-list mt-3"><div v-for="i in syncBatch.items||[]" class="sync-row sync-row-detail"><div><span>#{{i.paper_id}} · {{i.status}}</span><small v-if="['PROCESSING','FETCHING'].includes(i.status)">Started {{Math.floor((i.elapsed_seconds||0)/60)}} minutes ago. Recovery available after 30 minutes; other batches can proceed.</small><button v-if="['PROCESSING','FETCHING'].includes(i.status)" class="btn btn-outline-primary btn-sm" :disabled="busy||webRunnerActive||!i.recoverable" @click="recoverPaper(i)">Recover interrupted paper</button><small v-if="i.error" class="batch-error">{{i.error}}</small></div><strong>{{i.filename}}</strong><button v-if="['PROCESSING_FAILED','EXTRACTION_FAILED'].includes(i.status)" class="btn btn-outline-primary btn-sm" :disabled="busy||webRunnerActive" @click="retryPaper(i)">Retry this paper</button></div></div>
</section>

<details v-if="resetPreview" class="panel danger-zone mb-4">
 <summary><strong>Danger zone · Fresh library reset</strong></summary>
 <p class="muted mt-3">Use this once when the current PYQ catalog is mixed or uncertain. User accounts are preserved. Papers, questions, bookmarks, progress, temporary attempts, ingestion history, courses/terms/exam metadata and PYQ-owned R2 objects are cleared.</p>
 <div class="admin-stat-grid mt-3"><div class="panel"><span class="eyebrow">papers</span><strong>{{resetPreview.counts.papers}}</strong></div><div class="panel"><span class="eyebrow">questions</span><strong>{{resetPreview.counts.questions}}</strong></div><div class="panel"><span class="eyebrow">attempts</span><strong>{{resetPreview.counts.attempts}}</strong></div><div class="panel"><span class="eyebrow">R2 objects</span><strong>{{resetPreview.storage?.objects??'—'}}</strong></div></div>
 <label class="sync-choice mt-3"><input type="checkbox" v-model="cleanupStorage"><span><strong>Clean PYQ-owned R2 prefix too</strong><small>Recommended for a truly fresh start. Other prefixes/buckets are not touched.</small></span></label>
 <label class="mt-3">Type <strong>RESET PYQ LIBRARY</strong><input class="form-control mt-2" v-model="resetPhrase" autocomplete="off"></label>
 <button class="btn btn-danger mt-3" :disabled="busy||resetPhrase!=='RESET PYQ LIBRARY'" @click="resetLibrary">{{resetPreview.counts.active_ingestion?'Cancel processing & reset PYQ library':'Reset PYQ library'}}</button>
 <p v-if="resetPreview.counts.active_ingestion" class="alert alert-warning mt-3 mb-0">
   {{resetPreview.counts.stale_ingestion?resetPreview.counts.stale_ingestion+' stale processing marker(s) detected. ':''}}
   {{resetPreview.counts.live_ingestion?resetPreview.counts.live_ingestion+' job(s) are still marked active. ':''}}
   This full reset will cancel those jobs first, then clear the PYQ library.
 </p>
</details>
</template>
<section class="panel" v-if="tab==='Settings'"><h2>Extraction services</h2><dl class="settings-list"><template v-for="(v,k) in settings"><dt>{{k.replaceAll('_',' ')}}</dt><dd>{{String(v)}}</dd></template></dl><p class="muted">Native PDF colour/layout extraction runs automatically. Configured models assist extraction; source indicators always take precedence. Secrets remain on the server.</p></section>
<div v-if="['Content Reports','Processing','Papers','Question bank'].includes(tab)&&total>24" class="pagination-row"><button class="btn btn-light" :disabled="page===1" @click="page--;run(refresh)">Previous</button><span>Page {{page}}</span><button class="btn btn-light" :disabled="page*24>=total" @click="page++;run(refresh)">Next</button></div></template></template>
