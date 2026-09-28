import {test} from 'node:test';import assert from 'node:assert/strict';import {clock,answerText,remaining,paletteLabel} from '../src/utils.js';
test('timer clamps at zero and formats minutes',()=>{assert.equal(clock(-3),'00:00');assert.equal(clock(3661),'61:01');assert.equal(remaining(160,100,70),0);assert.equal(remaining(null,100,3),null)});
test('answer display retains zero and multiselect',()=>{assert.equal(answerText(0),'0');assert.equal(answerText(['A','B']),'A, B');assert.equal(answerText(null),'Not available')});
test('review states have distinct accessible labels',()=>{assert.equal(paletteLabel('ANSWERED_AND_MARKED_FOR_REVIEW'),'Answered and marked');assert.equal(paletteLabel('NOT_VISITED'),'Not visited')});
