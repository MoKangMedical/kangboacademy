const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'server_patch/frontend/book-shop.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const manifestScript = fs.readFileSync(path.join(root, 'server_patch/frontend/content-manifest.js'), 'utf8');
const sample = {id: 1, title: 'Book', category: 'period', purchaseEntryReady: true,
  entryType: 'product', externalUrl: 'https://item.jd.com/123.html'};

async function page(responses = [{books: []}], manifest = true) {
  const nodes = Object.fromEntries(['q','category','status','stats','grid','empty','retry'].map(id =>
    [id, {value: '', innerHTML: '', textContent: '', hidden: false, listeners: {},
      addEventListener(type, fn) { this.listeners[type] = fn; }}]));
  const requests = [];
  const context = vm.createContext({window: {}, URL, AbortController, setTimeout, clearTimeout,
    location: {hostname: 'kangboacademy.cn'}, document: {getElementById: id => nodes[id]},
    fetch: async (url, options) => {
      requests.push({url, options});
      const next = responses.shift();
      if(next instanceof Error) throw next;
      return {ok: next?.ok !== false, json: async () => {
        if(next?.badJson) throw new SyntaxError('bad JSON');
        return next;
      }};
    }});
  if(manifest) vm.runInContext(manifestScript, context);
  vm.runInContext(script, context);
  await new Promise(resolve => setImmediate(resolve));
  return {nodes, requests, context, run: source => vm.runInContext(source, context)};
}

test('shared manifest is the only category source, including order', async () => {
  const p = await page();
  const m = p.context.window.KANGBO_CONTENT;
  const values = [...p.nodes.category.innerHTML.matchAll(/value="([^"]+)"/g)].map(x => x[1]);
  assert.deepEqual(values, Array.from(m.categoryOrder));
  for(const name of Object.values(m.categories)) assert.ok(p.nodes.category.innerHTML.includes(name));
  assert.match(html, /<script src="content-manifest.js"><\/script>/);
  assert.doesNotMatch(script, /period\s*:/);
});

test('legacy jd_search wins over readiness, commission and conflicting product type', async () => {
  const p = await page();
  for(const flags of [
    {channel: 'jd_search'}, {source: 'jd_search'}, {purchaseEntryType: 'search'},
    {externalUrl: 'https://search.jd.com/Search?keyword=book'},
    {externalUrl: 'https://www.example.com/search?q=book'}
  ]) {
    p.context.book = {...sample, commissionReady: true, canBuy: true, ...flags};
    assert.equal(p.run('entry(book).type'), 'search');
  }
});

test('entry types require strict readiness and safe numeric IDs', async () => {
  const p = await page();
  for(const type of ['configured_product','product','affiliate','wechat_shop','direct']) {
    p.context.book = {...sample, entryType: undefined, purchaseEntryType: type};
    assert.equal(p.run('entry(book).type'), 'product');
  }
  for(const patch of [
    {purchaseEntryReady: false}, {purchaseEntryReady: 'true'}, {purchaseEntryReady: undefined, canBuy: true},
    {entryType: undefined, commissionReady: true}, {entryType: 'unknown'},
    ...['0', -1, '1/../2', '1e2', '1" onclick="x', true, 1.5, '9007199254740992'].map(id => ({id}))
  ]) {
    p.context.book = {...sample, ...patch};
    assert.equal(p.run('entry(book).type'), 'none', JSON.stringify(patch));
  }
});

test('unsafe and internal URLs cannot create an outbound link', async () => {
  const p = await page();
  for(const url of ['javascript:alert(1)', 'data:text/html,x', '//item.jd.com/1',
    'http://item.jd.com/1', 'https://user:pass@item.jd.com/1', 'https://item.jd.com\\@evil.com',
    'https://item.jd.com/\n1', 'https://kangboacademy.cn/api/shop/redirect/1',
    'https://other.example/api/shop/redirect/1', 'https://localhost/a', 'https://item.jd.com:444/1']) {
    p.context.book = {...sample, externalUrl: url};
    assert.equal(p.run('entry(book).type'), 'none', url);
  }
});

