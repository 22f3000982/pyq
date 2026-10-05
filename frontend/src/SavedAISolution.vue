<script setup>
import {ref,watch} from 'vue';import {api} from './api';import MathText from './MathText.vue';
const props=defineProps({attemptId:Number,questionId:Number,saved:Object});const data=ref(null),error=ref(''),loading=ref(false);let generation=0;
const cache=new Map();
async function load(){const key=props.attemptId+':'+props.questionId,n=++generation;error.value='';data.value=null;if(props.saved!==undefined){data.value=props.saved;loading.value=false;return}if(cache.has(key)){data.value=cache.get(key);return}loading.value=true;try{const d=await api(`/attempts/${props.attemptId}/questions/${props.questionId}/ai-solution`);if(n===generation){data.value=d;cache.set(key,d)}}catch(e){if(n===generation)error.value='Explanation could not load.'}finally{if(n===generation)loading.value=false}}
watch(()=>[props.attemptId,props.questionId,props.saved],load,{immediate:true});
</script>
<template><section v-if="data?.available" class="ai-solution"><span class="eyebrow">Solution</span><MathText class="solution-text" :text="data.text" inline-dollar/></section><p v-else-if="loading" class="small muted" role="status">Loading explanation…</p><p v-else-if="error" class="small muted">{{error}} <button class="text-btn" @click="load">Retry</button></p></template>

<style scoped>
.solution-text{display:block;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.75}
.solution-text :deep(.katex-display){margin:.65em 0;overflow-x:auto;overflow-y:hidden}
</style>
