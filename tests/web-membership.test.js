'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {render, escapeHtml, mount} = require('../server_patch/frontend/membership-catalog.js');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'server_patch/frontend/membership-catalog.js'), 'utf8');
const index = fs.readFileSync(path.join(root, 'server_index.html'), 'utf8');
const pricing = index.match(/<section id="pricing"[\s\S]*?<\/section>/)[0];

// Contract fixture from get_membership_plans / plan_public, not fallback UI data.
function payload(ready = false) {
  return {
    plans: [
      {id:'core_year', name:'主干课程年卡', price:399, amountFen:39900, scope:'core', durationDays:365,
        features:['65门主干课程', '课程进度记录', '后续课程更新'], courses:[1], highlight:false},
      {id:'books_year', name:'书目课程年卡', price:299, amountFen:29900, scope:'books', durationDays:365,
        features:['500本推荐书目课程', '17波系统精读', '19类知识领域'], bookCourses:[1], highlight:false},
      {id:'bundle_year', name:'全库升级包', price:599, amountFen:59900, scope:'bundle', durationDays:365,
        features:['主干课程 + 书目课程', '升级打包优惠', '后续内容更新'], highlight:true}
    ],
    free:{id:'free', name:'免费体验', price:0, amountFen:0, scope:'free', durationDays:0,
      features:['每个主干课程阶段第一课免费', '每个书目课程波次第一本免费', '免费工具'], courses:[1], bookCourses:[1]},
    payment:{provider:'wechat', ready},
    revenueModes:[]
  };
}

function fakeHost() {
  return {innerHTML:'', attributes:{}, listeners:{},
    setAttribute(key, value) { this.attributes[key] = value; },
    addEventListener(key, fn) { this.listeners[key] = fn; }};
}

test('API contract renders exact plan names, current prices, duration and benefits', () => {
  const data = payload();
  const snapshot = JSON.stringify(data);
  const html = render(data);
  for (const plan of [data.free, ...data.plans]) {
    assert.ok(html.includes(escapeHtml(plan.name)));
    assert.ok(html.includes(`>${plan.price}<span`));
    for (const feature of plan.features) assert.ok(html.includes(escapeHtml(feature)));
  }
  assert.match(html, /元\/年/);
  assert.equal(JSON.stringify(data), snapshot);
  data.plans[0].price = 402.50;
  data.plans[0].amountFen = 40250;
  data.plans[0].durationDays = 30;
  assert.match(render(data), /402\.50<span class="unit">元\/30天/);
  assert.doesNotMatch(render(data), />399<span/);
});

