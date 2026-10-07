<script setup>
import {ref,computed,nextTick,onMounted,onUnmounted} from 'vue';
import {api} from './api';
import ImportPaperSolutions from './ImportPaperSolutions.vue';
import SearchableSelect from './SearchableSelect.vue';
import MathText from './MathText.vue';
import QuestionContent from './QuestionContent.vue';
import BusyFeedback from './BusyFeedback.vue';
const courses=ref([]),exams=ref([]),papers=ref([]),statistics=ref({}),course=ref(''),exam=ref(''),paper=ref(''),page=ref(1),total=ref(0),items=ref([]),selected=ref([]),error=ref(''),busy=ref(false),loading=ref(false),preview=ref(null),editText=ref('');
const coverage=ref('all'),paperSearch=ref('');
const filteredPapers=computed(()=>papers.value.filter(p=>{const matches={all:true,none:!p.published,partial:p.published>0&&p.published<p.questions,complete:p.published===p.questions,missing:p.uploaded<p.questions,partial_upload:p.uploaded>0&&p.uploaded<p.questions,review:p.review>0,outdated:p.outdated>0};return matches[coverage.value]&&[p.course,p.name,p.term,p.exam].join(' ').toLowerCase().includes(paperSearch.value.toLowerCase())}));
async function openUpload(p){paper.value=p.id;await choosePaper();await nextTick();document.getElementById('paper-solution-import')?.scrollIntoView?.({behavior:'smooth',block:'start'})}
let stopped=false,scopeVersion=0,rowsVersion=0;
const courseOptions=computed(()=>courses.value.map(c=>({value:c.id,label:c.name+(c.code?' · '+c.code:'')})));
const selectedPaper=computed(()=>papers.value.find(p=>String(p.id)===String(paper.value)));
const publishable=computed(()=>selected.value.length>0&&selected.value.every(id=>items.value.some(i=>i.question_id===id&&['CHECKS_PASSED','DRAFT'].includes(i.solution?.status))));
const percent=computed(()=>Math.round((statistics.value.questions_uploaded||0)*100/(statistics.value.questions_total||1)));
async function loadSummary(){const n=++scopeVersion,d=await api('/admin/ai-solutions/summary?'+new URLSearchParams({course_id:course.value,exam_type_id:exam.value}));if(stopped||n!==scopeVersion)return;papers.value=d.papers;statistics.value=d.statistics}
async function loadRows(){const n=++rowsVersion;if(!paper.value){items.value=[];total.value=0;return}const d=await api('/admin/ai-solutions?'+new URLSearchParams({paper_id:paper.value,page:page.value}));if(stopped||n!==rowsVersion)return;items.value=d.items;total.value=d.total}
async function refresh(){await Promise.all([loadSummary(),loadRows()])}
async function run(fn){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){error.value=e.message}finally{busy.value=false}}
async function changeScope(){paper.value='';page.value=1;selected.value=[];preview.value=null;++rowsVersion;items.value=[];total.value=0;loading.value=true;error.value='';try{await loadSummary()}catch(e){error.value=e.message}finally{loading.value=false}}
async function chooseCourse(){exam.value='';await changeScope()}
async function choosePaper(){page.value=1;selected.value=[];preview.value=null;items.value=[];total.value=0;loading.value=true;error.value='';try{await loadRows()}catch(e){error.value=e.message}finally{loading.value=false}}
async function action(qid,action,text){await run(async()=>{await api('/admin/ai-solutions/'+qid,{method:'POST',body:{action,text}});await refresh();if(action==='edit')preview.value=null})}
async function bulkPublish(){await run(async()=>{for(const id of selected.value)await api('/admin/ai-solutions/'+id,{method:'POST',body:{action:'publish'}});selected.value=[];await refresh()})}
async function nextPage(delta){page.value+=delta;selected.value=[];await run(loadRows)}
onMounted(()=>run(async()=>{const [catalog,meta]=await Promise.all([api('/catalog'),api('/metadata')]);courses.value=catalog.courses||[];exams.value=meta.exams||[];await loadSummary()}));
onUnmounted(()=>{stopped=true;++scopeVersion;++rowsVersion});
</script>
<template>
<section class="panel">
 <div class="section-row"><div><h2>Solutions</h2><p class="muted">Choose a course, exam and paper. Export questions, then paste or upload solutions and review before publishing.</p></div><button class="btn btn-light" :disabled="busy||loading" @click="run(refresh)">Refresh</button></div>
 <p v-if="error" role="alert" class="alert alert-danger">{{error}}</p>
 <fieldset class="solution-filters" :disabled="busy||loading">
  <label>1. Course<SearchableSelect v-model="course" :options="courseOptions" placeholder="Select course" search-placeholder="Search course name or code…" aria-label="Choose solution course" @change="chooseCourse"/></label>
  <label>2. Exam<select aria-label="Choose solution exam" class="form-select" v-model="exam" :disabled="!course||busy||loading" @change="changeScope"><option value="">Select Quiz 1 / Quiz 2 / ET</option><option v-for="e in exams" :key="e.id" :value="e.id">{{/end|term/i.test(e.name)?'ET · '+e.name:e.name}}</option></select></label>
  <label>3. Paper<select aria-label="Choose solution paper" class="form-select" v-model="paper" :disabled="!course||!exam||busy||loading" @change="choosePaper"><option value="">Select paper</option><option v-for="p in filteredPapers" :key="p.id" :value="p.id">{{p.term}} {{p.session?'· '+p.session:''}} · {{p.name}} · {{p.uploaded}}/{{p.questions}} solutions</option></select></label>
 </fieldset>
 <div v-if="busy||loading" class="my-3"><BusyFeedback label="Loading solutions…"/></div>
 <h3 class="mt-3">{{course?'Selected course'+(exam?' and exam':''):'All courses'}} · Solution progress</h3>
 <div class="solution-statistics" aria-label="Paper solution statistics">
  <div><strong>{{statistics.papers_total||0}}</strong><span>Processed papers</span></div>
  <div><strong>{{statistics.papers_complete||0}}</strong><span>All solutions uploaded</span></div>
  <div><strong>{{statistics.papers_pending||0}}</strong><span>Papers pending</span></div>
  <div><strong>{{statistics.papers_published||0}}</strong><span>Fully published</span></div>
 </div>
 <progress class="solution-progress" aria-label="Uploaded solution progress" :max="statistics.questions_total||1" :value="statistics.questions_uploaded||0"></progress><strong class="ms-2">{{percent}}%</strong>
 <p class="small muted">{{statistics.questions_uploaded||0}} / {{statistics.questions_total||0}} question solutions uploaded · {{statistics.questions_pending||0}} missing or outdated · {{statistics.questions_review||0}} awaiting review/publish. {{statistics.papers_partial||0}} partly uploaded papers · {{statistics.papers_not_started||0}} not started. Hidden questions and papers without extracted questions are excluded. Uploaded does not mean published.</p>
 <div class="solution-list-filters"><label>Solution availability<select class="form-select" aria-label="Filter solution availability" v-model="coverage"><option value="all">All papers</option><option value="none">No published solutions</option><option value="partial">Partially published</option><option value="complete">Fully published</option><option value="missing">Missing / outdated uploads</option><option value="partial_upload">Partially uploaded</option><option value="review">Awaiting review / publish</option><option value="outdated">Outdated solutions</option></select></label><label>Find paper<input class="form-control" type="search" aria-label="Search solution papers" v-model="paperSearch" placeholder="Course, paper or term…"></label></div>
 <p class="muted">Published coverage: {{statistics.papers_published||0}} complete · {{statistics.papers_partial_published||0}} partial · {{statistics.papers_without_published||0}} with no published solutions.</p>
 <div class="solution-paper-list"><article v-for="p in filteredPapers" :key="p.id" class="solution-paper-row"><div><strong>{{p.course}} · {{p.name}}</strong><p class="muted mb-0">{{p.exam}} · {{p.term}} {{p.session}} — {{p.published}} / {{p.questions}} published · {{p.uploaded}} uploaded · {{p.questions-p.uploaded}} missing / outdated</p></div><button class="btn btn-outline-primary" :disabled="busy||loading" @click="openUpload(p)">{{p.uploaded<p.questions?'Upload solution':p.published<p.questions?'Review / publish':'View solutions'}}</button></article><p v-if="!loading&&!busy&&!filteredPapers.length">No papers match these filters.</p></div>
 <p v-if="selectedPaper" class="status">This paper: {{selectedPaper.uploaded}} / {{selectedPaper.questions}} uploaded · {{selectedPaper.published}} published</p>
