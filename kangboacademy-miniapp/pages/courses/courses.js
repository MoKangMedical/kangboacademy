const api = require('../../utils/api');
const { normalizeCatalog, groupCoreCourses } = require('../../utils/catalog');

Page({
 data: { phases: [], keyword: '', filteredCount: 0, total: 0, loading: true, error: '' },
 allPhases: [],
 onShow() { return this.loadCourses(); },

 async loadCourses() {
 const requestId = (this.requestId || 0) + 1;
 this.requestId = requestId;
 this.allPhases = [];
 this.setData({ loading: true, error: '', phases: [], total: 0, filteredCount: 0 });
 try {
 const result = await api.getCourses();
 if (requestId !== this.requestId) return;
 const courses = normalizeCatalog(result, false);
 this.allPhases = groupCoreCourses(courses);
 this.setData({ loading: false, total: courses.length });
 this.applySearch();
 } catch (err) {
 if (requestId !== this.requestId) return;
 this.setData({ loading: false, error: '课程目录暂时无法同步，请检查网络后重试。' });
 }
 },

 applySearch() {
 const keyword = this.data.keyword.toLowerCase().trim();
 const phases = this.allPhases.map(phase => {
 const courses = phase.courses.filter(course => !keyword ||
 `${course.n} ${course.title} ${course.desc}`.toLowerCase().includes(keyword));
 return { ...phase, courses, visible: courses.length > 0 };
 });
 this.setData({ phases, filteredCount: phases.reduce((total, phase) => total + phase.courses.length, 0) });
 },
 onSearch(e) { this.setData({ keyword: e.detail.value }); this.applySearch(); },
 clearSearch() { this.setData({ keyword: '' }); this.applySearch(); }
});
