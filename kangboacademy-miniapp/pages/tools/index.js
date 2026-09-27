const tools = [
 {
 url: '/pages/tools/calculator',
 name: '康波计算器',
 desc: '输入出生年份和风险偏好，定位周期位置并生成资产配置提问',
 tag: '周期定位'
 },
 {
 url: '/pages/tools/asset-rotation',
 name: '资产轮动查询',
 desc: '按周期阶段和投资期限，生成仓位节奏、观察指标和调仓追问',
 tag: '配置策略'
 },
 {
 url: '/pages/tools/radar',
 name: '四维评分',
 desc: '从确定性、收益性、流动性、安全性诊断单类资产',
 tag: '资产体检'
 },
 {
 url: '/pages/tools/ranking',
 name: '四维排名榜',
 desc: '按进攻、防守、流动性等目标切换资产排序',
 tag: '优先级'
 }
];

const scenarios = {
 cycle: {
 key: 'cycle',
 name: '先判断周期',
 desc: '适合不知道当前处在什么阶段时使用。先做周期定位，再让Agent追问年龄、现金流、负债和风险边界。',
 steps: ['康波计算器', '风险偏好', '复制问题给Agent'],
 prompts: [
 '请先问我5个问题，判断我的年龄、现金流、负债、投资期限和风险承受力，再结合康波周期给出资产配置建议。',
 '请把“周期位置、个人阶段、资产节奏、最大风险”整理成一张决策表，不要直接推荐单一资产。',
 '如果当前周期判断错了，哪些指标会最先提示我需要修正？请给我一个月度观察清单。'
 ],
 actions: [
 { label: '复制周期问诊', text: '我想先判断自己的康波周期位置。请按年龄、现金流、负债、风险承受力、投资期限五个方面依次问我问题，然后再给建议。' },
 { label: '复制复盘框架', text: '请按“周期判断-个人约束-资产配置-风险边界-下一步行动”五段帮我做一次投资复盘。' }
 ]
 },
 portfolio: {
 key: 'portfolio',
 name: '优化配置',
 desc: '适合已经有持仓或想设计组合时使用。先看资产轮动，再用Agent把仓位拆成核心、卫星和观察仓。',
 steps: ['资产轮动', '选择期限', '生成仓位追问'],
 prompts: [
 '请根据我当前的周期判断，把组合拆成核心仓、卫星仓、观察仓，并写出每一类的调仓触发条件。',
 '请用保守、平衡、进取三种版本，分别给出不超过6项资产的配置比例。',
 '请帮我把这套配置改成每月定投计划，并设置季度再平衡规则。'
 ],
 actions: [
 { label: '复制配置问诊', text: '我想优化资产配置。请先问我现有持仓、可投资金额、月现金流、最大可接受回撤和资金使用期限，再给出组合建议。' },
 { label: '复制调仓规则', text: '请给我一套简单调仓规则：什么时候加仓、什么时候减仓、什么时候只观察。' }
 ]
 },
 risk: {
 key: 'risk',
 name: '检查风险',
 desc: '适合准备买入前使用。用四维评分和排名榜检查确定性、收益性、流动性、安全性是否匹配。',
 steps: ['四维评分', '排名对比', '让Agent挑错'],
 prompts: [
 '请从确定性、收益性、流动性、安全性四个维度反驳我的投资想法，并指出最容易被我忽视的风险。',
 '请用“最坏情况、触发条件、应对动作”三列做一张风险表。',
 '请检查我是否把短期波动误认为长期趋势，并给出避免冲动交易的流程。'
 ],
 actions: [
 { label: '复制风险追问', text: '我准备买入一个资产。请你先从确定性、收益性、流动性、安全性四个维度问我问题，再指出反对买入的理由。' },
 { label: '复制止损清单', text: '请帮我设计一份止损和降仓清单，包含价格、基本面、政策、流动性四类触发条件。' }
 ]
 }
};

Page({
 data: {
 tools,
 scenarioOptions: [scenarios.cycle, scenarios.portfolio, scenarios.risk],
 activeScenario: 'cycle',
 currentScenario: scenarios.cycle
 },

 selectScenario(e) {
 const key = e.currentTarget.dataset.key;
 this.setData({
 activeScenario: key,
 currentScenario: scenarios[key]
 });
 }
});
