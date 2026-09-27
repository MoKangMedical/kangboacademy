const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const contract = require('../data/content-contract.json');
const makeWeb = require('../../server_patch/frontend/catalog-contract');
const mini = require('../utils/catalog');
const root = path.join(__dirname, '../..');

test('web and mini artifacts have exactly the same version and full 565 identities', () => {
 const website = JSON.parse(fs.readFileSync(path.join(root, 'server_patch/frontend/content-manifest.json'), 'utf8'));
 assert.deepEqual(website, contract);
 assert.equal(contract.courses.length, 565);
 const keys = contract.courses.map(course => course.key);
 assert.equal(new Set(keys).size, 565);
 assert.equal(new Set(contract.courses.map(course => course.legacyCourseRef)).size, 565);
});

test('every web phase and mini phase has the same IDs, titles, descriptions and duration', () => {
 const courses = contract.courses.filter(row => row.kind === 'core');
 const apiResponse = { total: courses.length, courses: courses.map(row => ({ id: row.number, title: row.title })) };
 const actual = mini.groupCoreCourses(mini.normalizeCatalog(apiResponse, false));
 const web = makeWeb(contract);
 assert.equal(actual.length, 10);
 actual.forEach((phase, i) => {
 assert.equal(phase.title, web.phases[i].title);
 assert.deepEqual(phase.courses.map(row => [row.n, row.title, row.desc, row.time]),
 web.phases[i].courses.map(row => [row.n, row.title, row.desc, row.time]));
 });
});

test('all book categories retain the locked order and names', () => {
 assert.deepEqual(Object.keys(mini.BOOK_LABELS), ['period','invest','risk','money','demo','tech','china','behavior','wealth','inequality','history','global','future','ai','bio','energy','geo','science','east']);
 assert.equal(mini.BOOK_LABELS.east, '东方智慧');
});

test('cached metadata cannot overwrite a changed server title', () => {
 const row = mini.normalizeCatalog({ total: 1, courses: [{ id: 31, title: 'A different replacement course' }] }, false)[0];
 assert.equal(row.title, 'A different replacement course');
 assert.equal(row.desc, '');
 assert.equal(row.time, '');
});

test('home renders exactly one link per core course, with safe escaped text', () => {
 const container = { dataset: {} };
 makeWeb(contract).renderHome(container);
 const links = Array.from(container.innerHTML.matchAll(/href="(lesson\d+\.html)"/g), match => match[1]);
 assert.equal(links.length, 65);
 assert.equal(new Set(links).size, 65);
 assert.equal(container.dataset.contentVersion, contract.contentVersion);
 assert.equal(makeWeb(contract).escape('<img onerror="x">'), '&lt;img onerror=&quot;x&quot;&gt;');
});

test('legacy homepage graph sidebar uses correct identities and includes all 15 advanced courses', () => {
 const source = fs.readFileSync(path.join(root, 'server_index.html'), 'utf8');
 const mapping = source.slice(source.indexOf('window.__kgCourses={'), source.indexOf('(function(){\nvar c=document.getElementById("kgEmbed")'));
 const context = { window: {}, KangboCatalog: makeWeb(contract) };
 vm.runInNewContext(mapping, context);
 const sidebar = context.window.__kgCourses;
 const advanced = sidebar['高级投资策略'];
 assert.equal(advanced.length, 15);
 for (const rows of Object.values(sidebar)) {
 for (const row of rows) {
 const course = contract.courses.find(item => item.lesson === row.link);
 if (course) assert.equal(row.title, course.title);
 }
 }
 assert.equal(advanced.find(row => row.num === '56').title, '房地产周期与REITs');
});

test('shared public metadata contains no account access decisions', () => {
 for (const course of contract.courses) {
 for (const field of ['free', 'accessible', 'locked', 'token', 'price']) assert.equal(field in course, false);
 assert.match(course.audioPath, course.kind === 'book' ? /^audio\/books\// : /^audio\/lesson/);
 assert.equal(course.audioRevision, null);
 }
});
