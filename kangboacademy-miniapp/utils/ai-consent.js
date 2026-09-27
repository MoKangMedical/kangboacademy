function confirmAIProcessing(kind) {
 const details = kind === 'practice'
 ? '练习答案、课后反思、相关课程信息及评分'
 : '你选择的问题、相关工具上下文及内部账号标识';
 const processing = kind === 'practice' ? '处理并保存练习记录' : '处理你提交的问题';

 // Ask for each submission rather than silently reusing a prior consent.
 return new Promise((resolve, reject) => {
 wx.hideLoading();
 wx.showModal({
 title: 'AI处理确认',
 content: `本次提交会由康波研究院服务器${processing}；启用AI分析时，${details}会发送至DeepSeek接口以生成反馈。请勿提交身份证、病历、支付密码等敏感信息。取消不会发送本次内容，也不影响课程浏览。是否同意本次处理？`,
 confirmText: '同意提交',
 cancelText: '取消',
 success(result) {
 if (result.confirm) resolve();
 else reject(new Error('已取消，未发送本次内容'));
 },
 fail() {
 reject(new Error('未获得AI处理确认，本次内容未发送'));
 }
 });
 });
}

module.exports = { confirmAIProcessing };
