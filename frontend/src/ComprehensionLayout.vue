<script setup>
import {computed,ref,watch,nextTick} from 'vue';
import QuestionContent from './QuestionContent.vue';
const props=defineProps({passage:{type:String,default:''},images:{type:Array,default:()=>[]}});
const expanded=ref(true),passageBody=ref(null);
const enabled=computed(()=>Boolean(props.passage?.trim()));
const passageImages=computed(()=>props.images.filter(i=>i.token&&props.passage.includes('[[IMAGE:'+i.token+']]')));
watch(()=>props.passage,async()=>{expanded.value=true;await nextTick();if(passageBody.value)passageBody.value.scrollTop=0});
</script>
<template>
 <div class="comprehension-layout" :class="{'comprehension-split':enabled}">
  <aside v-if="enabled" class="comprehension-passage" aria-label="Common passage">
   <div class="comprehension-heading"><strong>Common passage / data</strong><button type="button" class="text-btn passage-toggle" :aria-expanded="expanded" @click="expanded=!expanded">{{expanded?'Collapse':'Expand'}}</button></div>
   <div ref="passageBody" class="comprehension-passage-body" v-show="expanded"><QuestionContent :text="passage" :images="passageImages"/></div>
  </aside>
  <div class="comprehension-question"><slot/></div>
 </div>
</template>
