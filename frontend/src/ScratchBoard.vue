<script setup>
import {onMounted,onUnmounted,ref} from 'vue';
import {Download,Trash2,X,Undo2,Redo2,Eraser} from 'lucide-vue-next';
const emit=defineEmits(['close']);
const board=ref(null),root=ref(null),tool=ref('pen'),color=ref('#172943');
let drawing=false,last=null,drag=null,history=[],future=[];
const palette=['#172943','#d62828','#1f8f4e','#8e44ad'];

function coords(e){
 const rect=board.value.getBoundingClientRect();
 return {x:(e.clientX-rect.left)*board.value.width/rect.width,y:(e.clientY-rect.top)*board.value.height/rect.height};
}
function snapshot(){return board.value.toDataURL('image/png')}
function pushHistory(){
 history.push(snapshot());if(history.length>40)history.shift();future=[];
}
function restore(data){
 const img=new Image();img.onload=()=>{const ctx=board.value.getContext('2d');ctx.clearRect(0,0,board.value.width,board.value.height);ctx.drawImage(img,0,0,board.value.width,board.value.height)};img.src=data;
}
function down(e){if(e.button!==0&&e.pointerType==='mouse')return;pushHistory();drawing=true;last=coords(e);board.value.setPointerCapture?.(e.pointerId);e.preventDefault()}
function move(e){
 if(!drawing)return;const p=coords(e),ctx=board.value.getContext('2d');ctx.save();ctx.beginPath();ctx.moveTo(last.x,last.y);ctx.lineTo(p.x,p.y);ctx.lineCap='round';
 if(tool.value==='eraser'){ctx.globalCompositeOperation='destination-out';ctx.lineWidth=28}else{ctx.globalCompositeOperation='source-over';ctx.strokeStyle=color.value;ctx.lineWidth=4}
 ctx.stroke();ctx.restore();last=p;e.preventDefault();
}
function up(){drawing=false;last=null}
function clearBoard(record=true){if(record&&board.value)pushHistory();const ctx=board.value.getContext('2d');ctx.save();ctx.setTransform(1,0,0,1,0,0);ctx.fillStyle='#fff';ctx.globalCompositeOperation='source-over';ctx.fillRect(0,0,board.value.width,board.value.height);ctx.restore()}
function undo(){if(!history.length)return;future.push(snapshot());restore(history.pop())}
function redo(){if(!future.length)return;history.push(snapshot());restore(future.pop())}
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
function keyboard(e){
 if(!(e.ctrlKey||e.metaKey)||e.shiftKey)return;
 if(e.key.toLowerCase()==='z'){e.preventDefault();undo()}
 else if(e.key.toLowerCase()==='y'){e.preventDefault();redo()}
}
onMounted(()=>{clearBoard(false);window.addEventListener('keydown',keyboard)});
onUnmounted(()=>window.removeEventListener('keydown',keyboard));
</script>
<template>
<section ref="root" class="floating-tool scratch-tool" aria-label="Scratch board">
 <header class="floating-tool-header" @pointerdown="dragStart">
   <strong>Scratch board</strong><span>Drag · resize · draw</span>
   <div class="floating-tool-actions">
    <button type="button" title="Undo (Ctrl+Z)" @click="undo"><Undo2 :size="16"/></button>
    <button type="button" title="Redo (Ctrl+Y)" @click="redo"><Redo2 :size="16"/></button>
    <button type="button" title="Clear board" @click="clearBoard"><Trash2 :size="16"/></button>
    <button type="button" title="Export annotation" @click="exportBoard"><Download :size="16"/></button>
    <button type="button" title="Close" @click="emit('close')"><X :size="17"/></button>
   </div>
 </header>
 <div class="scratch-toolbar">
  <button type="button" :class="{active:tool==='pen'}" @click="tool='pen'">Marker</button>
  <button v-for="c in palette" :key="c" type="button" class="scratch-color" :class="{active:tool==='pen'&&color===c}" :style="{background:c}" :aria-label="'Marker '+c" @click="tool='pen';color=c"></button>
  <button type="button" :class="{active:tool==='eraser'}" @click="tool='eraser'"><Eraser :size="15"/>Eraser</button>
 </div>
 <div class="scratch-canvas-wrap">
  <canvas ref="board" width="1400" height="900" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @pointerleave="up"></canvas>
 </div>
</section>
</template>