const modes = {
 balanced: { key: 'balanced', name: '综合', desc: '周期适应力' },
 growth: { key: 'growth', name: '进攻', desc: '成长弹性' },
 defense: { key: 'defense', name: '防守', desc: '回撤控制' },
 liquid: { key: 'liquid', name: '流动', desc: '退出能力' }
};

const baseRankings = [
 {
 name: '黄金', reason: '跨周期避险+央行增持+地缘溢价',
 scores: { balanced: 8.5, growth: 7.4, defense: 9.2, liquid: 8.8 }
 },
 {
 name: 'AI/科技股', reason: '第六轮康波核心驱动力，结构性变革',
 scores: { balanced: 8.2, growth: 9.4, defense: 5.8, liquid: 7.4 }
 },
 {
 name: '比特币', reason: '减半周期+ETF，高风险高回报',
 scores: { balanced: 7.0, growth: 8.6, defense: 4.8, liquid: 8.2 }
 },
 {
 name: '长期国债', reason: '利率下行周期，确定性高',
 scores: { balanced: 7.0, growth: 5.6, defense: 8.5, liquid: 7.2 }
 },
 {
 name: '新能源', reason: '能源转型大趋势，政策持续支持',
 scores: { balanced: 6.8, growth: 8.0, defense: 5.4, liquid: 6.8 }
 },
 {
 name: 'REITs', reason: '利率下行+商业地产触底反弹',
 scores: { balanced: 6.5, growth: 6.2, defense: 6.7, liquid: 6.3 }
 },
 {
 name: '原油期货', reason: '地缘溢价+供给约束',
 scores: { balanced: 6.5, growth: 7.0, defense: 5.8, liquid: 7.8 }
 },
 {
 name: 'A股指数', reason: '结构性机会，需精选赛道',
 scores: { balanced: 6.0, growth: 7.2, defense: 5.3, liquid: 7.5 }
 },
 {
 name: '核心房产', reason: '人口拐点，精选标的仍有价值',
 scores: { balanced: 5.5, growth: 4.8, defense: 6.0, liquid: 3.6 }
 },
 {
 name: '美元现金', reason: '通胀侵蚀，但流动性为王',
 scores: { balanced: 5.0, growth: 3.8, defense: 7.4, liquid: 9.4 }
 }
];

function buildRankings(modeKey) {
 return baseRankings
 .map(item => ({
 ...item,
 score: item.scores[modeKey] || item.scores.balanced
 }))
 .sort((a, b) => b.score - a.score)
 .map((item, index) => ({
 ...item,
 rank: index + 1
 }));
}

function buildAdvisor(mode, selectedAsset, rankings) {
 const topThree = rankings.slice(0, 3).map(item => item.name).join('、');

 return {
 intro: `当前排序模式是${mode.name}，前三名为${topThree}。点击任一资产后，Agent问题会聚焦该资产。`,
 prompts: [
 `我现在按${mode.name}目标查看资产排名，前三名是${topThree}。请先问我投资期限、现金流、最大回撤和已有持仓，再判断这些资产是否适合我。`,
 `我重点关注${selectedAsset.name}，当前${mode.name}评分${selectedAsset.score}/10，理由是：${selectedAsset.reason}。请给我买入前必须验证的5个问题。`,
 `请把${mode.name}排名转成一个“核心仓、卫星仓、观察仓、暂不碰”的清单，并说明每类适合什么人。`
 ],
 actions: [
 { label: '复制排名问诊', text: `请基于${mode.name}目标，比较${topThree}，先问我约束条件，再给出适合我的排序。` },
 { label: '复制资产追问', text: `我想重点研究${selectedAsset.name}。请从周期位置、估值、流动性、风险触发条件四方面追问我。` }
 ]
 };
}

const initialRankings = buildRankings('balanced');
const initialAdvice = buildAdvisor(modes.balanced, initialRankings[0], initialRankings);

Page({
 data: {
 modeOptions: [modes.balanced, modes.growth, modes.defense, modes.liquid],
 activeMode: 'balanced',
 selectedIndex: 0,
 displayedRankings: initialRankings,
 selectedAsset: initialRankings[0],
 agentIntro: initialAdvice.intro,
 agentPrompts: initialAdvice.prompts,
 agentActions: initialAdvice.actions
 },

 selectMode(e) {
 const modeKey = e.currentTarget.dataset.mode;
 const rankings = buildRankings(modeKey);
 const advice = buildAdvisor(modes[modeKey], rankings[0], rankings);

 this.setData({
 activeMode: modeKey,
 selectedIndex: 0,
 displayedRankings: rankings,
 selectedAsset: rankings[0],
 agentIntro: advice.intro,
 agentPrompts: advice.prompts,
 agentActions: advice.actions
 });
 },

 selectAsset(e) {
 const index = Number(e.currentTarget.dataset.index);
 const selectedAsset = this.data.displayedRankings[index];
 const advice = buildAdvisor(modes[this.data.activeMode], selectedAsset, this.data.displayedRankings);

 this.setData({
 selectedIndex: index,
 selectedAsset,
 agentIntro: advice.intro,
 agentPrompts: advice.prompts,
 agentActions: advice.actions
 });
 }
});