</section>
<ImportPaperSolutions id="paper-solution-import" v-if="paper" :key="paper" :paper-id="paper" @saved="run(refresh)"/>
<p v-else class="panel mt-3 muted">Select course → exam → paper to upload and review its solutions.</p>
<section v-if="paper" class="panel mt-3"><div class="d-flex flex-wrap gap-2"><button class="btn btn-light" :disabled="busy||!publishable" @click="bulkPublish">Publish selected drafts</button><button class="btn btn-light" :disabled="busy" @click="selected=items.filter(i=>['CHECKS_PASSED','DRAFT'].includes(i.solution?.status)).map(i=>i.question_id)">Select publishable drafts on this page</button></div><p class="small muted mt-3">Format and answer-key checks do not verify the reasoning. Review each solution before publishing.</p></section>
<article v-for="i in items" :key="i.question_id" class="panel mt-3">
 <label><input type="checkbox" :value="i.question_id" v-model="selected" :disabled="busy"> Q{{i.number}} · {{i.kind}} · {{i.solution?.status?.replaceAll('_',' ')||'No solution'}}</label>
 <div class="d-flex flex-wrap gap-2 mt-3"><button class="btn btn-light" :disabled="busy" @click="preview=i;editText=i.solution?.text||''">Preview / edit</button><button v-if="i.solution&&['CHECKS_PASSED','DRAFT'].includes(i.solution.status)" class="btn btn-primary" :disabled="busy" @click="action(i.question_id,'publish')">Publish</button><button v-if="i.solution?.status==='PUBLISHED'" class="btn btn-light" :disabled="busy" @click="action(i.question_id,'unpublish')">Unpublish</button></div>
