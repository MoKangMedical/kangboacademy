// 资产轮动
const phases = {
 depression_late: {
 name: '萧条末期 · 布局期',
 shortName: '萧条末期',
 desc: '市场恐慌见底，聪明资金开始左侧布局。适合长期价值投资。',
 assets: [
 { name: '黄金', score: 4.5, reason: '避险需求高企，央行持续增持' },
 { name: '高评级债券', score: 4, reason: '利率下行预期，债券牛市' },
 { name: '科技龙头', score: 3.5, reason: '估值低位，长期布局窗口' },
 { name: '比特币', score: 3, reason: '减半周期叠加，历史规律偏多' }
 ],
 courses: [
 { n: 6, lesson: 'lesson6.html', title: '投资操作手册' },
 { n: 42, lesson: 'lesson42.html', title: '全球房地产周期' },
 { n: 60, lesson: 'lesson60.html', title: '金刚经与财富观' },
 { n: 57, lesson: 'lesson57.html', title: '家族办公室与财富传承' }
 ]
 },
 recovery: {
 name: '复苏期 · 进攻期',
 shortName: '复苏期',
 desc: '经济回暖，企业盈利改善，风险偏好上升。适合增加权益配置。',
 assets: [
 { name: 'AI/科技股', score: 5, reason: '技术突破驱动，成长空间大' },
 { name: '新能源', score: 4.5, reason: '能源转型加速，政策支持' },
 { name: 'REITs', score: 4, reason: '利率下行+经济复苏双重利好' },
 { name: '加密资产', score: 3.5, reason: '风险偏好回升，资金流入' }
 ],
 courses: [
 { n: 3, lesson: 'lesson3.html', title: 'AI驱动新纪元' },
 { n: 40, lesson: 'lesson40.html', title: '黄金与货币500年' },
 { n: 41, lesson: 'lesson41.html', title: '石油地缘政治' },
 { n: 53, lesson: 'lesson53.html', title: '量化投资入门' }
 ]
 },
 prosperity: {
 name: '繁荣期 · 收获期',
 shortName: '繁荣期',
 desc: '市场全面上涨，泡沫开始积累，警惕过热信号。适合逐步止盈。',
 assets: [
 { name: '指数基金', score: 4, reason: '趋势跟踪，享受主升浪' },
 { name: '大宗商品', score: 4, reason: '需求旺盛，通胀预期推动' },
 { name: '核心地产', score: 3.5, reason: '资产价格上涨，财富效应' },
 { name: '现金', score: 3, reason: '逐步减仓，保留弹药' }
 ],
 courses: [
 { n: 40, lesson: 'lesson40.html', title: '黄金与货币500年' },
 { n: 41, lesson: 'lesson41.html', title: '石油地缘政治' },
 { n: 45, lesson: 'lesson45.html', title: '大宗商品超级周期' }
 ]
 },
 recession: {
 name: '衰退期 · 防御期',
 shortName: '衰退期',
 desc: '经济下行，企业盈利恶化，避险情绪主导。适合防御性配置。',
 assets: [
 { name: '黄金', score: 5, reason: '终极避险资产，央行增持' },
 { name: '短期国债', score: 4.5, reason: '流动性好，本金安全' },
 { name: '防御板块', score: 4, reason: '必需消费、公用事业抗跌' },
 { name: '美元现金', score: 4, reason: '避险货币，流动性为王' }
 ],
 courses: [
 { n: 1, lesson: 'lesson1.html', title: '康波理论基础' },
 { n: 2, lesson: 'lesson2.html', title: '周金涛周期论' },
 { n: 10, lesson: 'lesson10.html', title: '黑天鹅与反脆弱' },
 { n: 46, lesson: 'lesson46.html', title: '日本失去的三十年' }
 ]
 }
};

const horizons = {
 short: { key: 'short', name: '3个月', desc: '只看验证信号和仓位纪律' },
 mid: { key: 'mid', name: '12个月', desc: '适合做年度配置和季度复盘' },
 long: { key: 'long', name: '3年+', desc: '适合左侧布局和长期主题' }
};

function buildAdvisor(phase, horizon, asset) {
 const assetNames = phase.assets.map(item => item.name).join('、');

 return {
 intro: `当前选择为${phase.shortName}，期限${horizon.name}，重点关注${asset.name}。让Agent先验证阶段判断，再谈仓位。`,
 prompts: [
 `我判断当前处于${phase.name}，投资期限是${horizon.name}，候选资产包括${assetNames}。请把它们分成核心仓、卫星仓、观察仓，并写出调仓触发条件。`,
 `我重点关注${asset.name}，理由是：${asset.reason}。请反向检查这个判断，列出最可能出错的3个前提。`,
 `请基于${phase.shortName}和${horizon.name}期限，给我一份“加仓、持有、减仓、空仓等待”的行动规则。`
 ],
 actions: [
 { label: '复制仓位追问', text: `请根据${phase.shortName}和${horizon.name}期限，把${assetNames}拆成核心仓、卫星仓、观察仓，并给出仓位比例区间。` },
 { label: '复制验证指标', text: `请列出验证${phase.shortName}是否成立的5个宏观或市场指标，并告诉我每月应该如何检查。` }
 ]
 };
}

Page({
 data: {
 activePhase: 'depression_late',
 activeHorizon: 'mid',
 activeAssetIndex: 0,
 horizonOptions: [horizons.short, horizons.mid, horizons.long],
 currentPhase: phases.depression_late,
 focusedAsset: phases.depression_late.assets[0],
 agentIntro: buildAdvisor(phases.depression_late, horizons.mid, phases.depression_late.assets[0]).intro,
 agentPrompts: buildAdvisor(phases.depression_late, horizons.mid, phases.depression_late.assets[0]).prompts,
 agentActions: buildAdvisor(phases.depression_late, horizons.mid, phases.depression_late.assets[0]).actions
 },

 selectPhase(e) {
 this.updateState(e.currentTarget.dataset.phase, this.data.activeHorizon, 0);
 },

 selectHorizon(e) {
 this.updateState(this.data.activePhase, e.currentTarget.dataset.horizon, this.data.activeAssetIndex);
 },

 selectAsset(e) {
 this.updateState(this.data.activePhase, this.data.activeHorizon, Number(e.currentTarget.dataset.index));
 },

 updateState(phaseKey, horizonKey, assetIndex) {
 const phase = phases[phaseKey] || phases.depression_late;
 const horizon = horizons[horizonKey] || horizons.mid;
 const safeIndex = Math.min(assetIndex, phase.assets.length - 1);
 const asset = phase.assets[safeIndex];
 const advice = buildAdvisor(phase, horizon, asset);

 this.setData({
 activePhase: phaseKey,
 activeHorizon: horizonKey,
 activeAssetIndex: safeIndex,
 currentPhase: phase,
 focusedAsset: asset,
 agentIntro: advice.intro,
 agentPrompts: advice.prompts,
 agentActions: advice.actions
 });
 }
});
