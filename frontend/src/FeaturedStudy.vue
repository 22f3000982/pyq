<script setup>
import {onMounted,ref} from 'vue';
const papers=ref([]);
onMounted(async()=>{try{const r=await fetch('/api/study-featured');if(r.ok)papers.value=(await r.json()).items}catch{}});
</script>
<template><section class="panel" v-if="papers.length"><h2>Read published solutions</h2><p class="muted">Selected study papers. No test or login needed.</p><ul><li v-for="p in papers" :key="p.id"><a :href="'/study/papers/'+p.id">{{p.title}}</a> · {{p.published}}/{{p.total}} solutions</li></ul><a href="/study/featured">All featured study papers →</a></section><p v-else class="mt-3"><a href="/study">Browse public questions and published solutions →</a></p></template>
