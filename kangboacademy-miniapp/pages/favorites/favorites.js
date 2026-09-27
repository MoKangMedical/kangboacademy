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
 bookmarks: []
 },

 onShow() {
 const app = getApp();
 const isLogin = !!(app.globalData.isLogin && wx.getStorageSync('token'));
 this.setData({ isLogin });
 if (isLogin) {
 this.loadBookmarks();
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
 this.loadBookmarks();
 } catch (err) {
 wx.hideLoading();
 wx.showToast({ title: err.message || '登录失败', icon: 'none' });
 }
 },

 async loadBookmarks() {
 this.setData({ loading: true, error: '' });
 try {
 const res = await api.getBookmarks();
 const bookmarks = (res.bookmarks || []).map(item => ({
 ...item,
 createdText: formatDate(item.createdAt || item.updatedAt),
 accessText: item.locked ? '需订阅' : (item.free ? '免费' : '已开放')
 }));
 this.setData({ bookmarks, loading: false });
 } catch (err) {
 this.setData({
 loading: false,
 error: err.message || '收藏课程加载失败'
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
