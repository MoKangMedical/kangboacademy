const phases = [
 { label: '第一康波', year: '1782-1845', start: 1782, end: 1845, desc: '工业革命' },
 { label: '第二康波', year: '1845-1892', start: 1845, end: 1892, desc: '铁路时代' },
 { label: '第三康波', year: '1892-1948', start: 1892, end: 1948, desc: '电气化' },
 { label: '第四康波', year: '1948-1991', start: 1948, end: 1991, desc: '信息化' },
 { label: '第五康波', year: '1991-2025', start: 1991, end: 2025, desc: '互联网' },
 { label: '第六康波', year: '2025-2060+', start: 2025, end: 2060, desc: 'AI+能源+生物' }
];

const profileConfigs = {
 steady: {
 key: 'steady',
 name: '稳健',
 desc: '先守住本金',
 strategy: '以现金流、防守仓和低波动再平衡为主，避免一次性重仓。',
 allocations: [
 { name: '黄金/避险', pct: 22, color: '#e2b64f' },
 { name: '现金/债券', pct: 28, color: '#8b5cf6' },
 { name: 'AI/科技股', pct: 16, color: '#3b82f6' },
 { name: '能源/大宗', pct: 14, color: '#f59e0b' },
 { name: '核心地产', pct: 14, color: '#22c55e' },
 { name: '加密/另类', pct: 6, color: '#ec4899' }
 ]
 },
 balanced: {
 key: 'balanced',
 name: '平衡',
 desc: '攻守兼备',
 strategy: '核心仓保持稳定，卫星仓跟随第六康波主题，季度复盘。',
 allocations: [
 { name: 'AI/科技股', pct: 25, color: '#3b82f6' },
 { name: '能源/大宗', pct: 20, color: '#f59e0b' },
 { name: '黄金/避险', pct: 15, color: '#e2b64f' },
 { name: '核心地产', pct: 15, color: '#22c55e' },
 { name: '现金/债券', pct: 15, color: '#8b5cf6' },
 { name: '加密/另类', pct: 10, color: '#ec4899' }
 ]
 },
 growth: {
 key: 'growth',
 name: '进取',
 desc: '提高成长弹性',
 strategy: '提高成长与新技术敞口，但必须预设回撤阈值和分批规则。',
 allocations: [
 { name: 'AI/科技股', pct: 34, color: '#3b82f6' },
 { name: '加密/另类', pct: 14, color: '#ec4899' },
 { name: '能源/大宗', pct: 18, color: '#f59e0b' },
 { name: '黄金/避险', pct: 12, color: '#e2b64f' },
 { name: '现金/债券', pct: 10, color: '#8b5cf6' },
 { name: '核心地产', pct: 12, color: '#22c55e' }
 ]
 }
};

function findPhase(year) {
 return phases.find(item => year >= item.start && year <= item.end);
}

function buildAgentAdvice(payload) {
 const { birth, current, age, phase, birthPhase, profile } = payload;
 const phaseName = phase ? phase.label : '未知周期';
 const birthPhaseName = birthPhase ? birthPhase.label : '未知出生周期';

 return {
 intro: `你的结果是${phaseName}，风险偏好为${profile.name}。复制下面的问题给Agent，让它先追问约束条件，再给具体行动。`,
 prompts: [
 `我${birth}年出生，${current}年${age}岁，工具判断当前处于${phaseName}，出生于${birthPhaseName}，风险偏好是${profile.name}。请先问我5个关键问题，再给资产配置建议。`,
 `请把这次结果拆成“核心仓、卫星仓、防守仓、现金仓”，并说明每一类的再平衡触发条件。`,
 `如果未来12个月出现衰退、复苏或过热三种不同情景，我应该如何调整这套${profile.name}配置？`
 ],
 actions: [
 { label: '复制个人问诊', text: `我${birth}年出生，现在${age}岁，风险偏好${profile.name}。请结合康波周期，先问我现金流、负债、家庭责任、投资期限和最大可接受回撤，再给建议。` },
 { label: '复制行动清单', text: `请基于${phaseName}和${profile.name}风格，给我一份未来30天可执行的投资行动清单，包含学习、观察、配置、风险控制。` }
 ]
 };
}

Page({
 data: {
 birthYear: '',
 currentYear: '2026',
 activeProfile: 'balanced',
 profileOptions: [profileConfigs.steady, profileConfigs.balanced, profileConfigs.growth],
 result: null,
 timeline: [],
 allocations: [],
 agentIntro: '',
 agentPrompts: [],
 agentActions: []
 },

 onBirthChange(e) {
 this.setData({ birthYear: e.detail.value });
 },

 onCurrentChange(e) {
 this.setData({ currentYear: e.detail.value });
 },

 selectProfile(e) {
 const key = e.currentTarget.dataset.profile;
 this.setData({ activeProfile: key }, () => {
 if (this.data.result) this.calculate();
 });
 },

 calculate() {
 const birth = parseInt(this.data.birthYear, 10);
 const current = parseInt(this.data.currentYear, 10);

 if (!birth || !current || birth < 1900 || current < birth) {
 wx.showToast({ title: '请输入有效年份', icon: 'none' });
 return;
 }

 const age = current - birth;
 const currentPhase = findPhase(current);
 const birthPhase = findPhase(birth);
 const profile = profileConfigs[this.data.activeProfile] || profileConfigs.balanced;
 const timeline = phases.map(item => ({
 ...item,
 active: current >= item.start && current <= item.end
 }));
 const agentAdvice = buildAgentAdvice({
 birth,
 current,
 age,
 phase: currentPhase,
 birthPhase,
 profile
 });

 this.setData({
 result: {
 phase: currentPhase ? currentPhase.label : '未知',
 desc: currentPhase ? `当前处于${currentPhase.desc}周期，你出生于${birthPhase ? birthPhase.label : '未知周期'}。` : '当前年份超出内置康波范围，可让Agent按最新数据继续判断。',
 age,
 profileName: profile.name,
 strategy: profile.strategy
 },
 timeline,
 allocations: profile.allocations,
 agentIntro: agentAdvice.intro,
 agentPrompts: agentAdvice.prompts,
 agentActions: agentAdvice.actions
 });
 }
});
