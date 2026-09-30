<script setup>
import {ExternalLink} from 'lucide-vue-next';
import FloatingTool from './FloatingTool.vue';
defineEmits(['close']);
const url='https://tcsion.com/OnlineAssessment/ScientificCalculator/Calculator.html';
</script>

<template>
<FloatingTool title="TCS iON scientific calculator" :width="620" :height="570" :y="92" :x="28" @close="$emit('close')">
  <div class="calculator-shell">
    <div class="calculator-note"><span>Official TCS iON calculator demo</span><a :href="url" target="_blank" rel="noopener noreferrer">Open separately <ExternalLink :size="14"/></a></div>
    <iframe class="tcs-calculator-frame" :src="url" title="TCS iON scientific calculator" referrerpolicy="no-referrer"></iframe>
    <p class="calculator-fallback">If the provider blocks embedded display in your browser, use <a :href="url" target="_blank" rel="noopener noreferrer">Open separately</a>.</p>
  </div>
</FloatingTool>
</template>
