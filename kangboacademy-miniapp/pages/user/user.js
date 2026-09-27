// 我的
const { fullLogin, logout } = require('../../utils/auth');
const api = require('../../utils/api');

Page({
 data: {
 userInfo: null,
 isLogin: false,
 phoneDraft: '',
 savingPhone: false,
 dailyRefinement: null,
 streakDays: 0,
 badgesEarned: 0,
 recentBadges: []
 },

 onShow() {
 const app = getApp();
 if (app.globalData.isLogin) {
 this.setData({
 userInfo: app.globalData.userInfo,
 isLogin: true,
 phoneDraft: app.globalData.userInfo?.phone || ''
 });
 this.loadLearningStatus();
 } else {
 this.setData({ userInfo: null, isLogin: false, phoneDraft: '', dailyRefinement: null,
 streakDays: 0, badgesEarned: 0, recentBadges: [] });
 }
 },

 async doLogin() {
 wx.showLoading({ title: '登录中...' });
 try {
 const data = await fullLogin();
 const app = getApp();
 app.globalData.userInfo = data.userInfo;
 app.globalData.isLogin = true;

 this.setData({
 userInfo: data.userInfo,
 isLogin: true,
 phoneDraft: data.userInfo?.phone || ''
 });
 this.loadLearningStatus();
 wx.hideLoading();
 wx.showToast({ title: '登录成功', icon: 'success' });
 } catch (err) {
 wx.hideLoading();
 wx.showToast({ title: '登录失败，请重试', icon: 'none' });
 }
 },

 doLogout() {
 wx.showModal({
 title: '退出登录',
 content: '确定要退出登录吗？学习记录将保留。',
 success: res => {
 if (res.confirm) {
 logout();
 this.setData({
 userInfo: null,
 isLogin: false,
 phoneDraft: '',
 dailyRefinement: null,
 streakDays: 0,
 badgesEarned: 0,
 recentBadges: []
 });
 wx.showToast({ title: '已退出', icon: 'none' });
 }
 }
 });
 },

 async loadLearningStatus() {
 if (!wx.getStorageSync('token')) return;
 try {
 const [daily, badges] = await Promise.all([
 api.getDailyRefinement(),
 api.getBadges()
 ]);
 this.setData({
 dailyRefinement: (daily.days || [])[0] || null,
 streakDays: daily.streakDays || 0,
 badgesEarned: badges.totalEarned || 0,
 recentBadges: (badges.earned || []).slice(0, 3)
 });
 } catch (err) {
 // 学习状态加载失败不影响个人页基础功能。
 }
 },

 onPhoneInput(e) {
 this.setData({ phoneDraft: e.detail.value });
 },

 async ensureLogin() {
 if (this.data.isLogin && wx.getStorageSync('token')) return true;
 await this.doLogin();
 return !!wx.getStorageSync('token');
 },

 updateLocalUser(userInfo) {
 const app = getApp();
 const merged = { ...(app.globalData.userInfo || {}), ...(userInfo || {}) };
 app.globalData.userInfo = merged;
 app.globalData.isLogin = true;
 wx.setStorageSync('userInfo', merged);
 this.setData({
 userInfo: merged,
 isLogin: true,
 phoneDraft: merged.phone || this.data.phoneDraft
 });
 },

 async bindPhoneFromWechat(e) {
 if (e.detail.errMsg !== 'getPhoneNumber:ok' || !e.detail.code) {
 wx.showToast({ title: '未授权手机号', icon: 'none' });
 return;
 }
 this.setData({ savingPhone: true });
 wx.showLoading({ title: '绑定手机号...' });
 try {
 await this.ensureLogin();
 const res = await api.bindWechatPhone({ code: e.detail.code });
 this.updateLocalUser(res.userInfo || res.user);
 wx.hideLoading();
 wx.showToast({ title: '手机号已绑定', icon: 'success' });
 } catch (err) {
 wx.hideLoading();
 wx.showToast({ title: err.message || '绑定失败', icon: 'none' });
 }
 this.setData({ savingPhone: false });
 },

 async savePhone() {
 const phone = (this.data.phoneDraft || '').trim();
 if (!phone) {
 wx.showToast({ title: '请填写手机号', icon: 'none' });
 return;
 }
 if (!/^\+?\d{6,20}$/.test(phone.replace(/[\s\-()]/g, ''))) {
 wx.showToast({ title: '手机号格式不正确', icon: 'none' });
 return;
 }
 this.setData({ savingPhone: true });
 wx.showLoading({ title: '保存中...' });
 try {
 await this.ensureLogin();
 const res = await api.bindWechatPhone({ phone });
 this.updateLocalUser(res.userInfo || res.user || { phone });
 wx.hideLoading();
 wx.showToast({ title: '已保存', icon: 'success' });
 } catch (err) {
 wx.hideLoading();
 wx.showToast({ title: err.message || '保存失败', icon: 'none' });
 }
 this.setData({ savingPhone: false });
 },

 goPage(e) {
 const url = e.currentTarget.dataset.url;
 const tabPages = [
 '/pages/index/index',
 '/pages/courses/courses',
 '/pages/book-courses/book-courses',
 '/pages/tools/index',
 '/pages/user/user'
 ];
 if (tabPages.includes(url)) {
 wx.switchTab({ url });
 } else {
 wx.navigateTo({ url });
 }
 }
});
