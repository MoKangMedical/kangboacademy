const api = require('../../utils/api');
const commerce = require('../../utils/commerce');
const { BOOK_LABELS } = require('../../utils/catalog');

function normalizeBooks(rows) {
 const seen = new Set();
 return rows.map(book => {
 const id = Number(book.id);
 if (!Number.isInteger(id) || id < 1 || !book.title || seen.has(id)) throw new Error('书目身份重复或缺失');
 seen.add(id);
 const search = commerce.isSearchEntry(book);
 const ready = commerce.hasPurchaseEntry(book);
 return { ...book, id, purchaseEntryReady: ready,
 commissionReady: ready && book.commissionReady === true,
 priceText: '价格以商家页面为准',
 channelText: search ? '书名搜索' : (book.channelName || '合作商家'),
 entryText: search ? '书名搜索' : (ready ? '商品入口' : '待接入'),
 entryClass: ready ? 'ready' : 'pending',
 buyText: search ? '查找图书' : (ready ? '查看商品' : '接入说明'),
 buyHint: search ? '未绑定具体商品，不代表已授权销售' :
 (ready ? '由商家收款、发货与售后，本站不代收书款' : '尚未取得合作商商品资料，不创建订单、不收款') };
 });
}

Page({
 data: {
 activeCat: 'all', keyword: '', books: [], filteredBooks: [],
 categories: Object.keys(BOOK_LABELS).map(key => ({ key, label: BOOK_LABELS[key] })),
 shopConfig: null, shopSummary: commerce.summarize([]), loading: false, opening: false, error: ''
 },
 onLoad() { this.loadShopBooks(); },
 onShareAppMessage() { return { title: '康波研究院：课程配套阅读书单', path: '/pages/books/books' }; },
 onShareTimeline() { return { title: '康波研究院：课程配套阅读书单' }; },
 async loadShopBooks() {
 const requestId = (this._requestId || 0) + 1;
 this._requestId = requestId;
 this.setData({ loading: true, error: '' });
 try {
 const response = await api.getShopBooks(500);
 if (!Array.isArray(response.books) || !response.books.length) throw new Error('图书目录暂未提供');
 if (Number.isInteger(response.total) && response.total !== response.books.length) throw new Error('图书目录不完整');
 const books = normalizeBooks(response.books);
 if (this._requestId !== requestId) return;
 this.setData({ books, filteredBooks: books, shopConfig: response.shop || null,
 shopSummary: commerce.summarize(books), loading: false });
 this.applyFilters();
 } catch (error) {
 if (this._requestId !== requestId) return;
 this.setData({ books: [], filteredBooks: [], shopConfig: null,
 shopSummary: commerce.summarize([]), loading: false, error: error.message || '加载失败' });
 }
 },
 normalizeShopSummary(shop, books) { return commerce.summarize(books); },
 filterCat(e) { this.setData({ activeCat: e.currentTarget.dataset.cat }); this.applyFilters(); },
 onSearchInput(e) { this.setData({ keyword: e.detail.value || '' }); this.applyFilters(); },
 applyFilters() {
 const keyword = this.data.keyword.trim().toLowerCase();
 this.setData({ filteredBooks: this.data.books.filter(book =>
 (this.data.activeCat === 'all' || (book.category || book.cat) === this.data.activeCat) &&
 (!keyword || [book.id, book.title, book.author, BOOK_LABELS[book.category || book.cat]].join(' ').toLowerCase().includes(keyword))) });
 },
 openShop() { this.showCommerceHelp(); },
 showCommerceHelp() {
 wx.showModal({ title: '购书与售后说明',
 content: '图书商品由合作书商提供。没有商品授权时仅提供书名检索，不创建订单、不收款。商品接入后，请在商家页面核对ISBN、版本、价格与售后，再决定是否购买。订单、物流、发票和退款请在实际成交商家的订单页处理。课程订阅与纸质图书购买分别管理。',
 showCancel: false });
 },
 buyBook(e) {
 const selected = e.currentTarget.dataset.book;
 const book = this.data.books.find(row => row.id === Number(selected && selected.id));
 if (!book || this.data.opening) return;
 if (!book.purchaseEntryReady && !commerce.isSearchEntry(book)) { this.showCommerceHelp(); return; }
 wx.showModal({ title: book.title,
 content: [book.buyHint, book.merchantName ? `商家：${book.merchantName}` : '',
 typeof book.afterSales === 'string' ? `售后：${book.afterSales}` :
 (book.afterSales ? `售后：${[book.afterSales.description, book.afterSales.contact].filter(Boolean).join('；')}` : ''),
 '跳转和复制链接不代表购买成功。'].filter(Boolean).join('\n'),
 confirmText: book.buyText,
 success: result => { if (result.confirm) this.openShopTarget(book); } });
 },
 async openShopTarget(book) {
 if (!book || !book.id || this.data.opening) return;
 this.setData({ opening: true });
 wx.showLoading({ title: '核实商品入口' });
 try {
 const response = await api.resolveShopBook(book.id, 'miniapp');
 wx.hideLoading();
 const action = response.action;
 const search = action && (action.entryKind === 'search' || commerce.isSearchEntry(action));
 if (!action || !commerce.validateAction(action) || (!search && action.canBuy !== true)) {
 wx.showModal({ title: '入口暂不可用', content: '尚未提供可核验的商品链接或当前小程序支持的跳转方式，请稍后重试。不会改跳其他商品。', showCancel: false });
 return;
 }
 this.openResolvedAction(action, { ...book, channel: search ? 'jd_search' : book.channel });
 } catch (error) {
 wx.hideLoading();
 wx.showToast({ title: '入口核实失败，请稍后重试', icon: 'none' });
 } finally { this.setData({ opening: false }); }
 },
 openResolvedAction(action, book) {
 if (!commerce.validateAction(action)) return;
 const success = () => this.rememberInterest(book);
 if (action.type === 'mini_program') {
 wx.navigateToMiniProgram({ appId: action.appId, path: action.path, envVersion: 'release', success,
 fail: () => wx.showToast({ title: '未打开商品，未产生订单', icon: 'none' }) });
 } else {
 wx.setClipboardData({ data: action.url, success: () => {
 success();
 wx.showModal({ title: commerce.isSearchEntry(book) ? '搜索链接已复制' : '商品链接已复制',
 content: '请打开链接核对商品。本站仅记录访问意向，不记录为付款；如成交，订单与售后请在商家平台查看。', showCancel: false });
 }, fail: () => wx.showToast({ title: '复制失败，请重试', icon: 'none' }) });
 }
 },
 rememberInterest(book) {
 const stored = wx.getStorageSync('bookPurchaseLeads');
 const records = Array.isArray(stored) ? stored : [];
 const row = { bookId: book.id, title: book.title, author: book.author || '', status: 'pending',
 statusLabel: '访问意向，非订单', source: 'miniapp', created_at: new Date().toISOString() };
 wx.setStorageSync('bookPurchaseLeads', [row, ...records.filter(item => Number(item.bookId) !== book.id)].slice(0, 50));
 }
});
