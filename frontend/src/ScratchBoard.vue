<script setup>
import {nextTick,onBeforeUnmount,onMounted,ref} from 'vue';
import {Download,Eraser,PenLine,Trash2} from 'lucide-vue-next';
import FloatingTool from './FloatingTool.vue';

defineEmits(['close']);
const canvas=ref(null),stage=ref(null),mode=ref('pen');let drawing=false,last=null,observer=null;
function context(){
  const ctx=canvas.value?.getContext('2d');
  if(ctx){ctx.lineCap='round';ctx.lineJoin='round';ctx.lineWidth=2.2}
  return ctx;
}
function resize(){
  const c=canvas.value,s=stage.value;if(!c||!s)return;
  const rect=s.getBoundingClientRect();if(rect.width<2||rect.height<2)return;
  const old=document.createElement('canvas');old.width=c.width;old.height=c.height;old.getContext('2d').drawImage(c,0,0);
  const dpr=Math.max(1,window.devicePixelRatio||1);c.width=Math.round(rect.width*dpr);c.height=Math.round(rect.height*dpr);c.style.width=rect.width+'px';c.style.height=rect.height+'px';
  const ctx=c.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);
  if(old.width&&old.height)ctx.drawImage(old,0,0,old.width,old.height,0,0,rect.width,rect.height);
}
function point(e){const r=canvas.value.getBoundingClientRect();return {x:e.clientX-r.left,y:e.clientY-r.top}}
function down(e){if(e.button!==0&&e.pointerType==='mouse')return;drawing=true;last=point(e);canvas.value.setPointerCapture?.(e.pointerId);e.preventDefault()}
function move(e){
  if(!drawing||!last)return;const p=point(e),ctx=context();if(!ctx)return;
  ctx.save();ctx.globalCompositeOperation=mode.value==='eraser'?'destination-out':'source-over';ctx.strokeStyle='#172943';ctx.lineWidth=mode.value==='eraser'?18:2.2;ctx.beginPath();ctx.moveTo(last.x,last.y);ctx.lineTo(p.x,p.y);ctx.stroke();ctx.restore();last=p;e.preventDefault();
}
function up(){drawing=false;last=null}
function clear(){const c=canvas.value;if(!c)return;const ctx=c.getContext('2d');ctx.save();ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,c.width,c.height);ctx.restore()}
function download(){
  const c=canvas.value;if(!c)return;const out=document.createElement('canvas');out.width=c.width;out.height=c.height;const ctx=out.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,out.width,out.height);ctx.drawImage(c,0,0);
  const a=document.createElement('a');a.download='pyq-scratch-board.png';a.href=out.toDataURL('image/png');a.click();
}
onMounted(async()=>{await nextTick();resize();if(typeof ResizeObserver!=='undefined'){observer=new ResizeObserver(resize);observer.observe(stage.value)}window.addEventListener('pointerup',up)});
onBeforeUnmount(()=>{observer?.disconnect();window.removeEventListener('pointerup',up)});
</script>

<template>
<FloatingTool title="Scratch board" :width="560" :height="430" :y="110" @close="$emit('close')">
  <div class="scratch-board">
    <div class="scratch-toolbar">
      <button type="button" :class="{active:mode==='pen'}" @click="mode='pen'"><PenLine :size="16"/>Pen</button>
      <button type="button" :class="{active:mode==='eraser'}" @click="mode='eraser'"><Eraser :size="16"/>Eraser</button>
      <button type="button" @click="clear"><Trash2 :size="16"/>Clear</button>
      <button type="button" @click="download"><Download :size="16"/>Export PNG</button>
    </div>
    <div ref="stage" class="scratch-stage"><canvas ref="canvas" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up"></canvas></div>
  </div>
</FloatingTool>
</template>
