const assert = require('node:assert/strict');
const { test } = require('node:test');
const api = require('../utils/api');

function mockWx() {
 const storage = new Map([['token', 'synthetic-token'], ['userInfo', { id: 1 }]]);
 const state = { storage, requests: [], dialogs: 0, consent: true, fail: false };
 global.wx = {
  hideLoading() {},
  getStorageSync(key) { return storage.get(key); },
  setStorageSync(key, value) { storage.set(key, value); },
  showModal(options) { state.dialogs++; options.success({ confirm: state.consent }); },
  request(options) {
   state.requests.push(options);
   if (state.fail) options.fail({ errMsg: 'request:fail timeout' });
   else options.success({ statusCode: 200, data: { success: true } });
  }
 };
 return state;
}

test('timeout retry keeps ID across helper reload and asks consent every time', async () => {
 const state = mockWx();
 state.fail = true;
 await assert.rejects(api.submitPractice('lesson1', { b: 'B', a: 'A' }), /timeout/);
 delete require.cache[require.resolve('../utils/practice-submission')];
 state.fail = false;
 await api.submitPractice('lesson1', { a: 'A', b: 'B' });
 assert.equal(state.requests[0].data.submission_id, state.requests[1].data.submission_id);
 assert.equal(state.dialogs, 2);
 assert.equal(state.requests[0].timeout, 40000);
 assert.equal(state.requests[1].timeout, 40000);
});

test('changed answers/reflection get new IDs; successful retries reuse their ID', async () => {
 const state = mockWx();
 await api.submitPractice('lesson1', { q: 'A' });
 await api.submitPractice('lesson1', { q: 'A' });
 await api.submitPractice('lesson1', { q: 'B' });
 await api.submitPractice('lesson1', { q: 'B' }, 'reflection');
 await api.submitPractice('lesson1', { q: 'A' });
 const ids = state.requests.map(r => r.data.submission_id);
 assert.equal(ids[0], ids[1]);
 assert.equal(new Set([ids[0], ...ids.slice(2)]).size, 4);
});

test('concurrent calls share ID; account and lesson isolate stored drafts', async () => {
 const state = mockWx();
 await Promise.all([api.submitPractice('lesson1', { q: 'A' }), api.submitPractice('lesson1', { q: 'A' })]);
 assert.equal(state.requests[0].data.submission_id, state.requests[1].data.submission_id);
 state.storage.set('userInfo', { id: 2 });
 await api.submitPractice('lesson1', { q: 'A' });
 await api.submitPractice('lesson2', { q: 'A' });
 assert.equal(new Set(state.requests.map(r => r.data.submission_id)).size, 3);
});

test('cancelled retry sends nothing; storage failure fails before network', async () => {
 const state = mockWx();
 await api.submitPractice('lesson1', { q: 'A' });
 state.consent = false;
 await assert.rejects(api.submitPractice('lesson1', { q: 'A' }), /已取消/);
 assert.equal(state.requests.length, 1);
 state.consent = true;
 global.wx.setStorageSync = () => { throw new Error('storage full'); };
 await assert.rejects(api.submitPractice('lesson1', { q: 'B' }), /storage full/);
 assert.equal(state.requests.length, 1);
});

test('payload is captured before consent yields to answer edits', async () => {
 const state = mockWx();
 const answers = { q: 'before' };
 const pending = api.submitPractice('lesson1', answers);
 answers.q = 'after';
 await pending;
 assert.equal(state.requests[0].data.answers.q, 'before');
});

test('request accepts bounded integer timeout only, default remains 15 seconds', async () => {
 const state = mockWx();
 for (const timeout of [undefined, null, 0, -1, 999, 60001, 40000.5, '40000', Infinity, NaN]) {
  await api.request('/courses', { timeout });
  assert.equal(state.requests.at(-1).timeout, 15000);
 }
 for (const timeout of [1000, 40000, 60000]) {
  await api.request('/courses', { timeout });
  assert.equal(state.requests.at(-1).timeout, timeout);
 }
});
