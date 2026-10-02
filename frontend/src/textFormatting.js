// Restricted emphasis only. User content never becomes HTML; math stays intact.
export function textSegments(value) {
 const text=String(value??''),parts=[];
 const tokens=/\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\*\*([^\n]+?)\*\*/g;
 let cursor=0;
 for(const match of text.matchAll(tokens)) {
  if(match.index>cursor)parts.push({text:text.slice(cursor,match.index),bold:false});
  parts.push({text:match[1]??match[0],bold:match[1]!==undefined});cursor=match.index+match[0].length;
 }
 if(cursor<text.length)parts.push({text:text.slice(cursor),bold:false});
 return parts;
}
