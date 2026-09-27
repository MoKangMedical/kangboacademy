const STORAGE_KEY = 'kangboMicroCourseProgressV1';

const MODULES = [
  {
    no: '01',
    english: 'READ THE SIGNAL',
    title: '先看变化，而不是先找答案',
    lead: '周期并不直接告诉你该买什么。它先提示：增长、信用、价格和预期，正在向哪个方向移动。',
    lesson: '关联主干课：康波理论基础',
    prompt: '如果市场情绪非常乐观、估值不断上行，第一步更应该做什么？',
    options: [
      { id: 'a', text: '立即追随最热门的资产', correct: false },
      { id: 'b', text: '核对增长、估值和流动性的变化', correct: true },
      { id: 'c', text: '完全忽略宏观变化，只看单一消息', correct: false }
    ],
    explanation: '判断阶段不是预测顶部。先把情绪和基本变量拆开，才有后续配置与风控的空间。'
  },
  {
    no: '02',
    english: 'LOCATE THE CYCLE',
    title: '给自己一个可复用的坐标系',
    lead: '同一个价格波动，在复苏、繁荣、滞胀和衰退阶段，含义并不一样。定位比结论更重要。',
    lesson: '关联主干课：周金涛四周期嵌套',
    prompt: '一个有效的周期观察框架，至少应同时记录什么？',
    options: [
      { id: 'a', text: '增长、通胀、流动性与风险偏好', correct: true },
      { id: 'b', text: '只记录某一天的涨跌幅', correct: false },
      { id: 'c', text: '只按别人推荐的名单操作', correct: false }
    ],
    explanation: '周期不是单指标竞赛。把四类变量放进同一张观察表，才能知道变化来自哪里。'
  },
  {
    no: '03',
    english: 'TEST THE DECISION',
    title: '把观点变成可回看的动作',
    lead: '真正的学习不止于形成判断，而在于记录行动、设定边界，并在变化后复盘原来的依据。',
    lesson: '关联主干课：投资操作手册 2026-2040',
    prompt: '当你的阶段判断仍有不确定性时，哪个动作更符合风险管理？',
    options: [
      { id: 'a', text: '一次性把所有资金压向单一观点', correct: false },
      { id: 'b', text: '分批行动，并预先写清观察条件', correct: true },
      { id: 'c', text: '不记录依据，凭感觉随时改变计划', correct: false }
    ],
    explanation: '不确定性不是停止思考的理由。小步行动、明确条件、持续复盘，能让判断随着事实更新。'
  }
];

const STAGES = [
  { no: '01', title: '识别', desc: '捕捉变量变化' },
  { no: '02', title: '定位', desc: '找到周期坐标' },
  { no: '03', title: '推演', desc: '写下行动假设' },
  { no: '04', title: '复盘', desc: '让判断可校正' }
];

function getSavedProgress() {
  const saved = wx.getStorageSync(STORAGE_KEY);
  return saved && typeof saved === 'object' ? saved : { answered: {}, startedAt: '' };
}

function buildModules(progress) {
  const answered = progress.answered || {};
  return MODULES.map((module, index) => {
    const selectedId = answered[module.no] || '';
    const answeredModule = !!selectedId;
    return {
      ...module,
      unlocked: index === 0 || !!answered[MODULES[index - 1].no],
      answered: answeredModule,
      selectedId,
      answerCorrect: module.options.some(option => option.id === selectedId && option.correct),
      options: module.options.map(option => ({
        ...option,
        selected: selectedId === option.id,
        showCorrect: answeredModule && option.correct,
        showIncorrect: answeredModule && selectedId === option.id && !option.correct
      }))
    };
  });
}

function buildStages(completed) {
  return STAGES.map((stage, index) => ({
    ...stage,
    active: index <= completed,
    complete: index < completed
  }));
}

Page({
  data: {
    modules: [],
    stages: [],
    completedCount: 0,
    progressPercent: 0,
    finished: false
  },

  onLoad() {
    this.refreshProgress();
  },

  onShow() {
    this.refreshProgress();
  },

  onShareAppMessage() {
    return {
      title: '波动中的决策：康波研究院互动微课程',
      path: '/pages/micro-course/micro-course?utm_source=wechat_share&utm_campaign=micro_course'
    };
  },

  onShareTimeline() {
    return {
      title: '把周期变化变成一条可走的决策路径',
      query: 'utm_source=wechat_timeline&utm_campaign=micro_course'
    };
  },

  refreshProgress() {
    const progress = getSavedProgress();
    const completedCount = Object.keys(progress.answered || {}).length;
    this.setData({
      modules: buildModules(progress),
      stages: buildStages(Math.min(completedCount, STAGES.length - 1)),
      completedCount,
      progressPercent: Math.round((completedCount / MODULES.length) * 100),
      finished: completedCount === MODULES.length
    });
  },

  beginCourse() {
    wx.pageScrollTo({ scrollTop: 620, duration: 360 });
  },

  answerQuestion(e) {
    const moduleIndex = Number(e.currentTarget.dataset.moduleIndex);
    const optionId = e.currentTarget.dataset.optionId;
    const module = MODULES[moduleIndex];
    if (!module) return;

    const progress = getSavedProgress();
    if (progress.answered && progress.answered[module.no]) return;

    progress.startedAt = progress.startedAt || new Date().toISOString();
    progress.answered = { ...(progress.answered || {}), [module.no]: optionId };
    wx.setStorageSync(STORAGE_KEY, progress);
    this.refreshProgress();
  },

  resetProgress() {
    wx.showModal({
      title: '重新开始微课程',
      content: '将清除本地保存的三道判断题进度，不影响主干课程学习记录。',
      confirmText: '重新开始',
      success: res => {
        if (!res.confirm) return;
        wx.removeStorageSync(STORAGE_KEY);
        this.refreshProgress();
      }
    });
  },

  goToCoreCourses() {
    wx.switchTab({ url: '/pages/courses/courses' });
  }
});
