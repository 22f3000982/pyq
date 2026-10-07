import {it,expect,vi} from 'vitest';
import {readFileSync} from 'node:fs';
it('restores and persists the shared theme on public pages',()=>{
 localStorage.setItem('pyq-theme','dark');document.body.innerHTML='<button id="study-theme-toggle"></button>';
 window.matchMedia=vi.fn(()=>({matches:false}));window.eval(readFileSync('public/study-theme.js','utf8'));document.dispatchEvent(new Event('DOMContentLoaded'));
 expect(document.documentElement.dataset.theme).toBe('dark');expect(document.documentElement.dataset.bsTheme).toBe('dark');document.getElementById('study-theme-toggle').click();
 expect(document.documentElement.dataset.theme).toBe('light');expect(localStorage.getItem('pyq-theme')).toBe('light');
});
