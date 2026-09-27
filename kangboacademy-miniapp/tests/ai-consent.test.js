const assert = require('node:assert/strict');
const { test } = require('node:test');
const api = require('../utils/api');

function mockWx(decision) {
 const requests = [];
 const dialogs = [];
 global.wx = {
 hideLoading() {},
 getStorageSync() { return ''; },
 showModal(options) {
 dialogs.push(options);
 if (decision === 'fail') options.fail();
 else options.success({ confirm: decision });
 },
 request(options) {
 requests.push(options);
 options.success({ statusCode: 200, data: { success: true } });
 }
 };
 return { requests, dialogs };
}

test('practice cancellation never sends answers or reflection', async () => {
 const state = mockWx(false);
 await assert.rejects(api.submitPractice('book1.html', { q: 'answer' }, 'reflection'), /已取消/);
 assert.equal(state.requests.length, 0);
 assert.match(state.dialogs[0].content, /练习答案、课后反思/);
});

test('agent cancellation never sends a question', async () => {
 const state = mockWx(false);
 await assert.rejects(api.askAgent({ prompt: 'question' }), /已取消/);
 assert.equal(state.requests.length, 0);
 assert.match(state.dialogs[0].content, /内部账号标识/);
});

test('modal failure fails closed', async () => {
 const state = mockWx('fail');
 await assert.rejects(api.askAgent({ prompt: 'question' }), /未获得/);
 assert.equal(state.requests.length, 0);
});

test('practice consent sends the original payload exactly once', async () => {
 const state = mockWx(true);
 const answers = { q: 'answer' };
 await api.submitPractice('book1.html', answers, 'reflection');
 assert.equal(state.requests.length, 1);
 assert.match(state.requests[0].url, /\/practice\/submit$/);
 assert.deepEqual(state.requests[0].data, { lesson: 'book1.html', answers, reflection: 'reflection' });
});

test('agent requests obtain consent each time', async () => {
 const state = mockWx(true);
 await api.askAgent({ prompt: 'first question' });
 await api.askAgent({ prompt: 'second question' });
 assert.equal(state.dialogs.length, 2);
 assert.equal(state.requests.length, 2);
 assert.match(state.dialogs[0].content, /DeepSeek/);
});

test('public course browsing does not ask for AI consent', async () => {
 const state = mockWx(false);
 await api.getCourses();
 assert.equal(state.dialogs.length, 0);
 assert.equal(state.requests.length, 1);
});
