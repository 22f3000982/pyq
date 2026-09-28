<script setup>
import {computed,reactive} from 'vue';import MathText from './MathText.vue';
const props=defineProps({text:String,images:{type:Array,default:()=>[]}});
const failed=reactive(new Set());
function retryImage(id){failed.delete(id)}
const parts=computed(()=>{
 const used=new Set(),out=[];let cursor=0;
 for(const match of (props.text||'').matchAll(/\[\[IMAGE:([^\]]+)\]\]/g)){
  out.push({text:props.text.slice(cursor,match.index)});
  const img=props.images.find(i=>i.token===match[1]);if(img){out.push({img});used.add(img.id)}else out.push({missing:true})
  cursor=match.index+match[0].length;
 }
 out.push({text:(props.text||'').slice(cursor)});
 for(const img of props.images)if(!used.has(img.id))out.push({img});
 return out;
});
</script>
<template><div class="source-content"><template v-for="(part,n) in parts" :key="n"><span v-if="part.missing" class="missing-asset" role="status">[Source notation unavailable]</span><span v-else-if="part.img&&failed.has(part.img.id)" class="missing-asset" role="status">Source diagram or notation unavailable. <button type="button" class="text-btn" @click="retryImage(part.img.id)">Retry image</button></span><img v-else-if="part.img" :src="part.img.url||'/api/images/'+part.img.id" :alt="part.img.alt" class="question-image" :class="{'inline-notation':part.img.inline}" :style="part.img.width?{width:part.img.width+'em'}:undefined" @error="failed.add(part.img.id)" decoding="async"><MathText v-else :text="part.text"/></template></div></template>
