import {test} from 'node:test';import assert from 'node:assert/strict';import {recognize} from '../src/scratchGeometry.js';import {makePdf} from '../src/scratchPdf.js';
test('recognizes simple shapes and leaves irregular writing unchanged',()=>{
 const line=Array.from({length:30},(_,i)=>({x:10+i*5,y:30+i*.1}));assert.equal(recognize(line).type,'line');
 const ellipse=Array.from({length:81},(_,i)=>({x:200+100*Math.cos(i*Math.PI/40),y:150+60*Math.sin(i*Math.PI/40)}));assert.equal(recognize(ellipse).type,'ellipse');
 const box=[];for(let edge=0;edge<4;edge++)for(let i=0;i<=20;i++){const t=i/20;box.push([{x:50+100*t,y:50},{x:150,y:50+100*t},{x:150-100*t,y:150},{x:50,y:150-100*t}][edge])}assert.equal(recognize(box).type,'rect');
 assert.equal(recognize(Array.from({length:60},(_,i)=>({x:i*3,y:Math.sin(i)*40+100}))),null);
});
test('PDF contains ordered pages and valid xref offsets',async()=>{const blob=makePdf([new Uint8Array([255,216,255,217]),new Uint8Array([255,216,255,217])]);const bytes=new Uint8Array(await blob.arrayBuffer()),s=new TextDecoder().decode(bytes);assert.match(s,/Page 1 \/ 2/);assert.match(s,/Page 2 \/ 2/);assert.match(s,/\/Count 2/);const start=Number(s.match(/startxref\n(\d+)/)[1]);assert.equal(new TextDecoder().decode(bytes.slice(start,start+4)),'xref')});

test('recognizes uneven boxes without turning triangles into rectangles',()=>{
 const trace=corners=>corners.flatMap((a,i)=>{const b=corners[(i+1)%corners.length];return Array.from({length:21},(_,j)=>({x:a.x+(b.x-a.x)*j/20,y:a.y+(b.y-a.y)*j/20}));});
 for(const corners of [[{x:50,y:65},{x:180,y:50},{x:175,y:160},{x:55,y:145}],[{x:50,y:60},{x:280,y:50},{x:270,y:150},{x:55,y:145}]])assert.equal(recognize(trace(corners))?.type,'rect');
 assert.equal(recognize(trace([{x:50,y:50},{x:180,y:150},{x:50,y:150}])),null);
});
