<script setup>
import {computed,ref,watch,nextTick} from 'vue';
import QuestionContent from './QuestionContent.vue';
const props=defineProps({passage:{type:String,default:''},images:{type:Array,default:()=>[]}});
const expanded=ref(true),passageBody=ref(null),layout=ref(null),width=ref(60),dragging=ref(false);
function resize(value){width.value=Math.max(30,Math.min(70,value))}
function drag(event){if(!dragging.value)return;const box=layout.value?.getBoundingClientRect();if(box?.width)resize((event.clientX-box.left)/box.width*100)}
function startDrag(event){if(event.button!==0)return;dragging.value=true;event.currentTarget.setPointerCapture?.(event.pointerId);drag(event)}
function stopDrag(){dragging.value=false}
function resizeKey(event){if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();event.stopPropagation();resize(width.value+(event.key==='ArrowLeft'?-2:2))}else if(event.key==='Home'){event.preventDefault();resize(60)}}
const enabled=computed(()=>Boolean(props.passage?.trim()));
const passageImages=computed(()=>props.images.filter(i=>i.token&&props.passage.includes('[[IMAGE:'+i.token+']]')));
watch(()=>props.passage,async()=>{expanded.value=true;await nextTick();if(passageBody.value)passageBody.value.scrollTop=0});
</script>
<template>
 <div ref="layout" class="comprehension-layout" :class="{'comprehension-split':enabled,'passage-resizing':dragging}" :style="{'--passage-width':width+'%'}">
  <aside v-if="enabled" class="comprehension-passage" aria-label="Common passage">
   <div class="comprehension-heading"><strong>Common passage / data</strong><button type="button" class="text-btn passage-toggle" :aria-expanded="expanded" @click="expanded=!expanded">{{expanded?'Collapse':'Expand'}}</button></div>
   <div ref="passageBody" class="comprehension-passage-body" v-show="expanded"><QuestionContent :text="passage" :images="passageImages"/></div>
  </aside>
  <div v-if="enabled" class="passage-divider" role="separator" tabindex="0" aria-label="Resize passage width" aria-orientation="vertical" :aria-valuenow="Math.round(width)" :aria-valuemin="30" :aria-valuemax="70" @pointerdown.prevent="startDrag" @pointermove="drag" @pointerup="stopDrag" @pointercancel="stopDrag" @lostpointercapture="stopDrag" @keydown="resizeKey" @dblclick="width=60"><span></span></div>
  <div class="comprehension-question"><slot/></div>
 </div>
</template>
