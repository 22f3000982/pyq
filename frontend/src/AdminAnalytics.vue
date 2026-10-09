<script setup>
import {ref,onMounted,computed} from 'vue';
import {api} from './api';
const period=ref('7d'),start=ref(''),end=ref(''),data=ref(null),busy=ref(false),error=ref('');
const params=()=>new URLSearchParams({period:period.value,...(period.value==='custom'?{start:start.value,end:end.value}:{})}).toString();
async function load(){
 if(busy.value)return;busy.value=true;error.value='';
 try{data.value=await api('/admin/analytics?'+params())}catch(e){error.value=e.message}finally{busy.value=false}
}
const percent=v=>v==null?'—':v+'%';
const duration=v=>v==null?'—':v<60?v+' sec':(v/60).toFixed(1)+' min';
const peak=computed(()=>Math.max(1,...(data.value?.trend||[]).map(r=>r.starts)));
const cards=computed(()=>data.value?[
 ['Active browsers',data.value.totals.active_browsers],['Exam starts',data.value.totals.exam_starts],
 ['Practice starts',data.value.totals.practice_starts],['Exam completions',data.value.totals.exam_completions],
 ['All submissions',data.value.totals.completions],['Completion rate',percent(data.value.totals.completion_rate)],
 ['Average completion duration',duration(data.value.totals.average_seconds)],['Expired without submission',data.value.totals.abandoned]
 ]:[]);
onMounted(load);
</script>
<template>
 <section class="panel mb-3">
  <h2>Usage analytics</h2><p class="muted">Permanent exam/practice records · IST · Admin only</p>
  <form class="d-flex gap-2 flex-wrap" @submit.prevent="load">
   <select v-model="period" class="form-select w-auto" aria-label="Analytics period" :disabled="busy" @change="period!=='custom'&&load()"><option value="today">Today</option><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="all">All time</option><option value="custom">Custom range</option></select>
   <template v-if="period==='custom'"><label>From <input type="date" v-model="start" required class="form-control"></label><label>To <input type="date" v-model="end" required class="form-control"></label></template>
   <button class="btn btn-light" :disabled="busy">{{busy?'Loading…':'Refresh'}}</button>
   <a v-if="data&&!busy" :href="'/api/admin/analytics?'+params()+'&format=csv'" class="btn btn-outline-primary">Download CSV</a>
  </form>
  <p v-if="error" class="alert alert-danger mt-3" role="alert">{{error}}</p>
  <p v-if="!data&&!error" role="status">Loading analytics…</p>
  <template v-if="data">
   <p class="muted small mt-3">{{data.first_day?'Recorded since '+data.first_day+'.':'No recorded attempts yet.'}} Starts and completions are grouped by the IST start date. Reports may be cached for 30 seconds.</p>
   <div class="admin-stat-grid"><div class="panel" v-for="[label,value] in cards" :key="label"><span class="eyebrow">{{label}}</span><strong>{{value}}</strong></div></div>
   <p class="small muted mt-3">Active browsers are estimated devices/browsers using exams or practice, not exact students or homepage visitors. Clearing cookies can increase this number. Admin attempts and pre-installation history are excluded.</p>
   <p class="small muted">{{data.totals.switched_completions}} exam-started sessions used a mode switch and are excluded from Exam completions. {{data.totals.automatic}} submissions were timer-triggered. Duration includes idle time. Expired unsubmitted sessions count as drop-off ({{percent(data.totals.dropoff_rate)}}); browser-close or error reasons are unknown.</p>
   <div class="d-flex gap-3 flex-wrap"><span v-for="d in data.devices" :key="d.name" class="status">{{d.name}} · {{d.starts}} starts</span></div>
  </template>
 </section>
 <template v-if="data">
  <section class="panel mb-3"><h3>Daily starts</h3><p class="small muted">Latest 90 recorded days in the selected range.</p><div v-for="r in data.trend" :key="r.day" class="d-flex gap-2 align-items-center mb-2"><span style="min-width:90px">{{r.day}}</span><div class="progress flex-grow-1" role="img" :aria-label="r.day+': '+r.starts+' starts'"><div class="progress-bar" :style="{width:(100*r.starts/peak)+'%'}"></div></div><span>{{r.starts}}</span></div><p v-if="!data.trend.length" class="muted">No activity yet.</p></section>
  <section v-for="section in ['papers','courses']" :key="section" class="panel mb-3">
   <h3>{{section==='papers'?'Popular papers':'Popular courses'}}</h3><p class="small muted">Top 50 by starts; overall totals include all records.</p>
   <div class="table-responsive"><table class="table"><thead><tr><th>Name</th><th>Starts</th><th>Submissions</th><th>Active browsers</th><th>Average duration</th></tr></thead><tbody><tr v-for="row in data[section]" :key="row.key"><td>{{row.name}}</td><td>{{row.starts}}</td><td>{{row.completions}}</td><td>{{row.active_browsers}}</td><td>{{duration(row.average_seconds)}}</td></tr></tbody></table></div>
  </section>
  <details class="panel"><summary>Metric definitions and reliability</summary><p class="mt-3">One successful new paper attempt counts as one start. Changing mode does not add a start. One submission per attempt is recorded. Minimal usage records survive temporary answer cleanup and catalog deletion. No GA4, answer tracking, IP storage, fingerprinting or per-question tracking is used.</p><p>Writes share existing request transactions in an isolated savepoint. Analytics failures are logged and do not intentionally fail the main action; failed writes may leave incomplete counts. Successful commits survive process restarts. Changing SECRET_KEY or clearing browser cookies can change browser counts. Heavy reporting runs only when this admin tab is opened; the shared database still has finite resources.</p></details>
 </template>
</template>
