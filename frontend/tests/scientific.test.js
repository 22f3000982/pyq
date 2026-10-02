import {test} from 'node:test';import assert from 'node:assert/strict';import {calculate} from '../src/scientific.js';
test('scientific operations and degree/radian modes',()=>{
 for(const [text,result] of [['2+3*4',14],['(2+3)*4',20],['2^3^2',512],['-2^2',-4],['2^-3',.125],['5!',120],['sin(30)',.5],['logbase(2,8)',3],['root(3,-27)',-3],['1e3+2',1002],['10 mod 3',1]])assert.ok(Math.abs(calculate(text)-result)<1e-10,text);
 assert.ok(Math.abs(calculate('sin(pi/2)',false)-1)<1e-10);
});
test('rejects invalid domains, malformed expressions and code',()=>{for(const text of ['1/0','sqrt(-1)','tan(90)','(-2)!','171!','2+','2pi','window.alert(1)','constructor(1)','logbase(1,2)','root(0,2)'])assert.throws(()=>calculate(text),undefined,text)});
