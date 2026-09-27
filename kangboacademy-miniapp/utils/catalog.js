const CONTRACT = require('../data/content-contract.json');
const BOOK_LABELS = {};
CONTRACT.categoryOrder.forEach(key => { BOOK_LABELS[key] = CONTRACT.categories[key]; });
const metadata = new Map(CONTRACT.courses.map(course => [course.key, course]));

function normalizeCatalog(response, isBook) {
 if (!response || !Array.isArray(response.courses) || !response.courses.length ||
 !Number.isInteger(response.total) || response.total !== response.courses.length) {
 throw new Error('课程目录为空或不完整');
 }
 const seen = new Set();
 return response.courses.map(course => {
 const n = Number(course.id || course.n);
 const title = String(course.title || course.t || '').trim();
 const lesson = `${isBook ? 'book' : 'lesson'}${n}.html`;
 if (!Number.isInteger(n) || n < 1 || !title || seen.has(n) ||
 (course.id != null && Number(course.id) !== n) ||
 (course.n != null && Number(course.n) !== n) ||
 (course.lesson && course.lesson !== lesson)) throw new Error('课程编号或链接不一致');
 seen.add(n);
 // Metadata is usable only while it still describes the current API identity/title.
 const candidate = metadata.get(`${isBook ? 'book' : 'core'}:${n}`);
 const meta = candidate && candidate.title === title ? candidate : {};
 return {
 n, id: n, title, t: title, lesson,
 order: Number.isFinite(course.order) ? course.order : n,
 a: String(course.author || course.a || ''),
 c: String(course.category || course.c || ''),
 desc: String(course.description || course.desc || meta.description || ''),
 diffLabel: String(course.diffLabel || meta.difficulty || ''), diffColor: 'tag-gold',
 time: String(course.time || meta.durationLabel || ''),
 free: course.free === true && course.locked !== true && course.accessible !== false,
 locked: course.locked === true || course.accessible === false,
 accessible: course.accessible === true && course.locked !== true
 };
 }).sort((a, b) => a.order - b.order || a.n - b.n);
}

function groupCoreCourses(courses) {
 const grouped = new Set();
 const groups = CONTRACT.phases.map(phase => {
 const members = courses.filter(course => phase.courseKeys.includes(`core:${course.n}`));
 members.forEach(course => grouped.add(course.n));
 const range = members.length ? `${members[0].n}-${members[members.length - 1].n}` : '';
 return { title: phase.title, range, sub: phase.description, courses: members };
 });
 const extra = courses.filter(course => !grouped.has(course.n));
 if (extra.length) groups.push({ title: '新增课程', range: '', sub: '网站新增内容', courses: extra });
 return groups.filter(group => group.courses.length).map(group => ({
 ...group, visible: true, count: group.courses.length, desc: group.sub
 }));
}

function normalizeWaves(waves) {
 if (!Array.isArray(waves)) return [];
 const seen = new Set();
 return waves.filter(wave => {
 if (!Number.isInteger(wave.w) || wave.w < 1 || seen.has(wave.w) ||
 !Array.isArray(wave.range) || wave.range.length !== 2 ||
 !wave.range.every(Number.isInteger) || wave.range[0] < 1 || wave.range[1] < wave.range[0]) return false;
 seen.add(wave.w);
 return true;
 }).map(wave => ({ w: wave.w, range: wave.range.slice() }));
}

module.exports = { normalizeCatalog, groupCoreCourses, normalizeWaves, BOOK_LABELS, CONTENT_VERSION: CONTRACT.contentVersion };
