const api = require('../../utils/api');

Component({
 properties: {
 title: {
 type: String,
 value: '康波Agent建议'
 },
 status: {
 type: String,
 value: ''
 },
 intro: {
 type: String,
 value: ''
 },
 prompts: {
 type: Array,
 value: []
 },
 actions: {
 type: Array,
 value: []
 },
 enableChat: {
 type: Boolean,
 value: true
 }
 },

 data: {
 loading: false,
 answer: '',
 error: '',
 activePrompt: ''
 },

 methods: {
 copyText(e) {
 const text = e.currentTarget.dataset.text;
 if (!text) return;

 wx.setClipboardData({
 data: text,
 success() {
 wx.showToast({ title: '已复制给Agent的问题', icon: 'none' });
 }
 });
 },

 askAgent(e) {
 const prompt = e.currentTarget.dataset.text;
 if (!prompt || this.data.loading) return;

 this.setData({
 loading: true,
 answer: '',
 error: '',
 activePrompt: prompt
 });

 api.askAgent({
 prompt,
 source: 'miniapp_tools',
 context: {
 title: this.properties.title,
 status: this.properties.status,
 intro: this.properties.intro
 }
 }).then((res) => {
 this.setData({
 answer: res.answer || '',
 error: ''
 });
 }).catch((err) => {
 let message = err.message || 'Agent暂时不可用，请稍后再试';
 if (message.indexOf('登录') >= 0) {
 message = '请先在“我的”页面完成微信登录，再使用Agent API沟通功能。';
 } else if (message.indexOf('付费') >= 0 || message.indexOf('会员') >= 0 || message.indexOf('订阅') >= 0) {
 message = 'Agent API沟通功能仅限已付费会员使用，请先开通主干课程、书目课程或全库会员。';
 }
 this.setData({
 answer: '',
 error: message
 });
 }).then(() => {
 this.setData({ loading: false });
 });
 }
 }
});
