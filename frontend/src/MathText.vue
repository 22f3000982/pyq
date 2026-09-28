<script setup>
import {ref,watch,nextTick,onMounted} from 'vue';
import renderMathInElement from 'katex/contrib/auto-render';
const props=defineProps({text:[String,Number]});const el=ref();
async function render(){await nextTick();if(el.value){el.value.textContent=String(props.text??'');renderMathInElement(el.value,{delimiters:[{left:'$$',right:'$$',display:true},{left:'\\[',right:'\\]',display:true},{left:'\\(',right:'\\)',display:false}],throwOnError:false,trust:false});}}
onMounted(render);watch(()=>props.text,render);
</script><template><span ref="el" class="math-text"></span></template>
