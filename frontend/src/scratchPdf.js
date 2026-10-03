// Small image-backed PDF writer. No upload, external service or new dependency.
export function makePdf(images){
 const encoder=new TextEncoder(),chunks=[],offsets=[0];let size=0;
 function add(v){const bytes=typeof v==='string'?encoder.encode(v):v;chunks.push(bytes);size+=bytes.length}
 function object(id,body){offsets[id]=size;add(`${id} 0 obj\n`);add(body);add('\nendobj\n')}
 add('%PDF-1.4\n');object(1,'<< /Type /Catalog /Pages 2 0 R >>');
 object(2,`<< /Type /Pages /Count ${images.length} /Kids [${images.map((_,i)=>`${4+i*3} 0 R`).join(' ')}] >>`);
 object(3,'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');
 images.forEach((jpeg,i)=>{
  const page=4+i*3,img=page+1,content=page+2;
  object(page,`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 3 0 R >> /XObject << /Im ${img} 0 R >> >> /Contents ${content} 0 R >>`);
  offsets[img]=size;add(`${img} 0 obj\n<< /Type /XObject /Subtype /Image /Width 1400 /Height 900 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`);add(jpeg);add('\nendstream\nendobj\n');
  const stream=`q 798 0 0 513 22 55 cm /Im Do Q\nBT /F1 10 Tf 405 22 Td (Page ${i+1} / ${images.length}) Tj ET`;
  object(content,`<< /Length ${encoder.encode(stream).length} >>\nstream\n${stream}\nendstream`);
 });
 const xref=size,count=4+images.length*3;add(`xref\n0 ${count}\n0000000000 65535 f \n`);
 for(let id=1;id<count;id++)add(`${String(offsets[id]).padStart(10,'0')} 00000 n \n`);
 add(`trailer\n<< /Size ${count} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`);
 return new Blob(chunks,{type:'application/pdf'});
}
