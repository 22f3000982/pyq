<script setup>
import {ref,onMounted,onUnmounted} from 'vue';
import {api} from './api';
const props=defineProps({questionId:Number,number:String});const emit=defineEmits(['close','sent']);
const issue=ref('TEXT'),description=ref(''),busy=ref(false),error=ref(''),dialog=ref(null);let previous;
function close(){if(!busy.value)emit('close')}
function keyboard(e){
 if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close()}
 if(e.key==='Tab'){
  const nodes=[...dialog.value.querySelectorAll('button:not(:disabled),select,textarea')];const first=nodes[0],last=nodes.at(-1);
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
 }
}
onMounted(()=>{previous=document.activeElement;dialog.value.querySelector('select').focus()});
onUnmounted(()=>previous?.focus());
async function send(){if(busy.value)return;busy.value=true;error.value='';try{const r=await api('/questions/'+props.questionId+'/report-format',{method:'POST',body:{issue:issue.value,description:description.value}});emit('sent',r.duplicate?'You already reported this question.':'Report sent. Thank you for helping improve this paper.');emit('close')}catch(e){error.value=e.message}finally{busy.value=false}}
</script>
<template><div class="modal-backdrop-custom" @click.self="close"><section ref="dialog" class="confirm-dialog panel report-dialog" role="dialog" aria-modal="true" aria-labelledby="report-title" @keydown="keyboard"><h2 id="report-title">Report broken format</h2><p class="muted">Question {{number}} · Tell us what looks wrong.</p><form @submit.prevent="send"><label>Issue type<select v-model="issue" class="form-select" :disabled="busy"><option value="TEXT">Text / layout</option><option value="FORMULA">Formula / math notation</option><option value="IMAGE">Image / diagram</option><option value="OPTIONS">Answer options</option><option value="OTHER">Other</option></select></label><label>Details (optional)<textarea v-model="description" class="form-control" rows="3" maxlength="1000" placeholder="For example: the formula overlaps the options." :disabled="busy"></textarea></label><p v-if="error" class="alert alert-danger mt-3" role="alert">{{error}}</p><div class="dialog-actions"><button type="button" class="btn btn-light" :disabled="busy" @click="close">Cancel</button><button class="btn btn-primary" :disabled="busy">{{busy?'Sending…':'Send report'}}</button></div></form></section></div></template>
