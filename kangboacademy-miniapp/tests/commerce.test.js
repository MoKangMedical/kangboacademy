const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const commerce = require('../utils/commerce');

function page(name, api = {}, storage = {}) {
 let definition;
 const calls = [];
 vm.runInNewContext(fs.readFileSync(path.join(__dirname, `../pages/${name}/${name}.js`), 'utf8'), {
 Page: value => { definition = value; },
 require: id => id.endsWith('/api') ? api : id.endsWith('/commerce') ? commerce :
 id.endsWith('/catalog') ? require('../utils/catalog') : {},
 wx: { getStorageSync: key => storage[key], setStorageSync: (key, value) => { storage[key] = value; },
 showLoading() {}, hideLoading() {}, showToast: v => calls.push(['toast', v]), showModal: v => calls.push(['modal', v]),
 navigateToMiniProgram: v => calls.push(['navigate', v]), setClipboardData: v => calls.push(['copy', v]) }
 });
 const instance = { ...definition, data: JSON.parse(JSON.stringify(definition.data)), calls };
 instance.setData = value => Object.assign(instance.data, value);
 return instance;
}

test('search and canBuy never establish a concrete product or commission', () => {
 const result = commerce.summarize([{ channel: 'jd_search', purchaseEntryReady: true, commissionReady: true }, { canBuy: true }]);
 assert.equal(result.purchaseEntryBooks, 0);
 assert.equal(result.directCommissionBooks, 0);
 assert.equal(result.searches, 1);
});

test('unsafe targets and unverified business views are rejected', () => {
 for (const url of ['http://shop.test/a', 'javascript:alert(1)', 'https://user@shop.test/a', 'https://shop.test\\@evil.test']) {
 assert.equal(commerce.validateAction({ type: 'clipboard', url }), false);
 }
 assert.equal(commerce.validateAction({ type: 'business_view', businessType: 'wxShop' }), false);
 assert.equal(commerce.validateAction({ type: 'mini_program', appId: 'wx0123456789abcdef', path: 'pages/../index' }), false);
 assert.equal(commerce.validateAction({ type: 'mini_program', appId: 'wx0123456789abcdef', path: 'pages/product/detail?id=123' }), true);
});

test('summary recomputes from rows even if server totals claim 500 ready', async () => {
 const p = page('books', { getShopBooks: async () => ({ books: [{ id: 1, title: 'B', channel: 'jd_search' }],
 shop: { purchaseEntryBooks: 500, directCommissionReady: true, directCommissionBooks: 500 } }) });
 await p.loadShopBooks();
 assert.equal(p.data.shopSummary.purchaseEntryBooks, 0);
 assert.equal(p.data.shopSummary.directCommissionReady, false);
 assert.equal(p.data.categories.length, 19);
});

test('failed resolution never falls back to stale product or shop homepage', async () => {
 const storage = {};
 const p = page('books', { resolveShopBook: async () => { throw new Error('offline'); } }, storage);
 p.data.shopConfig = { appId: 'wx0123456789abcdef', homePath: 'pages/index/index' };
 await p.openShopTarget({ id: 1, title: 'B', externalUrl: 'https://shop.test/1' });
 assert.equal(p.calls.some(([name]) => ['copy', 'navigate'].includes(name)), false);
 assert.equal(storage.bookPurchaseLeads, undefined);
 assert.equal(p.data.opening, false);
});

test('duplicate taps resolve once; navigation records only pending interest on success', async () => {
 let done, count = 0;
 const storage = {};
 const p = page('books', { resolveShopBook: () => { count++; return new Promise(resolve => { done = resolve; }); } }, storage);
 const book = { id: 1, title: 'B' };
 const first = p.openShopTarget(book);
 await p.openShopTarget(book);
 assert.equal(count, 1);
 done({ action: { type: 'mini_program', appId: 'wx0123456789abcdef', path: 'pages/product/detail?id=1', canBuy: true } });
 await first;
 assert.equal(storage.bookPurchaseLeads, undefined);
 const navigation = p.calls.find(([type]) => type === 'navigate')[1];
 assert.equal(navigation.envVersion, 'release');
 navigation.success();
 assert.equal(storage.bookPurchaseLeads[0].status, 'pending');
});

test('unverified and local purchase records never become paid', () => {
 const p = page('membership');
 const rows = [{}, { status: 'paid' }, { status: 'paid', paymentVerified: true }];
 assert.deepEqual(Array.from(p.normalizePurchasedBooks(rows), row => row.status), ['pending', 'pending', 'paid']);
 assert.deepEqual(Array.from(p.normalizePurchasedBooks(rows, true), row => row.status), ['pending', 'pending', 'pending']);
});

test('truncated or duplicate shop catalog fails closed', async () => {
 for (const response of [{ total: 2, books: [{ id: 1, title: 'B' }] },
 { books: [{ id: 1, title: 'B' }, { id: 1, title: 'C' }] }]) {
 const p = page('books', { getShopBooks: async () => response });
 await p.loadShopBooks();
 assert.ok(p.data.error);
 assert.equal(p.data.books.length, 0);
 }
});

test('authorization revoked after catalog load blocks stale product navigation', async () => {
 const p = page('books', { resolveShopBook: async () => ({ action: {
 type: 'mini_program', appId: 'wx0123456789abcdef', path: 'pages/product/detail?id=1', canBuy: false,
 entryKind: 'configured_product' } }) });
 await p.openShopTarget({ id: 1, title: 'B', purchaseEntryReady: true });
 assert.equal(p.calls.some(([type]) => type === 'navigate'), false);
 assert.equal(p.calls.find(([type]) => type === 'modal')[1].title, '入口暂不可用');
});
