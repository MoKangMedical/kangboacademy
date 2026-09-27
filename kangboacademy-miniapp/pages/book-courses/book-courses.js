const api = require('../../utils/api');
const { normalizeCatalog, normalizeWaves, BOOK_LABELS } = require('../../utils/catalog');

Page({
 data: {
 categories: Object.keys(BOOK_LABELS).map(key => ({ key, label: BOOK_LABELS[key] })),
 catLabels: BOOK_LABELS, waves: [], activeCat: 'all', activeWave: 0, keyword: '',
 allCourses: [], filteredCourses: [], filteredCount: 0, total: 0, loading: true, error: ''
 },
 onShow() { return this.loadCourses(); },

 async loadCourses() {
 const requestId = (this.requestId || 0) + 1;
 this.requestId = requestId;
 this.setData({ loading: true, error: '', allCourses: [], filteredCourses: [], total: 0, filteredCount: 0 });
 try {
 const res = await api.getBookCourses();
 if (requestId !== this.requestId) return;
 const courses = normalizeCatalog(res, true);
 const waves = normalizeWaves(res.waves);
 // Preserve the 19 locked labels, but permit new server categories at the end.
 const labels = { ...BOOK_LABELS };
 Object.keys(res.categories || {}).forEach(key => {
 if (!Object.prototype.hasOwnProperty.call(labels, key)) labels[key] = String(res.categories[key]);
 });
 const activeWave = waves.some(wave => wave.w === this.data.activeWave) ? this.data.activeWave : 0;
 const activeCat = Object.prototype.hasOwnProperty.call(labels, this.data.activeCat) ? this.data.activeCat : 'all';
 this.setData({ allCourses: courses, total: courses.length, waves, activeWave, activeCat,
 categories: Object.keys(labels).map(key => ({ key, label: labels[key] })), catLabels: labels, loading: false });
 this.applyFilters();
 } catch (err) {
 if (requestId !== this.requestId) return;
 this.setData({ loading: false, error: '书目目录暂时无法同步，请检查网络后重试。' });
 }
 },
 filterCat(e) { this.setData({ activeCat: e.currentTarget.dataset.cat }); this.applyFilters(); },
 filterWave(e) { this.setData({ activeWave: Number(e.currentTarget.dataset.wave) }); this.applyFilters(); },
 onSearch(e) { this.setData({ keyword: e.detail.value }); this.applyFilters(); },

 applyFilters() {
 const { activeCat, activeWave, allCourses, waves, keyword } = this.data;
 const query = keyword.toLowerCase().trim();
 const wave = waves.find(item => item.w === activeWave);
 const filtered = allCourses.filter(course =>
 (activeCat === 'all' || course.c === activeCat) &&
 (!wave || (course.n >= wave.range[0] && course.n <= wave.range[1])) &&
 (!query || `${course.n} ${course.t} ${course.a}`.toLowerCase().includes(query)));
 this.setData({ filteredCourses: filtered, filteredCount: filtered.length });
 },
 openCourse(e) {
 const { lesson, title } = e.currentTarget.dataset;
 wx.navigateTo({ url: `/pages/course-detail/course-detail?lesson=${lesson}&title=${encodeURIComponent(title)}` });
 }
});
