// 首页
const api = require('../../utils/api');
const { normalizeCatalog, groupCoreCourses } = require('../../utils/catalog');

const AUDIO_SCOPE_LABELS = {
 all: '全部课程',
 core: '主干课程',
 books: '书目课程'
};

Page({
 data: {
 audioScope: 'all',
 audioScopeTabs: [
 { key: 'all', label: '全部' },
 { key: 'core', label: '主干' },
 { key: 'books', label: '书目' }
 ],
 audioTracks: [],
 audioTotal: 0,
 audioPreviewTracks: [],
 audioCounts: { core: 0, book: 0 },
 currentAudioIndex: 0,
 currentAudio: null,
 audioLoading: false,
 audioListLoading: true,
 audioPlaying: false,
 audioReady: false,
 audioError: '',
 audioCurrent: 0,
 audioDuration: 0,
 audioProgress: 0,
 audioCurrentText: '00:00',
 audioDurationText: '--:--',
 audioScopeLabel: '全部课程',
 phases: [],
 catalogTotal: 0,
 catalogLoading: true,
 catalogError: ''
 },

 audioCtx: null,
 lastAudioSync: 0,
 audioSeeking: false,

 onLoad() {
 this.loadAudioPlaylist('all');
 this.loadCatalog();
 },

 async loadCatalog() {
 this.setData({ catalogLoading: true, catalogError: '', phases: [], catalogTotal: 0 });
 try {
 const courses = normalizeCatalog(await api.getCourses(), false);
 this.setData({ phases: groupCoreCourses(courses), catalogTotal: courses.length, catalogLoading: false });
 } catch (err) {
 this.setData({ catalogLoading: false, catalogError: '课程目录同步失败，请重试' });
 }
 },

 onShareAppMessage() {
 return {
 title: '康波研究院：65门课程 + 500本书单，先从一节试学开始',
 path: '/pages/index/index?utm_source=wechat_share&utm_campaign=miniapp_launch'
 };
 },

 onShareTimeline() {
 return {
 title: '康波研究院：用课程和书单建立周期判断力',
 query: 'utm_source=wechat_timeline&utm_campaign=miniapp_launch'
 };
 },

 onUnload() {
 this.destroyHomeAudio();
 },

 onPhaseTap(e) {
 wx.switchTab({ url: '/pages/courses/courses' });
 },

 async loadAudioPlaylist(scope = 'all') {
 this.setData({
 audioScope: scope,
 audioScopeLabel: AUDIO_SCOPE_LABELS[scope] || AUDIO_SCOPE_LABELS.all,
 audioListLoading: true,
 audioError: ''
 });
 try {
 const res = await api.getAudioPlaylist(scope);
 const tracks = (res.tracks || []).map((track, index) => this.normalizeAudioTrack(track, index));
 const currentAudio = tracks[0] || null;
 this.setData({
 audioTracks: tracks,
 audioTotal: tracks.length,
 audioCounts: res.counts || { core: 0, book: 0 },
 currentAudioIndex: 0,
 currentAudio,
 audioPreviewTracks: this.buildAudioPreview(tracks, 0),
 audioListLoading: false,
 audioPlaying: false,
 audioReady: false,
 audioCurrent: 0,
 audioDuration: 0,
 audioProgress: 0,
 audioCurrentText: '00:00',
 audioDurationText: '--:--'
 });
 if (this.audioCtx) {
 this.audioCtx.stop();
 if (currentAudio) this.audioCtx.src = currentAudio.audioUrl;
 }
 } catch (err) {
 this.setData({
 audioListLoading: false,
 audioTotal: 0,
 audioError: err.message || '音频清单加载失败'
 });
 }
 },

 normalizeAudioTrack(track, index) {
 const isBook = track.type === 'book';
 const subtitle = isBook
 ? `书目课程 ${track.courseId}${track.author ? ` · ${track.author}` : ''}`
 : `主干课程 ${track.courseId}`;
 return {
 ...track,
 index,
 displayNo: index + 1,
 subtitle,
 typeBadge: isBook ? '书目' : '主干'
 };
 },

 buildAudioPreview(tracks, currentIndex) {
 if (!tracks.length) return [];
 let start = Math.max(0, currentIndex - 2);
 let end = Math.min(tracks.length, start + 8);
 start = Math.max(0, end - 8);
 return tracks.slice(start, end).map(track => ({
 ...track,
 active: track.index === currentIndex
 }));
 },

 switchAudioScope(e) {
 const scope = e.currentTarget.dataset.scope || 'all';
 if (scope === this.data.audioScope && this.data.audioTracks.length) return;
 this.loadAudioPlaylist(scope);
 },

 initHomeAudio() {
 if (this.audioCtx) return;
 const audio = wx.createInnerAudioContext();
 audio.obeyMuteSwitch = false;

 audio.onCanplay(() => {
 this.setData({ audioLoading: false, audioReady: true, audioError: '' });
 setTimeout(() => this.syncHomeAudioTime(true), 300);
 });
 audio.onPlay(() => this.setData({ audioPlaying: true, audioLoading: false }));
 audio.onPause(() => this.setData({ audioPlaying: false }));
 audio.onStop(() => this.setData({ audioPlaying: false }));
 audio.onEnded(() => this.nextAudio(true));
 audio.onTimeUpdate(() => this.syncHomeAudioTime());
 audio.onError(err => {
 console.error('首页连续播放失败:', err);
 this.setData({
 audioPlaying: false,
 audioLoading: false,
 audioReady: false,
 audioError: '当前音频加载失败，正在切换下一课'
 });
 setTimeout(() => this.nextAudio(true), 900);
 });

 this.audioCtx = audio;
 },

 toggleHomeAudio() {
 if (this.data.audioPlaying) {
 if (this.audioCtx) this.audioCtx.pause();
 return;
 }
 this.playHomeAudio();
 },

 playHomeAudio() {
 const current = this.data.currentAudio;
 if (!current || !current.audioUrl) {
 wx.showToast({ title: '暂无可播放音频', icon: 'none' });
 return;
 }
 this.initHomeAudio();
 if (this.audioCtx.src !== current.audioUrl) {
 this.audioCtx.src = current.audioUrl;
 }
 this.setData({ audioLoading: true, audioError: '' });
 this.audioCtx.play();
 },

 setCurrentAudio(index, autoplay = false) {
 const tracks = this.data.audioTracks || [];
 if (!tracks.length) return;
 const safeIndex = ((index % tracks.length) + tracks.length) % tracks.length;
 const currentAudio = tracks[safeIndex];
 this.setData({
 currentAudioIndex: safeIndex,
 currentAudio,
 audioPreviewTracks: this.buildAudioPreview(tracks, safeIndex),
 audioCurrent: 0,
 audioDuration: 0,
 audioProgress: 0,
 audioCurrentText: '00:00',
 audioDurationText: '--:--',
 audioError: ''
 });
 if (this.audioCtx) {
 this.audioCtx.stop();
 this.audioCtx.src = currentAudio.audioUrl;
 }
 if (autoplay) {
 setTimeout(() => this.playHomeAudio(), 80);
 }
 },

 nextAudio(autoplay = false) {
 this.setCurrentAudio(this.data.currentAudioIndex + 1, autoplay);
 },

 prevAudio() {
 this.setCurrentAudio(this.data.currentAudioIndex - 1, this.data.audioPlaying);
 },

 selectAudioTrack(e) {
 const index = Number(e.currentTarget.dataset.index || 0);
 this.setCurrentAudio(index, true);
 },

 syncHomeAudioTime(force = false) {
 if (!this.audioCtx || this.audioSeeking) return;
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

 onHomeAudioSliderChanging(e) {
 this.audioSeeking = true;
 this.setData({ audioProgress: e.detail.value });
 },

 onHomeAudioSliderChange(e) {
 const duration = this.data.audioDuration || 0;
 const value = e.detail.value || 0;
 const target = duration ? duration * value / 100 : 0;
 if (this.audioCtx && duration) {
 this.audioCtx.seek(target);
 }
 this.audioSeeking = false;
 this.setData({
 audioCurrent: target,
 audioProgress: value,
 audioCurrentText: this.formatAudioTime(target)
 });
 },

 destroyHomeAudio() {
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
 }
});
