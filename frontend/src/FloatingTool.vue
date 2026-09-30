<script setup>
import {onBeforeUnmount,onMounted,ref} from 'vue';
import {X,GripHorizontal} from 'lucide-vue-next';

let topZ=1300;
const props=defineProps({title:String,width:{type:Number,default:520},height:{type:Number,default:420},x:{type:Number,default:null},y:{type:Number,default:100}});
const emit=defineEmits(['close']);
const left=ref(40),top=ref(props.y),z=ref(++topZ),drag=null;
function clamp(){
  left.value=Math.max(6,Math.min(left.value,Math.max(6,window.innerWidth-220)));
  top.value=Math.max(6,Math.min(top.value,Math.max(6,window.innerHeight-70)));
}
function raise(){z.value=++topZ}
function startDrag(e){
  if(e.button!==0)return;raise();
  drag={id:e.pointerId,x:e.clientX,y:e.clientY,left:left.value,top:top.value};
  e.currentTarget.setPointerCapture?.(e.pointerId);
  window.addEventListener('pointermove',move);window.addEventListener('pointerup',stop,{once:true});
}
function move(e){
  if(!drag||e.pointerId!==drag.id)return;
  left.value=drag.left+e.clientX-drag.x;top.value=drag.top+e.clientY-drag.y;clamp();
}
function stop(){drag=null;window.removeEventListener('pointermove',move)}
function viewport(){clamp()}
onMounted(()=>{
  const preferred=props.x??Math.max(12,window.innerWidth-props.width-40);
  left.value=Math.max(8,Math.min(preferred,Math.max(8,window.innerWidth-Math.min(props.width,window.innerWidth-16)-8)));
  clamp();window.addEventListener('resize',viewport)
});
onBeforeUnmount(()=>{window.removeEventListener('pointermove',move);window.removeEventListener('resize',viewport)});
</script>

<template>
<section class="floating-tool" :style="{left:left+'px',top:top+'px',width:width+'px',height:height+'px',zIndex:z}" @pointerdown="raise" role="dialog" :aria-label="title">
  <header class="floating-tool-header" @pointerdown="startDrag"><GripHorizontal :size="18"/><strong>{{title}}</strong><button type="button" class="floating-tool-close" aria-label="Close" @pointerdown.stop @click="$emit('close')"><X :size="18"/></button></header>
  <div class="floating-tool-body"><slot/></div>
</section>
</template>
