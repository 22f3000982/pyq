<script setup>
import {ref,onMounted,onBeforeUnmount,watch} from 'vue';
import {EditorState} from '@codemirror/state';
import {EditorView,lineNumbers,highlightActiveLine,drawSelection,keymap} from '@codemirror/view';
import {defaultKeymap,history,historyKeymap,indentWithTab} from '@codemirror/commands';
import {syntaxHighlighting,defaultHighlightStyle,bracketMatching} from '@codemirror/language';
import {python} from '@codemirror/lang-python';import {java} from '@codemirror/lang-java';import {sql,PostgreSQL} from '@codemirror/lang-sql';
const props=defineProps({modelValue:String,language:String});const emit=defineEmits(['update:modelValue']);const root=ref();let view;
onMounted(()=>{view=new EditorView({parent:root.value,state:EditorState.create({doc:props.modelValue||'',extensions:[lineNumbers(),highlightActiveLine(),drawSelection(),history(),bracketMatching(),syntaxHighlighting(defaultHighlightStyle),keymap.of([...defaultKeymap,...historyKeymap,indentWithTab]),props.language==='python'?python():props.language==='java'?java():props.language==='postgresql'?sql({dialect:PostgreSQL}):[],EditorView.contentAttributes.of({'aria-label':'OPPE code editor',spellcheck:'false'}),EditorView.updateListener.of(u=>{if(u.docChanged)emit('update:modelValue',u.state.doc.toString())}),EditorView.theme({'&':{height:'100%',background:'var(--oppe-code-bg, #f8fafc)',color:'var(--oppe-code-fg, #172033)'},'.cm-scroller':{overflow:'auto',fontFamily:'ui-monospace, monospace',fontSize:'14px'},'.cm-content':{minHeight:'350px'},'.cm-gutters':{background:'transparent',color:'#64748b'},'.cm-activeLine':{background:'#64748b12'}})]})})});
watch(()=>props.modelValue,text=>{if(view&&text!==view.state.doc.toString())view.dispatch({changes:{from:0,to:view.state.doc.length,insert:text||''}})});
onBeforeUnmount(()=>view?.destroy());
</script>
<template><div ref="root" class="oppe-code"/></template>
