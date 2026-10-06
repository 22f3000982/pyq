// @vitest-environment jsdom
import {it,expect} from 'vitest';
it('renders safe bold text and LaTeX on the public reading page',async()=>{
 document.body.innerHTML='<div class="math-copy"></div>';
 document.querySelector('.math-copy').textContent='**Step 1**: \\(2+2=4\\)';
 await import('../src/study');
 expect(document.querySelector('strong')?.textContent).toBe('Step 1');
 expect(document.querySelector('.katex')).toBeTruthy();
});
