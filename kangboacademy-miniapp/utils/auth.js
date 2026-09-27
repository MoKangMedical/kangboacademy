// ═══════════════════════════════════════════
//  微信登录
// ═══════════════════════════════════════════

/**
 * 检查登录状态
 */
function checkLogin() {
 return new Promise((resolve) => {
 const token = wx.getStorageSync('token');
 const userInfo = wx.getStorageSync('userInfo');
 if (token && userInfo) {
 resolve(userInfo);
 } else {
 resolve(null);
 }
 });
}

/**
 * 获取用户信息（需用户授权）
 */
function getUserInfo() {
 return new Promise((resolve, reject) => {
 wx.getUserProfile({
 desc: '用于完善您的学习档案',
 success: res => {
 wx.setStorageSync('userInfo', res.userInfo);
 resolve(res.userInfo);
 },
 fail: reject
 });
 });
}

/**
 * 微信登录获取 code
 */
function wxLogin() {
 return new Promise((resolve, reject) => {
 wx.login({
 success: res => {
 if (res.code) {
 resolve(res.code);
 } else {
 reject(new Error('wx.login 失败'));
 }
 },
 fail: reject
 });
 });
}

/**
 * 发送 code 到后端换取 token
 */
function code2Session(code, userInfo = null) {
 const app = getApp();
 return new Promise((resolve, reject) => {
 wx.request({
 url: `${app.globalData.apiUrl}/wx-login`,
 method: 'POST',
 data: { code, userInfo },
 success: res => {
 if (res.data && res.data.token) {
 wx.setStorageSync('token', res.data.token);
 wx.setStorageSync('userInfo', res.data.userInfo || {});
 resolve(res.data);
 } else {
 const message = res.data?.detail || res.data?.message || `登录失败(${res.statusCode || 'unknown'})`;
 reject(new Error(message));
 }
 },
 fail: err => {
 const errMsg = err && err.errMsg ? err.errMsg : 'unknown';
 console.error('[wx-login request failed]', {
 url: `${app.globalData.apiUrl}/wx-login`,
 errMsg,
 err
 });
 reject(new Error(`登录网络异常：${errMsg}`));
 }
 });
 });
}

/**
 * 完整登录流程
 */
async function fullLogin() {
 const code = await wxLogin();
 let profile = null;
 try {
 profile = await getUserInfo();
 } catch {
 // 用户拒绝头像昵称授权时，仍使用微信 openid 完成登录
 }
 const data = await code2Session(code, profile);
 return { ...data, userInfo: data.userInfo || profile || {} };
}

/**
 * 退出登录
 */
function logout() {
 wx.removeStorageSync('token');
 wx.removeStorageSync('userInfo');
 getApp().globalData.isLogin = false;
 getApp().globalData.userInfo = null;
}

module.exports = {
 checkLogin,
 getUserInfo,
 wxLogin,
 code2Session,
 fullLogin,
 logout
};
