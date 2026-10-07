import {it,expect,vi} from 'vitest';import {mount,flushPromises} from '@vue/test-utils';import ScratchBoard from '../src/ScratchBoard.vue';
it('keeps separate pages and restores work after closing/remounting',async()=>{
 sessionStorage.clear();const ctx={fillRect:vi.fn(),save:vi.fn(),restore:vi.fn(),beginPath:vi.fn(),arc:vi.fn(),fill:vi.fn(),stroke:vi.fn(),moveTo:vi.fn(),lineTo:vi.fn()};const spy=vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue(ctx);
 const w=mount(ScratchBoard,{props:{sessionId:77}});const canvas=w.get('canvas');canvas.element.getBoundingClientRect=()=>({left:0,top:0,width:1400,height:900});
 await canvas.trigger('pointerdown',{pointerId:1,clientX:20,clientY:30});await canvas.trigger('pointerup',{pointerId:1});
 await w.findAll('button').find(b=>b.text()==='Page').trigger('click');await flushPromises();expect(w.text()).toContain('Page 2 / 2');w.unmount();
 const saved=JSON.parse(sessionStorage.getItem('pyq-scratch-v2-77'));expect(saved.pages[0].strokes).toHaveLength(1);expect(saved.pages[1].strokes).toHaveLength(0);
 const restored=mount(ScratchBoard,{props:{sessionId:77}});await flushPromises();expect(restored.text()).toContain('Page 2 / 2');expect(restored.findAll('.scratch-color')).toHaveLength(4);restored.unmount();spy.mockRestore();
});

it('adds typed notes and supports undo and restoring typed pages',async()=>{
 sessionStorage.clear();const ctx={fillRect:vi.fn(),save:vi.fn(),restore:vi.fn(),fillText:vi.fn()};const spy=vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue(ctx);
 const w=mount(ScratchBoard,{props:{sessionId:78,paperTitle:'Maths · Quiz 1 · Jan 2025'}});
 await w.findAll('button').find(b=>b.text()==='Type').trigger('click');const canvas=w.get('canvas');canvas.element.getBoundingClientRect=()=>({left:0,top:0,width:1400,height:900});
 await canvas.trigger('pointerdown',{clientX:30,clientY:40});await w.get('[aria-label="Scratch text"]').setValue('Step 1\nSolve x');await w.get('form').trigger('submit');
 expect(ctx.fillText).toHaveBeenCalledWith('Step 1',30,40);w.unmount();expect(JSON.parse(sessionStorage.getItem('pyq-scratch-v2-78')).pages[0].strokes[0].text).toBe('Step 1\nSolve x');
 const restored=mount(ScratchBoard,{props:{sessionId:78}});await flushPromises();await restored.get('[title="Undo (Ctrl+Z)"]').trigger('click');restored.unmount();expect(JSON.parse(sessionStorage.getItem('pyq-scratch-v2-78')).pages[0].strokes).toHaveLength(0);spy.mockRestore();
});
