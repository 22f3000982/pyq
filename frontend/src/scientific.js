// Small expression parser: never evaluates JavaScript or arbitrary code.
export function calculate(expression,degrees=true){
 if(typeof expression!=='string'||expression.length>500)throw Error('Expression is too long');
 const tokens=[];let position=0;
 while(position<expression.length){
  if(/\s/.test(expression[position])){position++;continue}
  const match=expression.slice(position).match(/^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?|^[a-z]+|^[+\-*/^!(),]/i);
  if(!match)throw Error('Invalid expression');tokens.push(match[0]);position+=match[0].length;
 }
 let i=0;const factor=degrees?Math.PI/180:1;
 const factorial=n=>{if(!Number.isInteger(n)||n<0||n>170)throw Error('Factorial requires an integer from 0 to 170');let v=1;for(let k=2;k<=n;k++)v*=k;return v};
 const functions={sin:x=>Math.sin(x*factor),cos:x=>Math.cos(x*factor),tan:x=>{if(Math.abs(Math.cos(x*factor))<1e-14)throw Error('Undefined tangent');return Math.tan(x*factor)},asin:x=>Math.asin(x)/factor,acos:x=>Math.acos(x)/factor,atan:x=>Math.atan(x)/factor,sinh:Math.sinh,cosh:Math.cosh,tanh:Math.tanh,asinh:Math.asinh,acosh:Math.acosh,atanh:Math.atanh,sqrt:Math.sqrt,cbrt:Math.cbrt,abs:Math.abs,ln:Math.log,log:Math.log10,exp:Math.exp,logbase:(base,x)=>{if(base<=0||base===1||x<=0)throw Error('Invalid log base');return Math.log(x)/Math.log(base)},root:(degree,x)=>{if(degree===0)throw Error('Root degree cannot be zero');return x<0&&Number.isInteger(degree)&&degree%2? -Math.pow(-x,1/degree):Math.pow(x,1/degree)}};
 function atom(){
  const token=tokens[i++];let value;
  if(token==='('){value=sum();if(tokens[i++]!==')')throw Error('Missing closing parenthesis')}
  else if(token==='pi')value=Math.PI;
  else if(token==='e')value=Math.E;
  else if(token&&Object.hasOwn(functions,token)){
   if(tokens[i++]!=='(')throw Error('Use function parentheses');const args=[sum()];while(tokens[i]===','){i++;args.push(sum())}
   if(tokens[i++]!==')'||args.length!==(token==='logbase'||token==='root'?2:1))throw Error('Invalid function arguments');value=functions[token](...args);
  }else if(token&&!Number.isNaN(Number(token)))value=Number(token);
  else throw Error('Incomplete expression');
  while(tokens[i]==='!'){i++;value=factorial(value)}return value;
 }
 function power(){const v=atom();if(tokens[i]==='^'){i++;return Math.pow(v,unary())}return v}
 function unary(){if(tokens[i]==='+'){i++;return unary()}if(tokens[i]==='-'){i++;return -unary()}return power()}
 function product(){let v=unary();while(['*','/','mod'].includes(tokens[i])){const op=tokens[i++],r=unary();if((op==='/'||op==='mod')&&r===0)throw Error('Division by zero');v=op==='*'?v*r:op==='/'?v/r:v%r}return v}
 function sum(){let v=product();while(tokens[i]==='+'||tokens[i]==='-'){const op=tokens[i++],r=product();v=op==='+'?v+r:v-r}return v}
 const result=sum();if(i!==tokens.length)throw Error('Check operators and parentheses');if(!Number.isFinite(result))throw Error('Result is outside the real-number range');return result;
}
export function displayNumber(value){return Number(value.toPrecision(12)).toString()}
