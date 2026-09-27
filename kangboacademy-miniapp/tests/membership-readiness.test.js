const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup(payment, freePlan = null) {
 let definition;
 const calls = [];
 const api = {
 createPayment: async () => { calls.push('order'); return { mode: 'pending_config' }; }
 };
 vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../pages/membership/membership.js'), 'utf8'), {
 Page: value => { definition = value; },
 require: name => name === '../../utils/api' ? api : {},
 wx: {
 showModal: value => calls.push(value.title),
 showToast: value => calls.push(value.title),
 showLoading() {}, hideLoading() {},
 navigateTo: value => calls.push(value.url)
 }
 });
 const page = { ...definition, data: { ...definition.data, loading: false, payment, freePlan } };
 page.setData = value => Object.assign(page.data, value);
 page.ensureLogin = async () => calls.push('login');
 return { page, calls };
}

for (const payment of [null, {}, { ready: false }, { ready: 'true' }]) {
 test(`unavailable payment never logs in or creates an order: ${JSON.stringify(payment)}`, async () => {
 const { page, calls } = setup(payment);
 await page.buyPlan({ currentTarget: { dataset: { plan: 'core_year' } } });
 assert.deepEqual(calls, ['订阅暂未开放']);
 assert.equal(page.data.paying, false);
 });
}

test('verified payment readiness retains the existing ordering path', async () => {
 const { page, calls } = setup({ ready: true });
 await page.buyPlan({ currentTarget: { dataset: { plan: 'core_year' } } });
 assert.deepEqual(calls.slice(0, 2), ['login', 'order']);
});

test('free trial uses the server-declared free IDs without logging in', () => {
 const { page, calls } = setup(null, { courses: [7], bookCourses: [63] });
 page.startFreeLesson({ currentTarget: { dataset: { scope: 'core' } } });
 page.startFreeLesson({ currentTarget: { dataset: { scope: 'books' } } });
 assert.deepEqual(calls, [
 '/pages/course-detail/course-detail?lesson=lesson7.html',
 '/pages/course-detail/course-detail?lesson=book63.html'
 ]);
});

test('missing or invalid free-course metadata never invents access', () => {
 for (const freePlan of [null, {}, { courses: [0, -1, 999, '1'] }]) {
 const { page, calls } = setup(null, freePlan);
 page.startFreeLesson({ currentTarget: { dataset: { scope: 'core' } } });
 assert.deepEqual(calls, ['免费课程暂不可用，请稍后重试']);
 }
});
