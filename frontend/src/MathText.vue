<script setup>
import {ref,watch,nextTick,onMounted} from 'vue';
import {textSegments} from './textFormatting';
import renderMathInElement from 'katex/contrib/auto-render';
const props=defineProps({text:[String,Number]});const el=ref();
async function render(){await nextTick();if(el.value){el.value.replaceChildren();for(const part of textSegments(props.text)){const node=part.bold?document.createElement('strong'):document.createTextNode(part.text);if(part.bold)node.textContent=part.text;el.value.appendChild(node)}renderMathInElement(el.value,{delimiters:[{left:'$$',right:'$$',display:true},{left:'\\[',right:'\\]',display:true},{left:'\\(',right:'\\)',display:false}],throwOnError:false,trust:false});}}
onMounted(render);watch(()=>props.text,render);
</script><template><span ref="el" class="math-text"></span></template>
