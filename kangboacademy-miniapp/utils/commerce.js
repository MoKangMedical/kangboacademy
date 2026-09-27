function isSearchEntry(book = {}) {
 return book.channel === 'jd_search' || book.source === 'jd_search' ||
 book.purchaseEntryType === 'search' || book.entryType === 'search';
}

function safeHttps(value) {
 return typeof value === 'string' && /^https:\/\/[a-z0-9.-]+(?::443)?(?:[/?#][^\s\\]*)?$/i.test(value) &&
 !/[\u0000-\u0020\u007f]/.test(value);
}

function hasPurchaseEntry(book = {}) {
 return !isSearchEntry(book) && book.purchaseEntryReady === true &&
 book.action && book.action.canBuy === true && validateAction(book.action) ? true : false;
}

function summarize(books) {
 const total = books.length;
 const purchaseEntryBooks = books.filter(hasPurchaseEntry).length;
 const directCommissionBooks = books.filter(b => hasPurchaseEntry(b) && b.commissionReady === true).length;
 const searches = books.filter(isSearchEntry).length;
 return { total, linked: purchaseEntryBooks + searches, searches, purchaseEntryBooks,
 directCommissionBooks, purchaseEntryReady: total > 0 && purchaseEntryBooks === total,
 directCommissionReady: total > 0 && directCommissionBooks === total,
 modeText: `${purchaseEntryBooks}/${total} 商品入口 · ${searches} 本仅支持书名搜索` };
}

function validateAction(action = {}) {
 if (action.type === 'mini_program') {
 return /^wx[a-f0-9]{16}$/i.test(action.appId || '') &&
 typeof action.path === 'string' && /^\/?pages\/[^\s\\<>]+$/.test(action.path) &&
 !action.path.split('?')[0].split('/').includes('..');
 }
 if (action.type === 'clipboard' || action.type === 'web_view') return safeHttps(action.url);
 // Generic businessType strings do not establish a supported shop integration.
 return false;
}

module.exports = { isSearchEntry, safeHttps, hasPurchaseEntry, summarize, validateAction };
