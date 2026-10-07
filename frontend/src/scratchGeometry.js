export const WIDTH=1400,HEIGHT=900;
const dist=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
export function recognize(points){
 if(points.length<8)return null;
 const xs=points.map(p=>p.x),ys=points.map(p=>p.y),x=Math.min(...xs),y=Math.min(...ys),w=Math.max(...xs)-x,h=Math.max(...ys)-y;
 const a=points[0],b=points.at(-1),length=points.slice(1).reduce((s,p,i)=>s+dist(points[i],p),0),chord=dist(a,b);
 if(chord>45&&length/chord<1.08&&points.every(p=>Math.abs((b.x-a.x)*(a.y-p.y)-(a.x-p.x)*(b.y-a.y))/chord<Math.max(5,chord*.025)))return {type:'line',a,b};
 if(w<35||h<35||dist(a,b)>Math.max(16,Math.min(w,h)*.22))return null;
 const cx=x+w/2,cy=y+h/2;
 const radial=points.map(p=>Math.hypot((p.x-cx)/(w/2),(p.y-cy)/(h/2)));
 const sectors=new Set(points.map(p=>Math.floor((Math.atan2((p.y-cy)/(h/2),(p.x-cx)/(w/2))+Math.PI)/(Math.PI*2)*12)%12));
 if(sectors.size>=11&&radial.every(r=>Math.abs(r-1)<.2)&&radial.reduce((s,r)=>s+Math.abs(r-1),0)/points.length<.08&&length/(Math.PI*Math.sqrt((w*w+h*h)/2))<1.2)return {type:'ellipse',x,y,w,h};
 // Hand-drawn boxes often have sloping sides and overshot corners. Allow
 // local wobble, but require a low average error and coverage of every side.
 const tol=Math.max(9,Math.min(w,h)*.20),edges=new Set();
 const errors=points.map(p=>Math.min(p.x-x,x+w-p.x,p.y-y,y+h-p.y));
 if(errors.every(e=>e<tol)&&errors.reduce((s,e)=>s+e,0)/points.length<Math.max(4,Math.min(w,h)*.075)){
  for(const p of points){const tx=(p.x-x)/w,ty=(p.y-y)/h;if(ty>.3&&ty<.7){if(p.x-x<tol)edges.add('l');if(x+w-p.x<tol)edges.add('r')}if(tx>.3&&tx<.7){if(p.y-y<tol)edges.add('t');if(y+h-p.y<tol)edges.add('b')}}
  if(edges.size===4&&length/(2*(w+h))>.8&&length/(2*(w+h))<1.2)return {type:'rect',x,y,w,h};
 }
 return null;
}
export function drawStroke(ctx,s){
 if(s.tool==='text'){ctx.save();ctx.fillStyle=s.color||'#172943';const size=Math.max(12,Math.min(72,Number(s.fontSize)||28));ctx.font=`${size}px sans-serif`;ctx.textBaseline='top';String(s.text||'').split('\n').forEach((line,i)=>ctx.fillText(line,s.x,s.y+i*size*1.25));ctx.restore();return}

 ctx.save();ctx.strokeStyle=s.tool==='eraser'?'#ffffff':s.color;ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=s.tool==='eraser'?28:4;ctx.lineJoin='round';ctx.lineCap='round';ctx.beginPath();
 const shape=s.shape;
 if(shape?.type==='ellipse')ctx.ellipse(shape.x+shape.w/2,shape.y+shape.h/2,shape.w/2,shape.h/2,0,0,Math.PI*2);
 else if(shape?.type==='rect')ctx.rect(shape.x,shape.y,shape.w,shape.h);
 else if(shape?.type==='line'){ctx.moveTo(shape.a.x,shape.a.y);ctx.lineTo(shape.b.x,shape.b.y)}
 else if(s.points.length===1){ctx.arc(s.points[0].x,s.points[0].y,ctx.lineWidth/2,0,Math.PI*2);ctx.fill()}
 else{s.points.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y))}
 ctx.stroke();ctx.restore();
}
