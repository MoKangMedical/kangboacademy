// ═══════════════════════════════════════════
//  API 工具 · 封装 wx.request
// ═══════════════════════════════════════════

const BASE_URL = 'https://kangboacademy.cn';
const API_URL = BASE_URL + '/api';
const { confirmAIProcessing } = require('./ai-consent');

/**
 * 通用请求
 */
function request(url, options = {}) {
 if (typeof url !== 'string' || (url.startsWith('http') && !url.startsWith(API_URL + '/')) ||
 (!url.startsWith('http') && (!url.startsWith('/') || url.startsWith('//')))) {
 return Promise.reject(new Error('不允许向非本站接口发送账户凭据'));
 }
 const { method = 'GET', data = {} } = options;
 const header = { ...(options.header || {}) };
 const token = wx.getStorageSync('token');

 if (token) {
 header['Authorization'] = `Bearer ${token}`;
 }

 return new Promise((resolve, reject) => {
 wx.request({
 url: url.startsWith('http') ? url : API_URL + url,
 method,
 data,
 timeout: Number.isInteger(options.timeout) && options.timeout >= 1000 && options.timeout <= 60000
  ? options.timeout : 15000,
 header: {
 'Content-Type': 'application/json',
 ...header
 },
 success(res) {
 if (res.statusCode >= 200 && res.statusCode < 300) {
 resolve(res.data);
 } else if (res.statusCode === 401) {
 // A response from an older session must not log out a newer login.
 if (token && wx.getStorageSync('token') === token) {
 wx.removeStorageSync('token');
 wx.removeStorageSync('userInfo');
 const app = typeof getApp === 'function' ? getApp() : null;
 if (app && app.globalData) {
 app.globalData.isLogin = false;
 app.globalData.userInfo = null;
 }
 }
 reject(new Error('登录已过期'));
 } else {
 reject(new Error(res.data?.detail || res.data?.message || `请求失败(${res.statusCode})`));
 }
 },
 fail(err) {
 const errMsg = err && err.errMsg ? err.errMsg : 'unknown';
 console.error('[API request failed]', {
 url: url.startsWith('http') ? url : API_URL + url,
 method,
 errMsg,
 err
 });
 reject(new Error(`网络异常：${errMsg}`));
 }
 });
 });
}

/**
 * 获取课程列表
 */
function getCourses() {
 return request('/courses');
}

/**
 * 获取课程详情
 */
function getCourseDetail(id) {
 return request(`/courses/${id}`);
}

/**
 * 获取课程 Markdown 内容
 */
function getCourseContent(file) {
 return request(`/course-content/${file}`);
}

/**
 * 获取书目课程内容
 */
function getBookCourseContent(file) {
 return request(`/book-course-content/${file}`);
}

/**
 * 获取书目课程列表
 */
function getBookCourses() {
 return request('/book-courses');
}

/**
 * 搜索
 */
function search(keyword) {
 return request('/search', { method: 'POST', data: { keyword } });
}

/**
 * 获取知识图谱数据
 */
function getKnowledgeGraph() {
 return request('/knowledge-graph');
}

/**
 * 获取用户学习记录
 */
function getProgress() {
 return request('/progress');
}

/**
 * 保存学习进度
 */
function saveProgress(data) {
 return request('/progress', { method: 'POST', data });
}

/**
 * 获取推荐
 */
function getRecommendations() {
 return request('/recommendations');
}

/**
 * 获取主干课程和书目课程连续播放清单
 */
function getAudioPlaylist(scope = 'all') {
 return request(`/audio-playlist?scope=${scope}`);
}

/**
 * 获取微信小店配置
 */
function getShopConfig() {
 return request('/shop/config');
}

/**
 * 获取书店图书
 */
function getShopBooks(limit = 24) {
 return request(`/shop/books?limit=${limit}`);
}

/**
 * 解析图书销售渠道，返回小程序跳转、交易组件或联盟链接动作
 */
function resolveShopBook(bookId, source = 'miniapp') {
 return request('/shop/resolve', {
 method: 'POST',
 data: { book_id: bookId, source }
 });
}

/**
 * 记录图书购买/跳转点击，用于分成归因
 */
function recordShopClick(bookId, target = '', source = 'miniapp') {
 return request('/shop/click', {
 method: 'POST',
 data: { book_id: bookId, target, source }
 });
}

/**
 * 获取当前用户的图书购买明细
 */
function getPurchasedBooks() {
 return request('/shop/purchases');
}

/**
 * 获取当前用户收藏课程
 */
function getBookmarks() {
 return request('/bookmarks');
}

/**
 * 收藏/取消收藏课程
 */
function toggleBookmark(course) {
 return request('/bookmarks', {
 method: 'POST',
 data: course
 });
}

/**
 * 获取学习笔记：课后反思、Agent反馈和AI建议
 */
function getStudyNotes(limit = 100) {
 return request(`/study-notes?limit=${limit}`);
}

/**
 * 获取会员套餐
 */
function getMembershipPlans() {
 return request('/membership/plans');
}

/**
 * 创建课程订阅订单
 */
function createPayment(plan, method = 'wechat') {
 return request('/payment/create', {
 method: 'POST',
 data: { plan, method }
 });
}

/**
 * 查询订单状态
 */
function getPaymentStatus(orderNo) {
 return request(`/payment/status/${orderNo}`);
}

/**
 * 更新用户资料
 */
function updateProfile(data) {
 return request('/user/profile', {
 method: 'PUT',
 data
 });
}

/**
 * 绑定手机号：可传微信 getPhoneNumber code，或手动填写 phone
 */
function bindWechatPhone(data) {
 return request('/wx-phone', {
 method: 'POST',
 data
 });
}

/**
 * 获取课程互动练习
 */
function getPractice(lesson) {
 return request(`/practice/${lesson}`);
}

/**
 * 提交课程互动练习
 */
async function submitPractice(lesson, answers, reflection = '') {
 const { practiceSubmissionPayload, withSubmissionId } = require('./practice-submission');
 const payload = practiceSubmissionPayload(lesson, answers, reflection);
 await confirmAIProcessing('practice');
 return request('/practice/submit', {
 method: 'POST',
 timeout: 40000,
 data: withSubmissionId(payload)
 });
}

/**
 * 获取每日精进记录
 */
function getDailyRefinement() {
 return request('/daily-refinement');
}

/**
 * 获取徽章体系和已获得徽章
 */
function getBadges() {
 return request('/badges');
}

/**
 * 获取 Agent 服务状态
 */
function getAgentConfig() {
 return request('/agent/config');
}

/**
 * 调用康波 Agent 生成建议
 */
async function askAgent(data) {
 await confirmAIProcessing('agent');
 return request('/agent/chat', {
 method: 'POST',
 data
 });
}

module.exports = {
 BASE_URL,
 API_URL,
 request,
 getCourses,
 getCourseDetail,
 getCourseContent,
 getBookCourseContent,
 getBookCourses,
 search,
 getKnowledgeGraph,
 getProgress,
 saveProgress,
 getRecommendations,
 getAudioPlaylist,
 getShopConfig,
 getShopBooks,
 resolveShopBook,
 recordShopClick,
 getPurchasedBooks,
 getBookmarks,
 toggleBookmark,
 getStudyNotes,
 getMembershipPlans,
 createPayment,
 getPaymentStatus,
 updateProfile,
 bindWechatPhone,
 getPractice,
 submitPractice,
 getDailyRefinement,
 getBadges,
 getAgentConfig,
 askAgent
};