test('pure renderer escapes names and features and ignores API action URLs', () => {
  const data = payload(true);
  data.plans[0].name = '<img src=x onerror="alert(1)">';
  data.plans[0].features = ['<script>alert(1)</script>', 'A & B "quoted" \'text\''];
  data.free.name = '<svg onload=alert(1)>';
  data.payment.url = 'javascript:alert(1)';
  data.plans[0].checkoutUrl = 'https://evil.example/pay';
  const html = render(data);
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(html, /A &amp; B &quot;quoted&quot; &#39;text&#39;/);
  assert.doesNotMatch(html, /<img|<svg|<script|javascript:|evil\.example/);
  assert.equal(escapeHtml('&<>"\''), '&amp;&lt;&gt;&quot;&#39;');
});

test('bad prices fail the entire catalog without a fallback price', () => {
  for (const price of [undefined, null, '', '399', '<img>', -1, NaN, Infinity, 1.001, Number.MAX_SAFE_INTEGER, 0]) {
    const data = payload();
    data.plans[0].price = price;
    const html = render(data);
    assert.match(html, /价格无效/);
    assert.match(html, /data-membership-retry/);
    assert.doesNotMatch(html, /price-amount|>399<|>299<|>599</);
  }
  const data = payload();
  data.plans[0].amountFen = 1;
  assert.match(render(data), /价格无效/);
  data.plans[0].amountFen = 39900;
  data.free.price = 99;
  assert.match(render(data), /价格无效/);
});

test('empty and malformed payloads never fabricate plans, benefits or prices', () => {
  for (const data of [null, {}, {plans:null}, {plans:[null]}, {plans:[{}]}]) {
    const html = render(data);
    assert.match(html, /重新加载套餐/);
    assert.doesNotMatch(html, /price-amount/);
  }
  const empty = render({plans:[], payment:{ready:false}});
  assert.match(empty, /暂无可用订阅套餐/);
  assert.doesNotMatch(empty, /price-amount/);
  const data = payload();
  data.plans[1].id = data.plans[0].id;
  assert.match(render(data), /数据不完整/);
  data.plans = [];
  assert.match(render(data), /免费体验/);
  assert.match(render(data), /暂无可用订阅套餐/);
});

test('readiness is strict, and even ready true never opens web payment', () => {
  for (const ready of [false, undefined, null, 'true', 1]) {
    const html = render(payload(ready));
    assert.match(html, /当前不创建订单、不收取费用/);
    assert.doesNotMatch(html, /配置就绪/);
  }
  const noPayment = payload();
  delete noPayment.payment;
  assert.match(render(noPayment), /当前不创建订单、不收取费用/);
  const html = render(payload(true));
  assert.match(html, /不代表支付链路已验证/);
  assert.match(html, /本站网页不创建订单、不收款/);
  assert.equal((html.match(/disabled>网页不收款/g) || []).length, 3);
  assert.match(html, /本页入口待核验/);
  for (const match of html.matchAll(/href="([^"]+)"/g)) assert.equal(match[1], 'courses.html');
});

test('loading, network, HTTP and JSON failures clear stale prices and retry with GET only', async () => {
  for (const failure of ['network', 'http', 'json']) {
    const host = fakeHost();
    host.innerHTML = render(payload());
    const calls = [];
    const controller = mount(host, async (url, options) => {
      calls.push({url, options});
      if (calls.length === 1 && failure === 'network') throw new Error('offline');
      return {ok: !(calls.length === 1 && failure === 'http'), json: async () => {
        if (calls.length === 1 && failure === 'json') throw new SyntaxError('JSON');
        return payload();
      }};
    });
    assert.match(host.innerHTML, /正在加载/);
    assert.doesNotMatch(host.innerHTML, /price-amount/);
    await controller.initialLoad;
    assert.match(host.innerHTML, /套餐加载失败/);
    assert.doesNotMatch(host.innerHTML, /price-amount/);
    assert.equal(host.attributes['aria-busy'], 'false');
    host.listeners.click({target:{closest: selector => selector === '[data-membership-retry]' ? {} : null}});
    await new Promise(resolve => setImmediate(resolve));
    assert.match(host.innerHTML, /主干课程年卡/);
    assert.equal(calls.length, 2);
    for (const call of calls) {
      assert.equal(call.url, '/api/membership/plans');
      assert.equal(call.options.method, 'GET');
      assert.equal(call.options.cache, 'no-store');
    }
  }
});

test('in-flight loads are deduplicated and timeout exposes a retry', async () => {
  const host = fakeHost();
  let onTimeout;
  let signal;
  let calls = 0;
  const context = vm.createContext({module:{exports:{}}, AbortController,
    setTimeout(fn) { onTimeout = fn; return 1; }, clearTimeout() {}});
  vm.runInContext(source, context);
  const controller = context.module.exports.mount(host, (url, options) => {
    calls += 1;
    signal = options.signal;
    return new Promise(() => {});
  });
  await controller.load();
  assert.equal(calls, 1);
  onTimeout();
  await controller.initialLoad;
  assert.equal(signal.aborted, true);
  assert.match(host.innerHTML, /套餐加载失败/);
  assert.match(host.innerHTML, /重新加载套餐/);
  assert.equal(host.attributes['aria-busy'], 'false');
});

test('pricing integrates the resource without fake checkout, QR, mentor benefits or hardcoded prices', () => {
  assert.match(pricing, /src="membership-catalog.js" defer/);
  assert.match(pricing, /id="membership-catalog"/);
  assert.match(pricing, /href="courses.html"/);
  assert.ok(fs.existsSync(path.join(root, 'server_patch/frontend/courses.html')));
  assert.match(pricing, /暂未提供已验证的订阅入口或二维码/);
  assert.doesNotMatch(pricing, /99|399|299|599|导师|立即购买|digitalsage|onclick|<img/);
  assert.doesNotMatch(source, /399|299|599|\/api\/payment|requestPayment|window\.open|location\.|method:\s*['"]POST/);
  assert.match(source, /\/api\/membership\/plans/);
});
