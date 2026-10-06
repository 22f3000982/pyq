import renderMathInElement from 'katex/contrib/auto-render';
import 'katex/dist/katex.min.css';
import {textSegments} from './textFormatting';
for(const el of document.querySelectorAll('.math-copy')){
 const text=el.textContent;el.replaceChildren();
 for(const part of textSegments(text,true)){const node=part.bold?document.createElement('strong'):document.createTextNode(part.text);if(part.bold)node.textContent=part.text;el.appendChild(node);}
 renderMathInElement(el,{delimiters:[{left:'$$',right:'$$',display:true},{left:'\\[',right:'\\]',display:true},{left:'\\(',right:'\\)',display:false},{left:'$',right:'$',display:false}],throwOnError:false,trust:false});
}
