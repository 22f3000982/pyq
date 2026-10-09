<script setup>
import {ref,onMounted} from 'vue';
import {api} from './api';
const period=ref('7d'),data=ref(null),busy=ref(false),error=ref('');
async function load(){
 if(busy.value)return;
 busy.value=true;error.value='';data.value=null;
 try{data.value=await api('/admin/analytics?period='+period.value)}
 catch(e){error.value=e.message}
 finally{busy.value=false}
}
const percent=v=>v==null?'—':v+'%';
const duration=v=>v==null?'—':v<60?v+' sec':Math.round(v/60)+' min';
onMounted(load);
</script>
<template>
 <section class="panel mb-3">
  <div class="section-row"><div><h2>Exam analytics</h2><p class="muted mb-0">Anonymous paper attempts · India time (IST)</p></div>
   <div class="d-flex gap-2"><select v-model="period" class="form-select" aria-label="Analytics period" :disabled="busy" @change="load"><option value="today">Today</option><option value="7d">Last 7 days</option><option value="all">All time</option></select><button class="btn btn-light" :disabled="busy" @click="load">{{busy?'Loading…':'Refresh'}}</button></div>
  </div>
  <p v-if="error" class="alert alert-danger mt-3" role="alert">{{error}}</p>
  <p v-if="!data&&!error" class="muted mt-3" role="status">Loading analytics…</p>
  <template v-if="data">
   <p class="muted small mt-3">{{data.first_day?'Recorded since '+data.first_day+'.':'No recorded attempts yet.'}} Results belong to the date an attempt started. Current attempts can complete later. Counts refresh when you open this tab or press Refresh.</p>
   <div class="admin-stat-grid">
    <div class="panel"><span class="eyebrow">Starts</span><strong>{{data.totals.starts}}</strong></div>
    <div class="panel"><span class="eyebrow">Completions</span><strong>{{data.totals.completions}}</strong></div>
    <div class="panel"><span class="eyebrow">Completion rate</span><strong>{{percent(data.totals.completion_rate)}}</strong></div>
    <div class="panel"><span class="eyebrow">Average elapsed time</span><strong>{{duration(data.totals.average_seconds)}}</strong></div>
   </div>
   <p class="muted small mt-3">{{data.totals.automatic}} completions were triggered by an expired exam timer. Elapsed time includes idle time; it is not a measure of paper difficulty. Unsubmitted attempts may still be active; browser-close reasons are not collected.</p>
   <div class="d-flex gap-3 flex-wrap"><span v-for="d in data.devices" :key="d.device" class="status">{{d.device}} · {{d.starts}} starts</span></div>
  </template>
 </section>
 <template v-if="data">
  <section v-for="section in ['papers','courses']" :key="section" class="panel mb-3">
   <h3>{{section==='papers'?'Papers':'Courses'}}</h3><p class="muted small">Top 50 by starts in the selected period.</p>
   <div class="table-responsive"><table class="table"><thead><tr><th scope="col">{{section==='papers'?'Paper':'Course'}}</th><th scope="col">Starts</th><th scope="col">Completed</th><th scope="col">Rate</th><th scope="col">Average time</th></tr></thead><tbody><tr v-for="row in data[section]" :key="row.key"><td>{{row.name}}</td><td>{{row.starts}}</td><td>{{row.completions}}</td><td>{{percent(row.completion_rate)}}</td><td>{{duration(row.average_seconds)}}</td></tr></tbody></table></div>
   <p v-if="!data[section].length" class="muted">No attempts recorded for this period.</p>
  </section>
  <details class="panel"><summary>Collection details</summary><p class="muted mt-3">Analytics use a bounded background queue. Counts can be incomplete after a restart or database failure. Daily summaries are retained; learner answers, IP addresses and browser identifiers are not collected.</p><p v-if="data.writer" class="small">This web process: {{data.writer.queued}} queued · {{data.writer.dropped}} queue-overflow drops · {{data.writer.failed}} failed-write events. These counters reset when this process restarts.</p></details>
 </template>
</template>
