// ═══════════════════════════════════════════
//  通用工具函数
// ═══════════════════════════════════════════

/**
 * 格式化时间
 */
function formatTime(date) {
 const year = date.getFullYear();
 const month = date.getMonth() + 1;
 const day = date.getDate();
 return `${year}-${pad(month)}-${pad(day)}`;
}

function pad(n) {
 return n < 10 ? '0' + n : '' + n;
}

/**
 * 防抖
 */
function debounce(fn, delay = 300) {
 let timer = null;
 return function (...args) {
 if (timer) clearTimeout(timer);
 timer = setTimeout(() => fn.apply(this, args), delay);
 };
}

/**
 * 节流
 */
function throttle(fn, interval = 300) {
 let last = 0;
 return function (...args) {
 const now = Date.now();
 if (now - last >= interval) {
 last = now;
 fn.apply(this, args);
 }
 };
}

/**
 * 难度标签颜色映射
 */
const DIFF_MAP = {
 beginner: { label: '入门', color: 'tag-green' },
 core: { label: '核心', color: 'tag-gold' },
 advanced: { label: '进阶', color: 'tag-purple' }
};

module.exports = {
 formatTime,
 pad,
 debounce,
 throttle,
 DIFF_MAP
};
