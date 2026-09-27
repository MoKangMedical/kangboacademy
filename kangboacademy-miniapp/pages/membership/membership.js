const api = require('../../utils/api');
const { fullLogin } = require('../../utils/auth');

Page({
 data: {
 loading: true,
 paying: false,
 scope: '',
 plans: [],
 freePlan: null,
 payment: null,
 revenueModes: [],
 purchaseLoading: false,
 purchasesLoaded: false,
 purchaseError: '',
 purchasedBooks: [],
 purchaseSummary: null
 },

 onLoad(options) {
 this.setData({ scope: options.scope || '' });
 this.loadPlans();
 if (wx.getStorageSync('token')) {
 this.loadPurchasedBooks(false);
 }
 },

 async loadPlans() {
 this.setData({ loading: true });
 try {
 const res = await api.getMembershipPlans();
 const scope = this.data.scope;
 const plans = (res.plans || []).map(plan => ({
 ...plan,
 recommended: plan.scope === scope || (!scope && plan.highlight),
 priceLabel: `¥${plan.price}/年`,
 scopeLabel: plan.scope === 'core' ? '主干课程' : (plan.scope === 'books' ? '书目课程' : '全库权益')
 }));
 this.setData({
 plans,
 freePlan: res.free || null,
 payment: res.payment || null,
 revenueModes: res.revenueModes || [],
 loading: false
 });
 } catch (err) {
 this.setData({ loading: false });
 wx.showToast({ title: err.message || '套餐加载失败', icon: 'none' });
 }
 },

 async ensureLogin() {
 if (wx.getStorageSync('token')) return;
 const data = await fullLogin();
 const app = getApp();
 app.globalData.userInfo = data.userInfo;
 app.globalData.isLogin = true;
 },

 async buyPlan(e) {
 const planId = e.currentTarget.dataset.plan;
 if (!planId || this.data.paying) return;
 if (this.data.loading || !this.data.payment || this.data.payment.ready !== true) {
 wx.showModal({
 title: '订阅暂未开放',
 content: '当前不创建订单、不收取费用。你可以先学习免费主干课程和书目课程。',
 showCancel: false
 });
 return;
 }

 this.setData({ paying: true });
 wx.showLoading({ title: '创建订单...' });
 try {
 await this.ensureLogin();
 const order = await api.createPayment(planId, 'wechat');
 wx.hideLoading();

 if (order.mode === 'pending_config' || !order.payParams) {
 wx.showModal({
 title: '订单已创建',
 content: `${order.plan_name}\n订单号：${order.order_no}\n\n${order.message || '微信支付商户参数配置完成后即可拉起支付。'}`,
 showCancel: false
 });
 this.setData({ paying: false });
 return;
 }

 wx.requestPayment({
 ...order.payParams,
 success: () => this.checkOrder(order.order_no),
 fail: () => {
 wx.showToast({ title: '支付未完成', icon: 'none' });
 this.setData({ paying: false });
 }
 });
 } catch (err) {
 wx.hideLoading();
 wx.showToast({ title: err.message || '支付发起失败', icon: 'none' });
 this.setData({ paying: false });
 }
 },

 wait(ms) {
 return new Promise(resolve => setTimeout(resolve, ms));
 },

 async checkOrder(orderNo) {
 wx.showLoading({ title: '确认支付...' });
 try {
 let status = null;
 for (let attempt = 0; attempt < 5; attempt += 1) {
 if (attempt > 0) {
 await this.wait(1500);
 }
 status = await api.getPaymentStatus(orderNo);
 if (status && status.paid) {
 break;
 }
 }
 wx.hideLoading();
 if (status && status.paid) {
 wx.showModal({
 title: '订阅成功',
 content: '会员权益已开通，可以继续学习。',
 showCancel: false,
 success: () => wx.navigateBack({ delta: 1 })
 });
 } else {
 wx.showModal({
 title: '等待确认',
 content: '支付结果还在同步，请稍后在“我的”页面查看会员状态。',
 showCancel: false
 });
 }
 } catch (err) {
 wx.hideLoading();
 wx.showToast({ title: err.message || '订单查询失败', icon: 'none' });
 }
 this.setData({ paying: false });
 },

 formatPurchaseDate(value) {
 if (!value) return '';
 return String(value).replace('T', ' ').slice(0, 16);
 },

 normalizePurchasedBooks(items = [], localOnly = false) {
 return (Array.isArray(items) ? items : []).map(item => {
 const status = !localOnly && item.status === 'paid' && item.paymentVerified === true ? 'paid' : 'pending';
 const priceText = item.priceText || item.price_text || (item.price ? `¥${item.price}` : '价格待同步');
 return {
 ...item,
 bookId: item.bookId || item.book_id || item.id,
 title: item.title || item.book_title || '未命名图书',
 author: item.author || '',
 priceText,
 quantity: item.quantity || 1,
 status,
 statusLabel: status === 'paid' ? '商家付款已核验' : '访问意向，非已付款订单',
 purchasedAtText: this.formatPurchaseDate(item.purchasedAt || item.purchased_at || item.created_at)
 };
 });
 },

 localPurchaseLeads() {
 return this.normalizePurchasedBooks(wx.getStorageSync('bookPurchaseLeads') || [], true);
 },

 async showPurchasedBooks() {
 try {
 await this.ensureLogin();
 await this.loadPurchasedBooks(true);
 } catch (err) {
 wx.showToast({ title: err.message || '请先登录', icon: 'none' });
 }
 },

 async loadPurchasedBooks(showLoading = true) {
 if (this.data.purchaseLoading) return;
 this.setData({ purchaseLoading: true, purchaseError: '', purchasesLoaded: true });
 if (showLoading) wx.showLoading({ title: '加载图书明细...' });
 try {
 const res = await api.getPurchasedBooks();
 const purchasedBooks = this.normalizePurchasedBooks(res.purchases || []);
 this.setData({
 purchasedBooks,
 purchaseSummary: {
 total: purchasedBooks.length,
 paid: purchasedBooks.filter(item => item.status === 'paid').length,
 pending: purchasedBooks.filter(item => item.status !== 'paid').length
 },
 purchaseLoading: false
 });
 } catch (err) {
 const localBooks = this.localPurchaseLeads();
 this.setData({
 purchasedBooks: localBooks,
 purchaseSummary: {
 total: localBooks.length,
 paid: localBooks.filter(item => item.status === 'paid').length,
 pending: localBooks.filter(item => item.status !== 'paid').length
 },
 purchaseError: localBooks.length ? '服务器明细暂不可用，已显示本机待确认记录。' : (err.message || '图书明细加载失败'),
 purchaseLoading: false
 });
 }
 if (showLoading) wx.hideLoading();
 },

 goBooks() {
 wx.navigateTo({ url: '/pages/books/books' });
 },

 startFreeLesson(e) {
 const isBook = e.currentTarget.dataset.scope === 'books';
 const ids = this.data.freePlan && this.data.freePlan[isBook ? 'bookCourses' : 'courses'];
 const id = Array.isArray(ids) && ids.find(value => Number.isInteger(value) && value > 0 && value <= (isBook ? 500 : 65));
 if (!id) {
 wx.showToast({ title: '免费课程暂不可用，请稍后重试', icon: 'none' });
 return;
 }
 wx.navigateTo({
 url: `/pages/course-detail/course-detail?lesson=${isBook ? 'book' : 'lesson'}${id}.html`
 });
 }
});