test('separate counts, filters, buttons; escaped metadata; no fake price, stock or attribution', async () => {
  const p = await page([{books: [
    {...sample, title: '<img src=x onerror=alert(1)>', merchant: {name: '<Seller>'}, afterSales: 'Call <support>', priceText: 'FAKE_PRICE', stock: 'FAKE_STOCK'},
    {...sample, id: 2, channel: 'jd_search', commissionReady: true},
    {...sample, id: 3, purchaseEntryReady: false},
    {...sample, id: 4, externalUrl: 'javascript:alert(1)'}
  ]}]);
  assert.match(p.nodes.stats.innerHTML, /具体商品入口<\/small><strong>1/);
  assert.match(p.nodes.stats.innerHTML, /书商搜索<\/small><strong>1/);
  assert.match(p.nodes.grid.innerHTML, /查看书商商品/);
  assert.match(p.nodes.grid.innerHTML, /去书商搜索/);
  assert.match(p.nodes.grid.innerHTML, /&lt;img/);
  assert.match(p.nodes.grid.innerHTML, /&lt;Seller&gt;/);
  assert.match(p.nodes.grid.innerHTML, /Call &lt;support&gt;/);
  assert.match(p.nodes.grid.innerHTML, /未提供/);
  assert.match(p.nodes.grid.innerHTML, /rel="noopener noreferrer nofollow"/);
  assert.doesNotMatch(p.nodes.grid.innerHTML, /<img|FAKE_PRICE|FAKE_STOCK|href="javascript:|可直接分成|真实购买入口/);
  for(const [status, count] of [['product',1],['search',1],['none',2]]) {
    p.nodes.status.value = status;
    p.nodes.status.listeners.input();
    assert.equal(p.run('state.filtered.length'), count);
  }
  p.nodes.q.value = 'no match';
  p.nodes.q.listeners.input();
  assert.equal(p.nodes.empty.hidden, false);
  assert.match(p.nodes.empty.textContent, /调整筛选/);
  assert.deepEqual(p.requests.map(r => r.url), ['/api/shop/books?limit=500']);
  assert.doesNotMatch(script, /sendBeacon|\/api\/launch|\/api\/shop\/(redirect|click|resolve)|method:\s*['"]POST/);
  assert.match(html, /学习课程与书商交易分离/);
  assert.match(html, /不代表购书、订单、支付或分成/);
});

test('network, HTTP, malformed JSON and schema failures allow successful retry', async () => {
  for(const failure of [new Error('offline'), {ok:false}, {badJson:true}, {}, {books:[null]}]) {
    const p = await page([failure, {books:[sample]}]);
    assert.match(p.nodes.empty.textContent, /加载失败/);
    assert.equal(p.nodes.retry.hidden, false);
    await p.nodes.retry.listeners.click();
    assert.equal(p.nodes.retry.hidden, true);
    assert.equal(p.nodes.empty.hidden, true);
    assert.match(p.nodes.grid.innerHTML, /查看书商商品/);
  }
});

test('empty catalog and missing manifest fail without manufactured data', async () => {
  const p = await page();
  assert.match(p.nodes.empty.textContent, /暂无书目/);
  assert.equal(p.nodes.retry.hidden, false);
  const missing = await page([{books:[sample]}], false);
  assert.match(missing.nodes.empty.textContent, /加载失败/);
  assert.equal(missing.requests.length, 0);
  assert.equal(missing.nodes.grid.innerHTML, '');
});

test('search remains visible with purchaseEntryReady false, but products do not', async () => {
  const searches = [
    {entryType:'search'}, {entryType:undefined, purchaseEntryType:'search'},
    {channel:'jd_search'}, {source:'jd_search'},
    {externalUrl:'https://search.jd.com/Search?keyword=book'}
  ].map((flags, i) => ({...sample, id:i + 1, ...flags, purchaseEntryReady:false}));
  const p = await page([{books:[...searches, {...sample, id:6, purchaseEntryReady:false}]}]);
  assert.match(p.nodes.stats.innerHTML, /具体商品入口<\/small><strong>0/);
  assert.match(p.nodes.stats.innerHTML, /书商搜索<\/small><strong>5/);
  p.nodes.status.value = 'search';
  p.nodes.status.listeners.input();
  assert.equal(p.run('state.filtered.length'), 5);
  assert.equal((p.nodes.grid.innerHTML.match(/>去书商搜索<\/a>/g) || []).length, 5);
  for(const url of ['javascript:alert(1)', 'http://search.jd.com/Search']) {
    p.context.book = {...searches[0], externalUrl:url};
    assert.equal(p.run('entry(book).type'), 'none');
  }
});

test('merchantName is preferred and escaped; legacy merchant is retained', async () => {
  const p = await page([{books:[
    {...sample, merchantName:'<Current "Seller">', merchant:'Legacy ignored'},
    {...sample, id:2, merchant:'Legacy <Seller>'}
  ]}]);
  assert.match(p.nodes.grid.innerHTML, /&lt;Current &quot;Seller&quot;&gt;/);
  assert.match(p.nodes.grid.innerHTML, /Legacy &lt;Seller&gt;/);
  assert.doesNotMatch(p.nodes.grid.innerHTML, /Legacy ignored|<Current/);
  assert.doesNotMatch(html, /目前尚无合作商授权/);
  assert.match(html, /仅标记商品入口/);
  assert.match(html, /未接入商品时/);
});

test('duplicate, invalid, truncated and oversized catalogs fail closed and can retry', async () => {
  const invalidCatalogs = [
    {books:[sample, {...sample, id:'1'}], total:2},
    {books:[{...sample, id:'1" onclick="bad'}]},
    {books:[sample], total:500},
    {books:[sample], total:0},
    {books:[sample], total:'1'},
    {books:[sample], truncated:true},
    {books:[sample], hasMore:true},
    {books:[sample], nextCursor:'next-page'},
    {books:Array.from({length:501}, (_, i) => ({...sample, id:i+1})), total:501}
  ];
  for(const catalog of invalidCatalogs) {
    const p = await page([catalog, {books:[sample], total:1}]);
    assert.match(p.nodes.empty.textContent, /加载失败.*数据不完整/);
    assert.equal(p.nodes.grid.innerHTML, '');
    assert.equal(p.run('state.books.length'), 0);
    assert.equal(p.nodes.retry.hidden, false);
    await p.nodes.retry.listeners.click();
    assert.match(p.nodes.grid.innerHTML, /查看书商商品/);
    assert.equal(p.nodes.empty.hidden, true);
  }
  assert.doesNotMatch(script, /\.slice\(/);
});

test('complete 500-row catalog is rendered without truncation', async () => {
  const p = await page([{books:Array.from({length:500}, (_, i) => ({...sample, id:i+1})), total:500}]);
  assert.equal(p.run('state.books.length'), 500);
  assert.equal((p.nodes.grid.innerHTML.match(/<article /g) || []).length, 500);
  assert.equal(p.nodes.empty.hidden, true);
});

test('mini-program-only targets explain the limitation without manufacturing URLs', async () => {
  for(const fields of [
    {appId:'wx0123456789abcdef', path:'pages/product/detail?id=123'},
    {miniProgramAppId:'wx0123456789abcdef', shopPath:'pages/product/detail?id=123'}
  ]) {
    const p = await page([{books:[{...sample, externalUrl:'', ...fields}]}]);
    assert.match(p.nodes.grid.innerHTML, /仅微信小程序内可打开/);
    assert.match(p.nodes.grid.innerHTML, /disabled>仅微信小程序内可打开/);
    assert.doesNotMatch(p.nodes.grid.innerHTML, /target="_blank"|href="https:|href="pages\/|href="weixin:/);
    assert.match(p.nodes.stats.innerHTML, /具体商品入口<\/small><strong>0/);
    p.nodes.status.value = 'miniProgram';
    p.nodes.status.listeners.input();
    assert.equal(p.run('state.filtered.length'), 1);
    p.context.book = {...sample, externalUrl:'', ...fields, appId:'bad', miniProgramAppId:'bad'};
    assert.equal(p.run('entry(book).type'), 'none');
  }
});

// Mirrors get_shop_books and public_merchant_info in server_patch/backend/main.py.
// Deliberately no entryType: the API exposes purchaseEntryType = action.entryKind.
function backendBook(id, kind, ready) {
  const url = kind === 'search' ? 'https://search.jd.com/Search?keyword=book' :
    kind === 'unavailable' ? '' : 'https://item.jd.com/123.html';
  const canBuy = kind === 'configured_product' && ready === true;
  const action = {type: url ? 'clipboard' : 'none', channel: 'jd_union', url,
    target:url, entryKind:kind, canOpen:!!url, canBuy};
  return {
    id, title:'Imported book', author:'Author', price:canBuy ? '68.00' : '',
    priceText:canBuy ? '68.00' : '价格以渠道页面为准',
    priceEvidence:canBuy ? 'configured' : 'unknown', cat:'period', category:'period',
    shopProductId:'123', shopPath:'', affiliateUrl:url, externalUrl:url,
    commissionRate:'', settlementMode:'cps', commissionReady:false,
    purchaseEntryReady:ready, purchaseEntryType:kind,
    channel:'jd_union', channelName:'JD', source:'jd_union',
    openType:action.type, canBuy, canOpen:action.canOpen, entryKind:kind, action,
    paymentEvidence:'none', purchaseStatus:canBuy ? 'ready' :
      kind === 'configured_product' ? 'authorization_or_service_missing' : kind,
    merchantName:'Contract <Seller>',
    afterSales:{contact:'service@example.com', description:'Return <policy>',
      policyUrl:'https://merchant.example/policy?a=1&b=2'},
    authorizationStatus:canBuy ? 'confirmed' : 'unverified'
  };
}

test('backend shop/books payload recognizes configured_product without entryType', async () => {
  const books = [backendBook(1, 'configured_product', true),
    backendBook(2, 'configured_product', false), backendBook(3, 'search', false),
    backendBook(4, 'store', false), backendBook(5, 'unavailable', false)];
  const p = await page([{books, total:books.length, shop:{}}]);
  assert.deepEqual(Array.from(p.run('state.books.map(b => entry(b).type)')),
    ['product','none','search','none','none']);
  assert.match(p.nodes.stats.innerHTML, /具体商品入口<\/small><strong>1/);
  assert.match(p.nodes.stats.innerHTML, /书商搜索<\/small><strong>1/);
  p.nodes.status.value = 'product';
  p.nodes.status.listeners.input();
  assert.equal(p.run('state.filtered.length'), 1);
  assert.match(p.nodes.grid.innerHTML, /href="https:\/\/item.jd.com\/123.html"/);
  assert.match(p.nodes.grid.innerHTML, /查看书商商品/);
  assert.match(p.nodes.grid.innerHTML, /Contract &lt;Seller&gt;/);
  assert.match(p.nodes.grid.innerHTML, /contact：service@example.com/);
  assert.match(p.nodes.grid.innerHTML, /description：Return &lt;policy&gt;/);
  assert.match(p.nodes.grid.innerHTML, /policyUrl：https:\/\/merchant.example\/policy\?a=1&amp;b=2/);
  assert.doesNotMatch(p.nodes.grid.innerHTML, /68\.00|>已支付<|>已成交<|可直接分成/);
  assert.match(p.nodes.grid.innerHTML, /打开链接不代表已购买或已支付/);
  assert.deepEqual(p.requests.map(r => r.url), ['/api/shop/books?limit=500']);
});

test('configured_product still requires strict readiness and a safe URL', async () => {
  const p = await page();
  for(const ready of [false, undefined, null, 'true', 1]) {
    p.context.book = backendBook(1, 'configured_product', ready);
    assert.equal(p.run('entry(book).type'), 'none');
  }
  for(const kind of ['store','unavailable']) {
    p.context.book = {...backendBook(1, kind, true), externalUrl:'https://item.jd.com/123.html'};
    assert.equal(p.run('entry(book).type'), 'none');
  }
  p.context.book = {...backendBook(1, 'configured_product', true), externalUrl:'javascript:alert(1)'};
  assert.equal(p.run('entry(book).type'), 'none');
});

test('empty backend service fields use missing-information text, never fabricate service', async () => {
  const book = {...backendBook(1, 'configured_product', true), merchantName:'',
    afterSales:{contact:'', description:'  ', policyUrl:''}};
  const p = await page([{books:[book], total:1, shop:{}}]);
  assert.match(p.nodes.grid.innerHTML, /书商信息：未提供/);
  assert.match(p.nodes.grid.innerHTML, /售后信息：未提供/);
  assert.doesNotMatch(p.nodes.grid.innerHTML, /contact：|description：|policyUrl：/);
});
