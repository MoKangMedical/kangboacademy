const api = require('../../utils/api');
const CATEGORY_LABELS = {
 core_theory: '周期理论', economic_thinkers: '经济思想与实战',
 contemporary_china: '中国与生活经济', investment_fundamentals: '投资基础',
 advanced_application: '进阶应用'
};

Page({
 data: { groups: [], nodeCount: 0, linkCount: 0, loading: true, error: '', selected: null, related: [] },
 onLoad() { return this.loadGraph(); },
 async loadGraph() {
 this.setData({ loading: true, error: '', groups: [], selected: null, related: [] });
 try {
 const res = await api.getKnowledgeGraph();
 if (!Array.isArray(res.nodes) || !res.nodes.length || !Array.isArray(res.links)) throw new Error('图谱暂未提供');
 const nodes = res.nodes.filter(node => /^L\d+$/.test(node.id) && node.title)
 .map(node => ({ ...node, lesson: `lesson${Number(node.id.slice(1))}.html` }));
 const byId = new Map(nodes.map(node => [node.id, node]));
 const links = res.links.filter(link => byId.has(link.source) && byId.has(link.target));
 const groups = [];
 nodes.forEach(node => {
 const relatedIds = new Set(links.filter(link => link.source === node.id || link.target === node.id)
 .map(link => link.source === node.id ? link.target : link.source));
 node.relatedIds = Array.from(relatedIds);
 node.desc = `${node.difficulty || '课程'} · ${relatedIds.size}门关联课程`;
 const key = node.category || 'other';
 let group = groups.find(item => item.key === key);
 if (!group) { group = { key, name: CATEGORY_LABELS[key] || key, nodes: [], count: 0 }; groups.push(group); }
 group.nodes.push(node);
 group.count++;
 });
 if (!nodes.length) throw new Error('图谱中暂无可访问课程');
 this.nodes = nodes;
 this.setData({ groups, nodeCount: nodes.length, linkCount: links.length, loading: false });
 } catch (err) {
 this.setData({ loading: false, nodeCount: 0, linkCount: 0, error: '知识图谱暂时无法同步，请重试。' });
 }
 },
 onNodeTap(e) {
 const selected = (this.nodes || []).find(node => node.id === e.currentTarget.dataset.node.id);
 if (!selected) return;
 this.setData({ selected, related: this.nodes.filter(node => selected.relatedIds.includes(node.id)) });
 wx.pageScrollTo({ scrollTop: 0, duration: 250 });
 },
 openCourse(e) {
 const node = (this.nodes || []).find(item => item.id === e.currentTarget.dataset.id);
 if (!node) return;
 wx.navigateTo({ url: `/pages/course-detail/course-detail?lesson=${node.lesson}&title=${encodeURIComponent(node.title)}` });
 }
});
