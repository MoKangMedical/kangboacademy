(function (root, factory) {
  'use strict';
  const catalog = factory();
  if (typeof module === 'object' && module.exports) module.exports = catalog;
  else {
    root.KangboMembershipCatalog = catalog;
    const host = root.document.getElementById('membership-catalog');
    if (host) catalog.mount(host, root.fetch.bind(root));
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);
  }

  function validatePlan(plan, free) {
    if (!plan || typeof plan !== 'object' || Array.isArray(plan) ||
        typeof plan.id !== 'string' || !/^[a-zA-Z0-9_-]+$/.test(plan.id) ||
        typeof plan.name !== 'string' || !plan.name.trim() ||
        !Array.isArray(plan.features) || plan.features.some(item => typeof item !== 'string' || !item.trim())) {
      throw new Error('Invalid plan');
    }
    const price = plan.price;
    const fen = Math.round(price * 100);
    if (typeof price !== 'number' || !Number.isFinite(price) || price < 0 ||
        !Number.isSafeInteger(fen) || Math.abs(price * 100 - fen) > 0.000001 ||
        (plan.amountFen !== undefined && plan.amountFen !== fen) ||
        (free && price !== 0) || (!free && price === 0) ||
        !Number.isSafeInteger(plan.durationDays) || plan.durationDays < 0 || (!free && plan.durationDays === 0)) {
      throw new Error('Invalid price or duration');
    }
    return plan;
  }

  function card(plan, free) {
    const period = free ? '' : plan.durationDays === 365 ? '/年' : `/${plan.durationDays}天`;
    const price = Number.isInteger(plan.price) ? String(plan.price) : plan.price.toFixed(2);
    const features = plan.features.length ? plan.features.map(item => `<li>${escapeHtml(item)}</li>`).join('') : '<li>接口暂未提供权益明细</li>';
    return `<article class="price-card">
      <h3 class="price-name">${escapeHtml(plan.name)}</h3>
      <div class="price-amount">${escapeHtml(price)}<span class="unit">元${period}</span></div>
      <ul class="price-features">${features}</ul>
      ${free ? '<a class="price-btn price-btn-secondary" href="courses.html">先试学：查看免费内容</a>' : '<p class="price-desc">本页仅展示方案。订阅请使用已验证的小程序入口；本页入口待核验。</p><button class="price-btn price-btn-secondary" type="button" disabled>网页不收款，不在此开通</button>'}
    </article>`;
  }

  function retry(message) {
    return `<p role="status">${escapeHtml(message)}</p><button class="price-btn price-btn-secondary" type="button" data-membership-retry>重新加载套餐</button>`;
  }

  // Pure renderer: API strings are text, never URLs, markup or payment actions.
  function render(payload, status) {
    if (status === 'loading') return '<p role="status">正在加载套餐；网页不创建订单、不收款。</p>';
    if (status === 'error') return retry('套餐加载失败，未展示价格。网页不创建订单、不收款，请重试。');
    try {
      if (!payload || !Array.isArray(payload.plans)) throw new Error('Invalid catalog');
      const plans = payload.plans.map(plan => validatePlan(plan, false));
      const free = payload.free == null ? null : validatePlan(payload.free, true);
      const all = free ? [free, ...plans] : plans;
      if (new Set(all.map(plan => plan.id)).size !== all.length) throw new Error('Duplicate plan');
      const ready = payload.payment && payload.payment.ready === true;
      const message = ready
        ? '接口报告小程序支付配置就绪，但不代表支付链路已验证；本站网页不创建订单、不收款。'
        : '订阅暂未开放或支付状态未确认，当前不创建订单、不收取费用。请先试学。';
      return `<p role="status">${message}</p>` +
        (all.length ? `<div class="pricing-grid">${all.map(plan => card(plan, plan === free)).join('')}</div>` : '') +
        (!plans.length ? retry('暂无可用订阅套餐，不展示默认价格。请稍后重试。') : '');
    } catch (error) {
      return retry('套餐数据不完整或价格无效，未展示价格。网页不创建订单、不收款，请重试。');
    }
  }

  function mount(host, fetcher) {
    let loading = false;
    async function load() {
      if (loading) return;
      loading = true;
      host.setAttribute('aria-busy', 'true');
      host.innerHTML = render(null, 'loading');
      const controller = new AbortController();
      let timer;
      try {
        const payload = await Promise.race([
          (async () => {
            const response = await fetcher('/api/membership/plans', {method: 'GET', cache: 'no-store', signal: controller.signal});
            if (!response.ok) throw new Error('HTTP error');
            return response.json();
          })(),
          new Promise((resolve, reject) => {
            timer = setTimeout(() => { controller.abort(); reject(new Error('Timeout')); }, 15000);
          })
        ]);
        host.innerHTML = render(payload);
      } catch (error) {
        host.innerHTML = render(null, 'error');
      } finally {
        clearTimeout(timer);
        loading = false;
        host.setAttribute('aria-busy', 'false');
      }
    }
    host.addEventListener('click', event => {
      if (event.target.closest('[data-membership-retry]')) load();
    });
    const initialLoad = load();
    return {load, initialLoad};
  }

  return {escapeHtml, render, mount};
});
