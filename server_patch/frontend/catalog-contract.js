(function (root, factory) {
 if (typeof module === 'object' && module.exports) module.exports = factory;
 else root.KangboCatalog = factory(root.KANGBO_CONTENT);
})(typeof window === 'undefined' ? this : window, function (manifest) {
 'use strict';
 if (!manifest || manifest.schemaVersion !== 1) throw new Error('Shared course manifest is missing');
 const byKey = new Map(manifest.courses.map(course => [course.key, course]));
 const byLesson = new Map(manifest.courses.map(course => [course.lesson, course]));
 const escape = value => String(value || '').replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[char]);
 const phases = manifest.phases.map(phase => ({
 id: phase.id, icon: '', title: phase.title, sub: phase.description,
 courses: phase.courseKeys.map(key => {
 const course = byKey.get(key);
 if (!course) throw new Error(`Unresolved course: ${key}`);
 return { n: course.number, title: course.title, desc: course.description,
 diff: '', diffLabel: course.difficulty, time: course.durationLabel, file: '',
 lesson: course.lesson, audio: course.audioPath };
 })
 }));

 function renderHome(container) {
 if (!container) return;
 container.innerHTML = phases.map((phase, index) =>
 `<div style="margin:32px auto 16px;max-width:900px"><h3 style="color:var(--gold)">Phase ${index + 1}：${escape(phase.title)}</h3><p>${escape(phase.sub)}</p></div>` +
 `<div class="grid-2" style="max-width:900px;margin:0 auto">` + phase.courses.map(course =>
 `<a href="${escape(course.lesson)}" class="course-card fade-in" style="display:block"><div style="display:flex"><div class="course-num">${course.n}</div><div class="course-body"><h3>${escape(course.title)}</h3><p>${escape(course.desc)}</p><div class="course-tags"><span class="course-tag">${escape(course.diffLabel)}</span><span class="course-tag">${escape(course.time)}</span></div></div></div></a>`).join('') + '</div>'
 ).join('');
 container.dataset.contentVersion = manifest.contentVersion;
 }

 function sidebar(existing) {
 const result = {};
 Object.keys(existing || {}).forEach(key => {
 result[key] = existing[key].map(row => {
 const course = byLesson.get(row.link);
 return course ? { ...row, num: String(course.number), title: course.title,
 meta: [course.difficulty, course.durationLabel].filter(Boolean).join(' · ') } : row;
 });
 });
 const aliases = ['周期理论基础', '投资大师智慧', '经济学派对决', '周期实战应用',
 '读懂中国经济', '生活经济学', '理财基础技能', '经济史与金融', '投资实战未来', '高级投资策略'];
 phases.forEach((phase, index) => {
 const rows = phase.courses.map(course => ({ num: String(course.n), title: course.title,
 meta: [course.diffLabel, course.time].filter(Boolean).join(' · '), link: course.lesson }));
 result[phase.title] = rows;
 if (aliases[index]) result[aliases[index]] = rows;
 });
 return result;
 }
 return { phases, renderHome, sidebar, escape, contentVersion: manifest.contentVersion };
});
