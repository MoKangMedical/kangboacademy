const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const catalog = require('../utils/catalog');
const content = require('../utils/course-content');

function pageFor(file, api = {}, token = 'test-only', login = async () => {}) {
 let definition;
 const toasts = [];
 vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../pages', file, `${file}.js`), 'utf8'), {
 Page: value => { definition = value; },
 require: name => ({ '../../utils/api': api, '../../utils/catalog': catalog,
 '../../utils/course-content': content, '../../utils/commerce': require('../utils/commerce'), '../../utils/auth': { fullLogin: login } })[name],
 wx: { getStorageSync: () => token, showToast: value => toasts.push(value), pageScrollTo() {}, navigateTo: value => toasts.push(value) },
 console: { error() {} }
 });
 const page = { ...definition, data: JSON.parse(JSON.stringify(definition.data)), toasts };
 page.setData = (value, cb) => { Object.assign(page.data, value); if (cb) cb(); };
 return page;
}
const response = { total: 2, courses: [
 { id: 31, title: '储蓄与复利', lesson: 'lesson31.html', accessible: true, free: true },
 { id: 65, title: '投资体系总结', lesson: 'lesson65.html', accessible: false, locked: true }
] };

test('catalog uses server titles and never infers free access or invented duration', () => {
 const rows = catalog.normalizeCatalog(response, false);
 assert.equal(rows[0].title, '储蓄与复利');
 assert.equal(rows[0].time, '40分钟');
 assert.equal(rows[1].free, false);
 assert.equal(rows[1].locked, true);
 const unknown = catalog.normalizeCatalog({ total: 1, courses: [{ id: 1, title: 'A' }] }, false)[0];
 assert.equal(unknown.free, false);
 assert.equal(unknown.accessible, false);
 assert.equal(unknown.time, '');
});

test('catalog rejects empty, truncated, duplicate and mismatched identities', () => {
 for (const bad of [{}, { total: 0, courses: [] }, { ...response, total: 3 },
 { total: 2, courses: [response.courses[0], response.courses[0]] },
 { total: 1, courses: [{ id: 31, n: 32, title: 'X' }] },
 { total: 1, courses: [{ id: 31, title: 'X', lesson: 'lesson1.html' }] }]) {
 assert.throws(() => catalog.normalizeCatalog(bad, false));
 }
});

test('every core course is grouped once, including future IDs', () => {
 const rows = Array.from({ length: 67 }, (_, i) => ({ n: i + 1 }));
 const groups = catalog.groupCoreCourses(rows);
 assert.equal(groups.flatMap(group => group.courses).length, 67);
 assert.equal(groups.find(group => group.title === '理财基础技能').courses.length, 3);
 assert.equal(groups.at(-1).title, '新增课程');
});

test('core search survives asynchronous loading and retry', async () => {
 const page = pageFor('courses', { getCourses: async () => response });
 page.data.keyword = '储蓄';
 await page.loadCourses();
 assert.equal(page.data.total, 2);
 assert.equal(page.data.filteredCount, 1);
 assert.equal(page.data.phases.flatMap(group => group.courses)[0].title, '储蓄与复利');
 page.clearSearch();
 assert.equal(page.data.filteredCount, 2);
});

test('book failure never substitutes demo rows and retry recovers', async () => {
 let fail = true;
 const api = { getBookCourses: async () => {
 if (fail) throw new Error('offline');
 return { total: 1, courses: [{ id: 500, title: '最后一本', author: '作者', category: 'east' }],
 waves: [{ w: 17, range: [473, 500] }], categories: { east: '不得覆盖', new: '新增领域' } };
 } };
 const page = pageFor('book-courses', api);
 await page.loadCourses();
 assert.equal(page.data.filteredCount, 0);
 assert.ok(page.data.error);
 fail = false;
 await page.loadCourses();
 assert.equal(page.data.filteredCount, 1);
 assert.equal(page.data.error, '');
 assert.equal(page.data.catLabels.east, '东方智慧');
 assert.equal(page.data.categories.at(-1).key, 'new');
 page.onSearch({ detail: { value: '作者' } });
 assert.equal(page.data.filteredCount, 1);
 page.filterWave({ currentTarget: { dataset: { wave: 17 } } });
 assert.equal(page.data.filteredCount, 1);
});

test('older requests cannot overwrite a newer catalog result', async () => {
 let oldResolve, calls = 0;
 const page = pageFor('courses', { getCourses: () => ++calls === 1
 ? new Promise(resolve => { oldResolve = resolve; }) : Promise.resolve(response) });
 const oldRequest = page.loadCourses();
 await page.loadCourses();
 oldResolve({ total: 1, courses: [{ id: 1, title: 'Old' }] });
 await oldRequest;
 assert.equal(page.data.total, 2);
});

test('safe first-party images survive but handlers and foreign sources do not', () => {
 const html = content.sanitizeCourseImages('<img src="/images/a.png" onerror="bad()" width="9999">' +
 '<img src="https://evil.test/x"><img src="javascript:bad()"><IMG SRC=audio/cover.png>');
 assert.equal((html.match(/<img/g) || []).length, 2);
 assert.ok(html.includes('https://kangboacademy.cn/images/a.png'));
 assert.doesNotMatch(html, /onerror|evil|javascript|9999/);
});

