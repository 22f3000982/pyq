export function displayExamTitle(title=''){
 return title.split(' · ').filter(part=>! /\.pdf\b/i.test(part)&&!/^timed practice \(user-selected duration\)$/i.test(part.trim())).join(' · ')||'Practice session';
}
