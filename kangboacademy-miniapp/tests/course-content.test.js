const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { extractCourseBody, sanitizeCourseImages } = require('../utils/course-content');

test('extracts formatted HTML with nested divs and reordered attributes', () => {
 const html = '<!DOCTYPE html><html><head><title>Title</title></head><body><nav>Menu</nav>' +
 '<div id="lesson" class="content reader"><h2>Main</h2><div><p>Actual book ideas</p></div><p>Last paragraph</p></div>' +
 '<div class="bottom-nav" id="next">Next</div></body></html>';
 assert.equal(extractCourseBody(html), '<h2>Main</h2><div><p>Actual book ideas</p></div><p>Last paragraph</p>');
});

test('handles a document truncated before the exercises', () => {
 const html = '<html><head><style>p{}</style></head><body><div class="content"><h2>Main</h2><p>Book ideas</p>';
 assert.equal(extractCourseBody(html), '<h2>Main</h2><p>Book ideas</p>');
});

test('preserves existing fragments and article bodies', () => {
 assert.equal(extractCourseBody('<p>Core lesson</p>'), '<p>Core lesson</p>');
 assert.equal(extractCourseBody('<ARTICLE><p>Outer</p><article><p>Inner</p></article><p>End</p></ARTICLE>'), '<p>Outer</p><p>Inner</p><p>End</p>');
});

test('ignores fake content in comments and scripts', () => {
 assert.equal(extractCourseBody('<!--<div class="content">Fake</div>--><script>"<article>fake</article>"</script><div CLASS = \'content\'><p>Real</p></div>'), '<p>Real</p>');
});

function makePage(response) {
 let definition;
 const api = { getBookCourseContent: async () => response, getCourseContent: async () => response };
 vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../pages/course-detail/course-detail.js'), 'utf8'), {
 Page: value => { definition = value; },
 require: name => name === '../../utils/api' ? api : name === '../../utils/auth' ? {} : { extractCourseBody, sanitizeCourseImages },
 console: { error() {} },
 });
 const page = { ...definition, data: { ...definition.data, title: 'Book', courseNum: 63 } };
 page.setData = value => Object.assign(page.data, value);
 for (const method of ['stopAutoRead', 'stopAudio', 'clearPracticeTimer', 'loadFavoriteState']) page[method] = () => {};
 page.schedulePracticeLoad = () => { page.practiceScheduled = true; };
 return page;
}

test('detail loader does not silently show exercises without a body', async () => {
 const page = makePage({ content: '', accessible: true, locked: false });
 await page.loadContent('book63.html');
 assert.ok(page.data.error.includes('正文'));
 assert.equal(page.practiceScheduled, undefined);
});

test('locked courses still respect subscription access', async () => {
 const page = makePage({ locked: true, requiredPlan: 'books_year' });
 await page.loadContent('book63.html');
 assert.equal(page.data.locked, true);
 assert.equal(page.data.readerContent, '');
 assert.equal(page.practiceScheduled, undefined);
});

test('detail loader preserves real body, separates recommendations, then loads practice', async () => {
 const page = makePage({ content: '<div class="content"><p>Specific book arguments</p><h2>推荐阅读</h2><ul><li>《Another book》 Author</li></ul></div>' });
 await page.loadContent('book63.html');
 assert.ok(page.data.readerContent.includes('Specific book arguments'));
 assert.ok(!page.data.readerContent.includes('Another book'));
 assert.equal(page.data.recommendedBooks.length, 1);
 assert.equal(page.practiceScheduled, true);
});

const fixture = path.join(__dirname, '../../reports/book-content-check-20260831/api-book63.json');
test('captured live API response no longer leaks document wrappers into rich-text', { skip: !fs.existsSync(fixture) }, async () => {
 const response = JSON.parse(fs.readFileSync(fixture, 'utf8'));
 assert.equal(response.locked, false);
 assert.match(response.content, /<html\b/i);
 const page = makePage(response);
 await page.loadContent('book63.html');
 assert.equal(page.data.error, '');
 assert.ok(page.data.readerContent.length > 1000);
 assert.doesNotMatch(page.data.readerContent, /<(?:html|head|body|main|nav)\b/i);
 assert.ok(page.data.readerContent.includes('核心思想'));
 assert.equal(page.practiceScheduled, true);
});