test('completion requires server acknowledgement and uses distinct book IDs', async () => {
 const saved = [];
 const page = pageFor('course-detail', { saveProgress: async value => { saved.push(value); return { success: true }; } });
 page.setData({ loading: false, courseRef: 10031 });
 await page.markComplete();
 assert.equal(saved[0].course_id, 10031);
 assert.equal(saved[0].progress_percent, 100);
 assert.equal(page.data.completed, true);
 await page.markComplete();
 assert.equal(saved.length, 1);
});

test('failed or unacknowledged progress saves never display completion', async () => {
 for (const saveProgress of [async () => { throw new Error('offline'); }, async () => ({})]) {
 const page = pageFor('course-detail', { saveProgress });
 page.setData({ loading: false, courseRef: 31 });
 await page.markComplete();
 assert.equal(page.data.completed, false);
 assert.equal(page.data.savingProgress, false);
 assert.ok(page.data.progressError);
 assert.ok(page.toasts.every(toast => toast.icon !== 'success'));
 }
});

test('cancelled login never writes learning progress', async () => {
 let calls = 0;
 const page = pageFor('course-detail', { saveProgress: async () => { calls++; } }, '', async () => { throw new Error('取消'); });
 page.setData({ loading: false, courseRef: 31 });
 await page.markComplete();
 assert.equal(calls, 0);
 assert.equal(page.data.completed, false);
});

test('final course still resolves its canonical title without a next lesson', async () => {
 const page = pageFor('course-detail', { getBookCourses: async () => ({ total: 1, courses: [{ id: 500, title: '真实书名' }] }) });
 page.setData({ courseNum: 500, isBookCourse: true, title: '旧标题', nextLesson: '' });
 await page.resolveAdjacentLessonMeta(true, 500);
 assert.equal(page.data.title, '真实书名');
});

test('shop failure never fabricates book IDs or prices', async () => {
 const page = pageFor('books', { getShopBooks: async () => { throw new Error('offline'); } });
 await page.loadShopBooks();
 assert.equal(page.data.books.length, 0);
 assert.equal(page.data.filteredBooks.length, 0);
 assert.equal(page.data.shopSummary.total, 0);
 assert.ok(page.data.error);
 page.applyFilters();
});

test('detail title prefers the content service over a stale route title', async () => {
 const page = pageFor('course-detail', { getCourseContent: async () => ({ title: '储蓄与复利', content: '<p>Actual course body</p>' }) });
 for (const method of ['stopAutoRead','stopAudio','clearPracticeTimer','loadFavoriteState','schedulePracticeLoad']) page[method] = () => {};
 page.setData({ title: '巴菲特致股东的信', courseNum: 31 });
 await page.loadContent('lesson31.html');
 assert.equal(page.data.title, '储蓄与复利');
 assert.equal(page.data.audioTitle, '储蓄与复利');
});

test('knowledge graph uses real edges and navigates to corresponding lessons', async () => {
 const page = pageFor('knowledge-graph', { getKnowledgeGraph: async () => ({
 nodes: [{ id: 'L31', title: '储蓄', category: 'investment_fundamentals' }, { id: 'L32', title: '通胀', category: 'investment_fundamentals' }],
 links: [{ source: 'L31', target: 'L32' }, { source: 'L31', target: 'missing' }]
 }) });
 await page.loadGraph();
 assert.equal(page.data.nodeCount, 2);
 assert.equal(page.data.linkCount, 1);
 page.onNodeTap({ currentTarget: { dataset: { node: { id: 'L31' } } } });
 assert.equal(page.data.related[0].id, 'L32');
 page.openCourse({ currentTarget: { dataset: { id: 'L32' } } });
 assert.ok(page.toasts[0].url.includes('lesson32.html'));
});

test('search links are not advertised as confirmed products or prices', async () => {
 const page = pageFor('books', { getShopBooks: async () => ({ books: [{ id: 1, title: 'Book', channel: 'jd_search', canBuy: true, price: '68.00' }] }) });
 await page.loadShopBooks();
 assert.equal(page.data.books[0].purchaseEntryReady, false);
 assert.equal(page.data.books[0].entryText, '书名搜索');
 assert.equal(page.data.books[0].priceText, '价格以商家页面为准');
});

test('native tab pages never render a duplicate custom bottom navigation', () => {
 const app = require('../app.json');
 for (const tab of app.tabBar.list) {
 const template = fs.readFileSync(path.join(__dirname, '..', `${tab.pagePath}.wxml`), 'utf8');
 assert.doesNotMatch(template, /<app-tabbar\b/);
 }
});

test('next lesson follows a verified catalog with missing IDs and explicit order', async () => {
 const page = pageFor('course-detail', { getCourses: async () => ({ total: 3, courses: [
 { id: 31, title: 'A', order: 1 }, { id: 33, title: 'C', order: 3 }, { id: 66, title: 'B', order: 2 }
 ] }) });
 page.setData({ courseNum: 31, isBookCourse: false });
 await page.resolveAdjacentLessonMeta(false, 31);
 assert.equal(page.data.nextLesson, 'lesson66.html');
 assert.equal(page.data.nextLessonTitle, 'B');
 page.setData({ courseNum: 33 });
 await page.resolveAdjacentLessonMeta(false, 33);
 assert.equal(page.data.nextLesson, '');
});
