// 课程详情页
const API = require('../../utils/api');
const { getCourseContent, getBookCourseContent } = API;
const { fullLogin } = require('../../utils/auth');
const { extractCourseBody, sanitizeCourseImages } = require('../../utils/course-content');
const { normalizeCatalog } = require('../../utils/catalog');

function stripTags(fragment) {
 return String(fragment || '')
 .replace(/<script\b[\s\S]*?<\/script>/gi, '')
 .replace(/<style\b[\s\S]*?<\/style>/gi, '')
 .replace(/<\/(h[1-6]|p|li|div|tr|section|article)>/gi, '\n')
 .replace(/<br\s*\/?>/gi, '\n')
 .replace(/<[^>]+>/g, ' ')
 .replace(/&nbsp;/g, ' ')
 .replace(/&amp;/g, '&')
 .replace(/&lt;/g, '<')
 .replace(/&gt;/g, '>')
 .replace(/&quot;/g, '"')
 .replace(/&#39;/g, "'")
 .replace(/[ \t\r\f\v]+/g, ' ')
 .replace(/\n\s*\n+/g, '\n')
 .trim();
}

function normalizeDifficultyLabel(value) {
 const text = stripTags(value);
 if (!/[]/.test(text)) return text;
 const score = (text.match(/[]/g) || []).length;
 return score ? `难度 ${score}/5` : '';
}

function fallbackLessonTitle(isBookCourse, num) {
 if (!num) return isBookCourse ? '书目课程' : '主干课程';
 return isBookCourse ? `书目课程 ${num}` : `第 ${num} 课`;
}

Page({
 data: {
 lesson: '',
 title: '',
 courseNum: 0,
 courseRef: 0,
 isBookCourse: false,
 favorited: false,
 favoriteLoading: false,
 diffLabel: '',
 time: '',
 content: '',
 readerContent: '',
 loading: true,
 error: '',
 locked: false,
 lockTitle: '',
 lockMessage: '',
 requiredPlan: '',
 nextLesson: '',
 nextLessonTitle: '',
 nextLessonLabel: '下一课',
 audioUrl: '',
 audioTitle: '',
 recommendedBooks: [],
 audioPlaying: false,
 audioLoading: false,
 audioReady: false,
 audioError: '',
 audioCurrent: 0,
 audioDuration: 0,
 audioProgress: 0,
 audioCurrentText: '00:00',
 audioDurationText: '--:--',
 audioSeeking: false,
 autoReading: false,
 autoReadLabel: '慢速阅读',
 practiceLoading: false,
 practiceQuestions: [],
 practiceSubmitted: false,
 practiceScore: 0,
 practiceFeedback: '',
 practiceResults: [],
 reflectionText: '',
 aiAnalysis: null,
 aiFollowUps: [],
 aiAnalysisStatus: '',
 aiAnalysisMessage: '',
 badgesEarned: [],
 dailyRefinement: null,
 submittingPractice: false,
 completed: false,
 savingProgress: false,
 progressError: ''
 },

 audioCtx: null,
 lastAudioSync: 0,
 autoReadTimer: null,
 practiceLoadTimer: null,
 currentScrollTop: 0,

 onLoad(options) {
 const { lesson } = options;
 const safeLesson = lesson || '';
 const isBookCourse = /^book\d+\.html$/.test(safeLesson);
 const match = safeLesson.match(isBookCourse ? /book(\d+)/ : /lesson(\d+)/);
 const num = parseInt(match?.[1]) || 0;
 const nextLesson = '';

 this.setData({
 lesson: safeLesson,
 title: fallbackLessonTitle(isBookCourse, num),
 courseNum: num,
 courseRef: isBookCourse ? 10000 + num : num,
 isBookCourse,
 nextLesson,
 nextLessonTitle: nextLesson ? fallbackLessonTitle(isBookCourse, num + 1) : '',
 nextLessonLabel: isBookCourse ? '下一本' : '下一课'
 });
 this.resolveAdjacentLessonMeta(isBookCourse, num);
 this.loadFavoriteState();
 this.loadCompletionStatus();

 if (lesson) {
 this.loadContent(lesson);
 }
 },

 onUnload() {
 this.stopAutoRead();
 this.clearPracticeTimer();
 this.destroyAudio();
 },

 onPageScroll(e) {
 this.currentScrollTop = e.scrollTop || 0;
 },

 async loadContent(lesson) {
 this.stopAutoRead();
 this.stopAudio();
 this.clearPracticeTimer();
 this.setData({
 loading: true,
 error: '',
 locked: false,
 lockMessage: '',
 content: '',
 readerContent: '',
 practiceLoading: false,
 practiceQuestions: [],
 recommendedBooks: [],
 practiceSubmitted: false,
 practiceScore: 0,
 practiceFeedback: '',
 practiceResults: [],
 reflectionText: '',
 aiAnalysis: null,
 aiFollowUps: [],
 aiAnalysisStatus: '',
 aiAnalysisMessage: '',
 badgesEarned: [],
 dailyRefinement: null,
 submittingPractice: false,
 audioUrl: '',
 audioTitle: '',
 audioPlaying: false,
 audioLoading: false,
 audioReady: false,
 audioError: '',
 audioCurrent: 0,
 audioDuration: 0,
 audioProgress: 0,
 audioCurrentText: '00:00',
 audioDurationText: '--:--'
 });

 try {
 const isBookCourse = /^book\d+\.html$/.test(lesson);
 const res = isBookCourse ? await getBookCourseContent(lesson) : await getCourseContent(lesson);
 if (res && res.locked) {
 this.setData({
 loading: false,
 locked: true,
 lockTitle: isBookCourse ? '书目课程已锁定' : '主干课程已锁定',
 requiredPlan: res.requiredPlan || (isBookCourse ? 'books_year' : 'core_year'),
 lockMessage: res.message || '订阅后可继续学习'
 });
 return;
 }
 const html = typeof res === 'string' ? res : (res.content || '');
 const content = extractCourseBody(html);
 const audioUrl = typeof res === 'object' ? (res.audioUrl || '') : this.extractAudioUrl(html);
 const cleanContent = this.sanitizeContent(content);
 const apiRecommendedBooks = typeof res === 'object' ? this.normalizeRecommendedBooks(res.recommendedBooks) : [];
 const recommendedBooks = apiRecommendedBooks.length ? apiRecommendedBooks : this.extractRecommendedBooks(cleanContent);
 const readableContent = recommendedBooks.length ? this.removeRecommendedReadingSection(cleanContent) : cleanContent;
 if (!stripTags(readableContent)) {
 throw new Error('本课正文暂未提供，请稍后重试；练习不能替代课程正文。');
 }
 const responseTitle = typeof res === 'object' ? (res.title || '') : '';
 this.responseTitle = responseTitle;
 const resolvedTitle = responseTitle || this.catalogTitle || fallbackLessonTitle(isBookCourse, this.data.courseNum);

 this.setData({
 title: resolvedTitle,
 content: readableContent,
 readerContent: this.formatReadingContent(readableContent),
 audioUrl,
 audioTitle: resolvedTitle || (isBookCourse ? '书目课程音频' : '课程音频'),
 recommendedBooks,
 loading: false
 });
 this.loadFavoriteState();

 this.schedulePracticeLoad(lesson);
 } catch (err) {
 console.error('加载课程失败:', err);
 this.setData({
 loading: false,
 error: err.message || '课程内容加载失败，请检查网络后重试'
 });
 }
 },

 sanitizeContent(html) {
 return sanitizeCourseImages(html)
 .replace(/<script\b[\s\S]*?<\/script>/gi, '')
 .replace(/<style\b[\s\S]*?<\/style>/gi, '')
 .replace(/<div[^>]*class=["'][^"']*audio-player[^"']*["'][^>]*>[\s\S]*?<\/audio>\s*<\/div>\s*(<\/div>)?/gi, '')
 .replace(/<audio\b[\s\S]*?<\/audio>/gi, '')
 .replace(/`{1,3}<code>\s*/gi, '<br>')
 .replace(/<\/code>`{1,3}<code>/gi, '<br>')
 .replace(/<\/code>`{1,3}/gi, '<br>');
 },

 normalizeRecommendedBooks(books) {
 return (books || [])
 .map(book => ({
 title: stripTags(book.title || book.name || ''),
 author: stripTags(book.author || ''),
 difficulty: normalizeDifficultyLabel(book.difficulty || book.level || ''),
 reason: stripTags(book.reason || book.value || book.desc || '')
 }))
 .filter(book => book.title && book.title !== '书籍' && book.title !== '书名')
 .slice(0, 8);
 },

 extractRecommendedBooks(html) {
 if (!html) return [];
 const sections = [];
 const headingRe = /<h[23][^>]*>[^<]*(推荐阅读|延伸阅读|参考书目)[^<]*<\/h[23]>([\s\S]*?)(?=<h[23]\b|<hr\b|$)/gi;
 let match;
 while ((match = headingRe.exec(html))) {
 sections.push(match[2]);
 }
 const recommendDiv = html.match(/<div[^>]*class=["'][^"']*recommend[^"']*["'][^>]*>([\s\S]*?)<\/div>/i);
 if (recommendDiv) sections.push(recommendDiv[1]);

 for (const section of sections) {
 const fromTable = this.parseRecommendedTable(section);
 if (fromTable.length) return fromTable;
 const fromList = this.parseRecommendedList(section);
 if (fromList.length) return fromList;
 }
 return [];
 },

 parseRecommendedTable(section) {
 const rows = section.match(/<tr[^>]*>[\s\S]*?<\/tr>/gi) || [];
 let headers = [];
 const books = [];
 rows.forEach(row => {
 const rawCells = row.match(/<t[dh][^>]*>[\s\S]*?<\/t[dh]>/gi) || [];
 const cells = rawCells.map(cell => stripTags(cell)).filter(Boolean);
 if (!cells.length) return;
 if (/<th\b/i.test(row)) {
 headers = cells;
 return;
 }
 if (cells[0] === '书籍' || cells[0] === '书名') return;
 const book = { title: cells[0], author: '', difficulty: '', reason: '' };
 if (headers.length) {
 headers.slice(0, cells.length).forEach((header, index) => {
 const value = cells[index];
 if (header.includes('书')) book.title = value;
 else if (header.includes('作者')) book.author = value;
 else if (header.includes('难度')) book.difficulty = value;
 else if (header.includes('价值') || header.includes('理由')) book.reason = value;
 else if (header.includes('关联') && value) book.reason = book.reason ? `${book.reason}；关联度：${value}` : `关联度：${value}`;
 });
 } else {
 book.author = cells[1] || '';
 if (cells.length === 3) {
 book.reason = cells[2];
 } else if (cells.length >= 4) {
 if (/[]/.test(cells[2])) {
 book.difficulty = cells[2];
 book.reason = cells[3];
 } else {
 book.reason = cells[2];
 book.difficulty = /[]/.test(cells[3]) ? cells[3] : '';
 }
 }
 }
 books.push(book);
 });
 return this.normalizeRecommendedBooks(books);
 },

 parseRecommendedList(section) {
 const items = section.match(/<li[^>]*>[\s\S]*?<\/li>/gi) || [];
 const books = items.map(item => this.parseRecommendedLine(item)).filter(Boolean);
 return this.normalizeRecommendedBooks(books);
 },

 parseRecommendedLine(fragment) {
 const line = stripTags(fragment).replace(/\s+/g, ' ').trim();
 const titleMatch = line.match(/《[^》]+》/);
 if (!titleMatch) return null;
 const title = titleMatch[0];
 const before = line.slice(0, titleMatch.index).replace(/[：:，,.\-—\s]+$/g, '').trim();
 const after = line.slice(titleMatch.index + title.length).trim();
 let author = before && before.length <= 32 ? before : '';
 let reason = '';
 const sep = after.match(/\s*(——|—|-)\s*/);
 if (sep) {
 if (!author) author = after.slice(0, sep.index).replace(/[，,\s]+$/g, '').trim();
 reason = after.slice(sep.index + sep[0].length).trim();
 } else if (!author) {
 author = after.replace(/[，,\s]+$/g, '').trim();
 }
 return { title, author, reason };
 },

 removeRecommendedReadingSection(html) {
 return html
 .replace(/<div[^>]*class=["'][^"']*recommend[^"']*["'][^>]*>[\s\S]*?<\/div>/gi, '')
 .replace(/<h[23][^>]*>[^<]*(推荐阅读|延伸阅读|参考书目)[^<]*<\/h[23]>[\s\S]*?(?=<h[23]\b|<hr\b|$)/gi, '');
 },

 formatReadingContent(html) {
 if (!html) return '';
 return html
 .replace(/<h1[^>]*>/gi, '<h2 style="font-size:24px;line-height:1.35;margin:28px 0 14px;color:#f5f5f7;font-weight:800;">')
 .replace(/<\/h1>/gi, '</h2>')
 .replace(/<h2[^>]*>/gi, '<h2 style="font-size:22px;line-height:1.4;margin:30px 0 14px;color:#f0d478;font-weight:800;">')
 .replace(/<h3[^>]*>/gi, '<h3 style="font-size:19px;line-height:1.45;margin:24px 0 10px;color:#f5f5f7;font-weight:750;">')
 .replace(/<p[^>]*>/gi, '<p style="font-size:17px;line-height:2.05;margin:0 0 18px;color:#e8e8ee;">')
 .replace(/<li[^>]*>/gi, '<li style="font-size:16px;line-height:1.95;margin:8px 0;color:#dedee8;">')
 .replace(/<ul[^>]*>/gi, '<ul style="padding-left:22px;margin:10px 0 18px;">')
 .replace(/<ol[^>]*>/gi, '<ol style="padding-left:22px;margin:10px 0 18px;">')
 .replace(/<blockquote[^>]*>/gi, '<blockquote style="margin:18px 0;padding:14px 16px;border-left:3px solid #e2b64f;background:#15151c;color:#d9d9e3;">')
 .replace(/<strong[^>]*>/gi, '<strong style="color:#f0d478;font-weight:800;">')
 .replace(/<table[^>]*>/gi, '<table style="width:100%;border-collapse:collapse;margin:18px 0;font-size:14px;color:#e8e8ee;">')
 .replace(/<th[^>]*>/gi, '<th style="border:1px solid #2c2c38;padding:8px;background:#1c1c24;color:#f0d478;">')
 .replace(/<td[^>]*>/gi, '<td style="border:1px solid #2c2c38;padding:8px;color:#d8d8e2;">');
 },

 extractAudioUrl(html) {
 const sourceMatch = html.match(/<source[^>]+src=["']([^"']+)["']/i) || html.match(/<audio[^>]+src=["']([^"']+)["']/i);
 if (!sourceMatch) return '';
 const src = sourceMatch[1];
 if (/^https?:\/\//i.test(src)) return src;
 if (src.startsWith('//')) return `https:${src}`;
 if (src.startsWith('/')) return `${API.BASE_URL}${src}`;
 return `${API.BASE_URL}/${src.replace(/^\.\//, '')}`;
 },

 prepareAudio(src) {
 if (!src) return;
 this.initAudio();
 this.audioCtx.stop();
 this.audioCtx.src = src;
 this.setData({ audioLoading: true, audioError: '' });
 },

 initAudio() {
 if (this.audioCtx) return;
 const audio = wx.createInnerAudioContext();
 audio.obeyMuteSwitch = false;

 audio.onCanplay(() => {
 this.setData({ audioLoading: false, audioReady: true, audioError: '' });
 setTimeout(() => this.syncAudioTime(true), 300);
 });
 audio.onPlay(() => this.setData({ audioPlaying: true, audioLoading: false }));
 audio.onPause(() => this.setData({ audioPlaying: false }));
 audio.onStop(() => this.setData({ audioPlaying: false }));
 audio.onEnded(() => {
 const duration = this.data.audioDuration || audio.duration || 0;
 this.setData({
 audioPlaying: false,
 audioCurrent: duration,
 audioProgress: 100,
 audioCurrentText: this.formatAudioTime(duration)
 });
 });
 audio.onTimeUpdate(() => this.syncAudioTime());
 audio.onError(err => {
 console.error('音频播放失败:', err);
 this.setData({
 audioPlaying: false,
 audioLoading: false,
 audioReady: false,
 audioError: '音频加载失败，请稍后重试'
 });
 });

 this.audioCtx = audio;
 },

 clearPracticeTimer() {
 if (this.practiceLoadTimer) {
 clearTimeout(this.practiceLoadTimer);
 this.practiceLoadTimer = null;
 }
 },

 schedulePracticeLoad(lesson) {
 this.clearPracticeTimer();
 this.practiceLoadTimer = setTimeout(() => {
 this.practiceLoadTimer = null;
 if (!this.data.locked && !this.data.error && this.data.lesson === lesson) {
 this.loadPractice(lesson);
 }
 }, 600);
 },

 syncAudioTime(force = false) {
 if (!this.audioCtx || this.data.audioSeeking) return;
 const now = Date.now();
 if (!force && now - this.lastAudioSync < 500) return;
 this.lastAudioSync = now;

 const current = this.audioCtx.currentTime || 0;
 const duration = this.audioCtx.duration || this.data.audioDuration || 0;
 this.setData({
 audioCurrent: current,
 audioDuration: duration,
 audioProgress: duration ? Math.min(100, Math.round((current / duration) * 100)) : 0,
 audioCurrentText: this.formatAudioTime(current),
 audioDurationText: duration ? this.formatAudioTime(duration) : '--:--'
 });
 },

 toggleAudio() {
 if (!this.data.audioUrl) return;
 this.initAudio();
 if (this.audioCtx.src !== this.data.audioUrl) {
 this.audioCtx.src = this.data.audioUrl;
 }
 if (this.data.audioPlaying) {
 this.audioCtx.pause();
 } else {
 this.setData({ audioLoading: true, audioError: '' });
 this.audioCtx.play();
 }
 },

 onAudioSliderChanging(e) {
 this.setData({
 audioSeeking: true,
 audioProgress: e.detail.value
 });
 },

 onAudioSliderChange(e) {
 const duration = this.data.audioDuration || 0;
 const value = e.detail.value || 0;
 const target = duration ? duration * value / 100 : 0;
 if (this.audioCtx && duration) {
 this.audioCtx.seek(target);
 }
 this.setData({
 audioSeeking: false,
 audioCurrent: target,
 audioProgress: value,
 audioCurrentText: this.formatAudioTime(target)
 });
 },

 stopAudio() {
 if (this.audioCtx) {
 this.audioCtx.stop();
 }
 },

 destroyAudio() {
 if (this.audioCtx) {
 this.audioCtx.destroy();
 this.audioCtx = null;
 }
 },

 formatAudioTime(seconds) {
 const safeSeconds = Math.max(0, Math.floor(seconds || 0));
 const min = String(Math.floor(safeSeconds / 60)).padStart(2, '0');
 const sec = String(safeSeconds % 60).padStart(2, '0');
 return `${min}:${sec}`;
 },

 toggleAutoRead() {
 if (this.data.autoReading) {
 this.stopAutoRead();
 } else {
 this.startAutoRead();
 }
 },

 startAutoRead() {
 if (this.autoReadTimer || this.data.locked || this.data.loading) return;
 this.setData({ autoReading: true, autoReadLabel: '暂停阅读' });
 this.autoReadTimer = setInterval(() => {
 this.currentScrollTop += 10;
 wx.pageScrollTo({
 scrollTop: this.currentScrollTop,
 duration: 900
 });
 }, 1200);
 },

 stopAutoRead() {
 if (this.autoReadTimer) {
 clearInterval(this.autoReadTimer);
 this.autoReadTimer = null;
 }
 if (this.data.autoReading) {
 this.setData({ autoReading: false, autoReadLabel: '慢速阅读' });
 }
 },

 async loadPractice(lesson) {
 this.setData({ practiceLoading: true });
 try {
 const res = await API.getPractice(lesson);
 if (res.locked) {
 this.setData({ practiceLoading: false, practiceQuestions: [] });
 return;
 }
 const questions = (res.questions || []).map(q => ({
 ...q,
 answer: '',
 result: null
 }));
 this.setData({
 practiceLoading: false,
 practiceQuestions: questions
 });
 } catch (err) {
 console.error('加载练习失败:', err);
 this.setData({ practiceLoading: false, practiceQuestions: [] });
 }
 },

 onPracticeInput(e) {
 const id = e.currentTarget.dataset.id;
 const value = e.detail.value || '';
 const questions = this.data.practiceQuestions.map(q => (
 q.id === id ? { ...q, answer: value } : q
 ));
 this.setData({ practiceQuestions: questions });
 },

 onReflectionInput(e) {
 this.setData({ reflectionText: e.detail.value || '' });
 },

 async ensureLoginForPractice() {
 if (wx.getStorageSync('token')) return true;
 const data = await fullLogin();
 const app = getApp();
 app.globalData.userInfo = data.userInfo;
 app.globalData.isLogin = true;
 return true;
 },

 courseFavoritePayload() {
 const { courseRef, lesson, title, isBookCourse } = this.data;
 return {
 course_id: courseRef,
 lesson,
 title,
 is_book_course: !!isBookCourse
 };
 },

 async loadFavoriteState() {
 if (!wx.getStorageSync('token') || !this.data.courseRef) return;
 try {
 const res = await API.getBookmarks();
 const favorited = (res.bookmarks || []).some(item => item.courseRef === this.data.courseRef);
 this.setData({ favorited });
 } catch (err) {
 // 收藏状态加载失败不影响课程阅读。
 }
 },

 async toggleFavorite() {
 if (this.data.favoriteLoading || this.data.locked || !this.data.courseRef) return;
 this.setData({ favoriteLoading: true });
 try {
 await this.ensureLoginForPractice();
 const res = await API.toggleBookmark(this.courseFavoritePayload());
 this.setData({
 favorited: !!res.bookmarked,
 favoriteLoading: false
 });
 wx.showToast({
 title: res.bookmarked ? '已收藏' : '已取消收藏',
 icon: 'success'
 });
 } catch (err) {
 this.setData({ favoriteLoading: false });
 wx.showToast({ title: err.message || '收藏失败', icon: 'none' });
 }
 },

 async submitPractice() {
 if (this.data.submittingPractice || !this.data.practiceQuestions.length) return;
 const hasAnswer = this.data.practiceQuestions.some(q => (q.answer || '').trim());
 if (!hasAnswer) {
 wx.showToast({ title: '请先完成至少一道练习', icon: 'none' });
 return;
 }
 const reflection = (this.data.reflectionText || '').trim();
 if (reflection.length < 10) {
 wx.showToast({ title: '请先写下至少10个字的课后反思', icon: 'none' });
 return;
 }

 this.setData({ submittingPractice: true });
 wx.showLoading({ title: '分析练习中...' });
 try {
 await this.ensureLoginForPractice();
 const answers = {};
 this.data.practiceQuestions.forEach(q => {
 answers[q.id] = q.answer || '';
 });
 const res = await API.submitPractice(this.data.lesson, answers, reflection);
 const resultMap = {};
 (res.results || []).forEach(item => {
 resultMap[item.questionId] = item;
 });
 const questions = this.data.practiceQuestions.map(q => ({
 ...q,
 result: resultMap[q.id] || null
 }));
 this.setData({
 practiceQuestions: questions,
 practiceSubmitted: true,
 practiceScore: res.score || 0,
 practiceFeedback: res.feedback || '',
 practiceResults: res.results || [],
 aiAnalysis: res.aiAnalysis || null,
 aiFollowUps: res.aiFollowUps || [],
 aiAnalysisStatus: res.aiAnalysisStatus || '',
 aiAnalysisMessage: res.aiAnalysisMessage || '',
 badgesEarned: res.badgesEarned || [],
 dailyRefinement: res.dailyRefinement || null,
 submittingPractice: false
 });
 wx.hideLoading();
 wx.showToast({ title: '练习已完成', icon: 'success' });
 } catch (err) {
 wx.hideLoading();
 this.setData({ submittingPractice: false });
 wx.showToast({ title: err.message || '提交失败', icon: 'none' });
 }
 },

 retry() {
 if (this.data.lesson) this.loadContent(this.data.lesson);
 },

 async loadCompletionStatus() {
 if (!wx.getStorageSync('token')) return;
 try {
 const result = await API.getProgress();
 const row = (result.progress || []).find(item => Number(item.course_id) === this.data.courseRef);
 if (!this.data.completed && !this.data.savingProgress) {
 this.setData({ completed: !!row && row.status === 'completed' });
 }
 } catch (err) {
 // Reading remains available when progress cannot be fetched.
 }
 },

 async markComplete() {
 if (this.data.locked || this.data.loading || this.data.error || this.data.savingProgress || this.data.completed) return;
 this.setData({ savingProgress: true, progressError: '' });
 try {
 if (!wx.getStorageSync('token')) await fullLogin();
 const result = await API.saveProgress({ course_id: this.data.courseRef, status: 'completed', progress_percent: 100 });
 if (!result || result.success !== true) throw new Error('服务器未确认保存，请重试');
 this.setData({ completed: true });
 wx.showToast({ title: '学习进度已同步', icon: 'success' });
 } catch (err) {
 this.setData({ progressError: err.message || '进度未同步，请重试' });
 wx.showToast({ title: '进度未同步，请重试', icon: 'none' });
 } finally {
 this.setData({ savingProgress: false });
 }
 },

 goSubscribe() {
 const scope = this.data.isBookCourse ? 'books' : 'core';
 wx.navigateTo({
 url: `/pages/membership/membership?scope=${scope}`
 });
 },

 async resolveAdjacentLessonMeta(isBookCourse, num) {
 try {
 const res = isBookCourse ? await API.getBookCourses() : await API.getCourses();
 const courses = normalizeCatalog(res, isBookCourse);
 if (this.data.courseNum !== num || this.data.isBookCourse !== isBookCourse) return;
 const current = courses.find(course => Number(course.id || course.n) === num);
 if (current && this.data.courseNum === num && this.data.isBookCourse === isBookCourse) {
 this.catalogTitle = current.title || current.t || '';
 const title = this.responseTitle || this.catalogTitle || fallbackLessonTitle(isBookCourse, num);
 this.setData({ title, audioTitle: title });
 }
 const index = courses.findIndex(course => course.n === num);
 const next = index >= 0 ? courses[index + 1] : null;
 const title = next ? (next.title || next.t || '') : '';
 this.setData({ nextLesson: next ? next.lesson : '', nextLessonTitle: title });
 } catch (err) {
 // Do not guess a next lesson when catalog identity/order cannot be verified.
 this.setData({ nextLesson: '', nextLessonTitle: '' });
 }
 },

 nextLesson() {
 const { nextLesson, nextLessonTitle, isBookCourse, courseNum } = this.data;
 if (!nextLesson) return;
 const title = nextLessonTitle || fallbackLessonTitle(isBookCourse, courseNum + 1);
 wx.redirectTo({
 url: `/pages/course-detail/course-detail?lesson=${nextLesson}&title=${encodeURIComponent(title)}`
 });
 }
});
