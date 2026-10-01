const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function setup(statusCode = 200) {
 const storage = { token: 'test-fixture-only', userInfo: { name: 'Test' } };
 const app = { globalData: { isLogin: true, userInfo: storage.userInfo } };
 const calls = [];
 const module = { exports: {} };
 vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../utils/api.js'), 'utf8'), {
 module, require: () => ({ confirmAIProcessing: async () => {} }), getApp: () => app,
 wx: { getStorageSync: key => storage[key], removeStorageSync: key => { delete storage[key]; },
 request: request => { calls.push(request); if (statusCode !== null) request.success({ statusCode, data: {} }); } }
 });
 return { api: module.exports, app, calls, storage };
}

test('API rejects foreign absolute URLs before attaching credentials', async () => {
 const { api, calls } = setup();
 for (const url of ['https://evil.test/api', 'https://kangboacademy.cn.evil.test/api', '//evil.test/api', 'not-a-path']) {
 await assert.rejects(api.request(url));
 }
 assert.equal(calls.length, 0);
});

test('401 clears persisted and in-memory login state', async () => {
 const { api, app, storage } = setup(401);
 await assert.rejects(api.getProgress(), /登录已过期/);
 assert.equal(storage.token, undefined);
 assert.equal(app.globalData.isLogin, false);
 assert.equal(app.globalData.userInfo, null);
});

test('requests do not mutate caller headers', async () => {
 const { api, calls } = setup();
 const header = { 'X-Test': 'test' };
 await api.request('/courses', { header });
 assert.deepEqual(header, { 'X-Test': 'test' });
 assert.equal(calls[0].timeout, 15000);
 assert.equal(calls[0].header.Authorization, 'Bearer test-fixture-only');
});

test('late 401 from an expired session preserves a newer login', async () => {
 const { api, app, storage, calls } = setup(null);
 const first = assert.rejects(api.getProgress(), /登录已过期/);
 const second = assert.rejects(api.getBookmarks(), /登录已过期/);
 calls[0].success({ statusCode: 401, data: {} });
 await first;
 storage.token = 'new-test-session';
 storage.userInfo = { name: 'New session' };
 app.globalData.isLogin = true;
 app.globalData.userInfo = storage.userInfo;
 calls[1].success({ statusCode: 401, data: {} });
 await second;
 assert.equal(storage.token, 'new-test-session');
 assert.equal(app.globalData.isLogin, true);
 assert.equal(app.globalData.userInfo, storage.userInfo);
 assert.equal(storage.userInfo.name, 'New session');
});

test('anonymous request 401 cannot clear a subsequent login', async () => {
 const { api, app, storage, calls } = setup(null);
 delete storage.token;
 const pending = assert.rejects(api.getProgress(), /登录已过期/);
 storage.token = 'new-test-session';
 calls[0].success({ statusCode: 401, data: {} });
 await pending;
 assert.equal(storage.token, 'new-test-session');
 assert.equal(app.globalData.isLogin, true);
});
