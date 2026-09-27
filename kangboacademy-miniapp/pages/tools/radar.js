const assets = {
 gold: {
 name: '黄金', total: 8.5,
 dims: [
 { name: '确定性', score: 9, reason: '央行持续购金，地缘风险支撑' },
 { name: '收益性', score: 8, reason: '突破历史新高，上行趋势明确' },
 { name: '流动性', score: 9, reason: '全球24小时交易，变现极快' },
 { name: '安全性', score: 8, reason: '无对手方风险，终极避险资产' }
 ],
 analysis: '黄金正处于第六轮康波的避险需求上升期。全球央行购金潮+地缘冲突加剧+去美元化趋势，三重因素支撑黄金长期上行。建议配置15-20%。'
 },
 btc: {
 name: '比特币', total: 7.0,
 dims: [
 { name: '确定性', score: 5, reason: '政策监管不确定，波动剧烈' },
 { name: '收益性', score: 9, reason: '减半周期+ETF资金流入，上涨空间大' },
 { name: '流动性', score: 8, reason: 'ETF加持，流动性大幅改善' },
 { name: '安全性', score: 6, reason: '技术风险+监管风险并存' }
 ],
 analysis: '比特币正在经历新一轮减半周期，历史规律偏多。但需注意监管政策变化和极端波动风险。建议配置5-10%，作为另类资产。'
 },
 stock: {
 name: 'A股', total: 6.0,
 dims: [
 { name: '确定性', score: 5, reason: '政策市特征明显，择时难度大' },
 { name: '收益性', score: 7, reason: 'AI/半导体/新能源结构性机会' },
 { name: '流动性', score: 7, reason: '成交活跃，进出方便' },
 { name: '安全性', score: 5, reason: '个股风险高，指数相对安全' }
 ],
 analysis: 'A股处于震荡筑底阶段，结构性机会优于系统性机会。AI产业链、新能源、高端制造是核心赛道。建议配置20-25%。'
 },
 house: {
 name: '房产', total: 5.5,
 dims: [
 { name: '确定性', score: 4, reason: '人口拐点+库存高企，长期承压' },
 { name: '收益性', score: 5, reason: '核心城市抗跌，但增值预期降低' },
 { name: '流动性', score: 5, reason: '二手房挂牌量大增，变现周期拉长' },
 { name: '安全性', score: 8, reason: '实物资产，不会归零' }
 ],
 analysis: '中国房地产进入存量时代，18年周期拐点已现。核心城市核心地段仍有价值，但整体投资回报率下降。建议配置10-15%，精选标的。'
 },
 bond: {
 name: '债券', total: 7.0,
 dims: [
 { name: '确定性', score: 7, reason: '利率下行趋势明确' },
 { name: '收益性', score: 6, reason: '票息收益稳定，资本利得可期' },
 { name: '流动性', score: 8, reason: '市场深度好，大宗交易便捷' },
 { name: '安全性', score: 7, reason: '国债近乎零风险，信用债需精选' }
 ],
 analysis: '全球利率下行周期，债券牛市延续。国债+高评级信用债组合是稳健底仓。建议配置15-20%。'
 },
 oil: {
 name: '原油', total: 6.5,
 dims: [
 { name: '确定性', score: 5, reason: '地缘扰动+OPEC+博弈，供需不确定' },
 { name: '收益性', score: 7, reason: '供给端约束+需求复苏，价格中枢上移' },
 { name: '流动性', score: 7, reason: '期货市场活跃，ETF工具丰富' },
 { name: '安全性', score: 7, reason: '实物资产，地缘溢价支撑' }
 ],
 analysis: '能源转型期供需错配叠加地缘溢价，原油价格中枢上移。但替代能源加速+经济衰退风险压制上行空间。建议配置5-10%。'
 }
};

const goals = {
 preserve: { key: 'preserve', name: '保值', focus: '安全性', desc: '先看本金和回撤' },
 growth: { key: 'growth', name: '增值', focus: '收益性', desc: '先看成长空间' },
 liquid: { key: 'liquid', name: '变现', focus: '流动性', desc: '先看退出能力' },
 certain: { key: 'certain', name: '确定', focus: '确定性', desc: '先看判断把握' }
};

function getDim(asset, dimName) {
 return asset.dims.find(item => item.name === dimName) || asset.dims[0];
}

function buildAdvisor(asset, goal, dimName) {
 const focusDim = getDim(asset, dimName || goal.focus);
 const scores = asset.dims.map(item => `${item.name}${item.score}/10`).join('、');

 return {
 intro: `当前目标是${goal.name}，重点检查${focusDim.name}。点击任一维度后，Agent问题会聚焦该维度。`,
 prompts: [
 `我正在评估${asset.name}，综合评分${asset.total}/10，四维分别是${scores}。我的目标是${goal.name}。请判断它是否匹配我的目标，并先问我必要的约束条件。`,
 `${asset.name}的${focusDim.name}评分为${focusDim.score}/10，理由是：${focusDim.reason}。请反驳这个评分，列出可能被高估或低估的证据。`,
 `请把${asset.name}做成“可以买、需要观察、不能买”三种结论，并给出每种结论的触发条件。`
 ],
 actions: [
 { label: '复制四维问诊', text: `请按确定性、收益性、流动性、安全性四个维度评估${asset.name}，并说明它是否适合我的${goal.name}目标。` },
 { label: '复制反方检查', text: `请作为反方，专门指出我投资${asset.name}最可能忽视的风险，尤其检查${focusDim.name}。` }
 ]
 };
}

Page({
 data: {
 activeAsset: 'gold',
 activeGoal: 'preserve',
 activeDimension: '安全性',
 goalOptions: [goals.preserve, goals.growth, goals.liquid, goals.certain],
 currentAsset: assets.gold,
 agentIntro: buildAdvisor(assets.gold, goals.preserve, '安全性').intro,
 agentPrompts: buildAdvisor(assets.gold, goals.preserve, '安全性').prompts,
 agentActions: buildAdvisor(assets.gold, goals.preserve, '安全性').actions
 },

 selectAsset(e) {
 this.updateState(e.currentTarget.dataset.asset, this.data.activeGoal, this.data.activeDimension);
 },

 selectGoal(e) {
 const goalKey = e.currentTarget.dataset.goal;
 this.updateState(this.data.activeAsset, goalKey, goals[goalKey].focus);
 },

 selectDimension(e) {
 this.updateState(this.data.activeAsset, this.data.activeGoal, e.currentTarget.dataset.dim);
 },

 updateState(assetKey, goalKey, dimName) {
 const asset = assets[assetKey] || assets.gold;
 const goal = goals[goalKey] || goals.preserve;
 const advice = buildAdvisor(asset, goal, dimName);

 this.setData({
 activeAsset: assetKey,
 activeGoal: goalKey,
 activeDimension: dimName,
 currentAsset: asset,
 agentIntro: advice.intro,
 agentPrompts: advice.prompts,
 agentActions: advice.actions
 });
 }
});
