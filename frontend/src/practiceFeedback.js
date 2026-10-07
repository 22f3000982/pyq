// Practice preview only. Final scoring always remains authoritative on the server.
function number(raw){
 const text=String(raw).trim().replaceAll('−','-');
 if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?:\s*\/\s*[+-]?\d+(?:\.\d+)?)?$/.test(text))throw Error('Invalid number');
 if(text.includes('/')){const [a,b]=text.split('/').map(number);if(b.n===0n)throw Error('Zero denominator');const result=normal(a.n*b.d,a.d*b.n);let denominator=result.d, numerator=result.n;while(numerator){const next=denominator%numerator;denominator=numerator;numerator=next}let remainder=result.d/(denominator<0n?-denominator:denominator);while(remainder%2n===0n)remainder/=2n;while(remainder%5n===0n)remainder/=5n;if(remainder!==1n)throw Error('Repeating fraction requires server grading');return result}
 const [mantissa,exp='0']=text.toLowerCase().split('e'),exponent=Number(exp);if(Math.abs(exponent)>1000)throw Error('Large exponent');
 const decimals=(mantissa.split('.')[1]||'').length,shift=exponent-decimals,n=BigInt(mantissa.replace('.',''));
 return normal(n*(shift>0?10n**BigInt(shift):1n),shift<0?10n**BigInt(-shift):1n);
}
function normal(n,d){return d<0n?{n:-n,d:-d}:{n,d}}
function compare(a,b){const v=a.n*b.d-b.n*a.d;return v<0n?-1:v>0n?1:0}
function numericCorrect(answer,key,tolerance){
 const a=number(answer),tol=number(tolerance||0);
 if(key&&typeof key==='object'){
  if(key.kind==='alternatives')return key.keys.some(k=>numericCorrect(answer,k,tolerance));
  if(key.kind==='range')return compare(number(key.lower),a)<=0&&compare(a,number(key.upper))<=0;
  if(key.kind==='values')return key.values.some(k=>numericCorrect(answer,k,tolerance));
  throw Error('Unknown key');
 }
 const b=number(key),diff=a.n*b.d-b.n*a.d;
 return compare({n:diff<0n?-diff:diff,d:a.d*b.d},tol)<=0;
}
export function practiceFeedback(key,answer){
 if(!key)return null;
 const result=(outcome,awarded)=>({...key,outcome,awarded});
 if(answer==null||answer===''||Array.isArray(answer)&&!answer.length)return result('SKIPPED',0);
 if(!['MCQ','MSQ','TRUE_FALSE','NAT','SHORT_TEXT'].includes(key.kind)||key.answer_status!=='ANSWER_AVAILABLE'||key.marks==null||key.negative_marks==null)return result('UNGRADED',null);
 try{
  if(key.kind==='MSQ'&&key.msq_scoring==='proportional-v1'){
   const selected=new Set(answer),correct=new Set(key.answers||[]);
   if(!correct.size)return result('UNGRADED',null);
   if([...selected].some(k=>!correct.has(k)))return result('INCORRECT',0);
   return result(selected.size===correct.size?'CORRECT':'PARTIAL',key.marks*selected.size/correct.size);
  }
  let correct;
  if(key.kind==='NAT')correct=numericCorrect(answer,key.answers,key.tolerance);
  else if(key.kind==='SHORT_TEXT'){if(key.answers.case_sensitive===false&&[answer,...key.answers.values].some(v=>/[^\x00-\x7f]/.test(String(v))))return null;const norm=v=>key.answers.case_sensitive===false?String(v).trim().toLowerCase():String(v).trim();correct=key.answers.values.some(v=>norm(v)===norm(answer))}
  else{const a=new Set(answer),b=new Set(key.answers);correct=a.size===b.size&&[...a].every(v=>b.has(v))}
  return result(correct?'CORRECT':'INCORRECT',correct?key.marks:-key.negative_marks);
 }catch{return null} // Unsupported/invalid input falls back to server validation.
}