</article>
<div v-if="paper&&total>24" class="pagination-row"><button class="btn btn-light" :disabled="page===1||busy" @click="nextPage(-1)">Previous</button><span>{{page}} · {{total}} questions</span><button class="btn btn-light" :disabled="page*24>=total||busy" @click="nextPage(1)">Next</button></div>
<div v-if="preview" class="modal-backdrop-custom"><section class="panel modal-panel ai-solution-editor" role="dialog" aria-modal="true"><h2>Question {{preview.number}}</h2><QuestionContent :text="[preview.question.passage,preview.question.text].filter(Boolean).join('\n\n')" :images="preview.question.images.filter(i=>!i.option_key)"/><div v-for="(o,n) in preview.question.options" :key="o.key"><strong>{{String.fromCharCode(65+n)}}:</strong><QuestionContent :text="o.text" :images="preview.question.images.filter(i=>i.option_key===o.key)"/></div><p v-for="c in preview.solution?.checks" class="alert alert-warning">{{c}}</p><textarea aria-label="Edit solution" class="form-control" rows="10" maxlength="14000" v-model="editText"></textarea><MathText class="solution-text" :text="editText" inline-dollar/><button v-if="preview.solution&&preview.solution.status!=='OUTDATED'" class="btn btn-primary" :disabled="busy" @click="action(preview.question_id,'edit',editText)">Save draft</button><button class="btn btn-light" @click="preview=null">Close</button></section></div>
</template>
<style scoped>
.solution-list-filters{display:flex;gap:14px;flex-wrap:wrap;margin-top:20px}.solution-list-filters label{flex:1;min-width:180px}.solution-paper-list{max-height:420px;overflow:auto;margin-top:16px}.solution-paper-row{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:14px 0;border-bottom:1px solid var(--line)}@media(max-width:600px){.solution-paper-row{align-items:flex-start;flex-direction:column}}.solution-filters{border:0;padding:0;margin:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.solution-filters label{min-width:0}.solution-filters select{width:100%}.solution-statistics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}.solution-statistics>div{border:1px solid var(--line);border-radius:10px;padding:16px;background:var(--bs-body-bg,transparent)}.solution-statistics strong{display:block;font-size:1.65rem}.solution-statistics span{font-size:.85rem}.solution-progress{width:calc(100% - 65px);height:12px;accent-color:var(--blue)}.solution-text{display:block;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.75}.solution-text :deep(.katex-display){margin:.65em 0;overflow-x:auto;overflow-y:hidden}@media(max-width:700px){.solution-list-filters{display:flex;gap:14px;flex-wrap:wrap;margin-top:20px}.solution-list-filters label{flex:1;min-width:180px}.solution-paper-list{max-height:420px;overflow:auto;margin-top:16px}.solution-paper-row{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:14px 0;border-bottom:1px solid var(--line)}@media(max-width:600px){.solution-paper-row{align-items:flex-start;flex-direction:column}}.solution-filters{grid-template-columns:1fr}.solution-statistics{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
