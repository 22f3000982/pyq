<script setup>
import {computed} from 'vue';
const props=defineProps({coverage:Object});
const total=computed(()=>Number(props.coverage?.total)||0);
const published=computed(()=>Math.min(total.value,Number(props.coverage?.published)||0));
const complete=computed(()=>total.value>0&&published.value===total.value);
</script>
<template><span v-if="published>0" class="solution-badge" :class="{complete}" :title="complete?'All visible questions have published solutions':'Some visible questions have published solutions'">Solutions · {{published}}/{{total}}</span></template>
<style>
.pyq-card,.solution-card{position:relative}.pyq-card.panel:has(.solution-badge),.solution-card:has(.solution-badge){padding-top:36px}.solution-badge{position:absolute;right:10px;top:8px;background:#dcfce7;color:#14532d;border:1px solid #86efac;border-radius:6px;padding:3px 7px;font-size:10px;font-weight:650;line-height:1.3;white-space:nowrap}.solution-badge.complete{background:#15803d;color:#fff;border-color:#15803d}
[data-theme="dark"] .solution-badge{background:#bbf7d0;color:#14532d;border-color:#86efac}[data-theme="dark"] .solution-badge.complete{background:#166534;color:#f0fdf4;border-color:#22c55e}
@media(max-width:480px){.pyq-card.panel:has(.solution-badge){padding-top:32px}.solution-badge{right:8px;top:7px;font-size:9px;padding:3px 5px}}
</style>
