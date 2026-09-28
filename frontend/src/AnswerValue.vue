<script setup>
import {computed} from 'vue';import MathText from './MathText.vue';import QuestionContent from './QuestionContent.vue';import {answerText} from './utils';
const props=defineProps({question:Object,value:null,empty:{type:String,default:'Not available'}});
const choices=computed(()=>['MCQ','MSQ','TRUE_FALSE'].includes(props.question?.kind)&&Array.isArray(props.value)?props.value.map(key=>{const n=props.question.options.findIndex(o=>o.key===key);return n<0?null:{...props.question.options[n],letter:String.fromCharCode(65+n),images:(props.question.images||[]).filter(i=>i.option_key===key)}}):null);
</script>
<template><div class="answer-value"><span v-if="value===null||value===undefined||value===''||Array.isArray(value)&&!value.length">{{empty}}</span><template v-else-if="choices"><div v-for="(o,n) in choices" :key="n" class="answer-choice"><template v-if="o"><strong>Option {{o.letter}}</strong><QuestionContent :text="o.text" :images="o.images"/></template><span v-else>Option no longer available in this attempt</span></div></template><MathText v-else :text="answerText(value)"/></div></template>
