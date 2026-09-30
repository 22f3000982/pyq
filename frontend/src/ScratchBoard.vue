<script setup>
import {onMounted,ref} from 'vue';
import {Download,Trash2,X} from 'lucide-vue-next';
const emit=defineEmits(['close']);
const board=ref(null),root=ref(null);
let drawing=false,last=null,drag=null;
function coords(e){
 const rect=board.value.getBoundingClientRect();
 return {x:(e.clientX-rect.left)*board.value.width/rect.width,y:(e.clientY-rect.top)*board.value.height/rect.height};
}
function down(e){drawing=true;last=coords(e);board.value.setPointerCapture?.(e.pointerId)}
function move(e){if(!drawing)return;const p=coords(e),ctx=board.value.getContext('2d');ctx.beginPath();ctx.moveTo(last.x,last.y);ctx.lineTo(p.x,p.y);ctx.strokeStyle='#182335';ctx.lineWidth=3;ctx.lineCap='round';ctx.stroke();last=p}
function up(){drawing=false;last=null}
function clearBoard(){const ctx=board.value.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,board.value.width,board.value.height)}
function exportBoard(){const a=document.createElement('a');a.href=board.value.toDataURL('image/png');a.download='pyq-scratch-board.png';a.click()}
function dragStart(e){
 if(e.target.closest('button'))return;
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
onMounted(()=>clearBoard());
</script>
<template>
<section ref="root" class="floating-tool scratch-tool" aria-label="Scratch board">
 <header class="floating-tool-header" @pointerdown="dragStart">
   <strong>Scratch board</strong><span>Drag · resize · draw</span>
   <div class="floating-tool-actions">
    <button type="button" title="Clear board" @click="clearBoard"><Trash2 :size="16"/></button>
    <button type="button" title="Export annotation" @click="exportBoard"><Download :size="16"/></button>
    <button type="button" title="Close" @click="emit('close')"><X :size="17"/></button>
   </div>
 </header>
 <div class="scratch-canvas-wrap">
  <canvas ref="board" width="1400" height="900" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @pointerleave="up"></canvas>
 </div>
</section>
</template>
