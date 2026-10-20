<script setup>
import {ref,watch,nextTick,onMounted} from 'vue';
import MarkdownIt from 'markdown-it';
import renderMathInElement from 'katex/contrib/auto-render';
const props=defineProps({text:String});const el=ref();
const md=new MarkdownIt({html:false,breaks:true,linkify:false});
md.renderer.rules.image=(tokens,index)=>{const token=tokens[index],src=token.attrGet('src')||'';return /^\/api\/admin\/oppe\/assets\/[a-f0-9]{64}\.(png|jpg)$/.test(src)?`<img src="${src}" alt="Original question diagram" loading="lazy">`:'<span>[Unsupported image]</span>'};
md.renderer.rules.link_open=(tokens,index,options,env,self)=>{tokens[index].attrSet('rel','noopener noreferrer');return self.renderToken(tokens,index,options)};
async function render(){await nextTick();if(!el.value)return;el.value.innerHTML=md.render(props.text||'');renderMathInElement(el.value,{delimiters:[{left:'$$',right:'$$',display:true},{left:'\\[',right:'\\]',display:true},{left:'\\(',right:'\\)',display:false},{left:'$',right:'$',display:false}],throwOnError:false,trust:false});}
onMounted(render);watch(()=>props.text,render);
</script>
<template><div ref="el" class="oppe-rich-text"/></template>
<style>.oppe-rich-text img{max-width:100%;height:auto;background:white;border-radius:6px}.oppe-rich-text table{border-collapse:collapse;display:block;overflow:auto;margin:12px 0}.oppe-rich-text td,.oppe-rich-text th{border:1px solid #94a3b855;padding:7px 10px}.oppe-rich-text p{white-space:normal}.oppe-rich-text pre{white-space:pre!important}</style>
