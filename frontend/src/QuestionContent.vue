<script setup>
import {computed} from 'vue';import MathText from './MathText.vue';
const props=defineProps({text:String,images:{type:Array,default:()=>[]}});
const parts=computed(()=>{
 const used=new Set(),out=[];let cursor=0;
 for(const match of (props.text||'').matchAll(/\[\[IMAGE:([^\]]+)\]\]/g)){
  out.push({text:props.text.slice(cursor,match.index)});
  const img=props.images.find(i=>i.token===match[1]);if(img){out.push({img});used.add(img.id)}
  cursor=match.index+match[0].length;
 }
 out.push({text:(props.text||'').slice(cursor)});
 for(const img of props.images)if(!used.has(img.id))out.push({img});
 return out;
});
</script>
<template><div class="source-content"><template v-for="(part,n) in parts" :key="n"><img v-if="part.img" :src="'/api/images/'+part.img.id" :alt="part.img.alt" class="question-image" :class="{'inline-notation':part.img.inline}" :style="part.img.width?{width:part.img.width+'em'}:undefined"><MathText v-else :text="part.text"/></template></div></template>
