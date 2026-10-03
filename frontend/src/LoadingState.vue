<script setup>
import {ref,onMounted,onUnmounted} from 'vue';
defineProps({title:{type:String,default:'Preparing your exam…'},description:{type:String,default:'Loading questions and setting up your session.'}});
const percentage=ref(0);let timer;
onMounted(()=>{const started=Date.now();timer=setInterval(()=>{percentage.value=Math.min(95,Math.round(95*(1-Math.exp(-(Date.now()-started)/7000))))},200)});
onUnmounted(()=>clearInterval(timer));
</script>
<template><section class="loading-state panel" role="status" aria-live="polite" aria-busy="true"><span class="loading-spinner" aria-hidden="true"></span><h2>{{title}}</h2><p class="muted">{{description}}</p><div class="loading-percentage" aria-live="off"><strong>{{percentage}}%</strong><span class="muted">Estimated progress</span></div><progress :value="percentage" :aria-label="title+' — estimated progress'" max="100"></progress><p v-if="percentage>=95" class="muted">Still waiting for the server. Your session will open when ready.</p><div class="loading-skeleton" aria-hidden="true"><span></span><span></span><span></span></div></section></template>
<style scoped>.loading-percentage{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:18px 0 8px}.loading-percentage strong{font-size:1.25rem}progress{width:100%;height:12px;accent-color:#2f63df}</style>
