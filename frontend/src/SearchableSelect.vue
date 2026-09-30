<script setup>
import {computed,nextTick,onBeforeUnmount,onMounted,ref} from 'vue';
import {ChevronDown,Search,X} from 'lucide-vue-next';

const props=defineProps({
  modelValue:{default:''},
  options:{type:Array,default:()=>[]},
  placeholder:{type:String,default:'Select'},
  searchPlaceholder:{type:String,default:'Type to search…'},
  labelKey:{type:String,default:'label'},
  valueKey:{type:String,default:'value'}
});
const emit=defineEmits(['update:modelValue','change']);
const open=ref(false),query=ref(''),root=ref(null),searchInput=ref(null);
const selected=computed(()=>props.options.find(o=>String(o[props.valueKey])===String(props.modelValue)));
const filtered=computed(()=>{
  const q=query.value.trim().toLowerCase();
  if(!q)return props.options;
  return props.options.filter(o=>String(o[props.labelKey]??'').toLowerCase().includes(q));
});
async function toggle(){open.value=!open.value;if(open.value){query.value='';await nextTick();searchInput.value?.focus()}}
function choose(option){emit('update:modelValue',option[props.valueKey]);emit('change',option[props.valueKey]);open.value=false;query.value=''}
function clear(e){e.stopPropagation();emit('update:modelValue','');emit('change','');query.value=''}
function outside(e){if(open.value&&!root.value?.contains(e.target))open.value=false}
function keydown(e){
 if(e.key==='Escape')open.value=false;
 if(e.key==='Enter'&&open.value&&filtered.value.length){e.preventDefault();choose(filtered.value[0])}
}
onMounted(()=>{document.addEventListener('pointerdown',outside);document.addEventListener('keydown',keydown)});
onBeforeUnmount(()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',keydown)});
</script>

<template>
<div ref="root" class="searchable-select" :class="{open}">
  <button type="button" class="searchable-select-trigger" @click="toggle" :aria-expanded="open">
    <span :class="{placeholder:!selected}">{{selected?.[labelKey]||placeholder}}</span>
    <span class="searchable-select-icons">
      <X v-if="selected" :size="15" class="searchable-select-clear" @click="clear"/>
      <ChevronDown :size="18"/>
    </span>
  </button>
  <div v-if="open" class="searchable-select-menu">
    <div class="searchable-select-search">
      <Search :size="16"/>
      <input ref="searchInput" v-model="query" :placeholder="searchPlaceholder" autocomplete="off" aria-label="Search options">
    </div>
    <div class="searchable-select-options" role="listbox">
      <button type="button" class="searchable-select-option" :class="{selected:String(modelValue)===String(option[valueKey])}" v-for="option in filtered" :key="option[valueKey]" @click="choose(option)">
        {{option[labelKey]}}
      </button>
      <p v-if="!filtered.length" class="searchable-select-empty">No matching result</p>
    </div>
  </div>
</div>
</template>
