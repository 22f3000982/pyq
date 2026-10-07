import {test} from 'node:test';
import assert from 'node:assert/strict';
import {scratchFilename} from '../src/scratchFilename.js';
test('scratch PDF filenames identify course, exam and term',()=>{
 assert.equal(scratchFilename('Maths 1 · Quiz 1 · Jan 2025 · Paper'),'Maths_1_Quiz-1_jan25.pdf');
 assert.equal(scratchFilename('MLF · Quiz 2 · Sep 2025 · Paper'),'MLF_Quiz-2_sept25.pdf');
 assert.equal(scratchFilename('Python · End Term · May 2026 · Afternoon'),'Python_ET_may26.pdf');
 assert.equal(scratchFilename('A/B · Quiz 1 · Jan 2025'),'A-B_Quiz-1_jan25.pdf');
});
