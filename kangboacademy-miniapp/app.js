// ═══════════════════════════════════════════
//  康波研究院 · 微信小程序
//  App 入口
// ═══════════════════════════════════════════

const API = require('./utils/api');
const { checkLogin, getUserInfo } = require('./utils/auth');

App({
 globalData: {
 userInfo: null,
 isLogin: false,
 baseUrl: 'https://kangboacademy.cn',
 apiUrl: 'https://kangboacademy.cn/api'
 },

 onLaunch() {
 // 先把微信生态传播跑起来，支付和直播能力可以后续补齐。
 if (wx.showShareMenu) {
 wx.showShareMenu({
 withShareTicket: true,
 menus: ['shareAppMessage', 'shareTimeline']
 });
 }

 // 检查登录状态
 checkLogin().then(userInfo => {
 if (userInfo) {
 this.globalData.userInfo = userInfo;
 this.globalData.isLogin = true;
 }
 }).catch(() => {
 // 未登录，静默处理
 });

 // 获取系统信息
 this.initSystemInfo();
 },

 initSystemInfo() {
 if (wx.getWindowInfo && wx.getDeviceInfo) {
 const windowInfo = wx.getWindowInfo();
 const deviceInfo = wx.getDeviceInfo();
 const systemInfo = { ...windowInfo, ...deviceInfo };
 this.globalData.systemInfo = systemInfo;
 this.globalData.isIOS = deviceInfo.platform === 'ios';
 this.globalData.statusBarHeight = windowInfo.statusBarHeight;
 this.globalData.navBarHeight = deviceInfo.platform === 'ios' ? 44 : 48;
 return;
 }

 wx.getSystemInfo({
 success: res => {
 this.globalData.systemInfo = res;
 this.globalData.isIOS = res.platform === 'ios';
 this.globalData.statusBarHeight = res.statusBarHeight;
 this.globalData.navBarHeight = res.platform === 'ios' ? 44 : 48;
 }
 });
 },

 // 全局登录方法
 doLogin() {
 return new Promise((resolve, reject) => {
 wx.login({
 success: res => {
 if (res.code) {
 wx.request({
 url: `${this.globalData.apiUrl}/wx-login`,
 method: 'POST',
 data: { code: res.code },
 success: resp => {
 if (resp.data && resp.data.token) {
 wx.setStorageSync('token', resp.data.token);
 wx.setStorageSync('userInfo', resp.data.userInfo);
 this.globalData.userInfo = resp.data.userInfo;
 this.globalData.isLogin = true;
 resolve(resp.data.userInfo);
 } else {
 const message = resp.data?.detail || resp.data?.message || `登录失败(${resp.statusCode || 'unknown'})`;
 reject(new Error(message));
 }
 },
 fail: err => {
 const errMsg = err && err.errMsg ? err.errMsg : 'unknown';
 console.error('[app wx-login request failed]', {
 url: `${this.globalData.apiUrl}/wx-login`,
 errMsg,
 err
 });
 reject(new Error(`登录网络异常：${errMsg}`));
 }
 });
 } else {
 reject(new Error('wx.login 失败'));
 }
 },
 fail: reject
 });
 });
 }
});
