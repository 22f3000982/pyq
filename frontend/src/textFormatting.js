// Restricted emphasis only. User content never becomes HTML; math stays intact.
export function textSegments(value,inlineDollar=false) {
 const text=String(value??''),parts=[];
 const baseTokens=/\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\*\*([^\n]+?)\*\*/g;
 const tokens=inlineDollar?/\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|(?<!\\)\$(?!\$)(?:\\.|[^$\\\n])+\$|\*\*([^\n]+?)\*\*/g:baseTokens;
 let cursor=0;
 for(const match of text.matchAll(tokens)) {
  if(match.index>cursor)parts.push({text:text.slice(cursor,match.index),bold:false});
  parts.push({text:match[1]??match[0],bold:match[1]!==undefined});cursor=match.index+match[0].length;
 }
 if(cursor<text.length)parts.push({text:text.slice(cursor),bold:false});
 return parts;
}
