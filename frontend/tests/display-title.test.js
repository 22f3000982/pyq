import {test} from 'node:test';
import assert from 'node:assert/strict';
import {displayExamTitle} from '../src/displayTitle.js';
test('exam heading preserves paper context without filename or verbose timer suffix',()=>{
 assert.equal(displayExamTitle('Deep Learning · Quiz 1 · May 2026 · cs3004_2026T2_Q1_NA.pdf · timed practice (user-selected duration)'),'Deep Learning · Quiz 1 · May 2026');
 assert.equal(displayExamTitle('Practice bookmarks'),'Practice bookmarks');
});
