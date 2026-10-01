const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const content = require('../utils/course-content');

const detailPath = path.join(__dirname, '../pages/course-detail/course-detail');

function deferred() {
 let resolve, reject;
 const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
 return { promise, resolve, reject };
}

function makePage(api = {}) {
 let definition;
 vm.runInNewContext(fs.readFileSync(`${detailPath}.js`, 'utf8'), {
 Page: value => { definition = value; },
 require: name => name === '../../utils/api' ? api : name === '../../utils/course-content' ? content : {},
 console: { error() {} },
 clearTimeout,
 });
 const page = { ...definition, data: { ...definition.data, lesson: 'lesson1.html', courseNum: 1, loading: false } };
 page.setData = value => Object.assign(page.data, value);
 page.stopAutoRead = () => {};
 page.stopAudio = () => { page.audioStops = (page.audioStops || 0) + 1; };
 page.destroyAudio = () => {};
 page.loadFavoriteState = () => {};
 page.schedulePracticeLoad = () => {};
 return page;
}

test('first show does not issue another content request', () => {
 const page = makePage();
 page.data.loading = true;
 page.loadContent = () => assert.fail('duplicate content request');
 page.onShow();
});

test('return to locked course refreshes access once and unlocks content', async () => {
 const pending = deferred();
 let calls = 0;
 const page = makePage({ getCourseContent: () => { calls += 1; return pending.promise; } });
 page.data.locked = true;
 page.onHide();
 const refresh = page.onShow();
 page.onShow();
 assert.equal(calls, 1);
 pending.resolve({ content: '<p>Available after entitlement update</p>', audioUrl: '/audio/test.mp3', locked: false });
 await refresh;
 assert.equal(page.data.locked, false);
 assert.match(page.data.readerContent, /Available after entitlement update/);
 assert.equal(page.data.audioUrl, '/audio/test.mp3');
 page.onShow();
 assert.equal(calls, 1);
});

test('return to readable course preserves audio and practice answers', () => {
 const page = makePage();
 page.data.audioPlaying = true;
 page.data.practiceQuestions = [{ id: 'q1', answer: 'draft' }];
 page.loadContent = () => assert.fail('readable course must not reload');
 page.onHide();
 page.onShow();
 assert.equal(page.data.audioPlaying, true);
 assert.equal(page.data.practiceQuestions[0].answer, 'draft');
 assert.equal(page.audioStops, undefined);
});

test('return while content is loading does not issue concurrent reload', () => {
 const page = makePage();
 page.data.locked = true;
 page.onHide();
 page.data.loading = true;
 page.loadContent = () => assert.fail('concurrent content request');
 page.onShow();
});

test('practice failure is visible and retry only reloads practice', async () => {
 let calls = 0;
 const page = makePage({ getPractice: async () => {
 calls += 1;
 if (calls === 1) throw new Error('Practice network failure');
 return { questions: [{ id: 'q1', prompt: 'Test question' }] };
 } });
 page.data.readerContent = '<p>Keep body</p>';
 page.data.audioPlaying = true;
 await page.loadPractice(page.data.lesson);
 assert.equal(page.data.practiceError, 'Practice network failure');
 assert.equal(page.data.practiceLoading, false);
 await page.retryPractice();
 assert.equal(calls, 2);
 assert.equal(page.data.practiceError, '');
 assert.equal(page.data.practiceQuestions.length, 1);
 assert.equal(page.data.readerContent, '<p>Keep body</p>');
 assert.equal(page.data.audioPlaying, true);
 assert.equal(page.audioStops, undefined);
});

test('repeated practice retry taps share the in-flight request', async () => {
 let calls = 0;
 const pending = deferred();
 const page = makePage({ getPractice: () => { calls += 1; return pending.promise; } });
 page.data.practiceError = 'Retry needed';
 const first = page.retryPractice();
 await page.retryPractice();
 await page.loadPractice(page.data.lesson);
 assert.equal(calls, 1);
 pending.resolve({ questions: [{ id: 'q1' }] });
 await first;
 assert.equal(page.data.practiceLoading, false);
});

test('practice retry respects content access and loading guards', async () => {
 for (const state of [{ locked: true }, { loading: true }, { error: 'Body failed' }]) {
 const page = makePage({ getPractice: () => assert.fail('must not request practice') });
 Object.assign(page.data, state, { practiceError: 'Retry needed' });
 await page.retryPractice();
 }
});

test('late practice response cannot repopulate a reloaded locked course', async () => {
 const pending = deferred();
 const page = makePage({ getPractice: () => pending.promise, getCourseContent: async () => ({ locked: true }) });
 const oldRequest = page.loadPractice(page.data.lesson);
 await page.loadContent(page.data.lesson);
 pending.resolve({ questions: [{ id: 'stale' }] });
 await oldRequest;
 assert.equal(page.data.locked, true);
 assert.equal(page.data.practiceQuestions.length, 0);
 assert.equal(page.data.practiceError, '');
});

test('late practice error after unload does not update the page', async () => {
 const pending = deferred();
 const page = makePage({ getPractice: () => pending.promise });
 const request = page.loadPractice(page.data.lesson);
 page.onUnload();
 page.setData = () => assert.fail('setData after unload');
 pending.reject(new Error('Late network failure'));
 await request;
});

test('empty or newly locked practice responses show recoverable feedback', async () => {
 for (const response of [{ questions: [] }, { locked: true, message: 'Access changed' }]) {
 const page = makePage({ getPractice: async () => response });
 await page.loadPractice(page.data.lesson);
 assert.ok(page.data.practiceError);
 assert.equal(page.data.practiceLoading, false);
 }
});

test('practice error remains visible in template with a dedicated retry action', () => {
 const template = fs.readFileSync(`${detailPath}.wxml`, 'utf8');
 assert.match(template, /practiceLoading \|\| practiceQuestions.length \|\| practiceError/);
 assert.match(template, /wx:if="\{\{practiceError\}\}"/);
 assert.match(template, /bindtap="retryPractice"/);
});
