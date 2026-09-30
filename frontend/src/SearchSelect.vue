<script setup>
import {computed,nextTick,onMounted,onUnmounted,ref} from 'vue';
import {ChevronDown,Search} from 'lucide-vue-next';

const props=defineProps({
  modelValue:{default:''},
  options:{type:Array,default:()=>[]},
  placeholder:{type:String,default:'Select'},
  searchPlaceholder:{type:String,default:'Type to search…'},
  labelKey:{type:String,default:'name'},
  valueKey:{type:String,default:'id'},
  emptyLabel:{type:String,default:''}
});
const emit=defineEmits(['update:modelValue','change']);
const open=ref(false),query=ref(''),active=ref(0),root=ref(null),searchInput=ref(null);
const selected=computed(()=>props.options.find(o=>String(o?.[props.valueKey])===String(props.modelValue)));
const label=computed(()=>selected.value?.[props.labelKey]||props.emptyLabel||props.placeholder);
const filtered=computed(()=>{
  const needle=query.value.trim().toLowerCase();
  if(!needle)return props.options;
  return props.options.filter(o=>String(o?.[props.labelKey]||'').toLowerCase().includes(needle));
});
async function toggle(){
  open.value=!open.value;query.value='';active.value=0;
  if(open.value){await nextTick();searchInput.value?.focus()}
}
function choose(option){
  const value=option===null?'':option[props.valueKey];
  open.value=false;query.value='';
  emit('update:modelValue',value);emit('change',value);
}
function keys(e){
  if(e.key==='ArrowDown'){e.preventDefault();active.value=Math.min(active.value+1,filtered.value.length-1)}
  else if(e.key==='ArrowUp'){e.preventDefault();active.value=Math.max(active.value-1,0)}
  else if(e.key==='Enter'&&filtered.value.length){e.preventDefault();choose(filtered.value[active.value])}
  else if(e.key==='Escape'){open.value=false}
}
function outside(e){if(open.value&&!root.value?.contains(e.target))open.value=false}
onMounted(()=>document.addEventListener('pointerdown',outside));
onUnmounted(()=>document.removeEventListener('pointerdown',outside));
</script>

<template>
<div ref="root" class="search-select">
  <button type="button" class="form-select search-select-trigger" :aria-expanded="open" aria-haspopup="listbox" @click="toggle">
    <span>{{label}}</span><ChevronDown :size="17"/>
  </button>
  <div v-if="open" class="search-select-menu" role="listbox">
    <div class="search-select-input"><Search :size="16"/><input ref="searchInput" v-model="query" :placeholder="searchPlaceholder" autocomplete="off" @keydown="keys" aria-label="Search options"></div>
    <button v-if="emptyLabel" type="button" class="search-select-option" :class="{selected:modelValue===''}" @mousedown.prevent="choose(null)">{{emptyLabel}}</button>
    <button v-for="(option,i) in filtered" :key="option[valueKey]" type="button" class="search-select-option" :class="{active:i===active,selected:String(option[valueKey])===String(modelValue)}" @mouseenter="active=i" @mousedown.prevent="choose(option)">{{option[labelKey]}}</button>
    <p v-if="!filtered.length" class="search-select-empty">No matching options</p>
  </div>
</div>
</template>
