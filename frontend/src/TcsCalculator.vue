<script setup>
import {ref} from 'vue';
import {ExternalLink,X} from 'lucide-vue-next';
const emit=defineEmits(['close']);
const root=ref(null);let drag=null;
const url='https://tcsion.com/OnlineAssessment/ScientificCalculator/Calculator.html';
function dragStart(e){
 if(e.target.closest('button,a'))return;
 const r=root.value.getBoundingClientRect();drag={dx:e.clientX-r.left,dy:e.clientY-r.top};
 window.addEventListener('pointermove',dragMove);window.addEventListener('pointerup',dragEnd,{once:true});
}
function dragMove(e){
 if(!drag)return;
 const w=root.value.offsetWidth,h=root.value.offsetHeight;
 root.value.style.left=Math.max(0,Math.min(window.innerWidth-w,e.clientX-drag.dx))+'px';
 root.value.style.top=Math.max(0,Math.min(window.innerHeight-h,e.clientY-drag.dy))+'px';
}
function dragEnd(){drag=null;window.removeEventListener('pointermove',dragMove)}
</script>
<template>
<section ref="root" class="floating-tool calculator-tool" aria-label="TCS iON scientific calculator">
 <header class="floating-tool-header" @pointerdown="dragStart">
   <strong>TCS iON calculator</strong><span>Drag · resize</span>
   <div class="floating-tool-actions">
    <a :href="url" target="_blank" rel="noopener noreferrer" title="Open calculator in new tab"><ExternalLink :size="16"/></a>
    <button type="button" title="Close" @click="emit('close')"><X :size="17"/></button>
   </div>
 </header>
 <iframe :src="url" title="TCS iON Scientific Calculator" loading="eager" referrerpolicy="no-referrer"></iframe>
 <p class="calculator-fallback">If TCS blocks embedded viewing in your browser, use the ↗ button to open the official calculator.</p>
</section>
</template>
