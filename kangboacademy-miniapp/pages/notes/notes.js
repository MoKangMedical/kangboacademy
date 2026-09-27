const api = require('../../utils/api');
const { fullLogin } = require('../../utils/auth');

function formatDate(value) {
 if (!value) return '';
 return String(value).replace('T', ' ').slice(0, 16);
}

Page({
 data: {
 isLogin: false,
 loading: false,
 error: '',
 notes: []
 },

 onShow() {
 const app = getApp();
 const isLogin = !!(app.globalData.isLogin && wx.getStorageSync('token'));
 this.setData({ isLogin });
 if (isLogin) {
 this.loadNotes();
 }
 },

 async doLogin() {
 wx.showLoading({ title: '登录中...' });
 try {
 const data = await fullLogin();
 const app = getApp();
 app.globalData.userInfo = data.userInfo;
 app.globalData.isLogin = true;
 this.setData({ isLogin: true });
 wx.hideLoading();
 this.loadNotes();
 } catch (err) {
 wx.hideLoading();
 wx.showToast({ title: err.message || '登录失败', icon: 'none' });
 }
 },

 async loadNotes() {
 this.setData({ loading: true, error: '' });
 try {
 const res = await api.getStudyNotes(100);
 const notes = (res.notes || []).map(item => ({
 ...item,
 createdText: formatDate(item.createdAt),
 scoreText: `${item.score || 0}/${item.maxScore || 100}`,
 hasAi: !!(item.aiFeedback || (item.focusPoints || []).length || (item.followUps || []).length)
 }));
 this.setData({ notes, loading: false });
 } catch (err) {
 this.setData({
 loading: false,
 error: err.message || '学习笔记加载失败'
 });
 }
 },

 openCourse(e) {
 const { lesson, title } = e.currentTarget.dataset;
 if (!lesson) return;
 wx.navigateTo({
 url: `/pages/course-detail/course-detail?lesson=${lesson}&title=${encodeURIComponent(title || '')}`
 });
 },

 goCourses() {
 wx.switchTab({ url: '/pages/courses/courses' });
 }
});
