export function scratchFilename(title=''){
 const parts=String(title).replace(/^Wrong-answer practice · /,'').split(' · ');
 const clean=s=>String(s||'').replace(/[<>:"/\\|?*\u0000-\u001f]/g,'-').trim().replace(/\s+/g,'_').replace(/[. ]+$/,'');
 const course=clean(parts[0])||'Scratch';
 const exam=/quiz\s*1/i.test(parts[1])?'Quiz-1':/quiz\s*2/i.test(parts[1])?'Quiz-2':/end\s*term|^ET$/i.test(parts[1])?'ET':clean(parts[1])||'Practice';
 const months={jan:'jan',feb:'feb',mar:'mar',apr:'apr',may:'may',jun:'jun',jul:'jul',aug:'aug',sep:'sept',oct:'oct',nov:'nov',dec:'dec'};
 const term=parts[2]||'',month=term.match(/[A-Za-z]+/),year=term.match(/\b(20\d{2}|\d{2})\b/);
 const label=month&&year&&months[month[0].slice(0,3).toLowerCase()]?months[month[0].slice(0,3).toLowerCase()]+year[0].slice(-2):clean(term)||'notes';
 return `${course}_${exam}_${label}.pdf`;
}
