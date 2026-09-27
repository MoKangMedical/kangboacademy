// Read-only production audit. No authentication, orders, progress writes or AI calls.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { normalizeCatalog } = require('../kangboacademy-miniapp/utils/catalog');
const { extractCourseBody } = require('../kangboacademy-miniapp/utils/course-content');
const base = 'https://kangboacademy.cn';
const output = process.argv[2];
const full = process.argv.includes('--all');
let serviceUnavailable = false;
if (!output) throw new Error('Usage: node tools/audit_content_sync.cjs /absolute/new-output-dir');
fs.mkdirSync(output, { recursive: false });
const plain = value => String(value || '').replace(/<script\b[\s\S]*?<\/script>/gi, '')
 .replace(/<style\b[\s\S]*?<\/style>/gi, '').replace(/<[^>]*>/g, '').replace(/\s+/g, '');
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
async function fetchText(route) {
 await new Promise(resolve => setTimeout(resolve, 1800));
 const response = await fetch(base + route, { signal: AbortSignal.timeout(20000) });
 if (!response.ok) {
 if ([429, 502, 503, 504].includes(response.status)) serviceUnavailable = true;
 throw new Error(`HTTP ${response.status}`);
 }
 return response.text();
}
async function main() {
 const startedAt = new Date().toISOString();
 const coreResponse = JSON.parse(await fetchText('/api/courses'));
 const bookResponse = JSON.parse(await fetchText('/api/book-courses'));
 const core = normalizeCatalog(coreResponse, false);
 const books = normalizeCatalog(bookResponse, true);
 const catalog = [...core.map(row => ({ ...row, type: 'core' })), ...books.map(row => ({ ...row, type: 'book' }))];
 fs.writeFileSync(path.join(output, 'catalog.json'), JSON.stringify({ startedAt, catalog }, null, 2));
 const samples = new Set(['lesson1.html', 'lesson27.html', 'lesson31.html', 'lesson40.html',
 'lesson49.html', 'lesson51.html', 'lesson58.html', 'lesson65.html',
 'book1.html', 'book63.html', 'book337.html', 'book500.html']);
 const selected = full ? catalog : catalog.filter(row => samples.has(row.lesson));
 const rows = [];
 let cursor = 0, finished = 0;
 async function worker() {
 while (cursor < selected.length && !serviceUnavailable) {
 const index = cursor++;
 const course = selected[index];
 const row = { type: course.type, id: course.n, title: course.title, lesson: course.lesson,
 webUrl: `${base}/${course.lesson}`, miniRoute: `/pages/course-detail/course-detail?lesson=${course.lesson}`,
 declaredAccessible: course.accessible, errors: [] };
 try {
 const web = await fetchText(`/${course.lesson}`);
 row.webTitle = plain((web.match(/<h1\b[^>]*>([\s\S]*?)<\/h1>/i) || [])[1]);
 row.webBodyChars = plain(extractCourseBody(web)).length;
 row.webHash = hash(web);
 const title = plain(course.title);
 row.titleRelation = row.webTitle === title ? 'exact' : row.webTitle.includes(title) ? 'expanded_web_title' : 'needs_review';
 } catch (error) { row.errors.push(`web: ${error.message}`); }
 if (!serviceUnavailable) try {
 const endpoint = course.type === 'book' ? 'book-course-content' : 'course-content';
 const api = JSON.parse(await fetchText(`/api/${endpoint}/${course.lesson}`));
 row.locked = api.locked === true;
 const body = extractCourseBody(api.content || '');
 row.apiBodyChars = plain(body).length;
 row.apiBodyHash = hash(body);
 row.apiImages = (body.match(/<img\b/gi) || []).length;
 row.apiTitle = api.title || '';
 row.audioUrl = api.audioUrl || '';
 row.apiDocumentWrapper = /<(?:html|head|body)\b/i.test(api.content || '');
 if (!row.locked && row.apiBodyChars < 100) row.errors.push('api: body_missing_or_short');
 if (course.accessible && row.locked) row.errors.push('api: access_changed_or_inconsistent');
 } catch (error) { row.errors.push(`api: ${error.message}`); }
 rows[index] = row;
 fs.writeFileSync(path.join(output, 'checkpoint.json'), JSON.stringify({ startedAt, serviceUnavailable, rows }, null, 2));
 finished++;
 if (finished % 50 === 0) console.log(`Checked ${finished}/${catalog.length}`);
 }
 }
 // Serial, paced requests; stop at the first overload response, without retries.
 await worker();
 const summary = {
 startedAt, finishedAt: new Date().toISOString(), core: core.length, books: books.length,
 mappedRoutes: catalog.length, detailsRequested: selected.length, detailsChecked: rows.length,
 stoppedForServiceError: serviceUnavailable, errors: rows.filter(row => row.errors.length).length,
 apiReadable: rows.filter(row => !row.locked && row.apiBodyChars >= 100).length,
 locked: rows.filter(row => row.locked).length,
 titleNeedsReview: rows.filter(row => row.titleRelation === 'needs_review').length,
 audioUrlProvided: rows.filter(row => row.audioUrl).length,
 scope: `${full ? 'All' : 'Sampled'} public page/API details; all catalog IDs mapped. No semantic equivalence, factual review, audio listening, login merging, payment or release verification.`
 };
 fs.writeFileSync(path.join(output, 'audit.json'), JSON.stringify({ summary, rows }, null, 2));
 const fields = ['type','id','title','lesson','webTitle','titleRelation','webBodyChars','apiBodyChars','locked','apiImages','audioUrl','errors'];
 const csv = [fields, ...rows.map(row => fields.map(key => Array.isArray(row[key]) ? row[key].join('; ') : row[key] ?? ''))]
 .map(row => row.map(value => `"${String(value).replace(/"/g, '""')}"`).join(',')).join('\n');
 fs.writeFileSync(path.join(output, 'course-mapping.csv'), '\ufeff' + csv);
 console.log(JSON.stringify(summary));
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
